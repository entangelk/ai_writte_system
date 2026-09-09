"""탈퇴 유예가 끝난 계정을 파기하는 워커 (계정 탈퇴 Slice 3).

오너 결정 **D2=ⓐ — 새 워커 컨테이너**(2026-09-07): 워커당 한 관심사가 선례이고,
**파기는 되돌릴 수 없어 다른 일과 한 프로세스에 두지 않는다.** 모양은
[`index_sync_worker.py`](index_sync_worker.py) 를 따른다 — 한 번 돌고 끝나는 것이
기본이고 `--loop` 이 SIGTERM 까지 배수하는 데몬이며 compose 서비스로 뜬다.

## 이 워커가 하지 않는 것

**재시도하지 않는다.** 파기 본체(`routers/admin.py::execute_project_purge`)는
core_sot 을 먼저 지우므로 두 번째 호출이 404 로 끝나고 derived(프롬프트 본문·원고
후보)에 도달하지 못한다. 그래서 실패한 계정은 `purge_started_at` 이 찍힌 채 남아
**다시 청구되지 않고**, 잔여 청소는 [`account_purge_reconciler.py`]
(account_purge_reconciler.py) 가 맡는다(D3=ⓐ).

## 왜 파기 본체를 그대로 못 부르는가

그 함수는 HTTP handler 와 공유하는 **한 벌뿐인 본체**라 `HTTPException` 을 던진다.
데몬은 HTTP 문맥이 아니므로 경계 하나가 필요하고, 그것이 아래
`_project_purge_boundary` 다 — **본체는 손대지 않는다**(세 벌째를 만들면 조용한 고아).

사용법 (컨테이너 안에서 돈다 — 저장소는 loopback 바인드다):

    python scripts/account_withdrawal_worker.py                 # 한 번
    python scripts/account_withdrawal_worker.py --loop          # 데몬
    python scripts/account_withdrawal_worker.py --dry-run       # 조사만
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, TextIO

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_MONGO_DB = "ai_writing_system"

#: 파기 감사 원장에 남는 사유. 관리자·소유자 purge 와 구별되어야 한다 — 원장을
#: 읽는 사람에게 *"누가 왜 지웠는가"* 가 이 문자열 하나로 답해진다.
PURGE_REASON = "account withdrawal grace period elapsed"


def _project_purge_boundary(services: dict):
    """`execute_project_purge` 로 가는 **비-HTTP 경계**.

    본체가 던지는 `HTTPException` 을 그대로 위로 보내지 않는다 — 워커에게 상태
    코드는 뜻이 없고, 오케스트레이터는 *"실패했다"* 와 그 문장만 있으면 된다.
    """
    from fastapi import HTTPException

    from services.application.app.routers.admin import execute_project_purge

    async def purge(*, project_id: str, acting_user_id: str) -> None:
        try:
            await execute_project_purge(
                project_id=project_id,
                reason=PURGE_REASON,
                acting_user_id=acting_user_id,
                **services,
            )
        except HTTPException as exc:
            raise RuntimeError(
                f"project purge refused ({exc.status_code}): {exc.detail}"
            ) from exc

    return purge


def purge_services(app_main, *, core_sot, sync_outbox, memory) -> dict:
    """파기 본체가 받는 서비스 16개.

    **본체의 인자 이름 그대로** 맞춘다 — 본체가 서비스를 하나 더 받게 되면 워커가
    조용히 낡는다(선례: worker 이미지가 15일 뒤처져 PROJECT_PURGED drain 없이 돌던
    2026-08-11). 조립(Mongo 접속)에서 떼어 낸 이유는 **그 대조를 저장소 없이 잴 수
    있어야** 하기 때문이다 — 붙여 두면 가드가 Mongo 를 요구하고, 그러면 가드가
    개발 머신에서 조용히 건너뛰어진다.
    """
    return {
        "core_sot": core_sot,
        "admin_audit": app_main._default_admin_audit_service(),
        "project_name_history": app_main._default_project_name_history_service(),
        "memory": memory,
        "analysis": app_main._default_analysis_service(
            core_sot, reindex_outbox=sync_outbox
        ),
        "review_queue": app_main._default_review_queue_service(),
        "identity_groups": app_main._default_candidate_identity_group_service(),
        "identity_group_approvals": (
            app_main._default_identity_group_approval_service()
        ),
        "gate_findings": app_main._default_gate_finding_service(),
        "writing_generation_jobs": (
            app_main._default_writing_generation_job_service()
        ),
        "writing_scratch": app_main._default_writing_scratch_service(),
        "writing_loop_audit": app_main._default_writing_loop_audit_service(),
        "llm_call_audit": app_main._default_llm_call_audit_service(),
        "access_grants": app_main._default_access_grant_service(),
        "activity": app_main._default_activity_log_service(),
        "sync_outbox": sync_outbox,
    }


def _build_purge_service(args: argparse.Namespace):
    """조립. `admin` 컨테이너와 같은 이유로 **Mongo 만** 필요하다."""
    if not args.mongo_uri:
        raise ValueError("CORE_SOT_MONGO_URI or --mongo-uri is required")
    if args.limit < 1:
        raise ValueError("limit must be positive")

    os.environ.setdefault("CORE_SOT_MONGO_URI", args.mongo_uri)
    os.environ.setdefault("CORE_SOT_MONGO_DB", args.mongo_db)

    from services.application.app import main as app_main
    from services.application.app.deletion.account_axis_sweep import (
        MongoAccountAxisSweeper,
    )
    from services.application.app.deletion.account_purge import AccountPurgeService
    from services.application.app.deletion.user_name_history import (
        UserNameHistoryService,
    )
    from services.application.app.deletion.user_name_history_mongo import (
        MongoUserNameHistoryRepository,
    )

    core_sot = app_main._default_core_sot_service()
    sync_outbox = app_main._default_index_sync_outbox_service()
    memory = app_main._default_memory_service(reindex_outbox=sync_outbox)
    services = purge_services(
        app_main, core_sot=core_sot, sync_outbox=sync_outbox, memory=memory
    )
    return AccountPurgeService(
        users=app_main._default_user_service()._repo,
        core_sot=core_sot,
        user_name_history=UserNameHistoryService(
            MongoUserNameHistoryRepository.from_uri(
                args.mongo_uri, db_name=args.mongo_db
            )
        ),
        sweeper=MongoAccountAxisSweeper.from_uri(
            args.mongo_uri, db_name=args.mongo_db
        ),
        purge_project=_project_purge_boundary(services),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Purge accounts whose withdrawal grace period has elapsed "
        "(one-shot by default; --loop runs a draining daemon until SIGTERM)."
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--mongo-uri", default=os.environ.get("CORE_SOT_MONGO_URI"))
    parser.add_argument(
        "--mongo-db", default=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_MONGO_DB)
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="파기 대상만 조사하고 아무것도 지우지 않는다. 파기는 비가역이라 "
        "운영자가 먼저 규모를 볼 수 있어야 한다(purge_reconciler 와 같은 자세).",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run as a long-lived daemon: loop run_once until SIGTERM/SIGINT.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.environ.get("ACCOUNT_PURGE_INTERVAL", "3600")),
        help="배수할 것이 없을 때 쉬는 초. 기본 1시간 — 유예가 30일이라 분 단위로 "
        "깨울 이유가 없고, 하루 늦게 도는 것이 파기를 더 안전하게 만들지도 않는다.",
    )
    return parser.parse_args(argv)


def _summary_doc(summary) -> dict[str, Any]:
    return {
        "accounts_claimed": summary.accounts_claimed,
        "accounts_purged": summary.accounts_purged,
        "accounts_failed": summary.accounts_failed,
        "failures": [
            {
                "user_id": result.user_id,
                "failed_at": result.failed_at,
                "error": result.error,
            }
            for result in summary.results if not result.succeeded
        ],
    }


def run_worker(args: argparse.Namespace, *, build_fn=_build_purge_service) -> dict:
    service = build_fn(args)
    if args.dry_run:
        from datetime import UTC, datetime

        due = service.due_accounts(now=datetime.now(UTC))
        return {
            "mode": "dry-run",
            "due_account_count": len(due),
            "due_user_ids": sorted(user.id for user in due),
        }
    return {"mode": "apply", **_summary_doc(asyncio.run(service.run_once(limit=args.limit)))}


class _GracefulShutdown:
    """SIGTERM/SIGINT 로 서는 정지 플래그. 진행 중인 **계정 하나는 끝내고** 다음
    청구 경계에서 나간다 — 파기 중간에 죽으면 그 계정이 부분 파기로 남는다."""

    def __init__(self) -> None:
        self.requested = False

    def request(self, *_args: object) -> None:
        self.requested = True

    def is_requested(self) -> bool:
        return self.requested


def _install_signal_handlers(stop: _GracefulShutdown) -> None:
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop.request)


def run_loop(
    args: argparse.Namespace,
    *,
    build_fn=_build_purge_service,
    stop: _GracefulShutdown,
    sleep_fn=time.sleep,
    stdout: TextIO | None = None,
) -> int:
    service = build_fn(args)
    stream = stdout if stdout is not None else sys.stdout

    def emit(doc: dict) -> None:
        print(json.dumps(doc, ensure_ascii=False, sort_keys=True), file=stream)
        stream.flush()

    emit({
        "event": "loop_started",
        "limit": args.limit,
        "interval_seconds": args.interval,
    })
    passes = 0
    while not stop.is_requested():
        summary = asyncio.run(
            service.run_once(limit=args.limit, stop_check=stop.is_requested)
        )
        passes += 1
        emit({"event": "pass", "pass": passes, **_summary_doc(summary)})
        if stop.is_requested():
            break
        if summary.accounts_claimed == 0:
            sleep_fn(args.interval)
    emit({"event": "loop_stopped", "passes": passes})
    return 0


def main(
    argv: list[str] | None = None,
    *,
    run_worker_fn=run_worker,
    run_loop_fn=run_loop,
    install_signal_handlers_fn=_install_signal_handlers,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    args = parse_args(argv)
    err = stderr if stderr is not None else sys.stderr
    try:
        if args.loop:
            if args.dry_run:
                raise ValueError("--dry-run and --loop are mutually exclusive")
            stop = _GracefulShutdown()
            install_signal_handlers_fn(stop)
            return run_loop_fn(args, stop=stop, stdout=stdout)
        summary = run_worker_fn(args)
    except ValueError as exc:
        print(str(exc), file=err)
        return 2

    stream = stdout if stdout is not None else sys.stdout
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), file=stream)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
