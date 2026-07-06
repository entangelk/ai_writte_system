import unittest

from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.memory.models import (
    MemoryStatus,
    PromotionMode,
)
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryNotFound,
    MemoryService,
)


def _candidate(
    *,
    candidate_id: str = "candidate-1",
    project_id: str = "project-1",
    confidence: float = 0.5,
    candidate_type: AnalysisCandidateType = AnalysisCandidateType.CHARACTER_OBSERVATION,
    payload=None,
) -> AnalysisCandidate:
    if payload is None:
        payload = {"name": "Ariel", "observation": "brave under pressure"}
    return AnalysisCandidate(
        id=candidate_id,
        project_id=project_id,
        job_id="analysis-job-1",
        task_id="analysis-task-1",
        candidate_type=candidate_type,
        action=AnalysisCandidateAction.CREATE,
        status=AnalysisCandidateStatus.NEEDS_REVIEW,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=confidence,
        source_ref_ids=("source-ref-1",),
        payload=payload,
    )


def _service(auto_promotion_threshold=None):
    repo = InMemoryMemoryRepository()
    return MemoryService(repo, auto_promotion_threshold=auto_promotion_threshold), repo


class ManualPromotionTest(unittest.TestCase):
    def test_manual_promote_creates_canonical_first_version_preserving_candidate(self):
        service, repo = _service()
        candidate = _candidate(confidence=0.42)

        result = service.promote_candidate(
            project_id="project-1",
            candidate=candidate,
            mode=PromotionMode.MANUAL,
        )

        memory = result.memory
        self.assertFalse(result.idempotent_replay)
        self.assertEqual(memory.status, MemoryStatus.CANONICAL)
        self.assertEqual(memory.version, 1)
        self.assertEqual(memory.promotion_mode, PromotionMode.MANUAL)
        # Manual promotion is a human override, not a threshold decision.
        self.assertIsNone(memory.applied_threshold)
        # Candidate content is preserved verbatim.
        self.assertEqual(memory.memory_type, candidate.candidate_type)
        self.assertEqual(memory.provenance, candidate.provenance)
        self.assertEqual(memory.confidence, 0.42)
        self.assertEqual(memory.source_ref_ids, candidate.source_ref_ids)
        self.assertEqual(dict(memory.payload), dict(candidate.payload))
        # Audit trail back to the analysis run.
        self.assertEqual(memory.analysis_job_id, candidate.job_id)
        self.assertEqual(memory.source_candidate_id, candidate.id)
        self.assertEqual(len(repo.memories), 1)

    def test_manual_promote_is_idempotent_per_candidate(self):
        service, repo = _service()
        candidate = _candidate()

        first = service.promote_candidate(
            project_id="project-1", candidate=candidate, mode=PromotionMode.MANUAL
        )
        replay = service.promote_candidate(
            project_id="project-1", candidate=candidate, mode=PromotionMode.MANUAL
        )

        self.assertFalse(first.idempotent_replay)
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.memory.id, first.memory.id)
        self.assertEqual(len(repo.memories), 1)

    def test_manual_promote_rejects_cross_project_candidate(self):
        service, _repo = _service()
        candidate = _candidate(project_id="project-1")

        with self.assertRaises(MemoryNotFound):
            service.promote_candidate(
                project_id="project-2",
                candidate=candidate,
                mode=PromotionMode.MANUAL,
            )


