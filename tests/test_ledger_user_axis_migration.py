"""원장 소유 축 개명 마이그레이션 (D4, 오너 2026-09-07).

**이 마이그레이션이 지키는 것**: 사용량 원장은 계정 탈퇴 파기를 **살아남아야 한다**
(오너 결정). 그런데 이 저장소에서 파기 대상의 표식은 **필드 이름**이라
(``purge_reconciler`` 가 ``find_one({field: {"$exists": True}})`` **표본 한 건**으로
컬렉션을 고른다) 원장이 ``user_id`` 를 들고 있으면 사용자 축 reconciler 가 생기는 날
통째로 쓸려 간다. 프로젝트 축이 ``target_project_id`` 인 것과 같은 뿌리다(8.2 L1=B).

**★ 인덱스 제거는 문서 개명과 독립이어야 한다**(독립 검증 H1, 2026-09-07). 종전 구현은
``pending == 0`` 이면 조기 반환했는데, 문서 개명과 인덱스 제거 **사이에 프로세스가 죽으면**
재실행이 그 조기 반환에 걸려 **옛 인덱스를 영원히 안 지운다.** 그 상태로 앱을 기동하면
어댑터의 같은-이름-다른-키 ``create_index`` 를 MongoDB 가 **code=86 으로 거부**해 기동이
깨진다(검증자 실측). 그래서 지울 대상은 게이트가 아니라 **실제 인덱스 키**로 고른다.

**양방향**:
- under-strict — 개명을 안 하면(문서에 ``user_id`` 가 남으면) 1·2번이 실패한다.
- under-strict — 옛 인덱스를 안 지우면 3번이 실패한다.
- under-strict — 크래시 창(문서는 옮겼는데 인덱스가 남은 상태)에서 재실행이 인덱스를
  안 지우면 5번이 실패한다.
- over-strict — 옛 필드를 **안 쓰는** 인덱스(``_id_``, 어댑터가 새 키로 만든 것)까지
  지우면 6번이 실패한다.
- over-strict — 이미 옮긴 문서를 또 건드리거나 **인덱스를 또 지우면** 4번이 실패한다.
"""

from __future__ import annotations

import unittest

from scripts.migrate_ledger_user_axis import migrate

#: 어댑터가 실제로 만드는 인덱스(개명 전 키). `list_indexes()` 모양 그대로.
_OLD_INDEXES = [
    {"name": "_id_", "key": {"_id": 1}},
    {"name": "request_usage_ledger_dedupe_unique",
     "key": {"user_id": 1, "action": 1, "dedupe_key": 1}},
    {"name": "request_usage_ledger_by_user_day", "key": {"user_id": 1, "daily_key": 1}},
    {"name": "request_usage_ledger_by_user_week", "key": {"user_id": 1, "weekly_key": 1}},
]

#: 어댑터가 개명 뒤 다시 만든 모양(같은 이름, 새 키).
_NEW_INDEXES = [
    {"name": "_id_", "key": {"_id": 1}},
    {"name": "request_usage_ledger_dedupe_unique",
     "key": {"target_user_id": 1, "action": 1, "dedupe_key": 1}},
    {"name": "request_usage_ledger_by_user_day",
     "key": {"target_user_id": 1, "daily_key": 1}},
    {"name": "request_usage_ledger_by_user_week",
     "key": {"target_user_id": 1, "weekly_key": 1}},
]


class _Collection:
    """``$rename``·``drop_index``·``list_indexes`` 를 흉내 내는 최소 드라이버."""

    def __init__(self, docs: list[dict], indexes: list[dict] | None = None):
        self.docs = docs
        self.indexes = [dict(one) for one in (_OLD_INDEXES if indexes is None else indexes)]

    def list_indexes(self):
        return list(self.indexes)

    @property
    def index_names(self) -> list[str]:
        return [one["name"] for one in self.indexes]

    def _matching(self, query: dict) -> list[dict]:
        (field, condition), = query.items()
        assert condition == {"$exists": True}, condition
        return [doc for doc in self.docs if field in doc]

    def count_documents(self, query: dict) -> int:
        return len(self._matching(query))

    def update_many(self, query: dict, update: dict):
        (old, new), = update["$rename"].items()
        touched = self._matching(query)
        for doc in touched:
            doc[new] = doc.pop(old)

        class _Result:
            modified_count = len(touched)

        return _Result()

    def drop_index(self, name: str) -> None:
        for index in self.indexes:
            if index["name"] == name:
                self.indexes.remove(index)
                return
        raise KeyError(name)


