"""증분 C — call-site mapping and scope coverage (owner decision 2026-07-26).

Brief ``observability-site-mapping-decisions.md``. Three things this locks that
the seam tests (``test_llm_call_scope.py``) structurally cannot:

- **Which literal a call is filed under.** Five literals covered eight adapters,
  so the loop's planner/reviser/report calls had nowhere to go (D1/D2). A
  mis-filed call is invisible: the row exists, the KPI just answers the wrong
  question.
- **Whether the deployed assembly wraps the provider at all.** Every other
  regression builds ``ObservedProvider`` by hand, so a factory that stops
  wrapping keeps the suite green and records nothing in production.
- **Whether the request path opens a scope** (D3). Wrapping without a scope
  records zero, silently — the failure mode this project already measured once.
"""

import asyncio
import json
import os
import unittest
from dataclasses import replace
from unittest import mock

# D8-3a: authenticated client — these suites drive domain behaviour, not the
# session boundary (that is tests/test_auth_api.py, which uses the real one).
from tests.auth_support import AuthenticatedTestClient as TestClient

from services.application.app.analysis.compare import InvalidJudgeResult
from services.application.app.analysis.compare_judge import (
    TerminalJsonCompareJudge,
)
from services.application.app.context_search.models import (
    ContextSearchErrorType,
)
from services.application.app.context_search.service import ContextSearchFailed
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.main import create_app
from services.application.app.observability.llm_call_audit import (
    InMemoryLlmCallAuditRepository,
    LlmCallAuditService,
    LlmCallOutcome,
    LlmCallSite,
)
from services.application.app.observability.llm_call_scope import (
    ObservedProvider,
    llm_call_scope,
)
from services.application.app.writing.models import (
    WritingGateDecision,
    WritingGateResult,
)
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.provider import GenerationResult, TokenUsage

from tests.test_analysis_compare_judge import (
    _candidate as _judge_candidate,
    _judge_content,
    _memory as _judge_memory,
    _service as _judge_templates,
)
from tests.test_writing_revise import (
    _Context,
    _candidate,
    _finding,
    _package,
)


def _audit():
    return LlmCallAuditService(InMemoryLlmCallAuditRepository())


class _Provider:
    """Answers with a scripted sequence; a ``ProviderError`` entry is raised."""

    def __init__(self, *contents):
        self.contents = list(contents)
        self.calls = 0

    async def generate(self, request):
        self.calls += 1
        item = self.contents.pop(0) if self.contents else "ok"
        if isinstance(item, Exception):
            raise item
        return GenerationResult(model="fake-model", content=item,
                                finish_reason="stop", usage=TokenUsage(2, 3))


def _observed(site, *contents):
    return ObservedProvider(_Provider(*contents), call_site=site)


class SiteAssemblyIsInstrumentedTest(unittest.TestCase):
    """The deployed graph, one guard per factory 증분 C touched.

    Structural (private attribute) where the factory builds its provider
    internally and there is no seam to feed a fake through — the same reason
    the extractor guard is structural. Each asserts the *literal* too, because
    wrapping with the wrong site is as wrong as not wrapping.
    """

    def setUp(self):
        self._env = mock.patch.dict(
            os.environ, {"LLM_GATEWAY_BASE_URL": "http://gw"})
        self._env.start()
        self.addCleanup(self._env.stop)

    def _assert_wrapped(self, provider, site):
        self.assertIsInstance(provider, ObservedProvider)
        self.assertEqual(provider._call_site, site)

    def test_compare_judge_assembly_is_wrapped(self):
        from services.application.app.main import _default_compare_service
        from services.application.app.memory.service import (
            InMemoryMemoryRepository, MemoryService,
        )

        compare = _default_compare_service(
            MemoryService(InMemoryMemoryRepository()))
        self._assert_wrapped(compare._judge._provider,
                             LlmCallSite.COMPARE_JUDGE)

    def test_context_search_planner_assembly_is_wrapped(self):
        from services.application.app.analysis.service import (
            AnalysisService, InMemoryAnalysisRepository,
        )
        from services.application.app.indexing.service import (
            DeterministicFakeEmbeddingProvider, InMemoryVectorIndexAdapter,
        )
        from services.application.app.main import _default_context_search_service
        from services.application.app.memory.service import (
            InMemoryMemoryRepository, MemoryService,
        )

        core_sot = CoreSotService(InMemoryCoreSotRepository())
        service = _default_context_search_service(
            core_sot,
            vector_index=InMemoryVectorIndexAdapter(),
            embeddings=DeterministicFakeEmbeddingProvider(),
            memory=MemoryService(InMemoryMemoryRepository()),
            analysis=AnalysisService(InMemoryAnalysisRepository()),
        )
        self._assert_wrapped(service._planner._provider,
                             LlmCallSite.QUERY_PLANNER)

    def test_writing_retrieval_planner_assembly_is_wrapped(self):
        # D1: a *different* literal from the context-search planner above. If
        # both were QUERY_PLANNER this test would pass while the aggregation
        # lost the ability to tell the two subsystems apart.
        from services.application.app.main import _build_writing_retrieval_planner

        planner = _build_writing_retrieval_planner(_Provider())
        self._assert_wrapped(planner._provider,
                             LlmCallSite.WRITING_RETRIEVAL_PLANNER)

    def test_revision_assembly_is_wrapped(self):
        from services.application.app.main import _build_revise_service

        self._assert_wrapped(_build_revise_service(_Provider())._provider,
                             LlmCallSite.WRITING_REVISION)

    def test_report_assembly_is_wrapped(self):
        from services.application.app.main import _build_report_service

        self._assert_wrapped(_build_report_service(_Provider()).provider,
                             LlmCallSite.WRITING_REPORT)

    def test_generation_and_its_reporter_are_wrapped_as_different_sites(self):
        # The generation factory builds ONE gateway provider and hands it to
        # both the generator and its reporter. Wrapping once would file the
        # self-report under ``writing_generation`` and make "is generation or
        # reporting the expensive half" unanswerable (D2).
        from services.application.app.main import _default_writing_service

        writing = _default_writing_service()
        self._assert_wrapped(writing._provider, LlmCallSite.WRITING_GENERATION)
        self._assert_wrapped(writing._reporter.provider,
                             LlmCallSite.WRITING_REPORT)


