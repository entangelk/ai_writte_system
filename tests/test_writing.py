"""Phase 5.1 Writing generation regressions (v1.6.68).

Locks the generation-only slice: prompt assembly carries the instruction, draft
excerpt, do_not_use/constraints (hard priority) and candidate labels; the plain
prose response is wrapped into a WritingCandidate (status always "candidate");
deterministic safety (project isolation / task-type / instruction) rejects bad
requests; and a provider fault is not swallowed. Guards run both directions. See
docs/plans/05-writing-generation-decisions.md.
"""

import asyncio
import json
import os
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx

from services.application.app.context_search.models import (
    ContextItem,
    ContextItemStatus,
    ContextNeed,
    ContextPackage,
    ContextSearchErrorType,
    ContextSearchPurpose,
)
from services.application.app.context_search.service import (
    ContextSearchBudgetExceeded,
    ContextSearchFailed,
    InvalidContextSearchRequest,
)
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.indexing.models import IndexPointer
from services.application.app.main import (
    WRITING_REPORT_DEFAULT_MAX_TOKENS,
    _build_report_service,
    create_app,
)
from services.application.app.api.models import (
    DEFAULT_CONTEXT_BUDGET_TOKENS,
    WritingGenerateRequest,
    WritingReviseRequest,
    _writing_output_length_tokens,
)
from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository,
    PromptTemplateService,
)
from services.application.app.writing.models import (
    CandidateClaim,
    CandidateClaimType,
    ContextPointer,
    MemoryHintType,
    NewMemoryHint,
    OutputLength,
    RiskNote,
    RiskNoteType,
    RiskSeverity,
    WritingCandidate,
    WritingGateDecision,
    WritingGateResult,
    WritingOutputType,
    WritingRequest,
    WritingTaskType,
)
from services.application.app.writing.prompt import (
    build_writing_request,
    format_context_package,
)
from services.application.app.writing.service import (
    WritingError,
    WritingService,
    seed_writing_template,
)
from services.application.app.writing.report import (
    InvalidCandidateReport,
    WritingCandidateReportService,
    seed_report_template,
)
from services.application.app import main as main_module
from services.application.app.writing.report import TEMPLATE as REPORT_SYSTEM_TEMPLATE
from services.application.app.writing.report_budget import (
    candidate_tokens_from_text,
    derive_context_budget,
)
from services.application.app.writing.generation_job import (
    InMemoryWritingGenerationJobRepository,
    WritingGenerationJob,
    WritingGenerationJobFailureReason,
    WritingGenerationJobService,
    WritingGenerationJobStatus,
)
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.provider import (
    FakeLLMProvider,
    GenerationResult,
    TokenUsage,
)
from tests.auth_support import authenticate


def _pointer(project_id="p1"):
    return IndexPointer(
        project_id=project_id, collection="memory_entries",
        document_id="m1", version_id="1", content_hash="",
    )


def _item(text, *, status=ContextItemStatus.CANONICAL,
          need=ContextNeed.CURRENT_SCENE):
    return ContextItem(
        need=need, status=status, text=text, pointer=_pointer(),
        snapshot_id="", sot_reloaded=False, token_estimate=0,
    )


def _package(project_id="p1", *, do_not_use=(), constraints=(),
             macro=(), micro=()):
    return ContextPackage(
        project_id=project_id,
        purpose=ContextSearchPurpose.WRITING_CONTEXT,
        macro_items=tuple(macro), micro_evidence=tuple(micro),
        constraints=tuple(constraints), do_not_use=tuple(do_not_use),
        token_estimate_total=0, degraded=False,
    )


def _request(project_id="p1", *, instruction="이어서 써줘.",
             task_type=WritingTaskType.CONTINUE_SCENE, draft_excerpt=""):
    return WritingRequest(
        request_id="wr1", project_id=project_id, task_type=task_type,
        instruction=instruction, draft_excerpt=draft_excerpt,
    )


class _FakeProvider:
    def __init__(self, content="아린은 성문 앞에서 멈췄다.", *, error=None):
        self._content = content
        self._error = error
        self.last_request = None

    async def generate(self, request):
        self.last_request = request
        if self._error is not None:
            raise self._error
        return GenerationResult(
            model="fake-writer", content=self._content,
            finish_reason="stop", usage=TokenUsage(1, 1),
        )


# A claim's evidence pointer (stable-pointer brief D1=A/D3=A). Real pointers are
# projected from the request's package; here it is a serialization fixture so the
# HTTP wire is exercised with a non-empty pointer array.
_CLAIM_POINTER = ContextPointer("source_blocks", "b1", "ver1", "hash1")


class _FakeReporter:
    # Phase 5.4 report extractor stub: enriches a plain-prose candidate with the
    # four structured report fields so the HTTP serialization path is exercised
    # with non-empty values (v1.6.71 보강 B1).
    def __init__(self, *, error=None):
        self.calls = 0
        self.error = error
        self.last_candidate = None
        self.last_package = None

    async def enrich(self, candidate, package):
        self.calls += 1
        self.last_candidate = candidate
        self.last_package = package
        if self.error is not None:
            raise self.error
        return replace(
            candidate,
            self_reported_constraints=("제한 시점",),
            candidate_claims=(
                CandidateClaim("문이 열렸다", CandidateClaimType.NARRATIVE_EVENT, True,
                               (_CLAIM_POINTER,)),
            ),
            new_memory_hints=(
                NewMemoryHint(MemoryHintType.EVENT, "문이 열림", 0.8, True),
            ),
            risk_notes=(
                RiskNote(RiskNoteType.POV, RiskSeverity.HIGH, "시점 확인"),
            ),
        )


def _service(provider, *, reporter=None):
    templates = PromptTemplateService(InMemoryPromptTemplateRepository())
    seed_writing_template(templates)
    return WritingService(provider, prompt_templates=templates, reporter=reporter)


def _run(coro):
    return asyncio.run(coro)


class PromptAssemblyTest(unittest.TestCase):
    def test_context_format_orders_do_not_use_and_labels_candidate(self):
        # under-strict (rows 1/3/10): do_not_use first, candidate items labeled.
        text = format_context_package(_package(
            do_not_use=("아린은 레온의 배신을 모른다.",),
            constraints=("[POV] 제한 시점.",),
            macro=(_item("노스워치는 춥고 폐쇄적이다."),),
            micro=(_item("검은 태양 단검.",
                         status=ContextItemStatus.CANDIDATE),),
        ))
        self.assertLess(text.index("do_not_use"), text.index("constraints"))
        self.assertLess(text.index("constraints"), text.index("macro_context"))
        self.assertIn("아린은 레온의 배신을 모른다.", text)
        self.assertIn("[canonical] 노스워치는 춥고 폐쇄적이다.", text)
        self.assertIn("[candidate (uncertain)] 검은 태양 단검.", text)

    def test_empty_package_is_explicit(self):
        self.assertIn("no project memory retrieved",
                      format_context_package(_package()))

    def test_build_request_carries_instruction_excerpt_and_context(self):
        # under-strict (row 1): the user message includes all inputs.
        templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        template = seed_writing_template(templates)
        chat = build_writing_request(
            request=_request(instruction="다음 문단을 써줘.",
                             draft_excerpt="그는 문을 열었다."),
            package=_package(do_not_use=("금지 사실.",)),
            prompt_template=template,
        )
        system, user = chat.messages
        self.assertEqual(system.role, "system")
        self.assertIn("ContextPackage is your ONLY project memory", system.content)
        self.assertIn("다음 문단을 써줘.", user.content)
        self.assertIn("그는 문을 열었다.", user.content)
        self.assertIn("금지 사실.", user.content)
        self.assertFalse(chat.thinking)

