"""Phase 2B.4 follow-up: durable review queue for review-only compare actions.

2B.3 compare emits ``conflict`` ``ActionProposal``s (merge/split are not emitted
yet); 2B.4 apply classifies them as review-only (D7 — never an automatic write).
Without a durable store that classification is lost after the apply response, so
an unresolved conflict cannot be reconciled later.

This module persists each review-only proposal as a ``ReviewQueueEntry`` so
Phase 6 (review UI) and 2B.4 merge/split reconciliation can consume it. Scope is
deliberately minimal (kickoff brief
``docs/plans/02b-4-review-queue-persistence-decisions.md``):

* ``status`` is a single ``open`` value — resolve/dismiss/reconcile transitions
  belong to the Phase 6 review state machine (forward-defense, mirroring the
  candidate ``needs_review``-only store), not this slice.
* the entry id is derived deterministically from
  ``(project_id, job_id, candidate_id, action)`` so re-applying the same job
  (apply is idempotent) upserts rather than duplicates (D3).
* ``action`` is stored as a ``CompareAction`` so a future ``merge``/``split``
  flows through the same queue without a schema change (D4).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol

from services.application.app.analysis.compare import CompareAction
from services.application.app.analysis.models import AnalysisCandidateType


class ReviewQueueStatus(StrEnum):
    OPEN = "open"
    # Phase 6 (v1.6.61): a candidate transition closes its open conflict entries.
    # confirm → resolved (the conflict was decided in favor of the candidate),
    # reject → dismissed (the candidate and its conflict are set aside).
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


@dataclass(frozen=True, slots=True)
class ReviewQueueEntry:
    id: str
    project_id: str
    job_id: str
    candidate_id: str
    candidate_type: AnalysisCandidateType
    action: CompareAction
    matched_memory_id: str | None
    rationale: str
    status: ReviewQueueStatus
    resolution_action: str | None = None
    resolution_memory_id: str | None = None


def derive_review_queue_id(
    *, project_id: str, job_id: str, candidate_id: str, action: CompareAction
) -> str:
    """Deterministic id so an apply replay upserts the same entry (D3).

    Mirrors the 2A ``logical_key`` canonical-JSON SHA-256 convention.
    """
    canonical = {
        "project_id": project_id,
        "job_id": job_id,
        "candidate_id": candidate_id,
        "action": action.value,
    }
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return f"rq:{hashlib.sha256(encoded).hexdigest()}"


class ReviewQueueRepository(Protocol):
    def upsert_entry(self, entry: ReviewQueueEntry) -> None: ...

    def list_open_for_project(
        self, project_id: str
    ) -> tuple[ReviewQueueEntry, ...]: ...

    def list_open_for_candidate(
        self, project_id: str, candidate_id: str
    ) -> tuple[ReviewQueueEntry, ...]: ...

    def get_entry(self, entry_id: str) -> ReviewQueueEntry | None: ...


class InMemoryReviewQueueRepository:
    """Non-durable ``ReviewQueueRepository`` for tests / the no-Mongo path."""

    def __init__(self) -> None:
        self._entries: dict[str, ReviewQueueEntry] = {}

    def upsert_entry(self, entry: ReviewQueueEntry) -> None:
        self._entries[entry.id] = entry

    def list_open_for_project(
        self, project_id: str
    ) -> tuple[ReviewQueueEntry, ...]:
        return tuple(
            entry
            for entry in self._entries.values()
            if entry.project_id == project_id
            and entry.status is ReviewQueueStatus.OPEN
        )

    def list_open_for_candidate(
        self, project_id: str, candidate_id: str
    ) -> tuple[ReviewQueueEntry, ...]:
        return tuple(
            entry
            for entry in self._entries.values()
            if entry.project_id == project_id
            and entry.candidate_id == candidate_id
            and entry.status is ReviewQueueStatus.OPEN
        )

    def get_entry(self, entry_id: str) -> ReviewQueueEntry | None:
        return self._entries.get(entry_id)


class ReviewQueueService:
    def __init__(self, repository: ReviewQueueRepository) -> None:
        self._repository = repository

    def enqueue(
        self,
        *,
        project_id: str,
        job_id: str,
        candidate_id: str,
        candidate_type: AnalysisCandidateType,
        action: CompareAction,
        matched_memory_id: str | None,
        rationale: str,
    ) -> ReviewQueueEntry:
        """Persist a review-only proposal. Idempotent on the deterministic id."""
        entry = ReviewQueueEntry(
            id=derive_review_queue_id(
                project_id=project_id,
                job_id=job_id,
                candidate_id=candidate_id,
                action=action,
            ),
            project_id=project_id,
            job_id=job_id,
            candidate_id=candidate_id,
            candidate_type=candidate_type,
            action=action,
            matched_memory_id=matched_memory_id,
            rationale=rationale,
            status=ReviewQueueStatus.OPEN,
        )
        self._repository.upsert_entry(entry)
        return entry

    def list_open(self, project_id: str) -> tuple[ReviewQueueEntry, ...]:
        return self._repository.list_open_for_project(project_id)

    def get(self, *, project_id: str, entry_id: str) -> ReviewQueueEntry:
        entry = self._repository.get_entry(entry_id)
        if entry is None or entry.project_id != project_id:
            raise KeyError("review queue entry not found")
        return entry

    def mark_resolved(
        self, entry: ReviewQueueEntry, *, action: str | None = None,
        memory_id: str | None = None
    ) -> ReviewQueueEntry:
        if entry.status is ReviewQueueStatus.RESOLVED:
            return entry
        if entry.status is not ReviewQueueStatus.OPEN:
            raise ValueError("review queue entry is not open")
        resolved = replace(
            entry, status=ReviewQueueStatus.RESOLVED,
            resolution_action=action, resolution_memory_id=memory_id,
        )
        self._repository.upsert_entry(resolved)
        return resolved

    def resolve_for_candidate(
        self, *, project_id: str, candidate_id: str
    ) -> tuple[ReviewQueueEntry, ...]:
        """Close a candidate's open conflict entries as RESOLVED (confirm path).

        Idempotent: a replay finds no open entries and is a no-op."""
        return self._transition_candidate_entries(
            project_id=project_id,
            candidate_id=candidate_id,
            target=ReviewQueueStatus.RESOLVED,
        )

    def dismiss_for_candidate(
        self, *, project_id: str, candidate_id: str
    ) -> tuple[ReviewQueueEntry, ...]:
        """Close a candidate's open conflict entries as DISMISSED (reject path).

        Idempotent: a replay finds no open entries and is a no-op."""
        return self._transition_candidate_entries(
            project_id=project_id,
            candidate_id=candidate_id,
            target=ReviewQueueStatus.DISMISSED,
        )

    def _transition_candidate_entries(
        self,
        *,
        project_id: str,
        candidate_id: str,
        target: ReviewQueueStatus,
    ) -> tuple[ReviewQueueEntry, ...]:
        transitioned: list[ReviewQueueEntry] = []
        for entry in self._repository.list_open_for_candidate(
            project_id, candidate_id
        ):
            closed = replace(entry, status=target)
            self._repository.upsert_entry(closed)
            transitioned.append(closed)
        return tuple(transitioned)
