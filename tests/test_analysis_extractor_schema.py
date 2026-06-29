import json
import unittest

from services.application.app.analysis.extractor import (
    AnalysisExtractionAdapter,
    AnalysisExtractionError,
    parse_analysis_extraction,
)
from services.application.app.analysis.models import (
    AnalysisCandidateAction,
    AnalysisCandidateType,
    AnalysisProvenance,
    SnapshotText,
)
from services.application.app.analysis.service import (
    AnalysisService,
    InMemoryAnalysisRepository,
    InvalidAnalysisCandidate,
)
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

    def test_extractor_rejects_malformed_provider_payload(self):
        """Under-strict guard: invalid provider JSON cannot become a draft."""
        malformed = [
            "[]",
            json.dumps({"candidates": []}),
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


if __name__ == "__main__":
    unittest.main()
