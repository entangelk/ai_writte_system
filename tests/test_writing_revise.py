"""Phase 5.6 exact-evidence partial revise regressions."""

import asyncio
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

import httpx

from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository,
    PromptTemplateService,
)
from services.application.app.context_search.models import (
    ContextNeed,
    ContextPackage,
    ContextSearchErrorType,
    ContextSearchPurpose,
)
from services.application.app.context_search.service import (
    ContextSearchBudgetExceeded,
    ContextSearchFailed,
    InvalidContextSearchRequest,
)
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.main import create_app
from services.application.app.writing.models import (
    CandidateClaim,
    CandidateClaimType,
    WritingCandidate,
    WritingGateDecision,
    WritingGateFinding,
    WritingGateFindingType,
    WritingGateResult,
    WritingGateSeverity,
    WritingOutputType,
    WritingRequest,
    WritingTaskType,
)
from services.application.app.writing.metering import MeteredCallError
from services.application.app.writing.revise import (
    InvalidWritingRevision,
    WritingRevisionError,
    WritingRevisionService,
    seed_writing_revise_template,
)
from services.application.app.writing.gate import (
    InvalidWritingGateResult,
    WritingGateError,
)
from services.application.app.writing.report import InvalidCandidateReport
from services.application.app.writing.revise_gate import (
    WritingLoopPolicy,
    WritingLoopStatus,
    WritingReviseGateService,
    _eligible_revision_finding,
)
from services.application.app.writing.retrieval import (
    InvalidWritingRetrievalPlan,
    WritingRetrievalPlan,
    WritingRetrievalPlannerError,
)
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.provider import GenerationResult, TokenUsage


def _package(project_id="p1"):
    return ContextPackage(
        project_id, ContextSearchPurpose.WRITING_CONTEXT, (), (), (), (), 0, False
    )


def _candidate(text="앞 문장. 잘못된 문장. 뒤 문장.", project_id="p1"):
    return WritingCandidate(
        "r1", project_id, WritingTaskType.CONTINUE_SCENE,
        WritingOutputType.DRAFT_PATCH, text,
        candidate_claims=(CandidateClaim(
            "stale", CandidateClaimType.INTERPRETATION, True
        ),),
    )


def _finding(evidence="잘못된 문장.", *, finding_type=WritingGateFindingType.CONTINUITY,
             decision=WritingGateDecision.REVISE):
    return WritingGateFinding(
        finding_type, WritingGateSeverity.WARNING, "연속성 수정", evidence, decision
    )


class _Provider:
    def __init__(self, content="고친 문장.", *, error=None):
        self.content = content
        self.error = error
        self.calls = 0
        self.last_request = None
        self.last_package = None

    async def generate(self, request):
        self.calls += 1
        self.last_request = request
        if self.error:
            raise self.error
        return GenerationResult("fake-reviser", self.content, "stop", TokenUsage(1, 1))


class _SequenceProvider(_Provider):
    def __init__(self, contents):
        super().__init__()
        self.contents = list(contents)

    async def generate(self, request):
        next_result = self.contents.pop(0)
        if isinstance(next_result, Exception):
            self.error = next_result
        else:
            self.error = None
            self.content = next_result
        return await super().generate(request)


def _service(provider):
    templates = PromptTemplateService(InMemoryPromptTemplateRepository())
    seed_writing_revise_template(templates)
    return WritingRevisionService(provider, prompt_templates=templates)


class WritingRevisionServiceTest(unittest.TestCase):
    def test_replaces_only_unique_evidence_and_clears_stale_report(self):
        provider = _Provider()
        revised = asyncio.run(_service(provider).revise(
            candidate=_candidate(), finding=_finding(), instruction="고쳐줘",
            package=_package(),
        ))
        self.assertEqual(revised.text, "앞 문장. 고친 문장. 뒤 문장.")
        self.assertEqual(revised.candidate_claims, ())
        self.assertIsNone(revised.candidate_id)
        self.assertEqual(revised.generated_by_model, "fake-reviser")
        self.assertEqual(provider.calls, 1)
        self.assertIn("replacement prose fragment", provider.last_request.messages[0].content)

    def test_revise_metered_returns_provider_usage(self):
        # Phase 5.10 ("B2"): revise_metered surfaces the provider TokenUsage so
        # the bounded loop can aggregate it (bare revise still drops it).
        provider = _Provider()
        revised, usage = asyncio.run(_service(provider).revise_metered(
            candidate=_candidate(), finding=_finding(), instruction="고쳐줘",
            package=_package(),
        ))
        self.assertEqual(revised.text, "앞 문장. 고친 문장. 뒤 문장.")
        self.assertEqual(usage.total_tokens, 2)

    def test_revise_metered_invalid_result_carries_usage(self):
        with self.assertRaises(MeteredCallError) as caught:
            asyncio.run(_service(_Provider("")).revise_metered(
                candidate=_candidate(), finding=_finding(), instruction="고쳐줘",
                package=_package(),
            ))
        self.assertIsInstance(caught.exception.cause, InvalidWritingRevision)
        self.assertEqual(caught.exception.usage.total_tokens, 2)

    def test_missing_or_duplicate_anchor_rejected_before_provider(self):
        for text in ("anchor 없음", "잘못된 문장. 그리고 잘못된 문장."):
            provider = _Provider()
            with self.subTest(text=text), self.assertRaises(WritingRevisionError):
                asyncio.run(_service(provider).revise(
                    candidate=_candidate(text), finding=_finding(),
                    instruction="고쳐줘", package=_package(),
                ))
            self.assertEqual(provider.calls, 0)

    def test_non_revise_or_non_continuity_rejected_before_provider(self):
        cases = (
            _finding(finding_type=WritingGateFindingType.POV,
                     decision=WritingGateDecision.BLOCK),
            _finding(decision=WritingGateDecision.RETRIEVE_MORE),
        )
        for finding in cases:
            provider = _Provider()
            with self.subTest(finding=finding), self.assertRaises(WritingRevisionError):
                asyncio.run(_service(provider).revise(
                    candidate=_candidate(), finding=finding,
                    instruction="고쳐줘", package=_package(),
                ))
            self.assertEqual(provider.calls, 0)

    def test_empty_and_unchanged_replacement_are_invalid_provider_results(self):
        for content in ("   ", "잘못된 문장."):
            with self.subTest(content=content), self.assertRaises(InvalidWritingRevision):
                asyncio.run(_service(_Provider(content)).revise(
                    candidate=_candidate(), finding=_finding(),
                    instruction="고쳐줘", package=_package(),
                ))

    def test_markdown_fence_is_unwrapped_by_application(self):
        revised = asyncio.run(_service(_Provider("```text\n고친 문장.\n```" )).revise(
            candidate=_candidate(), finding=_finding(), instruction="고쳐줘",
            package=_package(),
        ))
        self.assertEqual(revised.text, "앞 문장. 고친 문장. 뒤 문장.")

    def test_cross_project_rejected_before_provider(self):
        provider = _Provider()
        with self.assertRaises(WritingRevisionError):
            asyncio.run(_service(provider).revise(
                candidate=_candidate("잘못된 문장.", "p1"), finding=_finding(),
                instruction="고쳐줘", package=_package("p2"),
            ))
        self.assertEqual(provider.calls, 0)


