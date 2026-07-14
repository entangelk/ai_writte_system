"""Phase 5.10 ("B2 increment") — Writing loop aggregate token/wall-clock budget.

Locks the owner-approved bundle M1=A (plumbing + configurable enforcement now,
calibrated numbers as B2b), M2=A (total-token + wall-clock dimensions), M3=A
(usage on the internal return; public envelope unchanged), M4=A (post-accounting
token / monotonic deadline mirror of flat-loop-gate), M5=A (aggregate on the
persisted audit only), M6=A (off by default). Both directions of each guard.
"""

import asyncio
import unittest
from unittest.mock import patch

from services.application.app.context_search.models import ContextBudget
from services.application.app.writing.models import (
    WritingRequest,
    WritingGateDecision,
    WritingTaskType,
)
from services.application.app.writing.revise_gate import (
    WritingLoopPolicy,
    WritingLoopStatus,
    WritingReviseGateFailure,
    WritingReviseReportFailure,
    WritingReviseGateService,
)
from services.application.app.writing.metering import MeteredCallError
from services.application.app.writing.report import InvalidCandidateReport
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.provider import TokenUsage

from tests.test_writing_revise import (
    _Gate,
    _LoopGate,
    _Provider,
    _Reporter,
    _RetrievalPlanner,
    _SequenceProvider,
    _Context,
    _candidate,
    _finding,
    _http,
    _package,
    _service,
    _Client,
)


def _request(project_id="p1"):
    return WritingRequest(
        "r1", project_id, WritingTaskType.CONTINUE_SCENE, "연속성을 고쳐줘"
    )


class _AdvancingClock:
    """Monotonic-seconds double: first call is the loop start, all later calls
    return ``then`` — so a single injected value controls the measured elapsed."""

    def __init__(self, *, first=0.0, then):
        self._first = first
        self._then = then
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self._first if self.calls == 1 else self._then


class _SequenceClock:
    def __init__(self, *values):
        self._values = list(values)
        self._last = values[-1]

    def __call__(self):
        if self._values:
            self._last = self._values.pop(0)
        return self._last


class _MeteredReporter(_Reporter):
    def __init__(self, *, usage, error=None):
        super().__init__(error=error)
        self._usage = usage

    async def enrich_metered(self, candidate, package):
        return await self.enrich(candidate, package), self._usage


class _FailedMeteredReporter(_Reporter):
    async def enrich_metered(self, candidate, package):
        self.calls += 1
        raise MeteredCallError(
            InvalidCandidateReport("bad report"), TokenUsage(0, 3)
        )


class _MeteredLoopGate(_LoopGate):
    def __init__(self, decisions, *, usage, revise_evidence="고친 문장."):
        super().__init__(decisions, revise_evidence=revise_evidence)
        self._usage = usage

    async def evaluate_metered(self, *, request, candidate, package):
        result = await self.evaluate(
            request=request, candidate=candidate, package=package
        )
        return result, self._usage


class _MeteredRetrievalPlanner(_RetrievalPlanner):
    def __init__(self, *, usage):
        super().__init__()
        self._usage = usage

    async def plan_metered(self, *, request, candidate, gate,
                           current_position=None):
        plan = await self.plan(
            request=request, candidate=candidate, gate=gate,
            current_position=current_position,
        )
        return plan, self._usage


class _MeteredContext(_Context):
    """A context search that WOULD surface provider usage via a _metered variant.

    The loop calls the bare build_context_package directly (revise_gate.py), so
    this variant stays dormant and its usage never enters the aggregate. It is a
    tripwire: if the loop is ever changed to route context_search through
    metered(), metered() picks up build_context_package_metered and its usage
    inflates total_tokens — caught by the excluded-from-aggregate test.
    """

    def __init__(self, package, *, usage):
        super().__init__(package)
        self._usage = usage
        self.metered_calls = 0

    async def build_context_package_metered(self, request):
        self.metered_calls += 1
        return await self.build_context_package(request), self._usage


def _build(*, reviser_provider, gate, reporter, policy, clock=None,
           retrieval_planner=None, context_search=None):
    return WritingReviseGateService(
        reviser=_service(reviser_provider), reporter=reporter, gate=gate,
        policy=policy, clock=clock, retrieval_planner=retrieval_planner,
        context_search=context_search,
    )


