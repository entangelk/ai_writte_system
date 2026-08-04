"""실수 중복 요청의 DB 잠금 — 저장 의미론 (Phase 8 Slice 8.2b).

오너 결정 2026-08-03, 브리프 ``08-2b-duplicate-request-lock-decisions.md``
**G1=C · G2~G6=A**. 8.2의 원장 dedupe 는 **키가 같을 때만** 문는데 프론트는 클릭마다
새 uuid 를 만들므로 재클릭은 그것을 그대로 통과한다 — 이 모듈이 그 자리를 덮는다.
**차감·차단·HTTP 응답은 여기 없다**(8.3).

- **G1=C — 잠금은 "5초 타이머"가 아니라 진행 중 보호 + 최소 냉각 창이다.** 이 제품의
  동기 생성은 **약 23초**(short)이고 long 은 91초라, 고정 5초 창은 "결과가 나오기 전
  재클릭"이라는 **실수 중복의 주된 형태를 못 막는다**. 그래서 요청이 진행 중이면 잠기고,
  끝나도 **차지 시각 + 최소 창**까지는 잠긴 채로 남는다.
- **G2=A — 축은 `(user_id, action, target_project_id)` 셋 다다.** 그래야 제품의 정상
  연쇄(generate → gate → revise-and-gate → accept)가 서로를 막지 않고, 다른 프로젝트
  작업도 막히지 않는다. 그 셋이 곧 문서 ``_id`` 라 **추가 인덱스가 필요 없다**.
- **G3=A — 차지는 원자적 연산 하나다.** 읽고 판단하고 쓰면 동시 두 요청이 둘 다 "없음"을
  읽는다. **★ 그리고 판정은 언제나 ``expires_at`` 비교다** — 문서 존재 여부로 판정하면
  Mongo TTL 이 백그라운드 주기(~60초)로 도는 탓에 **5초가 최대 1분이 되는데, fake 에는
  TTL 주기가 없어 테스트로는 안 보이고 운영에서만 보인다**. TTL 은 청소용이다.
- **G4=A — 확인된 요청은 강제 재차지한다.** 잠금의 목적은 "두 번 못 하게"가 아니라
  **"두 번인 줄 모르고 두 번 하지 않게"** 다. 의도적으로 2안을 받고 싶은 사용자는 확인
  한 번으로 통과하고 사용량 1회를 더 쓴다(8.0 B1=A). 강제 재차지는 **크래시 복구
  경로이기도 하다** — 요청이 죽으면 해제가 안 불려 lease 만료까지 막히는데, 확인이 그
  자리를 즉시 뚫는다.
- **★ G4 를 고른 순간 `해제`에 소유권 검사가 필수가 된다**(브리프 §0.4): 강제 재차지로
  주인이 바뀐 뒤 **먼저 시작한 요청이 완료되며 해제를 부르면** 새 주인의 보호가 사라진다.
  그래서 차지가 ``holder`` 토큰을 돌려주고 **해제는 그 토큰이 일치할 때만** 동작한다.
  분산 잠금의 고전적 fencing 문제이며 A 의 부가 기능이 아니라 **전제 조건**이다.
- **G5=A — 실패는 남은 시간과 진행 중 여부를 돌려준다.** 두 이유("아직 생성 중" /
  "방금 요청함")는 저장 필드 ``released_at`` 에서 **파생**되므로 필드가 늘지 않는다.

**두 상수는 서로 다른 것이며 합치면 둘 다 틀린다**(§0.2): 최소 창 5초는 **제품 정책**
(오너가 준 숫자)이고, lease 는 **기술 한계**로 가장 긴 동기 요청(long 91초 · gateway
timeout 120초)보다 길어야 한다.

**알려진 한계 — 잠금은 최선 노력이다**(§0.3): lease 가 만료됐는데 원래 요청이 아직 살아
있으면 중복이 샌다. ``WRITING_LOOP_MAX_WALL_CLOCK_MS`` 가 기본 무제한이라 동기 경로의
상한을 코드로 증명할 수 없기 때문이며, lease 를 넉넉히 두는 것이 그 방어다. **절대
보장이 아니다.**

시각은 **aware 여야 한다**. 8.1처럼 별도 단정을 두지는 않았다 — 창 키를 계산하지 않고
간격만 재므로 naive 가 조용히 값을 어긋내지 않고, 저장소가 aware 를 돌려주므로 naive
clock 은 첫 비교에서 ``TypeError`` 로 즉시 드러난다.
"""

