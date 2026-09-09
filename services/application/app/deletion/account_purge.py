"""계정 파기 — 유예가 끝난 탈퇴 계정을 지운다 (계정 탈퇴 Slice 3).

오너 결정: D1~D6(2026-09-07) + 브리프
``plans/slice3-withdrawal-purge-daemon-decisions.md`` 의 **ⓑ 두 규칙 스윕 · ⓔ 범위**
(2026-09-09). 이 모듈은 **파기의 순서와 실패 규칙**을 담고, 실제 프로젝트 파괴는
``routers/admin.py::execute_project_purge`` **한 벌뿐인 본체**에 위임한다.

## 한 계정의 처리 순서

1. **청구** — ``purge_started_at`` 을 조건부로 찍는다. 못 찍으면 남의 것이거나
   이미 시작된 것이라 **건드리지 않는다.**
2. **사용자명 묘비** — 아무것도 부수기 전에 이름을 남긴다. 프로젝트 축이 같은 자리에서
   같은 이유로 이 순서를 강제한다: 뒤로 미루면 저장 장애 한 번에 이름이 영영 사라진다.
3. **프로젝트** — 소유한 것을 하나씩 ``archive → execute_project_purge``.
   2단계는 그 함수가 강제한다(active 인 채로 부르면 409).
4. **계정 축 스윕** — ⓑ 의 두 규칙.
5. **계정 행 파기** — 마지막이다.

## ★ 실패하면 멈춘다 (D3=ⓐ)

``execute_project_purge`` 는 core_sot 을 **먼저** 지우므로 **재시도가 멱등이 아니다** —
중간에 실패하면 두 번째 호출은 404 로 끝나고 derived(프롬프트 본문·원고 후보)에
도달하지 못한다. 그래서 여기서도 재시도하지 않는다: 실패한 계정은 ``purge_started_at``
이 찍힌 채 남아 **다시 청구되지 않고**, 잔여 청소는 reconciler 경로가 맡는다
(``scripts/purge_reconciler.py`` · ``scripts/account_purge_reconciler.py``).

한 계정의 실패는 **다른 계정을 막지 않는다** — 그 계정만 멈추고 배수는 계속한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Awaitable, Callable, Protocol

from services.application.app.auth.models import User
from services.application.app.auth.users import is_purge_due

#: 계정 축 스윕이 **절대 건드리지 않는** 컬렉션. 계정 행은 파기 그래프의 마지막
#: 단계라 스윕이 먼저 지우면 실패를 표시할 자리가 사라진다.
NEVER_SWEPT = frozenset({"users"})


class AccountAxisSweeper(Protocol):
    def sweep(self, user_id: str) -> dict[str, int]:
        """계정 축 잔여를 지우고 ``컬렉션 → 삭제 건수`` 를 돌려준다."""


@dataclass(frozen=True, slots=True)
class AccountPurgeResult:
    user_id: str
    username: str
    projects_purged: tuple[str, ...] = ()
    swept: dict[str, int] = field(default_factory=dict)
    failed_at: str | None = None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.failed_at is None


@dataclass(frozen=True, slots=True)
class AccountPurgeSummary:
    accounts_claimed: int = 0
    accounts_purged: int = 0
    accounts_failed: int = 0
    results: tuple[AccountPurgeResult, ...] = ()


class AccountPurgeService:
    def __init__(
        self,
        *,
        users,
        core_sot,
        user_name_history,
        sweeper: AccountAxisSweeper,
        purge_project: Callable[..., Awaitable[None]],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._users = users
        self._core_sot = core_sot
        self._names = user_name_history
        self._sweeper = sweeper
        # 프로젝트 파괴 본체로 가는 **경계**. 서비스 18개를 이 모듈이 알 이유가 없고,
        # HTTP 예외를 도메인 예외로 옮기는 자리도 여기가 아니라 조립부다.
        self._purge_project = purge_project
        self._clock = clock or (lambda: datetime.now(UTC))

    def due_accounts(self, *, now: datetime) -> tuple[User, ...]:
        """유예가 끝났고 아직 아무도 시작하지 않은 계정.

        경계 판정은 ``is_purge_due`` **한 곳**이다(``>=``·30일 상수 모두 그 안).
        저장소 질의로 내리면 산술이 두 곳이 되고, 화면의 *남은 N일* 과 데몬의
        *오늘이 그날인가* 가 갈라진다(Slice 0 계약 ⓑ).
        """
        return tuple(
            user for user in self._users.list_withdrawing()
            if is_purge_due(user, now=now)
        )

    async def run_once(
        self, *, now: datetime | None = None, limit: int = 10,
        stop_check: Callable[[], bool] | None = None,
    ) -> AccountPurgeSummary:
        if limit < 1:
            raise ValueError("limit must be positive")
        moment = now if now is not None else self._clock()
        claimed = 0
        purged = 0
        failed = 0
        results: list[AccountPurgeResult] = []
        for user in self.due_accounts(now=moment)[:limit]:
            if stop_check is not None and stop_check():
                break
            result = await self.purge_account(user)
            if result is None:
                # 청구 실패 — 남이 가져갔거나 이미 시작됐다. 조용히 지나간다.
                continue
            claimed += 1
            results.append(result)
            if result.succeeded:
                purged += 1
            else:
                failed += 1
        return AccountPurgeSummary(
            accounts_claimed=claimed,
            accounts_purged=purged,
            accounts_failed=failed,
            results=tuple(results),
        )

    async def purge_account(self, user: User) -> AccountPurgeResult | None:
        claimed = self._users.claim_for_purge(user.id, at=self._clock())
        if claimed is None:
            return None
        purged_projects: list[str] = []
        try:
            # 2. 이름 먼저. 이 실패는 삼키지 않는다 — 뒤로 미루면 저장 장애 한 번에
            #    이름이 영영 사라진다(project_name_history 와 같은 순서·같은 이유).
            self._names.record_purged(user_id=user.id, username=user.username)
        except Exception as exc:
            return _failure(user, "user_name_history", exc, purged_projects)
        for project in self._core_sot.list_projects_for_owner(owner_id=user.id):
            try:
                if not project.archived:
                    # 2단계 삭제는 UI 관례가 아니라 파기 본체가 강제한다(active 면 409).
                    self._core_sot.archive_project(project_id=project.id)
                await self._purge_project(
                    project_id=project.id, acting_user_id=user.id
                )
            except Exception as exc:
                # ★ 여기서 멈춘다. 다음 프로젝트로 넘어가면 **부분 파기가 커진다** —
                #   실패한 프로젝트의 derived 는 재시도로 못 지우므로(본체의 알려진
                #   한계), 남는 잔여를 늘리지 않는 것이 D3 의 뜻이다.
                return _failure(user, f"project:{project.id}", exc, purged_projects)
            purged_projects.append(project.id)
        try:
            swept = self._sweeper.sweep(user.id)
        except Exception as exc:
            return _failure(user, "account_axis_sweep", exc, purged_projects)
        try:
            self._users.delete(user.id)
        except Exception as exc:
            return _failure(user, "user_row", exc, purged_projects)
        return AccountPurgeResult(
            user_id=user.id,
            username=user.username,
            projects_purged=tuple(purged_projects),
            swept=swept,
        )


def _failure(
    user: User, stage: str, exc: Exception, purged: list[str]
) -> AccountPurgeResult:
    return AccountPurgeResult(
        user_id=user.id,
        username=user.username,
        projects_purged=tuple(purged),
        failed_at=stage,
        # 예외 **종류와 문장**을 남긴다. 계정은 이미 ``purge_started_at`` 이 찍혀
        # 다시 청구되지 않으므로, 운영자가 무엇을 수습해야 하는지 알 유일한 통로다.
        error=f"{type(exc).__name__}: {exc}",
    )
