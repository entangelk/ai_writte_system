"""b-2 increment 1: project ``needs_review`` candidates into a vector index.

Mirror of the canonical vector leg (``memory_index.py``) for candidates, kept
physically separate (own collection) because the authority source and lifecycle
differ (G1). Write path only: ``record_candidate(s)`` enqueues a
``CANDIDATE_UPSERTED`` outbox event and the worker drains it here.

The drain is a *reconcile* keyed on the candidate id, not a blind upsert:
``index_candidate`` re-derives the candidate's current status from the store and
either upserts (still ``needs_review``) or deletes (missing, or left needs_review).
So ``CANDIDATE_UPSERTED`` and the Phase 6 (v1.6.61) ``CANDIDATE_REMOVED`` event
share **one** code path — the event only decides *when* to reconcile, the store's
current truth decides *what*. A ``confirmed``/``rejected`` candidate is therefore
de-indexed by either event, giving the self-healing invariant "exactly the current
needs_review candidates are indexed" (same as the canonical leg). The worker routes
both events through the per-sink candidate path (``_PER_SINK_EVENTS``).
"""

from __future__ import annotations

from typing import Any, Protocol

from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateStatus,
)
from services.application.app.analysis.service import AnalysisNotFound, AnalysisService
from services.application.app.indexing.memory_index import (
    EmbeddingProvider,
    derive_memory_index_text,
)
from services.application.app.indexing.models import (
    CandidateIndexRecord,
    IndexRecordKind,
    IndexSyncErrorType,
    IndexSyncLastError,
    IndexSyncOutboxEntry,
    SinkOutcome,
)
from services.application.app.indexing.service import _cosine_similarity


CANDIDATE_VECTOR_COLLECTION = "candidate_vectors"


class CandidateVectorIndexAdapter(Protocol):
    def upsert_candidate_records(
        self, records: tuple[CandidateIndexRecord, ...]
    ) -> int: ...

    def delete_candidate_record(
        self, *, project_id: str, candidate_id: str
    ) -> None: ...

    def list_candidate_records(
        self, *, project_id: str
    ) -> tuple[CandidateIndexRecord, ...]: ...

    def query_similar(
        self,
        *,
        project_id: str,
        candidate_type: str,
        vector: tuple[float, ...],
        limit: int,
    ) -> tuple[CandidateIndexRecord, ...]: ...

    # D8-6c: hard, whole-project delete of the candidate_vectors collection. Purge
    # is irreversible+idempotent, so an already-empty result is NOT an error.
    def purge_project(self, *, project_id: str) -> None: ...


