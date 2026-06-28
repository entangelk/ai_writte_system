"""FastAPI shell tests for the Application service."""

import unittest

from fastapi.testclient import TestClient

from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.main import create_app


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


if __name__ == "__main__":
    unittest.main()
