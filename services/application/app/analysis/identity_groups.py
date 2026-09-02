"""미승인 후보 정체성 그룹 Slice 0 — 저장 모델과 수명.

계획: ``docs/plans/pending-candidate-identity-grouping-implementation-phases.md``
Slice 0(오너 C 채택, 2026-09-02). 서로 다른 분석 job이 만든 ``needs_review`` 후보가
같은 인물·사건을 가리킬 때 이를 하나의 검토 그룹으로 묶는 **저장 단위**만 만든다.
HTTP·runner 배선·LLM judge·Review Inbox UI는 이 Slice 밖이다.

세 저장 단위(모든 unique/index 축에 ``project_id``·``candidate_type`` 포함):

- ``candidate_identity_groups`` — 그룹 본체. ``status``는 최소
  ``open|contradicted|closed``. ``contradicted``는 같은 group 안에서 ``same``
  추이와 상충하는 ``different`` relation이 관측된 상태를 저장하는 자리일 뿐 —
  자동 분할·자동 병합은 하지 않는다(계획 Slice 0). ``revision``은 승격 액션의
  낙관적 동시성 축(Slice 5의 revision mismatch 409)으로, 상태 변경마다 1 오른다.
- ``candidate_identity_group_members`` — 원 후보를 **소유하지 않고 참조만** 한다.
  같은 (project, type, group, candidate) 재추가는 멱등(한 행, ``added_at`` 불변).
- ``candidate_identity_relations`` — 후보↔후보 판정. pair는 ``normalize_relation_pair``
  로 좌우를 정렬해 저장하므로 ``(A,B)``와 ``(B,A)``는 같은 행이고, 재기록은 upsert
  (마지막 판정 승리 — 판정 재사용 정책은 Slice 1). ``candidate_type`` 필드는 오너
  결정(2026-09-02)으로 relation unique 축에도 들어간다.

project purge는 세 컬렉션을 모두 지운다(고아 없음). 후보 문서를 지우는 경로는
현재 project purge뿐이라 그 한 벌로 "candidate purge/project purge 고아 없음"이
닫힌다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Callable, Protocol
from uuid import uuid4

from services.application.app.analysis.models import AnalysisCandidateType


class IdentityGroupStatus(StrEnum):
    """그룹 상태. Slice 0 은 상태를 저장할 자리만 만든다(자동 분할·병합 없음)."""

    OPEN = "open"
    CONTRADICTED = "contradicted"
    CLOSED = "closed"


class IdentityRelationVerdict(StrEnum):
    SAME = "same"
    DIFFERENT = "different"
    UNCERTAIN = "uncertain"


class IdentityGroupMemberStatus(StrEnum):
    """Slice 0 유일값은 ``active``. Slice 4·5의 terminal/skip 의미가 확장한다."""

    ACTIVE = "active"


@dataclass(frozen=True, slots=True)
class CandidateIdentityGroup:
    group_id: str
    project_id: str
    candidate_type: AnalysisCandidateType
    status: IdentityGroupStatus
    revision: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CandidateIdentityGroupMember:
    group_id: str
    candidate_id: str
    project_id: str
    candidate_type: AnalysisCandidateType
    member_status: IdentityGroupMemberStatus
    added_at: datetime


@dataclass(frozen=True, slots=True)
class CandidateIdentityRelation:
    """``left_candidate_id`` < ``right_candidate_id`` 정규형으로만 저장한다."""

    project_id: str
    candidate_type: AnalysisCandidateType
    left_candidate_id: str
    right_candidate_id: str
    verdict: IdentityRelationVerdict
    rationale: str
    source: str
    group_id: str | None
    created_at: datetime


def normalize_relation_pair(
    left_candidate_id: str, right_candidate_id: str
) -> tuple[str, str]:
    """pair의 정규형 — ``(A,B)``와 ``(B,A)``가 같은 행에 앉는 축이다.

    같은 후보끼리의 pair(``A == B``)는 판정 대상이 아니므로 거절한다.
    """
    if left_candidate_id == right_candidate_id:
        raise ValueError(
            "identity relation pair must reference two distinct candidates"
        )
    if left_candidate_id < right_candidate_id:
        return left_candidate_id, right_candidate_id
    return right_candidate_id, left_candidate_id


class CandidateIdentityGroupRepository(Protocol):
    """세 컬렉션의 저장 계약. relation은 서비스가 정규화한 뒤에만 들어온다."""

    def save_group(self, group: CandidateIdentityGroup) -> None: ...

    def get_group(self, group_id: str) -> CandidateIdentityGroup | None: ...

    def list_groups(self, project_id: str) -> tuple[CandidateIdentityGroup, ...]: ...

    def get_member(
        self,
        project_id: str,
        candidate_type: AnalysisCandidateType,
        group_id: str,
        candidate_id: str,
    ) -> CandidateIdentityGroupMember | None: ...

    def upsert_member(self, member: CandidateIdentityGroupMember) -> None: ...

    def list_members(
        self, project_id: str, group_id: str
    ) -> tuple[CandidateIdentityGroupMember, ...]: ...

    def upsert_relation(self, relation: CandidateIdentityRelation) -> None: ...

    def get_relation(
        self,
        project_id: str,
        candidate_type: AnalysisCandidateType,
        left_candidate_id: str,
        right_candidate_id: str,
    ) -> CandidateIdentityRelation | None: ...

    def list_relations(
        self, project_id: str
    ) -> tuple[CandidateIdentityRelation, ...]: ...

    def purge_project(self, project_id: str) -> None: ...


class InMemoryCandidateIdentityGroupRepository:
    """비내구 저장소 — 표준 suite 와 no-Mongo 경로."""

    def __init__(self) -> None:
        self._groups: dict[str, CandidateIdentityGroup] = {}
        self._members: dict[
            tuple[str, str, str, str], CandidateIdentityGroupMember
        ] = {}
        self._relations: dict[
            tuple[str, str, str, str], CandidateIdentityRelation
        ] = {}

    def save_group(self, group: CandidateIdentityGroup) -> None:
        self._groups[group.group_id] = group

    def get_group(self, group_id: str) -> CandidateIdentityGroup | None:
        return self._groups.get(group_id)

    def list_groups(
        self, project_id: str
    ) -> tuple[CandidateIdentityGroup, ...]:
        return tuple(
            sorted(
                (
                    group
                    for group in self._groups.values()
                    if group.project_id == project_id
                ),
                key=lambda group: group.group_id,
            )
        )

    def get_member(
        self,
        project_id: str,
        candidate_type: AnalysisCandidateType,
        group_id: str,
        candidate_id: str,
    ) -> CandidateIdentityGroupMember | None:
        return self._members.get(
            (project_id, str(candidate_type), group_id, candidate_id)
        )

    def upsert_member(self, member: CandidateIdentityGroupMember) -> None:
        self._members[
            (
                member.project_id,
                str(member.candidate_type),
                member.group_id,
                member.candidate_id,
            )
        ] = member

    def list_members(
        self, project_id: str, group_id: str
    ) -> tuple[CandidateIdentityGroupMember, ...]:
        return tuple(
            sorted(
                (
                    member
                    for member in self._members.values()
                    if member.project_id == project_id
                    and member.group_id == group_id
                ),
                key=lambda member: (member.added_at, member.candidate_id),
            )
        )

    def upsert_relation(self, relation: CandidateIdentityRelation) -> None:
        self._relations[
            (
                relation.project_id,
                str(relation.candidate_type),
                relation.left_candidate_id,
                relation.right_candidate_id,
            )
        ] = relation

    def get_relation(
        self,
        project_id: str,
        candidate_type: AnalysisCandidateType,
        left_candidate_id: str,
        right_candidate_id: str,
    ) -> CandidateIdentityRelation | None:
        return self._relations.get(
            (
                project_id,
                str(candidate_type),
                left_candidate_id,
                right_candidate_id,
            )
        )

    def list_relations(
        self, project_id: str
    ) -> tuple[CandidateIdentityRelation, ...]:
        return tuple(
            sorted(
                (
                    relation
                    for relation in self._relations.values()
                    if relation.project_id == project_id
                ),
                key=lambda relation: (
                    relation.created_at,
                    relation.left_candidate_id,
                ),
            )
        )

    def purge_project(self, project_id: str) -> None:
        # Slice 0: project 파기가 그룹·멤버·관계 고아를 남기지 않는다.
        self._groups = {
            gid: group
            for gid, group in self._groups.items()
            if group.project_id != project_id
        }
        self._members = {
            key: member
            for key, member in self._members.items()
            if member.project_id != project_id
        }
        self._relations = {
            key: relation
            for key, relation in self._relations.items()
            if relation.project_id != project_id
        }


class CandidateIdentityGroupError(RuntimeError):
    pass


class CandidateIdentityGroupNotFoundError(CandidateIdentityGroupError):
    pass


class CandidateIdentityGroupTypeError(CandidateIdentityGroupError):
    pass


class CandidateIdentityGroupService:
    """Slice 0 의 public service — 다음 Slice 는 이 면만 사용한다(계획 인계 조항)."""

    def __init__(
        self,
        repository: CandidateIdentityGroupRepository,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repo = repository
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: "cig:" + uuid4().hex)

    def purge_project(self, *, project_id: str) -> None:
        # project 파기의 identity-group 다리. execute_project_purge 가 호출한다.
        self._repo.purge_project(project_id)

    def create_group(
        self, project_id: str, candidate_type: AnalysisCandidateType
    ) -> CandidateIdentityGroup:
        now = self._clock()
        group = CandidateIdentityGroup(
            group_id=self._id_factory(),
            project_id=project_id,
            candidate_type=candidate_type,
            status=IdentityGroupStatus.OPEN,
            revision=0,
            created_at=now,
            updated_at=now,
        )
        self._repo.save_group(group)
        return group

    def get_group(
        self, project_id: str, group_id: str
    ) -> CandidateIdentityGroup:
        group = self._repo.get_group(group_id)
        if group is None or group.project_id != project_id:
            raise CandidateIdentityGroupNotFoundError(
                "candidate identity group not found"
            )
        return group

    def list_groups(
        self, project_id: str
    ) -> tuple[CandidateIdentityGroup, ...]:
        return self._repo.list_groups(project_id)

    def set_group_status(
        self, project_id: str, group_id: str, status: IdentityGroupStatus
    ) -> CandidateIdentityGroup:
        group = self.get_group(project_id, group_id)
        updated = CandidateIdentityGroup(
            group_id=group.group_id,
            project_id=group.project_id,
            candidate_type=group.candidate_type,
            status=status,
            revision=group.revision + 1,
            created_at=group.created_at,
            updated_at=self._clock(),
        )
        self._repo.save_group(updated)
        return updated

    def add_member(
        self,
        project_id: str,
        group_id: str,
        candidate_id: str,
        candidate_type: AnalysisCandidateType,
    ) -> CandidateIdentityGroupMember:
        group = self.get_group(project_id, group_id)
        if group.candidate_type != candidate_type:
            # 격리 축 — 다른 type 의 후보는 그룹에 들어올 수 없다.
            raise CandidateIdentityGroupTypeError(
                "candidate type does not match the identity group"
            )
        existing = self._repo.get_member(
            project_id, candidate_type, group_id, candidate_id
        )
        if existing is not None:
            # 멱등 — 재추가는 added_at 을 바꾸지 않는다.
            return existing
        member = CandidateIdentityGroupMember(
            group_id=group_id,
            candidate_id=candidate_id,
            project_id=project_id,
            candidate_type=candidate_type,
            member_status=IdentityGroupMemberStatus.ACTIVE,
            added_at=self._clock(),
        )
        self._repo.upsert_member(member)
        return member

    def list_members(
        self, project_id: str, group_id: str
    ) -> tuple[CandidateIdentityGroupMember, ...]:
        self.get_group(project_id, group_id)
        return self._repo.list_members(project_id, group_id)

    def record_relation(
        self,
        project_id: str,
        candidate_type: AnalysisCandidateType,
        left_candidate_id: str,
        right_candidate_id: str,
        *,
        verdict: IdentityRelationVerdict,
        rationale: str,
        source: str,
        group_id: str | None = None,
    ) -> CandidateIdentityRelation:
        left, right = normalize_relation_pair(
            left_candidate_id, right_candidate_id
        )
        existing = self._repo.get_relation(
            project_id, candidate_type, left, right
        )
        relation = CandidateIdentityRelation(
            project_id=project_id,
            candidate_type=candidate_type,
            left_candidate_id=left,
            right_candidate_id=right,
            verdict=verdict,
            rationale=rationale,
            source=source,
            group_id=group_id,
            # 재기록은 새 행이 아니라 같은 행 — created_at 도 첫 판정을 유지한다.
            created_at=(
                existing.created_at if existing is not None else self._clock()
            ),
        )
        self._repo.upsert_relation(relation)
        return relation

    def get_relation(
        self,
        project_id: str,
        candidate_type: AnalysisCandidateType,
        left_candidate_id: str,
        right_candidate_id: str,
    ) -> CandidateIdentityRelation | None:
        left, right = normalize_relation_pair(
            left_candidate_id, right_candidate_id
        )
        return self._repo.get_relation(project_id, candidate_type, left, right)

    def list_relations(
        self, project_id: str
    ) -> tuple[CandidateIdentityRelation, ...]:
        return self._repo.list_relations(project_id)
