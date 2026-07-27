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
    GateDecision,
    GateFinding,
    SearchPlan,
    SearchPlanStep,
    SearchTool,
)
from services.application.app.context_search.gate_findings import (
    GateFindingService,
    InMemoryGateFindingRepository,
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
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from tests.auth_support import authenticate


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
        # D8-3a: this suite is about domain behaviour, not the session
        # boundary, so the client arrives authenticated. The boundary itself
        # is driven un-overridden in tests/test_auth_api.py.
        authenticate(app)
        self._app = app

    def post(self, path, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.post(path, **kwargs)

        return asyncio.run(send())

    def get(self, path, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.get(path, **kwargs)
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


class _AsyncProviderErrorPlanner:
    """Mirrors the real (async) LLM planner: build_plan returns a coroutine
    whose await raises a Gateway ProviderError (timeout/unavailable/5xx)."""

    def __init__(self, _plan=None):
        pass

    def build_plan(self, request):
        async def _turn():
            raise ProviderError(
                code=ProviderErrorCode.UNAVAILABLE,
                message="gateway is unavailable",
                retryable=True,
                provider="llm_gateway",
            )

        return _turn()


class _AdvancingClock:
    """Returns each value once, then repeats the last, to drive wall-clock."""

    def __init__(self, values):
        self._values = list(values)
        self._i = 0

    def __call__(self):
        value = self._values[min(self._i, len(self._values) - 1)]
        self._i += 1
        return value


class _FailingGateFindingService:
    def persist_rejection(self, **_kwargs):
        raise RuntimeError("store unavailable")

    def list_open(self, _project_id):
        return ()


try:  # pymongo is optional for the in-memory path
    from pymongo.errors import AutoReconnect as _STORAGE_FAILURE
except ModuleNotFoundError:  # pragma: no cover - the driver is present in CI
    _STORAGE_FAILURE = None


class _StorageFailingGateFindingService:
    def persist_rejection(self, **_kwargs):
        raise _STORAGE_FAILURE("connection to the canonical store was lost")

    def list_open(self, _project_id):
        return ()


def _fixture(planner_factory, *, gate_finding_service=None, **service_kwargs):
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
        **service_kwargs,
    )
    app = create_app(
        service=core_sot, context_search_service=css,
        gate_finding_service=gate_finding_service,
    )
    return app, project.id, draft.id, saved.draft_version.id


def _body(draft_id, version_id, *, needs=("current_scene", "source_quote"), **over):
    payload = {
        "idempotency_key": "context-search-1",
        "query": "아린이 항구에서 낡은 단검을 발견한다",
        "needs": list(needs),
        "current_position": {"draft_id": draft_id, "version_id": version_id},
        "max_tokens": 10_000,
    }
    payload.update(over)
    return payload


class ContextSearchApiTest(unittest.TestCase):
    def test_gate_finding_routes_return_404_for_missing_scope_or_id(self):
        app, project_id, _draft_id, _version_id = _fixture(_StaticPlanner)
        client = TestClient(app)
        self.assertEqual(
            client.get("/projects/missing/analysis/gate-findings").status_code,
            404,
        )
        self.assertEqual(
            client.get(
                f"/projects/{project_id}/analysis/gate-findings/missing"
            ).status_code,
            404,
        )
        self.assertEqual(
            client.post(
                f"/projects/{project_id}/analysis/gate-findings/missing/resolve"
            ).status_code,
            404,
        )

    def test_gate_finding_persistence_failure_is_502(self):
        app, project_id, draft_id, version_id = _fixture(
            _StaticPlanner,
            gate_finding_service=_FailingGateFindingService(),
        )
        rejected = GateDecision(decision="reject", findings=(
            GateFinding(check="x", detail="y"),
        ))
        with patch(
            "services.application.app.main.evaluate_context_gate",
            return_value=rejected,
        ):
            response = TestClient(app).post(
                f"/projects/{project_id}/context-search",
                json=_body(draft_id, version_id),
            )
        self.assertEqual(response.status_code, 502)
        self.assertIn("persistence failed", response.json()["detail"])

    @unittest.skipIf(_STORAGE_FAILURE is None, "pymongo is not installed")
    def test_gate_finding_storage_failure_is_503(self):
        # SoT v1.7.40 D2=A (owner decision 2026-07-24). A canonical store failure
        # (pymongo type) while persisting the gate rejection is the store face of
        # 503, not the 502 an operational persistence bug gets. Before this the
        # ``except Exception → GateFindingError`` wrap reclassified it as an
        # upstream 502; now it re-raises unwrapped and reaches the global handler.
        #
        # Under-strict: removing the ``except _STORAGE_ERRORS: raise`` clause drops
        # the pymongo error back into the wrap and this re-fails at 502. Over-strict
        # (a non-pymongo persist failure must stay 502) is held by the sibling
        # test_gate_finding_persistence_failure_is_502, whose fake raises a plain
        # RuntimeError.
        app, project_id, draft_id, version_id = _fixture(
            _StaticPlanner,
            gate_finding_service=_StorageFailingGateFindingService(),
        )
        rejected = GateDecision(decision="reject", findings=(
            GateFinding(check="x", detail="y"),
        ))
        with patch(
            "services.application.app.main.evaluate_context_gate",
            return_value=rejected,
        ):
            response = TestClient(app).post(
                f"/projects/{project_id}/context-search",
                json=_body(draft_id, version_id),
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(set(response.json()), {"detail"})

    def test_reject_persists_to_inbox_and_transitions(self):
        store = GateFindingService(InMemoryGateFindingRepository())
        app, project_id, draft_id, version_id = _fixture(
            _StaticPlanner, gate_finding_service=store
        )
        rejected = GateDecision(decision="reject", findings=(
            GateFinding(check="test_check", detail="test detail"),
        ))
        with patch(
            "services.application.app.main.evaluate_context_gate",
            return_value=rejected,
        ):
            first = TestClient(app).post(
                f"/projects/{project_id}/context-search",
                json=_body(draft_id, version_id),
            )
            replay = TestClient(app).post(
                f"/projects/{project_id}/context-search",
                json=_body(draft_id, version_id),
            )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        inbox = TestClient(app).get(
            f"/projects/{project_id}/analysis/review-inbox"
        ).json()
        [finding] = inbox["gate_findings"]
        self.assertEqual(finding["origin"], "context_gate")
        self.assertEqual(finding["check"], "test_check")
        self.assertTrue(finding["request_fingerprint"])
        resolved = TestClient(app).post(
            f"/projects/{project_id}/analysis/gate-findings/{finding['id']}/resolve"
        )
        self.assertEqual(resolved.status_code, 200)
        self.assertFalse(resolved.json()["idempotent_replay"])
        repeated = TestClient(app).post(
            f"/projects/{project_id}/analysis/gate-findings/{finding['id']}/resolve"
        )
        self.assertTrue(repeated.json()["idempotent_replay"])
        crossed = TestClient(app).post(
            f"/projects/{project_id}/analysis/gate-findings/{finding['id']}/dismiss"
        )
        self.assertEqual(crossed.status_code, 409)

    def test_empty_idempotency_key_is_400(self):
        app, project_id, draft_id, version_id = _fixture(_StaticPlanner)
        response = TestClient(app).post(
            f"/projects/{project_id}/context-search",
            json=_body(draft_id, version_id, idempotency_key=""),
        )
        self.assertEqual(response.status_code, 400)

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

    def test_planner_provider_error_maps_to_502_llm_error(self):
        """Tracked debt #8 lock: a real Gateway ProviderError raised during the
        planner's async provider turn maps to 502/llm_error (not an uncaught
        500). Under-strict: removing the service's ``except ProviderError`` (and
        the generic catch) re-fails this via a 500. Over-strict: the explicit
        branch is pinned by asserting the ``provider error`` detail, which only
        that branch (not the generic ``planner failed`` catch) produces."""
        app, project_id, draft_id, version_id = _fixture(
            _AsyncProviderErrorPlanner
        )
        resp = TestClient(app).post(
            f"/projects/{project_id}/context-search",
            json=_body(draft_id, version_id),
        )
        self.assertEqual(resp.status_code, 502)
        self.assertIn("llm_error", resp.json()["detail"])
        self.assertIn("provider error", resp.json()["detail"])

    def test_wall_clock_budget_exceeded_is_504(self):
        """E1 should-fire: ContextSearchBudgetExceeded (wall-clock) maps to 504
        per contract §9.3. Changing the endpoint mapping re-fails this."""
        app, project_id, draft_id, version_id = _fixture(
            _StaticPlanner,
            wall_clock_seconds=0.01,
            clock=_AdvancingClock([0.0, 100.0]),
        )
        resp = TestClient(app).post(
            f"/projects/{project_id}/context-search",
            json=_body(draft_id, version_id),
        )
        self.assertEqual(resp.status_code, 504)

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


class ContextSearchErrorBodyExactKeyTest(unittest.TestCase):
    """context-search error bodies are exactly ``{"detail": <string>}``.

    H3 S4 declares 400/404/502/503/504 on this endpoint, all pointing at the
    single ``ErrorDetailResponse``. Those declarations are only honest if the
    wire body matches, and ``detail`` being the *only* key is what lets the SoT
    say the status code is the machine-readable layer (a future ``reason`` field
    is an explicit additive decision, D1=B, not something that arrives by drift).

    These live here rather than in ``test_application_api.py`` because 502/504
    need this module's planner/clock fixtures; duplicating that harness to keep
    the S4 locks in one file would be the worse trade.
    """

    def _assert_detail_only(self, response, status: int):
        self.assertEqual(response.status_code, status)
        body = response.json()
        self.assertEqual(set(body), {"detail"})
        self.assertIsInstance(body["detail"], str)
        self.assertTrue(body["detail"])

    def test_502_body(self):
        app, project_id, draft_id, version_id = _fixture(_FailingPlanner)
        self._assert_detail_only(
            TestClient(app).post(
                f"/projects/{project_id}/context-search",
                json=_body(draft_id, version_id),
            ),
            502,
        )

    def test_504_body(self):
        app, project_id, draft_id, version_id = _fixture(
            _StaticPlanner,
            wall_clock_seconds=0.01,
            clock=_AdvancingClock([0.0, 100.0]),
        )
        self._assert_detail_only(
            TestClient(app).post(
                f"/projects/{project_id}/context-search",
                json=_body(draft_id, version_id),
            ),
            504,
        )

    def test_503_body(self):
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
        self._assert_detail_only(
            TestClient(app).post(
                f"/projects/{project.id}/context-search",
                json=_body(draft.id, saved.draft_version.id),
            ),
            503,
        )


if __name__ == "__main__":
    unittest.main()
