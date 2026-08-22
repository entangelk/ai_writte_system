"""동기 키 회전 — 임베딩·리랭커 래퍼의 회전 계약 (오너 정책 2026-08-22).

시작 키 라운드로빈(오너 정정 2026-08-22 — 랜덤이 아니라 정확히 분산), 키당 RPM
슬라이딩 60s 창, 401/403 장기·429/5xx/네트워크 단기 쿨다운, 소진 fail-fast.
차원 가드·400류는 회전하지 않는다(over-strict 방향).
"""

import threading
import unittest

from services.application.app.indexing.embedding import (
    EmbeddingProviderError,
    KeyRotatingEmbeddingProvider,
)
from services.application.app.context_search.rerank import (
    KeyRotatingRerankProvider,
    RerankProviderError,
    RerankingRetriever,
)
from services.application.app.key_rotation import (
    KEY_REJECTED_COOLDOWN_SECONDS,
    RATE_LIMIT_COOLDOWN_SECONDS,
    SyncSlidingWindowLimiter,
    split_env_list,
)


class FakeClock:
    """monotonic 대용 — 창/쿨다운의 시간 경과를 테스트가 직접 밀고 간다."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


class FakeEmbeddingProvider:
    """결과/오류를 FIFO 로 내는 embed fake — httpx 없이 회전 계약만 본다.

    큐가 비었는데 불리면 IndexError — "불려선 안 되는 시도"가 조용히 넘어가지
    않게 하는 암묵적 가드다.
    """

    def __init__(self, outcomes) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def embed(self, text: str) -> tuple[float, ...]:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _network_error() -> EmbeddingProviderError:
    return EmbeddingProviderError(
        "embedding service is unavailable", network=True
    )


def _status_error(status_code: int) -> EmbeddingProviderError:
    return EmbeddingProviderError(
        f"embedding service returned status {status_code}",
        status_code=status_code,
    )


class KeyRotatableClassificationTests(unittest.TestCase):
    def test_rotation_worthiness_of_each_error_shape(self):
        # 회전 대상: 네트워크·401/403/408/429·5xx. 비회전: 400·404·본문/차원 계약 위반.
        rotatable = [
            _network_error(),
            _status_error(401),
            _status_error(403),
            _status_error(408),
            _status_error(429),
            _status_error(500),
            _status_error(503),
        ]
        for error in rotatable:
            with self.subTest(error=str(error)):
                self.assertTrue(error.key_rotatable)

        not_rotatable = [
            _status_error(400),
            _status_error(404),
            EmbeddingProviderError("embedding response is not JSON"),
            EmbeddingProviderError(
                "embedding has 3 dimensions, expected 1024"
            ),
        ]
        for error in not_rotatable:
            with self.subTest(error=str(error)):
                self.assertFalse(error.key_rotatable)


class KeyRotatingEmbeddingProviderTests(unittest.TestCase):
    def _rotating(self, providers, *, limit=30, clock=None, budget=30.0):
        clock = clock if clock is not None else FakeClock()
        return KeyRotatingEmbeddingProvider(
            providers=providers,
            limiter=SyncSlidingWindowLimiter(
                slots=len(providers), limit=limit, clock=clock
            ),
            budget_seconds=budget,
            clock=clock,
        )

    def test_rotates_on_a_network_error_then_succeeds(self):
        # under-strict: 회전이 없으면(오늘의 단일 provider) 첫 실패가 곧 실패다.
        providers = [
            FakeEmbeddingProvider([_network_error()]),
            FakeEmbeddingProvider([(1.0, 2.0)]),
        ]
        rotating = self._rotating(providers)

        self.assertEqual(rotating.embed("x"), (1.0, 2.0))
        self.assertEqual([p.calls for p in providers], [1, 1])

    def test_round_robin_assignment_spreads_requests(self):
        # 시작 키가 요청마다 0→1→2로 순환 — 어느 키로도 집중되지 않는다.
        providers = [
            FakeEmbeddingProvider([(float(index),)]) for index in range(3)
        ]
        rotating = self._rotating(providers)

        results = [rotating.embed("x") for _ in range(3)]

        self.assertEqual(results, [(0.0,), (1.0,), (2.0,)])
        self.assertEqual([p.calls for p in providers], [1, 1, 1])

    def test_a_4xx_error_does_not_rotate(self):
        # over-strict: 요청 버그(400)를 회전으로 삼키면 진단이 늦어진다.
        rejected = _status_error(400)
        providers = [
            FakeEmbeddingProvider([rejected]),
            FakeEmbeddingProvider([(1.0,)]),
        ]
        rotating = self._rotating(providers)

        with self.assertRaises(EmbeddingProviderError) as raised:
            rotating.embed("x")

        self.assertIs(raised.exception, rejected)
        self.assertEqual(providers[1].calls, 0)

    def test_a_dimension_guard_error_does_not_rotate(self):
        # 차원 가드 오류는 키와 무관하다 — 어느 키로 보내도 같은 결과다(결정 3=A).
        guard = EmbeddingProviderError(
            "embedding has 3 dimensions, expected 1024"
        )
        providers = [
            FakeEmbeddingProvider([guard]),
            FakeEmbeddingProvider([(1.0,)]),
        ]
        rotating = self._rotating(providers)

        with self.assertRaises(EmbeddingProviderError) as raised:
            rotating.embed("x")

        self.assertIs(raised.exception, guard)
        self.assertEqual(providers[1].calls, 0)

    def test_401_cools_long_and_429_cools_short(self):
        clock = FakeClock()
        limiter = SyncSlidingWindowLimiter(slots=2, limit=30, clock=clock)
        providers = [
            FakeEmbeddingProvider([_status_error(401)]),
            FakeEmbeddingProvider([_status_error(429)]),
        ]
        rotating = KeyRotatingEmbeddingProvider(
            providers=providers, limiter=limiter,
            budget_seconds=30.0, clock=clock,
        )

        with self.assertRaises(EmbeddingProviderError):
            rotating.embed("x")  # 둘 다 실패 — 마지막(429)이 재발생

        self.assertTrue(limiter.is_cooling(0))
        self.assertTrue(limiter.is_cooling(1))
        clock.now += RATE_LIMIT_COOLDOWN_SECONDS + 1.0
        self.assertFalse(limiter.is_cooling(1))  # 429는 짧게 풀리고
        self.assertTrue(limiter.is_cooling(0))   # 401은 아직 쉰다
        clock.now += KEY_REJECTED_COOLDOWN_SECONDS - RATE_LIMIT_COOLDOWN_SECONDS
        self.assertFalse(limiter.is_cooling(0))  # 600초 지나서야 풀린다

    def test_all_keys_limited_fails_fast_with_a_retryable_status(self):
        clock = FakeClock()
        limiter = SyncSlidingWindowLimiter(slots=2, limit=30, clock=clock)
        limiter.cool(0, 60.0)
        limiter.cool(1, 60.0)
        providers = [FakeEmbeddingProvider([]), FakeEmbeddingProvider([])]
        rotating = KeyRotatingEmbeddingProvider(
            providers=providers, limiter=limiter,
            budget_seconds=30.0, clock=clock,
        )

        with self.assertRaises(EmbeddingProviderError) as raised:
            rotating.embed("x")

        self.assertEqual(raised.exception.status_code, 429)
        # 인덱스 재시도 backoff 가 잡을 수 있는 모양이어야 한다.
        self.assertTrue(raised.exception.key_rotatable)
        self.assertEqual([p.calls for p in providers], [0, 0])

    def test_exhaustion_reraises_the_last_error(self):
        # 시도는 했으나 전부 실패 — 마지막 오류 그대로(진단 보존).
        last = _network_error()
        providers = [
            FakeEmbeddingProvider([_network_error()]),
            FakeEmbeddingProvider([last]),
        ]
        rotating = self._rotating(providers)

        with self.assertRaises(EmbeddingProviderError) as raised:
            rotating.embed("x")

        self.assertIs(raised.exception, last)

    def test_budget_stops_extra_attempts_but_the_first_always_runs(self):
        # 첫 시도는 예산 0이어도 돈다 — 시도조차 안 하고 실패하는 것보다 낫다.
        clock = FakeClock()
        providers = [
            FakeEmbeddingProvider([_network_error()]),
            FakeEmbeddingProvider([(1.0,)]),
        ]
        rotating = self._rotating(providers, clock=clock, budget=0.0)

        with self.assertRaises(EmbeddingProviderError):
            rotating.embed("x")

        self.assertEqual(providers[0].calls, 1)
        self.assertEqual(providers[1].calls, 0)  # 예산 소진 — 시작하지 않는다

    def test_rpm_window_skips_keys_until_freed(self):
        clock = FakeClock()
        providers = [
            FakeEmbeddingProvider([(0.0,), (0.0,)]),
            FakeEmbeddingProvider([(1.0,), (1.0,)]),
        ]
        rotating = self._rotating(providers, limit=1, clock=clock)

        rotating.embed("x")  # 키 0 — 창 1/1
        rotating.embed("x")  # 키 1 — 창 1/1

        with self.assertRaises(EmbeddingProviderError) as raised:
            rotating.embed("x")  # 전부 가득 — fail-fast
        self.assertEqual(raised.exception.status_code, 429)

        clock.now += 61.0  # 창이 비워진다
        rotating.embed("x")
        # 세 번째 요청의 시작 키는 라운드로빈 카운터가 정한다 — 키 1부터.
        self.assertEqual([p.calls for p in providers], [1, 2])


class SyncSlidingWindowLimiterTests(unittest.TestCase):
    def test_concurrent_acquires_never_exceed_the_limit(self):
        # 스레드풀 동시 호출 smoke — 엄밀한 증명은 아니지만 Lock 부재가 즉시 드러난다.
        clock = FakeClock()  # 창이 안 흐르므로 정확히 limit 개만 성공한다
        limiter = SyncSlidingWindowLimiter(slots=1, limit=3, clock=clock)
        acquired: list[bool] = []
        lock = threading.Lock()

        def worker() -> None:
            result = limiter.try_acquire(0)
            with lock:
                acquired.append(result)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(sum(acquired), 3)

    def test_construction_rejects_non_positive_arguments(self):
        with self.assertRaises(ValueError):
            SyncSlidingWindowLimiter(slots=1, limit=0)
        with self.assertRaises(ValueError):
            SyncSlidingWindowLimiter(slots=0, limit=1)


class FakeRerankProvider:
    """결과/오류를 FIFO 로 내는 rerank fake — httpx 없이 회전 계약만 본다."""

    def __init__(self, outcomes) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def rerank(self, *, query: str, documents) -> tuple[int, ...]:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _rerank_status_error(status_code: int) -> RerankProviderError:
    return RerankProviderError(
        f"rerank service returned status {status_code}",
        status_code=status_code,
    )


class _StaticInner:
    def __init__(self, items) -> None:
        self._items = items

    def retrieve(self, *, project_id, query, limit):
        return self._items


class KeyRotatingRerankProviderTests(unittest.TestCase):
    def _rotating(self, providers, *, limit=30, clock=None, budget=10.0):
        clock = clock if clock is not None else FakeClock()
        return KeyRotatingRerankProvider(
            providers=providers,
            limiter=SyncSlidingWindowLimiter(
                slots=len(providers), limit=limit, clock=clock
            ),
            budget_seconds=budget,
            clock=clock,
        )

    def test_rotates_on_a_5xx_error_then_succeeds(self):
        providers = [
            FakeRerankProvider([_rerank_status_error(503)]),
            FakeRerankProvider([(1, 0)]),
        ]
        rotating = self._rotating(providers)

        self.assertEqual(
            rotating.rerank(query="q", documents=("d0", "d1")), (1, 0)
        )
        self.assertEqual([p.calls for p in providers], [1, 1])

    def test_a_4xx_error_does_not_rotate(self):
        # over-strict: 요청 버그(400)를 회전으로 삼키면 진단이 늦어진다.
        rejected = _rerank_status_error(400)
        providers = [
            FakeRerankProvider([rejected]),
            FakeRerankProvider([(1, 0)]),
        ]
        rotating = self._rotating(providers)

        with self.assertRaises(RerankProviderError) as raised:
            rotating.rerank(query="q", documents=("d0", "d1"))

        self.assertIs(raised.exception, rejected)
        self.assertEqual(providers[1].calls, 0)

    def test_all_keys_limited_fails_fast_with_a_retryable_status(self):
        clock = FakeClock()
        limiter = SyncSlidingWindowLimiter(slots=2, limit=30, clock=clock)
        limiter.cool(0, 60.0)
        limiter.cool(1, 60.0)
        providers = [FakeRerankProvider([]), FakeRerankProvider([])]
        rotating = KeyRotatingRerankProvider(
            providers=providers, limiter=limiter,
            budget_seconds=10.0, clock=clock,
        )

        with self.assertRaises(RerankProviderError) as raised:
            rotating.rerank(query="q", documents=("d0", "d1"))

        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual([p.calls for p in providers], [0, 0])

    def test_exhaustion_reraises_the_last_error(self):
        last = _rerank_status_error(429)
        providers = [
            FakeRerankProvider([_rerank_status_error(500)]),
            FakeRerankProvider([last]),
        ]
        rotating = self._rotating(providers)

        with self.assertRaises(RerankProviderError) as raised:
            rotating.rerank(query="q", documents=("d0", "d1"))

        self.assertIs(raised.exception, last)

    def test_exhaustion_is_still_fail_open_at_the_retriever(self):
        # 이 슬라이스의 원래 계약(결정 4-①)은 회전이 늘어나도 그대로다 — 키 전부가
        # 소진되면 융합 순서로 내려가고, WARNING 으로 남는다.
        providers = [
            FakeRerankProvider([_rerank_status_error(503)]),
            FakeRerankProvider([_rerank_status_error(429)]),
        ]
        retriever = RerankingRetriever(
            inner=_StaticInner(("a", "b")),
            provider=self._rotating(providers),
            text_of=str,
        )

        with self.assertLogs(
            "services.application.app.context_search.rerank", level="WARNING"
        ):
            self.assertEqual(
                retriever.retrieve(project_id="p", query="q", limit=5),
                ("a", "b"),
            )


class SplitEnvListTests(unittest.TestCase):
    def test_splits_strips_and_dedups(self):
        self.assertEqual(split_env_list(" a , b ,,a "), ["a", "b"])

    def test_empty_or_separator_only_is_unset(self):
        # compose 대시 표기(`${VAR-}`)는 빈 값을 내려보낸다 — unset과 같아야 한다.
        for raw in (None, "", "  ", ",,"):
            with self.subTest(raw=raw):
                self.assertEqual(split_env_list(raw), [])


if __name__ == "__main__":
    unittest.main()
