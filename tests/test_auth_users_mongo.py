"""Mongo user repository round-trip against a fake collection (no live Mongo),
following the gate_findings/loop_audit convention so the standard suite covers
the persistence wire without infra."""

import unittest
from datetime import UTC, datetime, timedelta

from pymongo import ReturnDocument
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

    def find(self, query):
        return _Cursor([
            dict(doc) for doc in self.docs.values()
            if all(doc.get(key) == value for key, value in query.items())
        ])

    def find_one_and_update(self, query, update, *, return_document=None):
        for doc in self.docs.values():
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update["$set"])
                # The repository asks for the post-update document; returning the
                # pre-update one here would let a broken return_document argument
                # pass unnoticed.
                assert return_document is ReturnDocument.AFTER
                return dict(doc)
        return None


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, key, direction):
        self._docs.sort(key=lambda doc: doc[key], reverse=direction == -1)
        return self

    def __iter__(self):
        return iter(self._docs)


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

    def test_list_all_round_trips_every_user_oldest_first(self) -> None:
        later = _user(uid="user:2", username="bob")
        later = User(
            id=later.id, username=later.username,
            password_hash=later.password_hash, is_admin=later.is_admin,
            is_active=later.is_active,
            created_at=_FIXED_TIME + timedelta(minutes=5),
        )
        # Inserted newest first so a repository that returned insertion order
        # instead of asking the server to sort would fail this.
        self.repo.insert(later)
        self.repo.insert(_user())

        self.assertEqual(self.repo.list_all(), (_user(), later))

    def test_list_all_is_empty_before_any_insert(self) -> None:
        self.assertEqual(self.repo.list_all(), ())

    def test_set_active_persists_and_returns_the_updated_user(self) -> None:
        self.repo.insert(_user())

        updated = self.repo.set_active("user:1", is_active=False)

        self.assertFalse(updated.is_active)
        # Under-strict guard: the returned object must come from the store, not
        # be a locally patched copy, so re-read it.
        self.assertFalse(self.repo.get_by_id("user:1").is_active)
        # Over-strict: nothing else moved.
        self.assertEqual(self.repo.get_by_id("user:1").username, "alice")

    def test_set_active_on_an_unknown_user_returns_none(self) -> None:
        self.assertIsNone(self.repo.set_active("user:ghost", is_active=False))


if __name__ == "__main__":
    unittest.main()
