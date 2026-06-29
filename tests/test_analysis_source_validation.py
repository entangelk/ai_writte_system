import unittest

from services.application.app.analysis.models import (
    AnalysisCandidateAction,
    AnalysisCandidateType,
    AnalysisProvenance,
    CandidateSourceAnchor,
)
from services.application.app.analysis.source import CoreSotSourceAdapter
from services.application.app.analysis.service import (
    AnalysisService,
    InMemoryAnalysisRepository,
    InvalidAnalysisCandidate,
)
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
    NotFound,
)


def _core_sot():
    repo = InMemoryCoreSotRepository()
    return CoreSotService(repo), repo


def _analysis(core_sot: CoreSotService):
    repo = InMemoryAnalysisRepository()
    adapter = CoreSotSourceAdapter(core_sot)
    return AnalysisService(repo, source_ref_resolver=adapter), adapter


class AnalysisSourceValidationTest(unittest.TestCase):
    def test_snapshot_loader_reads_raw_text_hash_and_blocks(self):
        core_sot, saved = self._saved_source()
        _analysis_service, source_adapter = _analysis(core_sot)

        loaded = source_adapter.load_snapshot(
            project_id=saved["project_id"],
            snapshot_id=saved["snapshot_id"],
        )

        self.assertEqual(loaded.project_id, saved["project_id"])
        self.assertEqual(loaded.snapshot_id, saved["snapshot_id"])
        self.assertEqual(loaded.raw_text, saved["raw_text"])
        self.assertEqual(loaded.content_hash, saved["content_hash"])
        self.assertEqual(loaded.block_ids, saved["block_ids"])

    def test_snapshot_loader_enforces_project_isolation(self):
        core_sot, saved = self._saved_source()
        other_project = core_sot.create_project(name="Other")
        _analysis_service, source_adapter = _analysis(core_sot)

        with self.assertRaises(NotFound):
            source_adapter.load_snapshot(
                project_id=other_project.id,
                snapshot_id=saved["snapshot_id"],
            )

    def test_record_candidate_validates_matching_source_anchor(self):
        core_sot, saved = self._saved_source()
        analysis_service, _source_adapter = _analysis(core_sot)
        task = self._task(analysis_service, saved)

        result = self._record(
            analysis_service,
            project_id=saved["project_id"],
            task_id=task.id,
            source_ref_id=saved["source_ref_id"],
            source_anchor=saved["source_anchor"],
        )

        self.assertFalse(result.idempotent_replay)
        self.assertEqual(result.candidate.source_ref_ids, (saved["source_ref_id"],))

    def test_record_candidate_rejects_cross_project_source_ref(self):
        core_sot, saved = self._saved_source()
        other_project = core_sot.create_project(name="Other")
        other_analysis, _source_adapter = _analysis(core_sot)
        job = other_analysis.create_job(
            project_id=other_project.id,
            snapshot_id=saved["snapshot_id"],
            idempotency_key="analysis-run-1",
        ).job
        task = other_analysis.create_task(
            project_id=other_project.id,
            job_id=job.id,
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
        )

        with self.assertRaises(InvalidAnalysisCandidate):
            self._record(
                other_analysis,
                project_id=other_project.id,
                task_id=task.id,
                source_ref_id=saved["source_ref_id"],
                source_anchor=saved["source_anchor"],
            )

    def test_record_candidate_rejects_quote_hash_and_span_mismatch(self):
        core_sot, saved = self._saved_source()
        analysis_service, _source_adapter = _analysis(core_sot)
        task = self._task(analysis_service, saved)

        cases = (
            ("quote", {"quote": "다른 인용"}),
            ("hash", {"content_hash": "bad-hash"}),
            ("start", {"start_offset": saved["source_anchor"].start_offset + 1}),
            ("end", {"end_offset": saved["source_anchor"].end_offset + 1}),
        )
        for name, overrides in cases:
            with self.subTest(mismatch=name):
                anchor = self._anchor_with(saved["source_anchor"], **overrides)
                with self.assertRaises(InvalidAnalysisCandidate):
                    self._record(
                        analysis_service,
                        project_id=saved["project_id"],
                        task_id=task.id,
                        logical_key=f"character:mismatch:{name}",
                        source_ref_id=saved["source_ref_id"],
                        source_anchor=anchor,
                    )

    def test_record_candidate_rejects_anchor_id_list_mismatch(self):
        core_sot, saved = self._saved_source()
        analysis_service, _source_adapter = _analysis(core_sot)
        task = self._task(analysis_service, saved)

        with self.assertRaises(InvalidAnalysisCandidate):
            self._record(
                analysis_service,
                project_id=saved["project_id"],
                task_id=task.id,
                source_ref_id="source-ref-different",
                source_anchor=saved["source_anchor"],
            )

    def test_record_candidate_requires_source_anchors_when_resolver_is_configured(self):
        core_sot, saved = self._saved_source()
        analysis_service, _source_adapter = _analysis(core_sot)
        task = self._task(analysis_service, saved)

        with self.assertRaises(InvalidAnalysisCandidate):
            analysis_service.record_candidate(
                project_id=saved["project_id"],
                task_id=task.id,
                logical_key="character:no-anchor",
                candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
                action=AnalysisCandidateAction.CREATE,
                provenance=AnalysisProvenance.SOURCE_OBSERVED,
                confidence=1.0,
                source_ref_ids=(saved["source_ref_id"],),
                payload={"name": "민아", "observation": "민아가 편지를 발견했다."},
            )

    def _saved_source(self):
        core_sot, _repo = _core_sot()
        project = core_sot.create_project(name="Novel")
        draft = core_sot.create_draft(project_id=project.id, title="Episode 1")
        raw_text = "민아는 파란 편지를 발견했다.\n\n다음 장면."
        saved = core_sot.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text=raw_text,
            idempotency_key="save-1",
        )
        start = raw_text.index("민아")
        end = start + len("민아")
        source_ref = core_sot.create_source_ref(
            project_id=project.id,
            snapshot_id=saved.snapshot.id,
            start_offset=start,
            end_offset=end,
        )
        return core_sot, {
            "project_id": project.id,
            "snapshot_id": saved.snapshot.id,
            "raw_text": raw_text,
            "content_hash": saved.snapshot.content_hash,
            "block_ids": tuple(block.id for block in saved.blocks),
            "source_ref_id": source_ref.id,
            "source_anchor": CandidateSourceAnchor(
                source_ref_id=source_ref.id,
                start_offset=source_ref.start_offset,
                end_offset=source_ref.end_offset,
                quote=source_ref.quote,
                content_hash=source_ref.content_hash,
            ),
        }

    def _task(self, analysis_service: AnalysisService, saved):
        job = analysis_service.create_job(
            project_id=saved["project_id"],
            snapshot_id=saved["snapshot_id"],
            idempotency_key="analysis-run-1",
        ).job
        return analysis_service.create_task(
            project_id=saved["project_id"],
            job_id=job.id,
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
        )

    def _record(
        self,
        analysis_service: AnalysisService,
        *,
        task_id: str,
        source_ref_id: str,
        source_anchor: CandidateSourceAnchor,
        project_id: str,
        logical_key="character:min-a",
    ):
        return analysis_service.record_candidate(
            project_id=project_id,
            task_id=task_id,
            logical_key=logical_key,
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
            action=AnalysisCandidateAction.CREATE,
            provenance=AnalysisProvenance.SOURCE_OBSERVED,
            confidence=1.0,
            source_ref_ids=(source_ref_id,),
            source_anchors=(source_anchor,),
            payload={"name": "민아", "observation": "민아가 편지를 발견했다."},
        )

    @staticmethod
    def _anchor_with(anchor: CandidateSourceAnchor, **overrides):
        values = {
            "source_ref_id": anchor.source_ref_id,
            "start_offset": anchor.start_offset,
            "end_offset": anchor.end_offset,
            "quote": anchor.quote,
            "content_hash": anchor.content_hash,
        }
        values.update(overrides)
        return CandidateSourceAnchor(**values)
