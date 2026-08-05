"""Slice 8.2c — 파기된 프로젝트의 이름 이력 (N1~N3=A).

**무엇을 잠그는가.** D8-6은 "purge는 이름을 남기지 않는다"였고 오너가 2026-08-05에 그것을
개정했다 — 사용 기록(원장)을 사람이 읽을 수 있어야 하므로 **프로젝트 이름 한 값**이 파기를
살아남는다. 이 파일은 그 저장 계약을 잠근다.

- **N1=A**: 전용 컬렉션 `project_name_history`, `_id`=project id. **`project_id` 필드를 쓰지
  않는다** — 쓰는 순간 파기 reconciler가 이 컬렉션을 고아 sweep 대상으로 발견해 **이 슬라이스의
  목적을 정확히 반대로 실행한다**(`tests/test_purge_reconciler.py`의 실 Mongo 셀이 그 방향을 잰다).
- **N2=A**: 프로젝트 이름 **최신 한 값**. draft 제목도 개명 이력도 아니다.
- **N3=A**: **파기 시점에만** 쓴다. 살아 있는 프로젝트의 이름 정본은 `projects`이고, 복제하면
  두 정본 문제가 생긴다.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from services.application.app.deletion.project_name_history import (
    InMemoryProjectNameHistoryRepository,
    ProjectNameHistoryService,
    ProjectNameSnapshot,
)
from services.application.app.deletion.project_name_history_mongo import (
    MongoProjectNameHistoryRepository,
)


class ProjectNameHistoryServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = InMemoryProjectNameHistoryRepository()
        self.clock = datetime(2026, 8, 5, 12, tzinfo=UTC)
        self.service = ProjectNameHistoryService(self.repo, clock=lambda: self.clock)

    def test_a_purged_project_keeps_exactly_its_name_and_nothing_else(self) -> None:
        self.service.record_purged(project_id="p1", name="첫 장편")

        stored = self.service.get(project_id="p1")
        self.assertEqual(
            stored, ProjectNameSnapshot(project_id="p1", name="첫 장편", purged_at=self.clock)
        )

    def test_an_unpurged_project_has_no_row(self) -> None:
        self.assertIsNone(self.service.get(project_id="never-purged"))

    def test_a_blank_name_is_still_recorded_verbatim(self) -> None:
        """이름은 사용자 텍스트지 검증 대상이 아니다 — 정본이 허용한 것을 그대로 스냅샷한다.

        over-strict 방어: 여기에 정규화나 거부를 넣으면 원장 조회가 정본과 다른 이름을 말한다.
        """
        self.service.record_purged(project_id="p1", name="  여백 있는 제목  ")

        self.assertEqual(self.service.get(project_id="p1").name, "  여백 있는 제목  ")

    def test_a_second_snapshot_of_the_same_id_does_not_multiply_rows(self) -> None:
        """N2=A는 project 하나에 행 하나다(개명 이력이 아니다).

        두 번째 purge는 endpoint에서 404라 여기까지 오지 않지만, 저장 계약 자체가 1:1임을
        잠근다 — 이것이 무너지면 원장 조인이 어느 행을 쓸지 정해야 한다.
        """
        self.service.record_purged(project_id="p1", name="첫 이름")
        self.service.record_purged(project_id="p1", name="둘째 이름")

        self.assertEqual(self.repo.count(), 1)
        self.assertEqual(self.service.get(project_id="p1").name, "둘째 이름")


class MongoProjectNameHistoryRepositoryTest(unittest.TestCase):
    """fake collection 왕복 — 신규 `*_mongo.py`의 표준 요구(선례: gate_findings·loop_audit)."""

    def setUp(self) -> None:
        self.collection = _Collection()
        self.repo = MongoProjectNameHistoryRepository(_Client(self.collection))

    def test_the_round_trip_preserves_every_field(self) -> None:
        snapshot = ProjectNameSnapshot(
            project_id="p1", name="첫 장편", purged_at=datetime(2026, 8, 5, 12, tzinfo=UTC)
        )

        self.repo.put(snapshot)

        self.assertEqual(self.repo.get("p1"), snapshot)

    def test_the_document_key_set_is_fixed_and_has_no_project_id_field(self) -> None:
        """★ 이 셀이 이 슬라이스의 핵심 방어다.

        파기 reconciler는 `find_one({"project_id": {"$exists": True}})` **표본 한 건**으로
        컬렉션을 판정한다. 그래서 문서 **하나**에만 `project_id`가 섞여도 컬렉션 전체가 sweep
        대상이 되고, 이름 이력이 통째로 지워진다. 8.2 원장이 `target_project_id`로 개명하며
        치른 값과 같은 뿌리다 — 여기서는 `_id`를 쓰므로 필드 자체가 생기지 않는다.

        누군가 `project_id`를 더하면 이 셀이 실패한다.
        """
        self.repo.put(
            ProjectNameSnapshot(
                project_id="p1", name="첫 장편",
                purged_at=datetime(2026, 8, 5, 12, tzinfo=UTC),
            )
        )

        doc = self.collection.docs["p1"]
        self.assertEqual(set(doc), {"_id", "name", "purged_at"})
        self.assertNotIn("project_id", doc)

    def test_a_naive_datetime_from_the_driver_comes_back_aware(self) -> None:
        """pymongo는 BSON 날짜를 naive로 돌려준다(HANDOFF 함정). 경계에서 UTC를 재부착한다."""
        self.collection.docs["p1"] = {
            "_id": "p1", "name": "첫 장편",
            "purged_at": datetime(2026, 8, 5, 12),  # tzinfo 없음 = 드라이버가 주는 모양
        }

        self.assertEqual(self.repo.get("p1").purged_at, datetime(2026, 8, 5, 12, tzinfo=UTC))

    def test_an_unknown_project_reads_as_none(self) -> None:
        self.assertIsNone(self.repo.get("never-purged"))


class _Collection:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}
        self.indexes: list[tuple] = []

    def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))

    def replace_one(self, query, doc, *, upsert):
        assert upsert
        self.docs[query["_id"]] = dict(doc)

    def find_one(self, query):
        return self.docs.get(query["_id"])


class _Database:
    def __init__(self, collection) -> None:
        self.collection = collection

    def __getitem__(self, name):
        assert name == "project_name_history"
        return self.collection


class _Client:
    def __init__(self, collection) -> None:
        self.database = _Database(collection)

    def __getitem__(self, _name):
        return self.database


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
