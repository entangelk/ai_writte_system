"""b-2 increment 1: project ``needs_review`` candidates into a lexical (ES) index.

Mirror of the canonical lexical leg (``memory_lexical_index.py``) for
candidates, kept physically separate (own ES index) because the authority source
and lifecycle differ (G1). The search filter pins ``status: needs_review`` (the
canonical leg pins ``canonical``). The nori analyzer / single-node replica
settings are shared with the memory index — only the mappings and index name
differ (no versioning field for candidates).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateStatus,
)
from services.application.app.analysis.service import AnalysisNotFound, AnalysisService
from services.application.app.indexing.candidate_index import candidate_index_text
from services.application.app.indexing.memory_lexical_index import (
    ELASTICSEARCH_MEMORY_SETTINGS,
    ElasticsearchClient,
    _tokens,
)
from services.application.app.indexing.models import IndexSyncOutboxEntry


CANDIDATE_LEXICAL_INDEX = "candidate_lexical"

# Shared nori / single-node replica settings with the memory index; candidates
# have no version field, so the mappings are candidate-specific.
ELASTICSEARCH_CANDIDATE_SETTINGS = ELASTICSEARCH_MEMORY_SETTINGS
ELASTICSEARCH_CANDIDATE_MAPPINGS: dict[str, Any] = {
    "properties": {
        "candidate_id": {"type": "keyword"},
        "mongo_collection": {"type": "keyword"},
        "project_id": {"type": "keyword"},
        "candidate_type": {"type": "keyword"},
        "status": {"type": "keyword"},
        "text": {"type": "text", "analyzer": "korean"},
    }
}


@dataclass(frozen=True, slots=True)
class CandidateLexicalRecord:
    """A ``needs_review`` candidate projected into the lexical index.

    ``score`` is the lexical relevance of a search hit (0.0 for stored records).
    """

    candidate_id: str
    project_id: str
    candidate_type: str
    status: str
    text: str
    score: float = 0.0


def build_candidate_lexical_record(candidate: AnalysisCandidate, *, text: str) -> CandidateLexicalRecord:
    return CandidateLexicalRecord(
        candidate_id=candidate.id,
        project_id=candidate.project_id,
        candidate_type=candidate.candidate_type.value,
        status=candidate.status.value,
        text=text,
    )


class CandidateLexicalIndexAdapter(Protocol):
    def index_candidate_records(
        self, records: tuple[CandidateLexicalRecord, ...]
    ) -> int: ...

    def delete_candidate_record(
        self, *, project_id: str, candidate_id: str
    ) -> None: ...

    def search(
        self, *, project_id: str, query: str, limit: int
    ) -> tuple[CandidateLexicalRecord, ...]: ...

    # D8-6c: hard, whole-project delete of the candidate lexical leg. Idempotent —
    # an already-empty index is success, not a not-found (purge is irreversible).
    def purge_project(self, *, project_id: str) -> None: ...


class InMemoryCandidateLexicalIndexAdapter:
    """No-infra lexical backend for unit tests and the deterministic fallback.

    Scores a document by the count of distinct query tokens it contains (a
    token-overlap proxy for BM25). Real Korean morphology (nori) is only in the
    Elasticsearch backend; unit tests drive whitespace-separable text."""

    def __init__(self) -> None:
        self.records: dict[str, CandidateLexicalRecord] = {}

    def index_candidate_records(
        self, records: tuple[CandidateLexicalRecord, ...]
    ) -> int:
        for record in records:
            self.records[record.candidate_id] = record
        return len(records)

    def delete_candidate_record(
        self, *, project_id: str, candidate_id: str
    ) -> None:
        existing = self.records.get(candidate_id)
        if existing is not None and existing.project_id == project_id:
            del self.records[candidate_id]

    def search(
        self, *, project_id: str, query: str, limit: int
    ) -> tuple[CandidateLexicalRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        query_tokens = set(_tokens(query))
        scored: list[CandidateLexicalRecord] = []
        for record in self.records.values():
            if record.project_id != project_id:
                continue
            overlap = query_tokens & set(_tokens(record.text))
            if not overlap:
                continue
            scored.append(
                CandidateLexicalRecord(
                    candidate_id=record.candidate_id,
                    project_id=record.project_id,
                    candidate_type=record.candidate_type,
                    status=record.status,
                    text=record.text,
                    score=float(len(overlap)),
                )
            )
        ranked = sorted(scored, key=lambda r: (-r.score, r.candidate_id))
        return tuple(ranked[:limit])

    def purge_project(self, *, project_id: str) -> None:
        # D8-6c: drop every document of one project. Idempotent — a project with
        # no documents leaves nothing to remove.
        self.records = {
            candidate_id: record
            for candidate_id, record in self.records.items()
            if record.project_id != project_id
        }


class ElasticsearchCandidateIndexAdapter:
    """Real lexical backend over an Elasticsearch index (nori-analyzed text).

    Documents carry the MongoDB pointer (``candidate_id``) so a hit is resolvable
    back to the analysis store; the ``text`` field is nori-analyzed by the index
    mapping. The search filter pins ``status: needs_review``."""

    def __init__(self, client: ElasticsearchClient, *, index_name: str) -> None:
        self._client = client
        self._index = index_name

    def index_candidate_records(
        self, records: tuple[CandidateLexicalRecord, ...]
    ) -> int:
        for record in records:
            self._client.index(
                index=self._index,
                id=record.candidate_id,
                document={
                    "candidate_id": record.candidate_id,
                    "mongo_collection": "analysis_candidates",
                    "project_id": record.project_id,
                    "candidate_type": record.candidate_type,
                    "status": record.status,
                    "text": record.text,
                },
            )
        return len(records)

    def delete_candidate_record(
        self, *, project_id: str, candidate_id: str
    ) -> None:
        # Doc id is the candidate id; a missing doc must not raise (idempotent).
        try:
            self._client.delete(index=self._index, id=candidate_id)
        except Exception:
            pass

    def purge_project(self, *, project_id: str) -> None:
        # D8-6c: delete every document of one project via a term filter on
        # project_id. ES delete_by_query returns 0 deleted for a project with no
        # documents — that is idempotent success, not an error (purge is
        # irreversible). The ElasticsearchClient Protocol (shared with the memory
        # leg) gained delete_by_query in 6c-1.
        self._client.delete_by_query(
            index=self._index,
            query={"term": {"project_id": project_id}},
        )

    def search(
        self, *, project_id: str, query: str, limit: int
    ) -> tuple[CandidateLexicalRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        bool_query = {
            "bool": {
                "must": {"match": {"text": query}},
                "filter": [
                    {"term": {"project_id": project_id}},
                    {"term": {"status": "needs_review"}},
                ],
            }
        }
        result = self._client.search(
            index=self._index, query=bool_query, size=limit
        )
        hits = result.get("hits", {}).get("hits", [])
        records: list[CandidateLexicalRecord] = []
        for hit in hits:
            source = hit.get("_source", {})
            records.append(
                CandidateLexicalRecord(
                    candidate_id=source["candidate_id"],
                    project_id=source["project_id"],
                    candidate_type=source["candidate_type"],
                    status=source["status"],
                    text=source["text"],
                    score=float(hit.get("_score") or 0.0),
                )
            )
        return tuple(records)


class CandidateLexicalIndexSyncAdapter:
    """Worker-side lexical drain: load the candidate a CANDIDATE_UPSERTED entry
    points at and reindex it. Mirror of the vector leg's
    ``CandidateIndexSyncAdapter`` — needs_review → index, removed/transitioned →
    delete — so both branches are idempotent and order-independent."""

    def __init__(
        self,
        *,
        analysis_service: AnalysisService,
        lexical_index: CandidateLexicalIndexAdapter,
    ) -> None:
        self._analysis = analysis_service
        self._lexical = lexical_index

    def index_candidate(self, entry: IndexSyncOutboxEntry) -> None:
        project_id = entry.project_id
        candidate_id = entry.source.mongo_id
        try:
            candidate = self._analysis.get_candidate(
                project_id=project_id, candidate_id=candidate_id
            )
        except AnalysisNotFound:
            self._lexical.delete_candidate_record(
                project_id=project_id, candidate_id=candidate_id
            )
            return
        if candidate.status is not AnalysisCandidateStatus.NEEDS_REVIEW:
            self._lexical.delete_candidate_record(
                project_id=project_id, candidate_id=candidate.id
            )
            return
        record = build_candidate_lexical_record(
            candidate, text=candidate_index_text(candidate)
        )
        self._lexical.index_candidate_records((record,))

    def purge_project(self, *, project_id: str) -> None:
        # D8-6c: whole-project purge of the lexical leg. Idempotent — the lexical
        # adapter drops every document of the project and an empty result is
        # success, not a not-found (mirrors the memory leg's
        # MemoryLexicalIndexSyncAdapter.purge_project).
        self._lexical.purge_project(project_id=project_id)


def connect_elasticsearch_candidate_index(
    *, url: str, index_name: str, request_timeout: int = 30
) -> ElasticsearchCandidateIndexAdapter:
    """Lazily build a real ES adapter, creating the nori index if it is absent.

    Mirror of ``connect_elasticsearch_memory_index``; the 30s default covers the
    cold nori index create at startup (the stock 10s client timeout can flake)."""
    from elasticsearch import Elasticsearch  # lazy: optional dependency

    client = Elasticsearch(url, request_timeout=request_timeout)
    if not client.indices.exists(index=index_name):
        client.indices.create(
            index=index_name,
            settings=ELASTICSEARCH_CANDIDATE_SETTINGS,
            mappings=ELASTICSEARCH_CANDIDATE_MAPPINGS,
        )
    return ElasticsearchCandidateIndexAdapter(client, index_name=index_name)
