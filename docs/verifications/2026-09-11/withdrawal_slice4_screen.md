# 계정 탈퇴 Slice 4(화면) 독립 검증

**합격 판정이 아니다 — 조건 둘이 닫혀야 한다.** (판정은 아래 Verdict)

- **일시**: 2026-09-11 · **검증자**: 세션 56(구현 세션 55와 다른 세션)
- **의뢰**: 오너 지시 *"핸드오프 확인해서 다음 작업 진행해줘. 독립 검증작업이야. 검증하고 의심하고 또 의심해줄래"*
- **대상**: 계정 탈퇴 Slice 4 — 전역 유예 배너 · `/me` 탈퇴 요청·취소 (커밋 `534fb74`·`b68d923`, SoT **v1.8.54**)
- **정규 스펙**: [`docs/system-contract-sot.md`](../../system-contract-sot.md) v1.8.54 행 · 브리프 [`plans/slice4-withdrawal-screen-decisions.md`](../../plans/slice4-withdrawal-screen-decisions.md)(D1=ⓐ·D2=ⓐ, 오너 2026-09-10) · 계획서 [`plans/account-withdrawal-implementation-phases.md`](../../plans/account-withdrawal-implementation-phases.md) §Slice 4
- **검증 트리**: HEAD `0cf184a`(Slice 4 구현·기록 전부 실린 뒤, 트리 clean)

## Scope

프런트 전용 슬라이스다. 본 축: ① 계약 문언(SoT·브리프·계획서·백엔드 라우터의 409 의미 셋) ② 구현(`withdrawal.tsx`·`AuthGate.tsx`·`client.ts`·`vitest.setup.ts`·`styles.css`·`PersonalHubPage.tsx`) ③ 신규 셀 [`frontend/src/me/withdrawal.test.tsx`](../../../frontend/src/me/withdrawal.test.tsx) 11셀 ④ 세션 55 변이 기록의 재현성 ⑤ 전수 재실행. ★ 가장 의심스러운 축: **"셀이 잠근다"는 SoT 문언이 실제 장착 지점에서 참인가** — 배너의 프로덕션 마운트는 `AuthGate.tsx:161` 한 곳인데, 셀들은 `AuthGate` 없이 배너를 직접 마운트하는 **복제 셸**을 쓴다.

## Methodology

- 계약 스코프 정독(SoT v1.8.54 · 브리프 ⓐ표/후속 고려 · 계획서 §Slice 4 · [`auth.py:260-316`](../../../services/application/app/routers/auth.py)·[`users.py:112-121`](../../../services/application/app/auth/users.py)) → 경계 행렬 14칸 구축 → 코드·셀 대조.
- 초점: `cd frontend && npx vitest run src/me/withdrawal.test.tsx`(필요 시 `PersonalHubPage.test.tsx`·`App.test.tsx` 병합).
- 변이: 매번 `git status --short` 무출력 게이트 → 편집 → 초점 실행(파일 캡처) → `git -C <절대경로> checkout -- <절대경로>` 원복 → 무출력 확인. 세션 55 변이 6종 재적용 + 신규 5종.
- 전수: 프런트 `npx vitest run --reporter=basic > 파일 2>&1`(frontend/ 안에서, 파일 캡처). 백엔드는 소스 무변(`git diff --name-only b68d923^..b68d923 -- services scripts tests` 빈)이라 세션 55 선례의 **통제 대조**(문서 가드 양단)로 귀속.
- 환경: 알파(WSL2, 부팅 직후 창 포함) · 시계 스텝 journal 실측 · `python3 -m pytest`.

## Findings

### 1. 계약 문언 ↔ 구현 — 일치 (단, SoT의 잠금 주장 둘은 실측으로 반증됨)

