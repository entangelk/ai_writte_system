"""Phase 4 Slice 4.1 context search contract tests.

Locks the approved kickoff boundaries (docs/plans/
04-agentic-search-kickoff-decisions.md, SoT v1.6.30): SOT reload before use,
stale/project isolation, deterministic ranking/budget, degraded-mode error
taxonomy, and the independent Context Gate. Guards run in both directions:
should-fire branches re-fail if the check is dropped, and should-NOT-fire
branches fail if a normal package is wrongly rejected.
"""

import unittest

from services.application.app.context_search.models import (
    BUDGET_EXCLUDED_REASON,
    ContextBudget,
    ContextItemStatus,
    ContextNeed,
    ContextSearchErrorType,
    ContextSearchPurpose,
    ContextSearchRequest,
    CurrentPosition,
    GATE_PASS,
    GATE_REJECT,
    SearchPlan,
    SearchPlanStep,
    SearchTool,
)
from services.application.app.context_search.service import (
    ContextSearchBudgetExceeded,
    ContextSearchFailed,
    ContextSearchService,
    InvalidContextSearchRequest,
    estimate_tokens,
    evaluate_context_gate,
)
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.indexing.models import (
    IndexPointer,
    IndexRecordKind,
    SourceBlockIndexRecord,
)
from services.application.app.indexing.service import (
    DeterministicFakeEmbeddingProvider,
    InMemoryVectorIndexAdapter,
    SourceBlockIndexingService,
)

from dataclasses import replace


RAW_TEXT = (
    "# 1장\n\n"
    "아린은 항구에 도착했다.\n\n"
    "낡은 단검에는 검은 태양 문양이 새겨져 있었다.\n\n"
    "---\n\n"
    "밤이 되자 노스워치의 등불이 켜졌다.\n\n"
    "아린은 편지를 다시 읽었다."
)


class _StaticPlanner:
    def __init__(self, plan):
        self.plan = plan

    def build_plan(self, request):
        return self.plan


class _FailingPlanner:
    def build_plan(self, request):
        raise RuntimeError("provider unavailable")


class _AsyncStaticPlanner:
    """Async producer like the Slice 4.2 terminal-JSON planner."""

    def __init__(self, plan):
        self.plan = plan

    async def build_plan(self, request):
        return self.plan


class _FailingVectorSearchAdapter:
    def query_similar(self, *, project_id, vector, limit):
        raise RuntimeError("vector backend unavailable")


class _ToggleBackendSotRepository(InMemoryCoreSotRepository):
    """In-memory SOT repo that can simulate the backend going down for reads.

    While ``fail_reads`` is False it behaves normally (over-strict guard:
    healthy reloads must keep working); once True, every block read raises a
    raw non-CoreSotError exception like a real pymongo failure would.
    """

    def __init__(self):
        super().__init__()
        self.fail_reads = False

    def get_blocks(self, snapshot_id):
        if self.fail_reads:
            raise RuntimeError("simulated SOT backend down")
        return super().get_blocks(snapshot_id)


def _fixture(*, project_name="Novel", raw_text=RAW_TEXT, repository=None):
    core_sot = CoreSotService(repository or InMemoryCoreSotRepository())
    project = core_sot.create_project(name=project_name)
    draft = core_sot.create_draft(project_id=project.id, title="Episode 1")
    saved = core_sot.save_draft(
        project_id=project.id,
        draft_id=draft.id,
        raw_text=raw_text,
        idempotency_key=f"save-{project_name}",
    )
    vector_index = InMemoryVectorIndexAdapter()
    indexing = SourceBlockIndexingService(
        core_sot=core_sot,
        embeddings=DeterministicFakeEmbeddingProvider(),
        vector_index=vector_index,
    )
    indexing.rebuild_snapshot_source_block_index(
        project_id=project.id, snapshot_id=saved.snapshot.id
    )
    return core_sot, vector_index, indexing, {
        "project_id": project.id,
        "draft_id": draft.id,
        "version_id": saved.draft_version.id,
        "snapshot_id": saved.snapshot.id,
        "content_hash": saved.snapshot.content_hash,
        "blocks": saved.blocks,
    }


