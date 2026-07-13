"""One-shot partial-revise, report refresh, then Writing Gate composition."""

from __future__ import annotations

from dataclasses import dataclass
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
    WritingGateResult,
    WritingRequest,
)
from services.application.app.writing.retrieval import (
    WritingRetrievalPlan,
    merge_context_packages,
)


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


@dataclass(frozen=True, slots=True)
class WritingReviseGateResult:
    candidate: WritingCandidate
    gate: WritingGateResult


class WritingReviseGateFailure(RuntimeError):
    def __init__(self, candidate: WritingCandidate, cause: Exception) -> None:
        super().__init__(str(cause))
        self.candidate = candidate
        self.cause = cause


class WritingReviseReportFailure(RuntimeError):
    def __init__(self, candidate: WritingCandidate, cause: Exception) -> None:
        super().__init__(str(cause))
        self.candidate = candidate
        self.cause = cause


class WritingRetrievalConfigurationError(RuntimeError):
    pass


class WritingRetrievalFailure(RuntimeError):
    def __init__(self, candidate: WritingCandidate, gate: WritingGateResult,
                 cause: Exception) -> None:
        super().__init__(str(cause))
        self.candidate = candidate
        self.gate = gate
        self.cause = cause


class WritingReviseGateService:
    def __init__(
        self,
        *,
        reviser: CandidateReviser,
        reporter: CandidateReporter,
        gate: CandidateGate,
        retrieval_planner: FollowupRetrievalPlanner | None = None,
        context_search: ContextPackageSearch | None = None,
        max_retrieval_rounds: int = 1,
    ) -> None:
        if max_retrieval_rounds not in (0, 1):
            raise ValueError("max_retrieval_rounds must be 0 or 1")
        self._reviser = reviser
        self._reporter = reporter
        self._gate = gate
        self._retrieval_planner = retrieval_planner
        self._context_search = context_search
        self._max_retrieval_rounds = max_retrieval_rounds

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
        revised = await self._reviser.revise(
            candidate=candidate,
            finding=finding,
            instruction=request.instruction,
            package=package,
        )
        try:
            enriched = await self._reporter.enrich(revised, package)
        except Exception as exc:
            raise WritingReviseReportFailure(revised, exc) from exc
        try:
            gate = await self._gate.evaluate(
                request=request, candidate=enriched, package=package
            )
        except Exception as exc:
            raise WritingReviseGateFailure(enriched, exc) from exc
        if (gate.decision is not WritingGateDecision.RETRIEVE_MORE
                or self._max_retrieval_rounds == 0):
            return WritingReviseGateResult(candidate=enriched, gate=gate)
        try:
            if self._retrieval_planner is None or self._context_search is None:
                raise WritingRetrievalConfigurationError(
                    "writing retrieval planner and context search are required"
                )
            if context_budget is None:
                raise WritingRetrievalConfigurationError(
                    "context budget is required for retrieve_more"
                )
            retrieval = await self._retrieval_planner.plan(
                request=request, candidate=enriched, gate=gate,
                current_position=current_position,
            )
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
            merged = merge_context_packages(
                package, delta, max_tokens=context_budget.max_tokens
            )
        except Exception as exc:
            raise WritingRetrievalFailure(enriched, gate, exc) from exc
        try:
            final_gate = await self._gate.evaluate(
                request=request, candidate=enriched, package=merged
            )
        except Exception as exc:
            raise WritingReviseGateFailure(enriched, exc) from exc
        return WritingReviseGateResult(candidate=enriched, gate=final_gate)
