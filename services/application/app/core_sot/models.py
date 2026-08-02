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
    # ``None`` exists only while the explicit W3 legacy migration is inspecting
    # pre-v1.7.14 documents. Every runtime-created/migrated Draft has both fields.
    unit_kind: UnitKind | None = None
    position: int | None = None


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
