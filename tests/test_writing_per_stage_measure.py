"""Phase 5.10 Option A (M-i) per-stage cost measurement regressions.

Locks the measurement core's load-bearing properties:
- each of the five loop stages is measured in isolation (token + wall-clock),
- ``context_search`` is excluded from the token budget by construction
  (mirrors ``_TOKEN_STAGES`` / ``revise_gate`` metered boundary),
- ``retrieve_plan`` is fed a SYNTHETIC ``retrieve_more`` Gate (not model-
  produced) so the planner runs regardless of the real Gate's decision,
- the conservative MAX per stage is taken across repeats,
- a stage fault is surfaced and the stage is reported incomplete,
- the measured dict composes into the same ceiling ``compose_worst_case_ceiling``
  produces (round-trip with the synthesis), and
- the core reaches no write path.
"""

import asyncio
import unittest
from dataclasses import replace

from services.application.app.context_search.models import (
    ContextBudget, ContextPackage, ContextSearchPurpose, ContextSearchRequest,
    CurrentPosition,
)
from services.application.app.writing.metering import MeteredCallError
from services.application.app.writing.models import (
    WritingCandidate, WritingGateDecision, WritingGateFinding,
    WritingGateFindingType, WritingGateResult, WritingGateSeverity,
    WritingOutputType, WritingRequest, WritingTaskType,
)
from services.application.app.writing.per_stage_measure import (
    CONTEXT_SEARCH_STAGE, GATE_STAGE, PerStageMeasurement, REPORT_STAGE,
    RETRIEVE_PLAN_STAGE, REVISE_STAGE, measurement_to_dict,
    run_per_stage_measurement,
)
from services.application.app.writing.retrieval import WritingRetrievalPlan
from services.application.app.writing.revise_gate import WritingLoopPolicy
from services.llm_gateway.app.provider import TokenUsage

from scripts.benchmark_writing_loop import compose_worst_case_ceiling

_PROJECT = "p1"
_REQUEST_ID = "wr1"
_CANDIDATE_TEXT = "아린은 문을 열었다. 비는 그쳤다."


def _request():
    return WritingRequest(request_id=_REQUEST_ID, project_id=_PROJECT,
                          task_type=WritingTaskType.CONTINUE_SCENE,
                          instruction="이어서 써줘")


def _candidate(text=_CANDIDATE_TEXT):
    return WritingCandidate(request_id=_REQUEST_ID, project_id=_PROJECT,
                            task_type=WritingTaskType.CONTINUE_SCENE,
                            output_type=WritingOutputType.DRAFT_PATCH, text=text)


def _package():
    return ContextPackage(project_id=_PROJECT,
                          purpose=ContextSearchPurpose.WRITING_CONTEXT,
                          macro_items=(), micro_evidence=(), constraints=(),
                          do_not_use=(), token_estimate_total=0, degraded=False)


def _finding():
    return WritingGateFinding(
        finding_type=WritingGateFindingType.CONTINUITY,
        severity=WritingGateSeverity.WARNING, message="상태가 다르다.",
        evidence="문을 열었다", recommended_decision=WritingGateDecision.REVISE,
    )


def _search_request():
    return ContextSearchRequest(
        project_id=_PROJECT, purpose=ContextSearchPurpose.WRITING_CONTEXT,
        needs=(), query="이어서 써줘", current_position=None,
        context_budget=ContextBudget(max_tokens=4096),
    )


def _gate_result(decision=WritingGateDecision.PASS):
    return WritingGateResult(request_id=_REQUEST_ID, project_id=_PROJECT,
                             decision=decision, findings=(),
                             checked_constraints=(), evaluated_by_model="g")


class _SpyContext:
    def __init__(self): self.calls = []
    async def build_context_package(self, request):
        self.calls.append("build_context_package")
        return _package()


class _SpyReviser:
    def __init__(self, usage): self.usage, self.calls = usage, []
    async def revise_metered(self, *, candidate, finding, instruction, package):
        self.calls.append("revise_metered")
        return replace(candidate, text=candidate.text + " (수정)"), self.usage


