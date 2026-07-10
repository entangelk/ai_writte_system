import unittest

from services.application.app.analysis.apply import (
    ApplyOutcome,
    MemoryApplyService,
    MissingMatchedMemory,
    UnknownCandidate,
)
from services.application.app.analysis.compare import ActionProposal, CompareAction
from services.application.app.analysis.review_queue import (
    InMemoryReviewQueueRepository,
    ReviewQueueService,
    ReviewQueueStatus,
)
from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.memory.models import MemoryStatus, PromotionMode
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryError,
    MemoryService,
)


CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION
EVENT = AnalysisCandidateType.EVENT_OBSERVATION


def _candidate(
    *,
    candidate_id="cand-1",
    project_id="project-1",
    job_id="job-current",
    candidate_type=CHARACTER,
    confidence=0.5,
    source_ref_ids=("source-ref-1",),
    payload=None,
    provenance=AnalysisProvenance.SOURCE_OBSERVED,
):
    if payload is None:
        payload = {"name": "Ariel", "observation": "brave"}
    return AnalysisCandidate(
        id=candidate_id,
        project_id=project_id,
        job_id=job_id,
        task_id="task-1",
        candidate_type=candidate_type,
        action=AnalysisCandidateAction.CREATE,
        status=AnalysisCandidateStatus.NEEDS_REVIEW,
        provenance=provenance,
        confidence=confidence,
        source_ref_ids=source_ref_ids,
        payload=payload,
    )


def _proposal(candidate, action, matched_memory_id=None):
    return ActionProposal(
        candidate_id=candidate.id,
        candidate_type=candidate.candidate_type,
        action=action,
        matched_memory_id=matched_memory_id,
        rationale="",
    )


def _service_and_apply():
    memory = MemoryService(InMemoryMemoryRepository())
    return memory, MemoryApplyService(memory_service=memory)


def _promote(memory, candidate):
    return memory.promote_candidate(
        project_id=candidate.project_id,
        candidate=candidate,
        mode=PromotionMode.MANUAL,
    ).memory


def _apply(apply_service, proposals, candidates):
    return apply_service.apply_proposals(
        project_id="project-1",
        proposals=tuple(proposals),
        candidates=tuple(candidates),
    )


class ApplyCreateTest(unittest.TestCase):
    def test_create_mints_new_canonical_version_one(self):
        memory, apply_service = _service_and_apply()
        candidate = _candidate(candidate_id="cur")
        [applied] = _apply(apply_service, [_proposal(candidate, CompareAction.CREATE)], [candidate])

        self.assertEqual(applied.outcome, ApplyOutcome.CREATED)
        self.assertFalse(applied.idempotent_replay)
        self.assertEqual(applied.version, 1)
        self.assertIsNone(applied.superseded_memory_id)
        entry = memory.get_memory(project_id="project-1", memory_id=applied.memory_id)
        self.assertEqual(entry.status, MemoryStatus.CANONICAL)
        self.assertIsNone(entry.supersedes)

    def test_create_is_idempotent_replay_on_reapply(self):
        memory, apply_service = _service_and_apply()
        candidate = _candidate(candidate_id="cur")
        [first] = _apply(apply_service, [_proposal(candidate, CompareAction.CREATE)], [candidate])
        [second] = _apply(apply_service, [_proposal(candidate, CompareAction.CREATE)], [candidate])
        self.assertFalse(first.idempotent_replay)
        self.assertTrue(second.idempotent_replay)
        self.assertEqual(first.memory_id, second.memory_id)
        self.assertEqual(len(memory.list_memories(project_id="project-1")), 1)


