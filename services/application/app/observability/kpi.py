"""KPI aggregation over the per-LLM-call audit (증분 5, brief D3=A/D4=A).

A pure read-model: it derives nothing new, it only counts what the audit trail
already recorded. Kept out of the endpoint so the aggregation rules the contract
fixes can be tested as rules rather than through HTTP.

Three of those rules are counter-intuitive enough that the payload carries its
own denominators (owner decision 2026-07-26, brief
``observability-kpi-readout-decisions.md`` D2=A):

- **Token totals exclude ``provider_error``** (SoT v1.7.42): that outcome's ``0``
  means "unknown", not "spent nothing", so averaging over it drags the number
  down. ``tokens_counted_from`` is the row count the total was actually built
  from.
- **Multi-call workflows are counted per ``correlation_id`` *within a site***
  (SoT v1.7.47): a single request now spans several sites, so counting rows per
  correlation without fixing the site would read another site's normal call as
  an extra round of this one. The count is reported as what it is — more than
  one call for one workflow — because a second row means a repair at a
  repair-shaped site but a designed extra round inside the writing loop.
- **The gate quality score does not cover every gate call** (SoT v1.7.47 known
  gap): calls made inside the revise loop carry no decision, so
  ``gate.scored_calls`` is the average's real denominator.

D8-5c adds the deployment-wide fold on top of the same rules. It is the same
code path, not a parallel one, because all three rules have to survive widening
the input — and one of them only survives if the aggregation keeps the project
axis inside the correlation key (see ``_rows_per_correlation``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from services.application.app.observability.llm_call_audit import (
    LlmCallOutcome,
    StoredLlmCall,
)
from services.application.app.writing.loop_audit import StoredWritingLoopRun
from services.application.app.writing.revise_gate import WritingLoopStatus


# Only these outcomes carry a token count that means what it says (SoT v1.7.42).
TOKEN_COUNTED_OUTCOMES: frozenset[str] = frozenset({
    LlmCallOutcome.SUCCESS.value,
    LlmCallOutcome.PARSE_ERROR.value,
})

# A loop run that stopped without resolving the finding it was started for.
# ``budget_exhausted`` ran out of rounds, ``no_change`` could not improve the
# candidate, ``failed`` broke — none of them reached an answer.
NON_CONVERGED_LOOP_STATUSES: frozenset[str] = frozenset({
    WritingLoopStatus.BUDGET_EXHAUSTED.value,
    WritingLoopStatus.NO_CHANGE.value,
    WritingLoopStatus.FAILED.value,
})

# ``not_eligible`` means the loop never ran (the finding was not auto-revisable),
# so it belongs in neither half — including it in the denominator would dilute
# the rate with runs that were never attempts. ``pass`` and ``terminal_decision``
# are both convergence: the latter is the loop correctly handing a judgement
# call to the user, which is a designed ending, not a failure to converge.
NOT_A_LOOP_ATTEMPT: frozenset[str] = frozenset({
    WritingLoopStatus.NOT_ELIGIBLE.value,
})


@dataclass(frozen=True, slots=True)
class SiteKpi:
    call_site: str
    calls: int
    success: int
    provider_error: int
    parse_error: int
    total_tokens: int
    tokens_counted_from: int
    avg_latency_ms: int
    # Distinct workflows this site served, and how many of them took more
    # than one call — with the site already fixed, as the contract requires.
    #
    # Deliberately *not* named "repairs": for a repair-shaped site (extractor,
    # compare judge, planner) a second row does mean a retry, but the writing
    # loop calls its gate/reviser/reporter several times **by design**
    # (WRITING_LOOP_MAX_GATE_EVALUATIONS defaults to 3). One name cannot mean
    # both, so the field states the fact it measured and the reader applies the
    # site's shape.
    correlations: int
    multi_call_correlations: int


@dataclass(frozen=True, slots=True)
class TotalsKpi:
    calls: int
    success: int
    provider_error: int
    parse_error: int
    total_tokens: int
    tokens_counted_from: int


@dataclass(frozen=True, slots=True)
class GateKpi:
    scored_calls: int
    # None rather than 0.0 when nothing was scored: "no gate call carried a
    # score" and "the average score is zero" are different facts.
    avg_quality_score: float | None


@dataclass(frozen=True, slots=True)
class LoopKpi:
    runs_considered: int
    non_convergence_rate: float | None


@dataclass(frozen=True, slots=True)
class ObservabilityKpi:
    project_id: str
    totals: TotalsKpi
    sites: tuple[SiteKpi, ...]
    gate: GateKpi
    loop: LoopKpi


@dataclass(frozen=True, slots=True)
class GlobalObservabilityKpi:
    """The same fold, over every project's records (D8-5c).

    Deliberately not a per-project breakdown: this is the deployment-wide
    read-out, and listing which projects exist is the admin *projects* slice
    (5-b), still behind the owner decisions F1=C opened. ``projects_considered``
    keeps the project axis present as a denominator — "this number came from N
    projects" — without naming any of them, which is the same line the admin
    boundary already draws (an admin sees accounts and aggregates, not project
    content).
    """

    projects_considered: int
    totals: TotalsKpi
    sites: tuple[SiteKpi, ...]
    gate: GateKpi
    loop: LoopKpi


def aggregate_kpi(
    *,
    project_id: str,
    calls: Sequence[StoredLlmCall],
    loop_runs: Sequence[StoredWritingLoopRun],
) -> ObservabilityKpi:
    """Fold the audit trails into the KPI read-model."""
    return ObservabilityKpi(project_id=project_id, **_fold(calls, loop_runs))


def aggregate_global_kpi(
    *,
    calls: Sequence[StoredLlmCall],
    loop_runs: Sequence[StoredWritingLoopRun],
) -> GlobalObservabilityKpi:
    """The deployment-wide fold — same rules, wider input (D8-5c).

    Shares ``_fold`` with the per-project aggregation rather than restating it,
    so the three counter-intuitive rules the contract fixes (denominators
    alongside every rate, ``None`` over zero samples, ``multi_call_correlations``
    is not a repair count) hold globally by construction instead of by a second
    implementation that has to be kept in step.
    """
    return GlobalObservabilityKpi(
        # Records are the only source: a project that never called an LLM is not
        # part of this measurement, and counting it would dilute every per-call
        # number with projects that contributed no calls.
        projects_considered=len(
            {call.project_id for call in calls}
            | {run.project_id for run in loop_runs}
        ),
        **_fold(calls, loop_runs),
    )


def _fold(
    calls: Sequence[StoredLlmCall], loop_runs: Sequence[StoredWritingLoopRun]
) -> dict[str, object]:
    return {
        "totals": _totals(calls),
        "sites": tuple(
            _site_kpi(site, [c for c in calls if c.call_site == site])
            # Sorted by name, and only sites that actually made a call: a
            # dashboard iterating rows should not have to filter out seven rows
            # of zeros, and the order must not depend on insertion.
            for site in sorted({call.call_site for call in calls})
        ),
        "gate": _gate(calls),
        "loop": _loop(loop_runs),
    }


def _totals(calls: Sequence[StoredLlmCall]) -> TotalsKpi:
    counted = [c for c in calls if c.outcome in TOKEN_COUNTED_OUTCOMES]
    return TotalsKpi(
        calls=len(calls),
        success=_count(calls, LlmCallOutcome.SUCCESS),
        provider_error=_count(calls, LlmCallOutcome.PROVIDER_ERROR),
        parse_error=_count(calls, LlmCallOutcome.PARSE_ERROR),
        total_tokens=sum(c.total_tokens for c in counted),
        tokens_counted_from=len(counted),
    )


def _site_kpi(call_site: str, calls: Sequence[StoredLlmCall]) -> SiteKpi:
    counted = [c for c in calls if c.outcome in TOKEN_COUNTED_OUTCOMES]
    per_correlation = _rows_per_correlation(calls)
    return SiteKpi(
        call_site=call_site,
        calls=len(calls),
        success=_count(calls, LlmCallOutcome.SUCCESS),
        provider_error=_count(calls, LlmCallOutcome.PROVIDER_ERROR),
        parse_error=_count(calls, LlmCallOutcome.PARSE_ERROR),
        total_tokens=sum(c.total_tokens for c in counted),
        tokens_counted_from=len(counted),
        # Latency is averaged over *every* call, failures included: a provider
        # timeout really did cost that wall-clock time, and hiding it would make
        # a degrading gateway look fast.
        avg_latency_ms=(
            round(sum(c.latency_ms for c in calls) / len(calls)) if calls else 0
        ),
        correlations=len(per_correlation),
        multi_call_correlations=sum(
            1 for rows in per_correlation.values() if rows > 1
        ),
    )


def _rows_per_correlation(
    calls: Iterable[StoredLlmCall],
) -> dict[tuple[str, str], int]:
    # Rows with no correlation_id are skipped rather than bucketed together:
    # they cannot be attributed to a workflow, and lumping them into one bucket
    # would invent a workflow that made many calls.
    #
    # Keyed by ``project_id`` as well, which is invisible per project (every row
    # already shares one) and load-bearing globally: correlation ids are the
    # caller's own ``request_id``/``idempotency_key``, so two projects can and do
    # use the same string. Without the project in the key, one call in each of
    # two projects would fold into a single two-row workflow and be reported as a
    # repair that never happened.
    #
    # The asymmetry — ``correlation_id`` is skipped when absent, ``project_id``
    # is not checked — mirrors the record: ``correlation_id`` is ``str | None``
    # and ``project_id`` is ``str`` (``llm_call_audit.py``; the Mongo mapper
    # reads ``doc["project_id"]`` but ``doc.get("correlation_id")``). A guard
    # here would be unreachable today; the moment that field becomes nullable is
    # the moment to add one, because a ``None`` bucket would distort the
    # denominator rather than merely skip a row.
    counts: dict[tuple[str, str], int] = {}
    for call in calls:
        if call.correlation_id is None:
            continue
        key = (call.project_id, call.correlation_id)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _gate(calls: Sequence[StoredLlmCall]) -> GateKpi:
    scored = [c.gate_quality_score for c in calls
              if c.gate_quality_score is not None]
    return GateKpi(
        scored_calls=len(scored),
        avg_quality_score=(sum(scored) / len(scored)) if scored else None,
    )


def _loop(runs: Sequence[StoredWritingLoopRun]) -> LoopKpi:
    considered = [r for r in runs if r.loop_status not in NOT_A_LOOP_ATTEMPT]
    non_converged = sum(
        1 for r in considered if r.loop_status in NON_CONVERGED_LOOP_STATUSES
    )
    return LoopKpi(
        runs_considered=len(considered),
        non_convergence_rate=(
            non_converged / len(considered) if considered else None
        ),
    )


def _count(calls: Sequence[StoredLlmCall], outcome: LlmCallOutcome) -> int:
    return sum(1 for call in calls if call.outcome == outcome.value)
