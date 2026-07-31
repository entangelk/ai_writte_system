"""Writing canonical inclusion — lexical (ES) leg + hybrid RRF (⑤ §5 B / §8).

Locks:
- the in-memory lexical adapter ranks by keyword overlap, project-scoped;
- the Elasticsearch adapter builds pointer documents and a project+canonical
  filtered query, parses hits, and deletes idempotently (unit-tested with a fake
  client — no elasticsearch package);
- LexicalCanonicalMemoryRetriever re-derives authority from the memory store
  (canonical-only, stale skip) and lets the query drive ranking;
- HybridCanonicalMemoryRetriever fuses vector + lexical by Reciprocal Rank
  Fusion, so a memory ranked well by BOTH signals outranks one ranked #1 by only
  one signal (the property that distinguishes RRF from a single-signal or naive
  concat), with dedup by memory id.
"""

import importlib.util
import unittest

from services.application.app.analysis.models import (
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.context_search.service import (
    HybridCanonicalMemoryRetriever,
    LexicalCanonicalMemoryRetriever,
)
from services.application.app.indexing.memory_index import (
    CompositeMemoryIndexSyncAdapter,
)
from services.application.app.indexing.memory_lexical_index import (
    ElasticsearchMemoryIndexAdapter,
    InMemoryMemoryLexicalIndexAdapter,
    MemoryLexicalIndexSyncAdapter,
    MemoryLexicalRecord,
    build_memory_lexical_record,
    connect_elasticsearch_memory_index,
    memory_lexical_text,
)
from services.application.app.indexing.service import (
    CHROMA_VECTOR_BACKEND,
    ELASTICSEARCH_BACKEND,
    IndexSyncOutboxService,
    InMemoryIndexSyncRepository,
    LEXICAL_TARGET,
    VECTOR_TARGET,
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


def _memory(memory_id, *, text=None, status=MemoryStatus.CANONICAL,
            project_id="project-1", version=1):
    # EVENT payload text is the event string; derive_memory_index_text projects
    # it verbatim, so ``text`` controls the lexical/vector surface.
    return MemoryEntry(
        id=memory_id,
        project_id=project_id,
        memory_type=EVENT,
        status=status,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.5,
        source_ref_ids=("s1",),
        payload={"event": text if text is not None else memory_id},
        version=version,
        analysis_job_id="job-1",
        source_candidate_id=f"c-{memory_id}",
        promotion_mode=PromotionMode.MANUAL,
        applied_threshold=None,
    )


def _store(*entries):
    memory = MemoryService(InMemoryMemoryRepository())
    for entry in entries:
        memory._repo.put_memory(entry)
    return memory


def _lexical_index(*entries):
    adapter = InMemoryMemoryLexicalIndexAdapter()
    adapter.index_memory_records(
        tuple(
            build_memory_lexical_record(e, text=memory_lexical_text(e))
            for e in entries
        )
    )
    return adapter


class InMemoryLexicalAdapterTest(unittest.TestCase):
    def test_ranks_by_token_overlap_and_scopes_project(self):
        m_both = _memory("both", text="storm at the harbor")
        m_one = _memory("one", text="a quiet storm")
        m_none = _memory("none", text="sunshine")
        m_other = _memory("other", text="storm", project_id="project-2")
        index = _lexical_index(m_both, m_one, m_none, m_other)
        hits = index.search(project_id="project-1", query="storm harbor", limit=10)
        ids = [h.memory_id for h in hits]
        # "both" (storm+harbor) outranks "one" (storm); "none" and cross-project
        # "other" are excluded.
        self.assertEqual(ids, ["both", "one"])
        self.assertGreater(hits[0].score, hits[1].score)

    def test_purge_drops_only_target_project(self):
        # D8-6c-1: whole-project delete of the memory lexical leg. Two-directional:
        # the target project is emptied and an adjacent project survives.
        index = _lexical_index(
            _memory("a", text="storm"),
            _memory("b", text="calm"),
            _memory("other", text="storm", project_id="project-2"),
        )
        index.purge_project(project_id="project-1")
        self.assertEqual(index.search(project_id="project-1", query="storm", limit=10), ())
        self.assertEqual(
            [h.memory_id for h in index.search(project_id="project-2", query="storm", limit=10)],
            ["other"],
        )

    def test_purge_is_idempotent_on_empty(self):
        index = _lexical_index(_memory("a", text="storm"))
        # never indexed → purge must not raise and leave project-1 intact.
        index.purge_project(project_id="ghost")
        self.assertEqual(
            [h.memory_id for h in index.search(project_id="project-1", query="storm", limit=10)],
            ["a"],
        )


class ElasticsearchAdapterTest(unittest.TestCase):
    class _FakeES:
        class _NotFound(Exception):
            pass

        def __init__(self, hits=None):
            self.docs = {}
            self.last_query = None
            self.last_size = None
            self._hits = hits or []

        def index(self, *, index, id, document):
            self.docs[id] = document

        def delete(self, *, index, id):
            if id not in self.docs:
                raise self._NotFound()
            del self.docs[id]

        def search(self, *, index, query, size):
            self.last_query = query
            self.last_size = size
            return {"hits": {"hits": self._hits}}

        def delete_by_query(self, *, index, query):
            # D8-6c: ES 8.x signature — a term filter on project_id deletes every
            # matching doc and returns a count (0 for a project with none).
            term = query.get("term", {})
            to_delete = [
                doc_id
                for doc_id, doc in self.docs.items()
                if all(doc.get(k) == v for k, v in term.items())
            ]
            for doc_id in to_delete:
                del self.docs[doc_id]
            return {"deleted": len(to_delete)}

    def test_index_builds_pointer_document(self):
        client = self._FakeES()
        adapter = ElasticsearchMemoryIndexAdapter(client, index_name="mem")
        rec = MemoryLexicalRecord(
            memory_id="m1", project_id="project-1", memory_type="event_observation",
            version=3, status="canonical", text="the storm",
        )
        adapter.index_memory_records((rec,))
        doc = client.docs["m1"]
        self.assertEqual(doc["memory_id"], "m1")
        self.assertEqual(doc["mongo_collection"], "memory_entries")
        self.assertEqual(doc["mongo_version"], 3)
        self.assertEqual(doc["text"], "the storm")

    def test_search_filters_project_and_canonical_and_parses_hits(self):
        client = self._FakeES(
            hits=[
                {
                    "_id": "m1",
                    "_score": 2.5,
                    "_source": {
                        "memory_id": "m1", "project_id": "project-1",
                        "memory_type": "event_observation", "mongo_version": 1,
                        "status": "canonical", "text": "the storm",
                    },
                }
            ]
        )
        adapter = ElasticsearchMemoryIndexAdapter(client, index_name="mem")
        got = adapter.search(project_id="project-1", query="storm", limit=5)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].memory_id, "m1")
        self.assertEqual(got[0].score, 2.5)
        filters = client.last_query["bool"]["filter"]
        self.assertIn({"term": {"project_id": "project-1"}}, filters)
        self.assertIn({"term": {"status": "canonical"}}, filters)
        self.assertEqual(
            client.last_query["bool"]["must"], {"match": {"text": "storm"}}
        )
        self.assertEqual(client.last_size, 5)

    def test_delete_is_idempotent(self):
        client = self._FakeES()
        adapter = ElasticsearchMemoryIndexAdapter(client, index_name="mem")
        # absent doc: must not raise (idempotent drain).
        adapter.delete_memory_record(project_id="project-1", memory_id="ghost")

    def test_purge_deletes_only_target_project(self):
        # D8-6c-1: delete_by_query with a project_id term filter drops the
        # project's documents and leaves an adjacent project intact.
        client = self._FakeES()
        adapter = ElasticsearchMemoryIndexAdapter(client, index_name="mem")
        adapter.index_memory_records(
            (
                MemoryLexicalRecord(
                    memory_id="m1", project_id="project-1",
                    memory_type="event_observation", version=1,
                    status="canonical", text="a",
                ),
                MemoryLexicalRecord(
                    memory_id="m2", project_id="project-1",
                    memory_type="event_observation", version=1,
                    status="canonical", text="b",
                ),
                MemoryLexicalRecord(
                    memory_id="p2", project_id="project-2",
                    memory_type="event_observation", version=1,
                    status="canonical", text="c",
                ),
            )
        )
        adapter.purge_project(project_id="project-1")
        self.assertEqual(set(client.docs), {"p2"})

    def test_purge_is_idempotent_on_empty(self):
        client = self._FakeES()
        adapter = ElasticsearchMemoryIndexAdapter(client, index_name="mem")
        # never indexed → delete_by_query matches 0 docs; must not raise.
        adapter.purge_project(project_id="ghost")
        self.assertEqual(client.docs, {})


