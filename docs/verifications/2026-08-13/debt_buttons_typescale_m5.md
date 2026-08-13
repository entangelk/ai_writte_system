# 부채 ①② 폐쇄 — 기본 버튼 겉모습 통일 · typeScale 이관 목록 M5 한계

## Subject metadata

- **날짜**: 2026-08-13 (베타 머신 — 검증자 세션, 구현자와 다름)
- **요청자**: 오너 ("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?")
- **검증자**: 독립 세션 (구현자가 아님)
- **대상**: 부채 ①② 폐쇄 — `db9f9c0`(기본 버튼 겉모습 다섯 벌 → 한 자리 · 신규 가드 `buttonAppearance.test.ts`) · `f022088`(`typeScale.test.ts` 넷째 셀로 M5 한계 폐쇄) · `08aed1b`(기록). 세 커밋은 서로 독립.
- **정규 스펙**: [`docs/plans/10-frontend-design-system-decisions.md`](../../plans/10-frontend-design-system-decisions.md) (Phase 10) · 오너 결정 D-10.5-b(모션 다섯 곳 통일) · D-10.5-c(③은 육안까지 유예).
- **소스**: 커밋 `db9f9c0`·`f022088`·`08aed1b` (HEAD `08aed1b`, 작업 트리 clean).

## Scope

- **① 캐스케이드**: 통일 규칙이 파일 앞(줄 328)으로 옮겨진 뒤, 뒤쪽 규칙이 7 선택자의 겉모습을 덮어쓰지 않는지. ghost 변형의 특이도 우위. 다른 CSS 파일 · `!important` · `@media` 중첩 가능성.
- **① 시각-diff 주장**: 7 선택자 × base/hover/disabled = 21자리의 before/after 유효 선언 대조가 정확한지.
- **① `buttonAppearance.test.ts`** (4셀): 값이 아니라 규칙성을 재고, 목록을 손으로 들지 않고 스타일시트에서 유도하는지. 양방향 뮤테이션으로 각 셀이 단독 물림.
- **② `typeScale.test.ts` 넷째 셀**: 종전 M5 한계("목록에서 행을 지우면 아무 셀도 안 실패")를 닫는지. 양방향 뮤테이션.
- **원문 전제 정확성**: 구현자 보고 #1("부채 문서 전제가 틀렸다")가 사실인지 — `b97307d`(작업 직전) HANDOFF 원문과 대조.
- **측정**: frontend 323/27 · build modules/진입/lazy · CSS 31.42→30.79. HEAD에서 직접 재측정.
- **패턴 스윕**: 같은 패턴(같은 선언이 흩어져 조용히 갈라지는)이 다른 곳에도 있는지.

## Methodology

모든 뮤테이션은 clean-tree 분기(`git status --short` 공백 확인 후 변형 → 실행 → `git checkout --` 복원 → `git status --short` 공백 **및** `md5sum` 바이트 대조로 원복 확인). 측정 뮤테이션(CSS-pre)은 git 인덱스를 건드리지 않는 `cp` 백업 방식.

```bash
# 기준선 (clean HEAD)
md5sum frontend/src/styles.css   # a7e28ea933a5b208e603c467bcc628c3
md5sum frontend/src/buttonAppearance.test.ts   # 3a840c4d84e525827a5609fb712b51b9
md5sum frontend/src/typeScale.test.ts           # 1433d2e0212edcbab7b5ed7750ead0e9

# 가드 단독 실행 (기준선 green 확인)
cd frontend && npx vitest run src/buttonAppearance.test.ts src/typeScale.test.ts   # 8 passed

# 전수 + 빌드 (HEAD)
npx vitest run                  # 323 passed / 27 files (423s)
npx tsc --noEmit && npm run build   # 704 modules · CSS 30.79 · 진입 421.78 · lazy 387.43 · AdminConsole 8.50

# CSS-pre (변경 전) 독립 측정 — cp 백업 방식 (인덱스 무건드림)
cp frontend/src/styles.css /tmp/head.css
git show f022088:frontend/src/styles.css > frontend/src/styles.css
cd frontend && npm run build    # CSS 31.42 kB
cd .. && cp /tmp/head.css frontend/src/styles.css   # 복원 → md5 a7e28ea… 재확인
```

