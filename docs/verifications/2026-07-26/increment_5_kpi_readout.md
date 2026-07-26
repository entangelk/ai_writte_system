# 독립 검증 — 관측 KPI 증분 5 (집계 read-out `GET /observability/kpi`)

## Subject metadata

- **날짜**: 2026-07-26
- **요청자**: 오너 ("다음작업 검증해줘. 증분 5 완료 — 커밋 2374538")
- **검증자**: 독립 검증자 (Claude, 별개 세션)
- **대상 슬라이스**: 관측 KPI 증분 5 — per-call 감사 레코드를 처음으로 읽는 집계 read-out. SoT v1.7.48. 관측 KPI 페이즈의 계측·read-out을 닫는 슬라이스.
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.7.48 §"LLM 파이프라인 관측(KPI)" read-out 조항 (392–398줄), v1.7.48 변경이력 (36줄). 결정 브리프 `docs/plans/observability-kpi-readout-decisions.md` (D1=A·D2=A, Approved 2026-07-26).
- **작업 소스**: 커밋 `2374538` (HEAD). 작업 트리 clean. 파일: `observability/kpi.py`(신규 213줄)·`main.py`(+80)·`tests/test_observability_kpi.py`(신규 385줄)·`frontend/src/api/schema.d.ts`(+128)·SoT(+10)·브리프(신규 102)·HANDOFF·work_log.

## Scope

정본 계약 스코프(SoT read-out 조항 392–398 + v1.7.48 변경이력이 묶는 범위):

1. **계약 본문 조항** (SoT 392–398) — 응답 형태·분모 3종 동반·표본 0 → null·`multi_call_correlations` 명명·latency 실패 포함 평균·루프 상태 6종 3분류. 절 내 자기 모순 탐지.
2. **집계 로직** (`observability/kpi.py`) — `aggregate_kpi`·`_totals`·`_site_kpi`·`_rows_per_correlation`·`_gate`·`_loop`, 상수 3종(`TOKEN_COUNTED_OUTCOMES`·`NON_CONVERGED_LOOP_STATUSES`·`NOT_A_LOOP_ATTEMPT`).
3. **endpoint** (`main.py`) — `GET /projects/{id}/observability/kpi`, 5개 response model, `responses=_ERRORS_404`(404+저장소 503).
4. **회귀 테스트** (`tests/test_observability_kpi.py`) — 신규 23 케이스 / 9 subtest. 각 케이스가 잠그는 집계 규칙, under/over-strict 양방향, 루프 상태 6종 전수 + `len()` 단정, H3 선언 가드.
5. **공개 계약** — `schema.d.ts` +128줄, `gen:api` 재생성 no-drift, 프론트 tsc/build/vitest.
6. **전체 회귀 스위트** — 증분 전후 증감.

## Methodology

스코프된 계약 읽기 → boundary matrix 구축 → 매트릭스 각 셀을 코드·테스트·실행으로 채우기. "틀렸다 until 깨뜨리는 데 실패" 스탠스.

**정확한 명령**:

- 정적 독해: `Read`, `git --no-pager show 2374538 -- <file>`, `grep`.
- 신규 회귀: `python3 -m pytest tests/test_observability_kpi.py -q` → `23 passed, 9 subtests passed`.
- 전체 회귀(백그라운드): `python3 -m pytest tests/ -q -p no:cacheprovider`.
- 공개 계약:
  - `git diff 2374538^..2374538 -- frontend/src/api/schema.d.ts` 로 +/- 줄 수 (+128/0).
  - `cd frontend && npm run gen:api` 재실행 후 `git status --short src/api/schema.d.ts` 로 no-drift 확인.
  - 프론트: `npm run build`(`tsc --noEmit && vite build`) + `npm test`(vitest) 백그라운드.
- **mutation 6종 (cp 백업 → Edit → 해당 테스트 실행 → `diff -q` 복원)** — 코드 3개 분모 규칙 + null + site 고정 + H3:
  - **M1**: `TOKEN_COUNTED_OUTCOMES`에 `PROVIDER_ERROR` 추가 → `TokenAggregationTest` 2건.
  - **M2**: `_loop`의 `else None` → `else 0.0` → null over-strict 2건.
  - **M3**: `NOT_A_LOOP_ATTEMPT` → `frozenset()` → `test_every_loop_status_is_classified`의 NOT_ELIGIBLE subtest.
  - **M4**: `_gate` 분모 `len(scored)` → `len(calls)` → `test_the_average_is_taken_over_scored_calls_only`.
  - **M5**: `aggregate_kpi`의 site별 calls 필터링 제거 → `test_extra_calls_are_counted_within_a_site_not_across_sites`.
  - **M6**: endpoint `responses=_ERRORS_404` → `{404: _ERROR}`(503 제거) → `test_declared_error_statuses_match_the_lock_list`.
  - 복원 후 신규 파일 재실행(23/9)로 무결성 확인.

