"""Mongo repository for signup attempt records (Phase S-3, 2026-09-05).

``_id`` 는 :mod:`.client_ip` 가 해석한 발신 주소 — 이 가드의 축이다. 행 하나가
IP 하나이고, 창이 지나면 서비스가 읽는 자리에서 새 창으로 덮어쓴다.

**여기에는 TTL 인덱스를 둔다** — ``login_failures`` 와 갈리는 지점이라 이유를
적는다. 로그인 축은 *사람이 타이핑한 username* 이라 행 집합이 사실상 유한하지만,
이쪽 축은 **인터넷의 발신 주소**라 상한이 없다. 정리를 읽기 시점에만 하면 다시는
오지 않는 주소의 행이 영구히 쌓여, 이 가드가 막으려던 무한 적재를 가드 자신이
만들어 낸다(감사 §A.11-(2)와 같은 모양).

TTL 은 창보다 **넉넉히** 잡는다(``expireAfterSeconds`` = 창 × 24, 최소 1일).
정확히 창에 맞추면 ``AUTH_SIGNUP_WINDOW_SECONDS`` 를 늘린 배포에서 인덱스가
서비스보다 먼저 행을 지워 카운터가 조용히 리셋된다 — 인덱스는 **청소부**이지
정책이 아니고, 만료 판단은 서비스가 계속 쥔다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pymongo import MongoClient

from services.application.app.auth.signup_guard import AttemptRecord
from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME

_COLLECTION = "signup_attempts"
# 창의 24배(최소 1일). 아래 인덱스는 서비스의 만료 판단을 대신하지 않는다.
_TTL_MULTIPLIER = 24
_TTL_FLOOR_SECONDS = 86400


def _aware(value: datetime) -> datetime:
    # sessions_mongo·login_guard_mongo 와 같은 재라벨링: BSON 날짜는 naive 로
    # 돌아오고 서비스는 aware now() 와 비교한다. 섞이면 TypeError 가 하필
    # **창 판정 자리**에서 터진다.
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class MongoAttemptRecordRepository:
    def __init__(
        self,
        client: MongoClient,
        *,
        db_name: str = DEFAULT_DB_NAME,
        window_seconds: int,
    ) -> None:
        self._records = client[db_name][_COLLECTION]
        self._records.create_index(
            "window_started_at",
            expireAfterSeconds=max(
                _TTL_FLOOR_SECONDS, window_seconds * _TTL_MULTIPLIER
            ),
        )

    @classmethod
    def from_uri(
        cls, uri: str, *, db_name: str = DEFAULT_DB_NAME, window_seconds: int
    ):
        return cls(
            MongoClient(uri), db_name=db_name, window_seconds=window_seconds
        )

    def get(self, client_ip: str) -> AttemptRecord | None:
        doc = self._records.find_one({"_id": client_ip})
        if doc is None:
            return None
        return AttemptRecord(
            attempts=doc["attempts"],
            window_started_at=_aware(doc["window_started_at"]),
        )

    def put(self, client_ip: str, record: AttemptRecord) -> None:
        self._records.update_one(
            {"_id": client_ip},
            {"$set": {
                "attempts": record.attempts,
                "window_started_at": record.window_started_at,
            }},
            upsert=True,
        )
