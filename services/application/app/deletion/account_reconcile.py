"""계정 탈퇴 Slice 4b — 부분 파기 계정의 잔여 조사·정리 본체(한 벌).

관리자 operation(``GET/POST /admin/users/{id}/reconcile``)과 수습 스크립트
(``scripts/account_purge_reconciler.py``)가 **같은 이 모듈**을 쓴다 — 파기 본체를
두 벌로 만들지 않는다는 Slice 3 계약 주의 ⓕ 와 같은 정신. 이 모듈이 오기 전에는
본체가 스크립트에 있었고, 이관이 그 역할을 뒤집는다(스크립트는 조립·출력만).

## 조건·순서는 스크립트가 세운 그대로다

    조사(잔여 프로젝트·사용자명 묘비) → 계정 축 두 규칙 스윕 →
    (프로젝트 잔여 없음 + 묘비 있음)이면 계정 행 삭제.

프로젝트가 남아 있으면 계정 행을 지우지 않는다 — 그 행이 ``owner_id`` 로 잔여를
찾는 유일한 실마리다. 묘비가 없어도 지우지 않는다(원장이 영원히 id 로만 답한다).

## 대상 계정의 정의

``users.purge_started_at`` 이 찍힌 행 — 성공한 파기는 행 자체를 지우므로 스탬프가
곧 *시작됐지만 안 끝난* 계정의 정의다. 라우터는 조사·실행 직전에 이 스탬프를 다시
확인한다(경합: 유예 만료 청구가 dry-run 과 실행 사이에 끼어들 수 있다).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME

_USERS = "users"
_PROJECTS = "projects"


@dataclass(frozen=True, slots=True)
class ReconcileSurvey:
    """dry-run 결과 — 파괴가 없다. 실행 전에 사람이 볼 값이다(①ⓐ·②ⓐ)."""

    leftover_projects: list[str]
    has_username_tombstone: bool


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    """실행 결과 — 스크립트의 출력 키와 같은 넷."""

    leftover_projects: list[str]
    swept: dict[str, int] = field(default_factory=dict)
    has_username_tombstone: bool = False
    removed_user_row: bool = False


class AccountReconcileRepository(Protocol):
    """조사·정리가 저장소에 묻는 넷 + 요약 하나. Mongo/인메모리가 같은 계약."""

    def stalled_user_ids(self) -> list[str]: ...
    def live_user_count(self) -> int: ...
    def projects_owned_by(self, user_id: str) -> list[str]: ...
    def has_username_tombstone(self, user_id: str) -> bool: ...
    def delete_user_row(self, user_id: str) -> bool: ...


class AccountReconcileSweeper(Protocol):
    """``MongoAccountAxisSweeper``/``InMemoryAccountAxisSweeper`` 가 만족하는 계약."""

    def sweep(self, user_id: str) -> dict[str, int]: ...


class AccountReconcileService:
    def __init__(
        self,
        repository: AccountReconcileRepository,
        *,
        sweeper: AccountReconcileSweeper,
    ) -> None:
        self._repo = repository
        self._sweeper = sweeper

    def survey(self, user_id: str) -> ReconcileSurvey:
        return ReconcileSurvey(
            leftover_projects=self._repo.projects_owned_by(user_id),
            has_username_tombstone=self._repo.has_username_tombstone(user_id),
        )

    def reconcile(self, user_id: str) -> ReconcileResult:
        projects = self._repo.projects_owned_by(user_id)
        swept = self._sweeper.sweep(user_id)
        has_tombstone = self._repo.has_username_tombstone(user_id)
        removed_user_row = False
        if not projects and has_tombstone:
            # 프로젝트가 남아 있으면 계정 행을 지우지 않는다 — 그 행이 `owner_id`
            # 로 잔여를 찾는 유일한 실마리다. 묘비가 없어도 지우지 않는다.
            removed_user_row = self._repo.delete_user_row(user_id)
        return ReconcileResult(
            leftover_projects=projects,
            swept=swept,
            has_username_tombstone=has_tombstone,
            removed_user_row=removed_user_row,
        )


class InMemoryAccountReconcileRepository:
    """테스트·비-Mongo 조립용(``InMemoryAccountAxisSweeper`` 선례)."""

    def __init__(
        self,
        *,
        stalled: list[str] | None = None,
        live: list[str] | None = None,
        projects_by_owner: dict[str, list[str]] | None = None,
        tombstoned: list[str] | None = None,
    ) -> None:
        self._stalled = list(stalled or [])
        self._live = list(live or [])
        self._projects = {
            owner: list(ids) for owner, ids in (projects_by_owner or {}).items()
        }
        self._tombstoned = set(tombstoned or [])
        self.deleted_rows: list[str] = []  # 호출 순서까지 남긴다(셀 관측용)

    def stalled_user_ids(self) -> list[str]:
        return sorted(self._stalled)

    def live_user_count(self) -> int:
        return len(self._live)

    def projects_owned_by(self, user_id: str) -> list[str]:
        return sorted(self._projects.get(user_id, []))

    def has_username_tombstone(self, user_id: str) -> bool:
        return user_id in self._tombstoned

    def delete_user_row(self, user_id: str) -> bool:
        if user_id not in self._stalled:
            return False
        self._stalled.remove(user_id)
        self.deleted_rows.append(user_id)
        return True


class MongoAccountReconcileRepository:
    """스크립트가 직접 돌던 질의 그대로 — 이관이지 재설계가 아니다."""

    def __init__(self, client, *, db_name: str = DEFAULT_DB_NAME) -> None:
        self._db = client[db_name]

    def stalled_user_ids(self) -> list[str]:
        return sorted(
            doc["_id"] for doc in self._db[_USERS].find(
                {"purge_started_at": {"$ne": None}}, {"_id": 1}
            )
        )

    def live_user_count(self) -> int:
        return self._db[_USERS].count_documents({"purge_started_at": None})

    def projects_owned_by(self, user_id: str) -> list[str]:
        return sorted(
            doc["_id"] for doc in self._db[_PROJECTS].find(
                {"owner_id": user_id}, {"_id": 1}
            )
        )

    def has_username_tombstone(self, user_id: str) -> bool:
        from services.application.app.deletion.user_name_history import document_id
        from services.application.app.deletion.user_name_history_mongo import (
            COLLECTION as USER_NAME_HISTORY,
        )
        return self._db[USER_NAME_HISTORY].find_one(
            {"_id": document_id(user_id)}, {"_id": 1}
        ) is not None

    def delete_user_row(self, user_id: str) -> bool:
        return self._db[_USERS].delete_one({"_id": user_id}).deleted_count == 1
