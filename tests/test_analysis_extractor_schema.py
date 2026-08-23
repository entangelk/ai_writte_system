import json
import unittest

from services.application.app.analysis.extractor import (
    AnalysisExtractionAdapter,
    AnalysisExtractionError,
    VersionedPromptAnalysisExtractionAdapter,
    parse_analysis_extraction,
)
from services.application.app.analysis.models import (
    AnalysisCandidateAction,
    AnalysisCandidateType,
    AnalysisProvenance,
    SnapshotText,
)
from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository,
    PromptTemplateService,
)
from services.application.app.analysis.schema import (
    InvalidAnalysisPayload,
    validate_candidate_payload,
)
from services.application.app.analysis.service import (
    AnalysisService,
    InMemoryAnalysisRepository,
    InvalidAnalysisCandidate,
)
from services.application.app.core_sot.models import SourceRef
from services.llm_gateway.app.provider import FakeLLMProvider, GenerationResult


def _candidate(candidate_type, payload):
    return {
        "candidate_type": candidate_type,
        "provenance": "source_observed",
        "confidence": 0.8,
        "source_anchors": [_anchor("source-ref-1", 0, 2, "민아")],
        "payload": payload,
    }


def _anchor(source_ref_id, start_offset, end_offset, quote):
    return {
        "source_ref_id": source_ref_id,
        "start_offset": start_offset,
        "end_offset": end_offset,
        "quote": quote,
        "content_hash": "hash-1",
    }


def _content(candidates):
    return json.dumps({"candidates": candidates}, ensure_ascii=False)


class AnalysisTaxonomySchemaTest(unittest.TestCase):
    def test_all_three_phase2a_payload_shapes_are_accepted(self):
        """Over-strict guard: each approved taxonomy shape must remain storable."""
        service = AnalysisService(InMemoryAnalysisRepository())
        job = service.create_job(
            project_id="project-1",
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        ).job
        cases = [
            (
                AnalysisCandidateType.CHARACTER_OBSERVATION,
                "character:min-a",
                {"name": "민아", "observation": "민아가 편지를 발견했다."},
            ),
            (
                AnalysisCandidateType.EVENT_OBSERVATION,
                "event:letter",
                {"event": "민아가 편지를 발견했다."},
            ),
            (
                AnalysisCandidateType.OPEN_QUESTION_OBSERVATION,
                "question:sender",
                {"question": "편지를 보낸 사람은 누구인가?"},
            ),
        ]

        for candidate_type, logical_key, payload in cases:
            with self.subTest(candidate_type=candidate_type.value):
                task = service.create_task(
                    project_id="project-1",
                    job_id=job.id,
                    candidate_type=candidate_type,
                )
                result = service.record_candidate(
                    project_id="project-1",
                    task_id=task.id,
                    logical_key=logical_key,
                    candidate_type=candidate_type,
                    action=AnalysisCandidateAction.CREATE,
                    provenance=AnalysisProvenance.SOURCE_OBSERVED,
                    confidence=0.8,
                    source_ref_ids=("source-ref-1",),
                    payload=payload,
                )

                self.assertEqual(dict(result.candidate.payload), payload)

    def test_malformed_payload_is_rejected_by_service(self):
        """Under-strict guard: storage cannot accept missing/extra/wrong fields."""
        service = AnalysisService(InMemoryAnalysisRepository())
        job = service.create_job(
            project_id="project-1",
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        ).job
        task = service.create_task(
            project_id="project-1",
            job_id=job.id,
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
        )
        bad_payloads = [
            {"name": "민아"},
            {"name": "민아", "observation": ""},
            {"name": "민아", "observation": "관찰", "mood": "불안"},
            {"event": "민아가 편지를 발견했다."},
        ]

        for index, payload in enumerate(bad_payloads):
            with self.subTest(payload=payload):
                with self.assertRaises(InvalidAnalysisCandidate):
                    service.record_candidate(
                        project_id="project-1",
                        task_id=task.id,
                        logical_key=f"character:bad-{index}",
                        candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
                        action=AnalysisCandidateAction.CREATE,
                        provenance=AnalysisProvenance.SOURCE_OBSERVED,
                        confidence=0.8,
                        source_ref_ids=("source-ref-1",),
                        payload=payload,
                    )


