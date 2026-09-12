# 계정 탈퇴 Slice 4b — 관리자 잔여 정리 독립 검증

## Subject metadata

- **검증일**: 2026-09-12 (검증 세션 71)
- **요청자**: 오너 (구현 세션 70 지시 — "서브 에이전트 하나 스폰해서 독립검증 맡기고 결과 나오면 보강할 부분 보강")
- **검증자**: 구현 세션과 다른 독립 세션. 이 슬라이스의 어떤 코드도 쓰지 않았다.
- **대상**: 계정 탈퇴 Slice 4b(관리자 잔여 정리). 커밋 `73ae7f7`(브리프) · `2aa9e3f`(백엔드) · `b3e5ec0`(프런트) · `c443b4c`(계획서) · `21626b8`(선언 지도) · `9806b7a`(기록, HEAD). 작업 트리 clean(`git status --short` 빈 출력으로 확인).
- **정규 스펙(계약 스코프)**: [`plans/slice4b-admin-residual-purge-decisions.md`](../../plans/slice4b-admin-residual-purge-decisions.md) — 오너 결정 **①ⓐ 계정 하나 · ②ⓐ 두 액션 · ③ⓐ admin_audit 감사**(2026-09-12)와 "결정을 따라오는 것"·"후속 고려" 절. 부모 계획서 [`account-withdrawal-implementation-phases.md`](../../plans/account-withdrawal-implementation-phases.md) §Slice 4b(117-121행)·§Slice 3 남는 계약 주의(98-104행)·D3·D5·D6 오너 결정 표(139-144행). [`slice4-withdrawal-screen-decisions.md`](../../plans/slice4-withdrawal-screen-decisions.md) §후속 고려 첫 항목(갈래 셋의 원문, 55행). SoT `docs/system-contract-sot.md` v1.8.62 행(63행).
- **환경**: WSL2 · python3(초점 실행 내 skip 0 — pymongo 설치됨) · frontend node/npx vitest(openapi-typescript 7.13.0). **전수는 돌리지 않았다**(검증 지시 — 이 머신에서 전수를 겹치면 과부하 타이밍 탐오가 난다. 구현 세션 기록 3053/1/4213 · 488/41은 대조값으로만 사용).

## Scope

| 표면 | 무엇을 보는가 |
|---|---|
| 본체 | `services/application/app/deletion/account_reconcile.py` — 조건·순서가 스크립트 이관본과 일치하는가(Slice 3 계약 주의 ⓕ "한 벌") |
| 라우터 | `services/application/app/routers/admin.py` GET/POST `/admin/users/{user_id}/reconcile` — 404/409/400 계약, 호출 직전 스탬프 재확인(경합), 감사 2단계·fail-closed·best-effort outcome |
| 감사 | `auth/admin_audit.py`·`auth/admin_audit_mongo.py` — action 확장, `record_account_reconcile_requested`, `record_purge_outcome` 의 target_user_id 상속(프로젝트 purge 무변), `list_destructive_events`(member_quota 계속 밖) |
| 스키마·읽기 | `api/models.py`(AdminUserPayload 스탬프 둘·세 스키마·`target_project_id: str \| None`)·`api/errors.py`(`_ERRORS_ADMIN_400_404_409`) |
| 스크립트 | `scripts/account_purge_reconciler.py` — 본체 import 로 얇아졌는가, 출력 키 무변 |
| 등재 | `tests/test_auth_api.py`(tier 107·admin 19)·`tests/test_application_api.py`(선언 지도 19)·`activity/actions.py`(EXCLUDED 32·절 주석 12·POST 만)·프런트 `gen:api` 재생성 |
| 셀 | `tests/test_admin_account_reconcile.py`(13셀)·`tests/test_account_withdrawal_worker.py` ReconcilerTest(이관 4셀)·`tests/test_auth_api.py` payload 핀·프런트 `AdminUserDetail.test.tsx`(4)·`AdminConsole.test.tsx`(1)·`navigationLinks.test.ts` |
| 프런트 화면 | `AdminUserDetail.tsx`(조사→사용자명 확인→실행)·`AdminConsole.tsx`·`userStatus.ts`(세 번째 축 라벨)·새 CSS 규칙 부재 |

## Methodology

