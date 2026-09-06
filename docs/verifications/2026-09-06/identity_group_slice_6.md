# identity group Slice 6(grouped Inbox UI)— 독립 검증

## Subject metadata

- 검증일: 2026-09-06
- 요청자: 오너 — *"작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래? Slice 6 완료입니다."*
- 검증자: 이 세션(구현 세션 17·2026-09-06과 다른 세션). 구현자 보고(오너 전달 메시지·work_log 세션 17·SoT v1.8.34 행·커밋 메시지 5건)는 전부 가설로 취급해 원본에서 재유도했다.
- 대상: 커밋 5건 — `c8ab9cf`(프론트 기존 결함 2건 폐쇄 + 착수 브리프) · `07a7428`(읽기면 `group_revision`, D1=A) · `0083f34`(grouped Inbox UI) · `149263a`(폐쇄 기록 · SoT v1.8.34) · `c260e49`(기준선 갱신). 검증 개시 시 트리 clean.
- 정규 계약: 브리프 [`pending-candidate-identity-grouping-slice6-grouped-inbox-ui-decisions.md`](../../plans/pending-candidate-identity-grouping-slice6-grouped-inbox-ui-decisions.md)(확정 **D1=A·D2=B**, 오너 2026-09-06) · [`system-contract-sot.md`](../../system-contract-sot.md) **v1.8.34**(변경이력 행 + "검토함 그룹 읽기면" 계약 절) · 페이즈 문서 §Slice 6(범위·규칙·검증 목록·완료 기록).

## Scope

1. **경계 행렬** — SoT 계약 절 리터럴 ①~⑤(묶기·첫 등장 순서 / 기본 펼침·접어도 머리·액션 잔존 / 결과 상자 페이지 수준·`applied`/`skipped` 아닌 step 잔여 보고 / job 표시·`contradicted` 경고만 / 멤버 개별 affordance 유지) + 페이즈 검증 목록 6항 + 읽기면 6키 + D2=B 방어 단언(`uncertain` 미개방)을 should / should-NOT / 리터럴로 전개. ★ 최우선 의심축은 HANDOFF Next Tasks 1이 지정한 검증자 자리 셋(**① 결과 상자 페이지 수준 ② `group_revision` 픽스처가 revision 0이 아닌 이유 ③ 좁은 폭 스타일시트 규칙성**)과, 검증자가 추가한 **step 리터럴 3종(`conflict`·`failed`·`pending`)의 전건 잠금 여부**.
2. **구현 코드 감사** — `analysis/review_inbox.py`(`IdentityGroupSummary.revision`) · `routers/analysis.py`(`_identity_group_payload`·approve/reject 라우트·유료 배선) · `analysis/identity_groups.py`(revision 저장 계약) · `frontend/src/review/ReviewInbox.tsx` · `frontend/src/api/client.ts` · `frontend/src/styles.css`.
3. **테스트 코드 감사** — `tests/test_review_inbox_identity_groups.py`(신규 1 + 갱신 5) · `ReviewInbox.test.tsx`(+12) · `pageLayout.test.ts`(+2) · `typeScale.test.ts`(이관 목록 7행) — 단정이 계약을 잡는지, not 스냅샷 부산물.
4. **등재 표면** — OpenAPI 독립 재덤프(`git worktree`로 `07a7428^`와 HEAD 대조) · `gen:api` 후 트리 무변 · plans 인덱스 등재 · 기준선 줄·상태 마커.
5. **전수 재실행** — 백엔드·프론트(순차 — HANDOFF "겹쳐 돌리지 말 것").
6. **뮤테이션** — 구현자 표 9종 중 8종 재유도(정확한 diff 기록) + 검증자 신규 3종(광역 M5·정밀 M5·**M10 pending 배제**).

## Methodology

환경(측정의 일부): **알파**(WSL2 `DESKTOP-27QM1FP`, HANDOFF 머신 표 기준 2026-09-06 알파 전환 후) · test-mongo `127.0.0.1:27020` healthy(기동 4시간 경과 — PRIMARY 대기 함정 해당 없음) · 백엔드 전수는 호스트 `python3 -m pytest -q`(`~/.local` user-site) · 프론트는 `frontend/`에서 `npx vitest run`.

