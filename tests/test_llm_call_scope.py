"""Provider-level LLM call capture (owner decision 2026-07-25, seam C).

Brief ``observability-instrumentation-seam-decisions.md``. The load-bearing
claim of seam C is that a call site making N provider calls leaves N records —
the thing endpoint-level instrumentation structurally cannot do. The analysis
extractor's repair retry is the case the owner named, so it is pinned here
against the real extractor rather than a stand-in.
"""

import asyncio
from dataclasses import replace
import json
import unittest

from services.application.app.analysis.extractor import (
    VersionedPromptAnalysisExtractionAdapter,
)
from services.application.app.analysis.models import SnapshotText
from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository, PromptTemplateService,
)
from services.application.app.core_sot.models import SourceRef
from services.application.app.observability.llm_call_audit import (
    InMemoryLlmCallAuditRepository, LlmCallAuditService, LlmCallOutcome,
    LlmCallSite,
)
from services.application.app.observability.llm_call_scope import (
    ObservedProvider, current_scope, llm_call_scope,
)
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.provider import GenerationResult, TokenUsage


class _Provider:
    """Answers with a scripted sequence, one entry per call."""

    def __init__(self, *contents, error=None):
        self.contents = list(contents)
        self.error = error
        self.calls = 0

    async def generate(self, request):
        self.calls += 1
        if self.error is not None:
            raise self.error
        content = self.contents.pop(0)
        return GenerationResult(model=f"fake-{self.calls}", content=content,
                                finish_reason="stop",
                                usage=TokenUsage(self.calls, self.calls))


class _Request:
    """`ObservedProvider`가 요청에서 읽는 것은 출력 상한뿐이다."""

    def __init__(self, *, max_tokens: int | None = None):
        self.max_tokens = max_tokens


class _WindowAwareProvider(_Provider):
    """창을 신고하는 provider(게이트웨이 경유 실 provider와 같은 모양)."""

    def __init__(self, *contents, context_window: int | None = None):
        super().__init__(*(contents or ("a",)))
        self._context_window = context_window

    async def generate(self, request):
        result = await super().generate(request)
        return replace(result, context_window=self._context_window)


def _audit():
    return LlmCallAuditService(InMemoryLlmCallAuditRepository())


def _observed(provider, site=LlmCallSite.ANALYSIS_EXTRACTOR):
    return ObservedProvider(provider, call_site=site)


