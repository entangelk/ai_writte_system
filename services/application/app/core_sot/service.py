"""Infrastructure-free Core SOT service skeleton.

The in-memory repository is deliberately small: it locks the application-level
contract before a MongoDB adapter exists. It preserves immutable snapshots,
idempotent draft saves, deterministic block/hash/ref generation, project
isolation, and archive behavior.
"""

from __future__ import annotations

from dataclasses import replace

from services.application.app.core_sot.models import (
    Chapter,
    Draft,
    DraftVersion,
    DraftVersionDetail,
    DraftVersionExport,
    Project,
    ProjectBriefVersion,
    ProjectExport,
    ProjectExportUnit,
    PutProjectBriefResult,
    SaveDraftResult,
    SourceBlock,
    SourceRef,
    SourceSnapshot,
    SourceSnapshotDetail,
    StartNextUnitResult,
    UnitKind,
    WritingAcceptReceipt,
)
from services.application.app.core_sot.repository import (
    CoreSotRepository,
    DraftSetChanged,
    DuplicateProjectBriefRequest,
    DuplicateSaveRequest,
    DuplicateWritingAcceptReceipt,
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


class DraftOrderIntegrityError(InvalidDraftOrder):
    """The *stored* draft set violates the ordered-unit invariant.

    Distinct from the input-validation faces of ``InvalidDraftOrder`` (a bad
    ``unit_kind`` on create, a malformed reorder permutation): this signals that
    persisted data itself is not well-formed — a pre-v1.7.14 legacy document
    missing ``unit_kind``/``position``, or a corrupt non-contiguous position set.
    The resolution is the one-shot ``scripts/migrate_ordered_units.py`` migration,
    not a corrected request, so read endpoints surface it as 503 rather than a
    4xx client error.
    """


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
        self._chapter_seq = 0
        self._draft_seq = 0
        self._version_seq = 0
        self._snapshot_seq = 0
        self._source_ref_seq = 0
        self.projects: dict[str, Project] = {}
        self.chapters: dict[str, Chapter] = {}
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
        self._writing_accept_receipts: dict[
            tuple[str, str], WritingAcceptReceipt
        ] = {}

    def next_project_id(self) -> str:
        self._project_seq += 1
        return f"project-{self._project_seq}"

    def next_project_brief_version_id(self) -> str:
        self._project_brief_version_seq += 1
        return f"project-brief-version-{self._project_brief_version_seq}"

    def next_chapter_id(self) -> str:
        self._chapter_seq += 1
        return f"chapter-{self._chapter_seq}"

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

    def list_projects_for_owner(self, owner_id: str) -> tuple[Project, ...]:
        return tuple(
            project for project in self.projects.values()
            if project.owner_id == owner_id
        )

    def purge_project(self, project_id: str) -> None:
        # D8-6a: project 전체 그래프 영구 파기(in-memory). 직접 project_id 스코프 6곳 +
        # snapshot 체인(snapshots·blocks_by_snapshot). 인접 project 레코드는 건드리지 않는다.
        snapshot_ids = [
            sid
            for sid, snapshot in self.snapshots.items()
            if snapshot.project_id == project_id
        ]
        for sid in snapshot_ids:
            self.snapshots.pop(sid, None)
            self.blocks_by_snapshot.pop(sid, None)

        version_ids = [
            vid
            for vid, version in self.versions.items()
            if version.project_id == project_id
        ]
        for vid in version_ids:
            del self.versions[vid]
        self._save_request_index = {
            key: vid
            for key, vid in self._save_request_index.items()
            if key[0] != project_id
        }

        draft_ids = [
            draft.id
            for draft in self.drafts.values()
            if draft.project_id == project_id
        ]
        for draft_id in draft_ids:
            self.drafts.pop(draft_id, None)
            self._version_ids_by_draft.pop(draft_id, None)

        self.chapters = {
            cid: chapter
            for cid, chapter in self.chapters.items()
            if chapter.project_id != project_id
        }

        ref_ids = [
            rid
            for rid, ref in self.source_refs.items()
            if ref.project_id == project_id
        ]
        for rid in ref_ids:
            del self.source_refs[rid]

        # key = (project_id, idempotency_key)
        self._writing_accept_receipts = {
            key: receipt
            for key, receipt in self._writing_accept_receipts.items()
            if key[0] != project_id
        }

        brief_ids = list(self._project_brief_ids_by_project.pop(project_id, ()))
        for brief_id in brief_ids:
            self.project_brief_versions.pop(brief_id, None)
        self._project_brief_request_index = {
            key: bid
            for key, bid in self._project_brief_request_index.items()
            if key[0] != project_id
        }

        self.projects.pop(project_id, None)

    def purge_draft(self, project_id: str, draft_id: str) -> None:
        # 원고 하드 삭제 — purge_project가 지우는 축의 draft 소속 판(2026-08-28 오너
        # 결정: 원고 영구 삭제 추가). 프로젝트 레코드·브리프·인접 draft는 건드리지
        # 않는다. source_refs는 SourceRef가 draft_id를 몰라 snapshot_id 경유로 지운다.
        snapshot_ids = [
            sid
            for sid, snapshot in self.snapshots.items()
            if snapshot.project_id == project_id and snapshot.draft_id == draft_id
        ]
        removed_snapshots = set(snapshot_ids)
        for sid in snapshot_ids:
            self.snapshots.pop(sid, None)
            self.blocks_by_snapshot.pop(sid, None)
        self.source_refs = {
            rid: ref
            for rid, ref in self.source_refs.items()
            if ref.snapshot_id not in removed_snapshots
        }

        version_ids = [
            vid
            for vid, version in self.versions.items()
            if version.project_id == project_id and version.draft_id == draft_id
        ]
        for vid in version_ids:
            del self.versions[vid]
        # key = (project_id, idempotency_key) → version_id. draft_id가 키에 없어
        # 지워진 version_id를 값으로 갖는 행을 뺀다.
        removed_versions = set(version_ids)
        self._save_request_index = {
            key: vid
            for key, vid in self._save_request_index.items()
            if vid not in removed_versions
        }

        self.drafts.pop(draft_id, None)
        self._version_ids_by_draft.pop(draft_id, None)
        # receipt 는 (project_id, idempotency_key) 키지만 값에 draft_id 를 갖는다.
        self._writing_accept_receipts = {
            key: receipt
            for key, receipt in self._writing_accept_receipts.items()
            if receipt.draft_id != draft_id
        }

    def purge_chapter(self, project_id: str, chapter_id: str) -> None:
        chapter = self.chapters.get(chapter_id)
        if chapter is None or chapter.project_id != project_id:
            return
        child_ids = [
            draft.id for draft in self.drafts.values()
            if draft.project_id == project_id and draft.chapter_id == chapter_id
        ]
        for draft_id in child_ids:
            self.purge_draft(project_id, draft_id)
        self.chapters.pop(chapter_id, None)

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

    def get_chapter(self, chapter_id: str) -> Chapter | None:
        return self.chapters.get(chapter_id)

    def put_chapter(self, chapter: Chapter) -> None:
        self.chapters[chapter.id] = chapter

    def list_chapters(self, project_id: str) -> tuple[Chapter, ...]:
        return tuple(sorted(
            (chapter for chapter in self.chapters.values()
             if chapter.project_id == project_id),
            key=lambda chapter: chapter.position,
        ))

    def replace_chapter_metadata(
        self, project_id: str, chapters: tuple[Chapter, ...]
    ) -> None:
        current_ids = {
            chapter.id for chapter in self.chapters.values()
            if chapter.project_id == project_id
        }
        if current_ids != {chapter.id for chapter in chapters}:
            raise DraftSetChanged("chapter set changed during write")
        for chapter in chapters:
            self.chapters[chapter.id] = chapter

    def replace_hierarchy(
        self,
        project_id: str,
        chapters: tuple[Chapter, ...],
        drafts: tuple[Draft, ...],
    ) -> None:
        before_chapters = dict(self.chapters)
        before_drafts = dict(self.drafts)
        try:
            for chapter in chapters:
                if chapter.project_id != project_id:
                    raise DraftSetChanged("chapter belongs to another project")
                self.chapters[chapter.id] = chapter
            current_draft_ids = {
                draft.id for draft in self.drafts.values()
                if draft.project_id == project_id
            }
            if current_draft_ids != {draft.id for draft in drafts}:
                raise DraftSetChanged("draft set changed during hierarchy migration")
            for draft in drafts:
                self.drafts[draft.id] = draft
        except Exception:
            self.chapters = before_chapters
            self.drafts = before_drafts
            raise

    def put_draft(self, draft: Draft) -> None:
        self.drafts[draft.id] = draft

    def list_drafts(self, project_id: str) -> tuple[Draft, ...]:
        drafts = tuple(
            draft for draft in self.drafts.values() if draft.project_id == project_id
        )
        if drafts and all(draft.position is not None for draft in drafts):
            return tuple(sorted(
                drafts,
                key=lambda draft: (draft.chapter_id or "", draft.position),
            ))
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

    def get_writing_accept_receipt(
        self, project_id: str, idempotency_key: str
    ) -> WritingAcceptReceipt | None:
        return self._writing_accept_receipts.get((project_id, idempotency_key))

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
    ) -> None:
        receipt_key = (receipt.project_id, receipt.idempotency_key)
        if receipt_key in self._writing_accept_receipts:
            raise DuplicateWritingAcceptReceipt(receipt.idempotency_key)
        # Snapshot the exact before-image of every mutated draft so a mid-write
        # failure leaves zero of the six surfaces (WI-11 semantics on the
        # single-writer path; the transaction path enforces the same on Mongo).
        before = {draft.id: self.drafts[draft.id] for draft in shifted_drafts}
        try:
            for draft in shifted_drafts:
                self.drafts[draft.id] = draft
                self._after_draft_metadata_write(draft)
            self.drafts[new_draft.id] = new_draft
            self.versions[version.id] = version
            self.snapshots[snapshot.id] = snapshot
            self.blocks_by_snapshot[snapshot.id] = blocks
            self._version_ids_by_draft.setdefault(
                version.draft_id, []
            ).append(version.id)
            self._save_request_index[
                (version.project_id, version.draft_id, idempotency_key)
            ] = version.id
            self._writing_accept_receipts[receipt_key] = receipt
        except Exception:
            self.drafts.update(before)
            self.drafts.pop(new_draft.id, None)
            self.versions.pop(version.id, None)
            self.snapshots.pop(snapshot.id, None)
            self.blocks_by_snapshot.pop(snapshot.id, None)
            version_ids = self._version_ids_by_draft.get(version.draft_id)
            if version_ids and version.id in version_ids:
                version_ids.remove(version.id)
            self._save_request_index.pop(
                (version.project_id, version.draft_id, idempotency_key), None
            )
            self._writing_accept_receipts.pop(receipt_key, None)
            raise


