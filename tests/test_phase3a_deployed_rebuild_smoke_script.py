import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

import httpx

from scripts.phase3a_deployed_rebuild_smoke import (
    main,
    run_deployed_smoke,
    terminal_status,
)


class DeployedPhase3ARebuildSmokeScriptTest(unittest.IsolatedAsyncioTestCase):
    async def test_run_deployed_smoke_rebuilds_over_http(self):
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
                == "/projects/project-1/snapshots/snapshot-1/index/source-blocks/rebuild"
            ):
                return _json_response(_summary(project_id="project-1"))
            return httpx.Response(404, json={"detail": request.url.path})

        async with httpx.AsyncClient(
            base_url="http://application",
            transport=httpx.MockTransport(handler),
        ) as client:
            summary = await run_deployed_smoke(
                client,
                application_base_url="http://application",
            )

        self.assertEqual(summary["http_summary"]["backend"], "in_memory_fake")
        self.assertIsNone(summary["cli_summary"])
        self.assertIsNone(summary["summaries_match"])
        self.assertTrue(terminal_status(summary))
        self.assertIn(
            (
                "POST",
                "/projects/project-1/snapshots/snapshot-1/index/source-blocks/rebuild",
            ),
            calls,
        )

    async def test_run_deployed_smoke_compares_cli_summary_when_configured(self):
        async def handler(request):
            if request.method == "POST" and request.url.path == "/projects":
                return _json_response({"id": "project-1", "name": "Smoke"})
            if request.method == "POST" and request.url.path == "/projects/project-1/drafts":
                return _json_response({"id": "draft-1", "project_id": "project-1"})
            if (
                request.method == "POST"
                and request.url.path == "/projects/project-1/drafts/draft-1/versions"
            ):
                return _json_response({"snapshot": {"id": "snapshot-1"}})
            if (
                request.method == "POST"
                and request.url.path
                == "/projects/project-1/snapshots/snapshot-1/index/source-blocks/rebuild"
            ):
                return _json_response(_summary(project_id="project-1"))
            return httpx.Response(404, json={"detail": request.url.path})

        def cli_rebuild(project_id, snapshot_id):
            self.assertEqual(project_id, "project-1")
            self.assertEqual(snapshot_id, "snapshot-1")
            return _summary(project_id=project_id)

        async with httpx.AsyncClient(
            base_url="http://application",
            transport=httpx.MockTransport(handler),
        ) as client:
            summary = await run_deployed_smoke(
                client,
                application_base_url="http://application",
                cli_rebuild_fn=cli_rebuild,
            )

        self.assertTrue(summary["summaries_match"])
        self.assertTrue(terminal_status(summary))

    async def test_terminal_status_rejects_cli_http_summary_mismatch(self):
        summary = {
            "http_summary": _summary(project_id="project-1"),
            "cli_summary": {
                **_summary(project_id="project-1"),
                "records_query_visible": 1,
            },
            "summaries_match": False,
        }

        self.assertFalse(terminal_status(summary))

    async def test_terminal_status_rejects_http_partial_without_cli(self):
        summary = {
            "http_summary": {
                **_summary(project_id="project-1"),
                "records_written": 1,
            },
            "cli_summary": None,
            "summaries_match": None,
        }

        self.assertFalse(terminal_status(summary))

    async def test_terminal_status_rejects_cli_partial_even_when_summaries_match(self):
        summary = {
            "http_summary": _summary(project_id="project-1"),
            "cli_summary": {
                **_summary(project_id="project-1"),
                "records_written": 1,
            },
            "summaries_match": True,
        }

        self.assertFalse(terminal_status(summary))


class DeployedPhase3ARebuildSmokeScriptCliTest(unittest.TestCase):
    def test_main_prints_summary_and_uses_terminal_exit_rule(self):
        async def fake_run_live(args):
            return {
                "application_base_url": args.application_base_url,
                "http_summary": _summary(project_id="project-1"),
                "cli_summary": None,
                "summaries_match": None,
            }

        out = io.StringIO()

        code = main(
            ["--application-base-url", "http://application.test"],
            run_live_fn=fake_run_live,
            stdout=out,
        )

        self.assertEqual(code, 0)
        body = json.loads(out.getvalue())
        self.assertEqual(body["application_base_url"], "http://application.test")
        self.assertEqual(body["http_summary"]["records_written"], 2)

    def test_main_returns_one_when_cli_summary_does_not_match(self):
        async def fake_run_live(_args):
            return {
                "application_base_url": "http://application.test",
                "http_summary": _summary(project_id="project-1"),
                "cli_summary": {
                    **_summary(project_id="project-1"),
                    "records_written": 1,
                },
                "summaries_match": False,
            }

        code = main(
            ["--application-base-url", "http://application.test"],
            run_live_fn=fake_run_live,
            stdout=io.StringIO(),
        )

        self.assertEqual(code, 1)


class DeployedPhase3ARebuildSmokeScriptImportTest(unittest.TestCase):
    def test_script_file_path_invocation_can_import_repo_packages(self):
        repo_root = Path(__file__).resolve().parents[1]

        result = subprocess.run(
            [
                sys.executable,
                "scripts/phase3a_deployed_rebuild_smoke.py",
                "--help",
            ],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--application-base-url", result.stdout)
        self.assertIn("--mongo-uri", result.stdout)


def _summary(*, project_id):
    return {
        "project_id": project_id,
        "snapshot_id": "snapshot-1",
        "target": "vector",
        "backend": "in_memory_fake",
        "records_attempted": 2,
        "records_written": 2,
        "records_indexed": 2,
        "records_query_visible": 2,
        "records_archived": 0,
    }


def _json_response(body):
    return httpx.Response(200, json=body)


if __name__ == "__main__":
    unittest.main()