class ScopeCaptureTest(unittest.TestCase):
    def test_each_provider_call_leaves_its_own_record(self):
        # The core claim of seam C. Three calls in one scope → three records,
        # in call order, each with its own model/tokens.
        audit = _audit()
        provider = _observed(_Provider("a", "b", "c"))

        async def run():
            with llm_call_scope(audit, project_id="p1", correlation_id="job-1"):
                for _ in range(3):
                    await provider.generate(object())

        asyncio.run(run())
        calls = audit.list_calls("p1")
        self.assertEqual(len(calls), 3)
        self.assertEqual({c.correlation_id for c in calls}, {"job-1"})
        self.assertEqual({c.call_site for c in calls},
                         {LlmCallSite.ANALYSIS_EXTRACTOR.value})
        # Per-call token values, not a single summed row.
        self.assertEqual(sorted(c.total_tokens for c in calls), [2, 4, 6])
        self.assertEqual(sorted(c.model for c in calls),
                         ["fake-1", "fake-2", "fake-3"])

    def test_input_and_output_tokens_are_recorded_separately(self):
        """컨텍스트 효율 분석의 전제 — 입력과 출력이 분리돼 있어야 한다.

        오너 목적(2026-07-29)은 "효과적인 자원 배분"과 "컨텍스트 양 효율성 분석"이다.
        그러려면 **창의 얼마를 입력에 쓰는가**를 물을 수 있어야 하는데, `total_tokens`
        하나로는 답할 수 없다 — 입력 8,000/출력 500과 입력 500/출력 8,000이 같은 값으로
        접힌다. 게이트웨이는 `prompt_tokens`·`completion_tokens`를 이미 돌려주고
        (`llm_gateway/app/main.py`) 앱 provider도 파싱하는데, 종전에는
        `ObservedProvider`가 **`total_tokens`만 취해 분해를 버렸다.**

        under-strict: 다시 분해를 버리면 두 필드가 None이 되어 실패.
        over-strict: 합이 분해와 어긋나면(어느 한쪽만 기록하는 등) 실패.
        """
        audit = _audit()
        provider = _observed(_Provider("a"))

        async def run():
            with llm_call_scope(audit, project_id="p1", correlation_id="job-1"):
                await provider.generate(object())

        asyncio.run(run())
        call = audit.list_calls("p1")[0]
        # _Provider는 n번째 호출에서 TokenUsage(n, n)을 낸다 → 첫 호출은 입력 1·출력 1.
        self.assertEqual(call.prompt_tokens, 1)
        self.assertEqual(call.completion_tokens, 1)
        self.assertEqual(call.total_tokens, 2)
        self.assertEqual(
            call.prompt_tokens + call.completion_tokens,
            call.total_tokens,
            "분해와 합이 어긋난다 — 둘 중 하나가 다른 호출의 값이거나 누락됐다",
        )

    def test_window_and_output_cap_are_recorded_so_headroom_is_derivable(self):
        """자원 배분 지표의 **분모**. 1a가 분자(입력 토큰)를 채웠고 이것이 분모다.

        `입력 + 출력 상한 ≤ 창`을 사후에 판정하려면 세 값이 필요하다 — 입력(1a), 출력 상한,
        그리고 창. 앞의 둘만으로는 "입력 1,851"이 많은지 적은지 말할 수 없다.

        **헤드룸 자체는 저장하지 않는다.** `창 − 입력 − 출력상한`은 파생값이고, 파생값을
        저장하면 세 원천값과 조용히 갈라진다. 저장하는 것은 원천값뿐이다.

        관측만이다 — 초과해도 요청은 그대로 통과한다(오너 결정 2026-07-29).
        """
        audit = _audit()
        provider = _observed(_WindowAwareProvider(context_window=16384))

        async def run():
            with llm_call_scope(audit, project_id="p1", correlation_id="job-1"):
                await provider.generate(_Request(max_tokens=6144))

        asyncio.run(run())
        call = audit.list_calls("p1")[0]
        self.assertEqual(call.context_window, 16384)
        self.assertEqual(call.max_output_tokens, 6144)
        # 세 원천값으로 헤드룸이 완전히 판정된다.
        headroom = call.context_window - call.prompt_tokens - call.max_output_tokens
        self.assertEqual(headroom, 16384 - 1 - 6144)

    def test_unknown_window_is_none_so_headroom_is_not_faked(self):
        """창을 모르면 `None`이다 — 0도, 어떤 기본값도 아니다.

        게이트웨이가 `/props`를 못 읽었거나(외부 서버 장애) provider가 창을 신고하지 않는
        구성이면 창을 **모른다**. 여기서 임의의 기본값(8192 등)을 넣으면 **헤드룸이 지어낸
        숫자 위에서 계산**되고, 그 값이 지표에 섞여 "여유가 있다/없다"를 거짓으로 말한다.
        분해 토큰의 `None`과 같은 규칙이다(SoT v1.7.58).
        """
        audit = _audit()
        provider = _observed(_Provider("a"))  # 창을 신고하지 않는 provider

        async def run():
            with llm_call_scope(audit, project_id="p1", correlation_id="job-1"):
                await provider.generate(_Request(max_tokens=1024))

        asyncio.run(run())
        call = audit.list_calls("p1")[0]
        self.assertIsNone(call.context_window)
        # 출력 상한은 요청에서 오므로 창을 몰라도 알 수 있다.
        self.assertEqual(call.max_output_tokens, 1024)

    def test_provider_error_leaves_the_split_unknown_not_zero(self):
        """실패한 호출의 분해는 **0이 아니라 '모른다'**여야 한다.

        provider가 답하지 않았으므로 입력 토큰도 알 수 없다. 0으로 적으면 집계가
        "입력을 0 토큰 썼다"로 읽어 **효율 지표를 낙관 쪽으로 오염**시킨다. 계약이
        `total_tokens`의 0을 "모른다"로 정의한 것과 같은 이유이며(SoT §관측 KPI),
        분해는 `None`으로 그 사실을 **명시**할 수 있다.
        """
        audit = _audit()
        provider = _observed(_Provider(error=ProviderError(
            code=ProviderErrorCode.TIMEOUT, message="down", retryable=True)))

        async def run():
            with llm_call_scope(audit, project_id="p1", correlation_id="job-1"):
                with self.assertRaises(ProviderError):
                    await provider.generate(object())

        asyncio.run(run())
        call = audit.list_calls("p1")[0]
        self.assertIsNone(call.prompt_tokens)
        self.assertIsNone(call.completion_tokens)

    def test_a_failed_call_still_records_what_it_asked_for(self):
        """관측 1b — 실패한 호출도 **요청한 출력 상한**은 남긴다(독립 검증 B5).

        응답이 없으므로 창과 토큰은 모르지만, 출력 상한은 **요청에서** 온다. 실패한 호출이
        얼마를 요구했는지는 자원 분석에 유효한 정보다 — 큰 상한을 요구한 호출이 자주
        실패한다면 그 자체가 신호다. SoT §관측 KPI가 명시한 분기이며, 지우면 그 신호가
        조용히 사라진다.
        """
        audit = _audit()
        provider = _observed(_Provider(error=ProviderError(
            code=ProviderErrorCode.TIMEOUT, message="down", retryable=True)))

        async def run():
            with llm_call_scope(audit, project_id="p1", correlation_id="job-1"):
                with self.assertRaises(ProviderError):
                    await provider.generate(_Request(max_tokens=6144))

        asyncio.run(run())
        call = audit.list_calls("p1")[0]
        self.assertEqual(call.max_output_tokens, 6144)
        # 응답이 없으므로 창은 모른다 — 여기서 값을 지어내지 않는다.
        self.assertIsNone(call.context_window)

    def test_provider_failure_is_recorded_and_still_raises(self):
        audit = _audit()
        provider = _observed(_Provider(error=ProviderError(
            code=ProviderErrorCode.TIMEOUT, message="down", retryable=True)))

        async def run():
            with llm_call_scope(audit, project_id="p1", correlation_id="job-1"):
                with self.assertRaises(ProviderError):
                    await provider.generate(object())

        asyncio.run(run())
        call = audit.list_calls("p1")[0]
        self.assertEqual(call.outcome, LlmCallOutcome.PROVIDER_ERROR.value)
        self.assertEqual(call.error_type, "provider_timeout")
        self.assertEqual(call.total_tokens, 0)

    def test_calls_are_flushed_even_when_the_request_fails(self):
        # Under-strict guard for the ``finally`` flush: a workflow that blows up
        # after its LLM calls still made them, and a failure-rate KPI needs
        # exactly those.
        audit = _audit()
        provider = _observed(_Provider("a"))

        async def run():
            with llm_call_scope(audit, project_id="p1", correlation_id="job-1"):
                await provider.generate(object())
                raise RuntimeError("later step exploded")

        with self.assertRaisesRegex(RuntimeError, "later step exploded"):
            asyncio.run(run())
        self.assertEqual(len(audit.list_calls("p1")), 1)

    def test_calls_outside_any_scope_are_not_recorded(self):
        # Over-strict guard. Worker entrypoints and scripts call providers with
        # no request context; inventing a project_id there would file the call
        # under a workflow that never happened.
        audit = _audit()
        provider = _observed(_Provider("a"))
        asyncio.run(provider.generate(object()))
        self.assertEqual(audit.list_calls("p1"), ())
        self.assertIsNone(current_scope())

    def test_annotation_lands_on_the_call_it_describes(self):
        # The seam's answer to "the provider cannot know a domain verdict".
        audit = _audit()
        provider = _observed(_Provider("a", "b"))

        async def run():
            with llm_call_scope(audit, project_id="p1",
                                correlation_id="wr1") as scope:
                await provider.generate(object())
                scope.annotate_last(decision="revise", gate_quality_score=0.3)
                await provider.generate(object())
                scope.annotate_last(outcome=LlmCallOutcome.PARSE_ERROR)

        asyncio.run(run())
        calls = sorted(audit.list_calls("p1"), key=lambda c: c.total_tokens)
        self.assertEqual(calls[0].decision, "revise")
        self.assertEqual(calls[0].gate_quality_score, 0.3)
        self.assertEqual(calls[0].outcome, LlmCallOutcome.SUCCESS.value)
        # The second call was re-labelled by the domain, and the first was not
        # touched — annotation applies to the latest call, not to all of them.
        self.assertEqual(calls[1].outcome, LlmCallOutcome.PARSE_ERROR.value)
        self.assertIsNone(calls[1].decision)

    def test_annotating_with_no_call_made_is_a_no_op(self):
        # Over-strict guard: a pre-call failure has no call to annotate, and
        # must not conjure a record for one that never happened.
        audit = _audit()

        async def run():
            with llm_call_scope(audit, project_id="p1",
                                correlation_id="wr1") as scope:
                scope.annotate_last(outcome=LlmCallOutcome.PARSE_ERROR)

        asyncio.run(run())
        self.assertEqual(audit.list_calls("p1"), ())

    def test_audit_failure_does_not_break_the_workflow(self):
        # SoT §관측 KPI 격리 조항. The flush runs in a ``finally``, so a raising
        # audit store would also replace the request's own exception — this is
        # what keeps the real failure visible.
        class _FailingRepo:
            def add(self, call):
                raise RuntimeError("audit store down")

            def list_for_project(self, project_id):
                return ()

        audit = LlmCallAuditService(_FailingRepo())
        provider = _observed(_Provider("a"))

        async def run():
            with llm_call_scope(audit, project_id="p1", correlation_id="job-1"):
                await provider.generate(object())
            return "completed"

        self.assertEqual(asyncio.run(run()), "completed")

    def test_concurrent_scopes_do_not_mix_their_calls(self):
        # Isolation is a correctness property, not a nicety: a leak would file
        # one project's LLM call under another project's workflow.
        audit = _audit()

        async def one(project):
            provider = _observed(_Provider("a"))
            with llm_call_scope(audit, project_id=project,
                                correlation_id=f"job-{project}"):
                await asyncio.sleep(0.01)
                await provider.generate(object())

        async def run():
            await asyncio.gather(*(one(f"p{i}") for i in range(10)))

        asyncio.run(run())
        for i in range(10):
            calls = audit.list_calls(f"p{i}")
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0].correlation_id, f"job-p{i}")


