"""Session login for the operator scripts that call the Application HTTP API.

D8-3a put every application route behind a session except ``/health`` and the
public ``/auth`` routes, so the smoke and diagnostic scripts get 401 without
one. This is the single place that knows how to obtain and carry a session, so
the eight callers cannot drift apart.

Credentials follow ``scripts/create_user.py``: the **username** may be argv,
the **password is environment only** so it does not land in shell history or
``ps`` output::

    APPLICATION_PASSWORD='...' \\
    python3 scripts/phase2a_deployed_e2e_smoke.py --username probe

Credentials are optional. Without them the script runs anonymously and the
application answers 401 — that is the pre-D8-3a behaviour, kept so a caller
pointed at a route that needs no session is not forced to invent an account.
"""

from __future__ import annotations

import argparse
import os

import httpx

SESSION_COOKIE_NAME = "session"

USERNAME_ENV = "APPLICATION_USERNAME"
PASSWORD_ENV = "APPLICATION_PASSWORD"


class ScriptLoginError(RuntimeError):
    """Login could not produce a usable session."""


def add_login_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--username",
        default=os.environ.get(USERNAME_ENV),
        help=(
            "Application account to log in as (D8-3a: every route needs a "
            f"session). The password comes from ${PASSWORD_ENV}, never argv."
        ),
    )


def password_from_env() -> str | None:
    return os.environ.get(PASSWORD_ENV) or None


async def login(
    client: httpx.AsyncClient, *, username: str, password: str
) -> str:
    """POST /auth/login and return the raw session token."""
    response = await client.post(
        "/auth/login", json={"username": username, "password": password}
    )
    if response.status_code == 401:
        raise ScriptLoginError(
            f"login rejected for username={username!r} "
            "(unknown user, wrong password, or disabled account)"
        )
    response.raise_for_status()
    token = response.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise ScriptLoginError(
            "login succeeded but the response carried no "
            f"{SESSION_COOKIE_NAME} cookie"
        )
    return token


async def authenticate_client(
    client: httpx.AsyncClient, *, username: str | None
) -> bool:
    """Log in and pin the session on ``client`` as an explicit Cookie header.

    Returns False when no credentials were supplied, so the caller stays
    anonymous exactly as before.

    The header is deliberate: the session cookie ships ``Secure``, so httpx's
    cookie jar silently refuses to send it back over plain http — which is what
    every one of these scripts uses (``http://application:8000``). Relying on
    the jar would look like it worked and still 401.
    """
    password = password_from_env()
    if not username or not password:
        return False
    token = await login(client, username=username, password=password)
    client.headers["Cookie"] = f"{SESSION_COOKIE_NAME}={token}"
    return True
