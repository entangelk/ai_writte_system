"""Phase 5.10 (D1=A) operator-only Writing Gate live diagnostics.

Reproduces the production Gate provider request for a benchmark-dedicated
project/request — same prompt template, model, ``thinking=False`` and
``max_tokens`` as ``WritingGateService`` — and prints the raw model response
plus the exact strict-parse error to stdout. The loop's persisted audit is
bodyless (P1), so without this surface the ``invalid_gate_result`` 502 cannot
be traced to a specific JSON / enum / priority / evidence clause.

This module is the read-only orchestration core; it writes nothing — no Mongo,
no audit, no file — and holds no reference to the application wiring. The CLI
(``scripts/diagnose_writing_gate.py``) builds the production services and feeds
them in. Raw model text may include sensitive candidate/context prose; command
output must stay on the operator terminal only (decision brief follow-up #1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from services.application.app.context_search.models import ContextSearchRequest
from services.application.app.writing.gate import InvalidWritingGateResult
from services.application.app.writing.gate_prompt import WRITING_GATE_TEMPLATE
from services.application.app.writing.metering import MeteredCallError
from services.application.app.writing.models import (
    WritingCandidate,
    WritingGateFinding,
    WritingRequest,
    WritingGateResult,
)
from services.llm_gateway.app.payload import ChatCompletionRequest
from services.llm_gateway.app.provider import GenerationResult, LLMProvider, TokenUsage


@dataclass(frozen=True, slots=True)
class CapturedGeneration:
    """One provider call observed by :class:`RawCaptureProvider`."""

    request: ChatCompletionRequest
    result: GenerationResult

    @property
    def system(self) -> str:
        return self.request.messages[0].content if self.request.messages else ""


class RawCaptureProvider:
    """Transparent ``LLMProvider`` proxy that records every generation.

    The diagnostic routes only the Gate service through this wrapper, so its
    captures are the Gate's raw responses. Each recorded call still delegates to
    the real provider unchanged, so production behaviour (incl. error mapping)
    is byte-identical — the wrapper observes, it does not alter.
    """

    def __init__(self, inner: LLMProvider) -> None:
        self._inner = inner
        self.captures: list[CapturedGeneration] = []

    async def generate(self, request: ChatCompletionRequest) -> GenerationResult:
        result = await self._inner.generate(request)
        self.captures.append(CapturedGeneration(request=request, result=result))
        return result

    def gate_capture(self) -> CapturedGeneration | None:
        """Most recent capture whose system prompt is the Gate template."""
        for captured in reversed(self.captures):
            if captured.system == WRITING_GATE_TEMPLATE:
                return captured
        return None


class _ContextSearch(Protocol):
    async def build_context_package(
        self, request: ContextSearchRequest,
    ) -> object: ...


class _Reviser(Protocol):
    async def revise(
        self, *, candidate: WritingCandidate, finding: WritingGateFinding,
        instruction: str, package: object,
    ) -> WritingCandidate: ...


class _Reporter(Protocol):
    async def enrich(
        self, candidate: WritingCandidate, package: object,
    ) -> WritingCandidate: ...


class _Gate(Protocol):
    async def evaluate_metered(
        self, *, request: WritingRequest, candidate: WritingCandidate,
        package: object,
    ) -> tuple[WritingGateResult, TokenUsage]: ...


# Status literals surfaced in GateDiagnosis.parse_status / stage_trace.
GATE_PARSED_OK = "ok"
GATE_INVALID_RESULT = "invalid_gate_result"
GATE_PROVIDER_ERROR = "gate_provider_error"
UPSTREAM_ERROR = "upstream_error"

_CONTEXT_STAGE = "context"
_REVISE_STAGE = "revise"
_REPORT_STAGE = "report"
_GATE_STAGE = "gate"


@dataclass(frozen=True, slots=True)
class GateDiagnosis:
    """Outcome of one diagnostic pre-gate pipeline run.

    ``raw_content`` is the Gate's raw model text when the Gate provider call
    returned (success or strict-parse failure); ``None`` when the Gate was never
    reached (upstream revise/report/context failure) or the provider itself
    faulted before returning.
    """

    parse_status: str
    stage_trace: tuple[tuple[str, str], ...] = ()
    raw_content: str | None = None
    parse_detail: str | None = None
    decision: str | None = None
    finding_count: int | None = None
    gate_usage: TokenUsage | None = None
    gate_model: str | None = None
    upstream_stage: str | None = None
    upstream_detail: str | None = None


async def run_gate_diagnosis(
    *,
    context_search: _ContextSearch,
    search_request: ContextSearchRequest,
    reviser: _Reviser,
    reporter: _Reporter,
    gate: _Gate,
    capture: RawCaptureProvider,
    request: WritingRequest,
    candidate: WritingCandidate,
    finding: WritingGateFinding,
) -> GateDiagnosis:
    """Run the loop's first revise→report→Gate sequence with raw Gate capture.

    Mirrors the production ``/writing/revise-and-gate`` endpoint's pre-gate
    stages. Each stage is reported in ``stage_trace``; the Gate's raw response is
    recovered from ``capture`` (the Gate's own provider) whether it parsed or
    not, so the exact strict-validation clause is observable.
    """
    stages: list[tuple[str, str]] = []

    # Context assembly (read-only) — the same ContextSearchRequest the endpoint
    # builds. A failure here is upstream of the Gate.
    try:
        package = await context_search.build_context_package(search_request)
    except Exception as exc:  # noqa: BLE001 — surface any upstream cause verbatim
        stages.append((_CONTEXT_STAGE, "failed"))
        return GateDiagnosis(
            parse_status=UPSTREAM_ERROR, stage_trace=tuple(stages),
            upstream_stage=_CONTEXT_STAGE, upstream_detail=str(exc),
        )
    stages.append((_CONTEXT_STAGE, "ok"))

    # Revise the supplied evidence anchor (continuity revise). The reviser
    # validates inputs itself, so an invalid finding/candidate surfaces here.
    try:
        revised = await reviser.revise(
            candidate=candidate, finding=finding,
            instruction=request.instruction, package=package,
        )
    except Exception as exc:  # noqa: BLE001
        stages.append((_REVISE_STAGE, "failed"))
        return GateDiagnosis(
            parse_status=UPSTREAM_ERROR, stage_trace=tuple(stages),
            upstream_stage=_REVISE_STAGE, upstream_detail=str(exc),
        )
    stages.append((_REVISE_STAGE, "ok"))

    # Report: enrich the revised candidate with structured claims/hints/notes
    # exactly as the loop does before gating. Side-effect free.
    try:
        reported = await reporter.enrich(revised, package)
    except Exception as exc:  # noqa: BLE001
        stages.append((_REPORT_STAGE, "failed"))
        return GateDiagnosis(
            parse_status=UPSTREAM_ERROR, stage_trace=tuple(stages),
            upstream_stage=_REPORT_STAGE, upstream_detail=str(exc),
        )
    stages.append((_REPORT_STAGE, "ok"))

    # Gate (side-effect free). evaluate_metered raises MeteredCallError on a
    # strict-parse / evidence-containment failure (cause InvalidWritingGateResult)
    # or propagates a provider fault directly.
    usage: TokenUsage | None = None
    try:
        result, usage = await gate.evaluate_metered(
            request=request, candidate=reported, package=package,
        )
    except MeteredCallError as exc:
        cause = exc.cause
        stages.append((_GATE_STAGE, "failed"))
        captured = capture.gate_capture()
        parse_status = (
            GATE_INVALID_RESULT
            if isinstance(cause, InvalidWritingGateResult)
            else GATE_PROVIDER_ERROR
        )
        return GateDiagnosis(
            parse_status=parse_status, stage_trace=tuple(stages),
            raw_content=captured.result.content if captured is not None else None,
            parse_detail=str(cause),
            gate_usage=captured.result.usage if captured is not None else exc.usage,
            gate_model=captured.result.model if captured is not None else None,
        )
    except Exception as exc:  # noqa: BLE001 — provider fault before a result
        stages.append((_GATE_STAGE, "failed"))
        return GateDiagnosis(
            parse_status=GATE_PROVIDER_ERROR, stage_trace=tuple(stages),
            raw_content=None, parse_detail=str(exc),
        )
    stages.append((_GATE_STAGE, "ok"))

    captured = capture.gate_capture()
    return GateDiagnosis(
        parse_status=GATE_PARSED_OK, stage_trace=tuple(stages),
        raw_content=captured.result.content if captured is not None else None,
        decision=result.decision.value,
        finding_count=len(result.findings),
        gate_usage=usage,
        gate_model=(captured.result.model if captured is not None
                    else result.evaluated_by_model),
    )


def format_diagnosis(
    diagnosis: GateDiagnosis, *,
    request_id: str, project_id: str,
    model: str | None, max_tokens: int | None,
    prompt_version: str = "writing_gate_v2",
) -> str:
    """Render a diagnosis as operator-terminal text (stdout only).

    No structure suitable for machine parsing is emitted on purpose: this is a
    human inspection surface, and the raw block may carry sensitive prose.
    """
    lines: list[str] = [
        "Writing Gate live diagnostic",
        "============================",
        "(SENSITIVE: raw output may include candidate/context text. Keep this on",
        " the operator terminal only — do not paste into work logs or fixtures.)",
        f"project_id: {project_id}",
        f"request_id: {request_id}",
        f"gate model: {model if model is not None else '(unset)'}",
        f"gate max_tokens: {max_tokens if max_tokens is not None else '(unset)'}",
        "gate thinking: false",
        f"gate prompt_version: {prompt_version}",
        "",
        "Stage trace:",
    ]
    for stage, status in diagnosis.stage_trace:
        lines.append(f"  {stage}: {status}")
    if diagnosis.upstream_stage is not None:
        lines.append("")
        lines.append(f"Stopped before Gate at stage: {diagnosis.upstream_stage}")
        if diagnosis.upstream_detail is not None:
            lines.append(f"  cause: {diagnosis.upstream_detail}")
        lines.append("")
        lines.append("Gate provider raw response: (not reached)")
        return "\n".join(lines)

    lines.append("")
    if diagnosis.parse_status == GATE_PARSED_OK:
        lines.append(
            f"Strict parse: OK (decision={diagnosis.decision}, "
            f"findings={diagnosis.finding_count})"
        )
    elif diagnosis.parse_status == GATE_INVALID_RESULT:
        lines.append("Strict parse: INVALID — invalid_gate_result")
        if diagnosis.parse_detail is not None:
            lines.append(f"  error: {diagnosis.parse_detail}")
    else:
        lines.append(f"Strict parse: GATE PROVIDER ERROR ({diagnosis.parse_status})")
        if diagnosis.parse_detail is not None:
            lines.append(f"  error: {diagnosis.parse_detail}")

    lines.append("")
    lines.append("Gate provider raw response:")
    lines.append("-----BEGIN RAW-----")
    lines.append(diagnosis.raw_content if diagnosis.raw_content is not None
                 else "(provider returned no content)")
    lines.append("-----END RAW-----")

    usage = diagnosis.gate_usage
    if usage is not None:
        lines.append("")
        lines.append(
            f"Gate usage: prompt_tokens={usage.prompt_tokens} "
            f"completion_tokens={usage.completion_tokens} "
            f"total={usage.total_tokens}"
        )
    if diagnosis.gate_model is not None:
        lines.append(f"Gate served_by_model: {diagnosis.gate_model}")
    return "\n".join(lines)
