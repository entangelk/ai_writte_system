"""어떤 요청이 활동 로그에 한 행을 남기는가 (Phase 9 Slice 9.0, A2=B).

오너 결정 2026-08-09, 브리프 ``09-0-service-activity-log-decisions.md``.
이 모듈은 **분류만** 한다 — 문서 형태는 ``log.py``, 쓰기는 각 endpoint 다.

- **A2=B — 기준은 "사용자가 무엇을 *바꿨는가*"다.** Chapter 계층 경로를 포함한 정본 변경
  가 `writing/accept` 를 더했다 — 아래 그 행의 주석) + 검토 결정 9 = **20 경로**가
  + 검토 결정 경로가 ``logged`` 다. 승격·거절은 원고를 바꾸지 않지만 **기억을 바꾸고**,
  memory 가 append-only 라 이 제품에서 되돌리기가 가장 어려운 종류다.
- **★ 표는 mutating operation *전수* 다.** 오너가 B 를 고른 것은 범위 판단이지
  C(AI 요청까지)의 각하가 아니므로, **C 로 넓히는 일이 "행 값 하나 바꾸기"여야
  한다**는 것이 A2 확정 조건이다. 그래서 기록하지 않는 21 경로도 **사유와 함께**
  여기 등재된다 — 빠진 것과 일부러 뺀 것이 구분돼야 한다.
  ``tests/test_activity_actions.py`` 가 미등재 mutating route 를 실패시킨다.
- **★ C 를 열 때 A8 을 함께 다시 본다.** A8=A("중복 기록 없음")가 성립하는 근거가
  *"AI 요청은 활동 로그 밖"* 이라, ``ai_request`` 14 행만 뒤집으면 같은 사건이
  ``llm_call_audits``·``request_usage_ledger``·활동 로그 **셋**에 사는 두 정본이 된다.
- **A8=A — 이미 다른 축이 담는 것은 여기 담지 않는다.** AI 요청은 관측(호출 단위)과
  원장(과금 단위)이, 관리자 행위는 ``admin_audit_events``·``access_grant_uses`` 가
  담는다(부모 계획 §4 I3 이 섞는 것을 금지한다).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: 기록하지 않는 이유. 리터럴이 곧 "왜 뺐는가" 이며 C 확장은 ``ai_request`` 행을
#: ``logged`` 로 옮기는 것이다(위 A2 확정 조건).
ExclusionReason = Literal[
    "ai_request",
    "derived_rebuild",
    "not_project_scoped",
    "admin_audited",
]


@dataclass(frozen=True, slots=True)
class ActivityAction:
    """활동 로그에 한 행을 남기는 제품 동작 하나."""

    action: str
    """저장되는 리터럴. 조용히 바꾸면 과거 행과 대조가 끊긴다."""

    method: str
    path: str
    target_type: str
    """무엇을 바꿨는가의 종류. ``target_id`` 와 짝이다."""


@dataclass(frozen=True, slots=True)
class ExcludedOperation:
    """기록하지 않는 mutating operation — **사유와 함께** 등재한다."""

    method: str
    path: str
    reason: ExclusionReason
    note: str = ""


#: 정본 변경. "제품이 답할 수 있어야 하는 것"(부모 계획 §2)의 뼈대다.
_CANONICAL: tuple[ActivityAction, ...] = (
    ActivityAction("project_created", "POST", "/projects", "project"),
    # 개명은 덮어쓰기라 지금까지 **흔적이 전혀 없었다**(부모 계획 §1). before/after 가
    # 붙는 대표 자리이며, A3=B 가 존재하는 이유가 이 행이다.
    ActivityAction("project_renamed", "PATCH", "/projects/{project_id}", "project"),
    ActivityAction("project_archived", "DELETE", "/projects/{project_id}", "project"),
    ActivityAction("project_brief_saved", "PUT",
                   "/projects/{project_id}/brief", "project_brief"),
    ActivityAction("chapter_created", "POST",
                   "/projects/{project_id}/chapters", "chapter"),
    ActivityAction("chapter_archived", "POST",
                   "/projects/{project_id}/chapters/{chapter_id}/archive",
                   "chapter"),
    ActivityAction("chapter_purged", "POST",
                   "/projects/{project_id}/chapters/{chapter_id}/purge",
                   "chapter"),
    ActivityAction("chapter_order_changed", "PUT",
                   "/projects/{project_id}/chapter-order", "project"),
    ActivityAction("scene_order_changed", "PUT",
                   "/projects/{project_id}/chapters/{chapter_id}/scene-order",
                   "chapter"),
    ActivityAction("draft_created", "POST",
                   "/projects/{project_id}/drafts", "draft"),
    ActivityAction("draft_renamed", "PATCH",
                   "/projects/{project_id}/drafts/{draft_id}", "draft"),
    ActivityAction("draft_archived", "DELETE",
                   "/projects/{project_id}/drafts/{draft_id}", "draft"),
    # 원고 하드 삭제(2026-08-28). append-only 원장이라 **파기 뒤에도 행은 남는다** —
    # 프로젝트 purge 때만 activity.purge_project 가 행을 지운다.
    ActivityAction("draft_purged", "POST",
                   "/projects/{project_id}/drafts/{draft_id}/purge", "draft"),
    # **본문 저장.** `draft_versions` 는 append-only 지만 `created_at` 도 `user_id` 도
    # 없어서(부모 계획 §1) "누가 언제 저장했나"에 답할 수 없었다 — 이 행이 그것을 준다.
    ActivityAction("draft_version_saved", "POST",
                   "/projects/{project_id}/drafts/{draft_id}/versions",
                   "draft_version"),
    ActivityAction("draft_finalized", "POST",
                   "/projects/{project_id}/drafts/{draft_id}/finalize",
                   "draft_version"),
    ActivityAction("source_ref_created", "POST",
                   "/projects/{project_id}/snapshots/{snapshot_id}/source-refs",
                   "source_ref"),
    # ★ 오너 결정 2026-08-09(9.0 착수 결정 뒤의 추가 확정): **accept 는 정본 저장이다.**
    #   브리프 §0.2 는 이 경로를 *성격*으로 "AI·작업 요청 14" 에 넣었는데, A2 의 기준은
    #   **"사용자가 무엇을 바꿨는가"** 이고 accept 는 `start_next_unit` →
    #   `SaveDraftResult` 로 draft version 을 실제로 만든다. 그리고 이것이 **주 저작
    #   흐름의 저장 경로**라, 빼면 부모 계획 §2 의 *"특정 원고가 마지막으로 저장된 것은
    #   언제인가"* 가 수동 저장에만 답해진다. 그래서 A2 는 19 → **20 경로**다.
    #
    #   **A8(중복 없음)은 그대로다** — 여기서 남기는 것은 *AI 요청*이 아니라 *정본 저장*
    #   이고, `llm_call_audits`(호출)·`request_usage_ledger`(과금)가 담는 것과 **다른
    #   사실**이다. C 확장(AI 요청 자체를 담는 것)과 혼동하지 말 것.
    ActivityAction("draft_version_accepted", "POST",
                   "/projects/{project_id}/writing/accept", "draft_version"),
    # 장면 메모 저장(2026-08-31, Slice 2, D4=A). 메모는 원고 정본이 아니지만 **사용자가
    # 명시적으로 저장한 것**이라 A2=B 의 기준("무엇을 바꿨는가")에 그대로 걸린다 —
    # AI 요청도 파생 색인도 아니라 excluded 쪽 사유 넷 중 어느 것도 맞지 않는다.
    # 저장 버튼 연타는 handler 의 연타 창이 접는다(값이 같고 5초 안이면 행을 안 남긴다).
    ActivityAction("scene_note_saved", "PUT",
                   "/projects/{project_id}/drafts/{draft_id}/note", "scene_note"),
)

#: 검토 결정 9 — 원고가 아니라 **기억을 바꾸는 사용자 판단**.
_REVIEW: tuple[ActivityAction, ...] = (
    ActivityAction("candidate_promoted", "POST",
                   "/projects/{project_id}/analysis/candidates/{candidate_id}/promote",
                   "candidate"),
    ActivityAction("candidate_rejected", "POST",
                   "/projects/{project_id}/analysis/candidates/{candidate_id}/reject",
                   "candidate"),
    ActivityAction("candidate_edited", "POST",
                   "/projects/{project_id}/analysis/candidates/{candidate_id}/edit",
                   "candidate"),
    ActivityAction("candidate_confirmed", "POST",
                   "/projects/{project_id}/analysis/candidates/{candidate_id}/confirm",
                   "candidate"),
    ActivityAction("compare_actions_applied", "POST",
                   "/projects/{project_id}/analysis/jobs/{job_id}/apply",
                   "analysis_job"),
    ActivityAction("candidates_auto_promoted", "POST",
                   "/projects/{project_id}/analysis/jobs/{job_id}/auto-promote",
                   "analysis_job"),
    ActivityAction("review_queue_reconciled", "POST",
                   "/projects/{project_id}/analysis/review-queue/{entry_id}/reconcile",
                   "review_queue_entry"),
    ActivityAction("gate_finding_resolved", "POST",
                   "/projects/{project_id}/analysis/gate-findings/{finding_id}/resolve",
                   "gate_finding"),
    ActivityAction("gate_finding_dismissed", "POST",
                   "/projects/{project_id}/analysis/gate-findings/{finding_id}/dismiss",
                   "gate_finding"),
)

#: 기록하는 경로 전수.
ACTIVITY_ACTIONS: tuple[ActivityAction, ...] = _CANONICAL + _REVIEW

#: 기록하지 않는 21 — **사유와 함께**. 이 목록이 있어야 "빠진 것"과 "일부러 뺀 것"이
#: 구분되고, C 확장이 값 변경으로 끝난다.
EXCLUDED_OPERATIONS: tuple[ExcludedOperation, ...] = (
    # --- AI·작업 요청 14 (A2=C 로 넓힐 때 이 행들이 logged 가 된다) -------------
    #
    # ★ 넓힐 때 A8 을 함께 다시 본다: 지금 "중복 없음"이 성립하는 이유가 이 13 개가
    #   활동 로그 밖이기 때문이다. (`writing/accept` 는 2026-08-09 에 여기서 나갔다 —
    #   그것은 C 확장이 아니라 "정본 저장"이라는 다른 사실이다.)
    ExcludedOperation("POST", "/projects/{project_id}/writing/generate",
                      "ai_request", "llm_call_audits + 원장"),
    ExcludedOperation("POST", "/projects/{project_id}/writing/gate",
                      "ai_request", "llm_call_audits + 원장"),
    ExcludedOperation("POST", "/projects/{project_id}/writing/revise",
                      "ai_request", "llm_call_audits + 원장"),
    ExcludedOperation("POST", "/projects/{project_id}/writing/revise-and-gate",
                      "ai_request", "llm_call_audits + 원장"),
    ExcludedOperation("POST", "/projects/{project_id}/writing/report",
                      "ai_request", "llm_call_audits + 원장"),
    ExcludedOperation("POST",
                      "/projects/{project_id}/writing/generation-jobs/{job_id}/retry",
                      "ai_request", "같은 논리 요청의 재실행(8.0 B5)"),
    ExcludedOperation("DELETE", "/projects/{project_id}/writing/scratch",
                      "ai_request", "미승인 후보 임시 저장소 비우기 — 정본이 아니다"),
    ExcludedOperation("DELETE",
                      "/projects/{project_id}/writing/scratch/{scratch_id}",
                      "ai_request",
                      "미승인 후보 임시 저장소 항목 버리기 — 정본이 아니다"),
    ExcludedOperation("POST", "/projects/{project_id}/analysis/jobs",
                      "ai_request", "분석 작업 접수"),
    ExcludedOperation("POST", "/projects/{project_id}/analysis/jobs/{job_id}/run",
                      "ai_request", "llm_call_audits + 원장"),
    ExcludedOperation("POST", "/projects/{project_id}/analysis/jobs/{job_id}/compare",
                      "ai_request", "llm_call_audits + 원장"),
    ExcludedOperation("POST", "/projects/{project_id}/analysis/jobs/{job_id}/context",
                      "ai_request", "기존 기억 조회 — 바꾸지 않는다"),
    ExcludedOperation("POST", "/projects/{project_id}/analysis/jobs/{job_id}/retry",
                      "ai_request", "같은 논리 요청의 재실행"),
    ExcludedOperation("POST", "/projects/{project_id}/context-search",
                      "ai_request", "llm_call_audits + 원장"),
    # --- 파생 색인 재구축 1 ---------------------------------------------------
    ExcludedOperation("POST",
                      "/projects/{project_id}/snapshots/{snapshot_id}"
                      "/index/source-blocks/rebuild",
                      "derived_rebuild",
                      "파생 색인이라 사용자가 바꾼 정본이 아니다 — 정본은 그대로다"),
    # --- 인증 2 ---------------------------------------------------------------
    #
    # project 를 지목하지 않는다. 활동 로그는 **프로젝트 자식**(I1)이라 `project_id`
    # 없는 행을 담을 자리가 없고, 담게 만들면 purge 가 못 지우는 행이 생긴다.
    ExcludedOperation("POST", "/auth/login", "not_project_scoped", "세션 축"),
    ExcludedOperation("POST", "/auth/logout", "not_project_scoped", "세션 축"),
    # 승인제 가입(2026-08-22): 요청은 pending 행 하나뿐 — 정본도 세션도 아니다.
    ExcludedOperation("POST", "/auth/signup", "not_project_scoped", "가입 요청 축"),
    # --- 관리자 4 + 승인 2 ----------------------------------------------------
    #
    # I3: 관리자 행위·승격 접근과 소유자 활동을 섞으면 양쪽이 쓸모를 잃는다
    # (SoT v1.7.78). purge 생존 여부도 정반대라 한 컬렉션에 둘 수 없다.
    ExcludedOperation("POST", "/admin/users", "admin_audited", "관리자 축"),
    ExcludedOperation("POST", "/admin/users/{user_id}/deactivate",
                      "admin_audited", "관리자 축"),
    # 승인·거절은 계정 관리 조작(사용자 만들기·비활성화와 같은 축) — admin_audit
    # 도 활동 로그도 아니다(계정 관련 관리 조작은 현행대로 미기록, 브리프 P-7).
    ExcludedOperation("POST", "/admin/signup-requests/{user_id}/approve",
                      "admin_audited", "관리자 축(계정 관리)"),
    ExcludedOperation("POST", "/admin/signup-requests/{user_id}/reject",
                      "admin_audited", "관리자 축(계정 관리)"),
    # 8.5-b(2026-08-23): 회원 quota 정책 조작 — 이제 정말 admin_audit_events 에
    # 남는다(D3=ⓑ). 활동 로그는 회원의 project 행위(I3)라 여기도 관리자 축.
    ExcludedOperation("POST", "/admin/quota-policies/{user_id}/limits",
                      "admin_audited", "관리자 축(회원 정책)"),
    ExcludedOperation("POST", "/admin/quota-policies/{user_id}/suspend",
                      "admin_audited", "관리자 축(회원 정책)"),
    ExcludedOperation("POST", "/admin/quota-policies/{user_id}/activate",
                      "admin_audited", "관리자 축(회원 정책)"),
    ExcludedOperation("POST", "/admin/projects/{project_id}/purge",
                      "admin_audited", "admin_audit_events(파기 tombstone)"),
    # 소유자 purge(2026-08-28): 파기가 activity 를 통째로 지우므로 행을 남길 수
    # 없다 — 감사는 admin_audit_events 가 담는다(execute_project_purge 공유 본체).
    ExcludedOperation("POST", "/projects/{project_id}/purge",
                      "admin_audited", "파기가 activity 자체를 지운다"),
    # 관리자 아카이브(2026-08-28): purge 진입 조건을 여는 관리자 행위 — I3 의
    # 관리자 축이라 활동 로그에 남지 않는다(소유자 아카이브만 남긴다).
    ExcludedOperation("POST", "/admin/projects/{project_id}/archive",
                      "admin_audited", "관리자 축(I3)"),
    ExcludedOperation("POST", "/admin/projects/{project_id}/access-grants",
                      "admin_audited", "access_grant_uses"),
)

#: ``(path, method)`` → 기록 정의. 배선과 가드가 **같은 정본**을 본다.
ACTIVITY_ACTION_BY_OPERATION: dict[tuple[str, str], ActivityAction] = {
    (action.path, action.method.lower()): action for action in ACTIVITY_ACTIONS
}

LOGGED_OPERATIONS: frozenset[tuple[str, str]] = frozenset(
    ACTIVITY_ACTION_BY_OPERATION
)

EXCLUDED_BY_OPERATION: dict[tuple[str, str], ExcludedOperation] = {
    (excluded.path, excluded.method.lower()): excluded
    for excluded in EXCLUDED_OPERATIONS
}

#: 분류된 mutating operation 전수 — 가드가 `app.routes` 와 대조하는 집합.
CLASSIFIED_OPERATIONS: frozenset[tuple[str, str]] = LOGGED_OPERATIONS | frozenset(
    EXCLUDED_BY_OPERATION
)
