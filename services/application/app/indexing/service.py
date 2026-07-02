"""Phase 3 source-block indexing service with fake vector infrastructure."""

from __future__ import annotations

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