class GenerateTest(unittest.TestCase):
    def test_plain_prose_is_wrapped_into_candidate(self):
        # under-strict (rows 2/8): prose → candidate, status always "candidate".
        provider = _FakeProvider(content="  아린은 성문 앞에서 멈췄다.  ")
        candidate = _run(_service(provider).generate(
            request=_request(), package=_package(),
        ))
        self.assertIsInstance(candidate, WritingCandidate)
        self.assertEqual(candidate.text, "아린은 성문 앞에서 멈췄다.")
        self.assertEqual(candidate.status, "candidate")
        self.assertEqual(candidate.output_type, WritingOutputType.DRAFT_PATCH)
        self.assertEqual(candidate.task_type, WritingTaskType.CONTINUE_SCENE)
        self.assertEqual(candidate.request_id, "wr1")
        self.assertEqual(candidate.generated_by_model, "fake-writer")
        self.assertIsNone(candidate.candidate_id)
        self.assertEqual(candidate.self_reported_constraints, ())

    def test_provider_error_is_not_swallowed(self):
        # under-strict (row 7): a Gateway fault propagates, never a fake success.
        provider = _FakeProvider(error=ProviderError(
            code=ProviderErrorCode.UNAVAILABLE, message="down",
            retryable=True, provider="llm_gateway",
        ))
        with self.assertRaises(ProviderError):
            _run(_service(provider).generate(
                request=_request(), package=_package(),
            ))

    def test_non_continue_scene_task_rejected(self):
        # over-strict (row 5): the enum has one member, so build an invalid one.
        class _OtherTask:
            value = "revise"
        provider = _FakeProvider()
        request = WritingRequest(
            request_id="wr1", project_id="p1", task_type=_OtherTask(),
            instruction="x", draft_excerpt="",
        )
        with self.assertRaises(WritingError):
            _run(_service(provider).generate(request=request, package=_package()))
        self.assertIsNone(provider.last_request)  # never reached the model

    def test_empty_instruction_rejected(self):
        provider = _FakeProvider()
        with self.assertRaises(WritingError):
            _run(_service(provider).generate(
                request=_request(instruction="   "), package=_package(),
            ))
        self.assertIsNone(provider.last_request)

    def test_cross_project_package_rejected(self):
        # over-strict (row 4): package from another project must not be used.
        provider = _FakeProvider()
        with self.assertRaises(WritingError):
            _run(_service(provider).generate(
                request=_request(project_id="p1"),
                package=_package(project_id="p2"),
            ))
        self.assertIsNone(provider.last_request)

    def test_template_unavailable_raises_writing_error(self):
        # empty template store → WritingError (not a silent empty prompt).
        provider = _FakeProvider()
        service = WritingService(
            provider,
            prompt_templates=PromptTemplateService(
                InMemoryPromptTemplateRepository()
            ),
        )
        with self.assertRaises(WritingError):
            _run(service.generate(request=_request(), package=_package()))


class _TestClient:
    __test__ = False

    def __init__(self, app):
        # D8-3a: this suite is about domain behaviour, not the session
        # boundary, so the client arrives authenticated. The boundary itself
        # is driven un-overridden in tests/test_auth_api.py.
        authenticate(app)
        self._app = app

    def post(self, path, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.post(path, **kwargs)

        return asyncio.run(send())

    def get(self, path, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.get(path, **kwargs)

        return asyncio.run(send())


class _FakeContextSearch:
    def __init__(self, package, *, error=None):
        self._package = package
        self._error = error
        self.last_request = None

    async def build_context_package(self, request):
        # Real context search returns a package for the requested project; mirror
        # that so the service's project-isolation check sees a matching id.
        self.last_request = request
        if self._error is not None:
            raise self._error
        return replace(self._package, project_id=request.project_id)


class _NoWriteCoreSotService(CoreSotService):
    def __init__(self):
        super().__init__(InMemoryCoreSotRepository())
        self.save_calls = 0

    def save_draft(self, **kwargs):
        self.save_calls += 1
        raise AssertionError("writing/report must not save a draft")


def _http(provider=None, *, package=None, with_context=True, context_error=None,
          reporter=None, report_service=None, core_service=None,
          writing_generation_job_service=None):
    core_sot = core_service or CoreSotService(InMemoryCoreSotRepository())
    writing_service = (
        _service(provider, reporter=reporter) if provider is not None else None
    )
    context = (
        _FakeContextSearch(
            package if package is not None else _package(),
            error=context_error,
        )
        if with_context else None
    )
    app = create_app(
        service=core_sot,
        writing_service=writing_service,
        writing_report_service=report_service,
        context_search_service=context,
        writing_generation_job_service=writing_generation_job_service,
    )
    client = _TestClient(app)
    project_id = client.post("/projects", json={"name": "Novel"}).json()["id"]
    return client, project_id, context


class WritingGenerateApiTest(unittest.TestCase):
    def test_generate_returns_candidate(self):
        # under-strict (rows 2/9): orchestration context_search → generate → 200.
        client, project_id, context = _http(
            _FakeProvider(content="이어진 장면."),
            package=_package(),
        )
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "이어서 써줘.",
                  "draft_excerpt": "그는 문을 열었다."},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["text"], "이어진 장면.")
        self.assertEqual(body["status"], "candidate")
        self.assertEqual(body["output_type"], "draft_patch")
        self.assertEqual(body["project_id"], project_id)
        # the context search ran for this project with the instruction as query
        self.assertEqual(context.last_request.project_id, project_id)
        self.assertEqual(context.last_request.query, "이어서 써줘.")

    def test_generate_enriches_candidate_report_in_http_response(self):
        # v1.6.71 후속 보강 (B1): a wired reporter enriches the candidate and the
        # HTTP response surfaces the four report fields under the PUBLIC schema
        # key `type` — the internal dataclass names (claim_type/hint_type/risk_type)
        # must not leak. Mutating the HTTP serializer to emit the internal name
        # re-fails this test.
        reporter = _FakeReporter()
        client, project_id, _ = _http(
            _FakeProvider(content="이어진 장면."),
            package=_package(),
            reporter=reporter,
        )
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "이어서 써줘."},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(reporter.calls, 1)
        body = response.json()
        self.assertEqual(body["self_reported_constraints"], ["제한 시점"])
        claim = body["candidate_claims"][0]
        self.assertEqual(claim["type"], "narrative_event")
        self.assertNotIn("claim_type", claim)
        # Stable-pointer brief D3=A: the claim's evidence pointers reach the HTTP
        # wire as the exact 4-field object, project_id excluded (D1=A).
        self.assertEqual(claim["related_context_pointers"], [
            {"collection": "source_blocks", "document_id": "b1",
             "version_id": "ver1", "content_hash": "hash1"}])
        hint = body["new_memory_hints"][0]
        self.assertEqual(hint["type"], "event")
        self.assertNotIn("hint_type", hint)
        risk = body["risk_notes"][0]
        self.assertEqual(risk["type"], "pov")
        self.assertNotIn("risk_type", risk)

    def test_writing_not_configured_returns_503(self):
        client, project_id, _ = _http(provider=None, with_context=True)
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "x"},
        )
        self.assertEqual(response.status_code, 503)

    def test_context_search_not_configured_returns_503(self):
        client, project_id, _ = _http(_FakeProvider(), with_context=False)
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "x"},
        )
        self.assertEqual(response.status_code, 503)

    def test_start_next_intent_binding_rejects_invalid_pairs_before_provider(self):
        cases = (
            (
                "append_with_next_unit",
                {
                    "intent": "append_current",
                    "next_unit": {"title": "다음 장면", "goal": "긴장 유지"},
                },
                "append_current must not carry next_unit",
            ),
            (
                "start_without_next_unit",
                {"intent": "start_next_unit"},
                "start_next_unit requires next_unit",
            ),
            (
                "start_with_blank_title",
                {
                    "intent": "start_next_unit",
                    "next_unit": {"title": "   ", "goal": "긴장 유지"},
                },
                "next_unit.title must not be blank",
            ),
            (
                "start_with_blank_goal",
                {
                    "intent": "start_next_unit",
                    "next_unit": {"title": "다음 장면", "goal": "   "},
                },
                "next_unit.goal must be a nonblank string or null",
            ),
        )
        for name, extra, detail in cases:
            with self.subTest(name=name):
                provider = _FakeProvider()
                client, project_id, _ = _http(provider)
                response = client.post(
                    f"/projects/{project_id}/writing/generate",
                    json={"request_id": f"wr-{name}",
                          "instruction": "다음 장면으로 이어써줘.", **extra},
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["detail"], detail)
                self.assertIsNone(
                    provider.last_request,
                    "invalid start-next intent bindings must fail before provider call",
                )

    def test_unsupported_task_type_returns_400(self):
        client, project_id, _ = _http(_FakeProvider())
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "x", "task_type": "revise"},
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_project_returns_404(self):
        client, _project_id, _ = _http(_FakeProvider())
        response = client.post(
            "/projects/ghost/writing/generate",
            json={"request_id": "wr1", "instruction": "x"},
        )
        self.assertEqual(response.status_code, 404)

    def test_provider_error_returns_502(self):
        client, project_id, _ = _http(_FakeProvider(error=ProviderError(
            code=ProviderErrorCode.TIMEOUT, message="timeout",
            retryable=True, provider="llm_gateway",
        )))
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "이어서 써줘."},
        )
        self.assertEqual(response.status_code, 502)

    def test_context_window_guard_rejection_returns_400_not_502(self):
        """K-3 창 가드 거부는 **4xx**다(오너 2026-07-30).

        under-strict: 502로 새면 클라이언트에게 "상류 장애 → 재시도해 보라"로 보이는데
        이 실패는 결정적이다(입력을 줄여야 한다). over-strict: 위 셀이 다른 provider
        실패가 400으로 새지 않는 것을 함께 잠근다.

        detail이 수치를 실어 나르는 것이 오너 결정의 "경고" 절반이다 — 상태코드는 기계용,
        detail은 사람용이라는 H3 계약대로 문자열 분기는 하지 않는다.
        """
        client, project_id, _ = _http(_FakeProvider(error=ProviderError(
            code=ProviderErrorCode.CONTEXT_WINDOW_EXCEEDED,
            message="context window exceeded before the call: input 11905 + "
                    "output cap 6144 = 18049 > window 16384",
            retryable=False, provider="llm_gateway",
        )))
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "이어서 써줘."},
        )
        self.assertEqual(response.status_code, 400)
        for number in ("11905", "6144", "16384"):
            self.assertIn(number, response.json()["detail"])

    def test_context_search_budget_exceeded_returns_504(self):
        # the context-search leg of the orchestration: budget exhaustion → 504.
        client, project_id, _ = _http(
            _FakeProvider(),
            context_error=ContextSearchBudgetExceeded("budget exhausted"),
        )
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "이어서 써줘."},
        )
        self.assertEqual(response.status_code, 504)

    def test_context_search_failure_returns_502(self):
        # the context-search leg failing (e.g. planner LLM) → 502, distinct from
        # the writing provider fault path.
        client, project_id, _ = _http(
            _FakeProvider(),
            context_error=ContextSearchFailed(
                ContextSearchErrorType.LLM_ERROR, "planner failed"
            ),
        )
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "이어서 써줘."},
        )
        self.assertEqual(response.status_code, 502)


