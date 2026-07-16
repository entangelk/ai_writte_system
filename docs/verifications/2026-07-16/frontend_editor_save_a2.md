# 독립 검증 — Frontend editor/save A2 슬라이스 (SoT v1.6.99)

## Subject metadata

- **날짜**: 2026-07-16
- **요청자**: 오너 (“작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래? A2 구현을 완료했습니다.”)
- **검증자**: 독립 검증 AI (Claude Code)
- **대상 슬라이스/산출물**: Product shell A2 — `/projects/:projectId/drafts/:draftId` editor 안에 (1) 최신순 version history 렌더, (2) 과거 version 선택 → snapshot 본문 표시, (3) dirty 상태 version 전환 `window.confirm` 확인/취소, (4) selection 조회 실패 시 현재 본문·선택 보존, (5) 과거 version 편집 → Save → append-only 새 latest mint·선택(기존 version 보존), (6) 선택 version txt/Markdown Blob export(서버 body·content_type·filename 그대로). D2=A·D3=A 기존 계약을 그대로 따름(별도 결정 브리프 없음).
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.6.99(버전 로그 행 36), `docs/plans/frontend-editor-save-decisions.md` D2=A implementation locks(72-78행) + “A2 후속 범위”(122-128행) + backend export 계약(21-26행), `product-shell.md`, `product-readiness-backlog.md` ARCH-1 정의(37행).
- **검증 대상 작업 출처**: working tree, uncommitted. 변경 `frontend/src/drafts/DraftEditor.tsx`·`DraftEditor.test.tsx`·`api/client.ts`·`styles.css` + 문서(SoT·product-shell·readiness backlog·decisions·CHANGELOG·HANDOFF·work_log). 백엔드 `services/`·`tests/`·`scripts/`·`docker-compose*.yml` diff 0(작업자 주장이며 검증에서 재확인).

## Scope

결정 브리프의 **A2 lock list**(122-128행)와 D2=A implementation locks(72-78행)가 명시한 표면 전부와 그 전제(백엔드 무변·기존 version/export 공급 계약 정합)를 1차 소스에서 재도출한다.

1. **정본 계약(소비 면)**: SoT v1.6.99 행, 브리프 D2=A locks + A2 후속 범위 5항, follow-up의 ARCH-1 점검 항.
2. **백엔드 계약(공급 면)**: A2가 새로 소비하는 `/versions/{version_id}/export` endpoint 실제 존재·`response_model`·`content_type`/`filename` literal, 그리고 export body가 snapshot `raw_text` verbatim인지. 기존 `listDraftVersions`/`getDraftVersion`/`saveDraft`는 A1에서 이미 소비.
3. **구현 코드**: `DraftEditor.tsx`(`selectVersion`·`download`·save의 append-only history 갱신·선택 중 readOnly/disabled race guard), `client.ts`(`exportDraftVersion` 추가).
4. **회귀 테스트**: `DraftEditor.test.tsx` A2 신규 7케이스(newest-first/선택·dirty cancel/confirm·selection 404 보존·과거→새 latest·txt/Markdown export parametrized 2·export 404 무다운로드) + A1 기존.
5. **스키마 동기화**: `DraftVersionExportResponse` 타입 실재 여부, `gen:api` 재생성 불변.
6. **정량 주장 재현**: red-first 7 fail/16 pass · focused 23/1 · 전체 46/4 · build 90 modules · schema IDENTICAL · `git diff --check` clean · 백엔드 diff 0.
7. **계약 자기일관성**: SoT·decisions·product-shell·readiness backlog·CHANGELOG·HANDOFF 간 literal/버전/수치 충돌.

## Methodology

정본·구현·작업자 주장을 “읽어서” 맞다고 치지 않고, 각 표면을 실행·재계산·대조했다.