class _Context:
    def __init__(self, package, *, error=None, error_on_call=1):
        self.package = package
        self.error = error
        self.error_on_call = error_on_call
        self.last_request = None
        self.calls = 0

    async def build_context_package(self, request):
        self.calls += 1
        self.last_request = request
        if self.error and self.calls >= self.error_on_call:
            raise self.error
        self.last_package = _package(request.project_id)
        return self.last_package


class _Client:
    def __init__(self, app):
        self.app = app

    def post(self, path, json):
        async def send():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app), base_url="http://test"
            ) as client:
                return await client.post(path, json=json)
        return asyncio.run(send())


class _NoWriteCoreSotService(CoreSotService):
    def __init__(self):
        super().__init__(InMemoryCoreSotRepository())
        self.save_calls = 0

    def save_draft(self, **kwargs):
        self.save_calls += 1
        raise AssertionError("writing/revise must not save a draft")


class _Gate:
    def __init__(self, decision=WritingGateDecision.PASS, *, error=None):
        self.decision = decision
        self.error = error
        self.calls = 0
        self.last_candidate = None
        self.last_package = None

    async def evaluate(self, *, request, candidate, package):
        self.calls += 1
        self.last_candidate = candidate
        self.last_package = package
        if self.error:
            raise self.error
        findings = (
            (WritingGateFinding(
                WritingGateFindingType.CONTINUITY,
                WritingGateSeverity.WARNING,
                "정본 근거가 부족함",
                candidate.text,
                WritingGateDecision.RETRIEVE_MORE,
            ),)
            if self.decision is WritingGateDecision.RETRIEVE_MORE else ()
        )
        return WritingGateResult(
            request.request_id, request.project_id, self.decision, findings, (),
            "fake-gate"
        )


class _SequenceGate(_Gate):
    def __init__(self, decisions):
        super().__init__()
        self.decisions = list(decisions)

    async def evaluate(self, *, request, candidate, package):
        self.decision = self.decisions.pop(0)
        return await super().evaluate(
            request=request, candidate=candidate, package=package
        )


class _LoopGate(_Gate):
    def __init__(self, decisions, *, revise_evidence="고친 문장."):
        super().__init__()
        self.decisions = list(decisions)
        self.revise_evidence = revise_evidence

    async def evaluate(self, *, request, candidate, package):
        self.calls += 1
        self.last_candidate = candidate
        self.last_package = package
        decision = self.decisions.pop(0)
        if decision is WritingGateDecision.REVISE:
            findings = (_finding(self.revise_evidence),)
        elif decision is WritingGateDecision.RETRIEVE_MORE:
            findings = (_finding(
                candidate.text, decision=WritingGateDecision.RETRIEVE_MORE
            ),)
        else:
            findings = ()
        return WritingGateResult(
            request.request_id, request.project_id, decision, findings, (),
            "fake-gate"
        )


class _RetrievalPlanner:
    def __init__(self, *, error=None):
        self.error = error
        self.calls = 0
        self.last_gate = None

    async def plan(self, *, request, candidate, gate, current_position=None):
        self.calls += 1
        self.last_gate = gate
        if self.error:
            raise self.error
        return WritingRetrievalPlan(
            query="부족한 사건 근거", needs=(ContextNeed.EVENT_CONTEXT,)
        )


class _Reporter:
    def __init__(self, *, error=None):
        self.error = error
        self.calls = 0
        self.last_candidate = None
        self.last_package = None

    async def enrich(self, candidate, package):
        self.calls += 1
        self.last_candidate = candidate
        self.last_package = package
        if self.error:
            raise self.error
        return replace(candidate, candidate_claims=(CandidateClaim(
            "fresh", CandidateClaimType.NARRATIVE_EVENT, True
        ),))


def _http(provider=None, *, context_error=None, core_service=None,
          gate_service=None, report_service=None, retrieval_planner=None,
          context_error_on_call=1, loop_policy=None, loop_audit_service=None,
          context_service=None):
    core = core_service or CoreSotService(InMemoryCoreSotRepository())
    context = context_service or _Context(
        _package(), error=context_error, error_on_call=context_error_on_call
    )
    app = create_app(
        service=core,
        context_search_service=context,
        writing_revision_service=_service(provider) if provider else None,
        writing_gate_service=gate_service,
        writing_report_service=report_service,
        writing_retrieval_planner=retrieval_planner,
        writing_loop_policy=loop_policy,
        writing_loop_audit_service=loop_audit_service,
    )
    client = _Client(app)
    project = client.post("/projects", {"name": "Novel"}).json()["id"]
    return client, project, context


def _body(**overrides):
    body = {
        "request_id": "r1", "instruction": "연속성을 고쳐줘",
        "candidate_text": "앞 문장. 잘못된 문장. 뒤 문장.",
        "finding": {"type": "continuity", "severity": "warning",
                    "message": "연속성 수정", "evidence": "잘못된 문장.",
                    "recommended_decision": "revise"},
    }
    body.update(overrides)
    return body