def _request(saved, *, needs, max_tokens=10_000, query="검은 태양 단검"):
    return ContextSearchRequest(
        project_id=saved["project_id"],
        purpose=ContextSearchPurpose.WRITING_CONTEXT,
        needs=needs,
        query=query,
        current_position=CurrentPosition(
            draft_id=saved["draft_id"], version_id=saved["version_id"]
        ),
        context_budget=ContextBudget(max_tokens=max_tokens),
    )


def _plan(saved, *, steps):
    return SearchPlan(
        plan_id="plan-1", project_id=saved["project_id"], steps=steps
    )


def _vector_step(*, step_id="step-1", need=ContextNeed.SOURCE_QUOTE, query="단검"):
    return SearchPlanStep(
        step_id=step_id, need=need, tools=(SearchTool.VECTOR,), query=query
    )


def _mongo_step(*, step_id="step-2", need=ContextNeed.CURRENT_SCENE):
    return SearchPlanStep(step_id=step_id, need=need, tools=(SearchTool.MONGO,), query="")


def _service(core_sot, vector_index, indexing, planner, **kwargs):
    return ContextSearchService(
        core_sot=core_sot,
        indexing_service=indexing,
        vector_search=vector_index,
        embeddings=DeterministicFakeEmbeddingProvider(),
        planner=planner,
        **kwargs,
    )