class CompareJudgeRecordsEveryTurnTest(unittest.TestCase):
    """The real judge, not a stand-in — N pairs and the repair retry.

    The judge has the extractor's shape (one call, plus a repair when the
    verdict is not JSON), so it is the site where D4 (reclassify the *final*
    rejection only) has to hold without collapsing the repair signal.
    """

    def _judge(self, *contents):
        provider = _observed(LlmCallSite.COMPARE_JUDGE, *contents)
        return TerminalJsonCompareJudge(
            provider, prompt_templates=_judge_templates())

    def _run(self, judge, audit, *, pairs=1):
        async def run():
            with llm_call_scope(audit, project_id="project-1",
                                correlation_id="job-1"):
                for _ in range(pairs):
                    await judge.judge(candidate=_judge_candidate(),
                                      memory=_judge_memory())

        return asyncio.run(run())

    def test_each_matched_pair_leaves_its_own_record(self):
        audit = _audit()
        judge = self._judge(_judge_content(), _judge_content(), _judge_content())
        self._run(judge, audit, pairs=3)
        calls = audit.list_calls("project-1")
        self.assertEqual(len(calls), 3)
        self.assertEqual({c.call_site for c in calls},
                         {LlmCallSite.COMPARE_JUDGE.value})
        self.assertEqual({c.correlation_id for c in calls}, {"job-1"})
        self.assertEqual({c.outcome for c in calls},
                         {LlmCallOutcome.SUCCESS.value})

    def test_a_repaired_verdict_leaves_two_records_both_successful(self):
        # The recovered first call stays ``success``: the pair was judged, and
        # counting it as a failure would understate the success rate. Repair
        # frequency reads off "two rows under one correlation_id" instead.
        audit = _audit()
        judge = self._judge("not json", _judge_content())
        self._run(judge, audit)
        calls = audit.list_calls("project-1")
        self.assertEqual(len(calls), 2)
        self.assertEqual({c.outcome for c in calls},
                         {LlmCallOutcome.SUCCESS.value})

    def test_a_clean_verdict_leaves_exactly_one_record(self):
        # Over-strict guard for the above: a second row must mean a repair
        # really happened, or the observed repair rate is pinned at 100%.
        audit = _audit()
        judge = self._judge(_judge_content())
        self._run(judge, audit)
        self.assertEqual(len(audit.list_calls("project-1")), 1)

    def test_provider_failure_keeps_its_taxonomy(self):
        audit = _audit()
        judge = self._judge(ProviderError(
            code=ProviderErrorCode.TIMEOUT, message="down", retryable=True))

        async def run():
            with llm_call_scope(audit, project_id="project-1",
                                correlation_id="job-1"):
                with self.assertRaises(ProviderError):
                    await judge.judge(candidate=_judge_candidate(),
                                      memory=_judge_memory())

        asyncio.run(run())
        call = audit.list_calls("project-1")[0]
        self.assertEqual(call.outcome, LlmCallOutcome.PROVIDER_ERROR.value)
        self.assertEqual(call.error_type, "provider_timeout")


