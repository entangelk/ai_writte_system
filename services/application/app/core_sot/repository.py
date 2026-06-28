"""Repository contract shared by the in-memory and MongoDB adapters.

The service depends only on this interface so the storage backend can be
swapped without touching domain logic. The contract intentionally exposes
narrow, method-based access (no raw collection / dict handles) so the Mongo
adapter can enforce project isolation, transactional save, and idempotency.
"""

from __future__ import annotations

from typing import Protocol

from services.application.app.core_sot.models import (
    Draft,
    DraftVersion,
    Project,
    SourceBlock,
    SourceSnapshot,
)


class DuplicateSaveRequest(Exception):
    """Raised when ``record_save`` loses an idempotency-key race.

    The committed ``draft_version`` already exists for the same
    ``(project_id, draft_id, idempotency_key)``. Callers resolve it by
    re-reading the existing version and returning an idempotent replay.
    """


class CoreSotRepository(Protocol):
    """Storage operations the Core SOT service requires."""

    def next_project_id(self) -> str: ...

    def next_draft_id(self) -> str: ...

    def next_version_id(self) -> str: ...

    def next_snapshot_id(self) -> str: ...

    def get_project(self, project_id: str) -> Project | None: ...

    def put_project(self, project: Project) -> None: ...

    def get_draft(self, draft_id: str) -> Draft | None: ...

    def put_draft(self, draft: Draft) -> None: ...

    def version_count(self, draft_id: str) -> int: ...

    def find_save_request(
        self, project_id: str, draft_id: str, idempotency_key: str
    ) -> str | None: ...

    def record_save(
        self,
        *,
        idempotency_key: str,
        version: DraftVersion,
        snapshot: SourceSnapshot,
        blocks: tuple[SourceBlock, ...],
    ) -> None: ...

    def get_version(self, version_id: str) -> DraftVersion | None: ...

    def get_snapshot(self, snapshot_id: str) -> SourceSnapshot | None: ...

    def get_blocks(self, snapshot_id: str) -> tuple[SourceBlock, ...]: ...