def _run(service):
    return asyncio.run(service.run(
        request=_request(), candidate=_candidate(), finding=_finding(),
        package=_package(), context_budget=ContextBudget(max_tokens=100),
    ))


class WritingLoopPolicyBudgetTest(unittest.TestCase):
    def test_rejects_nonpositive_aggregate_caps(self):
        with self.assertRaises(ValueError):
            WritingLoopPolicy(max_total_tokens=0)
        with self.assertRaises(ValueError):
            WritingLoopPolicy(max_wall_clock_ms=0)

    def test_none_and_positive_caps_are_accepted(self):
        default = WritingLoopPolicy()
        self.assertIsNone(default.max_total_tokens)
        self.assertIsNone(default.max_wall_clock_ms)
        tuned = WritingLoopPolicy(max_total_tokens=1, max_wall_clock_ms=1)
        self.assertEqual((tuned.max_total_tokens, tuned.max_wall_clock_ms), (1, 1))


class WritingLoopAggregationTest(unittest.TestCase):
    def test_aggregates_provider_usage_and_wall_clock(self):
        # Pass-after-one-revise: 2 revises + 2 reports + 2 gates.
        # reviser TokenUsage(1,1)=2 ×2 = 4; reporter total 3 ×2 = 6;
        # gate total 5 ×2 = 10 → 20 tokens. wall-clock from the injected clock.
        gate = _MeteredLoopGate(
            (WritingGateDecision.REVISE, WritingGateDecision.PASS),
            usage=TokenUsage(0, 5),
        )
        service = _build(
            reviser_provider=_SequenceProvider(("고친 문장.", "또 고친 문장.")),
            gate=gate, reporter=_MeteredReporter(usage=TokenUsage(0, 3)),
            policy=WritingLoopPolicy(),
            clock=_AdvancingClock(first=0.0, then=2.5),
        )
        result = _run(service)
        self.assertIs(result.loop.status, WritingLoopStatus.PASS)
        self.assertEqual(result.loop.total_tokens, 20)
        self.assertEqual(result.loop.wall_clock_ms, 2500)

    def test_aggregates_retrieval_planner_usage_once(self):
        planner = _MeteredRetrievalPlanner(usage=TokenUsage(0, 7))
        context = _Context(_package())
        service = _build(
            reviser_provider=_Provider(),
            gate=_MeteredLoopGate(
                (WritingGateDecision.RETRIEVE_MORE, WritingGateDecision.PASS),
                usage=TokenUsage(0, 5),
            ),
            reporter=_MeteredReporter(usage=TokenUsage(0, 3)),
            policy=WritingLoopPolicy(), retrieval_planner=planner,
            context_search=context,
        )
        result = _run(service)
        # revise(2) + report(3) + two Gates(10) + planner(7) = 22.
        self.assertIs(result.loop.status, WritingLoopStatus.PASS)
        self.assertEqual(result.loop.total_tokens, 22)
        self.assertEqual(planner.calls, 1)
        self.assertEqual(context.calls, 1)

    def test_context_search_usage_excluded_from_aggregate_tokens(self):
        # Invariant behind the Option A ceiling composition
        # (05-writing-loop-ceiling-composition-decisions.md): context_search runs
        # OUTSIDE the loop's metered() channel (revise_gate.py), so even a search
        # that surfaces provider usage must not inflate total_tokens. If someone
        # routes it through metered(), metered() prefers the _metered variant and
        # its 999 tokens enter the aggregate → total != 22 and metered_calls != 0,
        # failing here. Without this guard the B2b ceiling would silently
        # under-bound (context_search cost double-counted into max_total_tokens).
        context = _MeteredContext(_package(), usage=TokenUsage(0, 999))
        service = _build(
            reviser_provider=_Provider(),
            gate=_MeteredLoopGate(
                (WritingGateDecision.RETRIEVE_MORE, WritingGateDecision.PASS),
                usage=TokenUsage(0, 5),
            ),
            reporter=_MeteredReporter(usage=TokenUsage(0, 3)),
            policy=WritingLoopPolicy(),
            retrieval_planner=_MeteredRetrievalPlanner(usage=TokenUsage(0, 7)),
            context_search=context,
        )
        result = _run(service)
        self.assertIs(result.loop.status, WritingLoopStatus.PASS)
        # Same 22 as above: the 999-token context search is excluded.
        self.assertEqual(result.loop.total_tokens, 22)
        self.assertEqual(context.calls, 1)          # bare method used
        self.assertEqual(context.metered_calls, 0)  # metered variant NOT used

    def test_off_by_default_never_enforces_despite_usage(self):
        # Usage accrues but the default (None) caps never stop the loop.
        gate = _MeteredLoopGate(
            (WritingGateDecision.REVISE, WritingGateDecision.PASS),
            usage=TokenUsage(500, 500),
        )
        service = _build(
            reviser_provider=_SequenceProvider(("고친 문장.", "또 고친 문장.")),
            gate=gate, reporter=_MeteredReporter(usage=TokenUsage(500, 500)),
            policy=WritingLoopPolicy(),
        )
        result = _run(service)
        self.assertIs(result.loop.status, WritingLoopStatus.PASS)
        self.assertGreater(result.loop.total_tokens, 0)

    def test_failed_stage_usage_is_counted_before_original_error_propagates(self):
        service = _build(
            reviser_provider=_Provider(), gate=_Gate(),
            reporter=_FailedMeteredReporter(), policy=WritingLoopPolicy(),
        )
        with self.assertRaises(WritingReviseReportFailure) as caught:
            _run(service)
        self.assertIsInstance(caught.exception.cause, InvalidCandidateReport)
        # revise(2) + rejected report response(3), counted exactly once.
        self.assertEqual(caught.exception.loop.total_tokens, 5)

    def test_failed_response_token_overrun_wins_before_parse_error(self):
        service = _build(
            reviser_provider=_Provider(), gate=_Gate(),
            reporter=_FailedMeteredReporter(),
            policy=WritingLoopPolicy(max_total_tokens=4),
        )
        result = _run(service)
        self.assertIs(result.loop.status, WritingLoopStatus.BUDGET_EXHAUSTED)
        self.assertEqual(result.loop.total_tokens, 5)
        self.assertIsNone(result.gate)


