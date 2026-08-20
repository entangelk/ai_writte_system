"""`request_locks` Mongo 어댑터 (Phase 8 Slice 8.2b).

**차지는 연산 하나다**(G3=A). ``find_one_and_update`` 의 필터가 "없거나 만료됐다"를
표현하고, 살아 있는 잠금이 있으면 upsert 가 ``_id`` 중복으로 튕긴다. 이 저장소의 생성
job·색인 outbox 차지와 같은 모양이며, 읽고 판단하고 쓰는 형태는 **동시 두 요청이 둘 다
"없음"을 읽으므로** 쓰지 않는다.

**★ 다만 그 충돌은 "잠겨 있음"의 증거가 아니라 신호다**(2026-08-03 독립 검증 B1이 잡은
결함). 충돌과 그 뒤의 확인 읽기 사이에 원래 요청이 **해제**하거나 TTL 이 문서를 **치울**
수 있다 — 그 상태를 그대로 믿으면 ① 이미 만료된 잠금으로 남을 막거나(거짓 차단) ②
**저장되지 않은 성공**을 돌려주어 다음 요청까지 통과시킨다(= 중복 실행, 이 슬라이스가
막으려던 바로 그것). 그래서 충돌 뒤에는 **살아 있음을 다시 확인**하고, 아니면 원자적
차지를 다시 한다. 재시도는 ``CLAIM_ATTEMPTS`` 번으로 유한하며, 소진되면 예외를 올려
**fail-closed** 한다(중복을 허용하느니 요청을 실패시킨다).

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

import re
from datetime import UTC, datetime, timedelta

from pymongo import ASCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
from services.application.app.quota.lock import (
    RequestLock,
    cooldown_until,
    in_flight_prefix,
)

COLLECTION = "request_locks"

#: 충돌 뒤 상태가 바뀐 것을 확인하면 다시 차지한다. **유한**해야 한다 — 무한 재시도는
#: 잠금 하나 때문에 요청 스레드를 붙잡는다.
CLAIM_ATTEMPTS = 3


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
        conflict: DuplicateKeyError | None = None
        for _attempt in range(CLAIM_ATTEMPTS):
            try:
                doc = self._locks.find_one_and_update(
                    {"_id": lock.key, "expires_at": {"$lte": now}},
                    {"$set": _claim_fields(lock)},
                    upsert=True,
                    return_document=ReturnDocument.AFTER,
                )
                return lock_entry(doc)
            except DuplicateKeyError as exc:
                conflict = exc
            # ★ 충돌은 "잠겨 있음"의 **증거가 아니라 신호**다(2026-08-03 독립 검증 B1).
            # 충돌과 이 읽기 사이에 원래 요청이 해제하거나(냉각까지 지난 경우) TTL 이
            # 문서를 치울 수 있다. 그 상태를 그대로 돌려주면 **만료된 잠금으로 남을
            # 막고**, 없는 문서를 성공으로 날조하면 **저장되지 않은 잠금**이 되어 다음
            # 요청도 통과한다(= 중복 실행). 그래서 살아 있음을 다시 확인하고, 아니면
            # 원자적 차지를 **다시** 한다.
            blocking = self._locks.find_one({"_id": lock.key})
            if blocking is not None and _aware(blocking["expires_at"]) > now:
                return lock_entry(blocking)
        # 유한 번만 돈다. 여기까지 오면 매 시도가 충돌했는데 매 읽기가 "없거나 만료"를
        # 본 것이라 상태를 신뢰할 수 없다 — **fail-closed**: 실수 중복을 허용하느니
        # 요청을 실패시킨다(8.3 이 상태코드를 정한다).
        if conflict is None:
            # `CLAIM_ATTEMPTS` 가 0 이면 시도를 **한 번도 안 하고** 여기 닿는다. 종전
            # 코드는 그 자리에서 `raise None` 으로 `TypeError` 를 냈다 — 잠금을 안 걸고
            # 나가는 것은 같은데 **이유를 말하지 않는** 실패였다. 이 상수는 "유한해야
            # 한다"는 이유로 존재하므로 0 으로 바뀔 수 있고, 그때도 fail-closed 여야
            # 한다(2026-08-20 mypy 가드가 찾았다).
            raise RuntimeError(
                f"CLAIM_ATTEMPTS={CLAIM_ATTEMPTS} 이라 차지를 시도하지 않았다")
        raise conflict

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

    def count_in_flight(self, user_id: str, *, now: datetime) -> int:
        # 8.3 Q3=E. 앵커 정규식이라 ``_id`` 인덱스를 탄다 — 8.2b 의 "추가 인덱스
        # 없음" 계약을 지키는 자리다. **escape 가 필수다**: 회원 id 에 정규식
        # 메타문자가 들어가면 앵커가 다른 회원의 잠금까지 세거나 아무것도 못 센다.
        # 판정은 여기서도 ``expires_at`` 비교다(G3=A) — TTL 은 청소용이라 문서
        # 존재로 세면 최대 1분간 남의 창을 먹는다.
        return self._locks.count_documents({
            "_id": {"$regex": f"^{re.escape(in_flight_prefix(user_id))}"},
            "released_at": None,
            "expires_at": {"$gt": now},
        })


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
