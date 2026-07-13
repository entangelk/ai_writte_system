"""Phase 5.6 exact-evidence partial revise regressions."""

import asyncio
import unittest

import httpx

from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository,
    PromptTemplateService,
)
from services.application.app.context_search.models import (
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
from services.application.app.main import create_app
from services.application.app.writing.models import (
    CandidateClaim,
    CandidateClaimType,
    WritingCandidate,
    WritingGateDecision,
    WritingGateFinding,
    WritingGateFindingType,
    WritingGateSeverity,
    WritingOutputType,
    WritingTaskType,
)
from services.application.app.writing.revise import (
    InvalidWritingRevision,
    WritingRevisionError,
    WritingRevisionService,
    seed_writing_revise_template,
)
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.provider import GenerationResult, TokenUsage


def _package(project_id="p1"):
    return ContextPackage(
        project_id, ContextSearchPurpose.WRITING_CONTEXT, (), (), (), (), 0, False
    )


def _candidate(text="앞 문장. 잘못된 문장. 뒤 문장.", project_id="p1"):
    return WritingCandidate(
        "r1", project_id, WritingTaskType.CONTINUE_SCENE,
        WritingOutputType.DRAFT_PATCH, text,
        candidate_claims=(CandidateClaim(
            "stale", CandidateClaimType.INTERPRETATION, True
        ),),
    )


def _finding(evidence="잘못된 문장.", *, finding_type=WritingGateFindingType.CONTINUITY,
             decision=WritingGateDecision.REVISE):
    return WritingGateFinding(
        finding_type, WritingGateSeverity.WARNING, "연속성 수정", evidence, decision
    )


class _Provider:
    def __init__(self, content="고친 문장.", *, error=None):
        self.content = content
        self.error = error
        self.calls = 0
        self.last_request = None

    async def generate(self, request):
        self.calls += 1
        self.last_request = request
        if self.error:
            raise self.error
        return GenerationResult("fake-reviser", self.content, "stop", TokenUsage(1, 1))


def _service(provider):
    templates = PromptTemplateService(InMemoryPromptTemplateRepository())
    seed_writing_revise_template(templates)
    return WritingRevisionService(provider, prompt_templates=templates)


class WritingRevisionServiceTest(unittest.TestCase):
    def test_replaces_only_unique_evidence_and_clears_stale_report(self):
        provider = _Provider()
        revised = asyncio.run(_service(provider).revise(
            candidate=_candidate(), finding=_finding(), instruction="고쳐줘",
            package=_package(),
        ))
        self.assertEqual(revised.text, "앞 문장. 고친 문장. 뒤 문장.")
        self.assertEqual(revised.candidate_claims, ())
        self.assertIsNone(revised.candidate_id)
        self.assertEqual(revised.generated_by_model, "fake-reviser")
        self.assertEqual(provider.calls, 1)
        self.assertIn("replacement prose fragment", provider.last_request.messages[0].content)

    def test_missing_or_duplicate_anchor_rejected_before_provider(self):
        for text in ("anchor 없음", "잘못된 문장. 그리고 잘못된 문장."):
            provider = _Provider()
            with self.subTest(text=text), self.assertRaises(WritingRevisionError):
                asyncio.run(_service(provider).revise(
                    candidate=_candidate(text), finding=_finding(),
                    instruction="고쳐줘", package=_package(),
                ))
            self.assertEqual(provider.calls, 0)

    def test_non_revise_or_non_continuity_rejected_before_provider(self):
        cases = (
            _finding(finding_type=WritingGateFindingType.POV,
                     decision=WritingGateDecision.BLOCK),
            _finding(decision=WritingGateDecision.RETRIEVE_MORE),
        )
        for finding in cases:
            provider = _Provider()
            with self.subTest(finding=finding), self.assertRaises(WritingRevisionError):
                asyncio.run(_service(provider).revise(
                    candidate=_candidate(), finding=finding,
                    instruction="고쳐줘", package=_package(),
                ))
            self.assertEqual(provider.calls, 0)

    def test_empty_and_unchanged_replacement_are_invalid_provider_results(self):
        for content in ("   ", "잘못된 문장."):
            with self.subTest(content=content), self.assertRaises(InvalidWritingRevision):
                asyncio.run(_service(_Provider(content)).revise(
                    candidate=_candidate(), finding=_finding(),
                    instruction="고쳐줘", package=_package(),
                ))

    def test_markdown_fence_is_unwrapped_by_application(self):
        revised = asyncio.run(_service(_Provider("```text\n고친 문장.\n```" )).revise(
            candidate=_candidate(), finding=_finding(), instruction="고쳐줘",
            package=_package(),
        ))
        self.assertEqual(revised.text, "앞 문장. 고친 문장. 뒤 문장.")

    def test_cross_project_rejected_before_provider(self):
        provider = _Provider()
        with self.assertRaises(WritingRevisionError):
            asyncio.run(_service(provider).revise(
                candidate=_candidate("잘못된 문장.", "p1"), finding=_finding(),
                instruction="고쳐줘", package=_package("p2"),
            ))
        self.assertEqual(provider.calls, 0)


class _Context:
    def __init__(self, package, *, error=None):
        self.package = package
        self.error = error
        self.last_request = None
        self.calls = 0

    async def build_context_package(self, request):
        self.calls += 1
        self.last_request = request
        if self.error:
            raise self.error
        return _package(request.project_id)


class _Client:
    def __init__(self, app):
        self.app = app

    def post(self, path, json):
        async def send():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app), base_url="http://test"
            ) as client:
                return await client.post(path, json=json)
        return asyncio.run(send())


