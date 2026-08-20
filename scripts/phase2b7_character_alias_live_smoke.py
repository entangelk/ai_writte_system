"""Live smoke for Phase 2B.7 (c) character alias detection (sandbox-external).

Drives the whole path against real infra: promote a canonical character memory
(``김철수``) through a Mongo-backed MemoryService wired to the index-sync outbox,
drain it through the real index-sync worker (real embedding + real Chroma
``memory_vectors``), then run ``AnalysisCompareService`` with the character alias
matcher (real embedding + real Chroma ``query_similar``) over two candidates:

* a differently-named but same-subject candidate (``철수``, same observation) —
  expected ``conflict`` carrying the canonical id (alias detected, no auto-merge);
* a far, different character (``영희``) — expected ``create`` (over-strict live
  check that the threshold does not over-flag).

This exercises the real BGE-m3-ko embedding + Chroma vector query, which is what
the sandbox cannot do. It does NOT assert semantic label *quality* beyond the two
coarse boundaries — threshold calibration (the real cosine value) is a follow-up
(2B.7 D5/D7). Prints a JSON status and cleans up the Chroma record + Mongo docs.

Requires a reachable Mongo (``--mongo-uri`` / CORE_SOT_MONGO_URI), Chroma
(``CHROMA_HOST``), and embedding service (``EMBEDDING_SERVICE_URL``). The alias
threshold is ``--threshold`` / ANALYSIS_CHARACTER_ALIAS_MATCH_THRESHOLD.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import index_sync_worker
from services.application.app.analysis.compare import (
    AnalysisCompareService,
    CompareAction,
)
from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.analysis.semantic_matcher import (
    EmbeddingSemanticMatcher,
)
from services.application.app.indexing.memory_index import MEMORY_VECTOR_COLLECTION
from services.application.app.memory.models import PromotionMode

DEFAULT_MONGO_DB = "ai_writing_system"
CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION

CANONICAL_PAYLOAD = {"name": "김철수", "observation": "검을 든 방랑 기사"}
ALIAS_PAYLOAD = {"name": "철수", "observation": "검을 든 방랑 기사"}
FAR_PAYLOAD = {"name": "영희", "observation": "도서관을 지키는 조용한 사서"}


def _cleanup_mongo_docs(mongo_uri: str, db_name: str, project_id: str) -> None:
    """Delete the memory + index-sync-log docs this smoke wrote. Best-effort: a
    cleanup failure must not mask the smoke's real result."""
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
    parser.add_argument(
        "--threshold",
        type=float,
        default=float(
            os.environ.get("ANALYSIS_CHARACTER_ALIAS_MATCH_THRESHOLD", "0.7")
        ),
    )
    return parser.parse_args(argv)


def _candidate(project_id: str, candidate_id: str, payload: dict[str, str], *, job_id="smoke-job-current"):
    return AnalysisCandidate(
        id=candidate_id,
        project_id=project_id,
        job_id=job_id,
        task_id="smoke-task",
        candidate_type=CHARACTER,
        action=AnalysisCandidateAction.CREATE,
        status=AnalysisCandidateStatus.NEEDS_REVIEW,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.9,
        source_ref_ids=("smoke-source",),
        payload=payload,
    )


