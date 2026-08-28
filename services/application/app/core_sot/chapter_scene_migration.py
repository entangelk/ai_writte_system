"""Explicit flat ordered-unit → Chapter/Scene hierarchy migration."""

from __future__ import annotations

from dataclasses import dataclass, replace

from services.application.app.core_sot.models import Chapter, Draft, UnitKind
from services.application.app.core_sot.repository import CoreSotRepository


@dataclass(frozen=True, slots=True)
class ChapterSceneMigrationResult:
    migrated_projects: int
    unchanged_projects: int


class ChapterSceneHierarchyMigration:
    """Build deterministic Chapter parents while preserving every Draft id."""

    def __init__(self, repository: CoreSotRepository) -> None:
        self._repo = repository

    def run(self) -> ChapterSceneMigrationResult:
        migrated = 0
        unchanged = 0
        for project in self._repo.list_projects():
            if self._migrate_project(project.id):
                migrated += 1
            else:
                unchanged += 1
        return ChapterSceneMigrationResult(
            migrated_projects=migrated,
            unchanged_projects=unchanged,
        )

    def _migrate_project(self, project_id: str) -> bool:
        chapters = self._repo.list_chapters(project_id)
        drafts = self._repo.list_drafts(project_id)
        if chapters or any(draft.chapter_id is not None for draft in drafts):
            self._validate_hierarchy(chapters, drafts)
            return False
        if not drafts:
            return False
        self._validate_legacy(drafts)

        migrated_chapters: list[Chapter] = []
        migrated_drafts: list[Draft] = []
        scene_counts: dict[str, int] = {}
        current_chapter: Chapter | None = None

        def open_chapter(title: str) -> Chapter:
            chapter = Chapter(
                id=self._repo.next_chapter_id(),
                project_id=project_id,
                title=title,
                position=len(migrated_chapters) + 1,
            )
            migrated_chapters.append(chapter)
            scene_counts[chapter.id] = 0
            return chapter

        for draft in sorted(drafts, key=lambda item: item.position):
            if draft.unit_kind is UnitKind.CHAPTER:
                current_chapter = open_chapter(draft.title)
                title = "본문"
            else:
                if current_chapter is None:
                    current_chapter = open_chapter("미분류")
                title = draft.title
            scene_counts[current_chapter.id] += 1
            migrated_drafts.append(replace(
                draft,
                chapter_id=current_chapter.id,
                title=title,
                unit_kind=None,
                position=scene_counts[current_chapter.id],
            ))

        self._repo.replace_hierarchy(
            project_id,
            tuple(migrated_chapters),
            tuple(migrated_drafts),
        )
        return True

    @staticmethod
    def _validate_legacy(drafts: tuple[Draft, ...]) -> None:
        if any(
            not isinstance(draft.unit_kind, UnitKind)
            or not isinstance(draft.position, int)
            or isinstance(draft.position, bool)
            or draft.position < 1
            for draft in drafts
        ):
            raise ValueError("legacy ordered-unit metadata is invalid")
        positions = tuple(sorted(draft.position for draft in drafts))
        if positions != tuple(range(1, len(drafts) + 1)):
            raise ValueError("legacy draft positions are duplicate or gapped")

    @staticmethod
    def _validate_hierarchy(
        chapters: tuple[Chapter, ...], drafts: tuple[Draft, ...]
    ) -> None:
        chapter_ids = {chapter.id for chapter in chapters}
        chapter_positions = tuple(sorted(chapter.position for chapter in chapters))
        if chapter_positions != tuple(range(1, len(chapters) + 1)):
            raise ValueError("chapter positions are duplicate or gapped")
        if any(
            draft.chapter_id not in chapter_ids or draft.unit_kind is not None
            for draft in drafts
        ):
            raise ValueError("draft hierarchy is partial or invalid")
        for chapter_id in chapter_ids:
            scenes = [draft for draft in drafts if draft.chapter_id == chapter_id]
            positions = tuple(sorted(draft.position for draft in scenes))
            if positions != tuple(range(1, len(scenes) + 1)):
                raise ValueError("scene positions are duplicate or gapped")
