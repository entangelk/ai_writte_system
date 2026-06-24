"""Contract tests for the flat agent loop multi-dimensional budget.

Locks the budget policy validation and per-dimension metering defined in
docs/plans/flat-loop-gate.md (§Budget 계약, budget boundary matrix). Each
dimension is guarded in both directions: the should-fire branch (the limit
blocks the next unit of work) and the should-NOT-fire branch (a normal in-budget
case is not over-blocked).

Scope: this slice covers policy validation and the metering primitives only.
Mapping a blocked dimension to LoopDecision.BUDGET_EXHAUSTED, retry accounting,
and tool-call signature normalization arrive in later sub-slices, so signatures
are passed in already-normalized here.
"""

import unittest

from services.application.app.agent_loop.budget import (
    BudgetPolicy,
    BudgetTracker,
    InvalidBudgetPolicy,
)


def _tool_policy(**overrides):
    base = dict(
        max_iterations=10,
        max_wall_clock_ms=1000,
        max_total_tokens=100,
        max_tool_calls=5,
        max_repeated_calls=2,
        allows_tools=True,
    )
    base.update(overrides)
    return BudgetPolicy(**base)


def _writing_policy(**overrides):
    base = dict(
        max_iterations=4,
        max_wall_clock_ms=1000,
        max_total_tokens=100,
        max_tool_calls=0,
        max_repeated_calls=0,
        allows_tools=False,
    )
    base.update(overrides)
    return BudgetPolicy(**base)


class BudgetPolicyValidationTest(unittest.TestCase):
    def test_valid_tool_and_tool_free_policies_construct(self):
        self.assertTrue(_tool_policy().allows_tools)
        self.assertFalse(_writing_policy().allows_tools)

    def test_positive_dimensions_allow_lower_bound_one(self):
        policy = _tool_policy(
            max_iterations=1, max_wall_clock_ms=1, max_total_tokens=1
        )
        self.assertEqual(policy.max_iterations, 1)

    def test_iteration_wall_token_must_be_at_least_one(self):
        for name in ("max_iterations", "max_wall_clock_ms", "max_total_tokens"):
            with self.subTest(dimension=name):
                with self.assertRaises(InvalidBudgetPolicy):
                    _tool_policy(**{name: 0})

    def test_negative_dimensions_are_rejected(self):
        for name in ("max_tool_calls", "max_repeated_calls"):
            with self.subTest(dimension=name):
                with self.assertRaises(InvalidBudgetPolicy):
                    _tool_policy(**{name: -1})

    def test_bool_is_not_accepted_as_an_integer_dimension(self):
        # bool is a subclass of int; a True iteration budget is a contract error.
        with self.assertRaises(InvalidBudgetPolicy):
            _tool_policy(max_iterations=True)

    def test_tool_using_profile_requires_tool_budgets_at_least_one(self):
        with self.assertRaises(InvalidBudgetPolicy):
            _tool_policy(max_tool_calls=0)
        with self.assertRaises(InvalidBudgetPolicy):
            _tool_policy(max_repeated_calls=0)

    def test_tool_free_profile_requires_zero_tool_budgets(self):
        with self.assertRaises(InvalidBudgetPolicy):
            _writing_policy(max_tool_calls=1)
        with self.assertRaises(InvalidBudgetPolicy):
            _writing_policy(max_repeated_calls=1)


class IterationBudgetTest(unittest.TestCase):
    def test_allows_up_to_n_then_blocks_n_plus_one(self):
        tracker = BudgetTracker(_tool_policy(max_iterations=2))
        self.assertTrue(tracker.can_start_iteration())
        tracker.record_iteration()
        self.assertTrue(tracker.can_start_iteration())  # 2nd allowed, not over-blocked
        tracker.record_iteration()
        self.assertFalse(tracker.can_start_iteration())  # N+1 blocked


