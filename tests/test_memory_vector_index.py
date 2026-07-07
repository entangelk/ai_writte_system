"""Phase 2B.5 write-path regressions: apply → outbox → worker → memory vectors.

Two-directional discipline: every "should index" branch is paired with a "should
NOT index / must remove" guard so a canonical-only violation (superseded vector
left behind) and an over-eager enqueue (no_change/conflict) both re-fail.
"""

import unittest

from services.application.app.analysis.apply import (
    ApplyOutcome,
    MemoryApplyService,
)
from services.application.app.analysis.compare import ActionProposal, CompareAction
from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.indexing.memory_index import (
    InMemoryMemoryVectorIndexAdapter,
    MemoryIndexSyncAdapter,
    build_memory_index_record,
    derive_memory_index_text,
)
from services.application.app.indexing.models import (
    IndexRecordKind,
    IndexSyncErrorType,
    IndexSyncEvent,
)
from services.application.app.indexing.service import (
    DeterministicFakeEmbeddingProvider,
    InMemoryIndexSyncRepository,
    IndexSyncOutboxService,
    IndexSyncWorker,
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


def _candidate(
    *,
    candidate_id="cand-1",
    project_id="project-1",
    job_id="job-current",
    candidate_type=CHARACTER,
    confidence=0.5,
    source_ref_ids=("source-ref-1",),
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


def _wire():
    memory = MemoryService(InMemoryMemoryRepository())
    repo = InMemoryIndexSyncRepository()
    outbox = IndexSyncOutboxService(repo)
    apply_service = MemoryApplyService(memory_service=memory, reindex_outbox=outbox)
    vector_index = InMemoryMemoryVectorIndexAdapter()
    worker = IndexSyncWorker(
        repository=repo,
        archive_adapter=object(),  # never reached for memory events
        memory_adapter=MemoryIndexSyncAdapter(
            memory_service=memory,
            embeddings=DeterministicFakeEmbeddingProvider(),
            vector_index=vector_index,
        ),
    )
    return memory, apply_service, repo, worker, vector_index


def _apply(apply_service, proposals, candidates):
    return apply_service.apply_proposals(
        project_id="project-1",
        proposals=tuple(proposals),
        candidates=tuple(candidates),
    )


def _drain(worker):
    return worker.run_once(limit=50)


class ProjectionTest(unittest.TestCase):
    def test_character_projects_name_and_observation(self):
        text = derive_memory_index_text(
            CHARACTER, {"name": "Ariel", "observation": "brave"}
        )
        self.assertEqual(text, "Ariel\nbrave")

    def test_event_projects_event_text(self):
        text = derive_memory_index_text(EVENT, {"event": "the storm hit"})
        self.assertEqual(text, "the storm hit")

    def test_open_question_projects_question_text(self):
        text = derive_memory_index_text(
            OPEN_QUESTION, {"question": "who is the traitor?"}
        )
        self.assertEqual(text, "who is the traitor?")


class EnqueueTest(unittest.TestCase):
    def test_create_enqueues_reindex(self):
        _memory, apply_service, repo, _worker, _vec = _wire()
        candidate = _candidate()
        applied = _apply(
            apply_service, [_proposal(candidate, CompareAction.CREATE)], [candidate]
        )
        self.assertEqual(applied[0].outcome, ApplyOutcome.CREATED)
        entries = list(repo.outbox_entries.values())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].event, IndexSyncEvent.MEMORY_UPSERTED)
        self.assertEqual(entries[0].source.mongo_id, applied[0].memory_id)

    def test_no_change_does_not_enqueue(self):
        # over-strict guard: a no_change proposal must not enqueue a reindex.
        _memory, apply_service, repo, _worker, _vec = _wire()
        candidate = _candidate()
        _apply(
            apply_service,
            [_proposal(candidate, CompareAction.NO_CHANGE)],
            [candidate],
        )
        self.assertEqual(len(repo.outbox_entries), 0)

    def test_conflict_does_not_enqueue(self):
        _memory, apply_service, repo, _worker, _vec = _wire()
        candidate = _candidate()
        _apply(
            apply_service,
            [_proposal(candidate, CompareAction.CONFLICT)],
            [candidate],
        )
        self.assertEqual(len(repo.outbox_entries), 0)

    def test_no_outbox_configured_is_a_noop(self):
        memory = MemoryService(InMemoryMemoryRepository())
        apply_service = MemoryApplyService(memory_service=memory)  # no outbox
        candidate = _candidate()
        applied = _apply(
            apply_service, [_proposal(candidate, CompareAction.CREATE)], [candidate]
        )
        self.assertEqual(applied[0].outcome, ApplyOutcome.CREATED)

    def test_enqueue_dedups_same_memory(self):
        _memory, apply_service, repo, _worker, _vec = _wire()
        candidate = _candidate()
        # Two applies of the same create replay onto one memory id (idempotent
        # promotion), so the outbox keeps a single pending entry.
        _apply(
            apply_service, [_proposal(candidate, CompareAction.CREATE)], [candidate]
        )
        _apply(
            apply_service, [_proposal(candidate, CompareAction.CREATE)], [candidate]
        )
        self.assertEqual(len(repo.outbox_entries), 1)