class WritingRevisionApiTest(unittest.TestCase):
    def test_http_revises_inline_candidate_with_server_context(self):
        client, project, context = _http(_Provider())
        response = client.post(f"/projects/{project}/writing/revise", _body(
            query="명시 검색", current_position={
                "draft_id": "d1", "version_id": "v1"
            }))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "앞 문장. 고친 문장. 뒤 문장.")
        self.assertIsNone(response.json()["candidate_id"])
        self.assertEqual(context.last_request.query, "명시 검색")
        self.assertEqual(context.last_request.current_position.version_id, "v1")

    def test_http_validation_and_unchanged_mapping(self):
        client, project, _ = _http(_Provider())
        duplicate = _body(candidate_text="잘못된 문장. 잘못된 문장.")
        self.assertEqual(client.post(
            f"/projects/{project}/writing/revise", duplicate).status_code, 400)

        client, project, _ = _http(_Provider("잘못된 문장."))
        self.assertEqual(client.post(
            f"/projects/{project}/writing/revise", _body()).status_code, 502)

    def test_http_empty_inputs_rejected_before_context_search(self):
        cases = (
            {"instruction": "   "},
            {"request_id": "   "},
            {"candidate_text": "   "},
            {"finding": {"type": "continuity", "severity": "warning",
                         "message": "연속성 수정", "evidence": "   ",
                         "recommended_decision": "revise"}},
        )
        for override in cases:
            provider = _Provider()
            client, project, context = _http(provider)
            with self.subTest(override=override):
                response = client.post(
                    f"/projects/{project}/writing/revise", _body(**override)
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(context.calls, 0)
                self.assertEqual(provider.calls, 0)

    def test_http_context_failures_keep_public_mapping(self):
        cases = (
            (ContextSearchBudgetExceeded("budget"), 504),
            (ContextSearchFailed(
                ContextSearchErrorType.LLM_ERROR, "planner failed"), 502),
        )
        for error, expected in cases:
            client, project, _ = _http(_Provider(), context_error=error)
            with self.subTest(error=type(error).__name__):
                self.assertEqual(client.post(
                    f"/projects/{project}/writing/revise", _body()).status_code,
                    expected)

    def test_http_does_not_save_draft(self):
        core = _NoWriteCoreSotService()
        client, project, _ = _http(_Provider(), core_service=core)
        response = client.post(f"/projects/{project}/writing/revise", _body())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(core.save_calls, 0)

    def test_http_provider_timeout_and_unavailable_mapping(self):
        for code, expected in ((ProviderErrorCode.TIMEOUT, 504),
                               (ProviderErrorCode.UNAVAILABLE, 502)):
            provider = _Provider(error=ProviderError(
                code=code, message="provider failed", retryable=True,
                provider="llm_gateway"))
            client, project, _ = _http(provider)
            with self.subTest(code=code):
                self.assertEqual(client.post(
                    f"/projects/{project}/writing/revise", _body()).status_code,
                    expected)

    def test_http_missing_service_and_project(self):
        client, project, _ = _http()
        self.assertEqual(client.post(
            f"/projects/{project}/writing/revise", _body()).status_code, 503)
        self.assertEqual(client.post(
            "/projects/ghost/writing/revise", _body()).status_code, 404)


class WritingReviseGateApiTest(unittest.TestCase):
    def _post(self, client, project, body=None):
        return client.post(
            f"/projects/{project}/writing/revise-and-gate", body or _body()
        )

    def test_loop_policy_accepts_tunable_caps_and_rejects_invalid_settings(self):
        """Lock exact defaults in both drift directions while allowing tuning."""
        defaults = WritingLoopPolicy()
        self.assertEqual(
            (defaults.max_revision_rounds, defaults.max_retrieval_rounds,
             defaults.max_gate_evaluations),
            (2, 1, 3),
        )
        policy = WritingLoopPolicy(
            max_revision_rounds=3, max_retrieval_rounds=2,
            max_gate_evaluations=5,
        )
        self.assertEqual(
            (policy.max_revision_rounds, policy.max_retrieval_rounds,
             policy.max_gate_evaluations),
            (3, 2, 5),
        )
        invalid = (
            {"max_revision_rounds": 0},
            {"max_retrieval_rounds": -1},
            {"max_gate_evaluations": 0},
        )
        for override in invalid:
            with self.subTest(override=override), self.assertRaises(ValueError):
                WritingLoopPolicy(**override)

    def test_composes_one_revise_and_one_gate_with_same_context(self):
        provider = _Provider()
        gate = _Gate()
        reporter = _Reporter()
        client, project, context = _http(
            provider, gate_service=gate, report_service=reporter
        )

        response = self._post(client, project)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["candidate"]["text"], "앞 문장. 고친 문장. 뒤 문장.")
        self.assertEqual(body["gate"]["decision"], "pass")
        self.assertEqual(provider.calls, 1)
        self.assertEqual(reporter.calls, 1)
        self.assertEqual(gate.calls, 1)
        self.assertIs(reporter.last_package, context.last_package)
        self.assertIs(gate.last_package, context.last_package)
        self.assertEqual(reporter.last_candidate.candidate_claims, ())
        self.assertEqual(gate.last_candidate.candidate_claims[0].text, "fresh")
        self.assertEqual(body["candidate"]["candidate_claims"][0]["text"], "fresh")

    def test_auto_revise_refreshes_report_and_reaches_pass(self):
        provider = _SequenceProvider(("고친 문장.", "다시 고친 문장."))
        gate = _LoopGate((WritingGateDecision.REVISE, WritingGateDecision.PASS))
        reporter = _Reporter()
        client, project, context = _http(
            provider, gate_service=gate, report_service=reporter,
        )

        response = self._post(client, project)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["candidate"]["text"],
                         "앞 문장. 다시 고친 문장. 뒤 문장.")
        self.assertEqual(body["gate"]["decision"], "pass")
        self.assertEqual(body["loop"], {
            "status": "pass", "revision_rounds": 2,
            "retrieval_rounds": 0, "gate_evaluations": 2,
        })
        self.assertEqual(
            [(stage["stage"], stage["ordinal"], stage["status"])
             for stage in body["stages"]],
            [("revise", 1, "completed"), ("report", 2, "completed"),
             ("gate", 3, "completed"), ("revise", 4, "completed"),
             ("report", 5, "completed"), ("gate", 6, "completed")],
        )
        self.assertTrue(all(set(stage) == {"stage", "ordinal", "status"}
                            for stage in body["stages"]))
        self.assertEqual(provider.calls, 2)
        self.assertEqual(reporter.calls, 2)
        self.assertEqual(gate.calls, 2)
        self.assertEqual(context.calls, 1)

    def test_retrieve_then_revise_uses_each_action_once_and_three_gates(self):
        provider = _SequenceProvider(("고친 문장.", "다시 고친 문장."))
        gate = _LoopGate((
            WritingGateDecision.RETRIEVE_MORE,
            WritingGateDecision.REVISE,
            WritingGateDecision.PASS,
        ))
        reporter = _Reporter()
        retrieval = _RetrievalPlanner()
        client, project, context = _http(
            provider, gate_service=gate, report_service=reporter,
            retrieval_planner=retrieval,
        )

        response = self._post(client, project)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["loop"], {
            "status": "pass", "revision_rounds": 2,
            "retrieval_rounds": 1, "gate_evaluations": 3,
        })
        self.assertEqual(
            [stage["stage"] for stage in body["stages"]],
            ["revise", "report", "gate", "retrieve_plan", "context_search",
             "merge", "gate", "revise", "report", "gate"],
        )
        self.assertEqual(context.calls, 2)
        self.assertEqual(retrieval.calls, 1)
        self.assertEqual(provider.calls, 2)
        self.assertEqual(reporter.calls, 2)
        self.assertEqual(gate.calls, 3)

    def test_revise_then_retrieve_also_reaches_pass_with_same_caps(self):
        provider = _SequenceProvider(("고친 문장.", "다시 고친 문장."))
        gate = _LoopGate((
            WritingGateDecision.REVISE,
            WritingGateDecision.RETRIEVE_MORE,
            WritingGateDecision.PASS,
        ))
        retrieval = _RetrievalPlanner()
        reporter = _Reporter()
        client, project, context = _http(
            provider, gate_service=gate, report_service=reporter,
            retrieval_planner=retrieval,
        )

        response = self._post(client, project)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["loop"], {
            "status": "pass", "revision_rounds": 2,
            "retrieval_rounds": 1, "gate_evaluations": 3,
        })
        self.assertEqual(
            [stage["stage"] for stage in body["stages"]],
            ["revise", "report", "gate", "revise", "report", "gate",
             "retrieve_plan", "context_search", "merge", "gate"],
        )
        self.assertEqual(context.calls, 2)
        self.assertEqual(retrieval.calls, 1)
        self.assertEqual(reporter.calls, 2)
        self.assertEqual(gate.calls, 3)

    def test_configurable_revision_cap_stops_before_auto_revise(self):
        gate = _LoopGate((WritingGateDecision.REVISE,))
        reporter = _Reporter()
        policy = WritingLoopPolicy(
            max_revision_rounds=1, max_retrieval_rounds=1,
            max_gate_evaluations=3,
        )
        client, project, _ = _http(
            _Provider(), gate_service=gate, report_service=reporter,
            loop_policy=policy,
        )

        response = self._post(client, project)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["loop"], {
            "status": "budget_exhausted", "revision_rounds": 1,
            "retrieval_rounds": 0, "gate_evaluations": 1,
        })
        self.assertEqual(gate.calls, 1)
        self.assertEqual(reporter.calls, 1)

    def test_default_revision_cap_stops_before_third_revise(self):
        """Allow the second revision, but never start a third at default policy."""
        provider = _SequenceProvider(("고친 문장.", "다시 고친 문장."))
        gate = _LoopGate((
            WritingGateDecision.REVISE,
            WritingGateDecision.REVISE,
        ), revise_evidence="고친 문장.")
        reporter = _Reporter()
        client, project, _ = _http(
            provider, gate_service=gate, report_service=reporter,
        )

        response = self._post(client, project)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["loop"], {
            "status": "budget_exhausted", "revision_rounds": 2,
            "retrieval_rounds": 0, "gate_evaluations": 2,
        })
        self.assertEqual(body["candidate"]["text"],
                         "앞 문장. 다시 고친 문장. 뒤 문장.")
        self.assertEqual(body["gate"]["decision"], "revise")
        self.assertEqual(provider.calls, 2)
        self.assertEqual(reporter.calls, 2)
        self.assertEqual(gate.calls, 2)

    def test_loop_caps_are_loaded_from_environment_settings(self):
        with patch.dict(os.environ, {
            "WRITING_LOOP_MAX_REVISION_ROUNDS": "1",
            "WRITING_LOOP_MAX_RETRIEVAL_ROUNDS": "0",
            "WRITING_LOOP_MAX_GATE_EVALUATIONS": "1",
        }):
            gate = _LoopGate((WritingGateDecision.REVISE,))
            client, project, _ = _http(
                _Provider(), gate_service=gate, report_service=_Reporter(),
            )
            response = self._post(client, project)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["loop"]["status"], "budget_exhausted")
        self.assertEqual(response.json()["loop"]["gate_evaluations"], 1)

    def test_auto_revise_unchanged_is_typed_no_change_not_standalone_error(self):
        provider = _SequenceProvider(("고친 문장.", "고친 문장."))
        gate = _LoopGate((WritingGateDecision.REVISE,))
        client, project, _ = _http(
            provider, gate_service=gate, report_service=_Reporter(),
        )

        response = self._post(client, project)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["loop"]["status"], "no_change")
        self.assertEqual(body["loop"]["revision_rounds"], 2)
        self.assertEqual(body["stages"][-1], {
            "stage": "revise", "ordinal": 4, "status": "no_change",
        })
        self.assertEqual(body["candidate"]["text"],
                         "앞 문장. 고친 문장. 뒤 문장.")
        self.assertEqual(body["gate"]["decision"], "revise")

        standalone, standalone_project, _ = _http(_Provider("잘못된 문장."))
        self.assertEqual(standalone.post(
            f"/projects/{standalone_project}/writing/revise", _body()
        ).status_code, 502)

    def test_auto_revise_failure_preserves_previous_candidate_gate_and_stages(self):
        provider = _SequenceProvider((
            "고친 문장.",
            ProviderError(
                code=ProviderErrorCode.UNAVAILABLE, message="auto revise down",
                retryable=True, provider="gateway",
            ),
        ))
        gate = _LoopGate((WritingGateDecision.REVISE,))
        client, project, _ = _http(
            provider, gate_service=gate, report_service=_Reporter(),
        )

        response = self._post(client, project)

        self.assertEqual(response.status_code, 502)
        body = response.json()
        self.assertEqual(body["candidate"]["text"],
                         "앞 문장. 고친 문장. 뒤 문장.")
        self.assertEqual(body["gate"]["decision"], "revise")
        self.assertEqual(body["revision_error"]["type"],
                         "provider_unavailable")
        self.assertEqual(body["loop"], {
            "status": "failed", "revision_rounds": 2,
            "retrieval_rounds": 0, "gate_evaluations": 1,
        })
        self.assertEqual(body["stages"][-1], {
            "stage": "revise", "ordinal": 4, "status": "failed",
        })

    def test_ineligible_or_human_gate_decision_never_auto_revises(self):
        cases = (
            (_LoopGate((WritingGateDecision.NEEDS_USER_REVIEW,)),
             "terminal_decision"),
            (_LoopGate((WritingGateDecision.BLOCK,)), "terminal_decision"),
            (_Gate(WritingGateDecision.REVISE), "not_eligible"),
        )
        for gate, expected_status in cases:
            provider = _Provider()
            reporter = _Reporter()
            client, project, _ = _http(
                provider, gate_service=gate, report_service=reporter,
            )
            with self.subTest(expected_status=expected_status):
                response = self._post(client, project)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["loop"]["status"],
                                 expected_status)
                self.assertEqual(provider.calls, 1)
                self.assertEqual(reporter.calls, 1)
                self.assertEqual(gate.calls, 1)

    def test_revise_eligibility_rejects_every_broader_boundary(self):
        class _FindingGate(_Gate):
            def __init__(self, findings):
                super().__init__()
                self.findings = findings

            async def evaluate(self, *, request, candidate, package):
                self.calls += 1
                return WritingGateResult(
                    request.request_id, request.project_id,
                    WritingGateDecision.REVISE, self.findings, (), "fake-gate",
                )

        # Multi-finding (D1=A/D2=A): TWO eligible continuity findings is no
        # longer ineligible — it is revised sequentially (see
        # test_multi_finding_revise_processes_sequentially). These remain
        # ineligible: empty, non-continuity, evidence absent, evidence not unique.
        invalid_findings = (
            (),
            (_finding("고친 문장.", finding_type=WritingGateFindingType.POV),),
            (_finding("존재하지 않는 문장."),),
            (_finding("문장.",),),
        )
        for findings in invalid_findings:
            provider = _Provider()
            gate = _FindingGate(findings)
            reporter = _Reporter()
            client, project, _ = _http(
                provider, gate_service=gate, report_service=reporter,
            )
            with self.subTest(findings=findings):
                response = self._post(client, project)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["loop"]["status"],
                                 "not_eligible")
                self.assertEqual(provider.calls, 1)
                self.assertEqual(reporter.calls, 1)
                self.assertEqual(gate.calls, 1)

    def test_all_gate_decisions_are_200_with_at_most_one_retrieval_round(self):
        for decision in WritingGateDecision:
            provider = _Provider()
            gate = (
                _SequenceGate((decision, decision))
                if decision is WritingGateDecision.RETRIEVE_MORE
                else _Gate(decision)
            )
            reporter = _Reporter()
            retrieval = _RetrievalPlanner()
            client, project, _ = _http(
                provider, gate_service=gate, report_service=reporter,
                retrieval_planner=retrieval,
            )
            with self.subTest(decision=decision):
                response = self._post(client, project)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["gate"]["decision"], decision.value)
                self.assertEqual(provider.calls, 1)
                self.assertEqual(reporter.calls, 1)
                expected_rounds = 2 if decision is WritingGateDecision.RETRIEVE_MORE else 1
                self.assertEqual(gate.calls, expected_rounds)
                self.assertEqual(retrieval.calls, expected_rounds - 1)

    def test_retrieve_more_merges_and_regates_without_rereport(self):
        provider = _Provider()
        gate = _SequenceGate((
            WritingGateDecision.RETRIEVE_MORE, WritingGateDecision.PASS,
        ))
        reporter = _Reporter()
        retrieval = _RetrievalPlanner()
        core = _NoWriteCoreSotService()
        client, project, context = _http(
            provider, gate_service=gate, report_service=reporter,
            retrieval_planner=retrieval, core_service=core,
        )

        response = self._post(client, project)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["gate"]["decision"], "pass")
        self.assertEqual(body["candidate"]["request_id"], "r1")
        self.assertEqual(body["candidate"]["project_id"], project)
        self.assertIsNone(body["candidate"]["candidate_id"])
        self.assertEqual(context.calls, 2)
        self.assertEqual(context.last_request.needs, (ContextNeed.EVENT_CONTEXT,))
        self.assertEqual(retrieval.calls, 1)
        self.assertEqual(reporter.calls, 1)
        self.assertEqual(gate.calls, 2)
        self.assertEqual(gate.last_candidate.candidate_claims[0].text, "fresh")
        self.assertEqual(core.save_calls, 0)

    def test_retrieval_failure_preserves_candidate_and_first_gate(self):
        retrieval = _RetrievalPlanner(error=RuntimeError("planner exploded"))
        gate = _Gate(WritingGateDecision.RETRIEVE_MORE)
        reporter = _Reporter()
        client, project, _ = _http(
            _Provider(), gate_service=gate, report_service=reporter,
            retrieval_planner=retrieval,
        )

        response = self._post(client, project)

        self.assertEqual(response.status_code, 502)
        body = response.json()
        self.assertEqual(body["candidate"]["candidate_claims"][0]["text"], "fresh")
        self.assertEqual(body["gate"]["decision"], "retrieve_more")
        self.assertEqual(body["retrieval_error"]["type"], "retrieval_error")
        self.assertEqual(gate.calls, 1)
        self.assertEqual(reporter.calls, 1)

    def test_retrieval_dependency_and_context_failures_are_partial(self):
        cases = (
            (None, None, 1, 503, "retrieval_not_configured"),
            (_RetrievalPlanner(error=ProviderError(
                code=ProviderErrorCode.TIMEOUT, message="planner timeout",
                retryable=True, provider="gateway",
            )), None, 1, 504, "provider_timeout"),
            (_RetrievalPlanner(error=ProviderError(
                code=ProviderErrorCode.UNAVAILABLE, message="planner down",
                retryable=True, provider="gateway",
            )), None, 1, 502, "provider_unavailable"),
            (_RetrievalPlanner(error=InvalidWritingRetrievalPlan(
                "invalid plan"
            )), None, 1, 502, "invalid_retrieval_plan"),
            (_RetrievalPlanner(error=WritingRetrievalPlannerError(
                "missing planner template"
            )), None, 1, 503, "retrieval_planner_error"),
            (_RetrievalPlanner(), ContextSearchFailed(
                ContextSearchErrorType.BACKEND_ERROR, "delta backend down"
            ), 2, 502, "backend_error"),
            (_RetrievalPlanner(), InvalidContextSearchRequest(
                "position required"
            ), 2, 400, "invalid_context_request"),
            (_RetrievalPlanner(), ContextSearchBudgetExceeded(
                "delta budget"
            ), 2, 504, "context_budget_exceeded"),
        )
        for planner, context_error, error_on_call, expected, error_type in cases:
            gate = _Gate(WritingGateDecision.RETRIEVE_MORE)
            reporter = _Reporter()
            client, project, _ = _http(
                _Provider(), gate_service=gate, report_service=reporter,
                retrieval_planner=planner, context_error=context_error,
                context_error_on_call=error_on_call,
            )
            with self.subTest(error_type=error_type):
                response = self._post(client, project)
                self.assertEqual(response.status_code, expected)
                body = response.json()
                self.assertEqual(body["gate"]["decision"], "retrieve_more")
                self.assertEqual(
                    body["candidate"]["candidate_claims"][0]["text"], "fresh"
                )
                self.assertEqual(body["retrieval_error"]["type"], error_type)
                self.assertEqual(gate.calls, 1)
                self.assertEqual(reporter.calls, 1)

    def test_second_gate_failure_keeps_latest_report_without_rereport(self):
        class _SecondGateFailure(_SequenceGate):
            async def evaluate(self, *, request, candidate, package):
                if self.calls == 1:
                    raise InvalidWritingGateResult("second gate invalid")
                return await super().evaluate(
                    request=request, candidate=candidate, package=package
                )

        gate = _SecondGateFailure((WritingGateDecision.RETRIEVE_MORE,))
        reporter = _Reporter()
        client, project, _ = _http(
            _Provider(), gate_service=gate, report_service=reporter,
            retrieval_planner=_RetrievalPlanner(),
        )

        response = self._post(client, project)

        self.assertEqual(response.status_code, 502)
        body = response.json()
        self.assertEqual(body["gate"]["decision"], "retrieve_more")
        self.assertEqual(body["loop"], {
            "status": "failed", "revision_rounds": 1,
            "retrieval_rounds": 1, "gate_evaluations": 2,
        })
        self.assertEqual(body["stages"][-1]["status"], "failed")
        self.assertEqual(body["gate_error"]["detail"], "second gate invalid")
        self.assertEqual(body["gate_error"]["type"], "invalid_gate_result")
        self.assertEqual(body["candidate"]["candidate_claims"][0]["text"], "fresh")
        self.assertEqual(reporter.calls, 1)

    def test_gate_failure_returns_partial_candidate(self):
        cases = (
            (ProviderError(
                code=ProviderErrorCode.TIMEOUT, message="gate timeout",
                retryable=True, provider="gateway"), 504, "provider_timeout"),
            (ProviderError(
                code=ProviderErrorCode.UNAVAILABLE, message="gate down",
                retryable=True, provider="gateway"), 502, "provider_unavailable"),
            (InvalidWritingGateResult("bad gate"), 502, "invalid_gate_result"),
            (WritingGateError("gate input failed"), 400, "writing_gate_error"),
            (RuntimeError("unexpected gate failure"), 502, "gate_error"),
        )
        for error, expected, error_type in cases:
            client, project, _ = _http(
                _Provider(), gate_service=_Gate(error=error),
                report_service=_Reporter(),
            )
            with self.subTest(error=type(error).__name__):
                response = self._post(client, project)
                self.assertEqual(response.status_code, expected)
                body = response.json()
                self.assertEqual(
                    body["candidate"]["text"], "앞 문장. 고친 문장. 뒤 문장."
                )
                self.assertEqual(
                    body["candidate"]["candidate_claims"][0]["text"], "fresh"
                )
                self.assertIsNone(body["gate"])
                self.assertEqual(body["gate_error"]["type"], error_type)

    def test_validation_failure_is_400_before_context_revise_or_gate(self):
        """Reject an invalid anchor, but keep a valid unique anchor accepted."""
        provider = _Provider()
        gate = _Gate()
        reporter = _Reporter()
        client, project, context = _http(
            provider, gate_service=gate, report_service=reporter
        )

        response = self._post(
            client, project,
            _body(candidate_text="잘못된 문장. 잘못된 문장."),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(context.calls, 0)
        self.assertEqual(provider.calls, 0)
        self.assertEqual(reporter.calls, 0)
        self.assertEqual(gate.calls, 0)

        accepted = self._post(client, project)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(context.calls, 1)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(reporter.calls, 1)
        self.assertEqual(gate.calls, 1)

    def test_revise_provider_timeout_is_504_without_calling_gate(self):
        """Preserve revise timeout mapping without wrapping it as a Gate failure."""
        provider = _Provider(error=ProviderError(
            code=ProviderErrorCode.TIMEOUT, message="revise timeout",
            retryable=True, provider="gateway",
        ))
        gate = _Gate()
        reporter = _Reporter()
        client, project, context = _http(
            provider, gate_service=gate, report_service=reporter
        )

        response = self._post(client, project)

        self.assertEqual(response.status_code, 504)
        body = response.json()
        self.assertIsNone(body["gate"])
        self.assertEqual(body["loop"], {
            "status": "failed", "revision_rounds": 1,
            "retrieval_rounds": 0, "gate_evaluations": 0,
        })
        self.assertEqual(body["stages"], [{
            "stage": "revise", "ordinal": 1, "status": "failed",
        }])
        self.assertEqual(body["revision_error"]["type"], "provider_timeout")
        self.assertEqual(context.calls, 1)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(reporter.calls, 0)
        self.assertEqual(gate.calls, 0)

    def test_revise_failure_never_calls_gate(self):
        gate = _Gate()
        reporter = _Reporter()
        client, project, _ = _http(
            _Provider("잘못된 문장."), gate_service=gate,
            report_service=reporter,
        )
        response = self._post(client, project)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(reporter.calls, 0)
        self.assertEqual(gate.calls, 0)

    def test_missing_gate_or_reviser_is_503(self):
        client, project, _ = _http(_Provider(), report_service=_Reporter())
        self.assertEqual(self._post(client, project).status_code, 503)

        client, project, _ = _http(
            gate_service=_Gate(), report_service=_Reporter()
        )
        self.assertEqual(self._post(client, project).status_code, 503)

        provider = _Provider()
        gate = _Gate()
        client, project, context = _http(provider, gate_service=gate)
        self.assertEqual(self._post(client, project).status_code, 503)
        self.assertEqual(context.calls, 0)
        self.assertEqual(provider.calls, 0)
        self.assertEqual(gate.calls, 0)

    def test_context_failures_map_without_revise_or_gate_calls(self):
        cases = (
            (ContextSearchBudgetExceeded("budget"), 504),
            (ContextSearchFailed(
                ContextSearchErrorType.BACKEND_ERROR, "backend down"), 502),
        )
        for error, expected in cases:
            provider = _Provider()
            gate = _Gate()
            reporter = _Reporter()
            client, project, _ = _http(
                provider, gate_service=gate, context_error=error,
                report_service=reporter,
            )
            with self.subTest(error=type(error).__name__):
                self.assertEqual(self._post(client, project).status_code, expected)
                self.assertEqual(provider.calls, 0)
                self.assertEqual(reporter.calls, 0)
                self.assertEqual(gate.calls, 0)

    def test_composition_does_not_save_draft(self):
        core = _NoWriteCoreSotService()
        client, project, _ = _http(
            _Provider(), gate_service=_Gate(), report_service=_Reporter(),
            core_service=core,
        )
        self.assertEqual(self._post(client, project).status_code, 200)
        self.assertEqual(core.save_calls, 0)

    def test_report_failure_returns_partial_candidate_without_calling_gate(self):
        cases = (
            (ProviderError(
                code=ProviderErrorCode.TIMEOUT, message="report timeout",
                retryable=True, provider="gateway"), 504, "provider_timeout"),
            (ProviderError(
                code=ProviderErrorCode.UNAVAILABLE, message="report down",
                retryable=True, provider="gateway"), 502, "provider_unavailable"),
            (InvalidCandidateReport("bad report"), 502,
             "invalid_candidate_report"),
            (RuntimeError("unexpected report failure"), 502, "report_error"),
        )
        for error, expected, error_type in cases:
            gate = _Gate()
            reporter = _Reporter(error=error)
            client, project, _ = _http(
                _Provider(), gate_service=gate, report_service=reporter
            )

            with self.subTest(error=type(error).__name__):
                response = self._post(client, project)
                self.assertEqual(response.status_code, expected)
                body = response.json()
                self.assertEqual(
                    body["candidate"]["text"], "앞 문장. 고친 문장. 뒤 문장."
                )
                self.assertEqual(body["candidate"]["candidate_claims"], [])
                self.assertIsNone(body["gate"])
                self.assertEqual(body["report_error"]["type"], error_type)
                self.assertEqual(reporter.calls, 1)
                self.assertEqual(gate.calls, 0)


class WritingReviseGateEnvelopeKeyTest(unittest.TestCase):
    """C0 exact-key safety net for the revise-and-gate envelopes (SoT v1.7.1).

    The success dict is validated by ``response_model=WritingReviseGateResponse``
    (a too-narrow model silently drops a field), while each partial envelope is a
    ``JSONResponse`` that bypasses ``response_model`` — so the partial key sets
    are locked HERE as their only guard. Every partial carries exactly one of the
    four ``*_error`` discriminators; this pins each one.
    """

    _COMMON = {"candidate", "gate", "loop", "stages", "audit_id", "audit_error"}

    def _post(self, client, project):
        return WritingReviseGateApiTest()._post(client, project)

    def test_success_envelope_keys_are_complete(self):
        client, project, _ = _http(
            _Provider(), gate_service=_Gate(WritingGateDecision.PASS),
            report_service=_Reporter(),
        )
        body = self._post(client, project).json()
        self.assertEqual(set(body), self._COMMON)
        self.assertEqual(set(body["loop"]), {
            "status", "revision_rounds", "retrieval_rounds", "gate_evaluations",
        })
        self.assertEqual(set(body["stages"][0]), {"stage", "ordinal", "status"})
        self.assertEqual(set(body["candidate"]), {
            "request_id", "project_id", "task_type", "output_type", "text",
            "status", "self_reported_constraints", "candidate_claims",
            "new_memory_hints", "risk_notes", "candidate_id",
            "generated_by_model",
        })

    def test_report_error_partial_envelope_keys(self):
        client, project, _ = _http(
            _Provider(), gate_service=_Gate(),
            report_service=_Reporter(error=InvalidCandidateReport("bad report")),
        )
        body = self._post(client, project).json()
        self.assertEqual(set(body), self._COMMON | {"report_error"})
        self.assertEqual(set(body["report_error"]), {"type", "detail"})

    def test_revision_error_partial_envelope_keys(self):
        provider = _SequenceProvider((
            "고친 문장.",
            ProviderError(code=ProviderErrorCode.UNAVAILABLE,
                          message="auto revise down", retryable=True,
                          provider="gateway"),
        ))
        client, project, _ = _http(
            provider, gate_service=_LoopGate((WritingGateDecision.REVISE,)),
            report_service=_Reporter(),
        )
        body = self._post(client, project).json()
        self.assertEqual(set(body), self._COMMON | {"revision_error"})
        self.assertEqual(set(body["revision_error"]), {"type", "detail"})

    def test_retrieval_error_partial_envelope_keys(self):
        client, project, _ = _http(
            _Provider(), gate_service=_Gate(WritingGateDecision.RETRIEVE_MORE),
            report_service=_Reporter(),
            retrieval_planner=_RetrievalPlanner(
                error=RuntimeError("planner exploded")),
        )
        body = self._post(client, project).json()
        self.assertEqual(set(body), self._COMMON | {"retrieval_error"})
        self.assertEqual(set(body["retrieval_error"]), {"type", "detail"})

    def test_gate_error_partial_envelope_keys(self):
        client, project, _ = _http(
            _Provider(),
            gate_service=_Gate(error=InvalidWritingGateResult("bad gate")),
            report_service=_Reporter(),
        )
        body = self._post(client, project).json()
        self.assertEqual(set(body), self._COMMON | {"gate_error"})
        self.assertEqual(set(body["gate_error"]), {"type", "detail"})


class EligibleRevisionFindingTest(unittest.TestCase):
    """Multi-finding selection (owner D1=A continuity-only, D3=A severity desc).

    Unit-locks `_eligible_revision_finding`: the loop revises one finding per
    round, so this must pick the single best-eligible continuity revise finding
    among N — no longer requiring exactly one.
    """

    @staticmethod
    def _cont(evidence, *, severity=WritingGateSeverity.WARNING,
              decision=WritingGateDecision.REVISE,
              finding_type=WritingGateFindingType.CONTINUITY):
        return WritingGateFinding(finding_type, severity, "m", evidence, decision)

    def test_none_when_no_finding_eligible(self):
        # under-strict: empty / non-continuity / evidence absent / not unique
        # still dead-end to not_eligible (unchanged from single-finding rule).
        cand = _candidate()  # "앞 문장. 잘못된 문장. 뒤 문장."
        for findings in (
            (),
            (self._cont("잘못된 문장.", finding_type=WritingGateFindingType.POV),),
            (self._cont("잘못된 문장.",
                        finding_type=WritingGateFindingType.DO_NOT_USE),),
            (self._cont("잘못된 문장.", decision=WritingGateDecision.RETRIEVE_MORE),),
            (self._cont("없는 문장."),),
            (self._cont("문장."),),  # occurs 3x → ambiguous anchor
        ):
            with self.subTest(findings=findings):
                self.assertIsNone(_eligible_revision_finding(cand, findings))

    def test_single_eligible_returned(self):
        cand = _candidate()
        f = self._cont("잘못된 문장.")
        self.assertIs(_eligible_revision_finding(cand, (f,)), f)

    def test_two_eligible_selects_first_in_gate_order(self):
        # The old contract dead-ended on 2 findings; now both are eligible and
        # the first (stable order, equal severity) is picked this round.
        cand = _candidate()
        f0 = self._cont("잘못된 문장.")
        f1 = self._cont("뒤 문장.")
        self.assertIs(_eligible_revision_finding(cand, (f0, f1)), f0)

    def test_error_severity_selected_before_warning_order_independent(self):
        # D3=A: error before warning regardless of Gate return order.
        cand = _candidate()
        warn = self._cont("잘못된 문장.", severity=WritingGateSeverity.WARNING)
        err = self._cont("뒤 문장.", severity=WritingGateSeverity.ERROR)
        self.assertIs(_eligible_revision_finding(cand, (warn, err)), err)
        self.assertIs(_eligible_revision_finding(cand, (err, warn)), err)

    def test_ineligible_findings_do_not_dead_end_eligible_one(self):
        # A POV (ineligible, D1=A) alongside a continuity finding → the
        # continuity one is still selected (presence of ineligible does not
        # force not_eligible, unlike the old len != 1 rule).
        cand = _candidate()
        pov = self._cont("잘못된 문장.", finding_type=WritingGateFindingType.POV)
        cont = self._cont("뒤 문장.")
        self.assertIs(_eligible_revision_finding(cand, (pov, cont)), cont)


class _MultiFindingGate:
    """Returns a scripted (decision, findings) per call so a multi-finding Gate
    result can drive several sequential auto-revise rounds."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = 0
        self.seen = []

    async def evaluate(self, *, request, candidate, package):
        self.calls += 1
        self.seen.append(candidate.text)
        decision, findings = self._script.pop(0)
        return WritingGateResult(
            request.request_id, request.project_id, decision, findings, (),
            "fake-gate",
        )


class MultiFindingSequentialLoopTest(unittest.TestCase):
    """D2=A: a Gate revise result with several findings is revised one per round
    (re-gate between), rather than dead-ending on the first."""

    @staticmethod
    def _request():
        return WritingRequest("r1", "p1", WritingTaskType.CONTINUE_SCENE, "고쳐줘")

    @staticmethod
    def _cont(evidence):
        return WritingGateFinding(
            WritingGateFindingType.CONTINUITY, WritingGateSeverity.WARNING,
            "m", evidence, WritingGateDecision.REVISE,
        )

    def test_multi_finding_revise_processes_sequentially(self):
        provider = _SequenceProvider(("고친1.", "고친2.", "뒤2."))
        gate = _MultiFindingGate((
            # gate 1: two eligible continuity findings → select first ("고친1.")
            (WritingGateDecision.REVISE,
             (self._cont("고친1."), self._cont("뒤 문장."))),
            # gate 2: remaining finding → select it ("뒤 문장.")
            (WritingGateDecision.REVISE, (self._cont("뒤 문장."),)),
            # gate 3: clean → pass
            (WritingGateDecision.PASS, ()),
        ))
        service = WritingReviseGateService(
            reviser=_service(provider), reporter=_Reporter(), gate=gate,
            policy=WritingLoopPolicy(max_revision_rounds=3,
                                     max_gate_evaluations=4),
        )
        result = asyncio.run(service.run(
            request=self._request(),
            candidate=_candidate("앞 문장. 잘못된 문장. 뒤 문장."),
            finding=self._cont("잘못된 문장."), package=_package(),
        ))
        self.assertIs(result.loop.status, WritingLoopStatus.PASS)
        # both continuity findings were revised in sequence, then pass.
        self.assertEqual(result.candidate.text, "앞 문장. 고친2. 뒤2.")
        self.assertEqual(result.loop.revision_rounds, 3)
        self.assertEqual(provider.calls, 3)
        self.assertEqual(gate.calls, 3)

    def test_second_eligible_bounded_by_revision_rounds(self):
        # over-strict on budget: with the default cap (2 revisions) two eligible
        # findings do NOT run unbounded — the loop stops at budget_exhausted
        # after the second revise instead of a third.
        provider = _SequenceProvider(("고친1.", "고친2."))
        gate = _MultiFindingGate((
            (WritingGateDecision.REVISE,
             (self._cont("고친1."), self._cont("뒤 문장."))),
            (WritingGateDecision.REVISE, (self._cont("뒤 문장."),)),
        ))
        service = WritingReviseGateService(
            reviser=_service(provider), reporter=_Reporter(), gate=gate,
            policy=WritingLoopPolicy(),  # defaults: 2 revision rounds
        )
        result = asyncio.run(service.run(
            request=self._request(),
            candidate=_candidate("앞 문장. 잘못된 문장. 뒤 문장."),
            finding=self._cont("잘못된 문장."), package=_package(),
        ))
        self.assertIs(result.loop.status, WritingLoopStatus.BUDGET_EXHAUSTED)
        self.assertEqual(result.loop.revision_rounds, 2)
        self.assertEqual(provider.calls, 2)


if __name__ == "__main__":
    unittest.main()
