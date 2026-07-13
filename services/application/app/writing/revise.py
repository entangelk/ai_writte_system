"""Server-controlled partial revision from one exact Gate evidence anchor."""

from __future__ import annotations

import json
from dataclasses import replace

from services.application.app.analysis.prompt_templates import (
    PromptTemplate,
    PromptTemplateError,
    PromptTemplateService,
)
from services.application.app.context_search.models import ContextPackage
from services.application.app.writing.models import (
    WritingCandidate,
    WritingGateDecision,
    WritingGateFinding,
    WritingGateFindingType,
)
from services.application.app.writing.metering import MeteredCallError
from services.application.app.writing.prompt import format_context_package
from services.llm_gateway.app.payload import ChatCompletionRequest, ChatMessage
from services.llm_gateway.app.provider import LLMProvider, TokenUsage


TASK = "writing_partial_revise"
VERSION = "writing_partial_revise_v1"
TEMPLATE = """Revise only the supplied evidence fragment to fix the continuity finding.
Return only the replacement prose fragment: no JSON, Markdown, quotes, explanation, prefix, or suffix.
Preserve the surrounding candidate meaning and do not introduce unsupported facts.
Anchor validation, offsets, and splicing are performed by the Application server."""


class WritingRevisionError(ValueError):
    pass


class InvalidWritingRevision(RuntimeError):
    pass


class UnchangedWritingRevision(InvalidWritingRevision):
    """A valid replacement request produced the exact anchored evidence again."""


def seed_writing_revise_template(
    service: PromptTemplateService,
) -> PromptTemplate:
    return service.seed_template(task_type=TASK, version=VERSION, template=TEMPLATE)


class WritingRevisionService:
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

    async def revise(
        self,
        *,
        candidate: WritingCandidate,
        finding: WritingGateFinding,
        instruction: str,
        package: ContextPackage,
    ) -> WritingCandidate:
        try:
            revised, _usage = await self.revise_metered(
                candidate=candidate, finding=finding,
                instruction=instruction, package=package,
            )
        except MeteredCallError as exc:
            raise exc.cause from exc
        return revised

    async def revise_metered(
        self,
        *,
        candidate: WritingCandidate,
        finding: WritingGateFinding,
        instruction: str,
        package: ContextPackage,
    ) -> tuple[WritingCandidate, TokenUsage]:
        self.validate_inputs(candidate, finding, instruction)
        if candidate.project_id != package.project_id:
            raise WritingRevisionError("candidate and context belong to different projects")
        try:
            template = self._templates.get_template(task_type=TASK, version=VERSION)
        except PromptTemplateError as exc:
            raise WritingRevisionError(
                f"writing revise template unavailable: {exc}"
            ) from exc
        result = await self._provider.generate(
            ChatCompletionRequest(
                messages=(
                    ChatMessage(role="system", content=template.template),
                    ChatMessage(
                        role="user",
                        content=json.dumps(
                            {
                                "instruction": instruction,
                                "candidate_text": candidate.text,
                                "finding": {
                                    "type": finding.finding_type.value,
                                    "severity": finding.severity.value,
                                    "message": finding.message,
                                    "evidence": finding.evidence,
                                    "recommended_decision": (
                                        finding.recommended_decision.value
                                    ),
                                },
                                "context_package": format_context_package(package),
                            },
                            ensure_ascii=False,
                        ),
                    ),
                ),
                model=self._model,
                max_tokens=self._max_tokens,
                thinking=False,
            )
        )
        try:
            replacement = _replacement_text(result.content)
        except Exception as exc:
            raise MeteredCallError(exc, result.usage) from exc
        if not replacement:
            cause = InvalidWritingRevision("replacement must not be empty")
            raise MeteredCallError(cause, result.usage)
        if replacement == finding.evidence:
            cause = UnchangedWritingRevision(
                "replacement did not change the evidence"
            )
            raise MeteredCallError(cause, result.usage)
        start = candidate.text.index(finding.evidence)
        end = start + len(finding.evidence)
        revised = replace(
            candidate,
            text=candidate.text[:start] + replacement + candidate.text[end:],
            self_reported_constraints=(),
            candidate_claims=(),
            new_memory_hints=(),
            risk_notes=(),
            candidate_id=None,
            generated_by_model=result.model,
        )
        return revised, result.usage

    @staticmethod
    def validate_inputs(
        candidate: WritingCandidate,
        finding: WritingGateFinding,
        instruction: str,
    ) -> None:
        if not instruction.strip():
            raise WritingRevisionError("instruction is required")
        if not candidate.request_id.strip() or not candidate.text.strip():
            raise WritingRevisionError("candidate identity and text are required")
        if finding.finding_type is not WritingGateFindingType.CONTINUITY:
            raise WritingRevisionError("only continuity findings can be revised")
        if finding.recommended_decision is not WritingGateDecision.REVISE:
            raise WritingRevisionError("finding must recommend revise")
        if not finding.evidence.strip():
            raise WritingRevisionError("finding evidence is required")
        if candidate.text.count(finding.evidence) != 1:
            raise WritingRevisionError(
                "finding evidence must occur exactly once in candidate text"
            )


def _replacement_text(content: str) -> str:
    replacement = content.strip()
    if replacement.startswith("```") and replacement.endswith("```"):
        inner = replacement[3:-3].strip()
        first, separator, rest = inner.partition("\n")
        if separator and first.strip().lower() in {"text", "plain", "plaintext"}:
            inner = rest.strip()
        replacement = inner
    return replacement
