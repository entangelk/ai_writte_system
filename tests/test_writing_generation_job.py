"""Async generation job store — service + in-memory repository regressions.

Brief: docs/plans/async-generation-pad-decisions.md (D3=B / D4=A, 2026-07-20).
This is the data layer (async-pad 증분 2a); the worker (2b) and endpoint (2c)
consume it. Locks the state machine and the atomic claim both directions:

- enqueue is idempotent on (project_id, request_id) — a retried POST never
  spawns a second background generation (under-strict), a distinct request does
  (over-strict).
- claim moves the oldest PENDING to RUNNING; a lease-expired RUNNING is
  reclaimable (crashed worker recovery), a fresh RUNNING is NOT (over-strict:
  no double-run of an in-flight job).
- mark_succeeded/failed only from RUNNING; the forbidden transitions raise
  (over-strict: the worker cannot corrupt terminal state).
"""

import unittest
from datetime import UTC, datetime, timedelta

from services.application.app.writing.generation_job import (
    DEFAULT_CLAIM_TIMEOUT_SECONDS,
    InMemoryWritingGenerationJobRepository,
    InvalidJobStateTransition,
    WritingGenerationJobFailureReason,
    WritingGenerationJobService,
    WritingGenerationJobStatus,
)


class _Clock:
    """A hand-cranked clock so claim/lease timing is deterministic."""

    def __init__(self, start=None):
        self.now = start or datetime(2026, 7, 21, tzinfo=UTC)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now = self.now + timedelta(seconds=seconds)


def _id_seq():
    state = {"n": 0}

    def factory():
        state["n"] += 1
        return f"wgj:{state['n']}"

    return factory


def _service(*, clock=None, claim_timeout_seconds=DEFAULT_CLAIM_TIMEOUT_SECONDS):
    return WritingGenerationJobService(
        InMemoryWritingGenerationJobRepository(),
        clock=clock or _Clock(),
        id_factory=_id_seq(),
        claim_timeout_seconds=claim_timeout_seconds,
    )


def _enqueue(svc, *, project="p1", draft="d1", request="wr1", length="medium",
             tokens=2048, user=None, intent=None, next_unit=None):
    return svc.enqueue(
        project_id=project, draft_id=draft, request_id=request,
        task_type="continue_scene", instruction="이어서 써줘",
        draft_excerpt="앞 문단", query=None, output_length=length,
        max_output_tokens=tokens, max_tokens=4096, version_id="v1",
        user_id=user, intent=intent, next_unit=next_unit,
    )


class EnqueueTest(unittest.TestCase):
    def test_enqueue_creates_pending_job_carrying_its_inputs(self):
        svc = _service()
        result = _enqueue(svc, length="long", tokens=4096)
        self.assertFalse(result.idempotent_replay)
        job = result.job
        self.assertEqual(job.status, WritingGenerationJobStatus.PENDING)
        self.assertEqual(
            (job.project_id, job.draft_id, job.request_id, job.version_id),
            ("p1", "d1", "wr1", "v1"))
        self.assertEqual(job.output_length, "long")
        self.assertEqual(job.max_output_tokens, 4096)
        self.assertEqual(job.max_tokens, 4096)
        self.assertIsNone(job.intent)
        self.assertIsNone(job.next_unit)
        self.assertIsNone(job.claimed_at)
        self.assertIsNone(job.result_scratch_id)

    def test_enqueue_carries_start_next_fields(self):
        svc = _service()
        result = _enqueue(
            svc,
            intent="start_next_unit",
            next_unit={"title": "다음 장면", "goal": None},
        )

        self.assertEqual(result.job.intent, "start_next_unit")
        self.assertEqual(result.job.next_unit, {
            "title": "다음 장면", "goal": None})

    def test_enqueue_is_idempotent_on_project_and_request(self):
        # under-strict: a retried POST of the same request returns the SAME job,
        # not a second background generation.
        svc = _service()
        first = _enqueue(svc)
        again = _enqueue(svc, length="long", tokens=4096)
        self.assertTrue(again.idempotent_replay)
        self.assertEqual(again.job.id, first.job.id)
        # the replay returns the stored job, ignoring the new args
        self.assertEqual(again.job.output_length, "medium")

    def test_distinct_request_id_creates_a_new_job(self):
        # over-strict: idempotency keys on request_id, so a genuinely new request
        # must not collapse into the first.
        svc = _service()
        first = _enqueue(svc, request="wr1")
        second = _enqueue(svc, request="wr2")
        self.assertFalse(second.idempotent_replay)
        self.assertNotEqual(second.job.id, first.job.id)

    def test_same_request_id_across_projects_is_not_deduped(self):
        # over-strict: the idempotency key includes project_id.
        svc = _service()
        a = _enqueue(svc, project="p1", request="wr1")
        b = _enqueue(svc, project="p2", request="wr1")
        self.assertFalse(b.idempotent_replay)
        self.assertNotEqual(b.job.id, a.job.id)


