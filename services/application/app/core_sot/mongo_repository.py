"""MongoDB adapter implementing the Core SOT repository contract.

The adapter persists the load-bearing draft-save write set
(``draft_versions``, ``source_snapshots``, ``source_blocks``) plus the
idempotency record carried on the ``draft_versions`` document.

Two write paths satisfy the approved persistence contract:

- Transaction path (Docker / replica-set runtime, default): the whole save
  write set commits in one MongoDB transaction.
- Non-transaction fallback (local / test deployments without transactions):
  immutable dependents are written first, the ``draft_versions`` commit marker
  is written last under a unique idempotency index, and a prior failed
  attempt's orphans are cleaned before re-writing. A committed version short
  circuits as an idempotent replay (retry guard). Per SoT v1.4 the fallback is
  **single-writer only**: its orphan cleanup / retry guard are defined for one
  writer's sequential retries, not for concurrent saves of the same request.
  Runtimes needing concurrency safety use the transaction path.

In both paths the success is only reported after the MongoDB write completes,
and the unique index on ``(project_id, draft_id, idempotency_key)`` is the
authoritative idempotency boundary.
"""

from __future__ import annotations

from bson import ObjectId
from pymongo import ASCENDING, MongoClient
from pymongo.errors import DuplicateKeyError

from services.application.app.core_sot.models import (
    BlockKind,
    Draft,
    DraftVersion,
    Project,
    SourceBlock,
    SourceRef,
    SourceSnapshot,
)
from services.application.app.core_sot.repository import DuplicateSaveRequest

DEFAULT_DB_NAME = "ai_writing_system"


