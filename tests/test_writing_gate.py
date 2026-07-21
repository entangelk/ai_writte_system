"""Phase 5.2 Writing Gate regressions (owner D1=A/D2=B/D3=A/D4=A)."""

import asyncio
import json
import unittest

import httpx

from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository, PromptTemplateService,
)
from services.application.app.context_search.models import (
    ContextPackage, ContextSearchErrorType, ContextSearchPurpose,
)
from services.application.app.context_search.service import (
    ContextSearchBudgetExceeded, ContextSearchFailed,
)
from services.application.app.core_sot.service import CoreSotService, InMemoryCoreSotRepository
from services.application.app.main import create_app
from services.application.app.writing.gate import (
    InvalidWritingGateResult, WritingGateError, WritingGateService,
    parse_writing_gate_result,
    seed_writing_gate_template,
)
from services.application.app.writing.models import (
    WritingCandidate, WritingGateDecision, WritingGateFindingType,
    WritingOutputType, WritingRequest, WritingTaskType,
)
from services.application.app.writing.metering import MeteredCallError
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.provider import GenerationResult, TokenUsage


def _package(project_id="p1", *, constraints=(), do_not_use=()):
    return ContextPackage(project_id=project_id,
        purpose=ContextSearchPurpose.WRITING_CONTEXT,
        macro_items=(), micro_evidence=(),
        constraints=tuple(constraints), do_not_use=tuple(do_not_use),
        token_estimate_total=0, degraded=False)


def _request(project_id="p1"):
    return WritingRequest(request_id="wr1", project_id=project_id,
        task_type=WritingTaskType.CONTINUE_SCENE, instruction="이어서 써줘")


def _candidate(project_id="p1", text="아린은 문을 열었다."):
    return WritingCandidate(request_id="wr1", project_id=project_id,
        task_type=WritingTaskType.CONTINUE_SCENE,
        output_type=WritingOutputType.DRAFT_PATCH, text=text)


def _output(decision="pass", findings=None):
    return json.dumps({"decision": decision, "findings": findings or [],
                       "checked_constraints": ["POV 제한 시점"]},
                      ensure_ascii=False)


def _finding(*, recommendation="revise", finding_type="continuity",
             severity="error"):
    return {"type": finding_type, "severity": severity,
            "message": "앞 문단과 상태가 다르다.", "evidence": "문을 열었다",
            "recommended_decision": recommendation}


class _Provider:
    def __init__(self, content=None, error=None):
        self.content = content if content is not None else _output()
        self.error = error
        self.calls = 0
        self.last_request = None

    async def generate(self, request):
        self.calls += 1
        self.last_request = request
        if self.error:
            raise self.error
        return GenerationResult(model="fake-gate", content=self.content,
            finish_reason="stop", usage=TokenUsage(1, 1))


def _service(provider):
    templates = PromptTemplateService(InMemoryPromptTemplateRepository())
    seed_writing_gate_template(templates)
    return WritingGateService(provider, prompt_templates=templates)


