"""Phase 5.3 Writing accept→save→pending-analysis regressions."""

import asyncio
import os
import unittest
from unittest.mock import patch
from dataclasses import replace

import httpx

from services.application.app.analysis.models import AnalysisJobStatus
from services.application.app.analysis.service import AnalysisService, InMemoryAnalysisRepository
from services.application.app.context_search.models import (
    ContextPackage, ContextSearchErrorType, ContextSearchPurpose,
)
from services.application.app.context_search.service import (
    ContextSearchBudgetExceeded, ContextSearchFailed,
)
from services.application.app.core_sot.models import UnitKind
from services.application.app.core_sot.service import (
    Archived, CoreSotService, InMemoryCoreSotRepository,
)
from services.application.app.core_sot.repository import (
    DuplicateWritingAcceptReceipt,
)
from services.application.app.activity.log import (
    ActivityLogService,
    InMemoryActivityLogRepository,
)
from services.application.app.main import create_app
from services.application.app.writing.accept import (
    StaleWritingBase, WritingAcceptAnalysisError, WritingAcceptService,
    _append_patch, analysis_job_key,
)
from services.application.app.writing.models import (
    CandidateClaim, CandidateClaimType, NextUnit, WritingCandidate,
    WritingGateDecision, WritingGateResult, WritingIntent,
    WritingOutputType, WritingRequest, WritingTaskType,
)
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from tests.auth_support import authenticate


def _package(project="project-1"):
    return ContextPackage(project_id=project,
        purpose=ContextSearchPurpose.WRITING_CONTEXT,
        macro_items=(), micro_evidence=(), constraints=(), do_not_use=(),
        token_estimate_total=0, degraded=False)


def _request(project="project-1"):
    return WritingRequest("wr1", project, WritingTaskType.CONTINUE_SCENE,
                          "이어서 써줘")


def _candidate(project="project-1", text="새 문단."):
    return WritingCandidate("wr1", project, WritingTaskType.CONTINUE_SCENE,
        WritingOutputType.DRAFT_PATCH, text)


class _ReceiptRaceCore:
    """`start_next_unit` 이 중복 영수증을 알리는데 그 영수증이 아직 안 읽히는 창.

    Mongo 에서 실제로 열리는 창이다 — 중복 키 오류는 다른 트랜잭션이 **썼다**는
    신호이고, 그 트랜잭션이 아직 커밋 전이면 뒤따르는 읽기는 **못 본다**.

    `receipt_readable=True` 는 그 반대쪽(이미 보이는 정상 수렴)을 만든다. 두 방향이
    다 필요하다 — accept.py 의 그 자리는 한쪽만 보고 짜여 있었다.
    """

    def __init__(self, inner, *, receipt_readable):
        self._inner = inner
        self._receipt_readable = receipt_readable

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def start_next_unit(self, **kwargs):
        if self._receipt_readable:
            # 다른 트랜잭션이 이미 커밋한 상태를 만든다.
            self._inner.start_next_unit(**kwargs)
        raise DuplicateWritingAcceptReceipt(kwargs["idempotency_key"])

    def get_writing_accept_receipt(self, *, project_id, idempotency_key):
        if not self._receipt_readable:
            return None
        return self._inner.get_writing_accept_receipt(
            project_id=project_id, idempotency_key=idempotency_key)


class _Gate:
    def __init__(self, decision=WritingGateDecision.PASS, *, error=None):
        self.decision = decision
        self.error = error
        self.calls = 0
    async def evaluate(self, *, request, candidate, package):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return WritingGateResult(request.request_id, request.project_id,
            self.decision, (), (), "fake-gate")


class _FailingAnalysis(AnalysisService):
    def __init__(self, repository):
        super().__init__(repository)
        self.fail = True
    def create_job(self, **kwargs):
        if self.fail:
            raise RuntimeError("analysis store down")
        return super().create_job(**kwargs)


class _Context:
    def __init__(self, *, error=None):
        self.error = error
    async def build_context_package(self, request):
        if self.error is not None:
            raise self.error
        return _package(request.project_id)


class _Reporter:
    async def enrich(self, candidate, package):
        return replace(candidate, candidate_claims=(CandidateClaim(
            "문이 열렸다", CandidateClaimType.NARRATIVE_EVENT, True),))


