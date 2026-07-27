"""Session cookie policy (D2=A security hardening).

Kept in one place so the three flags that make the cookie safe cannot drift
apart across set/clear call sites.
"""

from __future__ import annotations

import os

SESSION_COOKIE_NAME = "session"


def cookie_secure() -> bool:
    """``Secure`` defaults to on (fail closed toward security).

    Modern browsers treat ``http://localhost`` as a trustworthy origin, so a
    Secure cookie still works for local development over plain HTTP; the escape
    hatch exists for non-localhost HTTP deployments, which should be rare and
    deliberate.
    """
    return os.environ.get("AUTH_COOKIE_SECURE", "true").lower() not in {
        "0", "false", "no",
    }


def cookie_kwargs(*, max_age: int | None = None) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "key": SESSION_COOKIE_NAME,
        "httponly": True,       # JS cannot read it, so XSS cannot exfiltrate it
        "secure": cookie_secure(),
        "samesite": "lax",      # cross-site POSTs carry no cookie → CSRF defense
        "path": "/",
    }
    if max_age is not None:
        kwargs["max_age"] = max_age
    return kwargs
