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
from services.application.app.analysis.semantic_matcher import (
    EmbeddingSemanticMatcher,
)
from services.application.app.indexing.memory_index import (
    InMemoryMemoryVectorIndexAdapter,
    build_memory_index_record,
    derive_memory_index_text,
)
from services.application.app.memory.models import PromotionMode
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryService,
)


class StubEmbedding:
    """Deterministic text→vector map so cosine (and the threshold) is exact."""

    def __init__(self, table):
        self._table = table

    def embed(self, text: str) -> tuple[float, ...]:
        if text not in self._table:
            raise AssertionError(f"unexpected embed text: {text!r}")
        return self._table[text]


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


class FakeIdentityVerifier:
    def __init__(self, supports):
        self.supports = supports
        self.calls = []

    def supports_same_identity(self, *, candidate, memory):
        self.calls.append((candidate, memory))
        return self.supports


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

    def test_character_with_different_identity_is_create(self):
        # Negative direction of scope matching (G1): a prior character memory
        # with a DIFFERENT name must not match → create, judge never consulted.
        prior = _candidate(
            candidate_id="prior", job_id="job-prior",
            payload={"name": "Bob", "observation": "x"},
        )
        judge = FakeJudge(CompareAction.UPDATE)
        service = AnalysisCompareService(
            memory_service=_memory_service_with(prior), judge=judge
        )
        [proposal] = _compare(
            service,
            [_candidate(candidate_id="cur", payload={"name": "Ariel", "observation": "y"})],
        )
        self.assertEqual(proposal.action, CompareAction.CREATE)
        self.assertEqual(len(judge.calls), 0)

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
    def test_same_name_below_identity_floor_is_conflict_without_judge(self):
        prior = _candidate(candidate_id="prior", job_id="job-prior")
        judge = FakeJudge(CompareAction.UPDATE)
        verifier = FakeIdentityVerifier(False)
        service = AnalysisCompareService(
            memory_service=_memory_service_with(prior), judge=judge,
            homonym_verifier=verifier,
        )
        [proposal] = _compare(service, [_candidate(candidate_id="cur")])
        self.assertEqual(proposal.action, CompareAction.CONFLICT)
        self.assertEqual(len(verifier.calls), 1)
        self.assertEqual(judge.calls, [])

    def test_same_name_above_identity_floor_keeps_judge_path(self):
        prior = _candidate(candidate_id="prior", job_id="job-prior")
        judge = FakeJudge(CompareAction.UPDATE)
        service = AnalysisCompareService(
            memory_service=_memory_service_with(prior), judge=judge,
            homonym_verifier=FakeIdentityVerifier(True),
        )
        [proposal] = _compare(service, [_candidate(candidate_id="cur")])
        self.assertEqual(proposal.action, CompareAction.UPDATE)
        self.assertEqual(len(judge.calls), 1)

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


