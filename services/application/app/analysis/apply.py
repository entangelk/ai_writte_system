"""Phase 2B.4: apply compare action proposals to the canonical memory store.

Phase 2B.3 produces ``ActionProposal``s (proposal only); this slice reflects the
*safe* actions into deterministic memory writes (D1=A: a distinct apply step,
never inside compare):

* ``create``       → mint a new canonical ``MemoryEntry`` (version=1).
* ``update``       → new version, prior entry superseded (payload replaced).
* ``add_evidence`` → new version, prior entry superseded (payload preserved).
* ``no_change``    → no write.
* ``conflict`` (and future ``merge``/``split``) → review-only, no write (D7).

The write itself is a deterministic system operation (not the Analysis AI): the
proposals carry the already-decided labels. ``merge``/``split`` are not emitted
by 2B.3, so only ``conflict`` reaches the review-only branch here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from services.application.app.analysis.compare import ActionProposal, CompareAction
from services.application.app.analysis.models import AnalysisCandidate
from services.application.app.memory.models import PromotionMode
from services.application.app.memory.service import MemoryService


class MemoryReindexOutbox(Protocol):
    """Phase 2B.5 (D3=B): enqueue a memory reindex; the worker drains it."""

    def enqueue_memory_upserted(
        self, *, project_id: str, memory_id: str, version: int
    ) -> object: ...


class ApplyOutcome(StrEnum):
    CREATED = "created"
    VERSIONED = "versioned"
    NO_CHANGE = "no_change"
    SKIPPED_REVIEW = "skipped_review"


class MemoryApplyError(Exception):
    pass


class UnknownCandidate(MemoryApplyError):
    """A proposal references a candidate that is not part of the job."""


class MissingMatchedMemory(MemoryApplyError):
    """update/add_evidence proposal without a matched memory to version."""


@dataclass(frozen=True, slots=True)
class AppliedProposal:
    candidate_id: str
    action: CompareAction
    outcome: ApplyOutcome
    memory_id: str | None
    superseded_memory_id: str | None
    version: int | None
    idempotent_replay: bool


class MemoryApplyService:
    def __init__(
        self,
        *,
        memory_service: MemoryService,
        reindex_outbox: MemoryReindexOutbox | None = None,
    ) -> None:
        self._memory = memory_service
        self._reindex_outbox = reindex_outbox

    def apply_proposals(
        self,
        *,
        project_id: str,
        proposals: tuple[ActionProposal, ...],
        candidates: tuple[AnalysisCandidate, ...],
    ) -> tuple[AppliedProposal, ...]:
        by_id = {candidate.id: candidate for candidate in candidates}
        applied = tuple(
            self._apply_one(project_id, proposal, by_id) for proposal in proposals
        )
        if self._reindex_outbox is not None:
            for result in applied:
                self._enqueue_reindex(project_id, result)
        return applied

    def _enqueue_reindex(
        self, project_id: str, result: AppliedProposal
    ) -> None:
        # Only writes that touched a canonical version need reindexing;
        # no_change/conflict wrote nothing (D4: no enqueue). memory_id/version
        # are always set for CREATED/VERSIONED.
        if result.outcome not in (ApplyOutcome.CREATED, ApplyOutcome.VERSIONED):
            return
        assert result.memory_id is not None and result.version is not None
        self._reindex_outbox.enqueue_memory_upserted(
            project_id=project_id,
            memory_id=result.memory_id,
            version=result.version,
        )

    def _apply_one(
        self,
        project_id: str,
        proposal: ActionProposal,
        by_id: dict[str, AnalysisCandidate],
    ) -> AppliedProposal:
        action = proposal.action

        if action is CompareAction.NO_CHANGE:
            return self._skip(proposal, ApplyOutcome.NO_CHANGE)
        if action is CompareAction.CONFLICT:
            # D7: conflict (and future merge/split) is review-only — never an
            # automatic write.
            return self._skip(proposal, ApplyOutcome.SKIPPED_REVIEW)

        candidate = by_id.get(proposal.candidate_id)
        if candidate is None:
            raise UnknownCandidate(
                f"candidate {proposal.candidate_id} is not part of this job"
            )

        if action is CompareAction.CREATE:
            result = self._memory.promote_candidate(
                project_id=project_id,
                candidate=candidate,
                mode=PromotionMode.MANUAL,
            )
            return AppliedProposal(
                candidate_id=proposal.candidate_id,
                action=action,
                outcome=ApplyOutcome.CREATED,
                memory_id=result.memory.id,
                superseded_memory_id=None,
                version=result.memory.version,
                idempotent_replay=result.idempotent_replay,
            )

        # update / add_evidence: version an existing canonical memory.
        if proposal.matched_memory_id is None:
            raise MissingMatchedMemory(
                f"{action.value} proposal has no matched_memory_id"
            )
        if action is CompareAction.UPDATE:
            result = self._memory.record_updated_version(
                project_id=project_id,
                candidate=candidate,
                target_memory_id=proposal.matched_memory_id,
            )
        else:  # ADD_EVIDENCE
            result = self._memory.record_evidence_version(
                project_id=project_id,
                candidate=candidate,
                target_memory_id=proposal.matched_memory_id,
            )
        return AppliedProposal(
            candidate_id=proposal.candidate_id,
            action=action,
            outcome=ApplyOutcome.VERSIONED,
            memory_id=result.memory.id,
            superseded_memory_id=proposal.matched_memory_id,
            version=result.memory.version,
            idempotent_replay=result.idempotent_replay,
        )

    @staticmethod
    def _skip(
        proposal: ActionProposal, outcome: ApplyOutcome
    ) -> AppliedProposal:
        return AppliedProposal(
            candidate_id=proposal.candidate_id,
            action=proposal.action,
            outcome=outcome,
            memory_id=None,
            superseded_memory_id=None,
            version=None,
            idempotent_replay=False,
        )