class _SpyReporter:
    def __init__(self, usage): self.usage, self.calls = usage, []
    async def enrich_metered(self, candidate, package):
        self.calls.append("enrich_metered")
        return candidate, self.usage


class _SpyGate:
    def __init__(self, usage): self.usage, self.calls = usage, []
    async def evaluate_metered(self, *, request, candidate, package):
        self.calls.append("evaluate_metered")
        return _gate_result(), self.usage


class _SpyPlanner:
    def __init__(self, usage): self.usage, self.calls, self.seen_gate = usage, [], []
    async def plan_metered(self, *, request, candidate, gate, current_position):
        self.calls.append("plan_metered")
        self.seen_gate.append(gate)
        return WritingRetrievalPlan(query="q", needs=()), self.usage


class _FailingReporter:
    async def enrich_metered(self, candidate, package):
        raise MeteredCallError(ValueError("report field must be an array"),
                               TokenUsage(7, 3))


def _sequential_clock(step=1.0):
    """Deterministic monotonic clock: each call advances by ``step`` seconds, so
    every timed stage (two clock reads) measures exactly ``step*1000`` ms. Uses a
    binary-exact step (1.0) to avoid float-accumulation truncation."""
    state = {"t": 0.0}

    def clock():
        value = state["t"]
        state["t"] += step
        return value

    return clock


def _drive(*, reviser=None, reporter=None, gate=None, planner=None,
           context=None, repeats=1, clock=None):
    reviser = reviser or _SpyReviser(TokenUsage(30, 20))
    reporter = reporter or _SpyReporter(TokenUsage(40, 25))
    gate = gate or _SpyGate(TokenUsage(50, 30))
    planner = planner or _SpyPlanner(TokenUsage(20, 10))
    context = context or _SpyContext()
    return asyncio.run(run_per_stage_measurement(
        context_search=context, search_request=_search_request(),
        reviser=reviser, reporter=reporter, gate=gate, retrieval_planner=planner,
        request=_request(), candidate=_candidate(), finding=_finding(),
        current_position=CurrentPosition(draft_id="d", version_id="v"),
        repeats=repeats, clock=clock or _sequential_clock(),
    ))