class WritingLoopTokenBudgetTest(unittest.TestCase):
    def _service(self, *, max_total_tokens, decisions, reviser_provider):
        gate = _MeteredLoopGate(decisions, usage=TokenUsage(0, 5))
        return _build(
            reviser_provider=reviser_provider, gate=gate,
            reporter=_MeteredReporter(usage=TokenUsage(0, 3)),
            policy=WritingLoopPolicy(max_total_tokens=max_total_tokens),
        )

    def test_gate_response_over_limit_is_not_adopted(self):
        # revise(2)+report(3)+gate(5)=10 > 9. The Gate response is counted but
        # not adopted, and no second revise starts (under-strict guard).
        provider = _Provider()
        service = self._service(
            max_total_tokens=9, decisions=(WritingGateDecision.REVISE,),
            reviser_provider=provider,
        )
        result = _run(service)
        self.assertIs(result.loop.status, WritingLoopStatus.BUDGET_EXHAUSTED)
        self.assertEqual(result.loop.revision_rounds, 1)
        self.assertIsNone(result.gate)
        self.assertEqual(provider.calls, 1)
        self.assertEqual([stage.stage.value for stage in result.stages], [
            "revise", "report",
        ])

    def test_cumulative_equal_to_limit_can_complete(self):
        # Over-strict guard: revise(2)+report(3)+gate(5)==10 may complete.
        provider = _Provider()
        service = self._service(
            max_total_tokens=10, decisions=(WritingGateDecision.PASS,),
            reviser_provider=provider,
        )
        result = _run(service)
        self.assertIs(result.loop.status, WritingLoopStatus.PASS)
        self.assertIs(result.gate.decision, WritingGateDecision.PASS)
        self.assertEqual(result.loop.total_tokens, 10)

    def test_initial_revise_over_limit_preserves_original_candidate(self):
        provider = _Provider()
        service = self._service(
            max_total_tokens=1, decisions=(), reviser_provider=provider,
        )
        result = _run(service)
        self.assertIs(result.loop.status, WritingLoopStatus.BUDGET_EXHAUSTED)
        self.assertEqual(result.candidate.text, _candidate().text)
        self.assertIsNone(result.gate)
        self.assertEqual(result.stages, ())

    def test_report_over_limit_preserves_revised_candidate_and_skips_gate(self):
        provider = _Provider()
        service = self._service(
            max_total_tokens=4, decisions=(), reviser_provider=provider,
        )
        result = _run(service)
        self.assertIs(result.loop.status, WritingLoopStatus.BUDGET_EXHAUSTED)
        self.assertEqual(result.candidate.text, "앞 문장. 고친 문장. 뒤 문장.")
        self.assertEqual(result.candidate.candidate_claims, ())
        self.assertIsNone(result.gate)
        self.assertEqual([stage.stage.value for stage in result.stages], ["revise"])


