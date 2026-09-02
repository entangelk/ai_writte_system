"""MongoDB adapter for the candidate identity group store (Slice 0).

``review_queue_mongo_repository``·``scene_notes`` 선례를 따른다: 멱등 쓰기는
unique 축 위의 ``replace_one(..., upsert=True)`` 이고, member/relation 문서는
``_id`` 를 두지 않는다(정체성은 unique 인덱스 축이다). relation은 서비스가
``normalize_relation_pair`` 로 정규화한 뒤에만 들어온다 — 반대 방향 원본은
저장 축에 그대로 두면 unique 인덱스가 두 번째 행을 막는다.
"""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, MongoClient
from pymongo.errors import OperationFailure

from services.application.app.analysis.identity_groups import (
    CandidateIdentityGroup,
    CandidateIdentityGroupMember,
    CandidateIdentityRelation,
    IdentityGroupMemberStatus,
    IdentityGroupStatus,
    IdentityRelationVerdict,
)
from services.application.app.analysis.models import AnalysisCandidateType
from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME


class MongoCandidateIdentityGroupRepositorySetupError(RuntimeError):
    """Raised when MongoDB cannot install required identity-group indexes."""


class MongoCandidateIdentityGroupRepository:
    """``CandidateIdentityGroupRepository`` backed by three Mongo collections."""

    def __init__(
        self,
        client: MongoClient,
        *,
        db_name: str = DEFAULT_DB_NAME,
    ) -> None:
        self._client = client
        db = client[db_name]
        self._groups = db["candidate_identity_groups"]
        self._members = db["candidate_identity_group_members"]
        self._relations = db["candidate_identity_relations"]
        self._ensure_indexes()

    @classmethod
    def from_uri(
        cls, uri: str, *, db_name: str = DEFAULT_DB_NAME
    ) -> "MongoCandidateIdentityGroupRepository":
        return cls(MongoClient(uri), db_name=db_name)

    def _ensure_indexes(self) -> None:
        # 모든 unique/index 축에 project_id·candidate_type 선행(계획 격리 문장).
        try:
            self._groups.create_index(
                [
                    ("project_id", ASCENDING),
                    ("candidate_type", ASCENDING),
                    ("status", ASCENDING),
                ],
                name="candidate_identity_groups_by_project_type_status",
            )
            self._members.create_index(
                [
                    ("project_id", ASCENDING),
                    ("candidate_type", ASCENDING),
                    ("group_id", ASCENDING),
                    ("candidate_id", ASCENDING),
                ],
                name="uniq_candidate_identity_group_member",
                unique=True,
            )
            self._relations.create_index(
                [
                    ("project_id", ASCENDING),
                    ("candidate_type", ASCENDING),
                    ("left_candidate_id", ASCENDING),
                    ("right_candidate_id", ASCENDING),
                ],
                name="uniq_candidate_identity_relation",
                unique=True,
            )
        except OperationFailure as exc:
            raise MongoCandidateIdentityGroupRepositorySetupError(
                "failed to create required identity-group MongoDB indexes"
            ) from exc

    def save_group(self, group: CandidateIdentityGroup) -> None:
        self._groups.replace_one(
            {"_id": group.group_id}, _group_doc(group), upsert=True
        )

    def get_group(self, group_id: str) -> CandidateIdentityGroup | None:
        doc = self._groups.find_one({"_id": group_id})
        return None if doc is None else _to_group(doc)

    def list_groups(
        self, project_id: str
    ) -> tuple[CandidateIdentityGroup, ...]:
        cursor = self._groups.find({"project_id": project_id}).sort(
            [("_id", ASCENDING)]
        )
        return tuple(_to_group(doc) for doc in cursor)

    def get_member(
        self,
        project_id: str,
        candidate_type: AnalysisCandidateType,
        group_id: str,
        candidate_id: str,
    ) -> CandidateIdentityGroupMember | None:
        doc = self._members.find_one(
            _member_filter(
                project_id, candidate_type, group_id, candidate_id
            )
        )
        return None if doc is None else _to_member(doc)

    def upsert_member(self, member: CandidateIdentityGroupMember) -> None:
        self._members.replace_one(
            _member_filter(
                member.project_id,
                member.candidate_type,
                member.group_id,
                member.candidate_id,
            ),
            _member_doc(member),
            upsert=True,
        )

    def list_members(
        self, project_id: str, group_id: str
    ) -> tuple[CandidateIdentityGroupMember, ...]:
        cursor = self._members.find(
            {"project_id": project_id, "group_id": group_id}
        ).sort([("added_at", ASCENDING), ("candidate_id", ASCENDING)])
        return tuple(_to_member(doc) for doc in cursor)

    def upsert_relation(self, relation: CandidateIdentityRelation) -> None:
        self._relations.replace_one(
            _relation_filter(
                relation.project_id,
                relation.candidate_type,
                relation.left_candidate_id,
                relation.right_candidate_id,
            ),
            _relation_doc(relation),
            upsert=True,
        )

    def get_relation(
        self,
        project_id: str,
        candidate_type: AnalysisCandidateType,
        left_candidate_id: str,
        right_candidate_id: str,
    ) -> CandidateIdentityRelation | None:
        doc = self._relations.find_one(
            _relation_filter(
                project_id, candidate_type, left_candidate_id, right_candidate_id
            )
        )
        return None if doc is None else _to_relation(doc)

    def list_relations(
        self, project_id: str
    ) -> tuple[CandidateIdentityRelation, ...]:
        cursor = self._relations.find({"project_id": project_id}).sort(
            [
                ("created_at", ASCENDING),
                ("left_candidate_id", ASCENDING),
            ]
        )
        return tuple(_to_relation(doc) for doc in cursor)

    def purge_project(self, project_id: str) -> None:
        # Slice 0: project 파기가 그룹·멤버·관계 고아를 남기지 않는다.
        self._groups.delete_many({"project_id": project_id})
        self._members.delete_many({"project_id": project_id})
        self._relations.delete_many({"project_id": project_id})