1. **사전 점검**: `git status --short` 빈 출력(클린 트리 — 뮤테이션 표준 절차 적용).
2. **계약 스코핑 → 경계 행렬**: 위 스코프 문서를 먼저 읽고 계약 요구 분기(should fire / should NOT fire)를 표로 세운 뒤 코드를 봤다(아래 Findings 표).
3. **diff 대조**: `git show 2aa9e3f -- scripts/account_purge_reconciler.py` 로 이관 전후 본체를 줄 단위 대조(질의·조건·출력 키).
4. **초점 실측**(전수 제외):
   - `python3 -m pytest tests/test_admin_account_reconcile.py tests/test_account_withdrawal_worker.py -q` → **28 passed**
   - `python3 -m pytest tests/test_auth_api.py -q` → **153 passed, 1222 subtests**
   - `python3 -m pytest tests/test_application_api.py::AdminErrorContractDeclarationTest tests/test_activity_actions.py -q` → **13 passed, 194 subtests**
   - `python3 -m pytest tests/test_admin_audit.py -q`(M6 폭 확대용) → 초록
   - 프런트(`frontend/` 안에서): `npx vitest run src/admin/AdminUserDetail.test.tsx src/admin/AdminConsole.test.tsx src/navigationLinks.test.ts` → **20 passed (3 files)**
5. **`gen:api` 무드리프트**: `cd frontend && npm run gen:api` → `git status --short` 빈 출력(재생성 결과가 커밋된 `schema.d.ts`와 무차분).
6. **뮤테이션 10종**: 절차는 매번 동일 — `git status --short` 확인(빈) → 변이 → 초점 셀 재실행(요약 줄 `passed/failed` + `FAILED|SUBFAILED` 같이 읽음) → `git checkout -- <파일>` → `git status --short` 빈 확인. 변이별 diff 를 아래 표에 그대로 남긴다.
7. **스크립트 스모크**: `python3 scripts/account_purge_reconciler.py`(dry-run, 읽기 전용) 시도 — 이 검증 환경에서 Mongo(`localhost:27520`) 접속이 열리지 않아 25초 타임아웃 강종(EXIT=143). 대체: `import scripts.account_purge_reconciler` + `inspect.getsource(main)` 로 ①임포트 성립 ②`main` 이 `AccountReconcileService`·`MongoAccountReconcileRepository` 를 쓰는지 ③모듈 수준에 이관 전 함수(`stalled_user_ids`·`leftover_projects`·`reconcile`) 잔류 없음 — 세 가지 확인.

## Findings

### 경계 행렬 — 계약 분기 ↔ 기명 셀 대응

