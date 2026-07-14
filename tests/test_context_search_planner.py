"""Phase 4 Slice 4.2 terminal-JSON SearchPlan planner tests.

Locks the approved boundaries (docs/plans/04-agentic-search-kickoff-decisions.md
§9.2): the planner strict-parses a SearchPlan JSON, repairs once on a malformed
or out-of-set output, and maps a still-invalid result to llm_error. Guards run
both directions: valid output must parse (over-strict guard) and invalid literals
must repair-then-fail (under-strict guard).
"""

import json
import unittest

from services.application.app.context_search.models import (
    ContextBudget,
    ContextNeed,
    ContextSearchErrorType,
    ContextSearchPurpose,
    ContextSearchRequest,
    CurrentPosition,
    SearchTool,
)
from services.application.app.context_search.planner import (
    CONTEXT_SEARCH_PLAN_PROMPT_VERSION,
    CONTEXT_SEARCH_PLAN_TASK_TYPE,
    CONTEXT_SEARCH_PLAN_TEMPLATE,
    SearchPlanParseError,
    TerminalJsonSearchPlanner,
    parse_search_plan,
    seed_context_search_plan_template,
)
from services.application.app.context_search.service import ContextSearchFailed
from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository,
    PromptTemplateService,
)
from services.llm_gateway.app.provider import FakeLLMProvider, GenerationResult


def _request() -> ContextSearchRequest:
    return ContextSearchRequest(
        project_id="project-1",
        purpose=ContextSearchPurpose.WRITING_CONTEXT,
        needs=(ContextNeed.CURRENT_SCENE, ContextNeed.SOURCE_QUOTE),
        query="아린이 항구에서 무엇을 봤나",
        current_position=CurrentPosition(draft_id="draft-1", version_id="v-1"),
        context_budget=ContextBudget(max_tokens=1024),
    )


def _result(content: str) -> GenerationResult:
    return GenerationResult(model="fake", content=content, finish_reason="stop")


def _plan_content(steps=None) -> str:
    if steps is None:
        steps = [
            {
                "step_id": "s1",
                "need": "current_scene",
                "tools": ["mongo"],
                "query": "현재 장면",
            },
            {
                "step_id": "s2",
                "need": "source_quote",
                "tools": ["vector"],
                "query": "항구 묘사",
            },
        ]
    return json.dumps({"plan_id": "plan-1", "steps": steps}, ensure_ascii=False)


def _planner(provider) -> TerminalJsonSearchPlanner:
    templates = PromptTemplateService(InMemoryPromptTemplateRepository())
    seed_context_search_plan_template(templates)
    return TerminalJsonSearchPlanner(provider, prompt_templates=templates)


class ParseSearchPlanTest(unittest.TestCase):
    def test_valid_plan_parses_literals_and_injects_project_id(self):
        plan = parse_search_plan(_plan_content(), "project-1")
        self.assertEqual(plan.plan_id, "plan-1")
        self.assertEqual(plan.project_id, "project-1")
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].need, ContextNeed.CURRENT_SCENE)
        self.assertEqual(plan.steps[0].tools, (SearchTool.MONGO,))
        self.assertEqual(plan.steps[1].tools, (SearchTool.VECTOR,))

    def test_plan_id_defaults_when_absent(self):
        content = json.dumps(
            {"steps": [
                {"step_id": "s1", "need": "current_scene",
                 "tools": ["mongo"], "query": "x"},
            ]}
        )
        plan = parse_search_plan(content, "project-1")
        self.assertTrue(plan.plan_id)

    def test_unknown_need_literal_is_parse_error(self):
        with self.assertRaises(SearchPlanParseError):
            parse_search_plan(
                _plan_content(
                    [{"step_id": "s1", "need": "villain_arc",
                      "tools": ["mongo"], "query": "x"}]
                ),
                "project-1",
            )

    def test_unknown_tool_literal_is_parse_error(self):
        with self.assertRaises(SearchPlanParseError):
            parse_search_plan(
                _plan_content(
                    [{"step_id": "s1", "need": "current_scene",
                      "tools": ["graph"], "query": "x"}]
                ),
                "project-1",
            )

    def test_step_with_extra_field_is_parse_error(self):
        """B1 should-fire: exact key match rejects extra fields (LLM reasoning
        leak / tool typo). Dropping the set-equality check re-passes this."""
        with self.assertRaises(SearchPlanParseError):
            parse_search_plan(
                _plan_content(
                    [{"step_id": "s1", "need": "current_scene",
                      "tools": ["mongo"], "query": "x", "reasoning": "why"}]
                ),
                "project-1",
            )

    def test_step_missing_required_field_is_parse_error(self):
        """B1 should-fire (other direction): a step missing a required key is
        rejected by the same set-equality check."""
        with self.assertRaises(SearchPlanParseError):
            parse_search_plan(
                _plan_content(
                    [{"step_id": "s1", "need": "current_scene",
                      "tools": ["mongo"]}]
                ),
                "project-1",
            )

    def test_non_object_step_is_parse_error(self):
        """B1 sibling should-fire: a step that is not an object is rejected."""
        with self.assertRaises(SearchPlanParseError):
            parse_search_plan(_plan_content(["not-a-step"]), "project-1")

    def test_non_string_query_is_parse_error(self):
        """B2 should-fire: contract requires query to be a string."""
        with self.assertRaises(SearchPlanParseError):
            parse_search_plan(
                _plan_content(
                    [{"step_id": "s1", "need": "current_scene",
                      "tools": ["mongo"], "query": 123}]
                ),
                "project-1",
            )

    def test_present_empty_plan_id_is_parse_error(self):
        """B4 should-fire: an explicit empty plan_id is invalid, while an
        absent plan_id (test_plan_id_defaults_when_absent) is allowed."""
        content = json.dumps(
            {"plan_id": "", "steps": [
                {"step_id": "s1", "need": "current_scene",
                 "tools": ["mongo"], "query": "x"},
            ]}
        )
        with self.assertRaises(SearchPlanParseError):
            parse_search_plan(content, "project-1")

    def test_non_json_and_bad_shape_are_parse_errors(self):
        for content in ("```json\n{}\n```", "[]", '{"steps":"nope"}',
                        '{"steps":[{"step_id":"","need":"current_scene",'
                        '"tools":["mongo"],"query":"x"}]}',
                        '{"steps":[{"step_id":"s1","need":"current_scene",'
                        '"tools":[],"query":"x"}]}'):
            with self.subTest(content=content):
                with self.assertRaises(SearchPlanParseError):
                    parse_search_plan(content, "project-1")

    def test_fenced_valid_plan_is_extracted(self):
        # Under-strict: a whole-content markdown fence is stripped before
        # json.loads. Removing strip_code_fence re-fails with a JSON error.
        for tag in ("json", "", "text"):
            with self.subTest(tag=tag):
                plan = parse_search_plan(f"```{tag}\n{_plan_content()}\n```", "project-1")
                self.assertEqual(len(plan.steps), 2)

    def test_fence_does_not_weaken_object_check(self):
        # Over-strict: extraction unwraps format only — a fenced JSON array is
        # still rejected for the RIGHT reason (object check, not a coincidental
        # JSON error), exactly as an unfenced one.
        with self.assertRaisesRegex(
            SearchPlanParseError, "must be a JSON object"
        ):
            parse_search_plan("```json\n[]\n```", "project-1")


