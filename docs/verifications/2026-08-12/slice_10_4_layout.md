# Slice 10.4 페이지 배치 통일 독립 검증

## Subject metadata

- 날짜: 2026-08-12
- 요청자: 오너 — *"다음작업 검증해줘. Slice 10.4 완료. 실측으로 시작해서, 렌더해서 보다가 두 개를 더 찾았습니다."*
- 검증자: 이 세션 (구현자와 다른 세션). 10.0·10.1·10.2·10.3(타이포·차트) 에 이어 같은 Phase.
- 대상: Phase 10 Slice 10.4 — 배치를 편집기 기준으로 전 화면 통일. 커밋 `4db744c`(구현+하네스) · `e749873`(배치 가드+overview 폐쇄) · `822bf10`(기록).
- 정규 스펙(정본): [`docs/plans/10-frontend-design-system-decisions.md`](../../plans/10-frontend-design-system-decisions.md) §10.4(배치 — 2026-08-12) + 슬라이스 표 10.4 행. 실측 하네스: [`docs/plans/10_layout_probe.sh`](../../plans/10_layout_probe.sh)·`.html`·`_report.py`(커밋됨).
- 검증 출처: `git status --short` empty · HEAD = `822bf10` (트리 clean, 커밋됨).

## Scope

1. **★ "실측으로 시작" — 하네스 픽셀 수치를 직접 재도출.** 보고 표의 **양쪽 열**(PRE 380/274/240 · POST 244/138/247)을 모두 재현. 작업자가 커밋한 하네스(headless chromium 1440×900)를 직접 돌림.
2. **세 규칙** — ① 폭 68rem 한 곳 ② 블록 자기제한(컨테이너로 좁히지 않음) ③ 화면 제목 `--type-title` 한 계단, 로그인은 램프 안 예외.
3. **렌더로 찾은 둘** — ① `.login-form button` 규칙이 없어 회색 기본값(종전엔 선언 자체가 없었는가) ② `.overview-page` 폭 override 가 통일 후에도 남아 있었는가(가드가 잡았다는 주장).
4. **배치 가드 `pageLayout.test.ts`** — "값이 아니라 자리가 하나인가". 뮤테이션 3종 단독 물림.
5. **★ 가드의 페이지 뿌리 분류가 건전한가** (작업자가 두 번 틀린 자리) — `access-log-page` 가 진짜 안쪽 블록인지, 그리고 **모든 라우트 페이지가 가드 뿌리 안에 있는지**.
6. **회귀·번들** — frontend 318/26 · 백엔드 prod 0줄 · CSS 31.76 · 진입·lazy.

## Methodology

정본 → 하네스·코드·뮤테이션으로 재도출(보고를 사실로 받지 않음).

- **하네스 실측**: `bash docs/plans/10_layout_probe.sh 1440` (chromium 150 snap; 스크립트가 $HOME 밖 파일 접근 함정을 스스로 처리). POST-fix = 현재 `styles.css`. **PRE-fix** = `git show 4db744c~1:frontend/src/styles.css` 로 잠시 교체 후 측정(`cp` 백업·`diff` byte-identical 복원 증명).
- 코드: `grep` 로 폭·제목·로그인 버튼·overview 규칙을 현재와 부모(4db744c~1)에서 대조. `--type-display` 램프 계산 `round(1.125**9,3)`.
- 가드 뿌리 분류: 각 라우트 페이지 컴포넌트의 루트 `className` 전수 확인 + `access-log-page` 가 `<ul>`(목록)인지 마크업에서 확인.
- 회귀: `cd frontend && npx vitest run`(전수) · `npm run build`(번들 직접 재생산) · 백엔드 `git show --stat 4db744c e749873`.
- **뮤테이션**: 트리 clean·커밋됨 → `git checkout --` 복원 + `cp` 백업 + `diff -q` 증명 + trap. 스크립트: [`repro_layout_mutations.sh`](./repro_layout_mutations.sh).

## Findings

### 1. ★ 하네스 픽셀 수치 — PRE·POST 양쪽 열 전부 독립 재현

작업자가 커밋한 하네스를 **내가 직접 돌려** 한 픽셀 안 틀림 없이 재현:

| 표면 | PRE 콘텐츠까지·h1·점유·오른쪽 끝 | POST (동일 순서) |
|---|---|---|
| workspace-page | **380**·**83**·**55%**·**1033** | **244**·**39**·**38%**·**1225** |
| admin-page | **274**·**83**·**42%**·**1193** | **138**·**39**·**25%**·**1225** |
| editor-page | **240**·**31**·**37%**·**1225** | **247**·**39**·**38%**·**1225** |

양쪽 열 전부 작업자 보고와 정확히 일치. headerRight=1257(가드 주석이 말한 헤더 끝)도 재현. PRE 의 비대칭(컨테이너 오른쪽 끝 1033/1193/1225 세 종류 vs 헤더 1257 → workspace 는 224px·admin 은 64px 삐져나감)이 POST 에서 1225 단일로 통일됨을 실측으로 확인. **"실측으로 시작"이 하네스로 성립**한다.

