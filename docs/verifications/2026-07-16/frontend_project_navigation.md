# 독립 검증 — Frontend 프로젝트 상세 내비게이션 슬라이스 (SoT v1.6.96)

## Subject metadata

- **날짜**: 2026-07-16
- **요청자**: 오너 (“작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?”)
- **검증자**: 독립 검증 AI (Claude Code)
- **대상 슬라이스/산출물**: Product shell 두 번째 세로 슬라이스 — `/` → `/projects/:projectId` route spine + 원고 목록/생성/빈 상태/보관 read-only/404 shell. `react-router@8.2.0` Declarative BrowserRouter 도입.
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.6.96 (버전 로그 행 + 본문 route spine 서술), `docs/plans/frontend-project-navigation-decisions.md` §4(구현된 첫 code slice 범위)·§3(UI 기준), `docs/plans/product-shell.md` “최소 사용자 표면”.
- **검증 대상 작업 출처**: working tree, uncommitted(`git status` — `frontend/src/App.tsx`, `frontend/src/drafts/`(신규), `frontend/src/api/client.ts`, `frontend/src/main.tsx`, `frontend/src/projects/ProjectList.tsx`·`.test.tsx`, `frontend/src/styles.css`, `frontend/src/App.test.tsx`(신규), `package.json`·`package-lock.json` + 문서 6건). 백엔드 `services/`·`tests/`·`scripts/`·`docker-compose.yml` diff 0.

## Scope

이 검증은 결정 브리프 §4가 **이 slice의 lock list**로 명시한 표면 전부 + 그 전제(백엔드 무변·단일 origin·타입 동기화)를 1차 소스에서 재도출한다.

1. **정본 계약(소비 면)**: SoT v1.6.96 버전 로그 행 + 본문 `/`·`/projects/:projectId` route spine 서술, 결정 브리프 §4 회귀 항목, product-shell “최소 사용자 표면”.
2. **백엔드 계약(공급 면)**: 프론트가 호출하는 5개 endpoint의 실제 존재·`response_model`·오류 코드(`services/application/app/main.py`).
3. **구현 코드**: `App.tsx`(route spine), `main.tsx`(BrowserRouter mount), `drafts/DraftList.tsx`(신규), `projects/ProjectList.tsx`(링크화), `api/client.ts`(`getProject`/`listDrafts`/`createDraft` 추가).
4. **회귀 테스트**: `App.test.tsx`(3)·`drafts/DraftList.test.tsx`(9)·`projects/ProjectList.test.tsx`(10) — 총 22.
5. **공개 envelope/스키마**: `frontend/src/api/schema.d.ts`(생성 타입)와 백엔드 `response_model` 정합, 그리고 `gen:api` 재생성 불변.
6. **스태일/접근성 보조**: `styles.css` `page-enter`·`prefers-reduced-motion`.
7. **정량 주장 재현**: 22 passed / build PASS / OpenAPI 재생성 무변 / `git diff --check` clean.

## Methodology

정본을 “읽고” 구현을 “읽는” 검증이 아니라, 각 표면을 직접 실행·재계산했다. 사용한 명령(전부 repo root 또는 `frontend/`에서):

- 회귀: `cd frontend && npm test` (vitest run, jsdom).
- 빌드/타입: `cd frontend && npm run build` (`tsc --noEmit && vite build`).
- OpenAPI 타입 재생성 불변: `cp frontend/src/api/schema.d.ts /tmp/schema_committed.d.ts && cd frontend && npm run gen:api && cd .. && diff /tmp/schema_committed.d.ts frontend/src/api/schema.d.ts` → 복원.
- 백엔드 무변: `git diff --stat -- services/ tests/ scripts/ docker-compose.yml`.
- 코드 계약 정합: `grep -nE '@app\.(get|post|...)\(' services/application/app/main.py | grep -iE 'project|draft'` 와 `client.ts` 호출 URL 대조; `schema.d.ts` payload 필드와 컴포넌트 소비 필드 대조.
- 종속성 실재: `package-lock.json` `node_modules/react-router` resolved 버전 확인.
- 워크카드: `git diff --check`.

**라이브 관통(in-memory application + Vite 실 API smoke)은 본 검증에서 독립 재실행하지 않았다.** 그 대신 (a) 회귀가 fetch URL·method·body·응답 소비를 정확히 pin 하고, (b) 백엔드 endpoint·오류 코드를 소스에서 직접 확인해 프론트 테스트의 mock(예: 409 “project is archived”)이 실제 계약과 일치함을 증명했다. 라이브 smoke은 검증자가 아닌 작업자의 routine self-check 기록(work_log Task 4 Verification)으로만 존재하며, 이 검증은 그 위에 단위·빌드·소스 단위의 독립 증거를 더한다.