## Findings

### 1. 계약 본문 조항 (SoT 392–398)

- **응답 형태** (393줄): `{project_id, totals, sites[], gate, loop}`, **`sites`는 배열**. 코드 `ObservabilityKpiResponse`(`main.py:1700`)의 `sites: list[...]`·스키마 `sites: components[...][]` 와 일치.
- **분모 3종 동반** (394줄): `tokens_counted_from`·`gate.scored_calls`·`loop.runs_considered`. 코드 `TotalsKpi.tokens_counted_from`·`GateKpi.scored_calls`·`LoopKpi.runs_considered` 와 1:1.
- **표본 0 → null** (395줄): `gate.avg_quality_score`·`loop.non_convergence_rate` 모두 `float | None`. 코드 `_gate`(`kpi.py:195`)·`_loop`(`kpi.py:206-208`)의 `if ... else None`와 일치. 스키마도 `number | null`.
- **`multi_call_correlations` 명명** (396줄): "repair 수가 아니다". 코드 `SiteKpi.multi_call_correlations`(`kpi.py:84`) + docstring(74–82)이 "잰 사실만 말한다"는 근거(WRITING_LOOP_MAX_GATE_EVALUATIONS=3)를 정확히 반영. 브리프 정정 노트(69–73줄)와 일치.
- **latency 실패 포함** (397줄): 코드 `_site_kpi`의 `avg_latency_ms = round(sum(모든 calls)/len)`(`kpi.py:168-170`)가 주석(165–167)과 함께 정확히 구현.
- **루프 상태 6종 분류** (398줄): 수렴(pass·terminal_decision) / 미수렴(budget_exhausted·no_change·failed) / 분모 제외(not_eligible). 코드 `NON_CONVERGED_LOOP_STATUSES`·`NOT_A_LOOP_ATTEMPT`(`kpi.py:48-61`)와 정확히 일치. `pass`·`terminal_decision`은 두 집합 어디에도 없어 자동으로 "considered & not non_converged" = 수렴으로 처리.
- **자기 모순 탐지**: 본문 6개 하위 조항(응답 형태·분모·null·명명·latency·루프 분류) 상호 일관. 모순 없음.

### 2. 집계 상수 3종 (`kpi.py:40-61`)

- `TOKEN_COUNTED_OUTCOMES = {SUCCESS, PARSE_ERROR}` (40–43). SoT v1.7.42 토큰 분모 규칙.
- `NON_CONVERGED_LOOP_STATUSES = {BUDGET_EXHAUSTED, NO_CHANGE, FAILED}` (48–52).
- `NOT_A_LOOP_ATTEMPT = {NOT_ELIGIBLE}` (59–61).
- `WritingLoopStatus` 6종(`revise_gate.py:77-83`: PASS·TERMINAL_DECISION·NOT_ELIGIBLE·BUDGET_EXHAUSTED·NO_CHANGE·FAILED)이 세 집합으로 완전 분할됨(수렴 2 + 미수렴 3 + 제외 1 = 6). 누락·중복 없음.

### 3. 집계 로직 — counter-intuitive 규칙 3개의 시행 (`kpi.py`)

- **토큰 분모**: `_totals`·`_site_kpi` 모두 `counted = [c for c in calls if c.outcome in TOKEN_COUNTED_OUTCOMES]`로 `provider_error` 행을 분모에서 제외(143, 155). `total_tokens=sum(counted)`, `tokens_counted_from=len(counted)`.
- **site 고정 correlation**: `aggregate_kpi`가 `sorted({call.call_site})`로 site를 순회하며 **site별로 calls를 필터링**해 `_site_kpi`에 전달(131). `_rows_per_correlation`는 그 site의 calls 안에서만 버킷. null `correlation_id`는 버킷팅하지 않음(184–186).
- **gate 분모**: `_gate`가 `scored = [c.gate_quality_score for c in calls if not None]`로 점수 있는 호출만 분모(191–195). loop 내부 gate 호출(점수 없음)이 평균을 0으로 끌어내리지 않음.

### 4. endpoint (`main.py:4391-4418`)

