"""Writing candidate inclusion (⑤ §5 B follow-up) regressions.

Locks: the candidate_memory step surfaces needs_review candidates as micro
evidence labeled ``candidate`` with a candidate pointer + review_status (never
macro, never constraints/do_not_use — Phase 6 §62); the retriever returns
needs_review-only; the Context Gate allows candidate items ONLY through the
candidate origin, re-validating against the analysis store (present +
needs_review), and still rejects candidate-status items on any other origin.
Guards run both directions.
"""

import asyncio
import unittest
from types import SimpleNamespace

from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.analysis.service import (
    AnalysisService,
    InMemoryAnalysisRepository,
)
from services.application.app.context_search.models import (
    ContextBudget,
    ContextItem,
    ContextItemStatus,
    ContextNeed,
    ContextPackage,
    ContextSearchPurpose,
    ContextSearchRequest,
    GATE_PASS,
    GATE_REJECT,
    SearchPlan,
    SearchPlanStep,
    SearchTool,
)
from services.application.app.context_search.service import (
    CANDIDATES_COLLECTION,
    ContextSearchService,
    MongoDirectCandidateMemoryRetriever,
    evaluate_context_gate,
)
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.indexing.models import IndexPointer
from services.application.app.indexing.service import (
    MEMORIES_COLLECTION,
    DeterministicFakeEmbeddingProvider,
    InMemoryVectorIndexAdapter,
    SourceBlockIndexingService,
)


EVENT = AnalysisCandidateType.EVENT_OBSERVATION


class _StaticPlanner:
    def __init__(self, plan):
        self.plan = plan

    def build_plan(self, request):
        return self.plan


class _RaisingRetriever:
    """CandidateMemoryRetriever whose retrieve() always raises (store outage)."""

    def retrieve(self, *, project_id, query, limit):
        raise RuntimeError("analysis store unreachable")


class _PromotedResolver:
    """PromotedCandidateResolver stub: the given ids report as promoted."""

    def __init__(self, *promoted_ids):
        self._promoted = set(promoted_ids)

    def is_candidate_promoted(self, project_id, candidate_id):
        return candidate_id in self._promoted


class _RaisingResolver:
    """PromotedCandidateResolver whose lookup always raises (memory outage)."""

    def is_candidate_promoted(self, project_id, candidate_id):
        raise RuntimeError("memory store unreachable")


class _ProjectRecordingResolver:
    """PromotedCandidateResolver that reports promoted only for a given project
    and records every project_id it is queried with (locks the wiring passes the
    request's project_id, not a hardcoded/candidate-derived one)."""

    def __init__(self, promoted_project, *promoted_ids):
        self.seen_projects = []
        self._project = promoted_project
        self._ids = set(promoted_ids)

    def is_candidate_promoted(self, project_id, candidate_id):
        self.seen_projects.append(project_id)
        return project_id == self._project and candidate_id in self._ids


def _candidate(candidate_id, *, payload, status=AnalysisCandidateStatus.NEEDS_REVIEW,
               project_id="project-1", job_id="job-1"):
    return AnalysisCandidate(
        id=candidate_id,
        project_id=project_id,
        job_id=job_id,
        task_id="task-1",
        candidate_type=EVENT,
        action=AnalysisCandidateAction.CREATE,
        status=status,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.5,
        source_ref_ids=("s1",),
        payload=payload,
    )


def _analysis_with(*candidates):
    analysis = AnalysisService(InMemoryAnalysisRepository())
    for candidate in candidates:
        analysis._repo.put_candidate(candidate, logical_key=f"lk-{candidate.id}")
    return analysis


