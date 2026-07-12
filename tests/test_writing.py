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
    WritingBrief,
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


def _service(provider):
    templates = PromptTemplateService(InMemoryPromptTemplateRepository())
    seed_writing_template(templates)
    return WritingService(provider, prompt_templates=templates)


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

    def test_build_request_includes_brief_when_present(self):
        templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        template = seed_writing_template(templates)
        chat = build_writing_request(
            request=_request(),
            package=_package(),
            prompt_template=template,
            brief=WritingBrief(project_id="p1", tone=("불길함",),
                               forbidden_patterns=("운명처럼",)),
        )
        self.assertIn("Tone: 불길함", chat.messages[1].content)
        self.assertIn("Avoid: 운명처럼", chat.messages[1].content)


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

    def test_cross_project_brief_rejected(self):
        provider = _FakeProvider()
        with self.assertRaises(WritingError):
            _run(_service(provider).generate(
                request=_request(project_id="p1"), package=_package("p1"),
                brief=WritingBrief(project_id="p2"),
            ))

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


def _http(provider=None, *, package=None, with_context=True, context_error=None):
    core_sot = CoreSotService(InMemoryCoreSotRepository())
    writing_service = _service(provider) if provider is not None else None
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


if __name__ == "__main__":
    unittest.main()
