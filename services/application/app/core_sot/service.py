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
    DraftVersionDetail,
    DraftVersionExport,
    Project,
    ProjectBriefVersion,
    PutProjectBriefResult,
    SaveDraftResult,
    SourceBlock,
    SourceRef,
    SourceSnapshot,
    SourceSnapshotDetail,
    UnitKind,
)
from services.application.app.core_sot.repository import (
    CoreSotRepository,
    DraftSetChanged,
    DuplicateProjectBriefRequest,
    DuplicateSaveRequest,
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


class UnsupportedExportFormat(CoreSotError):
    pass


class StaleProjectBriefBase(CoreSotError):
    pass


class InvalidDraftOrder(CoreSotError):
    pass


_EXPORT_FORMATS: dict[str, tuple[str, str]] = {
    # format -> (content_type, filename extension)
    "txt": ("text/plain; charset=utf-8", "txt"),
    "markdown": ("text/markdown; charset=utf-8", "md"),
}


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class InMemoryCoreSotRepository:
    """Deterministic repository used until the Mongo adapter slice exists."""

    def __init__(self) -> None:
        self._project_seq = 0
        self._project_brief_version_seq = 0
        self._draft_seq = 0
        self._version_seq = 0
        self._snapshot_seq = 0
        self._source_ref_seq = 0
        self.projects: dict[str, Project] = {}
        self.project_brief_versions: dict[str, ProjectBriefVersion] = {}
        self._project_brief_ids_by_project: dict[str, list[str]] = {}
        self._project_brief_request_index: dict[tuple[str, str], str] = {}
        self.drafts: dict[str, Draft] = {}
        self.versions: dict[str, DraftVersion] = {}
        self.snapshots: dict[str, SourceSnapshot] = {}
        self.blocks_by_snapshot: dict[str, tuple[SourceBlock, ...]] = {}
        self.source_refs: dict[str, SourceRef] = {}
        self._version_ids_by_draft: dict[str, list[str]] = {}
        self._save_request_index: dict[tuple[str, str, str], str] = {}

    def next_project_id(self) -> str:
        self._project_seq += 1
        return f"project-{self._project_seq}"

    def next_project_brief_version_id(self) -> str:
        self._project_brief_version_seq += 1
        return f"project-brief-version-{self._project_brief_version_seq}"

    def next_draft_id(self) -> str:
        self._draft_seq += 1
        return f"draft-{self._draft_seq}"

    def next_version_id(self) -> str:
        self._version_seq += 1
        return f"draft-version-{self._version_seq}"

    def next_snapshot_id(self) -> str:
        self._snapshot_seq += 1
        return f"source-snapshot-{self._snapshot_seq}"

    def next_source_ref_id(self) -> str:
        self._source_ref_seq += 1
        return f"source-ref-{self._source_ref_seq}"

    def version_count(self, draft_id: str) -> int:
        return len(self._version_ids_by_draft.get(draft_id, ()))

    def list_versions(self, draft_id: str) -> tuple[DraftVersion, ...]:
        return tuple(
            self.versions[vid]
            for vid in self._version_ids_by_draft.get(draft_id, ())
        )

    def get_project(self, project_id: str) -> Project | None:
        return self.projects.get(project_id)

    def put_project(self, project: Project) -> None:
        self.projects[project.id] = project

    def list_projects(self) -> tuple[Project, ...]:
        return tuple(self.projects.values())

    def get_current_project_brief(
        self, project_id: str
    ) -> ProjectBriefVersion | None:
        ids = self._project_brief_ids_by_project.get(project_id, ())
        return self.project_brief_versions[ids[-1]] if ids else None

    def get_project_brief_version(
        self, version_id: str
    ) -> ProjectBriefVersion | None:
        return self.project_brief_versions.get(version_id)

    def list_project_brief_versions(
        self, project_id: str
    ) -> tuple[ProjectBriefVersion, ...]:
        return tuple(
            self.project_brief_versions[version_id]
            for version_id in self._project_brief_ids_by_project.get(project_id, ())
        )

    def find_project_brief_request(
        self, project_id: str, idempotency_key: str
    ) -> str | None:
        return self._project_brief_request_index.get((project_id, idempotency_key))

    def record_project_brief(self, brief: ProjectBriefVersion) -> None:
        self.project_brief_versions[brief.id] = brief
        self._project_brief_ids_by_project.setdefault(brief.project_id, []).append(
            brief.id
        )
        self._project_brief_request_index[
            (brief.project_id, brief.idempotency_key)
        ] = brief.id

    def get_draft(self, draft_id: str) -> Draft | None:
        return self.drafts.get(draft_id)

    def put_draft(self, draft: Draft) -> None:
        self.drafts[draft.id] = draft

    def list_drafts(self, project_id: str) -> tuple[Draft, ...]:
        drafts = tuple(
            draft for draft in self.drafts.values() if draft.project_id == project_id
        )
        if drafts and all(draft.position is not None for draft in drafts):
            return tuple(sorted(drafts, key=lambda draft: draft.position))
        return drafts

    def replace_draft_metadata(
        self, project_id: str, drafts: tuple[Draft, ...]
    ) -> None:
        before = {
            draft.id: self.drafts[draft.id]
            for draft in drafts
            if draft.id in self.drafts
        }
        try:
            for draft in drafts:
                if draft.project_id != project_id or draft.id not in self.drafts:
                    raise DraftSetChanged("draft set changed during write")
                self.drafts[draft.id] = draft
                self._after_draft_metadata_write(draft)
        except Exception:
            self.drafts.update(before)
            raise

    def _after_draft_metadata_write(self, draft: Draft) -> None:
        """Failure-injection seam for ordered-unit fallback regressions."""

    def ensure_draft_position_index(self) -> None:
        # Dict-backed tests enforce uniqueness in service validation.
        return None

    def get_version(self, version_id: str) -> DraftVersion | None:
        return self.versions.get(version_id)

    def get_snapshot(self, snapshot_id: str) -> SourceSnapshot | None:
        return self.snapshots.get(snapshot_id)

    def get_blocks(self, snapshot_id: str) -> tuple[SourceBlock, ...]:
        return self.blocks_by_snapshot.get(snapshot_id, ())

    def record_source_ref(self, source_ref: SourceRef) -> None:
        self.source_refs[source_ref.id] = source_ref

    def get_source_ref(self, source_ref_id: str) -> SourceRef | None:
        return self.source_refs.get(source_ref_id)

    def list_source_refs(
        self, *, project_id: str, snapshot_id: str
    ) -> tuple[SourceRef, ...]:
        refs = (
            source_ref
            for source_ref in self.source_refs.values()
            if source_ref.project_id == project_id
            and source_ref.snapshot_id == snapshot_id
        )
        return tuple(
            sorted(
                refs,
                key=lambda source_ref: (
                    source_ref.start_offset,
                    source_ref.end_offset,
                    source_ref.id,
                ),
            )
        )

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
    def __init__(self, repository: CoreSotRepository) -> None:
        self._repo = repository

    def create_project(self, *, name: str) -> Project:
        project = Project(id=self._repo.next_project_id(), name=name)
        self._repo.put_project(project)
        return project

    def create_draft(
        self,
        *,
        project_id: str,
        title: str,
        unit_kind: UnitKind = UnitKind.OTHER,
    ) -> Draft:
        project = self._require_project(project_id)
        if project.archived:
            raise Archived("project is archived")
        if not isinstance(unit_kind, UnitKind):
            raise InvalidDraftOrder("draft unit_kind is invalid")
        drafts = self._repo.list_drafts(project_id)
        self._require_ordered_drafts(drafts)
        draft = Draft(
            id=self._repo.next_draft_id(),
            project_id=project_id,
            title=title,
            unit_kind=unit_kind,
            position=len(drafts) + 1,
        )
        self._repo.put_draft(draft)
        return draft

    def rename_project(self, *, project_id: str, name: str) -> Project:
        project = self._require_project(project_id)
        if project.archived:
            raise Archived("project is archived")
        renamed = replace(project, name=name)
        self._repo.put_project(renamed)
        return renamed

    def rename_draft(self, *, project_id: str, draft_id: str, title: str) -> Draft:
        project = self._require_project(project_id)
        if project.archived:
            raise Archived("project is archived")
        draft = self._require_draft(project_id, draft_id)
        if draft.archived:
            raise Archived("draft is archived")
        renamed = replace(draft, title=title)
        self._repo.put_draft(renamed)
        return renamed

    def get_project(self, *, project_id: str) -> Project:
        return self._require_project(project_id)

    def list_projects(self) -> tuple[Project, ...]:
        return self._repo.list_projects()

    def get_project_brief(self, *, project_id: str) -> ProjectBriefVersion | None:
        self._require_project(project_id)
        return self._repo.get_current_project_brief(project_id)

    def get_project_brief_version(
        self, *, project_id: str, version_id: str
    ) -> ProjectBriefVersion:
        self._require_project(project_id)
        brief = self._repo.get_project_brief_version(version_id)
        if brief is None or brief.project_id != project_id:
            raise NotFound("project brief version not found")
        return brief

    def list_project_brief_versions(
        self, *, project_id: str
    ) -> tuple[ProjectBriefVersion, ...]:
        self._require_project(project_id)
        return self._repo.list_project_brief_versions(project_id)

    def put_project_brief(
        self,
        *,
        project_id: str,
        base_version_id: str | None,
        idempotency_key: str,
        premise: str | None,
        genre: str | None,
        tone: str | None,
        pov: str | None,
        constraints: tuple[str, ...],
    ) -> PutProjectBriefResult:
        if not idempotency_key:
            raise CoreSotError("idempotency_key is required")
        project = self._require_project(project_id)
        if project.archived:
            raise Archived("project is archived")

        replay_id = self._repo.find_project_brief_request(
            project_id, idempotency_key
        )
        if replay_id is not None:
            replay = self._repo.get_project_brief_version(replay_id)
            assert replay is not None
            return PutProjectBriefResult(brief=replay, idempotent_replay=True)

        current = self._repo.get_current_project_brief(project_id)
        expected_base = current.id if current is not None else None
        if base_version_id != expected_base:
            raise StaleProjectBriefBase("project brief base is stale")

        brief = ProjectBriefVersion(
            id=self._repo.next_project_brief_version_id(),
            project_id=project_id,
            version_number=(current.version_number + 1 if current else 1),
            premise=premise,
            genre=genre,
            tone=tone,
            pov=pov,
            constraints=constraints,
            idempotency_key=idempotency_key,
        )
        try:
            self._repo.record_project_brief(brief)
        except DuplicateProjectBriefRequest:
            replay_id = self._repo.find_project_brief_request(
                project_id, idempotency_key
            )
            if replay_id is None:
                raise StaleProjectBriefBase("project brief base is stale")
            replay = self._repo.get_project_brief_version(replay_id)
            assert replay is not None
            return PutProjectBriefResult(brief=replay, idempotent_replay=True)
        return PutProjectBriefResult(brief=brief, idempotent_replay=False)

    def get_draft(self, *, project_id: str, draft_id: str) -> Draft:
        self._require_project(project_id)
        return self._require_draft(project_id, draft_id)

    def list_drafts(self, *, project_id: str) -> tuple[Draft, ...]:
        self._require_project(project_id)
        drafts = self._repo.list_drafts(project_id)
        self._require_ordered_drafts(drafts)
        return drafts

    def reorder_drafts(
        self, *, project_id: str, ordered_draft_ids: tuple[str, ...]
    ) -> tuple[Draft, ...]:
        project = self._require_project(project_id)
        if project.archived:
            raise Archived("project is archived")
        current = self._repo.list_drafts(project_id)
        self._require_ordered_drafts(current)
        current_ids = tuple(draft.id for draft in current)
        if (
            len(ordered_draft_ids) != len(current_ids)
            or len(set(ordered_draft_ids)) != len(ordered_draft_ids)
            or set(ordered_draft_ids) != set(current_ids)
        ):
            raise InvalidDraftOrder("ordered_draft_ids must be the complete draft set")
        if ordered_draft_ids == current_ids:
            return current
        by_id = {draft.id: draft for draft in current}
        reordered = tuple(
            replace(by_id[draft_id], position=index)
            for index, draft_id in enumerate(ordered_draft_ids, start=1)
        )
        try:
            self._repo.replace_draft_metadata(project_id, reordered)
        except DraftSetChanged as exc:
            raise InvalidDraftOrder("draft set changed during reorder") from exc
        committed = self._repo.list_drafts(project_id)
        if tuple(draft.id for draft in committed) != ordered_draft_ids:
            raise InvalidDraftOrder("draft set changed during reorder")
        return committed

    def list_draft_versions(
        self, *, project_id: str, draft_id: str
    ) -> tuple[DraftVersion, ...]:
        self._require_project(project_id)
        self._require_draft(project_id, draft_id)
        return self._repo.list_versions(draft_id)

    def get_draft_version(
        self, *, project_id: str, draft_id: str, version_id: str
    ) -> DraftVersionDetail:
        self._require_project(project_id)
        self._require_draft(project_id, draft_id)
        version = self._repo.get_version(version_id)
        if (
            version is None
            or version.project_id != project_id
            or version.draft_id != draft_id
        ):
            raise NotFound("draft_version not found")
        snapshot = self._repo.get_snapshot(version.snapshot_id)
        assert snapshot is not None
        blocks = self._repo.get_blocks(version.snapshot_id)
        return DraftVersionDetail(
            draft_version=version, snapshot=snapshot, blocks=blocks
        )

    def export_draft_version(
        self,
        *,
        project_id: str,
        draft_id: str,
        version_id: str,
        fmt: str = "txt",
    ) -> DraftVersionExport:
        if fmt not in _EXPORT_FORMATS:
            raise UnsupportedExportFormat(f"unsupported export format: {fmt!r}")
        detail = self.get_draft_version(
            project_id=project_id, draft_id=draft_id, version_id=version_id
        )
        content_type, extension = _EXPORT_FORMATS[fmt]
        version = detail.draft_version
        return DraftVersionExport(
            format=fmt,
            filename=f"{draft_id}-v{version.version_number}.{extension}",
            content_type=content_type,
            body=detail.snapshot.raw_text,
            project_id=project_id,
            draft_id=draft_id,
            version_id=version.id,
            version_number=version.version_number,
            snapshot_id=detail.snapshot.id,
            content_hash=detail.snapshot.content_hash,
        )

    def get_snapshot(
        self, *, project_id: str, snapshot_id: str
    ) -> SourceSnapshotDetail:
        snapshot = self._repo.get_snapshot(snapshot_id)
        if snapshot is None or snapshot.project_id != project_id:
            raise NotFound("snapshot not found")
        return SourceSnapshotDetail(
            snapshot=snapshot,
            blocks=self._repo.get_blocks(snapshot_id),
        )

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
        try:
            self._repo.record_save(
                idempotency_key=idempotency_key,
                version=version,
                snapshot=snapshot,
                blocks=blocks,
            )
        except DuplicateSaveRequest:
            committed_version_id = self._repo.find_save_request(
                project_id, draft_id, idempotency_key
            )
            assert committed_version_id is not None
            return self._save_result(committed_version_id, idempotent_replay=True)
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
        snapshot = self._repo.get_snapshot(snapshot_id)
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

        for block in self._repo.get_blocks(snapshot_id):
            if block.start_offset <= start_offset and end_offset <= block.end_offset:
                source_ref = SourceRef(
                    id=self._repo.next_source_ref_id(),
                    project_id=project_id,
                    snapshot_id=snapshot_id,
                    block_id=block.id,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    quote=snapshot.raw_text[start_offset:end_offset],
                    content_hash=snapshot.content_hash,
                )
                self._repo.record_source_ref(source_ref)
                return source_ref
        raise InvalidSourceRef("source_ref span must fit within one source block")

    def get_source_ref(self, *, project_id: str, source_ref_id: str) -> SourceRef:
        source_ref = self._repo.get_source_ref(source_ref_id)
        if source_ref is None or source_ref.project_id != project_id:
            raise NotFound("source_ref not found")
        return source_ref

    def list_source_refs(
        self, *, project_id: str, snapshot_id: str
    ) -> tuple[SourceRef, ...]:
        snapshot = self._repo.get_snapshot(snapshot_id)
        if snapshot is None or snapshot.project_id != project_id:
            raise NotFound("snapshot not found")
        return self._repo.list_source_refs(
            project_id=project_id, snapshot_id=snapshot_id
        )

    def archive_project(self, *, project_id: str) -> Project:
        project = self._require_project(project_id)
        archived = replace(project, archived=True)
        self._repo.put_project(archived)
        return archived

    def archive_draft(self, *, project_id: str, draft_id: str) -> Draft:
        self._require_project(project_id)
        draft = self._require_draft(project_id, draft_id)
        archived = replace(draft, archived=True)
        self._repo.put_draft(archived)
        return archived

    def _save_result(self, version_id: str, *, idempotent_replay: bool) -> SaveDraftResult:
        version = self._repo.get_version(version_id)
        assert version is not None
        snapshot = self._repo.get_snapshot(version.snapshot_id)
        assert snapshot is not None
        blocks = self._repo.get_blocks(version.snapshot_id)
        return SaveDraftResult(
            draft_version=version,
            snapshot=snapshot,
            blocks=blocks,
            idempotent_replay=idempotent_replay,
        )

    def _require_project(self, project_id: str) -> Project:
        project = self._repo.get_project(project_id)
        if project is None:
            raise NotFound("project not found")
        return project

    def _require_draft(self, project_id: str, draft_id: str) -> Draft:
        draft = self._repo.get_draft(draft_id)
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

    @staticmethod
    def _require_ordered_drafts(drafts: tuple[Draft, ...]) -> None:
        if any(
            draft.unit_kind is None
            or not isinstance(draft.unit_kind, UnitKind)
            or draft.position is None
            or not _is_int(draft.position)
            or draft.position < 1
            for draft in drafts
        ):
            raise InvalidDraftOrder("draft metadata migration is required")
        positions = tuple(draft.position for draft in drafts)
        if positions != tuple(range(1, len(drafts) + 1)):
            raise InvalidDraftOrder("draft positions must be a contiguous permutation")
