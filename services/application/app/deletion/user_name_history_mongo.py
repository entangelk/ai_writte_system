"""``user_name_history`` Mongo 어댑터 (계정 탈퇴 Slice 3).

``_id`` 는 ``user_name:<user id>`` 이고 문서는 ``target_user_id`` 필드를 든다 —
둘 다 의도적이며 이유는 [`user_name_history.py`](user_name_history.py) 머리말에 있다.
**``user_id`` 필드를 쓰면 파기 데몬이 이 컬렉션을 지운다**(그것이 목적의 정반대다).
"""

from __future__ import annotations

from datetime import UTC, datetime

from pymongo import MongoClient

from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
from services.application.app.deletion.user_name_history import (
    UserNameSnapshot,
    document_id,
)

COLLECTION = "user_name_history"


def _aware(value: datetime) -> datetime:
    # pymongo 는 client 가 tz_aware 가 아니면 BSON 날짜를 naive 로 돌려준다. 섞이면
    # 비교 자리에서 TypeError 가 나는데 fake collection 은 넣은 그대로 주므로 그것을
    # 재현하지 못한다(HANDOFF 함정 · project_name_history 와 같은 재라벨링).
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class MongoUserNameHistoryRepository:
    def __init__(self, client: MongoClient, *, db_name: str = DEFAULT_DB_NAME) -> None:
        self._names = client[db_name][COLLECTION]

    @classmethod
    def from_uri(cls, uri: str, *, db_name: str = DEFAULT_DB_NAME):
        return cls(MongoClient(uri), db_name=db_name)

    def put(self, snapshot: UserNameSnapshot) -> None:
        self._names.replace_one(
            {"_id": document_id(snapshot.target_user_id)}, _doc(snapshot), upsert=True
        )

    def get(self, user_id: str) -> UserNameSnapshot | None:
        doc = self._names.find_one({"_id": document_id(user_id)})
        return None if doc is None else _entry(doc)


def _doc(snapshot: UserNameSnapshot) -> dict:
    return {
        "_id": document_id(snapshot.target_user_id),
        "target_user_id": snapshot.target_user_id,
        "username": snapshot.username,
        "purged_at": snapshot.purged_at,
    }


def _entry(doc: dict) -> UserNameSnapshot:
    return UserNameSnapshot(
        target_user_id=doc["target_user_id"],
        username=doc["username"],
        purged_at=_aware(doc["purged_at"]),
    )
