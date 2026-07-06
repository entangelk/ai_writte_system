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
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryService,
)


class TestClient:
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


def _seed_candidate(
    analysis: AnalysisService,
    *,
    project_id: str,
    candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
    logical_key="lk-1",
    confidence=0.5,
    payload=None,
):
    if payload is None:
        payload = {"name": "Ariel", "observation": "brave under pressure"}
    job = analysis.create_job(
        project_id=project_id,
        snapshot_id="snapshot-1",
        idempotency_key=f"run-{logical_key}",
    ).job
    task = analysis.create_task(
        project_id=project_id, job_id=job.id, candidate_type=candidate_type
    )
    return analysis.record_candidate(
        project_id=project_id,
        task_id=task.id,
        logical_key=logical_key,
        candidate_type=candidate_type,
        action=AnalysisCandidateAction.CREATE,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=confidence,
        source_ref_ids=("source-ref-1",),
        payload=payload,
    ).candidate


def _build(*, auto_promotion_threshold=None):
    core_sot = CoreSotService(InMemoryCoreSotRepository())
    analysis = AnalysisService(InMemoryAnalysisRepository())
    memory = MemoryService(
        InMemoryMemoryRepository(),
        auto_promotion_threshold=auto_promotion_threshold,
    )
    app = create_app(
        service=core_sot,
        analysis_service=analysis,
        memory_service=memory,
    )
    client = TestClient(app)
    project_id = client.post("/projects", json={"name": "Novel"}).json()["id"]
    return client, analysis, project_id


class ManualPromotionApiTest(unittest.TestCase):
    def test_promote_candidate_creates_and_reads_canonical_memory(self):
        client, analysis, project_id = _build()
        candidate = _seed_candidate(analysis, project_id=project_id, confidence=0.42)

        response = client.post(
            f"/projects/{project_id}/analysis/candidates/{candidate.id}/promote"
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["idempotent_replay"])
        memory = body["memory"]
        self.assertEqual(memory["status"], "canonical")
        self.assertEqual(memory["version"], 1)
        self.assertEqual(memory["promotion_mode"], "manual")
        self.assertIsNone(memory["applied_threshold"])
        self.assertEqual(memory["source_candidate_id"], candidate.id)
        self.assertEqual(memory["memory_type"], "character_observation")
        self.assertEqual(memory["confidence"], 0.42)

        fetched = client.get(f"/projects/{project_id}/memory/{memory['id']}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["id"], memory["id"])

        listed = client.get(f"/projects/{project_id}/memory").json()["memory"]
        self.assertEqual([m["id"] for m in listed], [memory["id"]])

    def test_promote_candidate_is_idempotent(self):
        client, analysis, project_id = _build()
        candidate = _seed_candidate(analysis, project_id=project_id)

        first = client.post(
            f"/projects/{project_id}/analysis/candidates/{candidate.id}/promote"
        ).json()
        replay = client.post(
            f"/projects/{project_id}/analysis/candidates/{candidate.id}/promote"
        ).json()

        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["memory"]["id"], first["memory"]["id"])
        listed = client.get(f"/projects/{project_id}/memory").json()["memory"]
        self.assertEqual(len(listed), 1)

    def test_promote_missing_candidate_returns_404(self):
        client, _analysis, project_id = _build()
        response = client.post(
            f"/projects/{project_id}/analysis/candidates/nope/promote"
        )
        self.assertEqual(response.status_code, 404)

    def test_promote_on_missing_project_returns_404(self):
        client, analysis, project_id = _build()
        candidate = _seed_candidate(analysis, project_id=project_id)
        response = client.post(
            f"/projects/missing/analysis/candidates/{candidate.id}/promote"
        )
        self.assertEqual(response.status_code, 404)


class AutoPromotionApiTest(unittest.TestCase):
    def test_auto_promote_off_by_default_promotes_nothing(self):
        client, analysis, project_id = _build(auto_promotion_threshold=None)
        candidate = _seed_candidate(analysis, project_id=project_id, confidence=1.0)
        job_id = candidate.job_id

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job_id}/auto-promote"
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["auto_promotion_threshold"])
        self.assertEqual(body["promoted"], [])
        self.assertEqual(
            client.get(f"/projects/{project_id}/memory").json()["memory"], []
        )

    def test_auto_promote_fires_only_at_or_above_threshold(self):
        client, analysis, project_id = _build(auto_promotion_threshold=0.9)
        high = _seed_candidate(
            analysis, project_id=project_id, logical_key="high", confidence=0.95
        )

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{high.job_id}/auto-promote"
        )

        body = response.json()
        self.assertEqual(body["auto_promotion_threshold"], 0.9)
        self.assertEqual(len(body["promoted"]), 1)
        promoted = body["promoted"][0]
        self.assertEqual(promoted["promotion_mode"], "auto_threshold")
        self.assertEqual(promoted["applied_threshold"], 0.9)
        self.assertEqual(promoted["source_candidate_id"], high.id)

    def test_auto_promote_recall_reports_only_newly_promoted(self):
        # promoted[] means "newly promoted this call": a second run of the gate
        # over the same job replays idempotently (stored memory stays 1) and
        # must not re-report the already-promoted candidate.
        client, analysis, project_id = _build(auto_promotion_threshold=0.9)
        high = _seed_candidate(
            analysis, project_id=project_id, logical_key="high", confidence=0.95
        )
        path = f"/projects/{project_id}/analysis/jobs/{high.job_id}/auto-promote"

        first = client.post(path).json()
        second = client.post(path).json()

        self.assertEqual(len(first["promoted"]), 1)
        self.assertEqual(second["promoted"], [])
        stored = client.get(f"/projects/{project_id}/memory").json()["memory"]
        self.assertEqual(len(stored), 1)

    def test_auto_promote_leaves_below_threshold_candidate_for_manual(self):
        client, analysis, project_id = _build(auto_promotion_threshold=0.9)
        low = _seed_candidate(
            analysis, project_id=project_id, logical_key="low", confidence=0.5
        )

        auto = client.post(
            f"/projects/{project_id}/analysis/jobs/{low.job_id}/auto-promote"
        ).json()
        self.assertEqual(auto["promoted"], [])

        manual = client.post(
            f"/projects/{project_id}/analysis/candidates/{low.id}/promote"
        )
        self.assertEqual(manual.status_code, 200)
        self.assertEqual(manual.json()["memory"]["promotion_mode"], "manual")

    def test_get_missing_memory_returns_404(self):
        client, _analysis, project_id = _build()
        self.assertEqual(
            client.get(f"/projects/{project_id}/memory/nope").status_code, 404
        )


if __name__ == "__main__":
    unittest.main()