class GateContractTest(unittest.TestCase):
    def test_pass_requires_no_findings(self):
        decision, findings, checked = parse_writing_gate_result(_output())
        self.assertIs(decision, WritingGateDecision.PASS)
        self.assertEqual(findings, ())
        self.assertEqual(checked, ("POV 제한 시점",))

    def test_each_non_pass_decision_is_preserved(self):
        for literal in ("revise", "retrieve_more", "needs_user_review", "block"):
            with self.subTest(literal=literal):
                decision, findings, _ = parse_writing_gate_result(_output(
                    literal, [_finding(recommendation=literal)]))
                self.assertEqual(decision.value, literal)
                self.assertEqual(findings[0].recommended_decision.value, literal)

    def test_priority_rejects_weaker_top_level_decision(self):
        findings = [_finding(recommendation="revise"),
                    _finding(recommendation="block", finding_type="pov")]
        with self.assertRaisesRegex(ValueError, "priority"):
            parse_writing_gate_result(_output("revise", findings))
        decision, _, _ = parse_writing_gate_result(_output("block", findings))
        self.assertIs(decision, WritingGateDecision.BLOCK)

    def test_priority_rejects_overstated_top_level_decision(self):
        # Over-strict guard: lower findings cannot be promoted to a stronger
        # editor action by the model.
        for overstated in ("retrieve_more", "needs_user_review", "block"):
            with self.subTest(overstated=overstated), self.assertRaisesRegex(
                ValueError, "priority"
            ):
                parse_writing_gate_result(_output(
                    overstated, [_finding(recommendation="revise")]))

    def test_priority_chain_uses_strongest_finding_at_every_level(self):
        chain = ("revise", "retrieve_more", "needs_user_review", "block")
        for strongest_index, strongest in enumerate(chain):
            findings = [_finding(recommendation=value) for value in
                        chain[:strongest_index + 1]]
            decision, _, _ = parse_writing_gate_result(
                _output(strongest, findings))
            self.assertEqual(decision.value, strongest)

    def test_unknown_literal_and_schema_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_writing_gate_result("not json")
        with self.assertRaises(ValueError):
            parse_writing_gate_result(_output("review"))
        with self.assertRaises(ValueError):
            parse_writing_gate_result(json.dumps({"decision": "pass"}))

    def test_finding_cannot_recommend_pass(self):
        with self.assertRaises(ValueError):
            parse_writing_gate_result(_output("pass", [_finding(recommendation="pass")]))

    def test_hard_do_not_use_and_pov_findings_cannot_be_weakened(self):
        invalid_pairs = (
            ("error", "revise"),
            ("error", "retrieve_more"),
            ("error", "needs_user_review"),
            ("warning", "block"),
            ("warning", "revise"),
            ("warning", "retrieve_more"),
            ("warning", "needs_user_review"),
        )
        for finding_type in ("do_not_use", "pov"):
            for severity, recommendation in invalid_pairs:
                with self.subTest(finding_type=finding_type,
                                  severity=severity,
                                  recommendation=recommendation), \
                        self.assertRaisesRegex(ValueError, "blocking errors"):
                    parse_writing_gate_result(_output(recommendation, [_finding(
                        recommendation=recommendation,
                        finding_type=finding_type, severity=severity)]))

    def test_evaluate_is_one_turn_and_returns_structured_result(self):
        provider = _Provider(_output("block", [_finding(
            recommendation="block", finding_type="do_not_use")]))
        result = asyncio.run(_service(provider).evaluate(
            request=_request(), candidate=_candidate(),
            package=_package(do_not_use=("배신을 밝히지 않는다",))))
        self.assertIs(result.decision, WritingGateDecision.BLOCK)
        self.assertEqual(provider.calls, 1)
        self.assertIn("배신을 밝히지 않는다", provider.last_request.messages[1].content)

    def test_evaluate_metered_returns_provider_usage(self):
        provider = _Provider()
        result, usage = asyncio.run(_service(provider).evaluate_metered(
            request=_request(), candidate=_candidate(), package=_package(),
        ))
        self.assertIs(result.decision, WritingGateDecision.PASS)
        self.assertEqual(usage.total_tokens, 2)

    def test_evaluate_metered_invalid_result_carries_usage(self):
        with self.assertRaises(MeteredCallError) as caught:
            asyncio.run(_service(_Provider("bad")).evaluate_metered(
                request=_request(), candidate=_candidate(), package=_package(),
            ))
        self.assertIsInstance(caught.exception.cause, InvalidWritingGateResult)
        self.assertEqual(caught.exception.usage.total_tokens, 2)

    def test_evidence_must_be_grounded_in_candidate_text(self):
        provider = _Provider(_output("revise", [_finding(
            recommendation="revise")]))
        with self.assertRaisesRegex(InvalidWritingGateResult, "evidence"):
            asyncio.run(_service(provider).evaluate(
                request=_request(), candidate=_candidate(text="다른 문장."),
                package=_package()))

    def test_cross_project_and_request_mismatch_stop_before_provider(self):
        provider = _Provider()
        for candidate in (_candidate("p2"), WritingCandidate(
                request_id="other", project_id="p1",
                task_type=WritingTaskType.CONTINUE_SCENE,
                output_type=WritingOutputType.DRAFT_PATCH, text="x")):
            with self.assertRaises(WritingGateError):
                asyncio.run(_service(provider).evaluate(
                    request=_request(), candidate=candidate, package=_package()))
        self.assertEqual(provider.calls, 0)

    def test_cross_project_package_stops_before_provider(self):
        provider = _Provider()
        with self.assertRaisesRegex(WritingGateError, "different projects"):
            asyncio.run(_service(provider).evaluate(
                request=_request(), candidate=_candidate(),
                package=_package("p2")))
        self.assertEqual(provider.calls, 0)