class _NoWriteCoreSotService(CoreSotService):
    def __init__(self):
        super().__init__(InMemoryCoreSotRepository())
        self.save_calls = 0

    def save_draft(self, **kwargs):
        self.save_calls += 1
        raise AssertionError("writing/revise must not save a draft")


def _http(provider=None, *, context_error=None, core_service=None):
    core = core_service or CoreSotService(InMemoryCoreSotRepository())
    context = _Context(_package(), error=context_error)
    app = create_app(
        service=core,
        context_search_service=context,
        writing_revision_service=_service(provider) if provider else None,
    )
    client = _Client(app)
    project = client.post("/projects", {"name": "Novel"}).json()["id"]
    return client, project, context


def _body(**overrides):
    body = {
        "request_id": "r1", "instruction": "연속성을 고쳐줘",
        "candidate_text": "앞 문장. 잘못된 문장. 뒤 문장.",
        "finding": {"type": "continuity", "severity": "warning",
                    "message": "연속성 수정", "evidence": "잘못된 문장.",
                    "recommended_decision": "revise"},
    }
    body.update(overrides)
    return body


class WritingRevisionApiTest(unittest.TestCase):
    def test_http_revises_inline_candidate_with_server_context(self):
        client, project, context = _http(_Provider())
        response = client.post(f"/projects/{project}/writing/revise", _body(
            query="명시 검색", current_position={
                "draft_id": "d1", "version_id": "v1"
            }))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "앞 문장. 고친 문장. 뒤 문장.")
        self.assertIsNone(response.json()["candidate_id"])
        self.assertEqual(context.last_request.query, "명시 검색")
        self.assertEqual(context.last_request.current_position.version_id, "v1")

    def test_http_validation_and_unchanged_mapping(self):
        client, project, _ = _http(_Provider())
        duplicate = _body(candidate_text="잘못된 문장. 잘못된 문장.")
        self.assertEqual(client.post(
            f"/projects/{project}/writing/revise", duplicate).status_code, 400)

        client, project, _ = _http(_Provider("잘못된 문장."))
        self.assertEqual(client.post(
            f"/projects/{project}/writing/revise", _body()).status_code, 502)

    def test_http_empty_inputs_rejected_before_context_search(self):
        cases = (
            {"instruction": "   "},
            {"request_id": "   "},
            {"candidate_text": "   "},
            {"finding": {"type": "continuity", "severity": "warning",
                         "message": "연속성 수정", "evidence": "   ",
                         "recommended_decision": "revise"}},
        )
        for override in cases:
            provider = _Provider()
            client, project, context = _http(provider)
            with self.subTest(override=override):
                response = client.post(
                    f"/projects/{project}/writing/revise", _body(**override)
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(context.calls, 0)
                self.assertEqual(provider.calls, 0)

    def test_http_context_failures_keep_public_mapping(self):
        cases = (
            (ContextSearchBudgetExceeded("budget"), 504),
            (ContextSearchFailed(
                ContextSearchErrorType.LLM_ERROR, "planner failed"), 502),
        )
        for error, expected in cases:
            client, project, _ = _http(_Provider(), context_error=error)
            with self.subTest(error=type(error).__name__):
                self.assertEqual(client.post(
                    f"/projects/{project}/writing/revise", _body()).status_code,
                    expected)

    def test_http_does_not_save_draft(self):
        core = _NoWriteCoreSotService()
        client, project, _ = _http(_Provider(), core_service=core)
        response = client.post(f"/projects/{project}/writing/revise", _body())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(core.save_calls, 0)

    def test_http_provider_timeout_and_unavailable_mapping(self):
        for code, expected in ((ProviderErrorCode.TIMEOUT, 504),
                               (ProviderErrorCode.UNAVAILABLE, 502)):
            provider = _Provider(error=ProviderError(
                code=code, message="provider failed", retryable=True,
                provider="llm_gateway"))
            client, project, _ = _http(provider)
            with self.subTest(code=code):
                self.assertEqual(client.post(
                    f"/projects/{project}/writing/revise", _body()).status_code,
                    expected)

    def test_http_missing_service_and_project(self):
        client, project, _ = _http()
        self.assertEqual(client.post(
            f"/projects/{project}/writing/revise", _body()).status_code, 503)
        self.assertEqual(client.post(
            "/projects/ghost/writing/revise", _body()).status_code, 404)


if __name__ == "__main__":
    unittest.main()
