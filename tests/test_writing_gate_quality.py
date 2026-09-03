"""Writing Gate labelled-quality benchmark regressions."""

import asyncio
import json
import os
import unittest

from services.application.app.writing.gate_quality import (
    GATE_QUALITY_CASES,
    run_gate_quality_benchmark,
)
from services.application.app.writing.gate_prompt import WRITING_GATE_TEMPLATE
from services.llm_gateway.app.provider import (
    FakeLLMProvider,
    GenerationResult,
    TokenUsage,
)


def _output(case):
    findings = []
    if case.expected_finding_types:
        finding_type = case.expected_finding_types[0].value
        evidence = (
            "준호가 배신자라는 사실"
            if finding_type == "do_not_use"
            else "준호는 민아가 자신을 의심한다는 사실에 속으로 안도했다"
            if finding_type == "pov"
            else case.candidate_text.split(".")[0].strip()
        )
        findings.append({
            "type": finding_type,
            "severity": "error" if finding_type in {"do_not_use", "pov"} else "warning",
            "message": "라벨 fixture의 판정 근거다.",
            "evidence": evidence,
            "recommended_decision": case.expected_decision.value,
        })
    return json.dumps({
        "findings": findings,
        "checked_constraints": ["do_not_use", "POV", "continuity"],
    }, ensure_ascii=False)


def _result(content, tokens=3):
    return GenerationResult(
        model="fake-gate", content=content, finish_reason="stop",
        usage=TokenUsage(1, tokens - 1),
    )


class GateQualityFixtureTest(unittest.TestCase):
    def test_fixture_matrix_locks_every_decision_and_pass_overstrict_guards(self):
        decisions = {case.expected_decision.value for case in GATE_QUALITY_CASES}
        self.assertEqual(decisions, {
            "pass", "revise", "retrieve_more", "needs_user_review", "block",
        })
        self.assertEqual(
            [case.case_id for case in GATE_QUALITY_CASES if case.expected_decision.value == "pass"],
            ["pass_live_seed_transition", "pass_compatible_new_action"],
        )

    def test_all_labelled_outputs_score_exactly(self):
        provider = FakeLLMProvider([_result(_output(case)) for case in GATE_QUALITY_CASES])
        from services.application.app.analysis.prompt_templates import (
            InMemoryPromptTemplateRepository,
            PromptTemplateService,
        )
        from services.application.app.writing.gate import (
            WritingGateService,
            seed_writing_gate_template,
        )
        templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        seed_writing_gate_template(templates)
        report = asyncio.run(run_gate_quality_benchmark(
            WritingGateService(provider, prompt_templates=templates)
        ))
        self.assertTrue(report["complete"])
        self.assertEqual(report["matched_count"], len(GATE_QUALITY_CASES))
        self.assertEqual(report["accuracy"], 1.0)
        self.assertTrue(all(row["total_tokens"] == 3 for row in report["rows"]))

    def test_wrong_decision_and_invalid_result_are_fail_closed_and_isolated(self):
        cases = GATE_QUALITY_CASES[:2]
        wrong = json.dumps({
            # Schema audit A: no top-level decision — a wrong verdict now comes
            # from an over-eager finding, which the server derives "revise" from.
            "findings": [{
                "type": "continuity", "severity": "warning",
                "message": "과민 판정", "evidence": "민아는 역 안으로 들어섰다",
                "recommended_decision": "revise",
            }],
            "checked_constraints": ["continuity"],
        }, ensure_ascii=False)
        provider = FakeLLMProvider([_result(wrong), _result("not json")])
        from services.application.app.analysis.prompt_templates import (
            InMemoryPromptTemplateRepository,
            PromptTemplateService,
        )
        from services.application.app.writing.gate import (
            WritingGateService,
            seed_writing_gate_template,
        )
        templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        seed_writing_gate_template(templates)
        report = asyncio.run(run_gate_quality_benchmark(
            WritingGateService(provider, prompt_templates=templates), cases=cases,
        ))
        self.assertFalse(report["complete"])
        self.assertEqual(report["matched_count"], 0)
        self.assertEqual(report["rows"][0]["status"], "succeeded")
        self.assertFalse(report["rows"][0]["matched"])
        self.assertEqual(report["rows"][1]["status"], "invalid_result")
        self.assertFalse(report["rows"][1]["matched"])
        self.assertEqual(report["rows"][1]["total_tokens"], 3)

    def test_repeats_are_scored_as_separate_attempts(self):
        case = GATE_QUALITY_CASES[0]
        provider = FakeLLMProvider([_result(_output(case)), _result(_output(case))])
        from services.application.app.analysis.prompt_templates import (
            InMemoryPromptTemplateRepository,
            PromptTemplateService,
        )
        from services.application.app.writing.gate import (
            WritingGateService,
            seed_writing_gate_template,
        )
        templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        seed_writing_gate_template(templates)
        report = asyncio.run(run_gate_quality_benchmark(
            WritingGateService(provider, prompt_templates=templates),
            cases=(case,), repeats=2,
        ))
        self.assertEqual(report["attempt_count"], 2)
        self.assertEqual([row["iteration"] for row in report["rows"]], [1, 2])

    def test_production_factory_preserves_prompt_model_and_token_config(self):
        original = os.environ.copy()
        self.addCleanup(self._restore_env, original)
        os.environ.update({
            "LLM_GATEWAY_BASE_URL": "http://gateway",
            "LLM_GATEWAY_MODEL": "quality-model",
            "WRITING_GATE_MAX_TOKENS": "777",
        })
        provider = FakeLLMProvider([_result(_output(GATE_QUALITY_CASES[0]))])
        from scripts.benchmark_writing_gate import build_gate_service
        gate = build_gate_service(provider=provider)
        asyncio.run(run_gate_quality_benchmark(
            gate, cases=(GATE_QUALITY_CASES[0],),
        ))
        request = provider.requests[0]
        self.assertEqual(request.model, "quality-model")
        self.assertEqual(request.max_tokens, 777)
        self.assertFalse(request.thinking)
        self.assertEqual(request.messages[0].content, WRITING_GATE_TEMPLATE)

    @staticmethod
    def _restore_env(original):
        os.environ.clear()
        os.environ.update(original)

    def test_invalid_repeats_rejected_before_provider(self):
        with self.assertRaisesRegex(ValueError, "at least 1"):
            asyncio.run(run_gate_quality_benchmark(
                FakeLLMProvider([]), repeats=0, cases=(),
            ))
