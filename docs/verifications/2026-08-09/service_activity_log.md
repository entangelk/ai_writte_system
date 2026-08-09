# Phase 9 Slice 9.0 — 서비스 활동 로그(A1~A8) 독립 검증

- **날짜**: 2026-08-09
- **요청자**: 오너("다음 작업 검증해줘. Phase 9 Slice 9.0")
- **검증자**: Claude Code 세션(구현자와 다름 — 구현 커밋 `65507d9`·문서 `c5b5af4`·브리프 확정 `9dae6b9`를 건드리지 않은 채 HEAD `c5b5af4`에서 감사)
- **대상 슬라이스**: 서비스 활동 로그 — 정본 변경 10 + 검토 결정 9 = 19 경로가 `activity_events` 에 한 행씩 남기고, 소유자가 `GET /projects/{id}/activity`(operation 77)로 읽는다.
- **정규 스펙**: [`docs/system-contract-sot.md`](../../system-contract-sot.md) **v1.7.92** 변경이력(Phase 9 Slice 9.0) · [`docs/plans/09-0-service-activity-log-decisions.md`](../../plans/09-0-service-activity-log-decisions.md) A1~A8 + "A2 확정 조건" · [`docs/mongo_collections.md`](../../mongo_collections.md) §43G.
- **오너 결정 근거**: A1~A8(2026-08-09), 특히 A2=B(19) + C 확장 조건 3, A4=A(격리), A7=A(endpoint+전수 가드), A8=A(중복 없음).
- **검증 원천**: 커밋 `c5b5af4`(HEAD, working tree clean).

## Scope

boundary matrix 의 정본은 브리프 A1~A8 + A2 확장조건 3 + 부모계획 §4 I1~I5 다.

1. **★ 분류표 40 전수** — mutating 40 이 `logged`(19) / `excluded(21, 사유)` 로 빈틈없이 분류되고 미등재 route 가 가드를 실패시키는가(A7). 구현자 숫자를 믿지 않고 `app.routes` 를 직접 뽑아 대조.
2. **★ N5 — I1 방향(8.2c 와 정반대)** — `activity_events` 문서가 `project_id` 필드를 써서 파기 reconciler 가 **발견**하는가. `project_name_history`(8.2c) 가 `_id` 로 발견을 **피하는** 것과 정반대인가.
3. **19 배선** — logged 19 가 실제로 `activity.record(` 를 부르고, excluded 21 은 부르지 않는가(A8). 결과 **뒤에** 쓰는가(A7 — 409 셀이 순서를 잠근다).
4. **A4 격리** — 기록 실패가 요청을 죽이지 않고, 파기 경로는 격리하지 않는가.
5. **operation 77 + tier** — `GET /projects/{id}/activity` 가 project tier(소유권)에 있고 tier 전수 가드가 77/62 를 단정하는가.
6. **회귀 + openapi/프론트** — operation 76→77, `schema.d.ts` +118.
7. **★ accept 오너 확인 사안** — `writing/accept` 가 정본 저장인데 excluded 인 것이 blocking 인가.

## Methodology

트리 clean 이므로 뮤테이션 원복은 `git checkout -- <path>` 안전 분기 + 매 회 바이트 복원 확인. subtest 실패는 `SUBFAILED` 접두사로 나오므로 `FAILED|SUBFAILED` 둘 다 잡는 추출을 썼다(2026-08-09 검증이 올린 그 함정).

```bash
# 40 전수 — app.routes 의 mutating 을 직접 추출해 CLASSIFIED_OPERATIONS(40) 와 대조
PYTHONPATH=$PWD python3 -c "from services.application.app.main import create_app; ..."

# N5 — log_mongo.py 의 '\"project_id\"'(문자열 리터럴, 5출현) → '\"target_project_id\"'
#   초점 = test_activity_log + test_activity_api + test_purge_reconciler(실 Mongo)

# N1/N3/N4/N6/N7/N8 — 각 변이 치환 → pytest 초점 → git checkout -- → status+byte
# N2 — rename handler 의 record 블록을 rename_project 호출 직전으로 이동

# 회귀 — test-mongo ON(docker-compose.test.yml up -d, healthy 대기) 후 python3 -m pytest -q
```

## Findings

### 1. 분류표 40 전수 — 완벽 대응, 미등재·stale 0

직접 추출: app mutating operation **40** = CLASSIFIED_OPERATIONS **40**. `set(routes) - CLASSIFIED` = **0**(미등재 없음), `CLASSIFIED - set(routes)` = **0**(오타/삭제 경로 없음). LOGGED **19**(정본 10 `_CANONICAL` + 검토 9 `_REVIEW`) · EXCLUDED **21**(AI 요청 14 `ai_request` + 파생 1 + 인증 2 + 관리자 4). 구현자·브리프·SoT v1.7.92 숫자와 한 치 없이 일치. `test_every_ai_request_is_excluded_with_that_reason` 이 AI 요청 14 가 `ai_request` 사유로 **모여** 있고 각 note 를 달았음을 단정(C 확장 = 행 값 변경이 되는 구조).