- **409 두 뜻 분할의 전제가 성립한다**: 백엔드에서 POST 409 는 `LastActiveAdmin`([auth.py:294](../../../services/application/app/routers/auth.py)), DELETE 409 는 `WithdrawalNotRequested`([auth.py:314](../../../services/application/app/routers/auth.py)) **각각 하나뿐** — "동작별로 가른다"는 분할이 빈틈없다. 화면 판정은 전부 `cause.status` 로만(H3 준수, `detail` 분기 없음).
- **남은 일수 산술**: `remainingGraceDays` = 빼기 + `Math.ceil` + `Math.max(0,…)`([withdrawal.tsx:113](../../../frontend/src/me/withdrawal.tsx)) — 30 무박(정본은 서버 `purge_due_at`, [`users.py:112`](../../../services/application/app/auth/users.py)가 유일 산술 지점).
- **상태 한 벌**: `WithdrawalProvider` 셸 배치 + `/me` 요청·취소가 같은 `apply` 로 갱신 — 구조 일치.
- **구조 주장 셋 전부 실측 일치**: `AuthUserContext` 프로덕션 소비자는 `useAuthenticatedUser` 뿐(grep: 정의=`AuthGate.tsx` 내부, 직접 소비=테스트 둘) · `schema.d.ts` 슬라이스 무변 + `npm run gen:api` 재실행 **무차분** · 백엔드 무변(=operation 105 무변).
- **배너 마운트는 `AuthGate.tsx:161` 유일**(grep 전수) — authenticated 분기 안, `header-alert` 아래. 비로그인·세션 확인 중엔 provider 자체가 안 선다.

### 2. 세션 55 변이 기록 재현 — 6종 중 5종 일치, **MV-2 는 프로덕션 지점에서 재현 불가**

| 변이 | 내가 적용한 diff (위치) | 세션 55 기록 | 실측 |
|---|---|---|---|
| MV-1 | `remainingGraceDays` 의 return → `return 30;` | 6실패 | **6실패 ✓** |
| **MV-2** | `AuthGate.tsx:161` → `{location.pathname === "/me" && <WithdrawalBanner />}` (**프로덕션 장착 지점**) | 5실패 | **0실패(11/11 초록) ✗** |
| MV-3 | provider 의 `apply` → `useCallback((_next) => undefined, [])` | 3실패 | **3실패 ✓** |
| MV-4 | `submit()` 의 409 분기 제거 → 항상 `describeApiError` | 1실패 | **1실패 ✓** |
| MV-5 (over) | 위험 버튼 `disabled` 에 `\|\| confirmation.length > 0` 추가(맞아도 잠금) | 3실패 | **3실패 ✓** |
| MV-6 (over) | 배너 `cancel()` 의 409 분기 제거 → 오류 문구로 | 1실패 | **1실패 ✓** |

**MV-2 불일치의 원인은 변이 위치다.** `withdrawal.test.tsx` 의 `renderShell`([withdrawal.test.tsx:86-100](../../../frontend/src/me/withdrawal.test.tsx))은 `AuthGate` 을 렌더하지 않고 `<WithdrawalBanner />` 를 직접 마운트한다 — 그래서 **AuthGate 안에서 일어나는 일은 그 어떤 셀에게도 보이지 않는다**. 참고로 배너 **컴포넌트 내부**에 `/me` 게이팅을 넣는 약한 형태(MV-2c: `useLocation().pathname !== "/me"` early return)는 **2실패**(says-why·reads-once)였다 — 세션 55 의 "5"는 어느 쪽 형태로도 재현되지 않는다(기록에 diff 가 없어 재유도가 갈린다 — 가이드 §"write down the diff" 가 경고한 바로 그 사태).

### 3. 신규 반증 변이 — 갭 둘, 확증 셋

| 변이 | diff | 실측 | 해석 |
|---|---|---|---|
| **MV-2b** | `AuthGate.tsx` 에서 `<WithdrawalBanner />` **통째 제거**(프로덕션 전체 화면에서 배너 소멸) | **3파일 52셀 전건 초록**(withdrawal·PersonalHubPage·App) | **갭 B1 실증** |
| **MV-7** | 배너·절 양쪽의 409 처리에서 `apply(await getMyWithdrawal())` → `apply({withdrawal_requested_at: null, purge_due_at: null})`(재조회 없이 로컬 합성) | **11/11 초록** | **갭 B2 실증** — SoT 의 "서버의 지금 상태를 다시 읽어" 가 무셀 |
| MV-8 | `Math.ceil` → `Math.floor` | **4실패**(rounds-up 셀 + 3일 단정 셋) | 올림 리터럴 잠금 ✓ |
| MV-9 | `Math.max(0, …)` 제거 | **1실패**(never-negative 셀) | 0 하한 잠금 ✓ |
| MV-10 | `.withdrawal-banner` 에 `color: #ff3355;` 추가 | 프런트 `designTokens.test.ts` **1실패**("keeps every colour behind a token") | CSS 축 가드 실효 ✓ — ★ 백엔드 `test_design_token_provenance` 는 `:root`↔생성기 연결만 보므로 **이 변이를 잡지 못한다**(초록). 색 리터럴 금지의 기계 시행은 프런트 가드가 유일하다 |

