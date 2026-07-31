"""MongoDB adapter for the review queue store (2B.4 follow-up).

Mirrors ``memory/mongo_repository.py``: a ``review_queue`` collection keyed by
the deterministic entry id so an apply replay upserts (D3) instead of
duplicating. ``status`` is a single ``open`` value in this slice.
"""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, MongoClient
from pymongo.errors import OperationFailure

from services.application.app.analysis.compare import CompareAction
from services.application.app.analysis.models import AnalysisCandidateType
from services.application.app.analysis.review_queue import (
    ReviewQueueEntry,
    ReviewQueueStatus,
)
from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME


class MongoReviewQueueRepositorySetupError(RuntimeError):
    """Raised when MongoDB cannot install required review-queue indexes."""


class MongoReviewQueueRepository:
    """``ReviewQueueRepository`` backed by a ``review_queue`` collection."""

    def __init__(
        self,
        client: MongoClient,
        *,
        db_name: str = DEFAULT_DB_NAME,
    ) -> None:
        self._client = client
        self._db = client[db_name]
        self._entries = self._db["review_queue"]
        self.ensure_indexes()

    @classmethod
    def from_uri(
        cls, uri: str, *, db_name: str = DEFAULT_DB_NAME
    ) -> "MongoReviewQueueRepository":
        return cls(MongoClient(uri), db_name=db_name)

    def ensure_indexes(self) -> None:
        try:
            self._entries.create_index(
                [("project_id", ASCENDING), ("status", ASCENDING)],
                name="review_queue_by_project_status",
            )
        except OperationFailure as exc:
            raise MongoReviewQueueRepositorySetupError(
                "failed to create required review-queue MongoDB indexes"
            ) from exc

    def upsert_entry(self, entry: ReviewQueueEntry) -> None:
        self._entries.replace_one(
            {"_id": entry.id}, _entry_doc(entry), upsert=True
        )

    def list_open_for_project(
        self, project_id: str
    ) -> tuple[ReviewQueueEntry, ...]:
        cursor = self._entries.find(
            {"project_id": project_id, "status": ReviewQueueStatus.OPEN.value}
        ).sort("_id", ASCENDING)
        return tuple(_to_entry(doc) for doc in cursor)

    def list_open_for_candidate(
        self, project_id: str, candidate_id: str
    ) -> tuple[ReviewQueueEntry, ...]:
        cursor = self._entries.find(
            {
                "project_id": project_id,
                "candidate_id": candidate_id,
                "status": ReviewQueueStatus.OPEN.value,
            }
        ).sort("_id", ASCENDING)
        return tuple(_to_entry(doc) for doc in cursor)

    def get_entry(self, entry_id: str) -> ReviewQueueEntry | None:
        doc = self._entries.find_one({"_id": entry_id})
        return _to_entry(doc) if doc is not None else None

    def purge_project(self, project_id: str) -> None:
        # D8-6b-2: project 의 review queue 전부 파기(직접 project_id 스코프).
        self._entries.delete_many({"project_id": project_id})


def _entry_doc(entry: ReviewQueueEntry) -> dict[str, Any]:
    return {
        "_id": entry.id,
        "project_id": entry.project_id,
        "job_id": entry.job_id,
        "candidate_id": entry.candidate_id,
        "candidate_type": str(entry.candidate_type),
        "action": str(entry.action),
        "matched_memory_id": entry.matched_memory_id,
        "rationale": entry.rationale,
        "status": str(entry.status),
        "resolution_action": entry.resolution_action,
        "resolution_memory_id": entry.resolution_memory_id,
    }


def _to_entry(doc: dict[str, Any]) -> ReviewQueueEntry:
    return ReviewQueueEntry(
        id=doc["_id"],
        project_id=doc["project_id"],
        job_id=doc["job_id"],
        candidate_id=doc["candidate_id"],
        candidate_type=AnalysisCandidateType(doc["candidate_type"]),
        action=CompareAction(doc["action"]),
        matched_memory_id=doc.get("matched_memory_id"),
        rationale=doc["rationale"],
        status=ReviewQueueStatus(doc["status"]),
        resolution_action=doc.get("resolution_action"),
        resolution_memory_id=doc.get("resolution_memory_id"),
    )
