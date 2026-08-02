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


def _user(uid="user:1", username="alice", must_change_password=False):
    return User(
        id=uid, username=username, password_hash="$argon2id$fake",
        is_admin=False, is_active=True, created_at=_FIXED_TIME,
        must_change_password=must_change_password,
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

    def test_a_row_written_before_c6_reads_back_without_a_forced_change(self) -> None:
        """C-6 이전 행에는 `must_change_password` 필드 자체가 없다.

        정본 v1.7.80 이 "기존 계정은 잠기지 않는다"고 단언하는 방어인데, 2026-08-02
        독립 검증이 **그 방어가 빈 셀**임을 잡았다 — `_entry` 의 `.get(..., False)` 를
        하드 서브스크립트로 바꿔도 **1898 테스트가 전부 통과**했다. 필드 없는 문서를
        `_entry` 에 먹이는 셀이 하나도 없었기 때문이다.

        하드 서브스크립트였다면 배포에서 **C-6 이전 계정 전부가 로그인 시 KeyError**
        (500)로 죽는다 — fake collection 이 늘 새 필드를 갖고 있어 스위트는 green 인
        채로. `sessions` 의 naive-datetime 함정과 같은 형태다.
        """
        # 드라이버가 돌려주는 그대로: C-6 이전에 쓰인 문서에는 그 키가 없다.
        self.collection.docs["user:legacy"] = {
            "_id": "user:legacy",
            "username": "legacy",
            "password_hash": "H:old",
            "is_admin": False,
            "is_active": True,
            "created_at": _FIXED_TIME,
        }

        stored = self.repo.get_by_id("user:legacy")
        self.assertIsNotNone(stored)
        # 잠기지 않는다 = 교체를 요구받지 않는다.
        self.assertFalse(stored.must_change_password)

    def test_a_row_written_after_c6_keeps_its_pending_change(self) -> None:
        # over-strict 짝: 위 셀을 "항상 False" 로 만족시키는 과잉 교정(필드를 아예
        # 안 읽는 것)을 막는다. 저장된 True 는 True 로 돌아와야 한다.
        self.repo.insert(_user(must_change_password=True))
        self.assertTrue(self.repo.get_by_id("user:1").must_change_password)


if __name__ == "__main__":
    unittest.main()
