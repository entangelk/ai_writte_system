"""Phase 2B.5: project canonical memories into the vector index.

Write path only (D6=write-only): apply enqueues a ``MEMORY_UPSERTED`` outbox
event and the index-sync worker drains it here (D3=B async). The semantic
*read* path (event/open_question resolution via vector search) is a later slice.

Canonical-only invariant under 2B.4's append-only model (D4, corrected): each
memory version is a distinct ``MemoryEntry`` id, so ``MemoryIndexSyncAdapter``
loads the memory the entry points at and:

* if it is no longer canonical (a later version superseded it before we got
  here), deletes that id's vector and stops — order-independent self-healing;
* otherwise upserts the version's vector and, when it supersedes a prior
  version, deletes the prior id's vector.

Both branches are idempotent, so replays and out-of-order drains converge on
"exactly the current canonical versions are indexed".
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from services.application.app.analysis.models import AnalysisCandidateType
from services.application.app.indexing.models import (
    IndexRecordKind,
    IndexSyncOutboxEntry,
    MemoryIndexRecord,
)
from services.application.app.indexing.service import _cosine_similarity
from services.application.app.memory.models import MemoryEntry, MemoryStatus
from services.application.app.memory.service import MemoryNotFound, MemoryService


MEMORY_VECTOR_COLLECTION = "memory_vectors"


def derive_memory_index_text(
    memory_type: AnalysisCandidateType, payload: Mapping[str, Any]
) -> str:
    """Deterministic text projection of a memory payload for embedding (D1=A).

    The payload fields are exactly the type's required fields (validated at
    extraction, ``analysis/schema.py``), so this reads only contracted keys.
    """
    if memory_type is AnalysisCandidateType.CHARACTER_OBSERVATION:
        return f"{payload['name']}\n{payload['observation']}"
    if memory_type is AnalysisCandidateType.EVENT_OBSERVATION:
        return str(payload["event"])
    if memory_type is AnalysisCandidateType.OPEN_QUESTION_OBSERVATION:
        return str(payload["question"])
    raise ValueError(f"unsupported memory_type for indexing: {memory_type}")


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> tuple[float, ...]: ...


class MemoryVectorIndexAdapter(Protocol):
    def upsert_memory_records(
        self, records: tuple[MemoryIndexRecord, ...]
    ) -> int: ...

    def delete_memory_record(self, *, project_id: str, memory_id: str) -> None: ...

    def list_memory_records(
        self, *, project_id: str
    ) -> tuple[MemoryIndexRecord, ...]: ...

    def query_similar(
        self,
        *,
        project_id: str,
        memory_type: str,
        vector: tuple[float, ...],
        limit: int,
    ) -> tuple[MemoryIndexRecord, ...]: ...


class InMemoryMemoryVectorIndexAdapter:
    """No-infra vector backend for unit tests and the deterministic fallback."""

    def __init__(self) -> None:
        self.records: dict[str, MemoryIndexRecord] = {}

    def upsert_memory_records(
        self, records: tuple[MemoryIndexRecord, ...]
    ) -> int:
        for record in records:
            self.records[record.id] = record
        return len(records)

    def delete_memory_record(self, *, project_id: str, memory_id: str) -> None:
        existing = self.records.get(memory_id)
        if existing is not None and existing.project_id == project_id:
            del self.records[memory_id]

    def query_similar(
        self,
        *,
        project_id: str,
        memory_type: str,
        vector: tuple[float, ...],
        limit: int,
    ) -> tuple[MemoryIndexRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        candidates = [
            record
            for record in self.records.values()
            if record.project_id == project_id
            and record.memory_type == memory_type
        ]
        ranked = sorted(
            candidates,
            key=lambda record: (
                -_cosine_similarity(vector, record.vector),
                record.id,
            ),
        )
        return tuple(ranked[:limit])

    def list_memory_records(
        self, *, project_id: str
    ) -> tuple[MemoryIndexRecord, ...]:
        return tuple(
            sorted(
                (
                    record
                    for record in self.records.values()
                    if record.project_id == project_id
                ),
                key=lambda record: record.id,
            )
        )


def build_memory_index_record(
    memory: MemoryEntry, *, text: str, vector: tuple[float, ...]
) -> MemoryIndexRecord:
    return MemoryIndexRecord(
        id=memory.id,
        kind=IndexRecordKind.MEMORY,
        project_id=memory.project_id,
        memory_id=memory.id,
        memory_type=memory.memory_type.value,
        version=memory.version,
        status=memory.status.value,
        text=text,
        vector=vector,
    )


class MemoryIndexSyncAdapter:
    """Worker-side adapter: load the memory an entry points at and reindex it."""

    def __init__(
        self,
        *,
        memory_service: MemoryService,
        embeddings: EmbeddingProvider,
        vector_index: MemoryVectorIndexAdapter,
    ) -> None:
        self._memory = memory_service
        self._embeddings = embeddings
        self._vector_index = vector_index

    def index_memory(self, entry: IndexSyncOutboxEntry) -> None:
        project_id = entry.project_id
        memory_id = entry.source.mongo_id
        try:
            memory = self._memory.get_memory(
                project_id=project_id, memory_id=memory_id
            )
        except MemoryNotFound:
            # The memory was removed before we indexed it; ensure no stale vector.
            self._vector_index.delete_memory_record(
                project_id=project_id, memory_id=memory_id
            )
            return

        if memory.status is not MemoryStatus.CANONICAL:
            # A later version superseded this one before the drain reached it.
            # Drop its vector (order-independent) and stop — the successor's own
            # entry carries the canonical upsert.
            self._vector_index.delete_memory_record(
                project_id=project_id, memory_id=memory.id
            )
            return

        text = derive_memory_index_text(memory.memory_type, memory.payload)
        vector = self._embeddings.embed(text)
        record = build_memory_index_record(memory, text=text, vector=vector)
        self._vector_index.upsert_memory_records((record,))
        if memory.supersedes is not None:
            self._vector_index.delete_memory_record(
                project_id=project_id, memory_id=memory.supersedes
            )


class CompositeMemoryIndexSyncAdapter:
    """Fan a MEMORY_UPSERTED drain out to every configured memory sink (vector +
    lexical), so one outbox entry keeps both indexes current. Each sink's
    ``index_memory`` is idempotent, so a replay after a partial failure re-drains
    both; if any sink raises, the entry fails and requeues (worker contract)."""

    def __init__(self, adapters: tuple[object, ...]) -> None:
        self._adapters = tuple(adapters)

    def index_memory(self, entry: IndexSyncOutboxEntry) -> None:
        for adapter in self._adapters:
            adapter.index_memory(entry)
