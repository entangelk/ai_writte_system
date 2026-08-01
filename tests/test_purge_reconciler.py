"""D8-6 잔여: 파기된 project 의 잔류 데이터를 reconciler 가 찾아 지운다.

**막으려는 결함.** `POST /admin/projects/{id}/purge` 는 core_sot 을 먼저 지우고 derived 와
outbox enqueue 를 뒤이어 한다. derived 단계에서 mongo 장애가 나면 503 이 나가지만 **재시도는
불가능하다** — core_sot 이 이미 비어 있어 두 번째 호출은 404 다. 그래서 derived 가 영원히 남는데,
거기에는 그 project 의 **프롬프트 본문**(`llm_call_audits`)과 **원고 후보**(`writing_drafts_scratch`)가
들어 있다. 파기를 요청받은 데이터가 남는 것이므로 D5 "부분 삭제는 조용한 고아" 금지 위반이다.

잠그는 것 네 가지.

- **under-strict**: 고아를 못 찾거나 안 지우면 실패한다(핵심 계약).
- **over-strict**: **살아 있는 project 의 데이터를 지우면 실패한다.** reconciler 는 삭제 도구라
  이 방향이 under 보다 위험하다 — 판정이 뒤집히면 멀쩡한 원고가 사라진다.
- **dry-run 기본**: `--apply` 없이는 아무것도 바뀌지 않는다. 파기는 비가역이므로 기본이 안전해야 한다.
- **로스터를 안 믿는다**: 스크립트가 모르는 **새 컬렉션**에 고아가 있어도 찾아낸다. 컬렉션 목록을
  코드에 적었다면 이 셀이 실패한다(2026-08-01 스크립트 로그인 슬라이스의 교훈).
"""

from __future__ import annotations

import os
import sys
import time
import unittest
import uuid
from unittest import mock

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, PyMongoError

    _PYMONGO_AVAILABLE = True
except ImportError:  # pragma: no cover - 환경에 pymongo 가 없을 때
    MongoClient = None
    ConnectionFailure = PyMongoError = Exception
    _PYMONGO_AVAILABLE = False

from scripts import purge_reconciler
from scripts.purge_reconciler import (
    _collections_scoped_by_project,
    _orphan_project_ids,
    _purge,
)

_MONGO_URI = os.environ.get(
    "CORE_SOT_TEST_MONGO_URI", "mongodb://localhost:27020/?replicaSet=rs-test"
)


def _probe_mongo() -> bool:
    if not _PYMONGO_AVAILABLE:
        return False
    for _ in range(5):
        client = None
        probe_db = f"purge_reconciler_probe_{uuid.uuid4().hex}"
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
class PurgeReconcilerTest(unittest.TestCase):
    """실 Mongo 위에서 돈다 — `distinct`·`list_collection_names` 가 이 도구의 핵심이라
    fake collection 으로는 그 성질을 재현하지 못한다(HANDOFF 의 pymongo 함정과 같은 이유)."""

    LIVE = "live-project"
    PURGED = "purged-project"

    def setUp(self) -> None:
        self._client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=800)
        self._db_name = f"purge_reconciler_test_{uuid.uuid4().hex}"
        self.db = self._client[self._db_name]

        # 살아 있는 project 는 `projects` 에 행이 있다. 파기된 것은 없다 — 그것이 유일한 판정 근거다.
        self.db["projects"].insert_one({"_id": self.LIVE, "name": "살아 있음"})
        for collection in ("llm_call_audits", "writing_drafts_scratch", "memory_entries"):
            self.db[collection].insert_many(
                [
                    {"project_id": self.LIVE, "body": "살아 있는 원고"},
                    {"project_id": self.PURGED, "body": "파기됐어야 하는 프롬프트"},
                ]
            )

    def tearDown(self) -> None:
        self._client.drop_database(self._db_name)
        self._client.close()

    def _run(self) -> dict[str, list[str]]:
        collections = _collections_scoped_by_project(self.db)
        return _orphan_project_ids(self.db, collections)

    def test_the_orphan_is_found_and_the_live_project_is_not(self) -> None:
        orphans = self._run()

        self.assertEqual(sorted(orphans), [self.PURGED])
        self.assertNotIn(
            self.LIVE,
            orphans,
            "`projects` 에 행이 있는 project 를 고아로 보면 멀쩡한 원고를 지운다",
        )
        self.assertEqual(
            sorted(orphans[self.PURGED]),
            ["llm_call_audits", "memory_entries", "writing_drafts_scratch"],
        )

    def test_a_collection_the_script_never_heard_of_is_still_swept(self) -> None:
        """컬렉션 목록을 코드에 적었다면 여기서 실패한다."""

        self.db["some_future_derived_collection"].insert_one(
            {"project_id": self.PURGED, "body": "미래의 파생 데이터"}
        )

        self.assertIn("some_future_derived_collection", self._run()[self.PURGED])

    def test_purging_removes_the_orphan_and_leaves_the_live_project_intact(self) -> None:
        collections = _collections_scoped_by_project(self.db)

        deleted = _purge(self.db, self.PURGED, collections)

        self.assertEqual(
            sorted(deleted), ["llm_call_audits", "memory_entries", "writing_drafts_scratch"]
        )
        for collection in ("llm_call_audits", "writing_drafts_scratch", "memory_entries"):
            with self.subTest(collection=collection):
                self.assertEqual(
                    self.db[collection].count_documents({"project_id": self.PURGED}),
                    0,
                    "파기 요청된 project 의 데이터가 남았다 — D5 부분 삭제 금지 위반",
                )
                self.assertEqual(
                    self.db[collection].count_documents({"project_id": self.LIVE}),
                    1,
                    "살아 있는 project 의 데이터를 지웠다 — 과잉 교정",
                )
        self.assertEqual(self.db["projects"].count_documents({"_id": self.LIVE}), 1)

    def test_the_default_run_changes_nothing(self) -> None:
        """dry-run 이 기본이다 — 파기는 비가역이라 기본이 안전해야 한다."""

        before = {
            name: self.db[name].count_documents({})
            for name in self.db.list_collection_names()
        }

        orphans = self._run()  # 조사만. `--apply` 없이는 _purge 를 부르지 않는다.

        self.assertTrue(orphans, "조사 자체는 고아를 찾아야 한다")
        after = {
            name: self.db[name].count_documents({})
            for name in self.db.list_collection_names()
        }
        self.assertEqual(after, before)


