# Verification — Phase 5.10 Option A (M-i) per-stage 측정 도구 (SoT v1.6.87)

## Subject metadata

- **Date**: 2026-07-15
- **Requester**: owner ("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?")
- **Verifier**: independent audit (this session)
- **Target slice/artifact**: B2b ceiling Option A 의 **측정 메커니즘 M-i** 구현
  - `services/application/app/writing/per_stage_measure.py` (`run_per_stage_measurement` + `StageSample`/`PerStageMeasurement`)
  - `scripts/measure_writing_stages.py` (operator CLI)
  - `tests/test_writing_per_stage_measure.py` (회귀 10)
- **Canonical spec reference**: `docs/plans/05-writing-loop-ceiling-composition-decisions.md` (결정 브리프, "측정 메커니즘 sub-decision M-i" §) + `docs/system-contract-sot.md` v1.6.87 row (line 36). 종속 합성 코어 정본: `scripts/benchmark_writing_loop.py:418-467` (`_TOKEN_STAGES`/`_WALL_CLOCK_STAGES`/`worst_case_stage_counts`/`compose_worst_case_ceiling`, v1.6.86, 독립 검증 PASS `docs/verifications/2026-07-14/writing_loop_ceiling_and_fence_hardening.md`).
- **Source of work being verified**: working tree, uncommitted (git status: 3 untracked files + doc edits; HEAD = `18f0786`).

## Scope

Canonical contract scope (chain from the brief, widened only along cross-references the brief itself makes):

1. **측정 코어 계약** — `per_stage_measure.py`: 5 stage(revise/report/gate/retrieve_plan/context_search) 격리 측정(`TokenUsage`+`perf_counter`); `context_search` token 제외(항상 0)·wall-clock만; `retrieve_plan` 합성 `retrieve_more` Gate; `repeats`간 보수적 MAX; stage fault→`incomplete_stages`; 쓰기 0.
2. **CLI 계약** — `measure_writing_stages.py`: production seam 조립 → 실 gateway 측정 → 측정 dict → `compose_worst_case_ceiling`(env 정책) → raw ceiling JSON.
3. **합성 동형성** — 측정 결과가 합성 코어 `_TOKEN_STAGES`/`_WALL_CLOCK_STAGES` 경계와 정확히 일치.
4. **경계 불변식 종속** — `context_search` token 제외가 의존하는 `revise_gate.py` 직접 호출 구조 + loop-level tripwire lock.
5. **회귀 품질** — 10개 테스트의 under/over-strict guard, 공개 표면 타격.
6. **문서 정합** — SoT v1.6.87 row, 결정 브리프, CHANGELOG, HANDOFF.

Out of scope: live 12B per-stage 수치 수집 자체(sandbox 밖 풀스택, 오너 후속), B4 여유율/default-on 승인, v1.6.86 합성 코어 자체(이미 독립 검증 PASS — 종속성만 확인).

## Methodology

계약 스코핑 → 경계 매트릭스 구축(모든 should-fire/should-NOT-fire branch + literal) → 구현/테스트를 **반박 대상 가설**로 취급해 1차 소스에서 재도출. 모든 claim에 `file:line` 인용.

실행한 명령(전부 재현 가능):
- `git status --short` / `git diff --stat` / `git log --oneline -8`
- `python3 -m py_compile services/application/app/writing/per_stage_measure.py scripts/measure_writing_stages.py tests/test_writing_per_stage_measure.py`
- `PYTHONPATH=. python3 -m pytest tests/test_writing_per_stage_measure.py -q`
- `PYTHONPATH=. python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` (프로젝트 **정규** 명령, HANDOFF:22·137)
- `PYTHONPATH=. python3 -m pytest tests/ -q` (비정규 — Mongo 통합 포함, 비교용)
- `PYTHONPATH=. python3 -m pytest tests/test_memory_mongo.py -q` (실패 원인 분리)
- `docker compose config --quiet`; `git diff --check`
- `docker ps` (스택 가용성)
- 코드 정독: `per_stage_measure.py`·`measure_writing_stages.py`·`benchmark_writing_loop.py:408-467`·`revise_gate.py:244-267,440-494`·`retrieval.py:100-200`·`tests/test_writing_per_stage_measure.py`·`tests/test_writing_loop_budget.py:200-241`·`provider.py:13-19`·`revise_gate.py:101-114`

## Findings

