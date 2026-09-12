"""Mongo user repository round-trip against a fake collection (no live Mongo),
following the gate_findings/loop_audit convention so the standard suite covers
the persistence wire without infra."""

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from services.application.app.auth.models import User
from services.application.app.auth.users import (
    DuplicateUsername, is_purge_due, TERMS_VERSION,
    USER_STATUS_ACTIVE, USER_STATUS_PENDING, USER_STATUS_REJECTED,
)
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

    def replace_one(self, query, replacement):
        # Driver semantics: matched 0 → nothing written (no upsert).
        for doc_id, doc in self.docs.items():
            if all(doc.get(key) == value for key, value in query.items()):
                self.docs[doc_id] = dict(replacement)
                return

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


def _user(uid="user:1", username="alice", must_change_password=False,
          status=USER_STATUS_ACTIVE):
    return User(
        id=uid, username=username, password_hash="$argon2id$fake",
        is_admin=False, is_active=True, created_at=_FIXED_TIME,
        must_change_password=must_change_password, status=status,
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

    def test_a_row_written_before_signup_approval_reads_back_active(self) -> None:
        """가입 승인 필드(status) 이전에 쓰인 행은 "active" 로 읽힌다.

        C-6 의 `.get` 방어와 같은 병을 미리 막는 셀이다 — `_entry` 의
        `doc.get("status", "active")` 를 하드 서브스크립트로 바꾸면 이 셀이
        실패해야 한다. 실패하지 않으면(빈 셀이면) 승인 슬라이스 배포 직후
        **기존 관리자·사용자 전부가 로그인에서 KeyError(500)** 로 죽는다.
        """
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
        self.assertEqual(stored.status, USER_STATUS_ACTIVE)

    def test_signup_status_round_trips(self) -> None:
        # over-strict 짝: 위 셀을 상수 반환로 만족시키는 과잉 교정(필드를 안
        # 읽는 것)을 막는다. pending 으로 쓰면 pending 으로 돌아온다.
        self.repo.insert(_user(status=USER_STATUS_PENDING))
        self.assertEqual(
            self.repo.get_by_id("user:1").status, USER_STATUS_PENDING
        )

    def test_replace_overwrites_the_row_wholesale(self) -> None:
        original = _user(status=USER_STATUS_REJECTED)
        self.repo.insert(original)
        replacement = User(
            id=original.id, username=original.username,
            password_hash="H:new-pw", is_admin=False, is_active=True,
            created_at=_FIXED_TIME, must_change_password=False,
            status=USER_STATUS_PENDING,
        )
        self.repo.replace(replacement)
        stored = self.repo.get_by_id(original.id)
        self.assertEqual(stored.password_hash, "H:new-pw")
        self.assertEqual(stored.status, USER_STATUS_PENDING)
        # 덮어쓴 것이지 두 번째 행이 생긴 것이 아니다.
        self.assertEqual(len(self.collection.docs), 1)

    def test_list_pending_returns_only_pending_rows(self) -> None:
        # Pre-signup rows (no status field) can never be pending — the filter
        # is on the stored field, and their absence from the queue is what
        # keeps administrator-created accounts out of the approval queue.
        self.collection.docs["user:legacy"] = {
            "_id": "user:legacy", "username": "legacy",
            "password_hash": "H:old", "is_admin": True, "is_active": True,
            "created_at": _FIXED_TIME,
        }
        self.repo.insert(_user(status=USER_STATUS_PENDING))
        self.repo.insert(_user(uid="user:2", username="active-user"))

        pending = self.repo.list_pending()
        self.assertEqual([u.id for u in pending], ["user:1"])

    def test_set_status_persists_and_returns_the_updated_user(self) -> None:
        self.repo.insert(_user(status=USER_STATUS_PENDING))
        updated = self.repo.set_status("user:1", status=USER_STATUS_ACTIVE)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, USER_STATUS_ACTIVE)
        self.assertEqual(
            self.repo.get_by_id("user:1").status, USER_STATUS_ACTIVE
        )

    def test_set_status_on_an_unknown_user_returns_none(self) -> None:
        self.assertIsNone(
            self.repo.set_status("user:ghost", status=USER_STATUS_ACTIVE)
        )

    # --- 계정 탈퇴 상태 축(Slice 0, 2026-09-07) ----------------------------

    def test_withdrawal_request_persists_and_returns_the_updated_user(self) -> None:
        self.repo.insert(_user())
        updated = self.repo.set_withdrawal_requested_at("user:1", at=_FIXED_TIME)
        self.assertEqual(updated.withdrawal_requested_at, _FIXED_TIME)
        self.assertEqual(
            self.repo.get_by_id("user:1").withdrawal_requested_at, _FIXED_TIME
        )

    def test_cancelling_writes_none_rather_than_leaving_the_stamp(self) -> None:
        self.repo.insert(_user())
        self.repo.set_withdrawal_requested_at("user:1", at=_FIXED_TIME)
        cleared = self.repo.set_withdrawal_requested_at("user:1", at=None)
        self.assertIsNone(cleared.withdrawal_requested_at)
        self.assertIsNone(
            self.repo.get_by_id("user:1").withdrawal_requested_at
        )
        # 저장면까지 본다: 필드가 남아 옛 값을 들고 있으면 파기 데몬이 취소한
        # 계정을 집는다.
        self.assertIsNone(
            self.collection.docs["user:1"]["withdrawal_requested_at"]
        )

    def test_set_withdrawal_on_an_unknown_user_returns_none(self) -> None:
        self.assertIsNone(
            self.repo.set_withdrawal_requested_at("user:ghost", at=_FIXED_TIME)
        )

    def test_a_row_written_before_the_withdrawal_axis_reads_back_as_not_withdrawing(self):
        """탈퇴 축 이전에 쓰인 행에는 그 키가 없다.

        `must_change_password`·`status` 와 같은 계열의 셀이다 — `_entry` 의
        `.get` 을 하드 서브스크립트로 바꾸면 **기존 계정 전부가 로그인에서
        KeyError(500)** 로 죽는데, fake collection 이 늘 새 필드를 갖고 있으면
        스위트는 초록인 채다(2026-08-02 독립 검증이 잡은 바로 그 빈 셀).
        """
        self.collection.docs["user:legacy"] = {
            "_id": "user:legacy", "username": "legacy",
            "password_hash": "H:old", "is_admin": False, "is_active": True,
            "created_at": _FIXED_TIME, "status": USER_STATUS_ACTIVE,
        }
        stored = self.repo.get_by_id("user:legacy")
        self.assertIsNotNone(stored)
        self.assertIsNone(stored.withdrawal_requested_at)

    def test_the_write_face_carries_the_stamp_through_insert_and_replace(self) -> None:
        """★ 쓰기면(`_doc`)에도 탈퇴 필드가 실려야 한다 — 독립 검증 H1(2026-09-08).

        위의 두 셀은 전부 `set_withdrawal_requested_at`(=`find_one_and_update`)로
        값을 넣으므로 **`_doc` 을 한 번도 지나지 않는다.** 그래서 `_doc` 에서 이
        필드를 빼도 **아무 셀도 안 물렸다**(검증자 대항 변이 X1 = 0실패).

        빠졌을 때 실제로 나는 일: `insert`(신규 계정)와 `replace`(가입 재요청)가
        쓰는 문서에 키가 없어진다. 지금은 두 경로 다 값이 `None` 이라 무해하지만,
        **`replace` 는 행을 통째로 덮으므로** 탈퇴 상태를 든 행이 그 경로를 지나면
        스탬프가 **조용히 사라진다** — 파기 예정이던 계정이 예정에서 빠지고, 그
        실패는 아무 데서도 안 보인다.

        `_doc` 을 지나는 두 경로 모두 왕복시킨다.
        """
        withdrawing = replace(_user(), withdrawal_requested_at=_FIXED_TIME)
        self.repo.insert(withdrawing)
        self.assertEqual(
            self.repo.get_by_id("user:1").withdrawal_requested_at, _FIXED_TIME
        )
        # 저장면까지: `_doc` 이 키를 안 실으면 여기서 KeyError 다.
        self.assertEqual(
            self.collection.docs["user:1"]["withdrawal_requested_at"], _FIXED_TIME
        )

        later = _FIXED_TIME + timedelta(days=3)
        self.repo.replace(replace(withdrawing, withdrawal_requested_at=later))
        self.assertEqual(
            self.repo.get_by_id("user:1").withdrawal_requested_at, later
        )

    def test_a_conditional_stamp_is_decided_by_the_query_not_the_caller(self) -> None:
        """H2 — 조건이 **질의로** 내려가야 저장소가 경쟁을 가른다.

        `find_one_and_update` 의 필터에 조건이 없으면 두 요청이 모두 쓰기에
        도달하고 나중 것이 이긴다. 여기서 재는 것은 그 필터다.
        """
        self.repo.insert(_user())
        self.repo.set_withdrawal_requested_at("user:1", at=_FIXED_TIME)
        later = _FIXED_TIME + timedelta(days=7)
        self.assertIsNone(self.repo.set_withdrawal_requested_at(
            "user:1", at=later, only_if_absent=True
        ))
        self.assertEqual(
            self.collection.docs["user:1"]["withdrawal_requested_at"], _FIXED_TIME
        )

    def test_a_conditional_stamp_also_matches_a_row_that_never_had_the_field(self):
        """★ 조건은 `None` 과 **키 없음**을 같이 골라야 한다.

        탈퇴 축 이전에 쓰인 행에는 키 자체가 없다. 필터가 그것을 못 고르면
        **기존 계정 전부가 탈퇴를 요청할 수 없다** — 첫 요청이 조용히 실패하고
        화면은 아무 일도 안 일어난 것처럼 보인다. `_entry` 가 둘을 같은 값으로
        읽으므로 쓰기면도 같아야 한다.
        """
        self.collection.docs["user:legacy"] = {
            "_id": "user:legacy", "username": "legacy",
            "password_hash": "H:old", "is_admin": False, "is_active": True,
            "created_at": _FIXED_TIME, "status": USER_STATUS_ACTIVE,
        }
        updated = self.repo.set_withdrawal_requested_at(
            "user:legacy", at=_FIXED_TIME, only_if_absent=True
        )
        self.assertIsNotNone(updated, "옛 행이 탈퇴를 요청하지 못한다")
        self.assertEqual(updated.withdrawal_requested_at, _FIXED_TIME)

    def test_a_naive_stored_stamp_reads_back_aware(self) -> None:
        """★ pymongo 는 BSON 날짜를 **naive** 로 돌려준다.

        `is_purge_due` 가 이 값을 aware `now` 와 비교하므로, 재라벨링이 없으면
        파기 데몬이 탈퇴한 계정마다 `TypeError` 로 죽는다 — 그리고 그것은
        **드라이버가 있는 배포에서만** 드러난다(fake collection 은 넣은 그대로를
        돌려준다). 그래서 드라이버가 하는 일을 여기서 흉내 낸다.
        """
        self.repo.insert(_user())
        # 드라이버가 돌려주는 모양: tzinfo 가 벗겨진 채로.
        self.collection.docs["user:1"]["withdrawal_requested_at"] = (
            _FIXED_TIME.replace(tzinfo=None)
        )
        stored = self.repo.get_by_id("user:1")
        self.assertEqual(stored.withdrawal_requested_at, _FIXED_TIME)
        # 비교 자체가 서는지까지 본다(TypeError 가 나면 여기서 터진다).
        self.assertTrue(is_purge_due(
            stored, now=_FIXED_TIME + timedelta(days=30)
        ))

    def test_a_row_written_before_the_consent_axis_reads_back_as_not_consenting(self):
        """동의 축 이전에 쓰인 행에는 그 키가 없다 (방침 제3조 — 소급 동의 금지).

        `must_change_password`·`status`·탈퇴 축과 같은 계열의 방어 셀이다 —
        `_entry` 의 `.get` 을 하드 서브스크립트로 바꾸면 **현존 계정 전부가
        로그인에서 KeyError(500)** 로 죽는다(독립 검증 2026-09-12 조건 C1·MV-B).
        None 판독은 결함이 아니라 방침적 사실이다: 게이트 이전 가입자와 관리자가
        만든 계정은 동의한 적 없는 인구다.
        """
        self.collection.docs["user:legacy"] = {
            "_id": "user:legacy", "username": "legacy",
            "password_hash": "H:old", "is_admin": False, "is_active": True,
            "created_at": _FIXED_TIME, "status": USER_STATUS_ACTIVE,
        }
        stored = self.repo.get_by_id("user:legacy")
        self.assertIsNotNone(stored)
        self.assertIsNone(stored.terms_agreed_at)
        self.assertIsNone(stored.terms_version_agreed)

    def test_the_write_face_carries_the_consent_stamp_through_insert_and_replace(self):
        """★ 쓰기면(`_doc`)에도 동의 스탬프가 실려야 한다 — 독립 검증 C1·MV-A.

        동의 스탬프는 `insert`(신규 가입)와 `replace`(거절 재요청)로만 들어간다
        — 갱신 API 가 없다. 그래서 `_doc` 에서 이 두 필드를 빼도 **가입은 계속
        성공**하고(201) 스탬프는 몽고에 영영 안 쓰인다. 방침 제3조 *"운영자는
        동의한 시각과 동의한 문서의 버전을 기록합니다"* 가 배포에서 조용히
        거짓이 되는 모양이고, 2026-09-12 독립 검증이 실측했다(변이 MV-A =
        auth 초점 277셀 전건 초록). 탈퇴축 선례
        (`test_the_write_face_carries_the_stamp_through_insert_and_replace`)
        와 같은 모양으로 저장면까지 왕복시킨다.
        """
        agreed = replace(
            _user(),
            terms_agreed_at=_FIXED_TIME, terms_version_agreed=TERMS_VERSION,
        )
        self.repo.insert(agreed)
        self.assertEqual(
            self.repo.get_by_id("user:1").terms_agreed_at, _FIXED_TIME
        )
        # 저장면까지: `_doc` 이 키를 안 실으면 여기서 KeyError 다.
        self.assertEqual(
            self.collection.docs["user:1"]["terms_agreed_at"], _FIXED_TIME
        )
        self.assertEqual(
            self.collection.docs["user:1"]["terms_version_agreed"], TERMS_VERSION
        )

        # 재요청 갈래 — `replace` 가 행을 통째로 덮으므로 새 동의가 실려야 한다.
        later = _FIXED_TIME + timedelta(days=2)
        self.repo.replace(replace(agreed, terms_agreed_at=later))
        self.assertEqual(self.repo.get_by_id("user:1").terms_agreed_at, later)
        self.assertEqual(
            self.collection.docs["user:1"]["terms_agreed_at"], later
        )


if __name__ == "__main__":
    unittest.main()
