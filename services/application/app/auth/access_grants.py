"""Administrator access grants — the expiring, audited reach of F1=C.

Owner decisions (2026-08-02, brief ``plans/auth-d8-5-admin-decisions.md`` §7):

* **C-1 수명** = fixed TTL, **1 hour**. Not "until released" (a forgotten grant
  becomes a permanent privilege) and not single-use (one support task would mean
  dozens of re-issues).
* **C-2 쓰기** = read-only. The support scenario is "look and confirm"; letting
  an administrator edit someone else's manuscript would collide with the
  canonical-preservation policy. Enforcement lives in ``require_project_owner``
  (HTTP method), not here — this module only answers *is there a live grant*.
* **C-3 감사** = issuance is recorded by the grant row itself, which is why this
  store is **append-only**. Per-operation audit under a live grant is the next
  slice.
* **C-5 사유** = required, and required *here* rather than only in the HTTP
  model, so a script cannot mint a reasonless grant.

The shape deliberately mirrors ``sessions.py``: the service is the authority on
whether a grant is live, and the store is allowed to still hold expired rows.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Callable, Protocol

from services.application.app.auth.models import AccessGrant

# C-1 (owner, 2026-08-02). A contract literal: the SoT and the regression pin it,
# so changing the number is a contract change rather than a tuning knob.
DEFAULT_ACCESS_GRANT_TTL = timedelta(hours=1)


class AccessGrantRepository(Protocol):
    def insert(self, grant: AccessGrant) -> None: ...
    def latest_for(
        self, *, admin_user_id: str, project_id: str
    ) -> AccessGrant | None: ...
    def purge_project(self, *, project_id: str) -> None: ...


class InMemoryAccessGrantRepository:
    def __init__(self) -> None:
        # Append-only, in issue order — the same property the Mongo repository
        # has, so a test that passes here means something for the deployment.
        self._grants: list[AccessGrant] = []

    def insert(self, grant: AccessGrant) -> None:
        self._grants.append(grant)

    def latest_for(
        self, *, admin_user_id: str, project_id: str
    ) -> AccessGrant | None:
        for grant in reversed(self._grants):
            if (
                grant.admin_user_id == admin_user_id
                and grant.project_id == project_id
            ):
                return grant
        return None

    def purge_project(self, *, project_id: str) -> None:
        self._grants = [g for g in self._grants if g.project_id != project_id]


class AccessGrantService:
    def __init__(
        self,
        repository: AccessGrantRepository,
        *,
        ttl: timedelta = DEFAULT_ACCESS_GRANT_TTL,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repo = repository
        self._ttl = ttl
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: secrets.token_hex(12))

    def issue(
        self, *, admin_user_id: str, project_id: str, reason: str
    ) -> AccessGrant:
        # C-5: the value of an audit record is in the "why", and it costs one
        # field. A blank reason is rejected at the domain boundary so the rule
        # holds for callers that never touch the HTTP model.
        if not reason.strip():
            raise ValueError("reason must not be blank")
        now = self._clock()
        grant = AccessGrant(
            id=self._id_factory(),
            admin_user_id=admin_user_id,
            project_id=project_id,
            reason=reason,
            created_at=now,
            expires_at=now + self._ttl,
        )
        self._repo.insert(grant)
        return grant

    def active(self, *, admin_user_id: str, project_id: str) -> AccessGrant | None:
        """The live grant for this (admin, project), or None.

        Expired rows stay in the store on purpose (they are the audit trail), so
        this judgement — not the store's contents — is the gate.
        """
        grant = self._repo.latest_for(
            admin_user_id=admin_user_id, project_id=project_id
        )
        if grant is None or grant.expires_at <= self._clock():
            return None
        return grant

    def purge_project(self, *, project_id: str) -> None:
        """D5/D8-6: a purged project takes its grants with it.

        Append-only is a rule about *expiry*, not about project destruction —
        leaving grant rows behind would be exactly the silent orphan D5 forbids
        (they carry the project's id and the reason someone looked at it).
        """
        self._repo.purge_project(project_id=project_id)
