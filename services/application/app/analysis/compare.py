"""Phase 2B.3: candidate ↔ canonical-memory compare and action proposals.

Given an analysis job's candidates and the existing canonical memory store,
produce one action proposal per candidate. The judgment is a hybrid (D3=A):

* the deterministic scope key (D2=A, character-only) decides *which* canonical
  memories a candidate could refer to;
* if none match, the action is ``create`` deterministically (no LLM);
* if exactly one matches, an injected ``CompareJudge`` (terminal-JSON LLM,
  D1=A) labels it ``update``/``add_evidence``/``no_change``/``conflict``;
* if several canonical memories share the identity (2B.1 allowed duplicate
  canonical per scope), that ambiguous store state is surfaced deterministically
  as ``conflict`` for later reconciliation (2B.4 / merge-split review).

This slice produces *proposals only* (D4=A). It never writes to the memory
store — versioned upsert is 2B.4. ``merge``/``split`` are review-only and not
emitted here.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from enum import StrEnum
from typing import Awaitable, Protocol

from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateType,
)
from services.application.app.memory.models import MemoryEntry, MemoryStatus
from services.application.app.memory.scope import MemoryScope, derive_scope
from services.application.app.memory.service import MemoryService


class CompareAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    ADD_EVIDENCE = "add_evidence"
    NO_CHANGE = "no_change"
    CONFLICT = "conflict"


# Actions the LLM judge is allowed to return for a matched pair. ``create`` is
# deterministic (no match) and must never come from the judge.
JUDGE_ACTIONS = frozenset(
    {
        CompareAction.UPDATE,
        CompareAction.ADD_EVIDENCE,
        CompareAction.NO_CHANGE,
        CompareAction.CONFLICT,
    }
)


class AnalysisCompareError(Exception):
    pass


class CompareJudgeNotConfigured(AnalysisCompareError):
    """A candidate matched an existing memory but no judge was configured."""


class InvalidJudgeResult(AnalysisCompareError):
    """The judge returned an action outside the allowed matched-pair set."""


@dataclass(frozen=True, slots=True)
class JudgeResult:
    action: CompareAction
    rationale: str


@dataclass(frozen=True, slots=True)
class ActionProposal:
    candidate_id: str
    candidate_type: AnalysisCandidateType
    action: CompareAction
    matched_memory_id: str | None
    rationale: str


class CompareJudge(Protocol):
    # May be sync (fake) or async (the terminal-JSON Gateway judge); the service
    # awaits the result when it is awaitable, so either shape fits the seam.
    def judge(
        self, *, candidate: AnalysisCandidate, memory: MemoryEntry
    ) -> JudgeResult | Awaitable[JudgeResult]: ...


class AnalysisCompareService:
    def __init__(
        self,
        *,
        memory_service: MemoryService,
        judge: CompareJudge | None = None,
    ) -> None:
        self._memory = memory_service
        self._judge = judge

    async def compare_job(
        self,
        *,
        project_id: str,
        job_id: str,
        candidates: tuple[AnalysisCandidate, ...],
    ) -> tuple[ActionProposal, ...]:
        proposals: list[ActionProposal] = []
        for candidate in candidates:
            proposals.append(
                await self._compare_candidate(project_id, job_id, candidate)
            )
        return tuple(proposals)

    async def _compare_candidate(
        self, project_id: str, job_id: str, candidate: AnalysisCandidate
    ) -> ActionProposal:
        scope = derive_scope(candidate.candidate_type, candidate.payload)
        matches = self._find_matches(project_id, job_id, candidate, scope)
        if not matches:
            # No deterministic identity match (includes event/open_question,
            # which have no scope key): treat as a new subject.
            return ActionProposal(
                candidate_id=candidate.id,
                candidate_type=candidate.candidate_type,
                action=CompareAction.CREATE,
                matched_memory_id=None,
                rationale="no matching canonical memory for this identity",
            )
        if len(matches) > 1:
            # Ambiguous store state (duplicate canonical per identity, a 2B.1
            # boundary deferred to 2B.3): surface for reconciliation.
            return ActionProposal(
                candidate_id=candidate.id,
                candidate_type=candidate.candidate_type,
                action=CompareAction.CONFLICT,
                matched_memory_id=None,
                rationale=(
                    f"{len(matches)} canonical memories share identity "
                    f"{scope.scope_type}:{scope.scope_id}"
                ),
            )
        memory = matches[0]
        if self._judge is None:
            raise CompareJudgeNotConfigured(
                "a candidate matched an existing memory but no compare judge "
                "is configured"
            )
        result = self._judge.judge(candidate=candidate, memory=memory)
        if inspect.isawaitable(result):
            result = await result
        if result.action not in JUDGE_ACTIONS:
            raise InvalidJudgeResult(
                f"judge returned {result.action.value}, which is not a valid "
                "matched-pair action"
            )
        return ActionProposal(
            candidate_id=candidate.id,
            candidate_type=candidate.candidate_type,
            action=result.action,
            matched_memory_id=memory.id,
            rationale=result.rationale,
        )

    def _find_matches(
        self,
        project_id: str,
        job_id: str,
        candidate: AnalysisCandidate,
        scope: MemoryScope | None,
    ) -> tuple[MemoryEntry, ...]:
        if scope is None:
            return ()
        return tuple(
            entry
            for entry in self._memory.list_memories(project_id=project_id)
            if entry.status is MemoryStatus.CANONICAL
            and entry.scope == scope
            # D6: self-exclusion — a candidate does not compare against the
            # memory its own job promoted (that is always no_change noise).
            and entry.analysis_job_id != job_id
        )
