"""Real persistent Chroma vector adapter (Phase 4 real vector backend, B.3).

`ChromaVectorIndexAdapter` implements the same `VectorIndexAdapter` (write) and
`VectorSearchAdapter` (query) seams as the in-memory fake, plus `list_records`
used by the rebuild summary, but stores records in a Chroma collection so the
index survives a process restart. The adapter takes an injected collection
(duck-typed: upsert/query/get), so its logic — project scoping, archived
exclusion, ordering, record reconstruction — is unit-tested with an in-memory
fake collection and needs no `chromadb`. `connect_chroma_collection` lazily
imports `chromadb` to build a real HttpClient collection for the container /
skip-aware live tests. See docs/plans/04-real-vector-backend-decisions.md (B.3).
"""

from __future__ import annotations

from typing import Any, Protocol

from services.application.app.indexing.models import (
    IndexPointer,
    IndexRecordKind,
    IndexSyncEvent,
    IndexSyncOutboxEntry,
    SourceBlockIndexRecord,
)
from services.application.app.indexing.service import DerivedIndexRecordNotFound


DEFAULT_COLLECTION_NAME = "project_memory_vectors"


class ChromaCollection(Protocol):
    def upsert(
        self,
        *,
        ids: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None: ...

    def query(
        self,
        *,
        query_embeddings: list[list[float]],
        n_results: int,
        where: dict[str, Any] | None,
        include: list[str],
    ) -> dict[str, Any]: ...

    def get(
        self, *, where: dict[str, Any] | None, include: list[str]
    ) -> dict[str, Any]: ...

    def delete(self, *, where: dict[str, Any] | None) -> None: ...


def record_to_chroma(
    record: SourceBlockIndexRecord,
) -> tuple[str, list[float], dict[str, Any]]:
    """Flatten a record into (id, embedding, metadata). Every field needed to
    reconstruct the record is kept in metadata (Chroma metadata values are
    str/int/float/bool), so a query can rebuild the record without the SOT."""
    metadata = {
        "kind": record.kind.value,
        "project_id": record.pointer.project_id,
        "collection": record.pointer.collection,
        "document_id": record.pointer.document_id,
        "version_id": record.pointer.version_id,
        "content_hash": record.pointer.content_hash,
        "snapshot_id": record.snapshot_id,
        "draft_id": record.draft_id,
        "block_id": record.block_id,
        "block_index": record.block_index,
        "text": record.text,
        "project_archived": record.project_archived,
        "draft_archived": record.draft_archived,
    }
    return record.id, list(record.vector), metadata


def record_from_chroma(
    record_id: str, embedding: Any, metadata: dict[str, Any]
) -> SourceBlockIndexRecord:
    return SourceBlockIndexRecord(
        id=record_id,
        kind=IndexRecordKind(metadata["kind"]),
        pointer=IndexPointer(
            project_id=metadata["project_id"],
            collection=metadata["collection"],
            document_id=metadata["document_id"],
            version_id=metadata["version_id"],
            content_hash=metadata["content_hash"],
        ),
        snapshot_id=metadata["snapshot_id"],
        draft_id=metadata["draft_id"],
        block_id=metadata["block_id"],
        block_index=int(metadata["block_index"]),
        text=metadata["text"],
        vector=tuple(float(value) for value in embedding),
        project_archived=bool(metadata["project_archived"]),
        draft_archived=bool(metadata["draft_archived"]),
    )


def _active_where(project_id: str) -> dict[str, Any]:
    # Only a project's non-archived records are ranking candidates, matching the
    # in-memory fake's query_similar (which lists non-archived, then ranks).
    return {
        "$and": [
            {"project_id": project_id},
            {"project_archived": False},
            {"draft_archived": False},
        ]
    }


class ChromaVectorIndexAdapter:
    # Chroma get/query omit embeddings unless requested; the adapter always
    # needs them to reconstruct record.vector, so this is fixed.
    _INCLUDE = ["embeddings", "metadatas"]

    def __init__(self, collection: ChromaCollection) -> None:
        self._collection = collection

    def upsert_records(self, records: tuple[SourceBlockIndexRecord, ...]) -> int:
        if not records:
            return 0
        ids: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict[str, Any]] = []
        for record in records:
            record_id, embedding, metadata = record_to_chroma(record)
            ids.append(record_id)
            embeddings.append(embedding)
            metadatas.append(metadata)
        self._collection.upsert(
            ids=ids, embeddings=embeddings, metadatas=metadatas
        )
        return len(records)

    def list_records(
        self, *, project_id: str, include_archived: bool = False
    ) -> tuple[SourceBlockIndexRecord, ...]:
        result = self._collection.get(
            where={"project_id": project_id}, include=self._INCLUDE
        )
        records = _records_from_get(result)
        if not include_archived:
            records = [
                record
                for record in records
                if not record.project_archived and not record.draft_archived
            ]
        return tuple(sorted(records, key=lambda record: record.id))

    def query_similar(
        self, *, project_id: str, vector: tuple[float, ...], limit: int
    ) -> tuple[SourceBlockIndexRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        result = self._collection.query(
            query_embeddings=[list(vector)],
            n_results=limit,
            where=_active_where(project_id),
            include=self._INCLUDE,
        )
        return _records_from_query(result)


def _records_from_get(result: dict[str, Any]) -> list[SourceBlockIndexRecord]:
    ids = result.get("ids")
    if ids is None:
        ids = []
    embeddings = result.get("embeddings")
    if embeddings is None:
        embeddings = [None] * len(ids)
    metadatas = result.get("metadatas")
    if metadatas is None:
        metadatas = []
    return [
        record_from_chroma(record_id, embedding, metadata)
        for record_id, embedding, metadata in zip(ids, embeddings, metadatas)
    ]


def _records_from_query(
    result: dict[str, Any],
) -> tuple[SourceBlockIndexRecord, ...]:
    # query nests one list per query embedding; we send exactly one.
    ids_by_query = result.get("ids")
    if ids_by_query is None:
        ids_by_query = [[]]
    ids = ids_by_query[0]
    embeddings_by_query = result.get("embeddings")
    if embeddings_by_query is None:
        embeddings_by_query = [[None] * len(ids)]
    metadatas_by_query = result.get("metadatas")
    if metadatas_by_query is None:
        metadatas_by_query = [[]]
    embeddings = embeddings_by_query[0]
    metadatas = metadatas_by_query[0]
    return tuple(
        record_from_chroma(record_id, embedding, metadata)
        for record_id, embedding, metadata in zip(ids, embeddings, metadatas)
    )


def _archive_where(entry: IndexSyncOutboxEntry) -> dict[str, Any]:
    # project_archived deletes every derived record of the project; draft_archived
    # narrows to that draft (still project-scoped so a cross-project draft id can
    # never collide). entry.source.mongo_id is the draft id for draft_archived.
    if entry.event is IndexSyncEvent.PROJECT_ARCHIVED:
        return {"project_id": entry.project_id}
    if entry.event is IndexSyncEvent.DRAFT_ARCHIVED:
        return {
            "$and": [
                {"project_id": entry.project_id},
                {"draft_id": entry.source.mongo_id},
            ]
        }
    raise ValueError(f"unsupported archive event: {entry.event.value}")


class ChromaArchiveIndexMutationAdapter:
    """Archive-time mutation against real Chroma (worker->real Chroma wiring).

    When a project/draft is archived the derived source-block records for it must
    stop being retrieval candidates. Records are fully rebuildable from the SOT,
    so the cleanup is a delete, not a tombstone. If no matching record exists the
    target state (archived content absent from the derived index) is already met,
    so `mark_archived` raises `DerivedIndexRecordNotFound` and the worker treats
    it as idempotent success (docs/plans/03-index-worker-retry-decisions.md §8.2).
    """

    def __init__(self, collection: ChromaCollection) -> None:
        self._collection = collection

    def mark_archived(self, entry: IndexSyncOutboxEntry) -> None:
        where = _archive_where(entry)
        existing = self._collection.get(where=where, include=[])
        ids = existing.get("ids")
        if ids is None:
            ids = []
        # len() rather than truthiness: real Chroma may hand back numpy-like
        # containers whose __bool__ is ambiguous (B.5 live fix).
        if len(ids) == 0:
            raise DerivedIndexRecordNotFound(
                f"no derived index records for {entry.event.value} "
                f"{entry.source.mongo_id}"
            )
        self._collection.delete(where=where)


def connect_chroma_collection(
    *, host: str, port: int, collection_name: str = DEFAULT_COLLECTION_NAME
) -> ChromaCollection:
    """Build a real Chroma HttpClient collection. `chromadb` is imported lazily
    so unit tests (fake collection) and environments without Chroma do not need
    the dependency. The collection uses cosine space to match the fake's cosine
    ranking."""
    import chromadb

    client = chromadb.HttpClient(host=host, port=port)
    return client.get_or_create_collection(
        name=collection_name, metadata={"hnsw:space": "cosine"}
    )
