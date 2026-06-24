"""Contract tests for the flat agent loop terminal decision literal.

Locks the seven mutually exclusive terminal decisions defined in
docs/plans/flat-loop-gate.md (종료 decision literal). The string values are a
public contract consumed by trace logging and downstream Gate composition, so a
literal rename or count change must fail here.
"""

import unittest

from services.application.app.agent_loop.decision import LoopDecision


class LoopDecisionLiteralTest(unittest.TestCase):
    def test_exactly_seven_terminal_decisions(self):
        # The contract fixes exactly seven decisions; adding or dropping one is a
        # breaking change that must be made deliberately.
        self.assertEqual(len(LoopDecision), 7)

    def test_decision_string_values_match_contract(self):
        self.assertEqual(LoopDecision.COMPLETED.value, "completed")
        self.assertEqual(LoopDecision.AWAITING_REVIEW.value, "awaiting_review")
        self.assertEqual(LoopDecision.BLOCKED.value, "blocked")
        self.assertEqual(LoopDecision.BUDGET_EXHAUSTED.value, "budget_exhausted")
        self.assertEqual(
            LoopDecision.INVALID_TOOL_ARGUMENTS.value, "invalid_tool_arguments"
        )
        self.assertEqual(LoopDecision.TOOL_ERROR.value, "tool_error")
        self.assertEqual(LoopDecision.PROVIDER_ERROR.value, "provider_error")

    def test_values_are_unique(self):
        values = [decision.value for decision in LoopDecision]
        self.assertEqual(len(values), len(set(values)))

    def test_decision_is_string_comparable(self):
        # StrEnum lets trace payloads compare against the raw literal.
        self.assertEqual(LoopDecision.COMPLETED, "completed")


if __name__ == "__main__":
    unittest.main()
