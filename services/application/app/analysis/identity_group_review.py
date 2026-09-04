"""정체성 그룹 단위 검토 액션(정체성 그룹 Slice 4·5).

그룹 거절(Slice 4, 2026-09-04)은 한 번의 조작이 여러 후보에 적용되는 **배치
검토 판단**이다. 일괄 승격(``candidates_auto_promoted``)과 같은 종류라는 것이
착수 브리프의 전제였고, 그래서 오케스트레이션도 같은 모양이다 — 저장 멤버십을
읽어 개별 거절 경로(``CandidateReviewService.reject``)를 멤버별으로 적용한다.
전이·de-index·대기열 dismissal·멱등은 전부 그 경로의 것이고, 이 서비스는
어떤 후보를 대상으로 삼을지(상태 기계 판정)와 결과의 분류만 소유한다.

그룹 승인(Slice 5, 2026-09-04 — 착수 브리프 D1=A·D2=A·D3=A·D4=A)은 같은
멤버십 위에 **오케스트레이션**을 얹는다: 첫 eligible 멤버를 canonical로
승격하고(개별 confirm 경로 그대로) 나머지를 그 canonical을 **강제 대상**으로
compare judge에 넣어 update/add_evidence/no_change/conflict로 수렴시킨다.
단계별 진행은 ``identity_group_approvals`` 문서에 저장되고 재시도는 applied
step을 재실행하지 않는다.

이 모듈이 확정한 리터럴 — 거절(Slice 4):

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
  (승인 경로의 같은 축은 step 문서 저장이 잡는다 — 아래.)

승인(Slice 5):

* **D1=A — revision이 멱등 key를 겸한다**: 요청 ``expected_revision`` ≠ 그룹
  현재 revision이면 409. 같은 revision 재전송은 문서의 진행과 붕괴해
  replay/이어가기가 된다.
* **canonical은 그룹이 정한다** — judge 대상 선택을 scope matcher에 맡기지
  않는다(create 폴스루로 두 번째 canonical이 생기는 것이 C안이 막으려던
  것이다). 멤버 중 승격된 memory가 있으면(개별 승격·잃은 패스 재구성 모두)
  **가장 이른 CANONICAL memory를 채택**한다.
* **D2=A — applied 멤버는 confirm의 부수효과 세트로 닫는다**: confirmed 전이
  + de-index + 대기열 resolve. memory write만 갈린다(승격/버전/무변).
  conflict 멤버는 needs_review 잔류 + 검토 대기열 적재(적용 경로와 같은 모양).
* **D4=A — 첫 판정 실패에 step=failed·패스 종료**(나머지는 pending 잔류,
  재호출이 이어간다). 응답은 step 상태를 싣는다 — 부분 실패는 성공처럼
  닫지 않는다(Slice 6 전제).
* **그룹·멤버·relation 행은 승인도 바꾸지 않는다**(D3=A — 거절과 대칭).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from services.application.app.analysis.candidate_review import (
    CandidateReviewService,
)
from services.application.app.analysis.compare import (
    AnalysisCompareService,
    CompareAction,
    CompareJudgeNotConfigured,
    InvalidJudgeResult,
)
from services.application.app.analysis.identity_group_approvals import (
    CandidateIdentityGroupApproval,
    CandidateIdentityGroupApprovalService,
    GroupApprovalStep,
    GroupApprovalStepStatus,
)
from services.application.app.analysis.identity_groups import (
    CandidateIdentityGroupNotFoundError,
    CandidateIdentityGroupRevisionMismatch,
    CandidateIdentityGroupService,
    IdentityGroupStatus,
)
from services.application.app.analysis.models import AnalysisCandidateStatus
from services.application.app.analysis.review_queue import ReviewQueueService
from services.application.app.analysis.service import AnalysisService
from services.application.app.memory.models import MemoryEntry, MemoryStatus
from services.application.app.memory.service import MemoryService
from services.llm_gateway.app.errors import ProviderError


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


@dataclass(frozen=True, slots=True)
class GroupApproveResult:
    """승인 패스의 관측. ``steps`` 는 후보 id 정렬(거절과 같은 결정성 리터럴).

    ``changed`` 는 이번 패스에 applied|conflict로 옮은 step 수 — 활동 로그의
    "변경≥1"과 idempotent_replay의 정본이다.
    """

    group_id: str
    expected_revision: int
    canonical_memory_id: str | None
    steps: tuple[GroupApprovalStep, ...]
    changed: int

    @property
    def idempotent_replay(self) -> bool:
        return self.changed == 0

    @property
    def applied_count(self) -> int:
        return sum(
            1 for s in self.steps if s.status is GroupApprovalStepStatus.APPLIED
        )

    @property
    def conflict_count(self) -> int:
        return sum(
            1 for s in self.steps if s.status is GroupApprovalStepStatus.CONFLICT
        )

    @property
    def skipped_count(self) -> int:
        return sum(
            1 for s in self.steps if s.status is GroupApprovalStepStatus.SKIPPED
        )


class GroupApprovalRemovalOutbox(Protocol):
    """개별 confirm 경로와 같은 de-index seam(candidate_review 의 거울)."""

    def enqueue_candidate_removed(
        self, *, project_id: str, candidate_id: str
    ) -> object: ...


class CandidateIdentityGroupReviewService:
    def __init__(
        self,
        *,
        identity_groups: CandidateIdentityGroupService,
        candidate_review: CandidateReviewService,
        analysis_service: AnalysisService,
        approvals: CandidateIdentityGroupApprovalService,
        compare: AnalysisCompareService,
        memory_service: MemoryService,
        review_queue: ReviewQueueService,
        removal_outbox: GroupApprovalRemovalOutbox | None = None,
    ) -> None:
        self._identity = identity_groups
        self._candidate_review = candidate_review
        self._analysis = analysis_service
        # Slice 5(그룹 승인) 조립 — 단계별 진행 저장·판정 seam·버전 upsert·
        # confirm 부수효과(de-index·대기열). 거절 경로는 이들을 쓰지 않는다.
        self._approvals = approvals
        self._compare = compare
        self._memory = memory_service
        self._review_queue = review_queue
        self._removal_outbox = removal_outbox

    # --- Slice 4 — 그룹 거절 -------------------------------------------------

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

    # --- Slice 5 — 그룹 승인 -------------------------------------------------

    async def approve_group(
        self, *, project_id: str, group_id: str, expected_revision: int
    ) -> GroupApproveResult:
        """첫 eligible 멤버 승격 → 나머지를 그 canonical로 수렴시킨다.

        멱등은 진행 문서가 쥔다(D1=A): 같은 revision 재호출은 applied step을
        건너뛰고 failed/pending만 이어간다. 스토리지 실패는 잡지 않고 흘려
        전역 503로 간다(step마다 저장하므로 재호출이 이어간다).
        """
        group = self._identity.get_group(project_id, group_id)
        if group.status is IdentityGroupStatus.CLOSED:
            raise CandidateIdentityGroupNotFoundError(
                "candidate identity group is closed"
            )
        if expected_revision != group.revision:
            raise CandidateIdentityGroupRevisionMismatch(
                expected=expected_revision, current=group.revision
            )
        # list_members 는 (added_at, candidate_id) 정렬 — seed 선택의 결정성 축.
        members = self._identity.list_members(project_id, group_id)

        stored = self._approvals.get(project_id, group_id)
        if stored is not None and stored.expected_revision != group.revision:
            # 낡은 패스(판정이 revision을 올렸다) — 현재 revision의 새 패스.
            stored = None
        steps: dict[str, GroupApprovalStep] = (
            {step.candidate_id: step for step in stored.steps}
            if stored is not None else {}
        )
        for member in members:
            if member.candidate_id not in steps:
                steps[member.candidate_id] = _step(
                    member.candidate_id, GroupApprovalStepStatus.PENDING
                )

        # canonical 확보 — 문서가 기억하면 그것, 아니면 멤버 memory에서 채택.
        # 채택이 terminal 분류보다 먼저다: 되살린 step(applied)은 분류가 다시
        # 건드리지 않고, 채택된 eligible 멤버는 루프의 seed 가지(confirm)로
        # 닫히기 때문이다.
        canonical: MemoryEntry | None = None
        if stored is not None and stored.canonical_memory_id is not None:
            canonical = self._memory.get_memory(
                project_id=project_id,
                memory_id=stored.canonical_memory_id,
            )
        changed = 0
        if canonical is None:
            canonical = self._adopt_member_canonical(
                project_id=project_id, members=members, steps=steps,
                reconcile=stored is not None,
            )
            if canonical is not None and stored is not None:
                # 잃은 패스의 재구성 — 이 멤버의 applied는 이번 패스가 문서에
                # 새기는 것이므로 changed가 잰다(첫 패스의 행은 503으로 못
                # 남겼다). 첫 호출의 채택은 남의 일(개별 승격)을 가로채지
                # 않는다 — step은 분류가 skipped로 두고 changed도 0이다.
                changed = sum(
                    1 for step in steps.values()
                    if step.status is GroupApprovalStepStatus.APPLIED
                )

        # pending/failed 중 후보가 terminal이 된 것은 skipped로 — 멤버 판정은
        # 거절과 같은 면(후보 상태 기계만 본다).
        runnable: list[str] = []
        for member in members:
            step = steps[member.candidate_id]
            if step.status in (
                GroupApprovalStepStatus.APPLIED,
                GroupApprovalStepStatus.CONFLICT,
                GroupApprovalStepStatus.SKIPPED,
            ):
                continue
            candidate = self._analysis.get_candidate(
                project_id=project_id, candidate_id=member.candidate_id
            )
            if candidate.status is not AnalysisCandidateStatus.NEEDS_REVIEW:
                steps[member.candidate_id] = _step(
                    member.candidate_id, GroupApprovalStepStatus.SKIPPED
                )
            else:
                runnable.append(member.candidate_id)

        # judge fail-fast — seed 하나뿐이면 판정이 필요 없다(eligible==1).
        to_judge = len(runnable) - (0 if canonical is not None else 1)
        if to_judge > 0 and not self._compare.has_judge:
            raise CompareJudgeNotConfigured(
                "group approval needs the compare judge but none is configured"
            )

        def _sorted_steps() -> tuple[GroupApprovalStep, ...]:
            return tuple(
                sorted(steps.values(), key=lambda step: step.candidate_id)
            )

        if not runnable and changed == 0:
            # 할 일이 없는 호출(eligible 0 첫 호출·완료된 승인의 replay) —
            # 문서 쓰기도 없는 무변경 replay다.
            return GroupApproveResult(
                group_id=group_id, expected_revision=group.revision,
                canonical_memory_id=(
                    canonical.id if canonical is not None else None
                ),
                steps=_sorted_steps(), changed=0,
            )

        doc = self._save_doc(
            project_id=project_id, group_id=group_id, revision=group.revision,
            canonical=canonical, steps=steps, previous=stored,
        )
        for member in members:
            candidate_id = member.candidate_id
            if candidate_id not in runnable:
                continue
            candidate = self._analysis.get_candidate(
                project_id=project_id, candidate_id=candidate_id
            )
            if canonical is None or canonical.source_candidate_id == candidate_id:
                # seed — 개별 confirm 경로 그대로. 채택된 canonical의 원천
                # 멤버도 이 가지로 닫는다(승격은 이미 있으니 replay).
                seed_memory = self._confirm_seed(
                    project_id=project_id, candidate=candidate
                )
                canonical = seed_memory
                steps[candidate_id] = GroupApprovalStep(
                    candidate_id=candidate_id,
                    status=GroupApprovalStepStatus.APPLIED,
                    action=CompareAction.CREATE.value,
                    memory_id=seed_memory.id, version=seed_memory.version,
                    error=None,
                )
                changed += 1
                doc = self._save_doc(
                    project_id=project_id, group_id=group_id,
                    revision=group.revision, canonical=canonical,
                    steps=steps, previous=doc,
                )
                continue
            try:
                proposal = await self._compare.judge_against(
                    candidate=candidate, memory=canonical
                )
            except (ProviderError, InvalidJudgeResult) as exc:
                # D4=A — 그 step=failed·패스 종료. 스토리지 503과 다르게 이건
                # 멤버 국소 실패라 200 응답에 상태로 남는다.
                steps[candidate_id] = GroupApprovalStep(
                    candidate_id=candidate_id,
                    status=GroupApprovalStepStatus.FAILED,
                    action=None, memory_id=None, version=None,
                    error=type(exc).__name__,
                )
                self._save_doc(
                    project_id=project_id, group_id=group_id,
                    revision=group.revision, canonical=canonical,
                    steps=steps, previous=doc,
                )
                break
            if proposal.action is CompareAction.CONFLICT:
                self._review_queue.enqueue(
                    project_id=project_id, job_id=candidate.job_id,
                    candidate_id=candidate_id,
                    candidate_type=candidate.candidate_type,
                    action=CompareAction.CONFLICT,
                    matched_memory_id=canonical.id,
                    rationale=proposal.rationale,
                )
                steps[candidate_id] = GroupApprovalStep(
                    candidate_id=candidate_id,
                    status=GroupApprovalStepStatus.CONFLICT,
                    action=CompareAction.CONFLICT.value,
                    memory_id=canonical.id, version=canonical.version,
                    error=None,
                )
                changed += 1
            else:
                applied_step = await self._apply_to_canonical(
                    project_id=project_id, candidate=candidate,
                    action=proposal.action, canonical=canonical,
                )
                steps[candidate_id] = applied_step
                # 버전 적용 뒤의 최신 canonical — 다음 멤버는 이것을 본다.
                canonical = self._memory.get_memory(
                    project_id=project_id,
                    memory_id=applied_step.memory_id
                    if applied_step.memory_id is not None else canonical.id,
                )
                changed += 1
            doc = self._save_doc(
                project_id=project_id, group_id=group_id,
                revision=group.revision, canonical=canonical,
                steps=steps, previous=doc,
            )
        return GroupApproveResult(
            group_id=group_id,
            expected_revision=group.revision,
            canonical_memory_id=canonical.id if canonical is not None else None,
            steps=_sorted_steps(),
            changed=changed,
        )

    def _confirm_seed(self, *, project_id: str, candidate) -> MemoryEntry:
        result = self._candidate_review.confirm(
            project_id=project_id, candidate_id=candidate.id
        )
        return self._memory.get_memory(
            project_id=project_id, memory_id=result.memory_id
        )

    async def _apply_to_canonical(
        self, *, project_id: str, candidate, action: CompareAction,
        canonical: MemoryEntry,
    ) -> GroupApprovalStep:
        """D2=A — memory write(갈림) + confirm의 부수효과 세트(공통)."""
        versioned = None
        if action is CompareAction.UPDATE:
            versioned = self._memory.record_updated_version(
                project_id=project_id, candidate=candidate,
                target_memory_id=canonical.id,
            )
        elif action is CompareAction.ADD_EVIDENCE:
            versioned = self._memory.record_evidence_version(
                project_id=project_id, candidate=candidate,
                target_memory_id=canonical.id,
            )
        transition = self._analysis.transition_candidate(
            project_id=project_id, candidate_id=candidate.id,
            target=AnalysisCandidateStatus.CONFIRMED,
        )
        if transition.changed:
            if self._removal_outbox is not None:
                self._removal_outbox.enqueue_candidate_removed(
                    project_id=project_id, candidate_id=candidate.id
                )
            self._review_queue.resolve_for_candidate(
                project_id=project_id, candidate_id=candidate.id
            )
        if versioned is not None:
            memory_id, version = versioned.memory.id, versioned.memory.version
        else:  # no_change — write 없음, step은 현재 canonical을 가리킨다.
            memory_id, version = canonical.id, canonical.version
        return GroupApprovalStep(
            candidate_id=candidate.id,
            status=GroupApprovalStepStatus.APPLIED,
            action=action.value,
            memory_id=memory_id, version=version, error=None,
        )

    def _adopt_member_canonical(
        self, *, project_id: str, members, steps: dict[str, GroupApprovalStep],
        reconcile: bool,
    ) -> MemoryEntry | None:
        """멤버 중 가장 이른(added_at 순) CANONICAL memory를 그룹 canonical로 채택.

        두 창을 닫는다 — 개별 승격 뒤 그룹 승인(두 번째 canonical 방지)과,
        문서 저장이 mid-flight로 죽은 패스의 재구성(seed 승격은 durable했다).
        ``reconcile``(문서가 있던 패스)일 때만 채택된 멤버의 pending/failed
        step을 applied/create로 되살린다 — 첫 호출의 채택은 남이 한 개별
        승격이므로 이 호출의 변경으로 세지 않는다.
        """
        for member in members:
            memory = self._memory.memory_for_candidate(
                project_id=project_id, candidate_id=member.candidate_id
            )
            if memory is None or memory.status is not MemoryStatus.CANONICAL:
                # superseded 라면 뒤늦은 멤버의 버전이 현재 canonical이다 —
                # added_at 순회가 그 행에 도달해 잡는다.
                continue
            if reconcile:
                step = steps[member.candidate_id]
                if step.status in (
                    GroupApprovalStepStatus.PENDING,
                    GroupApprovalStepStatus.FAILED,
                ):
                    steps[member.candidate_id] = GroupApprovalStep(
                        candidate_id=member.candidate_id,
                        status=GroupApprovalStepStatus.APPLIED,
                        action=CompareAction.CREATE.value,
                        memory_id=memory.id, version=memory.version,
                        error=None,
                    )
            return memory
        return None

    def _save_doc(
        self, *, project_id: str, group_id: str, revision: int,
        canonical: MemoryEntry | None, steps: dict[str, GroupApprovalStep],
        previous: CandidateIdentityGroupApproval | None,
    ) -> CandidateIdentityGroupApproval:
        return self._approvals.save(
            CandidateIdentityGroupApproval(
                group_id=group_id, project_id=project_id,
                expected_revision=revision,
                canonical_memory_id=canonical.id if canonical else None,
                steps=tuple(
                    sorted(steps.values(), key=lambda step: step.candidate_id)
                ),
                created_at=previous.created_at if previous else None,
                updated_at=previous.updated_at if previous else None,
            )
        )


def _step(
    candidate_id: str, status: GroupApprovalStepStatus
) -> GroupApprovalStep:
    return GroupApprovalStep(
        candidate_id=candidate_id, status=status,
        action=None, memory_id=None, version=None, error=None,
    )
