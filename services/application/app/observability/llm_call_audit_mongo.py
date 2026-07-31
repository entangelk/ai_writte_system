"""Mongo repository for the unified per-LLM-call observability audit."""

from pymongo import DESCENDING, MongoClient

from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
from services.application.app.observability.llm_call_audit import StoredLlmCall


class MongoLlmCallAuditRepository:
    def __init__(
        self, client: MongoClient, *, db_name: str = DEFAULT_DB_NAME
    ) -> None:
        self._entries = client[db_name]["llm_call_audits"]
        self._entries.create_index(
            [("project_id", 1), ("created_at", DESCENDING)],
            name="llm_call_audits_by_project_created",
        )
        # D8-5c: the compound index above cannot serve a project-less sort, and
        # an unindexed one is a blocking in-memory sort that fails outright once
        # the collection outgrows Mongo's 32MB sort buffer.
        self._entries.create_index(
            [("created_at", DESCENDING)],
            name="llm_call_audits_by_created",
        )

    @classmethod
    def from_uri(cls, uri: str, *, db_name: str = DEFAULT_DB_NAME):
        return cls(MongoClient(uri), db_name=db_name)

    def add(self, call: StoredLlmCall) -> None:
        # Append-only: insert, never replace (a fresh id per call).
        self._entries.insert_one(_doc(call))

    def list_for_project(
        self, project_id: str
    ) -> tuple[StoredLlmCall, ...]:
        return self._listed({"project_id": project_id})

    def list_all(self) -> tuple[StoredLlmCall, ...]:
        return self._listed({})

    def purge_project(self, project_id: str) -> None:
        # D8-6b-2: project 의 llm call audit 전부 파기(직접 project_id 스코프).
        self._entries.delete_many({"project_id": project_id})

    def _listed(self, query: dict) -> tuple[StoredLlmCall, ...]:
        return tuple(_call(doc) for doc in self._entries.find(query).sort(
            [("created_at", DESCENDING), ("_id", DESCENDING)]
        ))


def _doc(call: StoredLlmCall) -> dict:
    return {
        "_id": call.id,
        "project_id": call.project_id,
        "call_site": call.call_site,
        "correlation_id": call.correlation_id,
        "model": call.model,
        "outcome": call.outcome,
        "decision": call.decision,
        "gate_quality_score": call.gate_quality_score,
        "total_tokens": call.total_tokens,
        "prompt_tokens": call.prompt_tokens,
        "completion_tokens": call.completion_tokens,
        "context_window": call.context_window,
        "max_output_tokens": call.max_output_tokens,
        "latency_ms": call.latency_ms,
        "error_type": call.error_type,
        "created_at": call.created_at,
    }


def _call(doc: dict) -> StoredLlmCall:
    return StoredLlmCall(
        id=doc["_id"],
        project_id=doc["project_id"],
        call_site=doc["call_site"],
        correlation_id=doc.get("correlation_id"),
        model=doc.get("model"),
        outcome=doc["outcome"],
        decision=doc.get("decision"),
        gate_quality_score=doc.get("gate_quality_score"),
        total_tokens=doc.get("total_tokens", 0),
        # 필드가 생기기 전 레코드에는 없다 → None("모른다"). 0으로 채우면 옛 레코드가
        # "입력 0 토큰"으로 집계에 섞인다.
        prompt_tokens=doc.get("prompt_tokens"),
        completion_tokens=doc.get("completion_tokens"),
        context_window=doc.get("context_window"),
        max_output_tokens=doc.get("max_output_tokens"),
        latency_ms=doc.get("latency_ms", 0),
        error_type=doc.get("error_type"),
        created_at=doc["created_at"],
    )