## Boundary matrix (lock list — 빈 셀 없음)

브리프 §4의 계약 요구 분기를 1차 소스에서 뽑고 각각을 named regression test로 추적했다. 모든 행이 매핑되며, under-strict(버그 재도입 시 실패)·over-strict(정상 케이스를 잘못 막으면 실패) 양방향을 명시.

| # | 계약 요구 분기 (브리프 §4 / SoT v1.6.96) | 잠근 테스트 (file: 행) | 방향 |
|---|---|---|---|
| 1 | `/` = 프로젝트 목록/생성 유지 | `App.test.tsx:26` root route → “프로젝트” heading; `ProjectList.test.tsx:36` 목록 렌더 | under |
| 2 | 프로젝트 이름 → `/projects/:projectId` 진입 링크 | `ProjectList.test.tsx:50` `link href="/projects/p1"` (exact) | under+over(절대 URL 아님) |
| 3 | 단일 origin `/api` 경로 (CORS 미개방 전제) | `ProjectList.test.tsx:58` fetch 첫 인자 정확히 `/api/projects` | over-strict |
| 4 | `/projects/:projectId` = 선택 프로젝트 이름 + 돌아가기 | `DraftList.test.tsx:39` heading “겨울 이야기”; `App.test.tsx:38` direct address | under |
| 5 | project isolation — 경로의 projectId로만 조회 | `DraftList.test.tsx:60` fetch calls = `/api/projects/p1`, `/api/projects/p1/drafts` (exact) | under+over |
| 6 | 빈 원고 상태 | `DraftList.test.tsx:66` “아직 원고가 없습니다” | under |
| 7 | 원고 생성 → **서버 목록 재조회**(낙관적 패치 아님) | `DraftList.test.tsx:78` fetch 4회(GET×2, POST, GET 재조회) + 새 항목 렌더 | under |
| 8 | trim 후 전송 (과교정 방지) | `DraftList.test.tsx:129` `"  첫 장면  "` → body `{title:"첫 장면"}` | over-strict |
| 9 | 공백-only 미전송 | `DraftList.test.tsx:124` whitespace → button disabled, fetch 2회 | under |
| 10 | in-flight 중복 생성 방지 (submit-level guard) | `DraftList.test.tsx:136` `fireEvent.submit`×2 → POST 1회 (disabled 우회) | under |
| 11 | 보관 프로젝트 read-only — form 숨김 + 원고는 표시 | `DraftList.test.tsx:194` form 부재 + “남은 원고” 표시 + fetch 2회 | over-strict(정상 프로젝트는 form 표시) |
| 12 | direct URL(deep-link) 진입 | `DraftList.test.tsx:66` + `App.test.tsx:38` | under |
| 13 | 뒤로가기(링크 네비게이션) | `DraftList.test.tsx:244` 링크 클릭 → “프로젝트 홈” | under |
| 14 | 알 수 없는 route → shell 안 404 | `App.test.tsx:59` heading + link `href="/"` | under |
| 15 | 원고 목록 조회 실패 → 오류 노출(타 프로젝트 누출 없음) | `DraftList.test.tsx:214` alert “404: …”, 드래프트 미렌더 | under |
| 16 | 생성 실패 → 오류 + 제목 보존(재시도) | `DraftList.test.tsx:226` alert “409: project is archived” + 입력값 보존 | over-strict |

빈 셀 없음. 모든 계약 요구 분기가 named test로 trace된다.

## Findings

### 1. 정본 계약(소비 면) — PASS

- SoT v1.6.96 버전 로그 행(`system-contract-sot.md:36`)이 route spine `/`·`/projects/:projectId`, “Data/Framework mode·loader/action 미도입”, “direct URL·뒤로가기·SPA fallback”, “생성 후 서버 재조회”, “공백-only·in-flight 이중 제출 방지”, “보관 프로젝트 read-only”, “`react-router@8.2.0`(React/DOM `^19.2.7`)”, “백엔드 무변”을 서술한다 — 구현과 1:1.
- 본문 route spine 서술(`system-contract-sot.md` HANDOFF 연계 `:9`,`:11`)도 동일.
- 브리프 §4가 5개 항목(루트 유지·상세·API client·회귀·editor는 다음)으로 lock list를 명시했고, 구현이 그 경계를 넘지 않는다(editor/save/version/export 미구현 = 다음 slice, 브리프 §4.5·Deferred와 일치).
- 계약 내부 모순(버전 로그 ↔ 본문 ↔ 브리프) 없음.

