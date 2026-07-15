"""Deterministic labelled fixtures for Writing Gate quality measurement.

The Gate is an LLM classifier, so contract tests with a fake provider can lock
the scoring machinery but cannot establish live prompt accuracy.  This module
keeps those concerns separate: fixture labels come from the approved Gate
decision boundaries, while the supplied Gate service remains the production
classifier under measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from services.application.app.context_search.models import (
    ContextPackage,
    ContextSearchPurpose,
)
from services.application.app.writing.metering import MeteredCallError
from services.application.app.writing.models import (
    WritingCandidate,
    WritingGateDecision,
    WritingGateFindingType,
    WritingGateResult,
    WritingOutputType,
    WritingRequest,
    WritingTaskType,
)
from services.llm_gateway.app.provider import TokenUsage


_PROJECT_ID = "writing-gate-quality"


class _Gate(Protocol):
    async def evaluate_metered(
        self, *, request: WritingRequest, candidate: WritingCandidate,
        package: ContextPackage,
    ) -> tuple[WritingGateResult, TokenUsage]: ...


@dataclass(frozen=True, slots=True)
class GateQualityCase:
    case_id: str
    expected_decision: WritingGateDecision
    expected_finding_types: tuple[WritingGateFindingType, ...]
    instruction: str
    draft_excerpt: str
    candidate_text: str
    constraints: tuple[str, ...] = ()
    do_not_use: tuple[str, ...] = ()

    def request(self, iteration: int) -> WritingRequest:
        return WritingRequest(
            request_id=f"gate-quality-{self.case_id}-{iteration}",
            project_id=_PROJECT_ID,
            task_type=WritingTaskType.CONTINUE_SCENE,
            instruction=self.instruction,
            draft_excerpt=self.draft_excerpt,
        )

    def candidate(self, iteration: int) -> WritingCandidate:
        return WritingCandidate(
            request_id=f"gate-quality-{self.case_id}-{iteration}",
            project_id=_PROJECT_ID,
            task_type=WritingTaskType.CONTINUE_SCENE,
            output_type=WritingOutputType.DRAFT_PATCH,
            text=self.candidate_text,
        )

    def package(self) -> ContextPackage:
        return ContextPackage(
            project_id=_PROJECT_ID,
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            macro_items=(),
            micro_evidence=(),
            constraints=self.constraints,
            do_not_use=self.do_not_use,
            token_estimate_total=0,
            degraded=False,
        )


# Labels are deliberately small and contract-derived.  The first two PASS
# cases are the over-strict guards for the observed live failure mode: a normal
# scene transition or a new compatible action is not itself a continuity bug.
GATE_QUALITY_CASES: tuple[GateQualityCase, ...] = (
    GateQualityCase(
        case_id="pass_live_seed_transition",
        expected_decision=WritingGateDecision.PASS,
        expected_finding_types=(),
        instruction="민아가 역 안으로 들어가는 다음 장면을 이어 써줘.",
        draft_excerpt="민아는 기차역 플랫폼에 서 있었다.",
        candidate_text=(
            "민아는 역 안으로 들어섰다. 비는 이미 그쳤고, "
            "그녀는 파란 편지를 주머니에 넣었다."
        ),
        constraints=(
            "현재 장면: 민아는 기차역 플랫폼에 서 있다.",
            "날씨: 비는 이미 그쳤다.",
            "소지품: 민아는 파란 편지를 갖고 있다.",
            "POV: 3인칭 민아 제한 시점.",
        ),
    ),
    GateQualityCase(
        case_id="pass_compatible_new_action",
        expected_decision=WritingGateDecision.PASS,
        expected_finding_types=(),
        instruction="민아가 편지를 확인하는 장면을 이어 써줘.",
        draft_excerpt="민아는 파란 편지를 주머니에 넣었다.",
        candidate_text="민아는 주머니에서 파란 편지를 꺼내 봉인을 살폈다.",
        constraints=(
            "소지품: 민아는 파란 편지를 갖고 있다.",
            "POV: 3인칭 민아 제한 시점.",
        ),
    ),
    GateQualityCase(
        case_id="revise_repairable_continuity",
        expected_decision=WritingGateDecision.REVISE,
        expected_finding_types=(WritingGateFindingType.CONTINUITY,),
        instruction="직전 장면의 상태를 유지하며 이어 써줘.",
        draft_excerpt="민아는 젖은 우산을 접어 들었다.",
        candidate_text="민아는 활짝 편 우산을 든 채 역 안으로 들어섰다.",
        constraints=("현재 상태: 민아의 우산은 접혀 있다.",),
    ),
    GateQualityCase(
        case_id="retrieve_more_missing_canon",
        expected_decision=WritingGateDecision.RETRIEVE_MORE,
        expected_finding_types=(WritingGateFindingType.CONTINUITY,),
        instruction="편지의 발신인을 드러내며 이어 써줘.",
        draft_excerpt="민아는 파란 편지를 주머니에 넣었다.",
        candidate_text="파란 편지의 발신인은 오래전에 떠난 준호였다.",
        constraints=(
            "소지품: 민아는 파란 편지를 갖고 있다.",
            "발신인 정보: 현재 ContextPackage에 없음.",
        ),
    ),
    GateQualityCase(
        case_id="needs_review_conflicting_context",
        expected_decision=WritingGateDecision.NEEDS_USER_REVIEW,
        expected_finding_types=(WritingGateFindingType.CONTINUITY,),
        instruction="아린이 검을 집는 장면을 이어 써줘.",
        draft_excerpt="아린은 검 앞에 섰다.",
        candidate_text="아린은 익숙한 오른손으로 검을 집었다.",
        constraints=(
            "기억 A: 아린은 오른손잡이다.",
            "기억 B: 아린은 왼손잡이다.",
            "두 기억은 아직 사람 검토 전이며 서로 상충한다.",
        ),
    ),
    GateQualityCase(
        case_id="block_do_not_use",
        expected_decision=WritingGateDecision.BLOCK,
        expected_finding_types=(WritingGateFindingType.DO_NOT_USE,),
        instruction="긴장감을 유지하며 이어 써줘.",
        draft_excerpt="민아는 봉인된 편지를 바라보았다.",
        candidate_text="편지에는 준호가 배신자라는 사실이 적혀 있었다.",
        do_not_use=("준호가 배신자라는 사실을 공개하지 않는다.",),
    ),
    GateQualityCase(
        case_id="block_explicit_pov",
        expected_decision=WritingGateDecision.BLOCK,
        expected_finding_types=(WritingGateFindingType.POV,),
        instruction="민아의 제한 시점으로 이어 써줘.",
        draft_excerpt="민아는 준호를 바라보았다.",
        candidate_text="준호는 민아가 자신을 의심한다는 사실에 속으로 안도했다.",
        constraints=(
            "POV: 3인칭 민아 제한 시점. 민아가 알 수 없는 타인의 내면은 서술 금지.",
        ),
    ),
)


async def run_gate_quality_benchmark(
    gate: _Gate, *, repeats: int = 1,
    cases: tuple[GateQualityCase, ...] = GATE_QUALITY_CASES,
) -> dict[str, object]:
    """Score labelled cases without changing the Gate or persisting prose."""
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    rows: list[dict[str, object]] = []
    for case in cases:
        for iteration in range(1, repeats + 1):
            row: dict[str, object] = {
                "case_id": case.case_id,
                "iteration": iteration,
                "expected_decision": case.expected_decision.value,
                "expected_finding_types": [
                    item.value for item in case.expected_finding_types
                ],
                "status": "succeeded",
                "actual_decision": None,
                "actual_finding_types": [],
                "decision_match": False,
                "finding_types_match": False,
                "matched": False,
                "total_tokens": 0,
                "error_type": None,
                "error_detail": None,
            }
            try:
                result, usage = await gate.evaluate_metered(
                    request=case.request(iteration),
                    candidate=case.candidate(iteration),
                    package=case.package(),
                )
            except MeteredCallError as exc:
                row["status"] = "invalid_result"
                row["total_tokens"] = exc.usage.total_tokens
                row["error_type"] = type(exc.cause).__name__
                row["error_detail"] = str(exc.cause)
            except Exception as exc:  # noqa: BLE001 - benchmark isolates cases
                row["status"] = "error"
                row["error_type"] = type(exc).__name__
                row["error_detail"] = str(exc)
            else:
                actual_types = tuple(
                    dict.fromkeys(item.finding_type for item in result.findings)
                )
                decision_match = result.decision is case.expected_decision
                finding_match = all(
                    expected in actual_types
                    for expected in case.expected_finding_types
                )
                if not case.expected_finding_types:
                    finding_match = not actual_types
                row.update({
                    "actual_decision": result.decision.value,
                    "actual_finding_types": [item.value for item in actual_types],
                    "decision_match": decision_match,
                    "finding_types_match": finding_match,
                    "matched": decision_match and finding_match,
                    "total_tokens": usage.total_tokens,
                })
            rows.append(row)

    matched = sum(bool(row["matched"]) for row in rows)
    succeeded = sum(row["status"] == "succeeded" for row in rows)
    return {
        "fixture_version": "writing_gate_quality_v1",
        "case_count": len(cases),
        "repeats": repeats,
        "attempt_count": len(rows),
        "succeeded_count": succeeded,
        "matched_count": matched,
        "accuracy": matched / len(rows) if rows else 0.0,
        "complete": succeeded == len(rows),
        "rows": rows,
    }