def _service(analysis, *, with_retriever=True, retriever=None,
             promoted_resolver=None):
    core_sot = CoreSotService(InMemoryCoreSotRepository())
    vector_index = InMemoryVectorIndexAdapter()
    indexing = SourceBlockIndexingService(
        core_sot=core_sot,
        embeddings=DeterministicFakeEmbeddingProvider(),
        vector_index=vector_index,
    )
    if retriever is not None:
        resolved = retriever
    elif with_retriever:
        resolved = MongoDirectCandidateMemoryRetriever(analysis)
    else:
        resolved = None
    return ContextSearchService(
        core_sot=core_sot,
        indexing_service=indexing,
        vector_search=vector_index,
        embeddings=DeterministicFakeEmbeddingProvider(),
        planner=_StaticPlanner(
            SearchPlan(
                plan_id="plan-1",
                project_id="project-1",
                steps=(
                    SearchPlanStep(
                        step_id="s1",
                        need=ContextNeed.CANDIDATE_MEMORY,
                        tools=(SearchTool.MONGO,),
                        query="storm",
                    ),
                ),
            )
        ),
        candidate_memory_retriever=resolved,
        promoted_candidate_resolver=promoted_resolver,
    )


def _request():
    return ContextSearchRequest(
        project_id="project-1",
        purpose=ContextSearchPurpose.WRITING_CONTEXT,
        needs=(ContextNeed.CANDIDATE_MEMORY,),
        query="storm",
        current_position=None,  # candidate_memory is micro, no position needed
        context_budget=ContextBudget(max_tokens=10_000),
    )


def _candidate_item(candidate_id, *, project_id="project-1",
                    status=ContextItemStatus.CANDIDATE,
                    collection=CANDIDATES_COLLECTION):
    return ContextItem(
        need=ContextNeed.CANDIDATE_MEMORY,
        status=status,
        text="the storm hit",
        pointer=IndexPointer(
            project_id=project_id,
            collection=collection,
            document_id=candidate_id,
            version_id="",
            content_hash="",
        ),
        snapshot_id="",
        sot_reloaded=True,
        token_estimate=4,
        review_status="needs_review",
    )


class CandidateMemoryStepTest(unittest.TestCase):
    def _seed(self):
        return _analysis_with(
            _candidate("c1", payload={"event": "the storm hit"}),
            _candidate("c2", payload={"event": "the calm after"}),
        )

    def test_candidate_lands_in_micro_labeled_with_candidate_pointer(self):
        analysis = self._seed()
        package = asyncio.run(_service(analysis).build_context_package(_request()))
        # micro only — candidate_memory is not a MACRO need, and candidates must
        # never become authoritative constraints/do_not_use (Phase 6 §62).
        self.assertEqual(package.macro_items, ())
        self.assertEqual(package.constraints, ())
        self.assertEqual(package.do_not_use, ())
        ids = {item.pointer.document_id for item in package.micro_evidence}
        self.assertEqual(ids, {"c1", "c2"})
        item = package.micro_evidence[0]
        self.assertEqual(item.status, ContextItemStatus.CANDIDATE)
        self.assertEqual(item.pointer.collection, CANDIDATES_COLLECTION)
        self.assertEqual(item.review_status, "needs_review")
        self.assertTrue(item.text)

    def test_candidate_memory_budget_counts_the_rendered_item_bidirectional(self):
        """후보 메모리 생산자도 렌더링 기준으로 회계한다.

        `tests/test_context_search.py`의 같은 이름 회귀는 **source-block 항목만** 구동하는
        픽스처라 이 생산자를 잠그지 못한다(실측: 그 픽스처의 8개 항목이 전부
        `source_blocks`). 생산자마다 포인터 모양이 달라(후보는 `version_id`·`content_hash`가 둘 다 비고 라벨이 `candidate (uncertain)`이다) 렌더링 비용도 다르므로,
        칸을 비워 두면 이 사이트만 조용히 `text`만 세는 상태로 돌아갈 수 있다.

        under-strict: 회계가 렌더링보다 작으면 예산이 창을 넘기는 프롬프트를 통과시킨다.
        over-strict: 회계가 2배를 넘으면 멀쩡한 항목이 예산에서 잘린다.
        """
        from services.application.app.context_search.service import estimate_tokens
        from services.application.app.writing.prompt import _format_item

        analysis = self._seed()
        package = asyncio.run(_service(analysis).build_context_package(_request()))
        items = package.macro_items + package.micro_evidence
        self.assertTrue(items)
        rendered = sum(
            estimate_tokens(_format_item(item, package, True)) for item in items
        )
        self.assertGreaterEqual(package.token_estimate_total, rendered)
        self.assertLessEqual(package.token_estimate_total, rendered * 2)

    def test_unwired_retriever_yields_empty_without_failure(self):
        analysis = self._seed()
        package = asyncio.run(
            _service(analysis, with_retriever=False).build_context_package(_request())
        )
        self.assertEqual(package.micro_evidence, ())
        self.assertFalse(package.degraded)

    def test_retriever_failure_maps_to_backend_error_without_crashing(self):
        # Mirrors the canonical cell #10 lock: a failing retriever degrades the
        # package with a BACKEND_ERROR step failure instead of crashing.
        analysis = _analysis_with()
        service = _service(analysis, retriever=_RaisingRetriever())
        package = asyncio.run(service.build_context_package(_request()))
        self.assertTrue(package.degraded)
        self.assertEqual(package.micro_evidence, ())
        self.assertEqual(len(package.trace.steps), 1)
        step = package.trace.steps[0]
        self.assertEqual(step.need, ContextNeed.CANDIDATE_MEMORY)
        self.assertIsNotNone(step.failure)
        self.assertEqual(step.failure.error_type.value, "backend_error")


