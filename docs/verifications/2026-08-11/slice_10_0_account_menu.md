# Slice 10.0 계정 메뉴 + 제품명 "에-라잇" 독립 검증

## Subject metadata

- 날짜: 2026-08-11
- 요청자: 오너 — *"작업 AI가 작업한거 검증하고 의심하고 또 의심해줄래? … 다른쪽으로 검증해주면 될꺼같아."* (육안 확인은 오너 완료, 특이사항 없었음)
- 검증자: 이 세션 (구현자와 다른 세션)
- 대상: Phase 10 Slice 10.0 — 계정 메뉴(D4 ⓐ+ⓒ) + 제품명 "에-라잇"(D5). 커밋 `387bfe7`·`5965c9b`·`db223ee`.
- 정규 스펙: [`docs/plans/10-frontend-design-system-decisions.md`](../../plans/10-frontend-design-system-decisions.md) §D4·§D5 (Resolved, 오너 2026-08-11).
- 오너 결정(검증 중, 2026-08-11): 탭 `<title>` 수정은 **작업 AI** 몫; 검증은 검증으로 끝.

## Scope

1. 계약(D4 ⓐ+ⓒ·D5) 대 구현 — `frontend/src/auth/AuthGate.tsx` `SessionMenu`(신규) + 헤더/eyebrow.
2. 회귀 셀 — `frontend/src/App.test.tsx` "계정 메뉴" describe(신규 4) + 갱신된 기존 6줄. 가드가 무엇을 무는가.
3. **뮤테이션 6종(작업자 주장)의 독립 재도출** — 특히 M2(강화 전 안 물음 → 강화 후 물음)의 양방향 재현.
4. 기준선 수치 — frontend 289/20 · build · 백엔드 UI-label 가드.
5. 두 일탈의 건전성 — disclosure vs `role="menu"` · 로그아웃 패널 유지.
6. 완전성 스윕 — 제품명 구명칭 잔존 표면.
7. 기록(§5) — work_log·HANDOFF·CHANGELOG·브리프 정정.

## Methodology

- 트리 clean 전제(HEAD `db223ee`, 전부 커밋됨). 뮤테이션은 `verification.md` 검증자 분기 — `cp` 백업 → 변형 → 실측 → 원복 → `diff` byte 대조 + `git status --short` empty 확인.
- frontend 전체: `cd frontend && npx vitest run`.
- focused: `npx vitest run src/App.test.tsx` (24 tests, ~51s).
- 백엔드 가드: `python3 -m pytest tests/test_activity_ui_labels.py -q`.
- build: `cd frontend && npm run build` (`tsc --noEmit && vite build`).
- 제품명 스윕: `grep -rni "AI Writing System" frontend/` + `index.html`.

## Findings

### 1. 기준선 수치 — 전부 독립 재현 (작업자 주장과 일치)

- frontend `npx vitest run`: **Test Files 20 passed (20) · Tests 289 passed (289)**, exit 0.
- 백엔드 `test_activity_ui_labels.py`: **6 passed, 30 subtests passed**.
- build: **702 modules transformed** · 진입 `index.js` **420.81 kB** · CSS **26.62 kB** · AdminConsole lazy **8.50 kB** · 관측 lazy **386.70 kB** · `tsc --noEmit` clean.

### 2. 뮤테이션 — M2 헤드라인 내러티브를 양방향으로 재현

작업자의 핵심 주장 *"M2(Esc 포커스 복귀)가 처음에 안 물었다(24 passed) → 강화 후 문다(1 failed)"* 를 **직접 반박 시도→재현**:

- M2 변형(`close()` 의 `triggerRef.current?.focus()` → `void 0`, `AuthGate.tsx:206`)
  + **강화 전 테스트**(`387bfe7` 버전, `tab()` 없음) = **24 passed | 0 failed** → **안 물음 확인**.
- 같은 변형 + **강화 후 테스트**(현행, `5965c9b` 의 `tab()` 후 Esc) = **1 failed | 23 passed** → 실패는 `App.test.tsx:653` `expect(trigger).toHaveFocus()`. **물음 확인**.
- 원인이 작업자 서술대로임 확인: 트리거 클릭 직후엔 포커스가 이미 트리거에 있어 복귀 코드를 지워도 `toHaveFocus()` 가 통과. *"안 무는 것이 신호다"* 교훈이 동일하게 재현.

