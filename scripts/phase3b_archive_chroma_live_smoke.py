"""Live smoke for Phase 3B archive->worker->real Chroma delete (sandbox-external).

Drives the archive drain against real infra in two phases, seeding two
source-block records (an "archived" draft and a "control" draft) in the SAME
project into the real Chroma project_memory_vectors collection:

  Phase 1 (DRAFT_ARCHIVED): enqueue + worker drain deletes only the archived
  draft's record; the control draft survives (draft_archived narrows to
  {project_id AND draft_id}, it does not wipe the project).

  Phase 2 (PROJECT_ARCHIVED): enqueue + worker drain deletes every remaining
  record of the project (whole-project wipe), including the control draft.

Both phases go through the real ChromaArchiveIndexMutationAdapter. Prints a JSON
status.

Requires a reachable Mongo (`--mongo-uri` / CORE_SOT_MONGO_URI) and Chroma
(`CHROMA_HOST`); the internal sandbox cannot open external TCP, so run this
outside it. Writes test data under a dedicated project id; the archived record is
deleted by the drain and the control record is removed at the end.
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
from services.application.app.indexing.models import (
    IndexPointer,
    IndexRecordKind,
    SourceBlockIndexRecord,
)

DEFAULT_MONGO_DB = "ai_writing_system"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mongo-uri", default=os.environ.get("CORE_SOT_MONGO_URI"))
    parser.add_argument(
        "--mongo-db", default=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_MONGO_DB)
    )
    return parser.parse_args(argv)


def _source_block_record(
    *, project_id: str, draft_id: str, block_id: str
) -> SourceBlockIndexRecord:
    return SourceBlockIndexRecord(
        id=f"{draft_id}:{block_id}",
        kind=IndexRecordKind.SOURCE_BLOCK,
        pointer=IndexPointer(
            project_id=project_id,
            collection="draft_versions",
            document_id=draft_id,
            version_id="v1",
            content_hash="deadbeef",
        ),
        snapshot_id="smoke-snap",
        draft_id=draft_id,
        block_id=block_id,
        block_index=0,
        text="smoke archive block",
        # The deployed project_memory_vectors collection is 1024-dim (BGE-m3-ko);
        # archive deletes by metadata where-clause, so the values are irrelevant,
        # but the dimension must match the collection.
        vector=(0.1,) + (0.0,) * 1023,
        project_archived=False,
        draft_archived=False,
    )


def run_smoke(args: argparse.Namespace) -> dict:
    if not args.mongo_uri:
        raise ValueError("CORE_SOT_MONGO_URI or --mongo-uri is required")
    if not os.environ.get("CHROMA_HOST"):
        raise ValueError("CHROMA_HOST is required for a real archive delete")

    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
    from services.application.app.indexing.chroma import (
        DEFAULT_COLLECTION_NAME,
        ChromaVectorIndexAdapter,
        connect_chroma_collection,
    )
    from services.application.app.indexing.mongo_repository import (
        MongoIndexSyncRepository,
    )
    from services.application.app.indexing.service import IndexSyncOutboxService

    db_name = args.mongo_db or DEFAULT_DB_NAME
    project_id = f"smoke-3b-{uuid.uuid4().hex[:8]}"
    archived_draft = "draft-archived"
    control_draft = "draft-control"

    collection = connect_chroma_collection(
        host=os.environ["CHROMA_HOST"],
        port=int(os.environ.get("CHROMA_PORT", "8000")),
        collection_name=os.environ.get("CHROMA_COLLECTION", DEFAULT_COLLECTION_NAME),
    )
    adapter = ChromaVectorIndexAdapter(collection)
    adapter.upsert_records(
        (
            _source_block_record(
                project_id=project_id, draft_id=archived_draft, block_id="b1"
            ),
            _source_block_record(
                project_id=project_id, draft_id=control_draft, block_id="b1"
            ),
        )
    )

    outbox = IndexSyncOutboxService(
        MongoIndexSyncRepository.from_uri(args.mongo_uri, db_name=db_name)
    )

    def drain() -> dict:
        return index_sync_worker.run_worker(
            argparse.Namespace(mongo_uri=args.mongo_uri, mongo_db=db_name, limit=10)
        )

    # Phase 1 — DRAFT_ARCHIVED: project-scoped draft narrowing. Only the archived
    # draft's record is deleted; the control draft in the SAME project survives
    # (a project_id-only delete would wipe the control too — see _archive_where).
    outbox.enqueue_draft_archived(project_id=project_id, draft_id=archived_draft)
    draft_summary = drain()
    after_draft = sorted(
        r.draft_id
        for r in adapter.list_records(project_id=project_id, include_archived=True)
    )

    # Phase 2 — PROJECT_ARCHIVED: whole-project wipe. Every remaining derived
    # record of the project is deleted (closes the PROJECT_ARCHIVED branch of
    # _archive_where that DRAFT_ARCHIVED alone does not exercise live).
    outbox.enqueue_project_archived(project_id=project_id)
    project_summary = drain()
    after_project = sorted(
        r.draft_id
        for r in adapter.list_records(project_id=project_id, include_archived=True)
    )

    # Cleanup (best-effort; phase 2 already deleted everything for this project).
    collection.delete(where={"project_id": project_id})

    ok = after_draft == [control_draft] and after_project == []
    return {
        "status": "ok" if ok else "mismatch",
        "project_id": project_id,
        "archive_backend": draft_summary.get("archive_backend"),
        "draft_archived_worker_succeeded": draft_summary.get("entries_succeeded"),
        "project_archived_worker_succeeded": project_summary.get("entries_succeeded"),
        "remaining_after_draft_archived": after_draft,
        "remaining_after_project_archived": after_project,
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
