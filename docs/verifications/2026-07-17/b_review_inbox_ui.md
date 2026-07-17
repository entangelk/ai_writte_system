# Verification Record — Frontend B Review Inbox 첫 슬라이스(목록 + 근거 detail + 이진 action)

## Subject metadata

- **날짜**: 2026-07-17
- **요청자**: 오너(작업 AI의 완료 보고에 대한 독립 검증 요청 — "작업 AI의 작업내용 확인해서 검증하고 의심하고 또 의심해줄래?")
- **검증자**: 독립 검증 AI(본 세션)
- **대상 슬라이스/산물**: Frontend B Review Inbox 첫 슬라이스. 신규 `frontend/src/review/ReviewInbox.tsx`·`ReviewInboxDetail.tsx`·동반 `.test.tsx` 2종, 변경 `frontend/src/api/client.ts`(review 손선언 타입+함수 6종)·`App.tsx`(route 2종)·`drafts/DraftList.tsx`(진입 링크)·`styles.css`(review 스타일), 문서 `docs/plans/frontend-review-inbox-decisions.md`(신설, Resolved)·`docs/system-contract-sot.md`(v1.7.4 행)·`HANDOFF.md`·`CHANGELOG.md`·`docs/daily_logs/2026-07-17/work_log.md`.
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.7.4(Approved). 이 슬라이스가 소비하는 어포던스 계약 = v1.6.67 `plans/06-review-inbox-affordances-decisions.md`(`{action, eligible, reason}`, read-time 재계산·write가 authority). 범위 fork = `plans/frontend-review-inbox-decisions.md`(오너 D=B). 백엔드 라우트/어포던스 구현 = `services/application/app/main.py`·`services/application/app/analysis/review_inbox.py`.
- **소스(검증 대상 작업의 출처)**: 작업 트리, 미커밋(`git status`로 전부 untracked/modified). 커밋되지 않음(오너가 커밋을 요청하지 않음).

## Scope

코드 전에 먼저 정본 계약 범위를 확정한 뒤, 그 범위 안의 표면만 검증했다(관련 없는 규칙·과거 plan iteration은 제외).

1. **정본 계약(범위화된 읽기)**: SoT v1.7.4 행(이 슬라이스가 선언한 경계: 순수 소비·이진 action 4종만 배선·edit·merge/split 미렌더·action 후 서버 재조회·detail read-only·review-inbox 손선언), v1.6.67 어포던스 계약(action/eligible/reason + 자격 규칙), 결정 브리프(D=B, 수용 기준 "근거 확인 후 승인"), 그리고 v1.6.95 "타입 계약 동기화의 실제 범위" 노트(review-inbox 손선언 정당성).
2. **구현 코드**: `ReviewInbox.tsx`·`ReviewInboxDetail.tsx`(어포던스 소비·라우팅·재조회·에러 처리)와 `client.ts` 손선언 타입·URL 빌더 6종.
3. **회귀 테스트 코드 자체**: `ReviewInbox.test.tsx`(8)·`ReviewInboxDetail.test.tsx`(8) — assertion이 계약을 실제로 pin하는지, under/over-strict guard 존재, mutation bite.
4. **백엔드 무변**: `services/`·`tests/`·`scripts/`·`schemas/`·`docker-compose.yml` 변경 0 + `gen:api` schema diff 0.
5. **문서 동기화**: SoT v1.7.4 행·HANDOFF(Current Status/Next Tasks/Project Structure/수치)·CHANGELOG·work_log·브리프의 상호 정합성.

## Methodology

독립·대립적 접근. 작업 AI의 주장을 가설로 취급해 반박을 시도했다. 모든 명령은 재현 가능.