class CharacterAspectPayloadTest(unittest.TestCase):
    """증분 3 (D4=B, owner=optional): character_observation payload may carry an
    optional ``aspect`` classifier. Taxonomy stays 3-typed (2A D5=A); the field is
    optional so existing ``{name, observation}`` payloads keep validating.

    Boundary matrix for the validator:
      - {name, observation}            → accepted (backward compat, no migration)
      - {name, observation, aspect}    → accepted, aspect preserved
      - aspect present but empty ""    → rejected (non-empty guard)
      - aspect on a non-character type → rejected (unknown field)
      - unknown extra field (mood)     → still rejected
    """

    def test_aspect_is_optional_and_backward_compatible(self):
        # under-strict: the pre-slice shape must keep validating unchanged.
        normalized = validate_candidate_payload(
            AnalysisCandidateType.CHARACTER_OBSERVATION,
            {"name": "아린", "observation": "성문 앞에서 멈췄다."},
        )
        self.assertEqual(
            dict(normalized), {"name": "아린", "observation": "성문 앞에서 멈췄다."}
        )

    def test_aspect_is_accepted_and_preserved(self):
        # under-strict: a present aspect (free string) is stored, enabling D5.
        normalized = validate_candidate_payload(
            AnalysisCandidateType.CHARACTER_OBSERVATION,
            {"name": "아린", "observation": "짧게 끊어 말한다.", "aspect": "voice"},
        )
        self.assertEqual(dict(normalized), {
            "name": "아린", "observation": "짧게 끊어 말한다.", "aspect": "voice",
        })

    def test_aspect_value_is_a_free_string_not_an_enum(self):
        # over-strict guard: aspect is extensible (Follow-up), so an arbitrary
        # value must validate — pinning it to an enum would re-fail this.
        normalized = validate_candidate_payload(
            AnalysisCandidateType.CHARACTER_OBSERVATION,
            {"name": "아린", "observation": "x", "aspect": "speech-rhythm"},
        )
        self.assertEqual(normalized["aspect"], "speech-rhythm")

    def test_empty_aspect_is_rejected(self):
        # under-strict: a present-but-empty aspect is not a valid classifier.
        with self.assertRaises(InvalidAnalysisPayload):
            validate_candidate_payload(
                AnalysisCandidateType.CHARACTER_OBSERVATION,
                {"name": "아린", "observation": "x", "aspect": ""},
            )

    def test_aspect_is_rejected_on_non_character_types(self):
        # over-strict guard: aspect is a character-only optional; on event/question
        # it is an unknown field. Making optional fields global would re-fail this.
        for candidate_type, payload in (
            (AnalysisCandidateType.EVENT_OBSERVATION,
             {"event": "문이 열렸다.", "aspect": "voice"}),
            (AnalysisCandidateType.OPEN_QUESTION_OBSERVATION,
             {"question": "누구인가?", "aspect": "voice"}),
        ):
            with self.subTest(candidate_type=candidate_type.value):
                with self.assertRaises(InvalidAnalysisPayload):
                    validate_candidate_payload(candidate_type, payload)

    def test_other_unknown_fields_still_rejected(self):
        # under-strict: allowing aspect must not open the door to arbitrary keys.
        with self.assertRaises(InvalidAnalysisPayload):
            validate_candidate_payload(
                AnalysisCandidateType.CHARACTER_OBSERVATION,
                {"name": "아린", "observation": "x", "mood": "불안"},
            )

    def test_missing_required_field_still_rejected(self):
        with self.assertRaises(InvalidAnalysisPayload):
            validate_candidate_payload(
                AnalysisCandidateType.CHARACTER_OBSERVATION,
                {"name": "아린", "aspect": "voice"},
            )

    def test_non_string_aspect_is_rejected(self):
        # hardening (D4): aspect must be a non-empty STRING, not merely truthy.
        # The contract says "non-empty string"; if the guard ever relaxed to a
        # truthy check (`if not value`), aspect=123 would slip through — re-fails.
        with self.assertRaises(InvalidAnalysisPayload):
            validate_candidate_payload(
                AnalysisCandidateType.CHARACTER_OBSERVATION,
                {"name": "아린", "observation": "x", "aspect": 123},
            )

    def test_aspect_does_not_permit_other_unknown_fields_alongside(self):
        # hardening (D4): allowing aspect must not open the door to a second
        # unknown key. {name, observation, aspect, mood} is still malformed; if
        # allowed_fields were widened to accept any superset, mood would slip in.
        with self.assertRaises(InvalidAnalysisPayload):
            validate_candidate_payload(
                AnalysisCandidateType.CHARACTER_OBSERVATION,
                {"name": "아린", "observation": "x", "aspect": "voice",
                 "mood": "불안"},
            )


