"""Run one Phase 3B index sync worker pass."""

from __future__ import annotations

import argparse
import json
import os
import sys
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one bounded Phase 3B index sync worker pass."
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--mongo-uri", default=os.environ.get("CORE_SOT_MONGO_URI"))
    parser.add_argument(
        "--mongo-db",
        default=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_MONGO_DB),
    )
    return parser.parse_args(argv)


def run_worker(args: argparse.Namespace) -> dict[str, Any]:
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
    worker = IndexSyncWorker(
        repository=repository,
        archive_adapter=archive_adapter,
        memory_adapter=memory_adapter,
    )
    summary = worker.run_once(limit=args.limit)
    return {
        "archive_backend": archive_backend,
        "memory_backend": memory_backend,
        "entries_claimed": summary.entries_claimed,
        "entries_succeeded": summary.entries_succeeded,
        "entries_failed": summary.entries_failed,
        "entries_requeued": summary.entries_requeued,
    }


def main(
    argv: list[str] | None = None,
    *,
    run_worker_fn=run_worker,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    args = parse_args(argv)
    err = stderr if stderr is not None else sys.stderr
    try:
        summary = run_worker_fn(args)
    except ValueError as exc:
        print(str(exc), file=err)
        return 2

    stream = stdout if stdout is not None else sys.stdout
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), file=stream)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
