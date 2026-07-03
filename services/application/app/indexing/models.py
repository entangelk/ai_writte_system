"""Contracts for Phase 3 derived index records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class IndexRecordKind(StrEnum):
    SOURCE_BLOCK = "source_block"


class IndexSyncTarget(StrEnum):
    VECTOR = "vector"


class IndexSyncBackend(StrEnum):
    IN_MEMORY_FAKE = "in_memory_fake"


class IndexSyncEvent(StrEnum):
    PROJECT_ARCHIVED = "project_archived"
    DRAFT_ARCHIVED = "draft_archived"


class IndexSyncStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class IndexSyncErrorType(StrEnum):
    BACKEND_ERROR = "backend_error"
    NOT_FOUND = "not_found"


class IndexStaleReason(StrEnum):
    PROJECT_ARCHIVED = "project_archived"
    DRAFT_ARCHIVED = "draft_archived"
    SNAPSHOT_MISSING = "snapshot_missing"
    DRAFT_MISMATCH = "draft_mismatch"
    CONTENT_HASH_MISMATCH = "content_hash_mismatch"
    BLOCK_MISSING = "block_missing"


@dataclass(frozen=True, slots=True)
class IndexSyncRequest:
    project_id: str
    snapshot_id: str
    target: IndexSyncTarget


@dataclass(frozen=True, slots=True)
class IndexSyncSource:
    mongo_collection: str
    mongo_id: str
    mongo_version: int | None = None


@dataclass(frozen=True, slots=True)
class IndexSyncTargetState:
    status: IndexSyncStatus
    backend: IndexSyncBackend


@dataclass(frozen=True, slots=True)
class IndexSyncLastError:
    error_type: IndexSyncErrorType
    detail: str


@dataclass(frozen=True, slots=True)
class IndexSyncOutboxEntry:
    sync_request_id: str
    project_id: str
    user_id: str | None
    event: IndexSyncEvent
    source: IndexSyncSource
    targets: dict[str, IndexSyncTargetState]
    status: IndexSyncStatus
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime | None
    claimed_at: datetime | None
    last_error: IndexSyncLastError | None


@dataclass(frozen=True, slots=True)
class IndexSyncLog:
    sync_log_id: str
    sync_request_id: str
    project_id: str
    user_id: str | None
    event: IndexSyncEvent
    source: IndexSyncSource
    targets: dict[str, IndexSyncTargetState]
    status: IndexSyncStatus
    attempt_count: int
    error: IndexSyncLastError | None
    started_at: datetime
    finished_at: datetime


@dataclass(frozen=True, slots=True)
class IndexPointer:
    project_id: str
    collection: str
    document_id: str
    version_id: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class SourceBlockIndexRecord:
    id: str
    kind: IndexRecordKind
    pointer: IndexPointer
    snapshot_id: str
    draft_id: str
    block_id: str
    block_index: int
    text: str
    vector: tuple[float, ...]
    project_archived: bool
    draft_archived: bool


@dataclass(frozen=True, slots=True)
class IndexSyncResult:
    request: IndexSyncRequest
    records_attempted: int
    records_written: int


@dataclass(frozen=True, slots=True)
class IndexRecordValidation:
    record_id: str
    usable: bool
    stale_reasons: tuple[IndexStaleReason, ...]
