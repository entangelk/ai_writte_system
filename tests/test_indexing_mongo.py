"""Live MongoDB smoke tests for Phase 3 index sync outbox persistence."""

import os
import time
import unittest
import uuid

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
    IndexSyncEvent,
    IndexSyncSource,
    IndexSyncStatus,
)
from services.application.app.indexing.service import (
    CHROMA_TARGET,
    INDEX_SYNC_MAX_ATTEMPTS,
    PROJECTS_COLLECTION,
    IndexSyncOutboxService,
)

_MONGO_URI = os.environ.get("CORE_SOT_TEST_MONGO_URI", "mongodb://localhost:27017")


def _probe_mongo() -> bool:
    if not _PYMONGO_AVAILABLE:
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


if __name__ == "__main__":
    unittest.main()
