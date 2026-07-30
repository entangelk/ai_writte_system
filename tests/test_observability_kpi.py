"""증분 5 — KPI 집계 read-out (owner decision 2026-07-26, D1=A·D2=A).

The aggregation encodes three rules that are counter-intuitive on purpose, and
each is locked in both directions here:

- token totals exclude ``provider_error`` (its 0 means "unknown"),
- extra calls are counted per ``correlation_id`` **within one site** (a
  second row is a repair at a repair-shaped site, a designed round in the loop),
- a rate over zero samples is ``None``, never ``0.0``.

The last one is the whole reason the payload carries denominators: on a default
deployment the loop rollup is off, and a ``0.0`` non-convergence rate would read
as "the loop never diverged" when it means "nobody measured".
"""

import unittest
from datetime import UTC, datetime

# D8-3a: authenticated client — these suites drive domain behaviour, not the
# session boundary (that is tests/test_auth_api.py, which uses the real one).
# The admin read-out below is the exception: the seam does not resolve
# ``require_admin_user``, so that one drives a real app with a real session.
from fastapi.testclient import TestClient as _RealTestClient

from tests.auth_support import AuthenticatedTestClient as TestClient

from services.application.app.auth.sessions import (
    InMemorySessionRepository,
    SessionService,
)
from services.application.app.auth.users import (
    InMemoryUserRepository,
    UserService,
)
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.main import create_app
from services.application.app.observability.kpi import (
    NON_CONVERGED_LOOP_STATUSES,
    NOT_A_LOOP_ATTEMPT,
    TOKEN_COUNTED_OUTCOMES,
    aggregate_global_kpi,
    aggregate_kpi,
)
from services.application.app.observability.llm_call_audit import (
    InMemoryLlmCallAuditRepository,
    LlmCallAuditService,
    LlmCallOutcome,
    LlmCallSite,
    StoredLlmCall,
)
from services.application.app.writing.loop_audit import (
    InMemoryWritingLoopAuditRepository,
    StoredWritingLoopRun,
    WritingLoopAuditService,
)
from services.application.app.writing.revise_gate import WritingLoopStatus


class _FakeHasher:
    """Argon2id is deliberately slow; these tests are not about hashing."""

    def hash(self, password: str) -> str:
        return "H:" + password

    def verify(self, stored_hash: str, password: str) -> bool:
        return stored_hash == "H:" + password


def _call(
    call_site=LlmCallSite.WRITING_GATE, *, outcome=LlmCallOutcome.SUCCESS,
    correlation_id="wr-1", tokens=10, latency_ms=100, score=None,
    call_id="llmc:1", project_id="p1",
    prompt_tokens=None, max_output_tokens=None, context_window=None,
):
    # 세 창 관련 값은 **기본이 None("모른다")**이다 — 1a/1b 계약대로이며, 헤드룸 파생이
    # 그 경우를 판정 대상에서 빼는지(분모)까지 이 기본값으로 잠근다.
    return StoredLlmCall(
        id=call_id, project_id=project_id, call_site=call_site.value,
        correlation_id=correlation_id, model="fake", outcome=outcome.value,
        decision=None, gate_quality_score=score, total_tokens=tokens,
        latency_ms=latency_ms, error_type=None,
        created_at=datetime(2026, 7, 26, tzinfo=UTC),
        prompt_tokens=prompt_tokens, max_output_tokens=max_output_tokens,
        context_window=context_window,
    )


def _run(status, *, run_id="run-1", project_id="p1"):
    return StoredWritingLoopRun(
        id=run_id, project_id=project_id, request_id="wr-1",
        loop_status=status.value, revision_rounds=1, retrieval_rounds=0,
        gate_evaluations=1, error_type=None,
        trigger_finding_fingerprint="f", initial_candidate_hash="a",
        final_candidate_hash="b", final_candidate_text="text",
        final_gate_decision="pass", final_gate_finding_fingerprints=(),
        stages=(), created_at=datetime(2026, 7, 26, tzinfo=UTC),
    )


def _kpi(calls=(), runs=()):
    return aggregate_kpi(project_id="p1", calls=list(calls), loop_runs=list(runs))


def _global_kpi(calls=(), runs=()):
    return aggregate_global_kpi(calls=list(calls), loop_runs=list(runs))


