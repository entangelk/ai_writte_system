import asyncio
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

import httpx

from scripts.benchmark_writing_loop import (
    WritingLoopBenchmarkCase,
    build_report,
    main,
    run_benchmark,
    seed_benchmark_context,
    summarize_runs,
)


CASE = WritingLoopBenchmarkCase(
    name="terminal",
    instruction="pass로 끝내세요",
    candidate_text="문장.",
    finding={
        "type": "continuity", "severity": "warning", "message": "m",
        "evidence": "문장.", "recommended_decision": "revise",
    },
    expected_loop_status="pass",
    expected_stages=("revise", "report", "gate"),
)


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class _Client:
    def __init__(self, *, loop_payload, audit_payload=None, post_status=200):
        self.loop_payload = loop_payload
        self.audit_payload = audit_payload or {"total_tokens": 33, "wall_clock_ms": 1200}
        self.post_status = post_status
        self.posts = []
        self.gets = []

    async def post(self, url, *, json):
        self.posts.append((url, json))
        return _Response(self.post_status, self.loop_payload)

    async def get(self, url):
        self.gets.append(url)
        return _Response(200, self.audit_payload)


class _Clock:
    def __init__(self, *values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


class WritingLoopBenchmarkScriptTests(unittest.TestCase):
    def test_success_records_post_latency_and_persisted_aggregate_metrics(self):
        client = _Client(loop_payload={
            "loop": {"status": "pass"},
            "stages": [{"stage": value} for value in CASE.expected_stages],
            "audit_id": "wla:1", "audit_error": None,
        })

        runs = asyncio.run(run_benchmark(
            client, base_url="http://app.test/", project_id="p1", cases=(CASE,),
            repeats=1, warmups=0, now=_Clock(10.0, 11.25),
        ))

        self.assertEqual(len(runs), 1)
        run = runs[0]
        self.assertTrue(run.success)
        self.assertEqual(run.http_latency_ms, 1250.0)
        self.assertEqual(run.total_tokens, 33)
        self.assertEqual(run.loop_wall_clock_ms, 1200)
        self.assertEqual(client.posts[0][0], "http://app.test/projects/p1/writing/revise-and-gate")
        self.assertTrue(client.posts[0][1]["persist_audit"])
        self.assertTrue(client.gets[0].endswith("/wla:1"))

    def test_current_position_is_forwarded_to_each_benchmark_request(self):
        client = _Client(loop_payload={
            "loop": {"status": "pass"},
            "stages": [{"stage": value} for value in CASE.expected_stages],
            "audit_id": "wla:1", "audit_error": None,
        })

        asyncio.run(run_benchmark(
            client, base_url="http://app.test", project_id="p1", cases=(CASE,),
            repeats=1, warmups=0, current_position={"draft_id": "d1", "version_id": "v1"},
            now=_Clock(0, 1),
        ))

        self.assertEqual(
            client.posts[0][1]["current_position"],
            {"draft_id": "d1", "version_id": "v1"},
        )

    def test_seed_benchmark_context_creates_draft_and_version_before_measurement(self):
        class _SeedClient:
            def __init__(self):
                self.posts = []

            async def post(self, url, *, json):
                self.posts.append((url, json))
                if url.endswith("/drafts"):
                    return _Response(200, {"id": "draft-1"})
                return _Response(200, {"draft_version": {"id": "version-1"}})

        client = _SeedClient()
        position = asyncio.run(seed_benchmark_context(
            client, base_url="http://app.test/", project_id="p1"
        ))

        self.assertEqual(position, {"draft_id": "draft-1", "version_id": "version-1"})
        self.assertEqual(client.posts[0][0], "http://app.test/projects/p1/drafts")
        self.assertEqual(client.posts[1][0], "http://app.test/projects/p1/drafts/draft-1/versions")
        self.assertIn("raw_text", client.posts[1][1])

    def test_unexpected_trace_fails_instead_of_being_measured_as_requested_case(self):
        client = _Client(loop_payload={
            "loop": {"status": "pass"},
            "stages": [{"stage": "revise"}, {"stage": "report"}],
            "audit_id": "wla:1", "audit_error": None,
        })

        run = asyncio.run(run_benchmark(
            client, base_url="http://app.test", project_id="p1", cases=(CASE,),
            repeats=1, warmups=0, now=_Clock(0.0, 0.1),
        ))[0]

        self.assertFalse(run.success)
        self.assertEqual(run.error_code, "unexpected_loop_trace")
        self.assertEqual(run.total_tokens, 33)

    def test_warmup_success_is_excluded(self):
        success = _Client(loop_payload={
            "loop": {"status": "pass"},
            "stages": [{"stage": value} for value in CASE.expected_stages],
            "audit_id": "wla:1", "audit_error": None,
        })
        runs = asyncio.run(run_benchmark(
            success, base_url="http://app.test", project_id="p1", cases=(CASE,),
            repeats=1, warmups=1, now=_Clock(0, 1, 2, 3),
        ))
        self.assertEqual([run.iteration for run in runs], [1])

    def test_warmup_http_failure_is_retained_and_measured_run_continues(self):
        # Under-strict: deleting run_benchmark's `if not run.success` append
        # drops iteration 0 and fails. Over-strict: the measured iteration must
        # still run and be recorded after a failed warmup.
        failure = _Client(loop_payload={"detail": "gateway unavailable"}, post_status=503)
        runs = asyncio.run(run_benchmark(
            failure, base_url="http://app.test", project_id="p1", cases=(CASE,),
            repeats=1, warmups=1, now=_Clock(0, 1, 2, 3),
        ))
        self.assertEqual([run.iteration for run in runs], [0, 1])
        self.assertTrue(all(not run.success for run in runs))
        self.assertEqual([run.error_code for run in runs], ["http_503", "http_503"])

    def test_http_and_audit_envelope_failures_become_raw_failure_runs(self):
        for client, error_code in (
            (_Client(loop_payload={"detail": "bad gateway"}, post_status=502), "http_502"),
            (_Client(loop_payload={
                "loop": {"status": "pass"},
                "stages": [{"stage": value} for value in CASE.expected_stages],
                "audit_id": None, "audit_error": "audit down",
            }), "audit_missing"),
        ):
            with self.subTest(error_code=error_code):
                run = asyncio.run(run_benchmark(
                    client, base_url="http://app.test", project_id="p1", cases=(CASE,),
                    repeats=1, warmups=0, now=_Clock(0, 1),
                ))[0]
                self.assertFalse(run.success)
                self.assertEqual(run.error_code, error_code)

    def test_summary_uses_only_successes_for_p95_and_tokens(self):
        from scripts.benchmark_writing_loop import WritingLoopBenchmarkRun

        summary = summarize_runs((
            WritingLoopBenchmarkRun("x", 1, True, 100.0, 10, 90),
            WritingLoopBenchmarkRun("x", 2, True, 300.0, 12, 270),
            WritingLoopBenchmarkRun("x", 3, False, 5000.0, error_code="unexpected_loop_trace"),
        ))["x"]
        self.assertEqual(summary["http_latency_ms_p95"], 300.0)
        self.assertEqual(summary["loop_wall_clock_ms_p95"], 270)
        self.assertEqual(summary["max_total_tokens"], 12)
        self.assertEqual(summary["error_codes"], ["unexpected_loop_trace"])

    def test_report_preserves_fixture_hash_and_raw_branch_trace(self):
        from scripts.benchmark_writing_loop import WritingLoopBenchmarkRun

        report = build_report(
            base_url="http://app.test", project_id="p1", model="gemma", quant="Q4_0",
            compose_revision="abc123", repeats=1, warmups=0,
            cases=(CASE,), runs=(WritingLoopBenchmarkRun(
                "terminal", 1, True, 12.0, 33, 10, "pass", CASE.expected_stages, 200
            ),),
        )
        self.assertEqual(len(report["metadata"]["fixture_sha256"]), 64)
        self.assertEqual(report["metadata"]["model"], "gemma")
        self.assertEqual(report["metadata"]["quant"], "Q4_0")
        self.assertEqual(report["metadata"]["compose_revision"], "abc123")
        self.assertEqual(report["runs"][0]["stage_trace"], list(CASE.expected_stages))

    def test_main_wires_cli_arguments(self):
        captured = {}

        async def fake_run_live(args):
            captured["args"] = args
            return {"metadata": {}, "fixtures": [], "summary": {}, "runs": []}

        out = io.StringIO()
        main([
            "--application-base-url", "http://app.test", "--project-id", "p1",
            "--model", "gemma", "--quant", "Q4_0", "--compose-revision", "abc123",
            "--repeats", "2", "--warmups", "0", "--timeout", "9",
        ], run_live=fake_run_live, stdout=out)
        self.assertEqual(captured["args"].project_id, "p1")
        self.assertEqual(captured["args"].compose_revision, "abc123")
        self.assertEqual(captured["args"].repeats, 2)
        self.assertEqual(json.loads(out.getvalue())["summary"], {})

    def test_script_path_can_import_repo_packages(self):
        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "scripts/benchmark_writing_loop.py", "--help"],
            cwd=repo_root, check=False, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--project-id", result.stdout)


if __name__ == "__main__":
    unittest.main()