| # | 계약 조항(출처) | 코드 | 셀 | 판정 |
|---|---|---|---|---|
| B1 | 조사는 dry-run, 파괴 없음(②ⓐ · SoT) | `account_reconcile.py:78-82`·`admin.py` GET | `test_survey_reports_leftovers_and_tombstone_without_destroying` | 잠김(M1·M10) |
| B2 | 404 사용자 없음(브리프 셀 · SoT) | `admin.py:498-502`(`_stalled_user_or_error`) | `test_survey_of_a_missing_user_is_404` | 잠김(GET 경유) |
| B3 | 409 파기 미시작 + **조사·실행 양쪽** 호출 직전 재확인(SoT "양쪽이…재확인한다" · 브리프 후속 고려) | `admin.py:516`·`admin.py:535` | GET: `test_survey_of_an_unclaimed_account_is_409_not_a_no_op`·`test_a_grace_period_account_is_not_a_reconcile_target`. **POST: 셀 없음** | **C1(차단)** — M3 실증 |
| B4 | 400 빈 사유(SoT — 사유 필수) | `admin.py:536-538` | `test_execute_requires_a_non_blank_reason` | 잠김 |
| B5 | 잔여 없음+묘비 있음 → 계정 행 삭제(Slice 3 주의 · 스크립트 조건) | `account_reconcile.py:84-98` | `test_execute_sweeps_and_removes_the_user_row_when_clear` + ReconcilerTest 4셀 | 잠김 |
| B6 | 프로젝트 잔여 있으면 행 안 지움(동일) | 같은 줄 | `test_execute_keeps_the_row_while_projects_remain` + ReconcilerTest | 잠김(M2) |
| B7 | 묘비 없으면 행 안 지움(동일) | 같은 줄 | `test_execute_keeps_the_row_without_a_tombstone` + ReconcilerTest | 잠김(M1) |
| B8 | 감사 2단계 fail-closed, action=`account_reconcile`, target_type="user", target_user_id 상속(③ⓐ · SoT) | `admin_audit.py:136-160`·`111-134` | `test_execute_is_audited_in_two_stages_with_the_target_user` | 잠김(M4·M5) |
| B9 | 본체 실패 → failed 결과 행 + 예외 전파 | `admin.py:543-557` | `test_a_failed_execution_records_the_failed_outcome` | 잠김(M4) |
| B10 | 감사 화면이 account_reconcile 을 보여준다(SoT) | `admin.py:656-664` | `test_the_audit_surface_lists_account_reconcile_events` | 잠김(포함 방향만) |
| B11 | member_quota_policy 는 **계속 이 화면 밖**(SoT) | `admin_audit.py:69-76`·`admin_audit_mongo.py:52-62` | **셀 없음** | **C2(차단)** — M6 실증 |
| B12 | 상속이 프로젝트 purge 축을 오염시키지 않음(SoT "프로젝트 purge 는 None 이라 무변" · 8.5-b D3=ⓑ 축 무결) | `admin_audit.py:130` | **셀 없음**(과교정 방향) | **C3(차단)** — M5b 실증 |
| B13 | AdminUserPayload 스탬프 둘(세 번째 축, 서버 값 그대로 · `purge_due_at` 부재) | `admin.py:231-236`·`models.py:240-244` | `test_the_admin_user_payload_carries_both_withdrawal_stamps` + `test_auth_api.py:1112-1140` 핀 둘 | 잠김 |
| B14 | 등재: tier 107/admin 19 · 선언 지도 19 · EXCLUDED 32(POST 만) | `test_auth_api.py:2131-2135`·`test_application_api.py:2498-2504`·`actions.py:237-243` | 각 가드 셀 | 잠김(실측 초록) |
| B15 | 프런트: stalled 에만 정리 UI · 조사→결과→사유+사용자명 확인→실행→결과 · 409 처리 · 목록 세 번째 축 옆 표시 | `AdminUserDetail.tsx:174-258`·`userStatus.ts:19-30`·`AdminConsole.tsx:219-221` | 프런트 5셀 | 잠김(M8·M9) |
| B16 | 본체 한 벌 — 라우터와 스크립트가 같은 모듈(Slice 3 ⓑ·브리프) | `admin.py:519`·`scripts/account_purge_reconciler.py:37-40` | 라우터 셀(M10)·ReconcilerTest | 잠김 |

### 표면별 관찰

