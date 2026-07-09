"""b-2 increment 1 regressions: candidate index pipeline.

record_candidate → CANDIDATE_UPSERTED outbox → worker composite drain → candidate
vector + lexical index. Two-directional discipline: every "should index" branch
is paired with a "should NOT enqueue / must remove" guard so an over-eager
enqueue (idempotent replay) and a missing self-heal (stale vector/doc left
behind) both re-fail.
"""

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
    AnalysisCandidateRecordRequest,
    AnalysisNotFound,
    AnalysisService,
    InMemoryAnalysisRepository,
)
from services.application.app.indexing.candidate_index import (
    CandidateIndexSyncAdapter,
    CompositeCandidateIndexSyncAdapter,
    InMemoryCandidateVectorIndexAdapter,
    build_candidate_index_record,
    candidate_index_text,
)
from services.application.app.indexing.candidate_lexical_index import (
    CandidateLexicalIndexSyncAdapter,
    ElasticsearchCandidateIndexAdapter,
    InMemoryCandidateLexicalIndexAdapter,
    build_candidate_lexical_record,
)
from services.application.app.indexing.chroma import (
    ChromaCandidateVectorIndexAdapter,
    candidate_record_from_chroma,
    candidate_record_to_chroma,
)
from services.application.app.indexing.models import (
    CandidateIndexRecord,
    IndexRecordKind,
    IndexSyncEvent,
    IndexSyncOutboxEntry,
    IndexSyncSource,
    IndexSyncStatus,
)
from services.application.app.indexing.service import (
    DeterministicFakeEmbeddingProvider,
    InMemoryIndexSyncRepository,
    IndexSyncOutboxService,
    IndexSyncWorker,
    RecordingArchiveIndexMutationAdapter,
)

CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION
EVENT = AnalysisCandidateType.EVENT_OBSERVATION


def _candidate(
    *,
    candidate_id="cand-1",
    project_id="project-1",
    candidate_type=CHARACTER,
    payload=None,
    status=AnalysisCandidateStatus.NEEDS_REVIEW,
):
    if payload is None:
        payload = {"name": "Ariel", "observation": "brave"}
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
        source_ref_ids=("source-ref-1",),
        payload=payload,
    )


def _entry(*, candidate_id="cand-1", project_id="project-1"):
    return IndexSyncOutboxEntry(
        sync_request_id="req-1",
        project_id=project_id,
        user_id=None,
        event=IndexSyncEvent.CANDIDATE_UPSERTED,
        source=IndexSyncSource(
            mongo_collection="analysis_candidates", mongo_id=candidate_id
        ),
        targets={},
        status=IndexSyncStatus.PENDING,
        attempt_count=0,
        max_attempts=3,
        next_attempt_at=None,
        claimed_at=None,
        last_error=None,
    )


class _StubAnalysis:
    """Minimal analysis-store stub for the drain adapters (get_candidate only)."""

    def __init__(self, candidate=None, *, raise_not_found=False):
        self._candidate = candidate
        self._raise = raise_not_found

    def get_candidate(self, *, project_id, candidate_id):
        if self._raise:
            raise AnalysisNotFound("analysis candidate not found")
        return self._candidate


# --------------------------------------------------------------------------- #
# G2: enqueue choke point
# --------------------------------------------------------------------------- #
class _RecordingOutbox:
    def __init__(self):
        self.calls = []

    def enqueue_candidate_upserted(self, *, project_id, candidate_id):
        self.calls.append((project_id, candidate_id))
        return object()


