"""Live MongoDB integration tests for the Core SOT adapter.

These tests require a reachable MongoDB. They skip (not fail) when none is
available so the infrastructure-free unit suite stays runnable everywhere.

- Point them at a deployment with ``CORE_SOT_TEST_MONGO_URI`` (default
  ``mongodb://localhost:27017``).
- The fallback (non-transaction) contract runs against any ``mongod``.
- The transaction contract only runs when the deployment supports
  transactions (a replica set); otherwise it skips.

Every test uses a throwaway database that is dropped on teardown, so runs are
isolated and leave no residue.
"""

import os
import unittest
import uuid

# pymongo (and the Mongo adapter that imports it) is an optional dependency for
# the test suite: when it is absent these integration tests skip rather than
# break ``unittest discover`` for the otherwise infrastructure-free unit suite.
try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, OperationFailure, PyMongoError

    from services.application.app.core_sot.mongo_repository import (
        MongoCoreSotRepository,
    )

    _PYMONGO_AVAILABLE = True
except ImportError:
    MongoClient = None
    ConnectionFailure = OperationFailure = PyMongoError = Exception
    MongoCoreSotRepository = None
    _PYMONGO_AVAILABLE = False

from services.application.app.core_sot.models import (
    DraftVersion,
    SourceSnapshot,
)
from services.application.app.core_sot.repository import DuplicateSaveRequest
from services.application.app.core_sot.service import (
    Archived,
    CoreSotService,
    NotFound,
)
from services.application.app.core_sot.splitter import (
    content_hash,
    materialize_blocks,
    split_source_blocks,
)

_MONGO_URI = os.environ.get("CORE_SOT_TEST_MONGO_URI", "mongodb://localhost:27017")


def _probe_mongo() -> tuple[bool, bool]:
    """Return ``(available, transactions_supported)`` for the test deployment."""

    if not _PYMONGO_AVAILABLE:
        return False, False
    try:
        client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=800)
        client.admin.command("ping")
    except (ConnectionFailure, PyMongoError):
        return False, False

    txn_supported = False
    probe_db = f"core_sot_probe_{uuid.uuid4().hex}"
    try:
        with client.start_session() as session:
            with session.start_transaction():
                client[probe_db]["probe"].insert_one({"_id": "x"}, session=session)
        txn_supported = True
    except OperationFailure:
        txn_supported = False
    finally:
        try:
            client.drop_database(probe_db)
        except PyMongoError:
            client.close()
            return False, False
        client.close()
    return True, txn_supported


_MONGO_AVAILABLE, _TXN_SUPPORTED = _probe_mongo()


