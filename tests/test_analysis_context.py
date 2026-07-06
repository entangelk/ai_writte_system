import unittest

from services.application.app.analysis.models import (
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.context_search.models import (
    AnalysisContextRequest,
    ContextItem,
    ContextItemStatus,
    ContextNeed,
    ContextPackage,
    ContextSearchPurpose,
    GATE_PASS,
    GATE_REJECT,
    PriorMemoryItem,
)
from services.application.app.context_search.prior_memory import (
    AnalysisContextService,
    DeterministicPriorMemoryBackend,
    InvalidAnalysisContextRequest,
    evaluate_analysis_context_gate,
)
from services.application.app.indexing.models import IndexPointer
from services.application.app.memory.models import (
    MemoryEntry,
    MemoryStatus,
    PromotionMode,
)
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryService,
)


CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION
EVENT = AnalysisCandidateType.EVENT_OBSERVATION


def _memory(
    *,
    memory_id: str,
    project_id: str = "project-1",
    memory_type: AnalysisCandidateType = CHARACTER,
    job_id: str = "job-A",
    candidate_id: str | None = None,
    payload=None,
    version: int = 1,
    source_ref_ids=("source-ref-1",),
    status: MemoryStatus = MemoryStatus.CANONICAL,
) -> MemoryEntry:
    return MemoryEntry(
        id=memory_id,
        project_id=project_id,
        memory_type=memory_type,
        status=status,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.5,
        source_ref_ids=source_ref_ids,
        payload=payload or {"name": "Ariel", "observation": "brave"},
        version=version,
        analysis_job_id=job_id,
        source_candidate_id=candidate_id or f"cand-{memory_id}",
        promotion_mode=PromotionMode.MANUAL,
        applied_threshold=None,
    )


def _service(*memories: MemoryEntry):
    repo = InMemoryMemoryRepository()
    for memory in memories:
        repo.put_memory(memory)
    backend = DeterministicPriorMemoryBackend(MemoryService(repo))
    return AnalysisContextService(backend=backend)


def _request(
    *,
    project_id: str = "project-1",
    memory_types=(CHARACTER,),
    exclude_job_id: str | None = None,
    needs=(ContextNeed.PRIOR_MEMORY,),
) -> AnalysisContextRequest:
    return AnalysisContextRequest(
        project_id=project_id,
        needs=needs,
        memory_types=memory_types,
        exclude_job_id=exclude_job_id,
    )


class PriorMemorySearchTest(unittest.TestCase):
    def test_returns_canonical_memories_of_requested_type_as_package(self):
        service = _service(
            _memory(memory_id="m1", memory_type=CHARACTER),
            _memory(memory_id="m2", memory_type=CHARACTER),
            _memory(memory_id="m3", memory_type=EVENT, payload={"event": "storm"}),
        )

        package = service.build_prior_memory_package(
            _request(memory_types=(CHARACTER,))
        )

        self.assertEqual(package.purpose, ContextSearchPurpose.ANALYSIS_CONTEXT)
        self.assertEqual(package.macro_items, ())
        self.assertEqual(package.micro_evidence, ())
        self.assertIsNone(package.trace)
        self.assertEqual(
            {item.memory_id for item in package.prior_memories}, {"m1", "m2"}
        )

    def test_superseded_memories_excluded_from_prior_memory(self):
        # 2B.2 O1, now testable: Phase 2B.4 introduced MemoryStatus.SUPERSEDED.
        # The canonical-only prior filter must exclude a superseded version and
        # keep the current canonical one (both directions in one case).
        service = _service(
            _memory(memory_id="old", memory_type=CHARACTER,
                    status=MemoryStatus.SUPERSEDED),
            _memory(memory_id="cur", memory_type=CHARACTER,
                    status=MemoryStatus.CANONICAL),
        )

        package = service.build_prior_memory_package(
            _request(memory_types=(CHARACTER,))
        )

        self.assertEqual(
            {item.memory_id for item in package.prior_memories}, {"cur"}
        )

    def test_prior_memory_item_carries_five_required_comparison_fields(self):
        payload = {"name": "Ariel", "observation": "brave"}
        service = _service(
            _memory(
                memory_id="m1",
                memory_type=CHARACTER,
                payload=payload,
                version=3,
                source_ref_ids=("sr-1", "sr-2"),
            )
        )

        item = service.build_prior_memory_package(
            _request(memory_types=(CHARACTER,))
        ).prior_memories[0]

        # value == MemoryEntry.payload (F3), plus status/source/version/reason.
        self.assertEqual(dict(item.value), payload)
        self.assertEqual(item.status, MemoryStatus.CANONICAL)
        self.assertEqual(item.version, 3)
        self.assertEqual(item.source_ref_ids, ("sr-1", "sr-2"))
        self.assertIn("character_observation", item.match_reason)
        self.assertEqual(item.memory_type, CHARACTER)

    def test_memory_type_filter_is_two_directional(self):
        service = _service(
            _memory(memory_id="m1", memory_type=CHARACTER),
            _memory(memory_id="m2", memory_type=EVENT, payload={"event": "storm"}),
        )

        chars = service.build_prior_memory_package(_request(memory_types=(CHARACTER,)))
        events = service.build_prior_memory_package(_request(memory_types=(EVENT,)))

        self.assertEqual([i.memory_id for i in chars.prior_memories], ["m1"])
        self.assertEqual([i.memory_id for i in events.prior_memories], ["m2"])

    def test_empty_memory_types_returns_empty_package_not_all(self):
        # A job with no candidates yields no comparison target: empty, never
        # the whole project memory.
        service = _service(
            _memory(memory_id="m1", memory_type=CHARACTER),
            _memory(memory_id="m2", memory_type=EVENT, payload={"event": "storm"}),
        )

        package = service.build_prior_memory_package(_request(memory_types=()))

        self.assertEqual(package.prior_memories, ())

    def test_self_exclusion_is_two_directional(self):
        service = _service(
            _memory(memory_id="own", memory_type=CHARACTER, job_id="job-A"),
            _memory(memory_id="prior", memory_type=CHARACTER, job_id="job-B"),
        )

        # F4: excluding job-A drops the memory job-A itself promoted.
        excluded = service.build_prior_memory_package(
            _request(memory_types=(CHARACTER,), exclude_job_id="job-A")
        )
        self.assertEqual([i.memory_id for i in excluded.prior_memories], ["prior"])

        # Over-strict guard: without exclusion both are returned (exclusion must
        # not drop unrelated jobs).
        both = service.build_prior_memory_package(
            _request(memory_types=(CHARACTER,), exclude_job_id=None)
        )
        self.assertEqual(
            {i.memory_id for i in both.prior_memories}, {"own", "prior"}
        )

    def test_lookup_is_project_scoped(self):
        service = _service(
            _memory(memory_id="mine", project_id="project-1", candidate_id="c1"),
            _memory(memory_id="other", project_id="project-2", candidate_id="c2"),
        )

        package = service.build_prior_memory_package(
            _request(project_id="project-1", memory_types=(CHARACTER,))
        )

        self.assertEqual([i.memory_id for i in package.prior_memories], ["mine"])


