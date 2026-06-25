"""Contract tests for minimal AgentLoopRunner provider composition.

This slice connects parser/budget/completion primitives without real domain
tools. The load-bearing guards are two-directional:

* budget is checked after provider usage and before completion, so an over-limit
  finalize cannot masquerade as completed;
* provider retries consume the same iteration budget as normal provider calls;
* self-report parsing failures terminate as provider_error through the public
  runner result.
"""

import unittest

from services.application.app.agent_loop.budget import BudgetPolicy
from services.application.app.agent_loop.completion import SelfReport
from services.application.app.agent_loop.decision import LoopDecision
from services.application.app.agent_loop.runner import (
    AgentLoopRunner,
    ProviderCallError,
    ProviderTurnResult,
)


def _policy(**overrides):
    base = dict(
        max_iterations=3,
        max_wall_clock_ms=1000,
        max_total_tokens=10,
        max_tool_calls=0,
        max_repeated_calls=0,
        allows_tools=False,
        provider_retry_cap=1,
        tool_retry_cap=0,
    )
    base.update(overrides)
    return BudgetPolicy(**base)


class _QueuedProvider:
    def __init__(self, *outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _result(content='{"self_report":"finalize","artifact":{}}', *, tokens=2):
    return ProviderTurnResult(
        content=content,
        prompt_tokens=tokens // 2,
        completion_tokens=tokens - (tokens // 2),
    )


def _artifact_present(_content):
    return True


class RunnerProviderCompletionTest(unittest.TestCase):
    def test_finalize_response_completes_after_self_report_parse(self):
        provider = _QueuedProvider(_result())

        result = AgentLoopRunner(
            provider=provider,
            policy=_policy(),
            artifact_present=_artifact_present,
        ).run()

        self.assertEqual(result.decision, LoopDecision.COMPLETED)
        self.assertEqual(result.self_report, SelfReport.FINALIZE)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(
            [event.kind for event in result.trace],
            ["provider_call", "self_report", "completion"],
        )

    def test_defer_response_awaits_review(self):
        provider = _QueuedProvider(_result('{"self_report":"defer","artifact":{}}'))

        result = AgentLoopRunner(
            provider=provider,
            policy=_policy(),
            artifact_present=_artifact_present,
        ).run()

        self.assertEqual(result.decision, LoopDecision.AWAITING_REVIEW)
        self.assertEqual(result.self_report, SelfReport.DEFER)

    def test_invalid_self_report_maps_to_provider_error(self):
        provider = _QueuedProvider(_result('{"artifact":{}}'))

        result = AgentLoopRunner(
            provider=provider,
            policy=_policy(),
            artifact_present=_artifact_present,
        ).run()

        self.assertEqual(result.decision, LoopDecision.PROVIDER_ERROR)
        self.assertEqual(result.trace[-1].kind, "self_report")


class RunnerBudgetOrderingTest(unittest.TestCase):
    def test_token_overrun_is_budget_exhausted_before_completion(self):
        # I2 forward-lock: this content would parse as finalize and the artifact
        # exists, but post-accounting token overrun wins before completion.
        provider = _QueuedProvider(_result(tokens=2))

        result = AgentLoopRunner(
            provider=provider,
            policy=_policy(max_total_tokens=1),
            artifact_present=_artifact_present,
        ).run()

        self.assertEqual(result.decision, LoopDecision.BUDGET_EXHAUSTED)
        self.assertNotIn("self_report", [event.kind for event in result.trace])

    def test_equal_token_limit_can_complete(self):
        # over-strict guard: == limit remains in budget and may complete.
        provider = _QueuedProvider(_result(tokens=2))

        result = AgentLoopRunner(
            provider=provider,
            policy=_policy(max_total_tokens=2),
            artifact_present=_artifact_present,
        ).run()

        self.assertEqual(result.decision, LoopDecision.COMPLETED)


class RunnerRetryBudgetTest(unittest.TestCase):
    def test_provider_retry_consumes_iteration_budget(self):
        # Under-strict guard: a retry is not a free path. With max_iterations=1,
        # the retry cap is available but the next provider attempt is blocked.
        provider = _QueuedProvider(
            ProviderCallError("provider_timeout", retryable=True),
            _result(),
        )

        result = AgentLoopRunner(
            provider=provider,
            policy=_policy(max_iterations=1, provider_retry_cap=1),
            artifact_present=_artifact_present,
        ).run()

        self.assertEqual(result.decision, LoopDecision.BUDGET_EXHAUSTED)
        self.assertEqual(result.preserved_error_literal, "provider_error")
        self.assertEqual(provider.calls, 1)

    def test_provider_retry_can_complete_when_iteration_budget_remains(self):
        # over-strict guard: retry is allowed when both cap and normal iteration
        # budget permit the next provider attempt.
        provider = _QueuedProvider(
            ProviderCallError("provider_timeout", retryable=True),
            _result(),
        )

        result = AgentLoopRunner(
            provider=provider,
            policy=_policy(max_iterations=2, provider_retry_cap=1),
            artifact_present=_artifact_present,
        ).run()

        self.assertEqual(result.decision, LoopDecision.COMPLETED)
        self.assertEqual(provider.calls, 2)
        self.assertIn("provider_retry", [event.kind for event in result.trace])


if __name__ == "__main__":
    unittest.main()
