"""`request_locks` Mongo 어댑터 (Phase 8 Slice 8.2b).

**차지는 연산 하나다**(G3=A). ``find_one_and_update`` 의 필터가 "없거나 만료됐다"를
표현하고, 살아 있는 잠금이 있으면 upsert 가 ``_id`` 중복으로 튕긴다 — 그 예외가 곧
"잠겨 있음"이다. 이 저장소의 생성 job·색인 outbox 차지와 같은 모양이며, 읽고 판단하고
쓰는 형태는 **동시 두 요청이 둘 다 "없음"을 읽으므로** 쓰지 않는다.

**★ TTL 인덱스는 청소용이고 판정에 쓰지 않는다.** Mongo 의 TTL 삭제는 백그라운드
모니터가 **약 60초 주기**로 돌기 때문에, 문서 존재 여부로 판정하면 최소 창 5초가
**최대 1분**이 된다. 그래서 필터가 언제나 ``expires_at`` 을 비교한다. fake collection 은
TTL 을 **흉내 내지 않으며**, 그것이 이 규칙의 증거다(문서가 남아 있는데도 차지에
성공해야 한다).

**저장 문서에는 ``project_id`` 필드가 없다.** 프로젝트 축은 ``_id`` 문자열 안에 들어
있고 별도 필드로 두지 않는다 — purge reconciler 가 ``project_id`` 필드를 가진 컬렉션을
DB 에서 발견해 고아 행을 지우므로(§43D 와 같은 이유), 잠금은 애초에 그 발견에 걸리지
않는다. 잠금은 사실이 아니라 통제라 지워져도 무해하지만, 그렇다고 sweep 대상으로
만들 이유는 없다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pymongo import ASCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
from services.application.app.quota.lock import RequestLock, cooldown_until

COLLECTION = "request_locks"


def _aware(value: datetime | None) -> datetime | None:
    """BSON 날짜는 naive 로 돌아온다 — 원장·세션 저장소와 같은 재부착."""

    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class MongoRequestLockRepository:
    def __init__(self, client: MongoClient, *, db_name: str = DEFAULT_DB_NAME) -> None:
        self._locks = client[db_name][COLLECTION]
        # 키가 곧 `_id` 라(G2=A) 조회 인덱스가 필요 없다. 유일한 인덱스는 **청소용**
        # TTL 이며 판정은 여기에 기대지 않는다.
        self._locks.create_index(
            [("expires_at", ASCENDING)],
            name="request_locks_ttl",
            expireAfterSeconds=0,
        )

    @classmethod
    def from_uri(cls, uri: str, *, db_name: str = DEFAULT_DB_NAME):
        return cls(MongoClient(uri), db_name=db_name)

    def claim(self, lock: RequestLock, *, now: datetime) -> RequestLock:
        try:
            doc = self._locks.find_one_and_update(
                {"_id": lock.key, "expires_at": {"$lte": now}},
                {"$set": _claim_fields(lock)},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            return lock_entry(doc)
        except DuplicateKeyError:
            existing = self._locks.find_one({"_id": lock.key})
        # 막은 잠금이 곧바로 사라지는 경우는 TTL 이 **만료된** 문서만 지우므로 사실상
        # 없다. 그래도 도달하면 "잠금이 없다"가 사실이므로 차지한 것으로 본다.
        return lock_entry(existing) if existing is not None else lock

    def force_claim(self, lock: RequestLock) -> None:
        self._locks.replace_one({"_id": lock.key}, _doc(lock), upsert=True)

    def release(
        self, key: str, *, holder: str, now: datetime, minimum_window: timedelta
    ) -> bool:
        doc = self._locks.find_one({"_id": key})
        if doc is None or doc.get("holder") != holder:
            return False
        # `claimed_at` 은 그 holder 에게 불변이므로 읽고 쓰는 사이에 바뀌지 않는다.
        # 소유권 자체는 갱신 필터가 다시 확인한다 — 그 사이 강제 재차지가 일어났으면
        # 아무 문서도 안 맞고, 새 주인의 잠금은 그대로 남는다(§0.4).
        result = self._locks.update_one(
            {"_id": key, "holder": holder},
            {"$set": {
                "released_at": now,
                "expires_at": cooldown_until(
                    _aware(doc["claimed_at"]), now, minimum_window),
            }},
        )
        return result.matched_count == 1


def _claim_fields(lock: RequestLock) -> dict:
    return {
        "holder": lock.holder,
        "claimed_at": lock.claimed_at,
        "expires_at": lock.expires_at,
        "released_at": lock.released_at,
    }


def _doc(lock: RequestLock) -> dict:
    return {"_id": lock.key, **_claim_fields(lock)}


def lock_entry(doc: dict) -> RequestLock:
    return RequestLock(
        key=doc["_id"],
        holder=doc["holder"],
        claimed_at=_aware(doc["claimed_at"]),
        expires_at=_aware(doc["expires_at"]),
        released_at=_aware(doc["released_at"]),
    )
