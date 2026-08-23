"""회원별 요청 한도 정책 — 저장 계약 (Phase 8 Slice 8.1).

오너 결정 2026-08-03, 브리프 ``08-1-request-quota-policy-decisions.md``.
8.0이 "무엇을 1회로 세는가"를 닫았고([`billable_actions.py`]), 이 모듈은 그 숫자에
**한도를 붙이는 저장 계약**이다. **차감·차단은 여기 없다** — 8.3의 몫이다.

- **P1 — 정책은 회원 문서가 아니라 자기 저장소에 산다.** `User`는 로그인·세션·
  부트스트랩이 모두 지나는 자료라 상품 정책이 얹히면 안 된다.
- **P2 — 사용량 창은 둘이다.** ① **일**: KST 자정마다 새 창 ② **주**: **가입일로부터
  7일** 주기(회원마다 다르다). 요청은 **두 창을 모두** 통과해야 한다. 구독 개월
  카운트는 이 축이 아니다(오너: 초기화 주기와 이용기간은 다른 축이다) — 구독은
  8.6에서 별도로 선다.
- **P2-a — 경계는 KST다.** 저장은 UTC 그대로이고 **경계 계산만** 한국 시간으로 한다.
  UTC 자정으로 두면 한국 회원의 리셋이 매일 오전 9시가 된다. **이 모듈이 이 저장소의
  유일한 지역 시간대 지점이다** — 창 키 계산을 여기 밖에서 다시 하면 조회 화면과
  시행 경로가 다른 "오늘"을 말하게 된다.
- **P3 — 창은 파생한다.** 시각에서 계산할 뿐 저장하지 않는다. 그래서 **리셋 작업이
  없다** — 리셋은 키가 바뀌는 것이지 무엇이 도는 것이 아니다(스택에 스케줄러가 없다).
- **P4 — 행이 없으면 기본값**이다. 개인 예외만 행을 갖는다. 기본을 바꿔도 옛 값을
  들고 있는 회원이 생기지 않는다.
- **P5 — 수량과 상태를 분리한다.** 한도는 창별로 하나씩이고 ``None``은 무제한이다
  (이 저장소의 기존 관례). 정지는 수량이 아니라 ``status``라, ``daily_limit=0``
  ("오늘은 0회")과 구분된다.
- **P6 — 유리한 변경은 즉시, 불리한 변경은 현재 주가 끝날 때** 발효한다. 판정은
  **필드별**이다(일은 올리고 주는 내리는 변경이 가능하다). 오너는 정지가 최대 1주
  늦어지는 것을 받아들였다 — "고객의 사용감 편의가 먼저"이며, 즉시 차단이 필요한
  상황에는 계정 비활성화(`POST /admin/users/{id}/deactivate`)가 이미 있다. 그쪽은
  세션 해석마다 `is_active`를 보므로 **기존 세션까지 즉시** 끊긴다.
- **P7 — 기본값은 잠정이고, 호출부는 상수가 아니라 이 모듈의 해석을 지난다.**
  실사용 데이터가 없어 숫자를 못박지 않았다(오너). 나중에 플랜별·구독 개월별 계산이
  들어와도 호출부는 바뀌지 않는다.
- **P8 — 구독 축은 여기 없다.** 결제 방식이 정해질 때(8.6) 그 요구에서 나오는 편이
  낭비가 없다. ``status``는 enum이라 값 추가가 스키마 변경이 아니다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

#: 창 경계를 재는 시간대(P2-a). 저장은 UTC이고 이 값은 경계 계산에만 쓴다.
BOUNDARY_TIMEZONE = ZoneInfo("Asia/Seoul")

_WEEK = timedelta(days=7)

#: 잠정 기본값(P7). 실사용 분포가 나오면 조정한다 — env 로 먼저 재고, 영구 변경은
#: 이 상수를 고친다. `주 < 일 × 7` 이어야 주 한도가 실제로 의미를 갖는다.
DEFAULT_DAILY_LIMIT = 20
DEFAULT_WEEKLY_LIMIT = 100


class QuotaStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


@dataclass(frozen=True, slots=True)
class QuotaLimits:
    """한 회원에게 지금 유효한 한도(P5).

    ``None`` 은 그 창에 상한이 없다는 뜻이다. 두 창은 독립이라 한쪽만 무제한인
    설정도 정당하다.
    """

    daily_limit: int | None = DEFAULT_DAILY_LIMIT
    weekly_limit: int | None = DEFAULT_WEEKLY_LIMIT
    status: QuotaStatus = QuotaStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class PendingLimits:
    """주 경계에 발효할 예약 변경(P6). 예약은 한 건이며 새 예약이 앞 것을 덮는다."""

    limits: QuotaLimits
    effective_at: datetime


@dataclass(frozen=True, slots=True)
class QuotaPolicy:
    """저장된 정책 문서. **`limits` 는 유효 한도가 아니다.**

    발효한 `pending` 이 문서에 남아 있을 수 있기 때문이다(`clear_pending` 은 선택적
    정리이고 자동으로 도는 것이 없다 — 그것이 P3/P6의 요지다). 읽는 쪽은 항상
    `effective_limits(policy, now)` 나 `QuotaPolicyService.limits_for` 를 지나야 하며,
    `policy.limits` 를 직접 읽으면 **만료된 예약이 "아직 대기 중"으로 보인다**
    (2026-08-03 독립 검증 H2 — 8.5 관리자 조회에서 특히 주의).
    """

    user_id: str
    limits: QuotaLimits
    pending: PendingLimits | None
    updated_at: datetime


# ---------------------------------------------------------------- 창 (P2·P3)


def _require_aware(name: str, moment: datetime) -> datetime:
    """naive 를 조용히 받지 않는다 (2026-08-03 독립 검증 H1).

    `astimezone` 은 naive 를 **시스템 로컬**로 해석하므로, 비-UTC 호스트에서 naive 가
    들어오면 창 경계가 조용히 어긋난다 — 이 저장소가 가장 크게 데인 함정의 형태
    그대로다(값이 틀리는데 아무것도 실패하지 않는다). 지금 입력 경로는 전부 aware
    이지만(기본 clock 은 `datetime.now(UTC)`, `created_at` 은 `users_mongo` 가 UTC 를
    재부착한다) 그것은 **관습이지 계약이 아니었다.** 여기서 계약으로 만든다.

    저장소 경계의 `_aware` 와 방향이 다른 것은 의도적이다: BSON 은 UTC 임이 알려져
    있어 재부착이 재명명이지만, 도메인 입력의 naive 는 **무엇인지 알 수 없다**.
    """

    if moment.tzinfo is None:
        raise ValueError(
            f"{name} must be timezone-aware — a naive datetime would be read as "
            "system local time and silently shift the window boundary"
        )
    return moment


def _local(moment: datetime) -> datetime:
    return moment.astimezone(BOUNDARY_TIMEZONE)


def daily_key(now: datetime) -> str:
    """일 창의 키 = KST 날짜. 자정에 바뀐다."""

    return _local(_require_aware("now", now)).date().isoformat()


def next_daily_boundary(now: datetime) -> datetime:
    """현재 일 창이 끝나는 순간 = 다음 KST 자정. UTC 로 돌려준다 (8.4 W5=B).

    회원 화면이 "언제 초기화되나"를 말하려면 창의 **끝**이 필요한데, 그 계산이
    화면으로 새면 이 모듈이 유일한 지역 시간대 지점이라는 성질이 깨진다 —
    시행과 표시가 다른 "오늘"을 말하게 된다.
    """

    local = _local(_require_aware("now", now))
    tomorrow = local.date() + timedelta(days=1)
    return datetime(
        tomorrow.year, tomorrow.month, tomorrow.day,
        tzinfo=BOUNDARY_TIMEZONE,
    ).astimezone(UTC)


def weekly_cycle_bounds(created_at: datetime, now: datetime) -> tuple[datetime, datetime]:
    """가입일 기준 7일 주기의 [시작, 끝). 둘 다 UTC 로 돌려준다.

    기준점은 가입 **시각**이 아니라 가입**일**의 KST 자정이다(오너 문언 그대로).
    그래야 두 창이 같은 순간에 넘어간다 — 오후에 주가 따로 바뀌면 "오늘 리셋됐는데
    왜 또 바뀌었나"가 된다.
    """

    _require_aware("now", now)
    anchor_date = _local(_require_aware("created_at", created_at)).date()
    anchor = datetime.combine(
        anchor_date, datetime.min.time(), tzinfo=BOUNDARY_TIMEZONE
    ).astimezone(UTC)
    elapsed = now - anchor
    if elapsed < timedelta(0):
        # 가입 당일 자정 이전(= 가입 시각과 자정 사이)도 첫 주기 안이다.
        index = 0
    else:
        index = elapsed // _WEEK
    start = anchor + index * _WEEK
    return start, start + _WEEK


def weekly_key(created_at: datetime, now: datetime) -> str:
    """주 창의 키 = 그 주기가 시작한 KST 날짜. 회원마다 다르다(P2-b)."""

    start, _end = weekly_cycle_bounds(created_at, now)
    return _local(start).date().isoformat()


def next_week_boundary(created_at: datetime, now: datetime) -> datetime:
    """현재 주기가 끝나는 순간 = 불리한 정책 변경이 발효하는 시각(P6)."""

    _start, end = weekly_cycle_bounds(created_at, now)
    return end


# ------------------------------------------------------- 기본값·해석 (P4·P7)


def _env_limit(name: str, fallback: int) -> int | None:
    """미설정이면 코드 기본, 빈 문자열이면 무제한(``None``), 그 외는 정수.

    빈 문자열 = 상한 없음은 루프 토큰 예산(`_env_opt_int`)의 기존 관례를 따른 것이다.
    """

    raw = os.environ.get(name)
    if raw is None:
        return fallback
    if not raw.strip():
        return None
    return int(raw)


def default_limits() -> QuotaLimits:
    """행이 없는 회원에게 적용되는 정책(P4). 호출부는 이 함수만 안다(P7)."""

    return QuotaLimits(
        daily_limit=_env_limit("QUOTA_DEFAULT_DAILY_LIMIT", DEFAULT_DAILY_LIMIT),
        weekly_limit=_env_limit("QUOTA_DEFAULT_WEEKLY_LIMIT", DEFAULT_WEEKLY_LIMIT),
        status=QuotaStatus.ACTIVE,
    )


def effective_limits(policy: QuotaPolicy | None, now: datetime) -> QuotaLimits:
    """지금 이 순간 유효한 한도.

    P6의 예약 변경을 **읽는 쪽에서** 해석한다 — 순수 함수이므로 발효를 위해 도는
    작업이 필요 없다(P3과 같은 성질). 문서를 실제로 갱신하는 것은 다음 쓰기 때
    곁들여도 되고 안 해도 된다.
    """

    _require_aware("now", now)
    if policy is None:
        return default_limits()
    if policy.pending is not None and now >= policy.pending.effective_at:
        return policy.pending.limits
    return policy.limits


# --------------------------------------------------------- 유·불리 판정 (P6)


def _rank(limit: int | None) -> float:
    """무제한이 가장 큰 값이다 — 10 → None 은 상향, None → 10 은 하향이다."""

    return float("inf") if limit is None else float(limit)


def _favorable_limit(current: int | None, target: int | None) -> bool:
    return _rank(target) >= _rank(current)


def _favorable_status(current: QuotaStatus, target: QuotaStatus) -> bool:
    return target is QuotaStatus.ACTIVE or target is current


def split_change(
    current: QuotaLimits, target: QuotaLimits
) -> tuple[QuotaLimits, bool]:
    """(즉시 반영분, 유예가 필요한가). 판정은 **필드별**이다(P6).

    일은 올리고 주는 내리는 변경에서 덩어리로 판정하면 한쪽 때문에 다른 쪽까지
    즉시가 되거나 유예된다.
    """

    immediate = QuotaLimits(
        daily_limit=(
            target.daily_limit
            if _favorable_limit(current.daily_limit, target.daily_limit)
            else current.daily_limit
        ),
        weekly_limit=(
            target.weekly_limit
            if _favorable_limit(current.weekly_limit, target.weekly_limit)
            else current.weekly_limit
        ),
        status=(
            target.status
            if _favorable_status(current.status, target.status)
            else current.status
        ),
    )
    return immediate, immediate != target


# ------------------------------------------------------------------ 저장소


class QuotaPolicyRepository(Protocol):
    def get(self, user_id: str) -> QuotaPolicy | None: ...

    def upsert(self, policy: QuotaPolicy) -> None:
        """회원당 최대 한 행. 같은 회원의 두 번째 쓰기는 덮어쓴다."""


class InMemoryQuotaPolicyRepository:
    def __init__(self) -> None:
        self._policies: dict[str, QuotaPolicy] = {}

    def get(self, user_id: str) -> QuotaPolicy | None:
        return self._policies.get(user_id)

    def upsert(self, policy: QuotaPolicy) -> None:
        self._policies[policy.user_id] = policy


class QuotaPolicyService:
    """정책을 읽고 바꾸는 유일한 자리. **한도를 시행하지는 않는다**(8.3)."""

    def __init__(
        self,
        repository: QuotaPolicyRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repo = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    def limits_for(self, user_id: str) -> QuotaLimits:
        return effective_limits(self._repo.get(user_id), self._clock())

    def policy_row(self, user_id: str) -> QuotaPolicy | None:
        """저장된 정책 행 그대로(8.5-a 관리자 조회용).

        **호출부는 이 값을 "유효 한도"로 쓰면 안 된다** — 해석(``effective_limits``)
        을 거쳐야 하며, 여기가 진단용 원본(``stored_limits``·``pending``)이 필요한
        관리자 상세를 위해만 존재한다. 시행은 계속 ``limits_for`` 를 쓴다.
        """

        return self._repo.get(user_id)

    def now(self) -> datetime:
        """이 서비스가 보는 현재 시각. 창 경계를 묻는 호출부(8.4 W5)가 쓴다.

        시행과 표시가 **같은 시계**를 봐야 "오늘"이 갈라지지 않는다 — 호출부가
        `datetime.now(UTC)` 를 따로 부르면 테스트의 고정 시계도 새어 나간다.
        """

        return self._clock()

    def set_limits(
        self, *, user_id: str, created_at: datetime, target: QuotaLimits
    ) -> QuotaPolicy:
        """목표 한도를 요청한다. 유리한 부분은 즉시, 불리한 부분은 주 경계에.

        ``created_at`` 은 회원 가입 시각이다 — 주 경계가 회원마다 다르므로(P2-b)
        발효 시각을 계산하려면 필요하다.
        """

        now = self._clock()
        current = effective_limits(self._repo.get(user_id), now)
        immediate, deferred = split_change(current, target)
        policy = QuotaPolicy(
            user_id=user_id,
            limits=immediate,
            pending=(
                PendingLimits(
                    limits=target,
                    effective_at=next_week_boundary(created_at, now),
                )
                if deferred
                else None
            ),
            updated_at=now,
        )
        self._repo.upsert(policy)
        return policy

    def clear_pending(self, user_id: str) -> QuotaPolicy | None:
        """발효한 예약을 문서에 굳힌다(선택적 정리 — 해석은 이미 예약을 반영한다)."""

        policy = self._repo.get(user_id)
        if policy is None or policy.pending is None:
            return policy
        now = self._clock()
        if now < policy.pending.effective_at:
            return policy
        settled = replace(
            policy, limits=policy.pending.limits, pending=None, updated_at=now
        )
        self._repo.upsert(settled)
        return settled