- **boundary matrix 우선**: 계약(D2=A locks + A2 후속 범위)을 먼저 읽어 should-fire / should-NOT-fire 분기를 나열한 뒤, 각 분기를 코드와 테스트에 추적. 코드부터 열어 맞추지 않았다.
- **회귀**: `cd frontend && npx vitest run src/drafts/DraftEditor.test.tsx --reporter=dot`(focused) 및 `npm test -- --reporter=dot`(전체). vitest 3.2.7, jsdom.
- **red-first 독립 재현**: `git stash push -- frontend/src/drafts/DraftEditor.tsx`로 컴포넌트만 HEAD(A1)로 되돌리고(client.ts·test는 A2 유지 → import 해석 유지) focused 실행 후 `git stash pop`으로 복원. 작업자 주장 “7 fail / 16 pass”를 그대로 재현하는지 확인.
- **빌드/타입**: `cd frontend && npm run build`(`tsc --noEmit && vite build`).
- **OpenAPI 재생성 불변**: `npm run gen:api` 후 `git diff --stat src/api/schema.d.ts`(빈) + `git status --porcelain openapi.json src/api/schema.d.ts`.
- **백엔드 무변**: `git diff --stat`에서 `services/`·`tests/`·`scripts/`·`docker-compose*.yml` 항 없음 확인. 단, A2가 처음 소비하는 export endpoint의 공급 계약(content_type/filename literal)은 이 검증에서 처음 대조하므로 `core_sot/service.py`·`main.py`를 직접 읽어 프론트 기대와 정합하는지 확인.
- **문서 일관성**: 각 문서 diff를 읽고 버전 포인터·수치·ARCH-1 판정이 서로 모순하지 않는지 대조.

## Findings

### 1. 정본 계약(소비 면)

A2 후속 범위(122-128행) 5항과 D2=A locks(72-78행)를 그대로 인용해 boundary matrix를 구축했다. 모든 계약-required 분기가 아래 표처럼 코드와 테스트에 추적된다(빈 셀 없음).

| # | 계약 분기(should / should-NOT) | 구현(코드) | 회귀 테스트 | 비고 |
|---|---|---|---|---|
| 1 | version history 최신순 렌더(should) | `DraftEditor.tsx:325-326` desc sort | `lists versions newest-first`(test:377) | mock `[v1,v3]` asc → assert `[v3,v1]` desc, 양방향 |
| 2 | 과거 version 선택 → snapshot 본문(should) | `selectVersion` `DraftEditor.tsx:187-191` | test:396-400 | URL `/versions/v1`, 본문·`현재 version 1` |
| 3 | 동일 version/in-flight 재선택 차단(NOT) | guard `DraftEditor.tsx:171-173` | (방어적, 암시적) | guard 존재 확인 |
| 4 | dirty 전환 → confirm UI(should) | `DraftEditor.tsx:177-182` | `cancels a dirty version switch`(test:403) | cancel→fetch 0·confirm→로드 |
| 5 | 취소 시 fetch/state 무변(NOT) | early return `DraftEditor.tsx:182` | test:418-420(fetch count 4) | under-strict |
| 6 | 조회 실패 시 본문·선택 보존(NOT) | catch `DraftEditor.tsx:195-196` | `preserves current text when confirmed load fails`(test:427) | 본문 + `aria-current` 보존, 양방향 |
| 7 | 과거→Save→append-only 새 latest + 선택(should) | `submit` `DraftEditor.tsx:142-147` | `selects a newly saved version without mutating historical`(test:478) | v4 선택 + v1/v3 유지 |
| 8 | replay id 중복 추가 X(NOT) | filter `DraftEditor.tsx:144` | 구조적 커버 | 동일 id filter+prepend |
| 9 | export Blob download(should) | `download` `DraftEditor.tsx:222-231` | `downloads the selected version`(test:522, parametrized 2) | URL·blob.type·body·click·download·revoke |
| 10 | filename·content_type·body 서버 envelope 그대로(should) | `DraftEditor.tsx:222-227` | test:545-553 | ⚠ 검증 당시 fixture fidelity는 후속 H1에서 폐쇄 |
| 11 | txt/markdown 모두(should) | 버튼 2 + `?format=` `client.ts:126` | parametrized 2케이스 | body 같고 MIME/filename 상이 |
| 12 | export 404 → 무다운로드(NOT) | catch `DraftEditor.tsx:233-234` | `surfaces export failure`(test:516) | `createObjectURL` 미호출 |
| 13 | object URL 해제(should) | `revokeObjectURL` `DraftEditor.tsx:231` | test:513 | `blob:download` 해제 |
| 14 | 선택 중 readOnly/버튼 비활성 race guard(NOT) | `readOnly`/disabled `DraftEditor.tsx:278,288,332` | `locks editing only while a version selection is in flight`(test:448) | 독립 검증 뒤 Hardening H2로 추가 |
| 15 | ARCH-1 미발화(backend 무변) | 백엔드 diff 0 | `git status` | Findings §5 |

독립 검증 시에도 계약-required 분기 1-13, 15는 전부 명명된 회귀 또는 구조적 사실로 추적되어 빈 셀이 없었다. 당시 spec-silent hardening이던 14번도 후속 H2 회귀로 잠겼다.

