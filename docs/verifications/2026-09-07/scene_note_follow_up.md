# 독립 검증 기록 — 장면 메모 후속(목록 행 수정 시각 · "더 보기")

## Subject metadata

- **일자**: 2026-09-07 · **요청자**: 오너("검증하고 의심하고 또 의심해줘") · **검증자**: 독립 검증 세션(구현 세션 24 와 다른 세션)
- **대상 슬라이스**: HANDOFF Next Tasks 4번(오너 결정 2026-09-06) — 커밋 `f46a462`(구현)·`9262f27`(MN-8 셀)·`50fa146`·`c7ab9e9`(기록). 소스 = main HEAD `c7ab9e9`, 트리 clean, origin보다 4커밋 선행(push 대기 — 주장과 일치).
- **정규 스펙**: [`system-contract-sot.md`](../../system-contract-sot.md) **v1.8.38** 리터럴 ⑩~⑫ + **v1.8.37 ②** 가 박아 둔 조건(*"절단 표시를 열려면 true/false 양방향 셀과 함께 연다"*) + v1.8.36 ①~⑨(상속, 이번에 건드린 분기) + 오너 결정 원문(`docs/daily_logs/2026-09-06/work_log.md:672`).

## Scope

★ = 가장 의심스러운 축.

1. ★ **무변 주장** — 백엔드·API 계약·`schema.d.ts` 무변(구현 보고의 근간).
2. ★ **v1.8.37 ② 조건 이행** — 양방향 셀이 조건이지 부록이 아님.
3. 구현 ↔ SoT ⑩~⑫ 리터럴 대응(단건 GET · 펼침≠선택 · 갱신 접힘 · aware 시각).
4. 신규 6셀의 경계 행렬(under-strict / over-strict).
5. 구현자 변이 표 MN-1~MN-8 의 정직성(3종 직접 재유도).
6. 전수·tsc 재실측 + 문서 색인 가드 실시(백엔드 미실행 판단 감사).
7. ★ **미확인 "1 failed / 457"** 정체 조사(작업자가 정체를 못 남긴 실행).

## Methodology

전수·변이 모두 **전량 파일 캡처**(`> file 2>&1; echo EXIT=$?`)로 돌리고 요약 라인(`Test Files`/`Tests`)을 판독했다. 변이는 매회 프리플라이트 `git status --short` 공백 확인 → Edit → focused 실행 → `git checkout --` 원복 → 재확인(3회 모두 clean 복귀).

```bash
cd frontend && npm test --silent > /tmp/vitest_verify1.log 2>&1; echo EXIT=$?
# → Test Files 38 passed (38) / Tests 457 passed (457) / EXIT=0 / environment 1712.25s
npx tsc --noEmit   # → rc=0, 출력 0줄
python3 -m pytest tests/test_docs_indexes.py -q   # → 15 passed, 298 subtests
# 변이 focused(★ frontend/ 안에서 — 저장소 루트에서 돌리면 jsdom 미설정으로
#   "ReferenceError: document is not defined" 전멸이 난다; 본 검증 실측):
cd frontend && npx vitest run src/notes/SceneNotesPage.test.tsx src/notes/SceneNotePanel.test.tsx
```

## Findings

### F1. ★ 무변 주장 — 전부 성립

- 4커밋의 파일 집합(`git show --stat`): `services/`·`tests/`·`schemas/` **0건**. 프런트 6파일 + 문서뿐.
- `frontend/src/api/client.ts` diff는 **주석 2줄뿐**(코드·타입 무변) — 와이어 계약 무변.
- `frontend/src/api/schema.d.ts:2566-2586` — `truncated: boolean`·`updated_at`(date-time) 모두 **이 슬라이스 이전부터 선언**. 화면이 읽기 시작한 것뿐이라는 보고와 일치.
- **naive 함정 없음을 소스까지 추적**: `services/application/app/routers/notes.py:140` → `SceneNote.updated_at` → `services/application/app/core_sot/mongo_repository.py:911` 이 읽기 경계에서 `_aware(doc["updated_at'])`(`:913-920`, BSON 날짜를 UTC-aware 로 정규화)로 되돌려 준다. `SceneNoteSearch.tsx:172` 의 `new Date(note.updated_at)` 은 offset 있는 값을 받는다.

