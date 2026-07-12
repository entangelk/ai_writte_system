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
    InvalidAnalysisCandidate,
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
    return queue.enqueue(
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

    def test_superseded_is_not_a_transition_target(self):
        # over-strict (v1.6.66): SUPERSEDED is edit-only; it must never be
        # reachable through the confirm/reject transition channel, or a caller
        # could orphan a candidate without minting its replacement version.
        analysis = self._analysis()
        with self.assertRaises(InvalidCandidateStateTransition):
            analysis.transition_candidate(
                project_id="p1", candidate_id="c1",
                target=AnalysisCandidateStatus.SUPERSEDED,
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


class EditTest(unittest.TestCase):
    """Phase 6 candidate edit (v1.6.66): edit mints a confirmed successor version
    (append-only), supersedes the original, promotes to canonical, de-indexes the
    original, and resolves its conflicts. Guards run both directions. See
    docs/plans/06-candidate-edit-decisions.md."""

    def test_edit_mints_confirmed_version_supersedes_and_promotes(self):
        # under-strict: every edit side effect fires exactly once.
        service, analysis, memory, outbox, queue = _fixture("c1")
        entry = _enqueue_conflict(queue, "c1")
        result = service.edit(
            project_id="p1", candidate_id="c1",
            payload={"event": "the storm passed"},
        )
        self.assertEqual(result.original_candidate_id, "c1")
        self.assertNotEqual(result.candidate_id, "c1")
        self.assertEqual(result.status, AnalysisCandidateStatus.CONFIRMED)
        self.assertFalse(result.idempotent_replay)
        self.assertIsNotNone(result.memory_id)
        # successor is a confirmed version linked to the original with the edit
        successor = analysis.get_candidate(
            project_id="p1", candidate_id=result.candidate_id
        )
        self.assertEqual(successor.status, AnalysisCandidateStatus.CONFIRMED)
        self.assertEqual(successor.supersedes_candidate_id, "c1")
        self.assertEqual(dict(successor.payload), {"event": "the storm passed"})
        # original retained as superseded (audit history, D3)
        self.assertEqual(
            analysis.get_candidate(project_id="p1", candidate_id="c1").status,
            AnalysisCandidateStatus.SUPERSEDED,
        )
        # canonical promoted, linked to the SUCCESSOR (not the original)
        self.assertTrue(memory.is_candidate_promoted("p1", result.candidate_id))
        self.assertFalse(memory.is_candidate_promoted("p1", "c1"))
        # original de-indexed; edit is an approval → conflict resolved
        self.assertEqual(outbox.removed, [("p1", "c1")])
        self.assertEqual(queue.list_open("p1"), ())
        # over-strict (matrix row 7): the entry must be RESOLVED, not DISMISSED —
        # list_open() emptiness alone cannot tell the two apart, so assert the
        # terminal status directly (edit is an approval, like confirm, not reject).
        self.assertIs(
            queue.get(project_id="p1", entry_id=entry.id).status,
            ReviewQueueStatus.RESOLVED,
        )

    def test_edit_preserves_source_provenance_confidence(self):
        # under/over: only the payload changes; grounding is inherited (D5).
        service, analysis, memory, outbox, queue = _fixture("c1")
        result = service.edit(
            project_id="p1", candidate_id="c1", payload={"event": "corrected"}
        )
        original = _candidate("c1")
        successor = analysis.get_candidate(
            project_id="p1", candidate_id=result.candidate_id
        )
        self.assertEqual(successor.provenance, original.provenance)
        self.assertEqual(successor.confidence, original.confidence)
        self.assertEqual(successor.source_ref_ids, original.source_ref_ids)

    def test_edit_replay_is_idempotent_without_duplicate_side_effects(self):
        # over-strict idempotency (D4): a second edit returns the same successor
        # with no duplicate version/promotion/de-index.
        service, analysis, memory, outbox, queue = _fixture("c1")
        first = service.edit(
            project_id="p1", candidate_id="c1", payload={"event": "v2"}
        )
        replay = service.edit(
            project_id="p1", candidate_id="c1", payload={"event": "v2"}
        )
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.candidate_id, first.candidate_id)
        self.assertEqual(replay.memory_id, first.memory_id)
        self.assertEqual(outbox.removed, [("p1", "c1")])  # not duplicated

    def test_edit_is_one_shot_second_payload_replays_first_version(self):
        # over-strict: an original is edited at most once; a different payload
        # replays the first successor rather than minting a second version.
        service, analysis, memory, outbox, queue = _fixture("c1")
        first = service.edit(
            project_id="p1", candidate_id="c1", payload={"event": "v2"}
        )
        second = service.edit(
            project_id="p1", candidate_id="c1", payload={"event": "v3"}
        )
        self.assertTrue(second.idempotent_replay)
        self.assertEqual(second.candidate_id, first.candidate_id)
        successor = analysis.get_candidate(
            project_id="p1", candidate_id=first.candidate_id
        )
        self.assertEqual(dict(successor.payload), {"event": "v2"})

    def test_edit_drops_original_and_successor_from_needs_review_set(self):
        # over-strict (retriever forward-defense): neither the superseded original
        # nor the confirmed successor surfaces as a candidate.
        service, analysis, memory, outbox, queue = _fixture("c1", "c2")
        result = service.edit(
            project_id="p1", candidate_id="c1", payload={"event": "v2"}
        )
        needs_review = {
            c.id for c in analysis.list_needs_review_candidates(project_id="p1")
        }
        self.assertEqual(needs_review, {"c2"})
        self.assertNotIn(result.candidate_id, needs_review)

    def test_edit_invalid_payload_rejected_original_unchanged(self):
        # under/over: a schema-invalid edit raises and mints/supersedes nothing.
        service, analysis, memory, outbox, queue = _fixture("c1")
        with self.assertRaises(InvalidAnalysisCandidate):
            service.edit(
                project_id="p1", candidate_id="c1",
                payload={"event": "x", "extra": "y"},
            )
        self.assertEqual(
            analysis.get_candidate(project_id="p1", candidate_id="c1").status,
            AnalysisCandidateStatus.NEEDS_REVIEW,
        )
        self.assertEqual(outbox.removed, [])

    def test_edit_non_needs_review_candidate_raises(self):
        # over-strict: a confirmed (terminal) candidate cannot be edited.
        service, analysis, memory, outbox, queue = _fixture("c1")
        service.confirm(project_id="p1", candidate_id="c1")
        with self.assertRaises(InvalidCandidateStateTransition):
            service.edit(
                project_id="p1", candidate_id="c1", payload={"event": "v2"}
            )

    def test_edit_without_optional_deps_still_edits(self):
        # backward-compat: no removal_outbox / no review_queue → edit works.
        service, analysis, memory, outbox, queue = _fixture(
            "c1", with_outbox=False, with_queue=False
        )
        result = service.edit(
            project_id="p1", candidate_id="c1", payload={"event": "v2"}
        )
        self.assertEqual(result.status, AnalysisCandidateStatus.CONFIRMED)
        self.assertTrue(memory.is_candidate_promoted("p1", result.candidate_id))

    def test_missing_or_cross_project_edit_raises(self):
        service, analysis, memory, outbox, queue = _fixture("c1")
        with self.assertRaises(AnalysisNotFound):
            service.edit(
                project_id="p1", candidate_id="ghost", payload={"event": "v2"}
            )
        with self.assertRaises(AnalysisNotFound):
            service.edit(
                project_id="p2", candidate_id="c1", payload={"event": "v2"}
            )


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
