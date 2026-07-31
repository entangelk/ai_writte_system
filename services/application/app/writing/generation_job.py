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

    def purge_project(self, project_id: str) -> None: ...


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

    def purge_project(self, project_id: str) -> None:
        # D8-6b-2: project 의 generation job 전부 파기(직접 project_id 스코프).
        ids = [jid for jid, j in self.jobs.items() if j.project_id == project_id]
        for jid in ids:
            del self.jobs[jid]
        self._request_index = {
            k: v for k, v in self._request_index.items() if k[0] != project_id
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

    def enqueue(
        self, *, project_id: str, draft_id: str, request_id: str,
        task_type: str, instruction: str, draft_excerpt: str,
        query: str | None, output_length: str, max_output_tokens: int,
        max_tokens: int, version_id: str,
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
            created_at=self._clock(),
        )
        self._repo.add(job)
        return CreateWritingGenerationJobResult(job=job, idempotent_replay=False)

    def get(self, job_id: str) -> WritingGenerationJob | None:
        return self._repo.get(job_id)

    def list_for_draft(
        self, project_id: str, draft_id: str
    ) -> tuple[WritingGenerationJob, ...]:
        return self._repo.list_for_draft(project_id, draft_id)

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
