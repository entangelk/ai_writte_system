import asyncio
import unittest

import httpx

from services.application.app.analysis.compare import (
    AnalysisCompareService,
    CompareAction,
    JudgeResult,
)
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


class FakeJudge:
    def __init__(self, action, rationale="judged"):
        self._action = action
        self._rationale = rationale

    def judge(self, *, candidate, memory):
        return JudgeResult(action=self._action, rationale=self._rationale)


def _seed_candidate(
    analysis, *, project_id, logical_key, payload, candidate_type=CHARACTER
):
    job = analysis.create_job(
        project_id=project_id, snapshot_id="snapshot-1",
        idempotency_key=f"run-{logical_key}",
    ).job
    task = analysis.create_task(
        project_id=project_id, job_id=job.id, candidate_type=candidate_type
    )
    candidate = analysis.record_candidate(
        project_id=project_id, task_id=task.id, logical_key=logical_key,
        candidate_type=candidate_type, action=AnalysisCandidateAction.CREATE,
        provenance=AnalysisProvenance.SOURCE_OBSERVED, confidence=0.5,
        source_ref_ids=("source-ref-1",), payload=payload,
    ).candidate
    return job, candidate


def _build(*, judge=None):
    core_sot = CoreSotService(InMemoryCoreSotRepository())
    analysis = AnalysisService(InMemoryAnalysisRepository())
    memory = MemoryService(InMemoryMemoryRepository())
    compare_service = (
        None if judge is None
        else AnalysisCompareService(memory_service=memory, judge=judge)
    )
    app = create_app(
        service=core_sot, analysis_service=analysis, memory_service=memory,
        compare_service=compare_service,
    )
    client = TestClient(app)
    project_id = client.post("/projects", json={"name": "Novel"}).json()["id"]
    return client, analysis, memory, project_id


class AnalysisCompareApiTest(unittest.TestCase):
    def test_no_match_returns_create_proposal_without_judge(self):
        client, analysis, _memory, project_id = _build()
        job, _c = _seed_candidate(
            analysis, project_id=project_id, logical_key="c1",
            payload={"name": "Ariel", "observation": "brave"},
        )

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/compare"
        )

        self.assertEqual(response.status_code, 200)
        proposals = response.json()["proposals"]
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["action"], "create")
        self.assertIsNone(proposals[0]["matched_memory_id"])

    def test_match_without_judge_returns_503(self):
        client, analysis, memory, project_id = _build()  # no judge
        _pj, prior = _seed_candidate(
            analysis, project_id=project_id, logical_key="prior",
            payload={"name": "Ariel", "observation": "brave"},
        )
        memory.promote_candidate(
            project_id=project_id, candidate=prior, mode=PromotionMode.MANUAL
        )
        job, _c = _seed_candidate(
            analysis, project_id=project_id, logical_key="cur",
            payload={"name": "Ariel", "observation": "braver"},
        )

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/compare"
        )
        self.assertEqual(response.status_code, 503)

    def test_match_with_injected_judge_returns_labeled_proposal(self):
        client, analysis, memory, project_id = _build(
            judge=FakeJudge(CompareAction.ADD_EVIDENCE, rationale="corroborates")
        )
        _pj, prior = _seed_candidate(
            analysis, project_id=project_id, logical_key="prior",
            payload={"name": "Ariel", "observation": "brave"},
        )
        memory.promote_candidate(
            project_id=project_id, candidate=prior, mode=PromotionMode.MANUAL
        )
        job, _c = _seed_candidate(
            analysis, project_id=project_id, logical_key="cur",
            payload={"name": "Ariel", "observation": "braver"},
        )

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/compare"
        )

        self.assertEqual(response.status_code, 200)
        proposal = response.json()["proposals"][0]
        self.assertEqual(proposal["action"], "add_evidence")
        self.assertEqual(proposal["rationale"], "corroborates")
        self.assertIsNotNone(proposal["matched_memory_id"])

    def test_promoted_character_memory_serializes_scope(self):
        # §8 ⑧ completion: scope is stored at promotion and exposed on the
        # memory envelope.
        client, analysis, memory, project_id = _build()
        _pj, prior = _seed_candidate(
            analysis, project_id=project_id, logical_key="prior",
            payload={"name": "  Ariel Song ", "observation": "brave"},
        )
        memory.promote_candidate(
            project_id=project_id, candidate=prior, mode=PromotionMode.MANUAL
        )

        listed = client.get(f"/projects/{project_id}/memory").json()["memory"]
        self.assertEqual(
            listed[0]["scope"],
            {"scope_type": "character", "scope_id": "ariel song"},
        )

    def test_missing_project_returns_404(self):
        client, analysis, _memory, project_id = _build()
        job, _c = _seed_candidate(
            analysis, project_id=project_id, logical_key="c1",
            payload={"name": "Ariel", "observation": "brave"},
        )
        response = client.post(f"/projects/missing/analysis/jobs/{job.id}/compare")
        self.assertEqual(response.status_code, 404)

    def test_missing_job_returns_404(self):
        client, _analysis, _memory, project_id = _build()
        response = client.post(
            f"/projects/{project_id}/analysis/jobs/nope/compare"
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
