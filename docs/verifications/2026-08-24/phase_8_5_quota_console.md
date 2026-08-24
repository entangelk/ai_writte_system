# 8.5 프론트 — 관리자 콘솔 "회원 사용량 한도" 화면 + "서비스로 이동" 링크 — 독립 검증

## Subject metadata

- 날짜: 2026-08-24 (검증 세션 — 구현 세션 1과 다른 AI 세션)
- 요청자: 오너 — *"작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?"*
- 대상: 이날 커밋 4개 전부(HANDOFF가 "미검증 구간"으로 지목한 범위 그대로)
  - `09946e2` schema.d.ts 재생성 · `36d5778` 구현+테스트 · `713b68d` App.test 보강 ·
    `2cea291` 문서 마감. HEAD `2cea291` 클린 트리에서 검증.
- 정규 스펙: SoT **v1.8.4** 행(노출 결정 — 모델 v1.7.95) +
  [`plans/08-5-usage-admin-cms-decisions.md`](../../plans/08-5-usage-admin-cms-decisions.md)
  §5의 예약 문구("관리자 콘솔 UI는 백엔드 확정 뒤 별도 슬라이스 — 5-d 콘솔에 붙인다") +
  화면이 지켜야 할 백엔드 계약의 정본(`routers/admin.py`·`api/models.py` — 8.5-a/b·검증 폐초 슬라이스).
- 소스: 위 커밋 + `daily_logs/2026-08-24/work_log.md`.

## Scope

- **계약(SoT v1.8.4 행이 화면에 부과한 의무)**: ① 한도 변경은 두 창을 항상 같이 전송
  (서버가 `QuotaLimits` 전체를 대체) ② 변경 실패 뒤 상세 재독기(H2) ③ 소수는 클라이언트
  통과(서버 StrictInt 422 위임), 빈 칸·해석불가·둘 다 무제한은 제출 비활성
  (`Number("")===0`·`JSON.stringify(NaN)→null` 사고 방어) ④ 자기 정지 선차단 없음(서버 400
  메시지 표시). 노출: 사용자 섹션 뒤 배치·제품 어휘("정지됨"/"무제한"/"남은 사용 N회")·창 사용량
  표기·`변경 예약됨` 배지·축소 예약 힌트·"저장된 정책 없음" 힌트·P6 힌트·머리글 링크(`/`).
- 구현: `MemberQuotaSection.tsx`(304줄)·`AdminConsole.tsx` 배선 7줄·`client.ts` 함수 5종+
  타입 2종·`styles.css` 4곳·`schema.d.ts`(+548줄).
- 회귀셀: `MemberQuotaSection.test.tsx` 7셀(전수 정독 — 감사 대상으로 취급)·
  `AdminConsole.test.tsx` 7셀 보강·`App.test.tsx` 관리자 라우트 셀 보강.
- 수치 재현: frontend 전수 338/29·build 705 modules·진입 425.90·AdminConsole lazy 14.76·
  관측 387.43·CSS 31.36·문서 가드 13/265.
- 백엔드 계약 전제 4종의 실재(읽기 대조 — 이 슬라이스는 backend 프로덕션 0줄).

## Methodology

재현 환경: WSL2 알파 머신, frontend `node_modules` 설치됨. **vitest는 반드시 `frontend/`에서**
(루트에서 돌리면 jsdom이 안 붙어 전 셀이 1ms 실패로 보인다 — 작업자 기록과 동일하게 재현됨,
아래 Findings 8). 뮤테이션 절차: `git status --short` 빈 확인(게이트) → Edit 변이 →
`frontend/`에서 포커스 셀 실행 → 요약 count 줄로 판독 → `git checkout -- <루트 기준 경로>` →
클린 재확인. 복구 pathspec은 **루트 기준**이다(cwd가 `frontend/`면 지정이 실패한다 — 이번 검증
중 2회 실수하여 즉시 바로잡음).

