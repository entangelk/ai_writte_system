"""Phase 5.2 Writing Gate prompt and strict terminal-JSON parser."""

from __future__ import annotations

import json
from collections.abc import Mapping

from services.application.app.analysis.prompt_templates import PromptTemplate
from services.application.app.context_search.models import ContextPackage
from services.application.app.writing.context_pointer import pointer_wire
from services.application.app.writing.json_extract import strip_code_fence
from services.application.app.writing.models import WritingCandidate, WritingRequest
from services.application.app.writing.prompt import format_context_package
from services.llm_gateway.app.payload import ChatCompletionRequest, ChatMessage


WRITING_GATE_TASK_TYPE = "writing_gate"
WRITING_GATE_PROMPT_VERSION = "writing_gate_v1"
WRITING_GATE_TEMPLATE = """You are the Writing Gate. Evaluate candidate prose against the supplied ContextPackage and original writing request.

Check only: do_not_use, POV, and continuity. Return raw JSON only (no markdown code fence, no surrounding prose) with exactly:
- decision: pass|revise|retrieve_more|needs_user_review|block
- findings: array of objects with exactly type, severity, message, evidence, recommended_decision
- checked_constraints: array of strings

Finding type is do_not_use|pov|continuity. Severity is warning|error. A finding recommendation is revise|retrieve_more|needs_user_review|block (never pass).

Decision priority is block > needs_user_review > retrieve_more > revise > pass. Use block for a hard do_not_use or explicit POV violation; needs_user_review for genuine ambiguity or conflicting context; retrieve_more when canonical evidence is insufficient; revise for a repairable continuity problem; pass only with no findings. Every finding must quote a short exact excerpt from the candidate in evidence, including retrieve_more findings; choose the candidate span whose claim cannot be verified from the supplied context.

Do not rewrite prose, search, save, or execute the recommendation."""


def build_writing_gate_request(*, request: WritingRequest,
                               candidate: WritingCandidate,
                               package: ContextPackage,
                               prompt_template: PromptTemplate,
                               model: str | None = None,
                               max_tokens: int = 1024) -> ChatCompletionRequest:
    payload = {
        "task_type": prompt_template.task_type,
        "prompt_version": prompt_template.version,
        "original_request": {
            "request_id": request.request_id,
            "task_type": request.task_type.value,
            "instruction": request.instruction,
            "draft_excerpt": request.draft_excerpt,
        },
        "candidate": {"output_type": candidate.output_type.value,
                      "text": candidate.text,
                      "self_reported_constraints": list(candidate.self_reported_constraints),
                      # The Gate reads the claim's pointers as evidence of what
                      # the claim was grounded in (D5=B consumption boundary);
                      # its own decision schema is unchanged.
                      "candidate_claims": [{"text": x.text,
                          "type": x.claim_type.value,
                          "requires_gate_check": x.requires_gate_check,
                          "related_context_pointers": [
                              pointer_wire(p) for p in x.related_context_pointers]}
                          for x in candidate.candidate_claims],
                      "new_memory_hints": [{"type": x.hint_type.value,
                          "text": x.text, "confidence": x.confidence,
                          "should_analyze_after_save": x.should_analyze_after_save}
                          for x in candidate.new_memory_hints],
                      "risk_notes": [{"type": x.risk_type.value,
                          "severity": x.severity.value, "message": x.message}
                          for x in candidate.risk_notes]},
        "context_package": format_context_package(package),
    }
    return ChatCompletionRequest(
        messages=(ChatMessage(role="system", content=prompt_template.template),
                  ChatMessage(role="user", content=json.dumps(
                      payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")))),
        model=model, max_tokens=max_tokens, thinking=False,
    )


# A fenced Gate JSON object is unwrapped via the shared strip_code_fence
# extraction (see writing/json_extract.py) before parsing; the strict
# schema/enum/priority/evidence checks then apply unchanged.


def json_object(content: str) -> Mapping[str, object]:
    try:
        value = json.loads(strip_code_fence(content))
    except json.JSONDecodeError as exc:
        raise ValueError("writing gate content must be JSON") from exc
    if not isinstance(value, Mapping):
        raise ValueError("writing gate content must be a JSON object")
    return value