class WritingAcceptServiceTest(unittest.TestCase):
    def setUp(self):
        self.core = CoreSotService(InMemoryCoreSotRepository())
        project = self.core.create_project(name="Novel")
        self.project = project.id
        self.draft = self.core.create_draft(project_id=project.id, title="Draft")
        self.base = self.core.save_draft(project_id=project.id,
            draft_id=self.draft.id, raw_text="기존 문단.", idempotency_key="base")
        self.analysis_repo = InMemoryAnalysisRepository()
        self.analysis = AnalysisService(self.analysis_repo)
        self.gate = _Gate()

    def _service(self, analysis=None, reporter=None):
        return WritingAcceptService(core_sot=self.core,
            analysis=analysis or self.analysis, gate=self.gate,
            reporter=reporter)

    def _accept(self, *, key="accept-1", base=None, candidate=None):
        return asyncio.run(self._service().accept(
            draft_id=self.draft.id,
            base_version_id=base or self.base.draft_version.id,
            idempotency_key=key, request=_request(self.project),
            candidate=candidate or _candidate(self.project),
            package=_package(self.project)))

    def test_append_literal_all_boundaries(self):
        self.assertEqual(_append_patch("", "새 글"), "새 글")
        self.assertEqual(_append_patch("기존\n", "새 글"), "기존\n새 글")
        self.assertEqual(_append_patch("기존", "새 글"), "기존\n\n새 글")

    def test_pass_saves_new_version_and_creates_pending_job(self):
        result = self._accept()
        self.assertTrue(result.accepted)
        self.assertEqual(result.saved.snapshot.raw_text, "기존 문단.\n\n새 문단.")
        self.assertIs(result.analysis_job.status, AnalysisJobStatus.PENDING)
        self.assertEqual(result.analysis_job.snapshot_id, result.saved.snapshot.id)
        self.assertEqual(len(self.core.list_draft_versions(
            project_id=self.project, draft_id=self.draft.id)), 2)

    def test_analysis_job_key_is_snapshot_scoped_and_shared_with_trigger(self):
        # D5=A alignment: accept's analysis job key is derived from the snapshot,
        # so the explicit "이 원고 분석" trigger — which only knows the snapshot —
        # reuses the SAME job via create_job's (project, snapshot, key)
        # idempotency, instead of minting a new one (no orphan, no duplicate).
        result = self._accept()
        snapshot_id = result.saved.snapshot.id
        self.assertEqual(result.analysis_job.idempotency_key,
                         analysis_job_key(snapshot_id))
        # The trigger's create_job with the same derived key replays accept's job.
        replay = self.analysis.create_job(
            project_id=self.project, snapshot_id=snapshot_id,
            idempotency_key=analysis_job_key(snapshot_id))
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.job.id, result.analysis_job.id)
        self.assertEqual(len(self.analysis_repo.jobs), 1)  # one shared job

    def test_non_pass_is_normal_no_write_outcome(self):
        for decision in (WritingGateDecision.REVISE,
                         WritingGateDecision.RETRIEVE_MORE,
                         WritingGateDecision.NEEDS_USER_REVIEW,
                         WritingGateDecision.BLOCK):
            with self.subTest(decision=decision):
                self.gate.decision = decision
                result = self._accept(key=f"non-pass-{decision.value}")
                self.assertFalse(result.accepted)
                self.assertIs(result.gate.decision, decision)
                self.assertIsNone(result.saved)
        self.assertEqual(len(self.core.list_draft_versions(
            project_id=self.project, draft_id=self.draft.id)), 1)
        self.assertEqual(self.analysis_repo.jobs, {})

    def test_stale_base_rejected_before_gate(self):
        newer = self.core.save_draft(project_id=self.project,
            draft_id=self.draft.id, raw_text="manual", idempotency_key="manual")
        with self.assertRaises(StaleWritingBase):
            self._accept(base=self.base.draft_version.id)
        self.assertEqual(self.gate.calls, 0)
        self.assertEqual(newer.draft_version.version_number, 2)

    def test_same_key_replays_without_gate_or_duplicate(self):
        first = self._accept()
        calls = self.gate.calls
        replay = self._accept(candidate=_candidate(self.project, "다른 글"))
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.saved.draft_version.id,
                         first.saved.draft_version.id)
        self.assertEqual(replay.analysis_job.id, first.analysis_job.id)
        self.assertEqual(self.gate.calls, calls)
        self.assertEqual(len(self.analysis_repo.jobs), 1)

    def test_different_key_creates_next_version_and_job(self):
        first = self._accept(key="one")
        second = self._accept(key="two", base=first.saved.draft_version.id)
        self.assertNotEqual(first.saved.draft_version.id,
                            second.saved.draft_version.id)
        self.assertEqual(len(self.analysis_repo.jobs), 2)

    def test_job_failure_exposes_saved_and_retry_converges(self):
        repo = InMemoryAnalysisRepository()
        failing = _FailingAnalysis(repo)
        service = self._service(failing)
        kwargs = dict(draft_id=self.draft.id,
            base_version_id=self.base.draft_version.id,
            idempotency_key="partial", request=_request(self.project),
            candidate=_candidate(self.project), package=_package(self.project))
        with self.assertRaises(WritingAcceptAnalysisError) as raised:
            asyncio.run(service.accept(**kwargs))
        saved_id = raised.exception.saved.draft_version.id
        failing.fail = False
        replay = asyncio.run(service.accept(**kwargs))
        self.assertEqual(replay.saved.draft_version.id, saved_id)
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(len(repo.jobs), 1)

    def test_archived_draft_blocks_replay_before_job_or_gate(self):
        first = self._accept()
        self.core.archive_draft(project_id=self.project, draft_id=self.draft.id)
        calls = self.gate.calls
        with self.assertRaises(Archived):
            self._accept()
        self.assertEqual(self.gate.calls, calls)
        self.assertEqual(len(self.analysis_repo.jobs), 1)
        self.assertIsNotNone(first.analysis_job)

    def test_cross_project_candidate_and_package_stop_before_gate(self):
        for candidate, package in (
            (_candidate("other"), _package(self.project)),
            (_candidate(self.project), _package("other")),
        ):
            with self.subTest(candidate_project=candidate.project_id,
                              package_project=package.project_id), \
                    self.assertRaisesRegex(ValueError, "different projects"):
                asyncio.run(self._service().accept(
                    draft_id=self.draft.id,
                    base_version_id=self.base.draft_version.id,
                    idempotency_key="cross", request=_request(self.project),
                    candidate=candidate, package=package))
        self.assertEqual(self.gate.calls, 0)

    def test_accepted_report_is_copied_to_pending_analysis_job(self):
        result = asyncio.run(self._service(reporter=_Reporter()).accept(
            draft_id=self.draft.id,
            base_version_id=self.base.draft_version.id,
            idempotency_key="report", request=_request(self.project),
            candidate=_candidate(self.project), package=_package(self.project)))
        report = result.analysis_job.writing_candidate_report
        self.assertEqual(report["candidate_claims"][0]["text"], "문이 열렸다")
        self.assertEqual(report["candidate_claims"][0]["type"],
                         "narrative_event")
        self.assertNotIn("claim_type", report["candidate_claims"][0])
        self.assertIs(result.analysis_job.status, AnalysisJobStatus.PENDING)


