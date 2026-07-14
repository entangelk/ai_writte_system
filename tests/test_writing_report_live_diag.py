"""Phase 5.10 Writing candidate report live diagnostics regressions.

Locks the report diagnostic's two load-bearing properties (mirror of the gate
diagnostic tests): **parity** (same model / prompt template / thinking /
max_tokens as the production report service, built through
``_build_report_service``) and **capture** (both the first and the 1-call
repair raw responses are recovered with their exact strict-parse errors,
whether the report parsed or not), with no write path reached.
"""

import asyncio
import json
import os
import unittest

from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository, PromptTemplateService,
)
from services.application.app.context_search.models import (
    ContextBudget, ContextPackage, ContextSearchPurpose, ContextSearchRequest,
)
from services.application.app.writing.models import (
    WritingCandidate, WritingGateDecision, WritingGateFinding,
    WritingGateFindingType, WritingGateSeverity, WritingOutputType,
    WritingRequest, WritingTaskType,
)
from services.application.app.writing.metering import MeteredCallError
from services.application.app.writing.report import (
    TEMPLATE as REPORT_TEMPLATE, InvalidCandidateReport,
    WritingCandidateReportService, seed_report_template,
)
from services.application.app.writing.report_live_diag import (
    INVALID_CANDIDATE_REPORT, REPORT_PARSED_OK, REPORT_PROVIDER_ERROR,
    RawCaptureProvider, UPSTREAM_ERROR, format_report_diagnosis,
    run_report_diagnosis,
)
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.provider import (
    FakeLLMProvider, GenerationResult, TokenUsage,
)

_PROJECT = "p1"
_REQUEST_ID = "wr1"
_CANDIDATE_TEXT = "아린은 문을 열었다."


def _request():
    return WritingRequest(request_id=_REQUEST_ID, project_id=_PROJECT,
                          task_type=WritingTaskType.CONTINUE_SCENE,
                          instruction="이어서 써줘")


def _candidate(text=_CANDIDATE_TEXT):
    return WritingCandidate(request_id=_REQUEST_ID, project_id=_PROJECT,
                            task_type=WritingTaskType.CONTINUE_SCENE,
                            output_type=WritingOutputType.DRAFT_PATCH, text=text)


def _package():
    return ContextPackage(project_id=_PROJECT,
                          purpose=ContextSearchPurpose.WRITING_CONTEXT,
                          macro_items=(), micro_evidence=(), constraints=(),
                          do_not_use=(), token_estimate_total=0, degraded=False)


def _finding():
    return WritingGateFinding(
        finding_type=WritingGateFindingType.CONTINUITY,
        severity=WritingGateSeverity.WARNING, message="상태가 다르다.",
        evidence="문을 열었다", recommended_decision=WritingGateDecision.REVISE,
    )


def _search_request():
    return ContextSearchRequest(
        project_id=_PROJECT, purpose=ContextSearchPurpose.WRITING_CONTEXT,
        needs=(), query="이어서 써줘", current_position=None,
        context_budget=ContextBudget(max_tokens=4096),
    )


def _report_json(*, constraints="[]", claims="[]", hints="[]", risks="[]"):
    return json.dumps({
        "self_reported_constraints": json.loads(constraints),
        "candidate_claims": json.loads(claims),
        "new_memory_hints": json.loads(hints),
        "risk_notes": json.loads(risks),
    }, ensure_ascii=False)


def _gen(content, *, model="rep", pt=10, ct=5):
    return GenerationResult(model=model, content=content, finish_reason="stop",
                            usage=TokenUsage(pt, ct))


def _report_service(capture, *, model=None, max_tokens=1024):
    templates = PromptTemplateService(InMemoryPromptTemplateRepository())
    seed_report_template(templates)
    return WritingCandidateReportService(capture, prompt_templates=templates,
                                         model=model, max_tokens=max_tokens)


class _OkContext:
    def __init__(self): self.calls = []
    async def build_context_package(self, request):
        self.calls.append("build_context_package"); return _package()


class _OkReviser:
    def __init__(self): self.calls = []
    async def revise(self, *, candidate, finding, instruction, package):
        self.calls.append("revise"); return candidate