def _member_filter(
    project_id: str,
    candidate_type: AnalysisCandidateType,
    group_id: str,
    candidate_id: str,
) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "candidate_type": str(candidate_type),
        "group_id": group_id,
        "candidate_id": candidate_id,
    }


def _relation_filter(
    project_id: str,
    candidate_type: AnalysisCandidateType,
    left_candidate_id: str,
    right_candidate_id: str,
) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "candidate_type": str(candidate_type),
        "left_candidate_id": left_candidate_id,
        "right_candidate_id": right_candidate_id,
    }


def _group_doc(group: CandidateIdentityGroup) -> dict[str, Any]:
    return {
        "_id": group.group_id,
        "project_id": group.project_id,
        "candidate_type": str(group.candidate_type),
        "status": str(group.status),
        "revision": group.revision,
        "created_at": group.created_at,
        "updated_at": group.updated_at,
    }


def _to_group(doc: dict[str, Any]) -> CandidateIdentityGroup:
    return CandidateIdentityGroup(
        group_id=doc["_id"],
        project_id=doc["project_id"],
        candidate_type=AnalysisCandidateType(doc["candidate_type"]),
        status=IdentityGroupStatus(doc["status"]),
        revision=doc["revision"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


def _member_doc(member: CandidateIdentityGroupMember) -> dict[str, Any]:
    # ``_id`` 를 두지 않는다 — 정체성은 uniq_candidate_identity_group_member
    # 인덱스의 (project_id, candidate_type, group_id, candidate_id)다.
    return {
        "group_id": member.group_id,
        "candidate_id": member.candidate_id,
        "project_id": member.project_id,
        "candidate_type": str(member.candidate_type),
        "member_status": str(member.member_status),
        "added_at": member.added_at,
    }


def _to_member(doc: dict[str, Any]) -> CandidateIdentityGroupMember:
    return CandidateIdentityGroupMember(
        group_id=doc["group_id"],
        candidate_id=doc["candidate_id"],
        project_id=doc["project_id"],
        candidate_type=AnalysisCandidateType(doc["candidate_type"]),
        member_status=IdentityGroupMemberStatus(doc["member_status"]),
        added_at=doc["added_at"],
    )


def _relation_doc(relation: CandidateIdentityRelation) -> dict[str, Any]:
    # ``_id`` 를 두지 않는다 — 정체성은 uniq_candidate_identity_relation
    # 인덱스의 (project_id, candidate_type, left, right)다.
    return {
        "project_id": relation.project_id,
        "candidate_type": str(relation.candidate_type),
        "left_candidate_id": relation.left_candidate_id,
        "right_candidate_id": relation.right_candidate_id,
        "verdict": str(relation.verdict),
        "rationale": relation.rationale,
        "source": relation.source,
        "group_id": relation.group_id,
        "created_at": relation.created_at,
    }


def _to_relation(doc: dict[str, Any]) -> CandidateIdentityRelation:
    return CandidateIdentityRelation(
        project_id=doc["project_id"],
        candidate_type=AnalysisCandidateType(doc["candidate_type"]),
        left_candidate_id=doc["left_candidate_id"],
        right_candidate_id=doc["right_candidate_id"],
        verdict=IdentityRelationVerdict(doc["verdict"]),
        rationale=doc["rationale"],
        source=doc["source"],
        group_id=doc.get("group_id"),
        created_at=doc["created_at"],
    )
