"""Async generation execution — the worker's per-job core (async-pad 증분 2b).

Runs one claimed ``WritingGenerationJob`` through the same pipeline the sync
generate endpoint uses (context build → generate) and appends the result to the
scratch store (D1=A) for the pad, then marks the job terminal. Kept separate
from the CLI/loop (``scripts/generation_job_worker.py``) so the execution
contract is unit-testable with a fake provider — no Mongo, no gateway, no daemon.

Failure taxonomy is the ``WritingGenerationJobFailureReason`` contract: each
mapped generate-pipeline exception → its reason, and an outermost catch-all →
``INTERNAL`` so any unmapped fault — generate-pipeline OR a result-persist
failure (the scratch store down after a successful generate) — still reaches a
terminal state (verification H-2 / H-1(2b); otherwise the job livelocks RUNNING
→ reclaim → re-fail, re-running the expensive generate each time).

Reclaim idempotency (verification H-3): a worker that generated then crashed
before marking the job leaves a scratch entry; on reclaim the re-run would
append a second. ``execute_generation_job`` clears this job's prior scratch
(keyed by ``request_id``, reusing the 2a per-request delete) before saving, so
each job leaves at most one scratch entry regardless of reclaims.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.application.app.context_search.models import (
    ContextBudget,
    ContextNeed,
    ContextSearchPurpose,
    ContextSearchRequest,
    CurrentPosition,
)
from services.application.app.context_search.service import (
    ContextSearchBudgetExceeded,
    ContextSearchFailed,
    ContextSearchService,
    InvalidContextSearchRequest,
)
from services.application.app.writing.generation_job import (
    WritingGenerationJob,
    WritingGenerationJobFailureReason,
    WritingGenerationJobService,
)
from services.application.app.observability.llm_call_audit import LlmCallAuditService
from services.application.app.observability.llm_call_scope import (
    llm_call_scope,
    reclassify_planner_parse_error,
)
from services.application.app.writing.models import WritingRequest, WritingTaskType
from services.application.app.writing.report import InvalidCandidateReport
from services.application.app.writing.report import (
    TEMPLATE as REPORT_SYSTEM_TEMPLATE,
)
from services.application.app.writing.report_budget import derive_context_budget
from services.application.app.writing.scratch import WritingScratchService
from services.application.app.writing.service import WritingError, WritingService


@dataclass(frozen=True)
class GenerationCollaborators:
    """The env-configured services the executor drives. Assembled by
    ``main.build_async_generation_collaborators`` (production/worker) or by hand
    (tests)."""

    context_search: ContextSearchService
    writing: WritingService
    scratch: WritingScratchService
    jobs: WritingGenerationJobService
    needs: tuple[ContextNeed, ...]
    # Observability seam C (증분 C, owner decision 2026-07-26 D3). The worker is
    # the one path outside a request that may still open an ``llm_call_scope``:
    # it holds a real ``project_id``/``request_id`` from the claimed job, so
    # nothing has to be guessed. Without it the medium/long presets — the
    # expensive generations — would be the only ones missing from the KPI.
    # Optional so hand-assembled test collaborators stay valid; None simply
    # records nothing.
    llm_call_audit: LlmCallAuditService | None = None
    # R-a (오너 2026-07-31). 워커의 생성은 곧바로 self-report로 이어지고 그쪽이 창을
    # 구속하므로, 패키지 예산을 창에서 유도한다. **Optional인 이유는 llm_call_audit과 같다** —
    # 손으로 조립한 테스트 collaborators가 그대로 유효해야 하고, None이면 유도 없이 요청값을
    # 쓴다(종전 동작).
    # 둘 중 하나라도 없으면 유도하지 않는다. 상한 기본값을 여기에 복제하지 않는 것이
    # 의도다 — 리터럴 사본은 main과 워커가 서로 다른 상한을 믿게 만드는 가장 흔한 길이다.
    capabilities: object | None = None
    report_output_cap: int | None = None


async def execute_generation_job(
    job: WritingGenerationJob, collaborators: GenerationCollaborators
) -> WritingGenerationJob:
    """Run one claimed (RUNNING) job to a terminal state and return it."""
    c = collaborators
    fail = c.jobs.mark_failed
    reasons = WritingGenerationJobFailureReason
    with llm_call_scope(c.llm_call_audit, project_id=job.project_id,
                        correlation_id=job.request_id) as scope:
        try:
            search_request = ContextSearchRequest(
                project_id=job.project_id,
                purpose=ContextSearchPurpose.WRITING_CONTEXT,
                needs=c.needs,
                query=job.query or job.instruction,
                current_position=CurrentPosition(
                    draft_id=job.draft_id, version_id=job.version_id),
                context_budget=ContextBudget(max_tokens=await derive_context_budget(
                    requested_tokens=job.max_tokens,
                    capabilities=(
                        c.capabilities if c.report_output_cap is not None else None
                    ),
                    report_output_cap=c.report_output_cap or 0,
                    report_system_template=REPORT_SYSTEM_TEMPLATE,
                    # 후보는 아직 없다 — 상한은 이 job이 요청한 출력 프리셋이다.
                    candidate_tokens_upper_bound=job.max_output_tokens,
                )),
            )
            package = await c.context_search.build_context_package(search_request)
            candidate = await c.writing.generate(
                request=WritingRequest(
                    request_id=job.request_id,
                    project_id=job.project_id,
                    task_type=WritingTaskType(job.task_type),
                    instruction=job.instruction,
                    draft_excerpt=job.draft_excerpt,
                ),
                package=package,
                max_output_tokens=job.max_output_tokens,
            )
            # H-3 + H-1(2b): the result-persist phase lives INSIDE the catch-all so
            # a scratch-write fault (the store down after a successful generate)
            # terminates the job via INTERNAL instead of escaping to crash the worker
            # loop and re-running the expensive generate on every reclaim. H-3 still
            # holds: clear this job's prior (crashed-attempt) scratch before saving,
            # so a reclaim replaces rather than duplicates the pad result.
            c.scratch.clear_accepted_item(
                job.project_id, job.draft_id, job.request_id)
            entry = c.scratch.save(
                project_id=job.project_id,
                draft_id=job.draft_id,
                request_id=job.request_id,
                task_type=candidate.task_type.value,
                output_type=candidate.output_type.value,
                instruction=job.instruction,
                candidate_text=candidate.text,
                version_id=job.version_id,
            )
        except (WritingError, InvalidContextSearchRequest) as exc:
            return fail(job, reason=reasons.INVALID_REQUEST, detail=str(exc))
        except InvalidCandidateReport as exc:
            # Same rule as the sync endpoints (D4): the reporter answered and
            # the domain rejected that answer, so the last row is a parse_error.
            scope.reclassify_last_as_parse_error(type(exc).__name__)
            return fail(job, reason=reasons.INVALID_REPORT, detail=str(exc))
        except ContextSearchBudgetExceeded as exc:
            return fail(job, reason=reasons.CONTEXT_BUDGET_EXCEEDED, detail=str(exc))
        except ContextSearchFailed as exc:
            # Same shared rule the endpoints use — a second copy here is how
            # the worker's policy would drift from theirs (verification H-2).
            reclassify_planner_parse_error(scope, exc)
            return fail(job, reason=reasons.CONTEXT_SEARCH_FAILED,
                        detail=f"{exc.error_type.value}: {exc.detail}")
        except ProviderError as exc:
            # 창 가드 거부는 별도 사유다(K-3, 오너 2026-07-30) — job은 실패하지만 원인은
            # 상류 장애가 아니라 "요청이 창을 넘었다"이고, 재시도는 같은 실패로 끝난다.
            if exc.code is ProviderErrorCode.CONTEXT_WINDOW_EXCEEDED:
                reason = reasons.CONTEXT_WINDOW_EXCEEDED
            elif exc.code is ProviderErrorCode.TIMEOUT:
                reason = reasons.PROVIDER_TIMEOUT
            else:
                reason = reasons.PROVIDER_ERROR
            return fail(job, reason=reason, detail=str(exc))
        except Exception as exc:  # noqa: BLE001 — H-2 catch-all (now covers persist too): never livelock
            return fail(job, reason=reasons.INTERNAL, detail=repr(exc))
        return c.jobs.mark_succeeded(job, result_scratch_id=entry.id)