class InMemoryCandidateVectorIndexAdapter:
    """No-infra vector backend for unit tests and the deterministic fallback."""

    def __init__(self) -> None:
        self.records: dict[str, CandidateIndexRecord] = {}

    def upsert_candidate_records(
        self, records: tuple[CandidateIndexRecord, ...]
    ) -> int:
        for record in records:
            self.records[record.id] = record
        return len(records)

    def delete_candidate_record(
        self, *, project_id: str, candidate_id: str
    ) -> None:
        existing = self.records.get(candidate_id)
        if existing is not None and existing.project_id == project_id:
            del self.records[candidate_id]

    def query_similar(
        self,
        *,
        project_id: str,
        candidate_type: str,
        vector: tuple[float, ...],
        limit: int,
    ) -> tuple[CandidateIndexRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        candidates = [
            record
            for record in self.records.values()
            if record.project_id == project_id
            and record.candidate_type == candidate_type
        ]
        ranked = sorted(
            candidates,
            key=lambda record: (
                -_cosine_similarity(vector, record.vector),
                record.id,
            ),
        )
        return tuple(ranked[:limit])

    def list_candidate_records(
        self, *, project_id: str
    ) -> tuple[CandidateIndexRecord, ...]:
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

    def purge_project(self, *, project_id: str) -> None:
        # D8-6c: drop every record of one project. Idempotent — a project that was
        # never indexed (or already purged) simply leaves nothing to remove.
        self.records = {
            record_id: record
            for record_id, record in self.records.items()
            if record.project_id != project_id
        }


def candidate_index_text(candidate: AnalysisCandidate) -> str:
    """The candidate index text uses the same deterministic projection as the
    canonical index, so the write and query surfaces rank the same text."""
    return derive_memory_index_text(candidate.candidate_type, candidate.payload)


def build_candidate_index_record(
    candidate: AnalysisCandidate, *, text: str, vector: tuple[float, ...]
) -> CandidateIndexRecord:
    return CandidateIndexRecord(
        id=candidate.id,
        kind=IndexRecordKind.CANDIDATE,
        project_id=candidate.project_id,
        candidate_id=candidate.id,
        candidate_type=candidate.candidate_type.value,
        status=candidate.status.value,
        text=text,
        vector=vector,
    )


class CandidateIndexSyncAdapter:
    """Worker-side adapter: load the candidate an entry points at and reindex it."""

    def __init__(
        self,
        *,
        analysis_service: AnalysisService,
        embeddings: EmbeddingProvider,
        vector_index: CandidateVectorIndexAdapter,
    ) -> None:
        self._analysis = analysis_service
        self._embeddings = embeddings
        self._vector_index = vector_index

    def index_candidate(self, entry: IndexSyncOutboxEntry) -> None:
        project_id = entry.project_id
        candidate_id = entry.source.mongo_id
        try:
            candidate = self._analysis.get_candidate(
                project_id=project_id, candidate_id=candidate_id
            )
        except AnalysisNotFound:
            # The candidate was removed before we indexed it; drop any stale
            # vector (forward-defense — no removal path exists today).
            self._vector_index.delete_candidate_record(
                project_id=project_id, candidate_id=candidate_id
            )
            return

        if candidate.status is not AnalysisCandidateStatus.NEEDS_REVIEW:
            # Phase 6 forward-defense: a confirmed/rejected candidate leaves the
            # retrievable set, so drop its vector (unreachable while the status
            # enum is single-valued).
            self._vector_index.delete_candidate_record(
                project_id=project_id, candidate_id=candidate.id
            )
            return

        text = candidate_index_text(candidate)
        vector = self._embeddings.embed(text)
        record = build_candidate_index_record(candidate, text=text, vector=vector)
        self._vector_index.upsert_candidate_records((record,))

    def purge_project(self, *, project_id: str) -> None:
        # D8-6c: whole-project purge of the vector leg. Unlike index_candidate,
        # purge is idempotent (an already-empty backend is success, not a
        # not-found), so there is no load/status branching here.
        self._vector_index.purge_project(project_id=project_id)


class CompositeCandidateIndexSyncAdapter:
    """Fan a CANDIDATE_UPSERTED drain out to every configured candidate sink
    (vector + lexical), so one outbox entry keeps both indexes current (b-6 증분2).

    Named-sink mirror of ``CompositeMemoryIndexSyncAdapter``: each sink is
    ``(target, backend, adapter)`` and ``drain`` runs every sink NOT in ``skip``
    under try/except, returning a per-sink ``SinkOutcome`` so the worker tracks a
    per-sink retry budget (G4=B)."""

    def __init__(self, sinks: tuple[tuple[str, str, Any], ...]) -> None:
        self._sinks = tuple(sinks)

    def drain(
        self, entry: IndexSyncOutboxEntry, *, skip: frozenset[str]
    ) -> tuple[SinkOutcome, ...]:
        outcomes: list[SinkOutcome] = []
        for target, backend, adapter in self._sinks:
            if target in skip:
                continue
            try:
                adapter.index_candidate(entry)
            except Exception as exc:  # per-sink isolation (G4=B)
                outcomes.append(
                    SinkOutcome(
                        target=target,
                        backend=backend,
                        ok=False,
                        error=IndexSyncLastError(
                            error_type=IndexSyncErrorType.BACKEND_ERROR,
                            detail=str(exc),
                        ),
                    )
                )
            else:
                outcomes.append(
                    SinkOutcome(target=target, backend=backend, ok=True, error=None)
                )
        return tuple(outcomes)

    def purge_project(self, *, project_id: str) -> None:
        # D8-6c: fan a whole-project purge out to every configured candidate sink
        # (vector + lexical). Unlike ``drain`` this does NOT isolate per sink — a
        # failure propagates so the worker retries the whole PROJECT_PURGED entry
        # (mirrors CompositeMemoryIndexSyncAdapter.purge_project). Each sink
        # adapter owns its own idempotent ``purge_project``.
        for _target, _backend, adapter in self._sinks:
            adapter.purge_project(project_id=project_id)