- `GET /projects/{id}/observability/kpi`, `response_model=ObservabilityKpiResponse`, `responses=_ERRORS_404`(`{404: _ERROR, 503: _STORAGE_503}`, main.py:1171).
- 순수 집계: provider 호출 없음, scope 개방 없음. `_require_project_exists` → NotFound → 404. 저장소 조회(`list_calls`/`list_runs`) 중 예외 → 전역 handler(v1.7.38) → 503, 그래서 503 선언이 맞음.
- `asdict`로 dataclass → dict 직렬화. `ObservabilityKpi` 5개 dataclass 필드명이 5개 payload model 필드명과 정확히 일치 → response_model 검증 통과.

### 5. 회귀 테스트 감사 (`tests/test_observability_kpi.py`, 23/9)

- **(a) assertion이 계약 고정**: mutation 6종으로 실증(아래). 각 테스트가 집계 규칙을 정확히 잠금.
- **(b) under-strict**: `test_a_converged_run_reports_a_real_zero`(205–210, 진짜 0.0 도달 — null이 0.0을 삼키지 않음), `test_outcome_counts_cover_every_literal`.
- **(c) over-strict (다수)**:
  - `test_the_counted_outcome_set_is_exactly_success_and_parse_error`(92–98) — **집합 자체를 고정** (가장 강력, M1에서 규칙 위반 직접 포착).
  - `test_rows_without_a_correlation_are_not_bucketed_together`(136–146), `test_no_scored_call_reports_null_not_zero`(162–165), `test_no_loop_run_reports_null_rate_not_zero`(198–203), `test_records_of_another_project_are_not_counted`(302–312), `test_the_classification_sets_do_not_overlap`(195–196), `test_an_empty_project_reports_zeros_and_nulls_not_an_error`(282–294).
- **(d) parametrized**: `test_every_loop_status_is_classified`(169–193) — **`len(WritingLoopStatus) == 6` 단정 + 6종 전수 subTest**. CLAUDE.md "every enumerated boundary value + len() guard" 정확히 충족. 새 상태 추가 시 먼저 깨져 분류 결정을 강제.
- **(e) 공개 표면**: `KpiErrorContractDeclarationTest`(321–385) — OpenAPI 스키마 5개 검증(선언 상태 집합·track 전수·error body uniform model·success body named schema ref·**sites 배열형**). D2=A의 load-bearing 이유를 스키마 수준에서 잠금.

### 6. mutation 6종 실증 (각각 해당 회귀만)

- **M1**: `TOKEN_COUNTED_OUTCOMES += PROVIDER_ERROR` → `test_provider_error_rows_are_excluded_from_token_totals` + `test_the_counted_outcome_set_is_exactly_success_and_parse_error` 2건 실패(집합 자체 고정이 가장 먼저 포착). 토큰 분모 규칙 양방향 생존.
- **M2**: `_loop` `else None` → `else 0.0` → `test_no_loop_run_reports_null_rate_not_zero` + `test_an_empty_project_reports_zeros_and_nulls_not_an_error` 2건 실패. **load-bearing case**(loop 감사 opt-in이라 기본 배포의 정상 상태) 보호.
- **M3**: `NOT_A_LOOP_ATTEMPT` → 빈 집합 → NOT_ELIGIBLE subtest 실패(`1 != 0`). not_eligible 분모 희석(루프 안 돈 것을 시도로 세 rate 낮춤) 포착.
- **M4**: `_gate` 분모 `len(scored)` → `len(calls)` → avg 0.533 ≠ 0.8. 점수 없는 loop 내부 gate 호출이 평균을 0으로 끌어내리는 것(SoT v1.7.47 공백) 포착.
- **M5**: site별 calls 필터링 제거 → query_planner가 다른 site 호출까지 세 multi_call=1 ≠ 0. SoT v1.7.47 "correlation_id는 call_site와 함께" 위반 포착.
- **M6**: endpoint `responses`에서 503 제거 → 선언 {404} ≠ lock {404,503}. H3 저장소 503 face 선언 가드 생존.
- 각 mutation은 정확히 의도한 회귀군만 포착. mutation 후 전부 `cp` 복원, 신규 파일 23/9 재통과로 무결성 확인.

### 7. 공개 계약 변경 실측

- `schema.d.ts`: `git diff 2374538^..2374538` → **+128 추가 / 0 삭제**. 작업 AI 보고와 정확히 일치.
- 신규 노출: endpoint `/projects/{project_id}/observability/kpi` + 5개 response model(`ObservabilityKpiResponse`·`SitePayload`·`TotalsPayload`·`GatePayload`·`LoopPayload`).
- 스키마에 반영된 계약: `sites: ...SitePayload[]`(배열형), `avg_quality_score: number | null`, `non_convergence_rate: number | null`(null 가능), `multi_call_correlations`, `tokens_counted_from`, `scored_calls`, `runs_considered`.
- **`npm run gen:api` 재실행 후 `git status --short src/api/schema.d.ts` = clean → schema.d.ts 재생성 == 커밋본 (no drift)**. openapi.json은 git 미추적(schema.d.ts만 커밸).

