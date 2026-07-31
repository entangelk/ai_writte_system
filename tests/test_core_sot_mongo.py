"""Live MongoDB integration tests for the Core SOT adapter.

These tests require a reachable MongoDB. They skip (not fail) when none is
available so the infrastructure-free unit suite stays runnable everywhere.

- The default deployment is the dedicated test replica set from
  ``docker-compose.test.yml`` (``mongodb://localhost:27020/?replicaSet=rs-test``);
  start it with ``docker compose -f docker-compose.test.yml up -d``.
  ``CORE_SOT_TEST_MONGO_URI`` overrides it.
- The fallback (non-transaction) contract runs against any ``mongod``.
- The transaction contract only runs when the deployment supports
  transactions (a replica set); otherwise it skips. Pointing these tests at a
  standalone mongod is the usual reason ~40 of them silently skip.

Every test uses a throwaway database that is dropped on teardown, so runs are
isolated and leave no residue.
"""

import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

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
    UnitKind,
)
from services.application.app.core_sot.ordered_unit_migration import (
    OrderedUnitMigrationService,
)
from services.application.app.core_sot.repository import DuplicateSaveRequest
from services.application.app.core_sot.service import (
    Archived,
    CoreSotService,
    NotFound,
    StaleProjectBriefBase,
)
from services.application.app.core_sot.splitter import (
    content_hash,
    materialize_blocks,
    split_source_blocks,
)

_MONGO_URI = os.environ.get(
    "CORE_SOT_TEST_MONGO_URI", "mongodb://localhost:27020/?replicaSet=rs-test"
)


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


