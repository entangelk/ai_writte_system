"""Run one Phase 3B index sync worker pass."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, TextIO

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.application.app.indexing.service import (
    CHROMA_VECTOR_BACKEND,
    DeterministicFakeEmbeddingProvider,
    FAKE_VECTOR_BACKEND,
    IndexSyncWorker,
    RecordingArchiveIndexMutationAdapter,
)
from services.application.app.indexing.memory_index import (
    InMemoryMemoryVectorIndexAdapter,
    MemoryIndexSyncAdapter,
    MEMORY_VECTOR_COLLECTION,
)

DEFAULT_MONGO_DB = "ai_writing_system"


def _build_archive_adapter() -> tuple[object, str]:
    # Real persistent Chroma when CHROMA_HOST is set (same env convention as
    # create_app's B.4 wiring), else the recording-only fake so the worker still
    # exercises the status/log lifecycle without a Chroma dependency. chromadb is
    # imported lazily inside connect_chroma_collection.
    host = os.environ.get("CHROMA_HOST")
    if not host:
        return RecordingArchiveIndexMutationAdapter(), FAKE_VECTOR_BACKEND
    from services.application.app.indexing.chroma import (
        DEFAULT_COLLECTION_NAME,
        ChromaArchiveIndexMutationAdapter,
        connect_chroma_collection,
    )

    collection = connect_chroma_collection(
        host=host,
        port=int(os.environ.get("CHROMA_PORT", "8000")),
        collection_name=os.environ.get("CHROMA_COLLECTION", DEFAULT_COLLECTION_NAME),
    )
    return ChromaArchiveIndexMutationAdapter(collection), CHROMA_VECTOR_BACKEND


def _build_embedding_provider():
    # Real embedding service when EMBEDDING_SERVICE_URL is set (same convention as
    # create_app), else the deterministic fake.
    base_url = os.environ.get("EMBEDDING_SERVICE_URL")
    if not base_url:
        return DeterministicFakeEmbeddingProvider()
    from services.application.app.indexing.embedding import RemoteEmbeddingProvider

    return RemoteEmbeddingProvider(
        base_url=base_url,
        timeout_seconds=float(os.environ.get("EMBEDDING_TIMEOUT_SECONDS", "30")),
        expected_dimensions=int(os.environ.get("EMBEDDING_DIMENSIONS", "1024")),
    )


def _build_memory_adapter(
    *, mongo_uri: str, mongo_db: str
) -> tuple[MemoryIndexSyncAdapter, str]:
    # Phase 2B.5 (D3=B): the memory-reindex side of the worker. Loads the memory a
    # MEMORY_UPSERTED entry points at (Mongo-backed) and reindexes it into the
    # memory_vectors collection — real Chroma when CHROMA_HOST is set, else the
    # in-memory fake so the worker still exercises the lifecycle without Chroma.
    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
    from services.application.app.memory.mongo_repository import MongoMemoryRepository
    from services.application.app.memory.service import MemoryService

    memory = MemoryService(
        MongoMemoryRepository.from_uri(mongo_uri, db_name=mongo_db or DEFAULT_DB_NAME)
    )
    embeddings = _build_embedding_provider()

    host = os.environ.get("CHROMA_HOST")
    if not host:
        vector_index = InMemoryMemoryVectorIndexAdapter()
        backend = FAKE_VECTOR_BACKEND
    else:
        from services.application.app.indexing.chroma import (
            ChromaMemoryVectorIndexAdapter,
            connect_chroma_collection,
        )

        vector_index = ChromaMemoryVectorIndexAdapter(
            connect_chroma_collection(
                host=host,
                port=int(os.environ.get("CHROMA_PORT", "8000")),
                collection_name=os.environ.get(
                    "CHROMA_MEMORY_COLLECTION", MEMORY_VECTOR_COLLECTION
                ),
            )
        )
        backend = CHROMA_VECTOR_BACKEND
    adapter = MemoryIndexSyncAdapter(
        memory_service=memory, embeddings=embeddings, vector_index=vector_index
    )
    # §8 lexical leg: when ELASTICSEARCH_URL is set, fan the memory drain out to
    # the Elasticsearch index alongside the vector index so both stay current.
    es_url = os.environ.get("ELASTICSEARCH_URL")
    if es_url:
        from services.application.app.indexing.memory_index import (
            CompositeMemoryIndexSyncAdapter,
        )
        from services.application.app.indexing.memory_lexical_index import (
            MEMORY_LEXICAL_INDEX,
            MemoryLexicalIndexSyncAdapter,
            connect_elasticsearch_memory_index,
        )

        lexical_adapter = MemoryLexicalIndexSyncAdapter(
            memory_service=memory,
            lexical_index=connect_elasticsearch_memory_index(
                url=es_url,
                index_name=os.environ.get(
                    "ELASTICSEARCH_MEMORY_INDEX", MEMORY_LEXICAL_INDEX
                ),
            ),
        )
        return (
            CompositeMemoryIndexSyncAdapter((adapter, lexical_adapter)),
            f"{backend}+elasticsearch",
        )
    return adapter, backend


def _build_candidate_adapter(
    *, mongo_uri: str, mongo_db: str
) -> tuple[object, str]:
    # b-2: the candidate-index side of the worker. Loads the candidate a
    # CANDIDATE_UPSERTED entry points at (Mongo-backed) and indexes it into the
    # candidate_vectors collection (+ candidate_lexical ES index when configured)
    # — real backends when CHROMA_HOST / ELASTICSEARCH_URL are set, else the
    # in-memory fake so the worker still exercises the lifecycle.
    from services.application.app.analysis.mongo_repository import (
        MongoAnalysisRepository,
    )
    from services.application.app.analysis.service import AnalysisService
    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
    from services.application.app.indexing.candidate_index import (
        CANDIDATE_VECTOR_COLLECTION,
        CandidateIndexSyncAdapter,
        InMemoryCandidateVectorIndexAdapter,
    )

    analysis = AnalysisService(
        MongoAnalysisRepository.from_uri(mongo_uri, db_name=mongo_db or DEFAULT_DB_NAME)
    )
    embeddings = _build_embedding_provider()

    host = os.environ.get("CHROMA_HOST")
    if not host:
        vector_index = InMemoryCandidateVectorIndexAdapter()
        backend = FAKE_VECTOR_BACKEND
    else:
        from services.application.app.indexing.chroma import (
            ChromaCandidateVectorIndexAdapter,
            connect_chroma_collection,
        )

        vector_index = ChromaCandidateVectorIndexAdapter(
            connect_chroma_collection(
                host=host,
                port=int(os.environ.get("CHROMA_PORT", "8000")),
                collection_name=os.environ.get(
                    "CHROMA_CANDIDATE_COLLECTION", CANDIDATE_VECTOR_COLLECTION
                ),
            )
        )
        backend = CHROMA_VECTOR_BACKEND
    adapter = CandidateIndexSyncAdapter(
        analysis_service=analysis, embeddings=embeddings, vector_index=vector_index
    )
    es_url = os.environ.get("ELASTICSEARCH_URL")
    if es_url:
        from services.application.app.indexing.candidate_index import (
            CompositeCandidateIndexSyncAdapter,
        )
        from services.application.app.indexing.candidate_lexical_index import (
            CANDIDATE_LEXICAL_INDEX,
            CandidateLexicalIndexSyncAdapter,
            connect_elasticsearch_candidate_index,
        )

        lexical_adapter = CandidateLexicalIndexSyncAdapter(
            analysis_service=analysis,
            lexical_index=connect_elasticsearch_candidate_index(
                url=es_url,
                index_name=os.environ.get(
                    "ELASTICSEARCH_CANDIDATE_INDEX", CANDIDATE_LEXICAL_INDEX
                ),
            ),
        )
        return (
            CompositeCandidateIndexSyncAdapter((adapter, lexical_adapter)),
            f"{backend}+elasticsearch",
        )
    return adapter, backend


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a Phase 3B index sync worker pass (one-shot by default; "
        "--loop runs a draining daemon until SIGTERM)."
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--mongo-uri", default=os.environ.get("CORE_SOT_MONGO_URI"))
    parser.add_argument(
        "--mongo-db",
        default=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_MONGO_DB),
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run as a long-lived draining daemon: loop run_once until SIGTERM/SIGINT.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.environ.get("INDEX_SYNC_INTERVAL", "30")),
        help="Seconds to idle-sleep between drain passes when no entry is claimable.",
    )
    return parser.parse_args(argv)


def _build_index_sync_worker(
    args: argparse.Namespace,
) -> tuple[IndexSyncWorker, dict[str, str]]:
    if not args.mongo_uri:
        raise ValueError("CORE_SOT_MONGO_URI or --mongo-uri is required")
    if args.limit < 1:
        raise ValueError("limit must be positive")

    from services.application.app.indexing.mongo_repository import (
        MongoIndexSyncRepository,
    )

    repository = MongoIndexSyncRepository.from_uri(
        args.mongo_uri,
        db_name=args.mongo_db,
    )
    archive_adapter, archive_backend = _build_archive_adapter()
    memory_adapter, memory_backend = _build_memory_adapter(
        mongo_uri=args.mongo_uri, mongo_db=args.mongo_db
    )
    candidate_adapter, candidate_backend = _build_candidate_adapter(
        mongo_uri=args.mongo_uri, mongo_db=args.mongo_db
    )
    worker = IndexSyncWorker(
        repository=repository,
        archive_adapter=archive_adapter,
        memory_adapter=memory_adapter,
        candidate_adapter=candidate_adapter,
    )
    backends = {
        "archive_backend": archive_backend,
        "memory_backend": memory_backend,
        "candidate_backend": candidate_backend,
    }
    return worker, backends


def run_worker(args: argparse.Namespace) -> dict[str, Any]:
    worker, backends = _build_index_sync_worker(args)
    summary = worker.run_once(limit=args.limit)
    return {
        **backends,
        "entries_claimed": summary.entries_claimed,
        "entries_succeeded": summary.entries_succeeded,
        "entries_failed": summary.entries_failed,
        "entries_requeued": summary.entries_requeued,
    }


class _GracefulShutdown:
    """Stop flag set by SIGTERM/SIGINT so the drain loop exits at the next entry
    boundary (the in-flight entry finishes first). The atomic outbox claim
    (find_one_and_update + lease) is what makes concurrent/replica execution
    safe; this only governs orderly shutdown of a single loop (b-6 G2=A)."""

    def __init__(self) -> None:
        self.requested = False

    def request(self, *_args: object) -> None:
        self.requested = True

    def is_requested(self) -> bool:
        return self.requested


def _install_signal_handlers(stop: _GracefulShutdown) -> None:
    # SIGTERM (compose stop) and SIGINT (ctrl-c) both request a graceful exit.
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop.request)


def run_loop(
    args: argparse.Namespace,
    *,
    build_worker_fn=_build_index_sync_worker,
    stop: _GracefulShutdown,
    sleep_fn=time.sleep,
    stdout: TextIO | None = None,
) -> int:
    # b-6 G0=A: a long-lived draining daemon. Builds the worker (and its sink
    # adapters) ONCE, then loops run_once — draining immediately while entries
    # are claimable and idle-sleeping when the queue is empty. stop_check is
    # threaded into run_once so SIGTERM finishes the in-flight entry then exits
    # at the next claim boundary (G2 graceful shutdown).
    worker, backends = build_worker_fn(args)
    stream = stdout if stdout is not None else sys.stdout
    print(
        json.dumps(
            {
                "event": "loop_started",
                "limit": args.limit,
                "interval_seconds": args.interval,
                **backends,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        file=stream,
    )
    stream.flush()
    passes = 0
    while True:
        if stop.is_requested():
            break
        summary = worker.run_once(limit=args.limit, stop_check=stop.is_requested)
        passes += 1
        print(
            json.dumps(
                {
                    "event": "pass",
                    "pass": passes,
                    "entries_claimed": summary.entries_claimed,
                    "entries_succeeded": summary.entries_succeeded,
                    "entries_failed": summary.entries_failed,
                    "entries_requeued": summary.entries_requeued,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=stream,
        )
        stream.flush()
        if stop.is_requested():
            break
        if summary.entries_claimed == 0:
            sleep_fn(args.interval)
    print(
        json.dumps(
            {"event": "loop_stopped", "passes": passes},
            ensure_ascii=False,
            sort_keys=True,
        ),
        file=stream,
    )
    stream.flush()
    return 0


def main(
    argv: list[str] | None = None,
    *,
    run_worker_fn=run_worker,
    run_loop_fn=run_loop,
    install_signal_handlers_fn=_install_signal_handlers,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    args = parse_args(argv)
    err = stderr if stderr is not None else sys.stderr
    try:
        if args.loop:
            stop = _GracefulShutdown()
            install_signal_handlers_fn(stop)
            return run_loop_fn(args, stop=stop, stdout=stdout)
        summary = run_worker_fn(args)
    except ValueError as exc:
        print(str(exc), file=err)
        return 2

    stream = stdout if stdout is not None else sys.stdout
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), file=stream)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
