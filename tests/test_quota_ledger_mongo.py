"""`request_usage_ledger` 어댑터 (Slice 8.2).

두 가지가 이 파일의 존재 이유다.

1. **유니크 인덱스가 부분(partial) 인덱스여야 한다.** 조정 행에는 ``action``·
   ``dedupe_key`` 가 없고 Mongo 는 없는 필드를 ``null`` 로 취급하므로, 전체 인덱스로
   걸면 **두 번째 조정 행이 중복 키로 거부된다.** fake collection 이 그 규칙을
   실제로 흉내 내어 이 함정을 재현한다.
2. **naive/aware 왕복** — 8.1과 같은 요구(드라이버처럼 naive 를 돌려준다).
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from services.application.app.quota.ledger import (
    AdjustmentEntry,
    DuplicateUsageEntry,
    UsageEntry,
)
from services.application.app.quota.ledger_mongo import (
    COLLECTION,
    MongoUsageLedgerRepository,
    adjustment_entry,
    usage_entry,
)

AT = datetime(2026, 7, 8, 5, 0, tzinfo=UTC)


class _Collection:
    """드라이버 흉내 — 부분 유니크 인덱스와 naive 날짜를 함께 재현한다."""

    def __init__(self):
        self.docs: dict[str, dict] = {}
        self.indexes: list[tuple] = []

    def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))

    def insert_one(self, doc):
        from pymongo.errors import DuplicateKeyError

        stored = _strip_tzinfo(doc)
        for keys, options in self.indexes:
            if not options.get("unique"):
                continue
            partial = options.get("partialFilterExpression")
            if partial and any(stored.get(k) != v for k, v in partial.items()):
                continue  # 이 인덱스의 대상이 아니다 — 조정 행이 여기로 빠진다
            fields = [name for name, _direction in keys]
            signature = tuple(stored.get(name) for name in fields)
            for other in self.docs.values():
                if partial and any(other.get(k) != v for k, v in partial.items()):
                    continue
                if tuple(other.get(name) for name in fields) == signature:
                    raise DuplicateKeyError(str(signature))
        if stored["_id"] in self.docs:
            raise DuplicateKeyError(stored["_id"])
        self.docs[stored["_id"]] = stored

    def count_documents(self, query):
        return sum(1 for doc in self.docs.values() if _matches(doc, query))

    def find(self, query):
        return [doc for doc in self.docs.values() if _matches(doc, query)]


def _matches(doc, query):
    return all(doc.get(key) == value for key, value in query.items())


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


def _usage(entry_id="e1", *, action="writing_generate", key="k1", user="u1"):
    return UsageEntry(
        id=entry_id, user_id=user, target_project_id="p1", action=action,
        dedupe_key=key, daily_key="2026-07-08", weekly_key="2026-07-06", at=AT,
    )


def _adjustment(entry_id, delta=-1):
    return AdjustmentEntry(
        id=entry_id, user_id="u1", target_project_id="p1", delta=delta,
        reason="오류 보상", admin_user_id="admin-1",
        daily_key="2026-07-08", weekly_key="2026-07-06", at=AT,
    )


class MongoUsageLedgerRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.collection = _Collection()
        self.repo = MongoUsageLedgerRepository(_Client(self.collection))

    def test_it_installs_the_dedupe_and_aggregation_indexes(self):
        names = {options["name"] for _keys, options in self.collection.indexes}
        self.assertEqual(names, {
            "request_usage_ledger_dedupe_unique",
            "request_usage_ledger_by_user_day",
            "request_usage_ledger_by_user_week",
        })

    def test_the_dedupe_index_is_unique_and_scoped_to_usage_rows(self):
        # 부분 인덱스가 아니면 조정 행이 중복 키로 막힌다(아래 셀이 그것을 실증).
        keys, options = next(
            (k, o) for k, o in self.collection.indexes
            if o["name"] == "request_usage_ledger_dedupe_unique")
        self.assertTrue(options["unique"])
        self.assertEqual(options["partialFilterExpression"], {"kind": "usage"})
        self.assertEqual([name for name, _ in keys],
                         ["user_id", "action", "dedupe_key"])

    def test_a_repeated_usage_key_is_refused(self):
        self.repo.add_usage(_usage("e1"))
        with self.assertRaises(DuplicateUsageEntry):
            self.repo.add_usage(_usage("e2"))

    def test_the_same_key_under_a_different_action_is_accepted(self):
        self.repo.add_usage(_usage("e1", action="writing_generate", key="same"))
        self.repo.add_usage(_usage("e2", action="writing_gate", key="same"))
        self.assertEqual(len(self.collection.docs), 2)

    def test_many_adjustments_coexist_despite_the_unique_index(self):
        # ★ 부분 인덱스가 아니면 여기서 DuplicateKeyError 가 난다 — 조정 행은
        # action/dedupe_key 가 없어 전부 (user, null, null) 로 보이기 때문이다.
        self.repo.add_adjustment(_adjustment("a1"))
        self.repo.add_adjustment(_adjustment("a2", delta=-2))
        self.repo.add_adjustment(_adjustment("a3", delta=+3))
        self.assertEqual(len(self.collection.docs), 3)

    def test_counting_separates_usage_from_adjustments(self):
        self.repo.add_usage(_usage("e1"))
        self.repo.add_usage(_usage("e2", key="k2"))
        self.repo.add_adjustment(_adjustment("a1", delta=-1))
        self.assertEqual(self.repo.count_usage(
            "u1", window_field="daily_key", window_key="2026-07-08"), 2)
        self.assertEqual(self.repo.sum_adjustments(
            "u1", window_field="daily_key", window_key="2026-07-08"), -1)

    def test_another_member_is_not_counted(self):
        self.repo.add_usage(_usage("e1", user="u1"))
        self.repo.add_usage(_usage("e2", user="u2"))
        self.assertEqual(self.repo.count_usage(
            "u1", window_field="daily_key", window_key="2026-07-08"), 1)

    def test_the_project_axis_is_stored_as_target_project_id(self):
        # ★ 이름이 계약이다 — `project_id` 면 purge reconciler 가 지운다.
        # **두 종류를 모두 본다**: 조정 행 하나만 `project_id` 를 들어도 컬렉션 전체가
        # sweep 대상이 된다(아래 셀 참조).
        self.repo.add_usage(_usage("e1"))
        self.repo.add_adjustment(_adjustment("a1"))
        for doc_id in ("e1", "a1"):
            with self.subTest(doc=doc_id):
                doc = self.collection.docs[doc_id]
                self.assertIn("target_project_id", doc)
                self.assertNotIn("project_id", doc)

    def test_the_stored_key_sets_are_pinned_so_no_field_creeps_in(self):
        # H2 보강(독립 검증 2026-08-03): 파기 reconciler 의 컬렉션 발견은
        # `find_one({project_id: {$exists: true}})` 라 **표본 한 건**이다. 원장 문서
        # **단 하나**에라도 `project_id` 가 섞이면 컬렉션 전체가 sweep 대상이 되어
        # 과금 기록이 지워진다. 이름 부재만 보는 것으로는 "다른 새 필드"를 못 잡으므로
        # **키 집합 자체를 못박는다** — 필드를 더하려면 이 셀을 함께 고쳐야 한다.
        self.repo.add_usage(_usage("e1"))
        self.repo.add_adjustment(_adjustment("a1"))
        self.assertEqual(set(self.collection.docs["e1"]), {
            "_id", "kind", "user_id", "target_project_id", "action",
            "dedupe_key", "daily_key", "weekly_key", "at",
        })
        self.assertEqual(set(self.collection.docs["a1"]), {
            "_id", "kind", "user_id", "target_project_id", "delta", "reason",
            "admin_user_id", "daily_key", "weekly_key", "at",
        })

    def test_dates_come_back_aware(self):
        self.repo.add_usage(_usage("e1"))
        self.repo.add_adjustment(_adjustment("a1"))
        self.assertIsNotNone(usage_entry(self.collection.docs["e1"]).at.tzinfo)
        self.assertIsNotNone(adjustment_entry(self.collection.docs["a1"]).at.tzinfo)

    def test_the_fake_really_returns_naive_dates(self):
        # 위 셀이 무엇을 지키는지 못박는다(8.1과 같은 가드의 가드).
        self.repo.add_usage(_usage("e1"))
        self.assertIsNone(self.collection.docs["e1"]["at"].tzinfo)

    def test_round_trip_preserves_both_kinds(self):
        self.repo.add_usage(_usage("e1"))
        self.repo.add_adjustment(_adjustment("a1", delta=-2))
        self.assertEqual(usage_entry(self.collection.docs["e1"]), _usage("e1"))
        self.assertEqual(
            adjustment_entry(self.collection.docs["a1"]), _adjustment("a1", delta=-2))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
