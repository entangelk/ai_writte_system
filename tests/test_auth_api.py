"""Login/logout/me endpoints: cookie policy, 401 branches, and the slice's
explicit non-goal — existing endpoints must stay reachable without a session
until the authorization slice (D7) lands."""

import os
import unittest
from datetime import timedelta
from unittest import mock

from fastapi.testclient import TestClient

from services.application.app.auth.cookies import cookie_secure
from services.application.app.auth.sessions import (
    InMemorySessionRepository, SessionService,
)
from services.application.app.auth.users import InMemoryUserRepository, UserService
from services.application.app.main import create_app


class _FakeHasher:
    def hash(self, password: str) -> str:
        return "H:" + password

    def verify(self, stored_hash: str, password: str) -> bool:
        return stored_hash == "H:" + password


def _client(*, ttl=timedelta(hours=1)):
    users = UserService(InMemoryUserRepository(), hasher=_FakeHasher())
    sessions = SessionService(InMemorySessionRepository(), ttl=ttl)
    users.create_user(username="alice", password="pw123")
    app = create_app(user_service=users, session_service=sessions)
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


class SliceBoundaryTest(unittest.TestCase):
    def test_existing_endpoints_stay_open_without_a_session(self) -> None:
        # This slice adds authentication only. Authorization is D7; until then a
        # sessionless request must still work, or the owner is locked out of
        # data that has no owner_id yet.
        client, _, _ = _client()
        self.assertEqual(client.get("/health").status_code, 200)
        created = client.post("/projects", json={"name": "Novel"})
        self.assertEqual(created.status_code, 200)
        self.assertEqual(client.get("/projects").status_code, 200)

    def test_no_non_auth_operation_is_protected_yet(self) -> None:
        # Exhaustive form of the non-goal: the 3 endpoints sampled above are a
        # spot check, and this slice's claim is about *all* of them. Two contract
        # signals must stay absent outside /auth until D8-3:
        #   - a `security` requirement (declared authentication), and
        #   - a 401 declaration (H3 forces every realistic status to be declared,
        #     so authorization cannot land without 401s appearing here).
        # When D8-3 does land, this test is expected to fail — that failure is
        # the marker that the non-goal has ended, and it should be rewritten
        # into its inverse rather than deleted.
        spec = create_app().openapi()
        offenders = {
            (path, method)
            for path, operations in spec["paths"].items()
            for method, operation in operations.items()
            if not path.startswith("/auth/")
            and ("security" in operation or "401" in operation.get("responses", {}))
        }
        self.assertEqual(offenders, set())

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


if __name__ == "__main__":
    unittest.main()
