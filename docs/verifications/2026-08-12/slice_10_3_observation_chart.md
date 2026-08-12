# Slice 10.3 관측 차트 독립 검증

## Subject metadata

- 날짜: 2026-08-12
- 요청자: 오너 — *"다음작업 검증해줘. 관측 차트 완료. 재보고 나서 손댔더니 결론이 예상과 달랐습니다 — 그게 이 슬라이스의 핵심입니다."*
- 검증자: 이 세션 (구현자와 다른 세션). 10.0·10.1·10.2·10.3(타이포) 에 이어 같은 Phase.
- 대상: Phase 10 Slice 10.3 관측 화면 차트 — recharts 색을 `:root` 로 되돌리고 chrome 을 앱 토큰에 맞춤. 커밋 `0aa787f`(구현) · `b7c6453`(TS 가드 확장) · `b60e90d`(기록).
- 정규 스펙(정본): [`docs/plans/10-frontend-design-system-decisions.md`](../../plans/10-frontend-design-system-decisions.md) §Follow-up "recharts 차트는 옛 팔레트에 하드코딩돼 있다"(L450–462) + 슬라이스 표 10.3 행(L383). 색 리터럴은 `frontend/src/observability/{ObservabilityDashboard.tsx,chartColors.ts}` · `frontend/src/styles.css:116–118`.
- 검증 출처: `git status --short` empty · HEAD = `b60e90d` (트리 clean, 커밋됨).

## Scope

1. **★ 슬라이스의 핵심 — CVD/ΔE 실측 4종.** 작업자가 *"재보고 뒤 결론이 예상과 달랐다"* 는 바로 이것. 보고 수치를 dataviz 검증기로 **전부 독립 재계산**.
2. **chrome 수정(④)** — 종전 막대 stroke `#f4f0e7`(옛 페이지 배경)이 새 배경에서 크림 테두리로 보이던 결함. grid·axis·간격이 앱 토큰으로, 간격이 `--surface-raised` 로.
3. **구조** — `chartColors.ts` 가 `getComputedStyle` 로 `:root` 를 읽고 fallback 을 두지 않는 점 · `chartColors.test.ts` 가 그 사각지데를 메우는지.
4. **TS 가드 확장** — `designTokens.test.ts` 의 색 리터럴 금지가 TS 소스까지 넓어갔는지(현재 0건).
5. **뮤테이션 C1–C5** — 단독 물림(C3·C4·C5) 과 C5(=이 슬라이스가 고친 결함의 재발) 독립 재현.
6. **회귀·번들** — frontend 313/25 · 백엔드 prod 0줄 · CSS 31.70 · 관측 lazy 387.03 · 진입 421.78 무변.
7. **이전 검증의 폐쇄 확인** — `e5c0fac`(내 H1 맹점 폐쇄) · `11f8bb6`(내 측정 니트 정정·인덱스 가드 실패 폐쇄) 이 내 지적을 올바르게 닫았는지.

## Methodology

정본 → 코드·실측·뮤테이션으로 재도출(보고를 사실로 받지 않음).

- **CVD/ΔE**: 작업자가 쓴 **같은 dataviz 스킬 검증기** `scripts/validate_palette.js`(스킬 기본 `--mode light --surface "#f6f9fc"` = `--surface-raised`). 4케이스 재실행. 규칙: 정상 시야 최악 쌍 ΔE < 15 = hard FAIL · CVD ΔE ≥ 8 목표(6–8은 2차 인코딩 전제).
- 토큰 hex: `grep -E '\-\-(blue|slate|danger|warn)-(50|600|700)\s*:' styles.css`. `--blue-600=#006ebe` · `--surface-raised=--slate-50=#f6f9fc` · `--danger-600=#b63132` · `--danger-700=#951e22` · `--warn-700=#7b5100`.
- 대시보드 리터럴: `grep -E '#[0-9a-fA-F]{3,8}|rgba?\(' ObservabilityDashboard.tsx`(현재 0건) · 종전 결함은 `git show 0aa787f~1:...ObservabilityDashboard.tsx`.
- 회귀: `cd frontend && npx vitest run` (전수) · 가드 단독 · `npm run build`(번들 수치 직접 재생산) · 백엔드 `PYTHONPATH=. python3 -m pytest tests/test_design_token_provenance.py tests/test_docs_indexes.py`.
- **뮤테이션**: 트리 clean·커밋됨 → `git checkout --` 복원 + `cp` 백업 + `diff -q` byte-identical 증명 + trap. 매번 두 가드(chartColors·designTokens)를 **함께** 돌려 단독 물림을 확인. 스크립트: [`repro_chart_mutations.sh`](./repro_chart_mutations.sh).

## Findings

### 1. ★ 핵심 실측 — CVD/ΔE 4종 전부 독립 재현 (보고 수치와 정확 일치)

