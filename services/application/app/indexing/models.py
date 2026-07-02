"""Contracts for Phase 3 derived index records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class IndexRecordKind(StrEnum):
    SOURCE_BLOCK = "source_block"


class IndexSyncTarget(StrEnum):
    VECTOR = "vector"


@dataclass(frozen=True, slots=True)
class IndexSyncRequest:
    project_id: str
    snapshot_id: str
    target: IndexSyncTarget


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
