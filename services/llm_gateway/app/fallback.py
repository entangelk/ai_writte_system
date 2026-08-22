"""키 회전(1순위)·모델 폴백(2순위) provider — 오너 정책 2026-08-22.

배포 서버가 외부 API 로만 돌면서(docker-compose.external.yml) 단일 키·단일 모델로는
429/5xx 한 번에 호출이 죽는 것이 이 모듈의 계기다. 정책:

- **키를 먼저 바꾸고, 모델을 나중에 바꾼다.** keys=[a,b,c]·models=[1,2]일 때 표준
  시도 순서는 a1 → b1 → c1 → a2 → b2 → c2 — 모델 1로 키 전부가 실패해야 모델 2로
  넘어간다(키를 바꾸는 것이 모델을 바꾸는 것보다 싸고, 같은 모델을 다른 계정
  한도로 쓸 수 있기 때문).
- **시작 키는 라운드로빈으로 배분한다**(요청마다 순환). 한 키로 트래픽이 집중되면
  그 키만 429에 걸리고 나머지는 쉰다 — 배분이 곧 예산이다(오너 정정 2026-08-22,
  최초 안은 "랜덤 시작"이었으나 랜덤은 통계적으로만 분산되고 라운드로빈은 정확히
  분산한다).
- **키당 기본 RPM 30**(슬라이딩 60초 창). 창이 찬 키는 시도하지 않고 건너뛴다.
- **전 조합이 소진되면 fail-fast** — 대기하지 않고 retryable 오류를 낸다(오너
  2026-08-22). 앱 쪽에 이미 provider_retry_cap 재시도 예산이 있고, 게이트웨이가
  창이 풀릴 때까지 붙잡고 있으면 그만큼 다른 요청의 예산도 함께 태운다.

어떤 오류가 회전 트리거인가는 `ProviderError.retryable`와 `KEY_REJECTED`(401/403)가
이미 담고 있다 — 이 모듈은 분류를 다시 하지 않고 그 판정을 소비만 한다.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import replace
import logging
import time

from .errors import ProviderError, ProviderErrorCode
from .payload import ChatCompletionRequest
from .provider import GenerationResult, LLMProvider


log = logging.getLogger(__name__)

# 401/403 — 키 자체가 거부된 경우. 잘못된 키는 60초 뒤에도 잘못됐으므로 길게 쉰다.
KEY_REJECTED_COOLDOWN_SECONDS = 600.0
# 429 — 키의 분당 한도에 걸린 경우. 슬라이딩 창(60초)과 같은 길이면 충분하다.
RATE_LIMIT_COOLDOWN_SECONDS = 60.0


class SlidingWindowRateLimiter:
    """슬롯(키)별 슬라이딩 창 RPM 계수기 + 쿨다운.

    확인(`try_acquire`)과 기록이 한 덩어리로, 그 사이에 await이 없다 — 이벤트 루프
    하나에서 도는 이 서비스에는 그것으로 원자성이 충분하다(동기 쪽 형제는
    `services/application/app/key_rotation.py`가 Lock을 씌운다).
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
        self._windows: list[deque[float]] = [deque() for _ in range(slots)]
        self._cooldown_until: list[float] = [float("-inf")] * slots
        self._limit = limit
        self._window_seconds = window_seconds
        self._clock = clock

    def try_acquire(self, slot: int) -> bool:
        """이 슬롯으로 한 번 시도해도 되는가. 가능하면 즉시 기록까지 마친다."""
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
        self._cooldown_until[slot] = self._clock() + seconds

    def is_cooling(self, slot: int) -> bool:
        return self._clock() < self._cooldown_until[slot]

    def _evict(self, slot: int, now: float) -> None:
        window = self._windows[slot]
        horizon = now - self._window_seconds
        while window and window[0] <= horizon:
            window.popleft()


def parse_env_list(raw: str | None) -> list[str]:
    """쉼표 env 리스트 → 순서 보존 중복 제거 목록. 빈 항목·공백은 버린다.

    같은 키를 두 번 적으면 그 키의 RPM 예산이 두 배로 세지므로(슬롯이 두 개가
    되니까) 중복은 뺀다. 쉼표를 포함한 키 값은 지원하지 않는다 — 그런 벤더 키는
    사실상 없다는 가정이며, 필요해지면 그때 구분자를 정한다.
    """
    if not raw:
        return []
    items: list[str] = []
    for piece in raw.split(","):
        item = piece.strip()
        if item and item not in items:
            items.append(item)
    return items


