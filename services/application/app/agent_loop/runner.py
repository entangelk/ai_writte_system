"""Minimal AgentLoopRunner composition for provider-response termination.

This slice wires the pure A1/A3 primitives into an executable provider loop for
one terminal provider response. Domain tool handlers remain a later Slice 1/3
surface; this runner fixes the load-bearing order that already has contracts:

1. check budget before starting each provider call;
2. record the provider call as one iteration, including retries;
3. record provider usage, then check post-accounting budget before completion;
4. parse the top-level ``self_report`` termination channel;
5. judge completion from artifact presence plus self-report.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from services.application.app.agent_loop.budget import (
    BudgetPolicy,
    BudgetTracker,
    InvalidProviderUsage,
)
from services.application.app.agent_loop.completion import SelfReport, judge_completion
from services.application.app.agent_loop.decision import LoopDecision
from services.application.app.agent_loop.parser import (
    InvalidSelfReport,
    parse_self_report_payload,
)
from services.application.app.agent_loop.resolution import (
    ErrorKind,
    next_step_budget_decision,
    resolve_retry,
)


@dataclass(frozen=True, slots=True)
class ProviderTurnResult:
    """Provider output consumed by the runner after one call."""

    content: str
    prompt_tokens: int
    completion_tokens: int


class ProviderCallError(RuntimeError):
    """Provider failure with retry metadata supplied by the gateway adapter."""

    def __init__(
        self,
        detail: str,
        *,
        retryable: bool,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.retryable = retryable


class ProviderCallable(Protocol):
    def __call__(self) -> ProviderTurnResult:
        """Return one provider result or raise ProviderCallError."""

        ...


@dataclass(frozen=True, slots=True)
class RunnerTraceEvent:
    """Small trace record for decision reconstruction in contract tests."""

    kind: str
    detail: str


@dataclass(frozen=True, slots=True)
class AgentLoopRunResult:
    decision: LoopDecision
    trace: tuple[RunnerTraceEvent, ...]
    content: str | None = None
    self_report: SelfReport | None = None
    preserved_error_literal: str | None = None


class AgentLoopRunner:
    """Run provider calls until a terminal LoopDecision is reached."""

    def __init__(
        self,
        *,
        provider: ProviderCallable,
        policy: BudgetPolicy,
        artifact_present: Callable[[str], bool],
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        self._provider = provider
        self._policy = policy
        self._artifact_present = artifact_present
        self._now_ms = now_ms

    def run(self) -> AgentLoopRunResult:
        tracker = (
            BudgetTracker(self._policy, now_ms=self._now_ms)
            if self._now_ms is not None
            else BudgetTracker(self._policy)
        )
        tracker.start()
        trace: list[RunnerTraceEvent] = []
        provider_retries_used = 0

        while True:
            budget_decision = next_step_budget_decision(
                tracker,
                needs_iteration=True,
            )
            if budget_decision is not None:
                trace.append(RunnerTraceEvent("budget", "before_provider"))
                return AgentLoopRunResult(decision=budget_decision, trace=tuple(trace))

            tracker.record_iteration()
            trace.append(RunnerTraceEvent("provider_call", "started"))

            try:
                provider_result = self._provider()
            except ProviderCallError as exc:
                trace.append(RunnerTraceEvent("provider_error", exc.detail))
                budget_permits_retry = (
                    next_step_budget_decision(tracker, needs_iteration=True) is None
                )
                retry_outcome = resolve_retry(
                    error_kind=ErrorKind.PROVIDER,
                    retryable=exc.retryable,
                    retries_remaining=(
                        self._policy.provider_retry_cap - provider_retries_used
                    ),
                    budget_permits_next=budget_permits_retry,
                )
                if retry_outcome.retry:
                    provider_retries_used += 1
                    trace.append(RunnerTraceEvent("provider_retry", exc.detail))
                    continue
                return AgentLoopRunResult(
                    decision=retry_outcome.decision or LoopDecision.PROVIDER_ERROR,
                    trace=tuple(trace),
                    preserved_error_literal=retry_outcome.preserved_literal,
                )

            try:
                tracker.record_tokens(
                    provider_result.prompt_tokens,
                    provider_result.completion_tokens,
                )
            except InvalidProviderUsage as exc:
                trace.append(RunnerTraceEvent("provider_usage", str(exc)))
                return AgentLoopRunResult(decision=exc.decision, trace=tuple(trace))

            budget_decision = next_step_budget_decision(
                tracker,
                needs_iteration=False,
            )
            if budget_decision is not None:
                trace.append(RunnerTraceEvent("budget", "after_provider_usage"))
                return AgentLoopRunResult(decision=budget_decision, trace=tuple(trace))

            try:
                self_report = parse_self_report_payload(provider_result.content)
            except InvalidSelfReport as exc:
                trace.append(RunnerTraceEvent("self_report", str(exc)))
                return AgentLoopRunResult(decision=exc.decision, trace=tuple(trace))

            trace.append(RunnerTraceEvent("self_report", self_report.value))
            decision = judge_completion(
                self._artifact_present(provider_result.content),
                self_report,
            )
            trace.append(RunnerTraceEvent("completion", decision.value))
            return AgentLoopRunResult(
                decision=decision,
                content=provider_result.content,
                self_report=self_report,
                trace=tuple(trace),
            )
