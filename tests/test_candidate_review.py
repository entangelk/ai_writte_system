"""Phase 6 candidate review state transition regressions (v1.6.61).

Locks the candidate state machine (needs_review→confirmed/rejected, idempotent,
illegal edges rejected) and the CandidateReviewService orchestration: confirm
promotes + de-indexes + resolves the conflict queue; reject de-indexes +
dismisses; both are idempotent (a replay repeats no side effect). Guards run both
directions. See docs/plans/06-candidate-state-transition-decisions.md.
"""

import unittest

from services.application.app.analysis.candidate_review import (
    CandidateReviewService,
)
from services.application.app.analysis.compare import CompareAction
from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.analysis.review_queue import (
    InMemoryReviewQueueRepository,
    ReviewQueueService,
    ReviewQueueStatus,
)
from services.application.app.analysis.service import (
    AnalysisNotFound,
    AnalysisService,
    InMemoryAnalysisRepository,
    InvalidCandidateStateTransition,
)
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryService,
)

EVENT = AnalysisCandidateType.EVENT_OBSERVATION


class _RecordingRemovalOutbox:
    def __init__(self):
        self.removed = []

    def enqueue_candidate_removed(self, *, project_id, candidate_id):
        self.removed.append((project_id, candidate_id))


def _candidate(candidate_id, *, project_id="p1", job_id="j1"):
    return AnalysisCandidate(
        id=candidate_id,
        project_id=project_id,
        job_id=job_id,
        task_id="t1",
        candidate_type=EVENT,
        action=AnalysisCandidateAction.CREATE,
        status=AnalysisCandidateStatus.NEEDS_REVIEW,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.5,
        source_ref_ids=("s1",),
        payload={"event": "the storm hit"},
    )


def _fixture(*candidate_ids, with_outbox=True, with_queue=True):
    analysis = AnalysisService(InMemoryAnalysisRepository())
    for cid in candidate_ids:
        analysis._repo.put_candidate(_candidate(cid), logical_key=f"lk-{cid}")
    memory = MemoryService(InMemoryMemoryRepository())
    outbox = _RecordingRemovalOutbox() if with_outbox else None
    queue = ReviewQueueService(InMemoryReviewQueueRepository()) if with_queue else None
    service = CandidateReviewService(
        analysis_service=analysis,
        memory_service=memory,
        removal_outbox=outbox,
        review_queue=queue,
    )
    return service, analysis, memory, outbox, queue


def _enqueue_conflict(queue, candidate_id, *, project_id="p1", job_id="j1"):
    queue.enqueue(
        project_id=project_id,
        job_id=job_id,
        candidate_id=candidate_id,
        candidate_type=EVENT,
        action=CompareAction.CONFLICT,
        matched_memory_id="mem-x",
        rationale="duplicate",
    )


class TransitionStateMachineTest(unittest.TestCase):
    """AnalysisService.transition_candidate — the deterministic edges."""

    def _analysis(self, cid="c1"):
        analysis = AnalysisService(InMemoryAnalysisRepository())
        analysis._repo.put_candidate(_candidate(cid), logical_key=f"lk-{cid}")
        return analysis

    def test_needs_review_to_confirmed_and_rejected_are_legal(self):
        for target in (
            AnalysisCandidateStatus.CONFIRMED,
            AnalysisCandidateStatus.REJECTED,
        ):
            analysis = self._analysis()
            t = analysis.transition_candidate(
                project_id="p1", candidate_id="c1", target=target
            )
            self.assertTrue(t.changed)
            self.assertEqual(t.candidate.status, target)
            self.assertEqual(
                analysis.get_candidate(project_id="p1", candidate_id="c1").status,
                target,
            )

    def test_same_status_is_idempotent_noop(self):
        # under/over-strict: re-applying the current status changes nothing.
        analysis = self._analysis()
        analysis.transition_candidate(
            project_id="p1", candidate_id="c1",
            target=AnalysisCandidateStatus.CONFIRMED,
        )
        replay = analysis.transition_candidate(
            project_id="p1", candidate_id="c1",
            target=AnalysisCandidateStatus.CONFIRMED,
        )
        self.assertFalse(replay.changed)
        self.assertEqual(replay.candidate.status, AnalysisCandidateStatus.CONFIRMED)

    def test_cross_terminal_and_backward_edges_are_rejected(self):
        # over-strict: confirmed→rejected, rejected→confirmed, confirmed→needs_review
        # must all raise (never silently overturn a review).
        illegal = [
            (AnalysisCandidateStatus.CONFIRMED, AnalysisCandidateStatus.REJECTED),
            (AnalysisCandidateStatus.REJECTED, AnalysisCandidateStatus.CONFIRMED),
            (AnalysisCandidateStatus.CONFIRMED, AnalysisCandidateStatus.NEEDS_REVIEW),
            # backward from a terminal (rejected→needs_review) must also raise —
            # a rejected candidate cannot be silently reopened.
            (AnalysisCandidateStatus.REJECTED, AnalysisCandidateStatus.NEEDS_REVIEW),
        ]
        for first, second in illegal:
            analysis = self._analysis()
            analysis.transition_candidate(
                project_id="p1", candidate_id="c1", target=first
            )
            with self.assertRaises(InvalidCandidateStateTransition):
                analysis.transition_candidate(
                    project_id="p1", candidate_id="c1", target=second
                )

    def test_missing_or_cross_project_candidate_raises(self):
        analysis = self._analysis()
        with self.assertRaises(AnalysisNotFound):
            analysis.transition_candidate(
                project_id="p1", candidate_id="ghost",
                target=AnalysisCandidateStatus.CONFIRMED,
            )
        with self.assertRaises(AnalysisNotFound):
            analysis.transition_candidate(
                project_id="p2", candidate_id="c1",
                target=AnalysisCandidateStatus.CONFIRMED,
            )


