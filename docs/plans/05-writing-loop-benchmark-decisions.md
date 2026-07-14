# 착수 결정 브리프 — Phase 5.10 B2b Writing loop full-stack benchmark

상태: `Resolved — 2026-07-14 (B1~B4 승인·benchmark harness 구현)`

관련 정본: `docs/system-contract-sot.md` v1.6.81, `05-writing-loop-budget-decisions.md` M6, `05-writing-bounded-loop-decisions.md`, `flat-loop-gate.md` §Budget, `docs/benchmarks/2026-06-30/gemma_q4_llama_cpp_repeats3_warmup1.json`

## Decision needed

`WritingLoopPolicy.max_total_tokens|max_wall_clock_ms`의 production 기본값은 현재 `None`(off)이며, B2b는 full-stack Gemma Q4 환경에서 loop-level aggregate p95를 측정한 뒤 그 값을 기본 on으로 승격할지 결정해야 한다. 기존 정본은 측정할 loop 조합만 예시로 들 뿐, **어느 public 경계를 측정할지·어떤 종료 경로를 대표 workload로 삼을지·p95를 어떤 default로 변환할지**를 정하지 않았으므로, 이를 추측해 benchmark나 운영 설정을 구현할 수 없다.

## Resolution

- 오너 결정: **B1=A, B2=A, B3=A, B4=A**.
- `scripts/benchmark_writing_loop.py`는 deployed `/writing/revise-and-gate` HTTP POST를 측정하고, `persist_audit=true`로 만든 audit detail에서 aggregate `total_tokens`와 loop monotonic `wall_clock_ms`를 읽는다. audit GET은 계측 POST 지연에 섞지 않는다.
- 고정 fixture 세 개(`terminal_pass`, `retrieve_more_then_pass`, `max_structural_path`)는 요구하는 loop status/stage trace를 함께 가진다. 실모델이 요구 branch를 만들지 못하면 `unexpected_loop_trace` failure로 raw report에 남기며, 다른 branch의 비용을 성공 표본에 섞지 않는다.
- warmup 1회 성공은 버리고 failure는 보존한다. measured success 3회만 case p95/max token의 입력이며 failure는 별도 error code로 보고한다.
- 결과는 default-on 후보 ceiling의 근거일 뿐이다. **actual p95, failure rate, model/quant/compose revision을 본 뒤** 오너가 token/time 여유율과 `None`→default-on 승격을 별도 승인한다.

## 현재 확정된 사실

- 측정 대상 public flow는 `POST /projects/{project_id}/writing/revise-and-gate`이며, 정상 loop는 revise → report(필요 시 repair) → Gate를 수행한다. Gate의 `retrieve_more`는 retrieval planner → context search → Gate 재평가를 추가하고, structural cap은 revision 2 / retrieval 1 / Gate 3이다.
- aggregate `total_tokens`는 revise, report(+repair), Gate, retrieval planner(+repair)의 provider usage를 정확히 한 번씩 합산한다. `wall_clock_ms`는 loop service의 monotonic 측정값이다. 두 값은 opt-in persisted audit에만 저장되고 ephemeral HTTP response에는 노출되지 않는다.
- `max_total_tokens`는 post-accounting에서 누적 `> limit`이면 그 단계 결과를 채택하지 않는다. `max_wall_clock_ms`는 다음 provider/search 단계 직전에 deadline을 검사한다. 따라서 benchmark는 limits off 상태로 측정해야 실제 workload 분포를 자르지 않는다.
- 기존 single-turn benchmark의 재현 절차는 warmup 1회 + measured repeat 3회, success/failure를 분리 기록, p95와 max token을 보고한다. B2b는 동일 모델/quant 및 full-stack compose 환경에서 이 선례를 따른다.
- benchmark는 품질 평가나 prompt 튜닝이 아니다. strict parsing, HTTP status, persisted audit, Core SOT/Analysis write는 이 측정 slice의 pass/fail 대상이 아니다. 단, workload가 의도한 loop branch를 실제로 통과했는지는 기록해야 한다.

