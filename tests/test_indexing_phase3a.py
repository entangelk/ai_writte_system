"""Phase 3A source block indexing contract tests."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest

from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.indexing.models import (
    IndexSyncErrorType,
    IndexSyncEvent,
    IndexSyncLastError,
    IndexSyncSource,
    IndexSyncStatus,
    IndexRecordKind,
    IndexStaleReason,
    IndexSyncTarget,
)
from services.application.app.indexing.service import (
    DeterministicFakeEmbeddingProvider,
    DerivedIndexRecordNotFound,
    DRAFTS_COLLECTION,
    INDEX_SYNC_CLAIM_TIMEOUT_SECONDS,
    INDEX_SYNC_MAX_ATTEMPTS,
    InMemoryIndexSyncRepository,
    InMemoryVectorIndexAdapter,
    IndexSyncWorker,
    IndexSyncOutboxService,
    PROJECTS_COLLECTION,
    RecordingArchiveIndexMutationAdapter,
    SourceBlockIndexingService,
)


class SourceBlockIndexingServiceTest(unittest.TestCase):
    def test_rebuild_indexes_source_blocks_with_sot_pointer_hash_and_version(self):
        core_sot, index, service, saved = _fixture()

        result = service.rebuild_snapshot_source_block_index(
            project_id=saved["project_id"], snapshot_id=saved["snapshot_id"]
        )
        records = index.list_records(project_id=saved["project_id"])

        self.assertEqual(result.request.project_id, saved["project_id"])
        self.assertEqual(result.request.snapshot_id, saved["snapshot_id"])
        self.assertEqual(result.request.target, IndexSyncTarget.VECTOR)
        self.assertEqual(result.records_attempted, 2)
        self.assertEqual(result.records_written, 2)
        self.assertEqual(len(records), 2)
        first = records[0]
        self.assertEqual(first.kind, IndexRecordKind.SOURCE_BLOCK)
        self.assertEqual(first.pointer.project_id, saved["project_id"])
        self.assertEqual(first.pointer.collection, "source_blocks")
        self.assertEqual(first.pointer.document_id, saved["blocks"][0].id)
        self.assertEqual(first.pointer.version_id, saved["version_id"])
        self.assertEqual(first.pointer.content_hash, saved["content_hash"])
        self.assertEqual(first.text, saved["blocks"][0].text)
        self.assertEqual(len(first.vector), 4)
        self.assertFalse(first.project_archived)
        self.assertFalse(first.draft_archived)
        self.assertIs(core_sot.get_project(project_id=saved["project_id"]).archived, False)

    def test_rebuild_is_idempotent_for_same_snapshot(self):
        _core_sot, index, service, saved = _fixture()

        first = service.rebuild_snapshot_source_block_index(
            project_id=saved["project_id"], snapshot_id=saved["snapshot_id"]
        )
        second = service.rebuild_snapshot_source_block_index(
            project_id=saved["project_id"], snapshot_id=saved["snapshot_id"]
        )

        self.assertEqual(first.records_written, 2)
        self.assertEqual(second.records_written, 2)
        self.assertEqual(len(index.list_records(project_id=saved["project_id"])), 2)

    def test_project_isolation_filters_index_records(self):
        core_sot, index, service, saved_a = _fixture(project_name="A")
        project_b = core_sot.create_project(name="B")
        draft_b = core_sot.create_draft(project_id=project_b.id, title="Episode")
        saved_b = core_sot.save_draft(
            project_id=project_b.id,
            draft_id=draft_b.id,
            raw_text="다른 프로젝트 문장.",
            idempotency_key="save-b",
        )

        service.rebuild_snapshot_source_block_index(
            project_id=saved_a["project_id"], snapshot_id=saved_a["snapshot_id"]
        )
        service.rebuild_snapshot_source_block_index(
            project_id=project_b.id, snapshot_id=saved_b.snapshot.id
        )

        self.assertEqual(
            {record.pointer.project_id for record in index.list_records(project_id=saved_a["project_id"])},
            {saved_a["project_id"]},
        )
        self.assertEqual(
            {record.pointer.project_id for record in index.list_records(project_id=project_b.id)},
            {project_b.id},
        )

    def test_archived_project_or_draft_records_are_filtered_from_query_results(self):
        core_sot, index, service, saved = _fixture()

        core_sot.archive_project(project_id=saved["project_id"])
        service.rebuild_snapshot_source_block_index(
            project_id=saved["project_id"], snapshot_id=saved["snapshot_id"]
        )

        self.assertEqual(index.list_records(project_id=saved["project_id"]), ())
        archived_records = index.list_records(
            project_id=saved["project_id"], include_archived=True
        )
        self.assertEqual(len(archived_records), 2)
        self.assertTrue(all(record.project_archived for record in archived_records))
        self.assertTrue(all(not record.draft_archived for record in archived_records))

    def test_archived_draft_records_are_filtered_without_project_archive(self):
        core_sot, index, service, saved = _fixture()

        core_sot.archive_draft(
            project_id=saved["project_id"], draft_id=saved["draft_id"]
        )
        service.rebuild_snapshot_source_block_index(
            project_id=saved["project_id"], snapshot_id=saved["snapshot_id"]
        )

        self.assertEqual(index.list_records(project_id=saved["project_id"]), ())
        archived_records = index.list_records(
            project_id=saved["project_id"], include_archived=True
        )
        self.assertEqual(len(archived_records), 2)
        self.assertTrue(all(record.draft_archived for record in archived_records))
        self.assertTrue(all(not record.project_archived for record in archived_records))

    def test_adapter_failure_does_not_rollback_core_sot_save(self):
        core_sot, _index, _service, saved = _fixture()
        failing = _FailingVectorIndexAdapter()
        service = SourceBlockIndexingService(
            core_sot=core_sot,
            embeddings=DeterministicFakeEmbeddingProvider(),
            vector_index=failing,
        )

        with self.assertRaises(RuntimeError):
            service.rebuild_snapshot_source_block_index(
                project_id=saved["project_id"], snapshot_id=saved["snapshot_id"]
            )

        detail = core_sot.get_snapshot(
            project_id=saved["project_id"], snapshot_id=saved["snapshot_id"]
        )
        self.assertEqual(detail.snapshot.content_hash, saved["content_hash"])
        self.assertEqual(len(detail.blocks), 2)

    def test_validate_source_block_record_accepts_current_live_record(self):
        _core_sot, index, service, saved = _fixture()
        service.rebuild_snapshot_source_block_index(
            project_id=saved["project_id"], snapshot_id=saved["snapshot_id"]
        )
        record = index.list_records(project_id=saved["project_id"])[0]

        validation = service.validate_source_block_record(record)

        self.assertTrue(validation.usable)
        self.assertEqual(validation.record_id, record.id)
        self.assertEqual(validation.stale_reasons, ())

    def test_validate_source_block_record_detects_archive_after_rebuild(self):
        core_sot, index, service, saved = _fixture()
        service.rebuild_snapshot_source_block_index(
            project_id=saved["project_id"], snapshot_id=saved["snapshot_id"]
        )
        record = index.list_records(project_id=saved["project_id"])[0]
        core_sot.archive_project(project_id=saved["project_id"])

        validation = service.validate_source_block_record(record)

        self.assertFalse(validation.usable)
        self.assertEqual(
            validation.stale_reasons,
            (IndexStaleReason.PROJECT_ARCHIVED,),
        )

    def test_validate_source_block_record_detects_draft_archive_after_rebuild(self):
        core_sot, index, service, saved = _fixture()
        service.rebuild_snapshot_source_block_index(
            project_id=saved["project_id"], snapshot_id=saved["snapshot_id"]
        )
        record = index.list_records(project_id=saved["project_id"])[0]
        core_sot.archive_draft(
            project_id=saved["project_id"], draft_id=saved["draft_id"]
        )

        validation = service.validate_source_block_record(record)

        self.assertFalse(validation.usable)
        self.assertEqual(
            validation.stale_reasons,
            (IndexStaleReason.DRAFT_ARCHIVED,),
        )

    def test_validate_source_block_record_detects_pointer_drift(self):
        _core_sot, index, service, saved = _fixture()
        service.rebuild_snapshot_source_block_index(
            project_id=saved["project_id"], snapshot_id=saved["snapshot_id"]
        )
        record = index.list_records(project_id=saved["project_id"])[0]

        validation = service.validate_source_block_record(
            replace(
                record,
                draft_id="other-draft",
                block_id="missing-block",
                pointer=replace(record.pointer, content_hash="wrong-hash"),
            )
        )

        self.assertFalse(validation.usable)
        self.assertEqual(
            validation.stale_reasons,
            (
                IndexStaleReason.DRAFT_MISMATCH,
                IndexStaleReason.CONTENT_HASH_MISMATCH,
                IndexStaleReason.BLOCK_MISSING,
            ),
        )

    def test_validate_source_block_record_detects_missing_snapshot(self):
        _core_sot, index, service, saved = _fixture()
        service.rebuild_snapshot_source_block_index(
            project_id=saved["project_id"], snapshot_id=saved["snapshot_id"]
        )
        record = index.list_records(project_id=saved["project_id"])[0]

        validation = service.validate_source_block_record(
            replace(record, snapshot_id="missing-snapshot")
        )

        self.assertFalse(validation.usable)
        self.assertEqual(
            validation.stale_reasons,
            (IndexStaleReason.SNAPSHOT_MISSING,),
        )


class IndexSyncOutboxServiceTest(unittest.TestCase):
    def test_analysis_completed_event_is_not_open_until_candidate_indexing_contract(self):
        self.assertNotIn(
            "analysis_completed",
            {event.value for event in IndexSyncEvent},
        )

    def test_project_archive_creates_sink_agnostic_pending_outbox_entry(self):
        repo = InMemoryIndexSyncRepository()
        service = IndexSyncOutboxService(repo)

        entry = service.enqueue_project_archived(project_id="project-1")

        self.assertEqual(entry.sync_request_id, "index-sync-request-1")
        self.assertEqual(entry.project_id, "project-1")
        self.assertIsNone(entry.user_id)
        self.assertEqual(entry.event, IndexSyncEvent.PROJECT_ARCHIVED)
        self.assertEqual(entry.source.mongo_collection, PROJECTS_COLLECTION)
        self.assertEqual(entry.source.mongo_id, "project-1")
        self.assertEqual(entry.status, IndexSyncStatus.PENDING)
        self.assertEqual(entry.attempt_count, 0)
        self.assertEqual(entry.max_attempts, INDEX_SYNC_MAX_ATTEMPTS)
        self.assertEqual(INDEX_SYNC_MAX_ATTEMPTS, 3)
        self.assertIsNone(entry.next_attempt_at)
        self.assertIsNone(entry.last_error)
        # b-6 증분2: enqueue is sink-agnostic — the worker materializes per-sink
        # targets on claim, so the entry starts with no targets.
        self.assertEqual(entry.targets, {})

    def test_draft_archive_creates_distinct_dedup_source(self):
        service = IndexSyncOutboxService(InMemoryIndexSyncRepository())

        entry = service.enqueue_draft_archived(
            project_id="project-1",
            draft_id="draft-1",
        )

        self.assertEqual(entry.event, IndexSyncEvent.DRAFT_ARCHIVED)
        self.assertEqual(entry.source.mongo_collection, DRAFTS_COLLECTION)
        self.assertEqual(entry.source.mongo_id, "draft-1")

    def test_repeated_archive_replays_same_outbox_entry(self):
        repo = InMemoryIndexSyncRepository()
        service = IndexSyncOutboxService(repo)

        first = service.enqueue_project_archived(project_id="project-1")
        second = service.enqueue_project_archived(project_id="project-1")

        self.assertEqual(first, second)
        self.assertEqual(len(repo.outbox_entries), 1)

    def test_error_types_are_distinct_and_share_three_attempt_limit(self):
        backend_error = IndexSyncLastError(
            error_type=IndexSyncErrorType.BACKEND_ERROR,
            detail="server unavailable",
        )
        not_found = IndexSyncLastError(
            error_type=IndexSyncErrorType.NOT_FOUND,
            detail="derived record not found",
        )

        self.assertNotEqual(backend_error.error_type, not_found.error_type)
        self.assertEqual(INDEX_SYNC_MAX_ATTEMPTS, 3)


class IndexSyncWorkerTest(unittest.TestCase):
    def test_worker_success_records_log_and_moves_terminal_out_of_outbox(self):
        repo = InMemoryIndexSyncRepository()
        outbox = IndexSyncOutboxService(repo)
        entry = outbox.enqueue_project_archived(project_id="project-1")
        adapter = RecordingArchiveIndexMutationAdapter()
        worker = IndexSyncWorker(repository=repo, archive_adapter=adapter)
        now = _utc(2026, 7, 3, 12, 0, 0)

        summary = worker.run_once(limit=1, now=now)

        self.assertEqual(summary.entries_claimed, 1)
        self.assertEqual(summary.entries_succeeded, 1)
        self.assertEqual(summary.entries_failed, 0)
        self.assertEqual(adapter.marked_archived, [replace(entry, status=IndexSyncStatus.RUNNING, claimed_at=now)])
        self.assertEqual(repo.outbox_entries, {})
        self.assertEqual(len(repo.logs), 1)
        self.assertEqual(repo.logs[0].status, IndexSyncStatus.SUCCESS)
        self.assertEqual(repo.logs[0].attempt_count, 1)

        reenqueued = outbox.enqueue_project_archived(project_id="project-1")

        self.assertEqual(reenqueued.sync_request_id, "index-sync-request-2")

    def test_active_pending_or_running_entry_is_deduped(self):
        repo = InMemoryIndexSyncRepository()
        outbox = IndexSyncOutboxService(repo)
        first = outbox.enqueue_project_archived(project_id="project-1")
        pending_replay = outbox.enqueue_project_archived(project_id="project-1")
        now = _utc(2026, 7, 3, 12, 0, 0)

        running = repo.claim_next_outbox_entry(
            now=now,
            claim_timeout_seconds=INDEX_SYNC_CLAIM_TIMEOUT_SECONDS,
        )
        running_replay = outbox.enqueue_project_archived(project_id="project-1")

        self.assertEqual(pending_replay, first)
        self.assertEqual(running_replay, running)
        self.assertEqual(len(repo.outbox_entries), 1)

    def test_stale_running_reclaim_does_not_consume_attempt(self):
        repo = InMemoryIndexSyncRepository()
        IndexSyncOutboxService(repo).enqueue_project_archived(project_id="project-1")
        now = _utc(2026, 7, 3, 12, 0, 0)
        first_claim = repo.claim_next_outbox_entry(
            now=now,
            claim_timeout_seconds=INDEX_SYNC_CLAIM_TIMEOUT_SECONDS,
        )

        non_stale = repo.claim_next_outbox_entry(
            now=now + timedelta(seconds=INDEX_SYNC_CLAIM_TIMEOUT_SECONDS - 1),
            claim_timeout_seconds=INDEX_SYNC_CLAIM_TIMEOUT_SECONDS,
        )
        stale = repo.claim_next_outbox_entry(
            now=now + timedelta(seconds=INDEX_SYNC_CLAIM_TIMEOUT_SECONDS),
            claim_timeout_seconds=INDEX_SYNC_CLAIM_TIMEOUT_SECONDS,
        )

        self.assertIsNone(non_stale)
        self.assertEqual(first_claim.attempt_count, 0)
        self.assertEqual(stale.attempt_count, 0)
        self.assertEqual(
            stale.claimed_at,
            now + timedelta(seconds=INDEX_SYNC_CLAIM_TIMEOUT_SECONDS),
        )

    def test_backend_error_uses_one_minute_then_five_minute_backoff_then_failed(self):
        repo = InMemoryIndexSyncRepository()
        IndexSyncOutboxService(repo).enqueue_project_archived(project_id="project-1")
        worker = IndexSyncWorker(
            repository=repo,
            archive_adapter=_FailingArchiveAdapter(),
        )
        first = _utc(2026, 7, 3, 12, 0, 0)

        first_summary = worker.run_once(limit=1, now=first)
        after_first = next(iter(repo.outbox_entries.values()))
        second = first + timedelta(seconds=60)
        second_summary = worker.run_once(limit=1, now=second)
        after_second = next(iter(repo.outbox_entries.values()))
        third = second + timedelta(seconds=300)
        third_summary = worker.run_once(limit=1, now=third)

        self.assertEqual(first_summary.entries_requeued, 1)
        self.assertEqual(after_first.status, IndexSyncStatus.PENDING)
        self.assertEqual(after_first.attempt_count, 1)
        self.assertEqual(after_first.next_attempt_at, second)
        self.assertEqual(after_first.last_error.error_type, IndexSyncErrorType.BACKEND_ERROR)
        self.assertEqual(second_summary.entries_requeued, 1)
        self.assertEqual(after_second.attempt_count, 2)
        self.assertEqual(after_second.next_attempt_at, third)
        self.assertEqual(third_summary.entries_requeued, 0)
        self.assertEqual(repo.outbox_entries, {})
        self.assertEqual([log.attempt_count for log in repo.logs], [1, 2, 3])
        self.assertTrue(all(log.status == IndexSyncStatus.FAILED for log in repo.logs))

    def test_archive_worker_time_not_found_is_idempotent_success(self):
        repo = InMemoryIndexSyncRepository()
        IndexSyncOutboxService(repo).enqueue_draft_archived(
            project_id="project-1",
            draft_id="draft-1",
        )
        worker = IndexSyncWorker(
            repository=repo,
            archive_adapter=_NotFoundArchiveAdapter(),
        )

        summary = worker.run_once(limit=1, now=_utc(2026, 7, 3, 12, 0, 0))

        self.assertEqual(summary.entries_succeeded, 1)
        self.assertEqual(summary.entries_failed, 0)
        self.assertEqual(repo.outbox_entries, {})
        self.assertEqual(repo.logs[0].status, IndexSyncStatus.SUCCESS)
        self.assertIsNone(repo.logs[0].error)

    def test_run_once_stop_check_finishes_in_flight_entry_then_stops(self):
        # b-6 (G2): stop_check lets a drain loop request exit at the next entry
        # boundary. Under-strict: ignoring stop_check would drain all entries.
        repo = InMemoryIndexSyncRepository()
        outbox = IndexSyncOutboxService(repo)
        for i in range(3):
            outbox.enqueue_project_archived(project_id=f"p{i}")
        worker = IndexSyncWorker(
            repository=repo, archive_adapter=RecordingArchiveIndexMutationAdapter()
        )
        full = worker.run_once(limit=10, now=_utc(2026, 7, 3, 12, 0, 0))
        self.assertEqual(full.entries_claimed, 3)

        # stop_check requested after the first claim boundary: the in-flight
        # entry finishes, then run_once stops before claiming the next.
        repo2 = InMemoryIndexSyncRepository()
        outbox2 = IndexSyncOutboxService(repo2)
        for i in range(3):
            outbox2.enqueue_project_archived(project_id=f"p{i}")
        worker2 = IndexSyncWorker(
            repository=repo2, archive_adapter=RecordingArchiveIndexMutationAdapter()
        )
        checks = {"n": 0}

        def stop_after_first() -> bool:
            checks["n"] += 1
            return checks["n"] > 1

        partial = worker2.run_once(
            limit=10, now=_utc(2026, 7, 3, 12, 0, 0), stop_check=stop_after_first
        )
        self.assertEqual(partial.entries_claimed, 1)
        self.assertEqual(partial.entries_succeeded, 1)
        self.assertEqual(len(repo2.outbox_entries), 2)

        # Over-strict: a stop_check that never requests stop drains everything
        # (no over-trigger).
        repo3 = InMemoryIndexSyncRepository()
        outbox3 = IndexSyncOutboxService(repo3)
        for i in range(3):
            outbox3.enqueue_project_archived(project_id=f"p{i}")
        worker3 = IndexSyncWorker(
            repository=repo3, archive_adapter=RecordingArchiveIndexMutationAdapter()
        )
        never_stop = worker3.run_once(
            limit=10, now=_utc(2026, 7, 3, 12, 0, 0), stop_check=lambda: False
        )
        self.assertEqual(never_stop.entries_claimed, 3)


def _fixture(*, project_name="Novel"):
    core_sot = CoreSotService(InMemoryCoreSotRepository())
    project = core_sot.create_project(name=project_name)
    draft = core_sot.create_draft(project_id=project.id, title="Episode 1")
    saved = core_sot.save_draft(
        project_id=project.id,
        draft_id=draft.id,
        raw_text="첫 문장입니다.\n\n두번째 문장입니다.",
        idempotency_key=f"save-{project_name}",
    )
    index = InMemoryVectorIndexAdapter()
    service = SourceBlockIndexingService(
        core_sot=core_sot,
        embeddings=DeterministicFakeEmbeddingProvider(),
        vector_index=index,
    )
    return (
        core_sot,
        index,
        service,
        {
            "project_id": project.id,
            "draft_id": draft.id,
            "version_id": saved.draft_version.id,
            "snapshot_id": saved.snapshot.id,
            "content_hash": saved.snapshot.content_hash,
            "blocks": saved.blocks,
        },
    )


class _FailingVectorIndexAdapter:
    def upsert_records(self, records):
        raise RuntimeError("vector index unavailable")


class _FailingArchiveAdapter:
    def mark_archived(self, entry):
        raise RuntimeError("backend unavailable")


class _NotFoundArchiveAdapter:
    def mark_archived(self, entry):
        raise DerivedIndexRecordNotFound("already absent")


def _utc(year, month, day, hour, minute, second):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


if __name__ == "__main__":
    unittest.main()
