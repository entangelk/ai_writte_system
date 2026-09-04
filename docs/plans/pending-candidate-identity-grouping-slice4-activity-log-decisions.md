# Slice 4 착수 결정 브리프 — 그룹 거절의 활동 로그

**상태**: 확정 — A 채택 (2026-09-04, 오너)
**정본**: `docs/system-contract-sot.md` · 구현 페이즈
[`pending-candidate-identity-grouping-implementation-phases.md`](pending-candidate-identity-grouping-implementation-phases.md) §Slice 4
**계기**: 페이즈 공통 규칙 "활동 로그를 남길지 여부는 이 Slice 착수 시 짧은 결정 브리프로 확인한다"

## Decision needed

그룹 거절(`POST /projects/{pid}/analysis/review-inbox/groups/{group_id}/reject`,
operation 100→101)이 `activity_events`에 행을 남기는가, 남긴다면 어떤 모양인가.
분류표(`activity/actions.py`)는 mutating 전수 가드라 "남기지 않음"도 사유를 달아
`EXCLUDED_OPERATIONS`에 등재해야 하는데, 사유 축(AI 요청·파생 색인·…) 중 어느 것도
"기억을 바꾸는 사용자 판단"(A2=B)에는 맞지 않아 소극적으로는 닫히지 않는다.

## 실측한 선례 둘

| 선례 | 모양 | 재전송 시 |
|---|---|---|
| `candidates_auto_promoted`(일괄 승격, 배치 액션) | 배치당 1행(target=`analysis_job`, `after`=승격 수) | 변경 있을 때만 기록(`if promoted:` — 전부 replay면 행 0) |
| `candidate_rejected`(개별 거절) | 후보당 1행(target=`candidate`) | 무조건 기록 — replay에도 행 중복(N3와 같은 결의 알려진 공백) |

## Options table

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 그룹 행 1줄 (신규 리터럴) — 채택** | `identity_group_rejected`, target_type=`candidate_identity_group`, target_id=group_id, `after`="rejected=N, skipped=M". 변경≥1일 때만 기록 | 일괄 승격 배치 선례와 같은 모양 · 타임라인 1행 · 재전송(같은 key·다른 key 모두) 중복 없음 | 신규 리터럴 → 프론트 label 표 28행째 + `NON_LINKABLE_TARGET_TYPES` 등재 필요(가드가 전수 대조 — 이것이 연결선) · "어떤 후보가 거절됐는지"는 행 자체엔 없음 |
| B. 멤버별 행 N줄 (기존 리터럴 재사용) | 변경된 멤버마다 `candidate_rejected` 1행 | 개별 거절과 동일한 사실 모양 · 프론트 무변경 · 후보 단위로 무엇이 거절됐는지 보임 | 5멤버 그룹=5행(소음) · "그룹 액션이었다"는 맥락 소실 · 개별 거절은 replay에도 남기므로 changed만 남기려면 규칙이 미세하게 갈림 |
| C. 둘 다 | 그룹 행 + 멤버 행 | 두 관점 모두 보존 | N+1행 · 같은 사실의 두 번째 정본(A8 정신에 반함) |
| D. 남기지 않음 | EXCLUDED 등재 | 기록 최소 | A2=B에 정면으로 걸리는데 사유 축에 맞는 것이 없다 — 실질 제외 불가 |

## Recommendation + reason (오너 채택: A)

그룹 거절은 일괄 승격과 같은 종류(한 번의 조작이 여러 대상에 적용되는 배치 판단)이고,
그 선례가 이미 "배치당 1행 + 변경 있을 때만"을 확립했다. 멤버 목록은 소비 시점에
그룹에서 조인하면 되고(A8=A 정신), B의 N행은 dogfood에서 그룹이 대개 2~3멤버라
당장 아프지 않아도 계약 모양으로는 타임라인을 후보 단위 행으로 채우는 쪽이다.
**이 결정은 Slice 5(그룹 승인)의 기록 모양에도 그대로 묶인다.**

## Follow-up considerations

- changed-only 기록으로 "다시 건드리지 않는다"(같은 key 재전송·다른 key 재호출 모두
  행 0·행위 재발 없음)를 셀로 잠근다.
- 프론트 라벨 "정체성 그룹 거절" + NON_LINKABLE 사유 "검토함 목록 안에만 있다"
  (candidate와 같은 사유). label 가드(`test_activity_ui_labels.py`)가 28행 전수로 묶는다.
- 멱등은 멤버 상태 기계에서 유도한다(요청 body 없음 — 개별 reject와 대칭). 명시적
  key 필드는 단계별 진행을 저장하는 Slice 5에서만 필요하다.

## Deferred / out of scope

- 타임라인 그룹 행 → 그룹 멤버 조회 링크(LINKABLE 확장)는 Slice 6 UI 때 본다.
- 개별 거절 replay 중복(N3와 같은 결의)은 이 슬라이스에서 고치지 않는다.
