"""Phase 9 Slice 9.0 — 활동 로그 저장 계약 (A3=B · A4=A · A6=A · I1).

**무엇을 잠그는가.**

- **A3=B 문서 형태**: 고정 코어 + 짧은 값 변화. **키 집합 자체를 고정**한다 — 파기
  reconciler 가 `find_one` **표본 한 건**으로 컬렉션을 판정하므로, 새 필드를 더하는
  일은 계약 변경이다(8.2 원장이 같은 이유로 같은 셀을 갖는다).
- **★ I1 `project_id` 필드명**: 8.2c `project_name_history` 와 **정반대**다. 그쪽은
  `_id` 를 써서 reconciler 를 피하고, 여기는 **일부러 발견되어야** 한다 — 활동 로그는
  프로젝트 자식이고 파기와 함께 사라져야 하기 때문이다(I2, D8-6).
- **A4=A 격리**: 기록 실패가 요청을 죽이지 않는다. 그리고 그 격리가 **파기 경로까지
  번지지 않는다**(파기 실패는 삼키면 안 된다) — 양방향.
- **A6=A**: TTL 인덱스 없음.
"""

from __future__ import annotations

import os
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from unittest import mock

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, PyMongoError

    _PYMONGO_AVAILABLE = True
except ImportError:  # pragma: no cover
    MongoClient = None
    ConnectionFailure = PyMongoError = Exception
    _PYMONGO_AVAILABLE = False

from services.application.app.activity.log import (
    ACTIVITY_VALUE_MAX_CHARS,
    ActivityEvent,
    ActivityLogService,
    InMemoryActivityLogRepository,
)
from services.application.app.activity.log_mongo import MongoActivityLogRepository
from services.application.app.main import _default_activity_log_service

_MONGO_URI = os.environ.get(
    "CORE_SOT_TEST_MONGO_URI", "mongodb://localhost:27020/?replicaSet=rs-test"
)


def _probe_mongo() -> bool:
    if not _PYMONGO_AVAILABLE:
        return False
    client = None
    probe_db = f"activity_probe_{uuid.uuid4().hex}"
    try:
        client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=300)
        client.admin.command("ping")
        client[probe_db]["probe"].insert_one({"probe": True})
        return True
    except (ConnectionFailure, PyMongoError):
        return False
    finally:
        if client is not None:
            try:
                client.drop_database(probe_db)
            except PyMongoError:
                pass
            client.close()


_MONGO_AVAILABLE = _probe_mongo()

_AT = datetime(2026, 8, 9, 12, tzinfo=UTC)


class ActivityLogServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = InMemoryActivityLogRepository()
        self.service = ActivityLogService(
            self.repo, clock=lambda: _AT, id_factory=lambda: "e1"
        )

    def test_a_recorded_event_carries_actor_target_and_time(self) -> None:
        self.service.record(
            project_id="p1", actor_user_id="u1", action="project_renamed",
            target_type="project", target_id="p1",
            before="옛 이름", after="새 이름",
        )

        self.assertEqual(
            self.repo.events,
            [ActivityEvent(
                id="e1", project_id="p1", actor_user_id="u1",
                action="project_renamed", target_type="project", target_id="p1",
                at=_AT, before="옛 이름", after="새 이름",
            )],
        )

    def test_a_value_change_is_optional(self) -> None:
        """A3=B — before/after 는 값 변화가 있는 행만 채운다(생성·저장에는 없다)."""
        self.service.record(
            project_id="p1", actor_user_id="u1", action="draft_created",
            target_type="draft", target_id="d1",
        )

        self.assertIsNone(self.repo.events[0].before)
        self.assertIsNone(self.repo.events[0].after)

    def test_a_long_value_is_cut_to_the_short_value_cap(self) -> None:
        """★ A3=B 의 "짧은 값"은 계약이다 — 다음 사람이 본문을 넣지 못하게 막는다.

        이름·제목에는 길이 제한이 없으므로(실측: `NonBlankName` 은 `min_length=1` 뿐)
        상한이 없으면 본문 길이의 문자열이 그대로 들어온다. D(본문 diff)를 기각한
        이유가 그 순간 무의미해진다.
        """
        self.service.record(
            project_id="p1", actor_user_id="u1", action="project_renamed",
            target_type="project", target_id="p1",
            before="가" * 5000, after="나" * 5000,
        )

        stored = self.repo.events[0]
        self.assertEqual(len(stored.before), ACTIVITY_VALUE_MAX_CHARS)
        self.assertEqual(len(stored.after), ACTIVITY_VALUE_MAX_CHARS)

    def test_a_normal_value_is_stored_verbatim(self) -> None:
        """over-strict 방향 — 상한을 지키려다 정상 라벨을 자르면 실패한다."""
        self.service.record(
            project_id="p1", actor_user_id="u1", action="draft_renamed",
            target_type="draft", target_id="d1", before="1장", after="1장 — 재고",
        )

        self.assertEqual(self.repo.events[0].after, "1장 — 재고")

    def test_a_write_failure_does_not_reach_the_caller(self) -> None:
        """★ A4=A — 로그 저장소가 죽어도 사용자의 저장은 성공한다.

        판정 기준은 코드가 이미 문장으로 갖고 있다: `access_grant_uses` 가
        fail-closed 인 것은 그 기록이 없으면 관리자 열람을 아무도 설명할 수 없어서다.
        활동 로그가 없다고 잘못 열리는 문은 없다.
        """
        service = ActivityLogService(_ExplodingRepository())

        service.record(
            project_id="p1", actor_user_id="u1", action="draft_created",
            target_type="draft", target_id="d1",
        )  # 예외가 올라오면 이 셀이 실패한다

    def test_a_purge_failure_is_not_swallowed(self) -> None:
        """★ 격리는 기록에만 걸린다 — 파기까지 삼키면 D5 부분 삭제가 조용히 성공한다.

        purge handler 는 예외를 받아 감사 `failed` 를 남기고 503 을 낸다. 여기서
        삼키면 "지워지지 않은 로그가 남은 채 파기 성공"이 된다.
        """
        service = ActivityLogService(_ExplodingRepository())

        with self.assertRaises(RuntimeError):
            service.purge_project(project_id="p1")

    def test_reading_is_scoped_to_one_project_and_newest_first(self) -> None:
        repo = InMemoryActivityLogRepository()
        service = ActivityLogService(repo)
        for index, (project_id, at) in enumerate(
            [("p1", _AT), ("p2", _AT), ("p1", _AT + timedelta(hours=1))]
        ):
            repo.insert(ActivityEvent(
                id=f"e{index}", project_id=project_id, actor_user_id="u1",
                action="draft_created", target_type="draft", target_id="d1", at=at,
            ))

        rows = service.list_for_project(project_id="p1")

        self.assertEqual([row.id for row in rows], ["e2", "e0"])

    def test_reading_honours_the_limit(self) -> None:
        repo = InMemoryActivityLogRepository()
        for index in range(5):
            repo.insert(ActivityEvent(
                id=f"e{index}", project_id="p1", actor_user_id="u1",
                action="draft_created", target_type="draft", target_id="d1",
                at=_AT + timedelta(minutes=index),
            ))

        rows = ActivityLogService(repo).list_for_project(project_id="p1", limit=2)

        self.assertEqual([row.id for row in rows], ["e4", "e3"])

    def _seed(self, rows):
        """(id, project_id, at) 을 그대로 넣는다 — `record()` 는 setUp 의 고정 시계라
        같은 `at` 이 되어 정렬을 잴 수 없다(기존 정렬 셀과 같은 관용구)."""
        repo = InMemoryActivityLogRepository()
        for event_id, project_id, at in rows:
            repo.insert(ActivityEvent(
                id=event_id, project_id=project_id, actor_user_id="u1",
                action="draft_created", target_type="draft", target_id="d1", at=at,
            ))
        return ActivityLogService(repo)

    def test_reading_many_projects_merges_them_newest_first(self) -> None:
        """9.2 P1=ⓐ — 통합 조회는 **여러 project 를 한 줄로** 접는다."""
        service = self._seed([
            ("e0", "p1", _AT),
            ("e1", "p2", _AT + timedelta(hours=2)),
            ("e2", "p1", _AT + timedelta(hours=1)),
        ])

        rows = service.list_for_projects(project_ids=("p1", "p2"))

        self.assertEqual([row.id for row in rows], ["e1", "e2", "e0"])

    def test_reading_many_projects_excludes_the_ones_not_named(self) -> None:
        """★ 소유 기준(P8)의 경계는 **호출자가 준 집합**이다."""
        service = self._seed([
            ("mine", "p1", _AT),
            ("theirs", "p9", _AT + timedelta(hours=1)),
        ])

        rows = service.list_for_projects(project_ids=("p1",))

        self.assertEqual([row.id for row in rows], ["mine"])

    def test_reading_no_projects_returns_nothing(self) -> None:
        """프로젝트가 없는 회원 — 빈 집합은 "전부"가 아니라 "없음"이다.

        뒤집히면 **남의 활동이 전부 보이는** 형태가 되므로 저장소에 묻지도 않는다.
        """
        service = self._seed([("e0", "p1", _AT)])

        self.assertEqual(service.list_for_projects(project_ids=()), ())

    def test_the_merged_read_honours_the_ceiling(self) -> None:
        """P2 — 통합 상한 기본값은 per-project 와 **같은 수**다(역전 방지)."""
        service = self._seed([
            (f"e{i}", f"p{i}", _AT + timedelta(hours=i)) for i in range(5)
        ])

        rows = service.list_for_projects(
            project_ids=tuple(f"p{i}" for i in range(5)), limit=2)

        self.assertEqual([row.id for row in rows], ["e4", "e3"])

    def test_purge_removes_only_the_named_project(self) -> None:
        repo = InMemoryActivityLogRepository()
        for project_id in ("p1", "p2"):
            repo.insert(ActivityEvent(
                id=f"e-{project_id}", project_id=project_id, actor_user_id="u1",
                action="draft_created", target_type="draft", target_id="d1", at=_AT,
            ))

        ActivityLogService(repo).purge_project(project_id="p1")

        self.assertEqual([event.project_id for event in repo.events], ["p2"])


