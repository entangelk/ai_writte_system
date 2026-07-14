import asyncio
import json
import unittest

from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository, PromptTemplateService,
)
from services.application.app.context_search.models import ContextPackage, ContextSearchPurpose
from services.application.app.writing.models import WritingCandidate, WritingOutputType, WritingTaskType
from services.application.app.writing.report import (
    InvalidCandidateReport, WritingCandidateReportService, parse_report,
    seed_report_template,
)
from services.application.app.writing.metering import MeteredCallError
from services.application.app.writing.gate_prompt import build_writing_gate_request
from services.application.app.analysis.prompt_templates import PromptTemplate
from services.llm_gateway.app.provider import GenerationResult, TokenUsage


def _payload():
    return {"self_reported_constraints": ["제한 시점"],
        "candidate_claims": [{"text": "문이 열렸다", "type": "narrative_event",
                              "requires_gate_check": True}],
        "new_memory_hints": [{"type": "event", "text": "문이 열림",
                              "confidence": 0.8, "should_analyze_after_save": True}],
        "risk_notes": [{"type": "pov", "severity": "high", "message": "시점 확인"}]}


class _Provider:
    def __init__(self, outputs):
        self.outputs=list(outputs); self.calls=0; self.requests=[]
    async def generate(self, request):
        self.calls += 1
        self.requests.append(request)
        return GenerationResult("fake", self.outputs.pop(0), "stop", TokenUsage(1,1))