### F1. 측정 코어 — 5 stage 격리 측정 + token/wall-clock 분리 (CONFIRMED)

`per_stage_measure.py:177-241` `_measure_once` 가 context→revise→report→gate→retrieve_plan 순으로 각 stage를 `timed_metered`(`:201-216`)로 감싸 `usage.total_tokens`+wall-clock을 기록. token 기여 stage는 `revise_metered`/`enrich_metered`/`evaluate_metered`/`plan_metered` variant 사용(`:229-241`) — 이는 loop `metered()`(`revise_gate.py:247-267`)가 `method+"_metered"` variant를 선호하는 channel과 **동일**. `TokenUsage.total_tokens`=`prompt+completion`(`provider.py:18-19`)로 revise 30+20=50 등 산출 일치. 회귀 `test_each_stage_measured_with_token_and_wall_clock`(`test_writing_per_stage_measure.py:160`)가 token+wall-clock 양쪽 단언. **boundary cell 채움**: token/wall-clock 캡처 ✓.

### F2. `context_search` token 제외 (always 0)·wall-clock만 — 동형성 CONFIRMED [load-bearing]

3중 교차검증:
1. **loop 경계**: `revise_gate.py:482` `await self._context_search.build_context_package(...)` — `metered(self._context_search,"build_context_package",...)`가 **아님**. 주석(`:474-481`)이 "Called directly (NOT via metered())"로 명시. `metered()`만이 `accumulated`에 usage를 더하는 유일한 channel(`:264`)이므로, context_search usage는 구조상 aggregate에 도달 불가.
2. **합성 코어**: `benchmark_writing_loop.py:418` `_TOKEN_STAGES=("revise","report","gate","retrieve_plan")` — context_search 제외; `:419` `_WALL_CLOCK_STAGES`는 context_search **포함**.
3. **측정 구현**: `per_stage_measure.py:224-227` context_search sample `total_tokens=0` 하드코딩; `:294` `if sample.stage in _TOKEN_STAGES` 로 token dict에서 context_search 배제.

**loop-level tripwire lock 존재+bite 실증**: `test_writing_loop_budget.py:214` `test_context_search_usage_excluded_from_aggregate_tokens` — `_MeteredContext`가 bare method **와** 999-token `_metered` variant **모두** 노출하고, `total_tokens==22`(999 제외)+`metered_calls==0`을 단언. 누군가 context_search를 metered()로 돌리면 999가 aggregate로 → 1021 → 실패. 브리프 "22→1021로 bite" 주장 그대로. **boundary cell 채움**: token 제외 under-strict(`test_context_search_excluded_from_token_budget:174` over-strict wall-clock 포함 단언) ✓.

### F3. `retrieve_plan` 합성 `retrieve_more` Gate — 유효 입력 CONFIRMED [load-bearing]

`_synthetic_retrieve_more_gate`(`per_stage_measure.py:151-174`)가 `decision=RETRIEVE_MORE` + 1개 finding(`recommended_decision=RETRIEVE_MORE`, `evidence=candidate.text[:32]`) 생성. planner `plan_metered`(`retrieval.py:107-126`) 계약:
- `:115` `gate.decision is not RETRIEVE_MORE`면 raise → 합성 gate 통과 ✓
- `:119-122` `recommended_decision is RETRIEVE_MORE`인 finding ≥1 요구 → 1개 존재 ✓
- evidence containment check **없음** — `:180-188` payload에 `finding.evidence`를 그대로 담아 provider에 전달만 함. 브리프/코어 docstring "generic finding suffices" 주장 확인.

실 loop에서는 `retrieve_plan`이 `metered(planner,"plan",...,gate=last_gate)`(`revise_gate.py:462-466`)로 실 gate를 받으나, 측정에서는 Gate 독립성(live 0/12) 회피를 위해 합성 gate로 planner를 **독립** 구동 — Option A 전제와 정합. 단, GATE_STAGE 자체(`:235`)는 **실 gate**를 실 candidate로 측정(합성 gate는 retrieve_plan 입력용으로만 사용). **boundary cell 채움**: `test_retrieve_plan_fed_synthetic_retrieve_more_gate:182` 가 planner가 받은 gate의 decision/finding 단언, len(seen_gate)==1 over-strict ✓.

### F4. 합성 공식 — 브리프와 정확 일치 CONFIRMED