### 2. 백엔드 계약(공급 면)

A2가 처음 소비하는 export endpoint와 기존 version endpoint를 1차 소스에서 확인.

- **export route 실재**: `main.py:1563-1595`에 `GET /projects/{project_id}/drafts/{draft_id}/versions/{version_id}/export`, `response_model=DraftVersionExportResponse`(`main.py:987`). 400(UnsupportedExportFormat)/404(NotFound) 매핑 존재. 프론트 `exportDraftVersion`(`client.ts:119-128`) 경로·query 정합.
- **content_type literal(핵심)**: `core_sot/service.py:56-60`의 `_EXPORT_FORMATS`가 `txt` → `"text/plain; charset=utf-8"`, `markdown` → `"text/markdown; charset=utf-8"`(둘 다 **charset 파라미터 포함**). 프론트는 `new Blob([exported.body], { type: exported.content_type })`(`DraftEditor.tsx:223`)로 이 값을 verbatim 전달 → 브라우저 Blob type도 charset 포함. 기능적 정상(다운로드 동작).
- **filename literal**: `service.py:288` `f"{draft_id}-v{version.version_number}.{extension}"` → 예: `"d1-v3.txt"`/`"d1-v3.md"`. 프론트는 `anchor.download = exported.filename`(`DraftEditor.tsx:227`)로 verbatim 사용.
- **body verbatim**: `service.py:290` `body=detail.snapshot.raw_text`. 프론트는 `exported.body`를 Blob에 그대로(`DraftEditor.tsx:223`). AI metadata 주입 없음(SoT v1.6.99 행 명시대로).
- **`DraftVersionExportResponse` 스키마 실재**: `schema.d.ts:826-846`에 `body`·`content_type`·`filename`·`format`·`content_hash` 등 필드 존재. 프론트 필드 접근(`exported.body`/`.content_type`/`.filename`) 전부 정합. `gen:api` 재생성 diff 없음(작업자 주장 “schema 동일” 확인).
- 백엔드·Core SOT 코드 diff 0 — 작업자 주장 확인. export endpoint는 이미 존재하던 척추 endpoint를 소비만 한다.

### 3. 구현 코드(DraftEditor.tsx·client.ts)

- **dirty confirm 제어**: `selectVersion`(`DraftEditor.tsx:167-201`)는 동일 선택·save/selection in-flight를 guard(171-173행)한 뒤, dirty면 `window.confirm`(177-182행). **취소는 fetch 전 early return**이라 state/fetch 무변(D2=A lock line 77 정합). 확인 시 `getDraftVersion` 후 **성공한 경우에만** `setRawText`/`setBaseline`/`setSelectedVersionId`/`setVersionNumber`를 함께 교체(188-191행, 원자적). 실패 시 `setError`만(195-196행)으로 본문·선택 보존(D2=A lock line 78·A2 line 127 정합).
- **append-only save**: `submit`의 `setVersions((current) => [savedVersion, ...current.filter((version) => version.id !== savedVersion.id)])`(`DraftEditor.tsx:142-145`)는 신규 id는 prepend, replay(동일 id)는 filter로 중복 제거. 렌더가 `version_number` desc로 재정렬(325-326행)하므로 내부 배열 순서 무관. 기존 version 미변경(D2=A lock line 76 정합).
- **export download**: `download`(`DraftEditor.tsx:203-239`)는 `selectedVersionId === null`·`exportingRef` guard 후, 서버 envelope으로 Blob 생성·anchor click·`revokeObjectURL`(222-231행). 실패 시 catch가 `setError`만(233-234행), Blob/anchor 생성 없음.
- **race guard**: 선택 fetch 중 `readOnly={readOnly || selecting}`(278행) + Save/버전 버튼 `disabled={... || selecting}`(288,332행). A1 B1(저장 중 타이핑 silent loss)과 동형의 경쟁을 막는 예방 조치. 단 **이 guard에 직접 회귀 테스트가 없다**(H2).
- **`exportDraftVersion` client**(`client.ts:119-128`): 생성 타입 `DraftVersionExport` 반환, 경로·query 정합. 손선언 0.

### 4. 회귀 테스트(DraftEditor.test.tsx)

A2 신규 7케이스를 계약 분기에 매핑(§1 표). 각 테스트의 guard 방향을 읽어 확인:

