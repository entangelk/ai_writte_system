"""Core SOT immutable data contracts.

These models intentionally avoid database-specific fields. MongoDB adapters can
persist them later, while unit tests can exercise the source-of-truth contract
without infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BlockKind(StrEnum):
    HEADING = "heading"
    SCENE_MARKER = "scene_marker"
    PARAGRAPH = "paragraph"


@dataclass(frozen=True, slots=True)
class Project:
    id: str
    name: str
    archived: bool = False


@dataclass(frozen=True, slots=True)
class Draft:
    id: str
    project_id: str
    title: str
    archived: bool = False


@dataclass(frozen=True, slots=True)
class DraftVersion:
    id: str
    project_id: str
    draft_id: str
    version_number: int
    snapshot_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    id: str
    project_id: str
    draft_id: str
    version_id: str
    raw_text: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class SourceBlock:
    id: str
    project_id: str
    snapshot_id: str
    block_index: int
    kind: BlockKind
    start_offset: int
    end_offset: int
    text: str


@dataclass(frozen=True, slots=True)
class SourceRef:
    id: str
    project_id: str
    snapshot_id: str
    block_id: str
    start_offset: int
    end_offset: int
    quote: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class SaveDraftResult:
    draft_version: DraftVersion
    snapshot: SourceSnapshot
    blocks: tuple[SourceBlock, ...]
    idempotent_replay: bool

