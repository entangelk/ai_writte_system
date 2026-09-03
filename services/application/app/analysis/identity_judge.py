"""미승인 후보 정체성 그룹 Slice 2 — gateway identity judge adapter.

Slice 1이 남긴 ``IdentityJudge`` seam(후보↔후보 ``same|different|uncertain``
판정)을 Gateway ``/v1/generate`` 1-turn으로 채운다. ``TerminalJsonCompareJudge``
(2B.3.2)와 같은 모양이다 — versioned prompt, strict JSON parse,
malformed/fenced/out-of-set이면 1회 repair, 그래도 실패하면
``InvalidIdentityJudgement``(parse error 축의 seam 대응). 판정 축 세 값은
전부 judge 출력으로 허용된다(compare judge의 ``create`` 금지에 대응하는
도메인측 배제가 없다 — shortlist 규칙이 이미 비교 대상을 좁혔다).

계측: 조립점(``main.py``)이 provider를 ``LlmCallSite.IDENTITY_JUDGE``로 감싼다.
호출당 1행이고 repair 재시도는 둘째 행으로 남는다(seam C). ``correlation_id``
는 이 판정을 부르는 run endpoint의 scope(``job_id``)를 탄다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from services.application.app.analysis.identity_groups import (
    IdentityRelationVerdict,
)
from services.application.app.analysis.identity_judging import (
    IdentityJudgement,
    InvalidIdentityJudgement,
)
from services.application.app.analysis.models import AnalysisCandidate
from services.application.app.analysis.prompt_templates import (
    PromptTemplate,
    PromptTemplateError,
    PromptTemplateService,
)
from services.application.app.writing.json_extract import strip_code_fence
from services.llm_gateway.app.payload import ChatCompletionRequest, ChatMessage
from services.llm_gateway.app.provider import LLMProvider


ANALYSIS_IDENTITY_TASK_TYPE = "analysis_identity"
ANALYSIS_IDENTITY_PROMPT_VERSION = "analysis_identity_v1"
ANALYSIS_IDENTITY_TEMPLATE = """You decide whether two analysis candidates of the same type describe the same real-world identity.

Return one JSON object with exactly these fields:
- verdict: one of "same", "different", "uncertain"
- rationale: a short string explaining the choice

Do not wrap the JSON in markdown fences and do not add prose.

Verdict meanings (both candidates are observations of the same kind of thing):
- same: both candidates clearly refer to the same identity (the same character, the same event, or the same open question).
- different: the candidates clearly refer to different identities.
- uncertain: the evidence is not enough to tell them apart.
"""


class IdentityJudgeParseError(ValueError):
    pass


def seed_analysis_identity_judge_template(
    prompt_templates: PromptTemplateService,
) -> PromptTemplate:
    return prompt_templates.seed_template(
        task_type=ANALYSIS_IDENTITY_TASK_TYPE,
        version=ANALYSIS_IDENTITY_PROMPT_VERSION,
        template=ANALYSIS_IDENTITY_TEMPLATE,
    )


class TerminalJsonIdentityJudge:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        prompt_templates: PromptTemplateService,
        task_type: str = ANALYSIS_IDENTITY_TASK_TYPE,
        prompt_version: str = ANALYSIS_IDENTITY_PROMPT_VERSION,
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
        self, *, left: AnalysisCandidate, right: AnalysisCandidate
    ) -> IdentityJudgement:
        try:
            prompt_template = self._prompt_templates.get_template(
                task_type=self._task_type,
                version=self._prompt_version,
            )
        except PromptTemplateError as exc:
            raise InvalidIdentityJudgement(
                f"identity judge template unavailable: {exc}"
            ) from exc

        chat_request = build_analysis_identity_request(
            left=left,
            right=right,
            prompt_template=prompt_template,
            model=self._model,
            max_tokens=self._max_tokens,
        )
        result = await self._provider.generate(chat_request)
        try:
            return parse_identity_judgement(result.content)
        except IdentityJudgeParseError as first_error:
            repair = await self._provider.generate(
                _repair_request(
                    original_request=chat_request,
                    invalid_content=result.content,
                    parser_error=str(first_error),
                )
            )
            try:
                return parse_identity_judgement(repair.content)
            except IdentityJudgeParseError as second_error:
                raise InvalidIdentityJudgement(
                    f"identity judge produced an invalid result: {second_error}"
                ) from second_error


def build_analysis_identity_request(
    *,
    left: AnalysisCandidate,
    right: AnalysisCandidate,
    prompt_template: PromptTemplate,
    model: str | None = None,
    max_tokens: int = 512,
) -> ChatCompletionRequest:
    user_payload = {
        "task_type": prompt_template.task_type,
        "prompt_version": prompt_template.version,
        "left": {
            "memory_type": left.candidate_type.value,
            "payload": dict(left.payload),
        },
        "right": {
            "memory_type": right.candidate_type.value,
            "payload": dict(right.payload),
        },
        "allowed_verdicts": sorted(
            verdict.value for verdict in IdentityRelationVerdict
        ),
        "output_contract": {
            "type": "json_object",
            "fields": ["verdict", "rationale"],
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


def parse_identity_judgement(content: str) -> IdentityJudgement:
    root = _json_object(content)
    if set(root.keys()) != {"verdict", "rationale"}:
        raise IdentityJudgeParseError("result fields do not match schema")
    verdict = _verdict(root["verdict"])
    rationale = _string(root["rationale"], "rationale")
    return IdentityJudgement(verdict=verdict, rationale=rationale)


def _verdict(value: object) -> IdentityRelationVerdict:
    try:
        return IdentityRelationVerdict(value)
    except ValueError as exc:
        raise IdentityJudgeParseError(
            f"unknown verdict literal: {value!r}"
        ) from exc


def _json_object(content: str) -> Mapping[str, object]:
    try:
        payload = json.loads(strip_code_fence(content))
    except json.JSONDecodeError as exc:
        raise IdentityJudgeParseError("judge content must be JSON") from exc
    if not isinstance(payload, Mapping):
        raise IdentityJudgeParseError("judge content must be a JSON object")
    return payload


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise IdentityJudgeParseError(f"{field} must be a non-empty string")
    return value


_REPAIR_SYSTEM_PROMPT = """Repair analysis identity judge output.

Return valid JSON only. Do not wrap the JSON in markdown fences. Do not add prose.

The output must be one object with exactly these fields:
- verdict: one of "same", "different", "uncertain"
- rationale: a non-empty string
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
