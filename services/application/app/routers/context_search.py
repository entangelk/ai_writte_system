"""컨텍스트 검색 route (``POST /projects/{id}/context-search``, 1 operation).

``main.py`` 의 ``create_app()`` 에서 옮겨온 register 함수(R1). handler 본문은
byte-동일이다.

**유료 경로다**(Slice 8.0 분류표) — ``_REQUIRE_PROJECT_OWNER_BILLABLE`` 이
소유권 뒤에 시행을 두는 순서 자체가 계약이고("404·403 은 무과금"), 그 순서는
route 선언을 읽는 셀이 잠근다. 데코레이터를 이 파일로 옮겨도 가드는
``app.routes`` 를 보므로 그대로 성립한다.

``_context_*_payload`` 와 ``_build_context_search_request`` 는 **이 도메인만**
쓰므로 공유 모듈이 아니라 여기 있다. 반면 ``_project_brief_payload`` 는
projects 도메인과 공유하므로 ``..api.payloads`` 에서 가져온다.
"""

from __future__ import annotations

from fastapi import HTTPException

from services.application.app.context_search.gate_findings import GateFindingError
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
    InvalidContextSearchRequest,
    evaluate_context_gate,
)
from services.application.app.core_sot.service import NotFound
from services.application.app.observability.llm_call_scope import (
    llm_call_scope,
    reclassify_planner_parse_error,
)

from ..api.models import ContextSearchHttpRequest
from ..api.errors import _BILLABLE_400_404_502_504_CONFIG, _STORAGE_ERRORS, _owned
from ..api.dependencies import (
    _REQUIRE_PROJECT_OWNER_BILLABLE,
    project_existence_check,
)
from ..api.payloads import _project_brief_payload


