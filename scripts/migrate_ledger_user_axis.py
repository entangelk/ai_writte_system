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
결과다. 인덱스는 키가 바뀌므로 **같은 이름으로 다시 만들 수 없다** — MongoDB 가
**code=86** 으로 거부한다(2026-09-07 독립 검증 실측). 그래서 옛 인덱스를 지우고 어댑터가
새로 만들게 둔다(``MongoUsageLedgerRepository.__init__`` 이 생성한다). 이 때문에
**마이그레이션은 앱 기동의 필요조건**이지 권고가 아니다.

**★ 인덱스 제거는 문서 개명과 독립이다**(독립 검증 H1). 종전 구현은 옮길 문서가 없으면
조기 반환했는데, 개명과 제거 **사이에 프로세스가 죽으면** 재실행이 그 반환에 걸려 옛
인덱스를 영영 안 지웠다 — 그리고 그 상태의 앱 기동이 code=86 으로 깨진다. 그래서 지울
대상은 게이트가 아니라 **실제 인덱스 키**로 고른다: 키에 ``user_id`` 가 들어간 인덱스만
지운다. 어댑터가 새 키로 다시 만든 동명 인덱스는 키가 달라 대상이 아니다.

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

#: 옮기는 필드. 인덱스가 이것을 키로 쓰면 옛 인덱스다.
OLD_FIELD = "user_id"
NEW_FIELD = "target_user_id"


def stale_index_names(collection) -> list[str]:
    """키에 옛 필드가 들어간 인덱스 이름 — **이름 목록을 손으로 들지 않는다.**

    이름으로 고르면 어댑터가 **새 키로 다시 만든 동명 인덱스**까지 지운다. 키로
    고르면 그 둘이 구분되고, 나중에 인덱스가 늘어도 목록이 뒤처지지 않는다.
    """
    return [
        index["name"]
        for index in collection.list_indexes()
        if OLD_FIELD in dict(index.get("key", {}))
    ]


def migrate(collection, *, dry_run: bool = False) -> dict[str, object]:
    pending = collection.count_documents({OLD_FIELD: {"$exists": True}})
    stale = stale_index_names(collection)
    report: dict[str, object] = {
        "collection": COLLECTION,
        "documents_with_old_field": pending,
        "stale_indexes": stale,
        "dry_run": dry_run,
    }
    if dry_run:
        report["renamed"] = 0
        report["dropped_indexes"] = []
        return report

    renamed = 0
    if pending:
        renamed = collection.update_many(
            {OLD_FIELD: {"$exists": True}},
            {"$rename": {OLD_FIELD: NEW_FIELD}},
        ).modified_count
    report["renamed"] = renamed

    # 이름은 `list_indexes` 에서 왔으므로 존재가 보장된다 — 실패는 권한 문제 같은
    # 진짜 오류이니 삼키지 않고 올린다(종전의 `except Exception: continue` 는 그것도
    # 조용히 먹었다).
    for name in stale:
        collection.drop_index(name)
    # 새 키의 인덱스는 어댑터가 만든다(생성 지점을 두 벌로 두지 않는다).
    report["dropped_indexes"] = stale
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
