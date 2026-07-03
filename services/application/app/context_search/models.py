"""Phase 4 context search domain contracts (Slice 4.1).

Approved scope: docs/plans/04-agentic-search-kickoff-decisions.md (SoT v1.6.30).
First-slice literal sets are intentionally minimal; enums extend in later
slices without schema changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from services.application.app.indexing.models import IndexPointer


CONTEXT_PACKAGE_STATUS_CANDIDATE = "candidate"
GATE_PASS = "pass"
GATE_REJECT = "reject"
BUDGET_EXCLUDED_REASON = "budget_exceeded"


class ContextSearchPurpose(StrEnum):
    WRITING_CONTEXT = "writing_context"


class ContextNeed(StrEnum):
    CURRENT_SCENE = "current_scene"
    RECENT_SCENES = "recent_scenes"
    EVENT_CONTEXT = "event_context"
    SOURCE_QUOTE = "source_quote"


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
    trace: ContextSearchTrace
    status: str = CONTEXT_PACKAGE_STATUS_CANDIDATE


@dataclass(frozen=True, slots=True)
class GateFinding:
    check: str
    detail: str


@dataclass(frozen=True, slots=True)
class GateDecision:
    decision: str
    findings: tuple[GateFinding, ...] = field(default=())