class TokenAggregationTest(unittest.TestCase):
    def test_provider_error_rows_are_excluded_from_token_totals(self):
        # SoT v1.7.42: a provider_error's 0 tokens means "unknown", so counting
        # it drags the average down and misstates what the pipeline spent.
        kpi = _kpi([
            _call(outcome=LlmCallOutcome.SUCCESS, tokens=100, call_id="a"),
            _call(outcome=LlmCallOutcome.PARSE_ERROR, tokens=40, call_id="b"),
            _call(outcome=LlmCallOutcome.PROVIDER_ERROR, tokens=0, call_id="c"),
        ])
        self.assertEqual(kpi.totals.total_tokens, 140)
        # The denominator is reported so a reader never has to re-derive which
        # rows the total came from.
        self.assertEqual(kpi.totals.tokens_counted_from, 2)
        self.assertEqual(kpi.totals.calls, 3)

    def test_the_counted_outcome_set_is_exactly_success_and_parse_error(self):
        # Over-strict guard on the rule itself: widening this set silently
        # re-includes the rows the contract excluded.
        self.assertEqual(
            TOKEN_COUNTED_OUTCOMES,
            {LlmCallOutcome.SUCCESS.value, LlmCallOutcome.PARSE_ERROR.value},
        )

    def test_outcome_counts_cover_every_literal(self):
        kpi = _kpi([
            _call(outcome=LlmCallOutcome.SUCCESS, call_id="a"),
            _call(outcome=LlmCallOutcome.PROVIDER_ERROR, call_id="b"),
            _call(outcome=LlmCallOutcome.PARSE_ERROR, call_id="c"),
        ])
        self.assertEqual(
            (kpi.totals.success, kpi.totals.provider_error, kpi.totals.parse_error),
            (1, 1, 1),
        )


class MultiCallCorrelationTest(unittest.TestCase):
    def test_extra_calls_are_counted_within_a_site_not_across_sites(self):
        # SoT v1.7.47: one request now spans several sites. Counting rows per
        # correlation_id without fixing the site would read the planner's normal
        # call as a repair of the gate call.
        kpi = _kpi([
            _call(LlmCallSite.QUERY_PLANNER, correlation_id="wr-1", call_id="a"),
            _call(LlmCallSite.WRITING_GATE, correlation_id="wr-1", call_id="b"),
        ])
        by_site = {site.call_site: site for site in kpi.sites}
        self.assertEqual(by_site["query_planner"].multi_call_correlations, 0)
        self.assertEqual(by_site["writing_gate"].multi_call_correlations, 0)
        self.assertEqual(by_site["query_planner"].correlations, 1)

    def test_a_second_row_in_the_same_site_is_counted(self):
        kpi = _kpi([
            _call(LlmCallSite.COMPARE_JUDGE, correlation_id="job-1", call_id="a"),
            _call(LlmCallSite.COMPARE_JUDGE, correlation_id="job-1", call_id="b"),
            _call(LlmCallSite.COMPARE_JUDGE, correlation_id="job-2", call_id="c"),
        ])
        site = kpi.sites[0]
        self.assertEqual(site.correlations, 2)
        self.assertEqual(site.multi_call_correlations, 1)

    def test_rows_without_a_correlation_are_not_bucketed_together(self):
        # Over-strict guard: lumping null correlations into one bucket would
        # invent a single workflow that made every unattributed call — and then
        # report it as one that took many rounds.
        kpi = _kpi([
            _call(correlation_id=None, call_id="a"),
            _call(correlation_id=None, call_id="b"),
        ])
        self.assertEqual(kpi.sites[0].correlations, 0)
        self.assertEqual(kpi.sites[0].multi_call_correlations, 0)
        self.assertEqual(kpi.sites[0].calls, 2)


class GateScoreCoverageTest(unittest.TestCase):
    def test_the_average_is_taken_over_scored_calls_only(self):
        # SoT v1.7.47 known gap: gate calls made inside the revise loop carry no
        # score. Dividing by every gate call would drag the average toward zero
        # and make the gate look harsher than it judged.
        kpi = _kpi([
            _call(LlmCallSite.WRITING_GATE, score=1.0, call_id="a"),
            _call(LlmCallSite.WRITING_GATE, score=0.6, call_id="b"),
            _call(LlmCallSite.WRITING_GATE, score=None, call_id="c"),
        ])
        self.assertEqual(kpi.gate.scored_calls, 2)
        self.assertAlmostEqual(kpi.gate.avg_quality_score, 0.8)

    def test_no_scored_call_reports_null_not_zero(self):
        kpi = _kpi([_call(LlmCallSite.WRITING_GATE, score=None)])
        self.assertEqual(kpi.gate.scored_calls, 0)
        self.assertIsNone(kpi.gate.avg_quality_score)

    def test_a_scored_block_reports_a_real_zero(self):
        # Under-strict guard mirroring the loop's: ``BLOCK`` maps to 0.0, so a
        # real zero average must stay reachable. Without this, "null when
        # unmeasured" could swallow the gate's harshest verdict — the one an
        # owner most wants to see.
        kpi = _kpi([_call(LlmCallSite.WRITING_GATE, score=0.0)])
        self.assertEqual(kpi.gate.scored_calls, 1)
        self.assertEqual(kpi.gate.avg_quality_score, 0.0)


