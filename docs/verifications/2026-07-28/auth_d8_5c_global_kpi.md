# 독립 검증 — 인증 D8-5c 전역 관측 KPI (SoT v1.7.57)

## Subject metadata

- **날짜**: 2026-07-28
- **요청자**: 오너 (“작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?”)
- **검증자**: 독립 AI(Claude Code)
- **대상 슬라이스**: D8-5c — `GET /admin/observability/kpi` 전역 관측 KPI read-out
- **정준 계약**: `docs/system-contract-sot.md` v1.7.57(변경이력 + 본문 §”LLM 파이프라인 관측(KPI)” 전역 read-out·버킷 키 조항 + §H3 403 행 `/admin/*` 4개)
- **결정 근거**: `docs/plans/auth-d8-5-admin-decisions.md` §4(5-c)·§5(“전역 KPI는 `project_id` 축을 잃지 않아야 한다”)
- **검증 대상 소스**: 작업 트리, 미커밋(`git status` — `main.py`, `observability/kpi.py`, 감사 repo 4종, `schema.d.ts`, 테스트 6종, SoT/CHANGELOG/HANDOFF/work_log 변경)

## Scope

검증 계약 범위(스코핑된 읽기로 도출):

1. **정준 계약 조항** — SoT v1.7.57 (a) 변경이력 전역 KPI 항, (b) 본문 §”LLM 파이프라인 관측(KPI)”의 전역 read-out + 버킷 키 `(project_id, correlation_id)` 조항, (c) §H3 상태코드 표 403 행(`/admin/*` 4개)·404 행, (d) 제품 경계 절의 tier 수(69 = public 4 · 인증 전용 2 · 관리자 4 · project-scoped 59).
2. **구현** — `services/application/app/observability/kpi.py`(`aggregate_global_kpi`, 공용 `_fold`, `_rows_per_correlation` 버킷 키, `GlobalObservabilityKpi`), `services/application/app/main.py`(`admin_observability_kpi_endpoint`, `AdminObservabilityKpiResponse`, `_REQUIRE_ADMIN`/`_ERRORS_ADMIN`), 감사 repo 4종(`list_all()` Protocol+in-memory+Mongo, 서비스 `list_all_calls()`/`list_all_runs()`, Mongo `created_at` 단독 index 2종).
3. **회귀 테스트** — `tests/test_observability_kpi.py`(`GlobalAggregationTest` 8, `AdminKpiEndpointTest` 5, `KpiErrorContractDeclarationTest` 규칙 변경), 감사 repo 테스트 4종(`list_all` 경계·정렬·index 이름·fake 왕복), `tests/test_application_api.py::AdminErrorContractDeclarationTest`(4 op), `tests/test_auth_api.py::CombinedBoundaryMatrixTest`(tier 69).
4. **공개 계약** — `frontend/src/api/schema.d.ts`(gen:api 동기화), OpenAPI self-discovery(`$ref`, sites 행 타입 공유).

## Methodology

계약을 먼저 읽고 경계 매트릭스(lock list)를 세운 뒤, 코드·테스트를 그 매트릭스에 대조. 모든 정량·뮤테은 독립 재도출(작업자 주장을 전제하지 않음). 명령:

# 0. 인프라 — test-mongo(rs-test, 27020) ON 사전 확인
- `docker ps` → `ai_writte_system-test-mongo-1` 27020 healthy.
- 표준 관행: `CORE_SOT_TEST_MONGO_URI=mongodb://localhost:27020/?replicaSet=rs-test`(memory 참조).

# 1. 초점 스위트(test-mongo ON)
- `PYTHONPATH=. python3 -m pytest tests/test_observability_kpi.py tests/test_llm_call_audit.py tests/test_llm_call_audit_mongo.py tests/test_writing_loop_audit.py tests/test_writing_loop_audit_mongo.py -q`
- `PYTHONPATH=. python3 -m pytest CombinedBoundaryMatrixTest AdminErrorContractDeclarationTest GlobalAggregationTest AdminKpiEndpointTest MultiCallCorrelationTest -v`

# 2. 뮤테이션 탐침(실소스 무변, in-process monkeypatch)
- `/tmp/d85c_mutation_probe.py` — 실 `_rows_per_correlation`을 변이판으로 교체해 `aggregate_global_kpi`를 구동.
  잠긴 단정과 모순되면 해당 테스트가 그 뮤테에서 실패함을 증명. M1(키=correlation_id 단독)·M2(키=(project, call_id) 과분할)·M4(loop_runs=()).

