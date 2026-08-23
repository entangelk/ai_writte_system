"""Login/logout/me endpoints, and the authentication boundary they guard.

D8-3a turned the slice-1 non-goal ("existing endpoints stay open") into its
inverse: every operation except ``/health`` and the public ``/auth`` pair now
requires a live session. This module is the one place that drives real,
non-overridden apps, so it is where the exhaustive guard D7=A calls for lives —
every other suite runs authenticated through ``tests/auth_support.py``.
"""

import ast
import os
import pathlib
import re
import unittest
from datetime import UTC, datetime, timedelta
from unittest import mock

from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

try:
    from pymongo.errors import AutoReconnect as _STORAGE_FAILURE
except ModuleNotFoundError:  # pragma: no cover - the driver is present in CI
    _STORAGE_FAILURE = None

from services.application.app.auth.access_grants import (
    AccessGrantService, InMemoryAccessGrantRepository,
)
from services.application.app.auth.admin_audit import (
    AdminAuditService, InMemoryAdminAuditRepository,
)
from services.application.app.auth.cookies import cookie_secure
from services.application.app.auth.sessions import (
    InMemorySessionRepository, SessionService,
)
from services.application.app.auth.models import User
from services.application.app.auth.users import (
    MIN_PASSWORD_LENGTH, InMemoryUserRepository, UserService,
)
from services.application.app.core_sot.service import (
    CoreSotService, InMemoryCoreSotRepository,
)
from services.application.app.deletion.project_name_history import (
    InMemoryProjectNameHistoryRepository, ProjectNameHistoryService,
)
from services.application.app.indexing.models import IndexSyncEvent
from services.application.app.indexing.service import (
    InMemoryIndexSyncRepository, IndexSyncOutboxService,
)
from services.application.app.analysis.service import (
    AnalysisService, InMemoryAnalysisRepository,
)
from services.application.app.memory.service import (
    InMemoryMemoryRepository, MemoryService,
)
from services.application.app.main import create_app
from services.application.app.api.dependencies import (
    enforce_quota,
    require_admin_user,
    require_authenticated_user,
    require_project_owner,
)
from tests.auth_support import authenticate

_ROOT = pathlib.Path(__file__).resolve().parents[1]

# The only `{project_id}` routes that are admin-authorized instead of
# ownership-authorized. Spelled out once so a third entry is a decision someone
# had to type, not something a new route inherits by being under /admin.
_ADMIN_PROJECT_ROUTES = frozenset({
    "/admin/projects/{project_id}/purge",
    "/admin/projects/{project_id}/access-grants",
})


def _create_user_flags(relative: str) -> list[bool]:
    """소스에서 `create_user(...)` 호출을 찾아 `must_change_password` 값을 뽑는다.

    주석·문자열이 아니라 **실제 호출의 키워드 인자**를 본다(부분문자열 그렙은
    주석만 남겨도 통과한다 — 독립 검증이 실증). 인자가 없으면 도메인 기본값 False.
    """

    tree = ast.parse((_ROOT / relative).read_text(encoding="utf-8"))
    flags: list[bool] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name != "create_user":
            continue
        value = False
        for keyword in node.keywords:
            if keyword.arg == "must_change_password":
                value = bool(getattr(keyword.value, "value", False))
        flags.append(value)
    return flags


class _FakeHasher:
    def hash(self, password: str) -> str:
        return "H:" + password

    def verify(self, stored_hash: str, password: str) -> bool:
        return stored_hash == "H:" + password


def _client(*, ttl=timedelta(hours=1), core_sot=None, index_sync_outbox=None,
            memory_service=None, analysis_service=None, access_grants=None,
            admin_audit=None, project_name_history=None):
    users = UserService(InMemoryUserRepository(), hasher=_FakeHasher())
    sessions = SessionService(InMemorySessionRepository(), ttl=ttl)
    users.create_user(username="alice", password="pw123")
    app = create_app(
        service=core_sot, user_service=users, session_service=sessions,
        index_sync_outbox=index_sync_outbox, memory_service=memory_service,
        analysis_service=analysis_service, access_grant_service=access_grants,
        admin_audit_service=admin_audit,
        project_name_history_service=project_name_history,
    )
    # https base_url on purpose: the cookie ships Secure by default, so an http
    # client would silently drop it and every session test would pass/fail for
    # the wrong reason. This exercises the deployed configuration.
    return TestClient(app, base_url="https://testserver"), users, sessions


class LoginTest(unittest.TestCase):
    def test_valid_credentials_set_session_cookie_and_return_user(self) -> None:
        client, _, _ = _client()
        response = client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )
        self.assertEqual(response.status_code, 200)
        user = response.json()["user"]
        self.assertEqual(user["username"], "alice")
        self.assertFalse(user["is_admin"])
        self.assertTrue(user["id"])
        self.assertIn("session", response.cookies)

    def test_response_never_carries_the_password_hash(self) -> None:
        client, _, _ = _client()
        response = client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )
        self.assertEqual(set(response.json()["user"]), {"id", "username", "is_admin"})
        self.assertNotIn("pw123", response.text)

    def test_cookie_carries_the_three_security_flags(self) -> None:
        # D2=A hardening. These flags are the cookie's entire defense: HttpOnly
        # (XSS cannot read it), SameSite=Lax (CSRF), Secure (no cleartext).
        client, _, _ = _client()
        response = client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )
        header = response.headers["set-cookie"].lower()
        self.assertIn("httponly", header)
        self.assertIn("samesite=lax", header)
        self.assertIn("secure", header)
        self.assertIn("path=/", header)

    def test_wrong_password_is_401_and_sets_no_cookie(self) -> None:
        client, _, _ = _client()
        response = client.post(
            "/auth/login", json={"username": "alice", "password": "nope"}
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(set(response.json()), {"detail"})
        self.assertNotIn("set-cookie", response.headers)

    def test_unknown_user_is_401_with_the_same_message_as_wrong_password(self) -> None:
        # Over-strict guard against username enumeration: if someone "improves"
        # the errors into "no such user" / "wrong password", this fails.
        client, _, _ = _client()
        unknown = client.post(
            "/auth/login", json={"username": "ghost", "password": "pw123"}
        )
        wrong = client.post(
            "/auth/login", json={"username": "alice", "password": "nope"}
        )
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(unknown.json()["detail"], wrong.json()["detail"])


class SignupApiTest(unittest.TestCase):
    """승인제 가입 요청 HTTP 계약 (2026-08-22, 슬라이스 1-a).

    under-strict: 가입이 세션을 요구하면(공개가 아니면) 첫 셀이 실패한다.
    over-strict: 가입이 곧바로 로그인 가능한 계정을 만들면 넷째 셀이 실패한다.
    다섯째 셀은 1-b(403+사유)에서 갱신된다 — 지금은 임시 401 통일이다.
    """

    def test_a_signup_request_is_public_and_creates_a_pending_row(self) -> None:
        client, _, _ = _client()
        response = client.post(
            "/auth/signup", json={"username": "bob", "password": "long-enough-pw"}
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["username"], "bob")
        self.assertEqual(body["status"], "pending")

    def test_a_taken_active_username_is_409(self) -> None:
        client, _, _ = _client()  # alice exists
        response = client.post(
            "/auth/signup", json={"username": "alice", "password": "long-enough-pw"}
        )
        self.assertEqual(response.status_code, 409)

    def test_a_password_under_the_policy_minimum_is_400(self) -> None:
        client, _, _ = _client()
        response = client.post(
            "/auth/signup", json={"username": "bob", "password": "short"}
        )
        self.assertEqual(response.status_code, 400)

    def test_a_pending_account_is_403_pending(self) -> None:
        client, _, _ = _client()
        client.post(
            "/auth/signup", json={"username": "bob", "password": "long-enough-pw"}
        )
        # Right password, no session, told *why* (owner 2026-08-22): the 403 is
        # effectively addressed to the account owner alone, since reaching it
        # requires the correct password.
        response = client.post(
            "/auth/login", json={"username": "bob", "password": "long-enough-pw"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "account approval pending")
        self.assertNotIn("set-cookie", response.headers)

    def test_a_rejected_account_is_403_rejected(self) -> None:
        client, users, _ = _client()
        client.post(
            "/auth/signup", json={"username": "bob", "password": "long-enough-pw"}
        )
        # An admin's rejection (1-d will expose this as an operation; the domain
        # write itself is exercised in the users tests — here we only need the
        # row in place, so the repository seam is used directly).
        pending = users.list_users()[-1]  # alice is created first, bob is last
        users._repo.replace(User(
            id=pending.id, username=pending.username,
            password_hash=pending.password_hash, is_admin=False,
            is_active=True, created_at=pending.created_at,
            must_change_password=False, status="rejected",
        ))
        response = client.post(
            "/auth/login", json={"username": "bob", "password": "long-enough-pw"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "signup request rejected")
        self.assertNotIn("set-cookie", response.headers)

    def test_a_pending_status_is_not_revealed_by_a_wrong_password(self) -> None:
        # Enumeration defense continues to hold: guessing at a pending account
        # must look identical to guessing at any other account.
        client, _, _ = _client()
        client.post(
            "/auth/signup", json={"username": "bob", "password": "long-enough-pw"}
        )
        wrong = client.post(
            "/auth/login", json={"username": "bob", "password": "not-the-password"}
        )
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(wrong.json()["detail"], "invalid credentials")


class LoginLockoutTest(unittest.TestCase):
    """승인제 가입과 함께 선 브루트포스 방어 (2026-08-22, P-6).

    under-strict: 가드가 없으면 첫 셀이 실패한다(6번째 올바른 로그인이 200).
    over-strict: 잠금이 다른 username 까지 묻거나(셋째) 다른 실패 모드와 응답이
    갈라지면(넷째) 실패한다.
    """

    def test_the_sixth_attempt_with_the_right_password_is_still_401(self) -> None:
        client, _, _ = _client()
        for _ in range(5):
            client.post(
                "/auth/login", json={"username": "alice", "password": "nope"}
            )
        # The lock must hold even against the *correct* password — that is the
        # entire point of the guard.
        response = client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("set-cookie", response.headers)

    def test_lockout_answers_the_unified_401_detail(self) -> None:
        client, _, _ = _client()
        for _ in range(5):
            client.post(
                "/auth/login", json={"username": "alice", "password": "nope"}
            )
        response = client.post(
            "/auth/login", json={"username": "alice", "password": "nope"}
        )
        self.assertEqual(response.status_code, 401)
        # Whether an account is locked must not be distinguishable from any
        # other 401 — the lock state was created by the attacker's own failures
        # and must not become an oracle.
        self.assertEqual(response.json()["detail"], "invalid credentials")

    def test_a_lock_is_per_username(self) -> None:
        client, _, _ = _client()
        for _ in range(5):
            client.post(
                "/auth/login", json={"username": "alice", "password": "nope"}
            )
        # bob never failed: his sign-in is untouched.
        response = client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )
        self.assertEqual(response.status_code, 401)

    def test_a_locked_out_unknown_username_is_also_401(self) -> None:
        client, _, _ = _client()
        for _ in range(5):
            client.post(
                "/auth/login", json={"username": "ghost", "password": "nope"}
            )
        response = client.post(
            "/auth/login", json={"username": "ghost", "password": "anything"}
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "invalid credentials")


class MeTest(unittest.TestCase):
    def test_returns_current_user_after_login(self) -> None:
        client, _, _ = _client()
        client.post("/auth/login", json={"username": "alice", "password": "pw123"})
        response = client.get("/auth/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "alice")

    def test_without_cookie_is_401(self) -> None:
        client, _, _ = _client()
        response = client.get("/auth/me")
        self.assertEqual(response.status_code, 401)

    def test_forged_cookie_is_401(self) -> None:
        client, _, _ = _client()
        client.cookies.set("session", "forged-token")
        self.assertEqual(client.get("/auth/me").status_code, 401)

    def test_expired_session_is_401(self) -> None:
        # Zero-length TTL: the session is already past expiry when read back.
        client, _, _ = _client(ttl=timedelta(seconds=0))
        client.post("/auth/login", json={"username": "alice", "password": "pw123"})
        self.assertEqual(client.get("/auth/me").status_code, 401)

    def test_user_disabled_after_login_is_401(self) -> None:
        # A live cookie must stop working the moment the account is disabled —
        # that is the property D2=A chose server sessions for (admin force-logout).
        client, users, _ = _client()
        client.post("/auth/login", json={"username": "alice", "password": "pw123"})
        self.assertEqual(client.get("/auth/me").status_code, 200)
        stored = users.get_by_id(
            users.authenticate(username="alice", password="pw123").id
        )
        users._repo._by_id[stored.id] = type(stored)(
            id=stored.id, username=stored.username,
            password_hash=stored.password_hash, is_admin=stored.is_admin,
            is_active=False, created_at=stored.created_at,
        )
        self.assertEqual(client.get("/auth/me").status_code, 401)


class LogoutTest(unittest.TestCase):
    def test_logout_revokes_the_session(self) -> None:
        client, _, _ = _client()
        client.post("/auth/login", json={"username": "alice", "password": "pw123"})
        self.assertEqual(client.get("/auth/me").status_code, 200)
        response = client.post("/auth/logout")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        # Under-strict guard: the token must be dead server-side, not merely
        # dropped by this client.
        self.assertEqual(client.get("/auth/me").status_code, 401)

    def test_logout_without_session_is_not_an_error(self) -> None:
        client, _, _ = _client()
        self.assertEqual(client.post("/auth/logout").status_code, 200)


class CookiePolicyTest(unittest.TestCase):
    def test_secure_defaults_on_and_only_explicit_falsey_disables_it(self) -> None:
        # Fail closed: anything other than a deliberate false value keeps Secure.
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTH_COOKIE_SECURE", None)
            self.assertTrue(cookie_secure())
        for value, expected in (
            ("false", False), ("0", False), ("no", False), ("FALSE", False),
            ("true", True), ("1", True), ("", True), ("yes", True),
        ):
            with self.subTest(value=value):
                with mock.patch.dict(os.environ, {"AUTH_COOKIE_SECURE": value}):
                    self.assertEqual(cookie_secure(), expected)


class ProjectOwnershipRecordingTest(unittest.TestCase):
    """Creating a project records the creator.

    D8-2b recorded the creator when a session happened to exist. D8-3a made the
    session mandatory, so ``owner_id=None`` is no longer reachable through this
    endpoint — the unowned arms below became 401 arms. Nothing *reads* owner_id
    for access decisions yet; that is D8-3b.
    """

    def setUp(self) -> None:
        self.core_sot = CoreSotService(InMemoryCoreSotRepository())
        self.client, self.users, _ = _client(core_sot=self.core_sot)

    def _created_project(self, response):
        return self.core_sot.get_project(project_id=response.json()["id"])

    def test_logged_in_create_records_the_creator_as_owner(self) -> None:
        login = self.client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )
        expected_owner = login.json()["user"]["id"]

        response = self.client.post("/projects", json={"name": "Novel"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._created_project(response).owner_id, expected_owner)

    def test_anonymous_create_is_401_and_stores_nothing(self) -> None:
        # The inverse of the D8-2b guard, which asserted this stayed 200. Both
        # halves matter: the status *and* the absence of a stored row. A guard
        # that ran the handler and then rejected the response would leave an
        # unowned project behind on every anonymous call.
        response = self.client.post("/projects", json={"name": "Anonymous"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "not authenticated"})
        self.assertEqual(list(self.core_sot.list_projects()), [])

    def test_owner_is_not_exposed_on_the_public_payload_yet(self) -> None:
        # The field is recorded but not published: adding it to the response is a
        # public contract change (schema.d.ts) and belongs with the slice that
        # gives the frontend a reason to read it.
        self.client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )
        response = self.client.post("/projects", json={"name": "Novel"})
        self.assertEqual(set(response.json()), {"id", "name", "archived"})

    def test_create_after_logout_is_401(self) -> None:
        # Authorization comes from the *live* session, not from "was ever logged
        # in". Under D8-2b this recorded an unowned project; now it is refused.
        self.client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )
        self.client.post("/auth/logout")

        response = self.client.post("/projects", json={"name": "After logout"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(list(self.core_sot.list_projects()), [])

    def test_expired_session_cannot_create(self) -> None:
        # The other way a cookie stops being live. Same boundary, different
        # cause, and the one a long-lived browser tab actually hits.
        client, _, _ = _client(ttl=timedelta(seconds=-1), core_sot=self.core_sot)
        client.post("/auth/login", json={"username": "alice", "password": "pw123"})

        response = client.post("/projects", json={"name": "Stale"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(list(self.core_sot.list_projects()), [])


class ProjectAuthorizationTest(unittest.TestCase):
    """D8-3b locks both project detail access and the project list."""

    def setUp(self) -> None:
        self.core_sot = CoreSotService(InMemoryCoreSotRepository())
        self.client, self.users, _ = _client(core_sot=self.core_sot)
        self.bob = self.users.create_user(username="bob", password="pw456")
        login = self.client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )
        self.alice_id = login.json()["user"]["id"]

    def test_owner_can_read_own_project_and_missing_project_stays_404(self) -> None:
        """Over-strict: ownership must not reject a valid owner or erase 404."""
        owned = self.core_sot.create_project(
            name="Alice's", owner_id=self.alice_id
        )

        self.assertEqual(self.client.get(f"/projects/{owned.id}").status_code, 200)
        self.assertEqual(
            self.client.get("/projects/does-not-exist").status_code, 404
        )

    def test_other_owner_and_unowned_project_are_both_403(self) -> None:
        """Under-strict guards: mismatch and None are separate deny branches."""
        other = self.core_sot.create_project(name="Bob's", owner_id=self.bob.id)
        unowned = self.core_sot.create_project(name="Unowned")

        for project in (other, unowned):
            with self.subTest(owner_id=project.owner_id):
                response = self.client.get(f"/projects/{project.id}")
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), {"detail": "forbidden"})

    def test_list_returns_only_the_authenticated_users_projects(self) -> None:
        """Neither another user's metadata nor an unowned row may reach the wire."""
        mine = self.core_sot.create_project(
            name="Visible", owner_id=self.alice_id
        )
        self.core_sot.create_project(name="Other name", owner_id=self.bob.id)
        self.core_sot.create_project(name="Unowned name")

        response = self.client.get("/projects")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "projects": [{"id": mine.id, "name": "Visible", "archived": False}]
        })

    @unittest.skipIf(_STORAGE_FAILURE is None, "pymongo is not installed")
    def test_project_owner_dependency_maps_storage_failure_to_503(self) -> None:
        """Under-strict: a store outage in the dependency must not leak a 500."""
        class FailingRepository(InMemoryCoreSotRepository):
            def get_project(self, project_id):
                raise _STORAGE_FAILURE("canonical store unavailable")

        client, _, _ = _client(
            core_sot=CoreSotService(FailingRepository())
        )
        client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )

        response = client.get("/projects/any-project")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "canonical store unavailable"})

    def test_every_project_scoped_operation_refuses_a_foreign_project(self) -> None:
        """Under-strict: every {project_id} route stops before validation/handler."""
        foreign = self.core_sot.create_project(
            name="Foreign", owner_id=self.bob.id
        )
        for route in self.client.app.routes:
            if not isinstance(route, APIRoute) or "{project_id}" not in route.path:
                continue
            url = route.path.replace("{project_id}", foreign.id)
            url = re.sub(r"\{[^}]+\}", "does-not-exist", url)
            for method in sorted(route.methods):
                with self.subTest(path=route.path, method=method):
                    response = self.client.request(method, url)
                    self.assertEqual(response.status_code, 403)

    def test_ownership_dependency_and_403_declaration_match_project_scope(self) -> None:
        """Declaration guard in both directions: scoped routes only, no drift.

        D8-5 widened the *declaration* half: 403 gained its second producer (the
        admin boundary) and signup approval (owner 2026-08-22) its third — so
        "declares 403" no longer means "is project-scoped". The dependency half
        stayed exact — the ownership dependency belongs on `{project_id}` routes
        and nowhere else, which is the property this class exists to protect.
        """
        spec = self.client.app.openapi()
        for route in self.client.app.routes:
            if not isinstance(route, APIRoute):
                continue
            declared = [d.dependency for d in route.dependencies]
            ownership_guarded = require_project_owner in declared
            admin_guarded = require_admin_user in declared
            expected = "{project_id}" in route.path
            for method in sorted(route.methods):
                method = method.lower()
                with self.subTest(path=route.path, method=method):
                    if route.path in _ADMIN_PROJECT_ROUTES:
                        # The intentional exceptions to "{project_id} path ⇒
                        # ownership". Both name a project by id without reading
                        # its content: D8-6d purge destroys it (D5), and D8-5e
                        # issues the grant that *later* opens read access —
                        # issuing is not itself access. Any other admin +
                        # project_id route still fails this guard.
                        #
                        # The exception has a shape, so assert the shape instead of
                        # skipping: a bare `pass` here would also accept such a
                        # route with *no* authorization at all, which is the one
                        # way this exception could turn into a hole.
                        self.assertFalse(
                            ownership_guarded,
                            f"{route.path} is admin-authorized by design; adding "
                            "ownership would deny the admin the very thing it grants",
                        )
                        self.assertTrue(
                            admin_guarded,
                            f"{route.path} dropped its admin guard — a "
                            "{project_id} route with neither ownership nor admin "
                            "is unauthorized",
                        )
                    else:
                        self.assertEqual(ownership_guarded, expected)
                        # An admin route must never be project-scoped: the admin
                        # surface deliberately does not reach project content.
                        self.assertFalse(admin_guarded and expected)
                    responses = spec["paths"][route.path][method]["responses"]
                    if route.path == "/auth/login":
                        # 403's third producer (owner 2026-08-22): signup
                        # status, raised *in the handler* after credentials
                        # verify — an account-state answer, not an authorization
                        # boundary. Shape-asserted like the admin exception
                        # above rather than skipped: the login route must carry
                        # neither dependency (a guard here would wall off the
                        # very handshake the route exists for), must declare
                        # 403, and must keep 401 alongside (a wrong password is
                        # still the first gate — the status never leaks to a
                        # guesser).
                        self.assertFalse(
                            ownership_guarded or admin_guarded,
                            "the login route must stay dependency-free — "
                            "authorization belongs to the sessions it hands "
                            "out, not to the handshake itself",
                        )
                        self.assertIn("403", responses)
                        self.assertIn("401", responses)
                    else:
                        self.assertEqual(
                            "403" in responses, expected or admin_guarded
                        )


