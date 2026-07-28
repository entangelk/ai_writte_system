"""FastAPI shell tests for the Application service."""

import asyncio
import json
import os
import unittest
from unittest.mock import patch

import httpx

from services.application.app.analysis.models import (
    AnalysisCandidateAction,
    AnalysisCandidateType,
    AnalysisJobFailureReason,
    AnalysisProvenance,
)
from services.application.app.analysis.repository import (
    DuplicateAnalysisCandidateRequest,
)
from services.application.app.analysis.runner import AnalysisExtractionRunResult
from services.application.app.analysis.service import (
    AnalysisService,
    InMemoryAnalysisRepository,
    InvalidAnalysisCandidate,
)
from services.application.app.core_sot.models import Draft
from services.application.app.indexing.embedding import EmbeddingProviderError
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
    NotFound,
)
from services.application.app.indexing.models import IndexSyncEvent
from services.application.app.indexing.service import (
    DRAFTS_COLLECTION,
    InMemoryIndexSyncRepository,
    IndexSyncOutboxService,
    PROJECTS_COLLECTION,
)
from services.application.app.main import create_app
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryReindexEnqueueFailed,
    MemoryService,
)

try:  # pymongo is optional for the in-memory path (main._resolve_storage_error_types)
    from pymongo.errors import AutoReconnect as _STORAGE_FAILURE
except ModuleNotFoundError:  # pragma: no cover - the driver is present in CI
    _STORAGE_FAILURE = None
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.provider import FakeLLMProvider, GenerationResult
from tests.auth_support import authenticate


class TestClient:
    """Small sync wrapper around ASGITransport for this test module."""

    def __init__(self, app):
        # D8-3a: this suite is about domain behaviour, not the session
        # boundary, so the client arrives authenticated. The boundary itself
        # is driven un-overridden in tests/test_auth_api.py.
        authenticate(app)
        self._app = app

    def get(self, path: str, **kwargs):
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs):
        return self._request("POST", path, **kwargs)

    def put(self, path: str, **kwargs):
        return self._request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs):
        return self._request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs):
        return self._request("DELETE", path, **kwargs)

    def _request(self, method: str, path: str, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())


