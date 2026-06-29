"""Phase 2A snapshot extraction orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from services.application.app.analysis.extractor import AnalysisCandidateDraft
from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateRecordRequest,
    AnalysisJob,
    SnapshotText,
)
from services.application.app.analysis.service import AnalysisService
from services.application.app.analysis.source import SnapshotLoader


class CandidateExtractor(Protocol):
    async def extract(self, snapshot: SnapshotText) -> tuple[AnalysisCandidateDraft, ...]:
        ...


class AnalysisRunnerConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AnalysisExtractionRunResult:
    job: AnalysisJob
    candidates: tuple[AnalysisCandidate, ...]
    job_idempotent_replay: bool
    candidate_idempotent_replays: tuple[bool, ...]


@dataclass(frozen=True, slots=True)
class _PreparedDraft:
    draft: AnalysisCandidateDraft
    task_id: str


class AnalysisExtractionRunner:
    def __init__(
        self,
        *,
        analysis_service: AnalysisService,
        snapshot_loader: SnapshotLoader,
        extractor: CandidateExtractor,
    ) -> None:
        if not analysis_service.source_validation_enabled:
            raise AnalysisRunnerConfigurationError(
                "AnalysisExtractionRunner requires source validation"
            )
        self._analysis_service = analysis_service
        self._snapshot_loader = snapshot_loader
        self._extractor = extractor

    async def run(
        self,
        *,
        project_id: str,
        snapshot_id: str,
        idempotency_key: str,
    ) -> AnalysisExtractionRunResult:
        job_result = self._analysis_service.create_job(
            project_id=project_id,
            snapshot_id=snapshot_id,
            idempotency_key=idempotency_key,
        )
        snapshot = self._snapshot_loader.load_snapshot(
            project_id=project_id,
            snapshot_id=snapshot_id,
        )
        drafts = await self._extractor.extract(snapshot)
        prepared = self._dedupe_prepared(
            tuple(
                self._prepare_draft(
                    project_id=project_id,
                    job_id=job_result.job.id,
                    draft=draft,
                )
                for draft in drafts
            )
        )

        # Preflight every draft before writing any candidate. Job/task creation is
        # idempotent setup; candidate persistence remains all-or-nothing here.
        for item in prepared:
            self._validate_draft(project_id=project_id, item=item)

        recorded = self._analysis_service.record_candidates(
            project_id=project_id,
            requests=tuple(self._record_request(item) for item in prepared),
        )
        return AnalysisExtractionRunResult(
            job=job_result.job,
            candidates=tuple(result.candidate for result in recorded),
            job_idempotent_replay=job_result.idempotent_replay,
            candidate_idempotent_replays=tuple(
                result.idempotent_replay for result in recorded
            ),
        )

    def _prepare_draft(
        self,
        *,
        project_id: str,
        job_id: str,
        draft: AnalysisCandidateDraft,
    ) -> _PreparedDraft:
        task = self._analysis_service.create_task(
            project_id=project_id,
            job_id=job_id,
            candidate_type=draft.candidate_type,
        )
        return _PreparedDraft(draft=draft, task_id=task.id)

    def _validate_draft(self, *, project_id: str, item: _PreparedDraft) -> None:
        draft = item.draft
        self._analysis_service.validate_candidate(
            project_id=project_id,
            task_id=item.task_id,
            logical_key=draft.logical_key,
            candidate_type=draft.candidate_type,
            action=AnalysisCandidateAction.CREATE,
            provenance=draft.provenance,
            confidence=draft.confidence,
            source_ref_ids=tuple(anchor.source_ref_id for anchor in draft.source_anchors),
            payload=draft.payload,
            source_anchors=draft.source_anchors,
        )

    @staticmethod
    def _record_request(item: _PreparedDraft) -> AnalysisCandidateRecordRequest:
        draft = item.draft
        return AnalysisCandidateRecordRequest(
            task_id=item.task_id,
            logical_key=draft.logical_key,
            candidate_type=draft.candidate_type,
            action=AnalysisCandidateAction.CREATE,
            provenance=draft.provenance,
            confidence=draft.confidence,
            source_ref_ids=tuple(anchor.source_ref_id for anchor in draft.source_anchors),
            payload=draft.payload,
            source_anchors=draft.source_anchors,
        )

    @staticmethod
    def _dedupe_prepared(
        prepared: tuple[_PreparedDraft, ...],
    ) -> tuple[_PreparedDraft, ...]:
        unique: dict[tuple[str, str], _PreparedDraft] = {}
        for item in prepared:
            unique.setdefault((item.task_id, item.draft.logical_key), item)
        return tuple(unique.values())
