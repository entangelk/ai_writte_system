"""Self-regression for the Phase 4 context search deployed smoke script.

Exercises the HTTP orchestration against a MockTransport (no live server) and
locks the exit rule in both directions.
"""

import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

import httpx

from scripts.phase4_context_search_deployed_smoke import (
    main,
    run_deployed_context_search_smoke,
    search_succeeded,
)


class DeployedContextSearchSmokeScriptTest(unittest.IsolatedAsyncioTestCase):
    async def test_run_smoke_creates_snapshot_and_reads_package_and_gate(self):
        calls = []

        async def handler(request):
            calls.append((request.method, request.url.path))
            if request.method == "POST" and request.url.path == "/projects":
                return _json_response({"id": "project-1", "name": "Smoke"})
            if (
                request.method == "POST"
                and request.url.path == "/projects/project-1/drafts"
            ):
                return _json_response({"id": "draft-1", "project_id": "project-1"})
            if (
                request.method == "POST"
                and request.url.path
                == "/projects/project-1/drafts/draft-1/versions"
            ):
                return _json_response(
                    {
                        "snapshot": {"id": "snapshot-1"},
                        "draft_version": {"id": "version-1"},
                    }
                )
            if (
                request.method == "POST"
                and request.url.path == "/projects/project-1/context-search"
            ):
                payload = json.loads(request.content)
                # The smoke must send the current_position and the needs.
                assert payload["current_position"] == {
                    "draft_id": "draft-1",
                    "version_id": "version-1",
                }
                assert payload["needs"] == ["current_scene", "source_quote"]
                return _json_response(
                    {
                        "package": {
                            "degraded": False,
                            "status": "candidate",
                            "macro_items": [{"need": "current_scene"}],
                            "micro_evidence": [],
                            "trace": {
                                "plan": {
                                    "steps": [
                                        {
                                            "step_id": "s1",
                                            "need": "current_scene",
                                            "tools": ["mongo"],
                                            "query": "",
                                        }
                                    ]
                                }
                            },
                        },
                        "gate": {"decision": "pass", "findings": []},
                    }
                )
            return httpx.Response(404, json={"detail": request.url.path})

        async with httpx.AsyncClient(
            base_url="http://application",
            transport=httpx.MockTransport(handler),
        ) as client:
            summary = await run_deployed_context_search_smoke(
                client,
                application_base_url="http://application",
            )

        self.assertEqual(summary["search_http_status"], 200)
        self.assertEqual(summary["gate_decision"], "pass")
        self.assertFalse(summary["degraded"])
        self.assertEqual(summary["macro_count"], 1)
        self.assertEqual(summary["micro_count"], 0)
        self.assertEqual(
            summary["plan_steps"], [{"need": "current_scene", "tools": ["mongo"]}]
        )
        self.assertIn(
            ("POST", "/projects/project-1/context-search"), calls
        )

    async def test_error_status_is_captured_without_package_fields(self):
        async def handler(request):
            if request.method == "POST" and request.url.path == "/projects":
                return _json_response({"id": "project-1"})
            if request.url.path == "/projects/project-1/drafts":
                return _json_response({"id": "draft-1"})
            if request.url.path == "/projects/project-1/drafts/draft-1/versions":
                return _json_response(
                    {"snapshot": {"id": "s1"}, "draft_version": {"id": "v1"}}
                )
            if request.url.path == "/projects/project-1/context-search":
                return httpx.Response(502, json={"detail": "llm_error: boom"})
            return httpx.Response(404, json={"detail": request.url.path})

        async with httpx.AsyncClient(
            base_url="http://application",
            transport=httpx.MockTransport(handler),
        ) as client:
            summary = await run_deployed_context_search_smoke(
                client, application_base_url="http://application"
            )

        self.assertEqual(summary["search_http_status"], 502)
        self.assertNotIn("gate_decision", summary)
        self.assertFalse(search_succeeded(summary))


class DeployedContextSearchSmokeScriptCliTest(unittest.TestCase):
    def test_main_exit_rule_is_two_directional(self):
        async def ok_run(args):
            return {
                "application_base_url": args.application_base_url,
                "search_http_status": 200,
            }

        async def err_run(args):
            return {
                "application_base_url": args.application_base_url,
                "search_http_status": 502,
            }

        out = io.StringIO()
        ok_code = main(
            ["--application-base-url", "http://application.test"],
            run_live_fn=ok_run,
            stdout=out,
        )
        err_code = main(
            ["--application-base-url", "http://application.test"],
            run_live_fn=err_run,
            stdout=io.StringIO(),
        )

        self.assertEqual(ok_code, 0)
        self.assertEqual(err_code, 1)
        self.assertEqual(
            json.loads(out.getvalue())["search_http_status"], 200
        )


class DeployedContextSearchSmokeScriptImportTest(unittest.TestCase):
    def test_script_file_path_invocation_can_import_repo_packages(self):
        repo_root = Path(__file__).resolve().parents[1]

        result = subprocess.run(
            [
                sys.executable,
                "scripts/phase4_context_search_deployed_smoke.py",
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