class ParseErrorReclassificationTest(unittest.TestCase):
    """D4 — only the last call, and only when the provider actually answered."""

    def test_terminal_rejection_marks_the_repair_call_not_the_first(self):
        audit = _audit()
        provider = _observed(LlmCallSite.COMPARE_JUDGE, "not json", "still not json")
        judge = TerminalJsonCompareJudge(
            provider, prompt_templates=_judge_templates())

        async def run():
            with llm_call_scope(audit, project_id="project-1",
                                correlation_id="job-1") as scope:
                try:
                    await judge.judge(candidate=_judge_candidate(),
                                      memory=_judge_memory())
                except InvalidJudgeResult as exc:
                    scope.reclassify_last_as_parse_error(type(exc).__name__)

        asyncio.run(run())
        calls = sorted(audit.list_calls("project-1"), key=lambda c: c.created_at)
        self.assertEqual(len(calls), 2)
        # The first attempt was recovered-by-retry, not a failure of its own.
        self.assertEqual(calls[0].outcome, LlmCallOutcome.SUCCESS.value)
        self.assertEqual(calls[1].outcome, LlmCallOutcome.PARSE_ERROR.value)
        self.assertEqual(calls[1].error_type, "InvalidJudgeResult")

    def test_a_provider_failure_is_never_relabelled_as_parse_error(self):
        # Over-strict guard, and the reason the operation is named rather than a
        # raw annotate_last: ``ContextSearchFailed(llm_error)`` covers both "the
        # provider never answered" and "its answer was rejected". Relabelling
        # the first would erase the provider code and move a token-less row into
        # the token-aggregation set.
        audit = _audit()
        provider = _observed(LlmCallSite.QUERY_PLANNER, ProviderError(
            code=ProviderErrorCode.UNAVAILABLE, message="down", retryable=True))

        async def run():
            with llm_call_scope(audit, project_id="p1",
                                correlation_id="c1") as scope:
                with self.assertRaises(ProviderError):
                    await provider.generate(object())
                scope.reclassify_last_as_parse_error("ContextSearchFailed")

        asyncio.run(run())
        call = audit.list_calls("p1")[0]
        self.assertEqual(call.outcome, LlmCallOutcome.PROVIDER_ERROR.value)
        self.assertEqual(call.error_type, "provider_unavailable")

    def test_reclassifying_with_no_call_made_records_nothing(self):
        # Over-strict guard: a failure before any provider call must not invent
        # a row, and must not reach back to an earlier workflow's call.
        audit = _audit()

        async def run():
            with llm_call_scope(audit, project_id="p1",
                                correlation_id="c1") as scope:
                scope.reclassify_last_as_parse_error("InvalidJudgeResult")

        asyncio.run(run())
        self.assertEqual(audit.list_calls("p1"), ())

    def test_only_the_llm_error_lineage_reclassifies(self):
        # A store/embedding failure *after* a successful plan is not the
        # planner's fault; marking that plan ``parse_error`` would blame the
        # model for a backend outage.
        from services.application.app.observability.llm_call_scope import (
            reclassify_planner_parse_error,
        )

        audit = _audit()
        provider = _observed(LlmCallSite.QUERY_PLANNER, "plan")

        async def run(error_type):
            with llm_call_scope(audit, project_id=f"p-{error_type.value}",
                                correlation_id="c1") as scope:
                await provider.generate(object())
                reclassify_planner_parse_error(
                    scope, ContextSearchFailed(error_type, "boom"))

        # All four lineages the contract enumerates (SoT §관측 KPI), not a
        # sample: the rule is stated as an enumeration, so the boundary test
        # covers every member. Verification 2026-07-26 H-1.
        self.assertEqual(len(ContextSearchErrorType), 4)
        for error_type, expected in (
            (ContextSearchErrorType.LLM_ERROR, LlmCallOutcome.PARSE_ERROR),
            (ContextSearchErrorType.BACKEND_ERROR, LlmCallOutcome.SUCCESS),
            (ContextSearchErrorType.SYSTEM_ERROR, LlmCallOutcome.SUCCESS),
            (ContextSearchErrorType.SOT_ERROR, LlmCallOutcome.SUCCESS),
        ):
            with self.subTest(error_type=error_type):
                provider._inner.contents = ["plan"]
                asyncio.run(run(error_type))
                call = audit.list_calls(f"p-{error_type.value}")[0]
                self.assertEqual(call.outcome, expected.value)


