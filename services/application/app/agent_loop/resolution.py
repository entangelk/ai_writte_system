"""Flat agent loop retry and budget decision synthesis contract.

Implements the failure/budget half of the terminal decision synthesis fixed in
docs/plans/flat-loop-gate.md (§retry와 terminal decision 우선순위, §budget boundary
matrix). These are the pure decision primitives a future runner calls at its
decision points; they do not drive a loop or call any provider/tool. Completion
judgment lives in completion.py; together they cover the seven terminal
decisions with the precedence

    error (at a failure point) > blocked/invalid_tool_arguments (registry/setup)
    > budget_exhausted (before the next unit of work) > completion (success).

Each primitive is checked at its own decision point, so exactly one fires.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from services.application.app.agent_loop.budget import BudgetTracker
from services.application.app.agent_loop.decision import LoopDecision


class ErrorKind(StrEnum):
    """Which side of the loop produced a failure."""

    PROVIDER = "provider"
    TOOL = "tool"


@dataclass(frozen=True)
class RetryOutcome:
    """Result of resolving a failure into either a retry or a terminal decision.

    ``decision`` is ``None`` when the run should retry (non-terminal); otherwise
    it is the terminal decision. ``preserved_literal`` carries the original
    error literal ("provider_error"/"tool_error") for the trace when a budget
    blocks a retryable failure and the terminal decision becomes
    ``budget_exhausted`` (flat-loop-gate.md §retry, §boundary matrix).
    """

    decision: LoopDecision | None
    preserved_literal: str | None = None

    @property
    def retry(self) -> bool:
        return self.decision is None


def _error_decision(error_kind: ErrorKind) -> LoopDecision:
    if error_kind is ErrorKind.PROVIDER:
        return LoopDecision.PROVIDER_ERROR
    return LoopDecision.TOOL_ERROR


def resolve_retry(
    *,
    error_kind: ErrorKind,
    retryable: bool,
    retries_remaining: int,
    budget_permits_next: bool,
) -> RetryOutcome:
    """Resolve a failure into a retry or a terminal decision.

    Precedence (flat-loop-gate.md §retry와 terminal decision 우선순위):

    * non-retryable -> terminal error decision immediately;
    * retryable but the retry cap is exhausted (``retries_remaining <= 0``) ->
      the error decision;
    * retryable, cap remaining, and budget permits the next attempt -> retry
      (non-terminal);
    * retryable, cap remaining, but a budget dimension blocks the next attempt
      -> ``budget_exhausted`` with the original error literal preserved.

    The retry cap's policy placement (numeric defaults deferred to the Gemma Q4
    benchmark) is irrelevant here: the caller passes ``retries_remaining``,
    derived from the matching ``BudgetPolicy`` retry cap (``provider_retry_cap``
    / ``tool_retry_cap``) minus retries already used.
    """
    error_decision = _error_decision(error_kind)

    if not retryable:
        return RetryOutcome(decision=error_decision)

    if retries_remaining <= 0:
        return RetryOutcome(decision=error_decision)

    if budget_permits_next:
        return RetryOutcome(decision=None)

    return RetryOutcome(
        decision=LoopDecision.BUDGET_EXHAUSTED,
        preserved_literal=error_decision.value,
    )


def next_step_budget_decision(
    tracker: BudgetTracker,
    *,
    needs_iteration: bool = True,
    tool_signature: str | None = None,
) -> LoopDecision | None:
    """Map the budget state for the next unit of work to a terminal decision.

    Returns ``BUDGET_EXHAUSTED`` if any dimension blocks the next step, else
    ``None`` (OK to proceed). The runner must have started the tracker. Wall-clock
    deadline and token overrun are global stop signals checked regardless of the
    next step type; iteration is checked only when the next step is a provider
    call, and the tool dimensions only when a tool call is next
    (flat-loop-gate.md §budget boundary matrix). This fires before completion, so
    an exhausted budget is never masked as ``completed``.
    """
    if needs_iteration and not tracker.can_start_iteration():
        return LoopDecision.BUDGET_EXHAUSTED
    if tracker.is_deadline_reached():
        return LoopDecision.BUDGET_EXHAUSTED
    if tracker.is_token_budget_exceeded():
        return LoopDecision.BUDGET_EXHAUSTED
    if tool_signature is not None:
        if not tracker.can_start_tool_call() or not tracker.can_start_repeated_call(
            tool_signature
        ):
            return LoopDecision.BUDGET_EXHAUSTED
    return None