class ApplicationApiTest(unittest.TestCase):
    def test_health_endpoint(self):
        client = TestClient(create_app())

        response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_project_draft_save_minimal_flow_and_idempotent_replay(self):
        client = TestClient(create_app())

        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts",
            json={"title": "Episode 1"},
        ).json()
        first = client.post(
            f"/projects/{project['id']}/drafts/{draft['id']}/versions",
            json={"raw_text": "# Title\n\nBody.", "idempotency_key": "save-1"},
        )
        replay = client.post(
            f"/projects/{project['id']}/drafts/{draft['id']}/versions",
            json={"raw_text": "retry body", "idempotency_key": "save-1"},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertFalse(first.json()["idempotent_replay"])
        self.assertTrue(replay.json()["idempotent_replay"])
        self.assertEqual(
            replay.json()["draft_version"]["id"],
            first.json()["draft_version"]["id"],
        )

    def test_project_list_and_get_round_trip(self):
        client = TestClient(create_app())
        self.assertEqual(client.get("/projects").json(), {"projects": []})

        created = client.post("/projects", json={"name": "Novel"}).json()
        listed = client.get("/projects").json()["projects"]
        fetched = client.get(f"/projects/{created['id']}")

        self.assertEqual([p["id"] for p in listed], [created["id"]])
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json(), created)

    def test_get_missing_project_returns_404(self):
        client = TestClient(create_app())

        self.assertEqual(client.get("/projects/nope").status_code, 404)

    def test_draft_list_get_and_project_isolation(self):
        client = TestClient(create_app())
        project_a = client.post("/projects", json={"name": "A"}).json()
        project_b = client.post("/projects", json={"name": "B"}).json()
        draft_a = client.post(
            f"/projects/{project_a['id']}/drafts", json={"title": "Episode 1"}
        ).json()

        listed_a = client.get(f"/projects/{project_a['id']}/drafts").json()["drafts"]
        listed_b = client.get(f"/projects/{project_b['id']}/drafts").json()["drafts"]
        fetched = client.get(f"/projects/{project_a['id']}/drafts/{draft_a['id']}")

        self.assertEqual([d["id"] for d in listed_a], [draft_a["id"]])
        # should NOT fire: project B must not see project A's draft.
        self.assertEqual(listed_b, [])
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json(), draft_a)

    def test_get_draft_cross_project_returns_404(self):
        client = TestClient(create_app())
        project_a = client.post("/projects", json={"name": "A"}).json()
        project_b = client.post("/projects", json={"name": "B"}).json()
        draft_a = client.post(
            f"/projects/{project_a['id']}/drafts", json={"title": "Episode 1"}
        ).json()

        cross = client.get(f"/projects/{project_b['id']}/drafts/{draft_a['id']}")
        missing_project = client.get("/projects/nope/drafts")

        self.assertEqual(cross.status_code, 404)
        self.assertEqual(missing_project.status_code, 404)

    def test_get_missing_draft_returns_404(self):
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()

        missing = client.get(f"/projects/{project['id']}/drafts/nope")

        self.assertEqual(missing.status_code, 404)

    def test_lists_preserve_creation_order(self):
        # Spec is silent on order, but both backends return creation order;
        # lock that deterministic behavior so an accidental reorder is caught.
        client = TestClient(create_app())
        created_projects = [
            client.post("/projects", json={"name": name}).json()["id"]
            for name in ("First", "Second", "Third")
        ]
        listed_projects = [p["id"] for p in client.get("/projects").json()["projects"]]
        self.assertEqual(listed_projects, created_projects)

        created_drafts = [
            client.post(
                f"/projects/{created_projects[0]}/drafts", json={"title": title}
            ).json()["id"]
            for title in ("E1", "E2", "E3")
        ]
        listed_drafts = [
            d["id"]
            for d in client.get(f"/projects/{created_projects[0]}/drafts").json()[
                "drafts"
            ]
        ]
        self.assertEqual(listed_drafts, created_drafts)

    def test_rename_project_and_draft_persist_via_get(self):
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Old"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Old Title"}
        ).json()

        renamed_project = client.patch(
            f"/projects/{project['id']}", json={"name": "New"}
        )
        renamed_draft = client.patch(
            f"/projects/{project['id']}/drafts/{draft['id']}",
            json={"title": "New Title"},
        )

        self.assertEqual(renamed_project.status_code, 200)
        self.assertEqual(renamed_project.json()["name"], "New")
        self.assertEqual(renamed_draft.json()["title"], "New Title")
        # Reflected through a fresh read.
        self.assertEqual(client.get(f"/projects/{project['id']}").json()["name"], "New")
        self.assertEqual(
            client.get(
                f"/projects/{project['id']}/drafts/{draft['id']}"
            ).json()["title"],
            "New Title",
        )

    def test_rename_missing_returns_404(self):
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()

        self.assertEqual(
            client.patch("/projects/nope", json={"name": "X"}).status_code, 404
        )
        self.assertEqual(
            client.patch(
                f"/projects/{project['id']}/drafts/nope", json={"title": "X"}
            ).status_code,
            404,
        )

    def test_rename_cross_project_draft_returns_404(self):
        client = TestClient(create_app())
        project_a = client.post("/projects", json={"name": "A"}).json()
        project_b = client.post("/projects", json={"name": "B"}).json()
        draft_a = client.post(
            f"/projects/{project_a['id']}/drafts", json={"title": "Episode 1"}
        ).json()

        cross = client.patch(
            f"/projects/{project_b['id']}/drafts/{draft_a['id']}",
            json={"title": "Hijack"},
        )

        self.assertEqual(cross.status_code, 404)

    def test_rename_on_archived_is_blocked_409(self):
        service = CoreSotService(InMemoryCoreSotRepository())
        client = TestClient(create_app(service))
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        service.archive_draft(project_id=project["id"], draft_id=draft["id"])

        # Draft archived: draft rename blocked, project still renamable.
        draft_blocked = client.patch(
            f"/projects/{project['id']}/drafts/{draft['id']}",
            json={"title": "Nope"},
        )
        self.assertEqual(draft_blocked.status_code, 409)

        service.archive_project(project_id=project["id"])
        # Project archived: project rename blocked too.
        project_blocked = client.patch(
            f"/projects/{project['id']}", json={"name": "Nope"}
        )
        self.assertEqual(project_blocked.status_code, 409)

    def test_rename_draft_blocked_when_only_project_archived(self):
        # Isolates rename_draft's `project.archived` guard: the draft itself is
        # active, so only the project-archived branch can block. Removing that
        # guard would wrongly allow renaming a draft in an archived project.
        service = CoreSotService(InMemoryCoreSotRepository())
        client = TestClient(create_app(service))
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        service.archive_project(project_id=project["id"])  # draft stays active

        blocked = client.patch(
            f"/projects/{project['id']}/drafts/{draft['id']}",
            json={"title": "Nope"},
        )

        self.assertEqual(blocked.status_code, 409)

    def test_rename_project_allowed_when_only_draft_archived(self):
        # should-fire: an archived draft must not block renaming its project.
        service = CoreSotService(InMemoryCoreSotRepository())
        client = TestClient(create_app(service))
        project = client.post("/projects", json={"name": "Old"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        service.archive_draft(project_id=project["id"], draft_id=draft["id"])

        renamed = client.patch(f"/projects/{project['id']}", json={"name": "New"})

        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["name"], "New")

    def test_archive_project_via_delete_blocks_writes_keeps_reads(self):
        sync_repo = InMemoryIndexSyncRepository()
        client = TestClient(
            create_app(
                index_sync_outbox=IndexSyncOutboxService(sync_repo),
            )
        )
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()

        archived = client.delete(f"/projects/{project['id']}")

        self.assertEqual(archived.status_code, 200)
        self.assertTrue(archived.json()["archived"])
        outbox_entries = tuple(sync_repo.outbox_entries.values())
        self.assertEqual(len(outbox_entries), 1)
        self.assertEqual(outbox_entries[0].event, IndexSyncEvent.PROJECT_ARCHIVED)
        self.assertEqual(outbox_entries[0].source.mongo_collection, PROJECTS_COLLECTION)
        self.assertEqual(outbox_entries[0].source.mongo_id, project["id"])
        # Read still allowed (§115).
        self.assertEqual(
            client.get(f"/projects/{project['id']}").json()["archived"], True
        )
        # Writes blocked: new draft and save → 409.
        self.assertEqual(
            client.post(
                f"/projects/{project['id']}/drafts", json={"title": "E2"}
            ).status_code,
            409,
        )
        self.assertEqual(
            client.post(
                f"/projects/{project['id']}/drafts/{draft['id']}/versions",
                json={"raw_text": "x", "idempotency_key": "k"},
            ).status_code,
            409,
        )

    def test_archive_draft_via_delete(self):
        sync_repo = InMemoryIndexSyncRepository()
        client = TestClient(
            create_app(
                index_sync_outbox=IndexSyncOutboxService(sync_repo),
            )
        )
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()

        archived = client.delete(
            f"/projects/{project['id']}/drafts/{draft['id']}"
        )

        self.assertEqual(archived.status_code, 200)
        self.assertTrue(archived.json()["archived"])
        outbox_entries = tuple(sync_repo.outbox_entries.values())
        self.assertEqual(len(outbox_entries), 1)
        self.assertEqual(outbox_entries[0].event, IndexSyncEvent.DRAFT_ARCHIVED)
        self.assertEqual(outbox_entries[0].source.mongo_collection, DRAFTS_COLLECTION)
        self.assertEqual(outbox_entries[0].source.mongo_id, draft["id"])
        # Draft write blocked, draft still readable.
        self.assertEqual(
            client.patch(
                f"/projects/{project['id']}/drafts/{draft['id']}",
                json={"title": "X"},
            ).status_code,
            409,
        )
        self.assertEqual(
            client.get(
                f"/projects/{project['id']}/drafts/{draft['id']}"
            ).status_code,
            200,
        )

    def test_archive_is_idempotent(self):
        sync_repo = InMemoryIndexSyncRepository()
        client = TestClient(
            create_app(
                index_sync_outbox=IndexSyncOutboxService(sync_repo),
            )
        )
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()

        # Draft re-archive is idempotent (archive its draft before the project).
        first_draft = client.delete(
            f"/projects/{project['id']}/drafts/{draft['id']}"
        )
        second_draft = client.delete(
            f"/projects/{project['id']}/drafts/{draft['id']}"
        )
        self.assertEqual(first_draft.status_code, 200)
        self.assertEqual(second_draft.status_code, 200)
        self.assertTrue(second_draft.json()["archived"])

        # Project re-archive is idempotent too.
        first = client.delete(f"/projects/{project['id']}")
        second = client.delete(f"/projects/{project['id']}")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["archived"])
        entries = tuple(sync_repo.outbox_entries.values())
        self.assertEqual(len(entries), 2)
        self.assertEqual(
            {entry.event for entry in entries},
            {IndexSyncEvent.DRAFT_ARCHIVED, IndexSyncEvent.PROJECT_ARCHIVED},
        )

    def test_archive_draft_allowed_when_project_archived(self):
        # §115: archiving a draft is a STATE TRANSITION, exempt from the
        # "archived project blocks child-draft writes" rule. Archiving the
        # project first must NOT make the draft un-archivable. This is an
        # over-strict guard: adding a project.archived check to archive_draft
        # (misreading the write-block) would re-fail this test.
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        client.delete(f"/projects/{project['id']}")  # archive project first

        archived_draft = client.delete(
            f"/projects/{project['id']}/drafts/{draft['id']}"
        )

        self.assertEqual(archived_draft.status_code, 200)
        self.assertTrue(archived_draft.json()["archived"])

    def test_archive_missing_and_cross_project_returns_404(self):
        client = TestClient(create_app())
        project_a = client.post("/projects", json={"name": "A"}).json()
        project_b = client.post("/projects", json={"name": "B"}).json()
        draft_a = client.post(
            f"/projects/{project_a['id']}/drafts", json={"title": "Episode 1"}
        ).json()

        self.assertEqual(client.delete("/projects/nope").status_code, 404)
        # Missing draft under an existing project.
        self.assertEqual(
            client.delete(
                f"/projects/{project_a['id']}/drafts/nope"
            ).status_code,
            404,
        )
        # Cross-project draft.
        self.assertEqual(
            client.delete(
                f"/projects/{project_b['id']}/drafts/{draft_a['id']}"
            ).status_code,
            404,
        )

    def test_version_list_and_detail_read_back_saved_content(self):
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        base = f"/projects/{project['id']}/drafts/{draft['id']}/versions"
        raw_text = "# Chapter 1\n\nOpening line.\n\n---\n\nNext scene."
        v1 = client.post(
            base, json={"raw_text": raw_text, "idempotency_key": "save-1"}
        ).json()
        v2 = client.post(
            base, json={"raw_text": "second", "idempotency_key": "save-2"}
        ).json()

        listed = client.get(base).json()["versions"]
        detail = client.get(f"{base}/{v1['draft_version']['id']}")

        # Listed in version_number order, idempotency_key not leaked.
        self.assertEqual(
            [(v["version_number"], v["id"]) for v in listed],
            [(1, v1["draft_version"]["id"]), (2, v2["draft_version"]["id"])],
        )
        self.assertNotIn("idempotency_key", listed[0])
        # Detail reads back the exact persisted snapshot text and block text.
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["snapshot"]["raw_text"], raw_text)
        self.assertEqual(
            [b["text"] for b in body["blocks"]],
            ["# Chapter 1", "Opening line.", "---", "Next scene."],
        )
        # idempotency_key stays an internal token in the detail payload too.
        self.assertNotIn("idempotency_key", body["draft_version"])

    def test_get_missing_version_returns_404(self):
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()

        missing = client.get(
            f"/projects/{project['id']}/drafts/{draft['id']}/versions/nope"
        )
        missing_list = client.get(
            f"/projects/{project['id']}/drafts/nope/versions"
        )

        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing_list.status_code, 404)

    def test_get_version_cross_draft_returns_404(self):
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft_a = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        draft_b = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 2"}
        ).json()
        version = client.post(
            f"/projects/{project['id']}/drafts/{draft_a['id']}/versions",
            json={"raw_text": "body", "idempotency_key": "save-1"},
        ).json()["draft_version"]["id"]

        # Version belongs to draft A; requesting it under draft B must 404.
        cross = client.get(
            f"/projects/{project['id']}/drafts/{draft_b['id']}/versions/{version}"
        )

        self.assertEqual(cross.status_code, 404)

    def test_get_version_cross_project_returns_404(self):
        client = TestClient(create_app())
        project_a = client.post("/projects", json={"name": "A"}).json()
        project_b = client.post("/projects", json={"name": "B"}).json()
        draft_a = client.post(
            f"/projects/{project_a['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        draft_b = client.post(
            f"/projects/{project_b['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        version = client.post(
            f"/projects/{project_a['id']}/drafts/{draft_a['id']}/versions",
            json={"raw_text": "secret", "idempotency_key": "save-1"},
        ).json()["draft_version"]["id"]

        # Project A's version must not be readable through project B's context.
        cross = client.get(
            f"/projects/{project_b['id']}/drafts/{draft_b['id']}/versions/{version}"
        )

        self.assertEqual(cross.status_code, 404)

    def test_archived_project_and_draft_remain_listable_and_gettable(self):
        # SoT §113: archive preserves data; read stays allowed (writes blocked
        # elsewhere). Lock that archived entities are still listed/fetched.
        service = CoreSotService(InMemoryCoreSotRepository())
        client = TestClient(create_app(service))
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        service.archive_draft(project_id=project["id"], draft_id=draft["id"])
        service.archive_project(project_id=project["id"])

        got_project = client.get(f"/projects/{project['id']}")
        listed_projects = client.get("/projects").json()["projects"]
        got_draft = client.get(f"/projects/{project['id']}/drafts/{draft['id']}")
        listed_drafts = client.get(f"/projects/{project['id']}/drafts").json()["drafts"]

        self.assertEqual(got_project.status_code, 200)
        self.assertTrue(got_project.json()["archived"])
        self.assertIn(project["id"], [p["id"] for p in listed_projects])
        self.assertEqual(got_draft.status_code, 200)
        self.assertTrue(got_draft.json()["archived"])
        self.assertIn(draft["id"], [d["id"] for d in listed_drafts])

    def test_export_returns_selected_version_body_and_traceability(self):
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        base = f"/projects/{project['id']}/drafts/{draft['id']}/versions"
        raw_text = "# Chapter 1\n\nOpening line.\n\n---\n\nNext scene."
        saved = client.post(
            base, json={"raw_text": raw_text, "idempotency_key": "save-1"}
        ).json()
        version_id = saved["draft_version"]["id"]

        resp = client.get(f"{base}/{version_id}/export")

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["format"], "txt")
        self.assertEqual(body["body"], raw_text)
        self.assertEqual(body["version_id"], version_id)
        self.assertEqual(body["version_number"], 1)
        self.assertEqual(body["snapshot_id"], saved["snapshot"]["id"])
        self.assertTrue(body["filename"].endswith(".txt"))
        # AI metadata must not leak into an export payload's body.
        self.assertNotIn("---\nanalysis", body["body"])

    def test_export_markdown_format_query(self):
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        base = f"/projects/{project['id']}/drafts/{draft['id']}/versions"
        saved = client.post(
            base, json={"raw_text": "# H\n\nbody", "idempotency_key": "save-1"}
        ).json()
        version_id = saved["draft_version"]["id"]

        resp = client.get(f"{base}/{version_id}/export?format=markdown")

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["format"], "markdown")
        self.assertIn("text/markdown", body["content_type"])
        self.assertTrue(body["filename"].endswith(".md"))
        self.assertEqual(body["body"], "# H\n\nbody")

    def test_export_unsupported_format_returns_400(self):
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        base = f"/projects/{project['id']}/drafts/{draft['id']}/versions"
        saved = client.post(
            base, json={"raw_text": "body", "idempotency_key": "save-1"}
        ).json()
        version_id = saved["draft_version"]["id"]

        resp = client.get(f"{base}/{version_id}/export?format=pdf")

        self.assertEqual(resp.status_code, 400)

    def test_export_missing_version_returns_404(self):
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()

        resp = client.get(
            f"/projects/{project['id']}/drafts/{draft['id']}/versions/nope/export"
        )

        self.assertEqual(resp.status_code, 404)

    def test_export_cross_project_returns_404(self):
        client = TestClient(create_app())
        project_a = client.post("/projects", json={"name": "A"}).json()
        project_b = client.post("/projects", json={"name": "B"}).json()
        draft_a = client.post(
            f"/projects/{project_a['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        draft_b = client.post(
            f"/projects/{project_b['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        version_id = client.post(
            f"/projects/{project_a['id']}/drafts/{draft_a['id']}/versions",
            json={"raw_text": "secret", "idempotency_key": "save-1"},
        ).json()["draft_version"]["id"]

        # Project A's version must not be exportable through project B's context.
        resp = client.get(
            f"/projects/{project_b['id']}/drafts/{draft_b['id']}"
            f"/versions/{version_id}/export"
        )

        self.assertEqual(resp.status_code, 404)

    def test_export_survives_draft_and_project_archive(self):
        # SoT archive read-allowed policy (v1.5): archiving blocks writes but not
        # reads, and export is a read. Pin the export endpoint directly for both
        # draft archive and project archive (the service-level domain test only
        # covers project archive).
        service = CoreSotService(InMemoryCoreSotRepository())
        client = TestClient(create_app(service))
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        base = f"/projects/{project['id']}/drafts/{draft['id']}/versions"
        version_id = client.post(
            base, json={"raw_text": "archived body", "idempotency_key": "save-1"},
        ).json()["draft_version"]["id"]

        # Archive the draft, then the project; export must stay 200 each time.
        client.delete(f"/projects/{project['id']}/drafts/{draft['id']}")
        after_draft_archive = client.get(f"{base}/{version_id}/export")
        client.delete(f"/projects/{project['id']}")
        after_project_archive = client.get(f"{base}/{version_id}/export")

        self.assertEqual(after_draft_archive.status_code, 200)
        self.assertEqual(after_draft_archive.json()["body"], "archived body")
        self.assertEqual(after_project_archive.status_code, 200)
        self.assertEqual(after_project_archive.json()["body"], "archived body")

    def test_export_missing_project_returns_404(self):
        client = TestClient(create_app())

        resp = client.get(
            "/projects/nope/drafts/also-nope/versions/whatever/export"
        )

        self.assertEqual(resp.status_code, 404)

    def test_source_ref_create_list_get_round_trip(self):
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        raw_text = "민아는 파란 편지를 발견했다.\n\n다음 문단."
        saved = client.post(
            f"/projects/{project['id']}/drafts/{draft['id']}/versions",
            json={"raw_text": raw_text, "idempotency_key": "save-1"},
        ).json()
        quote = "파란 편지"
        start = raw_text.index(quote)
        end = start + len(quote)
        base = f"/projects/{project['id']}/snapshots/{saved['snapshot']['id']}"

        created = client.post(
            f"{base}/source-refs",
            json={"start_offset": start, "end_offset": end},
        )
        listed = client.get(f"{base}/source-refs")
        fetched = client.get(
            f"/projects/{project['id']}/source-refs/{created.json()['id']}"
        )

        self.assertEqual(created.status_code, 200)
        body = created.json()
        self.assertEqual(body["project_id"], project["id"])
        self.assertEqual(body["snapshot_id"], saved["snapshot"]["id"])
        self.assertEqual(body["block_id"], saved["blocks"][0]["id"])
        self.assertEqual(body["start_offset"], start)
        self.assertEqual(body["end_offset"], end)
        self.assertEqual(body["quote"], quote)
        self.assertEqual(body["content_hash"], saved["snapshot"]["content_hash"])
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["source_refs"], [body])
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json(), body)

    def test_source_ref_api_rejects_invalid_span_and_cross_project(self):
        client = TestClient(create_app())
        project_a = client.post("/projects", json={"name": "A"}).json()
        project_b = client.post("/projects", json={"name": "B"}).json()
        draft_a = client.post(
            f"/projects/{project_a['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        raw_text = "민아는 파란 편지를 발견했다."
        saved = client.post(
            f"/projects/{project_a['id']}/drafts/{draft_a['id']}/versions",
            json={"raw_text": raw_text, "idempotency_key": "save-1"},
        ).json()
        snapshot_id = saved["snapshot"]["id"]
        ref = client.post(
            f"/projects/{project_a['id']}/snapshots/{snapshot_id}/source-refs",
            json={"start_offset": 0, "end_offset": 2},
        ).json()

        invalid = client.post(
            f"/projects/{project_a['id']}/snapshots/{snapshot_id}/source-refs",
            json={"start_offset": 2, "end_offset": 2},
        )
        cross_create = client.post(
            f"/projects/{project_b['id']}/snapshots/{snapshot_id}/source-refs",
            json={"start_offset": 0, "end_offset": 2},
        )
        missing_list = client.get(
            f"/projects/{project_a['id']}/snapshots/nope/source-refs"
        )
        cross_get = client.get(
            f"/projects/{project_b['id']}/source-refs/{ref['id']}"
        )

        # should fire: malformed spans are rejected at the public API boundary.
        self.assertEqual(invalid.status_code, 400)
        # should NOT fire: project B cannot create/list/read project A anchors.
        self.assertEqual(cross_create.status_code, 404)
        self.assertEqual(missing_list.status_code, 404)
        self.assertEqual(cross_get.status_code, 404)

    def test_source_ref_api_survives_project_archive(self):
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        raw_text = "민아는 파란 편지를 발견했다."
        saved = client.post(
            f"/projects/{project['id']}/drafts/{draft['id']}/versions",
            json={"raw_text": raw_text, "idempotency_key": "save-1"},
        ).json()
        snapshot_id = saved["snapshot"]["id"]
        client.delete(f"/projects/{project['id']}")

        created = client.post(
            f"/projects/{project['id']}/snapshots/{snapshot_id}/source-refs",
            json={"start_offset": 0, "end_offset": 2},
        )
        listed = client.get(
            f"/projects/{project['id']}/snapshots/{snapshot_id}/source-refs"
        )
        fetched = client.get(
            f"/projects/{project['id']}/source-refs/{created.json()['id']}"
        )

        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["quote"], "민아")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            [ref["id"] for ref in listed.json()["source_refs"]],
            [created.json()["id"]],
        )
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json(), created.json())

    def test_source_block_index_rebuild_endpoint_returns_fake_adapter_summary(self):
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        saved = client.post(
            f"/projects/{project['id']}/drafts/{draft['id']}/versions",
            json={
                "raw_text": "민아는 파란 편지를 발견했다.\n\n준호는 지도를 접었다.",
                "idempotency_key": "save-1",
            },
        ).json()

        response = client.post(
            f"/projects/{project['id']}/snapshots/{saved['snapshot']['id']}"
            "/index/source-blocks/rebuild"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "project_id": project["id"],
                "snapshot_id": saved["snapshot"]["id"],
                "target": "vector",
                "backend": "in_memory_fake",
                "records_attempted": 2,
                "records_written": 2,
                "records_indexed": 2,
                "records_query_visible": 2,
                "records_archived": 0,
            },
        )

    def test_source_block_index_rebuild_filters_archived_project_records(self):
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        saved = client.post(
            f"/projects/{project['id']}/drafts/{draft['id']}/versions",
            json={"raw_text": "문장 하나.\n\n문장 둘.", "idempotency_key": "save-1"},
        ).json()
        client.delete(f"/projects/{project['id']}")

        response = client.post(
            f"/projects/{project['id']}/snapshots/{saved['snapshot']['id']}"
            "/index/source-blocks/rebuild"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["records_indexed"], 2)
        self.assertEqual(response.json()["records_query_visible"], 0)
        self.assertEqual(response.json()["records_archived"], 2)

    def test_source_block_index_rebuild_rejects_missing_and_cross_project_snapshot(self):
        client = TestClient(create_app())
        project_a = client.post("/projects", json={"name": "A"}).json()
        project_b = client.post("/projects", json={"name": "B"}).json()
        draft_a = client.post(
            f"/projects/{project_a['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        saved = client.post(
            f"/projects/{project_a['id']}/drafts/{draft_a['id']}/versions",
            json={"raw_text": "문장 하나.", "idempotency_key": "save-1"},
        ).json()

        missing = client.post(
            f"/projects/{project_a['id']}/snapshots/nope/index/source-blocks/rebuild"
        )
        cross_project = client.post(
            f"/projects/{project_b['id']}/snapshots/{saved['snapshot']['id']}"
            "/index/source-blocks/rebuild"
        )

        self.assertEqual(missing.status_code, 404)
        self.assertEqual(cross_project.status_code, 404)

    def test_analysis_job_create_get_and_idempotent_replay(self):
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        analysis = AnalysisService(InMemoryAnalysisRepository())
        client = TestClient(create_app(core_sot, analysis_service=analysis))
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        version = client.post(
            f"/projects/{project['id']}/drafts/{draft['id']}/versions",
            json={"raw_text": "Opening line.", "idempotency_key": "save-1"},
        ).json()
        request = {
            "snapshot_id": version["snapshot"]["id"],
            "idempotency_key": "analysis-run-1",
        }

        first = client.post(
            f"/projects/{project['id']}/analysis/jobs", json=request
        )
        replay = client.post(
            f"/projects/{project['id']}/analysis/jobs", json=request
        )
        fetched = client.get(
            f"/projects/{project['id']}/analysis/jobs/{first.json()['job']['id']}"
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertFalse(first.json()["idempotent_replay"])
        self.assertTrue(replay.json()["idempotent_replay"])
        self.assertEqual(replay.json()["job"]["id"], first.json()["job"]["id"])
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["status"], "pending")
        self.assertIsNone(fetched.json()["failure_reason"])

    def test_analysis_candidates_read_back_and_project_isolation(self):
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        analysis = AnalysisService(InMemoryAnalysisRepository())
        client = TestClient(create_app(core_sot, analysis_service=analysis))
        project_a = client.post("/projects", json={"name": "A"}).json()
        project_b = client.post("/projects", json={"name": "B"}).json()
        job = analysis.create_job(
            project_id=project_a["id"],
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        ).job
        task = analysis.create_task(
            project_id=project_a["id"],
            job_id=job.id,
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
        )
        saved = analysis.record_candidate(
            project_id=project_a["id"],
            task_id=task.id,
            logical_key="candidate-1",
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
            action=AnalysisCandidateAction.CREATE,
            provenance=AnalysisProvenance.SOURCE_OBSERVED,
            confidence=0.75,
            source_ref_ids=("source-ref-1",),
            payload={"name": "Mina", "observation": "Keeps a hidden notebook."},
        ).candidate

        listed = client.get(
            f"/projects/{project_a['id']}/analysis/jobs/{job.id}/candidates"
        )
        cross_project_job = client.get(
            f"/projects/{project_b['id']}/analysis/jobs/{job.id}"
        )
        cross_project_candidates = client.get(
            f"/projects/{project_b['id']}/analysis/jobs/{job.id}/candidates"
        )

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["candidates"]), 1)
        candidate = listed.json()["candidates"][0]
        self.assertEqual(candidate["id"], saved.id)
        self.assertEqual(candidate["candidate_type"], "character_observation")
        self.assertEqual(candidate["status"], "needs_review")
        self.assertEqual(candidate["source_ref_ids"], ["source-ref-1"])
        self.assertEqual(
            candidate["payload"],
            {"name": "Mina", "observation": "Keeps a hidden notebook."},
        )
        # should NOT fire: project B must not read project A's analysis job.
        self.assertEqual(cross_project_job.status_code, 404)
        self.assertEqual(cross_project_candidates.status_code, 404)

    def test_analysis_job_missing_project_returns_404(self):
        client = TestClient(create_app())

        created = client.post(
            "/projects/nope/analysis/jobs",
            json={"snapshot_id": "snapshot-1", "idempotency_key": "analysis-run-1"},
        )
        fetched = client.get("/projects/nope/analysis/jobs/analysis-job-1")
        candidates = client.get(
            "/projects/nope/analysis/jobs/analysis-job-1/candidates"
        )

        self.assertEqual(created.status_code, 404)
        self.assertEqual(fetched.status_code, 404)
        self.assertEqual(candidates.status_code, 404)

    def test_analysis_missing_job_under_existing_project_returns_404(self):
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()

        fetched = client.get(
            f"/projects/{project['id']}/analysis/jobs/analysis-job-nope"
        )
        candidates = client.get(
            f"/projects/{project['id']}/analysis/jobs/analysis-job-nope/candidates"
        )

        self.assertEqual(fetched.status_code, 404)
        self.assertEqual(candidates.status_code, 404)

    def test_analysis_run_endpoint_executes_pending_job_with_injected_runner(self):
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        analysis = AnalysisService(InMemoryAnalysisRepository())
        runner = _ApiFakeAnalysisRunner(analysis)
        client = TestClient(
            create_app(core_sot, analysis_service=analysis, analysis_runner=runner)
        )
        project = client.post("/projects", json={"name": "Novel"}).json()
        created = client.post(
            f"/projects/{project['id']}/analysis/jobs",
            json={"snapshot_id": "snapshot-1", "idempotency_key": "analysis-run-1"},
        ).json()

        response = client.post(
            f"/projects/{project['id']}/analysis/jobs/{created['job']['id']}/run"
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["idempotent_replay"])
        self.assertEqual(body["job"]["status"], "succeeded")
        self.assertEqual(len(body["candidates"]), 1)
        self.assertEqual(
            body["candidates"][0]["candidate_type"],
            "character_observation",
        )
        self.assertEqual(runner.calls, [created["job"]["id"]])
        self.assertEqual(
            client.get(
                f"/projects/{project['id']}/analysis/jobs/{created['job']['id']}/candidates"
            ).json()["candidates"][0]["id"],
            body["candidates"][0]["id"],
        )

    def test_analysis_run_endpoint_uses_env_configured_default_runner(self):
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        client = TestClient(create_app(core_sot))
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts",
            json={"title": "Episode 1"},
        ).json()
        version = client.post(
            f"/projects/{project['id']}/drafts/{draft['id']}/versions",
            json={
                "raw_text": "Mina finds a hidden notebook.",
                "idempotency_key": "save-1",
            },
        ).json()["draft_version"]
        source_ref = core_sot.create_source_ref(
            project_id=project["id"],
            snapshot_id=version["snapshot_id"],
            start_offset=0,
            end_offset=4,
        )
        provider = FakeLLMProvider(
            (
                GenerationResult(
                    model="test-model",
                    finish_reason="stop",
                    content=json.dumps(
                        {
                            "candidates": [
                                {
                                    "candidate_type": "character_observation",
                                    "provenance": "source_observed",
                                    "confidence": 0.9,
                                    "source_anchors": [
                                        {
                                            "source_ref_id": source_ref.id,
                                            "start_offset": source_ref.start_offset,
                                            "end_offset": source_ref.end_offset,
                                            "quote": source_ref.quote,
                                            "content_hash": source_ref.content_hash,
                                        }
                                    ],
                                    "payload": {
                                        "name": "Mina",
                                        "observation": "Mina finds a hidden notebook.",
                                    },
                                }
                            ]
                        }
                    ),
                ),
            )
        )

        with patch.dict(
            os.environ,
            {
                "LLM_GATEWAY_BASE_URL": "http://gateway.test",
                "LLM_GATEWAY_MODEL": "",
                "CORE_SOT_MONGO_URI": "",
            },
        ), patch(
            "services.application.app.main.GatewayGenerateProvider",
            return_value=provider,
        ) as provider_factory:
            client = TestClient(create_app(core_sot))
            job = client.post(
                f"/projects/{project['id']}/analysis/jobs",
                json={
                    "snapshot_id": version["snapshot_id"],
                    "idempotency_key": "analysis-run-1",
                },
            ).json()["job"]

            response = client.post(
                f"/projects/{project['id']}/analysis/jobs/{job['id']}/run"
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["idempotent_replay"])
        self.assertEqual(body["job"]["status"], "succeeded")
        self.assertEqual(body["candidates"][0]["source_ref_ids"], [source_ref.id])
        self.assertEqual(
            body["candidates"][0]["payload"],
            {"name": "Mina", "observation": "Mina finds a hidden notebook."},
        )
        self.assertEqual(len(provider.requests), 1)
        self.assertEqual(provider.requests[0].model, None)
        # create_app now builds a gateway provider for both the analysis runner
        # and the context search planner; assert the env config drives the
        # construction rather than pinning the exact consumer count.
        provider_factory.assert_called_with(
            base_url="http://gateway.test",
            timeout_seconds=120.0,
            trust_env=False,
        )
        fetched = client.get(
            f"/projects/{project['id']}/analysis/jobs/{job['id']}/candidates"
        )
        self.assertEqual(
            fetched.json()["candidates"][0]["id"],
            body["candidates"][0]["id"],
        )

    def test_analysis_run_endpoint_replays_terminal_and_running_without_runner(self):
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        analysis = AnalysisService(InMemoryAnalysisRepository())
        client = TestClient(create_app(core_sot, analysis_service=analysis))
        project = client.post("/projects", json={"name": "Novel"}).json()
        succeeded = analysis.create_job(
            project_id=project["id"],
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        ).job
        analysis.mark_job_running(project_id=project["id"], job_id=succeeded.id)
        analysis.mark_job_succeeded(project_id=project["id"], job_id=succeeded.id)
        running = analysis.create_job(
            project_id=project["id"],
            snapshot_id="snapshot-2",
            idempotency_key="analysis-run-2",
        ).job
        analysis.mark_job_running(project_id=project["id"], job_id=running.id)
        failed = analysis.create_job(
            project_id=project["id"],
            snapshot_id="snapshot-3",
            idempotency_key="analysis-run-3",
        ).job
        analysis.mark_job_running(project_id=project["id"], job_id=failed.id)
        analysis.mark_job_failed(
            project_id=project["id"],
            job_id=failed.id,
            failure_reason=AnalysisJobFailureReason.PROVIDER_ERROR,
            failure_detail="gateway down",
        )

        succeeded_replay = client.post(
            f"/projects/{project['id']}/analysis/jobs/{succeeded.id}/run"
        )
        running_replay = client.post(
            f"/projects/{project['id']}/analysis/jobs/{running.id}/run"
        )
        failed_replay = client.post(
            f"/projects/{project['id']}/analysis/jobs/{failed.id}/run"
        )

        self.assertEqual(succeeded_replay.status_code, 200)
        self.assertTrue(succeeded_replay.json()["idempotent_replay"])
        self.assertEqual(succeeded_replay.json()["job"]["status"], "succeeded")
        self.assertEqual(running_replay.status_code, 200)
        self.assertTrue(running_replay.json()["idempotent_replay"])
        self.assertEqual(running_replay.json()["job"]["status"], "running")
        self.assertEqual(failed_replay.status_code, 200)
        self.assertTrue(failed_replay.json()["idempotent_replay"])
        self.assertEqual(failed_replay.json()["job"]["status"], "failed")
        self.assertEqual(
            failed_replay.json()["job"]["failure_reason"],
            "provider_error",
        )

    def test_analysis_retry_endpoint_resets_only_failed_job_in_place(self):
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        analysis = AnalysisService(InMemoryAnalysisRepository())
        client = TestClient(create_app(core_sot, analysis_service=analysis))
        project = client.post("/projects", json={"name": "Novel"}).json()
        job = analysis.create_job(
            project_id=project["id"],
            snapshot_id="snapshot-1",
            idempotency_key="analyze:snapshot-1",
        ).job
        analysis.mark_job_running(project_id=project["id"], job_id=job.id)
        analysis.mark_job_failed(
            project_id=project["id"],
            job_id=job.id,
            failure_reason=AnalysisJobFailureReason.SOURCE_INVALID,
            failure_detail="source_ref not found",
        )

        response = client.post(
            f"/projects/{project['id']}/analysis/jobs/{job.id}/retry"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], job.id)
        self.assertEqual(response.json()["status"], "pending")
        self.assertIsNone(response.json()["failure_reason"])
        self.assertIsNone(response.json()["failure_detail"])

    def test_analysis_retry_endpoint_rejects_non_failed_and_cross_project(self):
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        analysis = AnalysisService(InMemoryAnalysisRepository())
        client = TestClient(create_app(core_sot, analysis_service=analysis))
        project_a = client.post("/projects", json={"name": "A"}).json()
        project_b = client.post("/projects", json={"name": "B"}).json()
        pending = analysis.create_job(
            project_id=project_a["id"],
            snapshot_id="snapshot-1",
            idempotency_key="analyze:snapshot-1",
        ).job

        non_failed = client.post(
            f"/projects/{project_a['id']}/analysis/jobs/{pending.id}/retry"
        )
        cross_project = client.post(
            f"/projects/{project_b['id']}/analysis/jobs/{pending.id}/retry"
        )
        missing = client.post(
            f"/projects/{project_a['id']}/analysis/jobs/nope/retry"
        )

        self.assertEqual(non_failed.status_code, 409)
        self.assertEqual(cross_project.status_code, 404)
        self.assertEqual(missing.status_code, 404)

    def test_analysis_run_endpoint_missing_and_cross_project_returns_404(self):
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        analysis = AnalysisService(InMemoryAnalysisRepository())
        runner = _ApiFakeAnalysisRunner(analysis)
        client = TestClient(
            create_app(core_sot, analysis_service=analysis, analysis_runner=runner)
        )
        project_a = client.post("/projects", json={"name": "A"}).json()
        project_b = client.post("/projects", json={"name": "B"}).json()
        job = analysis.create_job(
            project_id=project_a["id"],
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        ).job

        missing_project = client.post(
            f"/projects/nope/analysis/jobs/{job.id}/run"
        )
        missing_job = client.post(
            f"/projects/{project_a['id']}/analysis/jobs/nope/run"
        )
        cross_project = client.post(
            f"/projects/{project_b['id']}/analysis/jobs/{job.id}/run"
        )

        self.assertEqual(missing_project.status_code, 404)
        self.assertEqual(missing_job.status_code, 404)
        self.assertEqual(cross_project.status_code, 404)

    def test_analysis_run_endpoint_preserves_failed_job_on_runner_error(self):
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        analysis = AnalysisService(InMemoryAnalysisRepository())
        client = TestClient(
            create_app(
                core_sot,
                analysis_service=analysis,
                analysis_runner=_ApiFailingAnalysisRunner(analysis),
            )
        )
        project = client.post("/projects", json={"name": "Novel"}).json()
        job = analysis.create_job(
            project_id=project["id"],
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        ).job

        failed = client.post(f"/projects/{project['id']}/analysis/jobs/{job.id}/run")
        fetched = client.get(f"/projects/{project['id']}/analysis/jobs/{job.id}")

        self.assertEqual(failed.status_code, 400)
        self.assertEqual(fetched.json()["status"], "failed")
        self.assertEqual(fetched.json()["failure_reason"], "schema_invalid")

    def test_analysis_run_endpoint_maps_duplicate_conflict_to_409(self):
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        analysis = AnalysisService(InMemoryAnalysisRepository())
        client = TestClient(
            create_app(
                core_sot,
                analysis_service=analysis,
                analysis_runner=_ApiDuplicateConflictRunner(analysis),
            )
        )
        project = client.post("/projects", json={"name": "Novel"}).json()
        job = analysis.create_job(
            project_id=project["id"],
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        ).job

        failed = client.post(f"/projects/{project['id']}/analysis/jobs/{job.id}/run")
        fetched = client.get(f"/projects/{project['id']}/analysis/jobs/{job.id}")

        self.assertEqual(failed.status_code, 409)
        self.assertEqual(fetched.json()["status"], "failed")
        self.assertEqual(fetched.json()["failure_reason"], "duplicate_conflict")

    def test_analysis_run_endpoint_maps_provider_exception_to_502(self):
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        analysis = AnalysisService(InMemoryAnalysisRepository())
        client = TestClient(
            create_app(
                core_sot,
                analysis_service=analysis,
                analysis_runner=_ApiProviderErrorRunner(analysis),
            )
        )
        project = client.post("/projects", json={"name": "Novel"}).json()
        job = analysis.create_job(
            project_id=project["id"],
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        ).job

        failed = client.post(f"/projects/{project['id']}/analysis/jobs/{job.id}/run")
        fetched = client.get(f"/projects/{project['id']}/analysis/jobs/{job.id}")

        self.assertEqual(failed.status_code, 502)
        self.assertEqual(fetched.json()["status"], "failed")
        self.assertEqual(fetched.json()["failure_reason"], "provider_error")

    def test_analysis_run_endpoint_maps_real_provider_error_to_502(self):
        # Tracked debt #8 lock: a real Gateway ProviderError re-raised by the
        # runner (not just a generic RuntimeError) hits the endpoint's explicit
        # ``except ProviderError`` branch → 502, and the job stays failed with
        # failure_reason=provider_error. Under-strict: removing both the
        # explicit branch and the generic catch re-fails this via an unhandled
        # 500.
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        analysis = AnalysisService(InMemoryAnalysisRepository())
        client = TestClient(
            create_app(
                core_sot,
                analysis_service=analysis,
                analysis_runner=_ApiRealProviderErrorRunner(analysis),
            )
        )
        project = client.post("/projects", json={"name": "Novel"}).json()
        job = analysis.create_job(
            project_id=project["id"],
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        ).job

        failed = client.post(f"/projects/{project['id']}/analysis/jobs/{job.id}/run")
        fetched = client.get(f"/projects/{project['id']}/analysis/jobs/{job.id}")

        self.assertEqual(failed.status_code, 502)
        self.assertEqual(fetched.json()["status"], "failed")
        self.assertEqual(fetched.json()["failure_reason"], "provider_error")

    def test_analysis_run_endpoint_maps_snapshot_not_found_to_404(self):
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        analysis = AnalysisService(InMemoryAnalysisRepository())
        client = TestClient(
            create_app(
                core_sot,
                analysis_service=analysis,
                analysis_runner=_ApiSnapshotNotFoundRunner(analysis),
            )
        )
        project = client.post("/projects", json={"name": "Novel"}).json()
        job = analysis.create_job(
            project_id=project["id"],
            snapshot_id="missing-snapshot",
            idempotency_key="analysis-run-1",
        ).job

        failed = client.post(f"/projects/{project['id']}/analysis/jobs/{job.id}/run")
        fetched = client.get(f"/projects/{project['id']}/analysis/jobs/{job.id}")

        self.assertEqual(failed.status_code, 404)
        self.assertEqual(fetched.json()["status"], "failed")
        self.assertEqual(fetched.json()["failure_reason"], "snapshot_not_found")

    def test_analysis_run_endpoint_pending_without_runner_returns_503(self):
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()
        job = client.post(
            f"/projects/{project['id']}/analysis/jobs",
            json={"snapshot_id": "snapshot-1", "idempotency_key": "analysis-run-1"},
        ).json()["job"]

        response = client.post(f"/projects/{project['id']}/analysis/jobs/{job['id']}/run")

        self.assertEqual(response.status_code, 503)


