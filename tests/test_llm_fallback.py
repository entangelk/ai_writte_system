"""키 회전(1순위)·모델 폴백(2순위) — FallbackProvider 계약 (오너 정책 2026-08-22).

표준 시도 순서는 a1 → b1 → c1 → a2 → b2 → c2(키를 먼저 전부, 모델을 나중에).
시작 키는 라운드로빈으로 배분한다(오너 정정 2026-08-22 — 랜덤이 아니라 정확히
분산). 전 조합 소진은 fail-fast.
"""

import asyncio
import unittest

from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.fallback import (
    KEY_REJECTED_COOLDOWN_SECONDS,
    RATE_LIMIT_COOLDOWN_SECONDS,
    FallbackProvider,
    SlidingWindowRateLimiter,
    parse_env_list,
)
from services.llm_gateway.app.payload import ChatCompletionRequest, ChatMessage
from services.llm_gateway.app.provider import FakeLLMProvider, GenerationResult, TokenUsage


class FakeClock:
    """monotonic 대용 — 창/쿨다운의 시간 경과를 테스트가 직접 밀고 간다."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


class RecordingProvider:
    """FakeLLMProvider를 감싸 (키, 모델) 시도 순서를 하나의 로그에 남긴다.

    provider별 요청 리스트만으로는 교차 순서가 사라진다 — a1b1c1a2b2c2와
    a1a2b1b2c1c2가 provider별 기록으로는 구별되지 않기 때문이다.
    """

    def __init__(self, name: str, outcomes, attempts: list[str]) -> None:
        self._name = name
        self._inner = FakeLLMProvider(outcomes)
        self._attempts = attempts

    async def generate(self, request: ChatCompletionRequest) -> GenerationResult:
        self._attempts.append(f"{self._name}:{request.model}")
        return await self._inner.generate(request)


class _HangingProvider:
    """예산 검증용 — 서버가 답하지 않는 최악의 경우."""

    async def generate(self, request: ChatCompletionRequest) -> GenerationResult:
        await asyncio.sleep(30.0)
        raise AssertionError("unreachable — the budget must cancel this first")


class _ProbingProvider:
    """context_window/count_tokens 위임 검증용."""

    def __init__(self, window: int | None, tokens: int | None) -> None:
        self._window = window
        self._tokens = tokens

    async def generate(self, request: ChatCompletionRequest) -> GenerationResult:
        raise AssertionError("not under test")

    async def context_window(self) -> int | None:
        return self._window

    async def count_tokens(self, text: str) -> int | None:
        return self._tokens


def _request(content: str = "안녕", model: str | None = None):
    return ChatCompletionRequest(
        messages=(ChatMessage(role="user", content=content),),
        model=model,
        max_tokens=8,
    )


def _result() -> GenerationResult:
    return GenerationResult(
        model="any",
        content="ok",
        finish_reason="stop",
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
    )


def _error(code: ProviderErrorCode, retryable: bool) -> ProviderError:
    return ProviderError(
        code=code, message=code.value, retryable=retryable, provider="external"
    )


def _unavailable() -> ProviderError:
    return _error(ProviderErrorCode.UNAVAILABLE, True)


class FallbackProviderTests(unittest.IsolatedAsyncioTestCase):
    def _fallback(self, providers, models, *, limit: int = 30, clock=None):
        return FallbackProvider(
            providers=providers,
            models=models,
            limiter=SlidingWindowRateLimiter(
                slots=len(providers),
                limit=limit,
                clock=clock if clock is not None else FakeClock(),
            ),
            total_timeout_seconds=10.0,
        )

    async def test_attempt_order_is_keys_first_then_models(self):
        # 표준 순서(오너 2026-08-22): a1 → b1 → c1 → a2 → b2 → c2.
        # under-strict: 모델을 먼저 바꾸면(a1a2b1b2…) 이 셀이 재실패한다.
        attempts: list[str] = []
        providers = [
            RecordingProvider(name, [_unavailable(), _unavailable()], attempts)
            for name in ("a", "b", "c")
        ]
        fallback = self._fallback(providers, ["m1", "m2"])

        with self.assertRaises(ProviderError):
            await fallback.generate(_request())

        self.assertEqual(
            attempts,
            ["a:m1", "b:m1", "c:m1", "a:m2", "b:m2", "c:m2"],
        )

    async def test_starting_key_rotates_round_robin_across_requests(self):
        # 라운드로빈 배분(오너 정정 2026-08-22): 요청마다 시작 키가 0→1→2로 순환해
        # 어느 키로도 집중되지 않는다. under-strict: 시작 키를 고정하면 재실패한다.
        providers = [FakeLLMProvider([_result()]) for _ in range(3)]
        fallback = self._fallback(providers, ["m1"])

        for content in ("r1", "r2", "r3"):
            await fallback.generate(_request(content=content))

        placement = {
            request.messages[0].content: index
            for index, provider in enumerate(providers)
            for request in provider.requests
        }
        self.assertEqual(placement, {"r1": 0, "r2": 1, "r3": 2})

    async def test_full_windows_skip_keys_and_fail_fast_until_freed(self):
        # limit=1 — 한 번 쓴 키의 창은 즉시 가득 찬다. 세 키 전부가 찬 순간 시도
        # 자체가 0개가 되고 fail-fast(오너 2026-08-22). 창이 지나면 다시 쓴다.
        clock = FakeClock()
        providers = [FakeLLMProvider([_result(), _result()]) for _ in range(3)]
        fallback = self._fallback(providers, ["m1"], limit=1, clock=clock)

        await fallback.generate(_request("r1"))  # 키 0
        await fallback.generate(_request("r2"))  # 키 1
        await fallback.generate(_request("r3"))  # 키 2

        with self.assertRaises(ProviderError) as raised:
            await fallback.generate(_request("r4"))
        self.assertIs(raised.exception.code, ProviderErrorCode.OVERLOADED)
        self.assertIs(raised.exception.retryable, True)
        # skip은 시도가 아니었다 — 누구도 추가로 불리지 않았다.
        self.assertEqual([len(p.requests) for p in providers], [1, 1, 1])

        clock.now += 61.0  # 창이 비워진다
        result = await fallback.generate(_request("r5"))
        self.assertEqual(result.content, "ok")

    async def test_all_keys_cooling_fails_fast_without_any_attempt(self):
        # 쿨다운 경로의 fail-fast: 시도 0개 → OVERLOADED retryable. 빈 큐의 fake는
        # 불리는 순간 FakeProviderExhausted를 내므로 아래 assertRaises가 그 자리를
        # 같이 지킨다.
        clock = FakeClock()
        providers = [FakeLLMProvider([]), FakeLLMProvider([])]
        limiter = SlidingWindowRateLimiter(slots=2, limit=30, clock=clock)
        limiter.cool(0, 60.0)
        limiter.cool(1, 60.0)
        fallback = FallbackProvider(
            providers=providers,
            models=["m1"],
            limiter=limiter,
            total_timeout_seconds=10.0,
        )

        with self.assertRaises(ProviderError) as raised:
            await fallback.generate(_request())

        self.assertIs(raised.exception.code, ProviderErrorCode.OVERLOADED)
        self.assertIs(raised.exception.retryable, True)
        self.assertEqual(providers[0].requests, [])
        self.assertEqual(providers[1].requests, [])

    async def test_exhaustion_after_attempts_reraises_the_last_error(self):
        # 시도는 했으나 전부 실패 — 마지막 오류를 그대로(진단 보존). 별도의 뭉뚱그린
        # 오류로 바꾸면 under-strict: 원인이 사라진다.
        outcomes_b = [_unavailable(), _unavailable()]
        providers = [
            FakeLLMProvider([_unavailable(), _unavailable()]),
            FakeLLMProvider(outcomes_b),
        ]
        fallback = self._fallback(providers, ["m1", "m2"])

        with self.assertRaises(ProviderError) as raised:
            await fallback.generate(_request())

        self.assertIs(raised.exception, outcomes_b[1])  # a:m1→b:m1→a:m2→b:m2의 끝

    async def test_key_rejected_cools_the_key_long(self):
        # 401/403 — 키 자체가 거부됐다. 600초 쉬지 않으면 같은 거절에 RPM 예산만 태운다.
        clock = FakeClock()
        rejected = _error(ProviderErrorCode.KEY_REJECTED, False)
        providers = [FakeLLMProvider([rejected]), FakeLLMProvider([_result()])]
        limiter = SlidingWindowRateLimiter(slots=2, limit=30, clock=clock)
        fallback = FallbackProvider(
            providers=providers, models=["m1"], limiter=limiter,
            total_timeout_seconds=10.0,
        )

        result = await fallback.generate(_request())
        self.assertEqual(result.content, "ok")  # 키 1이 살렸다
        self.assertTrue(limiter.is_cooling(0))
        self.assertFalse(limiter.is_cooling(1))
        clock.now += KEY_REJECTED_COOLDOWN_SECONDS - 1.0
        self.assertTrue(limiter.is_cooling(0))
        clock.now += 2.0
        self.assertFalse(limiter.is_cooling(0))

    async def test_overloaded_cools_the_key_short(self):
        # 429 — 분당 한도. 슬라이딩 창과 같은 60초면 충분하다.
        clock = FakeClock()
        overloaded = _error(ProviderErrorCode.OVERLOADED, True)
        providers = [FakeLLMProvider([overloaded]), FakeLLMProvider([_result()])]
        limiter = SlidingWindowRateLimiter(slots=2, limit=30, clock=clock)
        fallback = FallbackProvider(
            providers=providers, models=["m1"], limiter=limiter,
            total_timeout_seconds=10.0,
        )

        result = await fallback.generate(_request())
        self.assertEqual(result.content, "ok")
        self.assertTrue(limiter.is_cooling(0))
        clock.now += RATE_LIMIT_COOLDOWN_SECONDS - 1.0
        self.assertTrue(limiter.is_cooling(0))
        clock.now += 2.0
        self.assertFalse(limiter.is_cooling(0))

    async def test_non_retryable_errors_stop_the_chain_immediately(self):
        # 400류 — 키·모델을 바꿔도 같은 결과다. 남은 조합에 왕복 비용을 쓰지 않는다.
        # over-strict 방향: retryable 오류를 여기 끊어 넣으면 시도-순서 셀들이
        # 재실패한다(회전은 retryable의 몫이다).
        non_retryable = (
            ProviderErrorCode.REQUEST_REJECTED,
            ProviderErrorCode.INVALID_RESPONSE,
            ProviderErrorCode.CONTEXT_WINDOW_EXCEEDED,
        )
        for code in non_retryable:
            with self.subTest(code=code):
                fatal = _error(code, False)
                providers = [FakeLLMProvider([fatal]), FakeLLMProvider([])]
                fallback = self._fallback(providers, ["m1", "m2"])

                with self.assertRaises(ProviderError) as raised:
                    await fallback.generate(_request())

                self.assertIs(raised.exception, fatal)
                self.assertEqual(len(providers[0].requests), 1)
                self.assertEqual(providers[1].requests, [])

    async def test_request_model_leads_the_chain_and_duplicates_collapse(self):
        # 앱이 LLM_GATEWAY_MODEL을 요청에 싣는 일이 흔하다 — 명시 모델이 첫 순위,
        # env 모델은 그 뒤 폴백. 명시 모델 = env models[0]이면 체인은 한 번만.
        attempts: list[str] = []
        providers = [
            RecordingProvider("a", [_unavailable()] * 3, attempts),
            RecordingProvider("b", [_unavailable()] * 3, attempts),
        ]
        fallback = self._fallback(providers, ["m1", "m2"])

        with self.assertRaises(ProviderError):
            await fallback.generate(_request(model="explicit"))
        self.assertEqual(
            attempts,
            ["a:explicit", "b:explicit", "a:m1", "b:m1", "a:m2", "b:m2"],
        )

        deduped: list[str] = []
        providers_dedup = [
            RecordingProvider("a", [_unavailable()] * 2, deduped),
            RecordingProvider("b", [_unavailable()] * 2, deduped),
        ]
        fallback_dedup = self._fallback(providers_dedup, ["m1", "m2"])

        with self.assertRaises(ProviderError):
            await fallback_dedup.generate(_request(model="m1"))
        self.assertEqual(deduped, ["a:m1", "b:m1", "a:m2", "b:m2"])

    async def test_total_budget_bounds_the_chain(self):
        # N개 조합이 시도당 타임아웃을 N배로 불리는 것을 막는다 — 예산이 창이면
        # 남은 조합은 시도하지 않고 TIMEOUT으로 돌아간다.
        fallback = FallbackProvider(
            providers=[_HangingProvider()],
            models=["m1"],
            limiter=SlidingWindowRateLimiter(slots=1, limit=30, clock=FakeClock()),
            total_timeout_seconds=0.05,
        )

        with self.assertRaises(ProviderError) as raised:
            await fallback.generate(_request())

        self.assertIs(raised.exception.code, ProviderErrorCode.TIMEOUT)
        self.assertIs(raised.exception.retryable, True)

    async def test_window_and_token_queries_delegate_to_the_first_provider(self):
        # /v1/capabilities·/v1/tokenize의 getattr 프로브가 계속 통과해야 한다.
        first = _ProbingProvider(window=4096, tokens=7)
        second = _ProbingProvider(window=999, tokens=999)
        fallback = self._fallback([first, second], ["m1"])

        self.assertEqual(await fallback.context_window(), 4096)
        self.assertEqual(await fallback.count_tokens("hi"), 7)

        # 메서드가 없는 provider(FakeLLMProvider) 앞에서는 "모른다"=None 이다.
        plain = FallbackProvider(
            providers=[FakeLLMProvider([])],
            models=["m1"],
            limiter=SlidingWindowRateLimiter(slots=1, limit=30, clock=FakeClock()),
            total_timeout_seconds=10.0,
        )
        self.assertIsNone(await plain.context_window())
        self.assertIsNone(await plain.count_tokens("hi"))

    async def test_failure_logs_name_the_key_index_and_code_only(self):
        # 이 클래스는 키 값을 모른다 — 구조적 보증. 로그 형식이 우연히 키를 실을
        # 자리가 생기지 않게 잠근다(운용자가 어느 키가 아픈지 알아야 하므로 인덱스는 남긴다).
        providers = [
            FakeLLMProvider([_unavailable(), _unavailable()]),
            FakeLLMProvider([_unavailable(), _unavailable()]),
        ]
        fallback = self._fallback(providers, ["m1", "m2"])

        with self.assertLogs(
            "services.llm_gateway.app.fallback", level="WARNING"
        ) as captured:
            with self.assertRaises(ProviderError):
                await fallback.generate(_request())

        text = "\n".join(captured.output)
        self.assertIn("key_index=0", text)
        self.assertIn("key_index=1", text)
        self.assertIn("code=provider_unavailable", text)
        self.assertNotIn("Bearer", text)
        self.assertNotIn("sk-", text)


class SlidingWindowRateLimiterTests(unittest.TestCase):
    def test_limit_is_enforced_within_the_window_and_frees_at_the_boundary(self):
        clock = FakeClock()
        limiter = SlidingWindowRateLimiter(slots=1, limit=2, clock=clock)

        self.assertTrue(limiter.try_acquire(0))
        self.assertTrue(limiter.try_acquire(0))
        self.assertFalse(limiter.try_acquire(0))  # 창 가득 — skip은 시도가 아니다

        clock.now += 59.0
        self.assertFalse(limiter.try_acquire(0))
        clock.now += 1.0  # 정확히 60초 경계 — 가장 오래된 기록이 창을 나간다
        self.assertTrue(limiter.try_acquire(0))

    def test_cooldown_blocks_acquisition_regardless_of_the_window(self):
        clock = FakeClock()
        limiter = SlidingWindowRateLimiter(slots=1, limit=5, clock=clock)

        limiter.cool(0, 60.0)
        self.assertFalse(limiter.try_acquire(0))
        clock.now += 60.0
        self.assertTrue(limiter.try_acquire(0))

    def test_construction_rejects_non_positive_arguments(self):
        with self.assertRaises(ValueError):
            SlidingWindowRateLimiter(slots=1, limit=0)
        with self.assertRaises(ValueError):
            SlidingWindowRateLimiter(slots=0, limit=1)


class FallbackConstructionTests(unittest.TestCase):
    def test_empty_providers_or_models_are_rejected(self):
        limiter = SlidingWindowRateLimiter(slots=1, limit=1, clock=FakeClock())
        with self.assertRaises(ValueError):
            FallbackProvider(
                providers=[], models=["m"], limiter=limiter,
                total_timeout_seconds=1.0,
            )
        with self.assertRaises(ValueError):
            FallbackProvider(
                providers=[FakeLLMProvider([])], models=[], limiter=limiter,
                total_timeout_seconds=1.0,
            )


class CooldownLiteralTests(unittest.TestCase):
    def test_owner_policy_cooldown_literals_are_pinned(self):
        """오너 정책 리터럴 600s/60s — 상대 기준 셀(상수±1)은 임의 값에도 참이다.

        2026-08-23 독립 검증 H1(M1): 600을 60으로 바꿔도 전 수트가 green이었다.
        두 값은 오너 결정(401/403 장기·429 단기)이므로 절대값으로 잠근다.
        under-strict: 리터럴을 바꾸면 이 셀이 문다. over-strict: 없음 —
        값 자체가 계약이다(바꾸려면 오너 결정과 함께 이 셀을 고친다).
        """
        self.assertEqual(KEY_REJECTED_COOLDOWN_SECONDS, 600.0)
        self.assertEqual(RATE_LIMIT_COOLDOWN_SECONDS, 60.0)


class ParseEnvListTests(unittest.TestCase):
    def test_splits_strips_and_dedups(self):
        # 같은 키를 두 번 적으면 슬롯이 두 개가 돼 RPM 예산이 두 배로 세진다 — 중복 제거는 그 방지.
        self.assertEqual(parse_env_list(" a , b ,,a "), ["a", "b"])

    def test_empty_or_separator_only_is_unset(self):
        # compose 대시 표기(`${VAR-}`)는 빈 값을 내려보낸다 — unset과 같아야 한다.
        for raw in (None, "", "  ", ",,"):
            with self.subTest(raw=raw):
                self.assertEqual(parse_env_list(raw), [])


if __name__ == "__main__":
    unittest.main()