### 2. ★ N5 — I1 방향 가드, 8.2c 와 정반대 (이 슬라이스의 핵심 증거)

`activity/log_mongo.py::_doc` 은 `"project_id"` 필드로 문서를 만들고, `log.py::ActivityEvent` docstring 이 명시한다 — *"project_id 는 반두시 이 이름이어야 한다… target_project_id 로 바꾸면 파기가 이 로그를 못 지운다 — 8.2c project_name_history 와 정확히 반대 방향"*.

**★ N5 뮤테이션 재현** — `"project_id"` 문자열 리터럴 5출현을 `"target_project_id"` 로 바꿨더니 **정확히 7셀 재실패**(구현자 보고와 동일):
- 어댑터 5: `test_a_naive_datetime_from_the_driver_comes_back_aware` · `test_purge_deletes_by_project` · **`test_the_document_carries_project_id_so_the_reconciler_finds_it`**(이름 자체가 계약) · `test_the_document_key_set_is_fixed` · `test_the_round_trip_preserves_every_field`
- 실 Mongo 조립 1: `test_the_default_factory_persists_to_mongo_and_reads_back_aware`
- **reconciler: `test_the_activity_log_is_swept`**(발견 못 함 → I1 위반)

그리고 `test_purge_reconciler.py` 의 두 셀이 **나란히** 정반대를 잠근다 — `test_the_project_name_history_is_not_swept`(8.2c, 발견되면 **안 됨**) · `test_the_activity_log_is_swept`(9.0, **반드시 발견**). 둘 다 "손으로 넣지 않고 어댑터로 쓴다"로 어댑터 변경까지 잡는다. 다음 사람이 8.2c 의 `_id` 트릭을 activity_events 에 복사하면 즉시 드러난다.

### 3. 19 배선 + 결과 뒤 기록 (A7) — 양방향 가드 확인

logged 19 **전부** `activity.record(` 를 부르고(배선 누락 0), excluded 21 은 **0건**(A8 복제 없음). `test_every_logged_route_actually_records`(under) · `test_no_excluded_route_records`(over, A8) · `test_the_recorded_action_literal_matches_the_table`(리터럴 일치) 가 `inspect.getsource(route.endpoint)` 로 잰다.

**404 vs 409 셀의 역할 분담** (구현자가 N2 로 드러낸 것, 독립 확인): `test_a_conflicting_request_leaves_no_trace`(409, archive 된 프로젝트 개명)가 **순서를 실제로 잠근다**. 404 는 `require_project_owner` dependency 가 route 실행 **전**에 내므로 handler 가 안 돌아 — 404 셀은 "기록을 dependency 로 옮기면" 잡히는 반대 방향이다. 두 셀을 함께 읽어야 A7 이 덮인다(구현자가 셀 문서를 이 실측에 맞게 고쳤다).

### 4. A4 격리 — fail-open 은 `record` 에만, 파기는 격리 X

`log.py::ActivityLogService.record` 가 `try/except Exception`(noqa BLE001)로 insert 실패를 삼키고 warning 로그로 흘린다. `purge_project` 는 **격리하지 않는다**(docstring: 삼키면 지워지지 않은 로그가 남은 채 파기 성공 = D5 부분 삭제). N3 뮤테이션(try/except 제거 → fail-closed)이 `test_a_broken_activity_store_does_not_break_the_request`·`test_a_write_failure_does_not_reach_the_caller` 2셀을 물어 양방향을 잠근다. 격리 경계를 서비스 안(19 호출부가 아니라) 둔 것은 올바르다 — 각자 try/except 면 한 곳이 빠져도 저장소가 죽기 전까지 안 보인다.

### 5. operation 77 + tier + openapi

`GET /projects/{project_id}/activity`(GET, responses 401/403/404/503, project tier). 총 operation **76→77**, `test_auth_api` 가 `by_tier["project"]==62` · `len(tiers)==77` 을 단정(public 4 · auth 3 · admin 8 · project 62). `schema.d.ts` 에 path·`ActivityEventPayload`·`ActivityLogResponse`·`get_project_activity` 가 additive(+118줄, tsc clean). 프론트 화면 0줄(A5=B 는 API 까지).

### 6. 회귀 — 구현자 기준선 재현

`2244 passed / 4 skipped / 2322 subtests in 177s`(test-mongo ON). skip 4 = live Chroma 1 + ES 패키지 부재 3 → 보정 **2247 / 1 / 2322**. 직전 `2211/1/2247` 대비 cell +36 · subtest +75, 전부 신규 가드.

### 7. ★ accept 오너 확인 사안 — blocking 아님

`POST …/writing/accept` 는 **정본 draft version 을 실제로 저장**한다(독립 확인: `writing/accept.py:127` `core_sot.start_next_unit(…)` → `:138` `SaveDraftResult(result.draft_version, result.snapshot, …)`). 브리프 §0.2 는 성격으로 "AI·작업 요청 14" 에 넣었으나 A2 의 기준("무엇을 바꿨는가")으로 보면 정본 변경이다.