class AnalysisExtractionAdapterTest(unittest.IsolatedAsyncioTestCase):
    async def test_fake_provider_result_parses_into_candidate_drafts(self):
        provider = FakeLLMProvider(
            [
                GenerationResult(
                    model="fake-gemma",
                    content=_content(
                        [
                            _candidate(
                                "character_observation",
                                {
                                    "name": "민아",
                                    "observation": "민아가 편지를 발견했다.",
                                },
                            )
                        ]
                    ),
                    finish_reason="stop",
                )
            ]
        )
        adapter = AnalysisExtractionAdapter(provider)

        drafts = await adapter.extract(
            SnapshotText(
                project_id="project-1",
                snapshot_id="snapshot-1",
                raw_text="민아",
                content_hash="hash-1",
                block_ids=("block-1",),
            )
        )

        self.assertEqual(len(drafts), 1)
        self.assertEqual(
            drafts[0].candidate_type, AnalysisCandidateType.CHARACTER_OBSERVATION
        )
        self.assertEqual(drafts[0].provenance, AnalysisProvenance.SOURCE_OBSERVED)
        self.assertEqual(drafts[0].source_anchors[0].source_ref_id, "source-ref-1")
        self.assertTrue(
            drafts[0].logical_key.startswith("character_observation:")
        )
        self.assertEqual(len(provider.requests), 1)
        self.assertEqual(provider.requests[0].messages[-1].content, "민아")
        self.assertIs(provider.requests[0].thinking, False)

    async def test_versioned_prompt_adapter_uses_template_and_source_ref_catalog(self):
        provider = FakeLLMProvider(
            [
                GenerationResult(
                    model="fake-gemma",
                    content=_content(
                        [
                            _candidate(
                                "character_observation",
                                {
                                    "name": "민아",
                                    "observation": "민아가 편지를 발견했다.",
                                },
                            )
                        ]
                    ),
                    finish_reason="stop",
                )
            ]
        )
        prompt_templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        template = prompt_templates.seed_analysis_extract_v5()
        adapter = VersionedPromptAnalysisExtractionAdapter(
            provider,
            prompt_templates=prompt_templates,
            source_ref_catalog=_Catalog(
                (
                    SourceRef(
                        id="source-ref-1",
                        project_id="project-1",
                        snapshot_id="snapshot-1",
                        block_id="block-1",
                        start_offset=0,
                        end_offset=2,
                        quote="민아",
                        content_hash="hash-1",
                    ),
                )
            ),
            model="gemma",
            max_tokens=512,
        )

        drafts = await adapter.extract(
            SnapshotText(
                project_id="project-1",
                snapshot_id="snapshot-1",
                raw_text="민아는 편지를 발견했다.",
                content_hash="hash-1",
                block_ids=("block-1",),
            )
        )

        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0].source_anchors[0].source_ref_id, "source-ref-1")
        self.assertEqual(provider.requests[0].messages[0].content, template.template)
        self.assertIn("source-ref-1", provider.requests[0].messages[1].content)
        self.assertEqual(provider.requests[0].model, "gemma")
        self.assertEqual(provider.requests[0].max_tokens, 512)

    async def test_versioned_prompt_adapter_repairs_invalid_provider_json_once(self):
        provider = FakeLLMProvider(
            [
                GenerationResult(
                    model="fake-gemma",
                    content='{"candidates": [ this is not valid json',
                    finish_reason="stop",
                ),
                GenerationResult(
                    model="fake-gemma",
                    content=_content(
                        [
                            _candidate(
                                "character_observation",
                                {
                                    "name": "민아",
                                    "observation": "민아가 편지를 발견했다.",
                                },
                            )
                        ]
                    ),
                    finish_reason="stop",
                ),
            ]
        )
        prompt_templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        prompt_templates.seed_analysis_extract_v4()
        prompt_templates.seed_analysis_extract_v5()
        adapter = VersionedPromptAnalysisExtractionAdapter(
            provider,
            prompt_templates=prompt_templates,
            source_ref_catalog=_Catalog(
                (
                    SourceRef(
                        id="source-ref-1",
                        project_id="project-1",
                        snapshot_id="snapshot-1",
                        block_id="block-1",
                        start_offset=0,
                        end_offset=2,
                        quote="민아",
                        content_hash="hash-1",
                    ),
                )
            ),
            model="gemma",
            max_tokens=512,
        )

        drafts = await adapter.extract(
            SnapshotText(
                project_id="project-1",
                snapshot_id="snapshot-1",
                raw_text="민아는 편지를 발견했다.",
                content_hash="hash-1",
                block_ids=("block-1",),
            )
        )

        self.assertEqual(len(drafts), 1)
        self.assertEqual(len(provider.requests), 2)
        repair = provider.requests[1]
        self.assertEqual(repair.model, "gemma")
        self.assertEqual(repair.max_tokens, 512)
        self.assertIs(repair.thinking, False)
        self.assertIn("Return valid JSON only", repair.messages[0].content)
        self.assertIn("provider content must be JSON", repair.messages[1].content)
        self.assertIn("source-ref-1", repair.messages[1].content)
        self.assertIn("candidate_type", repair.messages[0].content)

    async def test_versioned_prompt_adapter_repairs_catalog_id_drift_once(self):
        provider = FakeLLMProvider(
            [
                GenerationResult(
                    model="fake-gemma",
                    content=_content(
                        [
                            {
                                **_candidate(
                                    "character_observation",
                                    {
                                        "name": "민아",
                                        "observation": "민아가 편지를 발견했다.",
                                    },
                                ),
                                "source_anchors": [
                                    _anchor("source_ref-1", 0, 2, "민아")
                                ],
                            }
                        ]
                    ),
                    finish_reason="stop",
                ),
                GenerationResult(
                    model="fake-gemma",
                    content=_content(
                        [
                            _candidate(
                                "character_observation",
                                {
                                    "name": "민아",
                                    "observation": "민아가 편지를 발견했다.",
                                },
                            )
                        ]
                    ),
                    finish_reason="stop",
                ),
            ]
        )
        prompt_templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        prompt_templates.seed_analysis_extract_v4()
        prompt_templates.seed_analysis_extract_v5()
        adapter = VersionedPromptAnalysisExtractionAdapter(
            provider,
            prompt_templates=prompt_templates,
            source_ref_catalog=_Catalog(
                (
                    SourceRef(
                        id="source-ref-1",
                        project_id="project-1",
                        snapshot_id="snapshot-1",
                        block_id="block-1",
                        start_offset=0,
                        end_offset=2,
                        quote="민아",
                        content_hash="hash-1",
                    ),
                )
            ),
        )

        drafts = await adapter.extract(
            SnapshotText(
                project_id="project-1",
                snapshot_id="snapshot-1",
                raw_text="민아",
                content_hash="hash-1",
                block_ids=("block-1",),
                writing_candidate_report={
                    "candidate_claims": [
                        {
                            "text": "민아가 편지를 발견했다.",
                            "related_context_pointers": [
                                {
                                    "collection": "source_blocks",
                                    "document_id": "old-snapshot:block:4",
                                    "version_id": "old-version",
                                    "content_hash": "old-hash",
                                }
                            ],
                        }
                    ]
                },
            )
        )

        self.assertEqual(len(provider.requests), 2)
        self.assertEqual(drafts[0].source_anchors[0].source_ref_id, "source-ref-1")
        self.assertIn(
            "source_ref_id must exactly match the source_ref catalog",
            provider.requests[1].messages[1].content,
        )
        self.assertIn("advisory provenance", provider.requests[1].messages[0].content)
        self.assertIn("Never copy document_id", provider.requests[1].messages[0].content)
        repair_payload = json.loads(provider.requests[1].messages[1].content)
        self.assertEqual(
            repair_payload["authoritative_source_ref_catalog"][0]["source_ref_id"],
            "source-ref-1",
        )
        self.assertNotIn("writing_candidate_report", repair_payload)
        self.assertNotIn("old-snapshot:block:4", provider.requests[1].messages[1].content)
        self.assertIn(
            "authoritative_source_ref_catalog in the repair payload",
            provider.requests[1].messages[0].content,
        )

    async def test_versioned_prompt_adapter_repairs_catalog_anchor_drift_once(self):
        provider = FakeLLMProvider(
            [
                GenerationResult(
                    model="fake-gemma",
                    content=_content(
                        [
                            {
                                **_candidate(
                                    "character_observation",
                                    {
                                        "name": "민아",
                                        "observation": "민아가 편지를 발견했다.",
                                    },
                                ),
                                "source_anchors": [
                                    _anchor("source-ref-1", 0, 2, "민호")
                                ],
                            }
                        ]
                    ),
                    finish_reason="stop",
                ),
                GenerationResult(
                    model="fake-gemma",
                    content=_content(
                        [
                            _candidate(
                                "character_observation",
                                {
                                    "name": "민아",
                                    "observation": "민아가 편지를 발견했다.",
                                },
                            )
                        ]
                    ),
                    finish_reason="stop",
                ),
            ]
        )
        prompt_templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        prompt_templates.seed_analysis_extract_v4()
        prompt_templates.seed_analysis_extract_v5()
        adapter = VersionedPromptAnalysisExtractionAdapter(
            provider,
            prompt_templates=prompt_templates,
            source_ref_catalog=_Catalog(
                (
                    SourceRef(
                        id="source-ref-1",
                        project_id="project-1",
                        snapshot_id="snapshot-1",
                        block_id="block-1",
                        start_offset=0,
                        end_offset=2,
                        quote="민아",
                        content_hash="hash-1",
                    ),
                )
            ),
        )

        drafts = await adapter.extract(
            SnapshotText(
                project_id="project-1",
                snapshot_id="snapshot-1",
                raw_text="민아",
                content_hash="hash-1",
                block_ids=("block-1",),
            )
        )

        self.assertEqual(len(provider.requests), 2)
        self.assertEqual(drafts[0].source_anchors[0].quote, "민아")
        self.assertIn(
            "source_anchors must preserve catalog span, quote, and content_hash",
            provider.requests[1].messages[1].content,
        )

    async def test_versioned_prompt_adapter_does_not_retry_more_than_once(self):
        provider = FakeLLMProvider(
            [
                GenerationResult(
                    model="fake-gemma",
                    content="{not valid json",
                    finish_reason="stop",
                ),
                GenerationResult(
                    model="fake-gemma",
                    content="still not json",
                    finish_reason="stop",
                ),
            ]
        )
        prompt_templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        prompt_templates.seed_analysis_extract_v4()
        prompt_templates.seed_analysis_extract_v5()
        adapter = VersionedPromptAnalysisExtractionAdapter(
            provider,
            prompt_templates=prompt_templates,
            source_ref_catalog=_Catalog(
                (
                    SourceRef(
                        id="source-ref-1",
                        project_id="project-1",
                        snapshot_id="snapshot-1",
                        block_id="block-1",
                        start_offset=0,
                        end_offset=2,
                        quote="민아",
                        content_hash="hash-1",
                    ),
                )
            ),
        )

        with self.assertRaises(AnalysisExtractionError):
            await adapter.extract(
                SnapshotText(
                    project_id="project-1",
                    snapshot_id="snapshot-1",
                    raw_text="민아",
                    content_hash="hash-1",
                    block_ids=("block-1",),
                )
            )

        self.assertEqual(len(provider.requests), 2)

    async def test_versioned_prompt_adapter_rejects_missing_catalog_before_provider(self):
        provider = FakeLLMProvider([])
        prompt_templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        prompt_templates.seed_analysis_extract_v4()
        prompt_templates.seed_analysis_extract_v5()
        adapter = VersionedPromptAnalysisExtractionAdapter(
            provider,
            prompt_templates=prompt_templates,
            source_ref_catalog=_Catalog(()),
        )

        with self.assertRaises(AnalysisExtractionError):
            await adapter.extract(
                SnapshotText(
                    project_id="project-1",
                    snapshot_id="snapshot-1",
                    raw_text="민아",
                    content_hash="hash-1",
                    block_ids=("block-1",),
                )
            )

        self.assertEqual(provider.requests, [])

    def test_extractor_rejects_malformed_provider_payload(self):
        """Under-strict guard: invalid provider JSON cannot become a draft."""
        malformed = [
            "[]",
            _content(
                [
                    _candidate(
                        "location_observation",
                        {"name": "창고", "observation": "창고가 나온다."},
                    )
                ]
            ),
            _content(
                [
                    {
                        **_candidate(
                            "character_observation",
                            {"name": "민아", "observation": "관찰"},
                        ),
                        "provenance": "user_declared",
                    }
                ]
            ),
            _content(
                [
                    {
                        **_candidate(
                            "character_observation",
                            {"name": "민아", "observation": "관찰"},
                        ),
                        "confidence": float("nan"),
                    }
                ]
            ),
            _content(
                [
                    _candidate(
                        "character_observation",
                        {"name": "민아"},
                    )
                ]
            ),
            _content(
                [
                    {
                        **_candidate(
                            "character_observation",
                            {"name": "민아", "observation": "관찰"},
                        ),
                        "source_anchors": [
                            {
                                "source_ref_id": "source-ref-1",
                                "start_offset": 2,
                                "end_offset": 2,
                                "quote": "민아",
                                "content_hash": "hash-1",
                            }
                        ],
                    }
                ]
            ),
        ]

        for content in malformed:
            with self.subTest(content=content):
                with self.assertRaises(AnalysisExtractionError):
                    parse_analysis_extraction(content)

    def test_empty_candidates_array_is_valid_empty_extraction(self):
        self.assertEqual(parse_analysis_extraction(json.dumps({"candidates": []})), ())

    def test_fenced_valid_extraction_is_extracted(self):
        # Under-strict: a whole-content markdown fence is stripped before
        # json.loads. Removing strip_code_fence re-fails with a JSON error.
        content = _content(
            [_candidate("character_observation",
                        {"name": "민아", "observation": "민아가 편지를 발견했다."})]
        )
        for tag in ("json", "", "text"):
            with self.subTest(tag=tag):
                drafts = parse_analysis_extraction(f"```{tag}\n{content}\n```")
                self.assertEqual(len(drafts), 1)

    def test_fence_does_not_weaken_object_check(self):
        # Over-strict: extraction unwraps format only — a fenced JSON array is
        # still rejected as "not a JSON object", exactly as an unfenced one.
        with self.assertRaisesRegex(AnalysisExtractionError, "must be a JSON object"):
            parse_analysis_extraction("```json\n[]\n```")

    def test_logical_key_is_stable_but_changes_when_payload_changes(self):
        """Over/under guard: retry identity is deterministic, not over-collapsed."""
        content = _content(
            [
                _candidate(
                    "character_observation",
                    {"name": "민아", "observation": "첫 관찰"},
                ),
                _candidate(
                    "character_observation",
                    {"name": "민아", "observation": "첫 관찰"},
                ),
                _candidate(
                    "character_observation",
                    {"name": "민아", "observation": "다른 관찰"},
                ),
            ]
        )

        first, replay, distinct = parse_analysis_extraction(content)

        self.assertEqual(replay.logical_key, first.logical_key)
        self.assertNotEqual(distinct.logical_key, first.logical_key)

    def test_logical_key_treats_same_anchor_set_as_order_insensitive(self):
        """Under/over guard: provider anchor ordering does not duplicate candidates."""
        anchors = [
            _anchor("source-ref-1", 0, 2, "민아"),
            _anchor("source-ref-2", 3, 5, "편지"),
        ]
        first = _candidate(
            "character_observation",
            {"name": "민아", "observation": "민아가 편지를 발견했다."},
        )
        replay = _candidate(
            "character_observation",
            {"name": "민아", "observation": "민아가 편지를 발견했다."},
        )
        distinct = _candidate(
            "character_observation",
            {"name": "민아", "observation": "민아가 편지를 발견했다."},
        )
        first["source_anchors"] = anchors
        replay["source_anchors"] = tuple(reversed(anchors))
        distinct["source_anchors"] = [
            _anchor("source-ref-1", 0, 2, "민아"),
            _anchor("source-ref-3", 6, 8, "창고"),
        ]

        first_draft, replay_draft, distinct_draft = parse_analysis_extraction(
            _content([first, replay, distinct])
        )

        self.assertEqual(replay_draft.logical_key, first_draft.logical_key)
        self.assertNotEqual(distinct_draft.logical_key, first_draft.logical_key)

    def test_logical_key_treats_duplicate_anchor_as_same_set_member(self):
        """Under/over guard: duplicate evidence anchors do not split identity."""
        anchor = _anchor("source-ref-1", 0, 2, "민아")
        first = _candidate(
            "character_observation",
            {"name": "민아", "observation": "민아가 편지를 발견했다."},
        )
        replay = _candidate(
            "character_observation",
            {"name": "민아", "observation": "민아가 편지를 발견했다."},
        )
        distinct = _candidate(
            "character_observation",
            {"name": "민아", "observation": "민아가 편지를 발견했다."},
        )
        first["source_anchors"] = [anchor]
        replay["source_anchors"] = [anchor, anchor]
        distinct["source_anchors"] = [
            anchor,
            _anchor("source-ref-2", 3, 5, "편지"),
        ]

        first_draft, replay_draft, distinct_draft = parse_analysis_extraction(
            _content([first, replay, distinct])
        )

        self.assertEqual(replay_draft.logical_key, first_draft.logical_key)
        self.assertEqual(len(replay_draft.source_anchors), 1)
        self.assertNotEqual(distinct_draft.logical_key, first_draft.logical_key)