class _MongoContractMixin:
    """Shared Core SOT contract exercised against a real Mongo backend.

    Concrete subclasses set ``use_transactions`` and the relevant skip guard.
    """

    use_transactions = False

    def setUp(self) -> None:
        self._client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=800)
        self._db_name = f"core_sot_test_{uuid.uuid4().hex}"
        self.repo = MongoCoreSotRepository(
            self._client,
            db_name=self._db_name,
            use_transactions=self.use_transactions,
        )
        self.service = CoreSotService(self.repo)

    def tearDown(self) -> None:
        self._client.drop_database(self._db_name)
        self._client.close()

    def _project_and_draft(self):
        project = self.service.create_project(name="Novel")
        draft = self.service.create_draft(project_id=project.id, title="Episode 1")
        return project, draft

    def test_save_persists_and_reconstructs_snapshot_blocks_and_version(self):
        project, draft = self._project_and_draft()
        raw_text = "# Chapter 1\n\nOpening line.\n\n---\n\nNext scene."

        result = self.service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text=raw_text,
            idempotency_key="save-1",
        )

        # Re-read through a fresh service so we exercise the read path, not the
        # in-flight objects returned by save.
        reread = CoreSotService(self.repo)
        version = reread._repo.get_version(result.draft_version.id)
        snapshot = reread._repo.get_snapshot(result.snapshot.id)
        blocks = reread._repo.get_blocks(result.snapshot.id)

        self.assertIsNotNone(version)
        self.assertEqual(snapshot.raw_text, raw_text)
        self.assertEqual(snapshot.content_hash, content_hash(raw_text))
        self.assertEqual(blocks, result.blocks)
        self.assertEqual(self.repo.version_count(draft.id), 1)

    def test_project_and_draft_list_get_round_trip_with_isolation(self):
        project_a = self.service.create_project(name="A")
        project_b = self.service.create_project(name="B")
        draft_a1 = self.service.create_draft(project_id=project_a.id, title="Episode 1")
        draft_a2 = self.service.create_draft(project_id=project_a.id, title="Episode 2")

        # Re-read through a fresh service to exercise the persisted read path.
        reread = CoreSotService(self.repo)
        self.assertIn(project_a.id, [p.id for p in reread.list_projects()])
        self.assertEqual(reread.get_project(project_id=project_a.id), project_a)
        # Persisted list returns creation order (_id ASCENDING).
        self.assertEqual(
            [d.id for d in reread.list_drafts(project_id=project_a.id)],
            [draft_a1.id, draft_a2.id],
        )
        # should NOT fire: project B has no drafts of project A.
        self.assertEqual(reread.list_drafts(project_id=project_b.id), ())
        self.assertEqual(
            reread.get_draft(project_id=project_a.id, draft_id=draft_a1.id), draft_a1
        )
        with self.assertRaises(NotFound):
            reread.get_draft(project_id=project_b.id, draft_id=draft_a1.id)

    def test_rename_persists_for_project_and_draft(self):
        project = self.service.create_project(name="Old")
        draft = self.service.create_draft(project_id=project.id, title="Old Title")

        self.service.rename_project(project_id=project.id, name="New")
        self.service.rename_draft(
            project_id=project.id, draft_id=draft.id, title="New Title"
        )

        reread = CoreSotService(self.repo)
        self.assertEqual(reread.get_project(project_id=project.id).name, "New")
        self.assertEqual(
            reread.get_draft(project_id=project.id, draft_id=draft.id).title,
            "New Title",
        )

    def test_version_read_back_from_persisted_store(self):
        project, draft = self._project_and_draft()
        raw_text = "# Chapter 1\n\nOpening line.\n\n---\n\nNext scene."
        saved1 = self.service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text=raw_text,
            idempotency_key="save-1",
        )
        saved2 = self.service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="second",
            idempotency_key="save-2",
        )

        # Fresh service so the read path comes entirely from Mongo.
        reread = CoreSotService(self.repo)
        versions = reread.list_draft_versions(project_id=project.id, draft_id=draft.id)
        self.assertEqual(
            [(v.version_number, v.id) for v in versions],
            [(1, saved1.draft_version.id), (2, saved2.draft_version.id)],
        )

        detail = reread.get_draft_version(
            project_id=project.id,
            draft_id=draft.id,
            version_id=saved1.draft_version.id,
        )
        self.assertEqual(detail.snapshot.raw_text, raw_text)
        self.assertEqual(detail.snapshot.content_hash, content_hash(raw_text))
        self.assertEqual(detail.blocks, saved1.blocks)

        with self.assertRaises(NotFound):
            reread.get_draft_version(
                project_id=project.id,
                draft_id=draft.id,
                version_id="does-not-exist",
            )

    def test_idempotent_replay_returns_same_version_without_duplicate(self):
        project, draft = self._project_and_draft()

        first = self.service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="first text",
            idempotency_key="same-key",
        )
        replay = self.service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="mutated retry body must not create a new version",
            idempotency_key="same-key",
        )

        self.assertFalse(first.idempotent_replay)
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.draft_version.id, first.draft_version.id)
        self.assertEqual(replay.snapshot.raw_text, "first text")
        self.assertEqual(self.repo.version_count(draft.id), 1)

    def test_distinct_idempotency_key_creates_next_version(self):
        project, draft = self._project_and_draft()

        first = self.service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="first text",
            idempotency_key="save-1",
        )
        second = self.service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="second text",
            idempotency_key="save-2",
        )

        self.assertNotEqual(second.draft_version.id, first.draft_version.id)
        self.assertEqual(second.draft_version.version_number, 2)
        self.assertEqual(self.repo.version_count(draft.id), 2)

    def test_unique_index_blocks_duplicate_save_request(self):
        # The unique (project_id, draft_id, idempotency_key) boundary must
        # reject a second committed version for the same save request. This
        # exercises record_save directly (the service normally short-circuits
        # via find_save_request before reaching it).
        project, draft = self._project_and_draft()
        self.service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="committed text",
            idempotency_key="dup-key",
        )

        conflicting_version = DraftVersion(
            id=self.repo.next_version_id(),
            project_id=project.id,
            draft_id=draft.id,
            version_number=2,
            snapshot_id="conflict-snapshot",
            idempotency_key="dup-key",
        )
        conflicting_snapshot = SourceSnapshot(
            id="conflict-snapshot",
            project_id=project.id,
            draft_id=draft.id,
            version_id=conflicting_version.id,
            raw_text="conflict",
            content_hash=content_hash("conflict"),
        )

        with self.assertRaises(DuplicateSaveRequest):
            self.repo.record_save(
                idempotency_key="dup-key",
                version=conflicting_version,
                snapshot=conflicting_snapshot,
                blocks=(),
            )
        self.assertEqual(self.repo.version_count(draft.id), 1)

    def test_project_id_isolation_blocks_cross_project_draft_access(self):
        project_a = self.service.create_project(name="A")
        project_b = self.service.create_project(name="B")
        draft_a = self.service.create_draft(project_id=project_a.id, title="Episode 1")

        with self.assertRaises(NotFound):
            self.service.save_draft(
                project_id=project_b.id,
                draft_id=draft_a.id,
                raw_text="leak",
                idempotency_key="save-1",
            )

    def test_archive_preserves_version_snapshot_and_blocks(self):
        project, draft = self._project_and_draft()
        saved = self.service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="archived text",
            idempotency_key="save-1",
        )

        self.service.archive_draft(project_id=project.id, draft_id=draft.id)

        with self.assertRaises(Archived):
            self.service.save_draft(
                project_id=project.id,
                draft_id=draft.id,
                raw_text="new text",
                idempotency_key="save-2",
            )
        self.assertIsNotNone(self.repo.get_version(saved.draft_version.id))
        self.assertIsNotNone(self.repo.get_snapshot(saved.snapshot.id))
        self.assertEqual(self.repo.get_blocks(saved.snapshot.id), saved.blocks)

    def test_source_ref_reconstructs_exact_quote_from_persisted_snapshot(self):
        project, draft = self._project_and_draft()
        raw_text = "첫 문장입니다.\n두번째 문장입니다."
        result = self.service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text=raw_text,
            idempotency_key="save-1",
        )
        start = raw_text.index("두번째")
        end = start + len("두번째")

        source_ref = self.service.create_source_ref(
            project_id=project.id,
            snapshot_id=result.snapshot.id,
            start_offset=start,
            end_offset=end,
        )

        self.assertEqual(source_ref.quote, "두번째")
        self.assertEqual(source_ref.content_hash, result.snapshot.content_hash)
        self.assertEqual(source_ref.block_id, result.blocks[0].id)
        # Persisted and reconstructable through a fresh read path.
        self.assertEqual(self.repo.get_source_ref(source_ref.id), source_ref)

    def test_archive_preserves_persisted_source_ref(self):
        project, draft = self._project_and_draft()
        result = self.service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="Paragraph one.",
            idempotency_key="save-1",
        )
        source_ref = self.service.create_source_ref(
            project_id=project.id,
            snapshot_id=result.snapshot.id,
            start_offset=0,
            end_offset=len("Paragraph"),
        )

        self.service.archive_project(project_id=project.id)

        # SoT §113: source_refs are preserved after archive.
        self.assertEqual(self.repo.get_source_ref(source_ref.id), source_ref)

    def test_source_ref_get_enforces_project_isolation(self):
        project_a = self.service.create_project(name="A")
        project_b = self.service.create_project(name="B")
        draft = self.service.create_draft(project_id=project_a.id, title="Episode 1")
        result = self.service.save_draft(
            project_id=project_a.id,
            draft_id=draft.id,
            raw_text="Paragraph one.",
            idempotency_key="save-1",
        )
        source_ref = self.service.create_source_ref(
            project_id=project_a.id,
            snapshot_id=result.snapshot.id,
            start_offset=0,
            end_offset=len("Paragraph"),
        )

        with self.assertRaises(NotFound):
            self.service.get_source_ref(
                project_id=project_b.id, source_ref_id=source_ref.id
            )

    def test_source_ref_catalog_round_trip_from_persisted_store(self):
        project, draft = self._project_and_draft()
        raw_text = "민아는 파란 편지를 발견했다."
        result = self.service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text=raw_text,
            idempotency_key="save-1",
        )
        letter_start = raw_text.index("편지")
        min_a_start = raw_text.index("민아")
        letter = self.service.create_source_ref(
            project_id=project.id,
            snapshot_id=result.snapshot.id,
            start_offset=letter_start,
            end_offset=letter_start + len("편지"),
        )
        min_a = self.service.create_source_ref(
            project_id=project.id,
            snapshot_id=result.snapshot.id,
            start_offset=min_a_start,
            end_offset=min_a_start + len("민아"),
        )

        reread = CoreSotService(self.repo)

        self.assertEqual(
            reread.list_source_refs(
                project_id=project.id, snapshot_id=result.snapshot.id
            ),
            (min_a, letter),
        )