`worst_case_stage_counts`(`benchmark_writing_loop.py:422-439`): `gate=min(G,1+(R-1)+T)`, `revise=report=R`, `retrieve_plan=context_search=T`. `compose_worst_case_ceiling`(`:442-467`): `max_total_tokens`=Σ over `_TOKEN_STAGES`(context_search 제외), `max_wall_clock_ms`=Σ over `_WALL_CLOCK_STAGES`(context_search 포함). 브리프 "합성 공식" §(`05:30-41`)와 **literal 일치** — 내부 모순 없음. 기본 정책(R=2,T=1,G=3) → n_revise=2,n_report=2,n_gate=3,n_retrieve_plan=1,n_context=1. `WritingLoopPolicy` 기본값(`revise_gate.py:112-114`) 2/1/3 확인. 회귀 `test_composes_into_default_policy_ceiling:222` 가 tokens=2·50+2·65+3·80+1·30=500, ms=(2+2+3+1+1)·1000=9000 산출·단언. **boundary cell 채움** ✓.

### F5. `repeats` 보수적 MAX + stage fault→incomplete CONFIRMED

- MAX: `run_per_stage_measurement:290-296` 각 pass별 `max(stage_tokens.get(stage,0), sample.total_tokens)`. 회귀 `test_conservative_max_across_repeats:195` — Alternating reviser(100→10) → MAX=100. **양방향**: under-strict(last=10이면 실패), over-strict(sum=110/mean=55이면 실패). docstring 명시 ✓.
- fault: `_measure_once:205-208` MeteredCallError/Exception → `_StageMeasurementError`; `run_per_stage_measurement:280-285` break + completed pass 보존; `:298-299` `incomplete = stage not in stage_ms`. 회귀 `test_stage_fault_surfaced_and_marked_incomplete:210` — report fault → error_stage=REPORT, report/gate/retrieve_plan incomplete, context_search+revise **not** incomplete(over-strict). MeteredCallError의 `exc.cause` 추출 경로(`:205-206`)도 이 테스트로 실제 관통 ✓.

### F6. 쓰기 0 (read-only core) CONFIRMED

코어가 받는 collaborator = 5개 stage service만(Protocol `:76-106`). Core SOT/memory/audit/outbox 객체는 `run_per_stage_measurement` signature에 없음. 회귀 `test_no_write_path_reached:237` 가 각 spy 정확히 1회 호출 단언. CLI `build_services`는 memory/sync_outbox/analysis를 **조립**하나(`measure_writing_stages.py:112-121`) 이는 context_search service 생성용이고 측정 자체는 read-only. 단, CLI는 `--current-position` 미주어 시 `seed_context`(`:162`)로 benchmark context draft를 **idempotent** seed — 이는 gate/report 진단 선례와 동형이며 브리프/SoT가 명시적으로 인지(측정 코어의 no-write와는 구분). **boundary cell 채움** ✓.

### F7. 회귀 10 — under/over-strict 품질 감사 PASS

10개 테스트 전부 under-strict guard(bug 재도입 시 재실패) 보유. over-strict 명시: test 2(context_search wall-clock 보존), test 4(MAX not sum/mean/last), test 5(fault 범위 not over-broad), test 3(seen_gate==1). assertion이 내부 helper가 아닌 공개 표면(`PerStageMeasurement.stage_tokens`/`stage_ms`/`incomplete_stages`/`error`, CLI JSON `ceiling`)을 타격. `repeats<1→ValueError`(`test_repeats_must_be_positive:265`), `measurement_to_dict` 6-key 숫자 shape(`test_measurement_to_dict_is_json_numeric_only:254`), CLI wiring(`test_main_prints_measurement_and_ceiling:271`, fake_run으로 gateway 미접촉) 모두 계약 대응.

**경계 매트릭스 빈 cell 없음** — 계약이 요구하는 모든 should-fire/should-NOT-fire branch가 회귀에 대응.

### F8. 재현 — 작업 AI claim 전부 독립 확인

| claim | 결과 |
|---|---|
| focused 10 passed | `10 passed in 1.05s` ✓ |
| full 1051/45/235 | 정규 명령 `--ignore=tests/test_memory_mongo.py` → `1051 passed, 45 skipped, 235 subtests` ✓ (정확 일치) |
| py_compile | OK ✓ |
| `docker compose config` | `--quiet` exit 0 ✓ |
| `git diff --check` | clean ✓ |

### F9. 스택 상태 (live 실행 불가 확인)

