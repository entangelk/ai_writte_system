"""동기 키 회전의 공유 부품 — 임베딩·리랭커 축이 같이 쓴다 (오너 정책 2026-08-22).

게이트웨이 형제(`services/llm_gateway/app/fallback.py`)와 같은 정책의 동기 버전:
시작 키 라운드로빈 배분, 키당 RPM 슬라이딩 60초 창, 401/403 장기(600s)·429 단기(60s)
쿨다운, 소진 fail-fast. 회전 루프 자체는 각 축의 파일에 있다(embedding.py·rerank.py) —
에러 클래스가 그쪽에 있고 이 모듈이 그것들을 import 하면 조립 사이클이 생긴다.

★ 이 모듈은 provider 생성자를 부르지 않는다. embedding 어셈블리 가드
(tests/test_embedding_assembly.py)가 services/ 전체에서 생성 호출을 금지하므로,
생성은 각 축의 build_*_from_env 가 하고 이 모듈은 계수기만 든다.

왜 게이트웨이의 SlidingWindowRateLimiter 와 코드를 공유하지 않는가: application 이
llm_gateway 패키지를 import 하는 방향은 이미 있다(gateway_provider.py)지만 그 반대는
없고, 40줄짜리 창 계수기를 위해 의존 방향을 하나 더 여는 것이 이 저장소의
self-containment 관례(_env_bool 등의 모듈별 복제)보다 비싸다.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable


# 401/403 — 키 자체가 거부됐다. 60초 뒤에도 여전히 잘못됐다.
KEY_REJECTED_COOLDOWN_SECONDS = 600.0
# 429 — 키의 분당 한도. 슬라이딩 창(60초)과 같은 길이면 충분하다.
RATE_LIMIT_COOLDOWN_SECONDS = 60.0


class SyncSlidingWindowLimiter:
    """슬롯(키)별 슬라이딩 창 RPM 계수기 + 쿨다운 (동기).

    임베딩·리랭커 호출은 FastAPI sync endpoint 의 스레드풀에서 동시에 들어올 수
    있어 Lock 으로 보호한다 — 비동기 형제(fallback.SlidingWindowRateLimiter)와의
    유일한 차이가 그것이다.
    """

    def __init__(
        self,
        *,
        slots: int,
        limit: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if slots < 1:
            raise ValueError("slots must be at least 1")
        if limit < 1:
            raise ValueError("limit must be at least 1")
        self._lock = threading.Lock()
        self._windows: list[deque[float]] = [deque() for _ in range(slots)]
        self._cooldown_until: list[float] = [float("-inf")] * slots
        self._limit = limit
        self._window_seconds = window_seconds
        self._clock = clock

    def try_acquire(self, slot: int) -> bool:
        """이 슬롯으로 한 번 시도해도 되는가. 가능하면 즉시 기록까지 마친다."""
        with self._lock:
            now = self._clock()
            self._evict(slot, now)
            if now < self._cooldown_until[slot]:
                return False
            if len(self._windows[slot]) >= self._limit:
                return False
            self._windows[slot].append(now)
            return True

    def cool(self, slot: int, seconds: float) -> None:
        """이 슬롯을 `seconds` 동안 아예 쓰지 않는다(429·401/403 응답용)."""
        with self._lock:
            self._cooldown_until[slot] = self._clock() + seconds

    def is_cooling(self, slot: int) -> bool:
        with self._lock:
            return self._clock() < self._cooldown_until[slot]

    def _evict(self, slot: int, now: float) -> None:
        window = self._windows[slot]
        horizon = now - self._window_seconds
        while window and window[0] <= horizon:
            window.popleft()


def split_env_list(raw: str | None) -> list[str]:
    """쉼표 env 리스트 → 순서 보존 중복 제거 목록. 빈 항목·공백은 버린다.

    게이트웨이의 parse_env_list 와 같은 계약 — 같은 키를 두 번 적으면 슬롯이 두 개가
    되어 RPM 예산이 두 배로 세지므로 중복은 뺀다.
    """
    if not raw:
        return []
    items: list[str] = []
    for piece in raw.split(","):
        item = piece.strip()
        if item and item not in items:
            items.append(item)
    return items