- **트리 게이트**: 검증 개시 `git status --short` 공백 확인. 모든 뮤테이션은 verification.md §"Mutation testing"의 **clean-tree 분기**(Edit → 집중 실행 → `git -C /mnt/f/devel/ai_writte_system checkout -- <절대경로>` → `git status --short` 공백 재확인)로 수행. 종료 시 0 변경 확인. **cwd 함정 대응**: 구현자가 같은 날 두 번 걸린 그 함정(`frontend/` 잔류 cwd)을 검증 중 1회 재현했다 — 저장소 루트에서 `npx vitest run src/review/…`를 돌려 jsdom 환경이 안 붙은 채 22 전건 실패(`document is not defined`). 이는 변이 결과가 아니라 실행 환경 오류로 폐기하고 `frontend/`에서 재실행했다. 측정은 전부 `frontend/` 기준.
- **전수**: `python3 -m pytest -q`(백그라운드, 종료 코드 0) · `cd frontend && npx vitest run` · `npx tsc --noEmit` · `npm run gen:api` 후 `git status --short`.
- **OpenAPI 대조**: `git worktree add /tmp/wt-slice6-pre 07a7428^` 후 양쪽 `python3 scripts/dump_openapi.py | md5sum` 비교(사후 worktree 제거).
- **★ CSS 실효값 측정(B2의 핵심)**: `var()` 실패의 실효값은 사양(computed-value time 실패 → `unset` → 상속값; cascade에서 진 다른 선언은 되살아나지 않음)이지만 jsdom이 계산값을 못 재므로 **실엔진으로 측정**했다 — WSL에서 Windows Chrome headless(`--headless --dump-dom`)에 실제 두 규칙(`.resource-link` 1362-1370행의 값, `.review-summary-link` 2073-2078행의 값)을 같은 순서·같은 특이도로 재현한 프로브를 띄우고 `getComputedStyle`로 fontSize·fontFamily를 읽었다. 프로브: pre-fix(`var(--type-body)`, 미선언) vs post-fix(`var(--type-base)`, 1rem).

## Findings

### 1. 전수·생성물 — 구현자 주장 전부 재현

| 주장 | 실측 | 판정 |
|---|---|---|
| 백엔드 **2891 passed / 1 skipped / 3792 subtests** | `2891 passed, 1 skipped, 3792 subtests passed in 333.10s`(exit 0) — skip 1 = live Chroma | ✅ 일치 |
| 프론트 **417 passed**(403 → +14) | `Test Files 35 passed (35) / Tests 417 passed (417)` — 신규 `it` 수 ReviewInbox 12 + pageLayout 2 = +14 산술도 일치 | ✅ 일치 |
| tsc 무오류 · build 성공 | `npx tsc --noEmit` 무오류(build는 재실행 안 함 — tsc와 vitest로 동일 위험군 커버) | ✅(tsc만 재측정) |
| OpenAPI 무변 **md5 `d60b94d3…`** | HEAD `d60b94d3a4c15a2b6e528af50756bf44` = `07a7428^` 동일(worktree 대조) | ✅ 일치 |
| `schema.d.ts` 재생성 불요 | `npm run gen:api` 후 `git status --short` 공백 | ✅ 일치 |
| `revision`은 `set_group_status`에서만 오르고 `add_member`는 그룹 행을 안 건드린다(브리프 사실 정정) | `identity_groups.py:382`(`revision=group.revision + 1` — set_group_status 유일) · `add_member`(`:376-421`)는 `get_group`을 **읽기만** 하고 member 행만 upsert | ✅ 코드로 확인 |
| 기존 결함 2건 사전존재 | SoT v1.8.27 행(2026-09-04)이 이미 "2 실패는 세션 시작 시점부터(`typeScale` 49↔54 · `designTokens` `--type-body`)"로 기록 — `d02837a`(2026-09-02)가 `var(--type-body)` **사용**을 도입했고 `git log --all -S '--type-body:'`로 **선언 이력 0건** 확인("선언된 적 없는 토큰"은 참) | ✅ |

### 2. 검증자 자리 셋(HANDOFF 지정) — 전부 확정

