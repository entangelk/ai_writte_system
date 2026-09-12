"""계정 탈퇴 파기 워커 스크립트 (Slice 3, 오너 D2=ⓐ · D3=ⓐ).

여기서 잠그는 것 넷:

1. **조립이 파기 본체의 인자 집합과 정확히 맞는가** — 본체가 서비스를 하나 더 받게
   되면 워커가 조용히 낡는다(선례: worker 이미지가 15일 뒤처져 PROJECT_PURGED drain
   없이 돌던 2026-08-11).
2. **HTTP 예외가 경계를 못 넘는가** — 넘으면 워커가 상태 코드를 들고 죽는다.
3. **`--loop` 이 배수하고 SIGTERM 에 선다.**
4. **`--dry-run` 은 아무것도 지우지 않는다.**
5. **일회성 apply 가 실패를 요약에 싣는다** — 재시도가 없으므로 그 목록이 운영자의
   유일한 수습 통로다(2026-09-10 검증 H2 로 더해졌다).
"""

from __future__ import annotations

import asyncio
import inspect
import json
import unittest
from argparse import Namespace
from dataclasses import dataclass
from io import StringIO
from unittest import mock

from scripts import account_withdrawal_worker as worker
from services.application.app.deletion.account_purge import (
    AccountPurgeResult,
    AccountPurgeSummary,
)


class BoundarySignatureTest(unittest.TestCase):
    def test_the_assembled_services_match_the_purge_body_exactly(self) -> None:
        """★ 조립과 본체가 갈라지면 배포에서만 터진다.

        `execute_project_purge` 는 서비스를 **명시 인자**로 받는다. 워커가 그 집합을
        직접 들고 있으므로, 본체가 서비스를 더하거나 이름을 바꾸면 이 셀이 실패한다.

        - under: 본체에 서비스를 더하고 워커를 안 고치면 실패한다.
        - over: 본체의 **비-서비스 인자**(project_id·reason·acting_user_id)는 워커가
          호출부에서 채우므로 집합에서 빼야 한다 — 넣으면 실패한다.
        """
        from services.application.app.routers.admin import execute_project_purge

        expected = set(inspect.signature(execute_project_purge).parameters) - {
            "project_id", "reason", "acting_user_id",
        }
        sentinel = object()

        built = worker.purge_services(
            _StubBuilders(sentinel),
            core_sot=sentinel, sync_outbox=sentinel, memory=sentinel,
        )

        self.assertEqual(set(built), expected)

    def test_an_http_exception_from_the_body_never_escapes_as_http(self) -> None:
        """본체는 HTTP handler 와 공유하는 한 벌뿐이라 `HTTPException` 을 던진다.

        워커에게 상태 코드는 뜻이 없다 — 경계가 도메인 예외로 옮기고 **문장은 보존**
        한다(운영자가 무엇을 수습할지 아는 유일한 통로다).
        """
        from fastapi import HTTPException

        async def raising(**_kwargs):
            raise HTTPException(status_code=409, detail="project must be archived")

        with mock.patch(
            "services.application.app.routers.admin.execute_project_purge", raising
        ):
            purge = worker._project_purge_boundary({})

            with self.assertRaises(RuntimeError) as caught:
                asyncio.run(purge(project_id="p1", acting_user_id="user:a"))

        self.assertNotIsInstance(caught.exception, HTTPException)
        self.assertIn("409", str(caught.exception))
        self.assertIn("must be archived", str(caught.exception))

    def test_the_purge_reason_names_the_withdrawal_axis(self) -> None:
        """감사 원장을 읽는 사람이 관리자·소유자 파기와 구별할 수 있어야 한다."""
        self.assertIn("withdrawal", worker.PURGE_REASON)


class _StubBuilders:
    """`main` 모듈의 대역 — 모든 `_default_*` 가 같은 sentinel 을 돌려준다.

    이 가드가 재는 것은 **키 집합**이지 조립의 성공이 아니다. 진짜 조립을 부르면
    Mongo 가 필요해지고, 그러면 저장소 없는 머신에서 가드가 조용히 건너뛰어진다.
    """

    def __init__(self, sentinel) -> None:
        self._sentinel = sentinel

    def __getattr__(self, name):
        assert name.startswith("_default_"), name
        return lambda *args, **kwargs: self._sentinel


