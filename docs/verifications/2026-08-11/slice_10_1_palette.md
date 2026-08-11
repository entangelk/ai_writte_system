# Slice 10.1 잉크블루 팔레트 교체 독립 검증

## Subject metadata

- 날짜: 2026-08-11
- 요청자: 오너 — *"다음작업 검증해줘. Slice 10.1 구현은 끝났습니다…"* (13표면 육안 확인은 오너 예정)
- 검증자: 이 세션 (구현자와 다른 세션; 10.0 검증에 이어 동일 날)
- 대상: Phase 10 Slice 10.1 — 잉크블루 토큰 체계(D2=ⓑ · D6=ⓑ). 커밋 `dcd2ad5`·`3465192`·`4dd2046`. (동일 세션이 10.0 H1/H3 폐쇄 `c343cbd` 도 함께 함.)
- 정규 스펙: [`docs/plans/10-frontend-design-system-decisions.md`](../../plans/10-frontend-design-system-decisions.md) §D2·§D6 (Resolved, 오너 2026-08-11).
- 주의: 백엔드 전수 회귀는 **작업자 세션에서 실행 중**이었다 — 충돌 회피해 본 검증은 백엔드 **새 가드만 단독** 실측(전수 스위트 수치는 작업자 보고 대기).

## Scope

1. 계약(D2 팔레트·대비) 대 구현 — `frontend/src/styles.css` `:root` + 생성 스크립트 `docs/plans/10_palette_contrast.py`.
2. **WCAG 대비 수치의 독립 재계산** — 작업자 스크립트를 믿지 않고 위험 짝(slate-400 테두리·slate-450 placeholder)을 별도 구현으로 잼.
3. 이관 완전성 — 옛 팔레트(hex·토큰) 잔존 스윕.
4. 새 가드 셋 — `designTokens.test.ts`(3) · `test_design_token_provenance.py`(3) · `productName.test.ts`(2, 10.0 폐쇄). 뮤테이션으로 물림 확인.
5. 반증된 브리프 가정 셋 + 작업자 결함(body 어두워짐) + 8.4 숨은 결함(.writing-confirm).
6. 스코프 축소(타이포 유예)의 건전성.
7. 기록 충실성 — 브리프·styles.css 주석·work_log 의 **짝 수 주장 일치** (★발견).

## Methodology

- 트리 clean(HEAD `4dd2046`, 전 커밋). 뮤테이션은 `cp` 백업 → 변형 → 실측 → 원복 → `diff` byte 대조 + `git status --short` empty.
- WCAG: 별도 python 구현(WCAG 상대 휘도 공식)으로 11개 위험 짝 계산 → 작업자 스크립트 출력과 교차 대조.
- frontend 전체·build·provenance 가드: 실구동.
- 옛 팔레트: 정밀 grep(`var(--(ink|muted|line|accent|accent-dark|danger)[),]`), `#f4f0e7`·`#a4452f`.

## Findings

### 1. 기준선 수치 — 전부 독립 재현

- frontend `npx vitest run`: **22 files / 294 passed**, exit 0. `designTokens.test.ts`(3)·`productName.test.ts`(2) 포함 clean. 작업자 294/22 일치.
- build: **702 modules · 진입 420.81 kB(무변) · CSS 30.47 kB**(26.62 → +3.85) · lazy(Admin 8.50·관측 386.70) 무변 · `tsc` clean. 색은 CSS에만 있어 JS 번들은 안 움직였다 — 작업자 주장 일치.
- provenance 가드 단독: **3 passed / 62 subtests**. 작업자 주장 일치.

### 2. WCAG 대비 — 독립 재계산으로 전 짝 통과 확인 (★계약의 심장)

