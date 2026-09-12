"""부분 파기된 계정의 잔류 데이터를 찾아 정리한다 — 계정 탈퇴 Slice 3 의 수습 경로.

**무엇을 고치는가.** 파기 데몬(`account_withdrawal_worker.py`)은 실패하면 그 계정에서
**멈춘다**(D3=ⓐ). 재시도가 수습이 아니기 때문이다 — 파기 본체가 core_sot 을 먼저
지우므로 두 번째 호출은 404 로 끝나고 derived(프롬프트 본문·원고 후보)에 도달하지
못한다. 그래서 실패한 계정은 `purge_started_at` 이 찍힌 채 남고, **이 스크립트가 그
잔류를 쓸어 간다.**

**조건·순서의 본체는 한 벌이다** — Slice 4b(2026-09-12)부터 관리자 operation
(`GET/POST /admin/users/{id}/reconcile`)과 이 스크립트가 같은
`deletion/account_reconcile.py` 를 쓴다. 이 파일은 조립·출력만 한다.

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
from services.application.app.deletion.account_reconcile import (
    AccountReconcileService,
    MongoAccountReconcileRepository,
)


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
        repository = MongoAccountReconcileRepository(client, db_name=db_name)
        service = AccountReconcileService(
            repository, sweeper=MongoAccountAxisSweeper(client, db_name=db_name)
        )
        stalled = repository.stalled_user_ids()
        summary: dict = {
            "mode": "apply" if args.apply else "dry-run",
            # 살아 있는 쪽의 규모를 요약이 보여 준다 — 삭제 도구라 "이만큼은 안
            # 건드린다"가 안 보이면 실행하기 무섭다(purge_reconciler 의 선례).
            "live_user_count": repository.live_user_count(),
            "stalled_user_ids": stalled,
        }
        if stalled and not args.apply:
            survey = service.survey  # dry-run: 파괴 없음
            summary["would_reconcile"] = {
                user_id: {
                    "leftover_projects": survey(user_id).leftover_projects,
                    "has_username_tombstone": (
                        survey(user_id).has_username_tombstone
                    ),
                }
                for user_id in stalled
            }
        if stalled and args.apply:
            reconciled: dict[str, dict] = {}
            for user_id in stalled:
                result = service.reconcile(user_id)
                reconciled[user_id] = {
                    "leftover_projects": result.leftover_projects,
                    "swept": result.swept,
                    "has_username_tombstone": result.has_username_tombstone,
                    "removed_user_row": result.removed_user_row,
                }
            summary["reconciled"] = reconciled
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        client.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
