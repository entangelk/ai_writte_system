"""Infrastructure-free Phase 2A analysis service."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from numbers import Real
from typing import Any

from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisJob,
    AnalysisProvenance,
    AnalysisTask,
    CandidateSourceAnchor,
    CreateAnalysisJobResult,
    RecordAnalysisCandidateResult,
    immutable_payload,
)
from services.application.app.analysis.repository import AnalysisRepository
from services.application.app.analysis.schema import (
    InvalidAnalysisPayload,
    validate_candidate_payload,
)
from services.application.app.analysis.source import SourceRefResolver


class AnalysisError(ValueError):
    pass


class AnalysisNotFound(AnalysisError):
    pass


class InvalidAnalysisCandidate(AnalysisError):
    pass


class InMemoryAnalysisRepository:
    def __init__(self) -> None:
        self._job_seq = 0
        self._task_seq = 0
        self._candidate_seq = 0
        self.jobs: dict[str, AnalysisJob] = {}
        self.tasks: dict[str, AnalysisTask] = {}
        self.candidates: dict[str, AnalysisCandidate] = {}
        self._job_request_index: dict[tuple[str, str, str], str] = {}
        self._candidate_request_index: dict[tuple[str, str, str], str] = {}

    def next_job_id(self) -> str:
        self._job_seq += 1
        return f"analysis-job-{self._job_seq}"

    def next_task_id(self) -> str:
        self._task_seq += 1
        return f"analysis-task-{self._task_seq}"

    def next_candidate_id(self) -> str:
        self._candidate_seq += 1
        return f"analysis-candidate-{self._candidate_seq}"

    def get_job(self, job_id: str) -> AnalysisJob | None:
        return self.jobs.get(job_id)

    def find_job_request(
        self, project_id: str, snapshot_id: str, idempotency_key: str
    ) -> str | None:
        return self._job_request_index.get((project_id, snapshot_id, idempotency_key))

    def put_job(self, job: AnalysisJob) -> None:
        self.jobs[job.id] = job
        self._job_request_index[
            (job.project_id, job.snapshot_id, job.idempotency_key)
        ] = job.id

    def get_task(self, task_id: str) -> AnalysisTask | None:
        return self.tasks.get(task_id)

    def put_task(self, task: AnalysisTask) -> None:
        self.tasks[task.id] = task

    def get_candidate(self, candidate_id: str) -> AnalysisCandidate | None:
        return self.candidates.get(candidate_id)

    def find_candidate_request(
        self, project_id: str, task_id: str, logical_key: str
    ) -> str | None:
        return self._candidate_request_index.get((project_id, task_id, logical_key))

    def put_candidate(
        self, candidate: AnalysisCandidate, *, logical_key: str
    ) -> None:
        self.candidates[candidate.id] = candidate
        self._candidate_request_index[
            (candidate.project_id, candidate.task_id, logical_key)
        ] = candidate.id

    def list_candidates_for_job(
        self, project_id: str, job_id: str
    ) -> tuple[AnalysisCandidate, ...]:
        return tuple(
            candidate
            for candidate in self.candidates.values()
            if candidate.project_id == project_id and candidate.job_id == job_id
        )


class AnalysisService:
    def __init__(
        self,
        repository: AnalysisRepository,
        *,
        source_ref_resolver: SourceRefResolver | None = None,
    ) -> None:
        self._repo = repository
        self._source_ref_resolver = source_ref_resolver

    def create_job(
        self, *, project_id: str, snapshot_id: str, idempotency_key: str
    ) -> CreateAnalysisJobResult:
        if not idempotency_key:
            raise AnalysisError("idempotency_key is required")
        existing_job_id = self._repo.find_job_request(
            project_id, snapshot_id, idempotency_key
        )
        if existing_job_id is not None:
            return CreateAnalysisJobResult(
                job=self._require_job(project_id, existing_job_id),
                idempotent_replay=True,
            )

        job = AnalysisJob(
            id=self._repo.next_job_id(),
            project_id=project_id,
            snapshot_id=snapshot_id,
            idempotency_key=idempotency_key,
        )
        self._repo.put_job(job)
        return CreateAnalysisJobResult(job=job, idempotent_replay=False)

    def create_task(
        self,
        *,
        project_id: str,
        job_id: str,
        candidate_type: AnalysisCandidateType,
    ) -> AnalysisTask:
        job = self._require_job(project_id, job_id)
        self._validate_candidate_type(candidate_type)
        task = AnalysisTask(
            id=self._repo.next_task_id(),
            project_id=project_id,
            job_id=job.id,
            candidate_type=candidate_type,
        )
        self._repo.put_task(task)
        return task

    def record_candidate(
        self,
        *,
        project_id: str,
        task_id: str,
        logical_key: str,
        candidate_type: AnalysisCandidateType,
        action: AnalysisCandidateAction,
        provenance: AnalysisProvenance,
        confidence: float,
        source_ref_ids: Sequence[str],
        payload: Mapping[str, Any],
        source_anchors: Sequence[CandidateSourceAnchor] | None = None,
    ) -> RecordAnalysisCandidateResult:
        self._validate_logical_key(logical_key)
        task = self._require_task(project_id, task_id)
        self._validate_candidate_type(candidate_type)
        self._validate_action(action)
        self._validate_provenance(provenance)
        if candidate_type != task.candidate_type:
            raise InvalidAnalysisCandidate("candidate_type must match task")
        normalized_payload = self._validate_payload(candidate_type, payload)
        normalized_confidence = self._validate_confidence(confidence)
        normalized_source_ref_ids = self._validate_source_ref_ids(source_ref_ids)
        if self._source_ref_resolver is not None and source_anchors is None:
            raise InvalidAnalysisCandidate("source_anchors are required")
        if source_anchors is not None:
            anchor_source_ref_ids = self._validate_source_anchors(
                project_id=project_id,
                source_anchors=source_anchors,
            )
            if anchor_source_ref_ids != normalized_source_ref_ids:
                raise InvalidAnalysisCandidate(
                    "source_anchors must match source_ref_ids"
                )

        existing_candidate_id = self._repo.find_candidate_request(
            project_id, task_id, logical_key
        )
        if existing_candidate_id is not None:
            return RecordAnalysisCandidateResult(
                candidate=self._require_candidate(project_id, existing_candidate_id),
                idempotent_replay=True,
            )

        candidate = AnalysisCandidate(
            id=self._repo.next_candidate_id(),
            project_id=project_id,
            job_id=task.job_id,
            task_id=task.id,
            candidate_type=candidate_type,
            action=AnalysisCandidateAction.CREATE,
            status=AnalysisCandidateStatus.NEEDS_REVIEW,
            provenance=provenance,
            confidence=normalized_confidence,
            source_ref_ids=normalized_source_ref_ids,
            payload=immutable_payload(normalized_payload),
        )
        self._repo.put_candidate(candidate, logical_key=logical_key)
        return RecordAnalysisCandidateResult(
            candidate=candidate,
            idempotent_replay=False,
        )

    def list_candidates(
        self, *, project_id: str, job_id: str
    ) -> tuple[AnalysisCandidate, ...]:
        self._require_job(project_id, job_id)
        return self._repo.list_candidates_for_job(project_id, job_id)

    def _require_job(self, project_id: str, job_id: str) -> AnalysisJob:
        job = self._repo.get_job(job_id)
        if job is None or job.project_id != project_id:
            raise AnalysisNotFound("analysis job not found")
        return job

    def _require_task(self, project_id: str, task_id: str) -> AnalysisTask:
        task = self._repo.get_task(task_id)
        if task is None or task.project_id != project_id:
            raise AnalysisNotFound("analysis task not found")
        self._require_job(project_id, task.job_id)
        return task

    def _require_candidate(
        self, project_id: str, candidate_id: str
    ) -> AnalysisCandidate:
        candidate = self._repo.get_candidate(candidate_id)
        if candidate is None or candidate.project_id != project_id:
            raise AnalysisNotFound("analysis candidate not found")
        return candidate

    @staticmethod
    def _validate_confidence(confidence: float) -> float:
        if isinstance(confidence, bool) or not isinstance(confidence, Real):
            raise InvalidAnalysisCandidate("confidence must be a number")
        normalized = float(confidence)
        if not (0.0 <= normalized <= 1.0):
            raise InvalidAnalysisCandidate("confidence must be between 0.0 and 1.0")
        return normalized

    @staticmethod
    def _validate_source_ref_ids(source_ref_ids: Sequence[str]) -> tuple[str, ...]:
        if isinstance(source_ref_ids, (str, bytes)) or not source_ref_ids:
            raise InvalidAnalysisCandidate("source_ref_ids are required")
        normalized = tuple(source_ref_ids)
        if any(
            not isinstance(source_ref_id, str) or not source_ref_id
            for source_ref_id in normalized
        ):
            raise InvalidAnalysisCandidate("source_ref_ids must be non-empty strings")
        return normalized

    def _validate_source_anchors(
        self,
        *,
        project_id: str,
        source_anchors: Sequence[CandidateSourceAnchor],
    ) -> tuple[str, ...]:
        if self._source_ref_resolver is None:
            raise InvalidAnalysisCandidate("source_ref resolver is required")
        if isinstance(source_anchors, (str, bytes)) or not source_anchors:
            raise InvalidAnalysisCandidate("source_anchors are required")

        source_ref_ids: list[str] = []
        for anchor in source_anchors:
            if not isinstance(anchor, CandidateSourceAnchor):
                raise InvalidAnalysisCandidate("invalid source anchor")
            source_ref = self._source_ref_resolver.get_source_ref(
                project_id=project_id,
                source_ref_id=anchor.source_ref_id,
            )
            if source_ref is None:
                raise InvalidAnalysisCandidate("source_ref not found")
            if (
                source_ref.project_id != project_id
                or source_ref.start_offset != anchor.start_offset
                or source_ref.end_offset != anchor.end_offset
                or source_ref.quote != anchor.quote
                or source_ref.content_hash != anchor.content_hash
            ):
                raise InvalidAnalysisCandidate("source_ref anchor mismatch")
            source_ref_ids.append(anchor.source_ref_id)
        return tuple(source_ref_ids)

    @staticmethod
    def _validate_candidate_type(candidate_type: AnalysisCandidateType) -> None:
        if not isinstance(candidate_type, AnalysisCandidateType):
            raise InvalidAnalysisCandidate("unsupported analysis candidate type")

    @staticmethod
    def _validate_action(action: AnalysisCandidateAction) -> None:
        if action is not AnalysisCandidateAction.CREATE:
            raise InvalidAnalysisCandidate("Phase 2A only supports create")

    @staticmethod
    def _validate_provenance(provenance: AnalysisProvenance) -> None:
        if not isinstance(provenance, AnalysisProvenance):
            raise InvalidAnalysisCandidate("unsupported analysis provenance")

    @staticmethod
    def _validate_payload(
        candidate_type: AnalysisCandidateType,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        try:
            return validate_candidate_payload(candidate_type, payload)
        except InvalidAnalysisPayload as exc:
            raise InvalidAnalysisCandidate(str(exc)) from exc

    @staticmethod
    def _validate_logical_key(logical_key: str) -> None:
        if not isinstance(logical_key, str) or not logical_key:
            raise InvalidAnalysisCandidate("logical_key is required")
