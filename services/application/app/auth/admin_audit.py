"""Administrator audit events that intentionally survive project purge.

D8-6 owner decisions (2026-08-02): a purge keeps only a minimal tombstone of
the administrator action.  These records use ``target_project_id`` rather than
``project_id`` because they are not children of the deleted project graph; the
purge reconciler deliberately discovers and removes orphan ``project_id`` rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Literal, Protocol
from uuid import uuid4

AdminAuditOutcome = Literal["requested", "succeeded", "failed"]


@dataclass(frozen=True, slots=True)
class AdminAuditEvent:
    id: str
    operation_id: str
    admin_user_id: str
    action: Literal["project_purge"]
    target_type: Literal["project"]
    target_project_id: str
    reason: str
    outcome: AdminAuditOutcome
    at: datetime
    error_kind: str | None = None


class AdminAuditRepository(Protocol):
    def insert(self, event: AdminAuditEvent) -> None: ...

    def list_project_purge_events(self, *, limit: int) -> tuple[AdminAuditEvent, ...]: ...


class InMemoryAdminAuditRepository:
    def __init__(self) -> None:
        self.events: list[AdminAuditEvent] = []

    def insert(self, event: AdminAuditEvent) -> None:
        self.events.append(event)

    def list_project_purge_events(self, *, limit: int) -> tuple[AdminAuditEvent, ...]:
        return tuple(sorted(self.events, key=lambda event: event.at, reverse=True)[:limit])


class AdminAuditService:
    def __init__(
        self,
        repository: AdminAuditRepository,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repo = repository
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    def record_purge_requested(
        self, *, admin_user_id: str, target_project_id: str, reason: str
    ) -> AdminAuditEvent:
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ValueError("purge reason must not be blank")
        event = AdminAuditEvent(
            id=self._id_factory(),
            operation_id=self._id_factory(),
            admin_user_id=admin_user_id,
            action="project_purge",
            target_type="project",
            target_project_id=target_project_id,
            reason=normalized_reason,
            outcome="requested",
            at=self._clock(),
        )
        self._repo.insert(event)
        return event

    def record_purge_outcome(
        self,
        requested: AdminAuditEvent,
        *,
        outcome: Literal["succeeded", "failed"],
        error_kind: str | None = None,
    ) -> AdminAuditEvent:
        event = AdminAuditEvent(
            id=self._id_factory(),
            operation_id=requested.operation_id,
            admin_user_id=requested.admin_user_id,
            action=requested.action,
            target_type=requested.target_type,
            target_project_id=requested.target_project_id,
            reason=requested.reason,
            outcome=outcome,
            at=self._clock(),
            error_kind=error_kind,
        )
        self._repo.insert(event)
        return event

    def list_project_purge_events(self, *, limit: int = 50) -> tuple[AdminAuditEvent, ...]:
        return self._repo.list_project_purge_events(limit=limit)
