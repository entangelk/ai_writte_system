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

from dataclasses import replace
from typing import Protocol

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
from services.application.app.memory.scope import derive_scope


def _union_source_refs(
    existing: tuple[str, ...], incoming: tuple[str, ...]
) -> tuple[str, ...]:
    """Order-preserving union: existing refs first, then new ones, deduped."""
    merged = dict.fromkeys(existing)
    for ref in incoming:
        merged.setdefault(ref, None)
    return tuple(merged)


class MemoryReindexOutbox(Protocol):
    """Phase 2B.5 (D3=B): enqueue a memory reindex when a canonical version is
    minted. Structural type (defined here, not imported from ``indexing``) so the
    memory service stays free of an indexing dependency."""

    def enqueue_memory_upserted(
        self, *, project_id: str, memory_id: str, version: int
    ) -> object: ...


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

    def update_memory(self, entry: MemoryEntry) -> None:
        # In-place replacement of an existing entry (e.g. superseding a prior
        # version). The candidate index is keyed on source_candidate_id, which
        # a status transition does not change, so it stays intact.
        self.memories[entry.id] = entry

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
        reindex_outbox: MemoryReindexOutbox | None = None,
    ) -> None:
        self._repo = repository
        self._auto_promotion_threshold = auto_promotion_threshold
        # Phase 2B.5 (D3=B): the single choke point for memory reindexing. Every
        # canonical version mint (manual promote, auto-promote, versioned upsert
        # via apply) enqueues here, so no write path can forget to index. Owner
        # decision 2026-07-07: promote paths reindex too, not backfill-only.
        self._reindex_outbox = reindex_outbox

    @property
    def auto_promotion_threshold(self) -> float | None:
        return self._auto_promotion_threshold

    def evaluate_auto_promotion(self, candidate: AnalysisCandidate) -> bool:
        """Deterministic threshold gate. Off by default (``None``)."""
        threshold = self._auto_promotion_threshold
        return threshold is not None and candidate.confidence >= threshold

    def is_candidate_promoted(self, project_id: str, candidate_id: str) -> bool:
        """Whether an analysis candidate has been promoted to a canonical entry.

        The promotion link is deterministic: a promote mints a MemoryEntry with
        ``source_candidate_id == candidate.id`` (see ``promote_candidate``). This
        is the canonical↔candidate dedup key ((e), v1.6.60): a promoted candidate
        still carries ``needs_review`` status (the transition is Phase 6), so the
        candidate retriever keeps surfacing it — context search suppresses it here
        instead. See docs/plans/04-canonical-candidate-dedup-decisions.md."""
        return (
            self._repo.find_memory_by_candidate(project_id, candidate_id)
            is not None
        )

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
            scope=derive_scope(candidate.candidate_type, candidate.payload),
        )
        try:
            self._repo.put_memory(entry)
        except DuplicatePromotionRequest:
            # Concurrent promotion of the same candidate: replay the winner.
            return PromoteMemoryResult(
                memory=self._require_memory_by_candidate(project_id, candidate.id),
                idempotent_replay=True,
            )
        self._enqueue_reindex(entry)
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

    def record_updated_version(
        self,
        *,
        project_id: str,
        candidate: AnalysisCandidate,
        target_memory_id: str,
    ) -> PromoteMemoryResult:
        """Phase 2B.4 ``update``: value changed → new version.

        Replaces the payload with the candidate's, unions source refs, and takes
        the candidate's confidence/provenance (D3).
        """
        return self._versioned_upsert(
            project_id=project_id,
            candidate=candidate,
            target_memory_id=target_memory_id,
            evidence_only=False,
        )

    def record_evidence_version(
        self,
        *,
        project_id: str,
        candidate: AnalysisCandidate,
        target_memory_id: str,
    ) -> PromoteMemoryResult:
        """Phase 2B.4 ``add_evidence``: same value, new source → new version.

        Preserves the prior payload/provenance, unions source refs, and keeps the
        higher confidence (D3).
        """
        return self._versioned_upsert(
            project_id=project_id,
            candidate=candidate,
            target_memory_id=target_memory_id,
            evidence_only=True,
        )

    def _versioned_upsert(
        self,
        *,
        project_id: str,
        candidate: AnalysisCandidate,
        target_memory_id: str,
        evidence_only: bool,
    ) -> PromoteMemoryResult:
        if candidate.project_id != project_id:
            raise MemoryNotFound("analysis candidate not found")

        # D5 idempotency: a candidate produces at most one memory write. A
        # re-application replays the version it already created.
        existing_id = self._repo.find_memory_by_candidate(project_id, candidate.id)
        if existing_id is not None:
            return PromoteMemoryResult(
                memory=self._require_memory(project_id, existing_id),
                idempotent_replay=True,
            )

        target = self._require_memory(project_id, target_memory_id)
        if target.status is not MemoryStatus.CANONICAL:
            raise MemoryError("cannot version a non-canonical memory entry")
        if candidate.candidate_type is not target.memory_type:
            raise MemoryError(
                "candidate type does not match the target memory type"
            )

        source_ref_ids = _union_source_refs(
            target.source_ref_ids, candidate.source_ref_ids
        )
        if evidence_only:
            payload = target.payload
            confidence = max(target.confidence, candidate.confidence)
            provenance = target.provenance
        else:
            payload = immutable_payload(candidate.payload)
            confidence = candidate.confidence
            provenance = candidate.provenance

        new_entry = MemoryEntry(
            id=self._repo.next_memory_id(),
            project_id=project_id,
            memory_type=target.memory_type,
            status=MemoryStatus.CANONICAL,
            provenance=provenance,
            confidence=confidence,
            source_ref_ids=source_ref_ids,
            payload=payload,
            version=target.version + 1,
            analysis_job_id=candidate.job_id,
            source_candidate_id=candidate.id,
            promotion_mode=PromotionMode.MANUAL,
            applied_threshold=None,
            scope=target.scope,
            supersedes=target.id,
        )
        try:
            self._repo.put_memory(new_entry)
        except DuplicatePromotionRequest:
            # Concurrent apply of the same candidate: replay the winner.
            return PromoteMemoryResult(
                memory=self._require_memory_by_candidate(project_id, candidate.id),
                idempotent_replay=True,
            )
        # Append-only: mint the new version first (canonical), then supersede the
        # prior entry so it is preserved immutably rather than overwritten.
        self._repo.update_memory(
            replace(target, status=MemoryStatus.SUPERSEDED)
        )
        self._enqueue_reindex(new_entry)
        return PromoteMemoryResult(memory=new_entry, idempotent_replay=False)

    def _enqueue_reindex(self, memory: MemoryEntry) -> None:
        # Only fresh canonical mints reach here (replays return earlier). Enqueue
        # is idempotent (dedup per memory_id) so this is safe under retries.
        if self._reindex_outbox is not None:
            self._reindex_outbox.enqueue_memory_upserted(
                project_id=memory.project_id,
                memory_id=memory.id,
                version=memory.version,
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
