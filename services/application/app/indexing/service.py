"""Phase 3 source-block indexing service with fake vector infrastructure."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Protocol

from services.application.app.core_sot.service import CoreSotService
from services.application.app.indexing.models import (
    IndexPointer,
    IndexRecordKind,
    IndexSyncRequest,
    IndexSyncResult,
    IndexSyncTarget,
    SourceBlockIndexRecord,
)


SOURCE_BLOCK_COLLECTION = "source_blocks"
FAKE_VECTOR_BACKEND = "in_memory_fake"


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> tuple[float, ...]: ...


class VectorIndexAdapter(Protocol):
    def upsert_records(self, records: tuple[SourceBlockIndexRecord, ...]) -> int: ...


class DeterministicFakeEmbeddingProvider:
    def __init__(self, *, dimensions: int = 4) -> None:
        if dimensions < 1:
            raise ValueError("dimensions must be positive")
        self._dimensions = dimensions

    def embed(self, text: str) -> tuple[float, ...]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = []
        for index in range(self._dimensions):
            raw = digest[index * 2 : index * 2 + 2]
            values.append(int.from_bytes(raw, "big") / 65535.0)
        return tuple(values)


class InMemoryVectorIndexAdapter:
    def __init__(self) -> None:
        self.records: dict[str, SourceBlockIndexRecord] = {}

    def upsert_records(self, records: tuple[SourceBlockIndexRecord, ...]) -> int:
        for record in records:
            self.records[record.id] = record
        return len(records)

    def list_records(
        self, *, project_id: str, include_archived: bool = False
    ) -> tuple[SourceBlockIndexRecord, ...]:
        records = (
            record
            for record in self.records.values()
            if record.pointer.project_id == project_id
        )
        if not include_archived:
            records = (
                record
                for record in records
                if not record.project_archived and not record.draft_archived
            )
        return tuple(sorted(records, key=lambda record: record.id))


@dataclass(frozen=True, slots=True)
class SourceBlockIndexRebuildSummary:
    project_id: str
    snapshot_id: str
    target: str
    records_attempted: int
    records_written: int
    records_indexed: int
    records_query_visible: int
    records_archived: int

    def to_dict(self, *, backend: str | None = None) -> dict[str, object]:
        payload: dict[str, object] = {
            "project_id": self.project_id,
            "snapshot_id": self.snapshot_id,
            "target": self.target,
            "records_attempted": self.records_attempted,
            "records_written": self.records_written,
            "records_indexed": self.records_indexed,
            "records_query_visible": self.records_query_visible,
            "records_archived": self.records_archived,
        }
        if backend is not None:
            payload["backend"] = backend
        return payload


def rebuild_source_block_index_summary(
    *,
    core_sot: CoreSotService,
    project_id: str,
    snapshot_id: str,
    embedding_dimensions: int = 4,
) -> SourceBlockIndexRebuildSummary:
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
    return SourceBlockIndexRebuildSummary(
        project_id=result.request.project_id,
        snapshot_id=result.request.snapshot_id,
        target=result.request.target.value,
        records_attempted=result.records_attempted,
        records_written=result.records_written,
        records_indexed=len(all_records),
        records_query_visible=len(visible_records),
        records_archived=len(all_records) - len(visible_records),
    )


class SourceBlockIndexingService:
    def __init__(
        self,
        *,
        core_sot: CoreSotService,
        embeddings: EmbeddingProvider,
        vector_index: VectorIndexAdapter,
    ) -> None:
        self._core_sot = core_sot
        self._embeddings = embeddings
        self._vector_index = vector_index

    def rebuild_snapshot_source_block_index(
        self, *, project_id: str, snapshot_id: str
    ) -> IndexSyncResult:
        request = IndexSyncRequest(
            project_id=project_id,
            snapshot_id=snapshot_id,
            target=IndexSyncTarget.VECTOR,
        )
        detail = self._core_sot.get_snapshot(
            project_id=project_id, snapshot_id=snapshot_id
        )
        project = self._core_sot.get_project(project_id=project_id)
        draft = self._core_sot.get_draft(
            project_id=project_id, draft_id=detail.snapshot.draft_id
        )
        records = tuple(
            self._record_for_block(
                project_archived=project.archived,
                draft_archived=draft.archived,
                version_id=detail.snapshot.version_id,
                content_hash=detail.snapshot.content_hash,
                draft_id=detail.snapshot.draft_id,
                block_id=block.id,
                project_id=project_id,
                snapshot_id=snapshot_id,
                block_index=block.block_index,
                text=block.text,
            )
            for block in detail.blocks
        )
        written = self._vector_index.upsert_records(records)
        return IndexSyncResult(
            request=request,
            records_attempted=len(records),
            records_written=written,
        )

    def _record_for_block(
        self,
        *,
        project_archived: bool,
        draft_archived: bool,
        version_id: str,
        content_hash: str,
        draft_id: str,
        block_id: str,
        project_id: str,
        snapshot_id: str,
        block_index: int,
        text: str,
    ) -> SourceBlockIndexRecord:
        return SourceBlockIndexRecord(
            id=f"source-block:{project_id}:{snapshot_id}:{block_id}",
            kind=IndexRecordKind.SOURCE_BLOCK,
            pointer=IndexPointer(
                project_id=project_id,
                collection=SOURCE_BLOCK_COLLECTION,
                document_id=block_id,
                version_id=version_id,
                content_hash=content_hash,
            ),
            snapshot_id=snapshot_id,
            draft_id=draft_id,
            block_id=block_id,
            block_index=block_index,
            text=text,
            vector=self._embeddings.embed(text),
            project_archived=project_archived,
            draft_archived=draft_archived,
        )