class WritingAcceptApiTest(unittest.TestCase):
    def _setup(self, *, decision=WritingGateDecision.PASS, analysis=None,
               gate_error=None, context_error=None, activity_repo=None):
        core = CoreSotService(InMemoryCoreSotRepository())
        project = core.create_project(name="Novel")
        draft = core.create_draft(project_id=project.id, title="Draft")
        base = core.save_draft(project_id=project.id, draft_id=draft.id,
            raw_text="기존.", idempotency_key="base")
        analysis = analysis or AnalysisService(InMemoryAnalysisRepository())
        gate = _Gate(decision, error=gate_error)
        app = create_app(service=core, analysis_service=analysis,
            context_search_service=_Context(error=context_error),
            writing_gate_service=gate,
            activity_log_service=(
                ActivityLogService(activity_repo)
                if activity_repo is not None else None
            ))
        authenticate(app)
        async def open_client():
            return httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test")
        return asyncio.run(open_client()), project.id, draft.id, base, gate

    def _post(self, client, project, draft, base, **overrides):
        body = {"request_id": "wr1", "draft_id": draft,
                "base_version_id": base, "idempotency_key": "accept-1",
                "instruction": "이어서 써줘", "candidate_text": "새 글."}
        body.update(overrides)
        return asyncio.run(client.post(
            f"/projects/{project}/writing/accept", json=body))

    def test_pass_returns_saved_version_and_pending_job(self):
        client, project, draft, base, _ = self._setup()
        response = self._post(client, project, draft, base.draft_version.id)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["accepted"])
        self.assertEqual(body["analysis_job"]["status"], "pending")
        self.assertEqual(body["analysis_job"]["snapshot_id"],
                         body["saved"]["snapshot_id"])
        asyncio.run(client.aclose())

    def test_a_saved_accept_is_recorded_in_the_activity_log(self):
        """Phase 9 (오너 2026-08-09): accept 는 **정본 저장**이라 타임라인에 남는다.

        착수 결정(A2=B, 19)은 브리프 §0.2 의 성격 분류를 따라 이 경로를 뺐는데,
        A2 의 기준은 "무엇을 바꿨는가"이고 accept 는 draft version 을 만든다 —
        그리고 이것이 **주 저작 흐름의 저장 경로**다.

        **기록하는 것은 AI 요청이 아니라 정본 저장이므로 A8(중복 없음)은 그대로다.**
        """
        repo = InMemoryActivityLogRepository()
        client, project, draft, base, _ = self._setup(activity_repo=repo)

        response = self._post(client, project, draft, base.draft_version.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(repo.events), 1)
        event = repo.events[0]
        self.assertEqual(event.action, "draft_version_accepted")
        self.assertEqual(event.project_id, project)
        self.assertEqual(
            event.target_id, response.json()["saved"]["draft_version_id"]
        )
        asyncio.run(client.aclose())

    def test_a_partial_accept_still_records_the_saved_version(self):
        """★ 기록 조건은 상태코드가 아니라 **정본이 바뀌었는가**다 (SoT v1.7.93).

        이 경로는 draft version 이 저장된 뒤 분석 job 만 실패한 자리라 응답이
        502(partial envelope)인데도 **정본은 바뀌었다**. 상태코드로 판정했다면
        타임라인이 실제로 일어난 저장을 빠뜨렸을 자리다.

        **이 셀이 왜 따로 필요한가**(2026-08-09 독립 검증이 연 조건): 같은 handler
        안에 기록 분기가 **둘**인데, 전수 가드
        ``ActivityActionClassificationTest::test_every_logged_route_actually_records``
        는 endpoint 소스에 ``activity.record(`` 가 **있는지**만 본다 — 성공 분기가
        남아 있으면 이 502 분기를 통째로 지워도 소스 스캔이 만족돼 **전수 회귀가
        전부 green 이었다**(실측). 분기를 보는 것은 행위 셀뿐이므로 **기록 분기마다
        하나씩** 필요하다.

        over-strict 도 함께 문다 — ``events`` 가 정확히 1건이라 이 분기에서 두 번
        기록하는 과잉 교정에서도 실패한다.
        """
        repo = InMemoryActivityLogRepository()
        client, project, draft, base, _ = self._setup(
            analysis=_FailingAnalysis(InMemoryAnalysisRepository()),
            activity_repo=repo)

        response = self._post(client, project, draft, base.draft_version.id)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(len(repo.events), 1)
        event = repo.events[0]
        self.assertEqual(event.action, "draft_version_accepted")
        self.assertEqual(event.project_id, project)
        self.assertEqual(
            event.target_id, response.json()["saved"]["draft_version_id"]
        )
        asyncio.run(client.aclose())

    def test_a_bounced_accept_is_not_recorded(self):
        """over-strict — Gate 가 거부하면 저장이 없고, 저장이 없으면 기록도 없다.

        A7=A 의 "결과를 안 뒤에 쓴다"가 이 경로에서 갖는 모양이다. 200 이지만
        `saved` 가 없다 — 상태코드가 아니라 **정본이 바뀌었는가**가 기준이다.
        """
        repo = InMemoryActivityLogRepository()
        client, project, draft, base, _ = self._setup(
            decision=WritingGateDecision.REVISE, activity_repo=repo)

        response = self._post(client, project, draft, base.draft_version.id)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["saved"])
        self.assertEqual(repo.events, [])
        asyncio.run(client.aclose())

    def test_non_pass_is_200_without_saved_artifacts(self):
        client, project, draft, base, _ = self._setup(
            decision=WritingGateDecision.REVISE)
        response = self._post(client, project, draft, base.draft_version.id)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["accepted"])
        self.assertIsNone(response.json()["saved"])
        self.assertEqual(response.json()["gate"]["decision"], "revise")
        asyncio.run(client.aclose())

    def test_stale_is_409_before_gate(self):
        client, project, draft, base, gate = self._setup()
        first = self._post(client, project, draft, base.draft_version.id,
                           idempotency_key="first")
        self.assertEqual(first.status_code, 200)
        response = self._post(client, project, draft, base.draft_version.id,
                              idempotency_key="stale")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(gate.calls, 1)
        asyncio.run(client.aclose())

    def test_replay_returns_same_version_without_second_gate(self):
        client, project, draft, base, gate = self._setup()
        first = self._post(client, project, draft, base.draft_version.id)
        replay = self._post(client, project, draft, base.draft_version.id,
                            candidate_text="다른 내용")
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["idempotent_replay"])
        self.assertEqual(replay.json()["saved"]["draft_version_id"],
                         first.json()["saved"]["draft_version_id"])
        self.assertEqual(gate.calls, 1)
        asyncio.run(client.aclose())

    def test_partial_failure_is_502_and_retry_converges(self):
        analysis = _FailingAnalysis(InMemoryAnalysisRepository())
        client, project, draft, base, gate = self._setup(analysis=analysis)
        failed = self._post(client, project, draft, base.draft_version.id)
        self.assertEqual(failed.status_code, 502)
        self.assertTrue(failed.json()["accepted"])
        saved_id = failed.json()["saved"]["draft_version_id"]
        failed_replay = self._post(client, project, draft,
                                   base.draft_version.id)
        self.assertEqual(failed_replay.status_code, 502)
        self.assertEqual(failed_replay.json()["saved"]["draft_version_id"],
                         saved_id)
        analysis.fail = False
        replay = self._post(client, project, draft, base.draft_version.id)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["saved"]["draft_version_id"], saved_id)
        self.assertEqual(replay.json()["analysis_job"]["status"], "pending")
        self.assertEqual(gate.calls, 1)
        asyncio.run(client.aclose())

    def test_missing_base_version_is_404_before_gate(self):
        client, project, draft, _base, gate = self._setup()
        response = self._post(client, project, draft, "missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(gate.calls, 0)
        asyncio.run(client.aclose())

    def test_invalid_inputs_are_400(self):
        client, project, draft, base, gate = self._setup()
        invalid = (
            {"idempotency_key": ""}, {"instruction": ""},
            {"candidate_text": ""}, {"task_type": "revise"},
            {"output_type": "full_draft"},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides):
                self.assertEqual(self._post(
                    client, project, draft, base.draft_version.id,
                    **overrides).status_code, 400)
        self.assertEqual(gate.calls, 0)
        asyncio.run(client.aclose())

    def test_provider_and_context_failures_map_on_accept_surface(self):
        cases = (
            ({"gate_error": ProviderError(
                code=ProviderErrorCode.UNAVAILABLE, message="down",
                retryable=True, provider="gateway")}, 502),
            ({"gate_error": ProviderError(
                code=ProviderErrorCode.TIMEOUT, message="slow",
                retryable=True, provider="gateway")}, 504),
            ({"context_error": ContextSearchBudgetExceeded("budget")}, 504),
            ({"context_error": ContextSearchFailed(
                ContextSearchErrorType.BACKEND_ERROR, "down")}, 502),
        )
        for setup_kwargs, expected in cases:
            client, project, draft, base, _ = self._setup(**setup_kwargs)
            with self.subTest(setup_kwargs=tuple(setup_kwargs)):
                self.assertEqual(self._post(
                    client, project, draft,
                    base.draft_version.id).status_code, expected)
            asyncio.run(client.aclose())

    def test_missing_accept_dependencies_are_503(self):
        core = CoreSotService(InMemoryCoreSotRepository())
        project = core.create_project(name="Novel")
        with patch.dict(os.environ, {}, clear=True):
            app = create_app(service=core,
                analysis_service=AnalysisService(InMemoryAnalysisRepository()))
            authenticate(app)
        async def call():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test") as client:
                return await client.post(
                    f"/projects/{project.id}/writing/accept", json={
                        "request_id": "wr1", "draft_id": "d",
                        "base_version_id": "v", "idempotency_key": "k",
                        "instruction": "x", "candidate_text": "y"})
        self.assertEqual(asyncio.run(call()).status_code, 503)


class WritingAcceptEnvelopeKeyTest(unittest.TestCase):
    """C0 exact-key safety net for the accept envelopes (SoT v1.7.1, D3=A).

    Pins the COMPLETE key set of both the success dict and the partial
    ``JSONResponse`` (analysis failure) before the models are applied. The
    success dict is validated by ``response_model=WritingAcceptResponse`` so a
    too-narrow model would silently drop a field; the partial envelope bypasses
    ``response_model`` (JSONResponse) so its keys are locked here as the only
    guard. Nested ``saved``/``analysis_job``/``gate`` key sets are pinned too.
    """

    def test_success_envelope_keys_are_complete(self):
        client, project, draft, base, _ = WritingAcceptApiTest()._setup()
        body = WritingAcceptApiTest()._post(
            client, project, draft, base.draft_version.id).json()
        self.assertEqual(set(body), {
            "accepted", "intent", "gate", "saved", "analysis_job",
            "idempotent_replay",
        })
        self.assertEqual(set(body["saved"]), {
            "draft_id", "draft_version_id", "version_number", "snapshot_id",
            "content_hash", "unit_kind", "position",
        })
        self.assertEqual(set(body["analysis_job"]), {
            "id", "project_id", "snapshot_id", "status", "failure_reason",
            "failure_detail",
        })
        self.assertEqual(set(body["gate"]), {
            "request_id", "project_id", "decision", "findings",
            "checked_constraints", "evaluated_by_model",
        })
        asyncio.run(client.aclose())

    def test_partial_analysis_failure_envelope_keys_are_complete(self):
        analysis = _FailingAnalysis(InMemoryAnalysisRepository())
        client, project, draft, base, _ = WritingAcceptApiTest()._setup(
            analysis=analysis)
        response = WritingAcceptApiTest()._post(
            client, project, draft, base.draft_version.id)
        self.assertEqual(response.status_code, 502)
        body = response.json()
        self.assertEqual(set(body), {
            "accepted", "intent", "saved", "analysis_job", "analysis_error",
        })
        self.assertEqual(set(body["saved"]), {
            "draft_id", "draft_version_id", "version_number", "snapshot_id",
            "content_hash", "unit_kind", "position",
        })
        # Load-bearing values (not just key existence): this partial is
        # `502 + accepted=true + saved present`. It must never be mistaken for a
        # plain error that discards the already-saved version. Keeping the value
        # lock in the C0 envelope test itself (not only in the accept behaviour
        # suite) keeps the contract self-contained (verification H2).
        self.assertTrue(body["accepted"])
        self.assertIsNotNone(body["saved"])
        asyncio.run(client.aclose())


# --- W3 Writing intent (W0 contract §3, WI-01~22) --------------------------


def _next_unit(title="새 장", kind=UnitKind.CHAPTER, goal=None):
    return NextUnit(title=title, unit_kind=kind, goal=goal)


def _start_request(project, next_unit):
    return WritingRequest("wr1", project, WritingTaskType.CONTINUE_SCENE,
                          "이어서 써줘", intent=WritingIntent.START_NEXT_UNIT,
                          next_unit=next_unit)


def _start_candidate(project, next_unit, text="새 유닛 본문."):
    return WritingCandidate("wr1", project, WritingTaskType.CONTINUE_SCENE,
        WritingOutputType.DRAFT_PATCH, text,
        intent=WritingIntent.START_NEXT_UNIT, next_unit=next_unit)


class _IntentBase(unittest.TestCase):
    """Seeds an ordered project: current(1)·following(2)·archived following(3)."""

    def setUp(self):
        self.core = CoreSotService(InMemoryCoreSotRepository())
        project = self.core.create_project(name="Novel")
        self.project = project.id
        self.current = self.core.create_draft(
            project_id=self.project, title="현재 장", unit_kind=UnitKind.CHAPTER)
        self.base = self.core.save_draft(project_id=self.project,
            draft_id=self.current.id, raw_text="현재 본문.",
            idempotency_key="base")
        self.following = self.core.create_draft(
            project_id=self.project, title="기존 다음", unit_kind=UnitKind.SCENE)
        self.archived_following = self.core.create_draft(
            project_id=self.project, title="보관됨", unit_kind=UnitKind.OTHER)
        self.core.archive_draft(project_id=self.project,
            draft_id=self.archived_following.id)
        self.analysis_repo = InMemoryAnalysisRepository()
        self.analysis = AnalysisService(self.analysis_repo)
        self.gate = _Gate()

    def _service(self, analysis=None, reporter=None):
        return WritingAcceptService(core_sot=self.core,
            analysis=analysis or self.analysis, gate=self.gate,
            reporter=reporter)

    def _positions(self):
        return [(d.title, d.position) for d in
                self.core.list_drafts(project_id=self.project)]

    def _draft_count(self):
        return len(self.core.list_drafts(project_id=self.project))

    def _accept_start(self, *, key="acc-start", next_unit=None, candidate=None,
                      base=None, service=None):
        nu = next_unit if next_unit is not None else _next_unit()
        return asyncio.run((service or self._service()).accept(
            draft_id=self.current.id,
            base_version_id=base or self.base.draft_version.id,
            idempotency_key=key, request=_start_request(self.project, nu),
            candidate=candidate or _start_candidate(self.project, nu),
            package=_package(self.project)))

    def _accept_append(self, *, key="acc-append", base=None, service=None,
                       text="추가 문단."):
        return asyncio.run((service or self._service()).accept(
            draft_id=self.current.id,
            base_version_id=base or self.base.draft_version.id,
            idempotency_key=key, request=_request(self.project),
            candidate=_candidate(self.project, text),
            package=_package(self.project)))


class WritingIntentAcceptTest(_IntentBase):
    def test_start_next_unit_creates_atomic_first_version(self):  # WI-03
        result = self._accept_start(next_unit=_next_unit("2장", UnitKind.CHAPTER))
        self.assertTrue(result.accepted)
        self.assertIs(result.intent, WritingIntent.START_NEXT_UNIT)
        self.assertEqual(result.saved.draft_version.version_number, 1)
        self.assertEqual(result.saved.snapshot.raw_text, "새 유닛 본문.")
        self.assertEqual(result.target_draft.title, "2장")
        self.assertIs(result.target_draft.unit_kind, UnitKind.CHAPTER)
        self.assertEqual(result.target_draft.position, 2)  # current + 1

    def test_start_next_unit_preserves_current_unit(self):  # WI-04
        before = self.core.get_draft_version(project_id=self.project,
            draft_id=self.current.id, version_id=self.base.draft_version.id)
        self._accept_start()
        current = self.core.get_draft(project_id=self.project,
            draft_id=self.current.id)
        versions = self.core.list_draft_versions(project_id=self.project,
            draft_id=self.current.id)
        self.assertEqual(current.position, 1)
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[-1].id, self.base.draft_version.id)
        after = self.core.get_draft_version(project_id=self.project,
            draft_id=self.current.id, version_id=self.base.draft_version.id)
        self.assertEqual(after.snapshot.raw_text, before.snapshot.raw_text)

    def test_start_next_unit_shifts_following_positions(self):  # WI-05
        result = self._accept_start()
        positions = self._positions()
        self.assertEqual(positions, [
            ("현재 장", 1), (result.target_draft.title, 2),
            ("기존 다음", 3), ("보관됨", 4)])
        archived = self.core.get_draft(project_id=self.project,
            draft_id=self.archived_following.id)
        self.assertTrue(archived.archived)  # archived unit is shifted, still archived

    def test_invalid_current_target_creates_nothing(self):  # WI-07
        before = self._draft_count()
        # stale base
        self.core.save_draft(project_id=self.project, draft_id=self.current.id,
            raw_text="수동 저장", idempotency_key="manual")
        with self.assertRaises(StaleWritingBase):
            self._accept_start(key="stale", base=self.base.draft_version.id)
        # cross-project candidate
        with self.assertRaisesRegex(ValueError, "different projects"):
            asyncio.run(self._service().accept(
                draft_id=self.current.id,
                base_version_id=self.base.draft_version.id,
                idempotency_key="cross",
                request=_start_request(self.project, _next_unit()),
                candidate=_start_candidate("other", _next_unit()),
                package=_package(self.project)))
        # archived current
        self.core.archive_draft(project_id=self.project,
            draft_id=self.current.id)
        with self.assertRaises(Archived):
            self._accept_start(key="arch")
        self.assertEqual(self._draft_count(), before)  # no new unit from any branch
        self.assertEqual(self.gate.calls, 0)
        self.assertEqual(self.analysis_repo.jobs, {})

    def test_nonpass_gate_has_no_start_next_side_effects(self):  # WI-08
        before = self._positions()
        for decision in (WritingGateDecision.REVISE, WritingGateDecision.BLOCK):
            with self.subTest(decision=decision):
                self.gate.decision = decision
                result = self._accept_start(key=f"nonpass-{decision.value}")
                self.assertFalse(result.accepted)
                self.assertIsNone(result.saved)
        self.assertEqual(self._positions(), before)
        self.assertEqual(self.analysis_repo.jobs, {})

    def test_start_next_same_key_replays_same_unit(self):  # WI-09
        first = self._accept_start(key="acc1")
        count = self._draft_count()
        positions = self._positions()
        calls = self.gate.calls
        replay = self._accept_start(key="acc1",
            candidate=_start_candidate(self.project, _next_unit(), "완전히 다른 글"))
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.target_draft.id, first.target_draft.id)
        self.assertEqual(replay.saved.draft_version.id,
                         first.saved.draft_version.id)
        self.assertEqual(self.gate.calls, calls)  # no second Gate
        self.assertEqual(self._draft_count(), count)  # no duplicate unit
        self.assertEqual(self._positions(), positions)

    def test_start_next_different_key_creates_distinct_unit(self):  # WI-10
        first = self._accept_start(key="acc1", next_unit=_next_unit("2장"))
        second = self._accept_start(key="acc2", next_unit=_next_unit("사이 장"))
        self.assertNotEqual(first.target_draft.id, second.target_draft.id)
        # The newer next-unit lands directly after the current unit.
        self.assertEqual(second.target_draft.position, 2)
        self.assertEqual(len(self.analysis_repo.jobs), 2)

    def test_start_next_partial_replay_converges(self):  # WI-14
        failing = _FailingAnalysis(InMemoryAnalysisRepository())
        service = self._service(analysis=failing)
        with self.assertRaises(WritingAcceptAnalysisError) as raised:
            self._accept_start(key="acc1", service=service)
        target_id = raised.exception.target_draft.id
        count = self._draft_count()
        # retry while still failing: no duplicate unit, same target.
        with self.assertRaises(WritingAcceptAnalysisError) as again:
            self._accept_start(key="acc1", service=service)
        self.assertEqual(again.exception.target_draft.id, target_id)
        self.assertEqual(self._draft_count(), count)
        # recover: converges on the same snapshot-scoped job, still one unit.
        failing.fail = False
        replay = self._accept_start(key="acc1", service=service)
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.target_draft.id, target_id)
        self.assertEqual(self._draft_count(), count)
        self.assertEqual(len(failing._repo.jobs), 1)

    # --- 중복 영수증 레이스: 두 방향 (2026-08-20, mypy 가드가 찾았다) ---
    #
    # accept.py 의 그 except 절은 `_replay()` 를 **None 검사 없이 언팩**했다. 같은
    # 함수 앞쪽(:106)은 제대로 `is not None` 을 보는데 여기만 안 봤다. 테스트가
    # 이 분기를 한 번도 안 밟아 한 번도 드러나지 않았다.

    def test_an_unreadable_receipt_fails_closed_instead_of_type_error(self):
        """under-strict: None 검사를 빼면 이 셀이 다시 실패한다.

        영수증을 아직 못 읽는 창에서 기대하는 것은 **원인을 말하는 실패**다.
        None 을 언팩하면 `TypeError: cannot unpack non-sequence NoneType` 가
        나고, 호출자는 무슨 일이 났는지 알 수 없다(재시도해야 하는지도 모른다).
        """
        service = self._service()
        service._core_sot = _ReceiptRaceCore(self.core, receipt_readable=False)
        with self.assertRaises(DuplicateWritingAcceptReceipt):
            self._accept_start(key="race-1", service=service)
        # 유닛을 날조하지 않았다 — fail-closed 의 나머지 절반이다.
        self.assertEqual(self._draft_count(), 3)

    def test_a_readable_receipt_still_converges_through_the_same_branch(self):
        """over-strict: 과잉교정(예: 무조건 raise)을 하면 이 셀이 실패한다.

        영수증이 보이는 정상 레이스는 **여전히 조용히 수렴**해야 한다 — 이것이
        그 except 절이 존재하는 이유 자체다.
        """
        service = self._service()
        service._core_sot = _ReceiptRaceCore(self.core, receipt_readable=True)
        result = self._accept_start(key="race-2", service=service)
        self.assertTrue(result.idempotent_replay)
        self.assertIsNone(result.gate)
        # 한 번만 만들어졌다(현재·기존 다음·보관됨 + 새 유닛 하나).
        self.assertEqual(self._draft_count(), 4)

    def test_next_unit_goal_is_not_persisted_as_prose(self):  # WI-16
        goal = "주인공을 죽이는 반전"
        result = self._accept_start(
            next_unit=_next_unit("2장", UnitKind.CHAPTER, goal=goal))
        self.assertNotIn(goal, result.saved.snapshot.raw_text)
        self.assertNotIn(goal, result.target_draft.title)
        receipt = self.core.get_writing_accept_receipt(
            project_id=self.project, idempotency_key="writing-accept:acc-start")
        self.assertEqual(receipt.intent, "start_next_unit")

    def test_replay_precedes_stale_base_and_gate(self):  # WI-19
        first = self._accept_start(key="acc1")
        calls = self.gate.calls
        # Make the current unit's latest version diverge from the accept base.
        self.core.save_draft(project_id=self.project, draft_id=self.current.id,
            raw_text="수동 편집", idempotency_key="manual")
        replay = self._accept_start(key="acc1",
            base=self.base.draft_version.id)  # now a stale base
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.target_draft.id, first.target_draft.id)
        self.assertEqual(self.gate.calls, calls)  # replay preceded the Gate

    def test_append_partial_replay_converges(self):  # WI-21
        failing = _FailingAnalysis(InMemoryAnalysisRepository())
        service = self._service(analysis=failing)
        with self.assertRaises(WritingAcceptAnalysisError) as raised:
            self._accept_append(key="acc1", service=service)
        saved_id = raised.exception.saved.draft_version.id
        self.assertIs(raised.exception.intent, WritingIntent.APPEND_CURRENT)
        versions = len(self.core.list_draft_versions(
            project_id=self.project, draft_id=self.current.id))
        failing.fail = False
        replay = self._accept_append(key="acc1", service=service)
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.saved.draft_version.id, saved_id)
        self.assertEqual(len(self.core.list_draft_versions(
            project_id=self.project, draft_id=self.current.id)), versions)
        self.assertEqual(len(failing._repo.jobs), 1)

    def test_append_current_saves_same_draft(self):  # WI-02
        result = self._accept_append(text="이어지는 문단.")
        self.assertTrue(result.accepted)
        self.assertIs(result.intent, WritingIntent.APPEND_CURRENT)
        self.assertEqual(result.saved.draft_version.draft_id, self.current.id)
        self.assertEqual(result.saved.snapshot.raw_text, "현재 본문.\n\n이어지는 문단.")
        self.assertEqual(result.target_draft.id, self.current.id)

    def test_both_intents_use_snapshot_scoped_analysis_key(self):  # WI-22
        appended = self._accept_append(key="a1")
        started = self._accept_start(key="s1",
            base=appended.saved.draft_version.id)
        for result in (appended, started):
            with self.subTest(intent=result.intent):
                self.assertEqual(
                    result.analysis_job.idempotency_key,
                    analysis_job_key(result.saved.snapshot.id))


