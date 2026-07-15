"""Stable context pointer contract for Writing candidate claims.

Brief: docs/plans/05-writing-stable-context-pointer-decisions.md —
D1=A (projection of the existing IndexPointer), D2=A (pointers shown to the
report extractor only, validated as exact membership of the current package),
D3=A (required claim array, empty allowed), sub-decision P-i (per-origin field
invariant: a store fills only the fields it has).
"""

import asyncio
import json
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


def _claim_json(pointers, *, text="문이 열렸다"):
    return {"text": text, "type": "narrative_event", "requires_gate_check": True,
            "related_context_pointers": list(pointers)}


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
    """D2=A membership + D3=A required array."""

    def setUp(self):
        self.allowed = package_pointers(_package(_BLOCK, _MEMORY, _CANDIDATE))

    def test_each_origin_pointer_round_trips(self):
        # under-strict: a claim citing a real package item keeps the exact
        # object. Dropping the allowlist check would not fail here — the
        # rejection tests below carry that direction.
        for pointer in self.allowed:
            with self.subTest(collection=pointer.collection):
                report = parse_report(
                    _report_json([_claim_json([pointer_wire(pointer)])]),
                    allowed_pointers=self.allowed)
                self.assertEqual(
                    report["candidate_claims"][0].related_context_pointers,
                    (pointer,))

    def test_claim_may_cite_several_items(self):
        report = parse_report(
            _report_json([_claim_json(
                [pointer_wire(p) for p in self.allowed])]),
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

    def test_hallucinated_pointer_is_rejected(self):
        real = pointer_wire(self.allowed[0])
        for field in ("collection", "document_id", "version_id", "content_hash"):
            with self.subTest(field=field), self.assertRaisesRegex(
                    ValueError, "not an item of this context package"):
                parse_report(
                    _report_json([_claim_json([{**real, field: "invented"}])]),
                    allowed_pointers=self.allowed)

    def test_valid_looking_pointer_of_another_package_is_rejected(self):
        other = package_pointers(_package(
            IndexPointer("p1", "source_blocks", "other-block", "ver9", "hash9")))
        with self.assertRaisesRegex(ValueError, "not an item of this context package"):
            parse_report(_report_json([_claim_json([pointer_wire(other[0])])]),
                         allowed_pointers=self.allowed)

    def test_rogue_or_missing_pointer_key_is_rejected(self):
        real = pointer_wire(self.allowed[0])
        for name, value in (
            ("rogue", {**real, "project_id": "p1"}),
            ("missing", {k: v for k, v in real.items() if k != "content_hash"}),
        ):
            with self.subTest(name=name), self.assertRaisesRegex(
                    ValueError, "item fields do not match schema"):
                parse_report(_report_json([_claim_json([value])]),
                             allowed_pointers=self.allowed)

    def test_non_string_pointer_field_is_rejected(self):
        real = pointer_wire(self.allowed[0])
        with self.assertRaisesRegex(ValueError, "must be strings"):
            parse_report(_report_json([_claim_json([{**real, "version_id": 1}])]),
                         allowed_pointers=self.allowed)

    def test_non_array_pointer_field_is_rejected(self):
        # H1 (verification 2026-07-15): the field is an ARRAY of pointers. A bare
        # object or string is rejected by the shared _list helper; pinned here so
        # the pointer contract is self-contained in its own class.
        for value in ("x", pointer_wire(self.allowed[0]), 3):
            claim = {"text": "x", "type": "narrative_event",
                     "requires_gate_check": True,
                     "related_context_pointers": value}
            with self.subTest(value=type(value).__name__), self.assertRaisesRegex(
                    ValueError, "must be an array"):
                parse_report(_report_json([claim]), allowed_pointers=self.allowed)

    def test_duplicate_pointer_in_one_claim_is_rejected(self):
        wire = pointer_wire(self.allowed[0])
        with self.assertRaisesRegex(ValueError, "must not repeat"):
            parse_report(_report_json([_claim_json([wire, dict(wire)])]),
                         allowed_pointers=self.allowed)

    def test_two_claims_may_cite_the_same_item(self):
        # over-strict: dedup is per claim; two claims grounded in one item is
        # normal and must not be rejected.
        wire = pointer_wire(self.allowed[0])
        report = parse_report(
            _report_json([_claim_json([wire], text="a"),
                          _claim_json([dict(wire)], text="b")]),
            allowed_pointers=self.allowed)
        self.assertEqual(len(report["candidate_claims"]), 2)

    def test_default_allowlist_admits_empty_claims_only(self):
        # fails-closed: a caller that passes no allowlist can only get []
        # claims through — a pointer the model did not see never validates.
        self.assertEqual(parse_report(_report_json([_claim_json([])]))
                         ["candidate_claims"][0].related_context_pointers, ())
        with self.assertRaisesRegex(ValueError, "not an item of this context package"):
            parse_report(_report_json([_claim_json([pointer_wire(self.allowed[0])])]))

    def test_fence_extraction_does_not_weaken_the_allowlist(self):
        # The v1.6.85 fence strip applies to pointer-carrying JSON too, but it
        # normalizes format only: a fenced valid pointer parses, a fenced
        # unknown pointer is still rejected.
        wire = pointer_wire(self.allowed[0])
        fenced = f"```json\n{_report_json([_claim_json([wire])])}\n```"
        self.assertEqual(
            parse_report(fenced, allowed_pointers=self.allowed)
            ["candidate_claims"][0].related_context_pointers, (self.allowed[0],))
        bad = f"```json\n{_report_json([_claim_json([{**wire, 'document_id': 'x'}])])}\n```"
        with self.assertRaisesRegex(ValueError, "not an item of this context package"):
            parse_report(bad, allowed_pointers=self.allowed)


class ReportServicePointerTest(unittest.TestCase):
    def test_extractor_sees_pointers_and_claim_keeps_them(self):
        # Service-level under-strict: the prompt carries each item's pointer and
        # a claim citing one survives into the enriched candidate.
        wire = pointer_wire(ContextPointer("memory_entries", "m1", "3", ""))
        provider = _Provider([_report_json([_claim_json([wire])])])
        package = _package(_MEMORY, macro=(_BLOCK,))
        enriched = asyncio.run(_service(provider).enrich(_candidate(), package))
        sent = json.loads(provider.requests[0].messages[1].content)["context_package"]
        self.assertIn('{"collection":"memory_entries","content_hash":"",'
                      '"document_id":"m1","version_id":"3"}', sent)
        self.assertIn('"collection":"source_blocks"', sent)
        self.assertEqual(enriched.candidate_claims[0].related_context_pointers,
                         (ContextPointer("memory_entries", "m1", "3", ""),))

    def test_template_requires_pointers_and_forbids_invention(self):
        provider = _Provider([_report_json([_claim_json([])])])
        asyncio.run(_service(provider).enrich(_candidate(), _package(_BLOCK)))
        template = provider.requests[0].messages[0].content
        self.assertIn('"related_context_pointers"', template)
        self.assertIn("copy that item's pointer object exactly", template)

    def test_cross_project_item_is_rejected_before_the_provider(self):
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
    """D2=A: only the report extractor sees pointers (contract 3)."""

    def test_default_formatter_shows_no_pointer(self):
        # over-strict: generation and revise send prose prompts; leaking DB
        # identity into them is the D2=B option the owner rejected.
        text = format_context_package(_package(_BLOCK, _MEMORY, _CANDIDATE))
        self.assertNotIn("collection", text)
        self.assertNotIn("source_blocks", text)
        self.assertIn("- [canonical] 문이 열렸다", text)
        self.assertIn("- [candidate (uncertain)] 문이 열렸다", text)

    def test_report_formatter_prefixes_the_pointer(self):
        text = format_context_package(_package(_BLOCK), include_pointers=True)
        self.assertIn(
            '- [canonical] {"collection":"source_blocks","content_hash":"hash1",'
            '"document_id":"b1","version_id":"ver1"} 문이 열렸다', text)

    def test_labels_and_sections_are_unchanged_by_pointers(self):
        # The pointer is additive: the candidate label a consumer relies on
        # (§2.2) still precedes the text.
        text = format_context_package(_package(_CANDIDATE), include_pointers=True)
        self.assertIn("<micro_evidence>", text)
        self.assertIn("- [candidate (uncertain)] {", text)

    def test_generation_service_sends_no_pointer(self):
        # H2 (verification 2026-07-15) service-seam tripwire: the formatter test
        # above locks the default, but only this one bites if a call site starts
        # passing include_pointers=True. Generation emits prose, so DB identity
        # must never reach its prompt (D2=B, the rejected axis).
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