class MongoCoreSotRepository:
    """``CoreSotRepository`` backed by MongoDB collections."""

    def __init__(
        self,
        client: MongoClient,
        *,
        db_name: str = DEFAULT_DB_NAME,
        use_transactions: bool = True,
    ) -> None:
        self._client = client
        self._db = client[db_name]
        self._use_transactions = use_transactions
        self._projects = self._db["projects"]
        self._drafts = self._db["drafts"]
        self._versions = self._db["draft_versions"]
        self._snapshots = self._db["source_snapshots"]
        self._blocks = self._db["source_blocks"]
        self._source_refs = self._db["source_refs"]
        self.ensure_indexes()

    @classmethod
    def from_uri(
        cls,
        uri: str,
        *,
        db_name: str = DEFAULT_DB_NAME,
        use_transactions: bool = True,
    ) -> "MongoCoreSotRepository":
        return cls(
            MongoClient(uri),
            db_name=db_name,
            use_transactions=use_transactions,
        )

    def ensure_indexes(self) -> None:
        self._versions.create_index(
            [
                ("project_id", ASCENDING),
                ("draft_id", ASCENDING),
                ("idempotency_key", ASCENDING),
            ],
            unique=True,
            name="uniq_save_request",
        )
        self._blocks.create_index(
            [("snapshot_id", ASCENDING), ("block_index", ASCENDING)],
            name="blocks_by_snapshot",
        )
        self._source_refs.create_index(
            [("project_id", ASCENDING), ("snapshot_id", ASCENDING)],
            name="source_refs_by_snapshot",
        )

    # -- identifier generation ------------------------------------------------

    def next_project_id(self) -> str:
        return str(ObjectId())

    def next_draft_id(self) -> str:
        return str(ObjectId())

    def next_version_id(self) -> str:
        return str(ObjectId())

    def next_snapshot_id(self) -> str:
        return str(ObjectId())

    def next_source_ref_id(self) -> str:
        return str(ObjectId())

    # -- project / draft ------------------------------------------------------

    def get_project(self, project_id: str) -> Project | None:
        doc = self._projects.find_one({"_id": project_id})
        return _to_project(doc) if doc else None

    def put_project(self, project: Project) -> None:
        self._projects.replace_one(
            {"_id": project.id}, _project_doc(project), upsert=True
        )

    def get_draft(self, draft_id: str) -> Draft | None:
        doc = self._drafts.find_one({"_id": draft_id})
        return _to_draft(doc) if doc else None

    def put_draft(self, draft: Draft) -> None:
        self._drafts.replace_one({"_id": draft.id}, _draft_doc(draft), upsert=True)

    # -- save / lookups -------------------------------------------------------

    def version_count(self, draft_id: str) -> int:
        return self._versions.count_documents({"draft_id": draft_id})

    def find_save_request(
        self, project_id: str, draft_id: str, idempotency_key: str
    ) -> str | None:
        doc = self._versions.find_one(
            {
                "project_id": project_id,
                "draft_id": draft_id,
                "idempotency_key": idempotency_key,
            },
            {"_id": 1},
        )
        return doc["_id"] if doc else None

    def get_version(self, version_id: str) -> DraftVersion | None:
        doc = self._versions.find_one({"_id": version_id})
        return _to_version(doc) if doc else None

    def get_snapshot(self, snapshot_id: str) -> SourceSnapshot | None:
        doc = self._snapshots.find_one({"_id": snapshot_id})
        return _to_snapshot(doc) if doc else None

    def get_blocks(self, snapshot_id: str) -> tuple[SourceBlock, ...]:
        cursor = self._blocks.find({"snapshot_id": snapshot_id}).sort(
            "block_index", ASCENDING
        )
        return tuple(_to_block(doc) for doc in cursor)

    def record_source_ref(self, source_ref: SourceRef) -> None:
        self._source_refs.insert_one(_source_ref_doc(source_ref))

    def get_source_ref(self, source_ref_id: str) -> SourceRef | None:
        doc = self._source_refs.find_one({"_id": source_ref_id})
        return _to_source_ref(doc) if doc else None

    def record_save(
        self,
        *,
        idempotency_key: str,
        version: DraftVersion,
        snapshot: SourceSnapshot,
        blocks: tuple[SourceBlock, ...],
    ) -> None:
        if self._use_transactions:
            self._record_save_transactional(idempotency_key, version, snapshot, blocks)
        else:
            self._record_save_fallback(idempotency_key, version, snapshot, blocks)

    def _record_save_transactional(
        self,
        idempotency_key: str,
        version: DraftVersion,
        snapshot: SourceSnapshot,
        blocks: tuple[SourceBlock, ...],
    ) -> None:
        version_doc = _version_doc(version)
        snapshot_doc = _snapshot_doc(snapshot, idempotency_key)
        block_docs = [
            _block_doc(block, idempotency_key, version.draft_id) for block in blocks
        ]
        with self._client.start_session() as session:
            try:
                with session.start_transaction():
                    # Version carries the unique idempotency key, so insert it
                    # first: a duplicate aborts the whole transaction.
                    self._versions.insert_one(version_doc, session=session)
                    self._snapshots.insert_one(snapshot_doc, session=session)
                    if block_docs:
                        self._blocks.insert_many(block_docs, session=session)
            except DuplicateKeyError as exc:
                raise DuplicateSaveRequest(idempotency_key) from exc

    def _record_save_fallback(
        self,
        idempotency_key: str,
        version: DraftVersion,
        snapshot: SourceSnapshot,
        blocks: tuple[SourceBlock, ...],
    ) -> None:
        # Single-writer only (SoT v1.4): the orphan cleanup below removes every
        # dependent matching this save request's scope, which is correct for one
        # writer's sequential retries but would drop a concurrent writer's
        # committed dependents. Concurrency safety is the transaction path's job.
        scope = {
            "project_id": version.project_id,
            "draft_id": version.draft_id,
            "idempotency_key": idempotency_key,
        }
        # Retry guard: a committed version means this is an idempotent replay;
        # never touch the committed dependents.
        if self.find_save_request(*scope.values()) is not None:
            raise DuplicateSaveRequest(idempotency_key)

        # Orphan cleanup: remove dependents left by a prior failed attempt for
        # this exact save request before re-writing.
        self._snapshots.delete_many(scope)
        self._blocks.delete_many(scope)

        # Ordered writes: immutable dependents first, commit marker last.
        self._snapshots.insert_one(_snapshot_doc(snapshot, idempotency_key))
        block_docs = [
            _block_doc(block, idempotency_key, version.draft_id) for block in blocks
        ]
        if block_docs:
            self._blocks.insert_many(block_docs)
        try:
            self._versions.insert_one(_version_doc(version))
        except DuplicateKeyError as exc:
            # Lost a concurrent race after writing our own dependents: drop only
            # what this attempt wrote, then signal the replay.
            self._snapshots.delete_many({"_id": snapshot.id})
            self._blocks.delete_many({"snapshot_id": snapshot.id})
            raise DuplicateSaveRequest(idempotency_key) from exc