class GateStyleFindingTest(unittest.TestCase):
    """증분 3 (D5=A/D6=A): ``style`` findings are ADVISORY. They must be warning
    severity recommending needs_user_review (never error/block/revise), and they are
    EXCLUDED from the decision priority so a candidate whose only findings are style
    still passes — 경고이지 차단 아님, 최종 결정은 사용자. Guards run both directions.
    """

    def _style(self, *, severity="warning", recommendation="needs_user_review"):
        return _finding(finding_type="style", severity=severity,
                        recommendation=recommendation)

    def test_style_only_findings_still_pass(self):
        # The crux of D6: style must NOT escalate the decision. If style were in the
        # priority max, decision would be needs_user_review and pass would reject —
        # this test fails then. The finding stays surfaced for the author to notice.
        decision, findings, _ = parse_writing_gate_result(
            _output("pass", [self._style()]))
        self.assertIs(decision, WritingGateDecision.PASS)
        self.assertEqual(len(findings), 1)
        self.assertIs(findings[0].finding_type, WritingGateFindingType.STYLE)

    def test_style_does_not_lift_a_non_style_decision(self):
        # style alongside a continuity revise: the decision follows continuity only.
        decision, _, _ = parse_writing_gate_result(_output("revise", [
            _finding(finding_type="continuity", severity="error",
                     recommendation="revise"),
            self._style(),
        ]))
        self.assertIs(decision, WritingGateDecision.REVISE)

    def test_style_is_carried_but_not_decision_driving_under_block(self):
        # do_not_use(block) drives; style rides along in findings, decision=block.
        decision, findings, _ = parse_writing_gate_result(_output("block", [
            _finding(finding_type="do_not_use", severity="error",
                     recommendation="block"),
            self._style(),
        ]))
        self.assertIs(decision, WritingGateDecision.BLOCK)
        self.assertIn(WritingGateFindingType.STYLE,
                      {f.finding_type for f in findings})

    def test_style_must_be_warning_not_error(self):
        # under-strict: a style finding may not masquerade as a blocking error.
        with self.assertRaises(ValueError):
            parse_writing_gate_result(
                _output("pass", [self._style(severity="error")]))

    def test_style_may_only_recommend_needs_user_review(self):
        # over-strict: warning-only·자동 revise 제외·block 없음 locked at parse.
        for rec in ("block", "revise", "retrieve_more"):
            with self.subTest(recommendation=rec):
                with self.assertRaises(ValueError):
                    parse_writing_gate_result(
                        _output("pass", [self._style(recommendation=rec)]))

    def test_style_does_not_suppress_a_non_style_needs_user_review(self):
        # hardening (D5): style is advisory, but a genuine non-style
        # needs_user_review finding must still drive the decision even when style
        # rides along. If style's advisory nature wrongly swallowed every
        # needs_user_review (or the non-style finding were dropped from the
        # priority max), decision would drop to pass and this re-fails.
        decision, findings, _ = parse_writing_gate_result(_output(
            "needs_user_review",
            [_finding(finding_type="continuity", severity="warning",
                      recommendation="needs_user_review"),
             self._style()],
        ))
        self.assertIs(decision, WritingGateDecision.NEEDS_USER_REVIEW)
        self.assertEqual(len(findings), 2)