### 2. 백엔드 계약(공급 면) — PASS

프론트가 호출하는 5 endpoint가 실제 존재하고 전부 `response_model` 부착(v1.6.95 척추 조임):

| 프론트 호출 (`client.ts`) | 백엔드 (`main.py`) | response_model | 오류 코드 |
|---|---|---|---|
| `GET /projects` (`listProjects`) | `:1427` | `ProjectListResponse` | — |
| `POST /projects` (`createProject`) | `:1422` | `ProjectPayload` | — |
| `GET /projects/{id}` (`getProject`, 신규) | `:1431` | `ProjectPayload` | NotFound→404 (`:1436`) |
| `GET /projects/{id}/drafts` (`listDrafts`, 신규) | `:1494` | `DraftListResponse` | NotFound→404 (`:1499`) |
| `POST /projects/{id}/drafts` (`createDraft`, 신규) | `:1597` | `DraftPayload` | NotFound→404 (`:1603`), **Archived→409 (`:1605`)** |

- **핵심 교차검증**: `DraftList.test.tsx:226`이 생성 실패를 mock한 값 `409 / "project is archived"`는 백엔드 `create_draft`의 실제 `Archived→HTTPException(409)`(`main.py:1605-1606`)와 **정확히 일치**한다. 프론트 테스트가 계약 위반이 아니라 실제 계약을 반영함을 증명.
- project isolation: `list_drafts`/`create_draft`/`get_project` 모두 경로의 `project_id`로 core_sot를 scope한다(`:1434`,`:1497`,`:1602`). 프론트는 URL의 projectId만 전달하므로 타 프로젝트 누출 경로 없음.

### 3. 백엔드 무변 — PASS

`git diff --stat -- services/ tests/ scripts/ docker-compose.yml` → **빈 출력**(0건). SoT “백엔드 endpoint/model/계약은 무변” 주장 독립 확인.

### 4. 구현 코드 — PASS

- `App.tsx:13-26` — `<Routes>` 로 `/`·`/projects/:projectId`·`*`(404 shell) 선언. `*` element는 shell 안에 “이 작업 공간은 없습니다.” + `/` 링크. Data mode 아님(선언적 `<Route>` only).
- `main.tsx:14` — `<BrowserRouter>`로 `<App/>` 감쌈. (테스트는 `<MemoryRouter>` 사용 — 표준 패턴.)
- `DraftList.tsx` — `useParams` projectId로 `getProject`+`listDrafts` 병렬 조회(`:38` `Promise.all`), `active` cleanup 플래그(`:36`,`:58`)로 unmount race 방지. `submit` 가드(`:66`) `projectId===undefined || trimmed==="" || saving || project?.archived` 4중. 보관 시 form 숨김(`:98-101`) + 원고는 표시. 생성 후 `loadDrafts()` 서버 재조회(`:74`).
- `ProjectList.tsx:89-93` — 프로젝트 이름이 `<Link to={`/projects/${project.id}`}>`.
- `client.ts:63-79` — `getProject`/`listDrafts`/`createDraft` 추가, 전부 생성 타입 소비(`Project`/`Draft`/`DraftListResponse`/`CreateDraftRequest`). 손선언 타입 없음(v1.6.95 H1로 제거됨).

### 5. 회귀 테스트 — PASS (코드 감사 포함)

`npm test` → **22 passed / 3 files**(DraftList 9, ProjectList 10, App 3). 작업자 주장과 정확히 일치.

CLAUDE.md “테스트 코드는 감사 대상” 기준으로 각 신규/변경 테스트를 읽었다:
- (a) assertion이 계약을 pin — 예: `DraftList.test.tsx:60`은 fetch URL 순서·경로를 exact로 검사해 project isolation을 잠그고, `:99-103`은 POST URL·method·body를 검사해 생성 계약을 잠근다.
- (b) under-strict 존재 — in-flight 테스트(`:136`)는 `fireEvent.submit`로 disabled 버튼을 **우회**해 `submit()` 내부 `saving` 가드를 직접 pin(버튼 disabled만 검사하면 가드 제거를 못 잡음 — v1.6.94 H6 패턴 정확히 계승).
- (c) over-strict 존재 — trim(`:129`), 단일 origin 경로(`ProjectList.test.tsx:66`), 보관 read-only(`:194` 정상 프로젝트는 form 표시), 제목 보존(`:241`) 양방향.
- (d) 경계값 — trim은 빈/공백/padding/내부공백 4가지를 다룬다(`:106-134`).
- (e) 공개 표면 — envelope·payload 필드를 검사하고 내부 헬퍼가 아닌 렌더 결과·fetch 인터페이스를 단언.

