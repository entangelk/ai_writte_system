"""Phase 4 Slice 4.3 context search HTTP API tests.

Locks the POST /projects/{id}/context-search surface and the async service
wiring: a wired ContextSearchService returns a serialized ContextPackage plus
the independent Context Gate decision; bad literals/requests, a missing
project, an unconfigured service, and planner (llm_error) failures each map to
their contracted status. The service is injected (fake planner + fake vector
index) so the endpoint is exercised without a live Gateway.
"""

import asyncio
import os
import unittest
from unittest.mock import patch

import httpx

from services.application.app.context_search.models import (
    ContextNeed,
    SearchPlan,
    SearchPlanStep,
    SearchTool,
)
from services.application.app.context_search.service import ContextSearchService
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.indexing.service import (
    DeterministicFakeEmbeddingProvider,
    InMemoryVectorIndexAdapter,
    SourceBlockIndexingService,
)
from services.application.app.main import create_app


RAW_TEXT = (
    "# 1장\n\n"
    "아린은 항구에 도착했다.\n\n"
    "낡은 단검에는 검은 태양 문양이 새겨져 있었다.\n\n"
    "---\n\n"
    "밤이 되자 노스워치의 등불이 켜졌다.\n\n"
    "아린은 편지를 다시 읽었다."
)


class TestClient:
    def __init__(self, app):
        self._app = app

    def post(self, path, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.post(path, **kwargs)

        return asyncio.run(send())


class _StaticPlanner:
    def __init__(self, plan):
        self._plan = plan

    def build_plan(self, request):
        return self._plan


class _FailingPlanner:
    def __init__(self, _plan=None):
        pass

    def build_plan(self, request):
        raise RuntimeError("provider unavailable")


def _fixture(planner_factory):
    core_sot = CoreSotService(InMemoryCoreSotRepository())
    project = core_sot.create_project(name="Novel")
    draft = core_sot.create_draft(project_id=project.id, title="Episode 1")
    saved = core_sot.save_draft(
        project_id=project.id,
        draft_id=draft.id,
        raw_text=RAW_TEXT,
        idempotency_key="save-1",
    )
    vector_index = InMemoryVectorIndexAdapter()
    indexing = SourceBlockIndexingService(
        core_sot=core_sot,
        embeddings=DeterministicFakeEmbeddingProvider(),
        vector_index=vector_index,
    )
    indexing.rebuild_snapshot_source_block_index(
        project_id=project.id, snapshot_id=saved.snapshot.id
    )
    plan = SearchPlan(
        plan_id="plan-1",
        project_id=project.id,
        steps=(
            SearchPlanStep(
                step_id="s1",
                need=ContextNeed.CURRENT_SCENE,
                tools=(SearchTool.MONGO,),
                query="",
            ),
            SearchPlanStep(
                step_id="s2",
                need=ContextNeed.SOURCE_QUOTE,
                tools=(SearchTool.VECTOR,),
                query="단검",
            ),
        ),
    )
    css = ContextSearchService(
        core_sot=core_sot,
        indexing_service=indexing,
        vector_search=vector_index,
        embeddings=DeterministicFakeEmbeddingProvider(),
        planner=planner_factory(plan),
    )
    app = create_app(service=core_sot, context_search_service=css)
    return app, project.id, draft.id, saved.draft_version.id


def _body(draft_id, version_id, *, needs=("current_scene", "source_quote"), **over):
    payload = {
        "query": "아린이 항구에서 낡은 단검을 발견한다",
        "needs": list(needs),
        "current_position": {"draft_id": draft_id, "version_id": version_id},
        "max_tokens": 10_000,
    }
    payload.update(over)
    return payload


class ContextSearchApiTest(unittest.TestCase):
    def test_returns_package_and_gate_decision(self):
        app, project_id, draft_id, version_id = _fixture(_StaticPlanner)
        resp = TestClient(app).post(
            f"/projects/{project_id}/context-search",
            json=_body(draft_id, version_id),
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        pkg = data["package"]
        self.assertEqual(pkg["project_id"], project_id)
        self.assertEqual(pkg["purpose"], "writing_context")
        self.assertEqual(pkg["status"], "candidate")
        # current_scene lands in macro; source_quote vector hits in micro.
        self.assertTrue(pkg["macro_items"])
        self.assertTrue(pkg["micro_evidence"])
        self.assertTrue(
            all(item["sot_reloaded"] for item in pkg["macro_items"])
        )
        self.assertEqual(
            {s["step_id"] for s in pkg["trace"]["plan"]["steps"]}, {"s1", "s2"}
        )
        self.assertIn(data["gate"]["decision"], {"pass", "reject"})

    def test_fresh_package_passes_the_gate(self):
        app, project_id, draft_id, version_id = _fixture(_StaticPlanner)
        resp = TestClient(app).post(
            f"/projects/{project_id}/context-search",
            json=_body(draft_id, version_id),
        )
        self.assertEqual(resp.json()["gate"]["decision"], "pass")

    def test_unknown_need_literal_is_400(self):
        app, project_id, draft_id, version_id = _fixture(_StaticPlanner)
        resp = TestClient(app).post(
            f"/projects/{project_id}/context-search",
            json=_body(draft_id, version_id, needs=["villain_arc"]),
        )
        self.assertEqual(resp.status_code, 400)

    def test_empty_needs_is_400(self):
        app, project_id, draft_id, version_id = _fixture(_StaticPlanner)
        resp = TestClient(app).post(
            f"/projects/{project_id}/context-search",
            json=_body(draft_id, version_id, needs=[]),
        )
        self.assertEqual(resp.status_code, 400)

    def test_missing_project_is_404(self):
        app, _project_id, draft_id, version_id = _fixture(_StaticPlanner)
        resp = TestClient(app).post(
            "/projects/does-not-exist/context-search",
            json=_body(draft_id, version_id),
        )
        self.assertEqual(resp.status_code, 404)

    def test_planner_failure_maps_to_502_llm_error(self):
        app, project_id, draft_id, version_id = _fixture(_FailingPlanner)
        resp = TestClient(app).post(
            f"/projects/{project_id}/context-search",
            json=_body(draft_id, version_id),
        )
        self.assertEqual(resp.status_code, 502)
        self.assertIn("llm_error", resp.json()["detail"])

    def test_unconfigured_service_is_503(self):
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        project = core_sot.create_project(name="Novel")
        draft = core_sot.create_draft(project_id=project.id, title="Episode 1")
        saved = core_sot.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text=RAW_TEXT,
            idempotency_key="save-1",
        )
        with patch.dict(os.environ):
            os.environ.pop("LLM_GATEWAY_BASE_URL", None)
            app = create_app(service=core_sot)
        resp = TestClient(app).post(
            f"/projects/{project.id}/context-search",
            json=_body(draft.id, saved.draft_version.id),
        )
        self.assertEqual(resp.status_code, 503)


if __name__ == "__main__":
    unittest.main()
