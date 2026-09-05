"""`request_usage_ledger` Mongo 어댑터 (Phase 8 Slice 8.2).

**필드 이름 하나가 계약이다**: 프로젝트 축은 ``target_project_id`` 이며 절대
``project_id`` 가 아니다. purge reconciler 는 컬렉션 목록을 하드코딩하지 않고
``project_id`` 필드를 가진 컬렉션을 **DB 에서 발견해** 고아 행을 지우므로, 그 이름으로
적으면 **project 영구 삭제가 과금 기록을 지운다** — 오너 결정("삭제돼도 사용 기록은
남는다")과 정면으로 어긋난다.

**유니크 인덱스는 부분(partial) 인덱스여야 한다.** 조정 행에는 ``action``·
``dedupe_key`` 가 아예 없고(L5: 두 종류의 필드 구성이 겹치지 않는다), Mongo 는 없는
필드를 ``null`` 로 취급하므로 전체 인덱스로 걸면 **두 번째 조정 행이 중복 키로
거부된다.** ``kind="usage"`` 로 제한해 그 함정을 피한다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pymongo import ASCENDING, MongoClient
from pymongo.errors import DuplicateKeyError

from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
from services.application.app.quota.ledger import (
    AdjustmentEntry,
    DuplicateUsageEntry,
    LedgerEntryKind,
    UsageEntry,
)

COLLECTION = "request_usage_ledger"


def _aware(value: datetime) -> datetime:
    """BSON 날짜는 naive 로 돌아온다 — 세션 저장소와 같은 재부착(재명명)."""

    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class MongoUsageLedgerRepository:
    def __init__(self, client: MongoClient, *, db_name: str = DEFAULT_DB_NAME) -> None:
        self._entries = client[db_name][COLLECTION]
        # 중복 방지(L2=A). `action` 이 키에 있어야 한 흐름의 서로 다른 유료 동작이
        # 같은 클라이언트 uuid 를 공유해도 각각 세어진다.
        self._entries.create_index(
            [("user_id", ASCENDING), ("action", ASCENDING),
             ("dedupe_key", ASCENDING)],
            name="request_usage_ledger_dedupe_unique",
            unique=True,
            partialFilterExpression={"kind": LedgerEntryKind.USAGE.value},
        )
        # 집계(L3=A) — 잔여는 세어서 얻는다.
        self._entries.create_index(
            [("user_id", ASCENDING), ("daily_key", ASCENDING)],
            name="request_usage_ledger_by_user_day",
        )
        self._entries.create_index(
            [("user_id", ASCENDING), ("weekly_key", ASCENDING)],
            name="request_usage_ledger_by_user_week",
        )

    @classmethod
    def from_uri(cls, uri: str, *, db_name: str = DEFAULT_DB_NAME):
        return cls(MongoClient(uri), db_name=db_name)

    def add_usage(self, entry: UsageEntry) -> None:
        try:
            self._entries.insert_one(_usage_doc(entry))
        except DuplicateKeyError as exc:
            raise DuplicateUsageEntry(entry.dedupe_key) from exc

    def add_adjustment(self, entry: AdjustmentEntry) -> None:
        self._entries.insert_one(_adjustment_doc(entry))

    def has_usage(self, user_id: str, *, action: str, dedupe_key: str) -> bool:
        # 유니크 인덱스와 같은 세 축 + kind 제한(조정 행은 null 키로 오탐한다 —
        # 부분 인덱스의 함정이 여기서도 같은 모양으로 성립한다).
        return self._entries.find_one({
            "user_id": user_id,
            "action": action,
            "dedupe_key": dedupe_key,
            "kind": LedgerEntryKind.USAGE.value,
        }) is not None

    def count_usage(self, user_id: str, *, window_field: str, window_key: str) -> int:
        return self._entries.count_documents({
            "user_id": user_id,
            window_field: window_key,
            "kind": LedgerEntryKind.USAGE.value,
        })

    def sum_adjustments(
        self, user_id: str, *, window_field: str, window_key: str
    ) -> int:
        cursor = self._entries.find({
            "user_id": user_id,
            window_field: window_key,
            "kind": LedgerEntryKind.ADJUSTMENT.value,
        })
        return sum(doc["delta"] for doc in cursor)


def _usage_doc(entry: UsageEntry) -> dict:
    return {
        "_id": entry.id,
        "kind": LedgerEntryKind.USAGE.value,
        "user_id": entry.user_id,
        "target_project_id": entry.target_project_id,
        "action": entry.action,
        "dedupe_key": entry.dedupe_key,
        "daily_key": entry.daily_key,
        "weekly_key": entry.weekly_key,
        "at": entry.at,
    }


def _adjustment_doc(entry: AdjustmentEntry) -> dict:
    return {
        "_id": entry.id,
        "kind": LedgerEntryKind.ADJUSTMENT.value,
        "user_id": entry.user_id,
        "target_project_id": entry.target_project_id,
        "delta": entry.delta,
        "reason": entry.reason,
        "admin_user_id": entry.admin_user_id,
        "daily_key": entry.daily_key,
        "weekly_key": entry.weekly_key,
        "at": entry.at,
    }


def usage_entry(doc: dict) -> UsageEntry:
    return UsageEntry(
        id=doc["_id"], user_id=doc["user_id"],
        target_project_id=doc["target_project_id"], action=doc["action"],
        dedupe_key=doc["dedupe_key"], daily_key=doc["daily_key"],
        weekly_key=doc["weekly_key"], at=_aware(doc["at"]),
    )


def adjustment_entry(doc: dict) -> AdjustmentEntry:
    return AdjustmentEntry(
        id=doc["_id"], user_id=doc["user_id"],
        target_project_id=doc["target_project_id"], delta=doc["delta"],
        reason=doc["reason"], admin_user_id=doc["admin_user_id"],
        daily_key=doc["daily_key"], weekly_key=doc["weekly_key"],
        at=_aware(doc["at"]),
    )
