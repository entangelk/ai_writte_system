/**
 * 활동 로그 리터럴의 **UI 문구 정본** (Phase 9 Slice 9.1, S4=ⓐ).
 *
 * ★ 이것은 두 번째 정본이고, 그래도 된다 — 오너 결정(2026-08-10):
 * *"서로 다른 섹션의 정본이면(중복된 내용이 아니라면) 정본은 몇 개가 되든 상관없어.
 * 인덱싱만 제대로 되어 있고 연결만 되어 있으면."*
 *
 * - **중복이 아니다**: 백엔드
 *   `services/application/app/activity/actions.py` 의 정본은 *"어떤 route 가 무엇을
 *   기록하는가"*(배선·분류)이고, 여기의 정본은 *"그 리터럴을 사람에게 뭐라 부르는가"*(UI 문구)다.
 * - **인덱싱**: 위 경로가 그 정본이고, 그쪽 모듈 docstring 이 이 파일을 되가리킨다.
 * - **연결**: `tests/test_activity_ui_labels.py` 가 두 표를 **전수 대조**한다. 백엔드가
 *   21번째 action 을 더하면 그 셀이 실패한다. `schema.d.ts` 는 `action` 을 `string` 으로만
 *   주므로 **타입으로는 못 잡는다 — 그 가드가 유일한 연결선이다.**
 *
 * 그래서 이 표는 **25행 전수**여야 하고, 임의로 줄이거나 늘리면 가드가 양방향으로 문다.
 */

/** `action` 리터럴 → 타임라인 한 줄에 쓰는 문구. 백엔드 분류표의 logged 25 과 1:1 이다. */
export const ACTIVITY_ACTION_LABELS: Record<string, string> = {
  // 정본 변경 (+ 원고 하드 삭제·장/장면 계층 2026-08-28 — 평면 원고 순서는 폐지)
  project_created: "프로젝트 생성",
  project_renamed: "프로젝트 이름 변경",
  project_archived: "프로젝트 보관",
  project_brief_saved: "기획 브리프 저장",
  chapter_created: "장 생성",
  chapter_archived: "장 보관",
  chapter_purged: "장 삭제",
  chapter_order_changed: "장 순서 변경",
  scene_order_changed: "장면 순서 변경",
  draft_created: "원고 생성",
  draft_renamed: "원고 제목 변경",
  draft_archived: "원고 보관",
  draft_purged: "원고 삭제",
  draft_version_saved: "원고 저장",
  source_ref_created: "출처 연결",
  draft_version_accepted: "생성 결과 반영",
  // 검토 결정 9
  candidate_promoted: "기억 후보 승격",
  candidate_rejected: "기억 후보 거절",
  candidate_edited: "기억 후보 수정",
  candidate_confirmed: "기억 후보 확정",
  compare_actions_applied: "비교 결과 적용",
  candidates_auto_promoted: "기억 후보 일괄 승격",
  review_queue_reconciled: "검토 대기열 정리",
  gate_finding_resolved: "Gate 지적 해결",
  gate_finding_dismissed: "Gate 지적 무시",
};

/**
 * 링크를 거는 `target_type` (S6=ⓑ, **구현 중 좁혀짐 — 아래 ★**).
 *
 * **화면이 있는 종류만 건다.** 나머지는 전용 화면이 없거나 목록 안에만 있어서 링크가
 * 갈 곳이 없다 — 아래 `NON_LINKABLE_TARGET_TYPES` 에 **사유와 함께 등재**한다(분류표를
 * 전수로 유지하는 `activity/actions.py`·`quota/billable_actions.py` 와 같은 관례다).
 *
 * ★ **브리프는 `draft_version` 도 링크한다고 적었지만 그럴 수 없다** — 이벤트 payload 에
 * `target_id`(= version id)만 있고 **`draft_id` 가 없어서** 편집 화면 route
 * `/projects/:projectId/drafts/:draftId` 를 만들 수 없다. 넣으려면 응답에 필드를 더해야 하고
 * 그것은 **operation 77 계약 변경**이라 이 슬라이스의 "계약 영향 0"과 어긋난다. 그래서
 * **`draft` 만** 걸고 `draft_version` 은 사유와 함께 아래 표에 등재했다(유예: 브리프 F7).
 *
 * ★ 대상이 사라진 행은 **정상**이다 — 활동 로그는 정의상 과거를 담으므로 보관·파기된
 * 원고를 가리키는 링크가 404 로 갈 수 있다. 그것은 결함이 아니라 이 화면의 성질이다.
 */
export const LINKABLE_TARGET_TYPES = ["draft"] as const;

/** 링크를 걸지 않는 `target_type` 과 그 사유. 미등재는 가드가 실패시킨다. */
export const NON_LINKABLE_TARGET_TYPES: Record<string, string> = {
  project: "지금 보고 있는 그 프로젝트다",
  project_brief: "전용 route 가 없고 개요 화면 안에 있다",
  chapter: "장 단위 route 가 없고 원고 목록 안에 중첩돼 있다",
  draft_version: "★ payload 에 draft_id 가 없어 편집 화면 route 를 만들 수 없다 (브리프 F7)",
  source_ref: "전용 화면이 없다",
  candidate: "검토함 목록 안에만 있고 단건 route 가 없다",
  analysis_job: "전용 화면이 없다",
  review_queue_entry: "검토함 목록 안에만 있다",
  gate_finding: "지적 목록 안에만 있다",
};

/** 미등재 리터럴은 **원문 그대로** 보여준다 — 라벨이 없다고 행을 숨기지 않는다. */
export function activityActionLabel(action: string): string {
  return ACTIVITY_ACTION_LABELS[action] ?? action;
}

/** 활동 한 줄에서 갈 곳. 없으면 `null`.
 *
 * 원고 purge(2026-08-28) 뒤에도 활동 행은 남는다(append-only 원장). 원고가 더
 * 없는 draft 행에 링크를 걸면 404 로 떨어진다 — `draft_version` 행이 무링크인
 * 것(F7)과 같은 처방으로, 호출자가 아는 원고 id 집합(`knownDraftIds`)에 없으면
 * 링크를 걸지 않는다. 집합을 안 넘긴 호출자는 종전처럼 항상 링크다.
 */
export function activityTargetHref(
  projectId: string,
  targetType: string,
  targetId: string,
  knownDraftIds?: ReadonlySet<string>,
): string | null {
  if (targetType === "draft") {
    if (knownDraftIds !== undefined && !knownDraftIds.has(targetId)) {
      return null;
    }
    return `/projects/${encodeURIComponent(projectId)}/drafts/${encodeURIComponent(targetId)}`;
  }
  return null;
}
