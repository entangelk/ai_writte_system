"""Phase 4 shared in-process vector index tests.

Locks the decision in docs/plans/04-shared-vector-index-decisions.md: create_app
owns a single in-process vector index that the rebuild HTTP endpoint writes into
and the default-wired context search reads from, so a rebuild followed by a
context search in the same process yields real vector hits. The rebuild HTTP
summary stays snapshot-scoped (per-rebuild, no accumulation) even though the
shared index accumulates behind the scenes. Archived-after-rebuild records are
excluded from context search by the query-time stale guard.
"""

import asyncio
import unittest

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
    __test__ = False  # httpx driver helper, not a pytest test class

    def __init__(self, app):
        self._app = app

    def _send(self, method, path, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    def post(self, path, **kwargs):
        return self._send("POST", path, **kwargs)

    def delete(self, path, **kwargs):
        return self._send("DELETE", path, **kwargs)


class _StaticPlanner:
    def __init__(self, plan):
        self._plan = plan

    def build_plan(self, request):
        return self._plan


def _plan(project_id):
    return SearchPlan(
        plan_id="plan-1",
        project_id=project_id,
        steps=(
            SearchPlanStep(
                step_id="s1",
                need=ContextNeed.SOURCE_QUOTE,
                tools=(SearchTool.VECTOR,),
                query="단검",
            ),
        ),
    )


def _shared_app():
    """create_app wired so the rebuild endpoint and the injected context search
    share one vector index (the same instance create_app owns)."""
    core_sot = CoreSotService(InMemoryCoreSotRepository())
    project = core_sot.create_project(name="Novel")
    draft = core_sot.create_draft(project_id=project.id, title="Episode 1")
    saved = core_sot.save_draft(
        project_id=project.id,
        draft_id=draft.id,
        raw_text=RAW_TEXT,
        idempotency_key="save-1",
    )
    shared_index = InMemoryVectorIndexAdapter()
    embeddings = DeterministicFakeEmbeddingProvider()
    indexing = SourceBlockIndexingService(
        core_sot=core_sot,
        embeddings=embeddings,
        vector_index=shared_index,
    )
    css = ContextSearchService(
        core_sot=core_sot,
        indexing_service=indexing,
        vector_search=shared_index,
        embeddings=embeddings,
        planner=_StaticPlanner(_plan(project.id)),
    )
    app = create_app(
        service=core_sot,
        context_search_service=css,
        vector_index=shared_index,
    )
    return app, core_sot, project.id, draft.id, saved.snapshot.id, saved.draft_version.id


def _search_body(draft_id, version_id):
    return {
        "idempotency_key": "shared-index-search-1",
        "query": "아린이 낡은 단검을 발견한다",
        "needs": ["source_quote"],
        "current_position": {"draft_id": draft_id, "version_id": version_id},
        "max_tokens": 10_000,
    }


class SharedVectorIndexTest(unittest.TestCase):
    def test_rebuild_endpoint_populates_index_queried_by_context_search(self):
        app, _core_sot, project_id, draft_id, snapshot_id, version_id = _shared_app()
        client = TestClient(app)

        # Before any rebuild the shared index is empty, so the vector need finds
        # no hits.
        before = client.post(
            f"/projects/{project_id}/context-search",
            json=_search_body(draft_id, version_id),
        )
        self.assertEqual(before.status_code, 200)
        self.assertEqual(before.json()["package"]["micro_evidence"], [])

        rebuilt = client.post(
            f"/projects/{project_id}/snapshots/{snapshot_id}"
            "/index/source-blocks/rebuild"
        )
        self.assertEqual(rebuilt.status_code, 200)
        self.assertGreater(rebuilt.json()["records_written"], 0)

        # After the HTTP rebuild the same-process context search sees real hits.
        after = client.post(
            f"/projects/{project_id}/context-search",
            json=_search_body(draft_id, version_id),
        )
        self.assertEqual(after.status_code, 200)
        micro = after.json()["package"]["micro_evidence"]
        self.assertTrue(micro)
        self.assertTrue(all(item["sot_reloaded"] for item in micro))

    def test_rebuild_summary_stays_snapshot_scoped_when_index_accumulates(self):
        app, core_sot, project_id, draft_id, snapshot_a, _version_id = _shared_app()
        client = TestClient(app)

        first = client.post(
            f"/projects/{project_id}/snapshots/{snapshot_a}"
            "/index/source-blocks/rebuild"
        ).json()

        # A second, larger snapshot in the same project accumulates into the
        # shared index, but its rebuild summary must report only its own records
        # (snapshot scope), not the running total.
        saved_b = core_sot.save_draft(
            project_id=project_id,
            draft_id=draft_id,
            raw_text=RAW_TEXT + "\n\n---\n\n새 장면이 이어졌다.\n\n또 다른 문단.",
            idempotency_key="save-2",
        )
        snapshot_b = saved_b.snapshot.id
        second = client.post(
            f"/projects/{project_id}/snapshots/{snapshot_b}"
            "/index/source-blocks/rebuild"
        ).json()

        # Re-running snapshot A after B is indexed still reports A's own count,
        # proving the summary is not the accumulated project total.
        first_again = client.post(
            f"/projects/{project_id}/snapshots/{snapshot_a}"
            "/index/source-blocks/rebuild"
        ).json()

        self.assertEqual(first["records_indexed"], first_again["records_indexed"])
        self.assertEqual(
            first["records_query_visible"], first_again["records_query_visible"]
        )
        self.assertGreater(
            second["records_indexed"], first["records_indexed"]
        )  # B genuinely has more blocks
        # The accumulated shared total (A + B) is strictly larger than either
        # per-rebuild summary, confirming the counts are scoped, not summed.
        self.assertLess(
            first_again["records_indexed"],
            first["records_indexed"] + second["records_indexed"],
        )

    def test_archived_draft_hit_excluded_by_stale_guard(self):
        app, _core_sot, project_id, draft_id, snapshot_id, version_id = _shared_app()
        client = TestClient(app)

        client.post(
            f"/projects/{project_id}/snapshots/{snapshot_id}"
            "/index/source-blocks/rebuild"
        )
        populated = client.post(
            f"/projects/{project_id}/context-search",
            json=_search_body(draft_id, version_id),
        )
        self.assertTrue(populated.json()["package"]["micro_evidence"])

        # Archiving the draft after the record was indexed leaves the record in
        # the shared index (fake mutation), but the query-time stale guard must
        # exclude it because the SOT reload now sees the draft archived.
        archived = client.delete(f"/projects/{project_id}/drafts/{draft_id}")
        self.assertEqual(archived.status_code, 200)

        after = client.post(
            f"/projects/{project_id}/context-search",
            json=_search_body(draft_id, version_id),
        )
        self.assertEqual(after.status_code, 200)
        self.assertEqual(after.json()["package"]["micro_evidence"], [])


if __name__ == "__main__":
    unittest.main()