- **본체 이관은 충실하다.** `git show 2aa9e3f -- scripts/account_purge_reconciler.py` 줄 대조: stalled 질의(`{"purge_started_at": {"$ne": None}}` + sorted)·`owner_id` 프로젝트 질의(sorted)·묘비 질의(`document_id(user_id)` find_one)·`delete_one` 판정이 전부 무변이고, 실행 조건 `if not projects and has_tombstone`(`account_reconcile.py:89`)도 문면 그대로. 스크립트 출력 키(`mode`·`live_user_count`·`stalled_user_ids`·`would_reconcile`{2}·`reconciled`{4}) 무변. 스크립트는 인자·JSON 출력만 남았다(모듈 수준 잔류 함수 0 — import 검사).
- **라우터 계약**(admin.py:495-575): 404/409는 `_stalled_user_or_error`(498-510)가 한 곳에서 — GET(516)·POST(535) 양쪽이 호출한다. 400 빈 사유(536-538). 감사 요청 행(540-543)은 try 밖 — **fail-closed**(감사 쓰기가 죽면 파괴가 시작 안 됨). outcome 은 실패 시 best-effort failed 행(544-556, 실패 기록 실패가 실제 실패를 덮지 않음)·성공 후 outcome 실패는 삼킴(558-562 — 완료된 파괴를 503 로 재시도시키지 않음). 프로젝트 purge 선례(admin.py:124-196)와 같은 모양.
- **감아 서**: `AdminAuditEvent.action` Literal 에 `account_reconcile` 추가(admin_audit.py:29). `record_account_reconcile_requested`(136-160)는 `target_type="user"`·`target_project_id=None`·사유 strip. `record_purge_outcome` 이 `target_user_id=requested.target_user_id` 를 상속(130) — `record_purge_requested`(91-109)는 target_user_id 를 아예 안 넘기므로 프로젝트 purge 이벤트의 값은 **코드 독해상** None 무변(셀은 없음 → C3). `list_destructive_events` 는 in-memory(69-76)·Mongo(52-62, `$in`) 모두 `project_purge`+`account_reconcile` 만 — member_quota 배제는 코드로 성립하나 셀이 없음(→ C2).
- **읽기 표면**: `AdminUserPayload` 에 스탬프 둘(`models.py:240-244` — `datetime | None`, 파생값 `purge_due_at` 없음 ✓). `AdminAuditEventPayload.target_project_id` 가 `str | None`(`models.py:496`)로 — 계정 축 이벤트(None)가 처음 실리는 자리라는 SoT 설명과 일치. `_ERRORS_ADMIN_400_404_409` 신규(`errors.py:294-299`) — 선언 지도 GET{401,403,404,409,503}·POST{+400} 와 정확히 대응(가드 통과).
- **등재 전부 실측 초록**: tier 105→107·admin 17→19(집합 원소 등재로 핀) · 선언 지도 17→19(21626b8 — 1차 전수 실패의 원인을 닫은 커밋) · `activity/actions.py` EXCLUDED 31→32·절 주석 11→12, 등재는 **POST 만**(237-243 — 조사 GET 은 mutating 이 아니라는 SoT 문언 그대로, 사유 코드 `admin_audited`) · `schema.d.ts` 재생성 무차분(gen:api 실측) · `navigationLinks.test.ts` 집합에 상세 추가.
- **프런트**: 정리 섹션은 `user.purge_started_at !== null` 일 때만(`AdminUserDetail.tsx:174`) — stalled 정의와 일치. 순서는 조사(185-194) → 조사 결과(195-216) → 사유+사용자명 입력 확인(217-227, disabled 조건에 `confirmation !== user.username`) → 실행 → 정리 결과(237-257) — SoT "조사 → 결과 → 사유+사용자명 입력 확인 → 실행 → 결과" 그대로. 사용자명 확인은 프로젝트 파기 UI(`AdminProjectCard.tsx:170-175`)의 계정축 이행 — 같은 게이트 산술. `removed_user_row` 참이면 "사용자 목록으로" 링크(255-257) — 브리프 후속 고려가 처방을 구현 재량으로 남긴 자리. 목록 라벨 `adminWithdrawalLabel`(`userStatus.ts:23-30`)은 파기 스탬프 우선·없으면 빈 문자열 — 기존 승인 라벨 순서 무변, "옆에" 표시(`AdminConsole.tsx:219-221`). **b3e5ec0 에 .css 변경 없음** — "새 CSS 규칙 없이" 성립.
- **셀 수 주장 대조**: 신규 13셀(파일 실측 — 대상 4+조사 1+실행 4+감사 3+읽기 1), ReconcilerTest 4셀 이관(가리키기만 새 모듈), payload 핀 갱신 2곳, 프런트 +5(상세 4·목록 1) — 구현 세션 기록과 전부 일치.
- **계약 내부 정합성**: 브리프 갈래 ③ⓐ 문언("action 신규(예: account_reconcile), target_type=\"user\"")·SoT v1.8.62(`record_account_reconcile_requested` 신규 + `record_purge_outcome` 상속)·구현 셋이 일치. 브리프 셀 나열의 "실행 후 notice" 는 구현이 제자리 "정리 결과" 절로 응답하는데, SoT 가 같은 슬라이스에서 "실행 → 결과"로 서술하고 있어 모순 아님(비차단 관찰).

### 뮤테이션 결과