def _drive(report_outcomes, *, reviser=None, context=None):
    fake = FakeLLMProvider(report_outcomes)
    capture = RawCaptureProvider(fake)
    reporter = _report_service(capture)
    return asyncio.run(run_report_diagnosis(
        context_search=context or _OkContext(), search_request=_search_request(),
        reviser=reviser or _OkReviser(), reporter=reporter, capture=capture,
        request=_request(), candidate=_candidate(), finding=_finding(),
    )), capture


class ReportRequestParityTest(unittest.TestCase):
    def _with_env(self, **env):
        original = os.environ.copy()
        for k, v in env.items(): os.environ[k] = v
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(original)))

    def test_production_factory_report_request_parity(self):
        # _build_report_service(capture) must yield the production report request:
        # env model/max_tokens, thinking=False, REPORT_TEMPLATE system prompt.
        self._with_env(LLM_GATEWAY_MODEL="prod-model",
                       WRITING_REPORT_MAX_TOKENS="515")
        from services.application.app.main import _build_report_service

        fake = FakeLLMProvider([_gen(_report_json())])
        capture = RawCaptureProvider(fake)
        reporter = _build_report_service(capture)
        asyncio.run(reporter.enrich_metered(_candidate(), _package()))
        request = capture.captures[0].request
        self.assertEqual(request.model, "prod-model")
        self.assertEqual(request.max_tokens, 515)
        self.assertFalse(request.thinking)
        self.assertEqual(request.messages[0].content, REPORT_TEMPLATE)

    def test_build_services_report_request_parity(self):
        self._with_env(LLM_GATEWAY_BASE_URL="http://gateway",
                       LLM_GATEWAY_MODEL="diag-model",
                       WRITING_REPORT_MAX_TOKENS="616")
        os.environ.pop("CORE_SOT_MONGO_URI", None)
        os.environ.pop("CHROMA_HOST", None)
        os.environ.pop("EMBEDDING_SERVICE_URL", None)
        from scripts.diagnose_writing_report import build_services

        services = build_services(gateway_provider=FakeLLMProvider([_gen(_report_json())]))
        self.assertEqual(services.model, "diag-model")
        self.assertEqual(services.max_tokens, 616)
        asyncio.run(services.reporter.enrich_metered(_candidate(), _package()))
        request = services.capture.captures[0].request
        self.assertEqual(request.model, "diag-model")
        self.assertEqual(request.max_tokens, 616)
        self.assertFalse(request.thinking)
        self.assertEqual(request.messages[0].content, REPORT_TEMPLATE)