class AnalysisContextValidationTest(unittest.TestCase):
    def test_empty_needs_rejected(self):
        service = _service()
        with self.assertRaises(InvalidAnalysisContextRequest):
            service.build_prior_memory_package(_request(needs=()))

    def test_non_prior_memory_need_rejected(self):
        service = _service()
        with self.assertRaises(InvalidAnalysisContextRequest):
            service.build_prior_memory_package(
                _request(needs=(ContextNeed.CURRENT_SCENE,))
            )


def _writing_item() -> ContextItem:
    return ContextItem(
        need=ContextNeed.CURRENT_SCENE,
        status=ContextItemStatus.CANONICAL,
        text="leaked scene",
        pointer=IndexPointer(
            project_id="project-1",
            collection="source_blocks",
            document_id="block-1",
            version_id="v1",
            content_hash="hash",
        ),
        snapshot_id="snap-1",
        sot_reloaded=True,
        token_estimate=3,
    )


class AnalysisContextGateTest(unittest.TestCase):
    def test_gate_passes_prior_memory_only_package(self):
        service = _service(_memory(memory_id="m1", memory_type=CHARACTER))
        package = service.build_prior_memory_package(
            _request(memory_types=(CHARACTER,))
        )

        decision = evaluate_analysis_context_gate(
            package=package, request=_request(memory_types=(CHARACTER,))
        )

        self.assertEqual(decision.decision, GATE_PASS)
        self.assertEqual(decision.findings, ())

    def test_gate_rejects_writing_item_leak(self):
        # Reject direction; paired with test_gate_passes_prior_memory_only_package
        # (accept direction) this locks the Writing-leak invariant both ways.
        item = PriorMemoryItem(
            memory_id="m1",
            memory_type=CHARACTER,
            value={"name": "Ariel"},
            status=MemoryStatus.CANONICAL,
            version=1,
            source_ref_ids=(),
            match_reason="memory_type matches character_observation",
        )
        leaked = ContextPackage(
            project_id="project-1",
            purpose=ContextSearchPurpose.ANALYSIS_CONTEXT,
            macro_items=(_writing_item(),),
            micro_evidence=(),
            constraints=(),
            do_not_use=(),
            token_estimate_total=0,
            degraded=False,
            trace=None,
            prior_memories=(item,),
        )

        decision = evaluate_analysis_context_gate(
            package=leaked, request=_request(memory_types=(CHARACTER,))
        )

        self.assertEqual(decision.decision, GATE_REJECT)
        self.assertEqual(
            [f.check for f in decision.findings],
            ["writing_item_in_analysis_package"],
        )


if __name__ == "__main__":
    unittest.main()
