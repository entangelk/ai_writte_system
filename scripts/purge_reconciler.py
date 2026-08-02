"""파기된 project 의 잔류 데이터(고아)를 찾아 정리한다 — D8-6 잔여 슬라이스.

**무엇을 고치는가.** `POST /admin/projects/{id}/purge` 는 core_sot(8컬렉션)을 먼저 지우고
derived(10컬렉션)와 outbox enqueue 를 뒤이어 한다. 그 사이에서 mongo 장애가 나면 전역 handler 가
503 을 내는데, **재시도가 불가능하다** — core_sot 이 이미 비어 있어 두 번째 호출은
`NotFound` → **404** 로 끝나고, derived 는 영원히 남는다. endpoint docstring 과 SoT 는 "재시도
(멱등)"라고 적었지만 그것은 **derived 단계에서 실패했을 때는 성립하지 않는다**.

잔류물을 "무해한 ghost"로 부를 수 없다: `llm_call_audits` 에는 그 project 의 **프롬프트 본문**이
남고, `writing_drafts_scratch` 에는 **원고 후보**가 남는다. 파기를 요청받은 데이터가 남아 있는
것이므로 D5 "부분 삭제는 조용한 고아" 금지의 위반이다.

**어떻게 찾는가.** 컬렉션 목록을 이 파일에 적지 않는다 — **DB 에서 발견한다.** `project_id`
필드를 쓰는 모든 컬렉션에서 그 값들을 모으고, `projects` 컬렉션에 살아 있지 않은 값을 고아로
본다. 새 derived 컬렉션이 생겨도 자동으로 덮이므로, 이 스크립트가 **로스터와 함께 낡지 않는다**
(2026-08-01 스크립트 로그인 슬라이스의 교훈: 목록을 믿지 말고 디렉터리/DB 를 읽어라).

**순서가 중요하다.** 삭제를 먼저 하고 outbox enqueue 를 마지막에 한다. `index_sync_outbox` 도
`project_id` 를 가진 컬렉션이라 삭제 대상에 포함되는데(죽은 project 를 향한 잔여 작업이므로
지우는 것이 맞다), 먼저 enqueue 하면 방금 넣은 PROJECT_PURGED 를 스스로 지운다.

기본은 **dry-run** 이다. 파기는 비가역이므로 `--apply` 를 명시해야 지운다.

사용법 (컨테이너 안에서 실행하는 것이 표준 — 저장소는 loopback 바인드다):

    docker compose run --rm --no-deps -v "$PWD/scripts:/app/scripts" -e PYTHONPATH=/app \\
      application python scripts/purge_reconciler.py            # 조사만
    ... python scripts/purge_reconciler.py --apply              # 실제 파기

앱 route 를 치지 않으므로 세션 로그인이 필요 없다(워커와 같은 Mongo 직접 접근 — D8-7 사안).
"""

from __future__ import annotations

import argparse
import json
import os

from pymongo import MongoClient

from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME

_PROJECT_ID_FIELD = "project_id"

# core_sot 의 project 정본. 여기 `_id` 로 살아 있는 project 만 살아 있는 것이다.
_PROJECTS_COLLECTION = "projects"


def _collections_scoped_by_project(db) -> list[str]:
    """`project_id` 필드를 실제로 쓰는 컬렉션 이름 (DB 에서 발견 — 하드코딩 없음)."""

    found = []
    for name in db.list_collection_names():
        if name == _PROJECTS_COLLECTION:
            continue
        if db[name].find_one({_PROJECT_ID_FIELD: {"$exists": True}}, {"_id": 1}):
            found.append(name)
    return sorted(found)


def _orphan_project_ids(db, collections: list[str]) -> dict[str, list[str]]:
    """고아 project_id → 그것이 남아 있는 컬렉션들."""

    live = {doc["_id"] for doc in db[_PROJECTS_COLLECTION].find({}, {"_id": 1})}
    orphans: dict[str, list[str]] = {}
    for name in collections:
        for project_id in db[name].distinct(_PROJECT_ID_FIELD):
            if project_id is None or project_id in live:
                continue
            orphans.setdefault(project_id, []).append(name)
    return orphans


def _purge(db, project_id: str, collections: list[str]) -> dict[str, int]:
    deleted: dict[str, int] = {}
    for name in collections:
        result = db[name].delete_many({_PROJECT_ID_FIELD: project_id})
        if result.deleted_count:
            deleted[name] = result.deleted_count
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="실제로 지운다. 없으면 조사만 하고 아무것도 바꾸지 않는다(기본).",
    )
    args = parser.parse_args()

    uri = os.environ.get("CORE_SOT_MONGO_URI", "mongodb://localhost:27520")
    db_name = os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME)
    client = MongoClient(uri)
    try:
        db = client[db_name]
        collections = _collections_scoped_by_project(db)
        orphans = _orphan_project_ids(db, collections)

        summary: dict = {
            "mode": "apply" if args.apply else "dry-run",
            # 운영자가 "이만큼은 안 건드린다"를 요약만 보고 확인할 수 있어야 한다 —
            # 삭제 도구라 살아 있는 쪽의 규모가 보이지 않으면 실행하기 무섭다
            # (2026-08-02 독립 검증 hardening #3).
            "live_project_count": db[_PROJECTS_COLLECTION].count_documents({}),
            "scanned_collections": collections,
            "orphan_project_ids": sorted(orphans),
            "orphans": {
                project_id: sorted(names) for project_id, names in sorted(orphans.items())
            },
        }

        if args.apply and orphans:
            from services.application.app.indexing.mongo_repository import (
                MongoIndexSyncRepository,
            )
            from services.application.app.indexing.service import IndexSyncOutboxService

            outbox = IndexSyncOutboxService(
                MongoIndexSyncRepository(client, db_name=db_name)
            )
            purged: dict[str, dict[str, int]] = {}
            for project_id in sorted(orphans):
                # 삭제가 먼저다. outbox 도 project_id 를 가진 컬렉션이라 삭제 대상이고,
                # enqueue 를 먼저 하면 방금 넣은 PROJECT_PURGED 를 스스로 지운다.
                purged[project_id] = _purge(db, project_id, collections)
                # vector/lexical 5백엔드는 worker 의 PROJECT_PURGED drain 이 지운다(6c).
                outbox.enqueue_project_purged(project_id=project_id)
            summary["purged"] = purged
            summary["enqueued_project_purged"] = sorted(orphans)

        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        client.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
