"""사용량 원장의 소유 축을 ``user_id`` → ``target_user_id`` 로 옮긴다 (D4).

**왜 개명하는가.** 이 저장소에서 **파기 대상의 표식은 필드 이름**이다 —
``scripts/purge_reconciler.py`` 는 ``project_id`` 필드를 **가진** 컬렉션을 DB 에서
발견해 고아를 쓸어 간다(판정은 ``find_one({...: {"$exists": True}})``, **표본 한 건**).
그래서 살아남아야 하는 원장은 프로젝트 축을 ``target_project_id`` 로 개명해 그 쓸이를
피했다(8.2 L1=B).

계정 탈퇴 파기(``plans/account-withdrawal-implementation-phases.md``)가 열리면 **사용자
축 reconciler** 가 같은 방식으로 생긴다. 그때 원장이 ``user_id`` 를 들고 있으면 통째로
쓸려 가는데, 오너 결정은 *"탈퇴해도 사용량 원장은 남긴다"* 다(2026-09-07). 이 스크립트가
그 문을 미리 닫는다.

**멱등하다.** 이미 옮긴 문서는 건드리지 않고(``user_id`` 가 없다), 두 번 돌려도 같은
결과다. 인덱스는 키가 바뀌므로 **같은 이름으로 다시 만들 수 없다** — 옛 인덱스를 지우고
어댑터가 새로 만들게 둔다(``MongoUsageLedgerRepository.__init__`` 이 생성한다).

    python scripts/migrate_ledger_user_axis.py            # 실제 적용
    python scripts/migrate_ledger_user_axis.py --dry-run  # 셈만
"""

from __future__ import annotations

import argparse
import json
import os

from pymongo import MongoClient

from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
from services.application.app.quota.ledger_mongo import COLLECTION

#: 키가 ``user_id`` 로 잡혀 있던 옛 인덱스들. 이름을 재사용하려면 먼저 지워야 한다.
_STALE_INDEXES = (
    "request_usage_ledger_dedupe_unique",
    "request_usage_ledger_by_user_day",
    "request_usage_ledger_by_user_week",
)


def migrate(collection, *, dry_run: bool = False) -> dict[str, object]:
    pending = collection.count_documents({"user_id": {"$exists": True}})
    report: dict[str, object] = {
        "collection": COLLECTION,
        "documents_with_old_field": pending,
        "dry_run": dry_run,
    }
    if dry_run or pending == 0:
        report["renamed"] = 0
        report["dropped_indexes"] = []
        return report

    result = collection.update_many(
        {"user_id": {"$exists": True}},
        {"$rename": {"user_id": "target_user_id"}},
    )
    report["renamed"] = result.modified_count

    dropped = []
    for name in _STALE_INDEXES:
        try:
            collection.drop_index(name)
        except Exception:  # noqa: BLE001 - 없으면 지울 것도 없다
            continue
        dropped.append(name)
    # 새 키의 인덱스는 어댑터가 만든다(생성 지점을 두 벌로 두지 않는다).
    report["dropped_indexes"] = dropped
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    uri = os.environ.get("CORE_SOT_MONGO_URI", "mongodb://localhost:27520")
    db_name = os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME)
    client = MongoClient(uri)
    try:
        report = migrate(client[db_name][COLLECTION], dry_run=args.dry_run)
    finally:
        client.close()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