- **`lists versions newest-first`(test:377)**: mock을 asc `[v1,v3]`로 주고 렌더가 desc `[v3,v1]`임을 assert → 정렬 방향을 양방향으로 pin. `aria-current`로 선택 표시 확인.
- **`cancels a dirty version switch`(test:403)**: confirm false→fetch count 4(무변)·본문 보존, confirm true→`첫 원고` 로드. under-strict(cancel 무력화 시 fetch 5로 fail) 충족. 비-dirty 전환은 `lists versions`(test:396)가 confirm 없이 로드됨을 확인해 over-strict 방향 커버.
- **`preserves the current text when confirmed load fails`(test:427)**: 404 시 본문(`셋째 원고 수정`) + `aria-current` v3 보존. 양방향.
- **`selects a newly saved version without mutating historical`(test:478)**: v1 선택→편집→Save→`version 4 저장됨` + `aria-current` v4 + v1/v3 버튼 존재. append-only + 새 버전 선택을 양방향으로 pin.
- **`downloads the selected version`(test:522, parametrized txt/markdown)**: URL·`blob.type`·blob body(`FileReader.readAsText`)·click 1회·`anchor.download` filename·`revokeObjectURL` 전부 검증. 두 포맷 모두. **검증 당시 fixture 값의 실제 backend envelope 차이는 후속 H1에서 폐쇄했다.**
- **`surfaces export failure`(test:556)**: 404 시 `createObjectURL` 미호출 + 본문 보존. 무다운로드 양방향.

**테스트 품질 단점(검증 당시)**: `expect(version4.version_number).toBe(4)`는 **지역 상수 자체를 검증**하는 무의미 단언이었다(contract-relevant “version 4”는 현재 test:498-501 UI 텍스트·`aria-current`로 pin됨). 후속 H3에서 상수와 단언을 제거했다.

### 5. 정량 주장 재현

| 항목 | 작업자 주장 | 독립 재현 결과 |
|---|---|---|
| red-first(component→A1) | 7 fail / 16 pass | **7 failed \| 16 passed (23)** — 정확 일치 |
| focused DraftEditor | 23 passed / 1 file | **23 passed / 1 file** — 일치 |
| 전체 프론트 | 46 passed / 4 files | **46 passed / 4 files** — 일치 |
| build | 90 modules, CSS 6.74kB(gzip 2.00), JS 240.55kB(gzip 76.88) | **정확 일치** |
| gen:api | schema.d.ts diff 없음 | **`git diff --stat src/api/schema.d.ts` 빈** — 일치 |
| 백엔드 diff | 0 | `services/`·`tests/`·`scripts/`·compose 항 없음 — 일치 |
| `git diff --check` | clean | **clean** — 일치 |

red-first는 컴포넌트만 A1으로 되돌려(클라이언트·테스트는 A2 유지해 import 해석 유지) 독립 재현했다. 작업자가 보고한 수치가 하나도 빈틈없이 재현됐다.

### 6. 계약 자기일관성

- SoT 헤더 `v1.6.99`(행 4)·버전 로그에 v1.6.99(행 36)와 v1.6.98(행 37, 보존) 공존 → 증분 정상.
- decisions doc 상태줄(행 7) “A2 완료(v1.6.99), Product shell A 종료”, 관련 정본 v1.6.99 → SoT·product-shell과 정합.
- product-shell.md “구현 진행”이 v1.6.99에서 A 기본 경로 완료, 상태 `Draft` 유지(전체 수용 기준 잔존) → 정합.
- HANDOFF `v1.6.99`(Approved), Current Status/Next Tasks/Verification/구조도 버전 포인터 전부 갱신, 프론트 수치 39→46(39+7=46 정합).
- readiness backlog A-체크포인트 note(행 47) “ARCH-1 Waiting 유지(미발화)” — ARCH-1 정의(행 37 “단순 프론트 조립만이면 미발화”)와 정합.
- **교차 모순 없음**. 정본이 이름·버전·수치에서 스스로와 충돌하지 않는다.

## Issues / Risks

### Blocking(계약 의무) — 없음

boundary matrix의 계약-required 분기 전부(§1 표 1-13, 15)가 명명된 회귀 테스트 또는 구조적 사실로 추적된다. 빈 셀 없음. D2=A locks·A2 후속 범위가 요구하는 literal(content_type verbatim 포함)이 코드에 불변으로 나타나며, under-strict/over-strict guard가 양방향으로 배치돼 있다. 정량 주장이 전부 독립 재현됐고, 백엔드·Core SOT 무변이 확인됐다.