# 3. 공개 계약 독립 도출
- gen:api round-trip: `dump_openapi.py → openapi.json → openapi-typescript` 재생성 후 `git diff --stat`로 커밋본과 동일한지(동기화) 확인.
- `npx tsc --noEmit` / `npx vite build` / `npx vitest run`.

# 4. 전량(test-mongo ON) — 재도출 진행 중(결과는 Findings §9 기재)
- `PYTHONPATH=. python3 -m pytest -q`

# 5. 계약 자기일관 — 변경이력·본문·H3·tier 수가 서로 모순 없는지 대조.

## Findings

### 1. 버킷 키 — “넓혀야만 드러나는 오집계”는 실제 버그이고, 수정은 올바르다

- `_rows_per_correlation` 키가 `correlation_id`(str) → `(project_id, correlation_id)`(tuple)로 바뀜(`kpi.py:235,246,250`). `correlation_id`는 호출자의 `request_id`/`idempotency_key`라 **서로 다른 project가 같은 문자열을 쓸 수 있고**, 전역에서 두 project의 1회 호출이 한 워크플로 2건으로 접혀 “일어나지 않은 repair”로 집계되는 것이 브리프 §5가 가리킨 지점임.
- **뮤테이션 M1(키에서 project 제거) 실측**: 두 project 같은 `correlation_id="wr-1"` 입력 → 정상 키는 `correlations=2, multi_call=0`(잠긴 단정)이나, 변이판은 `correlations=1, multi_call=1`을 내어 under-strict 테스트와 엔드포인트 payload 테스트가 모두 실패. 작업자가 찾은 버그가 재현되고 테스트가 잡는다.
- **per-project 불변 주장 검증**: 공용 `_fold`를 쓰므로 키 변경은 per-project 경로에도 적용되나, `aggregate_kpi`는 항상 단일 project 호출만 받고(`list_calls(project_id) → list_for_project` filter), site 내 모든 행이 같은 `project_id`를 가져 `(project_id, correlation_id)`가 `correlation_id`와 동일한 버킷링을 낳는다 — 구성상 불변. 기존 `MultiCallCorrelationTest::test_a_second_row_in_the_same_site_is_counted`(per-project, `correlations=2, multi_call=1`)가 그대로 통과해 이를 행위로도 확인.

### 2. 양방향 가드 — 둘 다 물고, 과교정도 잡는다

- M2(키를 `(project, call_id)`로 과분할) 실측: 한 project 2호출 + 다른 project 1호출 → 정상은 `correlations=2, multi_call=1`이나, 변이판은 `correlations=3, multi_call=0`을 내어 over-strict 테스트(`test_a_second_call_within_one_project_is_still_counted`)가 실패. “project를 넣었다”는 정당 수정이 “모든 호출을 별개로 세는” 과교정과 구분됨.
- 오독 방어 3종이 전역에서 재구동됨: 분모 동반(token/provider_error 제외)·표본 0 → `null`·`multi_call_correlations`≠repair 수. 셋 각각 전역 입력으로 잠김(`GlobalAggregationTest`).

### 3. 엔드포인트 경계 — 401·403·503, 404 없음(계약대로)

- `main.py:2347`: `responses=_ERRORS_ADMIN`=`{401,403,503}`·`dependencies=_REQUIRE_ADMIN`(두 겹). per-project KPI가 `_owned(_ERRORS_404)`로 404를 선언하는 것과 대칭적으로, **404를 선언하지 않는다** — 해석할 project가 없으므로 없을 것도 없다(SoT 본문 조항과 일치).
- 401/403: `CombinedBoundaryMatrixTest`가 실 비관리자를 ADMIN 리터럴 집합(이제 4 op, `/admin/observability/kpi` 포함) 전체에 구동해 403을 단정 → 통과. 배선이 `_REQUIRE_AUTH`였다면 비관리자가 200을 받아 실패. M3(배선 교체)는 구조적 추론으로 입증.
- **503 기계적 도달 가능**: 엔드포인트 본문에 try/except가 없으나 `create_app:2061-2062`의 전역 핸들러가 `PyMongoError` → 503으로 매핑(app-level, 등록 순서 무관). `list_all_calls()`/`list_all_runs()` 장애가 500으로 누출되지 않는다. 선언된 503은 거짓이 아니다.

### 4. `projects_considered` — 분모 형태의 project 축, 이름 없음

- `aggregate_global_kpi`가 `len({call.project_id} ∪ {run.project_id})`로 계산. 레코드를 남긴 project 수이며 **어떤 project도 이름 짓지 않는다**(per-project 분해 부재 = 5-b·F1=C 하위 결정을 앞질러 식별자를 노출하지 않음 — SoT 본문 조항·결정 브리프 §4와 일치).
- loop-only project도 분모에 포함(`test_projects_considered_counts_loop_only_projects_too`), 한 project 중복 미가산(`test_projects_considered_does_not_double_count_one_project`).

