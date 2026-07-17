# Work Log — 2026-07-17

## Goals

- HANDOFF가 지정한 다음 작업(★ B Review Inbox 최소 action UI)을 착수한다. 백엔드 어포던스 계약(v1.6.67)이 이미 완결돼 있으므로 프론트는 순수 소비만 한다.
- 첫 B 슬라이스의 범위(3섹션·7액션 중 어디까지)를 오너에게 확인한 뒤 구현한다 — genuine scope fork.
- backend·OpenAPI schema·회귀는 무변으로 둔다.

## User Decisions and Rationale

- **첫 B 슬라이스 범위 = B(목록 + 근거 detail + 이진 action)**: 오너가 세 선택지(A 목록+이진 action만 / B 목록+근거 detail+이진 action / C 전체 inbox) 중 B를 택했다. 근거로 제시하고 오너가 수용한 것: Phase 6 MVP 수용 기준이 "사용자가 후보의 원문 근거와 기존 기억 차이를 확인할 수 있다"를 명시하고, candidate confirm은 needs_review candidate를 canonical memory로 **비가역 승격**하므로 근거를 안 보고 승인(A)하면 "승인 전 candidate가 canonical로 위장되지 않는다"는 Phase 6 원칙의 정신과 어긋난다. B는 근거-우선 루프를 닫으면서 가장 무거운 두 표면(candidate edit payload 폼·conflict merge/split의 미묘한 자격)을 깔끔한 후속 슬라이스로 남긴다 — A1/A2·C1/C2 분할 cadence와 동형. 브리프: `plans/frontend-review-inbox-decisions.md`.
- 새 백엔드 계약 결정은 없다. 어포던스는 v1.6.67에 이미 확정돼 있고 이 슬라이스는 그것을 소비만 한다.

## Completed work

### Frontend B Review Inbox 첫 슬라이스 — 목록 + 근거 detail + 이진 action (SoT v1.7.4, 오너 D=B)

**착수 전 계약 범위화 (코드 전에 확인한 것)**

- 백엔드 review 표면을 `main.py`에서 확인: read `GET .../analysis/review-inbox`(list: candidate items + gate_findings), `GET .../analysis/review-inbox/{candidate_id}`(detail: payload·source_refs·conflicts+diff), write candidate confirm/reject/edit·conflict reconcile(merge/split)·gate finding resolve/dismiss.
- 각 항목이 `actions: [{action, eligible, reason}]` 어포던스를 실어 보냄을 확인(`_affordance_payload`, `candidate_affordances`/`conflict_affordances`/`gate_finding_affordances`, `review_inbox.py:117-152`). **자격 규칙(candidate 3종 항상 eligible·merge=character+matched·split=character·gate=open)은 서버가 read-time 재계산**하므로 프론트는 재구현하지 않는다.
- **review-inbox/gate-finding read 엔드포인트는 `dict[str, object]` 무타입**(생성 schema에 응답 body 없음)임을 확인 → v1.6.94 첫 슬라이스 선례대로 `client.ts`에 응답 shape을 손선언(response_model 타입화는 additive 후속).

**신규 파일**

- `frontend/src/review/ReviewInbox.tsx` — 목록 페이지. candidate 행(confirm/reject 버튼)과 gate finding 행(resolve/dismiss 버튼)을 list 응답 어포던스로 렌더. action 후 목록을 **서버에서 재조회**(낙관적 패치 없음, 처리된 항목은 inbox에서 빠짐). `busy` 단일 잠금으로 in-flight 중복 action 차단. candidate 행은 detail로 링크.
- `frontend/src/review/ReviewInboxDetail.tsx` — 근거 detail. candidate payload(key-value)·원문 근거 quote·conflict diff table을 read-only로 표시하고 confirm/reject 버튼 제공. 성공 시 목록으로 복귀(`useNavigate`). missing source_ref는 quote 대신 "원문을 찾을 수 없습니다".
- `frontend/src/review/ReviewInbox.test.tsx`(9) · `ReviewInboxDetail.test.tsx`(8) — 아래 회귀.

**변경 파일**

