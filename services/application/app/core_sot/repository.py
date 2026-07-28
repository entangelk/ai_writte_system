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
    ProjectBriefVersion,
    SourceBlock,
    SourceRef,
    SourceSnapshot,
    WritingAcceptReceipt,
)


class DuplicateWritingAcceptReceipt(Exception):
    """Raised when a ``start_next_unit`` accept loses a receipt-key race.

    The committed receipt already exists for the same
    ``(project_id, idempotency_key)``. Callers resolve it as an idempotent
    replay of the original unit.
    """


class DuplicateSaveRequest(Exception):
    """Raised when ``record_save`` loses an idempotency-key race.

    The committed ``draft_version`` already exists for the same
    ``(project_id, draft_id, idempotency_key)``. Callers resolve it by
    re-reading the existing version and returning an idempotent replay.
    """


class DuplicateProjectBriefRequest(Exception):
    """Raised when a ProjectBrief version loses a unique-index race."""


class DraftSetChanged(Exception):
    """Raised when an ordered-unit write no longer targets the full draft set."""


class CoreSotRepository(Protocol):
    """Storage operations the Core SOT service requires."""

    def next_project_id(self) -> str: ...

    def next_project_brief_version_id(self) -> str: ...

    def next_draft_id(self) -> str: ...

    def next_version_id(self) -> str: ...

    def next_snapshot_id(self) -> str: ...

    def next_source_ref_id(self) -> str: ...

    def get_project(self, project_id: str) -> Project | None: ...

    def put_project(self, project: Project) -> None: ...

    def list_projects(self) -> tuple[Project, ...]: ...

    def list_projects_for_owner(self, owner_id: str) -> tuple[Project, ...]: ...

    def get_current_project_brief(
        self, project_id: str
    ) -> ProjectBriefVersion | None: ...

    def get_project_brief_version(
        self, version_id: str
    ) -> ProjectBriefVersion | None: ...

    def list_project_brief_versions(
        self, project_id: str
    ) -> tuple[ProjectBriefVersion, ...]: ...

    def find_project_brief_request(
        self, project_id: str, idempotency_key: str
    ) -> str | None: ...

    def record_project_brief(self, brief: ProjectBriefVersion) -> None: ...

    def get_draft(self, draft_id: str) -> Draft | None: ...

    def put_draft(self, draft: Draft) -> None: ...

    def list_drafts(self, project_id: str) -> tuple[Draft, ...]: ...

    def replace_draft_metadata(
        self, project_id: str, drafts: tuple[Draft, ...]
    ) -> None: ...

    def ensure_draft_position_index(self) -> None: ...

    def version_count(self, draft_id: str) -> int: ...

    def list_versions(self, draft_id: str) -> tuple[DraftVersion, ...]: ...

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

    def record_start_next_unit(
        self,
        *,
        shifted_drafts: tuple[Draft, ...],
        new_draft: Draft,
        idempotency_key: str,
        version: DraftVersion,
        snapshot: SourceSnapshot,
        blocks: tuple[SourceBlock, ...],
        receipt: WritingAcceptReceipt,
    ) -> None: ...

    def get_writing_accept_receipt(
        self, project_id: str, idempotency_key: str
    ) -> WritingAcceptReceipt | None: ...

    def get_version(self, version_id: str) -> DraftVersion | None: ...

    def get_snapshot(self, snapshot_id: str) -> SourceSnapshot | None: ...

    def get_blocks(self, snapshot_id: str) -> tuple[SourceBlock, ...]: ...

    def record_source_ref(self, source_ref: SourceRef) -> None: ...

    def get_source_ref(self, source_ref_id: str) -> SourceRef | None: ...

    def list_source_refs(
        self, *, project_id: str, snapshot_id: str
    ) -> tuple[SourceRef, ...]: ...
