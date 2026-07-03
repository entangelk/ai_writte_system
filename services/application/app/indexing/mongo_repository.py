"""MongoDB repository for Phase 3 index sync outbox entries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo import ASCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, OperationFailure

from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
from services.application.app.indexing.models import (
    IndexSyncBackend,
    IndexSyncEvent,
    IndexSyncLastError,
    IndexSyncLog,
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
                    ("claimed_at", ASCENDING),
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

    def next_sync_log_id(self) -> str:
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
                "status": {
                    "$in": [
                        IndexSyncStatus.PENDING.value,
                        IndexSyncStatus.RUNNING.value,
                    ]
                },
            }
        )
        return _to_outbox_entry(doc) if doc else None

    def put_outbox_entry(self, entry: IndexSyncOutboxEntry) -> None:
        try:
            self._outbox.insert_one(_outbox_doc(entry))
        except DuplicateKeyError:
            return

    def claim_next_outbox_entry(
        self,
        *,
        now: datetime,
        claim_timeout_seconds: int,
    ) -> IndexSyncOutboxEntry | None:
        stale_before = now - timedelta(seconds=claim_timeout_seconds)
        doc = self._outbox.find_one_and_update(
            {
                "$or": [
                    {
                        "status": IndexSyncStatus.PENDING.value,
                        "$or": [
                            {"next_attempt_at": None},
                            {"next_attempt_at": {"$lte": now}},
                        ],
                    },
                    {
                        "status": IndexSyncStatus.RUNNING.value,
                        "claimed_at": {"$lte": stale_before},
                    },
                ]
            },
            {
                "$set": {
                    "status": IndexSyncStatus.RUNNING.value,
                    "claimed_at": now,
                }
            },
            sort=[
                ("next_attempt_at", ASCENDING),
                ("sync_request_id", ASCENDING),
            ],
            return_document=ReturnDocument.AFTER,
        )
        return _to_outbox_entry(doc) if doc else None

    def record_outbox_success(
        self,
        entry: IndexSyncOutboxEntry,
        *,
        started_at: datetime,
        finished_at: datetime,
    ) -> IndexSyncLog:
        log = _sync_log(
            repository=self,
            entry=entry,
            status=IndexSyncStatus.SUCCESS,
            attempt_count=entry.attempt_count + 1,
            error=None,
            started_at=started_at,
            finished_at=finished_at,
        )
        self._logs.insert_one(_log_doc(log))
        self._outbox.delete_one({"_id": entry.sync_request_id})
        return log

    def record_outbox_failure(
        self,
        entry: IndexSyncOutboxEntry,
        *,
        error: IndexSyncLastError,
        started_at: datetime,
        finished_at: datetime,
    ) -> IndexSyncLog:
        attempt_count = entry.attempt_count + 1
        log = _sync_log(
            repository=self,
            entry=entry,
            status=IndexSyncStatus.FAILED,
            attempt_count=attempt_count,
            error=error,
            started_at=started_at,
            finished_at=finished_at,
        )
        self._logs.insert_one(_log_doc(log))
        if attempt_count >= entry.max_attempts:
            self._outbox.delete_one({"_id": entry.sync_request_id})
            return log
        self._outbox.update_one(
            {"_id": entry.sync_request_id},
            {
                "$set": {
                    "status": IndexSyncStatus.PENDING.value,
                    "attempt_count": attempt_count,
                    "next_attempt_at": finished_at
                    + timedelta(seconds=_backoff_seconds(attempt_count)),
                    "claimed_at": None,
                    "last_error": _last_error_doc(error),
                }
            },
        )
        return log


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
        "claimed_at": entry.claimed_at,
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
        next_attempt_at=_to_utc_datetime(doc.get("next_attempt_at")),
        claimed_at=_to_utc_datetime(doc.get("claimed_at")),
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


def _to_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _sync_log(
    *,
    repository: MongoIndexSyncRepository,
    entry: IndexSyncOutboxEntry,
    status: IndexSyncStatus,
    attempt_count: int,
    error: IndexSyncLastError | None,
    started_at: datetime,
    finished_at: datetime,
) -> IndexSyncLog:
    return IndexSyncLog(
        sync_log_id=repository.next_sync_log_id(),
        sync_request_id=entry.sync_request_id,
        project_id=entry.project_id,
        user_id=entry.user_id,
        event=entry.event,
        source=entry.source,
        targets=entry.targets,
        status=status,
        attempt_count=attempt_count,
        error=error,
        started_at=started_at,
        finished_at=finished_at,
    )


def _log_doc(log: IndexSyncLog) -> dict:
    return {
        "_id": log.sync_log_id,
        "sync_log_id": log.sync_log_id,
        "sync_request_id": log.sync_request_id,
        "project_id": log.project_id,
        "user_id": log.user_id,
        "event": log.event.value,
        "source": _source_doc(log.source),
        "targets": {
            name: _target_state_doc(target)
            for name, target in log.targets.items()
        },
        "status": log.status.value,
        "attempt_count": log.attempt_count,
        "error": _last_error_doc(log.error) if log.error is not None else None,
        "started_at": log.started_at,
        "finished_at": log.finished_at,
    }


def _backoff_seconds(attempt_count: int) -> int:
    backoff_seconds = (60, 300)
    index = max(0, attempt_count - 1)
    if index >= len(backoff_seconds):
        return backoff_seconds[-1]
    return backoff_seconds[index]