def _traced_package(project_id="p1"):
    # The context-search endpoint renders the trace, so its package needs one;
    # the writing endpoints do not care either way.
    from services.application.app.context_search.models import (
        ContextSearchTrace, SearchPlan,
    )

    package = _package(project_id)
    return replace(package, trace=ContextSearchTrace(
        plan=SearchPlan(plan_id="plan-1", project_id=project_id, steps=()),
        steps=(), budget_excluded=(),
    ))


class _CallingContext(_Context):
    """A context search that makes one instrumented planner call."""

    def __init__(self, provider):
        super().__init__(_package())
        self.provider = provider

    async def build_context_package(self, request):
        await self.provider.generate(object())
        self.calls += 1
        self.last_request = request
        return _traced_package(request.project_id)


class _CallingGate:
    def __init__(self, provider, *, error=None):
        self.provider = provider
        self.error = error

    async def evaluate(self, *, request, candidate, package):
        await self.provider.generate(object())
        if self.error is not None:
            raise self.error
        return WritingGateResult(request.request_id, request.project_id,
                                 WritingGateDecision.PASS, (), (), "fake-gate")


class _CallingReporter:
    def __init__(self, provider, *, error=None):
        self.provider = provider
        self.error = error

    async def enrich(self, candidate, package):
        await self.provider.generate(object())
        if self.error is not None:
            raise self.error
        return candidate


class _CallingWriting:
    def __init__(self, provider):
        self.provider = provider

    async def generate(self, *, request, package, max_output_tokens=None):
        await self.provider.generate(object())
        return _candidate(project_id=request.project_id)


class _CallingRevision:
    def __init__(self, provider):
        self.provider = provider

    def validate_inputs(self, candidate, finding, instruction):
        return None

    async def revise(self, *, candidate, finding, instruction, package):
        await self.provider.generate(object())
        return candidate


class _CallingCompare:
    def __init__(self, provider, *, turns=2, error=None):
        self.provider = provider
        self.turns = turns
        self.error = error

    async def compare_job(self, *, project_id, job_id, candidates):
        for _ in range(self.turns):
            await self.provider.generate(object())
        if self.error is not None:
            raise self.error
        return ()


class _FailingContext(_Context):
    """A context search whose planner answers, then the plan is rejected."""

    def __init__(self, provider, error):
        super().__init__(_package())
        self.provider = provider
        self.failure = error

    async def build_context_package(self, request):
        await self.provider.generate(object())
        raise self.failure


class _EndpointHarness:
    """App/fixture helpers shared by the two endpoint suites below.

    Not a TestCase: subclassing one suite from the other would silently re-run
    its cases and inflate the counts this project reconciles after every slice.
    """

    def _app(self, audit, **kwargs):
        return create_app(
            CoreSotService(InMemoryCoreSotRepository()),
            llm_call_audit_service=audit,
            **kwargs,
        )

    def _project(self, client):
        return client.post("/projects", json={"name": "Novel"}).json()["id"]

    def _writing_body(self, **over):
        body = {
            "request_id": "wr-1",
            "instruction": "이어서 써줘",
            "candidate_text": "앞 문장. 잘못된 문장. 뒤 문장.",
        }
        body.update(over)
        return body


