"""Phase 4 Slice 4.2: terminal-JSON LLM SearchPlan planner adapter.

The planner produces a SearchPlan in one Gateway `/v1/generate` turn (no
tool-call; the tool-call flat-loop planner is the §2.1 transition plan). It
strict-parses the JSON plan, repairs once on a malformed/out-of-set output,
and maps a still-invalid result to ``llm_error``. Only enum-literal validity
(need/tool membership from §1) is checked here; plan semantics
(unrequested need, disallowed tool for a need, project match) stay in
``ContextSearchService._validate_plan``.

The adapter is async because the LLM provider is async, mirroring the Phase 2A
``VersionedPromptAnalysisExtractionAdapter``. Slice 4.1's sync ``SearchPlanner``
Protocol and sync ``build_context_package`` remain the fake-injection seam;
reconciling the async planner into the service happens at the HTTP-wiring slice.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from services.application.app.context_search.models import (
    ContextNeed,
    ContextSearchRequest,
    NEED_ALLOWED_TOOLS,
    SearchPlan,
    SearchPlanStep,
    SearchTool,
)
from services.application.app.context_search.service import (
    ContextSearchErrorType,
    ContextSearchFailed,
)
from services.application.app.analysis.prompt_templates import (
    PromptTemplate,
    PromptTemplateError,
    PromptTemplateService,
)
from services.application.app.writing.json_extract import strip_code_fence
from services.llm_gateway.app.payload import ChatCompletionRequest, ChatMessage
from services.llm_gateway.app.provider import LLMProvider


CONTEXT_SEARCH_PLAN_TASK_TYPE = "context_search_plan"
CONTEXT_SEARCH_PLAN_PROMPT_VERSION = "context_search_plan_v1"
CONTEXT_SEARCH_PLAN_TEMPLATE = """You plan retrieval for a novel-writing assistant.

Return one JSON object with a top-level "steps" array.
Do not wrap the JSON in markdown fences and do not add prose.
Each step must contain exactly these fields:
- step_id: non-empty string
- need: one of the needs listed in the request
- tools: non-empty array of tool literals drawn from that need's allowed_tools
- query: string sub-query for that need

