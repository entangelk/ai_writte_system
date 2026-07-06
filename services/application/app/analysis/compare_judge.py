"""Phase 2B.3.2: terminal-JSON LLM compare judge adapter.

Given a matched (candidate, canonical memory) pair, the judge produces the
comparison action label in one Gateway ``/v1/generate`` turn (no tool-call). It
strict-parses the JSON result, repairs once on a malformed/out-of-set output,
and maps a still-invalid result to ``InvalidJudgeResult``. Only the matched-pair
action set (update/add_evidence/no_change/conflict) is offered — ``create`` is
deterministic (no-match only, decided by ``AnalysisCompareService``) and is
never a judge output.

Mirrors the Phase 2A ``VersionedPromptAnalysisExtractionAdapter`` and the 4.2
``TerminalJsonSearchPlanner`` (async provider, versioned prompt, single repair).
``AnalysisCompareService``'s own ``JUDGE_ACTIONS`` guard stays as a defense for
the fake-injection seam.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from services.application.app.analysis.compare import (
    CompareAction,
    InvalidJudgeResult,
    JUDGE_ACTIONS,
    JudgeResult,
)
from services.application.app.analysis.models import AnalysisCandidate
from services.application.app.analysis.prompt_templates import (
    PromptTemplate,
    PromptTemplateError,
    PromptTemplateService,
)
from services.application.app.memory.models import MemoryEntry
from services.llm_gateway.app.payload import ChatCompletionRequest, ChatMessage
from services.llm_gateway.app.provider import LLMProvider


ANALYSIS_COMPARE_TASK_TYPE = "analysis_compare"
ANALYSIS_COMPARE_PROMPT_VERSION = "analysis_compare_v1"
ANALYSIS_COMPARE_TEMPLATE = """You compare a new analysis observation against an existing canonical memory about the SAME subject.

Return one JSON object with exactly these fields:
- action: one of "update", "add_evidence", "no_change", "conflict"
- rationale: a short string explaining the choice

Do not wrap the JSON in markdown fences and do not add prose.

Action meanings (both refer to the same subject):
- update: the new observation changes or refines an attribute already recorded in the memory.
- add_evidence: the new observation corroborates the memory or adds supporting detail without changing it.
- no_change: the new observation adds nothing not already captured.
- conflict: the new observation contradicts the memory.

Never return "create" — the subject already exists.
"""


class CompareJudgeParseError(ValueError):
    pass


def seed_analysis_compare_template(
    prompt_templates: PromptTemplateService,
) -> PromptTemplate:
    return prompt_templates.seed_template(
        task_type=ANALYSIS_COMPARE_TASK_TYPE,
        version=ANALYSIS_COMPARE_PROMPT_VERSION,
        template=ANALYSIS_COMPARE_TEMPLATE,
    )


class TerminalJsonCompareJudge:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        prompt_templates: PromptTemplateService,
        task_type: str = ANALYSIS_COMPARE_TASK_TYPE,
        prompt_version: str = ANALYSIS_COMPARE_PROMPT_VERSION,
        model: str | None = None,
        max_tokens: int = 512,
    ) -> None:
        self._provider = provider
        self._prompt_templates = prompt_templates
        self._task_type = task_type
        self._prompt_version = prompt_version
        self._model = model
        self._max_tokens = max_tokens

    async def judge(
        self, *, candidate: AnalysisCandidate, memory: MemoryEntry
    ) -> JudgeResult:
        try:
            prompt_template = self._prompt_templates.get_template(
                task_type=self._task_type,
                version=self._prompt_version,
            )
        except PromptTemplateError as exc:
            raise InvalidJudgeResult(
                f"analysis compare template unavailable: {exc}"
            ) from exc

        chat_request = build_analysis_compare_request(
            candidate=candidate,
            memory=memory,
            prompt_template=prompt_template,
            model=self._model,
            max_tokens=self._max_tokens,
        )
        result = await self._provider.generate(chat_request)
        try:
            return parse_judge_result(result.content)
        except CompareJudgeParseError as first_error:
            repair = await self._provider.generate(
                _repair_request(
                    original_request=chat_request,
                    invalid_content=result.content,
                    parser_error=str(first_error),
                )
            )
            try:
                return parse_judge_result(repair.content)
            except CompareJudgeParseError as second_error:
                raise InvalidJudgeResult(
                    f"compare judge produced an invalid result: {second_error}"
                ) from second_error


def build_analysis_compare_request(
    *,
    candidate: AnalysisCandidate,
    memory: MemoryEntry,
    prompt_template: PromptTemplate,
    model: str | None = None,
    max_tokens: int = 512,
) -> ChatCompletionRequest:
    user_payload = {
        "task_type": prompt_template.task_type,
        "prompt_version": prompt_template.version,
        "candidate": {
            "memory_type": candidate.candidate_type.value,
            "payload": dict(candidate.payload),
        },
        "existing_memory": {
            "memory_type": memory.memory_type.value,
            "payload": dict(memory.payload),
            "version": memory.version,
        },
        "allowed_actions": sorted(action.value for action in JUDGE_ACTIONS),
        "output_contract": {
            "type": "json_object",
            "fields": ["action", "rationale"],
        },
    }
    return ChatCompletionRequest(
        messages=(
            ChatMessage(role="system", content=prompt_template.template),
            ChatMessage(
                role="user",
                content=json.dumps(
                    user_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        ),
        model=model,
        max_tokens=max_tokens,
        thinking=False,
    )


def parse_judge_result(content: str) -> JudgeResult:
    root = _json_object(content)
    if set(root.keys()) != {"action", "rationale"}:
        raise CompareJudgeParseError("result fields do not match schema")
    action = _action(root["action"])
    rationale = _string(root["rationale"], "rationale")
    return JudgeResult(action=action, rationale=rationale)


def _action(value: object) -> CompareAction:
    try:
        action = CompareAction(value)
    except ValueError as exc:
        raise CompareJudgeParseError(
            f"unknown action literal: {value!r}"
        ) from exc
    if action not in JUDGE_ACTIONS:
        # ``create`` is deterministic (no-match only); the judge must never
        # mint it for a matched pair.
        raise CompareJudgeParseError(
            f"{action.value} is not a matched-pair action"
        )
    return action


def _json_object(content: str) -> Mapping[str, object]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise CompareJudgeParseError("judge content must be JSON") from exc
    if not isinstance(payload, Mapping):
        raise CompareJudgeParseError("judge content must be a JSON object")
    return payload


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise CompareJudgeParseError(f"{field} must be a non-empty string")
    return value


_REPAIR_SYSTEM_PROMPT = """Repair analysis compare output.

Return valid JSON only. Do not wrap the JSON in markdown fences. Do not add prose.

The output must be one object with exactly these fields:
- action: one of "update", "add_evidence", "no_change", "conflict"
- rationale: a non-empty string

Never return "create" — the subject already exists.
"""


def _repair_request(
    *,
    original_request: ChatCompletionRequest,
    invalid_content: str,
    parser_error: str,
) -> ChatCompletionRequest:
    payload = {
        "parser_error": parser_error,
        "invalid_output": invalid_content,
        "original_user_payload": original_request.messages[-1].content,
    }
    return ChatCompletionRequest(
        messages=(
            ChatMessage(role="system", content=_REPAIR_SYSTEM_PROMPT),
            ChatMessage(
                role="user",
                content=json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        ),
        model=original_request.model,
        temperature=original_request.temperature,
        top_p=original_request.top_p,
        max_tokens=original_request.max_tokens,
        thinking=False,
        chat_template_kwargs=original_request.chat_template_kwargs,
    )