- **① 결과 상자 페이지 수준**: `groupOutcomePanel()`이 `<ul class="resource-list">` 밖(섹션 직속, ReviewInbox.tsx 렌더 순서 error → outcome → 목록)에서 렌더되고 `outcome` state는 `data`와 별개(`runAction`의 재조회가 못 덮어쓴다). 잠금: 뮤테이션 **M6f**(재조회 뒤 `setOutcome(null)`) → **4 재실패**(승인·거절·부분실패·conflict 셀). "그룹이 다 처리되면 목록에서 빠지는데 결과는 살아야 한다"는 계약 문면이 셀 4개로 잠겨 있다. 구현자 서술("셀이 배치가 아니라 계약 위반을 잡았다")은 M6f·M7f(잔여 공집합 → 2 재실패)로 뒷받침된다.
- **② 픽스처가 revision 0이 아닌 이유**: 백엔드 신규 셀 `test_group_revision_is_the_live_group_revision`은 멤버 3 + 상태 전이 2회로 **revision 2 ≠ 멤버 3**을 만들고 `group_revision == 2`·`group_size == 3`·`get_group(…).revision == 2`를 함께 단정. 프론트 픽스처 `group()`은 **revision 3, size 2**. 뮤테이션 — **M2r**(payload 상수 0) → **1 재실패(신규 셀만; 기존 정확 일치 5셀은 전부 기대값 0이라 통과)**, **M1r**(payload = 멤버 수) → **6 재실패**, **M4f**(승인 body 상수 0) → **1 재실패**. "기존 픽스처를 0으로 두면 상수 박기가 전건 통과한다"는 구현자 분석은 정확했고, 그래서 이 셀들이 존재한다. M1r/M2r의 6 = 기존 5셀의 dict 정확 일치 단정 + 신규 1 — D2=B의 방어 단언(읽기면 6키 고정, `uncertain_peer_ids` 류 additive 키도 같은 5셀이 문다)도 같은 자리에서 잠긴다.
- **③ 좁은 폭 스타일시트 규칙성**: `.review-group-header`의 `flex-wrap: wrap` + `.review-group-copy`의 `min-width: 0`·`flex: 1 1 18rem`을 `pageLayout.test.ts` "정체성 그룹 상자 배치" 2셀이 정규식으로 단정. 뮤테이션 **M9f**(두 선언 제거) → **1 재실패**. jsdom이 배치를 못 재는 제약 아래 계획 §Slice 6 검증 항목("모바일 폭에서 겹침 없음")의 대리 잠금으로 성립한다(실제 겹침 비침은 육안 확인 영역).

### 3. 뮤테이션 — 구현자 표 9종 중 8종 재유도, 전부 기명 재실패 수치 일치

| # | 변이(적용한 diff) | 구현자 주장 | 실측 | 판정 |
|---|---|---|---|---|
| M2r | `routers/analysis.py` `"group_revision": summary.revision` → `0` | 1 | **1**(신규 셀) | ✅ |
| M1r | 같은 자리 → `len(summary.member_ids)` | 6 | **6** | ✅ |
| M3r | 키 삭제 | 6 | 재실행 안 함 — M1r이 같은 셀 집합(정확 일치 5 + 신규 1)을 이미 물었음 | (생략, 근거 명시) |
| M4f | `approveIdentityGroup(…, group.group_revision)` → `0` | 1 | **1** | ✅ |
| M5f(정밀) | `groupEntry` 멤버 `<li>`에서 `{candidateActions(item)}` 제거 | 1 | **1**(개별 affordance 유지 셀) | ✅ |
| M5f(광역·검증자 신규) | `candidateActions` 상단 `return null;`(전 행 대상) | — | **5**(사전존재 4 + 유지 셀 1) | 변이 폭 차이 — 구현자 변이가 더 좁았을 뿐, 주장과 모순 아님 |
| M6f | `runAction` 성공 경로 `await load()` 뒤 `setOutcome(null);` | 4 | **4** | ✅ |
| M7f | `unfinished` → `steps.filter(() => false)` | 2 | **2**(failed·conflict 셀) | ✅ |
| M8f | `buildEntries` 상단 `return items.map((item) => ({kind:"candidate", item}))` | 11 | **11** | ✅ |
| M9f | styles.css에서 `flex-wrap: wrap`·`min-width: 0` 제거 | 1 | **1**(pageLayout) | ✅ |
| **M10f(신규)** | `unfinished` → `steps.filter(s => s.status === "failed" \|\| s.status === "conflict")` | — | **0 — 22 passed** | **★ 안 물었다 → B1** |