class MongoDirectCandidateRetrieverTest(unittest.TestCase):
    def test_returns_needs_review_only_and_respects_limit(self):
        # A candidate whose status is no longer needs_review (Phase 6 confirmed/
        # rejected, simulated) must not be returned. Uses a fake status because
        # the enum currently only has needs_review.
        analysis = _analysis_with(
            _candidate("c1", payload={"event": "a"}),
            _candidate("c3", payload={"event": "c"}),
        )
        promoted = SimpleNamespace(
            id="c2", project_id="project-1", job_id="job-1", task_id="task-1",
            candidate_type=EVENT, action=AnalysisCandidateAction.CREATE,
            status=SimpleNamespace(value="confirmed"),
            provenance=AnalysisProvenance.SOURCE_OBSERVED, confidence=0.5,
            source_ref_ids=("s1",), payload={"event": "b"},
        )
        analysis._repo.put_candidate(promoted, logical_key="lk-c2")
        retriever = MongoDirectCandidateMemoryRetriever(analysis)
        got = retriever.retrieve(project_id="project-1", query="x", limit=1)
        self.assertEqual(len(got), 1)
        self.assertTrue(
            all(c.status is AnalysisCandidateStatus.NEEDS_REVIEW for c in got)
        )
        all_got = retriever.retrieve(project_id="project-1", query="x", limit=10)
        self.assertEqual({c.id for c in all_got}, {"c1", "c3"})  # confirmed excluded


class _PromotedCandidateAnalysis:
    """Analysis stub whose candidate is no longer needs_review (Phase 6 state)."""

    def get_candidate(self, *, project_id, candidate_id):
        return SimpleNamespace(status=SimpleNamespace(value="confirmed"))