- **계약 범위화 → boundary matrix 구축**: v1.7.4 행 + v1.6.67 어포던스 + 브리프(D=B)가 요구하는 should-fire/should-not-fire 브랜치를 행렬로 빗겨낸 뒤, 각 셀이 어느 테스트에 매핑되는지 추적.
- **손선언 타입 ↔ 백엔드 payload 대조**: `_review_inbox_payload`(list/detail)·`_gate_finding_payload`·`_review_source_pointer`·`_affordance_payload`(`main.py:2198-2320`)·`candidate_affordances`/`conflict_affordances`/`gate_finding_affordances`(`review_inbox.py:117-152`)를 `client.ts:277-401` 손선언 타입과 필드 단위 대조.
- **write endpoint 경로 대조**: `client.ts` URL 빌더 6종 vs `main.py` 라우트 선언(confirm/reject/edit/reconcile/resolve/dismiss).
- **회귀 재실행**: `cd frontend && npx vitest run`(전체) 및 `npx vitest run src/review/`(국소).
- **mutation bite 실증**: `ReviewInbox.tsx`의 `!confirm.eligible`을 `disabled`에서 제거 → `npx vitest run src/review/ReviewInbox.test.tsx`로 실패 폭 너비 관측 후 원복.
- **백엔드 무변 증명**: `git status --porcelain services/ tests/ scripts/ docker-compose.yml schemas/`, `git diff --check`, `cp src/api/schema.d.ts /tmp/schema.before.d.ts && npm run gen:api && diff`.
- **빌드/타입**: `npm run build`(`tsc --noEmit && vite build`).
- **빈 셀 탐지**: 4개 write endpoint 각각이 어느 테스트에 URL-pin되는지 교차 확인(`grep -rn "dismiss\|무시" src/review/`).

## Findings

### 1. 정본 계약(범위화된 읽기)

- v1.7.4 행은 명확하고 자기모순이 없다: "이진 action 4종(candidate confirm/reject, gate finding resolve/dismiss)만 배선", "candidate edit·conflict merge/split 어포던스는 payload에 실려 오지만 렌더하지 않는다(다음 슬라이스)", "프론트는 자격을 재계산하지 않는다", "action 성공 후 목록을 서버에서 재조회(낙관적 패치 없음)", "detail read-only", "review-inbox/gate-finding read는 무타입이라 client.ts 손선언 소비". (`system-contract-sot.md:88`)
- v1.6.67 어포던스 계약과 모순 없음: `review_inbox.py:117-152`의 자격 규칙(candidate confirm/reject/edit 항상 eligible; conflict merge=character+matched·split=character; gate resolve/dismiss=open)은 read-time 재계산이고, 프론트는 이것을 소비만 한다.
- 브리프(`frontend-review-inbox-decisions.md:3,32`)는 `Resolved`(오너 D=B)이며, 수용 기준 "근거 확인 후 승인"을 detail route로 충족시키는 논리가 합치한다.
- **계약 내부 교차검증**: 합격. v1.7.4 행 prose(4종 배선) ↔ 어포던스 함수(action literal) ↔ 구현(findAffordance 분기 대상) ↔ 테스트 클릭 대상이 모두 정합. 단, 아래 Findings 4의 빈 셀(dismiss) 참조.

### 2. 손선언 타입 ↔ 백엔드 payload 너비 일치

`client.ts` 손선언 타입은 백엔드 payload와 정확히 같은 너비이거나 안전한 부분집합이다:

- `ReviewAffordance {action, eligible, reason}` = `_affordance_payload`와 동일(`main.py:2216-2221`). ✓
- `ReviewInboxItem`(list) 8 필드 = `_review_inbox_payload(include_detail=False)`(`main.py:2225-2237`)와 동일. ✓
- `ReviewSourcePointer`: `status: "resolved" | "missing"` = `_review_source_pointer`(`main.py:2198-2214`)가 반환하는 두 값과 정확히 일치. resolved일 때만 존재하는 필드는 optional로 올바르게 표기. ✓
- `ReviewFieldDiff {field, before, after}` = conflict diff 빌더(`main.py:2254-2258`)와 동일. ✓
- `ReviewConflict` 5 필드 = detail conflict 빌더(`main.py:2246-2265`)와 동일. `matched_memory: {id, payload} | null`은 `_memory_payload`(`main.py:1367-1384`, 14 필드)의 안전한 부분집합. detail 컴포넌트는 matched_memory를 렌더하지 않으므로 런타임 영향 0. ✓
- `ReviewInboxDetailItem extends ReviewInboxItem` + payload/source_refs/conflicts = `_review_inbox_payload(include_detail=True)`와 동일. ✓
- `GateFinding`: `_gate_finding_payload`(`main.py:2300-2320`)의 14 필드 중 9개만 선언(`request_fingerprint`/`result_fingerprint`/`created_at`/`terminal_at` 생략). **안전한 부분집합** — 소비하지 않는 백엔드 필드를 무시하는 것은 v1.6.94 첫 슬라이스 선례와 동형이며 계약 위반 아님(이 구역은 `response_model` 미적용이라 컴파일 타임 잠금이 없음을 SoT v1.7.4 노트가 명시). ✓

