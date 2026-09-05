"""Phase 2A AnalysisJob state-transition contract tests (in-memory).

Locks the approved job lifecycle: pending -> running -> succeeded | failed,
terminal states immutable, failure fields only on failed.
"""

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from services.application.app.analysis.models import (
    AnalysisJobFailureReason,
    AnalysisJobStatus,
)
from services.application.app.retry_policy import (
    RetryCooldownActive,
    RetryLimitReached,
)
from services.application.app.analysis.service import (
    AnalysisNotFound,
    AnalysisService,
    InMemoryAnalysisRepository,
    InvalidJobStateTransition,
)


class _Clock:
    """S-1 D2 — 재시도 쿨다운(60s)을 결정적으로 흘리는 손잡이 클록."""

    def __init__(self) -> None:
        self.now = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def _service(clock=None) -> tuple[AnalysisService, InMemoryAnalysisRepository]:
    repo = InMemoryAnalysisRepository()
    return AnalysisService(repo, clock=clock), repo


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

    def test_explicit_retry_failed_to_pending_clears_failure_fields(self):
        clock = _Clock()
        service, repo = _service(clock=clock)
        job = _job(service)
        service.mark_job_running(project_id="project-1", job_id=job.id)
        service.mark_job_failed(
            project_id="project-1",
            job_id=job.id,
            failure_reason=AnalysisJobFailureReason.SOURCE_INVALID,
            failure_detail="source_ref not found",
        )
        clock.advance(61)  # S-1 D2: 재시도 쿨다운(60s)을 지난 뒤다

        retried = service.retry_failed_job(
            project_id="project-1", job_id=job.id
        )

        self.assertEqual(retried.id, job.id)
        self.assertEqual(retried.status, AnalysisJobStatus.PENDING)
        self.assertIsNone(retried.failure_reason)
        self.assertIsNone(retried.failure_detail)
        self.assertEqual(repo.get_job(job.id), retried)

    def test_explicit_retry_is_capped_at_two_attempts(self):
        """S-1 D2(오너 2026-09-05): 상한 2회 — B5 의 "재시도는 드문 회복 수단"
        전제를 지키는 숫자(감사 §A.2). under-strict: 상한을 지우면 세 번째가
        통과하고, over-strict: 1 로 당기면 둘째에서 실패한다.
        """
        clock = _Clock()
        service, repo = _service(clock=clock)
        job = _job(service)
        service.mark_job_running(project_id="project-1", job_id=job.id)
        job = service.mark_job_failed(
            project_id="project-1", job_id=job.id,
            failure_reason=AnalysisJobFailureReason.PROVIDER_ERROR,
        )
        for _ in range(2):
            clock.advance(61)
            job = service.retry_failed_job(
                project_id="project-1", job_id=job.id)
            service.mark_job_running(project_id="project-1", job_id=job.id)
            job = service.mark_job_failed(
                project_id="project-1", job_id=job.id,
                failure_reason=AnalysisJobFailureReason.PROVIDER_ERROR,
            )
        clock.advance(61)
        with self.assertRaises(RetryLimitReached):
            service.retry_failed_job(project_id="project-1", job_id=job.id)

    def test_explicit_retry_within_the_cooldown_is_refused(self):
        """쿨다운 60s — 실패 직후의 재시도 나열을 막는다."""
        clock = _Clock()
        service, _repo = _service(clock=clock)
        job = _job(service)
        service.mark_job_running(project_id="project-1", job_id=job.id)
        service.mark_job_failed(
            project_id="project-1", job_id=job.id,
            failure_reason=AnalysisJobFailureReason.PROVIDER_ERROR,
        )
        with self.assertRaises(RetryCooldownActive) as ctx:
            service.retry_failed_job(project_id="project-1", job_id=job.id)
        self.assertEqual(ctx.exception.retry_after_seconds, 60)
        clock.advance(61)
        retried = service.retry_failed_job(
            project_id="project-1", job_id=job.id)
        self.assertEqual(retried.retry_count, 1)

    def test_a_legacy_failed_row_without_failed_at_has_no_cooldown(self):
        """과잉 방어: S-1 이전 옛 행(``failed_at`` 없음)은 즉시 재시도할 수 있다."""
        service, repo = _service()
        job = _job(service)
        service.mark_job_running(project_id="project-1", job_id=job.id)
        service.mark_job_failed(
            project_id="project-1", job_id=job.id,
            failure_reason=AnalysisJobFailureReason.PROVIDER_ERROR,
        )
        legacy = replace(
            repo.get_job(job.id), failed_at=None)
        repo.update_job(legacy)
        retried = service.retry_failed_job(
            project_id="project-1", job_id=job.id)
        self.assertEqual(retried.status, AnalysisJobStatus.PENDING)

    def test_explicit_retry_rejects_every_non_failed_state(self):
        for status in (
            AnalysisJobStatus.PENDING,
            AnalysisJobStatus.RUNNING,
            AnalysisJobStatus.SUCCEEDED,
        ):
            with self.subTest(status=status):
                service, _ = _service()
                job = _job(service)
                if status is not AnalysisJobStatus.PENDING:
                    service.mark_job_running(project_id="project-1", job_id=job.id)
                if status is AnalysisJobStatus.SUCCEEDED:
                    service.mark_job_succeeded(project_id="project-1", job_id=job.id)
                with self.assertRaises(InvalidJobStateTransition):
                    service.retry_failed_job(
                        project_id="project-1", job_id=job.id
                    )

    def test_explicit_retry_enforces_project_isolation(self):
        service, _ = _service()
        job = _job(service)
        service.mark_job_running(project_id="project-1", job_id=job.id)
        service.mark_job_failed(
            project_id="project-1",
            job_id=job.id,
            failure_reason=AnalysisJobFailureReason.SOURCE_INVALID,
        )

        with self.assertRaises(AnalysisNotFound):
            service.retry_failed_job(project_id="project-2", job_id=job.id)

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

    def test_every_failure_reason_literal_round_trips(self):
        # Boundary matrix: every closed failure_reason literal must be lockable
        # on a failed job and survive read-back, including schema_invalid and
        # duplicate_conflict which no other test exercises.
        for reason in AnalysisJobFailureReason:
            with self.subTest(reason=reason):
                service, repo = _service()
                job = _job(service)
                service.mark_job_running(project_id="project-1", job_id=job.id)
                failed = service.mark_job_failed(
                    project_id="project-1",
                    job_id=job.id,
                    failure_reason=reason,
                    failure_detail=f"detail::{reason}",
                )
                self.assertEqual(failed.failure_reason, reason)
                persisted = repo.get_job(job.id)
                self.assertEqual(persisted.failure_reason, reason)
                self.assertEqual(persisted.failure_detail, f"detail::{reason}")

    def test_non_enum_failure_reason_is_rejected(self):
        # Over-strict guard: a raw string literal must not pass as a reason.
        service, _ = _service()
        job = _job(service)
        service.mark_job_running(project_id="project-1", job_id=job.id)
        with self.assertRaises(InvalidJobStateTransition):
            service.mark_job_failed(
                project_id="project-1",
                job_id=job.id,
                failure_reason="schema_invalid",  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
