import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

from scripts.phase3a_rebuild_source_block_index import (
    main,
    rebuild_source_block_index,
    terminal_status,
)
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)


class Phase3ARebuildSourceBlockIndexScriptTest(unittest.TestCase):
    def test_rebuild_source_block_index_outputs_summary(self):
        core_sot, saved = _fixture()

        summary = rebuild_source_block_index(
            core_sot=core_sot,
            project_id=saved["project_id"],
            snapshot_id=saved["snapshot_id"],
        )

        self.assertEqual(summary["project_id"], saved["project_id"])
        self.assertEqual(summary["snapshot_id"], saved["snapshot_id"])
        self.assertEqual(summary["target"], "vector")
        self.assertEqual(summary["records_attempted"], 2)
        self.assertEqual(summary["records_written"], 2)
        self.assertEqual(summary["records_indexed"], 2)
        self.assertEqual(summary["records_query_visible"], 2)
        self.assertEqual(summary["records_archived"], 0)

    def test_terminal_status_requires_full_write_count(self):
        self.assertTrue(
            terminal_status({"records_attempted": 2, "records_written": 2})
        )
        self.assertFalse(
            terminal_status({"records_attempted": 2, "records_written": 1})
        )


class Phase3ARebuildSourceBlockIndexScriptCliTest(unittest.TestCase):
    def test_main_prints_summary_and_uses_terminal_exit_rule(self):
        def fake_run_rebuild(args):
            return {
                "project_id": args.project_id,
                "snapshot_id": args.snapshot_id,
                "target": "vector",
                "records_attempted": 1,
                "records_written": 1,
                "records_indexed": 1,
                "records_query_visible": 1,
                "records_archived": 0,
            }

        out = io.StringIO()

        code = main(
            ["--project-id", "project-1", "--snapshot-id", "snapshot-1"],
            run_rebuild_fn=fake_run_rebuild,
            stdout=out,
        )

        self.assertEqual(code, 0)
        body = json.loads(out.getvalue())
        self.assertEqual(body["project_id"], "project-1")
        self.assertEqual(body["snapshot_id"], "snapshot-1")

    def test_main_returns_one_when_rebuild_writes_partial_count(self):
        def fake_run_rebuild(args):
            return {
                "project_id": args.project_id,
                "snapshot_id": args.snapshot_id,
                "target": "vector",
                "records_attempted": 2,
                "records_written": 1,
                "records_indexed": 1,
                "records_query_visible": 1,
                "records_archived": 0,
            }

        out = io.StringIO()

        code = main(
            ["--project-id", "project-1", "--snapshot-id", "snapshot-1"],
            run_rebuild_fn=fake_run_rebuild,
            stdout=out,
        )

        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out.getvalue())["records_written"], 1)

    def test_main_reports_missing_mongo_uri_as_usage_error(self):
        def fake_run_rebuild(_args):
            raise ValueError("CORE_SOT_MONGO_URI or --mongo-uri is required")

        err = io.StringIO()

        code = main(
            ["--project-id", "project-1", "--snapshot-id", "snapshot-1"],
            run_rebuild_fn=fake_run_rebuild,
            stderr=err,
        )

        self.assertEqual(code, 2)
        self.assertIn("CORE_SOT_MONGO_URI", err.getvalue())


class Phase3ARebuildSourceBlockIndexScriptImportTest(unittest.TestCase):
    def test_script_file_path_invocation_can_import_repo_packages(self):
        repo_root = Path(__file__).resolve().parents[1]

        result = subprocess.run(
            [
                sys.executable,
                "scripts/phase3a_rebuild_source_block_index.py",
                "--help",
            ],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--project-id", result.stdout)
        self.assertIn("--snapshot-id", result.stdout)


def _fixture():
    core_sot = CoreSotService(InMemoryCoreSotRepository())
    project = core_sot.create_project(name="Novel")
    draft = core_sot.create_draft(project_id=project.id, title="Episode 1")
    saved = core_sot.save_draft(
        project_id=project.id,
        draft_id=draft.id,
        raw_text="첫 문장입니다.\n\n두번째 문장입니다.",
        idempotency_key="save-1",
    )
    return (
        core_sot,
        {
            "project_id": project.id,
            "snapshot_id": saved.snapshot.id,
        },
    )


if __name__ == "__main__":
    unittest.main()
