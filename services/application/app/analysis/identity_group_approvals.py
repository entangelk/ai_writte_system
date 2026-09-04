"""정체성 그룹 승인의 단계별 진행 저장(정체성 그룹 Slice 5, 2026-09-04).

그룹 승인은 한 번의 조작이 여러 멤버에 걸치는 **오케스트레이션**이다 — 계획
문서가 "각 member step은 ``pending|applied|conflict|failed|skipped`` 상태와 결과
memory/version id를 저장한다. 재시도는 ``applied`` step을 재실행하지 않는다"를
명시한다(착수 브리프 "계획·선례가 이미 묶은 것" — member 행 확장은 Slice 4의
member 수명 리터럴과 충돌하므로 신규 상태 저장이다).

저장 모양은 **그룹당 1문서**다 — steps를 내장하고 그룹 id로 upsert한다. 패스는
step 하나가 끝날 때마다 문서 전체를 다시 저장해 mid-loop 실패(스토리지 503)뒤
재호출이 끝난 step부터 이어가게 한다. 클록 해상도는 Slice 0과 같은 BSON ms
절단이다(실몽고 왕복 동등성 — 검증 B1 선례).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Callable, Protocol

from services.application.app.analysis.identity_groups import truncate_to_ms


class GroupApprovalStepStatus(StrEnum):
    """계획 Slice 5가 명시한 다섯 값 그대로."""

    PENDING = "pending"
    APPLIED = "applied"
    CONFLICT = "conflict"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class GroupApprovalStep:
    """한 멤버의 처리 결과. ``action`` 은 memory 효과(create·update·add_evidence·
    no_change·conflict)이고, seed 승격은 ``create`` 다(skipped/failed는 None)."""

    candidate_id: str
    status: GroupApprovalStepStatus
    action: str | None
    memory_id: str | None
    version: int | None
    error: str | None


@dataclass(frozen=True, slots=True)
class CandidateIdentityGroupApproval:
    group_id: str
    project_id: str
    expected_revision: int
    canonical_memory_id: str | None
    steps: tuple[GroupApprovalStep, ...]
    created_at: datetime | None
    updated_at: datetime | None


class CandidateIdentityGroupApprovalRepository(Protocol):
    """승인 진행의 저장 계약. 문서의 정체성은 (project, group)이다."""

    def save(
        self, approval: CandidateIdentityGroupApproval
    ) -> None: ...

    def get(
        self, project_id: str, group_id: str
    ) -> CandidateIdentityGroupApproval | None: ...

    def purge_project(self, project_id: str) -> None: ...


class InMemoryCandidateIdentityGroupApprovalRepository:
    def __init__(self) -> None:
        self._docs: dict[tuple[str, str], CandidateIdentityGroupApproval] = {}

    def save(self, approval: CandidateIdentityGroupApproval) -> None:
        self._docs[(approval.project_id, approval.group_id)] = approval

    def get(
        self, project_id: str, group_id: str
    ) -> CandidateIdentityGroupApproval | None:
        return self._docs.get((project_id, group_id))

    def purge_project(self, project_id: str) -> None:
        self._docs = {
            key: doc
            for key, doc in self._docs.items()
            if key[0] != project_id
        }


class CandidateIdentityGroupApprovalService:
    """진행 문서의 public service — 문서 시각(stamp)의 정본도 이곳이다.

    ``save`` 는 문서 시각을 찍고 저장된 문서를 돌려준다(``created_at`` 은 첫
    저장의 값이 재저장에서 보존된다). 오케스트레이션은 항상 반환값을 다음
    읽기의 정본으로 삼는다.
    """

    def __init__(
        self,
        repository: CandidateIdentityGroupApprovalRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repo = repository
        raw_clock = clock or (lambda: datetime.now(UTC))
        self._clock = lambda: truncate_to_ms(raw_clock())

    def save(
        self, approval: CandidateIdentityGroupApproval
    ) -> CandidateIdentityGroupApproval:
        existing = self._repo.get(approval.project_id, approval.group_id)
        now = self._clock()
        stored = replace(
            approval,
            created_at=(
                existing.created_at
                if existing is not None and existing.created_at is not None
                else (approval.created_at if approval.created_at is not None
                      else now)
            ),
            updated_at=now,
        )
        self._repo.save(stored)
        return stored

    def get(
        self, project_id: str, group_id: str
    ) -> CandidateIdentityGroupApproval | None:
        return self._repo.get(project_id, group_id)

    def purge_project(self, project_id: str) -> None:
        # project 파기의 승인 진행 다리 — execute_project_purge 가 호출한다.
        self._repo.purge_project(project_id)
