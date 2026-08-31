"""장면 메모 읽기 API (Slice 1) — HTTP 계약.

`test_scene_notes.py` 가 저장·목록·검색의 **서비스 계약**을 잠근다. 여기는 요청을
실제로 구동해 **응답 모양·미리보기·인가 경계**가 조립에서 성립하는지 본다.

이 slice 는 읽기 전용이다 — 쓰기 route 도 활동 기록도 없다. 401/403 전수는
`test_auth_api.py` 의 tier 행렬이 잠그므로 여기서는 이 두 경로가 그 행렬 안에
있다는 사실(project tier)을 대표 셀로만 확인하고, **grant 읽기와 access-log 한 행**
처럼 이 표면에서만 물어볼 수 있는 것을 잰다.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from services.application.app.auth.access_grants import (
    AccessGrantService,
    InMemoryAccessGrantRepository,
)
from services.application.app.auth.sessions import (
    InMemorySessionRepository,
    SessionService,
)
from services.application.app.auth.users import InMemoryUserRepository, UserService
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.main import create_app
from services.application.app.routers.notes import (
    SCENE_NOTE_PREVIEW_MAX_CHARS,
    build_note_preview,
)


class _FakeHasher:
    def hash(self, password: str) -> str:
        return "H:" + password

    def verify(self, stored_hash: str, password: str) -> bool:
        return stored_hash == "H:" + password


def _client(*, core_sot=None, access_grants=None):
    users = UserService(InMemoryUserRepository(), hasher=_FakeHasher())
    sessions = SessionService(InMemorySessionRepository(), ttl=timedelta(hours=1))
    users.create_user(username="alice", password="pw123")
    core = core_sot or CoreSotService(InMemoryCoreSotRepository())
    app = create_app(
        service=core, user_service=users, session_service=sessions,
        access_grant_service=access_grants,
    )
    client = TestClient(app, base_url="https://testserver")
    return client, users, core


class _NoteApiBase(unittest.TestCase):
    def setUp(self) -> None:
        self.client, self.users, self.core_sot = _client()
        self.client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )
        self.project = self.client.post(
            "/projects", json={"name": "Novel"}
        ).json()["id"]

    def _chapter(self, title: str) -> str:
        return self.client.post(
            f"/projects/{self.project}/chapters", json={"title": title}
        ).json()["id"]

    def _scene(self, chapter_id: str, title: str) -> str:
        return self.client.post(
            f"/projects/{self.project}/drafts",
            json={"title": title, "chapter_id": chapter_id},
        ).json()["id"]

    def _put_note(self, draft_id: str, body: str) -> None:
        # Slice 2 전이라 쓰기 route 가 없다 — 서비스로 직접 넣는다. 이 파일이 재는
        # 것은 읽기 표면이고, 쓰기 표면이 생기면 그쪽 셀이 잠근다.
        self.core_sot.put_scene_note(
            project_id=self.project, draft_id=draft_id, body=body
        )


class SceneNoteListApiTest(_NoteApiBase):
    def setUp(self) -> None:
        super().setUp()
        first = self._chapter("1장 만남")
        second = self._chapter("2장 이별")
        self.alley = self._scene(first, "여름 골목")
        self.rain = self._scene(first, "빗속")
        self.station = self._scene(second, "역 앞")

    def test_list_rows_are_ordered_and_carry_scene_and_chapter_labels(self):
        self._put_note(self.station, "역 메모")
        self._put_note(self.alley, "골목 메모")

        response = self.client.get(f"/projects/{self.project}/notes")

        self.assertEqual(response.status_code, 200)
        notes = response.json()["notes"]
        self.assertEqual(
            [(n["scene_title"], n["chapter_title"]) for n in notes],
            [("여름 골목", "1장 만남"), ("역 앞", "2장 이별")],
        )
        self.assertEqual(notes[0]["draft_id"], self.alley)
        self.assertEqual(notes[0]["body_preview"], "골목 메모")
        self.assertFalse(notes[0]["truncated"])
        self.assertIsNotNone(notes[0]["updated_at"])

    def test_query_is_applied_on_the_server(self):
        self._put_note(self.alley, "여기엔 없는 말")
        self._put_note(self.rain, "우산을 놓고 온다")

        response = self.client.get(
            f"/projects/{self.project}/notes", params={"query": "우산"}
        )

        self.assertEqual(
            [n["scene_title"] for n in response.json()["notes"]], ["빗속"]
        )

    def test_no_match_is_an_empty_list_with_200(self):
        self._put_note(self.alley, "본문")

        response = self.client.get(
            f"/projects/{self.project}/notes", params={"query": "없는말"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["notes"], [])

    def test_long_body_is_truncated_in_the_list_but_whole_in_the_single_read(self):
        """목록이 전문을 실으면 12000자 × 장면 수가 그대로 응답이 된다."""

        body = "가" * 5000
        self._put_note(self.alley, body)

        listed = self.client.get(
            f"/projects/{self.project}/notes"
        ).json()["notes"][0]
        single = self.client.get(
            f"/projects/{self.project}/drafts/{self.alley}/note"
        ).json()

        self.assertLess(len(listed["body_preview"]), len(body))
        self.assertTrue(listed["truncated"])
        self.assertEqual(single["body"], body)

    def test_preview_centers_on_the_match_so_the_reader_sees_why_it_matched(self):
        """오너 2026-08-31: 미리보기를 검색과 연계한다.

        머리 200자만 주면 8000번째 글자에서 매치된 메모는 "왜 나왔는지"가 안 보인다.
        """

        body = "앞" * 4000 + "열쇠는 우물 안" + "뒤" * 4000
        self._put_note(self.alley, body)

        listed = self.client.get(
            f"/projects/{self.project}/notes", params={"query": "열쇠"}
        ).json()["notes"][0]

        self.assertIn("열쇠는 우물 안", listed["body_preview"])
        self.assertTrue(listed["truncated"])
        # 창이 본문 중간이라 양쪽에 잘림 표식이 붙는다.
        self.assertTrue(listed["body_preview"].startswith("…"))
        self.assertTrue(listed["body_preview"].endswith("…"))

    def test_archived_scene_and_chapter_stay_listed_with_their_flags(self):
        self._put_note(self.alley, "본문")
        self._put_note(self.station, "본문")
        self.client.delete(f"/projects/{self.project}/drafts/{self.alley}")
        chapter_id = self.client.get(
            f"/projects/{self.project}/notes"
        ).json()["notes"][1]["chapter_id"]
        self.client.post(
            f"/projects/{self.project}/chapters/{chapter_id}/archive"
        )

        notes = self.client.get(
            f"/projects/{self.project}/notes"
        ).json()["notes"]

        self.assertEqual(len(notes), 2)
        self.assertTrue(notes[0]["scene_archived"])
        self.assertFalse(notes[0]["chapter_archived"])
        self.assertFalse(notes[1]["scene_archived"])
        self.assertTrue(notes[1]["chapter_archived"])


class SceneNoteSingleReadApiTest(_NoteApiBase):
    def setUp(self) -> None:
        super().setUp()
        self.chapter = self._chapter("1장")
        self.scene = self._scene(self.chapter, "첫 장면")

    def test_a_scene_without_a_note_reads_as_null_body_not_404(self):
        """드로어가 메모 없는 장면을 열 때마다 오류를 받으면 안 된다."""

        response = self.client.get(
            f"/projects/{self.project}/drafts/{self.scene}/note"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"draft_id": self.scene, "body": None, "updated_at": None},
        )

    def test_an_empty_note_is_distinguishable_from_no_note(self):
        """저장 계약이 그 둘을 구분하므로 읽기 표면도 구분해야 한다."""

        self._put_note(self.scene, "")

        payload = self.client.get(
            f"/projects/{self.project}/drafts/{self.scene}/note"
        ).json()

        self.assertEqual(payload["body"], "")
        self.assertIsNotNone(payload["updated_at"])

    def test_a_scene_from_another_project_is_404(self):
        other = self.client.post("/projects", json={"name": "Other"}).json()["id"]

        response = self.client.get(
            f"/projects/{other}/drafts/{self.scene}/note"
        )

        self.assertEqual(response.status_code, 404)

    def test_a_missing_project_is_404_on_both_routes(self):
        for path in (
            "/projects/does-not-exist/notes",
            f"/projects/does-not-exist/drafts/{self.scene}/note",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)


class SceneNoteAuthorizationTest(unittest.TestCase):
    """소유자·grant 읽기 경계. 401/403 전수는 tier 행렬이 따로 잠근다."""

    def setUp(self) -> None:
        self.now = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
        self.core_sot = CoreSotService(InMemoryCoreSotRepository())
        self.grants = AccessGrantService(
            InMemoryAccessGrantRepository(), clock=lambda: self.now
        )
        self.client, self.users, _ = _client(
            core_sot=self.core_sot, access_grants=self.grants
        )
        self.users.create_user(username="root", password="pw789", is_admin=True)
        alice = self.users._repo.get_by_username("alice")
        self.project = self.core_sot.create_project(
            name="Novel", owner_id=alice.id
        ).id
        chapter = self.core_sot.create_chapter(
            project_id=self.project, title="1장"
        )
        self.scene = self.core_sot.create_scene(
            project_id=self.project, chapter_id=chapter.id, title="첫 장면"
        ).id
        self.core_sot.put_scene_note(
            project_id=self.project, draft_id=self.scene, body="비밀 메모"
        )

    def _paths(self) -> tuple[str, ...]:
        return (
            f"/projects/{self.project}/notes",
            f"/projects/{self.project}/drafts/{self.scene}/note",
        )

    def test_sessionless_reads_are_401(self):
        for path in self._paths():
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)

    def test_a_non_owner_without_a_grant_is_403(self):
        self.client.post(
            "/auth/login", json={"username": "root", "password": "pw789"}
        )
        for path in self._paths():
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)

    def test_a_live_grant_opens_the_reads_and_records_one_access_log_row(self):
        """D3=A: grant 는 읽기만 열고, 그 열람은 감사에 남는다."""

        self.client.post(
            "/auth/login", json={"username": "root", "password": "pw789"}
        )
        self.client.post(
            f"/admin/projects/{self.project}/access-grants",
            json={"reason": "지원 요청 #12 확인"},
        )

        before = len(self.grants.uses_for_project(project_id=self.project))
        listed = self.client.get(f"/projects/{self.project}/notes")
        single = self.client.get(
            f"/projects/{self.project}/drafts/{self.scene}/note"
        )
        uses = self.grants.uses_for_project(project_id=self.project)

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(single.status_code, 200)
        self.assertEqual(single.json()["body"], "비밀 메모")
        self.assertEqual(len(uses) - before, 2)
        # uses_for_project 는 최신 우선이라 앞 두 건이 방금의 읽기다.
        self.assertEqual({use.path for use in uses[:2]}, set(self._paths()))
        self.assertEqual({use.method for use in uses[:2]}, {"GET"})


class NotePreviewTest(unittest.TestCase):
    """미리보기 헬퍼의 경계 — 라우터를 거치지 않고 직접 잰다."""

    def test_a_short_body_is_returned_whole_without_an_ellipsis(self):
        preview, truncated = build_note_preview("짧은 메모", None)

        self.assertEqual(preview, "짧은 메모")
        self.assertFalse(truncated)

    def test_a_body_exactly_at_the_limit_is_not_truncated(self):
        body = "가" * SCENE_NOTE_PREVIEW_MAX_CHARS

        preview, truncated = build_note_preview(body, None)

        self.assertEqual(preview, body)
        self.assertFalse(truncated)

    def test_without_a_query_the_preview_is_the_head_of_the_body(self):
        body = "머리" + "가" * 1000

        preview, truncated = build_note_preview(body, None)

        self.assertTrue(preview.startswith("머리"))
        self.assertTrue(preview.endswith("…"))
        self.assertTrue(truncated)

    def test_a_query_that_only_matched_the_title_still_gets_the_head(self):
        """제목만 매치된 행은 본문에 검색어가 없다 — 머리로 떨어져야 한다."""

        body = "머리" + "가" * 1000

        preview, _truncated = build_note_preview(body, "제목에만")

        self.assertTrue(preview.startswith("머리"))
        self.assertFalse(preview.startswith("…"))

    def test_a_match_near_the_end_does_not_waste_half_the_window(self):
        """창을 왼쪽으로 밀지 않으면 예산의 절반이 빈 채로 낭비된다."""

        body = "가" * 1000 + "끝말"

        preview, _truncated = build_note_preview(body, "끝말")

        self.assertIn("끝말", preview)
        self.assertTrue(preview.endswith("끝말"))
        self.assertEqual(
            len(preview), SCENE_NOTE_PREVIEW_MAX_CHARS + len("…")
        )

    def test_the_window_never_exceeds_the_budget(self):
        body = "앞" * 500 + "표적" + "뒤" * 500

        preview, _truncated = build_note_preview(body, "표적")

        self.assertEqual(
            len(preview.strip("…")), SCENE_NOTE_PREVIEW_MAX_CHARS
        )


if __name__ == "__main__":
    unittest.main()