def run_smoke(args: argparse.Namespace) -> dict:
    if not args.mongo_uri:
        raise ValueError("CORE_SOT_MONGO_URI or --mongo-uri is required")
    if not os.environ.get("CHROMA_HOST"):
        raise ValueError("CHROMA_HOST is required")
    if not os.environ.get("EMBEDDING_SERVICE_URL"):
        raise ValueError("EMBEDDING_SERVICE_URL is required for real embedding")

    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
    from services.application.app.indexing.chroma import (
        ChromaMemoryVectorIndexAdapter,
        connect_chroma_collection,
    )
    from services.application.app.indexing.embedding import (
        build_embedding_provider_from_env,
    )
    from services.application.app.indexing.mongo_repository import (
        MongoIndexSyncRepository,
    )
    from services.application.app.indexing.service import IndexSyncOutboxService
    from services.application.app.memory.mongo_repository import MongoMemoryRepository
    from services.application.app.memory.service import MemoryService

    db_name = args.mongo_db or DEFAULT_DB_NAME
    project_id = f"smoke-2b7-{uuid.uuid4().hex[:8]}"

    outbox = IndexSyncOutboxService(
        MongoIndexSyncRepository.from_uri(args.mongo_uri, db_name=db_name)
    )
    memory = MemoryService(
        MongoMemoryRepository.from_uri(args.mongo_uri, db_name=db_name),
        reindex_outbox=outbox,
    )

    # 1. Promote the canonical character "김철수" and index its vector for real.
    #    A distinct prior job so self-exclusion (D6) does not drop it from the
    #    compare candidates' matches (they run under smoke-job-current).
    canonical = memory.promote_candidate(
        project_id=project_id,
        candidate=_candidate(
            project_id, f"cand-{uuid.uuid4().hex[:8]}", CANONICAL_PAYLOAD,
            job_id="smoke-job-prior",
        ),
        mode=PromotionMode.MANUAL,
    ).memory
    worker_summary = index_sync_worker.run_worker(
        argparse.Namespace(mongo_uri=args.mongo_uri, mongo_db=db_name, limit=10)
    )

    # 2. Build the compare service with the character alias matcher over the real
    #    embedding + Chroma memory_vectors (same projection the write path used).
    collection = connect_chroma_collection(
        host=os.environ["CHROMA_HOST"],
        port=int(os.environ.get("CHROMA_PORT", "8000")),
        collection_name=os.environ.get(
            "CHROMA_MEMORY_COLLECTION", MEMORY_VECTOR_COLLECTION
        ),
    )
    adapter = ChromaMemoryVectorIndexAdapter(collection)
    embeddings = build_embedding_provider_from_env(required=True)
    alias_matcher = EmbeddingSemanticMatcher(
        embeddings=embeddings,
        vector_search=adapter,
        memory_service=memory,
        similarity_threshold=args.threshold,
    )
    compare = AnalysisCompareService(memory_service=memory, alias_matcher=alias_matcher)

    # 3. Run compare over the alias candidate (different name, same subject) and a
    #    far candidate (different subject). Distinct candidate ids per compare so
    #    the deterministic name key finds no same-name canonical → alias path.
    async def _compare_one(payload):
        [proposal] = await compare.compare_job(
            project_id=project_id,
            job_id="smoke-job-current",
            candidates=(_candidate(project_id, f"cur-{uuid.uuid4().hex[:8]}", payload),),
        )
        return proposal

    alias_proposal = asyncio.run(_compare_one(ALIAS_PAYLOAD))
    far_proposal = asyncio.run(_compare_one(FAR_PAYLOAD))

    # 4. Best-effort cleanup (Chroma record + Mongo docs) so repeated live runs
    #    do not accumulate smoke-* documents.
    adapter.delete_memory_record(project_id=project_id, memory_id=canonical.id)
    _cleanup_mongo_docs(args.mongo_uri, db_name, project_id)

    alias_ok = (
        alias_proposal.action is CompareAction.CONFLICT
        and alias_proposal.matched_memory_id == canonical.id
    )
    far_ok = far_proposal.action is CompareAction.CREATE
    return {
        "status": "ok" if (alias_ok and far_ok) else "mismatch",
        "project_id": project_id,
        "threshold": args.threshold,
        "canonical_memory_id": canonical.id,
        "worker_succeeded": worker_summary.get("entries_succeeded"),
        "memory_backend": worker_summary.get("memory_backend"),
        "alias": {
            "action": alias_proposal.action.value,
            "matched_memory_id": alias_proposal.matched_memory_id,
            "rationale": alias_proposal.rationale,
            "ok": alias_ok,
        },
        "far": {"action": far_proposal.action.value, "ok": far_ok},
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
