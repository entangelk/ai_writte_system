"""Source loading and source_ref validation adapters for Phase 2A."""

from __future__ import annotations

from typing import Protocol

from services.application.app.analysis.models import SnapshotText
from services.application.app.core_sot.models import SourceRef
from services.application.app.core_sot.service import CoreSotService, NotFound


class SourceRefResolver(Protocol):
    def get_source_ref(
        self, *, project_id: str, source_ref_id: str
    ) -> SourceRef | None: ...


class SnapshotLoader(Protocol):
    def load_snapshot(self, *, project_id: str, snapshot_id: str) -> SnapshotText: ...


class CoreSotSourceAdapter:
    """Adapter that exposes Core SOT source material to analysis code."""

    def __init__(self, core_sot: CoreSotService) -> None:
        self._core_sot = core_sot

    def get_source_ref(
        self, *, project_id: str, source_ref_id: str
    ) -> SourceRef | None:
        try:
            return self._core_sot.get_source_ref(
                project_id=project_id,
                source_ref_id=source_ref_id,
            )
        except NotFound:
            return None

    def load_snapshot(self, *, project_id: str, snapshot_id: str) -> SnapshotText:
        detail = self._core_sot.get_snapshot(
            project_id=project_id,
            snapshot_id=snapshot_id,
        )
        return SnapshotText(
            project_id=detail.snapshot.project_id,
            snapshot_id=detail.snapshot.id,
            raw_text=detail.snapshot.raw_text,
            content_hash=detail.snapshot.content_hash,
            block_ids=tuple(block.id for block in detail.blocks),
        )
