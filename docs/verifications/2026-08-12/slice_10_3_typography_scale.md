# Slice 10.3 타이포 축 + DraftEditor 적용 독립 검증

## Subject metadata

- 날짜: 2026-08-12
- 요청자: 오너 — *"작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?"* (구현 완료 보고에 대한 독립 검증 요청)
- 검증자: 이 세션 (구현자와 다른 세션). 10.0·10.1·10.2 검증에 이어 같은 Phase.
- 대상: Phase 10 Slice 10.3 — 타이포 축 신설 + `DraftEditor` 적용. 구현 커밋 `d4bf832` · 기록 커밋 `a4ec45c`.
- 정규 스펙(정본): [`docs/plans/10-frontend-design-system-decisions.md`](../../plans/10-frontend-design-system-decisions.md) 슬라이스 표 10.3 행(L383) + §"10.3 이 확정한 것 — 타이포 축"(L386–422). 정본 표는 L397–406.
- 검증 출처: `git status --short` empty · HEAD = `a4ec45c` (트리 clean, 커밋됨).

## Scope

1. **스케일 산술** — 8계단 값이 정본 표·`round(1.125**n,3)`·`styles.css` 선언 셋이 한 글자 안 틀리고 같은가.
2. **신규 가드 `typeScale.test.ts`** — 3셀, 양방향. 뮤테이션 M1–M5(작업자 주장)를 **독립 재도출**.
3. **이관 충실성** — `MIGRATED` 목록이 실제 `var(--type-*)` 사용처를 빠짐없이 잡는가.
4. **위계 편집** — `.editor-heading h1` · `.editor-page` · `.editor-heading` 세 곳 + "3.7배" 주장.
5. **회귀** — frontend 전수(309/24) · 백엔드 prod 0줄 · 백엔드 CSS-읽기 가드.
6. **측정 주장** — "19종 / 12종 / 45곳·22종" 및 패턴 스윕 수치의 독립 재측정.
7. **발견된 한계** — 주석 없는 토큰이 cell 1 정규식을 빠져나가는지(M6 탐침).

## Methodology

정본 읽기 → 코드·수치·뮤테이션으로 재도출(보고를 사실로 받지 않음). 전 명령어 재현 가능.

- 트리/커밋: `git log --oneline -8` · `git show --stat d4bf832` · `git status --short`.
- 정본 대조: `git show d4bf832:frontend/src/styles.css` vs 정본 표 L397–406 수기 산술.
- font-size 분포: `grep -oE 'font-size:\s*[^;]+' src/styles.css | sort | uniq -c` (전수). 부모 커밋 분포: `git show d4bf832~1:frontend/src/styles.css | grep -oE ...`.
- 기준선 회귀: `cd frontend && npx vitest run` (전수) · `npx vitest run src/typeScale.test.ts` (단독).
- 백엔드 가드: `PYTHONPATH=. python3 -m pytest tests/test_design_token_provenance.py -q`.
- **뮤테이션**: 트리 clean·커밋됨 → `git checkout --` 복원 브랜치(verification.md "clean-tree"). 추가로 `cp` 백업 + 복원 후 `diff -q` byte-identical 증명 + `git status --short` empty 확인을 겹침. 인터럽트 시 복원을 위해 trap 부착. 재현 스크립트: [`repro_typescale_mutations.sh`](./repro_typescale_mutations.sh) (M1–M5). M6(탐침)은 동일 패턴으로 수동.
- 빌드/CSS 크기: 원시 바이트 `wc -c`로 pre/post 측정(빌드 아티팩트 재생산은 안 함 — Outstanding).

## Findings

### 1. 스케일 산술 — 정본·코드·수식 모두 일치

정본 표(L397–406)와 `styles.css:140–147`이 한 글자 안 틀리고 같다. `round(1.125**n, 3)` 수기 계산 전계단 일치:

| 토큰 | 선언 | `round(1.125**n,3)` | |
|---|---|---|---|
| `--type-micro` | 0.702rem | 0.70233→**0.702** | ✓ `^-3` |
| `--type-meta` | 0.79rem | 0.7901→**0.790** | ✓ `^-2` |
| `--type-small` | 0.889rem | 0.8889→**0.889** | ✓ `^-1` |
| `--type-base` | 1rem | 1 | ✓ `^0` |
| `--type-reading` | 1.125rem | 1.125 | ✓ `^1` |
| `--type-subhead` | 1.266rem | 1.2656→**1.266** | ✓ `^2` |
| `--type-panel` | 1.602rem | 1.6018→**1.602** | ✓ `^4` |
| `--type-title` | 2.027rem | 2.0273→**2.027** | ✓ `^6` |

