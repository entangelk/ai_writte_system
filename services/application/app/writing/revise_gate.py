"""Bounded partial-revise/report/Gate and targeted-retrieval composition."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from time import monotonic
from typing import Callable, Protocol

from services.application.app.writing.metering import (
    EMPTY_USAGE,
    MeteredCallError,
    add_usage,
)
from services.llm_gateway.app.provider import TokenUsage
from services.application.app.context_search.models import (
    ContextBudget,
    ContextPackage,
    ContextSearchPurpose,
    ContextSearchRequest,
    CurrentPosition,
)
from services.application.app.writing.audit_hash import (
    finding_fingerprint,
    hash_text,
    package_pointer_ids,
)
from services.application.app.writing.models import (
    WritingCandidate,
    WritingGateDecision,
    WritingGateFinding,
    WritingGateFindingType,
    WritingGateResult,
    WritingGateSeverity,
    WritingRequest,
)
from services.application.app.writing.retrieval import (
    WritingRetrievalPlan,
    merge_context_packages,
)
from services.application.app.writing.revise import UnchangedWritingRevision


class CandidateReviser(Protocol):
    async def revise(
        self, *, candidate: WritingCandidate, finding: WritingGateFinding,
        instruction: str, package: ContextPackage,
    ) -> WritingCandidate: ...


class CandidateGate(Protocol):
    async def evaluate(
        self, *, request: WritingRequest, candidate: WritingCandidate,
        package: ContextPackage,
    ) -> WritingGateResult: ...


class CandidateReporter(Protocol):
    async def enrich(
        self, candidate: WritingCandidate, package: ContextPackage,
    ) -> WritingCandidate: ...


class FollowupRetrievalPlanner(Protocol):
    async def plan(
        self, *, request: WritingRequest, candidate: WritingCandidate,
        gate: WritingGateResult, current_position: CurrentPosition | None = None,
    ) -> WritingRetrievalPlan: ...


class ContextPackageSearch(Protocol):
    async def build_context_package(
        self, request: ContextSearchRequest,
    ) -> ContextPackage: ...


class WritingLoopStatus(StrEnum):
    PASS = "pass"
    TERMINAL_DECISION = "terminal_decision"
    NOT_ELIGIBLE = "not_eligible"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NO_CHANGE = "no_change"
    FAILED = "failed"


class WritingLoopStageName(StrEnum):
    REVISE = "revise"
    REPORT = "report"
    GATE = "gate"
    RETRIEVE_PLAN = "retrieve_plan"
    CONTEXT_SEARCH = "context_search"
    MERGE = "merge"


class WritingLoopStageStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    NO_CHANGE = "no_change"


@dataclass(frozen=True, slots=True)
class WritingLoopPolicy:
    """Configurable structural caps; counts include the initial requested work.

    ``max_total_tokens``/``max_wall_clock_ms`` are the Phase 5.10 ("B2") aggregate
    budget dimensions. They default to ``None`` (unbounded): the structural round
    caps already bound the loop, and production numbers wait on live loop-level
    calibration (B2b). When set they enforce, mirroring ``flat-loop-gate.md``:
    token is post-accounting (a cumulative ``> limit`` result is not adopted),
    wall-clock is a monotonic deadline checked before the next stage.
    """

    max_revision_rounds: int = 2
    max_retrieval_rounds: int = 1
    max_gate_evaluations: int = 3
    max_total_tokens: int | None = None
    max_wall_clock_ms: int | None = None

    def __post_init__(self) -> None:
        if self.max_revision_rounds < 1:
            raise ValueError("max_revision_rounds must be at least 1")
        if self.max_retrieval_rounds < 0:
            raise ValueError("max_retrieval_rounds must not be negative")
        if self.max_gate_evaluations < 1:
            raise ValueError("max_gate_evaluations must be at least 1")
        if self.max_total_tokens is not None and self.max_total_tokens < 1:
            raise ValueError("max_total_tokens must be at least 1 when set")
        if self.max_wall_clock_ms is not None and self.max_wall_clock_ms < 1:
            raise ValueError("max_wall_clock_ms must be at least 1 when set")


@dataclass(frozen=True, slots=True)
class WritingLoopStage:
    stage: WritingLoopStageName
    ordinal: int
    status: WritingLoopStageStatus
    # Per-stage audit detail (Phase 5.9 L9 B, P1=B). The ephemeral HTTP
    # response exposes only stage/ordinal/status; the persisted loop audit
    # reads these bodyless hashes/fingerprints/pointers.
    candidate_hash: str | None = None
    finding_fingerprint: str | None = None
    pointer_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WritingLoopSummary:
    status: WritingLoopStatus
    revision_rounds: int
    retrieval_rounds: int
    gate_evaluations: int
    # Phase 5.10 ("B2") aggregate metering. Always computed; the ephemeral HTTP
    # `loop` payload does not expose these (M5=A) — only the persisted audit does.
    total_tokens: int = 0
    wall_clock_ms: int = 0


@dataclass(frozen=True, slots=True)
class WritingReviseGateResult:
    candidate: WritingCandidate
    gate: WritingGateResult | None
    loop: WritingLoopSummary
    stages: tuple[WritingLoopStage, ...]


class _WritingLoopFailure(RuntimeError):
    def __init__(
        self,
        candidate: WritingCandidate,
        cause: Exception,
        *,
        gate: WritingGateResult | None,
        loop: WritingLoopSummary,
        stages: tuple[WritingLoopStage, ...],
    ) -> None:
        super().__init__(str(cause))
        self.candidate = candidate
        self.gate = gate
        self.cause = cause
        self.loop = loop
        self.stages = stages


class WritingReviseGateFailure(_WritingLoopFailure):
    pass


class WritingReviseReportFailure(_WritingLoopFailure):
    pass


class WritingLoopRevisionFailure(_WritingLoopFailure):
    pass


class WritingRetrievalConfigurationError(RuntimeError):
    pass


class WritingRetrievalFailure(_WritingLoopFailure):
    pass


class _PostAccountingBudgetExceeded(RuntimeError):
    pass


class WritingReviseGateService:
    def __init__(
        self,
        *,
        reviser: CandidateReviser,
        reporter: CandidateReporter,
        gate: CandidateGate,
        retrieval_planner: FollowupRetrievalPlanner | None = None,
        context_search: ContextPackageSearch | None = None,
        policy: WritingLoopPolicy | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._reviser = reviser
        self._reporter = reporter
        self._gate = gate
        self._retrieval_planner = retrieval_planner
        self._context_search = context_search
        self._policy = policy or WritingLoopPolicy()
        # Monotonic seconds for the wall-clock budget; injectable for tests.
        self._clock = clock or monotonic

    async def run(
        self,
        *,
        request: WritingRequest,
        candidate: WritingCandidate,
        finding: WritingGateFinding,
        package: ContextPackage,
        current_position: CurrentPosition | None = None,
        context_budget: ContextBudget | None = None,
    ) -> WritingReviseGateResult:
        stages: list[WritingLoopStage] = []
        revision_rounds = 0
        retrieval_rounds = 0
        gate_evaluations = 0
        current_candidate = candidate
        current_package = package
        last_gate: WritingGateResult | None = None
        started_at = self._clock()
        accumulated: TokenUsage = EMPTY_USAGE

        async def metered(collaborator: object, method: str, /, **kwargs):
            # M3=A internal channel: prefer the ``*_metered`` variant so provider
            # TokenUsage rides on the return; fall back to the bare method (zero
            # usage) for collaborators that don't surface usage. With the default
            # unbounded policy, zero usage keeps behaviour byte-identical.
            nonlocal accumulated
            variant = getattr(collaborator, method + "_metered", None)
            if variant is not None:
                try:
                    value, usage = await variant(**kwargs)
                except MeteredCallError as exc:
                    accumulated = add_usage(accumulated, exc.usage)
                    if token_over_budget():
                        raise _PostAccountingBudgetExceeded from exc
                    raise exc.cause from exc
            else:
                value, usage = await getattr(collaborator, method)(**kwargs), EMPTY_USAGE
            accumulated = add_usage(accumulated, usage)
            if token_over_budget():
                raise _PostAccountingBudgetExceeded
            return value

        def elapsed_ms() -> int:
            return int((self._clock() - started_at) * 1000)

        def token_over_budget() -> bool:
            # Token is post-accounting (`>`); deadline is a pre-stage check
            # (`>=`). This intentional asymmetry mirrors flat-loop-gate §Budget.
            policy = self._policy
            return (
                policy.max_total_tokens is not None
                and accumulated.total_tokens > policy.max_total_tokens
            )

        def deadline_reached() -> bool:
            policy = self._policy
            return (
                policy.max_wall_clock_ms is not None
                and elapsed_ms() >= policy.max_wall_clock_ms
            )

        def record(
            stage: WritingLoopStageName, status: WritingLoopStageStatus,
            *, finding: WritingGateFinding | None = None,
            pointer_ids: tuple[str, ...] = (),
        ) -> None:
            stages.append(WritingLoopStage(
                stage, len(stages) + 1, status,
                candidate_hash=hash_text(current_candidate.text),
                finding_fingerprint=(
                    None if finding is None else finding_fingerprint(finding)
                ),
                pointer_ids=pointer_ids,
            ))

        def summary(status: WritingLoopStatus) -> WritingLoopSummary:
            return WritingLoopSummary(
                status, revision_rounds, retrieval_rounds, gate_evaluations,
                total_tokens=accumulated.total_tokens, wall_clock_ms=elapsed_ms(),
            )

        def result(status: WritingLoopStatus) -> WritingReviseGateResult:
            return WritingReviseGateResult(
                current_candidate, last_gate, summary(status), tuple(stages)
            )

        async def refresh_report() -> bool:
            nonlocal current_candidate
            if deadline_reached():
                return False
            try:
                enriched = await metered(
                    self._reporter, "enrich",
                    candidate=current_candidate, package=current_package,
                )
            except _PostAccountingBudgetExceeded:
                return False
            except Exception as exc:
                record(WritingLoopStageName.REPORT, WritingLoopStageStatus.FAILED)
                raise WritingReviseReportFailure(
                    current_candidate, exc, gate=last_gate,
                    loop=summary(WritingLoopStatus.FAILED), stages=tuple(stages),
                ) from exc
            current_candidate = enriched
            record(WritingLoopStageName.REPORT, WritingLoopStageStatus.COMPLETED)
            return True

        async def evaluate_gate() -> bool:
            nonlocal gate_evaluations, last_gate
            if deadline_reached():
                return False
            gate_evaluations += 1
            try:
                evaluated = await metered(
                    self._gate, "evaluate",
                    request=request, candidate=current_candidate,
                    package=current_package,
                )
            except _PostAccountingBudgetExceeded:
                return False
            except Exception as exc:
                record(WritingLoopStageName.GATE, WritingLoopStageStatus.FAILED)
                raise WritingReviseGateFailure(
                    current_candidate, exc, gate=last_gate,
                    loop=summary(WritingLoopStatus.FAILED), stages=tuple(stages),
                ) from exc
            last_gate = evaluated
            record(WritingLoopStageName.GATE, WritingLoopStageStatus.COMPLETED)
            return True

        if deadline_reached():
            return result(WritingLoopStatus.BUDGET_EXHAUSTED)
        revision_rounds += 1
        try:
            revised = await metered(
                self._reviser, "revise",
                candidate=current_candidate,
                finding=finding,
                instruction=request.instruction,
                package=current_package,
            )
        except _PostAccountingBudgetExceeded:
            return result(WritingLoopStatus.BUDGET_EXHAUSTED)
        except Exception as exc:
            record(WritingLoopStageName.REVISE, WritingLoopStageStatus.FAILED,
                   finding=finding)
            raise WritingLoopRevisionFailure(
                current_candidate, exc, gate=None,
                loop=summary(WritingLoopStatus.FAILED), stages=tuple(stages),
            ) from exc
        current_candidate = revised
        record(WritingLoopStageName.REVISE, WritingLoopStageStatus.COMPLETED,
               finding=finding)
        if not await refresh_report():
            return result(WritingLoopStatus.BUDGET_EXHAUSTED)
        if not await evaluate_gate():
            return result(WritingLoopStatus.BUDGET_EXHAUSTED)

        while True:
            assert last_gate is not None
            if last_gate.decision is WritingGateDecision.PASS:
                return result(WritingLoopStatus.PASS)
            if last_gate.decision in {
                WritingGateDecision.NEEDS_USER_REVIEW,
                WritingGateDecision.BLOCK,
            }:
                return result(WritingLoopStatus.TERMINAL_DECISION)
            if last_gate.decision is WritingGateDecision.REVISE:
                eligible = _eligible_revision_finding(
                    current_candidate, last_gate.findings
                )
                if eligible is None:
                    return result(WritingLoopStatus.NOT_ELIGIBLE)
                if (revision_rounds >= self._policy.max_revision_rounds
                        or gate_evaluations >= self._policy.max_gate_evaluations
                        or deadline_reached()):
                    return result(WritingLoopStatus.BUDGET_EXHAUSTED)
                revision_rounds += 1
                try:
                    revised = await metered(
                        self._reviser, "revise",
                        candidate=current_candidate,
                        finding=eligible,
                        instruction=request.instruction,
                        package=current_package,
                    )
                except _PostAccountingBudgetExceeded:
                    return result(WritingLoopStatus.BUDGET_EXHAUSTED)
                except UnchangedWritingRevision:
                    record(
                        WritingLoopStageName.REVISE,
                        WritingLoopStageStatus.NO_CHANGE,
                        finding=eligible,
                    )
                    return result(WritingLoopStatus.NO_CHANGE)
                except Exception as exc:
                    record(
                        WritingLoopStageName.REVISE,
                        WritingLoopStageStatus.FAILED,
                        finding=eligible,
                    )
                    raise WritingLoopRevisionFailure(
                        current_candidate, exc, gate=last_gate,
                        loop=summary(WritingLoopStatus.FAILED),
                        stages=tuple(stages),
                    ) from exc
                current_candidate = revised
                record(
                    WritingLoopStageName.REVISE,
                    WritingLoopStageStatus.COMPLETED,
                    finding=eligible,
                )
                if not await refresh_report():
                    return result(WritingLoopStatus.BUDGET_EXHAUSTED)
                if not await evaluate_gate():
                    return result(WritingLoopStatus.BUDGET_EXHAUSTED)
                continue

            if last_gate.decision is WritingGateDecision.RETRIEVE_MORE:
                if (retrieval_rounds >= self._policy.max_retrieval_rounds
                        or gate_evaluations >= self._policy.max_gate_evaluations
                        or deadline_reached()):
                    return result(WritingLoopStatus.BUDGET_EXHAUSTED)
                retrieval_rounds += 1
                failed_stage = WritingLoopStageName.RETRIEVE_PLAN
                try:
                    if (self._retrieval_planner is None
                            or self._context_search is None):
                        raise WritingRetrievalConfigurationError(
                            "writing retrieval planner and context search are required"
                        )
                    if context_budget is None:
                        raise WritingRetrievalConfigurationError(
                            "context budget is required for retrieve_more"
                        )
                    retrieval = await metered(
                        self._retrieval_planner, "plan",
                        request=request, candidate=current_candidate,
                        gate=last_gate, current_position=current_position,
                    )
                    record(
                        WritingLoopStageName.RETRIEVE_PLAN,
                        WritingLoopStageStatus.COMPLETED,
                    )
                    failed_stage = WritingLoopStageName.CONTEXT_SEARCH
                    if deadline_reached():
                        return result(WritingLoopStatus.BUDGET_EXHAUSTED)
                    # Called directly (NOT via metered()): context_search owns
                    # its own ContextBudget, so its provider usage stays out of
                    # the loop's aggregate total_tokens. The B2b ceiling
                    # composition depends on this boundary (benchmark_writing_loop
                    # _TOKEN_STAGES excludes context_search); routing this through
                    # metered() would silently inflate the aggregate — locked by
                    # test_writing_loop_budget
                    # ::test_context_search_usage_excluded_from_aggregate_tokens.
                    delta = await self._context_search.build_context_package(
                        ContextSearchRequest(
                            project_id=request.project_id,
                            purpose=ContextSearchPurpose.WRITING_CONTEXT,
                            needs=retrieval.needs,
                            query=retrieval.query,
                            current_position=current_position,
                            context_budget=context_budget,
                        )
                    )
                    record(
                        WritingLoopStageName.CONTEXT_SEARCH,
                        WritingLoopStageStatus.COMPLETED,
                        pointer_ids=package_pointer_ids(delta),
                    )
                    failed_stage = WritingLoopStageName.MERGE
                    current_package = merge_context_packages(
                        current_package, delta,
                        max_tokens=context_budget.max_tokens,
                    )
                    record(
                        WritingLoopStageName.MERGE,
                        WritingLoopStageStatus.COMPLETED,
                        pointer_ids=package_pointer_ids(current_package),
                    )
                except _PostAccountingBudgetExceeded:
                    return result(WritingLoopStatus.BUDGET_EXHAUSTED)
                except Exception as exc:
                    record(failed_stage, WritingLoopStageStatus.FAILED)
                    raise WritingRetrievalFailure(
                        current_candidate, exc, gate=last_gate,
                        loop=summary(WritingLoopStatus.FAILED),
                        stages=tuple(stages),
                    ) from exc
                if not await evaluate_gate():
                    return result(WritingLoopStatus.BUDGET_EXHAUSTED)
                continue

            return result(WritingLoopStatus.TERMINAL_DECISION)


def _is_eligible_continuity_revise(
    candidate: WritingCandidate, finding: WritingGateFinding,
) -> bool:
    """Per-finding eligibility, unchanged from the single-finding rule: a
    continuity finding recommending revise whose evidence occurs exactly once in
    the candidate (unambiguous splice anchor). do_not_use/pov stay out of the
    auto-splice path (owner D1=A) — the Gate contract routes those to
    block/needs_user_review, and continuity is the only auto-revisable type.
    """
    return (
        finding.finding_type is WritingGateFindingType.CONTINUITY
        and finding.recommended_decision is WritingGateDecision.REVISE
        and bool(finding.evidence.strip())
        and candidate.text.count(finding.evidence) == 1
    )


def _eligible_revision_finding(
    candidate: WritingCandidate,
    findings: tuple[WritingGateFinding, ...],
) -> WritingGateFinding | None:
    """Select the single best eligible continuity revise finding, or None.

    Multi-finding (owner D1=A continuity-only, D2=A sequential, D3=A severity
    desc): a Gate revise result may carry several revise-recommended findings.
    The loop revises one per round and re-gates, so this picks the highest-
    priority eligible one rather than requiring exactly one (the old "len != 1 →
    None" dead-ended a normal multi-continuity Gate result). Ordering: error
    severity before warning, then Gate return order (stable). Returns None when
    no finding is eligible (empty, or all ineligible) → loop yields
    ``not_eligible``, unchanged.
    """
    eligible = [f for f in findings if _is_eligible_continuity_revise(candidate, f)]
    if not eligible:
        return None
    # error before warning (D3=A); ties broken by Gate order via smallest index.
    return max(
        enumerate(eligible),
        key=lambda item: (item[1].severity is WritingGateSeverity.ERROR, -item[0]),
    )[1]