## Options table

### B1 — 계측 경계

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. deployed public HTTP (Recommended) | compose application의 `/writing/revise-and-gate`를 실제 HTTP로 호출하고 Mongo/Chroma/embedding/Gateway/llama를 모두 통과시킨다. | caller가 보는 전체 wall-clock과 실제 context path를 포함한다. production default의 근거와 가장 일치한다. | fixture seed/cleanup과 compose 준비가 필요하다. |
| B. application service 직접 호출 | `WritingReviseGateService.run()`만 process 내에서 호출한다. | 빠르고 failure 위치가 단순하다. | HTTP/context wiring과 deployed dependency latency를 빼므로 full-stack p95가 아니다. |
| C. Gateway provider turn 합산 | 기존 `benchmark_llm_provider.py`처럼 각 prompt만 별도 호출해 합친다. | 구현이 가장 작다. | repair·branch·context search와 실제 orchestration 시간을 재현하지 못한다. |

### B2 — 대표 workload set

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. terminal + retrieve_more + max structural path (Recommended) | (1) 첫 Gate terminal, (2) 첫 Gate `retrieve_more` 후 terminal, (3) revise 2 / retrieval 1 / Gate 3까지 도달하는 bounded path를 각각 별도 case로 측정한다. | 정상 fast path와 aggregate worst legitimate path를 모두 분리해 default 근거가 투명하다. | 모델 출력이 branch literal을 안정적으로 내도록 benchmark fixture/prompt control이 필요하다. |
| B. terminal + retrieve_more만 | 일반 성공과 retrieval 1회만 측정한다. | fixture가 작고 빠르다. | 허용된 두 번째 revise·세 번째 Gate 경로를 default 근거에서 누락한다. |
| C. max structural path만 | 가장 비싼 정상 경로 하나만 측정한다. | 보수적인 ceiling 산정이 쉽다. | 일반 요청의 분포를 잃고 default가 과도하게 커질 수 있다. |

### B3 — repeat / failure handling

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. warmup 1 + measured success 3, failure 별도 보고 (Recommended) | 기존 Gemma Q4 benchmark와 같은 최소 표본을 case별로 적용한다. branch mismatch, provider/parse/HTTP failure는 p95에서 제외하고 raw run·실패율로 남긴다. | 기존 숫자 근거와 비교 가능하며, 실패를 성공처럼 평균내지 않는다. | p95 표본이 작아 이후 운영 데이터로 재보정이 필요하다. |
| B. warmup 1 + success 10 | case별 10회 성공을 모은다. | p95 안정성이 높다. | GPU 점유와 실행 시간이 커진다. |
| C. 모든 run(실패 포함) 평균 | success/failure를 하나의 latency 수치로 요약한다. | 단일 숫자가 나온다. | timeout/parse 오류가 정상 예산으로 섞여 production default 의미가 무너진다. |

### B4 — p95에서 production default로의 승격

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. p95 기반 여유 ceiling을 기본 on (Recommended) | case별 p95를 기록하고, max structural-path p95에 명시적 여유율을 적용한 token/time ceiling을 제안한다. 숫자와 여유율은 결과를 본 뒤 owner가 승인한다. | 한도 도입 근거가 명확하고 정상 bounded path를 덮는다. | B2b 실행 후에도 최종 숫자/여유율 승인 단계가 한 번 남는다. |
| B. p95를 그대로 기본 on | 최고 측정 p95를 곧바로 env default로 넣는다. | 단순하다. | 작은 표본/환경 변동에서 정상 요청을 과도하게 차단할 수 있다. |
| C. 결과만 기록하고 off 유지 | benchmark report만 남기고 default `None`을 유지한다. | 운영 동작을 바꾸지 않는다. | B2b의 "production 숫자 확정" 목적을 다음 작업으로 미룬다. |