class PerStageMeasurementTests(unittest.TestCase):
    def test_each_stage_measured_with_token_and_wall_clock(self):
        result = _drive()
        # Token-contributing stages carry their provider total_tokens.
        self.assertEqual(result.stage_tokens[REVISE_STAGE], 50)   # 30+20
        self.assertEqual(result.stage_tokens[REPORT_STAGE], 65)   # 40+25
        self.assertEqual(result.stage_tokens[GATE_STAGE], 80)     # 50+30
        self.assertEqual(result.stage_tokens[RETRIEVE_PLAN_STAGE], 30)  # 20+10
        # Every stage (incl. context_search) has a wall-clock measurement.
        for stage in (CONTEXT_SEARCH_STAGE, REVISE_STAGE, REPORT_STAGE,
                      GATE_STAGE, RETRIEVE_PLAN_STAGE):
            self.assertEqual(result.stage_ms[stage], 1000)  # 1.0s step
        self.assertEqual(result.incomplete_stages, ())
        self.assertIsNone(result.error)

    def test_context_search_excluded_from_token_budget(self):
        # Under-strict + over-strict: context_search must have a wall-clock ms
        # but must NOT appear in stage_tokens (loop metered() boundary). If the
        # core ever counted its tokens, this key would be present.
        result = _drive()
        self.assertIn(CONTEXT_SEARCH_STAGE, result.stage_ms)
        self.assertNotIn(CONTEXT_SEARCH_STAGE, result.stage_tokens)

    def test_retrieve_plan_fed_synthetic_retrieve_more_gate(self):
        # The planner must receive a retrieve_more Gate result even though the
        # real Gate (SpyGate) decided PASS — this is the Gate-independence
        # sidestep Option A depends on.
        planner = _SpyPlanner(TokenUsage(20, 10))
        _drive(planner=planner)
        self.assertEqual(len(planner.seen_gate), 1)
        seen = planner.seen_gate[0]
        self.assertIs(seen.decision, WritingGateDecision.RETRIEVE_MORE)
        self.assertEqual(len(seen.findings), 1)
        self.assertIs(seen.findings[0].recommended_decision,
                      WritingGateDecision.RETRIEVE_MORE)

    def test_conservative_max_across_repeats(self):
        # Reviser alternates usage across passes; the aggregate must be the MAX,
        # not the last or the mean (under-strict: a later smaller pass must not
        # lower the recorded cost).
        class _AlternatingReviser:
            def __init__(self): self.n = 0
            async def revise_metered(self, *, candidate, finding, instruction, package):
                self.n += 1
                usage = TokenUsage(100, 0) if self.n == 1 else TokenUsage(10, 0)
                return candidate, usage

        result = _drive(reviser=_AlternatingReviser(), repeats=2)
        self.assertEqual(result.stage_tokens[REVISE_STAGE], 100)
        self.assertEqual(len(result.samples), 2)

    def test_stage_fault_surfaced_and_marked_incomplete(self):
        result = _drive(reporter=_FailingReporter())
        self.assertEqual(result.error_stage, REPORT_STAGE)
        self.assertIn("report field must be an array", result.error)
        # report and the stages after it never completed → incomplete.
        self.assertIn(REPORT_STAGE, result.incomplete_stages)
        self.assertIn(GATE_STAGE, result.incomplete_stages)
        self.assertIn(RETRIEVE_PLAN_STAGE, result.incomplete_stages)
        # context_search + revise ran before the fault → not incomplete.
        self.assertNotIn(CONTEXT_SEARCH_STAGE, result.incomplete_stages)
        self.assertNotIn(REVISE_STAGE, result.incomplete_stages)

    def test_composes_into_default_policy_ceiling(self):
        # Round-trip: the measured dict fed to the synthesis yields the same
        # ceiling as computing it directly. Default policy (2/1/3):
        #   n_revise=2, n_report=2, n_gate=3, n_retrieve_plan=1, n_context=1.
        result = _drive()
        policy = WritingLoopPolicy()
        ceiling = compose_worst_case_ceiling(
            stage_tokens=result.stage_tokens, stage_ms=result.stage_ms,
            policy=policy,
        )
        # tokens = 2*50 + 2*65 + 3*80 + 1*30 = 100+130+240+30 = 500
        self.assertEqual(ceiling["max_total_tokens"], 500)
        # ms = (2+2+3+1+1) * 1000 = 9000  (context_search included in wall-clock)
        self.assertEqual(ceiling["max_wall_clock_ms"], 9000)

    def test_no_write_path_reached(self):
        # The only collaborators the core touches are the five read/judge stages;
        # no Core SOT / memory / audit collaborator is passed in, and each spy
        # records exactly one call per pass.
        reviser = _SpyReviser(TokenUsage(1, 1))
        reporter = _SpyReporter(TokenUsage(1, 1))
        gate = _SpyGate(TokenUsage(1, 1))
        planner = _SpyPlanner(TokenUsage(1, 1))
        context = _SpyContext()
        _drive(reviser=reviser, reporter=reporter, gate=gate, planner=planner,
               context=context)
        self.assertEqual(context.calls, ["build_context_package"])
        self.assertEqual(reviser.calls, ["revise_metered"])
        self.assertEqual(reporter.calls, ["enrich_metered"])
        self.assertEqual(gate.calls, ["evaluate_metered"])
        self.assertEqual(planner.calls, ["plan_metered"])

    def test_measurement_to_dict_is_json_numeric_only(self):
        result = _drive()
        data = measurement_to_dict(result)
        self.assertEqual(set(data), {
            "stage_tokens", "stage_ms", "incomplete_stages", "error",
            "error_stage", "samples",
        })
        self.assertEqual(len(data["samples"]), 1)
        first_pass = data["samples"][0]
        self.assertEqual(len(first_pass), 5)  # five stages per pass

    def test_repeats_must_be_positive(self):
        with self.assertRaises(ValueError):
            _drive(repeats=0)