`docker ps`: `worker`, `chroma`, `mongodb`, `shared-mongo`만 up, **`application` 컨테이너 부재**. 따라서 `docker compose run --rm --no-deps application python scripts/measure_writing_stages.py ...` live 실행은 본 환경에서 불가 — 작업 AI "남은 것(오너, sandbox 밖 풀스택)" 진술과 정합. memory(`verify-machine-state-before-claiming-blocked`)에 따라 직접 `docker ps`로 기계 상태 확인한 결과.

## Issues / Risks

### Blocking (계약 의무 위반)

**없음.** 경계 매트릭스의 모든 계약-요구 branch가 회귀 lock으로 대응하고, 합성 동형성 3개 load-bearing claim이 1차 소스에서 확인됐으며, 작업 AI claim이 정규 명령으로 재현됐다.

### Hardening recommendations (비차단, 계약 초과)

- **H1 (문서 완결성)**: SoT v1.6.87 row(`system-contract-sot.md:36`)는 정확하나, **v1.6.86 row(`:37`)**는 동일 버전(`18f0786`)에 포함된 B2b ceiling 합성 코어(`worst_case_stage_counts`/`compose_worst_case_ceiling`)를 언급하지 않고 parser fence-strip만 기술. commit message + 독립 검증 기록(`docs/verifications/2026-07-14/writing_loop_ceiling_and_fence_hardening.md`)이 커버하므로 영향 없으나, 버전 로그가 같은 버전의 두 slice 중 하나를 누락. v1.6.87 row가 "v1.6.86 합성 코어"를 역참조하므로 독자가 v1.6.86 row에서 근거를 찾지 못함.
- **H2 (CLI env→policy wiring 미측정)**: `_policy_from_env`(`measure_writing_stages.py:132-144`)가 `WRITING_LOOP_MAX_{REVISION_ROUNDS,RETRIEVAL_ROUNDS,GATE_EVALUATIONS}` env→`WritingLoopPolicy`로 읽으나, `test_main_prints_measurement_and_ceiling`이 `fake_run`을 써 이 경로를 관통 안 함. 브리프 follow-up "상한이 env로 조정 가능 → 자동 재도출"을 부분적으로만 lock. 단순 `int(os.environ.get(...))`라 위험 낮으나 CLI wiring으로는 미측정.
- **H3 (first-stage fault edge 미측정)**: 회귀는 REPORT(중간 stage) fault만 covering. context_search(첫 stage) fault 시 전 stage incomplete 경로는 일반 fault 메커니즘(F5)으로 커버되나 명시적 케이스 없음.
- **H4 (cosmetic `model` 필드)**: `StageSample.model=getattr(value,"generated_by_model",None)`(`per_stage_measure.py:214`) — reviser/reporter/planner 반환값은 이 attr이 없을 가능성(오직 gate result가 `evaluated_by_model` 보유). 따라서 `model`은 gate를 제외하면 대부분 None. ceiling 산출(token/ms만 사용)에 영향 없으므로 cosmetic.
- **H5 (live real-gateway 미관통 — acknowledged)**: `build_services`의 실 provider 호출 경로는 자동화 테스트가 없고 live 미실행(오너 sandbox-外 후속). 브리프가 명시적으로 scope 밖으로 둔 항목이므로 slice gap 아님.
- **H6 (가장 실효적 — CLI가 incomplete 상태에서 ceiling을 무조건 합성)**: `measure_writing_stages.py:191-194` `_run`이 `incomplete_stages`를 점검하지 않고 `compose_worst_case_ceiling`을 무조건 호출. `compose_worst_case_ceiling`(`benchmark_writing_loop.py:457-462`)이 `stage_tokens.get(stage, 0)`를 쓰므로, fault로 빠진 stage는 **자동으로 0** 기여 → `ceiling.max_total_tokens`/`max_wall_clock_ms`가 **과소 산출**됨. 코어 docstring(`per_stage_measure.py:130-134`) 자체가 "operator must not compose a ceiling from an incomplete set (it would silently under-bound)"라고 명시. 현재 gap은 `measurement` sub-dict(`incomplete_stages`/`error`/`error_stage`, `:204`)에 노출되므로 full-output 수준에서는 silent 아님. 그러나 `ceiling` 키(`:205`) 자체에 completeness flag가 없어, `ceiling.max_total_tokens`만 읽는 operator는 under-bound(→ production `WRITING_LOOP_MAX_TOTAL_TOKENS` 과소 설정 → 루프가 유효 트래픽에서 `BUDGET_EXHAUSTED` 조기 발생, fails-closed 방향)을 놓칠 수 있음. 방어안: ceiling 출력에 `incomplete: bool`(또는 `complete: bool`) 추가, 혹은 incomplete 시 `ceiling=null` + 경고. **비차단 사유**: brief가 incomplete 점검을 "operator" 책임으로 위임하고, 데이터는 surface 되며, 실패 방향이 closed(과소→조기 거부)라 안전 쪽. 단 이 도구의 산출물이 production default 근거라 footgun 방어 가치가 높음.

