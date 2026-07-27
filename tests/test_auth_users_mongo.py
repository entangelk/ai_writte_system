"""Mongo user repository round-trip against a fake collection (no live Mongo),
following the gate_findings/loop_audit convention so the standard suite covers
the persistence wire without infra."""

import unittest
from datetime import UTC, datetime

from pymongo.errors import DuplicateKeyError

from services.application.app.auth.models import User
from services.application.app.auth.users import DuplicateUsername
from services.application.app.auth.users_mongo import MongoUserRepository

_FIXED_TIME = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


class _Collection:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}
        self.indexes: list[tuple] = []
        self._unique_fields: list[str] = []

    def create_index(self, keys, *, name=None, unique=False):
        self.indexes.append((keys, name, unique))
        if unique:
            self._unique_fields.extend(field for field, _ in keys)

    def insert_one(self, doc):
        if doc["_id"] in self.docs:
            raise DuplicateKeyError("duplicate _id")
        for field in self._unique_fields:
            if any(other.get(field) == doc.get(field) for other in self.docs.values()):
                raise DuplicateKeyError(f"duplicate {field}")
        self.docs[doc["_id"]] = dict(doc)

    def find_one(self, query):
        for doc in self.docs.values():
            if all(doc.get(key) == value for key, value in query.items()):
                return doc
        return None


class _Database:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == "users"
        return self.collection


class _Client:
    def __init__(self, collection):
        self.database = _Database(collection)

    def __getitem__(self, _name):
        return self.database


def _user(uid="user:1", username="alice"):
    return User(
        id=uid, username=username, password_hash="$argon2id$fake",
        is_admin=False, is_active=True, created_at=_FIXED_TIME,
    )


class MongoUserRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.collection = _Collection()
        self.repo = MongoUserRepository(_Client(self.collection))

    def test_declares_unique_username_index(self) -> None:
        self.assertIn(
            ([("username", 1)], "users_username_unique", True),
            self.collection.indexes,
        )

    def test_insert_then_get_by_id_round_trip(self) -> None:
        user = _user()
        self.repo.insert(user)
        self.assertEqual(self.repo.get_by_id("user:1"), user)

    def test_insert_then_get_by_username_round_trip(self) -> None:
        user = _user()
        self.repo.insert(user)
        self.assertEqual(self.repo.get_by_username("alice"), user)

    def test_missing_returns_none(self) -> None:
        self.assertIsNone(self.repo.get_by_id("nope"))
        self.assertIsNone(self.repo.get_by_username("nope"))

    def test_duplicate_username_maps_to_domain_error(self) -> None:
        self.repo.insert(_user(uid="user:1", username="alice"))
        # Different id, same username → the unique index fires and the raw
        # DuplicateKeyError is translated to the domain error the service knows.
        with self.assertRaises(DuplicateUsername):
            self.repo.insert(_user(uid="user:2", username="alice"))


if __name__ == "__main__":
    unittest.main()
