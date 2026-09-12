"""관리자 계정 잔여 정리 (계정 탈퇴 Slice 4b, 오너 2026-09-12 ①ⓐ·②ⓐ·③ⓐ).

브리프 ``plans/slice4b-admin-residual-purge-decisions.md``. 여기서 잠그는 것:

1. **조사는 dry-run** — 파괴가 없다(②ⓐ). 대상 계약(404 없음·409 파기 미시작)은
   프로젝트 purge 의 "archived 선행 409" 와 대칭이다.
2. **실행의 조건 그대로** — 프로젝트 잔여가 있으면 계정 행을 지우지 않고, 묘비가
   없어도 지우지 않는다(스크립트가 세운 순서·조건, 본체는 ``deletion/account_reconcile.py``).
3. **감사 2단계**(③ⓐ) — fail-closed 요청 행 → 실행 → 결과 행. 프로젝트 purge 선례.
4. **읽기 표면** — ``AdminUserPayload`` 의 탈퇴 축 두 스탬프(세 번째 축)와 감사
   화면의 ``account_reconcile`` 노출.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from services.application.app.auth.admin_audit import (
    AdminAuditService,
    InMemoryAdminAuditRepository,
)
from services.application.app.auth.sessions import (
    InMemorySessionRepository,
    SessionService,
)
from services.application.app.auth.users import (
    InMemoryUserRepository,
    UserService,
)
from services.application.app.deletion.account_axis_sweep import (
    InMemoryAccountAxisSweeper,
)
from services.application.app.deletion.account_reconcile import (
    AccountReconcileService,
    InMemoryAccountReconcileRepository,
)
from services.application.app.main import create_app

_NOW = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)


class _FakeHasher:
    def hash(self, password: str) -> str:
        return "H:" + password

    def verify(self, stored_hash: str, password: str) -> bool:
        return stored_hash == "H:" + password


class AdminAccountReconcileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.users_repo = InMemoryUserRepository()
        self.users = UserService(self.users_repo, hasher=_FakeHasher())
        self.sessions = SessionService(InMemorySessionRepository())
        self.audit_repo = InMemoryAdminAuditRepository()
        self.admin_audit = AdminAuditService(self.audit_repo)
        self.reconcile_repo = InMemoryAccountReconcileRepository()
        self.sweeper = InMemoryAccountAxisSweeper()
        self.reconcile = AccountReconcileService(
            self.reconcile_repo, sweeper=self.sweeper
        )
        app = create_app(
            user_service=self.users,
            session_service=self.sessions,
            admin_audit_service=self.admin_audit,
            account_reconcile_service=self.reconcile,
        )
        self.client = TestClient(app, base_url="https://testserver")
        self.users.create_user(username="root", password="pw789", is_admin=True)
        self.client.post(
            "/auth/login", json={"username": "root", "password": "pw789"}
        )
        # 대상 계정 bob — 유예 스탬프 → 파기 청구(=stalled)까지 밟아 둔다.
        self.users.create_user(username="bob", password="pw123")
        self.bob = next(
            u for u in self.users.list_users() if u.username == "bob"
        )
        self.users_repo.set_withdrawal_requested_at(
            self.bob.id, at=_NOW - timedelta(days=31)
        )
        self.users_repo.claim_for_purge(self.bob.id, at=_NOW)
        # reconcile 저장소의 stalled 은 사용자 저장소와 별개 상태 — 테스트가 같은
        # 사실(bob 이 stalled)을 이쪽에도 심는다(Mongo 배포에서는 둘 다 users 행).
        self.reconcile_repo._stalled.append(self.bob.id)

    # --- 대상 계약 ---------------------------------------------------------

    def test_survey_of_a_missing_user_is_404(self) -> None:
        response = self.client.get("/admin/users/user:missing/reconcile")
        self.assertEqual(response.status_code, 404)

    def test_survey_of_an_unclaimed_account_is_409_not_a_no_op(self) -> None:
        # 파기가 시작되지 않은 계정은 정리 대상이 아니다 — 200 no-op 으로 답하면
        # "정리했다"와 "아무것도 안 했다"가 같은 얼굴이 된다(프로젝트 purge 의
        # archived-선행 409 와 대칭).
        self.users.create_user(username="carol", password="pw123")
        carol = next(
            u for u in self.users.list_users() if u.username == "carol"
        )
        response = self.client.get(f"/admin/users/{carol.id}/reconcile")
        self.assertEqual(response.status_code, 409)

    def test_unauthenticated_and_non_admin_requests_are_refused(self) -> None:
        url = f"/admin/users/{self.bob.id}/reconcile"
        no_session = TestClient(create_app(), base_url="https://testserver")
        self.assertEqual(no_session.get(url).status_code, 401)
        # bob(일반 회원)으로 로그인해도 관리자 표면은 403.
        self.client.post(
            "/auth/login", json={"username": "bob", "password": "pw123"}
        )
        self.assertEqual(self.client.get(url).status_code, 403)

    # --- 조사(dry-run) ------------------------------------------------------

    def test_survey_reports_leftovers_and_tombstone_without_destroying(self) -> None:
        # ②ⓐ: 조사는 잔여 프로젝트·묘비 유무만 보고 **파괴가 없다** — 스윕도
        # 계정 행 삭제도 일어나지 않는다.
        self.reconcile_repo._projects[self.bob.id] = ["p1", "p2"]
        self.reconcile_repo._tombstoned.add(self.bob.id)
        response = self.client.get(f"/admin/users/{self.bob.id}/reconcile")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            set(body), {"leftover_projects", "has_username_tombstone"}
        )
        self.assertEqual(body["leftover_projects"], ["p1", "p2"])
        self.assertTrue(body["has_username_tombstone"])
        # 파괴 무변 — stalled 행이 그대로 살아 있고 스윕도 안 돌았다.
        self.assertIsNotNone(self.users_repo.get_by_id(self.bob.id))
        self.assertEqual(self.sweeper.collections, {})

    # --- 실행 ---------------------------------------------------------------

    def test_execute_sweeps_and_removes_the_user_row_when_clear(self) -> None:
        # 프로젝트 잔여 없음 + 묘비 있음 → 계정 행까지 지운다(스크립트 조건 그대로).
        self.reconcile_repo._tombstoned.add(self.bob.id)
        self.sweeper.collections = {
            "sessions": [{"_id": "s1", "user_id": self.bob.id}],
            "request_quota_policies": [{"_id": self.bob.id}],
        }
        response = self.client.post(
            f"/admin/users/{self.bob.id}/reconcile",
            json={"reason": "데몬 실패 수습"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["leftover_projects"], [])
        self.assertTrue(body["has_username_tombstone"])
        self.assertTrue(body["removed_user_row"])
        # 계정 축 두 규칙: user_id 필드로 가리키면 지운다, _id 로 가리켜도 지운다.
        self.assertEqual(
            body["swept"],
            {"sessions": 1, "request_quota_policies": 1},
        )
        self.assertEqual(self.sweeper.collections["sessions"], [])
        # Mongo 배포에서 reconcile repo 의 users 컬렉션 삭제가 곧 사용자 행
        # 삭제다 — InMemory 조립은 저장소 둘이 갈라지므로 삭제 요청으로 관측한다.
        self.assertEqual(self.reconcile_repo.deleted_rows, [self.bob.id])

    def test_execute_keeps_the_row_while_projects_remain(self) -> None:
        # 프로젝트가 남아 있으면 계정 행을 지우지 않는다 — 그 행이 owner_id 로
        # 잔여를 찾는 유일한 실마리다. 스윕은 돈다(계정 축 데이터는 정리).
        self.reconcile_repo._projects[self.bob.id] = ["p1"]
        self.reconcile_repo._tombstoned.add(self.bob.id)
        response = self.client.post(
            f"/admin/users/{self.bob.id}/reconcile",
            json={"reason": "잔여 프로젝트 확인"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["leftover_projects"], ["p1"])
        self.assertFalse(body["removed_user_row"])
        self.assertIsNotNone(self.users_repo.get_by_id(self.bob.id))

    def test_execute_keeps_the_row_without_a_tombstone(self) -> None:
        # 묘비가 없으면 지우지 않는다 — 묘비 없이 행을 지우면 원장이 영원히
        # id 로만 답한다(스크립트 머리말의 이유).
        response = self.client.post(
            f"/admin/users/{self.bob.id}/reconcile",
            json={"reason": "묘비 없음 확인"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["removed_user_row"])
        self.assertIsNotNone(self.users_repo.get_by_id(self.bob.id))

    def test_execute_requires_a_non_blank_reason(self) -> None:
        response = self.client.post(
            f"/admin/users/{self.bob.id}/reconcile", json={"reason": "   "}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.audit_repo.events, [])

    # --- 감사(③ⓐ) ------------------------------------------------------------

    def test_execute_is_audited_in_two_stages_with_the_target_user(self) -> None:
        self.reconcile_repo._tombstoned.add(self.bob.id)
        response = self.client.post(
            f"/admin/users/{self.bob.id}/reconcile",
            json={"reason": "  데몬 실패 수습  "},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.audit_repo.events), 2)
        requested, succeeded = self.audit_repo.events
        self.assertEqual(requested.action, "account_reconcile")
        self.assertEqual(requested.target_type, "user")
        self.assertEqual(requested.target_user_id, self.bob.id)
        self.assertIsNone(requested.target_project_id)
        self.assertEqual(requested.outcome, "requested")
        self.assertEqual(requested.reason, "데몬 실패 수습")  # strip 되어 저장
        self.assertEqual(succeeded.operation_id, requested.operation_id)
        self.assertEqual(succeeded.outcome, "succeeded")
        # 결과 행도 대상 축을 상속한다(요청만 target_user_id 를 아는 게 아니다).
        self.assertEqual(succeeded.target_user_id, self.bob.id)

    def test_a_failed_execution_records_the_failed_outcome(self) -> None:
        # 본체가 죽면 failed 결과 행이 남는다(프로젝트 purge 선례). TestClient 는
        # 예외를 전파하므로 전파 자체를 단정한다 — 감사가 실패를 삼키지 않는다.
        class _ExplodingSweeper:
            def sweep(self, user_id: str) -> dict[str, int]:
                raise RuntimeError("store down")

        self.reconcile._sweeper = _ExplodingSweeper()
        with self.assertRaises(RuntimeError):
            self.client.post(
                f"/admin/users/{self.bob.id}/reconcile",
                json={"reason": "실패 경로"},
            )
        outcomes = [e.outcome for e in self.audit_repo.events]
        self.assertEqual(outcomes, ["requested", "failed"])

    def test_the_audit_surface_lists_account_reconcile_events(self) -> None:
        # 감사 화면(/admin/audit-events)이 account_reconcile 을 보여준다(③ⓐ).
        self.reconcile_repo._tombstoned.add(self.bob.id)
        self.client.post(
            f"/admin/users/{self.bob.id}/reconcile",
            json={"reason": "목록 노출 확인"},
        )
        events = self.client.get("/admin/audit-events").json()["events"]
        self.assertTrue(
            any(e["action"] == "account_reconcile" for e in events)
        )

    # --- 읽기 표면(세 번째 축) -------------------------------------------------

    def test_the_admin_user_payload_carries_both_withdrawal_stamps(self) -> None:
        # 목록 읽기가 탈퇴 축의 두 스탬프를 서버 값 그대로 싣는다 — 이 필드가
        # 없으면 관리자는 stalled 계정을 찾을 수 없다(①ⓐ의 발견성 조건).
        users = self.client.get("/admin/users").json()["users"]
        bob_row = next(u for u in users if u["username"] == "bob")
        self.assertIsNotNone(bob_row["withdrawal_requested_at"])
        self.assertIsNotNone(bob_row["purge_started_at"])
        root_row = next(u for u in users if u["username"] == "root")
        self.assertIsNone(root_row["withdrawal_requested_at"])
        self.assertIsNone(root_row["purge_started_at"])

    def test_a_grace_period_account_is_not_a_reconcile_target(self) -> None:
        # 유예만 밟은(파기 미청구) 계정은 409 — 유예 중 회원을 정리 대상으로
        # 섞으면 안 된다. (409 셀의 유예 버전: 상태 축이 다른 계정.)
        self.users.create_user(username="dave", password="pw123")
        dave = next(
            u for u in self.users.list_users() if u.username == "dave"
        )
        self.users_repo.set_withdrawal_requested_at(dave.id, at=_NOW)
        response = self.client.get(f"/admin/users/{dave.id}/reconcile")
        self.assertEqual(response.status_code, 409)

    # --- 실행 측 대상 재확인(검증 조건 C1, 2026-09-12) ------------------------
    # SoT v1.8.62: "조사·실행 양쪽이 호출 직전에 스탬프를 재확인한다" — 실행
    # 쪽 절반이 무셀이었다(변이 M3: POST 의 재확인 삭제에 전건 초록). 실행은
    # 파괴라 이 축이 더 중요하다: 감사 행은 대상 검증 **뒤에** 남는다.

    def test_execute_for_a_missing_user_is_404(self) -> None:
        response = self.client.post(
            "/admin/users/user:missing/reconcile", json={"reason": "수습"}
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.audit_repo.events, [])

    def test_execute_for_an_unclaimed_account_is_409_and_unaudited(self) -> None:
        # 파기가 시작되지 않은 계정의 실행 요청은 대상 검증에서 끝난다 —
        # 감사 행까지 남기면 "정리했다"의 흔적이 대상 아닌 계정에 생긴다.
        self.users.create_user(username="erin", password="pw123")
        erin = next(
            u for u in self.users.list_users() if u.username == "erin"
        )
        self.users_repo.set_withdrawal_requested_at(erin.id, at=_NOW)
        response = self.client.post(
            f"/admin/users/{erin.id}/reconcile", json={"reason": "수습"}
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.audit_repo.events, [])

    # --- 감사 화면의 축 배제(검증 조건 C2, 2026-09-12) ------------------------
    # SoT: member_quota_policy 은 파괴가 아니라 이 화면 밖이다(변이 M6: 필터에
    # 추가돼도 전건 초록이었다). 회원 정책 행을 심어도 보이지 않는지 잰다.

    def test_the_audit_surface_excludes_member_quota_events(self) -> None:
        root = next(u for u in self.users.list_users() if u.username == "root")
        self.admin_audit.record_member_quota_change(
            admin_user_id=root.id, target_user_id=self.bob.id,
            change="suspend", reason="화면 배제 확인",
        )
        self.reconcile_repo._tombstoned.add(self.bob.id)
        self.client.post(
            f"/admin/users/{self.bob.id}/reconcile", json={"reason": "화면 배제 확인"}
        )
        actions = [
            event["action"]
            for event in self.client.get("/admin/audit-events").json()["events"]
        ]
        self.assertIn("account_reconcile", actions)
        self.assertNotIn("member_quota_policy", actions)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