별도 구현으로 위험 짝 계산 → 작업자 스크립트와 소수 셋째짜리까지 일치:
- **slate-400 #7f8994 / blue-50 = 3.32**(테두리 3:1 ✓). 브리프 원값 #88929d 는 2.95 로 페이지에서 미달이었고 작업자가 어둡게 보정 — 맞음.
- **slate-450 #636c77 / blue-50 = 4.98**(placeholder 4.5:1 ✓, **여유 있음**). "이분 탐색 4.50 → hex 양자화 4.49" 우려를 여유로 해소.
- 본문 blue-900/blue-50 = 14.01(AAA)·링크·버튼라벨·오류문구 전부 여유 통과.
- 생성기 `PAIRS` 30짝 전수 [OK], 실패 0. provenance cell 2 가 테스트 시점에 같은 30짝을 재검산한다.

### 3. 이관 완전성 — 옛 팔레트 제거 확인

- 옛 토큰(`var(--ink)`·`--accent`·`--line`·`--muted`·`--danger` 등 exact): **0건**(정밀 grep). 178곳 이관 주장과 모순 없음.
- `#a4452f`(옛 벽돌): **0건**.
- `#f4f0e7`(옛 크림): `ObservabilityDashboard.tsx` 4곳(line 53 주석·231/239/247 차트 stroke) — **예상된 중간 상태**(차트 색=JS 리터럴, `var(--)` 안 닿음; 브리프 follow-up에 10.3~ 별도 수립 명시).

### 4. 새 가드 — 둘 다 뮤테이션으로 물림 확인

- **`designTokens.test.ts`** 3셀: (1) 쓴 토큰이 전부 정의됨(fallback `var(--x,y)` 포함) (2) 규칙부에 리터럴색 0 (3) 화면이 raw primitive 를 안 쓴다.
  - **뮤테이션**: 규칙부에 미정의 `var(--text-bod)` 삽입 → cell 1 실패(line 52, `1 failed | 2 passed`). under-strict 확인. (작업자 M11 교훈 — :root 가 아닌 **규칙부**를 노려야 물린다 — 재현.)
- **`test_design_token_provenance.py`** 3셀: (1) CSS primitive == 생성기 `P` (2) 생성기 `PAIRS` 30짝 WCAG 재검산 (3) 본문 AAA.
  - **뮤테이션**: CSS `--slate-400` hex #7f8994→#7f8995 단독 수정 → cell 1 실패(subTest slate-400, `CSS=#7f8995 생성기=#7f8994`, `1 failed | 3 passed | 61 subtests`). cell 2·3 은 생성기 `P` 를 쓰므로 통과해 깔끔히 분리. CSS↔script 출처 연결선이 under-strict 로 문다.
- `productName.test.ts`(10.0 H1 폐쇄): `index.html` 파일을 읽어 `<title>에-라잇</title>` 단정 + 소스 전수 스웹(렌더 밖 `og:title` 등도 덮음). jsdom 이 `index.html` 을 안 읽어 `document.title` 가 무의미라는 점(10.0 검증 H1)을 정확히 짚음. 2셀 clean.

### 5. 반증된 브리프 가정 셋 + 결함 — 구현에서 드러나고 처리됨

- `--surface-raised` 신설(page < raised < card, sunken 만 page 보다 어둡다) — 브리프의 surface=page·card·sunken 가정이 실제 CSS 사용(융기면 다수)과 안 맞았음을 구현 중 발견. WCAG 30짝에 융기면(slate-50) 짝이 추가됐고 통과.
- **8.4 숨은 결함 `.writing-confirm`**: `var(--border)`·`var(--surface-muted, transparent)`(둘 다 미정의)로 2026-08-04 부터 테두리·배경 없이 렌더. `designTokens.test.ts` 가 첫 실행에 잡았고, 이제 `--border-hairline`·`--surface-raised`로 fix(새 토큰과 일관). **초판 정규식이 fallback 형태를 놓칠 뻔했고 결함이 정확히 그 형태** — 강화(fallback 도 셈)로 폐쇄. 검증자가 `.writing-confirm` 현재 CSS 확인 — 정의된 토큰만 사용.
- **작업자 자결함(body 한 단계 어두워짐)**: `#f4f0e7` 가 페이지 배경·침강 블록 두 역할을 격해 일괄 매핑에서 body 가 sunken 로 갔다. 배포 CSS 확인 중 발견 → `--surface-page` 로 정정. 현재 `body { background: …, var(--surface-page); }`(blue-50) 확인. **가드가 못 잡는 종류**(둘 다 정의된 토큰이라 참조 멀쩡, 의미만 틀림) — work_log Issue 6 에 기록.

