"""Infrastructure-free Core SOT service skeleton.

The in-memory repository is deliberately small: it locks the application-level
contract before a MongoDB adapter exists. It preserves immutable snapshots,
idempotent draft saves, deterministic block/hash/ref generation, project
isolation, and archive behavior.
"""

from __future__ import annotations

from dataclasses import replace

from services.application.app.core_sot.models import (
    Draft,
    DraftVersion,
    Project,
    SaveDraftResult,
    SourceBlock,
    SourceRef,
    SourceSnapshot,
)
from services.application.app.core_sot.splitter import (
    content_hash,
    materialize_blocks,
    split_source_blocks,
)


class CoreSotError(ValueError):
    pass


class NotFound(CoreSotError):
    pass


class Archived(CoreSotError):
    pass


class InvalidSourceRef(CoreSotError):
    pass


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class InMemoryCoreSotRepository:
    """Deterministic repository used until the Mongo adapter slice exists."""

    def __init__(self) -> None:
        self._project_seq = 0
        self._draft_seq = 0
        self._version_seq = 0
        self._snapshot_seq = 0
        self.projects: dict[str, Project] = {}
        self.drafts: dict[str, Draft] = {}
        self.versions: dict[str, DraftVersion] = {}
        self.snapshots: dict[str, SourceSnapshot] = {}
        self.blocks_by_snapshot: dict[str, tuple[SourceBlock, ...]] = {}
        self._version_ids_by_draft: dict[str, list[str]] = {}
        self._save_request_index: dict[tuple[str, str, str], str] = {}

    def next_project_id(self) -> str:
        self._project_seq += 1
        return f"project-{self._project_seq}"

    def next_draft_id(self) -> str:
        self._draft_seq += 1
        return f"draft-{self._draft_seq}"

    def next_version_id(self) -> str:
        self._version_seq += 1
        return f"draft-version-{self._version_seq}"

    def next_snapshot_id(self) -> str:
        self._snapshot_seq += 1
        return f"source-snapshot-{self._snapshot_seq}"

    def version_count(self, draft_id: str) -> int:
        return len(self._version_ids_by_draft.get(draft_id, ()))

    def find_save_request(
        self, project_id: str, draft_id: str, idempotency_key: str
    ) -> str | None:
        return self._save_request_index.get((project_id, draft_id, idempotency_key))

    def record_save(
        self,
        *,
        idempotency_key: str,
        version: DraftVersion,
        snapshot: SourceSnapshot,
        blocks: tuple[SourceBlock, ...],
    ) -> None:
        self.versions[version.id] = version
        self.snapshots[snapshot.id] = snapshot
        self.blocks_by_snapshot[snapshot.id] = blocks
        self._version_ids_by_draft.setdefault(version.draft_id, []).append(version.id)
        self._save_request_index[
            (version.project_id, version.draft_id, idempotency_key)
        ] = version.id


class CoreSotService:
    def __init__(self, repository: InMemoryCoreSotRepository) -> None:
        self._repo = repository

    def create_project(self, *, name: str) -> Project:
        project = Project(id=self._repo.next_project_id(), name=name)
        self._repo.projects[project.id] = project
        return project

    def create_draft(self, *, project_id: str, title: str) -> Draft:
        project = self._require_project(project_id)
        if project.archived:
            raise Archived("project is archived")
        draft = Draft(
            id=self._repo.next_draft_id(),
            project_id=project_id,
            title=title,
        )
        self._repo.drafts[draft.id] = draft
        return draft

    def save_draft(
        self,
        *,
        project_id: str,
        draft_id: str,
        raw_text: str,
        idempotency_key: str,
    ) -> SaveDraftResult:
        if not idempotency_key:
            raise CoreSotError("idempotency_key is required")
        self._require_active_project_and_draft(project_id, draft_id)

        existing_version_id = self._repo.find_save_request(
            project_id, draft_id, idempotency_key
        )
        if existing_version_id is not None:
            return self._save_result(existing_version_id, idempotent_replay=True)

        version_id = self._repo.next_version_id()
        snapshot_id = self._repo.next_snapshot_id()
        version = DraftVersion(
            id=version_id,
            project_id=project_id,
            draft_id=draft_id,
            version_number=self._repo.version_count(draft_id) + 1,
            snapshot_id=snapshot_id,
            idempotency_key=idempotency_key,
        )
        snapshot = SourceSnapshot(
            id=snapshot_id,
            project_id=project_id,
            draft_id=draft_id,
            version_id=version_id,
            raw_text=raw_text,
            content_hash=content_hash(raw_text),
        )
        blocks = materialize_blocks(
            project_id=project_id,
            snapshot_id=snapshot_id,
            raw_blocks=split_source_blocks(raw_text),
        )
        self._repo.record_save(
            idempotency_key=idempotency_key,
            version=version,
            snapshot=snapshot,
            blocks=blocks,
        )
        return SaveDraftResult(
            draft_version=version,
            snapshot=snapshot,
            blocks=blocks,
            idempotent_replay=False,
        )

    def create_source_ref(
        self,
        *,
        project_id: str,
        snapshot_id: str,
        start_offset: int,
        end_offset: int,
    ) -> SourceRef:
        snapshot = self._repo.snapshots.get(snapshot_id)
        if snapshot is None or snapshot.project_id != project_id:
            raise NotFound("snapshot not found")
        if (
            not _is_int(start_offset)
            or not _is_int(end_offset)
            or start_offset < 0
            or end_offset <= start_offset
            or end_offset > len(snapshot.raw_text)
        ):
            raise InvalidSourceRef("invalid source_ref span")

        for block in self._repo.blocks_by_snapshot.get(snapshot_id, ()):
            if block.start_offset <= start_offset and end_offset <= block.end_offset:
                return SourceRef(
                    snapshot_id=snapshot_id,
                    block_id=block.id,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    quote=snapshot.raw_text[start_offset:end_offset],
                    content_hash=snapshot.content_hash,
                )
        raise InvalidSourceRef("source_ref span must fit within one source block")

    def archive_project(self, *, project_id: str) -> Project:
        project = self._require_project(project_id)
        archived = replace(project, archived=True)
        self._repo.projects[project_id] = archived
        return archived

    def archive_draft(self, *, project_id: str, draft_id: str) -> Draft:
        self._require_project(project_id)
        draft = self._require_draft(project_id, draft_id)
        archived = replace(draft, archived=True)
        self._repo.drafts[draft_id] = archived
        return archived

    def _save_result(self, version_id: str, *, idempotent_replay: bool) -> SaveDraftResult:
        version = self._repo.versions[version_id]
        snapshot = self._repo.snapshots[version.snapshot_id]
        blocks = self._repo.blocks_by_snapshot[version.snapshot_id]
        return SaveDraftResult(
            draft_version=version,
            snapshot=snapshot,
            blocks=blocks,
            idempotent_replay=idempotent_replay,
        )

    def _require_project(self, project_id: str) -> Project:
        project = self._repo.projects.get(project_id)
        if project is None:
            raise NotFound("project not found")
        return project

    def _require_draft(self, project_id: str, draft_id: str) -> Draft:
        draft = self._repo.drafts.get(draft_id)
        if draft is None or draft.project_id != project_id:
            raise NotFound("draft not found")
        return draft

    def _require_active_project_and_draft(self, project_id: str, draft_id: str) -> None:
        project = self._require_project(project_id)
        draft = self._require_draft(project_id, draft_id)
        if project.archived:
            raise Archived("project is archived")
        if draft.archived:
            raise Archived("draft is archived")