class WritingIntentCompatibilityTest(_IntentBase):
    def test_omitted_intent_preserves_append_current(self):  # WI-01
        # A legacy request/candidate that omits intent entirely defaults to
        # append_current and behaves byte-for-byte like the pre-W3 append.
        request = WritingRequest("wr1", self.project,
            WritingTaskType.CONTINUE_SCENE, "이어서 써줘")
        candidate = _candidate(self.project, "이어지는 문단.")
        self.assertIs(request.intent, WritingIntent.APPEND_CURRENT)
        self.assertIsNone(request.next_unit)
        result = asyncio.run(self._service().accept(
            draft_id=self.current.id,
            base_version_id=self.base.draft_version.id,
            idempotency_key="legacy", request=request, candidate=candidate,
            package=_package(self.project)))
        self.assertIs(result.intent, WritingIntent.APPEND_CURRENT)
        self.assertEqual(result.saved.snapshot.raw_text, "현재 본문.\n\n이어지는 문단.")
        self.assertEqual(result.saved.draft_version.draft_id, self.current.id)

    def test_existing_append_accept_contract_remains_green(self):  # WI-12
        first = self._accept_append(key="one")
        second = self._accept_append(key="two",
            base=first.saved.draft_version.id, text="세 번째.")
        self.assertEqual(second.saved.draft_version.version_number, 3)
        self.assertNotEqual(first.saved.draft_version.id,
                            second.saved.draft_version.id)
        self.assertEqual(len(self.analysis_repo.jobs), 2)

    def test_legacy_append_save_record_replays_without_receipt(self):  # WI-17
        first = self._accept_append(key="acc1")
        # Append never writes an accept receipt (§3.3): the replay is a
        # read-through of the version idempotency key alone.
        self.assertIsNone(self.core.get_writing_accept_receipt(
            project_id=self.project,
            idempotency_key="writing-accept:acc1"))
        replay = self._accept_append(key="acc1", text="바뀐 글")
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.saved.draft_version.id,
                         first.saved.draft_version.id)

    def test_append_different_key_creates_next_version(self):  # WI-18
        first = self._accept_append(key="one")
        second = self._accept_append(key="two",
            base=first.saved.draft_version.id)
        self.assertFalse(second.idempotent_replay)
        self.assertEqual(second.saved.draft_version.version_number, 3)


