"""Bounded partial-revise/report/Gate and targeted-retrieval composition."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from services.application.app.context_search.models import (
    ContextBudget,
    ContextPackage,
    ContextSearchPurpose,
    ContextSearchRequest,
    CurrentPosition,
)
from services.application.app.writing.models import (
    WritingCandidate,
    WritingGateDecision,
    WritingGateFinding,
    WritingGateFindingType,
    WritingGateResult,
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
    """Configurable structural caps; counts include the initial requested work."""

    max_revision_rounds: int = 2
    max_retrieval_rounds: int = 1
    max_gate_evaluations: int = 3

    def __post_init__(self) -> None:
        if self.max_revision_rounds < 1:
            raise ValueError("max_revision_rounds must be at least 1")
        if self.max_retrieval_rounds < 0:
            raise ValueError("max_retrieval_rounds must not be negative")
        if self.max_gate_evaluations < 1:
            raise ValueError("max_gate_evaluations must be at least 1")


@dataclass(frozen=True, slots=True)
class WritingLoopStage:
    stage: WritingLoopStageName
    ordinal: int
    status: WritingLoopStageStatus


@dataclass(frozen=True, slots=True)
class WritingLoopSummary:
    status: WritingLoopStatus
    revision_rounds: int
    retrieval_rounds: int
    gate_evaluations: int


@dataclass(frozen=True, slots=True)
class WritingReviseGateResult:
    candidate: WritingCandidate
    gate: WritingGateResult
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
    ) -> None:
        self._reviser = reviser
        self._reporter = reporter
        self._gate = gate
        self._retrieval_planner = retrieval_planner
        self._context_search = context_search
        self._policy = policy or WritingLoopPolicy()

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

        def record(
            stage: WritingLoopStageName, status: WritingLoopStageStatus,
        ) -> None:
            stages.append(WritingLoopStage(stage, len(stages) + 1, status))

        def summary(status: WritingLoopStatus) -> WritingLoopSummary:
            return WritingLoopSummary(
                status, revision_rounds, retrieval_rounds, gate_evaluations
            )

        def result(status: WritingLoopStatus) -> WritingReviseGateResult:
            assert last_gate is not None
            return WritingReviseGateResult(
                current_candidate, last_gate, summary(status), tuple(stages)
            )

        async def refresh_report() -> None:
            nonlocal current_candidate
            try:
                current_candidate = await self._reporter.enrich(
                    current_candidate, current_package
                )
            except Exception as exc:
                record(WritingLoopStageName.REPORT, WritingLoopStageStatus.FAILED)
                raise WritingReviseReportFailure(
                    current_candidate, exc, gate=last_gate,
                    loop=summary(WritingLoopStatus.FAILED), stages=tuple(stages),
                ) from exc
            record(WritingLoopStageName.REPORT, WritingLoopStageStatus.COMPLETED)

        async def evaluate_gate() -> None:
            nonlocal gate_evaluations, last_gate
            gate_evaluations += 1
            try:
                evaluated = await self._gate.evaluate(
                    request=request, candidate=current_candidate,
                    package=current_package,
                )
            except Exception as exc:
                record(WritingLoopStageName.GATE, WritingLoopStageStatus.FAILED)
                raise WritingReviseGateFailure(
                    current_candidate, exc, gate=last_gate,
                    loop=summary(WritingLoopStatus.FAILED), stages=tuple(stages),
                ) from exc
            last_gate = evaluated
            record(WritingLoopStageName.GATE, WritingLoopStageStatus.COMPLETED)

        revision_rounds += 1
        try:
            current_candidate = await self._reviser.revise(
                candidate=current_candidate,
                finding=finding,
                instruction=request.instruction,
                package=current_package,
            )
        except Exception as exc:
            record(WritingLoopStageName.REVISE, WritingLoopStageStatus.FAILED)
            raise WritingLoopRevisionFailure(
                current_candidate, exc, gate=None,
                loop=summary(WritingLoopStatus.FAILED), stages=tuple(stages),
            ) from exc
        record(WritingLoopStageName.REVISE, WritingLoopStageStatus.COMPLETED)
        await refresh_report()
        await evaluate_gate()

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
                        or gate_evaluations >= self._policy.max_gate_evaluations):
                    return result(WritingLoopStatus.BUDGET_EXHAUSTED)
                revision_rounds += 1
                try:
                    revised = await self._reviser.revise(
                        candidate=current_candidate,
                        finding=eligible,
                        instruction=request.instruction,
                        package=current_package,
                    )
                except UnchangedWritingRevision:
                    record(
                        WritingLoopStageName.REVISE,
                        WritingLoopStageStatus.NO_CHANGE,
                    )
                    return result(WritingLoopStatus.NO_CHANGE)
                except Exception as exc:
                    record(
                        WritingLoopStageName.REVISE,
                        WritingLoopStageStatus.FAILED,
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
                )
                await refresh_report()
                await evaluate_gate()
                continue

            if last_gate.decision is WritingGateDecision.RETRIEVE_MORE:
                if (retrieval_rounds >= self._policy.max_retrieval_rounds
                        or gate_evaluations >= self._policy.max_gate_evaluations):
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
                    retrieval = await self._retrieval_planner.plan(
                        request=request, candidate=current_candidate,
                        gate=last_gate, current_position=current_position,
                    )
                    record(
                        WritingLoopStageName.RETRIEVE_PLAN,
                        WritingLoopStageStatus.COMPLETED,
                    )
                    failed_stage = WritingLoopStageName.CONTEXT_SEARCH
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
                    )
                    failed_stage = WritingLoopStageName.MERGE
                    current_package = merge_context_packages(
                        current_package, delta,
                        max_tokens=context_budget.max_tokens,
                    )
                    record(
                        WritingLoopStageName.MERGE,
                        WritingLoopStageStatus.COMPLETED,
                    )
                except Exception as exc:
                    record(failed_stage, WritingLoopStageStatus.FAILED)
                    raise WritingRetrievalFailure(
                        current_candidate, exc, gate=last_gate,
                        loop=summary(WritingLoopStatus.FAILED),
                        stages=tuple(stages),
                    ) from exc
                await evaluate_gate()
                continue

            return result(WritingLoopStatus.TERMINAL_DECISION)


def _eligible_revision_finding(
    candidate: WritingCandidate,
    findings: tuple[WritingGateFinding, ...],
) -> WritingGateFinding | None:
    """Lock both directions: one exact continuity revise, nothing broader."""

    if len(findings) != 1:
        return None
    finding = findings[0]
    if finding.finding_type is not WritingGateFindingType.CONTINUITY:
        return None
    if finding.recommended_decision is not WritingGateDecision.REVISE:
        return None
    if not finding.evidence.strip() or candidate.text.count(finding.evidence) != 1:
        return None
    return finding
