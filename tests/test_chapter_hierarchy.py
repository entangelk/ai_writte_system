"""Chapter→Scene hierarchy core contract (SoT v1.8.9).

Under-strict guards reject the pre-v1.8.9 flat model: a Scene must belong to a
real Chapter and ordering is parent-scoped. Over-strict guards keep valid
independent Chapter/Scene permutations and preserve every legacy Draft id.
"""

from __future__ import annotations

import asyncio
import unittest

from fastapi import FastAPI

from services.application.app.core_sot.chapter_scene_migration import (
    ChapterSceneHierarchyMigration,
)
from services.application.app.core_sot.models import Draft, UnitKind
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
    InvalidDraftOrder,
)
from services.application.app.activity.log import (
    ActivityLogService,
    InMemoryActivityLogRepository,
)
from services.application.app.api.models import (
    CreateChapterRequest,
    CreateDraftRequest,
    SceneOrderPutRequest,
)
from services.application.app.routers.drafts import register_drafts
from tests.auth_support import TEST_USER


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

    def test_chapter_purge_cascades_children_without_touching_a_sibling(self):
        first = self.service.create_chapter(
            project_id=self.project.id, title="1장"
        )
        second = self.service.create_chapter(
            project_id=self.project.id, title="2장"
        )
        victim = self.service.create_scene(
            project_id=self.project.id, chapter_id=first.id, title="삭제 장면"
        )
        sibling = self.service.create_scene(
            project_id=self.project.id, chapter_id=second.id, title="보존 장면"
        )

        self.service.archive_chapter(
            project_id=self.project.id, chapter_id=first.id
        )
        self.service.purge_chapter(
            project_id=self.project.id, chapter_id=first.id
        )

        self.assertIsNone(self.repo.get_chapter(first.id))
        self.assertIsNone(self.repo.get_draft(victim.id))
        self.assertEqual(self.repo.get_chapter(second.id), second)
        self.assertEqual(self.repo.get_draft(sibling.id), sibling)

    def test_start_next_unit_creates_only_the_next_scene_in_the_same_chapter(self):
        first = self.service.create_chapter(
            project_id=self.project.id, title="1장"
        )
        second = self.service.create_chapter(
            project_id=self.project.id, title="2장"
        )
        current = self.service.create_scene(
            project_id=self.project.id, chapter_id=first.id, title="현재 장면"
        )
        tail = self.service.create_scene(
            project_id=self.project.id, chapter_id=first.id, title="뒤 장면"
        )
        other = self.service.create_scene(
            project_id=self.project.id, chapter_id=second.id, title="다른 장"
        )

        result = self.service.start_next_unit(
            project_id=self.project.id,
            current_draft_id=current.id,
            raw_text="새 장면 본문",
            title="새 장면",
            unit_kind=UnitKind.CHAPTER,  # ignored after hierarchy migration
            goal_intent="start_next_unit",
            idempotency_key="next-scene",
        )

        self.assertEqual(result.draft.chapter_id, first.id)
        self.assertIsNone(result.draft.unit_kind)
        self.assertEqual(
            [(scene.id, scene.position) for scene in self.service.list_scenes(
                project_id=self.project.id, chapter_id=first.id
            )],
            [(current.id, 1), (result.draft.id, 2), (tail.id, 3)],
        )
        self.assertEqual(self.service.list_scenes(
            project_id=self.project.id, chapter_id=second.id), (other,))

    def test_export_uses_chapter_then_scene_headings_and_derived_archive(self):
        first = self.service.create_chapter(
            project_id=self.project.id, title="1장"
        )
        second = self.service.create_chapter(
            project_id=self.project.id, title="2장"
        )
        one = self.service.create_scene(
            project_id=self.project.id, chapter_id=first.id, title="첫 장면"
        )
        hidden = self.service.create_scene(
            project_id=self.project.id, chapter_id=second.id, title="숨은 장면"
        )
        for scene, body in ((one, "첫 본문"), (hidden, "숨은 본문")):
            self.service.save_draft(
                project_id=self.project.id,
                draft_id=scene.id,
                raw_text=body,
                idempotency_key=f"save-{scene.id}",
            )
        self.service.archive_chapter(
            project_id=self.project.id, chapter_id=second.id
        )

        visible = self.service.export_project(
            project_id=self.project.id, fmt="markdown"
        )
        complete = self.service.export_project(
            project_id=self.project.id, fmt="markdown", include_archived=True
        )

        self.assertEqual(visible.body, "# 1장\n\n## 첫 장면\n\n첫 본문")
        self.assertEqual(
            complete.body,
            "# 1장\n\n## 첫 장면\n\n첫 본문\n\n# 2장\n\n## 숨은 장면\n\n숨은 본문",
        )
        self.assertFalse(self.repo.get_draft(hidden.id).archived)
        self.assertEqual(
            [(unit.chapter_id, unit.chapter_title) for unit in complete.units],
            [(first.id, "1장"), (second.id, "2장")],
        )


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


class ChapterHierarchyApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = InMemoryCoreSotRepository()
        self.service = CoreSotService(self.repo)
        self.project = self.service.create_project(
            name="API 작품", owner_id=TEST_USER.id
        )
        activity = ActivityLogService(InMemoryActivityLogRepository())
        app = FastAPI()
        register_drafts(
            app,
            core_sot=self.service,
            sync_outbox=object(),
            activity=activity,
            writing_generation_jobs=object(),
            writing_scratch=object(),
        )
        self.app = app

    def _endpoint(self, path: str, method: str):
        return next(
            route.endpoint for route in self.app.routes
            if getattr(route, "path", None) == path
            and method in getattr(route, "methods", set())
        )

    def test_create_list_and_parent_scoped_reorder(self):
        create_chapter = self._endpoint(
            "/projects/{project_id}/chapters", "POST"
        )
        first = asyncio.run(create_chapter(
            self.project.id, CreateChapterRequest(title="1장"), TEST_USER
        ))
        chapter_id = first["id"]
        self.assertEqual(first["scenes"], [])

        create_scene = self._endpoint(
            "/projects/{project_id}/drafts", "POST"
        )
        one = asyncio.run(create_scene(
            self.project.id,
            CreateDraftRequest(title="첫 장면", chapter_id=chapter_id),
            TEST_USER,
        ))
        two = asyncio.run(create_scene(
            self.project.id,
            CreateDraftRequest(title="둘째 장면", chapter_id=chapter_id),
            TEST_USER,
        ))
        self.assertNotIn("unit_kind", one)

        reorder = self._endpoint(
            "/projects/{project_id}/chapters/{chapter_id}/scene-order", "PUT"
        )
        moved = asyncio.run(reorder(
            self.project.id,
            chapter_id,
            SceneOrderPutRequest(ordered_draft_ids=[two["id"], one["id"]]),
            TEST_USER,
        ))
        self.assertEqual(
            [scene["id"] for scene in moved["scenes"]],
            [two["id"], one["id"]],
        )

        list_chapters = self._endpoint(
            "/projects/{project_id}/chapters", "GET"
        )
        listed = asyncio.run(list_chapters(self.project.id))
        self.assertEqual(
            [scene["title"] for scene in listed["chapters"][0]["scenes"]],
            ["둘째 장면", "첫 장면"],
        )


if __name__ == "__main__":
    unittest.main()