### 6. 공개 envelope/스키마 동기화 — PASS

- `npm run gen:api` 재실행 → 재생성 `schema.d.ts`와 커밋본 `diff` **IDENTICAL**(0 byte 차이). “OpenAPI 타입 재생성 변경 없음” 독립 재현. 백엔드 무변이므로 이는 논리적으로 필연이지만, 재생성이 실제로 동작함(백엔드 import 가능)도 확인.
- payload 필드 ↔ 코드 소비 정합: `DraftPayload{archived,id,project_id,title}`(`schema.d.ts:809`)를 `DraftList`는 `draft.id/title/archived`로, `ProjectPayload{archived,id,name}`(`:885`)를 `project.name/archived`로 소비. `CreateDraftRequest{title}`에 `{title: trimmed}` 전송. `tsc --noEmit` 통과가 이 소비를 교차검증(필드 누락 시 컴파일 실패).

### 7. 정량 주장·스타일 — PASS

- build: `npm run build` → 89 modules transformed, 2.31s, exit 0. 작업자 주장(89 modules, CSS 4.53 kB/gzip 1.62, JS 234.46 kB/gzip 75.18)과 동일.
- `react-router@8.2.0` 실재: `package-lock.json` `node_modules/react-router` `version: 8.2.0`, resolved `registry.npmjs.org/react-router/-/react-router-8.2.0.tgz`. import 경로 `react-router`(v7+ 통합 패키지)가 `BrowserRouter`/`Routes`/`Route`/`Link`/`useParams`/`MemoryRouter`를 정상 export(테스트+빌드 통과로 증명).
- `styles.css:279-292` `page-enter` 애니메이션, `:319-328` `@media (prefers-reduced-motion: reduce)`로 animation/transition을 0.01ms로 무효화 — 브리프 §3 “prefers-reduced-motion에서는 제거한다” 이행.
- `git diff --check` → clean(exit 0).

## Issues / Risks

### Blocking (계약 의무 위반)

**없음.** boundary matrix에 빈 셀이 없고, 계약 요구 분기 전부가 양방향 named test로 잠겼으며, 백엔드 무변·타입 동기화·단일 origin 전제가 모두 1차 소스로 확인됐다.

### Hardening recommendations (비차단, 현 spec이 요구하지 않는 보강)

- **H1 — direct URL로 존재하지 않는 프로젝트(예: `/projects/nonexistent`)의 명시적 회귀 부재.** `getProject` 404 → `Promise.all` reject → 일반 error alert + (항상 렌더되는) 돌아가기 링크. 동작은 정상(브리프 §3 follow-up이 “404 project 표시는 editor slice에서 확장”으로 미뤄둔 항목)이지만, 이 경로를 pin하는 테스트가 없다. `DraftList.test.tsx:214`(유효 프로젝트 + drafts 404)가 유사하지만 `getProject` 404를 직접 다루지 않는다. 가치는 낮다(일반 error 경로가 이미 검사됨).
- **H2 — 브리프 §3 “새 항목 강조” 미구현.** §3 interaction thesis가 “생성 성공 후 목록 재조회와 **새 항목 강조**”를 언급하나, 구현은 서버 재조회까지만 하고 새 원고를 시각적으로 강조하지 않는다. **이것은 결함이 아니다** — §3는 “UI 기준(routing 선택과 무관)”의 aspirational thesis이고, lock list(§4)와 SoT v1.6.96 행은 “재조회”만 요구한다. 다만 의도적 skip임을 다음 UI slice에서 확인할 사항으로 남긴다(조용한 누락으로 오해되지 않도록).
- **H3 — draft 생성의 submit()-level 공백 가드가 disabled 버튼 뒤에서 독립 pin 안 됨.** in-flight 가드는 `fireEvent.submit`으로 submit-level에서 pin되지만(`DraftList.test.tsx:136`), 공백-only는 disabled 버튼에 의존해 검사한다(`:124`). 요구(공백 미전송)는 여전히 잠겨 있다 — 두 층(disabled + `submit()` 내 `trimmed===""`)을 **모두** 제거해야 실패하므로. 대칭을 위해 `fireEvent.submit` 공백 케이스를 추가할 수 있으나 비차단.
- **H4 — 같은 컴포넌트 route 전환 시 `page-enter` 재실행 안 됨.** `/projects/p1` → `/projects/p2`는 둘 다 `DraftList`를 mount해 React가 reconcile(재 mount 아님)하므로 CSS animation이 재생되지 않는다. §3 “route 전환 시 등장”과 부분 불일치. 단, lock된 네비게이션 회귀(뒤로가기/deep-link)는 컴포넌트가 교체되므로 정상 동작한다. 비차단 polish.

