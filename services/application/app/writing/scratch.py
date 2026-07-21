"""Recovery store for unaccepted Writing candidates.

Decision brief ``docs/plans/unaccepted-candidate-persistence-decisions.md``
(D0=B / D1=B / D2=A, 2026-07-20). A generated candidate lives only in memory
until ``accept`` mints a ``draft_version``; refreshing or navigating away
loses it. This store is the pre-dogfood safety net: every ``generate`` appends
the candidate to a **Core-SOT-external** ``writing_drafts_scratch`` collection
keyed by ``(project_id, draft_id)``, so the editor can offer to recover the
draft. It is explicitly NOT the canonical (version/snapshot) store.

D1=B keeps a short **history** per draft (not just the last one), so the per
-draft entries are capped (``MAX_SCRATCH_PER_DRAFT``) to bound growth. On
``accept`` success only the **accepted item** (matching ``request_id``) is
cleared — other generated candidates stay recoverable (async-pad D2=A, SoT
v1.7.25). The retention policy (cap value, per-item accept-clear, no time-based
expiry) is ratified into the SoT (v1.7.20 → v1.7.25).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Protocol
from uuid import uuid4

# Default per-draft history cap, overridable via WRITING_SCRATCH_MAX_PER_DRAFT
# (owner: "how many drafts are worth keeping differs per person" — the value is
# still provisional pending SoT ratification, so it is tunable without a code
# change). Bounds the unbounded append growth that D1=B (history) allows.
MAX_SCRATCH_PER_DRAFT = 20


@dataclass(frozen=True, slots=True)
class ScratchCandidate:
    id: str
    project_id: str
    draft_id: str
    request_id: str
    task_type: str
    output_type: str
    instruction: str
    candidate_text: str
    created_at: datetime
    # Phase 7 absorption seam: intent is only known at accept, so generate-time
    # saves leave it None. Kept nullable so a later conversation_turn can carry
    # it without a schema change (brief Follow-up considerations).
    intent: str | None = None
    # Async pad seam (async-generation-pad D7): the version the candidate was
    # generated against, so the pad can show "이 version 기준으로 생성됨".
    # Additive + nullable like ``intent`` — pre-pad records read as None.
    version_id: str | None = None


class WritingScratchRepository(Protocol):
    def add(self, entry: ScratchCandidate) -> None: ...
    def list_for_draft(
        self, project_id: str, draft_id: str
    ) -> tuple[ScratchCandidate, ...]: ...
    def delete_for_draft(self, project_id: str, draft_id: str) -> int: ...
    def delete_for_request(
        self, project_id: str, draft_id: str, request_id: str
    ) -> int: ...
    def delete_ids(self, ids: tuple[str, ...]) -> None: ...


class InMemoryWritingScratchRepository:
    def __init__(self) -> None:
        self.entries: dict[str, ScratchCandidate] = {}

    def add(self, entry: ScratchCandidate) -> None:
        self.entries[entry.id] = entry

    def list_for_draft(
        self, project_id: str, draft_id: str
    ) -> tuple[ScratchCandidate, ...]:
        return tuple(sorted(
            (e for e in self.entries.values()
             if e.project_id == project_id and e.draft_id == draft_id),
            key=lambda e: (e.created_at, e.id),
            reverse=True,
        ))

    def delete_for_draft(self, project_id: str, draft_id: str) -> int:
        victims = [
            e.id for e in self.entries.values()
            if e.project_id == project_id and e.draft_id == draft_id
        ]
        for entry_id in victims:
            del self.entries[entry_id]
        return len(victims)

    def delete_for_request(
        self, project_id: str, draft_id: str, request_id: str
    ) -> int:
        victims = [
            e.id for e in self.entries.values()
            if e.project_id == project_id and e.draft_id == draft_id
            and e.request_id == request_id
        ]
        for entry_id in victims:
            del self.entries[entry_id]
        return len(victims)

    def delete_ids(self, ids: tuple[str, ...]) -> None:
        for entry_id in ids:
            self.entries.pop(entry_id, None)


class WritingScratchService:
    def __init__(
        self, repository: WritingScratchRepository, *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
        max_per_draft: int = MAX_SCRATCH_PER_DRAFT,
    ) -> None:
        # A cap below 1 would make every save trim itself away (or, negative,
        # trim nonsensically) — a misconfigured safety net that silently discards
        # exactly what it exists to protect. Fail loudly at construction instead.
        if max_per_draft < 1:
            raise ValueError(
                f"max_per_draft must be >= 1, got {max_per_draft} "
                "(when configured from the environment, this is "
                "WRITING_SCRATCH_MAX_PER_DRAFT)"
            )
        self._repo = repository
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: "wds:" + uuid4().hex)
        self._max_per_draft = max_per_draft

    def save(
        self, *, project_id: str, draft_id: str, request_id: str,
        task_type: str, output_type: str, instruction: str,
        candidate_text: str, intent: str | None = None,
        version_id: str | None = None,
    ) -> ScratchCandidate:
        entry = ScratchCandidate(
            id=self._id_factory(),
            project_id=project_id,
            draft_id=draft_id,
            request_id=request_id,
            task_type=task_type,
            output_type=output_type,
            instruction=instruction,
            candidate_text=candidate_text,
            created_at=self._clock(),
            intent=intent,
            version_id=version_id,
        )
        self._repo.add(entry)
        self._trim(project_id, draft_id)
        return entry

    def list_for_draft(
        self, project_id: str, draft_id: str
    ) -> tuple[ScratchCandidate, ...]:
        return self._repo.list_for_draft(project_id, draft_id)

    def clear_draft(self, project_id: str, draft_id: str) -> int:
        return self._repo.delete_for_draft(project_id, draft_id)

    def clear_accepted_item(
        self, project_id: str, draft_id: str, request_id: str
    ) -> int:
        # Async-pad D2=A: an accept only retires the *accepted* candidate, not
        # the draft's whole scratch history. Other generated candidates stay
        # recoverable (they remain valuable to copy — the pad's reason to exist).
        # No matching entry → no-op (returns 0).
        return self._repo.delete_for_request(project_id, draft_id, request_id)

    def _trim(self, project_id: str, draft_id: str) -> None:
        # Keep only the newest ``max_per_draft`` entries; drop the oldest excess.
        entries = self._repo.list_for_draft(project_id, draft_id)
        if len(entries) <= self._max_per_draft:
            return
        stale = tuple(e.id for e in entries[self._max_per_draft:])
        self._repo.delete_ids(stale)