class MemoryLexicalSyncAdapterPurgeTest(unittest.TestCase):
    def test_purge_delegates_to_lexical_backend(self):
        # D8-6c-1: the lexical drain adapter's purge delegates to the lexical leg
        # (mirrors the vector leg's MemoryIndexSyncAdapter.purge_project).
        index = _lexical_index(
            _memory("a", text="storm"),
            _memory("other", text="storm", project_id="project-2"),
        )
        adapter = MemoryLexicalIndexSyncAdapter(
            memory_service=_store(
                _memory("a"), _memory("other", project_id="project-2")
            ),
            lexical_index=index,
        )
        adapter.purge_project(project_id="project-1")
        self.assertEqual(index.search(project_id="project-1", query="storm", limit=10), ())
        self.assertEqual(
            [h.memory_id for h in index.search(project_id="project-2", query="storm", limit=10)],
            ["other"],
        )


@unittest.skipUnless(
    importlib.util.find_spec("elasticsearch") is not None,
    "elasticsearch package not installed (this test patches elasticsearch.Elasticsearch)",
)
class ConnectElasticsearchTest(unittest.TestCase):
    """The deploy connect_ path (b-5): the client must carry request_timeout so a
    cold nori index create at app/worker boot does not flake on the stock 10s
    timeout, and the nori index is created only when absent (idempotent)."""

    class _FakeIndices:
        def __init__(self, exists):
            self._exists = exists
            self.created = None

        def exists(self, *, index):
            return self._exists

        def create(self, *, index, settings, mappings):
            self.created = {"index": index, "settings": settings, "mappings": mappings}

    class _FakeES:
        instances = []

        def __init__(self, url, *, request_timeout, exists=False):
            self.url = url
            self.request_timeout = request_timeout
            self.indices = ConnectElasticsearchTest._FakeIndices(exists)
            ConnectElasticsearchTest._FakeES.instances.append(self)

    def _connect(self, *, exists, **kwargs):
        from elasticsearch import Elasticsearch as _real  # noqa: F401
        from unittest import mock

        self._FakeES.instances = []

        def factory(url, *, request_timeout):
            return self._FakeES(url, request_timeout=request_timeout, exists=exists)

        with mock.patch("elasticsearch.Elasticsearch", side_effect=factory):
            connect_elasticsearch_memory_index(
                url="http://es:9200", index_name="mem", **kwargs
            )
        return self._FakeES.instances[0]

    def test_default_request_timeout_is_30_and_creates_nori_index_when_absent(self):
        es = self._connect(exists=False)
        self.assertEqual(es.request_timeout, 30)
        self.assertIsNotNone(es.indices.created)
        settings = es.indices.created["settings"]
        # nori analyzer must be on the created index (Korean morphology).
        self.assertEqual(
            settings["analysis"], {"analyzer": {"korean": {"type": "nori"}}}
        )
        # single-node steady-state green: no replica shard to leave unassigned.
        self.assertEqual(settings["number_of_replicas"], 0)

    def test_request_timeout_is_plumbed_not_hardcoded(self):
        # Over-strict guard: the param must reach the client, not a constant.
        es = self._connect(exists=True, request_timeout=5)
        self.assertEqual(es.request_timeout, 5)

    def test_existing_index_is_not_recreated(self):
        es = self._connect(exists=True)
        self.assertIsNone(es.indices.created)