class FallbackProvider:
    """`LLMProvider`를 키 수만큼 감싸 회전·폴백하는 데코레이터.

    각 provider 인스턴스가 **키 하나씩**을 든다(transport가 Bearer 헤더를 갖는다).
    이 클래스는 키 값을 모른다 — 로그에 키가 새는 경로가 원천적으로 없다.
    """

    def __init__(
        self,
        *,
        providers: list[LLMProvider],
        models: list[str],
        limiter: SlidingWindowRateLimiter,
        total_timeout_seconds: float,
    ) -> None:
        if not providers:
            raise ValueError("providers must not be empty")
        if not models:
            raise ValueError("models must not be empty")
        self._providers = providers
        self._models = models
        self._limiter = limiter
        self._total_timeout_seconds = total_timeout_seconds
        self._next_start = 0

    async def generate(
        self,
        request: ChatCompletionRequest,
    ) -> GenerationResult:
        chain = self._model_chain(request)
        rotated = self._rotated_slots()
        last_error: ProviderError | None = None
        try:
            # 체인 전체가 공유하는 예산. 시도당 타임아웃(LLAMA_TIMEOUT_SECONDS)을 그대로
            # 총액으로 쓴다 — N개 조합이 최악 지연을 N배로 불리는 것을 막는다. 앱의
            # 상위 deadline(역시 120s)을 넘기면 성공한 시도조차 timeout으로 뒤집히는
            # 것이 1b(B1)가 이미 겪은 실패 방식이다.
            async with asyncio.timeout(self._total_timeout_seconds):
                for model in chain:
                    for slot, provider in rotated:
                        if not self._limiter.try_acquire(slot):
                            continue
                        try:
                            return await provider.generate(
                                replace(request, model=model)
                            )
                        except ProviderError as exc:
                            last_error = exc
                            # 키 인덱스만 남긴다 — 키 값은 이 클래스가 모른다(위).
                            log.warning(
                                "llm fallback attempt failed: "
                                "key_index=%d model=%s code=%s",
                                slot,
                                model,
                                exc.code.value,
                            )
                            key_fatal = (
                                exc.code is ProviderErrorCode.KEY_REJECTED
                            )
                            if key_fatal:
                                # 401/403은 retryable=False지만 **키 치명**이다 —
                                # 다음 키로 넘어간다. retryable 플래그는 "이 요청을
                                # 그대로 재시도하면 되는가"(앱 쪽 계약)이고, 여기서
                                # 필요한 것은 "조합을 바꾸면 고쳐지는가"다.
                                self._limiter.cool(
                                    slot, KEY_REJECTED_COOLDOWN_SECONDS
                                )
                            elif exc.code is ProviderErrorCode.OVERLOADED:
                                self._limiter.cool(
                                    slot, RATE_LIMIT_COOLDOWN_SECONDS
                                )
                            if not exc.retryable and not key_fatal:
                                # 요청 자체가 못 쓰는 실패 — 키·모델을 바꿔도 같은
                                # 결과다. 남은 조합에 왕복 비용을 쓰지 않는다.
                                raise
        except TimeoutError as exc:
            raise ProviderError(
                code=ProviderErrorCode.TIMEOUT,
                message="fallback chain exceeded the total time budget",
                retryable=True,
            ) from exc
        if last_error is not None:
            # 시도는 했으나 전부 실패 — 마지막 오류를 그대로 돌려 보내 진단을 보존한다.
            raise last_error
        # 시도 자체가 0개 = 전 조합이 RPM/쿨다운 — fail-fast(오너 2026-08-22).
        raise ProviderError(
            code=ProviderErrorCode.OVERLOADED,
            message="all provider keys are rate-limited or cooling down",
            retryable=True,
        )

    async def context_window(self) -> int | None:
        """`/v1/capabilities`용 위임. 첫 provider(라운드로빈과 무관한 고정 순서)만 본다.

        창은 서버 기동 설정이라 키와 무관하며, 외부 API에서는 어차피 `None`이다.
        """
        probe = getattr(self._providers[0], "context_window", None)
        if not callable(probe):
            return None
        return await probe()

    async def count_tokens(self, text: str) -> int | None:
        """`/v1/tokenize`용 위임. 마찬가지로 첫 provider만 본다."""
        probe = getattr(self._providers[0], "count_tokens", None)
        if not callable(probe):
            return None
        return await probe(text)

    def _model_chain(self, request: ChatCompletionRequest) -> list[str]:
        """요청이 명시한 모델을 첫 순위로, env 모델들은 그 뒤 폴백으로.

        앱이 `LLM_GATEWAY_MODEL`을 요청에 싣는 일이 흔하므로(main.py 8곳) 명시 모델이
        env 체인을 **덮어쓰는 게 아니라 앞장서는** 것이 운용 의도에 맞다 — 폴백은
        여전히 뒤따른다. 중복은 뺀다(명시 모델 = env models[0]인 경우가 그렇다).
        """
        chain: list[str] = []
        if request.model:
            chain.append(request.model)
        for model in self._models:
            if model not in chain:
                chain.append(model)
        return chain

    def _rotated_slots(self) -> list[tuple[int, LLMProvider]]:
        """이번 요청의 시작 키를 라운드로빈으로 뽑고 거기서부터 순환하는 (슬롯, provider)."""
        count = len(self._providers)
        start = self._next_start
        self._next_start = (self._next_start + 1) % count
        return [
            ((start + offset) % count, self._providers[(start + offset) % count])
            for offset in range(count)
        ]
