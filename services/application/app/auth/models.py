"""Auth domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class User:
    id: str
    username: str
    password_hash: str
    is_admin: bool
    is_active: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AccessGrant:
    """An administrator's expiring, read-only reach into one project (F1=C).

    Ownership (403) applies to administrators too — this is the *only* way past
    it, and it is deliberately a separate mechanism rather than a wider admin
    tier: the grant names one project, expires on its own, and carries the
    reason it was issued (C-5), so "what did an admin look at, and why" is
    answerable after the fact.

    The row is never deleted, not even after expiry: it **is** the issuance
    audit record (C-3). Expiry is a judgement made against ``expires_at``, never
    a delete — see ``AccessGrantService.active``.
    """

    id: str
    admin_user_id: str
    project_id: str
    reason: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AccessGrantUse:
    """One request an administrator actually made under a live grant (C-3).

    The grant row answers "who was allowed in, and why". This answers "what did
    they then look at" — without it the grant is a permission slip with no
    record of what it was used for, which is the half of C-3 the owner said
    would otherwise make choosing F1=C pointless.

    One row per request, so the granularity is the operation, not the session.
    """

    id: str
    grant_id: str
    admin_user_id: str
    project_id: str
    method: str
    path: str
    at: datetime
    # Denormalized from the grant on purpose: an audit row records what was true
    # at that moment and must be readable without joining to a row that a purge
    # or a later re-issue could change.
    reason: str


@dataclass(frozen=True, slots=True)
class Session:
    # token_hash = sha256 of the raw cookie token. Only the hash is stored, so a
    # database leak does not hand over live session tokens; the raw token exists
    # only in the client cookie.
    token_hash: str
    user_id: str
    created_at: datetime
    expires_at: datetime
