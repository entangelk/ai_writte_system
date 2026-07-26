"""Unified per-LLM-call observability audit trail.

Observability KPI phase (brief ``observability-kpi-decisions.md``, D1=B).
Every LLM call site in the pipeline — query planner, writing gate, compare
judge, analysis extractor, writing generation — leaves **one append-only
record** with a common shape: which site, which workflow it belongs to, the
model, the outcome, the decision/verdict it produced, token usage, latency,
and any error. That single shape is the read-model the KPI aggregation reads
(D4=A); it fills the gap that ``StoredWritingLoopRun`` (a writing-loop *rollup*)
leaves for the planner/compare/extractor sites, which were previously
uninstrumented for persistence.

The ``gate_quality_score`` derived from the writing gate's own decision is the
"how well did the previous LLM write" signal the owner asked for (D2=C: derive
from the existing gate output first; an LLM-emitted score is a later slice).
The score keys off the gate *decision* — a deliberately **coarse,
decision-category approximation**, not a full quality metric. ``writing/gate.py``
sets ``decision == max(recommended_decision of decision-driving findings)``, so
the decision reflects only the single highest-priority finding and discards how
many findings there were or how they combined: a candidate with both a REVISE
and a NEEDS_USER_REVIEW finding scores as NEEDS_USER_REVIEW (0.6) alone. That
lost sub-signal is not redundant with the decision — folding in finding
severity/count would *add* information, not double-count it. It is left out here
on purpose to keep D2-C's first cut simple; recovering it (or an LLM-emitted
score) is the named D2-B follow-up.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Callable, Protocol
from uuid import uuid4

from services.application.app.writing.models import (
    WritingGateDecision,
    WritingGateResult,
)


class LlmCallSite(StrEnum):
    """Which pipeline stage made the LLM call.

    Kept general so a future site (e.g. Phase 7 conversational authoring) is a
    new member, not a schema change (brief Follow-up considerations).
    """

    QUERY_PLANNER = "query_planner"
    WRITING_GATE = "writing_gate"
    COMPARE_JUDGE = "compare_judge"
    ANALYSIS_EXTRACTOR = "analysis_extractor"
    WRITING_GENERATION = "writing_generation"
    # 증분 C (owner decision 2026-07-26, brief
    # ``observability-site-mapping-decisions.md`` D1=분리 / D2=신규 리터럴).
    # Measured at that point: five literals but eight real LLM adapters. The
    # writing loop's retrieval planner, reviser and self-report each make their
    # own provider call with their own prompt, token cap and failure mode, so
    # folding them into a neighbouring site would permanently blend distinct
    # signals — old records cannot be split apart afterwards, while adding a
    # member is explicitly not a schema change (see the section above).
    WRITING_RETRIEVAL_PLANNER = "writing_retrieval_planner"
    WRITING_REVISION = "writing_revision"
    WRITING_REPORT = "writing_report"


class LlmCallOutcome(StrEnum):
    """Terminal outcome of the call, from the caller's point of view."""

    SUCCESS = "success"
    PROVIDER_ERROR = "provider_error"
    PARSE_ERROR = "parse_error"
    BUDGET_EXCEEDED = "budget_exceeded"


# Derived quality score for a writing-gate decision (D2=C). Single source of
# truth so it moves in lockstep with the gate severity/decision scheme if that
# ever changes (brief Follow-up considerations).
#
# - PASS: the previous LLM's writing cleared the gate → 1.0.
# - NEEDS_USER_REVIEW: borderline, a human must judge → 0.6.
# - RETRIEVE_MORE: inconclusive — the gate could not verify for lack of context,
#   which is not a verdict on the writing itself → 0.5 (neutral midpoint).
# - REVISE: concrete, fixable defects were found → 0.3.
# - BLOCK: a must-not-use violation → 0.0.
_GATE_DECISION_QUALITY: dict[WritingGateDecision, float] = {
    WritingGateDecision.PASS: 1.0,
    WritingGateDecision.NEEDS_USER_REVIEW: 0.6,
    WritingGateDecision.RETRIEVE_MORE: 0.5,
    WritingGateDecision.REVISE: 0.3,
    WritingGateDecision.BLOCK: 0.0,
}


def gate_quality_score(gate: WritingGateResult) -> float:
    """Map a writing-gate decision to a [0.0, 1.0] writing-quality score.

    Every ``WritingGateDecision`` member is mapped, so this never raises for a
    valid gate result; a future decision literal added without a mapping entry
    fails the parametrized boundary test rather than silently defaulting.
    """
    return _GATE_DECISION_QUALITY[gate.decision]


@dataclass(frozen=True, slots=True)
class StoredLlmCall:
    id: str
    project_id: str
    call_site: str
    # Ties every call made while serving one workflow together (a writing
    # request_id, an analysis job_id, a context-search request_id). Nullable
    # only defensively; every real call site has one.
    correlation_id: str | None
    model: str | None
    outcome: str
    # The verdict/decision literal the call produced, when it has one (gate
    # decision, compare judge verdict). None for calls that only generate text.
    decision: str | None
    # Derived writing-quality score, present only on writing-gate calls.
    gate_quality_score: float | None
    total_tokens: int
    latency_ms: int
    error_type: str | None
    created_at: datetime


class LlmCallAuditRepository(Protocol):
    def add(self, call: StoredLlmCall) -> None: ...
    def list_for_project(
        self, project_id: str
    ) -> tuple[StoredLlmCall, ...]: ...


class InMemoryLlmCallAuditRepository:
    def __init__(self) -> None:
        self.entries: dict[str, StoredLlmCall] = {}

    def add(self, call: StoredLlmCall) -> None:
        self.entries[call.id] = call

    def list_for_project(
        self, project_id: str
    ) -> tuple[StoredLlmCall, ...]:
        return tuple(sorted(
            (call for call in self.entries.values()
             if call.project_id == project_id),
            key=lambda call: (call.created_at, call.id),
            reverse=True,
        ))


class LlmCallAuditService:
    def __init__(
        self, repository: LlmCallAuditRepository, *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repo = repository
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: "llmc:" + uuid4().hex)

    def record(
        self, *, project_id: str, call_site: LlmCallSite,
        correlation_id: str | None, outcome: LlmCallOutcome,
        model: str | None = None, decision: str | None = None,
        gate_quality_score: float | None = None,
        total_tokens: int = 0, latency_ms: int = 0,
        error_type: str | None = None,
    ) -> StoredLlmCall:
        call = StoredLlmCall(
            id=self._id_factory(),
            project_id=project_id,
            call_site=call_site.value,
            correlation_id=correlation_id,
            model=model,
            outcome=outcome.value,
            decision=decision,
            gate_quality_score=gate_quality_score,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            error_type=error_type,
            created_at=self._clock(),
        )
        self._repo.add(call)
        return call

    def list_calls(self, project_id: str) -> tuple[StoredLlmCall, ...]:
        return self._repo.list_for_project(project_id)
