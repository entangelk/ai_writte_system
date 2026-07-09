"""b-2 increment 2: candidate retrieval layer (vector / lexical / hybrid).

Locks the candidate retrievers symmetric to the canonical ones: relevance-ranked
hits come from the candidate index, but the analysis store stays the authority
(every hit is reloaded via ``get_candidate``; only ``needs_review`` survivors are
returned). Guards run both directions:
- under-strict: a stale index record (removed candidate → AnalysisNotFound, or a
  transitioned candidate whose status left needs_review) must be dropped —
  removing the re-derivation or the needs_review filter reintroduces the phantom.
- over-strict: the vector merge is a single global pool (not per-type fairness),
  and hybrid RRF fuses both signals with id dedup.
"""

import asyncio
import types
import unittest

from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.analysis.service import (
    AnalysisNotFound,
    AnalysisService,
    InMemoryAnalysisRepository,
)
from services.application.app.context_search.models import (
    ContextBudget,
    ContextItemStatus,
    ContextNeed,
    ContextSearchPurpose,
    ContextSearchRequest,
    SearchPlan,
    SearchPlanStep,
    SearchTool,
)
from services.application.app.context_search.service import (
    ContextSearchService,
    HybridCandidateMemoryRetriever,
    LexicalCandidateMemoryRetriever,
    VectorCandidateMemoryRetriever,
)
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.indexing.candidate_index import (
    InMemoryCandidateVectorIndexAdapter,
    build_candidate_index_record,
)
from services.application.app.indexing.candidate_lexical_index import (
    InMemoryCandidateLexicalIndexAdapter,
    build_candidate_lexical_record,
)
from services.application.app.indexing.service import (
    DeterministicFakeEmbeddingProvider,
    InMemoryVectorIndexAdapter,
    SourceBlockIndexingService,
)


CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION
EVENT = AnalysisCandidateType.EVENT_OBSERVATION

_QUERY_VECTOR = (1.0, 0.0, 0.0)


class _FixedEmbeddings:
    def embed(self, text):
        return _QUERY_VECTOR


class _QuerySensitiveEmbeddings:
    _MAP = {"toward-a": (1.0, 0.0, 0.0), "toward-b": (0.0, 1.0, 0.0)}

    def embed(self, text):
        return self._MAP[text]


def _candidate(candidate_id, *, candidate_type=EVENT, payload=None,
               status=AnalysisCandidateStatus.NEEDS_REVIEW, project_id="project-1"):
    return AnalysisCandidate(
        id=candidate_id,
        project_id=project_id,
        job_id="job-1",
        task_id="task-1",
        candidate_type=candidate_type,
        action=AnalysisCandidateAction.CREATE,
        status=status,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.5,
        source_ref_ids=("s1",),
        payload=payload if payload is not None else {"event": candidate_id},
    )


class _FakeAnalysis:
    """Analysis-store stub keyed by candidate id (get_candidate only)."""

    def __init__(self, *candidates):
        self._by_id = {c.id: c for c in candidates}

    def get_candidate(self, *, project_id, candidate_id):
        candidate = self._by_id.get(candidate_id)
        if candidate is None or candidate.project_id != project_id:
            raise AnalysisNotFound("analysis candidate not found")
        return candidate


def _vector_index(*records):
    adapter = InMemoryCandidateVectorIndexAdapter()
    adapter.upsert_candidate_records(tuple(records))
    return adapter


def _record(candidate, *, vector, text="index-projection"):
    # text intentionally NOT the payload so authority re-derivation is provable.
    return build_candidate_index_record(candidate, text=text, vector=vector)


def _vector_retriever(analysis, index, embeddings=None):
    return VectorCandidateMemoryRetriever(
        analysis_service=analysis,
        embeddings=embeddings or _FixedEmbeddings(),
        vector_index=index,
    )