class ApplyUpdateTest(unittest.TestCase):
    def test_update_versions_prior_and_replaces_payload(self):
        memory, apply_service = _service_and_apply()
        prior_cand = _candidate(
            candidate_id="prior", job_id="job-prior",
            confidence=0.5, source_ref_ids=("source-ref-1",),
            payload={"name": "Ariel", "observation": "brave"},
        )
        prior = _promote(memory, prior_cand)
        update_cand = _candidate(
            candidate_id="cur", job_id="job-current",
            confidence=0.8, source_ref_ids=("source-ref-2",),
            payload={"name": "Ariel", "observation": "now cautious"},
            provenance=AnalysisProvenance.AI_INFERRED,
        )
        [applied] = _apply(
            apply_service,
            [_proposal(update_cand, CompareAction.UPDATE, matched_memory_id=prior.id)],
            [update_cand],
        )

        self.assertEqual(applied.outcome, ApplyOutcome.VERSIONED)
        self.assertEqual(applied.version, 2)
        self.assertEqual(applied.superseded_memory_id, prior.id)
        new_entry = memory.get_memory(project_id="project-1", memory_id=applied.memory_id)
        # payload replaced, source refs unioned, candidate confidence/provenance
        self.assertEqual(new_entry.payload["observation"], "now cautious")
        self.assertEqual(new_entry.source_ref_ids, ("source-ref-1", "source-ref-2"))
        self.assertEqual(new_entry.confidence, 0.8)
        self.assertEqual(new_entry.provenance, AnalysisProvenance.AI_INFERRED)
        self.assertEqual(new_entry.supersedes, prior.id)
        self.assertEqual(new_entry.scope, prior.scope)
        # append-only: prior version preserved immutably, now superseded
        old_entry = memory.get_memory(project_id="project-1", memory_id=prior.id)
        self.assertEqual(old_entry.status, MemoryStatus.SUPERSEDED)
        self.assertEqual(old_entry.payload["observation"], "brave")

    def test_update_without_matched_memory_raises(self):
        memory, apply_service = _service_and_apply()
        candidate = _candidate(candidate_id="cur")
        with self.assertRaises(MissingMatchedMemory):
            _apply(apply_service, [_proposal(candidate, CompareAction.UPDATE)], [candidate])

    def test_update_type_mismatch_rejected(self):
        # A character candidate must not version an event memory (body-supplied
        # pairing could otherwise corrupt a memory with a wrong-type payload).
        memory, apply_service = _service_and_apply()
        event_prior = _promote(
            memory,
            _candidate(
                candidate_id="prior-ev", job_id="job-prior", candidate_type=EVENT,
                payload={"event": "storm"},
            ),
        )
        char_cand = _candidate(candidate_id="cur", candidate_type=CHARACTER)
        with self.assertRaises(MemoryError):
            _apply(
                apply_service,
                [_proposal(char_cand, CompareAction.UPDATE, matched_memory_id=event_prior.id)],
                [char_cand],
            )

    def test_update_of_superseded_target_rejected(self):
        # SoT v1.6.44 rejection boundary: a versioned upsert must not target a
        # non-canonical (superseded) entry. Reach the branch the way it happens
        # in practice — two DIFFERENT candidates version the SAME prior: the
        # first supersedes it, so the second lands on a superseded target.
        # Under-strict guard: removing the `status is CANONICAL` check lets the
        # second update silently succeed, so this must re-fail.
        memory, apply_service = _service_and_apply()
        prior = _promote(memory, _candidate(candidate_id="prior", job_id="job-prior"))
        first = _candidate(
            candidate_id="c1", job_id="job-current",
            payload={"name": "Ariel", "observation": "v2"},
        )
        _apply(
            apply_service,
            [_proposal(first, CompareAction.UPDATE, matched_memory_id=prior.id)],
            [first],
        )
        # prior is now superseded; a second update pointed at it must be rejected.
        second = _candidate(
            candidate_id="c2", job_id="job-current",
            payload={"name": "Ariel", "observation": "v3"},
        )
        with self.assertRaises(MemoryError):
            _apply(
                apply_service,
                [_proposal(second, CompareAction.UPDATE, matched_memory_id=prior.id)],
                [second],
            )

    def test_update_takes_candidate_confidence_even_when_lower(self):
        # D3 over-strict guard: update confidence = candidate's, even when it is
        # LOWER than the prior's. This distinguishes update (candidate) from
        # add_evidence (max); a max rule would re-fail here.
        memory, apply_service = _service_and_apply()
        prior = _promote(
            memory,
            _candidate(candidate_id="prior", job_id="job-prior", confidence=0.8),
        )
        update_cand = _candidate(
            candidate_id="cur", job_id="job-current", confidence=0.4,
            payload={"name": "Ariel", "observation": "changed"},
        )
        [applied] = _apply(
            apply_service,
            [_proposal(update_cand, CompareAction.UPDATE, matched_memory_id=prior.id)],
            [update_cand],
        )
        new_entry = memory.get_memory(project_id="project-1", memory_id=applied.memory_id)
        self.assertEqual(new_entry.confidence, 0.4)

    def test_update_is_idempotent_replay(self):
        # D5: re-applying the same candidate does not create a third version nor
        # re-supersede — it replays the version already written.
        memory, apply_service = _service_and_apply()
        prior = _promote(memory, _candidate(candidate_id="prior", job_id="job-prior"))
        update_cand = _candidate(
            candidate_id="cur", job_id="job-current",
            payload={"name": "Ariel", "observation": "changed"},
        )
        prop = _proposal(update_cand, CompareAction.UPDATE, matched_memory_id=prior.id)
        [first] = _apply(apply_service, [prop], [update_cand])
        [second] = _apply(apply_service, [prop], [update_cand])
        self.assertFalse(first.idempotent_replay)
        self.assertTrue(second.idempotent_replay)
        self.assertEqual(first.memory_id, second.memory_id)
        self.assertEqual(second.version, 2)
        # exactly two entries total (prior + one new version)
        self.assertEqual(len(memory.list_memories(project_id="project-1")), 2)


