"""Async generation executor — per-job contract (async-pad 증분 2b).

Drives ``execute_generation_job`` with fakes (no Mongo, no gateway):

- success: a claimed job generates, its result lands in scratch with the base
  version_id (D7), and the job goes SUCCEEDED with result_scratch_id.
- every mapped generate-pipeline exception → its failure reason, no scratch
  written.
- the catch-all: an *unmapped* fault (a bug/infra error) still reaches FAILED
  via INTERNAL (verification H-2 — never livelock RUNNING→reclaim→re-fail).
- reclaim idempotency (verification H-3): a job whose prior attempt already left
  a scratch entry leaves exactly one after re-execution, not two.
"""

import unittest

from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.application.app.context_search.models import (
    ContextNeed,
    ContextSearchErrorType,
)
from services.application.app.context_search.service import (
    ContextSearchBudgetExceeded,
    ContextSearchFailed,
    InvalidContextSearchRequest,
)
from services.application.app.writing.generation_job import (
    InMemoryWritingGenerationJobRepository,
    WritingGenerationJobFailureReason,
    WritingGenerationJobService,
    WritingGenerationJobStatus,
)
from services.application.app.writing.generation_worker import (
    GenerationCollaborators,
    execute_generation_job,
)
from services.application.app.writing.report import InvalidCandidateReport
from services.application.app.writing.scratch import (
    InMemoryWritingScratchRepository,
    WritingScratchService,
)
from services.application.app.writing.service import WritingError

from tests.test_writing import _FakeProvider, _package, _run, _service


class _OkContext:
    async def build_context_package(self, request):
        return _package()


class _RaisingContext:
    def __init__(self, exc):
        self._exc = exc

    async def build_context_package(self, request):
        raise self._exc


class _RaisingWriting:
    def __init__(self, exc):
        self._exc = exc

    async def generate(self, *, request, package, max_output_tokens):
        raise self._exc


class _RaisingScratch:
    # H-1(2b): the scratch store failing on save *after* a successful generate.
    # clear_accepted_item is a no-op so save is the fault site.
    def clear_accepted_item(self, project_id, draft_id, request_id):
        return 0

    def save(self, **kwargs):
        raise RuntimeError("scratch store down")

    def list_for_draft(self, project_id, draft_id):
        return ()


def _collaborators(*, context=None, writing=None, scratch=None, jobs=None,
                   quota=None):
    return GenerationCollaborators(
        context_search=context or _OkContext(),
        writing=writing or _service(_FakeProvider(content="생성된 장면.")),
        scratch=scratch or WritingScratchService(
            InMemoryWritingScratchRepository()),
        jobs=jobs or WritingGenerationJobService(
            InMemoryWritingGenerationJobRepository()),
        needs=(ContextNeed.CURRENT_SCENE,),
        quota=quota,
    )


class _RecordingCharger:
    """Slice 8.3 Q1-b=A 의 차감 주체 자리. 무엇이 언제 불렸는지만 기록한다."""

    def __init__(self):
        self.charged = []

    def charge(self, job):
        self.charged.append(job.id)


def _claimed(
    jobs, *, request="wr1", draft="d1", version="v1",
    intent=None, next_unit=None,
):
    jobs.enqueue(
        project_id="p1", draft_id=draft, request_id=request,
        task_type="continue_scene", instruction="이어서 써줘",
        draft_excerpt="앞 문단", query=None, output_length="medium",
        max_output_tokens=2048, max_tokens=4096, version_id=version,
        intent=intent, next_unit=next_unit)
    return jobs.claim_next()


class ExecuteSuccessTest(unittest.TestCase):
    def test_success_writes_scratch_and_marks_succeeded(self):
        c = _collaborators()
        job = _claimed(c.jobs)
        done = _run(execute_generation_job(job, c))

        self.assertEqual(done.status, WritingGenerationJobStatus.SUCCEEDED)
        entries = c.scratch.list_for_draft("p1", "d1")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].candidate_text, "생성된 장면.")
        # D7: the base version rides onto the pad result.
        self.assertEqual(entries[0].version_id, "v1")
        # the job points straight at the scratch it produced
        self.assertEqual(done.result_scratch_id, entries[0].id)
        self.assertEqual(c.jobs.get(job.id).status,
                         WritingGenerationJobStatus.SUCCEEDED)

    def test_success_preserves_start_next_intent_for_pad_accept(self):
        c = _collaborators()
        job = _claimed(
            c.jobs,
            intent="start_next_unit",
            next_unit={"title": "다음 장면", "goal": "긴장 유지"},
        )
        _run(execute_generation_job(job, c))

        entry = c.scratch.list_for_draft("p1", "d1")[0]
        self.assertEqual(entry.intent, "start_next_unit")
        self.assertEqual(entry.next_unit, {
            "title": "다음 장면", "goal": "긴장 유지"})