- `frontend/src/api/client.ts` — 손선언 타입(`ReviewAffordance`·`ReviewInboxItem`·`ReviewInboxDetailItem`·`GateFinding`·`ReviewConflict`·`ReviewSourcePointer` 등)과 함수 6종(`listReviewInbox`·`getReviewInboxItem`·`confirmCandidate`·`rejectCandidate`·`resolveGateFinding`·`dismissGateFinding`). 소비자는 `reason`을 pattern-match하지 말고 `eligible`/`action`으로 분기하라는 주석 명시.
- `frontend/src/App.tsx` — `/projects/:projectId/review`·`/projects/:projectId/review/:candidateId` route 추가.
- `frontend/src/drafts/DraftList.tsx` — 프로젝트 작업 공간 헤더에 "검토함 →" 진입 링크 additive.
- `frontend/src/styles.css` — review 목록/detail/diff-table/quote/affordance 버튼 스타일(기존 종이/잉크 토큰 재사용, ghost=secondary).

**어포던스 소비 계약 (이 슬라이스의 load-bearing 규칙)**

- 프론트는 **자격을 재계산하지 않는다**. 각 버튼의 `disabled`는 서버 `eligible`, tooltip은 `reason`에서 렌더한다. 목록/detail은 needs_review·open만 노출하므로 실전 payload에선 대부분 eligible=true지만, **`eligible=false` payload를 주입한 over-strict 회귀**로 소비 계약을 잠갔다(프론트가 `eligible`을 무시하고 항상 enable하면 실패). mutation(`!confirm.eligible` 제거)에서 정확히 그 1개가 bite함을 실증.
- 이 슬라이스는 **이진 action 4종만** 배선한다(confirm/reject·resolve/dismiss). candidate `edit`·conflict `merge`/`split` 어포던스는 payload에 실려 오지만 **버튼을 렌더하지 않는다**(over-strict 회귀로 미렌더 잠금 — 다음 슬라이스).

**회귀 (양방향, 17개 — B1 dismiss closure 포함)**

- ReviewInbox(9): 목록 렌더 · 단일 origin `/api/...review-inbox` path(over-strict, 절대 URL 방지) · confirm→POST confirm+재조회(server truth) · resolve→POST resolve+재조회 · **dismiss→POST dismiss+재조회**(B1 closure, 검증 지적 반영) · **`eligible=false`→disabled+reason title**(over-strict 어포던스 소비) · deferred edit 버튼 미렌더(over-strict) · action 실패 시 detail 보존+error · 두 섹션 빈 상태.
- ReviewInboxDetail(8): payload+quote+diff 렌더 · 단일 origin detail path · confirm→endpoint+목록 복귀 · reject→endpoint+목록 복귀 · **conflict merge/split 버튼 미렌더**(over-strict) · `eligible=false`→disabled+reason · missing source_ref 표시 · confirm 실패 시 detail 유지+error.

### 문서 동기화

- `plans/frontend-review-inbox-decisions.md` 신설(범위 fork 브리프) → 오너 B 결정으로 Resolved.
- SoT v1.7.4 행 추가 + 헤더 버전/갱신일 갱신 + "타입 계약 동기화의 실제 범위" 노트에 review-inbox 손선언(무타입) 명시.
- HANDOFF·CHANGELOG·plans 인덱스 동기화(다음 B 슬라이스 = candidate edit + conflict merge/split).

## Issues found

### `과묵함`이 payload와 diff 셀 양쪽에 나와 테스트 앵커가 ambiguous

- 문제: detail 테스트의 로드 앵커 `findByText("과묵함")`이 payload dd(`trait: 과묵함`)와 diff after 셀 양쪽에 매치돼 실패(3건).
- 해결: 로드 앵커를 유니크한 payload 값 `findByText("철수")`로 교체(getByText 기본 exact match라 quote "철수는 말이 없었다."와 구분됨). diff 검증은 유니크한 before 값 `수다스러움`으로 유지.

### review-inbox 응답이 무타입이라 손선언 필요

- 문제: 브리프 기본값 "OpenAPI→TS 타입 생성"이 review 엔드포인트를 잠글 것으로 읽히지만, 이 2 endpoint는 `dict[str, object]` 반환이라 응답 schema가 빈 object다.
- 조치: v1.6.94 첫 슬라이스 선례대로 `client.ts`에 응답 shape을 손선언하고 주석에 이유를 남겼다. response_model 타입화(exact-key 회귀 선행 + save/read 모델 분리)는 이 프론트 슬라이스의 "backend 무변" 목표 밖이라 additive 후속으로 남겼다.

## Decisions