class AuthenticationBoundaryTest(unittest.TestCase):
    """D7=A's exhaustive guard: the inverse of slice 1's non-goal.

    Slice 1 asserted that *no* operation outside ``/auth`` was protected, and
    said in so many words that D8-3 must rewrite it into its inverse rather than
    delete it. This is that rewrite, and it keeps the shape that made the
    original worth having: the claim is about **every** operation, so it is
    derived from the app rather than from a list somebody has to remember to
    extend.

    ``PUBLIC`` is the whole exemption list, spelled out. A new endpoint is
    protected by default; opening one is an edit to this literal, which is the
    point — the observability phase measured that a missing wrapper left 56
    tests green, and the same silence here is a data leak.
    """

    # (path, method) -> why it answers without a session.
    PUBLIC = {
        ("/health", "get"): "compose healthcheck cannot log in",
        ("/auth/login", "post"): "this is how a session is obtained",
        ("/auth/signup", "post"): "requesting an account is how an account "
                                  "begins to exist — the row it creates is "
                                  "pending and grants nothing (2026-08-22)",
        ("/auth/logout", "post"): "idempotent: a client must always reach "
                                  "logged-out, even with a forgotten cookie",
        ("/auth/me", "get"): "answers its own 401 — it is how the frontend asks "
                             "whether it has a session at all",
    }

    def setUp(self) -> None:
        self.client, _, _ = _client()
        self.app = self.client.app
        self.spec = self.app.openapi()

    def _operations(self):
        for route in self.app.routes:
            if not isinstance(route, APIRoute):
                continue
            for method in sorted(route.methods):
                yield route, route.path, method.lower()

    def test_every_operation_is_either_protected_or_a_named_exemption(self) -> None:
        # The declaration half. `dependencies=` is what actually enforces, so the
        # guard reads the route object: an operation could declare 401 in its
        # `responses=` and still be wide open, which is exactly the drift that
        # would be invisible in the OpenAPI document alone.
        for route, path, method in self._operations():
            with self.subTest(path=path, method=method):
                declared = [d.dependency for d in route.dependencies]
                guarded = require_authenticated_user in declared
                self.assertEqual(
                    guarded, (path, method) not in self.PUBLIC,
                    f"{method.upper()} {path}: add dependencies=_REQUIRE_AUTH, or "
                    f"add it to PUBLIC with the reason it is open",
                )

    def test_every_protected_operation_declares_401(self) -> None:
        # H3 (D3=A): OpenAPI is the mechanical truth about what a caller can get
        # back. Enforcement without the declaration would generate frontend types
        # that cannot see the status the endpoint now returns most often.
        for _route, path, method in self._operations():
            if (path, method) in self.PUBLIC:
                continue
            with self.subTest(path=path, method=method):
                self.assertIn("401", self.spec["paths"][path][method]["responses"])

    def test_no_public_operation_declares_401_it_cannot_return(self) -> None:
        # Over-strict guard. /auth/login and /auth/me *do* answer 401 from their
        # own bodies; /health and /auth/logout never can, and declaring it there
        # would lie to the generated types just as loudly as omitting it did.
        for path, method in (("/health", "get"), ("/auth/logout", "post")):
            with self.subTest(path=path):
                declared = self.spec["paths"][path][method]["responses"]
                self.assertNotIn("401", declared)

    def test_every_protected_operation_refuses_a_sessionless_request(self) -> None:
        # The runtime half, and the one that cannot be satisfied by paperwork.
        # Every protected operation is actually driven without a cookie and must
        # answer 401 — not 200, not 404 from a nonexistent id, not 422 from the
        # missing body. The guard runs before request validation, so a bare call
        # with no body is enough to prove the boundary is in front of the handler.
        for _route, path, method in self._operations():
            if (path, method) in self.PUBLIC:
                continue
            with self.subTest(path=path, method=method):
                url = re.sub(r"\{[^}]+\}", "does-not-exist", path)
                response = self.client.request(method.upper(), url)
                self.assertEqual(
                    response.status_code, 401,
                    f"{method.upper()} {path} answered {response.status_code} "
                    f"without a session",
                )

    def test_a_logged_in_request_passes_the_guard(self) -> None:
        # Over-strict guard for the runtime half: a boundary that refuses
        # everything would satisfy the test above and break the product. With a
        # live session the same requests get past the guard into the handler,
        # where a fabricated project id is a normal 404 rather than a 401.
        self.client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )
        self.assertEqual(self.client.get("/projects").status_code, 200)
        self.assertEqual(
            self.client.get("/projects/does-not-exist").status_code, 404
        )

    def test_health_stays_open(self) -> None:
        # Named separately from the matrix because breaking it does not show up
        # as a failed request — it shows up as containers restarting.
        client, _, _ = _client()
        self.assertEqual(client.get("/health").status_code, 200)

    def test_auth_endpoints_declare_401_and_the_storage_503(self) -> None:
        spec = create_app().openapi()
        for path, method, expects_401 in (
            ("/auth/login", "post", True),
            ("/auth/me", "get", True),
            ("/auth/logout", "post", False),
        ):
            with self.subTest(path=path):
                declared = set(spec["paths"][path][method]["responses"])
                self.assertIn("503", declared)
                self.assertEqual("401" in declared, expects_401)