뮤테이트(6종)는 각각 단독으로 돌려 어떤 셀이 실패하는지 기록(아래 Findings 표).

## Findings

### F1. 원문 전제 정정은 사실이다 (구현자 보고 #1 검증)

`git show b97307d:HANDOFF.md` 줄 163 의 부채 ① 원문:
> "★ **관측된 피해는 0건이다** … **시각을 바꾸지 않고 닫는 길이 있다**: *겉모습*(색·테두리·커서·**transition**)만 한 규칙으로 묶고 패딩은 자리마다 남긴다"

이 문장은 **스스로 모순**이다 — "transition"을 겉모습(통일 대상)으로 열거해 놓고도 "시각 무변"이라 했다. transition이 이미 5벌 동일했다면 통일이 중립이지만, 그렇지 않았다면 통일이 곧 시각 변화다. 구현자가 다섯 블록을 직접 재어 잡은 정정이 맞다 (`db9f9c0` diff 로 실증):

| 자리(변경 전) | transition | hover lift |
|---|---|---|
| `.auth-submit` · `.form-controls button` | bg + transform | 있음 |
| `.editor-actions button` | **없음** | 없음 |
| `.writing-actions`·`.candidate-actions`·`.loop-retry` · `.row-actions button` | bg만 | 없음 |

즉 "피해 0건"이 아니라 **이미 갈라진 채였고 아무도 안 봤을 뿐**. 구현자는 처방이 말하지 않은 자리(모션)를 임의로 정하지 않고 오너에게 물었다 → **D-10.5-b "다섯 곳 전부 뜨게"** 가 `docs/daily_logs/2026-08-13/work_log.md` §Decisions 에 근거와 함께 기록돼 있다. CLAUDE.md §1(모순을 드러내고 한쪽을 임의로 고르지 않는다)에 부합. **일치**.

### F2. 캐스케이드는 건전하다 (①)

`styles.css` 에서 7 선택자를 건드리는 규칙 9자리를 전수 추출(`grep -n`):
- 줄 328·345·357 — 신규 통일 base·hover·disabled (겉모습의 유일한 자리).
- 줄 446·1140·1290·1513·1810 — **`padding`만** 남은 자리별 규칙. 겉모식 속성(color/bg/border/cursor/transition)은 한 자리도 없다.
- 줄 1664 `.loop-retry` — `margin-top`만 (겉모습 아님).
- 줄 1814 `.row-actions button.ghost` — 유일한 의도적 덮개. 특이도 `(0,2,1)` > 통일 base `(0,1,1)` 로 accent 면을 **벗는** 변형이 정체성을 유지한다.

그 외: CSS 파일은 `styles.css` 단 하나. `!important` 는 줄 952(`display:none`, 무관)와 줄 2073-2080 `@media (prefers-reduced-motion)` 전역 규칙뿐 — 후자는 이 변경 **전부터** 존재(hover lift 를 즉시 전환시키는 a11y 규칙, 회귀 아님). 7 선택자의 겉모습 규칙은 전부 최상위(`@media` 중첩 없음). **일치**.

### F3. `buttonAppearance.test.ts` 4셀 — 유도되고, 양방향으로 무는다 (①)

가드는 identity 를 `background: var(--action-primary)` **∧** `cursor: pointer` 를 함께 선언한 규칙으로 **스타일시트에서 유도**한다(손 목록이 아니다). accent 면만 보면 배지(줄 921 `.tab-badge`)·날짜 점(줄 2183)이 섞이고 커서만 보면 탭·링크형 버튼이 섞여 **둘을 함께** 세는 것이 이 스타일시트에서 유일하게 정확한 기준이다(구현자 사전 스윕이 같은 결론).

뮤테이션(내가 설계·실측, 구현자 N1-N4 와는 독립):

