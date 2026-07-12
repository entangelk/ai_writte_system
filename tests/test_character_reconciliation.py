import unittest

from services.application.app.analysis.compare import CompareAction
from services.application.app.analysis.models import (
    AnalysisCandidate, AnalysisCandidateAction, AnalysisCandidateStatus,
    AnalysisCandidateType, AnalysisProvenance,
)
from services.application.app.analysis.reconciliation import (
    CharacterReconciliationService, ReconciliationAction,
)
from services.application.app.analysis.review_queue import (
    InMemoryReviewQueueRepository, ReviewQueueService, ReviewQueueStatus,
)
from services.application.app.analysis.service import (
    AnalysisService, InMemoryAnalysisRepository,
)
from services.application.app.memory.models import PromotionMode, MemoryStatus
from services.application.app.memory.service import (
    InMemoryMemoryRepository, MemoryService,
)


def candidate(cid, job, name, observation, refs):
    return AnalysisCandidate(
        id=cid, project_id="p", job_id=job, task_id=f"t-{cid}",
        candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
        action=AnalysisCandidateAction.CREATE,
        status=AnalysisCandidateStatus.NEEDS_REVIEW,
        provenance=AnalysisProvenance.SOURCE_OBSERVED, confidence=0.8,
        source_ref_ids=refs, payload={"name": name, "observation": observation},
    )


class CharacterReconciliationTest(unittest.TestCase):
    def setUp(self):
        self.analysis_repo = InMemoryAnalysisRepository()
        self.analysis = AnalysisService(self.analysis_repo)
        self.memory = MemoryService(InMemoryMemoryRepository())
        self.queue = ReviewQueueService(InMemoryReviewQueueRepository())
        self.service = CharacterReconciliationService(
            analysis_service=self.analysis, memory_service=self.memory,
            review_queue=self.queue,
        )

    def _record(self, item):
        self.analysis_repo.candidates[item.id] = item

    def _entry(self, item, matched):
        return self.queue.enqueue(
            project_id="p", job_id=item.job_id, candidate_id=item.id,
            candidate_type=item.candidate_type, action=CompareAction.CONFLICT,
            matched_memory_id=matched, rationale="review",
        )

    def test_merge_mints_evidence_version_and_replay_is_idempotent(self):
        prior = candidate("prior", "old", "Ariel", "brave", ("r1",))
        incoming = candidate("incoming", "new", "Song", "brave", ("r2",))
        old = self.memory.promote_candidate(
            project_id="p", candidate=prior, mode=PromotionMode.MANUAL
        ).memory
        self._record(incoming)
        entry = self._entry(incoming, old.id)

        first = self.service.reconcile(
            project_id="p", entry_id=entry.id, action=ReconciliationAction.MERGE
        )
        replay = self.service.reconcile(
            project_id="p", entry_id=entry.id, action=ReconciliationAction.MERGE
        )

        merged = self.memory.get_memory(project_id="p", memory_id=first.memory_id)
        self.assertEqual(merged.payload, old.payload)
        self.assertEqual(merged.source_ref_ids, ("r1", "r2"))
        self.assertEqual(merged.supersedes, old.id)
        self.assertEqual(
            self.memory.get_memory(project_id="p", memory_id=old.id).status,
            MemoryStatus.SUPERSEDED,
        )
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.memory_id, first.memory_id)
        self.assertEqual(
            self.analysis.get_candidate(project_id="p", candidate_id="incoming").status,
            AnalysisCandidateStatus.CONFIRMED,
        )

    def test_split_promotes_separate_canonical_and_locks_action(self):
        prior = candidate("prior", "old", "Kim", "doctor", ("r1",))
        incoming = candidate("incoming", "new", "Kim", "detective", ("r2",))
        old = self.memory.promote_candidate(
            project_id="p", candidate=prior, mode=PromotionMode.MANUAL
        ).memory
        self._record(incoming)
        entry = self._entry(incoming, old.id)

        split = self.service.reconcile(
            project_id="p", entry_id=entry.id, action=ReconciliationAction.SPLIT
        )

        self.assertNotEqual(split.memory_id, old.id)
        self.assertIsNone(split.superseded_memory_id)
        self.assertEqual(
            self.queue.get(project_id="p", entry_id=entry.id).status,
            ReviewQueueStatus.RESOLVED,
        )
        with self.assertRaisesRegex(ValueError, "different action"):
            self.service.reconcile(
                project_id="p", entry_id=entry.id,
                action=ReconciliationAction.MERGE,
            )
