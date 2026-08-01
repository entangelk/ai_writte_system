"""Operator scripts obtain and carry a session (D8-3a made every route 401).

Two directions are locked here:

* under-strict — a script that stops logging in (or stops sending the cookie)
  goes back to 401 against the deployed app, which no test could see before
  because these scripts are only exercised live;
* over-strict — carrying the session through httpx's cookie jar instead of an
  explicit header *looks* right and still 401s, because the session cookie
  ships ``Secure`` and every script talks plain http.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import os
import pathlib
import re
import unittest

import httpx

from scripts.script_auth import (
    PASSWORD_ENV,
    SESSION_COOKIE_NAME,
    ScriptLoginError,
    USERNAME_ENV,
    add_login_arguments,
    authenticate_client,
    login,
    password_from_env,
)

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"

# Every script that calls an Application route, and how it gets its session.
#
#   "operator"    — talks to a deployed app: --username + $APPLICATION_PASSWORD.
#   "self_hosted" — drives the app in-process with its own in-memory stores, so
#                   there is no operator account to borrow; it mints one.
#
# The first sweep for this slice keyed on `application_base_url`/`application:8000`
# and therefore missed phase2a_provider_live_smoke, which reaches the same routes
# over ASGITransport at http://application-smoke. The discovery test below is the
# fix for that class of miss: this table can no longer silently fall behind.
HTTP_SCRIPT_MODULES = {
    "scripts.phase2a_deployed_e2e_smoke": "operator",
    "scripts.phase3a_deployed_rebuild_smoke": "operator",
    "scripts.phase4_context_search_deployed_smoke": "operator",
    "scripts.phase6_gate_finding_live_smoke": "operator",
    "scripts.diagnose_writing_gate": "operator",
    "scripts.diagnose_writing_report": "operator",
    "scripts.measure_writing_stages": "operator",
    "scripts.benchmark_writing_loop": "operator",
    "scripts.phase2a_provider_live_smoke": "self_hosted",
}

# A script needs a session if it addresses an application route itself, or if it
# delegates that to the shared seed helper (diagnose_writing_report and
# measure_writing_stages reach /projects only through `seed_context`).
#
# `seed_context` is matched on word boundaries: without them
# `seed_context_search_plan_template` — a gateway-only script — reads as a false
# positive, and a discovery guard that cries wolf gets deleted.
_APP_ROUTE_MARKERS = (r'"/projects', r"\bseed_context\b")


def _login_transport(calls: list[httpx.Request], *, token: str = "tok-1"):
    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/auth/login":
            return httpx.Response(
                200,
                json={"user": {"id": "u1", "username": "probe", "is_admin": True}},
                headers={
                    "set-cookie": (
                        f"{SESSION_COOKIE_NAME}={token}; HttpOnly; Secure; "
                        "SameSite=lax; Path=/"
                    )
                },
            )
        return httpx.Response(200, json={"id": "project-1"})

    return httpx.MockTransport(handler)


class ScriptLoginTest(unittest.IsolatedAsyncioTestCase):
    # The password is environment-only (create_user.py precedent: argv would put
    # it in shell history and `ps`), so the env is part of the fixture.
    _NO_PASSWORD_TEST = "test_username_without_password_env_does_not_log_in"

    def setUp(self):
        self._saved = {
            name: os.environ.pop(name, None)
            for name in (USERNAME_ENV, PASSWORD_ENV)
        }
        if self._testMethodName != self._NO_PASSWORD_TEST:
            os.environ[PASSWORD_ENV] = "pw"

    def tearDown(self):
        os.environ.pop(PASSWORD_ENV, None)
        for name, value in self._saved.items():
            if value is not None:
                os.environ[name] = value

    async def test_login_attaches_the_session_to_later_requests_over_http(self):
        """Under-strict: no login (or no cookie) and the deployed app answers 401.

        The base_url is plain http on purpose: that is where the trap lives. The
        login response's ``Secure`` cookie lands in httpx's jar and is never
        replayed there, so leaving the session to the jar fails here (measured).

        This asserts the *behaviour* — a session reaches the next request — not
        the mechanism. ``client.cookies.set(...)`` passes too, and correctly so:
        a cookie put in the jar by hand carries no Secure flag and does travel.
        Do not tighten this into a header-only assertion; that would fail a
        working implementation.
        """
        calls: list[httpx.Request] = []
        async with httpx.AsyncClient(
            base_url="http://application:8000", transport=_login_transport(calls)
        ) as client:
            logged_in = await authenticate_client(client, username="probe")
            await client.post("/projects", json={"name": "after login"})

        self.assertTrue(logged_in)
        self.assertEqual(
            [request.url.path for request in calls], ["/auth/login", "/projects"]
        )
        self.assertEqual(
            calls[1].headers.get("cookie"), f"{SESSION_COOKIE_NAME}=tok-1"
        )

    async def test_login_sends_the_credentials_as_the_login_body(self):
        calls: list[httpx.Request] = []
        async with httpx.AsyncClient(
            base_url="http://application:8000", transport=_login_transport(calls)
        ) as client:
            token = await login(client, username="probe", password="pw")

        self.assertEqual(token, "tok-1")
        self.assertEqual(
            json.loads(calls[0].read()),
            {"username": "probe", "password": "pw"},
        )

    async def test_without_credentials_the_client_stays_anonymous(self):
        calls: list[httpx.Request] = []
        async with httpx.AsyncClient(
            base_url="http://application:8000", transport=_login_transport(calls)
        ) as client:
            logged_in = await authenticate_client(client, username=None)
            await client.post("/projects", json={"name": "anonymous"})

        self.assertFalse(logged_in)
        self.assertEqual([request.url.path for request in calls], ["/projects"])
        self.assertIsNone(calls[0].headers.get("cookie"))

    async def test_username_without_password_env_does_not_log_in(self):
        calls: list[httpx.Request] = []
        async with httpx.AsyncClient(
            base_url="http://application:8000", transport=_login_transport(calls)
        ) as client:
            logged_in = await authenticate_client(client, username="probe")

        self.assertFalse(logged_in)
        self.assertEqual(calls, [])

    async def test_rejected_credentials_raise_a_readable_error(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": "invalid credentials"})

        async with httpx.AsyncClient(
            base_url="http://application:8000",
            transport=httpx.MockTransport(handler),
        ) as client:
            with self.assertRaises(ScriptLoginError) as caught:
                await login(client, username="probe", password="wrong")

        self.assertIn("probe", str(caught.exception))

    async def test_login_without_a_session_cookie_is_an_error_not_a_silent_pass(self):
        """A 200 with no Set-Cookie would otherwise leave the client anonymous."""

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"user": {"id": "u1"}})

        async with httpx.AsyncClient(
            base_url="http://application:8000",
            transport=httpx.MockTransport(handler),
        ) as client:
            with self.assertRaises(ScriptLoginError):
                await login(client, username="probe", password="pw")


class ScriptLoginArgumentsTest(unittest.TestCase):
    def test_password_is_not_an_argv_option(self):
        """create_user.py precedent: argv leaks into shell history and `ps`."""
        parser = argparse.ArgumentParser()
        add_login_arguments(parser)

        options = {action.dest for action in parser._actions}
        self.assertIn("username", options)
        self.assertNotIn("password", options)

    def test_password_comes_from_the_environment(self):
        saved = os.environ.pop(PASSWORD_ENV, None)
        try:
            self.assertIsNone(password_from_env())
            os.environ[PASSWORD_ENV] = "pw"
            self.assertEqual(password_from_env(), "pw")
        finally:
            os.environ.pop(PASSWORD_ENV, None)
            if saved is not None:
                os.environ[PASSWORD_ENV] = saved


class ScriptLoginWiringCoverageTest(unittest.TestCase):
    """Every app-HTTP script must offer --username *and* actually log in.

    The behaviour above is the helper's; this is the assembly guard. Without it
    a script can keep the flag, drop the ``authenticate_client`` call, and fail
    only in the operator's terminal (the observability slice learned the same
    lesson: wrapping and opening the scope always travel together).
    """

    def test_each_http_script_exposes_the_login_flag_and_calls_the_helper(self):
        for module_name, mode in HTTP_SCRIPT_MODULES.items():
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                source = inspect.getsource(module)
                # assertTrue, not assertIn: a failing assertIn would dump the
                # whole script source into the report.
                self.assertTrue(
                    "await authenticate_client(" in source,
                    f"{module_name} never logs in",
                )
                if mode == "operator":
                    self.assertTrue(
                        "add_login_arguments(parser)" in source,
                        f"{module_name} logs in but offers no --username",
                    )
                else:
                    self.assertTrue(
                        "password=" in source,
                        f"{module_name} is self-hosted but passes no credential",
                    )

    def test_no_script_reaches_an_application_route_off_the_register(self):
        """The register cannot silently fall behind the scripts/ directory.

        This is the test the first pass of this slice did not have: it swept for
        one base-url spelling, missed phase2a_provider_live_smoke (same routes,
        ASGITransport, http://application-smoke), and still reported "all of
        them wired". Discovery reads the directory instead of a memory of it.
        """
        for path in sorted(SCRIPTS_DIR.glob("*.py")):
            module_name = f"scripts.{path.stem}"
            source = path.read_text(encoding="utf-8")
            touches_app = any(
                re.search(marker, source) for marker in _APP_ROUTE_MARKERS
            )
            if not touches_app or module_name == "scripts.script_auth":
                continue
            with self.subTest(script=path.name):
                self.assertIn(
                    module_name,
                    HTTP_SCRIPT_MODULES,
                    f"{path.name} calls application routes but is not registered "
                    "in HTTP_SCRIPT_MODULES, so nothing checks that it logs in",
                )
