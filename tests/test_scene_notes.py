"""장면 메모(Slice 0) 저장·수명 계약 — in-memory.

정본: [`docs/plans/scene-note-decisions.md`](../docs/plans/scene-note-decisions.md)
D1=C+A · D2=A · D3=A · D4=A, 페이즈: `scene-note-implementation-phases.md` Slice 0.

이 slice 가 잠그는 것은 **저장 단위와 파기 수명**뿐이다 — HTTP route·프론트·활동
기록은 다음 slice 다.

- `(project_id, draft_id)` 당 현재 메모 한 건, 명시적 저장이 값을 교체한다(D4=A).
- 빈 본문은 **행 삭제가 아니라 빈 현재값**이다(페이즈 Slice 0 계약).
- 다른 프로젝트의 `draft_id` 는 읽기·쓰기 모두 NotFound(프로젝트 격리).
- 본문 상한은 `SCENE_NOTE_MAX_CHARS`(12000자, 오너 2026-08-31) — 원고 본문 상한 4000 의
  3배. 메모는 프롬프트에 실리지 않으므로 4000 의 이어쓰기-예산 근거는 옮겨오지 않고,
  "여러 장면 분량의 재료를 담는다"는 쓰임이 값을 정한다.
- archive 는 메모를 파기하지 않는다(읽기 유지, 쓰기는 기존 원고 저장과 같은 409 축).
- Scene purge · Chapter cascade · project purge 에 고아가 남지 않는다.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from services.application.app.core_sot.models import SceneNote
from services.application.app.core_sot.service import (
    SCENE_NOTE_MAX_CHARS,
    Archived,
    CoreSotService,
    InMemoryCoreSotRepository,
    NotFound,
    SceneNoteTooLong,
)


class _Clock:
    """결정적 시계 — writing/scratch.py 의 clock 주입 관례와 같다."""

    def __init__(self) -> None:
        self._tick = 0

    def __call__(self) -> datetime:
        self._tick += 1
        return datetime(2026, 8, 31, 12, 0, self._tick, tzinfo=UTC)


def _service():
    repo = InMemoryCoreSotRepository()
    return CoreSotService(repo, clock=_Clock()), repo


def _scene(service, *, project_name="Novel", title="Scene 1"):
    project = service.create_project(name=project_name)
    chapter = service.create_chapter(project_id=project.id, title="Chapter 1")
    scene = service.create_scene(
        project_id=project.id, chapter_id=chapter.id, title=title
    )
    return project, chapter, scene


class SceneNoteStorageTest(unittest.TestCase):
    def test_put_creates_the_current_note_and_get_reads_it_back(self):
        service, _repo = _service()
        project, _chapter, scene = _scene(service)

        saved = service.put_scene_note(
            project_id=project.id, draft_id=scene.id, body="첫 메모"
        )

        self.assertIsInstance(saved, SceneNote)
        self.assertEqual(saved.project_id, project.id)
        self.assertEqual(saved.draft_id, scene.id)
        self.assertEqual(saved.body, "첫 메모")
        self.assertEqual(
            service.get_scene_note(project_id=project.id, draft_id=scene.id),
            saved,
        )

    def test_missing_note_reads_as_none_not_an_error(self):
        service, _repo = _service()
        project, _chapter, scene = _scene(service)

        self.assertIsNone(
            service.get_scene_note(project_id=project.id, draft_id=scene.id)
        )

    def test_second_put_replaces_the_body_and_advances_updated_at(self):
        """D4=A: 최신 한 값만 보존한다 — 두 번째 저장이 행을 늘리지 않는다."""

        service, _repo = _service()
        project, _chapter, scene = _scene(service)

        first = service.put_scene_note(
            project_id=project.id, draft_id=scene.id, body="초안"
        )
        second = service.put_scene_note(
            project_id=project.id, draft_id=scene.id, body="고친 메모"
        )

        current = service.get_scene_note(
            project_id=project.id, draft_id=scene.id
        )
        self.assertEqual(current, second)
        self.assertEqual(current.body, "고친 메모")
        self.assertGreater(second.updated_at, first.updated_at)

    def test_empty_body_is_stored_as_an_empty_current_value_not_a_deletion(self):
        """페이즈 Slice 0 계약. 지워지면 '빈 메모'와 '메모 없음'을 구분할 수 없다."""

        service, _repo = _service()
        project, _chapter, scene = _scene(service)
        service.put_scene_note(
            project_id=project.id, draft_id=scene.id, body="쓸 말"
        )

        service.put_scene_note(project_id=project.id, draft_id=scene.id, body="")

        current = service.get_scene_note(
            project_id=project.id, draft_id=scene.id
        )
        self.assertIsNotNone(current)
        self.assertEqual(current.body, "")

    def test_notes_are_per_scene_within_one_project(self):
        service, _repo = _service()
        project, chapter, first = _scene(service)
        second = service.create_scene(
            project_id=project.id, chapter_id=chapter.id, title="Scene 2"
        )

        service.put_scene_note(
            project_id=project.id, draft_id=first.id, body="1번 메모"
        )
        service.put_scene_note(
            project_id=project.id, draft_id=second.id, body="2번 메모"
        )

        self.assertEqual(
            service.get_scene_note(
                project_id=project.id, draft_id=first.id
            ).body,
            "1번 메모",
        )
        self.assertEqual(
            service.get_scene_note(
                project_id=project.id, draft_id=second.id
            ).body,
            "2번 메모",
        )


class SceneNoteBoundaryTest(unittest.TestCase):
    def test_cross_project_draft_id_is_not_found_for_read_and_write(self):
        service, _repo = _service()
        _mine, _chapter, scene = _scene(service, project_name="Mine")
        other = service.create_project(name="Other")

        with self.assertRaises(NotFound):
            service.put_scene_note(
                project_id=other.id, draft_id=scene.id, body="넘겨보기"
            )
        with self.assertRaises(NotFound):
            service.get_scene_note(project_id=other.id, draft_id=scene.id)

    def test_unknown_project_and_unknown_draft_are_not_found(self):
        service, _repo = _service()
        project, _chapter, scene = _scene(service)

        with self.assertRaises(NotFound):
            service.get_scene_note(project_id="missing", draft_id=scene.id)
        with self.assertRaises(NotFound):
            service.put_scene_note(
                project_id="missing", draft_id=scene.id, body="x"
            )
        with self.assertRaises(NotFound):
            service.get_scene_note(project_id=project.id, draft_id="missing")
        with self.assertRaises(NotFound):
            service.put_scene_note(
                project_id=project.id, draft_id="missing", body="x"
            )

    def test_body_at_the_limit_is_accepted(self):
        """과잉 교정 가드: 상한 '이하'가 거절되면 정확히 상한만큼 쓴 메모를 잃는다."""

        service, _repo = _service()
        project, _chapter, scene = _scene(service)

        body = "가" * SCENE_NOTE_MAX_CHARS
        saved = service.put_scene_note(
            project_id=project.id, draft_id=scene.id, body=body
        )

        self.assertEqual(len(saved.body), SCENE_NOTE_MAX_CHARS)

    def test_body_over_the_limit_is_rejected_and_leaves_the_current_note(self):
        service, _repo = _service()
        project, _chapter, scene = _scene(service)
        service.put_scene_note(
            project_id=project.id, draft_id=scene.id, body="지켜질 메모"
        )

        with self.assertRaises(SceneNoteTooLong):
            service.put_scene_note(
                project_id=project.id,
                draft_id=scene.id,
                body="가" * (SCENE_NOTE_MAX_CHARS + 1),
            )

        self.assertEqual(
            service.get_scene_note(
                project_id=project.id, draft_id=scene.id
            ).body,
            "지켜질 메모",
        )


class SceneNoteArchiveTest(unittest.TestCase):
    """archive 는 메모를 파기하지 않는다(결정 브리프 Follow-up).

    쓰기 축은 원고 저장과 같은 경계를 쓴다 — archived project/chapter/scene 은
    `Archived`. 읽기는 막지 않는다(SoT "archive 는 read 를 막지 않는다").
    """

    def test_archived_scene_keeps_the_note_readable_but_blocks_writes(self):
        service, _repo = _service()
        project, _chapter, scene = _scene(service)
        service.put_scene_note(
            project_id=project.id, draft_id=scene.id, body="보관 전 메모"
        )

        service.archive_draft(project_id=project.id, draft_id=scene.id)

        self.assertEqual(
            service.get_scene_note(
                project_id=project.id, draft_id=scene.id
            ).body,
            "보관 전 메모",
        )
        with self.assertRaises(Archived):
            service.put_scene_note(
                project_id=project.id, draft_id=scene.id, body="보관 뒤 메모"
            )

    def test_archived_chapter_and_project_block_writes(self):
        service, _repo = _service()
        project, chapter, scene = _scene(service)
        other_project, _other_chapter, other_scene = _scene(
            service, project_name="Other"
        )

        service.archive_chapter(project_id=project.id, chapter_id=chapter.id)
        with self.assertRaises(Archived):
            service.put_scene_note(
                project_id=project.id, draft_id=scene.id, body="x"
            )

        service.archive_project(project_id=other_project.id)
        with self.assertRaises(Archived):
            service.put_scene_note(
                project_id=other_project.id, draft_id=other_scene.id, body="x"
            )


class SceneNotePurgeTest(unittest.TestCase):
    """파기 수명 — 고아 0(결정 브리프 Follow-up, D5 '부분 삭제는 조용한 고아')."""

    def test_scene_purge_removes_its_note_and_keeps_the_sibling_scene_note(self):
        service, repo = _service()
        project, chapter, victim = _scene(service)
        sibling = service.create_scene(
            project_id=project.id, chapter_id=chapter.id, title="Scene 2"
        )
        service.put_scene_note(
            project_id=project.id, draft_id=victim.id, body="사라질 메모"
        )
        service.put_scene_note(
            project_id=project.id, draft_id=sibling.id, body="남을 메모"
        )

        service.purge_draft(project_id=project.id, draft_id=victim.id)

        # 저장소를 직접 본다 — service 조회는 draft 소멸이 내는 NotFound 에 가려져
        # **메모 행이 고아로 남아도 통과한다**(변이 M1 이 실증).
        self.assertNotIn(
            (project.id, victim.id),
            repo.scene_notes,
            "파기된 장면의 메모가 고아로 남았다",
        )
        with self.assertRaises(NotFound):
            service.get_scene_note(project_id=project.id, draft_id=victim.id)
        self.assertEqual(
            service.get_scene_note(
                project_id=project.id, draft_id=sibling.id
            ).body,
            "남을 메모",
        )

    def test_chapter_purge_cascades_to_child_scene_notes_only(self):
        service, repo = _service()
        project, victim_chapter, victim_scene = _scene(service)
        kept_chapter = service.create_chapter(
            project_id=project.id, title="Chapter 2"
        )
        kept_scene = service.create_scene(
            project_id=project.id, chapter_id=kept_chapter.id, title="Scene 2-1"
        )
        service.put_scene_note(
            project_id=project.id, draft_id=victim_scene.id, body="사라질 메모"
        )
        service.put_scene_note(
            project_id=project.id, draft_id=kept_scene.id, body="남을 메모"
        )

        service.archive_chapter(
            project_id=project.id, chapter_id=victim_chapter.id
        )
        service.purge_chapter(
            project_id=project.id, chapter_id=victim_chapter.id
        )

        # 같은 이유로 저장소를 직접 본다(위 M1 주석).
        self.assertNotIn(
            (project.id, victim_scene.id),
            repo.scene_notes,
            "cascade 로 지워진 장면의 메모가 고아로 남았다",
        )
        with self.assertRaises(NotFound):
            service.get_scene_note(
                project_id=project.id, draft_id=victim_scene.id
            )
        self.assertEqual(
            service.get_scene_note(
                project_id=project.id, draft_id=kept_scene.id
            ).body,
            "남을 메모",
        )

    def test_project_purge_removes_notes_and_leaves_another_project_intact(self):
        service, repo = _service()
        victim, _chapter, victim_scene = _scene(service, project_name="Victim")
        kept, _kept_chapter, kept_scene = _scene(service, project_name="Kept")
        service.put_scene_note(
            project_id=victim.id, draft_id=victim_scene.id, body="사라질 메모"
        )
        service.put_scene_note(
            project_id=kept.id, draft_id=kept_scene.id, body="남을 메모"
        )

        service.purge_project(project_id=victim.id)

        self.assertNotIn(
            (victim.id, victim_scene.id),
            repo.scene_notes,
            "파기된 프로젝트의 메모가 고아로 남았다",
        )
        with self.assertRaises(NotFound):
            service.get_scene_note(
                project_id=victim.id, draft_id=victim_scene.id
            )
        self.assertEqual(
            service.get_scene_note(
                project_id=kept.id, draft_id=kept_scene.id
            ).body,
            "남을 메모",
        )

    def test_purge_leaves_no_residue_in_the_repository(self):
        """저장소 잔류 직접 확인 — service 조회는 project/draft 소멸에 가려진다."""

        service, repo = _service()
        project, _chapter, scene = _scene(service)
        service.put_scene_note(
            project_id=project.id, draft_id=scene.id, body="메모"
        )

        service.purge_project(project_id=project.id)

        self.assertEqual(repo.scene_notes, {})


if __name__ == "__main__":
    unittest.main()
