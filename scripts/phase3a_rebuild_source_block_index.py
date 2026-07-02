"""Run Phase 3A explicit source-block index rebuild for one snapshot."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, TextIO

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.application.app.core_sot.service import CoreSotService
from services.application.app.indexing.service import (
    DeterministicFakeEmbeddingProvider,
    InMemoryVectorIndexAdapter,
    SourceBlockIndexingService,
)

DEFAULT_MONGO_DB = "ai_writing_system"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild Phase 3A source-block index records for a Core SOT "
            "snapshot using the current deterministic fake vector adapter."
        )
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--mongo-uri", default=os.environ.get("CORE_SOT_MONGO_URI"))
    parser.add_argument(
        "--mongo-db",
        default=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_MONGO_DB),
    )
    parser.add_argument(
        "--mongo-transactions",
        default=os.environ.get("CORE_SOT_MONGO_TRANSACTIONS", "true"),
        choices=("true", "false", "1", "0", "yes", "no"),
    )
    parser.add_argument(
        "--embedding-dimensions",
        type=int,
        default=4,
    )
    return parser.parse_args(argv)


def run_rebuild(args: argparse.Namespace) -> dict[str, Any]:
    return rebuild_source_block_index(
        core_sot=_core_sot_from_mongo(args),
        project_id=args.project_id,
        snapshot_id=args.snapshot_id,
        embedding_dimensions=args.embedding_dimensions,
    )


def rebuild_source_block_index(
    *,
    core_sot: CoreSotService,
    project_id: str,
    snapshot_id: str,
    embedding_dimensions: int = 4,
) -> dict[str, Any]:
    vector_index = InMemoryVectorIndexAdapter()
    service = SourceBlockIndexingService(
        core_sot=core_sot,
        embeddings=DeterministicFakeEmbeddingProvider(
            dimensions=embedding_dimensions,
        ),
        vector_index=vector_index,
    )

    result = service.rebuild_snapshot_source_block_index(
        project_id=project_id,
        snapshot_id=snapshot_id,
    )
    all_records = vector_index.list_records(project_id=project_id, include_archived=True)
    visible_records = vector_index.list_records(project_id=project_id)
    return {
        "project_id": result.request.project_id,
        "snapshot_id": result.request.snapshot_id,
        "target": result.request.target.value,
        "records_attempted": result.records_attempted,
        "records_written": result.records_written,
        "records_indexed": len(all_records),
        "records_query_visible": len(visible_records),
        "records_archived": len(all_records) - len(visible_records),
    }


def terminal_status(summary: dict[str, Any]) -> bool:
    return summary["records_attempted"] == summary["records_written"]


def main(
    argv: list[str] | None = None,
    *,
    run_rebuild_fn=run_rebuild,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    args = parse_args(argv)
    err = stderr if stderr is not None else sys.stderr
    try:
        summary = run_rebuild_fn(args)
    except ValueError as exc:
        print(str(exc), file=err)
        return 2

    stream = stdout if stdout is not None else sys.stdout
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), file=stream)
    return 0 if terminal_status(summary) else 1


def _core_sot_from_mongo(args: argparse.Namespace) -> CoreSotService:
    if not args.mongo_uri:
        raise ValueError("CORE_SOT_MONGO_URI or --mongo-uri is required")

    from services.application.app.core_sot.mongo_repository import (
        MongoCoreSotRepository,
    )

    repository = MongoCoreSotRepository.from_uri(
        args.mongo_uri,
        db_name=args.mongo_db,
        use_transactions=args.mongo_transactions.lower() in {"true", "1", "yes"},
    )
    return CoreSotService(repository)


if __name__ == "__main__":
    raise SystemExit(main())