### Post-verification disposition (Codex, owner-requested follow-up)

- **H3 반영**: 공백-only 테스트가 disabled 버튼을 넘어 `fireEvent.submit(form)`을 직접 호출하도록 보강했다. `submit()`의 `trimmed === ""` 가드를 제거하는 mutation에서 이 테스트가 `fetch 2회 기대 / 3회 실제`로 단독 실패함을 재현한 뒤 가드를 복원했다. 테스트 수는 22개로 동일하다.
- **H2 명확화**: 브리프의 interaction thesis를 현재 lock과 맞췄다. 이번 slice는 서버 재조회까지만 소유하며, 새 항목 강조는 실제 사용에서 재조회 후 위치 상실이 관측될 때 추가한다. 구현을 늘리지 않았다.
- **H1 보류 유지**: 존재하지 않는 project의 전용 404 UX는 브리프가 editor slice로 넘긴 경계이며 일반 error 회귀가 이미 있어 지금 중복 테스트를 추가하지 않는다.
- **H4 보류 유지**: 같은 컴포넌트 간 route animation 재실행은 기능 계약이 아닌 polish다. key/remount를 강제하면 입력·조회 state 수명도 함께 바뀌므로 실제 UX 문제가 관측되기 전에는 건드리지 않는다.

이 후속은 위 독립 검증의 PASS 판정을 변경하지 않는다. 구현 후속의 상세 명령·결과는 `docs/daily_logs/2026-07-16/work_log.md` Task 5에 기록한다.

## Verdict

**PASS (조건 없음).**

이유(load-bearing):
1. boundary matrix 16행에 빈 셀 없음 — 브리프 §4의 모든 계약 요구 분기가 양방향(under/over-strict) named regression으로 잠겼다.
2. 백엔드 무변(git diff 0건) + 프론트 호출 5 endpoint가 실제 존재하며 전부 `response_model` 부착 + 프론트 테스트의 409 mock이 백엔드 실제 `Archived→409`와 정합.
3. 정량 주장(22 passed / build / gen:api IDENTICAL / diff --check clean) 전부 독립 재현.
4. 타입 동기화: 생성 `schema.d.ts` payload 필드 ↔ 컴포넌트 소비 정합, `tsc` 통과로 교차검증.

비차단 hardening 4건(H1~H4)은 현 spec이 요구하지 않는 보강이며 판정에 영향을 주지 않는다.

## Outstanding items

- **커밋 대기**: 본 슬라이스 변경은 working tree에 uncommitted. 오너 승인 전 커밋하지 않음(작업자도 커밋하지 않았음을 확인).
- **라이브 관통 smoke 미재실행**: 본 검증은 단위·빌드·소스 단위 증거로 라이브 smoke을 대체함(방법론에 명시). 오너가 라이브 재현을 원하면 in-memory application + Vite 실 API 경로를 별도로 실행 가능(work_log Task 4 Verification에 절차 있음).
- **다음 slice**: `/projects/:projectId/drafts/:draftId` editor(평문 textarea → 명시적 save/version mint → version 목록 → txt/markdown export). 이 slice의 route spine이 그 기반이 된다.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
# 회귀
(cd frontend && npm test)                                   # 22 passed / 3 files
# 빌드/타입
(cd frontend && npm run build)                              # tsc + vite build, exit 0
# OpenAPI 재생성 불변
cp frontend/src/api/schema.d.ts /tmp/schema_committed.d.ts
(cd frontend && npm run gen:api) && diff /tmp/schema_committed.d.ts frontend/src/api/schema.d.ts  # IDENTICAL
cp /tmp/schema_committed.d.ts frontend/src/api/schema.d.ts  # 복원
# 백엔드 무변
git diff --stat -- services/ tests/ scripts/ docker-compose.yml   # 빈 출력
# 코드 계약 정합
grep -nE '@app\.(get|post|patch|delete)\(' services/application/app/main.py | grep -iE 'project|draft'
# 정리
git diff --check                                             # clean
```
