# 독립 검증 — Phase 8 Slice 8.3 quota 시행 (입장·성공차감·정산 조립)

- **날짜**: 2026-08-04
- **요청자**: 오너("작업 AI가 작업한 거 검증하고 의심하고 또 의심해줄래?")
- **검증자**: Claude(본 세션, 구현에 관여하지 않음). 깊은 독립 감사는 구현에 관여하지 않은
  서브에이전트 넷에게 맡기고(enforcement core / main.py 배선 / 테스트 품질 / 전체 실측+뮤테이션),
  본 세션은 결정 정본 대 코드 교차 읽기·뮤테이션 원복 무결성·최종 의심을 직접 담당했다.
- **대상**: Slice 8.3 — 커밋 `9a6a500`(시행 배선) → `5ddce4e`(회귀) → `ba3d153`(Q1-a 단위 셀) →
  `f09af95`(SoT v1.7.88·계약 정본화) → `98fee5c`(회귀 기준선 정정). **검증 시점 HEAD `98fee5c`**,
  작업 트리 clean.
- **정본 계약**: [`docs/plans/08-3-quota-enforcement-decisions.md`](../../plans/08-3-quota-enforcement-decisions.md)
  (Q1=C · Q1-a=A · Q1-b=A · Q3=E · Q3-a=A · Q4=A · Q5=B · Q6=C · Q7=A · Q8=C · Q9=A, Resolved 12건) +
  [`docs/system-contract-sot.md`](../../system-contract-sot.md) **v1.7.88** + [`docs/mongo_collections.md`](../../mongo_collections.md) §43E.
- **머신**: 베타, 전용 test-mongo(rs-test, `127.0.0.1:27020`)를 검증 중에만 기동·healthy 대기 후 회수.

## Scope

작업자가 스스로 밝힌 의심 지점 셋(정산 wrapper 이동 · Q8=C 상태 가드 정밀화 · `auth_support` 입장
우회 확장)이 핵심 축이다. 이것들을 반증 대상으로 잡았다.

1. **정산 wrapper(Q7=A 정밀화)** — `QuotaSettledRoute`가 **모든 종료 경로**(2xx · partial envelope
   4xx/5xx · 핸들러 예외 · async 202)에서 잠금을 푸는가. wrapper가 202를 과금하지 않는가.
   `_is_charged`가 Q1-a=A(`2xx` **그리고** provider 호출)를 정확히 구현하는가.
2. **입장(Q3-a=A)** — 회원 단위 입장 뮤텍스의 임계 구역에 **provider 호출이 없는가**(들어가면 이
   설계의 장점이 전부 사라진다). lease≈5s · 획득 실패 503(fail-closed) · 해제 `finally`.
3. **정산 순서(Q3=E)** — 원장 삽입이 잠금 해제보다 **먼저**인가(뒤집히면 초과가 샌다).
4. **Q1-b=A** — 비동기 202는 워커가 생성 성공 시 차감하는가. `dedupe_key=request_id` · job `user_id`
   비정규화 · `(user_id, status)` 인덱스 · 진행 중 job이 한도 계수에 들어가는가.
5. **Q8=C** — 상태 가드가 **새 job은 막되 같은 `request_id`의 멱등 replay는 통과**시키는가.
6. **Q9=A** — 경로별 dedupe 매핑표. 미분류 동작은 fail-closed인가.
7. **배선·가드** — `enforce_quota`가 소유권 **뒤**에 선언됐는가. 9경로가 `responses=`(429/402/403)·
   `X-Confirm-Duplicate` 헤더·`QuotaSettledRoute`를 모두 갖추었는가(전수 가드).
8. **`auth_support` 우회** — 입장(뮤텍스·한도·잠금)만 우회하고 **정산은 살아** 있는가(결함 은폐
   여부). 시행을 진짜로 재는 셀은 우회 없이 잡는가.
9. **실측** — 전체 회귀(2145/1/1921)와 뮤테이션 재실패가 구현자 주장과 일치하는가.

## Methodology

계약 범위를 Q1~Q9 + Q1-a/Q1-b/Q3-a로 한정해 경계 매트릭스를 세운 뒤, 구현자의 보고를 반증 대상
가설로 취급했다. 코드는 읽기 전용(감사), 뮤테이션은 커밋하지 않고 역방향 Edit로만 원복(`git checkout --` 금지 규칙 준수).