| 변이 | diff(적용 그대로) | 결과 |
|---|---|---|
| **M1** 묘비 검사 제거 | `account_reconcile.py:89` `if not projects and has_tombstone:` → `if not projects:` | **2셀 재실패** — `test_execute_keeps_the_row_without_a_tombstone` + `ReconcilerTest::test_a_missing_tombstone_also_holds_the_user_row_back` |
| **M2** 프로젝트 검사 제거 | 같은 줄 → `if has_tombstone:` | **2셀 재실패** — `test_execute_keeps_the_row_while_projects_remain` + `ReconcilerTest::test_leftover_projects_hold_the_user_row_back` |
| **M3** POST 스탬프 재확인 제거 | `admin.py` POST 핸들러(535행)에서 `_stalled_user_or_error(user_id)` 한 줄 삭제(GET 쪽 유지) | **0셀** — `test_admin_account_reconcile`(13)+`test_account_withdrawal_worker`+`test_auth_api`(153)+선언 지도 전부 초록(184 passed/1322 subtests) → **C1** |
| **M4** 감아 요청 행 적재 제거 | `admin_audit.py` `record_account_reconcile_requested` 본문에서 `self._repo.insert(event)` 삭제 | **2셀 재실패** — `test_execute_is_audited_in_two_stages_with_the_target_user`(len==2) + `test_a_failed_execution_records_the_failed_outcome`(outcomes==[requested, failed]) |
| **M5** outcome 상속 제거 | `admin_audit.py:130` `target_user_id=requested.target_user_id,` 한 줄 삭제 | **1셀 재실패** — 2단계 셀(`succeeded.target_user_id == bob.id`) |
| **M5b** 상속 과교정 | 같은 줄 → `target_user_id=requested.target_project_id,` | **계정 셀 1만 재실패** — 프로젝트 purge 이벤트의 축 오염(target_user_id 에 project id 주입)은 `test_auth_api` 165통과 전건 초록으로 무셀 → **C3** |
| **M6** member_quota 누수 | `admin_audit.py:75` 필터 → `if event.action in ("project_purge", "account_reconcile", "member_quota_policy")` | **0셀** — `test_admin_account_reconcile`+`test_auth_api`+`test_admin_audit` 전부 초록(171 passed/1225 subtests) → **C2** |
| **M8** 사용자명 확인 비교 제거 | `AdminUserDetail.tsx` 실행 버튼 disabled 조건에서 `\|\| reconcile.confirmation !== user.username` 삭제 | **1셀 재실패** — `surveys first, then executes only on the exact username` |
| **M9** stalled 게이트 제거 | `AdminUserDetail.tsx:174` `{user.purge_started_at !== null && (` → `{(true \|\| user.purge_started_at !== null) && (` | **1셀 재실패** — `keeps the reconcile section off accounts without a purge stamp` |
| **M10** 라우터가 본체 우회 | `admin.py` GET 이 `account_reconcile.survey(user_id)` 호출 대신 `{"leftover_projects": [], "has_username_tombstone": False}` 반환 | **1셀 재실패** — `test_survey_reports_leftovers_and_tombstone_without_destroying` |

매 변이 후 `git checkout -- <파일>` 원복 + `git status --short` 빈 확인. 원복 후 최종 실측: 백엔드 초점 6파일 **199 passed, 1419 subtests** · 프런트 초점 3파일 **20 passed** — 트리 clean.

## Issues / Risks

### Blocking (차단 — 계약 요구 분기 무셀; 판정 조건)

- **C1 — POST 측 대상 계약(404·409 재확인)이 무셀이다.** SoT v1.8.62: "**조사·실행 양쪽이** 호출 직전에 스탬프를 재확인한다(dry-run 사이에 데몬 청구가 끼어들면 409 로 걸린다)". M3 이 실증: POST 핸들러에서 재확인 한 줄을 지워도 초점 전부(184 passed/1322 subtests) 초록 — 모든 POST 셀이 stalled 계정(bob)만 향한다. 경합 조항(브리프 후속 고려 "purge_started_at 재확인이 응답 계약에 들어간다")의 실행 측 절반이 잠기지 않았다. **처방**: `test_admin_account_reconcile.py` 에 POST 셀 둘 — 없는 사용자 POST→404, 파기 미시작(예: 유예만) 계정 POST→409 + 감사 행 없음 단정.
- **C2 — member_quota_policy 의 화면 배제가 무셀이다.** SoT v1.8.62: "회원 정책(member_quota_policy)은 파괴가 아니라 **계속 이 화면 밖**이다". M6 이 실증: 파괴 축 필터에 member_quota 를 넣어도 171 passed/1225 subtests 초록 — 기존 purge 감사 셀(`test_auth_api.py:1625-1640`)은 repo 에 member_quota 이벤트가 없는 상태에서 화면을 읽고, member_quota 감사 셀(`test_auth_api.py:1941-1967`)은 화면을 안 읽는다. **처방**: quota 변경(예: `POST /admin/quota-policies/{id}/limits`)을 남긴 뒤 `GET /admin/audit-events` 에 `member_quota_policy` 행이 없는지 단정하는 셀.
- **C3 — `record_purge_outcome` 상속의 과교정 방향(프로젝트 purge 축 오염)이 무셀이다.** SoT v1.8.62: "record_purge_outcome 이 요청 행의 target_user_id 를 상속하게 함(**프로젝트 purge 는 None 이라 무변**)" — 이 슬라이스가 **공유 함수를 고친** 만큼 무변은 회귀 가드의 대상이다(8.5-b D3=ⓑ 축 무결 — `admin_audit.py:24-26` "한 필드를 겹쳐 쓰면 필드명이 거짓말을 한다"). M5b 실증: 상속값을 `target_project_id` 로 바꾸면 계정 셀만 실패하고 프로젝트 purge 이벤트가 대상 축을 거짓말해도 아무 셀이 안 물음(payload 가 target_user_id 를 안 실어 와이어로도 안 보임 — 원장이 조용히 오염). **처방**: 기존 프로젝트 purge 감사 셀(`test_success_records_requested_and_succeeded_tombstones`)에 요청·결과 행의 `target_user_id is None` 단정 한 줄씩.

