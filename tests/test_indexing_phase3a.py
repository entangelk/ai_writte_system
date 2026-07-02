"""Phase 3A source block indexing contract tests."""

from dataclasses import replace
import unittest

from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.indexing.models import (
    IndexRecordKind,
    IndexStaleReason,
    IndexSyncTarget,
)
from services.application.app.indexing.service import (
    DeterministicFakeEmbeddingProvider,
    InMemoryVectorIndexAdapter,
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


if __name__ == "__main__":
    unittest.main()
