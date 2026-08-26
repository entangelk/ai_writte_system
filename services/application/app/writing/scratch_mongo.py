"""Mongo repository for the unaccepted Writing candidate recovery store.

Backs ``writing_drafts_scratch`` (brief D2=A). Core-SOT-external: this never
touches version/snapshot collections. Mutable (upsert-per-generate, delete on
accept/discard), unlike the append-only ``writing_loop_audits``.
"""

from pymongo import DESCENDING, MongoClient

from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
from services.application.app.writing.scratch import ScratchCandidate


class MongoWritingScratchRepository:
    def __init__(
        self, client: MongoClient, *, db_name: str = DEFAULT_DB_NAME
    ) -> None:
        self._entries = client[db_name]["writing_drafts_scratch"]
        self._entries.create_index(
            [("project_id", 1), ("draft_id", 1), ("created_at", DESCENDING)],
            name="writing_drafts_scratch_by_draft_created",
        )

    @classmethod
    def from_uri(cls, uri: str, *, db_name: str = DEFAULT_DB_NAME):
        return cls(MongoClient(uri), db_name=db_name)

    def add(self, entry: ScratchCandidate) -> None:
        self._entries.insert_one(_doc(entry))

    def list_for_draft(
        self, project_id: str, draft_id: str
    ) -> tuple[ScratchCandidate, ...]:
        return tuple(_entry(doc) for doc in self._entries.find(
            {"project_id": project_id, "draft_id": draft_id},
        ).sort([("created_at", DESCENDING), ("_id", DESCENDING)]))

    def delete_for_draft(self, project_id: str, draft_id: str) -> int:
        result = self._entries.delete_many(
            {"project_id": project_id, "draft_id": draft_id}
        )
        return result.deleted_count

    def delete_for_request(
        self, project_id: str, draft_id: str, request_id: str
    ) -> int:
        result = self._entries.delete_many(
            {
                "project_id": project_id,
                "draft_id": draft_id,
                "request_id": request_id,
            }
        )
        return result.deleted_count

    def delete_one(self, project_id: str, scratch_id: str) -> bool:
        # Per-item discard — the project scope in the filter is the isolation:
        # another project's id matches nothing and reads as not-found.
        result = self._entries.delete_many(
            {"project_id": project_id, "_id": scratch_id}
        )
        return result.deleted_count == 1

    def delete_ids(self, ids: tuple[str, ...]) -> None:
        if not ids:
            return
        self._entries.delete_many({"_id": {"$in": list(ids)}})

    def purge_project(self, project_id: str) -> None:
        # D8-6b-2: project 의 scratch 전부 파기(직접 project_id 스코프).
        self._entries.delete_many({"project_id": project_id})


def _doc(entry: ScratchCandidate) -> dict:
    return {
        "_id": entry.id,
        "project_id": entry.project_id,
        "draft_id": entry.draft_id,
        "request_id": entry.request_id,
        "task_type": entry.task_type,
        "output_type": entry.output_type,
        "instruction": entry.instruction,
        "candidate_text": entry.candidate_text,
        "created_at": entry.created_at,
        "intent": entry.intent,
        "version_id": entry.version_id,
    }


def _entry(doc: dict) -> ScratchCandidate:
    return ScratchCandidate(
        id=doc["_id"],
        project_id=doc["project_id"],
        draft_id=doc["draft_id"],
        request_id=doc["request_id"],
        task_type=doc["task_type"],
        output_type=doc["output_type"],
        instruction=doc["instruction"],
        candidate_text=doc["candidate_text"],
        created_at=doc["created_at"],
        intent=doc.get("intent"),
        version_id=doc.get("version_id"),
    )
