"""Stable context pointer contract for Writing candidate claims.

Brief: docs/plans/05-writing-stable-context-pointer-decisions.md —
D1=A (projection of the existing IndexPointer), D2=A (the report extractor is the
only turn that can cite package items, validated against the current package),
D3=A (required claim array, empty allowed), sub-decision P-i (per-origin field
invariant: a store fills only the fields it has).

**K-6=R-e (2026-07-30)**: the extractor no longer copies pointer JSON. Items are
numbered in the prompt, a claim cites the number, and the number→pointer mapping
happens on the server. The pointer *domain* contract above is unchanged — what
changed is the wire the model writes, so the membership check became "is this
number one of the items this request showed" and the ordering
(``package_pointers`` == prompt numbering, macro then micro) became load-bearing.
"""

import asyncio
import json
import re
import unittest

from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository, PromptTemplate, PromptTemplateService,
)
from services.application.app.context_search.models import (
    ContextItem, ContextItemStatus, ContextNeed, ContextPackage,
    ContextSearchPurpose,
)
from services.application.app.indexing.models import IndexPointer
from services.application.app.writing.accept import _candidate_report_payload
from services.application.app.writing.context_pointer import (
    InvalidContextPointer, context_pointer_of, package_pointers, pointer_wire,
)
from services.application.app.writing.gate_prompt import build_writing_gate_request
from services.application.app.writing.models import (
    CandidateClaim, CandidateClaimType, ContextPointer, WritingCandidate,
    WritingGateDecision, WritingGateFinding, WritingGateFindingType,
    WritingGateSeverity, WritingOutputType, WritingRequest, WritingTaskType,
)
from services.application.app.writing.prompt import format_context_package
from services.application.app.writing.report import (
    InvalidCandidateReport, WritingCandidateReportService, parse_report,
    seed_report_template,
)
from services.application.app.writing.revise import (
    WritingRevisionService, seed_writing_revise_template,
)
from services.application.app.writing.service import (
    WritingService, seed_writing_template,
)
from services.llm_gateway.app.provider import GenerationResult, TokenUsage


# The three real origins, with the field invariant each one actually satisfies
# (context_search/service.py _item_from_block/_item_from_memory/
# _item_from_candidate). memory has no snapshot ⇒ no content_hash; a candidate
# has no version either.
_BLOCK = IndexPointer("p1", "source_blocks", "b1", "ver1", "hash1")
_MEMORY = IndexPointer("p1", "memory_entries", "m1", "3", "")
_CANDIDATE = IndexPointer("p1", "analysis_candidates", "c1", "", "")


def _item(pointer, *, text="문이 열렸다", status=None):
    if status is None:
        status = (ContextItemStatus.CANDIDATE
                  if pointer.collection == "analysis_candidates"
                  else ContextItemStatus.CANONICAL)
    return ContextItem(
        need=ContextNeed.CURRENT_SCENE, status=status, text=text,
        pointer=pointer, snapshot_id="s1", sot_reloaded=True, token_estimate=1,
    )


def _package(*pointers, project_id="p1", macro=()):
    return ContextPackage(
        project_id=project_id, purpose=ContextSearchPurpose.WRITING_CONTEXT,
        macro_items=tuple(_item(p) for p in macro),
        micro_evidence=tuple(_item(p) for p in pointers),
        constraints=(), do_not_use=(), token_estimate_total=0, degraded=False,
    )


def _candidate(project_id="p1"):
    return WritingCandidate("wr1", project_id, WritingTaskType.CONTINUE_SCENE,
                            WritingOutputType.DRAFT_PATCH, "아린은 문을 열었다.")


def _claim_json(cited, *, text="문이 열렸다"):
    # ``cited`` = the item numbers the model wrote (K-6=R-e wire).
    return {"text": text, "type": "narrative_event", "requires_gate_check": True,
            "related_context_pointers": list(cited)}


def _report_json(claims):
    return json.dumps({"self_reported_constraints": [], "candidate_claims": claims,
                       "new_memory_hints": [], "risk_notes": []},
                      ensure_ascii=False)


class _Provider:
    def __init__(self, outputs):
        self.outputs, self.calls, self.requests = list(outputs), 0, []

    async def generate(self, request):
        self.calls += 1
        self.requests.append(request)
        return GenerationResult("fake", self.outputs.pop(0), "stop", TokenUsage(1, 1))