class AdminUserApiTest(unittest.TestCase):
    """D8-5 (D6=A): the minimal admin surface — list, create, deactivate.

    The boundary itself is audited in ``CombinedBoundaryMatrixTest``; this class
    is about what the endpoints *do* once an admin is through it.
    """

    def setUp(self) -> None:
        self.client, self.users, _ = _client()
        self.root = self.users.create_user(
            username="root", password="pw789", is_admin=True
        )
        self.client.post(
            "/auth/login", json={"username": "root", "password": "pw789"}
        )

    def test_list_returns_every_account_and_never_a_password_hash(self) -> None:
        listed = self.client.get("/admin/users")

        self.assertEqual(listed.status_code, 200)
        users = listed.json()["users"]
        self.assertEqual(
            {u["username"] for u in users}, {"alice", "root"}
        )
        self.assertEqual(
            set(users[0]), {"id", "username", "is_admin", "is_active"}
        )
        # Over-strict: the wire model is what keeps a hash from ever riding
        # along, so assert the absence on the raw body rather than the parsed
        # keys — a nested or renamed field would still be caught.
        self.assertNotIn("password_hash", listed.text)
        self.assertNotIn("H:pw123", listed.text)

    def test_created_user_can_log_in_and_is_active(self) -> None:
        created = self.client.post(
            "/admin/users", json={"username": "carol", "password": "pw000"}
        )

        self.assertEqual(created.status_code, 200)
        self.assertEqual(
            created.json(),
            {
                "id": created.json()["id"], "username": "carol",
                "is_admin": False, "is_active": True,
            },
        )
        # C-6: the account is real, but the administrator-set password is
        # **single-use**. Signing in with it alone is refused (409) — that is the
        # whole point: an admin must not be left knowing a working password.
        refused = self.client.post(
            "/auth/login", json={"username": "carol", "password": "pw000"}
        )
        self.assertEqual(refused.status_code, 409)
        self.assertNotIn("set-cookie", refused.headers)

        # Spending it on a replacement works, and *is* the sign-in.
        login = self.client.post(
            "/auth/login",
            json={
                "username": "carol", "password": "pw000",
                "new_password": "carol-chosen-passphrase",
            },
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn("session", login.cookies)

    def test_duplicate_username_is_409_and_bad_input_is_400(self) -> None:
        self.assertEqual(
            self.client.post(
                "/admin/users", json={"username": "alice", "password": "x"}
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.post(
                "/admin/users", json={"username": "   ", "password": "x"}
            ).status_code,
            400,
        )

    def test_deactivating_a_user_kills_their_live_session(self) -> None:
        # The property D2 chose server sessions for. Alice logs in on her own
        # client, the admin disables her, and her *existing* cookie stops
        # working on the next request — no logout, no waiting for the TTL.
        alice = TestClient(self.client.app, base_url="https://testserver")
        alice.post("/auth/login", json={"username": "alice", "password": "pw123"})
        self.assertEqual(alice.get("/auth/me").status_code, 200)

        alice_id = alice.get("/auth/me").json()["id"]
        response = self.client.post(f"/admin/users/{alice_id}/deactivate")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_active"])
        self.assertEqual(alice.get("/auth/me").status_code, 401)
        # And she cannot get a new one either.
        self.assertEqual(
            alice.post(
                "/auth/login", json={"username": "alice", "password": "pw123"}
            ).status_code,
            401,
        )

    def test_deactivating_an_unknown_user_is_404(self) -> None:
        self.assertEqual(
            self.client.post("/admin/users/user:ghost/deactivate").status_code, 404
        )

    def test_the_last_active_admin_cannot_be_deactivated(self) -> None:
        # F2=A. root is the only admin, so this would lock the deployment out of
        # its own admin surface — recoverable only by exec-ing a script in the
        # container.
        response = self.client.post(f"/admin/users/{self.root.id}/deactivate")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get("/admin/users").status_code, 200)

    def test_an_admin_can_be_deactivated_once_another_admin_is_active(self) -> None:
        # Over-strict half: the rule is about the population, not about admins
        # being undeletable. With a second admin present the first one goes.
        self.client.post(
            "/admin/users",
            json={"username": "root2", "password": "pw111", "is_admin": True},
        )

        response = self.client.post(f"/admin/users/{self.root.id}/deactivate")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_active"])

    def test_an_inactive_admin_does_not_count_as_the_survivor(self) -> None:
        # The check asks for *active* admins. A disabled admin cannot log in, so
        # counting it would allow exactly the lockout F2=A forbids.
        second = self.client.post(
            "/admin/users",
            json={"username": "root2", "password": "pw111", "is_admin": True},
        ).json()
        self.client.post(f"/admin/users/{second['id']}/deactivate")

        response = self.client.post(f"/admin/users/{self.root.id}/deactivate")

        self.assertEqual(response.status_code, 409)


class SignupApprovalApiTest(unittest.TestCase):
    """승인제 가입의 관리자 측 (슬라이스 1-d, 오너 2026-08-22).

    under-strict: 승인이 pending 아닌 행도 바꾸면 409 셀이 실패한다.
    over-strict: 승인이 세션까지 만들면(로그인 대신) 승인 후 로그인 셀이 실패한다.
    """

    def setUp(self) -> None:
        self.client, self.users, _ = _client()
        self.users.create_user(username="root", password="pw789", is_admin=True)
        self.client.post(
            "/auth/login", json={"username": "root", "password": "pw789"}
        )

    def _request(self, username: str) -> str:
        response = self.client.post(
            "/auth/signup", json={"username": username, "password": "long-enough-pw"}
        )
        self.assertEqual(response.status_code, 201)
        # The signup response deliberately carries no id — the requester has no
        # use for one — so the admin flow discovers it the way the UI does.
        queue = self.client.get("/admin/signup-requests").json()["requests"]
        return next(r["id"] for r in queue if r["username"] == username)

    def test_the_queue_lists_pending_requests_only(self) -> None:
        self._request("bob")
        # An already-approved request leaves the queue.
        approved = self._request("carol")
        self.client.post(f"/admin/signup-requests/{approved}/approve")
        listed = self.client.get("/admin/signup-requests")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            [r["username"] for r in listed.json()["requests"]], ["bob"]
        )
        self.assertEqual(
            set(listed.json()["requests"][0]),
            {"id", "username", "requested_at"},
        )

    def test_approval_lets_the_member_sign_in(self) -> None:
        pending = self._request("bob")
        approved = self.client.post(
            f"/admin/signup-requests/{pending}/approve"
        )
        self.assertEqual(approved.status_code, 200)
        # Approval mints no session of its own — the member signs in themselves.
        signin = self.client.post(
            "/auth/login", json={"username": "bob", "password": "long-enough-pw"}
        )
        self.assertEqual(signin.status_code, 200)
        self.assertIn("session", signin.cookies)

    def test_rejection_keeps_the_account_403(self) -> None:
        pending = self._request("bob")
        rejected = self.client.post(
            f"/admin/signup-requests/{pending}/reject"
        )
        self.assertEqual(rejected.status_code, 200)
        signin = self.client.post(
            "/auth/login", json={"username": "bob", "password": "long-enough-pw"}
        )
        self.assertEqual(signin.status_code, 403)
        self.assertEqual(signin.json()["detail"], "signup request rejected")

    def test_an_already_resolved_request_is_409(self) -> None:
        pending = self._request("bob")
        self.client.post(f"/admin/signup-requests/{pending}/approve")
        again = self.client.post(
            f"/admin/signup-requests/{pending}/approve"
        )
        self.assertEqual(again.status_code, 409)

    def test_an_unknown_request_is_404(self) -> None:
        response = self.client.post(
            "/admin/signup-requests/user:ghost/approve"
        )
        self.assertEqual(response.status_code, 404)

    def test_a_non_admin_gets_403_on_all_three(self) -> None:
        self.client, self.users, _ = _client()
        self.client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )
        self.assertEqual(
            self.client.get("/admin/signup-requests").status_code, 403
        )
        self.assertEqual(
            self.client.post(
                "/admin/signup-requests/user:x/approve"
            ).status_code, 403
        )
        self.assertEqual(
            self.client.post(
                "/admin/signup-requests/user:x/reject"
            ).status_code, 403
        )


