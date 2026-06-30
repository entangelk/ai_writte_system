"""FastAPI shell tests for the Application service."""

import asyncio
import unittest

import httpx

from services.application.app.analysis.models import (
    AnalysisCandidateAction,
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.analysis.service import (
    AnalysisService,
    InMemoryAnalysisRepository,
)
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.main import create_app


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
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()

        archived = client.delete(f"/projects/{project['id']}")

        self.assertEqual(archived.status_code, 200)
        self.assertTrue(archived.json()["archived"])
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
        client = TestClient(create_app())
        project = client.post("/projects", json={"name": "Novel"}).json()
        draft = client.post(
            f"/projects/{project['id']}/drafts", json={"title": "Episode 1"}
        ).json()

        archived = client.delete(
            f"/projects/{project['id']}/drafts/{draft['id']}"
        )

        self.assertEqual(archived.status_code, 200)
        self.assertTrue(archived.json()["archived"])
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
        client = TestClient(create_app())
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


if __name__ == "__main__":
    unittest.main()
