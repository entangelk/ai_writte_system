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
        """Declaration guard in both directions: scoped routes only, no drift."""
        spec = self.client.app.openapi()
        for route in self.client.app.routes:
            if not isinstance(route, APIRoute):
                continue
            declared = [d.dependency for d in route.dependencies]
            ownership_guarded = require_project_owner in declared
            expected = "{project_id}" in route.path
            for method in sorted(route.methods):
                method = method.lower()
                with self.subTest(path=route.path, method=method):
                    self.assertEqual(ownership_guarded, expected)
                    responses = spec["paths"][route.path][method]["responses"]
                    self.assertEqual("403" in responses, expected)


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
