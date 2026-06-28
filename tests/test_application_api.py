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