class ContextSearchPackageTest(unittest.IsolatedAsyncioTestCase):
    async def test_builds_package_with_sot_reloaded_canonical_items_and_trace(self):
        core_sot, vector_index, indexing, saved = _fixture()
        request = _request(
            saved, needs=(ContextNeed.CURRENT_SCENE, ContextNeed.SOURCE_QUOTE)
        )
        plan = _plan(saved, steps=(_mongo_step(), _vector_step()))
        service = _service(core_sot, vector_index, indexing, _StaticPlanner(plan))

        package = await service.build_context_package(request)

        self.assertEqual(package.project_id, saved["project_id"])
        self.assertEqual(package.status, "candidate")
        self.assertFalse(package.degraded)
        self.assertGreater(len(package.macro_items), 0)
        self.assertGreater(len(package.micro_evidence), 0)
        for item in package.macro_items + package.micro_evidence:
            self.assertTrue(item.sot_reloaded)
            self.assertIs(item.status, ContextItemStatus.CANONICAL)
            self.assertEqual(item.pointer.project_id, saved["project_id"])
            self.assertEqual(item.pointer.content_hash, saved["content_hash"])
        self.assertEqual(package.trace.plan.plan_id, "plan-1")
        self.assertEqual(len(package.trace.steps), 2)
        self.assertEqual(
            package.token_estimate_total,
            sum(
                item.token_estimate
                for item in package.macro_items + package.micro_evidence
            ),
        )

    async def test_async_planner_is_awaited_by_service(self):
        """S1 should-fire: an async planner (the Slice 4.2 terminal-JSON
        planner shape) must be awaited by build_context_package. Dropping the
        isawaitable/await step leaves a coroutine that fails _validate_plan, so
        this test re-fails."""
        core_sot, vector_index, indexing, saved = _fixture()
        request = _request(
            saved, needs=(ContextNeed.CURRENT_SCENE, ContextNeed.SOURCE_QUOTE)
        )
        plan = _plan(saved, steps=(_mongo_step(), _vector_step()))
        service = _service(
            core_sot, vector_index, indexing, _AsyncStaticPlanner(plan)
        )

        package = await service.build_context_package(request)

        self.assertEqual(package.trace.plan.plan_id, plan.plan_id)
        self.assertGreater(len(package.macro_items), 0)
        self.assertGreater(len(package.micro_evidence), 0)

    async def test_current_scene_is_paragraph_run_after_last_scene_boundary(self):
        core_sot, vector_index, indexing, saved = _fixture()
        request = _request(
            saved, needs=(ContextNeed.CURRENT_SCENE, ContextNeed.RECENT_SCENES)
        )
        plan = _plan(
            saved,
            steps=(
                _mongo_step(step_id="s1", need=ContextNeed.CURRENT_SCENE),
                _mongo_step(step_id="s2", need=ContextNeed.RECENT_SCENES),
            ),
        )
        service = _service(core_sot, vector_index, indexing, _StaticPlanner(plan))

        package = await service.build_context_package(request)

        current = [
            item.text
            for item in package.macro_items
            if item.need is ContextNeed.CURRENT_SCENE
        ]
        recent = [
            item.text
            for item in package.macro_items
            if item.need is ContextNeed.RECENT_SCENES
        ]
        self.assertEqual(
            current,
            ["밤이 되자 노스워치의 등불이 켜졌다.", "아린은 편지를 다시 읽었다."],
        )
        self.assertEqual(
            recent,
            [
                "아린은 항구에 도착했다.",
                "낡은 단검에는 검은 태양 문양이 새겨져 있었다.",
            ],
        )

    async def test_project_isolation_excludes_other_project_records(self):
        core_sot, vector_index, indexing, saved = _fixture()
        other_project = core_sot.create_project(name="Other")
        other_draft = core_sot.create_draft(
            project_id=other_project.id, title="Other Episode"
        )
        other_saved = core_sot.save_draft(
            project_id=other_project.id,
            draft_id=other_draft.id,
            raw_text="다른 프로젝트의 단검 이야기.",
            idempotency_key="save-other",
        )
        indexing.rebuild_snapshot_source_block_index(
            project_id=other_project.id, snapshot_id=other_saved.snapshot.id
        )
        request = _request(saved, needs=(ContextNeed.SOURCE_QUOTE,))
        plan = _plan(saved, steps=(_vector_step(),))
        service = _service(core_sot, vector_index, indexing, _StaticPlanner(plan))

        package = await service.build_context_package(request)

        self.assertGreater(len(package.micro_evidence), 0)
        for item in package.micro_evidence:
            self.assertEqual(item.pointer.project_id, saved["project_id"])
            self.assertNotIn("다른 프로젝트", item.text)

    async def test_stale_hits_after_archive_are_excluded_with_reason_in_trace(self):
        core_sot, vector_index, indexing, saved = _fixture()
        core_sot.archive_project(project_id=saved["project_id"])
        request = _request(saved, needs=(ContextNeed.SOURCE_QUOTE,))
        plan = _plan(saved, steps=(_vector_step(),))
        service = _service(core_sot, vector_index, indexing, _StaticPlanner(plan))

        package = await service.build_context_package(request)

        self.assertEqual(package.micro_evidence, ())
        step = package.trace.steps[0]
        self.assertGreater(step.hits_considered, 0)
        self.assertEqual(step.items_produced, 0)
        self.assertTrue(step.excluded)
        for excluded in step.excluded:
            self.assertIn("project_archived", excluded.reason)

    async def test_fresh_hits_are_not_wrongly_excluded_as_stale(self):
        core_sot, vector_index, indexing, saved = _fixture()
        request = _request(saved, needs=(ContextNeed.SOURCE_QUOTE,))
        plan = _plan(saved, steps=(_vector_step(),))
        service = _service(core_sot, vector_index, indexing, _StaticPlanner(plan))

        package = await service.build_context_package(request)

        step = package.trace.steps[0]
        self.assertEqual(step.excluded, ())
        self.assertEqual(step.items_produced, len(package.micro_evidence))

    async def test_missing_position_version_maps_to_sot_error(self):
        # Mongo direct path: a position that does not exist in the SOT is a
        # full sot_error failure (documented divergence from the vector
        # path's soft stale exclusion).
        core_sot, vector_index, indexing, saved = _fixture()
        request = ContextSearchRequest(
            project_id=saved["project_id"],
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            needs=(ContextNeed.CURRENT_SCENE,),
            query="",
            current_position=CurrentPosition(
                draft_id=saved["draft_id"], version_id="missing-version"
            ),
            context_budget=ContextBudget(max_tokens=100),
        )
        plan = _plan(saved, steps=(_mongo_step(),))
        service = _service(core_sot, vector_index, indexing, _StaticPlanner(plan))

        with self.assertRaises(ContextSearchFailed) as ctx:
            await service.build_context_package(request)
        self.assertIs(ctx.exception.error_type, ContextSearchErrorType.SOT_ERROR)

    async def test_mongo_position_backend_down_maps_to_sot_error_bidirectional(self):
        # Under-strict: with the sot_error mapping removed this re-fails as a
        # raw RuntimeError. Over-strict: the same request succeeds while the
        # backend is healthy.
        repo = _ToggleBackendSotRepository()
        core_sot, vector_index, indexing, saved = _fixture(repository=repo)
        request = _request(saved, needs=(ContextNeed.CURRENT_SCENE,))
        plan = _plan(saved, steps=(_mongo_step(),))
        service = _service(core_sot, vector_index, indexing, _StaticPlanner(plan))

        healthy = await service.build_context_package(request)
        self.assertGreater(len(healthy.macro_items), 0)

        repo.fail_reads = True
        with self.assertRaises(ContextSearchFailed) as ctx:
            await service.build_context_package(request)
        self.assertIs(ctx.exception.error_type, ContextSearchErrorType.SOT_ERROR)

    async def test_vector_hit_backend_down_maps_to_sot_error_not_degraded(self):
        # A backend failure during the stale-guard/SOT reload of a vector hit
        # is an sot_error full failure, not a degraded backend_error package.
        repo = _ToggleBackendSotRepository()
        core_sot, vector_index, indexing, saved = _fixture(repository=repo)
        request = _request(saved, needs=(ContextNeed.SOURCE_QUOTE,))
        plan = _plan(saved, steps=(_vector_step(),))
        service = _service(core_sot, vector_index, indexing, _StaticPlanner(plan))

        healthy = await service.build_context_package(request)
        self.assertGreater(len(healthy.micro_evidence), 0)

        repo.fail_reads = True
        with self.assertRaises(ContextSearchFailed) as ctx:
            await service.build_context_package(request)
        self.assertIs(ctx.exception.error_type, ContextSearchErrorType.SOT_ERROR)

    async def test_vector_hit_missing_snapshot_is_soft_excluded_not_failure(self):
        # Index drift (snapshot gone from the SOT) excludes the hit as stale
        # instead of failing the request or degrading the package.
        core_sot, vector_index, indexing, saved = _fixture()
        embeddings = DeterministicFakeEmbeddingProvider()
        ghost = SourceBlockIndexRecord(
            id=f"source-block:{saved['project_id']}:ghost-snapshot:ghost-block",
            kind=IndexRecordKind.SOURCE_BLOCK,
            pointer=IndexPointer(
                project_id=saved["project_id"],
                collection="source_blocks",
                document_id="ghost-block",
                version_id="ghost-version",
                content_hash="ghost-hash",
            ),
            snapshot_id="ghost-snapshot",
            draft_id=saved["draft_id"],
            block_id="ghost-block",
            block_index=0,
            text="유령 블록",
            vector=embeddings.embed("유령 블록"),
            project_archived=False,
            draft_archived=False,
        )
        vector_index.upsert_records((ghost,))
        request = _request(saved, needs=(ContextNeed.SOURCE_QUOTE,))
        plan = _plan(saved, steps=(_vector_step(),))
        service = _service(core_sot, vector_index, indexing, _StaticPlanner(plan))

        package = await service.build_context_package(request)

        self.assertFalse(package.degraded)
        self.assertGreater(len(package.micro_evidence), 0)
        step = package.trace.steps[0]
        ghost_exclusions = [
            excluded for excluded in step.excluded if excluded.record_id == ghost.id
        ]
        self.assertEqual(len(ghost_exclusions), 1)
        self.assertEqual(ghost_exclusions[0].reason, "snapshot_missing")

    async def test_budget_includes_high_priority_and_excludes_overflow_bidirectional(self):
        core_sot, vector_index, indexing, saved = _fixture()
        plan = _plan(
            saved,
            steps=(
                _mongo_step(step_id="s1", need=ContextNeed.CURRENT_SCENE),
                _vector_step(step_id="s2"),
            ),
        )
        service = _service(core_sot, vector_index, indexing, _StaticPlanner(plan))

        generous = await service.build_context_package(
            _request(
                saved,
                needs=(ContextNeed.CURRENT_SCENE, ContextNeed.SOURCE_QUOTE),
                max_tokens=10_000,
            )
        )
        self.assertEqual(generous.trace.budget_excluded, ())
        all_items = generous.macro_items + generous.micro_evidence
        first_estimate = all_items[0].token_estimate

        tight = await service.build_context_package(
            _request(
                saved,
                needs=(ContextNeed.CURRENT_SCENE, ContextNeed.SOURCE_QUOTE),
                max_tokens=first_estimate,
            )
        )
        tight_items = tight.macro_items + tight.micro_evidence
        self.assertEqual(len(tight_items), 1)
        self.assertIs(tight_items[0].need, ContextNeed.CURRENT_SCENE)
        self.assertTrue(tight.trace.budget_excluded)
        for excluded in tight.trace.budget_excluded:
            self.assertEqual(excluded.reason, BUDGET_EXCLUDED_REASON)
        self.assertLessEqual(tight.token_estimate_total, first_estimate)

    async def test_need_priority_order_drives_ranking_bidirectional(self):
        core_sot, vector_index, indexing, saved = _fixture()
        plan = _plan(
            saved,
            steps=(
                _vector_step(step_id="s1"),
                _mongo_step(step_id="s2", need=ContextNeed.CURRENT_SCENE),
            ),
        )
        service = _service(core_sot, vector_index, indexing, _StaticPlanner(plan))

        quote_first = await service.build_context_package(
            _request(
                saved,
                needs=(ContextNeed.SOURCE_QUOTE, ContextNeed.CURRENT_SCENE),
                max_tokens=2,
            )
        )
        included = quote_first.macro_items + quote_first.micro_evidence
        self.assertTrue(included)
        for item in included:
            self.assertIs(item.need, ContextNeed.SOURCE_QUOTE)

        scene_first = await service.build_context_package(
            _request(
                saved,
                needs=(ContextNeed.CURRENT_SCENE, ContextNeed.SOURCE_QUOTE),
                max_tokens=4,
            )
        )
        included = scene_first.macro_items + scene_first.micro_evidence
        self.assertTrue(included)
        for item in included:
            self.assertIs(item.need, ContextNeed.CURRENT_SCENE)

    async def test_vector_backend_failure_marks_degraded_with_error_taxonomy(self):
        core_sot, vector_index, indexing, saved = _fixture()
        plan = _plan(
            saved,
            steps=(
                _vector_step(step_id="s1"),
                _mongo_step(step_id="s2", need=ContextNeed.CURRENT_SCENE),
            ),
        )
        service = ContextSearchService(
            core_sot=core_sot,
            indexing_service=indexing,
            vector_search=_FailingVectorSearchAdapter(),
            embeddings=DeterministicFakeEmbeddingProvider(),
            planner=_StaticPlanner(plan),
        )
        request = _request(
            saved, needs=(ContextNeed.SOURCE_QUOTE, ContextNeed.CURRENT_SCENE)
        )

        package = await service.build_context_package(request)

        self.assertTrue(package.degraded)
        failed_step = package.trace.steps[0]
        self.assertIsNotNone(failed_step.failure)
        self.assertIs(
            failed_step.failure.error_type, ContextSearchErrorType.BACKEND_ERROR
        )
        self.assertGreater(len(package.macro_items), 0)

    async def test_successful_run_is_not_marked_degraded(self):
        core_sot, vector_index, indexing, saved = _fixture()
        plan = _plan(saved, steps=(_vector_step(),))
        service = _service(core_sot, vector_index, indexing, _StaticPlanner(plan))

        package = await service.build_context_package(
            _request(saved, needs=(ContextNeed.SOURCE_QUOTE,))
        )

        self.assertFalse(package.degraded)
        self.assertIsNone(package.trace.steps[0].failure)

    async def test_empty_result_step_is_explainable_in_trace(self):
        core_sot, vector_index, indexing, saved = _fixture()
        empty_index = InMemoryVectorIndexAdapter()
        plan = _plan(saved, steps=(_vector_step(),))
        service = ContextSearchService(
            core_sot=core_sot,
            indexing_service=indexing,
            vector_search=empty_index,
            embeddings=DeterministicFakeEmbeddingProvider(),
            planner=_StaticPlanner(plan),
        )

        package = await service.build_context_package(
            _request(saved, needs=(ContextNeed.SOURCE_QUOTE,))
        )

        self.assertEqual(package.micro_evidence, ())
        self.assertFalse(package.degraded)
        step = package.trace.steps[0]
        self.assertEqual(step.hits_considered, 0)
        self.assertEqual(step.items_produced, 0)
        self.assertIsNone(step.failure)

    async def test_planner_failure_maps_to_llm_error(self):
        core_sot, vector_index, indexing, saved = _fixture()
        service = _service(core_sot, vector_index, indexing, _FailingPlanner())

        with self.assertRaises(ContextSearchFailed) as ctx:
            await service.build_context_package(
                _request(saved, needs=(ContextNeed.SOURCE_QUOTE,))
            )
        self.assertIs(ctx.exception.error_type, ContextSearchErrorType.LLM_ERROR)

    async def test_plan_with_disallowed_tool_for_need_is_llm_error(self):
        core_sot, vector_index, indexing, saved = _fixture()
        bad_plan = _plan(
            saved,
            steps=(
                SearchPlanStep(
                    step_id="s1",
                    need=ContextNeed.CURRENT_SCENE,
                    tools=(SearchTool.VECTOR,),
                    query="",
                ),
            ),
        )
        service = _service(core_sot, vector_index, indexing, _StaticPlanner(bad_plan))

        with self.assertRaises(ContextSearchFailed) as ctx:
            await service.build_context_package(
                _request(saved, needs=(ContextNeed.CURRENT_SCENE,))
            )
        self.assertIs(ctx.exception.error_type, ContextSearchErrorType.LLM_ERROR)

    async def test_plan_for_other_project_or_unrequested_need_is_llm_error(self):
        core_sot, vector_index, indexing, saved = _fixture()
        service_cross = _service(
            core_sot,
            vector_index,
            indexing,
            _StaticPlanner(
                SearchPlan(
                    plan_id="plan-x",
                    project_id="project-other",
                    steps=(_vector_step(),),
                )
            ),
        )
        with self.assertRaises(ContextSearchFailed) as ctx:
            await service_cross.build_context_package(
                _request(saved, needs=(ContextNeed.SOURCE_QUOTE,))
            )
        self.assertIs(ctx.exception.error_type, ContextSearchErrorType.LLM_ERROR)

        service_unrequested = _service(
            core_sot,
            vector_index,
            indexing,
            _StaticPlanner(
                _plan(saved, steps=(_mongo_step(need=ContextNeed.CURRENT_SCENE),))
            ),
        )
        with self.assertRaises(ContextSearchFailed) as ctx:
            await service_unrequested.build_context_package(
                _request(saved, needs=(ContextNeed.SOURCE_QUOTE,))
            )
        self.assertIs(ctx.exception.error_type, ContextSearchErrorType.LLM_ERROR)

    async def test_wall_clock_budget_exceeded_raises_budget_error(self):
        core_sot, vector_index, indexing, saved = _fixture()
        ticks = iter([0.0, 100.0])
        plan = _plan(saved, steps=(_vector_step(),))
        service = _service(
            core_sot,
            vector_index,
            indexing,
            _StaticPlanner(plan),
            wall_clock_seconds=60,
            clock=lambda: next(ticks),
        )

        with self.assertRaises(ContextSearchBudgetExceeded):
            await service.build_context_package(
                _request(saved, needs=(ContextNeed.SOURCE_QUOTE,))
            )

    async def test_invalid_requests_are_rejected(self):
        core_sot, vector_index, indexing, saved = _fixture()
        plan = _plan(saved, steps=(_vector_step(),))
        service = _service(core_sot, vector_index, indexing, _StaticPlanner(plan))

        with self.assertRaises(InvalidContextSearchRequest):
            await service.build_context_package(
                ContextSearchRequest(
                    project_id=saved["project_id"],
                    purpose=ContextSearchPurpose.WRITING_CONTEXT,
                    needs=(),
                    query="q",
                    current_position=None,
                    context_budget=ContextBudget(max_tokens=100),
                )
            )
        with self.assertRaises(InvalidContextSearchRequest):
            await service.build_context_package(
                _request(saved, needs=(ContextNeed.SOURCE_QUOTE,), max_tokens=0)
            )
        with self.assertRaises(InvalidContextSearchRequest):
            await service.build_context_package(
                ContextSearchRequest(
                    project_id=saved["project_id"],
                    purpose=ContextSearchPurpose.WRITING_CONTEXT,
                    needs=(ContextNeed.CURRENT_SCENE,),
                    query="q",
                    current_position=None,
                    context_budget=ContextBudget(max_tokens=100),
                )
            )