class EnqueueChokePointTest(unittest.TestCase):
    def _service(self, outbox):
        repo = InMemoryAnalysisRepository()
        service = AnalysisService(repo, reindex_outbox=outbox)
        job = service.create_job(
            project_id="project-1",
            snapshot_id="snap-1",
            idempotency_key="run-1",
        ).job
        task = service.create_task(
            project_id="project-1", job_id=job.id, candidate_type=CHARACTER
        )
        return service, task

    def _record(self, service, task, *, logical_key, payload=None):
        return service.record_candidate(
            project_id="project-1",
            task_id=task.id,
            logical_key=logical_key,
            candidate_type=CHARACTER,
            action=AnalysisCandidateAction.CREATE,
            provenance=AnalysisProvenance.SOURCE_OBSERVED,
            confidence=0.5,
            source_ref_ids=("source-ref-1",),
            payload=payload or {"name": "민아", "observation": "발견"},
        )

    def test_new_candidate_enqueues_candidate_upserted(self):
        outbox = _RecordingOutbox()
        service, task = self._service(outbox)
        result = self._record(service, task, logical_key="character:min-a")
        # under-strict: a new mint must enqueue exactly its id.
        self.assertEqual(outbox.calls, [("project-1", result.candidate.id)])

    def test_idempotent_replay_does_not_enqueue(self):
        outbox = _RecordingOutbox()
        service, task = self._service(outbox)
        first = self._record(service, task, logical_key="character:min-a")
        outbox.calls.clear()
        replay = self._record(
            service,
            task,
            logical_key="character:min-a",
            payload={"name": "민아", "observation": "retry"},
        )
        # over-strict: replaying the same logical candidate must NOT re-enqueue.
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.candidate.id, first.candidate.id)
        self.assertEqual(outbox.calls, [])

    def test_absent_outbox_is_a_no_op(self):
        repo = InMemoryAnalysisRepository()
        service = AnalysisService(repo)  # no reindex_outbox
        job = service.create_job(
            project_id="project-1", snapshot_id="snap-1", idempotency_key="run-1"
        ).job
        task = service.create_task(
            project_id="project-1", job_id=job.id, candidate_type=CHARACTER
        )
        # must not raise without a wired outbox.
        self._record(service, task, logical_key="character:min-a")

    def test_batch_record_enqueues_only_new_candidates(self):
        # under-strict: the production extraction path (runner.py) calls
        # record_candidates with a BATCH. Only genuinely-new candidates enqueue;
        # a within-batch duplicate (same task+logical_key) is a batch_seen replay
        # and must NOT enqueue. Pins the batch iteration — an early-return or
        # wrong-collection mutation that the N=1 singular delegation cannot catch.
        outbox = _RecordingOutbox()
        service, task = self._service(outbox)

        def _req(logical_key, payload):
            return AnalysisCandidateRecordRequest(
                task_id=task.id,
                logical_key=logical_key,
                candidate_type=CHARACTER,
                action=AnalysisCandidateAction.CREATE,
                provenance=AnalysisProvenance.SOURCE_OBSERVED,
                confidence=0.5,
                source_ref_ids=("source-ref-1",),
                payload=payload,
            )

        results = service.record_candidates(
            project_id="project-1",
            requests=(
                _req("character:a", {"name": "A", "observation": "x"}),
                _req("character:b", {"name": "B", "observation": "y"}),
                _req("character:a", {"name": "A", "observation": "dup"}),  # batch dup
            ),
        )
        new_ids = [r.candidate.id for r in results if not r.idempotent_replay]
        self.assertEqual(len(new_ids), 2)  # a, b minted; the dup is a replay
        # Both new candidates enqueue in mint order; the duplicate does NOT.
        self.assertEqual(
            outbox.calls,
            [("project-1", new_ids[0]), ("project-1", new_ids[1])],
        )


# --------------------------------------------------------------------------- #
# Vector drain (CandidateIndexSyncAdapter)
# --------------------------------------------------------------------------- #
class VectorDrainTest(unittest.TestCase):
    def _adapter(self, analysis, index):
        return CandidateIndexSyncAdapter(
            analysis_service=analysis,
            embeddings=DeterministicFakeEmbeddingProvider(),
            vector_index=index,
        )

    def test_needs_review_candidate_is_upserted(self):
        candidate = _candidate()
        index = InMemoryCandidateVectorIndexAdapter()
        self._adapter(_StubAnalysis(candidate), index).index_candidate(_entry())
        records = index.list_candidate_records(project_id="project-1")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].candidate_id, "cand-1")
        self.assertEqual(records[0].kind, IndexRecordKind.CANDIDATE)
        self.assertEqual(records[0].text, candidate_index_text(candidate))

    def test_missing_candidate_deletes_stale_vector(self):
        index = InMemoryCandidateVectorIndexAdapter()
        index.upsert_candidate_records(
            (
                build_candidate_index_record(
                    _candidate(), text="x", vector=(1.0, 0.0, 0.0, 0.0)
                ),
            )
        )
        self._adapter(_StubAnalysis(raise_not_found=True), index).index_candidate(
            _entry()
        )
        # under-strict: a removed candidate's vector must be dropped (self-heal).
        self.assertEqual(index.list_candidate_records(project_id="project-1"), ())

    def test_non_needs_review_status_deletes_vector_forward_defense(self):
        index = InMemoryCandidateVectorIndexAdapter()
        index.upsert_candidate_records(
            (
                build_candidate_index_record(
                    _candidate(), text="x", vector=(1.0, 0.0, 0.0, 0.0)
                ),
            )
        )
        # Phase 6 forward-defense: a candidate whose status left needs_review is
        # de-indexed (unreachable while the enum is single-valued, so use a stub).
        transitioned = types.SimpleNamespace(id="cand-1", project_id="project-1",
                                             status=object())
        self._adapter(_StubAnalysis(transitioned), index).index_candidate(_entry())
        self.assertEqual(index.list_candidate_records(project_id="project-1"), ())