### Hardening recommendations(비차단)

- **H1 — export fixture를 실제 백엔드 envelope에 정렬**: parametrized export 회귀(test:480-481, 495)의 fixture가 `content_type: "text/plain"`/`"text/markdown"`(charset 누락), `filename: "scene.txt"`/`"scene.md"`를 쓴다. 실제 백엔드는 `text/plain; charset=utf-8`/`text/markdown; charset=utf-8`(`service.py:58-59`), filename `d1-v3.txt`/`d1-v3.md`(`service.py:288`)를 생산한다. 프론트 코드는 verbatim pass-through로 **정확**하고, 테스트도 pass-through를 증명하므로 빈 셀은 아니다. 그러나 fixture가 charset 파라미터를 빼고 있어, 누군가 코드에 `.split(";")[0]` 식의 MIME 파라미터 제거를 넣어도 **현 테스트는 green을 유지**한다(실제로는 verbatim 위반이지만). A2 line 127 “filename/content-type/body가 서버 envelope과 일치하는 회귀”의 의도를 충분히 잠그려면 fixture를 실제 envelope 값으로 교체하라. CLAUDE.md “Fixture grounding / Smoke vs envelope claim”에 부합하는 보강.
- **H2 — selection race guard 전용 회귀 추가**: 작업자가 A1 B1(저장 중 타이핑 silent loss) 재발 방지용으로 추가한 `readOnly={readOnly || selecting}`(`DraftEditor.tsx:278`)·버튼 disabled(288,332행)에 대응하는 회귀가 없다. 이 guard가 제거돼도 현 suite는 green. D2/A2 locks가 “선택 fetch 중 read-only”를 명시적으로 열거하지 않으므로(spec-silent) 비차단이고, 프로젝트는 이미 A1 B1을 spec-silent hardening으로 수용한 선례이 있다. 단 **A1 B1과 동일한 실제 실패 모드**가 suite를 빠져나간 전례가 있으므로, 선택 fetch를 일으킨 뒤 resolve 전 `readOnly`/`aria-busy`와 Save·버전 버튼 disabled를 단언하는 양방향 회귀(guard 제거 시 fail)를 권장. A1 B1 closure 패턴과 동형.
- **H3 — test:476 무의미 단언 제거**: `expect(version4.version_number).toBe(4)`는 지역 상수 자체 검증이라 아무것도 pin하지 않는다. contract-relevant “version 4”는 이미 469·470행으로 pin돼 있어 안전하게 삭제 가능(가독성).
- **H4 — SoT v1.6.99 surfaces 보완(선택)**: 버전 로그 행의 surfaces가 `DraftEditor.tsx`·`.test.tsx`·decisions·work_log만 나열하고 `client.ts`(exportDraftVersion 추가)·`styles.css`(version panel 스타일)을 빠뜨린다. work_log는 client.ts를 언급하므로 비차단. surfaces를 완전히 나열하려면 두 파일 추가.
- **H5 — export↔selection 교차 잠금(선택, 양성)**: 버전 버튼이 `exporting`에 따라 disable되지 않고(332행 `saving || selecting`), export 버튼이 `selecting`에 따라 disable되지 않는다(305행 `exporting !== null`). 교차 동작은 각 함수가 call 시점의 id를 캡처해 양성이고 계약은 침묵하므로 비차단. 대칭성만 원하면 disable 조건 확장.

## Verdict

**PASS.**

이유:
1. **boundary matrix 빈 셀 없음** — D2=A implementation locks(72-78행)와 A2 후속 범위(122-128행)가 요구하는 should/should-NOT 분기 전부가 명명된 회귀 테스트로 추적된다(§1 표). 계약-required lock이 누락된 분기가 없다.
2. **정량 주장 전폭 재현** — red-first 7/16(정확)·focused 23/1·전체 46/4·build 90 modules(+ 정확한 byte)·gen:api IDENTICAL·`git diff --check` clean·백엔드 diff 0. 작업자 수치가 한 건도 빈틈없이 재현됐다.
3. **spec ↔ 구현 ↔ 테스트 정합** — 모든 literal(특히 export content_type/body/filename verbatim)이 코드에 불변으로 나타나고, 프론트가 처음 소비하는 export endpoint의 공급 계약이 1차 소스(`service.py`·`main.py`)에서 정합함을 확인했다.
4. **계약 자기일관** — SoT·decisions·product-shell·readiness backlog·CHANGELOG·HANDOFF 간 버전·수치·ARCH-1 판정 모순 없음.
5. **ARCH-1 미발화 판정 건전** — 백엔드 HTTP 표면 무변(순수 프론트 조립)이 정의(“단순 프론트 조립만이면 미발화”)대로다.