class EndpointOpensAScopeTest(_EndpointHarness, unittest.TestCase):
    """One guard per request path 증분 C opened (D3).

    Collaborators are stand-ins that make one instrumented provider call — the
    subject here is the endpoint's ``with llm_call_scope(...)``, not the
    adapter's internals (those are pinned above). Delete the ``with`` in any of
    these endpoints and exactly its test fails.
    """

    def _assert_recorded(self, audit, project_id, site, correlation_id):
        calls = [c for c in audit.list_calls(project_id) if c.call_site == site.value]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].correlation_id, correlation_id)
        return calls[0]

    def test_compare_endpoint_scopes_the_whole_job(self):
        from services.application.app.analysis.service import (
            AnalysisService, InMemoryAnalysisRepository,
        )

        audit = _audit()
        provider = _observed(LlmCallSite.COMPARE_JUDGE, "a", "b")
        analysis = AnalysisService(InMemoryAnalysisRepository())
        client = TestClient(self._app(
            audit, analysis_service=analysis,
            compare_service=_CallingCompare(provider)))
        project_id = self._project(client)
        job = client.post(f"/projects/{project_id}/analysis/jobs",
                          json={"snapshot_id": "s1", "idempotency_key": "k1"}
                          ).json()["job"]

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job['id']}/compare")

        self.assertEqual(response.status_code, 200)
        calls = audit.list_calls(project_id)
        # Two judge turns in one job → two rows under the job's correlation_id.
        self.assertEqual(len(calls), 2)
        self.assertEqual({c.correlation_id for c in calls}, {job["id"]})
        self.assertEqual({c.call_site for c in calls},
                         {LlmCallSite.COMPARE_JUDGE.value})

    def test_context_search_endpoint_scopes_the_planner(self):
        audit = _audit()
        provider = _observed(LlmCallSite.QUERY_PLANNER, "plan")
        client = TestClient(self._app(
            audit, context_search_service=_CallingContext(provider)))
        project_id = self._project(client)

        response = client.post(
            f"/projects/{project_id}/context-search",
            json={"idempotency_key": "cs-1", "query": "무엇을 검색할까",
                  "needs": ["canonical_memory"], "max_tokens": 4096},
        )

        self.assertEqual(response.status_code, 200)
        # ``idempotency_key`` is this endpoint's workflow tie.
        self._assert_recorded(audit, project_id, LlmCallSite.QUERY_PLANNER, "cs-1")

    def test_generate_endpoint_scopes_planner_and_generation(self):
        audit = _audit()
        planner = _observed(LlmCallSite.QUERY_PLANNER, "plan")
        writer = _observed(LlmCallSite.WRITING_GENERATION, "prose")
        client = TestClient(self._app(
            audit, context_search_service=_CallingContext(planner),
            writing_service=_CallingWriting(writer)))
        project_id = self._project(client)

        response = client.post(f"/projects/{project_id}/writing/generate",
                               json=self._writing_body())

        self.assertEqual(response.status_code, 200)
        self._assert_recorded(audit, project_id, LlmCallSite.QUERY_PLANNER, "wr-1")
        self._assert_recorded(audit, project_id,
                              LlmCallSite.WRITING_GENERATION, "wr-1")

    def test_report_endpoint_scopes_the_report_call(self):
        audit = _audit()
        planner = _observed(LlmCallSite.QUERY_PLANNER, "plan")
        reporter = _observed(LlmCallSite.WRITING_REPORT, "report")
        client = TestClient(self._app(
            audit, context_search_service=_CallingContext(planner),
            writing_report_service=_CallingReporter(reporter)))
        project_id = self._project(client)

        response = client.post(f"/projects/{project_id}/writing/report",
                               json=self._writing_body())

        self.assertEqual(response.status_code, 200)
        self._assert_recorded(audit, project_id, LlmCallSite.WRITING_REPORT, "wr-1")

    def test_revise_endpoint_scopes_the_revision_call(self):
        audit = _audit()
        planner = _observed(LlmCallSite.QUERY_PLANNER, "plan")
        reviser = _observed(LlmCallSite.WRITING_REVISION, "revised")
        client = TestClient(self._app(
            audit, context_search_service=_CallingContext(planner),
            writing_revision_service=_CallingRevision(reviser)))
        project_id = self._project(client)

        response = client.post(
            f"/projects/{project_id}/writing/revise",
            json=self._writing_body(finding={
                "type": "continuity", "severity": "warning",
                "message": "연속성 수정", "evidence": "잘못된 문장.",
                "recommended_decision": "revise"}),
        )

        self.assertEqual(response.status_code, 200)
        self._assert_recorded(audit, project_id,
                              LlmCallSite.WRITING_REVISION, "wr-1")

    def test_revise_and_gate_endpoint_scopes_every_site_in_the_loop(self):
        # The main workflow, and the reason D3 was not "sync endpoints only":
        # one request spends four different sites, and only a shared
        # correlation_id makes "what did this request cost" answerable.
        audit = _audit()
        planner = _observed(LlmCallSite.QUERY_PLANNER, "plan")
        reviser = _observed(LlmCallSite.WRITING_REVISION, "revised")
        reporter = _observed(LlmCallSite.WRITING_REPORT, "report")
        gate = _observed(LlmCallSite.WRITING_GATE, "gate")
        client = TestClient(self._app(
            audit, context_search_service=_CallingContext(planner),
            writing_revision_service=_CallingRevision(reviser),
            writing_report_service=_CallingReporter(reporter),
            writing_gate_service=_CallingGate(gate)))
        project_id = self._project(client)

        response = client.post(
            f"/projects/{project_id}/writing/revise-and-gate",
            json=self._writing_body(finding={
                "type": "continuity", "severity": "warning",
                "message": "연속성 수정", "evidence": "잘못된 문장.",
                "recommended_decision": "revise"}),
        )

        self.assertEqual(response.status_code, 200)
        sites = {c.call_site for c in audit.list_calls(project_id)}
        self.assertEqual(sites, {
            LlmCallSite.QUERY_PLANNER.value,
            LlmCallSite.WRITING_REVISION.value,
            LlmCallSite.WRITING_REPORT.value,
            LlmCallSite.WRITING_GATE.value,
        })
        self.assertEqual(
            {c.correlation_id for c in audit.list_calls(project_id)}, {"wr-1"})

    def test_accept_endpoint_scopes_its_gate_call(self):
        audit = _audit()
        planner = _observed(LlmCallSite.QUERY_PLANNER, "plan")
        gate = _observed(LlmCallSite.WRITING_GATE, "gate")
        client = TestClient(self._app(
            audit, context_search_service=_CallingContext(planner),
            writing_gate_service=_CallingGate(gate)))
        project_id = self._project(client)
        draft = client.post(f"/projects/{project_id}/drafts",
                            json={"title": "1장"}).json()
        version = client.post(
            f"/projects/{project_id}/drafts/{draft['id']}/versions",
            json={"raw_text": "앞 문장.", "idempotency_key": "v1"},
        ).json()

        response = client.post(
            f"/projects/{project_id}/writing/accept",
            json=self._writing_body(
                draft_id=draft["id"],
                base_version_id=version["draft_version"]["id"],
                idempotency_key="acc-1"),
        )

        self.assertEqual(response.status_code, 200)
        self._assert_recorded(audit, project_id, LlmCallSite.WRITING_GATE, "wr-1")