from __future__ import annotations

import math
import os
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Callable, Protocol

#: 오너가 정한 제품 정책(§0.2). 요청이 끝나도 차지 시각으로부터 이만큼은 잠긴다.
DEFAULT_MINIMUM_WINDOW_SECONDS = 5

#: 크래시한 요청의 잠금을 회수하는 안전 만료(§0.2). **최소 창과 다른 축이다** —
#: 가장 긴 동기 요청(long 91초)과 gateway timeout(120초)보다 길어야 한다.
DEFAULT_LEASE_SECONDS = 180

#: 동기 경로가 넘을 수 없는 시간 = ``LLM_GATEWAY_TIMEOUT_SECONDS`` 의 기본값(`main.py`).
#: lease 가 이보다 짧으면 **아직 살아 있는 요청의 잠금이 풀려** 보호가 상시로 샌다.
LONGEST_SYNCHRONOUS_SECONDS = 120


def lock_key(user_id: str, action: str, target_project_id: str) -> str:
    """G2=A 의 세 축이 곧 문서 ``_id`` 다."""

    return f"{user_id}:{action}:{target_project_id}"


def in_flight_prefix(user_id: str) -> str:
    """그 회원의 잠금 키가 공유하는 접두 (8.3 Q3=E).

    진행 중 계수는 이 접두로 ``_id`` 를 훑는다 — 세 축이 이미 ``_id`` 라
    **8.2b 의 "추가 인덱스 없음" 계약을 건드리지 않는다.** 8.3 의 입장 뮤텍스는
    ``admission:`` 접두라 여기에 걸리지 않는다(키 공간이 둘이다).
    """

    return f"{user_id}:"


def cooldown_until(
    claimed_at: datetime, now: datetime, minimum_window: timedelta
) -> datetime:
    """해제 뒤에도 잠겨 있는 시각 = ``max(지금, 차지 + 최소 창)``.

    기준점이 **완료 시각이 아니라 차지 시각**인 것이 G1=C 의 요지다. 23초 걸린 요청은
    이미 최소 창을 넘겼으므로 곧바로 풀리고, 1초 만에 끝난 요청만 냉각이 남는다.
    """

    return max(now, claimed_at + minimum_window)


@dataclass(frozen=True, slots=True)
class RequestLock:
    """§0.1 의 잠금 문서. 상태 둘(진행 중 / 냉각)은 ``released_at`` 으로 갈린다."""

    key: str
    holder: str
    """지금 이 잠금을 쥔 요청의 토큰. **해제는 이것이 일치할 때만 유효하다**(§0.4)."""

    claimed_at: datetime
    expires_at: datetime
    """**판정의 유일한 축** — ``expires_at > now`` 면 잠겨 있다."""

    released_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class LockGranted:
    """차지 성공. ``holder`` 를 들고 있어야 나중에 해제할 수 있다."""

    holder: str


@dataclass(frozen=True, slots=True)
class LockBlocked:
    """차지 실패(G5=A). 저장 표현을 그대로 노출하지 않는다."""

    retry_after_seconds: int
    in_flight: bool
    """``True`` 면 아직 생성 중, ``False`` 면 방금 끝나 냉각 중이다."""


ClaimResult = LockGranted | LockBlocked


def _env_seconds(name: str, fallback: int) -> int:
    raw = os.environ.get(name)
    return fallback if raw is None or not raw.strip() else int(raw)


