"""정체성 그룹 단위 검토 액션(정체성 그룹 Slice 4, 2026-09-04).

그룹 거절은 한 번의 조작이 여러 후보에 적용되는 **배치 검토 판단**이다.
일괄 승격(`candidates_auto_promoted`)과 같은 종류라는 것이 착수 브리프의
전제였고, 그래서 오케스트레이션도 같은 모양이다 — 저장 멤버십을 읽어
개별 거절 경로(``CandidateReviewService.reject``)를 멤버별로 적용한다.
전이·de-index·대기열 dismissal·멱등은 전부 그 경로의 것이고, 이 서비스는
어떤 후보를 대상으로 삼을지(상태 기계 판정)와 결과의 분류만 소유한다.

이 Slice가 확정한 리터럴 —

* **멤버 판정은 후보 상태 기계만 본다**: needs_review면 거절, 그 외
  (confirmed·rejected·superseded — terminal 전 종류)는 skip한다. 승격
  여부(``is_candidate_promoted``)는 보지 않는다 — 개별 reject와 같은 면이다.
* **closed 그룹은 404** — 병합으로 흡수된 껍데기며, 읽기면의 정본이 open
  그룹과 member 행이기 때문이다(Slice 3). ``contradicted``는 여전히 묶는다.
* **그룹·멤버 행은 바꾸지 않는다** — 멤버십은 append-only 참조이고, 수명은
  후보 상태로 표현된다. 거절된 멤버는 검토함 population 교집합(Slice 3
  roster)에서 자연히 사라진다. ``member_status`` 신규 값은 만들지 않는다.
* **부분 실패는 멤버 상태 멱등으로 치유된다** — 각 멤버 쓰기는 독립적·멱등이라
  중간 실패(스토리지 503) 뒤 재호출이 이미 끝난 멤버를 skip하며 이어간다.
  단계별 진행 저장은 Slice 5(그룹 승인)의 것이다.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.application.app.analysis.candidate_review import (
    CandidateReviewService,
)
from services.application.app.analysis.identity_groups import (
    CandidateIdentityGroupNotFoundError,
    CandidateIdentityGroupService,
    IdentityGroupStatus,
)
from services.application.app.analysis.models import AnalysisCandidateStatus
from services.application.app.analysis.service import AnalysisService


@dataclass(frozen=True, slots=True)
class GroupRejectResult:
    """``rejected``/``skipped`` 는 이번 호출이 분류한 멤버 후보 id(정렬)."""

    group_id: str
    rejected: tuple[str, ...]
    skipped: tuple[str, ...]

    @property
    def idempotent_replay(self) -> bool:
        # CandidateReviewResult.idempotent_replay = not transition.changed 의
        # 그룹판 — 하나도 바꾸지 않은 호출은 replay다.
        return not self.rejected


class CandidateIdentityGroupReviewService:
    def __init__(
        self,
        *,
        identity_groups: CandidateIdentityGroupService,
        candidate_review: CandidateReviewService,
        analysis_service: AnalysisService,
    ) -> None:
        self._identity = identity_groups
        self._candidate_review = candidate_review
        self._analysis = analysis_service

    def reject_group(self, *, project_id: str, group_id: str) -> GroupRejectResult:
        """그룹의 needs_review 멤버를 전부 거절하고 terminal 멤버는 skip한다.

        멱등은 상태에서 유도한다(요청 key 없음 — 개별 reject와 대칭): 완료된
        그룹의 재호출은 전 멤버가 terminal이므로 skipped 전체·rejected 공백이다.
        """
        group = self._identity.get_group(project_id, group_id)
        if group.status is IdentityGroupStatus.CLOSED:
            # 읽기면이 closed 그룹을 소속 정본에서 빼는 것과 같은 순서다 —
            # 존재하지 않는 검토 대상에 답한다.
            raise CandidateIdentityGroupNotFoundError(
                "candidate identity group is closed"
            )
        rejected: list[str] = []
        skipped: list[str] = []
        for member in self._identity.list_members(project_id, group_id):
            candidate = self._analysis.get_candidate(
                project_id=project_id, candidate_id=member.candidate_id
            )
            if candidate.status is not AnalysisCandidateStatus.NEEDS_REVIEW:
                skipped.append(candidate.id)
                continue
            result = self._candidate_review.reject(
                project_id=project_id, candidate_id=candidate.id
            )
            # 상태 검사를 통과했으므로 changed임이 보장된다 — 그럼에도 결과로
            # 분류하는 것은 changed의 정본을 candidate_review 결과로 두는 방어다
            # (auto_promote 의 ``not result.idempotent_replay`` 와 같은 모양).
            if result.idempotent_replay:
                skipped.append(candidate.id)
            else:
                rejected.append(candidate.id)
        return GroupRejectResult(
            group_id=group_id,
            rejected=tuple(sorted(rejected)),
            skipped=tuple(sorted(skipped)),
        )
