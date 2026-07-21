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


def _collaborators(*, context=None, writing=None, scratch=None, jobs=None):
    return GenerationCollaborators(
        context_search=context or _OkContext(),
        writing=writing or _service(_FakeProvider(content="생성된 장면.")),
        scratch=scratch or WritingScratchService(
            InMemoryWritingScratchRepository()),
        jobs=jobs or WritingGenerationJobService(
            InMemoryWritingGenerationJobRepository()),
        needs=(ContextNeed.CURRENT_SCENE,),
    )


def _claimed(jobs, *, request="wr1", draft="d1", version="v1"):
    jobs.enqueue(
        project_id="p1", draft_id=draft, request_id=request,
        task_type="continue_scene", instruction="이어서 써줘",
        draft_excerpt="앞 문단", query=None, output_length="medium",
        max_output_tokens=2048, max_tokens=4096, version_id=version)
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