def _project_doc(project: Project) -> dict:
    return {"_id": project.id, "name": project.name, "archived": project.archived}


def _to_project(doc: dict) -> Project:
    return Project(id=doc["_id"], name=doc["name"], archived=doc["archived"])


def _draft_doc(draft: Draft) -> dict:
    return {
        "_id": draft.id,
        "project_id": draft.project_id,
        "title": draft.title,
        "archived": draft.archived,
    }


def _to_draft(doc: dict) -> Draft:
    return Draft(
        id=doc["_id"],
        project_id=doc["project_id"],
        title=doc["title"],
        archived=doc["archived"],
    )


def _version_doc(version: DraftVersion) -> dict:
    return {
        "_id": version.id,
        "project_id": version.project_id,
        "draft_id": version.draft_id,
        "version_number": version.version_number,
        "snapshot_id": version.snapshot_id,
        "idempotency_key": version.idempotency_key,
    }


def _to_version(doc: dict) -> DraftVersion:
    return DraftVersion(
        id=doc["_id"],
        project_id=doc["project_id"],
        draft_id=doc["draft_id"],
        version_number=doc["version_number"],
        snapshot_id=doc["snapshot_id"],
        idempotency_key=doc["idempotency_key"],
    )


def _snapshot_doc(snapshot: SourceSnapshot, idempotency_key: str) -> dict:
    return {
        "_id": snapshot.id,
        "project_id": snapshot.project_id,
        "draft_id": snapshot.draft_id,
        "version_id": snapshot.version_id,
        "raw_text": snapshot.raw_text,
        "content_hash": snapshot.content_hash,
        "idempotency_key": idempotency_key,
    }


def _to_snapshot(doc: dict) -> SourceSnapshot:
    return SourceSnapshot(
        id=doc["_id"],
        project_id=doc["project_id"],
        draft_id=doc["draft_id"],
        version_id=doc["version_id"],
        raw_text=doc["raw_text"],
        content_hash=doc["content_hash"],
    )


def _block_doc(block: SourceBlock, idempotency_key: str, draft_id: str) -> dict:
    return {
        "_id": block.id,
        "project_id": block.project_id,
        "snapshot_id": block.snapshot_id,
        "draft_id": draft_id,
        "idempotency_key": idempotency_key,
        "block_index": block.block_index,
        "kind": str(block.kind),
        "start_offset": block.start_offset,
        "end_offset": block.end_offset,
        "text": block.text,
    }


def _to_block(doc: dict) -> SourceBlock:
    return SourceBlock(
        id=doc["_id"],
        project_id=doc["project_id"],
        snapshot_id=doc["snapshot_id"],
        block_index=doc["block_index"],
        kind=BlockKind(doc["kind"]),
        start_offset=doc["start_offset"],
        end_offset=doc["end_offset"],
        text=doc["text"],
    )


def _source_ref_doc(source_ref: SourceRef) -> dict:
    return {
        "_id": source_ref.id,
        "project_id": source_ref.project_id,
        "snapshot_id": source_ref.snapshot_id,
        "block_id": source_ref.block_id,
        "start_offset": source_ref.start_offset,
        "end_offset": source_ref.end_offset,
        "quote": source_ref.quote,
        "content_hash": source_ref.content_hash,
    }


def _to_source_ref(doc: dict) -> SourceRef:
    return SourceRef(
        id=doc["_id"],
        project_id=doc["project_id"],
        snapshot_id=doc["snapshot_id"],
        block_id=doc["block_id"],
        start_offset=doc["start_offset"],
        end_offset=doc["end_offset"],
        quote=doc["quote"],
        content_hash=doc["content_hash"],
    )