class LexicalRetrieverTest(unittest.TestCase):
    def test_authority_re_derivation_and_canonical_only(self):
        # The lexical index carries a stale projection; the returned entries are
        # the STORE MemoryEntry objects (payload), never the index records.
        live = _memory("live", text="storm")
        old = _memory("old", text="storm", status=MemoryStatus.SUPERSEDED)
        ghost = _memory("ghost", text="storm")  # indexed but absent from store
        memory = _store(live, old)
        index = _lexical_index(live, old, ghost)
        retriever = LexicalCanonicalMemoryRetriever(
            memory_service=memory, lexical_index=index
        )
        got = retriever.retrieve(project_id="project-1", query="storm", limit=8)
        self.assertEqual([e.id for e in got], ["live"])
        self.assertEqual(got[0].payload, {"event": "storm"})

    def test_query_drives_ranking(self):
        m_a = _memory("mem-a", text="alpha signal")
        m_b = _memory("mem-b", text="beta signal")
        memory = _store(m_a, m_b)
        index = _lexical_index(m_a, m_b)
        retriever = LexicalCanonicalMemoryRetriever(
            memory_service=memory, lexical_index=index
        )
        a = retriever.retrieve(project_id="project-1", query="alpha", limit=1)
        b = retriever.retrieve(project_id="project-1", query="beta", limit=1)
        self.assertEqual([e.id for e in a], ["mem-a"])
        self.assertEqual([e.id for e in b], ["mem-b"])


class _StubRetriever:
    """Returns a preset ranked MemoryEntry list regardless of query — isolates
    the hybrid's RRF fusion from the sub-retrievers' own logic."""

    def __init__(self, ranked):
        self._ranked = ranked

    def retrieve(self, *, project_id, query, limit):
        return tuple(self._ranked[:limit])