```bash
git status --short && git log origin/main..main --oneline   # 클린 + 미푸시 4커밋 확인
# 백엔드 계약 전제(읽기): routers/admin.py 210-290 · api/models.py 149-203 ·
#   AuthGate.tsx 112-128(링크 주장) · schema 재생성 멱등:
cd frontend && npm run gen:api && cd .. && git status --short # → 빈(바이트 동일)
cd frontend && npx vitest run                                # 전수 (338/29)
cd frontend && npm run build                                 # 705 modules·청크 지표
python3 -m pytest tests/test_docs_indexes.py -q              # 13 passed/265 subtests
# 뮤테이션 5종(아래 표) — 각: Edit → vitest run src/admin/MemberQuotaSection.test.tsx
#   → git checkout -- → 클린 확인
```

## Findings

### 1. git 상태 — 주장 그대로

클린 트리·커밋 4개(`09946e2`→`2cea291`)·`origin/main` 대비 4커밋 미푸시(작업자 "push 안 함"
주장과 일치). 4커밋의 파일 구성은 work_log 서술(스키마→구현→App.test 보강→문서)과 정확히
일치한다.

### 2. 백엔드 계약 전제 4종 — 전부 실재 (가드의 근거가 참)

프론트 가드 4종은 "백엔드가 그렇게 동작한다"는 전제 위에 서 있으므로, 전제 자체를 정본에서
역방향으로 확인했다. **하나도 거짓이 없었다.**

| 전제 | 정본 좌표 | 확인 내용 |
|---|---|---|
| ① 한도 쌍 전체 대체 | `routers/admin.py:241-248` | `set_limits(target=QuotaLimits(daily_limit=body.daily_limit, weekly_limit=body.weekly_limit, …))` — body 값을 그대로 저장. `models.py:187-196` docstring도 "둘 중 하나만 바꿀 수 있고 None 은 그 창의 무제한" — 한 창만 실으면 나머지가 무제한이 되는 함정은 실재하며, 프론트가 항상 두 창을 실어야 하는 이유가 성립 |
| ② 감사는 적용 뒤·fail-closed | `routers/admin.py:241-254` | `set_limits`(241) 다음 `_audit_quota_change`(249) — 감사 쓰기 실패 시 변경은 이미 적용된 채 요청만 죽는다(H2). 프론트의 실패 후 재독기가 필요한 이유가 성립 |
| ③ StrictInt 422 | `api/models.py:186-196` | `daily_limit: StrictInt \| None`·`weekly_limit: StrictInt \| None` — 소수·문자열·불 422, 음수·둘 다 미지정·공백 사유는 라우터 400(`admin.py:221-232`)과 갈림. "소수를 서버에 맡긴다"의 근거 성립 |
| ④ 자기 정지 400 | `routers/admin.py:286-289` | `user_id == current.id` → 400 "administrators cannot suspend their own quota". `describeApiError`(`client.ts:961`)가 `400: <detail>` 문자열을 그대로 낸다 — UI 선차단 없이 메시지를 보여주는 설계의 근거 성립 |

또한 행 교체 로직의 전제 — **상세 응답이 목록 필드 전부를 포함** — 도 확인:
`AdminQuotaPolicyDetailResponse(AdminQuotaPolicyPayload)` 상속(`models.py:171`)+`_quota_detail`이
`**base.model_dump()`로 payload를 확장(`admin.py:171-181`). `applyDetail`이 행을 detail로
통째로 교체해도 `username` 등이 소실되지 않는다.

### 3. 코드 대 계약 — SoT v1.8.4 행의 분기 전부 실재·전부 셀에 매핑

- **① 두 창 동시 전송**: `MemberQuotaSection.tsx:132-136`이 항상
  `{daily_limit, weekly_limit, reason}`를 담는다(한 창만 담는 조건 분기 없음).
- **② 실패 후 재독기**: `changeLimits`·`setSuspended` 양쪽 catch에서
  `refreshAfterFailure`(`:96-102`, `applyDetail(…, keepError=true)` — 오류 메시지는 유지).