나머지:
- **M1**(`<Link to="/me">`→`<span>`): **3 failed | 21 passed**. 작업자 주장(3) 일치. (실패 셀 라벨 정정 — Issues H3.)
- **M4**(로그아웃 `onClick` 에 `setOpen(false)` 재도입): **2 failed | 22 passed**. 주장(2) 일치. 전용 진행신호 셀 + 기존 `keeps the protected UI mounted until server logout succeeds` 셀(pannel 안 "나가는 중…" 버튼이 닫혀 사라져) 2겹.
- 뮤테이션 전후 트리 byte-identical·clean 확인(각 `diff` + `git status --short` empty).
- M3(admin 조건)·M5(제품명)·M6(항상 렌더)은 코드에서 기계적으로 자명하고 M1/M2/M4 로 작업자 정직성이 입증돼 별도 실측 생략.

### 3. 두 일탈 — 둘 다 건전

- **disclosure vs `role="menu"` (브리프 정정)**: 옳은 판단. ARIA `menu` 는 **애플리케이션 명령 메뉴**용(화살표 키 탐색·타입어헤드를 사용자에게 약속)이고, 여기엔 내비게이션 링크 둘 + 액션 하나라 그 약속을 지킬 이유·방법이 없다 → 표준 **disclosure**(버튼 `aria-expanded`/`aria-controls` + 접히는 영역)가 맞다. 부수 효과로 `<a>` 의 link 역할이 보존돼 기존 `getByRole("link",{name:"관리"})` 셀이 그대로 유효(`role="menuitem"` 이었으면 덮혀 무효). 구현은 Esc·포커스 복귀·바깥 클릭 닫기·트리거 토글의 이중 발화 없음까지 갖춘 정석 disclosure.
- **로그아웃 패널 유지(작업자 판단)**: 사운드. "나가는 중…"/`disabled` 가 **패널 안에** 있어 닫으면 진행 중이라는 유일한 신호를 잃는다. 성공 시 셸 전체가 로그인 화면으로 바뀌며 자연히 사라지고, 실패 시 열린 채로 남아 즉시 재시도 + 헤더 배너(`role="alert"`). M4 가 2겹으로 잠금.

### 4. 완전성 스윕 — 탭 타이틀 잔존 (★발견)

`grep -rni "AI Writing System" frontend/` → `frontend/index.html:6 <title>AI Writing System</title>` (및 빌드 산물 `dist/index.html`, `openapi.json:3540` API title). D5 가 헤더 브랜드(`AuthGate.tsx:137`)·AuthStatus eyebrow(`:159`)를 "에-라잇"으로 통일했으나 **브라우저 탭 타이틀은 구명칭 잔존**. 작업자의 D5 회귀(`App.test.tsx:701` `screen.queryByText("AI Writing System")`)는 `<title>` 을 못 본다 — testing-library `queryByText` 는 `<body>` 만 보고 `<head>` 는 안 보므로 이 갭이 **가드 밖**이다(현재 green 은 헤더에 구명칭이 없어서이지 탭을 본 것이 아니다).

### 5. 기록(§5) — 갖춤

work_log Task 5 · HANDOFF 기준선(frontend 289/20 · 진입 420.81 kB 갱신) · CHANGELOG 10.0 행 · 브리프 §D4 `role="menu"` 취소선 정정 — 전부 존재 확인.

## Issues / Risks

### Blocking (계약 의무 위반)

- **없음.** D4(ⓐ+ⓒ)는 계약대로 구현됐고 "지켜야 할 것 넷"(disclosure·키보드 Esc+포커스·관리자 조건·로그아웃 이동)이 전부 가드로 잠겼으며 뮤테이션으로 입증됐다. 경계 행렬에 빈 칸 없음.

### Hardening / 비차단

- **H1 (★완전성, 오너 결정 반영): 브라우저 탭 `<title>` 이 "AI Writing System"** (`frontend/index.html:6`). D5 의도 *"이름이 하나가 된다"* 가 탭에서 달성되지 않았다. 오너 결정(2026-08-11): **수정은 작업 AI 몫**. 권고 — `index.html` 타이틀을 "에-라잇" 으로 + `document.title` 을 읽는 회귀 가드(`queryByText` 맹점 폐쇄). 빌드 산물 `dist/index.html` 은 재빌드시 따라감.
- **H2 (범위 밖, 참고): `openapi.json:3540` API title "AI Writing System Application"** — backend 생성 메타데이터. 10.0 은 "backend 0줄" 이라 범위 밖. 완전 통일을 원하면 별도(backend 코드 + `gen:api` 재생성).
- **H3 (기록 정확성): work_log Task 5 의 M1 표가 세 번째 실패 셀을 "제품명 셀" 이라 적었으나 실제로는 Esc 포커스 복귀 셀**(`App.test.tsx:641`)이다. 개수(3 failed)는 맞고 라벨만 빗갔다. `verification.md` 가 뮤테이션→셀 페어링의 정확을 요구하므로 정정 권고.

