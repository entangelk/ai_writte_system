"""글쓰기 도메인 route (``/projects/{project_id}/writing*`` 13 operation).

``main.py`` 의 ``create_app()`` 에서 옮겨온 register 함수(R1). handler 본문은
byte-동일이다.

**유료 6경로** 가 섞여 있다 — ``generate`` · ``gate`` · ``report`` · ``revise`` ·
``revise-and-gate`` · ``accept`` 가 ``_REQUIRE_PROJECT_OWNER_BILLABLE`` (소유권 →
시행 순서) 이고 나머지 7경로는 ``_REQUIRE_PROJECT_OWNER`` 다. 그 순서가 곧
"404·403 은 무과금" 이며 ``BillableRouteWiringTest`` 가 route 선언에서 직접 잰다.

**partial envelope 5곳** 이 있다 — ``revise-and-gate`` 의 부분 실패 4 + ``accept``
의 분석 오류 1. 되돌릴 수 없는 성공 부분이 이미 영속된 실패 경로만 허용되는 균일
본문 예외(H3)이며 ``JSONResponse`` 로 직접 반환된다. 이동은 byte-동일.

``_analysis_job_payload`` 만 ``..api.payloads`` 에서 온다(analysis 와 공유 —
라우터 분해 3차에서 내림). 나머지 writing 직렬화기 9종 + 헬퍼 2종
(``_record_loop_audit``·``_clear_scratch_for_saved_accept``) 은 writing 전용이라
여기 있다(헬퍼 2종은 handler 내부 중첩이라 handler 와 함께 옮겨옴).
"""

from __future__ import annotations

from fastapi import (
    Depends,
    HTTPException,
    Request,
)
from fastapi.responses import JSONResponse
from services.application.app.context_search.models import (
    ContextBudget,
    ContextSearchPurpose,
    ContextSearchRequest,
    CurrentPosition,
)
from services.application.app.context_search.service import (
    ContextSearchBudgetExceeded,
    ContextSearchFailed,
    InvalidContextSearchRequest,
)
from services.application.app.core_sot.models import UnitKind
from services.application.app.core_sot.service import (
    Archived,
    DraftOrderIntegrityError,
    NotFound,
)
from services.application.app.observability.llm_call_audit import gate_quality_score
from services.application.app.observability.llm_call_scope import (
    llm_call_scope,
    reclassify_planner_parse_error,
)
from services.application.app.writing.accept import (
    StaleWritingBase,
    WritingAcceptAnalysisError,
    WritingAcceptError,
)
from services.application.app.writing.context_pointer import pointer_wire
from services.application.app.writing.gate import (
    InvalidWritingGateResult,
    WritingGateError,
)
from services.application.app.writing.generation_job import (
    InvalidJobStateTransition as InvalidGenerationJobStateTransition,
)
from services.application.app.writing.http_models import (
    ACCEPT_RESPONSES,
    GENERATE_ASYNC_RESPONSES,
    REVISE_AND_GATE_RESPONSES,
    WritingAcceptResponse,
    WritingCandidatePayload,
    WritingContextBudgetPayload,
    WritingGatePayload,
    WritingGenerationJobPayload,
    WritingReviseGateResponse,
)
from services.application.app.writing.loop_audit import WritingLoopAuditNotFound
from services.application.app.writing.models import (
    NextUnit,
    OutputLength,
    WritingCandidate,
    WritingGateDecision,
    WritingGateFinding,
    WritingGateFindingType,
    WritingGateSeverity,
    WritingIntent,
    WritingOutputType,
    WritingRequest,
    WritingTaskType,
)
from services.application.app.writing.report import (
    InvalidCandidateReport,
    TEMPLATE as REPORT_SYSTEM_TEMPLATE,
)
from services.application.app.writing.report_budget import (
    candidate_tokens_from_text,
    derive_context_budget,
)
from services.application.app.writing.retrieval import (
    InvalidWritingRetrievalPlan,
    WritingRetrievalPlannerError,
)
from services.application.app.writing.revise import (
    InvalidWritingRevision,
    WritingRevisionError,
)
from services.application.app.writing.revise_gate import (
    WritingLoopRevisionFailure,
    WritingRetrievalConfigurationError,
    WritingRetrievalFailure,
    WritingReviseGateFailure,
    WritingReviseReportFailure,
)
from services.application.app.writing.service import WritingError
from services.llm_gateway.app.errors import (
    ProviderError,
    ProviderErrorCode,
)
from ..api.dependencies import (
    _REQUIRE_PROJECT_OWNER,
    _REQUIRE_PROJECT_OWNER_BILLABLE,
    project_existence_check,
    quota_charge,
    quota_confirmed,
    require_authenticated_user,
)
from ..api.errors import (
    _BILLABLE_400_404_502_504_CONFIG,
    _ERRORS_404,
    _ERRORS_404_409,
    _billable,
    _owned,
    _provider_error_status,
)
from ..api.models import (
    DEFAULT_CONTEXT_BUDGET_TOKENS,
    WritingAcceptRequest,
    WritingGateRequest,
    WritingGenerateRequest,
    WritingReportRequest,
    WritingReviseRequest,
    _WRITING_CONTINUE_SCENE_NEEDS,
    _writing_output_length_tokens,
)
from ..api.payloads import _analysis_job_payload
from ..env import _env_bool


