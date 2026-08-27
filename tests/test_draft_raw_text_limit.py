"""D5-2(오너 2026-08-27, "전 경로 4000자") — 유닛 본문 길이 상한의 회귀.

두 축이 같은 상수(app/env.py draft_raw_text_max_chars)를 쓴다:

- **저장 스키마**: POST /projects/{id}/drafts/{draft_id}/versions 의
  SaveDraftRequest.raw_text → pydantic 검증 422.
- **채택 합성**: WritingAcceptService 가 append 합성 결과(base + "\\n\\n" + patch)와
  start_next_unit 씨앗 본문을 **provider 호출(enrich·gate) 앞에** 잰다 →
  WritingAcceptError → 400. 상한을 넘을 몸에 유료 호출이 돈을 쓰면 안 된다.

양방향: 상한 검증을 지우면 over 셀들이(under), 상한을 env 로 1로 내리면 boundary
셀들이(over) 각각 재실패한다. 상한의 근거는 창 안전이 아니라 이어쓰기 품질이다
(2026-08-27 실측 정정 — 원고는 매 생성 검색 조각으로 프롬프트에 실린다).
"""

from __future__ import annotations

import asyncio
import os
import unittest
from datetime import timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from services.application.app.analysis.service import (
    AnalysisService,
    InMemoryAnalysisRepository,
)
from services.application.app.auth.sessions import (
    InMemorySessionRepository,
    SessionService,
)
from services.application.app.auth.users import InMemoryUserRepository, UserService
from services.application.app.context_search.models import (
    ContextPackage,
    ContextSearchPurpose,
)
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
    NotFound,
)
from services.application.app.main import create_app
from services.application.app.writing.accept import (
    WritingAcceptError,
    WritingAcceptService,
)
from services.application.app.writing.models import (
    NextUnit,
    WritingCandidate,
    WritingGateDecision,
    WritingGateResult,
    WritingIntent,
    WritingOutputType,
    WritingRequest,
    WritingTaskType,
)
from services.application.app.core_sot.models import UnitKind


class _FakeHasher:
    def hash(self, password: str) -> str:
        return "H:" + password

    def verify(self, stored_hash: str, password: str) -> bool:
        return stored_hash == "H:" + password


class _Gate:
    def __init__(self):
        self.calls = 0

    async def evaluate(self, *, request, candidate, package):
        self.calls += 1
        return WritingGateResult(request.request_id, request.project_id,
            WritingGateDecision.PASS, (), (), "fake-gate")


class _Reporter:
    def __init__(self):
        self.calls = 0

    async def enrich(self, candidate, package):
        self.calls += 1
        return candidate


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


class SaveEndpointLimitTest(unittest.TestCase):
    """저장 스키마 축 — 422 와 env 조정성."""

    def setUp(self) -> None:
        users = UserService(InMemoryUserRepository(), hasher=_FakeHasher())
        sessions = SessionService(InMemorySessionRepository(),
                                  ttl=timedelta(hours=1))
        users.create_user(username="alice", password="pw123")
        self.core = CoreSotService(InMemoryCoreSotRepository())
        app = create_app(service=self.core, user_service=users,
                         session_service=sessions)
        self.client = TestClient(app, base_url="https://testserver")
        self.client.post("/auth/login",
                         json={"username": "alice", "password": "pw123"})
        self.project_id = self.client.post(
            "/projects", json={"name": "한 장편"}).json()["id"]
        self.draft_id = self.client.post(
            f"/projects/{self.project_id}/drafts",
            json={"title": "1장", "unit_kind": "chapter"}).json()["id"]

    def _save(self, raw_text: str, key: str = "k1"):
        return self.client.post(
            f"/projects/{self.project_id}/drafts/{self.draft_id}/versions",
            json={"raw_text": raw_text, "idempotency_key": key},
        )

    def test_exactly_at_the_limit_saves(self):
        # over 방향 앵커: 상한을 1로 내리면 이 셀이 재실패한다(정상 요청을 막는 과잉).
        response = self._save("가" * 4000)
        self.assertEqual(response.status_code, 200)

    def test_one_over_the_limit_is_rejected(self):
        # under 방향 앵커: validator 를 지우면 이 셀이 재실패한다.
        response = self._save("가" * 4001)
        self.assertEqual(response.status_code, 422)
        self.assertIn("4000", response.json()["detail"][0]["msg"])

    def test_the_limit_is_env_adjustable_in_both_directions(self):
        with patch.dict(os.environ, {"DRAFT_RAW_TEXT_MAX_CHARS": "10"}):
            self.assertEqual(self._save("가" * 10, key="k2").status_code, 200)
            self.assertEqual(self._save("가" * 11, key="k3").status_code, 422)

    def test_an_invalid_limit_fails_app_creation(self):
        for value in ("0", "not-an-integer"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"DRAFT_RAW_TEXT_MAX_CHARS": value},
            ):
                with self.assertRaises(ValueError):
                    create_app(service=CoreSotService(InMemoryCoreSotRepository()))