class ApplyAddEvidenceTest(unittest.TestCase):
    def test_add_evidence_preserves_payload_unions_source_max_confidence(self):
        memory, apply_service = _service_and_apply()
        prior = _promote(
            memory,
            _candidate(
                candidate_id="prior", job_id="job-prior",
                confidence=0.6, source_ref_ids=("source-ref-1",),
                payload={"name": "Ariel", "observation": "brave"},
            ),
        )
        # add_evidence candidate has a LOWER confidence and a new source ref.
        ev_cand = _candidate(
            candidate_id="cur", job_id="job-current",
            confidence=0.3, source_ref_ids=("source-ref-2",),
            payload={"name": "Ariel", "observation": "brave"},
        )
        [applied] = _apply(
            apply_service,
            [_proposal(ev_cand, CompareAction.ADD_EVIDENCE, matched_memory_id=prior.id)],
            [ev_cand],
        )

        self.assertEqual(applied.outcome, ApplyOutcome.VERSIONED)
        self.assertEqual(applied.version, 2)
        new_entry = memory.get_memory(project_id="project-1", memory_id=applied.memory_id)
        # payload preserved, source unioned, confidence = max(prior, candidate)
        self.assertEqual(new_entry.payload["observation"], "brave")
        self.assertEqual(new_entry.source_ref_ids, ("source-ref-1", "source-ref-2"))
        self.assertEqual(new_entry.confidence, 0.6)

    def test_add_evidence_is_idempotent_replay(self):
        # D5: add_evidence shares the _versioned_upsert replay check with update;
        # locked explicitly for the add_evidence branch (no third version).
        memory, apply_service = _service_and_apply()
        prior = _promote(memory, _candidate(candidate_id="prior", job_id="job-prior"))
        ev_cand = _candidate(
            candidate_id="cur", job_id="job-current",
            source_ref_ids=("source-ref-2",),
            payload={"name": "Ariel", "observation": "brave"},
        )
        prop = _proposal(ev_cand, CompareAction.ADD_EVIDENCE, matched_memory_id=prior.id)
        [first] = _apply(apply_service, [prop], [ev_cand])
        [second] = _apply(apply_service, [prop], [ev_cand])
        self.assertFalse(first.idempotent_replay)
        self.assertTrue(second.idempotent_replay)
        self.assertEqual(first.memory_id, second.memory_id)
        self.assertEqual(second.version, 2)
        self.assertEqual(len(memory.list_memories(project_id="project-1")), 2)


class ApplySkipTest(unittest.TestCase):
    def test_no_change_writes_nothing(self):
        memory, apply_service = _service_and_apply()
        prior = _promote(memory, _candidate(candidate_id="prior", job_id="job-prior"))
        cand = _candidate(candidate_id="cur", job_id="job-current")
        [applied] = _apply(
            apply_service,
            [_proposal(cand, CompareAction.NO_CHANGE, matched_memory_id=prior.id)],
            [cand],
        )
        self.assertEqual(applied.outcome, ApplyOutcome.NO_CHANGE)
        self.assertIsNone(applied.memory_id)
        # store unchanged: only the prior canonical entry
        self.assertEqual(len(memory.list_memories(project_id="project-1")), 1)

    def test_conflict_is_review_only_no_write(self):
        memory, apply_service = _service_and_apply()
        cand = _candidate(candidate_id="cur")
        [applied] = _apply(
            apply_service, [_proposal(cand, CompareAction.CONFLICT)], [cand]
        )
        self.assertEqual(applied.outcome, ApplyOutcome.SKIPPED_REVIEW)
        self.assertIsNone(applied.memory_id)
        self.assertEqual(len(memory.list_memories(project_id="project-1")), 0)