class WritingIntentApiTest(unittest.TestCase):
    def _setup(self, *, decision=WritingGateDecision.PASS, analysis=None):
        core = CoreSotService(InMemoryCoreSotRepository())
        project = core.create_project(name="Novel")
        current = core.create_draft(project_id=project.id, title="현재 장",
            unit_kind=UnitKind.CHAPTER)
        base = core.save_draft(project_id=project.id, draft_id=current.id,
            raw_text="현재 본문.", idempotency_key="base")
        following = core.create_draft(project_id=project.id, title="기존 다음",
            unit_kind=UnitKind.SCENE)
        analysis = analysis or AnalysisService(InMemoryAnalysisRepository())
        gate = _Gate(decision)
        app = create_app(service=core, analysis_service=analysis,
            context_search_service=_Context(), writing_gate_service=gate)
        authenticate(app)
        async def open_client():
            return httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test")
        return (asyncio.run(open_client()), project.id, current.id,
                base.draft_version.id, gate)

    def _post(self, client, project, body):
        return asyncio.run(client.post(
            f"/projects/{project}/writing/accept", json=body))

    def _start_body(self, draft, base, **overrides):
        body = {"request_id": "wr1", "draft_id": draft, "base_version_id": base,
                "idempotency_key": "acc1", "instruction": "이어서 써줘",
                "candidate_text": "새 유닛 본문.", "intent": "start_next_unit",
                "next_unit": {"title": "2장", "unit_kind": "chapter", "goal": None}}
        body.update(overrides)
        return body

    def test_mismatched_intent_binding_rejected_before_provider(self):  # WI-06
        client, project, draft, base, gate = self._setup()
        # append_current carrying a next_unit → 400, before the Gate.
        bad_append = self._post(client, project, {
            "request_id": "wr1", "draft_id": draft, "base_version_id": base,
            "idempotency_key": "a", "instruction": "이어서", "candidate_text": "글.",
            "intent": "append_current",
            "next_unit": {"title": "2장", "unit_kind": "chapter", "goal": None}})
        self.assertEqual(bad_append.status_code, 400)
        # start_next_unit missing next_unit → 400, before the Gate.
        bad_start = self._post(client, project, {
            "request_id": "wr1", "draft_id": draft, "base_version_id": base,
            "idempotency_key": "b", "instruction": "이어서", "candidate_text": "글.",
            "intent": "start_next_unit"})
        self.assertEqual(bad_start.status_code, 400)
        self.assertEqual(gate.calls, 0)
        asyncio.run(client.aclose())

    def test_accept_response_exact_keys_for_both_intents(self):  # WI-15
        client, project, draft, base, _ = self._setup()
        started = self._post(client, project, self._start_body(draft, base))
        self.assertEqual(started.status_code, 200)
        started_body = started.json()
        self.assertEqual(started_body["intent"], "start_next_unit")
        self.assertEqual(set(started_body["saved"]), {
            "draft_id", "draft_version_id", "version_number", "snapshot_id",
            "content_hash", "unit_kind", "position"})
        self.assertEqual(started_body["saved"]["unit_kind"], "chapter")
        self.assertEqual(started_body["saved"]["position"], 2)
        appended = self._post(client, project, {
            "request_id": "wr1", "draft_id": draft,
            "base_version_id": base, "idempotency_key": "acc2",
            "instruction": "이어서", "candidate_text": "덧붙임.",
            "intent": "append_current"})
        self.assertEqual(appended.status_code, 200)
        self.assertEqual(appended.json()["intent"], "append_current")
        self.assertEqual(appended.json()["saved"]["unit_kind"], "chapter")
        self.assertEqual(appended.json()["saved"]["position"], 1)
        asyncio.run(client.aclose())

    def test_start_next_analysis_failure_returns_saved_partial(self):  # WI-13
        analysis = _FailingAnalysis(InMemoryAnalysisRepository())
        client, project, draft, base, _ = self._setup(analysis=analysis)
        response = self._post(client, project, self._start_body(draft, base))
        self.assertEqual(response.status_code, 502)
        body = response.json()
        self.assertTrue(body["accepted"])
        self.assertEqual(body["intent"], "start_next_unit")
        self.assertEqual(body["saved"]["position"], 2)
        self.assertEqual(body["saved"]["unit_kind"], "chapter")
        self.assertIsNone(body["analysis_job"])
        asyncio.run(client.aclose())

    def test_append_analysis_failure_returns_saved_partial(self):  # WI-20
        analysis = _FailingAnalysis(InMemoryAnalysisRepository())
        client, project, draft, base, _ = self._setup(analysis=analysis)
        response = self._post(client, project, {
            "request_id": "wr1", "draft_id": draft, "base_version_id": base,
            "idempotency_key": "acc1", "instruction": "이어서",
            "candidate_text": "덧붙임.", "intent": "append_current"})
        self.assertEqual(response.status_code, 502)
        body = response.json()
        self.assertTrue(body["accepted"])
        self.assertEqual(body["intent"], "append_current")
        self.assertEqual(body["saved"]["draft_id"], draft)
        self.assertIsNone(body["analysis_job"])
        asyncio.run(client.aclose())