### 6. 타이포 스코프 축소 — 사유 타당, 기록됨

현행 `font-size` **29종**(0.7~1.8rem, 0.72/0.74/0.75/0.76 근접 중복) 확인. 스케일 스냅 안 함(무변). `:root` 주석(line 104-109)에 *"타이포 스케일은 10.1 범위 밖 — 눈으로 판단할 시각 재설계, 팔레트와 겹치면 diff 검토 불가, 10.3~ 첫 항목"* 으로 사유 명시. 브리프는 "10.1 = 팔레트 + 간격·타이포·반경"이라 **의도적 축소**.

## Issues / Risks

### Blocking (계약 의무 위반)

- **없음.** 팔레트 구현은 계약(D2)을 충족하고 WCAG 30짝이 독립 재계산으로 전부 통과하며, 가드가 뮤테이션으로 입증됐다.

### ★ 조건 → **폐쇄(같은 커밋 `f717b87`, 작업자; 검증자 실측 확인)**

- **C1 (문서 충실성) — 닫힘.** 발행 시점(HEAD `4dd2046`)에 브리프 §D2 표가 구현과 갈라져 있었다(`--slate-400 #88929d`·18짝·`--surface-raised`/`--slate-450` 누락). `f717b87` 이 정정: 원시테이블 `--slate-400` 취소선→**#7f8994** · `--slate-450` 신설 · 대비표를 "착수 시점 스냅샷"으로 명시 + 정본을 `10_palette_contrast.py`·`test_design_token_provenance.py` 로 지정(정정 주석이 "독립 검증 C1·H1" 인용). 검증자 실측 — 완전. **잔여 니트(비차단)**: semantic 표(§D2 line 204-220)에 `--surface-raised`·`--text-placeholder` 행이 여전히 빠지나 `:root`·work_log Task 6 에 문서화돼 있고 대비표 주석이 정본을 script 으로 지정하므로 "정본이 거짓 숫자를 말한다"는 정정 목적은 달성.

  **★ 잔여 니트도 폐쇄 2026-08-11 (작업 AI, 검증자 아님).** 표를 `:root` 에서 **재생성**했다 — 검증자가 짚은 둘 외에 **총 9행이 빠져 있었고**(`--action-danger-hover`·`--border-danger`·`--state-*` 6종 포함) `--border-hairline` 매핑도 틀렸다(`slate-300` → 실제 `slate-200`). §4 패턴 스윕으로 전수 대조해 한 번에 닫았다. **그리고 이 드리프트 자체를 가드로 묶었다**(`test_design_token_provenance.py` +1셀) — primitive hex·짝 수 prose 에 이은 **같은 병의 세 번째**라, 부주의가 아니라 *사람이 두 곳을 동시에 기억해야 하는 구조*가 원인이라고 봤다. 뮤테이션 3종 작동: M18 `:root` 에 토큰 추가·표 미갱신 → 1 failed · M19 표 매핑만 변경 → 1 failed · M20 표에서 행 삭제 → 1 failed. provenance 가드 **4 → 5 cells / 65 → 89 subtests**.

### Hardening / 비차단

- **H1 (문서 정확성) — 닫힘.** 짝 수 prose 3곳(브리프 "18"·styles.css :root 주석 "28"·work_log "18")이 모두 **30**으로 통일됐다(`259c7a4`). **검증자 권고를 받아 prose 를 `len(PAIRS)` 에 묶는 셀을 provenance 가드에 추가**했다(`test_prose_that_states_the_pair_count_matches_the_generator`, M16·M17 로 입증) — 가드 **3→4 cells·62→65 subtests**. "세는 사람 셋" 병의 재발을 구조적으로 막는다.
- **H2 (스코프, 오너 결정 대기): 타이포를 10.3~ 로 유예** — 브리프 10.1 범위("…타이포…")에서 축소. 사유 타당하고 `:root` 에 기록됐으나 **오너가 축소를 bless 했는지** 는 본 검증 시점에 미확정(작업자 보고만). 오너 수용 필요.
- **H3 (진행 중·작업자 공지): work_log 회귀 기준선·HANDOFF·CHANGELOG 미갱신** — 작업자가 *"회귀 끝나면 기준선 채우고 마무리"* 라 공지(work_log 하단이 10.0 값으로 stale). 백엔드 전수 수치는 작업자 세션 실행 대기라 본 검증도 미실측(새 provenance 가드 3/62 만 단독 확인).

