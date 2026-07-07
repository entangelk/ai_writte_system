"""Writing canonical inclusion (⑤ §5 B) regressions.

Locks: the canonical_memory step surfaces canonical memories as micro evidence
with a memory pointer (never macro); the retriever returns canonical-only; the
Context Gate re-validates memory items against the memory store (present +
canonical) instead of a SOT snapshot; and the candidate prohibition stays. Guards
run both directions — a superseded/missing memory must reject, a canonical one
must pass.
"""

import asyncio
import unittest

from services.application.app.analysis.models import (
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.context_search.models import (
    ContextBudget,
    ContextItem,
    ContextItemStatus,
    ContextNeed,
    ContextPackage,
    ContextSearchErrorType,
    ContextSearchPurpose,
    ContextSearchRequest,
    GATE_PASS,
    GATE_REJECT,
    SearchPlan,
    SearchPlanStep,
    SearchTool,
)
from services.application.app.context_search.service import (
    ContextSearchService,
    MongoDirectCanonicalMemoryRetriever,
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
from services.application.app.memory.models import (
    MemoryEntry,
    MemoryStatus,
    PromotionMode,
)
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryService,
)


EVENT = AnalysisCandidateType.EVENT_OBSERVATION


class _StaticPlanner:
    def __init__(self, plan):
        self.plan = plan

    def build_plan(self, request):
        return self.plan


class _RaisingRetriever:
    """CanonicalMemoryRetriever whose retrieve() always raises.

    Simulates a memory-store failure (e.g. pymongo outage) so the canonical
    memory step's error mapping can be exercised end-to-end.
    """

    def retrieve(self, *, project_id, query, limit):
        raise RuntimeError("memory store unreachable")


def _memory(memory_id, *, payload, status=MemoryStatus.CANONICAL, version=1,
            project_id="project-1"):
    return MemoryEntry(
        id=memory_id,
        project_id=project_id,
        memory_type=EVENT,
        status=status,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.5,
        source_ref_ids=("s1",),
        payload=payload,
        version=version,
        analysis_job_id="job-1",
        source_candidate_id=f"c-{memory_id}",
        promotion_mode=PromotionMode.MANUAL,
        applied_threshold=None,
    )


def _service(memory_service, *, with_retriever=True, retriever=None):
    core_sot = CoreSotService(InMemoryCoreSotRepository())
    vector_index = InMemoryVectorIndexAdapter()
    indexing = SourceBlockIndexingService(
        core_sot=core_sot,
        embeddings=DeterministicFakeEmbeddingProvider(),
        vector_index=vector_index,
    )
    if retriever is not None:
        resolved_retriever = retriever
    elif with_retriever:
        resolved_retriever = MongoDirectCanonicalMemoryRetriever(memory_service)
    else:
        resolved_retriever = None
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
                        need=ContextNeed.CANONICAL_MEMORY,
                        tools=(SearchTool.MONGO,),
                        query="storm",
                    ),
                ),
            )
        ),
        canonical_memory_retriever=resolved_retriever,
    )


def _request():
    return ContextSearchRequest(
        project_id="project-1",
        purpose=ContextSearchPurpose.WRITING_CONTEXT,
        needs=(ContextNeed.CANONICAL_MEMORY,),
        query="storm",
        current_position=None,  # canonical_memory is micro, no position needed
        context_budget=ContextBudget(max_tokens=10_000),
    )


def _memory_item(memory_id, *, project_id="project-1", version=1,
                 status=ContextItemStatus.CANONICAL):
    return ContextItem(
        need=ContextNeed.CANONICAL_MEMORY,
        status=status,
        text="the storm hit",
        pointer=IndexPointer(
            project_id=project_id,
            collection=MEMORIES_COLLECTION,
            document_id=memory_id,
            version_id=str(version),
            content_hash="",
        ),
        snapshot_id="",
        sot_reloaded=True,
        token_estimate=4,
    )


class CanonicalMemoryStepTest(unittest.TestCase):
    def _seed(self):
        memory = MemoryService(InMemoryMemoryRepository())
        memory._repo.put_memory(_memory("m1", payload={"event": "the storm hit"}))
        memory._repo.put_memory(_memory("m2", payload={"event": "the calm after"}))
        memory._repo.put_memory(
            _memory("m3", payload={"event": "old"}, status=MemoryStatus.SUPERSEDED)
        )
        return memory

    def test_canonical_memory_lands_in_micro_with_memory_pointer(self):
        memory = self._seed()
        package = asyncio.run(_service(memory).build_context_package(_request()))
        # micro only — canonical_memory is not a MACRO need.
        self.assertEqual(package.macro_items, ())
        ids = {item.pointer.document_id for item in package.micro_evidence}
        self.assertEqual(ids, {"m1", "m2"})  # superseded m3 excluded by retriever
        item = package.micro_evidence[0]
        self.assertEqual(item.status, ContextItemStatus.CANONICAL)
        self.assertEqual(item.pointer.collection, MEMORIES_COLLECTION)
        self.assertEqual(item.pointer.version_id, "1")
        self.assertTrue(item.text)

    def test_unwired_retriever_yields_empty_without_failure(self):
        memory = self._seed()
        package = asyncio.run(
            _service(memory, with_retriever=False).build_context_package(_request())
        )
        self.assertEqual(package.micro_evidence, ())
        self.assertFalse(package.degraded)