`^3`(1.424)·`^5`(1.802)는 정본이 *"이 화면이 안 써서 만들지 않았다 — 죽은 계단을 두지 않는다"* 라 한 대로 의도적 공백. spec↔impl 무결점.

"1.125^1=1.125 ≡ 현행 원고 본문 1.12rem → 가장 많이 읽는 글자가 안 움직인다" — `--type-reading` 흡수열이 `1.08·1.12`(L52)로 기록돼 있어 주장 성립.

### 2. 가드 — 3셀 양방향, 뮤테이션 5종(작업자 주장) 전부 독립 재현

`npx vitest run src/typeScale.test.ts` at HEAD = **3 passed**. 뮤테이션은 스크립트로 M1–M5 순차 적용, 매번 `diff -q` byte-identical 복원 + `git status --short` empty 확인:

| # | 적용 diff | file:line | 결과(독립 실측) | 작업자 주장 |
|---|---|---|---|---|
| M1 | `--type-small: 0.889rem`→`0.9rem`(지수 주석 유지) | styles.css:142 | cell 1 **FAIL** (`derives every step from the 1.125 ramp`) | ✓ under-strict |
| M2 | 같은 줄 `1.125^-1`→`1.125^-2`(값 유지) | styles.css:142 | **동일 cell 1 FAIL** | ✓ over-strict |
| M3 | `.workspace-status` 의 `var(--type-meta)`→`0.78rem`(한 블록만) | styles.css:790 영역 | cell 3 **만 FAIL** (`keeps the migrated rules on the scale`) | ✓ cell 3 단독 |
| M4 | `--type-huge: 3.653rem; /* 1.125^11 */` 추가(미사용) | styles.css:147 뒤 | cell 2 **FAIL** (`leaves no step declared that nothing draws with`) | ✓ 죽은 계단 |
| M5 | `MIGRATED` 에서 `".workspace-status": "meta",` 행 삭제 | typeScale.test.ts:59 | **3 passed — 안 물음** | ✓ 공식 한계 |

**5종 전부 작업자 주장과 정확히 일치.** M3 가 셀 3 *하나만* 물은 것도 재현 — 작업자가 기록한 "M3′ (전역 치환→블록 한정으로 좁힘)" 교훈이 실제로 지켜진 스코프. M1·M2 가 같은 셀을 물며 값·지수를 같은 줄에서 읽는 설계가 양방향으로 작동함을 증명.

**★ 한계(M5)는 계약 수준에서 이미 정본이 못 박은 것이다** — L420–422 가 *"가드는 목록이 이름을 부른 선택자만 본다 — 목록에서 행을 지우면 아무 셀도 실패하지 않는다(뮤테이션 M5 실측)"* 라 적고, 처방(화면 슬라이스가 자기 선택자를 목록에 더한다)도 같이 있다. 작업자가 이것을 숨기지 않고 정본·work_log·test 파일 머리말 세 곳에 반복 기록했다.

### 3. 이관 충실성 — `MIGRATED` 42행 == 실제 토큰 사용처 42곳 (단계별 정확)

`var(--type-*)` font-size 선언 수(전수 grep)와 `MIGRATED` 행 수가 **단계별로 정확히 일치**:

| 토큰 | 실제 사용처(grep) | MIGRATED 행 수 |
|---|---|---|
| micro | 6 | 6 |
| meta | 15 | 15 |
| small | 15 | 15 |
| base | 1 | 1 |
| reading | 2 | 2 |
| subhead | 1 | 1 |
| panel | 1 | 1 |
| title | 1 | 1 |
| **계** | **42** | **42** |

즉 `MIGRATED` 목록은 파일 전체의 토큰 사용처를 **빠짐없이** 열거한다(숨은 사용처 0). 작업자 "선언 42곳을 스냅" 주장이 재현됨. 쉼표 그룹 선택자(`.writing-block, .writing-hint` 등)는 CSS 한 선언 블록 = MIGRATED 한 행으로 대응.

### 4. 위계 편집 — 세 곳 전부 코드에 존재

- `.editor-heading h1`: `font-size: var(--type-title)` (`styles.css:986–987`). 종전 `clamp(2.4rem,5vw,4.2rem)` → 2.027rem.
- `.editor-page`: `padding-top: clamp(var(--space-8), 4vw, 3rem)` (`styles.css:785–787`). `--space-8`=2rem 이라 정본 `clamp(2rem,4vw,3rem)` (L415) 과 등가.
- `.editor-heading`: `margin-bottom: var(--space-6)` (`styles.css:781–783`). 종전 2rem.
- "제목이 본문의 3.7배": 종전 4.2/1.12 = **3.75** ✓. 변경 후 2.027/1.125 = **1.80×** — 원고 본문 위의 위계가 合理로 정정.