class MongoActivityLogRepositoryTest(unittest.TestCase):
    """fake collection 왕복 — 신규 `*_mongo.py` 의 표준 요구."""

    def setUp(self) -> None:
        self.collection = _Collection()
        self.repo = MongoActivityLogRepository(_Client(self.collection))

    def _event(self, **overrides) -> ActivityEvent:
        fields = dict(
            id="e1", project_id="p1", actor_user_id="u1",
            action="project_renamed", target_type="project", target_id="p1",
            at=_AT, before="옛 이름", after="새 이름",
        )
        fields.update(overrides)
        return ActivityEvent(**fields)

    def test_the_round_trip_preserves_every_field(self) -> None:
        event = self._event()

        self.repo.insert(event)

        self.assertEqual(
            self.repo.list_for_project(project_id="p1", limit=10), (event,)
        )

    def test_the_document_key_set_is_fixed(self) -> None:
        """새 필드는 계약 변경이다 — reconciler 가 표본 한 건으로 판정하기 때문이다."""
        self.repo.insert(self._event())

        self.assertEqual(
            set(self.collection.docs[0]),
            {"_id", "project_id", "actor_user_id", "action", "target_type",
             "target_id", "at", "before", "after"},
        )

    def test_the_document_carries_project_id_so_the_reconciler_finds_it(self) -> None:
        """★ I1 — 8.2c 와 정반대 방향이고 그것이 의도다.

        `project_name_history` 는 `_id` 를 project id 로 써서 reconciler 의 고아 sweep 을
        **구조적으로 피한다**. 활동 로그는 프로젝트 자식이라 **발견되어야** 한다 —
        여기서 그 흉내를 내면 파기가 못 지우는 행이 생기고 D8-6 이 무너진다(I2).
        """
        self.repo.insert(self._event())

        self.assertEqual(self.collection.docs[0]["project_id"], "p1")

    def test_a_naive_datetime_from_the_driver_comes_back_aware(self) -> None:
        """pymongo 는 BSON 날짜를 naive 로 준다(HANDOFF 함정). fake 로는 안 보인다."""
        self.collection.docs.append({
            "_id": "e1", "project_id": "p1", "actor_user_id": "u1",
            "action": "draft_created", "target_type": "draft", "target_id": "d1",
            "at": datetime(2026, 8, 9, 12),  # tzinfo 없음 = 드라이버가 주는 모양
            "before": None, "after": None,
        })

        row = self.repo.list_for_project(project_id="p1", limit=10)[0]

        self.assertEqual(row.at, _AT)

    def test_the_collection_has_no_ttl_index(self) -> None:
        """A6=A — 수명은 프로젝트가 정한다(I1). TTL 을 넣으면 파기 전에 사라진다."""
        for _keys, kwargs in self.collection.indexes:
            self.assertNotIn("expireAfterSeconds", kwargs)

    def test_purge_deletes_by_project(self) -> None:
        self.repo.purge_project(project_id="p1")

        self.assertEqual(self.collection.deleted, [{"project_id": "p1"}])