class CandidateMemoryGateTest(unittest.TestCase):
    def _package(self, item):
        return ContextPackage(
            project_id="project-1",
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            macro_items=(),
            micro_evidence=(item,),
            constraints=(),
            do_not_use=(),
            token_estimate_total=4,
            degraded=False,
        )

    def _gate(self, item, analysis):
        return evaluate_context_gate(
            package=self._package(item),
            request=_request(),
            core_sot=CoreSotService(InMemoryCoreSotRepository()),
            analysis_service=analysis,
        )

    def test_needs_review_candidate_item_passes(self):
        analysis = _analysis_with(_candidate("c1", payload={"event": "the storm hit"}))
        decision = self._gate(_candidate_item("c1"), analysis)
        self.assertEqual(decision.decision, GATE_PASS)

    def test_missing_candidate_is_stale(self):
        analysis = _analysis_with()  # c1 absent (removed or cross-project)
        decision = self._gate(_candidate_item("c1"), analysis)
        self.assertEqual(decision.decision, GATE_REJECT)
        self.assertTrue(any(f.check == "stale_item" for f in decision.findings))

    def test_no_longer_needs_review_candidate_is_stale(self):
        # Over-strict forward-defense (Phase 6 confirmed/rejected): a candidate
        # that left needs_review must be rejected as stale, not surfaced as an
        # unreviewed candidate. Removing the status check re-fails this.
        decision = self._gate(_candidate_item("c1"), _PromotedCandidateAnalysis())
        self.assertEqual(decision.decision, GATE_REJECT)
        self.assertTrue(any(f.check == "stale_item" for f in decision.findings))

    def test_unconfigured_analysis_service_rejects(self):
        decision = self._gate(_candidate_item("c1"), None)
        self.assertEqual(decision.decision, GATE_REJECT)
        self.assertTrue(
            any(f.check == "candidate_gate_unconfigured" for f in decision.findings)
        )

    def test_candidate_status_on_non_candidate_origin_still_rejected(self):
        # The safety line is narrowed, not lifted: a candidate-status item that
        # does NOT come through the candidate origin (here a memory-collection
        # pointer) is still candidate_item_not_allowed. Over-strict guard.
        analysis = _analysis_with(_candidate("c1", payload={"event": "x"}))
        item = _candidate_item("c1", collection=MEMORIES_COLLECTION)
        decision = evaluate_context_gate(
            package=self._package(item),
            request=_request(),
            core_sot=CoreSotService(InMemoryCoreSotRepository()),
            analysis_service=analysis,
        )
        self.assertEqual(decision.decision, GATE_REJECT)
        self.assertTrue(
            any(f.check == "candidate_item_not_allowed" for f in decision.findings)
        )


