"""FastAPI shell tests for the Application service."""

import unittest

from fastapi.testclient import TestClient

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


if __name__ == "__main__":
    unittest.main()
