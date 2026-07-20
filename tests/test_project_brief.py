"""Writing Workspace V2 W2 ProjectBrief contract regressions (PB/SC)."""

import asyncio
import json
import os
import unittest
from unittest.mock import patch
from pathlib import Path

import httpx

from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
    StaleProjectBriefBase,
)
from services.application.app.core_sot.repository import (
    DuplicateProjectBriefRequest,
)
from services.application.app.main import create_app
from services.application.app.context_search.models import (
    ContextBudget,
    ContextNeed,
    ContextSearchPurpose,
    ContextSearchRequest,
    SearchPlan,
)
from services.application.app.context_search.service import ContextSearchService
from services.application.app.indexing.service import (
    DeterministicFakeEmbeddingProvider,
    InMemoryVectorIndexAdapter,
    SourceBlockIndexingService,
)
from services.application.app.writing.prompt import format_context_package


class _Client:
    def __init__(self, app):
        self._app = app

    def request(self, method: str, path: str, **kwargs):
        async def send():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self._app),
                base_url="http://test",
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    def get(self, path: str):
        return self.request("GET", path)

    def post(self, path: str, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs):
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str):
        return self.request("DELETE", path)


def _brief_body(**overrides):
    body = {
        "base_version_id": None,
        "idempotency_key": "brief-1",
        "premise": "A winter mystery",
        "genre": "Mystery",
        "tone": "Quiet",
        "pov": "Third person",
        "constraints": ["No time travel"],
        "style_rules": ["Use restrained sensory detail"],
        "preferred_patterns": ["Short sentence after a reveal"],
        "forbidden_patterns": ["As fate would have it"],
        "style_examples": ["Snow gathered silently along the sill."],
    }
    body.update(overrides)
    return body


class _EmptyPlanner:
    def build_plan(self, request):
        return SearchPlan(plan_id="plan-brief", project_id=request.project_id, steps=())


def _context_service(core: CoreSotService) -> ContextSearchService:
    vector = InMemoryVectorIndexAdapter()
    embeddings = DeterministicFakeEmbeddingProvider()
    return ContextSearchService(
        core_sot=core,
        indexing_service=SourceBlockIndexingService(
            core_sot=core, embeddings=embeddings, vector_index=vector
        ),
        vector_search=vector,
        embeddings=embeddings,
        planner=_EmptyPlanner(),
    )


def _context_request(project_id: str) -> ContextSearchRequest:
    return ContextSearchRequest(
        project_id=project_id,
        purpose=ContextSearchPurpose.WRITING_CONTEXT,
        needs=(ContextNeed.CANONICAL_MEMORY,),
        query="continue",
        current_position=None,
        context_budget=ContextBudget(max_tokens=1000),
    )


