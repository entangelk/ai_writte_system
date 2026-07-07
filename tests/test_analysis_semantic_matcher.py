"""Phase 2B.6 semantic identity resolution regressions.

A StubEmbedding maps specific texts to specific vectors so cosine similarity —
and therefore the threshold boundary — is deterministic. Covers: off-by-default
(seam absent → event/open_question stay always-create), on → semantic match →
judge, below-threshold → create, top-1 (D6=A), memory_type scope, self-exclusion,
canonical/stale filtering, and projection parity with the write path.
"""

import asyncio
import unittest

from services.application.app.analysis.compare import (
    AnalysisCompareService,
    CompareAction,
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
from services.application.app.memory.models import (
    MemoryEntry,
    MemoryStatus,
    PromotionMode,
)
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryService,
)


EVENT = AnalysisCandidateType.EVENT_OBSERVATION
OPEN_QUESTION = AnalysisCandidateType.OPEN_QUESTION_OBSERVATION


class StubEmbedding:
    """Deterministic text→vector map so cosine (and the threshold) is exact."""

    def __init__(self, table):
        self._table = table

    def embed(self, text: str) -> tuple[float, ...]:
        if text not in self._table:
            raise AssertionError(f"unexpected embed text: {text!r}")
        return self._table[text]


def _candidate(
    *,
    candidate_id="cand-1",
    job_id="job-current",
    candidate_type=EVENT,
    payload=None,
):
    if payload is None:
        payload = {"event": "a big storm struck the coast"}
    return AnalysisCandidate(
        id=candidate_id,
        project_id="project-1",
        job_id=job_id,
        task_id="task-1",
        candidate_type=candidate_type,
        action=AnalysisCandidateAction.CREATE,
        status=AnalysisCandidateStatus.NEEDS_REVIEW,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.5,
        source_ref_ids=("s1",),
        payload=payload,
    )


def _memory(
    memory_id, *, job_id, payload, candidate_type=EVENT,
    status=MemoryStatus.CANONICAL, project_id="project-1",
):
    return MemoryEntry(
        id=memory_id,
        project_id=project_id,
        memory_type=candidate_type,
        status=status,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.5,
        source_ref_ids=("s1",),
        payload=payload,
        version=1,
        analysis_job_id=job_id,
        source_candidate_id=f"c-{memory_id}",
        promotion_mode=PromotionMode.MANUAL,
        applied_threshold=None,
    )


def _seed(memory_service, vector_index, embeddings, entry):
    """Put a canonical memory in the store AND index its vector, mirroring the
    2B.5 write path (same projection + embedding)."""
    memory_service._repo.put_memory(entry)
    text = derive_memory_index_text(entry.memory_type, entry.payload)
    vector_index.upsert_memory_records(
        (build_memory_index_record(entry, text=text, vector=embeddings.embed(text)),)
    )


def _matcher(embeddings, threshold=0.9, limit=5):
    memory = MemoryService(InMemoryMemoryRepository())
    vector_index = InMemoryMemoryVectorIndexAdapter()
    matcher = EmbeddingSemanticMatcher(
        embeddings=embeddings,
        vector_search=vector_index,
        memory_service=memory,
        similarity_threshold=threshold,
        limit=limit,
    )
    return memory, vector_index, matcher


# Storm memory vs a similar storm candidate (close) vs a dissimilar one (far).
_TABLE = {
    "the storm hit the coast": (1.0, 0.0, 0.0),
    "a big storm struck the coast": (0.98, 0.2, 0.0),   # ~cosine 0.98 with storm
    "a peaceful quiet morning": (0.0, 1.0, 0.0),         # cosine 0 with storm
    "who betrayed the king?": (0.0, 0.0, 1.0),
}


