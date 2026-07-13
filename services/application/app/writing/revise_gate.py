"""One-shot partial-revise then Writing Gate composition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from services.application.app.context_search.models import ContextPackage
from services.application.app.writing.models import (
    WritingCandidate,
    WritingGateFinding,
    WritingGateResult,
    WritingRequest,
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


@dataclass(frozen=True, slots=True)
class WritingReviseGateResult:
    candidate: WritingCandidate
    gate: WritingGateResult


class WritingReviseGateFailure(RuntimeError):
    def __init__(self, candidate: WritingCandidate, cause: Exception) -> None:
        super().__init__(str(cause))
        self.candidate = candidate
        self.cause = cause


class WritingReviseGateService:
    def __init__(self, *, reviser: CandidateReviser, gate: CandidateGate) -> None:
        self._reviser = reviser
        self._gate = gate

    async def run(
        self,
        *,
        request: WritingRequest,
        candidate: WritingCandidate,
        finding: WritingGateFinding,
        package: ContextPackage,
    ) -> WritingReviseGateResult:
        revised = await self._reviser.revise(
            candidate=candidate,
            finding=finding,
            instruction=request.instruction,
            package=package,
        )
        try:
            gate = await self._gate.evaluate(
                request=request, candidate=revised, package=package
            )
        except Exception as exc:
            raise WritingReviseGateFailure(revised, exc) from exc
        return WritingReviseGateResult(candidate=revised, gate=gate)