class WritingOutputLengthPresetTest(unittest.TestCase):
    """증분 2 (D3=A): the output-length preset maps to output tokens server-side.

    Boundary matrix — the request field `output_length` selects the output token
    cap the generation runs with, and the SERVER owns the mapping:
      - default (field omitted)   → short → 1024  (backward compat, pre-slice value)
      - short/medium/long         → 1024/2048/4096 (confirmed defaults)
      - unknown value             → 400 (never a silent default; model not reached)
      - env override / short base → the mapped value changes
      - value < 1 / non-int env   → app startup fails loudly
    The preset governs OUTPUT tokens only; `max_tokens` (the input ContextPackage
    budget) is a separate axis the preset must not move (over-strict guard). And
    `long` (4096, ~91s) exceeds WRITING_LOOP_MAX_WALL_CLOCK_MS, so the preset is a
    generate-only knob and must not exist on the revise-and-gate loop request.
    """

    def _generated_output_tokens(self, extra):
        provider = _FakeProvider(content="이어진 장면.")
        client, project_id, _ = _http(provider, package=_package())
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "이어서 써줘.", **extra},
        )
        self.assertEqual(response.status_code, 200)
        return provider.last_request.max_tokens

    def test_default_preset_is_short_1024(self):
        # under-strict: omitting the field keeps the pre-slice single value.
        self.assertEqual(self._generated_output_tokens({}), 1024)

    def test_short_preset_override_reaches_generation(self):
        # Load-bearing guard for the short/base path SPECIFICALLY. The service's
        # own construction default is also 1024, so `test_default_preset_is_short`
        # alone cannot prove the endpoint resolves+passes the preset (both paths
        # give 1024). Overriding short to a value the service default is NOT makes
        # the omitted-field request bite: dropping `max_output_tokens=` from the
        # endpoint re-fails this (provider would get the service default 1024).
        provider = _FakeProvider(content="x")
        with patch.dict(os.environ, {"WRITING_OUTPUT_LENGTH_SHORT": "1500"}):
            client, project_id, _ = _http(provider, package=_package())
            response = client.post(
                f"/projects/{project_id}/writing/generate",
                json={"request_id": "wr1", "instruction": "이어서 써줘."},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(provider.last_request.max_tokens, 1500)

    def test_presets_map_to_confirmed_tokens(self):
        # short is synchronous (the provider sees the resolved cap); medium/long are
        # async under 증분 2c — the endpoint returns 202 and carries the resolved cap
        # on the enqueued job's ``max_output_tokens`` (the worker consumes it). Both
        # channels must map the preset to the same confirmed token counts; asserting
        # only the sync channel would let the async resolution silently drift.
        self.assertEqual(
            self._generated_output_tokens({"output_length": "short"}), 1024
        )
        for preset, expected in (("medium", 2048), ("long", 4096)):
            with self.subTest(preset=preset):
                jobs = WritingGenerationJobService(
                    InMemoryWritingGenerationJobRepository()
                )
                client, project_id, _ = _http(
                    _FakeProvider(), package=_package(),
                    writing_generation_job_service=jobs,
                )
                response = client.post(
                    f"/projects/{project_id}/writing/generate",
                    json={"request_id": "wr1", "instruction": "이어서 써줘.",
                          "output_length": preset,
                          "current_position": {"draft_id": "d1", "version_id": "v1"}},
                )
                self.assertEqual(response.status_code, 202)
                job_id = response.json()["job"]["job_id"]
                self.assertEqual(jobs.get(job_id).max_output_tokens, expected)

    def test_unknown_preset_is_400_and_never_reaches_model(self):
        provider = _FakeProvider()
        client, project_id, _ = _http(provider, package=_package())
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "x",
                  "output_length": "epic"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(provider.last_request)

    def test_preset_is_independent_of_input_max_tokens(self):
        # over-strict guard: input budget (max_tokens) and output preset are
        # separate axes — moving one must not move the other. Under 증분 2c long is
        # async, so both axes land on the enqueued job: ``max_output_tokens`` (the
        # output preset) and ``max_tokens`` (the input ContextPackage budget the
        # worker will pass to context search). Collapsing the two would cross-wire
        # the axes on the job.
        jobs = WritingGenerationJobService(InMemoryWritingGenerationJobRepository())
        client, project_id, _ = _http(
            _FakeProvider(), package=_package(),
            writing_generation_job_service=jobs,
        )
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "이어서 써줘.",
                  "max_tokens": 512, "output_length": "long",
                  "current_position": {"draft_id": "d1", "version_id": "v1"}},
        )
        self.assertEqual(response.status_code, 202)
        job = jobs.get(response.json()["job"]["job_id"])
        self.assertEqual(job.max_output_tokens, 4096)  # output → preset
        self.assertEqual(job.max_tokens, 512)          # input → max_tokens

    def test_env_override_remaps_preset(self):
        with patch.dict(os.environ, {"WRITING_OUTPUT_LENGTH_MEDIUM": "3000"}):
            self.assertEqual(
                _writing_output_length_tokens()[OutputLength.MEDIUM], 3000,
            )

    def test_short_defaults_to_generate_max_tokens_env(self):
        # backward compat: the existing WRITING_GENERATE_MAX_TOKENS still tunes the
        # short/base preset unless a dedicated override wins.
        with patch.dict(os.environ, {"WRITING_GENERATE_MAX_TOKENS": "800"}):
            self.assertEqual(
                _writing_output_length_tokens()[OutputLength.SHORT], 800,
            )
        with patch.dict(os.environ, {"WRITING_GENERATE_MAX_TOKENS": "800",
                                     "WRITING_OUTPUT_LENGTH_SHORT": "900"}):
            self.assertEqual(
                _writing_output_length_tokens()[OutputLength.SHORT], 900,
            )

    def test_invalid_env_fails_app_creation(self):
        invalid = (
            ("WRITING_OUTPUT_LENGTH_SHORT", "0"),
            ("WRITING_OUTPUT_LENGTH_MEDIUM", "-1"),
            ("WRITING_OUTPUT_LENGTH_LONG", "0"),
            ("WRITING_OUTPUT_LENGTH_MEDIUM", "not-an-integer"),
        )
        for name, value in invalid:
            with self.subTest(name=name, value=value), patch.dict(
                os.environ, {name: value}
            ):
                with self.assertRaises(ValueError):
                    create_app()

    def test_output_length_is_a_generate_only_knob(self):
        # The long preset must not enter the revise-and-gate loop (91s > 60s loop
        # wall clock). Pinned structurally: the field is on generate, not on the
        # loop request model.
        self.assertIn("output_length", WritingGenerateRequest.model_fields)
        self.assertNotIn("output_length", WritingReviseRequest.model_fields)


