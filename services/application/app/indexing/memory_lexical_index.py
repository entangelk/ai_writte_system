"""⑤ §5 B / §8: project canonical memories into a lexical (Elasticsearch) index.

Mirror of ``memory_index.py`` (the vector leg) for lexical/keyword retrieval.
Elasticsearch is a lexical/metadata index, never a source of truth: a hit only
yields the MongoDB pointer (``memory_id``), and the caller reloads the canonical
``MemoryEntry`` from the store before grounding (contracts.md §1.3). The adapter
seam (``index``/``delete``/``search``) is duck-typed so the logic is unit-tested
with an in-memory fake and the real Elasticsearch client is optional.

Same canonical-only invariant as the vector leg (2B.4 append-only): the worker
indexes the current canonical version and deletes a superseded one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from services.application.app.indexing.memory_index import derive_memory_index_text
from services.application.app.indexing.models import IndexSyncOutboxEntry
from services.application.app.memory.models import MemoryEntry, MemoryStatus
from services.application.app.memory.service import MemoryNotFound, MemoryService


# Base index name; the real backend prefixes it (see connect_...). Kept distinct
# from the vector collection so the two legs never collide.
MEMORY_LEXICAL_INDEX = "memory_lexical"


@dataclass(frozen=True, slots=True)
class MemoryLexicalRecord:
    """A canonical MemoryEntry projected into the lexical index.

    ``memory_id`` is the version's own id (== the document id, 2B.4 append-only),
    so a superseded version's document is removed when its successor is indexed.
    ``score`` is the lexical relevance of a search hit (0.0 for stored records)."""

    memory_id: str
    project_id: str
    memory_type: str
    version: int
    status: str
    text: str
    score: float = 0.0


def build_memory_lexical_record(memory: MemoryEntry, *, text: str) -> MemoryLexicalRecord:
    return MemoryLexicalRecord(
        memory_id=memory.id,
        project_id=memory.project_id,
        memory_type=memory.memory_type.value,
        version=memory.version,
        status=memory.status.value,
        text=text,
    )


def memory_lexical_text(memory: MemoryEntry) -> str:
    """The lexical index text uses the same deterministic projection as the
    vector index, so both legs rank the same canonical surface."""
    return derive_memory_index_text(memory.memory_type, memory.payload)


class MemoryLexicalIndexAdapter(Protocol):
    def index_memory_records(
        self, records: tuple[MemoryLexicalRecord, ...]
    ) -> int: ...

    def delete_memory_record(self, *, project_id: str, memory_id: str) -> None: ...

    def search(
        self, *, project_id: str, query: str, limit: int
    ) -> tuple[MemoryLexicalRecord, ...]: ...


_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class InMemoryMemoryLexicalIndexAdapter:
    """No-infra lexical backend for unit tests and the deterministic fallback.

    Scores a document by the count of distinct query tokens it contains (a
    token-overlap proxy for BM25). Real Korean morphology (nori) is only in the
    Elasticsearch backend; unit tests drive whitespace-separable text."""

    def __init__(self) -> None:
        self.records: dict[str, MemoryLexicalRecord] = {}

    def index_memory_records(
        self, records: tuple[MemoryLexicalRecord, ...]
    ) -> int:
        for record in records:
            self.records[record.memory_id] = record
        return len(records)

    def delete_memory_record(self, *, project_id: str, memory_id: str) -> None:
        existing = self.records.get(memory_id)
        if existing is not None and existing.project_id == project_id:
            del self.records[memory_id]

    def search(
        self, *, project_id: str, query: str, limit: int
    ) -> tuple[MemoryLexicalRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        query_tokens = set(_tokens(query))
        scored: list[MemoryLexicalRecord] = []
        for record in self.records.values():
            if record.project_id != project_id:
                continue
            overlap = query_tokens & set(_tokens(record.text))
            if not overlap:
                continue
            scored.append(
                MemoryLexicalRecord(
                    memory_id=record.memory_id,
                    project_id=record.project_id,
                    memory_type=record.memory_type,
                    version=record.version,
                    status=record.status,
                    text=record.text,
                    score=float(len(overlap)),
                )
            )
        ranked = sorted(scored, key=lambda r: (-r.score, r.memory_id))
        return tuple(ranked[:limit])


class ElasticsearchClient(Protocol):
    """The narrow slice of the real Elasticsearch (8.x) client the adapter uses,
    so ``ElasticsearchMemoryIndexAdapter`` is unit-tested with a fake. The
    ``query``/``size`` keyword shape matches the 8.x client (``body=`` is removed
    in 8.x)."""

    def index(self, *, index: str, id: str, document: dict[str, Any]) -> Any: ...

    def delete(self, *, index: str, id: str) -> Any: ...

    def search(
        self, *, index: str, query: dict[str, Any], size: int
    ) -> dict[str, Any]: ...


class ElasticsearchMemoryIndexAdapter:
    """Real lexical backend over an Elasticsearch index (nori-analyzed text).

    Documents carry the MongoDB pointer (``memory_id``) and metadata so a hit is
    resolvable back to the canonical store; the ``text`` field is analyzed by the
    index mapping (nori for Korean). The client is injected/duck-typed so this is
    unit-tested with a fake and needs no ``elasticsearch`` package."""

    def __init__(self, client: ElasticsearchClient, *, index_name: str) -> None:
        self._client = client
        self._index = index_name

    def index_memory_records(
        self, records: tuple[MemoryLexicalRecord, ...]
    ) -> int:
        for record in records:
            self._client.index(
                index=self._index,
                id=record.memory_id,
                document={
                    "memory_id": record.memory_id,
                    "mongo_collection": "memory_entries",
                    "mongo_version": record.version,
                    "project_id": record.project_id,
                    "memory_type": record.memory_type,
                    "status": record.status,
                    "text": record.text,
                },
            )
        return len(records)

    def delete_memory_record(self, *, project_id: str, memory_id: str) -> None:
        # Doc id is the memory version id; a project-scoped filter is unnecessary
        # for delete-by-id, but a missing doc must not raise (idempotent drain).
        try:
            self._client.delete(index=self._index, id=memory_id)
        except Exception:
            # elasticsearch raises NotFoundError for an absent doc; the delete is
            # idempotent (the vector leg's delete is likewise order-independent).
            pass

    def search(
        self, *, project_id: str, query: str, limit: int
    ) -> tuple[MemoryLexicalRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        bool_query = {
            "bool": {
                "must": {"match": {"text": query}},
                "filter": [
                    {"term": {"project_id": project_id}},
                    {"term": {"status": "canonical"}},
                ],
            }
        }
        result = self._client.search(
            index=self._index, query=bool_query, size=limit
        )
        hits = result.get("hits", {}).get("hits", [])
        records: list[MemoryLexicalRecord] = []
        for hit in hits:
            source = hit.get("_source", {})
            records.append(
                MemoryLexicalRecord(
                    memory_id=source["memory_id"],
                    project_id=source["project_id"],
                    memory_type=source["memory_type"],
                    version=source["mongo_version"],
                    status=source["status"],
                    text=source["text"],
                    score=float(hit.get("_score") or 0.0),
                )
            )
        return tuple(records)


# Elasticsearch index definition: nori (Korean morphological) analyzer on
# ``text``, keyword filters on the metadata. Split into settings/mappings for the
# 8.x indices.create kwargs. Used by connect_... and the live smoke.
#
# ``number_of_replicas: 0``: the deploy is single-node (discovery.type=single-node),
# so a default replica shard can never be allocated and the cluster would sit
# perpetually yellow once this index exists. The lexical index is derived and
# rebuildable from Mongo (SoT §166), so no replica is needed for durability;
# 0 keeps the single-node cluster steady-state green.
ELASTICSEARCH_MEMORY_SETTINGS: dict[str, Any] = {
    "number_of_replicas": 0,
    "analysis": {"analyzer": {"korean": {"type": "nori"}}},
}
ELASTICSEARCH_MEMORY_MAPPINGS: dict[str, Any] = {
    "properties": {
        "memory_id": {"type": "keyword"},
        "mongo_collection": {"type": "keyword"},
        "mongo_version": {"type": "integer"},
        "project_id": {"type": "keyword"},
        "memory_type": {"type": "keyword"},
        "status": {"type": "keyword"},
        "text": {"type": "text", "analyzer": "korean"},
    }
}


class MemoryLexicalIndexSyncAdapter:
    """Worker-side lexical drain: load the memory a MEMORY_UPSERTED entry points
    at and reindex it into the lexical (ES) index. Mirror of the vector leg's
    ``MemoryIndexSyncAdapter`` — canonical → index, superseded/deleted → delete —
    so both branches are idempotent and order-independent (2B.4)."""

    def __init__(
        self,
        *,
        memory_service: MemoryService,
        lexical_index: MemoryLexicalIndexAdapter,
    ) -> None:
        self._memory = memory_service
        self._lexical = lexical_index

    def index_memory(self, entry: IndexSyncOutboxEntry) -> None:
        project_id = entry.project_id
        memory_id = entry.source.mongo_id
        try:
            memory = self._memory.get_memory(
                project_id=project_id, memory_id=memory_id
            )
        except MemoryNotFound:
            self._lexical.delete_memory_record(
                project_id=project_id, memory_id=memory_id
            )
            return
        if memory.status is not MemoryStatus.CANONICAL:
            self._lexical.delete_memory_record(
                project_id=project_id, memory_id=memory.id
            )
            return
        record = build_memory_lexical_record(memory, text=memory_lexical_text(memory))
        self._lexical.index_memory_records((record,))
        if memory.supersedes is not None:
            self._lexical.delete_memory_record(
                project_id=project_id, memory_id=memory.supersedes
            )


def connect_elasticsearch_memory_index(
    *, url: str, index_name: str, request_timeout: int = 30
) -> ElasticsearchMemoryIndexAdapter:
    """Lazily build a real ES adapter, creating the nori index if it is absent.

    ``elasticsearch`` is imported here so unconfigured environments/tests never
    need the package (mirrors chroma.connect_chroma_collection).

    ``request_timeout`` (default 30s) covers the cold nori index create at
    startup: the client's stock 10s timeout can be exceeded by the ~4s create
    under load, so app/worker boot would otherwise flake (the live smoke was
    hardened the same way)."""
    from elasticsearch import Elasticsearch  # lazy: optional dependency

    client = Elasticsearch(url, request_timeout=request_timeout)
    if not client.indices.exists(index=index_name):
        client.indices.create(
            index=index_name,
            settings=ELASTICSEARCH_MEMORY_SETTINGS,
            mappings=ELASTICSEARCH_MEMORY_MAPPINGS,
        )
    return ElasticsearchMemoryIndexAdapter(client, index_name=index_name)
