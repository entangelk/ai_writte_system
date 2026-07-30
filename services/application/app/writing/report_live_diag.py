"""Phase 5.10 operator-only Writing candidate report live diagnostics.

Mirror of ``gate_live_diag`` for the report stage. The B2b re-measurement
(v1.6.83) showed the gate fence fix removed ``invalid_gate_result`` 502s, but
``invalid_candidate_report`` 502s remain — the report parser
(``report.py:parse_report``) rejects the model output with "report field must
be an array" and the bodyless audit exposes neither the raw report text nor
which field/clause failed (and whether the first or the repair attempt failed).

This reproduces the production report provider request (same prompt template,
model, ``thinking=False``, ``max_tokens``) for a benchmark-dedicated
project/request, runs the loop's pre-report pipeline (context→revise→report),
and prints the raw model response(s) plus the exact strict-parse error to
stdout. The report has a 1-call repair, so BOTH the first and the repair raw
outputs are captured. Writes nothing — no Mongo, no audit, no file. Raw model
text may include sensitive candidate/context prose; keep output on the
operator terminal only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from services.application.app.context_search.models import ContextSearchRequest
from services.application.app.writing.gate_live_diag import (
    CapturedGeneration,
    RawCaptureProvider,
)
from services.application.app.writing.metering import MeteredCallError
from services.application.app.writing.context_pointer import package_pointers
from services.application.app.writing.models import (
    ContextPointer,
    WritingCandidate,
    WritingGateFinding,
    WritingRequest,
)
from services.application.app.writing.report import (
    InvalidCandidateReport,
    TEMPLATE as REPORT_TEMPLATE,
    VERSION as REPORT_VERSION,
    parse_report,
)
from services.llm_gateway.app.provider import TokenUsage

# Re-export so callers/tests can import the capture from the report diag module
# without reaching into gate_live_diag.
__all__ = [
    "CapturedGeneration", "RawCaptureProvider", "ReportDiagnosis",
    "run_report_diagnosis", "format_report_diagnosis",
    "REPORT_PARSED_OK", "INVALID_CANDIDATE_REPORT",
    "REPORT_PROVIDER_ERROR", "UPSTREAM_ERROR",
]


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
    async def enrich_metered(
        self, candidate: WritingCandidate, package: object,
    ) -> tuple[WritingCandidate, TokenUsage]: ...


REPORT_PARSED_OK = "ok"
INVALID_CANDIDATE_REPORT = "invalid_candidate_report"
REPORT_PROVIDER_ERROR = "report_provider_error"
UPSTREAM_ERROR = "upstream_error"

_CONTEXT_STAGE = "context"
_REVISE_STAGE = "revise"
_REPORT_STAGE = "report"


@dataclass(frozen=True, slots=True)
class ReportDiagnosis:
    """Outcome of one diagnostic pre-report pipeline run.

    ``first_raw``/``repair_raw`` are the report's raw model texts (first call
    and the 1-call repair) when those calls returned. ``first_error``/
    ``repair_error`` are the strict-parse errors re-derived from the captured
    raws (the report service only surfaces the repair/second error, so the
    first error is re-derived here).
    """

    parse_status: str
    stage_trace: tuple[tuple[str, str], ...] = ()
    first_raw: str | None = None
    first_error: str | None = None
    repair_raw: str | None = None
    repair_error: str | None = None
    claim_count: int | None = None
    hint_count: int | None = None
    risk_count: int | None = None
    report_usage: TokenUsage | None = None
    report_model: str | None = None
    upstream_stage: str | None = None
    upstream_detail: str | None = None


def _report_captures(capture: RawCaptureProvider) -> list[CapturedGeneration]:
    return [c for c in capture.captures if c.system == REPORT_TEMPLATE]


def _reparse_error(
    content: str | None, allowed: tuple[ContextPointer, ...]
) -> str | None:
    if content is None:
        return None
    try:
        # Same allowlist the report service used, so a pointer clause the
        # operator sees is the one production hit — not an artifact of
        # re-parsing without the package (stable-pointer brief D2=A).
        parse_report(content, allowed_pointers=allowed)
    except Exception as exc:  # noqa: BLE001 — surface the exact parse clause
        return str(exc)
    return None


async def run_report_diagnosis(
    *,
    context_search: _ContextSearch,
    search_request: ContextSearchRequest,
    reviser: _Reviser,
    reporter: _Reporter,
    capture: RawCaptureProvider,
    request: WritingRequest,
    candidate: WritingCandidate,
    finding: WritingGateFinding,
) -> ReportDiagnosis:
    """Run the loop's context→revise→report sequence with raw report capture.

    Mirrors the production ``/writing/revise-and-gate`` pre-report stages. The
    report's first and (if attempted) repair raw responses are recovered from
    ``capture`` (the report's own provider), so the exact strict-validation
    clause is observable for both attempts.
    """
    stages: list[tuple[str, str]] = []

    try:
        package = await context_search.build_context_package(search_request)
    except Exception as exc:  # noqa: BLE001
        stages.append((_CONTEXT_STAGE, "failed"))
        return ReportDiagnosis(
            parse_status=UPSTREAM_ERROR, stage_trace=tuple(stages),
            upstream_stage=_CONTEXT_STAGE, upstream_detail=str(exc),
        )
    stages.append((_CONTEXT_STAGE, "ok"))

    try:
        revised = await reviser.revise(
            candidate=candidate, finding=finding,
            instruction=request.instruction, package=package,
        )
    except Exception as exc:  # noqa: BLE001
        stages.append((_REVISE_STAGE, "failed"))
        return ReportDiagnosis(
            parse_status=UPSTREAM_ERROR, stage_trace=tuple(stages),
            upstream_stage=_REVISE_STAGE, upstream_detail=str(exc),
        )
    stages.append((_REVISE_STAGE, "ok"))

    # Report (side-effect free). enrich_metered raises MeteredCallError on a
    # strict-parse failure of BOTH the first and the repair attempt
    # (cause InvalidCandidateReport), or propagates a provider fault directly.
    try:
        enriched, usage = await reporter.enrich_metered(revised, package)
    except MeteredCallError as exc:
        cause = exc.cause
        stages.append((_REPORT_STAGE, "failed"))
        caps = _report_captures(capture)
        first = caps[0] if len(caps) >= 1 else None
        # The report now retries up to MAX_REPORT_REPAIRS times; surface the
        # FINAL repair raw (the one whose error is the reported cause).
        repair = caps[-1] if len(caps) >= 2 else None
        parse_status = (
            INVALID_CANDIDATE_REPORT
            if isinstance(cause, InvalidCandidateReport)
            else REPORT_PROVIDER_ERROR
        )
        return ReportDiagnosis(
            parse_status=parse_status, stage_trace=tuple(stages),
            first_raw=first.result.content if first is not None else None,
            first_error=_reparse_error(
                first.result.content if first else None, package_pointers(package)),
            repair_raw=repair.result.content if repair is not None else None,
            repair_error=str(cause),
            report_usage=exc.usage,
            report_model=first.result.model if first is not None else None,
        )
    except Exception as exc:  # noqa: BLE001 — provider fault before a result
        stages.append((_REPORT_STAGE, "failed"))
        return ReportDiagnosis(
            parse_status=REPORT_PROVIDER_ERROR, stage_trace=tuple(stages),
            first_raw=None, repair_error=str(exc),
        )
    stages.append((_REPORT_STAGE, "ok"))

    # On success the report may still have used its 1-call repair (first attempt
    # failed, e.g. a fenced output, and the repair parsed). Two captures ⇒ the
    # first failed and the repair succeeded; surface both so the operator sees
    # the first failure rather than misreading a fenced first raw as "parsed OK".
    caps = _report_captures(capture)
    first = caps[0] if caps else None
    repair = caps[-1] if len(caps) >= 2 else None
    first_content = first.result.content if first is not None else None
    return ReportDiagnosis(
        parse_status=REPORT_PARSED_OK, stage_trace=tuple(stages),
        first_raw=first_content,
        first_error=_reparse_error(first_content, package_pointers(package)),
        repair_raw=repair.result.content if repair is not None else None,
        claim_count=len(enriched.candidate_claims),
        hint_count=len(enriched.new_memory_hints),
        risk_count=len(enriched.risk_notes),
        report_usage=usage,
        report_model=first.result.model if first is not None else None,
    )


def format_report_diagnosis(
    diagnosis: ReportDiagnosis, *,
    request_id: str, project_id: str,
    model: str | None, max_tokens: int | None,
    # 리터럴 사본을 두면 버전을 올릴 때 진단이 조용히 옛 버전을 보고한다
    # (실측 2026-07-30: v2로 올린 뒤에도 "…_v1"을 출력했다).
    prompt_version: str = REPORT_VERSION,
) -> str:
    """Render a report diagnosis as operator-terminal text (stdout only)."""
    lines: list[str] = [
        "Writing candidate report live diagnostic",
        "=========================================",
        "(SENSITIVE: raw output may include candidate/context text. Keep this on",
        " the operator terminal only — do not paste into work logs or fixtures.)",
        f"project_id: {project_id}",
        f"request_id: {request_id}",
        f"report model: {model if model is not None else '(unset)'}",
        f"report max_tokens: {max_tokens if max_tokens is not None else '(unset)'}",
        "report thinking: false",
        f"report prompt_version: {prompt_version}",
        "",
        "Stage trace:",
    ]
    for stage, status in diagnosis.stage_trace:
        lines.append(f"  {stage}: {status}")
    if diagnosis.upstream_stage is not None:
        lines.append("")
        lines.append(f"Stopped before report at stage: {diagnosis.upstream_stage}")
        if diagnosis.upstream_detail is not None:
            lines.append(f"  cause: {diagnosis.upstream_detail}")
        lines.append("")
        lines.append("Report provider raw response: (not reached)")
        return "\n".join(lines)

    def _block(title: str, raw: str | None, error: str | None) -> None:
        lines.append("")
        lines.append(f"{title}:")
        lines.append("-----BEGIN RAW-----")
        lines.append(raw if raw is not None else "(provider returned no content)")
        lines.append("-----END RAW-----")
        if error is not None:
            lines.append(f"  strict parse error: {error}")

    if diagnosis.parse_status == REPORT_PARSED_OK:
        lines.append("")
        if diagnosis.first_error is not None and diagnosis.repair_raw is not None:
            # First attempt failed (e.g. fenced output) and the 1-call repair
            # produced the parsed result — show both so the first failure is
            # not misread as a successful parse of the fenced raw.
            lines.append(
                f"Strict parse: OK via repair (first attempt failed; "
                f"claims={diagnosis.claim_count}, hints={diagnosis.hint_count}, "
                f"risks={diagnosis.risk_count})"
            )
            _block("Report provider raw response (first attempt — failed)",
                   diagnosis.first_raw, diagnosis.first_error)
            _block("Report provider raw response (repair attempt — succeeded)",
                   diagnosis.repair_raw, None)
        else:
            lines.append(
                f"Strict parse: OK (claims={diagnosis.claim_count}, "
                f"hints={diagnosis.hint_count}, risks={diagnosis.risk_count})"
            )
            _block("Report provider raw response (first)", diagnosis.first_raw, None)
    elif diagnosis.parse_status == INVALID_CANDIDATE_REPORT:
        lines.append("")
        lines.append("Strict parse: INVALID — invalid_candidate_report")
        _block("Report provider raw response (first attempt)",
               diagnosis.first_raw, diagnosis.first_error)
        if diagnosis.repair_raw is not None:
            _block("Report provider raw response (repair attempt)",
                   diagnosis.repair_raw, diagnosis.repair_error)
        elif diagnosis.repair_error is not None:
            lines.append("")
            lines.append(f"Repair attempt error: {diagnosis.repair_error}")
    else:
        lines.append("")
        lines.append(
            f"Strict parse: REPORT PROVIDER ERROR ({diagnosis.parse_status})")
        if diagnosis.repair_error is not None:
            lines.append(f"  error: {diagnosis.repair_error}")

    usage = diagnosis.report_usage
    if usage is not None:
        lines.append("")
        lines.append(
            f"Report usage: prompt_tokens={usage.prompt_tokens} "
            f"completion_tokens={usage.completion_tokens} "
            f"total={usage.total_tokens}"
        )
    if diagnosis.report_model is not None:
        lines.append(f"Report served_by_model: {diagnosis.report_model}")
    return "\n".join(lines)