class InMemoryVectorAdapterTest(unittest.TestCase):
    def test_query_similar_ranks_and_scopes_by_type_and_project(self):
        index = InMemoryCandidateVectorIndexAdapter()
        index.upsert_candidate_records(
            (
                CandidateIndexRecord(
                    id="a", kind=IndexRecordKind.CANDIDATE, project_id="project-1",
                    candidate_id="a", candidate_type=CHARACTER.value, status="needs_review",
                    text="near", vector=(1.0, 0.0),
                ),
                CandidateIndexRecord(
                    id="b", kind=IndexRecordKind.CANDIDATE, project_id="project-1",
                    candidate_id="b", candidate_type=CHARACTER.value, status="needs_review",
                    text="far", vector=(0.0, 1.0),
                ),
                CandidateIndexRecord(
                    id="c", kind=IndexRecordKind.CANDIDATE, project_id="project-2",
                    candidate_id="c", candidate_type=CHARACTER.value, status="needs_review",
                    text="other", vector=(1.0, 0.0),
                ),
                CandidateIndexRecord(
                    id="d", kind=IndexRecordKind.CANDIDATE, project_id="project-1",
                    candidate_id="d", candidate_type=EVENT.value, status="needs_review",
                    text="wrongtype", vector=(1.0, 0.0),
                ),
            )
        )
        hits = index.query_similar(
            project_id="project-1", candidate_type=CHARACTER.value,
            vector=(1.0, 0.0), limit=10,
        )
        ids = [h.candidate_id for h in hits]
        self.assertEqual(ids, ["a", "b"])  # project + type scoped, a ranks first


# --------------------------------------------------------------------------- #
# Chroma vector adapter round-trip
# --------------------------------------------------------------------------- #
class _FakeChromaCollection:
    def __init__(self):
        self.docs = {}

    def upsert(self, *, ids, embeddings, metadatas):
        for i, e, m in zip(ids, embeddings, metadatas):
            self.docs[i] = (e, m)

    def get(self, *, where, include):
        pid = where["project_id"]
        ids, embs, metas = [], [], []
        for i, (e, m) in self.docs.items():
            if m["project_id"] == pid:
                ids.append(i)
                embs.append(e)
                metas.append(m)
        return {"ids": ids, "embeddings": embs, "metadatas": metas}

    def query(self, *, query_embeddings, n_results, where, include):
        clauses = where["$and"]
        pid = clauses[0]["project_id"]
        ctype = clauses[1]["candidate_type"]
        ids, embs, metas = [], [], []
        for i, (e, m) in self.docs.items():
            if m["project_id"] == pid and m["candidate_type"] == ctype:
                ids.append(i)
                embs.append(e)
                metas.append(m)
        return {"ids": [ids], "embeddings": [embs], "metadatas": [metas]}

    def delete(self, *, where):
        clauses = where["$and"]
        pid = clauses[0]["project_id"]
        cid = clauses[1]["candidate_id"]
        for i, (_e, m) in list(self.docs.items()):
            if m["project_id"] == pid and m["candidate_id"] == cid:
                del self.docs[i]