class CoreSotService:
    def __init__(self, repository: CoreSotRepository) -> None:
        self._repo = repository

    def create_project(self, *, name: str, owner_id: str | None = None) -> Project:
        # owner_id is recorded, not enforced (D8-3 owns enforcement). Optional so
        # every existing caller — workers, scripts, tests — keeps working.
        project = Project(
            id=self._repo.next_project_id(), name=name, owner_id=owner_id
        )
        self._repo.put_project(project)
        return project

    def create_chapter(self, *, project_id: str, title: str) -> Chapter:
        project = self._require_project(project_id)
        if project.archived:
            raise Archived("project is archived")
        chapters = self._repo.list_chapters(project_id)
        self._require_ordered_chapters(chapters)
        chapter = Chapter(
            id=self._repo.next_chapter_id(),
            project_id=project_id,
            title=title,
            position=len(chapters) + 1,
        )
        self._repo.put_chapter(chapter)
        return chapter

    def create_scene(
        self, *, project_id: str, chapter_id: str, title: str
    ) -> Draft:
        project = self._require_project(project_id)
        if project.archived:
            raise Archived("project is archived")
        chapter = self._require_chapter(project_id, chapter_id)
        if chapter.archived:
            raise Archived("chapter is archived")
        scenes = self.list_scenes(project_id=project_id, chapter_id=chapter_id)
        scene = Draft(
            id=self._repo.next_draft_id(),
            project_id=project_id,
            chapter_id=chapter_id,
            title=title,
            position=len(scenes) + 1,
        )
        self._repo.put_draft(scene)
        return scene

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

    def list_projects_for_owner(self, *, owner_id: str) -> tuple[Project, ...]:
        return self._repo.list_projects_for_owner(owner_id)

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
        style_rules: tuple[str, ...] = (),
        preferred_patterns: tuple[str, ...] = (),
        forbidden_patterns: tuple[str, ...] = (),
        style_examples: tuple[str, ...] = (),
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
            style_rules=style_rules,
            preferred_patterns=preferred_patterns,
            forbidden_patterns=forbidden_patterns,
            style_examples=style_examples,
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

    def list_chapters(self, *, project_id: str) -> tuple[Chapter, ...]:
        self._require_project(project_id)
        chapters = self._repo.list_chapters(project_id)
        self._require_ordered_chapters(chapters)
        return chapters

    def list_scenes(
        self, *, project_id: str, chapter_id: str
    ) -> tuple[Draft, ...]:
        self._require_project(project_id)
        self._require_chapter(project_id, chapter_id)
        scenes = tuple(
            draft for draft in self._repo.list_drafts(project_id)
            if draft.chapter_id == chapter_id
        )
        self._require_ordered_scenes(scenes, chapter_id=chapter_id)
        return tuple(sorted(scenes, key=lambda draft: draft.position))

    def reorder_chapters(
        self, *, project_id: str, ordered_chapter_ids: tuple[str, ...]
    ) -> tuple[Chapter, ...]:
        project = self._require_project(project_id)
        if project.archived:
            raise Archived("project is archived")
        current = self.list_chapters(project_id=project_id)
        current_ids = tuple(chapter.id for chapter in current)
        if (
            len(ordered_chapter_ids) != len(current_ids)
            or len(set(ordered_chapter_ids)) != len(ordered_chapter_ids)
            or set(ordered_chapter_ids) != set(current_ids)
        ):
            raise InvalidDraftOrder(
                "ordered_chapter_ids must be the complete chapter set"
            )
        if ordered_chapter_ids == current_ids:
            return current
        by_id = {chapter.id: chapter for chapter in current}
        reordered = tuple(
            replace(by_id[chapter_id], position=index)
            for index, chapter_id in enumerate(ordered_chapter_ids, start=1)
        )
        self._repo.replace_chapter_metadata(project_id, reordered)
        return self.list_chapters(project_id=project_id)

    def reorder_scenes(
        self,
        *,
        project_id: str,
        chapter_id: str,
        ordered_draft_ids: tuple[str, ...],
    ) -> tuple[Draft, ...]:
        project = self._require_project(project_id)
        if project.archived:
            raise Archived("project is archived")
        chapter = self._require_chapter(project_id, chapter_id)
        if chapter.archived:
            raise Archived("chapter is archived")
        current = self.list_scenes(project_id=project_id, chapter_id=chapter_id)
        current_ids = tuple(draft.id for draft in current)
        if (
            len(ordered_draft_ids) != len(current_ids)
            or len(set(ordered_draft_ids)) != len(ordered_draft_ids)
            or set(ordered_draft_ids) != set(current_ids)
        ):
            raise InvalidDraftOrder(
                "ordered_draft_ids must be the complete scene set"
            )
        if ordered_draft_ids == current_ids:
            return current
        by_id = {draft.id: draft for draft in current}
        reordered_subset = {
            draft_id: replace(by_id[draft_id], position=index)
            for index, draft_id in enumerate(ordered_draft_ids, start=1)
        }
        all_drafts = tuple(
            reordered_subset.get(draft.id, draft)
            for draft in self._repo.list_drafts(project_id)
        )
        self._repo.replace_draft_metadata(project_id, all_drafts)
        return self.list_scenes(project_id=project_id, chapter_id=chapter_id)

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

    def export_project(
        self,
        *,
        project_id: str,
        fmt: str = "txt",
        include_archived: bool = False,
    ) -> ProjectExport:
        if fmt not in _EXPORT_FORMATS:
            raise UnsupportedExportFormat(f"unsupported export format: {fmt!r}")
        # Read-only: archived projects still export (SoT archive read-allowed).
        self._require_project(project_id)
        chapters = self._repo.list_chapters(project_id)
        drafts = self._repo.list_drafts(project_id)
        content_type, extension = _EXPORT_FORMATS[fmt]

        units: list[ProjectExportUnit] = []
        blocks: list[str] = []
        if chapters:
            self._require_ordered_chapters(chapters)
            chapter_ids = {chapter.id for chapter in chapters}
            if any(
                draft.chapter_id not in chapter_ids or draft.unit_kind is not None
                for draft in drafts
            ):
                raise DraftOrderIntegrityError(
                    "scene hierarchy migration is required"
                )
            for chapter in chapters:
                scenes = tuple(
                    draft for draft in drafts if draft.chapter_id == chapter.id
                )
                self._require_ordered_scenes(scenes, chapter_id=chapter.id)
                if chapter.archived and not include_archived:
                    continue
                scene_blocks: list[str] = []
                for scene in scenes:
                    if scene.archived and not include_archived:
                        continue
                    versions = self._repo.list_versions(scene.id)
                    if not versions:
                        continue
                    latest = max(
                        versions, key=lambda version: version.version_number
                    )
                    snapshot = self._repo.get_snapshot(latest.snapshot_id)
                    assert snapshot is not None
                    units.append(ProjectExportUnit(
                        draft_id=scene.id,
                        title=scene.title,
                        chapter_id=chapter.id,
                        chapter_title=chapter.title,
                        chapter_position=chapter.position,
                        unit_kind=None,
                        position=scene.position,
                        version_id=latest.id,
                        version_number=latest.version_number,
                        snapshot_id=snapshot.id,
                        content_hash=snapshot.content_hash,
                    ))
                    heading = (
                        f"## {scene.title}" if fmt == "markdown" else scene.title
                    )
                    scene_blocks.append(f"{heading}\n\n{snapshot.raw_text}")
                if scene_blocks:
                    chapter_heading = (
                        f"# {chapter.title}" if fmt == "markdown" else chapter.title
                    )
                    blocks.append(
                        f"{chapter_heading}\n\n" + "\n\n".join(scene_blocks)
                    )
            return ProjectExport(
                format=fmt,
                filename=f"{project_id}.{extension}",
                content_type=content_type,
                body="\n\n".join(blocks),
                project_id=project_id,
                include_archived=include_archived,
                units=tuple(units),
            )

        self._require_ordered_drafts(drafts)
        for draft in drafts:
            if draft.archived and not include_archived:
                continue
            versions = self._repo.list_versions(draft.id)
            if not versions:
                # Nothing saved yet: no snapshot to export, so the unit is
                # skipped from both body and manifest.
                continue
            latest = max(versions, key=lambda version: version.version_number)
            snapshot = self._repo.get_snapshot(latest.snapshot_id)
            assert snapshot is not None
            units.append(
                ProjectExportUnit(
                    draft_id=draft.id,
                    title=draft.title,
                    chapter_id=None,
                    chapter_title=None,
                    chapter_position=None,
                    unit_kind=draft.unit_kind,
                    position=draft.position,
                    version_id=latest.id,
                    version_number=latest.version_number,
                    snapshot_id=snapshot.id,
                    content_hash=snapshot.content_hash,
                )
            )
            heading = f"# {draft.title}" if fmt == "markdown" else draft.title
            blocks.append(f"{heading}\n\n{snapshot.raw_text}")

        return ProjectExport(
            format=fmt,
            filename=f"{project_id}.{extension}",
            content_type=content_type,
            body="\n\n".join(blocks),
            project_id=project_id,
            include_archived=include_archived,
            units=tuple(units),
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

    def get_writing_accept_receipt(
        self, *, project_id: str, idempotency_key: str
    ) -> WritingAcceptReceipt | None:
        return self._repo.get_writing_accept_receipt(project_id, idempotency_key)

    def start_next_unit(
        self,
        *,
        project_id: str,
        current_draft_id: str,
        raw_text: str,
        title: str,
        unit_kind: UnitKind,
        goal_intent: str,
        idempotency_key: str,
    ) -> StartNextUnitResult:
        """Atomically open the unit that follows ``current_draft_id`` (W0 §3.2).

        Shifts every position after the current unit (archived included) up by
        one, creates the new active Draft at ``current position + 1``, mints its
        version 1 / snapshot / blocks, and writes the accept receipt — all six
        surfaces in one transaction. ``goal_intent`` is the stored intent string,
        NOT prose: the generation goal itself is never persisted (WI-16).
        """
        if not idempotency_key:
            raise CoreSotError("idempotency_key is required")
        self._require_active_project_and_draft(project_id, current_draft_id)
        current = self._require_draft(project_id, current_draft_id)
        if current.chapter_id is not None:
            drafts = self.list_scenes(
                project_id=project_id, chapter_id=current.chapter_id
            )
            new_chapter_id = current.chapter_id
            new_unit_kind = None
        else:
            # Pre-v1.8.9 compatibility until the explicit migration has run.
            if not isinstance(unit_kind, UnitKind):
                raise InvalidDraftOrder("draft unit_kind is invalid")
            drafts = self._repo.list_drafts(project_id)
            self._require_ordered_drafts(drafts)
            new_chapter_id = None
            new_unit_kind = unit_kind
        current_position = current.position
        shifted = tuple(
            replace(draft, position=draft.position + 1)
            for draft in drafts
            if draft.position > current_position
        )
        new_draft = Draft(
            id=self._repo.next_draft_id(),
            project_id=project_id,
            title=title,
            chapter_id=new_chapter_id,
            unit_kind=new_unit_kind,
            position=current_position + 1,
        )
        version_id = self._repo.next_version_id()
        snapshot_id = self._repo.next_snapshot_id()
        version = DraftVersion(
            id=version_id,
            project_id=project_id,
            draft_id=new_draft.id,
            version_number=1,
            snapshot_id=snapshot_id,
            idempotency_key=idempotency_key,
        )
        snapshot = SourceSnapshot(
            id=snapshot_id,
            project_id=project_id,
            draft_id=new_draft.id,
            version_id=version_id,
            raw_text=raw_text,
            content_hash=content_hash(raw_text),
        )
        blocks = materialize_blocks(
            project_id=project_id,
            snapshot_id=snapshot_id,
            raw_blocks=split_source_blocks(raw_text),
        )
        receipt = WritingAcceptReceipt(
            project_id=project_id,
            idempotency_key=idempotency_key,
            intent=goal_intent,
            draft_id=new_draft.id,
            draft_version_id=version_id,
        )
        self._repo.record_start_next_unit(
            shifted_drafts=shifted,
            new_draft=new_draft,
            idempotency_key=idempotency_key,
            version=version,
            snapshot=snapshot,
            blocks=blocks,
            receipt=receipt,
        )
        return StartNextUnitResult(
            draft=new_draft, draft_version=version,
            snapshot=snapshot, blocks=blocks)

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

    def purge_project(self, *, project_id: str) -> None:
        # D8-6a: project 전체 그래프 영구 파기(관리자 전용 operation, D5=A). archive와 달리
        # enqueue하지 않는다 — enqueue는 endpoint(D8-6d)에서 archive와 같은 시점에 한다.
        # NotFound 끌어올림은 _require_project에서(엔드포인트가 404로 매핑).
        self._require_project(project_id)
        self._repo.purge_project(project_id)

    def purge_draft(self, *, project_id: str, draft_id: str) -> None:
        # 원고 하드 삭제(2026-08-28 오너 결정) — purge_project의 draft 스코프 판.
        # archived 선행 검증은 엔드포인트가 한다(프로젝트 purge와 같은 분업).
        # NotFound 끌어올림은 _require_draft에서(엔드포인트가 404로 매핑).
        self._require_project(project_id)
        self._require_draft(project_id, draft_id)
        self._repo.purge_draft(project_id, draft_id)

    def archive_chapter(
        self, *, project_id: str, chapter_id: str
    ) -> Chapter:
        project = self._require_project(project_id)
        if project.archived:
            raise Archived("project is archived")
        chapter = self._require_chapter(project_id, chapter_id)
        archived = replace(chapter, archived=True)
        self._repo.put_chapter(archived)
        return archived

    def purge_chapter(self, *, project_id: str, chapter_id: str) -> None:
        self._require_project(project_id)
        self._require_chapter(project_id, chapter_id)
        self._repo.purge_chapter(project_id, chapter_id)

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

    def _require_chapter(self, project_id: str, chapter_id: str) -> Chapter:
        chapter = self._repo.get_chapter(chapter_id)
        if chapter is None or chapter.project_id != project_id:
            raise NotFound("chapter not found")
        return chapter

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
            raise DraftOrderIntegrityError("draft metadata migration is required")
        positions = tuple(draft.position for draft in drafts)
        if positions != tuple(range(1, len(drafts) + 1)):
            raise DraftOrderIntegrityError(
                "draft positions must be a contiguous permutation"
            )

    @staticmethod
    def _require_ordered_chapters(chapters: tuple[Chapter, ...]) -> None:
        if any(
            not _is_int(chapter.position) or chapter.position < 1
            for chapter in chapters
        ):
            raise DraftOrderIntegrityError("chapter positions are invalid")
        positions = tuple(sorted(chapter.position for chapter in chapters))
        if positions != tuple(range(1, len(chapters) + 1)):
            raise DraftOrderIntegrityError(
                "chapter positions must be a contiguous permutation"
            )

    @staticmethod
    def _require_ordered_scenes(
        scenes: tuple[Draft, ...], *, chapter_id: str
    ) -> None:
        if any(
            draft.chapter_id != chapter_id
            or draft.position is None
            or not _is_int(draft.position)
            or draft.position < 1
            for draft in scenes
        ):
            raise DraftOrderIntegrityError("scene hierarchy migration is required")
        positions = tuple(sorted(draft.position for draft in scenes))
        if positions != tuple(range(1, len(scenes) + 1)):
            raise DraftOrderIntegrityError(
                "scene positions must be a contiguous permutation within chapter"
            )