class _Catalog:
    def __init__(self, source_refs):
        self._source_refs = tuple(source_refs)

    def list_source_refs(self, *, project_id: str, snapshot_id: str):
        return tuple(
            ref for ref in self._source_refs
            if ref.project_id == project_id and ref.snapshot_id == snapshot_id
        )


def _source_ref():
    return SourceRef(
        id="source-ref-1", project_id="project-1", snapshot_id="snapshot-1",
        block_id="block-1", start_offset=0, end_offset=2, quote="민아",
        content_hash="hash-1",
    )


def _snapshot():
    return SnapshotText(
        project_id="project-1", snapshot_id="snapshot-1",
        raw_text="민아는 편지를 발견했다.", content_hash="hash-1",
        block_ids=("block-1",),
    )


def _extract_output():
    return json.dumps({"candidates": [{
        "candidate_type": "character_observation",
        "provenance": "source_observed",
        "confidence": 0.8,
        "source_anchors": [{
            "source_ref_id": "source-ref-1", "start_offset": 0,
            "end_offset": 2, "quote": "민아", "content_hash": "hash-1",
        }],
        "payload": {"name": "민아", "observation": "민아가 편지를 발견했다."},
    }]}, ensure_ascii=False)


class ExtractorRepairIsRecordedTest(unittest.TestCase):
    """The case that motivated seam C, pinned against the real extractor.

    ``_repair_once`` makes a second provider call after non-JSON output. At the
    endpoint level both calls hide behind one successful response, so the
    repair rate the owner asked to observe is unobtainable there.
    """

    def _adapter(self, provider):
        templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        templates.seed_analysis_extract_v4()
        templates.seed_analysis_extract_v5()
        return VersionedPromptAnalysisExtractionAdapter(
            _observed(provider), prompt_templates=templates,
            source_ref_catalog=_Catalog((_source_ref(),)), max_tokens=256,
        )

    def _run(self, provider, audit):
        async def run():
            with llm_call_scope(audit, project_id="p1", correlation_id="job-1"):
                return await self._adapter(provider).extract(_snapshot())

        return asyncio.run(run())

    def test_a_repaired_extraction_leaves_two_records_not_one(self):
        audit = _audit()
        provider = _Provider("not json at all", _extract_output())
        drafts = self._run(provider, audit)
        self.assertEqual(len(drafts), 1)          # the caller still succeeds
        self.assertEqual(provider.calls, 2)       # …after two provider calls
        calls = audit.list_calls("p1")
        self.assertEqual(len(calls), 2)           # …and both are visible
        self.assertEqual({c.call_site for c in calls},
                         {LlmCallSite.ANALYSIS_EXTRACTOR.value})
        self.assertEqual({c.correlation_id for c in calls}, {"job-1"})
        # Both were provider successes — the first call's *content* was bad,
        # which is a domain verdict the provider layer does not claim to know.
        self.assertEqual({c.outcome for c in calls},
                         {LlmCallOutcome.SUCCESS.value})

    def test_a_clean_extraction_leaves_exactly_one_record(self):
        # Over-strict guard: the second record must appear only when a repair
        # actually happened, or the observed repair rate is inflated to 100%.
        audit = _audit()
        provider = _Provider(_extract_output())
        self._run(provider, audit)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(len(audit.list_calls("p1")), 1)


