# Work Log — 2026-07-14

## Goals

- `HANDOFF.md`가 지정한 다음 Writing 작업(B2b full-stack loop-level benchmark)을 정본과 대조해 착수 가능 상태로 만든다.

## Completed work

- `docs/system-contract-sot.md` v1.6.80, `05-writing-loop-budget-decisions.md` M6, `flat-loop-gate.md`의 기존 single-turn benchmark 절차, 현재 `/writing/revise-and-gate` loop 경계를 대조했다.
- `docs/plans/05-writing-loop-benchmark-decisions.md`를 작성했다. benchmark의 public/deployed 경계, terminal·retrieve_more·최대 structural path workload, warmup/repeat와 failure 분리, p95를 production ceiling으로 승격하는 방식 B1~B4를 owner 결정으로 분리했다.
- `docs/plans/README.md`에 브리프를 추가하고, `HANDOFF.md`의 현재 blocker와 다음 작업을 B2b 승인 대기 상태로 갱신했다.

### Phase 5.10 B2b benchmark harness 구현 (SoT v1.6.81)

- 사용자 승인: **B1=A/B2=A/B3=A/B4=A**. deployed public HTTP, terminal/retrieve_more/max structural path 세 case, warmup 1+measured success 3 및 failure 분리, p95 결과 확인 뒤 default-on/여유율 추가 승인을 채택했다.
- `scripts/benchmark_writing_loop.py`를 추가했다. `/writing/revise-and-gate` POST의 caller-observed latency를 측정하고 `persist_audit=true` audit detail에서 aggregate token 및 loop monotonic wall-clock을 읽는다. audit GET의 비용은 POST latency에 포함하지 않는다.
- 모델이 의도한 branch 대신 다른 loop를 내면 `unexpected_loop_trace`로 raw report에 보존하고 p95 성공 표본에서 제외한다. report는 immutable fixture SHA-256, raw stage trace, HTTP status/error, aggregate 수치를 남긴다.
- `tests/test_writing_loop_benchmark_script.py`에 persisted-audit 계측, trace mismatch under-strict guard, warmup 제외, success-only p95, fixture hash, CLI import/wiring을 추가했다.
- benchmark procedure를 Resolved로 전환하고 SoT v1.6.81·CHANGELOG·HANDOFF에 승인 근거와 live 실행 후 남은 숫자 결정을 반영했다. aggregate env default는 계속 `None`(off)다.

### 독립 검증 B1 closure 및 report provenance 보강

- 독립 검증 기록 `docs/verifications/2026-07-14/b2b_writing_loop_benchmark_harness.md`를 1차 사료(브리프·harness·테스트·선례 benchmark test)와 대조했다. B1의 지적대로 기존 이름과 달리 warmup success만 검증해 `if not run.success: runs.append(run)` 분기에는 under-strict guard가 없었다.
- warmup HTTP 503이 `iteration=0`, `success=false`, `error_code="http_503"` raw run으로 보존되고, 이어지는 measured iteration도 기록되는 회귀를 추가했다. warmup 성공은 제외되는 기존 guard와 함께 양방향을 잠근다.
- H1을 보강했다. application이 runtime model/quant/Compose revision을 authoritative public surface로 제공하지 않으므로 환경 추측 대신 `--model`, `--quant`, `--compose-revision`을 required CLI provenance로 추가해 report metadata에 기록한다.
- H3/H4를 함께 보강했다. HTTP 502와 audit-missing envelope이 raw failure run으로 변환되는지 end-to-end로 확인하고, 기존 exact POST-only latency assertion을 유지했다. independent verification의 역사적 conditional-pass record는 수정하지 않았으며 B1 closure의 독립 재검증은 후속이다.

### 독립 재검증 PASS 확인

- 같은 검증 기록의 재검증 섹션이 B1 분기 제거 시 `test_warmup_http_failure_is_retained_and_measured_run_continues`가 RED가 되고, 복원 후 GREEN이 되는 mutation 증거를 남겼음을 확인했다. verdict는 conditional pass에서 **PASS**로 상향됐다.
- 재검증 기록의 H1(모델/quant/compose revision 누락)은 해당 검증 시점의 관찰이다. 현재 `scripts/benchmark_writing_loop.py`는 `--model`/`--quant`/`--compose-revision`을 required CLI로 받고, `build_report()` metadata 및 회귀가 세 값을 직접 잠근다. 따라서 live report provenance contract는 현재 working tree에서 충족한다.
- 남은 것은 code defect가 아니라 full-stack live benchmark와 B4 production ceiling 수치 승인이다. 검증 기록은 독립 사료이므로 과거 H1 관찰을 재작성하지 않고, 현재 상태는 HANDOFF와 이 work log에 기록한다.

### B2b full-stack 실행 및 context seed 보완