class SemanticMatcherTest(unittest.TestCase):
    def test_similar_event_matches_prior_canonical(self):
        embeddings = StubEmbedding(_TABLE)
        memory, vector_index, matcher = _matcher(embeddings)
        _seed(
            memory, vector_index, embeddings,
            _memory("m1", job_id="job-prior", payload={"event": "the storm hit the coast"}),
        )
        matches = matcher.match(
            project_id="project-1", job_id="job-current",
            candidate=_candidate(payload={"event": "a big storm struck the coast"}),
        )
        self.assertEqual([m.id for m in matches], ["m1"])

    def test_dissimilar_event_below_threshold_no_match(self):
        # over-strict guard: a far candidate must not match → compare stays create.
        embeddings = StubEmbedding(_TABLE)
        memory, vector_index, matcher = _matcher(embeddings)
        _seed(
            memory, vector_index, embeddings,
            _memory("m1", job_id="job-prior", payload={"event": "the storm hit the coast"}),
        )
        matches = matcher.match(
            project_id="project-1", job_id="job-current",
            candidate=_candidate(payload={"event": "a peaceful quiet morning"}),
        )
        self.assertEqual(matches, ())

    def test_top_1_only(self):
        # Two above-threshold memories; D6=A returns only the single best.
        embeddings = StubEmbedding(
            {**_TABLE, "the storm hit the shore": (0.99, 0.1, 0.0)}
        )
        memory, vector_index, matcher = _matcher(embeddings)
        _seed(memory, vector_index, embeddings,
              _memory("m1", job_id="p1", payload={"event": "the storm hit the coast"}))
        _seed(memory, vector_index, embeddings,
              _memory("m2", job_id="p2", payload={"event": "the storm hit the shore"}))
        matches = matcher.match(
            project_id="project-1", job_id="job-current",
            candidate=_candidate(payload={"event": "a big storm struck the coast"}),
        )
        self.assertEqual(len(matches), 1)

    def test_memory_type_scoped(self):
        # An event candidate must not match an open_question memory even if the
        # vectors are close — query_similar filters by memory_type.
        embeddings = StubEmbedding(
            {"a big storm struck the coast": (1.0, 0.0, 0.0),
             "was it really a storm?": (1.0, 0.0, 0.0)}
        )
        memory, vector_index, matcher = _matcher(embeddings)
        _seed(memory, vector_index, embeddings,
              _memory("q1", job_id="p1", candidate_type=OPEN_QUESTION,
                      payload={"question": "was it really a storm?"}))
        matches = matcher.match(
            project_id="project-1", job_id="job-current",
            candidate=_candidate(payload={"event": "a big storm struck the coast"}),
        )
        self.assertEqual(matches, ())

    def test_self_exclusion(self):
        # A candidate must not match memory its own job promoted (D6).
        embeddings = StubEmbedding(_TABLE)
        memory, vector_index, matcher = _matcher(embeddings)
        _seed(memory, vector_index, embeddings,
              _memory("m1", job_id="job-current",
                      payload={"event": "the storm hit the coast"}))
        matches = matcher.match(
            project_id="project-1", job_id="job-current",
            candidate=_candidate(payload={"event": "a big storm struck the coast"}),
        )
        self.assertEqual(matches, ())

    def test_superseded_index_record_skipped(self):
        # A stale vector pointing at a now-superseded memory is skipped.
        embeddings = StubEmbedding(_TABLE)
        memory, vector_index, matcher = _matcher(embeddings)
        _seed(memory, vector_index, embeddings,
              _memory("m1", job_id="job-prior", status=MemoryStatus.SUPERSEDED,
                      payload={"event": "the storm hit the coast"}))
        matches = matcher.match(
            project_id="project-1", job_id="job-current",
            candidate=_candidate(payload={"event": "a big storm struck the coast"}),
        )
        self.assertEqual(matches, ())


class SemanticCompareIntegrationTest(unittest.TestCase):
    def test_semantic_match_flows_through_judge(self):
        embeddings = StubEmbedding(_TABLE)
        memory, vector_index, matcher = _matcher(embeddings)
        _seed(memory, vector_index, embeddings,
              _memory("m1", job_id="job-prior",
                      payload={"event": "the storm hit the coast"}))

        class FakeJudge:
            def judge(self, *, candidate, memory):
                return JudgeResult(action=CompareAction.ADD_EVIDENCE, rationale="same event")

        service = AnalysisCompareService(
            memory_service=memory, judge=FakeJudge(), semantic_matcher=matcher
        )
        proposals = asyncio.run(
            service.compare_job(
                project_id="project-1", job_id="job-current",
                candidates=(_candidate(payload={"event": "a big storm struck the coast"}),),
            )
        )
        self.assertEqual(proposals[0].action, CompareAction.ADD_EVIDENCE)
        self.assertEqual(proposals[0].matched_memory_id, "m1")

    def test_no_matcher_keeps_event_always_create(self):
        # over-strict guard: without a matcher (off by default), an event with a
        # semantically identical prior still gets create.
        memory = MemoryService(InMemoryMemoryRepository())
        memory._repo.put_memory(
            _memory("m1", job_id="job-prior",
                    payload={"event": "the storm hit the coast"})
        )
        service = AnalysisCompareService(memory_service=memory)  # no matcher
        proposals = asyncio.run(
            service.compare_job(
                project_id="project-1", job_id="job-current",
                candidates=(_candidate(payload={"event": "the storm hit the coast"}),),
            )
        )
        self.assertEqual(proposals[0].action, CompareAction.CREATE)
        self.assertIsNone(proposals[0].matched_memory_id)


if __name__ == "__main__":
    unittest.main()