- **③ 입력 방어**: `parseLimitText`(`:45-49`) — 빈 칸·비유한수만 `undefined`, 소수 통과.
  `limitsInvalid`(`:176-179`)가 빈 칸/해석불가/둘 다 무제한을 잡고 한도 변경 버튼만 비활성
  (정지 버튼은 한도와 무관 — 계약대로).
- **④ 자기 정지**: 선차단 코드 없음. 서버 400 메시지가 패널 `alert`로 표시.
- **노출**: 섹션은 사용자 섹션 뒤·가입 요청 앞(`AdminConsole.tsx:277`, grep 실측 순서
  KPI→사용자→**quota**→가입→프로젝트→감사). 어휘는 `quotaStatusLine`(`:30-34`)이
  정지됨→무제한→남은 사용 순. `변경 예약됨` 배지(`:186`)·축소 예약 힌트(발효 시각 포함,
  `:194-203`)·"저장된 정책 없음 — 기본 한도로 운영 중입니다."(`:204-209`)·P6 힌트
  ("한도를 늘리면 즉시, 줄이면 다음 창 경계에 반영됩니다.", `:257-259`) 전부 실재.
- **링크**: `AdminConsole.tsx:238` `<Link className="section-link" to="/">서비스로 이동</Link>`
  — `</header>` 뒤(머리글 밖) 정위치. **"1회성 리다이렉트라 되돌아오지 않는다"는 주장을
  실증**: 리다이렉트는 `AuthGate.tsx:112-128`의 `onAuthenticated` 콜백 안(로그인 시 1회)이며,
  `/admin`으로의 네비게이션은 전수 grep에서 이 한 곳뿐(`App.tsx:31` 라우트 정의 제외) — 링크로
  `/`에 가면 관리자라도 프로젝트 목록에 머문다.
- **CSS 주장**: styles.css 15줄 변경은 전부 quota 패널용(셀렉터 목록 3곳 확장+
  `.admin-quota-detail` 1규칙). **링크에 쓴 새 CSS는 0줄** — 주장 정확.

### 4. schema.d.ts 재생성 — 멱등(바이트 동일)

`npm run gen:api`는 살아있는 앱에서 덤프한다(`scripts/dump_openapi.py` → `create_app()`).
HEAD에서 재실행 → **`git status` 빈**. 손편집 없음. diff의 548줄도 정밀 검사: 새 경로 키
5종·`AdminQuota*` 스키마 6종과 그 타입 스캐폴딩만 있고 **이물 0건**(work_log의 "다른 것이
섞이면 조사" 게이트 통과를 독립 확인).

### 5. 수치 재현 — 전부 일치

| 지표 | 작업자 주장 | 재실측 |
|---|---|---|
| frontend 전수 | 338 passed / 29 files | **338 / 29**, exit 0, 526초(410초보다 느린 것은 병행 부하 차이) |
| build modules | 705 | **705** |
| 진입 청크 | 425.90 kB(+4.12) | **425.90 kB** |
| AdminConsole lazy | 8.50 → 14.76 kB | **14.76 kB**(8.50은 HANDOFF 이력 기준선) |
| 관측 lazy | 387.43 무변 | **387.43 kB** |
| CSS | 31.36 kB | **31.36 kB** |
| 문서 가드 | 13 passed/265 subtests | **13 passed / 265 subtests** |

### 6. 회귀셀 감사(테스트는 검증자가 아니라 감사 대상) — 7셀 전수 정독

본문 단정은 전부 공개 표면(DOM 어휘·fetch URL·요청 본문)을 겨냥한다. 결정적으로
한도 변경 셀은 `toEqual({daily_limit: 30, weekly_limit: 100, reason})` — **본문 전체를
정확히** 단정하므로 ①의 의미론(변경 없는 창도 실린다)이 키 누락·추가 어느 쪽에도 실패한다.
제출 비활성 셀은 사유 공백(정지·변경 둘 다)·빈 칸·"abc"·둘 다 무제한 축과 "정지는 한도와
무관하게 살아있음"을 같이 잠근다. 422 셀은 "7.5"를 실제로 입력해 제출까지 가는지(=클라이언트가
소수를 안 막는지)를 행위로 확인한다. 자기 정지 셀은 서버 문구를 그대로+재독기 URL까지 단정.

