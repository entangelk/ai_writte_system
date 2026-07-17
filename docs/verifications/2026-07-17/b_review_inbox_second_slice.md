# Verification Record — Frontend B Review Inbox 두 번째 슬라이스(candidate edit + conflict merge/split)

## Subject metadata

- **날짜**: 2026-07-17
- **요청자**: 오너(작업 AI의 완료 보고에 대한 독립 검증 요청 — "다음 작업 검증해줘")
- **검증자**: 독립 검증 AI(본 세션)
- **대상 슬라이스/산물**: Frontend B Review Inbox 두 번째 슬라이스. 변경 `frontend/src/review/ReviewInboxDetail.tsx`(edit 폼 + conflict merge/split 버튼)·`ReviewInboxDetail.test.tsx`(+8 신규 / −1 삭제), `frontend/src/api/client.ts`(`editCandidate`·`reconcileConflict` 추가), `frontend/src/styles.css`(edit-form·conflict 스타일), 문서 `docs/system-contract-sot.md`(v1.7.5 행)·`HANDOFF.md`·`CHANGELOG.md`·`docs/daily_logs/2026-07-17/work_log.md`(Task 2)·`docs/plans/frontend-review-inbox-decisions.md`(follow-up).
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.7.5(Approved). 소비 계약 = v1.6.67 어포던스(`plans/06-review-inbox-affordances-decisions.md`). 백엔드 write 라우트/요청 모델 = `services/application/app/main.py`(edit `:1889` `EditCandidateRequest{payload}`·reconcile `:2173` `ReconcileCharacterRequest{action}`)·`services/application/app/analysis/reconciliation.py`(`ReconciliationAction` MERGE/SPLIT)·`review_inbox.py`(`conflict_affordances` merge=character+matched·split=character). 선행 검증 = `docs/verifications/2026-07-17/b_review_inbox_ui.md`(v1.7.4 조건부 합격, B1=dismiss 빈 셀).
- **소스**: 커밋 `18e0b8b`("feat(frontend): B Review Inbox 두 번째 슬라이스 … SoT v1.7.5"). 작업 트리 clean(커밋 완료).

## Scope

1. **정본 계약(범위화된 읽기)**: SoT v1.7.5 행(edit in-place·키 추가/삭제 금지·빈 필드 disabled·400/409 폼 유지·취소 복귀·merge/split 어포던스 소비·edit 모드 중 타 action 숨김·성공 시 목록 재조회) + v1.6.67 conflict 자격(merge=character+matched·split=character) + 백엔드 edit/reconcile 요청 모델.
2. **구현 코드**: `ReviewInboxDetail.tsx`(edit form 상태머신·merge/split 배선·예외 처리)·`client.ts` `editCandidate`/`reconcileConflict`.
3. **회귀 테스트 코드 자체**: `ReviewInboxDetail.test.tsx`(15) — assertion이 계약을 pin하는지, mutation bite 2종, boundary matrix 빈 셀.
4. **선행 검증 조건(dismiss 빈 셀) 폐쇄 확인**: v1.7.4 커밋(ae2f638)이 dismiss 회귀를 추가했는지.
5. **백엔드 무변 + 빌드/문서**: `gen:api` diff 0·build 93 modules·backend scope 0·git diff --check. SoT/HANDOFF/CHANGELOG/work_log 수치 정합·자기모순.

## Methodology

독립·대립적. 작업 AI 주장을 반박 시도. 모든 명령 재현 가능.