URL 빌더 6종은 백엔드 라우트 선언과 한 글자까지 일치:

| 함수(`client.ts`) | URL | 백엔드 라우트(`main.py`) |
|---|---|---|
| `listReviewInbox` | `/projects/${p}/analysis/review-inbox` | `:2269` ✓ |
| `getReviewInboxItem` | `/projects/${p}/analysis/review-inbox/${c}` | `:2287` ✓ |
| `confirmCandidate` | `/projects/${p}/analysis/candidates/${c}/confirm` | `:1853` ✓ |
| `rejectCandidate` | `/projects/${p}/analysis/candidates/${c}/reject` | `:1871` ✓ |
| `resolveGateFinding` | `/projects/${p}/analysis/gate-findings/${f}/resolve` | `:2359` ✓ |
| `dismissGateFinding` | `/projects/${p}/analysis/gate-findings/${f}/dismiss` | `:2365` ✓ |

단일 origin: `request()`가 `API_BASE="/api"`를 붙인다(`client.ts:5,18-30`). 절대 URL 사용 없음.

### 3. 구현이 계약을 충족(어포던스 순수 소비·이진 action·read-only·재조회)

- **자격 미재계산(핵심 계약)**: `ReviewInbox.tsx:154-182`·`:207-235`, `ReviewInboxDetail.tsx:113-133`의 모든 버튼이 `disabled={!X.eligible || busy}` + `title={X.reason ?? undefined}`로 렌더된다. 도메인 자격 규칙(문자열 비교 등)이 프론트에 전혀 없다. ✓
- **이진 action 4종만 배선**: confirm/reject(candidate)·resolve/dismiss(gate finding) 버튼만 렌더. edit·merge/split은 `findAffordance`로 찾지도 않는다. ✓
- **detail read-only**: `ReviewInboxDetail.tsx`는 payload를 `<dl>`로, quote를 `<blockquote>`로, conflict를 diff `<table>`로 표시. 편집 입력·form 없음. ✓
- **action 후 서버 재조회(낙관적 패치 없음)**: list `runAction`(`ReviewInbox.tsx:88-105`)는 op 성공 후 `await load()` 재조회. detail은 confirm/reject 성공 후 `navigate(…/review)`로 목록 복귀(`ReviewInboxDetail.tsx:72-86`). ✓
- **단일 잠금/busy**: `busy` 상태로 in-flight 중복 action 차단. 에러 시 항목 보존(list는 row, detail은 detail 유지). ✓
- **missing source_ref**: `status !== "resolved"` → "원문을 찾을 수 없습니다."(`ReviewInboxDetail.tsx:153-156`). 백엔드 status 값("resolved"/"missing")과 정합. ✓

### 4. 회귀 테스트(양방향, +16) — 어포던스 소비 mutation bite 실증

- 전체 `npx vitest run` → **98 passed / 7 files**(재실행 확인). review 16(각 8). 기존 82 + 16 = 98 정합. ✓
- **mutation bite 재현(결정적)**: `disabled={!confirm.eligible || busy !== null}`에서 `!confirm.eligible` 제거 → `npx vitest run src/review/ReviewInbox.test.tsx` 결과 **1 failed | 7 passed**. 실패한 유일한 테스트 = "disables a button from the server affordance instead of recomputing eligibility"(`ReviewInbox.test.tsx:145-173`, `expect(confirm).toBeDisabled()`가 bite). 즉 어포던스 소비 over-strict guard는 단독으로 계약을 pin하고 있다. 원복 후 16/16 회복. ✓
- **boundary matrix(should-fire / should-not-fire) 추적 결과**:

  should-fire(endpoint+재조회/렌더) — `confirm`은 list+detail 양쪽, `reject`는 detail, `resolve`는 list에서 URL-pin됨. 단 **`dismiss` endpoint는 어느 테스트에도 pin되지 않는다**(아래 Issues 참조).

  should-not-fire(over-strict) — `eligible=false→disabled+reason`(list `:145`·detail `:151`), `edit` 미렌더(`ReviewInbox.test.tsx:175`), `merge`/`split` 미렌더(`ReviewInboxDetail.test.tsx:140`), 단일 origin path assertion(list `:93`·detail `:99`) — 모두 pin됨. ✓

  under-strict(에러/빈 상태/missing ref) — list 에러 보존(`:184`)·detail 에러 보존(`:182`)·양쪽 빈 상태(`:197`)·missing source_ref(`:168`) — 모두 pin됨. ✓