@unittest.skipUnless(_PYMONGO_AVAILABLE, "pymongo is not installed")
class MongoOwnerFilterQueryTest(unittest.TestCase):
    def test_list_projects_for_owner_filters_at_the_mongo_query_boundary(self):
        filters = []

        class SpyCursor(list):
            def sort(self, *args, **kwargs):
                return self

        class SpyCollection:
            def find(self, filter=None):
                filters.append(filter)
                return SpyCursor()

        repo = MongoCoreSotRepository.__new__(MongoCoreSotRepository)
        repo._projects = SpyCollection()

        repo.list_projects_for_owner("user:1")

        self.assertEqual(filters, [{"owner_id": "user:1"}])


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

    def test_project_brief_versions_persist_in_order_and_replay(self):
        project = self.service.create_project(name="Novel")
        first = self.service.put_project_brief(
            project_id=project.id,
            base_version_id=None,
            idempotency_key="brief-1",
            premise="First",
            genre=None,
            tone=None,
            pov=None,
            constraints=(),
        )
        second = self.service.put_project_brief(
            project_id=project.id,
            base_version_id=first.brief.id,
            idempotency_key="brief-2",
            premise="Second",
            genre="Mystery",
            tone=None,
            pov=None,
            constraints=("Keep the secret",),
            style_rules=("Keep descriptions restrained",),
            preferred_patterns=("Short reveal endings",),
            forbidden_patterns=("As fate would have it",),
            style_examples=("Snow gathered silently.",),
        )
        replay = self.service.put_project_brief(
            project_id=project.id,
            base_version_id=None,
            idempotency_key="brief-2",
            premise="must not replace",
            genre=None,
            tone=None,
            pov=None,
            constraints=(),
        )

        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.brief, second.brief)
        self.assertEqual(
            self.service.list_project_brief_versions(project_id=project.id),
            (first.brief, second.brief),
        )
        self.assertEqual(second.brief.style_examples, ("Snow gathered silently.",))

    def test_legacy_project_brief_document_reads_with_empty_style_arrays(self):
        project = self.service.create_project(name="Legacy brief")
        self.repo._project_briefs.insert_one({
            "_id": "legacy-brief-1",
            "project_id": project.id,
            "version_number": 1,
            "premise": "Before style fields",
            "genre": None,
            "tone": None,
            "pov": None,
            "constraints": [],
            "idempotency_key": "legacy-key",
        })

        brief = self.service.get_project_brief(project_id=project.id)

        self.assertEqual(brief.style_rules, ())
        self.assertEqual(brief.preferred_patterns, ())
        self.assertEqual(brief.forbidden_patterns, ())
        self.assertEqual(brief.style_examples, ())

    def test_project_owner_id_round_trips_through_mongo(self):
        # D8-2a: ownership is recorded, not enforced. This locks the storage wire
        # only — a project created with an owner must read back with it, through
        # get and list alike (the two paths have separate decoders).
        owned = self.service.create_project(name="Owned", owner_id="user:1")

        self.assertEqual(self.service.get_project(project_id=owned.id).owner_id,
                         "user:1")
        listed = {p.id: p for p in self.service.list_projects()}
        self.assertEqual(listed[owned.id].owner_id, "user:1")

    def test_list_projects_for_owner_returns_only_matching_rows(self):
        mine = self.service.create_project(name="Mine", owner_id="user:1")
        self.service.create_project(name="Other", owner_id="user:2")
        self.service.create_project(name="Unowned")

        listed = self.service.list_projects_for_owner(owner_id="user:1")

        self.assertEqual([project.id for project in listed], [mine.id])

    def test_project_without_owner_round_trips_as_none(self):
        # Over-strict guard: the default must stay unowned rather than acquiring
        # a placeholder owner. D8-3 will treat "no owner" as its own case, and a
        # sentinel string here would silently become a real user id.
        unowned = self.service.create_project(name="Unowned")

        self.assertIsNone(unowned.owner_id)
        self.assertIsNone(self.service.get_project(project_id=unowned.id).owner_id)

    def test_legacy_project_document_without_owner_field_reads_as_unowned(self):
        # Documents written before ownership existed have no owner_id key at all.
        # Reading one must yield None, not KeyError — this is the exact shape of
        # every project currently in a deployed database.
        self.repo._projects.insert_one({
            "_id": "legacy-project-1",
            "name": "Before ownership",
            "archived": False,
        })

        project = self.service.get_project(project_id="legacy-project-1")

        self.assertIsNone(project.owner_id)
        self.assertEqual(project.name, "Before ownership")

    def test_concurrent_project_brief_version_collision_has_one_success_one_stale(self):
        """Live Mongo guard for W2 verification H3.

        Both writers observe the same empty base. The unique project/version
        index permits exactly one version 1; the losing different key is a
        stale conflict, never an idempotent replay.
        """

        project = self.service.create_project(name="Concurrent brief")
        original_current = self.repo.get_current_project_brief
        both_read_base = Barrier(2)

        def synchronized_current(project_id):
            current = original_current(project_id)
            both_read_base.wait(timeout=5)
            return current

        self.repo.get_current_project_brief = synchronized_current

        def put(key):
            try:
                return self.service.put_project_brief(
                    project_id=project.id,
                    base_version_id=None,
                    idempotency_key=key,
                    premise=key,
                    genre=None,
                    tone=None,
                    pov=None,
                    constraints=(),
                )
            except StaleProjectBriefBase as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(executor.map(put, ("brief-a", "brief-b")))

        successes = [result for result in results if not isinstance(result, Exception)]
        stale = [result for result in results if isinstance(result, StaleProjectBriefBase)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(stale), 1)
        self.assertFalse(successes[0].idempotent_replay)
        self.assertEqual(
            len(self.service.list_project_brief_versions(project_id=project.id)), 1
        )

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

    def test_ordered_unit_fields_and_full_reorder_persist(self):
        project = self.service.create_project(name="Ordered")
        first = self.service.create_draft(
            project_id=project.id, title="One", unit_kind=UnitKind.CHAPTER
        )
        second = self.service.create_draft(
            project_id=project.id, title="Two", unit_kind=UnitKind.SCENE
        )
        third = self.service.create_draft(project_id=project.id, title="Three")
        self.service.archive_draft(project_id=project.id, draft_id=second.id)

        reordered = self.service.reorder_drafts(
            project_id=project.id,
            ordered_draft_ids=(third.id, second.id, first.id),
        )

        self.assertEqual([draft.id for draft in reordered], [third.id, second.id, first.id])
        self.assertEqual([draft.position for draft in reordered], [1, 2, 3])
        self.assertEqual(
            [draft.unit_kind for draft in reordered],
            [UnitKind.OTHER, UnitKind.SCENE, UnitKind.CHAPTER],
        )
        self.assertTrue(reordered[1].archived)

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

    def test_purge_removes_entire_project_graph(self):
        # D8-6a: project 전체 그래프 영구 파기(mongo, transaction/fallback 양쪽).
        project, draft = self._project_and_draft()
        saved = self.service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="# Chapter 1\n\nOpening.\n\n---\n\nNext scene.",
            idempotency_key="save-1",
        )
        source_ref = self.service.create_source_ref(
            project_id=project.id,
            snapshot_id=saved.snapshot.id,
            start_offset=0,
            end_offset=len("Chapter"),
        )
        # 인접 project(과삭제 감지).
        other, other_draft = self._project_and_draft()
        other_saved = self.service.save_draft(
            project_id=other.id,
            draft_id=other_draft.id,
            raw_text="# Other\n\nText.",
            idempotency_key="save-1",
        )

        self.service.purge_project(project_id=project.id)

        # 대상 그래프 전부 제거(under-strict: 한 컬렉션이라도 남기면 실패).
        self.assertIsNone(self.repo.get_project(project.id))
        self.assertEqual(self.repo.list_drafts(project_id=project.id), ())
        self.assertIsNone(self.repo.get_version(saved.draft_version.id))
        self.assertIsNone(self.repo.get_snapshot(saved.snapshot.id))
        self.assertEqual(self.repo.get_blocks(saved.snapshot.id), ())
        self.assertIsNone(self.repo.get_source_ref(source_ref.id))
        # 인접 project 그래프는 그대로(over-strict: 인접까지 지우면 실패).
        self.assertIsNotNone(self.repo.get_project(other.id))
        self.assertEqual(len(self.repo.list_drafts(project_id=other.id)), 1)
        self.assertIsNotNone(self.repo.get_version(other_saved.draft_version.id))

    def test_purge_unknown_project_raises_not_found(self):
        with self.assertRaises(NotFound):
            self.service.purge_project(project_id="does-not-exist")

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

    def test_ordered_unit_migration_fallback_restores_raw_before_image(self):
        project = self.service.create_project(name="Legacy")
        legacy = [
            {
                "_id": f"legacy-{index}",
                "project_id": project.id,
                "title": f"Legacy {index}",
                "archived": index == 2,
            }
            for index in range(1, 4)
        ]
        self.repo._drafts.insert_many(legacy)
        before = list(self.repo._drafts.find({"project_id": project.id}).sort("_id", 1))
        original_hook = self.repo._after_draft_metadata_write

        def fail_second(index, draft):
            if index == 2:
                raise RuntimeError("injected ordered-unit failure")

        self.repo._after_draft_metadata_write = fail_second
        try:
            report = OrderedUnitMigrationService(self.repo).run()
        finally:
            self.repo._after_draft_metadata_write = original_hook

        after = list(self.repo._drafts.find({"project_id": project.id}).sort("_id", 1))
        self.assertFalse(report.succeeded)
        self.assertEqual(after, before)
        self.assertNotIn("uniq_draft_position", self.repo._drafts.index_information())

    def test_ordered_unit_migration_fallback_commits_and_installs_index(self):
        project = self.service.create_project(name="Legacy")
        self.repo._drafts.insert_many(
            [
                {
                    "_id": f"legacy-{index}",
                    "project_id": project.id,
                    "title": f"Legacy {index}",
                    "archived": False,
                }
                for index in range(1, 4)
            ]
        )

        report = OrderedUnitMigrationService(self.repo).run()

        self.assertTrue(report.succeeded)
        self.assertEqual(
            [draft.position for draft in self.repo.list_drafts(project.id)],
            [1, 2, 3],
        )
        self.assertIn("uniq_draft_position", self.repo._drafts.index_information())

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