### 4. 커밋 감사 — 외도 없음

- `07a7428`: 구현 3줄(필드·대입·payload 키) + 셀 1 + 기존 5셀 갱신 + 브리프 상태 갱신. `IdentityGroupSummary` 생성 지점은 전 저장소 1곳(`review_inbox.py:167`, 키워드 인자 — 필드 삽입 파급 없음)이고 `_identity_group_payload` 호출 지점도 1곳(`routers/analysis.py:849`, 목록·단건 공유 serializer)이라 **읽기 경로 두 개가 갈라질 수 없다**.
- `0083f34`: UI·client 타입·셀·스타일. `identity_group?: … | null` optional은 "Slice 3 이전 픽스처가 키를 안 싣는" 사실 반영(서버는 항상 전송). 그룹 액션 버튼이 `.row-actions` 안에 있어 accent 3규칙 묶음 상속(buttonAppearance 가드 green)도 확인.
- `c8ab9cf`·`149263a`·`c260e49`: 각각 결함 폐쇄+브리프, 폐쇄 기록, 기준선(최상위 README 절차 표 한 줄 포함 — HANDOFF가 지시한 그 줄). 변경 영역 전부 슬라이스 목적으로 추적 가능.

### 5. ★ 반증 1(B2) — "1.3rem 세리프 → 1rem, 행 크기가 실제로 바뀐다"는 사실이 아니다

구현자 보고·SoT v1.8.34 변경이력·페이즈 완료 기록·CHANGELOG·work_log·typeScale.test 주석·커밋 메시지가 공통으로 주장하는 *"선언이 통째로 버려지고 `.resource-link`의 1.3rem 세리프가 그대로 그려지고 있었다 → `--type-base`로 고쳤으므로 행 크기가 실제로 바뀐다(육안 확인 대상, 무해한 정리가 아님)"*을 **실측으로 반증**했다.

- cascade: `<a class="resource-link review-summary-link">`에서 두 규칙은 특이도 동일(0,1,0)·`.review-summary-link`(styles.css:2073)가 문서 순서상 뒤 → font-family·font-size **모두** 이 규칙이 이긴다. `.resource-link`의 1.3rem(1362-1370행)은 이미 cascade에서 졌다.
- `var(--type-body)`(미선언)은 **computed-value time 실패** → `unset` → font-size(상속 속성)는 **부모 상속값**. cascade에서 진 선언은 되살아나지 않는다. 상속 사슬(`html`→`body`→`main`→`.workspace-page`→`ul.resource-list`→`li`)에 font-size 선언은 전수 grep 상 **0건**(`*`는 box-sizing뿐) → 상속값 = 16px = 1rem.
- font-family는 `system-ui, sans-serif` 선언이 **유효했고 이기고 있었다** — 세리프로 그려지고 있었다는 전제부터 성립하지 않는다.
- **실엔진 측정**(headless Chrome, 두 규칙을 값·순서 그대로 재현): pre-fix `font-size 16px / font-family "system-ui, sans-serif"`, post-fix **동일**. **가시적 변화 0.**
- 사실 관계: 가시 변화(1.3rem 세리프 → 1rem sans)가 있었다면 그 시점은 `d02837a`(2026-09-02)가 이 규칙을 추가한 커밋이지, `c8ab9cf`(2026-09-06)의 토큰 교정이 아니다. `c8ab9cf`는 **같은 계산값(1rem)을 유효한 선언으로 만든 정리**다 — 필요하고 옳지만(선언된 토큰 + typeScale 가드가 `.review-summary-link: base`를 잠금) **무해한 정리가 아니라는 주장은 거짓**이고, 파생된 "육안 확인 대상"도 근거가 없다.
- **전파 경로**(정정 필요 범위): SoT `system-contract-sot.md:36`(v1.8.34 행 꼬리) · 페이즈 `…implementation-phases.md:370-371` · `CHANGELOG.md:5`(2026-09-06 행) · `work_log.md:397,400`(세션 17 §1) · `frontend/src/typeScale.test.ts:121-122`(주석) · 커밋 `c8ab9cf` 메시지(이력 불변 — 정정 대상에서 제외, 기록으로 남김). HANDOFF 본문에는 이 주장이 없다(전파되지 않음).

