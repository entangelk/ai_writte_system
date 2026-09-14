"""Phase 5.1 Writing generation service (generation-only slice).

One Gateway ``/v1/generate`` turn produces the scene continuation as plain prose
(owner Q2); the service wraps it into a ``WritingCandidate``. Mirrors the 1-turn
provider pattern of ``analysis/compare_judge.py`` but needs no JSON parse/repair
because the output is prose, not structured JSON.

Deterministic safety in this slice is limited to what generation can enforce
without an LLM: project isolation, task-type, a non-empty instruction (owner
D6), and a non-empty provider result (the prose path's empty-output guard — the
gate/revise/report parsers reject emptiness at their own boundaries).
do_not_use/POV *semantic* verification is the Writing Gate slice.
"""

from __future__ import annotations

from services.application.app.context_search.models import ContextPackage
from services.application.app.writing.models import (
    WRITING_CANDIDATE_STATUS,
    WritingCandidate,
    WritingOutputType,
    WritingRequest,
    WritingTaskType,
)
from services.application.app.writing.prompt import (
    WRITING_CONTINUE_SCENE_TEMPLATE,
    WRITING_PROMPT_VERSION,
    WRITING_TASK_TYPE,
    build_writing_request,
)
from services.application.app.analysis.prompt_templates import (
    PromptTemplate,
    PromptTemplateError,
    PromptTemplateService,
)
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.provider import LLMProvider
from typing import Protocol


class CandidateReporter(Protocol):
    async def enrich(self, candidate: WritingCandidate,
                     package: ContextPackage) -> WritingCandidate: ...


class WritingError(ValueError):
    """A writing request is invalid (validation), distinct from a provider fault."""


def seed_writing_template(
    prompt_templates: PromptTemplateService,
) -> PromptTemplate:
    return prompt_templates.seed_template(
        task_type=WRITING_TASK_TYPE,
        version=WRITING_PROMPT_VERSION,
        template=WRITING_CONTINUE_SCENE_TEMPLATE,
    )


class WritingService:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        prompt_templates: PromptTemplateService,
        task_type: str = WRITING_TASK_TYPE,
        prompt_version: str = WRITING_PROMPT_VERSION,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float | None = None,
        reporter: CandidateReporter | None = None,
    ) -> None:
        self._provider = provider
        self._prompt_templates = prompt_templates
        self._task_type = task_type
        self._prompt_version = prompt_version
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._reporter = reporter

    async def generate(
        self,
        *,
        request: WritingRequest,
        package: ContextPackage,
        max_output_tokens: int | None = None,
    ) -> WritingCandidate:
        # ``max_output_tokens`` is the resolved output-length preset (증분 2 D3);
        # the HTTP layer owns the preset→token mapping and passes the value here.
        # None keeps the service's construction-time default (direct callers/tests).
        self._validate(request, package)
        try:
            prompt_template = self._prompt_templates.get_template(
                task_type=self._task_type,
                version=self._prompt_version,
            )
        except PromptTemplateError as exc:
            raise WritingError(f"writing template unavailable: {exc}") from exc

        chat_request = build_writing_request(
            request=request,
            package=package,
            prompt_template=prompt_template,
            model=self._model,
            max_tokens=(
                max_output_tokens if max_output_tokens is not None
                else self._max_tokens
            ),
            temperature=self._temperature,
        )
        # A provider fault (ProviderError) is not swallowed — it propagates so the
        # HTTP layer maps it to 502 (never a success disguising a failure).
        result = await self._provider.generate(chat_request)
        if not result.content.strip():
            # 게이트웨이는 빈 content를 "정직한 신호"로 통과시킨다(닫히지 않은 thought 를
            # 지어내지 않는 계약). 그 빈 답을 거부할지는 소비자의 몫이고 gate(validate)·
            # revise(빈 replacement)·report(strict 파싱)은 이미 각자 거부한다. 이 산문
            # 경로가 유일하게 판단하지 않아 빈 후보가 scratch 저장·200 응답·job 성공으로
            # 흘렀다 — 업스트림 실패(502/PROVIDER_ERROR)로 승격한다.
            raise ProviderError(
                code=ProviderErrorCode.INVALID_RESPONSE,
                message=(
                    "provider returned an empty generation result "
                    f"(finish_reason={result.finish_reason!r})"
                ),
                retryable=False,
                provider="llm_gateway",
            )
        if result.finish_reason != "stop":
            # GAP-1 계약(B, 오너 2026-09-14): stop 외 종료는 대부분 length — 출력이
            # 상한에서 잘렸다는 뜻이다. 잘린 산문을 완성 후보로 내보내면 저장·과금이
            # 모두 "정상"으로 기록된다(조용한 헛소리). 실제 종료 사유를 메시지에 싣는다.
            raise ProviderError(
                code=ProviderErrorCode.INVALID_RESPONSE,
                message=(
                    "provider finished without completing the generation: "
                    f"finish_reason={result.finish_reason!r}"
                ),
                retryable=False,
                provider="llm_gateway",
            )
        candidate = WritingCandidate(
            request_id=request.request_id,
            project_id=request.project_id,
            task_type=request.task_type,
            output_type=WritingOutputType.DRAFT_PATCH,
            text=result.content.strip(),
            status=WRITING_CANDIDATE_STATUS,
            generated_by_model=result.model,
            # §3.1: the candidate echoes the request's exact intent/next_unit so
            # the accept boundary can bind them. Defaults keep append callers
            # unchanged.
            intent=request.intent,
            next_unit=request.next_unit,
        )
        if self._reporter is not None:
            return await self._reporter.enrich(candidate, package)
        return candidate

    @staticmethod
    def _validate(
        request: WritingRequest,
        package: ContextPackage,
    ) -> None:
        if request.task_type is not WritingTaskType.CONTINUE_SCENE:
            raise WritingError("only continue_scene is supported")
        if not request.instruction.strip():
            raise WritingError("instruction is required")
        # Project isolation (D6): the Writing AI never crosses projects. The
        # ContextPackage that grounds this generation must be the same project.
        if package.project_id != request.project_id:
            raise WritingError("context package belongs to a different project")