### F2. ★ v1.8.37 ② 조건 이행 — 이행됐고 조건대로다

`offers 더 보기 only where the server said the preview was cut`(`SceneNotesPage.test.tsx`)가 **한 셀에 양방향**을 담는다 — 참 행에 버튼 존재(under: 신호를 안 읽으면 실패) + 거짓 행에 부재(over: `truncated` 무시하고 전 행에 내면 실패). 검증자 변이 M-V2 로 2 재실패 실측(F5).

### F3. 구현 ↔ SoT ⑩~⑫ 리터럴

| 리터럴 | 코드 | 셀 |
|---|---|---|
| ⑩ 행은 자기 `updated_at` | `SceneNoteSearch.tsx:170-173` | last-modified 셀(행별 비교 + 타임존 무관 같은 변환 기대값) |
| ⑪ `truncated` 참인 행에만 | `:176` 게이팅 | F2 셀 |
| ⑪ 펼침 = 단건 GET | `:72-85`(`getSceneNote`, `client.ts:612-619` URL `/projects/:pid/drafts/:did/note`) | 단건 GET 셀 — 두 번째 요청 URL 직접 단정 |
| ⑪ 실패해도 미리보기 유지 | `:79-84`(catch 에서 `expandedId` 만 원복) | 실패 유지 셀(404 → alert + 미리보기 + 재시도 버튼) |
| ⑪ 목록 갱신 시 접힘 | `:54-57`(load 성공부) | MN-8 셀(`9262f27`) |
| ⑫ 두 화면 동일 + 편집 대상 불변 | `onSelect` 호출은 `:152`(행 제목 버튼)뿐 — 펼침 버튼은 미호출 | 드로어 펼침 셀(전문 표시 + 편집 상자 존재 + `aria-pressed="false"`) |

- 드로어·페이지가 같은 컴포넌트를 쓰는 것은 배선 사실(`SceneNotePanel.tsx:176-179`)이고, ⑫ 의 두 화면 축은 드로어 셀이 직접 잠근다(v1.8.37 B1 의 교훈이 적용된 모양).
- CSS: `.note-row-meta` 의 `var(--type-micro)` 가 `typeScale.test.ts` 이관 목록에 등재(`:120` 부근, +3줄) — 가드 4번 셀이 목록≡스타일시트 유도 집합을 대조하므로 미등재가 곧 실패라는 보고는 구조적으로 타당하다(가드 소스 확인). `.note-expand` 는 `font-size: inherit` 이라 유도 집합 밖 — 등재 불요 판단도 유도 규칙과 일치.

### F4. 경계 행렬 — 빈 칸 없음(하드닝 3건은 아래)

SoT ⑩~⑫ 가 요구하는 분기 전부가 기명 셀에 대응한다(F3 표). 상속 분기(검색은 서버·실패 목록 보존 등 v1.8.36 ①~④)는 이 슬라이스가 `load()` 를 고쳤으나 기존 셀이 그대로 잠근다(전수 초록으로 확인).

### F5. 변이 재유도(검증자 직접 3종) — 구현자 표는 정직

| 변이 | 적용 diff | 결과(31 focused 중) | 구현자 표와 비교 |
|---|---|---|---|
| M-V1 = MN-8(under) | load 성공부 `setExpandedId(null)`·`setExpandedBody(null)` 2줄 삭제 | **1 재실패** — `folds an expanded row back when a new list arrives` | 일치("셀 보강 후 1") |
| M-V2 = MN-1(over) | `{note.truncated && (` → `{true && (` | **2 재실패** — 페이지 truncated 셀 + 드로어 펼침 셀 | 일치(셀 이름·개수) |
| M-V3 = MN-5(over) | `const full = await getSceneNote(…)` 절을 `setExpandedBody(note.body_preview)` 로 | **4 재실패** — 단건 GET · 실패 유지 · 드로어 펼침 · **접힘(MN-8) 셀** | 표는 3 — **셀 커밋(`9262f27`) 이전 트리에서 측정**했으므로 지금 트리에서는 초집합. 표는 측정 시점 기준으로 정직 |