class TokenBudgetTest(unittest.TestCase):
    def test_accumulated_equal_to_limit_is_not_exceeded(self):
        # post-accounting: == limit completion is allowed.
        tracker = BudgetTracker(_tool_policy(max_total_tokens=10))
        tracker.record_tokens(prompt_tokens=6, completion_tokens=4)
        self.assertFalse(tracker.is_token_budget_exceeded())

    def test_accumulated_over_limit_is_exceeded(self):
        tracker = BudgetTracker(_tool_policy(max_total_tokens=10))
        tracker.record_tokens(prompt_tokens=6, completion_tokens=4)
        tracker.record_tokens(prompt_tokens=1, completion_tokens=0)
        self.assertTrue(tracker.is_token_budget_exceeded())


class WallClockBudgetTest(unittest.TestCase):
    def test_deadline_reached_only_at_or_after_the_limit(self):
        clock = {"now": 0}
        tracker = BudgetTracker(
            _tool_policy(max_wall_clock_ms=100), now_ms=lambda: clock["now"]
        )
        tracker.start()
        clock["now"] = 99
        self.assertFalse(tracker.is_deadline_reached())  # in budget
        clock["now"] = 100
        self.assertTrue(tracker.is_deadline_reached())  # deadline reached
        clock["now"] = 101
        self.assertTrue(tracker.is_deadline_reached())

    def test_deadline_check_before_start_is_an_error(self):
        tracker = BudgetTracker(_tool_policy())
        with self.assertRaises(RuntimeError):
            tracker.is_deadline_reached()


class ToolCallBudgetTest(unittest.TestCase):
    def test_allows_up_to_n_then_blocks_n_plus_one(self):
        tracker = BudgetTracker(_tool_policy(max_tool_calls=2))
        self.assertTrue(tracker.can_start_tool_call())
        tracker.record_tool_call("search_memory:{}")
        self.assertTrue(tracker.can_start_tool_call())  # 2nd allowed
        tracker.record_tool_call("search_memory:{}")
        self.assertFalse(tracker.can_start_tool_call())  # N+1 blocked

    def test_lower_bound_one_allows_first_then_blocks_second(self):
        # N=1 is the minimum operating budget for a tool-using profile; the 1st
        # call is allowed and the 2nd is blocked.
        tracker = BudgetTracker(_tool_policy(max_tool_calls=1))
        self.assertTrue(tracker.can_start_tool_call())
        tracker.record_tool_call("search_memory:{}")
        self.assertFalse(tracker.can_start_tool_call())


class RepeatedCallBudgetTest(unittest.TestCase):
    def test_same_signature_allows_n_then_blocks_n_plus_one(self):
        tracker = BudgetTracker(_tool_policy(max_repeated_calls=2))
        sig = "search_memory:{\"q\":1}"
        self.assertTrue(tracker.can_start_repeated_call(sig))
        tracker.record_tool_call(sig)
        self.assertTrue(tracker.can_start_repeated_call(sig))  # 2nd allowed
        tracker.record_tool_call(sig)
        self.assertFalse(tracker.can_start_repeated_call(sig))  # N+1 blocked

    def test_lower_bound_one_allows_first_then_blocks_second(self):
        # N=1 minimum operating budget: same signature once, then blocked.
        tracker = BudgetTracker(_tool_policy(max_repeated_calls=1))
        sig = "search_memory:{\"q\":1}"
        self.assertTrue(tracker.can_start_repeated_call(sig))
        tracker.record_tool_call(sig)
        self.assertFalse(tracker.can_start_repeated_call(sig))

    def test_different_signature_is_not_counted_as_a_repeat(self):
        # over-strict guard: same tool, different valid arguments must not be
        # mistaken for a repeated call.
        tracker = BudgetTracker(_tool_policy(max_repeated_calls=1))
        tracker.record_tool_call("search_memory:{\"q\":1}")
        self.assertTrue(
            tracker.can_start_repeated_call("search_memory:{\"q\":2}")
        )


if __name__ == "__main__":
    unittest.main()
