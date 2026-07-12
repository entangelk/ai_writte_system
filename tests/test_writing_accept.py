"""Phase 5.3 Writing accept→save→pending-analysis regressions."""

import asyncio
import os
import unittest
from unittest.mock import patch

import httpx

from services.application.app.analysis.models import AnalysisJobStatus
from services.application.app.analysis.service import AnalysisService, InMemoryAnalysisRepository
from services.application.app.context_search.models import (
    ContextPackage, ContextSearchErrorType, ContextSearchPurpose,
)
from services.application.app.context_search.service import (
    ContextSearchBudgetExceeded, ContextSearchFailed,
)
from services.application.app.core_sot.service import (
    Archived, CoreSotService, InMemoryCoreSotRepository,
)
from services.application.app.main import create_app
from services.application.app.writing.accept import (
    StaleWritingBase, WritingAcceptAnalysisError, WritingAcceptService,
    _append_patch,
)
from services.application.app.writing.models import (
    WritingCandidate, WritingGateDecision, WritingGateResult,
    WritingOutputType, WritingRequest, WritingTaskType,
)
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode


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

    def _service(self, analysis=None):
        return WritingAcceptService(core_sot=self.core,
            analysis=analysis or self.analysis, gate=self.gate)

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


class WritingAcceptApiTest(unittest.TestCase):
    def _setup(self, *, decision=WritingGateDecision.PASS, analysis=None,
               gate_error=None, context_error=None):
        core = CoreSotService(InMemoryCoreSotRepository())
        project = core.create_project(name="Novel")
        draft = core.create_draft(project_id=project.id, title="Draft")
        base = core.save_draft(project_id=project.id, draft_id=draft.id,
            raw_text="기존.", idempotency_key="base")
        analysis = analysis or AnalysisService(InMemoryAnalysisRepository())
        gate = _Gate(decision, error=gate_error)
        app = create_app(service=core, analysis_service=analysis,
            context_search_service=_Context(error=context_error),
            writing_gate_service=gate)
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
