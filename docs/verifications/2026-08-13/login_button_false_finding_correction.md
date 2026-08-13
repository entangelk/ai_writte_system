# 정문 버튼 "브라우저 기본값" 거짓 발견 정정 — 2c6eb9e

## Subject metadata

- **날짜**: 2026-08-13 (베타, 독립 검증 세션)
- **대상**: 10.4 검증(`33e8783`, 2026-08-12 합격) **뒤**의 `2c6eb9e` — 10.4 가 "정문 버튼이 브라우저 기본값(회색)"으로 보고 넣은 `.login-form button` 규칙이 **거짓 발견 위에 쓰인 코드**였음을 정정하고 전부 되돌림.
- **정규 스펙**: [`10-frontend-design-system-decisions.md`](../../plans/10-frontend-design-system-decisions.md) §10.4 + `33e8783` 의 H1 비차단(버튼 규칙 흩어짐).
- **소스**: 커밋 `2c6eb9e`. HEAD `08aed1b` 에서 검증 — 되돌린 자리는 오늘 부채 ①(버튼 겉모습 통일)가 이어받았다.

## Scope

1. **제거가 깨끗한가** — `.login-form button` 블록(base·hover·disabled)이 잔존/고아 없이 사라졌는지.
2. **정문 버튼이 여전히 스타일되는가** — `<button className="auth-submit">` 가 `.auth-submit`(HEAD 통일 블록)으로 칠해지는지.
3. **거짓 규칙이 왜 해로웠는가** — 특이도 `(0,1,1)` vs `(0,1,0)` override.
4. **★ 구멍이 구조적으로 닫혔는가** — 거짓 규칙이 돌아오면 오늘 `buttonAppearance.test.ts` 가 잡는지(2c6eb9e 가 손으로 닫은 것을 가드가 대체하는가).

## Methodology

`grep` 잔존/참조 확인 + 진짜 컴포넌트 className 확인 + **거짓 규칙 재도입 뮤테이션**(clean-tree 분기, 복원마다 `md5sum a7e28ea9…` 대조).

## Findings

### F1. 제거는 깨끗하다

`grep -n "login-form button" frontend/src/styles.css` = **0건**. `grep -rn "login-form button" frontend/src/` = **0건**(코드·테스트 어디도 참조 안 함 → 고아 없음). `2c6eb9e` diff 가 base·hover·disabled 세 블록을 통째로 지운 것과 일치.

### F2. 정문 버튼은 여전히 칠해진다 — 근거가 가짜였다

- 진짜 컴포넌트 [`AuthGate.tsx:97`](../../../frontend/src/auth/AuthGate.tsx)·`:397` = `<button className="auth-submit">`.
- `.auth-submit` 은 HEAD 통일 블록에 있다(줄 328 base · 345 hover · 357 disabled · 446 padding). `--action-primary`=`--blue-600`=`#006ebe`=**rgb(0,110,190)**.
- **"정정 전후 둘 다 rgb(0,110,190) — 회색이었던 적이 없다"**(2c6eb9e 메시지)가 성립한다. `e124879`/`db9f9c0` diff 모두 `.auth-submit` 이 처음부터 `--action-primary` 였음을 확인.

회색이었던 것은 **하네스** [`10_layout_probe.html`](../../plans/10_layout_probe.html) 의 손으로 쓴 마크업이 `auth-submit` 클래스를 빠뜨려서 — 렌더는 진짜인데 **입력이 가짜**라 "실측 스크린샷" 이라는 가장 믿음직한 형태로 없는 결함이 나온 것. `2c6eb9e` 가 이 함정을 하네스 머리말에 사례와 함께 박았다.

### F3. 거짓 규칙이 왜 해로웠는가 — 특이도 override