class _Catalog:
    def __init__(self, source_refs):
        self._source_refs = tuple(source_refs)

    def list_source_refs(self, *, project_id: str, snapshot_id: str):
        return tuple(
            source_ref
            for source_ref in self._source_refs
            if source_ref.project_id == project_id
            and source_ref.snapshot_id == snapshot_id
        )


class AssemblyDefaultTest(unittest.TestCase):
    def test_extractor_assembly_default_max_tokens_has_fence_headroom(self):
        """조립 기본은 8192 — 2048은 펜스째 끊김으로 후보 0을 만들었다(2026-08-23).

        under-strict: 기본을 2048로 되돌리면 이 셀이 문다(세션 5/6 실측 경로).
        over-strict는 이 셀이 못 본다 — 값을 더 크게 바꾸는 것은 이 슬라이스의
        취지(끊김 여유)와 충돌하지 않는다. 소스 스캔인 이유는 env 기본값이
        조립 지점에만 존재해 인스턴스 검사보다 정확해서다(activity 가드 패턴).
        """
        import inspect

        from services.application.app import main

        source = inspect.getsource(main)
        self.assertIn(
            'os.environ.get("ANALYSIS_EXTRACT_MAX_TOKENS", "8192")', source
        )


if __name__ == "__main__":
    unittest.main()
