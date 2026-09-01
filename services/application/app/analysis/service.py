"""Infrastructure-free Phase 2A analysis service."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from numbers import Real
from typing import Any, Protocol

from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateRecordRequest,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisJob,
    AnalysisJobFailureReason,
    AnalysisJobStatus,
    AnalysisProvenance,
    AnalysisTask,
    CandidateSourceAnchor,
    CreateAnalysisJobResult,
    RecordAnalysisCandidateResult,
    immutable_payload,
)
from services.application.app.analysis.repository import (
    AnalysisRepository,
    DuplicateAnalysisCandidateRequest,
)
from services.application.app.analysis.schema import (
    InvalidAnalysisPayload,
    validate_candidate_payload,
)
from services.application.app.analysis.source import SourceRefResolver


class CandidateReindexOutbox(Protocol):
    """b-2: enqueue a candidate index sync when a needs_review candidate is
    recorded. Structural type (defined here, not imported from ``indexing``) so
    the analysis service stays free of an indexing dependency — mirror of
    memory.service.MemoryReindexOutbox."""

    def enqueue_candidate_upserted(
        self, *, project_id: str, candidate_id: str
    ) -> object: ...

    def enqueue_candidate_removed(
        self, *, project_id: str, candidate_id: str
    ) -> object: ...


class AnalysisError(ValueError):
    pass


class AnalysisNotFound(AnalysisError):
    pass


class InvalidAnalysisCandidate(AnalysisError):
    pass


class InvalidCandidateSource(InvalidAnalysisCandidate):
    """Candidate rejected for a source_ref/anchor problem (vs payload schema)."""


class InvalidJobStateTransition(AnalysisError):
    pass


class InvalidCandidateStateTransition(AnalysisError):
    """A candidate status transition is not one of the legal edges (Phase 6)."""


@dataclass(frozen=True, slots=True)
class CandidateTransition:
    candidate: AnalysisCandidate
    changed: bool


@dataclass(frozen=True, slots=True)
class CandidateEdit:
    """Phase 6 candidate edit (v1.6.66): the confirmed successor version minted
    from a reviewer's payload correction. ``idempotent_replay`` is True when the
    original had already been edited (the successor is returned unchanged)."""

    candidate: AnalysisCandidate
    idempotent_replay: bool


# Phase 6 (v1.6.61): a needs_review candidate is confirmed or rejected. Both are
# terminal — there is no path back to needs_review or across to the other
# terminal (that would silently overturn a review).
_ALLOWED_CANDIDATE_TRANSITIONS: frozenset[
    tuple[AnalysisCandidateStatus, AnalysisCandidateStatus]
] = frozenset(
    {
        (AnalysisCandidateStatus.NEEDS_REVIEW, AnalysisCandidateStatus.CONFIRMED),
        (AnalysisCandidateStatus.NEEDS_REVIEW, AnalysisCandidateStatus.REJECTED),
    }
)


_ALLOWED_JOB_TRANSITIONS: frozenset[tuple[AnalysisJobStatus, AnalysisJobStatus]] = (
    frozenset(
        {
            (AnalysisJobStatus.PENDING, AnalysisJobStatus.RUNNING),
            (AnalysisJobStatus.RUNNING, AnalysisJobStatus.SUCCEEDED),
            (AnalysisJobStatus.RUNNING, AnalysisJobStatus.FAILED),
            (AnalysisJobStatus.FAILED, AnalysisJobStatus.PENDING),
        }
    )
)


_PreparedCandidateRecord = tuple[
    AnalysisCandidateRecordRequest,
    AnalysisTask,
    Mapping[str, Any],
    float,
    tuple[str, ...],
]


class InMemoryAnalysisRepository:
    def __init__(self) -> None:
        self._job_seq = 0
        self._task_seq = 0
        self._candidate_seq = 0
        self.jobs: dict[str, AnalysisJob] = {}
        self.tasks: dict[str, AnalysisTask] = {}
        self.candidates: dict[str, AnalysisCandidate] = {}
        self._job_request_index: dict[tuple[str, str, str], str] = {}
        self._task_request_index: dict[tuple[str, str, AnalysisCandidateType], str] = {}
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

    def update_job(self, job: AnalysisJob) -> None:
        self.jobs[job.id] = job

    def get_task(self, task_id: str) -> AnalysisTask | None:
        return self.tasks.get(task_id)

    def find_task_request(
        self, project_id: str, job_id: str, candidate_type: AnalysisCandidateType
    ) -> str | None:
        return self._task_request_index.get((project_id, job_id, candidate_type))

    def put_task(self, task: AnalysisTask) -> None:
        self.tasks[task.id] = task
        self._task_request_index[
            (task.project_id, task.job_id, task.candidate_type)
        ] = task.id

    def get_candidate(self, candidate_id: str) -> AnalysisCandidate | None:
        return self.candidates.get(candidate_id)

    def find_candidate_request(
        self, project_id: str, task_id: str, logical_key: str
    ) -> str | None:
        return self._candidate_request_index.get((project_id, task_id, logical_key))

    def put_candidate(
        self, candidate: AnalysisCandidate, *, logical_key: str
    ) -> None:
        self.put_candidates(((candidate, logical_key),))

    def put_candidates(
        self, candidates: Sequence[tuple[AnalysisCandidate, str]]
    ) -> None:
        next_candidates = dict(self.candidates)
        next_candidate_index = dict(self._candidate_request_index)
        for candidate, logical_key in candidates:
            next_candidates[candidate.id] = candidate
            next_candidate_index[
                (candidate.project_id, candidate.task_id, logical_key)
            ] = candidate.id
        self.candidates = next_candidates
        self._candidate_request_index = next_candidate_index

    def update_candidate(self, candidate: AnalysisCandidate) -> None:
        # Phase 6 status transition: replace the stored candidate in place
        # (mirrors update_job). The request index is keyed on logical_key, which
        # a status transition does not change, so it stays intact.
        self.candidates = {**self.candidates, candidate.id: candidate}

    def list_candidates_for_job(
        self, project_id: str, job_id: str
    ) -> tuple[AnalysisCandidate, ...]:
        return tuple(
            candidate
            for candidate in self.candidates.values()
            if candidate.project_id == project_id and candidate.job_id == job_id
        )

    def list_needs_review_candidates(
        self, project_id: str
    ) -> tuple[AnalysisCandidate, ...]:
        return tuple(
            candidate
            for candidate in self.candidates.values()
            if candidate.project_id == project_id
            and candidate.status is AnalysisCandidateStatus.NEEDS_REVIEW
        )

    def purge_project(self, project_id: str) -> None:
        # D8-6b: project 의 analysis 그래프(jobs·tasks·candidates) 전부 파기(직접 project_id 스코프).
        self.jobs = {jid: j for jid, j in self.jobs.items() if j.project_id != project_id}
        self.tasks = {tid: t for tid, t in self.tasks.items() if t.project_id != project_id}
        self.candidates = {cid: c for cid, c in self.candidates.items() if c.project_id != project_id}
        self._job_request_index = {k: v for k, v in self._job_request_index.items() if k[0] != project_id}
        self._task_request_index = {k: v for k, v in self._task_request_index.items() if k[0] != project_id}
        self._candidate_request_index = {k: v for k, v in self._candidate_request_index.items() if k[0] != project_id}


class AnalysisService:
    def __init__(
        self,
        repository: AnalysisRepository,
        *,
        source_ref_resolver: SourceRefResolver | None = None,
        reindex_outbox: CandidateReindexOutbox | None = None,
    ) -> None:
        self._repo = repository
        self._source_ref_resolver = source_ref_resolver
        # b-2: recording a needs_review candidate enqueues a CANDIDATE_UPSERTED
        # index sync here, so no extraction path can forget to index. Absent
        # (unwired) leaves the deterministic Mongo-direct retrieval intact.
        self._reindex_outbox = reindex_outbox

    def purge_project(self, *, project_id: str) -> None:
        # D8-6b: project 전체 파기의 analysis 다리. endpoint(D8-6d)가 core_sot 파기와 함께 호출한다.
        self._repo.purge_project(project_id)

    @property
    def source_validation_enabled(self) -> bool:
        return self._source_ref_resolver is not None

    def create_job(
        self, *, project_id: str, snapshot_id: str, idempotency_key: str,
        writing_candidate_report: Mapping[str, Any] | None = None,
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
            writing_candidate_report=(
                immutable_payload(writing_candidate_report)
                if writing_candidate_report is not None else None),
        )
        self._repo.put_job(job)
        return CreateAnalysisJobResult(job=job, idempotent_replay=False)

    def get_job(self, *, project_id: str, job_id: str) -> AnalysisJob:
        return self._require_job(project_id, job_id)

    def mark_job_running(self, *, project_id: str, job_id: str) -> AnalysisJob:
        return self._transition_job(
            project_id=project_id,
            job_id=job_id,
            target=AnalysisJobStatus.RUNNING,
        )

    def mark_job_succeeded(self, *, project_id: str, job_id: str) -> AnalysisJob:
        return self._transition_job(
            project_id=project_id,
            job_id=job_id,
            target=AnalysisJobStatus.SUCCEEDED,
        )

    def mark_job_failed(
        self,
        *,
        project_id: str,
        job_id: str,
        failure_reason: AnalysisJobFailureReason,
        failure_detail: str | None = None,
    ) -> AnalysisJob:
        return self._transition_job(
            project_id=project_id,
            job_id=job_id,
            target=AnalysisJobStatus.FAILED,
            failure_reason=failure_reason,
            failure_detail=failure_detail,
        )

    def retry_failed_job(self, *, project_id: str, job_id: str) -> AnalysisJob:
        """Explicitly reset one failed job; ordinary replay remains terminal."""
        return self._transition_job(
            project_id=project_id,
            job_id=job_id,
            target=AnalysisJobStatus.PENDING,
        )

    def _transition_job(
        self,
        *,
        project_id: str,
        job_id: str,
        target: AnalysisJobStatus,
        failure_reason: AnalysisJobFailureReason | None = None,
        failure_detail: str | None = None,
    ) -> AnalysisJob:
        job = self._require_job(project_id, job_id)
        if (job.status, target) not in _ALLOWED_JOB_TRANSITIONS:
            raise InvalidJobStateTransition(
                f"cannot transition job from {job.status} to {target}"
            )
        if target is AnalysisJobStatus.FAILED:
            if not isinstance(failure_reason, AnalysisJobFailureReason):
                raise InvalidJobStateTransition(
                    "failed transition requires a failure_reason"
                )
            updated = replace(
                job,
                status=target,
                failure_reason=failure_reason,
                failure_detail=failure_detail,
            )
        else:
            if failure_reason is not None or failure_detail:
                raise InvalidJobStateTransition(
                    "non-failed transition must not set failure fields"
                )
            updated = replace(
                job,
                status=target,
                failure_reason=None,
                failure_detail=None,
            )
        self._repo.update_job(updated)
        return updated

    def create_task(
        self,
        *,
        project_id: str,
        job_id: str,
        candidate_type: AnalysisCandidateType,
    ) -> AnalysisTask:
        job = self._require_job(project_id, job_id)
        self._validate_candidate_type(candidate_type)
        existing_task_id = self._repo.find_task_request(
            project_id, job.id, candidate_type
        )
        if existing_task_id is not None:
            return self._require_task(project_id, existing_task_id)

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
        return self.record_candidates(
            project_id=project_id,
            requests=(
                AnalysisCandidateRecordRequest(
                    task_id=task_id,
                    logical_key=logical_key,
                    candidate_type=candidate_type,
                    action=action,
                    provenance=provenance,
                    confidence=confidence,
                    source_ref_ids=source_ref_ids,
                    payload=payload,
                    source_anchors=source_anchors,
                ),
            ),
        )[0]

    def record_candidates(
        self,
        *,
        project_id: str,
        requests: Sequence[AnalysisCandidateRecordRequest],
    ) -> tuple[RecordAnalysisCandidateResult, ...]:
        prepared = tuple(
            self._prepare_candidate_record(project_id=project_id, request=request)
            for request in requests
        )
        new_candidates: list[tuple[AnalysisCandidate, str]] = []
        batch_seen: dict[tuple[str, str, str], AnalysisCandidate] = {}
        results: list[RecordAnalysisCandidateResult] = []

        for request, task, normalized_payload, confidence, source_ref_ids in prepared:
            candidate_key = (project_id, request.task_id, request.logical_key)
            existing_candidate = batch_seen.get(candidate_key)
            if existing_candidate is not None:
                results.append(
                    RecordAnalysisCandidateResult(
                        candidate=existing_candidate,
                        idempotent_replay=True,
                    )
                )
                continue

            existing_candidate_id = self._repo.find_candidate_request(
                project_id, request.task_id, request.logical_key
            )
            if existing_candidate_id is not None:
                results.append(
                    RecordAnalysisCandidateResult(
                        candidate=self._require_candidate(
                            project_id, existing_candidate_id
                        ),
                        idempotent_replay=True,
                    )
                )
                continue

            candidate = AnalysisCandidate(
                id=self._repo.next_candidate_id(),
                project_id=project_id,
                job_id=task.job_id,
                task_id=task.id,
                candidate_type=request.candidate_type,
                action=AnalysisCandidateAction.CREATE,
                status=AnalysisCandidateStatus.NEEDS_REVIEW,
                provenance=request.provenance,
                confidence=confidence,
                source_ref_ids=source_ref_ids,
                payload=immutable_payload(normalized_payload),
            )
            new_candidates.append((candidate, request.logical_key))
            batch_seen[candidate_key] = candidate
            results.append(
                RecordAnalysisCandidateResult(
                    candidate=candidate,
                    idempotent_replay=False,
                )
            )

        if new_candidates:
            self._repo.put_candidates(tuple(new_candidates))
            self._enqueue_candidate_reindex(new_candidates)
        return tuple(results)

    def _enqueue_candidate_reindex(
        self, new_candidates: Sequence[tuple[AnalysisCandidate, str]]
    ) -> None:
        # b-2 (G2): enqueue only newly minted candidates (idempotent replays are
        # skipped by never reaching this list). Absent outbox is a no-op.
        if self._reindex_outbox is None:
            return
        for candidate, _logical_key in new_candidates:
            self._reindex_outbox.enqueue_candidate_upserted(
                project_id=candidate.project_id, candidate_id=candidate.id
            )

    def validate_candidate(
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
    ) -> None:
        self._validate_logical_key(logical_key)
        self._validate_candidate_request(
            project_id=project_id,
            task_id=task_id,
            candidate_type=candidate_type,
            action=action,
            provenance=provenance,
            confidence=confidence,
            source_ref_ids=source_ref_ids,
            payload=payload,
            source_anchors=source_anchors,
        )

    def list_candidates(
        self, *, project_id: str, job_id: str
    ) -> tuple[AnalysisCandidate, ...]:
        self._require_job(project_id, job_id)
        return self._repo.list_candidates_for_job(project_id, job_id)

    def list_needs_review_candidates(
        self, *, project_id: str
    ) -> tuple[AnalysisCandidate, ...]:
        # Project-wide needs_review candidates (across jobs) for Writing
        # candidate inclusion (⑤ §5 B follow-up, D5=A). Promoted candidates
        # leave this set — they are served by the canonical path instead.
        return self._repo.list_needs_review_candidates(project_id)

    def get_candidate(
        self, *, project_id: str, candidate_id: str
    ) -> AnalysisCandidate:
        return self._require_candidate(project_id, candidate_id)

    def transition_candidate(
        self,
        *,
        project_id: str,
        candidate_id: str,
        target: AnalysisCandidateStatus,
    ) -> "CandidateTransition":
        """Phase 6 candidate status state machine (mirror of ``_transition_job``).

        Idempotent (D4): re-applying the current status is a no-op replay
        (``changed=False``). A cross-terminal or backward edge is rejected."""
        candidate = self._require_candidate(project_id, candidate_id)
        if candidate.status is target:
            return CandidateTransition(candidate=candidate, changed=False)
        if (candidate.status, target) not in _ALLOWED_CANDIDATE_TRANSITIONS:
            raise InvalidCandidateStateTransition(
                f"cannot transition candidate from {candidate.status} to {target}"
            )
        updated = replace(candidate, status=target)
        self._repo.update_candidate(updated)
        return CandidateTransition(candidate=updated, changed=True)

    def edit_candidate(
        self,
        *,
        project_id: str,
        candidate_id: str,
        payload: Mapping[str, Any],
    ) -> "CandidateEdit":
        """Phase 6 candidate edit (v1.6.66, D1=new candidate version).

        A reviewer corrects the candidate's ``payload``. The edit mints a new
        candidate version (append-only, new id) carrying the corrected payload
        and the original's source grounding/provenance/confidence (D5); the new
        version is ``confirmed`` (edit is an approve-with-correction, D2), and
        the original is retained as ``superseded`` (audit, D3).

        Idempotency (D4): an original is edited at most once. The successor's
        ``logical_key = f"edit:{original_id}"`` reuses the existing
        ``(project, task, logical_key)`` uniqueness — a replay returns the
        existing successor, and a concurrent second edit loses on the unique
        index and replays the winner. No client idempotency key is required.
        """
        original = self._require_candidate(project_id, candidate_id)
        edit_logical_key = f"edit:{original.id}"
        existing_successor_id = self._repo.find_candidate_request(
            project_id, original.task_id, edit_logical_key
        )
        if existing_successor_id is not None:
            return CandidateEdit(
                candidate=self._require_candidate(
                    project_id, existing_successor_id
                ),
                idempotent_replay=True,
            )
        if original.status is not AnalysisCandidateStatus.NEEDS_REVIEW:
            raise InvalidCandidateStateTransition(
                f"cannot edit candidate in status {original.status}"
            )
        normalized_payload = self._validate_payload(
            original.candidate_type, payload
        )
        successor = AnalysisCandidate(
            id=self._repo.next_candidate_id(),
            project_id=project_id,
            job_id=original.job_id,
            task_id=original.task_id,
            candidate_type=original.candidate_type,
            action=original.action,
            status=AnalysisCandidateStatus.CONFIRMED,
            provenance=original.provenance,
            confidence=original.confidence,
            source_ref_ids=original.source_ref_ids,
            payload=immutable_payload(normalized_payload),
            supersedes_candidate_id=original.id,
        )
        # Append-only: insert the successor first (its unique logical_key locks
        # idempotency and concurrent double-edit), then supersede the original —
        # mirrors memory's "mint new version, then supersede prior".
        try:
            self._repo.put_candidate(successor, logical_key=edit_logical_key)
        except DuplicateAnalysisCandidateRequest:
            return CandidateEdit(
                candidate=self._require_candidate(
                    project_id,
                    self._repo.find_candidate_request(
                        project_id, original.task_id, edit_logical_key
                    ),
                ),
                idempotent_replay=True,
            )
        self._repo.update_candidate(
            replace(original, status=AnalysisCandidateStatus.SUPERSEDED)
        )
        return CandidateEdit(candidate=successor, idempotent_replay=False)

    def _validate_candidate_request(
        self,
        *,
        project_id: str,
        task_id: str,
        candidate_type: AnalysisCandidateType,
        action: AnalysisCandidateAction,
        provenance: AnalysisProvenance,
        confidence: float,
        source_ref_ids: Sequence[str],
        payload: Mapping[str, Any],
        source_anchors: Sequence[CandidateSourceAnchor] | None,
    ) -> tuple[AnalysisTask, Mapping[str, Any], float, tuple[str, ...]]:
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
            raise InvalidCandidateSource("source_anchors are required")
        if source_anchors is not None:
            anchor_source_ref_ids = self._validate_source_anchors(
                project_id=project_id,
                source_anchors=source_anchors,
            )
            if anchor_source_ref_ids != normalized_source_ref_ids:
                raise InvalidCandidateSource(
                    "source_anchors must match source_ref_ids"
                )
        return (
            task,
            normalized_payload,
            normalized_confidence,
            normalized_source_ref_ids,
        )

    def _prepare_candidate_record(
        self,
        *,
        project_id: str,
        request: AnalysisCandidateRecordRequest,
    ) -> _PreparedCandidateRecord:
        self._validate_logical_key(request.logical_key)
        task, normalized_payload, normalized_confidence, normalized_source_ref_ids = (
            self._validate_candidate_request(
                project_id=project_id,
                task_id=request.task_id,
                candidate_type=request.candidate_type,
                action=request.action,
                provenance=request.provenance,
                confidence=request.confidence,
                source_ref_ids=request.source_ref_ids,
                payload=request.payload,
                source_anchors=request.source_anchors,
            )
        )
        return (
            request,
            task,
            normalized_payload,
            normalized_confidence,
            normalized_source_ref_ids,
        )

    def _require_job(self, project_id: str, job_id: str) -> AnalysisJob:
        job = self._repo.get_job(job_id)
        if job is None or job.project_id != project_id:
            raise AnalysisNotFound("analysis job not found")
        return job

    def get_job_request(
        self, *, project_id: str, snapshot_id: str, idempotency_key: str,
    ) -> AnalysisJob | None:
        job_id = self._repo.find_job_request(project_id, snapshot_id, idempotency_key)
        return self._repo.get_job(job_id) if job_id is not None else None

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
            raise InvalidCandidateSource("source_ref resolver is required")
        if isinstance(source_anchors, (str, bytes)) or not source_anchors:
            raise InvalidCandidateSource("source_anchors are required")

        source_ref_ids: list[str] = []
        for anchor in source_anchors:
            if not isinstance(anchor, CandidateSourceAnchor):
                raise InvalidCandidateSource("invalid source anchor")
            source_ref = self._source_ref_resolver.get_source_ref(
                project_id=project_id,
                source_ref_id=anchor.source_ref_id,
            )
            if source_ref is None:
                raise InvalidCandidateSource("source_ref not found")
            if (
                source_ref.project_id != project_id
                or source_ref.start_offset != anchor.start_offset
                or source_ref.end_offset != anchor.end_offset
                or source_ref.quote != anchor.quote
                or source_ref.content_hash != anchor.content_hash
            ):
                raise InvalidCandidateSource("source_ref anchor mismatch")
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