class ExecuteChargesOnSuccessTest(unittest.TestCase):
    """Slice 8.3 Q1-b=A — **성공한 생성만** 원장에 남는다."""

    def test_a_successful_job_is_charged(self):
        charger = _RecordingCharger()
        c = _collaborators(quota=charger)
        job = _claimed(c.jobs)
        _run(execute_generation_job(job, c))
        self.assertEqual(charger.charged, [job.id])

    def test_a_failed_job_is_not_charged(self):
        # 오너 정책("실패에는 과금하지 않는다")이 **가장 비싼 경로**에서도 지켜지는
        # 자리다. 차감을 try 블록 앞이나 mark_failed 경로로 옮기는 변경이 문다.
        charger = _RecordingCharger()
        c = _collaborators(
            quota=charger,
            writing=_RaisingWriting(ProviderError(
                code=ProviderErrorCode.TIMEOUT, message="timeout",
                retryable=True, provider="llm_gateway")),
        )
        done = _run(execute_generation_job(_claimed(c.jobs), c))
        self.assertEqual(done.status, WritingGenerationJobStatus.FAILED)
        self.assertEqual(charger.charged, [])

    def test_a_persist_failure_after_generation_is_not_charged(self):
        # 결과가 pad 에 안 남았으면 회원이 받은 것이 없다 — INTERNAL 로 끝나는
        # 이 경로도 무과금이어야 한다.
        charger = _RecordingCharger()
        c = _collaborators(quota=charger, scratch=_RaisingScratch())
        done = _run(execute_generation_job(_claimed(c.jobs), c))
        self.assertEqual(done.status, WritingGenerationJobStatus.FAILED)
        self.assertEqual(charger.charged, [])

    def test_a_worker_without_a_charger_still_runs(self):
        # 손으로 조립한 collaborators(테스트·스크립트)가 그대로 유효해야 한다 —
        # llm_call_audit·capabilities 와 같은 이유의 Optional 이다.
        c = _collaborators(quota=None)
        done = _run(execute_generation_job(_claimed(c.jobs), c))
        self.assertEqual(done.status, WritingGenerationJobStatus.SUCCEEDED)