## Verdict

**조건부 합격** — 조건: 브라우저 탭 `<title>`("AI Writing System")을 "에-라잇"으로 통일하고 `document.title`을 읽는 회귀 가드를 추가할 것(작업 AI). 그 외 blocking 0.

이유: D4 계정 메뉴는 계약대로 구현됐고 양방향 가드(뮤테이션 M1·M2·M4 독립 재현)로 입증됐으며 두 일탈(disclosure 전환·로그아웃 패널 유지) 모두 건전하다. 다만 D5 "이름 통일" 의도가 **탭 타이틀에서 잔존**하고 오너가 이를 수정 대상으로 결정한 실제 결손이 하나 있어 조건부로 둔다.

## Outstanding items

- ~~**작업 AI** 가 H1(탭 `<title>` 통일 + `document.title` 가드) 처리. H3(M1 셀 라벨 정정) 도 같이.~~
  **★ 폐쇄 2026-08-11 (작업 AI, 검증자 아님).**
  - **H1 닫힘** — `frontend/index.html:6` 을 `<title>에-라잇</title>` 로. 가드는
    `document.title` 이 아니라 **파일을 읽는** 쪽으로 만들었다
    ([`frontend/src/productName.test.ts`](../../../frontend/src/productName.test.ts), 2 cells):
    vitest 는 `index.html` 을 로드하지 않고 빈 jsdom 문서에 마운트하므로 `document.title`
    을 읽어도 **런타임 값이지 저장소의 값이 아니다** — 검증자가 지목한 맹점이 그대로 남는다.
    파일을 읽으면 `<head>` 전체가 사정거리에 들어온다. 두 번째 셀은 **소스 전수 스윕**이라
    `og:title`·manifest 등 아직 없는 자리도 미리 덮는다(테스트 파일은 제외 — 부재를
    단정하려면 그 문자열을 적어야 한다). 양방향 실측: **M7** 타이틀 되돌림 → 2 failed ·
    **M8** 렌더 밖 소스에 옛 이름 부활 → 1 failed.
  - **H3 닫힘** — work_log Task 5 의 M1 표를 `App.test.tsx:641` Esc 포커스 복귀 셀로 정정.
    검증자 지적대로 개수는 맞고 라벨만 빗갔다(작업자가 M1 을 재현해 직접 확인).
  - **기준선 이동**: frontend `289/20` → **`291 passed / 21 files`**(+2 cells · +1 file).
    build **702 modules · 진입 420.81 kB 무변**(타이틀은 JS 번들 밖이다). `dist/index.html`
    재빌드에서 `<title>에-라잇</title>` 확인.
- H2(openapi API title)는 10.0 범위 밖이라 별도 오너 판단.
- 본 검증은 **검증으로 끝** — 10.1 팔레트 교체 착수·타이틀 수정은 작업 AI 몫(오너 2026-08-11).

## Reproduction

```bash
# 기준선 (전부 독립 실측)
cd frontend && npx vitest run                          # 20 files / 289 passed
python3 -m pytest tests/test_activity_ui_labels.py -q  # 6 passed, 30 subtests
cd frontend && npm run build                           # 702 modules, 진입 420.81 kB

# M2 양방향 (cp 백업 → 변형 → 실측 → 원복 → diff)
cp frontend/src/auth/AuthGate.tsx /tmp/A.orig
#   Edit AuthGate.tsx close(): triggerRef.current?.focus()  →  void 0
npx vitest run src/App.test.tsx                        # 강화 후: 1 failed (App.test.tsx:653)
git checkout -- frontend/src/auth/AuthGate.tsx
git show 387bfe7:frontend/src/App.test.tsx > frontend/src/App.test.tsx   # 강화 전 테스트로 교체
#   (같은 M2 변형을 다시 AuthGate 에 적용한 뒤)
npx vitest run src/App.test.tsx                        # 24 passed (안 물음)
git checkout -- frontend/src/App.test.tsx frontend/src/auth/AuthGate.tsx
diff /tmp/A.orig frontend/src/auth/AuthGate.tsx        # empty

# M1·M4 도 같은 흐름(변형만 다르게) — 각 3 failed·2 failed.

# 제품명 잔존
grep -rni "AI Writing System" frontend/ --include='*.html'
```
