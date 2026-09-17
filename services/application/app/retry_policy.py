"""실패 job 재시도 정책 — 쿨다운만 남았다(오너 정정 2026-09-17, SoT v1.8.74).

S-1 D2(2026-09-05)는 상한 2회·쿨다운 60초를 함께 도입했다(감사 §A.2·§A.3 —
재시도의 무과금 재실행 통로화 방지). 2026-09-17 오너 정정으로 **영구 상한은
폐지**됐다: 상한이 analysis 의 결정적 snapshot 키(``analyze:<snapshot>``)와
만나면 초기 실행+재시도 2회를 실패로 소진한 원고가 **영원히 재분석 불가**해지는
것이 실제 배포에서 관측됐고, "회복 수단이 영구 봉쇄를 만든다"는 본말전도라는
판정이다. 남는 방어는 셋 — 쿨다운(아래), 입장 게이트(정지 403·소진 402), 그리고
확인된 재실행의 +1 과금(8.2b G4=D). ``retry_count``는 상한 없이 오르는 감사값으로
유지된다.

두 literal 은 analysis(``retry_failed_job``)·generation(``mark_pending_for_retry``)
양쪽이 같은 값을 쓴다 — 정책이 경로마다 달라지면 "어느 쪽 표면이 더 관대한가"로
공격이 몰리므로 한 곳에 둔다.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

#: 마지막 실툇 뒤 기다려야 하는 창(초). 실패 직후의 재시도 나열을 막는다.
RETRY_COOLDOWN_SECONDS = 60


class RetryCooldownActive(RuntimeError):
    """마지막 실패 직후다 — 잠시 기다렸다가 재시도한다(429 + Retry-After)."""

    def __init__(self, detail: str, *, retry_after_seconds: int) -> None:
        super().__init__(detail)
        self.retry_after_seconds = retry_after_seconds


def cooldown_remaining(failed_at: datetime | None, now: datetime) -> int:
    """쿨다운이 남았으면 올림한 초, 지났으면 ``0``.

    판정 기준은 ``failed_at`` 이다(없는 옛 행은 쿨다운이 없다). ``None`` 이 아닌
    이상 남은 시간은 항상 대략 ``RETRY_COOLDOWN_SECONDS`` 근처이므로 예외를 만드는
    쪽(sevice)이 이 값을 ``RetryCooldownActive`` 에 싣는다.
    """

    if failed_at is None:
        return 0
    elapsed = (now - failed_at).total_seconds()
    return max(0, math.ceil(RETRY_COOLDOWN_SECONDS - elapsed))


def now_utc() -> datetime:
    """서비스들의 기본 클록 — 테스트가 끊어 넣을 자리의 기본값이다."""

    return datetime.now(UTC)