Use only the needs listed in the request and only the tool literals in
allowed_tools. Produce at least one step per requested need. If you cannot
plan, return {"steps":[]}.
"""

# The plan id is a server-controlled constant. The prompt's output contract
# has never asked the model for it; a model-emitted "plan_id" is ignored
# instead of being echoed into the API response (contract schema duplication
# audit, option A for query_planner).
DEFAULT_PLAN_ID = "context_search_plan"


class SearchPlanParseError(ValueError):
    pass


def seed_context_search_plan_template(
    prompt_templates: PromptTemplateService,
) -> PromptTemplate:
    return prompt_templates.seed_template(
        task_type=CONTEXT_SEARCH_PLAN_TASK_TYPE,
        version=CONTEXT_SEARCH_PLAN_PROMPT_VERSION,
        template=CONTEXT_SEARCH_PLAN_TEMPLATE,
    )


class TerminalJsonSearchPlanner:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        prompt_templates: PromptTemplateService,
        task_type: str = CONTEXT_SEARCH_PLAN_TASK_TYPE,
        prompt_version: str = CONTEXT_SEARCH_PLAN_PROMPT_VERSION,
        model: str | None = None,
        max_tokens: int = 1024,
    ) -> None:
        self._provider = provider
        self._prompt_templates = prompt_templates
        self._task_type = task_type
        self._prompt_version = prompt_version
        self._model = model
        self._max_tokens = max_tokens

    async def build_plan(self, request: ContextSearchRequest) -> SearchPlan:
        try:
            prompt_template = self._prompt_templates.get_template(
                task_type=self._task_type,
                version=self._prompt_version,
            )
        except PromptTemplateError as exc:
            raise ContextSearchFailed(
                ContextSearchErrorType.LLM_ERROR,
                f"context search plan template unavailable: {exc}",
            ) from exc

        chat_request = build_context_search_plan_request(
            request=request,
            prompt_template=prompt_template,
            model=self._model,
            max_tokens=self._max_tokens,
        )
        result = await self._provider.generate(chat_request)
        try:
            return parse_search_plan(result.content, request.project_id)
        except SearchPlanParseError as first_error:
            repair = await self._provider.generate(
                _repair_request(
                    original_request=chat_request,
                    invalid_content=result.content,
                    parser_error=str(first_error),
                )
            )
            try:
                return parse_search_plan(repair.content, request.project_id)
            except SearchPlanParseError as second_error:
                raise ContextSearchFailed(
                    ContextSearchErrorType.LLM_ERROR,
                    f"planner produced an invalid SearchPlan: {second_error}",
                ) from second_error


def build_context_search_plan_request(
    *,
    request: ContextSearchRequest,
    prompt_template: PromptTemplate,
    model: str | None = None,
    max_tokens: int = 1024,
) -> ChatCompletionRequest:
    user_payload = {
        "task_type": prompt_template.task_type,
        "prompt_version": prompt_template.version,
        "project_id": request.project_id,
        "purpose": request.purpose.value,
        "query": request.query,
        "has_current_position": request.current_position is not None,
        "needs": [
            {
                "need": need.value,
                "allowed_tools": [
                    tool.value for tool in NEED_ALLOWED_TOOLS[need]
                ],
            }
            for need in request.needs
        ],
        "tool_literals": [tool.value for tool in SearchTool],
        "output_contract": {
            "type": "json_object",
            "top_level_key": "steps",
            "empty_result": {"steps": []},
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


def parse_search_plan(content: str, project_id: str) -> SearchPlan:
    root = _json_object(content)
    raw_steps = root.get("steps")
    if not isinstance(raw_steps, list):
        raise SearchPlanParseError("steps must be an array")
    steps = tuple(_plan_step(item) for item in raw_steps)
    return SearchPlan(
        plan_id=DEFAULT_PLAN_ID, project_id=project_id, steps=steps
    )


def _plan_step(item: object) -> SearchPlanStep:
    if not isinstance(item, Mapping):
        raise SearchPlanParseError("plan step must be an object")
    if set(item.keys()) != {"step_id", "need", "tools", "query"}:
        raise SearchPlanParseError("plan step fields do not match schema")
    step_id = _non_empty_string(item["step_id"], "step_id")
    need = _need(item["need"])
    tools = _tools(item["tools"])
    query = _string(item["query"], "query")
    return SearchPlanStep(step_id=step_id, need=need, tools=tools, query=query)


def _need(value: object) -> ContextNeed:
    try:
        return ContextNeed(value)
    except ValueError as exc:
        raise SearchPlanParseError(f"unknown need literal: {value!r}") from exc


def _tools(value: object) -> tuple[SearchTool, ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or not value
    ):
        raise SearchPlanParseError("tools must be a non-empty array")
    tools: list[SearchTool] = []
    for raw in value:
        try:
            tools.append(SearchTool(raw))
        except ValueError as exc:
            raise SearchPlanParseError(
                f"unknown tool literal: {raw!r}"
            ) from exc
    return tuple(tools)


def _json_object(content: str) -> Mapping[str, object]:
    try:
        payload = json.loads(strip_code_fence(content))
    except json.JSONDecodeError as exc:
        raise SearchPlanParseError("planner content must be JSON") from exc
    if not isinstance(payload, Mapping):
        raise SearchPlanParseError("planner content must be a JSON object")
    return payload


def _non_empty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise SearchPlanParseError(f"{field} must be a non-empty string")
    return value


def _string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise SearchPlanParseError(f"{field} must be a string")
    return value


_REPAIR_SYSTEM_PROMPT = """Repair context search SearchPlan output.

Return valid JSON only. Do not wrap the JSON in markdown fences. Do not add prose.

The output must be one object with a top-level "steps" array.
Each step must contain exactly these fields:
- step_id: non-empty string
- need: one of the needs from the original request
- tools: non-empty array of tool literals from that need's allowed_tools
- query: string

Use only the need and tool literals supplied in the original request. If no
valid plan can be produced, return {"steps":[]}.
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