class StartNextUnitLegacyDataTest(unittest.TestCase):
    """H3 S5: ``intent=start_next_unit`` on legacy drafts is 503, not a 500 leak.

    SoT v1.7.29 recorded this as a *known defect*: the 2026-07-22 fix mapped
    ``DraftOrderIntegrityError`` to 503 on the three CRUD endpoints but left the
    accept path uncovered, so a project holding a pre-W3 draft (no
    ``unit_kind``/``position``) made ``start_next_unit`` raise through every
    ``except`` clause and escape as an opaque 500.

    Both directions are pinned:

    * under-strict — remove the ``except DraftOrderIntegrityError`` clause in
      ``writing_accept_endpoint`` and ``test_start_next_unit_on_legacy_data_is_503``
      re-fails with the original 500.
    * over-strict — the fix must stay surgical: a project with no legacy draft
      still accepts normally (200); ``append_current`` is unaffected even *with*
      legacy data present, because that path never calls
      ``_require_ordered_drafts``; and a binding error is still 400 rather than
      being swallowed by the integrity clause sitting above the 400 group.

    What these tests do *not* catch (independent verification, 2026-07-23):
    broadening the clause to ``except InvalidDraftOrder`` passes all four,
    because through this endpoint the integrity subclass is the only member of
    that hierarchy reachable. The parent is also raised for a bad ``unit_kind``
    (``core_sot/service.py`` in ``start_next_unit``), but the endpoint coerces
    ``UnitKind(body.next_unit.unit_kind)`` before calling the service, so that
    branch is already a 400 at the HTTP boundary and never arrives here. So the
    widening has no observable effect through this endpoint today and there is
    nothing to assert against it at this layer — writing such a test would mean
    calling the service directly, which would no longer be testing the
    endpoint's mapping. The narrow catch stays a deliberate intent statement
    ("the server-side data problem is what maps to 503, not the caller's
    ordering mistakes"). If a later change makes the parent reachable here — for
    instance by dropping the ``UnitKind`` coercion above — the difference
    becomes observable and must be locked then.
    """

    def _setup(self, *, legacy: bool):
        core = CoreSotService(InMemoryCoreSotRepository())
        project = core.create_project(name="Novel")
        current = core.create_draft(
            project_id=project.id, title="현재 장", unit_kind=UnitKind.CHAPTER
        )
        base = core.save_draft(
            project_id=project.id, draft_id=current.id,
            raw_text="현재 본문.", idempotency_key="base",
        )
        if legacy:
            # A draft stored before the W3 ordered-unit invariant: no unit_kind,
            # no position. Built through the repository because the service
            # refuses to create one this way today — that is the point.
            core._repo.drafts["legacy-1"] = replace(
                current, id="legacy-1", title="구 회차",
                unit_kind=None, position=None,
            )
        app = create_app(
            service=core, analysis_service=AnalysisService(InMemoryAnalysisRepository()),
            context_search_service=_Context(),
            writing_gate_service=_Gate(WritingGateDecision.PASS),
        )
        authenticate(app)
        client = asyncio.run(self._open(app))
        return client, project.id, current.id, base.draft_version.id

    @staticmethod
    async def _open(app):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test")

    def _accept(self, client, project, body):
        return asyncio.run(
            client.post(f"/projects/{project}/writing/accept", json=body))

    def _start_body(self, draft, base, **overrides):
        body = {"request_id": "wr1", "draft_id": draft, "base_version_id": base,
                "idempotency_key": "acc1", "instruction": "이어서 써줘",
                "candidate_text": "새 유닛 본문.", "intent": "start_next_unit",
                "next_unit": {"title": "2장", "unit_kind": "chapter", "goal": None}}
        body.update(overrides)
        return body

    def test_start_next_unit_on_legacy_data_is_503(self):
        client, project, draft, base = self._setup(legacy=True)
        response = self._accept(client, project, self._start_body(draft, base))
        self.assertEqual(response.status_code, 503)
        # The body stays the uniform error shape (H3 D1=A), and the detail must
        # not be empty — it is what tells the operator which face they hit.
        self.assertEqual(set(response.json()), {"detail"})
        self.assertTrue(response.json()["detail"])
        asyncio.run(client.aclose())

    def test_start_next_unit_without_legacy_data_still_accepts(self):
        # Over-strict guard: the 503 must require the integrity failure, not
        # merely the start_next_unit intent.
        client, project, draft, base = self._setup(legacy=False)
        response = self._accept(client, project, self._start_body(draft, base))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["intent"], "start_next_unit")
        asyncio.run(client.aclose())

    def test_append_current_with_legacy_data_is_unaffected(self):
        # Over-strict guard: append never reaches _require_ordered_drafts, so
        # legacy data must not start failing it. This pins the surgical scope of
        # the 07-22 fix (its deliberate asymmetry, SoT v1.7.29).
        client, project, draft, base = self._setup(legacy=True)
        response = self._accept(client, project, {
            "request_id": "wr1", "draft_id": draft, "base_version_id": base,
            "idempotency_key": "acc1", "instruction": "이어서",
            "candidate_text": "덧붙임.", "intent": "append_current"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["intent"], "append_current")
        asyncio.run(client.aclose())

    def test_binding_errors_still_map_to_400_not_503(self):
        # Over-strict guard on clause ordering: the integrity catch sits above
        # the 400 group, so a malformed request must still be the caller's fault
        # even when legacy data is present.
        client, project, draft, base = self._setup(legacy=True)
        response = self._accept(client, project, self._start_body(
            draft, base, next_unit=None))
        self.assertEqual(response.status_code, 400)
        asyncio.run(client.aclose())


class WritingIntentInMemoryRollbackTest(_IntentBase):
    """Hardening (not a WI row): the in-memory single-writer rollback restores
    every one of the six start-next surfaces on a mid-write failure. The
    contract-named Mongo transaction guard is WI-11 in test_core_sot_mongo.py.
    """

    def test_mid_write_failure_leaves_no_partial_unit(self):
        class _FailingRepo(InMemoryCoreSotRepository):
            def _after_draft_metadata_write(self, draft):
                raise RuntimeError("injected start-next write failure")

        repo = _FailingRepo()
        core = CoreSotService(repo)
        project = core.create_project(name="Novel")
        current = core.create_draft(project_id=project.id, title="현재",
            unit_kind=UnitKind.CHAPTER)
        core.save_draft(project_id=project.id, draft_id=current.id,
            raw_text="본문.", idempotency_key="base")
        following = core.create_draft(project_id=project.id, title="다음",
            unit_kind=UnitKind.SCENE)
        before = [(d.id, d.position) for d in
                  core.list_drafts(project_id=project.id)]
        # Pin every one of the six surfaces explicitly (H1): draft/position,
        # version, snapshot, block, receipt — none may gain a row.
        versions_before = len(repo.versions)
        snapshots_before = len(repo.snapshots)
        blocks_before = len(repo.blocks_by_snapshot)
        with self.assertRaises(RuntimeError):
            core.start_next_unit(project_id=project.id,
                current_draft_id=current.id, raw_text="새 유닛.",
                title="2장", unit_kind=UnitKind.CHAPTER,
                goal_intent="start_next_unit",
                idempotency_key="writing-accept:acc1")
        # 1-2. Draft/position surface: positions restored, no new unit.
        self.assertEqual(
            [(d.id, d.position) for d in core.list_drafts(project_id=project.id)],
            before)
        # 3-5. Version/snapshot/block surfaces: no orphan write survived.
        self.assertEqual(len(repo.versions), versions_before)
        self.assertEqual(len(repo.snapshots), snapshots_before)
        self.assertEqual(len(repo.blocks_by_snapshot), blocks_before)
        # 6. Receipt surface: no receipt for the aborted accept.
        self.assertIsNone(core.get_writing_accept_receipt(
            project_id=project.id, idempotency_key="writing-accept:acc1"))
