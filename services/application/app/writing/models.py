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


# The Writing AI never decides canon: its output is always a review candidate
# (writing_agent_prompt.md §5.2).
WRITING_CANDIDATE_STATUS = "candidate"


class WritingTaskType(StrEnum):
    # MVP first slice supports only continue_scene (plan §76). The enum extends
    # to revise/outline/critique/rewrite_style in later slices.
    CONTINUE_SCENE = "continue_scene"


class WritingOutputType(StrEnum):
    # continue_scene emits new prose to append (a patch), not a whole draft
    # (writing_agent_prompt.md §9.1). Editor application semantics are a later
    # slice.
    DRAFT_PATCH = "draft_patch"


@dataclass(frozen=True, slots=True)
class WritingBrief:
    """Optional style guidance. Not project memory — never a fact source."""

    project_id: str
    style_rules: tuple[str, ...] = ()
    forbidden_patterns: tuple[str, ...] = ()
    preferred_patterns: tuple[str, ...] = ()
    tone: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WritingRequest:
    request_id: str
    project_id: str
    task_type: WritingTaskType
    instruction: str
    # The current text to continue from (continue_scene). Provided by the caller
    # in slice 1; a later slice may resolve it from the draft pointer via Core SOT.
    draft_excerpt: str = ""


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
    # Assigned when the candidate is accepted and saved (a later slice).
    candidate_id: str | None = None
    generated_by_model: str = ""