class ThresholdGateTest(unittest.TestCase):
    def test_gate_is_off_by_default_and_promotes_nothing(self):
        # Over-strict guard: with no threshold configured a high-confidence
        # candidate must NOT auto-promote (no canon minted from a guess).
        service, repo = _service(auto_promotion_threshold=None)
        candidate = _candidate(confidence=1.0)

        self.assertFalse(service.evaluate_auto_promotion(candidate))
        result = service.auto_promote_candidate(
            project_id="project-1", candidate=candidate
        )

        self.assertIsNone(result)
        self.assertEqual(len(repo.memories), 0)

    def test_gate_fires_at_or_above_threshold(self):
        # Under-strict guard: confidence exactly at the threshold promotes.
        service, repo = _service(auto_promotion_threshold=0.9)
        at_threshold = _candidate(candidate_id="candidate-at", confidence=0.9)
        above = _candidate(candidate_id="candidate-above", confidence=0.95)

        at_result = service.auto_promote_candidate(
            project_id="project-1", candidate=at_threshold
        )
        above_result = service.auto_promote_candidate(
            project_id="project-1", candidate=above
        )

        self.assertIsNotNone(at_result)
        self.assertIsNotNone(above_result)
        self.assertEqual(at_result.memory.promotion_mode, PromotionMode.AUTO_THRESHOLD)
        self.assertEqual(at_result.memory.applied_threshold, 0.9)
        self.assertEqual(at_result.memory.status, MemoryStatus.CANONICAL)
        self.assertEqual(len(repo.memories), 2)

    def test_gate_does_not_fire_below_threshold_but_manual_still_promotes(self):
        # Below the threshold the candidate stays needs_review and the manual
        # approval path remains available (both-direction lock).
        service, repo = _service(auto_promotion_threshold=0.9)
        candidate = _candidate(confidence=0.89)

        auto_result = service.auto_promote_candidate(
            project_id="project-1", candidate=candidate
        )
        self.assertIsNone(auto_result)
        self.assertEqual(len(repo.memories), 0)

        manual = service.promote_candidate(
            project_id="project-1", candidate=candidate, mode=PromotionMode.MANUAL
        )
        self.assertEqual(manual.memory.status, MemoryStatus.CANONICAL)
        self.assertEqual(manual.memory.promotion_mode, PromotionMode.MANUAL)
        self.assertIsNone(manual.memory.applied_threshold)
        self.assertEqual(len(repo.memories), 1)

    def test_auto_then_manual_promotion_is_idempotent(self):
        service, repo = _service(auto_promotion_threshold=0.5)
        candidate = _candidate(confidence=0.8)

        auto = service.auto_promote_candidate(
            project_id="project-1", candidate=candidate
        )
        manual = service.promote_candidate(
            project_id="project-1", candidate=candidate, mode=PromotionMode.MANUAL
        )

        self.assertFalse(auto.idempotent_replay)
        self.assertTrue(manual.idempotent_replay)
        self.assertEqual(manual.memory.id, auto.memory.id)
        # The first promotion wins: mode/threshold are not overwritten.
        self.assertEqual(manual.memory.promotion_mode, PromotionMode.AUTO_THRESHOLD)
        self.assertEqual(manual.memory.applied_threshold, 0.5)
        self.assertEqual(len(repo.memories), 1)


class MemoryReadTest(unittest.TestCase):
    def test_get_memory_enforces_project_isolation(self):
        service, _repo = _service()
        result = service.promote_candidate(
            project_id="project-1",
            candidate=_candidate(),
            mode=PromotionMode.MANUAL,
        )

        fetched = service.get_memory(
            project_id="project-1", memory_id=result.memory.id
        )
        self.assertEqual(fetched.id, result.memory.id)

        with self.assertRaises(MemoryNotFound):
            service.get_memory(project_id="project-2", memory_id=result.memory.id)

    def test_list_memories_is_scoped_to_project(self):
        service, _repo = _service()
        service.promote_candidate(
            project_id="project-1",
            candidate=_candidate(candidate_id="candidate-a", project_id="project-1"),
            mode=PromotionMode.MANUAL,
        )
        service.promote_candidate(
            project_id="project-2",
            candidate=_candidate(candidate_id="candidate-b", project_id="project-2"),
            mode=PromotionMode.MANUAL,
        )

        listed = service.list_memories(project_id="project-1")
        self.assertEqual([m.project_id for m in listed], ["project-1"])


if __name__ == "__main__":
    unittest.main()