class WritingReportBudgetTest(unittest.TestCase):
    """The self-report budget must stay above the longest prose preset.

    The report is a structured JSON summary OF the generated prose, so its output
    cap has to exceed the prose it describes. When it did not (the 1024 default
    shipped alongside the 2048/4096 presets of 증분 2), the report JSON was cut
    off mid-string and every affected generation failed as `invalid_report` —
    reproduced live on 2026-07-22, where the truncation always landed in the same
    ~2200-character window no matter how long the prose was.

    This is the lock that makes the coupling explicit: raising
    WRITING_OUTPUT_LENGTH_LONG without raising the report budget re-fails here.
    """

    def test_report_budget_exceeds_longest_prose_preset(self):
        longest = max(_writing_output_length_tokens().values())
        self.assertGreater(WRITING_REPORT_DEFAULT_MAX_TOKENS, longest)

    def test_raising_the_long_preset_alone_is_caught(self):
        # under-strict: the coupling is checked against the CURRENT preset values,
        # not against a hard-coded 4096, so an operator who lifts the prose ceiling
        # past the report budget trips this instead of hitting truncation live.
        with patch.dict(
            os.environ,
            {"WRITING_OUTPUT_LENGTH_LONG": str(WRITING_REPORT_DEFAULT_MAX_TOKENS)},
        ):
            longest = max(_writing_output_length_tokens().values())
            self.assertFalse(WRITING_REPORT_DEFAULT_MAX_TOKENS > longest)

    def test_default_budget_reaches_the_report_provider(self):
        # over-strict: the constant must actually be what the report service runs
        # with. Reverting _build_report_service to a literal 1024 re-fails here.
        service = _build_report_service(_FakeProvider())
        self.assertEqual(service.max_tokens, WRITING_REPORT_DEFAULT_MAX_TOKENS)

    def test_report_budget_is_env_adjustable(self):
        with patch.dict(os.environ, {"WRITING_REPORT_MAX_TOKENS": "2048"}):
            service = _build_report_service(_FakeProvider())
        self.assertEqual(service.max_tokens, 2048)


class _WindowCapabilities:
    """창·system 토큰 계수를 아는 가짜 게이트웨이 capabilities (R-a 유도용)."""

    def __init__(self, *, window, system_tokens=465):
        self._window = window
        self._system = system_tokens

    async def context_window(self):
        return self._window

    async def count_tokens(self, text):
        return self._system


# revise-and-gate 루프 collaborator stub. 유도 wiring만 잠그므로 루프는 첫 판에 PASS로
# 끝난다(revise → report → gate PASS). 루프 본체의 행동은 test_writing_revise/
# retrieval/loop_budget가 잠근다.
class _StubReviser:
    def validate_inputs(self, candidate, finding, instruction):
        pass

    async def revise(self, *, candidate, finding, instruction, package):
        return replace(candidate, text="수정된 문장")


class _StubReporter:
    async def enrich(self, candidate, package):
        return candidate


class _PassGate:
    async def evaluate(self, *, request, candidate, package):
        return WritingGateResult(
            request.request_id, request.project_id, WritingGateDecision.PASS,
            (), (), "stub-pass",
        )


class WritingReviseGateBudgetDerivationTest(unittest.TestCase):
    """R-a (v1.7.66): revise-and-gate 루프도 진입 시점에 예산을 **창에서 유도**한다.

    여기가 wiring 잠금이다 — 유도 **산식**은 `test_report_budget_derivation.py`가,
    루프 본체는 `test_writing_revise/retrieval/loop_budget`가 잠근다. 본 슬라이스가
    새로 잠그는 것은 **엔드포인트가 요청 예산을 `derive_context_budget`로 거쳐
    context_search(→ 루프의 패키지 예산·merge 상한)에 전달한다**는 한 가지다.

    양방향:
      - 창을 알면 **줄인다**(요청 8192가 유도값으로 내려간다). 엔드포인트를 raw
        `body.max_tokens`로 되돌리면 context_search가 8192를 보게 돼 재실패한다.
      - 창을 모르면 **건드리지 않는다**(게이트웨이 없으면 model_capabilities=None →
        유도 no-op → 요청값 그대로). over-strict: 유도가 정상 요청을 깎지 않는다.
    """

    _CANDIDATE_TEXT = "아린은 성문 앞에서 멈췄다."

    def _post_revise_and_gate(self, app, project_id, *, max_tokens):
        client = _TestClient(app)
        return client.post(
            f"/projects/{project_id}/writing/revise-and-gate",
            json={
                "request_id": "rg1",
                "instruction": "이어서 수정해줘.",
                "candidate_text": self._CANDIDATE_TEXT,
                "max_tokens": max_tokens,
                "finding": {
                    "type": "continuity",
                    "severity": "warning",
                    "message": "시점이 틀렸다.",
                    "evidence": "단락 1",
                    "recommended_decision": "revise",
                },
            },
        )

    def test_window_known_reduces_the_loop_budget(self):
        # under-strict: 작은 창(8000)을 아는 capabilities에서 엔드포인트가 내린 예산은
        # 요청 8192보다 작고, **report 엔드포인트와 같은 입력**(후보 산문 추정)으로 계산한
        # 유도값과 정확히 일치한다 — (iii) 후보 길이에서 유도함을 함께 건다.
        caps = _WindowCapabilities(window=8000)
        context = _FakeContextSearch(_package())
        with patch.object(main_module, "_default_model_capabilities",
                          return_value=caps):
            app = create_app(
                writing_revision_service=_StubReviser(),
                writing_report_service=_StubReporter(),
                writing_gate_service=_PassGate(),
                context_search_service=context,
            )
        project_id = _TestClient(app).post(
            "/projects", json={"name": "Novel"}).json()["id"]
        response = self._post_revise_and_gate(app, project_id, max_tokens=8192)

        self.assertEqual(response.status_code, 200)
        expected = asyncio.run(derive_context_budget(
            requested_tokens=8192,
            capabilities=caps,
            report_output_cap=WRITING_REPORT_DEFAULT_MAX_TOKENS,
            report_system_template=REPORT_SYSTEM_TEMPLATE,
            candidate_tokens_upper_bound=candidate_tokens_from_text(
                self._CANDIDATE_TEXT),
        ))
        self.assertEqual(context.last_request.context_budget.max_tokens, expected)
        self.assertLess(context.last_request.context_budget.max_tokens, 8192)

    def test_window_unknown_leaves_the_loop_budget_unchanged(self):
        # over-strict: 게이트웨이를 모르면(기본 — env 없음) model_capabilities=None이고
        # 유도는 no-op다. context_search는 요청 예산을 그대로 받는다(종전 동작).
        context = _FakeContextSearch(_package())
        app = create_app(
            writing_revision_service=_StubReviser(),
            writing_report_service=_StubReporter(),
            writing_gate_service=_PassGate(),
            context_search_service=context,
        )
        project_id = _TestClient(app).post(
            "/projects", json={"name": "Novel"}).json()["id"]
        response = self._post_revise_and_gate(app, project_id, max_tokens=8192)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(context.last_request.context_budget.max_tokens, 8192)


