"""Phase 5.8 targeted retrieve_more lifecycle regression guards."""

import asyncio
import json
import unittest
from dataclasses import replace

from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository,
    PromptTemplateService,
)
from services.application.app.context_search.models import (
    ContextBudget,
    ContextItem,
    ContextItemStatus,
    ContextNeed,
    ContextPackage,
    ContextSearchPurpose,
    CurrentPosition,
)
from services.application.app.indexing.models import IndexPointer
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
from services.application.app.writing.retrieval import (
    InvalidWritingRetrievalPlan,
    TerminalJsonWritingRetrievalPlanner,
    WritingRetrievalPlan,
    merge_context_packages,
    parse_writing_retrieval_plan,
    seed_writing_retrieval_template,
)
from services.application.app.writing.revise_gate import (
    WritingLoopPolicy,
    WritingReviseGateService,
)
from services.llm_gateway.app.provider import GenerationResult, TokenUsage


def _pointer(document_id):
    return IndexPointer("p1", "source_blocks", document_id, "v1", "hash")


def _item(document_id, need, tokens, text=None):
    return ContextItem(
        need=need,
        status=ContextItemStatus.CANONICAL,
        text=text or document_id,
        pointer=_pointer(document_id),
        snapshot_id="s1",
        sot_reloaded=True,
        token_estimate=tokens,
    )


def _package(*, macro=(), micro=(), tokens=None):
    all_items = macro + micro
    return ContextPackage(
        "p1", ContextSearchPurpose.WRITING_CONTEXT, macro, micro, (), (),
        sum(item.token_estimate for item in all_items) if tokens is None else tokens,
        False,
    )


def _candidate():
    return WritingCandidate(
        "r1", "p1", WritingTaskType.CONTINUE_SCENE,
        WritingOutputType.DRAFT_PATCH, "새 문장",
    )


def _retrieve_finding():
    return WritingGateFinding(
        WritingGateFindingType.CONTINUITY,
        WritingGateSeverity.WARNING,
        "이 사건의 정본 근거가 부족함",
        "새 문장",
        WritingGateDecision.RETRIEVE_MORE,
    )


class _Provider:
    def __init__(self, contents):
        self.contents = list(contents)
        self.calls = 0
        self.last_request = None

    async def generate(self, request):
        self.calls += 1
        self.last_request = request
        return GenerationResult(
            "fake-retrieval-planner", self.contents.pop(0), "stop",
            TokenUsage(1, 1),
        )


class WritingRetrievalPlannerTest(unittest.TestCase):
    def test_strict_plan_accepts_canonical_subset(self):
        plan = parse_writing_retrieval_plan(json.dumps({
            "query": "검은 태양 사건의 선행 장면",
            "needs": ["event_context", "source_quote"],
        }))
        self.assertEqual(plan.query, "검은 태양 사건의 선행 장면")
        self.assertEqual(
            plan.needs, (ContextNeed.EVENT_CONTEXT, ContextNeed.SOURCE_QUOTE)
        )

    def test_empty_duplicate_candidate_or_unknown_needs_are_rejected(self):
        cases = (
            {"query": "q", "needs": []},
            {"query": "q", "needs": ["source_quote", "source_quote"]},
            {"query": "q", "needs": ["candidate_memory"]},
            {"query": "q", "needs": ["villain_arc"]},
            {"query": " ", "needs": ["source_quote"]},
        )
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(
                InvalidWritingRetrievalPlan
            ):
                parse_writing_retrieval_plan(json.dumps(payload))

    def test_planner_sees_all_retrieve_findings_and_allowed_needs(self):
        provider = _Provider((json.dumps({
            "query": "선행 사건",
            "needs": ["event_context"],
        }),))
        templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        seed_writing_retrieval_template(templates)
        planner = TerminalJsonWritingRetrievalPlanner(
            provider, prompt_templates=templates
        )
        second = replace(_retrieve_finding(), message="인물 상태 근거도 부족함")
        gate = WritingGateResult(
            "r1", "p1", WritingGateDecision.RETRIEVE_MORE,
            (_retrieve_finding(), second), (), "first-gate",
        )

        plan = asyncio.run(planner.plan(
            request=WritingRequest(
                "r1", "p1", WritingTaskType.CONTINUE_SCENE, "계속 써줘"
            ),
            candidate=_candidate(),
            gate=gate,
        ))

        self.assertEqual(plan.needs, (ContextNeed.EVENT_CONTEXT,))
        payload = json.loads(provider.last_request.messages[1].content)
        self.assertEqual(len(payload["retrieve_more_findings"]), 2)
        self.assertNotIn("candidate_memory", payload["allowed_needs"])

    def test_planner_repairs_position_need_when_position_is_absent(self):
        provider = _Provider((
            json.dumps({"query": "현재 장면", "needs": ["current_scene"]}),
            json.dumps({"query": "선행 사건", "needs": ["event_context"]}),
        ))
        templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        seed_writing_retrieval_template(templates)
        planner = TerminalJsonWritingRetrievalPlanner(
            provider, prompt_templates=templates
        )
        gate = WritingGateResult(
            "r1", "p1", WritingGateDecision.RETRIEVE_MORE,
            (_retrieve_finding(),), (), "first-gate",
        )

        plan = asyncio.run(planner.plan(
            request=WritingRequest(
                "r1", "p1", WritingTaskType.CONTINUE_SCENE, "계속 써줘"
            ), candidate=_candidate(), gate=gate, current_position=None,
        ))

        self.assertEqual(plan.needs, (ContextNeed.EVENT_CONTEXT,))
        self.assertEqual(provider.calls, 2)