@unittest.skipUnless(_MONGO_AVAILABLE, "no MongoDB reachable for integration tests")
class FallbackMongoTest(_MongoContractMixin, unittest.TestCase):
    use_transactions = False

    def test_fallback_cleans_orphans_from_prior_failed_attempt(self):
        # Simulate an attempt that wrote immutable dependents but crashed before
        # the draft_versions commit marker. A retry with the same key must clean
        # the orphan and leave exactly one committed dependent set.
        project, draft = self._project_and_draft()
        orphan_snapshot = SourceSnapshot(
            id="orphan-snapshot",
            project_id=project.id,
            draft_id=draft.id,
            version_id="orphan-version",
            raw_text="orphan body",
            content_hash=content_hash("orphan body"),
        )
        orphan_blocks = materialize_blocks(
            project_id=project.id,
            snapshot_id=orphan_snapshot.id,
            raw_blocks=split_source_blocks("orphan body"),
        )
        # Write only the dependents (no version) — the orphan state.
        self.repo._snapshots.insert_one(
            {
                "_id": orphan_snapshot.id,
                "project_id": project.id,
                "draft_id": draft.id,
                "version_id": orphan_snapshot.version_id,
                "raw_text": orphan_snapshot.raw_text,
                "content_hash": orphan_snapshot.content_hash,
                "idempotency_key": "retry-key",
            }
        )
        self.repo._blocks.insert_many(
            [
                {
                    "_id": block.id,
                    "project_id": project.id,
                    "snapshot_id": orphan_snapshot.id,
                    "draft_id": draft.id,
                    "idempotency_key": "retry-key",
                    "block_index": block.block_index,
                    "kind": str(block.kind),
                    "start_offset": block.start_offset,
                    "end_offset": block.end_offset,
                    "text": block.text,
                }
                for block in orphan_blocks
            ]
        )

        result = self.service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="committed body",
            idempotency_key="retry-key",
        )

        self.assertFalse(result.idempotent_replay)
        self.assertEqual(self.repo.version_count(draft.id), 1)
        # The orphan dependents are gone; only the committed snapshot remains.
        self.assertEqual(
            self.repo._snapshots.count_documents({"idempotency_key": "retry-key"}), 1
        )
        self.assertIsNone(self.repo.get_snapshot("orphan-snapshot"))
        self.assertEqual(self.repo._blocks.count_documents({"snapshot_id": "orphan-snapshot"}), 0)
        self.assertEqual(self.repo.get_snapshot(result.snapshot.id).raw_text, "committed body")

    def test_retry_guard_does_not_delete_committed_dependents(self):
        # When a committed version already exists, record_save must signal a
        # replay WITHOUT touching the committed snapshot/blocks.
        project, draft = self._project_and_draft()
        committed = self.service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="committed body",
            idempotency_key="guard-key",
        )

        new_version = DraftVersion(
            id=self.repo.next_version_id(),
            project_id=project.id,
            draft_id=draft.id,
            version_number=2,
            snapshot_id="should-not-write",
            idempotency_key="guard-key",
        )
        new_snapshot = SourceSnapshot(
            id="should-not-write",
            project_id=project.id,
            draft_id=draft.id,
            version_id=new_version.id,
            raw_text="should not persist",
            content_hash=content_hash("should not persist"),
        )

        with self.assertRaises(DuplicateSaveRequest):
            self.repo.record_save(
                idempotency_key="guard-key",
                version=new_version,
                snapshot=new_snapshot,
                blocks=(),
            )
        # Committed dependents intact; the rejected attempt wrote nothing.
        self.assertIsNotNone(self.repo.get_snapshot(committed.snapshot.id))
        self.assertEqual(self.repo.get_blocks(committed.snapshot.id), committed.blocks)
        self.assertIsNone(self.repo.get_snapshot("should-not-write"))


