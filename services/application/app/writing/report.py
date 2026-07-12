"""Strict structured report extraction for a plain-prose WritingCandidate."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import replace

from services.application.app.analysis.prompt_templates import PromptTemplateService
from services.application.app.context_search.models import ContextPackage
from services.application.app.writing.models import (
    CandidateClaim, CandidateClaimType, MemoryHintType, NewMemoryHint,
    RiskNote, RiskNoteType, RiskSeverity, WritingCandidate,
)
from services.application.app.writing.prompt import format_context_package
from services.llm_gateway.app.payload import ChatCompletionRequest, ChatMessage
from services.llm_gateway.app.provider import LLMProvider

TASK = "writing_candidate_report"
VERSION = "writing_candidate_report_v1"
TEMPLATE = """Analyze candidate prose and return JSON only with exactly self_reported_constraints, candidate_claims, new_memory_hints, risk_notes. Use the supplied enum literals. Do not invent database ids or pointers. Empty arrays are valid."""


class InvalidCandidateReport(RuntimeError): pass


def seed_report_template(service: PromptTemplateService):
    return service.seed_template(task_type=TASK, version=VERSION, template=TEMPLATE)


class WritingCandidateReportService:
    def __init__(self, provider: LLMProvider, *, prompt_templates: PromptTemplateService,
                 model: str | None = None, max_tokens: int = 1024):
        self.provider, self.templates = provider, prompt_templates
        self.model, self.max_tokens = model, max_tokens

    async def enrich(self, candidate: WritingCandidate,
                     package: ContextPackage) -> WritingCandidate:
        if candidate.project_id != package.project_id:
            raise InvalidCandidateReport("candidate and context belong to different projects")
        template = self.templates.get_template(task_type=TASK, version=VERSION)
        request = self._request(candidate, package, template.template)
        result = await self.provider.generate(request)
        try:
            report = parse_report(result.content)
        except ValueError as first:
            repair = await self.provider.generate(ChatCompletionRequest(messages=(
                ChatMessage(role="system", content=TEMPLATE),
                ChatMessage(role="user", content=json.dumps({"invalid": result.content,
                    "error": str(first)}, ensure_ascii=False))),
                model=self.model, max_tokens=self.max_tokens, thinking=False))
            try: report = parse_report(repair.content)
            except ValueError as second:
                raise InvalidCandidateReport(str(second)) from second
        return replace(candidate, **report)

    def _request(self, candidate, package, template):
        payload = {"candidate_text": candidate.text,
                   "context_package": format_context_package(package)}
        return ChatCompletionRequest(messages=(ChatMessage(role="system", content=template),
            ChatMessage(role="user", content=json.dumps(payload, ensure_ascii=False))),
            model=self.model, max_tokens=self.max_tokens, thinking=False)


def parse_report(content: str) -> dict[str, object]:
    root = json.loads(content)
    if not isinstance(root, Mapping) or set(root) != {"self_reported_constraints",
            "candidate_claims", "new_memory_hints", "risk_notes"}:
        raise ValueError("candidate report fields do not match schema")
    constraints = tuple(_string(x) for x in _list(root["self_reported_constraints"]))
    claims = tuple(_claim(x) for x in _list(root["candidate_claims"]))
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
def _claim(v):
    _exact(v, ("text", "type", "requires_gate_check"))
    if not isinstance(v["requires_gate_check"], bool): raise ValueError("requires_gate_check must be boolean")
    return CandidateClaim(_string(v["text"]), CandidateClaimType(v["type"]), v["requires_gate_check"])
def _hint(v):
    _exact(v, ("type", "text", "confidence", "should_analyze_after_save"))
    c=v["confidence"]
    if isinstance(c, bool) or not isinstance(c,(int,float)) or not math.isfinite(c) or not 0<=c<=1: raise ValueError("confidence must be finite 0..1")
    if not isinstance(v["should_analyze_after_save"], bool): raise ValueError("should_analyze_after_save must be boolean")
    return NewMemoryHint(MemoryHintType(v["type"]), _string(v["text"]), float(c), v["should_analyze_after_save"])
def _risk(v):
    _exact(v, ("type", "severity", "message"))
    return RiskNote(RiskNoteType(v["type"]), RiskSeverity(v["severity"]), _string(v["message"]))
