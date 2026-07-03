"""Unit tests for Phase 3 index sync MongoDB index setup."""

from datetime import datetime, timezone
import unittest

try:
    from pymongo.errors import DuplicateKeyError, OperationFailure

    from services.application.app.indexing.models import (
        IndexSyncBackend,
        IndexSyncEvent,
        IndexSyncErrorType,
        IndexSyncLastError,
        IndexSyncOutboxEntry,
        IndexSyncSource,
        IndexSyncStatus,
        IndexSyncTargetState,
    )
    from services.application.app.indexing.mongo_repository import (
        MongoIndexSyncRepository,
        MongoIndexSyncRepositorySetupError,
    )

    _PYMONGO_AVAILABLE = True
except ImportError:
    DuplicateKeyError = OperationFailure = Exception
    MongoIndexSyncRepository = None
    MongoIndexSyncRepositorySetupError = RuntimeError
    _PYMONGO_AVAILABLE = False


class _FakeCollection:
    def __init__(self, *, fail_on_name: str | None = None) -> None:
        self.fail_on_name = fail_on_name
        self.calls = []
        self.docs = {}

    def create_index(self, keys, **kwargs):
        self.calls.append((list(keys), dict(kwargs)))
        if kwargs.get("name") == self.fail_on_name:
            raise OperationFailure("conflicting index spec")
        return kwargs.get("name")

    def insert_one(self, doc):
        if doc["_id"] in self.docs:
            raise DuplicateKeyError("duplicate key")
        self.docs[doc["_id"]] = dict(doc)

    def find_one(self, query):
        for doc in self.docs.values():
            if all(_matches(_lookup(doc, key), value) for key, value in query.items()):
                return dict(doc)
        return None


def _repo_with_indexes(*, fail_on_name: str | None = None):
    repo = object.__new__(MongoIndexSyncRepository)
    repo._outbox = _FakeCollection(fail_on_name=fail_on_name)
    repo._logs = _FakeCollection(fail_on_name=fail_on_name)
    return repo


def _lookup(doc, dotted_key):
    value = doc
    for part in dotted_key.split("."):
        value = value[part]
    return value


def _matches(actual, expected):
    if isinstance(expected, dict) and "$in" in expected:
        return actual in expected["$in"]
    return actual == expected


@unittest.skipUnless(_PYMONGO_AVAILABLE, "pymongo is not installed")
class MongoIndexSyncIndexSetupTests(unittest.TestCase):
    def test_ensure_indexes_creates_required_outbox_and_log_indexes(self):
        repo = _repo_with_indexes()

        repo.ensure_indexes()

        self.assertEqual(
            repo._outbox.calls,
            [
                (
                    [
                        ("project_id", 1),
                        ("event", 1),
                        ("source.mongo_collection", 1),
                        ("source.mongo_id", 1),
                    ],
                    {
                        "unique": True,
                        "name": "uniq_index_sync_outbox_event_source",
                    },
                ),
                (
                    [
                        ("status", 1),
                        ("next_attempt_at", 1),
                        ("claimed_at", 1),
                        ("sync_request_id", 1),
                    ],
                    {"name": "index_sync_outbox_by_status_next_attempt"},
                ),
            ],
        )
        self.assertEqual(
            repo._logs.calls,
            [
                (
                    [("sync_request_id", 1), ("attempt_count", 1)],
                    {"name": "index_sync_logs_by_request_attempt"},
                ),
                (
                    [("project_id", 1), ("sync_request_id", 1)],
                    {"name": "index_sync_logs_by_project_request"},
                ),
            ],
        )

    def test_conflicting_index_failure_is_stable_setup_error(self):
        repo = _repo_with_indexes(
            fail_on_name="uniq_index_sync_outbox_event_source"
        )

        with self.assertRaises(MongoIndexSyncRepositorySetupError) as raised:
            repo.ensure_indexes()

        self.assertIsInstance(raised.exception.__cause__, OperationFailure)

    def test_outbox_entry_round_trips_through_mongo_document_shape(self):
        repo = _repo_with_indexes()
        entry = IndexSyncOutboxEntry(
            sync_request_id="sync-request-1",
            project_id="project-1",
            user_id=None,
            event=IndexSyncEvent.PROJECT_ARCHIVED,
            source=IndexSyncSource(
                mongo_collection="projects",
                mongo_id="project-1",
            ),
            targets={
                "chroma": IndexSyncTargetState(
                    status=IndexSyncStatus.PENDING,
                    backend=IndexSyncBackend.IN_MEMORY_FAKE,
                )
            },
            status=IndexSyncStatus.PENDING,
            attempt_count=2,
            max_attempts=3,
            next_attempt_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
            claimed_at=datetime(2026, 7, 3, 0, 1, tzinfo=timezone.utc),
            last_error=IndexSyncLastError(
                error_type=IndexSyncErrorType.NOT_FOUND,
                detail="derived record not found",
            ),
        )

        repo.put_outbox_entry(entry)
        repo._outbox.docs["sync-request-1"]["next_attempt_at"] = datetime(
            2026, 7, 3
        )
        repo._outbox.docs["sync-request-1"]["claimed_at"] = datetime(
            2026, 7, 3, 0, 1
        )
        recovered = repo.get_outbox_entry_by_dedup_key(
            project_id="project-1",
            event=IndexSyncEvent.PROJECT_ARCHIVED,
            source=IndexSyncSource(
                mongo_collection="projects",
                mongo_id="project-1",
            ),
        )

        self.assertEqual(recovered, entry)

    def test_duplicate_outbox_insert_is_idempotent(self):
        repo = _repo_with_indexes()
        entry = IndexSyncOutboxEntry(
            sync_request_id="sync-request-1",
            project_id="project-1",
            user_id=None,
            event=IndexSyncEvent.PROJECT_ARCHIVED,
            source=IndexSyncSource(
                mongo_collection="projects",
                mongo_id="project-1",
            ),
            targets={
                "chroma": IndexSyncTargetState(
                    status=IndexSyncStatus.PENDING,
                    backend=IndexSyncBackend.IN_MEMORY_FAKE,
                )
            },
            status=IndexSyncStatus.PENDING,
            attempt_count=0,
            max_attempts=3,
            next_attempt_at=None,
            claimed_at=None,
            last_error=None,
        )

        repo.put_outbox_entry(entry)
        repo.put_outbox_entry(entry)

        self.assertEqual(len(repo._outbox.docs), 1)


if __name__ == "__main__":
    unittest.main()
