"""Infrastructure-free Phase 2B.1 canonical memory service.

Promotes Phase 2A ``needs_review`` candidates into canonical ``MemoryEntry``
records. Two promotion paths exist:

* manual approval — the user approves a candidate; it always becomes canonical
  regardless of confidence (explicit human override).
* deterministic threshold gate — a system policy (not the Analysis AI) promotes
  a candidate only when its confidence meets an injected threshold. Below the
  threshold the candidate stays ``needs_review`` and the manual path is
  preserved. The threshold defaults to ``None`` (auto-promotion disabled) so no
  canon is minted from a guessed value; real thresholds await quality fixtures
  (SoT v1.6.39 D2=B).
"""

from __future__ import annotations

from services.application.app.analysis.models import (
    AnalysisCandidate,
    immutable_payload,
)
from services.application.app.memory.models import (
    MemoryEntry,
    MemoryStatus,
    PromoteMemoryResult,
    PromotionMode,
)
from services.application.app.memory.repository import (
    DuplicatePromotionRequest,
    MemoryRepository,
)


class MemoryError(ValueError):
    pass


class MemoryNotFound(MemoryError):
    pass


class InMemoryMemoryRepository:
    def __init__(self) -> None:
        self._seq = 0
        self.memories: dict[str, MemoryEntry] = {}
        self._candidate_index: dict[tuple[str, str], str] = {}

    def next_memory_id(self) -> str:
        self._seq += 1
        return f"memory-{self._seq}"

    def get_memory(self, memory_id: str) -> MemoryEntry | None:
        return self.memories.get(memory_id)

    def find_memory_by_candidate(
        self, project_id: str, source_candidate_id: str
    ) -> str | None:
        return self._candidate_index.get((project_id, source_candidate_id))

    def put_memory(self, entry: MemoryEntry) -> None:
        key = (entry.project_id, entry.source_candidate_id)
        if key in self._candidate_index:
            raise DuplicatePromotionRequest(
                "candidate already promoted to a memory entry"
            )
        self.memories[entry.id] = entry
        self._candidate_index[key] = entry.id

    def list_memories_for_project(
        self, project_id: str
    ) -> tuple[MemoryEntry, ...]:
        return tuple(
            entry
            for entry in self.memories.values()
            if entry.project_id == project_id
        )


class MemoryService:
    def __init__(
        self,
        repository: MemoryRepository,
        *,
        auto_promotion_threshold: float | None = None,
    ) -> None:
        self._repo = repository
        self._auto_promotion_threshold = auto_promotion_threshold

    @property
    def auto_promotion_threshold(self) -> float | None:
        return self._auto_promotion_threshold

    def evaluate_auto_promotion(self, candidate: AnalysisCandidate) -> bool:
        """Deterministic threshold gate. Off by default (``None``)."""
        threshold = self._auto_promotion_threshold
        return threshold is not None and candidate.confidence >= threshold

    def promote_candidate(
        self,
        *,
        project_id: str,
        candidate: AnalysisCandidate,
        mode: PromotionMode,
    ) -> PromoteMemoryResult:
        if candidate.project_id != project_id:
            raise MemoryNotFound("analysis candidate not found")

        existing_id = self._repo.find_memory_by_candidate(project_id, candidate.id)
        if existing_id is not None:
            return PromoteMemoryResult(
                memory=self._require_memory(project_id, existing_id),
                idempotent_replay=True,
            )

        applied_threshold = (
            self._auto_promotion_threshold
            if mode is PromotionMode.AUTO_THRESHOLD
            else None
        )
        entry = MemoryEntry(
            id=self._repo.next_memory_id(),
            project_id=project_id,
            memory_type=candidate.candidate_type,
            status=MemoryStatus.CANONICAL,
            provenance=candidate.provenance,
            confidence=candidate.confidence,
            source_ref_ids=candidate.source_ref_ids,
            payload=immutable_payload(candidate.payload),
            version=1,
            analysis_job_id=candidate.job_id,
            source_candidate_id=candidate.id,
            promotion_mode=mode,
            applied_threshold=applied_threshold,
        )
        try:
            self._repo.put_memory(entry)
        except DuplicatePromotionRequest:
            # Concurrent promotion of the same candidate: replay the winner.
            return PromoteMemoryResult(
                memory=self._require_memory_by_candidate(project_id, candidate.id),
                idempotent_replay=True,
            )
        return PromoteMemoryResult(memory=entry, idempotent_replay=False)

    def auto_promote_candidate(
        self, *, project_id: str, candidate: AnalysisCandidate
    ) -> PromoteMemoryResult | None:
        """Promote only if the deterministic threshold gate fires.

        Returns ``None`` when the candidate is below threshold, leaving it
        ``needs_review`` with the manual path intact.
        """
        if not self.evaluate_auto_promotion(candidate):
            return None
        return self.promote_candidate(
            project_id=project_id,
            candidate=candidate,
            mode=PromotionMode.AUTO_THRESHOLD,
        )

    def get_memory(self, *, project_id: str, memory_id: str) -> MemoryEntry:
        return self._require_memory(project_id, memory_id)

    def list_memories(self, *, project_id: str) -> tuple[MemoryEntry, ...]:
        return self._repo.list_memories_for_project(project_id)

    def _require_memory(self, project_id: str, memory_id: str) -> MemoryEntry:
        memory = self._repo.get_memory(memory_id)
        if memory is None or memory.project_id != project_id:
            raise MemoryNotFound("memory entry not found")
        return memory

    def _require_memory_by_candidate(
        self, project_id: str, source_candidate_id: str
    ) -> MemoryEntry:
        memory_id = self._repo.find_memory_by_candidate(
            project_id, source_candidate_id
        )
        if memory_id is None:
            raise MemoryNotFound("memory entry not found")
        return self._require_memory(project_id, memory_id)