### 7. 기존 셀 보강 — 8곳 주장 확인

`AdminConsole.test.tsx`에 "6번째 마운트 fetch" 스텁 7곳 삽입+인덱스 시프트(5→6, 6→7)·
URL 배열 갱신, `App.test.tsx` 관리자 라우트 셀 1곳(스텁 2개 추가 — 종전 signup-requests가
녹화 밖 fetch였던 것도 이번에 해소, work_log Issue 기록과 부합). 6번째가 되는 구조적 근거도
확인: 섹션은 AdminConsole 자체 로딩 완료 뒤에 마운트하므로 자식 effect가 뒤늦게 돈다.

### 8. 뮤테이션 5종 — 전부 정확히 예상 셀 1개씩 재실패

작업자의 2종과 겹치지 않는 4종 + 작업자 M1 재검증. 각 행은 **적용한 diff 그 자체**이다.

| 변이 | 적용 diff | 재실패한 셀 | 결과 |
|---|---|---|---|
| V-M3(과잉 방향) | `parseLimitText` 복귀식 `Number.isFinite(value) ? value : undefined` → `Number.isFinite(value) && Number.isInteger(value) ? …`(소수 클라이언트 차단 = 계약 ③ 위반) | "shows a server 422 …" | **정확히 1셀** |
| V-M2 | `setSuspended` catch에서 `await refreshAfterFailure(userId);` 1줄 삭제(정지 경로 — 작업자 M2는 변경 경로) | "shows the server's self-suspend rejection …" | **정확히 1셀** |
| V-M1 | `client.ts` `suspendAdminQuota` 본문 `JSON.stringify({ reason })` → `JSON.stringify({})` | "suspends and re-activates a member with the audit reason" | **정확히 1셀** |
| V-M4 | `limitsInvalid`에서 `\|\| (panel.dailyUnlimited && panel.weeklyUnlimited)` 조항 삭제(둘 다 무제한={null,null}→서버 400 본문 방어 제거) | "disables submission for blank reason …" | **정확히 1셀** |
| M1 재검증(작업자 것) | `changeLimits` 호출 본문에서 `weekly_limit: weekly,` 1줄 삭제 | "sends both windows on a limit change …" | **정확히 1셀** |

매 변이 후 `git checkout --`(루트 기준 경로)으로 복구·클린 확인. 각 셀이 **제것만** 물었다는
것은 7셀이 각자 다른 조항을 잠근다는 뜻이다(한 넓은 셀이 전부 흡수하지 않는다).

**환경 함정 재현(정직 기록)**: V-M1 직후 루트에서 vitest를 돌려 전 7셀이 1ms 실패로
보였다 — jsdom 미부착(`document is not defined`). `frontend/`에서 재실행하니 정확히 1셀.
작업자가 work_log에 남긴 함정("실행 위치도 실측의 일부다")이 그대로 재현됐다. 복구 pathspec을
cwd 기준으로 쓰는 실수도 2회 했는데(루트 기준이어야 한다), 게이트 덕에 변이가 방치되는 일은
없었다.

### 9. 문서 — 정본 4종 상호 정합

SoT v1.8.4 행·CHANGELOG·HANDOFF(5-d 행+마감 메모)·브리프 상태줄 완료 처리가 서로 같은
사실을 말한다. SoT 헤더·README 버전 칸 v1.8.4 정렬도 확인. work_log의 측정 정직성(예상
330/28에 대한 +8의 정체를 기준선 오차로 해명)도 납득 — HANDOFF 08-21 기준 323/27 뒤 08-22
가입 슬라이스가 셀을 더했고 이번 기여는 +7셀·+1파일이 정확하다(338−323=15 중 7은 이번
신규, 나머지 8은 08-22분).

## Issues / Risks

### Blocking — 없음