class LoopConvergenceTest(unittest.TestCase):
    def test_every_loop_status_is_classified(self):
        # The rule is stated as an enumeration, so the boundary test covers each
        # member — and this breaks first if a status is added without deciding
        # which half it belongs to (verification 2026-07-26 H-1 pattern).
        self.assertEqual(len(WritingLoopStatus), 6)
        expected = {
            WritingLoopStatus.PASS: "converged",
            WritingLoopStatus.TERMINAL_DECISION: "converged",
            WritingLoopStatus.BUDGET_EXHAUSTED: "non_converged",
            WritingLoopStatus.NO_CHANGE: "non_converged",
            WritingLoopStatus.FAILED: "non_converged",
            WritingLoopStatus.NOT_ELIGIBLE: "not_an_attempt",
        }
        for status, half in expected.items():
            with self.subTest(status=status):
                kpi = _kpi(runs=[_run(status)])
                if half == "not_an_attempt":
                    self.assertEqual(kpi.loop.runs_considered, 0)
                    self.assertIsNone(kpi.loop.non_convergence_rate)
                else:
                    self.assertEqual(kpi.loop.runs_considered, 1)
                    self.assertEqual(
                        kpi.loop.non_convergence_rate,
                        1.0 if half == "non_converged" else 0.0,
                    )

    def test_the_classification_sets_do_not_overlap(self):
        self.assertEqual(NON_CONVERGED_LOOP_STATUSES & NOT_A_LOOP_ATTEMPT, set())

    def test_no_loop_run_reports_null_rate_not_zero(self):
        # The load-bearing case on a default deployment: the loop rollup is
        # opt-in, so 0.0 here would claim the loop always converged.
        kpi = _kpi()
        self.assertEqual(kpi.loop.runs_considered, 0)
        self.assertIsNone(kpi.loop.non_convergence_rate)

    def test_a_converged_run_reports_a_real_zero(self):
        # Under-strict guard for the above: zero must still be reachable, or
        # "null when unmeasured" would have swallowed a genuine 0.0.
        kpi = _kpi(runs=[_run(WritingLoopStatus.PASS)])
        self.assertEqual(kpi.loop.runs_considered, 1)
        self.assertEqual(kpi.loop.non_convergence_rate, 0.0)


