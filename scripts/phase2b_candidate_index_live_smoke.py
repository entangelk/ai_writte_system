"""Live smoke for b-2 candidate index write chain (v1.6.54, sandbox-external).

Drives the whole candidate write chain against real infra: record a needs_review
candidate through a Mongo-backed AnalysisService wired to the index-sync outbox
(enqueues a CANDIDATE_UPSERTED), then run the index-sync worker (real embedding +
real Chroma candidate_vectors + real Elasticsearch candidate_lexical) to drain
it, then read both indexes back to confirm the candidate's vector and lexical doc
landed. Prints a JSON status.

Requires a reachable Mongo (`--mongo-uri` / CORE_SOT_MONGO_URI), Chroma
(`CHROMA_HOST`), embedding service (`EMBEDDING_SERVICE_URL`), and Elasticsearch
(`ELASTICSEARCH_URL`); the internal sandbox cannot open external TCP, so run this
outside it. Writes test data under a dedicated project id and deletes the Chroma
and ES records at the end (the Mongo candidate doc, harmless, remains).
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
    AnalysisCandidateAction,
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.indexing.candidate_index import (
    CANDIDATE_VECTOR_COLLECTION,
)
from services.application.app.indexing.candidate_lexical_index import (
    CANDIDATE_LEXICAL_INDEX,
)

DEFAULT_MONGO_DB = "ai_writing_system"


def _cleanup_mongo_docs(mongo_uri: str, db_name: str, project_id: str) -> None:
    """Delete the job/task/candidate docs this smoke wrote for its project id.
    Best-effort: a cleanup failure must not mask the smoke's real result."""
    try:
        from pymongo import MongoClient

        client = MongoClient(mongo_uri)
        try:
            db = client[db_name]
            for collection in ("analysis_jobs", "analysis_tasks", "analysis_candidates"):
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
        raise ValueError("CHROMA_HOST is required for a real candidate reindex")
    if not os.environ.get("ELASTICSEARCH_URL"):
        raise ValueError("ELASTICSEARCH_URL is required for the lexical leg")

    from services.application.app.analysis.mongo_repository import (
        MongoAnalysisRepository,
    )
    from services.application.app.analysis.service import AnalysisService
    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
    from services.application.app.indexing.candidate_lexical_index import (
        connect_elasticsearch_candidate_index,
    )
    from services.application.app.indexing.chroma import (
        ChromaCandidateVectorIndexAdapter,
        connect_chroma_collection,
    )
    from services.application.app.indexing.mongo_repository import (
        MongoIndexSyncRepository,
    )
    from services.application.app.indexing.service import IndexSyncOutboxService

    db_name = args.mongo_db or DEFAULT_DB_NAME
    project_id = f"smoke-b2-{uuid.uuid4().hex[:8]}"

    outbox = IndexSyncOutboxService(
        MongoIndexSyncRepository.from_uri(args.mongo_uri, db_name=db_name)
    )
    analysis = AnalysisService(
        MongoAnalysisRepository.from_uri(args.mongo_uri, db_name=db_name),
        reindex_outbox=outbox,
    )

    job = analysis.create_job(
        project_id=project_id,
        snapshot_id="smoke-snap",
        idempotency_key=f"run-{uuid.uuid4().hex[:8]}",
    ).job
    task = analysis.create_task(
        project_id=project_id,
        job_id=job.id,
        candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
    )
    recorded = analysis.record_candidate(
        project_id=project_id,
        task_id=task.id,
        logical_key="smoke-ariel",
        candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
        action=AnalysisCandidateAction.CREATE,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.9,
        source_ref_ids=("smoke-source",),
        payload={"name": "Smoke Ariel", "observation": "brave under a live test"},
    ).candidate

    # Drain the CANDIDATE_UPSERTED entry through the real worker (embedding +
    # Chroma candidate_vectors + ES candidate_lexical composite).
    worker_summary = index_sync_worker.run_worker(
        argparse.Namespace(mongo_uri=args.mongo_uri, mongo_db=db_name, limit=10)
    )

    vector_adapter = ChromaCandidateVectorIndexAdapter(
        connect_chroma_collection(
            host=os.environ["CHROMA_HOST"],
            port=int(os.environ.get("CHROMA_PORT", "8000")),
            collection_name=os.environ.get(
                "CHROMA_CANDIDATE_COLLECTION", CANDIDATE_VECTOR_COLLECTION
            ),
        )
    )
    vector_records = vector_adapter.list_candidate_records(project_id=project_id)
    vector_ids = [r.candidate_id for r in vector_records]

    lexical_index_name = os.environ.get(
        "ELASTICSEARCH_CANDIDATE_INDEX", CANDIDATE_LEXICAL_INDEX
    )
    lexical_adapter = connect_elasticsearch_candidate_index(
        url=os.environ["ELASTICSEARCH_URL"],
        index_name=lexical_index_name,
    )
    # The worker indexes without a forced refresh (production searches at
    # generation time, not microseconds later); make the just-written doc
    # searchable before this immediate read-back.
    lexical_adapter._client.indices.refresh(index=lexical_index_name)
    lexical_hits = lexical_adapter.search(
        project_id=project_id, query="brave", limit=5
    )
    lexical_ids = [r.candidate_id for r in lexical_hits]

    # Best-effort cleanup of both index records AND the Mongo docs this smoke
    # created (job/task/candidate), so repeated live runs do not accumulate
    # smoke-* documents in the shared database.
    vector_adapter.delete_candidate_record(
        project_id=project_id, candidate_id=recorded.id
    )
    lexical_adapter.delete_candidate_record(
        project_id=project_id, candidate_id=recorded.id
    )
    _cleanup_mongo_docs(args.mongo_uri, db_name, project_id)

    ok = (
        vector_ids == [recorded.id]
        and lexical_ids == [recorded.id]
    )
    return {
        "status": "ok" if ok else "mismatch",
        "project_id": project_id,
        "candidate_id": recorded.id,
        "candidate_backend": worker_summary.get("candidate_backend"),
        "worker_succeeded": worker_summary.get("entries_succeeded"),
        "vector_candidate_ids": vector_ids,
        "lexical_candidate_ids": lexical_ids,
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