class WritingContextBudgetApiTest(unittest.TestCase):
    """K-4 (프론트 글자수 표시·경고): GET /writing/budget이 R-a 유도 예산을 per-preset으로
    프론트에 노출한다. wiring 잠금 — 유도 **산식**은 test_report_budget_derivation.py가
    잠그고, 여기는 **엔드포인트가 출력 프리셋마다 derive_context_budget을 거쳐 노출한다**는
    한 가지를 건다.

    양방향:
      - 창을 알면 preset마다 줄어든다(후보 상한 1024<2048<4096). 엔드포인트가 세 preset에
        같은 upper bound를 건네면(변이) 셋이 같아져 expected 불일치로 이 셀이 문다.
      - 창을 모르면(model_capabilities=None) 요청값 그대로 — 유도가 정상 요청을 깎지 않는다.
    """

    def _budget(self, app, project_id):
        return _TestClient(app).get(f"/projects/{project_id}/writing/budget")

    def test_known_window_derives_each_preset(self):
        # under-strict: 창을 아는 capabilities에서 세 preset 값이 derive 산식과 정확히
        # 일치한다(베타 실측 창 16384 — short=8192 clamp · medium≈7273 · long≈5307).
        caps = _WindowCapabilities(window=16384)
        with patch.object(main_module, "_default_model_capabilities",
                          return_value=caps):
            app = create_app()
        project_id = _TestClient(app).post(
            "/projects", json={"name": "Novel"}).json()["id"]
        response = self._budget(app, project_id)

        self.assertEqual(response.status_code, 200)
        tokens = response.json()["context_budget_tokens"]
        self.assertEqual(set(tokens), {"short", "medium", "long"})

        presets = _writing_output_length_tokens()

        async def expected(upper_bound: int) -> int:
            return await derive_context_budget(
                requested_tokens=DEFAULT_CONTEXT_BUDGET_TOKENS,
                capabilities=caps,
                report_output_cap=WRITING_REPORT_DEFAULT_MAX_TOKENS,
                report_system_template=REPORT_SYSTEM_TEMPLATE,
                candidate_tokens_upper_bound=upper_bound,
            )

        self.assertEqual(
            tokens["short"],
            asyncio.run(expected(presets[OutputLength.SHORT])))
        self.assertEqual(
            tokens["medium"],
            asyncio.run(expected(presets[OutputLength.MEDIUM])))
        self.assertEqual(
            tokens["long"],
            asyncio.run(expected(presets[OutputLength.LONG])))
        # 후보 상한이 클수록 예산이 줄어든다(long 출력 상한이 가장 크므로 long이 가장 작다).
        self.assertGreaterEqual(tokens["short"], tokens["long"])
        self.assertLess(tokens["long"], DEFAULT_CONTEXT_BUDGET_TOKENS)

    def test_unknown_window_leaves_the_requested_budget(self):
        # over-strict: 게이트웨이가 없으면(model_capabilities=None) 유도 no-op → 세 preset
        # 모두 요청값(DEFAULT_CONTEXT_BUDGET_TOKENS) 그대로. 유도가 정상 요청을 깎지 않는다.
        with patch.object(main_module, "_default_model_capabilities",
                          return_value=None):
            app = create_app()
        project_id = _TestClient(app).post(
            "/projects", json={"name": "Novel"}).json()["id"]
        response = self._budget(app, project_id)

        self.assertEqual(response.status_code, 200)
        tokens = response.json()["context_budget_tokens"]
        self.assertEqual(tokens["short"], DEFAULT_CONTEXT_BUDGET_TOKENS)
        self.assertEqual(tokens["medium"], DEFAULT_CONTEXT_BUDGET_TOKENS)
        self.assertEqual(tokens["long"], DEFAULT_CONTEXT_BUDGET_TOKENS)


class WritingAcceptBudgetDerivationTest(unittest.TestCase):
    """R-a (v1.7.66): `/writing/accept`도 report 다리(`WritingAcceptService.run`
    → `reporter.enrich`)를 지나므로 진입 시 창에서 예산을 유도한다.

    패턴 스윕으로 잡은 사이트다 — v1.7.65가 generate·worker·report에만 유도를 넣고
    accept는 원래 구현(2026-07-12) 그대로 raw로 남겨뒀었다. revise-and-gate와 같은
    결함·같은 수정(report 엔드포인트처럼 후보 산문 추정을 후보 상한으로). 여기서도
    엔드포인트→context_search 배선만 잠그고, accept.run의 이후 동작(승격 저장 등)은
    `test_writing_accept.py`가 담당한다.
    """

    _CANDIDATE_TEXT = "아린은 성문 앞에서 멈췄다."

    def _post_accept(self, app, project_id, *, max_tokens):
        client = _TestClient(app)
        return client.post(
            f"/projects/{project_id}/writing/accept",
            json={
                "request_id": "ac1",
                "draft_id": "d1",
                "base_version_id": "v1",
                "idempotency_key": "k1",
                "instruction": "이 장면을 받아들여라.",
                "candidate_text": self._CANDIDATE_TEXT,
                "max_tokens": max_tokens,
            },
        )

    def test_window_known_reduces_the_accept_budget(self):
        # under-strict: 작은 창을 알면 accept가 context_search에 내린 예산은 요청
        # 8192보다 작고, report 엔드포인트와 같은 입력(후보 산문 추정)으로 계산한
        # 유도값과 일치한다. 엔드포인트를 raw로 되돌리면 8192가 와 재실패한다.
        caps = _WindowCapabilities(window=8000)
        context = _FakeContextSearch(_package())
        with patch.object(main_module, "_default_model_capabilities",
                          return_value=caps):
            app = create_app(
                # writing_accept is built when writing_gate is non-None; the
                # reporter is None here (no gateway) — fine, we only need the
                # endpoint to reach build_context_package.
                writing_gate_service=_PassGate(),
                context_search_service=context,
            )
        project_id = _TestClient(app).post(
            "/projects", json={"name": "Novel"}).json()["id"]
        # Order-dependent by design: this locks the BUDGET derivation wiring
        # (observed at context_search.last_request), not accept semantics, so
        # base_version "v1" is deliberately unseeded — accept.run fails AFTER
        # build_context_package. If the endpoint ever validates base_version
        # BEFORE context search, last_request stays None and the
        # assertIsNotNone below fails — that failure is correct: it means the
        # derivation no longer reaches context search for this path.
        self._post_accept(app, project_id, max_tokens=8192)

        self.assertIsNotNone(context.last_request)
        expected = asyncio.run(derive_context_budget(
            requested_tokens=8192,
            capabilities=caps,
            report_output_cap=WRITING_REPORT_DEFAULT_MAX_TOKENS,
            report_system_template=REPORT_SYSTEM_TEMPLATE,
            candidate_tokens_upper_bound=candidate_tokens_from_text(
                self._CANDIDATE_TEXT),
        ))
        self.assertEqual(context.last_request.context_budget.max_tokens, expected)
        self.assertLess(context.last_request.context_budget.max_tokens, 8192)

    def test_window_unknown_leaves_the_accept_budget_unchanged(self):
        # over-strict: 게이트웨이를 모르면 model_capabilities=None → 유도 no-op →
        # 요청 예산 그대로(종전 동작).
        context = _FakeContextSearch(_package())
        app = create_app(
            writing_gate_service=_PassGate(),
            context_search_service=context,
        )
        project_id = _TestClient(app).post(
            "/projects", json={"name": "Novel"}).json()["id"]
        self._post_accept(app, project_id, max_tokens=8192)

        self.assertIsNotNone(context.last_request)
        self.assertEqual(context.last_request.context_budget.max_tokens, 8192)