### 5. 회귀 — 기준선 독립 재현

- frontend 전수 `npx vitest run`: **Test Files 24 passed (24) · Tests 309 passed (309)**, exit 0. 작업자 309/24 일치. 신규 `typeScale.test.ts`(3) + 형제 `designTokens.test.ts`(3, 무영향) 포함. Duration 408s(작업자 383s, 머신 편차).
- 백엔드 prod **0줄**: `git show --stat d4bf832` = `frontend/src/{styles.css,typeScale.test.ts}` 두 파일만. 백엔드 파일 0.
- 백엔드 CSS-읽기 가드 `test_design_token_provenance.py`: **5 passed / 89 subtests**, 4.71s. — 이것이 styles.css 를 읽는 유일한 백엔드 셀이다. `--type-*` 리터럴 rem 은 primitive 정규식 `(blue|slate|danger|warn|ok)-\d+`(L59) 에도, semantic `var(--)` 참조에도(L53 주석) 안 걸려 정상 green. "영향 없음" 주장 성립.

### 6. 측정 주장 재측정 — 대부분 일치, **둘은 틀렸다(기록 정정 필요)**

| 주장 | 독립 실측 | |
|---|---|---|
| 12종이 0.72~0.92rem 한 뼘 | 부모 커밋 전역 [0.72,0.92] 13종 중 0.74(=타 표면 리터럴로 잔존) 제외한 12종 흡수열 | ✓ 정합 |
| 남은 리터럴 **45곳** | `grep -cE 'font-size:\s*(0\.|1\.|clamp)'` = **45** | ✓ 정확 |
| 남은 리터럴 **22종** | distinct = **22** | ✓ 정확 |
| 패턴 스윕 "**0.78rem 17곳**" | `grep -cE 'font-size:\s*0\.78rem'` = **11** | ✗ **틀림(11≠17)** |
| 출발점 "**19종**" | 흡수열 distinct = **18** | ⚠ 부정합(아래) |

**★ 0.78rem 17곳은 틀렸다.** 실제 `font-size: 0.78rem` 선언은 **11곳**(직접 grep, 행 번호까지 확인). 작업자가 같이 뭉침이라 한 `0.82rem 8곳`은 정확(8). 작업자의 *총합* 45는 맞으므로 — 0.78rem 이 17 이라면 총합은 51 이 되어야 한다(내부 모순). 0.84·0.86 등 다른 후보와 헷갈린 것으로 보인다.

**19종 vs 18종.** 작업자가 스스로 기록한 흡수열(micro←0.72·0.75·0.76 / meta←0.78·0.8·0.82·0.84 / small←0.84·0.85·0.86·0.88·0.9·0.92 / base←1 / reading←1.08·1.12 / subhead←1.35 / panel←1.65 / title←clamp)의 distinct 합집합은 **18종**이다(0.84 가 meta·small 양쪽에 겹쳐 한 번만 센다). 슬라이스 전 값이 이미 토큰으로 교체돼 완전 재도출은 불가하나, 작업자 본인의 분해표가 19 가 아닌 18 을 가리킨다. "0.84 두 번 세기"로 19 가 나온 듯하다. 둘 다 **본문 서술의 정밀도 결함**이지 코드·가드 결함은 아니다.

### 7. 탐침(M6) — cell 1 정규식의 맹점 실존

cell 1 은 선언 줄의 `/* 1.125^n */` **주석이 있는 줄만** 잡는다(`/^\s*(--type-[a-z]+):\s*([\d.]+)rem;\s*\/\*\s*1\.125\^(-?\d+)/`). 주석을 통째로 떼면? — `--type-small` 줄에서 주석만 제거(값 0.889 유지, 소비도 유지) → **3 passed**. 즉 주석 없는 토큰은 램프 검사에서 조용히 빠진다. 미래의 `--type-foo: 0.83rem;`(주석 없음, 어딘가 소비)은 cell 1 이 영원히 검증하지 않는다. 현재 8 토큰은 모두 주석이 있어 당장 문제 없다.

## Issues / Risks

### Blocking (계약 위반) — **0건**

없다. 정본(§10.3 정본 표)과 코드가 무결점으로 일치하고, 가드는 양방향으로 물며, 이관은 충실하고, 회귀는 green, 백엔드 prod 는 0줄. 정본이 정한 M5 한계는 작업자가 정본·work_log·test 머리말에 반복 명시했고 처방도 갖춰져 있다.

### Hardening (비차단, 정본이 요구하지 않는 보강)

