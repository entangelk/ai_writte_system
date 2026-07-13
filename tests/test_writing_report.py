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