| # | 적용한 diff | 실패한 셀 | 격리 |
|---|---|---|---|
| M1 | `.probe-sixth-copy { background:…; cursor:pointer }` 여섯째 사본 추가 | 1번(`got 2`) | ✓ (2·3·4 통과) |
| M2 | hover 규칙에서 `.row-actions button:hover…` 제거 | 2번(줄기 6≠7) | ✓ |
| M3 | disabled 규칙에서 `.row-actions button:disabled` 제거 | 3번(6≠7) | ✓ |
| M4 | (over-strict) 통일 base 에 `padding: 0.5rem 1rem` 합치기 | 4번(`toBe(false)` 위반) | ✓ |

구현자 보고 "N1-N4 단독 물림" 과 독립적으로 일치. (참고: 구현자 초안 N2 가 3셀을 물어 좁혤 재측정했다고 기록했는데 — 이것이 "여러 셀이 물면 가드가 강한 것이 아니라 뮤테이션이 넓은 것" 인 점을 구현자가 정확히 이해하고 있음을 보여준다.) **일치**.

### F4. `typeScale.test.ts` 넷째 셀 — M5 한계를 닫는다 (②)

넷째 셀은 `Object.keys(MIGRATED)` ≡ "스타일시트에서 `font-size: var(--type-*)` 로 선언한 규칙 집합" 을 대조한다. 뮤테이션:

| # | 적용한 diff | 실패한 셀 | 격리 |
|---|---|---|---|
| M5 | `MIGRATED` 에서 `".eyebrow"` 행 삭제 (= 종전 M5 한계 재현) | **4번**(42≠43) | ✓ (1·2·3 통과) |
| M6 | `styles.css` 에 `.probe-new-rule { font-size: var(--type-small) }` 추가, 목록 미등재 | **4번**(43≠44) | ✓ |

**M5 가 핵심이다** — 종전에는("뮤테이션 M5 실측 2026-08-12") 행을 지워도 아무 셀도 실패하지 않았고, 이제 넷째 셀이 잡는다. 감시를 줄이는 쪽(M5)과 감시가 안 따라가는 쪽(M6)이 같은 셀에 걸리므로 양방향 성립. 착수 전 두 집합이 이미 43≡43 이었다는 구현자 주장도 M5 결과(원래 43)로 재확인. **일치**.

### F5. 측정 — 보고 수치를 HEAD에서 전부 재측정

| 지표 | 구현자 보고 | 독립 실측(HEAD) |
|---|---|---|
| frontend | 323 passed / 27 files (496s) | 323 / 27 (423s, exit 0) ✓ |
| build modules | 704 | 704 ✓ |
| 진입 kB | 421.78 | 421.78 ✓ |
| 관측 lazy kB | 387.43 | 387.43 ✓ |
| AdminConsole kB | 8.50 | 8.50 ✓ |
| CSS (post) | 30.79 | 30.79 ✓ |
| **CSS (pre, f022088 빌드)** | 31.42 | **31.42** (cp-swap 빌드로 직접 측정) ✓ |
| CSS delta | -0.63 | -0.63 ✓ |
| `tsc --noEmit` | OK | OK ✓ |

전체 323 green 은 "프로덕션 CSS 가 회귀를 한 셀도 물지 않았다"(기존 318셀 무변)를 실증. 유일하게 움직인 부하 지표가 CSS -0.63 = 사본 5벌 제거값이고 JS 가 한 줄도 안 건드렸다는 주장과 정합. **전부 일치**.

### F6. 패턴 스윕 — 놓친 사본 없다

`background: var(--action-primary)` 선언 3곳 중 2곳(줄 921 배지·2183 점)은 `cursor:pointer` 가 없어 identity 에서 **의도대로** 제외됨. `cursor: not-allowed` 는 줄 364(버튼 disabled 통일) 외 3곳(580·1206·1353)이나 이들은 input/link 계열의 **다른 표면**이라 이 슬라이스 범위 밖. `opacity: 0.42`·`translateY(-1px)` 는 통일 자리에만 존재(흩어짐 0).

### F7. 구현자 오염 보고는 정직하다

