"""Phase 5.1 Writing generation service (generation-only slice).

One Gateway ``/v1/generate`` turn produces the scene continuation as plain prose
(owner Q2); the service wraps it into a ``WritingCandidate``. Mirrors the 1-turn
provider pattern of ``analysis/compare_judge.py`` but needs no JSON parse/repair
because the output is prose, not structured JSON.

Deterministic safety in this slice is limited to what generation can enforce
without an LLM: project isolation, task-type, and a non-empty instruction (owner
D6). do_not_use/POV *semantic* verification is the Writing Gate slice.
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