def _service(provider):
    templates = PromptTemplateService(InMemoryPromptTemplateRepository())
    seed_report_template(templates)
    return WritingCandidateReportService(provider, prompt_templates=templates)


class ContextPointerProjectionTest(unittest.TestCase):
    """P-i: empty is allowed exactly where the store has no such field."""

    def test_each_origin_projects_its_real_pointer(self):
        # under-strict: all three origins are pointable, project_id dropped
        # (D1=A) and every other field preserved verbatim.
        self.assertEqual(
            context_pointer_of(_BLOCK, project_id="p1"),
            ContextPointer("source_blocks", "b1", "ver1", "hash1"))
        self.assertEqual(
            context_pointer_of(_MEMORY, project_id="p1"),
            ContextPointer("memory_entries", "m1", "3", ""))
        self.assertEqual(
            context_pointer_of(_CANDIDATE, project_id="p1"),
            ContextPointer("analysis_candidates", "c1", "", ""))

    def test_source_block_missing_version_or_hash_fails_closed(self):
        # over-strict: a source block HAS a snapshot version/hash, so an empty
        # one is a real defect — not an origin without the field.
        for field, pointer in (
            ("version_id", IndexPointer("p1", "source_blocks", "b1", "", "hash1")),
            ("content_hash", IndexPointer("p1", "source_blocks", "b1", "ver1", "")),
            ("document_id", IndexPointer("p1", "source_blocks", "", "ver1", "hash1")),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(
                    InvalidContextPointer, f"non-empty {field}"):
                context_pointer_of(pointer, project_id="p1")

    def test_absent_fields_must_stay_empty(self):
        # over-strict: the store has no content_hash for a memory and no version
        # for a candidate, so a filled one means the projection invented
        # identity (P-iv, the rejected option) — refuse it.
        for name, pointer in (
            ("memory hash", IndexPointer("p1", "memory_entries", "m1", "3", "h")),
            ("candidate version", IndexPointer("p1", "analysis_candidates", "c1", "v", "")),
            ("candidate hash", IndexPointer("p1", "analysis_candidates", "c1", "", "h")),
        ):
            with self.subTest(name=name), self.assertRaisesRegex(
                    InvalidContextPointer, "must leave"):
                context_pointer_of(pointer, project_id="p1")

    def test_memory_requires_document_id_and_version(self):
        for field, pointer in (
            ("document_id", IndexPointer("p1", "memory_entries", "", "3", "")),
            ("version_id", IndexPointer("p1", "memory_entries", "m1", "", "")),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(
                    InvalidContextPointer, f"non-empty {field}"):
                context_pointer_of(pointer, project_id="p1")

    def test_unknown_collection_is_not_pointable(self):
        with self.assertRaisesRegex(InvalidContextPointer, "not a pointable"):
            context_pointer_of(
                IndexPointer("p1", "memory_vectors", "x", "1", "h"), project_id="p1")

    def test_cross_project_item_is_rejected(self):
        # contract 2: the project comes from the trusted context, and an item
        # pointing elsewhere never reaches the model.
        with self.assertRaisesRegex(InvalidContextPointer, "belongs to project"):
            context_pointer_of(
                IndexPointer("other", "source_blocks", "b1", "ver1", "hash1"),
                project_id="p1")

    def test_allowlist_covers_macro_and_micro_items(self):
        allowed = package_pointers(_package(_MEMORY, macro=(_BLOCK,)))
        self.assertEqual(allowed, (
            ContextPointer("source_blocks", "b1", "ver1", "hash1"),
            ContextPointer("memory_entries", "m1", "3", ""),
        ))


class ReportPointerParseTest(unittest.TestCase):
    """D2=A membership (now by item number, K-6=R-e) + D3=A required array."""

    def setUp(self):
        self.allowed = package_pointers(_package(_BLOCK, _MEMORY, _CANDIDATE))

    def test_each_number_maps_to_its_own_package_item(self):
        # under-strict: the number the prompt showed comes back as *that* item's
        # pointer. This is the whole of R-e — a mapping off by one, reversed, or
        # keyed to the wrong list would still produce a valid-looking report, so
        # the position of every origin is pinned, not just one sample.
        for number, pointer in enumerate(self.allowed, start=1):
            with self.subTest(number=number, collection=pointer.collection):
                report = parse_report(
                    _report_json([_claim_json([number])]),
                    allowed_pointers=self.allowed)
                self.assertEqual(
                    report["candidate_claims"][0].related_context_pointers,
                    (pointer,))

    def test_rendered_number_resolves_to_the_item_it_labels(self):
        # H1 (독립 검증 2026-07-30): 위 셀은 allowlist만 보므로 **프롬프트의 번호 부여**가
        # 갈라지는 것을 혼자서는 보지 못한다(그 방향은 service 경유 e2e 셀이 잡는다).
        # 여기서는 provider 없이 **렌더링된 프롬프트에서 번호를 읽어** 그 번호가 그 줄의
        # 항목으로 되돌아오는지 본다 — render↔parse 왕복만으로 macro/micro 순서 발산을
        # 자급자족으로 잡는 셀이다. 세 origin의 본문을 서로 다르게 두는 것이 요점이다
        # (같은 본문이면 어느 줄이 어느 항목인지 구분할 수 없다).
        expected = {
            "등대의 문이 열렸다": ContextPointer("source_blocks", "b1", "ver1", "hash1"),
            "민아는 편지를 받았다": ContextPointer("memory_entries", "m1", "3", ""),
            "비가 그쳤다": ContextPointer("analysis_candidates", "c1", "", ""),
        }
        package = ContextPackage(
            project_id="p1", purpose=ContextSearchPurpose.WRITING_CONTEXT,
            macro_items=(_item(_BLOCK, text="등대의 문이 열렸다"),),
            micro_evidence=(_item(_MEMORY, text="민아는 편지를 받았다"),
                            _item(_CANDIDATE, text="비가 그쳤다")),
            constraints=(), do_not_use=(), token_estimate_total=0, degraded=False)
        allowed = package_pointers(package)
        rendered = format_context_package(package, include_citation_numbers=True)
        labelled = re.findall(r"^- \[(\d+)\] \[[^\]]+\] (.+)$", rendered, re.MULTILINE)
        self.assertEqual(len(labelled), len(expected))
        for number, text in labelled:
            with self.subTest(number=number, text=text):
                report = parse_report(_report_json([_claim_json([int(number)])]),
                                      allowed_pointers=allowed)
                self.assertEqual(
                    report["candidate_claims"][0].related_context_pointers,
                    (expected[text],),
                    "프롬프트가 이 번호로 보여준 항목과 파서가 되돌린 항목이 다르다 — "
                    "요청은 성공하고 근거만 조용히 다른 항목에 붙는다",
                )

    def test_claim_may_cite_several_items(self):
        report = parse_report(
            _report_json([_claim_json(range(1, len(self.allowed) + 1))]),
            allowed_pointers=self.allowed)
        self.assertEqual(
            report["candidate_claims"][0].related_context_pointers, self.allowed)

    def test_claim_without_evidence_is_valid_with_empty_array(self):
        # over-strict: a new event grounded in nothing is legitimate and must
        # not be rejected for having no pointer (D3=A).
        report = parse_report(_report_json([_claim_json([])]),
                              allowed_pointers=self.allowed)
        self.assertEqual(
            report["candidate_claims"][0].related_context_pointers, ())

    def test_missing_pointer_field_is_rejected(self):
        # D3=A: required, so missing ≠ empty.
        claim = {"text": "x", "type": "narrative_event", "requires_gate_check": True}
        with self.assertRaisesRegex(ValueError, "item fields do not match schema"):
            parse_report(_report_json([claim]), allowed_pointers=self.allowed)

    def test_number_past_the_end_is_rejected(self):
        # A hallucinated citation is now an out-of-range number: the model can
        # only invent numbers, and one the request never showed fails closed.
        for number in (len(self.allowed) + 1, 99):
            with self.subTest(number=number), self.assertRaisesRegex(
                    ValueError, "not an item of this context package"):
                parse_report(_report_json([_claim_json([number])]),
                             allowed_pointers=self.allowed)

    def test_zero_and_negative_numbers_are_rejected(self):
        # Numbering is 1-based on purpose. `0` is the number a model reaches for
        # to mean "none", and a 0-based mapping would silently credit the FIRST
        # item to a claim that has no evidence. Negative indices would wrap to
        # the end of the tuple, which is the same defect from the other side.
        for number in (0, -1, -len(self.allowed)):
            with self.subTest(number=number), self.assertRaisesRegex(
                    ValueError, "not an item of this context package"):
                parse_report(_report_json([_claim_json([number])]),
                             allowed_pointers=self.allowed)

    def test_number_only_another_package_would_have_is_rejected(self):
        # Same shape as the old "valid-looking pointer of another package": a
        # number that is legitimate somewhere else must not be honoured here.
        bigger = package_pointers(_package(
            _BLOCK, _MEMORY, _CANDIDATE,
            IndexPointer("p1", "source_blocks", "other-block", "ver9", "hash9")))
        self.assertEqual(len(bigger), len(self.allowed) + 1)
        with self.assertRaisesRegex(ValueError, "not an item of this context package"):
            parse_report(_report_json([_claim_json([len(bigger)])]),
                         allowed_pointers=self.allowed)

    def test_pointer_object_of_the_old_wire_is_rejected(self):
        # over-strict for the R-e migration: a model (or a half-reverted prompt)
        # that still emits the v1 pointer object must fail, not be silently
        # tolerated — accepting both wires would hide which contract is live.
        real = pointer_wire(self.allowed[0])
        for name, value in (("pointer", real), ("rogue", {**real, "project_id": "p1"})):
            with self.subTest(name=name), self.assertRaisesRegex(
                    ValueError, "must be an item number"):
                parse_report(_report_json([_claim_json([value])]),
                             allowed_pointers=self.allowed)

    def test_non_integer_citation_is_rejected(self):
        # `"1"` and `1.0` are what a JSON-sloppy model produces, and `true` is
        # the one that matters most: bool is a subclass of int in Python, so
        # without the explicit guard `true` would resolve to item 1.
        for value in ("1", 1.0, True, None, [1]):
            with self.subTest(value=repr(value)), self.assertRaisesRegex(
                    ValueError, "must be an item number"):
                parse_report(_report_json([_claim_json([value])]),
                             allowed_pointers=self.allowed)

    def test_non_array_pointer_field_is_rejected(self):
        # H1 (verification 2026-07-15): the field is an ARRAY. A bare number,
        # object or string is rejected by the shared _list helper; pinned here so
        # the citation contract is self-contained in its own class.
        for value in ("x", pointer_wire(self.allowed[0]), 3):
            claim = {"text": "x", "type": "narrative_event",
                     "requires_gate_check": True,
                     "related_context_pointers": value}
            with self.subTest(value=type(value).__name__), self.assertRaisesRegex(
                    ValueError, "must be an array"):
                parse_report(_report_json([claim]), allowed_pointers=self.allowed)

    def test_duplicate_number_in_one_claim_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "must not repeat"):
            parse_report(_report_json([_claim_json([1, 1])]),
                         allowed_pointers=self.allowed)

    def test_two_claims_may_cite_the_same_item(self):
        # over-strict: dedup is per claim; two claims grounded in one item is
        # normal and must not be rejected.
        report = parse_report(
            _report_json([_claim_json([1], text="a"), _claim_json([1], text="b")]),
            allowed_pointers=self.allowed)
        self.assertEqual(len(report["candidate_claims"]), 2)

    def test_default_allowlist_admits_empty_claims_only(self):
        # fails-closed: a caller that passes no allowlist can only get []
        # claims through — every number is out of range for an empty package.
        self.assertEqual(parse_report(_report_json([_claim_json([])]))
                         ["candidate_claims"][0].related_context_pointers, ())
        with self.assertRaisesRegex(ValueError, "not an item of this context package"):
            parse_report(_report_json([_claim_json([1])]))

    def test_fence_extraction_does_not_weaken_the_allowlist(self):
        # The v1.6.85 fence strip applies to citation-carrying JSON too, but it
        # normalizes format only: a fenced valid number parses, a fenced
        # out-of-range number is still rejected.
        fenced = f"```json\n{_report_json([_claim_json([1])])}\n```"
        self.assertEqual(
            parse_report(fenced, allowed_pointers=self.allowed)
            ["candidate_claims"][0].related_context_pointers, (self.allowed[0],))
        bad = f"```json\n{_report_json([_claim_json([len(self.allowed) + 1])])}\n```"
        with self.assertRaisesRegex(ValueError, "not an item of this context package"):
            parse_report(bad, allowed_pointers=self.allowed)


class ReportServicePointerTest(unittest.TestCase):
    def test_extractor_cites_a_number_and_the_service_maps_it_back(self):
        # Service-level under-strict, end to end: the prompt numbers the items in
        # allowlist order (macro item = 1, micro item = 2) and the number the
        # model wrote comes back as that item's pointer on the enriched
        # candidate. The prompt and the parser derive the order from two
        # different places (`format_context_package` sections vs
        # `package_pointers`), so this cell is what fails if they diverge —
        # swapping either order makes claim 2 resolve to the source block.
        provider = _Provider([_report_json([_claim_json([2])])])
        package = _package(_MEMORY, macro=(_BLOCK,))
        enriched = asyncio.run(_service(provider).enrich(_candidate(), package))
        sent = json.loads(provider.requests[0].messages[1].content)["context_package"]
        self.assertIn("- [1] [canonical] 문이 열렸다", sent)
        self.assertIn("- [2] [canonical] 문이 열렸다", sent)
        self.assertEqual(enriched.candidate_claims[0].related_context_pointers,
                         (ContextPointer("memory_entries", "m1", "3", ""),))
        # over-strict (R-e): the 64-char hash and the pointer keys are exactly
        # what R-e removed — 79% of the report context. If any of them come back
        # the saving is gone even though every other assertion still passes.
        for removed in ('"collection"', "source_blocks", "memory_entries", "hash1"):
            self.assertNotIn(removed, sent)

    def test_template_requires_numbers_and_forbids_invention(self):
        provider = _Provider([_report_json([_claim_json([])])])
        asyncio.run(_service(provider).enrich(_candidate(), _package(_BLOCK)))
        template = provider.requests[0].messages[0].content
        self.assertIn('"related_context_pointers"', template)
        self.assertIn("`- [N] [label] text`", template)
        self.assertIn("as a plain integer", template)
        self.assertIn("never use a number that is not shown in this request", template)
        # The old instruction told the model to copy the pointer object. Leaving
        # it in a prompt that no longer shows pointers is how a template ends up
        # asking for a field the request cannot supply.
        self.assertNotIn("pointer object", template)

    def test_cross_project_item_is_rejected_before_the_provider(self):
        # This cell now carries the whole "identity is validated before the
        # model is called" contract (2, P-i): before R-e the prompt formatter
        # projected every pointer too, so there were two independent rejection
        # points. The prompt no longer touches identity, and the only remaining
        # one is `package_pointers` in `enrich_metered` — which runs before the
        # request is built. `provider.calls == 0` is the assertion that says so.
        provider = _Provider([_report_json([_claim_json([])])])
        package = _package(IndexPointer("other", "source_blocks", "b1", "ver1", "hash1"))
        with self.assertRaisesRegex(InvalidCandidateReport, "belongs to project"):
            asyncio.run(_service(provider).enrich(_candidate(), package))
        self.assertEqual(provider.calls, 0)

    def test_invariant_violating_item_is_rejected_before_the_provider(self):
        provider = _Provider([_report_json([_claim_json([])])])
        package = _package(IndexPointer("p1", "source_blocks", "b1", "ver1", ""))
        with self.assertRaisesRegex(InvalidCandidateReport, "non-empty content_hash"):
            asyncio.run(_service(provider).enrich(_candidate(), package))
        self.assertEqual(provider.calls, 0)


class PointerExposureBoundaryTest(unittest.TestCase):
    """D2=A: only the report extractor can cite package items (contract 3)."""

    def test_default_formatter_shows_no_pointer_and_no_number(self):
        # over-strict: generation and revise send prose prompts; leaking DB
        # identity into them is the D2=B option the owner rejected, and a
        # citation number there would be an instruction the prompt never
        # explains.
        text = format_context_package(_package(_BLOCK, _MEMORY, _CANDIDATE))
        self.assertNotIn("collection", text)
        self.assertNotIn("source_blocks", text)
        self.assertNotIn("- [1]", text)
        self.assertIn("- [canonical] 문이 열렸다", text)
        self.assertIn("- [candidate (uncertain)] 문이 열렸다", text)

    def test_report_formatter_numbers_items_instead_of_showing_pointers(self):
        # under-strict + the R-e over-strict guard in one place: the number is
        # there and the pointer JSON is not.
        text = format_context_package(_package(_BLOCK), include_citation_numbers=True)
        self.assertIn("- [1] [canonical] 문이 열렸다", text)
        for removed in ('"collection"', "source_blocks", "b1", "ver1", "hash1"):
            self.assertNotIn(removed, text)

    def test_citation_numbers_run_continuously_across_sections(self):
        # `package_pointers` concatenates macro then micro, so the numbering must
        # too: the micro section starts where macro left off. If the sections were
        # numbered independently, every micro item would resolve to a macro one.
        package = _package(_MEMORY, _CANDIDATE, macro=(_BLOCK,))
        text = format_context_package(package, include_citation_numbers=True)
        macro, micro = text.split("<micro_evidence>")
        self.assertIn("- [1] [canonical]", macro)
        self.assertIn("- [2] [canonical]", micro)
        self.assertIn("- [3] [candidate (uncertain)]", micro)
        self.assertEqual(len(package_pointers(package)), 3)

    def test_labels_and_sections_are_unchanged_by_numbering(self):
        # The number is additive: the candidate label a consumer relies on
        # (§2.2) still precedes the text.
        text = format_context_package(_package(_CANDIDATE), include_citation_numbers=True)
        self.assertIn("<micro_evidence>", text)
        self.assertIn("- [1] [candidate (uncertain)] 문이 열렸다", text)

    def test_generation_service_sends_no_pointer(self):
        # H2 (verification 2026-07-15) service-seam tripwire: the formatter test
        # above locks the default, but only this one bites if the generation call
        # site starts sending DB identity. Generation emits prose, so identity
        # must never reach its prompt (D2=B, the rejected axis). Since R-e no
        # formatter path renders identity at all, this is now a guard against
        # re-opening that door rather than against a flag typo.
        provider = _Provider(["이어진 장면."])
        templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        seed_writing_template(templates)
        asyncio.run(WritingService(provider, prompt_templates=templates).generate(
            request=WritingRequest("wr1", "p1", WritingTaskType.CONTINUE_SCENE, "이어서 써줘."),
            package=_package(_BLOCK, _MEMORY, _CANDIDATE)))
        sent = provider.requests[0].messages[1].content
        self.assertIn("[CONTEXT PACKAGE]", sent)
        for leak in ('"collection"', "source_blocks", "memory_entries", "hash1"):
            self.assertNotIn(leak, sent)

    def test_revise_service_sends_no_pointer(self):
        # H2 service-seam tripwire, revise half: the reviser splices prose and
        # returns no pointers, so its prompt carries none either.
        provider = _Provider(["아린은 문을 닫았다."])
        templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        seed_writing_revise_template(templates)
        finding = WritingGateFinding(
            WritingGateFindingType.CONTINUITY, WritingGateSeverity.ERROR,
            "모순", "아린은 문을 열었다.", WritingGateDecision.REVISE)
        asyncio.run(WritingRevisionService(provider, prompt_templates=templates).revise(
            candidate=_candidate(), finding=finding, instruction="고쳐줘",
            package=_package(_BLOCK, _MEMORY, _CANDIDATE)))
        sent = json.loads(provider.requests[0].messages[1].content)["context_package"]
        for leak in ('"collection"', "source_blocks", "memory_entries", "hash1"):
            self.assertNotIn(leak, sent)


class PointerConsumerTest(unittest.TestCase):
    """Contract 4: the claim's pointers reach the Gate and the accept advisory
    copy under the same public wire literals."""

    @staticmethod
    def _enriched():
        pointer = ContextPointer("memory_entries", "m1", "3", "")
        return pointer, WritingCandidate(
            "wr1", "p1", WritingTaskType.CONTINUE_SCENE,
            WritingOutputType.DRAFT_PATCH, "아린은 문을 열었다.",
            candidate_claims=(CandidateClaim(
                "문이 열렸다", CandidateClaimType.NARRATIVE_EVENT, True, (pointer,)),))

    def test_gate_prompt_carries_claim_pointers(self):
        pointer, candidate = self._enriched()
        request = build_writing_gate_request(
            request=WritingRequest("wr1", "p1", WritingTaskType.CONTINUE_SCENE, "이어서"),
            candidate=candidate, package=_package(_MEMORY),
            prompt_template=PromptTemplate(
                id="x", task_type="writing_gate", version="v", template="gate"))
        claim = json.loads(request.messages[1].content)["candidate"]["candidate_claims"][0]
        self.assertEqual(claim["related_context_pointers"], [pointer_wire(pointer)])

    def test_accept_advisory_copy_carries_claim_pointers(self):
        pointer, candidate = self._enriched()
        claim = _candidate_report_payload(candidate)["candidate_claims"][0]
        self.assertEqual(claim["related_context_pointers"], [pointer_wire(pointer)])
        self.assertEqual(sorted(claim["related_context_pointers"][0]),
                         ["collection", "content_hash", "document_id", "version_id"])


if __name__ == "__main__":
    unittest.main()