### 2. 세 규칙 — 코드로 전부 확인

- **① 폭 한 곳**: `.workspace-page, .admin-page { width: min(100%, 68rem); … }`(`styles.css:479–482`) 가 유일한 페이지 폭 규칙. `main { max-width: 68rem }`(`:301–302`). 컨테이너 폭 == main 상한 == 68rem.
- **② 블록 자기제한**: `.page-heading { max-width: 42rem }`(`:693`) · `.page-heading > p:last-child { max-width: 34rem }`(`:1040`) — 페이지 컨테이너는 68rem(넓게, 정렬·헤더용)인데 **안의 머리글·설명 블록이 스스로 측정폭을 제한**한다. 컨테이너를 좁혀 가독성을 얻지 않는다(정렬과 가독성이 서로를 안 깎음).
- **③ 제목 한 계단 + 로그인 램프 안 예외**: `typeScale.test.ts` MIGRATED 가 `".page-heading h1, .workspace-page > h1": "title"` 로 전 표면을 한 계단으로. `".login-heading h1": "display"` — `--type-display: 2.887rem; /* 1.125^9 */`(`styles.css:172`) 이고 `round(1.125**9,3)=2.887` 로 **램프 안**. h1 높이도 POST 전 표면 39px 로 통일(PRE 83/83/31).

### 3. 렌더로 찾은 둘 — 둘 다 재현

- **로그인 버튼**: 현재 `.login-form button` 규칙 존재(`styles.css:361`, `var(--action-primary)` 배경·hover·disabled). **부모(4db744c~1)에는 이 규칙이 한 줄도 없었다** → 작업자 주장대로 "색 리터럴도 토큰 오타도 아니라 선언 자체가 없음" 이라 CSS·TS 가드가 조용했고 회색 상자로 렌더됐던 것.
- **overview 누락(가드가 잡음)**: 부모엔 `.overview-page { width: min(100%, 62rem) }`(`:673–675`) 이 남아 있어 "통일했다"는 커밋이 실제로 개요 화면을 62rem 에 빠뜨린 상태였다. 현재는 제거됨(`e749873` -4줄). 개요 화면 마크업이 `workspace-page overview-page` 이므로 overview-page 는 수식자이고, 이 override 가 바로 가드 cell 2 가 잡는 형태.

### 4. 배치 가드 — 뮤테이션 3종 단독 물림 재현

`pageLayout.test.ts` 3셀. 각 변형 후 복원 byte-identical:

| # | 변형 | 결과(독립) | 작업자 주장 |
|---|---|---|---|
| LM1 | `.overview-page { width: min(100%,62rem) }` 재삽입 | cell 2 *"lets no page modifier override"* **단독** | ✓ |
| LM2 | 공통 규칙에서 `.admin-page,` 제거 | cell 1 *"sets the page width in exactly one place"* **단독** | ✓ |
| LM3 | 컨테이너 폭 68→67(main 은 68) | cell 3 *"keeps the container width equal to the shell"* **단독** | ✓ |

3종 전부 단독 물림. 가드가 재는 것이 **값이 아니라 "폭을 정하는 자리가 하나인가"** 라는 설계가 변형 결과로 증명된다(LM3 은 값 1rem 차이만으로 cell 3 이 물고 cell 1·2 는 안 물린다 — 값이 아니라 자리·일치성을 본다).

### 5. ★ 가드 뿌리 분류 — 건전 (작업자가 두 번 틀린 자리, 내가再확인)

적대적으로 두 각도를 찔렀다:

- **`access-log-page` 는 진짜 안쪽 블록이다.** `PersonalHubPage` 마크업: `<section className="workspace-page …">` 안의 `<section className="hub-section">` 안의 **`<ul className="access-log access-log-page">`** — 페이지 뿌리가 아니라 **활동 목록 리스트**. 작업자가 "이름이 `-page` 로 끝나지만 화면 안쪽 블록" 이라 한 판정이 맞다. 가드가 페이지 뿌리와 **같은 요소에** 붙은 클래스만 보므로 이 `<ul>` 을 올바르게 무시한다.
- **모든 라우트 페이지가 가드 뿌리 안에 있다.** 전수 확인: ObservabilityDashboard·ReviewInbox·ProjectList·AccessLogPage·ActivityTimelinePage = `workspace-page page-enter`, ProjectOverview = `workspace-page overview-page page-enter`, AdminConsole = `admin-page page-enter`, login = `auth-shell`/`login-page`(AUTH_SHELL 제외). 가드 밖에서 자기 폭을 정하는 페이지 **0개**. 다른 클래스에 숨은 `width` 규칙도 grep 으로 **0건**.

즉 가드의 PAGE_ROOTS=[workspace-page, admin-page] 가 **모든 페이지 뿌리를 빠짐없이 덮고**, 이름 모양이 아니라 마크업 자리로 분류한다 — 작업자의 두 번 틀리고 고친 자리가 건강함.

### 6. 회귀·번들 — 독립 재현

