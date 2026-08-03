"""`request_quota_policies` 어댑터 왕복 (Slice 8.1).

**이 파일의 존재 이유 절반은 naive/aware 다.** pymongo 는 BSON 날짜를 tzinfo 없이
돌려주는데, in-memory fake 는 넣은 그대로(aware) 돌려주므로 그 결함을 재현하지
못한다 — 2026-07-27에 같은 형태가 실 Mongo 에서만 `GET /auth/me` 를 전량 500으로
만들었다. 그래서 아래 가짜 collection 은 **드라이버처럼 naive 로 돌려준다**.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from services.application.app.quota.policy import (
    PendingLimits,
    QuotaLimits,
    QuotaPolicy,
    QuotaStatus,
    effective_limits,
)
from services.application.app.quota.policy_mongo import (
    COLLECTION,
    MongoQuotaPolicyRepository,
)


class _Collection:
    """드라이버 흉내 — 저장된 datetime 을 **naive 로** 돌려준다."""

    def __init__(self):
        self.docs = {}
        self.indexes = []

    def create_index(self, keys, **kwargs):  # pragma: no cover - 현재 미사용
        self.indexes.append((keys, kwargs))

    def replace_one(self, query, doc, *, upsert):
        assert upsert
        self.docs[query["_id"]] = _strip_tzinfo(doc)

    def find_one(self, query):
        return self.docs.get(query["_id"])


def _strip_tzinfo(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC).replace(tzinfo=None)
    if isinstance(value, dict):
        return {key: _strip_tzinfo(item) for key, item in value.items()}
    return value


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


NOW = datetime(2026, 8, 3, 5, 0, tzinfo=UTC)
BOUNDARY = datetime(2026, 8, 10, 15, 0, tzinfo=UTC)


def _policy(pending: PendingLimits | None) -> QuotaPolicy:
    return QuotaPolicy(
        user_id="user-1",
        limits=QuotaLimits(daily_limit=20, weekly_limit=100),
        pending=pending,
        updated_at=NOW,
    )


class MongoQuotaPolicyRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.collection = _Collection()
        self.repo = MongoQuotaPolicyRepository(_Client(self.collection))

    def test_round_trip_preserves_every_field(self):
        stored = _policy(PendingLimits(
            limits=QuotaLimits(daily_limit=5, weekly_limit=None,
                               status=QuotaStatus.SUSPENDED),
            effective_at=BOUNDARY,
        ))
        self.repo.upsert(stored)
        self.assertEqual(self.repo.get("user-1"), stored)

    def test_an_unknown_member_has_no_row(self):
        self.assertIsNone(self.repo.get("nobody"))

    def test_the_member_id_is_the_document_id_so_there_is_one_row_each(self):
        # P1 계약("회원당 최대 한 행")을 DB 가 직접 강제한다. 두 번째 쓰기는 새 행이
        # 아니라 덮어쓰기여야 한다.
        self.repo.upsert(_policy(None))
        self.repo.upsert(QuotaPolicy(
            user_id="user-1", limits=QuotaLimits(daily_limit=1, weekly_limit=1),
            pending=None, updated_at=NOW,
        ))
        self.assertEqual(len(self.collection.docs), 1)
        self.assertEqual(self.repo.get("user-1").limits.daily_limit, 1)
        self.assertIn("user-1", self.collection.docs)

    def test_dates_come_back_comparable_to_an_aware_now(self):
        # 이 셀이 없으면 아래 비교가 실 Mongo 에서만 TypeError 로 터진다.
        self.repo.upsert(_policy(PendingLimits(
            limits=QuotaLimits(daily_limit=1, weekly_limit=1),
            effective_at=BOUNDARY,
        )))
        loaded = self.repo.get("user-1")
        self.assertIsNotNone(loaded.pending.effective_at.tzinfo)
        self.assertIsNotNone(loaded.updated_at.tzinfo)
        # 도메인이 실제로 하는 비교를 그대로 해 본다(P6 해석).
        self.assertEqual(
            effective_limits(loaded, BOUNDARY).daily_limit, 1)
        self.assertEqual(
            effective_limits(loaded, NOW).daily_limit, 20)

    def test_the_fake_really_returns_naive_dates(self):
        # 위 셀이 무엇을 지키는지 못박는다. 이 하네스가 aware 를 돌려주도록 바뀌면
        # `_aware` 를 지워도 스위트가 green 이 되어 함정이 되살아난다.
        self.repo.upsert(_policy(None))
        raw = self.collection.docs["user-1"]
        self.assertIsNone(raw["updated_at"].tzinfo)

    def test_unlimited_survives_the_round_trip_as_none(self):
        # over-strict: `None` 을 0 이나 sentinel 로 직렬화하면 무제한이 조용히
        # "0회 허용"이 된다.
        self.repo.upsert(QuotaPolicy(
            user_id="user-1",
            limits=QuotaLimits(daily_limit=None, weekly_limit=None),
            pending=None, updated_at=NOW,
        ))
        loaded = self.repo.get("user-1")
        self.assertIsNone(loaded.limits.daily_limit)
        self.assertIsNone(loaded.limits.weekly_limit)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