class LedgerUserAxisMigrationTest(unittest.TestCase):
    def test_it_moves_the_owning_axis_to_target_user_id(self):
        collection = _Collection([
            {"_id": "e1", "user_id": "u1", "target_project_id": "p1"},
            {"_id": "a1", "user_id": "u2", "admin_user_id": "admin-1"},
        ])

        report = migrate(collection)

        self.assertEqual(report["renamed"], 2)
        for doc in collection.docs:
            self.assertNotIn("user_id", doc)
        self.assertEqual(collection.docs[0]["target_user_id"], "u1")
        self.assertEqual(collection.docs[1]["target_user_id"], "u2")

    def test_the_actor_field_is_left_alone(self):
        # ``admin_user_id`` 는 **행위자**이지 원장의 소유 축이 아니다. 이름이 달라
        # 정확 일치 판정에 걸리지 않으므로 개명 대상이 아니다.
        collection = _Collection([{"_id": "a1", "user_id": "u1", "admin_user_id": "admin-1"}])

        migrate(collection)

        self.assertEqual(collection.docs[0]["admin_user_id"], "admin-1")

    def test_it_drops_the_indexes_that_were_keyed_on_the_old_field(self):
        # 같은 이름으로 **키가 다른** 인덱스를 만들 수 없다(MongoDB code=86, 검증자
        # 실측). 지우지 않으면 어댑터 기동이 깨지므로 마이그레이션이 지우고, 새
        # 인덱스는 어댑터가 만든다.
        collection = _Collection([{"_id": "e1", "user_id": "u1"}])

        report = migrate(collection)

        self.assertEqual(sorted(report["dropped_indexes"]), sorted([
            "request_usage_ledger_by_user_day",
            "request_usage_ledger_by_user_week",
            "request_usage_ledger_dedupe_unique",
        ]))
        # `_id_` 는 옛 필드를 안 쓰므로 살아남는다.
        self.assertEqual(collection.index_names, ["_id_"])

    def test_a_crash_between_the_rename_and_the_index_drop_is_recoverable(self):
        """★ 독립 검증 H1 — 부분 실패 창을 닫는다.

        문서 개명과 인덱스 제거 **사이에** 프로세스가 죽은 상태를 그대로 만든다:
        문서는 이미 `target_user_id` 인데 인덱스는 옛 키다. 재실행이 *"옮길 문서가
        없다"* 로 조기 반환하면 옛 인덱스가 **영원히** 남고, 그 상태의 어댑터 기동은
        같은-이름-다른-키 `create_index` 라 **code=86** 으로 깨진다.
        """
        collection = _Collection([{"_id": "e1", "target_user_id": "u1"}])

        report = migrate(collection)

        self.assertEqual(report["documents_with_old_field"], 0)
        self.assertEqual(report["renamed"], 0)
        self.assertEqual(len(report["dropped_indexes"]), 3)
        self.assertEqual(collection.index_names, ["_id_"])

    def test_it_leaves_indexes_that_do_not_use_the_old_field(self):
        # over-strict 방향: 어댑터가 **새 키로 다시 만든** 인덱스를 지우면 안 된다.
        # 이름은 같으므로 이름으로 지우면 여기서 걸린다.
        collection = _Collection([{"_id": "e1", "target_user_id": "u1"}], indexes=_NEW_INDEXES)

        report = migrate(collection)

        self.assertEqual(report["dropped_indexes"], [])
        self.assertEqual(len(collection.indexes), len(_NEW_INDEXES))

    def test_running_it_twice_changes_nothing_the_second_time(self):
        collection = _Collection([{"_id": "e1", "user_id": "u1"}])
        migrate(collection)
        before = [dict(doc) for doc in collection.docs]

        second = migrate(collection)

        self.assertEqual(second["documents_with_old_field"], 0)
        self.assertEqual(second["renamed"], 0)
        # ★ 독립 검증 H2 — 재실행은 인덱스도 **건드리지 않는다**. 이 다리가 없으면
        # 재실행이 drop 을 시도해도(그리고 예외가 삼켜져도) 셀이 통과한다.
        self.assertEqual(second["dropped_indexes"], [])
        self.assertEqual(collection.docs, before)

    def test_a_dry_run_reports_without_touching_anything(self):
        collection = _Collection([{"_id": "e1", "user_id": "u1"}])

        report = migrate(collection, dry_run=True)

        self.assertEqual(report["documents_with_old_field"], 1)
        self.assertEqual(report["renamed"], 0)
        self.assertIn("user_id", collection.docs[0])
        self.assertEqual(collection.index_names, [one["name"] for one in _OLD_INDEXES])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