class VectorRetrieverTest(unittest.TestCase):
    def test_returns_store_candidates_in_relevance_order(self):
        high = _candidate("high", payload={"event": "fresh-high"})
        mid = _candidate("mid", payload={"event": "fresh-mid"})
        low = _candidate("low", payload={"event": "fresh-low"})
        analysis = _FakeAnalysis(high, mid, low)
        index = _vector_index(
            _record(high, vector=(1.0, 0.0, 0.0), text="stale-high"),
            _record(mid, vector=(0.6, 0.8, 0.0), text="stale-mid"),
            _record(low, vector=(0.0, 1.0, 0.0), text="stale-low"),
        )
        got = _vector_retriever(analysis, index).retrieve(
            project_id="project-1", query="storm", limit=3
        )
        self.assertEqual([c.id for c in got], ["high", "mid", "low"])
        # authority: returned objects carry the STORE payload, not the index text.
        self.assertEqual(got[0].payload, {"event": "fresh-high"})

    def test_respects_global_limit(self):
        a, b, c = _candidate("a"), _candidate("b"), _candidate("c")
        analysis = _FakeAnalysis(a, b, c)
        index = _vector_index(
            _record(a, vector=(1.0, 0.0, 0.0)),
            _record(b, vector=(0.6, 0.8, 0.0)),
            _record(c, vector=(0.0, 1.0, 0.0)),
        )
        got = _vector_retriever(analysis, index).retrieve(
            project_id="project-1", query="storm", limit=2
        )
        self.assertEqual([c.id for c in got], ["a", "b"])

    def test_query_drives_ranking(self):
        a, b = _candidate("mem-a"), _candidate("mem-b")
        analysis = _FakeAnalysis(a, b)
        index = _vector_index(
            _record(a, vector=(1.0, 0.0, 0.0)),
            _record(b, vector=(0.0, 1.0, 0.0)),
        )
        retriever = _vector_retriever(analysis, index, _QuerySensitiveEmbeddings())
        toward_a = retriever.retrieve(project_id="project-1", query="toward-a", limit=1)
        toward_b = retriever.retrieve(project_id="project-1", query="toward-b", limit=1)
        self.assertEqual([c.id for c in toward_a], ["mem-a"])
        self.assertEqual([c.id for c in toward_b], ["mem-b"])

    def test_stale_records_are_dropped(self):
        # under-strict: "ghost" (removed → AnalysisNotFound) and "old" (status left
        # needs_review) must both be dropped; only needs_review "live" survives.
        live = _candidate("live", payload={"event": "here"})
        ghost = _candidate("ghost")  # index record but absent from the store
        old_record_src = _candidate("old")  # for building the index record
        transitioned = types.SimpleNamespace(id="old", project_id="project-1",
                                             status=object())
        analysis = _FakeAnalysis(live, transitioned)  # ghost absent
        index = _vector_index(
            _record(ghost, vector=(1.0, 0.0, 0.0)),
            _record(old_record_src, vector=(0.9, 0.1, 0.0)),
            _record(live, vector=(0.5, 0.5, 0.0)),
        )
        got = _vector_retriever(analysis, index).retrieve(
            project_id="project-1", query="storm", limit=8
        )
        self.assertEqual([c.id for c in got], ["live"])

    def test_merges_all_types_into_one_global_pool(self):
        # over-strict: two character hits outrank the single event hit; a single
        # global pool with limit=2 returns BOTH character hits.
        char_a = _candidate("char-a", candidate_type=CHARACTER,
                            payload={"name": "A", "observation": "x"})
        char_b = _candidate("char-b", candidate_type=CHARACTER,
                            payload={"name": "B", "observation": "y"})
        event = _candidate("event", candidate_type=EVENT)
        analysis = _FakeAnalysis(char_a, char_b, event)
        index = _vector_index(
            _record(char_a, vector=(1.0, 0.0, 0.0)),
            _record(char_b, vector=(0.95, 0.31, 0.0)),
            _record(event, vector=(0.5, 0.87, 0.0)),
        )
        got = _vector_retriever(analysis, index).retrieve(
            project_id="project-1", query="storm", limit=2
        )
        self.assertEqual([c.id for c in got], ["char-a", "char-b"])


class LexicalRetrieverTest(unittest.TestCase):
    def _index(self, *candidates_and_text):
        adapter = InMemoryCandidateLexicalIndexAdapter()
        adapter.index_candidate_records(
            tuple(
                build_candidate_lexical_record(c, text=text)
                for c, text in candidates_and_text
            )
        )
        return adapter

    def test_needs_review_only_and_ranked(self):
        a = _candidate("a", payload={"event": "storm harbor"})
        b = _candidate("b", payload={"event": "storm"})
        analysis = _FakeAnalysis(a, b)
        index = self._index((a, "storm harbor"), (b, "storm"))
        got = LexicalCandidateMemoryRetriever(
            analysis_service=analysis, lexical_index=index
        ).retrieve(project_id="project-1", query="storm harbor", limit=5)
        self.assertEqual([c.id for c in got], ["a", "b"])

    def test_stale_doc_skipped(self):
        # under-strict: a doc whose candidate was removed → AnalysisNotFound → skip.
        ghost = _candidate("ghost", payload={"event": "storm"})
        analysis = _FakeAnalysis()  # ghost absent from the store
        index = self._index((ghost, "storm"))
        got = LexicalCandidateMemoryRetriever(
            analysis_service=analysis, lexical_index=index
        ).retrieve(project_id="project-1", query="storm", limit=5)
        self.assertEqual(got, ())

    def test_transitioned_candidate_is_dropped(self):
        # under-strict: a doc whose candidate left needs_review (Phase 6 forward
        # defense) must be dropped by the lexical leg too — symmetric to the
        # vector retriever's stale-isolation guard. The index doc resolves to a
        # candidate whose status is no longer needs_review, so it is skipped.
        indexed = _candidate("c1", payload={"event": "storm"})
        transitioned = types.SimpleNamespace(
            id="c1", project_id="project-1", status=object()
        )
        analysis = _FakeAnalysis(transitioned)
        index = self._index((indexed, "storm"))
        got = LexicalCandidateMemoryRetriever(
            analysis_service=analysis, lexical_index=index
        ).retrieve(project_id="project-1", query="storm", limit=5)
        self.assertEqual(got, ())


