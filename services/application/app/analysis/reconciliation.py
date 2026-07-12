"""Human-authorized merge/split writes for open character conflicts."""

from dataclasses import dataclass
from enum import StrEnum

from typing import Protocol

from services.application.app.analysis.models import (
    AnalysisCandidateStatus, AnalysisCandidateType,
)
from services.application.app.analysis.review_queue import (
    ReviewQueueService,
    ReviewQueueStatus,
)
from services.application.app.analysis.service import AnalysisService
from services.application.app.memory.models import PromotionMode
from services.application.app.memory.service import MemoryService


class ReconciliationAction(StrEnum):
    MERGE = "merge"
    SPLIT = "split"


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    entry_id: str
    action: ReconciliationAction
    memory_id: str
    superseded_memory_id: str | None
    idempotent_replay: bool


class CharacterReconciliationService:
    class RemovalOutbox(Protocol):
        def enqueue_candidate_removed(
            self, *, project_id: str, candidate_id: str
        ) -> object: ...

    def __init__(self, *, analysis_service: AnalysisService,
                 memory_service: MemoryService,
                 review_queue: ReviewQueueService,
                 removal_outbox: RemovalOutbox | None = None) -> None:
        self._analysis = analysis_service
        self._memory = memory_service
        self._queue = review_queue
        self._removal_outbox = removal_outbox

    def reconcile(self, *, project_id: str, entry_id: str,
                  action: ReconciliationAction) -> ReconciliationResult:
        entry = self._queue.get(project_id=project_id, entry_id=entry_id)
        if entry.status is ReviewQueueStatus.RESOLVED:
            if entry.resolution_action != action.value or not entry.resolution_memory_id:
                raise ValueError("review entry was resolved with a different action")
            return ReconciliationResult(
                entry_id=entry.id, action=action,
                memory_id=entry.resolution_memory_id,
                superseded_memory_id=(
                    entry.matched_memory_id
                    if action is ReconciliationAction.MERGE else None
                ),
                idempotent_replay=True,
            )
        if entry.status is not ReviewQueueStatus.OPEN:
            raise ValueError("review queue entry is not open")
        candidate = self._analysis.get_candidate(
            project_id=project_id, candidate_id=entry.candidate_id
        )
        if candidate.candidate_type is not AnalysisCandidateType.CHARACTER_OBSERVATION:
            raise ValueError("merge/split reconciliation is character-only")

        if action is ReconciliationAction.MERGE:
            if entry.matched_memory_id is None:
                raise ValueError("merge requires a matched canonical memory")
            result = self._memory.record_evidence_version(
                project_id=project_id,
                candidate=candidate,
                target_memory_id=entry.matched_memory_id,
            )
            superseded = entry.matched_memory_id
        else:
            result = self._memory.promote_candidate(
                project_id=project_id, candidate=candidate,
                mode=PromotionMode.MANUAL,
            )
            superseded = None

        transition = self._analysis.transition_candidate(
            project_id=project_id, candidate_id=candidate.id,
            target=AnalysisCandidateStatus.CONFIRMED,
        )
        if transition.changed and self._removal_outbox is not None:
            self._removal_outbox.enqueue_candidate_removed(
                project_id=project_id, candidate_id=candidate.id
            )

        self._queue.mark_resolved(
            entry, action=action.value, memory_id=result.memory.id
        )
        return ReconciliationResult(
            entry_id=entry.id, action=action, memory_id=result.memory.id,
            superseded_memory_id=superseded,
            idempotent_replay=result.idempotent_replay,
        )