### 5. 백엔드·schema 무변 + 빌드

- `git status --porcelain services/ tests/ scripts/ docker-compose.yml schemas/` → **0건**(재확인). ✓
- `npm run gen:api` 후 schema.d.ts diff → **0(IDENTICAL)**(재확인). ✓
- `npm run build` → **93 modules**(CSS 11.85 kB/gzip 2.89, JS 260.18 kB/gzip 81.92). 작업 로그/SoT/HANDOFF 수치와 정확히 일치. ✓
- `git diff --check` → clean. ✓
- `styles.css` numstat `145 0`(순수 추가, 제거 규칙 없음 — 다른 컴포넌트 스타일 회귀 없음). ✓

### 6. 문서 동기화·자기모순

- SoT v1.7.4 행·헤더 버전/갱신일·"타입 계약 동기화 노트" review-inbox 손선언 문구가 work_log·CHANGELOG와 정합. ✓
- HANDOFF Current Status(v1.7.4로 승격·B 첫 슬라이스 요약)·Next Tasks(★ 다음 = candidate edit + conflict merge/split)·Project Structure(`review/` 추가·`client.ts`/`DraftList.tsx` 주석 갱신)·테스트 수치(98/7·93 modules) 모두 일치. ✓
- `OPS-1` Waiting·`ARCH-1` Done(backend 무변이라 재발화 없음) 트리거 서술 정합. ✓
- 계약 내부 모순(spans 문서 간 action 종류·필드명·자격 조건 불일치) 발견 안 됨.

## Issues / Risks

### Blocking(계약 의무)

- **`dismiss` action endpoint가 회귀에 pin되지 않음 — boundary matrix 빈 셀** (`frontend/src/review/ReviewInbox.tsx:221-235` 배선 ↔ `ReviewInbox.test.tsx`·`ReviewInboxDetail.test.tsx` 어디에도 dismiss URL 검증 없음).
  - **문제**: 이 슬라이스의 계약(SoT v1.7.4 행 + 브리프 D=B)은 "이진 action **4종**(candidate confirm/reject, gate finding **resolve/dismiss) 배선"을 명시한다. `dismiss`는 계약 요구 action이다. 구현은 dismiss 버튼을 렌더하고 `dismissGateFinding`(→ `POST /analysis/gate-findings/{id}/dismiss`)을 배선하지만, **dismiss 버튼을 클릭해 dismiss endpoint로 POST하고 재조회하는 경로를 검증하는 회귀가 단 하나도 없다**. 대조적으로 `resolve`는 `ReviewInbox.test.tsx:127`(`expect(...).toBe("/api/projects/p1/analysis/gate-findings/g1/resolve")`)로 pin된다.
  - **실패 시나리오**: 누군가 `dismissGateFinding`의 URL을 잘못 적거나(reconcile 경로 혼동 등)·`dismiss` affordance 분기를 제거해도, resolve 테스트는 통과한 채 dismiss만 조용히 깨진 채로 배포된다(현재 98 green bar는 이를 잡지 못함).
  - **교차 확인**: `grep -rn "dismiss\|무시" src/review/` → dismiss는 `ReviewInbox.tsx`(렌더/배선)와 fixture(`{ action: "dismiss", ... }`)·주석에만 등장. "무시" 버튼을 클릭하는 테스트 단언이나 dismiss URL `toBe` 단언은 0건. detail은 gate finding이 없어 dismiss가 애초에 등장하지 않는다. 따라서 4개 write endpoint 중 `confirm`(list+detail)·`reject`(detail)·`resolve`(list)는 pin, **`dismiss`만 어디서도 pin 아님**.
  - **결정**: 계약 요구 브랜치가 회귀로 잠기지 않았으므로 CLAUDE.md("boundary matrix has no empty cells — empty cells are blocking")에 따라 차단 소견. "패턴이 resolve와 대칭이라 커버된다"는 논리는 본 규칙이 명시적으로 금지하는 회피(각 contract literal은 named 회귀에 매핑되어야). 단 1개 셀이며 1-테스트 수정으로 닫힌다.
  - **권장 조치(소견만, 검증자가 임의 수정하지 않음)**: `ReviewInbox.test.tsx`의 resolve 테스트(`:127`)와 동형으로 dismiss 테스트 추가 — "무시" 클릭 → `expect(fetchMock.mock.calls[1][0]).toBe("/api/projects/p1/analysis/gate-findings/g1/dismiss")` + 재조회 GET. 이것이 본 슬라이스의 유일한 빈 셀을 닫는다.