- **독자 코드 추적(본 세션)**: [`enforcement.py`](../../../services/application/app/quota/enforcement.md)
  전수 · [`main.py:1656-1837`](../../../services/application/app/main.py#L1656)(`enforce_quota`·`QuotaSettledRoute`·
  `_is_charged`·`_REQUIRE_PROJECT_OWNER_BILLABLE`) · [`llm_call_scope.py`](../../../services/application/app/observability/llm_call_scope.md)
  (`ProviderCallTally`·`provider_call_tally`) · [`dedupe.py`](../../../services/application/app/quota/dedupe.md) ·
  [`lock.py`](../../../services/application/app/quota/lock.py) · [`auth_support.py`](../../../tests/auth_support.md) · 라우트 배선·가드.
- **서브에이전트 넷**: enforcement core · main.py 배선(worker·job 포함) · 테스트 품질 · **전체 회귀 및
  뮤테이션 재실험**(test-mongo 기동 후 healthy 대기).
- **뮤테이션(under-strict, 서브4가 실측)**: (a) `_is_charged`의 `provider_calls > 0` 제거 → 행렬 셀
  재실패 확인 → 역방향 Edit 원복. (b) `admit`의 `with self._mutex.hold(...)`를 `nullcontext()`로
  무력화 → 실 Mongo 20-way 셀 5회 반복 → 원복. 매번 `git diff --stat` 공백 단정.
- **실측(서브4)**: `docker compose -f docker-compose.test.yml up -d` → healthy 대기 → `python3 -m pytest`.

## Findings

### F1. 정산 wrapper — 네 종료 경로 모두 잠금을 푼다 (PASS)

