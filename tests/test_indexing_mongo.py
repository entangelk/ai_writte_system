"""Live MongoDB smoke tests for Phase 3 index sync outbox persistence."""

import os
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, PyMongoError

    from services.application.app.indexing.mongo_repository import (
        MongoIndexSyncRepository,
    )

    _PYMONGO_AVAILABLE = True
except ImportError:
    MongoClient = None
    ConnectionFailure = PyMongoError = Exception
    MongoIndexSyncRepository = None
    _PYMONGO_AVAILABLE = False

from services.application.app.indexing.models import (
    IndexSyncBackend,
    IndexSyncErrorType,
    IndexSyncEvent,
    IndexSyncSource,
    IndexSyncStatus,
)
from services.application.app.indexing.service import (
    CHROMA_TARGET,
    DRAFTS_COLLECTION,
    INDEX_SYNC_CLAIM_TIMEOUT_SECONDS,
    INDEX_SYNC_MAX_ATTEMPTS,
    PROJECTS_COLLECTION,
    IndexSyncOutboxService,
    IndexSyncWorker,
    RecordingArchiveIndexMutationAdapter,
)

_MONGO_URI = os.environ.get("CORE_SOT_TEST_MONGO_URI")


def _probe_mongo() -> bool:
    if not _PYMONGO_AVAILABLE or _MONGO_URI is None:
        return False
    for _ in range(5):
        client = None
        probe_db = f"index_sync_probe_{uuid.uuid4().hex}"
        try:
            client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=300)
            client.admin.command("ping")
            client[probe_db]["probe"].create_index("key", name="probe_key")
            return True
        except (ConnectionFailure, PyMongoError):
            time.sleep(0.2)
        finally:
            if client is not None:
                try:
                    client.drop_database(probe_db)
                except PyMongoError:
                    pass
                client.close()
    return False


_MONGO_AVAILABLE = _probe_mongo()


@unittest.skipUnless(_MONGO_AVAILABLE, "no MongoDB reachable for integration tests")
class MongoIndexSyncOutboxSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=800)
        self._db_name = f"index_sync_test_{uuid.uuid4().hex}"
        self.repo = MongoIndexSyncRepository(self._client, db_name=self._db_name)
        self.service = IndexSyncOutboxService(self.repo)

    def tearDown(self) -> None:
        self._client.drop_database(self._db_name)
        self._client.close()

    def test_project_archive_outbox_entry_persists_and_round_trips(self):
        entry = self.service.enqueue_project_archived(project_id="project-1")

        reread_repo = MongoIndexSyncRepository(
            self._client,
            db_name=self._db_name,
        )
        recovered = reread_repo.get_outbox_entry_by_dedup_key(
            project_id="project-1",
            event=IndexSyncEvent.PROJECT_ARCHIVED,
            source=IndexSyncSource(
                mongo_collection=PROJECTS_COLLECTION,
                mongo_id="project-1",
            ),
        )

        self.assertEqual(recovered, entry)
        self.assertEqual(entry.status, IndexSyncStatus.PENDING)
        self.assertEqual(entry.attempt_count, 0)
        self.assertEqual(entry.max_attempts, INDEX_SYNC_MAX_ATTEMPTS)
        self.assertIsNone(entry.next_attempt_at)
        self.assertIsNone(entry.last_error)
        self.assertEqual(
            entry.targets[CHROMA_TARGET].backend,
            IndexSyncBackend.IN_MEMORY_FAKE,
        )
        self.assertEqual(entry.targets[CHROMA_TARGET].status, IndexSyncStatus.PENDING)

    def test_repeated_project_archive_replays_same_live_outbox_document(self):
        first = self.service.enqueue_project_archived(project_id="project-1")
        replay = IndexSyncOutboxService(
            MongoIndexSyncRepository(self._client, db_name=self._db_name)
        ).enqueue_project_archived(project_id="project-1")

        self.assertEqual(replay.sync_request_id, first.sync_request_id)
        self.assertEqual(
            self._client[self._db_name]["index_sync_outbox"].count_documents({}),
            1,
        )

    def test_draft_archive_outbox_entry_persists_and_round_trips(self):
        entry = self.service.enqueue_draft_archived(
            project_id="project-1",
            draft_id="draft-1",
        )

        recovered = MongoIndexSyncRepository(
            self._client,
            db_name=self._db_name,
        ).get_outbox_entry_by_dedup_key(
            project_id="project-1",
            event=IndexSyncEvent.DRAFT_ARCHIVED,
            source=IndexSyncSource(
                mongo_collection=DRAFTS_COLLECTION,
                mongo_id="draft-1",
            ),
        )

        self.assertEqual(recovered, entry)
        self.assertEqual(entry.status, IndexSyncStatus.PENDING)
        self.assertEqual(entry.targets[CHROMA_TARGET].status, IndexSyncStatus.PENDING)


