"""b-2 increment 1: project ``needs_review`` candidates into a vector index.

Mirror of the canonical vector leg (``memory_index.py``) for candidates, kept
physically separate (own collection) because the authority source and lifecycle
differ (G1). Write path only: ``record_candidate(s)`` enqueues a
``CANDIDATE_UPSERTED`` outbox event and the worker drains it here.

Candidates are immutable today (a single ``needs_review`` status, no versioning)
so the drain is upsert-only in the common case. The delete branches are
forward-defense: they become reachable when Phase 6 introduces
``confirmed``/``rejected`` transitions that leave the candidate set. Both the
status-changed and the removed branches drop the stale vector so a later drain
converges on "exactly the current needs_review candidates are indexed" — the
same self-healing invariant as the canonical leg.
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
    IndexSyncOutboxEntry,
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


class CompositeCandidateIndexSyncAdapter:
    """Fan a CANDIDATE_UPSERTED drain out to every configured candidate sink
    (vector + lexical), so one outbox entry keeps both indexes current. Each
    sink's ``index_candidate`` is idempotent, so a replay after a partial failure
    re-drains both; if any sink raises, the entry fails and requeues."""

    def __init__(self, adapters: tuple[Any, ...]) -> None:
        self._adapters = tuple(adapters)

    def index_candidate(self, entry: IndexSyncOutboxEntry) -> None:
        for adapter in self._adapters:
            adapter.index_candidate(entry)