class MeasureCliTests(unittest.TestCase):
    def test_main_prints_measurement_and_ceiling(self):
        import json as _json

        from scripts.measure_writing_stages import build_arg_parser, main

        measurement = PerStageMeasurement(
            samples=(), stage_tokens={"revise": 50, "report": 65, "gate": 80,
                                      "retrieve_plan": 30},
            stage_ms={"context_search": 100, "revise": 100, "report": 100,
                      "gate": 100, "retrieve_plan": 100},
        )

        async def fake_run(args):
            from scripts.benchmark_writing_loop import compose_worst_case_ceiling
            policy = WritingLoopPolicy()
            return {
                "project_id": args.project_id, "model": "m", "repeats": args.repeats,
                "policy": {"max_revision_rounds": policy.max_revision_rounds,
                           "max_retrieval_rounds": policy.max_retrieval_rounds,
                           "max_gate_evaluations": policy.max_gate_evaluations},
                "measurement": measurement_to_dict(measurement),
                "ceiling": compose_worst_case_ceiling(
                    stage_tokens=measurement.stage_tokens,
                    stage_ms=measurement.stage_ms, policy=policy),
            }

        import io
        buf = io.StringIO()
        main(["--project-id", "p9", "--repeats", "2"], run=fake_run, stdout=buf)
        report = _json.loads(buf.getvalue())
        self.assertEqual(report["project_id"], "p9")
        self.assertEqual(report["ceiling"]["max_total_tokens"], 500)
        self.assertEqual(report["ceiling"]["max_wall_clock_ms"], 900)
        # arg parser exposes the measurement knobs.
        args = build_arg_parser().parse_args(["--project-id", "x"])
        self.assertEqual(args.repeats, 3)

    def test_compose_ceiling_complete_keeps_numbers(self):
        from scripts.measure_writing_stages import compose_ceiling

        result = _drive()  # all five stages complete
        ceiling = compose_ceiling(result, WritingLoopPolicy())
        self.assertTrue(ceiling["complete"])
        self.assertEqual(ceiling["incomplete_stages"], [])
        self.assertEqual(ceiling["max_total_tokens"], 500)
        self.assertEqual(ceiling["max_wall_clock_ms"], 9000)

    def test_compose_ceiling_incomplete_fails_closed(self):
        # H6: a faulted/incomplete measurement must NOT yield an under-bound
        # numeric ceiling — the numbers are nulled and completeness is surfaced.
        from scripts.measure_writing_stages import compose_ceiling

        result = _drive(reporter=_FailingReporter())
        self.assertTrue(result.incomplete_stages)  # precondition
        ceiling = compose_ceiling(result, WritingLoopPolicy())
        self.assertFalse(ceiling["complete"])
        self.assertIsNone(ceiling["max_total_tokens"])
        self.assertIsNone(ceiling["max_wall_clock_ms"])
        self.assertIn(REPORT_STAGE, ceiling["incomplete_stages"])
        # stage_counts is kept for debugging even when incomplete.
        self.assertIn("stage_counts", ceiling)

    def test_policy_from_env_reads_structural_caps(self):
        # H2: the CLI's env→policy wiring re-derives the structural caps the
        # production loop uses, so a changed cap re-composes the ceiling.
        import unittest.mock

        from scripts.measure_writing_stages import _policy_from_env

        with unittest.mock.patch.dict("os.environ", {
            "WRITING_LOOP_MAX_REVISION_ROUNDS": "4",
            "WRITING_LOOP_MAX_RETRIEVAL_ROUNDS": "2",
            "WRITING_LOOP_MAX_GATE_EVALUATIONS": "9",
        }):
            policy = _policy_from_env()
        self.assertEqual(policy.max_revision_rounds, 4)
        self.assertEqual(policy.max_retrieval_rounds, 2)
        self.assertEqual(policy.max_gate_evaluations, 9)

    def test_policy_from_env_defaults(self):
        import unittest.mock

        from scripts.measure_writing_stages import _policy_from_env

        with unittest.mock.patch.dict("os.environ", {}, clear=True):
            policy = _policy_from_env()
        self.assertEqual(
            (policy.max_revision_rounds, policy.max_retrieval_rounds,
             policy.max_gate_evaluations), (2, 1, 3))


if __name__ == "__main__":
    unittest.main()
