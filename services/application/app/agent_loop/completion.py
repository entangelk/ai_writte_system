"""Flat agent loop completion judgment contract.

Implements the completion half of the terminal decision synthesis fixed in
docs/plans/flat-loop-gate.md (§task별 completion criteria 계약). ``completed`` is
a *hybrid* judgment: it needs both a structural condition (the task's target
artifact exists in defined form) and a self-report condition (the model did not
defer). This module owns the self-report abstraction and the judgment; the
profile-specific structural evaluation (what counts as the artifact for each
task) is the caller's responsibility and is locked when the Phase payload
schemas land, so callers pass a pre-evaluated ``artifact_present`` flag.

Output set is exactly {COMPLETED, AWAITING_REVIEW}. ``blocked`` (premise
deficit) and ``budget_exhausted`` are decided elsewhere (registry/resolution)
with explicit structural or budget signals; this judge only answers the
completion question when the run has reached a candidate terminal state.

The concrete wire format of the self-report signal (explicit token, structured
field, ...) is fixed in the provider-response parser slice. Here it is injected
as a SelfReport value, so the judgment is infrastructure-free and deterministic.
"""

from __future__ import annotations

from enum import StrEnum

from services.application.app.agent_loop.decision import LoopDecision


class SelfReport(StrEnum):
    """Termination-channel signal: how the model closes the run.

    FINALIZE submits the artifact as final; DEFER requests human judgment. This
    is the termination channel and is orthogonal to artifact-data-channel fields
    (candidate ``needs_review`` status, confidence, conflict) which describe the
    artifact's contents rather than how the run closes.
    """

    FINALIZE = "finalize"
    DEFER = "defer"


def judge_completion(artifact_present: bool, self_report: SelfReport) -> LoopDecision:
    """Return the completion decision for a candidate terminal state.

    ``completed`` requires *both* the structural condition (artifact present)
    and a finalize self-report; anything else that reaches this judge is
    ``awaiting_review``. A finalize without the structural artifact is NOT
    completed (flat-loop-gate.md §Loop Gate 보강점 "answer 존재 = 완료"), and a
    defer with an artifact is awaiting review regardless of the artifact's
    uncertain contents.
    """
    if artifact_present and self_report is SelfReport.FINALIZE:
        return LoopDecision.COMPLETED
    return LoopDecision.AWAITING_REVIEW