class ThinHeadroomWarningTest(unittest.TestCase):
    """K-3 창 헤드룸 경고(오너 2026-07-30) — "400 거부 **및 경고**"의 경고 절반.

    거부는 게이트웨이 가드가 하고, 여기서는 **넘지는 않지만 빠듯한** 호출을 센다. 저장된
    플래그가 아니라 원천 세 값(`prompt_tokens`·`max_output_tokens`·`context_window`)에서
    **읽기 시점에 파생**한다 — v1.7.59가 "헤드룸은 파생값이라 저장하지 않는다"로 정했고,
    플래그를 저장하면 임계값을 바꾸는 순간 과거 레코드가 거짓말을 한다.
    """

    def _kpi_for(self, *, prompt, cap, window, site=LlmCallSite.WRITING_REPORT):
        return _kpi([_call(site, prompt_tokens=prompt, max_output_tokens=cap,
                           context_window=window, call_id="a")])

    def test_a_roomy_call_is_not_a_warning(self):
        # over-strict: R-e 뒤 실측 자리(입력 3,216 + 상한 6,144, 창 16384 → 헤드룸 43%).
        # 여기서 경고가 뜨면 정상 운영이 온통 경고로 덮인다.
        kpi = self._kpi_for(prompt=3216, cap=6144, window=16384)
        self.assertEqual(kpi.totals.thin_headroom_calls, 0)
        self.assertEqual(kpi.totals.headroom_considered, 1)

    def test_a_thin_but_passing_call_is_a_warning(self):
        # under-strict: 이것이 경고의 존재 이유다 — 지금은 통과하지만 입력이 조금만 커지면
        # 거부로 바뀐다. 헤드룸 800 = 창의 4.8% < 10%.
        kpi = self._kpi_for(prompt=9440, cap=6144, window=16384)
        self.assertEqual(kpi.totals.thin_headroom_calls, 1)
        self.assertEqual(kpi.totals.headroom_considered, 1)

    def test_an_over_the_window_call_is_also_a_warning(self):
        # 2026-07-29 실배포 레코드 그대로(헤드룸 −1,665). 음수를 빼면 **가드가 없던 시절의
        # 레코드가 경고에서 사라진다** — 경고가 가장 필요한 행이 그것이다.
        kpi = self._kpi_for(prompt=11905, cap=6144, window=16384)
        self.assertEqual(kpi.totals.thin_headroom_calls, 1)

    def test_the_ten_percent_line_is_exact_in_both_directions(self):
        # 창 10000 · 상한 1000 → 헤드룸 정확히 1000(=10%)이면 경고 아님, 999면 경고.
        # `<`를 `<=`로 넓히면 첫 칸이, 좁히면 둘째 칸이 깨진다.
        self.assertEqual(
            self._kpi_for(prompt=8000, cap=1000, window=10000)
            .totals.thin_headroom_calls, 0)
        self.assertEqual(
            self._kpi_for(prompt=8001, cap=1000, window=10000)
            .totals.thin_headroom_calls, 1)

    def test_unknown_values_are_not_judged_and_the_denominator_says_so(self):
        """`None`은 "모른다"이지 0이 아니다 — 판정 대상에서 빠지고 분모가 그것을 말한다.

        0으로 취급하면 헤드룸이 창 전체로 계산돼 **경고가 절대 뜨지 않는다**(조용한 실패).
        분모가 없으면 경고 0건이 "빠듯한 호출이 없었다"인지 "창을 아는 호출이 없었다"인지
        구분할 수 없다(v1.7.48이 세운 방어 패턴).
        """
        for name, kwargs in (
            ("창 모름", dict(prompt=9440, cap=6144, window=None)),
            ("상한 모름", dict(prompt=9440, cap=None, window=16384)),
            ("입력 모름", dict(prompt=None, cap=6144, window=16384)),
        ):
            with self.subTest(name=name):
                kpi = self._kpi_for(**kwargs)
                self.assertEqual(kpi.totals.thin_headroom_calls, 0)
                self.assertEqual(kpi.totals.headroom_considered, 0)

    def test_the_warning_is_attributed_to_the_site_that_ran_thin(self):
        # site별로 내는 이유 — 다음 거부가 **어디서** 날지가 그 신호다(실측: report였다).
        kpi = _kpi([
            _call(LlmCallSite.WRITING_REPORT, prompt_tokens=9440,
                  max_output_tokens=6144, context_window=16384, call_id="a"),
            _call(LlmCallSite.WRITING_GENERATION, prompt_tokens=2484,
                  max_output_tokens=4096, context_window=16384, call_id="b"),
        ])
        by_site = {s.call_site: s for s in kpi.sites}
        self.assertEqual(by_site["writing_report"].thin_headroom_calls, 1)
        self.assertEqual(by_site["writing_generation"].thin_headroom_calls, 0)
        # 두 행 모두 판정은 됐다 — 분모는 site마다 1이다.
        self.assertEqual(
            {s: by_site[s].headroom_considered for s in by_site},
            {"writing_report": 1, "writing_generation": 1})
        self.assertEqual(kpi.totals.thin_headroom_calls, 1)
        self.assertEqual(kpi.totals.headroom_considered, 2)


class SiteRowsTest(unittest.TestCase):
    def test_rows_are_sorted_by_site_and_only_for_sites_that_called(self):
        kpi = _kpi([
            _call(LlmCallSite.WRITING_GATE, call_id="a"),
            _call(LlmCallSite.ANALYSIS_EXTRACTOR, call_id="b"),
        ])
        self.assertEqual([s.call_site for s in kpi.sites],
                         ["analysis_extractor", "writing_gate"])

    def test_latency_is_rounded_to_an_integer_ties_to_even(self):
        # The contract states the rounding so a dashboard does not re-round and
        # disagree with the API. Both tie directions are pinned because Python's
        # round() breaks ties to even, which surprises readers who expect .5 to
        # always go up.
        for latencies, expected in (((100, 101), 100), ((101, 102), 102)):
            with self.subTest(latencies=latencies):
                kpi = _kpi([
                    _call(latency_ms=latencies[0], call_id="a"),
                    _call(latency_ms=latencies[1], call_id="b"),
                ])
                self.assertEqual(kpi.sites[0].avg_latency_ms, expected)

    def test_latency_averages_over_failures_too(self):
        # A provider timeout really did cost that wall clock; excluding it would
        # make a degrading gateway look fast.
        kpi = _kpi([
            _call(latency_ms=100, call_id="a"),
            _call(outcome=LlmCallOutcome.PROVIDER_ERROR, latency_ms=900,
                  call_id="b"),
        ])
        self.assertEqual(kpi.sites[0].avg_latency_ms, 500)


