"""정산된 유료 응답의 재생 저장소 — S-1 D1 의 국소 C (오너 2026-09-05).

대상은 **응답을 지속하지 않는 유료 경로**(``writing_report`` 하나)다. 다른 BODY 키
경로는 결과가 서버에 남아 상태 재조회로 회복되지만, 이 경로는 성공 응답이 유실되면
결과를 되돌릴 수 없다 — 그래서 정산 시점에 응답 본문을 저장해 두고 같은 키의
재제출은 **저장 응답을 재생**한다. 재생은 provider 를 다시 부르지 않고 과금도
새로 생기지 않는다(이미 그 요청은 세었다 — 8.0 B5).

TTL 은 24시간이다. 정직한 재시도(네트워크 유실)는 분 단위이고, 그보다 오래된
재제출은 애초에 드물다 — TTL 이 지나면 재제출은 409 로 답한다(무료 재실행이
아니다). 인덱스는 **청소부**이지 정책이 아니다(``signup_attempts`` 와 같은 자세).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Callable, Protocol

from pymongo import MongoClient

from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME

#: 재생 보증 창. 정직한 재시도 창(분)보다 넉넉히, 원장 행의 창(일·주)보다 짧게.
DEFAULT_REPLAY_TTL_SECONDS = 86400

_COLLECTION = "quota_replay_responses"


class ReplayResponseRepository(Protocol):
    def get(self, key: str) -> bytes | None: ...
    def put(self, key: str, body: bytes) -> None: ...


def replay_key(user_id: str, action: str, dedupe_key: str) -> str:
    """저장 축 — 원장 유니크 인덱스와 같은 세 축을 하나의 ``_id`` 로 접는다."""

    return f"{user_id}:{action}:{dedupe_key}"


class InMemoryReplayResponseRepository:
    """TTL 은 읽기마다 청소한다(가드 저장소들과 같은 자세 — 별도 수명이 없다)."""

    def __init__(
        self,
        *,
        ttl_seconds: int = DEFAULT_REPLAY_TTL_SECONDS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._docs: dict[str, tuple[bytes, datetime]] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
        self._clock = clock or (lambda: datetime.now(UTC))

    def get(self, key: str) -> bytes | None:
        self._sweep()
        entry = self._docs.get(key)
        return None if entry is None else entry[0]

    def put(self, key: str, body: bytes) -> None:
        self._docs[key] = (body, self._clock())

    def _sweep(self) -> None:
        now = self._clock()
        stale = [
            key for key, (_, at) in self._docs.items() if at + self._ttl <= now
        ]
        for key in stale:
            del self._docs[key]


class MongoReplayResponseRepository:
    def __init__(
        self,
        client: MongoClient,
        *,
        db_name: str = DEFAULT_DB_NAME,
        ttl_seconds: int = DEFAULT_REPLAY_TTL_SECONDS,
    ) -> None:
        self._docs = client[db_name][_COLLECTION]
        self._docs.create_index(
            "stored_at", expireAfterSeconds=max(1, ttl_seconds)
        )

    @classmethod
    def from_uri(
        cls, uri: str, *, db_name: str = DEFAULT_DB_NAME,
        ttl_seconds: int = DEFAULT_REPLAY_TTL_SECONDS,
    ):
        return cls(
            MongoClient(uri), db_name=db_name, ttl_seconds=ttl_seconds
        )

    def get(self, key: str) -> bytes | None:
        doc = self._docs.find_one({"_id": key})
        return None if doc is None else bytes(doc["payload"])

    def put(self, key: str, body: bytes) -> None:
        self._docs.update_one(
            {"_id": key},
            {"$set": {"payload": body, "stored_at": datetime.now(UTC)}},
            upsert=True,
        )