class ClaimTest(unittest.TestCase):
    def test_claim_moves_oldest_pending_to_running_and_stamps_time(self):
        clock = _Clock()
        svc = _service(clock=clock)
        first = _enqueue(svc, request="wr1").job
        clock.advance(1)
        _enqueue(svc, request="wr2")
        clock.advance(10)

        claimed = svc.claim_next()
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.id, first.id)  # oldest first
        self.assertEqual(claimed.status, WritingGenerationJobStatus.RUNNING)
        self.assertEqual(claimed.claimed_at, clock.now)

    def test_claim_returns_none_when_nothing_pending(self):
        svc = _service()
        self.assertIsNone(svc.claim_next())

    def test_claim_skips_a_fresh_running_job(self):
        # over-strict: an in-flight job within its lease must NOT be re-claimed —
        # that would double-run the same generation.
        svc = _service(claim_timeout_seconds=600)
        _enqueue(svc)
        self.assertIsNotNone(svc.claim_next())  # now RUNNING, claimed just now
        self.assertIsNone(svc.claim_next())

    def test_claim_reclaims_a_lease_expired_running_job(self):
        # under-strict: a worker that crashed mid-generation leaves a stale
        # RUNNING job; past the lease it becomes claimable again.
        clock = _Clock()
        svc = _service(clock=clock, claim_timeout_seconds=600)
        _enqueue(svc)
        first = svc.claim_next()
        self.assertIsNotNone(first)
        clock.advance(601)
        reclaimed = svc.claim_next()
        self.assertIsNotNone(reclaimed)
        self.assertEqual(reclaimed.id, first.id)
        self.assertEqual(reclaimed.claimed_at, clock.now)


class TransitionTest(unittest.TestCase):
    def _running(self, svc):
        _enqueue(svc)
        return svc.claim_next()

    def test_mark_succeeded_from_running_records_result(self):
        svc = _service()
        job = self._running(svc)
        done = svc.mark_succeeded(job, result_scratch_id="wds:7")
        self.assertEqual(done.status, WritingGenerationJobStatus.SUCCEEDED)
        self.assertEqual(done.result_scratch_id, "wds:7")
        self.assertEqual(svc.get(job.id).status,
                         WritingGenerationJobStatus.SUCCEEDED)

    def test_mark_failed_from_running_records_reason_and_detail(self):
        svc = _service()
        job = self._running(svc)
        failed = svc.mark_failed(
            job, reason=WritingGenerationJobFailureReason.PROVIDER_TIMEOUT,
            detail="gateway timed out")
        self.assertEqual(failed.status, WritingGenerationJobStatus.FAILED)
        self.assertEqual(failed.failure_reason,
                         WritingGenerationJobFailureReason.PROVIDER_TIMEOUT)
        self.assertEqual(failed.failure_detail, "gateway timed out")

    def test_mark_succeeded_on_pending_is_rejected(self):
        # over-strict: only a claimed (RUNNING) job may complete; skipping the
        # claim must raise, not silently succeed.
        svc = _service()
        job = _enqueue(svc).job  # still PENDING
        with self.assertRaises(InvalidJobStateTransition):
            svc.mark_succeeded(job, result_scratch_id="wds:7")

    def test_mark_failed_on_a_succeeded_job_is_rejected(self):
        # over-strict: terminal SUCCEEDED cannot be flipped to FAILED.
        svc = _service()
        job = self._running(svc)
        svc.mark_succeeded(job, result_scratch_id="wds:7")
        succeeded = svc.get(job.id)
        with self.assertRaises(InvalidJobStateTransition):
            svc.mark_failed(
                succeeded,
                reason=WritingGenerationJobFailureReason.PROVIDER_ERROR)


class RetryTest(unittest.TestCase):
    """FAILED→PENDING explicit retry (retry slice, D4=A). The worker re-claims
    any PENDING job, so the reset alone resumes execution."""

    def _failed(self, svc, *, detail="gateway timed out"):
        _enqueue(svc)
        job = svc.claim_next()
        return svc.mark_failed(
            job,
            reason=WritingGenerationJobFailureReason.PROVIDER_TIMEOUT,
            detail=detail,
        )

    def test_retry_resets_failed_job_to_pending_clearing_failure(self):
        svc = _service()
        failed = self._failed(svc)
        retried = svc.mark_pending_for_retry(failed)
        self.assertEqual(retried.status, WritingGenerationJobStatus.PENDING)
        self.assertIsNone(retried.failure_reason)
        self.assertIsNone(retried.failure_detail)
        self.assertIsNone(retried.claimed_at)  # stale lease cleared
        # persisted, not just the returned copy
        self.assertEqual(svc.get(failed.id).status,
                         WritingGenerationJobStatus.PENDING)

    def test_retried_job_is_reclaimable_by_the_worker(self):
        # under-strict — the whole point of the slice: after retry the worker's
        # claim loop must pick the job up again and re-run it.
        svc = _service()
        failed = self._failed(svc)
        self.assertIsNone(svc.claim_next())  # FAILED is not claimable
        svc.mark_pending_for_retry(failed)
        reclaimed = svc.claim_next()
        self.assertIsNotNone(reclaimed)
        self.assertEqual(reclaimed.id, failed.id)
        self.assertEqual(reclaimed.status, WritingGenerationJobStatus.RUNNING)

    def test_retry_on_pending_is_rejected(self):
        # over-strict: only a FAILED job is retryable — a queued one is not.
        svc = _service()
        job = _enqueue(svc).job  # PENDING
        with self.assertRaises(InvalidJobStateTransition):
            svc.mark_pending_for_retry(job)

    def test_retry_on_running_is_rejected(self):
        # over-strict: an in-flight job must not be yanked back to PENDING.
        svc = _service()
        _enqueue(svc)
        running = svc.claim_next()
        with self.assertRaises(InvalidJobStateTransition):
            svc.mark_pending_for_retry(running)

    def test_retry_on_succeeded_is_rejected(self):
        # over-strict: a completed job is terminal — retry cannot resurrect it.
        svc = _service()
        _enqueue(svc)
        job = svc.claim_next()
        svc.mark_succeeded(job, result_scratch_id="wds:7")
        succeeded = svc.get(job.id)
        with self.assertRaises(InvalidJobStateTransition):
            svc.mark_pending_for_retry(succeeded)