@unittest.skipUnless(_MONGO_AVAILABLE, "no MongoDB reachable for integration tests")
class DefaultAssemblyLiveMongoTest(unittest.TestCase):
    """★ 조립 가드 — 배포가 실제로 Mongo 에 쓰는가 (8.2c HARDEN-1 과 같은 이유).

    fake 셀은 어댑터를, HTTP 셀은 endpoint 를 잰다. 둘 다 green 인데
    `_default_activity_log_service()` 가 in-memory 를 돌려주면 **배포에서만** 로그가
    사라진다 — 그리고 A4=A 격리 때문에 **아무 소리도 안 난다**. 이 슬라이스에서
    조립 가드가 특히 필요한 이유가 그 조합이다.
    """

    def setUp(self) -> None:
        self._client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=800)
        self._db_name = f"activity_test_{uuid.uuid4().hex}"

    def tearDown(self) -> None:
        self._client.drop_database(self._db_name)
        self._client.close()

    def test_the_default_factory_persists_to_mongo_and_reads_back_aware(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"CORE_SOT_MONGO_URI": _MONGO_URI, "CORE_SOT_MONGO_DB": self._db_name},
        ):
            service = _default_activity_log_service()

        service.record(
            project_id="p1", actor_user_id="u1", action="project_renamed",
            target_type="project", target_id="p1", before="옛", after="새",
        )

        doc = self._client[self._db_name]["activity_events"].find_one(
            {"project_id": "p1"}
        )
        self.assertIsNotNone(doc, "배포 기본 조립이 Mongo 에 쓰지 않았다")
        stored = service.list_for_project(project_id="p1")[0]
        self.assertIsNotNone(
            stored.at.tzinfo,
            "드라이버가 돌려준 naive 날짜에 UTC 를 재부착하지 않았다",
        )
        service.purge_project(project_id="p1")
        self.assertEqual(
            self._client[self._db_name]["activity_events"].count_documents({}), 0
        )


class _ExplodingRepository:
    def insert(self, event) -> None:
        raise RuntimeError("storage is down")

    def list_for_project(self, *, project_id: str, limit: int):
        raise RuntimeError("storage is down")

    def purge_project(self, *, project_id: str) -> None:
        raise RuntimeError("storage is down")


class _Cursor:
    def __init__(self, docs) -> None:
        self._docs = docs

    def sort(self, key, direction):
        self._docs = sorted(
            self._docs, key=lambda doc: doc[key], reverse=direction == -1
        )
        return self

    def limit(self, count):
        return iter(self._docs[:count])

    def __iter__(self):
        return iter(self._docs)


class _Collection:
    def __init__(self) -> None:
        self.docs: list[dict] = []
        self.indexes: list[tuple] = []
        self.deleted: list[dict] = []

    def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))

    def insert_one(self, doc):
        self.docs.append(dict(doc))

    def find(self, query):
        return _Cursor([
            doc for doc in self.docs
            if doc["project_id"] == query["project_id"]
        ])

    def delete_many(self, query):
        self.deleted.append(dict(query))
        self.docs = [
            doc for doc in self.docs
            if doc["project_id"] != query["project_id"]
        ]


class _Database:
    def __init__(self, collection) -> None:
        self.collection = collection

    def __getitem__(self, name):
        assert name == "activity_events"
        return self.collection


class _Client:
    def __init__(self, collection) -> None:
        self.database = _Database(collection)

    def __getitem__(self, _name):
        return self.database


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
