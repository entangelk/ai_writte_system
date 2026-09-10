"""세션 49 산출물 독립 검증 — 파기 경로를 **실 mongod** 로 돈다 (2026-09-10).

구현자 신고 약점 ①("파기 경로는 실 Mongo 로 한 번도 안 돌았다 — 셀은 전부
fake")를 닫는 재현 스크립트. 청구 → 묘비 → 프로젝트(본체) → 계정 축 스윕 →
계정 행 순서와 reconciler 수습을 fake 없이 replica set 에서 돌리고 끝상태를
단정한다.

대상 DB 는 **분리된 이름**(`v49_slice3_verify`)이고 종료 시 스스로 지운다.
개발 스택 데이터(27520 `ai_writing_system`)는 읽지도 않는다.

사용(호스트, test-mongo 가 PRIMARY 인 상태):

    python3 docs/verifications/2026-09-10/repro_live_account_purge.py \
        --mongo-uri "mongodb://127.0.0.1:27020/?replicaSet=rs-test"

끝줄에 ``RESULT: PASS`` 를 출력하지 않으면 전부 실패로 읽는다.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from pymongo import MongoClient

NOW = datetime(2026, 9, 10, 0, tzinfo=UTC)
DUE_SINCE = NOW - timedelta(days=31)

ALICE = "user:" + "a1" * 12   # 유예 만료 — 이번 실행에 파기된다
BOB = "user:" + "b2" * 12     # 부분 파기(청구만 됨) — reconciler 수습 대상
CAROL = "user:" + "c3" * 12   # 활동 계정 — 아무 일도 일어나지 않아야 한다

CHECKS: list[tuple[str, bool, str]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((label, ok, detail))
    print(f"  {'ok ' if ok else 'FAIL'} {label}" + (f" — {detail}" if detail and not ok else ""))


def seed(client: MongoClient, db_name: str) -> None:
    from services.application.app.auth.models import User
    from services.application.app.auth.users_mongo import MongoUserRepository
    from services.application.app.deletion.user_name_history import (
        UserNameSnapshot,
    )
    from services.application.app.deletion.user_name_history_mongo import (
        MongoUserNameHistoryRepository,
    )

    db = client[db_name]
    users = MongoUserRepository(client, db_name=db_name)

    def row(uid: str, username: str, **extra) -> User:
        return User(
            id=uid, username=username, password_hash="h", is_admin=False,
            is_active=True, created_at=NOW - timedelta(days=90),
            status="active", **extra,
        )

    users.insert(row(ALICE, "alice49"))
    users.insert(row(BOB, "bob49"))
    users.insert(row(CAROL, "carol49"))

    # Slice 1 seam 으로 유예 시작 — alice 는 만료, bob 은 청구까지 간 상태(수습 입력)
    users.set_withdrawal_requested_at(ALICE, at=DUE_SINCE, only_if_absent=True)
    users.set_withdrawal_requested_at(BOB, at=DUE_SINCE, only_if_absent=True)
    assert users.claim_for_purge(BOB, at=NOW - timedelta(hours=1)) is not None

    # 계정 축 잔여 — 실제 어댑터가 쓰는 문서 모양 그대로
    db["sessions"].insert_many([
        {"_id": "tok-a1", "user_id": ALICE, "created_at": NOW, "expires_at": NOW},
        {"_id": "tok-a2", "user_id": ALICE, "created_at": NOW, "expires_at": NOW},
        {"_id": "tok-c1", "user_id": CAROL, "created_at": NOW, "expires_at": NOW},
        {"_id": "tok-b1", "user_id": BOB, "created_at": NOW, "expires_at": NOW},
    ])
    db["request_quota_policies"].insert_many([
        {"_id": ALICE, "daily_limit": 20, "weekly_limit": 100},
        {"_id": CAROL, "daily_limit": 20, "weekly_limit": 100},
    ])
    db["request_usage_ledger"].insert_many([
        {"_id": "led-a1", "target_user_id": ALICE, "action": "writing_report",
         "daily_key": "d", "weekly_key": "w", "at": NOW},
        {"_id": "led-b1", "target_user_id": BOB, "action": "writing_report",
         "daily_key": "d", "weekly_key": "w", "at": NOW},
    ])
    db["admin_audit_events"].insert_one(
        {"_id": "aud-1", "admin_user_id": "user:" + "9" * 24,
         "target_user_id": ALICE, "action": "status_change", "at": NOW},
    )
    # 제3의 축(브리프 후속 고려) — 어느 규칙도 못 찾는다고 예고된 잔류
    db["login_failures"].insert_one({"_id": "alice49", "failures": 1, "at": NOW})
    # 프로젝트 축 — alice 소유(파기 대상) 1, bob 소유(수습 때 잔여) 1
    db["projects"].insert_many([
        {"_id": "proj-alice", "name": "alice 의 원고", "archived": False,
         "owner_id": ALICE},
        {"_id": "proj-bob", "name": "bob 의 원고", "archived": False,
         "owner_id": BOB},
    ])
    # bob 묘비는 이미 있다(청구 단계에서 쓰였다고 가정) — 수습 판정의 입력
    MongoUserNameHistoryRepository(client, db_name=db_name).put(
        UserNameSnapshot(target_user_id=BOB, username="bob49", purged_at=NOW)
    )


def run_worker(uri: str, db_name: str) -> dict:
    from scripts import account_withdrawal_worker as worker

    out = io.StringIO()
    with redirect_stdout(out):
        code = worker.main(["--mongo-uri", uri, "--mongo-db", db_name, "--limit", "5"])
    print("  worker stdout:")
    for line in out.getvalue().splitlines():
        print("   |", line)
    assert code == 0, f"worker exit {code}"
    return json.loads(out.getvalue())


def run_reconciler(argv: list[str]) -> dict:
    import scripts.account_purge_reconciler as reconciler

    out = io.StringIO()
    with redirect_stdout(out):
        code = reconciler.main(argv)
    print("  reconciler stdout:")
    for line in out.getvalue().splitlines():
        print("   |", line)
    assert code == 0, f"reconciler exit {code}"
    return json.loads(out.getvalue())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mongo-uri", default="mongodb://127.0.0.1:27020/?replicaSet=rs-test")
    parser.add_argument("--mongo-db", default="v49_slice3_verify")
    parser.add_argument("--keep", action="store_true",
                        help="종료 시 대상 DB 를 지우지 않는다(디버깅용).")
    args = parser.parse_args()

    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=8000)
    client.drop_database(args.mongo_db)
    # compose 의 withdrawal_worker 환경과 같은 최소 집합 — 이것보다 더 필요하면
    # 배포 컨테이너에서도 데몬이 뜨지 못한다는 뜻이다.
    os.environ["CORE_SOT_MONGO_URI"] = args.mongo_uri
    os.environ["CORE_SOT_MONGO_DB"] = args.mongo_db
    os.environ["CORE_SOT_MONGO_TRANSACTIONS"] = "true"

    print("== dry-run (아무것도 지우지 않아야 한다) ==")
    seed(client, args.mongo_db)
    from scripts import account_withdrawal_worker as worker

    dry_out = io.StringIO()
    with redirect_stdout(dry_out):
        code = worker.main([
            "--mongo-uri", args.mongo_uri, "--mongo-db", args.mongo_db, "--dry-run",
        ])
    dry = json.loads(dry_out.getvalue())
    check("dry-run exit 0", code == 0)
    check("dry-run 대상은 alice 뿐", dry["due_user_ids"] == [ALICE],
          str(dry["due_user_ids"]))

    print("== apply (실 파기) ==")
    summary = run_worker(args.mongo_uri, args.mongo_db)
    check("worker 요약: 청구 1·파기 1·실패 0",
          (summary["accounts_claimed"], summary["accounts_purged"],
           summary["accounts_failed"]) == (1, 1, 0), str(summary))

    db = client[args.mongo_db]
    check("alice 계정 행 소멸", db["users"].find_one({"_id": ALICE}) is None)
    bob_row = db["users"].find_one({"_id": BOB})
    check("bob(부분 파기) 계정 행 생존 + purge_started_at 표식",
          bob_row is not None and bob_row.get("purge_started_at") is not None)
    check("carol 계정 행 생존", db["users"].find_one({"_id": CAROL}) is not None)

    tomb = db["user_name_history"].find_one({"_id": "user_name:" + ALICE})
    check("alice 묘비 존재(_id 접두)·target_user_id·이름 보존",
          tomb is not None and tomb["target_user_id"] == ALICE
          and tomb["username"] == "alice49")

    check("alice 세션 2건 소멸(필드 규칙)·carol 세션 생존",
          db["sessions"].count_documents({"user_id": ALICE}) == 0
          and db["sessions"].count_documents({"user_id": CAROL}) == 1)
    check("alice quota policy 소멸(_id 규칙)·carol 행 생존",
          db["request_quota_policies"].find_one({"_id": ALICE}) is None
          and db["request_quota_policies"].find_one({"_id": CAROL}) is not None)
    check("사용량 원장 보존(보존 표식)",
          db["request_usage_ledger"].count_documents({"target_user_id": ALICE}) == 1)
    check("감사 원장 보존(보존 표식)",
          db["admin_audit_events"].count_documents({"target_user_id": ALICE}) >= 1)
    check("login_failures 잔류(제3의 축 — 예고된 미수습)",
          db["login_failures"].find_one({"_id": "alice49"}) is not None)
    check("alice 프로젝트 소멸·bob 프로젝트 생존",
          db["projects"].find_one({"_id": "proj-alice"}) is None
          and db["projects"].find_one({"_id": "proj-bob"}) is not None)
    purged_audit = db["admin_audit_events"].find_one(
        {"admin_user_id": ALICE, "reason": "account withdrawal grace period elapsed"})
    check("파기 감사에 탈퇴 사유 리터럴(스윕을 살아남는다)", purged_audit is not None)

    print("== reconciler dry-run (bob 수습 조사) ==")
    dryrec = run_reconciler([])
    stalled = dryrec.get("stalled_user_ids")
    check("stalled = bob 만", stalled == [BOB], str(stalled))
    would = dryrec.get("would_reconcile", {}).get(BOB, {})
    check("잔여 프로젝트 보고·묘비 있음 보고",
          would.get("leftover_projects") == ["proj-bob"]
          and would.get("has_username_tombstone") is True, str(would))

    print("== reconciler apply — 잔여 프로젝트가 있으므로 계정 행을 지우지 않는다 ==")
    applied = run_reconciler(["--apply"])
    rec = applied.get("reconciled", {}).get(BOB, {})
    check("bob 계정 행 보존(잔여 때문)", rec.get("removed_user_row") is False
          and db["users"].find_one({"_id": BOB}) is not None, str(rec))
    check("bob 세션은 이번에 쓸렸다", rec.get("swept", {}).get("sessions") == 1)
    check("bob 묘비 보존",
          db["user_name_history"].find_one({"_id": "user_name:" + BOB}) is not None)
    check("bob 원장 보존",
          db["request_usage_ledger"].count_documents({"target_user_id": BOB}) == 1)

    print("== reconciler apply — 잔여 프로젝트가 사라진 뒤에는 끝낸다 ==")
    db["projects"].delete_one({"_id": "proj-bob"})
    applied2 = run_reconciler(["--apply"])
    rec2 = applied2.get("reconciled", {}).get(BOB, {})
    check("bob 계정 행 소멸·묘비·원장은 여전히 보존",
          rec2.get("removed_user_row") is True
          and db["users"].find_one({"_id": BOB}) is None
          and db["user_name_history"].find_one({"_id": "user_name:" + BOB}) is not None
          and db["request_usage_ledger"].count_documents({"target_user_id": BOB}) == 1,
          str(rec2))

    if not args.keep:
        client.drop_database(args.mongo_db)
        print(f"== 정리: {args.mongo_db} 삭제 ==")
    client.close()

    failed = [(l, d) for l, ok, d in CHECKS if not ok]
    print(f"\nCHECKS: {len(CHECKS) - len(failed)}/{len(CHECKS)} passed")
    for label, detail in failed:
        print(f"  FAILED: {label} — {detail}")
    print("RESULT: PASS" if not failed else "RESULT: FAIL")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
