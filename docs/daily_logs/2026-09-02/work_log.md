# 2026-09-02 Work Log

## Goals

- Dogfood에서 확인한 최종 저장 분석 진행 표시 공백을 닫는다.
- 미승인 기억 후보의 중복 정체성 처리 경계를 기술 검토한다.
- 검토함에서 candidate 내용을 읽고 즉시 승인/거절할 수 있게 한다.
- Chapter→Scene 목록에서 finality와 분석 상태를 구분한다.

## Completed work

| 작업 | 변경 파일 | 핵심 변경 | 효과 |
|---|---|---|---|
| finalize 요청 중 진행 표시 | `frontend/src/drafts/DraftEditor.tsx` · `DraftEditor.test.tsx` | finalize 호출 직전 `analysisStatus=running`, 전체 요청 실패시 `failed`, 응답 성공시 서버 job 상태로 수렴. `running`은 stale/needs-attention 판정보다 먼저 표시 | 장시간 동기 분석 중에도 상태 바와 버튼에서 진행 확인. 완료 후 page reload 없이 자동 수렴 |
| Review Inbox 목록 요약 | `routers/analysis.py` · `frontend/src/api/client.ts` · `ReviewInbox.tsx` · `styles.css` · 회귀 | list item에 immutable candidate `payload` additive. 행을 유형/신뢰도·payload 필드·상세 링크·즉시 승인/거절 구조로 확장. 작은 화면은 단일 열로 수렴 | detail 페이지를 매번 열지 않고 목록에서 후보 내용을 읽고 처리 |
| Scene 목록 상태 | `api/models.py` · `routers/drafts.py` · generated `schema.d.ts` · `DraftList.tsx` · 회귀 | `ScenePayload` 에 latest/finalized/analysis snapshot·status를 additive. 최신 snapshot 동일성으로 finality 3상태와 analysis 4상태를 텍스트로 파생 | 최종 저장 후 수정본을 완료로 오인하지 않고, 장면 목록에서 진행/완료/필요 확인 |
| 미승인 candidate 중복 기술 검토 | `docs/plans/pending-candidate-identity-grouping-decisions.md` · `docs/plans/README.md` | 현 compare의 canonical-only 공백을 확인. 화면만 그룹/관계 저장/그룹 승인/물리 병합 4안을 비교하고 C(영속 identity group+그룹 승인)를 권장 | 출처 손실·canonical 오염을 막으며 owner-level 전이 계약을 임의로 고르지 않음 |
| 정본/변경 기록 | `docs/system-contract-sot.md` v1.8.15 · `final-save-analysis-decisions.md` · `frontend-review-inbox-decisions.md` · `CHANGELOG.md` · `HANDOFF.md` | dogfood 요구와 구현 경계, 중복 그룹 결정 대기를 정본에 반영 | 종전 “list에 payload 없음” 결정을 명시적으로 dogfood 개정 |

## Issues found

| 문제 | 원인 | 해결 | 결과 |
|---|---|---|---|
| finalize 요청 중 상태 바가 `분석 필요`로 남음 | `finalizing` 버튼 state만 올리고 `analysisStatus`를 올리지 않았음. 또 attention 분기가 local running보다 먼저였음 | 요청 직전 running + running 표시 우선순위 보정 | deferred response 회귀가 요청 중/완료 양 방향을 잠금 |
| Chapter 목록에 표시할 status 데이터가 없음 | `_scene_payload`/`ScenePayload`가 계층 metadata 6필드만 남겨 Draft read-model의 final/analysis 축을 버림 | latest version→snapshot·`analyze:{snapshot}` job을 조회해 additive read fields 제공 | 프론트가 시간 비교 없이 snapshot identity로 판정 |
| 검토함에 후보 내용이 없음 | `_review_inbox_payload(include_detail=False)`가 payload를 명시적으로 제외 | list payload에 candidate payload additive, detail은 source/conflict 전용 역할로 유지 | 목록 즉시 판단 가능 |
| 분석을 반복하면 미승인 중복이 쌓임 | job 내 logical key dedup만 있고, job 간 pending candidate는 compare 대상이 아님 | owner decision brief 생성. 원 candidate를 합치지 않고 정체성 그룹+그룹 승인 권장 | 2번은 결정 전 미구현 |

## Decisions

- 사용자는 dogfood 결과로 ① 최종 저장 분석 중/완료 확인 ② 서로 다른 분석의 같은
  인물·사건 후보 묶음·동일성 판정 ③ 검토함 목록 안 요약+즉시 승인/거절 ④ Scene
  목록 final/analysis 표시를 요구했다.
- finalize 완료 후 “리셋”은 전체 페이지 reload로 해석하지 않았다. 응답이 이미 서버의
  final/version/job 정본을 싣므로 그 값으로 state를 수렴시켜 편집 문맥을 보존했다.
- 같은 인물의 서로 다른 observation은 단순 문장 중복이 아니라 “같은 identity의 추가 근거”다.
  따라서 승인 전 candidate document 자체를 합치는 D안은 권장하지 않았다.
- 2번의 그룹 승인은 원자성·부분 실패·과금/judge 호출을 새로 정하는 owner-level fork라
  C 권장을 제시하고 구현을 멈췄다.

## Verification

- 프론트 관련 3파일 집중 회귀 → **86 passed**: Review Inbox payload 표시·즉시 액션,
  Scene final/analysis 상태(최종 저장 후 수정의 over-strict 방향 포함), finalize in-flight
  `분석 진행 중`→완료 양방향을 포함한다.
- Chapter API + 문서 인덱스/링크 + OpenAPI schema 조각 → **15 passed, 279 subtests passed**.
- `npm run gen:api` 성공, `npx tsc --noEmit` 성공, `npm run build` 성공,
  `git diff --check` 성공.
- Review Inbox API의 기존 통합 셀
  `ReviewInboxApiTest::test_list_unifies_candidate_with_open_conflict`는 두 차례 각각
  180초/50초 timeout. faulthandler에서 변경한 inbox GET/assertion 전이 아니라 `_build()`의
  project 생성 POST(`tests/test_analysis_apply_api.py:115`)에서 anyio queue wait로 멈춤을 확인했다.
  따라서 새 list payload assertion은 이 환경에서 실행 완료되지 않았으며, 제품 코드 실패로
  오인하지 않되 후속 독립 검증에서 다시 돌린다.
- 결함 패턴 sweep: top-level Draft read-model에는 이미 final/analysis snapshot 필드가 있었고
  Chapter nested `_scene_payload` 한 곳만 누락돼 있었다. 해당 원행 blame은 계층화 도입
  `54192679`이며, 같은 snapshot identity 판정을 nested payload에도 맞췄다.

## Next steps

1. 오너가 미승인 후보 그룹 선택지 A~D 중 하나를 확정한다(권장 C).
2. C 선택 시 identity group/revision 스키마, shortlist+judge, 멱등 group action, grouped Inbox UI를
   작은 슬라이스로 나눈다.
3. 이 슬라이스를 독립 검증하고 실 dogfood로 상태·목록 가독성을 육안 확인한다.