def register_writing(
    app,
    *,
    core_sot,
    writing,
    writing_gate,
    writing_report,
    writing_revision,
    writing_revise_gate,
    writing_accept,
    writing_generation_jobs,
    writing_scratch,
    writing_loop_audit,
    context_search,
    llm_call_audit,
    model_capabilities,
    report_output_cap,
    activity,
) -> None:
    _require_project_exists = project_existence_check(core_sot)
    def _writing_candidate_payload(candidate) -> dict[str, object]:
        return {
            "request_id": candidate.request_id,
            "project_id": candidate.project_id,
            "task_type": candidate.task_type.value,
            "output_type": candidate.output_type.value,
            "text": candidate.text,
            "status": candidate.status,
            "self_reported_constraints": list(candidate.self_reported_constraints),
            "candidate_claims": [
                {"text": x.text, "type": x.claim_type.value,
                 "requires_gate_check": x.requires_gate_check,
                 "related_context_pointers": [
                     pointer_wire(p) for p in x.related_context_pointers]}
                for x in candidate.candidate_claims],
            "new_memory_hints": [
                {"type": x.hint_type.value, "text": x.text,
                 "confidence": x.confidence,
                 "should_analyze_after_save": x.should_analyze_after_save}
                for x in candidate.new_memory_hints],
            "risk_notes": [
                {"type": x.risk_type.value, "severity": x.severity.value,
                 "message": x.message} for x in candidate.risk_notes],
            "candidate_id": candidate.candidate_id,
            "generated_by_model": candidate.generated_by_model,
        }

    def _writing_generation_job_payload(job) -> dict[str, object]:
        # Async generation job status (async-pad D5=A, v1.7.27 = 증분 2c). Used by
        # GET .../writing/generation-jobs/{job_id} (validated through
        # WritingGenerationJobPayload) and nested under ``job`` in the 202 envelope
        # the generate endpoint returns for medium/long presets. The terminal
        # fields (result_scratch_id / failure_reason / failure_detail) are None
        # until the worker reaches a terminal state.
        return {
            "job_id": job.id,
            "request_id": job.request_id,
            "project_id": job.project_id,
            "draft_id": job.draft_id,
            "version_id": job.version_id,
            "task_type": job.task_type,
            "output_length": job.output_length,
            "status": job.status.value,
            "created_at": job.created_at.isoformat(),
            "result_scratch_id": job.result_scratch_id,
            "failure_reason": (
                job.failure_reason.value if job.failure_reason is not None else None
            ),
            "failure_detail": job.failure_detail,
        }

    def _writing_gate_payload(result) -> dict[str, object]:
        return {
            "request_id": result.request_id,
            "project_id": result.project_id,
            "decision": result.decision.value,
            "findings": [{
                "type": item.finding_type.value,
                "severity": item.severity.value,
                "message": item.message,
                "evidence": item.evidence,
                "recommended_decision": item.recommended_decision.value,
            } for item in result.findings],
            "checked_constraints": list(result.checked_constraints),
            "evaluated_by_model": result.evaluated_by_model,
        }

    def _writing_loop_payload(loop) -> dict[str, object]:
        return {
            "status": loop.status.value,
            "revision_rounds": loop.revision_rounds,
            "retrieval_rounds": loop.retrieval_rounds,
            "gate_evaluations": loop.gate_evaluations,
        }

    def _writing_stages_payload(stages) -> list[dict[str, object]]:
        return [{
            "stage": item.stage.value,
            "ordinal": item.ordinal,
            "status": item.status.value,
        } for item in stages]

    def _writing_loop_audit_summary_payload(run) -> dict[str, object]:
        return {
            "audit_id": run.id,
            "request_id": run.request_id,
            "loop_status": run.loop_status,
            "error_type": run.error_type,
            "revision_rounds": run.revision_rounds,
            "retrieval_rounds": run.retrieval_rounds,
            "gate_evaluations": run.gate_evaluations,
            # Phase 5.10 ("B2") aggregate metering — bodyless run-level metric,
            # exposed only on the persisted audit (M5=A), never on the ephemeral
            # loop response.
            "total_tokens": run.total_tokens,
            "wall_clock_ms": run.wall_clock_ms,
            "created_at": run.created_at.isoformat(),
        }

    def _writing_loop_audit_payload(run) -> dict[str, object]:
        return {
            **_writing_loop_audit_summary_payload(run),
            "trigger_finding_fingerprint": run.trigger_finding_fingerprint,
            "initial_candidate_hash": run.initial_candidate_hash,
            "final_candidate_hash": run.final_candidate_hash,
            "final_candidate_text": run.final_candidate_text,
            "final_gate_decision": run.final_gate_decision,
            "final_gate_finding_fingerprints": list(
                run.final_gate_finding_fingerprints
            ),
            "stages": [{
                "stage": stage.stage, "ordinal": stage.ordinal,
                "status": stage.status,
                "candidate_hash": stage.candidate_hash,
                "finding_fingerprint": stage.finding_fingerprint,
                "pointer_ids": list(stage.pointer_ids),
            } for stage in run.stages],
        }

    def _accepted_save_payload(saved, target_draft) -> dict[str, object]:
        return {
            "draft_id": saved.draft_version.draft_id,
            "draft_version_id": saved.draft_version.id,
            "version_number": saved.draft_version.version_number,
            "snapshot_id": saved.snapshot.id,
            "content_hash": saved.snapshot.content_hash,
            "unit_kind": target_draft.unit_kind.value,
            "position": target_draft.position,
        }

    @app.post("/projects/{project_id}/writing/generate",
              response_model=WritingCandidatePayload,
              responses=_owned({**GENERATE_ASYNC_RESPONSES,
                                **_BILLABLE_400_404_502_504_CONFIG}),
              dependencies=_REQUIRE_PROJECT_OWNER_BILLABLE)
    async def writing_generate_endpoint(
        project_id: str, body: WritingGenerateRequest, request: Request
    ) -> dict[str, object]:
        # Phase 5.1: continue_scene generation. The intended flow is
        # context request → ContextPackage → Writing AI (핵심 흐름), so the
        # endpoint builds the package via context search, then generates.
        try:
            _require_project_exists(project_id)
            task_type = WritingTaskType(body.task_type)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"unsupported task_type: {body.task_type}"
            ) from exc
        # 증분 2 (D3=A): resolve the output-length preset to a token cap. The server
        # owns the mapping; an unknown preset is a 400 (same shape as task_type).
        try:
            output_length = OutputLength(body.output_length)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"unsupported output_length: {body.output_length}",
            ) from exc
        output_tokens = _writing_output_length_tokens()[output_length]
        # 증분 2c (D5=A): medium/long presets are too slow to block the request, so
        # enqueue a background generation job and return 202 Accepted immediately
        # (the worker claims and runs it, appending the result to scratch). short
        # (1024) stays fully synchronous below. The pad is keyed per-draft, so an
        # async preset without current_position has nowhere to display → 400 (short
        # still allows a positionless request, as today). The endpoint does not
        # touch writing/context_search/scratch here — that is the worker's job, so
        # the sync-only 503 checks below are not consulted for async.
        if output_length in (OutputLength.MEDIUM, OutputLength.LONG):
            if body.current_position is None:
                raise HTTPException(
                    status_code=400,
                    detail="current_position is required for async presets "
                           "(output_length medium/long)",
                )
            # Slice 8.3 Q8=C (오너 2026-08-04): 202 로 잠금이 냉각으로 넘어간 뒤의
            # 재클릭은 **새 uuid → 새 job → 2회 과금**이 되는 가장 비싼 실수 중복이다.
            # 잠금과 같은 통로(429 + 확인 헤더)로 상태 축을 한 번 더 막는다 —
            # 새 저장소도 새 수명도 만들지 않고 이미 있는 조회 하나를 쓴다.
            if not quota_confirmed(request) and (
                writing_generation_jobs.has_other_active_for_draft(
                    project_id=project_id,
                    draft_id=body.current_position.draft_id,
                    request_id=body.request_id,
                )
            ):
                raise HTTPException(
                    status_code=429,
                    detail="a generation for this draft is still in progress; "
                           "confirm to start another",
                )
            result = writing_generation_jobs.enqueue(
                project_id=project_id,
                draft_id=body.current_position.draft_id,
                request_id=body.request_id,
                # Q1-b=A: 워커가 성공 시 원장에 쓰려면 이 job 이 누구 것인지 알아야
                # 한다. 요청 경로는 202 를 과금하지 않는다.
                user_id=quota_charge(request).user_id,
                task_type=task_type.value,
                instruction=body.instruction,
                draft_excerpt=body.draft_excerpt,
                query=body.query,
                output_length=output_length.value,
                max_output_tokens=output_tokens,
                max_tokens=body.max_tokens,
                version_id=body.current_position.version_id,
            )
            return JSONResponse(
                status_code=202,
                content={
                    "job": _writing_generation_job_payload(result.job),
                    "idempotent_replay": result.idempotent_replay,
                },
            )
        if writing is None:
            raise HTTPException(
                status_code=503, detail="writing service is not configured"
            )
        if context_search is None:
            raise HTTPException(
                status_code=503, detail="context search service is not configured"
            )
        position = (
            CurrentPosition(
                draft_id=body.current_position.draft_id,
                version_id=body.current_position.version_id,
            )
            if body.current_position is not None
            else None
        )
        search_request = ContextSearchRequest(
            project_id=project_id,
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            needs=_WRITING_CONTINUE_SCENE_NEEDS,
            query=body.query or body.instruction,
            current_position=position,
            # R-a: 생성은 이 패키지로 끝나지 않는다 — 같은 패키지가 곧바로 self-report에
            # 실리고 그쪽이 더 무겁다(출력 상한 6144 + 후보 산문). 후보는 아직 없지만
            # **상한은 출력 프리셋**이므로 그 값으로 창에 맞춰 줄인다.
            context_budget=ContextBudget(max_tokens=await derive_context_budget(
                requested_tokens=body.max_tokens,
                capabilities=model_capabilities,
                report_output_cap=report_output_cap,
                report_system_template=REPORT_SYSTEM_TEMPLATE,
                candidate_tokens_upper_bound=output_tokens,
            )),
        )
        # Observability seam C (증분 C): this one request makes up to three
        # provider calls under three different sites — the query planner, the
        # generation itself, and the self-report when a reporter is configured.
        with llm_call_scope(llm_call_audit, project_id=project_id,
                            correlation_id=body.request_id) as scope:
            try:
                package = await context_search.build_context_package(search_request)
                candidate = await writing.generate(
                    request=WritingRequest(
                        request_id=body.request_id,
                        project_id=project_id,
                        task_type=task_type,
                        instruction=body.instruction,
                        draft_excerpt=body.draft_excerpt,
                    ),
                    package=package,
                    max_output_tokens=output_tokens,
                )
            except WritingError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except InvalidCandidateReport as exc:
                # The reporter answered and its JSON was rejected — the report
                # call is the last one made, so this marks that row (D4).
                scope.reclassify_last_as_parse_error(type(exc).__name__)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            except InvalidContextSearchRequest as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except ContextSearchBudgetExceeded as exc:
                raise HTTPException(status_code=504, detail=str(exc)) from exc
            except ContextSearchFailed as exc:
                reclassify_planner_parse_error(scope, exc)
                raise HTTPException(
                    status_code=502,
                    detail=f"{exc.error_type.value}: {exc.detail}",
                ) from exc
            except ProviderError as exc:
                # 창 가드 거부만 4xx로 갈라진다(K-3, 오너 2026-07-30) — 상류 장애가 아니라
                # 요청이 창을 넘은 것이고, 같은 요청의 재시도는 반드시 같은 실패다.
                # **주의(기존 불일치, 이 슬라이스가 만든 것 아님)**: 이 endpoint는 TIMEOUT도
                # 502로 내는데 gate/revise/report는 504로 낸다. 그 정렬은 별도 판단이라
                # 여기서 바꾸지 않았다(추적 부채).
                if exc.code is ProviderErrorCode.CONTEXT_WINDOW_EXCEEDED:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
                raise HTTPException(status_code=502, detail=str(exc)) from exc
        # Safety net (brief D0=B): persist the just-generated candidate to the
        # recovery store so a refresh/navigation before accept doesn't lose it.
        # Keyed by the draft being continued; skipped when there's no draft key.
        # Best-effort — a scratch failure must never fail generation.
        if body.current_position is not None:
            try:
                writing_scratch.save(
                    project_id=project_id,
                    draft_id=body.current_position.draft_id,
                    request_id=body.request_id,
                    task_type=candidate.task_type.value,
                    output_type=candidate.output_type.value,
                    instruction=body.instruction,
                    candidate_text=candidate.text,
                    version_id=body.current_position.version_id,
                )
            except Exception:  # noqa: BLE001 — safety net never blocks generate
                pass
        return _writing_candidate_payload(candidate)

    @app.get("/projects/{project_id}/writing/generation-jobs/{job_id}",
             response_model=WritingGenerationJobPayload,
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def get_writing_generation_job(
        project_id: str, job_id: str,
    ) -> dict[str, object]:
        # 증분 2c (D5=A): status read for an async generation job — the pad (증분 3)
        # polls this to learn when a medium/long generation finishes, then re-reads
        # the scratch list to display the result. 404 covers both "no such job" and
        # "job exists but belongs to another project" (project-scoped isolation).
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        job = writing_generation_jobs.get(job_id)
        if job is None or job.project_id != project_id:
            raise HTTPException(
                status_code=404, detail="generation job not found"
            )
        return _writing_generation_job_payload(job)

    @app.get("/projects/{project_id}/writing/budget",
             response_model=WritingContextBudgetPayload,
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def get_writing_context_budget(project_id: str) -> dict[str, object]:
        # K-4 (프론트 글자수 표시·경고): R-a 유도 예산을 프론트에 노출해 카운터의 경고 기준을
        # 정확히 맞춘다 — 고정 상수(8192)는 R-a 이후 실제 예산(베타 ≈5407)과 어긋나 경고를
        # 거짓으로 만든다. 출력 프리셋마다 derive(후보 상한 = 해당 프리셋 출력 상한).
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        presets = _writing_output_length_tokens()

        async def _derive(upper_bound: int) -> int:
            return await derive_context_budget(
                requested_tokens=DEFAULT_CONTEXT_BUDGET_TOKENS,
                capabilities=model_capabilities,
                report_output_cap=report_output_cap,
                report_system_template=REPORT_SYSTEM_TEMPLATE,
                candidate_tokens_upper_bound=upper_bound,
            )

        return {
            "project_id": project_id,
            "context_budget_tokens": {
                "short": await _derive(presets[OutputLength.SHORT]),
                "medium": await _derive(presets[OutputLength.MEDIUM]),
                "long": await _derive(presets[OutputLength.LONG]),
            },
        }

    @app.post("/projects/{project_id}/writing/generation-jobs/{job_id}/retry",
              response_model=WritingGenerationJobPayload,
              responses=_owned(_ERRORS_404_409),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def retry_writing_generation_job(
        project_id: str, job_id: str,
    ) -> dict[str, object]:
        # Retry slice (async-pad D4=A): reset one FAILED generation job to PENDING
        # so the worker re-claims and re-runs it. Mirrors the Analysis retry
        # endpoint (failed→pending, others 409). No separate run call: the
        # generation worker's claim loop picks up any PENDING job on its own.
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        job = writing_generation_jobs.get(job_id)
        if job is None or job.project_id != project_id:
            raise HTTPException(
                status_code=404, detail="generation job not found"
            )
        try:
            job = writing_generation_jobs.mark_pending_for_retry(job)
        except InvalidGenerationJobStateTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _writing_generation_job_payload(job)

    @app.post("/projects/{project_id}/writing/gate",
              response_model=WritingGatePayload,
              responses=_owned(_BILLABLE_400_404_502_504_CONFIG),
              dependencies=_REQUIRE_PROJECT_OWNER_BILLABLE)
    async def writing_gate_endpoint(
        project_id: str, body: WritingGateRequest
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            task_type = WritingTaskType(body.task_type)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"unsupported task_type: {body.task_type}"
            ) from exc
        if writing_gate is None:
            raise HTTPException(
                status_code=503, detail="writing gate service is not configured"
            )
        if context_search is None:
            raise HTTPException(
                status_code=503, detail="context search service is not configured"
            )
        position = (
            CurrentPosition(draft_id=body.current_position.draft_id,
                            version_id=body.current_position.version_id)
            if body.current_position is not None else None
        )
        search_request = ContextSearchRequest(
            project_id=project_id,
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            needs=_WRITING_CONTINUE_SCENE_NEEDS,
            query=body.query or body.instruction,
            current_position=position,
            context_budget=ContextBudget(max_tokens=body.max_tokens),
        )
        request = WritingRequest(
            request_id=body.request_id, project_id=project_id,
            task_type=task_type, instruction=body.instruction,
            draft_excerpt=body.draft_excerpt,
        )
        candidate = WritingCandidate(
            request_id=body.request_id, project_id=project_id,
            task_type=task_type, output_type=WritingOutputType.DRAFT_PATCH,
            text=body.candidate_text,
        )

        # Observability seam C: the gate's provider is wrapped, so the record —
        # model, tokens, latency, provider failures — comes from the call itself.
        # This scope only has to supply what the provider cannot know: which
        # workflow the call belongs to, and the domain verdicts annotated below.
        # Pre-call rejections (bad task_type, invalid search request, context
        # budget, context-search failure) leave no record without any special
        # handling: no provider call means nothing to record.
        with llm_call_scope(llm_call_audit, project_id=project_id,
                            correlation_id=body.request_id) as scope:
            try:
                package = await context_search.build_context_package(search_request)
            except InvalidContextSearchRequest as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except ContextSearchBudgetExceeded as exc:
                raise HTTPException(status_code=504, detail=str(exc)) from exc
            except ContextSearchFailed as exc:
                reclassify_planner_parse_error(scope, exc)
                raise HTTPException(
                    status_code=502,
                    detail=f"{exc.error_type.value}: {exc.detail}",
                ) from exc
            try:
                result = await writing_gate.evaluate(
                    request=request, candidate=candidate, package=package)
            except InvalidWritingGateResult as exc:
                # The provider answered and domain parsing rejected it — a
                # verdict the provider layer cannot reach on its own, so the
                # success it recorded is corrected here before the flush.
                scope.reclassify_last_as_parse_error(type(exc).__name__)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            except WritingGateError as exc:
                # Input validation and an unavailable prompt template, both
                # raised before the provider is called — so no record.
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except ProviderError as exc:
                # Already recorded by the decorator, with its taxonomy intact.
                status = _provider_error_status(exc)
                raise HTTPException(status_code=status, detail=str(exc)) from exc
            scope.annotate_last(decision=result.decision.value,
                                gate_quality_score=gate_quality_score(result))
        return _writing_gate_payload(result)

    @app.post("/projects/{project_id}/writing/report",
              responses=_owned(_BILLABLE_400_404_502_504_CONFIG),
              dependencies=_REQUIRE_PROJECT_OWNER_BILLABLE)
    async def writing_report_endpoint(
        project_id: str, body: WritingReportRequest
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            task_type = WritingTaskType(body.task_type)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"unsupported task_type: {body.task_type}"
            ) from exc
        if not body.request_id.strip():
            raise HTTPException(status_code=400, detail="request_id must not be empty")
        if not body.instruction.strip():
            raise HTTPException(status_code=400, detail="instruction must not be empty")
        if not body.candidate_text.strip():
            raise HTTPException(status_code=400, detail="candidate_text must not be empty")
        if writing_report is None:
            raise HTTPException(
                status_code=503, detail="writing report service is not configured"
            )
        if context_search is None:
            raise HTTPException(
                status_code=503, detail="context search service is not configured"
            )
        position = (
            CurrentPosition(
                draft_id=body.current_position.draft_id,
                version_id=body.current_position.version_id,
            )
            if body.current_position is not None
            else None
        )
        search_request = ContextSearchRequest(
            project_id=project_id,
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            needs=_WRITING_CONTINUE_SCENE_NEEDS,
            query=body.query or body.instruction,
            current_position=position,
            # R-a: 여기서는 후보가 **이미 있으므로** 상한이 아니라 그 산문을 직접 센다.
            context_budget=ContextBudget(max_tokens=await derive_context_budget(
                requested_tokens=body.max_tokens,
                capabilities=model_capabilities,
                report_output_cap=report_output_cap,
                report_system_template=REPORT_SYSTEM_TEMPLATE,
                candidate_tokens_upper_bound=candidate_tokens_from_text(
                    body.candidate_text),
            )),
        )
        candidate = WritingCandidate(
            request_id=body.request_id,
            project_id=project_id,
            task_type=task_type,
            output_type=WritingOutputType.DRAFT_PATCH,
            text=body.candidate_text,
        )
        # Observability seam C (증분 C): planner call(s) then the report call.
        with llm_call_scope(llm_call_audit, project_id=project_id,
                            correlation_id=body.request_id) as scope:
            try:
                package = await context_search.build_context_package(search_request)
                enriched = await writing_report.enrich(candidate, package)
            except InvalidContextSearchRequest as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except InvalidCandidateReport as exc:
                scope.reclassify_last_as_parse_error(type(exc).__name__)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            except ContextSearchBudgetExceeded as exc:
                raise HTTPException(status_code=504, detail=str(exc)) from exc
            except ContextSearchFailed as exc:
                reclassify_planner_parse_error(scope, exc)
                raise HTTPException(
                    status_code=502,
                    detail=f"{exc.error_type.value}: {exc.detail}",
                ) from exc
            except ProviderError as exc:
                status = _provider_error_status(exc)
                raise HTTPException(status_code=status, detail=str(exc)) from exc
        return _writing_candidate_payload(enriched)

    @app.post("/projects/{project_id}/writing/revise",
              responses=_owned(_BILLABLE_400_404_502_504_CONFIG),
              dependencies=_REQUIRE_PROJECT_OWNER_BILLABLE)
    async def writing_revise_endpoint(
        project_id: str, body: WritingReviseRequest
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            task_type = WritingTaskType(body.task_type)
            finding = WritingGateFinding(
                finding_type=WritingGateFindingType(body.finding.type),
                severity=WritingGateSeverity(body.finding.severity),
                message=body.finding.message,
                evidence=body.finding.evidence,
                recommended_decision=WritingGateDecision(
                    body.finding.recommended_decision
                ),
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if writing_revision is None:
            raise HTTPException(
                status_code=503, detail="writing revision service is not configured"
            )
        if context_search is None:
            raise HTTPException(
                status_code=503, detail="context search service is not configured"
            )
        position = (
            CurrentPosition(
                draft_id=body.current_position.draft_id,
                version_id=body.current_position.version_id,
            )
            if body.current_position is not None
            else None
        )
        search_request = ContextSearchRequest(
            project_id=project_id,
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            needs=_WRITING_CONTINUE_SCENE_NEEDS,
            query=body.query or body.instruction,
            current_position=position,
            context_budget=ContextBudget(max_tokens=body.max_tokens),
        )
        candidate = WritingCandidate(
            request_id=body.request_id,
            project_id=project_id,
            task_type=task_type,
            output_type=WritingOutputType.DRAFT_PATCH,
            text=body.candidate_text,
        )
        # Observability seam C (증분 C): planner call(s) then the revision call.
        with llm_call_scope(llm_call_audit, project_id=project_id,
                            correlation_id=body.request_id) as scope:
            try:
                # Validate cheap deterministic boundaries before context search so
                # invalid requests never spend a planner round-trip.
                writing_revision.validate_inputs(candidate, finding, body.instruction)
                package = await context_search.build_context_package(search_request)
                revised = await writing_revision.revise(
                    candidate=candidate,
                    finding=finding,
                    instruction=body.instruction,
                    package=package,
                )
            except (WritingRevisionError, InvalidContextSearchRequest) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except InvalidWritingRevision as exc:
                scope.reclassify_last_as_parse_error(type(exc).__name__)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            except ContextSearchBudgetExceeded as exc:
                raise HTTPException(status_code=504, detail=str(exc)) from exc
            except ContextSearchFailed as exc:
                reclassify_planner_parse_error(scope, exc)
                raise HTTPException(
                    status_code=502,
                    detail=f"{exc.error_type.value}: {exc.detail}",
                ) from exc
            except ProviderError as exc:
                status = _provider_error_status(exc)
                raise HTTPException(status_code=status, detail=str(exc)) from exc
        return _writing_candidate_payload(revised)

    @app.post("/projects/{project_id}/writing/revise-and-gate",
              response_model=WritingReviseGateResponse,
              responses=_owned(_billable(REVISE_AND_GATE_RESPONSES)),
              dependencies=_REQUIRE_PROJECT_OWNER_BILLABLE)
    async def writing_revise_and_gate_endpoint(
        project_id: str, body: WritingReviseRequest
    ) -> object:
        try:
            _require_project_exists(project_id)
            task_type = WritingTaskType(body.task_type)
            finding = WritingGateFinding(
                finding_type=WritingGateFindingType(body.finding.type),
                severity=WritingGateSeverity(body.finding.severity),
                message=body.finding.message,
                evidence=body.finding.evidence,
                recommended_decision=WritingGateDecision(
                    body.finding.recommended_decision
                ),
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if writing_revise_gate is None:
            raise HTTPException(
                status_code=503,
                detail="writing revise-and-gate service is not configured",
            )
        if context_search is None:
            raise HTTPException(
                status_code=503, detail="context search service is not configured"
            )
        position = (
            CurrentPosition(
                draft_id=body.current_position.draft_id,
                version_id=body.current_position.version_id,
            )
            if body.current_position is not None
            else None
        )
        search_request = ContextSearchRequest(
            project_id=project_id,
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            needs=_WRITING_CONTINUE_SCENE_NEEDS,
            query=body.query or body.instruction,
            current_position=position,
            # R-a(오너 2026-07-31, v1.7.66): 후보가 이미 있고 루프의 report 다리(출력 상한
            # 6144 + 후보 산문)가 창을 구속하므로 report 엔드포인트와 같이 창에서 유도한다.
            # **진입 시 1회**만 유도한다 — 루프는 이 값을 (a) 패키지 예산과 (b) merge 상한의
            # 양쪽에 그대로 쓰므로, merge_context_packages가 패키지를 이 값으로 묶어
            # retrieve_more가 유도값 너머로 패키지를 키우지 못하게 한다. 후보는 revise로
            # partial patch될 뿐 유의하게 자라지 않고, 남는 초과는 K-3 가드가 받는다.
            context_budget=ContextBudget(max_tokens=await derive_context_budget(
                requested_tokens=body.max_tokens,
                capabilities=model_capabilities,
                report_output_cap=report_output_cap,
                report_system_template=REPORT_SYSTEM_TEMPLATE,
                candidate_tokens_upper_bound=candidate_tokens_from_text(
                    body.candidate_text),
            )),
        )
        request = WritingRequest(
            request_id=body.request_id,
            project_id=project_id,
            task_type=task_type,
            instruction=body.instruction,
        )
        candidate = WritingCandidate(
            request_id=body.request_id,
            project_id=project_id,
            task_type=task_type,
            output_type=WritingOutputType.DRAFT_PATCH,
            text=body.candidate_text,
        )

        persist_audit = (
            body.persist_audit if body.persist_audit is not None
            else _env_bool("WRITING_LOOP_AUDIT_DEFAULT", False)
        )

        def _record_loop_audit(*, summary, stages, final_candidate, gate,
                               error_type) -> tuple[str | None, dict | None]:
            # Phase 5.9 L9 B (P2=B opt-in): audit this loop termination only when
            # persist_audit is on. Only outcomes that produced a WritingLoopSummary
            # are loop runs; pre-loop request rejections (400/502/504) are never
            # audited. The persist is isolated from the loop critical path — a write
            # failure returns the loop result with audit_id=null + audit_error, it
            # never breaks the loop outcome (folds the prior H3 question).
            if not persist_audit:
                return None, None
            try:
                run_id = writing_loop_audit.record(
                    project_id=project_id, request_id=body.request_id,
                    trigger_finding=finding,
                    initial_candidate_text=body.candidate_text,
                    summary=summary, stages=stages,
                    final_candidate=final_candidate, gate=gate,
                    error_type=error_type,
                ).id
                return run_id, None
            except Exception as exc:  # noqa: BLE001 — deliberate isolation boundary
                return None, {"type": "audit_persist_error", "detail": str(exc)}

        # Observability seam C (증분 C): the loop's calls all land here —
        # planner, reviser, self-report and gate, once per round. One
        # correlation_id per request is what makes "how many rounds did this
        # request cost" answerable at all.
        with llm_call_scope(llm_call_audit, project_id=project_id,
                            correlation_id=body.request_id) as scope:
            try:
                writing_revision.validate_inputs(candidate, finding, body.instruction)
                package = await context_search.build_context_package(search_request)
                result = await writing_revise_gate.run(
                    request=request,
                    candidate=candidate,
                    finding=finding,
                    package=package,
                    current_position=position,
                    context_budget=search_request.context_budget,
                )
            except (WritingRevisionError, InvalidContextSearchRequest) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except InvalidWritingRevision as exc:
                scope.reclassify_last_as_parse_error(type(exc).__name__)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            except ContextSearchBudgetExceeded as exc:
                raise HTTPException(status_code=504, detail=str(exc)) from exc
            except ContextSearchFailed as exc:
                reclassify_planner_parse_error(scope, exc)
                raise HTTPException(
                    status_code=502,
                    detail=f"{exc.error_type.value}: {exc.detail}",
                ) from exc
            except ProviderError as exc:
                status = _provider_error_status(exc)
                raise HTTPException(status_code=status, detail=str(exc)) from exc
            except WritingReviseReportFailure as exc:
                cause = exc.cause
                if isinstance(cause, ProviderError):
                    status = _provider_error_status(cause)
                    error_type = cause.code.value
                elif isinstance(cause, InvalidCandidateReport):
                    status, error_type = 502, "invalid_candidate_report"
                    scope.reclassify_last_as_parse_error(type(cause).__name__)
                else:
                    status, error_type = 502, "report_error"
                audit_id, audit_error = _record_loop_audit(
                    summary=exc.loop, stages=exc.stages,
                    final_candidate=exc.candidate, gate=exc.gate,
                    error_type=error_type,
                )
                return JSONResponse(
                    status_code=status,
                    content={
                        "candidate": _writing_candidate_payload(exc.candidate),
                        "gate": (
                            _writing_gate_payload(exc.gate)
                            if exc.gate is not None else None
                        ),
                        "loop": _writing_loop_payload(exc.loop),
                        "stages": _writing_stages_payload(exc.stages),
                        "audit_id": audit_id,
                        "audit_error": audit_error,
                        "report_error": {
                            "type": error_type,
                            "detail": str(cause),
                        },
                    },
                )
            except WritingLoopRevisionFailure as exc:
                cause = exc.cause
                if isinstance(cause, ProviderError):
                    status = _provider_error_status(cause)
                    error_type = cause.code.value
                elif isinstance(cause, WritingRevisionError):
                    status, error_type = 400, "writing_revision_error"
                elif isinstance(cause, InvalidWritingRevision):
                    status, error_type = 502, "invalid_writing_revision"
                    scope.reclassify_last_as_parse_error(type(cause).__name__)
                else:
                    status, error_type = 502, "revision_error"
                audit_id, audit_error = _record_loop_audit(
                    summary=exc.loop, stages=exc.stages,
                    final_candidate=exc.candidate, gate=exc.gate,
                    error_type=error_type,
                )
                return JSONResponse(
                    status_code=status,
                    content={
                        "candidate": _writing_candidate_payload(exc.candidate),
                        "gate": (
                            _writing_gate_payload(exc.gate)
                            if exc.gate is not None else None
                        ),
                        "loop": _writing_loop_payload(exc.loop),
                        "stages": _writing_stages_payload(exc.stages),
                        "audit_id": audit_id,
                        "audit_error": audit_error,
                        "revision_error": {
                            "type": error_type,
                            "detail": str(cause),
                        },
                    },
                )
            except WritingRetrievalFailure as exc:
                cause = exc.cause
                if isinstance(cause, ProviderError):
                    status = _provider_error_status(cause)
                    error_type = cause.code.value
                elif isinstance(cause, InvalidWritingRetrievalPlan):
                    status, error_type = 502, "invalid_retrieval_plan"
                    scope.reclassify_last_as_parse_error(type(cause).__name__)
                elif isinstance(cause, WritingRetrievalConfigurationError):
                    status, error_type = 503, "retrieval_not_configured"
                elif isinstance(cause, WritingRetrievalPlannerError):
                    status, error_type = 503, "retrieval_planner_error"
                elif isinstance(cause, InvalidContextSearchRequest):
                    status, error_type = 400, "invalid_context_request"
                elif isinstance(cause, ContextSearchBudgetExceeded):
                    status, error_type = 504, "context_budget_exceeded"
                elif isinstance(cause, ContextSearchFailed):
                    status, error_type = 502, cause.error_type.value
                    reclassify_planner_parse_error(scope, cause)
                else:
                    status, error_type = 502, "retrieval_error"
                audit_id, audit_error = _record_loop_audit(
                    summary=exc.loop, stages=exc.stages,
                    final_candidate=exc.candidate, gate=exc.gate,
                    error_type=error_type,
                )
                return JSONResponse(
                    status_code=status,
                    content={
                        "candidate": _writing_candidate_payload(exc.candidate),
                        "gate": _writing_gate_payload(exc.gate),
                        "loop": _writing_loop_payload(exc.loop),
                        "stages": _writing_stages_payload(exc.stages),
                        "audit_id": audit_id,
                        "audit_error": audit_error,
                        "retrieval_error": {
                            "type": error_type,
                            "detail": str(cause),
                        },
                    },
                )
            except WritingReviseGateFailure as exc:
                cause = exc.cause
                if isinstance(cause, ProviderError):
                    status = _provider_error_status(cause)
                    error_type = cause.code.value
                elif isinstance(cause, InvalidWritingGateResult):
                    status, error_type = 502, "invalid_gate_result"
                    scope.reclassify_last_as_parse_error(type(cause).__name__)
                elif isinstance(cause, WritingGateError):
                    status, error_type = 400, "writing_gate_error"
                else:
                    status, error_type = 502, "gate_error"
                audit_id, audit_error = _record_loop_audit(
                    summary=exc.loop, stages=exc.stages,
                    final_candidate=exc.candidate, gate=exc.gate,
                    error_type=error_type,
                )
                return JSONResponse(
                    status_code=status,
                    content={
                        "candidate": _writing_candidate_payload(exc.candidate),
                        "gate": (
                            _writing_gate_payload(exc.gate)
                            if exc.gate is not None else None
                        ),
                        "loop": _writing_loop_payload(exc.loop),
                        "stages": _writing_stages_payload(exc.stages),
                        "audit_id": audit_id,
                        "audit_error": audit_error,
                        "gate_error": {
                            "type": error_type,
                            "detail": str(cause),
                        },
                    },
                )
        audit_id, audit_error = _record_loop_audit(
            summary=result.loop, stages=result.stages,
            final_candidate=result.candidate, gate=result.gate,
            error_type=None,
        )
        return {
            "candidate": _writing_candidate_payload(result.candidate),
            "gate": (
                _writing_gate_payload(result.gate)
                if result.gate is not None else None
            ),
            "loop": _writing_loop_payload(result.loop),
            "stages": _writing_stages_payload(result.stages),
            "audit_id": audit_id,
            "audit_error": audit_error,
        }

    @app.get("/projects/{project_id}/writing/loop-audits",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def writing_loop_audits_endpoint(project_id: str) -> dict[str, object]:
        # Phase 5.9 L9 B: durable, append-only loop audit summaries, newest
        # first. Project-scoped; retained for later verification reference.
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        runs = writing_loop_audit.list_runs(project_id)
        return {
            "project_id": project_id,
            "items": [_writing_loop_audit_summary_payload(run) for run in runs],
        }

    @app.get("/projects/{project_id}/writing/loop-audits/{audit_id}",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def writing_loop_audit_detail_endpoint(
        project_id: str, audit_id: str
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            run = writing_loop_audit.get(project_id=project_id, run_id=audit_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except WritingLoopAuditNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _writing_loop_audit_payload(run)

    @app.post("/projects/{project_id}/writing/accept",
              response_model=WritingAcceptResponse,
              responses=_owned(_billable(ACCEPT_RESPONSES)),
              dependencies=_REQUIRE_PROJECT_OWNER_BILLABLE)
    async def writing_accept_endpoint(
        project_id: str, body: WritingAcceptRequest,
        current=Depends(require_authenticated_user),
    ) -> object:
        try:
            _require_project_exists(project_id)
            task_type = WritingTaskType(body.task_type)
            output_type = WritingOutputType(body.output_type)
            intent = WritingIntent(body.intent)
            next_unit = (
                NextUnit(
                    title=body.next_unit.title,
                    unit_kind=UnitKind(body.next_unit.unit_kind),
                    goal=body.next_unit.goal,
                )
                if body.next_unit is not None else None
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if writing_accept is None:
            raise HTTPException(status_code=503,
                                detail="writing accept service is not configured")
        if context_search is None:
            raise HTTPException(status_code=503,
                                detail="context search service is not configured")
        position = (CurrentPosition(
            draft_id=body.current_position.draft_id,
            version_id=body.current_position.version_id)
            if body.current_position is not None else None)
        search_request = ContextSearchRequest(
            project_id=project_id,
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            needs=_WRITING_CONTINUE_SCENE_NEEDS,
            query=body.query or body.instruction,
            current_position=position,
            # R-a(오너 2026-07-31, v1.7.66): accept도 report 다리를 지난다
            # (`WritingAcceptService.run` → `reporter.enrich`), 그래서 report 엔드포인트와
            # 같이 창에서 유도한다(후보 산문 추정을 후보 상한으로). 패턴 스윕으로 발견해
            # revise-and-gate 확장과 한 슬라이스로 담았다.
            context_budget=ContextBudget(max_tokens=await derive_context_budget(
                requested_tokens=body.max_tokens,
                capabilities=model_capabilities,
                report_output_cap=report_output_cap,
                report_system_template=REPORT_SYSTEM_TEMPLATE,
                candidate_tokens_upper_bound=candidate_tokens_from_text(
                    body.candidate_text),
            )),
        )
        request = WritingRequest(body.request_id, project_id, task_type,
                                 body.instruction, body.draft_excerpt,
                                 intent=intent, next_unit=next_unit)
        candidate = WritingCandidate(
            body.request_id, project_id, task_type, output_type,
            body.candidate_text, intent=intent, next_unit=next_unit)

        def _clear_scratch_for_saved_accept() -> None:
            # A *saved* accept means the canonical version now exists, so the
            # accepted candidate is no longer "unaccepted" and is retired from
            # scratch. Async-pad D2=A (SoT v1.7.25): remove ONLY the accepted
            # item (matching request_id), not the draft's whole history — other
            # generated candidates stay recoverable/copyable (the pad's reason to
            # exist). Called from BOTH saved outcomes — the clean 200 and the 502
            # partial where the version saved but the analysis job failed. A
            # non-PASS Gate result (accepted=false, nothing saved) must NOT clear:
            # the user still has a bounced draft worth recovering. Key on the same
            # draft generate used (current_position), falling back to the accept
            # target. No matching entry → no-op. Best-effort — never fails accept.
            cleanup_draft_id = (
                body.current_position.draft_id
                if body.current_position is not None else body.draft_id
            )
            try:
                writing_scratch.clear_accepted_item(
                    project_id, cleanup_draft_id, body.request_id)
            except Exception:  # noqa: BLE001 — cleanup never blocks accept
                pass

        # Observability seam C (증분 C): accept runs the planner and then the
        # gate (plus the reporter when the gate asks for a fresh report), so
        # its calls belong to the accept request, not to whatever earlier
        # request produced the candidate.
        with llm_call_scope(llm_call_audit, project_id=project_id,
                            correlation_id=body.request_id) as scope:
            try:
                package = await context_search.build_context_package(search_request)
                result = await writing_accept.accept(
                    draft_id=body.draft_id,
                    base_version_id=body.base_version_id,
                    idempotency_key=body.idempotency_key,
                    request=request, candidate=candidate, package=package)
            except (NotFound,) as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except (Archived, StaleWritingBase) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except DraftOrderIntegrityError as exc:
                # H3 S5: closes the 500 leak SoT v1.7.29 recorded as a known defect.
                # intent=start_next_unit reaches core_sot.start_next_unit →
                # _require_ordered_drafts, which raises this on drafts predating the W3
                # ordered-unit invariant. No clause here caught it, so it escaped as an
                # opaque 500. Same mapping and rationale as the CRUD siblings (503, fix
                # is scripts/migrate_ordered_units.py — not a corrected request).
                #
                # Order matters: this must precede the WritingAcceptError clause below.
                # It is not a subclass today, but the 400 group is the broad
                # "bad request" bucket and putting the integrity face after it invites a
                # future re-parent to silently reclassify a server-side data problem as
                # the caller's fault. The over-strict regression pins 503, not 400.
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except (WritingAcceptError, WritingGateError,
                    InvalidContextSearchRequest) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except InvalidWritingGateResult as exc:
                scope.reclassify_last_as_parse_error(type(exc).__name__)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            except WritingAcceptAnalysisError as exc:
                # The version WAS saved here (only the analysis job failed), so the
                # canonical draft exists and the scratch history is moot — same
                # rationale as the clean success path below.
                _clear_scratch_for_saved_accept()
                # ★ 상태코드가 아니라 **정본이 바뀌었는가**로 기록한다(A7=A). 이
                # 경로는 version 이 저장된 뒤 분석 job 만 실패한 자리이므로, 여기서
                # 안 남기면 타임라인이 실제로 일어난 저장을 빠뜨린다.
                activity.record(
                    project_id=project_id, actor_user_id=current.id,
                    action="draft_version_accepted", target_type="draft_version",
                    target_id=exc.saved.draft_version.id,
                    after=str(exc.saved.draft_version.version_number),
                )
                return JSONResponse(status_code=502, content={
                    "accepted": True,
                    "intent": exc.intent.value,
                    "saved": _accepted_save_payload(exc.saved, exc.target_draft),
                    "analysis_job": None,
                    "analysis_error": str(exc),
                })
            except ContextSearchBudgetExceeded as exc:
                raise HTTPException(status_code=504, detail=str(exc)) from exc
            except ContextSearchFailed as exc:
                reclassify_planner_parse_error(scope, exc)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            except ProviderError as exc:
                status = _provider_error_status(exc)
                raise HTTPException(status_code=status, detail=str(exc)) from exc
        if result.accepted:
            _clear_scratch_for_saved_accept()
        # A2 확장(오너 2026-08-09): accept 는 **정본 draft version 을 저장한다** —
        # 브리프 §0.2 가 성격으로 "AI·작업 요청"에 넣었지만 A2 의 기준은 "무엇을
        # 바꿨는가"이고, 여기가 주 저작 흐름의 저장 경로다. **기록하는 것은 AI 요청이
        # 아니라 정본 저장**이므로 A8(중복 없음)은 그대로다 — `llm_call_audits`·원장이
        # 담는 사건과 다른 사실이다. Gate 가 통과하지 않으면 저장이 없고 기록도 없다.
        if result.saved is not None:
            activity.record(
                project_id=project_id, actor_user_id=current.id,
                action="draft_version_accepted", target_type="draft_version",
                target_id=result.saved.draft_version.id,
                after=str(result.saved.draft_version.version_number),
            )
        return {
            "accepted": result.accepted,
            "intent": result.intent.value,
            "gate": (_writing_gate_payload(result.gate)
                     if result.gate is not None else None),
            "saved": (_accepted_save_payload(result.saved, result.target_draft)
                      if result.saved is not None else None),
            "analysis_job": (_analysis_job_payload(result.analysis_job)
                             if result.analysis_job is not None else None),
            "idempotent_replay": result.idempotent_replay,
        }

    def _writing_scratch_payload(entry) -> dict[str, object]:
        return {
            "id": entry.id,
            "draft_id": entry.draft_id,
            "request_id": entry.request_id,
            "task_type": entry.task_type,
            "output_type": entry.output_type,
            "instruction": entry.instruction,
            "candidate_text": entry.candidate_text,
            "intent": entry.intent,
            "version_id": entry.version_id,
            "created_at": entry.created_at.isoformat(),
        }

    @app.get("/projects/{project_id}/writing/scratch", responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def writing_scratch_list_endpoint(
        project_id: str, draft_id: str
    ) -> dict[str, object]:
        # Recovery surface (brief D1=B): unaccepted candidates for a draft,
        # newest first, so the editor can offer to restore an in-progress draft.
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        entries = writing_scratch.list_for_draft(project_id, draft_id)
        return {
            "project_id": project_id,
            "draft_id": draft_id,
            "items": [_writing_scratch_payload(e) for e in entries],
        }

    @app.delete("/projects/{project_id}/writing/scratch", responses=_owned(_ERRORS_404),
                dependencies=_REQUIRE_PROJECT_OWNER)
    async def writing_scratch_discard_endpoint(
        project_id: str, draft_id: str
    ) -> dict[str, object]:
        # Explicit "버리기": drop the draft's unaccepted scratch history.
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        deleted = writing_scratch.clear_draft(project_id, draft_id)
        return {
            "project_id": project_id,
            "draft_id": draft_id,
            "deleted": deleted,
        }