class RunReportDiagnosisTest(unittest.TestCase):
    def test_first_and_repair_raw_captured_on_parse_failure(self):
        # under-strict: both attempts fail schema → invalid_candidate_report,
        # and BOTH raw outputs + their parse errors are recovered. The report
        # service only surfaces the repair error; the first is re-derived here.
        bad = _report_json(constraints='"not-an-array"')  # field not an array
        diag, _ = _drive([_gen(bad), _gen(bad)])
        self.assertEqual(diag.parse_status, INVALID_CANDIDATE_REPORT)
        self.assertEqual(diag.first_raw, bad)
        self.assertIn("must be an array", diag.first_error)
        self.assertEqual(diag.repair_raw, bad)
        self.assertIn("must be an array", diag.repair_error)
        self.assertEqual([s for s, _ in diag.stage_trace],
                         ["context", "revise", "report"])

    def test_report_strips_fence_so_fenced_valid_parses(self):
        # The report parser now strips a code fence (D2=A v1.6.85, mirroring the
        # gate): a fenced valid JSON parses on the first attempt — no repair.
        # The diagnostic surfaces the fenced raw + OK (first_error None).
        fenced = "```json\n" + _report_json() + "\n```"
        diag, capture = _drive([_gen(fenced)])
        self.assertEqual(diag.parse_status, REPORT_PARSED_OK)
        self.assertEqual(diag.first_raw, fenced)
        self.assertIsNone(diag.first_error)  # stripped → parsed
        self.assertEqual(len(capture.captures), 1)  # no repair needed

    def test_successful_parse_captures_first_raw_and_counts(self):
        diag, capture = _drive([_gen(_report_json(
            claims='[{"text":"x","type":"narrative_event","requires_gate_check":true}]',
            hints='[{"type":"event","text":"y","confidence":0.5,"should_analyze_after_save":false}]',
            risks='[{"type":"pov","severity":"low","message":"z"}]'))])
        self.assertEqual(diag.parse_status, REPORT_PARSED_OK)
        self.assertEqual(diag.claim_count, 1)
        self.assertEqual(diag.hint_count, 1)
        self.assertEqual(diag.risk_count, 1)
        self.assertIsNotNone(diag.first_raw)
        self.assertIsNone(diag.first_error)  # first parsed, no repair
        self.assertEqual(len(capture.captures), 1)  # no repair on success

    def test_success_via_repair_surfaces_first_failure_and_repair(self):
        # First attempt is schema-invalid (a field is not an array — NOT a
        # fence, so the v1.6.85 strip does not rescue it) → repair produces
        # valid JSON → report succeeds via repair. The diagnosis surfaces the
        # first failure + repair raw, not misreading the first as "parsed OK".
        bad = _report_json(constraints='"not-an-array"')
        diag, capture = _drive([_gen(bad), _gen(_report_json())])
        self.assertEqual(diag.parse_status, REPORT_PARSED_OK)
        self.assertEqual(diag.first_raw, bad)
        self.assertIsNotNone(diag.first_error)  # first failed (schema)
        self.assertIn("must be an array", diag.first_error)
        self.assertEqual(diag.repair_raw, _report_json())
        self.assertEqual(len(capture.captures), 2)  # first + repair

    def test_upstream_revise_failure_stops_before_report(self):
        class _FailReviser:
            async def revise(self, **kw): raise RuntimeError("revise broke")
        diag, _ = _drive([_gen(_report_json())], reviser=_FailReviser())
        self.assertEqual(diag.parse_status, UPSTREAM_ERROR)
        self.assertEqual(diag.upstream_stage, "revise")
        self.assertIsNone(diag.first_raw)
        self.assertEqual([s for s, _ in diag.stage_trace], ["context", "revise"])

    def test_upstream_context_failure_stops_before_report(self):
        class _FailContext:
            async def build_context_package(self, r): raise RuntimeError("no ctx")
        diag, _ = _drive([_gen(_report_json())], context=_FailContext())
        self.assertEqual(diag.parse_status, UPSTREAM_ERROR)
        self.assertEqual(diag.upstream_stage, "context")

    def test_provider_error_is_classified(self):
        # A provider fault before any result → no raw, classified separately.
        diag, _ = _drive([ProviderError(code=ProviderErrorCode.UNAVAILABLE,
                                        message="gateway 502", retryable=False)])
        self.assertEqual(diag.parse_status, REPORT_PROVIDER_ERROR)
        self.assertIsNone(diag.first_raw)

    def test_no_write_methods_are_invoked(self):
        ctx, rev = _OkContext(), _OkReviser()
        _drive([_gen(_report_json())], reviser=rev, context=ctx)
        self.assertEqual(ctx.calls, ["build_context_package"])
        self.assertEqual(rev.calls, ["revise"])


class FormatReportDiagnosisTest(unittest.TestCase):
    def test_invalid_output_carries_first_repair_and_warning(self):
        bad = _report_json(constraints='"not-an-array"')
        diag, _ = _drive([_gen(bad), _gen(bad)])
        text = format_report_diagnosis(
            diag, request_id=_REQUEST_ID, project_id=_PROJECT,
            model="m", max_tokens=1024)
        self.assertIn("SENSITIVE", text)
        self.assertIn("invalid_candidate_report", text)
        self.assertIn("first attempt", text)
        self.assertIn("repair attempt", text)
        self.assertIn("must be an array", text)
        self.assertIn("report thinking: false", text)

    def test_upstream_output_states_not_reached(self):
        class _FailReviser:
            async def revise(self, **kw): raise RuntimeError("boom")
        diag, _ = _drive([_gen(_report_json())], reviser=_FailReviser())
        text = format_report_diagnosis(
            diag, request_id=_REQUEST_ID, project_id=_PROJECT,
            model="m", max_tokens=1024)
        self.assertIn("not reached", text)
        self.assertIn("boom", text)


if __name__ == "__main__":
    unittest.main()
