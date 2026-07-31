"""Phase 3 source-block indexing service with fake vector infrastructure."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import math
from typing import Callable, Protocol

from services.application.app.core_sot.service import CoreSotService, NotFound
from services.application.app.indexing.models import (
    IndexSyncErrorType,
    IndexSyncEvent,
    IndexSyncLastError,
    IndexSyncLog,
    IndexSyncOutboxEntry,
    IndexPointer,
    IndexRecordKind,
    IndexRecordValidation,
    IndexStaleReason,
    IndexSyncRequest,
    IndexSyncResult,
    IndexSyncSource,
    IndexSyncStatus,
    IndexSyncTarget,
    IndexSyncTargetState,
    SinkOutcome,
    SourceBlockIndexRecord,
)


SOURCE_BLOCK_COLLECTION = "source_blocks"
FAKE_VECTOR_BACKEND = "in_memory_fake"
CHROMA_VECTOR_BACKEND = "chroma"
INDEX_SYNC_MAX_ATTEMPTS = 3
INDEX_SYNC_CLAIM_TIMEOUT_SECONDS = 600
INDEX_SYNC_BACKOFF_SECONDS = (60, 300)
PROJECTS_COLLECTION = "projects"
DRAFTS_COLLECTION = "drafts"
MEMORIES_COLLECTION = "memory_entries"
CANDIDATES_COLLECTION = "analysis_candidates"
# b-6 증분2: free-form per-sink target keys (G6=A — no new SoT enum literal). The
# worker materializes these on the outbox entry when it drains a composite sink.
VECTOR_TARGET = "vector"
LEXICAL_TARGET = "lexical"
ELASTICSEARCH_BACKEND = "elasticsearch"
# Events whose drain fans out to per-sink (vector + lexical) bookkeeping. Archive
# events stay on the single-sink whole-event path (only a vector sink exists).
_PER_SINK_EVENTS = frozenset(
    {
        IndexSyncEvent.MEMORY_UPSERTED,
        IndexSyncEvent.CANDIDATE_UPSERTED,
        # Phase 6 (v1.6.61): removal reconciles the same candidate sinks; the
        # adapter re-derives status and deletes when not needs_review.
        IndexSyncEvent.CANDIDATE_REMOVED,
    }
)


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> tuple[float, ...]: ...


class VectorIndexAdapter(Protocol):
    def upsert_records(self, records: tuple[SourceBlockIndexRecord, ...]) -> int: ...


class ArchiveIndexMutationAdapter(Protocol):
    def mark_archived(self, entry: IndexSyncOutboxEntry) -> None: ...


class MemoryIndexMutationAdapter(Protocol):
    # b-6 증분2: the composite drains every configured sink and reports a
    # SinkOutcome per sink; ``skip`` holds targets that already reached SUCCESS on
    # a prior attempt so a replay does not re-index a healthy sink (G4=B).
    def drain(
        self, entry: IndexSyncOutboxEntry, *, skip: frozenset[str]
    ) -> tuple[SinkOutcome, ...]: ...


class CandidateIndexMutationAdapter(Protocol):
    def drain(
        self, entry: IndexSyncOutboxEntry, *, skip: frozenset[str]
    ) -> tuple[SinkOutcome, ...]: ...


class IndexSyncRepository(Protocol):
    def next_sync_request_id(self) -> str: ...

    def next_sync_log_id(self) -> str: ...

    def get_outbox_entry_by_dedup_key(
        self,
        *,
        project_id: str,
        event: IndexSyncEvent,
        source: IndexSyncSource,
    ) -> IndexSyncOutboxEntry | None: ...

    def put_outbox_entry(self, entry: IndexSyncOutboxEntry) -> None: ...

    def claim_next_outbox_entry(
        self,
        *,
        now: datetime,
        claim_timeout_seconds: int,
    ) -> IndexSyncOutboxEntry | None: ...

    def record_outbox_success(
        self,
        entry: IndexSyncOutboxEntry,
        *,
        started_at: datetime,
        finished_at: datetime,
        targets: dict[str, IndexSyncTargetState] | None = None,
    ) -> IndexSyncLog: ...

    def record_outbox_failure(
        self,
        entry: IndexSyncOutboxEntry,
        *,
        error: IndexSyncLastError,
        started_at: datetime,
        finished_at: datetime,
        targets: dict[str, IndexSyncTargetState] | None = None,
        terminal: bool | None = None,
    ) -> IndexSyncLog: ...


class InMemoryIndexSyncRepository:
    def __init__(self) -> None:
        self._sync_request_seq = 0
        self._sync_log_seq = 0
        self.outbox_entries: dict[str, IndexSyncOutboxEntry] = {}
        self.logs: list[IndexSyncLog] = []
        self._outbox_dedup: dict[tuple[str, IndexSyncEvent, str, str], str] = {}

    def next_sync_request_id(self) -> str:
        self._sync_request_seq += 1
        return f"index-sync-request-{self._sync_request_seq}"

    def next_sync_log_id(self) -> str:
        self._sync_log_seq += 1
        return f"index-sync-log-{self._sync_log_seq}"

    def get_outbox_entry_by_dedup_key(
        self,
        *,
        project_id: str,
        event: IndexSyncEvent,
        source: IndexSyncSource,
    ) -> IndexSyncOutboxEntry | None:
        entry_id = self._outbox_dedup.get(_dedup_key(project_id, event, source))
        if entry_id is None:
            return None
        entry = self.outbox_entries.get(entry_id)
        if entry is None or entry.status not in _ACTIVE_OUTBOX_STATUSES:
            return None
        return entry

    def put_outbox_entry(self, entry: IndexSyncOutboxEntry) -> None:
        key = _dedup_key(entry.project_id, entry.event, entry.source)
        existing_id = self._outbox_dedup.get(key)
        if existing_id is not None:
            return
        self.outbox_entries[entry.sync_request_id] = entry
        self._outbox_dedup[key] = entry.sync_request_id

    def claim_next_outbox_entry(
        self,
        *,
        now: datetime,
        claim_timeout_seconds: int,
    ) -> IndexSyncOutboxEntry | None:
        stale_before = now - timedelta(seconds=claim_timeout_seconds)
        candidates = [
            entry
            for entry in self.outbox_entries.values()
            if _claimable(entry, now=now, stale_before=stale_before)
        ]
        if not candidates:
            return None
        entry = sorted(candidates, key=_claim_sort_key)[0]
        claimed = replace(
            entry,
            status=IndexSyncStatus.RUNNING,
            claimed_at=now,
        )
        self.outbox_entries[claimed.sync_request_id] = claimed
        return claimed

    def record_outbox_success(
        self,
        entry: IndexSyncOutboxEntry,
        *,
        started_at: datetime,
        finished_at: datetime,
        targets: dict[str, IndexSyncTargetState] | None = None,
    ) -> IndexSyncLog:
        log = _sync_log(
            repository=self,
            entry=entry,
            status=IndexSyncStatus.SUCCESS,
            attempt_count=entry.attempt_count + 1,
            error=None,
            started_at=started_at,
            finished_at=finished_at,
            targets=targets,
        )
        self._remove_outbox_entry(entry)
        self.logs.append(log)
        return log

    def record_outbox_failure(
        self,
        entry: IndexSyncOutboxEntry,
        *,
        error: IndexSyncLastError,
        started_at: datetime,
        finished_at: datetime,
        targets: dict[str, IndexSyncTargetState] | None = None,
        terminal: bool | None = None,
    ) -> IndexSyncLog:
        # b-6 증분2: per-sink callers pass merged ``targets`` + a worker-computed
        # ``terminal`` (all sinks SUCCESS or per-sink-max FAILED). The single-sink
        # archive path passes neither and keeps whole-event attempt-count DLQ.
        attempt_count = entry.attempt_count + 1
        effective_targets = targets if targets is not None else entry.targets
        if terminal is None:
            terminal = attempt_count >= entry.max_attempts
        log = _sync_log(
            repository=self,
            entry=entry,
            status=IndexSyncStatus.FAILED,
            attempt_count=attempt_count,
            error=error,
            started_at=started_at,
            finished_at=finished_at,
            targets=effective_targets,
        )
        self.logs.append(log)
        if terminal:
            self._remove_outbox_entry(entry)
            return log
        retry = replace(
            entry,
            status=IndexSyncStatus.PENDING,
            attempt_count=attempt_count,
            next_attempt_at=finished_at
            + timedelta(seconds=_backoff_seconds(attempt_count)),
            claimed_at=None,
            last_error=error,
            targets=effective_targets,
        )
        self.outbox_entries[retry.sync_request_id] = retry
        return log

    def _remove_outbox_entry(self, entry: IndexSyncOutboxEntry) -> None:
        self.outbox_entries.pop(entry.sync_request_id, None)
        self._outbox_dedup.pop(
            _dedup_key(entry.project_id, entry.event, entry.source),
            None,
        )


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

    def query_similar(
        self, *, project_id: str, vector: tuple[float, ...], limit: int
    ) -> tuple[SourceBlockIndexRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        scored = sorted(
            self.list_records(project_id=project_id),
            key=lambda record: (-_cosine_similarity(vector, record.vector), record.id),
        )
        return tuple(scored[:limit])


class IndexSyncOutboxService:
    def __init__(self, repository: IndexSyncRepository) -> None:
        self._repo = repository

    def enqueue_project_archived(
        self, *, project_id: str
    ) -> IndexSyncOutboxEntry:
        return self._enqueue_event(
            project_id=project_id,
            event=IndexSyncEvent.PROJECT_ARCHIVED,
            source=IndexSyncSource(
                mongo_collection=PROJECTS_COLLECTION,
                mongo_id=project_id,
            ),
        )

    def enqueue_project_purged(
        self, *, project_id: str
    ) -> IndexSyncOutboxEntry:
        # D8-6a: entry만 생산. drain(handler)은 D8-6c에서 붙인다 — endpoint(D8-6d)가 유일한
        # production 호출자이므로, 그 전엔 worker가 이 entry를 만날 일이 없다.
        return self._enqueue_event(
            project_id=project_id,
            event=IndexSyncEvent.PROJECT_PURGED,
            source=IndexSyncSource(
                mongo_collection=PROJECTS_COLLECTION,
                mongo_id=project_id,
            ),
        )

    def enqueue_draft_archived(
        self, *, project_id: str, draft_id: str
    ) -> IndexSyncOutboxEntry:
        return self._enqueue_event(
            project_id=project_id,
            event=IndexSyncEvent.DRAFT_ARCHIVED,
            source=IndexSyncSource(
                mongo_collection=DRAFTS_COLLECTION,
                mongo_id=draft_id,
            ),
        )

    def enqueue_memory_upserted(
        self, *, project_id: str, memory_id: str, version: int
    ) -> IndexSyncOutboxEntry:
        # Phase 2B.5 (D3=B): apply enqueues; the worker loads the memory and
        # reindexes it. Dedup is per memory_id, so a replay collapses onto the
        # same pending entry. See memory_index.MemoryIndexSyncAdapter.
        return self._enqueue_event(
            project_id=project_id,
            event=IndexSyncEvent.MEMORY_UPSERTED,
            source=IndexSyncSource(
                mongo_collection=MEMORIES_COLLECTION,
                mongo_id=memory_id,
                mongo_version=version,
            ),
        )

    def enqueue_candidate_upserted(
        self, *, project_id: str, candidate_id: str
    ) -> IndexSyncOutboxEntry:
        # b-2: record_candidate(s) enqueues; the worker loads the candidate and
        # indexes it. Dedup is per candidate_id, so a replay collapses onto the
        # same pending entry. See candidate_index.CandidateIndexSyncAdapter.
        return self._enqueue_event(
            project_id=project_id,
            event=IndexSyncEvent.CANDIDATE_UPSERTED,
            source=IndexSyncSource(
                mongo_collection=CANDIDATES_COLLECTION,
                mongo_id=candidate_id,
            ),
        )

    def enqueue_candidate_removed(
        self, *, project_id: str, candidate_id: str
    ) -> IndexSyncOutboxEntry:
        # Phase 6 (v1.6.61): a candidate left needs_review (confirmed/rejected);
        # the worker deletes it from the candidate index. Dedup is per
        # candidate_id, so a replay collapses onto the same pending entry. See
        # candidate_index.CandidateIndexSyncAdapter.drain (removed branch).
        return self._enqueue_event(
            project_id=project_id,
            event=IndexSyncEvent.CANDIDATE_REMOVED,
            source=IndexSyncSource(
                mongo_collection=CANDIDATES_COLLECTION,
                mongo_id=candidate_id,
            ),
        )

    def _enqueue_event(
        self,
        *,
        project_id: str,
        event: IndexSyncEvent,
        source: IndexSyncSource,
    ) -> IndexSyncOutboxEntry:
        existing = self._repo.get_outbox_entry_by_dedup_key(
            project_id=project_id,
            event=event,
            source=source,
        )
        if existing is not None:
            return existing
        entry = IndexSyncOutboxEntry(
            sync_request_id=self._repo.next_sync_request_id(),
            project_id=project_id,
            user_id=None,
            event=event,
            source=source,
            # b-6 증분2 (step 2): enqueue stays sink-agnostic — the choke point
            # cannot know which sinks the deployment configured, so it leaves
            # targets empty and the worker materializes per-sink state on claim.
            targets={},
            status=IndexSyncStatus.PENDING,
            attempt_count=0,
            max_attempts=INDEX_SYNC_MAX_ATTEMPTS,
            next_attempt_at=None,
            claimed_at=None,
            last_error=None,
        )
        self._repo.put_outbox_entry(entry)
        return entry


class DerivedIndexRecordNotFound(Exception):
    """Raised when archive mutation target is already absent."""


class RecordingArchiveIndexMutationAdapter:
    def __init__(self) -> None:
        self.marked_archived: list[IndexSyncOutboxEntry] = []

    def mark_archived(self, entry: IndexSyncOutboxEntry) -> None:
        self.marked_archived.append(entry)


@dataclass(frozen=True, slots=True)
class IndexSyncWorkerSummary:
    entries_claimed: int
    entries_succeeded: int
    entries_failed: int
    entries_requeued: int


class IndexSyncWorker:
    def __init__(
        self,
        *,
        repository: IndexSyncRepository,
        archive_adapter: ArchiveIndexMutationAdapter,
        memory_adapter: MemoryIndexMutationAdapter | None = None,
        candidate_adapter: CandidateIndexMutationAdapter | None = None,
        claim_timeout_seconds: int = INDEX_SYNC_CLAIM_TIMEOUT_SECONDS,
    ) -> None:
        self._repo = repository
        self._archive_adapter = archive_adapter
        self._memory_adapter = memory_adapter
        self._candidate_adapter = candidate_adapter
        self._claim_timeout_seconds = claim_timeout_seconds

    def run_once(
        self,
        *,
        limit: int,
        now: datetime | None = None,
        stop_check: Callable[[], bool] | None = None,
    ) -> IndexSyncWorkerSummary:
        if limit < 1:
            raise ValueError("limit must be positive")
        clock = now or datetime.now(timezone.utc)
        claimed = succeeded = failed = requeued = 0
        for _ in range(limit):
            # b-6 (G2): a drain loop passes stop_check so SIGTERM finishes the
            # in-flight entry then exits at the next claim boundary. Checked
            # before claiming so a partially-drained pass never starts a new one.
            if stop_check is not None and stop_check():
                break
            entry = self._repo.claim_next_outbox_entry(
                now=clock,
                claim_timeout_seconds=self._claim_timeout_seconds,
            )
            if entry is None:
                break
            claimed += 1
            if entry.event in _PER_SINK_EVENTS:
                disposition = self._drain_sinks(entry, clock)
            else:
                disposition = self._drain_archive(entry, clock)
            if disposition is _Disposition.SUCCEEDED:
                succeeded += 1
            elif disposition is _Disposition.REQUEUED:
                failed += 1
                requeued += 1
            else:
                failed += 1
        return IndexSyncWorkerSummary(
            entries_claimed=claimed,
            entries_succeeded=succeeded,
            entries_failed=failed,
            entries_requeued=requeued,
        )

    def _drain_archive(
        self, entry: IndexSyncOutboxEntry, clock: datetime
    ) -> "_Disposition":
        # Single-sink whole-event path (only a vector sink exists for archive):
        # unchanged from before b-6 증분2.
        try:
            self._archive_adapter.mark_archived(entry)
        except DerivedIndexRecordNotFound:
            self._repo.record_outbox_success(
                entry, started_at=clock, finished_at=clock
            )
            return _Disposition.SUCCEEDED
        except Exception as exc:
            will_requeue = entry.attempt_count + 1 < entry.max_attempts
            self._repo.record_outbox_failure(
                entry,
                error=_backend_error(exc),
                started_at=clock,
                finished_at=clock,
            )
            return _Disposition.REQUEUED if will_requeue else _Disposition.FAILED
        self._repo.record_outbox_success(entry, started_at=clock, finished_at=clock)
        return _Disposition.SUCCEEDED

    def _drain_sinks(
        self, entry: IndexSyncOutboxEntry, clock: datetime
    ) -> "_Disposition":
        # Per-sink path (b-6 증분2, G3=B/G4=B): the composite drains every
        # configured sink except those that already reached SUCCESS, and reports a
        # SinkOutcome per sink. The worker merges these into per-sink target state
        # (each sink carries its own attempt_count), then deletes the entry only
        # when every sink is terminal (SUCCESS, or FAILED at its own max) so one
        # persistently-down sink never poisons a healthy one.
        adapter = (
            self._memory_adapter
            if entry.event is IndexSyncEvent.MEMORY_UPSERTED
            else self._candidate_adapter
        )
        if adapter is None:
            will_requeue = entry.attempt_count + 1 < entry.max_attempts
            self._repo.record_outbox_failure(
                entry,
                error=IndexSyncLastError(
                    error_type=IndexSyncErrorType.BACKEND_ERROR,
                    detail=f"index adapter is not configured for {entry.event.value}",
                ),
                started_at=clock,
                finished_at=clock,
            )
            return _Disposition.REQUEUED if will_requeue else _Disposition.FAILED

        skip = frozenset(
            target
            for target, state in entry.targets.items()
            if state.status is IndexSyncStatus.SUCCESS
        )
        outcomes = adapter.drain(entry, skip=skip)
        targets = _merge_target_states(entry, outcomes)
        # On the per-sink path the terminal/requeue decision is driven entirely by
        # per-sink state (``_classify_targets``); the entry-level attempt_count that
        # ``record_outbox_failure`` still bumps only feeds the requeue backoff — it
        # no longer gates DLQ (that is each sink's own budget). ``terminal`` is
        # always passed explicitly so the whole-event max-attempts fallback (archive
        # only) never fires here.
        disposition, error = _classify_targets(targets, entry.max_attempts)
        if disposition is _Disposition.SUCCEEDED:
            self._repo.record_outbox_success(
                entry, started_at=clock, finished_at=clock, targets=targets
            )
            return _Disposition.SUCCEEDED
        self._repo.record_outbox_failure(
            entry,
            error=error,
            started_at=clock,
            finished_at=clock,
            targets=targets,
            terminal=disposition is _Disposition.FAILED,
        )
        return disposition


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
    vector_index: InMemoryVectorIndexAdapter | None = None,
    embeddings: EmbeddingProvider | None = None,
) -> SourceBlockIndexRebuildSummary:
    # When a shared in-process vector index is provided the rebuild accumulates
    # into it (so context search in the same process can query it); otherwise a
    # throwaway adapter keeps the CLI script non-persistent. Either way the
    # summary counts are scoped to this rebuild's snapshot_id, preserving the
    # per-rebuild "no accumulation" contract (SoT v1.6.23). See
    # docs/plans/04-shared-vector-index-decisions.md.
    if vector_index is None:
        vector_index = InMemoryVectorIndexAdapter()
    if embeddings is None:
        embeddings = DeterministicFakeEmbeddingProvider(dimensions=embedding_dimensions)
    service = SourceBlockIndexingService(
        core_sot=core_sot,
        embeddings=embeddings,
        vector_index=vector_index,
    )
    result = service.rebuild_snapshot_source_block_index(
        project_id=project_id,
        snapshot_id=snapshot_id,
    )
    all_records = tuple(
        record
        for record in vector_index.list_records(
            project_id=project_id, include_archived=True
        )
        if record.snapshot_id == snapshot_id
    )
    visible_records = tuple(
        record
        for record in vector_index.list_records(project_id=project_id)
        if record.snapshot_id == snapshot_id
    )
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

    def validate_source_block_record(
        self, record: SourceBlockIndexRecord
    ) -> IndexRecordValidation:
        reasons: list[IndexStaleReason] = []
        project_id = record.pointer.project_id
        try:
            detail = self._core_sot.get_snapshot(
                project_id=project_id,
                snapshot_id=record.snapshot_id,
            )
        except NotFound:
            return IndexRecordValidation(
                record_id=record.id,
                usable=False,
                stale_reasons=(IndexStaleReason.SNAPSHOT_MISSING,),
            )

        project = self._core_sot.get_project(project_id=project_id)
        draft = self._core_sot.get_draft(
            project_id=project_id,
            draft_id=detail.snapshot.draft_id,
        )
        if project.archived:
            reasons.append(IndexStaleReason.PROJECT_ARCHIVED)
        if draft.archived:
            reasons.append(IndexStaleReason.DRAFT_ARCHIVED)
        if record.draft_id != detail.snapshot.draft_id:
            reasons.append(IndexStaleReason.DRAFT_MISMATCH)
        if record.pointer.content_hash != detail.snapshot.content_hash:
            reasons.append(IndexStaleReason.CONTENT_HASH_MISMATCH)
        if record.block_id not in {block.id for block in detail.blocks}:
            reasons.append(IndexStaleReason.BLOCK_MISSING)
        return IndexRecordValidation(
            record_id=record.id,
            usable=not reasons,
            stale_reasons=tuple(reasons),
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


def _dedup_key(
    project_id: str, event: IndexSyncEvent, source: IndexSyncSource
) -> tuple[str, IndexSyncEvent, str, str]:
    return (project_id, event, source.mongo_collection, source.mongo_id)


def _cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


_ACTIVE_OUTBOX_STATUSES = {
    IndexSyncStatus.PENDING,
    IndexSyncStatus.RUNNING,
}


def _claimable(
    entry: IndexSyncOutboxEntry,
    *,
    now: datetime,
    stale_before: datetime,
) -> bool:
    if entry.status == IndexSyncStatus.PENDING:
        return entry.next_attempt_at is None or entry.next_attempt_at <= now
    if entry.status == IndexSyncStatus.RUNNING:
        return entry.claimed_at is not None and entry.claimed_at <= stale_before
    return False


def _claim_sort_key(entry: IndexSyncOutboxEntry) -> tuple[datetime, str]:
    return (
        entry.next_attempt_at or datetime.min.replace(tzinfo=timezone.utc),
        entry.sync_request_id,
    )


def _backoff_seconds(attempt_count: int) -> int:
    index = max(0, attempt_count - 1)
    if index >= len(INDEX_SYNC_BACKOFF_SECONDS):
        return INDEX_SYNC_BACKOFF_SECONDS[-1]
    return INDEX_SYNC_BACKOFF_SECONDS[index]


class _Disposition(Enum):
    """Outcome of draining one outbox entry, driving the worker summary counters."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REQUEUED = "requeued"


