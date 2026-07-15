"""Phase 5.10 Option A per-stage cost measurement (M-i).

Measures each Writing loop stage — revise, report, gate, retrieve_plan and
context_search — in isolation against the real gateway, recording provider
``TokenUsage`` and wall-clock latency. The synthesis in
``benchmark_writing_loop.compose_worst_case_ceiling`` then composes the loop's
worst-case aggregate ceiling from these per-stage costs.

Why measure per-stage instead of the whole loop: the Writing Gate is an
independent evaluator (D3=A) and cannot be prose-steered into ``retrieve_more``
(confirmed live 0/12), so the real model never walks the loop's max structural
path. But the aggregate budget is a SUM of per-stage provider usage bounded by
the structural caps, so the worst-case ceiling can be composed analytically from
isolated per-stage costs — which this module supplies.

Contract mirrored from ``revise_gate.metered``:
- revise / report / gate / retrieve_plan contribute provider tokens (measured
  via each collaborator's ``*_metered`` variant, which rides ``TokenUsage`` on
  the return, repair included).
- ``context_search`` runs OUTSIDE ``metered()`` in the loop (``revise_gate.py``),
  so it adds wall-clock only, never aggregate tokens. Its ``total_tokens`` here
  is always 0 by construction, matching ``_TOKEN_STAGES`` in the synthesis.

The ``retrieve_plan`` stage is fed a SYNTHETIC ``retrieve_more`` Gate result
(constructed here, not model-produced) so the planner runs without needing the
Gate to actually emit ``retrieve_more`` — the exact Gate-independence problem
Option A exists to sidestep.

Read-only: writes nothing — no Mongo, no audit, no file. The CLI
(``scripts/measure_writing_stages.py``) wires the production services and feeds
them in. Output is numeric only (tokens/ms/model) — no candidate/context prose —
so unlike ``gate_live_diag`` its report is safe to persist.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Protocol

from services.application.app.context_search.models import (
    ContextPackage,
    ContextSearchRequest,
    CurrentPosition,
)
from services.application.app.writing.metering import MeteredCallError
from services.application.app.writing.models import (
    WritingCandidate,
    WritingGateDecision,
    WritingGateFinding,
    WritingGateFindingType,
    WritingGateResult,
    WritingGateSeverity,
    WritingRequest,
)
from services.application.app.writing.retrieval import WritingRetrievalPlan
from services.llm_gateway.app.provider import TokenUsage


REVISE_STAGE = "revise"
REPORT_STAGE = "report"
GATE_STAGE = "gate"
RETRIEVE_PLAN_STAGE = "retrieve_plan"
CONTEXT_SEARCH_STAGE = "context_search"

# Ordered as the loop executes them. context_search is measured first because it
# builds the ContextPackage the token-contributing stages consume.
_MEASURED_STAGES = (
    CONTEXT_SEARCH_STAGE, REVISE_STAGE, REPORT_STAGE, GATE_STAGE,
    RETRIEVE_PLAN_STAGE,
)
# Stages whose provider usage rides the loop's aggregate token budget.
_TOKEN_STAGES = (REVISE_STAGE, REPORT_STAGE, GATE_STAGE, RETRIEVE_PLAN_STAGE)


class _ContextSearch(Protocol):
    async def build_context_package(
        self, request: ContextSearchRequest,
    ) -> ContextPackage: ...


class _Reviser(Protocol):
    async def revise_metered(
        self, *, candidate: WritingCandidate, finding: WritingGateFinding,
        instruction: str, package: ContextPackage,
    ) -> tuple[WritingCandidate, TokenUsage]: ...


class _Reporter(Protocol):
    async def enrich_metered(
        self, candidate: WritingCandidate, package: ContextPackage,
    ) -> tuple[WritingCandidate, TokenUsage]: ...


class _Gate(Protocol):
    async def evaluate_metered(
        self, *, request: WritingRequest, candidate: WritingCandidate,
        package: ContextPackage,
    ) -> tuple[WritingGateResult, TokenUsage]: ...


class _RetrievalPlanner(Protocol):
    async def plan_metered(
        self, *, request: WritingRequest, candidate: WritingCandidate,
        gate: WritingGateResult, current_position: CurrentPosition | None,
    ) -> tuple[WritingRetrievalPlan, TokenUsage]: ...


@dataclass(frozen=True, slots=True)
class StageSample:
    """One isolated measurement of a single stage.

    ``total_tokens`` is 0 for ``context_search`` by construction (it is excluded
    from the aggregate token budget); wall-clock is measured for every stage.
    """

    stage: str
    total_tokens: int
    wall_clock_ms: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str | None = None


@dataclass(frozen=True, slots=True)
class PerStageMeasurement:
    """Aggregated per-stage costs across ``repeats`` measurement passes.

    ``stage_tokens`` / ``stage_ms`` take the conservative MAX across passes (the
    synthesis wants "관측 최댓값"), keyed by stage name. ``stage_tokens`` omits
    ``context_search`` (token-excluded). ``incomplete_stages`` names any stage
    with no successful sample — the operator must not compose a ceiling from an
    incomplete set (it would silently under-bound).
    """

    samples: tuple[tuple[StageSample, ...], ...]
    stage_tokens: dict[str, int]
    stage_ms: dict[str, int]
    incomplete_stages: tuple[str, ...] = ()
    error: str | None = None
    error_stage: str | None = None


class _StageMeasurementError(RuntimeError):
    def __init__(self, stage: str, cause: Exception) -> None:
        super().__init__(f"{stage}: {cause}")
        self.stage = stage
        self.cause = cause


def _synthetic_retrieve_more_gate(
    request: WritingRequest, candidate: WritingCandidate,
) -> WritingGateResult:
    """A retrieve_more Gate result the planner accepts (constructed, not model-
    produced). The planner only requires a retrieve_more decision plus at least
    one finding whose ``recommended_decision`` is retrieve_more; it does not
    check evidence containment, so a generic finding suffices.
    """
    return WritingGateResult(
        request_id=request.request_id,
        project_id=request.project_id,
        decision=WritingGateDecision.RETRIEVE_MORE,
        findings=(
            WritingGateFinding(
                finding_type=WritingGateFindingType.CONTINUITY,
                severity=WritingGateSeverity.WARNING,
                message="추가 맥락이 필요합니다 (합성 측정용).",
                evidence=candidate.text[:32],
                recommended_decision=WritingGateDecision.RETRIEVE_MORE,
            ),
        ),
        checked_constraints=(),
        evaluated_by_model="synthetic-measurement",
    )


async def _measure_once(
    *,
    context_search: _ContextSearch,
    search_request: ContextSearchRequest,
    reviser: _Reviser,
    reporter: _Reporter,
    gate: _Gate,
    retrieval_planner: _RetrievalPlanner,
    request: WritingRequest,
    candidate: WritingCandidate,
    finding: WritingGateFinding,
    current_position: CurrentPosition | None,
    clock: Callable[[], float],
    samples: list[StageSample],
) -> None:
    """Run one context→revise→report→gate→retrieve_plan pass, timing each stage.

    Stages thread realistically (each consumes the previous output), but each is
    measured in isolation. retrieve_plan uses a synthetic retrieve_more Gate so
    it runs regardless of what the real Gate decided. Appends a ``StageSample``
    per completed stage to ``samples`` (so partial progress is retained by the
    caller) and raises ``_StageMeasurementError`` on the first stage that faults.
    """

    async def timed_metered(stage, coro):
        start = clock()
        try:
            value, usage = await coro
        except MeteredCallError as exc:
            raise _StageMeasurementError(stage, exc.cause) from exc
        except Exception as exc:  # noqa: BLE001 — surface provider fault verbatim
            raise _StageMeasurementError(stage, exc) from exc
        ms = int((clock() - start) * 1000)
        samples.append(StageSample(
            stage=stage, total_tokens=usage.total_tokens, wall_clock_ms=ms,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            model=getattr(value, "generated_by_model", None) or None,
        ))
        return value

    # context_search: measured for wall-clock only; excluded from token budget.
    start = clock()
    try:
        package = await context_search.build_context_package(search_request)
    except Exception as exc:  # noqa: BLE001
        raise _StageMeasurementError(CONTEXT_SEARCH_STAGE, exc) from exc
    samples.append(StageSample(
        stage=CONTEXT_SEARCH_STAGE, total_tokens=0,
        wall_clock_ms=int((clock() - start) * 1000),
    ))

    revised = await timed_metered(REVISE_STAGE, reviser.revise_metered(
        candidate=candidate, finding=finding,
        instruction=request.instruction, package=package,
    ))
    reported = await timed_metered(
        REPORT_STAGE, reporter.enrich_metered(revised, package))
    await timed_metered(GATE_STAGE, gate.evaluate_metered(
        request=request, candidate=reported, package=package))
    synthetic_gate = _synthetic_retrieve_more_gate(request, reported)
    await timed_metered(RETRIEVE_PLAN_STAGE, retrieval_planner.plan_metered(
        request=request, candidate=reported, gate=synthetic_gate,
        current_position=current_position,
    ))


async def run_per_stage_measurement(
    *,
    context_search: _ContextSearch,
    search_request: ContextSearchRequest,
    reviser: _Reviser,
    reporter: _Reporter,
    gate: _Gate,
    retrieval_planner: _RetrievalPlanner,
    request: WritingRequest,
    candidate: WritingCandidate,
    finding: WritingGateFinding,
    current_position: CurrentPosition | None = None,
    repeats: int = 1,
    clock: Callable[[], float] = perf_counter,
) -> PerStageMeasurement:
    """Measure per-stage costs over ``repeats`` passes, taking the conservative
    MAX per stage. On a stage fault the completed passes are retained and the
    fault is surfaced (``error``/``error_stage``); the faulting stage lands in
    ``incomplete_stages`` so the operator does not compose from a gap.
    """
    if repeats < 1:
        raise ValueError("repeats must be at least 1")

    passes: list[tuple[StageSample, ...]] = []
    error: str | None = None
    error_stage: str | None = None
    for _ in range(repeats):
        samples: list[StageSample] = []
        try:
            await _measure_once(
                context_search=context_search, search_request=search_request,
                reviser=reviser, reporter=reporter, gate=gate,
                retrieval_planner=retrieval_planner, request=request,
                candidate=candidate, finding=finding,
                current_position=current_position, clock=clock, samples=samples,
            )
        except _StageMeasurementError as exc:
            # Retain the stages that completed before the fault so they are not
            # spuriously reported incomplete.
            error, error_stage = str(exc.cause), exc.stage
            passes.append(tuple(samples))
            break
        passes.append(tuple(samples))

    stage_ms: dict[str, int] = {}
    stage_tokens: dict[str, int] = {}
    for pass_samples in passes:
        for sample in pass_samples:
            stage_ms[sample.stage] = max(
                stage_ms.get(sample.stage, 0), sample.wall_clock_ms)
            if sample.stage in _TOKEN_STAGES:
                stage_tokens[sample.stage] = max(
                    stage_tokens.get(sample.stage, 0), sample.total_tokens)

    incomplete = tuple(
        stage for stage in _MEASURED_STAGES if stage not in stage_ms)
    return PerStageMeasurement(
        samples=tuple(passes), stage_tokens=stage_tokens, stage_ms=stage_ms,
        incomplete_stages=incomplete, error=error, error_stage=error_stage,
    )


def measurement_to_dict(measurement: PerStageMeasurement) -> dict[str, Any]:
    """Render the aggregated measurement as JSON-safe data (numeric only)."""
    return {
        "stage_tokens": dict(measurement.stage_tokens),
        "stage_ms": dict(measurement.stage_ms),
        "incomplete_stages": list(measurement.incomplete_stages),
        "error": measurement.error,
        "error_stage": measurement.error_stage,
        "samples": [
            [
                {
                    "stage": s.stage,
                    "total_tokens": s.total_tokens,
                    "wall_clock_ms": s.wall_clock_ms,
                    "prompt_tokens": s.prompt_tokens,
                    "completion_tokens": s.completion_tokens,
                    "model": s.model,
                }
                for s in pass_samples
            ]
            for pass_samples in measurement.samples
        ],
    }
