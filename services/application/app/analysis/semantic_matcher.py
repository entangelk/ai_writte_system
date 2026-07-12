"""Phase 2B.6: embedding-backed semantic identity resolution for compare.

event/open_question candidates have no deterministic scope key (2B.3 D2=A), so
compare treats them as always-``create``. This matcher (D1=A, plugged into
``AnalysisCompareService`` via the ``SemanticMemoryMatcher`` seam) instead embeds
the candidate with the *same* projection the write path uses
(``derive_memory_index_text``, 2B.5) and queries the ``memory_vectors`` index for
the closest prior canonical memory of the same type. The single best match above
the similarity threshold (D6=A top-1) flows through compare's existing judge
logic; below threshold → no match → ``create`` (D4=A: threshold is injected and
off by default, so this is inert until calibrated).
"""

from __future__ import annotations

from typing import Protocol

from services.application.app.analysis.models import AnalysisCandidate
from services.application.app.indexing.memory_index import (
    MemoryIndexRecord,
    derive_memory_index_text,
)
from services.application.app.indexing.service import _cosine_similarity
from services.application.app.memory.models import MemoryEntry, MemoryStatus
from services.application.app.memory.service import MemoryNotFound, MemoryService


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> tuple[float, ...]: ...


class MemoryVectorSearch(Protocol):
    def query_similar(
        self,
        *,
        project_id: str,
        memory_type: str,
        vector: tuple[float, ...],
        limit: int,
    ) -> tuple[MemoryIndexRecord, ...]: ...


class EmbeddingSemanticMatcher:
    def __init__(
        self,
        *,
        embeddings: EmbeddingProvider,
        vector_search: MemoryVectorSearch,
        memory_service: MemoryService,
        similarity_threshold: float,
        limit: int = 5,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be positive")
        self._embeddings = embeddings
        self._vector_search = vector_search
        self._memory = memory_service
        self._threshold = similarity_threshold
        self._limit = limit

    def match(
        self, *, project_id: str, job_id: str, candidate: AnalysisCandidate
    ) -> tuple[MemoryEntry, ...]:
        text = derive_memory_index_text(
            candidate.candidate_type, candidate.payload
        )
        query_vector = self._embeddings.embed(text)
        records = self._vector_search.query_similar(
            project_id=project_id,
            memory_type=candidate.candidate_type.value,
            vector=query_vector,
            limit=self._limit,
        )
        for record in records:
            if _cosine_similarity(query_vector, record.vector) < self._threshold:
                continue
            entry = self._resolve(project_id, record.memory_id)
            if entry is None:
                continue
            # Canonical-only (the index should hold canonical only, but a stale
            # record could point at a superseded id) + self-exclusion: a
            # candidate never matches memory its own job promoted (D6).
            if entry.status is not MemoryStatus.CANONICAL:
                continue
            if entry.analysis_job_id == job_id:
                continue
            # Top-1 (D6=A): the first eligible record is the highest-ranked one.
            return (entry,)
        return ()

    def _resolve(self, project_id: str, memory_id: str) -> MemoryEntry | None:
        try:
            return self._memory.get_memory(
                project_id=project_id, memory_id=memory_id
            )
        except MemoryNotFound:
            # Stale vector for a deleted memory; skip it.
            return None


class EmbeddingCharacterIdentityVerifier:
    """Compare a same-name candidate directly with its selected canonical."""

    def __init__(
        self, *, embeddings: EmbeddingProvider, similarity_floor: float
    ) -> None:
        self._embeddings = embeddings
        self._floor = similarity_floor

    def supports_same_identity(
        self, *, candidate: AnalysisCandidate, memory: MemoryEntry
    ) -> bool:
        candidate_vector = self._embeddings.embed(
            derive_memory_index_text(candidate.candidate_type, candidate.payload)
        )
        memory_vector = self._embeddings.embed(
            derive_memory_index_text(memory.memory_type, memory.payload)
        )
        return _cosine_similarity(candidate_vector, memory_vector) >= self._floor
