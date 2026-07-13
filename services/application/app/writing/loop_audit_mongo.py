"""Mongo repository for durable Writing bounded-loop audit runs."""

from pymongo import DESCENDING, MongoClient

from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
from services.application.app.writing.loop_audit import (
    StoredLoopStage,
    StoredWritingLoopRun,
)


class MongoWritingLoopAuditRepository:
    def __init__(
        self, client: MongoClient, *, db_name: str = DEFAULT_DB_NAME
    ) -> None:
        self._entries = client[db_name]["writing_loop_audits"]
        self._entries.create_index(
            [("project_id", 1), ("created_at", DESCENDING)],
            name="writing_loop_audits_by_project_created",
        )

    @classmethod
    def from_uri(cls, uri: str, *, db_name: str = DEFAULT_DB_NAME):
        return cls(MongoClient(uri), db_name=db_name)

    def add(self, run: StoredWritingLoopRun) -> None:
        # Append-only: insert, never replace. A retry produces a new id.
        self._entries.insert_one(_doc(run))

    def get(self, run_id: str) -> StoredWritingLoopRun | None:
        doc = self._entries.find_one({"_id": run_id})
        return _run(doc) if doc else None

    def list_for_project(
        self, project_id: str
    ) -> tuple[StoredWritingLoopRun, ...]:
        return tuple(_run(doc) for doc in self._entries.find(
            {"project_id": project_id},
        ).sort([("created_at", DESCENDING), ("_id", DESCENDING)]))


def _doc(run: StoredWritingLoopRun) -> dict:
    return {
        "_id": run.id, "project_id": run.project_id,
        "request_id": run.request_id, "loop_status": run.loop_status,
        "revision_rounds": run.revision_rounds,
        "retrieval_rounds": run.retrieval_rounds,
        "gate_evaluations": run.gate_evaluations,
        "error_type": run.error_type,
        "trigger_finding_fingerprint": run.trigger_finding_fingerprint,
        "initial_candidate_hash": run.initial_candidate_hash,
        "final_candidate_hash": run.final_candidate_hash,
        "final_candidate_text": run.final_candidate_text,
        "final_gate_decision": run.final_gate_decision,
        "final_gate_finding_fingerprints": list(
            run.final_gate_finding_fingerprints
        ),
        "stages": [_stage_doc(stage) for stage in run.stages],
        "created_at": run.created_at,
    }


def _stage_doc(stage: StoredLoopStage) -> dict:
    return {
        "stage": stage.stage, "ordinal": stage.ordinal,
        "status": stage.status, "candidate_hash": stage.candidate_hash,
        "finding_fingerprint": stage.finding_fingerprint,
        "pointer_ids": list(stage.pointer_ids),
    }


def _run(doc: dict) -> StoredWritingLoopRun:
    return StoredWritingLoopRun(
        id=doc["_id"], project_id=doc["project_id"],
        request_id=doc["request_id"], loop_status=doc["loop_status"],
        revision_rounds=doc["revision_rounds"],
        retrieval_rounds=doc["retrieval_rounds"],
        gate_evaluations=doc["gate_evaluations"],
        error_type=doc.get("error_type"),
        trigger_finding_fingerprint=doc["trigger_finding_fingerprint"],
        initial_candidate_hash=doc["initial_candidate_hash"],
        final_candidate_hash=doc["final_candidate_hash"],
        final_candidate_text=doc["final_candidate_text"],
        final_gate_decision=doc.get("final_gate_decision"),
        final_gate_finding_fingerprints=tuple(
            doc.get("final_gate_finding_fingerprints", ())
        ),
        stages=tuple(_stage(stage) for stage in doc.get("stages", ())),
        created_at=doc["created_at"],
    )


def _stage(doc: dict) -> StoredLoopStage:
    return StoredLoopStage(
        stage=doc["stage"], ordinal=doc["ordinal"], status=doc["status"],
        candidate_hash=doc.get("candidate_hash"),
        finding_fingerprint=doc.get("finding_fingerprint"),
        pointer_ids=tuple(doc.get("pointer_ids", ())),
    )