class GateFenceStrippingTest(unittest.TestCase):
    """Markdown code-fence normalization (D2=A root-cause fix, SoT v1.6.83).

    A model may wrap an otherwise-valid Gate JSON object in a ``\\`\\`\\`json``
    fence. ``json_object`` strips a whole-content fence before parsing; the
    strict schema/enum/priority/evidence checks are unchanged. Both directions
    locked: fenced valid JSON must parse (under-strict — removing the strip
    re-fails the B2b ``invalid_gate_result`` 502), and fenced invalid JSON must
    still be rejected (over-strict — the strip normalizes format, not contract).
    """

    @staticmethod
    def _fence(inner, tag="json"):
        return f"```{tag}\n{inner}\n```"

    def test_fenced_valid_json_is_parsed(self):
        # under-strict: without the strip this raises JSONDecodeError (the B2b
        # invalid_gate_result 502). With the strip the valid object parses.
        decision, findings, checked = parse_writing_gate_result(
            self._fence(_output()))
        self.assertIs(decision, WritingGateDecision.PASS)
        self.assertEqual(findings, ())
        self.assertEqual(checked, ("POV 제한 시점",))

    def test_bare_and_other_language_tags_are_stripped(self):
        for tag in ("", "text", "json"):
            with self.subTest(tag=tag):
                decision, _, _ = parse_writing_gate_result(
                    self._fence(_output(), tag=tag))
                self.assertIs(decision, WritingGateDecision.PASS)

    def test_unfenced_content_is_unchanged(self):
        # No fence → behaviour identical to before the strip.
        decision, _, _ = parse_writing_gate_result(_output())
        self.assertIs(decision, WritingGateDecision.PASS)

    def test_fenced_surrounding_whitespace_is_tolerated(self):
        decision, _, _ = parse_writing_gate_result(
            "  \n" + self._fence(_output()) + "\n  ")
        self.assertIs(decision, WritingGateDecision.PASS)

    def test_fence_does_not_weaken_schema_check(self):
        # over-strict: a rogue key inside a fence is still rejected exactly as
        # an unfenced rogue key would be. The strip normalizes format only.
        rogue = json.dumps({"decision": "pass", "findings": [],
                            "checked_constraints": ["POV 제한 시점"],
                            "rogue_key": "schema violation"}, ensure_ascii=False)
        with self.assertRaisesRegex(ValueError, "fields do not match schema"):
            parse_writing_gate_result(self._fence(rogue))

    def test_fence_does_not_weaken_priority_check(self):
        fenced = self._fence(_output("block", [_finding(recommendation="revise")]))
        with self.assertRaisesRegex(ValueError, "priority"):
            parse_writing_gate_result(fenced)

    def test_fence_around_non_json_still_rejected(self):
        with self.assertRaisesRegex(ValueError, "must be JSON"):
            parse_writing_gate_result(self._fence("not json at all"))

    def test_gate_service_accepts_fenced_valid_output(self):
        # Full service path: the provider returns a fenced valid pass; the Gate
        # strips and evaluates normally in one turn (no repair needed).
        provider = _Provider(self._fence(_output()))
        result = asyncio.run(_service(provider).evaluate(
            request=_request(), candidate=_candidate(), package=_package()))
        self.assertIs(result.decision, WritingGateDecision.PASS)
        self.assertEqual(provider.calls, 1)

    def test_fence_does_not_weaken_evidence_containment(self):
        # over-strict at the service level: a fenced finding whose evidence is
        # absent from the candidate still fails the grounding check post-strip.
        provider = _Provider(self._fence(_output("revise", [_finding(
            recommendation="revise")])))
        with self.assertRaisesRegex(InvalidWritingGateResult, "evidence"):
            asyncio.run(_service(provider).evaluate(
                request=_request(), candidate=_candidate(text="다른 문장."),
                package=_package()))


class _Context:
    def __init__(self, package=None, *, error=None):
        self.package = package or _package()
        self.error = error
    async def build_context_package(self, request):
        if self.error is not None:
            raise self.error
        return _package(request.project_id,
            constraints=self.package.constraints, do_not_use=self.package.do_not_use)