class SpineEnvelopeKeyTest(unittest.TestCase):
    """Exact-key locks on the Product shell spine envelopes (SoT v1.6.95).

    ``response_model`` silently drops any field the model does not declare, so a
    model that is narrower than its payload would delete fields from the public
    envelope with no error. The per-key assertions elsewhere in this module do
    not catch that: they only read the keys they care about. These tests pin the
    complete key set of every spine response, so a too-narrow model bites here.

    Note the same key name carries different shapes per endpoint: ``save_draft``
    returns a narrow ``draft_version``/``snapshot``/``blocks`` while
    ``get_draft_version`` returns the wide read surface. They must not share a
    model, and these tests are what enforces that.
    """

    def setUp(self):
        self.client = TestClient(create_app())
        self.project = self.client.post("/projects", json={"name": "Novel"}).json()
        self.draft = self.client.post(
            f"/projects/{self.project['id']}/drafts",
            json={"title": "Episode 1"},
        ).json()
        self.saved = self.client.post(
            f"/projects/{self.project['id']}/drafts/{self.draft['id']}/versions",
            json={"raw_text": "# Title\n\nBody.", "idempotency_key": "save-1"},
        ).json()

    def _version_id(self) -> str:
        return self.saved["draft_version"]["id"]

    def test_project_payload_keys(self):
        expected = {"id", "name", "archived"}

        self.assertEqual(set(self.project), expected)
        self.assertEqual(
            set(self.client.get(f"/projects/{self.project['id']}").json()), expected
        )
        listed = self.client.get("/projects").json()
        self.assertEqual(set(listed), {"projects"})
        self.assertEqual(set(listed["projects"][0]), expected)
        self.assertEqual(
            set(
                self.client.patch(
                    f"/projects/{self.project['id']}", json={"name": "Renamed"}
                ).json()
            ),
            expected,
        )
        self.assertEqual(
            set(self.client.delete(f"/projects/{self.project['id']}").json()), expected
        )

    def test_draft_payload_keys(self):
        expected = {
            "id",
            "project_id",
            "title",
            "archived",
            "unit_kind",
            "position",
        }

        self.assertEqual(set(self.draft), expected)
        self.assertEqual(
            set(
                self.client.get(
                    f"/projects/{self.project['id']}/drafts/{self.draft['id']}"
                ).json()
            ),
            expected,
        )
        listed = self.client.get(f"/projects/{self.project['id']}/drafts").json()
        self.assertEqual(set(listed), {"drafts"})
        self.assertEqual(set(listed["drafts"][0]), expected)
        self.assertEqual(
            set(
                self.client.patch(
                    f"/projects/{self.project['id']}/drafts/{self.draft['id']}",
                    json={"title": "Renamed"},
                ).json()
            ),
            expected,
        )
        self.assertEqual(
            set(
                self.client.delete(
                    f"/projects/{self.project['id']}/drafts/{self.draft['id']}"
                ).json()
            ),
            expected,
        )

    def test_save_draft_envelope_keys_are_the_narrow_save_surface(self):
        self.assertEqual(
            set(self.saved),
            {"draft_version", "snapshot", "blocks", "idempotent_replay"},
        )
        # Narrower than the read surface on purpose: no project_id/draft_id here.
        self.assertEqual(
            set(self.saved["draft_version"]), {"id", "version_number", "snapshot_id"}
        )
        self.assertEqual(set(self.saved["snapshot"]), {"id", "content_hash"})
        self.assertEqual(
            set(self.saved["blocks"][0]),
            {"id", "kind", "start_offset", "end_offset"},
        )

    def test_version_list_and_detail_envelope_keys(self):
        listed = self.client.get(
            f"/projects/{self.project['id']}/drafts/{self.draft['id']}/versions"
        ).json()
        self.assertEqual(set(listed), {"versions"})
        # idempotency_key stays out of the public read surface.
        self.assertEqual(
            set(listed["versions"][0]),
            {"id", "project_id", "draft_id", "version_number", "snapshot_id"},
        )

        detail = self.client.get(
            f"/projects/{self.project['id']}/drafts/{self.draft['id']}"
            f"/versions/{self._version_id()}"
        ).json()
        self.assertEqual(set(detail), {"draft_version", "snapshot", "blocks"})
        self.assertEqual(
            set(detail["draft_version"]),
            {"id", "project_id", "draft_id", "version_number", "snapshot_id"},
        )
        self.assertEqual(
            set(detail["snapshot"]),
            {
                "id",
                "project_id",
                "draft_id",
                "version_id",
                "raw_text",
                "content_hash",
            },
        )
        self.assertEqual(
            set(detail["blocks"][0]),
            {
                "id",
                "project_id",
                "snapshot_id",
                "block_index",
                "kind",
                "start_offset",
                "end_offset",
                "text",
            },
        )

    def test_export_envelope_keys(self):
        export = self.client.get(
            f"/projects/{self.project['id']}/drafts/{self.draft['id']}"
            f"/versions/{self._version_id()}/export?format=markdown"
        ).json()

        self.assertEqual(
            set(export),
            {
                "format",
                "filename",
                "content_type",
                "body",
                "project_id",
                "draft_id",
                "version_id",
                "version_number",
                "snapshot_id",
                "content_hash",
            },
        )