구현자는 **오너가 승인한 B=19 를 지키고**, 자의로 20 으로 넓히지 않고, `actions.py` 의 그 행에 어긋남과 근거를 주석으로 달아 `excluded(ai_request, "오너 확인 대기")` 로 두었다. 이것은 **blocking 이 아니다**:
- 브리프가 열어둔 자리(A2=C 확장 조건)를 작업자가 결정 기록을 훼손하지 않게 존중했다.
- 넓히는 것은 A2 확장조건 그대로 **행 하나의 값을 바꾸는 일**이고, A8 은 그 결정과 함께 다시 본다(브리프가 못박은 조건 3).
- 알려진 제약("accept 가 주 저작 흐름의 저장 경로인데 타임라인에 절반만 답해진다")을 투명하게 work_log·주석·SoT 변경이력에 기록했다.

accept 를 `logged` 로 넓힐지는 오너 결정이고, 검증 합격을 막지 않는다.

## Issues / Risks

### Blocking (계약 의무 위반)

**없음.** A1~A8 · A2 확장조건 3 · I1~I2 가 전부 충족됐고, boundary matrix 의 모든 셀이 채워져 있으며, 뮤테이션 8종이 실제로 문다.

### Hardening (비차단)

- **N2 뮤테이션의 셀 수가 구현자 보고(2)와 하나 다르다(1).** 구현자는 "handler 맨 앞으로"라 했고 검증자는 "rename_project try 직전 이동"으로 시위했다. **핵심 셀**(`test_a_conflicting_request_leaves_no_trace` = 409 경로 순서 잠금)은 양쪽 모두에서 재현됐고, 그것이 A7 의 계약(결과 뒤에 쓴다)을 잠근다. 구현자 보고의 두 번째 셀(`test_the_owner_reads_newest_first`)은 변이 디테일 차이로 검증자 변이에서는 안 물렸다 — 매트릭스가 아니라 변이 구현의 미묘한 차이이며, 핵심 계약 검증에는 영향 없다.
- **accept 분류가 빠져 있는 것** — 위 §7. 알려진 제약이지 결함이 아니다. 오너가 넓히면 행 하나.

## Verdict

**합격** — Phase 9 Slice 9.0 의 A1~A8 + A2 확장조건 3 + I1(8.2c 와 정반대 파기 방향)이 전부 충족됐다. 분류표 40 전수(미등재·stale 0) 독립 재현, ★ N5 로 I1 방향 가드가 `target_project_id` 변이에 7셀이 물며 8.2c 이름 이력과 정반대를 나란히 잠그는 것을 입증, 19 배선·A4 격리·A7 결과-뒤-기록(409 셀)의 양방향 가드 확인, 회귀 2244/4/2322(보정 2247/1) 재현. Blocking 0. `writing/accept` 는 정본 저장이지만 오너가 승인한 B=19 를 존중해 excluded+주석으로 남겨뒀고, 넓히는 것은 오너 결정으로 행 하나(A8 와 함께)다.

## Outstanding items

- **★ 오너 결정 대기 — `writing/accept` 분류.** 정본 draft version 저장(`start_next_unit`→`SaveDraftResult`)이므로 A2 기준으로는 `logged` 후보다. 넓히면 19→20, action 리터럴은 `draft_version_accepted` 계열이 자연스럽다. **A8 을 함께 다시 본다**(브리프 A2 확장조건 3) — accept 가 정본 저장이라 `llm_call_audits`·원장과 같은 사건이 아닐 수 있어 중복 논의가 다르다.
- 본 검증 기록 추가로 `docs/verifications/` 건수 228→229(같은 날, 일수 46 유지). 인덱스·README 카운트·판정분포(합격 160→161) 동반 갱신했고 `VerificationCountClaimsTest`·`VerificationsIndexTest` 로 확인.

## Reproduction

```bash
git status --short   # clean 전제
# 40 전수·배선·A8·tier(1,3,5 절) — Mongo 무관
PYTHONPATH=$PWD python3 -c "import inspect; from fastapi.routing import APIRoute; from services.application.app.main import create_app; from services.application.app.activity.actions import CLASSIFIED_OPERATIONS,LOGGED_OPERATIONS,EXCLUDED_BY_OPERATION; ..."   # mutating 40 == CLASSIFIED 40, 미등재/stale 0, logged 19 배선
python3 -m pytest tests/test_activity_actions.py tests/test_activity_log.py tests/test_activity_api.py -q   # baseline
# N1~N8 변이 → pytest 초점 → git checkout -- → status+byte (FAILED|SUBFAILED 추출)
# N5(★) — log_mongo.py '"project_id"'→'"target_project_id"' (5출현) → test_purge_reconciler 포함 초점 → 7 failed
# 회귀 — Mongo 필요
docker compose -f docker-compose.test.yml up -d && until […healthy]; do sleep 2; done && python3 -m pytest -q   # 2244/4/2322
```
