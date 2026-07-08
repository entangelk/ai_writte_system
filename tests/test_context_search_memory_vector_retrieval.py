"""Writing canonical inclusion — vector retrieval layer (⑤ §5 B, D2 follow-up).

Locks the ``VectorCanonicalMemoryRetriever``: relevance-ranked hits come from the
``memory_vectors`` index, but the memory store stays the authority (every hit is
reloaded via ``get_memory``; only ``CANONICAL`` survivors are returned). The three
memory types are queried separately and merged into ONE relevance-ranked pool with
a global limit (owner D2: single pool for the MVP, kept separable).

Guards run both directions:
- under-strict: a stale vector (deleted or superseded memory whose vector lingers)
  must be dropped — dropping the ``get_memory`` re-derivation or the ``CANONICAL``
  filter reintroduces the phantom and re-fails ``test_stale_vectors_are_dropped``.
- over-strict: the merge must be a single global pool, not per-type fairness —
  a round-robin/one-per-type strategy would pick a lower-similarity item over a
  second same-type hit and re-fail ``test_merges_all_types_into_one_global_pool``.
"""

import asyncio
import unittest

from services.application.app.analysis.models import (
    AnalysisCandidateType,
    AnalysisProvenance,
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
    VectorCanonicalMemoryRetriever,
)
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.indexing.memory_index import (
    InMemoryMemoryVectorIndexAdapter,
    build_memory_index_record,
)
from services.application.app.indexing.service import (
    DeterministicFakeEmbeddingProvider,
    InMemoryVectorIndexAdapter,
    MEMORIES_COLLECTION,
    SourceBlockIndexingService,
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


CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION
EVENT = AnalysisCandidateType.EVENT_OBSERVATION
OPEN_QUESTION = AnalysisCandidateType.OPEN_QUESTION_OBSERVATION

# Query embedding is fixed; record vectors are hand-set so cosine order is exact.
_QUERY_VECTOR = (1.0, 0.0, 0.0)


class _FixedEmbeddings:
    """Embeds every query to a fixed vector so record cosine order is exact."""

    def embed(self, text: str) -> tuple[float, ...]:
        return _QUERY_VECTOR


class _QuerySensitiveEmbeddings:
    """Maps each query string to a distinct vector so the query provably drives
    ranking (unlike the query-agnostic _FixedEmbeddings). A retriever that ignored
    embed(query) and hardcoded a constant vector would rank identically for every
    query and fail one direction of test_query_drives_ranking."""

    _MAP = {"toward-a": (1.0, 0.0, 0.0), "toward-b": (0.0, 1.0, 0.0)}

    def embed(self, text: str) -> tuple[float, ...]:
        return self._MAP[text]


def _memory(memory_id, *, memory_type=EVENT, payload=None,
            status=MemoryStatus.CANONICAL, project_id="project-1", version=1):
    return MemoryEntry(
        id=memory_id,
        project_id=project_id,
        memory_type=memory_type,
        status=status,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.5,
        source_ref_ids=("s1",),
        payload=payload if payload is not None else {"event": memory_id},
        version=version,
        analysis_job_id="job-1",
        source_candidate_id=f"c-{memory_id}",
        promotion_mode=PromotionMode.MANUAL,
        applied_threshold=None,
    )


def _index(*records):
    adapter = InMemoryMemoryVectorIndexAdapter()
    adapter.upsert_memory_records(tuple(records))
    return adapter


def _record(memory, *, vector, text="index-projection"):
    # ``text`` is intentionally NOT the store payload so the authority
    # re-derivation (return the store entry, not the index record) is provable.
    return build_memory_index_record(memory, text=text, vector=vector)


def _store(*entries):
    memory = MemoryService(InMemoryMemoryRepository())
    for entry in entries:
        memory._repo.put_memory(entry)
    return memory


def _retriever(memory, vector_index):
    return VectorCanonicalMemoryRetriever(
        memory_service=memory,
        embeddings=_FixedEmbeddings(),
        vector_index=vector_index,
    )


class VectorRetrieverRelevanceTest(unittest.TestCase):
    def test_returns_store_entries_in_relevance_order(self):
        # Authority re-derivation + relevance order: hits ranked by cosine, then
        # each id reloaded from the store so the returned objects are MemoryEntry
        # (with payload) — NOT the index records (whose text is a stale
        # projection). If the retriever returned index records instead, the
        # ``.payload`` assertion would raise AttributeError.
        high = _memory("high", payload={"event": "fresh-high"})
        mid = _memory("mid", payload={"event": "fresh-mid"})
        low = _memory("low", payload={"event": "fresh-low"})
        memory = _store(high, mid, low)
        vector_index = _index(
            _record(high, vector=(1.0, 0.0, 0.0), text="stale-index-high"),
            _record(mid, vector=(0.6, 0.8, 0.0), text="stale-index-mid"),
            _record(low, vector=(0.0, 1.0, 0.0), text="stale-index-low"),
        )
        got = _retriever(memory, vector_index).retrieve(
            project_id="project-1", query="storm", limit=3
        )
        self.assertEqual([e.id for e in got], ["high", "mid", "low"])
        # authority: the returned objects carry the STORE payload, not the index.
        self.assertEqual(got[0].payload, {"event": "fresh-high"})

    def test_respects_global_limit(self):
        high = _memory("high")
        mid = _memory("mid")
        low = _memory("low")
        memory = _store(high, mid, low)
        vector_index = _index(
            _record(high, vector=(1.0, 0.0, 0.0)),
            _record(mid, vector=(0.6, 0.8, 0.0)),
            _record(low, vector=(0.0, 1.0, 0.0)),
        )
        got = _retriever(memory, vector_index).retrieve(
            project_id="project-1", query="storm", limit=2
        )
        self.assertEqual([e.id for e in got], ["high", "mid"])


class VectorRetrieverQuerySensitivityTest(unittest.TestCase):
    def test_query_drives_ranking(self):
        # Locks that embed(query) feeds the ranking: swapping the query changes
        # which memory ranks first. A retriever that hardcoded a constant query
        # vector (ignoring embed) would return the same top for both queries and
        # fail one direction here. Complements the _FixedEmbeddings tests, which
        # are query-agnostic by design (they pin cosine order, not query flow).
        mem_a = _memory("mem-a")
        mem_b = _memory("mem-b")
        memory = _store(mem_a, mem_b)
        vector_index = _index(
            _record(mem_a, vector=(1.0, 0.0, 0.0)),
            _record(mem_b, vector=(0.0, 1.0, 0.0)),
        )
        retriever = VectorCanonicalMemoryRetriever(
            memory_service=memory,
            embeddings=_QuerySensitiveEmbeddings(),
            vector_index=vector_index,
        )
        toward_a = retriever.retrieve(
            project_id="project-1", query="toward-a", limit=1
        )
        toward_b = retriever.retrieve(
            project_id="project-1", query="toward-b", limit=1
        )
        self.assertEqual([e.id for e in toward_a], ["mem-a"])
        self.assertEqual([e.id for e in toward_b], ["mem-b"])


class VectorRetrieverStaleIsolationTest(unittest.TestCase):
    def test_stale_vectors_are_dropped(self):
        # under-strict guard. Two stale vectors linger in the index:
        #   - "ghost": its memory was deleted → get_memory raises → skipped.
        #   - "old": its memory is superseded → get_memory returns non-canonical
        #     → filtered. Only the canonical "live" survives.
        live = _memory("live", payload={"event": "here"})
        old = _memory("old", status=MemoryStatus.SUPERSEDED)
        ghost = _memory("ghost")  # indexed but NOT put in the store
        memory = _store(live, old)  # ghost intentionally absent
        vector_index = _index(
            _record(ghost, vector=(1.0, 0.0, 0.0)),  # highest sim, but phantom
            _record(old, vector=(0.9, 0.1, 0.0)),    # superseded
            _record(live, vector=(0.5, 0.5, 0.0)),   # only valid survivor
        )
        got = _retriever(memory, vector_index).retrieve(
            project_id="project-1", query="storm", limit=8
        )
        self.assertEqual([e.id for e in got], ["live"])
        self.assertTrue(all(e.status is MemoryStatus.CANONICAL for e in got))


class VectorRetrieverMergeTest(unittest.TestCase):
    def test_merges_all_types_into_one_global_pool(self):
        # over-strict guard for D2. Two character hits outrank the single event
        # hit. A single global pool with limit=2 returns BOTH character hits; a
        # per-type/round-robin merge would instead take one character + the
        # lower-similarity event, so this assertion pins single-pool ranking.
        char_a = _memory("char-a", memory_type=CHARACTER)
        char_b = _memory("char-b", memory_type=CHARACTER)
        event = _memory("event", memory_type=EVENT)
        oq = _memory("oq", memory_type=OPEN_QUESTION)
        memory = _store(char_a, char_b, event, oq)
        vector_index = _index(
            _record(char_a, vector=(1.0, 0.0, 0.0)),   # cos 1.0
            _record(char_b, vector=(0.95, 0.31, 0.0)),  # cos ~0.95
            _record(event, vector=(0.5, 0.87, 0.0)),    # cos 0.5
            _record(oq, vector=(0.0, 1.0, 0.0)),        # cos 0.0
        )
        got = _retriever(memory, vector_index).retrieve(
            project_id="project-1", query="storm", limit=2
        )
        self.assertEqual([e.id for e in got], ["char-a", "char-b"])


class VectorRetrieverSeamInvarianceTest(unittest.TestCase):
    """The vector retriever plugs into the same seam: swapping it for
    Mongo-direct changes nothing in the step/item/Gate path — a canonical_memory
    step still yields micro items with a memory pointer."""

    def _service(self, memory, vector_index):
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        source_block_index = InMemoryVectorIndexAdapter()
        indexing = SourceBlockIndexingService(
            core_sot=core_sot,
            embeddings=DeterministicFakeEmbeddingProvider(),
            vector_index=source_block_index,
        )
        return ContextSearchService(
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
                            need=ContextNeed.CANONICAL_MEMORY,
                            tools=(SearchTool.MONGO,),
                            query="storm",
                        ),
                    ),
                )
            ),
            canonical_memory_retriever=_retriever(memory, vector_index),
        )

    def test_vector_retriever_produces_micro_memory_items(self):
        entry = _memory("m1", payload={"event": "the storm hit"})
        memory = _store(entry)
        vector_index = _index(_record(entry, vector=(1.0, 0.0, 0.0)))
        request = ContextSearchRequest(
            project_id="project-1",
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            needs=(ContextNeed.CANONICAL_MEMORY,),
            query="storm",
            current_position=None,
            context_budget=ContextBudget(max_tokens=10_000),
        )
        package = asyncio.run(
            self._service(memory, vector_index).build_context_package(request)
        )
        self.assertEqual(package.macro_items, ())
        self.assertEqual(len(package.micro_evidence), 1)
        item = package.micro_evidence[0]
        self.assertEqual(item.pointer.collection, MEMORIES_COLLECTION)
        self.assertEqual(item.pointer.document_id, "m1")
        self.assertEqual(item.status, ContextItemStatus.CANONICAL)


class _StaticPlanner:
    def __init__(self, plan):
        self.plan = plan

    def build_plan(self, request):
        return self.plan


if __name__ == "__main__":
    unittest.main()