class _RankedRetriever:
    """A CandidateMemoryRetriever returning a fixed ranked list (for hybrid RRF)."""

    def __init__(self, candidates):
        self._candidates = tuple(candidates)

    def retrieve(self, *, project_id, query, limit):
        return self._candidates[:limit]


class HybridRRFTest(unittest.TestCase):
    def test_fuses_both_signals_and_dedups_by_id(self):
        a, b, c = _candidate("a"), _candidate("b"), _candidate("c")
        # vector ranks [a, b]; lexical ranks [b, c]. b is boosted by both signals
        # and must rank first; a and c each appear once (dedup by id).
        hybrid = HybridCandidateMemoryRetriever(
            vector_retriever=_RankedRetriever([a, b]),
            lexical_retriever=_RankedRetriever([b, c]),
        )
        got = hybrid.retrieve(project_id="project-1", query="storm", limit=5)
        self.assertEqual(got[0].id, "b")
        self.assertEqual({c.id for c in got}, {"a", "b", "c"})
        self.assertEqual(len(got), 3)  # dedup: b not duplicated

    def test_single_backend_degradation_surfaces_the_other(self):
        # over-strict: if one sub-retriever returns empty (an index leg not yet
        # drained, or a query that matches nothing on one signal), the other
        # still surfaces its hits — no crash, no false-empty when one signal has
        # results. Both directions: vector-only and lexical-only.
        a = _candidate("a")
        b = _candidate("b")
        vector_only = HybridCandidateMemoryRetriever(
            vector_retriever=_RankedRetriever([a]),
            lexical_retriever=_RankedRetriever(()),
        ).retrieve(project_id="project-1", query="storm", limit=5)
        self.assertEqual([c.id for c in vector_only], ["a"])
        lexical_only = HybridCandidateMemoryRetriever(
            vector_retriever=_RankedRetriever(()),
            lexical_retriever=_RankedRetriever([b]),
        ).retrieve(project_id="project-1", query="storm", limit=5)
        self.assertEqual([c.id for c in lexical_only], ["b"])


class _StaticPlanner:
    def __init__(self, plan):
        self.plan = plan

    def build_plan(self, request):
        return self.plan


class SeamInvarianceTest(unittest.TestCase):
    """Swapping the vector retriever for Mongo-direct changes nothing in the
    step/item/Gate path — a candidate_memory step still yields micro candidate
    items with a candidate pointer."""

    def test_vector_retriever_produces_micro_candidate_items(self):
        candidate = _candidate("c1", payload={"event": "the storm hit"})
        # Real analysis store so the candidate_memory Gate re-derivation resolves.
        analysis = AnalysisService(InMemoryAnalysisRepository())
        analysis._repo.put_candidate(candidate, logical_key="lk-c1")
        index = _vector_index(_record(candidate, vector=(1.0, 0.0, 0.0)))

        core_sot = CoreSotService(InMemoryCoreSotRepository())
        source_block_index = InMemoryVectorIndexAdapter()
        indexing = SourceBlockIndexingService(
            core_sot=core_sot,
            embeddings=DeterministicFakeEmbeddingProvider(),
            vector_index=source_block_index,
        )
        service = ContextSearchService(
            core_sot=core_sot,
            indexing_service=indexing,
            vector_search=source_block_index,
            embeddings=DeterministicFakeEmbeddingProvider(),
            planner=_StaticPlanner(
                SearchPlan(
                    plan_id="plan-1",
                    project_id="project-1",
                    steps=(
                        SearchPlanStep(
                            step_id="s1",
                            need=ContextNeed.CANDIDATE_MEMORY,
                            tools=(SearchTool.MONGO,),
                            query="storm",
                        ),
                    ),
                )
            ),
            candidate_memory_retriever=_vector_retriever(analysis, index),
        )
        request = ContextSearchRequest(
            project_id="project-1",
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            needs=(ContextNeed.CANDIDATE_MEMORY,),
            query="storm",
            current_position=None,
            context_budget=ContextBudget(max_tokens=10_000),
        )
        package = asyncio.run(service.build_context_package(request))
        self.assertEqual(package.macro_items, ())
        self.assertEqual(len(package.micro_evidence), 1)
        item = package.micro_evidence[0]
        self.assertEqual(item.pointer.document_id, "c1")
        self.assertEqual(item.status, ContextItemStatus.CANDIDATE)


if __name__ == "__main__":
    unittest.main()