class EndpointReclassifiesTheFinalRejectionTest(_EndpointHarness, unittest.TestCase):
    """D4 at the request paths, not just on the scope object.

    Reaching ``reclassify_last_as_parse_error`` in a unit test proves the
    operation works; it does not prove any endpoint calls it. Deleting the call
    from an endpoint leaves every other test in this file green — these are the
    ones that bite.
    """

    def _last(self, audit, project_id, site):
        calls = [c for c in audit.list_calls(project_id)
                 if c.call_site == site.value]
        return calls[0]

    def test_compare_endpoint_marks_the_finally_rejected_verdict(self):
        from services.application.app.analysis.service import (
            AnalysisService, InMemoryAnalysisRepository,
        )

        audit = _audit()
        provider = _observed(LlmCallSite.COMPARE_JUDGE, "not json")
        analysis = AnalysisService(InMemoryAnalysisRepository())
        client = TestClient(self._app(
            audit, analysis_service=analysis,
            compare_service=_CallingCompare(
                provider, turns=1,
                error=InvalidJudgeResult("compare judge produced an invalid result"))))
        project_id = self._project(client)
        job = client.post(f"/projects/{project_id}/analysis/jobs",
                          json={"snapshot_id": "s1", "idempotency_key": "k1"}
                          ).json()["job"]

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job['id']}/compare")

        self.assertEqual(response.status_code, 502)
        call = self._last(audit, project_id, LlmCallSite.COMPARE_JUDGE)
        self.assertEqual(call.outcome, LlmCallOutcome.PARSE_ERROR.value)
        self.assertEqual(call.error_type, "InvalidJudgeResult")

    def test_planner_lineage_decides_whether_the_plan_row_is_reclassified(self):
        # Both directions of ``reclassify_planner_parse_error`` at a real
        # endpoint: the planner's own bad answer is a parse_error, a backend
        # outage after a good plan is not the model's fault.
        for error_type, expected in (
            (ContextSearchErrorType.LLM_ERROR, LlmCallOutcome.PARSE_ERROR),
            (ContextSearchErrorType.BACKEND_ERROR, LlmCallOutcome.SUCCESS),
        ):
            with self.subTest(error_type=error_type):
                audit = _audit()
                provider = _observed(LlmCallSite.QUERY_PLANNER, "plan")
                client = TestClient(self._app(
                    audit,
                    context_search_service=_FailingContext(
                        provider, ContextSearchFailed(error_type, "boom"))))
                project_id = self._project(client)

                response = client.post(
                    f"/projects/{project_id}/context-search",
                    json={"idempotency_key": "cs-1", "query": "질의",
                          "needs": ["canonical_memory"], "max_tokens": 4096},
                )

                self.assertEqual(response.status_code, 502)
                call = self._last(audit, project_id, LlmCallSite.QUERY_PLANNER)
                self.assertEqual(call.outcome, expected.value)

    def test_generate_endpoint_marks_a_rejected_self_report(self):
        from services.application.app.writing.report import InvalidCandidateReport

        audit = _audit()
        planner = _observed(LlmCallSite.QUERY_PLANNER, "plan")
        writer = _observed(LlmCallSite.WRITING_GENERATION, "prose")

        class _ReportingWriting(_CallingWriting):
            async def generate(self, *, request, package, max_output_tokens=None):
                await self.provider.generate(object())
                raise InvalidCandidateReport("report field must be an array")

        client = TestClient(self._app(
            audit, context_search_service=_CallingContext(planner),
            writing_service=_ReportingWriting(writer)))
        project_id = self._project(client)

        response = client.post(f"/projects/{project_id}/writing/generate",
                               json=self._writing_body())

        self.assertEqual(response.status_code, 502)
        call = self._last(audit, project_id, LlmCallSite.WRITING_GENERATION)
        self.assertEqual(call.outcome, LlmCallOutcome.PARSE_ERROR.value)
        # The planner's own call is untouched — it answered and was accepted.
        self.assertEqual(
            self._last(audit, project_id, LlmCallSite.QUERY_PLANNER).outcome,
            LlmCallOutcome.SUCCESS.value)

    def test_report_endpoint_marks_a_rejected_report(self):
        from services.application.app.writing.report import InvalidCandidateReport

        audit = _audit()
        planner = _observed(LlmCallSite.QUERY_PLANNER, "plan")
        reporter = _observed(LlmCallSite.WRITING_REPORT, "report")
        client = TestClient(self._app(
            audit, context_search_service=_CallingContext(planner),
            writing_report_service=_CallingReporter(
                reporter, error=InvalidCandidateReport("not an array"))))
        project_id = self._project(client)

        response = client.post(f"/projects/{project_id}/writing/report",
                               json=self._writing_body())

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            self._last(audit, project_id, LlmCallSite.WRITING_REPORT).outcome,
            LlmCallOutcome.PARSE_ERROR.value)

    def test_revise_endpoint_marks_a_rejected_revision(self):
        from services.application.app.writing.revise import InvalidWritingRevision

        audit = _audit()
        planner = _observed(LlmCallSite.QUERY_PLANNER, "plan")
        reviser = _observed(LlmCallSite.WRITING_REVISION, "revised")

        class _FailingRevision(_CallingRevision):
            async def revise(self, *, candidate, finding, instruction, package):
                await self.provider.generate(object())
                raise InvalidWritingRevision("evidence not replaced")

        client = TestClient(self._app(
            audit, context_search_service=_CallingContext(planner),
            writing_revision_service=_FailingRevision(reviser)))
        project_id = self._project(client)

        response = client.post(
            f"/projects/{project_id}/writing/revise",
            json=self._writing_body(finding={
                "type": "continuity", "severity": "warning",
                "message": "연속성 수정", "evidence": "잘못된 문장.",
                "recommended_decision": "revise"}),
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            self._last(audit, project_id, LlmCallSite.WRITING_REVISION).outcome,
            LlmCallOutcome.PARSE_ERROR.value)

    def test_loop_marks_the_stage_that_was_finally_rejected(self):
        # The loop wraps each stage's failure in its own exception, so the
        # endpoint's branches are the only place that knows which site to mark.
        from services.application.app.writing.gate import InvalidWritingGateResult
        from services.application.app.writing.report import InvalidCandidateReport

        for failing, site, error in (
            ("reporter", LlmCallSite.WRITING_REPORT,
             InvalidCandidateReport("not an array")),
            ("gate", LlmCallSite.WRITING_GATE,
             InvalidWritingGateResult("decision missing")),
        ):
            with self.subTest(stage=failing):
                audit = _audit()
                planner = _observed(LlmCallSite.QUERY_PLANNER, "plan")
                reviser = _observed(LlmCallSite.WRITING_REVISION, "revised")
                reporter = _observed(LlmCallSite.WRITING_REPORT, "report")
                gate = _observed(LlmCallSite.WRITING_GATE, "gate")
                client = TestClient(self._app(
                    audit, context_search_service=_CallingContext(planner),
                    writing_revision_service=_CallingRevision(reviser),
                    writing_report_service=_CallingReporter(
                        reporter,
                        error=error if failing == "reporter" else None),
                    writing_gate_service=_CallingGate(
                        gate, error=error if failing == "gate" else None)))
                project_id = self._project(client)

                response = client.post(
                    f"/projects/{project_id}/writing/revise-and-gate",
                    json=self._writing_body(finding={
                        "type": "continuity", "severity": "warning",
                        "message": "연속성 수정", "evidence": "잘못된 문장.",
                        "recommended_decision": "revise"}),
                )

                self.assertEqual(response.status_code, 502)
                self.assertEqual(self._last(audit, project_id, site).outcome,
                                 LlmCallOutcome.PARSE_ERROR.value)

    def test_accept_endpoint_marks_a_rejected_gate_result(self):
        from services.application.app.writing.gate import InvalidWritingGateResult

        audit = _audit()
        planner = _observed(LlmCallSite.QUERY_PLANNER, "plan")
        gate = _observed(LlmCallSite.WRITING_GATE, "gate")
        client = TestClient(self._app(
            audit, context_search_service=_CallingContext(planner),
            writing_gate_service=_CallingGate(
                gate, error=InvalidWritingGateResult("decision missing"))))
        project_id = self._project(client)
        draft = client.post(f"/projects/{project_id}/drafts",
                            json={"title": "1장"}).json()
        version = client.post(
            f"/projects/{project_id}/drafts/{draft['id']}/versions",
            json={"raw_text": "앞 문장.", "idempotency_key": "v1"},
        ).json()

        response = client.post(
            f"/projects/{project_id}/writing/accept",
            json=self._writing_body(
                draft_id=draft["id"],
                base_version_id=version["draft_version"]["id"],
                idempotency_key="acc-1"),
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            self._last(audit, project_id, LlmCallSite.WRITING_GATE).outcome,
            LlmCallOutcome.PARSE_ERROR.value)