class CharacterAliasTest(unittest.TestCase):
    """Phase 2B.7 (c): character alias detection (D1=A/D2=A/D3=A).

    When the deterministic name key finds no same-name canonical, a separately-
    thresholded semantic matcher checks whether a differently-named canonical
    character is the same subject. A hit → conflict (review), never an automatic
    merge (D1=A); off by default (D5). The matcher reuses 2B.6's
    EmbeddingSemanticMatcher over the same memory_vectors projection.
    """

    # Deterministic text→vector map keyed on the character write projection
    # (`derive_memory_index_text` = "name\nobservation").
    _TABLE = {
        "김철수\n검을 든 기사": (1.0, 0.0, 0.0),
        "철수\n검을 든 기사": (0.99, 0.1, 0.0),      # ~0.995: same subject, alias
        "영희\n조용한 사서": (0.0, 1.0, 0.0),         # far: different subject
        "Ariel\nbrave": (0.5, 0.5, 0.0),
    }

    def _alias_matcher(self, canonical_payload, *, table, threshold=0.9,
                       canonical_job="job-prior"):
        memory = _memory_service_with(
            _candidate(candidate_id="prior", job_id=canonical_job,
                       payload=canonical_payload)
        )
        vector_index = InMemoryMemoryVectorIndexAdapter()
        embeddings = StubEmbedding(table)
        for entry in memory.list_memories(project_id="project-1"):
            text = derive_memory_index_text(entry.memory_type, entry.payload)
            vector_index.upsert_memory_records(
                (build_memory_index_record(
                    entry, text=text, vector=embeddings.embed(text)),)
            )
        matcher = EmbeddingSemanticMatcher(
            embeddings=embeddings, vector_search=vector_index,
            memory_service=memory, similarity_threshold=threshold,
        )
        canonical_id = memory.list_memories(project_id="project-1")[0].id
        return memory, matcher, canonical_id

    def test_alias_surfaces_conflict_without_auto_merge(self):
        # Under-strict: a differently-named but semantically-near canonical is
        # detected. Over-strict (D1=A): the action is conflict, NOT an automatic
        # update/merge — and the judge is never consulted on the alias path.
        memory, matcher, canonical_id = self._alias_matcher(
            {"name": "김철수", "observation": "검을 든 기사"}, table=self._TABLE,
        )
        judge = FakeJudge(CompareAction.UPDATE)
        service = AnalysisCompareService(
            memory_service=memory, judge=judge, alias_matcher=matcher
        )
        [proposal] = _compare(
            service,
            [_candidate(candidate_id="cur",
                        payload={"name": "철수", "observation": "검을 든 기사"})],
        )
        self.assertEqual(proposal.action, CompareAction.CONFLICT)
        self.assertEqual(proposal.matched_memory_id, canonical_id)
        self.assertEqual(len(judge.calls), 0)

    def test_alias_below_threshold_is_create(self):
        # Over-strict: a far character (different subject) must not be flagged as
        # an alias → stays create.
        memory, matcher, _ = self._alias_matcher(
            {"name": "김철수", "observation": "검을 든 기사"}, table=self._TABLE,
        )
        service = AnalysisCompareService(
            memory_service=memory, alias_matcher=matcher
        )
        [proposal] = _compare(
            service,
            [_candidate(candidate_id="cur",
                        payload={"name": "영희", "observation": "조용한 사서"})],
        )
        self.assertEqual(proposal.action, CompareAction.CREATE)
        self.assertIsNone(proposal.matched_memory_id)

    def test_alias_off_by_default_is_create(self):
        # Over-strict (D5): without an alias matcher, a differently-named but
        # semantically-identical prior still gets create — deterministic only.
        memory, _, _ = self._alias_matcher(
            {"name": "김철수", "observation": "검을 든 기사"}, table=self._TABLE,
        )
        service = AnalysisCompareService(memory_service=memory)  # no alias matcher
        [proposal] = _compare(
            service,
            [_candidate(candidate_id="cur",
                        payload={"name": "철수", "observation": "검을 든 기사"})],
        )
        self.assertEqual(proposal.action, CompareAction.CREATE)

    def test_alias_self_exclusion_same_job(self):
        # Under-strict (D6 in the alias path): when the canonical was promoted by
        # the SAME job as the candidate, self-exclusion drops it — the alias path
        # must not surface a conflict against memory this very job created. This
        # is the exact scenario the live smoke first tripped on (a differently-
        # named same-subject pair that WOULD clear the threshold, yet must not
        # match because it is the candidate's own job's promotion).
        memory, matcher, _ = self._alias_matcher(
            {"name": "김철수", "observation": "검을 든 기사"}, table=self._TABLE,
            canonical_job="job-current",  # same job as _compare's job-current
        )
        service = AnalysisCompareService(
            memory_service=memory, alias_matcher=matcher
        )
        [proposal] = _compare(
            service,
            [_candidate(candidate_id="cur", job_id="job-current",
                        payload={"name": "철수", "observation": "검을 든 기사"})],
        )
        self.assertEqual(proposal.action, CompareAction.CREATE)

    def test_alias_matcher_does_not_affect_scopeless_candidates(self):
        # Over-strict (D2=A): the alias seam is character-only (scope is not
        # None). With an alias matcher configured but no semantic matcher, an
        # event candidate (scope None) must stay always-create — the alias branch
        # must not fire for scope-less types. The StubEmbedding table omits the
        # event text, so a wrongful alias.match() on it would raise.
        memory, matcher, _ = self._alias_matcher(
            {"name": "김철수", "observation": "검을 든 기사"}, table=self._TABLE,
        )
        service = AnalysisCompareService(
            memory_service=memory, alias_matcher=matcher
        )
        [proposal] = _compare(
            service,
            [_candidate(candidate_id="ev", candidate_type=EVENT,
                        payload={"event": "the storm hit"})],
        )
        self.assertEqual(proposal.action, CompareAction.CREATE)

    def test_same_name_uses_deterministic_path_not_alias(self):
        # Over-strict: a same-name candidate matches deterministically (name key),
        # so the alias matcher must NOT be consulted. The StubEmbedding table
        # omits the candidate text, so any wrongful alias.match() call raises.
        memory, matcher, _ = self._alias_matcher(
            {"name": "Ariel", "observation": "brave"},
            table={"Ariel\nbrave": (1.0, 0.0, 0.0)},  # no candidate-text entry
        )
        judge = FakeJudge(CompareAction.UPDATE)
        service = AnalysisCompareService(
            memory_service=memory, judge=judge, alias_matcher=matcher
        )
        [proposal] = _compare(
            service,
            [_candidate(candidate_id="cur",
                        payload={"name": "Ariel", "observation": "bold"})],
        )
        # Deterministic name-key match → judge path, alias never touched.
        self.assertEqual(proposal.action, CompareAction.UPDATE)
        self.assertEqual(len(judge.calls), 1)


if __name__ == "__main__":
    unittest.main()
