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
from services.application.app.memory.models import MemoryStatus, PromotionMode
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryService,
)


CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION


class TestClient:
    __test__ = False

    def __init__(self, app):
        self._app = app

    def get(self, path, **kwargs):
        return self._request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self._request("POST", path, **kwargs)

    def _request(self, method, path, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())


def _seed_candidate(analysis, *, project_id, logical_key, payload):
    job = analysis.create_job(
        project_id=project_id, snapshot_id="snapshot-1",
        idempotency_key=f"run-{logical_key}",
    ).job
    task = analysis.create_task(
        project_id=project_id, job_id=job.id, candidate_type=CHARACTER
    )
    candidate = analysis.record_candidate(
        project_id=project_id, task_id=task.id, logical_key=logical_key,
        candidate_type=CHARACTER, action=AnalysisCandidateAction.CREATE,
        provenance=AnalysisProvenance.SOURCE_OBSERVED, confidence=0.5,
        source_ref_ids=("source-ref-1",), payload=payload,
    ).candidate
    return job, candidate


def _build():
    core_sot = CoreSotService(InMemoryCoreSotRepository())
    analysis = AnalysisService(InMemoryAnalysisRepository())
    memory = MemoryService(InMemoryMemoryRepository())
    app = create_app(
        service=core_sot, analysis_service=analysis, memory_service=memory
    )
    client = TestClient(app)
    project_id = client.post("/projects", json={"name": "Novel"}).json()["id"]
    return client, analysis, memory, project_id


