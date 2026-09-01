"""장면 메모 읽기 API (Slice 1) — HTTP 계약.

`test_scene_notes.py` 가 저장·목록·검색의 **서비스 계약**을 잠근다. 여기는 요청을
실제로 구동해 **응답 모양·미리보기·인가 경계**가 조립에서 성립하는지 본다.

Slice 1 은 읽기 두 경로였고 **Slice 2 가 `PUT …/note` 와 활동 기록을 더했다**.
401/403 전수는 `test_auth_api.py` 의 tier 행렬이 잠그므로 여기서는 세 경로가 그 행렬
안에 있다는 사실(project tier)을 대표 셀로만 확인하고, **grant 읽기와 access-log 한
행**·**활동 행이 남는 조건**처럼 이 표면에서만 물어볼 수 있는 것을 잰다.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from services.application.app.activity.log import (
    ActivityLogService,
    InMemoryActivityLogRepository,
)
from services.application.app.auth.access_grants import (
    AccessGrantService,
    InMemoryAccessGrantRepository,
)
from services.application.app.auth.sessions import (
    InMemorySessionRepository,
    SessionService,
)
from services.application.app.auth.users import InMemoryUserRepository, UserService
from services.application.app.core_sot.models import Draft
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.main import create_app
from services.application.app.core_sot.service import SCENE_NOTE_MAX_CHARS
from services.application.app.routers.notes import (
    SCENE_NOTE_DOUBLE_SUBMIT_WINDOW,
    SCENE_NOTE_PREVIEW_MAX_CHARS,
    build_note_preview,
)


class _FakeHasher:
    def hash(self, password: str) -> str:
        return "H:" + password

    def verify(self, stored_hash: str, password: str) -> bool:
        return stored_hash == "H:" + password


def _client(*, core_sot=None, access_grants=None, activity_repo=None):
    users = UserService(InMemoryUserRepository(), hasher=_FakeHasher())
    sessions = SessionService(InMemorySessionRepository(), ttl=timedelta(hours=1))
    users.create_user(username="alice", password="pw123")
    core = core_sot or CoreSotService(InMemoryCoreSotRepository())
    app = create_app(
        service=core, user_service=users, session_service=sessions,
        access_grant_service=access_grants,
        activity_log_service=(
            ActivityLogService(activity_repo)
            if activity_repo is not None else None
        ),
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


class SceneNoteLegacyMigrationFaceTest(unittest.TestCase):
    """평면 legacy 데이터의 **503** 얼굴 (독립 검증 2026-08-31 차단 조건 폐쇄).

    SoT v1.8.12 는 목록 순서를 `list_drafts` 에서 가져오므로 "평면 legacy 의 503 얼굴도
    함께 온다"고 명문화했다. 그런데 그 분기는 **무셀이었다** — 라우터의
    `DraftOrderIntegrityError → 503` 핸들러를 통째로 지워도 notes 회귀가 전부 통과했다
    (검증자 변이 W5). 그 상태의 실제 동작은 **500** 이다: 처방이 재시도가 아니라
    `scripts/migrate_chapter_scene_hierarchy.py` 라는 사실이 응답에서 사라진다.

    두 상태를 모두 잰다 — 정합 평면(챕터 0개)과 혼합(부분 migration). export·versions 의
    대피 경로(v1.8.10)는 이 표면에 없다: 메모 목록은 `GET /drafts` 와 같은 목록형 읽기라
    같은 503 을 낸다.
    """

    def _app_with(self, *, mixed: bool):
        repo = InMemoryCoreSotRepository()
        service = CoreSotService(repo)
        users = UserService(InMemoryUserRepository(), hasher=_FakeHasher())
        sessions = SessionService(
            InMemorySessionRepository(), ttl=timedelta(hours=1)
        )
        users.create_user(username="alice", password="pw123")
        alice = users._repo.get_by_username("alice")
        project = service.create_project(name="Legacy", owner_id=alice.id)
        if mixed:
            # 부분 migration: 장은 생겼는데 어느 Draft 는 아직 평면이다.
            service.create_chapter(project_id=project.id, title="1장")
            repo.drafts["legacy-1"] = Draft(
                id="legacy-1", project_id=project.id, title="옛 원고"
            )
        else:
            # 정합 평면: 챕터 0개 + ordered unit Draft.
            service.create_draft(project_id=project.id, title="평면 원고")
        app = create_app(
            service=service, user_service=users, session_service=sessions
        )
        client = TestClient(app, base_url="https://testserver")
        client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )
        return client, project.id

    def test_flat_legacy_project_note_list_is_503_not_500(self):
        client, project_id = self._app_with(mixed=False)

        response = client.get(f"/projects/{project_id}/notes")

        self.assertEqual(response.status_code, 503)
        self.assertIn("migration is required", response.json()["detail"])

    def test_mixed_hierarchy_state_note_list_is_503_not_500(self):
        client, project_id = self._app_with(mixed=True)

        response = client.get(f"/projects/{project_id}/notes")

        self.assertEqual(response.status_code, 503)
        self.assertIn("migration is required", response.json()["detail"])

    def test_a_migrated_project_is_not_swept_into_the_503(self):
        """과잉 교정 가드: 정상 계층 프로젝트까지 503 이 되면 목록이 죽는다."""

        repo = InMemoryCoreSotRepository()
        service = CoreSotService(repo)
        users = UserService(InMemoryUserRepository(), hasher=_FakeHasher())
        sessions = SessionService(
            InMemorySessionRepository(), ttl=timedelta(hours=1)
        )
        users.create_user(username="alice", password="pw123")
        alice = users._repo.get_by_username("alice")
        project = service.create_project(name="Novel", owner_id=alice.id)
        chapter = service.create_chapter(project_id=project.id, title="1장")
        service.create_scene(
            project_id=project.id, chapter_id=chapter.id, title="첫 장면"
        )
        client = TestClient(
            create_app(
                service=service, user_service=users, session_service=sessions
            ),
            base_url="https://testserver",
        )
        client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )

        response = client.get(f"/projects/{project.id}/notes")

        self.assertEqual(response.status_code, 200)


class _NoteWriteBase(unittest.TestCase):
    """쓰기 표면의 공통 씨앗. 시계는 주입한다 — 연타 창을 결정적으로 재기 위해서다."""

    def setUp(self) -> None:
        self.now = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
        self.core_sot = CoreSotService(
            InMemoryCoreSotRepository(), clock=lambda: self.now
        )
        self.activity = InMemoryActivityLogRepository()
        self.client, self.users, _ = _client(
            core_sot=self.core_sot, activity_repo=self.activity
        )
        self.client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )
        self.project = self.client.post(
            "/projects", json={"name": "Novel"}
        ).json()["id"]
        self.chapter = self.client.post(
            f"/projects/{self.project}/chapters", json={"title": "1장"}
        ).json()["id"]
        self.scene = self.client.post(
            f"/projects/{self.project}/drafts",
            json={"title": "첫 장면", "chapter_id": self.chapter},
        ).json()["id"]

    def _put(self, body: str, *, project=None, draft=None):
        return self.client.put(
            f"/projects/{project or self.project}/drafts"
            f"/{draft or self.scene}/note",
            json={"body": body},
        )

    def _rows(self):
        return [
            event for event in self.activity.events
            if event.action == "scene_note_saved"
        ]


class SceneNoteWriteApiTest(_NoteWriteBase):
    """`PUT …/note` 의 저장 계약 (Slice 2, D4=A)."""

    def test_a_saved_note_comes_back_and_reads_back_the_same(self):
        response = self._put("첫 메모")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["draft_id"], self.scene)
        self.assertEqual(response.json()["body"], "첫 메모")
        self.assertIsNotNone(response.json()["updated_at"])
        read = self.client.get(
            f"/projects/{self.project}/drafts/{self.scene}/note"
        ).json()
        self.assertEqual(read["body"], "첫 메모")

    def test_a_second_save_replaces_the_value_without_leaving_a_version(self):
        """D4=A: 현재 값 하나뿐이다 — 이전 본문이 어디에도 남지 않는다."""

        self._put("첫 메모")
        self.now += timedelta(minutes=1)

        self._put("고친 메모")

        read = self.client.get(
            f"/projects/{self.project}/drafts/{self.scene}/note"
        ).json()
        self.assertEqual(read["body"], "고친 메모")
        self.assertEqual(
            self.core_sot.get_scene_note(
                project_id=self.project, draft_id=self.scene
            ).body,
            "고친 메모",
        )

    def test_an_empty_body_saves_an_empty_note_rather_than_deleting_the_row(self):
        """빈 본문은 행 삭제가 아니다(SoT v1.8.11) — 읽기가 그 둘을 구분한다."""

        self._put("지울 메모")
        self.now += timedelta(minutes=1)

        response = self._put("")

        self.assertEqual(response.status_code, 200)
        read = self.client.get(
            f"/projects/{self.project}/drafts/{self.scene}/note"
        ).json()
        self.assertEqual(read["body"], "")
        self.assertIsNotNone(read["updated_at"])

    def test_a_body_exactly_at_the_limit_is_accepted(self):
        response = self._put("가" * SCENE_NOTE_MAX_CHARS)

        self.assertEqual(response.status_code, 200)

    def test_a_body_over_the_limit_is_422_and_stores_nothing(self):
        """오너 확정 2026-08-31: 상한 초과의 얼굴은 **422** 다.

        원고 본문 상한(`SaveDraftRequest.enforce_raw_text_limit`)과 같은 관례 —
        요청 모델의 `field_validator` 라 handler 진입 **전**에 난다. 그래서
        아무것도 저장되지 않는다.
        """

        response = self._put("가" * (SCENE_NOTE_MAX_CHARS + 1))

        self.assertEqual(response.status_code, 422)
        self.assertIsNone(
            self.core_sot.get_scene_note(
                project_id=self.project, draft_id=self.scene
            )
        )

    def test_the_length_check_runs_before_the_archive_check(self):
        """검증 hardening #2 의 순서를 HTTP 에서 고정한다.

        보관된 장면에 상한 초과 본문을 보내면 **409 가 아니라 422** 다 —
        pydantic 검증이 handler 앞에 있기 때문이며, 서비스의 검사 순서
        (`put_scene_note` 가 길이를 먼저 본다)와 같은 방향이다.
        """

        self.core_sot.archive_draft(
            project_id=self.project, draft_id=self.scene
        )

        response = self._put("가" * (SCENE_NOTE_MAX_CHARS + 1))

        self.assertEqual(response.status_code, 422)

    def test_writing_to_an_archived_scene_is_409(self):
        self.core_sot.archive_draft(
            project_id=self.project, draft_id=self.scene
        )

        self.assertEqual(self._put("메모").status_code, 409)

    def test_writing_under_an_archived_chapter_is_409(self):
        """장 보관은 자식 Scene 의 `archived` 를 안 바꾸지만 쓰기는 막는다."""

        self.core_sot.archive_chapter(
            project_id=self.project, chapter_id=self.chapter
        )

        self.assertEqual(self._put("메모").status_code, 409)

    def test_writing_to_an_archived_project_is_409(self):
        self.core_sot.archive_project(project_id=self.project)

        self.assertEqual(self._put("메모").status_code, 409)

    def test_a_scene_from_another_project_is_404(self):
        other = self.client.post("/projects", json={"name": "Other"}).json()["id"]

        self.assertEqual(self._put("메모", project=other).status_code, 404)

    def test_a_missing_scene_is_404(self):
        self.assertEqual(self._put("메모", draft="nope").status_code, 404)

    def test_a_missing_project_is_404(self):
        self.assertEqual(
            self._put("메모", project="does-not-exist").status_code, 404
        )


class SceneNoteLiteralTest(unittest.TestCase):
    def test_the_owner_approved_double_submit_window_is_five_seconds(self):
        """SoT v1.8.13·오너 2026-08-31: 연타 창은 5초로 고정한다.

        under-strict: 창 리터럴 드리프트가 이 셀을 문다.
        over-strict: 정확히 창 경계의 재저장은 아래 셀이 다시 기록함을 잰다.
        """

        self.assertEqual(
            SCENE_NOTE_DOUBLE_SUBMIT_WINDOW, timedelta(seconds=5)
        )


class SceneNoteWriteActivityTest(_NoteWriteBase):
    """`scene_note_saved` 가 남는 조건 (D4=A · 오너 2026-08-31 연타 억제)."""

    def test_a_successful_save_records_exactly_one_row(self):
        self._put("첫 메모")

        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].project_id, self.project)
        self.assertEqual(rows[0].target_type, "scene_note")
        self.assertEqual(rows[0].target_id, self.scene)

    def test_the_row_names_the_actor_not_the_owner_field(self):
        """행위자는 세션 사용자다.

        이 PUT 경로는 소유자만 쓸 수 있어 현재는 두 ID가 구조적으로 같다. 따라서
        이 셀은 세션 사용자의 ID가 행에 든다는 현재 응답 사실만 잠근다.
        """

        self._put("첫 메모")

        alice = self.users._repo.get_by_username("alice")
        self.assertEqual(self._rows()[0].actor_user_id, alice.id)

    def test_the_note_body_never_rides_into_the_activity_row(self):
        """A3=B: `before`/`after` 는 **라벨**이다. 12000자 본문이 들어갈 자리가 아니다."""

        self._put("아주 사적인 메모")

        row = self._rows()[0]
        self.assertIsNone(row.before)
        self.assertIsNone(row.after)

    def test_a_rejected_save_records_nothing(self):
        """404·409·422 셋 다 — 실패가 타임라인에 저장으로 보이면 안 된다."""

        self.core_sot.archive_draft(
            project_id=self.project, draft_id=self.scene
        )
        cases = {
            409: self._put("메모"),
            404: self._put("메모", draft="nope"),
            422: self._put("가" * (SCENE_NOTE_MAX_CHARS + 1)),
        }

        for expected, response in cases.items():
            with self.subTest(status=expected):
                self.assertEqual(response.status_code, expected)
        self.assertEqual(self._rows(), [])

    def test_a_deliberate_re_save_of_the_same_body_records_again(self):
        """오너 확정 2026-08-31: 같은 값을 **다시** 저장해도 한 행이다.

        D4=A 의 "명시적 저장"은 값 비교가 아니라 사용자의 저장 행위를 센다.
        연타 창(아래)만 예외이며, 그 창을 지나면 다시 남는다.
        """

        self._put("같은 메모")
        self.now += SCENE_NOTE_DOUBLE_SUBMIT_WINDOW

        self._put("같은 메모")

        self.assertEqual(len(self._rows()), 2)

    def test_a_double_submit_of_the_same_body_records_once(self):
        """저장 버튼 연타(오너 2026-08-31). 창 안의 **같은 값** 재전송은 한 행이다."""

        self._put("같은 메모")
        self.now += timedelta(milliseconds=200)

        self._put("같은 메모")
        self._put("같은 메모")

        self.assertEqual(len(self._rows()), 1)

    def test_a_changed_body_inside_the_window_still_records(self):
        """over-strict 가드 — 억제 조건에서 **값 비교**를 빼면 이 셀이 문다.

        시간만 보는 과잉 교정은 빠르게 고쳐 다시 저장한 진짜 편집을 삼킨다.
        """

        self._put("첫 메모")
        self.now += timedelta(milliseconds=200)

        self._put("고친 메모")

        self.assertEqual(len(self._rows()), 2)

    def test_the_window_is_measured_per_scene(self):
        """다른 장면의 저장은 서로의 창에 걸리지 않는다."""

        second = self.client.post(
            f"/projects/{self.project}/drafts",
            json={"title": "둘째 장면", "chapter_id": self.chapter},
        ).json()["id"]

        self._put("같은 메모")
        self._put("같은 메모", draft=second)

        self.assertEqual(len(self._rows()), 2)

    def test_the_suppressed_save_still_persists_the_value(self):
        """억제되는 것은 **활동 행뿐**이다 — 저장 자체는 언제나 일어난다."""

        self._put("같은 메모")
        self.now += timedelta(milliseconds=200)

        response = self._put("같은 메모")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.core_sot.get_scene_note(
                project_id=self.project, draft_id=self.scene
            ).updated_at,
            self.now,
        )


class SceneNoteWriteAuthorizationTest(unittest.TestCase):
    """D3=A: grant 는 끝까지 읽기 전용이다."""

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
        self.path = f"/projects/{self.project}/drafts/{self.scene}/note"

    def test_a_sessionless_write_is_401(self):
        self.assertEqual(
            self.client.put(self.path, json={"body": "메모"}).status_code, 401
        )

    def test_a_live_grant_does_not_open_the_write(self):
        """`_GRANTED_METHODS` 가 GET/HEAD 뿐이라 PUT 은 grant 가 살아 있어도 403 이다."""

        self.client.post(
            "/auth/login", json={"username": "root", "password": "pw789"}
        )
        self.client.post(
            f"/admin/projects/{self.project}/access-grants",
            json={"reason": "지원 요청 #12 확인"},
        )

        self.assertEqual(self.client.get(self.path).status_code, 200)
        self.assertEqual(
            self.client.put(self.path, json={"body": "메모"}).status_code, 403
        )
        self.assertIsNone(
            self.core_sot.get_scene_note(
                project_id=self.project, draft_id=self.scene
            )
        )


class NotePreviewTest(unittest.TestCase):
    """미리보기 헬퍼의 경계 — 라우터를 거치지 않고 직접 잰다."""

    def test_the_owner_approved_preview_limit_literal_is_200_characters(self):
        """SoT v1.8.12·오너 2026-08-31: 미리보기 예산은 200자로 고정한다.

        under-strict: 예산 리터럴 드리프트가 이 셀을 문다.
        over-strict: 정확히 200자는 아래 경계 셀이 자르지 않음을 잰다.
        """

        self.assertEqual(SCENE_NOTE_PREVIEW_MAX_CHARS, 200)

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

    def test_a_padded_query_still_centers_the_snippet(self):
        """검증자 변이 W2: 필터와 스니펫 탐색의 `strip()` 대칭이 무가드였다.

        서비스 필터는 query 를 strip 해서 행을 올리는데 스니펫 탐색이 strip 하지 않으면,
        공백이 붙은 검색어에서 **목록에는 뜨는데 미리보기는 머리 200자**가 된다 — 검색
        연계가 조용히 꺼진 상태다.
        """

        body = "앞" * 500 + "표적" + "뒤" * 500

        preview, _truncated = build_note_preview(body, "  표적  ")

        self.assertIn("표적", preview)
        self.assertTrue(preview.startswith("…"))

    def test_the_window_never_exceeds_the_budget(self):
        body = "앞" * 500 + "표적" + "뒤" * 500

        preview, _truncated = build_note_preview(body, "표적")

        self.assertEqual(
            len(preview.strip("…")), SCENE_NOTE_PREVIEW_MAX_CHARS
        )


if __name__ == "__main__":
    unittest.main()