class KpiEndpointTest(unittest.TestCase):
    def _client(self, calls=(), runs=()):
        audit = LlmCallAuditService(InMemoryLlmCallAuditRepository())
        loop_audit = WritingLoopAuditService(InMemoryWritingLoopAuditRepository())
        app = create_app(
            CoreSotService(InMemoryCoreSotRepository()),
            llm_call_audit_service=audit,
            writing_loop_audit_service=loop_audit,
        )
        client = TestClient(app)
        project_id = client.post("/projects", json={"name": "Novel"}).json()["id"]
        for call in calls:
            audit._repo.add(  # noqa: SLF001 — seeding the read-model directly
                _replace_project(call, project_id))
        for run in runs:
            loop_audit._repo.add(  # noqa: SLF001
                _replace_project(run, project_id))
        return client, project_id

    def test_payload_shape_is_the_contract_the_dashboard_reads(self):
        client, project_id = self._client(
            calls=[
                _call(LlmCallSite.WRITING_GATE, score=1.0, tokens=100,
                      latency_ms=200, call_id="a"),
                _call(LlmCallSite.WRITING_GATE,
                      outcome=LlmCallOutcome.PROVIDER_ERROR, tokens=0,
                      latency_ms=400, call_id="b"),
            ],
            runs=[_run(WritingLoopStatus.BUDGET_EXHAUSTED)],
        )

        body = client.get(f"/projects/{project_id}/observability/kpi").json()

        self.assertEqual(set(body), {"project_id", "totals", "sites", "gate", "loop"})
        self.assertEqual(body["project_id"], project_id)
        self.assertEqual(body["totals"], {
            "calls": 2, "success": 1, "provider_error": 1, "parse_error": 0,
            "total_tokens": 100, "tokens_counted_from": 1,
            # 이 픽스처는 창을 모르므로 **판정 대상이 0건**이다 — 경고 0이 "빠듯한 호출이
            # 없었다"가 아니라 "판정할 수 없었다"임을 분모가 말한다(K-3).
            "thin_headroom_calls": 0, "headroom_considered": 0,
        })
        self.assertEqual(body["sites"], [{
            "call_site": "writing_gate", "calls": 2, "success": 1,
            "provider_error": 1, "parse_error": 0, "total_tokens": 100,
            "tokens_counted_from": 1, "avg_latency_ms": 300,
            "correlations": 1, "multi_call_correlations": 1,
            "thin_headroom_calls": 0, "headroom_considered": 0,
        }])
        self.assertEqual(body["gate"], {"scored_calls": 1, "avg_quality_score": 1.0})
        self.assertEqual(body["loop"],
                         {"runs_considered": 1, "non_convergence_rate": 1.0})

    def test_an_empty_project_reports_zeros_and_nulls_not_an_error(self):
        # The first thing an owner will hit. Empty must be a valid, readable
        # answer — and the two rates must be null so "no data" is legible.
        client, project_id = self._client()

        response = client.get(f"/projects/{project_id}/observability/kpi")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["totals"]["calls"], 0)
        self.assertEqual(body["sites"], [])
        self.assertIsNone(body["gate"]["avg_quality_score"])
        self.assertIsNone(body["loop"]["non_convergence_rate"])

    def test_unknown_project_is_404(self):
        client, _ = self._client()
        response = client.get("/projects/missing/observability/kpi")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(set(response.json()), {"detail"})

    def test_records_of_another_project_are_not_counted(self):
        # Over-strict guard: the MVP's only boundary is project_id, so a KPI
        # that leaked another project's calls would be both wrong and a leak.
        client, project_id = self._client(
            calls=[_call(LlmCallSite.WRITING_GATE, call_id="a")])
        other = client.post("/projects", json={"name": "Other"}).json()["id"]

        body = client.get(f"/projects/{other}/observability/kpi").json()

        self.assertEqual(body["totals"]["calls"], 0)
        self.assertEqual(body["sites"], [])


