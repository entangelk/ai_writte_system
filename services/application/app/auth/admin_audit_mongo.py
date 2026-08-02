"""Mongo repository for administrator audit tombstones."""

from datetime import UTC, datetime

from pymongo import ASCENDING, DESCENDING, MongoClient

from services.application.app.auth.admin_audit import AdminAuditEvent
from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class MongoAdminAuditRepository:
    def __init__(self, client: MongoClient, *, db_name: str = DEFAULT_DB_NAME) -> None:
        self._events = client[db_name]["admin_audit_events"]
        self._events.create_index(
            [("action", ASCENDING), ("at", DESCENDING)],
            name="admin_audit_events_by_action_at",
        )
        self._events.create_index(
            [("operation_id", ASCENDING), ("at", ASCENDING)],
            name="admin_audit_events_by_operation_at",
        )
        # No TTL: this minimal tombstone is the explicit D5 exception that
        # survives destruction of the project graph it describes.

    @classmethod
    def from_uri(cls, uri: str, *, db_name: str = DEFAULT_DB_NAME):
        return cls(MongoClient(uri), db_name=db_name)

    def insert(self, event: AdminAuditEvent) -> None:
        self._events.insert_one(_doc(event))

    def list_project_purge_events(self, *, limit: int) -> tuple[AdminAuditEvent, ...]:
        return tuple(
            _entry(doc)
            for doc in self._events.find({"action": "project_purge"})
            .sort("at", DESCENDING)
            .limit(limit)
        )


def _doc(event: AdminAuditEvent) -> dict:
    return {
        "_id": event.id,
        "operation_id": event.operation_id,
        "admin_user_id": event.admin_user_id,
        "action": event.action,
        "target_type": event.target_type,
        "target_project_id": event.target_project_id,
        "reason": event.reason,
        "outcome": event.outcome,
        "at": event.at,
        "error_kind": event.error_kind,
    }


def _entry(doc: dict) -> AdminAuditEvent:
    return AdminAuditEvent(
        id=doc["_id"],
        operation_id=doc["operation_id"],
        admin_user_id=doc["admin_user_id"],
        action=doc["action"],
        target_type=doc["target_type"],
        target_project_id=doc["target_project_id"],
        reason=doc["reason"],
        outcome=doc["outcome"],
        at=_aware(doc["at"]),
        error_kind=doc.get("error_kind"),
    )