3종 전부가 기명 셀을 물었다. "8종 중 7종이 곧바로 물었다"는 보고와 반박할 증거 없음.

### F6. 전수·tsc·산술·문서 가드

- 프런트 전수 **457 passed / 38 files, EXIT=0**(본 검증 캡처 실행, environment 1712.25s). 산술 451 + 5(`f46a462`) + 1(`9262f27`) = 457 ✓, 파일 수 38(신규 파일 없음) ✓.
- `tsc --noEmit` rc=0 · 출력 0줄.
- 백엔드 미실행 판단: `services/`·`tests/` 무변 확인 — 타당. 다만 문서를 바꿨으므로 이 검증이 `tests/test_docs_indexes.py` 를 대신 실시: **15 passed / 298 subtests**.

### F7. ★ 미확인 "1 failed / 457" — 배제는 확인, 부하 해석은 반증

- **문서-간섭 가설의 배제가 전체 스위트에 성립함을 확인**: 프런트 전수에서 파일을 읽는 테스트는 정확히 10개(`typeScale`·`buttonAppearance`·`pageLayout`·`designTokens`·`navigationLinks`·`disabledState`·`scratchPadCss`·`adsense`·`productName`·`chartColors`)이고 모두 `frontend/` 내부 파일만 읽는다. `ReviewInbox.test.tsx:508` 의 `docs/` 는 주석(검증 기록 참조)이다. 구현자가 별도 실시한 "10가드 35 passed" 배제가 스위트 전체로 확장된다.
- **다만 "머신 부하가 극단적이었다"는 해석은 이 비교로 지지되지 않는다**: 실패 실행의 `environment 1778s`(work_log 세션 24) vs 본 검증 **초록** 실행의 `environment 1712s` — 실패 실행이 특별히 무거웠다는 근거가 없다(약 4% 차이). 이 문장은 정정이 권고된다(소유는 기록자·오너).
- 동일 트리에서 전수 초록 **3연속**(구현자 캡처 2회 + 본 검증 1회). 재현 없음 — "정체 미상" 분류 유지가 맞다. 잔여 가설: 재현율이 낮은 타이밍 플레이크(`waitFor` 기본 1초 등). 실패 블록이 잘린 것은 `| tail` 운영 실수(기록에 정직하게 남음).
- 참고(별건): vitest 를 **저장소 루트에서** 돌리면 jsdom 환경이 없어 `ReferenceError: document is not defined` 로 파일 전멸이 난다(본 검증 실측, 2회 재현성). 실패 모양이 "1개 실패/457" 과 다르므로 그 실행의 정체는 아니지만, 실행 창의 cwd 도 변인임을 기록해 둔다.

### F8. 기록 일관성

SoT v1.8.38(헤더·변경이력 행·§장면 메모 화면 본문 갱신 상호 일치) · 최상위 README 절차 표 SoT 버전 셀(v1.8.38) · CHANGELOG 행 · HANDOFF(4번 폐쇄 + 다음 지시자 2번·6차 승격 재검증, 기준선 457/38, 배포 대기에 **프론트 이미지 재빌드 필요** 명시, 육안 확인 +2건) · work_log 세션 24(변이 표 8종·미확인 실패·백엔드 미실행 사유 정직 기록). 사소: `HANDOFF.md:235` 에 `0건). ·` 병기(문장부호 흠, 계약 무관).

## Issues / Risks

### Blocking (계약 의무)

**없음.**