def _replace_project(record, project_id):
    from dataclasses import replace

    return replace(record, project_id=project_id)


class GlobalAggregationTest(unittest.TestCase):
    """D8-5c: the same fold, over every project's records.

    The reason the global read-out reuses the aggregation instead of adding a
    second one is that the three rules above have to survive the wider input —
    so each is driven here against it rather than assumed from the per-project
    suite. One of them does not survive by itself: correlation ids are the
    caller's own request ids, so the bucket has to keep the project axis.
    """

    def test_every_project_is_folded_into_one_set_of_totals(self):
        kpi = _global_kpi([
            _call(project_id="p1", tokens=100, call_id="a"),
            _call(project_id="p2", tokens=40, call_id="b"),
        ])
        self.assertEqual(kpi.totals.calls, 2)
        self.assertEqual(kpi.totals.total_tokens, 140)
        self.assertEqual(kpi.projects_considered, 2)

    def test_the_same_correlation_id_in_two_projects_is_not_one_workflow(self):
        # The cell that only exists once the input widens. ``correlation_id`` is
        # the caller's own request_id/idempotency_key, so two projects can carry
        # the same string; bucketing on it alone would report one call in each
        # as a single two-call workflow — a repair that never happened.
        kpi = _global_kpi([
            _call(project_id="p1", correlation_id="wr-1", call_id="a"),
            _call(project_id="p2", correlation_id="wr-1", call_id="b"),
        ])
        [site] = kpi.sites
        self.assertEqual(site.correlations, 2)
        self.assertEqual(site.multi_call_correlations, 0)

    def test_a_second_call_within_one_project_is_still_counted(self):
        # Over-strict half of the cell above: adding the project to the key must
        # not split a genuine repair. Both directions are pinned because a key
        # of (project, call_id) would satisfy the previous test and report zero
        # multi-call workflows forever.
        kpi = _global_kpi([
            _call(project_id="p1", correlation_id="wr-1", call_id="a"),
            _call(project_id="p1", correlation_id="wr-1", call_id="b"),
            _call(project_id="p2", correlation_id="wr-1", call_id="c"),
        ])
        [site] = kpi.sites
        self.assertEqual(site.correlations, 2)
        self.assertEqual(site.multi_call_correlations, 1)

    def test_token_totals_still_exclude_provider_errors(self):
        kpi = _global_kpi([
            _call(project_id="p1", tokens=100, call_id="a"),
            _call(project_id="p2", outcome=LlmCallOutcome.PROVIDER_ERROR,
                  tokens=0, call_id="b"),
        ])
        self.assertEqual(kpi.totals.total_tokens, 100)
        self.assertEqual(kpi.totals.tokens_counted_from, 1)

    def test_zero_samples_report_null_rates_not_zero(self):
        kpi = _global_kpi()
        self.assertEqual(kpi.projects_considered, 0)
        self.assertEqual(kpi.totals.calls, 0)
        self.assertEqual(kpi.sites, ())
        self.assertIsNone(kpi.gate.avg_quality_score)
        self.assertIsNone(kpi.loop.non_convergence_rate)

    def test_real_zeroes_stay_reachable(self):
        # Under-strict half of the above, for both rates at once: "never
        # measured" must not swallow a measured zero just because the fold now
        # spans projects.
        kpi = _global_kpi(
            [_call(LlmCallSite.WRITING_GATE, project_id="p1", score=0.0)],
            [_run(WritingLoopStatus.PASS, project_id="p2")],
        )
        self.assertEqual(kpi.gate.avg_quality_score, 0.0)
        self.assertEqual(kpi.loop.non_convergence_rate, 0.0)

    def test_projects_considered_counts_loop_only_projects_too(self):
        # The loop rollup is opt-in per deployment, but a project whose only
        # record is a loop run did contribute to the numbers below it, so it
        # belongs in the denominator that says where they came from.
        kpi = _global_kpi(
            [_call(project_id="p1", call_id="a")],
            [_run(WritingLoopStatus.PASS, project_id="p2")],
        )
        self.assertEqual(kpi.projects_considered, 2)

    def test_projects_considered_does_not_double_count_one_project(self):
        kpi = _global_kpi(
            [_call(project_id="p1", call_id="a"),
             _call(project_id="p1", call_id="b")],
            [_run(WritingLoopStatus.PASS, project_id="p1")],
        )
        self.assertEqual(kpi.projects_considered, 1)


