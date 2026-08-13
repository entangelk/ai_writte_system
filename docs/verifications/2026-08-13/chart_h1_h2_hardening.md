# 차트 H1/H2 보강 — 검산 출처 잠금 · overlay 계통 편입

## Subject metadata

- **날짜**: 2026-08-13 (베타, 독립 검증 세션)
- **대상**: 차트 검증(`e124879`, 2026-08-12 합격)이 비차단으로 올린 **H1**(CVD 재실행 출처가 자동 가드가 아님)·**H2**(`<Tooltip>`/`<Legend>` recharts 기본 스타일)를 보강한 `444ab1b`(H1 출처 가드 + H2 툴팁/범례 계통 편입) · `f724fce`(H2 overlay 회귀 가드). 두 커밋은 `e124879` **뒤**에 붙어 미검증이었다.
- **정규 스펙**: [`10-frontend-design-system-decisions.md`](../../plans/10-frontend-design-system-decisions.md) §Follow-up(recharts 차트) + `e124879` 의 H1·H2 비차단 지적.
- **소스**: 커밋 `444ab1b`·`f724fce`. HEAD `08aed1b`(오늘 부채 ①② 위)에서 검증 — 두 커밋의 CSS·TS 변경은 부채 ①② 가 건드리지 않은 표면이다.

> **전제 정정 (메타)**: 오너가 건넨 "미검증 5커밋" 중 `e5c0fac`·`b7c6453` 은 이미 `e124879`(차트 검증)가 커버했다 — `e124879` Subject 가 `b7c6453` 을 검증 커밋으로 명시하고 §5 뮤테이션 C5 로 그 가드를 물었으며, §7 이 `e5c0fac` 의 맹점 폐쇄를 "M6 재탐침 → cell 1 FAIL"로 확인했다. **진짜 미검증은 3개**(이 슬라이스 2개 + `2c6eb9e`).

## Scope

1. **H1 셀**("still holds the exact palette the recorded validation covered"): ΔE를 재구현하지 않고 출처 연결 3종(계열색↔주석 팔레트·검산 표면↔`--surface-raised`·그 토큰↔`.chart-frame` 배경)을 잠그는지.
2. **H2 변경**(툴팁/범례에 `tooltipStyle(color)` 적용)과 **H2 셀**(모든 overlay 가 스타일 prop 을 갖는지 전수).
3. 회귀·번들.

## Methodology

clean-tree 분기(`git status --short` 공백 → 변형 → 단독 실행 → `git checkout --` 복원 → `md5sum` 바이트 대조). 기준 해시: `chartColors.test.ts=93700785…`·`chartColors.ts=2ebba9d5…`·`ObservabilityDashboard.tsx=239af552…`·`styles.css=a7e28ea9…`.

```bash
cd frontend && npx vitest run src/observability/chartColors.test.ts   # 기준 5 passed
```

## Findings

### F1. H1 셀 — 출처 연결이 양쪽으로 무는다 (양방향)

셀은 `styles.css:104` 주석의 검산 명령에서 팔레트(`#006ebe,#8c1f4a,#9a6a24`)·표면(`#f6f9fc`)을 읽고, (1) 계열색 3개(resolveToken 으로 var 한 겹 따라감) ≡ 팔레트, (2·3) `.chart-frame` 배경(줄 2124 `var(--surface-raised)`→`#f6f9fc`) ≡ 표면을 단정한다.

| # | 변형 | 결과 | 어긋난 연결 |
|---|---|---|---|
| H1-a | `--chart-parse-error: #9a6a24`→`#7b5100` | **H1만 FAIL**(`#7b5100`≠`#9a6a24`) | ① 계열색↔주석 |
| H1-c | `.chart-frame` 배경 `--surface-raised`→`--surface-card` | **H1만 FAIL**(`#ffffff`≠`#f6f9fc`) | ③ 프레임↔표면 |

둘 다 나머지 4셀 통과. 연결 ①·③ 이 독립적으로 무는 것을 실증(② 표면↔`--surface-raised` 값은 ③과 같은 축). 값·주석·프레임 중 어느 하나가 움직여도 실패 → **"지금 값이 그때 검산한 값인가"** 가 잠긴다.