class TerminalJsonSearchPlannerTest(unittest.IsolatedAsyncioTestCase):
    async def test_valid_first_response_parses_without_repair(self):
        provider = FakeLLMProvider([_result(_plan_content())])
        plan = await _planner(provider).build_plan(_request())
        self.assertEqual(plan.project_id, "project-1")
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(len(provider.requests), 1)

    async def test_prompt_carries_template_and_request_payload(self):
        provider = FakeLLMProvider([_result(_plan_content())])
        await _planner(provider).build_plan(_request())
        messages = provider.requests[0].messages
        self.assertEqual(messages[0].content, CONTEXT_SEARCH_PLAN_TEMPLATE)
        payload = json.loads(messages[1].content)
        self.assertEqual(payload["project_id"], "project-1")
        self.assertEqual(payload["prompt_version"], CONTEXT_SEARCH_PLAN_PROMPT_VERSION)
        self.assertEqual(payload["task_type"], CONTEXT_SEARCH_PLAN_TASK_TYPE)
        needs = {entry["need"]: entry["allowed_tools"] for entry in payload["needs"]}
        self.assertEqual(needs["current_scene"], ["mongo"])
        self.assertEqual(needs["source_quote"], ["vector"])

    async def test_markdown_fenced_first_response_parses_without_repair(self):
        # Under-strict guard: parse_search_plan strips a whole-content markdown
        # fence before json.loads, so a fenced valid plan parses on the FIRST
        # call — no repair. Removing strip_code_fence forces a second request.
        provider = FakeLLMProvider(
            [_result("```json\n" + _plan_content() + "\n```")]
        )
        plan = await _planner(provider).build_plan(_request())
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(len(provider.requests), 1)

    async def test_invalid_literal_first_response_repairs_once(self):
        bad = _plan_content(
            [{"step_id": "s1", "need": "villain_arc",
              "tools": ["mongo"], "query": "x"}]
        )
        provider = FakeLLMProvider([_result(bad), _result(_plan_content())])
        plan = await _planner(provider).build_plan(_request())
        self.assertEqual(plan.steps[0].need, ContextNeed.CURRENT_SCENE)
        self.assertEqual(len(provider.requests), 2)

    async def test_repair_prompt_includes_parser_error_and_invalid_output(self):
        bad = "not json at all"
        provider = FakeLLMProvider([_result(bad), _result(_plan_content())])
        await _planner(provider).build_plan(_request())
        repair_payload = json.loads(provider.requests[1].messages[1].content)
        self.assertIn("planner content must be JSON", repair_payload["parser_error"])
        self.assertEqual(repair_payload["invalid_output"], bad)

    async def test_still_invalid_after_repair_maps_to_llm_error(self):
        bad = _plan_content(
            [{"step_id": "s1", "need": "villain_arc",
              "tools": ["mongo"], "query": "x"}]
        )
        provider = FakeLLMProvider([_result(bad), _result(bad)])
        with self.assertRaises(ContextSearchFailed) as caught:
            await _planner(provider).build_plan(_request())
        self.assertEqual(caught.exception.error_type, ContextSearchErrorType.LLM_ERROR)

    async def test_does_not_retry_more_than_once(self):
        provider = FakeLLMProvider([_result("garbage"), _result("still garbage")])
        with self.assertRaises(ContextSearchFailed):
            await _planner(provider).build_plan(_request())
        self.assertEqual(len(provider.requests), 2)

    async def test_missing_template_maps_to_llm_error(self):
        templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        planner = TerminalJsonSearchPlanner(
            FakeLLMProvider([_result(_plan_content())]),
            prompt_templates=templates,
        )
        with self.assertRaises(ContextSearchFailed) as caught:
            await planner.build_plan(_request())
        self.assertEqual(caught.exception.error_type, ContextSearchErrorType.LLM_ERROR)


if __name__ == "__main__":
    unittest.main()