@unittest.skipUnless(
    _MONGO_AVAILABLE and _TXN_SUPPORTED,
    "MongoDB deployment does not support transactions (needs a replica set)",
)
class TransactionMongoTest(_MongoContractMixin, unittest.TestCase):
    use_transactions = True

    def test_transaction_abort_leaves_no_partial_write_on_duplicate(self):
        # A duplicate idempotency key aborts the transaction; none of the
        # second attempt's dependents may survive.
        project, draft = self._project_and_draft()
        self.service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="committed body",
            idempotency_key="txn-key",
        )

        conflicting_version = DraftVersion(
            id=self.repo.next_version_id(),
            project_id=project.id,
            draft_id=draft.id,
            version_number=2,
            snapshot_id="txn-conflict-snapshot",
            idempotency_key="txn-key",
        )
        conflicting_snapshot = SourceSnapshot(
            id="txn-conflict-snapshot",
            project_id=project.id,
            draft_id=draft.id,
            version_id=conflicting_version.id,
            raw_text="rolled back",
            content_hash=content_hash("rolled back"),
        )

        with self.assertRaises(DuplicateSaveRequest):
            self.repo.record_save(
                idempotency_key="txn-key",
                version=conflicting_version,
                snapshot=conflicting_snapshot,
                blocks=(),
            )
        self.assertEqual(self.repo.version_count(draft.id), 1)
        self.assertIsNone(self.repo.get_snapshot("txn-conflict-snapshot"))


if __name__ == "__main__":
    unittest.main()