def configured_minimum_window_seconds() -> int:
    window = _env_seconds(
        "QUOTA_LOCK_MINIMUM_WINDOW_SECONDS", DEFAULT_MINIMUM_WINDOW_SECONDS)
    if window < 1:
        raise ValueError(
            "QUOTA_LOCK_MINIMUM_WINDOW_SECONDS must be at least 1 second — "
            "a zero or negative window turns the guard off silently"
        )
    return window


def configured_lease_seconds() -> int:
    """배포 구성은 계약을 어기면 **거부한다**(2026-08-03 독립 검증 H2).

    생성자 인자는 자유롭게 둔다 — 테스트가 초 단위로 짧게 돌리는 자리이고, 거기서는
    값이 눈앞에 보인다. 반면 env 오설정은 **아무도 안 보는 사이에 핵심 보호를 끈다**:
    lease 가 gateway timeout 보다 짧으면 아직 실행 중인 요청의 잠금이 풀린다.
    """

    lease = _env_seconds("QUOTA_LOCK_LEASE_SECONDS", DEFAULT_LEASE_SECONDS)
    if lease <= LONGEST_SYNCHRONOUS_SECONDS:
        raise ValueError(
            f"QUOTA_LOCK_LEASE_SECONDS must outlive the longest synchronous "
            f"request ({LONGEST_SYNCHRONOUS_SECONDS}s, the gateway timeout) — "
            "a shorter lease frees the lock while the request is still running"
        )
    return lease


class RequestLockRepository(Protocol):
    def claim(self, lock: RequestLock, *, now: datetime) -> RequestLock:
        """없거나 만료된 잠금만 차지한다. **원자적 연산 하나여야 한다**(G3=A).

        돌려주는 것은 **그 키의 현재 잠금**이다 — 차지에 성공했으면 인자로 준 것과
        같은 ``holder`` 이고, 막혔으면 막은 잠금이다(호출자가 이유를 파생한다).
        """

    def force_claim(self, lock: RequestLock) -> None:
        """살아 있는 잠금을 덮어쓴다(G4=A). 확인된 요청만 이 문을 쓴다."""

    def release(
        self, key: str, *, holder: str, now: datetime, minimum_window: timedelta
    ) -> bool:
        """자기 토큰일 때만 냉각으로 넘긴다. 남의 잠금은 **건드리지 않는다**(§0.4)."""

    def count_in_flight(self, user_id: str, *, now: datetime) -> int:
        """그 회원의 **진행 중** 잠금 수 (8.3 Q3=E).

        "진행 중"은 ``released_at is None`` **그리고** ``expires_at > now`` 다 —
        해제된(냉각 중) 잠금은 이미 일이 끝난 것이라 사용량에 넣으면 회원이 쓰지도
        않은 한 칸을 5초간 잃는다.
        """


class InMemoryRequestLockRepository:
    def __init__(self) -> None:
        self._locks: dict[str, RequestLock] = {}

    def peek(self, key: str) -> RequestLock | None:
        """테스트용 — **판정에 쓰지 않는다**(존재는 잠김을 뜻하지 않는다)."""

        return self._locks.get(key)

    def claim(self, lock: RequestLock, *, now: datetime) -> RequestLock:
        current = self._locks.get(lock.key)
        if current is not None and current.expires_at > now:
            return current
        self._locks[lock.key] = lock
        return lock

    def force_claim(self, lock: RequestLock) -> None:
        self._locks[lock.key] = lock

    def release(
        self, key: str, *, holder: str, now: datetime, minimum_window: timedelta
    ) -> bool:
        current = self._locks.get(key)
        if current is None or current.holder != holder:
            return False
        self._locks[key] = replace(
            current,
            released_at=now,
            expires_at=cooldown_until(current.claimed_at, now, minimum_window),
        )
        return True

    def count_in_flight(self, user_id: str, *, now: datetime) -> int:
        prefix = in_flight_prefix(user_id)
        return sum(
            1 for key, lock in self._locks.items()
            if key.startswith(prefix)
            and lock.released_at is None
            and lock.expires_at > now
        )