### Hardening recommendations(비차단, 현 spec 초과)

- **`eligible=false` guard는 현 서버에서 발화 불가(순수 방어적)**: `candidate_affordances()`(`review_inbox.py:117-124`)는 confirm/reject/edit을 무조건 eligible로 반환(inbox가 needs_review·비승격 candidate만 노출), `gate_finding_affordances`(is_open)도 inbox의 OPEN finding에선 항상 eligible. 즉 실서버 payload에선 eligible=false가 올 수 없다. over-strict guard는 "프론트가 eligible을 존중한다"는 소비 계약을 방어적으로 잠근 것(work_log 기술과 합치)이며, 이 자체로 정당하다. 단, 실전에서 이 guard가 회귀를 잡을 일은 없으므로 — 어포던스 자격 규칙 자체(예 conflict merge=character+matched)가 프론트에 새로 도입될 때 같은 패턴으로 over-strict guard를 보강할 것을 권장.
- **detail이 `matched_memory`를 표시하지 않음**: `ReviewConflict.matched_memory` 타입을 선언했으나 `ReviewInboxDetail.tsx`는 이를 렌더하지 않는다(rationale·diff만 표시). 브리프 범위("근거 quote·conflict diff") 안이므로 결함 아님. 향후 "어느 기억과 충돌인지" 표시 시 활용 후보.
- **list `runAction` 에러 분류 없음**: 409(이미 처리)와 그 외 에러를 같은 detail 문자열로 표시. 수용 기준을 만족하므로 비차단. 409를 "이미 처리됨"으로 친절히 안내하는 것은 다음 B 슬라이스 UX 후보.

## Verdict

**조건부 합격(Conditional Pass)**.

이 슬라이스의 대부분은 독립 재검증에서 견고하다 — 어포던스 순수 소비 계약(자격 미재계산, mutation bite로 단독 pin 실증), 이진 action 4종 배선, edit·merge/split 미렌더, detail read-only, action 후 서버 재조회(낙관적 패치 없음), 손선언 타입의 백엔드 payload 정합(너비 일치 또는 안전 부분집합), 단일 origin, backend·schema·gen:api 무변(diff 0), build 93 modules, 98/7 green bar·수치 정합, 문서 동기화·계약 자기모순 없음 — 이 모두 확인됐다.

단, **boundary matrix에 정확히 1개 빈 셀이 존재한다**: `dismiss` action의 endpoint+재조회 경로가 어느 회귀에도 pin되지 않는다. `dismiss`는 이 슬라이스 계약이 명시한 4개 이진 action 중 하나이므로 이것은 계약 요구 브랜치의 미잠금(차단 소견)이다. 위 "권장 조치"의 dismiss 회귀 1건을 추가하면 빈 셀이 닫혀 무조건 합격으로 승격된다.

## Outstanding items(오너 다음 단계에 영향)

