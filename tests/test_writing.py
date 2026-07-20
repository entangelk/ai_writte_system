"""Phase 5.1 Writing generation regressions (v1.6.68).

Locks the generation-only slice: prompt assembly carries the instruction, draft
excerpt, do_not_use/constraints (hard priority) and candidate labels; the plain
prose response is wrapped into a WritingCandidate (status always "candidate");
deterministic safety (project isolation / task-type / instruction) rejects bad
requests; and a provider fault is not swallowed. Guards run both directions. See
docs/plans/05-writing-generation-decisions.md.
"""

import asyncio
import unittest
from dataclasses import replace

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
from services.application.app.main import create_app
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
    RiskNote,
    RiskNoteType,
    RiskSeverity,
    WritingCandidate,
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
from services.application.app.writing.report import InvalidCandidateReport
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.provider import GenerationResult, TokenUsage


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
        self._app = app

    def post(self, path, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.post(path, **kwargs)

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
          reporter=None, report_service=None, core_service=None):
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
            "generated_by_model",
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
