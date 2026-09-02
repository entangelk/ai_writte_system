# 착수 결정 브리프 — Frontend B Review Inbox 첫 슬라이스 범위

상태: `Resolved` (오너 결정 = B: 목록 + 근거 detail + 이진 action, v1.7.4 구현 완료)
관련: Phase 6 `plans/06-review-ui.md`(화면 단위·수용 기준)·어포던스 계약 `plans/06-review-inbox-affordances-decisions.md`(v1.6.67 `{action,eligible,reason}`)·HANDOFF Next Tasks "★ B Review Inbox 최소 action UI"·frontend 슬라이스 관례(A1/A2·C1/C2 분할)

## Decision needed

Review Inbox 프론트(B 트랙)를 **한 슬라이스로 다 만들지, 작은 첫 슬라이스로 쪼갤지**와 그 첫 슬라이스가 **어느 action까지 관통할지**를 정해야 한다. 백엔드는 완결돼 있고(list/detail read + 7개 write + 항목별 `actions` 어포던스), 프론트는 자격 규칙을 재구현하지 않고 `eligible`/`action`으로만 분기한다. 하지만 UI 표면은 세 성격이 다르다:

- **candidate confirm/reject** — 이진 action, list payload의 `actions`로 바로 렌더 가능(detail 불요).
- **gate finding resolve/dismiss** — 이진 action, list 응답의 `gate_findings[]`에 이미 실림(detail 불요).
- **candidate detail(원문 근거·기존 기억 diff)** — 별도 detail 조회(`review-inbox/{candidate_id}`), source quote·conflict diff 표시.
- **conflict merge/split** — detail 안 nested, 자격 규칙이 가장 미묘(character+matched).
- **candidate edit** — payload 편집 폼 필요(가장 무거운 UX), 편집값 재검증(400).

즉 "list에서 바로 되는 이진 action"과 "detail·폼이 필요한 무거운 action"이 섞여 있어 한 번에 다 만들면 슬라이스가 커진다.

## Options table

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. List + 이진 action만** (추천) | `/projects/:id/review` 목록 페이지 하나. candidate confirm/reject + gate finding resolve/dismiss를 list 응답 어포던스로 렌더, action 후 재조회. detail route·edit·conflict 없음 | 가장 작음(list endpoint 하나·detail route 불요), 4/7 action 관통, 어포던스 소비 패턴을 최소로 실증, 다음 슬라이스에 detail/conflict/edit 이관 | candidate를 **원문 근거·diff를 안 보고** 승인/거절하게 됨 — MVP 수용 기준 "사용자가 후보의 원문 근거와 기존 기억 차이를 확인할 수 있다"와 어긋남 |
| **B. List + Detail(근거) + candidate confirm/reject + gate resolve/dismiss** | A + candidate detail route(source quote·conflict diff 표시). detail을 열어 근거 확인 후 승인/거절. edit·conflict merge/split은 다음 슬라이스 | 수용 기준의 "근거 확인 후 승인" 충족(blind 승격 방지), detail read surface도 이 슬라이스에서 실증. edit(폼)·conflict(미묘 자격)를 깔끔히 후속으로 분리 | A보다 큼(detail route + source pointer/diff 렌더), conflict가 detail에 보이지만 action은 아직 없음(표시만) |
| **C. Full inbox** | 3섹션·7 action 전부(edit payload 폼·conflict merge/split 포함) | Phase 6 B 트랙 한 번에 종료 | 슬라이스 과대(폼·nested action·미묘 자격 동시), 이 저장소의 작은-슬라이스 관례 위반, 회귀 표면 급증 |

## Recommendation + reason

**B 추천.** MVP 수용 기준이 "사용자가 후보의 원문 근거와 기존 기억 차이를 확인할 수 있다"를 명시하고, candidate confirm은 **needs_review candidate를 canonical memory로 승격**하는 비가역 성격이라 근거를 안 보고 승인(A)하면 "승인 전 candidate가 canonical로 위장되지 않는다"는 Phase 6 원칙의 정신과 어긋난다. B는 근거-우선 루프를 닫으면서, 가장 무거운 두 표면(edit payload 폼·conflict merge/split의 미묘한 자격)을 깔끔한 후속 슬라이스로 남긴다 — A1/A2·C1/C2 분할 cadence와 동형이다. 로컬 1인 단계에서도 "근거 없이 기억을 확정"하는 UX는 dogfood 품질을 해친다.

A는 "일단 어포던스 배선이 도는지"만 보려면 더 작지만, review 루프의 핵심 가치(근거 확인)를 다음으로 미룬다. C는 관례상 과대다.

**오너 결정 = B**(추천 채택). v1.7.4로 구현 완료: 목록(`/projects/:projectId/review`) + 근거 detail(`/review/:candidateId`) + candidate confirm/reject + gate finding resolve/dismiss. candidate edit·conflict merge/split은 다음 슬라이스로 남겼다.

**두 번째 슬라이스 = candidate edit + conflict merge/split (v1.7.5 구현 완료)**. 첫 슬라이스가 남긴 두 무거운 표면을 detail에서 소비 확장했다 — candidate edit은 payload 필드별 textarea 폼(taxonomy 정확 키 집합·non-empty 문자열), conflict merge/split은 conflict card에 어포던스 소비 버튼(merge=character+matched·split=character 자격은 서버 선언). 새 owner fork 없음(어포던스는 v1.6.67에 이미 확정, 소비만 확장). 각 write endpoint(edit/reconcile)를 named 회귀에 pin(v1.7.4 검증 교훈). 이로써 Review Inbox 핵심 검토 루프가 완결됐다. 남은 Phase 6 UI = memory card·미회수 foreshadowing view(별도 화면)·부분 승인/retry 일반화(오너 결정 대기).

## Follow-up considerations (열어둘 문)

- **route**: `/projects/:projectId/review`(목록) + B면 `/projects/:projectId/review/:candidateId`(detail). 기존 route 관례와 정합, nginx SPA fallback 이미 준비.
- 진입점: DraftList 또는 프로젝트 화면에 Review Inbox 링크 additive.
- 다음 슬라이스: candidate edit(payload 폼) + conflict merge/split(reconcile) — 자격은 이미 어포던스로 실려 있어 소비만 하면 됨.
- action 후 목록 재조회로 서버 상태를 진실로 유지(낙관적 패치 없음 — 기존 ProjectList/DraftList 선례).

## Deferred / out of scope

백엔드/Core SOT 계약 무변(순수 소비). 부분 승인·bulk review·merge/split의 event/open_question 일반화·memory card/foreshadowing view·상태 변경 invalidate 범위는 계속 미확정(Phase 6 열린 항목). 어포던스 `reason`은 display text이므로 pattern-match 금지, `eligible`/`action`으로만 분기.

## 2026-09-02 dogfood 개정 — 목록 안 후보 요약

최초 B 결정은 “detail을 열어 근거를 확인한 뒤 승인”을 전제로 list payload에 candidate
`payload`를 싣지 않았다. dogfood에서 유형·신뢰도만 보이는 여러 행을 매번 detail로 열어야
하는 비용이 확인됐고, 오너가 “리스트 칸을 넓혀 대략적인 내용을 보고 바로 승인/거절”을
요구했다. 따라서 list item에 `payload`를 additive로 싣고, 행은 유형·신뢰도 → payload 필드
→ 즉시 승인/거절 순으로 펼쳐 보인다. detail은 source quote·conflict diff·edit/merge/split을 위한
고급 검토 통로로 계속 남는다. 자격은 여전히 서버 `actions` 어포던스만 소비한다.
