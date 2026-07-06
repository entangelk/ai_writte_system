import asyncio
import unittest

from services.application.app.analysis.compare import (
    ActionProposal,
    AnalysisCompareService,
    CompareAction,
    CompareJudgeNotConfigured,
    InvalidJudgeResult,
    JudgeResult,
)
from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.memory.models import PromotionMode
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
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
    payload=None,
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
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.5,
        source_ref_ids=("source-ref-1",),
        payload=payload,
    )


def _memory_service_with(*promoted_candidates):
    """Build a MemoryService and promote the given candidates to canonical."""
    service = MemoryService(InMemoryMemoryRepository())
    for candidate in promoted_candidates:
        service.promote_candidate(
            project_id=candidate.project_id,
            candidate=candidate,
            mode=PromotionMode.MANUAL,
        )
    return service


class FakeJudge:
    def __init__(self, action, rationale="judged"):
        self._action = action
        self._rationale = rationale
        self.calls = []

    def judge(self, *, candidate, memory):
        self.calls.append((candidate, memory))
        return JudgeResult(action=self._action, rationale=self._rationale)


def _compare(service, candidates):
    return asyncio.run(
        service.compare_job(
            project_id="project-1", job_id="job-current", candidates=tuple(candidates)
        )
    )


class CompareNoMatchTest(unittest.TestCase):
    def test_character_with_no_prior_is_create(self):
        service = AnalysisCompareService(memory_service=_memory_service_with())
        [proposal] = _compare(service, [_candidate()])
        self.assertEqual(proposal.action, CompareAction.CREATE)
        self.assertIsNone(proposal.matched_memory_id)

    def test_event_is_always_create_even_with_prior_event_memory(self):
        # D2=A: event has no scope key, so it never matches → always create,
        # even when a prior event memory exists in the project.
        prior_event = _candidate(
            candidate_id="prior-ev", job_id="job-prior", candidate_type=EVENT,
            payload={"event": "the storm hit"},
        )
        service = AnalysisCompareService(
            memory_service=_memory_service_with(prior_event)
        )
        current_event = _candidate(
            candidate_id="cur-ev", candidate_type=EVENT,
            payload={"event": "the storm hit"},
        )
        [proposal] = _compare(service, [current_event])
        self.assertEqual(proposal.action, CompareAction.CREATE)


class CompareMatchTest(unittest.TestCase):
    def test_single_match_is_labeled_by_judge(self):
        prior = _candidate(candidate_id="prior", job_id="job-prior")
        judge = FakeJudge(CompareAction.ADD_EVIDENCE, rationale="corroborates")
        service = AnalysisCompareService(
            memory_service=_memory_service_with(prior), judge=judge
        )

        [proposal] = _compare(service, [_candidate(candidate_id="cur")])

        self.assertEqual(proposal.action, CompareAction.ADD_EVIDENCE)
        self.assertEqual(proposal.rationale, "corroborates")
        self.assertIsNotNone(proposal.matched_memory_id)
        self.assertEqual(len(judge.calls), 1)

    def test_match_uses_normalized_name(self):
        prior = _candidate(
            candidate_id="prior", job_id="job-prior",
            payload={"name": "Ariel Song", "observation": "x"},
        )
        judge = FakeJudge(CompareAction.NO_CHANGE)
        service = AnalysisCompareService(
            memory_service=_memory_service_with(prior), judge=judge
        )
        # Different spacing/case still resolves to the same identity.
        current = _candidate(
            candidate_id="cur", payload={"name": "  ariel   song", "observation": "y"}
        )

        [proposal] = _compare(service, [current])

        self.assertEqual(proposal.action, CompareAction.NO_CHANGE)
        self.assertEqual(len(judge.calls), 1)

    def test_match_needs_judge_else_503_signal(self):
        prior = _candidate(candidate_id="prior", job_id="job-prior")
        service = AnalysisCompareService(
            memory_service=_memory_service_with(prior), judge=None
        )
        with self.assertRaises(CompareJudgeNotConfigured):
            _compare(service, [_candidate(candidate_id="cur")])

    def test_judge_returning_create_is_rejected(self):
        # Over-strict guard: create is deterministic (no-match only); the judge
        # must never mint it for a matched pair.
        prior = _candidate(candidate_id="prior", job_id="job-prior")
        service = AnalysisCompareService(
            memory_service=_memory_service_with(prior),
            judge=FakeJudge(CompareAction.CREATE),
        )
        with self.assertRaises(InvalidJudgeResult):
            _compare(service, [_candidate(candidate_id="cur")])

    def test_duplicate_canonical_identity_is_conflict_without_judge(self):
        # Two canonical memories share the identity (2B.1 allowed duplicate
        # canonical): ambiguous store state → deterministic conflict, no judge.
        p1 = _candidate(candidate_id="p1", job_id="job-a")
        p2 = _candidate(candidate_id="p2", job_id="job-b")
        service = AnalysisCompareService(
            memory_service=_memory_service_with(p1, p2), judge=None
        )
        [proposal] = _compare(service, [_candidate(candidate_id="cur")])
        self.assertEqual(proposal.action, CompareAction.CONFLICT)
        self.assertIsNone(proposal.matched_memory_id)


class CompareSelfExclusionTest(unittest.TestCase):
    def test_self_exclusion_is_two_directional(self):
        # D6: a candidate whose own job already promoted the matching memory
        # must not match it (would be perpetual no_change noise).
        own = _candidate(candidate_id="own", job_id="job-current")
        judge = FakeJudge(CompareAction.UPDATE)
        service = AnalysisCompareService(
            memory_service=_memory_service_with(own), judge=judge
        )
        # Same job as the promoted memory → self excluded → create, judge unused.
        [proposal] = _compare(service, [_candidate(candidate_id="cur", job_id="job-current")])
        self.assertEqual(proposal.action, CompareAction.CREATE)
        self.assertEqual(len(judge.calls), 0)

        # Under-strict guard: a memory promoted by a DIFFERENT job is a real
        # prior and must match (judge invoked).
        other = _candidate(candidate_id="other", job_id="job-prior")
        service2 = AnalysisCompareService(
            memory_service=_memory_service_with(other), judge=FakeJudge(CompareAction.UPDATE)
        )
        [proposal2] = _compare(service2, [_candidate(candidate_id="cur2", job_id="job-current")])
        self.assertEqual(proposal2.action, CompareAction.UPDATE)


if __name__ == "__main__":
    unittest.main()