경계 행렬(SoT v1.8.4 행이 요구하는 분기·리터럴)의 빈 칸을 못 찾았다: 조건 분기 전부
(정지됨/무제한/남은 사용·예약 배지·축소 예약 힌트·무정책 힌트·제출 비활성 4축·422 표시·
자기 정지 400 표시·재독기 2경로·링크 존재·href)가 명명된 셀에 매핑되고, 뮤테이션 5종이
각자 다른 셀을 물었다. 정본 상호 모순도 없다.

### Hardening recommendations (비차단)

- **H1 — P6 정적 힌트 문구 미고정**: SoT v1.8.4 행이 인용하는
  "한도를 늘리면 즉시, 줄이면 다음 창 경계에 반영됩니다."(`MemberQuotaSection.tsx:258`)는
  무조건 렌더라 조건 분기가 없고, 이 문구를 고정하는 셀도 없다 — 지우면 아무 테스트가 안
  물는다. 조건 힌트 둘(축소 예약·무정책)은 셀이 있으니 형평상 1줄 `getByText`로 잠그는
  것이 SoT 인용 문구의 수명을 보장한다. (어휘 "남은 사용 N회"는 제품쪽
  `WritingPanel.test.tsx:1098` 선례대로 이번에 관리자쪽도 고정했는데, 정적 힌트를 화면에
  낸 것 자체가 이번이 처음이라 선례가 없던 자리다.)
- **H2 — 링크 위치 미고정**: 링크는 존재+`href="/"`만 단정된다. "머리글 바로 아래"(
  `</header>` 뒤)는 DOM 순서 단정이 없어, header 안으로 옮겨져도(.page-heading 스타일이
  깨지는 그 배치) 테스트는 녹색이다. 작업자가 올린 주석의 이유가 사라지는 변화를 잡으려면
  순서 단정이 필요하다.

## Verdict

**합격** — 근거: ① 백엔드 계약 전제 4종(쌍 대체·감사 후적용·StrictInt 422·자기 정지 400)이
정본에서 전부 실재하며 프론트 가드의 방향이 옳다 ② SoT v1.8.4 행이 화면에 부과한 의무와
노출 전부가 코드에 실재하고 조건 분기 전부가 명명된 셀에 매핑된다 ③ schema.d.ts 재생성이
바이트 멱등(손편집 없음)이고 diff는 quota 5경로·6스키마뿐 ④ 전수 338/29·build 705/425.90/
14.76/387.43/31.36·문서 가드 13/265이 전부 재현됐다 ⑤ 뮤테이션 5종(작업자 2종과 다른
4종+M1 재검증)이 정확히 예상 셀 1개씩만 물었다 ⑥ 링크의 "되돌아오지 않는다" 주장이
코드 실증으로 성립한다. 비차단 hardening 2건(H1 힌트 문구·H2 링크 위치)은 위에 명명했다.

## Outstanding items

- **브라우저 육안 확인은 오너 몫** — 프론트 이미지 재빌드 필요
  (`docker compose build frontend && docker compose up -d frontend` → `:5520/admin`).
  이 검증은 코드·계약·셀 수준까지 갔고 화면 렌더 육안까지는 가지 않았다.
- 커밋 4개+이 검증 기록은 미푸시(오너 푸시 대기).
- backend 전수(2506)는 재실행하지 않았다 — 이 슬라이스는 backend 프로덕션 0줄이므로
  백엔드는 읽기 대조로 갈음(환경 기록: test-mongo 미기동).
- 프론트 전수 526초(작업자 410초) — 병행 작업 부하 차이, 셀 수·결과 동일.

## Reproduction

```bash
git status --short                          # 빈
cd frontend
npm run gen:api && cd .. && git status --short   # 빈(스키마 멱등)
cd frontend && npx vitest run               # 338 passed / 29 files
npm run build                               # 705 · 425.90 · 14.76 · 387.43 · 31.36
cd .. && python3 -m pytest tests/test_docs_indexes.py -q   # 13 passed/265
# 뮤테이션(각각): frontend/에서 Edit 변이 → npx vitest run src/admin/MemberQuotaSection.test.tsx
#   → 요약 줄 판독 → cd .. && git checkout -- frontend/src/... → git status --short 빈 확인
```