class _FakeService:
    def __init__(self, *, claims: list[int]) -> None:
        self._claims = list(claims)
        self.calls = 0
        self.due: list = []
        #: 마지막 pass 가 받은 정지 확인자. **받고 버리면 배선이 안 잠긴다** —
        #: 2026-09-10 승격 재검(MU-20)이 그 사각을 실측했다.
        self.last_stop_check = None

    def due_accounts(self, *, now):
        return tuple(self.due)

    async def run_once(self, *, limit=10, stop_check=None, now=None):
        self.calls += 1
        self.last_stop_check = stop_check
        claimed = self._claims.pop(0) if self._claims else 0
        return AccountPurgeSummary(accounts_claimed=claimed, accounts_purged=claimed)


class _FakeStop:
    def __init__(self, stop_after: int) -> None:
        self._stop_after = stop_after
        self.checks = 0

    def force(self) -> None:
        """이후 확인은 무조건 정지를 말한다 — 배선 셀이 *넘겨받은 호출자* 에게
        물어볼 때 쓴다(동일성이 아니라 동작으로 재기 위해)."""
        self._stop_after = -1

    def is_requested(self) -> bool:
        self.checks += 1
        return self.checks > self._stop_after


class LoopTest(unittest.TestCase):
    def test_run_loop_drains_then_idles_then_stops(self) -> None:
        service = _FakeService(claims=[2, 0])
        slept: list[float] = []
        out = StringIO()
        args = Namespace(limit=10, interval=7.0)

        code = worker.run_loop(
            args, build_fn=lambda _a: service, stop=_FakeStop(stop_after=4),
            sleep_fn=slept.append, stdout=out,
        )

        self.assertEqual(code, 0)
        self.assertEqual(service.calls, 2)
        # 청구가 있던 첫 pass 는 쉬지 않고, 빈 pass 에서만 쉰다.
        self.assertEqual(slept, [7.0])
        events = [json.loads(line)["event"] for line in out.getvalue().splitlines()]
        self.assertEqual(events, ["loop_started", "pass", "pass", "loop_stopped"])

    def test_the_loop_threads_its_stop_flag_into_run_once(self) -> None:
        """★ **배선 문장 자체**를 잠근다(2026-09-10 승격 재검 H1').

        H1 이 닫은 것은 **피호출자**였다 — `run_once` 가 `stop_check` 를 존중하는가.
        그런데 `run_loop` 이 그 인자를 **넘기는 문장**은 아무도 안 봤고, 인자를
        지우는 변이(MU-20)가 **43셀 전건 초록**이었다(대역이 인자를 받고 버렸다).

        끊기면 SIGTERM 은 `while` 경계에서만 서고 **진행 중인 pass 가 최대
        `limit`(기본 10) 계정을 끝까지 돈다** — compose `stop_grace_period: 120s`
        를 넘기면 SIGKILL 이라 그 계정이 **부분 파기**로 남는다. H1 이 막으려던
        결과가 다른 문으로 들어오는 자리다.

        형제 워커가 같은 축을 같은 방법으로 잠근다:
        `test_index_sync_worker_script.py::WorkerLoopTest::
        test_run_loop_drains_until_stop_then_exits`(*"stop_check was threaded into
        run_once (G2 wiring, not just the loop guard)"*).

        **양방향**:
          · under — `stop_check=` 인자를 지우면 `None` 이 기록돼 실패한다(MU-20).
          · over — **동일성이 아니라 동작**으로 잰다. 넘겨받은 호출자에게 *정지를
            세운 뒤* 물어보므로, 배선을 람다로 감싸도 같은 플래그를 가리키는 한
            안 깨진다. 반대로 **다른** 플래그를 넘기면 잡힌다.
        """
        service = _FakeService(claims=[1, 0])
        stop = _FakeStop(stop_after=4)

        worker.run_loop(
            Namespace(limit=10, interval=7.0), build_fn=lambda _a: service,
            stop=stop, sleep_fn=lambda _s: None, stdout=StringIO(),
        )

        self.assertIsNotNone(
            service.last_stop_check,
            "run_loop 이 정지 플래그를 run_once 로 안 넘겼다 — 진행 중인 pass 가 "
            "SIGTERM 을 못 듣고 limit 만큼 계속 파기한다",
        )
        stop.force()
        self.assertTrue(
            service.last_stop_check(),
            "run_once 가 받은 호출자가 **이 루프의** 정지 플래그가 아니다 — 세워 "
            "놓고 물었는데 아니라고 답했다",
        )

    def test_dry_run_and_loop_are_mutually_exclusive(self) -> None:
        """`--dry-run` 은 *조사만* 이고 `--loop` 은 *계속 지운다* 다 — 함께 주면
        운영자가 둘 중 어느 쪽을 기대했는지 알 수 없어 거절한다."""
        err = StringIO()

        code = worker.main(["--loop", "--dry-run"], stderr=err)

        self.assertEqual(code, 2)
        self.assertIn("mutually exclusive", err.getvalue())

    def test_dry_run_reports_the_due_accounts_without_purging(self) -> None:
        service = _FakeService(claims=[])
        service.due = [mock.Mock(id="user:b"), mock.Mock(id="user:a")]
        args = Namespace(limit=10, dry_run=True)

        summary = worker.run_worker(args, build_fn=lambda _a: service)

        self.assertEqual(summary["mode"], "dry-run")
        self.assertEqual(summary["due_user_ids"], ["user:a", "user:b"])
        self.assertEqual(service.calls, 0, "dry-run 이 파기를 돌렸다")


