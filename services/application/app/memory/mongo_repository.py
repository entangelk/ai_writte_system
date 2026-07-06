"""MongoDB adapter implementing the Phase 2B.1 memory repository contract."""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, OperationFailure

from services.application.app.analysis.models import (
    AnalysisCandidateType,
    AnalysisProvenance,
    immutable_payload,
)
from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
from services.application.app.memory.models import (
    MemoryEntry,
    MemoryStatus,
    PromotionMode,
)
from services.application.app.memory.repository import DuplicatePromotionRequest
from services.application.app.memory.scope import MemoryScope


class MongoMemoryRepositorySetupError(RuntimeError):
    """Raised when MongoDB cannot install required memory indexes."""


class MongoMemoryRepository:
    """``MemoryRepository`` backed by a MongoDB ``memory_entries`` collection."""

    def __init__(
        self,
        client: MongoClient,
        *,
        db_name: str = DEFAULT_DB_NAME,
    ) -> None:
        self._client = client
        self._db = client[db_name]
        self._memories = self._db["memory_entries"]
        self.ensure_indexes()

    @classmethod
    def from_uri(
        cls, uri: str, *, db_name: str = DEFAULT_DB_NAME
    ) -> "MongoMemoryRepository":
        return cls(MongoClient(uri), db_name=db_name)

    def ensure_indexes(self) -> None:
        try:
            self._memories.create_index(
                [
                    ("project_id", ASCENDING),
                    ("source_candidate_id", ASCENDING),
                ],
                unique=True,
                name="uniq_memory_candidate_promotion",
            )
            self._memories.create_index(
                [("project_id", ASCENDING)],
                name="memory_entries_by_project",
            )
        except OperationFailure as exc:
            raise MongoMemoryRepositorySetupError(
                "failed to create required memory MongoDB indexes"
            ) from exc

    def next_memory_id(self) -> str:
        return str(ObjectId())

    def get_memory(self, memory_id: str) -> MemoryEntry | None:
        doc = self._memories.find_one({"_id": memory_id})
        return _to_memory(doc) if doc else None

    def find_memory_by_candidate(
        self, project_id: str, source_candidate_id: str
    ) -> str | None:
        doc = self._memories.find_one(
            {
                "project_id": project_id,
                "source_candidate_id": source_candidate_id,
            },
            {"_id": 1},
        )
        return doc["_id"] if doc else None

    def put_memory(self, entry: MemoryEntry) -> None:
        try:
            self._memories.insert_one(_memory_doc(entry))
        except DuplicateKeyError as exc:
            raise DuplicatePromotionRequest(
                "candidate already promoted to a memory entry"
            ) from exc

    def list_memories_for_project(
        self, project_id: str
    ) -> tuple[MemoryEntry, ...]:
        cursor = self._memories.find({"project_id": project_id}).sort(
            "_id", ASCENDING
        )
        return tuple(_to_memory(doc) for doc in cursor)


def _memory_doc(entry: MemoryEntry) -> dict[str, Any]:
    return {
        "_id": entry.id,
        "project_id": entry.project_id,
        "memory_type": str(entry.memory_type),
        "status": str(entry.status),
        "provenance": str(entry.provenance),
        "confidence": entry.confidence,
        "source_ref_ids": list(entry.source_ref_ids),
        "payload": dict(entry.payload),
        "version": entry.version,
        "analysis_job_id": entry.analysis_job_id,
        "source_candidate_id": entry.source_candidate_id,
        "promotion_mode": str(entry.promotion_mode),
        "applied_threshold": entry.applied_threshold,
        "scope": (
            None
            if entry.scope is None
            else {
                "scope_type": entry.scope.scope_type,
                "scope_id": entry.scope.scope_id,
            }
        ),
    }


def _to_memory(doc: dict[str, Any]) -> MemoryEntry:
    scope_doc = doc.get("scope")
    return MemoryEntry(
        id=doc["_id"],
        project_id=doc["project_id"],
        memory_type=AnalysisCandidateType(doc["memory_type"]),
        status=MemoryStatus(doc["status"]),
        provenance=AnalysisProvenance(doc["provenance"]),
        confidence=doc["confidence"],
        source_ref_ids=tuple(doc["source_ref_ids"]),
        payload=immutable_payload(doc["payload"]),
        version=doc["version"],
        analysis_job_id=doc["analysis_job_id"],
        source_candidate_id=doc["source_candidate_id"],
        promotion_mode=PromotionMode(doc["promotion_mode"]),
        applied_threshold=doc.get("applied_threshold"),
        scope=(
            None
            if scope_doc is None
            else MemoryScope(
                scope_type=scope_doc["scope_type"],
                scope_id=scope_doc["scope_id"],
            )
        ),
    )