### Hardening recommendations (비차단)

- **H1 — 503 "not configured" 분기는 공개 조립으로 도달 불가.** `admin.py:494-497`(`account_reconcile is None` → 503)는 `create_app` 이 항상 `_default_account_reconcile_service()` 를 만들기 때문에(`main.py:2222-2226`) 공개 경로에서 죽은 분기다(quota 읽기 선례와 같은 모양 — 주석도 그렇게 말한다). 선언(503)은 지도에 잠겨 있으니 계약상 문제 없으나, 분기를 살릴지 걷을지는 처방 선택으로 남는다.
- **H2 — dry-run 스크립트가 계정당 survey 를 두 번 호출.** `scripts/account_purge_reconciler.py:71-74` — `survey(user_id)` 를 leftover·tombstone 각각 한 번씩 호출(계정당 질의 2배). 출력 무변(건너뛸 값 아님), 효율만.
- **H3 — 범위 밖 미용 변경 두 줄.** `b3e5ec0` 이 `AdminUserDetail.tsx:288`·`292` 의 알림 문구 곡은 인용부호(`“…”`)를 직은(`"…"`)으로 바꿨다 — 슬라이스 요청과 무관하고 `AdminConsole.tsx:286` 은 곡은 그대로라 **불일치를 만드는 변경**이다(CLAUDE.md §3 surgical changes 위반, 경미 — 셀은 부분문자열 매칭이라 무변). 되돌리거나 양쪽을 통일할 것.
- **H4 — `AdminAuditEventPayload` 가 `target_user_id` 를 안 실는다.** 감사 화면이 계정 이벤트의 대상 계정을 reason 문면으로만 식별한다(member_quota 선례와 대칭이라 우발은 아님 — 스펙 침묳). 감사 원장의 가독성 축으로 열어야 할지는 오너 판단.
- **H5 — 스크립트 `main()` 자체(인자·JSON 출력)는 여전히 무셀.** 이관 전에도 그랬고 이번에도 그렇다(출력 키 무변은 diff 대조로 확인). 슬라이스 전 상태와 동일하므로 비차단.
- **H6 — InMemory 조립에서 users 저장소와 reconcile 저장소가 갈라진다.** 구현 세션이 인지하고 셀 주석으로 남겼다(`test_admin_account_reconcile.py:159-161` — `deleted_rows` 관측으로 잠금). Mongo 배포는 둘이 같은 컬렉션을 봐 실제 불일치는 없다.

## Verdict

**조건부 합격** — C1(POST 측 404·409 재확인 셀)·C2(member_quota 화면 배제 셀)·C3(프로젝트 purge 감사 축 무변 셀)를 추가로 닫을 것.

이유: 구현 자체는 스코프 계약 전 축에서 성립한다 — 본체 한 벌(질의·조건·출력 키 무변 이관)·라우터 대상 계약·감사 2단계·읽기 표면(세 번째 축)·등재 전부·프런트 ②ⓐ 흐름이 모두 코드·셀·실측으로 확인됐고 뮤테이션 10종 중 7종이 기명 셀을 정확히 물었다. 그러나 계약이 요구하는 분기 셋(M3·M5b·M6 으로 실증된 무셀)이 남아 있어 — 경계 행렬에 빈 칸이 있는 채로 합격을 줄 수 없다(guide: "An untraced contract-required branch is a blocking finding regardless of the green bar").

## Outstanding items