class ProjectBriefContractTest(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryCoreSotRepository()
        self.service = CoreSotService(self.repo)
        self.project = self.service.create_project(name="Novel")

    def _put(self, **overrides):
        body = _brief_body(**overrides)
        for field in (
            "constraints", "style_rules", "preferred_patterns",
            "forbidden_patterns", "style_examples",
        ):
            body[field] = tuple(body[field])
        return self.service.put_project_brief(
            project_id=self.project.id,
            **body,
        )

    def test_first_put_creates_version_one(self):
        result = self._put()
        self.assertEqual(result.brief.version_number, 1)
        self.assertFalse(result.idempotent_replay)

    def test_current_base_creates_next_version(self):
        first = self._put()
        second = self._put(
            base_version_id=first.brief.id,
            idempotency_key="brief-2",
            premise="Changed",
        )
        self.assertEqual(second.brief.version_number, 2)
        self.assertEqual(first.brief.premise, "A winter mystery")

    def test_same_key_replays_original_version(self):
        first = self._put()
        replay = self._put(
            premise="must not replace",
            style_examples=["must not replace style examples"],
        )
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.brief, first.brief)
        self.assertEqual(len(self.repo.project_brief_versions), 1)

    def test_different_key_creates_distinct_version(self):
        first = self._put()
        second = self._put(
            base_version_id=first.brief.id, idempotency_key="brief-2"
        )
        self.assertNotEqual(first.brief.id, second.brief.id)

    def test_empty_version_clears_current_and_preserves_history(self):
        first = self._put()
        cleared = self._put(
            base_version_id=first.brief.id,
            idempotency_key="brief-clear",
            premise=None,
            genre=None,
            tone=None,
            pov=None,
            constraints=[],
            style_rules=[],
            preferred_patterns=[],
            forbidden_patterns=[],
            style_examples=[],
        )
        self.assertEqual(cleared.brief.version_number, 2)
        self.assertIsNone(cleared.brief.premise)
        self.assertEqual(
            self.service.list_project_brief_versions(project_id=self.project.id),
            (first.brief, cleared.brief),
        )

    def test_concurrent_different_key_collision_becomes_stale_not_replay(self):
        class CollidingRepository(InMemoryCoreSotRepository):
            def record_project_brief(self, brief):
                raise DuplicateProjectBriefRequest(brief.idempotency_key)

        service = CoreSotService(CollidingRepository())
        project = service.create_project(name="Novel")

        with self.assertRaises(StaleProjectBriefBase):
            service.put_project_brief(
                project_id=project.id,
                base_version_id=None,
                idempotency_key="different-key",
                premise="Premise",
                genre=None,
                tone=None,
                pov=None,
                constraints=(),
                style_rules=(),
                preferred_patterns=(),
                forbidden_patterns=(),
                style_examples=(),
            )


