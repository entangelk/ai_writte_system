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
    FAKE_VECTOR_BACKEND,
    IndexSyncWorker,
    RecordingArchiveIndexMutationAdapter,
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
    worker = IndexSyncWorker(
        repository=repository,
        archive_adapter=archive_adapter,
    )
    summary = worker.run_once(limit=args.limit)
    return {
        "archive_backend": archive_backend,
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