class ApplyReviewQueuePersistenceTest(unittest.TestCase):
    """2B.4 follow-up: review-only (conflict) proposals persist to the queue."""

    def _service_apply_queue(self):
        memory = MemoryService(InMemoryMemoryRepository())
        queue = ReviewQueueService(InMemoryReviewQueueRepository())
        return memory, MemoryApplyService(
            memory_service=memory, review_queue=queue
        ), queue

    def test_conflict_persists_open_review_entry(self):
        # Under-strict guard: if apply stops enqueuing conflicts, the queue is
        # empty and this re-fails.
        memory, apply_service, queue = self._service_apply_queue()
        cand = _candidate(candidate_id="cur", job_id="job-current")
        [applied] = _apply(
            apply_service,
            [_proposal(cand, CompareAction.CONFLICT, matched_memory_id="mem-x")],
            [cand],
        )
        self.assertEqual(applied.outcome, ApplyOutcome.SKIPPED_REVIEW)
        [entry] = queue.list_open(project_id="project-1")
        self.assertEqual(entry.action, CompareAction.CONFLICT)
        self.assertEqual(entry.candidate_id, "cur")
        self.assertEqual(entry.job_id, "job-current")
        self.assertEqual(entry.matched_memory_id, "mem-x")
        self.assertEqual(entry.status, ReviewQueueStatus.OPEN)
        # still no canonical write (D7)
        self.assertEqual(len(memory.list_memories(project_id="project-1")), 0)

    def test_safe_actions_do_not_enqueue(self):
        # Over-strict guard: EVERY safe/handled action (create/update/
        # add_evidence/no_change) must NEVER land in the review queue — only
        # review-only actions do. All 4 enumerated boundary values are covered,
        # not just a sample, so an errant enqueue on any branch re-fails.
        memory, apply_service, queue = self._service_apply_queue()
        prior_u = _promote(
            memory, _candidate(candidate_id="prior-u", job_id="job-pu")
        )
        prior_e = _promote(
            memory, _candidate(candidate_id="prior-e", job_id="job-pe")
        )
        prior_n = _promote(
            memory, _candidate(candidate_id="prior-n", job_id="job-pn")
        )
        create_cand = _candidate(candidate_id="new")
        update_cand = _candidate(candidate_id="upd")
        evidence_cand = _candidate(candidate_id="evi")
        nochange_cand = _candidate(candidate_id="nc")
        _apply(
            apply_service,
            [
                _proposal(create_cand, CompareAction.CREATE),
                _proposal(
                    update_cand, CompareAction.UPDATE, matched_memory_id=prior_u.id
                ),
                _proposal(
                    evidence_cand,
                    CompareAction.ADD_EVIDENCE,
                    matched_memory_id=prior_e.id,
                ),
                _proposal(
                    nochange_cand,
                    CompareAction.NO_CHANGE,
                    matched_memory_id=prior_n.id,
                ),
            ],
            [create_cand, update_cand, evidence_cand, nochange_cand],
        )
        self.assertEqual(len(queue.list_open(project_id="project-1")), 0)

    def test_reapplying_same_conflict_does_not_duplicate(self):
        # D3: apply replay is idempotent; the deterministic entry id upserts.
        _, apply_service, queue = self._service_apply_queue()
        cand = _candidate(candidate_id="cur", job_id="job-current")
        proposal = _proposal(cand, CompareAction.CONFLICT)
        _apply(apply_service, [proposal], [cand])
        _apply(apply_service, [proposal], [cand])
        self.assertEqual(len(queue.list_open(project_id="project-1")), 1)

    def test_conflict_with_queue_and_ghost_candidate_raises(self):
        # When a review_queue is configured the conflict branch needs the
        # candidate (for its job_id), so a proposal referencing a candidate not
        # in the job raises UnknownCandidate — parallels the create-branch guard
        # and extends SoT v1.6.44 D6 (candidate 부재 거절) into the conflict path.
        # Nothing is enqueued on the raise.
        _, apply_service, queue = self._service_apply_queue()
        ghost = _candidate(candidate_id="ghost")
        with self.assertRaises(UnknownCandidate):
            _apply(apply_service, [_proposal(ghost, CompareAction.CONFLICT)], [])
        self.assertEqual(len(queue.list_open(project_id="project-1")), 0)

    def test_conflict_without_queue_is_still_review_only(self):
        # Backward-compat: no review_queue injected → behavior unchanged, no raise.
        memory, apply_service = _service_and_apply()
        cand = _candidate(candidate_id="cur")
        [applied] = _apply(
            apply_service, [_proposal(cand, CompareAction.CONFLICT)], [cand]
        )
        self.assertEqual(applied.outcome, ApplyOutcome.SKIPPED_REVIEW)


class ApplyUnknownCandidateTest(unittest.TestCase):
    def test_proposal_for_missing_candidate_raises(self):
        _, apply_service = _service_and_apply()
        ghost = _candidate(candidate_id="ghost")
        # ghost is referenced by the proposal but not in the candidate list.
        with self.assertRaises(UnknownCandidate):
            _apply(apply_service, [_proposal(ghost, CompareAction.CREATE)], [])


if __name__ == "__main__":
    unittest.main()
