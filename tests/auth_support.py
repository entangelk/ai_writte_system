"""Test seam: an API client that arrives already authenticated.

D8-3a closed every operation except ``/health`` and ``/auth/*``: a sessionless
request is 401 before the handler runs. The suites that import from here are
about *domain* behaviour, not about the session boundary, so they run as a
logged-in user rather than re-asserting the guard at ~130 call sites.

What this does NOT do, deliberately:

* It does not remove either dependency. Authentication and project ownership
  stay declared on their routes; only their *resolution* is overridden, so a
  route that forgot a declaration does not accidentally start working here.
* It does not leave either boundary untested. ``tests/test_auth_api.py`` drives
  every route of a real, non-overridden app and asserts both sessionless 401
  and foreign-project 403 — the exhaustive guard D7=A calls for. A test that
  wants the real boundary imports ``fastapi.testclient.TestClient`` directly,
  as that module does.

Overriding is keyed on the module-level dependency function, which is why it is
module level in ``main`` rather than a ``create_app`` closure.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Header, Request
from fastapi.testclient import TestClient as _RealTestClient

from services.application.app.auth.models import User
from services.application.app.main import (
    CONFIRM_DUPLICATE_HEADER,
    enforce_quota,
    require_authenticated_user,
    require_project_owner,
)
from services.application.app.quota.enforcement import QuotaCharge

# A fixed identity, so a test that reads back what was recorded (owner_id) has a
# stable value to assert against.
TEST_USER = User(
    id="test-user-id",
    username="tester",
    password_hash="unused: the override skips authentication entirely",
    is_admin=False,
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=UTC),
)


def admit_without_quota(
    request: Request,
    x_confirm_duplicate: Annotated[
        str | None, Header(alias=CONFIRM_DUPLICATE_HEADER)
    ] = None,
) -> QuotaCharge:
    """Resolve ``enforce_quota`` without consulting the quota stores (8.3).

    Same reasoning — and the same limits — as the two overrides above. Slice 8.3
    turned on a **duplicate-request lock** whose minimum window is 5 seconds, so
    a suite that POSTs the same billable action to the same project twice (a
    replay assertion, a table of invalid bodies) would get 429 on the second call
    for reasons that have nothing to do with what it is testing. Overriding the
    resolution keeps those suites about their own subject.

    What this deliberately does **not** do:

    * It does not remove the dependency — ``tests/test_quota_enforcement_api.py``
      asserts every billable route declares it, on a real app.
    * It does not skip settlement: a receipt is still left on ``request.state``,
      so the post-response settle path runs in every suite that touches a
      billable endpoint. Only *admission* (limits, mutex, lock claim) is skipped.
    * It does not swallow the confirm header — ``X-Confirm-Duplicate`` still
      reaches the endpoint, because the in-flight generation guard (Q8=C) is
      endpoint logic rather than part of this dependency.
    """
    charge = QuotaCharge(
        user_id=TEST_USER.id,
        member_created_at=TEST_USER.created_at,
        action="test_override",
        target_project_id=request.path_params.get("project_id", ""),
        dedupe_key="test-override",
        holder="test-override",
    )
    request.state.quota_charge = charge
    request.state.quota_confirmed = x_confirm_duplicate is not None
    return charge


def authenticate(app) -> None:
    """Make every protected operation on ``app`` resolve to ``TEST_USER``."""
    app.dependency_overrides[require_authenticated_user] = lambda: TEST_USER
    app.dependency_overrides[require_project_owner] = lambda: None
    app.dependency_overrides[enforce_quota] = admit_without_quota


def authenticated(app):
    """``authenticate`` for call sites that need the app back as an expression."""
    authenticate(app)
    return app


class AuthenticatedTestClient(_RealTestClient):
    """``TestClient`` that authenticates the app it is given."""

    def __init__(self, app, *args, **kwargs):
        authenticate(app)
        super().__init__(app, *args, **kwargs)