### 6. ★ 반증 2(B1) — `pending` step은 계약이 열거했는데 잠그는 셀이 없다

SoT v1.8.34와 페이즈 완료 기록은 잔여 판정을 *"**`applied`/`skipped` 아닌 step(`conflict`·`failed`·`pending`)은** '반영'으로 세지 않고 남은 건수를 따로 말한다"*로 열거한다. 구현(`ReviewInbox.tsx` `unfinished`)은 올바른 보수형(`!== "applied" && !== "skipped"`)이지만 셀은 `failed`·`conflict` 두 표본뿐이고 **`pending` 표본이 없다**. 뮤테이션 **M10f** — 잔여 판정을 두 리터럴 열거로 좁히는(=`pending`을 빼는) 과잉 교정을 심으니 **22 passed, 아무 셀도 안 물었다**.

이 빈 칸은 실전에서 가장 자주 닿는 자리다: D4=A(첫 판정 실패에 패스 종료)의 실제 부분 패스 모양은 `[applied, failed, pending, …]`이므로 남은 건수의 대부분이 `pending`인데, 정확히 그 step이 잘못 세져도 green이다. `STEP_STATUS_LABELS.pending`("이번 패스에서 처리 안 됨") 라벨 렌더도 무셀 상태다. verification.md의 원칙("계약이 요구하는 분기의 빈 칸은 초록바와 무관하게 blocking")에 따라 차단으로 분류한다. 처방은 한 셀이다 — `mixedInbox()` 3멤버로 steps `[applied, failed, pending]`을 주고 "2건이 남았습니다" + "이번 패스에서 처리 안 됨" 라벨을 단정(양방향: 보수형을 열거형으로 되돌리면 재실패, 전원 성공 취급[M7f 방향]에도 재실패).

## Issues / Risks

### Blocking(계약 의무)

- **B1 — `pending` step 잔여 판정 셀 부재**(Findings §6, M10f로 입증). SoT/페이즈가 열거한 세 리터럴 중 하나가 무셀. 조건: 위 처방의 셀 1개 추가.
- **B2 — SoT v1.8.34 변경이력의 사실 오류와 전파**(Findings §5, headless Chrome 실측으로 반증). 정본 변경이력이 *"실크기가 1.3rem→1rem 으로 바뀌어 육안 확인 대상"*이라 기록했으나 **가시적 변화는 0**이었다. 조건: SoT v1.8.34 행(및 페이즈 370-371 · CHANGELOG:5 · work_log 세션 17 §1 · typeScale.test.ts 주석)의 해당 문장 정정 — `c8ab9cf`의 교정 자체는 유지한다(올바른 정리였다; 거짓인 것은 "가시 변화가 있었다"는 서술). SoT 정정은 이 저장소 선례상 버전 개정 사안이다.

### Hardening recommendations(비차단)