class GenerationWorkerOpensAScopeTest(unittest.TestCase):
    """The async presets (D3).

    The worker is outside any request, but it holds the job's real
    ``project_id``/``request_id`` — nothing is guessed. Without this the
    medium/long generations, the expensive ones, would be the only calls the
    KPI never sees.
    """

    def _job_and_collaborators(self, audit, provider):
        from services.application.app.writing.generation_job import (
            InMemoryWritingGenerationJobRepository, WritingGenerationJobService,
        )
        from services.application.app.writing.generation_worker import (
            GenerationCollaborators,
        )
        from services.application.app.writing.scratch import (
            InMemoryWritingScratchRepository, WritingScratchService,
        )

        jobs = WritingGenerationJobService(
            InMemoryWritingGenerationJobRepository())
        enqueued = jobs.enqueue(
            project_id="p1", draft_id="d1", request_id="job-req-1",
            task_type="continue_scene", instruction="이어서 써줘",
            draft_excerpt="", query=None, output_length="medium",
            max_output_tokens=2048, max_tokens=4096, version_id="v1",
        ).job
        claimed = jobs.claim_next()
        collaborators = GenerationCollaborators(
            context_search=_CallingContext(
                _observed(LlmCallSite.QUERY_PLANNER, "plan")),
            writing=_CallingWriting(provider),
            scratch=WritingScratchService(InMemoryWritingScratchRepository()),
            jobs=jobs,
            needs=(),
            llm_call_audit=audit,
        )
        return claimed or enqueued, collaborators

    def test_worker_records_the_generation_it_runs(self):
        from services.application.app.writing.generation_worker import (
            execute_generation_job,
        )

        audit = _audit()
        provider = _observed(LlmCallSite.WRITING_GENERATION, "prose")
        job, collaborators = self._job_and_collaborators(audit, provider)

        asyncio.run(execute_generation_job(job, collaborators))

        calls = audit.list_calls("p1")
        self.assertEqual({c.call_site for c in calls}, {
            LlmCallSite.QUERY_PLANNER.value,
            LlmCallSite.WRITING_GENERATION.value,
        })
        # The job's own request_id ties the worker's calls to the request that
        # enqueued it, so an async generation is not a KPI orphan.
        self.assertEqual({c.correlation_id for c in calls}, {"job-req-1"})

    def test_worker_without_an_audit_records_nothing_and_still_runs(self):
        # Over-strict guard: hand-assembled collaborators (tests, future
        # entrypoints) leave the audit unset, and that must degrade to "no
        # records", never to a crash in the worker loop.
        from dataclasses import replace as _replace

        from services.application.app.writing.generation_worker import (
            execute_generation_job,
        )

        audit = _audit()
        provider = _observed(LlmCallSite.WRITING_GENERATION, "prose")
        job, collaborators = self._job_and_collaborators(audit, provider)
        collaborators = _replace(collaborators, llm_call_audit=None)

        result = asyncio.run(execute_generation_job(job, collaborators))

        self.assertEqual(audit.list_calls("p1"), ())
        self.assertIsNotNone(result)


class CallSiteLiteralsAreDiscoverableTest(unittest.TestCase):
    def test_every_instrumented_site_has_a_literal(self):
        # The literals the aggregation increment will group by. Pinned as a set
        # so adding a site is a deliberate contract edit, not a silent one.
        self.assertEqual(
            {site.value for site in LlmCallSite},
            {"query_planner", "writing_gate", "compare_judge",
             "analysis_extractor", "writing_generation",
             "writing_retrieval_planner", "writing_revision", "writing_report"},
        )

    def test_literals_are_stable_strings(self):
        # They are persisted in ``llm_call_audits`` rows; renaming one orphans
        # every row already written under the old name.
        self.assertEqual(LlmCallSite.WRITING_REPORT.value, "writing_report")
        self.assertEqual(json.dumps(LlmCallSite.WRITING_REVISION.value),
                         '"writing_revision"')