class ConfirmTest(unittest.TestCase):
    def test_confirm_transitions_promotes_deindexes_and_resolves(self):
        # under-strict: every confirm side effect fires exactly once.
        service, analysis, memory, outbox, queue = _fixture("c1")
        _enqueue_conflict(queue, "c1")
        result = service.confirm(project_id="p1", candidate_id="c1")
        self.assertEqual(result.status, AnalysisCandidateStatus.CONFIRMED)
        self.assertFalse(result.idempotent_replay)
        self.assertIsNotNone(result.memory_id)
        # candidate transitioned
        self.assertEqual(
            analysis.get_candidate(project_id="p1", candidate_id="c1").status,
            AnalysisCandidateStatus.CONFIRMED,
        )
        # promoted to canonical
        self.assertTrue(memory.is_candidate_promoted("p1", "c1"))
        # de-index enqueued
        self.assertEqual(outbox.removed, [("p1", "c1")])
        # conflict queue resolved (no longer open)
        self.assertEqual(queue.list_open("p1"), ())

    def test_confirm_replay_is_idempotent_without_duplicate_side_effects(self):
        # over-strict idempotency (D4): a second confirm repeats no de-index/queue.
        service, analysis, memory, outbox, queue = _fixture("c1")
        _enqueue_conflict(queue, "c1")
        service.confirm(project_id="p1", candidate_id="c1")
        replay = service.confirm(project_id="p1", candidate_id="c1")
        self.assertTrue(replay.idempotent_replay)
        self.assertIsNotNone(replay.memory_id)  # promotion replay still resolves
        self.assertEqual(outbox.removed, [("p1", "c1")])  # not duplicated

    def test_confirmed_candidate_leaves_the_retrievable_needs_review_set(self):
        # over-strict (retriever forward-defense → real path): a confirmed
        # candidate must drop out of list_needs_review_candidates, which is what
        # the candidate retriever re-derives authority from. Its knowledge is now
        # served by the canonical path instead (D5=A / (e) becomes a superset).
        service, analysis, memory, outbox, queue = _fixture("c1", "c2")
        self.assertEqual(
            {c.id for c in analysis.list_needs_review_candidates(project_id="p1")},
            {"c1", "c2"},
        )
        service.confirm(project_id="p1", candidate_id="c1")
        self.assertEqual(
            {c.id for c in analysis.list_needs_review_candidates(project_id="p1")},
            {"c2"},
        )

    def test_confirm_without_optional_deps_still_transitions(self):
        # backward-compat: no removal_outbox / no review_queue → transition works.
        service, analysis, memory, outbox, queue = _fixture(
            "c1", with_outbox=False, with_queue=False
        )
        result = service.confirm(project_id="p1", candidate_id="c1")
        self.assertEqual(result.status, AnalysisCandidateStatus.CONFIRMED)
        self.assertTrue(memory.is_candidate_promoted("p1", "c1"))


class RejectTest(unittest.TestCase):
    def test_reject_transitions_deindexes_dismisses_without_promotion(self):
        service, analysis, memory, outbox, queue = _fixture("c1")
        _enqueue_conflict(queue, "c1")
        result = service.reject(project_id="p1", candidate_id="c1")
        self.assertEqual(result.status, AnalysisCandidateStatus.REJECTED)
        self.assertIsNone(result.memory_id)
        self.assertFalse(result.idempotent_replay)
        # rejected candidate retained (D5) but not promoted
        self.assertEqual(
            analysis.get_candidate(project_id="p1", candidate_id="c1").status,
            AnalysisCandidateStatus.REJECTED,
        )
        self.assertFalse(memory.is_candidate_promoted("p1", "c1"))
        self.assertEqual(outbox.removed, [("p1", "c1")])
        # conflict queue dismissed
        self.assertEqual(queue.list_open("p1"), ())

    def test_reject_replay_is_idempotent(self):
        service, analysis, memory, outbox, queue = _fixture("c1")
        service.reject(project_id="p1", candidate_id="c1")
        replay = service.reject(project_id="p1", candidate_id="c1")
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(outbox.removed, [("p1", "c1")])  # not duplicated

    def test_confirm_then_reject_raises(self):
        service, *_ = _fixture("c1")
        service.confirm(project_id="p1", candidate_id="c1")
        with self.assertRaises(InvalidCandidateStateTransition):
            service.reject(project_id="p1", candidate_id="c1")


class ReviewQueueScopingTest(unittest.TestCase):
    def test_confirm_only_closes_its_own_candidate_conflicts(self):
        # over-strict: a transition must not close a different candidate's entry.
        service, analysis, memory, outbox, queue = _fixture("c1", "c2")
        _enqueue_conflict(queue, "c1")
        _enqueue_conflict(queue, "c2")
        service.confirm(project_id="p1", candidate_id="c1")
        open_ids = {e.candidate_id for e in queue.list_open("p1")}
        self.assertEqual(open_ids, {"c2"})


if __name__ == "__main__":
    unittest.main()