### 4. 전수·기준선 — 전건 재현

- **프런트 전수 460 passed / 39 files · EXIT=0**(756초, 파일 캡처). 세션 55 주장(460/39, 635초)과 셋 수 일치 — 소요 차이는 머신 부하.
- `npx tsc --noEmit` 0에러 · `npm run build` 성공.
- 문서·프런트 읽는 가드 넷(현 HEAD `0cf184a`): **36 passed / 1018 subtests** — 세션 55 기록과 정확히 일치.
- **초점 첫 실행 2실패("남은 기간 3일"이 "4일"로)** — 환경 플레이크로 판정(아래 H1). 재실행 11/11 초록.

## Issues / Risks

### Blocking (계약 의무)

- **B1 — D1=ⓐ "배너는 앱 셸에 있다"의 장착 지점이 무셀이다.** SoT v1.8.54 는 *"셀이 `/me` 아닌 경로에서 배너를 단정해 그것을 잠근다"* 라고 적지만, 그 셀(`says why writing is blocked…`)은 **복제 셸**에서 배너 컴포넌트를 직접 마운트한다 — 프로덕션 장착 지점(`AuthGate.tsx:161`, grep 전수에서 유일)은 어떤 셀에게도 보이지 않는다. **MV-2b: 배너를 AuthGate 에서 통째로 지워도 3파일 52셀 전건 초록.** "배너를 화면 안으로 옮기지 말 것"(계획서 §Slice 4 남는 계약 주의)의 실패 형태가 그대로 배포된다. **처방: 진짜 `AuthGate` 를 렌더하는 셀 하나** — 탈퇴 중 시드 + `/me` 아닌 경로에서 배너 존재 단정(`App.test.tsx` 가 이미 `AuthGate` 를 세우는 선례가 있고, 시드 인프라도 이미 있다). 셀 하나면 MV-2·MV-2b 둘 다 물게 된다.
- **B2 — 취소 409 뒤 "서버의 지금 상태를 다시 읽어" 가 무셀이다.** SoT v1.8.54 가 재조회를 **메커니즘으로 명시**했는데 MV-7(재조회를 로컬 `null` 합성으로 치환)이 11/11 초록이다 — 기존 셀은 결과(배너 소멸·오류 아님)만 잠그고 수단을 안 잠근다. 재조회 실패 문구("탈퇴 상태를 다시 읽지 못했습니다") 경로도 전혀 테스트되지 않았다. **처방: 409 셀에 fetch 호출 단정 한 줄** — 큐에 이미 담아 둔 두 번째 응답이 실제로 **소비되는지**(`fetchMock.mock.calls` 길이 2 · 둘째 호출 GET `/api/me/withdrawal`)를 재면 된다. 관측 가능한 차이가 재조회 실패 경로뿐이라 축은 좁지만, 계약 문언이 이름 붙인 분기는 가이드상 잠겨야 한다.

### Hardening (비차단)

