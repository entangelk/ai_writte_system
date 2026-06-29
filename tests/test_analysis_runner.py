import json
import unittest

from services.application.app.analysis.extractor import (
    AnalysisCandidateDraft,
    AnalysisExtractionAdapter,
)
from services.application.app.analysis.models import (
    AnalysisCandidateType,
    AnalysisJobFailureReason,
    AnalysisJobStatus,
    AnalysisProvenance,
    CandidateSourceAnchor,
)
from services.application.app.analysis.repository import (
    DuplicateAnalysisCandidateRequest,
)
from services.application.app.analysis.runner import AnalysisExtractionRunner
from services.application.app.analysis.runner import AnalysisRunnerConfigurationError
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
    def test_runner_requires_source_validating_analysis_service(self):
        saved = self._saved_source()

        with self.assertRaises(AnalysisRunnerConfigurationError):
            AnalysisExtractionRunner(
                analysis_service=AnalysisService(InMemoryAnalysisRepository()),
                snapshot_loader=CoreSotSourceAdapter(saved["core_sot"]),
                extractor=_StaticExtractor(()),
            )

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

    async def test_runner_dedupes_duplicate_logical_key_in_same_run_result(self):
        saved = self._saved_source()
        analysis_service, analysis_repo, source_adapter = self._analysis(
            saved["core_sot"]
        )
        draft = self._draft(
            logical_key="character:min-a",
            source_anchor=saved["anchors"]["min-a"],
        )
        runner = AnalysisExtractionRunner(
            analysis_service=analysis_service,
            snapshot_loader=source_adapter,
            extractor=_StaticExtractor((draft, draft)),
        )

        result = await runner.run(
            project_id=saved["project_id"],
            snapshot_id=saved["snapshot_id"],
            idempotency_key="analysis-run-1",
        )

        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidate_idempotent_replays, (False,))
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

    async def test_runner_marks_job_succeeded_on_success(self):
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
                )
            ),
        )

        result = await runner.run(
            project_id=saved["project_id"],
            snapshot_id=saved["snapshot_id"],
            idempotency_key="analysis-run-1",
        )

        self.assertEqual(result.job.status, AnalysisJobStatus.SUCCEEDED)
        self.assertIsNone(result.job.failure_reason)
        self.assertEqual(
            analysis_repo.get_job(result.job.id).status,
            AnalysisJobStatus.SUCCEEDED,
        )

    async def test_runner_replay_does_not_reexecute_extraction(self):
        saved = self._saved_source()
        analysis_service, analysis_repo, source_adapter = self._analysis(
            saved["core_sot"]
        )
        extractor = _CountingExtractor(
            (
                self._draft(
                    logical_key="character:min-a",
                    source_anchor=saved["anchors"]["min-a"],
                ),
            )
        )
        runner = AnalysisExtractionRunner(
            analysis_service=analysis_service,
            snapshot_loader=source_adapter,
            extractor=extractor,
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

        self.assertEqual(extractor.calls, 1)  # replay must not re-extract
        self.assertTrue(replay.job_idempotent_replay)
        self.assertEqual(replay.job.status, AnalysisJobStatus.SUCCEEDED)
        self.assertEqual(replay.candidate_idempotent_replays, (True,))
        self.assertEqual(replay.candidates[0].id, first.candidates[0].id)
        self.assertEqual(len(analysis_repo.candidates), 1)

    async def test_runner_marks_failed_snapshot_not_found(self):
        await self._assert_failed_reason(
            extractor=_StaticExtractor(()),
            snapshot_id="missing-snapshot",
            expected=AnalysisJobFailureReason.SNAPSHOT_NOT_FOUND,
        )

    async def test_runner_marks_failed_schema_invalid_on_malformed_provider(self):
        await self._assert_failed_reason(
            extractor=AnalysisExtractionAdapter(
                FakeLLMProvider(
                    [
                        GenerationResult(
                            model="fake-gemma",
                            content="not json",
                            finish_reason="stop",
                        )
                    ]
                )
            ),
            expected=AnalysisJobFailureReason.SCHEMA_INVALID,
        )

    async def test_runner_marks_failed_source_invalid_on_anchor_mismatch(self):
        saved = self._saved_source()
        bad_anchor = {**saved["anchors"]["min-a"], "quote": "잘못된 인용"}
        await self._assert_failed_reason(
            saved=saved,
            extractor=_StaticExtractor(
                (self._draft(logical_key="character:min-a", source_anchor=bad_anchor),)
            ),
            expected=AnalysisJobFailureReason.SOURCE_INVALID,
        )

    async def test_runner_marks_failed_provider_error_on_extract_exception(self):
        await self._assert_failed_reason(
            extractor=_RaisingExtractor(RuntimeError("gateway down")),
            expected=AnalysisJobFailureReason.PROVIDER_ERROR,
            expected_exc=RuntimeError,
        )

    async def test_runner_marks_failed_duplicate_conflict_on_storage_duplicate(self):
        saved = self._saved_source()
        repo = _DuplicateOnWriteRepo()
        source_adapter = CoreSotSourceAdapter(saved["core_sot"])
        analysis_service = AnalysisService(repo, source_ref_resolver=source_adapter)
        runner = AnalysisExtractionRunner(
            analysis_service=analysis_service,
            snapshot_loader=source_adapter,
            extractor=_StaticExtractor(
                (
                    self._draft(
                        logical_key="character:min-a",
                        source_anchor=saved["anchors"]["min-a"],
                    ),
                )
            ),
        )

        with self.assertRaises(DuplicateAnalysisCandidateRequest):
            await runner.run(
                project_id=saved["project_id"],
                snapshot_id=saved["snapshot_id"],
                idempotency_key="analysis-run-1",
            )

        job = next(iter(repo.jobs.values()))
        self.assertEqual(job.status, AnalysisJobStatus.FAILED)
        self.assertEqual(
            job.failure_reason, AnalysisJobFailureReason.DUPLICATE_CONFLICT
        )
        self.assertEqual(len(repo.candidates), 0)

    async def _assert_failed_reason(
        self,
        *,
        extractor,
        expected,
        saved=None,
        snapshot_id=None,
        expected_exc=Exception,
    ):
        saved = saved or self._saved_source()
        analysis_service, analysis_repo, source_adapter = self._analysis(
            saved["core_sot"]
        )
        runner = AnalysisExtractionRunner(
            analysis_service=analysis_service,
            snapshot_loader=source_adapter,
            extractor=extractor,
        )

        with self.assertRaises(expected_exc):
            await runner.run(
                project_id=saved["project_id"],
                snapshot_id=snapshot_id or saved["snapshot_id"],
                idempotency_key="analysis-run-1",
            )

        job = next(iter(analysis_repo.jobs.values()))
        self.assertEqual(job.status, AnalysisJobStatus.FAILED)
        self.assertEqual(job.failure_reason, expected)
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


class _CountingExtractor:
    def __init__(self, drafts):
        self._drafts = drafts
        self.calls = 0

    async def extract(self, _snapshot):
        self.calls += 1
        return self._drafts


class _RaisingExtractor:
    def __init__(self, error):
        self._error = error

    async def extract(self, _snapshot):
        raise self._error


class _DuplicateOnWriteRepo(InMemoryAnalysisRepository):
    def put_candidates(self, candidates):
        raise DuplicateAnalysisCandidateRequest("duplicate candidate request")


if __name__ == "__main__":
    unittest.main()
