"""Chapter→Scene hierarchy core contract (SoT v1.8.9).

Under-strict guards reject the pre-v1.8.9 flat model: a Scene must belong to a
real Chapter and ordering is parent-scoped. Over-strict guards keep valid
independent Chapter/Scene permutations and preserve every legacy Draft id.
"""

from __future__ import annotations

import asyncio
import unittest
from dataclasses import replace

from fastapi import FastAPI, HTTPException

from services.application.app.analysis.service import (
    AnalysisService,
    InMemoryAnalysisRepository,
)

from services.application.app.core_sot.chapter_scene_migration import (
    ChapterSceneHierarchyMigration,
)
from services.application.app.core_sot.models import Draft, UnitKind
from services.application.app.core_sot.service import (
    Archived,
    CoreSotService,
    DraftOrderIntegrityError,
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
    DraftPayload,
    RenameDraftRequest,
    SceneOrderPutRequest,
)
from services.application.app.routers.drafts import register_drafts
from services.application.app.writing.generation_job import (
    InMemoryWritingGenerationJobRepository,
    WritingGenerationJobService,
)
from services.application.app.writing.scratch import (
    InMemoryWritingScratchRepository,
    WritingScratchService,
)
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

    def test_legacy_drafts_fail_closed_at_the_service_boundary(self):
        # 검증 B1(2026-08-28): migration 전 평면 Draft는 서비스 읽기 경계에서
        # 이미 거부된다(라우터 payload 가드와 2층 방어 — 각 층을 따로 잠근다).
        # 장면이 하나도 없는 프로젝트는 legacy가 아니라 빈 정상 상태다.
        empty = self.service.create_project(name="빈 작품")
        self.assertEqual(self.service.list_drafts(project_id=empty.id), ())

        self.repo.put_draft(Draft(
            id="legacy-flat", project_id=self.project.id,
            title="평면 원고", unit_kind=UnitKind.SCENE, position=1,
        ))
        with self.assertRaises(DraftOrderIntegrityError):
            self.service.list_drafts(project_id=self.project.id)

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
        text = self.service.export_project(
            project_id=self.project.id, fmt="txt", include_archived=True
        )

        self.assertEqual(visible.body, "# 1장\n\n## 첫 장면\n\n첫 본문")
        self.assertEqual(
            complete.body,
            "# 1장\n\n## 첫 장면\n\n첫 본문\n\n# 2장\n\n## 숨은 장면\n\n숨은 본문",
        )
        self.assertEqual(
            text.body,
            "1장\n\n첫 장면\n\n첫 본문\n\n2장\n\n숨은 장면\n\n숨은 본문",
        )
        self.assertFalse(self.repo.get_draft(hidden.id).archived)
        self.assertEqual(
            [(unit.chapter_id, unit.chapter_title) for unit in complete.units],
            [(first.id, "1장"), (second.id, "2장")],
        )

    def test_archived_chapter_blocks_child_writes_without_mutating_child_flag(self):
        chapter = self.service.create_chapter(
            project_id=self.project.id, title="보관 장"
        )
        scene = self.service.create_scene(
            project_id=self.project.id, chapter_id=chapter.id, title="장면"
        )
        self.service.archive_chapter(
            project_id=self.project.id, chapter_id=chapter.id
        )

        with self.assertRaises(Archived):
            self.service.save_draft(
                project_id=self.project.id,
                draft_id=scene.id,
                raw_text="쓰면 안 됨",
                idempotency_key="blocked-save",
            )

        self.assertFalse(self.repo.get_draft(scene.id).archived)
        self.assertEqual(self.repo.version_count(scene.id), 0)


class ChapterHierarchyMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = InMemoryCoreSotRepository()
        self.service = CoreSotService(self.repo)
        self.project = self.service.create_project(name="legacy")

    def _legacy(self, draft_id: str, title: str, kind: UnitKind, position: int):
        draft = Draft(
            id=draft_id,
            project_id=self.project.id,
            title=title,
            unit_kind=kind,
            position=position,
        )
        self.repo.put_draft(draft)
        return draft

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

    def test_migration_preserves_versions_snapshots_body_bytes_and_archive(self):
        legacy = self._legacy("legacy", "1장", UnitKind.CHAPTER, 1)
        raw_text = "첫 줄\r\n\r\n둘째 줄.  \n"
        saved = self.service.save_draft(
            project_id=self.project.id, draft_id=legacy.id,
            raw_text=raw_text, idempotency_key="legacy-save",
        )
        self.repo.put_draft(replace(legacy, archived=True))
        versions_before = self.repo.list_versions(legacy.id)
        snapshot_before = self.repo.get_snapshot(saved.snapshot.id)
        blocks_before = self.repo.get_blocks(saved.snapshot.id)

        ChapterSceneHierarchyMigration(self.repo).run()

        migrated = self.repo.get_draft(legacy.id)
        self.assertTrue(migrated.archived)
        self.assertEqual(self.repo.list_versions(legacy.id), versions_before)
        self.assertEqual(self.repo.get_snapshot(saved.snapshot.id), snapshot_before)
        self.assertEqual(self.repo.get_snapshot(saved.snapshot.id).raw_text, raw_text)
        self.assertEqual(self.repo.get_blocks(saved.snapshot.id), blocks_before)

    def test_partial_hierarchy_fails_closed_without_changing_any_row(self):
        chapter = self.service.create_chapter(
            project_id=self.project.id, title="이미 생긴 장"
        )
        legacy = self._legacy("legacy", "고아 평면 원고", UnitKind.SCENE, 1)
        before_chapters = self.repo.list_chapters(self.project.id)
        before_drafts = self.repo.list_drafts(self.project.id)

        with self.assertRaisesRegex(ValueError, "partial or invalid"):
            ChapterSceneHierarchyMigration(self.repo).run()

        self.assertEqual(self.repo.list_chapters(self.project.id), before_chapters)
        self.assertEqual(self.repo.list_drafts(self.project.id), before_drafts)
        self.assertEqual(self.repo.get_chapter(chapter.id), chapter)
        self.assertEqual(self.repo.get_draft(legacy.id), legacy)


class ChapterHierarchyApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = InMemoryCoreSotRepository()
        self.service = CoreSotService(self.repo)
        self.project = self.service.create_project(
            name="API 작품", owner_id=TEST_USER.id
        )
        activity = ActivityLogService(InMemoryActivityLogRepository())
        self.jobs = WritingGenerationJobService(
            InMemoryWritingGenerationJobRepository()
        )
        self.scratch = WritingScratchService(InMemoryWritingScratchRepository())
        self.analysis = AnalysisService(InMemoryAnalysisRepository())
        app = FastAPI()
        register_drafts(
            app,
            core_sot=self.service,
            sync_outbox=object(),
            activity=activity,
            writing_generation_jobs=self.jobs,
            writing_scratch=self.scratch,
            analysis=self.analysis,
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
        self.assertEqual(one["chapter_id"], chapter_id)

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
        for scene in listed["chapters"][0]["scenes"]:
            self.assertIn("latest_snapshot_id", scene)
            self.assertIn("finalized_snapshot_id", scene)
            self.assertIn("analysis_status", scene)
            self.assertIn("analysis_snapshot_id", scene)

        list_flat = self._endpoint("/projects/{project_id}/drafts", "GET")
        flattened = asyncio.run(list_flat(self.project.id))
        self.assertEqual(
            [scene["id"] for scene in flattened["drafts"]],
            [two["id"], one["id"]],
        )
        self.assertTrue(all(
            scene["chapter_id"] == chapter_id
            and "unit_kind" not in scene
            for scene in flattened["drafts"]
        ))

    def test_flat_contract_and_nested_analysis_values(self):
        """Under: exact latest job is exposed; over: flat Draft stays closed."""
        create_chapter = self._endpoint(
            "/projects/{project_id}/chapters", "POST"
        )
        chapter = asyncio.run(create_chapter(
            self.project.id, CreateChapterRequest(title="상태 장"), TEST_USER
        ))
        create_scene = self._endpoint(
            "/projects/{project_id}/drafts", "POST"
        )
        created = asyncio.run(create_scene(
            self.project.id,
            CreateDraftRequest(title="상태 장면", chapter_id=chapter["id"]),
            TEST_USER,
        ))
        # Flat endpoints declare DraftPayload(extra="forbid"). A Scene-only
        # latest_snapshot_id here reproduces the dogfood P0 response 500.
        DraftPayload.model_validate(created)
        self.assertNotIn("latest_snapshot_id", created)

        saved = self.service.save_draft(
            project_id=self.project.id,
            draft_id=created["id"],
            raw_text="분석할 본문",
            idempotency_key="scene-status-save",
        )
        snapshot_id = saved.snapshot.id
        job = self.analysis.create_job(
            project_id=self.project.id,
            snapshot_id=snapshot_id,
            idempotency_key=f"analyze:{snapshot_id}",
        ).job
        self.analysis.mark_job_running(project_id=self.project.id, job_id=job.id)

        list_flat = self._endpoint("/projects/{project_id}/drafts", "GET")
        flat = asyncio.run(list_flat(self.project.id))["drafts"][0]
        DraftPayload.model_validate(flat)
        self.assertNotIn("latest_snapshot_id", flat)
        self.assertEqual(flat["analysis_snapshot_id"], snapshot_id)
        self.assertEqual(flat["analysis_status"], "running")

        list_chapters = self._endpoint(
            "/projects/{project_id}/chapters", "GET"
        )
        nested = asyncio.run(list_chapters(self.project.id))["chapters"][0]["scenes"][0]
        self.assertEqual(nested["latest_snapshot_id"], snapshot_id)
        self.assertEqual(nested["analysis_snapshot_id"], snapshot_id)
        self.assertEqual(nested["analysis_status"], "running")

    def test_scene_create_contract_requires_parent_and_rejects_unit_kind(self):
        with self.assertRaises(ValueError):
            CreateDraftRequest.model_validate({"title": "고아 장면"})
        with self.assertRaises(ValueError):
            CreateDraftRequest.model_validate({
                "title": "예외축",
                "chapter_id": "chapter-1",
                "unit_kind": "other",
            })

    def test_legacy_scene_crud_fails_closed_with_503_before_any_write(self):
        legacy = Draft(
            id="legacy-scene", project_id=self.project.id, title="평면 원고",
            unit_kind=UnitKind.SCENE, position=1,
        )
        self.repo.put_draft(legacy)

        calls = (
            (self._endpoint("/projects/{project_id}/drafts", "GET"),
             (self.project.id,)),
            (self._endpoint("/projects/{project_id}/drafts/{draft_id}", "GET"),
             (self.project.id, legacy.id)),
            (self._endpoint("/projects/{project_id}/drafts/{draft_id}", "PATCH"),
             (self.project.id, legacy.id, RenameDraftRequest(title="바뀌면 안 됨"), TEST_USER)),
            (self._endpoint("/projects/{project_id}/drafts/{draft_id}", "DELETE"),
             (self.project.id, legacy.id, TEST_USER)),
        )
        for endpoint, arguments in calls:
            with self.subTest(endpoint=endpoint.__name__):
                with self.assertRaises(HTTPException) as raised:
                    asyncio.run(endpoint(*arguments))
                self.assertEqual(raised.exception.status_code, 503)

        unchanged = self.repo.get_draft(legacy.id)
        self.assertEqual(unchanged.title, "평면 원고")
        self.assertFalse(unchanged.archived)

    def test_chapter_purge_active_job_guard_writes_nothing(self):
        chapter = self.service.create_chapter(
            project_id=self.project.id, title="안전 장"
        )
        scene = self.service.create_scene(
            project_id=self.project.id, chapter_id=chapter.id, title="작업 중"
        )
        self.service.archive_chapter(
            project_id=self.project.id, chapter_id=chapter.id
        )
        self.jobs.enqueue(
            project_id=self.project.id,
            draft_id=scene.id,
            request_id="active-job",
            task_type="continue",
            instruction="이어쓰기",
            draft_excerpt="",
            query=None,
            output_length="short",
            max_output_tokens=512,
            max_tokens=1024,
            version_id="version-1",
        )
        purge = self._endpoint(
            "/projects/{project_id}/chapters/{chapter_id}/purge", "POST"
        )

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(purge(self.project.id, chapter.id, TEST_USER))

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIsNotNone(self.repo.get_chapter(chapter.id))
        self.assertIsNotNone(self.repo.get_draft(scene.id))

    def test_chapter_purge_removes_terminal_child_jobs(self):
        chapter = self.service.create_chapter(
            project_id=self.project.id, title="완료 장"
        )
        scene = self.service.create_scene(
            project_id=self.project.id, chapter_id=chapter.id, title="완료 장면"
        )
        self.service.archive_chapter(
            project_id=self.project.id, chapter_id=chapter.id
        )
        self.jobs.enqueue(
            project_id=self.project.id, draft_id=scene.id,
            request_id="done-job", task_type="continue", instruction="이어쓰기",
            draft_excerpt="", query=None, output_length="short",
            max_output_tokens=512, max_tokens=1024, version_id="version-1",
        )
        claimed = self.jobs.claim_next()
        assert claimed is not None
        self.jobs.mark_succeeded(claimed, result_scratch_id="scratch-1")
        purge = self._endpoint(
            "/projects/{project_id}/chapters/{chapter_id}/purge", "POST"
        )

        asyncio.run(purge(self.project.id, chapter.id, TEST_USER))

        self.assertIsNone(self.repo.get_chapter(chapter.id))
        self.assertIsNone(self.repo.get_draft(scene.id))
        self.assertEqual(self.jobs.list_for_draft(self.project.id, scene.id), ())


if __name__ == "__main__":
    unittest.main()