class AdminKpiEndpointTest(unittest.TestCase):
    """``GET /admin/observability/kpi`` — the deployment-wide read-out (D8-5c).

    Driven through a **real, non-overridden app**: the test seam in
    ``tests/auth_support.py`` resolves exactly two dependencies and
    ``require_admin_user`` is deliberately not one of them, so the only way in is
    a real admin session. The boundary itself (non-admin → 403, sessionless →
    401) is audited in ``CombinedBoundaryMatrixTest``; this class is about what
    the endpoint answers once an admin is through it.
    """

    def _client(self, calls=(), runs=()):
        audit = LlmCallAuditService(InMemoryLlmCallAuditRepository())
        loop_audit = WritingLoopAuditService(InMemoryWritingLoopAuditRepository())
        users = UserService(InMemoryUserRepository(), hasher=_FakeHasher())
        users.create_user(username="root", password="pw", is_admin=True)
        app = create_app(
            CoreSotService(InMemoryCoreSotRepository()),
            user_service=users,
            session_service=SessionService(InMemorySessionRepository()),
            llm_call_audit_service=audit,
            writing_loop_audit_service=loop_audit,
        )
        # https base_url: the session cookie is Secure by default and an http
        # client drops it silently, which would fail this suite as a 401.
        client = _RealTestClient(app, base_url="https://testserver")
        client.post("/auth/login", json={"username": "root", "password": "pw"})
        for call in calls:
            audit._repo.add(call)  # noqa: SLF001 — seeding the read-model
        for run in runs:
            loop_audit._repo.add(run)  # noqa: SLF001
        return client

    def test_payload_shape_is_the_global_contract(self):
        client = self._client(
            calls=[
                _call(LlmCallSite.WRITING_GATE, project_id="p1", score=1.0,
                      tokens=100, latency_ms=200, call_id="a"),
                _call(LlmCallSite.WRITING_GATE, project_id="p2",
                      outcome=LlmCallOutcome.PROVIDER_ERROR, tokens=0,
                      latency_ms=400, call_id="b"),
            ],
            runs=[_run(WritingLoopStatus.BUDGET_EXHAUSTED, project_id="p1")],
        )

        response = client.get("/admin/observability/kpi")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        # ``projects_considered`` where the per-project payload carries
        # ``project_id`` — and no project named anywhere, which is the same line
        # the admin boundary draws around project content.
        self.assertEqual(
            set(body),
            {"projects_considered", "totals", "sites", "gate", "loop"},
        )
        self.assertEqual(body["projects_considered"], 2)
        self.assertEqual(body["totals"], {
            "calls": 2, "success": 1, "provider_error": 1, "parse_error": 0,
            "total_tokens": 100, "tokens_counted_from": 1,
            "thin_headroom_calls": 0, "headroom_considered": 0,
        })
        self.assertEqual(body["sites"], [{
            "call_site": "writing_gate", "calls": 2, "success": 1,
            "provider_error": 1, "parse_error": 0, "total_tokens": 100,
            "tokens_counted_from": 1, "avg_latency_ms": 300,
            "correlations": 2, "multi_call_correlations": 0,
            "thin_headroom_calls": 0, "headroom_considered": 0,
        }])
        self.assertEqual(body["gate"], {"scored_calls": 1, "avg_quality_score": 1.0})
        self.assertEqual(body["loop"],
                         {"runs_considered": 1, "non_convergence_rate": 1.0})

    def test_it_counts_records_of_projects_the_admin_does_not_own(self):
        # The load-bearing difference from the per-project read-out, and the
        # reason this endpoint exists: the admin owns nothing here, and the
        # ownership boundary that answers 403 on every project route must not
        # narrow this fold to the admin's own (empty) share.
        client = self._client(calls=[
            _call(project_id="p1", tokens=10, call_id="a"),
            _call(project_id="p2", tokens=30, call_id="b"),
        ])

        body = client.get("/admin/observability/kpi").json()

        self.assertEqual(body["totals"]["calls"], 2)
        self.assertEqual(body["totals"]["total_tokens"], 40)
        self.assertEqual(body["projects_considered"], 2)

    def test_an_empty_deployment_reports_zeros_and_nulls_not_an_error(self):
        response = self._client().get("/admin/observability/kpi")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["projects_considered"], 0)
        self.assertEqual(body["totals"]["calls"], 0)
        self.assertEqual(body["sites"], [])
        self.assertIsNone(body["gate"]["avg_quality_score"])
        self.assertIsNone(body["loop"]["non_convergence_rate"])

    def test_the_success_body_is_a_declared_model_not_a_free_dict(self):
        spec = create_app().openapi()
        schema = (spec["paths"]["/admin/observability/kpi"]["get"]["responses"]
                  ["200"]["content"]["application/json"]["schema"])
        self.assertEqual(
            schema.get("$ref"),
            "#/components/schemas/AdminObservabilityKpiResponse",
        )

    def test_the_site_row_type_is_shared_with_the_per_project_read_out(self):
        # Two payloads, one row type: a site field added for one and not the
        # other would let the same number mean different things depending on
        # which endpoint a reader asked.
        spec = create_app().openapi()
        rows = {
            name: (spec["components"]["schemas"][name]["properties"]["sites"])
            for name in ("ObservabilityKpiResponse",
                         "AdminObservabilityKpiResponse")
        }
        for name, sites in rows.items():
            with self.subTest(schema=name):
                self.assertEqual(sites["type"], "array")
                self.assertEqual(
                    sites["items"]["$ref"],
                    "#/components/schemas/ObservabilityKpiSitePayload",
                )