class WritingReportTest(unittest.TestCase):
    def test_parse_typed_report_and_empty_arrays(self):
        report = parse_report(json.dumps(_payload(), ensure_ascii=False))
        self.assertEqual(report["candidate_claims"][0].claim_type.value, "narrative_event")
        empty = parse_report(json.dumps({"self_reported_constraints": [],
            "candidate_claims": [], "new_memory_hints": [], "risk_notes": []}))
        self.assertEqual(empty["risk_notes"], ())

    def test_confidence_rejects_bool_nan_and_range(self):
        for value in (True, float("nan"), -0.1, 1.1):
            payload=_payload(); payload["new_memory_hints"][0]["confidence"]=value
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_report(json.dumps(payload))

    def test_schema_and_unknown_enum_are_rejected(self):
        payload=_payload(); payload["extra"]=[]
        with self.assertRaises(ValueError): parse_report(json.dumps(payload))
        payload=_payload(); payload["risk_notes"][0]["type"]="unknown"
        with self.assertRaises(ValueError): parse_report(json.dumps(payload))

    def test_invalid_first_output_repairs_once(self):
        provider=_Provider(["bad", json.dumps(_payload(), ensure_ascii=False)])
        templates=PromptTemplateService(InMemoryPromptTemplateRepository())
        seed_report_template(templates)
        service=WritingCandidateReportService(provider, prompt_templates=templates)
        candidate=WritingCandidate("r","p",WritingTaskType.CONTINUE_SCENE,
                                   WritingOutputType.DRAFT_PATCH,"본문")
        package=ContextPackage("p",ContextSearchPurpose.WRITING_CONTEXT,(),(),(),(),0,False)
        enriched=asyncio.run(service.enrich(candidate, package))
        self.assertEqual(provider.calls,2)
        self.assertEqual(enriched.risk_notes[0].severity.value,"high")
        system_prompt = provider.requests[0].messages[0].content
        self.assertIn('"requires_gate_check": true', system_prompt)
        self.assertIn("narrative_event|character_state", system_prompt)
        self.assertIn("low|medium|high|critical", system_prompt)
        self.assertEqual(provider.requests[1].messages[0].content, system_prompt)

    def test_enrich_metered_sums_initial_and_repair_usage(self):
        # Phase 5.10 ("B2"): enrich_metered returns the summed provider usage of
        # the initial call plus the JSON-repair retry (1+1 tokens each → 4 total).
        provider=_Provider(["bad", json.dumps(_payload(), ensure_ascii=False)])
        templates=PromptTemplateService(InMemoryPromptTemplateRepository())
        seed_report_template(templates)
        service=WritingCandidateReportService(provider, prompt_templates=templates)
        candidate=WritingCandidate("r","p",WritingTaskType.CONTINUE_SCENE,
                                   WritingOutputType.DRAFT_PATCH,"본문")
        package=ContextPackage("p",ContextSearchPurpose.WRITING_CONTEXT,(),(),(),(),0,False)
        enriched, usage = asyncio.run(service.enrich_metered(candidate, package))
        self.assertEqual(provider.calls, 2)
        self.assertEqual(usage.total_tokens, 4)
        self.assertEqual(enriched.risk_notes[0].severity.value, "high")

    def test_enrich_metered_failure_carries_both_response_usages(self):
        provider = _Provider(["bad", "still bad"])
        templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        seed_report_template(templates)
        service = WritingCandidateReportService(
            provider, prompt_templates=templates
        )
        with self.assertRaises(MeteredCallError) as caught:
            asyncio.run(service.enrich_metered(
                WritingCandidate("r", "p", WritingTaskType.CONTINUE_SCENE,
                                 WritingOutputType.DRAFT_PATCH, "본문"),
                ContextPackage("p", ContextSearchPurpose.WRITING_CONTEXT,
                               (), (), (), (), 0, False),
            ))
        self.assertIsInstance(caught.exception.cause, InvalidCandidateReport)
        self.assertEqual(caught.exception.usage.total_tokens, 4)

    def test_invalid_repair_fails(self):
        provider=_Provider(["bad","still bad"])
        templates=PromptTemplateService(InMemoryPromptTemplateRepository())
        seed_report_template(templates)
        service=WritingCandidateReportService(provider, prompt_templates=templates)
        candidate=WritingCandidate("r","p",WritingTaskType.CONTINUE_SCENE,
                                   WritingOutputType.DRAFT_PATCH,"본문")
        package=ContextPackage("p",ContextSearchPurpose.WRITING_CONTEXT,(),(),(),(),0,False)
        with self.assertRaises(InvalidCandidateReport):
            asyncio.run(service.enrich(candidate,package))

    def test_gate_receives_structured_report_not_repr(self):
        provider=_Provider([json.dumps(_payload(), ensure_ascii=False)])
        templates=PromptTemplateService(InMemoryPromptTemplateRepository())
        seed_report_template(templates)
        service=WritingCandidateReportService(provider, prompt_templates=templates)
        candidate=WritingCandidate("r","p",WritingTaskType.CONTINUE_SCENE,
                                   WritingOutputType.DRAFT_PATCH,"본문")
        package=ContextPackage("p",ContextSearchPurpose.WRITING_CONTEXT,(),(),(),(),0,False)
        enriched=asyncio.run(service.enrich(candidate,package))
        prompt=PromptTemplate(id="x", task_type="writing_gate", version="v", template="gate")
        request=build_writing_gate_request(request=type("R",(),{
            "request_id":"r","task_type":WritingTaskType.CONTINUE_SCENE,
            "instruction":"x","draft_excerpt":""})(), candidate=enriched,
            package=package,prompt_template=prompt)
        payload=json.loads(request.messages[1].content)
        candidate=payload["candidate"]
        # v1.6.71 보강 (H3): every report field is serialized under the PUBLIC
        # schema key `type`; the internal dataclass names (claim_type/hint_type/
        # risk_type) must not leak into the gate prompt either.
        self.assertEqual(candidate["candidate_claims"][0]["type"], "narrative_event")
        self.assertNotIn("claim_type", candidate["candidate_claims"][0])
        self.assertEqual(candidate["new_memory_hints"][0]["type"], "event")
        self.assertNotIn("hint_type", candidate["new_memory_hints"][0])
        self.assertEqual(candidate["risk_notes"][0]["type"], "pov")
        self.assertNotIn("risk_type", candidate["risk_notes"][0])


