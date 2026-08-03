"""`request_quota_policies` Mongo 어댑터 (Phase 8 Slice 8.1).

``_id`` 가 곧 ``user_id`` 다 — 회원당 최대 한 행이라는 P1 계약을 데이터베이스가
직접 강제하게 하는 가장 짧은 방법이고, 조회 축도 그것 하나뿐이라 **추가 인덱스가
없다**. 다른 축(예: 정지된 회원 목록)이 실제로 생기면 그때 만든다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pymongo import MongoClient

from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
from services.application.app.quota.policy import (
    PendingLimits,
    QuotaLimits,
    QuotaPolicy,
    QuotaStatus,
)

COLLECTION = "request_quota_policies"


def _aware(value: datetime) -> datetime:
    """BSON 날짜는 naive 로 돌아온다(pymongo 기본이 tz_aware 가 아니다).

    P6의 발효 판정이 aware ``datetime.now(UTC)`` 와 비교하므로, 여기서 UTC 를 다시
    붙이지 않으면 실 Mongo 에서만 ``TypeError`` 가 난다 — fake collection 은 넣은
    그대로(aware) 돌려주므로 이 결함을 재현하지 못한다(세션 저장소의 같은 함정,
    2026-07-27 실측). BSON 은 UTC 를 담으므로 재부착은 변환이 아니라 재명명이다.
    """

    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class MongoQuotaPolicyRepository:
    def __init__(self, client: MongoClient, *, db_name: str = DEFAULT_DB_NAME) -> None:
        self._policies = client[db_name][COLLECTION]

    @classmethod
    def from_uri(cls, uri: str, *, db_name: str = DEFAULT_DB_NAME):
        return cls(MongoClient(uri), db_name=db_name)

    def get(self, user_id: str) -> QuotaPolicy | None:
        doc = self._policies.find_one({"_id": user_id})
        return None if doc is None else _entry(doc)

    def upsert(self, policy: QuotaPolicy) -> None:
        self._policies.replace_one(
            {"_id": policy.user_id}, _doc(policy), upsert=True
        )


def _limits_doc(limits: QuotaLimits) -> dict:
    return {
        "daily_limit": limits.daily_limit,
        "weekly_limit": limits.weekly_limit,
        "status": limits.status.value,
    }


def _limits(doc: dict) -> QuotaLimits:
    return QuotaLimits(
        daily_limit=doc["daily_limit"],
        weekly_limit=doc["weekly_limit"],
        status=QuotaStatus(doc["status"]),
    )


def _doc(policy: QuotaPolicy) -> dict:
    return {
        "_id": policy.user_id,
        "limits": _limits_doc(policy.limits),
        "pending": (
            None
            if policy.pending is None
            else {
                "limits": _limits_doc(policy.pending.limits),
                "effective_at": policy.pending.effective_at,
            }
        ),
        "updated_at": policy.updated_at,
    }


def _entry(doc: dict) -> QuotaPolicy:
    pending = doc.get("pending")
    return QuotaPolicy(
        user_id=doc["_id"],
        limits=_limits(doc["limits"]),
        pending=(
            None
            if pending is None
            else PendingLimits(
                limits=_limits(pending["limits"]),
                effective_at=_aware(pending["effective_at"]),
            )
        ),
        updated_at=_aware(doc["updated_at"]),
    )