class RunEndpointOpensAScopeTest(unittest.TestCase):
    """The endpoint wiring itself, not just the seam in isolation.

    ``ObservedProvider`` only records inside a scope, so instrumenting the
    extractor is useless unless ``/analysis/jobs/{id}/run`` actually opens one
    around the runner. Removing the ``with llm_call_scope(...)`` in main.py
    would leave every unit test above green — this is the one that bites.
    """

    def _client(self, runner, audit):
        from tests.auth_support import (  # noqa: PLC0415
            AuthenticatedTestClient as TestClient,
        )

        from services.application.app.analysis.service import (  # noqa: PLC0415
            AnalysisService, InMemoryAnalysisRepository,
        )
        from services.application.app.core_sot.service import (  # noqa: PLC0415
            CoreSotService, InMemoryCoreSotRepository,
        )
        from services.application.app.main import create_app  # noqa: PLC0415

        analysis = AnalysisService(InMemoryAnalysisRepository())
        app = create_app(
            CoreSotService(InMemoryCoreSotRepository()),
            analysis_service=analysis,
            analysis_runner=runner(analysis),
            llm_call_audit_service=audit,
        )
        client = TestClient(app)
        project = client.post("/projects", json={"name": "Novel"}).json()
        job = client.post(
            f"/projects/{project['id']}/analysis/jobs",
            json={"snapshot_id": "snapshot-1", "idempotency_key": "run-1"},
        ).json()
        return client, project["id"], job["job"]["id"]

    def _runner_factory(self, provider):
        from tests.test_application_api import _ApiFakeAnalysisRunner  # noqa: PLC0415

        class _CallingRunner(_ApiFakeAnalysisRunner):
            async def run_job(self, *, project_id, job_id):
                # Stands in for the extractor: one instrumented provider call
                # made while the endpoint is serving the request.
                await provider.generate(object())
                return await super().run_job(project_id=project_id, job_id=job_id)

        return _CallingRunner

    def test_run_endpoint_records_the_calls_its_runner_makes(self):
        audit = _audit()
        provider = _observed(_Provider("a"))
        client, project_id, job_id = self._client(
            self._runner_factory(provider), audit)

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job_id}/run")

        self.assertEqual(response.status_code, 200)
        calls = audit.list_calls(project_id)
        self.assertEqual(len(calls), 1)
        # correlation_id is the job: every call made while running it groups here.
        self.assertEqual(calls[0].correlation_id, job_id)
        self.assertEqual(calls[0].call_site,
                         LlmCallSite.ANALYSIS_EXTRACTOR.value)
        self.assertEqual(calls[0].outcome, LlmCallOutcome.SUCCESS.value)

    def test_replayed_run_makes_no_call_and_records_none(self):
        # Over-strict guard: an idempotent replay returns early without touching
        # the provider, so it must not add a record — otherwise call counts grow
        # every time a client re-POSTs a finished job.
        audit = _audit()
        provider = _observed(_Provider("a", "b"))
        client, project_id, job_id = self._client(
            self._runner_factory(provider), audit)
        path = f"/projects/{project_id}/analysis/jobs/{job_id}/run"

        self.assertEqual(client.post(path).status_code, 200)
        self.assertEqual(client.post(path).status_code, 200)

        self.assertEqual(len(audit.list_calls(project_id)), 1)