class ProjectExportApiTest(unittest.TestCase):
    """Whole-project export HTTP contract (W4, D6=A, SoT v1.7.17).

    The on-request delivery manifest lives entirely at this HTTP boundary: the
    service always computes the ordered units, but the ``manifest`` query flag
    decides whether the response carries the traceability manifest or ``null``.
    """

    def setUp(self):
        self.client = TestClient(create_app())
        self.project = self.client.post("/projects", json={"name": "Novel"}).json()
        self.d1 = self.client.post(
            f"/projects/{self.project['id']}/drafts",
            json={"title": "1장", "unit_kind": "chapter"},
        ).json()
        self.d2 = self.client.post(
            f"/projects/{self.project['id']}/drafts",
            json={"title": "2장", "unit_kind": "chapter"},
        ).json()
        self.saved1 = self.client.post(
            f"/projects/{self.project['id']}/drafts/{self.d1['id']}/versions",
            json={"raw_text": "first", "idempotency_key": "d1-save"},
        ).json()
        self.saved2 = self.client.post(
            f"/projects/{self.project['id']}/drafts/{self.d2['id']}/versions",
            json={"raw_text": "second", "idempotency_key": "d2-save"},
        ).json()

    def test_manifest_records_traceability_for_included_units(self):
        # EX-08 (fire): manifest lists project/unit/version/snapshot/hash in the
        # exact order the bodies were joined.
        resp = self.client.get(
            f"/projects/{self.project['id']}/export?format=markdown&manifest=true"
        )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["body"], "# 1장\n\nfirst\n\n# 2장\n\nsecond")
        manifest = body["manifest"]
        self.assertEqual(manifest["project_id"], self.project["id"])
        self.assertEqual(manifest["format"], "markdown")
        self.assertEqual(manifest["include_archived"], False)
        self.assertEqual(
            [u["draft_id"] for u in manifest["units"]],
            [self.d1["id"], self.d2["id"]],
        )
        self.assertEqual(
            manifest["units"][0],
            {
                "draft_id": self.d1["id"],
                "title": "1장",
                "unit_kind": "chapter",
                "position": 1,
                "version_id": self.saved1["draft_version"]["id"],
                "version_number": 1,
                "snapshot_id": self.saved1["snapshot"]["id"],
                "content_hash": self.saved1["snapshot"]["content_hash"],
            },
        )

    def test_manifest_omitted_unless_requested(self):
        # EX-09 (not fire): without the flag, manifest must be null, never a
        # populated object leaking on every export.
        resp = self.client.get(f"/projects/{self.project['id']}/export")

        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["manifest"])

    def test_include_archived_flag_over_http(self):
        # EX-03 mirror at HTTP: default excludes archived, opt-in includes it.
        self.client.delete(
            f"/projects/{self.project['id']}/drafts/{self.d1['id']}"
        )

        default = self.client.get(
            f"/projects/{self.project['id']}/export"
        ).json()
        opted_in = self.client.get(
            f"/projects/{self.project['id']}/export?include_archived=true"
        ).json()

        self.assertEqual(default["body"], "2장\n\nsecond")
        self.assertEqual(default["include_archived"], False)
        self.assertEqual(opted_in["body"], "1장\n\nfirst\n\n2장\n\nsecond")
        self.assertEqual(opted_in["include_archived"], True)

    def test_unsupported_format_and_missing_project_rejected(self):
        # EX-10 (not fire): bad format 400, missing project 404.
        self.assertEqual(
            self.client.get(
                f"/projects/{self.project['id']}/export?format=pdf"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get("/projects/nope/export").status_code, 404
        )

    def test_archived_project_export_survives(self):
        # EX-11 (not fire): archiving the project blocks writes, not reads.
        self.client.delete(f"/projects/{self.project['id']}")

        resp = self.client.get(f"/projects/{self.project['id']}/export")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["body"], "1장\n\nfirst\n\n2장\n\nsecond")

    def test_export_response_exact_keys(self):
        # EX-12 (fire): lock the exact top-level envelope keys so a future
        # response_model change cannot silently drop or add a field.
        body = self.client.get(
            f"/projects/{self.project['id']}/export?manifest=true"
        ).json()

        self.assertEqual(
            set(body),
            {
                "format",
                "filename",
                "content_type",
                "body",
                "project_id",
                "include_archived",
                "manifest",
            },
        )
        self.assertEqual(
            set(body["manifest"]),
            {"project_id", "format", "include_archived", "units"},
        )
        self.assertEqual(
            set(body["manifest"]["units"][0]),
            {
                "draft_id",
                "title",
                "unit_kind",
                "position",
                "version_id",
                "version_number",
                "snapshot_id",
                "content_hash",
            },
        )


