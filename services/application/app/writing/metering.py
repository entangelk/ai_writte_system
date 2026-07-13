"""Token-usage plumbing for the Writing loop aggregate budget.

Phase 5.10 ("B2 increment", brief ``05-writing-loop-budget-decisions.md``,
M3=A internal channel): each Writing domain service exposes a ``*_metered``
variant that returns ``(result, TokenUsage)`` so the bounded loop can sum the
provider token usage of every stage and enforce an aggregate token budget. The
public HTTP envelopes (``WritingCandidate``/``WritingGateResult``/ephemeral
``stages``) are unchanged — usage rides only on the internal return value.
"""

from __future__ import annotations

from services.llm_gateway.app.provider import TokenUsage

EMPTY_USAGE = TokenUsage()


class MeteredCallError(RuntimeError):
    """Carry usage from a provider response that domain parsing rejected."""

    def __init__(self, cause: Exception, usage: TokenUsage) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.usage = usage


def add_usage(a: TokenUsage, b: TokenUsage) -> TokenUsage:
    """Sum two usages (e.g. an initial call plus its JSON-repair retry)."""

    return TokenUsage(
        prompt_tokens=a.prompt_tokens + b.prompt_tokens,
        completion_tokens=a.completion_tokens + b.completion_tokens,
    )
