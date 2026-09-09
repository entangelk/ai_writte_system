"""계정 축 잔여 데이터 발견·파기 — ⓑ 두 규칙 스윕 (계정 탈퇴 Slice 3).

오너 결정 2026-09-09(브리프 ``plans/slice3-withdrawal-purge-daemon-decisions.md``).

## 규칙은 한 문장이다

    ``user_id`` 필드 또는 ``_id`` 로 사용자를 가리키면 **지운다.**
    ``target_user_id`` 로 가리키면 **남긴다.**

컬렉션 목록을 이 파일에 적지 않는다 — **DB 에서 발견한다.** ``purge_reconciler`` 가
프로젝트 축에서 하는 것과 같은 성질이고, 이유도 같다: 손으로 든 목록은 새 컬렉션이
생길 때 조용히 낡는다(이 저장소가 이미 값을 치른 실패 모양).

## 왜 규칙이 **둘**인가 — 프로젝트 축 그대로는 구멍이 난다

프로젝트 축은 ``project_id`` **필드** 하나로 충분했다. 계정 축은 아니다:
``request_quota_policies`` 는 회원당 한 행이라는 계약을 기본 키로 강제해
``_id`` 가 곧 user id 이고 ``user_id`` 필드가 **없다**(2026-09-09 실측). 필드 규칙만
쓰면 회원의 한도·정지 상태가 파기를 살아남는다 — 약속한 삭제가 조용히 안 된 것이라
D5(부분 삭제 = 조용한 고아) 금지에 걸린다.

## ★ `_id` 규칙의 안전 근거는 **id 접두**다

이 스윕은 컬렉션 전건에 ``{"_id": <user id>}`` 를 던진다. 그것이 안전한 이유는
user id 가 ``user:<hex>`` 라 다른 축의 ``_id``(project id · username · client_ip ·
lock key · ``user_name:<id>`` 묘비)와 **겹칠 수 없기** 때문이다. 접두가 바뀌면 그
근거가 사라지므로 셀이 그 사실을 함께 잠근다.

## 남는 것

``request_usage_ledger``(D4 로 ``target_user_id`` 개명) · ``admin_audit_events`` ·
``user_name_history`` 는 어느 규칙에도 안 걸린다 — **그것이 설계다.**
"""

from __future__ import annotations

from pymongo import MongoClient

from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
from services.application.app.deletion.account_purge import NEVER_SWEPT

#: 지우는 축의 필드 이름. 보존 축은 ``target_user_id`` 다(원장·감사·사용자명 묘비).
USER_ID_FIELD = "user_id"


class MongoAccountAxisSweeper:
    def __init__(self, client: MongoClient, *, db_name: str = DEFAULT_DB_NAME) -> None:
        self._db = client[db_name]

    @classmethod
    def from_uri(cls, uri: str, *, db_name: str = DEFAULT_DB_NAME):
        return cls(MongoClient(uri), db_name=db_name)

    def sweep(self, user_id: str) -> dict[str, int]:
        deleted: dict[str, int] = {}
        for name in self._db.list_collection_names():
            if name in NEVER_SWEPT:
                continue
            collection = self._db[name]
            count = collection.delete_many({USER_ID_FIELD: user_id}).deleted_count
            count += collection.delete_one({"_id": user_id}).deleted_count
            if count:
                deleted[name] = count
        return deleted


class InMemoryAccountAxisSweeper:
    """테스트·비-Mongo 조립용. 실 어댑터와 **같은 두 규칙**을 돈다."""

    def __init__(self, collections: dict[str, list[dict]] | None = None) -> None:
        self.collections: dict[str, list[dict]] = collections or {}

    def sweep(self, user_id: str) -> dict[str, int]:
        deleted: dict[str, int] = {}
        for name, docs in self.collections.items():
            if name in NEVER_SWEPT:
                continue
            keep = [
                doc for doc in docs
                if doc.get(USER_ID_FIELD) != user_id and doc.get("_id") != user_id
            ]
            if len(keep) != len(docs):
                deleted[name] = len(docs) - len(keep)
                self.collections[name] = keep
        return deleted
