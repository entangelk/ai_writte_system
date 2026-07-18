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
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.provider import FakeLLMProvider, GenerationResult


class TestClient:
    """Small sync wrapper around ASGITransport for this test module."""

    def __init__(self, app):
        self._app = app

    def get(self, path: str, **kwargs):
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs):
        return self._request("POST", path, **kwargs)

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
        expected = {"id", "project_id", "title", "archived"}

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


if __name__ == "__main__":
    unittest.main()