class ContextGateTest(unittest.IsolatedAsyncioTestCase):
    async def _package(self, core_sot, vector_index, indexing, saved, **request_kwargs):
        request = _request(
            saved,
            needs=(ContextNeed.CURRENT_SCENE, ContextNeed.SOURCE_QUOTE),
            **request_kwargs,
        )
        plan = _plan(saved, steps=(_mongo_step(), _vector_step()))
        service = _service(core_sot, vector_index, indexing, _StaticPlanner(plan))
        return request, await service.build_context_package(request)

    async def test_gate_passes_normal_package(self):
        core_sot, vector_index, indexing, saved = _fixture()
        request, package = await self._package(core_sot, vector_index, indexing, saved)

        decision = evaluate_context_gate(
            package=package, request=request, core_sot=core_sot
        )

        self.assertEqual(decision.decision, GATE_PASS)
        self.assertEqual(decision.findings, ())

    async def test_gate_rejects_cross_project_item(self):
        core_sot, vector_index, indexing, saved = _fixture()
        request, package = await self._package(core_sot, vector_index, indexing, saved)
        leaked = replace(
            package.micro_evidence[0],
            pointer=replace(
                package.micro_evidence[0].pointer, project_id="project-other"
            ),
        )
        tampered = replace(
            package, micro_evidence=package.micro_evidence + (leaked,)
        )

        decision = evaluate_context_gate(
            package=tampered, request=request, core_sot=core_sot
        )

        self.assertEqual(decision.decision, GATE_REJECT)
        self.assertIn(
            "cross_project_item", [finding.check for finding in decision.findings]
        )

    async def test_gate_rejects_item_without_sot_reload(self):
        core_sot, vector_index, indexing, saved = _fixture()
        request, package = await self._package(core_sot, vector_index, indexing, saved)
        unreloaded = replace(package.micro_evidence[0], sot_reloaded=False)
        tampered = replace(package, micro_evidence=(unreloaded,))

        decision = evaluate_context_gate(
            package=tampered, request=request, core_sot=core_sot
        )

        self.assertEqual(decision.decision, GATE_REJECT)
        self.assertIn(
            "missing_sot_reload", [finding.check for finding in decision.findings]
        )

    async def test_gate_rejects_candidate_status_item_in_first_slice(self):
        core_sot, vector_index, indexing, saved = _fixture()
        request, package = await self._package(core_sot, vector_index, indexing, saved)
        candidate_item = replace(
            package.micro_evidence[0], status=ContextItemStatus.CANDIDATE
        )
        tampered = replace(package, micro_evidence=(candidate_item,))

        decision = evaluate_context_gate(
            package=tampered, request=request, core_sot=core_sot
        )

        self.assertEqual(decision.decision, GATE_REJECT)
        self.assertIn(
            "candidate_item_not_allowed",
            [finding.check for finding in decision.findings],
        )

    async def test_gate_rejects_stale_item_when_project_archived_after_build(self):
        core_sot, vector_index, indexing, saved = _fixture()
        request, package = await self._package(core_sot, vector_index, indexing, saved)
        core_sot.archive_project(project_id=saved["project_id"])

        decision = evaluate_context_gate(
            package=package, request=request, core_sot=core_sot
        )

        self.assertEqual(decision.decision, GATE_REJECT)
        self.assertIn(
            "stale_item", [finding.check for finding in decision.findings]
        )

    async def test_gate_backend_down_maps_to_sot_error(self):
        # The gate's own SOT re-verification keeps the sot_error lineage: a
        # backend failure must not become a pass or a misattributed reject.
        repo = _ToggleBackendSotRepository()
        core_sot, vector_index, indexing, saved = _fixture(repository=repo)
        request, package = await self._package(core_sot, vector_index, indexing, saved)

        repo.fail_reads = True
        with self.assertRaises(ContextSearchFailed) as ctx:
            evaluate_context_gate(
                package=package, request=request, core_sot=core_sot
            )
        self.assertIs(ctx.exception.error_type, ContextSearchErrorType.SOT_ERROR)

    async def test_gate_rejects_budget_violation(self):
        core_sot, vector_index, indexing, saved = _fixture()
        request, package = await self._package(core_sot, vector_index, indexing, saved)
        shrunk_request = ContextSearchRequest(
            project_id=request.project_id,
            purpose=request.purpose,
            needs=request.needs,
            query=request.query,
            current_position=request.current_position,
            context_budget=ContextBudget(max_tokens=1),
        )

        decision = evaluate_context_gate(
            package=package, request=shrunk_request, core_sot=core_sot
        )

        self.assertEqual(decision.decision, GATE_REJECT)
        self.assertIn(
            "budget_exceeded", [finding.check for finding in decision.findings]
        )


class TokenEstimateTest(unittest.TestCase):
    def test_estimate_is_deterministic_char_based_and_positive(self):
        self.assertEqual(estimate_tokens(""), 1)
        self.assertEqual(estimate_tokens("abcd"), 1)
        self.assertEqual(estimate_tokens("abcde"), 2)
        self.assertEqual(estimate_tokens("가" * 8), 2)


class VectorQuerySimilarTest(unittest.TestCase):
    def test_query_similar_is_project_scoped_and_bounded(self):
        core_sot, vector_index, indexing, saved = _fixture()
        embeddings = DeterministicFakeEmbeddingProvider()
        hits = vector_index.query_similar(
            project_id=saved["project_id"],
            vector=embeddings.embed("단검"),
            limit=2,
        )
        self.assertLessEqual(len(hits), 2)
        for hit in hits:
            self.assertEqual(hit.pointer.project_id, saved["project_id"])
        with self.assertRaises(ValueError):
            vector_index.query_similar(
                project_id=saved["project_id"],
                vector=embeddings.embed("단검"),
                limit=0,
            )


if __name__ == "__main__":
    unittest.main()