- **백엔드 계약 대조**: `ReconcileCharacterRequest{action:str}`·`EditCandidateRequest{payload:dict}`·`ReconciliationAction`(merge/split)·reconcile 라우트(`main.py:2173-2200`)를 `client.ts editCandidate/reconcileConflict`의 URL·body와 대조.
- **boundary matrix**: v1.7.5 신규 should-fire(edit/merge/split write) + should-not-fire(merge eligible=false·빈 필드·edit 400·취소) 각 셀 → named 회귀 매핑. 7개 write action 전부 pin 여부 교차 확인.
- **회귀 재실행**: `npx vitest run`(전체)·`npx vitest run src/review/`.
- **mutation bite 2종 독립 재현**: (A) `editCandidate` URL `/edit`→`/confirm` (B) `reconcileConflict` body `{action}`→`{action:"merge"}`. 각각 실패 폭 관측 후 원복.
- **선행 조건 폐쇄 확인**: `git show ae2f638:frontend/src/review/ReviewInbox.test.tsx | grep -c it(` 및 현재 dismiss 테스트 존재·mutation bite.
- **수치 재계산**: 보고 "+9" vs 실제(ReviewInboxDetail 8→15) 대조.
- **무결성**: `gen:api` diff·`build`·`git diff --check`·`git status --porcelain services/ …`.

## Findings

### 1. 정본 계약(범위화된 읽기) — 자기모순 없음

v1.7.5 행은 명확: edit는 taxonomy 정확 키 집합·non-empty 문자열 in-place 편집(키 추가/삭제 금지→서버 400), 빈 필드 저장 disabled, 400/409→폼 유지+error, 취소→복귀, merge/split은 `conflict.actions` 어포던스 소비(자격 서버 선언), 성공→목록 재조회, edit 모드 중 타 action 숨김. v1.6.67 conflict 자격(merge=character+matched·split=character)·백엔드 요청 모델과 충돌 없음.

### 2. 손선언/요청 ↔ 백엔드 계약 정합

- `editCandidate`(`client.ts`): `POST /projects/${p}/analysis/candidates/${c}/edit`, body `{payload}` = 백엔드 라우트 `:1889` + `EditCandidateRequest{payload}` 일치. ✓
- `reconcileConflict`: `POST /projects/${p}/analysis/review-queue/${e}/reconcile`, body `{action}` = 백엔드 라우트 `:2173` + `ReconcileCharacterRequest{action}` 일치. ✓ `action`은 어포던스 literal("merge"/"split") 그대로 전송 → 백엔드 `ReconciliationAction(request.action)`로 변환.

### 3. 구현이 계약 충족(edit·merge/split)

- **edit in-place(키 추가/삭제 금지)**: `startEdit`(`ReviewInboxDetail.tsx:98-107`)는 `item.payload`의 기존 키만 `draft`로 복사. 폼은 `Object.entries(draft)` 만 렌더 — 키 추가/삭제 UI 없음. ✓
- **빈 필드 저장 disabled**: `editIncomplete = draft !== null && Object.values(draft).some(v => v.trim() === "")`(`:112-113`), `disabled={editIncomplete || busy}`(`:211`). ✓ (UX 편의, 서버가 최종 authority — SoT 명시와 합치)
- **성공→목록 이동 / 400·409→폼 유지+error**: `submit`(`:84-96`)은 op 성공 시 `navigate`, catch 시 `setError + setBusy(false)`(draft 유지). edit 400 회귀가 폼 유지를 pin. ✓
- **취소→복귀**: `setDraft(null)`(`:218`). ✓
- **merge/split 어포던스 소비(자격 미재계산)**: `conflict.actions.find(a => a.action === "merge"/"split")`, `disabled={!X.eligible || busy}`, `title={X.reason}`(`:247-310`). merge 버튼→`reconcileConflict(...,"merge")`, split→`reconcileConflict(...,"split")`. 도메인 자격 재계산 없음. ✓
- **edit 모드 중 타 action 숨김**: detail-actions와 conflict merge/split 모두 `{draft === null && (...)}`로 게이트(`:136,272`). edit 중엔 저장/취소만. ✓
- **모든 write 성공→목록**: `submit`이 `navigate(…/review)`(목록 재조회). 낙관적 패치 없음. ✓

