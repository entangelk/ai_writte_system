"""Phase 2B.3.2 terminal-JSON compare judge adapter tests.

Locks the approved boundaries (brief 02b-3, D1=A): the judge strict-parses an
action JSON, repairs once on malformed/out-of-set output, and maps a still-
invalid result to InvalidJudgeResult. Guards run both directions: valid output
must parse (over-strict) and `create`/unknown/bad-shape must repair-then-fail
(under-strict). `create` is never a valid judge output.
"""

import asyncio
import json
import unittest

from services.application.app.analysis.compare import (
    CompareAction,
    InvalidJudgeResult,
)
from services.application.app.analysis.compare_judge import (
    ANALYSIS_COMPARE_PROMPT_VERSION,
    ANALYSIS_COMPARE_TASK_TYPE,
    CompareJudgeParseError,
    TerminalJsonCompareJudge,
    parse_judge_result,
    seed_analysis_compare_template,
)
from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository,
    PromptTemplateService,
)
from services.application.app.memory.models import (
    MemoryEntry,
    MemoryStatus,
    PromotionMode,
)
from services.application.app.memory.scope import MemoryScope
from services.llm_gateway.app.provider import FakeLLMProvider, GenerationResult


CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION


def _candidate():
    return AnalysisCandidate(
        id="cand-1", project_id="project-1", job_id="job-current", task_id="task-1",
        candidate_type=CHARACTER, action=AnalysisCandidateAction.CREATE,
        status=AnalysisCandidateStatus.NEEDS_REVIEW,
        provenance=AnalysisProvenance.SOURCE_OBSERVED, confidence=0.5,
        source_ref_ids=("source-ref-1",),
        payload={"name": "Ariel", "observation": "braver than before"},
    )


def _memory():
    return MemoryEntry(
        id="mem-1", project_id="project-1", memory_type=CHARACTER,
        status=MemoryStatus.CANONICAL, provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.5, source_ref_ids=("source-ref-0",),
        payload={"name": "Ariel", "observation": "brave"}, version=1,
        analysis_job_id="job-prior", source_candidate_id="cand-0",
        promotion_mode=PromotionMode.MANUAL, applied_threshold=None,
        scope=MemoryScope(scope_type="character", scope_id="ariel"),
    )


def _service():
    templates = PromptTemplateService(InMemoryPromptTemplateRepository())
    seed_analysis_compare_template(templates)
    return templates


def _result(content):
    return GenerationResult(model="fake", content=content, finish_reason="stop")


def _judge_content(action="update", rationale="refines the observation"):
    return json.dumps({"action": action, "rationale": rationale})


def _run(provider):
    judge = TerminalJsonCompareJudge(provider, prompt_templates=_service())
    return asyncio.run(judge.judge(candidate=_candidate(), memory=_memory()))


class CompareJudgeParseTest(unittest.TestCase):
    def test_valid_output_parses(self):
        provider = FakeLLMProvider([_result(_judge_content("add_evidence", "corroborates"))])
        result = _run(provider)
        self.assertEqual(result.action, CompareAction.ADD_EVIDENCE)
        self.assertEqual(result.rationale, "corroborates")
        self.assertEqual(len(provider.requests), 1)

    def test_every_matched_pair_action_parses(self):
        for action in ("update", "add_evidence", "no_change", "conflict"):
            with self.subTest(action=action):
                provider = FakeLLMProvider([_result(_judge_content(action))])
                self.assertEqual(_run(provider).action, CompareAction(action))

    def test_markdown_fenced_valid_output_parses_without_repair(self):
        # Under-strict guard: parse_judge_result strips a whole-content markdown
        # fence before json.loads, so a fenced valid object parses on the FIRST
        # call — no repair. Removing strip_code_fence forces a second request.
        provider = FakeLLMProvider(
            [_result("```json\n" + _judge_content("no_change") + "\n```")]
        )
        self.assertEqual(_run(provider).action, CompareAction.NO_CHANGE)
        self.assertEqual(len(provider.requests), 1)

    def test_unknown_action_repairs_then_succeeds(self):
        provider = FakeLLMProvider(
            [_result(_judge_content("merge")), _result(_judge_content("conflict"))]
        )
        self.assertEqual(_run(provider).action, CompareAction.CONFLICT)

    def test_create_is_never_a_valid_judge_output(self):
        # Under-strict guard: create is deterministic (no-match only). Even after
        # a repair, a create output is InvalidJudgeResult.
        provider = FakeLLMProvider(
            [_result(_judge_content("create")), _result(_judge_content("create"))]
        )
        with self.assertRaises(InvalidJudgeResult):
            _run(provider)
        self.assertEqual(len(provider.requests), 2)

    def test_bad_shape_repairs_then_fails(self):
        bad = json.dumps({"action": "update"})  # missing rationale
        provider = FakeLLMProvider([_result(bad), _result(bad)])
        with self.assertRaises(InvalidJudgeResult):
            _run(provider)
        self.assertEqual(len(provider.requests), 2)

    def test_non_json_repairs_then_fails(self):
        provider = FakeLLMProvider([_result("not json"), _result("still not json")])
        with self.assertRaises(InvalidJudgeResult):
            _run(provider)

    def test_missing_template_is_invalid_judge_result_without_provider_call(self):
        provider = FakeLLMProvider([])
        empty_templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        judge = TerminalJsonCompareJudge(provider, prompt_templates=empty_templates)
        with self.assertRaises(InvalidJudgeResult):
            asyncio.run(judge.judge(candidate=_candidate(), memory=_memory()))
        self.assertEqual(len(provider.requests), 0)

    def test_prompt_payload_carries_candidate_memory_and_no_create_action(self):
        provider = FakeLLMProvider([_result(_judge_content())])
        _run(provider)
        user_payload = json.loads(provider.requests[0].messages[-1].content)
        self.assertEqual(user_payload["candidate"]["payload"]["name"], "Ariel")
        self.assertEqual(user_payload["existing_memory"]["payload"]["observation"], "brave")
        self.assertNotIn("create", user_payload["allowed_actions"])
        self.assertEqual(
            sorted(user_payload["allowed_actions"]),
            ["add_evidence", "conflict", "no_change", "update"],
        )


class ParseJudgeResultDirectTest(unittest.TestCase):
    def test_empty_rationale_rejected(self):
        with self.assertRaises(CompareJudgeParseError):
            parse_judge_result(json.dumps({"action": "update", "rationale": ""}))

    def test_extra_field_rejected(self):
        with self.assertRaises(CompareJudgeParseError):
            parse_judge_result(
                json.dumps({"action": "update", "rationale": "x", "extra": 1})
            )

    def test_fenced_valid_output_is_extracted(self):
        # Under-strict: the whole-content fence is stripped before json.loads.
        for tag in ("json", "", "text"):
            with self.subTest(tag=tag):
                result = parse_judge_result(
                    f"```{tag}\n" + _judge_content("no_change") + "\n```"
                )
                self.assertEqual(result.action, CompareAction.NO_CHANGE)

    def test_fence_does_not_weaken_schema_check(self):
        # Over-strict: extraction unwraps format only — a fenced schema-invalid
        # object is still rejected for the RIGHT reason (schema check, not a
        # coincidental JSON error), exactly as an unfenced one would be.
        with self.assertRaisesRegex(
            CompareJudgeParseError, "result fields do not match schema"
        ):
            parse_judge_result(
                "```json\n" + json.dumps({"action": "update"}) + "\n```"
            )


if __name__ == "__main__":
    unittest.main()
