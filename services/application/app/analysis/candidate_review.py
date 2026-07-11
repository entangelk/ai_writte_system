"""Phase 6 candidate review state transition orchestration (v1.6.61).

A reviewer confirms or rejects a ``needs_review`` candidate. This service is the
choke point that ties the deterministic candidate state machine together with
its side effects (kickoff brief
``docs/plans/06-candidate-state-transition-decisions.md``):

* **confirm** (D1=separate model): candidate ``needs_review→confirmed`` **and**
  promotion to a canonical ``MemoryEntry`` (reusing the idempotent
  ``promote_candidate``); its open conflict review-queue entries are RESOLVED.
* **reject**: candidate ``needs_review→rejected`` (no promotion, retained for
  audit — D5); its open conflict review-queue entries are DISMISSED.
* both transitions enqueue a ``CANDIDATE_REMOVED`` de-index event (D2) so the
  candidate leaves the candidate index (its knowledge, if confirmed, is served
  by the canonical path instead).

Idempotent (D4): re-applying the same transition is a no-op replay — no
duplicate status write, promotion, de-index enqueue, or queue transition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from services.application.app.analysis.models import AnalysisCandidateStatus
from services.application.app.analysis.review_queue import ReviewQueueService
from services.application.app.analysis.service import AnalysisService
from services.application.app.memory.models import PromotionMode
from services.application.app.memory.service import MemoryService


class CandidateRemovalOutbox(Protocol):
    """Structural seam for enqueuing candidate de-index (mirror of the b-2
    ``CandidateReindexOutbox`` upsert seam)."""

    def enqueue_candidate_removed(
        self, *, project_id: str, candidate_id: str
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class CandidateReviewResult:
    candidate_id: str
    status: AnalysisCandidateStatus
    memory_id: str | None
    idempotent_replay: bool


class CandidateReviewService:
    def __init__(
        self,
        *,
        analysis_service: AnalysisService,
        memory_service: MemoryService,
        removal_outbox: CandidateRemovalOutbox | None = None,
        review_queue: ReviewQueueService | None = None,
    ) -> None:
        self._analysis = analysis_service
        self._memory = memory_service
        # Optional so callers/tests without an index or queue keep working: the
        # transition still happens, only the de-index/queue side effects are
        # skipped (mirrors the b-2 optional reindex_outbox).
        self._removal_outbox = removal_outbox
        self._review_queue = review_queue

    def confirm(
        self, *, project_id: str, candidate_id: str
    ) -> CandidateReviewResult:
        transition = self._analysis.transition_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            target=AnalysisCandidateStatus.CONFIRMED,
        )
        # Promotion is idempotent, so a replay returns the already-minted memory.
        promotion = self._memory.promote_candidate(
            project_id=project_id,
            candidate=transition.candidate,
            mode=PromotionMode.MANUAL,
        )
        if transition.changed:
            self._enqueue_removed(project_id, candidate_id)
            if self._review_queue is not None:
                self._review_queue.resolve_for_candidate(
                    project_id=project_id, candidate_id=candidate_id
                )
        return CandidateReviewResult(
            candidate_id=candidate_id,
            status=AnalysisCandidateStatus.CONFIRMED,
            memory_id=promotion.memory.id,
            idempotent_replay=not transition.changed,
        )

    def reject(
        self, *, project_id: str, candidate_id: str
    ) -> CandidateReviewResult:
        transition = self._analysis.transition_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            target=AnalysisCandidateStatus.REJECTED,
        )
        if transition.changed:
            self._enqueue_removed(project_id, candidate_id)
            if self._review_queue is not None:
                self._review_queue.dismiss_for_candidate(
                    project_id=project_id, candidate_id=candidate_id
                )
        return CandidateReviewResult(
            candidate_id=candidate_id,
            status=AnalysisCandidateStatus.REJECTED,
            memory_id=None,
            idempotent_replay=not transition.changed,
        )

    def _enqueue_removed(self, project_id: str, candidate_id: str) -> None:
        if self._removal_outbox is not None:
            self._removal_outbox.enqueue_candidate_removed(
                project_id=project_id, candidate_id=candidate_id
            )
