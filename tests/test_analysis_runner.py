import json
import unittest

from services.application.app.analysis.extractor import (
    AnalysisCandidateDraft,
    AnalysisExtractionAdapter,
)
from services.application.app.analysis.models import (
    AnalysisCandidateType,
    AnalysisProvenance,
    CandidateSourceAnchor,
)
from services.application.app.analysis.runner import AnalysisExtractionRunner
from services.application.app.analysis.service import (
    AnalysisService,
    InMemoryAnalysisRepository,
    InvalidAnalysisCandidate,
)
from services.application.app.analysis.source import CoreSotSourceAdapter
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.llm_gateway.app.provider import FakeLLMProvider, GenerationResult


class AnalysisExtractionRunnerTest(unittest.IsolatedAsyncioTestCase):
    async def test_runner_loads_extracts_validates_and_stores_candidates(self):
        saved = self._saved_source()
        analysis_service, analysis_repo, source_adapter = self._analysis(
            saved["core_sot"]
        )
        provider = FakeLLMProvider(
            [
                self._provider_result(
                    [
                        self._candidate(
                            "character_observation",
                            {"name": "민아", "observation": "민아가 편지를 발견했다."},
                            saved["anchors"]["min-a"],
                        ),
                        self._candidate(
                            "event_observation",
                            {"event": "민아가 편지를 발견했다."},
                            saved["anchors"]["letter"],
                        ),
                    ]
                )
            ]
        )
        runner = AnalysisExtractionRunner(
            analysis_service=analysis_service,
            snapshot_loader=source_adapter,
            extractor=AnalysisExtractionAdapter(provider),
        )

        result = await runner.run(
            project_id=saved["project_id"],
            snapshot_id=saved["snapshot_id"],
            idempotency_key="analysis-run-1",
        )

        self.assertFalse(result.job_idempotent_replay)
        self.assertEqual(len(result.candidates), 2)
        self.assertEqual(result.candidate_idempotent_replays, (False, False))
        self.assertEqual(len(analysis_repo.jobs), 1)
        self.assertEqual(len(analysis_repo.tasks), 2)
        self.assertEqual(len(analysis_repo.candidates), 2)
        self.assertEqual(
            {candidate.candidate_type for candidate in result.candidates},
            {
                AnalysisCandidateType.CHARACTER_OBSERVATION,
                AnalysisCandidateType.EVENT_OBSERVATION,
            },
        )
        self.assertEqual(provider.requests[0].messages[-1].content, saved["raw_text"])

    async def test_runner_replays_same_job_tasks_and_candidates(self):
        saved = self._saved_source()
        analysis_service, analysis_repo, source_adapter = self._analysis(
            saved["core_sot"]
        )
        payload = self._content(
            [
                self._candidate(
                    "character_observation",
                    {"name": "민아", "observation": "민아가 편지를 발견했다."},
                    saved["anchors"]["min-a"],
                )
            ]
        )
        runner = AnalysisExtractionRunner(
            analysis_service=analysis_service,
            snapshot_loader=source_adapter,
            extractor=AnalysisExtractionAdapter(
                FakeLLMProvider(
                    [
                        GenerationResult(model="fake-gemma", content=payload, finish_reason="stop"),
                        GenerationResult(model="fake-gemma", content=payload, finish_reason="stop"),
                    ]
                )
            ),
        )

        first = await runner.run(
            project_id=saved["project_id"],
            snapshot_id=saved["snapshot_id"],
            idempotency_key="analysis-run-1",
        )
        replay = await runner.run(
            project_id=saved["project_id"],
            snapshot_id=saved["snapshot_id"],
            idempotency_key="analysis-run-1",
        )

        self.assertFalse(first.job_idempotent_replay)
        self.assertTrue(replay.job_idempotent_replay)
        self.assertEqual(replay.candidate_idempotent_replays, (True,))
        self.assertEqual(replay.job.id, first.job.id)
        self.assertEqual(replay.candidates[0].id, first.candidates[0].id)
        self.assertEqual(len(analysis_repo.jobs), 1)
        self.assertEqual(len(analysis_repo.tasks), 1)
        self.assertEqual(len(analysis_repo.candidates), 1)

    async def test_runner_preflights_all_drafts_before_candidate_writes(self):
        saved = self._saved_source()
        analysis_service, analysis_repo, source_adapter = self._analysis(
            saved["core_sot"]
        )
        bad_anchor = {
            **saved["anchors"]["letter"],
            "quote": "잘못된 인용",
        }
        runner = AnalysisExtractionRunner(
            analysis_service=analysis_service,
            snapshot_loader=source_adapter,
            extractor=AnalysisExtractionAdapter(
                FakeLLMProvider(
                    [
                        self._provider_result(
                            [
                                self._candidate(
                                    "character_observation",
                                    {
                                        "name": "민아",
                                        "observation": "민아가 편지를 발견했다.",
                                    },
                                    saved["anchors"]["min-a"],
                                ),
                                self._candidate(
                                    "event_observation",
                                    {"event": "민아가 편지를 발견했다."},
                                    bad_anchor,
                                ),
                            ]
                        )
                    ]
                )
            ),
        )

        with self.assertRaises(InvalidAnalysisCandidate):
            await runner.run(
                project_id=saved["project_id"],
                snapshot_id=saved["snapshot_id"],
                idempotency_key="analysis-run-1",
            )

        self.assertEqual(len(analysis_repo.candidates), 0)

    async def test_runner_preflights_logical_key_before_candidate_writes(self):
        saved = self._saved_source()
        analysis_service, analysis_repo, source_adapter = self._analysis(
            saved["core_sot"]
        )
        runner = AnalysisExtractionRunner(
            analysis_service=analysis_service,
            snapshot_loader=source_adapter,
            extractor=_StaticExtractor(
                (
                    self._draft(
                        logical_key="character:min-a",
                        source_anchor=saved["anchors"]["min-a"],
                    ),
                    self._draft(
                        logical_key="",
                        source_anchor=saved["anchors"]["min-a"],
                    ),
                )
            ),
        )

        with self.assertRaises(InvalidAnalysisCandidate):
            await runner.run(
                project_id=saved["project_id"],
                snapshot_id=saved["snapshot_id"],
                idempotency_key="analysis-run-1",
            )

        self.assertEqual(len(analysis_repo.candidates), 0)

    def _analysis(self, core_sot):
        repo = InMemoryAnalysisRepository()
        source_adapter = CoreSotSourceAdapter(core_sot)
        return (
            AnalysisService(repo, source_ref_resolver=source_adapter),
            repo,
            source_adapter,
        )

    def _saved_source(self):
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        project = core_sot.create_project(name="Novel")
        draft = core_sot.create_draft(project_id=project.id, title="Episode 1")
        raw_text = "민아는 파란 편지를 발견했다.\n\n다음 장면."
        saved = core_sot.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text=raw_text,
            idempotency_key="save-1",
        )
        min_a = self._source_ref(core_sot, project.id, saved.snapshot.id, raw_text, "민아")
        letter = self._source_ref(
            core_sot, project.id, saved.snapshot.id, raw_text, "편지"
        )
        return {
            "core_sot": core_sot,
            "project_id": project.id,
            "snapshot_id": saved.snapshot.id,
            "raw_text": raw_text,
            "anchors": {
                "min-a": self._anchor(min_a),
                "letter": self._anchor(letter),
            },
        }

    @staticmethod
    def _source_ref(core_sot, project_id, snapshot_id, raw_text, quote):
        start = raw_text.index(quote)
        return core_sot.create_source_ref(
            project_id=project_id,
            snapshot_id=snapshot_id,
            start_offset=start,
            end_offset=start + len(quote),
        )

    @staticmethod
    def _anchor(source_ref):
        return {
            "source_ref_id": source_ref.id,
            "start_offset": source_ref.start_offset,
            "end_offset": source_ref.end_offset,
            "quote": source_ref.quote,
            "content_hash": source_ref.content_hash,
        }

    @staticmethod
    def _candidate(candidate_type, payload, source_anchor):
        return {
            "candidate_type": candidate_type,
            "provenance": "source_observed",
            "confidence": 0.9,
            "source_anchors": [source_anchor],
            "payload": payload,
        }

    @staticmethod
    def _draft(logical_key, source_anchor):
        return AnalysisCandidateDraft(
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
            provenance=AnalysisProvenance.SOURCE_OBSERVED,
            confidence=0.9,
            source_anchors=(CandidateSourceAnchor(**source_anchor),),
            payload={"name": "민아", "observation": "민아가 편지를 발견했다."},
            logical_key=logical_key,
        )

    def _provider_result(self, candidates):
        return GenerationResult(
            model="fake-gemma",
            content=self._content(candidates),
            finish_reason="stop",
        )

    @staticmethod
    def _content(candidates):
        return json.dumps({"candidates": candidates}, ensure_ascii=False)

class _StaticExtractor:
    def __init__(self, drafts):
        self._drafts = drafts

    async def extract(self, _snapshot):
        return self._drafts


if __name__ == "__main__":
    unittest.main()
