"""분석 도메인 route (``/projects/{project_id}/analysis*`` 21 operation).

``main.py`` 의 ``create_app()`` 에서 옮겨온 register 함수(R1). handler 본문은
byte-동일이다.

**유료 2경로** 가 섞여 있다 — ``run`` · ``compare`` 가
``_REQUIRE_PROJECT_OWNER_BILLABLE`` (소유권 → 시행 순서) 이고 나머지 19경로는
``_REQUIRE_PROJECT_OWNER`` 다. 그 순서가 곧 "404·403 은 무과금" 이며
``BillableRouteWiringTest`` 가 route 선언에서 직접 잰다(요청 구동 테스트로는
안 보이는 자리다).

``_analysis_job_payload`` 만 ``..api.payloads`` 에서 온다(writing 의 accept 와
공유 — 라우터 분해 3차에서 내림). 나머지 직렬화기 13종·헬퍼 1종
(``_transition_gate_finding``) 은 이 도메인 전용이라 여기 있다.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse

from services.application.app.analysis.apply import MemoryApplyError, MissingMatchedMemory
from services.application.app.analysis.compare import (
    ActionProposal,
    CompareAction,
    CompareJudgeNotConfigured,
    InvalidJudgeResult,
)
from services.application.app.analysis.extractor import AnalysisExtractionError
from services.application.app.analysis.models import (
    AnalysisCandidateStatus,
    AnalysisJobStatus,
)
from services.application.app.analysis.reconciliation import ReconciliationAction
from services.application.app.analysis.repository import DuplicateAnalysisCandidateRequest
from services.application.app.analysis.review_inbox import (
    ReviewInboxNotFound,
    candidate_affordances,
    conflict_affordances,
    gate_finding_affordances,
)
from services.application.app.analysis.runner import AnalysisExtractionRunResult
from services.application.app.analysis.service import (
    AnalysisNotFound,
    InvalidAnalysisCandidate,
    InvalidCandidateSource,
    InvalidCandidateStateTransition,
    InvalidJobStateTransition,
)
from services.application.app.context_search.gate_findings import (
    GateFindingNotFound,
    GateFindingStatus,
    InvalidGateFindingTransition,
)
from services.application.app.context_search.models import AnalysisContextRequest, ContextNeed
from services.application.app.context_search.prior_memory import evaluate_analysis_context_gate
from services.application.app.core_sot.service import NotFound
from services.application.app.memory.models import PromotionMode
from services.application.app.memory.service import (
    MemoryError,
    MemoryNotFound,
    MemoryReindexEnqueueFailed,
)
from services.application.app.observability.llm_call_scope import llm_call_scope
from services.llm_gateway.app.errors import ProviderError

from ..api.dependencies import (
    _REQUIRE_PROJECT_OWNER,
    _REQUIRE_PROJECT_OWNER_BILLABLE,
    project_existence_check,
    require_authenticated_user,
)
from ..api.errors import (
    _BILLABLE_400_404_409_502_CONFIG,
    _BILLABLE_404_502_CONFIG,
    _ERRORS_400_404,
    _ERRORS_400_404_409,
    _ERRORS_404,
    _ERRORS_404_409,
    _ERRORS_404_STORAGE,
    _STORAGE_ERRORS,
    _owned,
    _provider_error_status,
)
from ..api.models import (
    ApplyMemoryRequest,
    CreateAnalysisJobRequest,
    EditCandidateRequest,
    ReconcileCharacterRequest,
)
from ..api.payloads import _analysis_job_payload, _memory_payload, _scope_payload


def register_analysis(
    app,
    *,
    core_sot,
    analysis,
    memory,
    runner,
    analysis_context,
    compare,
    apply_service,
    review_queue,
    character_reconciliation,
    review_inbox,
    gate_findings,
    llm_call_audit,
    candidate_review,
    activity,
) -> None:
    def _analysis_candidate_payload(candidate) -> dict[str, object]:
        return {
            "id": candidate.id,
            "project_id": candidate.project_id,
            "job_id": candidate.job_id,
            "task_id": candidate.task_id,
            "candidate_type": str(candidate.candidate_type),
            "action": str(candidate.action),
            "status": str(candidate.status),
            "provenance": str(candidate.provenance),
            "confidence": candidate.confidence,
            "source_ref_ids": list(candidate.source_ref_ids),
            "payload": dict(candidate.payload),
        }

    def _analysis_run_payload(
        result: AnalysisExtractionRunResult,
    ) -> dict[str, object]:
        return {
            "job": _analysis_job_payload(result.job),
            "candidates": [
                _analysis_candidate_payload(candidate)
                for candidate in result.candidates
            ],
            "idempotent_replay": result.job_idempotent_replay,
        }

    _require_project_exists = project_existence_check(core_sot)

    @app.post("/projects/{project_id}/analysis/jobs", responses=_owned(_ERRORS_404),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def create_analysis_job(
        project_id: str, request: CreateAnalysisJobRequest
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            result = analysis.create_job(
                project_id=project_id,
                snapshot_id=request.snapshot_id,
                idempotency_key=request.idempotency_key,
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "job": _analysis_job_payload(result.job),
            "idempotent_replay": result.idempotent_replay,
        }

    @app.get("/projects/{project_id}/analysis/jobs/{job_id}",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def get_analysis_job(project_id: str, job_id: str) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            job = analysis.get_job(project_id=project_id, job_id=job_id)
        except (AnalysisNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _analysis_job_payload(job)

    @app.get("/projects/{project_id}/analysis/jobs/{job_id}/candidates",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def list_analysis_candidates(
        project_id: str, job_id: str
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            candidates = analysis.list_candidates(project_id=project_id, job_id=job_id)
        except (AnalysisNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "candidates": [
                _analysis_candidate_payload(candidate) for candidate in candidates
            ]
        }

    @app.post("/projects/{project_id}/analysis/jobs/{job_id}/retry",
              responses=_owned(_ERRORS_404_409),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def retry_analysis_job(project_id: str, job_id: str) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            job = analysis.retry_failed_job(project_id=project_id, job_id=job_id)
        except (AnalysisNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidJobStateTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _analysis_job_payload(job)

    @app.post("/projects/{project_id}/analysis/jobs/{job_id}/run",
              responses=_owned(_BILLABLE_400_404_409_502_CONFIG),
              dependencies=_REQUIRE_PROJECT_OWNER_BILLABLE)
    async def run_analysis_job(project_id: str, job_id: str) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            job = analysis.get_job(project_id=project_id, job_id=job_id)
            if job.status is not AnalysisJobStatus.PENDING:
                candidates = analysis.list_candidates(
                    project_id=project_id, job_id=job_id
                )
                return _analysis_run_payload(
                    AnalysisExtractionRunResult(
                        job=job,
                        candidates=candidates,
                        job_idempotent_replay=True,
                        candidate_idempotent_replays=tuple(True for _ in candidates),
                    )
                )
            if runner is None:
                raise HTTPException(
                    status_code=503,
                    detail="analysis runner is not configured",
                )
            # Observability seam C: the extractor's provider is wrapped, so the
            # repair retry (extractor.py `_repair_once`) lands as its own record
            # instead of hiding behind this one endpoint call. correlation_id is
            # the job — every call made while running it belongs together.
            with llm_call_scope(llm_call_audit, project_id=project_id,
                                correlation_id=job_id):
                result = await runner.run_job(
                    project_id=project_id,
                    job_id=job_id,
                )
        except (AnalysisNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DuplicateAnalysisCandidateRequest as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (
            AnalysisExtractionError,
            InvalidCandidateSource,
            InvalidAnalysisCandidate,
        ) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ProviderError as exc:
            # A Gateway/provider failure (timeout/unavailable/5xx) re-raised by
            # the runner after it marks the job failed(provider_error) is an LLM
            # error → 502, mirroring the compare endpoint's explicit branch. The
            # generic catch below also maps to 502; this explicit branch keeps
            # the intent legible and refactor-safe. (It must precede the generic
            # ``except Exception`` catch; the 400/404/409 mappings above are for
            # unrelated types, so their order is unaffected.)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except _STORAGE_ERRORS as exc:
            # SoT v1.7.40 D2=A (owner decision 2026-07-24): a canonical store
            # failure — from the project-exists gate, get_job, list_candidates, or
            # a store write inside the runner — is not an upstream/LLM failure, so
            # it is the store face of 503, not the 502 the generic catch below
            # assigns. The 503 declaration already names this face (``_CONFIG_503``
            # is wrapped with ``_with_storage_note``), so the declaration is
            # unchanged; this branch is what makes the runtime match it and closes
            # the precision gap v1.7.39 had to record as a pre-existing exception.
            # It must precede the generic ``except Exception`` so the store failure
            # is not swallowed into 502.
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return _analysis_run_payload(result)

    @app.post(
        "/projects/{project_id}/analysis/candidates/{candidate_id}/promote",
        responses=_owned(_ERRORS_404),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def promote_candidate(
        project_id: str, candidate_id: str,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            candidate = analysis.get_candidate(
                project_id=project_id, candidate_id=candidate_id
            )
            result = memory.promote_candidate(
                project_id=project_id,
                candidate=candidate,
                mode=PromotionMode.MANUAL,
            )
        except (AnalysisNotFound, MemoryNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        # A2=B: 원고가 아니라 **기억**을 바꾼 사용자 판단. memory 는 append-only 라
        # 잘못 승격해도 과거가 남으므로, 되돌리기 가장 어려운 종류다.
        activity.record(
            project_id=project_id, actor_user_id=current.id,
            action="candidate_promoted", target_type="candidate",
            target_id=candidate_id,
        )
        return {
            "memory": _memory_payload(result.memory),
            "idempotent_replay": result.idempotent_replay,
        }

    def _candidate_review_payload(result) -> dict[str, object]:
        return {
            "candidate_id": result.candidate_id,
            "status": str(result.status),
            "memory_id": result.memory_id,
            "idempotent_replay": result.idempotent_replay,
        }

    def _candidate_edit_payload(result) -> dict[str, object]:
        return {
            "original_candidate_id": result.original_candidate_id,
            "candidate_id": result.candidate_id,
            "status": str(result.status),
            "memory_id": result.memory_id,
            "idempotent_replay": result.idempotent_replay,
        }

    @app.post(
        "/projects/{project_id}/analysis/candidates/{candidate_id}/confirm",
        responses=_owned(_ERRORS_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def confirm_candidate(
        project_id: str, candidate_id: str,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        # Phase 6 (v1.6.61): approve → confirmed + promotion + de-index + resolve.
        try:
            _require_project_exists(project_id)
            result = candidate_review.confirm(
                project_id=project_id, candidate_id=candidate_id
            )
        except (AnalysisNotFound, MemoryNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidCandidateStateTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        activity.record(
            project_id=project_id, actor_user_id=current.id,
            action="candidate_confirmed", target_type="candidate",
            target_id=candidate_id, after=str(result.status),
        )
        return _candidate_review_payload(result)

    @app.post(
        "/projects/{project_id}/analysis/candidates/{candidate_id}/reject",
        responses=_owned(_ERRORS_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def reject_candidate(
        project_id: str, candidate_id: str,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        # Phase 6 (v1.6.61): reject → rejected (no promotion) + de-index + dismiss.
        try:
            _require_project_exists(project_id)
            result = candidate_review.reject(
                project_id=project_id, candidate_id=candidate_id
            )
        except (AnalysisNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidCandidateStateTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        activity.record(
            project_id=project_id, actor_user_id=current.id,
            action="candidate_rejected", target_type="candidate",
            target_id=candidate_id, after=str(result.status),
        )
        return _candidate_review_payload(result)

    @app.post(
        "/projects/{project_id}/analysis/candidates/{candidate_id}/edit",
        responses=_owned(_ERRORS_400_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def edit_candidate(
        project_id: str, candidate_id: str, body: EditCandidateRequest,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        # Phase 6 (v1.6.66): edit → new confirmed candidate version + promotion +
        # de-index of the superseded original + resolve. The edited payload is
        # revalidated against the candidate_type schema (invalid → 400); editing a
        # non-needs_review candidate is a 409.
        try:
            _require_project_exists(project_id)
            result = candidate_review.edit(
                project_id=project_id,
                candidate_id=candidate_id,
                payload=body.payload,
            )
        except (AnalysisNotFound, MemoryNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidCandidateStateTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvalidAnalysisCandidate as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        activity.record(
            project_id=project_id, actor_user_id=current.id,
            action="candidate_edited", target_type="candidate",
            target_id=candidate_id,
        )
        return _candidate_edit_payload(result)

    @app.post("/projects/{project_id}/analysis/jobs/{job_id}/auto-promote",
              responses=_owned(_ERRORS_404_STORAGE),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def auto_promote_job(
        project_id: str, job_id: str,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            candidates = analysis.list_candidates(
                project_id=project_id, job_id=job_id
            )
        except (AnalysisNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        # ``promoted`` reports only memories newly created by this call. A
        # candidate already promoted (a re-run of the gate) replays idempotently
        # and is excluded, so the count stays consistent with the idempotency
        # semantics instead of growing on every re-call.
        promoted = []
        for candidate in candidates:
            if candidate.status is not AnalysisCandidateStatus.NEEDS_REVIEW:
                continue
            try:
                result = memory.auto_promote_candidate(
                    project_id=project_id, candidate=candidate
                )
            except MemoryNotFound as exc:
                # SoT v1.7.35 D3. Defensive: promote_candidate raises this on a
                # project mismatch, which cannot happen here because `candidates`
                # came from list_candidates(project_id=...). Mapped anyway so the
                # branch cannot leak a 500, and mapped to 404 like the sibling
                # manual promote endpoint. It precedes any write for this
                # candidate, so no mint of this iteration is lost.
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except MemoryReindexEnqueueFailed as exc:
                # SoT v1.7.36. A promotion is two writes — the mint, then the
                # reindex outbox — and only the second failed here, so *this*
                # candidate is durably stored too. Reporting it in ``promoted``
                # is what keeps the envelope's promise that the response agrees
                # with the stored state; dropping it (v1.7.35 did) understated the
                # mints by one and made the SoT claim false in this mode.
                promoted.append(_memory_payload(exc.result.memory))
                return JSONResponse(status_code=503, content={
                    "auto_promotion_threshold": memory.auto_promotion_threshold,
                    "promoted": promoted,
                    "promotion_error": str(exc),
                })
            except _STORAGE_ERRORS as exc:
                # SoT v1.7.35 D1=B/D2=A. The loop writes once per candidate with
                # no transaction spanning them, so a store failure at candidate N
                # leaves N-1 canonical mints already durable. They are append-only
                # and are not rolled back, so returning a bare error body would
                # make the response disagree with the stored state — report what
                # this call minted alongside the failure instead.
                #
                # The message names the stage (brief Follow-up #2): reaching here
                # means the mint itself did not happen, which is what tells an
                # operator that ``promoted`` is complete as reported.
                return JSONResponse(status_code=503, content={
                    "auto_promotion_threshold": memory.auto_promotion_threshold,
                    "promoted": promoted,
                    "promotion_error": (
                        f"canonical store failure — this candidate was not minted "
                        f"by this call: {exc}"
                    ),
                })
            if result is not None and not result.idempotent_replay:
                promoted.append(_memory_payload(result.memory))
        # 새로 승격된 것이 없으면(전부 replay) 바뀐 것이 없으므로 기록하지 않는다 —
        # A7=A 의 "결과를 안 뒤에 쓴다"를 이 경로에서 구체화한 것이다.
        #
        # ★ 알려진 공백: 위 두 503 partial envelope 경로는 mint 가 durable 한데도
        # 기록하지 않는다. 그 자리에 record 를 넣으면 부분 실패의 응답 계약(무엇이
        # 저장됐는지 envelope 이 말한다)과 로그가 두 정본이 되므로, 소비 시점에
        # 조인하는 A8=A 와 같은 이유로 미룬다.
        if promoted:
            activity.record(
                project_id=project_id, actor_user_id=current.id,
                action="candidates_auto_promoted", target_type="analysis_job",
                target_id=job_id, after=str(len(promoted)),
            )
        return {
            "auto_promotion_threshold": memory.auto_promotion_threshold,
            "promoted": promoted,
        }

    def _prior_memory_item_payload(item) -> dict[str, object]:
        return {
            "memory_id": item.memory_id,
            "memory_type": item.memory_type.value,
            "value": dict(item.value),
            "status": item.status.value,
            "version": item.version,
            "source_ref_ids": list(item.source_ref_ids),
            "match_reason": item.match_reason,
            "scope": _scope_payload(item.scope),
        }

    def _analysis_context_payload(package, gate) -> dict[str, object]:
        return {
            "package": {
                "project_id": package.project_id,
                "purpose": package.purpose.value,
                "status": package.status,
                "degraded": package.degraded,
                "token_estimate_total": package.token_estimate_total,
                "prior_memories": [
                    _prior_memory_item_payload(item)
                    for item in package.prior_memories
                ],
            },
            "gate": {
                "decision": gate.decision,
                "findings": [
                    {"check": finding.check, "detail": finding.detail}
                    for finding in gate.findings
                ],
            },
        }

    @app.post("/projects/{project_id}/analysis/jobs/{job_id}/context",
              responses=_owned(_ERRORS_404),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def analysis_context_endpoint(
        project_id: str, job_id: str
    ) -> dict[str, object]:
        # Job-aware entry surface (D4=B): derive the coarse candidate group
        # (the memory_types this job produced) and search prior canonical
        # memories of those types, excluding this job's own memories (F4).
        try:
            _require_project_exists(project_id)
            job = analysis.get_job(project_id=project_id, job_id=job_id)
            candidates = analysis.list_candidates(
                project_id=project_id, job_id=job_id
            )
        except (AnalysisNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        memory_types = tuple(
            dict.fromkeys(candidate.candidate_type for candidate in candidates)
        )
        # needs is fixed to (PRIOR_MEMORY,) here, so the service request is
        # always valid — no InvalidAnalysisContextRequest→400 branch to add
        # (the request validation is a service-level contract, locked at that
        # layer). Only job/project 404 is reachable from this endpoint.
        request = AnalysisContextRequest(
            project_id=project_id,
            needs=(ContextNeed.PRIOR_MEMORY,),
            memory_types=memory_types,
            exclude_job_id=job.id,
        )
        package = analysis_context.build_prior_memory_package(request)
        gate = evaluate_analysis_context_gate(package=package, request=request)
        return _analysis_context_payload(package, gate)

    def _action_proposal_payload(proposal) -> dict[str, object]:
        return {
            "candidate_id": proposal.candidate_id,
            "candidate_type": proposal.candidate_type.value,
            "action": proposal.action.value,
            "matched_memory_id": proposal.matched_memory_id,
            "rationale": proposal.rationale,
        }

    @app.post("/projects/{project_id}/analysis/jobs/{job_id}/compare",
              responses=_owned(_BILLABLE_404_502_CONFIG),
              dependencies=_REQUIRE_PROJECT_OWNER_BILLABLE)
    async def analysis_compare_endpoint(
        project_id: str, job_id: str
    ) -> dict[str, object]:
        # Phase 2B.3 (D7): compare a job's candidates against canonical memory
        # and return one action proposal per candidate (proposal only — no
        # memory write, D4=A).
        try:
            _require_project_exists(project_id)
            job = analysis.get_job(project_id=project_id, job_id=job_id)
            candidates = analysis.list_candidates(
                project_id=project_id, job_id=job_id
            )
        except (AnalysisNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        # Observability seam C (증분 C): one record per judge turn. The scope
        # ties a job's whole compare run together — N matched pairs leave N
        # rows under this one correlation_id, plus a repair row where the first
        # verdict was not JSON. Deterministic proposals (no match / duplicate)
        # call no provider and so leave nothing, without special handling.
        with llm_call_scope(llm_call_audit, project_id=project_id,
                            correlation_id=job.id) as scope:
            try:
                proposals = await compare.compare_job(
                    project_id=project_id, job_id=job.id, candidates=candidates
                )
            except CompareJudgeNotConfigured as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except InvalidJudgeResult as exc:
                # The judge answered and repair still failed to parse — the
                # domain's final rejection of that last answer (owner decision
                # 2026-07-26, D4). Recovered first attempts keep ``success``:
                # only the last call is touched, so the repair-frequency signal
                # (two rows under one correlation_id) stays intact.
                scope.reclassify_last_as_parse_error(type(exc).__name__)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            except ProviderError as exc:
                # A Gateway/provider failure during the matched-pair judge turn
                # (timeout/unavailable/5xx) is an LLM error → 502, applying the
                # v1.6.34 error taxonomy to this endpoint. Without this the
                # ProviderError raised by GatewayGenerateProvider propagates as an
                # unhandled 500. Already recorded by the decorator with its
                # taxonomy intact. 창 가드 거부만 4xx로 갈라진다(K-3).
                raise HTTPException(status_code=_provider_error_status(exc),
                                    detail=str(exc)) from exc
        return {
            "job_id": job.id,
            "proposals": [_action_proposal_payload(p) for p in proposals],
        }

    def _applied_proposal_payload(applied) -> dict[str, object]:
        return {
            "candidate_id": applied.candidate_id,
            "action": applied.action.value,
            "outcome": applied.outcome.value,
            "memory_id": applied.memory_id,
            "superseded_memory_id": applied.superseded_memory_id,
            "version": applied.version,
            "idempotent_replay": applied.idempotent_replay,
        }

    def _review_queue_entry_payload(entry) -> dict[str, object]:
        return {
            "id": entry.id,
            "job_id": entry.job_id,
            "candidate_id": entry.candidate_id,
            "candidate_type": entry.candidate_type.value,
            "action": entry.action.value,
            "matched_memory_id": entry.matched_memory_id,
            "rationale": entry.rationale,
            "status": entry.status.value,
        }

    @app.post("/projects/{project_id}/analysis/jobs/{job_id}/apply",
              responses=_owned(_ERRORS_400_404),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def analysis_apply_endpoint(
        project_id: str, job_id: str, request: ApplyMemoryRequest,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        # Phase 2B.4 (D1=A/D6=A): apply reviewed compare proposals to the
        # canonical memory store. Deterministic writes only — the proposals
        # carry the already-decided action labels (no LLM here). Safe actions
        # (create/update/add_evidence/no_change) are applied; conflict is
        # review-only (D7).
        try:
            _require_project_exists(project_id)
            job = analysis.get_job(project_id=project_id, job_id=job_id)
            candidates = analysis.list_candidates(
                project_id=project_id, job_id=job_id
            )
        except (AnalysisNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        proposals: list[ActionProposal] = []
        by_id = {candidate.id: candidate for candidate in candidates}
        for body in request.proposals:
            candidate = by_id.get(body.candidate_id)
            if candidate is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"candidate {body.candidate_id} is not part of this job",
                )
            try:
                action = CompareAction(body.action)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail=f"unknown action {body.action!r}"
                ) from exc
            proposals.append(
                ActionProposal(
                    candidate_id=body.candidate_id,
                    candidate_type=candidate.candidate_type,
                    action=action,
                    matched_memory_id=body.matched_memory_id,
                    rationale="",
                )
            )

        try:
            applied = apply_service.apply_proposals(
                project_id=project_id,
                proposals=tuple(proposals),
                candidates=candidates,
            )
        except MemoryNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (MissingMatchedMemory, MemoryError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except MemoryApplyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        activity.record(
            project_id=project_id, actor_user_id=current.id,
            action="compare_actions_applied", target_type="analysis_job",
            target_id=job.id, after=str(len(applied)),
        )
        return {
            "job_id": job.id,
            "applied": [_applied_proposal_payload(a) for a in applied],
        }

    @app.get("/projects/{project_id}/analysis/review-queue",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def analysis_review_queue_endpoint(project_id: str) -> dict[str, object]:
        # 2B.4 follow-up: list the project's open review-only (conflict) entries
        # persisted by apply, so an unresolved conflict is observable/reconcilable
        # (docs/plans/02b-4-review-queue-persistence-decisions.md, D2).
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        entries = review_queue.list_open(project_id)
        return {
            "project_id": project_id,
            "entries": [_review_queue_entry_payload(e) for e in entries],
        }

    @app.post(
        "/projects/{project_id}/analysis/review-queue/{entry_id}/reconcile",
        responses=_owned(_ERRORS_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def reconcile_character_conflict(
        project_id: str, entry_id: str, request: ReconcileCharacterRequest,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            action = ReconciliationAction(request.action)
            result = character_reconciliation.reconcile(
                project_id=project_id, entry_id=entry_id, action=action
            )
        except (NotFound, AnalysisNotFound, MemoryNotFound, KeyError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (MemoryError, InvalidCandidateStateTransition) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        activity.record(
            project_id=project_id, actor_user_id=current.id,
            action="review_queue_reconciled", target_type="review_queue_entry",
            target_id=result.entry_id, after=result.action.value,
        )
        return {
            "entry_id": result.entry_id,
            "action": result.action.value,
            "memory_id": result.memory_id,
            "superseded_memory_id": result.superseded_memory_id,
            "idempotent_replay": result.idempotent_replay,
        }

    def _review_source_pointer(project_id: str, source_ref_id: str) -> dict[str, object]:
        try:
            ref = core_sot.get_source_ref(
                project_id=project_id, source_ref_id=source_ref_id
            )
        except NotFound:
            return {"source_ref_id": source_ref_id, "status": "missing"}
        return {
            "source_ref_id": ref.id,
            "status": "resolved",
            "snapshot_id": ref.snapshot_id,
            "block_id": ref.block_id,
            "start_offset": ref.start_offset,
            "end_offset": ref.end_offset,
            "quote": ref.quote,
            "content_hash": ref.content_hash,
        }

    def _affordance_payload(affordance) -> dict[str, object]:
        return {
            "action": affordance.action,
            "eligible": affordance.eligible,
            "reason": affordance.reason,
        }

    def _identity_group_payload(summary) -> dict[str, object] | None:
        # 정체성 그룹 Slice 3 — additive group metadata. ungrouped는 null.
        # 기존 개별 item 필드·detail 경계는 개별 후보 기준으로 무변이다.
        if summary is None:
            return None
        return {
            "group_id": summary.group_id,
            "group_size": len(summary.member_ids),
            "group_status": summary.status.value,
            "group_member_ids": list(summary.member_ids),
            "identity_rationale_summary": summary.rationale_summary,
        }

    def _review_inbox_payload(item, *, include_detail: bool) -> dict[str, object]:
        candidate = item.candidate
        payload: dict[str, object] = {
            "candidate_id": candidate.id,
            "job_id": candidate.job_id,
            "candidate_type": candidate.candidate_type.value,
            "status": candidate.status.value,
            "confidence": candidate.confidence,
            "provenance": candidate.provenance.value,
            "conflict_count": len(item.conflicts),
            # Dogfood 2026-09-02: the inbox is an action surface, so the list
            # carries the candidate summary instead of forcing one detail trip
            # per approval/rejection decision.
            "payload": dict(candidate.payload),
            # v1.6.67: available review actions per item (list + detail, D3).
            "actions": [
                _affordance_payload(a) for a in candidate_affordances()
            ],
            # 정체성 그룹 Slice 3: 목록 렌더에 필요한 group 최소값(ungrouped null).
            "identity_group": _identity_group_payload(item.identity_group),
        }
        if include_detail:
            payload.update({
                "source_refs": [
                    _review_source_pointer(candidate.project_id, source_ref_id)
                    for source_ref_id in candidate.source_ref_ids
                ],
                "conflicts": [
                    {
                        "entry_id": conflict.entry.id,
                        "action": conflict.entry.action.value,
                        "rationale": conflict.entry.rationale,
                        "matched_memory": (
                            _memory_payload(conflict.matched_memory)
                            if conflict.matched_memory is not None else None
                        ),
                        "diff": [
                            {"field": diff.field, "before": diff.before,
                             "after": diff.after}
                            for diff in conflict.diff
                        ],
                        "actions": [
                            _affordance_payload(a)
                            for a in conflict_affordances(conflict)
                        ],
                    }
                    for conflict in item.conflicts
                ],
            })
        return payload

    @app.get("/projects/{project_id}/analysis/review-inbox",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def list_review_inbox(project_id: str) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "project_id": project_id,
            "items": [
                _review_inbox_payload(item, include_detail=False)
                for item in review_inbox.list_items(project_id=project_id)
            ],
            "gate_findings": [
                _gate_finding_payload(finding)
                for finding in gate_findings.list_open(project_id)
            ],
        }

    @app.get("/projects/{project_id}/analysis/review-inbox/{candidate_id}",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def get_review_inbox_item(
        project_id: str, candidate_id: str
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            item = review_inbox.get_item(
                project_id=project_id, candidate_id=candidate_id
            )
        except (NotFound, ReviewInboxNotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _review_inbox_payload(item, include_detail=True)

    def _gate_finding_payload(finding) -> dict[str, object]:
        return {
            "id": finding.id, "origin": "context_gate",
            "status": finding.status.value, "check": finding.check,
            "detail": finding.detail, "query": finding.query,
            "purpose": finding.purpose, "needs": list(finding.needs),
            "pointer_ids": list(finding.pointer_ids),
            "request_fingerprint": finding.request_fingerprint,
            "result_fingerprint": finding.result_fingerprint,
            "created_at": finding.created_at.isoformat(),
            "terminal_at": (
                finding.terminal_at.isoformat()
                if finding.terminal_at is not None else None
            ),
            "actions": [
                _affordance_payload(a)
                for a in gate_finding_affordances(
                    is_open=finding.status is GateFindingStatus.OPEN
                )
            ],
        }

    @app.get("/projects/{project_id}/analysis/gate-findings",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def list_gate_findings(project_id: str) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"project_id": project_id, "gate_findings": [
            _gate_finding_payload(finding)
            for finding in gate_findings.list_open(project_id)
        ]}

    @app.get("/projects/{project_id}/analysis/gate-findings/{finding_id}",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def get_gate_finding(project_id: str, finding_id: str):
        try:
            _require_project_exists(project_id)
            finding = gate_findings.get(
                project_id=project_id, finding_id=finding_id
            )
        except (NotFound, GateFindingNotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _gate_finding_payload(finding)

    async def _transition_gate_finding(
        project_id: str, finding_id: str, target: GateFindingStatus
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            finding, replay = gate_findings.transition(
                project_id=project_id, finding_id=finding_id, target=target
            )
        except (NotFound, GateFindingNotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidGateFindingTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"finding": _gate_finding_payload(finding),
                "idempotent_replay": replay}

    @app.post("/projects/{project_id}/analysis/gate-findings/{finding_id}/resolve",
              responses=_owned(_ERRORS_404_409),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def resolve_gate_finding(
        project_id: str, finding_id: str,
        current=Depends(require_authenticated_user),
    ):
        payload = await _transition_gate_finding(
            project_id, finding_id, GateFindingStatus.RESOLVED
        )
        activity.record(
            project_id=project_id, actor_user_id=current.id,
            action="gate_finding_resolved", target_type="gate_finding",
            target_id=finding_id, after=str(GateFindingStatus.RESOLVED),
        )
        return payload

    @app.post("/projects/{project_id}/analysis/gate-findings/{finding_id}/dismiss",
              responses=_owned(_ERRORS_404_409),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def dismiss_gate_finding(
        project_id: str, finding_id: str,
        current=Depends(require_authenticated_user),
    ):
        payload = await _transition_gate_finding(
            project_id, finding_id, GateFindingStatus.DISMISSED
        )
        activity.record(
            project_id=project_id, actor_user_id=current.id,
            action="gate_finding_dismissed", target_type="gate_finding",
            target_id=finding_id, after=str(GateFindingStatus.DISMISSED),
        )
        return payload
