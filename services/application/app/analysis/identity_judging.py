"""미승인 후보 정체성 그룹 Slice 1 — shortlist와 판정 서비스.

계획: ``docs/plans/pending-candidate-identity-grouping-implementation-phases.md``
Slice 1(오너 C 채택, 2026-09-02). 후보 하나를 기준으로 같은 project/type의
``needs_review`` 후보를 shortlist하고, 주입된 identity judge seam으로
``same|different|uncertain`` relation을 저장한다. **runner·HTTP 배선은 이 Slice
밖이다**(Slice 2). 저장은 Slice 0 의 public service
(``CandidateIdentityGroupService``)만 사용한다 — 컬렉션을 직접 읽지 않는다.

이 Slice가 확정하는 계약 리터럴:

- **판정 재사용**(Slice 0 이 이 Slice로 넘긴 정책): pair에 저장된 relation이
  있으면 judge를 다시 부르지 않고 그 판정을 재사용한다. 첫 판정이 승리하되
  재실행의 효과 적용(그룹 연결·모순 표시)은 멱등하게 다시 일어난다 — 중간에
  죽은 실행이 남긴 빈자리를 스스로 메운다.
- **shortlist**: character는 정규화 이름(``normalize_name``) 일치 신호가 전부다
  (후보 payload에는 별칭 필드가 없다 — 2B.7 alias matcher는 canonical 축이라 이
  경로에 쓰지 않는다). event/open-question은 주입된 retriever가 고르고,
  **retriever가 없으면 shortlist가 비는 no-op**다(fail-closed 아님).
- **judge 미구성**: 판정이 필요한 pair가 있을 때 명시 오류. shortlist가 비면
  judge 없이도 no-op로 끝난다.
- **``same``만 group member로 연결**되고 ``uncertain``은 relation만 남긴다.
  새 ``different`` relation이 기존 ``same`` 연결 성분과 충돌하면 relation은
  보존하고 group ``status``를 ``contradicted``로 올린다. 모순 감지는 **도착
  순서와 무관**하다 — ``same``이 기존 ``different``와 충돌하는 삼각형을 닫아도
  같은 표시가 일어난다(계획 검증 문장 "A=B·B=C·A≠C"는 순서를 못 박지 않는다).
  표시는 정확히 한 번의 상태 전환(``open``→``contradicted``)이다.
- **그룹 합류**: ``same`` 판정의 양 후보가 그룹에 없으면 새로 만들고, 한쪽만
  있으면 그 그룹에 합류한다. **서로 다른 두 그룹을 잇는 ``same``은 둘을 하나로
  합친다**(C 브리프 "``same``을 하나의 review group으로"의 직접 귀결) — 오래된
  그룹(created_at, 동률 시 group_id)이 살아남고 흡수된 그룹은 ``closed``가
  된다. 저장소에 member 삭제면이 없어 흡수된 그룹의 member 행은 남지만
  ``closed`` 그룹은 이후 소속 판정에서 제외되므로 두 그룹이 다시 갈라지지
  않는다.
- relation의 ``source`` 리터럴은 ``identity_judge``다.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Awaitable, Protocol

from services.application.app.analysis.identity_groups import (
    CandidateIdentityGroup,
    CandidateIdentityGroupService,
    IdentityGroupStatus,
    IdentityRelationVerdict,
    normalize_relation_pair,
)
from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
)
from services.application.app.analysis.repository import AnalysisRepository
from services.application.app.memory.scope import normalize_name


class CandidateIdentityJudgingError(RuntimeError):
    pass


class CandidateNotFoundForIdentityJudging(CandidateIdentityJudgingError):
    pass


class CandidateNotNeedsReviewError(CandidateIdentityJudgingError):
    pass


class IdentityJudgeNotConfigured(CandidateIdentityJudgingError):
    """판정이 필요한 pair가 있는데 judge가 주입되지 않았다."""


class InvalidIdentityJudgement(CandidateIdentityJudgingError):
    """judge가 verdict 축 밖의 값을 돌려줬다(parse error 축의 seam 대응)."""


@dataclass(frozen=True, slots=True)
class IdentityJudgement:
    verdict: IdentityRelationVerdict
    rationale: str


class IdentityJudge(Protocol):
    """후보↔후보 동일성 판정 seam — sync(fake)·async(gateway judge) 겸용."""

    def judge(
        self, *, left: AnalysisCandidate, right: AnalysisCandidate
    ) -> IdentityJudgement | Awaitable[IdentityJudgement]: ...


class CandidateShortlistRetriever(Protocol):
    """event/open_question 축의 선택적 retriever.

    pool은 서비스가 거른 같은 project/type의 ``needs_review`` 후보(자기 자신
    제외)다. 반환값은 pool 안의 후보만 살리고 나머지는 버린다. 주입되지 않으면
    이 타입의 shortlist는 비게 된다(no-op).
    """

    def shortlist(
        self,
        *,
        project_id: str,
        candidate: AnalysisCandidate,
        pool: tuple[AnalysisCandidate, ...],
    ) -> tuple[AnalysisCandidate, ...]: ...


@dataclass(frozen=True, slots=True)
class CandidateIdentityJudgingResult:
    focal_candidate_id: str
    candidate_type: AnalysisCandidateType
    shortlisted_candidate_ids: tuple[str, ...]
    judged_pair_ids: tuple[tuple[str, str], ...]
    reused_pair_ids: tuple[tuple[str, str], ...]
    group_id: str | None


class CandidateIdentityJudgingService:
    def __init__(
        self,
        *,
        group_service: CandidateIdentityGroupService,
        candidate_repository: AnalysisRepository,
        judge: IdentityJudge | None = None,
        shortlist_retriever: CandidateShortlistRetriever | None = None,
    ) -> None:
        self._groups = group_service
        self._candidates = candidate_repository
        self._judge = judge
        self._shortlist_retriever = shortlist_retriever

    async def judge_candidate(
        self, *, project_id: str, candidate_id: str
    ) -> CandidateIdentityJudgingResult:
        focal = self._candidates.get_candidate(candidate_id)
        if focal is None or focal.project_id != project_id:
            raise CandidateNotFoundForIdentityJudging(
                "candidate not found for identity judging"
            )
        if focal.status is not AnalysisCandidateStatus.NEEDS_REVIEW:
            raise CandidateNotNeedsReviewError(
                "identity judging targets needs_review candidates only"
            )
        pool = self._same_type_pool(project_id, focal)
        shortlist = self._shortlist(project_id, focal, pool)

        judged: list[tuple[str, str]] = []
        reused: list[tuple[str, str]] = []
        for other in shortlist:
            left, right = normalize_relation_pair(focal.id, other.id)
            pair = (left, right)
            relation = self._groups.get_relation(
                project_id, focal.candidate_type, left, right
            )
            if relation is None:
                judgement = await self._judge_pair(focal, other)
                judged.append(pair)
                group_id = None
                if judgement.verdict is IdentityRelationVerdict.SAME:
                    # relation.group_id에 싣기 위해 그룹을 먼저 확정한다.
                    group_id = self._ensure_same_group(
                        project_id, focal.candidate_type, left, right
                    ).group_id
                relation = self._groups.record_relation(
                    project_id=project_id,
                    candidate_type=focal.candidate_type,
                    left_candidate_id=left,
                    right_candidate_id=right,
                    verdict=judgement.verdict,
                    rationale=judgement.rationale,
                    source="identity_judge",
                    group_id=group_id,
                )
            else:
                # 판정 재사용 — judge 재호출 없이 효과만 멱등하게 다시 적용한다.
                reused.append(pair)
                if relation.verdict is IdentityRelationVerdict.SAME:
                    self._ensure_same_group(
                        project_id, focal.candidate_type, left, right
                    )
            if relation.verdict is not IdentityRelationVerdict.UNCERTAIN:
                # same(삼각형 완성)·different(성분 충돌) 양 방향의 모순을 본다.
                self._mark_contradictions(project_id, focal.candidate_type)

        group = self._group_of(project_id, focal.candidate_type, focal.id)
        return CandidateIdentityJudgingResult(
            focal_candidate_id=focal.id,
            candidate_type=focal.candidate_type,
            shortlisted_candidate_ids=tuple(c.id for c in shortlist),
            judged_pair_ids=tuple(judged),
            reused_pair_ids=tuple(reused),
            group_id=group.group_id if group is not None else None,
        )

    # --- shortlist -------------------------------------------------------

    def _same_type_pool(
        self, project_id: str, focal: AnalysisCandidate
    ) -> tuple[AnalysisCandidate, ...]:
        # 같은 job 자기 후보도 비교 대상이 될 수 있다 — 같은 candidate id만 뺀다.
        return tuple(
            sorted(
                (
                    candidate
                    for candidate in self._candidates.list_needs_review_candidates(
                        project_id
                    )
                    if candidate.candidate_type is focal.candidate_type
                    and candidate.id != focal.id
                ),
                key=lambda candidate: candidate.id,
            )
        )

    def _shortlist(
        self,
        project_id: str,
        focal: AnalysisCandidate,
        pool: tuple[AnalysisCandidate, ...],
    ) -> tuple[AnalysisCandidate, ...]:
        if focal.candidate_type is AnalysisCandidateType.CHARACTER_OBSERVATION:
            target = _normalized_character_name(focal)
            if target is None:
                return ()
            return tuple(
                candidate
                for candidate in pool
                if _normalized_character_name(candidate) == target
            )
        if self._shortlist_retriever is None:
            # adapter가 없으면 빈 shortlist — 실패가 아니라 no-op이다.
            return ()
        selected = self._shortlist_retriever.shortlist(
            project_id=project_id, candidate=focal, pool=pool
        )
        allowed = {candidate.id for candidate in pool}
        return tuple(
            candidate for candidate in selected if candidate.id in allowed
        )

    # --- 판정 seam ---------------------------------------------------------

    async def _judge_pair(
        self, focal: AnalysisCandidate, other: AnalysisCandidate
    ) -> IdentityJudgement:
        if self._judge is None:
            raise IdentityJudgeNotConfigured(
                "identity judging needs a judge but none is configured"
            )
        result = self._judge.judge(left=focal, right=other)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result.verdict, IdentityRelationVerdict) or not (
            isinstance(result.rationale, str)
        ):
            raise InvalidIdentityJudgement(
                f"identity judge returned {result.verdict!r}, which is not a "
                "valid identity relation verdict"
            )
        return result

    # --- 그룹 연결·모순 ----------------------------------------------------

    def _group_of(
        self,
        project_id: str,
        candidate_type: AnalysisCandidateType,
        candidate_id: str,
    ) -> CandidateIdentityGroup | None:
        for group in self._groups.list_groups(project_id):
            if group.candidate_type is not candidate_type:
                continue
            if group.status is IdentityGroupStatus.CLOSED:
                # 병합으로 흡수된 껍데기 — 소속 판정에서 제외한다.
                continue
            for member in self._groups.list_members(project_id, group.group_id):
                if member.candidate_id == candidate_id:
                    return group
        return None

    def _ensure_same_group(
        self,
        project_id: str,
        candidate_type: AnalysisCandidateType,
        left_id: str,
        right_id: str,
    ) -> CandidateIdentityGroup:
        group_left = self._group_of(project_id, candidate_type, left_id)
        group_right = self._group_of(project_id, candidate_type, right_id)
        if group_left is not None and group_right is not None:
            if group_left.group_id == group_right.group_id:
                return group_left
            # 서로 다른 두 그룹을 잇는 same — 오래된 그룹이 살아남는다.
            keep, drop = sorted(
                (group_left, group_right),
                key=lambda group: (group.created_at, group.group_id),
            )
            for member in self._groups.list_members(project_id, drop.group_id):
                self._groups.add_member(
                    project_id=project_id,
                    group_id=keep.group_id,
                    candidate_id=member.candidate_id,
                    candidate_type=candidate_type,
                )
            self._groups.set_group_status(
                project_id, drop.group_id, IdentityGroupStatus.CLOSED
            )
            return keep
        if group_left is None and group_right is None:
            group = self._groups.create_group(project_id, candidate_type)
            for candidate_id in (left_id, right_id):
                self._groups.add_member(
                    project_id=project_id,
                    group_id=group.group_id,
                    candidate_id=candidate_id,
                    candidate_type=candidate_type,
                )
            return group
        group = group_left or group_right
        joining = right_id if group_left is not None else left_id
        self._groups.add_member(
            project_id=project_id,
            group_id=group.group_id,
            candidate_id=joining,
            candidate_type=candidate_type,
        )
        return group

    def _mark_contradictions(
        self, project_id: str, candidate_type: AnalysisCandidateType
    ) -> None:
        for relation in self._groups.list_relations(project_id):
            if relation.candidate_type is not candidate_type:
                continue
            if relation.verdict is not IdentityRelationVerdict.DIFFERENT:
                continue
            if not self._same_component(
                project_id,
                candidate_type,
                relation.left_candidate_id,
                relation.right_candidate_id,
            ):
                continue
            group = self._group_of(
                project_id, candidate_type, relation.left_candidate_id
            )
            # open일 때만 올린다 — 이미 contradicted면 재표시하지 않는다(멱등).
            if group is not None and group.status is IdentityGroupStatus.OPEN:
                self._groups.set_group_status(
                    project_id, group.group_id, IdentityGroupStatus.CONTRADICTED
                )

    def _same_component(
        self,
        project_id: str,
        candidate_type: AnalysisCandidateType,
        left_id: str,
        right_id: str,
    ) -> bool:
        """``same`` relation들로 이은 연결 성분 안에서 둘이 이어지는가(BFS)."""
        if left_id == right_id:
            return True
        adjacency: dict[str, set[str]] = {}
        for relation in self._groups.list_relations(project_id):
            if relation.candidate_type is not candidate_type:
                continue
            if relation.verdict is not IdentityRelationVerdict.SAME:
                continue
            adjacency.setdefault(relation.left_candidate_id, set()).add(
                relation.right_candidate_id
            )
            adjacency.setdefault(relation.right_candidate_id, set()).add(
                relation.left_candidate_id
            )
        stack = [left_id]
        seen = {left_id}
        while stack:
            node = stack.pop()
            for neighbor in adjacency.get(node, ()):
                if neighbor == right_id:
                    return True
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        return False


def _normalized_character_name(candidate: AnalysisCandidate) -> str | None:
    name = candidate.payload.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    return normalize_name(name)
