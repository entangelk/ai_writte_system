"""계정 탈퇴 Slice 3 — 파기 데몬의 순서·식별 규칙·실패 규칙.

오너 결정 D1~D6(2026-09-07) + 브리프
`docs/plans/slice3-withdrawal-purge-daemon-decisions.md` **ⓑ 두 규칙 스윕 · ⓔ 범위**
(2026-09-09).

이 파일이 잠그는 것 넷:

1. **사용자명 묘비가 파기를 살아남는다** — 그것이 이 슬라이스에서 가장 쉽게 깨지는
   자리다. `project_name_history` 선례(`_id` = 대상 id)를 그대로 따르면 두 규칙 중
   `_id` 축이 묘비를 지운다.
2. **두 규칙이 각각 무엇을 잡는가** — 필드 축만으로는 `request_quota_policies` 를
   놓치고, `_id` 축만으로는 `sessions` 를 놓친다.
3. **보존 축은 `target_user_id`** — 원장·감사·묘비가 어느 규칙에도 안 걸린다.
4. **실패하면 그 계정에서 멈춘다** — 재시도하지 않고, 다른 계정을 막지도 않는다.
"""

from __future__ import annotations

import asyncio
import unittest
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from services.application.app.auth.models import User
from services.application.app.auth.users import (
    InMemoryUserRepository,
    WITHDRAWAL_GRACE_PERIOD,
)
from services.application.app.deletion.account_axis_sweep import (
    InMemoryAccountAxisSweeper,
    MongoAccountAxisSweeper,
    USER_ID_FIELD,
)
from services.application.app.deletion.account_purge import (
    AccountPurgeService,
    NEVER_SWEPT,
)
from services.application.app.deletion.user_name_history import (
    ID_PREFIX,
    InMemoryUserNameHistoryRepository,
    UserNameHistoryService,
    UserNameSnapshot,
    document_id,
)
from services.application.app.deletion.user_name_history_mongo import (
    COLLECTION,
    MongoUserNameHistoryRepository,
)

_NOW = datetime(2026, 9, 9, 12, tzinfo=UTC)
_REQUESTED = _NOW - WITHDRAWAL_GRACE_PERIOD


def _user(user_id="user:a", *, username="alice", requested=_REQUESTED, started=None):
    return User(
        id=user_id, username=username, password_hash="h", is_admin=False,
        is_active=True, created_at=_NOW - timedelta(days=90),
        withdrawal_requested_at=requested, purge_started_at=started,
    )


@dataclass
class _Project:
    id: str
    archived: bool = False


class _FakeCoreSot:
    def __init__(self, projects: dict[str, list[_Project]] | None = None) -> None:
        self.projects = projects or {}
        self.archived: list[str] = []

    def list_projects_for_owner(self, *, owner_id):
        return tuple(self.projects.get(owner_id, ()))

    def archive_project(self, *, project_id):
        self.archived.append(project_id)
        for owned in self.projects.values():
            for project in owned:
                if project.id == project_id:
                    project.archived = True
        return project_id