### Hardening (비차단)

1. **H1 — `expand()` 경쟁 상태(만료 응답 가드 없음).** A행 "더 보기" 로딩 중 B행 "더 보기"를 누르면: A의 늦은 성공이 `expandedBody` 에 A 본문을 싣는데 `expandedId` 는 B — B 행에 A 본문이 일시 렌더된다(B 응답 도착 시 자기 교정). 또는 A의 늦은 **실패**가 B의 성공 펼침을 접고 오류 배너를 띄운다. 계약이 동시 클릭을 열거하지 않아 비차단. 처방: 클릭 시 id 를 캡처하고 응답 시 현재 펼침과 일치할 때만 반영(functional `setState` + identity 검사).
2. **H2 — "불러오는 중…" 잠금 무셀.** work_log 결정("응답 전 접으면 늦게 도착한 전문이 접힌 행에 붙는다")의 방어(접기 버튼 `disabled`)에 셀이 없다 — `disabled` 제거 변이가 초록일 것. SoT 리터럴이 아니라 구현자 자기 방어라 비차단.
3. **H3 — 드로어의 수정 시각 존재 무셀.** ⑩ 은 페이지 셀로만 잠긴다. 컴포넌트 공유는 잠금이 아니다(v1.8.37 B1 과 같은 종) — 드로어에서만 시각 렌더를 끄는 변이가 초록일 것. ⑫ 가 "두 화면에 똑같이"를 펼침에만 명시하므로 리터럴 위반은 아니나, 드로어 셀에 `수정 ` 문자열 단정 한 줄이면 닫힌다.

## Verdict

**합격** — SoT v1.8.38 ⑩~⑫(및 상속 분기 중 이번에 건드린 축)의 요구 분기 전부가 기명 셀에 대응하고, 검증자 변이 3종(under 1 · over 2)이 전부 기명 셀을 물었으며, 무변 주장(백엔드·API 계약·`schema.d.ts`, `client.ts` 는 주석만)이 소스 수준에서 성립하고, 기록 4건(SoT·HANDOFF·CHANGELOG·work_log)과 실측(457/38·tsc 0)이 상호 일치한다. v1.8.37 ② 의 양방향 셀 조건은 이행됐다. 미확인 1실패는 계약 잠금과 무관한 운영 사안이다(아래).

## Outstanding items

- **미확인 "1 failed / 457"**: 동일 트리 전수 초록 3연속, 부하 가설 반증(F7) — 정체 미상 유지, 재현 시 그때 잡는다. 전수는 항상 전량 캡처로(`| tail` 금지 — 본 검증도 준수).
- work_log 세션 24 의 "머신 부하가 극단적이었다" 서술 정정 여부는 기록자·오너 몫(F7 이 근거).
- 배포 대기: 이 슬라이스는 프론트 소스 변경 — **frontend 이미지 재빌드 필요**(HANDOFF 5번에 명시됨).
- 육안 확인 +2건(좁은 드로어의 꼬리줄 줄바꿈 · 긴 전문 펼침 스크롤) — 프론트 재빌드 선행.

## Reproduction

```bash
git status --short          # 공백이어야 변이 가능(본 검증 3회 모두 준수)
cd frontend && npm test --silent > /tmp/v.log 2>&1; echo EXIT=$?
#   → 38 files / 457 tests / EXIT=0
npx tsc --noEmit; echo $?
python3 -m pytest tests/test_docs_indexes.py -q
# 변이: frontend/src/notes/SceneNoteSearch.tsx 를 F5 표의 diff 로 Edit →
#   cd frontend && npx vitest run src/notes/SceneNotesPage.test.tsx src/notes/SceneNotePanel.test.tsx
#   → 요약 라인 판독(1/2/4 failed) → git checkout -- frontend/src/notes/SceneNoteSearch.tsx
# ★ vitest 는 frontend/ 안에서 실행할 것(루트 실행 시 document is not defined 전멸).
```