### 5. 저장소 — 별도 메서드, 경계 횡단 + 정렬 유지 + index

- `list_all()`(nullable `project_id`가 아닌 별도 메서드 — None 흘림 방지)가 Protocol+in-memory+Mongo 양쪽에, 서비스 `list_all_calls()`/`list_all_runs()`.
- in-memory·Mongo 양쪽에서 `list_all`이 (a) project 경계를 넘고 (b) newest-first 정렬을 유지함을 단정. fake가 `create_index`를 기록하므로 Mongo index 2종 이름 고정 테스트는 유효(공허하지 않음).
- Mongo `created_at` 단독 index 2종 추가 — 복합 `(project_id, created_at)`이 project 없는 정렬을 못 태우고, 미색인 정렬이 32MB sort buffer 초과 시 실패한다는 근거가 타당.

### 6. 공개 계약 — gen:api round-trip 동일, additive

- 재생성 결과 커밋본과 **정확히 동일**(+74 insertions, 0 deletions). `AdminObservabilityKpiResponse`가 기존 `ObservabilityKpi{Gate,Loop,Site,Totals}Payload`를 재사용 → sites 행 타입 공유가 스키마 수준에서 확인. operation 응답 200·401·403·503(404 없음).
- `tsc --noEmit` exit 0. `vite build` 성공(진입 404.87 kB·관측 lazy 385.71 kB, 기준선 무변 — frontend 소비자가 아직 없으므로 번들 크기 변동 없음, 작업자 주장과 일치). `vitest run` 217 passed / 14 files(exit 0).

### 7. 스키마 self-discovery — `$ref` + 행 타입 공유 잠금

- `AdminKpiEndpointTest::test_the_success_body_is_a_declared_model_not_a_free_dict`가 OpenAPI 200 응답이 `$ref → AdminObservabilityKpiResponse`임을 단정(free dict 아님).
- `test_the_site_row_type_is_shared_with_the_per_project_read_out`가 두 응답 모두 sites items → `ObservabilityKpiSitePayload` 동일 `$ref`임을 단정.

### 8. boundary matrix·H3 lock list — 관리자 tier 4 op로 정식 편입

- `CombinedBoundaryMatrixTest`: tier 4 = public 4 + 인증 전용 2 + **관리자 4** + project-scoped 59 = **69**(종전 68). `len(tiers)==69`, `len(project)==59` 통과. `/admin/observability/kpi`가 ADMIN 리터럴에 추가.
- `AdminErrorContractDeclarationTest`: EXPECTED 4 op, `/admin/observability/kpi` → `{401,403,503}`(404 없음). `len(EXPECTED)==4`.
- 관측 track `KpiErrorContractDeclarationTest` 폐쇄 가드가 `/admin/`을 **규칙으로** 제외(`not path.startswith("/admin/")`). 이 규칙이 load-bearing임을 읽기로 입증 — 제외가 없으면 `/admin/observability/kpi`가 관측 track EXPECTED에 없어 undeclared로 잡힘(M5).

### 9. 정량 — 초점·프론트 재현, 전량은 아래

- 초점(test-mongo ON): KPI+감사 repo `74 passed / 26 subtests`; boundary+admin H3+전역집계+엔드포인트+per-project multi-call `31 passed / 394 subtests`.
- delta 회계: 신규 테스트 함수 = 전역집계 8 + 관리자 엔드포인트 5 + 저장소 순신규 6(list_all 6; index 2종은 rename이라 신규 아님) = **19**(작업자 +19 주장과 정확 일치).
- 백엔드 전량(test-mongo ON): **1700 passed / 1 skipped / 1468 subtests (734.36s)** — 작업자 주장(1700/1/1468)과 정확히 일치(실행시간만 더 빠름). 종전 기준선 1681/1/1455 대비 +19 passed / +13 subtests이고 설명되지 않은 증감은 0이다.
- 프론트: tsc exit 0 / build 성공 / vitest 217 passed(exit 0).

### 10. 정준 계약 자기일관 — 모순 없음

- 변경이행·본문 read-out·버킷 키 조항·H3 403 행·tier 수(69)가 서로 일치. H3 “403 생산자는 정확히 둘”(소유권·관리자) 선언이 관리자 4 op와 모순 없음. 404 행(자원 수준 격리)과 관리자 404 부재가 충돌 없음(해석 대상이 다름).

## Issues / Risks

### Blocking (계약 의무)

