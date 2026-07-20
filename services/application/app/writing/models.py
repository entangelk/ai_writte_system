"""Phase 5.1 Writing AI contracts (generation-only slice).

The Writing AI turns a ``WritingRequest`` and a verified ``ContextPackage`` into
a ``WritingCandidate`` — never a final draft, never canon (kickoff brief
``docs/plans/05-writing-generation-decisions.md``). Slice 1 produces plain prose
(owner Q2); the self-report fields are defined here but populated by the later
Writing Gate slice.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from services.application.app.core_sot.models import UnitKind


# The Writing AI never decides canon: its output is always a review candidate
# (writing_agent_prompt.md §5.2).
WRITING_CANDIDATE_STATUS = "candidate"


class WritingIntent(StrEnum):
    # W3 Writing intent (W0 contract §3.1). ``append_current`` continues the
    # current draft's latest version; ``start_next_unit`` atomically opens the
    # next ordered unit. Legacy clients omit the field → append_current.
    APPEND_CURRENT = "append_current"
    START_NEXT_UNIT = "start_next_unit"


class WritingTaskType(StrEnum):
    # MVP first slice supports only continue_scene (plan §76). The enum extends
    # to revise/outline/critique/rewrite_style in later slices.
    CONTINUE_SCENE = "continue_scene"


class WritingOutputType(StrEnum):
    # continue_scene emits new prose to append (a patch), not a whole draft
    # (writing_agent_prompt.md §9.1). Editor application semantics are a later
    # slice.
    DRAFT_PATCH = "draft_patch"


class WritingGateDecision(StrEnum):
    PASS = "pass"
    REVISE = "revise"
    RETRIEVE_MORE = "retrieve_more"
    NEEDS_USER_REVIEW = "needs_user_review"
    BLOCK = "block"


class WritingGateFindingType(StrEnum):
    DO_NOT_USE = "do_not_use"
    POV = "pov"
    CONTINUITY = "continuity"


class WritingGateSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class CandidateClaimType(StrEnum):
    NARRATIVE_EVENT = "narrative_event"
    CHARACTER_STATE = "character_state"
    LOCATION_STATE = "location_state"
    RELATION_CHANGE = "relation_change"
    TIMELINE_FACT = "timeline_fact"
    FORESHADOWING_USE = "foreshadowing_use"
    FACTUAL_CLAIM = "factual_claim"
    INTERPRETATION = "interpretation"


class MemoryHintType(StrEnum):
    EVENT = "event"
    CHARACTER_FACT = "character_fact"
    LOCATION_FACT = "location_fact"
    RELATION = "relation"
    FORESHADOWING = "foreshadowing"
    TIMELINE_FACT = "timeline_fact"
    STYLE_SIGNAL = "style_signal"


class RiskNoteType(StrEnum):
    POV = "pov"
    TIMELINE = "timeline"
    CANON = "canon"
    FORESHADOWING = "foreshadowing"
    RELATION = "relation"
    STYLE = "style"
    FACTUALITY = "factuality"


class RiskSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class ContextPointer:
    """Stable pointer to one ContextPackage item (kickoff brief
    ``docs/plans/05-writing-stable-context-pointer-decisions.md`` D1=A).

    A projection of ``IndexPointer`` without ``project_id``: the project comes
    from the trusted request/candidate context, never from the model. Which of
    the four fields may be empty is an origin-specific invariant (sub-decision
    P-i) enforced in ``writing/context_pointer.py`` — a store only fills the
    fields it actually has.
    """

    collection: str
    document_id: str
    version_id: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class CandidateClaim:
    text: str
    claim_type: CandidateClaimType
    requires_gate_check: bool
    # D3=A: required array in the report wire (empty allowed). A claim with no
    # package evidence carries (); one grounded in the package carries the exact
    # pointers of the items it used. The dataclass default keeps non-report
    # constructions (revise resets, tests) valid — requiredness is a wire
    # contract enforced by ``report.parse_report``.
    related_context_pointers: tuple[ContextPointer, ...] = ()


@dataclass(frozen=True, slots=True)
class NewMemoryHint:
    hint_type: MemoryHintType
    text: str
    confidence: float
    should_analyze_after_save: bool


@dataclass(frozen=True, slots=True)
class RiskNote:
    risk_type: RiskNoteType
    severity: RiskSeverity
    message: str


@dataclass(frozen=True, slots=True)
class NextUnit:
    """Target for ``start_next_unit`` (W0 contract §3.1).

    ``title`` is nonblank, ``unit_kind`` is chapter|scene|other, and ``goal`` is
    an optional nonblank generation hint that is NEVER persisted as prose
    (WI-16). Validation lives at the accept boundary, not in this container.
    """

    title: str
    unit_kind: UnitKind
    goal: str | None = None


@dataclass(frozen=True, slots=True)
class WritingRequest:
    request_id: str
    project_id: str
    task_type: WritingTaskType
    instruction: str
    # The current text to continue from (continue_scene). Provided by the caller
    # in slice 1; a later slice may resolve it from the draft pointer via Core SOT.
    draft_excerpt: str = ""
    # W3 Writing intent (§3.1). The save target's meaning is owned solely by
    # ``intent``; the prompt never re-decides it. ``next_unit`` is required for
    # start_next_unit and must be null for append_current.
    intent: WritingIntent = WritingIntent.APPEND_CURRENT
    next_unit: NextUnit | None = None


@dataclass(frozen=True, slots=True)
class WritingCandidate:
    request_id: str
    project_id: str
    task_type: WritingTaskType
    output_type: WritingOutputType
    text: str
    status: str = WRITING_CANDIDATE_STATUS
    # Populated by the Writing Gate slice (structured self-report); empty here
    # because slice 1 emits plain prose (owner Q2).
    self_reported_constraints: tuple[str, ...] = ()
    candidate_claims: tuple[CandidateClaim, ...] = ()
    new_memory_hints: tuple[NewMemoryHint, ...] = ()
    risk_notes: tuple[RiskNote, ...] = ()
    # Assigned when the candidate is accepted and saved (a later slice).
    candidate_id: str | None = None
    generated_by_model: str = ""
    # W3 (§3.1): the candidate echoes the request's exact intent/next_unit. The
    # accept boundary rejects any candidate whose echo diverges from the request.
    intent: WritingIntent = WritingIntent.APPEND_CURRENT
    next_unit: NextUnit | None = None


@dataclass(frozen=True, slots=True)
class WritingGateFinding:
    finding_type: WritingGateFindingType
    severity: WritingGateSeverity
    message: str
    evidence: str
    # A later revise/retrieve orchestrator may consume this recommendation and
    # evidence. The Gate itself remains side-effect free (owner D3=A).
    recommended_decision: WritingGateDecision


@dataclass(frozen=True, slots=True)
class WritingGateResult:
    request_id: str
    project_id: str
    decision: WritingGateDecision
    findings: tuple[WritingGateFinding, ...]
    checked_constraints: tuple[str, ...]
    evaluated_by_model: str = ""