### 4. 회귀 테스트(양방향) + mutation bite 2종 독립 재현

- 전체 `npx vitest run` → **106 passed / 7 files**(review: ReviewInbox 9 + ReviewInboxDetail 15 = 24). ✓
- **mutation bite A(edit URL) 재현**: `editCandidate` URL `/edit`→`/confirm` → "edits the candidate payload then re-versions via the edit endpoint" **단독 실패(1 failed | 14 passed)**, 나머지 14 통과. 원복 후 15/15. ✓ (보고 "1 failed/14 passed"와 정확 일치)
- **mutation bite B(reconcile action) 재현**: `reconcileConflict` body `{action}`→`{action:"merge"}` 하드코딩 → "splits a conflict via the reconcile endpoint with the split action" **단독 실패(1 failed | 14 passed)**, merge 테스트는 통과 유지. 원복 후 15/15. ✓
- **boundary matrix(v1.7.5 신규 + 전체 write)**:

  | write action | pin | 테스트 |
  |---|---|---|
  | confirm(detail) | URL | "confirms via the confirm endpoint…" |
  | reject(detail) | URL | "rejects via the reject endpoint…" |
  | edit | URL+body{payload} | "edits the candidate payload then re-versions…" |
  | reconcile merge | URL+body{merge} | "merges a conflict via the reconcile endpoint…" |
  | reconcile split | body{split} | "splits a conflict via the reconcile endpoint with the split action" |
  | confirm/resolve/dismiss(list) | URL | ReviewInbox.test.tsx |
  | reject(list) | — detail에서 cross-file pin | |

  **이제 7개 write action 전부 named 회귀에 pin.** v1.7.4의 dismiss 빈 셀(B1)은 폐쇄됨(아래 Findings 5).

  over-strict: merge eligible=false→disabled+reason("disables merge from the conflict affordance")·빈 필드 저장 disabled·edit 400 폼 유지 — 전부 pin. ✓

### 5. 선행 검증 조건(dismiss 빈 셀) 폐쇄 확인

v1.7.4 독립 검증(`b_review_inbox_ui.md`)의 유일한 차단 소견이었던 dismiss endpoint 미pin이 **폐쇄됐다**:
- `git show ae2f638:…/ReviewInbox.test.tsx | grep -c it(` → 9(v1.7.4 첫 슬라이스 8 + dismiss 1).
- 현재 `ReviewInbox.test.tsx:145` "dismisses a gate finding via the dismiss endpoint then re-reads" — "무시" 클릭 → `expect(...).toBe("…/gate-findings/g1/dismiss")` + 빈 상태 재조회. ✓
- v1.7.4 커밋 메시지·work_log line 82-86이 mutation bite(dismiss URL→/resolve 변이 시 단독 실패)까지 기술. ✓

### 6. 백엔드·schema 무변 + 빌드

- `git status --porcelain services/ tests/ scripts/ schemas/ docker-compose.yml` → **0건**. ✓
- `gen:api` 후 schema.d.ts diff → **0(IDENTICAL)**. ✓
- `npm run build` → **93 modules**(재확인). `git diff --check` clean. ✓

## Issues / Risks

### Blocking(계약 의무)

- **없음.** 7개 write action 전부 named 회귀에 pin됐고 mutation bite 2종으로 실증, 선행 dismiss 빈 셀은 폐쇄, 백엔드/schema 무변, 손선언/요청 정합, 어포던스 순수 소비 유지.

### Hardening recommendations(비차단, 현 spec 초과 또는 문서 정확성)