dataviz 검증기를 `--surface "#f6f9fc"`(=`--surface-raised`, 차트가 앉은 면) 로 직접 실행:

| 케이스 | 색 | 결과 | 보고 | |
|---|---|---|---|---|
| **P 채택** | `#006ebe,#8c1f4a,#9a6a24` | ALL PASS · 최악 CVD **15.4**(deutan) · 정상 **19.7** | 6검사 PASS·CVD15.4·정상19.7 | ✓ |
| **OLD 종전** | `#1a6d99,#8c1f4a,#9a6a24` | ALL PASS · 최악 CVD **12.6**(deutan) | 종전 최악CVD 12.6 | ✓ |
| **F1** | `#006ebe,#b63132,#7b5100`(blue·danger-600·warn-700) | **FAIL** · 정상 **13.9** · CVD **4.5**(protan) (+chroma) | 정상13.9·protan4.5 FAIL×3 | ✓ |
| **F2** | `#006ebe,#951e22,#7b5100`(blue·danger-700·warn-700) | **FAIL** · 정상 **12.2** · CVD **3.3**(deutan) (+chroma) | 정상12.2·deutan3.3 FAIL×3 | ✓ |

**네 수치 전부 정확 재현.** 슬라이스의 핵심 논리 — *"계열 팔레트를 앱 상태색으로 통일하면 색각 이상 사용자에게 두 계열이 한 덩어리로 보인다(warn-700↔danger 가 뭉친다). 계열 팔레트는 UI 상태색과 다른 물건이다"* — 가 성립한다. `styles.css:101` 주석 *"warn-700↔danger-600 정상 ΔE 13.9·protan 4.5"* 도 byte 일치.

