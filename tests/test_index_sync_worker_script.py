"""Unit tests for the Phase 3B index sync worker script."""

from io import StringIO
import json
import unittest
from unittest import mock

from scripts import index_sync_worker
from services.application.app.indexing.chroma import (
    ChromaArchiveIndexMutationAdapter,
    ChromaCandidateVectorIndexAdapter,
    ChromaMemoryVectorIndexAdapter,
)
from services.application.app.indexing.memory_index import (
    CompositeMemoryIndexSyncAdapter,
    InMemoryMemoryVectorIndexAdapter,
    MemoryIndexSyncAdapter,
)
from services.application.app.indexing.memory_lexical_index import (
    MemoryLexicalIndexSyncAdapter,
)
from services.application.app.indexing.candidate_index import (
    CandidateIndexSyncAdapter,
    CompositeCandidateIndexSyncAdapter,
    InMemoryCandidateVectorIndexAdapter,
)
from services.application.app.indexing.candidate_lexical_index import (
    CandidateLexicalIndexSyncAdapter,
)
from services.application.app.indexing.service import (
    IndexSyncWorkerSummary,
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

    def test_with_elasticsearch_url_builds_composite_memory_adapter(self):
        # §8 wiring glue: with ELASTICSEARCH_URL set, the worker fans the memory
        # drain out to a composite of the vector sink (in-memory fake here) and
        # the lexical (ES) sink, so an ES+Chroma deployment keeps both current.
        # Broken, this branch silently degrades to vector-only.
        sentinel_lexical = object()
        with mock.patch.dict(
            index_sync_worker.os.environ,
            {"ELASTICSEARCH_URL": "http://es:9200"},
            clear=True,
        ), mock.patch(self._REPO_PATH, return_value=object()), mock.patch(
            "services.application.app.indexing.memory_lexical_index."
            "connect_elasticsearch_memory_index",
            return_value=sentinel_lexical,
        ) as connect:
            adapter, backend = index_sync_worker._build_memory_adapter(
                mongo_uri="mongodb://localhost:27017", mongo_db="db"
            )
        self.assertIsInstance(adapter, CompositeMemoryIndexSyncAdapter)
        self.assertEqual(backend, "in_memory_fake+elasticsearch")
        # The composite fans out to exactly the vector sink then the lexical sink.
        self.assertEqual(len(adapter._adapters), 2)
        self.assertIsInstance(adapter._adapters[0], MemoryIndexSyncAdapter)
        self.assertIsInstance(adapter._adapters[1], MemoryLexicalIndexSyncAdapter)
        self.assertIs(adapter._adapters[1]._lexical, sentinel_lexical)
        connect.assert_called_once_with(
            url="http://es:9200", index_name="memory_lexical"
        )


class BuildCandidateAdapterTest(unittest.TestCase):
    # b-2 (G6): the candidate-index side of the worker. Mirrors
    # BuildMemoryAdapterTest — from_uri eagerly ensures Mongo indexes, so patch
    # it; the adapter's backend selection is the logic under test.
    _REPO_PATH = (
        "services.application.app.analysis.mongo_repository."
        "MongoAnalysisRepository.from_uri"
    )

    def test_without_chroma_host_uses_in_memory_fake(self):
        with mock.patch.dict(
            index_sync_worker.os.environ, {}, clear=True
        ), mock.patch(self._REPO_PATH, return_value=object()):
            adapter, backend = index_sync_worker._build_candidate_adapter(
                mongo_uri="mongodb://localhost:27017", mongo_db="db"
            )
        self.assertIsInstance(adapter, CandidateIndexSyncAdapter)
        self.assertIsInstance(
            adapter._vector_index, InMemoryCandidateVectorIndexAdapter
        )
        self.assertEqual(backend, index_sync_worker.FAKE_VECTOR_BACKEND)

    def test_with_chroma_host_builds_chroma_candidate_adapter(self):
        sentinel_collection = object()
        with mock.patch.dict(
            index_sync_worker.os.environ,
            {"CHROMA_HOST": "chroma", "CHROMA_PORT": "8000"},
            clear=True,
        ), mock.patch(self._REPO_PATH, return_value=object()), mock.patch(
            "services.application.app.indexing.chroma.connect_chroma_collection",
            return_value=sentinel_collection,
        ) as connect:
            adapter, backend = index_sync_worker._build_candidate_adapter(
                mongo_uri="mongodb://localhost:27017", mongo_db="db"
            )
        self.assertIsInstance(adapter, CandidateIndexSyncAdapter)
        self.assertIsInstance(
            adapter._vector_index, ChromaCandidateVectorIndexAdapter
        )
        self.assertIs(adapter._vector_index._collection, sentinel_collection)
        self.assertEqual(backend, index_sync_worker.CHROMA_VECTOR_BACKEND)
        connect.assert_called_once_with(
            host="chroma",
            port=8000,
            collection_name="candidate_vectors",
        )

    def test_with_elasticsearch_url_builds_composite_candidate_adapter(self):
        # With ELASTICSEARCH_URL set, the worker fans the candidate drain out to a
        # composite of the vector sink (in-memory fake here) and the lexical (ES)
        # sink. Broken, this branch silently degrades to vector-only.
        sentinel_lexical = object()
        with mock.patch.dict(
            index_sync_worker.os.environ,
            {"ELASTICSEARCH_URL": "http://es:9200"},
            clear=True,
        ), mock.patch(self._REPO_PATH, return_value=object()), mock.patch(
            "services.application.app.indexing.candidate_lexical_index."
            "connect_elasticsearch_candidate_index",
            return_value=sentinel_lexical,
        ) as connect:
            adapter, backend = index_sync_worker._build_candidate_adapter(
                mongo_uri="mongodb://localhost:27017", mongo_db="db"
            )
        self.assertIsInstance(adapter, CompositeCandidateIndexSyncAdapter)
        self.assertEqual(
            backend,
            f"{index_sync_worker.FAKE_VECTOR_BACKEND}+elasticsearch",
        )
        # The composite fans out to exactly the vector sink then the lexical sink.
        self.assertEqual(len(adapter._adapters), 2)
        self.assertIsInstance(adapter._adapters[0], CandidateIndexSyncAdapter)
        self.assertIsInstance(adapter._adapters[1], CandidateLexicalIndexSyncAdapter)
        self.assertIs(adapter._adapters[1]._lexical, sentinel_lexical)
        connect.assert_called_once_with(
            url="http://es:9200", index_name="candidate_lexical"
        )


class _FakeWorker:
    """Drain-loop test double: returns canned run_once summaries in order."""

    def __init__(self, summaries, on_call=None):
        self._summaries = list(summaries)
        self._on_call = on_call
        self.calls = 0
        self.last_stop_check = None

    def run_once(self, *, limit, stop_check=None):
        self.calls += 1
        self.last_stop_check = stop_check
        if self._on_call is not None:
            self._on_call(self.calls)
        if self._summaries:
            return self._summaries.pop(0)
        return IndexSyncWorkerSummary(0, 0, 0, 0)


class _FakeStop:
    def __init__(self):
        self.requested = False

    def is_requested(self):
        return self.requested


class WorkerLoopTest(unittest.TestCase):
    # b-6 G0=A: the --loop draining daemon. Backends are faked (build_worker_fn
    # is injected) so no Mongo/Chroma/ES is touched.
    _BACKENDS = {
        "archive_backend": "in_memory_fake",
        "memory_backend": "in_memory_fake",
        "candidate_backend": "in_memory_fake",
    }

    def test_run_loop_drains_until_stop_then_exits(self):
        # Two busy passes (entries claimed > 0), then stop is requested during
        # the second pass; the loop exits after it without idle-sleeping.
        stop = _FakeStop()
        worker = _FakeWorker(
            [IndexSyncWorkerSummary(2, 2, 0, 0), IndexSyncWorkerSummary(1, 1, 0, 0)],
            on_call=lambda n: setattr(stop, "requested", True) if n >= 2 else None,
        )
        sleeps = []
        stdout = StringIO()

        rc = index_sync_worker.run_loop(
            index_sync_worker.parse_args(["--loop"]),
            build_worker_fn=lambda args: (worker, self._BACKENDS),
            stop=stop,
            sleep_fn=lambda secs: sleeps.append(secs),
            stdout=stdout,
        )

        self.assertEqual(rc, 0)
        self.assertEqual(worker.calls, 2)
        # stop_check was threaded into run_once (G2 wiring, not just the loop guard).
        self.assertIsNotNone(worker.last_stop_check)
        self.assertEqual(sleeps, [])  # busy passes never idle-sleep
        events = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(events[0]["event"], "loop_started")
        self.assertEqual([e["event"] for e in events[1:3]], ["pass", "pass"])
        self.assertEqual(events[-1], {"event": "loop_stopped", "passes": 2})

    def test_run_loop_idles_when_no_entries_claimable(self):
        # An idle pass (entries_claimed == 0) sleeps for the interval; the sleep
        # here also flips stop so the loop exits after one pass.
        stop = _FakeStop()
        worker = _FakeWorker([IndexSyncWorkerSummary(0, 0, 0, 0)])
        sleeps = []

        def sleep_and_stop(secs):
            sleeps.append(secs)
            stop.requested = True

        rc = index_sync_worker.run_loop(
            index_sync_worker.parse_args(["--loop", "--interval", "5"]),
            build_worker_fn=lambda args: (worker, self._BACKENDS),
            stop=stop,
            sleep_fn=sleep_and_stop,
            stdout=StringIO(),
        )

        self.assertEqual(rc, 0)
        self.assertEqual(sleeps, [5.0])
        self.assertEqual(worker.calls, 1)

    def test_main_loop_mode_dispatches_run_loop(self):
        captured = {}

        def fake_run_loop(args, *, stop, stdout=None):
            captured["loop"] = True
            captured["stop"] = stop
            return 0

        rc = index_sync_worker.main(
            ["--loop"],
            run_loop_fn=fake_run_loop,
            install_signal_handlers_fn=lambda stop: None,
            stdout=StringIO(),
        )

        self.assertEqual(rc, 0)
        self.assertTrue(captured["loop"])
        self.assertIsInstance(captured["stop"], index_sync_worker._GracefulShutdown)


class ParseArgsLoopTest(unittest.TestCase):
    def test_defaults_are_one_shot_with_30s_interval(self):
        env = {
            k: v
            for k, v in index_sync_worker.os.environ.items()
            if k != "INDEX_SYNC_INTERVAL"
        }
        with mock.patch.dict(index_sync_worker.os.environ, env, clear=True):
            args = index_sync_worker.parse_args([])
        self.assertFalse(args.loop)
        self.assertEqual(args.interval, 30.0)

    def test_loop_flag_and_interval_override(self):
        args = index_sync_worker.parse_args(["--loop", "--interval", "7"])
        self.assertTrue(args.loop)
        self.assertEqual(args.interval, 7.0)


class Increment1SignalAndEdgeTest(unittest.TestCase):
    # Reinforcements closing the 2026-07-09 verification gaps 2-1 (the real
    # SIGTERM->graceful wiring was untraced in unit tests) and 2-2 (degenerate
    # + env-override branches). The integration smoke already proved the path;
    # these lock it at unit level.

    _BACKENDS = {
        "archive_backend": "in_memory_fake",
        "memory_backend": "in_memory_fake",
        "candidate_backend": "in_memory_fake",
    }

    def test_install_signal_handlers_binds_stop_request(self):
        # 2-1 wiring: SIGTERM/SIGINT must be bound to stop.request so a real
        # signal flips the flag the drain loop polls (handler registration,
        # verified without delivering a signal).
        import signal as _signal

        stop = index_sync_worker._GracefulShutdown()
        old_term = _signal.getsignal(_signal.SIGTERM)
        old_int = _signal.getsignal(_signal.SIGINT)
        try:
            index_sync_worker._install_signal_handlers(stop)
            # Bound methods are a fresh object per attribute access, so compare
            # by equality (same __func__ + __self__), not identity.
            self.assertEqual(_signal.getsignal(_signal.SIGTERM), stop.request)
            self.assertEqual(_signal.getsignal(_signal.SIGINT), stop.request)
        finally:
            _signal.signal(_signal.SIGTERM, old_term)
            _signal.signal(_signal.SIGINT, old_int)

    def test_real_sigterm_flips_stop_flag(self):
        # 2-1 end-to-end (not stubbed): a SIGTERM raised in-process is caught by
        # the installed handler and sets the graceful-stop flag that run_loop
        # polls via stop_check. CPython delivers the pending signal before the
        # next statement runs, so the flag is set before the handler is restored.
        import os
        import signal as _signal

        stop = index_sync_worker._GracefulShutdown()
        old_term = _signal.getsignal(_signal.SIGTERM)
        try:
            index_sync_worker._install_signal_handlers(stop)
            os.kill(os.getpid(), _signal.SIGTERM)
            self.assertTrue(stop.is_requested())
        finally:
            _signal.signal(_signal.SIGTERM, old_term)

    def test_run_loop_exits_immediately_if_stop_already_requested(self):
        # 2-2 degenerate path: stop already set before the first pass means the
        # loop emits loop_started/loop_stopped with zero passes and never sleeps.
        stop = index_sync_worker._GracefulShutdown()
        stop.requested = True
        worker = _FakeWorker([])
        sleeps = []
        stdout = StringIO()

        rc = index_sync_worker.run_loop(
            index_sync_worker.parse_args(["--loop"]),
            build_worker_fn=lambda args: (worker, self._BACKENDS),
            stop=stop,
            sleep_fn=lambda secs: sleeps.append(secs),
            stdout=stdout,
        )

        self.assertEqual(rc, 0)
        self.assertEqual(worker.calls, 0)  # the loop never started a pass
        self.assertEqual(sleeps, [])
        events = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([e["event"] for e in events], ["loop_started", "loop_stopped"])
        self.assertEqual(events[-1]["passes"], 0)

    def test_interval_reads_index_sync_interval_env(self):
        # 2-2 env-override branch: INDEX_SYNC_INTERVAL overrides the --interval
        # default (the compose worker service sets this env).
        with mock.patch.dict(
            index_sync_worker.os.environ,
            {"INDEX_SYNC_INTERVAL": "11"},
            clear=True,
        ):
            args = index_sync_worker.parse_args(["--loop"])
        self.assertTrue(args.loop)
        self.assertEqual(args.interval, 11.0)


if __name__ == "__main__":
    unittest.main()
