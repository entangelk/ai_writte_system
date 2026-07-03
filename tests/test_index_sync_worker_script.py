"""Unit tests for the Phase 3B index sync worker script."""

from io import StringIO
import json
import unittest

from scripts import index_sync_worker


class IndexSyncWorkerScriptTest(unittest.TestCase):
    def test_main_prints_worker_summary(self):
        def fake_run_worker(args):
            self.assertEqual(args.limit, 2)
            return {
                "entries_claimed": 2,
                "entries_succeeded": 1,
                "entries_failed": 1,
                "entries_requeued": 1,
            }

        stdout = StringIO()

        exit_code = index_sync_worker.main(
            ["--limit", "2"],
            run_worker_fn=fake_run_worker,
            stdout=stdout,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            json.loads(stdout.getvalue()),
            {
                "entries_claimed": 2,
                "entries_succeeded": 1,
                "entries_failed": 1,
                "entries_requeued": 1,
            },
        )

    def test_main_reports_usage_error(self):
        def fake_run_worker(args):
            raise ValueError("CORE_SOT_MONGO_URI or --mongo-uri is required")

        stderr = StringIO()

        exit_code = index_sync_worker.main(
            [],
            run_worker_fn=fake_run_worker,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("CORE_SOT_MONGO_URI", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
