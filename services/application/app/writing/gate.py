"""Phase 5.2 side-effect-free, one-turn LLM Writing Gate."""

from __future__ import annotations

from collections.abc import Mapping

from services.application.app.analysis.prompt_templates import (
    PromptTemplate, PromptTemplateError, PromptTemplateService,
)
from services.application.app.context_search.models import ContextPackage
from services.application.app.writing.gate_prompt import (
    WRITING_GATE_PROMPT_VERSION, WRITING_GATE_TASK_TYPE, WRITING_GATE_TEMPLATE,
    build_writing_gate_request, json_object,
)
from services.application.app.writing.models import (
    WritingCandidate, WritingGateDecision, WritingGateFinding,
    WritingGateFindingType, WritingGateResult, WritingGateSeverity,
    WritingRequest,
)
from services.application.app.writing.metering import MeteredCallError
from services.llm_gateway.app.provider import LLMProvider, TokenUsage


class WritingGateError(ValueError):
    pass


class InvalidWritingGateResult(RuntimeError):
    pass


_PRIORITY = {
    WritingGateDecision.PASS: 0, WritingGateDecision.REVISE: 1,
    WritingGateDecision.RETRIEVE_MORE: 2,
    WritingGateDecision.NEEDS_USER_REVIEW: 3, WritingGateDecision.BLOCK: 4,
}


def seed_writing_gate_template(service: PromptTemplateService) -> PromptTemplate:
    return service.seed_template(task_type=WRITING_GATE_TASK_TYPE,
                                 version=WRITING_GATE_PROMPT_VERSION,
                                 template=WRITING_GATE_TEMPLATE)


class WritingGateService:
    def __init__(self, provider: LLMProvider, *,
                 prompt_templates: PromptTemplateService,
                 model: str | None = None, max_tokens: int = 1024) -> None:
        self._provider = provider
        self._templates = prompt_templates
        self._model = model
        self._max_tokens = max_tokens

    async def evaluate(self, *, request: WritingRequest,
                       candidate: WritingCandidate,
                       package: ContextPackage) -> WritingGateResult:
        try:
            evaluated, _usage = await self.evaluate_metered(
                request=request, candidate=candidate, package=package)
        except MeteredCallError as exc:
            raise exc.cause from exc
        return evaluated

    async def evaluate_metered(self, *, request: WritingRequest,
                               candidate: WritingCandidate,
                               package: ContextPackage
                               ) -> tuple[WritingGateResult, TokenUsage]:
        self._validate(request, candidate, package)
        try:
            template = self._templates.get_template(
                task_type=WRITING_GATE_TASK_TYPE,
                version=WRITING_GATE_PROMPT_VERSION)
        except PromptTemplateError as exc:
            raise WritingGateError(f"writing gate template unavailable: {exc}") from exc
        result = await self._provider.generate(build_writing_gate_request(
            request=request, candidate=candidate, package=package,
            prompt_template=template, model=self._model,
            max_tokens=self._max_tokens))
        try:
            decision, findings, checked = parse_writing_gate_result(result.content)
            if any(item.evidence not in candidate.text for item in findings):
                raise ValueError("finding evidence must occur in candidate text")
        except ValueError as exc:
            cause = InvalidWritingGateResult(
                f"writing gate produced an invalid result: {exc}"
            )
            raise MeteredCallError(cause, result.usage) from exc
        return WritingGateResult(request_id=request.request_id,
                                 project_id=request.project_id,
                                 decision=decision, findings=findings,
                                 checked_constraints=checked,
                                 evaluated_by_model=result.model), result.usage

    @staticmethod
    def _validate(request: WritingRequest, candidate: WritingCandidate,
                  package: ContextPackage) -> None:
        if not request.instruction.strip():
            raise WritingGateError("instruction is required")
        if candidate.request_id != request.request_id:
            raise WritingGateError("candidate belongs to a different request")
        if candidate.project_id != request.project_id or package.project_id != request.project_id:
            raise WritingGateError("writing gate inputs belong to different projects")
        if not candidate.text.strip():
            raise WritingGateError("candidate text is required")


def parse_writing_gate_result(content: str):
    root = json_object(content)
    if set(root) != {"decision", "findings", "checked_constraints"}:
        raise ValueError("result fields do not match schema")
    try:
        decision = WritingGateDecision(root["decision"])
    except (ValueError, TypeError) as exc:
        raise ValueError("unknown decision literal") from exc
    raw_findings = root["findings"]
    raw_checked = root["checked_constraints"]
    if not isinstance(raw_findings, list) or not isinstance(raw_checked, list):
        raise ValueError("findings and checked_constraints must be arrays")
    findings = tuple(_finding(item) for item in raw_findings)
    checked = tuple(_nonempty_string(item, "checked constraint")
                    for item in raw_checked)
    # 증분 3 (D5=A/D6=A): style findings are advisory — excluded from the decision
    # priority so a candidate whose only findings are style still passes (경고이지
    # 차단 아님, 최종 결정은 사용자). They remain in `findings` so the author sees them.
    decision_driving = tuple(
        item for item in findings
        if item.finding_type is not WritingGateFindingType.STYLE
    )
    expected = max((item.recommended_decision for item in decision_driving),
                   key=_PRIORITY.get, default=WritingGateDecision.PASS)
    if decision is not expected:
        raise ValueError("decision does not match finding priority")
    return decision, findings, checked


def _finding(value: object) -> WritingGateFinding:
    if not isinstance(value, Mapping) or set(value) != {
        "type", "severity", "message", "evidence", "recommended_decision"
    }:
        raise ValueError("finding fields do not match schema")
    try:
        finding_type = WritingGateFindingType(value["type"])
        severity = WritingGateSeverity(value["severity"])
        recommendation = WritingGateDecision(value["recommended_decision"])
    except (ValueError, TypeError) as exc:
        raise ValueError("finding contains an unknown literal") from exc
    if recommendation is WritingGateDecision.PASS:
        raise ValueError("a finding cannot recommend pass")
    if finding_type in {
        WritingGateFindingType.DO_NOT_USE, WritingGateFindingType.POV
    } and (severity is not WritingGateSeverity.ERROR or
           recommendation is not WritingGateDecision.BLOCK):
        raise ValueError("do_not_use and POV findings must be blocking errors")
    # 증분 3 (D5=A): a style finding is advisory — warning severity, and it may only
    # recommend needs_user_review (never error, never block/revise/retrieve_more).
    # This locks "warning 전용·자동 revise 제외·block 없음" at the parse boundary.
    if finding_type is WritingGateFindingType.STYLE and (
        severity is not WritingGateSeverity.WARNING
        or recommendation is not WritingGateDecision.NEEDS_USER_REVIEW
    ):
        raise ValueError(
            "style findings must be warning severity recommending needs_user_review"
        )
    return WritingGateFinding(finding_type=finding_type, severity=severity,
        message=_nonempty_string(value["message"], "message"),
        evidence=_nonempty_string(value["evidence"], "evidence"),
        recommended_decision=recommendation)


def _nonempty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value
