"""Phase 2A snapshot extraction orchestration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from services.application.app.analysis.extractor import (
    AnalysisCandidateDraft,
    AnalysisExtractionError,
)
from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateRecordRequest,
    AnalysisJob,
    AnalysisJobFailureReason,
    AnalysisJobStatus,
    SnapshotText,
)
from services.application.app.analysis.repository import (
    DuplicateAnalysisCandidateRequest,
)
from services.application.app.analysis.service import (
    AnalysisService,
    InvalidAnalysisCandidate,
    InvalidCandidateSource,
)
from services.application.app.analysis.source import SnapshotLoader
from services.application.app.core_sot.service import NotFound


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
        if job_result.idempotent_replay:
            # Existing job (any state) is a replay: never re-run. Return the
            # already-stored candidates as-is.
            stored = self._analysis_service.list_candidates(
                project_id=project_id, job_id=job_result.job.id
            )
            return AnalysisExtractionRunResult(
                job=job_result.job,
                candidates=stored,
                job_idempotent_replay=True,
                candidate_idempotent_replays=tuple(True for _ in stored),
            )

        return await self._execute_pending_job(job_result.job)

    async def run_job(
        self,
        *,
        project_id: str,
        job_id: str,
    ) -> AnalysisExtractionRunResult:
        job = self._analysis_service.get_job(project_id=project_id, job_id=job_id)
        if job.status is not AnalysisJobStatus.PENDING:
            stored = self._analysis_service.list_candidates(
                project_id=project_id, job_id=job.id
            )
            return AnalysisExtractionRunResult(
                job=job,
                candidates=stored,
                job_idempotent_replay=True,
                candidate_idempotent_replays=tuple(True for _ in stored),
            )

        return await self._execute_pending_job(job)

    async def _execute_pending_job(
        self, job: AnalysisJob
    ) -> AnalysisExtractionRunResult:
        project_id = job.project_id
        snapshot_id = job.snapshot_id
        job_id = job.id
        self._analysis_service.mark_job_running(
            project_id=project_id, job_id=job_id
        )
        try:
            snapshot = self._snapshot_loader.load_snapshot(
                project_id=project_id,
                snapshot_id=snapshot_id,
            )
            if job.writing_candidate_report is not None:
                snapshot = replace(
                    snapshot,
                    writing_candidate_report=job.writing_candidate_report)
            drafts = await self._extractor.extract(snapshot)
            prepared = self._dedupe_prepared(
                tuple(
                    self._prepare_draft(
                        project_id=project_id,
                        job_id=job_id,
                        draft=draft,
                    )
                    for draft in drafts
                )
            )

            # Preflight every draft before writing any candidate. Job/task
            # creation is idempotent setup; candidate persistence stays
            # all-or-nothing here.
            for item in prepared:
                self._validate_draft(project_id=project_id, item=item)

            recorded = self._analysis_service.record_candidates(
                project_id=project_id,
                requests=tuple(self._record_request(item) for item in prepared),
            )
        except Exception as exc:
            self._analysis_service.mark_job_failed(
                project_id=project_id,
                job_id=job_id,
                failure_reason=self._failure_reason(exc),
                failure_detail=str(exc),
            )
            raise

        succeeded = self._analysis_service.mark_job_succeeded(
            project_id=project_id, job_id=job_id
        )
        return AnalysisExtractionRunResult(
            job=succeeded,
            candidates=tuple(result.candidate for result in recorded),
            job_idempotent_replay=False,
            candidate_idempotent_replays=tuple(
                result.idempotent_replay for result in recorded
            ),
        )

    @staticmethod
    def _failure_reason(exc: Exception) -> AnalysisJobFailureReason:
        # Map each runner failure point to its closed failure_reason. Order
        # matters: InvalidCandidateSource is a subclass of InvalidAnalysisCandidate.
        if isinstance(exc, NotFound):
            return AnalysisJobFailureReason.SNAPSHOT_NOT_FOUND
        if isinstance(exc, AnalysisExtractionError):
            return AnalysisJobFailureReason.SCHEMA_INVALID
        if isinstance(exc, InvalidCandidateSource):
            return AnalysisJobFailureReason.SOURCE_INVALID
        if isinstance(exc, InvalidAnalysisCandidate):
            return AnalysisJobFailureReason.SCHEMA_INVALID
        if isinstance(exc, DuplicateAnalysisCandidateRequest):
            return AnalysisJobFailureReason.DUPLICATE_CONFLICT
        return AnalysisJobFailureReason.PROVIDER_ERROR

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
