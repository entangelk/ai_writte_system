"""Phase 5.10 (D1=A) Writing Gate live diagnostics regressions.

Locks the two load-bearing properties of the operator-only diagnostic:

* **Parity** — the diagnostic's Gate request is the production request: same
  ``LLM_GATEWAY_MODEL`` / ``WRITING_GATE_MAX_TOKENS`` env contract, same
  ``WRITING_GATE_TEMPLATE`` system prompt, ``thinking=False``, and the same
  ContextSearchRequest shape as the ``/writing/revise-and-gate`` endpoint. Built
  through the same ``_default_writing_gate_service`` factory so the config cannot
  drift (decision brief follow-up #2).
* **Capture** — the Gate's raw model text and the exact strict-parse error are
  recovered whether the Gate parsed or not, and the pipeline never reaches a
  write path (no Mongo / audit / API mutation).
"""

import asyncio
import json
import os
import unittest

from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository, PromptTemplateService,
)
from services.application.app.context_search.models import (
    ContextBudget, ContextPackage, ContextNeed, ContextSearchPurpose,
    ContextSearchRequest,
)
from services.application.app.writing.gate import (
    WritingGateService, seed_writing_gate_template,
)
from services.application.app.writing.gate_live_diag import (
    GATE_INVALID_RESULT, GATE_PARSED_OK, GATE_PROVIDER_ERROR,
    RawCaptureProvider, UPSTREAM_ERROR, format_diagnosis, run_gate_diagnosis,
)
from services.application.app.writing.gate_prompt import WRITING_GATE_TEMPLATE
from services.application.app.writing.models import (
    WritingCandidate, WritingGateDecision, WritingGateFinding,
    WritingGateFindingType, WritingGateSeverity, WritingOutputType,
    WritingRequest, WritingTaskType,
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


def _gate_output(decision="pass", findings=None, *, extra_field=False):
    obj = {"decision": decision, "findings": findings or [],
           "checked_constraints": ["POV 제한 시점"]}
    if extra_field:
        obj["rogue_key"] = "schema violation"
    return json.dumps(obj, ensure_ascii=False)


def _search_request():
    return ContextSearchRequest(
        project_id=_PROJECT, purpose=ContextSearchPurpose.WRITING_CONTEXT,
        needs=(ContextNeed.CURRENT_SCENE,), query="이어서 써줘",
        current_position=None, context_budget=ContextBudget(max_tokens=4096),
    )


def _gate_service(capture, *, model=None, max_tokens=1024):
    templates = PromptTemplateService(InMemoryPromptTemplateRepository())
    seed_writing_gate_template(templates)
    return WritingGateService(capture, prompt_templates=templates,
                              model=model, max_tokens=max_tokens)


class _Recording:
    """Fake collaborator that records the methods the diagnostic is allowed to
    call (all read / enrich / evaluate — never a write)."""

    def __init__(self, name, *, result=None, error=None):
        self.name = name
        self.result = result
        self.error = error
        self.calls: list[str] = []

    async def build_context_package(self, request):
        self.calls.append("build_context_package")
        if self.error:
            raise self.error
        return self.result if self.result is not None else _package()

    async def revise(self, *, candidate, finding, instruction, package):
        self.calls.append("revise")
        if self.error:
            raise self.error
        return self.result if self.result is not None else candidate

    async def enrich(self, candidate, package):
        self.calls.append("enrich")
        if self.error:
            raise self.error
        return self.result if self.result is not None else candidate


def _drive(**overrides):
    """Run the diagnostic with ok-by-default fakes; ``gate_provider`` mandatory."""
    gate_provider = overrides.pop("gate_provider")
    reviser = overrides.pop("reviser", _Recording("reviser"))
    reporter = overrides.pop("reporter", _Recording("reporter"))
    context = overrides.pop("context", _Recording("context"))
    capture = RawCaptureProvider(gate_provider)
    gate = overrides.pop("gate", _gate_service(capture))
    return asyncio.run(run_gate_diagnosis(
        context_search=context, search_request=_search_request(),
        reviser=reviser, reporter=reporter, gate=gate, capture=capture,
        request=_request(), candidate=_candidate(), finding=_finding(),
    ))


class GateRequestParityTest(unittest.TestCase):
    """The diagnostic's Gate request must equal the production Gate request."""

    def _with_env(self, **env):
        original = os.environ.copy()
        for key, value in env.items():
            os.environ[key] = value
        self.addCleanup(self._restore_env, original)

    @staticmethod
    def _restore_env(original):
        os.environ.clear()
        os.environ.update(original)

    def test_production_factory_gate_request_parity(self):
        # build_services wires the Gate through _default_writing_gate_service,
        # so its request must reflect the env contract by construction. Drive the
        # factory directly and inspect the captured request.
        self._with_env(
            LLM_GATEWAY_BASE_URL="http://gateway", LLM_GATEWAY_MODEL="prod-model",
            WRITING_GATE_MAX_TOKENS="999", CORE_SOT_MONGO_URI="",
        )
        os.environ.pop("CORE_SOT_MONGO_URI", None)
        from services.application.app.main import _default_writing_gate_service

        fake = FakeLLMProvider([GenerationResult(
            model="prod-model", content=_gate_output(), finish_reason="stop",
            usage=TokenUsage(1, 1))])
        capture = RawCaptureProvider(fake)
        gate = _default_writing_gate_service(provider=capture)
        self.assertIsNotNone(gate)
        asyncio.run(gate.evaluate_metered(
            request=_request(), candidate=_candidate(), package=_package()))
        request = capture.gate_capture().request
        self.assertEqual(request.model, "prod-model")
        self.assertEqual(request.max_tokens, 999)
        self.assertFalse(request.thinking)
        self.assertEqual(request.messages[0].content, WRITING_GATE_TEMPLATE)

    def test_build_services_gate_request_parity(self):
        # The script's build_services must route the Gate through the production
        # factory too; its captured request reflects the env contract.
        self._with_env(
            LLM_GATEWAY_BASE_URL="http://gateway", LLM_GATEWAY_MODEL="diag-model",
            WRITING_GATE_MAX_TOKENS="4242", CORE_SOT_MONGO_URI="",
        )
        os.environ.pop("CORE_SOT_MONGO_URI", None)
        os.environ.pop("CHROMA_HOST", None)
        os.environ.pop("EMBEDDING_SERVICE_URL", None)
        from scripts.diagnose_writing_gate import build_services

        fake = FakeLLMProvider([GenerationResult(
            model="diag-model", content=_gate_output(), finish_reason="stop",
            usage=TokenUsage(1, 1))])
        services = build_services(gateway_provider=fake)
        self.assertEqual(services.model, "diag-model")
        self.assertEqual(services.max_tokens, 4242)
        asyncio.run(services.gate.evaluate_metered(
            request=_request(), candidate=_candidate(), package=_package()))
        request = services.capture.gate_capture().request
        self.assertEqual(request.model, "diag-model")
        self.assertEqual(request.max_tokens, 4242)
        self.assertFalse(request.thinking)
        self.assertEqual(request.messages[0].content, WRITING_GATE_TEMPLATE)

    def test_build_search_request_matches_endpoint_shape(self):
        # The ContextSearchRequest the diagnostic builds must mirror the
        # revise-and-gate endpoint: production needs, WRITING_CONTEXT, query
        # falls back to instruction, budget mirrors the request body max_tokens.
        from services.application.app.main import _WRITING_CONTINUE_SCENE_NEEDS
        from scripts.diagnose_writing_gate import build_search_request

        request = build_search_request(
            project_id=_PROJECT, instruction="continue", query=None,
            position=None, max_tokens=4096)
        self.assertEqual(request.needs, _WRITING_CONTINUE_SCENE_NEEDS)
        self.assertEqual(request.purpose, ContextSearchPurpose.WRITING_CONTEXT)
        self.assertEqual(request.query, "continue")  # query falls back to instruction
        self.assertEqual(request.context_budget.max_tokens, 4096)

        with_query = build_search_request(
            project_id=_PROJECT, instruction="continue", query="explicit",
            position=None, max_tokens=4096)
        self.assertEqual(with_query.query, "explicit")


class RunGateDiagnosisTest(unittest.TestCase):
    def test_raw_capture_on_strict_parse_failure(self):
        # Under-strict guard: a schema violation (rogue key) must surface as
        # invalid_gate_result with the raw model text preserved. If the parser
        # were silently relaxed, this would flip to "ok" and lose the evidence.
        diag = _drive(gate_provider=FakeLLMProvider([GenerationResult(
            model="m", content=_gate_output(extra_field=True),
            finish_reason="stop", usage=TokenUsage(5, 7))]))
        self.assertEqual(diag.parse_status, GATE_INVALID_RESULT)
        self.assertIn("rogue_key", diag.raw_content)
        self.assertIsNotNone(diag.parse_detail)
        self.assertEqual(diag.gate_usage.total_tokens, 12)
        self.assertEqual(diag.gate_model, "m")

    def test_raw_capture_on_successful_parse(self):
        diag = _drive(gate_provider=FakeLLMProvider([GenerationResult(
            model="m", content=_gate_output(), finish_reason="stop",
            usage=TokenUsage(2, 3))]))
        self.assertEqual(diag.parse_status, GATE_PARSED_OK)
        self.assertEqual(diag.decision, "pass")
        self.assertEqual(diag.finding_count, 0)
        self.assertIn("decision", diag.raw_content)

    def test_stage_trace_records_pre_gate_pipeline(self):
        diag = _drive(gate_provider=FakeLLMProvider([GenerationResult(
            model="m", content=_gate_output(), finish_reason="stop",
            usage=TokenUsage(1, 1))]))
        self.assertEqual([stage for stage, _ in diag.stage_trace],
                         ["context", "revise", "report", "gate"])
        self.assertTrue(
            all(status == "ok" for _, status in diag.stage_trace))

    def test_upstream_revise_failure_stops_before_gate(self):
        diag = _drive(
            gate_provider=FakeLLMProvider([GenerationResult(
                model="m", content=_gate_output(), finish_reason="stop")]),
            reviser=_Recording("reviser", error=RuntimeError("revise broke")))
        self.assertEqual(diag.parse_status, UPSTREAM_ERROR)
        self.assertEqual(diag.upstream_stage, "revise")
        self.assertIn("revise broke", diag.upstream_detail)
        self.assertIsNone(diag.raw_content)  # Gate never ran
        self.assertEqual([stage for stage, _ in diag.stage_trace],
                         ["context", "revise"])

    def test_upstream_report_failure_stops_before_gate(self):
        diag = _drive(
            gate_provider=FakeLLMProvider([GenerationResult(
                model="m", content=_gate_output(), finish_reason="stop")]),
            reporter=_Recording("reporter", error=RuntimeError("report broke")))
        self.assertEqual(diag.parse_status, UPSTREAM_ERROR)
        self.assertEqual(diag.upstream_stage, "report")
        self.assertEqual([stage for stage, _ in diag.stage_trace],
                         ["context", "revise", "report"])

    def test_upstream_context_failure_stops_before_gate(self):
        diag = _drive(
            gate_provider=FakeLLMProvider([GenerationResult(
                model="m", content=_gate_output(), finish_reason="stop")]),
            context=_Recording("context", error=RuntimeError("no context")))
        self.assertEqual(diag.parse_status, UPSTREAM_ERROR)
        self.assertEqual(diag.upstream_stage, "context")
        self.assertEqual([stage for stage, _ in diag.stage_trace], ["context"])

    def test_gate_provider_error_is_classified(self):
        # A provider fault (not a parse failure) must surface separately, with
        # no raw content (the provider returned nothing to capture).
        provider = FakeLLMProvider([
            ProviderError(code=ProviderErrorCode.UNAVAILABLE, message="gateway 502",
                          retryable=False)])
        diag = _drive(gate_provider=provider)
        self.assertEqual(diag.parse_status, GATE_PROVIDER_ERROR)
        self.assertIsNone(diag.raw_content)
        self.assertIn("gateway 502", diag.parse_detail)

    def test_no_write_methods_are_invoked(self):
        # The diagnostic must stay read-only: only build_context_package / revise
        # / enrich / evaluate are called. A spy log diverging from that sequence
        # would mean a write path was reached.
        reviser = _Recording("reviser")
        reporter = _Recording("reporter")
        context = _Recording("context")
        _drive(
            gate_provider=FakeLLMProvider([GenerationResult(
                model="m", content=_gate_output(), finish_reason="stop")]),
            reviser=reviser, reporter=reporter, context=context)
        self.assertEqual(context.calls, ["build_context_package"])
        self.assertEqual(reviser.calls, ["revise"])
        self.assertEqual(reporter.calls, ["enrich"])


class FormatDiagnosisTest(unittest.TestCase):
    def test_invalid_output_carries_raw_and_sensitive_warning(self):
        diag = _drive(gate_provider=FakeLLMProvider([GenerationResult(
            model="m", content=_gate_output(extra_field=True),
            finish_reason="stop", usage=TokenUsage(1, 1))]))
        text = format_diagnosis(
            diag, request_id=_REQUEST_ID, project_id=_PROJECT,
            model="m", max_tokens=999)
        self.assertIn("SENSITIVE", text)
        self.assertIn("invalid_gate_result", text)
        self.assertIn("rogue_key", text)  # raw content present
        self.assertIn("prompt_tokens=1", text)
        self.assertIn("gate thinking: false", text)

    def test_upstream_output_states_gate_not_reached(self):
        diag = _drive(
            gate_provider=FakeLLMProvider([GenerationResult(
                model="m", content=_gate_output(), finish_reason="stop")]),
            reviser=_Recording("reviser", error=RuntimeError("boom")))
        text = format_diagnosis(
            diag, request_id=_REQUEST_ID, project_id=_PROJECT,
            model="m", max_tokens=999)
        self.assertIn("not reached", text)
        self.assertIn("revise", text)
        self.assertIn("boom", text)


if __name__ == "__main__":
    unittest.main()