- 사용자 지시로 전용 Compose Mongo replica set을 유지했다. shared Mongo는 writable standalone(`setName` 없음)이어서 기본 transaction 경로를 재현하지 못하며, 별도 컨테이너와 충돌하지 않도록 이 stack의 host gateway/Mongo 포트를 각각 `8011`/`27019`로 매핑했다. 외부 llama는 `http://192.168.1.22:9080`, served model은 `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`임을 `/health`와 `/v1/models`로 확인했다.
- 첫 live harness 실행은 `current_position is required for current_scene, recent_scenes` HTTP 400만 기록했다. 원인은 harness가 B2b 브리프의 deterministic context fixture 요구를 구현하지 않은 것이었다.
- `scripts/benchmark_writing_loop.py`가 benchmark 전용 project에 draft/version을 seed하고 그 실제 `current_position`을 모든 POST에 전달하도록 보완했다. seed setup은 caller-observed POST latency 밖에 두고, report metadata에 position을 남긴다. 회귀는 current_position forward와 draft→version seed 순서를 직접 잠근다.
- 보완 뒤 live 요청은 remote gateway까지 도달했으나 `/writing/revise-and-gate`가 HTTP 502로 종료했다. 따라서 p95/max 성공 표본은 0이며 production aggregate default는 계속 off다. 비어 있는 생성 report는 남기지 않았다.
- 502 audit 진단: persisted audit 목록에서 provider token(대체로 1,600~3,100)이 실제 기록됐고, 최근 run은 `revise`·`report` 완료 뒤 `gate` stage만 failed, `error_type="invalid_gate_result"`였다. 일부 run은 `invalid_writing_revision` 또는 `invalid_candidate_report`였지만, dominant failure는 Gate의 strict JSON/enum/priority/evidence validation이다. 따라서 권한 오류가 아니라 remote 12B의 structured Gate 출력 적합성 문제로 분류한다.
- 권한/연결 가설도 직접 대조했다. gateway의 `LLAMA_BASE_URL`과 `LLAMA_DEFAULT_MODEL`은 remote `/v1/models`의 served id와 정확히 같고 `/health/ready`가 `ready`다. application은 전용 `mongodb://mongo:27017/?replicaSet=rs0` + transactions=true를 사용하며 project/draft/version/audit write가 실제 성공했다. remote auth·model-id mismatch·Mongo write permission은 이번 502의 원인이 아니다.

## Issues found

- SoT v1.6.80과 M6는 B2b가 필요하다는 사실과 예시 loop 조합만 확정한다. deployed HTTP 여부, representative branch set, failure를 p95에서 처리하는 방식, p95를 env default로 바꾸는 권한은 정하지 않는다.
- 이 항목들을 임의로 정하면 benchmark가 production default의 근거를 사실상 결정하게 되므로 owner-level 결정 없이 script/fixture나 default-on 변경을 시작할 수 없다.
- B2b 실제 계측을 시도하기 전에 로컬 runtime을 확인했다. `docker compose ps`는 service 0개였고 `curl -sS --max-time 5 http://127.0.0.1:8000/health`는 connection refused였다. 따라서 이 workspace에는 full-stack application/Gateway/LLM이 실행 중이지 않다. 대형 모델 다운로드·GPU runtime 기동을 이 작업에서 추측 실행하지 않았으며, live report는 준비된 full-stack machine에서 수행해야 한다.
- full-stack을 기동한 실제 실행에서는 context seed 보완 전 400, 보완 후 HTTP 502가 발생했다. 성공 표본이 없으므로 B2b report를 ceiling 근거로 승격할 수 없다.

## Decisions

- 작업자 추천: deployed public HTTP full-stack 경계, terminal/retrieve_more/max-structural-path 세 case, warmup 1 + measured success 3(실패 별도 보고), 결과 확인 후 owner가 여유 ceiling과 default-on 여부를 승인하는 B1=A/B2=A/B3=A/B4=A.
- 사용자 결정: B1=A/B2=A/B3=A/B4=A를 승인했다. benchmark의 trace mismatch는 failure로 남기고, live p95/failure rate를 보기 전 aggregate default 값을 켜지 않는다.
- 사용자 결정: shared Mongo가 standalone이라도 별도 Mongo를 더 띄우지 말자는 대안 대신, 정본의 transaction 기본 경로를 지키기 위해 이미 기동한 전용 replica-set Mongo를 사용한다.

## Next steps

- remote 12B live의 `/writing/revise-and-gate` HTTP 502 body와 strict revise/report/Gate failure stage를 분리 진단한 뒤, 세 workload의 success 3개를 다시 수집한다.
- Gate의 raw provider content를 보존하거나 live diagnostic surface로 노출해 `invalid_gate_result`의 정확한 parse/semantic clause를 확인하고, 그 결과를 바탕으로 Gate prompt/repair의 별도 결정 브리프를 만든다. 그 전에는 B2b fixture·default 값을 바꾸지 않는다.
- 세 workload의 success 3개·failure rate·p95/max를 근거로 production aggregate token/time default와 여유 ceiling을 별도 owner decision으로 확정한다.

## Verification

- focused: `python3 -m pytest -q -p no:cacheprovider tests/test_writing_loop_benchmark_script.py tests/test_llm_benchmark_script.py tests/test_writing_loop_budget.py tests/test_writing_loop_audit.py` → **52 passed / 8 subtests passed**.
- full: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **981 passed / 48 skipped / 217 subtests**.
- `python3 -m py_compile scripts/benchmark_writing_loop.py tests/test_writing_loop_benchmark_script.py` 및 `git diff --check` 통과.
- full-stack live는 B2b의 계측 대상이므로 이 sandbox에서 대체하지 않았다. 스크립트·fixture·report contract만 결정적으로 검증했고, 실제 p95/default 숫자는 full-stack machine 실행 후 확정한다.
- runtime readiness check: `docker compose ps` → 실행 service 없음; `curl -sS --max-time 5 http://127.0.0.1:8000/health` → connection refused. live benchmark는 미실행이다.
- live readiness: remote llama `/health` = `{"status":"ok"}`; Compose application/Mongo/gateway/embedding/Chroma/Elasticsearch healthy. initial full run은 pre-context 400, seed 보완 후 live `POST /writing/revise-and-gate`는 HTTP 502(성공 표본 0)로 종료했다.
- seed 보완 focused: `python3 -m pytest -q -p no:cacheprovider tests/test_writing_loop_benchmark_script.py tests/test_writing_revise.py tests/test_writing_report.py tests/test_writing_gate.py` → **80 passed / 81 subtests passed**. `py_compile`와 `git diff --check` 통과. 전체 suite는 58% 진행 후 실행 세션이 끊겨 이번 상태에서는 완료 결과를 주장하지 않는다.
