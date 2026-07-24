"""Observability KPI phase — unit locks for the per-LLM-call audit foundation.

Brief ``docs/plans/observability-kpi-decisions.md`` (D1=B record, D2=C derived
gate score, D3=A minimal counts). This slice is the read-model foundation: the
record shape, the gate-quality derivation, and in-memory persistence. Mongo
adapter, call-site wiring, and the aggregation API are later increments.
"""

import unittest
from datetime import UTC, datetime

from services.application.app.observability.llm_call_audit import (
    InMemoryLlmCallAuditRepository,
    LlmCallAuditService,
    LlmCallOutcome,
    LlmCallSite,
    StoredLlmCall,
    _GATE_DECISION_QUALITY,
    gate_quality_score,
)
from services.application.app.writing.models import (
    WritingGateDecision,
    WritingGateResult,
)


def _gate(decision: WritingGateDecision) -> WritingGateResult:
    return WritingGateResult(
        request_id="req-1",
        project_id="p1",
        decision=decision,
        findings=(),
        checked_constraints=(),
        evaluated_by_model="fake",
    )


class GateQualityScoreTest(unittest.TestCase):
    def test_every_decision_literal_has_a_score(self):
        # Over-strict guard: a future WritingGateDecision member added without a
        # score entry fails here instead of KeyError-ing at runtime, forcing the
        # single-source-of-truth map to stay complete.
        self.assertEqual(
            set(WritingGateDecision), set(_GATE_DECISION_QUALITY)
        )

    def test_score_values_are_pinned_and_bounded(self):
        expected = {
            WritingGateDecision.PASS: 1.0,
            WritingGateDecision.NEEDS_USER_REVIEW: 0.6,
            WritingGateDecision.RETRIEVE_MORE: 0.5,
            WritingGateDecision.REVISE: 0.3,
            WritingGateDecision.BLOCK: 0.0,
        }
        for decision, want in expected.items():
            with self.subTest(decision=decision):
                score = gate_quality_score(_gate(decision))
                self.assertEqual(score, want)
                self.assertGreaterEqual(score, 0.0)
                self.assertLessEqual(score, 1.0)

    def test_score_ordering_reflects_writing_quality(self):
        # Semantic lock: a clean pass outranks a human-review borderline, which
        # outranks an inconclusive retrieve-more, which outranks a concrete
        # revise, which outranks an outright block. Guards against a future edit
        # that reshuffles the map into an incoherent order.
        self.assertGreater(
            gate_quality_score(_gate(WritingGateDecision.PASS)),
            gate_quality_score(_gate(WritingGateDecision.NEEDS_USER_REVIEW)),
        )
        self.assertGreater(
            gate_quality_score(_gate(WritingGateDecision.NEEDS_USER_REVIEW)),
            gate_quality_score(_gate(WritingGateDecision.RETRIEVE_MORE)),
        )
        self.assertGreater(
            gate_quality_score(_gate(WritingGateDecision.RETRIEVE_MORE)),
            gate_quality_score(_gate(WritingGateDecision.REVISE)),
        )
        self.assertGreater(
            gate_quality_score(_gate(WritingGateDecision.REVISE)),
            gate_quality_score(_gate(WritingGateDecision.BLOCK)),
        )


class LlmCallAuditServiceTest(unittest.TestCase):
    def _service(self, *, times=None):
        repo = InMemoryLlmCallAuditRepository()
        ticks = iter(times or ())

        def clock():
            try:
                return next(ticks)
            except StopIteration:
                return datetime(2026, 7, 24, tzinfo=UTC)

        ids = iter(f"llmc:{i}" for i in range(1, 100))
        return repo, LlmCallAuditService(
            repo, clock=clock, id_factory=lambda: next(ids)
        )

    def test_record_round_trips_every_field(self):
        _repo, service = self._service()
        stored = service.record(
            project_id="p1",
            call_site=LlmCallSite.WRITING_GATE,
            correlation_id="req-1",
            outcome=LlmCallOutcome.SUCCESS,
            model="claude-fake",
            decision="pass",
            gate_quality_score=1.0,
            total_tokens=321,
            latency_ms=1200,
        )
        self.assertIsInstance(stored, StoredLlmCall)

        [listed] = service.list_calls("p1")
        self.assertEqual(listed.id, "llmc:1")
        self.assertEqual(listed.call_site, "writing_gate")
        self.assertEqual(listed.correlation_id, "req-1")
        self.assertEqual(listed.outcome, "success")
        self.assertEqual(listed.model, "claude-fake")
        self.assertEqual(listed.decision, "pass")
        self.assertEqual(listed.gate_quality_score, 1.0)
        self.assertEqual(listed.total_tokens, 321)
        self.assertEqual(listed.latency_ms, 1200)
        self.assertIsNone(listed.error_type)

    def test_error_call_records_outcome_and_error_without_score(self):
        _repo, service = self._service()
        service.record(
            project_id="p1",
            call_site=LlmCallSite.QUERY_PLANNER,
            correlation_id="req-2",
            outcome=LlmCallOutcome.PROVIDER_ERROR,
            error_type="upstream_unavailable",
        )
        [listed] = service.list_calls("p1")
        self.assertEqual(listed.outcome, "provider_error")
        self.assertEqual(listed.error_type, "upstream_unavailable")
        self.assertIsNone(listed.decision)
        self.assertIsNone(listed.gate_quality_score)
        self.assertEqual(listed.total_tokens, 0)

    def test_list_is_newest_first_and_project_scoped(self):
        _repo, service = self._service(times=[
            datetime(2026, 7, 24, 10, 0, tzinfo=UTC),
            datetime(2026, 7, 24, 11, 0, tzinfo=UTC),
            datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        ])
        service.record(
            project_id="p1", call_site=LlmCallSite.WRITING_GENERATION,
            correlation_id="a", outcome=LlmCallOutcome.SUCCESS,
        )
        service.record(
            project_id="p2", call_site=LlmCallSite.WRITING_GENERATION,
            correlation_id="b", outcome=LlmCallOutcome.SUCCESS,
        )
        service.record(
            project_id="p1", call_site=LlmCallSite.WRITING_GATE,
            correlation_id="c", outcome=LlmCallOutcome.SUCCESS,
        )

        p1 = service.list_calls("p1")
        self.assertEqual([c.correlation_id for c in p1], ["c", "a"])
        self.assertEqual([c.correlation_id for c in service.list_calls("p2")], ["b"])


if __name__ == "__main__":
    unittest.main()
