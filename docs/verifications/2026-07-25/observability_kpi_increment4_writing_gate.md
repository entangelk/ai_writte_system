# 독립 검증 — 관측 KPI 증분 4: `writing_gate` 첫 호출부 계측 + 와이어링 (SoT v1.7.42)

## Subject metadata

- **날짜**: 2026-07-25
- **요청자**: 오너 ("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래" — 증분 4 / SoT v1.7.42)
- **검증자**: Claude (독립 검증, 구현자와 무관)
- **대상 슬라이스**: 관측 KPI 페이즈 증분 4 — v1.7.41이 만든 `llm_call_audits` per-call 레코드를 `create_app`에 와이어링하고 `POST …/writing/gate`를 첫 계측 호출부로 만드는 변경. SoT v1.7.41 → v1.7.42.
- **정본(계약) 참조**: `docs/system-contract-sot.md` v1.7.42 — 본문 §"LLM 파이프라인 관측(KPI)"(`L356-L366`). 특히 v1.7.42가 **신규 추가한 3조항**: ① 격리 시행 지점·전역 handler와의 순서(`L364`), ② 레코드 조건 = provider 실호출(`L365`), ③ 계측 호출부 + `*_metered` 토큰 취득(`L366`). 무변 조항: 레코드 필드·`call_site`/`outcome` enum·게이트 파생 품질점수(`L360-L363`, v1.7.41). 변경이력 `v1.7.42` 행(`L36`).
- **검증 대상 작업 출처**: working tree, 미커밋(`git status`: `M` 4개 = `main.py`·`test_writing_gate.py`·`system-contract-sot.md`·`HANDOFF.md` + `??` `docs/daily_logs/2026-07-25/work_log.md`). HEAD = `9af173b`. 브리프 `docs/plans/observability-kpi-decisions.md`(상태 `Approved — 2026-07-24 (D1=B · D2=C[파생 먼저] · D3=A · D4=A · D5=계약 의무대로)`).

## Scope (정본 계약 범위 — 열기 전에 확정)

계약 문서를 임의로 전수 탐색하지 않고, 이 슬라이스가 지배하는 표면만 좁혀 읽었다(CLAUDE.md §5 "scope the contract read"):

1. **SoT 본문 §"LLM 파이프라인 관측(KPI)"** 전문(`L356-L366`, 6조항). v1.7.42 추가 3조항(`L364-L366`)을 본문 끝까지 읽고, v1.7.41이 정의한 레코드 모양(`L360-L363`)과의 정합을 교차 확인.
2. **SoT 변경이력** `v1.7.42`(`L36`) + `v1.7.41`(`L37`, 레코드/enum/score 정의의 근거).
3. **브리프** `docs/plans/observability-kpi-decisions.md` 전문(D1~D5 + Follow-up + Deferred — 특히 D2 파생점수·D5 schema lock).
4. **구현**: `services/application/app/main.py` — `_default_llm_call_audit_service`(`L433-L448`), `create_app` 파라미터(`L1702`), `_record_llm_call` 격리 헬퍼(`L1796-L1806`), `_record_gate_call` 로컬 헬퍼(`L3769-L3788`), `/writing/gate` endpoint 본체(`L3791-L3831`). `services/application/app/writing/gate.py`(`L54-L92` evaluate/evaluate_metered). `services/application/app/writing/metering.py`(`MeteredCallError`). `services/application/app/observability/llm_call_audit.py`(`_GATE_DECISION_QUALITY`·`gate_quality_score`·`StoredLlmCall`·`LlmCallAuditService.record`).
5. **회귀**: `tests/test_writing_gate.py::WritingGateObservabilityTest`(신규 7) + `_FailingAuditRepository` 헬퍼 + `WritingGateApiTest._client` 확장.
6. **공개 envelope/타입**: `frontend/openapi.json`·`frontend/src/api/schema.d.ts`(`gen:api` 결정적 생성).

