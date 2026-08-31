"""Core SOT immutable data contracts.

These models intentionally avoid database-specific fields. MongoDB adapters can
persist them later, while unit tests can exercise the source-of-truth contract
without infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class BlockKind(StrEnum):
    HEADING = "heading"
    SCENE_MARKER = "scene_marker"
    PARAGRAPH = "paragraph"


class UnitKind(StrEnum):
    CHAPTER = "chapter"
    SCENE = "scene"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Project:
    id: str
    name: str
    archived: bool = False
    # Multi-user ownership (D3=A). **Enforced since D8-3b (v1.7.53)** — every
    # project-scoped operation checks it, and an administrator gets past it only
    # through an expiring, audited grant (D8-5e). The earlier note here said
    # ownership was "only recorded"; that stopped being true and is corrected.
    #
    # Still nullable: projects created before authentication existed have no
    # owner, and such rows can also arrive from a deletion bug or a migration.
    # `owner_id=None` is therefore **always denied** (E1=A), never adopted.
    owner_id: str | None = None


@dataclass(frozen=True, slots=True)
class Chapter:
    """Metadata-only parent for ordered Scene drafts (SoT v1.8.9)."""

    id: str
    project_id: str
    title: str
    archived: bool = False
    position: int = 1


@dataclass(frozen=True, slots=True)
class ProjectBriefVersion:
    id: str
    project_id: str
    version_number: int
    premise: str | None
    genre: str | None
    tone: str | None
    pov: str | None
    constraints: tuple[str, ...]
    idempotency_key: str
    style_rules: tuple[str, ...] = ()
    preferred_patterns: tuple[str, ...] = ()
    forbidden_patterns: tuple[str, ...] = ()
    style_examples: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PutProjectBriefResult:
    brief: ProjectBriefVersion
    idempotent_replay: bool


@dataclass(frozen=True, slots=True)
class Draft:
    id: str
    project_id: str
    title: str
    archived: bool = False
    # v1.8.9: every runtime Scene belongs to one Chapter. ``None`` remains only
    # while the explicit flat-unit migration is inspecting legacy rows.
    chapter_id: str | None = None
    # ``None`` exists only while the explicit W3 legacy migration is inspecting
    # pre-v1.8.9 documents. ``unit_kind`` is legacy migration input only after
    # Chapter→Scene hierarchy; new runtime Scenes leave it unset.
    unit_kind: UnitKind | None = None
    position: int | None = None


@dataclass(frozen=True, slots=True)
class SceneNote:
    """One Scene's current working note (장면 메모 D2=A, 2026-08-29).

    Deliberately **not** part of the manuscript: notes never enter
    ``draft_versions``, exports, or LLM prompts, so the append-only version
    contract and the export body stay untouched. Identity is
    ``(project_id, draft_id)`` — one current value per Scene, replaced by an
    explicit save (D4=A), never versioned. An empty ``body`` is a stored empty
    note, not a deletion, so "빈 메모" stays distinguishable from "메모 없음".
    """

    project_id: str
    draft_id: str
    body: str
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SceneNoteListItem:
    """One row of the project-wide note list (장면 메모 Slice 1).

    Carries the existing models rather than a flattened copy of their fields:
    a second field list would drift from ``Draft``/``Chapter`` the moment either
    grows one. The list order is the caller's (Chapter position → Scene
    position), so no position field is repeated here either.
    """

    note: SceneNote
    scene: Draft
    chapter: Chapter


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
class WritingAcceptReceipt:
    """Durable record of a completed ``start_next_unit`` accept (W0 §3.3).

    Identity is ``(project_id, idempotency_key)`` where the key is the accept
    save key ``writing-accept:{key}``. It records which unit the accept created
    so a same-key replay reconstructs the exact original target without a second
    Gate/write. ``intent`` is stored as a plain string to keep Core SOT free of
    the Writing intent enum. Legacy append accepts intentionally have NO receipt
    (they replay via the version idempotency key — WI-17).
    """

    project_id: str
    idempotency_key: str
    intent: str
    draft_id: str
    draft_version_id: str


@dataclass(frozen=True, slots=True)
class StartNextUnitResult:
    """Six-surface atomic result of ``start_next_unit`` (W0 §3.2)."""

    draft: Draft
    draft_version: DraftVersion
    snapshot: SourceSnapshot
    blocks: tuple[SourceBlock, ...]


@dataclass(frozen=True, slots=True)
class SaveDraftResult:
    draft_version: DraftVersion
    snapshot: SourceSnapshot
    blocks: tuple[SourceBlock, ...]
    idempotent_replay: bool


@dataclass(frozen=True, slots=True)
class DraftVersionDetail:
    draft_version: DraftVersion
    snapshot: SourceSnapshot
    blocks: tuple[SourceBlock, ...]


@dataclass(frozen=True, slots=True)
class SourceSnapshotDetail:
    snapshot: SourceSnapshot
    blocks: tuple[SourceBlock, ...]


@dataclass(frozen=True, slots=True)
class DraftVersionExport:
    """A readable export of one immutable draft version.

    ``body`` is the snapshot's raw text verbatim: no AI analysis metadata is
    injected and no Markdown is synthesized or stripped, so the exported body
    always matches the selected version. ``format`` only governs the
    ``content_type`` and ``filename`` extension. The version pointers make the
    export traceable to exactly the version it was produced from.
    """

    format: str
    filename: str
    content_type: str
    body: str
    project_id: str
    draft_id: str
    version_id: str
    version_number: int
    snapshot_id: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class ProjectExportUnit:
    """One ordered unit inside a whole-project export.

    Every field is a traceability pointer to the exact latest version this unit
    contributed to the exported body, so a delivery manifest can reproduce the
    export from the immutable snapshots it was built from.
    """

    draft_id: str
    title: str
    chapter_id: str | None
    chapter_title: str | None
    chapter_position: int | None
    unit_kind: UnitKind | None
    position: int | None
    version_id: str
    version_number: int
    snapshot_id: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class ProjectExport:
    """An ordered-latest export of a whole project (W4, D6=A).

    ``body`` joins each included unit's latest snapshot ``raw_text`` verbatim in
    ``position`` order. The only synthesized text is a per-unit title line
    (Markdown ``# {title}`` heading, plain title line for txt); no AI analysis
    metadata is injected. Units are non-archived by default; ``include_archived``
    opts archived units back in. Units with no saved version are skipped because
    they have no snapshot to export. ``units`` backs the on-request delivery
    manifest and always matches the order the bodies were joined.
    """

    format: str
    filename: str
    content_type: str
    body: str
    project_id: str
    include_archived: bool
    units: tuple[ProjectExportUnit, ...]
