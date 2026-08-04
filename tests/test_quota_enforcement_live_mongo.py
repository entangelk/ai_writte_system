"""Slice 8.3 — 입장 직렬화를 **서버에서** 확인한다 (Q3-a=A).

오너 요구는 "ms 를 블로킹해서라도 원자성을 확보하라"였고, 그 답이 회원 단위 입장
뮤텍스다. **fake 로는 그것을 증명할 수 없다** — 단일 스레드 fake 의 순차 호출은
"동시에 둘이 같은 여유를 읽는" 상황을 만들지 못하기 때문이다. 8.2b 가 같은 이유로
20-way 셀을 남겼고, 여기서 재는 것은 그보다 한 겹 위다:

**같은 회원의 동시 요청 N 개가 한도 1칸을 두고 경쟁하면 정확히 하나만 통과한다.**
서로 **다른 action** 으로 경쟁시키는 것이 요점이다 — 8.2b 잠금은 action 이 다르면
서로를 막지 않으므로, 여기서 통과 수가 1을 넘으면 그것은 잠금이 아니라 **입장
뮤텍스가 없는 것**이다(뮤텍스를 지우는 뮤테이션이 정확히 이 셀에서 물린다).

test-mongo 가 없으면 skip 한다(실패가 아니다) — 이 저장소의 관례.
"""

from __future__ import annotations

import os
import threading
import time
import unittest
import uuid
from datetime import UTC, datetime

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, PyMongoError

    _PYMONGO_AVAILABLE = True
except ImportError:  # pragma: no cover
    MongoClient = None
    ConnectionFailure = PyMongoError = Exception
    _PYMONGO_AVAILABLE = False

from services.application.app.quota.enforcement import (
    AdmissionMutex,
    QuotaEnforcementService,
    QuotaRefused,
)
from services.application.app.quota.ledger import UsageLedgerService
from services.application.app.quota.ledger_mongo import MongoUsageLedgerRepository
from services.application.app.quota.lock import RequestLockService
from services.application.app.quota.lock_mongo import MongoRequestLockRepository
from services.application.app.quota.policy import QuotaLimits, QuotaPolicy
from services.application.app.quota.policy_mongo import MongoQuotaPolicyRepository
from services.application.app.quota.policy import QuotaPolicyService

_MONGO_URI = os.environ.get(
    "CORE_SOT_TEST_MONGO_URI", "mongodb://localhost:27020/?replicaSet=rs-test"
)

USER = "user-1"
PROJECT = "proj-1"
JOINED = datetime(2026, 7, 1, tzinfo=UTC)


def _probe_mongo() -> bool:
    if not _PYMONGO_AVAILABLE:
        return False
    for _ in range(5):
        client = None
        probe_db = f"quota_enforcement_probe_{uuid.uuid4().hex}"
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
class AdmissionSerialisationLiveMongoTest(unittest.TestCase):
    WORKERS = 20

    def setUp(self) -> None:
        self._client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=800)
        self._db_name = f"quota_enforcement_test_{uuid.uuid4().hex}"
        self.db = self._client[self._db_name]
        self.locks_repo = MongoRequestLockRepository(
            self._client, db_name=self._db_name)
        self.ledger_repo = MongoUsageLedgerRepository(
            self._client, db_name=self._db_name)
        self.policy_repo = MongoQuotaPolicyRepository(
            self._client, db_name=self._db_name)

    def tearDown(self) -> None:
        self._client.drop_database(self._db_name)
        self._client.close()

    def _service(self, *, daily_limit: int) -> QuotaEnforcementService:
        self.policy_repo.upsert(QuotaPolicy(
            user_id=USER,
            limits=QuotaLimits(daily_limit=daily_limit, weekly_limit=None),
            pending=None,
            updated_at=datetime.now(UTC),
        ))
        return QuotaEnforcementService(
            policy=QuotaPolicyService(self.policy_repo),
            ledger=UsageLedgerService(
                self.ledger_repo, id_factory=lambda: "rul:" + uuid.uuid4().hex),
            locks=RequestLockService(
                self.locks_repo, minimum_window_seconds=5, lease_seconds=180),
            # 실제 경합을 보려면 재시도가 진짜로 기다려야 한다 — 여기서는 기본
            # sleep 을 그대로 쓴다(수 ms).
            mutex=AdmissionMutex(self.locks_repo, attempts=40),
        )

    def test_only_one_of_many_concurrent_requests_takes_the_last_slot(self) -> None:
        # ★ 이 슬라이스의 존재 이유. 한도 1칸에 20개가 동시에 달려들고, 각자
        # **다른 action** 이라 8.2b 잠금은 아무도 막지 않는다 — 그래도 통과는
        # 정확히 하나여야 한다. 뮤텍스를 걷어내면 여러 개가 "아직 여유 있음"을
        # 함께 읽고 전부 통과한다.
        service = self._service(daily_limit=1)
        barrier = threading.Barrier(self.WORKERS)
        admitted: list[object] = []
        refused: list[Exception] = []
        guard = threading.Lock()

        def attempt(index: int) -> None:
            barrier.wait()
            try:
                charge = service.admit(
                    user_id=USER, member_created_at=JOINED,
                    action=f"action-{index}", target_project_id=PROJECT,
                    dedupe_key=f"key-{index}",
                )
            except QuotaRefused as exc:
                with guard:
                    refused.append(exc)
                return
            except Exception as exc:  # noqa: BLE001 — 실패 원인을 보고 싶다
                with guard:
                    refused.append(exc)
                return
            with guard:
                admitted.append(charge)

        threads = [
            threading.Thread(target=attempt, args=(index,))
            for index in range(self.WORKERS)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(admitted) + len(refused), self.WORKERS)
        self.assertEqual(
            len(admitted), 1,
            "한도 1칸에 동시 20건이면 정확히 하나만 입장해야 한다",
        )
        self.assertTrue(
            all(isinstance(exc, QuotaRefused) for exc in refused),
            f"거절 사유가 한도가 아니다: {[type(e).__name__ for e in refused]}",
        )

    def test_the_admission_mutex_does_not_count_itself_as_in_flight(self) -> None:
        # §Q3-a 계약 1: 키 공간이 둘이다. 접두가 겹치면 뮤텍스 문서가 진행 중
        # 요청으로 세어져 회원이 한 칸을 상시로 잃는다(무제한 한도에서도 보인다).
        service = self._service(daily_limit=None)
        mutex = AdmissionMutex(self.locks_repo)
        with mutex.hold(USER):
            self.assertEqual(
                service.effective_usage(user_id=USER, member_created_at=JOINED),
                (0, 0),
            )

    def test_in_flight_locks_are_counted_by_prefix_on_the_server(self) -> None:
        # 진행 중 계수는 ``_id`` 앵커 정규식이다(8.2b 의 "추가 인덱스 없음"을
        # 지키려고). 그 쿼리가 서버에서 실제로 맞는지 여기서만 확인된다.
        service = self._service(daily_limit=None)
        service.admit(
            user_id=USER, member_created_at=JOINED, action="writing_gate",
            target_project_id=PROJECT, dedupe_key="a")
        service.admit(
            user_id="other-user", member_created_at=JOINED, action="writing_gate",
            target_project_id=PROJECT, dedupe_key="b")
        self.assertEqual(
            service.effective_usage(user_id=USER, member_created_at=JOINED),
            (1, 1),
            "남의 잠금까지 세면 접두 조회가 회원 경계를 못 지키는 것이다",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