### Reporting note (결함 아님 — future verifier 혼란 방지)

`pytest tests/`를 **정규 `--ignore=tests/test_memory_mongo.py` 없이** 실행하면 `test_memory_mongo.py` 4개가 `MongoMemoryRepositorySetupError: failed to create required memory MongoDB indexes`(unique index `uniq_memory_candidate_promotion` 생성 `OperationFailure`)로 실패. 이는 (a) memory subsystem로 v1.6.87이 전혀 건드리지 않음(git status로 증명), (b) 공유 Mongo 컨테이너 index state에 의존(격리 실행에서도 동일 실패), (c) 프로젝트 정규 명령이 의도적 제외 대상(HANDOFF:22·137 "skip은 대부분 live Mongo 미가용 통합"). 작업 AI의 "full 1051 passed"는 정규 명령 기준이며 **정확**. 본 verifier도 최초 비정규 명령으로 4 실패를 발견해 오보로 오해했으나, HANDOFF 정규 명령 확인 후 정정.

## Verdict

**PASS (조건 없음).**

이유:
1. 경계 매트릭스에 빈 cell 없음 — 계약 요구 branch 전부 회귀 lock.
2. load-bearing 동형성 3건(context_search token 제외·retrieve_plan 합성 gate·합성 공식)이 1차 소스(`revise_gate.py:482`, `retrieval.py:115-126`, `benchmark_writing_loop.py:418-467`)에서 확인, loop-level tripwire(`test_writing_loop_budget.py:214`)가 bite 실증.
3. 측정 코어가 read-only(no-write)이며 token/wall-clock 분리가 합성 코어 경계와 정확 일치.
4. 작업 AI의 모든 claim(focused 10 / full 1051·45·235 / py_compile / compose config / diff --check)이 프로젝트 **정규 명령**으로 독립 재현.
5. 비차단 hardening 6건(H6=CLI incomplete 시 무조건 합성이 가장 실효적)은 모두 계약 초과 영역.

## Outstanding items

- **live per-stage 수집 (오너, sandbox 밖 풀스택)**: 풀스택 기동 후 `docker compose run --rm --no-deps application python scripts/measure_writing_stages.py --project-id <id> --repeats 3` → CLI `ceiling` JSON(raw 최악경로) → B4 여유율 얹어 `WRITING_LOOP_MAX_TOTAL_TOKENS|MAX_WALL_CLOCK_MS` default-on 승인. 측정 **도구 자체**는 결정적 회귀로 잠겨 live 불요; 새 CLI/JSON 출력 계약이라 live 1회 관통으로 출력 형상 확인 권장.
- **Mongo index 실패 (별도 subsystem, environmental)**: 공유 컨테이너의 `uniq_memory_candidate_promotion` index state. v1.6.87 무관이나 오너가 정규 run에 포함하길 원하면 별도 조치 필요.

## Reproduction

```bash
# 1. 컴파일
python3 -m py_compile services/application/app/writing/per_stage_measure.py \
  scripts/measure_writing_stages.py tests/test_writing_per_stage_measure.py

# 2. focused 회귀
PYTHONPATH=. python3 -m pytest tests/test_writing_per_stage_measure.py -q

# 3. 정규 full suite (작업 AI claim 재현)
PYTHONPATH=. python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider
#   → 1051 passed, 45 skipped, 235 subtests passed

# 4. 계약 정합/동형성 정독 (1차 소소)
#    per_stage_measure.py:151-303, measure_writing_stages.py:69-206,
#    benchmark_writing_loop.py:418-467, revise_gate.py:244-267 & 440-494,
#    retrieval.py:107-126, test_writing_loop_budget.py:214-241

# 5. 정합/설정 검사
docker compose config --quiet && git diff --check
```