class MongoDirectRetrieverTest(unittest.TestCase):
    def test_returns_canonical_only_and_respects_limit(self):
        memory = MemoryService(InMemoryMemoryRepository())
        memory._repo.put_memory(_memory("m1", payload={"event": "a"}))
        memory._repo.put_memory(
            _memory("m2", payload={"event": "b"}, status=MemoryStatus.SUPERSEDED)
        )
        memory._repo.put_memory(_memory("m3", payload={"event": "c"}))
        retriever = MongoDirectCanonicalMemoryRetriever(memory)
        got = retriever.retrieve(project_id="project-1", query="x", limit=1)
        self.assertEqual(len(got), 1)
        self.assertTrue(all(e.status is MemoryStatus.CANONICAL for e in got))
        all_got = retriever.retrieve(project_id="project-1", query="x", limit=10)
        self.assertEqual({e.id for e in all_got}, {"m1", "m3"})  # superseded excluded


class CanonicalMemoryGateTest(unittest.TestCase):
    def _memory_with(self, *entries):
        memory = MemoryService(InMemoryMemoryRepository())
        for entry in entries:
            memory._repo.put_memory(entry)
        return memory

    def test_canonical_memory_item_passes(self):
        memory = self._memory_with(_memory("m1", payload={"event": "the storm hit"}))
        package = ContextPackage(
            project_id="project-1",
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            macro_items=(),
            micro_evidence=(_memory_item("m1"),),
            constraints=(),
            do_not_use=(),
            token_estimate_total=4,
            degraded=False,
        )
        decision = evaluate_context_gate(
            package=package,
            request=_request(),
            core_sot=CoreSotService(InMemoryCoreSotRepository()),
            memory_service=memory,
        )
        self.assertEqual(decision.decision, GATE_PASS)

    def test_superseded_memory_item_is_rejected_stale(self):
        # under-strict guard: a memory superseded after packaging must reject.
        memory = self._memory_with(
            _memory("m1", payload={"event": "x"}, status=MemoryStatus.SUPERSEDED)
        )
        package = ContextPackage(
            project_id="project-1",
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            macro_items=(),
            micro_evidence=(_memory_item("m1"),),
            constraints=(),
            do_not_use=(),
            token_estimate_total=4,
            degraded=False,
        )
        decision = evaluate_context_gate(
            package=package,
            request=_request(),
            core_sot=CoreSotService(InMemoryCoreSotRepository()),
            memory_service=memory,
        )
        self.assertEqual(decision.decision, GATE_REJECT)
        self.assertTrue(
            any(f.check == "stale_item" for f in decision.findings)
        )

    def test_missing_memory_item_is_rejected_stale(self):
        memory = self._memory_with()  # empty store
        package = ContextPackage(
            project_id="project-1",
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            macro_items=(),
            micro_evidence=(_memory_item("ghost"),),
            constraints=(),
            do_not_use=(),
            token_estimate_total=4,
            degraded=False,
        )
        decision = evaluate_context_gate(
            package=package,
            request=_request(),
            core_sot=CoreSotService(InMemoryCoreSotRepository()),
            memory_service=memory,
        )
        self.assertEqual(decision.decision, GATE_REJECT)

    def test_memory_item_without_memory_service_is_rejected(self):
        package = ContextPackage(
            project_id="project-1",
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            macro_items=(),
            micro_evidence=(_memory_item("m1"),),
            constraints=(),
            do_not_use=(),
            token_estimate_total=4,
            degraded=False,
        )
        decision = evaluate_context_gate(
            package=package,
            request=_request(),
            core_sot=CoreSotService(InMemoryCoreSotRepository()),
            memory_service=None,
        )
        self.assertEqual(decision.decision, GATE_REJECT)
        self.assertTrue(
            any(f.check == "memory_gate_unconfigured" for f in decision.findings)
        )

    def test_candidate_status_memory_item_still_rejected(self):
        # The candidate prohibition is retained even for memory-collection items.
        memory = self._memory_with(_memory("m1", payload={"event": "x"}))
        package = ContextPackage(
            project_id="project-1",
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            macro_items=(),
            micro_evidence=(_memory_item("m1", status=ContextItemStatus.CANDIDATE),),
            constraints=(),
            do_not_use=(),
            token_estimate_total=4,
            degraded=False,
        )
        decision = evaluate_context_gate(
            package=package,
            request=_request(),
            core_sot=CoreSotService(InMemoryCoreSotRepository()),
            memory_service=memory,
        )
        self.assertEqual(decision.decision, GATE_REJECT)
        self.assertTrue(
            any(f.check == "candidate_item_not_allowed" for f in decision.findings)
        )


class CanonicalMemoryRetrieverFailureTest(unittest.TestCase):
    def test_retriever_failure_maps_to_backend_error_without_crashing(self):
        # Boundary cell #10 (⑤ §5 B verification): a failing canonical-memory
        # retriever must map to a BACKEND_ERROR step failure and degrade the
        # package, NOT crash the whole search. Guards run both directions —
        # removing the try/except (under-strict: exception propagates) or
        # failing to record BACKEND_ERROR (over-strict: silent/empty step)
        # both re-fail this test.
        memory = MemoryService(InMemoryMemoryRepository())
        service = _service(memory, retriever=_RaisingRetriever())
        package = asyncio.run(service.build_context_package(_request()))
        # over-strict: the failure is contained to the step; the package is
        # still built and marked degraded instead of raising.
        self.assertTrue(package.degraded)
        self.assertEqual(package.micro_evidence, ())
        # under-strict: the canonical_memory step records a BACKEND_ERROR.
        self.assertEqual(len(package.trace.steps), 1)
        step = package.trace.steps[0]
        self.assertEqual(step.need, ContextNeed.CANONICAL_MEMORY)
        self.assertIsNotNone(step.failure)
        self.assertEqual(
            step.failure.error_type, ContextSearchErrorType.BACKEND_ERROR
        )


if __name__ == "__main__":
    unittest.main()