### 8. 프론트 검증 (백그라운드 b616osf1h)

- `npm run build`(`tsc --noEmit && vite build`): tsc 통과, `dist/assets/index-*.js 399.03 kB`. 작업 AI 보고 "build 399.03 kB 무변"과 정확히 일치.
- `npm test`(vitest): **194 passed (194)**, 13 test files. 작업 AI 보고와 정확히 일치.

### 9. 전체 회귀 증감 (백그라운드 b38onbjvh)

- 검증자 환경(WSL2): **1478 passed / 80 skipped / 610 subtests, 실패·에러 0** (44.65s).
- 신규 파일 단독: **23 / 9 subtest** — 작업 AI 보고 +23/+9와 정확히 일치.
- subtests **610 = 작업 AI 보고와 정확히 일치**.
- 기준선 subtests: 610−9 = **601** = 작업 AI 보고 기준선 601과 정확히 일치. (이 601은 이전 증분 C 검증의 H-1 `system_error` 추가가 v1.7.47 커밋 5725acc에 반영된 결과 — 600→601로 일관.)
- passed 차이 76(1554−1478) = 동일한 WSL2 skip 정책(elasticsearch/Chroma 드라이버 부재로 80 skip vs 작업 AI 4 skip). 증분 C 검증 때과 동일한 76. "설명되지 않는 증감 0" 유효.

### 10. 작업 AI 자기 보고 교차 검증

- **`repair_correlations` → `multi_call_correlations` 이름 정정**: 브리프 정정 노트(69–73줄)가 "소급 수정 대신 정정 노트"(과거 결정 기록 불변 원칙)를 명시. 코드·SoT·스키마 전부 `multi_call_correlations`로 일치. 작업 AI 보고와 일치.
- **D1=A 분모 동반**: `runs_considered`를 응답에 실어 0을 "데이터 없음"으로. 코드·SoT·브리프 일치.
- **H3 track 전수 가드**: `KpiErrorContractDeclarationTest.test_the_whole_observability_track_is_declared`(344–352)가 `/observability/` 경로 전수 가드. 새 endpoint 추가 시 EXPECTED에 없으면 잡힘.
- v1.7.47 엔트리에 **이전 검증(증분 C)의 hardening 2건(H-1 `system_error` + H-2 worker 헬퍼 통합) 반영 기록** 확인 — 검증 피드백이 실제로 적용됐음.

## Issues / Risks

### Blocking (계약 의무)

**없음.** boundary matrix의 계약 필수 분기(3개 분모 규칙·null 규칙·site 고정·루프 6종 분류·H3 선언) 전부가 명명된 회귀에 매핑되며, mutation 6종으로 각 잠금의 양방향 생존을 실증. SoT 본문 6개 하위 조항 자기 모순 없음. 공개 계약 변경 no-drift. 회귀·프론트 전부 green.

### Hardening recommendations (non-blocking)

**H-1 — gate `avg_quality_score`의 "진짜 0.0 도달" under-strict 가드 누락.** loop에는 진짜 0.0 도달을 잠그는 `test_a_converged_run_reports_a_real_zero`가 있으나, gate avg에는 대응하는 under-strict(예: `BLOCK`=0.0 점수만 있는 호출의 avg가 0.0이지 null이 아님)가 없다.

- **blocking이 아닌 이유**: `_gate`(`kpi.py:190-196`)가 `avg_quality_score=(sum(scored)/len(scored)) if scored else None` 단일 분기 구조다. `scored`가 비어있지 않으면 무조건 float이므로, "0.0 when scored"는 코드 구조상 자명하고 None으로 잘못 변환될 경로가 없다. loop와 달리 gate는 분기가 단순해 0.0·null 혼동 경로가 없다.
- **권장 이유**: loop under-strict가 "null vs 0.0" 구분을 대표로 잠갔지만, gate도 같은 `float | None` 타입을 쓰므로 대칭적으로 명시 잠금하면 일관성이 완성된다. 한 케이스 추가(`score=[0.0]` → avg 0.0).

