"""Phase 2B.5/b-2 backfill: reindex existing needs_review candidates into
candidate_vectors + candidate_lexical.

Going forward every ``record_candidate(s)`` enqueues a CANDIDATE_UPSERTED
reindex, so the index stays current. This one-shot script covers candidates that
existed *before* that wiring (and any DLQ-dropped drain failures): it lists a
project's ``needs_review`` ``AnalysisCandidate`` records and upserts their
vectors — and lexical docs — directly (bypassing the outbox — D7). Candidates
are immutable today (a single ``needs_review`` status), so the result is
needs_review-only.

Real Chroma / Elasticsearch when CHROMA_HOST / ELASTICSEARCH_URL are set (writes
the deployed candidate_vectors / candidate_lexical), else the in-memory fakes (a
dry run — records are lost on exit, so the summary still reports what *would* be
written). Live run is sandbox-external.

    python3 scripts/phase2b5_reindex_candidate.py --project-id P --mongo-uri URI
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

from services.application.app.indexing.candidate_index import (
    CANDIDATE_VECTOR_COLLECTION,
    InMemoryCandidateVectorIndexAdapter,
    build_candidate_index_record,
    candidate_index_text,
)
from services.application.app.indexing.candidate_lexical_index import (
    CANDIDATE_LEXICAL_INDEX,
    InMemoryCandidateLexicalIndexAdapter,
    build_candidate_lexical_record,
)
from services.application.app.indexing.service import (
    CHROMA_VECTOR_BACKEND,
    ELASTICSEARCH_BACKEND,
    FAKE_VECTOR_BACKEND,
)

DEFAULT_MONGO_DB = "ai_writing_system"


def _build_embedding_provider():
    from services.application.app.indexing.embedding import (
        build_embedding_provider_from_env,
    )

    return build_embedding_provider_from_env()


def _build_candidate_vector_index() -> tuple[object, str]:
    host = os.environ.get("CHROMA_HOST")
    if not host:
        return InMemoryCandidateVectorIndexAdapter(), FAKE_VECTOR_BACKEND
    from services.application.app.indexing.chroma import (
        ChromaCandidateVectorIndexAdapter,
        connect_chroma_collection,
    )

    return (
        ChromaCandidateVectorIndexAdapter(
            connect_chroma_collection(
                host=host,
                port=int(os.environ.get("CHROMA_PORT", "8000")),
                collection_name=os.environ.get(
                    "CHROMA_CANDIDATE_COLLECTION", CANDIDATE_VECTOR_COLLECTION
                ),
            )
        ),
        CHROMA_VECTOR_BACKEND,
    )


def _build_candidate_lexical_index() -> tuple[object, str]:
    # §8 lexical leg: real Elasticsearch when ELASTICSEARCH_URL is set (writes
    # the deployed candidate_lexical index), else the in-memory fake (a dry run
    # — the summary still reports what *would* be written). Mirrors the vector
    # leg so a single needs_review sweep keeps both indexes current.
    url = os.environ.get("ELASTICSEARCH_URL")
    if not url:
        return InMemoryCandidateLexicalIndexAdapter(), FAKE_VECTOR_BACKEND
    from services.application.app.indexing.candidate_lexical_index import (
        connect_elasticsearch_candidate_index,
    )

    return (
        connect_elasticsearch_candidate_index(
            url=url,
            index_name=os.environ.get(
                "ELASTICSEARCH_CANDIDATE_INDEX", CANDIDATE_LEXICAL_INDEX
            ),
        ),
        ELASTICSEARCH_BACKEND,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reindex a project's needs_review candidates into "
        "candidate_vectors + candidate_lexical."
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

    from services.application.app.analysis.mongo_repository import (
        MongoAnalysisRepository,
    )
    from services.application.app.analysis.service import AnalysisService
    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME

    analysis = AnalysisService(
        MongoAnalysisRepository.from_uri(
            args.mongo_uri, db_name=args.mongo_db or DEFAULT_DB_NAME
        )
    )
    embeddings = _build_embedding_provider()
    vector_index, vector_backend = _build_candidate_vector_index()
    lexical_index, lexical_backend = _build_candidate_lexical_index()

    candidates = analysis.list_needs_review_candidates(project_id=args.project_id)
    vector_records = []
    lexical_records = []
    for candidate in candidates:
        text = candidate_index_text(candidate)
        vector_records.append(
            build_candidate_index_record(
                candidate, text=text, vector=embeddings.embed(text)
            )
        )
        lexical_records.append(build_candidate_lexical_record(candidate, text=text))
    vector_written = vector_index.upsert_candidate_records(tuple(vector_records))
    lexical_written = lexical_index.index_candidate_records(tuple(lexical_records))
    return {
        "project_id": args.project_id,
        "vector_backend": vector_backend,
        "lexical_backend": lexical_backend,
        "candidate_count": len(candidates),
        "vector_records_written": vector_written,
        "lexical_records_written": lexical_written,
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