class BlankNameRejectionTest(unittest.TestCase):
    """Project/draft naming constraint at the HTTP boundary (SoT v1.6.95, D3=A).

    Before this, `create_project` accepted any string, so a blank name reached the
    canonical store. The frontend trimmed as a UX nicety, but that is not a
    contract: any other client bypassed it. Validation sits at the HTTP boundary
    because every client reaches Core SOT through it, so the Core SOT contract
    itself is unchanged.
    """

    def setUp(self):
        self.client = TestClient(create_app())
        self.project = self.client.post("/projects", json={"name": "Novel"}).json()
        self.draft = self.client.post(
            f"/projects/{self.project['id']}/drafts",
            json={"title": "Episode 1"},
        ).json()

    def test_blank_project_name_is_rejected(self):
        for name in ["", " ", "   ", "\t", "\n", " \t\n "]:
            with self.subTest(name=name):
                response = self.client.post("/projects", json={"name": name})

                self.assertEqual(response.status_code, 422)

    def test_blank_draft_title_is_rejected(self):
        for title in ["", "   ", "\n"]:
            with self.subTest(title=title):
                response = self.client.post(
                    f"/projects/{self.project['id']}/drafts", json={"title": title}
                )

                self.assertEqual(response.status_code, 422)

    def test_blank_rename_is_rejected_for_project_and_draft(self):
        self.assertEqual(
            self.client.patch(
                f"/projects/{self.project['id']}", json={"name": "  "}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.patch(
                f"/projects/{self.project['id']}/drafts/{self.draft['id']}",
                json={"title": "  "},
            ).status_code,
            422,
        )

    def test_blank_name_does_not_reach_the_store(self):
        # Over-strict on the boundary: a rejected create must mint nothing.
        before = len(self.client.get("/projects").json()["projects"])

        self.client.post("/projects", json={"name": "   "})

        self.assertEqual(
            len(self.client.get("/projects").json()["projects"]), before
        )

    def test_surrounding_whitespace_is_stripped_not_rejected(self):
        # Under-strict guard: the constraint must not reject a real name that
        # merely carries padding — it strips and stores the trimmed value.
        created = self.client.post("/projects", json={"name": "  겨울 이야기  "})

        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["name"], "겨울 이야기")

        draft = self.client.post(
            f"/projects/{self.project['id']}/drafts", json={"title": "  1화  "}
        )
        self.assertEqual(draft.status_code, 200)
        self.assertEqual(draft.json()["title"], "1화")

    def test_ordinary_names_still_pass(self):
        # Over-strict guard on the constraint itself: normal input is unaffected.
        for name in ["A", "겨울 이야기", "Episode 1: 시작", "a" * 200]:
            with self.subTest(name=name):
                response = self.client.post("/projects", json={"name": name})

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["name"], name)

    def test_inner_whitespace_is_preserved(self):
        # The constraint strips only the edges; it must not normalize the middle.
        response = self.client.post("/projects", json={"name": "겨울  이야기"})

        self.assertEqual(response.json()["name"], "겨울  이야기")


class _ApiFakeAnalysisRunner:
    def __init__(self, analysis_service):
        self._analysis_service = analysis_service
        self.calls = []

    async def run_job(self, *, project_id: str, job_id: str):
        self.calls.append(job_id)
        running = self._analysis_service.mark_job_running(
            project_id=project_id,
            job_id=job_id,
        )
        task = self._analysis_service.create_task(
            project_id=project_id,
            job_id=running.id,
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
        )
        recorded = self._analysis_service.record_candidate(
            project_id=project_id,
            task_id=task.id,
            logical_key="character:min-a",
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
            action=AnalysisCandidateAction.CREATE,
            provenance=AnalysisProvenance.SOURCE_OBSERVED,
            confidence=0.9,
            source_ref_ids=("source-ref-1",),
            payload={"name": "Mina", "observation": "Keeps a hidden notebook."},
        )
        succeeded = self._analysis_service.mark_job_succeeded(
            project_id=project_id,
            job_id=job_id,
        )
        return AnalysisExtractionRunResult(
            job=succeeded,
            candidates=(recorded.candidate,),
            job_idempotent_replay=False,
            candidate_idempotent_replays=(recorded.idempotent_replay,),
        )


class _ApiFailingAnalysisRunner:
    def __init__(self, analysis_service):
        self._analysis_service = analysis_service

    async def run_job(self, *, project_id: str, job_id: str):
        self._analysis_service.mark_job_running(project_id=project_id, job_id=job_id)
        error = InvalidAnalysisCandidate("bad candidate")
        self._analysis_service.mark_job_failed(
            project_id=project_id,
            job_id=job_id,
            failure_reason=AnalysisJobFailureReason.SCHEMA_INVALID,
            failure_detail=str(error),
        )
        raise error


class _ApiDuplicateConflictRunner:
    def __init__(self, analysis_service):
        self._analysis_service = analysis_service

    async def run_job(self, *, project_id: str, job_id: str):
        self._analysis_service.mark_job_running(project_id=project_id, job_id=job_id)
        error = DuplicateAnalysisCandidateRequest("duplicate candidate request")
        self._analysis_service.mark_job_failed(
            project_id=project_id,
            job_id=job_id,
            failure_reason=AnalysisJobFailureReason.DUPLICATE_CONFLICT,
            failure_detail=str(error),
        )
        raise error


class _ApiProviderErrorRunner:
    def __init__(self, analysis_service):
        self._analysis_service = analysis_service

    async def run_job(self, *, project_id: str, job_id: str):
        self._analysis_service.mark_job_running(project_id=project_id, job_id=job_id)
        error = RuntimeError("gateway down")
        self._analysis_service.mark_job_failed(
            project_id=project_id,
            job_id=job_id,
            failure_reason=AnalysisJobFailureReason.PROVIDER_ERROR,
            failure_detail=str(error),
        )
        raise error


class _ApiRealProviderErrorRunner:
    """Re-raises a real Gateway ``ProviderError`` (timeout/unavailable/5xx),
    matching AnalysisExtractionRunner.run_job which marks the job failed then
    re-raises the original provider exception."""

    def __init__(self, analysis_service):
        self._analysis_service = analysis_service

    async def run_job(self, *, project_id: str, job_id: str):
        self._analysis_service.mark_job_running(project_id=project_id, job_id=job_id)
        error = ProviderError(
            code=ProviderErrorCode.UNAVAILABLE,
            message="gateway is unavailable",
            retryable=True,
            provider="llm_gateway",
        )
        self._analysis_service.mark_job_failed(
            project_id=project_id,
            job_id=job_id,
            failure_reason=AnalysisJobFailureReason.PROVIDER_ERROR,
            failure_detail=str(error),
        )
        raise error


class _ApiSnapshotNotFoundRunner:
    def __init__(self, analysis_service):
        self._analysis_service = analysis_service

    async def run_job(self, *, project_id: str, job_id: str):
        self._analysis_service.mark_job_running(project_id=project_id, job_id=job_id)
        error = NotFound("snapshot not found")
        self._analysis_service.mark_job_failed(
            project_id=project_id,
            job_id=job_id,
            failure_reason=AnalysisJobFailureReason.SNAPSHOT_NOT_FOUND,
            failure_detail=str(error),
        )
        raise error


class LegacyOrderedDraftMigration503Test(unittest.TestCase):
    """Pre-W3 legacy drafts must yield an actionable 503, never an opaque 500.

    A draft persisted before the v1.7.14 ordered-unit invariant has no
    ``unit_kind``/``position``; the read endpoints run that invariant and would
    otherwise leak the resulting ``DraftOrderIntegrityError`` as a 500 (found in
    2026-07-22 dogfood). The owner decision (503, endpoint defence + migration)
    maps the three read endpoints that were leaking — list, create, export — to
    503. ``reorder_drafts`` already caught it as 409 (left unchanged, §3) and
    ``start_next_unit`` remains tracked debt.
    """

    def _app_with_legacy_draft(self):
        repo = InMemoryCoreSotRepository()
        service = CoreSotService(repo)
        project = service.create_project(name="Novel")
        # Inject a legacy document exactly as a pre-migration Mongo record would
        # deserialize: no unit_kind, no position.
        repo.drafts["legacy-1"] = Draft(
            id="legacy-1", project_id=project.id, title="Old Episode"
        )
        return TestClient(create_app(service=service)), project.id

    def test_list_drafts_on_legacy_data_returns_503(self):
        # Under-strict: dropping the endpoint's except clause re-leaks a 500.
        client, project_id = self._app_with_legacy_draft()

        resp = client.get(f"/projects/{project_id}/drafts")

        self.assertEqual(resp.status_code, 503)
        self.assertIn("migration is required", resp.json()["detail"])

    def test_create_draft_on_legacy_data_returns_503(self):
        client, project_id = self._app_with_legacy_draft()

        resp = client.post(
            f"/projects/{project_id}/drafts", json={"title": "New"}
        )

        self.assertEqual(resp.status_code, 503)

    def test_project_export_on_legacy_data_returns_503(self):
        client, project_id = self._app_with_legacy_draft()

        resp = client.get(f"/projects/{project_id}/export")

        self.assertEqual(resp.status_code, 503)

    def test_well_formed_project_is_unaffected(self):
        # Over-strict: a normally-created (migrated) project must still 200 —
        # the 503 path must not swallow healthy reads.
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()
        client.post(f"/projects/{project['id']}/drafts", json={"title": "One"})

        resp = client.get(f"/projects/{project['id']}/drafts")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["drafts"]), 1)

    def test_reorder_on_legacy_data_stays_409_not_500(self):
        # Locks the intentional asymmetry: reorder already caught the integrity
        # error via its InvalidDraftOrder clause (409), so it never leaked a 500
        # and was deliberately left unchanged (work_log §3 scope-out). Without
        # this test the 409 rested only on the subclass-catch mechanism; here it
        # is pinned. Two directions: not 500 (if reorder's catch is ever split
        # out) and not 503 (the 503 mapping stays exclusive to list/create/export).
        client, project_id = self._app_with_legacy_draft()

        resp = client.put(
            f"/projects/{project_id}/draft-order",
            json={"ordered_draft_ids": ["legacy-1"]},
        )

        self.assertEqual(resp.status_code, 409)

    def test_create_with_bad_unit_kind_is_client_error_not_503(self):
        # Over-strict: a bad unit_kind is a client input error (422 at the
        # Pydantic boundary), never the server-integrity 503.
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()

        resp = client.post(
            f"/projects/{project['id']}/drafts",
            json={"title": "Bad", "unit_kind": "volume"},
        )

        self.assertNotEqual(resp.status_code, 503)
        self.assertEqual(resp.status_code, 422)