class _FailingArchiveAdapter:
    def mark_archived(self, entry):
        raise RuntimeError("backend unavailable")


@unittest.skipUnless(_MONGO_AVAILABLE, "no MongoDB reachable for integration tests")
class MongoIndexSyncWorkerSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=800)
        self._db_name = f"index_sync_test_{uuid.uuid4().hex}"
        self.repo = MongoIndexSyncRepository(self._client, db_name=self._db_name)
        self.service = IndexSyncOutboxService(self.repo)
        self._now = datetime(2026, 7, 3, 12, 0, 0, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self._client.drop_database(self._db_name)
        self._client.close()

    def _outbox_entry(self, project_id):
        return self.repo.get_outbox_entry_by_dedup_key(
            project_id=project_id,
            event=IndexSyncEvent.PROJECT_ARCHIVED,
            source=IndexSyncSource(
                mongo_collection=PROJECTS_COLLECTION,
                mongo_id=project_id,
            ),
        )

    def _logs(self, project_id):
        return sorted(
            self._client[self._db_name]["index_sync_logs"].find({"project_id": project_id}),
            key=lambda doc: doc["attempt_count"],
        )

    def test_worker_success_removes_active_outbox_and_appends_success_log(self):
        self.service.enqueue_project_archived(project_id="project-1")
        worker = IndexSyncWorker(
            repository=self.repo,
            archive_adapter=RecordingArchiveIndexMutationAdapter(),
        )

        summary = worker.run_once(limit=1, now=self._now)

        self.assertEqual(
            (summary.entries_claimed, summary.entries_succeeded, summary.entries_failed),
            (1, 1, 0),
        )
        self.assertIsNone(self._outbox_entry("project-1"))
        logs = self._logs("project-1")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["status"], IndexSyncStatus.SUCCESS.value)
        self.assertEqual(logs[0]["attempt_count"], 1)

    def test_worker_backend_error_backoff_then_terminal_failure(self):
        self.service.enqueue_project_archived(project_id="project-1")
        worker = IndexSyncWorker(
            repository=self.repo,
            archive_adapter=_FailingArchiveAdapter(),
        )

        first = worker.run_once(limit=1, now=self._now)
        after_first = self._outbox_entry("project-1")
        self.assertEqual(first.entries_requeued, 1)
        self.assertEqual(after_first.status, IndexSyncStatus.PENDING)
        self.assertEqual(after_first.attempt_count, 1)
        self.assertEqual(
            after_first.next_attempt_at, self._now + timedelta(seconds=60)
        )
        self.assertEqual(
            after_first.last_error.error_type, IndexSyncErrorType.BACKEND_ERROR
        )

        second = worker.run_once(limit=1, now=self._now + timedelta(seconds=60))
        after_second = self._outbox_entry("project-1")
        self.assertEqual(second.entries_requeued, 1)
        self.assertEqual(after_second.attempt_count, 2)
        self.assertEqual(
            after_second.next_attempt_at, self._now + timedelta(seconds=360)
        )

        third = worker.run_once(limit=1, now=self._now + timedelta(seconds=360))
        self.assertEqual(third.entries_requeued, 0)
        self.assertIsNone(self._outbox_entry("project-1"))
        logs = self._logs("project-1")
        self.assertEqual([log["attempt_count"] for log in logs], [1, 2, 3])
        self.assertTrue(
            all(log["status"] == IndexSyncStatus.FAILED.value for log in logs)
        )

    def test_stale_running_claim_is_reclaimable_without_consuming_attempt(self):
        self.service.enqueue_project_archived(project_id="project-1")
        timeout = INDEX_SYNC_CLAIM_TIMEOUT_SECONDS

        first_claim = self.repo.claim_next_outbox_entry(
            now=self._now, claim_timeout_seconds=timeout
        )
        self.assertEqual(first_claim.status, IndexSyncStatus.RUNNING)

        non_stale = self.repo.claim_next_outbox_entry(
            now=self._now + timedelta(seconds=timeout - 1),
            claim_timeout_seconds=timeout,
        )
        self.assertIsNone(non_stale)

        stale = self.repo.claim_next_outbox_entry(
            now=self._now + timedelta(seconds=timeout + 1),
            claim_timeout_seconds=timeout,
        )
        self.assertIsNotNone(stale)
        self.assertEqual(stale.attempt_count, 0)

    def test_terminal_success_then_reenqueue_creates_new_request(self):
        first = self.service.enqueue_project_archived(project_id="project-1")
        IndexSyncWorker(
            repository=self.repo,
            archive_adapter=RecordingArchiveIndexMutationAdapter(),
        ).run_once(limit=1, now=self._now)

        replay = self.service.enqueue_project_archived(project_id="project-1")

        self.assertNotEqual(replay.sync_request_id, first.sync_request_id)
        self.assertEqual(
            self._client[self._db_name]["index_sync_outbox"].count_documents({}),
            1,
        )


if __name__ == "__main__":
    unittest.main()
