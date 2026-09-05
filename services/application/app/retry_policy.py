"""실패 job 재시도 정책 — S-1 D2 (오너 2026-09-05 = 상한+쿨다운+입장).

감사 §A.2·§A.3: analysis·generation 양쪽 retry 엔드포인트에 횟수 제한·쿨다운이
없어서, 실패 job 을 되돌리는 것만으로 provider 를 실제로 부르는 재실행이
무과금으로 무한 반복됐다. B5(같은 논리 요청은 재차감하지 않는다)는 *"재시도는
드문 회복 수단"* 이라는 전제 위의 결정인데, 그 전제를 지키는 상한이 이 모듈이다.

두 literal 은 analysis(``retry_failed_job``)·generation(``mark_pending_for_retry``)
양쪽이 같은 값을 쓴다 — 정책이 경로마다 달라지면 "어느 쪽 표면이 더 관대한가"로
공격이 몰리므로 한 곳에 둔다.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

#: job 하나가 실패 뒤 되돌릴 수 있는 횟수. 2회면 실측 실패 원인(파싱·타임아웃)의
#: 대부분을 회복하면서, 반복 유도 공격의 기대 이득을 원점 근처로 묶는다.
MAX_JOB_RETRIES = 2

#: 마지막 실툇 뒤 기다려야 하는 창(초). 실패 직후의 자동 재시도 나열을 막는다.
RETRY_COOLDOWN_SECONDS = 60


class RetryLimitReached(RuntimeError):
    """이 job 은 상한만큼 재시도됐다 — 더는 회복 수단이 아니다(409)."""


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