class CanonicalCandidateDedupTest(unittest.TestCase):
    """(e) v1.6.60: a promoted candidate is suppressed from the candidate step
    (its canonical copy already grounds the knowledge), store-authoritative (D1),
    at retrieval time (D2). Guards run both directions. See
    docs/plans/04-canonical-candidate-dedup-decisions.md.
    """

    def _seed(self):
        return _analysis_with(
            _candidate("c1", payload={"event": "the storm hit"}),
            _candidate("c2", payload={"event": "the calm after"}),
        )

    def test_promoted_candidate_suppressed_and_traced(self):
        # under-strict: c1 promoted -> absent from micro, recorded as an
        # excluded hit with reason candidate_promoted. Removing the suppression
        # re-fails this (c1 would reappear in micro and excluded would be empty).
        analysis = _analysis_with(_candidate("c1", payload={"event": "storm"}))
        service = _service(analysis, promoted_resolver=_PromotedResolver("c1"))
        package = asyncio.run(service.build_context_package(_request()))
        self.assertEqual(package.micro_evidence, ())
        self.assertFalse(package.degraded)
        step = package.trace.steps[0]
        self.assertEqual(step.hits_considered, 1)
        self.assertEqual(step.items_produced, 0)
        self.assertEqual(len(step.excluded), 1)
        self.assertEqual(step.excluded[0].record_id, "c1")
        self.assertEqual(step.excluded[0].reason, "candidate_promoted")

    def test_mixed_only_suppresses_promoted(self):
        # both directions: c1 promoted is dropped, c2 (needs_review, not promoted)
        # survives. A too-broad suppression (dropping c2) or a too-narrow one
        # (keeping c1) both fail this.
        analysis = self._seed()
        service = _service(analysis, promoted_resolver=_PromotedResolver("c1"))
        package = asyncio.run(service.build_context_package(_request()))
        ids = {item.pointer.document_id for item in package.micro_evidence}
        self.assertEqual(ids, {"c2"})
        step = package.trace.steps[0]
        self.assertEqual(step.hits_considered, 2)
        self.assertEqual(step.items_produced, 1)
        self.assertEqual({h.record_id for h in step.excluded}, {"c1"})

    def test_all_candidates_promoted_all_suppressed(self):
        # N>1 boundary (independent review I1): when EVERY candidate is promoted,
        # ALL are suppressed — the loop has no early-stop and drops the whole set,
        # not just the first. A mutation that stops after the first suppression
        # (break/candidates[0]) leaves c2 in micro and re-fails this.
        analysis = self._seed()
        service = _service(
            analysis, promoted_resolver=_PromotedResolver("c1", "c2")
        )
        package = asyncio.run(service.build_context_package(_request()))
        self.assertEqual(package.micro_evidence, ())
        step = package.trace.steps[0]
        self.assertEqual(step.hits_considered, 2)
        self.assertEqual(step.items_produced, 0)
        self.assertEqual(
            {h.record_id for h in step.excluded}, {"c1", "c2"}
        )
        self.assertTrue(
            all(h.reason == "candidate_promoted" for h in step.excluded)
        )

    def test_resolver_is_queried_with_request_project_id(self):
        # Wiring lock (independent review I2): the suppression check is scoped to
        # the request's project_id. A resolver that only promotes for a DIFFERENT
        # project must not suppress c1 here, and every query it sees is project-1.
        # Guards against passing a hardcoded/candidate-derived project.
        analysis = _analysis_with(_candidate("c1", payload={"event": "storm"}))
        resolver = _ProjectRecordingResolver("project-2", "c1")
        service = _service(analysis, promoted_resolver=resolver)
        package = asyncio.run(service.build_context_package(_request()))
        ids = {item.pointer.document_id for item in package.micro_evidence}
        self.assertEqual(ids, {"c1"})  # not suppressed: wrong project in resolver
        self.assertEqual(package.trace.steps[0].excluded, ())
        self.assertEqual(set(resolver.seen_projects), {"project-1"})

    def test_no_candidate_promoted_keeps_all(self):
        # over-strict: resolver reports nothing promoted -> both surface, none
        # excluded. A candidate is never dropped just because a resolver is wired.
        analysis = self._seed()
        service = _service(analysis, promoted_resolver=_PromotedResolver())
        package = asyncio.run(service.build_context_package(_request()))
        ids = {item.pointer.document_id for item in package.micro_evidence}
        self.assertEqual(ids, {"c1", "c2"})
        self.assertEqual(package.trace.steps[0].excluded, ())

    def test_no_resolver_is_prior_d7_behavior(self):
        # over-strict backward-compat: with no resolver wired, suppression is
        # inert even for an id that would be promoted -> both surface (prior D7).
        analysis = self._seed()
        service = _service(analysis)  # promoted_resolver defaults to None
        package = asyncio.run(service.build_context_package(_request()))
        ids = {item.pointer.document_id for item in package.micro_evidence}
        self.assertEqual(ids, {"c1", "c2"})
        self.assertEqual(package.trace.steps[0].excluded, ())

    def test_resolver_failure_degrades_to_backend_error(self):
        # A resolver outage folds into the candidate step's backend_error degrade
        # (honest degrade, not a silent pass-through).
        analysis = _analysis_with(_candidate("c1", payload={"event": "storm"}))
        service = _service(analysis, promoted_resolver=_RaisingResolver())
        package = asyncio.run(service.build_context_package(_request()))
        self.assertTrue(package.degraded)
        self.assertEqual(package.micro_evidence, ())
        step = package.trace.steps[0]
        self.assertIsNotNone(step.failure)
        self.assertEqual(step.failure.error_type.value, "backend_error")


if __name__ == "__main__":
    unittest.main()
