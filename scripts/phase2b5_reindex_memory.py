"""Phase 2B.5 backfill: reindex existing canonical memories into memory_vectors.

Going forward every canonical mint (promote / auto-promote / apply) enqueues a
MEMORY_UPSERTED reindex, so the index stays current. This one-shot script covers
memories that existed *before* that wiring: it lists a project's canonical
``MemoryEntry`` records and upserts their vectors directly (bypassing the outbox
— D7). Superseded versions are skipped, so the result is canonical-only.

Real Chroma when CHROMA_HOST is set (writes the deployed memory_vectors
collection), else the in-memory fake (a dry run — records are lost on exit, so
the summary still reports what *would* be written). Live run is sandbox-external.

    python3 scripts/phase2b5_reindex_memory.py --project-id P --mongo-uri URI
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, TextIO

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.application.app.indexing.memory_index import (
    InMemoryMemoryVectorIndexAdapter,
    MEMORY_VECTOR_COLLECTION,
    build_memory_index_record,
    derive_memory_index_text,
)
from services.application.app.indexing.service import (
    CHROMA_VECTOR_BACKEND,
    FAKE_VECTOR_BACKEND,
    DeterministicFakeEmbeddingProvider,
)
from services.application.app.memory.models import MemoryStatus

DEFAULT_MONGO_DB = "ai_writing_system"


def _build_embedding_provider():
    base_url = os.environ.get("EMBEDDING_SERVICE_URL")
    if not base_url:
        return DeterministicFakeEmbeddingProvider()
    from services.application.app.indexing.embedding import RemoteEmbeddingProvider

    return RemoteEmbeddingProvider(
        base_url=base_url,
        timeout_seconds=float(os.environ.get("EMBEDDING_TIMEOUT_SECONDS", "30")),
        expected_dimensions=int(os.environ.get("EMBEDDING_DIMENSIONS", "1024")),
    )


def _build_memory_vector_index() -> tuple[object, str]:
    host = os.environ.get("CHROMA_HOST")
    if not host:
        return InMemoryMemoryVectorIndexAdapter(), FAKE_VECTOR_BACKEND
    from services.application.app.indexing.chroma import (
        ChromaMemoryVectorIndexAdapter,
        connect_chroma_collection,
    )

    return (
        ChromaMemoryVectorIndexAdapter(
            connect_chroma_collection(
                host=host,
                port=int(os.environ.get("CHROMA_PORT", "8000")),
                collection_name=os.environ.get(
                    "CHROMA_MEMORY_COLLECTION", MEMORY_VECTOR_COLLECTION
                ),
            )
        ),
        CHROMA_VECTOR_BACKEND,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reindex a project's canonical memories into memory_vectors."
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--mongo-uri", default=os.environ.get("CORE_SOT_MONGO_URI"))
    parser.add_argument(
        "--mongo-db",
        default=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_MONGO_DB),
    )
    return parser.parse_args(argv)


def run_reindex(args: argparse.Namespace) -> dict[str, Any]:
    if not args.mongo_uri:
        raise ValueError("CORE_SOT_MONGO_URI or --mongo-uri is required")

    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
    from services.application.app.memory.mongo_repository import MongoMemoryRepository
    from services.application.app.memory.service import MemoryService

    memory = MemoryService(
        MongoMemoryRepository.from_uri(
            args.mongo_uri, db_name=args.mongo_db or DEFAULT_DB_NAME
        )
    )
    embeddings = _build_embedding_provider()
    vector_index, backend = _build_memory_vector_index()

    memories = memory.list_memories(project_id=args.project_id)
    canonical = [m for m in memories if m.status is MemoryStatus.CANONICAL]
    records = []
    for entry in canonical:
        text = derive_memory_index_text(entry.memory_type, entry.payload)
        records.append(
            build_memory_index_record(
                entry, text=text, vector=embeddings.embed(text)
            )
        )
    written = vector_index.upsert_memory_records(tuple(records))
    return {
        "project_id": args.project_id,
        "memory_backend": backend,
        "canonical_count": len(canonical),
        "records_written": written,
    }


def main(
    argv: list[str] | None = None,
    *,
    run_reindex_fn=run_reindex,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    args = parse_args(argv)
    err = stderr if stderr is not None else sys.stderr
    try:
        summary = run_reindex_fn(args)
    except ValueError as exc:
        print(str(exc), file=err)
        return 2

    stream = stdout if stdout is not None else sys.stdout
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), file=stream)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