- **H1 — 새 셀의 픽스처가 시계 의존이다(실측 플레이크).** `DUE_IN_THREE_DAYS = Date.now() + 3일` 이 **모듈 스코프**에서 잡히고([withdrawal.test.tsx:41](../../../frontend/src/me/withdrawal.test.tsx)) 렌더 시점의 `new Date()` 와 빼기를 하므로, 시계가 모듈 로드 뒤 **뒤로** 점프하면 `ceil` 이 4 를 낸다. 이 머신(WSL2)은 부팅 직후 창에 시계 스텝이 실제로 반복된다 — 실패 창(08:47~08:50)에 journal **"Clock change detected" 11회**(08:47:30·08:48:01·08:48:31 포함), 같은 픽스처로 앞선 셀은 3일, 뒤의 셀은 4일로 갈라진 것이 산술적 증거. 재실행(시계 안정 뒤) 11/11 초록. **등재: 미수리 표 플레이크 셋째(프런트 계열)**. 처방: 순수함수 셋(명시적 `now`)처럼 렌더 셀도 시각을 고정(`vi.setSystemTime` 등)하거나 픽스처 여유를 하루 폭으로.
- **H2 — `isWithdrawing` 의 정본 필드 선택(`withdrawal_requested_at`)은 공개 payload 로 구분 불가다.** 서버가 두 필드를 항상 함께 세팅/해제한다([`users.py:112-121`](../../../services/application/app/auth/users.py) — 미요청이면 `purge_due_at` 도 `None`). 필드를 바꾸는 변이가 초록일 수밖에 없으나 서버 계약이 결합을 보장하므로 셀을 요구하지 않는다 — 관찰로 기록.
- **H3 — mount 조회 실패 삼킴**(`useMemberQuota` 와 같은 판단, 코드 주석이 사유를 박아 둠)은 계약 밖 — 관찰.
- **H4 — "reads the grace state once on mount" 셀**이 첫 호출 URL(`calls[0]`)만 재고 *횟수*는 못 잰다. `useEffect` 의존 `[]` 이 1회를 구조적으로 보장하므로 마이너.
- **계획서 §Slice 4 범위 문언 "설정 화면의 탈퇴 요청"** — 구현·브리프·SoT 는 모두 `/me`(개인 허브)로 확정했다. 결정 뒤 갱신된 절이 옛 문언을 그대로 담고 있을 뿐(모순 아님) — 다음에 이 문서를 열 때 정정.

## Verdict

**조건부 합격** — B1(진짜 앱 셸을 세우는 배너 장착 셀)·B2(취소 409 재조회의 fetch 단정)를 닫아야 합격이다.

근거: 구현 자체는 스코프 정독한 계약 전 축과 일치하고(409 분할·남은 일수 산술·상태 한 벌·확인 가드·CSS 토큰·구조 주장 셋), 변이 MV-1·3·4·5·6 및 산술 신규 둘(MV-8·9)·CSS(MV-10, 프런트 가드)이 전부 기명 셀로 물었다. 그러나 **이 슬라이스의 핵심 계약 두 문장**(배너는 셸에 있다 · 409 는 서버 상태 재조회로 화면을 맞춘다)이 **각자 무셀 변이(MV-2b·MV-7)로 전건 초록**이므로 "셀이 잠근다"는 SoT 서술은 둘 다 반증된다. 조건을 닫는 처방은 각각 한 셀이다.

## Outstanding items

- **조건 B1·B2 폐쇄는 구현 세션 몫**(셀 추가만으로 코드 무변 가능) — 폐쇄 뒤 승격 재검(변이 재적용)은 다음 검증 세션이 한다(세션 51 Decisions 선례: 조건을 닫은 세션은 자기 판정을 못 올린다).
- **플레이크 H1 을 미수리 표에 등재했다**(HANDOFF) — 고칠지는 오너/다음 슬라이스 판단.
- 개발 스택 재생성(`withdrawal_worker` 미기동)·배포 대기·육안 확인 목록(배너 좁은 화면)은 그대로.

## Reproduction

```bash
cd <repo>
git status --short                      # 무출력 확인(변이 전 게이트)
# 초점
cd frontend && npx vitest run src/me/withdrawal.test.tsx   # 11 passed
# 갭 B1: AuthGate.tsx:161 에서 <WithdrawalBanner /> 줄을 지우고
npx vitest run src/me/withdrawal.test.tsx src/me/PersonalHubPage.test.tsx src/App.test.tsx
# → 52 passed(갭: 아무 셀도 못 문다)
git checkout -- frontend/src/auth/AuthGate.tsx   # 절대경로로
# 갭 B2: withdrawal.tsx 의 409 처리 두 곳에서 apply(await getMyWithdrawal()) 를
#        apply({withdrawal_requested_at: null, purge_due_at: null}) 로 바꾸고
npx vitest run src/me/withdrawal.test.tsx        # → 11 passed(갭)
git checkout -- frontend/src/me/withdrawal.tsx
# 전수(파일 캡처)
npx vitest run --reporter=basic > /tmp/full.txt 2>&1; echo EXIT=$?   # 460/39
# 문서 가드(백엔드, 무변 대조용 기준)
cd .. && python3 -m pytest tests/test_design_token_provenance.py tests/test_repo_hygiene.py \
  tests/test_product_name.py tests/test_docs_indexes.py -q           # 36/1018 @0cf184a
```