def register_context_search(
    app,
    *,
    core_sot,
    memory,
    analysis,
    context_search,
    gate_findings,
    llm_call_audit,
) -> None:
    _require_project_exists = project_existence_check(core_sot)

    def _context_item_payload(item) -> dict[str, object]:
        return {
            "need": item.need.value,
            "status": item.status.value,
            "text": item.text,
            "pointer": {
                "project_id": item.pointer.project_id,
                "collection": item.pointer.collection,
                "document_id": item.pointer.document_id,
                "version_id": item.pointer.version_id,
                "content_hash": item.pointer.content_hash,
            },
            "snapshot_id": item.snapshot_id,
            "sot_reloaded": item.sot_reloaded,
            "token_estimate": item.token_estimate,
            "source_ref_ids": list(item.source_ref_ids),
            "review_status": item.review_status,
        }

    def _context_trace_payload(trace) -> dict[str, object]:
        return {
            "plan": {
                "plan_id": trace.plan.plan_id,
                "steps": [
                    {
                        "step_id": step.step_id,
                        "need": step.need.value,
                        "tools": [tool.value for tool in step.tools],
                        "query": step.query,
                    }
                    for step in trace.plan.steps
                ],
            },
            "steps": [
                {
                    "step_id": step.step_id,
                    "need": step.need.value,
                    "tool": step.tool.value,
                    "hits_considered": step.hits_considered,
                    "items_produced": step.items_produced,
                    "excluded": [
                        {"record_id": hit.record_id, "reason": hit.reason}
                        for hit in step.excluded
                    ],
                    "failure": (
                        None
                        if step.failure is None
                        else {
                            "error_type": step.failure.error_type.value,
                            "detail": step.failure.detail,
                        }
                    ),
                }
                for step in trace.steps
            ],
            "budget_excluded": [
                {"record_id": hit.record_id, "reason": hit.reason}
                for hit in trace.budget_excluded
            ],
        }

    def _context_package_payload(package, gate) -> dict[str, object]:
        return {
            "package": {
                "project_id": package.project_id,
                "purpose": package.purpose.value,
                "status": package.status,
                "degraded": package.degraded,
                "token_estimate_total": package.token_estimate_total,
                "macro_items": [
                    _context_item_payload(item) for item in package.macro_items
                ],
                "micro_evidence": [
                    _context_item_payload(item) for item in package.micro_evidence
                ],
                "constraints": list(package.constraints),
                "do_not_use": list(package.do_not_use),
                "project_brief": (
                    _project_brief_payload(package.project_brief)
                    if package.project_brief is not None
                    else None
                ),
                "trace": _context_trace_payload(package.trace),
            },
            "gate": {
                "decision": gate.decision,
                "findings": [
                    {"check": finding.check, "detail": finding.detail}
                    for finding in gate.findings
                ],
            },
        }

    @app.post("/projects/{project_id}/context-search",
              responses=_owned(_BILLABLE_400_404_502_504_CONFIG),
              dependencies=_REQUIRE_PROJECT_OWNER_BILLABLE)
    async def context_search_endpoint(
        project_id: str, body: ContextSearchHttpRequest
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            request = _build_context_search_request(project_id, body)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if context_search is None:
            raise HTTPException(
                status_code=503,
                detail="context search service is not configured",
            )
        # Observability seam C (증분 C): the query planner's calls (one, or two
        # when the first plan is not JSON). ``idempotency_key`` is this
        # endpoint's workflow tie — it is what the caller retries under.
        with llm_call_scope(llm_call_audit, project_id=project_id,
                            correlation_id=body.idempotency_key) as scope:
            try:
                package = await context_search.build_context_package(request)
                gate = evaluate_context_gate(
                    package=package,
                    request=request,
                    core_sot=core_sot,
                    memory_service=memory,
                    analysis_service=analysis,
                )
                try:
                    gate_findings.persist_rejection(
                        request=request, idempotency_key=body.idempotency_key,
                        package=package, gate=gate,
                    )
                except _STORAGE_ERRORS:
                    # SoT v1.7.40 D2=A (owner decision 2026-07-24): a canonical store
                    # failure while persisting the gate rejection is the store face of
                    # 503, not the upstream 502 the ``GateFindingError`` wrap below
                    # assigns. Re-raise it unwrapped so it escapes both this try and
                    # the outer one (no outer clause matches a pymongo type) to the
                    # global handler → 503, matching run and every other storage path.
                    # Non-pymongo persistence failures still become GateFindingError →
                    # 502 (over-strict guard: an operational persist bug is not a store
                    # outage). Empty ``_STORAGE_ERRORS`` (no driver) catches nothing.
                    raise
                except Exception as exc:
                    raise GateFindingError(str(exc)) from exc
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
            except GateFindingError as exc:
                raise HTTPException(
                    status_code=502, detail=f"gate finding persistence failed: {exc}"
                ) from exc
        return _context_package_payload(package, gate)


def _build_context_search_request(
    project_id: str, body: ContextSearchHttpRequest
) -> ContextSearchRequest:
    if not body.idempotency_key.strip():
        raise ValueError("idempotency_key is required")
    try:
        purpose = ContextSearchPurpose(body.purpose)
    except ValueError as exc:
        raise ValueError(f"unsupported purpose: {body.purpose}") from exc
    # /context-search serves Writing only; analysis_context has its own
    # job-scoped endpoint. Keep the two purposes on separate surfaces.
    if purpose is not ContextSearchPurpose.WRITING_CONTEXT:
        raise ValueError(f"unsupported purpose: {body.purpose}")
    needs: list[ContextNeed] = []
    for raw_need in body.needs:
        try:
            needs.append(ContextNeed(raw_need))
        except ValueError as exc:
            raise ValueError(f"unsupported need: {raw_need}") from exc
    position = (
        CurrentPosition(
            draft_id=body.current_position.draft_id,
            version_id=body.current_position.version_id,
        )
        if body.current_position is not None
        else None
    )
    return ContextSearchRequest(
        project_id=project_id,
        purpose=purpose,
        needs=tuple(needs),
        query=body.query,
        current_position=position,
        context_budget=ContextBudget(max_tokens=body.max_tokens),
    )