class CrudErrorContractDeclarationTest(unittest.TestCase):
    """OpenAPI must declare the realistic error statuses of the CRUD family.

    SoT v1.7.29 "HTTP 에러 응답 계약" (H3 S2, D3=A): the status code is the
    machine-readable half of the contract, and the endpoint-by-endpoint set lives
    in OpenAPI — not in the SoT — so this is where it has to be locked. Before
    S2 these 20 endpoints raised 404/409/400/503 at runtime while the public
    contract said nothing, which is exactly how the legacy-data 503 shipped
    undocumented (verification H-2, 2026-07-22).

    The expected set is exact, so the test bites in both directions:
    under-strict (a dropped ``responses=`` loses a documented failure) and
    over-strict (declaring a status the endpoint cannot raise, which would lie to
    the frontend's generated types just as loudly as silence did).
    """

    # (path, method) -> exact set of declared statuses besides 200/422.
    # 422 is excluded because FastAPI emits it automatically for any endpoint
    # with a validated body/param and its body shape is a different contract.
    EXPECTED = {
        ("/projects", "post"): {"401", "503"},
        ("/projects", "get"): {"401", "503"},
        ("/projects/{project_id}", "get"): {"401", "403", "404", "503"},
        ("/projects/{project_id}", "patch"): {"401", "403", "404", "409", "503"},
        ("/projects/{project_id}", "delete"): {"401", "403", "404", "503"},
        ("/projects/{project_id}/brief", "get"): {"401", "403", "404", "503"},
        ("/projects/{project_id}/brief", "put"): {"401", "403", "404", "409", "503"},
        ("/projects/{project_id}/brief/versions", "get"): {"401", "403", "404", "503"},
        ("/projects/{project_id}/brief/versions/{version_id}", "get"):
            {"401", "403", "404", "503"},
        ("/projects/{project_id}/drafts", "get"): {"401", "403", "404", "503"},
        ("/projects/{project_id}/drafts", "post"): {"401", "403", "404", "409", "503"},
        ("/projects/{project_id}/drafts/{draft_id}", "get"): {"401", "403", "404", "503"},
        ("/projects/{project_id}/drafts/{draft_id}", "patch"):
            {"401", "403", "404", "409", "503"},
        ("/projects/{project_id}/drafts/{draft_id}", "delete"): {"401", "403", "404", "503"},
        ("/projects/{project_id}/drafts/{draft_id}/versions", "get"):
            {"401", "403", "404", "503"},
        ("/projects/{project_id}/drafts/{draft_id}/versions", "post"):
            {"401", "403", "400", "404", "409", "503"},
        ("/projects/{project_id}/drafts/{draft_id}/versions/{version_id}", "get"):
            {"401", "403", "404", "503"},
        ("/projects/{project_id}/drafts/{draft_id}/versions/{version_id}/export",
         "get"): {"401", "403", "400", "404", "503"},
        ("/projects/{project_id}/export", "get"): {"401", "403", "400", "404", "503"},
        ("/projects/{project_id}/draft-order", "put"): {"401", "403", "404", "409", "503"},
    }

    def setUp(self):
        self.spec = create_app().openapi()

    def _declared(self, path: str, method: str) -> set[str]:
        responses = self.spec["paths"][path][method]["responses"]
        return {code for code in responses if code not in ("200", "422")}

    def test_declared_error_statuses_match_the_lock_list(self):
        self.assertEqual(len(self.EXPECTED), 20)
        for (path, method), expected in self.EXPECTED.items():
            with self.subTest(path=path, method=method):
                self.assertEqual(self._declared(path, method), expected)

    def test_every_declared_error_body_is_the_uniform_detail_model(self):
        # D1=A: one error body for the whole app. A richer per-status model would
        # fork the contract silently; this pins the Union-free single reference.
        for (path, method), expected in self.EXPECTED.items():
            responses = self.spec["paths"][path][method]["responses"]
            for code in expected:
                with self.subTest(path=path, method=method, code=code):
                    schema = responses[code]["content"]["application/json"]["schema"]
                    self.assertEqual(
                        schema.get("$ref"),
                        "#/components/schemas/ErrorDetailResponse",
                    )

    def test_migration_503_description_names_the_operator_action(self):
        # The 503 that shipped undocumented is the one whose fix is an operator
        # action, so its declaration must say which one instead of leaving the
        # next reader to infer it from a log.
        migration_503 = (
            ("/projects/{project_id}/drafts", "get"),
            ("/projects/{project_id}/drafts", "post"),
            ("/projects/{project_id}/export", "get"),
        )
        for path, method in migration_503:
            with self.subTest(path=path, method=method):
                description = (
                    self.spec["paths"][path][method]["responses"]["503"]["description"]
                )
                self.assertIn("migrate_ordered_units.py", description)


class CrudErrorBodyExactKeyTest(unittest.TestCase):
    """The runtime error body is exactly ``{"detail": <string>}``.

    The declarations above are only honest if the wire body matches them, and
    ``detail`` being the *only* key is what lets the SoT say "status code is the
    machine-readable layer, detail is for humans". A future ``reason`` field is
    an explicit additive decision (D1=B), not something that appears by drift.
    """

    def _assert_detail_only(self, response, status: int):
        self.assertEqual(response.status_code, status)
        body = response.json()
        self.assertEqual(set(body), {"detail"})
        self.assertIsInstance(body["detail"], str)
        self.assertTrue(body["detail"])

    def test_404_body(self):
        client = TestClient(create_app())
        self._assert_detail_only(client.get("/projects/missing"), 404)

    def test_409_body(self):
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()
        client.delete(f"/projects/{project['id']}")

        self._assert_detail_only(
            client.patch(f"/projects/{project['id']}", json={"name": "Renamed"}),
            409,
        )

    def test_400_body(self):
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()

        self._assert_detail_only(
            client.get(f"/projects/{project['id']}/export?format=pdf"), 400
        )

    def test_503_body(self):
        repo = InMemoryCoreSotRepository()
        service = CoreSotService(repo)
        project = service.create_project(name="Novel")
        repo.drafts["legacy-1"] = Draft(
            id="legacy-1", project_id=project.id, title="Old Episode"
        )
        client = TestClient(create_app(service=service))

        self._assert_detail_only(client.get(f"/projects/{project.id}/drafts"), 503)


class AdminErrorContractDeclarationTest(unittest.TestCase):
    """OpenAPI must declare the realistic error statuses of the admin track.

    The D8-5 sibling of the other track classes, and the first one whose 403
    means "not an admin" rather than "not your project". Both are the same
    uniform body; what the lock list pins is which operations can produce it at
    all, so a future non-admin endpoint cannot quietly inherit the status.

    Exact sets, so the test bites both ways — under-strict (a dropped
    ``responses=`` re-hides a documented failure) and over-strict (declaring a
    status the endpoint cannot raise, which lies to the generated frontend
    types).
    """

    EXPECTED = {
        ("/admin/users", "get"): {"401", "403", "503"},
        ("/admin/users", "post"): {"400", "401", "403", "409", "503"},
        ("/admin/users/{user_id}/deactivate", "post"):
            {"401", "403", "404", "409", "503"},
        # D8-5c. No 404: it looks nothing up, so there is nothing to be missing —
        # the per-project KPI declares one only because it resolves a project.
        ("/admin/observability/kpi", "get"): {"401", "403", "503"},
    }

    def setUp(self):
        self.spec = create_app().openapi()

    def _declared(self, path: str, method: str) -> set[str]:
        responses = self.spec["paths"][path][method]["responses"]
        return {code for code in responses if code not in ("200", "422")}

    def test_declared_error_statuses_match_the_lock_list(self):
        self.assertEqual(len(self.EXPECTED), 4)
        for (path, method), expected in self.EXPECTED.items():
            with self.subTest(path=path, method=method):
                self.assertEqual(self._declared(path, method), expected)

    def test_the_whole_admin_track_is_declared(self):
        # Over-strict guard on the lock list itself: a new /admin endpoint that
        # ships without a declaration must fail here rather than pass silently
        # because every row above still holds.
        undeclared = {
            (path, method)
            for path, operations in self.spec["paths"].items()
            if path.startswith("/admin/")
            for method in operations
            if (path, method) not in self.EXPECTED
        }
        self.assertEqual(undeclared, set())

    def test_every_declared_error_body_is_the_uniform_detail_model(self):
        detail = "#/components/schemas/ErrorDetailResponse"
        for (path, method), expected in self.EXPECTED.items():
            responses = self.spec["paths"][path][method]["responses"]
            for code in expected:
                with self.subTest(path=path, method=method, code=code):
                    schema = responses[code]["content"]["application/json"]["schema"]
                    self.assertEqual(schema.get("$ref"), detail)


class AnalysisErrorContractDeclarationTest(unittest.TestCase):
    """OpenAPI must declare the realistic error statuses of the analysis track.

    H3 S3, the sibling of :class:`CrudErrorContractDeclarationTest`. Same D3=A
    contract (status code = machine-readable layer, endpoint-by-endpoint set
    lives in OpenAPI), applied to the 21 analysis endpoints.

    What makes this track different from S2 is the failure vocabulary: 502
    (upstream LLM/provider) and the *configuration* face of 503 appear here for
    the first time outside the writing endpoints. The brief scopes them
    deliberately: each endpoint declares only the statuses it can actually
    reach, never the app-wide vocabulary.

    Exact sets, so the test bites both ways — under-strict (a dropped
    ``responses=`` re-hides a documented failure) and over-strict (declaring a
    status the endpoint cannot raise, which lies to the generated frontend
    types).

    ``auto-promote`` later gained the track's third failure code: SoT v1.7.35
    added the storage face of 503 and, with it, this track's only partial
    envelope (owner decision D1=B — canonical mints already written are reported
    rather than hidden). ``UNION_BODIES`` pins where that Union is allowed.
    """

    # (path, method, code) whose body is a Union of a partial envelope with the
    # uniform detail. Everything else must be a bare ErrorDetailResponse ref.
    UNION_BODIES = {
        ("/projects/{project_id}/analysis/jobs/{job_id}/auto-promote",
         "post", "503"),
    }

    # (path, method) -> exact set of declared statuses besides 200/422.
    EXPECTED = {
        ("/projects/{project_id}/analysis/jobs", "post"): {"401", "403", "404", "503"},
        ("/projects/{project_id}/analysis/jobs/{job_id}", "get"): {"401", "403", "404", "503"},
        ("/projects/{project_id}/analysis/jobs/{job_id}/candidates", "get"):
            {"401", "403", "404", "503"},
        ("/projects/{project_id}/analysis/jobs/{job_id}/retry", "post"):
            {"401", "403", "404", "409", "503"},
        ("/projects/{project_id}/analysis/jobs/{job_id}/run", "post"):
            {"401", "403", "400", "404", "409", "502", "503"},
        ("/projects/{project_id}/analysis/jobs/{job_id}/auto-promote", "post"):
            {"401", "403", "404", "503"},
        ("/projects/{project_id}/analysis/jobs/{job_id}/context", "post"):
            {"401", "403", "404", "503"},
        ("/projects/{project_id}/analysis/jobs/{job_id}/compare", "post"):
            {"401", "403", "404", "502", "503"},
        ("/projects/{project_id}/analysis/jobs/{job_id}/apply", "post"):
            {"401", "403", "400", "404", "503"},
        ("/projects/{project_id}/analysis/candidates/{candidate_id}/promote",
         "post"): {"401", "403", "404", "503"},
        ("/projects/{project_id}/analysis/candidates/{candidate_id}/confirm",
         "post"): {"401", "403", "404", "409", "503"},
        ("/projects/{project_id}/analysis/candidates/{candidate_id}/reject",
         "post"): {"401", "403", "404", "409", "503"},
        ("/projects/{project_id}/analysis/candidates/{candidate_id}/edit",
         "post"): {"401", "403", "400", "404", "409", "503"},
        ("/projects/{project_id}/analysis/review-queue", "get"): {"401", "403", "404", "503"},
        ("/projects/{project_id}/analysis/review-queue/{entry_id}/reconcile",
         "post"): {"401", "403", "404", "409", "503"},
        ("/projects/{project_id}/analysis/review-inbox", "get"): {"401", "403", "404", "503"},
        ("/projects/{project_id}/analysis/review-inbox/{candidate_id}", "get"):
            {"401", "403", "404", "503"},
        ("/projects/{project_id}/analysis/gate-findings", "get"): {"401", "403", "404", "503"},
        ("/projects/{project_id}/analysis/gate-findings/{finding_id}", "get"):
            {"401", "403", "404", "503"},
        ("/projects/{project_id}/analysis/gate-findings/{finding_id}/resolve",
         "post"): {"401", "403", "404", "409", "503"},
        ("/projects/{project_id}/analysis/gate-findings/{finding_id}/dismiss",
         "post"): {"401", "403", "404", "409", "503"},
    }

    def setUp(self):
        self.spec = create_app().openapi()

    def _declared(self, path: str, method: str) -> set[str]:
        responses = self.spec["paths"][path][method]["responses"]
        return {code for code in responses if code not in ("200", "422")}

    def test_declared_error_statuses_match_the_lock_list(self):
        self.assertEqual(len(self.EXPECTED), 21)
        for (path, method), expected in self.EXPECTED.items():
            with self.subTest(path=path, method=method):
                self.assertEqual(self._declared(path, method), expected)

    def test_the_whole_analysis_track_is_declared(self):
        # Over-strict guard on the lock list itself: if a new analysis endpoint
        # ships without a declaration, S3's closure claim is false even though
        # every row above still passes.
        undeclared = {
            (path, method)
            for path, operations in self.spec["paths"].items()
            if "/analysis/" in path
            for method in operations
            if (path, method) not in self.EXPECTED
        }
        self.assertEqual(undeclared, set())

    def test_every_declared_error_body_is_the_uniform_detail_model(self):
        # D1=A: one error body for the whole app, including the 502/503 this
        # track introduces to the declared surface. The single exception is the
        # partial envelope in UNION_BODIES, whose error arm is still the same
        # single model (SoT v1.7.35).
        detail = "#/components/schemas/ErrorDetailResponse"
        for (path, method), expected in self.EXPECTED.items():
            responses = self.spec["paths"][path][method]["responses"]
            for code in expected:
                with self.subTest(path=path, method=method, code=code):
                    schema = responses[code]["content"]["application/json"]["schema"]
                    if (path, method, code) in self.UNION_BODIES:
                        arms = {arm.get("$ref") for arm in schema["anyOf"]}
                        self.assertIn(detail, arms)
                        self.assertIn(
                            "#/components/schemas/AutoPromotePartialResponse", arms
                        )
                    else:
                        self.assertEqual(schema.get("$ref"), detail)

    def test_union_bodies_appear_only_where_the_contract_allows(self):
        # Over-strict guard on the exception itself, mirroring the writing
        # track's. auto-promote's 503 is a Union because canonical mints already
        # written cannot be rolled back and must not be hidden behind a bare
        # error body (D1=B). Every *other* analysis status is always a plain
        # error, and a partial envelope drifting onto one would fork the uniform
        # error body without anyone deciding to.
        actual_unions = {
            (path, method, code)
            for (path, method), expected in self.EXPECTED.items()
            for code in expected
            if "anyOf" in (self.spec["paths"][path][method]["responses"][code]
                           ["content"]["application/json"]["schema"])
        }
        self.assertEqual(actual_unions, self.UNION_BODIES)

    def test_config_503_description_names_the_operator_action(self):
        # The analysis 503 is the collaborator-not-configured face, not the
        # migration face. Its declaration must say the fix is a deployment
        # change so a reader is not left inferring it from a log (S2 precedent),
        # and must not borrow the migration wording.
        config_503 = (
            ("/projects/{project_id}/analysis/jobs/{job_id}/run", "post"),
            ("/projects/{project_id}/analysis/jobs/{job_id}/compare", "post"),
        )
        for path, method in config_503:
            with self.subTest(path=path, method=method):
                description = (
                    self.spec["paths"][path][method]["responses"]["503"]["description"]
                )
                self.assertIn("not configured", description)
                self.assertIn("deployment", description)
                self.assertNotIn("migrate_ordered_units.py", description)