class WritingGenerateEnvelopeKeyTest(unittest.TestCase):
    """C0 exact-key safety net for the generate envelope (SoT v1.7.1, D3=A).

    ``response_model`` silently DROPS any field a model does not declare, so a
    model narrower than ``_writing_candidate_payload`` would delete fields from
    the public envelope with no error. These assertions pin the COMPLETE key set
    of the candidate payload and every nested object BEFORE the model is applied,
    so a too-narrow ``WritingCandidatePayload`` bites here rather than shipping a
    silently-narrowed response. Runs both directions: a too-wide model would also
    fail behavioural tests (extra key never emitted).
    """

    def test_candidate_envelope_keys_are_complete(self):
        # A fully-populated candidate (claims/hints/risks/pointers) so every
        # nested key set is exercised, not just the empty top level.
        client, project_id, _ = _http(
            _FakeProvider(content="이어진 장면."),
            package=_package(),
            reporter=_FakeReporter(),
        )
        body = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "이어서 써줘."},
        ).json()
        self.assertEqual(set(body), {
            "request_id", "project_id", "task_type", "output_type", "text",
            "status", "self_reported_constraints", "candidate_claims",
            "new_memory_hints", "risk_notes", "candidate_id",
            "generated_by_model", "intent", "next_unit",
        })
        self.assertEqual(set(body["candidate_claims"][0]), {
            "text", "type", "requires_gate_check", "related_context_pointers",
        })
        self.assertEqual(
            set(body["candidate_claims"][0]["related_context_pointers"][0]),
            {"collection", "document_id", "version_id", "content_hash"},
        )
        self.assertEqual(set(body["new_memory_hints"][0]), {
            "type", "text", "confidence", "should_analyze_after_save",
        })
        self.assertEqual(
            set(body["risk_notes"][0]), {"type", "severity", "message"},
        )

    def test_policy_bools_are_server_constants_on_the_public_envelope(self):
        """검증 하드닝(2026-09-03 §H4) — 정책 bool의 이중 잠금.

        report v3부터 모델은 requires_gate_check/should_analyze_after_save를
        내지 않고 서버 정책 상수(True)가 채운다(파서 기본값 반전은
        test_writing_report가 잡는다). 이 셀은 그 짝으로 **공개 wire**를 잡는다:
        실 파서(v3 3키 출력)를 통과한 후보가 generate 응답에 True를 실어 나르는지.
        under-strict: 파서가 모델 출력을 다시 읽거나 payload 조립이 다른 값을
        읽으면 이 표면 값이 바뀌어 실패한다.
        over-strict: 값을 뒤집는 과잉 교정(not)도 실패한다.
        """
        report = json.dumps({
            "self_reported_constraints": ["제한 시점"],
            "candidate_claims": [{"text": "문이 열렸다",
                                  "type": "narrative_event",
                                  "related_context_pointers": []}],
            "new_memory_hints": [{"type": "event", "text": "문이 열림",
                                  "confidence": 0.8}],
            "risk_notes": [],
        }, ensure_ascii=False)
        provider = FakeLLMProvider([
            GenerationResult(model="fake-writer", content="이어진 장면.",
                             finish_reason="stop", usage=TokenUsage(1, 1)),
            GenerationResult(model="fake-writer", content=report,
                             finish_reason="stop", usage=TokenUsage(1, 1)),
        ])
        templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        seed_report_template(templates)
        client, project_id, _ = _http(
            provider,
            package=_package(),
            reporter=WritingCandidateReportService(
                provider, prompt_templates=templates),
        )
        body = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "이어서 써줘."},
        ).json()
        self.assertIs(body["candidate_claims"][0]["requires_gate_check"], True)
        self.assertIs(
            body["new_memory_hints"][0]["should_analyze_after_save"], True)


