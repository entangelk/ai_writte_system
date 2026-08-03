"""Slice 8.2b — 실 Mongo 위의 잠금 (독립 검증 2026-08-03 H3 보강).

이 기능은 **이름 그대로 DB 잠금**인데 저장소에는 fake 회귀만 있었다. fake 는 내가
믿는 드라이버 의미론을 재현할 뿐이라, 원자성이 실제로 서버에서 성립하는지는 증명하지
못한다 — 독립 검증은 20-way 경쟁을 손으로 돌려 확인했지만 그 실측이 저장소에 남지
않았다. 여기서 남긴다.

**세 가지만 본다**(fake 로는 원리적으로 못 보는 것들):

1. **진짜 동시성** — `Barrier` 로 스레드를 한꺼번에 풀어 같은 키를 친다. 정확히
   하나만 통과하고, **DB 가 그 승자의 토큰을 들고 있어야** 한다(저장 없는 성공 금지).
2. **TTL 인덱스가 서버에 실제로 걸리는가** — 옵션 이름·기준 필드가 틀리면 fake 는
   모르고 지나간다.
3. **만료 재차지가 TTL 삭제와 무관한가** — 문서가 물리적으로 남아 있는 상태에서
   재차지가 되는지(판정이 `expires_at` 비교라는 것).

test-mongo 가 없으면 **skip 한다**(실패가 아니다) — 이 저장소의 다른 실 Mongo 셀과
같은 관례다.
"""

from __future__ import annotations

import os
import threading
import time
import unittest
import uuid
from datetime import UTC, datetime, timedelta

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, PyMongoError

    _PYMONGO_AVAILABLE = True
except ImportError:  # pragma: no cover - 환경에 pymongo 가 없을 때
    MongoClient = None
    ConnectionFailure = PyMongoError = Exception
    _PYMONGO_AVAILABLE = False

from services.application.app.quota.lock import (
    LockGranted,
    RequestLockService,
    lock_key,
)
from services.application.app.quota.lock_mongo import COLLECTION, MongoRequestLockRepository

_MONGO_URI = os.environ.get(
    "CORE_SOT_TEST_MONGO_URI", "mongodb://localhost:27020/?replicaSet=rs-test"
)

USER = "user-1"
ACTION = "writing_generate"
PROJECT = "proj-1"
KEY = lock_key(USER, ACTION, PROJECT)


def _probe_mongo() -> bool:
    if not _PYMONGO_AVAILABLE:
        return False
    for _ in range(5):
        client = None
        probe_db = f"request_lock_probe_{uuid.uuid4().hex}"
        try:
            client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=300)
            client.admin.command("ping")
            client[probe_db]["probe"].insert_one({"probe": True})
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
class RequestLockLiveMongoTest(unittest.TestCase):
    WORKERS = 20

    def setUp(self) -> None:
        self._client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=800)
        self._db_name = f"request_lock_test_{uuid.uuid4().hex}"
        self.db = self._client[self._db_name]
        self.repo = MongoRequestLockRepository(self._client, db_name=self._db_name)

    def tearDown(self) -> None:
        self._client.drop_database(self._db_name)
        self._client.close()

    def _service(self, now: datetime) -> RequestLockService:
        return RequestLockService(
            self.repo, clock=lambda: now,
            minimum_window_seconds=5, lease_seconds=180,
        )

    def test_exactly_one_of_many_simultaneous_requests_wins(self) -> None:
        # ★ 이 슬라이스의 존재 이유를 **서버에서** 확인한다. fake 의 순차 호출로는
        # 원자성을 증명할 수 없다 — 여기서만 보인다.
        now = datetime.now(UTC)
        service = self._service(now)
        barrier = threading.Barrier(self.WORKERS)
        results: list[object] = []
        lock = threading.Lock()

        def attempt() -> None:
            barrier.wait()
            outcome = service.claim(
                user_id=USER, action=ACTION, target_project_id=PROJECT)
            with lock:
                results.append(outcome)

        threads = [threading.Thread(target=attempt) for _ in range(self.WORKERS)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        granted = [r for r in results if isinstance(r, LockGranted)]
        self.assertEqual(len(results), self.WORKERS)
        self.assertEqual(len(granted), 1, "동시 요청 중 정확히 하나만 통과해야 한다")

        # 그리고 **DB 가 그 승자를 들고 있어야** 한다 — 저장되지 않은 성공은 다음
        # 요청까지 통과시키므로 승자 수만 세는 것으로는 부족하다(독립 검증 B1).
        stored = self.db[COLLECTION].find_one({"_id": KEY})
        self.assertIsNotNone(stored)
        self.assertEqual(stored["holder"], granted[0].holder)

    def test_the_ttl_index_really_lands_on_the_server(self) -> None:
        indexes = self.db[COLLECTION].index_information()
        # 잠금을 한 번 만들어야 컬렉션이 생긴다.
        self._service(datetime.now(UTC)).claim(
            user_id=USER, action=ACTION, target_project_id=PROJECT)
        indexes = self.db[COLLECTION].index_information()
        self.assertEqual(set(indexes), {"_id_", "request_locks_ttl"})
        self.assertEqual(indexes["request_locks_ttl"]["key"], [("expires_at", 1)])
        self.assertEqual(indexes["request_locks_ttl"]["expireAfterSeconds"], 0)

    def test_an_expired_lock_is_reclaimed_while_the_document_is_still_present(
        self,
    ) -> None:
        # TTL 모니터는 ~60초 주기라 만료 직후에는 문서가 **아직 있다**. 그 상태에서
        # 재차지가 되어야 판정이 존재가 아니라 `expires_at` 비교라는 것이 성립한다.
        now = datetime.now(UTC)
        first = self._service(now).claim(
            user_id=USER, action=ACTION, target_project_id=PROJECT)
        later = now + timedelta(seconds=181)
        self.assertIsNotNone(self.db[COLLECTION].find_one({"_id": KEY}))
        second = self._service(later).claim(
            user_id=USER, action=ACTION, target_project_id=PROJECT)
        self.assertIsInstance(second, LockGranted)
        self.assertNotEqual(second.holder, first.holder)
        self.assertEqual(
            self.db[COLLECTION].find_one({"_id": KEY})["holder"], second.holder)

    def test_a_previous_holder_cannot_release_the_new_owners_lock(self) -> None:
        # fencing 을 실 드라이버 위에서도 확인한다(갱신 필터의 `holder`).
        now = datetime.now(UTC)
        service = self._service(now)
        first = service.claim(
            user_id=USER, action=ACTION, target_project_id=PROJECT)
        second = service.force_claim(
            user_id=USER, action=ACTION, target_project_id=PROJECT)
        self.assertFalse(service.release(
            user_id=USER, action=ACTION, target_project_id=PROJECT,
            holder=first.holder))
        stored = self.db[COLLECTION].find_one({"_id": KEY})
        self.assertEqual(stored["holder"], second.holder)
        self.assertIsNone(stored["released_at"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