@unittest.skipUnless(
    _MONGO_AVAILABLE and _TXN_SUPPORTED,
    "MongoDB deployment does not support transactions (needs a replica set)",
)
class WritingIntentMongoTest(_MongoContractMixin, unittest.TestCase):
    use_transactions = True

    def test_start_next_transaction_rolls_back_entire_write_set(self):  # WI-11
        # An injected mid-write failure must leave zero of the six start-next
        # surfaces: position shift, Draft, version, snapshot, block, receipt.
        project = self.service.create_project(name="Ordered")
        current = self.service.create_draft(
            project_id=project.id, title="현재", unit_kind=UnitKind.CHAPTER)
        self.service.save_draft(project_id=project.id, draft_id=current.id,
            raw_text="현재 본문.", idempotency_key="base")
        following = self.service.create_draft(
            project_id=project.id, title="다음", unit_kind=UnitKind.SCENE)
        before = [(d.id, d.position) for d in self.repo.list_drafts(project.id)]
        # Capture the full write-set counts so every one of the six surfaces is
        # pinned explicitly (H1): draft/position, version, snapshot, block,
        # receipt — none may gain a row from the aborted transaction.
        versions_before = self.repo._versions.count_documents({})
        snapshots_before = self.repo._snapshots.count_documents({})
        blocks_before = self.repo._blocks.count_documents({})
        receipts_before = self.repo._writing_accept_receipts.count_documents({})

        original_hook = self.repo._after_start_next_write

        def fail(new_draft):
            raise RuntimeError("injected start-next transaction failure")

        self.repo._after_start_next_write = fail
        try:
            with self.assertRaises(RuntimeError):
                self.service.start_next_unit(
                    project_id=project.id, current_draft_id=current.id,
                    raw_text="새 유닛 본문.", title="2장",
                    unit_kind=UnitKind.CHAPTER, goal_intent="start_next_unit",
                    idempotency_key="writing-accept:acc1")
        finally:
            self.repo._after_start_next_write = original_hook

        # 1-2. Draft/position surface: positions restored, no new Draft.
        self.assertEqual(
            [(d.id, d.position) for d in self.repo.list_drafts(project.id)],
            before)
        # 3. Version surface: no orphan version (neither on `following` nor anywhere).
        self.assertEqual(self.repo.version_count(following.id), 0)
        self.assertEqual(self.repo._versions.count_documents({}), versions_before)
        # 4. Snapshot surface: the new unit's snapshot never survived.
        self.assertEqual(self.repo._snapshots.count_documents({}), snapshots_before)
        self.assertEqual(
            self.repo._snapshots.count_documents({"raw_text": "새 유닛 본문."}), 0)
        # 5. Block surface: no block from the rolled-back snapshot.
        self.assertEqual(self.repo._blocks.count_documents({}), blocks_before)
        # 6. Receipt surface: no receipt for the aborted accept.
        self.assertEqual(
            self.repo._writing_accept_receipts.count_documents({}), receipts_before)
        self.assertIsNone(self.repo.get_writing_accept_receipt(
            project.id, "writing-accept:acc1"))


if __name__ == "__main__":
    unittest.main()
