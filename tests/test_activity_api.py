"""Phase 9 Slice 9.0 — 활동 로그의 HTTP 계약 (A5=B·A7=A·A4=A·I1).

`test_activity_log.py` 가 저장 계약을, `test_activity_actions.py` 가 "어느 경로가
기록하는가"를 잠근다. 여기는 **요청을 실제로 구동해** 그 셋이 배포 조립에서 함께
성립하는지 본다.

**★ 이 파일의 핵심 두 셀**:

- `test_a_conflicting_request_leaves_no_trace` — A7=A 를 고른 이유 그 자체다. 기록이
  결과보다 앞서면(handler 맨 앞이든 dependency 든) 409 로 끝난 요청이 "했다"로 남는다.
  **404 짝은 순서를 잠그지 않는다**(그쪽은 dependency 가 먼저 낸다 — 각 셀 docstring).
- `test_a_broken_activity_store_does_not_break_the_request` — A4=A. 로그 저장소가
  죽어도 사용자의 저장은 성공한다. 반대 방향(파기 실패는 삼키지 않는다)은
  `test_activity_log.py` 가 잰다.
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from fastapi.testclient import TestClient

from services.application.app.activity.log import (
    ActivityLogService,
    InMemoryActivityLogRepository,
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


class _FakeHasher:
    def hash(self, password: str) -> str:
        return "H:" + password

    def verify(self, stored_hash: str, password: str) -> bool:
        return stored_hash == "H:" + password


class _ExplodingRepository(InMemoryActivityLogRepository):
    def insert(self, event) -> None:
        raise RuntimeError("activity store is down")


def _client(*, activity_repo=None, core_sot=None):
    users = UserService(InMemoryUserRepository(), hasher=_FakeHasher())
    sessions = SessionService(InMemorySessionRepository(), ttl=timedelta(hours=1))
    users.create_user(username="alice", password="pw123")
    repo = activity_repo if activity_repo is not None else InMemoryActivityLogRepository()
    core = core_sot or CoreSotService(InMemoryCoreSotRepository())
    app = create_app(
        service=core, user_service=users, session_service=sessions,
        activity_log_service=ActivityLogService(repo),
    )
    client = TestClient(app, base_url="https://testserver")
    client.post("/auth/login", json={"username": "alice", "password": "pw123"})
    return client, repo, core


class ActivityRecordingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client, self.repo, self.core_sot = _client()

    def _create_project(self, name: str = "첫 장편") -> str:
        return self.client.post("/projects", json={"name": name}).json()["id"]

    def test_creating_a_project_records_the_actor_and_the_name(self) -> None:
        project_id = self._create_project()

        event = self.repo.events[-1]
        self.assertEqual(event.action, "project_created")
        self.assertEqual(event.project_id, project_id)
        self.assertEqual(event.target_id, project_id)
        self.assertEqual(event.after, "첫 장편")
        self.assertTrue(event.actor_user_id)

    def test_renaming_records_both_the_old_and_the_new_name(self) -> None:
        """★ 이 슬라이스의 발원 — 개명은 덮어쓰기라 흔적이 **전혀** 없었다."""
        project_id = self._create_project("옛 이름")

        self.client.patch(f"/projects/{project_id}", json={"name": "새 이름"})

        event = self.repo.events[-1]
        self.assertEqual(event.action, "project_renamed")
        self.assertEqual((event.before, event.after), ("옛 이름", "새 이름"))

    def test_saving_a_draft_version_records_who_and_when(self) -> None:
        """`draft_versions` 에는 `created_at` 도 `user_id` 도 없다(부모 계획 §1)."""
        project_id = self._create_project()
        draft_id = self.client.post(
            f"/projects/{project_id}/drafts",
            json={"title": "1장", "unit_kind": "chapter"},
        ).json()["id"]

        response = self.client.post(
            f"/projects/{project_id}/drafts/{draft_id}/versions",
            json={"raw_text": "본문", "idempotency_key": "k1"},
        )

        self.assertEqual(response.status_code, 200)
        event = self.repo.events[-1]
        self.assertEqual(event.action, "draft_version_saved")
        self.assertEqual(event.target_type, "draft_version")
        self.assertIsNotNone(event.at.tzinfo)

    def test_archiving_records_the_state_change(self) -> None:
        project_id = self._create_project()

        self.client.delete(f"/projects/{project_id}")

        event = self.repo.events[-1]
        self.assertEqual(event.action, "project_archived")
        self.assertEqual((event.before, event.after), ("active", "archived"))

    def test_a_failed_request_leaves_no_trace(self) -> None:
        """없는 프로젝트를 고치려는 요청은 흔적을 안 남긴다.

        ★ **이 셀은 순서를 잠그지 않는다**(뮤테이션 N2 실측). 없는 project 의 404 는
        `require_project_owner` **dependency** 가 내므로 handler 본문이 아예 안 돈다 —
        기록을 handler 맨 앞으로 옮겨도 여기는 통과한다. 순서를 실제로 잠그는 것은
        아래 409 셀이고, 두 셀을 함께 읽어야 A7=A 가 덮인다. 그래도 이 셀을 남기는
        이유는 반대 방향이다: 기록을 **dependency 로** 옮기면(A7 의 B안) 그때는
        여기가 문다.
        """
        before = len(self.repo.events)

        missing = self.client.patch("/projects/does-not-exist", json={"name": "x"})

        self.assertEqual(missing.status_code, 404)
        self.assertEqual(len(self.repo.events), before)

    def test_a_conflicting_request_leaves_no_trace(self) -> None:
        """같은 방향의 409 — archive 된 프로젝트는 개명되지 않는다."""
        project_id = self._create_project()
        self.client.delete(f"/projects/{project_id}")
        before = len(self.repo.events)

        conflict = self.client.patch(
            f"/projects/{project_id}", json={"name": "새 이름"}
        )

        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(len(self.repo.events), before)

    def test_a_broken_activity_store_does_not_break_the_request(self) -> None:
        """★ A4=A — 로그 저장소가 죽어도 원고는 저장된다.

        over-strict 방향이기도 하다: 여기를 fail-closed 로 바꾸면(B안) 이 셀이
        503 을 보고 실패한다. 활동 로그는 보안 하중을 지지 않으므로 그 대가를
        정당화할 근거가 없다 — `access_grant_uses` 와 정반대인 이유가 그것이다.
        """
        client, _repo, _core = _client(activity_repo=_ExplodingRepository())

        response = client.post("/projects", json={"name": "첫 장편"})

        self.assertEqual(response.status_code, 200)


class ActivityQueryTest(unittest.TestCase):
    """A5=B — `GET /projects/{id}/activity`(operation 77).

    미인증 401·비소유자 403 은 `CombinedBoundaryMatrixTest` 가 project tier 전수로
    잠근다(이 operation 도 그 62 에 든다). 여기는 성공 동작만 본다.
    """

    def setUp(self) -> None:
        self.client, self.repo, _core = _client()

    def test_the_owner_reads_their_projects_activity_newest_first(self) -> None:
        project_id = self.client.post(
            "/projects", json={"name": "첫 장편"}
        ).json()["id"]
        self.client.patch(f"/projects/{project_id}", json={"name": "둘째 이름"})

        response = self.client.get(f"/projects/{project_id}/activity")

        self.assertEqual(response.status_code, 200)
        actions = [event["action"] for event in response.json()["events"]]
        self.assertEqual(actions, ["project_renamed", "project_created"])

    def test_the_response_carries_the_value_change(self) -> None:
        project_id = self.client.post(
            "/projects", json={"name": "옛 이름"}
        ).json()["id"]
        self.client.patch(f"/projects/{project_id}", json={"name": "새 이름"})

        event = self.client.get(
            f"/projects/{project_id}/activity"
        ).json()["events"][0]

        self.assertEqual(event["before"], "옛 이름")
        self.assertEqual(event["after"], "새 이름")

    def test_an_unknown_project_is_404(self) -> None:
        self.assertEqual(
            self.client.get("/projects/does-not-exist/activity").status_code, 404
        )

    def test_the_log_does_not_leak_another_projects_events(self) -> None:
        """I4 — `project_id` 격리는 다른 모든 저장소와 동일하게 강제된다."""
        mine = self.client.post("/projects", json={"name": "내 것"}).json()["id"]
        other = self.client.post("/projects", json={"name": "남의 것"}).json()["id"]
        self.client.patch(f"/projects/{other}", json={"name": "남이 고침"})

        events = self.client.get(f"/projects/{mine}/activity").json()["events"]

        self.assertEqual([event["action"] for event in events], ["project_created"])


class PersonalActivityQueryTest(unittest.TestCase):
    """Slice 9.2 P1=ⓐ — `GET /me/activity`(operation 78, 인증 전용 tier).

    **P8=ⓐ 소유 기준이다.** 이 화면이 답하는 질문은 *"내 것들에 무슨 일이 있었나"* 이므로
    범위는 **내가 소유한 프로젝트**이지 *"내가 행위자인 이벤트"* 가 아니다. **오너 확정
    (2026-08-10): 다중 사용자가 되어도 이 범위는 유지되고, 그때 바뀌는 것은 범위가 아니라
    표시다**(F4 = 행위자 열을 켠다). 지금은 관리자=오너(1인)라 두 기준이 같은 결과를 내므로
    **아래 격리 셀이 그 구분을 지키는 유일한 자리**다.

    **S-3**: 이 endpoint 는 **project id 를 받지 않는다** — 주체는 세션에서만 유도한다.
    미인증 401 은 `CombinedBoundaryMatrixTest` 가 tier 전수로 잠근다.
    """

    def setUp(self) -> None:
        self.client, self.repo, self.core = _client()

    def _second_user_client(self) -> TestClient:
        """같은 앱에 다른 회원으로 로그인한 클라이언트."""
        app = self.client.app
        app.state.users.create_user(username="bob", password="pw456")
        other = TestClient(app, base_url="https://testserver")
        other.post("/auth/login", json={"username": "bob", "password": "pw456"})
        return other

    def test_it_merges_every_owned_project_newest_first(self) -> None:
        first = self.client.post("/projects", json={"name": "첫 장편"}).json()["id"]
        second = self.client.post("/projects", json={"name": "둘째 장편"}).json()["id"]
        self.client.patch(f"/projects/{first}", json={"name": "첫 장편 개정"})

        response = self.client.get("/me/activity")

        self.assertEqual(response.status_code, 200)
        events = response.json()["events"]
        # 최신순: first 개명 → second 생성 → first 생성
        self.assertEqual(
            [event["action"] for event in events],
            ["project_renamed", "project_created", "project_created"],
        )
        self.assertEqual(
            {event["project_id"] for event in events}, {first, second}
        )

    def test_it_never_shows_another_members_project(self) -> None:
        """★ P8 소유 기준의 경계 — 남의 프로젝트는 한 행도 새지 않는다."""
        mine = self.client.post("/projects", json={"name": "내 것"}).json()["id"]
        other_client = self._second_user_client()
        theirs = other_client.post(
            "/projects", json={"name": "남의 것"}
        ).json()["id"]

        mine_events = self.client.get("/me/activity").json()["events"]
        their_events = other_client.get("/me/activity").json()["events"]

        self.assertEqual({e["project_id"] for e in mine_events}, {mine})
        self.assertEqual({e["project_id"] for e in their_events}, {theirs})

    def test_a_member_without_projects_gets_an_empty_log(self) -> None:
        """프로젝트가 없으면 저장소를 묻지 않고 빈 목록이다(빈 `$in` 을 안 만든다)."""
        response = self.client.get("/me/activity")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["events"], [])

    def test_each_row_names_its_project_so_the_hub_can_group_them(self) -> None:
        """통합 화면은 행이 **어느 프로젝트의 것인지** 말할 수 있어야 한다.

        project-scoped 응답에는 `project_id` 가 없다(주소가 이미 말한다). 통합에서는
        그것이 사라지면 행을 해석할 수 없으므로 **이 tier 에서만 필드가 하나 는다**.
        """
        project_id = self.client.post("/projects", json={"name": "한 편"}).json()["id"]

        event = self.client.get("/me/activity").json()["events"][0]

        self.assertEqual(event["project_id"], project_id)
        # project-scoped 쪽은 그대로 — 계약을 넓히지 않았다.
        scoped = self.client.get(
            f"/projects/{project_id}/activity"
        ).json()["events"][0]
        self.assertNotIn("project_id", scoped)


class ActivityPurgeTest(unittest.TestCase):
    """★ I1·I2 — 프로젝트를 파기하면 활동 로그도 사라진다.

    이것을 살려 두면 개명 이력·제목·저장 이벤트 전체가 삭제 예외로 승격돼 D8-6 이
    무너진다. 실 Mongo 에서 reconciler 가 같은 방향을 재는 셀은
    `tests/test_purge_reconciler.py` 에 있다.
    """

    def test_purging_a_project_removes_its_activity(self) -> None:
        repo = InMemoryActivityLogRepository()
        users = UserService(InMemoryUserRepository(), hasher=_FakeHasher())
        sessions = SessionService(InMemorySessionRepository(), ttl=timedelta(hours=1))
        users.create_user(username="root", password="pw789", is_admin=True)
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        app = create_app(
            service=core_sot, user_service=users, session_service=sessions,
            activity_log_service=ActivityLogService(repo),
        )
        client = TestClient(app, base_url="https://testserver")
        client.post("/auth/login", json={"username": "root", "password": "pw789"})
        project_id = client.post("/projects", json={"name": "첫 장편"}).json()["id"]
        client.delete(f"/projects/{project_id}")
        self.assertTrue(repo.events)

        response = client.post(
            f"/admin/projects/{project_id}/purge", json={"reason": "정리 요청"}
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(repo.events, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
