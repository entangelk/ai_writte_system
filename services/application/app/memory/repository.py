"""Repository boundary for the Phase 2B.1 canonical memory store."""

from __future__ import annotations

from typing import Protocol

from services.application.app.memory.models import MemoryEntry


class DuplicatePromotionRequest(RuntimeError):
    """Raised when a candidate has already been promoted to a MemoryEntry.

    Defined at the repository boundary so storage-agnostic callers (service)
    can map a unique-index race without depending on a concrete adapter.
    """


class MemoryRepository(Protocol):
    def next_memory_id(self) -> str: ...

    def get_memory(self, memory_id: str) -> MemoryEntry | None: ...

    def find_memory_by_candidate(
        self, project_id: str, source_candidate_id: str
    ) -> str | None: ...

    def put_memory(self, entry: MemoryEntry) -> None: ...

    def update_memory(self, entry: MemoryEntry) -> None: ...

    def list_memories_for_project(
        self, project_id: str
    ) -> tuple[MemoryEntry, ...]: ...

    def purge_project(self, project_id: str) -> None: ...
