"""회원 사용량 원장 — 기록과 집계 (Phase 8 Slice 8.2).

오너 결정 2026-08-03, 브리프 ``08-2-usage-ledger-decisions.md`` L1~L5.
8.0이 **무엇을 세는지**를, 8.1이 **얼마나 쓸 수 있는지**를 닫았고 이 모듈이 그
사이 — **"이번 창에서 몇 번 썼는가"** — 를 기록한다. **차감·차단은 없다**(8.3).

- **L1=B — 행은 `target_project_id`를 든다.** "어느 프로젝트에서 얼마나 썼는가"를
  완성하기 위해서이고, **프로젝트가 삭제돼도 사용 기록은 남아야 한다**는 것이 오너
  결정이다. **이름이 `project_id`가 아닌 것이 핵심이다** — purge reconciler는 컬렉션
  목록을 하드코딩하지 않고 ``project_id`` 필드를 가진 컬렉션을 **DB에서 발견해** 고아
  행을 지운다. 그 이름으로 적는 순간 과금 기록이 project 삭제와 함께 사라진다
  (D8-6의 ``admin_audit_events``가 ``target_project_id``를 쓰는 이유와 같다).
- **L2=A — 중복 방지 키에 `action`이 들어간다.** 프론트는 "이어쓰기" 클릭마다 새
  uuid를 만들고 **그 하나를 generate·gate·revise-and-gate·accept가 함께 쓴다.**
  ``(user, dedupe_key)``로만 잡으면 **한 흐름의 유료 동작 4개가 1개로 접혀** 8.0의
  "요청 1건 = 1회"가 조용히 깨진다. **이 모듈이 막는 것은 같은 동작의 재전송뿐이며,
  사용자가 다시 눌러 새 키로 오는 실수 중복은 막지 못한다** — 그것은 8.2b의 잠금이다.
- **L3=A — 원장 행이 정본이다.** 잔여는 세어서 얻는다. 카운터 캐시를 두지 않는 이유는
  규모다(외부 LLM ``total_slots=1``, 창당 수십 행). 정본이 하나면 어긋날 수 없다.
- **L4=A — TTL이 없다.** 지금 없는 문제를 위해 되돌릴 수 없는 삭제를 켜지 않는다.
- **L5=A — 조정은 같은 컬렉션의 다른 종류다.** 사용 행과 조정 행은 **필드 구성이
  겹치지 않는다**(``kind``로 갈린다). 집계는 둘을 함께 세지만 표시에서 섞지 않는다.

창 키는 **여기서 계산하지 않는다** — 8.1의 ``daily_key``/``weekly_key``를 부른다.
KST 경계는 ``quota/policy.py``가 이 저장소의 유일한 지역 시간대 지점이라는 결정이
여기서 지켜져야 한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Callable, Protocol

from services.application.app.quota.policy import daily_key, weekly_key


class LedgerEntryKind(StrEnum):
    USAGE = "usage"
    ADJUSTMENT = "adjustment"


class DuplicateUsageEntry(RuntimeError):
    """같은 ``(user_id, action, dedupe_key)`` 가 이미 기록돼 있다."""


@dataclass(frozen=True, slots=True)
class UsageEntry:
    """유료 동작 1회. ``delta``·``reason``·``admin_user_id`` 를 **갖지 않는다**(L5)."""

    id: str
    user_id: str
    target_project_id: str
    action: str
    dedupe_key: str
    daily_key: str
    weekly_key: str
    at: datetime
    kind: LedgerEntryKind = LedgerEntryKind.USAGE


@dataclass(frozen=True, slots=True)
class AdjustmentEntry:
    """관리자 가감 1건. ``action``·``dedupe_key`` 를 **갖지 않는다**(L5).

    ``delta`` 는 **사용량에 더해지는 값**이다 — 20회를 돌려주면 ``-20``, 10회를
    더 쓴 것으로 치면 ``+10``. 부호를 이렇게 잡아야 집계가 단순한 합이 된다.
    """

    id: str
    user_id: str
    target_project_id: str
    delta: int
    reason: str
    admin_user_id: str
    daily_key: str
    weekly_key: str
    at: datetime
    kind: LedgerEntryKind = LedgerEntryKind.ADJUSTMENT


@dataclass(frozen=True, slots=True)
class WindowUsage:
    """두 창의 사용량. **단일 값이 아니다** — 요청은 두 창을 모두 통과해야 한다.

    두 값 모두 **음수가 될 수 있다**: 관리자가 사용량보다 많이 돌려주면 그렇다.
    깎지 않는 것은 의도다 — 원장은 사실을 말하고, "한도를 넘는 보너스"는 관리자가
    만든 정당한 상태다. 잔여를 어떻게 읽을지는 8.3이 정한다.
    """

    daily: int
    weekly: int


class UsageLedgerRepository(Protocol):
    def add_usage(self, entry: UsageEntry) -> None:
        """Raises DuplicateUsageEntry if (user_id, action, dedupe_key) exists."""

    def add_adjustment(self, entry: AdjustmentEntry) -> None: ...

    def count_usage(self, user_id: str, *, window_field: str, window_key: str) -> int:
        """그 창의 **사용 행 수**(조정 제외)."""

    def sum_adjustments(
        self, user_id: str, *, window_field: str, window_key: str
    ) -> int:
        """그 창의 **조정 합**(사용 제외)."""


class InMemoryUsageLedgerRepository:
    def __init__(self) -> None:
        self._usage: list[UsageEntry] = []
        self._adjustments: list[AdjustmentEntry] = []
        self._keys: set[tuple[str, str, str]] = set()

    def add_usage(self, entry: UsageEntry) -> None:
        key = (entry.user_id, entry.action, entry.dedupe_key)
        if key in self._keys:
            raise DuplicateUsageEntry(str(key))
        self._keys.add(key)
        self._usage.append(entry)

    def add_adjustment(self, entry: AdjustmentEntry) -> None:
        self._adjustments.append(entry)

    def count_usage(self, user_id: str, *, window_field: str, window_key: str) -> int:
        return sum(
            1 for entry in self._usage
            if entry.user_id == user_id
            and getattr(entry, window_field) == window_key
        )

    def sum_adjustments(
        self, user_id: str, *, window_field: str, window_key: str
    ) -> int:
        return sum(
            entry.delta for entry in self._adjustments
            if entry.user_id == user_id
            and getattr(entry, window_field) == window_key
        )


class UsageLedgerService:
    """원장에 쓰고 원장에서 센다. **한도를 보지 않는다**(8.3의 몫)."""

    def __init__(
        self,
        repository: UsageLedgerRepository,
        *,
        id_factory: Callable[[], str],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repo = repository
        self._id_factory = id_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def _windows(self, created_at: datetime, now: datetime) -> tuple[str, str]:
        # 8.1 의 함수를 부른다 — 창 계산을 여기서 다시 하지 않는다.
        return daily_key(now), weekly_key(created_at, now)

    def record_usage(
        self, *, user_id: str, member_created_at: datetime,
        target_project_id: str, action: str, dedupe_key: str,
    ) -> UsageEntry | None:
        """유료 동작 1회를 기록한다. 이미 있는 키면 ``None``(중복이라 안 셌다).

        ``member_created_at`` 은 회원 가입 시각이다 — 주 창이 가입일 기준 7일
        주기이므로(8.1 P2-b) 창 키를 얻으려면 필요하다.
        """

        now = self._clock()
        day, week = self._windows(member_created_at, now)
        entry = UsageEntry(
            id=self._id_factory(),
            user_id=user_id,
            target_project_id=target_project_id,
            action=action,
            dedupe_key=dedupe_key,
            daily_key=day,
            weekly_key=week,
            at=now,
        )
        try:
            self._repo.add_usage(entry)
        except DuplicateUsageEntry:
            return None
        return entry

    def record_adjustment(
        self, *, user_id: str, member_created_at: datetime,
        target_project_id: str, delta: int, reason: str, admin_user_id: str,
    ) -> AdjustmentEntry:
        if not reason.strip():
            raise ValueError("adjustment reason is required")
        now = self._clock()
        day, week = self._windows(member_created_at, now)
        entry = AdjustmentEntry(
            id=self._id_factory(),
            user_id=user_id,
            target_project_id=target_project_id,
            delta=delta,
            reason=reason,
            admin_user_id=admin_user_id,
            daily_key=day,
            weekly_key=week,
            at=now,
        )
        self._repo.add_adjustment(entry)
        return entry

    def used(self, *, user_id: str, member_created_at: datetime) -> WindowUsage:
        """두 창의 사용량 = 사용 행 수 + 조정 합(L3=A, 세어서 얻는다)."""

        now = self._clock()
        day, week = self._windows(member_created_at, now)
        return WindowUsage(
            daily=self._total(user_id, "daily_key", day),
            weekly=self._total(user_id, "weekly_key", week),
        )

    def _total(self, user_id: str, field: str, key: str) -> int:
        return (
            self._repo.count_usage(user_id, window_field=field, window_key=key)
            + self._repo.sum_adjustments(user_id, window_field=field, window_key=key)
        )
