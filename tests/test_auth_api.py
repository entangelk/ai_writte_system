"""Login/logout/me endpoints, and the authentication boundary they guard.

D8-3a turned the slice-1 non-goal ("existing endpoints stay open") into its
inverse: every operation except ``/health`` and the public ``/auth`` pair now
requires a live session. This module is the one place that drives real,
non-overridden apps, so it is where the exhaustive guard D7=A calls for lives —
every other suite runs authenticated through ``tests/auth_support.py``.
"""

import os
import re
import unittest
from datetime import timedelta
from unittest import mock

from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

try:
    from pymongo.errors import AutoReconnect as _STORAGE_FAILURE
except ModuleNotFoundError:  # pragma: no cover - the driver is present in CI
    _STORAGE_FAILURE = None

from services.application.app.auth.cookies import cookie_secure
from services.application.app.auth.sessions import (
    InMemorySessionRepository, SessionService,
)
from services.application.app.auth.users import InMemoryUserRepository, UserService
from services.application.app.core_sot.service import (
    CoreSotService, InMemoryCoreSotRepository,
)
from services.application.app.main import (
    create_app,
    require_admin_user,
    require_authenticated_user,
    require_project_owner,
)
from tests.auth_support import authenticate


class _FakeHasher:
    def hash(self, password: str) -> str:
        return "H:" + password

    def verify(self, stored_hash: str, password: str) -> bool:
        return stored_hash == "H:" + password


def _client(*, ttl=timedelta(hours=1), core_sot=None):
    users = UserService(InMemoryUserRepository(), hasher=_FakeHasher())
    sessions = SessionService(InMemorySessionRepository(), ttl=ttl)
    users.create_user(username="alice", password="pw123")
    app = create_app(
        service=core_sot, user_service=users, session_service=sessions
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

        D8-5 widened the *declaration* half: 403 now has two producers, the
        ownership boundary and the admin boundary, so "declares 403" no longer
        means "is project-scoped". The dependency half stayed exact — the
        ownership dependency belongs on `{project_id}` routes and nowhere else,
        which is the property this class exists to protect.
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
                    self.assertEqual(ownership_guarded, expected)
                    # An admin route must never be project-scoped: the admin
                    # surface deliberately does not reach project content.
                    self.assertFalse(admin_guarded and expected)
                    responses = spec["paths"][route.path][method]["responses"]
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
        # The account is real, not just a row: it can actually log in.
        login = self.client.post(
            "/auth/login", json={"username": "carol", "password": "pw000"}
        )
        self.assertEqual(login.status_code, 200)

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


class AdminProjectPurgeTest(unittest.TestCase):
    """D8-6d: POST /admin/projects/{id}/purge — 204 + core_sot 파기(정본).

    비관리자 403·미인증 401 은 CombinedBoundaryMatrixTest 가 ADMIN tier 전수로 잠근다
    (purge 포함). 여기는 성공 동작(204 + project 소멸)과 NotFound 404.
    """

    def setUp(self) -> None:
        self.core_sot = CoreSotService(InMemoryCoreSotRepository())
        self.client, self.users, _ = _client(core_sot=self.core_sot)
        self.users.create_user(username="root", password="pw789", is_admin=True)
        self.client.post(
            "/auth/login", json={"username": "root", "password": "pw789"}
        )

    def test_admin_purge_returns_204_and_removes_project(self) -> None:
        project = self.core_sot.create_project(name="Novel")
        response = self.client.post(f"/admin/projects/{project.id}/purge")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")  # 204 carries no body
        # 정본(core_sot)에서 project 소멸 — purge_project 가 실제로 돌았다.
        self.assertEqual([p.id for p in self.core_sot.list_projects()], [])

    def test_admin_purge_missing_project_is_404(self) -> None:
        response = self.client.post("/admin/projects/does-not-exist/purge")
        self.assertEqual(response.status_code, 404)
        self.assertIn("detail", response.json())


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
    }

    # D8-5's tier. Admin operations name no project on purpose: the admin
    # surface manages accounts, and reaching another user's project content is
    # the audited, expiring grant of F1=C — a different mechanism, not this one.
    ADMIN = {
        ("/admin/users", "get"),
        ("/admin/users", "post"),
        ("/admin/users/{user_id}/deactivate", "post"),
        # D8-5c. Aggregate counts over every project's LLM-call audit — which is
        # why it sits in this tier rather than the project one: it names no
        # project and reads no project's content.
        ("/admin/observability/kpi", "get"),
        # D8-6d: admin project 영구 파기(204, ADMIN tier). project_id 경로지만 소유권이
        # 아니라 관리자 검사를 쓰므로 project tier 가 아닌 admin tier.
        ("/admin/projects/{project_id}/purge", "post"),
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
        self.assertEqual(len(by_tier["project"]), 60)
        self.assertEqual(len(tiers), 71)
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
        #   * 403 has two producers since D8-5 (ownership, admin) and exactly
        #     those two: a 403 on any other operation is a false declaration.
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
                self.assertEqual(tier in ("project", "admin"), "403" in responses)
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
        self.assertEqual(
            list(app.dependency_overrides),
            [require_authenticated_user, require_project_owner],
        )

    def test_this_module_drives_apps_that_are_not_overridden(self) -> None:
        # The guard's whole value is that it runs against the deployed
        # resolution path. A future global/autouse override would neuter it and
        # nothing else would notice — this is what notices.
        client, _, _ = _client()
        self.assertEqual(client.app.dependency_overrides, {})


if __name__ == "__main__":
    unittest.main()
