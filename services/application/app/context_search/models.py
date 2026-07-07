"""Phase 4 context search domain contracts (Slice 4.1).

Approved scope: docs/plans/04-agentic-search-kickoff-decisions.md (SoT v1.6.30).
First-slice literal sets are intentionally minimal; enums extend in later
slices without schema changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from services.application.app.analysis.models import AnalysisCandidateType
from services.application.app.indexing.models import IndexPointer
from services.application.app.memory.models import MemoryStatus
from services.application.app.memory.scope import MemoryScope


CONTEXT_PACKAGE_STATUS_CANDIDATE = "candidate"
GATE_PASS = "pass"
GATE_REJECT = "reject"
BUDGET_EXCLUDED_REASON = "budget_exceeded"


class ContextSearchPurpose(StrEnum):
    WRITING_CONTEXT = "writing_context"
    # Phase 2B.2: prior-memory comparison view consumed by Analysis compare
    # (2B.3), not by Writing. The two purposes share this package schema but
    # branch on serialization, Gate rules, and which section is filled.
    ANALYSIS_CONTEXT = "analysis_context"


class ContextNeed(StrEnum):
    CURRENT_SCENE = "current_scene"
    RECENT_SCENES = "recent_scenes"
    EVENT_CONTEXT = "event_context"
    SOURCE_QUOTE = "source_quote"
    # Phase 2B.2: canonical prior memories retrieved for Analysis comparison.
    PRIOR_MEMORY = "prior_memory"
    # Writing canonical inclusion (⑤ §5 B): approved canonical memories surfaced
    # as micro evidence for Writing. Served Mongo-direct now; the retrieval layer
    # extends to vector/search-engine later (docs/plans/
    # 04-writing-canonical-context-decisions.md, D2=A).
    CANONICAL_MEMORY = "canonical_memory"


class SearchTool(StrEnum):
    VECTOR = "vector"
    MONGO = "mongo"


class ContextItemStatus(StrEnum):
    CANDIDATE = "candidate"
    CANONICAL = "canonical"


class ContextSearchErrorType(StrEnum):
    """Failure lineage so later retry logic can pick its target component."""

    BACKEND_ERROR = "backend_error"
    SYSTEM_ERROR = "system_error"
    LLM_ERROR = "llm_error"
    SOT_ERROR = "sot_error"


# Needs that a given tool is allowed to serve. Plans violating this mapping
# are rejected as llm_error because the planner produced them.
NEED_ALLOWED_TOOLS: dict[ContextNeed, tuple[SearchTool, ...]] = {
    ContextNeed.CURRENT_SCENE: (SearchTool.MONGO,),
    ContextNeed.RECENT_SCENES: (SearchTool.MONGO,),
    ContextNeed.EVENT_CONTEXT: (SearchTool.VECTOR,),
    ContextNeed.SOURCE_QUOTE: (SearchTool.VECTOR,),
    # canonical_memory is served Mongo-direct (D2=A); when the retrieval layer
    # gains a vector path it adds VECTOR here without touching item/Gate logic.
    ContextNeed.CANONICAL_MEMORY: (SearchTool.MONGO,),
}

# Needs whose items land in macro context; the rest are micro evidence.
MACRO_NEEDS = (ContextNeed.CURRENT_SCENE, ContextNeed.RECENT_SCENES)


@dataclass(frozen=True, slots=True)
class ContextBudget:
    max_tokens: int


@dataclass(frozen=True, slots=True)
class CurrentPosition:
    draft_id: str
    version_id: str


@dataclass(frozen=True, slots=True)
class ContextSearchRequest:
    project_id: str
    purpose: ContextSearchPurpose
    needs: tuple[ContextNeed, ...]
    query: str
    current_position: CurrentPosition | None
    context_budget: ContextBudget


@dataclass(frozen=True, slots=True)
class SearchPlanStep:
    step_id: str
    need: ContextNeed
    tools: tuple[SearchTool, ...]
    query: str


@dataclass(frozen=True, slots=True)
class SearchPlan:
    plan_id: str
    project_id: str
    steps: tuple[SearchPlanStep, ...]


@dataclass(frozen=True, slots=True)
class ContextItem:
    need: ContextNeed
    status: ContextItemStatus
    text: str
    pointer: IndexPointer
    snapshot_id: str
    sot_reloaded: bool
    token_estimate: int
    source_ref_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PriorMemoryItem:
    """Phase 2B.2 comparison view of one canonical prior memory (§8 ⑧).

    Carries the taxonomy's five required comparison fields — existing value,
    status, source, version, and the reason it was retrieved — plus the
    memory identity. ``value`` is the MemoryEntry ``payload`` (MemoryEntry has
    no ``value`` field; F3). ``scope`` (scope_type/scope_id) is not carried
    here because MemoryEntry lacks it (D1=A defers scope to 2B.3), so §8 ⑧
    stays open until 2B.3.
    """

    memory_id: str
    memory_type: AnalysisCandidateType
    value: Mapping[str, Any]
    status: MemoryStatus
    version: int
    source_ref_ids: tuple[str, ...]
    match_reason: str
    # Phase 2B.3: deterministic identity scope (character → name; else None).
    # Completes §8 ⑧ (memory type/scope/status/version/retrieval reason).
    scope: MemoryScope | None = None


@dataclass(frozen=True, slots=True)
class AnalysisContextRequest:
    """Deterministic prior-memory search primitive (D4 memory_type layer).

    ``memory_types`` is the coarse candidate-group filter (D1=A). An empty
    tuple yields an empty package — there is no comparison target — never the
    whole project memory. ``exclude_job_id`` implements the F4 self-exclusion
    default so a job does not compare against memories it just promoted.
    """

    project_id: str
    needs: tuple[ContextNeed, ...]
    memory_types: tuple[AnalysisCandidateType, ...] = ()
    exclude_job_id: str | None = None


@dataclass(frozen=True, slots=True)
class StepFailure:
    error_type: ContextSearchErrorType
    detail: str


@dataclass(frozen=True, slots=True)
class ExcludedHit:
    record_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class SearchStepTrace:
    step_id: str
    need: ContextNeed
    tool: SearchTool
    hits_considered: int
    items_produced: int
    excluded: tuple[ExcludedHit, ...]
    failure: StepFailure | None


@dataclass(frozen=True, slots=True)
class ContextSearchTrace:
    plan: SearchPlan
    steps: tuple[SearchStepTrace, ...]
    budget_excluded: tuple[ExcludedHit, ...]


@dataclass(frozen=True, slots=True)
class ContextPackage:
    project_id: str
    purpose: ContextSearchPurpose
    macro_items: tuple[ContextItem, ...]
    micro_evidence: tuple[ContextItem, ...]
    constraints: tuple[str, ...]
    do_not_use: tuple[str, ...]
    token_estimate_total: int
    degraded: bool
    # Writing packages carry a full search trace; the analysis_context package
    # has no planner/vector plan, so trace is None there (D3=A: one schema,
    # purpose branches which section is filled).
    trace: ContextSearchTrace | None = None
    prior_memories: tuple[PriorMemoryItem, ...] = ()
    status: str = CONTEXT_PACKAGE_STATUS_CANDIDATE


@dataclass(frozen=True, slots=True)
class GateFinding:
    check: str
    detail: str


@dataclass(frozen=True, slots=True)
class GateDecision:
    decision: str
    findings: tuple[GateFinding, ...] = field(default=())
