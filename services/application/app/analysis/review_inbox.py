"""Read-only Phase 6 review inbox over candidates and open conflicts."""

from dataclasses import dataclass
from typing import Any, Mapping

from services.application.app.analysis.models import (
    AnalysisCandidate, AnalysisCandidateType,
)
from services.application.app.analysis.review_queue import (
    ReviewQueueEntry, ReviewQueueService,
)
from services.application.app.analysis.service import AnalysisService
from services.application.app.memory.models import MemoryEntry
from services.application.app.memory.service import MemoryNotFound, MemoryService


@dataclass(frozen=True, slots=True)
class FieldDiff:
    field: str
    before: Any
    after: Any


@dataclass(frozen=True, slots=True)
class ConflictDetail:
    entry: ReviewQueueEntry
    matched_memory: MemoryEntry | None
    diff: tuple[FieldDiff, ...]


@dataclass(frozen=True, slots=True)
class ReviewInboxItem:
    candidate: AnalysisCandidate
    conflicts: tuple[ConflictDetail, ...]


class ReviewInboxNotFound(LookupError):
    pass


class ReviewInboxService:
    def __init__(self, *, analysis_service: AnalysisService,
                 memory_service: MemoryService,
                 review_queue: ReviewQueueService) -> None:
        self._analysis = analysis_service
        self._memory = memory_service
        self._queue = review_queue

    def list_items(self, *, project_id: str) -> tuple[ReviewInboxItem, ...]:
        candidates = self._analysis.list_needs_review_candidates(
            project_id=project_id
        )
        candidates = tuple(
            candidate for candidate in candidates
            if not self._memory.is_candidate_promoted(project_id, candidate.id)
        )
        open_by_candidate: dict[str, list[ReviewQueueEntry]] = {}
        for entry in self._queue.list_open(project_id):
            open_by_candidate.setdefault(entry.candidate_id, []).append(entry)
        return tuple(
            self._item(project_id, candidate, open_by_candidate.get(candidate.id, []))
            for candidate in candidates
        )

    def get_item(self, *, project_id: str, candidate_id: str) -> ReviewInboxItem:
        for item in self.list_items(project_id=project_id):
            if item.candidate.id == candidate_id:
                return item
        raise ReviewInboxNotFound("review inbox candidate not found")

    def _item(self, project_id: str, candidate: AnalysisCandidate,
              entries: list[ReviewQueueEntry]) -> ReviewInboxItem:
        conflicts = tuple(
            self._conflict(project_id, candidate.payload, entry)
            for entry in sorted(entries, key=lambda value: value.id)
        )
        return ReviewInboxItem(candidate=candidate, conflicts=conflicts)

    def _conflict(self, project_id: str, candidate_payload: Mapping[str, Any],
                  entry: ReviewQueueEntry) -> ConflictDetail:
        memory = None
        if entry.matched_memory_id is not None:
            try:
                memory = self._memory.get_memory(
                    project_id=project_id, memory_id=entry.matched_memory_id
                )
            except MemoryNotFound:
                memory = None
        diff = _payload_diff(memory.payload, candidate_payload) if memory else ()
        return ConflictDetail(entry=entry, matched_memory=memory, diff=diff)


def _payload_diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> tuple[FieldDiff, ...]:
    return tuple(
        FieldDiff(field=field, before=before.get(field), after=after.get(field))
        for field in sorted(set(before) | set(after))
        if before.get(field) != after.get(field)
    )


@dataclass(frozen=True, slots=True)
class ActionAffordance:
    """Declares whether a review action is available on an inbox item, and when
    not, why (v1.6.67) — so a frontend can render disabled controls with a
    tooltip. Eligibility is recomputed at read time from item state; the write
    endpoints remain the authority (an eligible=True affordance does not skip the
    write's own validation). See docs/plans/06-review-inbox-affordances-decisions.md."""

    action: str
    eligible: bool
    reason: str | None = None


_CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION


def candidate_affordances() -> tuple[ActionAffordance, ...]:
    """The inbox only surfaces needs_review, non-promoted candidates, so all
    three candidate review actions are always available (v1.6.61/66)."""
    return (
        ActionAffordance("confirm", True),
        ActionAffordance("reject", True),
        ActionAffordance("edit", True),
    )


def conflict_affordances(conflict: ConflictDetail) -> tuple[ActionAffordance, ...]:
    """merge/split reconciliation is character-only; merge additionally needs a
    resolvable matched canonical (``reconciliation.py`` reconcile guard)."""
    is_character = conflict.entry.candidate_type is _CHARACTER
    has_matched = conflict.matched_memory is not None
    if not is_character:
        merge_reason = split_reason = "merge/split is character-only"
    else:
        split_reason = None
        merge_reason = (
            None if has_matched
            else "merge requires a matched canonical memory"
        )
    return (
        ActionAffordance("merge", is_character and has_matched, merge_reason),
        ActionAffordance("split", is_character, split_reason),
    )


def gate_finding_affordances(*, is_open: bool) -> tuple[ActionAffordance, ...]:
    """A gate finding can be resolved/dismissed only while open (v1.6.65)."""
    reason = None if is_open else "gate finding is already terminal"
    return (
        ActionAffordance("resolve", is_open, reason),
        ActionAffordance("dismiss", is_open, reason),
    )
