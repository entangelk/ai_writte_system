"""Background generation job store for the async result pad.

Decision brief ``docs/plans/async-generation-pad-decisions.md`` (D3=B / D4=A /
D5=A, 2026-07-20). Long presets (``medium``=2048, ``long``=4096) are too slow to
block a request, so they run in the **worker** instead: the generate endpoint
enqueues a ``WritingGenerationJob`` here, the worker atomically claims it, runs
the same context-build + generate pipeline, and appends the result to the
existing ``writing_drafts_scratch`` recovery store (D1=A) for the pad to display.

This module is the **data layer only** (async-pad 증분 2a): the job model, the
state machine, the repository boundary, and the atomic claim. It wires into
nothing yet — the endpoint branch (D5) and the worker execution loop (D3) land
in 증분 2c and 2b respectively. Building it standalone keeps the worker's first
LLM-execution diff isolated.

Design mirrors the Analysis job precedent (``analysis/models.py`` +
``analysis/service.py`` — same ``pending/running/succeeded/failed`` states and
transition enforcement) and the index-sync worker claim (``indexing/
mongo_repository.py::claim_next_outbox_entry`` — ``find_one_and_update`` with a
lease so a crashed worker's in-flight job is reclaimable, and concurrent/replica
workers never double-run). D4=A keeps the job (execution state) separate from
scratch (the result), so scratch stays the simple append/delete store it is.

**Async requires a draft anchor.** The pad is keyed by ``(project_id,
draft_id)``, so a job has nowhere to display without one — ``draft_id`` and
``version_id`` are required (they come from the generate request's
``current_position``). The endpoint branch (2c) therefore rejects an async
preset with no ``current_position``; the model already assumes this.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Callable, Protocol
from uuid import uuid4

# How long a claimed (RUNNING) job may sit before another worker may reclaim it.
# Mirrors the index-sync outbox lease: if a worker crashes mid-generation, the
# job is not stranded. A long generate (``long``≈91s) must fit comfortably under
# this, so the default is generous and env-tunable.
DEFAULT_CLAIM_TIMEOUT_SECONDS = 600


class WritingGenerationJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class WritingGenerationJobFailureReason(StrEnum):
    """Failure taxonomy the worker (증분 2b) maps the generate pipeline's
    exceptions onto. The *exception set* is grounded in the sync generate
    endpoint's ``except`` blocks (``main.py`` writing_generate_endpoint); the
    worker classifies those same exceptions into a job reason, not an HTTP
    status (it produces no HTTP response), so no status codes are implied here:

    - ``INVALID_REQUEST``      ← WritingError / InvalidContextSearchRequest
    - ``INVALID_REPORT``       ← InvalidCandidateReport
    - ``CONTEXT_BUDGET_EXCEEDED`` ← ContextSearchBudgetExceeded
    - ``CONTEXT_WINDOW_EXCEEDED`` ← ProviderError(CONTEXT_WINDOW_EXCEEDED)
    - ``CONTEXT_SEARCH_FAILED`` ← ContextSearchFailed
    - ``PROVIDER_ERROR``       ← ProviderError (non-timeout)
    - ``PROVIDER_TIMEOUT``     ← ProviderError with code ProviderErrorCode.TIMEOUT

    The timeout split follows the writing endpoints' established convention —
    ``accept`` distinguishes ``ProviderErrorCode.TIMEOUT`` (the generate
    endpoint itself collapses all ProviderError to one status), and the worker
    keeps them apart so the pad can tell "timed out" from other provider faults.

    ``INTERNAL`` is the catch-all (verification H-2): the mapped reasons cover
    only the generate pipeline's *known* exceptions, so the worker's outermost
    handler maps any **unmapped** fault (a pymongo/httpx infra error, a bug) onto
    ``INTERNAL`` and marks the job FAILED. Without it such a job would never reach
    a terminal state and would livelock RUNNING → lease-reclaim → re-fail.
    """

    INVALID_REQUEST = "invalid_request"
    INVALID_REPORT = "invalid_report"
    CONTEXT_BUDGET_EXCEEDED = "context_budget_exceeded"
    # K-3 창 가드(오너 2026-07-30). `PROVIDER_ERROR`와 **구분해야 한다**: 모델을 부르기
    # 전에 우리가 거부한 것이라 재시도는 반드시 같은 실패로 끝나고(입력을 줄여야 한다),
    # 비용도 0이다. 같은 사유로 접으면 "재시도하면 될 실패"와 섞여 보인다.
    CONTEXT_WINDOW_EXCEEDED = "context_window_exceeded"
    CONTEXT_SEARCH_FAILED = "context_search_failed"
    PROVIDER_ERROR = "provider_error"
    PROVIDER_TIMEOUT = "provider_timeout"
    INTERNAL = "internal"


@dataclass(frozen=True, slots=True)
class WritingGenerationJob:
    id: str
    project_id: str
    draft_id: str
    request_id: str
    task_type: str
    instruction: str
    draft_excerpt: str
    # Retrieval query for the internal context search (None → the endpoint uses
    # the instruction, same as the sync path).
    query: str | None
    # Symbolic async preset (medium|long) — kept for the pad/debug alongside the
    # resolved token cap so the record stays model-agnostic (D3=A: server owns
    # the mapping; the record carries the resolved value so the worker need not
    # re-read env).
    output_length: str
    max_output_tokens: int
    # Input ContextPackage budget (the request's ``max_tokens``); distinct axis
    # from output tokens.
    max_tokens: int
    # Base version the generation is anchored to (from current_position) — the
    # worker stamps it onto the scratch result (D7) and the pad shows it.
    version_id: str
    created_at: datetime
    # Generate-time W3 intent fields. Async results surface through scratch, so
    # these must ride the job to keep a later pad accept from defaulting to append.
    intent: str | None = None
    next_unit: dict[str, str | None] | None = None
    # Phase 8 Slice 8.3 (Q1-b=A, 오너 2026-08-04). 202 는 "접수 성공"이지 "생성
    # 성공"이 아니므로 **워커가 성공 시 원장에 쓴다** — 그러려면 이 job 이 누구
    # 것인지 워커가 알아야 하고, 그 한 필드가 이것이다. 부모 계획이 8.4 에 배정한
    # "워커의 주체 전달"을 Q1=C(성공차감)가 여기로 당겼다.
    #
    # ``None`` 인 job 은 **과금되지 않는다**: 세션 없이 만들어질 수 있는 경로가
    # 없으므로 실제로는 8.3 이전에 만들어진 옛 행뿐이고, 주체를 추측해 남의
    # 사용량에 얹느니 안 세는 편이 옳다(오너 정책: 무노동 무과금과 같은 방향).
    user_id: str | None = None
    status: WritingGenerationJobStatus = WritingGenerationJobStatus.PENDING
    claimed_at: datetime | None = None
    failure_reason: WritingGenerationJobFailureReason | None = None
    failure_detail: str | None = None
    # Set on success: the scratch entry the worker wrote the result into, so the
    # status surface (2c) can point the pad straight at it.
    result_scratch_id: str | None = None


@dataclass(frozen=True, slots=True)
class CreateWritingGenerationJobResult:
    job: WritingGenerationJob
    idempotent_replay: bool


# PENDING→RUNNING is the claim; RUNNING→{SUCCEEDED,FAILED} are the worker's
# outcomes. A stale RUNNING job is reclaimed by the lease inside ``claim_next``
# (it stays RUNNING), not by a transition. FAILED→PENDING is the explicit user
# retry (D4=A: "orphan/retry도 Analysis 계약을 재사용") — driven by
# ``mark_pending_for_retry`` below (mirrors AnalysisService.retry_failed_job), so
# the transition is never callerless. Only FAILED is retryable; succeeded and the
# in-flight states raise (the endpoint maps that to 409).
_ALLOWED_TRANSITIONS: frozenset[
    tuple[WritingGenerationJobStatus, WritingGenerationJobStatus]
] = frozenset(
    {
        (WritingGenerationJobStatus.PENDING, WritingGenerationJobStatus.RUNNING),
        (WritingGenerationJobStatus.RUNNING, WritingGenerationJobStatus.SUCCEEDED),
        (WritingGenerationJobStatus.RUNNING, WritingGenerationJobStatus.FAILED),
        (WritingGenerationJobStatus.FAILED, WritingGenerationJobStatus.PENDING),
    }
)


#: 8.3 Q1-b=A 의 "진행 중 job" = 아직 결과가 나오지 않은 상태 둘. 완료·실패한 job 은
#: 세지 않는다 — 성공은 원장 행이 대신 세고, 실패는 애초에 과금하지 않는다(Q1=C).
_ACTIVE_STATUSES: frozenset[WritingGenerationJobStatus] = frozenset({
    WritingGenerationJobStatus.PENDING,
    WritingGenerationJobStatus.RUNNING,
})


class InvalidJobStateTransition(RuntimeError):
    """A mark_* was asked for a transition the state machine forbids."""


class WritingGenerationJobRepository(Protocol):
    def add(self, job: WritingGenerationJob) -> None: ...
    def get(self, job_id: str) -> WritingGenerationJob | None: ...
    def find_request(self, project_id: str, request_id: str) -> str | None: ...
    def update(self, job: WritingGenerationJob) -> None: ...
    def claim_next(
        self, *, now: datetime, claim_timeout_seconds: int
    ) -> WritingGenerationJob | None: ...
    def list_for_draft(
        self, project_id: str, draft_id: str
    ) -> tuple[WritingGenerationJob, ...]: ...

    def count_active_for_user(self, user_id: str) -> int:
        """그 회원의 **대기·실행 중** job 수 (8.3 Q1-b=A).

        비동기 생성은 202 에서 잠금이 풀리므로(Q8=C) 워커가 도는 91초 동안 그
        요청은 진행 중 계수에서 빠진다 — 그 자리를 이 계수가 덮는다. 없으면 회원이
        async job 을 쌓아 한도를 우회한다.
        """

    def purge_project(self, project_id: str) -> None: ...
    def purge_draft(self, project_id: str, draft_id: str) -> None: ...


class InMemoryWritingGenerationJobRepository:
    def __init__(self) -> None:
        self.jobs: dict[str, WritingGenerationJob] = {}
        # (project_id, request_id) → job_id, for enqueue idempotency.
        self._request_index: dict[tuple[str, str], str] = {}

    def add(self, job: WritingGenerationJob) -> None:
        self.jobs[job.id] = job
        self._request_index[(job.project_id, job.request_id)] = job.id

    def get(self, job_id: str) -> WritingGenerationJob | None:
        return self.jobs.get(job_id)

    def find_request(self, project_id: str, request_id: str) -> str | None:
        return self._request_index.get((project_id, request_id))

    def update(self, job: WritingGenerationJob) -> None:
        self.jobs[job.id] = job

    def claim_next(
        self, *, now: datetime, claim_timeout_seconds: int
    ) -> WritingGenerationJob | None:
        stale_before = now - timedelta(seconds=claim_timeout_seconds)

        def _claimable(job: WritingGenerationJob) -> bool:
            if job.status is WritingGenerationJobStatus.PENDING:
                return True
            # Reclaim a RUNNING job whose worker went silent past the lease.
            return (
                job.status is WritingGenerationJobStatus.RUNNING
                and job.claimed_at is not None
                and job.claimed_at <= stale_before
            )

        candidates = sorted(
            (job for job in self.jobs.values() if _claimable(job)),
            key=lambda job: (job.created_at, job.id),
        )
        if not candidates:
            return None
        claimed = replace(
            candidates[0],
            status=WritingGenerationJobStatus.RUNNING,
            claimed_at=now,
        )
        self.jobs[claimed.id] = claimed
        return claimed

    def list_for_draft(
        self, project_id: str, draft_id: str
    ) -> tuple[WritingGenerationJob, ...]:
        return tuple(sorted(
            (job for job in self.jobs.values()
             if job.project_id == project_id and job.draft_id == draft_id),
            key=lambda job: (job.created_at, job.id),
            reverse=True,
        ))

    def count_active_for_user(self, user_id: str) -> int:
        return sum(
            1 for job in self.jobs.values()
            if job.user_id == user_id and job.status in _ACTIVE_STATUSES
        )

    def purge_project(self, project_id: str) -> None:
        # D8-6b-2: project 의 generation job 전부 파기(직접 project_id 스코프).
        ids = [jid for jid, j in self.jobs.items() if j.project_id == project_id]
        for jid in ids:
            del self.jobs[jid]
        self._request_index = {
            k: v for k, v in self._request_index.items() if k[0] != project_id
        }

    def purge_draft(self, project_id: str, draft_id: str) -> None:
        ids = [
            job_id for job_id, job in self.jobs.items()
            if job.project_id == project_id and job.draft_id == draft_id
        ]
        for job_id in ids:
            del self.jobs[job_id]
        removed = set(ids)
        self._request_index = {
            key: job_id for key, job_id in self._request_index.items()
            if job_id not in removed
        }


class WritingGenerationJobService:
    def __init__(
        self, repository: WritingGenerationJobRepository, *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
        claim_timeout_seconds: int = DEFAULT_CLAIM_TIMEOUT_SECONDS,
    ) -> None:
        self._repo = repository
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: "wgj:" + uuid4().hex)
        self._claim_timeout_seconds = claim_timeout_seconds

    def purge_project(self, *, project_id: str) -> None:
        # D8-6b-2: project 전체 파기의 generation-job 다리. endpoint(D8-6d)가 호출한다.
        self._repo.purge_project(project_id)

    def purge_draft(self, *, project_id: str, draft_id: str) -> None:
        self._repo.purge_draft(project_id, draft_id)

    def enqueue(
        self, *, project_id: str, draft_id: str, request_id: str,
        task_type: str, instruction: str, draft_excerpt: str,
        query: str | None, output_length: str, max_output_tokens: int,
        max_tokens: int, version_id: str, user_id: str | None = None,
        intent: str | None = None,
        next_unit: dict[str, str | None] | None = None,
    ) -> CreateWritingGenerationJobResult:
        # Idempotent on (project_id, request_id): re-submitting the same logical
        # generate (a retried POST) returns the existing job instead of running a
        # second background generation. Mirrors AnalysisService.create_job.
        existing_id = self._repo.find_request(project_id, request_id)
        if existing_id is not None:
            existing = self._repo.get(existing_id)
            if existing is not None:
                return CreateWritingGenerationJobResult(
                    job=existing, idempotent_replay=True)
        job = WritingGenerationJob(
            id=self._id_factory(),
            project_id=project_id,
            draft_id=draft_id,
            request_id=request_id,
            task_type=task_type,
            instruction=instruction,
            draft_excerpt=draft_excerpt,
            query=query,
            output_length=output_length,
            max_output_tokens=max_output_tokens,
            max_tokens=max_tokens,
            version_id=version_id,
            intent=intent,
            next_unit=next_unit,
            created_at=self._clock(),
            user_id=user_id,
        )
        self._repo.add(job)
        return CreateWritingGenerationJobResult(job=job, idempotent_replay=False)

    def get(self, job_id: str) -> WritingGenerationJob | None:
        return self._repo.get(job_id)

    def list_for_draft(
        self, project_id: str, draft_id: str
    ) -> tuple[WritingGenerationJob, ...]:
        return self._repo.list_for_draft(project_id, draft_id)

    def count_active_for_user(self, *, user_id: str) -> int:
        return self._repo.count_active_for_user(user_id)

    def has_other_active_for_draft(
        self, *, project_id: str, draft_id: str, request_id: str
    ) -> bool:
        """이 draft 에 **다른 요청의** 결과 대기 중 job 이 있는가 (8.3 Q8=C).

        202 로 잠금이 풀린 뒤의 재클릭이 **새 uuid 로 새 job 을 만들어 2회 과금**
        되는 것이 가장 비싼 실수 중복이라, 상태 축으로 한 번 더 막는다. 새 저장소도
        새 수명도 만들지 않는다 — 이미 있는 조회 하나다.

        **``request_id`` 를 빼는 것이 핵심이다.** 같은 ``request_id`` 의 재전송은
        ``enqueue`` 가 기존 job 을 그대로 돌려주는 **멱등 replay** 라 새 job 도 새
        과금도 만들지 않는다 — 그것까지 막으면 폴링·재전송하는 클라이언트가 자기
        job 을 조회하지 못한다. 막아야 하는 것은 **새 job 이 생기는 경우**뿐이다.
        """

        return any(
            job.status in _ACTIVE_STATUSES and job.request_id != request_id
            for job in self._repo.list_for_draft(project_id, draft_id)
        )

    def claim_next(self) -> WritingGenerationJob | None:
        return self._repo.claim_next(
            now=self._clock(),
            claim_timeout_seconds=self._claim_timeout_seconds,
        )

    def mark_succeeded(
        self, job: WritingGenerationJob, *, result_scratch_id: str,
    ) -> WritingGenerationJob:
        updated = replace(
            self._transition(job, WritingGenerationJobStatus.SUCCEEDED),
            result_scratch_id=result_scratch_id,
            failure_reason=None,
            failure_detail=None,
        )
        self._repo.update(updated)
        return updated

    def mark_failed(
        self, job: WritingGenerationJob, *,
        reason: WritingGenerationJobFailureReason, detail: str | None = None,
    ) -> WritingGenerationJob:
        updated = replace(
            self._transition(job, WritingGenerationJobStatus.FAILED),
            failure_reason=reason,
            failure_detail=detail,
        )
        self._repo.update(updated)
        return updated

    def mark_pending_for_retry(
        self, job: WritingGenerationJob,
    ) -> WritingGenerationJob:
        """Explicitly reset one FAILED job to PENDING so the worker re-claims it.

        Mirrors ``AnalysisService.retry_failed_job``. Unlike Analysis (whose
        caller then POSTs a separate ``run``), the generation worker's claim loop
        picks up any PENDING job on its own, so the retry alone resumes execution.
        Non-FAILED jobs raise ``InvalidJobStateTransition`` (the endpoint maps
        that to 409) — succeeded and the in-flight states are never retryable.
        The failure fields and the stale claim lease are cleared on the way back.
        """
        updated = replace(
            self._transition(job, WritingGenerationJobStatus.PENDING),
            failure_reason=None,
            failure_detail=None,
            claimed_at=None,
        )
        self._repo.update(updated)
        return updated

    def _transition(
        self, job: WritingGenerationJob, to: WritingGenerationJobStatus,
    ) -> WritingGenerationJob:
        if (job.status, to) not in _ALLOWED_TRANSITIONS:
            raise InvalidJobStateTransition(
                f"cannot move generation job {job.id} from {job.status} to {to}"
            )
        return replace(job, status=to)