class _RecordingPurge:
    """`execute_project_purge` 경계의 대역. 호출 순서와 인자를 그대로 기록한다."""

    def __init__(self, *, fail_on: str | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self._fail_on = fail_on

    async def __call__(self, *, project_id, acting_user_id):
        self.calls.append((project_id, acting_user_id))
        if project_id == self._fail_on:
            raise RuntimeError("storage went away")


def _service(users, core_sot, sweeper, purge, names=None):
    return AccountPurgeService(
        users=users, core_sot=core_sot,
        user_name_history=names or UserNameHistoryService(
            InMemoryUserNameHistoryRepository(), clock=lambda: _NOW
        ),
        sweeper=sweeper, purge_project=purge, clock=lambda: _NOW,
    )


class UserNameTombstoneTest(unittest.TestCase):
    """묘비가 **자기를 지우는 규칙에 안 걸리는가** — 이 슬라이스의 핵심 방어."""

    def setUp(self) -> None:
        self.repo = InMemoryUserNameHistoryRepository()
        self.service = UserNameHistoryService(self.repo, clock=lambda: _NOW)

    def test_a_purged_account_keeps_exactly_its_username(self) -> None:
        self.service.record_purged(user_id="user:a", username="alice")

        self.assertEqual(
            self.service.get(user_id="user:a"),
            UserNameSnapshot(
                target_user_id="user:a", username="alice", purged_at=_NOW
            ),
        )

    def test_an_unpurged_account_has_no_row(self) -> None:
        self.assertIsNone(self.service.get(user_id="user:never"))

    def test_a_second_snapshot_of_the_same_account_does_not_multiply_rows(self) -> None:
        self.service.record_purged(user_id="user:a", username="alice")
        self.service.record_purged(user_id="user:a", username="alice2")

        self.assertEqual(self.repo.count(), 1)
        self.assertEqual(self.service.get(user_id="user:a").username, "alice2")

    def test_the_document_id_is_prefixed_and_carries_no_user_id_field(self) -> None:
        """★ 이 셀이 선례 이탈의 이유 그 자체다 (브리프 ⓑ 후속 계약 1).

        `project_name_history` 는 `_id` = project id 로 프로젝트 스윕을 비껴간다.
        계정 축은 **`_id` 도 규칙**이라 같은 모양이면 데몬이 방금 자기가 쓴 묘비를
        지운다. 그래서 둘을 함께 잠근다 — `_id` 에 접두가 붙어 있고(따라서 user id 와
        같지 않다), `user_id` 필드가 **없다**.

        - under: 접두를 떼면(= 선례를 그대로 따르면) 이 셀이 실패한다.
        - under: `user_id` 필드를 더하면 이 셀이 실패한다.
        """
        collection = _Collection()
        MongoUserNameHistoryRepository(_Client(collection)).put(
            UserNameSnapshot(
                target_user_id="user:a", username="alice", purged_at=_NOW
            )
        )

        key, doc = next(iter(collection.docs.items()))
        self.assertNotEqual(key, "user:a", "묘비의 `_id` 가 user id 와 같다")
        self.assertEqual(key, ID_PREFIX + "user:a")
        self.assertEqual(set(doc), {"_id", "target_user_id", "username", "purged_at"})
        self.assertNotIn(USER_ID_FIELD, doc)

    def test_the_tombstone_survives_the_two_rule_sweep(self) -> None:
        """행위 축 — 규칙을 실제로 돌려 묘비가 남는지 본다.

        위 셀은 **저장 모양**을, 이 셀은 **결과**를 잠근다. 둘 다 필요하다:
        모양만 재면 규칙이 셋째 축으로 넓어졌을 때 못 보고, 결과만 재면 왜
        살아남았는지가 기록에 안 남는다.
        """
        sweeper = InMemoryAccountAxisSweeper({
            COLLECTION: [{
                "_id": document_id("user:a"), "target_user_id": "user:a",
                "username": "alice", "purged_at": _NOW,
            }],
        })

        self.assertEqual(sweeper.sweep("user:a"), {})
        self.assertEqual(len(sweeper.collections[COLLECTION]), 1)


class TwoRuleSweepTest(unittest.TestCase):
    """ⓑ — `user_id` 필드 **또는** `_id`. 하나만으로는 각각 다른 것을 놓친다."""

    def _sweeper(self):
        return InMemoryAccountAxisSweeper({
            # 필드 축만 잡는다
            "sessions": [
                {"_id": "t1", USER_ID_FIELD: "user:a"},
                {"_id": "t2", USER_ID_FIELD: "user:b"},
            ],
            # `_id` 축만 잡는다 — 회원당 한 행이라 기본 키가 곧 user id 다
            "request_quota_policies": [
                {"_id": "user:a", "daily_limit": 20},
                {"_id": "user:b", "daily_limit": 20},
            ],
            # 남아야 하는 셋
            "request_usage_ledger": [{"_id": "l1", "target_user_id": "user:a"}],
            "admin_audit_events": [
                {"_id": "e1", "admin_user_id": "user:z", "target_user_id": "user:a"}
            ],
            "users": [{"_id": "user:a"}, {"_id": "user:b"}],
        })

    def test_the_field_rule_takes_the_sessions_of_that_account_only(self) -> None:
        sweeper = self._sweeper()

        deleted = sweeper.sweep("user:a")

        self.assertEqual(deleted.get("sessions"), 1)
        self.assertEqual(
            [doc["_id"] for doc in sweeper.collections["sessions"]], ["t2"]
        )

    def test_the_id_rule_takes_the_quota_policy_the_field_rule_cannot_see(self) -> None:
        """★ 규칙이 하나였다면 여기가 조용히 살아남는다(2026-09-09 실측).

        `request_quota_policies` 는 `user_id` 필드를 쓰지 않는다 — 회원당 한 행이라는
        계약을 기본 키가 강제하는 의도적 설계다. 필드 규칙만 쓰면 회원의 한도·정지
        상태가 파기를 살아남고, 그것은 *약속한 삭제가 조용히 안 된 것*이다.
        """
        sweeper = self._sweeper()

        deleted = sweeper.sweep("user:a")

        self.assertEqual(deleted.get("request_quota_policies"), 1)
        self.assertEqual(
            [doc["_id"] for doc in sweeper.collections["request_quota_policies"]],
            ["user:b"],
        )

    def test_target_user_id_rows_are_never_touched(self) -> None:
        """보존 표식은 **필드 이름 하나**다 — 원장(D4)·관리자 감사가 그것을 쓴다."""
        sweeper = self._sweeper()

        deleted = sweeper.sweep("user:a")

        self.assertNotIn("request_usage_ledger", deleted)
        self.assertNotIn("admin_audit_events", deleted)
        self.assertEqual(len(sweeper.collections["request_usage_ledger"]), 1)
        self.assertEqual(len(sweeper.collections["admin_audit_events"]), 1)

    def test_the_users_collection_is_never_swept(self) -> None:
        """계정 행은 파기 그래프의 **마지막** 단계다.

        스윕이 먼저 지우면 실패를 표시할 자리(`purge_started_at`)가 사라져
        D3 의 *부분 파기로 표시하고 멈춘다* 가 성립하지 않는다.
        """
        sweeper = self._sweeper()

        deleted = sweeper.sweep("user:a")

        self.assertNotIn("users", deleted)
        self.assertEqual(len(sweeper.collections["users"]), 2)
        self.assertIn("users", NEVER_SWEPT)

    def test_the_id_rule_rests_on_the_user_id_prefix(self) -> None:
        """★ `_id` 규칙의 안전 근거를 잠근다 (브리프 ⓑ 후속 계약 3).

        전 컬렉션에 `{"_id": <user id>}` 를 던지는 것이 안전한 이유는 user id 가
        `user:<hex>` 라 다른 축의 `_id`(project id · username · client_ip · lock key ·
        묘비)와 겹칠 수 없기 때문이다. **접두를 떼면 그 근거가 사라진다** — 예컨대
        사용자명을 `_id` 로 쓰는 `login_failures` 와 충돌할 수 있다.
        """
        minted = InMemoryUserRepository()
        from services.application.app.auth.users import UserService

        service = UserService(minted, hasher=_NullHasher())
        user = service.create_user(username="alice", password="a" * 12)

        self.assertTrue(
            user.id.startswith("user:"),
            "user id 접두가 바뀌면 `_id` 스윕의 안전 근거가 사라진다",
        )
        self.assertNotEqual(user.id, user.username)


class AccountPurgeOrderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.users = InMemoryUserRepository()
        self.user = _user()
        self.users.insert(self.user)
        self.core_sot = _FakeCoreSot({"user:a": [_Project("p1"), _Project("p2")]})
        self.purge = _RecordingPurge()
        self.names_repo = InMemoryUserNameHistoryRepository()
        self.names = UserNameHistoryService(self.names_repo, clock=lambda: _NOW)
        self.sweeper = InMemoryAccountAxisSweeper({
            "sessions": [{"_id": "t1", USER_ID_FIELD: "user:a"}],
        })
        self.service = _service(
            self.users, self.core_sot, self.sweeper, self.purge, self.names
        )

    def test_a_due_account_is_purged_end_to_end(self) -> None:
        summary = asyncio.run(self.service.run_once(now=_NOW))

        self.assertEqual(summary.accounts_purged, 1)
        self.assertEqual(summary.accounts_failed, 0)
        # 프로젝트 둘이 archive 를 거쳐 **한 벌뿐인 본체**로 갔다.
        self.assertEqual(self.core_sot.archived, ["p1", "p2"])
        self.assertEqual(
            self.purge.calls, [("p1", "user:a"), ("p2", "user:a")]
        )
        # 이름은 남고 계정 행과 세션은 사라졌다.
        self.assertEqual(self.names.get(user_id="user:a").username, "alice")
        self.assertIsNone(self.users.get_by_id("user:a"))
        self.assertEqual(self.sweeper.collections["sessions"], [])

    def test_the_username_is_snapshotted_before_anything_is_destroyed(self) -> None:
        """순서가 계약이다 — 뒤로 미루면 저장 장애 한 번에 이름이 영영 사라진다.

        프로젝트 축이 같은 자리에서 같은 이유로 이 순서를 강제한다(8.2c N3).
        여기서는 **첫 프로젝트 파기를 실패시켜** 이름이 이미 남았는지 본다.
        """
        service = _service(
            self.users, self.core_sot, self.sweeper,
            _RecordingPurge(fail_on="p1"), self.names,
        )

        summary = asyncio.run(service.run_once(now=_NOW))

        self.assertEqual(summary.accounts_failed, 1)
        self.assertEqual(self.names.get(user_id="user:a").username, "alice")

    def test_an_account_whose_grace_has_not_elapsed_is_left_alone(self) -> None:
        """경계 판정은 `is_purge_due` 한 곳이다 — 29일은 아직 아니다."""
        self.users.replace(
            replace(self.user, withdrawal_requested_at=_NOW - timedelta(days=29))
        )

        summary = asyncio.run(self.service.run_once(now=_NOW))

        self.assertEqual(summary.accounts_claimed, 0)
        self.assertEqual(self.purge.calls, [])
        self.assertIsNotNone(self.users.get_by_id("user:a"))

    def test_exactly_the_thirtieth_day_is_due(self) -> None:
        """`>=` 경계. `>` 로 과잉 교정하면 이 셀이 실패한다."""
        summary = asyncio.run(self.service.run_once(now=_NOW))

        self.assertEqual(summary.accounts_purged, 1)

    def test_an_account_that_never_asked_is_not_a_candidate(self) -> None:
        self.users.replace(replace(self.user, withdrawal_requested_at=None))

        summary = asyncio.run(self.service.run_once(now=_NOW))

        self.assertEqual(summary.accounts_claimed, 0)
        self.assertIsNotNone(self.users.get_by_id("user:a"))


class AccountPurgeFailureTest(unittest.TestCase):
    """D3=ⓐ — 실패하면 표시하고 멈춘다. 재시도하지 않는다."""

    def setUp(self) -> None:
        self.users = InMemoryUserRepository()
        self.users.insert(_user())
        self.users.insert(_user("user:b", username="bob"))
        self.core_sot = _FakeCoreSot({
            "user:a": [_Project("p1"), _Project("p2")],
            "user:b": [_Project("p3")],
        })
        self.sweeper = InMemoryAccountAxisSweeper({})

    def test_a_failed_project_stops_that_account_and_marks_it(self) -> None:
        purge = _RecordingPurge(fail_on="p1")
        service = _service(self.users, self.core_sot, self.sweeper, purge)

        summary = asyncio.run(service.run_once(now=_NOW))

        failed = [r for r in summary.results if r.user_id == "user:a"][0]
        self.assertEqual(failed.failed_at, "project:p1")
        self.assertIn("storage went away", failed.error)
        # ★ 다음 프로젝트로 넘어가지 않았다 — 부분 파기를 키우지 않는다.
        self.assertNotIn(("p2", "user:a"), purge.calls)
        # 계정 행은 살아 있고 표식이 찍혔다.
        stopped = self.users.get_by_id("user:a")
        self.assertIsNotNone(stopped)
        self.assertEqual(stopped.purge_started_at, _NOW)

    def test_a_failed_account_is_never_claimed_again(self) -> None:
        """★ 재시도가 **틀린** 이유: 두 번째 호출은 404 로 끝나고 derived 에 못 간다.

        - under: 청구 조건에서 `purge_started_at` 을 빼면 두 번째 배수가 같은 계정을
          다시 때려 이 셀이 실패한다.
        """
        purge = _RecordingPurge(fail_on="p1")
        service = _service(self.users, self.core_sot, self.sweeper, purge)
        asyncio.run(service.run_once(now=_NOW))
        calls_after_first = list(purge.calls)

        second = asyncio.run(service.run_once(now=_NOW))

        self.assertEqual(purge.calls, calls_after_first)
        self.assertEqual(
            [r.user_id for r in second.results], [],
            "표시된 계정이 다시 청구됐다",
        )

    def test_one_failing_account_does_not_block_the_others(self) -> None:
        purge = _RecordingPurge(fail_on="p1")
        service = _service(self.users, self.core_sot, self.sweeper, purge)

        summary = asyncio.run(service.run_once(now=_NOW))

        self.assertEqual(summary.accounts_failed, 1)
        self.assertEqual(summary.accounts_purged, 1)
        self.assertIsNone(self.users.get_by_id("user:b"))

    def test_limit_below_one_is_rejected_rather_than_silently_raised(self) -> None:
        service = _service(self.users, self.core_sot, self.sweeper, _RecordingPurge())

        for limit in (0, -1):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    asyncio.run(service.run_once(now=_NOW, limit=limit))

    def test_a_limit_of_one_is_still_valid(self) -> None:
        """over-strict 반대편 — 경계를 `< 2` 로 조이면 이 셀이 실패한다."""
        service = _service(self.users, self.core_sot, self.sweeper, _RecordingPurge())

        summary = asyncio.run(service.run_once(now=_NOW, limit=1))

        self.assertEqual(summary.accounts_claimed, 1)


class MongoSweeperShapeTest(unittest.TestCase):
    """fake collection 왕복 — 실 어댑터가 **두 규칙 둘 다** 던지는지."""

    def test_the_adapter_issues_both_rules_against_every_collection(self) -> None:
        db = _FakeDatabase({
            "sessions": _SweepCollection(),
            "request_quota_policies": _SweepCollection(),
            "users": _SweepCollection(),
        })

        MongoAccountAxisSweeper(_FakeSweepClient(db)).sweep("user:a")

        self.assertEqual(
            db.collections["sessions"].many, [{USER_ID_FIELD: "user:a"}]
        )
        self.assertEqual(db.collections["sessions"].one, [{"_id": "user:a"}])
        # `users` 는 두 규칙 어느 쪽도 안 던진다.
        self.assertEqual(db.collections["users"].many, [])
        self.assertEqual(db.collections["users"].one, [])


class _NullHasher:
    def hash(self, password): return "h:" + password
    def verify(self, hashed, password): return hashed == "h:" + password
    def needs_rehash(self, hashed): return False


class _Collection:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}

    def create_index(self, keys, **kwargs): pass

    def replace_one(self, query, doc, *, upsert):
        assert upsert
        self.docs[query["_id"]] = dict(doc)

    def find_one(self, query):
        return self.docs.get(query["_id"])


class _Client:
    def __init__(self, collection) -> None:
        self._collection = collection

    def __getitem__(self, _name):
        return {COLLECTION: self._collection}


@dataclass
class _Deleted:
    deleted_count: int


class _SweepCollection:
    def __init__(self) -> None:
        self.many: list[dict] = []
        self.one: list[dict] = []

    def delete_many(self, query):
        self.many.append(query)
        return _Deleted(0)

    def delete_one(self, query):
        self.one.append(query)
        return _Deleted(0)


class _FakeDatabase:
    def __init__(self, collections) -> None:
        self.collections = collections

    def list_collection_names(self):
        return list(self.collections)

    def __getitem__(self, name):
        return self.collections[name]


class _FakeSweepClient:
    def __init__(self, db) -> None:
        self._db = db

    def __getitem__(self, _name):
        return self._db


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
