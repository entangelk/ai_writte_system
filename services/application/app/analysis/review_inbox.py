"""Read-only Phase 6 review inbox over candidates and open conflicts."""

from dataclasses import dataclass
from typing import Any, Mapping

from services.application.app.analysis.identity_groups import (
    CandidateIdentityGroupService, CandidateIdentityRelation,
    IdentityGroupStatus, IdentityRelationVerdict,
)
from services.application.app.analysis.models import (
    AnalysisCandidate, AnalysisCandidateType,
)
from services.application.app.analysis.review_queue import (
    ReviewQueueEntry, ReviewQueueService,
)
from services.application.app.analysis.service import AnalysisService
from services.application.app.memory.models import MemoryEntry
from services.application.app.memory.service import MemoryNotFound, MemoryService

#: identity_rationale_summary 상한. 활동 로그 "짧은 값"(`ACTIVITY_VALUE_MAX_CHARS`)·
#: 장면 메모 목록 미리보기(`SCENE_NOTE_PREVIEW_MAX_CHARS`)와 같은 값이다 — 목록에
#: 싣는 텍스트 조각에 두 번째 숫자를 만들지 않는다(notes.py 선례).
IDENTITY_RATIONALE_SUMMARY_MAX_CHARS = 200


@dataclass(frozen=True, slots=True)
class FieldDiff:
    field: str
    before: Any
    after: Any


@dataclass(frozen=True, slots=True)
class ConflictDetail:
    entry: ReviewQueueEntry
    matched_memory: MemoryEntry | None
    diff: tuple[FieldDiff, ...]


@dataclass(frozen=True, slots=True)
class IdentityGroupSummary:
    """목록 렌더에 필요한 identity group 최소값(정체성 그룹 Slice 3).

    소속의 정본은 **open(non-closed) 그룹과 member 행**이다 — relation 행의
    ``group_id``는 기록 시점 값이라 병합으로 흡수된(``closed``) 그룹을 가리킬
    수 있으므로 표시 전용이다. ``member_ids``는 그 멤버십을 검토함 population
    (needs_review·미승격)으로 자른 roster다 — 검토함을 떠난 stale member는
    목록 렌더에 싣지 않는다(member 수명 자체는 Slice 4·5가 확정한다).
    """

    group_id: str
    status: IdentityGroupStatus
    member_ids: tuple[str, ...]
    rationale_summary: str | None


@dataclass(frozen=True, slots=True)
class ReviewInboxItem:
    candidate: AnalysisCandidate
    conflicts: tuple[ConflictDetail, ...]
    #: 정체성 그룹 Slice 3 — additive 읽기면 메타데이터. ungrouped는 None.
    identity_group: IdentityGroupSummary | None = None


class ReviewInboxNotFound(LookupError):
    pass


