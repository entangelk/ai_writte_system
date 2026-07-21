"""Async generation worker CLI/loop (async-pad 증분 2b, scripts/).

The per-job execution is covered in test_writing_generation_worker; here the
daemon shell: run_pass claims+executes exactly one job (or None when idle), the
loop drains until the stop flag and idle-sleeps only when nothing was claimable,
and an unconfigured gateway exits non-zero instead of running.
"""

import argparse
import io
import json
import unittest

from services.application.app.context_search.models import ContextNeed
from services.application.app.writing.generation_job import (
    InMemoryWritingGenerationJobRepository,
    WritingGenerationJobService,
    WritingGenerationJobStatus,
)
from services.application.app.writing.generation_worker import (
    GenerationCollaborators,
)
from services.application.app.writing.scratch import (
    InMemoryWritingScratchRepository,
    WritingScratchService,
)

from scripts import generation_job_worker as worker

from tests.test_writing import _FakeProvider, _package, _service


class _OkContext:
    async def build_context_package(self, request):
        return _package()


def _collaborators(jobs):
    return GenerationCollaborators(
        context_search=_OkContext(),
        writing=_service(_FakeProvider(content="생성물.")),
        scratch=WritingScratchService(InMemoryWritingScratchRepository()),
        jobs=jobs,
        needs=(ContextNeed.CURRENT_SCENE,),
    )


def _events(buf):
    return [json.loads(line) for line in buf.getvalue().splitlines()]


class RunPassTest(unittest.TestCase):
    def test_run_pass_executes_one_job_and_reports_status(self):
        jobs = WritingGenerationJobService(
            InMemoryWritingGenerationJobRepository())
        jobs.enqueue(project_id="p1", draft_id="d1", request_id="wr1",
                     task_type="continue_scene", instruction="이어서",
                     draft_excerpt="", query=None, output_length="medium",
                     max_output_tokens=2048, max_tokens=4096, version_id="v1")
        result = worker.run_pass(_collaborators(jobs))
        self.assertEqual(result["status"],
                         WritingGenerationJobStatus.SUCCEEDED.value)
        self.assertIsNone(result["failure_reason"])

    def test_run_pass_returns_none_when_no_job(self):
        jobs = WritingGenerationJobService(
            InMemoryWritingGenerationJobRepository())
        self.assertIsNone(worker.run_pass(_collaborators(jobs)))


class RunLoopTest(unittest.TestCase):
    def test_loop_drains_then_stops_and_sleeps_only_when_idle(self):
        stop = worker._GracefulShutdown()
        # two jobs, then idle; stop after the third pass.
        script = [{"status": "succeeded", "failure_reason": None},
                  {"status": "failed", "failure_reason": "internal"},
                  None]
        seen = {"i": 0}
        sleeps = []

        def fake_pass(_collaborators):
            result = script[seen["i"]]
            seen["i"] += 1
            if seen["i"] >= len(script):
                stop.request()
            return result

        buf = io.StringIO()
        rc = worker.run_loop(
            argparse.Namespace(loop=True, interval=7),
            build_fn=lambda: object(),
            run_pass_fn=fake_pass,
            stop=stop,
            sleep_fn=lambda s: sleeps.append(s),
            stdout=buf,
        )
        self.assertEqual(rc, 0)
        events = _events(buf)
        self.assertEqual(events[0]["event"], "loop_started")
        self.assertEqual(events[-1], {"event": "loop_stopped", "passes": 3})
        # only the idle (None) pass sleeps; the two busy passes do not.
        self.assertEqual(sleeps, [])  # the idle pass set stop → loop breaks before sleep

    def test_loop_idle_pass_sleeps_when_not_stopping(self):
        stop = worker._GracefulShutdown()
        seen = {"i": 0}
        sleeps = []

        def fake_pass(_collaborators):
            seen["i"] += 1
            if seen["i"] >= 2:
                stop.request()
            return None  # always idle

        worker.run_loop(
            argparse.Namespace(loop=True, interval=5),
            build_fn=lambda: object(),
            run_pass_fn=fake_pass,
            stop=stop,
            sleep_fn=lambda s: sleeps.append(s),
            stdout=io.StringIO(),
        )
        # first idle pass (not yet stopping) sleeps; second sets stop → no sleep.
        self.assertEqual(sleeps, [5])


class GatewayGatingTest(unittest.TestCase):
    def test_unconfigured_gateway_exits_nonzero(self):
        err = io.StringIO()
        rc = worker.main(["--loop"], build_fn=lambda: None, stderr=err)
        self.assertEqual(rc, 2)
        self.assertIn("LLM_GATEWAY_BASE_URL", err.getvalue())

    def test_one_shot_runs_a_single_pass(self):
        out = io.StringIO()
        rc = worker.main(
            [],
            build_fn=lambda: object(),
            run_pass_fn=lambda c: {"job_id": "wgj:1", "status": "succeeded",
                                   "failure_reason": None},
            stdout=out,
        )
        self.assertEqual(rc, 0)
        self.assertIn("wgj:1", out.getvalue())


if __name__ == "__main__":
    unittest.main()
