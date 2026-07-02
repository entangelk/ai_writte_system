import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

import httpx

from scripts.phase2a_deployed_e2e_smoke import (
    main,
    run_deployed_smoke,
    terminal_status,
)


class DeployedPhase2ASmokeScriptTest(unittest.IsolatedAsyncioTestCase):
    async def test_run_deployed_smoke_prepares_source_refs_and_runs_job(self):
        calls = []

        async def handler(request):
            calls.append((request.method, request.url.path))
            if request.method == "POST" and request.url.path == "/projects":
                return _json_response({"id": "project-1", "name": "Smoke"})
            if request.method == "POST" and request.url.path == "/projects/project-1/drafts":
                return _json_response({"id": "draft-1", "project_id": "project-1"})
            if (
                request.method == "POST"
                and request.url.path == "/projects/project-1/drafts/draft-1/versions"
            ):
                return _json_response(
                    {
                        "snapshot": {"id": "snapshot-1"},
                        "draft_version": {"id": "version-1"},
                    }
                )
            if (
                request.method == "POST"
                and request.url.path
                == "/projects/project-1/snapshots/snapshot-1/source-refs"
            ):
                payload = json.loads(request.content)
                index = len(
                    [
                        call
                        for call in calls
                        if call
                        == (
                            "POST",
                            "/projects/project-1/snapshots/snapshot-1/source-refs",
                        )
                    ]
                )
                quote = ("민아", "파란 편지", "준호")[index - 1]
                return _json_response(
                    {
                        "id": f"source-ref-{index}",
                        "project_id": "project-1",
                        "snapshot_id": "snapshot-1",
                        "block_id": "block-1",
                        "start_offset": payload["start_offset"],
                        "end_offset": payload["end_offset"],
                        "quote": quote,
                        "content_hash": "hash",
                    }
                )
            if (
                request.method == "POST"
                and request.url.path == "/projects/project-1/analysis/jobs"
            ):
                return _json_response({"job": {"id": "analysis-job-1"}})
            if (
                request.method == "POST"
                and request.url.path
                == "/projects/project-1/analysis/jobs/analysis-job-1/run"
            ):
                return _json_response(
                    {"job": {"id": "analysis-job-1", "status": "succeeded"}}
                )
            if (
                request.method == "GET"
                and request.url.path
                == "/projects/project-1/analysis/jobs/analysis-job-1"
            ):
                return _json_response(
                    {
                        "id": "analysis-job-1",
                        "project_id": "project-1",
                        "status": "succeeded",
                    }
                )
            if (
                request.method == "GET"
                and request.url.path
                == "/projects/project-1/analysis/jobs/analysis-job-1/candidates"
            ):
                return _json_response(
                    {
                        "candidates": [
                            {
                                "id": "candidate-1",
                                "candidate_type": "character_observation",
                            }
                        ]
                    }
                )
            return httpx.Response(404, json={"detail": request.url.path})

        async with httpx.AsyncClient(
            base_url="http://application",
            transport=httpx.MockTransport(handler),
        ) as client:
            summary = await run_deployed_smoke(
                client,
                application_base_url="http://application",
            )

        self.assertEqual(summary["run_http_status"], 200)
        self.assertEqual(summary["final_job"]["status"], "succeeded")
        self.assertEqual(summary["candidate_count"], 1)
        self.assertEqual(
            [ref["quote"] for ref in summary["source_refs"]],
            ["민아", "파란 편지", "준호"],
        )
        self.assertIn(
            (
                "POST",
                "/projects/project-1/snapshots/snapshot-1/source-refs",
            ),
            calls,
        )

    async def test_terminal_status_rejects_non_terminal_job(self):
        self.assertFalse(terminal_status({"final_job": {"status": "pending"}}))


class DeployedPhase2ASmokeScriptCliTest(unittest.TestCase):
    def test_main_prints_summary_and_uses_terminal_exit_rule(self):
        async def fake_run_live(args):
            return {
                "application_base_url": args.application_base_url,
                "final_job": {"status": "failed"},
            }

        out = io.StringIO()

        code = main(
            ["--application-base-url", "http://application.test"],
            run_live_fn=fake_run_live,
            stdout=out,
        )

        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(out.getvalue())["application_base_url"],
            "http://application.test",
        )


class DeployedPhase2ASmokeScriptImportTest(unittest.TestCase):
    def test_script_file_path_invocation_can_import_repo_packages(self):
        repo_root = Path(__file__).resolve().parents[1]

        result = subprocess.run(
            [
                sys.executable,
                "scripts/phase2a_deployed_e2e_smoke.py",
                "--help",
            ],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--application-base-url", result.stdout)


def _json_response(body):
    return httpx.Response(200, json=body)


if __name__ == "__main__":
    unittest.main()