class WritingGenerateAsyncBranchTest(unittest.TestCase):
    """증분 2c (D5=A): the generate endpoint branches on ``output_length``.

    Boundary matrix — the preset selects sync vs async (the server owns the
    mapping; the worker owns execution):
      - short (1024)             → 200 + WritingCandidatePayload (sync, unchanged)
      - medium (2048)/long (4096)→ 202 + {job, idempotent_replay} (enqueued,
                                   non-blocking; worker runs it)
      - async + no current_position → 400 (the pad is keyed per-draft)
      - short + no current_position → 200 (over-strict: the 400 is async-only)
      - async does NOT call writing.generate/context_search/scratch (worker's job)
      - same (project_id, request_id) re-POST → 202 idempotent_replay=true, one job
      - GET .../generation-jobs/{job_id} → 200 + full status payload
      - GET 404 not-found / wrong-project; GET surfaces terminal fields
    """

    _POSITION = {"draft_id": "d1", "version_id": "v1"}

    def _http(self, *, provider=None, jobs=None):
        return _http(provider, package=_package(),
                     writing_generation_job_service=jobs)

    def _async_body(self, request_id="wr1", output_length="medium"):
        return {
            "request_id": request_id, "instruction": "이어서 써줘.",
            "output_length": output_length, "current_position": self._POSITION,
        }

    def test_medium_preset_enqueues_job_and_returns_202(self):
        # under-strict (async fire): medium + current_position → 202, job pending.
        provider = _FakeProvider(content="should not be used")
        jobs = WritingGenerationJobService(InMemoryWritingGenerationJobRepository())
        client, project_id, context = self._http(provider=provider, jobs=jobs)
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json=self._async_body(output_length="medium"),
        )
        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertFalse(body["idempotent_replay"])
        self.assertEqual(body["job"]["status"], "pending")
        self.assertEqual(body["job"]["output_length"], "medium")
        self.assertEqual(body["job"]["project_id"], project_id)
        self.assertEqual(body["job"]["draft_id"], "d1")
        self.assertEqual(body["job"]["version_id"], "v1")
        # The endpoint did NOT run the pipeline — that is the worker's job, so the
        # provider AND context search were never consulted. (Dropping the async
        # branch would call generate + context and set both last_request fields.)
        self.assertIsNone(provider.last_request)
        self.assertIsNone(context.last_request)

    def test_long_preset_also_enqueues(self):
        provider = _FakeProvider()
        jobs = WritingGenerationJobService(InMemoryWritingGenerationJobRepository())
        client, project_id, _ = self._http(provider=provider, jobs=jobs)
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json=self._async_body(output_length="long"),
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job"]["output_length"], "long")

    def test_short_preset_stays_synchronous(self):
        # over-strict: short must NOT take the async branch. short returns a real
        # candidate (200) and DID call generate — flipping short into the async
        # branch would make this 400 (no current_position) and leave last_request
        # None.
        provider = _FakeProvider(content="이어진 장면.")
        client, project_id, _ = self._http(provider=provider)
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "이어서 써줘.",
                  "output_length": "short"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "이어진 장면.")
        self.assertIsNotNone(provider.last_request)

    def test_async_without_current_position_is_400(self):
        # under-strict: the pad is per-draft, so async with no anchor has nowhere
        # to display. Removing the 400 would enqueue an unanchored job.
        provider = _FakeProvider()
        jobs = WritingGenerationJobService(InMemoryWritingGenerationJobRepository())
        client, project_id, _ = self._http(provider=provider, jobs=jobs)
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "x",
                  "output_length": "medium"},  # no current_position
        )
        self.assertEqual(response.status_code, 400)
        # Rejection enqueues nothing.
        self.assertEqual(jobs.list_for_draft(project_id, "d1"), ())

    def test_short_without_current_position_is_not_400(self):
        # over-strict guard: the async-only 400 must not bleed into the short path.
        # short with no current_position still works (positionless generate allowed).
        provider = _FakeProvider(content="ok")
        client, project_id, _ = self._http(provider=provider)
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "x",
                  "output_length": "short"},  # no current_position
        )
        self.assertEqual(response.status_code, 200)

    def test_async_is_idempotent_on_request_id(self):
        # same (project_id, request_id) re-POST returns the SAME job, not a second
        # generation. Dropping the idempotency lookup creates a duplicate.
        provider = _FakeProvider()
        jobs = WritingGenerationJobService(InMemoryWritingGenerationJobRepository())
        client, project_id, _ = self._http(provider=provider, jobs=jobs)
        body = self._async_body()
        first = client.post(f"/projects/{project_id}/writing/generate", json=body)
        second = client.post(f"/projects/{project_id}/writing/generate", json=body)
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertFalse(first.json()["idempotent_replay"])
        self.assertTrue(second.json()["idempotent_replay"])
        self.assertEqual(first.json()["job"]["job_id"],
                         second.json()["job"]["job_id"])

    def test_async_idempotency_key_is_project_plus_request(self):
        # over-strict complement: the idempotency key is (project_id, request_id),
        # NOT either axis alone. Two DIFFERENT request_ids in the same project must
        # each mint a fresh job (idempotent_replay=false, distinct job_ids). A
        # too-coarse key (project-only or request-only) would collapse these into a
        # replay — this test bites if the key is narrowed.
        jobs = WritingGenerationJobService(InMemoryWritingGenerationJobRepository())
        client, project_id, _ = self._http(provider=_FakeProvider(), jobs=jobs)
        first = client.post(
            f"/projects/{project_id}/writing/generate",
            json=self._async_body(request_id="wr-a"),
        ).json()
        second = client.post(
            f"/projects/{project_id}/writing/generate",
            json=self._async_body(request_id="wr-b"),
            # Slice 8.3 Q8=C: a *different* request_id while the first job is
            # still pending is exactly the mistaken duplicate the in-flight
            # guard refuses (429). Confirming is the product's stated way to
            # start a second one deliberately, so this test — which is about
            # key granularity, not about that guard — takes it.
            headers={"X-Confirm-Duplicate": "1"},
        ).json()
        self.assertFalse(first["idempotent_replay"])
        self.assertFalse(second["idempotent_replay"])
        self.assertNotEqual(first["job"]["job_id"], second["job"]["job_id"])

    def test_async_bypasses_sync_only_503_checks(self):
        # SoT §272: the async branch must NOT consult the sync-only writing /
        # context_search 503 guards — the endpoint uses neither for async (the
        # worker has its own gateway/context). With BOTH services unconfigured an
        # async preset still enqueues and returns 202. over-strict mutation: hoisting
        # either 503 guard above the async branch turns this 202 into a 503.
        jobs = WritingGenerationJobService(InMemoryWritingGenerationJobRepository())
        client, project_id, _ = _http(
            provider=None, with_context=False,
            writing_generation_job_service=jobs,
        )
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json=self._async_body(output_length="medium"),
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job"]["status"], "pending")

    def test_async_does_not_write_scratch_at_endpoint(self):
        # The worker (2b) writes the result to scratch; the endpoint must not, so a
        # refresh right after enqueue shows no premature candidate. (If the endpoint
        # re-used the sync scratch-save, an empty-text premature entry would appear.)
        provider = _FakeProvider()
        jobs = WritingGenerationJobService(InMemoryWritingGenerationJobRepository())
        client, project_id, _ = self._http(provider=provider, jobs=jobs)
        client.post(f"/projects/{project_id}/writing/generate",
                    json=self._async_body())
        scratch = client.get(
            f"/projects/{project_id}/writing/scratch?draft_id=d1"
        ).json()
        self.assertEqual(scratch["items"], [])

    def test_get_generation_job_returns_status(self):
        provider = _FakeProvider()
        jobs = WritingGenerationJobService(InMemoryWritingGenerationJobRepository())
        client, project_id, _ = self._http(provider=provider, jobs=jobs)
        job_id = client.post(
            f"/projects/{project_id}/writing/generate",
            json=self._async_body(),
        ).json()["job"]["job_id"]
        body = client.get(
            f"/projects/{project_id}/writing/generation-jobs/{job_id}"
        ).json()
        self.assertEqual(body["job_id"], job_id)
        self.assertEqual(body["status"], "pending")
        self.assertIsNone(body["result_scratch_id"])
        self.assertIsNone(body["failure_reason"])

    def test_get_generation_job_404_unknown(self):
        client, project_id, _ = self._http(provider=_FakeProvider())
        response = client.get(
            f"/projects/{project_id}/writing/generation-jobs/wgj:ghost"
        )
        self.assertEqual(response.status_code, 404)

    def test_get_generation_job_404_nonexistent_project(self):
        # GET falls under the spec's "404 미발견" arm when the path project itself
        # never existed (_require_project_exists guard). Distinct from unknown-job
        # and wrong-project: a nonexistent project must 404 before any job lookup.
        client, _project_id, _ = self._http(provider=_FakeProvider())
        response = client.get(
            "/projects/ghost/writing/generation-jobs/wgj:any"
        )
        self.assertEqual(response.status_code, 404)

    def test_get_generation_job_404_wrong_project(self):
        # project-scoped: a job enqueued under project A is not readable via
        # project B's path (MVP single-user, but the invariant still holds).
        provider = _FakeProvider()
        jobs = WritingGenerationJobService(InMemoryWritingGenerationJobRepository())
        client, project_a, _ = self._http(provider=provider, jobs=jobs)
        project_b = client.post("/projects", json={"name": "Other"}).json()["id"]
        job_id = client.post(
            f"/projects/{project_a}/writing/generate",
            json=self._async_body(),
        ).json()["job"]["job_id"]
        response = client.get(
            f"/projects/{project_b}/writing/generation-jobs/{job_id}"
        )
        self.assertEqual(response.status_code, 404)

    def test_get_generation_job_surfaces_terminal_fields(self):
        # Seed succeeded + failed jobs directly via the service, then GET each. The
        # terminal fields (result_scratch_id / failure_reason / failure_detail) must
        # round-trip through the response_model on both terminal states.
        provider = _FakeProvider()
        jobs = WritingGenerationJobService(InMemoryWritingGenerationJobRepository())
        client, project_id, _ = self._http(provider=provider, jobs=jobs)

        def _enqueue(request_id, output_length):
            return jobs.enqueue(
                project_id=project_id, draft_id="d1", request_id=request_id,
                task_type="continue_scene", instruction="x", draft_excerpt="",
                query=None, output_length=output_length, max_output_tokens=2048,
                max_tokens=4096, version_id="v1",
            ).job

        ok = _enqueue("wr-ok", "medium")
        jobs.mark_succeeded(jobs.claim_next(), result_scratch_id="scratch-1")
        fail = _enqueue("wr-bad", "long")
        jobs.mark_failed(
            jobs.claim_next(),
            reason=WritingGenerationJobFailureReason.PROVIDER_TIMEOUT,
            detail="upstream 504",
        )
        ok_body = client.get(
            f"/projects/{project_id}/writing/generation-jobs/{ok.id}").json()
        self.assertEqual(ok_body["status"], "succeeded")
        self.assertEqual(ok_body["result_scratch_id"], "scratch-1")
        self.assertIsNone(ok_body["failure_reason"])
        fail_body = client.get(
            f"/projects/{project_id}/writing/generation-jobs/{fail.id}").json()
        self.assertEqual(fail_body["status"], "failed")
        self.assertEqual(fail_body["failure_reason"], "provider_timeout")
        self.assertEqual(fail_body["failure_detail"], "upstream 504")
        self.assertIsNone(fail_body["result_scratch_id"])


class WritingGenerationJobRetryTest(unittest.TestCase):
    """Retry slice (async-pad D4=A): POST .../generation-jobs/{job_id}/retry
    resets a FAILED job to PENDING so the worker re-claims it. Mirrors the
    Analysis retry endpoint — failed→pending, non-failed 409, 404 missing/wrong
    project. No separate run call: the worker's claim loop picks up PENDING.
    """

    def _seed(self):
        jobs = WritingGenerationJobService(InMemoryWritingGenerationJobRepository())
        client, project_id, _ = _http(_FakeProvider(), package=_package(),
                                      writing_generation_job_service=jobs)
        return client, project_id, jobs

    def _enqueue(self, jobs, project_id, request_id="wr1"):
        return jobs.enqueue(
            project_id=project_id, draft_id="d1", request_id=request_id,
            task_type="continue_scene", instruction="x", draft_excerpt="",
            query=None, output_length="medium", max_output_tokens=2048,
            max_tokens=4096, version_id="v1",
        ).job

    def test_retry_failed_resets_to_pending_and_is_reclaimable(self):
        # under-strict — the slice's purpose: a failed job becomes PENDING (failure
        # cleared) and the worker can claim it again.
        client, project_id, jobs = self._seed()
        job = self._enqueue(jobs, project_id)
        jobs.claim_next()
        failed = jobs.mark_failed(
            jobs.get(job.id),
            reason=WritingGenerationJobFailureReason.PROVIDER_TIMEOUT,
            detail="upstream 504")
        # S-1 D2: 재시도 쿨다운(60s)을 지난 상태로 만든다 — 서비스 클록이 실시간이므로
        # 저장된 실패 시각을 되돌려 놓는다(test_application_api 와 같은 처방).
        jobs._repo.update(replace(  # noqa: SLF001 — 옛 시각의 행을 만드는 입력
            failed, failed_at=datetime.now(UTC) - timedelta(seconds=61)))
        response = client.post(
            f"/projects/{project_id}/writing/generation-jobs/{job.id}/retry")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "pending")
        self.assertIsNone(body["failure_reason"])
        self.assertIsNone(body["failure_detail"])
        # the worker's claim loop can now pick it up again
        self.assertIsNotNone(jobs.claim_next())

    def test_retry_non_failed_states_are_409(self):
        # over-strict: only FAILED is retryable — pending/running/succeeded raise
        # InvalidJobStateTransition, mapped to 409 (never silently reset).
        for state in ("pending", "running", "succeeded"):
            with self.subTest(state=state):
                client, project_id, jobs = self._seed()
                job = self._enqueue(jobs, project_id)
                if state in ("running", "succeeded"):
                    jobs.claim_next()
                if state == "succeeded":
                    jobs.mark_succeeded(jobs.get(job.id), result_scratch_id="s1")
                response = client.post(
                    f"/projects/{project_id}/writing/generation-jobs/{job.id}/retry")
                self.assertEqual(response.status_code, 409)

    def test_retry_404_unknown_job(self):
        client, project_id, _ = self._seed()
        response = client.post(
            f"/projects/{project_id}/writing/generation-jobs/wgj:ghost/retry")
        self.assertEqual(response.status_code, 404)

    def test_retry_404_wrong_project(self):
        # project-scoped: a failed job under project A is not retryable via B's path.
        client, project_a, jobs = self._seed()
        project_b = client.post("/projects", json={"name": "Other"}).json()["id"]
        job = self._enqueue(jobs, project_a)
        jobs.claim_next()
        jobs.mark_failed(
            jobs.get(job.id),
            reason=WritingGenerationJobFailureReason.PROVIDER_ERROR)
        response = client.post(
            f"/projects/{project_b}/writing/generation-jobs/{job.id}/retry")
        self.assertEqual(response.status_code, 404)


