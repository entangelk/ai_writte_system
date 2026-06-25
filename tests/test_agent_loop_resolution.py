"""Contract tests for flat agent loop retry and budget decision synthesis.

Locks the failure/budget half of the terminal decision synthesis defined in
docs/plans/flat-loop-gate.md (§retry와 terminal decision 우선순위, §budget boundary
matrix). resolve_retry maps a failure to a retry or terminal decision;
next_step_budget_decision maps the budget state for the next unit of work to
budget_exhausted. Each branch is guarded in both directions: the should-fire
branch (cap/budget conditions produce the documented decision) and the
over-strict/under-strict guards (no false retry, no masking budget exhaustion as
an error or as completion).
"""

import unittest

from services.application.app.agent_loop.budget import BudgetPolicy, BudgetTracker
from services.application.app.agent_loop.completion import SelfReport, judge_completion
from services.application.app.agent_loop.decision import LoopDecision
from services.application.app.agent_loop.resolution import (
    ErrorKind,
    resolve_retry,
    next_step_budget_decision,
)


def _policy(**overrides):
    base = dict(
        max_iterations=2,
        max_wall_clock_ms=1000,
        max_total_tokens=100,
        max_tool_calls=2,
        max_repeated_calls=2,
        allows_tools=True,
        provider_retry_cap=2,
        tool_retry_cap=1,
    )
    base.update(overrides)
    return BudgetPolicy(**base)


def _started_tracker(policy=None, *, now=0):
    clock = {"now": now}
    tracker = BudgetTracker(policy or _policy(), now_ms=lambda: clock["now"])
    tracker.start()
    return tracker, clock


class ResolveRetryNonRetryableTest(unittest.TestCase):
    def test_non_retryable_provider_terminates_immediately(self):
        outcome = resolve_retry(
            error_kind=ErrorKind.PROVIDER,
            retryable=False,
            retries_remaining=3,
            budget_permits_next=True,
        )
        self.assertFalse(outcome.retry)
        self.assertEqual(outcome.decision, LoopDecision.PROVIDER_ERROR)
        self.assertIsNone(outcome.preserved_literal)

    def test_non_retryable_tool_terminates_immediately(self):
        outcome = resolve_retry(
            error_kind=ErrorKind.TOOL,
            retryable=False,
            retries_remaining=3,
            budget_permits_next=True,
        )
        self.assertFalse(outcome.retry)
        self.assertEqual(outcome.decision, LoopDecision.TOOL_ERROR)
        self.assertIsNone(outcome.preserved_literal)


class ResolveRetryCapExhaustedTest(unittest.TestCase):
    def test_retryable_provider_with_cap_exhausted_is_provider_error(self):
        outcome = resolve_retry(
            error_kind=ErrorKind.PROVIDER,
            retryable=True,
            retries_remaining=0,
            budget_permits_next=True,
        )
        self.assertFalse(outcome.retry)
        self.assertEqual(outcome.decision, LoopDecision.PROVIDER_ERROR)
        self.assertIsNone(outcome.preserved_literal)

    def test_retryable_tool_with_cap_exhausted_is_tool_error(self):
        outcome = resolve_retry(
            error_kind=ErrorKind.TOOL,
            retryable=True,
            retries_remaining=0,
            budget_permits_next=True,
        )
        self.assertEqual(outcome.decision, LoopDecision.TOOL_ERROR)

    def test_cap_exhausted_takes_precedence_over_budget_blocked(self):
        # retry cap exhausted wins over a blocked budget: the run ends with the
        # error decision, not budget_exhausted, and no literal is preserved.
        outcome = resolve_retry(
            error_kind=ErrorKind.PROVIDER,
            retryable=True,
            retries_remaining=0,
            budget_permits_next=False,
        )
        self.assertEqual(outcome.decision, LoopDecision.PROVIDER_ERROR)
        self.assertIsNone(outcome.preserved_literal)


class ResolveRetryRetryPathTest(unittest.TestCase):
    def test_cap_remaining_and_budget_permits_retries_for_provider(self):
        outcome = resolve_retry(
            error_kind=ErrorKind.PROVIDER,
            retryable=True,
            retries_remaining=1,
            budget_permits_next=True,
        )
        self.assertTrue(outcome.retry)
        self.assertIsNone(outcome.decision)
        self.assertIsNone(outcome.preserved_literal)

    def test_cap_remaining_and_budget_permits_retries_for_tool(self):
        outcome = resolve_retry(
            error_kind=ErrorKind.TOOL,
            retryable=True,
            retries_remaining=2,
            budget_permits_next=True,
        )
        self.assertTrue(outcome.retry)
        self.assertIsNone(outcome.decision)