class WorkerIndexTest(unittest.TestCase):
    def test_create_indexes_canonical_record(self):
        _memory, apply_service, _repo, worker, vector_index = _wire()
        candidate = _candidate()
        applied = _apply(
            apply_service, [_proposal(candidate, CompareAction.CREATE)], [candidate]
        )
        _drain(worker)
        records = vector_index.list_memory_records(project_id="project-1")
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.id, applied[0].memory_id)
        self.assertEqual(record.kind, IndexRecordKind.MEMORY)
        self.assertEqual(record.memory_type, CHARACTER.value)
        self.assertEqual(record.version, 1)
        self.assertEqual(record.text, "Ariel\nbrave")
        self.assertTrue(record.vector)

    def test_update_replaces_prior_version_vector(self):
        # canonical-only: after an update, only the new version's vector remains
        # (prior superseded id removed) — both directions locked.
        memory, apply_service, _repo, worker, vector_index = _wire()
        prior = _candidate()
        _apply(apply_service, [_proposal(prior, CompareAction.CREATE)], [prior])
        _drain(worker)
        prior_memory = vector_index.list_memory_records(project_id="project-1")[0]

        updated = _candidate(
            candidate_id="cand-2", payload={"name": "Ariel", "observation": "bold"}
        )
        applied = _apply(
            apply_service,
            [
                _proposal(
                    updated,
                    CompareAction.UPDATE,
                    matched_memory_id=prior_memory.memory_id,
                )
            ],
            [updated],
        )
        _drain(worker)

        records = vector_index.list_memory_records(project_id="project-1")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].memory_id, applied[0].memory_id)
        self.assertEqual(records[0].version, 2)
        self.assertEqual(records[0].text, "Ariel\nbold")
        self.assertNotIn(
            prior_memory.memory_id, {r.memory_id for r in records}
        )

    def test_superseded_id_is_dropped_not_reindexed(self):
        # Isolated self-heal guard: an entry pointing at an already-superseded
        # version must remove that id's vector and NOT re-index it — even when no
        # successor entry cleans it up. Drive the adapter directly so this does
        # not lean on the supersedes-delete of a sibling entry.
        memory = MemoryService(InMemoryMemoryRepository())
        vector_index = InMemoryMemoryVectorIndexAdapter()
        adapter = MemoryIndexSyncAdapter(
            memory_service=memory,
            embeddings=DeterministicFakeEmbeddingProvider(),
            vector_index=vector_index,
        )
        prior = _candidate()
        prior_memory = memory.promote_candidate(
            project_id="project-1", candidate=prior, mode=PromotionMode.MANUAL
        ).memory
        updated = _candidate(
            candidate_id="cand-2", payload={"name": "Ariel", "observation": "bold"}
        )
        memory.record_updated_version(
            project_id="project-1",
            candidate=updated,
            target_memory_id=prior_memory.id,
        )
        # Seed a stale vector for the now-superseded prior version, then drive its
        # (late) reindex entry.
        repo = InMemoryIndexSyncRepository()
        outbox = IndexSyncOutboxService(repo)
        vector_index.upsert_memory_records(
            (
                build_memory_index_record(
                    prior_memory, text="stale", vector=(0.1,)
                ),
            )
        )
        entry = outbox.enqueue_memory_upserted(
            project_id="project-1", memory_id=prior_memory.id, version=1
        )
        adapter.index_memory(entry)
        records = vector_index.list_memory_records(project_id="project-1")
        self.assertEqual(records, ())

    def test_missing_memory_removes_stale_vector_without_crash(self):
        memory = MemoryService(InMemoryMemoryRepository())
        vector_index = InMemoryMemoryVectorIndexAdapter()
        adapter = MemoryIndexSyncAdapter(
            memory_service=memory,
            embeddings=DeterministicFakeEmbeddingProvider(),
            vector_index=vector_index,
        )
        # Seed a stale vector for the ghost id so this proves the not-found
        # branch actively deletes (not merely that an absent id stays absent).
        vector_index.records["ghost"] = build_memory_index_record(
            MemoryEntry(
                id="ghost",
                project_id="project-1",
                memory_type=CHARACTER,
                status=MemoryStatus.CANONICAL,
                provenance=AnalysisProvenance.SOURCE_OBSERVED,
                confidence=0.5,
                source_ref_ids=("s1",),
                payload={"name": "Ghost", "observation": "x"},
                version=1,
                analysis_job_id="j",
                source_candidate_id="c",
                promotion_mode=PromotionMode.MANUAL,
                applied_threshold=None,
            ),
            text="stale",
            vector=(0.1,),
        )
        repo = InMemoryIndexSyncRepository()
        outbox = IndexSyncOutboxService(repo)
        outbox.enqueue_memory_upserted(
            project_id="project-1", memory_id="ghost", version=1
        )
        worker = IndexSyncWorker(
            repository=repo, archive_adapter=object(), memory_adapter=adapter
        )
        summary = worker.run_once(limit=5)
        self.assertEqual(summary.entries_succeeded, 1)
        self.assertEqual(vector_index.list_memory_records(project_id="project-1"), ())

    def test_memory_upserted_without_adapter_records_backend_error(self):
        # SoT v1.6.45: the worker dispatches MEMORY_UPSERTED to an optional
        # memory_adapter and RAISES when it is unconfigured. Lock that contract
        # branch: the RuntimeError surfaces as a BACKEND_ERROR failure + requeue
        # (not a silent success). Two-directional: a configured adapter succeeds
        # (covered by the WorkerIndexTest cases above), so this pins the "must
        # raise when unconfigured" direction.
        repo = InMemoryIndexSyncRepository()
        outbox = IndexSyncOutboxService(repo)
        outbox.enqueue_memory_upserted(
            project_id="project-1", memory_id="m1", version=1
        )
        worker = IndexSyncWorker(
            repository=repo, archive_adapter=object(), memory_adapter=None
        )
        summary = worker.run_once(limit=5)
        self.assertEqual(summary.entries_succeeded, 0)
        self.assertEqual(summary.entries_failed, 1)
        self.assertEqual(summary.entries_requeued, 1)
        entry = list(repo.outbox_entries.values())[0]
        self.assertEqual(
            entry.last_error.error_type, IndexSyncErrorType.BACKEND_ERROR
        )
        self.assertIn("memory index adapter is not configured", entry.last_error.detail)

    def test_reindex_is_idempotent(self):
        _memory, apply_service, _repo, worker, vector_index = _wire()
        candidate = _candidate()
        _apply(
            apply_service, [_proposal(candidate, CompareAction.CREATE)], [candidate]
        )
        _drain(worker)
        first = vector_index.list_memory_records(project_id="project-1")
        # Re-enqueue the same memory and drain again → still one record.
        _apply(
            apply_service, [_proposal(candidate, CompareAction.CREATE)], [candidate]
        )
        _drain(worker)
        second = vector_index.list_memory_records(project_id="project-1")
        self.assertEqual(len(second), 1)
        self.assertEqual(first[0].id, second[0].id)

    def test_events_accumulate_as_separate_records(self):
        # event/open_question always create (no scope), so two events index as
        # two distinct records — the known duplicate-accumulation caveat.
        _memory, apply_service, _repo, worker, vector_index = _wire()
        first = _candidate(
            candidate_id="ev-1", candidate_type=EVENT, payload={"event": "storm"}
        )
        second = _candidate(
            candidate_id="ev-2", candidate_type=EVENT, payload={"event": "calm"}
        )
        _apply(apply_service, [_proposal(first, CompareAction.CREATE)], [first])
        _apply(apply_service, [_proposal(second, CompareAction.CREATE)], [second])
        _drain(worker)
        records = vector_index.list_memory_records(project_id="project-1")
        self.assertEqual(len(records), 2)
        self.assertEqual(
            {r.text for r in records}, {"storm", "calm"}
        )


if __name__ == "__main__":
    unittest.main()
