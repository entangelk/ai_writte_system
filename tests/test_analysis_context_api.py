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
from services.application.app.memory.models import PromotionMode
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryService,
)


CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION
EVENT = AnalysisCandidateType.EVENT_OBSERVATION


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


def _seed_candidate(
    analysis: AnalysisService,
    *,
    project_id: str,
    candidate_type=CHARACTER,
    logical_key="lk-1",
    idempotency_key=None,
    confidence=0.5,
    payload=None,
):
    if payload is None:
        payload = {"name": "Ariel", "observation": "brave"}
    job = analysis.create_job(
        project_id=project_id,
        snapshot_id="snapshot-1",
        idempotency_key=idempotency_key or f"run-{logical_key}",
    ).job
    task = analysis.create_task(
        project_id=project_id, job_id=job.id, candidate_type=candidate_type
    )
    candidate = analysis.record_candidate(
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
    return job, candidate


def _build():
    core_sot = CoreSotService(InMemoryCoreSotRepository())
    analysis = AnalysisService(InMemoryAnalysisRepository())
    memory = MemoryService(InMemoryMemoryRepository())
    app = create_app(
        service=core_sot,
        analysis_service=analysis,
        memory_service=memory,
    )
    client = TestClient(app)
    project_id = client.post("/projects", json={"name": "Novel"}).json()["id"]
    return client, analysis, memory, project_id


class AnalysisContextApiTest(unittest.TestCase):
    def test_returns_prior_memories_of_job_candidate_types_excluding_self(self):
        client, analysis, memory, project_id = _build()
        # Prior job promotes a character memory (the comparison target).
        _prior_job, prior = _seed_candidate(
            analysis, project_id=project_id, logical_key="prior"
        )
        memory.promote_candidate(
            project_id=project_id, candidate=prior, mode=PromotionMode.MANUAL
        )
        # Current job produces a character candidate and promotes its own memory
        # (must be self-excluded, F4).
        current_job, current = _seed_candidate(
            analysis, project_id=project_id, logical_key="current"
        )
        memory.promote_candidate(
            project_id=project_id, candidate=current, mode=PromotionMode.MANUAL
        )

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{current_job.id}/context"
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        package = body["package"]
        self.assertEqual(package["purpose"], "analysis_context")
        self.assertEqual(body["gate"]["decision"], "pass")
        ids = [m["memory_id"] for m in package["prior_memories"]]
        # Only the prior job's memory; the current job's own memory is excluded.
        self.assertEqual(len(ids), 1)
        item = package["prior_memories"][0]
        self.assertEqual(item["memory_type"], "character_observation")
        self.assertEqual(item["status"], "canonical")
        self.assertEqual(item["value"], {"name": "Ariel", "observation": "brave"})
        self.assertIn("character_observation", item["match_reason"])

    def test_job_with_no_prior_memories_returns_empty_package(self):
        client, analysis, _memory, project_id = _build()
        job, _candidate = _seed_candidate(analysis, project_id=project_id)

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/context"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["package"]["prior_memories"], [])

    def test_only_job_candidate_types_are_searched(self):
        client, analysis, memory, project_id = _build()
        # Prior event memory exists in the project.
        _prior_job, prior_event = _seed_candidate(
            analysis,
            project_id=project_id,
            candidate_type=EVENT,
            logical_key="prior-event",
            payload={"event": "storm"},
        )
        memory.promote_candidate(
            project_id=project_id, candidate=prior_event, mode=PromotionMode.MANUAL
        )
        # Current job only produced a character candidate → event memory not pulled.
        char_job, _char = _seed_candidate(
            analysis, project_id=project_id, logical_key="char"
        )

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{char_job.id}/context"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["package"]["prior_memories"], [])

    def test_missing_project_returns_404(self):
        client, analysis, _memory, project_id = _build()
        job, _candidate = _seed_candidate(analysis, project_id=project_id)
        response = client.post(f"/projects/missing/analysis/jobs/{job.id}/context")
        self.assertEqual(response.status_code, 404)

    def test_missing_job_returns_404(self):
        client, _analysis, _memory, project_id = _build()
        response = client.post(
            f"/projects/{project_id}/analysis/jobs/nope/context"
        )
        self.assertEqual(response.status_code, 404)

    def test_job_context_unions_multiple_types_and_dedups_same_type(self):
        # D4=B derivation: a job whose candidates span two types (plus a
        # duplicate character candidate) must pull prior memories of BOTH types
        # (union), and the duplicate type must not multiply results.
        client, analysis, memory, project_id = _build()
        # Prior job seeds one character + one event canonical memory.
        _pj1, prior_char = _seed_candidate(
            analysis, project_id=project_id, candidate_type=CHARACTER,
            logical_key="prior-char",
        )
        _pj2, prior_event = _seed_candidate(
            analysis, project_id=project_id, candidate_type=EVENT,
            logical_key="prior-event", payload={"event": "storm"},
        )
        for candidate in (prior_char, prior_event):
            memory.promote_candidate(
                project_id=project_id, candidate=candidate, mode=PromotionMode.MANUAL
            )
        # Current job: two character candidates (dup type) + one event candidate.
        job = analysis.create_job(
            project_id=project_id, snapshot_id="snapshot-1", idempotency_key="multi"
        ).job
        task_c = analysis.create_task(
            project_id=project_id, job_id=job.id, candidate_type=CHARACTER
        )
        task_e = analysis.create_task(
            project_id=project_id, job_id=job.id, candidate_type=EVENT
        )
        for lk, payload in (("c1", {"name": "A", "observation": "x"}),
                            ("c2", {"name": "B", "observation": "y"})):
            analysis.record_candidate(
                project_id=project_id, task_id=task_c.id, logical_key=lk,
                candidate_type=CHARACTER, action=AnalysisCandidateAction.CREATE,
                provenance=AnalysisProvenance.SOURCE_OBSERVED, confidence=0.5,
                source_ref_ids=("source-ref-1",), payload=payload,
            )
        analysis.record_candidate(
            project_id=project_id, task_id=task_e.id, logical_key="e1",
            candidate_type=EVENT, action=AnalysisCandidateAction.CREATE,
            provenance=AnalysisProvenance.SOURCE_OBSERVED, confidence=0.5,
            source_ref_ids=("source-ref-1",), payload={"event": "duel"},
        )

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/context"
        )

        self.assertEqual(response.status_code, 200)
        prior = response.json()["package"]["prior_memories"]
        # Both prior types returned (union), each exactly once (dedup): no
        # duplicate character memory despite two character candidates.
        self.assertEqual(len(prior), 2)
        self.assertEqual(
            {p["memory_type"] for p in prior},
            {"character_observation", "event_observation"},
        )

    def test_analysis_context_purpose_rejected_on_writing_endpoint(self):
        client, _analysis, _memory, project_id = _build()
        response = client.post(
            f"/projects/{project_id}/context-search",
            json={
                "idempotency_key": "analysis-purpose-reject",
                "purpose": "analysis_context",
                "needs": ["prior_memory"],
                "query": "x",
                "max_tokens": 100,
            },
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