class AnalysisErrorBodyExactKeyTest(unittest.TestCase):
    """The analysis track's runtime error bodies are exactly ``{"detail": str}``.

    Sibling of :class:`CrudErrorBodyExactKeyTest`, covering the two statuses S2
    could not reach: 502 (provider) and the configuration face of 503. The
    declarations above are only honest if the wire body matches them.
    """

    def _assert_detail_only(self, response, status: int):
        self.assertEqual(response.status_code, status)
        body = response.json()
        self.assertEqual(set(body), {"detail"})
        self.assertIsInstance(body["detail"], str)
        self.assertTrue(body["detail"])

    def _project_with_job(self, client):
        project = client.post("/projects", json={"name": "Novel"}).json()
        job = client.post(
            f"/projects/{project['id']}/analysis/jobs",
            json={"snapshot_id": "snapshot-1", "idempotency_key": "analysis-1"},
        ).json()["job"]
        return project, job

    def test_404_body(self):
        client = TestClient(create_app())
        self._assert_detail_only(
            client.get("/projects/missing/analysis/review-inbox"), 404
        )

    def test_409_body(self):
        client = TestClient(create_app())
        project, job = self._project_with_job(client)

        # retry is only legal from failed; a freshly created job is pending.
        self._assert_detail_only(
            client.post(
                f"/projects/{project['id']}/analysis/jobs/{job['id']}/retry"
            ),
            409,
        )

    def test_400_body(self):
        client = TestClient(create_app())
        project, job = self._project_with_job(client)

        self._assert_detail_only(
            client.post(
                f"/projects/{project['id']}/analysis/jobs/{job['id']}/apply",
                json={"proposals": [{"candidate_id": "nope", "action": "create"}]},
            ),
            400,
        )

    def test_502_body(self):
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        analysis = AnalysisService(InMemoryAnalysisRepository())
        client = TestClient(
            create_app(
                core_sot,
                analysis_service=analysis,
                analysis_runner=_ApiProviderErrorRunner(analysis),
            )
        )
        project = client.post("/projects", json={"name": "Novel"}).json()
        job = analysis.create_job(
            project_id=project["id"],
            snapshot_id="snapshot-1",
            idempotency_key="analysis-1",
        ).job

        self._assert_detail_only(
            client.post(f"/projects/{project['id']}/analysis/jobs/{job.id}/run"), 502
        )

    def test_503_body(self):
        # No runner configured — the collaborator face of 503.
        client = TestClient(create_app())
        project, job = self._project_with_job(client)

        self._assert_detail_only(
            client.post(f"/projects/{project['id']}/analysis/jobs/{job['id']}/run"),
            503,
        )


class MemorySourceErrorContractDeclarationTest(unittest.TestCase):
    """OpenAPI must declare the realistic error statuses of the memory/source track.

    H3 S4, after S2 (CRUD) and S3 (analysis). Same D3=A contract; what this
    track adds to the declared surface is **504** — ``context-search`` is the
    only endpoint outside the writing track that can exhaust its own budget
    (``ContextSearchBudgetExceeded``), so the timeout semantics S1 wrote into
    the SoT table first become machine-readable here.

    Exact sets, biting both ways (under-strict: a dropped declaration re-hides a
    failure; over-strict: declaring a status the endpoint cannot raise).
    """

    # Path fragments that make up this slice's track, used by the closure guard.
    TRACK = ("/memory", "/snapshots/", "/source-refs", "/context-search")

    # (path, method) -> exact set of declared statuses besides 200/422.
    EXPECTED = {
        ("/projects/{project_id}/memory", "get"): {"401", "403", "404", "503"},
        ("/projects/{project_id}/memory/{memory_id}", "get"): {"401", "403", "404", "503"},
        ("/projects/{project_id}/snapshots/{snapshot_id}/source-refs", "post"):
            {"401", "403", "400", "404", "503"},
        ("/projects/{project_id}/snapshots/{snapshot_id}/source-refs", "get"):
            {"401", "403", "404", "503"},
        ("/projects/{project_id}/source-refs/{source_ref_id}", "get"):
            {"401", "403", "404", "503"},
        # 502 added when the embedding-failure 500 leak was closed: the rebuild
        # embeds every source block, so a configured-but-failing embedding
        # service is an upstream failure, not a missing collaborator (503).
        ("/projects/{project_id}/snapshots/{snapshot_id}"
         "/index/source-blocks/rebuild", "post"): {"401", "403", "404", "502", "503"},
        ("/projects/{project_id}/context-search", "post"):
            {"401", "403", "400", "404", "502", "503", "504"},
    }

    def setUp(self):
        self.spec = create_app().openapi()

    def _declared(self, path: str, method: str) -> set[str]:
        responses = self.spec["paths"][path][method]["responses"]
        return {code for code in responses if code not in ("200", "422")}

    def test_declared_error_statuses_match_the_lock_list(self):
        self.assertEqual(len(self.EXPECTED), 7)
        for (path, method), expected in self.EXPECTED.items():
            with self.subTest(path=path, method=method):
                self.assertEqual(self._declared(path, method), expected)

    def test_the_whole_memory_source_track_is_declared(self):
        # Closure guard (S3 precedent): a new endpoint on this track shipping
        # without a declaration would leave every row above green while the
        # "track is closed" claim silently becomes false.
        undeclared = {
            (path, method)
            for path, operations in self.spec["paths"].items()
            if any(fragment in path for fragment in self.TRACK)
            for method in operations
            if (path, method) not in self.EXPECTED
        }
        self.assertEqual(undeclared, set())

    def test_every_declared_error_body_is_the_uniform_detail_model(self):
        # D1=A: one error body app-wide, including the 504 this track introduces.
        for (path, method), expected in self.EXPECTED.items():
            responses = self.spec["paths"][path][method]["responses"]
            for code in expected:
                with self.subTest(path=path, method=method, code=code):
                    schema = responses[code]["content"]["application/json"]["schema"]
                    self.assertEqual(
                        schema.get("$ref"),
                        "#/components/schemas/ErrorDetailResponse",
                    )

    def test_context_search_503_uses_the_configuration_face(self):
        # context search's 503 is "service is not configured", not the stored-data
        # integrity face, so it must carry the deployment wording and must not
        # borrow the migration script wording (S3 precedent).
        description = self.spec["paths"]["/projects/{project_id}/context-search"][
            "post"]["responses"]["503"]["description"]
        self.assertIn("not configured", description)
        self.assertIn("deployment", description)
        self.assertNotIn("migrate_ordered_units.py", description)


class MemorySourceErrorBodyExactKeyTest(unittest.TestCase):
    """The memory/source track's error bodies are exactly ``{"detail": str}``.

    Covers the statuses reachable without the context-search fixture stack; the
    502/503/504 bodies are locked next to their existing runtime fixtures in
    ``test_context_search_api.py`` rather than duplicating that harness here.
    """

    def _assert_detail_only(self, response, status: int):
        self.assertEqual(response.status_code, status)
        body = response.json()
        self.assertEqual(set(body), {"detail"})
        self.assertIsInstance(body["detail"], str)
        self.assertTrue(body["detail"])

    def test_404_body(self):
        client = TestClient(create_app())
        self._assert_detail_only(client.get("/projects/missing/memory"), 404)

    def test_400_body(self):
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        saved = client.post(
            f"/projects/{project['id']}/drafts/{draft['id']}/versions",
            json={"raw_text": "민아는 파란 편지를 발견했다.", "idempotency_key": "save-1"},
        ).json()
        snapshot_id = saved["snapshot"]["id"]

        # end_offset beyond the snapshot text is a CoreSotError, not a NotFound.
        self._assert_detail_only(
            client.post(
                f"/projects/{project['id']}/snapshots/{snapshot_id}/source-refs",
                json={"start_offset": 0, "end_offset": 9999},
            ),
            400,
        )


class CanonicalStoreFailureHandlerTest(unittest.TestCase):
    """A failing canonical store is a 503 from every endpoint, not an opaque 500.

    SoT v1.7.38 (owner decision 2026-07-24). Before this, only auto-promote
    mapped a storage failure; the other 48 undeclared operations leaked a 500 —
    the exact thing H3 spent the phase defining as a bug. The mapping is one
    app-wide handler rather than a clause per endpoint, because a clause per
    endpoint is what a new endpoint forgets.

    Both directions. Under-strict: dropping the handler brings the 500 back.
    Over-strict: (a) /health must NOT declare 503, since it touches no store and
    declaring it would lie to the generated types as loudly as silence did;
    (b) an endpoint that maps the failure itself must keep winning, so
    auto-promote still answers with its partial envelope instead of being
    flattened into the uniform body.
    """

    def _client_with_failing_store(self, error):
        class _FailingRepository(InMemoryCoreSotRepository):
            def list_projects_for_owner(self, owner_id):
                raise error

        return TestClient(create_app(service=CoreSotService(_FailingRepository())))

    @unittest.skipIf(_STORAGE_FAILURE is None, "pymongo is not installed")
    def test_storage_failure_is_503_with_the_uniform_body(self):
        client = self._client_with_failing_store(
            _STORAGE_FAILURE("connection to the canonical store was lost")
        )

        response = client.get("/projects")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(set(response.json()), {"detail"})
        self.assertTrue(response.json()["detail"])

    def test_reindex_enqueue_failure_is_also_503(self):
        # The one storage path that is not a pymongo type: it carries the mint it
        # completed, so it needs its own handler or it stays a 500.
        class _FailingRepository(InMemoryCoreSotRepository):
            def list_projects_for_owner(self, owner_id):
                raise MemoryReindexEnqueueFailed(
                    type("R", (), {"memory": type("M", (), {"id": "memory-1"})()})(),
                    RuntimeError("outbox write lost"),
                )

        client = TestClient(create_app(service=CoreSotService(_FailingRepository())))

        response = client.get("/projects")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(set(response.json()), {"detail"})
        self.assertIn("memory-1", response.json()["detail"])

    def test_health_does_not_declare_the_storage_503(self):
        # Over-strict guard. /health returns a constant and never reaches Mongo,
        # so it is the one endpoint for which the storage face is unreachable.
        # It is also the probe compose uses, so a spurious 503 there would be
        # read as the app being down.
        spec = create_app().openapi()
        self.assertEqual(
            {c for c in spec["paths"]["/health"]["get"]["responses"]
             if c not in ("200", "422")},
            set(),
        )
        self.assertEqual(TestClient(create_app()).get("/health").status_code, 200)

    def test_every_other_operation_declares_the_storage_503(self):
        # Under-strict guard on the declaration side: the handler makes 503
        # reachable everywhere, and D3=A says OpenAPI is the mechanical truth, so
        # silence anywhere but /health is a lie.
        spec = create_app().openapi()
        missing = {
            (path, method)
            for path, operations in spec["paths"].items()
            for method in operations
            if path != "/health"
            and "503" not in spec["paths"][path][method]["responses"]
        }
        self.assertEqual(missing, set())

    @unittest.skipIf(_STORAGE_FAILURE is None, "pymongo is not installed")
    def test_endpoint_level_mapping_still_wins_over_the_handler(self):
        # Over-strict guard on the handler's reach. Starlette only consults a
        # handler for exceptions that escape the route, so auto-promote's own
        # clause must still produce the partial envelope. If the handler ever
        # swallowed these first, the promoted[] contract (v1.7.35 D1=B) would be
        # silently replaced by a bare {"detail": ...}.
        class _FailingMemoryRepository(InMemoryMemoryRepository):
            def put_memory(self, entry):
                raise _STORAGE_FAILURE("connection lost")

        analysis = AnalysisService(InMemoryAnalysisRepository())
        memory = MemoryService(
            _FailingMemoryRepository(), auto_promotion_threshold=0.9
        )
        client = TestClient(create_app(
            service=CoreSotService(InMemoryCoreSotRepository()),
            analysis_service=analysis,
            memory_service=memory,
        ))
        project_id = client.post("/projects", json={"name": "Novel"}).json()["id"]
        job = analysis.create_job(
            project_id=project_id, snapshot_id="s1", idempotency_key="run-1"
        ).job
        task = analysis.create_task(
            project_id=project_id,
            job_id=job.id,
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
        )
        analysis.record_candidate(
            project_id=project_id,
            task_id=task.id,
            logical_key="k1",
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
            action=AnalysisCandidateAction.CREATE,
            provenance=AnalysisProvenance.SOURCE_OBSERVED,
            confidence=0.95,
            source_ref_ids=("source-ref-1",),
            payload={"name": "Ariel", "observation": "brave"},
        )

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/auto-promote"
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            set(response.json()),
            {"auto_promotion_threshold", "promoted", "promotion_error"},
        )

    @unittest.skipIf(_STORAGE_FAILURE is None, "pymongo is not installed")
    def test_storage_failure_is_503_from_routes_across_every_track(self):
        # Breadth guard (SoT v1.7.38). test_storage_failure_is_503_with_the_
        # uniform_body proves the handler fires for GET /projects alone. This
        # samples one route per track through the shared project-exists gate,
        # so a future endpoint that wraps its body in a broad ``except`` (and so
        # swallows the storage failure before it escapes to the handler) cannot
        # pass the declaration guard while leaking a 500 — the declaration test
        # would stay green in that drift; this runtime sweep would not.
        class _ProjectGateFailingRepository(InMemoryCoreSotRepository):
            def get_project(self, *args, **kwargs):
                raise _STORAGE_FAILURE(
                    "connection to the canonical store was lost"
                )

        client = TestClient(
            create_app(service=CoreSotService(_ProjectGateFailingRepository()))
        )
        # One route per track, all through the project-exists gate.
        routes = [
            "/projects/p1",                    # core_sot
            "/projects/p1/drafts",             # drafts
            "/projects/p1/brief",              # brief
            "/projects/p1/memory",             # memory
            "/projects/p1/analysis/jobs/j1",   # analysis
            "/projects/p1/writing/loop-audits",  # writing
        ]
        for path in routes:
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(set(response.json()), {"detail"})

    @unittest.skipIf(_STORAGE_FAILURE is None, "pymongo is not installed")
    def test_run_endpoint_narrows_storage_failure_to_503_despite_broad_except(self):
        # SoT v1.7.40 D2=A (owner decision 2026-07-24). The run endpoint wraps its
        # body in a broad ``except Exception → 502`` to mirror the compare endpoint,
        # so before this slice a canonical store failure was reclassified as an
        # upstream 502 — the precision gap v1.7.39 had to record as a pre-existing
        # exception. The explicit ``except _STORAGE_ERRORS → 503`` now precedes that
        # catch, so the store face reaches 503 like everywhere else.
        #
        # Under-strict: removing the new branch drops the failure into
        # ``except Exception`` and this re-fails with a 502. Over-strict (that the
        # store catch must not swallow an actual LLM failure into 503) is held by
        # test_analysis_run_endpoint_maps_provider_exception_to_502 and
        # test_analysis_run_endpoint_maps_real_provider_error_to_502, which pin
        # provider failures at 502.
        class _ProjectGateFailingRepository(InMemoryCoreSotRepository):
            def get_project(self, *args, **kwargs):
                raise _STORAGE_FAILURE(
                    "connection to the canonical store was lost"
                )

        client = TestClient(
            create_app(service=CoreSotService(_ProjectGateFailingRepository()))
        )

        response = client.post("/projects/p1/analysis/jobs/j1/run")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(set(response.json()), {"detail"})
        self.assertTrue(response.json()["detail"])

    @unittest.skipIf(_STORAGE_FAILURE is None, "pymongo is not installed")
    def test_handler_registration_is_skipped_when_no_driver(self):
        # Robustness guard (SoT v1.7.38). The app must build and /health must
        # answer even when pymongo is absent — the in-memory path needs no
        # driver, and a deployment with no Mongo has no Mongo failure to
        # classify. An empty ``_STORAGE_ERRORS`` means the registration loop
        # runs zero times, so no pymongo handler is keyed; the
        # ``MemoryReindexEnqueueFailed`` handler (registered outside the loop)
        # is unaffected, as is /health. Both directions: with the driver the
        # handler IS keyed, without it it is NOT.
        from pymongo.errors import PyMongoError
        self.assertIn(PyMongoError, create_app().exception_handlers)

        import services.application.app.main as main_module
        original = main_module._STORAGE_ERRORS
        main_module._STORAGE_ERRORS = ()
        try:
            app = create_app()
            self.assertNotIn(PyMongoError, app.exception_handlers)
            self.assertEqual(
                TestClient(app).get("/health").status_code, 200,
            )
        finally:
            main_module._STORAGE_ERRORS = original