class WritingGenerationJobEnvelopeKeyTest(unittest.TestCase):
    """C0 exact-key safety net for the async generate surface (v1.7.27, 증분 2c).

    ``response_model`` (GET) and the ``responses={}`` doc (202) silently DROP any
    field a model does not declare, so a model narrower than
    ``_writing_generation_job_payload`` would delete fields from the public status
    surface with no error. These pin the COMPLETE key set of the job status payload
    (GET) and the 202 accepted envelope before the models are applied — a too-narrow
    WritingGenerationJobPayload / WritingGenerationJobAcceptedPayload bites here.
    """

    _POSITION = {"draft_id": "d1", "version_id": "v1"}

    def _seed(self):
        jobs = WritingGenerationJobService(InMemoryWritingGenerationJobRepository())
        client, project_id, _ = _http(_FakeProvider(),
                                      writing_generation_job_service=jobs)
        job_id = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "x",
                  "output_length": "medium", "current_position": self._POSITION},
        ).json()["job"]["job_id"]
        return client, project_id, job_id

    _JOB_KEYS = {
        "job_id", "request_id", "project_id", "draft_id", "version_id",
        "task_type", "output_length", "status", "created_at",
        "result_scratch_id", "failure_reason", "failure_detail",
    }

    def test_get_status_envelope_keys_are_complete(self):
        client, project_id, job_id = self._seed()
        body = client.get(
            f"/projects/{project_id}/writing/generation-jobs/{job_id}").json()
        self.assertEqual(set(body), self._JOB_KEYS)

    def test_accepted_envelope_keys_are_complete(self):
        jobs = WritingGenerationJobService(InMemoryWritingGenerationJobRepository())
        client, project_id, _ = _http(_FakeProvider(),
                                      writing_generation_job_service=jobs)
        body = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "x",
                  "output_length": "long", "current_position": self._POSITION},
        ).json()
        self.assertEqual(set(body), {"job", "idempotent_replay"})
        self.assertEqual(set(body["job"]), self._JOB_KEYS)


class WritingReportApiTest(unittest.TestCase):
    def _post(self, client, project_id, **overrides):
        payload = {
            "request_id": "wr1",
            "instruction": "이어서 써줘.",
            "candidate_text": "문이 열렸다.",
        }
        payload.update(overrides)
        return client.post(
            f"/projects/{project_id}/writing/report", json=payload
        )

    def test_inline_candidate_is_re_evaluated_with_server_context(self):
        # Under-strict guard: the endpoint must rebuild context server-side and
        # return the enriched public candidate envelope without persisting it.
        reporter = _FakeReporter()
        client, project_id, context = _http(
            package=_package(), report_service=reporter
        )

        response = self._post(client, project_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(reporter.calls, 1)
        self.assertEqual(context.last_request.project_id, project_id)
        self.assertEqual(context.last_request.query, "이어서 써줘.")
        self.assertEqual(reporter.last_candidate.text, "문이 열렸다.")
        self.assertEqual(reporter.last_package.project_id, project_id)
        body = response.json()
        self.assertEqual(body["request_id"], "wr1")
        self.assertEqual(body["candidate_claims"][0]["type"], "narrative_event")
        self.assertNotIn("claim_type", body["candidate_claims"][0])
        self.assertIsNone(body["candidate_id"])

    def test_invalid_inline_input_is_rejected_before_reporter(self):
        # Over-strict guard: malformed inline candidates are not sent to the LLM.
        reporter = _FakeReporter()
        client, project_id, _ = _http(report_service=reporter)

        for field in ("request_id", "instruction", "candidate_text"):
            with self.subTest(field=field):
                response = self._post(client, project_id, **{field: "   "})
                self.assertEqual(response.status_code, 400)
        self.assertEqual(reporter.calls, 0)

    def test_unsupported_task_type_is_rejected_before_reporter(self):
        # B1 closure: this is the report endpoint's own task-type boundary, not
        # the older generate endpoint guard.
        reporter = _FakeReporter()
        client, project_id, _ = _http(report_service=reporter)

        response = self._post(client, project_id, task_type="revise")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(reporter.calls, 0)

    def test_explicit_query_and_current_position_are_forwarded(self):
        reporter = _FakeReporter()
        client, project_id, context = _http(report_service=reporter)

        response = self._post(
            client,
            project_id,
            query="명시 검색어",
            current_position={"draft_id": "draft-1", "version_id": "version-2"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(context.last_request.query, "명시 검색어")
        self.assertEqual(context.last_request.current_position.draft_id, "draft-1")
        self.assertEqual(
            context.last_request.current_position.version_id, "version-2"
        )

    def test_report_does_not_save_draft(self):
        # H2 direct guard: candidate_id=None is only an envelope proxy; a save
        # spy proves the report endpoint itself leaves Core SOT untouched.
        core_sot = _NoWriteCoreSotService()
        client, project_id, _ = _http(
            report_service=_FakeReporter(), core_service=core_sot
        )

        response = self._post(client, project_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(core_sot.save_calls, 0)

    def test_report_dependencies_and_project_scope_are_enforced(self):
        client, project_id, _ = _http(with_context=False,
                                      report_service=_FakeReporter())
        self.assertEqual(self._post(client, project_id).status_code, 503)

        client, project_id, _ = _http()
        self.assertEqual(self._post(client, project_id).status_code, 503)

        client, _project_id, _ = _http(report_service=_FakeReporter())
        response = client.post("/projects/ghost/writing/report", json={
            "request_id": "wr1", "instruction": "x", "candidate_text": "본문"
        })
        self.assertEqual(response.status_code, 404)

    def test_report_and_context_failures_keep_public_mapping(self):
        cases = (
            (_FakeReporter(error=InvalidCandidateReport("invalid report")), None, 502),
            (_FakeReporter(error=ProviderError(
                code=ProviderErrorCode.TIMEOUT, message="timeout",
                retryable=True, provider="llm_gateway")), None, 504),
            (_FakeReporter(error=ProviderError(
                code=ProviderErrorCode.UNAVAILABLE, message="down",
                retryable=True, provider="llm_gateway")), None, 502),
            (_FakeReporter(), InvalidContextSearchRequest("invalid context"), 400),
            (_FakeReporter(), ContextSearchBudgetExceeded("budget"), 504),
            (_FakeReporter(), ContextSearchFailed(
                ContextSearchErrorType.LLM_ERROR, "planner failed"), 502),
        )
        for reporter, context_error, expected in cases:
            with self.subTest(expected=expected, error=type(context_error).__name__):
                client, project_id, _ = _http(
                    report_service=reporter, context_error=context_error
                )
                self.assertEqual(self._post(client, project_id).status_code, expected)

if __name__ == "__main__":
    unittest.main()