class AnalysisApplyApiTest(unittest.TestCase):
    def test_create_proposal_mints_canonical(self):
        client, analysis, memory, project_id = _build()
        job, candidate = _seed_candidate(
            analysis, project_id=project_id, logical_key="c1",
            payload={"name": "Ariel", "observation": "brave"},
        )

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/apply",
            json={"proposals": [{"candidate_id": candidate.id, "action": "create"}]},
        )

        self.assertEqual(response.status_code, 200)
        applied = response.json()["applied"][0]
        self.assertEqual(applied["outcome"], "created")
        self.assertEqual(applied["version"], 1)
        self.assertEqual(len(memory.list_memories(project_id=project_id)), 1)

    def test_update_proposal_versions_prior_and_supersedes(self):
        client, analysis, memory, project_id = _build()
        _pj, prior = _seed_candidate(
            analysis, project_id=project_id, logical_key="prior",
            payload={"name": "Ariel", "observation": "brave"},
        )
        prior_mem = memory.promote_candidate(
            project_id=project_id, candidate=prior, mode=PromotionMode.MANUAL
        ).memory
        job, current = _seed_candidate(
            analysis, project_id=project_id, logical_key="cur",
            payload={"name": "Ariel", "observation": "now cautious"},
        )

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/apply",
            json={
                "proposals": [
                    {
                        "candidate_id": current.id,
                        "action": "update",
                        "matched_memory_id": prior_mem.id,
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        applied = response.json()["applied"][0]
        self.assertEqual(applied["outcome"], "versioned")
        self.assertEqual(applied["version"], 2)
        self.assertEqual(applied["superseded_memory_id"], prior_mem.id)
        # prior preserved as superseded, new version canonical
        old = memory.get_memory(project_id=project_id, memory_id=prior_mem.id)
        self.assertEqual(old.status, MemoryStatus.SUPERSEDED)
        new = memory.get_memory(project_id=project_id, memory_id=applied["memory_id"])
        self.assertEqual(new.status, MemoryStatus.CANONICAL)
        self.assertEqual(new.supersedes, prior_mem.id)

    def test_reapply_is_idempotent(self):
        # D5: re-posting the same apply body replays, no duplicate version.
        client, analysis, memory, project_id = _build()
        _pj, prior = _seed_candidate(
            analysis, project_id=project_id, logical_key="prior",
            payload={"name": "Ariel", "observation": "brave"},
        )
        prior_mem = memory.promote_candidate(
            project_id=project_id, candidate=prior, mode=PromotionMode.MANUAL
        ).memory
        job, current = _seed_candidate(
            analysis, project_id=project_id, logical_key="cur",
            payload={"name": "Ariel", "observation": "changed"},
        )
        body = {
            "proposals": [
                {
                    "candidate_id": current.id,
                    "action": "update",
                    "matched_memory_id": prior_mem.id,
                }
            ]
        }
        url = f"/projects/{project_id}/analysis/jobs/{job.id}/apply"

        first = client.post(url, json=body).json()["applied"][0]
        second = client.post(url, json=body).json()["applied"][0]

        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(second["idempotent_replay"])
        self.assertEqual(first["memory_id"], second["memory_id"])
        self.assertEqual(len(memory.list_memories(project_id=project_id)), 2)

    def test_no_change_and_conflict_write_nothing(self):
        client, analysis, memory, project_id = _build()
        _pj, prior = _seed_candidate(
            analysis, project_id=project_id, logical_key="prior",
            payload={"name": "Ariel", "observation": "brave"},
        )
        prior_mem = memory.promote_candidate(
            project_id=project_id, candidate=prior, mode=PromotionMode.MANUAL
        ).memory
        job, current = _seed_candidate(
            analysis, project_id=project_id, logical_key="cur",
            payload={"name": "Ariel", "observation": "same"},
        )

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/apply",
            json={
                "proposals": [
                    {
                        "candidate_id": current.id,
                        "action": "no_change",
                        "matched_memory_id": prior_mem.id,
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["applied"][0]["outcome"], "no_change")
        # only the prior canonical entry remains
        self.assertEqual(len(memory.list_memories(project_id=project_id)), 1)

    def test_unknown_action_returns_400(self):
        client, analysis, _memory, project_id = _build()
        job, candidate = _seed_candidate(
            analysis, project_id=project_id, logical_key="c1",
            payload={"name": "Ariel", "observation": "brave"},
        )
        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/apply",
            json={"proposals": [{"candidate_id": candidate.id, "action": "merge"}]},
        )
        self.assertEqual(response.status_code, 400)

    def test_candidate_not_in_job_returns_400(self):
        client, analysis, _memory, project_id = _build()
        job, _candidate = _seed_candidate(
            analysis, project_id=project_id, logical_key="c1",
            payload={"name": "Ariel", "observation": "brave"},
        )
        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/apply",
            json={"proposals": [{"candidate_id": "ghost", "action": "create"}]},
        )
        self.assertEqual(response.status_code, 400)

    def test_update_missing_matched_memory_returns_404(self):
        client, analysis, _memory, project_id = _build()
        job, candidate = _seed_candidate(
            analysis, project_id=project_id, logical_key="c1",
            payload={"name": "Ariel", "observation": "brave"},
        )
        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/apply",
            json={
                "proposals": [
                    {
                        "candidate_id": candidate.id,
                        "action": "update",
                        "matched_memory_id": "no-such-memory",
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_update_without_matched_memory_returns_400(self):
        # O3: update with matched_memory_id omitted (None) → MissingMatchedMemory
        # → 400 at the HTTP boundary (distinct from a non-existent id → 404).
        client, analysis, _memory, project_id = _build()
        job, candidate = _seed_candidate(
            analysis, project_id=project_id, logical_key="c1",
            payload={"name": "Ariel", "observation": "brave"},
        )
        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/apply",
            json={"proposals": [{"candidate_id": candidate.id, "action": "update"}]},
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_project_and_job_return_404(self):
        client, analysis, _memory, project_id = _build()
        job, candidate = _seed_candidate(
            analysis, project_id=project_id, logical_key="c1",
            payload={"name": "Ariel", "observation": "brave"},
        )
        body = {"proposals": [{"candidate_id": candidate.id, "action": "create"}]}
        missing_project = client.post(
            f"/projects/missing/analysis/jobs/{job.id}/apply", json=body
        )
        self.assertEqual(missing_project.status_code, 404)
        missing_job = client.post(
            f"/projects/{project_id}/analysis/jobs/nope/apply", json=body
        )
        self.assertEqual(missing_job.status_code, 404)


if __name__ == "__main__":
    unittest.main()
