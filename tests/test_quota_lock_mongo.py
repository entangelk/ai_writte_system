"""`request_locks` 어댑터 (Slice 8.2b).

세 가지가 이 파일의 존재 이유다.

1. **차지가 연산 하나여야 한다**(G3=A). 읽고 판단하고 쓰면 동시 두 요청이 둘 다
   "없음"을 읽는다 — 그것이 이 슬라이스가 존재하는 이유 자체를 무효로 만든다.
   ``test_claiming_a_free_key_takes_exactly_one_operation`` 이 호출 기록으로 단정한다.
2. **판정이 문서 존재가 아니라 ``expires_at`` 비교여야 한다.** fake 는 **TTL 을
   흉내 내지 않으므로** 만료된 잠금의 문서가 그대로 남아 있고, 그래도 차지에 성공해야
   한다. 존재로 판정하는 구현은 여기서 막히며, 그 결함은 운영에서만 보인다(TTL 주기
   ~60초 → 5초가 최대 1분).
3. **fencing**(§0.4). 갱신 필터가 ``holder`` 를 들지 않으면 먼저 시작한 요청이 남의
   잠금을 푼다.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from pymongo.errors import DuplicateKeyError

from services.application.app.quota.lock import (
    LockBlocked,
    LockGranted,
    RequestLock,
    RequestLockService,
)
from services.application.app.quota.lock_mongo import (
    CLAIM_ATTEMPTS,
    COLLECTION,
    MongoRequestLockRepository,
    lock_entry,
)

AT = datetime(2026, 8, 3, 5, 0, tzinfo=UTC)
KEY = "user-1:writing_generate:proj-1"
WINDOW = timedelta(seconds=5)
LEASE = timedelta(seconds=180)


def _lock(holder="h1", *, key=KEY, claimed_at=AT):
    return RequestLock(
        key=key, holder=holder, claimed_at=claimed_at,
        expires_at=claimed_at + LEASE, released_at=None,
    )


def _naive(value: datetime) -> datetime:
    """드라이버가 돌려주는 모양 — fake 문서에 직접 써 넣을 때 쓴다."""

    return value.astimezone(UTC).replace(tzinfo=None)


def _strip_tzinfo(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC).replace(tzinfo=None)
    if isinstance(value, dict):
        return {key: _strip_tzinfo(item) for key, item in value.items()}
    return value


def _matches(doc, query):
    for field, condition in query.items():
        value = doc.get(field)
        condition = _strip_tzinfo(condition)
        if isinstance(condition, dict):
            if "$lte" in condition and not (
                value is not None and value <= condition["$lte"]
            ):
                return False
            if "$gt" in condition and not (
                value is not None and value > condition["$gt"]
            ):
                return False
            if "$regex" in condition:
                import re as _re  # noqa: PLC0415

                if value is None or _re.search(condition["$regex"], value) is None:
                    return False
        elif value != condition:
            return False
    return True


class _UpdateResult:
    def __init__(self, matched):
        self.matched_count = matched


class _Collection:
    """드라이버 흉내 — `_id` 유일성과 naive 날짜를 재현하고, **TTL 은 흉내 내지 않는다**."""

    def __init__(self):
        self.docs: dict[str, dict] = {}
        self.indexes: list[tuple] = []
        self.calls: list[str] = []
        self.on_conflict = None
        """`_id` 충돌 직후 실 서버에서 일어날 수 있는 일을 끼워 넣는 seam.

        충돌과 그 뒤의 확인 읽기 **사이**가 이 슬라이스에서 가장 위험한 구간이다
        (2026-08-03 독립 검증 B1) — 그 사이에 원래 요청이 해제하거나 TTL 이 문서를
        치울 수 있고, 그것을 안 보는 구현은 거짓 차단이나 **저장 없는 성공**을 낸다.
        """

    def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))

    def find_one(self, query, projection=None):
        self.calls.append("find_one")
        for doc in self.docs.values():
            if _matches(doc, query):
                return dict(doc)
        return None

    def find_one_and_update(self, query, update, *, upsert=False,
                            return_document=None):
        self.calls.append("find_one_and_update")
        changes = _strip_tzinfo(update["$set"])
        for doc in self.docs.values():
            if _matches(doc, query):
                doc.update(changes)
                return dict(doc)
        if not upsert:
            return None
        if query["_id"] in self.docs:
            # 살아 있는 잠금이 있어 필터는 안 맞는데 `_id` 는 이미 있다.
            if self.on_conflict is not None:
                self.on_conflict()
            raise DuplicateKeyError(query["_id"])
        self.docs[query["_id"]] = {"_id": query["_id"], **changes}
        return dict(self.docs[query["_id"]])

    def count_documents(self, query):
        self.calls.append("count_documents")
        return sum(1 for doc in self.docs.values() if _matches(doc, query))

    def update_one(self, query, update, upsert=False):
        self.calls.append("update_one")
        changes = _strip_tzinfo(update["$set"])
        for doc in self.docs.values():
            if _matches(doc, query):
                doc.update(changes)
                return _UpdateResult(1)
        return _UpdateResult(0)

    def replace_one(self, query, document, upsert=False):
        self.calls.append("replace_one")
        stored = _strip_tzinfo(document)
        self.docs[stored["_id"]] = stored
        return _UpdateResult(1)


class _Database:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == COLLECTION
        return self.collection


class _Client:
    def __init__(self, collection):
        self.database = _Database(collection)

    def __getitem__(self, _name):
        return self.database


class MongoRequestLockRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.collection = _Collection()
        self.repo = MongoRequestLockRepository(_Client(self.collection))
        self.collection.calls.clear()

    # ------------------------------------------------------------- 인덱스

    def test_the_only_index_is_the_cleanup_ttl(self):
        # 키가 곧 `_id` 라 조회 인덱스가 필요 없다(§0.1). 인덱스가 늘면 그 주장이
        # 조용히 낡는다.
        self.assertEqual(len(self.collection.indexes), 1)
        keys, options = self.collection.indexes[0]
        self.assertEqual(options["name"], "request_locks_ttl")
        self.assertEqual([name for name, _direction in keys], ["expires_at"])
        self.assertEqual(options["expireAfterSeconds"], 0)

    # --------------------------------------------------------------- 차지

    def test_claiming_a_free_key_takes_exactly_one_operation(self):
        # ★ G3=A — 읽고 판단하고 쓰는 형태로 바뀌면 여기서 막힌다.
        self.repo.claim(_lock("h1"), now=AT)
        self.assertEqual(self.collection.calls, ["find_one_and_update"])

    def test_the_claim_filter_compares_the_expiry_and_not_the_existence(self):
        # 같은 규칙의 다른 각도: 필터에서 만료 비교가 빠지면 살아 있는 잠금을 덮어쓴다.
        captured = {}
        original = self.collection.find_one_and_update

        def spy(query, update, **kwargs):
            captured.update(query=query, kwargs=kwargs)
            return original(query, update, **kwargs)

        self.collection.find_one_and_update = spy
        self.repo.claim(_lock("h1"), now=AT)
        self.assertEqual(captured["query"], {"_id": KEY, "expires_at": {"$lte": AT}})
        self.assertTrue(captured["kwargs"]["upsert"])

    def test_a_live_lock_blocks_and_the_blocking_lock_comes_back(self):
        self.repo.claim(_lock("h1"), now=AT)
        current = self.repo.claim(_lock("h2"), now=AT + timedelta(seconds=1))
        self.assertEqual(current.holder, "h1")

    def test_an_expired_lock_is_reclaimed_although_the_document_is_still_there(self):
        # ★ fake 에는 TTL 이 없다 — 문서는 그대로인데 차지에 성공해야 한다.
        self.repo.claim(_lock("h1"), now=AT)
        later = AT + LEASE + timedelta(seconds=1)
        self.assertIn(KEY, self.collection.docs)
        current = self.repo.claim(_lock("h2", claimed_at=later), now=later)
        self.assertEqual(current.holder, "h2")

    def test_the_fake_never_removes_documents_on_its_own(self):
        # 위 셀의 가드의 가드. fake 가 TTL 을 흉내 내기 시작하면 위 셀은 아무것도
        # 증명하지 못한다(문서가 사라져서 통과하기 때문이다).
        self.repo.claim(_lock("h1"), now=AT)
        self.assertIn(KEY, self.collection.docs)

    # ------------------------------------ 충돌 뒤 경쟁 (독립 검증 B1·B2 폐쇄)

    def test_a_lock_released_between_the_conflict_and_the_read_is_not_a_false_block(
        self,
    ):
        # ★ B1의 한쪽: 충돌 직후 원래 요청이 해제하고 냉각까지 지나면 그 잠금은
        # **만료된 것**이다. 충돌을 곧 "잠겨 있음"으로 읽는 구현은 여기서 남을
        # 1초짜리 거짓 차단으로 막는다 — "`expires_at > now` 가 판정의 유일한 축"과
        # 정면으로 어긋난다.
        self.repo.claim(_lock("h1"), now=AT)

        def release_and_cool_down():
            self.collection.docs[KEY].update({
                "released_at": _naive(AT), "expires_at": _naive(AT),
            })

        self.collection.on_conflict = release_and_cool_down
        current = self.repo.claim(_lock("h2"), now=AT)
        self.assertEqual(current.holder, "h2")
        self.assertEqual(self.collection.docs[KEY]["holder"], "h2")

    def test_a_lock_removed_between_the_conflict_and_the_read_is_actually_stored(self):
        # ★ B1의 더 위험한 쪽: 문서가 사라졌다고 **저장 없는 성공**을 돌려주면 잠금이
        # DB 에 없으므로 **다음 요청도 통과한다** — 서로 다른 두 요청이 동시에 돌고,
        # 이 슬라이스가 막으려던 중복 과금이 그대로 열린다.
        self.repo.claim(_lock("h1"), now=AT)
        self.collection.on_conflict = lambda: self.collection.docs.pop(KEY, None)
        current = self.repo.claim(_lock("h2"), now=AT)
        self.assertEqual(current.holder, "h2")
        self.assertEqual(self.collection.docs[KEY]["holder"], "h2")

        # 그리고 그 뒤에 온 요청은 막힌다(= 저장이 실제로 됐다).
        self.collection.on_conflict = None
        self.assertEqual(self.repo.claim(_lock("h3"), now=AT).holder, "h2")

    def test_every_granted_claim_is_persisted(self):
        # B2 — `LockGranted(holder=X)` 뒤에는 언제나 저장소가 X 를 들고 있어야 한다.
        # 차지가 성립하는 세 경로(빈 키 · 만료 회수 · 강제 재차지)를 모두 지난다.
        first = self.repo.claim(_lock("h1"), now=AT)
        self.assertEqual(self.collection.docs[KEY]["holder"], first.holder)

        later = AT + LEASE + timedelta(seconds=1)
        second = self.repo.claim(_lock("h2", claimed_at=later), now=later)
        self.assertEqual(self.collection.docs[KEY]["holder"], second.holder)

        self.repo.force_claim(_lock("h3", claimed_at=later))
        self.assertEqual(self.collection.docs[KEY]["holder"], "h3")

    def test_a_conflict_that_never_resolves_fails_closed(self):
        # 종료 정책(검증 지적 4): 재시도는 **유한**해야 하고, 소진되면 성공을 날조하는
        # 대신 실패해야 한다. 실수 중복을 허용하느니 요청을 실패시킨다.
        self.repo.claim(_lock("h1"), now=AT)
        self.collection.find_one = lambda *_args, **_kwargs: None  # 늘 "없다"고 본다
        self.collection.calls.clear()
        with self.assertRaises(DuplicateKeyError):
            self.repo.claim(_lock("h2"), now=AT)
        self.assertEqual(
            self.collection.calls.count("find_one_and_update"), CLAIM_ATTEMPTS)
        self.assertEqual(self.collection.docs[KEY]["holder"], "h1")  # 남의 잠금 무손상

    def test_zero_attempts_fails_closed_with_a_stated_reason(self):
        """under-strict: `conflict is None` 가드를 빼면 이 셀이 다시 실패한다.

        종전에는 이 경로가 `raise None` → `TypeError` 였다. 잠금을 안 걸고 나가는
        것은 같지만 **이유를 말하지 않는** 실패라, 호출자도 로그를 보는 사람도
        무슨 일이 났는지 알 수 없다. 이 상수는 "유한해야 한다"는 이유로 존재하므로
        0 으로 바뀔 수 있는 값이다(2026-08-20 mypy 가드가 찾았다).

        over-strict 쪽은 바로 위 `test_a_conflict_that_never_resolves_fails_closed`
        가 잠근다 — 정상 소진은 여전히 `DuplicateKeyError` 여야지 이 새 오류가
        아니다. 둘을 함께 봐야 이 가드가 양방향이 된다.
        """
        with patch("services.application.app.quota.lock_mongo.CLAIM_ATTEMPTS", 0):
            with self.assertRaises(RuntimeError) as raised:
                self.repo.claim(_lock("h1"), now=AT)
        self.assertNotIsInstance(raised.exception, TypeError)
        self.assertIn("CLAIM_ATTEMPTS", str(raised.exception))
        # 시도를 아예 안 했으므로 아무것도 안 남았다.
        self.assertEqual(self.collection.docs, {})

    # --------------------------------------------------------------- 해제

    def test_releasing_as_the_owner_moves_the_lock_into_its_cooldown(self):
        self.repo.claim(_lock("h1"), now=AT)
        released_at = AT + timedelta(seconds=1)
        self.assertTrue(self.repo.release(
            KEY, holder="h1", now=released_at, minimum_window=WINDOW))
        stored = lock_entry(self.collection.docs[KEY])
        self.assertEqual(stored.released_at, released_at)
        self.assertEqual(stored.expires_at, AT + WINDOW)  # 차지 시각 기준이다

    def test_a_release_by_the_previous_holder_changes_nothing(self):
        # ★ fencing — 강제 재차지 뒤 옛 요청이 완료되며 해제를 부르는 그 자리.
        self.repo.claim(_lock("h1"), now=AT)
        self.repo.force_claim(_lock("h2", claimed_at=AT + timedelta(seconds=5)))
        before = dict(self.collection.docs[KEY])
        self.assertFalse(self.repo.release(
            KEY, holder="h1", now=AT + timedelta(seconds=23),
            minimum_window=WINDOW))
        self.assertEqual(self.collection.docs[KEY], before)

    def test_releasing_a_key_that_does_not_exist_is_a_no_op(self):
        self.assertFalse(self.repo.release(
            "nobody", holder="h1", now=AT, minimum_window=WINDOW))

    def test_the_release_update_filters_on_the_holder(self):
        # 읽기에서만 소유권을 보고 쓰기 필터에서 빠뜨리면, 읽기와 쓰기 사이의 강제
        # 재차지를 덮어쓴다. 필터 자체를 못박는다.
        self.repo.claim(_lock("h1"), now=AT)
        captured = {}
        original = self.collection.update_one

        def spy(query, update, **kwargs):
            captured.update(query=query)
            return original(query, update, **kwargs)

        self.collection.update_one = spy
        self.repo.release(KEY, holder="h1", now=AT, minimum_window=WINDOW)
        self.assertEqual(captured["query"], {"_id": KEY, "holder": "h1"})

    # --------------------------------------------------- 강제 재차지·왕복

    def test_a_forced_claim_overwrites_a_live_lock(self):
        self.repo.claim(_lock("h1"), now=AT)
        self.repo.force_claim(_lock("h2", claimed_at=AT + timedelta(seconds=5)))
        self.assertEqual(lock_entry(self.collection.docs[KEY]).holder, "h2")

    def test_a_forced_claim_clears_a_previous_release(self):
        self.repo.claim(_lock("h1"), now=AT)
        self.repo.release(KEY, holder="h1", now=AT + timedelta(seconds=1),
                          minimum_window=WINDOW)
        self.repo.force_claim(_lock("h2", claimed_at=AT + timedelta(seconds=2)))
        self.assertIsNone(lock_entry(self.collection.docs[KEY]).released_at)

    def test_the_stored_key_set_is_pinned_and_carries_no_project_id(self):
        # 프로젝트 축은 `_id` 안에만 있다. `project_id` 필드가 생기면 purge
        # reconciler 의 컬렉션 발견에 걸린다(§43D 와 같은 함정).
        self.repo.claim(_lock("h1"), now=AT)
        self.assertEqual(set(self.collection.docs[KEY]), {
            "_id", "holder", "claimed_at", "expires_at", "released_at",
        })

    def test_dates_come_back_aware(self):
        self.repo.claim(_lock("h1"), now=AT)
        self.repo.release(KEY, holder="h1", now=AT + timedelta(seconds=1),
                          minimum_window=WINDOW)
        stored = lock_entry(self.collection.docs[KEY])
        self.assertIsNotNone(stored.claimed_at.tzinfo)
        self.assertIsNotNone(stored.expires_at.tzinfo)
        self.assertIsNotNone(stored.released_at.tzinfo)

    def test_the_fake_really_returns_naive_dates(self):
        # 위 셀이 무엇을 지키는지 못박는다(8.1·8.2와 같은 가드의 가드).
        self.repo.claim(_lock("h1"), now=AT)
        self.assertIsNone(self.collection.docs[KEY]["claimed_at"].tzinfo)

    def test_round_trip_preserves_the_lock(self):
        self.repo.claim(_lock("h1"), now=AT)
        self.assertEqual(lock_entry(self.collection.docs[KEY]), _lock("h1"))


class InFlightCountAdapterTest(unittest.TestCase):
    """8.3 Q3=E — 접두 조회가 회원 경계와 판정 축을 둘 다 지키는가."""

    def setUp(self):
        self.collection = _Collection()
        self.repo = MongoRequestLockRepository(
            _Client(self.collection), db_name="test")

    def _store(self, key, *, released=False, expires_at=AT + LEASE):
        self.collection.docs[key] = {
            "_id": key, "holder": "h", "claimed_at": _naive(AT),
            "expires_at": _naive(expires_at),
            "released_at": _naive(AT) if released else None,
        }

    def test_it_counts_only_that_members_live_unreleased_locks(self):
        self._store("user-1:writing_generate:proj-1")
        self._store("user-1:writing_gate:proj-2")
        self._store("user-1:writing_report:proj-1", released=True)
        self._store("user-1:context_search:proj-1", expires_at=AT)  # 만료
        self._store("user-2:writing_generate:proj-1")
        self.assertEqual(self.repo.count_in_flight("user-1", now=AT), 2)

    def test_a_member_id_is_not_read_as_a_pattern(self):
        # 정규식 메타문자를 escape 하지 않으면 앵커가 남의 잠금을 세거나 아무것도
        # 못 센다. 회원 id 는 지금 ObjectId hex 이지만 그것은 **관습이지 계약이
        # 아니다** — 그리고 여기서 틀리면 사용량이 조용히 어긋난다.
        self._store("a.c:writing_generate:proj-1")
        self._store("abc:writing_generate:proj-1")
        # escape 를 빼면 `^a.c:` 가 "abc:" 까지 물어 2가 된다.
        self.assertEqual(self.repo.count_in_flight("a.c", now=AT), 1)
        self.assertEqual(self.repo.count_in_flight("abc", now=AT), 1)

    def test_the_admission_mutex_key_is_not_counted(self):
        # §Q3-a 계약 1: 키 공간이 둘이다.
        self._store("admission:user-1")
        self.assertEqual(self.repo.count_in_flight("user-1", now=AT), 0)


class ServiceOverMongoTest(unittest.TestCase):
    """도메인 계약이 **이 어댑터 위에서도** 성립하는가.

    `test_quota_lock.py` 는 in-memory 저장소로 계약을 잠근다. 두 저장소가 갈라지면
    유닛은 전부 green 인데 배포만 다르게 동작하므로, 계약의 뼈대 넷을 여기서 다시
    구동한다(구간 둘 · 강제 재차지 · fencing).
    """

    def setUp(self):
        self.collection = _Collection()
        self.clock = {"now": AT}
        holders = iter(f"h{n}" for n in range(1, 100))
        self.service = RequestLockService(
            MongoRequestLockRepository(_Client(self.collection)),
            holder_factory=lambda: next(holders),
            clock=lambda: self.clock["now"],
            minimum_window_seconds=5,
            lease_seconds=180,
        )

    def claim(self):
        return self.service.claim(
            user_id="user-1", action="writing_generate", target_project_id="proj-1")

    def force_claim(self):
        return self.service.force_claim(
            user_id="user-1", action="writing_generate", target_project_id="proj-1")

    def release(self, holder):
        return self.service.release(
            user_id="user-1", action="writing_generate", target_project_id="proj-1",
            holder=holder)

    def advance(self, seconds):
        self.clock["now"] = self.clock["now"] + timedelta(seconds=seconds)

    def test_a_request_in_flight_blocks_and_says_so(self):
        self.claim()
        self.advance(10)
        blocked = self.claim()
        self.assertIsInstance(blocked, LockBlocked)
        self.assertTrue(blocked.in_flight)

    def test_the_cooldown_blocks_and_then_lets_go(self):
        granted = self.claim()
        self.advance(1)
        self.release(granted.holder)
        blocked = self.claim()
        self.assertIsInstance(blocked, LockBlocked)
        self.assertFalse(blocked.in_flight)
        self.advance(4)
        self.assertIsInstance(self.claim(), LockGranted)

    def test_a_forced_claim_moves_the_lock_instead_of_clearing_it(self):
        self.claim()
        self.force_claim()
        self.assertIsInstance(self.claim(), LockBlocked)

    def test_the_earlier_request_cannot_release_the_new_owners_lock(self):
        first = self.claim()
        self.advance(5)
        self.force_claim()
        self.advance(18)
        self.assertFalse(self.release(first.holder))
        self.assertIsInstance(self.claim(), LockBlocked)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