- **H1 — 주석 없는 토큰이 cell 1 을 빠져나간다(M6 실측).** cell 1 정규식이 `1.125^n` 주석에 의존하므로, 주석 없이 선언된 `--type-*` 은 램프 검사에서 안 보인다. 보강 후보: *"선언된 모든 `--type-*` 은 `1.125^n` 지수 주석을 가져야 한다"* 는 셀(정규식의 silent-skip 폐쇄). M5 와 같은 계열(가드는 자기가 짚은 것만 본다)이며, 현재 8 토큰은 전부 주석이 있어 즉시 위험은 없다. 정본이 요구하지 않았으므로 비차단.

## 기록 정정 권고 (비차단 — 코드·가드가 아니라 서술 정밀도)

정본 §10.3·work_log·CHANGELOG 의 아래 수치가 실측과 다르다. 코드에는 영향 없고, 가드에도 영향 없다.

1. **"0.78rem 17곳" → 11곳** (work_log §패턴스윕). 총합 45 는 맞다.
2. **"19종" → 18종**(흡수열 distinct). 브리프 본문·CHANGELOG 도 19 로 되 있어 같이 정정.

## Verdict

**합격** — 차단 결함 0. 스케일은 계산대로 정확하고(8/8), 가드는 양방향으로 물며(뮤테이션 5종 전부 독립 재현), 이관 목록은 실제 토큰 사용처 42곳과 단계별 정확히 일치(숨은 사용처 0), 위계 편집 3곳은 코드에 존재하고 "3.7배" 주장은 성립하며, frontend 309/24 green·백엔드 prod 0줄·CSS-읽기 백엔드 가드 green. M5 한계는 정본이 이미 못 박았고 작업자가 투명하게 기록했다. 0.78rem(17→11)·19(→18) 측정 정밀도 니트와 H1(주석 없는 토큰 맹점)은 비차단이나, "의심하고 또 의심하라"는 요청에 맞춰 위에 명시한다.

## Outstanding items (오너 다음 단계에 영향)

1. **육안 확인 미수행 — 프론트 재빌드가 선행.** 변경은 CSS 에만 있어 컨테이너 이미지에 반영돼 있지 않다. `docker compose build frontend && docker compose up -d frontend` 후 `DraftEditor` 확인. 볼 것(정본 L425 가 "가드가 안 무는 슬라이스라 육안 확인이 유일한 검증" 이라 못 박은 자리): 제목이 원고보다 작아졌는가 · 첫 화면에 원고가 들어오는가 · 레일 12종이 3계단으로 정리돼 보이는가. 작업자가 이것을 솔직하게 유예로 기록함.
2. **백엔드 전수 회귀 미갱신.** prod 0줄이고 CSS-읽기 가드는 green 이나, HANDOFF 의 백엔드 기준선 `2271/1/2430` 은 어제 값 그대로(이 세션이 재측정 안 함). 수치 갱신이 필요하면 `docker compose -f docker-compose.test.yml up -d` 후 전수.
3. **빌드/CSS 크기 미재측정.** 작업자 "CSS 30.94→31.60 kB · 진입 421.78 kB 무변 · 703 modules" 는 이 세션이 빌드 아티팩트로 재생산하지 않았다. 원시 소스 delta 42031→44945 바이트(+2914, 대부분 doc 주석 블록)로 방향은 합리적이고, 진입 번들 무변은 JS/TS 변경이 0(d4bf832 는 CSS + 비-앱-진입 .test.ts)이라 근거가 서 있으나 — 보고된 수치 자체는 미검증.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
git status --short                          # empty 전제
git show --stat d4bf832                      # 파일 2개(frontend 만)
# 스케일 산술·이관·위계·측정:
cd frontend
grep -oE 'font-size:\s*[^;]+' src/styles.css | sed 's/font-size:\s*//' | sort | uniq -c   # 42 var(--type-*) + 45 리터럴
grep -cE 'font-size:\s*0\.78rem' src/styles.css                                            # → 11 (17 아님)
git show d4bf832~1:frontend/src/styles.css | grep -oE 'font-size:\s*[^;]+' | sed 's/font-size:\s*//' | sort -u | wc -l  # 부모 distinct
# 기준선 회귀:
npx vitest run                               # 24 files / 309 passed
# 백엔드 CSS-읽기 가드:
cd .. && PYTHONPATH=. python3 -m pytest tests/test_design_token_provenance.py -q   # 5/89
# 뮤테이션 M1–M5 (트리 clean·커밋됨 → git checkout 복원 + cp 백업 + diff 증명 + trap):
bash docs/verifications/2026-08-12/repro_typescale_mutations.sh
```

M6 탐침(주석 제거, 본 기록 §7)은 같은 패턴으로: `--type-small` 줄에서 `/* 1.125^-1 … */` 만 삭제 → `npx vitest run src/typeScale.test.ts` → **3 passed**(맹점) → `git checkout -- src/styles.css`.
