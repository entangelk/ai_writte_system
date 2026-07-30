"""Strict structured report extraction for a plain-prose WritingCandidate."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import replace

from services.application.app.analysis.prompt_templates import PromptTemplateService
from services.application.app.context_search.models import ContextPackage
from services.application.app.writing.context_pointer import (
    InvalidContextPointer, package_pointers,
)
from services.application.app.writing.json_extract import strip_code_fence
from services.application.app.writing.models import (
    CandidateClaim, CandidateClaimType, ContextPointer, MemoryHintType,
    NewMemoryHint, RiskNote, RiskNoteType, RiskSeverity, WritingCandidate,
)
from services.application.app.writing.prompt import format_context_package
from services.application.app.writing.metering import MeteredCallError, add_usage
from services.llm_gateway.app.payload import ChatCompletionRequest, ChatMessage
from services.llm_gateway.app.provider import TokenUsage
from services.llm_gateway.app.provider import LLMProvider

TASK = "writing_candidate_report"
# v2 (K-6=R-e, 2026-07-30): 항목을 포인터 JSON이 아니라 **번호**로 인용한다. 본문이 요구하는
# 출력 형식이 바뀌었으므로 버전을 올린다 — v1이 두 형식을 뜻하면 진단·감사가 거짓말을 한다.
# 이 템플릿은 Mongo 영속이 아니라 조립 때마다 in-memory seed이므로(sha256 불변 핀은
# `analysis_extract` 전용) 기존 배포와 충돌하지 않는다.
VERSION = "writing_candidate_report_v2"
TEMPLATE = """Analyze candidate prose and return one JSON object only. Do not use Markdown or explanatory text, and do not wrap the JSON in a ``` code fence.

The object must have exactly these four fields:
{
  "self_reported_constraints": ["non-empty string"],
  "candidate_claims": [
    {
      "text": "non-empty string",
      "type": "narrative_event|character_state|location_state|relation_change|timeline_fact|foreshadowing_use|factual_claim|interpretation",
      "requires_gate_check": true,
      "related_context_pointers": [1]
    }
  ],
  "new_memory_hints": [
    {
      "type": "event|character_fact|location_fact|relation|foreshadowing|timeline_fact|style_signal",
      "text": "non-empty string",
      "confidence": 0.0,
      "should_analyze_after_save": true
    }
  ],
  "risk_notes": [
    {
      "type": "pov|timeline|canon|foreshadowing|relation|style|factuality",
      "severity": "low|medium|high|critical",
      "message": "non-empty string"
    }
  ]
}

Each `type` and `severity` must be one literal from its pipe-separated list, not the whole list. Confidence must be a finite number from 0 through 1. Empty arrays are valid and preferred over invented facts.

`related_context_pointers` is required on every claim. Each context_package item is shown as `- [N] [label] text`, where N is that item's number. When a claim uses an item, put that item's number in `related_context_pointers` as a plain integer — the number only, not the item text and not a quoted string. Never invent a number, never use a number that is not shown in this request, and never repeat a number within one claim. When a claim has no supporting item, return `[]`."""


class InvalidCandidateReport(RuntimeError): pass


# A real 12B occasionally emits a malformed report (e.g. a non-array field) that
# the first repair does not fix; a second bounded repair recovers most of these
# before the whole candidate is discarded. Each retry's usage is still metered so
# the aggregate budget (B2) accounts for it.
MAX_REPORT_REPAIRS = 2


def seed_report_template(service: PromptTemplateService):
    return service.seed_template(task_type=TASK, version=VERSION, template=TEMPLATE)


class WritingCandidateReportService:
    def __init__(self, provider: LLMProvider, *, prompt_templates: PromptTemplateService,
                 model: str | None = None, max_tokens: int = 1024):
        self.provider, self.templates = provider, prompt_templates
        self.model, self.max_tokens = model, max_tokens

    async def enrich(self, candidate: WritingCandidate,
                     package: ContextPackage) -> WritingCandidate:
        try:
            enriched, _usage = await self.enrich_metered(candidate, package)
        except MeteredCallError as exc:
            raise exc.cause from exc
        return enriched

    async def enrich_metered(self, candidate: WritingCandidate,
                             package: ContextPackage
                             ) -> tuple[WritingCandidate, TokenUsage]:
        if candidate.project_id != package.project_id:
            raise InvalidCandidateReport("candidate and context belong to different projects")
        # Both the allowlist and the prompt's pointer rendering project every
        # item, so a cross-project or invariant-violating item is rejected here,
        # before the provider is called (stable-pointer brief contracts 2/P-i).
        try:
            allowed = package_pointers(package)
        except InvalidContextPointer as exc:
            raise InvalidCandidateReport(str(exc)) from exc
        template = self.templates.get_template(task_type=TASK, version=VERSION)
        request = self._request(candidate, package, template.template)
        result = await self.provider.generate(request)
        usage = result.usage
        raw = result.content
        try:
            report = parse_report(raw, allowed_pointers=allowed)
        except ValueError as exc:
            report, error = None, exc
        # Bounded repair loop: feed the latest malformed output + its parse error
        # back for up to MAX_REPORT_REPAIRS retries before discarding the candidate.
        repairs = 0
        while report is None and repairs < MAX_REPORT_REPAIRS:
            repairs += 1
            try:
                retry = await self.provider.generate(ChatCompletionRequest(messages=(
                    ChatMessage(role="system", content=TEMPLATE),
                    ChatMessage(role="user", content=json.dumps({"invalid": raw,
                        "error": str(error)}, ensure_ascii=False))),
                    model=self.model, max_tokens=self.max_tokens, thinking=False))
            except Exception as exc:
                raise MeteredCallError(exc, usage) from exc
            usage = add_usage(usage, retry.usage)
            raw = retry.content
            try:
                report = parse_report(raw, allowed_pointers=allowed)
            except ValueError as exc:
                report, error = None, exc
        if report is None:
            cause = InvalidCandidateReport(str(error))
            raise MeteredCallError(cause, usage) from error
        return replace(candidate, **report), usage

    def _request(self, candidate, package, template):
        payload = {"candidate_text": candidate.text,
                   "context_package": format_context_package(
                       package, include_citation_numbers=True)}
        return ChatCompletionRequest(messages=(ChatMessage(role="system", content=template),
            ChatMessage(role="user", content=json.dumps(payload, ensure_ascii=False))),
            model=self.model, max_tokens=self.max_tokens, thinking=False)


def parse_report(content: str, *,
                 allowed_pointers: tuple[ContextPointer, ...] = ()) -> dict[str, object]:
    """Strict parse. ``allowed_pointers`` is the current package's pointer set
    (D2=A) **in the order the prompt numbered the items** (macro then micro): a
    claim cites an item by its 1-based number and the number→pointer mapping
    happens here, on the server (K-6=R-e). A number the request did not show fails
    closed — the default empty allowlist admits ``[]`` claims only.
    """
    # 순서가 의미다 — 번호가 곧 이 tuple의 위치이므로 set으로 바꾸면 매핑이 사라진다.
    allowed = tuple(allowed_pointers)
    root = json.loads(strip_code_fence(content))
    if not isinstance(root, Mapping) or set(root) != {"self_reported_constraints",
            "candidate_claims", "new_memory_hints", "risk_notes"}:
        raise ValueError("candidate report fields do not match schema")
    constraints = tuple(_string(x) for x in _list(root["self_reported_constraints"]))
    claims = tuple(_claim(x, allowed) for x in _list(root["candidate_claims"]))
    hints = tuple(_hint(x) for x in _list(root["new_memory_hints"]))
    risks = tuple(_risk(x) for x in _list(root["risk_notes"]))
    return dict(self_reported_constraints=constraints, candidate_claims=claims,
                new_memory_hints=hints, risk_notes=risks)

def _list(v):
    if not isinstance(v, list): raise ValueError("report field must be an array")
    return v
def _string(v):
    if not isinstance(v, str) or not v.strip(): raise ValueError("report string must be non-empty")
    return v
def _exact(v, keys):
    if not isinstance(v, Mapping) or set(v) != set(keys): raise ValueError("report item fields do not match schema")
def _claim(v, allowed):
    _exact(v, ("text", "type", "requires_gate_check", "related_context_pointers"))
    if not isinstance(v["requires_gate_check"], bool): raise ValueError("requires_gate_check must be boolean")
    pointers = tuple(_cited_pointer(x, allowed) for x in _list(v["related_context_pointers"]))
    if len(set(pointers)) != len(pointers): raise ValueError("claim pointers must not repeat")
    return CandidateClaim(_string(v["text"]), CandidateClaimType(v["type"]),
                          v["requires_gate_check"], pointers)
def _cited_pointer(v, allowed):
    # 번호는 **1-based**다(프롬프트가 `- [1] …`로 보여준다). 그래서 `0`은 어떤 항목도 가리키지
    # 않는다 — "없음"을 0으로 쓰는 모델은 거부되고, 0-based였다면 첫 항목이 조용히 근거로
    # 붙었을 것이다. `bool`은 `int`의 하위형이라 명시적으로 먼저 막는다(`True`는 1이다).
    if isinstance(v, bool) or not isinstance(v, int):
        raise ValueError("claim pointer must be an item number")
    if not 1 <= v <= len(allowed):
        raise ValueError("claim pointer is not an item of this context package")
    return allowed[v - 1]
def _hint(v):
    _exact(v, ("type", "text", "confidence", "should_analyze_after_save"))
    c=v["confidence"]
    if isinstance(c, bool) or not isinstance(c,(int,float)) or not math.isfinite(c) or not 0<=c<=1: raise ValueError("confidence must be finite 0..1")
    if not isinstance(v["should_analyze_after_save"], bool): raise ValueError("should_analyze_after_save must be boolean")
    return NewMemoryHint(MemoryHintType(v["type"]), _string(v["text"]), float(c), v["should_analyze_after_save"])
def _risk(v):
    _exact(v, ("type", "severity", "message"))
    return RiskNote(RiskNoteType(v["type"]), RiskSeverity(v["severity"]), _string(v["message"]))
