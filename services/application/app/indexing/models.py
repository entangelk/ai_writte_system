"""Contracts for Phase 3 derived index records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class IndexRecordKind(StrEnum):
    SOURCE_BLOCK = "source_block"
    # Phase 2B.5: a canonical MemoryEntry projected into the vector index.
    MEMORY = "memory"
    # b-2: a needs_review AnalysisCandidate projected into its own index.
    CANDIDATE = "candidate"


class IndexSyncTarget(StrEnum):
    VECTOR = "vector"


class IndexSyncBackend(StrEnum):
    IN_MEMORY_FAKE = "in_memory_fake"
    CHROMA = "chroma"


class IndexSyncEvent(StrEnum):
    PROJECT_ARCHIVED = "project_archived"
    # D8-6a: project 전체 그래프 파기. drain은 D8-6c에서 연결한다 — a 단계엔 production
    # 호출자가 없어 worker가 이 entry를 만나지 않는다("정의됐으나 drain 대기" 상태).
    PROJECT_PURGED = "project_purged"
    DRAFT_ARCHIVED = "draft_archived"
    # Phase 2B.5: apply minted/versioned a canonical memory; reindex it.
    MEMORY_UPSERTED = "memory_upserted"
    # b-2: extraction recorded a needs_review candidate; index it.
    CANDIDATE_UPSERTED = "candidate_upserted"
    # Phase 6 (v1.6.61): a candidate left needs_review (confirmed/rejected); the
    # worker deletes it from the candidate index (upsert-only stub → real path).
    CANDIDATE_REMOVED = "candidate_removed"


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
class IndexSyncLastError:
    error_type: IndexSyncErrorType
    detail: str


@dataclass(frozen=True, slots=True)
class IndexSyncTargetState:
    # b-6 증분2 (G3=B/G4=B): one sink's state inside a multi-sink drain. ``backend``
    # is a free-form string (not ``IndexSyncBackend``) so a lexical sink can record
    # ``"elasticsearch"`` without a new SoT enum literal (G6=A). ``attempt_count`` /
    # ``last_error`` give each sink its own retry budget, so a persistently-down
    # sink no longer poisons a healthy one.
    status: IndexSyncStatus
    backend: str
    attempt_count: int = 0
    last_error: IndexSyncLastError | None = None


@dataclass(frozen=True, slots=True)
class SinkOutcome:
    """Result of draining one named sink (b-6 증분2). The composite adapters run
    each configured sink under try/except and return one of these per sink so the
    worker can materialize per-sink target state on the outbox entry."""

    target: str
    backend: str
    ok: bool
    error: IndexSyncLastError | None


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
class MemoryIndexRecord:
    """Phase 2B.5: a canonical MemoryEntry projected into the vector index.

    ``id`` is the memory version's own id (``MemoryEntry.id``); each version is a
    distinct entry (2B.4 append-only), so the vector for a superseded version is
    removed when its successor is indexed. See
    docs/plans/02b-5-memory-vector-reindex-decisions.md (D4).
    """

    id: str
    kind: IndexRecordKind
    project_id: str
    memory_id: str
    memory_type: str
    version: int
    status: str
    text: str
    vector: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class CandidateIndexRecord:
    """b-2: a ``needs_review`` AnalysisCandidate projected into the vector index.

    Physically separate from ``MemoryIndexRecord`` (own collection): the
    authority re-derivation source (analysis store) and lifecycle (candidates
    are immutable/no versioning today, unlike append-only memories) differ. See
    docs/plans/04-writing-candidate-retrieval-decisions.md (G1).
    """

    id: str
    kind: IndexRecordKind
    project_id: str
    candidate_id: str
    candidate_type: str
    status: str
    text: str
    vector: tuple[float, ...]


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