class ReviewInboxService:
    def __init__(self, *, analysis_service: AnalysisService,
                 memory_service: MemoryService,
                 review_queue: ReviewQueueService,
                 identity_groups: CandidateIdentityGroupService) -> None:
        self._analysis = analysis_service
        self._memory = memory_service
        self._queue = review_queue
        self._identity = identity_groups

    def list_items(self, *, project_id: str) -> tuple[ReviewInboxItem, ...]:
        candidates = self._analysis.list_needs_review_candidates(
            project_id=project_id
        )
        candidates = tuple(
            candidate for candidate in candidates
            if not self._memory.is_candidate_promoted(project_id, candidate.id)
        )
        open_by_candidate: dict[str, list[ReviewQueueEntry]] = {}
        for entry in self._queue.list_open(project_id):
            open_by_candidate.setdefault(entry.candidate_id, []).append(entry)
        identity_groups = self._identity_summaries(project_id, candidates)
        return tuple(
            self._item(
                project_id, candidate,
                open_by_candidate.get(candidate.id, []),
                identity_group=identity_groups.get(candidate.id),
            )
            for candidate in candidates
        )

    def get_item(self, *, project_id: str, candidate_id: str) -> ReviewInboxItem:
        for item in self.list_items(project_id=project_id):
            if item.candidate.id == candidate_id:
                return item
        raise ReviewInboxNotFound("review inbox candidate not found")

    def _identity_summaries(
        self, project_id: str, candidates: tuple[AnalysisCandidate, ...]
    ) -> dict[str, IdentityGroupSummary]:
        """후보별 identity group 요약. 계산은 목록 단위로 한 번만 돈다."""
        visible = {candidate.id for candidate in candidates}
        if not visible:
            return {}
        relations = self._identity.list_relations(project_id)
        # 병합 생존 규칙과 같은 순서(오래된 그룹 first) — 후보가 non-closed
        # 그룹에 동시에 들어 있는 비정상 상태에서도 결정적으로 말한다.
        groups = sorted(
            (
                group for group in self._identity.list_groups(project_id)
                if group.status is not IdentityGroupStatus.CLOSED
            ),
            key=lambda group: (group.created_at, group.group_id),
        )
        summaries: dict[str, IdentityGroupSummary] = {}
        for group in groups:
            roster = tuple(sorted(
                member.candidate_id
                for member in self._identity.list_members(
                    project_id, group.group_id
                )
                if member.candidate_id in visible
            ))
            if len(roster) < 2:
                # 검토함에서 가시 멤버가 하나뿐인 그룹은 묶을 것이 없다.
                continue
            roster_set = set(roster)
            latest_same: dict[str, CandidateIdentityRelation] = {}
            for relation in relations:
                if relation.candidate_type is not group.candidate_type:
                    continue
                if relation.verdict is not IdentityRelationVerdict.SAME:
                    continue
                if (relation.left_candidate_id not in roster_set
                        or relation.right_candidate_id not in roster_set):
                    continue
                # relation.group_id는 보지 않는다(기록 시점 값 — 표시 전용).
                # 소속·근거 선택의 정본은 현재 roster의 pair 멤버십이다.
                order = (relation.created_at, relation.left_candidate_id,
                         relation.right_candidate_id)
                for candidate_id in (relation.left_candidate_id,
                                     relation.right_candidate_id):
                    current = latest_same.get(candidate_id)
                    if current is None or order > (
                        current.created_at, current.left_candidate_id,
                        current.right_candidate_id,
                    ):
                        latest_same[candidate_id] = relation
            for candidate_id in roster:
                if candidate_id in summaries:
                    continue
                rationale = latest_same.get(candidate_id)
                summaries[candidate_id] = IdentityGroupSummary(
                    group_id=group.group_id,
                    status=group.status,
                    member_ids=roster,
                    rationale_summary=(
                        rationale.rationale[:IDENTITY_RATIONALE_SUMMARY_MAX_CHARS]
                        if rationale is not None else None
                    ),
                )
        return summaries

    def _item(self, project_id: str, candidate: AnalysisCandidate,
              entries: list[ReviewQueueEntry],
              *, identity_group: IdentityGroupSummary | None) -> ReviewInboxItem:
        conflicts = tuple(
            self._conflict(project_id, candidate.payload, entry)
            for entry in sorted(entries, key=lambda value: value.id)
        )
        return ReviewInboxItem(
            candidate=candidate, conflicts=conflicts,
            identity_group=identity_group,
        )

    def _conflict(self, project_id: str, candidate_payload: Mapping[str, Any],
                  entry: ReviewQueueEntry) -> ConflictDetail:
        memory = None
        if entry.matched_memory_id is not None:
            try:
                memory = self._memory.get_memory(
                    project_id=project_id, memory_id=entry.matched_memory_id
                )
            except MemoryNotFound:
                memory = None
        diff = _payload_diff(memory.payload, candidate_payload) if memory else ()
        return ConflictDetail(entry=entry, matched_memory=memory, diff=diff)


def _payload_diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> tuple[FieldDiff, ...]:
    return tuple(
        FieldDiff(field=field, before=before.get(field), after=after.get(field))
        for field in sorted(set(before) | set(after))
        if before.get(field) != after.get(field)
    )


@dataclass(frozen=True, slots=True)
class ActionAffordance:
    """Declares whether a review action is available on an inbox item, and when
    not, why (v1.6.67) — so a frontend can render disabled controls with a
    tooltip. Eligibility is recomputed at read time from item state; the write
    endpoints remain the authority (an eligible=True affordance does not skip the
    write's own validation). See docs/plans/06-review-inbox-affordances-decisions.md."""

    action: str
    eligible: bool
    reason: str | None = None


_CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION


def candidate_affordances() -> tuple[ActionAffordance, ...]:
    """The inbox only surfaces needs_review, non-promoted candidates, so all
    three candidate review actions are always available (v1.6.61/66)."""
    return (
        ActionAffordance("confirm", True),
        ActionAffordance("reject", True),
        ActionAffordance("edit", True),
    )


def conflict_affordances(conflict: ConflictDetail) -> tuple[ActionAffordance, ...]:
    """merge/split reconciliation is character-only; merge additionally needs a
    resolvable matched canonical (``reconciliation.py`` reconcile guard)."""
    is_character = conflict.entry.candidate_type is _CHARACTER
    has_matched = conflict.matched_memory is not None
    if not is_character:
        merge_reason = split_reason = "merge/split is character-only"
    else:
        split_reason = None
        merge_reason = (
            None if has_matched
            else "merge requires a matched canonical memory"
        )
    return (
        ActionAffordance("merge", is_character and has_matched, merge_reason),
        ActionAffordance("split", is_character, split_reason),
    )


def gate_finding_affordances(*, is_open: bool) -> tuple[ActionAffordance, ...]:
    """A gate finding can be resolved/dismissed only while open (v1.6.65)."""
    reason = None if is_open else "gate finding is already terminal"
    return (
        ActionAffordance("resolve", is_open, reason),
        ActionAffordance("dismiss", is_open, reason),
    )
