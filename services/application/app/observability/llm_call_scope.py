"""Provider-level capture of every LLM call (owner decision 2026-07-25, seam C).

Brief ``observability-instrumentation-seam-decisions.md``. Increment 4 first
instrumented the writing gate at the *endpoint* level, which worked only
because that endpoint makes exactly one LLM call. Every remaining call site
breaks that assumption — the analysis extractor calls the provider a second
time to repair non-JSON output, compare judges once per candidate, and the
retrieval planner runs inside the revise loop where no endpoint can see it. An
endpoint-level record would silently collapse those into one, and the repair
count is a metric the owner explicitly asked to observe.

So the seam is the provider itself: ``ObservedProvider`` wraps any
``LLMProvider`` and every ``generate()`` becomes exactly one record. A call
cannot be miscounted, because making the call *is* what produces the record.
Domain code is untouched — only the assembly points in ``main.py`` change.

Two things the provider cannot know on its own:

- **Which workflow the call belongs to.** ``llm_call_scope`` carries
  ``project_id``/``correlation_id`` in a ``contextvar``. Measured on this
  codebase before adopting it: 20 concurrent requests propagated 20/20 with
  zero cross-request leakage, and a call made outside any scope simply sees
  ``None`` (it is then left unrecorded rather than guessed at).
- **Whether the domain later rejected the response.** The provider only knows
  it answered; ``parse_error`` is a domain verdict. Records are therefore held
  in the scope and flushed when it closes, giving the caller a window to
  annotate the call it just made. The record is still one-per-call and
  append-only — annotation happens before the row is ever written.
"""

from __future__ import annotations

import contextvars
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterator

from services.application.app.context_search.models import ContextSearchErrorType
from services.application.app.observability.llm_call_audit import (
    LlmCallAuditService,
    LlmCallOutcome,
    LlmCallSite,
)
from services.llm_gateway.app.errors import ProviderError

if TYPE_CHECKING:  # the exception type only, kept out of the runtime import
    from services.application.app.context_search.service import ContextSearchFailed


@dataclass
class PendingLlmCall:
    """One provider round-trip, not yet written to the audit store."""

    call_site: LlmCallSite
    outcome: LlmCallOutcome
    model: str | None = None
    total_tokens: int = 0
    latency_ms: int = 0
    error_type: str | None = None
    # Domain verdicts the provider cannot see; filled in by ``annotate_last``.
    decision: str | None = None
    gate_quality_score: float | None = None


class LlmCallScope:
    """The LLM calls made while serving one workflow."""

    def __init__(self, *, project_id: str, correlation_id: str | None) -> None:
        self.project_id = project_id
        self.correlation_id = correlation_id
        self.calls: list[PendingLlmCall] = []

    def add(self, call: PendingLlmCall) -> None:
        self.calls.append(call)

    def annotate_last(self, **fields: object) -> None:
        """Attach a domain verdict to the call that was just made.

        A no-op when no call was made — the caller may be reporting on a
        failure that happened before the provider was ever reached, and in that
        case there is no call to annotate (nor should one be invented).
        """
        if not self.calls:
            return
        last = self.calls[-1]
        for name, value in fields.items():
            setattr(last, name, value)

    def reclassify_last_as_parse_error(self, error_type: str) -> None:
        """Mark the call just made as one the domain finally rejected.

        Named rather than a raw ``annotate_last`` because the safe condition is
        part of the contract, not the caller's to remember: ``parse_error``
        means *the provider answered and the domain rejected that answer*. A
        call that already failed at the provider must keep its own outcome and
        its taxonomy ``error_type`` — overwriting it would both lose the
        provider code and move the row out of the token-aggregation set
        (``provider_error`` rows carry no usable token count).

        This matters where the caller cannot tell the two apart from the
        exception alone: the context-search planner wraps *both* a provider
        failure and a terminal parse failure into the same
        ``ContextSearchFailed(LLM_ERROR)``.
        """
        if not self.calls:
            return
        if self.calls[-1].outcome is not LlmCallOutcome.SUCCESS:
            return
        last = self.calls[-1]
        last.outcome = LlmCallOutcome.PARSE_ERROR
        last.error_type = error_type