class _StubSummaryService:
    """준비된 요약을 그대로 돌려주는 대역 — apply 모드의 **출력 모양**만 잰다."""

    def __init__(self, summary) -> None:
        self._summary = summary
        self.limit: int | None = None

    async def run_once(self, *, limit=10, stop_check=None, now=None):
        self.limit = limit
        return self._summary


class ApplyModeTest(unittest.TestCase):
    """일회성 apply(H2, 2026-09-10 검증) — 셀이 dry-run·loop 에만 있었다.

    ★ 워커는 **재시도하지 않는다**(D3=ⓐ). 실패한 계정은 `purge_started_at` 만
    찍힌 채 조용히 남으므로, 운영자가 *무엇을 수습해야 하는지* 아는 통로는
    이 요약의 `failures` 뿐이다(`account_purge._failure` 주석이 그렇게 적는다).
    비면 실패가 없어서 빈 것인지 출력이 삼킨 것인지 구별되지 않는다.
    """

    def test_apply_mode_reports_every_failure_with_its_stage(self) -> None:
        """- under — `_summary_doc` 이 `failures` 를 빠뜨리면 실패한다.
        - over — 성공한 계정까지 실어도 실패한다(수습 목록이 아니라 전체 목록이
          되면 운영자가 무엇을 봐야 하는지 다시 골라야 한다).
        """
        service = _StubSummaryService(AccountPurgeSummary(
            accounts_claimed=2, accounts_purged=1, accounts_failed=1,
            results=(
                AccountPurgeResult(user_id="user:a", username="alice"),
                AccountPurgeResult(
                    user_id="user:b", username="bob",
                    failed_at="account_axis_sweep",
                    error="RuntimeError: sweep storage went away",
                ),
            ),
        ))
        args = Namespace(limit=3, dry_run=False)

        doc = worker.run_worker(args, build_fn=lambda _a: service)

        self.assertEqual(doc["mode"], "apply")
        self.assertEqual(
            (doc["accounts_claimed"], doc["accounts_purged"], doc["accounts_failed"]),
            (2, 1, 1),
        )
        self.assertEqual(doc["failures"], [{
            "user_id": "user:b",
            "failed_at": "account_axis_sweep",
            "error": "RuntimeError: sweep storage went away",
        }])
        self.assertEqual(
            service.limit, 3, "--limit 이 run_once 로 전달되지 않았다"
        )

    def test_a_clean_apply_pass_reports_an_empty_failure_list(self) -> None:
        """빈 목록은 **키가 있는 채로** 비어야 한다 — 키가 사라지면 요약을 읽는
        쪽이 *실패 없음* 과 *출력 형식이 바뀜* 을 구별할 수 없다."""
        service = _StubSummaryService(AccountPurgeSummary(
            accounts_claimed=1, accounts_purged=1,
            results=(AccountPurgeResult(user_id="user:a", username="alice"),),
        ))

        doc = worker.run_worker(
            Namespace(limit=10, dry_run=False), build_fn=lambda _a: service
        )

        self.assertEqual(doc["failures"], [])
        self.assertEqual(doc["accounts_failed"], 0)