- **어포던스 순수 소비(자격 미재계산)**: 프론트가 도메인 자격 규칙을 재구현하면 백엔드와 드리프트한다. 서버가 `{action,eligible,reason}`을 선언하고 프론트는 `eligible`로 disable·`action`으로 분기·`reason`을 display로만 쓴다. over-strict 회귀로 잠갔다.
- **이진 action만 첫 슬라이스**: edit(payload 폼)·conflict merge/split(미묘 자격)은 UX가 무거워 다음 슬라이스로 분리. 어포던스는 이미 실려 오므로 다음 슬라이스는 소비만 하면 된다.
- **action 후 서버 재조회(낙관적 패치 없음)**: 서버가 상태 전이를 소유하므로 재조회가 렌더된 목록을 항상 서버의 진실로 유지한다(기존 ProjectList/DraftList 선례).
- **응답 손선언(response_model 미도입)**: 이 슬라이스 목표가 backend 무변이고, review payload는 중첩·조건부(include_detail·optional matched_memory)라 response_model 도입은 exact-key 회귀 선행이 필요한 별도 백엔드 슬라이스다.

## Verification

- **프론트 회귀**: `cd frontend && npx vitest run src/review/` → **17 passed / 2 files**. 전체 `npm test -- --run` → **99 passed / 7 files**(기존 82 + review 17).
- **어포던스 소비 mutation bite 실증**: `ReviewInbox.tsx`의 `!confirm.eligible`을 제거(서버 eligible 무시) → "disables a button from the server affordance" 회귀 **단독 실패**. 복원 후 9 passed.
- **빌드/타입**: `npm run build`(`tsc --noEmit && vite build`) → PASS, **93 modules**(CSS 11.85 kB gzip 2.89, JS 260.18 kB gzip 81.92).
- **타입 생성**: `npm run gen:api` → schema.d.ts diff **0**(backend 무변 확인).
- **backend/scope diff 0**: `git status --porcelain services/ tests/ scripts/ docker-compose.yml schemas/` → 0건. `git diff --check` clean.

### 독립 검증 조건부 합격 → B1(dismiss 빈 셀) closure

오너가 독립 검증을 요청·완료했다(`docs/verifications/2026-07-17/b_review_inbox_ui.md`). **판정 조건부 합격, blocking 1건**: 검증자가 boundary matrix에서 정확히 1개 빈 셀을 찾았다 — `dismiss` action의 endpoint+재조회 경로가 어느 회귀에도 URL-pin되지 않음(confirm은 list+detail, reject는 detail, resolve는 list에서 pin됐으나 dismiss만 누락). `dismiss`는 이 슬라이스 계약이 명시한 이진 action 4종 중 하나라 계약 요구 브랜치의 미잠금이다.

- **closure**: 검증자의 권장 조치대로 resolve 테스트와 동형인 dismiss 회귀 1건을 추가했다("dismisses a gate finding via the dismiss endpoint then re-reads" — "무시" 클릭 → `expect(...).toBe(".../gate-findings/g1/dismiss")` + 빈 상태 재조회). **mutation bite 실증**: `dismissGateFinding` URL을 `/dismiss`→`/resolve`로 변이 → 새 dismiss 회귀만 단독 실패(1 failed | 8 passed), 원복 후 9/9. 이제 4개 이진 action endpoint 전부 named 회귀에 pin.
- 검증자의 hardening 3건(비차단, 현 spec 초과)은 코드 무변으로 유지(eligible=false guard는 이미 방어적 존재, matched_memory 표시·409 안내는 다음 슬라이스 UX 후보).
- 회귀 16→17, 전체 프론트 98→99. build·gen:api·backend diff 무변.

## Next steps

- **다음 B 슬라이스 = candidate edit + conflict merge/split**: candidate edit(payload 편집 폼 → `POST .../candidates/{id}/edit`, 편집값 400 재검증)·conflict merge/split(`POST .../review-queue/{entry_id}/reconcile`, 자격은 이미 어포던스로 실려 있어 소비만). 부분 승인/retry·merge/split의 event/open_question 일반화는 오너 결정 전 구현하지 않는다.
- **실 데이터 관통(오너 풀스택)**: compose 스택에서 분석 candidate/gate finding을 실제로 만들어 검토함 목록→근거 detail→승인/거절→재색인을 관통 확인한다. sandbox는 12B·실 Mongo/Chroma 불가라 unit/build/gen:api 증거로 대체했다.
- **트리거 체크**: 이 슬라이스는 backend 무변이라 `ARCH-1` 재발화 없음. `OPS-1`은 실 12B 관통·dogfood 착수 결정 전까지 Waiting 유지.
