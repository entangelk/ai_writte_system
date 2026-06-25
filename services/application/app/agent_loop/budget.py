"""Flat agent loop multi-dimensional budget contract.

Implements the budget policy and per-dimension metering fixed in
docs/plans/flat-loop-gate.md (§Budget 계약). A run is bounded along five
dimensions; an invalid or self-contradictory policy is rejected before any
provider call so the runner can terminate as `blocked`.

This module owns policy validation, the metering primitives, and provider-usage
defense. Mapping an exceeded dimension to LoopDecision.BUDGET_EXHAUSTED and retry
accounting live in resolution.py (A3); callers pass already-normalized signatures
to the repeated-call metering here. record_tokens rejects missing/invalid provider
usage as ``provider_error`` rather than defaulting it to 0.
"""

from __future__ import annotations

from time import monotonic_ns
from typing import Callable

from services.application.app.agent_loop.decision import LoopDecision

_POSITIVE_DIMENSIONS = ("max_iterations", "max_wall_clock_ms", "max_total_tokens")
_TOOL_DIMENSIONS = ("max_tool_calls", "max_repeated_calls")
_RETRY_DIMENSIONS = ("provider_retry_cap", "tool_retry_cap")


class InvalidBudgetPolicy(ValueError):
    """Raised when a budget policy is missing a dimension or self-contradictory.

    A missing/negative/self-contradictory policy terminates before any provider
    call as ``blocked`` (flat-loop-gate.md §Budget 계약). The ``decision``
    attribute lets a future runner map budget/registry exceptions to a terminal
    decision uniformly.
    """

    decision = LoopDecision.BLOCKED


class InvalidProviderUsage(ValueError):
    """Raised when provider-reported token usage is missing or invalid.

    Per docs/plans/flat-loop-gate.md (§Budget 계약) invalid usage is never
    coerced to 0; it terminates the run as ``provider_error``. The ``decision``
    attribute lets a future runner map budget/registry exceptions to a terminal
    decision uniformly.
    """

    decision = LoopDecision.PROVIDER_ERROR


def _default_now_ms() -> int:
    return monotonic_ns() // 1_000_000


def _is_int(value: object) -> bool:
    # bool is a subclass of int; reject it so a True budget is never silently
    # treated as 1.
    return isinstance(value, int) and not isinstance(value, bool)


def _require_token_count(value: object, name: str) -> int:
    # Provider-reported usage is never coerced: a missing/negative/non-integer
    # count (including a bool) terminates as provider_error, not a silent 0.
    if not _is_int(value) or value < 0:
        raise InvalidProviderUsage(f"{name} must be a non-negative integer")
    return value


class BudgetPolicy:
    """Validated, immutable run policy fixed at run start.

    Holds the five consumption budget dimensions, ``allows_tools``, and the
    provider/tool retry caps (flat-loop-gate.md §retry: mandatory task-profile
    policy values, ``>= 0``). A missing/negative/self-contradictory policy is
    rejected before any provider call so the runner can terminate as ``blocked``.
    """

    __slots__ = (
        "max_iterations",
        "max_wall_clock_ms",
        "max_total_tokens",
        "max_tool_calls",
        "max_repeated_calls",
        "allows_tools",
        "provider_retry_cap",
        "tool_retry_cap",
    )

    def __init__(
        self,
        *,
        max_iterations: int,
        max_wall_clock_ms: int,
        max_total_tokens: int,
        max_tool_calls: int,
        max_repeated_calls: int,
        allows_tools: bool,
        provider_retry_cap: int,
        tool_retry_cap: int,
    ) -> None:
        for name in _POSITIVE_DIMENSIONS:
            value = locals()[name]
            if not _is_int(value) or value < 1:
                raise InvalidBudgetPolicy(f"{name} must be an integer >= 1")
        for name in _TOOL_DIMENSIONS:
            value = locals()[name]
            if not _is_int(value) or value < 0:
                raise InvalidBudgetPolicy(f"{name} must be an integer >= 0")
        for name in _RETRY_DIMENSIONS:
            value = locals()[name]
            if not _is_int(value) or value < 0:
                raise InvalidBudgetPolicy(f"{name} must be an integer >= 0")
        if not isinstance(allows_tools, bool):
            raise InvalidBudgetPolicy("allows_tools must be a bool")
        if allows_tools:
            if max_tool_calls < 1 or max_repeated_calls < 1:
                raise InvalidBudgetPolicy(
                    "tool-using profile requires tool budgets >= 1"
                )
        elif max_tool_calls != 0 or max_repeated_calls != 0:
            raise InvalidBudgetPolicy(
                "tool-free profile requires zero tool budgets"
            )

        self.max_iterations = max_iterations
        self.max_wall_clock_ms = max_wall_clock_ms
        self.max_total_tokens = max_total_tokens
        self.max_tool_calls = max_tool_calls
        self.max_repeated_calls = max_repeated_calls
        self.allows_tools = allows_tools
        self.provider_retry_cap = provider_retry_cap
        self.tool_retry_cap = tool_retry_cap


class BudgetTracker:
    """Meters one run against its BudgetPolicy across all five dimensions.

    Count dimensions (iteration, tool-call, repeated-call) allow the 1..N-th unit
    of work and block the N+1-th via `can_start_*`. Wall-clock is a deadline set
    at `start`. Token is a post-accounting dimension: a response may carry the
    accumulated total over the limit, so the runner records usage and then checks
    `is_token_budget_exceeded` (`== limit` is still in budget, `> limit` is not).
    """

    def __init__(
        self,
        policy: BudgetPolicy,
        *,
        now_ms: Callable[[], int] = _default_now_ms,
    ) -> None:
        self._policy = policy
        self._now_ms = now_ms
        self._iterations = 0
        self._tool_calls = 0
        self._total_tokens = 0
        self._signature_counts: dict[str, int] = {}
        self._deadline_ms: int | None = None

    # wall-clock -----------------------------------------------------------
    def start(self) -> None:
        self._deadline_ms = self._now_ms() + self._policy.max_wall_clock_ms

    def is_deadline_reached(self) -> bool:
        if self._deadline_ms is None:
            raise RuntimeError("budget tracker not started")
        return self._now_ms() >= self._deadline_ms

    # iteration ------------------------------------------------------------
    def can_start_iteration(self) -> bool:
        return self._iterations < self._policy.max_iterations

    def record_iteration(self) -> None:
        self._iterations += 1

    # token (post-accounting) ---------------------------------------------
    def record_tokens(self, prompt_tokens: int, completion_tokens: int) -> None:
        prompt_tokens = _require_token_count(prompt_tokens, "prompt_tokens")
        completion_tokens = _require_token_count(completion_tokens, "completion_tokens")
        self._total_tokens += prompt_tokens + completion_tokens

    def is_token_budget_exceeded(self) -> bool:
        return self._total_tokens > self._policy.max_total_tokens

    # tool-call ------------------------------------------------------------
    def can_start_tool_call(self) -> bool:
        return self._tool_calls < self._policy.max_tool_calls

    # repeated-call --------------------------------------------------------
    def can_start_repeated_call(self, signature: str) -> bool:
        return self._signature_counts.get(signature, 0) < self._policy.max_repeated_calls

    def record_tool_call(self, signature: str) -> None:
        self._tool_calls += 1
        self._signature_counts[signature] = (
            self._signature_counts.get(signature, 0) + 1
        )