class AcceptRawTextLimitTest(unittest.TestCase):
    """채택 합성 축 — provider 호출 앞에서 거부된다(400 face)."""

    def setUp(self):
        self.core = CoreSotService(InMemoryCoreSotRepository())
        project = self.core.create_project(name="Novel")
        self.project = project.id
        self.draft = self.core.create_draft(project_id=project.id, title="Draft")
        self.analysis = AnalysisService(InMemoryAnalysisRepository())
        self.gate = _Gate()
        self.reporter = _Reporter()

    def _seed_base(self, raw_text: str):
        return self.core.save_draft(
            project_id=self.project, draft_id=self.draft.id,
            raw_text=raw_text, idempotency_key="seed")

    def _service(self):
        return WritingAcceptService(core_sot=self.core, analysis=self.analysis,
                                    gate=self.gate, reporter=self.reporter)

    def _accept_append(self, *, base_version_id, text):
        return asyncio.run(self._service().accept(
            draft_id=self.draft.id, base_version_id=base_version_id,
            idempotency_key="accept-1", request=_request(self.project),
            candidate=_candidate(self.project, text),
            package=_package(self.project)))

    def test_append_past_the_limit_fails_before_any_provider_call(self):
        # 레거시 몸(상한 이전에 저장된 4000자)에 1문단이라도 얹으면 합성이 상한을 넘는다.
        base = self._seed_base("가" * 4000)
        with self.assertRaises(WritingAcceptError):
            self._accept_append(base_version_id=base.draft_version.id,
                                text="넘는 문단.")
        self.assertEqual((self.reporter.calls, self.gate.calls), (0, 0),
                         "상한을 넘을 몸에 enrich·gate 어느 쪽에도 돈을 쓰면 안 된다")

    def test_append_composed_exactly_at_the_limit_passes(self):
        # 3997 + "\n\n"(2) + 1 = 4000 — 경계는 통과해야 한다(over 방향 앵커).
        base = self._seed_base("가" * 3997)
        result = self._accept_append(base_version_id=base.draft_version.id,
                                     text="가")
        self.assertTrue(result.accepted)
        self.assertEqual(self.gate.calls, 1)
        # 합성은 3997 + "\n\n" + 1 — 구분자까지 합쳐 정확히 4000자다.
        self.assertEqual(result.saved.snapshot.raw_text, "가" * 3997 + "\n\n" + "가")
        self.assertEqual(len(result.saved.snapshot.raw_text), 4000)

    def test_start_next_unit_seed_past_the_limit_fails_before_any_provider_call(self):
        base = self._seed_base("짧은 본문.")
        next_unit = NextUnit(title="새 장", unit_kind=UnitKind.CHAPTER)
        request = WritingRequest("wr1", self.project,
                                 WritingTaskType.CONTINUE_SCENE, "이어서 써줘",
                                 intent=WritingIntent.START_NEXT_UNIT,
                                 next_unit=next_unit)
        # ★ candidate 도 intent·next_unit 을 함께 싣는다 — 안 그러면 _validate 의
        # next_unit 일치 검사가 먼저 걸려 이 셀이 상한과 무관한 이유로 통과한다
        # (M3 뮤테이션으로 발견한 무효 통과).
        candidate = WritingCandidate("wr1", self.project,
                                     WritingTaskType.CONTINUE_SCENE,
                                     WritingOutputType.DRAFT_PATCH, "가" * 4001,
                                     intent=WritingIntent.START_NEXT_UNIT,
                                     next_unit=next_unit)
        with self.assertRaises(WritingAcceptError) as ctx:
            asyncio.run(self._service().accept(
                draft_id=self.draft.id,
                base_version_id=base.draft_version.id,
                idempotency_key="accept-start", request=request,
                candidate=candidate, package=_package(self.project)))
        self.assertIn("at most 4000 characters", str(ctx.exception))
        self.assertEqual((self.reporter.calls, self.gate.calls), (0, 0))

    def test_a_missing_base_still_reports_not_found_not_the_limit(self):
        # §3.3 — 상한 산술용 조용한 base 읽기가 replay/404 순서를 바꾸면 안 된다.
        self._seed_base("본문.")
        with self.assertRaises(NotFound):
            self._accept_append(base_version_id="no-such-version",
                                text="무엇이든")
