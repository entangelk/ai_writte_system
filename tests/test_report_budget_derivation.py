"""R-a — report 입력 예산을 창에서 유도한다 (오너 결정 2026-07-31: (ii)+(iii)).

여기서 잠그는 계약:
1. 창을 알면 **줄인다**(요청값이 창에 안 맞으면 유도값으로 내려간다).
2. 창을 모르면 **건드리지 않는다**(요청값 그대로 — 종전 동작).
3. **늘리지 않는다**(창이 커도 요청보다 큰 예산을 돌려주지 않는다).
4. 유도값은 실제로 **가드를 통과하는 크기**다(2026-07-31 베타 실측 위에서 검산).
"""

import unittest

from services.application.app.writing.report_budget import (
    FRAMING_RESERVE_TOKENS,
    MIN_CONTEXT_BUDGET_TOKENS,
    PACKAGE_ACCOUNTING_RATIO,
    candidate_tokens_from_text,
    derive_context_budget,
)


class _Capabilities:
    """창·계수를 아는 가짜 게이트웨이. `None`은 "모른다"를 뜻한다."""

    def __init__(self, *, window=None, tokens=None):
        self._window = window
        self._tokens = tokens
        self.window_calls = 0
        self.token_calls = 0

    async def context_window(self):
        self.window_calls += 1
        return self._window

    async def count_tokens(self, text):
        self.token_calls += 1
        return self._tokens


# 2026-07-31 베타 실측(`scripts/report_budget_measure.py`): 창 16,384 · report 출력 상한
# 6,144 · report system 템플릿 465 tok · `long` 후보 4,159 tok.
_WINDOW = 16384
_CAP = 6144
_SYSTEM = 465
_LONG_CANDIDATE = 4159


async def _derive(**overrides):
    kwargs = dict(
        requested_tokens=8192,
        capabilities=_Capabilities(window=_WINDOW, tokens=_SYSTEM),
        report_output_cap=_CAP,
        report_system_template="report system template",
        candidate_tokens_upper_bound=_LONG_CANDIDATE,
    )
    kwargs.update(overrides)
    return await derive_context_budget(**kwargs)


class DerivationTest(unittest.IsolatedAsyncioTestCase):
    async def test_it_shrinks_the_requested_budget_to_what_the_window_allows(self):
        derived = await _derive()
        allowance = _WINDOW - _CAP - _SYSTEM - _LONG_CANDIDATE - FRAMING_RESERVE_TOKENS
        self.assertEqual(derived, int(allowance * PACKAGE_ACCOUNTING_RATIO))
        self.assertLess(derived, 8192)

    async def test_the_derived_budget_actually_fits_the_window(self):
        """유도가 **가드를 통과하는 값**을 내는지 실측 위에서 검산한다.

        회계 예산 → 실제 렌더링은 `예산 / 비율`이다(회계가 렌더링보다 작다). 그 렌더링에
        고정 오버헤드와 출력 상한을 더한 값이 창을 넘으면 유도는 제 일을 못 한 것이다 —
        가드가 400을 낼 테니 조용히 깨지지는 않지만, 그것이 바로 R-a가 없애려는 상태다.
        """
        derived = await _derive()
        # 실측 비율의 **높은** 쪽(0.979)으로 되돌려도 들어가야 한다 — 유도가 낮은 쪽(0.96)을
        # 쓰는 이유가 이 여유다.
        rendered = derived / 0.979
        total = rendered + _SYSTEM + _LONG_CANDIDATE + FRAMING_RESERVE_TOKENS + _CAP
        self.assertLessEqual(total, _WINDOW)

    async def test_a_short_candidate_keeps_more_context_than_a_long_one(self):
        """(iii)의 핵심 — 흔한 경우를 굶기지 않는다."""
        short = await _derive(candidate_tokens_upper_bound=1024)
        long_ = await _derive(candidate_tokens_upper_bound=4096)
        self.assertGreater(short, long_)

    async def test_a_bigger_window_allows_a_bigger_budget(self):
        """(ii)의 핵심 — 창을 키운 배포(알파 32768)가 자동으로 넓어진다."""
        small = await _derive(requested_tokens=32768, capabilities=_Capabilities(
            window=16384, tokens=_SYSTEM))
        big = await _derive(requested_tokens=32768, capabilities=_Capabilities(
            window=32768, tokens=_SYSTEM))
        self.assertGreater(big, small)


class FallbackTest(unittest.IsolatedAsyncioTestCase):
    """유도가 자기 실패로 기능을 깨뜨리지 않는다(K-3 가드와 같은 계약)."""

    async def test_an_unknown_window_leaves_the_requested_budget_alone(self):
        self.assertEqual(await _derive(capabilities=_Capabilities(window=None)), 8192)

    async def test_no_gateway_leaves_the_requested_budget_alone(self):
        self.assertEqual(await _derive(capabilities=None), 8192)

    async def test_an_uncountable_template_falls_back_to_the_estimate(self):
        """서버가 못 세면 자체 추정으로 떨어진다 — 그리고 그 추정은 **더 좁은** 쪽이다.

        report 템플릿은 영문이라 `len/1.7`이 2배 넘게 과대평가한다(실측 1,660자 → 976 vs
        465). 과대평가는 예산을 좁히므로 창을 넘기는 방향이 아니다.
        """
        template = "a" * 1700
        counted = await _derive(
            capabilities=_Capabilities(window=_WINDOW, tokens=465),
            report_system_template=template,
        )
        estimated = await _derive(
            capabilities=_Capabilities(window=_WINDOW, tokens=None),
            report_system_template=template,
        )
        self.assertLess(estimated, counted)


class ShrinkOnlyTest(unittest.IsolatedAsyncioTestCase):
    """**늘리지 않는다** — over-strict 가드.

    창이 아주 크면 산식은 요청보다 큰 값을 낸다. 그것을 그대로 쓰면 호출자가 요청하지 않은
    비용(더 큰 패키지 = 더 느리고 비싼 호출)을 앱이 임의로 쓰는 것이다. 유도는 **창에 맞게
    줄이는** 장치이지 예산 정책을 대신 정하는 장치가 아니다.
    """

    async def test_a_huge_window_does_not_inflate_a_small_request(self):
        derived = await _derive(
            requested_tokens=2048, capabilities=_Capabilities(window=131072, tokens=_SYSTEM),
        )
        self.assertEqual(derived, 2048)

    async def test_a_window_smaller_than_the_fixed_overhead_still_yields_a_valid_budget(self):
        """`ContextBudget.max_tokens`는 양수여야 한다 — 0이나 음수를 만들면 요청이 400이 된다.

        그런 배포에서 남는 초과는 여기서 숨기지 않고 **가드가 400으로** 말한다.
        """
        derived = await _derive(capabilities=_Capabilities(window=2048, tokens=_SYSTEM))
        self.assertEqual(derived, MIN_CONTEXT_BUDGET_TOKENS)
        self.assertGreater(derived, 0)


class CandidateEstimateTest(unittest.TestCase):
    def test_the_candidate_estimate_uses_the_korean_density(self):
        # `len/1.7` — K-1(a)에서 실 원고 429블록으로 보정한 상수.
        self.assertEqual(candidate_tokens_from_text("가" * 1700), 1000)


if __name__ == "__main__":
    unittest.main()
