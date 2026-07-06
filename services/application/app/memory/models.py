"""Phase 2B.1 canonical MemoryEntry contracts.

A ``MemoryEntry`` is the canonical (approved) memory store unit. Phase 2B.1
only creates the first version of a memory by promoting a Phase 2A
``needs_review`` candidate; it preserves the candidate's payload, provenance,
source refs, and confidence and records the promotion audit trail. Entity/scope
key resolution and versioned upsert are later slices (2B.3/2B.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from services.application.app.analysis.models import (
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.memory.scope import MemoryScope


class MemoryStatus(StrEnum):
    CANONICAL = "canonical"
    # Phase 2B.4: a versioned upsert (update/add_evidence) mints a new canonical
    # version and marks the prior entry superseded, preserving it immutably.
    SUPERSEDED = "superseded"


class PromotionMode(StrEnum):
    MANUAL = "manual"
    AUTO_THRESHOLD = "auto_threshold"


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    id: str
    project_id: str
    memory_type: AnalysisCandidateType
    status: MemoryStatus
    provenance: AnalysisProvenance
    confidence: float
    source_ref_ids: tuple[str, ...]
    payload: Mapping[str, Any]
    version: int
    analysis_job_id: str
    source_candidate_id: str
    promotion_mode: PromotionMode
    applied_threshold: float | None
    # Phase 2B.3: deterministic identity key (character → normalized name;
    # event/open_question → None). Computed at promotion; used by compare.
    scope: MemoryScope | None = None
    # Phase 2B.4: id of the memory version this entry replaced (update/
    # add_evidence). ``None`` for a first (``version=1``) canonical entry.
    supersedes: str | None = None


@dataclass(frozen=True, slots=True)
class PromoteMemoryResult:
    memory: MemoryEntry
    idempotent_replay: bool