- **[문서 정확성] 회귀 수 "+9" 오기**: SoT v1.7.5 행·CHANGELOG·커밋 메시지·work_log Task 2 헤더(line 121) 모두 "회귀 +9"로 표기. 그러나 실제는 ReviewInboxDetail **8→15 = 순 +7**(gross +8 신규[merge/split 렌더·merge eligible disabled·merge reconcile·split reconcile·edit endpoint·빈 필드 disabled·취소 복귀·edit 400 폼 유지] / −1 삭제[구 "does not render conflict merge/split actions" over-strict, 이제 렌더하므로 제거]). review 17→24(+7), 전체 99→106(+7). SoT 행의 "+9" 열거조차 8개 항목만 나열해 자체 모순. work_log 상세 수(line 138: Detail 15·review 24·106)는 정확해 헤더 "+9"와 충돌. 권장: "+9"→"+7(순) / +8 추가·−1 삭제"로 정정(정본 SoT 행·CHANGELOG·work_log·커밋). 테스트 자체는 정확·green이므로 슬라이스 실패 사유는 아님.
- **[문서 정확성] HANDOFF 빌들 번들 사이즈 stale**: 실제 build는 **CSS 12.28 kB(gzip 2.94)·JS 261.92 kB(gzip 82.36)**(v1.7.5가 edit-form/conflict 스타일 추가). HANDOFF(line 31)는 **11.85/260.18**(v1.7.4 수치)로 적음. 모듈 수 93은 정확. 권장: 번들 수치 갱신 또는 "93 modules"만 남기고 kB 생략.
- **[guard 대칭] split eligible=false over-strict 미pin**: merge에는 "disables merge from the conflict affordance" eligible=false 회귀가 있으나 split에는 없음(split 버튼은 동일한 `disabled={!split.eligible || busy}` 식 사용, split write 경로는 body{split}으로 pin됨). 패턴은 merge로 커버. split 자격(character-only)이 merge(character+matched)와 다르므로, split 전용 eligible=false 회귀를 추가하면 대칭성 강화(선택).
- **[UX guard 미pin] edit 모드 중 타 action 숨김 미pin**: 코드는 `draft === null &&` 게이트로 confirm/reject/merge/split을 edit 중 숨기나, 이를 단언하는 회귀가 없음("cancels an edit" 테스트는 취소 후 복귀만 검증). 동작은 정확. "edit 중 승인/병합 버튼이 보이지 않는다" 회귀 추가 시 안전망 강화(선택).

## Verdict

**합격(PASS, 조건 없음).**

독립 재검증에서 v1.7.5 슬라이스는 견고하다 — candidate edit(taxonomy 정확 키 in-place 편집·빈 필드 disabled·400/409 폼 유지·취소 복귀), conflict merge/split(어포던스 순수 소비·올바른 action 전송), 모든 write 성공 시 목록 재조회, edit 모드 중 타 action 숨김. **7개 write action(confirm/reject/edit·merge/split·resolve/dismiss)이 전부 named 회귀에 pin**됐고 mutation bite 2종(edit URL·reconcile action)을 독립 재현해 각 endpoint가 실제로 잠겨 있음을 확인. 백엔드/schema/gen:api 무변(diff 0), 손선언·요청 정합, build 93 modules, 어포던스 자격 미재계산 유지. **선행 v1.7.4 검증의 유일한 차단 조건(dismiss 빈 셀)이 폐쇄**됐다.

남은 4건은 모두 비차단(회귀 수 "+9" 오표기·stale 번들 사이즈·split eligible guard 대칭·edit-중 숨김 guard 미pin)으로, 어느 것도 계약 요구 브랜치의 미잠금이 아니다. 문서 정확성 2건("+9"→+7, 번들 사이즈)은 정본 SoT 행에 있으므로 정정을 권하나, 슬라이스 자체의 계약 충족·테스트 무결성에는 영향 없다.

## Outstanding items(오너 다음 단계에 영향)