class ChromaCandidateAdapterTest(unittest.TestCase):
    def test_record_round_trip(self):
        rec = CandidateIndexRecord(
            id="c1", kind=IndexRecordKind.CANDIDATE, project_id="project-1",
            candidate_id="c1", candidate_type=CHARACTER.value, status="needs_review",
            text="brave", vector=(0.1, 0.2),
        )
        rid, emb, meta = candidate_record_to_chroma(rec)
        back = candidate_record_from_chroma(rid, emb, meta)
        self.assertEqual(back, rec)

    def test_upsert_list_query_delete(self):
        collection = _FakeChromaCollection()
        adapter = ChromaCandidateVectorIndexAdapter(collection)
        rec = CandidateIndexRecord(
            id="c1", kind=IndexRecordKind.CANDIDATE, project_id="project-1",
            candidate_id="c1", candidate_type=CHARACTER.value, status="needs_review",
            text="brave", vector=(1.0, 0.0),
        )
        adapter.upsert_candidate_records((rec,))
        self.assertEqual(adapter.list_candidate_records(project_id="project-1"), (rec,))
        hits = adapter.query_similar(
            project_id="project-1", candidate_type=CHARACTER.value,
            vector=(1.0, 0.0), limit=5,
        )
        self.assertEqual([h.candidate_id for h in hits], ["c1"])
        adapter.delete_candidate_record(project_id="project-1", candidate_id="c1")
        self.assertEqual(adapter.list_candidate_records(project_id="project-1"), ())


# --------------------------------------------------------------------------- #
# Lexical drain + adapters
# --------------------------------------------------------------------------- #
class LexicalDrainTest(unittest.TestCase):
    def _adapter(self, analysis, index):
        return CandidateLexicalIndexSyncAdapter(
            analysis_service=analysis, lexical_index=index
        )

    def test_needs_review_candidate_is_indexed(self):
        candidate = _candidate(payload={"event": "the storm hit the harbor"},
                               candidate_type=EVENT)
        index = InMemoryCandidateLexicalIndexAdapter()
        self._adapter(_StubAnalysis(candidate), index).index_candidate(_entry())
        hits = index.search(project_id="project-1", query="storm", limit=5)
        self.assertEqual([h.candidate_id for h in hits], ["cand-1"])

    def test_missing_candidate_deletes_doc(self):
        index = InMemoryCandidateLexicalIndexAdapter()
        index.index_candidate_records(
            (
                build_candidate_lexical_record(
                    _candidate(payload={"event": "storm"}, candidate_type=EVENT),
                    text="storm",
                ),
            )
        )
        self._adapter(_StubAnalysis(raise_not_found=True), index).index_candidate(
            _entry()
        )
        self.assertEqual(index.search(project_id="project-1", query="storm", limit=5), ())

    def test_non_needs_review_deletes_doc_forward_defense(self):
        index = InMemoryCandidateLexicalIndexAdapter()
        index.index_candidate_records(
            (
                build_candidate_lexical_record(
                    _candidate(payload={"event": "storm"}, candidate_type=EVENT),
                    text="storm",
                ),
            )
        )
        transitioned = types.SimpleNamespace(id="cand-1", project_id="project-1",
                                             status=object())
        self._adapter(_StubAnalysis(transitioned), index).index_candidate(_entry())
        self.assertEqual(index.search(project_id="project-1", query="storm", limit=5), ())


class InMemoryLexicalAdapterTest(unittest.TestCase):
    def test_search_ranks_and_scopes_by_project(self):
        index = InMemoryCandidateLexicalIndexAdapter()
        index.index_candidate_records(
            (
                build_candidate_lexical_record(
                    _candidate(candidate_id="a", payload={"event": "storm harbor"},
                               candidate_type=EVENT),
                    text="storm harbor",
                ),
                build_candidate_lexical_record(
                    _candidate(candidate_id="b", payload={"event": "storm"},
                               candidate_type=EVENT),
                    text="storm",
                ),
                build_candidate_lexical_record(
                    _candidate(candidate_id="c", project_id="project-2",
                               payload={"event": "storm"}, candidate_type=EVENT),
                    text="storm",
                ),
            )
        )
        hits = index.search(project_id="project-1", query="storm harbor", limit=10)
        ids = [h.candidate_id for h in hits]
        self.assertEqual(ids, ["a", "b"])  # project scoped, a scores higher
        self.assertGreater(hits[0].score, hits[1].score)