- **미커밋 작업 트리**: 모든 변경(코드·문서)은 작업 트리에만 있고 커밋되지 않았다(오너가 커밋을 요청하지 않음). 작업 AI가 "커밋할까요?"를 물은 상태. 검증자는 dismiss 빈 셀을 먼저 닫을지·그대로 커밋할지 오너 결정에 맡긴다.
- **dismiss 회귀 추가 여부**: 위 차단 소견. 검증자가 임의 수정하지 않음(CLAUDE.md "검증 실패 시 검증자가 조용히 고치지 않는다").
- **실 데이터 관통**: 작업 AI가 명시한 대로 sandbox는 12B·실 Mongo/Chroma 불가라, 분석 candidate/gate finding 생성 → 검토함 → 근거 detail → 승인/거절 → 재색인 관통은 오너 품스택 후속. 본 검증은 unit/build/gen:api 증거로 한정됨.
- **다음 B 슬라이스(candidate edit + conflict merge/split)**: 자격은 이미 어포던스로 실려 오므로 소비만 하면 되나, 그 슬라이스에서도 각 write endpoint를 회귀로 pin할 것(본 검증의 dismiss 사례 교훈).

## Reproduction

```bash
cd frontend
# 1. 회귀 재실행(98 passed / 7 files 기대)
npx vitest run

# 2. 빌드(93 modules 기대)
npm run build

# 3. 백엔드·schema 무변 증명
git status --porcelain services/ tests/ scripts/ docker-compose.yml schemas/   # → 0건
git diff --check                                                                # → clean
cp src/api/schema.d.ts /tmp/schema.before.d.ts && npm run gen:api
diff -q /tmp/schema.before.d.ts src/api/schema.d.ts                             # → identical

# 4. 어포던스 소비 mutation bite(disable→1 failed | 7 passed 기대 후 원복)
# ReviewInbox.tsx confirm 버튼의 disabled={!confirm.eligible || busy !== null}에서
# !confirm.eligible 제거 후:
npx vitest run src/review/ReviewInbox.test.tsx
# → "disables a button from the server affordance …" 1건 단독 실패. 원복 필수.

# 5. dismiss 빈 셀 확인(어느 테스트도 dismiss endpoint URL을 검증하지 않음)
grep -rn "dismiss\|무시" src/review/
```

## Post-verification disposition (작업 AI, 오너 지시로 빈 셀 closure)

오너가 "검증기록 확인해서 보강할 부분 보강한 다음 커밋" 지시. 위 원 판정(조건부 합격)과 Findings/Issues는 **검증 시점 상태 그대로 보존**하고, 아래에 blocking 소견의 closure만 구분해 남긴다.

- **Blocking(dismiss 빈 셀) closure**: 검증자의 "권장 조치"대로 `ReviewInbox.test.tsx`에 resolve 테스트와 동형인 dismiss 회귀 1건을 추가했다 — "무시" 클릭 → `expect(fetchMock.mock.calls[1][0]).toBe("/api/projects/p1/analysis/gate-findings/g1/dismiss")` + 빈 상태 재조회 확인(`ReviewInbox.test.tsx`, "dismisses a gate finding via the dismiss endpoint then re-reads"). 이제 4개 이진 action endpoint(confirm/reject/resolve/dismiss)가 전부 named 회귀에 URL-pin된다.
  - **red-first/mutation bite 실증**: `dismissGateFinding`의 URL을 `/dismiss`→`/resolve`로 변이 → `npx vitest run src/review/ReviewInbox.test.tsx` 결과 **1 failed | 8 passed**, 실패한 유일한 테스트 = 새 dismiss 회귀. 원복 후 9/9 회복. 빈 셀이 양방향으로 닫혔음을 확인.
  - review 회귀 16→**17**(ReviewInbox 8→9), 전체 프론트 98→**99 passed / 7 files**. build·gen:api·backend diff 0 무변.
- **Hardening recommendations(비차단)**: 3건 모두 현 spec 초과라 코드 무변으로 둔다(검증자도 비차단으로 분류). `eligible=false` guard는 이미 방어적 over-strict로 존재하고, matched_memory 표시·409 친절 안내는 다음 B 슬라이스 UX 후보로 유지.
- **승격**: 유일한 빈 셀이 닫혔으므로 원 판정 "조건부 합격"의 조건이 해소됐다 → **무조건 합격 상당**. 원 판정 텍스트는 감사 무결성을 위해 위에 보존.
- **수치 반영**: SoT v1.7.4 행·HANDOFF·CHANGELOG·work_log의 회귀 수를 +16→+17, 98→99로 갱신했다.
