"""Contract tests for the flat agent loop completion judgment.

Locks the completion half of the terminal decision synthesis defined in
docs/plans/flat-loop-gate.md (§task별 completion criteria 계약, §completion boundary
matrix). ``completed`` is a hybrid judgment: the structural condition (artifact
present) AND a finalize self-report. Each branch is guarded in both directions:

* should-fire: artifact + finalize -> completed; defer -> awaiting_review.
* over-strict: a finalize without the structural artifact is NOT completed
  (§Loop Gate 보강점 "answer 존재 = 완료"); artifact-channel uncertainty
  (candidate needs_review status, confidence, conflict) does NOT escalate a
  finalize.

The judge is profile-agnostic given a pre-evaluated ``artifact_present`` flag.
The per-task structural semantics (what counts as the artifact) are documented
per case and locked when the Phase payload schemas land, so each profile's
completed/awaiting_review row is exercised through the same uniform logic.
"""

import unittest

from services.application.app.agent_loop.completion import SelfReport, judge_completion
from services.application.app.agent_loop.decision import LoopDecision
from services.application.app.agent_loop.registry import TaskProfile

# Per-task structural condition that the caller evaluates into artifact_present.
# Documented here so the completion matrix is explicit per profile:
#   analysis_compare  : every analysis target candidate-ized (individual targets
#                       may be needs_review candidates; that is still a complete
#                       artifact -> artifact_present=True)
#   context_search    : a ContextPackage candidate built with pointer/budget
#   writing_generate  : a WritingCandidate produced
_STRUCTURAL_CONDITION = {
    TaskProfile.ANALYSIS_COMPARE: "all targets candidate-ized",
    TaskProfile.CONTEXT_SEARCH: "package candidate built",
    TaskProfile.WRITING_GENERATE: "candidate generated",
}


class SelfReportLiteralTest(unittest.TestCase):
    def test_self_report_has_finalize_and_defer(self):
        self.assertEqual(SelfReport.FINALIZE.value, "finalize")
        self.assertEqual(SelfReport.DEFER.value, "defer")

    def test_self_report_values_are_string_comparable(self):
        # StrEnum lets the termination-channel signal compare against the literal.
        self.assertEqual(SelfReport.FINALIZE, "finalize")
        self.assertEqual(SelfReport.DEFER, "defer")


class CompletionMatrixTest(unittest.TestCase):
    def test_artifact_present_and_finalize_completes_for_every_profile(self):
        # completed requires BOTH the structural condition and a finalize, for
        # every task profile. Artifact-channel uncertainty (needs_review /
        # confidence / conflict) is part of the artifact, so artifact_present=True
        # holds and a finalize stays completed (over-strict: never escalated).
        for profile, condition in _STRUCTURAL_CONDITION.items():
            with self.subTest(profile=profile.value, condition=condition):
                self.assertEqual(
                    judge_completion(True, SelfReport.FINALIZE),
                    LoopDecision.COMPLETED,
                )

    def test_defer_is_awaiting_review_for_every_profile(self):
        # artifact present but the model defers (requests human judgment).
        for profile in _STRUCTURAL_CONDITION:
            with self.subTest(profile=profile.value):
                self.assertEqual(
                    judge_completion(True, SelfReport.DEFER),
                    LoopDecision.AWAITING_REVIEW,
                )

    def test_finalize_without_artifact_is_not_completed(self):
        # over-strict guard (§Loop Gate 보강점 "answer 존재 = 완료"): a finalize
        # without the structural artifact is awaiting_review, never completed.
        self.assertEqual(
            judge_completion(False, SelfReport.FINALIZE),
            LoopDecision.AWAITING_REVIEW,
        )

    def test_no_artifact_and_defer_is_awaiting_review(self):
        # under-strict direction: absence of artifact is never masked as completed.
        self.assertEqual(
            judge_completion(False, SelfReport.DEFER),
            LoopDecision.AWAITING_REVIEW,
        )


if __name__ == "__main__":
    unittest.main()
