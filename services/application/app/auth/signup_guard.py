"""Signup 표면 속박 — 발신 IP 축 고정창 카운터(Phase S-3, 오너 2026-09-05 = C).

공개 ``POST /auth/signup`` 은 **승인 전에** Argon2 해시를 수행하고(t=3·m=64MiB·p=4)
앱은 단일 uvicorn 워커라, 요청 하나가 이벤트 루프를 수십~수백 ms 점유한다. 즉
**계정을 하나도 승인하지 않아도** 미인증 요청자가 서비스 전체를 세울 수 있다
(2026-09-05 감사 §A.5·§A.11). 이 모듈이 그 비용의 상한이다.

축이 **username 이 아니라 IP** 인 이유: P-6(로그인)은 같은 계정을 두드리는
공격을 막으므로 username 축이 맞지만, signup 은 **username 이 매번 다른 것이
공격 그 자체**다. 축을 IP 로 옮기는 대신 "헤더를 언제 믿는가"를 정해야 했고,
그것이 :mod:`.client_ip` 다.

창은 **고정창**이다(슬라이딩 아님). 창이 지나면 카운터가 0에서 다시 시작한다 —
``login_guard`` 와 같은 자세로, 이것은 속도 방지턱이지 누적 처벌 사다리가 아니다.
정확히 그 이유로 **막힌 요청은 창을 연장하지 않는다**: 연장하면 공격자가 자기
차단을 무한히 늘리는 대신 정직한 재시도자도 영원히 못 들어온다.

거절은 **Argon2 앞**이다. 막힌 요청이 싼 것이 이 가드의 전부다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable, Protocol

# 시간당 5건. 정상 가입은 승인제 1인 운영에서 하루 한 자릿수이고, 공격 쪽에서는
# IP 하나가 하루에 태울 수 있는 Argon2 를 120회로 묶는다.
DEFAULT_MAX_REQUESTS = 5
DEFAULT_WINDOW_SECONDS = 3600


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    attempts: int
    window_started_at: datetime


class AttemptRecordRepository(Protocol):
    def get(self, client_ip: str) -> AttemptRecord | None: ...
    def put(self, client_ip: str, record: AttemptRecord) -> None: ...


class InMemoryAttemptRecordRepository:
    def __init__(self) -> None:
        self._records: dict[str, AttemptRecord] = {}

    def get(self, client_ip: str) -> AttemptRecord | None:
        return self._records.get(client_ip)

    def put(self, client_ip: str, record: AttemptRecord) -> None:
        self._records[client_ip] = record


class SignupThrottle:
    """발신 IP 하나가 한 창 안에 낼 수 있는 signup 요청 수를 묶는다."""

    def __init__(
        self,
        repository: AttemptRecordRepository,
        *,
        max_requests: int = DEFAULT_MAX_REQUESTS,
        window: timedelta = timedelta(seconds=DEFAULT_WINDOW_SECONDS),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repo = repository
        self._max_requests = max_requests
        self._window = window
        self._clock = clock or (lambda: datetime.now(UTC))

    def consume(self, client_ip: str) -> int | None:
        """요청 하나를 계수한다. 통과면 ``None``, 막히면 ``Retry-After`` 초.

        성공·실패·409 를 가리지 않고 **모든 시도**를 센다. 비용이 결과가 아니라
        요청 자체에 붙어 있기 때문이다 — 409(중복 username)는 해시를 건너뛰지만,
        해시를 태우는 신규 username 을 섞어 보내는 것을 막을 방법이 없으므로
        결과로 나누면 그 틈이 그대로 우회 통로가 된다.
        """
        now = self._clock()
        record = self._repo.get(client_ip)
        if record is None or record.window_started_at + self._window <= now:
            self._repo.put(client_ip, AttemptRecord(attempts=1, window_started_at=now))
            return None
        if record.attempts >= self._max_requests:
            # 창을 건드리지 않는다. 여기서 ``window_started_at`` 을 now 로 밀면
            # 두드리는 동안 창이 영원히 갱신돼 정직한 재시도자까지 영구히 막힌다.
            remaining = (record.window_started_at + self._window) - now
            return max(1, int(remaining.total_seconds()))
        self._repo.put(
            client_ip,
            AttemptRecord(
                attempts=record.attempts + 1,
                window_started_at=record.window_started_at,
            ),
        )
        return None
