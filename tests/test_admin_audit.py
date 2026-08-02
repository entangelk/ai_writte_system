"""D8-6 administrator purge tombstones — domain and Mongo wire guards."""

import unittest
from datetime import UTC, datetime, timedelta

from services.application.app.auth.admin_audit import (
    AdminAuditService,
    InMemoryAdminAuditRepository,
)
from services.application.app.auth.admin_audit_mongo import MongoAdminAuditRepository

_T0 = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)


class AdminAuditServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = InMemoryAdminAuditRepository()
        ids = iter(("event:requested", "operation:1", "event:outcome"))
        self.service = AdminAuditService(
            self.repo, clock=lambda: _T0, id_factory=lambda: next(ids)
        )

    def test_blank_reason_is_refused_before_any_tombstone(self) -> None:
        for reason in ("", "  ", "\n\t"):
            with self.subTest(reason=repr(reason)):
                with self.assertRaises(ValueError):
                    self.service.record_purge_requested(
                        admin_user_id="admin:1",
                        target_project_id="p1",
                        reason=reason,
                    )
        self.assertEqual(self.repo.events, [])

    def test_requested_and_outcome_share_one_operation(self) -> None:
        requested = self.service.record_purge_requested(
            admin_user_id="admin:1", target_project_id="p1", reason="  고객 요청  "
        )
        succeeded = self.service.record_purge_outcome(
            requested, outcome="succeeded"
        )

        self.assertEqual(requested.operation_id, succeeded.operation_id)
        self.assertEqual(requested.reason, "고객 요청")
        self.assertEqual(succeeded.reason, "고객 요청")
        self.assertEqual(
            [event.outcome for event in self.service.list_project_purge_events()],
            ["requested", "succeeded"],
        )


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, field, direction):
        self.docs.sort(key=lambda doc: doc[field], reverse=direction < 0)
        return self

    def limit(self, limit):
        self.docs = self.docs[:limit]
        return self

    def __iter__(self):
        return iter(self.docs)


class _Collection:
    def __init__(self) -> None:
        self.docs: list[dict] = []
        self.indexes: list[tuple] = []

    def create_index(self, keys, *, name=None, **kwargs):
        self.indexes.append((keys, name, kwargs))

    def insert_one(self, doc):
        stored = dict(doc)
        stored["at"] = stored["at"].replace(tzinfo=None)
        self.docs.append(stored)

    def find(self, query):
        return _Cursor([
            dict(doc) for doc in self.docs
            if all(doc.get(key) == value for key, value in query.items())
        ])


class _Database:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == "admin_audit_events"
        return self.collection


class _Client:
    def __init__(self, collection):
        self.database = _Database(collection)

    def __getitem__(self, _name):
        return self.database


class MongoAdminAuditRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.collection = _Collection()
        self.repo = MongoAdminAuditRepository(_Client(self.collection))
        now = _T0
        self.service = AdminAuditService(
            self.repo,
            clock=lambda: now,
            id_factory=iter(("e1", "op1", "e2")).__next__,
        )

    def test_tombstone_wire_uses_target_project_id_not_project_id(self) -> None:
        requested = self.service.record_purge_requested(
            admin_user_id="admin:1", target_project_id="p1", reason="정리"
        )
        self.service.record_purge_outcome(requested, outcome="succeeded")

        self.assertTrue(all("target_project_id" in doc for doc in self.collection.docs))
        self.assertTrue(all("project_id" not in doc for doc in self.collection.docs))
        events = self.repo.list_project_purge_events(limit=50)
        self.assertEqual({event.target_project_id for event in events}, {"p1"})
        self.assertTrue(all(event.at.tzinfo is not None for event in events))

    def test_latest_events_are_bounded_and_newest_first(self) -> None:
        first = self.service.record_purge_requested(
            admin_user_id="admin:1", target_project_id="p1", reason="정리"
        )
        self.service._clock = lambda: _T0 + timedelta(seconds=1)
        self.service.record_purge_outcome(first, outcome="succeeded")

        events = self.repo.list_project_purge_events(limit=1)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].outcome, "succeeded")

    def test_indexes_have_no_ttl(self) -> None:
        self.assertEqual(len(self.collection.indexes), 2)
        for _keys, _name, kwargs in self.collection.indexes:
            self.assertNotIn("expireAfterSeconds", kwargs)


if __name__ == "__main__":
    unittest.main()
