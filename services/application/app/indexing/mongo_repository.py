"""MongoDB repository for Phase 3 index sync outbox entries."""

from __future__ import annotations

from bson import ObjectId
from pymongo import ASCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, OperationFailure

from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
from services.application.app.indexing.models import (
    IndexSyncBackend,
    IndexSyncEvent,
    IndexSyncLastError,
    IndexSyncOutboxEntry,
    IndexSyncSource,
    IndexSyncStatus,
    IndexSyncTargetState,
)


class MongoIndexSyncRepositorySetupError(RuntimeError):
    """Raised when MongoDB cannot install required index sync indexes."""


class MongoIndexSyncRepository:
    def __init__(
        self,
        client: MongoClient,
        *,
        db_name: str = DEFAULT_DB_NAME,
    ) -> None:
        self._db = client[db_name]
        self._outbox = self._db["index_sync_outbox"]
        self._logs = self._db["index_sync_logs"]
        self.ensure_indexes()

    @classmethod
    def from_uri(
        cls,
        uri: str,
        *,
        db_name: str = DEFAULT_DB_NAME,
    ) -> "MongoIndexSyncRepository":
        return cls(MongoClient(uri), db_name=db_name)

    def ensure_indexes(self) -> None:
        try:
            self._outbox.create_index(
                [
                    ("project_id", ASCENDING),
                    ("event", ASCENDING),
                    ("source.mongo_collection", ASCENDING),
                    ("source.mongo_id", ASCENDING),
                ],
                unique=True,
                name="uniq_index_sync_outbox_event_source",
            )
            self._outbox.create_index(
                [
                    ("status", ASCENDING),
                    ("next_attempt_at", ASCENDING),
                    ("sync_request_id", ASCENDING),
                ],
                name="index_sync_outbox_by_status_next_attempt",
            )
            self._logs.create_index(
                [("sync_request_id", ASCENDING), ("attempt_count", ASCENDING)],
                name="index_sync_logs_by_request_attempt",
            )
            self._logs.create_index(
                [("project_id", ASCENDING), ("sync_request_id", ASCENDING)],
                name="index_sync_logs_by_project_request",
            )
        except OperationFailure as exc:
            raise MongoIndexSyncRepositorySetupError(
                "failed to create required Index Sync MongoDB indexes"
            ) from exc

    def next_sync_request_id(self) -> str:
        return str(ObjectId())

    def get_outbox_entry_by_dedup_key(
        self,
        *,
        project_id: str,
        event: IndexSyncEvent,
        source: IndexSyncSource,
    ) -> IndexSyncOutboxEntry | None:
        doc = self._outbox.find_one(
            {
                "project_id": project_id,
                "event": event.value,
                "source.mongo_collection": source.mongo_collection,
                "source.mongo_id": source.mongo_id,
            }
        )
        return _to_outbox_entry(doc) if doc else None

    def put_outbox_entry(self, entry: IndexSyncOutboxEntry) -> None:
        try:
            self._outbox.insert_one(_outbox_doc(entry))
        except DuplicateKeyError:
            return


def _outbox_doc(entry: IndexSyncOutboxEntry) -> dict:
    return {
        "_id": entry.sync_request_id,
        "sync_request_id": entry.sync_request_id,
        "project_id": entry.project_id,
        "user_id": entry.user_id,
        "event": entry.event.value,
        "source": _source_doc(entry.source),
        "targets": {
            name: _target_state_doc(target)
            for name, target in entry.targets.items()
        },
        "status": entry.status.value,
        "attempt_count": entry.attempt_count,
        "max_attempts": entry.max_attempts,
        "next_attempt_at": entry.next_attempt_at,
        "last_error": (
            _last_error_doc(entry.last_error)
            if entry.last_error is not None
            else None
        ),
    }


def _source_doc(source: IndexSyncSource) -> dict:
    return {
        "mongo_collection": source.mongo_collection,
        "mongo_id": source.mongo_id,
        "mongo_version": source.mongo_version,
    }


def _target_state_doc(target: IndexSyncTargetState) -> dict:
    return {
        "status": target.status.value,
        "backend": target.backend.value,
    }


def _last_error_doc(error: IndexSyncLastError) -> dict:
    return {
        "error_type": error.error_type.value,
        "detail": error.detail,
    }


def _to_outbox_entry(doc: dict) -> IndexSyncOutboxEntry:
    return IndexSyncOutboxEntry(
        sync_request_id=doc["sync_request_id"],
        project_id=doc["project_id"],
        user_id=doc.get("user_id"),
        event=IndexSyncEvent(doc["event"]),
        source=_to_source(doc["source"]),
        targets={
            name: _to_target_state(target)
            for name, target in doc["targets"].items()
        },
        status=IndexSyncStatus(doc["status"]),
        attempt_count=doc["attempt_count"],
        max_attempts=doc["max_attempts"],
        next_attempt_at=doc.get("next_attempt_at"),
        last_error=(
            _to_last_error(doc["last_error"])
            if doc.get("last_error") is not None
            else None
        ),
    )


def _to_source(doc: dict) -> IndexSyncSource:
    return IndexSyncSource(
        mongo_collection=doc["mongo_collection"],
        mongo_id=doc["mongo_id"],
        mongo_version=doc.get("mongo_version"),
    )


def _to_target_state(doc: dict) -> IndexSyncTargetState:
    return IndexSyncTargetState(
        status=IndexSyncStatus(doc["status"]),
        backend=IndexSyncBackend(doc["backend"]),
    )


def _to_last_error(doc: dict) -> IndexSyncLastError:
    from services.application.app.indexing.models import IndexSyncErrorType

    return IndexSyncLastError(
        error_type=IndexSyncErrorType(doc["error_type"]),
        detail=doc["detail"],
    )