class HybridRRFTest(unittest.TestCase):
    def test_rrf_fuses_both_signals(self):
        a = _memory("a")
        b = _memory("b")
        c = _memory("c")
        # vector: [a, b] ; lexical: [b, c]. RRF(k=60): b in both ranks highest;
        # a (vector #1 only) beats c (lexical #2 only). Distinguishes RRF from a
        # single signal or a naive concat.
        vector = _StubRetriever([a, b])
        lexical = _StubRetriever([b, c])
        hybrid = HybridCanonicalMemoryRetriever(
            vector_retriever=vector, lexical_retriever=lexical
        )
        got = hybrid.retrieve(project_id="project-1", query="q", limit=3)
        self.assertEqual([e.id for e in got], ["b", "a", "c"])

    def test_dedup_and_limit(self):
        a = _memory("a")
        b = _memory("b")
        vector = _StubRetriever([a, b])
        lexical = _StubRetriever([a, b])
        hybrid = HybridCanonicalMemoryRetriever(
            vector_retriever=vector, lexical_retriever=lexical
        )
        got = hybrid.retrieve(project_id="project-1", query="q", limit=5)
        self.assertEqual([e.id for e in got], ["a", "b"])  # deduped, not 4

    def test_single_backend_degrades_to_that_backend(self):
        a = _memory("a")
        b = _memory("b")
        vector = _StubRetriever([a, b])
        empty = _StubRetriever([])
        hybrid = HybridCanonicalMemoryRetriever(
            vector_retriever=vector, lexical_retriever=empty
        )
        got = hybrid.retrieve(project_id="project-1", query="q", limit=5)
        self.assertEqual([e.id for e in got], ["a", "b"])


class LexicalDrainTest(unittest.TestCase):
    def _entry(self, memory_id, version=1):
        outbox = IndexSyncOutboxService(InMemoryIndexSyncRepository())
        return outbox.enqueue_memory_upserted(
            project_id="project-1", memory_id=memory_id, version=version
        )

    def test_canonical_memory_is_indexed(self):
        entry_mem = _memory("m1", text="storm")
        memory = _store(entry_mem)
        index = InMemoryMemoryLexicalIndexAdapter()
        adapter = MemoryLexicalIndexSyncAdapter(
            memory_service=memory, lexical_index=index
        )
        adapter.index_memory(self._entry("m1"))
        hits = index.search(project_id="project-1", query="storm", limit=5)
        self.assertEqual([h.memory_id for h in hits], ["m1"])

    def test_superseded_memory_is_deleted(self):
        entry_mem = _memory("m1", text="storm", status=MemoryStatus.SUPERSEDED)
        memory = _store(entry_mem)
        index = _lexical_index(_memory("m1", text="storm"))  # stale doc present
        adapter = MemoryLexicalIndexSyncAdapter(
            memory_service=memory, lexical_index=index
        )
        adapter.index_memory(self._entry("m1"))
        hits = index.search(project_id="project-1", query="storm", limit=5)
        self.assertEqual(hits, ())

    def test_missing_memory_deletes_without_crash(self):
        memory = _store()  # empty store; m1 was deleted
        index = _lexical_index(_memory("m1", text="storm"))  # stale doc present
        adapter = MemoryLexicalIndexSyncAdapter(
            memory_service=memory, lexical_index=index
        )
        adapter.index_memory(self._entry("m1"))  # must not raise
        hits = index.search(project_id="project-1", query="storm", limit=5)
        self.assertEqual(hits, ())


class CompositeDrainTest(unittest.TestCase):
    class _Recorder:
        def __init__(self):
            self.entries = []

        def index_memory(self, entry):
            self.entries.append(entry)

    def test_drain_fans_out_to_every_sink_with_per_sink_outcomes(self):
        vector = self._Recorder()
        lexical = self._Recorder()
        composite = CompositeMemoryIndexSyncAdapter(
            (
                (VECTOR_TARGET, CHROMA_VECTOR_BACKEND, vector),
                (LEXICAL_TARGET, ELASTICSEARCH_BACKEND, lexical),
            )
        )
        outbox = IndexSyncOutboxService(InMemoryIndexSyncRepository())
        entry = outbox.enqueue_memory_upserted(
            project_id="project-1", memory_id="m1", version=1
        )
        outcomes = composite.drain(entry, skip=frozenset())
        self.assertEqual(vector.entries, [entry])
        self.assertEqual(lexical.entries, [entry])
        self.assertEqual(
            [(o.target, o.ok) for o in outcomes],
            [(VECTOR_TARGET, True), (LEXICAL_TARGET, True)],
        )


if __name__ == "__main__":
    unittest.main()