class WritingLoopWallClockBudgetTest(unittest.TestCase):
    def _service(self, *, clock, decisions, reviser_provider):
        gate = _MeteredLoopGate(decisions, usage=TokenUsage(0, 5))
        return _build(
            reviser_provider=reviser_provider, gate=gate,
            reporter=_MeteredReporter(usage=TokenUsage(0, 3)),
            policy=WritingLoopPolicy(max_wall_clock_ms=500), clock=clock,
        )

    def test_deadline_reached_before_initial_stage_starts_nothing(self):
        provider = _Provider()
        service = self._service(
            clock=_AdvancingClock(first=0.0, then=100.0),  # 100_000 ms >= 500
            decisions=(WritingGateDecision.REVISE,),
            reviser_provider=provider,
        )
        result = _run(service)
        self.assertIs(result.loop.status, WritingLoopStatus.BUDGET_EXHAUSTED)
        self.assertEqual(provider.calls, 0)
        self.assertEqual(result.loop.revision_rounds, 0)
        self.assertIsNone(result.gate)

    def test_deadline_after_revise_blocks_report(self):
        provider = _Provider()
        service = self._service(
            clock=_SequenceClock(0.0, 0.0, 1.0),
            decisions=(), reviser_provider=provider,
        )
        result = _run(service)
        self.assertIs(result.loop.status, WritingLoopStatus.BUDGET_EXHAUSTED)
        self.assertEqual(provider.calls, 1)
        self.assertEqual([stage.stage.value for stage in result.stages], ["revise"])
        self.assertIsNone(result.gate)

    def test_deadline_after_retrieval_plan_blocks_context_search(self):
        planner = _MeteredRetrievalPlanner(usage=TokenUsage(0, 1))
        context = _Context(_package())
        service = _build(
            reviser_provider=_Provider(),
            gate=_MeteredLoopGate(
                (WritingGateDecision.RETRIEVE_MORE,), usage=TokenUsage(0, 1),
            ),
            reporter=_MeteredReporter(usage=TokenUsage(0, 1)),
            policy=WritingLoopPolicy(max_wall_clock_ms=500),
            clock=_SequenceClock(0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
            retrieval_planner=planner, context_search=context,
        )
        result = _run(service)
        self.assertIs(result.loop.status, WritingLoopStatus.BUDGET_EXHAUSTED)
        self.assertEqual(planner.calls, 1)
        self.assertEqual(context.calls, 0)
        self.assertEqual([stage.stage.value for stage in result.stages], [
            "revise", "report", "gate", "retrieve_plan",
        ])

    def test_within_deadline_continues(self):
        provider = _SequenceProvider(("고친 문장.", "또 고친 문장."))
        service = self._service(
            clock=_AdvancingClock(first=0.0, then=0.1),  # 100 ms < 500
            decisions=(WritingGateDecision.REVISE, WritingGateDecision.PASS),
            reviser_provider=provider,
        )
        result = _run(service)
        self.assertIs(result.loop.status, WritingLoopStatus.PASS)
        self.assertEqual(provider.calls, 2)

    def test_provider_timeout_is_provider_error_not_budget(self):
        # A provider fault inside a stage propagates as a loop failure; the
        # budget guard (which only runs before the next stage) never converts it.
        timeout = ProviderError(
            code=ProviderErrorCode.TIMEOUT, message="slow", retryable=True
        )
        service = _build(
            reviser_provider=_Provider(), gate=_Gate(error=timeout),
            reporter=_Reporter(),
            policy=WritingLoopPolicy(max_wall_clock_ms=1),
            clock=_AdvancingClock(first=0.0, then=0.0),
        )
        with self.assertRaises(WritingReviseGateFailure) as caught:
            _run(service)
        self.assertIsInstance(caught.exception.cause, ProviderError)
        self.assertIs(caught.exception.loop.status, WritingLoopStatus.FAILED)


class WritingLoopBudgetHttpTest(unittest.TestCase):
    def _audit_service(self):
        from services.application.app.writing.loop_audit import (
            InMemoryWritingLoopAuditRepository,
            WritingLoopAuditService,
        )
        return WritingLoopAuditService(InMemoryWritingLoopAuditRepository())

    def test_ephemeral_loop_payload_excludes_token_fields(self):
        # M5=A: even with a budget configured, the ephemeral `loop` payload keeps
        # exactly the four structural keys — aggregate metering is audit-only.
        client, project, _ = _http(
            _Provider(), gate_service=_Gate(),
            report_service=_MeteredReporter(usage=TokenUsage(0, 3)),
            loop_policy=WritingLoopPolicy(max_total_tokens=1000),
        )
        response = client.post(
            f"/projects/{project}/writing/revise-and-gate", _http_body()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()["loop"]), {
            "status", "revision_rounds", "retrieval_rounds", "gate_evaluations",
        })

    def test_env_token_limit_changes_state_and_empty_value_is_unbounded(self):
        with patch.dict("os.environ", {"WRITING_LOOP_MAX_TOTAL_TOKENS": "1"}):
            client, project, _ = _http(
                _Provider(), gate_service=_Gate(), report_service=_Reporter(),
            )
            limited = client.post(
                f"/projects/{project}/writing/revise-and-gate", _http_body()
            ).json()
        self.assertEqual(limited["loop"]["status"], "budget_exhausted")
        self.assertIsNone(limited["gate"])

        with patch.dict("os.environ", {"WRITING_LOOP_MAX_TOTAL_TOKENS": ""}):
            client, project, _ = _http(
                _Provider(), gate_service=_Gate(), report_service=_Reporter(),
            )
            unbounded = client.post(
                f"/projects/{project}/writing/revise-and-gate", _http_body()
            ).json()
        self.assertEqual(unbounded["loop"]["status"], "pass")
        self.assertIsNotNone(unbounded["gate"])

    def test_persisted_audit_carries_aggregate_tokens(self):
        audit = self._audit_service()
        client, project, _ = _http(
            _Provider(),
            gate_service=_MeteredGateHttp(usage=TokenUsage(0, 5)),
            report_service=_MeteredReporter(usage=TokenUsage(0, 3)),
            loop_policy=WritingLoopPolicy(max_total_tokens=1000),
            loop_audit_service=audit,
        )
        posted = client.post(
            f"/projects/{project}/writing/revise-and-gate",
            dict(_http_body(), persist_audit=True),
        ).json()
        audit_id = posted["audit_id"]
        self.assertTrue(audit_id)
        detail = _http_get(
            client, f"/projects/{project}/writing/loop-audits/{audit_id}"
        )
        # revise(2) + report(3) + gate(5) on a single-pass loop = 10 tokens.
        self.assertEqual(detail["total_tokens"], 10)
        self.assertIsInstance(detail["wall_clock_ms"], int)
        self.assertGreaterEqual(detail["wall_clock_ms"], 0)


class _MeteredGateHttp(_Gate):
    def __init__(self, *, usage, decision=WritingGateDecision.PASS):
        super().__init__(decision=decision)
        self._usage = usage

    async def evaluate_metered(self, *, request, candidate, package):
        result = await self.evaluate(
            request=request, candidate=candidate, package=package
        )
        return result, self._usage


def _http_body():
    return {
        "request_id": "r1", "instruction": "연속성을 고쳐줘",
        "candidate_text": "앞 문장. 잘못된 문장. 뒤 문장.",
        "finding": {"type": "continuity", "severity": "warning",
                    "message": "연속성 수정", "evidence": "잘못된 문장.",
                    "recommended_decision": "revise"},
    }


def _http_get(client: _Client, path: str):
    async def send():
        import httpx
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app), base_url="http://test"
        ) as http:
            return (await http.get(path)).json()
    return asyncio.run(send())


if __name__ == "__main__":
    unittest.main()
