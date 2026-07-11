"""b-2 increment 1 regressions: candidate index pipeline.

record_candidate → CANDIDATE_UPSERTED outbox → worker composite drain → candidate
vector + lexical index. Two-directional discipline: every "should index" branch
is paired with a "should NOT enqueue / must remove" guard so an over-eager
enqueue (idempotent replay) and a missing self-heal (stale vector/doc left
behind) both re-fail.
"""

from datetime import datetime, timezone
import types
import unittest
from dataclasses import replace


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)

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
    IndexSyncErrorType,
    IndexSyncEvent,
    IndexSyncOutboxEntry,
    IndexSyncSource,
    IndexSyncStatus,
)
from services.application.app.indexing.service import (
    CHROMA_VECTOR_BACKEND,
    DeterministicFakeEmbeddingProvider,
    ELASTICSEARCH_BACKEND,
    InMemoryIndexSyncRepository,
    IndexSyncOutboxService,
    IndexSyncWorker,
    LEXICAL_TARGET,
    RecordingArchiveIndexMutationAdapter,
    VECTOR_TARGET,
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

    def test_non_needs_review_status_deletes_vector(self):
        index = InMemoryCandidateVectorIndexAdapter()
        index.upsert_candidate_records(
            (
                build_candidate_index_record(
                    _candidate(), text="x", vector=(1.0, 0.0, 0.0, 0.0)
                ),
            )
        )
        # Phase 6 (v1.6.61) real path: a confirmed/rejected candidate left
        # needs_review, so a CANDIDATE_REMOVED (or upsert) drain de-indexes it.
        transitioned = replace(
            _candidate(), status=AnalysisCandidateStatus.CONFIRMED
        )
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

    def test_non_needs_review_deletes_doc(self):
        index = InMemoryCandidateLexicalIndexAdapter()
        index.index_candidate_records(
            (
                build_candidate_lexical_record(
                    _candidate(payload={"event": "storm"}, candidate_type=EVENT),
                    text="storm",
                ),
            )
        )
        # Phase 6 (v1.6.61) real path: a confirmed candidate is de-indexed.
        transitioned = replace(
            _candidate(payload={"event": "storm"}, candidate_type=EVENT),
            status=AnalysisCandidateStatus.CONFIRMED,
        )
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
class _RecordingSink:
    def __init__(self, *, fail=False):
        self.calls = 0
        self.fail = fail

    def index_candidate(self, entry):
        self.calls += 1
        if self.fail:
            raise RuntimeError("sink down")


def _composite(*sinks):
    return CompositeCandidateIndexSyncAdapter(tuple(sinks))


class CompositeDrainTest(unittest.TestCase):
    def test_drain_fans_out_to_every_sink_and_reports_ok_outcomes(self):
        vector = _RecordingSink()
        lexical = _RecordingSink()
        outcomes = _composite(
            (VECTOR_TARGET, CHROMA_VECTOR_BACKEND, vector),
            (LEXICAL_TARGET, ELASTICSEARCH_BACKEND, lexical),
        ).drain(_entry(), skip=frozenset())

        self.assertEqual((vector.calls, lexical.calls), (1, 1))
        self.assertEqual(
            [(o.target, o.backend, o.ok) for o in outcomes],
            [
                (VECTOR_TARGET, CHROMA_VECTOR_BACKEND, True),
                (LEXICAL_TARGET, ELASTICSEARCH_BACKEND, True),
            ],
        )

    def test_sink_failure_is_isolated_not_swallowed_not_propagated(self):
        # b-6 증분2 re-lock (was all-or-nothing propagate): a raising sink is
        # neither propagated (which would fail the whole event, re-indexing a
        # healthy sink) nor swallowed as success. It becomes a FAILED SinkOutcome
        # so the worker retries only that sink. Two-directional: the healthy
        # co-sink still reports ok=True (isolation up), the failing sink reports
        # ok=False + BACKEND_ERROR (isolation down).
        healthy = _RecordingSink()
        broken = _RecordingSink(fail=True)
        outcomes = _composite(
            (VECTOR_TARGET, CHROMA_VECTOR_BACKEND, healthy),
            (LEXICAL_TARGET, ELASTICSEARCH_BACKEND, broken),
        ).drain(_entry(), skip=frozenset())

        by_target = {o.target: o for o in outcomes}
        self.assertTrue(by_target[VECTOR_TARGET].ok)
        self.assertFalse(by_target[LEXICAL_TARGET].ok)
        self.assertEqual(
            by_target[LEXICAL_TARGET].error.error_type,
            IndexSyncErrorType.BACKEND_ERROR,
        )

    def test_drain_skips_already_succeeded_targets(self):
        # over-strict: a target listed in ``skip`` (it reached SUCCESS on a prior
        # attempt) must NOT be re-run, so a replay never re-indexes a healthy sink.
        vector = _RecordingSink()
        lexical = _RecordingSink(fail=True)
        outcomes = _composite(
            (VECTOR_TARGET, CHROMA_VECTOR_BACKEND, vector),
            (LEXICAL_TARGET, ELASTICSEARCH_BACKEND, lexical),
        ).drain(_entry(), skip=frozenset({VECTOR_TARGET}))

        self.assertEqual(vector.calls, 0)
        self.assertEqual([o.target for o in outcomes], [LEXICAL_TARGET])


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
        return repo, worker

    def test_candidate_upserted_dispatches_to_candidate_adapter(self):
        seen = []

        class _Adapter:
            def index_candidate(self, entry):
                seen.append(entry.source.mongo_id)

        repo, worker = self._worker(
            _composite((VECTOR_TARGET, CHROMA_VECTOR_BACKEND, _Adapter()))
        )
        summary = worker.run_once(limit=10)
        self.assertEqual(seen, ["cand-1"])  # single entry (deduped)
        self.assertEqual(summary.entries_succeeded, 1)
        self.assertEqual(repo.outbox_entries, {})  # all-success deletes the entry

    def test_unconfigured_candidate_adapter_fails_entry(self):
        _repo, worker = self._worker(None)
        summary = worker.run_once(limit=10)
        # missing adapter must fail the entry, not silently succeed.
        self.assertEqual(summary.entries_succeeded, 0)
        self.assertEqual(summary.entries_failed, 1)

    def test_candidate_removed_routes_to_candidate_adapter_and_deletes(self):
        # Phase 6 (v1.6.61): a CANDIDATE_REMOVED event must route through the same
        # per-sink candidate path (_PER_SINK_EVENTS) and reconcile-delete the stale
        # vector of a candidate that left needs_review. Locks the enqueue + routing
        # end-to-end, not just the adapter's delete branch. Removing CANDIDATE_REMOVED
        # from _PER_SINK_EVENTS re-fails this (it would fall to the archive path).
        repo = InMemoryIndexSyncRepository()
        outbox = IndexSyncOutboxService(repo)
        index = InMemoryCandidateVectorIndexAdapter()
        index.upsert_candidate_records(
            (build_candidate_index_record(
                _candidate(), text="x", vector=(1.0, 0.0, 0.0, 0.0)),)
        )
        confirmed = replace(_candidate(), status=AnalysisCandidateStatus.CONFIRMED)
        adapter = CandidateIndexSyncAdapter(
            analysis_service=_StubAnalysis(confirmed),
            embeddings=DeterministicFakeEmbeddingProvider(),
            vector_index=index,
        )
        worker = IndexSyncWorker(
            repository=repo,
            archive_adapter=RecordingArchiveIndexMutationAdapter(),
            candidate_adapter=_composite(
                (VECTOR_TARGET, CHROMA_VECTOR_BACKEND, adapter)
            ),
        )
        outbox.enqueue_candidate_removed(project_id="project-1", candidate_id="cand-1")
        summary = worker.run_once(limit=10)
        self.assertEqual(summary.entries_succeeded, 1)
        self.assertEqual(index.list_candidate_records(project_id="project-1"), ())
        self.assertEqual(repo.outbox_entries, {})


class PerSinkBookkeepingTest(unittest.TestCase):
    """b-6 증분2 (G3=B/G4=B): the core new behavior — one down sink must not poison
    a healthy one, each sink carries its own retry budget, and the entry is deleted
    only when every sink is terminal."""

    def _wire(self, vector, lexical):
        repo = InMemoryIndexSyncRepository()
        outbox = IndexSyncOutboxService(repo)
        outbox.enqueue_candidate_upserted(project_id="project-1", candidate_id="cand-1")
        worker = IndexSyncWorker(
            repository=repo,
            archive_adapter=RecordingArchiveIndexMutationAdapter(),
            candidate_adapter=_composite(
                (VECTOR_TARGET, CHROMA_VECTOR_BACKEND, vector),
                (LEXICAL_TARGET, ELASTICSEARCH_BACKEND, lexical),
            ),
        )
        return repo, worker

    def _entry_now(self, repo):
        return next(iter(repo.outbox_entries.values()))

    def test_failing_sink_requeues_only_itself_until_per_sink_max(self):
        vector = _RecordingSink()
        lexical = _RecordingSink(fail=True)
        repo, worker = self._wire(vector, lexical)

        # Pass 1: vector SUCCESS, lexical FAILED → entry requeued (not deleted),
        # per-sink state materialized.
        s1 = worker.run_once(limit=1, now=_utc(2026, 7, 9, 12, 0, 0))
        self.assertEqual((s1.entries_failed, s1.entries_requeued), (1, 1))
        entry = self._entry_now(repo)
        self.assertEqual(entry.targets[VECTOR_TARGET].status, IndexSyncStatus.SUCCESS)
        self.assertEqual(entry.targets[LEXICAL_TARGET].status, IndexSyncStatus.FAILED)
        self.assertEqual(entry.targets[LEXICAL_TARGET].attempt_count, 1)

        # Pass 2: vector is SUCCESS so it is skipped (over-strict: healthy sink not
        # re-indexed); only lexical retries → attempt 2, still requeued.
        worker.run_once(limit=1, now=_utc(2026, 7, 9, 12, 5, 0))
        entry = self._entry_now(repo)
        self.assertEqual(vector.calls, 1)  # NOT re-indexed
        self.assertEqual(entry.targets[LEXICAL_TARGET].attempt_count, 2)

        # Pass 3: lexical fails a third time → per-sink max (3) reached → every
        # target terminal → entry deleted (all-terminal deletion).
        s3 = worker.run_once(limit=1, now=_utc(2026, 7, 9, 12, 15, 0))
        self.assertEqual(vector.calls, 1)
        self.assertEqual(lexical.calls, 3)
        self.assertEqual((s3.entries_failed, s3.entries_requeued), (1, 0))
        self.assertEqual(repo.outbox_entries, {})

    def test_both_sinks_fail_requeue_together_then_dlq_together(self):
        # Boundary: when EVERY sink fails, none is frozen (skip stays empty), so
        # both retry on their own budget and the entry is deleted only once ALL
        # sinks are terminal (per-sink-max). Distinct from the single-sink-fail
        # path — this pins that "no healthy sink to preserve" still deletes
        # exactly at all-terminal, not early (under-strict) and not never
        # (over-strict against an infinite requeue).
        vector = _RecordingSink(fail=True)
        lexical = _RecordingSink(fail=True)
        repo, worker = self._wire(vector, lexical)

        s1 = worker.run_once(limit=1, now=_utc(2026, 7, 9, 12, 0, 0))
        self.assertEqual((s1.entries_failed, s1.entries_requeued), (1, 1))
        entry = self._entry_now(repo)
        self.assertEqual(entry.targets[VECTOR_TARGET].attempt_count, 1)
        self.assertEqual(entry.targets[LEXICAL_TARGET].attempt_count, 1)

        worker.run_once(limit=1, now=_utc(2026, 7, 9, 12, 5, 0))  # attempt 2, requeue
        s3 = worker.run_once(limit=1, now=_utc(2026, 7, 9, 12, 15, 0))  # attempt 3

        self.assertEqual((vector.calls, lexical.calls), (3, 3))
        self.assertEqual((s3.entries_failed, s3.entries_requeued), (1, 0))
        self.assertEqual(repo.outbox_entries, {})  # both terminal → deleted together

    def test_failed_sink_recovers_on_retry_then_entry_deleted(self):
        # under-strict: if the down sink comes back before its budget runs out, the
        # entry completes (all SUCCESS) and is deleted — the requeue is not a
        # permanent DLQ for a transient failure.
        vector = _RecordingSink()
        lexical = _RecordingSink(fail=True)
        repo, worker = self._wire(vector, lexical)

        worker.run_once(limit=1, now=_utc(2026, 7, 9, 12, 0, 0))
        lexical.fail = False  # sink recovers
        s2 = worker.run_once(limit=1, now=_utc(2026, 7, 9, 12, 5, 0))

        self.assertEqual(s2.entries_succeeded, 1)
        self.assertEqual(vector.calls, 1)  # still not re-indexed
        self.assertEqual(lexical.calls, 2)
        self.assertEqual(repo.outbox_entries, {})


if __name__ == "__main__":
    unittest.main()