class KpiErrorContractDeclarationTest(unittest.TestCase):
    """H3 — the observability track's OpenAPI declaration.

    A track of one endpoint today, with the same closure guard the other tracks
    carry: a second observability endpoint shipping without a declaration would
    leave the row below green while "the track is closed" quietly stops being
    true.
    """

    EXPECTED = {
        ("/projects/{project_id}/observability/kpi", "get"): {"401", "403", "404", "503"},
    }

    def setUp(self):
        self.spec = create_app().openapi()

    def test_declared_error_statuses_match_the_lock_list(self):
        for (path, method), expected in self.EXPECTED.items():
            with self.subTest(path=path, method=method):
                responses = self.spec["paths"][path][method]["responses"]
                declared = {c for c in responses if c not in ("200", "422")}
                self.assertEqual(declared, expected)

    def test_the_whole_observability_track_is_declared(self):
        # ``/admin/observability/*`` is excluded by rule, not by listing each
        # one: those operations belong to the admin track's lock list
        # (``AdminErrorContractDeclarationTest``), whose status set they share
        # and whose closure guard already refuses an undeclared ``/admin/``
        # path. One operation owned by two exact-set lock lists is how the two
        # start to disagree.
        undeclared = {
            (path, method)
            for path, operations in self.spec["paths"].items()
            if "/observability/" in path and not path.startswith("/admin/")
            for method in operations
            if (path, method) not in self.EXPECTED
        }
        self.assertEqual(undeclared, set())

    def test_every_declared_error_body_is_the_uniform_detail_model(self):
        for (path, method), expected in self.EXPECTED.items():
            responses = self.spec["paths"][path][method]["responses"]
            for code in expected:
                with self.subTest(path=path, method=method, code=code):
                    schema = responses[code]["content"]["application/json"]["schema"]
                    self.assertEqual(
                        schema.get("$ref"),
                        "#/components/schemas/ErrorDetailResponse",
                    )

    def test_the_success_body_is_a_declared_model_not_a_free_dict(self):
        # D2=A: the dashboard consumes generated types, so the 200 arm has to be
        # a named schema — an untyped dict would generate ``unknown``.
        schema = (self.spec["paths"]["/projects/{project_id}/observability/kpi"]
                  ["get"]["responses"]["200"]["content"]["application/json"]
                  ["schema"])
        self.assertEqual(schema.get("$ref"),
                         "#/components/schemas/ObservabilityKpiResponse")

    def test_sites_is_an_array_so_new_call_sites_do_not_change_the_schema(self):
        # The load-bearing reason for D2=A. If sites were a map keyed by
        # call_site, every new literal (5→8 in 증분 C, more with Phase 7) would
        # change the generated frontend type.
        sites = (self.spec["components"]["schemas"]["ObservabilityKpiResponse"]
                 ["properties"]["sites"])
        self.assertEqual(sites["type"], "array")
        self.assertEqual(sites["items"]["$ref"],
                         "#/components/schemas/ObservabilityKpiSitePayload")
        call_site = (self.spec["components"]["schemas"]
                     ["ObservabilityKpiSitePayload"]["properties"]["call_site"])
        self.assertEqual(call_site["type"], "string")