class ResolveRetryBudgetBlockedTest(unittest.TestCase):
    def test_provider_retry_blocked_by_budget_is_budget_exhausted_with_literal(self):
        # retryable, cap remaining, but a budget blocks the next attempt:
        # budget_exhausted, with the original provider_error literal preserved.
        outcome = resolve_retry(
            error_kind=ErrorKind.PROVIDER,
            retryable=True,
            retries_remaining=1,
            budget_permits_next=False,
        )
        self.assertFalse(outcome.retry)
        self.assertEqual(outcome.decision, LoopDecision.BUDGET_EXHAUSTED)
        self.assertEqual(outcome.preserved_literal, "provider_error")

    def test_tool_retry_blocked_by_budget_is_budget_exhausted_with_literal(self):
        outcome = resolve_retry(
            error_kind=ErrorKind.TOOL,
            retryable=True,
            retries_remaining=1,
            budget_permits_next=False,
        )
        self.assertEqual(outcome.decision, LoopDecision.BUDGET_EXHAUSTED)
        self.assertEqual(outcome.preserved_literal, "tool_error")


class NextStepBudgetDecisionTest(unittest.TestCase):
    def test_clear_budget_returns_none(self):
        tracker, _ = _started_tracker()
        self.assertIsNone(next_step_budget_decision(tracker))

    def test_iteration_n_plus_one_blocks(self):
        tracker, _ = _started_tracker(_policy(max_iterations=1))
        self.assertIsNone(next_step_budget_decision(tracker))  # 1st allowed
        tracker.record_iteration()
        self.assertEqual(
            next_step_budget_decision(tracker), LoopDecision.BUDGET_EXHAUSTED
        )

    def test_token_equal_to_limit_is_allowed(self):
        # post-accounting: accumulated == limit completion is in budget.
        tracker, _ = _started_tracker(_policy(max_total_tokens=10))
        tracker.record_tokens(prompt_tokens=6, completion_tokens=4)
        self.assertIsNone(next_step_budget_decision(tracker, needs_iteration=False))

    def test_token_over_limit_blocks(self):
        tracker, _ = _started_tracker(_policy(max_total_tokens=10))
        tracker.record_tokens(prompt_tokens=6, completion_tokens=4)
        tracker.record_tokens(prompt_tokens=1, completion_tokens=0)
        self.assertEqual(
            next_step_budget_decision(tracker, needs_iteration=False),
            LoopDecision.BUDGET_EXHAUSTED,
        )

    def test_wall_clock_deadline_blocks(self):
        tracker, clock = _started_tracker(_policy(max_wall_clock_ms=100))
        clock["now"] = 100  # deadline reached
        self.assertEqual(
            next_step_budget_decision(tracker, needs_iteration=False),
            LoopDecision.BUDGET_EXHAUSTED,
        )

    def test_tool_call_n_plus_one_blocks(self):
        tracker, _ = _started_tracker(_policy(max_tool_calls=1))
        self.assertIsNone(
            next_step_budget_decision(
                tracker, needs_iteration=False, tool_signature="search:{}"
            )
        )
        tracker.record_tool_call("search:{}")
        self.assertEqual(
            next_step_budget_decision(
                tracker, needs_iteration=False, tool_signature="search:{}"
            ),
            LoopDecision.BUDGET_EXHAUSTED,
        )

    def test_repeated_call_n_plus_one_blocks_same_signature_only(self):
        tracker, _ = _started_tracker(_policy(max_repeated_calls=1))
        tracker.record_tool_call("search:{\"q\":1}")
        # same signature: N+1 blocked
        self.assertEqual(
            next_step_budget_decision(
                tracker, needs_iteration=False, tool_signature="search:{\"q\":1}"
            ),
            LoopDecision.BUDGET_EXHAUSTED,
        )
        # over-strict guard: same tool, different valid args is not a repeat
        self.assertIsNone(
            next_step_budget_decision(
                tracker, needs_iteration=False, tool_signature="search:{\"q\":2}"
            )
        )

    def test_tool_only_step_not_blocked_by_iteration(self):
        # over-strict: a non-iteration (tool-only) next step must not be blocked
        # by an exhausted iteration dimension.
        tracker, _ = _started_tracker(_policy(max_iterations=1))
        tracker.record_iteration()
        self.assertIsNone(
            next_step_budget_decision(
                tracker, needs_iteration=False, tool_signature="search:{}"
            )
        )


class BudgetExhaustedPrecedenceTest(unittest.TestCase):
    def test_exhausted_budget_takes_precedence_over_completion(self):
        # under-strict guard (§budget boundary matrix, §boundary matrix): an
        # exhausted budget terminates the run as budget_exhausted even when an
        # artifact is present and the model finalizes -- never masked as
        # completed. judge_completion would say completed, but the budget check
        # fires first.
        tracker, _ = _started_tracker(_policy(max_total_tokens=10))
        tracker.record_tokens(prompt_tokens=11, completion_tokens=0)
        self.assertEqual(
            next_step_budget_decision(tracker, needs_iteration=False),
            LoopDecision.BUDGET_EXHAUSTED,
        )
        # and the completion judgment, reached only when budget is clear, is what
        # a finalize would yield:
        self.assertEqual(
            judge_completion(True, SelfReport.FINALIZE), LoopDecision.COMPLETED
        )


if __name__ == "__main__":
    unittest.main()
