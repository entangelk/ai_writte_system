"""Unit tests for the Phase 3B index sync worker script."""

from io import StringIO
import json
import unittest
from unittest import mock

from scripts import index_sync_worker
from services.application.app.indexing.chroma import (
    ChromaArchiveIndexMutationAdapter,
    ChromaMemoryVectorIndexAdapter,
)
from services.application.app.indexing.memory_index import (
    InMemoryMemoryVectorIndexAdapter,
    MemoryIndexSyncAdapter,
)
from services.application.app.indexing.service import (
    RecordingArchiveIndexMutationAdapter,
)


class IndexSyncWorkerScriptTest(unittest.TestCase):
    def test_main_prints_worker_summary(self):
        def fake_run_worker(args):
            self.assertEqual(args.limit, 2)
            return {
                "archive_backend": "in_memory_fake",
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
                "archive_backend": "in_memory_fake",
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


class BuildArchiveAdapterTest(unittest.TestCase):
    def test_without_chroma_host_uses_recording_fake(self):
        with mock.patch.dict(index_sync_worker.os.environ, {}, clear=True):
            adapter, backend = index_sync_worker._build_archive_adapter()

        self.assertIsInstance(adapter, RecordingArchiveIndexMutationAdapter)
        self.assertEqual(backend, "in_memory_fake")

    def test_with_chroma_host_builds_chroma_archive_adapter(self):
        sentinel_collection = object()
        with mock.patch.dict(
            index_sync_worker.os.environ,
            {"CHROMA_HOST": "chroma", "CHROMA_PORT": "8000"},
            clear=True,
        ), mock.patch(
            "services.application.app.indexing.chroma.connect_chroma_collection",
            return_value=sentinel_collection,
        ) as connect:
            adapter, backend = index_sync_worker._build_archive_adapter()

        self.assertIsInstance(adapter, ChromaArchiveIndexMutationAdapter)
        self.assertEqual(backend, "chroma")
        connect.assert_called_once_with(
            host="chroma", port=8000, collection_name="project_memory_vectors"
        )


class BuildMemoryAdapterTest(unittest.TestCase):
    # from_uri eagerly ensures Mongo indexes, so patch it — the adapter's backend
    # selection is the logic under test, not the Mongo connection.
    _REPO_PATH = (
        "services.application.app.memory.mongo_repository."
        "MongoMemoryRepository.from_uri"
    )

    def test_without_chroma_host_uses_in_memory_fake(self):
        with mock.patch.dict(
            index_sync_worker.os.environ, {}, clear=True
        ), mock.patch(self._REPO_PATH, return_value=object()):
            adapter, backend = index_sync_worker._build_memory_adapter(
                mongo_uri="mongodb://localhost:27017", mongo_db="db"
            )
        self.assertIsInstance(adapter, MemoryIndexSyncAdapter)
        self.assertIsInstance(
            adapter._vector_index, InMemoryMemoryVectorIndexAdapter
        )
        self.assertEqual(backend, "in_memory_fake")

    def test_with_chroma_host_builds_chroma_memory_adapter(self):
        sentinel_collection = object()
        with mock.patch.dict(
            index_sync_worker.os.environ,
            {"CHROMA_HOST": "chroma", "CHROMA_PORT": "8000"},
            clear=True,
        ), mock.patch(self._REPO_PATH, return_value=object()), mock.patch(
            "services.application.app.indexing.chroma.connect_chroma_collection",
            return_value=sentinel_collection,
        ) as connect:
            adapter, backend = index_sync_worker._build_memory_adapter(
                mongo_uri="mongodb://localhost:27017", mongo_db="db"
            )
        self.assertIsInstance(adapter, MemoryIndexSyncAdapter)
        self.assertIsInstance(
            adapter._vector_index, ChromaMemoryVectorIndexAdapter
        )
        self.assertEqual(backend, "chroma")
        connect.assert_called_once_with(
            host="chroma", port=8000, collection_name="memory_vectors"
        )


if __name__ == "__main__":
    unittest.main()