class ParseArgsTest(unittest.TestCase):
    def test_defaults_are_one_shot_with_an_hourly_interval(self) -> None:
        """유예가 30일이라 분 단위로 깨울 이유가 없다.

        - over: 기본을 초 단위로 조이면 이 셀이 실패한다(파기가 더 안전해지지 않는다).
        """
        args = worker.parse_args([])

        self.assertFalse(args.loop)
        self.assertFalse(args.dry_run)
        self.assertEqual(args.interval, 3600.0)
        self.assertEqual(args.limit, 10)

    def test_install_signal_handlers_binds_stop_request(self) -> None:
        stop = worker._GracefulShutdown()
        bound: dict = {}

        with mock.patch("signal.signal", lambda sig, fn: bound.setdefault(sig, fn)):
            worker._install_signal_handlers(stop)

        self.assertEqual(len(bound), 2)
        self.assertFalse(stop.is_requested())
        next(iter(bound.values()))(None, None)
        self.assertTrue(stop.is_requested())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class ReconcilerTest(unittest.TestCase):
    """부분 파기 수습 경로 — 데몬이 멈춘 자리를 잇는 본체의 조건 넷.

    Slice 4b(2026-09-12)부터 본체는 ``deletion/account_reconcile.py`` 다 —
    스크립트와 관리자 operation 이 같이 쓰는 한 벌. 이 조건 셀들은 이관 전에
    스크립트가 지키던 것과 같은 넷을 그 모듈에 잠근다.
    """

    def setUp(self) -> None:
        from services.application.app.deletion.account_reconcile import (
            AccountReconcileService,
            MongoAccountReconcileRepository,
        )

        class _Client:
            def __init__(self, db) -> None:
                self._db = db

            def __getitem__(self, _name):
                return self._db

        self._make_service = lambda db: AccountReconcileService(
            MongoAccountReconcileRepository(
                _Client(db), db_name="ai_writing_system"
            ),
            sweeper=_NullSweeper(),
        )

    def test_a_stalled_account_is_the_one_with_a_purge_stamp(self) -> None:
        """성공하면 행이 사라지므로 이 질의가 곧 *부분 파기* 의 정의다."""
        db = _FakeDb({
            "users": [
                {"_id": "user:a", "purge_started_at": None},
                {"_id": "user:b", "purge_started_at": "t"},
            ],
        })

        service = self._make_service(db)
        self.assertEqual(service._repo.stalled_user_ids(), ["user:b"])

    def test_leftover_projects_hold_the_user_row_back(self) -> None:
        """★ 프로젝트가 남았으면 계정 행을 지우지 않는다.

        그 행의 `owner_id` 가 잔여를 찾는 **유일한 실마리**다. 먼저 지우면
        프로젝트 축 reconciler 도 그것이 누구 것이었는지 모른다.
        """
        db = _FakeDb({
            "users": [{"_id": "user:b", "purge_started_at": "t"}],
            "projects": [{"_id": "p9", "owner_id": "user:b"}],
            "user_name_history": [{"_id": "user_name:user:b"}],
        })

        result = self._make_service(db).reconcile("user:b")

        self.assertEqual(result.leftover_projects, ["p9"])
        self.assertFalse(result.removed_user_row)
        self.assertEqual(len(db.collections["users"]), 1)

    def test_a_missing_tombstone_also_holds_the_user_row_back(self) -> None:
        """이름 한 값을 남기는 것이 오너 결정이다 — 묘비 없이 지우면 원장이
        영원히 id 로만 답한다. under: 조건에서 묘비를 빼면 이 셀이 실패한다."""
        db = _FakeDb({
            "users": [{"_id": "user:b", "purge_started_at": "t"}],
            "projects": [],
            "user_name_history": [],
        })

        result = self._make_service(db).reconcile("user:b")

        self.assertFalse(result.has_username_tombstone)
        self.assertFalse(result.removed_user_row)
        self.assertEqual(len(db.collections["users"]), 1)

    def test_a_clean_stalled_account_is_finished_off(self) -> None:
        """over-strict 반대편 — 조건을 더 조이면 수습이 아무것도 못 끝낸다."""
        db = _FakeDb({
            "users": [{"_id": "user:b", "purge_started_at": "t"}],
            "projects": [],
            "user_name_history": [{"_id": "user_name:user:b"}],
        })

        result = self._make_service(db).reconcile("user:b")

        self.assertTrue(result.removed_user_row)
        self.assertEqual(db.collections["users"], [])


@dataclass
class _Deleted:
    deleted_count: int


class _NullSweeper:
    def sweep(self, user_id):
        return {}


class _FakeDb:
    def __init__(self, collections) -> None:
        self.collections = collections

    def __getitem__(self, name):
        return _FakeDbCollection(self.collections.setdefault(name, []))


class _FakeDbCollection:
    def __init__(self, docs) -> None:
        self._docs = docs

    def _matches(self, doc, query):
        for key, want in query.items():
            if isinstance(want, dict) and "$ne" in want:
                if doc.get(key) == want["$ne"]:
                    return False
            elif doc.get(key) != want:
                return False
        return True

    def find(self, query, _projection=None):
        return [doc for doc in self._docs if self._matches(doc, query)]

    def find_one(self, query, _projection=None):
        found = self.find(query)
        return found[0] if found else None

    def count_documents(self, query):
        return len(self.find(query))

    def delete_one(self, query):
        for index, doc in enumerate(self._docs):
            if self._matches(doc, query):
                self._docs.pop(index)
                return _Deleted(1)
        return _Deleted(0)
