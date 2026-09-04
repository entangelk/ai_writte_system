"""MongoDB adapter for the identity group approval store (Slice 5).

``identity_groups_mongo`` 선례를 따른다: 문서 정체성은 (project, group)이고
멱등 쓰기는 그 축 위의 ``replace_one(..., upsert=True)``다. steps는 문서에
내장 배열로 저장한다(그룹당 1문서 — 서비스 계약 참조).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pymongo import ASCENDING, MongoClient
from pymongo.errors import OperationFailure

from services.application.app.analysis.identity_group_approvals import (
    CandidateIdentityGroupApproval,
    GroupApprovalStep,
    GroupApprovalStepStatus,
)
from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME


def _aware(value: datetime) -> datetime:
    """BSON 날짼 tzinfo 없이 돌아온다 — UTC 로 되돌린다(경계 정규화)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class MongoCandidateIdentityGroupApprovalRepositorySetupError(RuntimeError):
    """Raised when MongoDB cannot install required approval-store indexes."""


class MongoCandidateIdentityGroupApprovalRepository:
    """``CandidateIdentityGroupApprovalRepository`` backed by one collection."""

    def __init__(
        self,
        client: MongoClient,
        *,
        db_name: str = DEFAULT_DB_NAME,
    ) -> None:
        self._client = client
        db = client[db_name]
        self._approvals = db["candidate_identity_group_approvals"]
        self._ensure_indexes()

    @classmethod
    def from_uri(
        cls, uri: str, *, db_name: str = DEFAULT_DB_NAME
    ) -> "MongoCandidateIdentityGroupApprovalRepository":
        return cls(MongoClient(uri), db_name=db_name)

    def _ensure_indexes(self) -> None:
        try:
            self._approvals.create_index(
                [("project_id", ASCENDING)],
                name="candidate_identity_group_approvals_by_project",
            )
        except OperationFailure as exc:
            raise MongoCandidateIdentityGroupApprovalRepositorySetupError(
                "failed to create required approval-store MongoDB indexes"
            ) from exc

    def save(self, approval: CandidateIdentityGroupApproval) -> None:
        self._approvals.replace_one(
            {"_id": approval.group_id}, _approval_doc(approval), upsert=True
        )

    def get(
        self, project_id: str, group_id: str
    ) -> CandidateIdentityGroupApproval | None:
        doc = self._approvals.find_one({"_id": group_id})
        if doc is None or doc["project_id"] != project_id:
            return None
        return _to_approval(doc)

    def purge_project(self, project_id: str) -> None:
        self._approvals.delete_many({"project_id": project_id})


def _step_doc(step: GroupApprovalStep) -> dict[str, Any]:
    return {
        "candidate_id": step.candidate_id,
        "status": str(step.status),
        "action": step.action,
        "memory_id": step.memory_id,
        "version": step.version,
        "error": step.error,
    }


def _to_step(doc: dict[str, Any]) -> GroupApprovalStep:
    return GroupApprovalStep(
        candidate_id=doc["candidate_id"],
        status=GroupApprovalStepStatus(doc["status"]),
        action=doc.get("action"),
        memory_id=doc.get("memory_id"),
        version=doc.get("version"),
        error=doc.get("error"),
    )


def _approval_doc(approval: CandidateIdentityGroupApproval) -> dict[str, Any]:
    return {
        "_id": approval.group_id,
        "project_id": approval.project_id,
        "expected_revision": approval.expected_revision,
        "canonical_memory_id": approval.canonical_memory_id,
        "steps": [_step_doc(step) for step in approval.steps],
        "created_at": approval.created_at,
        "updated_at": approval.updated_at,
    }


def _to_approval(doc: dict[str, Any]) -> CandidateIdentityGroupApproval:
    return CandidateIdentityGroupApproval(
        group_id=doc["_id"],
        project_id=doc["project_id"],
        expected_revision=doc["expected_revision"],
        canonical_memory_id=doc.get("canonical_memory_id"),
        steps=tuple(_to_step(step) for step in doc.get("steps", ())),
        created_at=(
            _aware(doc["created_at"]) if doc.get("created_at") is not None else None
        ),
        updated_at=(
            _aware(doc["updated_at"]) if doc.get("updated_at") is not None else None
        ),
    )