class _PurgeSpy:
    """Records purge_project calls; delegates everything else to the inner service.

    D8-6d regression: prove the endpoint actually fans the purge out to the derived
    services, not just core_sot + enqueue (otherwise derived 10컬렉션 become silent
    orphans — D5 부분 삭제)."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.purged: list[str] = []

    def purge_project(self, *, project_id: str) -> None:
        self.purged.append(project_id)
        return self.inner.purge_project(project_id=project_id)

    def __getattr__(self, name):
        return getattr(self.inner, name)


class AdminProjectPurgeTest(unittest.TestCase):
    """D8-6d: POST /admin/projects/{id}/purge — 204 + core_sot/derived 파기 + enqueue.

    비관리자 403·미인증 401 은 CombinedBoundaryMatrixTest 가 ADMIN tier 전수로 잠근다
    (purge 포함). 여기는 성공 동작을 세 축으로 검증한다 — 정본(core_sot) 소멸 ·
    vector/index 용 enqueue · **derived 서비스 파기 호출(D5 전수, memory·analysis 대표)**.
    """

    def setUp(self) -> None:
        self.core_sot = CoreSotService(InMemoryCoreSotRepository())
        self.outbox_repo = InMemoryIndexSyncRepository()
        self.sync_outbox = IndexSyncOutboxService(self.outbox_repo)
        # memory·analysis spy — 8 derived service 중 대표 2개. endpoint 가 이들의
        # purge_project 를 빼먹으면 조용한 고아(부분 삭제, D5 위반)가 된다.
        self.memory_spy = _PurgeSpy(MemoryService(InMemoryMemoryRepository()))
        self.analysis_spy = _PurgeSpy(AnalysisService(InMemoryAnalysisRepository()))
        self.audit_repo = InMemoryAdminAuditRepository()
        self.admin_audit = AdminAuditService(self.audit_repo)
        self.name_history_repo = InMemoryProjectNameHistoryRepository()
        self.name_history = ProjectNameHistoryService(self.name_history_repo)
        self.client, self.users, _ = _client(
            core_sot=self.core_sot, index_sync_outbox=self.sync_outbox,
            memory_service=self.memory_spy, analysis_service=self.analysis_spy,
            admin_audit=self.admin_audit, project_name_history=self.name_history,
        )
        self.users.create_user(username="root", password="pw789", is_admin=True)
        self.client.post(
            "/auth/login", json={"username": "root", "password": "pw789"}
        )

    def test_admin_purge_returns_204_and_removes_project(self) -> None:
        project = self.core_sot.create_project(name="Novel")
        self.core_sot.archive_project(project_id=project.id)
        response = self.client.post(
            f"/admin/projects/{project.id}/purge", json={"reason": "정리 요청"}
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")  # 204 carries no body
        # 정본(core_sot)에서 project 소멸 — purge_project 가 실제로 돌았다.
        self.assertEqual([p.id for p in self.core_sot.list_projects()], [])

    def test_admin_purge_enqueues_project_purged(self) -> None:
        # endpoint 가 worker drain(6c _drain_purge) 용 PROJECT_PURGED entry 를 생산한다 —
        # 이것이 빠지면 vector/index 5백엔드가 고아로 잔류한다(D5).
        project = self.core_sot.create_project(name="Novel")
        self.core_sot.archive_project(project_id=project.id)
        self.client.post(
            f"/admin/projects/{project.id}/purge", json={"reason": "정리 요청"}
        )
        entries = list(self.outbox_repo.outbox_entries.values())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].event, IndexSyncEvent.PROJECT_PURGED)
        self.assertEqual(entries[0].project_id, project.id)

    def test_admin_purge_fans_out_to_derived_services(self) -> None:
        # D5 전수: endpoint 가 8 derived service purge 를 부른다. memory·analysis spy
        # (대표 2개)로 호출을 잠근다 — 이것이 빠지면 derived 10컬렉션이 조용한 고아.
        project = self.core_sot.create_project(name="Novel")
        self.core_sot.archive_project(project_id=project.id)
        self.client.post(
            f"/admin/projects/{project.id}/purge", json={"reason": "정리 요청"}
        )
        self.assertEqual(self.memory_spy.purged, [project.id])
        self.assertEqual(self.analysis_spy.purged, [project.id])

    def test_the_project_name_survives_the_purge_that_destroys_everything_else(
        self,
    ) -> None:
        """Slice 8.2c N3=A: 파기가 이름 한 값을 남긴다 — 사용 기록을 사람이 읽기 위해서다.

        under-strict: 쓰기를 지우면 실패한다. 정본(`projects`)은 소멸했는데 이름 행은
        살아 있다는 것이 D8-6 계약 개정의 실체다.
        """
        project = self.core_sot.create_project(name="첫 장편")
        self.core_sot.archive_project(project_id=project.id)

        response = self.client.post(
            f"/admin/projects/{project.id}/purge", json={"reason": "고객 삭제 요청"}
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual([p.id for p in self.core_sot.list_projects()], [])
        stored = self.name_history.get(project_id=project.id)
        self.assertIsNotNone(stored, "파기가 이름을 안 남겼다 — 8.2c N3=A 위반")
        self.assertEqual(stored.name, "첫 장편")

    def test_a_failed_name_snapshot_stops_the_purge_before_it_destroys_anything(
        self,
    ) -> None:
        """★ 이 셀이 **쓰기 순서와 fail-closed를 동시에** 잠근다.

        이름 행 쓰기가 실패했는데 파기가 이미 시작됐다면, 그 프로젝트는 **이름 없이**
        사라진다(원장이 id로만 답하게 되어 개정 전으로 되돌아간다). 그래서 쓰기는 파괴
        **앞**이고 실패는 요청 실패다.

        - under-strict: `try/except`로 감싸 "안정화"하면 실패한다(파기가 진행된다).
        - 순서: 쓰기를 `core_sot.purge_project` 뒤로 옮기면 실패한다 — 그때는 파기가
          이미 돌았으므로 아래 `list_projects()` 단정이 무너진다.
        """
        if _STORAGE_FAILURE is None:
            self.skipTest("pymongo is not installed")

        class FailingRepository(InMemoryProjectNameHistoryRepository):
            def put(self, snapshot):
                raise _STORAGE_FAILURE("name history unavailable")

        core_sot = CoreSotService(InMemoryCoreSotRepository())
        memory_spy = _PurgeSpy(MemoryService(InMemoryMemoryRepository()))
        client, users, _ = _client(
            core_sot=core_sot, memory_service=memory_spy,
            project_name_history=ProjectNameHistoryService(FailingRepository()),
        )
        users.create_user(username="root", password="pw789", is_admin=True)
        client.post("/auth/login", json={"username": "root", "password": "pw789"})
        project = core_sot.create_project(name="첫 장편")
        core_sot.archive_project(project_id=project.id)

        response = client.post(
            f"/admin/projects/{project.id}/purge", json={"reason": "정리 요청"}
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            [p.id for p in core_sot.list_projects()], [project.id],
            "이름을 못 남겼는데 정본을 지웠다 — 그 프로젝트는 영영 id로만 답해진다",
        )
        self.assertEqual(memory_spy.purged, [], "derived 파기까지 진행됐다")

    def test_the_name_survives_a_purge_that_dies_halfway_through(self) -> None:
        """★ 8.2c의 진짜 값이 나오는 자리 (독립 검증 2026-08-05 HARDEN-2).

        purge는 **중간에 죽을 수 있다** — core_sot을 지운 뒤 derived 단계에서 저장소가
        나가면 503이고, 그 프로젝트는 `scripts/purge_reconciler.py`가 수습한다. 이름 행이
        그 잔해에서 살아남지 못하면 **가장 수습이 어려운 경로에서만** 이름이 사라진다.

        지금은 쓰기 순서가 그것을 보장한다(이름 → core_sot → derived). 이 셀은 그 보장을
        **순서가 아니라 결과로** 단정한다 — 순서를 바꾸는 어떤 리팩터링도 여기서 걸린다.
        """
        if _STORAGE_FAILURE is None:
            self.skipTest("pymongo is not installed")
        project = self.core_sot.create_project(name="첫 장편")
        self.core_sot.archive_project(project_id=project.id)

        def _die(**_kwargs):
            raise _STORAGE_FAILURE("derived storage unavailable")

        self.memory_spy.purge_project = _die

        response = self.client.post(
            f"/admin/projects/{project.id}/purge", json={"reason": "정리 요청"}
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual([p.id for p in self.core_sot.list_projects()], [])
        self.assertEqual(
            self.name_history.get(project_id=project.id).name, "첫 장편",
            "파기가 중간에 죽자 이름이 사라졌다 — reconciler가 수습할 잔해에 이름이 없다",
        )

    def test_a_live_project_has_no_history_row(self) -> None:
        """Over-strict: N3=A는 **파기 시점에만** 쓴다.

        생성·개명이 이 컬렉션을 건드리면 살아 있는 이름이 두 곳에 복제되고(두 정본),
        보존 정책의 대상("사라진 프로젝트의 이름")도 흐려진다. 그 과잉 구현이 들어오면
        이 셀이 실패한다.
        """
        # ★ 서비스가 아니라 **HTTP로** 돈다. 서비스만 부르면 endpoint에 쓰기를 더하는
        # 과잉 구현을 못 잡는다 — 실제로 뮤테이션에서 그 구멍이 드러나 이 셀을 고쳤다
        # (2026-08-05, 뮤테이션 4가 첫 판에서는 통과했다).
        created = self.client.post("/projects", json={"name": "첫 장편"})
        self.assertEqual(created.status_code, 200)
        project_id = created.json()["id"]

        renamed = self.client.patch(f"/projects/{project_id}", json={"name": "바뀐 이름"})
        archived = self.client.delete(f"/projects/{project_id}")

        self.assertEqual((renamed.status_code, archived.status_code), (200, 200))
        self.assertIsNone(self.name_history.get(project_id=project_id))
        self.assertEqual(self.name_history_repo.count(), 0)

    def test_a_second_purge_is_404_and_leaves_the_recorded_name_untouched(self) -> None:
        project = self.core_sot.create_project(name="첫 장편")
        self.core_sot.archive_project(project_id=project.id)
        self.client.post(
            f"/admin/projects/{project.id}/purge", json={"reason": "정리 요청"}
        )

        second = self.client.post(
            f"/admin/projects/{project.id}/purge", json={"reason": "다시 정리"}
        )

        self.assertEqual(second.status_code, 404)
        self.assertEqual(self.name_history.get(project_id=project.id).name, "첫 장편")
        self.assertEqual(self.name_history_repo.count(), 1)

    def test_admin_purge_missing_project_is_404(self) -> None:
        response = self.client.post(
            "/admin/projects/does-not-exist/purge", json={"reason": "정리 요청"}
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("detail", response.json())

    def test_active_project_is_409_before_audit_or_purge(self) -> None:
        """Under-strict: D5의 archive→purge 2단계를 backend가 직접 강제한다."""
        project = self.core_sot.create_project(name="Novel")

        response = self.client.post(
            f"/admin/projects/{project.id}/purge", json={"reason": "정리 요청"}
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual([p.id for p in self.core_sot.list_projects()], [project.id])
        self.assertEqual(self.admin_audit.list_project_purge_events(), ())

    def test_archived_project_is_the_over_strict_normal_case(self) -> None:
        """Over-strict: 2단계 확인은 archive된 정상 purge까지 막지 않는다."""
        project = self.core_sot.create_project(name="Novel")
        self.core_sot.archive_project(project_id=project.id)

        response = self.client.post(
            f"/admin/projects/{project.id}/purge", json={"reason": "정리 요청"}
        )

        self.assertEqual(response.status_code, 204)

    def test_reason_is_required_and_non_blank(self) -> None:
        project = self.core_sot.create_project(name="Novel")
        self.core_sot.archive_project(project_id=project.id)

        for body in ({}, {"reason": "   "}):
            with self.subTest(body=body):
                response = self.client.post(
                    f"/admin/projects/{project.id}/purge", json=body
                )
                self.assertEqual(response.status_code, 422)
        self.assertEqual([p.id for p in self.core_sot.list_projects()], [project.id])

    def test_success_records_requested_and_succeeded_tombstones(self) -> None:
        project = self.core_sot.create_project(name="Novel")
        self.core_sot.archive_project(project_id=project.id)

        response = self.client.post(
            f"/admin/projects/{project.id}/purge", json={"reason": "고객 삭제 요청"}
        )
        audit = self.client.get("/admin/audit-events?action=project_purge")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(audit.status_code, 200)
        events = audit.json()["events"]
        self.assertEqual([event["outcome"] for event in events], ["succeeded", "requested"])
        self.assertEqual({event["target_project_id"] for event in events}, {project.id})
        self.assertEqual({event["reason"] for event in events}, {"고객 삭제 요청"})
        self.assertEqual(len({event["operation_id"] for event in events}), 1)
        self.assertTrue(all("project_id" not in event for event in events))

    def test_requested_audit_failure_prevents_the_purge(self) -> None:
        if _STORAGE_FAILURE is None:
            self.skipTest("pymongo is not installed")

        class FailingRepository(InMemoryAdminAuditRepository):
            def insert(self, event):
                raise _STORAGE_FAILURE("audit unavailable")

        core_sot = CoreSotService(InMemoryCoreSotRepository())
        audit = AdminAuditService(FailingRepository())
        client, users, _ = _client(core_sot=core_sot, admin_audit=audit)
        users.create_user(username="root", password="pw789", is_admin=True)
        client.post("/auth/login", json={"username": "root", "password": "pw789"})
        project = core_sot.create_project(name="Novel")
        core_sot.archive_project(project_id=project.id)

        response = client.post(
            f"/admin/projects/{project.id}/purge", json={"reason": "정리 요청"}
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual([p.id for p in core_sot.list_projects()], [project.id])

    def test_outcome_audit_failure_does_not_turn_a_completed_purge_into_503(self) -> None:
        class OutcomeFailingRepository(InMemoryAdminAuditRepository):
            def insert(self, event):
                if event.outcome != "requested":
                    raise RuntimeError("outcome audit unavailable")
                super().insert(event)

        core_sot = CoreSotService(InMemoryCoreSotRepository())
        audit = AdminAuditService(OutcomeFailingRepository())
        client, users, _ = _client(core_sot=core_sot, admin_audit=audit)
        users.create_user(username="root", password="pw789", is_admin=True)
        client.post("/auth/login", json={"username": "root", "password": "pw789"})
        project = core_sot.create_project(name="Novel")
        core_sot.archive_project(project_id=project.id)

        response = client.post(
            f"/admin/projects/{project.id}/purge", json={"reason": "정리 요청"}
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(list(core_sot.list_projects()), [])

    def test_a_second_purge_is_404_and_never_reaches_the_derived_services(self) -> None:
        """★ 알려진 한계를 **실행 가능한 사실로** 못박는다 — 재시도는 멱등이 아니다.

        endpoint 는 `core_sot.purge_project` 를 **먼저** 부르고 derived 8종을 뒤이어
        부른다. 그래서 derived 단계에서 mongo 장애(503)가 나면 **수습할 방법이 없다**:
        두 번째 호출은 core_sot 이 이미 비어 `NotFound` → 404 로 끝나고 **derived 에
        도달하지 못한다.** 아래 spy 가 그 도달 실패를 직접 단정한다.

        v1.7.74 changelog 와 endpoint docstring 은 이것을 "멱등 재시도"라고 적었는데
        거짓이었다(2026-08-02 독립 검증 Blocking #1). 잔류물 수습은 별도 도구가 한다
        (`scripts/purge_reconciler.py`).

        **이 셀은 오너 결정 ⓑ(순서 변경)·ⓒ(`core_sot.purge` 멱등화)를 막지 않는다 —
        오히려 그 결정을 구현하면 여기서 실패하므로, 문서 정정을 함께 하도록 강제한다.**
        """

        project = self.core_sot.create_project(name="Novel")
        self.core_sot.archive_project(project_id=project.id)
        self.assertEqual(
            self.client.post(
                f"/admin/projects/{project.id}/purge", json={"reason": "정리 요청"}
            ).status_code, 204
        )
        self.memory_spy.purged.clear()
        self.analysis_spy.purged.clear()

        retry = self.client.post(
            f"/admin/projects/{project.id}/purge", json={"reason": "재시도"}
        )

        self.assertEqual(retry.status_code, 404)
        self.assertEqual(
            (self.memory_spy.purged, self.analysis_spy.purged),
            ([], []),
            "재시도가 derived 에 도달했다면 부분 실패를 수습할 수 있다는 뜻이다 — "
            "그렇다면 docstring·SoT 의 '재시도 불가' 서술을 함께 고쳐야 한다",
        )


class AdminQuotaPolicyApiTest(unittest.TestCase):
    """Phase 8.5-a (owner 2026-08-23): the quota operations read surface.

    경계(401/403/tier)는 ``CombinedBoundaryMatrixTest`` 가 본다 — 이 클래스는
    통과한 관리자가 **무엇을 보는가**를 잠근다. 특히 H2(2026-08-03 검증): 저장된
    ``policy.limits`` 를 유효 한도인 양 내놓으면 만료된 예약이 "아직 대기 중"으로
    보인다 — 상세의 두 값이 갈라져 있는 것이 이 표면의 존재 이유다.
    """

    def setUp(self) -> None:
        self.client, self.users, _ = _client()
        self.root = self.users.create_user(
            username="root", password="pw789", is_admin=True
        )
        self.client.post(
            "/auth/login", json={"username": "root", "password": "pw789"}
        )
        self.quota = self.client.app.state.quota

    def _member(self, username):
        return next(
            u for u in self.users.list_users() if u.username == username)

    def test_list_includes_members_without_a_policy_row(self) -> None:
        # under-strict: 정책 행 없는 회원이 조용히 빠지면 "무제한인 줄 알았는데
        # 기본 20" 사고가 목록에서 보이지 않는다 — 포함이 이 endpoint 의 요점.
        listed = self.client.get("/admin/quota-policies")

        self.assertEqual(listed.status_code, 200)
        entries = {p["username"]: p for p in listed.json()["policies"]}
        self.assertIn("alice", entries)  # 정책 행 없음 — 기본 해석으로 포함
        self.assertIn("root", entries)   # 부트스트랩 정책 행 있음
        self.assertFalse(entries["alice"]["has_pending"])
        self.assertEqual(
            set(entries["alice"]),
            {"user_id", "username", "is_active", "status", "unlimited",
             "remaining", "daily", "weekly", "has_pending"},
        )
        # 비활성 회원은 운영 목록에서 제외 — 로그인할 수 없는 계정의 한도는
        # 운영 대상이 아니다(상세는 user_id 로 직접 보는 길이 남는다).
        self.users.create_user(username="ghost", password="pw000")
        ghost = self._member("ghost")
        self.users.deactivate_user(ghost.id)
        listed = self.client.get("/admin/quota-policies")
        names = {p["username"] for p in listed.json()["policies"]}
        self.assertNotIn("ghost", names)

    def test_detail_splits_effective_from_stored_and_hides_expired_pending(self) -> None:
        # ★ H2 — 만료된 예약(effective_at 이 지난 pending)은 어디에도 "대기 중"으로
        # 나와선 안 된다. 행에 그 잔재를 심어도 상세의 pending 은 None 이고 유효
        # 한도는 이미 예약을 반영한다.
        from datetime import UTC, datetime, timedelta

        from services.application.app.quota.policy import (
            PendingLimits, QuotaLimits, QuotaPolicy, QuotaStatus,
        )
        now = datetime.now(UTC)
        self.quota.policy._repo.upsert(QuotaPolicy(
            user_id=self._member("alice").id,
            limits=QuotaLimits(10, 10, QuotaStatus.ACTIVE),
            pending=PendingLimits(
                limits=QuotaLimits(3, 3, QuotaStatus.ACTIVE),
                effective_at=now - timedelta(days=1),
            ),
            updated_at=now,
        ))
        alice = self._member("alice")
        detail = self.client.get(f"/admin/quota-policies/{alice.id}")

        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertIsNone(body["pending"])          # 만료 예약은 "대기 중"이 아니다
        self.assertFalse(body["has_pending"])
        self.assertEqual(body["stored_daily_limit"], 10)   # 진단용 원본
        self.assertEqual(body["daily"]["limit"], 3)        # 유효 한도 = 해석값
        self.assertIsNotNone(body["updated_at"])

    def test_future_reservation_is_pending_and_relief_is_immediate(self) -> None:
        # P6(D2=ⓐ): 완화는 즉시, 축소는 창 경계 예약 — set_limits 가 그렇게 굽는다.
        from services.application.app.quota.policy import (
            QuotaLimits, QuotaStatus,
        )

        alice = self._member("alice")
        self.quota.policy.set_limits(
            user_id=alice.id, created_at=alice.created_at,
            target=QuotaLimits(50, 200, QuotaStatus.ACTIVE),
        )
        detail = self.client.get(f"/admin/quota-policies/{alice.id}")
        body = detail.json()
        # 완화(20→50)는 즉시라 예약이 남지 않는다 — P6 의 절반.
        self.assertFalse(body["has_pending"])
        self.assertEqual(body["daily"]["limit"], 50)

        # 축소(50→1)는 다음 주 경계 예약 — 목록의 has_pending 으로 보인다.
        self.quota.policy.set_limits(
            user_id=alice.id, created_at=alice.created_at,
            target=QuotaLimits(1, 1, QuotaStatus.ACTIVE),
        )
        detail = self.client.get(f"/admin/quota-policies/{alice.id}")
        body = detail.json()
        self.assertTrue(body["has_pending"])
        self.assertIsNotNone(body["pending"])
        self.assertEqual(body["pending"]["daily_limit"], 1)
        # 유효 한도는 아직 50 — 예약은 창 경계까지 기다린다.
        self.assertEqual(body["daily"]["limit"], 50)
        listed = self.client.get("/admin/quota-policies")
        entry = next(p for p in listed.json()["policies"]
                     if p["username"] == "alice")
        self.assertTrue(entry["has_pending"])

    def test_detail_matches_the_member_s_own_quota_numbers(self) -> None:
        # 관리자 화면과 회원 화면이 다른 산식을 말하면 지원 대화가 성립하지
        # 않는다 — 같은 snapshot 정의를 쓰는지를 두 표면에서 직접 비교한다.
        alice = self._member("alice")
        self.client.post("/auth/login",
                         json={"username": "alice", "password": "pw123"})
        mine = self.client.get("/me/quota").json()
        self.client.post("/auth/login",
                         json={"username": "root", "password": "pw789"})
        detail = self.client.get(f"/admin/quota-policies/{alice.id}").json()

        self.assertEqual(detail["daily"]["used"], mine["daily"]["used"])
        self.assertEqual(detail["daily"]["limit"], mine["daily"]["limit"])
        self.assertEqual(detail["status"], mine["status"])

    def test_unknown_user_is_404_and_non_admin_is_403(self) -> None:
        self.assertEqual(
            self.client.get("/admin/quota-policies/user:nope").status_code, 404)
        self.client.post("/auth/login",
                         json={"username": "alice", "password": "pw123"})
        self.assertEqual(
            self.client.get("/admin/quota-policies").status_code, 403)
        self.assertEqual(
            self.client.get(
                f"/admin/quota-policies/{self.root.id}").status_code, 403)


class AdminQuotaPolicyChangeApiTest(unittest.TestCase):
    """Phase 8.5-b (owner 2026-08-23): 한도 변경·정지/해제 + 감사.

    발효 규칙(P6) 자체는 도메인 셀이 잠근다 — 이 클래스는 HTTP 표면이 그걸
    올바르게 타는지(특히 **suspended 회원의 한도 변경이 정지를 몰래 풀지
    않는다**)와 감사(D3=ⓑ)를 본다.
    """

    def setUp(self) -> None:
        self.client, self.users, _ = _client()
        self.users.create_user(username="root", password="pw789", is_admin=True)
        self.client.post(
            "/auth/login", json={"username": "root", "password": "pw789"}
        )
        self.quota = self.client.app.state.quota

    def _member(self, username):
        return next(
            u for u in self.users.list_users() if u.username == username)

    def test_relief_applies_immediately_and_response_shows_effect(self) -> None:
        alice = self._member("alice")
        changed = self.client.post(
            f"/admin/quota-policies/{alice.id}/limits",
            json={"reason": "완화 테스트", "daily_limit": 50},
        )
        self.assertEqual(changed.status_code, 200)
        body = changed.json()
        self.assertEqual(body["daily"]["limit"], 50)   # 완화 = 즉시
        self.assertEqual(body["stored_daily_limit"], 50)
        self.assertFalse(body["has_pending"])

    def test_a_limits_change_does_not_lift_a_suspension(self) -> None:
        # ★ 이 슬라이스가 만든 위험과 그 폐쇄 — set_limits 는 status 미지정을
        # ACTIVE 로 해석하므로, 라우터가 현재 status 를 유지해 target 을 만드는
        # 것이 없으면 한도 변경 한 번에 정지가 풀린다.
        from services.application.app.quota.policy import QuotaStatus

        alice = self._member("alice")
        self.client.post(
            f"/admin/quota-policies/{alice.id}/suspend",
            json={"reason": "긴급 정지"},
        )
        changed = self.client.post(
            f"/admin/quota-policies/{alice.id}/limits",
            json={"reason": "정지 상태에서 한도 조정", "weekly_limit": 200},
        )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()["status"], "suspended")

    def test_suspend_is_immediate_and_activate_restores(self) -> None:
        alice = self._member("alice")
        suspended = self.client.post(
            f"/admin/quota-policies/{alice.id}/suspend",
            json={"reason": "긴급 정지"},
        )
        self.assertEqual(suspended.status_code, 200)
        self.assertEqual(suspended.json()["status"], "suspended")

        # 즉시다(D1ⓒ·D2) — 회원의 다음 요청 관점: /me/quota 가 이미 반영.
        self.client.post("/auth/login",
                         json={"username": "alice", "password": "pw123"})
        self.assertEqual(
            self.client.get("/me/quota").json()["status"], "suspended")
        self.client.post("/auth/login",
                         json={"username": "root", "password": "pw789"})

        restored = self.client.post(
            f"/admin/quota-policies/{alice.id}/activate",
            json={"reason": "해제"},
        )
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["status"], "active")

    def test_changes_are_audited_with_reason_but_reads_are_not(self) -> None:
        from services.application.app.auth.admin_audit import (
            AdminAuditService, InMemoryAdminAuditRepository,
        )

        repo = InMemoryAdminAuditRepository()
        audit = AdminAuditService(repo)
        client, users, _ = _client(admin_audit=audit)
        users.create_user(username="root", password="pw789", is_admin=True)
        client.post("/auth/login",
                    json={"username": "root", "password": "pw789"})
        alice = next(u for u in users.list_users() if u.username == "alice")

        # 읽기는 감사를 남기지 않는다(D3=ⓑ — 목록 polling 이 감사를 채운다).
        client.get("/admin/quota-policies")
        client.get(f"/admin/quota-policies/{alice.id}")
        self.assertEqual(repo.events, [])

        changed = client.post(
            f"/admin/quota-policies/{alice.id}/limits",
            json={"reason": "  사유 있는 변경  ", "daily_limit": 40},
        )
        self.assertEqual(changed.status_code, 200)
        client.post(f"/admin/quota-policies/{alice.id}/suspend",
                    json={"reason": "정지 사유"})
        self.assertEqual(len(repo.events), 2)
        row = repo.events[0]
        self.assertEqual(row.action, "member_quota_policy")
        self.assertEqual(row.target_type, "user")
        self.assertEqual(row.target_user_id, alice.id)
        self.assertIsNone(row.target_project_id)  # 회원 이벤트에 project 필드 없음
        self.assertEqual(row.reason, "사유 있는 변경")  # strip 되어 저장
        self.assertIn("daily", row.detail)
        self.assertEqual(row.outcome, "succeeded")

    def test_audit_failure_fails_the_request_closed(self) -> None:
        # fail-closed(D3=ⓑ): 감사 쓰기가 죽으면 요청도 죽는다 — 삼키면
        # "기록했지만 사실은 못 했다"가 된다.
        from services.application.app.auth.admin_audit import (
            AdminAuditService,
        )

        class _FailingRepo:
            def insert(self, event):
                raise RuntimeError("audit store down")

            def list_project_purge_events(self, *, limit):
                return ()

            def list_member_quota_events(self, *, limit):
                return ()

        audit = AdminAuditService(_FailingRepo())
        client, users, _ = _client(admin_audit=audit)
        users.create_user(username="root", password="pw789", is_admin=True)
        client.post("/auth/login",
                    json={"username": "root", "password": "pw789"})
        alice = next(u for u in users.list_users() if u.username == "alice")

        # fail-closed 의 정의 = 예외가 요청을 죽인다(삼키지 않는다). TestClient
        # 는 예외를 그대로 전파하므로 전파 자체를 단정한다 — 배포에서는 전역
        # handler 가 저장소 계열을 503 로, 그 외를 500 으로 바꾼다(v1.7.38).
        with self.assertRaises(RuntimeError):
            client.post(
                f"/admin/quota-policies/{alice.id}/suspend",
                json={"reason": "감사 죽는 경우"},
            )

    def test_validation_and_target_errors(self) -> None:
        alice = self._member("alice")
        base = f"/admin/quota-policies/{alice.id}/limits"
        # 둘 다 미지정 · 음수 · 공백 사유 → 400
        self.assertEqual(self.client.post(
            base, json={"reason": "r"}).status_code, 400)
        self.assertEqual(self.client.post(
            base, json={"reason": "r", "daily_limit": -1}).status_code, 400)
        self.assertEqual(self.client.post(
            base, json={"reason": "   ", "daily_limit": 5}).status_code, 400)
        # 없는 회원 → 404 (변경·정지 공통)
        self.assertEqual(self.client.post(
            "/admin/quota-policies/user:nope/limits",
            json={"reason": "r", "daily_limit": 5}).status_code, 404)
        self.assertEqual(self.client.post(
            "/admin/quota-policies/user:nope/suspend",
            json={"reason": "r"}).status_code, 404)
        # 비관리자 → 403
        self.client.post("/auth/login",
                         json={"username": "alice", "password": "pw123"})
        self.assertEqual(self.client.post(
            base, json={"reason": "r", "daily_limit": 5}).status_code, 403)


class CombinedBoundaryMatrixTest(unittest.TestCase):
    """D8-3c: the 401 and 403 guards audited as a single matrix.

    3-a proved "every operation is protected" and 3-b proved "every project
    operation is owned". Each was exhaustive **in its own dimension**, which
    leaves the cells that only exist where the two meet unowned: whether a
    sessionless request to someone else's project answers 401 or 403, and
    whether the owner the ownership guard is supposed to let through actually
    gets through on all 59 rather than on the one route a sample checked
    (verification H-1).

    This slice adds no policy and changes no behaviour — it fills those cells
    and pins the tier of every operation, so a new endpoint cannot land outside
    all three tiers without a test naming it.

    Tier membership is derived from the **route's dependencies**, not from the
    path shape: the path is what the operation looks like, the dependency list
    is what actually enforces, and the whole point of an audit is to read the
    enforcing side.

    Two cells of the matrix are deliberately **not** here, because the slice that
    introduced them already drives them exhaustively and absorbing them would
    leave an axis undefended if this class ever broke: sessionless → 401 on all
    61 protected operations lives in ``AuthenticationBoundaryTest``, and
    authenticated-but-not-the-owner → 403 on all 59 project operations lives in
    ``ProjectAuthorizationTest``. Read all three as one matrix (verification H-c).
    """

    # Protected, but naming no project — so there is no owner to check and no
    # 403 to declare. Spelled out for the same reason ``PUBLIC`` is: a third
    # entry appearing here is a decision, not an accident.
    AUTH_ONLY = {
        ("/projects", "post"): "creates the project, so ownership is an output "
                               "of this call rather than an input",
        ("/projects", "get"): "names no project: isolation is the store query "
                              "narrowed to the caller, not a 403",
        ("/me/quota", "get"): "8.4 W5=B — 자기 사용량은 회원 단위 사실이라 "
                              "project 를 지목하지 않는다. 남의 quota 는 경로가 "
                              "없어서 못 읽는다(관리자 조회는 8.5의 별도 tier)",
        ("/me/activity", "get"): "9.2 P1=ⓐ·P8=ⓐ — 통합 활동은 **소유 프로젝트 "
                                 "집합**을 세션 주체에서 유도하므로 project 를 "
                                 "지목하지 않는다. **경로가 project id 를 받지 "
                                 "않는 것이 S-3(IDOR 표면 없음)이다** — 남의 "
                                 "프로젝트는 요청할 방법 자체가 없다",
    }

    # D8-5's tier. Admin operations name no project on purpose: the admin
    # surface manages accounts, and reaching another user's project content is
    # the audited, expiring grant of F1=C — a different mechanism, not this one.
    ADMIN = {
        # D8-5b: 전 프로젝트 **메타데이터** 목록. project 를 지목하지 않으므로
        # `_ADMIN_PROJECT_ROUTES` 예외가 아니라 평범한 admin tier 다. 내용은 주지
        # 않는다 — 그것은 여전히 D8-5e 승격을 거친다.
        ("/admin/projects", "get"),
        ("/admin/users", "get"),
        ("/admin/users", "post"),
        ("/admin/users/{user_id}/deactivate", "post"),
        # Phase 8.5-a (owner 2026-08-23, plans/08-5-usage-admin-cms-decisions.md):
        # the quota operations read surface. Reads only — changes/suspend and
        # their audit are 8.5-b. Not project-scoped: the subject is users.id.
        ("/admin/quota-policies", "get"),
        ("/admin/quota-policies/{user_id}", "get"),
        # 8.5-b (2026-08-23): changes + suspend/activate. Audited (D3=ⓑ) —
        # unlike the account operations above, member-policy *writes* leave
        # an admin_audit_events row with a mandatory reason.
        ("/admin/quota-policies/{user_id}/limits", "post"),
        ("/admin/quota-policies/{user_id}/suspend", "post"),
        ("/admin/quota-policies/{user_id}/activate", "post"),
        # Signup approval (owner 2026-08-22): requests are public, the check is
        # admin. These three are account operations like users above — not
        # admin-audited, not project-scoped.
        ("/admin/signup-requests", "get"),
        ("/admin/signup-requests/{user_id}/approve", "post"),
        ("/admin/signup-requests/{user_id}/reject", "post"),
        # D8-5c. Aggregate counts over every project's LLM-call audit — which is
        # why it sits in this tier rather than the project one: it names no
        # project and reads no project's content.
        ("/admin/observability/kpi", "get"),
        ("/admin/audit-events", "get"),
        # D8-6d: admin project 영구 파기(204, ADMIN tier). project_id 경로지만 소유권이
        # 아니라 관리자 검사를 쓰므로 project tier 가 아닌 admin tier.
        ("/admin/projects/{project_id}/purge", "post"),
        # D8-5e: 승격 발급(201). 같은 이유로 admin tier — 경로가 project 를 지목하지만
        # 검사는 "관리자인가"이지 "소유자인가"가 아니다. 이 operation 이 여는 것은
        # **읽기 전용·만료되는** 접근이며, 그 시행은 require_project_owner 안에 있다.
        ("/admin/projects/{project_id}/access-grants", "post"),
    }

    def setUp(self) -> None:
        self.core_sot = CoreSotService(InMemoryCoreSotRepository())
        self.client, self.users, self.sessions = _client(core_sot=self.core_sot)
        self.app = self.client.app
        self.spec = self.app.openapi()
        self.bob = self.users.create_user(username="bob", password="pw456")

    def _tiers(self):
        """Yield (route, path, method, tier) for every operation."""
        for route in self.app.routes:
            if not isinstance(route, APIRoute):
                continue
            declared = [d.dependency for d in route.dependencies]
            if require_project_owner in declared:
                tier = "project"
            elif require_admin_user in declared:
                tier = "admin"
            elif require_authenticated_user in declared:
                tier = "auth"
            else:
                tier = "public"
            for method in sorted(route.methods):
                yield route, route.path, method.lower(), tier

    def _project_operations(self):
        for _route, path, method, tier in self._tiers():
            if tier == "project":
                yield path, method

    def _url(self, path: str, project_id: str) -> str:
        # Sub-resource ids are deliberately fabricated: every cell below is
        # about the guard, which runs before the handler ever looks them up.
        return re.sub(
            r"\{[^}]+\}", "does-not-exist", path.replace("{project_id}", project_id)
        )

    def _login_alice(self) -> str:
        response = self.client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )
        return response.json()["user"]["id"]

    def test_every_operation_lands_in_exactly_one_named_tier(self) -> None:
        # The no-empty-cell guard. Every operation is classified by what guards
        # it, and each tier's membership is pinned: an endpoint added without a
        # dependency shows up as an unexpected public operation instead of
        # quietly inheriting whatever the matrix assumed.
        tiers = {(path, method): tier for _r, path, method, tier in self._tiers()}
        by_tier: dict[str, set] = {
            "public": set(), "auth": set(), "admin": set(), "project": set(),
        }
        for operation, tier in tiers.items():
            by_tier[tier].add(operation)

        # Reuses 3-a's exemption literal rather than restating it: two lists of
        # "which operations are open" would eventually disagree.
        self.assertEqual(by_tier["public"], set(AuthenticationBoundaryTest.PUBLIC))
        self.assertEqual(by_tier["auth"], set(self.AUTH_ONLY))
        self.assertEqual(by_tier["admin"], self.ADMIN)
        # Phase 9 A5=B 가 `GET /projects/{id}/activity` 를 더해 62/77 이 됐고,
        # Slice 9.2 P1=ⓐ 가 `GET /me/activity` 를 **인증 전용** tier 에 더해 78 이
        # 됐다(project tier 는 무변 62 — 통합 조회는 project 를 지목하지 않는다).
        # 가입 승인 슬라이스(2026-08-22)가 `POST /auth/signup` 을 공개 tier 에
        # 더해 79 가 됐다 — 요청은 누구나, 승인은 관리자.
        # Phase 8.5-a/b(2026-08-23)가 quota 운영 5종을 admin tier 에 더해 87 이
        # 됐다(ADMIN 11→16).
        self.assertEqual(len(by_tier["project"]), 62)
        self.assertEqual(len(tiers), 87)  # 8.5-b: quota 변경·정지 3종
        # A project tier derived from dependencies must coincide with the path
        # shape; the reverse direction is locked by ProjectAuthorizationTest.
        for path, method in by_tier["project"]:
            with self.subTest(path=path, method=method):
                self.assertIn("{project_id}", path)

    def test_the_two_guards_are_declared_as_one_consistent_stack(self) -> None:
        # Joint declaration invariants — the ones no single slice's own guard can
        # state, because each sees only its own axis:
        #   * 403 without 401 would advertise "you are logged in but refused" on
        #     an operation that never requires logging in.
        #   * an authorization dependency without the authentication dependency
        #     would leave the exhaustive 3-a guard blind to a protected route,
        #     even though the sub-dependency would still resolve.
        #   * a repeated identity is the drift a copy-pasted `dependencies=`
        #     list produces, and it makes "is this route guarded" ambiguous.
        #   * 403 has three producers: D8-5's two boundaries (ownership, admin)
        #     and — since signup approval (owner 2026-08-22) — the login
        #     handshake itself, which answers 403 to a correct password on a
        #     pending/rejected account. That third producer lives only on
        #     /auth/login; a 403 on any other operation is a false declaration.
        for route, path, method, tier in self._tiers():
            with self.subTest(path=path, method=method):
                declared = [d.dependency for d in route.dependencies]
                responses = self.spec["paths"][path][method]["responses"]
                if "403" in responses:
                    self.assertIn("401", responses)
                for authorization in (require_project_owner, require_admin_user):
                    if authorization in declared:
                        self.assertIn(require_authenticated_user, declared)
                    self.assertLessEqual(declared.count(authorization), 1)
                self.assertLessEqual(declared.count(require_authenticated_user), 1)
                if path == "/auth/login":
                    # The third producer, shape-asserted: an authorization-free
                    # public route whose 403 is an account-state answer.
                    self.assertEqual(tier, "public")
                    self.assertIn("403", responses)
                else:
                    self.assertEqual(
                        tier in ("project", "admin"), "403" in responses
                    )
                # The two authorization boundaries are alternatives, never a
                # stack: an operation behind both would have two different
                # meanings for the same status.
                self.assertFalse(
                    require_project_owner in declared
                    and require_admin_user in declared
                )

    def test_authentication_answers_before_ownership_on_every_project_route(self) -> None:
        # The load-bearing joint cell. A sessionless request naming *someone
        # else's* project satisfies both deny conditions, and the two guards
        # would report it differently: 401 says "log in", 403 says "you are the
        # wrong user". Answering 403 here would tell an anonymous caller that
        # the project exists and belongs to somebody — and would mean the
        # ownership lookup ran for an unauthenticated request.
        foreign = self.core_sot.create_project(name="Bob's", owner_id=self.bob.id)
        # This client never logged in; asserted rather than assumed, because the
        # whole cell is void if the fixture ever starts handing out a session.
        self.assertEqual(self.client.get("/auth/me").status_code, 401)

        for path, method in self._project_operations():
            with self.subTest(path=path, method=method):
                response = self.client.request(method, self._url(path, foreign.id))
                self.assertEqual(
                    response.status_code, 401,
                    f"{method.upper()} {path} answered {response.status_code} to a "
                    f"sessionless request for another user's project",
                )

    def test_the_ownership_dependency_cannot_run_without_authentication(self) -> None:
        # Measured while mutating the cell above: the project routes declare the
        # authentication dependency *and* the ownership dependency declares it as
        # a sub-dependency, so deleting either one alone leaves every observable
        # status unchanged — the surviving layer answers. That redundancy is the
        # point, and it is also why no cell driven against the real app can see
        # one layer go missing.
        #
        # So the inner layer is driven in isolation instead: a throwaway app that
        # mounts *only* ``require_project_owner``, with the outer layer removed
        # on purpose. Asserting a status rather than the parameter default keeps
        # this refactor-tolerant — swapping the sub-dependency for a composed or
        # wrapped one keeps this green as long as it still authenticates, which
        # is the property being locked (verification H-a).
        probe = FastAPI()
        probe.state.core_sot = self.core_sot
        probe.state.users = self.users
        probe.state.sessions = self.sessions
        # D8-5e: the dependency also reads ``access_grants``. Today the grant
        # branch short-circuits on ``is_admin`` before touching it, so leaving
        # this out happened to work — but then this cell fails with
        # ``AttributeError: 'State' object has no attribute 'access_grants'``
        # instead of asserting its property, which is what a 2026-08-02
        # mutation actually produced (and what made a crash look like the
        # isolation property being detected). Wiring it keeps the failure
        # meaningful if the branch order ever changes.
        probe.state.access_grants = AccessGrantService(
            InMemoryAccessGrantRepository()
        )

        @probe.get(
            "/projects/{project_id}/probe",
            dependencies=[Depends(require_project_owner)],
        )
        async def _probe() -> dict[str, bool]:
            return {"reached": True}

        alice_id = self._login_alice()
        owned = self.core_sot.create_project(name="Alice's", owner_id=alice_id)
        foreign = self.core_sot.create_project(name="Bob's", owner_id=self.bob.id)
        client = TestClient(probe, base_url="https://testserver")

        self.assertEqual(client.get(f"/projects/{foreign.id}/probe").status_code, 401)

        # Over-strict half, and the reason the 401 above means anything: with a
        # session the same unguarded-by-the-outer-layer route runs, so the 401 is
        # the inner layer refusing rather than the probe app being misassembled.
        client.cookies = self.client.cookies
        self.assertEqual(client.get(f"/projects/{owned.id}/probe").status_code, 200)
        self.assertEqual(client.get(f"/projects/{foreign.id}/probe").status_code, 403)

    def test_the_owner_passes_the_guard_on_every_project_operation(self) -> None:
        # Verification H-1, over-strict half: a boundary that refused everything
        # would satisfy every deny cell in this matrix and ship a dead product.
        # Only the guard is asserted — what the handler then answers (200, a 422
        # for the body this bare call omits, a 404 for the fabricated
        # sub-resource id) is each endpoint's own contract, locked elsewhere.
        alice_id = self._login_alice()
        for path, method in self._project_operations():
            # A fresh project per operation: some of these archive or mutate,
            # and a shared one would make the matrix order-dependent.
            owned = self.core_sot.create_project(name="Alice's", owner_id=alice_id)
            with self.subTest(path=path, method=method):
                response = self.client.request(method, self._url(path, owned.id))
                self.assertNotIn(
                    response.status_code, (401, 403),
                    f"{method.upper()} {path} refused the project's own owner",
                )

    def test_an_unowned_project_is_refused_on_every_project_operation(self) -> None:
        # Verification H-1 + E1=A. ``owner_id=None`` is the shape a pre-auth
        # project, a deleted account, or a failed migration leaves behind, and
        # the owner decision is that it is denied everywhere — not adopted by
        # the first caller who asks.
        self._login_alice()
        unowned = self.core_sot.create_project(name="Unowned")
        self.assertIsNone(unowned.owner_id)

        for path, method in self._project_operations():
            with self.subTest(path=path, method=method):
                response = self.client.request(method, self._url(path, unowned.id))
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), {"detail": "forbidden"})

    def test_a_missing_project_is_404_on_every_project_operation(self) -> None:
        # Verification H-1, third branch. 403 hides nothing about existence, so
        # a project that is absent must keep saying so instead of being folded
        # into the ownership refusal — otherwise the owner of a deleted project
        # is told they lack permission to their own missing data.
        self._login_alice()
        for path, method in self._project_operations():
            with self.subTest(path=path, method=method):
                response = self.client.request(
                    method, self._url(path, "does-not-exist")
                )
                self.assertEqual(response.status_code, 404)

    def test_the_non_project_operations_serve_any_authenticated_user(self) -> None:
        # Over-strict guard for the middle tier: ownership must not creep into
        # the two operations that name no project. Bob owns nothing, and both
        # still work for him — the list is empty because the store query is
        # narrowed, not because a guard refused.
        self.client.post("/auth/login", json={"username": "bob", "password": "pw456"})

        listed = self.client.get("/projects")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json(), {"projects": []})

        created = self.client.post("/projects", json={"name": "Bob's first"})
        self.assertEqual(created.status_code, 200)
        self.assertEqual(
            self.client.get("/projects").json()["projects"][0]["name"], "Bob's first"
        )

    def test_every_admin_operation_refuses_an_authenticated_non_admin(self) -> None:
        # D8-5's row, under-strict half. Alice is a perfectly valid user, so the
        # only thing standing between her and the admin surface is the flag —
        # and the guard runs before request validation, so a bare call with no
        # body is enough to prove it is in front of the handler (a 422 here
        # would mean the body was parsed before anyone checked who she is).
        self._login_alice()
        for path, method in sorted(self.ADMIN):
            with self.subTest(path=path, method=method):
                url = re.sub(r"\{[^}]+\}", "does-not-exist", path)
                response = self.client.request(method, url)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), {"detail": "forbidden"})

    def test_every_admin_operation_admits_an_admin(self) -> None:
        # Over-strict half: a boundary that refused everyone would satisfy the
        # cell above and ship an admin surface nobody can use.
        self.users.create_user(username="root", password="pw789", is_admin=True)
        self.client.post(
            "/auth/login", json={"username": "root", "password": "pw789"}
        )
        for path, method in sorted(self.ADMIN):
            with self.subTest(path=path, method=method):
                url = re.sub(r"\{[^}]+\}", "does-not-exist", path)
                response = self.client.request(method, url)
                self.assertNotIn(response.status_code, (401, 403))

    def test_the_admin_dependency_cannot_run_without_authentication(self) -> None:
        # Same isolation drive as the ownership dependency, for the same reason:
        # the admin routes declare the authentication dependency *and*
        # ``require_admin_user`` re-declares it, so dropping either layer alone
        # changes no observable status. This mounts the inner one alone.
        probe = FastAPI()
        probe.state.users = self.users
        probe.state.sessions = self.sessions

        @probe.get("/probe", dependencies=[Depends(require_admin_user)])
        async def _probe() -> dict[str, bool]:
            return {"reached": True}

        client = TestClient(probe, base_url="https://testserver")
        self.assertEqual(client.get("/probe").status_code, 401)

        # And with a session it still refuses a non-admin — the 401 above is the
        # authentication layer, not the admin check answering everything.
        self._login_alice()
        client.cookies = self.client.cookies
        self.assertEqual(client.get("/probe").status_code, 403)

    def test_the_public_row_is_answered_by_handlers_not_by_a_guard(self) -> None:
        # Completes the matrix's fourth row. The tier partition proves no public
        # operation *declares* a guard; this proves none behaves as if it had
        # one. ``/auth/login`` is the discriminator: a guarded operation refuses
        # a bodyless call with 401 before validation runs, so 422 here is
        # positive evidence that the request reached the handler's own contract.
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.post("/auth/logout").status_code, 200)
        self.assertEqual(self.client.post("/auth/login").status_code, 422)
        self.assertEqual(self.client.get("/auth/me").status_code, 401)


class TestSeamStaysAnOverrideTest(unittest.TestCase):
    """``tests/auth_support.py`` must never become a switch that turns the
    boundary off.

    Nineteen domain suites run authenticated through that seam, so if it ever
    started *removing* the dependency instead of resolving it, every one of them
    would keep passing while the guard above lost its subject. Two properties
    keep that from happening silently, and both are asserted here rather than
    left to the docstring that currently states them.
    """

    def test_authenticating_an_app_leaves_route_declarations_untouched(self) -> None:
        client, _, _ = _client()
        app = client.app

        def declarations():
            return {
                (route.path, tuple(sorted(route.methods))):
                    [dep.dependency for dep in route.dependencies]
                for route in app.routes if isinstance(route, APIRoute)
            }

        before = declarations()
        authenticate(app)

        # The seam may only add to dependency_overrides. Emptying a route's
        # `dependencies` would make an unguarded endpoint indistinguishable from
        # a guarded one for the exhaustive guard.
        self.assertEqual(declarations(), before)
        # The list is pinned, not just length-checked: adding a third override
        # must be a deliberate edit here. Slice 8.3 added ``enforce_quota`` —
        # the duplicate-request lock it turns on has a 5-second minimum window,
        # so a domain suite POSTing the same billable action twice would 429 for
        # reasons unrelated to its subject. Its own boundary is driven
        # un-overridden in ``tests/test_quota_enforcement_api.py``, the same way
        # this module drives the two above.
        self.assertEqual(
            list(app.dependency_overrides),
            [require_authenticated_user, require_project_owner, enforce_quota],
        )

    def test_this_module_drives_apps_that_are_not_overridden(self) -> None:
        # The guard's whole value is that it runs against the deployed
        # resolution path. A future global/autouse override would neuter it and
        # nothing else would notice — this is what notices.
        client, _, _ = _client()
        self.assertEqual(client.app.dependency_overrides, {})


class ForcedPasswordChangeTest(unittest.TestCase):
    """C-6 (오너 2026-08-02): 관리자가 정한 비밀번호는 **1회용**이다.

    D8-5a 독립 검증 H-c 가 남긴 위험 — *관리자가 사용자의 비밀번호를 아는 상태* — 를
    없앤다. 강제 지점은 **세션 발급**이지 개별 operation 이 아니다: 그래서 나머지 73개
    operation 은 검사도, 새 상태코드도 얻지 않고 "403 생산자는 정확히 둘"이라는 불변식이
    그대로 유지된다.
    """

    def setUp(self) -> None:
        self.client, self.users, _ = _client()
        self.users.create_user(
            username="carol", password="admin-set", must_change_password=True
        )

    def _login(self, **extra):
        return self.client.post(
            "/auth/login",
            json={"username": "carol", "password": "admin-set", **extra},
        )

    def test_the_admin_set_password_alone_never_yields_a_session(self) -> None:
        # 이 셀이 C-6 의 전부다. 여기가 200 이면 관리자가 아는 비밀번호로 계정을
        # 그대로 쓸 수 있다는 뜻이고, 슬라이스가 아무것도 안 한 것이 된다.
        response = self._login()
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("set-cookie", response.headers)

    def test_spending_it_on_a_replacement_signs_in(self) -> None:
        response = self._login(new_password="carol-chosen-passphrase")
        self.assertEqual(response.status_code, 200)
        self.assertIn("session", response.cookies)
        self.assertEqual(self.client.get("/auth/me").status_code, 200)

    def test_the_old_password_stops_working_afterwards(self) -> None:
        # under-strict: 교체가 실제로 저장되지 않으면 옛 비밀번호가 계속 통한다.
        self._login(new_password="carol-chosen-passphrase")
        self.client.post("/auth/logout")
        self.assertEqual(self._login().status_code, 401)
        self.assertEqual(
            self.client.post(
                "/auth/login",
                json={"username": "carol", "password": "carol-chosen-passphrase"},
            ).status_code, 200,
        )

    def test_the_change_is_required_only_once(self) -> None:
        # over-strict: 플래그가 안 지워지면 사용자가 로그인할 때마다 비밀번호를
        # 바꿔야 한다 — 계정을 못 쓰게 만드는 과잉 교정 방향이다.
        self._login(new_password="carol-chosen-passphrase")
        self.client.post("/auth/logout")
        again = self.client.post(
            "/auth/login",
            json={"username": "carol", "password": "carol-chosen-passphrase"},
        )
        self.assertEqual(again.status_code, 200)

    def test_a_wrong_password_is_401_whether_or_not_a_change_is_due(self) -> None:
        # 409 가 열거 신호가 되면 안 된다 — 자격증명 검증이 **먼저**이므로, 틀린
        # 비밀번호는 교체 대기 여부와 무관하게 401 이다.
        wrong_pending = self.client.post(
            "/auth/login", json={"username": "carol", "password": "nope"}
        )
        wrong_normal = self.client.post(
            "/auth/login", json={"username": "alice", "password": "nope"}
        )
        self.assertEqual(wrong_pending.status_code, 401)
        self.assertEqual(wrong_normal.status_code, 401)
        self.assertEqual(wrong_pending.json(), wrong_normal.json())

    def test_a_new_password_below_the_policy_is_400_and_changes_nothing(self) -> None:
        response = self._login(new_password="short")
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("set-cookie", response.headers)
        # 거부가 상태를 남기지 않는다: 옛 비밀번호로 여전히 교체를 요구받는다.
        self.assertEqual(self._login().status_code, 409)

    def test_the_minimum_length_is_the_pinned_literal(self) -> None:
        # 계약 리터럴. 정확히 경계 위/아래를 친다 — 밴드로 두면 정책을 1자로
        # 낮추는 변경도 통과한다.
        self.assertEqual(MIN_PASSWORD_LENGTH, 12)
        self.assertEqual(
            self._login(new_password="a" * (MIN_PASSWORD_LENGTH - 1)).status_code, 400
        )
        self.assertEqual(
            self._login(new_password="a" * MIN_PASSWORD_LENGTH).status_code, 200
        )

    def test_offering_a_new_password_when_none_is_due_is_refused(self) -> None:
        # 조용히 무시하면 "비밀번호를 바꿨다"고 믿는 클라이언트에게 거짓말이 된다.
        response = self.client.post(
            "/auth/login",
            json={
                "username": "alice", "password": "pw123",
                "new_password": "irrelevant-but-long-enough",
            },
        )
        self.assertEqual(response.status_code, 409)

    def test_the_two_admin_surfaces_mark_the_password_single_use(self) -> None:
        # 디스커버리 가드. `create_user` 의 기본값은 False 이고(도메인은 누가 정한
        # 비밀번호인지 모른다), **남의 비밀번호를 정하는 두 표면**이 True 를 준다.
        # 여기가 없으면 새 표면이 조용히 기본값을 물려받는다.
        #
        # ★ **호출부를 AST 로 읽는다.** 첫 판은 `assertIn("must_change_password=True")`
        # 부분문자열 그렙이었는데, 2026-08-02 독립 검증이 반증했다 — 실제 인자를
        # 지우고 **주석에 그 문자열만 남겨도 통과**했다(false negative). 즉 그 셀은
        # "호출부가 플래그를 준다"가 아니라 "파일 어딘가에 그 글자가 있다"를 잠그고
        # 있었다. 소스를 파싱해 `create_user(...)` 호출의 키워드를 직접 본다.
        for label, relative in [
            ("POST /admin/users", "services/application/app/routers/admin.py"),
            ("scripts/create_user.py", "scripts/create_user.py"),
        ]:
            with self.subTest(surface=label):
                self.assertEqual(
                    _create_user_flags(relative), [True],
                    f"{label}: create_user 호출이 정확히 하나이고 "
                    "must_change_password=True 를 줘야 한다",
                )

        # 반대 방향: 자기 계정을 스스로 발급하는 smoke 스크립트는 주면 안 된다
        # (아무도 그 비밀번호를 모르고, 강제하면 스크립트가 못 돈다).
        self.assertEqual(
            _create_user_flags("scripts/phase2a_provider_live_smoke.py"), [False]
        )


class AdminProjectListTest(unittest.TestCase):
    """D8-5b: 전 프로젝트 **메타데이터** 목록.

    미인증 401·비관리자 403 은 CombinedBoundaryMatrixTest 가 ADMIN tier 전수로 잠근다.
    여기는 이 endpoint 의 **경계**를 잠근다 — 소유자를 가리지 않고 전부 보이되,
    **내용은 주지 않는다**(그것은 여전히 D8-5e 승격을 거친다).
    """

    def setUp(self) -> None:
        self.core_sot = CoreSotService(InMemoryCoreSotRepository())
        self.client, self.users, _ = _client(core_sot=self.core_sot)
        self.root = self.users.create_user(
            username="root", password="pw789", is_admin=True
        )
        self.alice = self.users._repo.get_by_username("alice")
        self.client.post("/auth/login",
                         json={"username": "root", "password": "pw789"})

    def test_it_lists_projects_of_every_owner_including_unowned(self) -> None:
        # 관리자 목록의 존재 이유. 소유자별 필터(GET /projects)와 정반대 방향이라,
        # 여기가 소유자로 좁혀지면 endpoint 가 무의미해진다.
        self.core_sot.create_project(name="Alice's", owner_id=self.alice.id)
        self.core_sot.create_project(name="Root's", owner_id=self.root.id)
        self.core_sot.create_project(name="Orphan")

        projects = self.client.get("/admin/projects").json()["projects"]
        self.assertEqual(
            {p["name"] for p in projects}, {"Alice's", "Root's", "Orphan"}
        )
        by_name = {p["name"]: p for p in projects}
        self.assertEqual(by_name["Alice's"]["owner_id"], self.alice.id)
        self.assertIsNone(by_name["Orphan"]["owner_id"])

    def test_archived_projects_are_included_and_flagged(self) -> None:
        # archive 는 soft delete 라 "무엇이 존재하나"에 답할 때 빠지면 안 된다.
        project = self.core_sot.create_project(
            name="Shelved", owner_id=self.alice.id
        )
        self.core_sot.archive_project(project_id=project.id)
        [row] = self.client.get("/admin/projects").json()["projects"]
        self.assertTrue(row["archived"])

    def test_the_listing_carries_no_project_contents(self) -> None:
        # ★ over-strict 경계. 이 endpoint 가 내용을 흘리기 시작하면 D8-5e 승격
        # (사유·만료·감사)을 우회하는 뒷문이 된다. 필드 집합을 정확히 단정한다 —
        # 필드가 늘면 그것은 결정이지 사고여서는 안 된다.
        #
        # **이 셀이 잠그는 것은 `AdminProjectPayload` 모델이다.** 핸들러 dict 에
        # 필드를 더하는 것만으로는 응답이 안 바뀐다 — `response_model` 이 여분을
        # 걸러 내기 때문이다(뮤테이션으로 실측). 필드가 클라이언트에 실제로 닿는
        # 유일한 경로가 모델이므로, 겨눌 곳도 거기다.
        self.core_sot.create_project(name="Novel", owner_id=self.alice.id)
        [row] = self.client.get("/admin/projects").json()["projects"]
        self.assertEqual(set(row), {"id", "name", "archived", "owner_id"})

    def test_listing_a_project_is_not_recorded_as_an_access(self) -> None:
        # 목록은 접근이 아니다 — 승격 감사(C-3)는 project **내용**에 닿은 요청만
        # 센다. 여기가 기록되면 접근 이력이 관리자의 목록 조회로 오염된다.
        project = self.core_sot.create_project(
            name="Novel", owner_id=self.alice.id
        )
        self.client.get("/admin/projects")
        self.client.post("/auth/logout")
        self.client.post("/auth/login",
                         json={"username": "alice", "password": "pw123"})
        entries = self.client.get(
            f"/projects/{project.id}/access-log"
        ).json()["entries"]
        self.assertEqual(entries, [])


class AdminAccessGrantTest(unittest.TestCase):
    """D8-5e (F1=C): 관리자의 만료되는 **읽기 전용** project 접근.

    미인증 401·비관리자 403(발급 endpoint)은 CombinedBoundaryMatrixTest 가 ADMIN tier
    전수로 잠근다. 여기는 **승격이 실제로 무엇을 열고 무엇을 열지 않는가**를 양방향으로
    잠근다 — 열려야 할 읽기가 열리고(under-strict), 열리면 안 되는 쓰기·만료·타 project
    가 닫혀 있다(over-strict).
    """

    def setUp(self) -> None:
        self.now = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
        self.core_sot = CoreSotService(InMemoryCoreSotRepository())
        self.grants = AccessGrantService(
            InMemoryAccessGrantRepository(), clock=lambda: self.now
        )
        self.client, self.users, _ = _client(
            core_sot=self.core_sot, access_grants=self.grants
        )
        self.root = self.users.create_user(
            username="root", password="pw789", is_admin=True
        )
        # alice 소유 project — 관리자(root)의 것이 아니다. 저장소에 직접 만든다:
        # 이 클래스가 보는 것은 소유권 경계이지 생성 경로가 아니다.
        alice = self.users._repo.get_by_username("alice")
        self.project = self.core_sot.create_project(
            name="Novel", owner_id=alice.id
        ).id
        self.client.post("/auth/login",
                         json={"username": "root", "password": "pw789"})

    def _issue(self, reason: str = "지원 요청 #12 확인"):
        return self.client.post(
            f"/admin/projects/{self.project}/access-grants",
            json={"reason": reason},
        )

    def test_issuing_records_the_reason_and_a_one_hour_expiry(self) -> None:
        # C-1(1시간)·C-5(사유)는 계약 리터럴이다. 발급 응답이 그것을 그대로 싣는다.
        response = self._issue()
        self.assertEqual(response.status_code, 201)
        grant = response.json()["grant"]
        self.assertEqual(grant["project_id"], self.project)
        self.assertEqual(grant["reason"], "지원 요청 #12 확인")
        self.assertEqual(
            datetime.fromisoformat(grant["expires_at"])
            - datetime.fromisoformat(grant["created_at"]),
            timedelta(hours=1),
        )

    def test_a_blank_reason_is_refused(self) -> None:
        # C-5. 공백만 있는 사유는 `str` 로는 통과하지만 아무것도 기록하지 않는다.
        self.assertEqual(self._issue("   ").status_code, 422)

    def test_a_grant_for_a_missing_project_is_404_not_201(self) -> None:
        # 없는 project 에 대한 승격은 아무것도 아닌 것에 대한 감사 기록이고,
        # 201 이 project id 존재 여부를 알려 주는 probe 가 된다.
        response = self.client.post(
            "/admin/projects/does-not-exist/access-grants",
            json={"reason": "probe"},
        )
        self.assertEqual(response.status_code, 404)

    def test_without_a_grant_an_admin_is_still_refused(self) -> None:
        # 관리자라는 것만으로는 남의 project 를 못 읽는다 — 승격이 유일한 통로다.
        self.assertEqual(
            self.client.get(f"/projects/{self.project}/drafts").status_code, 403
        )

    def test_a_live_grant_opens_reads_on_that_project(self) -> None:
        self._issue()
        self.assertEqual(
            self.client.get(f"/projects/{self.project}/drafts").status_code, 200
        )

    def test_a_live_grant_never_opens_writes(self) -> None:
        # C-2 읽기 전용. 승격이 살아 있어도 쓰기는 403이다 — 관리자가 남의 원고를
        # 고칠 수 있으면 정본 보존 정책과 충돌한다. 방법 판정이라 새 endpoint 도 자동으로
        # 닫힌 쪽에서 시작한다(fail-closed).
        self._issue()
        for method, path in [
            ("post", f"/projects/{self.project}/drafts"),
            ("patch", f"/projects/{self.project}"),
            ("delete", f"/projects/{self.project}"),
        ]:
            with self.subTest(method=method, path=path):
                response = self.client.request(
                    method.upper(), path, json={"name": "X"}
                )
                self.assertEqual(response.status_code, 403)

    def test_the_grant_stops_working_when_it_expires(self) -> None:
        # C-1. 만료는 판정이지 삭제가 아니다 — 아래 append-only 셀이 짝이다.
        self._issue()
        self.now += timedelta(hours=1, seconds=1)
        self.assertEqual(
            self.client.get(f"/projects/{self.project}/drafts").status_code, 403
        )

    def test_an_expired_grant_row_survives_as_the_audit_record(self) -> None:
        # C-3. 발급 기록은 만료 뒤에도 남아야 "무엇을 왜 봤는가"가 답해진다.
        # 이 셀이 없으면 누군가 만료 승격을 지우는 "정리"를 넣어도 아무도 모른다.
        self._issue("감사 대상")
        self.now += timedelta(days=365)
        row = self.grants._repo.latest_for(
            admin_user_id=self.root.id, project_id=self.project
        )
        self.assertIsNotNone(row)
        self.assertEqual(row.reason, "감사 대상")

    def test_a_grant_does_not_reach_a_different_project(self) -> None:
        # 승격은 한 project 를 지목한다. 여기가 새면 "전 project 열람"이 된다.
        alice = self.users._repo.get_by_username("alice")
        other = self.core_sot.create_project(name="Other", owner_id=alice.id).id
        self._issue()
        self.assertEqual(
            self.client.get(f"/projects/{other}/drafts").status_code, 403
        )

    def test_a_grant_held_by_a_non_admin_does_not_work(self) -> None:
        # 승격은 관리자 자격과 **함께** 검사된다(is_admin AND live grant). 강등된
        # 관리자의 살아 있는 승격이 그 역할보다 오래 사는 것을 막는다 — 승격만 보면
        # 강등이 무의미해진다.
        bob = self.users.create_user(username="bob", password="pw000")
        self.assertFalse(bob.is_admin)
        self.grants.issue(
            admin_user_id=bob.id, project_id=self.project, reason="비관리자 승격"
        )
        self.client.post("/auth/logout")
        self.client.post("/auth/login",
                         json={"username": "bob", "password": "pw000"})
        self.assertEqual(
            self.client.get(f"/projects/{self.project}/drafts").status_code, 403
        )

    def test_a_grant_does_not_adopt_an_unowned_project(self) -> None:
        # E1=A: `owner_id=None` 은 **항상** deny 다. 승격도 예외가 아니다 — 승격은
        # 소유권을 지나는 통로이지 주인 없는 project 를 입양하는 수단이 아니다.
        #
        # 2026-08-02 독립 검증 Blocking. 첫 판은 두 번째 분기(승격)에 owner_id 검사가
        # 없어 **무소유 project + 승격 → 200** 이었다. SoT 세 곳과 docstring 이 반대를
        # 단언하고 있었는데도 AdminAccessGrantTest 11셀이 전부 alice 소유 project 만
        # 써서 **이 조합이 0건**이었다(빈 셀).
        #
        # 도달 가능성: create_project 는 owner 를 강제하지만, 무소유 행은 삭제 버그나
        # 미래 migration 으로 남을 수 있다 — 그것이 E1=A 가 존재하는 이유다.
        orphan = self.core_sot.create_project(name="Orphan").id
        self.client.post(
            f"/admin/projects/{orphan}/access-grants", json={"reason": "조사"}
        )
        self.assertEqual(
            self.client.get(f"/projects/{orphan}/drafts").status_code, 403
        )

    def test_reads_under_a_grant_are_recorded_with_the_reason(self) -> None:
        # C-3의 나머지: 발급만으로는 "무엇을 봤는가"가 안 남는다. 승격 아래 요청마다
        # 한 행이 남고, **사유가 그 행에 함께** 있어 join 없이 읽힌다.
        self._issue("지원 요청 #12 확인")
        self.client.get(f"/projects/{self.project}/drafts")
        uses = self.grants.uses_for_project(project_id=self.project)
        self.assertEqual(len(uses), 1)
        self.assertEqual(uses[0].method, "GET")
        self.assertEqual(uses[0].path, f"/projects/{self.project}/drafts")
        self.assertEqual(uses[0].admin_user_id, self.root.id)
        self.assertEqual(uses[0].reason, "지원 요청 #12 확인")

    def test_the_owner_reads_the_access_log(self) -> None:
        # C-4: 통지 채널이 없으므로 "소유자가 알게 된다"의 현실적 형태는 조회다.
        self._issue("지원")
        self.client.get(f"/projects/{self.project}/drafts")
        self.client.post("/auth/logout")
        self.client.post("/auth/login",
                         json={"username": "alice", "password": "pw123"})

        response = self.client.get(f"/projects/{self.project}/access-log")
        self.assertEqual(response.status_code, 200)
        entries = response.json()["entries"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["reason"], "지원")
        self.assertEqual(entries[0]["path"], f"/projects/{self.project}/drafts")

    def test_the_owners_own_reads_are_not_recorded(self) -> None:
        # over-strict: 감사 대상은 **승격 아래 접근**이지 소유자의 정상 사용이 아니다.
        # 여기가 새면 접근 이력이 소유자 자신의 활동 로그로 오염돼 쓸모를 잃는다.
        self.client.post("/auth/logout")
        self.client.post("/auth/login",
                         json={"username": "alice", "password": "pw123"})
        self.client.get(f"/projects/{self.project}/drafts")
        self.assertEqual(
            self.grants.uses_for_project(project_id=self.project), ()
        )

    def test_a_refused_request_is_not_recorded(self) -> None:
        # 승격이 없거나 만료면 접근 자체가 없었으므로 기록도 없다.
        self.client.get(f"/projects/{self.project}/drafts")  # 승격 없음 → 403
        self._issue()
        self.now += timedelta(hours=2)
        self.client.get(f"/projects/{self.project}/drafts")  # 만료 → 403
        self.assertEqual(
            self.grants.uses_for_project(project_id=self.project), ()
        )

    def test_a_read_is_refused_when_it_cannot_be_recorded(self) -> None:
        # ★ fail-closed. 감사 기록이 실패하면 **읽기도 실패한다** — 아무도 설명할 수
        # 없는 접근은 F1=C 가 막으려던 바로 그것이라, 기록 없이 통과시키면 C 를 고른
        # 이유가 사라진다. (LLM 호출 감사가 격리된 것과 반대다: 그쪽은 보안 경계의
        # 하중을 받지 않는다.)
        self._issue()

        def _boom(*_args, **_kwargs):
            raise RuntimeError("audit store down")

        self.grants.record_use = _boom
        with self.assertRaises(RuntimeError):
            self.client.get(f"/projects/{self.project}/drafts")

    def test_a_storage_failure_while_recording_is_the_503_face(self) -> None:
        # 독립 검증 hardening #1: fail-closed 셀은 RuntimeError 로 "통과하지 않는다"만
        # 보였고, **배포에서 실제로 나는 얼굴**(저장소 장애 → 503)은 전역 handler 에만
        # 기대고 있었다. 여기가 그 얼굴을 이 경로에 대해 직접 핀한다 — 500 으로 새거나
        # 200 으로 통과하면 실패한다.
        self._issue()

        def _down(*_args, **_kwargs):
            raise _STORAGE_FAILURE("audit store down")

        self.grants.record_use = _down
        response = self.client.get(f"/projects/{self.project}/drafts")
        self.assertEqual(response.status_code, 503)

    def test_reading_the_access_log_under_a_grant_records_that_read_too(self) -> None:
        # 독립 검증 hardening #2. 승격을 든 관리자는 access-log 도 읽을 수 있고(GET),
        # **그 읽기 자체가 기록된다** — 감사에 사각지대를 두지 않는다는 뜻이다.
        #
        # 기록은 dependency 에서 일어나므로(handler 이전) **응답이 자기 자신의 조회를
        # 포함한다.** 놀랍게 보이지만 옳은 쪽이다: 로그를 연 사실이 로그에 남는다.
        self._issue("이력 확인")
        response = self.client.get(f"/projects/{self.project}/access-log")
        self.assertEqual(response.status_code, 200)

        entries = response.json()["entries"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["path"], f"/projects/{self.project}/access-log")
        self.assertEqual(entries[0]["admin_user_id"], self.root.id)

    def test_purging_a_project_takes_its_access_log_with_it(self) -> None:
        self._issue()
        self.client.get(f"/projects/{self.project}/drafts")
        self.core_sot.archive_project(project_id=self.project)
        self.client.post(
            f"/admin/projects/{self.project}/purge", json={"reason": "정리 요청"}
        )
        self.assertEqual(
            self.grants.uses_for_project(project_id=self.project), ()
        )

    def test_purging_a_project_takes_its_grants_with_it(self) -> None:
        # D5: 새 project-scoped 컬렉션이 파기에 안 물리면 조용한 고아가 된다.
        self._issue()
        self.core_sot.archive_project(project_id=self.project)
        self.client.post(
            f"/admin/projects/{self.project}/purge", json={"reason": "정리 요청"}
        )
        self.assertIsNone(
            self.grants._repo.latest_for(
                admin_user_id=self.root.id, project_id=self.project
            )
        )


if __name__ == "__main__":
    unittest.main()
