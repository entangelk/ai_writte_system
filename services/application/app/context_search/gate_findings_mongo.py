"""Mongo repository for durable Context Gate findings."""

from pymongo import ASCENDING, MongoClient

from services.application.app.context_search.gate_findings import (
    GateFindingStatus, StoredGateFinding,
)
from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME


class MongoGateFindingRepository:
    def __init__(self, client: MongoClient, *, db_name: str = DEFAULT_DB_NAME) -> None:
        self._entries = client[db_name]["gate_findings"]
        self._entries.create_index(
            [("project_id", ASCENDING), ("status", ASCENDING)],
            name="gate_findings_by_project_status",
        )

    @classmethod
    def from_uri(cls, uri: str, *, db_name: str = DEFAULT_DB_NAME):
        return cls(MongoClient(uri), db_name=db_name)

    def upsert(self, finding: StoredGateFinding) -> None:
        self._entries.replace_one({"_id": finding.id}, _doc(finding), upsert=True)

    def get(self, finding_id: str) -> StoredGateFinding | None:
        doc = self._entries.find_one({"_id": finding_id})
        return _entry(doc) if doc else None

    def list_open(self, project_id: str) -> tuple[StoredGateFinding, ...]:
        return tuple(_entry(doc) for doc in self._entries.find({
            "project_id": project_id, "status": GateFindingStatus.OPEN.value,
        }).sort("_id", ASCENDING))

    def purge_project(self, project_id: str) -> None:
        # D8-6b-2: project 의 gate finding 전부 파기(직접 project_id 스코프).
        self._entries.delete_many({"project_id": project_id})


def _doc(value: StoredGateFinding) -> dict:
    return {
        "_id": value.id, "project_id": value.project_id,
        "idempotency_key": value.idempotency_key, "ordinal": value.ordinal,
        "check": value.check, "detail": value.detail,
        "status": value.status.value, "query": value.query,
        "purpose": value.purpose, "needs": list(value.needs),
        "pointer_ids": list(value.pointer_ids),
        "request_fingerprint": value.request_fingerprint,
        "result_fingerprint": value.result_fingerprint,
        "created_at": value.created_at, "terminal_at": value.terminal_at,
    }


def _entry(doc: dict) -> StoredGateFinding:
    return StoredGateFinding(
        id=doc["_id"], project_id=doc["project_id"],
        idempotency_key=doc["idempotency_key"], ordinal=doc["ordinal"],
        check=doc["check"], detail=doc["detail"],
        status=GateFindingStatus(doc["status"]), query=doc["query"],
        purpose=doc["purpose"], needs=tuple(doc["needs"]),
        pointer_ids=tuple(doc.get("pointer_ids", ())),
        request_fingerprint=doc["request_fingerprint"],
        result_fingerprint=doc["result_fingerprint"],
        created_at=doc["created_at"], terminal_at=doc.get("terminal_at"),
    )