**H-2 — `avg_latency_ms` 반올림 규칙·`sites` 정렬 순서를 계약에 명시.** 코드는 `round(sum/len)`(은행가 반올림)과 `sorted({call_site})`(이름 오름차순)을 쓰는데, SoT가 이 디테일을 명시하지 않는다.

- **blocking이 아닌 이유**: 동작에 영향 없는 구현 디테일. 대시보드 소비에 지장 없음. 코드 주석(`kpi.py:132-134`, 165–167)이 의도를 설명.
- **권장 이유**: 대시보드가 다음 페이즈의 입력이므로, 정렬 순서·반올림이 "계약이 정한 안정 값"이면 클라이언트가 재정렬·재반올림하지 않아도 된다. SoT read-out 조항에 한 줄 추가.

## Verdict

**합격 (pass).**

이유(유효 하중):

1. 집계 규칙 3개(토큰 분모 `success`+`parse_error` / 표본 0 → `null` / `not_eligible` 분모 제외)가 직관에 반하므로 계약이 분모를 함께 싣도록 못박았고, 코드·테스트·스키마가 그것을 정확히 구현. mutation 6종이 각 규칙의 양방향 생존을 실증(M1 토큰 분모·M2 null·M3 not_eligible·M4 gate 분모·M5 site 고정·M6 H3 503).
2. **루프 상태 6종 분류가 `len(WritingLoopStatus)==6` 단정 + 전수 subTest로 잠겼다** — CLAUDE.md의 parametrized 커버리지 원칙을 가장 모범적으로 충족. 새 상태 추가 시 분류 결정 없이 회귀가 먼저 깨진다.
3. **`multi_call_correlations` 이름 정정**이 브리프 정정 노트(과거 결정 기록 불변) + 코드 docstring + SoT 본문 + 스키마 4곳에서 일관. 작업 AI가 테스트 작성 중 발견한 "이름의 거짓"을 투명하게 처리.
4. 공개 계약 변경을 실측: `schema.d.ts` +128/0, `gen:api` 재실행 no-drift, 프론트 tsc 통과·build 399.03 kB·vitest 194 — 작업 AI 보고 전 수치와 정확히 일치.
5. 회귀 1478 passed/610 subtests(검증자 환경); subtests 610·신규 23/9·기준선 601·passed 차이 76(=skip 정책) 전부 작업 AI 보고와 일치. "설명되지 않는 증감 0" 유효.
6. SoT read-out 본문 6개 하위 조항 자기 모순 없음.

Hardening 2건(H-1 gate 0.0 under-strict, H-2 latency 반올림·sites 정렬 명시)은 모두 동작이 이미 보장된 경로의 일관성·계약 명시 제안이며, 계약 요구 잠금이 빠진 것이 아니다.

## Outstanding items

- **커밋 완료**: `2374538` HEAD, 작업 트리 clean. 검증자 mutation 전부 복원 후 `diff -q`로 원본 일치 확인.
- **관측 KPI 페이즈 폐쇄**: 증분 4·B·C·5로 계측·read-out 닫힘. 다음은 대시보드 페이즈(오너 분리).
- **CHANGELOG 일괄 반영 제안**: 작업 AI가 v1.7.41~48 한 행 정리를 제안 중 — 오너 확인 사항.
- **오너 결정 대기 2건**(HANDOFF, 증분 C부터 이월): ① `analysis_extractor` D4 정렬, ② loop round별 gate decision 노출(loop 내부 gate 레코드 파생점수 커버리지의 유일한 경로, D2-B 연계). 둘 다 도메인 계약 변경 동반 → 별도 증분+이행 무손실 증명.

## Reproduction

```bash
# 1. 신규 회귀 (23/9)
python3 -m pytest tests/test_observability_kpi.py -q

# 2. 전체 회귀 (skip 수는 머신마다 상이)
python3 -m pytest tests/ -q -p no:cacheprovider

# 3. 공개 계약 no-drift
cd frontend && npm run gen:api && git status --short src/api/schema.d.ts  # clean

# 4. 프론트
cd frontend && npm run build && npm test   # tsc 0, 399.03 kB, vitest 194

# 5. mutation (cp 백업 → Edit → 실행 → 복원). 예: M2
cp services/application/app/observability/kpi.py /tmp/kpi.py.bak
# Edit _loop: `else None` → `else 0.0`
python3 -m pytest "tests/test_observability_kpi.py::LoopConvergenceTest::test_no_loop_run_reports_null_rate_not_zero" -q  # → FAILED
cp /tmp/kpi.py.bak services/application/app/observability/kpi.py && diff -q services/application/app/observability/kpi.py /tmp/kpi.py.bak
```
