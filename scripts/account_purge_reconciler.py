"""부분 파기된 계정의 잔류 데이터를 찾아 정리한다 — 계정 탈퇴 Slice 3 의 수습 경로.

**무엇을 고치는가.** 파기 데몬(`account_withdrawal_worker.py`)은 실패하면 그 계정에서
**멈춘다**(D3=ⓐ). 재시도가 수습이 아니기 때문이다 — 파기 본체가 core_sot 을 먼저
지우므로 두 번째 호출은 404 로 끝나고 derived(프롬프트 본문·원고 후보)에 도달하지
못한다. 그래서 실패한 계정은 `purge_started_at` 이 찍힌 채 남고, **이 스크립트가 그
잔류를 쓸어 간다.**

**어떻게 찾는가.** `users` 에 `purge_started_at` 이 찍힌 행이 곧 *시작됐지만 안 끝난*
계정이다(성공하면 행 자체가 사라진다). 그 각각에 대해 **계정 축 두 규칙**을 다시 돌고,
남은 프로젝트가 있으면 프로젝트 축 reconciler 가 쓸 수 있도록 **이름만 보고한다** —
프로젝트 파괴 그래프를 여기서 두 번째로 구현하지 않는다(`purge_reconciler.py` 가 그
일을 하고, 이 스크립트는 계정 축만 본다).

**순서**: 계정 축 스윕 → 사용자명 묘비 확인 → 계정 행 삭제. 묘비가 없으면 **지우지
않는다** — 이름 한 값을 남기는 것이 오너 결정이라, 묘비 없이 행을 지우면 원장이
영원히 id 로만 답한다.

기본은 **dry-run** 이다. 파기는 비가역이므로 `--apply` 를 명시해야 지운다.

    docker compose run --rm --no-deps application \\
      python scripts/account_purge_reconciler.py            # 조사만
    ... python scripts/account_purge_reconciler.py --apply  # 실제 정리
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pymongo import MongoClient

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
from services.application.app.deletion.account_axis_sweep import (
    MongoAccountAxisSweeper,
)
from services.application.app.deletion.user_name_history import document_id
from services.application.app.deletion.user_name_history_mongo import (
    COLLECTION as USER_NAME_HISTORY,
)

_USERS = "users"
_PROJECTS = "projects"


def stalled_user_ids(db) -> list[str]:
    """파기가 시작됐지만 안 끝난 계정. 성공하면 행이 사라지므로 이 질의가 곧 정의다."""
    return sorted(
        doc["_id"] for doc in db[_USERS].find(
            {"purge_started_at": {"$ne": None}}, {"_id": 1}
        )
    )


def leftover_projects(db, user_id: str) -> list[str]:
    return sorted(
        doc["_id"] for doc in db[_PROJECTS].find({"owner_id": user_id}, {"_id": 1})
    )


def reconcile(db, user_id: str, *, sweeper) -> dict:
    projects = leftover_projects(db, user_id)
    swept = sweeper.sweep(user_id)
    has_tombstone = db[USER_NAME_HISTORY].find_one(
        {"_id": document_id(user_id)}, {"_id": 1}
    ) is not None
    removed_user_row = False
    if not projects and has_tombstone:
        # 프로젝트가 남아 있으면 계정 행을 지우지 않는다 — 그 행이 `owner_id` 로
        # 잔여를 찾는 유일한 실마리다. 묘비가 없어도 지우지 않는다(위 머리말).
        removed_user_row = db[_USERS].delete_one({"_id": user_id}).deleted_count == 1
    return {
        "leftover_projects": projects,
        "swept": swept,
        "has_username_tombstone": has_tombstone,
        "removed_user_row": removed_user_row,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="실제로 지운다. 없으면 조사만 하고 아무것도 바꾸지 않는다(기본).",
    )
    args = parser.parse_args(argv)

    uri = os.environ.get("CORE_SOT_MONGO_URI", "mongodb://localhost:27520")
    db_name = os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME)
    client = MongoClient(uri)
    try:
        db = client[db_name]
        stalled = stalled_user_ids(db)
        summary: dict = {
            "mode": "apply" if args.apply else "dry-run",
            # 살아 있는 쪽의 규모를 요약이 보여 준다 — 삭제 도구라 "이만큼은 안
            # 건드린다"가 안 보이면 실행하기 무섭다(purge_reconciler 의 선례).
            "live_user_count": db[_USERS].count_documents(
                {"purge_started_at": None}
            ),
            "stalled_user_ids": stalled,
        }
        if stalled and not args.apply:
            summary["would_reconcile"] = {
                user_id: {
                    "leftover_projects": leftover_projects(db, user_id),
                    "has_username_tombstone": db[USER_NAME_HISTORY].find_one(
                        {"_id": document_id(user_id)}, {"_id": 1}
                    ) is not None,
                }
                for user_id in stalled
            }
        if stalled and args.apply:
            sweeper = MongoAccountAxisSweeper(client, db_name=db_name)
            summary["reconciled"] = {
                user_id: reconcile(db, user_id, sweeper=sweeper)
                for user_id in stalled
            }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        client.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