def _backend_error(exc: Exception) -> IndexSyncLastError:
    return IndexSyncLastError(
        error_type=IndexSyncErrorType.BACKEND_ERROR,
        detail=str(exc),
    )


def _merge_target_states(
    entry: IndexSyncOutboxEntry, outcomes: tuple[SinkOutcome, ...]
) -> dict[str, IndexSyncTargetState]:
    # Carry forward frozen SUCCESS sinks (they were skipped this pass), then fold in
    # this pass's outcomes — each sink's attempt_count advances on its own budget.
    merged = dict(entry.targets)
    for outcome in outcomes:
        prior = entry.targets.get(outcome.target)
        prior_attempts = prior.attempt_count if prior is not None else 0
        merged[outcome.target] = IndexSyncTargetState(
            status=(
                IndexSyncStatus.SUCCESS if outcome.ok else IndexSyncStatus.FAILED
            ),
            backend=outcome.backend,
            attempt_count=prior_attempts + 1,
            last_error=None if outcome.ok else outcome.error,
        )
    return merged


def _classify_targets(
    targets: dict[str, IndexSyncTargetState], max_attempts: int
) -> tuple[_Disposition, IndexSyncLastError | None]:
    # A missing/empty target set means there is nothing to keep retrying — drop it
    # (should not happen: a composite always has at least one sink).
    if not targets or all(
        state.status is IndexSyncStatus.SUCCESS for state in targets.values()
    ):
        return _Disposition.SUCCEEDED, None
    error = next(
        (
            state.last_error
            for state in targets.values()
            if state.status is IndexSyncStatus.FAILED and state.last_error is not None
        ),
        None,
    )
    if all(_sink_terminal(state, max_attempts) for state in targets.values()):
        return _Disposition.FAILED, error
    return _Disposition.REQUEUED, error


def _sink_terminal(state: IndexSyncTargetState, max_attempts: int) -> bool:
    if state.status is IndexSyncStatus.SUCCESS:
        return True
    return (
        state.status is IndexSyncStatus.FAILED
        and state.attempt_count >= max_attempts
    )


def _sync_log(
    *,
    repository: IndexSyncRepository,
    entry: IndexSyncOutboxEntry,
    status: IndexSyncStatus,
    attempt_count: int,
    error: IndexSyncLastError | None,
    started_at: datetime,
    finished_at: datetime,
    targets: dict[str, IndexSyncTargetState] | None = None,
) -> IndexSyncLog:
    return IndexSyncLog(
        sync_log_id=repository.next_sync_log_id(),
        sync_request_id=entry.sync_request_id,
        project_id=entry.project_id,
        user_id=entry.user_id,
        event=entry.event,
        source=entry.source,
        targets=targets if targets is not None else entry.targets,
        status=status,
        attempt_count=attempt_count,
        error=error,
        started_at=started_at,
        finished_at=finished_at,
    )