class WritingGateApiTest(unittest.TestCase):
    def _client(self, provider=None, *, with_context=True, with_gate=True,
                context_error=None):
        templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        seed_writing_gate_template(templates)
        gate = (WritingGateService(provider or _Provider(), prompt_templates=templates)
                if with_gate else None)
        app = create_app(service=CoreSotService(InMemoryCoreSotRepository()),
            context_search_service=(_Context(error=context_error)
                                    if with_context else None),
            writing_gate_service=gate)
        async def setup():
            transport = httpx.ASGITransport(app=app)
            client = httpx.AsyncClient(transport=transport, base_url="http://test")
            project = (await client.post("/projects", json={"name": "Novel"})).json()["id"]
            return client, project
        return asyncio.run(setup())

    def _post(self, client, project, **overrides):
        payload = {
            "request_id": "wr1", "instruction": "이어서 써줘",
            "candidate_text": "아린은 문을 열었다."
        }
        payload.update(overrides)
        return asyncio.run(client.post(
            f"/projects/{project}/writing/gate", json=payload))

    def test_gate_returns_structured_result(self):
        client, project = self._client(_Provider(_output(
            "revise", [_finding(recommendation="revise")])))
        response = self._post(client, project)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "revise")
        self.assertEqual(response.json()["findings"][0]["type"], "continuity")
        asyncio.run(client.aclose())

    def test_invalid_model_output_is_502_not_success(self):
        client, project = self._client(_Provider("bad"))
        self.assertEqual(self._post(client, project).status_code, 502)
        asyncio.run(client.aclose())

    def test_provider_timeout_is_504_and_other_fault_is_502(self):
        for code, expected in ((ProviderErrorCode.TIMEOUT, 504),
                               (ProviderErrorCode.UNAVAILABLE, 502)):
            provider = _Provider(error=ProviderError(
                code=code, message="down", retryable=True, provider="gateway"))
            client, project = self._client(provider)
            self.assertEqual(self._post(client, project).status_code, expected)
            asyncio.run(client.aclose())

    def test_missing_project_is_404(self):
        client, _ = self._client()
        self.assertEqual(self._post(client, "ghost").status_code, 404)
        asyncio.run(client.aclose())

    def test_missing_dependencies_are_503(self):
        client, project = self._client(with_context=False)
        self.assertEqual(self._post(client, project).status_code, 503)
        asyncio.run(client.aclose())

    def test_invalid_inputs_are_400(self):
        client, project = self._client()
        for overrides in ({"instruction": "   "},
                          {"candidate_text": "   "},
                          {"task_type": "revise"}):
            with self.subTest(overrides=overrides):
                self.assertEqual(
                    self._post(client, project, **overrides).status_code, 400)
        asyncio.run(client.aclose())

    def test_context_search_failures_map_to_504_and_502(self):
        cases = (
            (ContextSearchBudgetExceeded("budget"), 504),
            (ContextSearchFailed(ContextSearchErrorType.BACKEND_ERROR, "down"),
             502),
        )
        for error, expected in cases:
            client, project = self._client(context_error=error)
            with self.subTest(error=type(error).__name__):
                self.assertEqual(self._post(client, project).status_code, expected)
            asyncio.run(client.aclose())
        client, project = self._client(with_gate=False)
        self.assertEqual(self._post(client, project).status_code, 503)
        asyncio.run(client.aclose())


class WritingGateEnvelopeKeyTest(unittest.TestCase):
    """C0 exact-key safety net for the gate envelope (SoT v1.7.1, D3=A).

    Pins the COMPLETE key set of ``_writing_gate_payload`` and its nested
    findings before ``response_model=WritingGatePayload`` is applied, so a
    too-narrow model bites here instead of silently dropping a field.
    """

    def test_gate_envelope_keys_are_complete(self):
        client, project = WritingGateApiTest()._client(_Provider(_output(
            "revise", [_finding(recommendation="revise")])))
        body = WritingGateApiTest()._post(client, project).json()
        self.assertEqual(set(body), {
            "request_id", "project_id", "decision", "findings",
            "checked_constraints", "evaluated_by_model",
        })
        self.assertEqual(set(body["findings"][0]), {
            "type", "severity", "message", "evidence", "recommended_decision",
        })
        asyncio.run(client.aclose())
