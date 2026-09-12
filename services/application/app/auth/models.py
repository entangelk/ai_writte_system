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
    # C-6 (owner 2026-08-02): True while the account still carries a password
    # somebody *else* chose. Set by the two surfaces where an administrator sets
    # a password for another human (`POST /admin/users`, `scripts/create_user.py`)
    # and cleared the moment that human sets their own. While it is True the
    # account cannot obtain a session at all — see `/auth/login`.
    must_change_password: bool = False
    # Signup approval (owner 2026-08-22): "pending" = requested, waiting for an
    # admin; "active" = can sign in; "rejected" = an admin declined (the username
    # may be re-requested — rejection is not a ban; banning is deactivation).
    # Defaults to "active" so rows written before this field existed keep
    # signing in — same migration posture as ``must_change_password``.
    # A separate axis from ``is_active``: deactivation stays one-way (D6=A) and
    # keeps its unified 401 (enumeration defense); status is what an *approved
    # or not* question answers, only visible after correct credentials.
    status: str = "active"
    # Account withdrawal (owner 2026-09-07 — plans/account-withdrawal-…-phases.md).
    # When the member asked to be deleted; None means they did not. The purge
    # falls due one grace period later — see ``auth/users.py::purge_due_at``,
    # which is the only place that arithmetic is done.
    #
    # A *third* axis, deliberately not folded into ``status`` or ``is_active``:
    # a withdrawing account is neither disabled (it must still sign in to
    # cancel — D1=C) nor a resolved signup request, and folding it in would put
    # a reversible state on ``is_active``, which is one-way by contract (D6=A).
    # Defaults to None so rows written before this field keep reading — same
    # migration posture as ``must_change_password`` and ``status`` above.
    withdrawal_requested_at: datetime | None = None
    # Purge claim **and** partial-purge marker, one field (Slice 3, D3=ⓐ).
    # Set atomically by the withdrawal worker when it begins destroying this
    # account; never cleared, because a successful purge deletes the row itself.
    #
    # So its presence means exactly one thing to the daemon: *someone already
    # started* — in flight, crashed midway, or stopped on a failure. All three
    # must be left alone. Retrying is not merely wasteful, it is wrong:
    # ``execute_project_purge`` empties core_sot first, so a second pass ends in
    # 404 and never reaches the derived collections (see that function's known
    # limit). Cleanup is the reconciler's job, not a retry's.
    #
    # Deliberately not a lease with an expiry: a lease says "take it again
    # later", which is the one thing this axis must not do.
    purge_started_at: datetime | None = None
    # Terms consent at signup (owner 2026-09-07, implemented 2026-09-12 —
    # privacy policy §3). The signup request carries the version string of the
    # documents the requester was shown; the server stamps the time and the
    # *server's* current version (``TERMS_VERSION``), never the client's claim.
    #
    # None on every pre-gate row — administrator-created accounts and everyone
    # who joined before the gate, because retroactive consent is deliberately
    # not collected (policy §3 notice box). Same migration posture as
    # ``must_change_password`` above: defaults keep old rows reading.
    terms_agreed_at: datetime | None = None
    terms_version_agreed: str | None = None



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