- frontend 전수: **Test Files 26 · Tests 318**, exit 0. 작업자 318/26 일치. 484s.
- 백엔드 prod **0줄**: `git show --stat 4db744c e749873` 의 `.py` 는 `docs/plans/10_layout_probe_report.py`(문서 하네스)뿐.
- **번들(직접 빌드)**: CSS **31.76 kB** ✓(원시 46548→48703 B) · 진입 **421.78 kB 무변** ✓. lazy ObservabilityDashboard **387.43 kB** — 본 슬라이스(10.4)는 JS/TS 앱 코드를 한 줄도 안 건드려(git --stat) lazy 에 손을 안 댔다; 387.03→387.43 의 차이는 10.3 차트 보강(`444ab1b` H2, ObservabilityDashboard.tsx 변경)이고 10.4 이전에 이미 이 값이었다.

## Issues / Risks

### Blocking (계약 위반) — **0건**

정본 §10.4 가 정한 세 규칙이 코드로 성립하고, 하네스 실측이 양쪽 열에서 재현됐으며, 배치 가드는 단독 물림 3종으로 증명됐고, 가드 뿌리 분류는 모든 라우트를 빠짐없이 덮는다. 회귀 green·백엔드 prod 0줄.

### Hardening / 추적 부채 (비차단, 작업자가 이미 기록)

- **H1 — 기본 버튼 규칙이 네 곳에 흩어져 있다.** 로그인 버튼이 회색으로 렌더된 근본 원인. 이 슬라이스는 빠진 자리(`.login-form button`)만 채웠고 **통합은 추적 부채로 남겼다**. 새 표면이 또 어디에도 안 들어가 회색 버튼으로 렌더되는 일이 반복될 수 있다 — 작업자 기록대로.
- **T1 — 68rem 확장의 목록 행 간격.** 폭을 넓히면 목록 행에서 제목과 오른쪽 `→` 사이가 벌어진다. 헤더 정렬 이득이 더 크다고 판단했으나 **육안 확인 때 다시 볼 자리**로 기록됨.
- **측정 하네스는 정성적 스크린샷이 아니라 픽셀 수치** — 이 저장소의 다른 벤치마크처럼 재현 경로가 저장소 안(커밋됨)에 있어, 내가 돌려 같은 수치를 냈다.

## Verdict

**합격** — 차단 결함 0. "실측으로 시작"의 근거가 되는 하네스 픽셀 수치를 PRE·POST 양쪽 열에서 내가 직접 돌려 한 픽셀 안 틀림 없이 재현했고, 세 규칙(폭 한 곳 68rem · 블록 자기제한 42/34rem · 제목 한 계단 + 로그인 램프 안 예외)이 코드로 성립하며, 렌더로 찾은 둘(로그인 버튼 미선언·overview override 잔존)을 부모 커밋에서 확인했다. 배치 가드는 LM1/LM2/LM3 단독 물림으로 "값이 아니라 자리가 하나"를 증명하고, 가드 뿌리 분류는 모든 라우트를 덮고 access-log-page 를 올바르게 안쪽 블록으로 뺀다. 회귀 318/26 · 백엔드 prod 0줄 · CSS 31.76 · 진입 421.78 무변. H1(버튼 규칼 흩어짐)·T1(목록 행 간격)은 작업자가 이미 추적 부채/육안 확인로 기록한 비차단.

## Outstanding items

1. **육안 확인 — Phase 10 말로 미룸.** CSS 변경이라 컨테이너 이미지에 않음: `docker compose build frontend && up -d frontend` 선행. 볼 것: 9개 workspace 화면·admin 의 첫 화면에 콘텐츠가 들어왔는가 · 헤더 밑줄이 대칭인가 · **목록 행 간격(T1)** · 로그인 버튼이 액션 블루로 렌더되는가.
2. **H1 추적 부채** — 기본 버튼 규칙 통합(언제 열지는 작업자 판단).
3. **백엔드 전수 회귀 미갱신** — 기준선 2271/1/2430 은 8/11 값. prod 0줄.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
git status --short                          # empty 전제
git show --stat 4db744c e749873             # 백엔드 .py = 하네스 report 뿐(prod 0줄)
# ★ 하네스 실측 (POST-fix):
bash docs/plans/10_layout_probe.sh 1440      # workspace 244·39·38%·1225 / admin 138·39·25%·1225 / editor 247·39·38%·1225
# ★ 하네스 실측 (PRE-fix) — 부모 CSS 로 잠시 교체:
cp frontend/src/styles.css /tmp/post.bak
git show 4db744c~1:frontend/src/styles.css > frontend/src/styles.css
bash docs/plans/10_layout_probe.sh 1440      # workspace 380·83·55%·1033 / admin 274·83·42%·1193 / editor 240·31·37%·1225
cp /tmp/post.bak frontend/src/styles.css     # 복원
# 회귀·번들:
cd frontend && npx vitest run                # 26 files / 318 passed
npm run build                                # CSS 31.76 · 진입 421.78
# 뮤테이션 LM1–LM3 (트리 clean·커밋됨 → git checkout 복원 + cp 백업 + diff 증명 + trap):
bash docs/verifications/2026-08-12/repro_layout_mutations.sh
```