class ProjectBriefApiTest(unittest.TestCase):
    def setUp(self):
        self.service = CoreSotService(InMemoryCoreSotRepository())
        self.client = _Client(create_app(self.service))
        self.project = self.client.post("/projects", json={"name": "Novel"}).json()

    @property
    def path(self):
        return f"/projects/{self.project['id']}/brief"

    def test_existing_project_without_brief_returns_null(self):
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"brief": None})

    def test_stale_base_rejected_without_write(self):
        first = self.client.put(self.path, json=_brief_body()).json()["brief"]
        before = self.client.get(f"{self.path}/versions").json()
        stale = self.client.put(
            self.path,
            json=_brief_body(idempotency_key="brief-2", base_version_id=None),
        )
        wrong = self.client.put(
            self.path,
            json=_brief_body(idempotency_key="brief-3", base_version_id="wrong"),
        )
        self.assertEqual((stale.status_code, wrong.status_code), (409, 409))
        self.assertEqual(self.client.get(f"{self.path}/versions").json(), before)
        self.assertEqual(before["versions"][0]["id"], first["id"])

    def test_put_normalizes_and_returns_exact_envelope(self):
        response = self.client.put(
            self.path,
            json=_brief_body(
                premise="  Premise  ",
                genre=None,
                tone="  Quiet ",
                pov=None,
                constraints=["  Rule one ", "Rule two  "],
                style_rules=["  Restrained  "],
                preferred_patterns=["  Short ending "],
                forbidden_patterns=["  Fate  "],
                style_examples=["  Snow fell.  "],
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"brief", "idempotent_replay"})
        brief = response.json()["brief"]
        self.assertEqual(
            set(brief),
            {
                "id", "project_id", "version_number", "premise", "genre",
                "tone", "pov", "constraints", "style_rules",
                "preferred_patterns", "forbidden_patterns", "style_examples",
            },
        )
        self.assertEqual(brief["premise"], "Premise")
        self.assertEqual(brief["constraints"], ["Rule one", "Rule two"])
        self.assertEqual(brief["style_examples"], ["Snow fell."])

    def test_invalid_content_rejected_without_write(self):
        invalid = [
            _brief_body(premise="  "),
            _brief_body(constraints=["ok", "  "]),
            _brief_body(constraints=["same", " same "]),
            _brief_body(style_rules=["same", " same "]),
            _brief_body(preferred_patterns=["ok", "  "]),
            _brief_body(forbidden_patterns=["same", " same "]),
            _brief_body(style_examples=["same", " same "]),
            _brief_body(style_examples=["a", "b", "c", "d"]),
            _brief_body(style_examples=["x" * 1001]),
            {**_brief_body(), "unknown": True},
            {key: value for key, value in _brief_body().items() if key != "tone"},
            *(
                {key: value for key, value in _brief_body().items() if key != field}
                for field in (
                    "style_rules", "preferred_patterns",
                    "forbidden_patterns", "style_examples",
                )
            ),
        ]
        for body in invalid:
            with self.subTest(body=body):
                self.assertEqual(self.client.put(self.path, json=body).status_code, 422)
                self.assertEqual(self.client.get(f"{self.path}/versions").json(), {"versions": []})

    def test_style_example_limits_are_environment_adjustable_both_directions(self):
        with patch.dict(
            os.environ,
            {
                "PROJECT_BRIEF_STYLE_EXAMPLES_MAX_ITEMS": "4",
                "PROJECT_BRIEF_STYLE_EXAMPLE_MAX_CHARS": "1001",
            },
        ):
            accepted = self.client.put(
                self.path,
                json=_brief_body(
                    style_examples=["a", "b", "c", "x" * 1001]
                ),
            )
        self.assertEqual(accepted.status_code, 200)

    def test_lowered_style_example_limits_do_not_break_existing_reads(self):
        created = self.client.put(
            self.path,
            json=_brief_body(style_examples=["one", "two", "three"]),
        ).json()["brief"]

        with patch.dict(
            os.environ,
            {
                "PROJECT_BRIEF_STYLE_EXAMPLES_MAX_ITEMS": "1",
                "PROJECT_BRIEF_STYLE_EXAMPLE_MAX_CHARS": "1",
            },
        ):
            current = self.client.get(self.path)
            history = self.client.get(f"{self.path}/versions")
            detail = self.client.get(f"{self.path}/versions/{created['id']}")

        self.assertEqual(
            (current.status_code, history.status_code, detail.status_code),
            (200, 200, 200),
        )
        self.assertEqual(current.json()["brief"]["style_examples"], ["one", "two", "three"])
        self.assertEqual(history.json()["versions"][0]["style_examples"], ["one", "two", "three"])
        self.assertEqual(detail.json()["brief"]["style_examples"], ["one", "two", "three"])

    def test_invalid_style_example_limits_fail_app_creation(self):
        invalid = (
            ("PROJECT_BRIEF_STYLE_EXAMPLES_MAX_ITEMS", "0"),
            ("PROJECT_BRIEF_STYLE_EXAMPLE_MAX_CHARS", "0"),
            ("PROJECT_BRIEF_STYLE_EXAMPLES_MAX_ITEMS", "not-an-integer"),
            ("PROJECT_BRIEF_STYLE_EXAMPLE_MAX_CHARS", "not-an-integer"),
        )
        for name, value in invalid:
            with self.subTest(name=name, value=value), patch.dict(
                os.environ,
                {
                    "PROJECT_BRIEF_STYLE_EXAMPLES_MAX_ITEMS": "3",
                    "PROJECT_BRIEF_STYLE_EXAMPLE_MAX_CHARS": "1000",
                    name: value,
                },
            ):
                with self.assertRaises(ValueError):
                    create_app()

    def test_version_read_is_project_isolated(self):
        version = self.client.put(self.path, json=_brief_body()).json()["brief"]
        other = self.client.post("/projects", json={"name": "Other"}).json()
        response = self.client.get(
            f"/projects/{other['id']}/brief/versions/{version['id']}"
        )
        self.assertEqual(response.status_code, 404)

    def test_archived_project_blocks_write_but_allows_read(self):
        first = self.client.put(self.path, json=_brief_body()).json()["brief"]
        self.client.delete(f"/projects/{self.project['id']}")
        blocked = self.client.put(
            self.path,
            json=_brief_body(
                base_version_id=first["id"], idempotency_key="brief-2"
            ),
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(self.client.get(self.path).json()["brief"], first)
        self.assertEqual(self.client.get(f"{self.path}/versions").json()["versions"], [first])

    def test_current_brief_read_is_project_isolated(self):
        self.assertEqual(self.client.get("/projects/missing/brief").status_code, 404)
        other = self.client.post("/projects", json={"name": "Other"}).json()
        self.client.put(self.path, json=_brief_body())
        self.assertEqual(
            self.client.get(f"/projects/{other['id']}/brief").json(),
            {"brief": None},
        )


class WorkspaceW0SchemaIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.openapi = create_app().openapi()
        self.catalog = json.loads(
            Path("schemas/writing-workspace-v2-w0.schema.json").read_text(
                encoding="utf-8"
            )
        )["$defs"]

    def test_openapi_components_match_w0_fragments(self):
        schemas = self.openapi["components"]["schemas"]
        expected_keys = set(self.catalog["projectBriefVersion"]["required"])
        self.assertEqual(
            set(schemas["ProjectBriefVersionPayload"]["required"]), expected_keys
        )
        self.assertEqual(
            set(schemas["PutProjectBriefRequest"]["required"]),
            set(self.catalog["projectBriefPutRequest"]["required"]),
        )
        self.assertFalse(schemas["ProjectBriefVersionPayload"]["additionalProperties"])
        self.assertFalse(schemas["PutProjectBriefRequest"]["additionalProperties"])
        self.assertTrue(
            schemas["ProjectBriefVersionPayload"]["properties"]["constraints"][
                "uniqueItems"
            ]
        )
        self.assertEqual(
            schemas["ProjectBriefVersionPayload"]["properties"]["id"]["pattern"],
            r"\S",
        )
        self.assertEqual(
            schemas["PutProjectBriefRequest"]["properties"]["idempotency_key"][
                "pattern"
            ],
            r"\S",
        )
        self.assertTrue(
            schemas["PutProjectBriefRequest"]["properties"]["constraints"][
                "uniqueItems"
            ]
        )
        for field in (
            "style_rules", "preferred_patterns", "forbidden_patterns",
            "style_examples",
        ):
            self.assertTrue(
                schemas["ProjectBriefVersionPayload"]["properties"][field][
                    "uniqueItems"
                ]
            )
            self.assertTrue(
                schemas["PutProjectBriefRequest"]["properties"][field][
                    "uniqueItems"
                ]
            )
        # --- W3 ordered unit + Writing intent fragments (SC-01 final closure) ---
        self.assertEqual(
            set(schemas["DraftPayload"]["required"]),
            set(self.catalog["draftV2"]["required"]),
        )
        self.assertEqual(
            set(schemas["DraftOrderPutRequest"]["required"]),
            set(self.catalog["draftOrderPutRequest"]["required"]),
        )
        self.assertTrue(
            schemas["DraftOrderPutRequest"]["properties"]["ordered_draft_ids"][
                "uniqueItems"
            ]
        )
        self.assertEqual(
            set(schemas["DraftOrderPutResponse"]["required"]),
            set(self.catalog["draftOrderPutResponse"]["required"]),
        )
        self.assertEqual(
            schemas["UnitKind"]["enum"], self.catalog["unitKind"]["enum"]
        )
        self.assertEqual(
            schemas["WritingIntent"]["enum"], self.catalog["writingIntent"]["enum"]
        )
        self.assertEqual(
            set(schemas["NextUnitBody"]["required"]),
            set(self.catalog["nextUnitSpec"]["required"]),  # goal is a required key
        )
        self.assertFalse(schemas["NextUnitBody"]["additionalProperties"])
        self.assertEqual(
            set(schemas["AcceptedSavePayload"]["required"]),
            set(self.catalog["savedWritingTarget"]["required"]),
        )
        self.assertEqual(
            set(schemas["WritingAcceptResponse"]["required"]),
            set(self.catalog["writingAcceptResponseV2"]["required"]),
        )
        self.assertEqual(
            set(schemas["WritingAcceptAnalysisPartial"]["required"]),
            set(self.catalog["writingAcceptAnalysisPartialV2"]["required"]),
        )

        paths = self.openapi["paths"]
        self.assertIn("put", paths["/projects/{project_id}/brief"])
        self.assertIn("get", paths["/projects/{project_id}/brief/versions"])
        self.assertIn("put", paths["/projects/{project_id}/draft-order"])
        self.assertIn("post", paths["/projects/{project_id}/writing/accept"])

    def test_endpoints_do_not_reference_catalog_root(self):
        encoded = json.dumps(
            self.openapi["paths"]["/projects/{project_id}/brief"], sort_keys=True
        )
        self.assertNotIn("writing-workspace-v2-w0.schema.json", encoded)
        self.assertIn("PutProjectBriefRequest", encoded)
        self.assertIn("ProjectBriefPutResponse", encoded)
        # W3 endpoints reference their named components, never the catalog root.
        reorder = json.dumps(
            self.openapi["paths"]["/projects/{project_id}/draft-order"],
            sort_keys=True,
        )
        self.assertNotIn("writing-workspace-v2-w0.schema.json", reorder)
        self.assertIn("DraftOrderPutRequest", reorder)
        self.assertIn("DraftOrderPutResponse", reorder)
        accept = json.dumps(
            self.openapi["paths"]["/projects/{project_id}/writing/accept"],
            sort_keys=True,
        )
        self.assertNotIn("writing-workspace-v2-w0.schema.json", accept)
        self.assertIn("WritingAcceptRequest", accept)
        self.assertIn("WritingAcceptResponse", accept)


class ProjectBriefWritingContextTest(unittest.TestCase):
    def test_current_brief_is_a_separate_authoritative_context_item(self):
        repo = InMemoryCoreSotRepository()
        core = CoreSotService(repo)
        project = core.create_project(name="Novel")
        core.put_project_brief(
            project_id=project.id,
            base_version_id=None,
            idempotency_key="brief-1",
            premise="A hidden key changes hands.",
            genre="Mystery",
            tone=None,
            pov="Close third",
            constraints=("Do not reveal the traitor.",),
            style_rules=("Keep description restrained.",),
            preferred_patterns=("End reveals with a short sentence.",),
            forbidden_patterns=("As fate would have it",),
            style_examples=("Snow gathered silently along the sill.",),
        )
        package = asyncio.run(
            _context_service(core).build_context_package(_context_request(project.id))
        )

        self.assertIsNotNone(package.project_brief)
        self.assertEqual(package.macro_items, ())
        self.assertEqual(package.micro_evidence, ())
        rendered = format_context_package(package)
        self.assertIn('<project_brief authority="canonical" version="1">', rendered)
        self.assertIn("- premise: A hidden key changes hands.", rendered)
        self.assertIn("- constraint: Do not reveal the traitor.", rendered)
        self.assertIn("- style rule: Keep description restrained.", rendered)
        self.assertIn("- prefer: End reveals with a short sentence.", rendered)
        self.assertIn("- avoid: As fate would have it", rendered)
        self.assertIn("- style example: Snow gathered silently along the sill.", rendered)

    def test_missing_brief_does_not_invent_an_authoritative_item(self):
        from services.application.app.context_search.models import ContextPackage

        package = ContextPackage(
            project_id="p1",
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            macro_items=(),
            micro_evidence=(),
            constraints=(),
            do_not_use=(),
            token_estimate_total=0,
            degraded=False,
        )
        self.assertNotIn("<project_brief", format_context_package(package))

    def test_existing_project_without_brief_builds_package_with_none(self):
        core = CoreSotService(InMemoryCoreSotRepository())
        project = core.create_project(name="No brief yet")

        package = asyncio.run(
            _context_service(core).build_context_package(_context_request(project.id))
        )

        self.assertIsNone(package.project_brief)
        self.assertNotIn("<project_brief", format_context_package(package))


if __name__ == "__main__":
    unittest.main()