class RequestLockService:
    """차지·해제·강제 재차지 세 연산. **누가 얼마나 썼는지는 모른다**(8.2의 몫)."""

    def __init__(
        self,
        repository: RequestLockRepository,
        *,
        holder_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        minimum_window_seconds: int | None = None,
        lease_seconds: int | None = None,
    ) -> None:
        """``holder_factory`` 는 **부를 때마다 새 토큰**을 줘야 한다.

        같은 토큰을 돌려주는 factory 를 넘기면 옛 요청이 새 주인의 잠금을 해제할 수
        있어 fencing 이 통째로 무너진다(§0.4). 그래서 기본값을 이 모듈이 소유한다 —
        인자는 테스트가 토큰을 읽을 수 있게 하려고 남긴 자리다
        (2026-08-03 독립 검증 H1).
        """

        window = (
            minimum_window_seconds if minimum_window_seconds is not None
            else configured_minimum_window_seconds()
        )
        lease = (
            lease_seconds if lease_seconds is not None
            else configured_lease_seconds()
        )
        if window < 1:
            raise ValueError("the minimum window must be at least 1 second")
        if lease <= window:
            raise ValueError(
                "lease must outlive the minimum window — they are different axes: "
                "the window is product policy, the lease covers the longest "
                "synchronous request"
            )
        self._repo = repository
        self._holder_factory = holder_factory or (lambda: uuid.uuid4().hex)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._minimum_window = timedelta(seconds=window)
        self._lease = timedelta(seconds=lease)

    def claim(
        self, *, user_id: str, action: str, target_project_id: str
    ) -> ClaimResult:
        now = self._clock()
        attempt = self._new_lock(user_id, action, target_project_id, now)
        current = self._repo.claim(attempt, now=now)
        if current.holder == attempt.holder:
            return LockGranted(holder=attempt.holder)
        return LockBlocked(
            retry_after_seconds=_seconds_left(current.expires_at, now),
            # 이유는 파생된다 — 저장 필드를 늘리지 않고 G5 가 성립하는 자리다.
            in_flight=current.released_at is None,
        )

    def force_claim(
        self, *, user_id: str, action: str, target_project_id: str
    ) -> LockGranted:
        """확인된 요청(G4=A). 잠금을 **끄는 것이 아니라 옮긴다** — 다음 클릭은 다시 막힌다."""

        now = self._clock()
        lock = self._new_lock(user_id, action, target_project_id, now)
        self._repo.force_claim(lock)
        return LockGranted(holder=lock.holder)

    def release(
        self, *, user_id: str, action: str, target_project_id: str, holder: str
    ) -> bool:
        """요청 완료. 자기 잠금이 아니면 ``False`` 이고 **아무것도 바꾸지 않는다**."""

        return self._repo.release(
            lock_key(user_id, action, target_project_id),
            holder=holder,
            now=self._clock(),
            minimum_window=self._minimum_window,
        )

    def count_in_flight(self, *, user_id: str) -> int:
        """지금 이 회원이 **처리 중인** 유료 요청 수 (8.3 Q3=E).

        8.3 이 이것을 사용량에 더해 "진행 중 요청도 한도를 차지한다"를 만든다 —
        성공차감(Q1=C)이라 원장 행은 응답 직전에야 생기고, 그 사이가 최대 91초다.
        잠금이 곧 그 구간의 예약 장부라 **새 저장소도 새 수명도 만들지 않는다**.
        """

        return self._repo.count_in_flight(user_id, now=self._clock())

    def _new_lock(
        self, user_id: str, action: str, target_project_id: str, now: datetime
    ) -> RequestLock:
        return RequestLock(
            key=lock_key(user_id, action, target_project_id),
            holder=self._holder_factory(),
            claimed_at=now,
            expires_at=now + self._lease,
            released_at=None,
        )


def _seconds_left(expires_at: datetime, now: datetime) -> int:
    """올림한다 — 0.5초 남았는데 "0초 뒤 다시"라고 말하면 그 재시도가 또 막힌다."""

    return max(1, math.ceil((expires_at - now).total_seconds()))