- **조건 폐쇄(셀 셋 추가)는 구현 세션의 몫** — 검증자가 닫으면 독립성이 사라진다(이 저장소의 확립 절차). 셋 다 기존 셀에 단정 몇 줄을 더하는 수준이다.
- 폐쇄 후 이 기록의 판정 승격(합격)은 다음 독립 검증 또는 승격 재검 몫.
- 스크립트 dry-run 스모크는 이 검증 환경에서 Mongo 접속 불가로 미실행(방법론 7의 대체 확인으로 충당) — 배포 환경에서 한 번 돌려볼 것(브리프 "스크립트 경로 유지" 검증).
- 전수 회귀(백엔드 3053/1/4213 · 프런트 488/41)는 구현 세션 기록값을 대조값으로만 사용 — 이 검증은 지시에 따라 초점만 실측했다.

## Reproduction

```bash
git status --short          # 빈 출력이어야 한다
# 초점 실측
python3 -m pytest tests/test_admin_account_reconcile.py tests/test_account_withdrawal_worker.py -q
python3 -m pytest tests/test_auth_api.py -q
python3 -m pytest tests/test_application_api.py::AdminErrorContractDeclarationTest tests/test_activity_actions.py tests/test_admin_audit.py -q
cd frontend && npm run gen:api && git status --short   # 무차분
npx vitest run src/admin/AdminUserDetail.test.tsx src/admin/AdminConsole.test.tsx src/navigationLinks.test.ts
# 뮤테이션(표의 각 변이): git status --short 확인 → 변이 → 위 초점 재실행 → git checkout -- <파일> → git status --short
# C1 재현: admin.py POST 핸들러에서 _stalled_user_or_error(user_id) 삭제 → 전부 초록(0실패)
# C2 재현: admin_audit.py list_destructive_events 필터에 "member_quota_policy" 추가 → 전부 초록
# C3 재현: admin_audit.py:130 을 target_user_id=requested.target_project_id 로 → test_auth_api 만으로는 초록
```

---

## 폐쇄 보고 (구현 세션, 2026-09-12 · 커밋 `a460237`)

조건 셋을 닫았다 — **판정 승격은 하지 않는다**(조건을 닫은 세션이 자기 판정을 올리면 독립성이 사라진다 — v1.8.52·v1.8.55 선례. 승격은 다음 독립 검증/승격 재검 몫).

- **C1 — 실행 측 재확인 무셀 폐쇄**: 셀 둘(`test_admin_account_reconcile.py::…test_execute_for_a_missing_user_is_404` · `…test_execute_for_an_unclaimed_account_is_409_and_unaudited`). 후자는 **감사 행이 남지 않음**(대상 검증 뒤에 감사가 온다는 순서)까지 잠근다. **변이 M3 재적용 → 2셀 기명 재실패** 확인.
- **C2 — member_quota 화면 배제 무셀 폐쇄**: 셀 하나(`…test_the_audit_surface_excludes_member_quota_events` — 회원 정책 행을 심은 뒤 `/admin/audit-events` 에 `account_reconcile` 은 보이고 `member_quota_policy` 는 안 보이는지). **변이 M6 재적용(InMemory 필터) → 1셀 기명 재실패** 확인.
- **C3 — `record_purge_outcome` 상속의 과교정 방향 폐쇄**: 기존 프로젝트 purge 감사 셀(`test_auth_api.py::AdminProjectPurgeTest::test_success_records_requested_and_succeeded_tombstones`)에 **저장소에서 직접** 요청·결과 행의 `target_user_id is None` 단정 추가(wire payload 는 이 필드를 안 실어 워이어로는 잴 수 없다 — 하드닝 H4 와 같은 근원). **변이 M5b 재적용 → 1셀 기명 재실패** 확인.
- **하드닝 H3(범위 밖 인용부호 변경)도 원복**했다 — `AdminUserDetail.tsx` 의 알림 문구 두 곳을 곡은 인용부호로 되돌림(구현 세션이 `b3e5ec0` 에서 직은으로 바꿨던 것).
- 초점 재실측(원복 뒤): `test_admin_account_reconcile`+`test_auth_api`+`test_admin_audit`+`test_owner_project_purge` **181 passed / 1225 subtests**. 전수 재실측은 하지 않았다 — **백엔드 서비스 소스 무변**(순수 테스트 추가)이므로 유도가 정당: 백엔드 3053→**3056 passed**(subtest 무변 4213). 프런트는 문구 원복 두 곳(셀 수 무변 — 488/41 그대로).