class DefaultAssemblyIsInstrumentedTest(unittest.TestCase):
    """The deployed assembly, not the test harness.

    Every other regression builds ``ObservedProvider`` itself, so
    ``_default_*`` could stop wrapping its provider and they would all stay
    green while the deployed app records nothing at all. Measured before adding
    these: stripping the wrapper from the gate assembly left 56 tests passing.
    """

    def test_gate_assembly_instruments_the_provider_it_builds(self):
        # Behavioural, not structural: build through the real factory (feeding
        # it a fake provider the way the operator diagnostic does) and check a
        # call through it actually lands in the audit.
        import os  # noqa: PLC0415
        from unittest import mock  # noqa: PLC0415

        from services.application.app.main import (  # noqa: PLC0415
            _default_writing_gate_service,
        )
        from tests.test_writing_gate import (  # noqa: PLC0415
            _Provider as _GateProvider, _candidate, _package, _request,
        )

        with mock.patch.dict(os.environ, {"LLM_GATEWAY_BASE_URL": "http://gw"}):
            service = _default_writing_gate_service(provider=_GateProvider())
        audit = _audit()

        async def run():
            with llm_call_scope(audit, project_id="p1", correlation_id="wr1"):
                await service.evaluate(request=_request(), candidate=_candidate(),
                                       package=_package())

        asyncio.run(run())
        calls = audit.list_calls("p1")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].call_site, LlmCallSite.WRITING_GATE.value)

    def test_extractor_assembly_instruments_the_provider_it_builds(self):
        # Structural: this factory builds its provider internally, so there is
        # no seam to feed a fake through. Reaching for the private attribute is
        # the only way to assert the deployed graph is wrapped.
        import os  # noqa: PLC0415
        from unittest import mock  # noqa: PLC0415

        from services.application.app.analysis.service import (  # noqa: PLC0415
            AnalysisService, InMemoryAnalysisRepository,
        )
        from services.application.app.core_sot.service import (  # noqa: PLC0415
            CoreSotService, InMemoryCoreSotRepository,
        )
        from services.application.app.main import (  # noqa: PLC0415
            _default_analysis_runner,
        )

        with mock.patch.dict(os.environ, {"LLM_GATEWAY_BASE_URL": "http://gw"}):
            core_sot = CoreSotService(InMemoryCoreSotRepository())
            # The runner refuses to build without source validation, so the
            # resolver has to be present for the factory to run at all.
            runner = _default_analysis_runner(
                core_sot=core_sot,
                analysis=AnalysisService(InMemoryAnalysisRepository(),
                                         source_ref_resolver=core_sot),
            )
        provider = runner._extractor._provider
        self.assertIsInstance(provider, ObservedProvider)
        self.assertEqual(provider._call_site, LlmCallSite.ANALYSIS_EXTRACTOR)
