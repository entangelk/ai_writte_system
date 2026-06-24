"""Flat agent loop terminal decision contract.

The seven literals below are the stable, mutually exclusive outcomes of one
AgentLoopRunner run, as fixed in docs/plans/flat-loop-gate.md (§종료 decision
literal). They report *why* a run ended and are orthogonal to the domain Gate
decisions composed afterward; the granular Gateway provider error literals are
preserved in the trace rather than promoted here.
"""

from __future__ import annotations

from enum import StrEnum


class LoopDecision(StrEnum):
    COMPLETED = "completed"
    AWAITING_REVIEW = "awaiting_review"
    BLOCKED = "blocked"
    BUDGET_EXHAUSTED = "budget_exhausted"
    INVALID_TOOL_ARGUMENTS = "invalid_tool_arguments"
    TOOL_ERROR = "tool_error"
    PROVIDER_ERROR = "provider_error"