구현자는 `cd frontend` 실패 → `&&` 체인 끊김 → 뮤테이션 적층(출력은 "1 failed | 3 passed" 로 깨끗해 보임)을 `pwd`+`git status` 로 잡아 재측정했다고 기록(work_log §Issues 1). **검증자가 같은 함정을 재현할 뻔했다** — `git checkout` 명령의 cwd 가 `frontend/` 에 남아 `pathspec did not match` 로 큰소리로 실패한 것. 차이: 이번엔 `git checkout` 이 에러를 냈고(구현자 사례는 `&&` 가 조용히 넘어감), 곧바로 정리했다. 구현자의 교훈("뮤테이션 사이에도 `git status --short`")은 실제 함정에서 나온 것이 맞다.

## Issues / Risks

### Blocking
- 없음. 계약 위반·추적 안 된 경계·과잉 교정 누락 전부 0건. (이 슬라이스는 frontend CSS·테스트 작업으로 API/schema 계약에 닿지 않는다.)

### Hardening (비차단)
- **H1 — `cursor: not-allowed` 가 다른 표면 3곳에 흩어져 있다** (줄 580·1206·1353, 비버튼 disabled). 이 슬라이스가 다룬 "버튼 겉모습 흩어짐" 과 **같은 계열**(disabled 스타일이 조용히 갈라질 수 있음)이나 대상이 input/link 계열로 다르다. 범위 밖이므로 이 슬라이스에서 손대지 않았고, 정당하다. 해당 표면들이 늘어나면 별도 부채 후보.

## Verdict

**합격** — 부채 ①② 가 처방대로(단 ①은 전제 정정 + 오너 D-10.5-b 로 모션까지 통일) 닫혔고, 두 가드 모두 스타일시트에서 유도해 양방향으로 물며, 캐스케이드·측정·패턴 스윕 전부 구현자 보고와 독립적으로 일치한다. Blocking 0.

하중을 받는 근거: ① 캐스케이드는 grep 수준이 아니라 9규칙 전수 추출 + ghost 특이도 계산으로 확인(F2). ② 넷째 셀의 M5 한계 폐쇄는 행 삭제 뮤테이션이 **이제는** 실패하는 것으로 직접 증명(F4-M5). ③ CSS-pre 31.42 는 cp-swap 빌드로 디스크에서 재측정(F5, 믿지 않고 잼).

## Outstanding items

- **어제 5커밋(`e5c0fac`·`b7c6453`·`444ab1b`·`f724fce`·`2c6eb9e`)은 이 검증의 범위 밝이 아니라 여전히 미검증** — 구현자 Next steps 1 이 "검증을 한 번에" 로 이것들을 포함한다. 본 기록은 오늘 2커밋(①②)만 다룬다.
- **backend 전수 회귀 기준선 `2271/1/2430`** (2026-08-11 값) 이 이틀째 미측정 — 오늘도 backend 프로덕션 코드 0줄이라 유효하나, D-10.5-a 순서대로 검증 뒤 한 번 돌려야 갱신된다.
- **부채 ③(T1)** 은 오너 D-10.5-c 로 Phase 10 끝 육안까지 유예(트리거 있음). 이 검증이 닫지 않은 것은 의도다.

## Reproduction

```bash
git status --short                          # 공백이어야 한다 (clean HEAD = 08aed1b)
cd frontend && npx vitest run src/buttonAppearance.test.ts src/typeScale.test.ts   # 8 passed
npx vitest run                              # 323 passed / 27 files
npx tsc --noEmit && npm run build           # 704 · CSS 30.79 · 421.78 · 387.43 · 8.50

# 뮤테이션(각 단독, 복원마다 md5 대조): styles.css 에 사본 추가/선택자 제거/padding 합치기 →
#   buttonAppearance M1-M4 가 cell 1-4 을 각각 한 씩씩 물음.
# typeScale M5(MIGRATED 행 삭제)·M6(미등재 규칙 추가) → cell 4 만.

# CSS-pre (cp-swap, 인덱스 무건드림):
cp frontend/src/styles.css /tmp/h.css
git show f022088:frontend/src/styles.css > frontend/src/styles.css
cd frontend && npm run build               # CSS 31.42 kB
cd .. && cp /tmp/h.css frontend/src/styles.css && md5sum frontend/src/styles.css   # a7e28ea…
```