@unittest.skipUnless(_MONGO_AVAILABLE, "no MongoDB reachable for integration tests")
class PurgeReconcilerCommandTest(unittest.TestCase):
    """스크립트를 통째로 돌린다 — 헬퍼가 맞아도 **배선**이 틀리면 아무것도 안 지운다."""

    def setUp(self) -> None:
        self._client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=800)
        self._db_name = f"purge_reconciler_cmd_{uuid.uuid4().hex}"
        self.db = self._client[self._db_name]
        self.db["projects"].insert_one({"_id": "live", "name": "살아 있음"})
        self.db["llm_call_audits"].insert_many(
            [{"project_id": "live"}, {"project_id": "dead"}]
        )

    def tearDown(self) -> None:
        self._client.drop_database(self._db_name)
        self._client.close()

    def _run(self, *argv: str) -> None:
        with mock.patch.dict(
            os.environ,
            {"CORE_SOT_MONGO_URI": _MONGO_URI, "CORE_SOT_MONGO_DB": self._db_name},
        ), mock.patch.object(sys, "argv", ["purge_reconciler.py", *argv]):
            self.assertEqual(purge_reconciler.main(), 0)

    def test_the_enqueued_purge_event_survives_the_sweep(self) -> None:
        """★ 순서 함정: `index_sync_outbox` 도 `project_id` 를 가진 컬렉션이라 삭제 대상이다.

        그래서 삭제가 먼저고 enqueue 가 마지막이어야 한다. 순서를 뒤집으면 방금 넣은
        PROJECT_PURGED 를 스스로 지우고, **vector/lexical 5백엔드가 영원히 안 지워진다**
        (그 파기는 worker 의 PROJECT_PURGED drain 이 하기 때문이다). 그 실패는 mongo 만
        보면 성공처럼 보이므로 여기서만 잡힌다.
        """

        self._run("--apply")

        entries = list(self.db["index_sync_outbox"].find({"project_id": "dead"}))
        self.assertEqual(
            len(entries),
            1,
            "PROJECT_PURGED entry 가 사라졌다 — enqueue 를 삭제보다 먼저 했는가?",
        )
        self.assertEqual(entries[0]["event"], "project_purged")
        self.assertEqual(self.db["llm_call_audits"].count_documents({}), 1)

    def test_without_apply_nothing_is_written(self) -> None:
        self._run()

        self.assertEqual(self.db["llm_call_audits"].count_documents({}), 2)
        self.assertEqual(self.db["index_sync_outbox"].count_documents({}), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