[`main.py:1769-1791`](../../../services/application/app/main.py#L1769)의 `QuotaSettledRoute.settled`는
`status_code: int | None = None`에서 시작해 `try: response = await original(request); status_code =
response.status_code` 뒤 `finally`에서 `settle(charge, charged=_is_charged(...))`를 부른다.

| 종료 경로 | status_code | `_is_charged` | settle | 잠금 해제 |
|---|---|---|---|---|
| 2xx + provider 호출 | 2xx | True | 원장 삽입 + 해제 | O |
| partial envelope 4xx/5xx | 400/502/503 | False | 해제만 | O |
| 핸들러 예외 | None | False(None 가드) | 해제만 | O |
| async 202 | 202 | False(202 가드) | 해제만(워커가 차감) | O |

`settle`([`enforcement.py:328-350`](../../../services/application/app/quota/enforcement.py#L328))은
`try: if charged: self._record(...) / finally: self._locks.release(...)`라 record가 예외를 삼켜도
release는 항상 실행. **잠금 영구 누락 경로 없음.**

### F2. 정산 wrapper 이동은 합법적이다 (작업자 정밀화 #1 — PASS)

Q7=A 문언은 "차감은 `yield` 뒤"였으나, 이 앱의 partial envelope 6곳·async 202는 예외(`raise`)가
아니라 `JSONResponse`를 **반환**하므로 FastAPI yield dependency의 exit에 상태코드 신호가 오지 않는다.
그 자리에서 정산하면 "일하고도 실패한 응답"과 "접수만 한 202"가 과금된다(Q1-a·Q1-b 동시 위반).
**입장은 dependency에, 정산은 응답을 실제로 보는 route wrapper에** 둔 것은 결정 위반이 아니라 결정을
지키기 위한 배치다. wrapper는 정책을 정하지 않는다 — dependency가 남긴 영수증(`request.state`)이
있을 때만 동작한다.

### F3. wrapper 누락 = 잠금 누수가 구조적으로 불가능하다 (PASS)

`app.router.route_class = QuotaSettledRoute`([`main.py:2657`](../../../services/application/app/main.py#L2657))로
**전역 적용**. 의존성은 있는데 wrapper가 없는 route(→ 잠금이 영원히 안 풀리는 시나리오)는 존재할 수
없다. [`test_quota_enforcement_api.py:552-557`](../../../tests/test_quota_enforcement_api.py#L552)
`test_every_route_is_built_by_the_settling_wrapper`가 모든 route의 타입을 `assertIsInstance(route,
QuotaSettledRoute)`로 단정. 비유료 경로는 charge가 None이라 settle이 건너뛴다(무해).

### F4. `_is_charged` = Q1-a=A 정확 (PASS)

[`main.py:1794-1799`](../../../services/application/app/main.py#L1794):

```
None/비2xx → False(예외·partial envelope 무과금) · 202 → False(워커 차감)
2xx & provider_calls>0 → True · 2xx & 0 호출 → False(replay 무과금)
```

`(2xx 여부) × (provider 호출 수)` 네 칸이 정확하고 partial envelope의 4xx/5xx는 무과금이 맞다.
[`test_quota_enforcement_api.py:335-350`](../../../tests/test_quota_enforcement_api.py#L335)
`ChargeRuleTest.test_the_matrix`가 8 케이스로 행렬을 단위 잠금한다.

### F5. `ProviderCallTally` — 요청 격리·실패 호출 카운트 (PASS)

[`llm_call_scope.py:154-194`](../../../services/application/app/observability/llm_call_scope.py#L154)는
`contextvars.ContextVar` 기반이라 동시 요청에 섞이지 않는다(모듈 docstring이 20-way 20/20 무누설
실측을 기록). `llm_call_scope`가 닫힐 때 `tally.add(len(scope.calls))`([`:216-218`](../../../services/application/app/observability/llm_call_scope.py#L216))를
더하며, `scope.calls`는 성공·`ProviderError` 모두를 기록하므로 "불렀다"가 정확히 잡힌다.
**관측 flush 실패(`_flush`의 `except Exception`)는 tally.add 뒤**라 과금 판정에 영향을 주지 않는다.
replay(200 무노동)는 provider를 안 불러 tally=0 → 무과금(Q1-a 핵심).

### F6. 입장 뮤텍스 임계 구역에 provider 호출이 없다 (Q3-a=A — PASS)

[`enforcement.py:233-269`](../../../services/application/app/quota/enforcement.py#L233) `admit`을 줄 단위로
읽었다. `with self._mutex.hold(user_id):` 안에는 `_refuse_if_exhausted`(count+판정)와 `_claim`(잠금
차지) **둘뿐**이고 provider/generate/llm 호출이 없다. 임계 구역은 Mongo 왕복 두어 번(수 ms)이다.
네 구현 계약 전부 확인: 키 `admission:{user}`(접두 분리, 진행 중 계수에 안 잡힘) ·
`ADMISSION_LEASE_SECONDS=5`([`:69`](../../../services/application/app/quota/enforcement.py#L69), 8.2b
180초와 다른 축) · `ADMISSION_ATTEMPTS=5` 후 `AdmissionUnavailable`→503([`:196`](../../../services/application/app/quota/enforcement.py#L196)) ·
`hold`의 `try/finally`([`:167-175`](../../../services/application/app/quota/enforcement.py#L167)).

### F7. 정산 순서 — 원장 삽입이 잠금 해제보다 먼저 (Q3=E — PASS)

`settle`([`enforcement.py:335-350`](../../../services/application/app/quota/enforcement.py#L335)):
`try: self._record(...) / finally: self._locks.release(...)`. 역순면 "행도 잠금도 없는 한 칸"으로
초과가 샌다. [`test_quota_enforcement.py`](../../../tests/test_quota_enforcement.py)
`test_the_usage_row_lands_before_the_lock_is_released`가 순서를 단정.

### F8. Q1-b=A — 워커 차감·user_id·인덱스·진행 중 계수 (PASS)

- `charge_completed_generation`([`enforcement.py:352-369`](../../../services/application/app/quota/enforcement.py#L352)):
  `action="writing_generate"`, `dedupe_key=request_id`(요청 경로와 같은 키 → 이중 과금 구조적 불가).
- `GenerationJobCharger.charge`([`:409-438`](../../../services/application/app/quota/enforcement.py#L409)):
  `job.user_id is None`이면 무과금, 회원 조회 실패해도 job을 실패시키지 않음(91초 GPU 재실행 방지),
  차감 예외 삼킴.
- worker의 모든 실패 경로가 차감 코드 도달 전 `fail()`을 반환, 성공만 charge
  ([`generation_worker.py`](../../../services/application/app/writing/generation_worker.md)).
- job `user_id` 비정규화 + `(user_id, status)` 인덱스 실제 선언
  ([`generation_job_mongo.py`](../../../services/application/app/writing/generation_job_mongo.md)).
- 진행 중 job이 한도 계수에 들어간다: `effective_usage`가 `jobs.count_active_for_user`를 더함
  ([`enforcement.py:283-284`](../../../services/application/app/quota/enforcement.py#L283)). **이 조회는 원장이
  아니라 공유 job 저장소를 직접 보므로** async가 입장을 우회하지 못한다.

### F9. Q8=C — 상태 가드가 멱등 replay는 통과시킨다 (작업자 정밀화 #2 — PASS)

`has_other_active_for_draft` = `job.status in _ACTIVE_STATUSES and job.request_id != request_id` —
"새 job은 막되 같은 `request_id`의 재전송은 통과"가 Q9=A(replay=같은 키→새 job·과금 없음)와 일치.
문언을 그대로 구현하면 폴링·재전송 클라이언트가 자기 job을 못 받으므로 `request_id`로 좁힌 것은
옳다. `AsyncInFlightGuardTest` 4셀이 양방향으로 잠근다.

### F10. Q9=A — 매핑표 + 미분류 fail-closed (PASS)

[`dedupe.py:42-52`](../../../services/application/app/quota/dedupe.py#L42) 9칸이 정본과 일치(writing 5경로=
`body.request_id` · `writing_accept`=`body.idempotency_key` · `analysis_extract`=경로 `job_id` ·
`analysis_compare`=서버 생성 · `context_search`=`body.idempotency_key`). 미분류 동작은
`resolve_dedupe_key`가 `KeyError`([`:64-65`](../../../services/application/app/quota/dedupe.py#L64))를 올려
조용히 통과하지 않는다. `test_the_table_covers_exactly_the_billable_actions`가 분류표와 1:1을 단정.

### F11. 배선·전수 가드 (PASS)

- **선언 순서**: `_REQUIRE_PROJECT_OWNER_BILLABLE = [*_REQUIRE_PROJECT_OWNER, Depends(enforce_quota)]`
  ([`main.py:1834-1837`](../../../services/application/app/main.py#L1834)) — 소유권 뒤. 404/403이 차감 앞.
  `test_enforcement_is_declared_after_ownership`가 `assertLess(owner, enforce_quota)`로 route 객체에서 단정.
- **상태코드 선언(Q5=B)**: `_billable()`가 402/429, `_owned()`가 403 추가. 403은 소유권이 이미 모든
  project-scoped 경로에 선언하므로 quota의 **net-new**는 402/429이고 가드도 그 둘을 단정(403은 상속).
- **헤더(Q6=C)**: `X-Confirm-Duplicate`가 9경로 OpenAPI parameter로 선언.
- **의존성 신원 가드**: `test_every_billable_operation_declares_the_enforcement_dependency`가
  `d.dependency is enforce_quota`(identity)로 9경로 집합을 양방향 단정.

### F12. `auth_support` 우회는 결함을 숨기지 않는다 (작업자 정밀화 #4 — PASS)

`admit_without_quota`([`auth_support.py:52-88`](../../../tests/auth_support.md))는 `enforce_quota`를
대체해 **입장**(뮤텍스·한도·잠금)만 건너뛰고 `request.state.quota_charge = charge`로 영수증을 남긴다.
`_QUOTA_STATE = "quota_charge"`([`main.py:1652`](../../../services/application/app/main.py#L1652))와 키가
**정확히 일치** → wrapper의 finally가 영수증을 읽어 **정산이 진짜로 돈다**(원장 삽입+잠금 해제).
확인 헤더도 endpoint까지 살아 간다. 시행을 진짜로 재는 `test_quota_enforcement_api.py`는 이 우회를
**쓰지 않고** 진짜 입장을 관통하며(line 7 명시 + 109-110은 auth·소유권만 override),
`test_auth_api`의 override-목록 핀(`list(app.dependency_overrides) == [...]`)이 새 우회를 감지한다.

### F13. 회귀 수치·뮤테이션 — 구현자 주장과 일치 (PASS)

- 전체(test-mongo ON): **2145 passed / 1 skipped / 1921 subtests** — 구현자 주장과 **정확히 일치**(exit 0).
- 실 Mongo 동시성 셀: 한도 1칸·20-way → 정확히 1건 입장. 각기 다른 `action`이라 8.2b 잠금은 서로를
  안 막고 **뮤텍스만** 재는 설계.
- **뮤테이션 (a)** `_is_charged`의 provider-호출 조건 제거 → 단위 행렬 셀 `(200,0)`이 `True != False`로
  **재실패**, 통합 replay 셀은 통과. 이것은 결함이 아니라 **Q1-a의 두 겹 방어**(겉: provider 조건 · 속:
  Q9 dedupe가 DB 수준에서 두 번째 행 거부)가 실제로 겹쳐 있다는 증거.
- **뮤테이션 (b)** 입장 뮤텍스 제거 → 5회 중 4회서 1건 초과 통과(2~3건) 발생 → "뮤텍스 제거=초과
  샌다" 확증. 역방향 Edit 원복 후 `git diff --stat` 공백, 트리 clean.

## Issues / Risks

### Blocking (계약 의무)

없다. Q1~Q9·Q1-a·Q1-b·Q3-a의 계약 요구가 코드로 닫혀 있고, 양방향 회귀가 각 핵심 셀을 잠그며,
전체 suite 녹색 + 뮤테이션 재실패가 실측으로 재현됐다. 작업자의 두 "정밀화"는 결정 위반이 아니라
결정을 지키기 위한 구현이다.

### Hardening recommendations (비차단)

- **H-1 — 정산의 잠금 `release`가 성공 응답을 왜곡할 수 있음(경량).**
  [`enforcement.py:344-350`](../../../services/application/app/quota/enforcement.py#L344)에서 `settle`이
  원장 삽입(`_record`, 예외 삼김 — Q2 잔여)은 `try`로 감싸지만 **`release`는 감싸지 않는다**. Mongo가
  claim 직후 release 찰나에 죽으면 예외가 wrapper의 finally까지 올라와 이미 만들어진 2xx를 503/500으로
  바꾼다. 원장 행은 이미 썼고 잠금은 lease(180s)가 회수하므로 **정합성엔 안전**, 응답 왜곡만. Q2 잔여
  원칙("성공한 응답을 뒤집지 않는다")을 release에도 적용(wrap+로그)하면 더 깔끔. 발현 창이 극히
  좁아(claim 성공 직후 ms 안에 Mongo 사망) 차단 아님.
- **H-2 — "3건 통과"는 race 인스턴스, 고정값이 아님(문서 표현 정정).**
  뮤테이션 (b)의 5회 반복에서 통과 건수는 1~3+로 변동(5회 중 4회서 초과). 정성 주장("뮤텍스 제거→
  초과 샌다")은 확증됐으나, work_log·CHANGELOG·SoT v1.7.88의 "3건 통과를 만들었다"는 "이 실행에서
  3건"으로 읽히는 게 타당(고정 계약값으로는 문서화 안 됨). 재검증자이 "정확히 3"을 기대할 수 있어
  표현을 "초과 통과(N건, 변동)"로 다듬으면 좋다.
- **H-3 — 미분류 동작이 `KeyError` → 500(503 아님).**
  [`dedupe.py:64-65`](../../../services/application/app/quota/dedupe.py#L64)의 `KeyError`는 저장소 예외가
  아니라 전역 handler에서 500이 된다(Q4=A의 503 관행과 미세 불일치). 분류표↔매핑표 1:1 가드로 도달
  불가라 실질 노출 0. 향후 유료 동작 추가 시 두 표를 같이 안 고치면 500으로 발현.
- **H-4 — 워커·app이 별개 `QuotaEnforcementService` 인스턴스(테스트 모드 한정).**
  둘 다 `_default_quota_enforcement_service(...)`로 따로 만들어 Mongo(배포)에서만 같은 컬렉션을 공유.
  in-memory(no Mongo) 조립에선 원장이 갈라진다. 단 async 우회 방지의 핵심(진행 중 job 계수)은 원장이
  아니라 **공유 job 저장소**를 직접 조회하므로 영향 없고, 원장 갈라짐은 수용된 Q2 잔여와 같은 성격.
  배포 결함 아님.
- **H-5 — `confirmed = x_confirm_duplicate is not None`이 존재 기반(trivial).**
  빈 값이어도 확인 처리. 단 확인은 dedup 잠금만 우회(다음 클릭에 재차지)라 남용 폭이 좁다.

## Verdict

**합격(PASS).** 차단 결함 없음.

오너가 확정한 12건(Q1=C·Q1-a=A·Q1-b=A·Q3=E·Q3-a=A·Q4=A·Q5=B·Q6=C·Q7=A·Q8=C·Q9=A)이 코드·테스트·실측에서
충실히 확인됐다. 작업자가 스스로 밝힌 의심 지점 셋(정산 wrapper 이동 · Q8=C replay 통과 · `auth_support`
입장 우회)을 반증 시도로 파고들었으나 어느 것도 결정 위반이나 결함 은폐로 나타나지 않았다 — 정산 wrapper는
`_is_charged`(Q1-a 정확) + 전역 `route_class` + `QuotaSettledRoute` 단정 가드로 모든 종료 경로에서 잠금을
풀고 202를 과금하지 않으며, 우회는 정산을 살려 둔다. `_is_charged`의 `(상태코드 × provider 호출)` 행렬,
뮤테이션(행렬 단위 셀 재실패 + 뮤텍스 제거→초과 확증), 전체 회귀(2145/1/1921 정확 일치)가 이를 뒷받침한다.
위 Hardening 5건은 비차단 정리/잔류 위험 기록이다.

## Outstanding items

- 본 검증은 코드·브리프·SoT를 수정하지 않았다. **인덱스·카운트·판정 분포 갱신**(`docs/verifications/README.md`·
  `docs/README.md`·`README.md`의 "검증 기록 N건" 4곳 215→216 + 합격 분포 143→144)은 이 기록 등재의 필수
  동반 작업으로 가드가 요구하는 분이며 본 세션이 함께 올렸다.
- 뮤테이션 원복 후 `git diff --stat` 공백·작업 트리 clean을 본 세션이 직접 확인했다(서브4 실측).
- **(비차단 메모)** 작업자 HANDOFF/work_log의 "8.2b 재검증 PASS의 검증 기록이 `docs/verifications/`에
  없다"는 **stale**다 — 그 기록은 `91ae4e0`에 이미 존재하며 인덱스·카운트에 포함돼 있다. 본 검증 범위
  밖이라 고치지 않았으나 알려둔다.
- Slice 8.3은 검증 합격으로 완료로 볼 수 있다. 다음은 **8.4**(프론트 배선·확인 대화 UX·면제·잔여 표시)와
  **8.2c**(이름 이력)다.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
git rev-parse --short HEAD          # 98fee5c (작업 트리 clean)

# test-mongo 기동 + healthy 대기(고정 sleep 금지 — 부분 기준선 함정)
docker compose -f docker-compose.test.yml up -d
until [ "$(docker inspect -f '{{.State.Health.Status}}' ai_writte_system-test-mongo-1)" = healthy ]; do sleep 2; done

# 전체 회귀(test-mongo ON)
python3 -m pytest -q -p no:cacheprovider
# → 2145 passed, 1 skipped, 1921 subtests (exit 0)

# 실 Mongo 동시성 셀(뮤텍스만 재는지)
python3 -m pytest -q tests/test_quota_enforcement_live_mongo.py -p no:cacheprovider -v
# → 한도 1칸·20-way → 1건 입장

# 뮤테이션 (a): _is_charged 의 provider_calls>0 제거(main.py:1799) → 행렬 셀 (200,0) 재실패
#   (통합 replay 셀은 통과 = Q1-a 두 겹 방어) → 역방향 Edit 원복 → git diff --stat 공백
# 뮤테이션 (b): enforcement.py:251 의 with self._mutex.hold(...)를 nullcontext()로 무력화
#   → 20-way 셀 5회 반복(4/5서 1건 초과 통과) → 역방향 Edit 원복 → git diff --stat 공백

# 문서 인덱스·카운트 가드(등재 동반 갱신이 맞는지)
python3 -m pytest -q tests/test_docs_indexes.py -p no:cacheprovider
# → 9 passed

docker compose -f docker-compose.test.yml down
```