**잔여 한계(비차단, `e124879` H1 과 동일)**: 값↔주석 일치는 잠그지만 **그 값이 CVD 를 통과하는지**는 안 본다(ΔE 미재구현 — 두 번째 정본 방지). 값과 주석을 함께 바꾸면 셀은 통과하지만 CVD 는 FAIL 일 수 있다. 완화: 복붙 충돌(가장 흔한 사고)은 잡고, 주석에 재실행 명령이 있다. **palette 를 건드리는 다음 슬라이스에 `validate_palette.js` 재실행이 리뷰 필수**인 점은 변함없다.

### F2. H2 — overlay 가 계통으로 들어왔고, 회귀를 잠근다

- **변경**(`444ab1b`): 두 `<Tooltip>`가 `contentStyle={tooltipStyle(color)}`(카드면 `--surface-card`·가는 테두리·본문 글자)를, `<Legend>`가 `wrapperStyle={{color: color.overlayText}}`를 받는다. `tooltipStyle()` 가 `chartColors.ts` 에 한 곳 — 두 차트가 서로 다른 툴팁을 갖는 재발을 구조로 막는다.
- **셀**(`f724fce` "dresses every recharts overlay"): `ObservabilityDashboard.tsx` 소스를 읽어 **모든** `<Tooltip>`·`<Legend>` 가 각각 `contentStyle=`·`wrapperStyle=` 를 갖는지 전수. overlay 가 0이 되면 공허 통과를 막는 `length > 0` 도 있다.

| # | 변형 | 결과 |
|---|---|---|
| H2-a | 첫 차트 `<Tooltip contentStyle=…/>`→`<Tooltip/>` | **H2만 FAIL**(`['<Tooltip ']`≠`[]`) |

나머지 4셀 통과. "색 안 쓰기"와 "라이브러리 색 쓰기"를 구별 못하던 리터럴 가드의 사각지대를 소스 전수로 메운다.

### F3. 회귀·번들

- `chartColors.test.ts` HEAD = **5 cells**(기존 3 + H1 + H2) 전부 green. 전체 frontend **323/27**(오늘 부채 ①② 포함) green — 두 셀이 기존 회귀를 한 건도 깨뜨리지 않는다.
- 번들: 관측 lazy **387.03 → 387.43 kB**(`chartColors.ts` 가 `tooltipStyle`·overlay 토큰을 얻어 lazy 경계 안에서 커진 값, 오늘 HEAD 빌드로 387.43 재확인). 진입 421.78·CSS 무변(이 슬라이스는 JS·CSS 본문을 안 건드린다).

## Issues / Risks

- **Blocking**: 0.
- **Hardening**: H1 잔여(CVD 미자동화, 위 F1) — `e124879` H1 에서 이미 비차단으로 기록된 것이고 444ab1b 의 설계 선택(ΔE 미재구현)과 일관. 변동 없음.

## Verdict

**합격** — H1 셀은 출처 연결 ①·③ 양쪽에서 무하고(값·주석·프레임 어느 하나 움직여도 실패), H2 셀은 overlay 회귀를 잠근다. 둘 다 단독 물림·회귀 무변. CVD 미자동화는 잔여 비차단(종전과 동일).

## Outstanding items

- palette 변경 시 `validate_palette.js` 재실행은 여전히 리뷰 필수(H1 셀이 값↔주천 일치만 잠그고 CVD 통과는 안 보므로).
- Tooltip/Legend 의 **시각** 적합성(카드면이 차트 톤과 어울리는가)은 Phase 10 끝 육안 확인 대상(`e124879` H2 와 같음).

## Reproduction

```bash
cd frontend && npx vitest run src/observability/chartColors.test.ts   # 5 passed
# H1-a: styles.css 의 --chart-parse-error 값을 #7b5100 등으로 → cell "still holds..." FAIL
# H1-c: .chart-frame 배경을 var(--surface-card)로 → 같은 셀 FAIL (#ffffff≠#f6f9fc)
# H2-a: ObservabilityDashboard.tsx 의 한 Tooltip contentStyle 제거 → cell "dresses..." FAIL
# 복원마다 git checkout -- + md5sum(93700785…/239af552…/a7e28ea9…) 대조
```
