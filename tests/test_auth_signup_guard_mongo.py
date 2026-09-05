"""Mongo signup 시도 저장소 — fake collection 회귀(라이브 Mongo 없음).

독립 검증 B4 폐쇄(2026-09-05, `verifications/2026-09-05/phase_s3_signup_throttle.md`).
이 저장소의 다른 Mongo 저장소(sessions·users 등)는 전용 테스트 파일을 두는데 이것만
없었다 — TTL 인덱스가 SoT v1.8.30 등재 literal 인데 리팩터링으로 ``create_index``
가 사라져도 무엇도 안 물었다. 여기 잠그는 축 셋:

① TTL 인덱스 — ``expireAfterSeconds = max(86400, 창×24)``. 인덱스는 **청소부**이지
   정책이 아니다(만료 판단은 서비스가 쥔다) — 정확히 창에 맞추면 창을 늘린 배포에서
   인덱스가 서비스보다 먼저 행을 지워 카운터가 조용히 리셋된다.
② 축 — 행 하나가 발신 IP 하나다(``_id`` = 해석된 주소).
③ naive BSON 재라벨링(``_aware``) — pymongo 는 tz_aware 미지정 클라이언트에서
   BSON 날짜를 naive 로 돌려주고, 서비스는 aware now() 완 비교한다. 섞이면 TypeError
   가 하필 **창 판정 자리**에서 터진다(sessions 의 2026-07-27 실결함과 같은 모양).
"""

import unittest
from datetime import UTC, datetime, timedelta

from services.application.app.auth.signup_guard import (
    AttemptRecord,
    SignupThrottle,
)
from services.application.app.auth.signup_guard_mongo import (
    MongoAttemptRecordRepository,
)

_T0 = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


class _Collection:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}
        self.indexes: list[tuple] = []

    def create_index(self, keys, *, name=None, **kwargs):
        self.indexes.append((keys, name, kwargs))

    def find_one(self, query):
        return self.docs.get(query["_id"])

    def update_one(self, query, update, upsert=False):
        doc = self.docs.get(query["_id"])
        if doc is None:
            if not upsert:
                return
            doc = {"_id": query["_id"]}
            self.docs[query["_id"]] = doc
        doc.update(update["$set"])


class _Database:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == "signup_attempts"
        return self.collection


class _Client:
    def __init__(self, collection):
        self.database = _Database(collection)

    def __getitem__(self, _name):
        return self.database


def _repo(collection, *, window_seconds: int = 60) -> MongoAttemptRecordRepository:
    return MongoAttemptRecordRepository(
        _Client(collection), window_seconds=window_seconds
    )


class MongoAttemptRecordRepositoryTest(unittest.TestCase):
    def test_declares_the_ttl_index_at_window_x24_with_a_one_day_floor(self) -> None:
        """① TTL literal — 창×24, 최소 1일. 경계 네 점이 공식 전체를 핀한다.

        under-strict: ``create_index`` 를 없애면 인덱스 목록이 비어 실패한다. 바닥을
        걷어내면(``max`` 없이 창×24) 60s 창에서 1440초 — 인덱스가 서비스보다 먼저
        행을 지우는 것이 그대로 잡힌다.
        over-strict: 창에 딱 맞추면(3600→3600) 60s·3600s 점이, 곱을 늘리면(24→48)
        7200s 점이 실패한다.
        """
        # 3600/3601 묶음이 max() 의 교차점을 정확히 친다: 창×24 가 하루와 같아지는
        # 자리와 그 한 초 뒤.
        for window_seconds, expected in [
            (60, 86400), (3600, 86400), (3601, 86424), (7200, 172800),
        ]:
            with self.subTest(window_seconds=window_seconds):
                collection = _Collection()
                _repo(collection, window_seconds=window_seconds)
                self.assertEqual(
                    collection.indexes,
                    [("window_started_at", None,
                      {"expireAfterSeconds": expected})],
                )

    def test_the_row_key_is_the_client_ip(self) -> None:
        """② 축 literal — ``_id`` 는 해석된 발신 주소, 행 하나가 IP 하나다."""
        collection = _Collection()
        repo = _repo(collection)
        repo.put("203.0.113.9", AttemptRecord(attempts=3, window_started_at=_T0))
        self.assertEqual(list(collection.docs), ["203.0.113.9"])
        self.assertEqual(
            repo.get("203.0.113.9"),
            AttemptRecord(attempts=3, window_started_at=_T0),
        )

    def test_get_missing_returns_none(self) -> None:
        self.assertIsNone(_repo(_Collection()).get("198.51.100.7"))


class NaiveBsonDatetimeTest(unittest.TestCase):
    """③ 재라벨링 — fake 는 aware 를 그대로 돌려주므로 naive 로 되돌려 재현한다."""

    def setUp(self) -> None:
        self.collection = _Collection()
        self.repo = _repo(self.collection)
        self.repo.put("203.0.113.9", AttemptRecord(attempts=1, window_started_at=_T0))
        for doc in self.collection.docs.values():
            doc["window_started_at"] = doc["window_started_at"].replace(tzinfo=None)

    def test_read_back_window_started_at_is_utc_aware(self) -> None:
        # under-strict: 재라벨링을 지우면 실패한다.
        record = self.repo.get("203.0.113.9")
        self.assertIsNotNone(record.window_started_at.tzinfo)

    def test_normalization_does_not_shift_the_instant(self) -> None:
        # over-strict: BSON 은 이미 UTC 다 — tz 변환을 하면 이 instant 가 움직인다.
        self.assertEqual(self.repo.get("203.0.113.9").window_started_at, _T0)

    def test_already_aware_dates_pass_through_unchanged(self) -> None:
        # over-strict 반대 방향: aware 값(인메모리 경로)을 덮어쓰지 않는다.
        self.repo.put("198.51.100.7",
                      AttemptRecord(attempts=2, window_started_at=_T0))
        self.assertEqual(
            self.repo.get("198.51.100.7").window_started_at, _T0
        )

    def test_the_service_judges_windows_against_naive_stored_dates(self) -> None:
        # 실제 실패 경로 end-to-end: 창이 찬 행을 naive 로 돌려주고 consume 하면,
        # 재라벨링이 없으면 창 판정 자리에서 TypeError 가 난다.
        throttle = SignupThrottle(
            self.repo,
            max_requests=1,
            window=timedelta(seconds=60),
            clock=lambda: _T0 + timedelta(seconds=1),
        )
        self.assertIsNotNone(throttle.consume("203.0.113.9"))


if __name__ == "__main__":
    unittest.main()
