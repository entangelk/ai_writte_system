"""원장 소유 축 개명 마이그레이션 (D4, 오너 2026-09-07).

**이 마이그레이션이 지키는 것**: 사용량 원장은 계정 탈퇴 파기를 **살아남아야 한다**
(오너 결정). 그런데 이 저장소에서 파기 대상의 표식은 **필드 이름**이라
(``purge_reconciler`` 가 ``find_one({field: {"$exists": True}})`` **표본 한 건**으로
컬렉션을 고른다) 원장이 ``user_id`` 를 들고 있으면 사용자 축 reconciler 가 생기는 날
통째로 쓸려 간다. 프로젝트 축이 ``target_project_id`` 인 것과 같은 뿌리다(8.2 L1=B).

**양방향**:
- under-strict — 개명을 안 하면(문서에 ``user_id`` 가 남으면) 1·2번이 실패한다.
- under-strict — 옛 인덱스를 안 지우면 3번이 실패한다(같은 이름으로 새 키의 인덱스를
  만들 수 없어 어댑터 기동이 깨진다).
- over-strict — 이미 옮긴 문서를 또 건드리거나 값을 바꾸면 4번이 실패한다(멱등).
"""

from __future__ import annotations

import unittest

from scripts.migrate_ledger_user_axis import _STALE_INDEXES, migrate


class _Collection:
    """``$rename`` 과 ``drop_index`` 만 흉내 내는 최소 드라이버."""

    def __init__(self, docs: list[dict], indexes: list[str] | None = None):
        self.docs = docs
        self.indexes = list(_STALE_INDEXES if indexes is None else indexes)

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
        if name not in self.indexes:
            raise KeyError(name)
        self.indexes.remove(name)


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
        # 같은 이름으로 **키가 다른** 인덱스를 만들 수 없다. 지우지 않으면 어댑터
        # 기동이 깨지므로 마이그레이션이 지우고, 새 인덱스는 어댑터가 만든다.
        collection = _Collection([{"_id": "e1", "user_id": "u1"}])

        report = migrate(collection)

        self.assertEqual(sorted(report["dropped_indexes"]), sorted(_STALE_INDEXES))
        self.assertEqual(collection.indexes, [])

    def test_running_it_twice_changes_nothing_the_second_time(self):
        collection = _Collection([{"_id": "e1", "user_id": "u1"}])
        migrate(collection)
        before = [dict(doc) for doc in collection.docs]

        second = migrate(collection)

        self.assertEqual(second["documents_with_old_field"], 0)
        self.assertEqual(second["renamed"], 0)
        self.assertEqual(collection.docs, before)

    def test_a_dry_run_reports_without_touching_anything(self):
        collection = _Collection([{"_id": "e1", "user_id": "u1"}])

        report = migrate(collection, dry_run=True)

        self.assertEqual(report["documents_with_old_field"], 1)
        self.assertEqual(report["renamed"], 0)
        self.assertIn("user_id", collection.docs[0])
        self.assertEqual(collection.indexes, list(_STALE_INDEXES))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
