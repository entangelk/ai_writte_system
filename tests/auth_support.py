"""Test seam: an API client that arrives already authenticated.

D8-3a closed every operation except ``/health`` and ``/auth/*``: a sessionless
request is 401 before the handler runs. The suites that import from here are
about *domain* behaviour, not about the session boundary, so they run as a
logged-in user rather than re-asserting the guard at ~130 call sites.

What this does NOT do, deliberately:

* It does not remove the dependency. ``require_authenticated_user`` is still
  declared on the route; only its *resolution* is overridden, so a route that
  forgot to declare it does not accidentally start working here.
* It does not leave the boundary untested. ``tests/test_auth_api.py`` drives
  every route of a real, non-overridden app and asserts 401 — the exhaustive
  guard D7=A calls for. A test that wants the real boundary imports
  ``fastapi.testclient.TestClient`` directly, as that module does.

Overriding is keyed on the module-level dependency function, which is why it is
module level in ``main`` rather than a ``create_app`` closure.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient as _RealTestClient

from services.application.app.auth.models import User
from services.application.app.main import require_authenticated_user

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


def authenticate(app) -> None:
    """Make every protected operation on ``app`` resolve to ``TEST_USER``."""
    app.dependency_overrides[require_authenticated_user] = lambda: TEST_USER


def authenticated(app):
    """``authenticate`` for call sites that need the app back as an expression."""
    authenticate(app)
    return app


class AuthenticatedTestClient(_RealTestClient):
    """``TestClient`` that authenticates the app it is given."""

    def __init__(self, app, *args, **kwargs):
        authenticate(app)
        super().__init__(app, *args, **kwargs)
