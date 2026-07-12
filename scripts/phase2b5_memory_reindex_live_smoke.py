"""Live smoke for Phase 2B.5 memory->vector reindex (D3=B, sandbox-external).

Drives the whole write chain against real infra: promote a synthetic candidate
through a Mongo-backed MemoryService wired to the index-sync outbox (enqueues a
MEMORY_UPSERTED), then run the index-sync worker (real embedding + real Chroma
memory_vectors collection) to drain it, then read the collection back to confirm
the memory's vector landed. Prints a JSON status.

Requires a reachable Mongo (`--mongo-uri` / CORE_SOT_MONGO_URI), Chroma
(`CHROMA_HOST`), and embedding service (`EMBEDDING_SERVICE_URL`); the internal
sandbox cannot open external TCP, so run this outside it. Writes test data under
a dedicated project id and deletes the Chroma record at the end (the Mongo memory
doc, harmless, remains).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import index_sync_worker
from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.indexing.memory_index import MEMORY_VECTOR_COLLECTION
from services.application.app.memory.models import PromotionMode

DEFAULT_MONGO_DB = "ai_writing_system"


def _cleanup_mongo_docs(mongo_uri: str, db_name: str, project_id: str) -> None:
    """Delete the memory + index-sync-log docs this smoke wrote for its project
    id. Best-effort: a cleanup failure must not mask the smoke's real result."""
    try:
        from pymongo import MongoClient

        client = MongoClient(mongo_uri)
        try:
            db = client[db_name]
            for collection in ("memory_entries", "index_sync_logs"):
                db[collection].delete_many({"project_id": project_id})
        finally:
            client.close()
    except Exception as exc:  # transient/driver — warn, don't mask the result
        print(f"WARNING: Mongo cleanup failed for {project_id}: {exc!r}", file=sys.stderr)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mongo-uri", default=os.environ.get("CORE_SOT_MONGO_URI"))
    parser.add_argument(
        "--mongo-db", default=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_MONGO_DB)
    )
    return parser.parse_args(argv)


def run_smoke(args: argparse.Namespace) -> dict:
    if not args.mongo_uri:
        raise ValueError("CORE_SOT_MONGO_URI or --mongo-uri is required")
    if not os.environ.get("CHROMA_HOST"):
        raise ValueError("CHROMA_HOST is required for a real reindex")

    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
    from services.application.app.indexing.chroma import (
        ChromaMemoryVectorIndexAdapter,
        connect_chroma_collection,
    )
    from services.application.app.indexing.mongo_repository import (
        MongoIndexSyncRepository,
    )
    from services.application.app.indexing.service import IndexSyncOutboxService
    from services.application.app.memory.mongo_repository import MongoMemoryRepository
    from services.application.app.memory.service import MemoryService

    db_name = args.mongo_db or DEFAULT_DB_NAME
    project_id = f"smoke-2b5-{uuid.uuid4().hex[:8]}"

    outbox = IndexSyncOutboxService(
        MongoIndexSyncRepository.from_uri(args.mongo_uri, db_name=db_name)
    )
    memory = MemoryService(
        MongoMemoryRepository.from_uri(args.mongo_uri, db_name=db_name),
        reindex_outbox=outbox,
    )

    candidate = AnalysisCandidate(
        id=f"cand-{uuid.uuid4().hex[:8]}",
        project_id=project_id,
        job_id="smoke-job",
        task_id="smoke-task",
        candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
        action=AnalysisCandidateAction.CREATE,
        status=AnalysisCandidateStatus.NEEDS_REVIEW,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.9,
        source_ref_ids=("smoke-source",),
        payload={"name": "Smoke Ariel", "observation": "brave under a live test"},
    )
    promoted = memory.promote_candidate(
        project_id=project_id, candidate=candidate, mode=PromotionMode.MANUAL
    ).memory

    # Drain the MEMORY_UPSERTED entry through the real worker (embedding + Chroma).
    worker_summary = index_sync_worker.run_worker(
        argparse.Namespace(
            mongo_uri=args.mongo_uri, mongo_db=db_name, limit=10
        )
    )

    collection = connect_chroma_collection(
        host=os.environ["CHROMA_HOST"],
        port=int(os.environ.get("CHROMA_PORT", "8000")),
        collection_name=os.environ.get(
            "CHROMA_MEMORY_COLLECTION", MEMORY_VECTOR_COLLECTION
        ),
    )
    adapter = ChromaMemoryVectorIndexAdapter(collection)
    records = adapter.list_memory_records(project_id=project_id)
    indexed_ids = [r.memory_id for r in records]

    # Best-effort cleanup of the Chroma record AND the Mongo docs this smoke
    # wrote (memory entry + index-sync log), so repeated live runs do not
    # accumulate smoke-* documents in the shared database.
    adapter.delete_memory_record(project_id=project_id, memory_id=promoted.id)
    _cleanup_mongo_docs(args.mongo_uri, db_name, project_id)

    ok = promoted.id in indexed_ids and len(records) == 1
    return {
        "status": "ok" if ok else "mismatch",
        "project_id": project_id,
        "promoted_memory_id": promoted.id,
        "memory_backend": worker_summary.get("memory_backend"),
        "worker_succeeded": worker_summary.get("entries_succeeded"),
        "indexed_memory_ids": indexed_ids,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = run_smoke(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