## Recommendation + reason

**B1=A, B2=A, B3=A, B4=A**를 권장한다.

현재는 로컬 1인 프로젝트이지만 aggregate cap은 user-visible partial result를 중단시킬 수 있는 운영 경계다. 그러므로 provider turn을 인위적으로 합산하지 말고 deployed public HTTP full-stack path를 측정해야 한다. 세 workload는 fast path와 허용된 가장 긴 정상 path를 혼동하지 않게 하며, 기존 1 warmup/3 measured 선례를 재사용해 GPU 비용을 제한한다. 다만 3회 p95만으로 원본 숫자를 즉시 강제하면 과도하게 촘촘해질 수 있으므로, benchmark는 후보 ceiling과 근거를 만들고 **최종 기본 숫자 및 여유율은 결과 확인 후 owner가 승인**하는 두 단계로 둔다.

## Follow-up considerations

- 결과 report는 `--model`·`--quant`·`--compose-revision`의 필수 operator 입력, endpoint, case fixture hash, warmup/repeat, raw per-run aggregate tokens/wall-clock, branch/stage trace, success/failure, case별 p95/max를 보존한다. application이 이 provenance를 public health surface로 제공하지 않으므로 harness가 환경을 추측하지 않는다.
- B4 승인 후에만 `WRITING_LOOP_MAX_TOTAL_TOKENS`와 `WRITING_LOOP_MAX_WALL_CLOCK_MS`의 default/Compose/SoT를 함께 바꾸고, default-on과 explicit-off의 양방향 회귀를 추가한다.
- 실제 운영에서 prompt/model/quant/context backend가 바뀌면 이 benchmark를 재실행한다. aggregate budget 값은 모델 품질 점수가 아니다.

## Deferred / out of scope

- multi-finding revise, stable ContextPackage pointer, persisted audit retention/TTL, per-stage usage 공개.
- Gate/retrieval planner prompt의 품질 튜닝 및 JSON parse failure 수정.
- Context Gate의 search/context budget 재설계, generic `AgentLoopRunner`과 Writing loop budget 통합.
- B2b 결과 전 production default를 임의로 on으로 바꾸는 작업.

## Approval → execution outline

1. `scripts/benchmark_writing_loop.py`와 deterministic seeded project/context fixture를 추가하고, selected public HTTP cases의 branch/stage assertion을 unit-test로 잠근다.
2. full-stack machine에서 warmup 1 + measured repeat 3을 실행해 `docs/benchmarks/YYYY-MM-DD/`에 raw report를 저장한다.
3. report의 p95/max와 failure rate를 검토하는 owner decision brief로 B4 숫자·여유율·off→on 여부를 확정한다.

## Live execution

1. full-stack Compose를 올린 뒤 `POST /projects`로 benchmark 전용 project를 하나 만든다. harness는 계측 전 해당 project에 결정적 context draft/version을 seed하고 그 `current_position`을 모든 loop 요청에 보낸다. benchmark는 audit record를 append-only로 남기므로, 일반 작업 project는 사용하지 않는다.
2. application host에서 아래를 실행한다. 기본은 B3의 warmup 1 / measured 3이다.

   ```bash
   mkdir -p docs/benchmarks/YYYY-MM-DD
   python3 scripts/benchmark_writing_loop.py \
     --application-base-url http://127.0.0.1:8000 \
     --project-id <benchmark-project-id> \
     --model <served-model-id> \
     --quant <quantization> \
     --compose-revision "$(git rev-parse HEAD)" \
     > docs/benchmarks/YYYY-MM-DD/writing_loop_b2b.json
   ```

3. 세 case 모두 성공 표본 3개인지, `unexpected_loop_trace`/provider/parse failure가 없는지 먼저 확인한다. failure가 있으면 p95를 default 근거로 승격하지 않고 해당 raw report와 함께 모델/fixture 원인을 검토한다.