- **없음.** 계약이 요구하는 모든 분기(should-fire / should-NOT-fire)가 명명된 회귀 테스트에 매핑되며, 빈 칸이 없다. 버킷 키 양방향·401/403/503·404 부재·공개 계약 동기화·tier 편입·스키마 self-discovery까지 잠겨 있다.

### Hardening recommendations (비차단, 현 계약 범위 초과)

- **H-1 (기록 정확성)**: 작업자가 “뮤테이션 5종”을 주장했으나 검증 prose에는 4종만 상술했다(M1 project 제거·M2 과분할·M3 `REQUIRE_ADMIN`→`REQUIRE_AUTH`·M4 loop_runs=()). 다섯 번째는 관측 track H3 `/admin/` 제외 규칙 mutation(M5)으로 정합하게 해석되어 카운트 5는 성립하지만, prose에 명시되지 않아 추적성이 떨어진다. 추후 뮤테 회차에는 전수를 prose에 기록 권고.
- **H-2 (가능한 미래 부채, 현 결함 아님)**: `projects_considered`가 `None` project_id를 하나의 project로 센다. SoT가 `project_id`를 항상 강제(“project_id 강제는 그대로 살아남는다”)하므로 현실에서 `None`은 발생하지 않는다. 다만 `_rows_per_correlation`은 `correlation_id is None`을 skip하는 데 반해 project_id에는 대칭 가드가 없다. 향후 레코드 형태가 바뀌어 `None`이 흘러들면 분모가 왜곡되므로, 그 시점에 `if project_id is not None` 가드를 고려. 현 계약 위반 아님.
- **H-3 (재현 불가 flake)**: 작업자가 첫 vitest 1건 실패·재실행 217 통과를 “재현 불가 flake”로 기록했다. 이번 검증에서도 217 passed(exit 0)로 재현되지 않아 기록 정확. 본 슬라이스는 `schema.d.ts` additive만 건드리므로 회귀 인과도 없다. 반복 시에만 추적.

## Verdict

**합격(차단 0건).**

- 이유: (1) 버킷 키 수정은 실제 버그에 대한 올바른 수정이며 양방향으로 잠겼다(in-process 뮤테 M1·M2로 입증). (2) 계약이 요구하는 모든 분기가 명명된 회귀에 매핑되어 boundary matrix에 빈 칸이 없다. (3) 503이 전역 핸들러로 기계적 도달 가능해 선언이 거짓이 아니다. (4) 공개 계약이 gen:api round-trip으로 동기화됐고 tsc/build/vitest green. (5) 정준 계약 자기일관에 모순이 없다.
- 비차단 3건(H-1~H-3)은 현 계약 범위 밖이거나 기록 정확성이며, 합격 판정을 바꾸지 않는다.

## Outstanding items

- **백엔드 전량 재도출 완료**: 1700 passed / 1 skipped / 1468 subtests (734.36s, test-mongo ON) — 작업자 주장과 정확히 일치. `Methodology #4` 명령으로 재현 가능.
- 오너의 다음 행보는 작업자가 제시한 대로: 5-b·5-d는 브리프 §7 C-1~C-6 오너 결정 대기, D8-6(영구 삭제)은 그 결정 없이 진행 가능.

## Reproduction

# 인프라
docker compose -f docker-compose.test.yml up -d   # test-mongo 27020 rs-test
docker ps | grep test-mongo                        # healthy 확인

# 초점(test-mongo ON)
PYTHONPATH=. python3 -m pytest tests/test_observability_kpi.py \
  tests/test_llm_call_audit.py tests/test_llm_call_audit_mongo.py \
  tests/test_writing_loop_audit.py tests/test_writing_loop_audit_mongo.py -q
PYTHONPATH=. python3 -m pytest \
  "tests/test_auth_api.py::CombinedBoundaryMatrixTest" \
  "tests/test_application_api.py::AdminErrorContractDeclarationTest" \
  "tests/test_observability_kpi.py::GlobalAggregationTest" \
  "tests/test_observability_kpi.py::AdminKpiEndpointTest" \
  "tests/test_observability_kpi.py::MultiCallCorrelationTest" -v

# 뮤테이션 탐침(실소스 무변)
PYTHONPATH=. python3 /tmp/d85c_mutation_probe.py   # M1·M2·M4 각 bite=True

# 공개 계약 round-trip + 프론트
cd frontend && PYTHONPATH=.. python3 ../scripts/dump_openapi.py > openapi.json \
  && npx openapi-typescript openapi.json -o src/api/schema.d.ts
git diff --stat HEAD -- frontend/src/api/schema.d.ts   # +74/0 = 동기화
npx tsc --noEmit && npx vite build && npx vitest run

# 전량(test-mongo ON)
PYTHONPATH=. python3 -m pytest -q
