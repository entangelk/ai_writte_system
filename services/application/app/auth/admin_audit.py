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
    # 8.5-b(D3=ⓑ, 오너 2026-08-23): 회원 정책 조작이 감사의 네 번째 대상이 된다.
    # purge 는 여전히 target_project_id 를 쓰고, 회원 정책은 target_user_id 를
    # 쓴다 — 한 필드를 겹쳐 쓰면 필드명이 거짓말을 한다.
    action: Literal["project_purge", "member_quota_policy"]
    target_type: Literal["project", "user"]
    target_project_id: str | None
    reason: str
    outcome: AdminAuditOutcome
    at: datetime
    target_user_id: str | None = None
    # 변경 요약(예: "suspend" · "daily 20→50, weekly 100→None"). 원장·사용량
    # 스냅샷은 남기지 않는다 — 이력 오남용 방지(8.5 브리프 D3 note).
    detail: str | None = None
    error_kind: str | None = None


class AdminAuditRepository(Protocol):
    def insert(self, event: AdminAuditEvent) -> None: ...

    def list_project_purge_events(self, *, limit: int) -> tuple[AdminAuditEvent, ...]: ...

    def list_member_quota_events(self, *, limit: int) -> tuple[AdminAuditEvent, ...]: ...


class InMemoryAdminAuditRepository:
    def __init__(self) -> None:
        self.events: list[AdminAuditEvent] = []

    def insert(self, event: AdminAuditEvent) -> None:
        self.events.append(event)

    def list_project_purge_events(self, *, limit: int) -> tuple[AdminAuditEvent, ...]:
        return tuple(sorted(self.events, key=lambda event: event.at, reverse=True)[:limit])

    def list_member_quota_events(self, *, limit: int) -> tuple[AdminAuditEvent, ...]:
        return tuple(
            event for event in sorted(
                self.events, key=lambda event: event.at, reverse=True)
            if event.action == "member_quota_policy"
        )[:limit]


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
    def record_member_quota_change(
        self,
        *,
        admin_user_id: str,
        target_user_id: str,
        change: str,
        reason: str,
    ) -> AdminAuditEvent:
        """8.5-b — 한도 변경·정지·해제 감사(단일 즉시 이벤트, outcome=succeeded).

        purge 와 달리 2단계(요청→결과)가 없다: 변경은 동기적으로 완결되고 이
        이벤트는 그 뒤에 남는다. **호출부가 예외를 삼키지 않는다**(D3=ⓑ
        fail-closed) — 감사 쓰기 실패가 요청을 죽게 둔다.
        """
        cleaned = reason.strip()
        if not cleaned:
            raise ValueError("reason must not be blank")
        event = AdminAuditEvent(
            id=f"audit:{self._id_factory()}",
            operation_id=f"member-quota:{self._id_factory()}",
            admin_user_id=admin_user_id,
            action="member_quota_policy",
            target_type="user",
            target_project_id=None,
            reason=cleaned,
            outcome="succeeded",
            at=self._clock(),
            target_user_id=target_user_id,
            detail=change,
        )
        self._repo.insert(event)
        return event