class ExecuteFailureMappingTest(unittest.TestCase):
    def _fail_with(self, *, context=None, writing=None):
        c = _collaborators(context=context, writing=writing)
        job = _claimed(c.jobs)
        done = _run(execute_generation_job(job, c))
        # no result was stored for a failed generation
        self.assertEqual(c.scratch.list_for_draft("p1", "d1"), ())
        self.assertEqual(done.status, WritingGenerationJobStatus.FAILED)
        return done.failure_reason

    def test_provider_timeout_maps_to_provider_timeout(self):
        exc = ProviderError(code=ProviderErrorCode.TIMEOUT,
                            message="gateway timed out", retryable=True)
        self.assertEqual(
            self._fail_with(writing=_RaisingWriting(exc)),
            WritingGenerationJobFailureReason.PROVIDER_TIMEOUT)

    def test_non_timeout_provider_error_maps_to_provider_error(self):
        exc = ProviderError(code=ProviderErrorCode.OVERLOADED,
                            message="overloaded", retryable=True)
        self.assertEqual(
            self._fail_with(writing=_RaisingWriting(exc)),
            WritingGenerationJobFailureReason.PROVIDER_ERROR)

    def test_context_window_exceeded_is_its_own_reason(self):
        """K-3 창 가드 거부는 `provider_error`로 접히지 않는다(오너 2026-07-30).

        under-strict: 같은 사유로 접으면 화면에서 **"재시도하면 될 실패"와 섞인다** — 이
        실패는 모델을 부르기 전에 우리가 거부한 것이라 같은 요청의 재시도는 반드시 같은
        결과이고, 사용자가 할 일은 재시도가 아니라 입력을 줄이는 것이다.
        over-strict: 다른 provider 실패(위 두 셀)가 이 사유로 새면 안 된다.
        """
        exc = ProviderError(code=ProviderErrorCode.CONTEXT_WINDOW_EXCEEDED,
                            message="context window exceeded before the call: "
                                    "input 11905 + output cap 6144 = 18049 > window 16384",
                            retryable=False)
        reason = self._fail_with(writing=_RaisingWriting(exc))
        self.assertEqual(
            reason, WritingGenerationJobFailureReason.CONTEXT_WINDOW_EXCEEDED)
        self.assertNotEqual(
            reason, WritingGenerationJobFailureReason.PROVIDER_ERROR)

    def test_writing_error_maps_to_invalid_request(self):
        self.assertEqual(
            self._fail_with(writing=_RaisingWriting(WritingError("bad"))),
            WritingGenerationJobFailureReason.INVALID_REQUEST)

    def test_invalid_report_maps_to_invalid_report(self):
        self.assertEqual(
            self._fail_with(writing=_RaisingWriting(
                InvalidCandidateReport("not an array"))),
            WritingGenerationJobFailureReason.INVALID_REPORT)

    def test_invalid_context_request_maps_to_invalid_request(self):
        self.assertEqual(
            self._fail_with(context=_RaisingContext(
                InvalidContextSearchRequest("blank query"))),
            WritingGenerationJobFailureReason.INVALID_REQUEST)

    def test_context_budget_exceeded_maps_to_context_budget_exceeded(self):
        self.assertEqual(
            self._fail_with(context=_RaisingContext(
                ContextSearchBudgetExceeded("over budget"))),
            WritingGenerationJobFailureReason.CONTEXT_BUDGET_EXCEEDED)

    def test_context_search_failed_maps_to_context_search_failed(self):
        self.assertEqual(
            self._fail_with(context=_RaisingContext(
                ContextSearchFailed(ContextSearchErrorType.BACKEND_ERROR, "down"))),
            WritingGenerationJobFailureReason.CONTEXT_SEARCH_FAILED)

    def test_unmapped_fault_maps_to_internal_catch_all(self):
        # H-2: an unmapped exception (a bug, an infra error) must still land the
        # job in a terminal FAILED state — never leave it RUNNING to livelock.
        self.assertEqual(
            self._fail_with(context=_RaisingContext(ValueError("boom"))),
            WritingGenerationJobFailureReason.INTERNAL)

    def test_persist_failure_terminates_job_not_crash(self):
        # H-1(2b): a fault in the result-persist phase (scratch down after a
        # successful generate) must reach terminal FAILED via INTERNAL, not
        # escape to crash the worker loop and re-run the expensive generate on
        # every reclaim. Under-strict: with the persist phase outside the
        # catch-all this re-raises instead of returning a FAILED job.
        c = _collaborators(scratch=_RaisingScratch())
        job = _claimed(c.jobs)
        done = _run(execute_generation_job(job, c))
        self.assertEqual(done.status, WritingGenerationJobStatus.FAILED)
        self.assertEqual(done.failure_reason,
                         WritingGenerationJobFailureReason.INTERNAL)


class ExecuteReclaimIdempotencyTest(unittest.TestCase):
    def test_reclaim_after_partial_write_leaves_one_scratch_entry(self):
        # H-3: simulate a worker that generated + wrote scratch then crashed
        # before marking the job. The prior scratch entry (same request_id) must
        # be replaced, not duplicated, on the reclaim re-run.
        c = _collaborators()
        c.scratch.save(
            project_id="p1", draft_id="d1", request_id="wr1",
            task_type="continue_scene", output_type="draft_patch",
            instruction="이어서 써줘", candidate_text="crashed 이전 시도",
            version_id="v1")
        job = _claimed(c.jobs, request="wr1")

        _run(execute_generation_job(job, c))

        entries = c.scratch.list_for_draft("p1", "d1")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].candidate_text, "생성된 장면.")


if __name__ == "__main__":
    unittest.main()