범위 밖: 나머지 호출부(generation·planner·compare·extractor) 계측 — 후속 증분(워크로그 명시). 집계 read API(증분 5). Mongo 어댑터 field round-trip·index-name(v1.7.41 `test_llm_call_audit_mongo.py` lock, 이번 슬라이스 무변).

## 경계 매트릭스 (정본이 요구하는 분기 — 코드/테스트가 채워야 할 lock list)

정본 읽기에서 도출한 분기를 먼저 세우고, 코드·회귀가 각 cell을 채우는지 추적했다. **빈 cell은 blocking finding**이다.

| # | 분기(should fire / NOT fire) | 유형 | 코드(file:line) | 회귀 테스트 | 가드 방향 |
|---|---|---|---|---|---|
| 1 | success 레코드 — 전 필드(call_site·outcome·correlation_id·project·model·decision·score·tokens·latency·error_type) | FIRE | `main.py:3826` `_record_gate_call(SUCCESS)` | `test_successful_gate_call_is_recorded_with_its_derived_quality_score` | under-strict(레코드/필드 제거) |
| 2 | decision 5종 → score 전수 매핑(PASS 1.0 / NUR 0.6 / RM 0.5 / REV 0.3 / BLOCK 0.0) | FIRE | `llm_call_audit.py:75-81`, `:84-91` `gate_quality_score` | `test_every_gate_decision_records_its_contract_score` (parametrized 5 + `set(expected)==enum` 전수 확인 `test_writing_gate.py:504-506`) | over-strict(잘못된 매핑 / 새 decision 미커버) |
| 3 | provider_error(TIMEOUT→504, UNAVAILABLE→502) + `error_type=code.value` + tokens=0 + decision/quality=None | FIRE | `main.py:3821-3825` | `test_provider_failure_is_recorded_and_keeps_its_status` (parametrized 2) | under-strict(레코드 제거) |
| 4 | parse_error + 실소비 토큰(`exc.usage`) + `error_type="InvalidWritingGateResult"` + quality=None | FIRE | `main.py:3810-3816` | `test_parse_failure_records_the_tokens_that_were_really_spent` | under-strict(token 캡처) |
| 5 | `context_search_failed`(502) 미기록 | NOT FIRE | `main.py:3792` build 전 / `3797` except | `test_rejections_before_the_provider_is_called_record_nothing` (case=context_search_failed) | over-strict(호출 전 기록) |
| 6 | `context_budget_exceeded`(504) 미기록 | NOT FIRE | `main.py:3795` except(build 전) | 동일 (case=context_budget_exceeded) | over-strict |
| 7 | bad `task_type`(400) 미기록 | NOT FIRE | request boundary(`WritingTaskType(...)` 검증) | 동일 (task_type="nope") | over-strict |
| 8 | 격리 — 감사 write RuntimeError → 응답 200 유지 | ISOLATION | `main.py:1798-1806` `_record_llm_call` `except Exception → return` | `test_audit_write_failure_does_not_break_the_gate_response` | under-strict(격리 제거) |
| 9 | 격리 — pymongo(AutoReconnect) → 200, **전역 503 handler 안쪽** | ISOLATION | 동일 | `test_audit_storage_failure_does_not_surface_as_a_503` (skipIf pymongo) | over-strict(503으로 뒤집힘) |

**빈 cell 없음.** 정본이 요구하는 9개 분기 전부 명명된 회귀로 lock됐다. `budget_exceeded` outcome은 이 site에서 발화하지 않는다(context budget은 `L365`에 따라 호출 전) — 회귀가 이를 안 다루는 것은 정본 정합이지 누락이 아니다.

## Methodology

정적 도출과 동적 실행을 병행했다. 모든 주장을 primary source에서 재도출했고, 작업 AI의 서술을 받아쓰지 않았다.