넣었던 `.login-form button`(특이도 **0,1,1**)이 `.auth-submit`(**0,1,0**)보다 높아 **덮어썼다** — 패딩(0.78/1.35→0.72/1.5)·`border-radius`(0→4.8px)·`font-weight`(400→700)를 바꾸고 hover 의 `translateY(-1px)`를 없앴다. 요청도 근거도 없는 restyle 이었고, `2c6eb9e` 가 규칙 셋을 전부 되돌렸다. 특이도 산술 (0,1,1)>(0,1,0) 이 "왜 조용히 덮어썼는가"를 설명한다.

### F4. ★ 구멍이 오늘 가드로 구조적으로 닫혔다

`2c6eb9e` 가 손으로 닫은 "흩어진 N번째 사본" 패턴이 오늘 [`buttonAppearance.test.ts`](../../../frontend/src/buttonAppearance.test.ts) 로 잠겼는지 확인 — **거짓 규칙을 그대로 재도입**:

```css
.login-form button { … background: var(--action-primary); cursor: pointer; … }
.login-form button:hover:not(:disabled) { background: var(--action-primary-hover); }
.login-form button:disabled { … }
```

결과 — **cell 1("자리 하나")·cell 2("같은 hover") FAIL**(identity 규칙 2개·hover 규칙 2개). cell 3·4 통과. 즉 2c6eb9e 가 **눈으로** 잡아 손으로 지운 패턴을 오늘 가드가 **자동으로** 잡는다. 거짓 규칙이 돌아오면 회귀가 실패한다.

### F5. 회귀·CSS

`2c6eb9e` = CSS-only 제거라 JS 회귀 무변(작업자 보고 318/26). CSS **31.76 → 31.42 kB**(-0.34) — styles.css@`2c6eb9e` == styles.css@`f022088`(그 사이 CSS 변경 0)이고, 오늘 내가 cp-swap 빌드로 잰 f022088 CSS = **31.42**로 post 상태 재확인(31.76 은 `33e8783` 10.4 검증의 실측값).

## Issues / Risks

- **Blocking**: 0.
- **Hardening**: 없음. 단 **교훈이 저장소에 남는다** — 하네스 머리말(`10_layout_probe.html`)의 "손으로 쓴 마크업은 진짜 컴포넌트가 아니다, className 을 직접 확인하라" 경고. 그리고 이 빈 자리(거짓 발견이 메운 자리)가 오늘 부채 ① 통일 가드로 채워졌다.

## Verdict

**합격** — 제거는 잔존/고아 없이 깨끗하고, 정문 버튼은 `.auth-submit`(항상 `--action-primary`)으로 여전히 스타일된다. "회색이었다"는 발견이 하네스 입력 오류였음을 진짜 컴포넌트 className 으로 확인. 특이도 (0,1,1)>(0,1,0) 이 거짓 규칙의 피해(조용한 restyle)를 설명하고, **거짓 규칙 재도입 시 오늘 `buttonAppearance` 가 cell 1·2 로 잡음**을 실증해 구멍이 구조적으로 닫혔음을 증명했다.

## Outstanding items

- 이 정정과 오늘 부채 ① 의 연결: `2c6eb9e` 는 "관측된 피해 0건" 으로 부채 ① 을 내려놓았으나, 오늘 실측이 그것도 다시 정정했다(transition 없음·hover lift 2:3). 즉 **같은 자리를 두 번** 추렸고, 부채 ① 가드가 그 연결의 종착이다.
- 정문 버튼 시각(padding 0.78/1.35·hover lift)은 Phase 10 끝 육안 확인에 포함.

## Reproduction

```bash
grep -n "login-form button" frontend/src/styles.css                 # 0건
grep -rn "login-form button" frontend/src/                          # 0건
grep -n 'className="auth-submit"' frontend/src/auth/AuthGate.tsx    # 2건 (97·397)
grep -n "auth-submit" frontend/src/styles.css | head                # 328·345·357·446 (통일 블록)
# 뮤테이션: .login-form button { background:var(--action-primary); cursor:pointer; … } 재도입
#   → buttonAppearance cell 1·2 FAIL (구멍 폐쇄). 복원: git checkout -- + md5sum a7e28ea9…
```
