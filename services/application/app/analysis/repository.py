"""Repository boundary for Phase 2A analysis state."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateType,
    AnalysisJob,
    AnalysisTask,
)


class DuplicateAnalysisCandidateRequest(RuntimeError):
    """Raised when a candidate idempotency key is already committed.

    Defined at the repository boundary so storage-agnostic callers (service,
    runner) can map it without depending on a concrete adapter.
    """


class AnalysisRepository(Protocol):
    def next_job_id(self) -> str: ...

    def next_task_id(self) -> str: ...

    def next_candidate_id(self) -> str: ...

    def get_job(self, job_id: str) -> AnalysisJob | None: ...

    def find_job_request(
        self, project_id: str, snapshot_id: str, idempotency_key: str
    ) -> str | None: ...

    def put_job(self, job: AnalysisJob) -> None: ...

    def update_job(self, job: AnalysisJob) -> None: ...

    def get_task(self, task_id: str) -> AnalysisTask | None: ...

    def find_task_request(
        self, project_id: str, job_id: str, candidate_type: AnalysisCandidateType
    ) -> str | None: ...

    def put_task(self, task: AnalysisTask) -> None: ...

    def get_candidate(self, candidate_id: str) -> AnalysisCandidate | None: ...

    def find_candidate_request(
        self, project_id: str, task_id: str, logical_key: str
    ) -> str | None: ...

    def put_candidate(
        self, candidate: AnalysisCandidate, *, logical_key: str
    ) -> None: ...

    def put_candidates(
        self, candidates: Sequence[tuple[AnalysisCandidate, str]]
    ) -> None: ...

    def update_candidate(self, candidate: AnalysisCandidate) -> None: ...

    def list_candidates_for_job(
        self, project_id: str, job_id: str
    ) -> tuple[AnalysisCandidate, ...]: ...

    def list_needs_review_candidates(
        self, project_id: str
    ) -> tuple[AnalysisCandidate, ...]: ...