def reclassify_planner_parse_error(
    scope: LlmCallScope, exc: ContextSearchFailed
) -> None:
    """Record a context-search failure the planner's own answer caused.

    Lives here rather than at either caller because both the request endpoints
    (``main.py``) and the async generation worker hit this branch, and a second
    copy is how the two would quietly drift into different policies
    (verification 2026-07-26 H-2). Keeping every reclassification rule in one
    module is the same reasoning that put the isolation clause in ``_flush``.

    ``ContextSearchFailed`` is raised for four lineages and only ``llm_error``
    means "the planner is at fault" — a Mongo/embedding failure after a
    successful plan must leave that plan's record as ``success``. Within
    ``llm_error`` the two sub-cases (the provider never answered vs. it
    answered and the plan was rejected) are not distinguishable from the
    exception, so the outcome guard inside ``reclassify_last_as_parse_error``
    is what keeps a ``provider_error`` row from being relabelled.
    """
    if exc.error_type is ContextSearchErrorType.LLM_ERROR:
        scope.reclassify_last_as_parse_error(type(exc).__name__)


_SCOPE: contextvars.ContextVar[LlmCallScope | None] = contextvars.ContextVar(
    "llm_call_scope", default=None
)


def current_scope() -> LlmCallScope | None:
    return _SCOPE.get()


@contextmanager
def llm_call_scope(
    audit: LlmCallAuditService | None, *, project_id: str,
    correlation_id: str | None,
) -> Iterator[LlmCallScope]:
    """Collect the LLM calls made in this block, then write them.

    The flush is in ``finally`` on purpose: a request that fails partway still
    made its calls, and those are exactly the ones a failure-rate KPI needs.
    """
    scope = LlmCallScope(project_id=project_id, correlation_id=correlation_id)
    token = _SCOPE.set(scope)
    try:
        yield scope
    finally:
        _SCOPE.reset(token)
        _flush(audit, scope)


def _flush(audit: LlmCallAuditService | None, scope: LlmCallScope) -> None:
    # SoT §"LLM 파이프라인 관측(KPI)" 격리 조항: observing a request must never
    # be able to fail it. This runs inside a ``finally``, so letting an audit
    # write raise would also replace whatever exception the request was already
    # raising — the isolation is what keeps the original failure visible.
    if audit is None:
        return
    try:
        for call in scope.calls:
            audit.record(
                project_id=scope.project_id,
                call_site=call.call_site,
                correlation_id=scope.correlation_id,
                outcome=call.outcome,
                model=call.model,
                decision=call.decision,
                gate_quality_score=call.gate_quality_score,
                total_tokens=call.total_tokens,
                latency_ms=call.latency_ms,
                error_type=call.error_type,
            )
    except Exception:  # noqa: BLE001 — deliberate isolation boundary
        return


class ObservedProvider:
    """An ``LLMProvider`` that records each call it forwards."""

    def __init__(self, inner, *, call_site: LlmCallSite) -> None:
        self._inner = inner
        self._call_site = call_site

    async def generate(self, request):
        scope = _SCOPE.get()
        if scope is None:
            # Outside any scope (worker entrypoints, scripts, direct service
            # use). Forward untouched rather than invent a project_id — a
            # record attributed to a guessed workflow is worse than no record.
            return await self._inner.generate(request)
        started = time.perf_counter()
        try:
            result = await self._inner.generate(request)
        except ProviderError as exc:
            scope.add(PendingLlmCall(
                call_site=self._call_site,
                outcome=LlmCallOutcome.PROVIDER_ERROR,
                error_type=exc.code.value,
                latency_ms=_elapsed_ms(started),
            ))
            raise
        scope.add(PendingLlmCall(
            call_site=self._call_site,
            outcome=LlmCallOutcome.SUCCESS,
            model=result.model,
            total_tokens=result.usage.total_tokens,
            latency_ms=_elapsed_ms(started),
        ))
        return result


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