class ReportFenceStrippingTest(unittest.TestCase):
    """Markdown code-fence extraction in parse_report (D2=A v1.6.85).

    Mirror of GateFenceStrippingTest. parse_report strips a whole-content
    ```` ```lang…``` ```` fence before json.loads — extraction, not contract
    relaxation: the strict 4-field schema/item checks still apply. Both the
    first and the 1-call repair outputs go through parse_report, so a fence on
    EITHER attempt is handled. Two directions locked: fenced valid parses
    (under-strict — removing the strip re-fails), fenced invalid is still
    rejected for the right reason (over-strict — the strip does not weaken).
    """

    @staticmethod
    def _fence(inner, tag="json"):
        return f"```{tag}\n{inner}\n```"

    def _service(self, provider):
        templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        seed_report_template(templates)
        return WritingCandidateReportService(provider, prompt_templates=templates)

    @staticmethod
    def _candidate():
        return WritingCandidate(request_id="wr1", project_id="p1",
            task_type=WritingTaskType.CONTINUE_SCENE,
            output_type=WritingOutputType.DRAFT_PATCH, text="아린은 문을 열었다.")

    @staticmethod
    def _package():
        return ContextPackage(project_id="p1", purpose=ContextSearchPurpose.WRITING_CONTEXT,
            macro_items=(), micro_evidence=(), constraints=(), do_not_use=(),
            token_estimate_total=0, degraded=False)

    def test_fenced_valid_report_is_parsed(self):
        # under-strict: without the strip this raises JSONDecodeError. With the
        # strip the fenced valid object parses.
        report = parse_report(self._fence(json.dumps(_payload(), ensure_ascii=False)))
        self.assertEqual(report["candidate_claims"][0].text, "문이 열렸다")

    def test_bare_and_other_language_tags_are_stripped(self):
        valid = json.dumps(_payload(), ensure_ascii=False)
        for tag in ("", "text", "json"):
            with self.subTest(tag=tag):
                self.assertEqual(parse_report(self._fence(valid, tag=tag))
                                 ["risk_notes"][0].severity, "high")

    def test_unfenced_report_is_unchanged(self):
        report = parse_report(json.dumps(_payload(), ensure_ascii=False))
        self.assertEqual(report["self_reported_constraints"], ("제한 시점",))

    def test_fence_does_not_weaken_schema_check(self):
        # over-strict: a rogue key inside a fence is still rejected exactly as
        # an unfenced rogue key would be. The strip normalizes format only.
        rogue = {**_payload(), "rogue_key": "schema violation"}
        with self.assertRaisesRegex(ValueError, "fields do not match schema"):
            parse_report(self._fence(json.dumps(rogue, ensure_ascii=False)))

    def test_fence_does_not_weaken_array_field_check(self):
        # over-strict: a non-array field inside a fence is still rejected.
        bad = {**_payload(), "candidate_claims": "not-an-array"}
        with self.assertRaisesRegex(ValueError, "must be an array"):
            parse_report(self._fence(json.dumps(bad, ensure_ascii=False)))

    def test_enrich_strips_fenced_first_and_skips_repair(self):
        # Service-level under-strict: a fenced valid first output parses via the
        # strip → enrich succeeds in ONE call (no repair needed). Removing the
        # strip would force a repair call.
        provider = _Provider([self._fence(json.dumps(_payload(), ensure_ascii=False))])
        asyncio.run(self._service(provider).enrich_metered(self._candidate(), self._package()))
        self.assertEqual(provider.calls, 1)  # no repair

    def test_repair_output_fence_is_also_stripped(self):
        # The repair path also calls parse_report, so a fenced repair output is
        # extracted too. First attempt is schema-invalid (triggers repair); the
        # repair returns a fenced valid object → stripped → success via repair.
        provider = _Provider([
            json.dumps({**_payload(), "candidate_claims": "not-an-array"}, ensure_ascii=False),
            self._fence(json.dumps(_payload(), ensure_ascii=False)),
        ])
        enriched, _usage = asyncio.run(self._service(provider).enrich_metered(
            self._candidate(), self._package()))
        self.assertEqual(provider.calls, 2)  # first failed (schema) + repair
        self.assertEqual(enriched.candidate_claims[0].text, "문이 열렸다")