- **정적 — 계약/리터럴 교차검증**: 본문 §관측 KPI(`L356-L366`) ↔ 변경이력 `v1.7.42`/`v1.7.41` ↔ 브리프 D1~D5 간 정합. `evaluate()→evaluate_metered()` 전환의 응답 무변을 `gate.py:54-92`의 unwrap 체인(`MeteredCallError.cause` 단일 생성지 `gate.py:84`)과 endpoint except 절 매핑을 대조해 추적.
- **동적 — focused 회귀**: `env -u CORE_SOT_MONGO_URI python3 -m pytest tests/test_writing_gate.py -q` → `44 passed, 41 subtests`.
- **동적 — 전체 suite(after)**: `env -u CORE_SOT_MONGO_URI -u CORE_SOT_MONGO_DB -u ELASTICSEARCH_URL python3 -m pytest -q -p no:cacheprovider` → `1409 passed, 80 skipped, 593 subtests`.
- **동적 — 전체 suite(before)**: `git stash push -- <소스 4>` 로 변경 전 복원 후 **동일 머신·동일 조건**(test-mongo 미기동, pymongo present, elasticsearch 부재)에서 재측정 → `1402 passed, 80 skipped, 584 subtests`. `git stash pop` 복구.
- **동적 — mutation 3종**: 각 계약 결정별로 코드를 깨고 focused 회귀가 정확히 해당 cell만 물리는지 확인. 적용→`pytest`→역방향 Edit 원복, `diff /tmp/main.py.after services/application/app/main.py`로 잔재 없음 확인(3종 모두 no-diff 복구).
- **동적 — gen:api no-diff**: (a) after 코드 `npm run gen:api` 후 `schema.d.ts` tracked·`git status` clean 확인(after dump == HEAD); (b) `git stash` 로 before 코드 dump와 비교 — `openapi.json`·`schema.d.ts` 각 `diff` 로 identical 실증.
- **환경**: pymongo `4.13.2` present(#9 회귀 skip 아님). `elasticsearch` 파이썬 패키지 부재 → lexical retrieval 3건 skip(이 머신). `CORE_SOT_MONGO_URI`/`ELASTICSEARCH_URL` unset → in-memory 경로.

## Findings (표면별 — 모든 주장에 file:line)

### F1. 계약 ↔ 구현 리터럴 정합
- `call_site="writing_gate"`: `main.py:3783` `LlmCallSite.WRITING_GATE` · `llm_call_audit.py:50` `WRITING_GATE="writing_gate"`. SoT `L361` enum 일치. ✓
- `outcome` success/provider_error/parse_error: `main.py:3813`(PARSE_ERROR)·`:3822`(PROVIDER_ERROR)·`:3826`(SUCCESS). `llm_call_audit.py:59-61`. SoT `L362`. `budget_exceeded`는 이 site 미발화(워크로그 의도). ✓
- score 매핑 `PASS=1.0·NEEDS_USER_REVIEW=0.6·RETRIEVE_MORE=0.5·REVISE=0.3·BLOCK=0.0`: `llm_call_audit.py:75-81` `_GATE_DECISION_QUALITY` 단일 dict. SoT `L363` 정합. ✓
- `correlation_id=body.request_id`: `main.py:3783`. SoT `L360` "호출을 워크플로로 묶음". 회귀 `test_successful…` 가 `"wr1"`(request_id)로 단정. ✓
- `total_tokens`: success/parse=`usage.total_tokens`(=2), provider=0. `main.py:3830`(success, `usage=usage`)·`:3813`(parse, `usage=exc.usage`)·`:3822`(provider, usage 미전달→default 0). ✓
- `error_type`: parse=`type(exc.cause).__name__`=`"InvalidWritingGateResult"`(`main.py:3815`, cause는 `gate.py:84` 의 `InvalidWritingGateResult` 단일 생성지), provider=`exc.code.value`(`main.py:3823`, provider taxonomy 보존). ✓

### F2. `evaluate()` → `evaluate_metered()` 전환의 응답 무변
- `gate.py:54-62` `evaluate()` 는 `evaluate_metered()` 를 감싸 `_usage` 를 폐기(`L58` `evaluated, _usage`)하고 `MeteredCallError` 를 `raise exc.cause`(`L60-61`)로 unwrap하는 얇은 래퍼.
- endpoint **before**: `result = await writing_gate.evaluate(...)`. endpoint **after**: `result, usage = await writing_gate.evaluate_metered(...)`(`main.py:3808`) + 인라인 unwrap `except MeteredCallError as exc: raise HTTPException(502, detail=str(exc.cause))`(`main.py:3810-3816`).
- `exc.cause` 는 항상 `InvalidWritingGateResult`(`gate.py:84` 단일 생성지이므로 다른 cause 불가). 따라서 after의 `except MeteredCallError→502(str(exc.cause))` 는 before의 `except InvalidWritingGateResult→502(str(exc))`(`main.py:3819-3820` after에 잔존)와 status(502)+detail 문자열이 동일. `WritingGateError→400`·`ProviderError→504/502` 매핑도 무변. **응답 무변 확정.** ✓
- 기존 gate 회귀(`GateContractTest` 등 37건) 전부 green(focused `44 passed`에 포함). 무변을 독립적으로 지킨다. ✓

### F3. 격리 시행 지점 단일성 + 전역 handler 안쪽
- `_record_llm_call` 단일 정의(`main.py:1798-1806`): `try: llm_call_audit.record(...) except Exception: return`. `_record_gate_call`(`main.py:3769-3788`)는 outcome/필드 인자만 넘기고 격리를 재구현하지 않는다. SoT `L364` "시행 지점은 `_record_llm_call` 한 곳" 정합. ✓
- pymongo 예외가 이 `except` 안에서 잡혀 v1.7.38 전역 저장소 handler에 도달하지 못한다. SoT `L364` "v1.7.38 전역 저장소 handler보다 안쪽" 정합. mutation-B 로 실증(아래). ✓

### F4. 레코드 조건 = provider 실호출
- `build_context_package`(`main.py:3792`)가 별도 try(`L3791-L3801`)에 있고 `started = time.perf_counter()`(`L3806`)가 그 **이후**. `evaluate_metered` try(`L3807-`) 안에서만 `_record_gate_call` 가 호출된다. 그래서 build 실패(`ContextSearchFailed L3797` / `ContextSearchBudgetExceeded L3795`)·bad `task_type`(request boundary)는 `started` 이전에 raise → `_record_gate_call` 미도출 → 미기록.
- SoT `L365` "provider가 실제로 호출된 경우" 정합. mutation-C 로 실증(아래). ✓

### F5. 와이어링 (`create_app`)
- `_default_llm_call_audit_service`(`main.py:433-448`): in-memory 기본, `CORE_SOT_MONGO_URI` 시 `MongoLlmCallAuditRepository.from_uri`(loop audit 팩토리 `_default_writing_loop_audit_service` 미러).
- `create_app` 파라미터(`main.py:1702`), `llm_call_audit = llm_call_audit_service or _default_llm_call_audit_service()`(`L1796`). opt-in 아님 — 워크로그 결정: "KPI는 요청한 사람이 있을 때만 세는 순간 측정이 아니게 된다". SoT 본문은 opt-in 여부를 명시하지 않으나(격리 조항 `L364` 만), 구현이 항상-가동인 것은 KPI의 본질(증분 5 집계가 undercount 되지 않음)과 정합. ✓

### F6. 회귀 테스트 감사 (test code IS audit subject)
- `test_successful…`: 전 필드 단정 + `len(calls)==1`. 레코드/필드 제거 시 fail(under-strict). ✓
- `test_every_gate_decision…`: `set(expected) == {d.value for d in WritingGateDecision}`(`test_writing_gate.py:504-506`)로 enum 전수 커버 확인 + parametrized 5 score. 잘못된 매핑·새 decision 미커버 시 fail(over-strict). ✓
- `test_provider_failure…`: parametrized `TIMEOUT`/`UNAVAILABLE`, outcome + `error_type=code.value` + status(504/502) + tokens=0 + decision/quality=None. ✓
- `test_parse_failure…`: outcome + `error_type="InvalidWritingGateResult"` + **tokens=2(실소비)** + quality=None. metered 전환의 값(mutation-A 가 정확히 이 단정을 물림). ✓
- `test_rejections…`: over-strict, 3 pre-call 케이스 `list_calls==()`. ✓
- `test_audit_write_failure…`: 격리(RuntimeError) under-strict. `test_audit_storage_failure_does_not_surface_as_a_503`: 격리(pymongo) over-strict, `skipIf _STORAGE_FAILURE is None`. 이 머신 pymongo present → 실행·통과. ✓
- assertion이 caller(KPI 집계)가 읽을 public surface(`StoredLlmCall` 필드)를 겨냥. 양방향 가드 충분. ✓

### F7. 공개 계약 무변 (gen:api)
- `frontend/src/api/schema.d.ts` 는 tracked. after 코드로 `npm run gen:api` 후 `git status --short frontend/` 빈 출력 → after dump == HEAD(clean).
- before(stash) dump vs after dump: `diff /tmp/openapi.before.json /tmp/openapi.now.json` → identical; `diff …/schema.before.d.ts …/schema.now.d.ts` → identical. **공개 스키마 무변 확정.** ✓

### F8. before/after 증분 + skip 차이의 정당화
- after: `1409 passed / 80 skipped / 593 subtests`. before(동일 머신·동일 조건): `1402 passed / 80 skipped / 584 subtests`. → **+7 passed / +9 subtests / skip 동일(80)**. 작업 AI 주장 "+7/+9, 설명되지 않는 증감 0" 정확히 재현. ✓
- 작업 AI 보고 절대값 `1485 / 4` 와 본 측정 `1409 / 80` 의 차이(76)는 **test-mongo 기동 여부**: 작업 AI 환경은 test-mongo 기동(MongoDB 의존 테스트 실행 → 4 skip), 본 환경은 test-mongo 미기동(동일 테스트 skip → 80 skip). `pytest -rs` 실측으로 80 skip의 내역을 확인했다 — 압도적 대다수(~74)가 MongoDB 의존(`requires a reachable MongoDB` / `no MongoDB reachable for integration tests` / `MongoDB deployment does not support transactions (needs a replica set)`), 나머지는 elasticsearch(~6)·chroma(~3). 즉 80−4≈76 = MongoDB 의존 테스트(test-mongo 미기동 시 skip, 기동 시 passed). **회귀 결함이 아니며**, 증분 +7/+9 는 양쪽 조건에서 동일하게 성립한다(skip 동일성 80==80 도 before/after 양쪽에서 재현).
- `subtests 593` 은 두 조건 모두 동일(신규 subtest 들은 pymongo/mongo 의존이 아님 — in-memory audit repo 사용). ✓

### F9. mutation 3종 실증 (회귀가 각 계약 결정을 보호함)

각 mutation 적용 → focused 회귀 → 역방향 원복(잔재 `diff` 없음 확인).

| 변이(계약 결정) | 코드 변경 | 기대 | 실측 |
|---|---|---|---|
| **A — 토큰 캡처** | success/parse의 `usage` → `None`(evaluate 가 `_usage` 폐기하는 효과) | 토큰 단정 2건 fail | `test_successful`(total_tokens 0≠2) + `test_parse_failure`(0≠2) **2 failed**, 42 passed ✓ |
| **B — 격리** | `_record_llm_call` 의 `try/except Exception` 제거 → 직접 `record()` | 격리 2건 fail | `test_audit_write_failure`(≠200) + `test_audit_storage_failure…`(**503≠200**) **2 failed**, 42 passed ✓ |
| **C — 레코드 조건** | `except ContextSearchFailed`(호출 전)에 `_record_gate_call` 추가 | over-strict 1 subtest fail | `test_rejections`(case=context_search_failed, 레코드 1건≠`()`) **1 subtest failed**, 44 passed ✓ |

세 mutation 모두 **정확히 해당 cell만** 물리고 무관 회귀는 green. 작업 AI 의 mutation 5종 중 핵심 3종(각 계약 결정에 1:1 대응)을 직접 재현했다. 나머지 2종(성공/실패 레코드 제거)은 `test_successful`(`len==1`)·`test_provider_failure`·`test_parse_failure` 가 레코드 존재를 전제 단정(`calls[0]` 인덱싱)하므로 레코드 제거 시 `IndexError` 로 fail함이 코드 리딩으로 자명(독립 mutation 미실행이지 lock 누락 아님).

## Issues / Risks

### Blocking (계약 의무 위반)
**없음.** 경계 매트릭스 9개 cell 전부 명명 회귀로 lock(빈 cell 없음). 리터럴 정합. 응답 무변. 공개 스키마 무변. mutation 3종이 정확히 해당 회귀만 물림. skip 차이는 조건 차이로 회귀 결함 아님.

### Hardening (non-blocking — spec-silent / 범위 밖 / dead-branch 정리)
1. **provider_error 의 `total_tokens=0` 이 계약에 명시 없음** — SoT `L362` outcome enum은 `provider_error` 를 정의하나 token 취급은 침묵. 코드는 usage 미전달→0(`main.py:3822`). provider 가 응답 전 실패(timeout/unavailable)라 토큰 없음이 자연스럽지만, 증분 5 집계에서 provider_error token을 0으로 셀지 제외할지를 계약에 명시하면 집계 의미론이 단단해진다(spec-silent 경향; 다만 outcome enum이 token 필드 의무조항을 정하지 않으므로 완전 gap은 아님 — 집계 시점 의사결정 후보).
2. **브리프 D2-A 설명(`observability-kpi-decisions.md:41`)이 본문(`system-contract-sot.md:363`)과 미세 불일치** — 브리프는 "severity findings + ERROR/WARNING 개수 반영"이라 하나, 본문/구현은 decision-only 거친 근사로 lock. v1.7.41 독립검증 H1이 정정·본문 명시(`L37` 변경이력에 근거). canonical은 본문이나, 브리프(설계기 문서)가 갱신되지 않아 drift. 이번 슬라이스 범위 밖(v1.7.41 잔여)이나 문서 정합 권장.
3. **endpoint except 절에 dead branch 잔재** — after에서 `except (WritingGateError, InvalidContextSearchRequest)→400`(`main.py:3793`, build try)에 `WritingGateError` 가 포함되나, `build_context_package`는 `WritingGateError`를 던지지 않는다(기존 `evaluate()`가 같은 try에 있을 때만 유효했던 분기). 또한 `except InvalidWritingGateResult→502`(`main.py:3819`)는 `evaluate_metered`가 `InvalidWritingGateResult`를 직접 던지지 않고 `MeteredCallError`로 감싸므로 도달 불가. 행동 무변이나 surgical 정리 후보. blocking 아님.
4. **mutation 5종 중 2종 미직접재현** — 작업 AI는 5종 실증을 보고했으나, 본 검증은 3종만 직접 재현. 나머지 2종(레코드 존재 제거)은 코드 리딩으로 자명(finding F9). lock 누락이 아니라 검증 범위의 선택.

## Verdict

**합격 (조건 없음).**

하중 이유:
1. 경계 매트릭스 9개 cell이 전부 명명 회귀로 lock — **빈 cell 없음**(CLAUDE.md "boundary matrix has no empty cells" 충족).
2. mutation 3종(token 캡처·격리 위치·레코드 조건 — 각 계약 결정에 1:1)이 정확히 해당 회귀만 물림 — **under-strict 가드 유효**.
3. over-strict 가드(score 매핑 전수·pre-call 미기록·pymongo 503 비샘) 존재 — 양방향 보호.
4. 공개 계약 무변(`openapi.json`·`schema.d.ts` identical) — 공개 스키마 lock.
5. 응답 무변(`evaluate→evaluate_metered`, `MeteredCallError` unwrap 동일 status+detail) — 기존 37 gate 회귀가 지킴.
6. before/after 증분 `+7/+9` 설명됨, skip 차이는 test-mongo 조건(회귀 결함 아님).

hardening 4건은 전부 non-blocking(spec-silent 집계 의사결정 / v1.7.41 잔여 drift / dead-branch 정리 / 검증 범위 선택).

## Outstanding items (오너 다음 단계에 영향)

- **working tree 미커밋**(`M` 4 + `??` work_log). 커밋 여부 오너 판단 대기 — 작업 AI가 "커밋 안 했습니다 — 하실까요?"로 물었고, 본 검증은 커밋하지 않았다.
- **라이브 확증 미수행**: 작업 AI가 제안한 내부 12B 모델로 gate 1회 태워 레코드가 실제 model/token을 수신하는지 라이브 확인 — 본 검증은 in-memory 더블(`_Provider`, `TokenUsage(1,1)`) 기반이라 라이브를 대체하지 않는다. 단 계약/회귀 lock으로 더블 경로의 정확성은 확보됐고, 라이브는 스택 기동 필요·HANDOFF 가 기동을 오너 몫으로 두는 상태라 별도 결정.
- **증분 4 잔여 호출부**(generation → planner → compare → extractor) — 후속. 각 서비스의 `*_metered` 변형 존재 확인이 선행(`generation_worker.py`·`revise_gate.py`·`per_stage_measure.py`·`gate_quality.py`에 metered 변형 확인됨).

## Reproduction

```bash
# focused (신규 7건 포함)
env -u CORE_SOT_MONGO_URI -u CORE_SOT_MONGO_DB \
  python3 -m pytest tests/test_writing_gate.py -q
# → 44 passed, 41 subtests

# 전체 after
env -u CORE_SOT_MONGO_URI -u CORE_SOT_MONGO_DB -u ELASTICSEARCH_URL \
  python3 -m pytest -q -p no:cacheprovider
# → 1409 passed, 80 skipped, 593 subtests  (이 머신, 2026-07-25, test-mongo 미기동)

# 전체 before (증분 +7/+9 검증)
git stash push -- services/application/app/main.py tests/test_writing_gate.py \
                   docs/system-contract-sot.md HANDOFF.md
env -u CORE_SOT_MONGO_URI -u ELASTICSEARCH_URL python3 -m pytest -q -p no:cacheprovider
# → 1402 passed, 80 skipped, 584 subtests
git stash pop

# gen:api no-diff (schema.d.ts tracked + clean 확인 후, before dump 비교)
(cd frontend && npm run gen:api)               # schema.d.ts clean 확인
git stash push -- services/application/app/main.py tests/test_writing_gate.py \
                   docs/system-contract-sot.md HANDOFF.md
(cd frontend && npm run gen:api)               # before dump
diff frontend/openapi.json   <(cat)            # /tmp 에 저장한 before snapshot과 identical
diff frontend/src/api/schema.d.ts <(cat)       # 동일
git stash pop && git checkout -- frontend/src/api/schema.d.ts

# mutation 3종 — 각각 Edit 적용 → focused pytest → 역방향 Edit 원복
#   A(토큰): main.py:3813/3830 의 usage=exc.usage/usage=usage → None
#   B(격리): main.py:1798-1806 _record_llm_call 의 try/except Exception 제거
#   C(레코드조건): main.py:3797 except ContextSearchFailed 에 _record_gate_call(..., started=0.0) 추가
#   각 후: env -u CORE_SOT_MONGO_URI python3 -m pytest tests/test_writing_gate.py -q
#   역방향 원복 후 diff /tmp/main.py.after services/application/app/main.py  (no diff)
```