class ListForDraftTest(unittest.TestCase):
    def test_lists_draft_jobs_newest_first_isolated_by_draft(self):
        clock = _Clock()
        svc = _service(clock=clock)
        _enqueue(svc, draft="d1", request="wr1")
        clock.advance(1)
        _enqueue(svc, draft="d1", request="wr2")
        clock.advance(1)
        _enqueue(svc, draft="d2", request="wr3")

        d1 = svc.list_for_draft("p1", "d1")
        self.assertEqual([j.request_id for j in d1], ["wr2", "wr1"])
        d2 = svc.list_for_draft("p1", "d2")
        self.assertEqual([j.request_id for j in d2], ["wr3"])


class QuotaSubjectTest(unittest.TestCase):
    """Slice 8.3 Q1-b=A — job 이 주체를 들고 간다."""

    def test_the_enqueued_job_carries_its_member(self):
        svc = _service()
        _enqueue(svc, user="u-1")
        self.assertEqual(svc.get(svc.claim_next().id).user_id, "u-1")

    def test_only_pending_and_running_jobs_count_toward_the_limit(self):
        # 완료·실패한 job 은 세지 않는다 — 성공은 원장 행이 대신 세고(이중 계수가
        # 된다), 실패는 애초에 과금하지 않는다(Q1=C).
        clock = _Clock()
        svc = _service(clock=clock)
        _enqueue(svc, draft="d1", request="wr1", user="u-1")
        clock.advance(1)
        _enqueue(svc, draft="d2", request="wr2", user="u-1")
        self.assertEqual(svc.count_active_for_user(user_id="u-1"), 2)
        svc.mark_succeeded(svc.claim_next(), result_scratch_id="wds:1")
        self.assertEqual(svc.count_active_for_user(user_id="u-1"), 1)
        svc.mark_failed(
            svc.claim_next(),
            reason=WritingGenerationJobFailureReason.PROVIDER_ERROR)
        self.assertEqual(svc.count_active_for_user(user_id="u-1"), 0)

    def test_another_members_jobs_are_not_counted(self):
        # over-strict 짝: 회원 경계를 잃으면 남의 생성이 내 한도를 먹는다.
        svc = _service()
        _enqueue(svc, user="someone-else")
        self.assertEqual(svc.count_active_for_user(user_id="u-1"), 0)


class InFlightDraftGuardTest(unittest.TestCase):
    """Slice 8.3 Q8=C — 같은 draft 의 **다른** 요청만 막는다."""

    def test_a_pending_job_from_another_request_blocks(self):
        svc = _service()
        _enqueue(svc, draft="d1", request="wr1")
        self.assertTrue(svc.has_other_active_for_draft(
            project_id="p1", draft_id="d1", request_id="wr2"))

    def test_the_same_request_is_never_blocked_by_its_own_job(self):
        # over-strict 짝: 멱등 replay 까지 막으면 폴링·재전송하는 클라이언트가
        # 자기 job 을 못 받는다(그 replay 는 새 job 도 새 과금도 만들지 않는다).
        svc = _service()
        _enqueue(svc, draft="d1", request="wr1")
        self.assertFalse(svc.has_other_active_for_draft(
            project_id="p1", draft_id="d1", request_id="wr1"))

    def test_a_finished_job_stops_blocking(self):
        svc = _service()
        _enqueue(svc, draft="d1", request="wr1")
        svc.mark_succeeded(svc.claim_next(), result_scratch_id="wds:1")
        self.assertFalse(svc.has_other_active_for_draft(
            project_id="p1", draft_id="d1", request_id="wr2"))

    def test_another_draft_is_unaffected(self):
        svc = _service()
        _enqueue(svc, draft="d1", request="wr1")
        self.assertFalse(svc.has_other_active_for_draft(
            project_id="p1", draft_id="d2", request_id="wr2"))


if __name__ == "__main__":
    unittest.main()
