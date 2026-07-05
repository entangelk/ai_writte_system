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
    smoke_succeeded,
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
                and request.url.path
                == "/projects/project-1/snapshots/snapshot-1"
                "/index/source-blocks/rebuild"
            ):
                return _json_response(
                    {"backend": "in_memory_fake", "records_written": 2}
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
                # The rebuild must run before the search so the shared index is
                # populated (source_quote can hit).
                assert (
                    "POST",
                    "/projects/project-1/snapshots/snapshot-1"
                    "/index/source-blocks/rebuild",
                ) in calls
                return _json_response(
                    {
                        "package": {
                            "degraded": False,
                            "status": "candidate",
                            "macro_items": [{"need": "current_scene"}],
                            "micro_evidence": [{"need": "source_quote"}],
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

        self.assertEqual(summary["rebuild_http_status"], 200)
        self.assertEqual(summary["rebuild_records_written"], 2)
        self.assertEqual(summary["rebuild_backend"], "in_memory_fake")
        self.assertEqual(summary["search_http_status"], 200)
        self.assertEqual(summary["gate_decision"], "pass")
        self.assertFalse(summary["degraded"])
        self.assertEqual(summary["macro_count"], 1)
        self.assertEqual(summary["micro_count"], 1)
        self.assertEqual(
            summary["plan_steps"], [{"need": "current_scene", "tools": ["mongo"]}]
        )
        self.assertTrue(summary_step_order_rebuild_before_search(calls))
        self.assertTrue(smoke_succeeded(summary))

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
            if (
                request.url.path
                == "/projects/project-1/snapshots/s1/index/source-blocks/rebuild"
            ):
                return _json_response(
                    {"backend": "in_memory_fake", "records_written": 2}
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

        self.assertEqual(summary["rebuild_http_status"], 200)
        self.assertEqual(summary["search_http_status"], 502)
        self.assertNotIn("gate_decision", summary)
        self.assertFalse(smoke_succeeded(summary))

    async def test_rebuild_failure_fails_the_smoke_before_search(self):
        async def handler(request):
            if request.method == "POST" and request.url.path == "/projects":
                return _json_response({"id": "project-1"})
            if request.url.path == "/projects/project-1/drafts":
                return _json_response({"id": "draft-1"})
            if request.url.path == "/projects/project-1/drafts/draft-1/versions":
                return _json_response(
                    {"snapshot": {"id": "s1"}, "draft_version": {"id": "v1"}}
                )
            if (
                request.url.path
                == "/projects/project-1/snapshots/s1/index/source-blocks/rebuild"
            ):
                return httpx.Response(404, json={"detail": "snapshot not found"})
            if request.url.path == "/projects/project-1/context-search":
                return _json_response(
                    {"package": {"degraded": False}, "gate": {"decision": "pass"}}
                )
            return httpx.Response(404, json={"detail": request.url.path})

        async with httpx.AsyncClient(
            base_url="http://application",
            transport=httpx.MockTransport(handler),
        ) as client:
            summary = await run_deployed_context_search_smoke(
                client, application_base_url="http://application"
            )

        # A search 200 is not enough: a failed rebuild fails the smoke, so the
        # exit rule genuinely gates on both statuses.
        self.assertEqual(summary["rebuild_http_status"], 404)
        self.assertEqual(summary["search_http_status"], 200)
        self.assertFalse(smoke_succeeded(summary))


class DeployedContextSearchSmokeScriptCliTest(unittest.TestCase):
    def test_main_exit_rule_is_two_directional(self):
        async def ok_run(args):
            return {
                "application_base_url": args.application_base_url,
                "rebuild_http_status": 200,
                "search_http_status": 200,
            }

        async def search_err_run(args):
            return {
                "application_base_url": args.application_base_url,
                "rebuild_http_status": 200,
                "search_http_status": 502,
            }

        async def rebuild_err_run(args):
            return {
                "application_base_url": args.application_base_url,
                "rebuild_http_status": 404,
                "search_http_status": 200,
            }

        out = io.StringIO()
        ok_code = main(
            ["--application-base-url", "http://application.test"],
            run_live_fn=ok_run,
            stdout=out,
        )
        search_err_code = main(
            ["--application-base-url", "http://application.test"],
            run_live_fn=search_err_run,
            stdout=io.StringIO(),
        )
        rebuild_err_code = main(
            ["--application-base-url", "http://application.test"],
            run_live_fn=rebuild_err_run,
            stdout=io.StringIO(),
        )

        self.assertEqual(ok_code, 0)
        self.assertEqual(search_err_code, 1)
        self.assertEqual(rebuild_err_code, 1)
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


def summary_step_order_rebuild_before_search(calls):
    paths = [path for _method, path in calls]
    rebuild = "/projects/project-1/snapshots/snapshot-1/index/source-blocks/rebuild"
    search = "/projects/project-1/context-search"
    return paths.index(rebuild) < paths.index(search)


def _json_response(body):
    return httpx.Response(200, json=body)


if __name__ == "__main__":
    unittest.main()
