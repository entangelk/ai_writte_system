"""프로젝트별 LLM 파이프라인 관측 KPI (``GET …/observability/kpi``, 1 operation).

``main.py`` 의 ``create_app()`` 에서 옮겨온 register 함수(R1). handler 본문은
byte-동일이다.

**집계 규칙은 여기 없다** — per-project 와 전역(``routers/admin.py``)이
``observability/kpi.py`` 의 ``_fold`` 한 곳을 공유한다(v1.7.57). 두 화면이 다른
사실을 말하지 않는 이유가 그 공유이므로, 규칙을 이 파일에 복제하면 안 된다.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import HTTPException

from services.application.app.core_sot.service import NotFound
from services.application.app.observability.kpi import aggregate_kpi

from ..api.models import ObservabilityKpiResponse
from ..api.errors import _ERRORS_404, _owned
from ..api.dependencies import _REQUIRE_PROJECT_OWNER


def register_observability(
    app, *, core_sot, llm_call_audit, writing_loop_audit
) -> None:
    def _require_project_exists(project_id: str) -> None:
        core_sot.get_project(project_id=project_id)

    @app.get("/projects/{project_id}/observability/kpi",
             response_model=ObservabilityKpiResponse,
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def observability_kpi_endpoint(project_id: str) -> dict[str, object]:
        # 증분 5 (brief D4=A): the read-out over the per-call audit trail. Pure
        # aggregation — nothing is measured here that the pipeline did not
        # already record, so this endpoint calls no provider and opens no scope.
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        kpi = aggregate_kpi(
            project_id=project_id,
            calls=llm_call_audit.list_calls(project_id),
            # The loop rollup is opt-in (WRITING_LOOP_AUDIT_DEFAULT, off), so
            # this is empty on a default deployment. That is why the payload
            # reports ``runs_considered`` next to the rate: a null rate over
            # zero runs is "never measured", not "never diverged".
            loop_runs=writing_loop_audit.list_runs(project_id),
        )
        return {
            "project_id": kpi.project_id,
            "totals": asdict(kpi.totals),
            "sites": [asdict(site) for site in kpi.sites],
            "gate": asdict(kpi.gate),
            "loop": asdict(kpi.loop),
        }