개선 ③ (#1a6d99 → `--blue-600`=#006ebe)도 재현: 종전엔 최악 쌍이 `#8c1f4a↔#1a6d99`(12.6) 였는데, 성공만 blue-600 으로 옮기자 최악 쌍이 `#9a6a24↔#8c1f4a`(15.4) 로 바뀌며 여유가 생겼다. **취향이 아니라 측정**이라는 주장이 맞다. ★ 주의: F1/F2 는 ΔE 외에 **chroma floor** 도 추가로 FAIL(#7b5100=warn-700 chroma 0.099<0.1). 작업자 "FAIL ×3" 은 이 3개 체크(정상·CVD·chroma)를 가리키며 정확하다 — 다만 prose엔 chroma 를 명시 안 했다(비차단).

### 2. chrome 수정(④) — 종전 결함 실존 · 현재 0 리터럴

- **종전(0aa787f~1)** `ObservabilityDashboard.tsx`: grid `stroke="#d8d0c1"`(:222) · 축 `#746f65`(:223–224) · **막대 stroke `#f4f0e7`**(:231/239/247 = 옛 페이지 배경 → 새 배경 위 크림 테두리) · `:53` 주석 *"Validated against this app's paper surface (#f4f0e7)"*(무효화된 검증 전제). 결함 실존 확인.
- **현재**: 색 리터럴 **0건**. `readChartColors()`(=getComputedStyle `:root`, fallback 없음) 로 grid·axis·막대 fill/stroke 를 읽고, 막대 `stroke={color.markGap}` = `--surface-raised`(styles.css:2144 `.chart-frame` 배경과 동일). ④ "간격은 `--surface-page` 가 아니라 `--surface-raised`(차트가 `.chart-frame` 안에 앉으니까)" 코드로 확인.

### 3. 구조 — `chartColors.ts` · 사각지대와 가드

- `CHART_TOKENS` 6키: success/providerError/parseError(=`--chart-*`, 차트 전용) + grid(`--border-hairline`)/axis(`--text-muted`)/markGap(`--surface-raised`, 앱 일반 토큰). "격자·축·간격은 차트만의 색이 아니라 앱의 선과 잉크" 주장 성립.
- fallback 없음 — `chartColors.ts:14–18` 가 8.4 `.writing-confirm` 사고(조용히 배경 없이 렌더)와 동일한 구조라 명시. 대신 `chartColors.test.ts` 가 메운다: jsdom 은 스타일시트 로드 안 함 → 읽기 전부 빈 문자열 → recharts `fill=""` 로 예외 없이 그림 → 관측 15셀 전부 green(문구·역할 단정). 그래서 **별도 파일이 필요**라는 주장이 회귀로 증명됐다(15셀은 색이 빠져도 green).

### 4. TS 가드 확장 — `designTokens.test.ts` 4셀, 신규 "TS 소스 색 금지"

`b7c6453` 이 더한 셀 *"keeps colour out of the TypeScript sources too"* 는 `.ts/.tsx`(단, `.test.` 제외) 를 walk 하여 주석을 지우고 `#hex|rgba?()` 리터럴을 찾는다. 목록이 비면 공허 통과를 막는 `length > 0` 가드도 있다. 현재 **0건**(대시보드 직접 grep 으로도 0건). 작업자가 "이번에 몸으로 겪어 넓혔다" 는 10.3 의 사각지대(styles.css 만 읽어 TS 색을 못 본다)가 제대로 폐쇄됐다.

### 5. 뮤테이션 C1–C5 — 전부 재현, C3·C4·C5 단독 물림 확인

두 가드 파일을 **함께** 돌려 다른 셀이 안 물린 것까지 증명(스크립트로 매 뮤테이션마다 `chartColors+designTokens` 동시 실행):

| # | 변형 | 결과(독립 실측) | 작업자 주장 |
|---|---|---|---|
| C1 | `parseError` 토큰 오타(`--chart-parse-eror`) | chartColors **3셀 전부** FAIL | ✓ 3셀 전부 |
| C2 | `:root` 에서 `--chart-provider-error` 삭제 | chartColors **cell 1·3** | ✓ 1·3 |
| C3 | `--chart-parse-error` → 크림슨(#8c1f4a) 동값 | chartColors **cell 3 단독**(series distinct) | ✓ 3 단독 |
| C4 | `--chart-legacy`(미사용) 추가 | chartColors **cell 2 단독**(dead token) | ✓ 2 단독 |
| C5 | 대시보드 `stroke={color.grid}`→`stroke="#d8d0c1"` | **designTokens TS셀 단독** | ✓ 결함 그 자체 재발 |

C5 가 이 슬라이스가 고친 결함(대시보드 리터럴)의 **재발**을 잡는다는 작업자 주장이 정확하다. 단독 물림(C3·C4·C5)도 재현 — 오늘 두 번 "뮤테이션이 넓어 셀 귀속이 흐려지는" 실수를 한 뒤 이번엔 처음부터 좁게 잡았다는 주장과 일치.

### 6. 회귀·번들 — 전부 독립 재현

- frontend 전수: **Test Files 25 · Tests 313**, exit 0. 작업자 313/25 일치(typeScale 3·chartColors 3·designTokens 4 포함). 425s.
- 백엔드 prod **0줄**: `git show --stat 0aa787f b7c6453` = 백엔드 파일 0.
- 백엔드 CSS-읽기 가드 `test_design_token_provenance.py`: **5 passed / 90 subtests** green. `--chart-*` 리터럴 rem/hex 는 primitive 정규식·semantic `var(--)` 참조 모두에 안 걸려 정상. (★ "24/367" 전체 묶음은 작업자의 정확한 pytest 호출을 모르면 단일 수치로 재현 어려우나, 백엔드 코드 0줄이므로 정의상 무영향.)
- **번들(내가 `npm run build` 로 직접 재생산)**: CSS **31.70 kB** ✓ · 관측 lazy **387.03 kB** ✓(`chartColors` 가 lazy 경계 안) · 진입 **421.78 kB** 무변 ✓ · 704 modules.

### 7. 이전 검증의 폐쇄 — 내 지적을 올바르게 닫았다

- **`e5c0fac`(내 H1 폐쇄)**: cell 1 앞에 "선언된 모든 `--type-*` 이 지수 주석을 달고 있는지" 단정을 추가. 내 **M6 탐침(주석만 제거) 재실행 → cell 1 FAIL**(종전 3 passed). 맹점이 닫혔다. 단독 물림.
- **`11f8bb6`(내 니트 정정·인덱스 가드)**: ① `0.78rem` 17→**11곳** 정정(Issue 3 기록) ② "19종"→**18종** 정정(근원: `0.84` 이중 집계, 내 분석과 동일) ③ 내 검증 커밋(`4f67779`)이 올리지 않은 README 헤더 수치(237건·49일·합격168) 갱신 → `test_docs_indexes.py` **13/247 green** 으로 폐쇄 확인.

## Issues / Risks

### Blocking (계약 위반) — **0건**

정본(Follow-up "계열 팔레트를 새 배경에 대해 다시 검증")이 요구한 대로: 새 표면(`--surface-raised`)에서 재검증했고(★ 핵심 실측 4종으로 독립 확인), 계열 팔레트를 앱 상태색과 **별개로 유지**했으며(통합 시 CVD FAIL 이 그 이유), 검증 명령·결과를 `styles.css:104–113` 주석에 남겼다. 가드는 양방향·단독 물림, 회귀 green, 백엔드 prod 0줄.

### Hardening (비차단)

- **H1 — CVD 분리 자체는 자동 가드가 아니다.** `chartColors.test.ts` cell 3 은 세 계열이 **서로 다른 값**인지만 잠그고(Set size), ΔE/CVD 통과 여부는 잡지 않는다. 작업자는 의도적이다 — *"검증기를 셀에 옮기면 검증기와 갈리는 두 번째 정본이 생긴다"*(`chartColors.test.ts:56–65`). 즉 누군가 `#8c1f4a`/`#9a6a24`/표면을 바꾸면 회귀는 조용하고 CSS 주석만 낡는다. 현재 완화: cell 3 이 복붙 충돌(가장 흔한 사고)은 잡고, 주석에 재실행 명령이 있다. 정본이 ΔE 자동화를 요구하진 않으므로 비차단이나, **palette 를 건드는 다음 슬라이스에 재실행이 리뷰 체크리스트에 있어야 한다.**

- **H2 — `<Tooltip>`/`<Legend>` 가 recharts 기본 스타일.** 회색 테두리·흰 배경(우리 코드에 리터럴이 없어 가드는 조용). 작업자가 솔직하게 비차단으로 올린 항목이며 확인: `ObservabilityDashboard.tsx:226–227,263` 에 존재. 육안 확인 때 같은 계통인지 볼 자리.

## Verdict

**합격** — 차단 결함 0. 슬라이스의 핵심인 CVD/ΔE 실측 4종을 작업자가 쓴 **같은 검증기로 전부 재계산해 정확히 일치**했고(채택안 PASS·종전 12.6·개선 12.6→15.4 · 상태색 통제안 F1/F2 FAIL), "재보고 뒤 예상과 달라진 결론"이 실측 위에 서 있다. chrome 결함(막대 크림 테두리)은 종전 커밋에서 실존 확인·현재 0 리터럴·간격 `--surface-raised` 적용. 가드는 C1–C5 양방향·C3/4/5 단독 물림(C5=결함 재발). 회귀 313/25 · 백엔드 prod 0줄 · 번들 31.70/387.03/421.78 직접 재생산. 이전 검증의 H1·측정 니트·인덱스 가드도 올바르게 폐쇄됐다. H1(CVD 미자동화)·H2(Tooltip 기본 스타일)는 비차단이나 위에 명시.

## Outstanding items

1. **육안 확인 — Phase 10 말로 미룸.** 회귀가 프로덕션 CSS 를 거의 안 물어 시각 결함이 회귀로 드러나지 않는다(작업자 기록대로). 이 차트 변경도 CSS·TS 에 있어 컨테이너 이미지에 반영됐으려면 `docker compose build frontend && up -d frontend` 선행. 볼 것: 막대 크림 테두리가 없어졌는가 · 계열 3색이 구별되는가 · Tooltip/Legend 가 화면 톤과 어울리는가(H2).
2. **백엔드 전수 회귀 미갱신** — 기준선 2271/1/2430 은 8/11 값. prod 0줄·CSS 가드 green 이나 수치 갱신은 별도.
3. **H1 재실행 규칙** — 다음 palette 변경 시 `validate_palette.js` 재실행이 리뷰 필수(자동 가드가 아니므로).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
git status --short                          # empty 전제
git show --stat 0aa787f b7c6453              # 백엔드 파일 0
# ★ 핵심 실측(dataviz 스킬 검증기):
SKILL=/tmp/claude-1000/bundled-skills/2.1.228/9e81b2d9055ee06a82295c39870718be/dataviz
node "$SKILL/scripts/validate_palette.js" "#006ebe,#8c1f4a,#9a6a24" --mode light --surface "#f6f9fc" --pairs all   # P: PASS, CVD15.4, 정상19.7
node "$SKILL/scripts/validate_palette.js" "#1a6d99,#8c1f4a,#9a6a24" --mode light --surface "#f6f9fc" --pairs all   # OLD: PASS, CVD12.6
node "$SKILL/scripts/validate_palette.js" "#006ebe,#b63132,#7b5100" --mode light --surface "#f6f9fc" --pairs all   # F1: FAIL, 정상13.9, protan4.5
node "$SKILL/scripts/validate_palette.js" "#006ebe,#951e22,#7b5100" --mode light --surface "#f6f9fc" --pairs all   # F2: FAIL, 정상12.2, deutan3.3
# 회귀·번들:
cd frontend && npx vitest run                                  # 25 files / 313 passed
npm run build                                                  # CSS 31.70 · lazy 387.03 · 진입 421.78
cd .. && PYTHONPATH=. python3 -m pytest tests/test_design_token_provenance.py tests/test_docs_indexes.py -q   # green
# 뮤테이션 C1–C5 (트리 clean·커밋됨 → git checkout 복원 + cp 백업 + diff 증명 + trap):
bash docs/verifications/2026-08-12/repro_chart_mutations.sh
# H1 폐쇄 재확인(e5c0fac): --type-small 줄에서 지수 주석만 제거 → typeScale cell 1 FAIL
```
