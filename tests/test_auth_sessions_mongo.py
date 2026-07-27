"""Mongo session repository round-trip against a fake collection (no live Mongo)."""

import unittest
from datetime import UTC, datetime, timedelta

from services.application.app.auth.models import Session
from services.application.app.auth.sessions_mongo import MongoSessionRepository

_T0 = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


class _Collection:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}
        self.indexes: list[tuple] = []

    def create_index(self, keys, *, name=None, **kwargs):
        self.indexes.append((keys, name, kwargs))

    def insert_one(self, doc):
        self.docs[doc["_id"]] = dict(doc)

    def find_one(self, query):
        for doc in self.docs.values():
            if all(doc.get(key) == value for key, value in query.items()):
                return doc
        return None

    def delete_one(self, query):
        self.docs.pop(query["_id"], None)

    def delete_many(self, query):
        for key in [
            k for k, d in self.docs.items()
            if all(d.get(f) == v for f, v in query.items())
        ]:
            del self.docs[key]


class _Database:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == "sessions"
        return self.collection


class _Client:
    def __init__(self, collection):
        self.database = _Database(collection)

    def __getitem__(self, _name):
        return self.database


def _session(token_hash="h1", user_id="user:1"):
    return Session(
        token_hash=token_hash, user_id=user_id,
        created_at=_T0, expires_at=_T0 + timedelta(days=7),
    )


class MongoSessionRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.collection = _Collection()
        self.repo = MongoSessionRepository(_Client(self.collection))

    def test_declares_user_and_ttl_indexes(self) -> None:
        names = {name for _, name, _ in self.collection.indexes}
        self.assertIn("sessions_by_user", names)
        self.assertIn("sessions_ttl", names)
        ttl = next(kw for _, name, kw in self.collection.indexes
                   if name == "sessions_ttl")
        self.assertEqual(ttl.get("expireAfterSeconds"), 0)

    def test_insert_then_get_round_trip(self) -> None:
        session = _session()
        self.repo.insert(session)
        self.assertEqual(self.repo.get("h1"), session)

    def test_get_missing_returns_none(self) -> None:
        self.assertIsNone(self.repo.get("nope"))

    def test_delete_removes(self) -> None:
        self.repo.insert(_session())
        self.repo.delete("h1")
        self.assertIsNone(self.repo.get("h1"))

    def test_delete_for_user_only_targets_that_user(self) -> None:
        self.repo.insert(_session(token_hash="h1", user_id="user:1"))
        self.repo.insert(_session(token_hash="h2", user_id="user:1"))
        self.repo.insert(_session(token_hash="h3", user_id="user:2"))
        self.repo.delete_for_user("user:1")
        self.assertIsNone(self.repo.get("h1"))
        self.assertIsNone(self.repo.get("h2"))
        self.assertIsNotNone(self.repo.get("h3"))


if __name__ == "__main__":
    unittest.main()