- **H1 — 그룹 승인(유료 경로)의 402/429 화면 처리가 기존 유료 화면과 안 맞는다.** 브리프 follow-up이 *"UI 문구를 기존 유료 화면(`WritingPanel`의 quota 표시)과 맞춘다"*로 남겼는데, 검토함의 그룹 액션은 `describeApiError` 원문(`429: the same request…`, 영어) alert뿐이다. `WritingPanel`은 `describeQuotaError`·429 되묻기(`X-Confirm-Duplicate`)·402 안내·잔여 표시를 갖췄다. 특히 결과 상자의 안내 문구 *"나머지는 승인을 다시 눌러 이어서 진행합니다"* 직후 재클릭은 `identity_group_approve`의 5초 최소 창(`quota/lock.py` `release` → `cooldown_until`)에 걸려 429가 난다 — 슬라이스가 스스로 유도한 클릭이 유료 가드와 시간충돌하는 자리. 완료 기준 #6("실패를 사람이 이해할 수 있다")과의 관계는 오너 판단 몫.
- **H2 — 409(낡은 revision) 뒤 재동기화가 없다.** `runAction`의 catch는 알림만 남기고 재조회하지 않고, 화면에 수동 재조회 버튼도 없다 → 같은 그룹에 다시 누르면 같은 409가 반복되고 회복은 화면 이동(재마운트)뿐이다. D1=A의 "409 재동기화" 중 서버 절반만 구현됐다(클라이언트가 값을 다시 읽는 경로가 없다).
- **H3 — `idempotent_replay: true` 표시 문구 무셀.** "이미 끝난 그룹이라…"/"이미 끝난 패스의 재확인입니다" 라벨이 셀 없이 렌더된다(계약 문면 밖 — 표시는 있으나 잠금 없음).
- **H4 — `outcome` 단일 슬롯.** 연속해서 두 그룹에 액션하면 이전 결과 요약이 대체된다. 계약 문면("재조회를 넘겨 산다")은 마지막 액션 수준이라 위반은 아니나, 두 그룹의 부분 실패를 동시에 추적하는 도그푸드 시나리오에서 하나가 조용히 사라진다.
- **H5 — plans 인덱스 꼬리 낡음.** `plans/README.md:75` 행 꼬리가 "Slice 6(grouped UI) 다음"으로 멈춰 있다(선두 토큰 `Active`는 문서와 같아 가드는 green). 본 검증의 상태 갱신에 맞춰 함께 고친다.

## Verdict

**조건부 합격** — 조건: **B1**(`pending` step 잔여 판정 셀 추가)과 **B2**(SoT v1.8.34 변경이력의 "1.3rem→1rem 가시 변화 · 육안 확인 대상" 서술 정정 및 전파 문서 동반 정정)가 닫힐 때까지.

근거 요약: 구현·셀·뮤테이션·전수·생성물 무변 주장은 전부 재현됐고(8/8 재유도 뮤테이션이 수치까지 일치), HANDOFF가 지정한 검증자 자리 셋은 전부 실질 잠금으로 확인됐다. 그러나 (1) 계약이 열거한 step 리터럴 `pending`이 무셀인 채 green이고(M10f 입증), (2) 정본 변경이력에 실측으로 반증된 사실 서술이 기록되어 전파됐다. 둘 다 작은 처방으로 닫히는 자리라 합격 조건부로 둔다.

## Outstanding items

- **조건 B1·B2의 처방 주체** — 다음 슬라이스(또는 오너 지시). B2의 SoT 정정은 버전 개정을 수반한다(선례: "정정은 버전 개정 사안", HANDOFF 미수리 표).
- 본 검증이 함께 갱신하는 것: 검증 인덱스 등재 + 판정 분포/건수(285→286, 조건부 91→92) · 최상위 README 검증 건수 2곳 · work_log 세션 18 · HANDOFF Next Tasks 1 · 페이즈 문서/plans 인덱스 상태 마커(Slice 6 검증 조건부).
- 구현자가 보고한 "cwd 함정 2회"는 기록대로였고(work_log 세션 17 §7) 커밋 선행으로 실손실 없음 — 검증자도 변형 중 1회 유사 경로 오류(저장소 루트 실행)를 냈고 측정 폐기·재실행으로 처리했다.

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system && git status --short          # 공백이어야 함
# 전수(순차)
python3 -m pytest -q                                             # 2891 passed / 1 skipped / 3792 subtests
(cd frontend && npx vitest run && npx tsc --noEmit && npm run gen:api && git -C .. status --short)
# OpenAPI 무변
git worktree add /tmp/wt-pre 07a7428^
python3 scripts/dump_openapi.py | md5sum                         # d60b94d3a4c15a2b6e528af50756bf44
python3 /tmp/wt-pre/scripts/dump_openapi.py | md5sum             # 동일
git worktree remove /tmp/wt-pre
# 뮤테이션 예(전부 Edit → 실행 → git -C /mnt/f/devel/ai_writte_system checkout -- <path>)
#   B1 입증: ReviewInbox.tsx unfinished → failed/conflict 열거 → (cd frontend && npx vitest run src/review/ReviewInbox.test.tsx) → 22 passed(안 물림)
#   B2 입증: styles.css 두 규칙(.resource-link / .review-summary-link pre·post)을 재현한 HTML을
#            headless Chrome --dump-dom + getComputedStyle → pre/post 모두 16px·system-ui
```
