"""Phase 2A snapshot extraction orchestration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from services.application.app.analysis.extractor import (
    AnalysisCandidateDraft,
    AnalysisExtractionError,
)
from services.application.app.analysis.identity_judging import (
    DEFAULT_MAX_NEW_RELATIONS_PER_RUN,
    CandidateIdentityJudgingService,
    InvalidIdentityJudgement,
    JudgingBudget,
)
from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateRecordRequest,
    AnalysisJob,
    AnalysisJobFailureReason,
    AnalysisJobStatus,
    RecordAnalysisCandidateResult,
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
from services.application.app.observability.llm_call_scope import current_scope


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
        identity_judging: CandidateIdentityJudgingService | None = None,
    ) -> None:
        if not analysis_service.source_validation_enabled:
            raise AnalysisRunnerConfigurationError(
                "AnalysisExtractionRunner requires source validation"
            )
        self._analysis_service = analysis_service
        self._snapshot_loader = snapshot_loader
        self._extractor = extractor
        self._identity_judging = identity_judging

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
        await self._judge_candidate_identities(
            project_id=project_id, recorded=recorded
        )
        return AnalysisExtractionRunResult(
            job=succeeded,
            candidates=tuple(result.candidate for result in recorded),
            job_idempotent_replay=False,
            candidate_idempotent_replays=tuple(
                result.idempotent_replay for result in recorded
            ),
        )

    async def _judge_candidate_identities(
        self, *, project_id: str, recorded: tuple[RecordAnalysisCandidateResult, ...]
    ) -> None:
        """Slice 2 (identity grouping): link the job's fresh candidates.

        Runs only on the success path — the failure ``try`` above re-raises
        before this point, so a save failure or job failure never attempts
        judging, and the job is already terminal(succeeded) when this runs,
        which is what makes the isolation structural. Plan Slice 2: a judging
        failure must not fail the job; candidates stay ``needs_review``.
        The whole phase is one isolation boundary and the first failure ends
        it — a down gateway would otherwise burn one timeout per remaining
        pair for nothing. Partially applied phases self-heal on re-runs
        (Slice 1: stored relations are reused, group links re-applied —
        the B3 closure cell is the trust basis).
        """
        if self._identity_judging is None:
            return
        try:
            # S-1 D3(오너 2026-09-05): run 하나가 새로 판정하는 pair 의 상한 —
            # 같은 예산을 후보마다 넘기므로 상한이 run 단위로 걸린다. 넘친 쌍은
            # relation 이 없는 채로 남아 다음 run 이 이어받는다(이월).
            budget = JudgingBudget(DEFAULT_MAX_NEW_RELATIONS_PER_RUN)
            for result in recorded:
                await self._identity_judging.judge_candidate(
                    project_id=project_id,
                    candidate_id=result.candidate.id,
                    budget=budget,
                )
        except InvalidIdentityJudgement as exc:
            # D4 (owner decision 2026-07-26, compare endpoint's branch): the
            # judge answered and repair still failed to parse — the domain's
            # final rejection of that last answer. The outcome guard inside
            # reclassify keeps a provider_error row untouched; with no scope
            # open (direct service use) there is nothing to annotate.
            scope = current_scope()
            if scope is not None:
                scope.reclassify_last_as_parse_error(type(exc).__name__)
        except Exception:  # noqa: BLE001 — deliberate isolation boundary
            pass

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