- **로컬 커밋 2개(v1.7.4 ae2f638·v1.7.5 18e0b8b), 미 push**: push는 오너 요청 시. 본 검증은 코드 무결성을 확인했을 뿐 push 여부는 건드리지 않음.
- **문서 정정(권장, 비차단)**: SoT v1.7.5 행·CHANGELOG·work_log의 "회귀 +9"→"+7(순)", HANDOFF 번들 사이즈 갱신. 검증자가 임의 수정하지 않음.
- **실 데이터 dogfood 관통(오너 풀스택)**: 분석 candidate/gate finding을 실제로 만들어 검토함→근거→승인/수정/병합→재색인 관통(12B·실 Mongo/Chroma 필요). sandbox 불가라 unit/build/gen:api 증거로 대체. 그 결과로 `OPS-1` Ready 승격·dogfood 착수를 오너가 결정.
- **잔여 Phase 6 UI**: memory card·미회수 foreshadowing view(별도 화면)·부분 승인/retry 일반화(오너 결정) — 본 트랙과 분리 후속.

## Reproduction

```bash
cd frontend
# 1. 회귀(106 passed / 7 files; review 24)
npx vitest run

# 2. 무결성
git status --porcelain services/ tests/ scripts/ schemas/ docker-compose.yml   # → 0건
cp src/api/schema.d.ts /tmp/before.d.ts && npm run gen:api
diff -q /tmp/before.d.ts src/api/schema.d.ts                                    # → identical
npm run build                                                                   # → 93 modules
git diff --check                                                                # → clean

# 3. mutation bite A: editCandidate URL /edit -> /confirm (src/api/client.ts)
#    → "edits the candidate payload then re-versions…" 단독 실패(1 failed | 14 passed)
npx vitest run src/review/ReviewInboxDetail.test.tsx   # 원복 필수

# 4. mutation bite B: reconcileConflict body {action} -> {action:"merge"}
#    → "splits a conflict via the reconcile endpoint with the split action" 단독 실패
npx vitest run src/review/ReviewInboxDetail.test.tsx   # 원복 필수

# 5. 선행 dismiss 빈 셀 폐쇄 확인
git show ae2f638:frontend/src/review/ReviewInbox.test.tsx | grep -c "it("      # → 9
grep -n "dismisses a gate finding" src/review/ReviewInbox.test.tsx              # → :145
```

## Post-verification disposition (작업 AI, 오너 지시로 비차단 소견 반영)

오너가 "검증기록 확인해서 보강할 부분 보강하고 커밋" 지시. 원 판정(합격, 조건 없음)은 보존하고 비차단 소견 3건을 반영했다. **프로덕션 코드 무변(테스트·문서만)**.

- **소견 1(회귀 수 "+9" 오기) 반영**: 최초 커밋 시점 순 회귀는 ReviewInboxDetail 8→15 = 순 +7(추가 8·삭제 1)로, "+9" 표기가 부정확했다. SoT v1.7.5 행·CHANGELOG·work_log를 순증가 표기로 정정. 아래 소견 3의 보강 2건을 더해 최종 **순 +9(추가 10·삭제 1)**로 확정(표기와 실제 일치).
- **소견 2(HANDOFF 번들 사이즈 stale) 반영**: HANDOFF 현재 상태 라인의 CSS 11.85/JS 260.18(v1.7.4 값)을 실측 **CSS 12.28/JS 261.92**로 정정(edit-form 스타일 추가분). 모듈 수 93은 원래 정확.
- **소견 3(선택 보강) 반영**: (a) **split eligible=false→disabled+reason** 대칭 회귀(merge guard와 대칭, split의 character-only 자격 소비 pin), (b) **edit 모드 중 confirm/reject·merge/split 숨김** over-strict 회귀(상태 계약). ReviewInboxDetail 15→17, review 24→**26**, 전체 106→**108 passed/7 files**. build·gen:api·backend diff 무변(12.28/261.92, IDENTICAL, 0).
- **재확인**: 정정·보강 후 `npm test -- --run` → 108 passed/7 files, `npm run build` 93 modules, `gen:api` IDENTICAL, backend/scope diff 0, `git diff --check` clean.
