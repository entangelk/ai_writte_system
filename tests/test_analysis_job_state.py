"""Phase 2A AnalysisJob state-transition contract tests (in-memory).

Locks the approved job lifecycle: pending -> running -> succeeded | failed,
terminal states immutable, failure fields only on failed.
"""

import unittest

from services.application.app.analysis.models import (
    AnalysisJobFailureReason,
    AnalysisJobStatus,
)
from services.application.app.analysis.service import (
    AnalysisNotFound,
    AnalysisService,
    InMemoryAnalysisRepository,
    InvalidJobStateTransition,
)


def _service() -> tuple[AnalysisService, InMemoryAnalysisRepository]:
    repo = InMemoryAnalysisRepository()
    return AnalysisService(repo), repo


def _job(service: AnalysisService):
    return service.create_job(
        project_id="project-1",
        snapshot_id="snapshot-1",
        idempotency_key="run-1",
    ).job


class AnalysisJobStateTests(unittest.TestCase):
    def test_created_job_starts_pending(self):
        service, _ = _service()
        job = _job(service)
        self.assertEqual(job.status, AnalysisJobStatus.PENDING)
        self.assertIsNone(job.failure_reason)
        self.assertIsNone(job.failure_detail)

    def test_pending_to_running_to_succeeded(self):
        service, repo = _service()
        job = _job(service)

        running = service.mark_job_running(project_id="project-1", job_id=job.id)
        self.assertEqual(running.status, AnalysisJobStatus.RUNNING)

        succeeded = service.mark_job_succeeded(project_id="project-1", job_id=job.id)
        self.assertEqual(succeeded.status, AnalysisJobStatus.SUCCEEDED)
        # Over-strict guard: a succeeded job carries no failure fields.
        self.assertIsNone(succeeded.failure_reason)
        self.assertIsNone(succeeded.failure_detail)
        self.assertEqual(repo.get_job(job.id).status, AnalysisJobStatus.SUCCEEDED)

    def test_running_to_failed_records_reason_and_detail(self):
        service, repo = _service()
        job = _job(service)
        service.mark_job_running(project_id="project-1", job_id=job.id)

        failed = service.mark_job_failed(
            project_id="project-1",
            job_id=job.id,
            failure_reason=AnalysisJobFailureReason.PROVIDER_ERROR,
            failure_detail="gateway timeout",
        )
        self.assertEqual(failed.status, AnalysisJobStatus.FAILED)
        self.assertEqual(
            failed.failure_reason, AnalysisJobFailureReason.PROVIDER_ERROR
        )
        self.assertEqual(failed.failure_detail, "gateway timeout")
        persisted = repo.get_job(job.id)
        self.assertEqual(persisted.status, AnalysisJobStatus.FAILED)
        self.assertEqual(
            persisted.failure_reason, AnalysisJobFailureReason.PROVIDER_ERROR
        )

    def test_failed_requires_failure_reason(self):
        service, _ = _service()
        job = _job(service)
        service.mark_job_running(project_id="project-1", job_id=job.id)
        with self.assertRaises(InvalidJobStateTransition):
            service.mark_job_failed(
                project_id="project-1",
                job_id=job.id,
                failure_reason=None,  # type: ignore[arg-type]
            )

    def test_pending_cannot_skip_to_succeeded(self):
        service, _ = _service()
        job = _job(service)
        with self.assertRaises(InvalidJobStateTransition):
            service.mark_job_succeeded(project_id="project-1", job_id=job.id)

    def test_pending_cannot_skip_to_failed(self):
        service, _ = _service()
        job = _job(service)
        with self.assertRaises(InvalidJobStateTransition):
            service.mark_job_failed(
                project_id="project-1",
                job_id=job.id,
                failure_reason=AnalysisJobFailureReason.SNAPSHOT_NOT_FOUND,
            )

    def test_succeeded_is_terminal(self):
        service, _ = _service()
        job = _job(service)
        service.mark_job_running(project_id="project-1", job_id=job.id)
        service.mark_job_succeeded(project_id="project-1", job_id=job.id)
        with self.assertRaises(InvalidJobStateTransition):
            service.mark_job_failed(
                project_id="project-1",
                job_id=job.id,
                failure_reason=AnalysisJobFailureReason.PROVIDER_ERROR,
            )
        with self.assertRaises(InvalidJobStateTransition):
            service.mark_job_running(project_id="project-1", job_id=job.id)

    def test_failed_is_terminal(self):
        service, _ = _service()
        job = _job(service)
        service.mark_job_running(project_id="project-1", job_id=job.id)
        service.mark_job_failed(
            project_id="project-1",
            job_id=job.id,
            failure_reason=AnalysisJobFailureReason.SOURCE_INVALID,
        )
        # failed is terminal: no re-run in place (Fork B).
        with self.assertRaises(InvalidJobStateTransition):
            service.mark_job_running(project_id="project-1", job_id=job.id)

    def test_running_cannot_repeat(self):
        service, _ = _service()
        job = _job(service)
        service.mark_job_running(project_id="project-1", job_id=job.id)
        with self.assertRaises(InvalidJobStateTransition):
            service.mark_job_running(project_id="project-1", job_id=job.id)

    def test_transition_enforces_project_isolation(self):
        service, _ = _service()
        job = _job(service)
        with self.assertRaises(AnalysisNotFound):
            service.mark_job_running(project_id="project-2", job_id=job.id)


if __name__ == "__main__":
    unittest.main()