class MergeContextPackagesTest(unittest.TestCase):
    def test_delta_is_prioritized_deduplicated_and_rebudgeted(self):
        base = _package(
            macro=(_item("current", ContextNeed.CURRENT_SCENE, 3),),
            micro=(_item("shared", ContextNeed.CANONICAL_MEMORY, 3),),
        )
        delta = _package(micro=(
            _item("shared", ContextNeed.SOURCE_QUOTE, 3, "new duplicate"),
            _item("missing", ContextNeed.EVENT_CONTEXT, 4),
        ))

        merged = merge_context_packages(base, delta, max_tokens=7)

        # Under-strict: the targeted missing evidence survives the global budget.
        self.assertEqual(
            [item.pointer.document_id for item in merged.micro_evidence],
            ["shared", "missing"],
        )
        # Over-strict: duplicate pointer is represented once and old context is
        # retained when budget remains; current is evicted only by the global cap.
        self.assertEqual(merged.macro_items, ())
        self.assertEqual(merged.token_estimate_total, 7)


class _Reviser:
    async def revise(self, *, candidate, finding, instruction, package):
        return replace(candidate, text="수정된 문장")


class _Reporter:
    def __init__(self):
        self.calls = 0

    async def enrich(self, candidate, package):
        self.calls += 1
        return replace(candidate, candidate_claims=(CandidateClaim(
            "최신 report", CandidateClaimType.NARRATIVE_EVENT, True
        ),))


class _Gate:
    def __init__(self):
        self.calls = []

    async def evaluate(self, *, request, candidate, package):
        self.calls.append((candidate, package))
        if len(self.calls) == 1:
            return WritingGateResult(
                "r1", "p1", WritingGateDecision.RETRIEVE_MORE,
                (_retrieve_finding(),), (), "first-gate",
            )
        return WritingGateResult(
            "r1", "p1", WritingGateDecision.PASS, (), (), "second-gate"
        )


class _RetrievalPlanner:
    def __init__(self):
        self.calls = 0

    async def plan(self, *, request, candidate, gate, current_position=None):
        self.calls += 1
        return WritingRetrievalPlan(
            query="부족한 사건 근거", needs=(ContextNeed.EVENT_CONTEXT,)
        )


class _ContextSearch:
    def __init__(self):
        self.calls = 0
        self.request = None

    async def build_context_package(self, request):
        self.calls += 1
        self.request = request
        return _package(micro=(
            _item("missing", ContextNeed.EVENT_CONTEXT, 2),
        ))


class WritingRetrieveLifecycleTest(unittest.TestCase):
    def test_retrieve_more_plans_merges_and_regates_without_rereport(self):
        reporter = _Reporter()
        gate = _Gate()
        planner = _RetrievalPlanner()
        context = _ContextSearch()
        service = WritingReviseGateService(
            reviser=_Reviser(), reporter=reporter, gate=gate,
            retrieval_planner=planner, context_search=context,
            policy=WritingLoopPolicy(max_retrieval_rounds=1),
        )

        result = asyncio.run(service.run(
            request=WritingRequest(
                "r1", "p1", WritingTaskType.CONTINUE_SCENE, "계속 써줘"
            ),
            candidate=_candidate(),
            finding=replace(
                _retrieve_finding(), recommended_decision=WritingGateDecision.REVISE
            ),
            package=_package(macro=(
                _item("current", ContextNeed.CURRENT_SCENE, 2),
            )),
            current_position=CurrentPosition("d1", "v1"),
            context_budget=ContextBudget(10),
        ))

        self.assertEqual(result.gate.decision, WritingGateDecision.PASS)
        self.assertEqual(reporter.calls, 1)
        self.assertEqual(planner.calls, 1)
        self.assertEqual(context.calls, 1)
        self.assertEqual(context.request.needs, (ContextNeed.EVENT_CONTEXT,))
        self.assertEqual(context.request.query, "부족한 사건 근거")
        self.assertEqual(len(gate.calls), 2)
        self.assertEqual(
            gate.calls[1][0].candidate_claims[0].text, "최신 report"
        )
        self.assertEqual(
            {item.pointer.document_id for item in (
                gate.calls[1][1].macro_items + gate.calls[1][1].micro_evidence
            )},
            {"current", "missing"},
        )

    def test_non_retrieve_and_second_retrieve_both_stop(self):
        class _AlwaysRetrieve(_Gate):
            async def evaluate(self, *, request, candidate, package):
                self.calls.append((candidate, package))
                return WritingGateResult(
                    "r1", "p1", WritingGateDecision.RETRIEVE_MORE,
                    (_retrieve_finding(),), (), "gate",
                )

        reporter = _Reporter()
        gate = _AlwaysRetrieve()
        planner = _RetrievalPlanner()
        context = _ContextSearch()
        service = WritingReviseGateService(
            reviser=_Reviser(), reporter=reporter, gate=gate,
            retrieval_planner=planner, context_search=context,
            policy=WritingLoopPolicy(max_retrieval_rounds=1),
        )
        result = asyncio.run(service.run(
            request=WritingRequest(
                "r1", "p1", WritingTaskType.CONTINUE_SCENE, "계속 써줘"
            ), candidate=_candidate(),
            finding=replace(
                _retrieve_finding(), recommended_decision=WritingGateDecision.REVISE
            ), package=_package(), current_position=None,
            context_budget=ContextBudget(10),
        ))
        self.assertEqual(result.gate.decision, WritingGateDecision.RETRIEVE_MORE)
        self.assertEqual(len(gate.calls), 2)
        self.assertEqual(planner.calls, 1)
        self.assertEqual(context.calls, 1)
