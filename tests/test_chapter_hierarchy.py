"""Chapter→Scene hierarchy core contract (SoT v1.8.9).

Under-strict guards reject the pre-v1.8.9 flat model: a Scene must belong to a
real Chapter and ordering is parent-scoped. Over-strict guards keep valid
independent Chapter/Scene permutations and preserve every legacy Draft id.
"""

from __future__ import annotations

import unittest

from services.application.app.core_sot.chapter_scene_migration import (
    ChapterSceneHierarchyMigration,
)
from services.application.app.core_sot.models import Draft, UnitKind
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
    InvalidDraftOrder,
)


class ChapterHierarchyContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = InMemoryCoreSotRepository()
        self.service = CoreSotService(self.repo)
        self.project = self.service.create_project(name="계층 작품")

    def test_chapters_and_scenes_have_independent_contiguous_orders(self):
        first = self.service.create_chapter(
            project_id=self.project.id, title="1장"
        )
        second = self.service.create_chapter(
            project_id=self.project.id, title="2장"
        )
        one = self.service.create_scene(
            project_id=self.project.id, chapter_id=first.id, title="첫 장면"
        )
        two = self.service.create_scene(
            project_id=self.project.id, chapter_id=first.id, title="둘째 장면"
        )
        other = self.service.create_scene(
            project_id=self.project.id, chapter_id=second.id, title="다른 장면"
        )

        self.assertEqual([c.id for c in self.service.list_chapters(
            project_id=self.project.id)], [first.id, second.id])
        self.assertEqual([d.id for d in self.service.list_scenes(
            project_id=self.project.id, chapter_id=first.id)], [one.id, two.id])
        self.assertEqual(other.position, 1)  # over-strict: position is per Chapter.

    def test_reorder_rejects_a_scene_from_another_chapter_without_write(self):
        first = self.service.create_chapter(
            project_id=self.project.id, title="1장"
        )
        second = self.service.create_chapter(
            project_id=self.project.id, title="2장"
        )
        one = self.service.create_scene(
            project_id=self.project.id, chapter_id=first.id, title="첫 장면"
        )
        other = self.service.create_scene(
            project_id=self.project.id, chapter_id=second.id, title="다른 장면"
        )

        with self.assertRaises(InvalidDraftOrder):
            self.service.reorder_scenes(
                project_id=self.project.id,
                chapter_id=first.id,
                ordered_draft_ids=(other.id,),
            )

        self.assertEqual(self.service.list_scenes(
            project_id=self.project.id, chapter_id=first.id), (one,))

    def test_chapter_and_scene_reorder_are_independent(self):
        first = self.service.create_chapter(
            project_id=self.project.id, title="1장"
        )
        second = self.service.create_chapter(
            project_id=self.project.id, title="2장"
        )
        one = self.service.create_scene(
            project_id=self.project.id, chapter_id=first.id, title="첫 장면"
        )
        two = self.service.create_scene(
            project_id=self.project.id, chapter_id=first.id, title="둘째 장면"
        )

        self.service.reorder_chapters(
            project_id=self.project.id,
            ordered_chapter_ids=(second.id, first.id),
        )
        self.service.reorder_scenes(
            project_id=self.project.id,
            chapter_id=first.id,
            ordered_draft_ids=(two.id, one.id),
        )

        self.assertEqual([c.id for c in self.service.list_chapters(
            project_id=self.project.id)], [second.id, first.id])
        self.assertEqual([d.id for d in self.service.list_scenes(
            project_id=self.project.id, chapter_id=first.id)], [two.id, one.id])


class ChapterHierarchyMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = InMemoryCoreSotRepository()
        self.service = CoreSotService(self.repo)
        self.project = self.service.create_project(name="legacy")

    def _legacy(self, draft_id: str, title: str, kind: UnitKind, position: int):
        self.repo.put_draft(Draft(
            id=draft_id,
            project_id=self.project.id,
            title=title,
            unit_kind=kind,
            position=position,
        ))

    def test_migration_preserves_draft_ids_and_builds_deterministic_groups(self):
        self._legacy("preface", "서문", UnitKind.OTHER, 1)
        self._legacy("chapter-body", "1장", UnitKind.CHAPTER, 2)
        self._legacy("scene-two", "둘째 장면", UnitKind.SCENE, 3)
        self._legacy("chapter-two", "2장", UnitKind.CHAPTER, 4)

        result = ChapterSceneHierarchyMigration(self.repo).run()

        self.assertEqual(result.migrated_projects, 1)
        chapters = self.service.list_chapters(project_id=self.project.id)
        self.assertEqual([c.title for c in chapters], ["미분류", "1장", "2장"])
        self.assertEqual(
            [d.id for d in self.service.list_scenes(
                project_id=self.project.id, chapter_id=chapters[0].id)],
            ["preface"],
        )
        first_chapter_scenes = self.service.list_scenes(
            project_id=self.project.id, chapter_id=chapters[1].id
        )
        self.assertEqual(
            [(d.id, d.title) for d in first_chapter_scenes],
            [("chapter-body", "본문"), ("scene-two", "둘째 장면")],
        )
        self.assertEqual(
            [d.id for d in self.service.list_scenes(
                project_id=self.project.id, chapter_id=chapters[2].id)],
            ["chapter-two"],
        )

    def test_valid_hierarchy_is_a_noop_not_an_over_strict_remigration(self):
        chapter = self.service.create_chapter(
            project_id=self.project.id, title="1장"
        )
        scene = self.service.create_scene(
            project_id=self.project.id, chapter_id=chapter.id, title="첫 장면"
        )

        result = ChapterSceneHierarchyMigration(self.repo).run()

        self.assertEqual(result.migrated_projects, 0)
        self.assertEqual(result.unchanged_projects, 1)
        self.assertEqual(self.service.list_scenes(
            project_id=self.project.id, chapter_id=chapter.id), (scene,))


if __name__ == "__main__":
    unittest.main()