## Verdict

**합격** — 발행 시점엔 **조건부 합격**(조건 C1·H1 = 브리프 §D2 표·prose 짝 수 정정)이었으나, **후속 커밋 `259c7a4`(작업자)에서 폐쇄**됐다 → 합격 승격. (참고: `f717b87` 은 슬라이스 표만 고쳤고 D2 본표 정정·prose 통일·prose-가드는 `259c7a4`.) 작업자가 브리프 원시테이블을 정정(`--slate-400` ~~#88929d~~→**#7f8994**·`--slate-450` 신설)하고 대비표를 **착수 시점 스냅샷**으로 명시하며 정본을 [`10_palette_contrast.py`](../../plans/10_palette_contrast.py)·[`test_design_token_provenance.py`](../../tests/test_design_token_provenance.py) 로 지정했다. **정정 주석이 "독립 검증 C1·H1" 을 직접 인용**한다(10.0 `role="menu"` 인라인 정정 패턴). styles.css 주석(28→30)·work_log(18→30) 도 통일. 검증자가 정정 내용을 실측해 완전함을 확인했다.

이유: 팔레트 구현은 WCAG 30짝 독립 재계산으로 전부 통과하고 옛 팔레트는 제거됐으며 새 가드 셋(designTokens·provenance·productName)이 뮤테이션으로 입증됐다. 8.4 숨은 결함·작업자 자결함도 fix. **검증이 잡은 문서 충실성 결함(C1·H1)이 동일 커밋에서 닫혔다** — 검증 절차가 정상 작동한 사례. 잔여 니트(semantic 표에 `--surface-raised`/`--text-placeholder` 행 누락, 비차단)만 남는다.

## Outstanding items

- **작업 AI** 가 C1(브리프 §D2 표 정정 — 취소선/정정블록, 10.0 `role="menu"` 선례) + H1(prose 짝 수 30 통일, 권고: provenance 가드에 prose-셀 추가) 처리.
- **오너 결정**: H2 타이포 유예(10.3~ 이관) bless 여부.
- **작업 AI 마무리**: H3 — 백엔드 전수 회귀 후 기준선·HANDOFF·CHANGELOG 채우기.
- **오너**: 13표면 육안 확인(회귀가 0셀도 안 무는 슬라이스라 눈이 유일 검증). 관측 화면 차트는 옛 색 잔존(예상된 중간 상태).
- 본 검증은 **검증으로 끝**.

## Reproduction

```bash
# 기준선
cd frontend && npx vitest run                       # 22 files / 294 passed
cd frontend && npm run build                        # 702 modules, 진입 420.81, CSS 30.47
python3 -m pytest tests/test_design_token_provenance.py -q   # 3 passed / 62 subtests

# WCAG 독립 재계산 (별도 구현; slate-400/slate-450 위주)
python3 -c "def L(h):..."   # 상대휘도→대비; slate-400/blue-50=3.32, slate-450/blue-50=4.98
python3 docs/plans/10_palette_contrast.py           # 30짝 [OK] 실패 0

# 옛 팔레치 잔존
grep -rnE "var\(--(ink|muted|line|accent|accent-dark|danger)[),]" frontend/src   # 0
grep -rni "a4452f" frontend/src                                                    # 0

# 가드 뮤테이션 (cp 백업 → 변형 → 실측 → 원복 → diff)
# provenance: CSS --slate-400 hex 한 단위 수정 → cell 1 SUBFAILED(slate-400)
# designTokens: 규칙부에 var(--text-bod) 삽입 → cell 1 (1 failed | 2 passed)
```