class SourceBlockRebuildEmbeddingFailureTest(unittest.TestCase):
    """A failing embedding service makes the rebuild a 502, not an opaque 500.

    ``POST …/index/source-blocks/rebuild`` embeds every source block, but the
    endpoint only caught ``NotFound`` — so a configured-but-failing embedding
    service escaped as a 500. Nobody in the app caught ``EmbeddingProviderError``
    at all (it is raised for timeout / unreachable / malformed response alike).

    502 rather than 503 because the collaborator is present and failing, not
    missing. That is what the SoT taxonomy assigns to upstream failures, and it
    matches the precedent already in the codebase: context search's vector step
    maps an embedding failure to ``BACKEND_ERROR``, which surfaces as 502.

    Both directions: removing the ``except EmbeddingProviderError`` clause makes
    the failure case re-fail (the 500 returns), and the healthy case must stay
    200 so the catch cannot be widened into swallowing successful rebuilds.
    """

    def _project_with_snapshot(self, client):
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()
        saved = client.post(
            f"/projects/{project['id']}/drafts/{draft['id']}/versions",
            json={"raw_text": "민아는 파란 편지를 발견했다.", "idempotency_key": "s1"},
        ).json()
        return project["id"], saved["snapshot"]["id"]

    def test_embedding_failure_is_502_with_the_uniform_body(self):
        class _FailingEmbeddings:
            def embed(self, text):
                raise EmbeddingProviderError("embedding service is unavailable")

        with patch(
            "services.application.app.main._build_embedding_provider",
            return_value=_FailingEmbeddings(),
        ):
            client = TestClient(create_app())
            project_id, snapshot_id = self._project_with_snapshot(client)
            response = client.post(
                f"/projects/{project_id}/snapshots/{snapshot_id}"
                f"/index/source-blocks/rebuild"
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(set(response.json()), {"detail"})
        self.assertTrue(response.json()["detail"])

    def test_healthy_rebuild_still_succeeds(self):
        # Over-strict guard: the new clause must not turn working rebuilds into
        # errors. The default deterministic fake embedding never raises.
        client = TestClient(create_app())
        project_id, snapshot_id = self._project_with_snapshot(client)
        response = client.post(
            f"/projects/{project_id}/snapshots/{snapshot_id}"
            f"/index/source-blocks/rebuild"
        )
        self.assertEqual(response.status_code, 200)

    def test_unrelated_failure_is_not_relabelled_as_502(self):
        # Over-strict guard on the clause's *width*. Catching bare ``Exception``
        # here would pass every other test in this class while quietly
        # relabelling programming errors as an upstream failure — telling an
        # operator to go check a healthy embedding service. Only the named type
        # is a 502; anything else must keep propagating.
        class _BrokenEmbeddings:
            def embed(self, text):
                raise ValueError("not an embedding transport failure")

        with patch(
            "services.application.app.main._build_embedding_provider",
            return_value=_BrokenEmbeddings(),
        ):
            client = TestClient(create_app())
            project_id, snapshot_id = self._project_with_snapshot(client)
            with self.assertRaises(ValueError):
                client.post(
                    f"/projects/{project_id}/snapshots/{snapshot_id}"
                    f"/index/source-blocks/rebuild"
                )


class WritingErrorContractDeclarationTest(unittest.TestCase):
    """OpenAPI must declare the realistic error statuses of the writing track.

    H3 S5 — the phase's last slice, closing the surface H1 opened. Two things
    make this track different from S2/S3/S4:

    * **Dynamic ``ProviderError`` mapping.** All nine dynamic
      ``status_code=status`` sites live here, every one of them
      ``504 if TIMEOUT else 502``. So the realistic set is exactly ``{502, 504}``
      — the brief's "declare the realistic set, do not enumerate everything
      upstream could produce" applies here and nowhere else.
    * **Partial envelopes.** ``revise-and-gate`` and ``accept`` were already
      declared before H3 and document a Union of their partial envelope with the
      uniform detail on partial-capable statuses. That is not a D1=A violation —
      the error arm is still the single ``ErrorDetailResponse`` — so the body
      assertion below accepts either a direct ``$ref`` or an ``anyOf`` arm, and
      ``UNION_BODIES`` pins exactly where a Union is allowed to appear so a new
      one cannot arrive by drift.

    ``accept`` also carries the phase's only runtime change: its 503 now covers
    both faces (collaborator-not-configured *and* the ordered-unit integrity
    failure that used to leak as a 500), so its declaration names both actions.
    """

    # (path, method) -> exact set of declared statuses besides 200/422.
    # 202 on generate is a success arm, not an error, but it is declared via the
    # same mechanism so it appears here to keep the set exact.
    EXPECTED = {
        ("/projects/{project_id}/writing/generate", "post"):
            {"401", "403", "202", "400", "404", "502", "503", "504"},
        ("/projects/{project_id}/writing/generation-jobs/{job_id}", "get"):
            {"401", "403", "404", "503"},
        ("/projects/{project_id}/writing/generation-jobs/{job_id}/retry", "post"):
            {"401", "403", "404", "409", "503"},
        ("/projects/{project_id}/writing/gate", "post"):
            {"401", "403", "400", "404", "502", "503", "504"},
        ("/projects/{project_id}/writing/report", "post"):
            {"401", "403", "400", "404", "502", "503", "504"},
        ("/projects/{project_id}/writing/revise", "post"):
            {"401", "403", "400", "404", "502", "503", "504"},
        ("/projects/{project_id}/writing/revise-and-gate", "post"):
            {"401", "403", "400", "404", "502", "503", "504"},
        ("/projects/{project_id}/writing/loop-audits", "get"): {"401", "403", "404", "503"},
        ("/projects/{project_id}/writing/loop-audits/{audit_id}", "get"):
            {"401", "403", "404", "503"},
        ("/projects/{project_id}/writing/accept", "post"):
            {"401", "403", "400", "404", "409", "502", "503", "504"},
        ("/projects/{project_id}/writing/scratch", "get"): {"401", "403", "404", "503"},
        ("/projects/{project_id}/writing/scratch", "delete"): {"401", "403", "404", "503"},
    }

    # (path, method, code) where the body is a Union of a partial envelope with
    # the uniform detail. Everything else must be a bare ErrorDetailResponse ref.
    UNION_BODIES = {
        ("/projects/{project_id}/writing/revise-and-gate", "post", code)
        for code in ("400", "502", "503", "504")
    } | {("/projects/{project_id}/writing/accept", "post", "502")}

    def setUp(self):
        self.spec = create_app().openapi()

    def _declared(self, path: str, method: str) -> set[str]:
        responses = self.spec["paths"][path][method]["responses"]
        return {code for code in responses if code not in ("200", "422")}

    def _schema(self, path: str, method: str, code: str) -> dict:
        return (self.spec["paths"][path][method]["responses"][code]
                ["content"]["application/json"]["schema"])

    def test_declared_error_statuses_match_the_lock_list(self):
        self.assertEqual(len(self.EXPECTED), 12)
        for (path, method), expected in self.EXPECTED.items():
            with self.subTest(path=path, method=method):
                self.assertEqual(self._declared(path, method), expected)

    def test_the_whole_writing_track_is_declared(self):
        undeclared = {
            (path, method)
            for path, operations in self.spec["paths"].items()
            if "/writing/" in path
            for method in operations
            if (path, method) not in self.EXPECTED
        }
        self.assertEqual(undeclared, set())

    def test_every_declared_error_body_carries_the_uniform_detail_model(self):
        detail = "#/components/schemas/ErrorDetailResponse"
        for (path, method), expected in self.EXPECTED.items():
            for code in expected:
                if code == "202":  # success arm, not an error body
                    continue
                with self.subTest(path=path, method=method, code=code):
                    schema = self._schema(path, method, code)
                    if (path, method, code) in self.UNION_BODIES:
                        arms = {arm.get("$ref") for arm in schema["anyOf"]}
                        self.assertIn(detail, arms)
                    else:
                        self.assertEqual(schema.get("$ref"), detail)

    def test_union_bodies_appear_only_where_the_contract_allows(self):
        # Over-strict guard on the exception itself: a partial envelope leaking
        # onto a status that is always a plain error would fork the uniform error
        # body without anyone deciding to.
        actual_unions = {
            (path, method, code)
            for (path, method), expected in self.EXPECTED.items()
            for code in expected
            if code != "202" and "anyOf" in self._schema(path, method, code)
        }
        self.assertEqual(actual_unions, self.UNION_BODIES)

    def test_accept_503_names_both_operator_actions(self):
        # accept is the only endpoint whose 503 has two faces, so — unlike the
        # single-face constants — its declaration must name both remedies.
        description = self.spec["paths"]["/projects/{project_id}/writing/accept"][
            "post"]["responses"]["503"]["description"]
        self.assertIn("not configured", description)
        self.assertIn("migrate_ordered_units.py", description)

    def test_writing_endpoints_declare_the_dynamic_provider_pair_together(self):
        # The dynamic sites are all `504 if TIMEOUT else 502`, so an endpoint that
        # can reach one can reach the other. Declaring 502 without 504 (or vice
        # versa) would document half a branch.
        #
        # Read from the live spec, not from EXPECTED: asserting over the lock list
        # would only prove the lock list is self-consistent and could never fail on
        # a code change. This bites even when someone drops 504 from both places.
        for (path, method) in self.EXPECTED:
            declared = self._declared(path, method)
            with self.subTest(path=path, method=method):
                self.assertEqual("502" in declared, "504" in declared)


class WritingErrorBodyExactKeyTest(unittest.TestCase):
    """The writing track's plain error bodies are exactly ``{"detail": str}``.

    The partial-envelope statuses are deliberately not asserted here — their
    Union arm is a different, already-locked contract (``ACCEPT_RESPONSES`` /
    ``REVISE_AND_GATE_RESPONSES`` regressions). The 503 migration face is locked
    where it fires, in ``test_writing_accept.py::StartNextUnitLegacyDataTest``.
    """

    def _assert_detail_only(self, response, status: int):
        self.assertEqual(response.status_code, status)
        body = response.json()
        self.assertEqual(set(body), {"detail"})
        self.assertIsInstance(body["detail"], str)
        self.assertTrue(body["detail"])

    def test_404_body(self):
        client = TestClient(create_app())
        self._assert_detail_only(
            client.get("/projects/missing/writing/scratch?draft_id=d1"), 404
        )

    def test_503_config_body(self):
        # No writing service configured — the collaborator face.
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()
        self._assert_detail_only(
            client.post(
                f"/projects/{project['id']}/writing/generate",
                json={"request_id": "wr1", "task_type": "continue_scene",
                      "instruction": "이어서 써줘"},
            ),
            503,
        )

    def test_400_body(self):
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()
        self._assert_detail_only(
            client.post(
                f"/projects/{project['id']}/writing/generate",
                json={"request_id": "wr1", "task_type": "nope",
                      "instruction": "이어서 써줘"},
            ),
            400,
        )


if __name__ == "__main__":
    unittest.main()
