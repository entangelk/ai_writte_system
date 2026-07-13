"""Targeted follow-up retrieval planning and ContextPackage merge."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from services.application.app.analysis.prompt_templates import (
    PromptTemplateError,
    PromptTemplateService,
)
from services.application.app.context_search.models import (
    BUDGET_EXCLUDED_REASON,
    MACRO_NEEDS,
    ContextItem,
    ContextNeed,
    ContextPackage,
    CurrentPosition,
    ExcludedHit,
)
from services.application.app.writing.models import (
    WritingCandidate,
    WritingGateDecision,
    WritingGateResult,
    WritingRequest,
)
from services.llm_gateway.app.payload import (
    ChatCompletionRequest,
    ChatMessage,
)
from services.llm_gateway.app.provider import LLMProvider


TASK = "writing_retrieval_plan"
VERSION = "writing_retrieval_plan_v1"
TEMPLATE = """You plan one targeted follow-up retrieval after a Writing Gate returned retrieve_more.

Return JSON only with exactly:
{
  "query": "non-empty search query",
  "needs": ["one or more allowed need literals"]
}

Choose only the minimum needs required to verify the supplied candidate claims. Never choose candidate_memory and never invent a need literal. Do not evaluate or rewrite the prose."""

ALLOWED_WRITING_RETRIEVAL_NEEDS = (
    ContextNeed.CURRENT_SCENE,
    ContextNeed.RECENT_SCENES,
    ContextNeed.EVENT_CONTEXT,
    ContextNeed.SOURCE_QUOTE,
    ContextNeed.CANONICAL_MEMORY,
)


class WritingRetrievalPlannerError(RuntimeError):
    pass


class InvalidWritingRetrievalPlan(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WritingRetrievalPlan:
    query: str
    needs: tuple[ContextNeed, ...]


def seed_writing_retrieval_template(service: PromptTemplateService):
    return service.seed_template(task_type=TASK, version=VERSION, template=TEMPLATE)


class TerminalJsonWritingRetrievalPlanner:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        prompt_templates: PromptTemplateService,
        model: str | None = None,
        max_tokens: int = 512,
    ) -> None:
        self._provider = provider
        self._templates = prompt_templates
        self._model = model
        self._max_tokens = max_tokens

    async def plan(
        self,
        *,
        request: WritingRequest,
        candidate: WritingCandidate,
        gate: WritingGateResult,
        current_position: CurrentPosition | None = None,
    ) -> WritingRetrievalPlan:
        if gate.decision is not WritingGateDecision.RETRIEVE_MORE:
            raise WritingRetrievalPlannerError(
                "retrieval planner requires a retrieve_more Gate result"
            )
        findings = tuple(
            finding for finding in gate.findings
            if finding.recommended_decision is WritingGateDecision.RETRIEVE_MORE
        )
        if not findings:
            raise WritingRetrievalPlannerError(
                "retrieve_more Gate result has no retrieve_more finding"
            )
        try:
            template = self._templates.get_template(task_type=TASK, version=VERSION)
        except PromptTemplateError as exc:
            raise WritingRetrievalPlannerError(
                f"writing retrieval template unavailable: {exc}"
            ) from exc
        allowed_needs = tuple(
            need for need in ALLOWED_WRITING_RETRIEVAL_NEEDS
            if current_position is not None or need not in MACRO_NEEDS
        )
        chat_request = self._request(
            request=request,
            candidate=candidate,
            findings=findings,
            template=template.template,
            allowed_needs=allowed_needs,
        )
        result = await self._provider.generate(chat_request)
        try:
            return parse_writing_retrieval_plan(
                result.content, allowed_needs=allowed_needs
            )
        except InvalidWritingRetrievalPlan as first:
            repair = await self._provider.generate(ChatCompletionRequest(
                messages=(
                    ChatMessage(role="system", content=TEMPLATE),
                    ChatMessage(role="user", content=json.dumps({
                        "invalid": result.content,
                        "error": str(first),
                    }, ensure_ascii=False)),
                ),
                model=self._model,
                max_tokens=self._max_tokens,
                thinking=False,
            ))
            return parse_writing_retrieval_plan(
                repair.content, allowed_needs=allowed_needs
            )

    def _request(self, *, request, candidate, findings, template, allowed_needs):
        payload = {
            "request": {
                "request_id": request.request_id,
                "instruction": request.instruction,
            },
            "candidate_text": candidate.text,
            "retrieve_more_findings": [
                {
                    "type": finding.finding_type.value,
                    "severity": finding.severity.value,
                    "message": finding.message,
                    "evidence": finding.evidence,
                }
                for finding in findings
            ],
            "allowed_needs": [
                need.value for need in allowed_needs
            ],
        }
        return ChatCompletionRequest(
            messages=(
                ChatMessage(role="system", content=template),
                ChatMessage(
                    role="user",
                    content=json.dumps(payload, ensure_ascii=False, sort_keys=True),
                ),
            ),
            model=self._model,
            max_tokens=self._max_tokens,
            thinking=False,
        )


def parse_writing_retrieval_plan(
    content: str,
    *,
    allowed_needs: tuple[ContextNeed, ...] = ALLOWED_WRITING_RETRIEVAL_NEEDS,
) -> WritingRetrievalPlan:
    try:
        root = json.loads(content)
    except json.JSONDecodeError as exc:
        raise InvalidWritingRetrievalPlan(
            "writing retrieval plan must be JSON"
        ) from exc
    if not isinstance(root, Mapping) or set(root) != {"query", "needs"}:
        raise InvalidWritingRetrievalPlan(
            "writing retrieval plan fields do not match schema"
        )
    query = root["query"]
    raw_needs = root["needs"]
    if not isinstance(query, str) or not query.strip():
        raise InvalidWritingRetrievalPlan("query must be a non-empty string")
    if not isinstance(raw_needs, list) or not raw_needs:
        raise InvalidWritingRetrievalPlan("needs must be a non-empty array")
    needs: list[ContextNeed] = []
    for raw_need in raw_needs:
        try:
            need = ContextNeed(raw_need)
        except (TypeError, ValueError) as exc:
            raise InvalidWritingRetrievalPlan(
                f"unknown need literal: {raw_need!r}"
            ) from exc
        if need not in allowed_needs:
            raise InvalidWritingRetrievalPlan(
                f"need is not allowed for Writing retrieval: {need.value}"
            )
        if need in needs:
            raise InvalidWritingRetrievalPlan(
                f"duplicate need: {need.value}"
            )
        needs.append(need)
    return WritingRetrievalPlan(query=query.strip(), needs=tuple(needs))


def merge_context_packages(
    base: ContextPackage,
    delta: ContextPackage,
    *,
    max_tokens: int,
) -> ContextPackage:
    if base.project_id != delta.project_id or base.purpose is not delta.purpose:
        raise ValueError("context packages belong to different scopes")
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")

    # Targeted delta comes first so a full prior package cannot starve the exact
    # evidence requested by retrieve_more. Pointer identity prevents the same
    # canonical artifact from occupying budget twice under different needs.
    ordered = (
        delta.macro_items + delta.micro_evidence
        + base.macro_items + base.micro_evidence
    )
    seen: set[tuple[str, str, str, str]] = set()
    included: list[ContextItem] = []
    excluded: list[ExcludedHit] = []
    total = 0
    for item in ordered:
        identity = (
            item.pointer.collection,
            item.pointer.document_id,
            item.pointer.version_id,
            item.pointer.content_hash,
        )
        if identity in seen:
            continue
        seen.add(identity)
        if total + item.token_estimate <= max_tokens:
            included.append(item)
            total += item.token_estimate
        else:
            excluded.append(ExcludedHit(
                record_id=item.pointer.document_id,
                reason=BUDGET_EXCLUDED_REASON,
            ))

    macro = tuple(item for item in included if item.need in MACRO_NEEDS)
    micro = tuple(item for item in included if item.need not in MACRO_NEEDS)
    constraints = tuple(dict.fromkeys(base.constraints + delta.constraints))
    do_not_use = tuple(dict.fromkeys(base.do_not_use + delta.do_not_use))
    # The delta trace describes the actual follow-up retrieval. Full multi-stage
    # trace composition stays with the later public stages/audit contract.
    trace = delta.trace if delta.trace is not None else base.trace
    return ContextPackage(
        project_id=base.project_id,
        purpose=base.purpose,
        macro_items=macro,
        micro_evidence=micro,
        constraints=constraints,
        do_not_use=do_not_use,
        token_estimate_total=total,
        degraded=base.degraded or delta.degraded,
        trace=trace,
        prior_memories=base.prior_memories + tuple(
            item for item in delta.prior_memories if item not in base.prior_memories
        ),
        status=base.status,
    )