Hardening 5건(H1~H5)은 모두 **비차단**이다. H1은 기존 lock의 fixture 강화(실제 envelope 정렬), H2는 spec-silent race guard의 전용 회귀(프로젝트 선례상 spec-silent), H3~H5는 가독성/완전성/양성 대칭이다. 어느 것도 “계약-required 분기에 회귀가 없는 빈 셀”이 아니므로 조건부 합격 사유가 되지 않는다. 단, H1·H2는 이 슬라이스의 회귀망을 의미 있게 강화하므로 C 착수 전 반영을 권장한다.

## Outstanding items

- 독립 검증 시점에는 변경이 **working tree, uncommitted** 상태였다. 이후 오너가 아래 hardening 반영과 커밋을 승인했다.
- compose는 worker만 실행 중이어서 **live browser smoke는 미실행**(작업자가 unit/build/OpenAPI 증거로 대체). 이 검증도 동일하게 unit 수준에서 재현했다. export Blob 다운로드·dirty confirm의 실제 브라우저 동작(특히 `text/plain; charset=utf-8` MIME의 브라우저 처리)은 live browser smoke로 한 번 더 확인하면 H1 보강과 함께 완전하다.
- 다음 작업은 C(Writing 작업공간) 착수 브리프이며, 본 슬라이스가 그를 차단하지 않는다.

## Post-verification disposition

원 독립 판정 **PASS**와 그 근거는 그대로 보존한다. 오너의 후속 지시에 따라 다음 hardening을 처리했다.

- **H1 반영**: export parametrized fixture를 실제 backend envelope인 `d1-v3.txt`/`d1-v3.md`, `text/plain; charset=utf-8`/`text/markdown; charset=utf-8`로 정렬했다. body·전체 MIME·filename verbatim을 함께 잠근다.
- **H2 반영**: selection detail fetch를 보류한 채 textarea `readOnly`·`aria-busy=true`, Save/history 버튼 disabled를 확인하고, 성공 응답 뒤 잠금이 해제되는 전용 양방향 회귀를 추가했다.
- **H3 반영**: 지역 상수 자체를 검증하던 `expect(version4.version_number).toBe(4)`를 제거했다. 사용자 표면 notice와 `aria-current` 단언은 유지된다.
- **H4 반영**: SoT v1.6.99 surface 목록에 `frontend/src/api/client.ts`와 `frontend/src/styles.css`를 추가했다.
- **H5 유지**: export와 selection은 호출 시점의 version id를 캡처하므로 현재 교차 동작은 안전하다. 상호 disabled는 계약 없이 기능을 줄이는 변경이라 적용하지 않았다.

후속 기준선은 focused `DraftEditor` **24 passed / 1 file**, 전체 프론트 **47 passed / 4 files**다. backend/Core SOT 구현은 계속 무변이다.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system/frontend

# focused + 전체 회귀
npx vitest run src/drafts/DraftEditor.test.tsx --reporter=dot   # 24 passed / 1 file
npm test -- --reporter=dot                                       # 47 passed / 4 files

# 빌드 + OpenAPI 재생성 불변
npm run build                                                    # 90 modules, CSS 6.74kB, JS 240.55kB
npm run gen:api && git diff --stat src/api/schema.d.ts           # (빈 = IDENTICAL)

# red-first 독립 재현: 컴포넌트만 A1/HEAD로, 클라이언트·테스트는 A2 유지
cd /mnt/d/devel/에베베/ai_writte_system
git stash push -- frontend/src/drafts/DraftEditor.tsx
cd frontend && npx vitest run src/drafts/DraftEditor.test.tsx --reporter=dot   # 7 failed | 16 passed
cd /mnt/d/devel/에베베/ai_writte_system && git stash pop          # A2 컴포넌트 복원

# 백엔드 무변 + clean
git diff --stat -- services/ tests/ scripts/ docker-compose.yml docker-compose.llama.yml   # (빈)
git diff --check                                                  # clean

# export 공급 계약 대조(핵심)
grep -n "_EXPORT_FORMATS" services/application/app/core_sot/service.py              # charset 포함 MIME
sed -n '271,297p' services/application/app/core_sot/service.py                      # filename 형식·body verbatim
sed -n '1563,1595p' services/application/app/main.py                                 # export route + response_model
```