class ElasticsearchCandidateAdapterTest(unittest.TestCase):
    class _FakeES:
        class _NotFound(Exception):
            pass

        def __init__(self, hits=None):
            self.docs = {}
            self.last_query = None
            self._hits = hits or []

        def index(self, *, index, id, document):
            self.docs[id] = document

        def delete(self, *, index, id):
            if id not in self.docs:
                raise self._NotFound()
            del self.docs[id]

        def search(self, *, index, query, size):
            self.last_query = query
            return {"hits": {"hits": self._hits}}

    def test_index_builds_candidate_pointer_document(self):
        client = self._FakeES()
        adapter = ElasticsearchCandidateIndexAdapter(client, index_name="cand")
        rec = build_candidate_lexical_record(
            _candidate(payload={"event": "storm"}, candidate_type=EVENT), text="storm"
        )
        adapter.index_candidate_records((rec,))
        doc = client.docs["cand-1"]
        self.assertEqual(doc["candidate_id"], "cand-1")
        self.assertEqual(doc["mongo_collection"], "analysis_candidates")
        self.assertEqual(doc["status"], "needs_review")
        self.assertEqual(doc["text"], "storm")

    def test_search_filters_project_and_needs_review(self):
        client = self._FakeES(
            hits=[
                {
                    "_id": "cand-1",
                    "_score": 3.0,
                    "_source": {
                        "candidate_id": "cand-1", "project_id": "project-1",
                        "candidate_type": "event_observation",
                        "status": "needs_review", "text": "storm",
                    },
                }
            ]
        )
        adapter = ElasticsearchCandidateIndexAdapter(client, index_name="cand")
        got = adapter.search(project_id="project-1", query="storm", limit=5)
        self.assertEqual(got[0].candidate_id, "cand-1")
        self.assertEqual(got[0].score, 3.0)
        filters = client.last_query["bool"]["filter"]
        self.assertIn({"term": {"project_id": "project-1"}}, filters)
        # over-strict: candidate leg must pin needs_review (not canonical).
        self.assertIn({"term": {"status": "needs_review"}}, filters)

    def test_delete_is_idempotent(self):
        client = self._FakeES()
        adapter = ElasticsearchCandidateIndexAdapter(client, index_name="cand")
        adapter.delete_candidate_record(project_id="project-1", candidate_id="ghost")


# --------------------------------------------------------------------------- #
# Composite fan-out + worker dispatch
# --------------------------------------------------------------------------- #
class CompositeDrainTest(unittest.TestCase):
    def test_fans_out_to_every_sink(self):
        calls = []

        class _Sink:
            def __init__(self, name):
                self.name = name

            def index_candidate(self, entry):
                calls.append(self.name)

        CompositeCandidateIndexSyncAdapter((_Sink("v"), _Sink("l"))).index_candidate(
            _entry()
        )
        self.assertEqual(calls, ["v", "l"])

    def test_sink_failure_propagates_not_swallowed(self):
        # under-strict: a sink that raises must propagate so the worker marks the
        # entry failed+requeued — it must NOT be silently swallowed (which would
        # leave the entry "succeeded" with one sink stale).
        class _Boom:
            def index_candidate(self, entry):
                raise RuntimeError("sink down")

        with self.assertRaises(RuntimeError):
            CompositeCandidateIndexSyncAdapter((_Boom(),)).index_candidate(_entry())


class WorkerDispatchTest(unittest.TestCase):
    def _worker(self, candidate_adapter):
        repo = InMemoryIndexSyncRepository()
        outbox = IndexSyncOutboxService(repo)
        outbox.enqueue_candidate_upserted(project_id="project-1", candidate_id="cand-1")
        # over-strict: a replay collapses onto the same pending entry (dedup).
        outbox.enqueue_candidate_upserted(project_id="project-1", candidate_id="cand-1")
        worker = IndexSyncWorker(
            repository=repo,
            archive_adapter=RecordingArchiveIndexMutationAdapter(),
            candidate_adapter=candidate_adapter,
        )
        return worker

    def test_candidate_upserted_dispatches_to_candidate_adapter(self):
        seen = []

        class _Adapter:
            def index_candidate(self, entry):
                seen.append(entry.source.mongo_id)

        summary = self._worker(_Adapter()).run_once(limit=10)
        self.assertEqual(seen, ["cand-1"])  # single entry (deduped)
        self.assertEqual(summary.entries_succeeded, 1)

    def test_unconfigured_candidate_adapter_fails_entry(self):
        summary = self._worker(None).run_once(limit=10)
        # missing adapter must fail the entry, not silently succeed.
        self.assertEqual(summary.entries_succeeded, 0)
        self.assertEqual(summary.entries_failed, 1)


if __name__ == "__main__":
    unittest.main()
