# 검증 기록 — Phase 5.10 B2b Writing loop full-stack benchmark harness

## Subject metadata

- **날짜**: 2026-07-14 (초기 검증) / **2026-07-14 재검증**(B1 보완 후)
- **요청자**: 오너(사용자) — 초기 "의심하고 또 의심해줄래" → B1 보완 후 "테스트 추가했다니까 재검증 진행해줘"
- **검증자**: 독립 검증자(Claude, 작업자와 다른 session)
- **재검증 대상**: B1 blocking cell 보완 테스트 2건 추가(`test_warmup_http_failure_is_retained_and_measured_run_continues`, `test_http_and_audit_envelope_failures_become_raw_failure_runs`) 및 `_Client`/`_Response` `post_status` 확장.
- **대상 slice/artifact**: Phase 5.10 B2b benchmark harness 구현(SoT v1.6.81)
  - `scripts/benchmark_writing_loop.py`(신규)
  - `tests/test_writing_loop_benchmark_script.py`(신규)
  - `docs/plans/05-writing-loop-benchmark-decisions.md`(신규 착수 결정 브리프)
  - 문서 갱신: `docs/system-contract-sot.md`(v1.6.80→v1.6.81), `CHANGELOG.md`, `HANDOFF.md`, `docs/plans/README.md`
- **정본 참조**: `docs/system-contract-sot.md` v1.6.81 (및 v1.6.78~80 연쇄), `docs/plans/05-writing-loop-benchmark-decisions.md`, `docs/plans/05-writing-loop-budget-decisions.md`, `services/application/app/writing/revise_gate.py`
- **작업 출처**: working tree, uncommitted(`git status` — 위 4개 doc 수정 + 4개 untracked). 본 slice는 production code를 전혀 수정하지 않는다(scripts/·tests/·docs/ 만 추가).

## Scope

정본 계약을 먼저 좁혀 읽었다(canonical contract scope). 본 slice의 계약은 착수 결정 브리프 `05-writing-loop-benchmark-decisions.md`가 정하며, SoT v1.6.81 changelog가 그 요약이다. 브리프가 연쇄 참조하는 한에서 `revise_gate.py`(loop stage 추적), `loop_audit.py`/`main.py`(audit·응답 envelope), `05-writing-loop-budget-decisions.md` M6(budget off 전제)까지 포함했다. 관련 없는 이전 plan iteration·아이디에이션 원본은 제외.

검증 대상 표면(정본→구현→회귀→fixture를 한 덩어리로):

1. **정본(브리프) 계약**: B1~B4 결정, Resolution, Follow-up, execution outline이 harness에 요구하는 경계.
2. **harness 구현**: `scripts/benchmark_writing_loop.py`.
3. **회귀 테스트**: `tests/test_writing_loop_benchmark_script.py`.
4. **구현 대조용 실제 loop/endpoint**: `revise_gate.py` stage 추적, `main.py` 응답/audit payload, `WritingLoopPolicy` 기본값.
5. **선례 일치**: 기존 `scripts/benchmark_llm_provider.py` + `tests/test_llm_benchmark_script.py`(브리프가 "기존 Gemma Q4 선례"라고 주장).
6. **테스트 카운트 재현**: focused 4종 + full suite.
7. **live 실행 가능성**: budget off 전제, audit opt-in override.

## Methodology

boundary matrix를 브리프에서 먼저 세운 뒤, 각 cell을 구현→테스트→실제 loop 순으로 추적했다. 작업자 주장을 믿지 않고 1차 사료에서 재도출.

```bash
# 정본/구현/테스트 읽기 + grep 대조
git diff HEAD -- docs/system-contract-sot.md HANDOFF.md CHANGELOG.md docs/plans/README.md
grep -rn 'REVISE = "revise"|REPORT = "report"|...' services/application/app/writing/revise_gate.py
# loop run() 전문과 응답 envelope을 직독(read)하고 fixture trace를 손으로 end-to-end 추적
# WritingLoopStatus / WritingLoopPolicy 기본값 / _env_opt_int / _env_bool 직독

# 컴파일 + whitespace
python3 -m py_compile scripts/benchmark_writing_loop.py tests/test_writing_loop_benchmark_script.py
git diff --check

# focused(작업 로그 주장: 50 passed / 6 subtests)
python3 -m pytest -q -p no:cacheprovider tests/test_writing_loop_benchmark_script.py
python3 -m pytest -q -p no:cacheprovider \
  tests/test_writing_loop_benchmark_script.py tests/test_llm_benchmark_script.py \
  tests/test_writing_loop_budget.py tests/test_writing_loop_audit.py

# full(작업 로그 주장: 979 passed / 48 skipped / 215 subtests)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider

# budget off 전제 검증
grep -n 'WRITING_LOOP_MAX_TOTAL_TOKENS|WRITING_LOOP_MAX_WALL_CLOCK_MS' docker-compose*.yml
```

## Findings

### F1. fixture stage trace가 실제 loop 추적과 정확히 일치한다 (가장 큰 위험 제거)

브리프는 fixture의 expected stage trace를 "현재 확정된 사실"로 가정하지만, live 실행이 없어 한 번도 실제 loop와 대조되지 않았다. trace가 틀리면 모든 live run이 `unexpected_loop_trace`로 붕괴한다. 그래서 `revise_gate.py:WritingReviseGateService.run`(226~511행)을 직독하여 세 fixture를 손으로 추적했다.

stage 이름 enum(`revise_gate.py:86-91`)이 fixture와 문자열까지 일치: `revise`/`report`/`gate`/`retrieve_plan`/`context_search`/`merge`. 별도 enum이 6개뿐이고 **`repair`는 없다** — repair는 report/retrieval 내부 sub-operation이라 stage trace에 별도 row로 나오지 않는다(`refresh_report()`가 REPORT 1개만 record). 따라서 fixture에 repair가 없는 것은 정확하다.

추적 결과(구조적 상한 `max_revision_rounds=2 / max_retrieval_rounds=1 / max_gate_evaluations=3`, `revise_gate.py:112-114`):

- **terminal_pass**: 최초 revise→report→gate(1), gate=PASS 종료. trace=`(revise, report, gate)`. ✓ 일치
- **retrieve_more_then_pass**: 최초 3단계 후 gate1=RETRIEVE_MORE → `(retrieve_plan, context_search, merge)` + gate2(2)=PASS. trace=`(revise, report, gate, retrieve_plan, context_search, merge, gate)`. ✓ 일치
- **max_structural_path**: gate1=REVISE(revision 2회 도달) → gate2=RETRIEVE_MORE(retrieval 1회 도달) → gate3=PASS(gate_evaluations 3 도달). trace=`(revise, report, gate, revise, report, gate, retrieve_plan, context_search, merge, gate)`. ✓ 일치. 세 cap에 정확히 도달하는 bounded path다.

→ fixture의 expected trace는 loop 구현과 완전히 일치한다. live 실행 전에는 검증이 불가능했던 가장 치명적 가정이 코드 수준에서 확증됐다.

### F2. 응답/audit envelope contract가 harness 읽기와 일치한다

harness가 읽는 키가 실제 endpoint 응답에 그대로 존재한다(`main.py` 직독):

- POST 성공 응답(2982~2992행): `candidate`/`gate`/`loop`/`stages`/`audit_id`/`audit_error`. harness는 `payload["loop"]`,`["stages"]`,`["audit_id"]` 읽음(`benchmark_writing_loop.py:225-227`). ✓
- `_writing_loop_payload`(2386-2392행) → `{"status": ..., ...}`. harness `loop.get("status")`와 `expected_loop_status="pass"` 비교. `WritingLoopStatus.PASS="pass"`(`revise_gate.py:77`). ✓
- `_writing_stages_payload`(2394-2399행) → `[{"stage": item.stage.value, ...}]`. harness `stage["stage"]`. ✓
- audit detail `_writing_loop_audit_payload`(2418-2436행) = summary 전개 + detail. summary(2401-2416행)가 **최상위** `total_tokens`/`wall_clock_ms` 포함. harness `audit["total_tokens"]`,`["wall_clock_ms"]`(`benchmark_writing_loop.py:258-259`). ✓

### F3. audit GET이 POST latency에 섞이지 않는다

`_run_case`는 `started=now()`→POST→`elapsed_ms=(now()-started)*1000`를 POST 직후에 계산(205~216행)하고, audit GET은 그 이후(240행)에 실행된다. GET 경로는 `now()`를 소비하지 않는다. 테스트 `test_success_records_post_latency_and_persisted_aggregate_metrics`가 `_Clock(10.0, 11.25)`(정확히 2값)로 `http_latency_ms==1250.0`을 검증(83행) — audit GET이 `now()`를 소비하면 clock 고갈로 에러난다. under-strict guard가 clock 고갈이라는 우회적 형태로 존재한다(명시적 assertion은 아님 → F7 참조).

### F4. budget off 전제가 기본 Compose 배포에서 성립한다 (live 측정 유효성)

브리프는 "limits off 상태로 측정해야 실제 workload 분포를 자르지 않는다"고 요구. 검증:
- `WritingLoopPolicy` 기본 `max_total_tokens=None`,`max_wall_clock_ms=None`(`revise_gate.py:115-116`).
- env wiring(`main.py:1149-1161`)이 `_env_opt_int` 사용. `_env_opt_int`(433-438행)는 "Unset or empty means None" — 빈 문자열→None.
- `docker-compose.yml:45-46`이 `${WRITING_LOOP_MAX_TOTAL_TOKENS:-}`/`${..._WALL_CLOCK_MS:-}`(빈 문자열 기본)로 전달.
- → 미설정 시 None→**budget off**. harness가 env를 건드리지 않으므로 기본 배포에서 limits-off 측정이 보장된다.
- audit은 harness가 요청마다 `persist_audit=True`를 보내(`benchmark_writing_loop.py:53`) env 기본(false)을 override(`main.py:2785-2788`). 따라서 audit은 benchmark run마다 강제 persist. ✓

### F5. production default가 여전히 off다 (B4 위반 없음)

본 slice diff는 어떤 default-on 변경도 포함하지 않는다. SoT v1.6.81 changelog·HANDOFF·CHANGELOG 모두 "결과 확인 전까지 기본 off(`None`)"를 명시. `WRITING_LOOP_MAX_TOTAL_TOKENS|MAX_WALL_CLOCK_MS` 기본값 코드는 건드리지 않았다. B4(결과 후 별도 승인)를 준수한다.

### F6. 선례 일치와 테스트 카운트 재현

- `benchmark_writing_loop.py`의 `_percentile`(`int(round((p/100)*(n-1)))` index, 339-344행), warmup/repeat 구조, ValueError 메시지가 기존 `benchmark_llm_provider.py:249-254,123-148`과 동일. 브리프의 "기존 Gemma Q4 선례 재사용" 주장이 코드 수준에서 성립.
- **focused 재현(초기)**: `tests/test_writing_loop_benchmark_script.py` 단독 → 7 passed. 작업 로그 주장 4종 세트 → **50 passed, 6 subtests passed** (독립 재현 일치).
- **full 재현(초기)**: **982 passed / 45 skipped / 215 subtests passed**. 작업 로그/HANDOFF의 979/48과 다르나 **완전히 설명됨**: 총합 동일(982+45 = 979+48 = 1027), subtests 215 동일. 차이 3개는 본 검증 환경에 ES Python 의존성이 있어 3개가 skip→pass로 바뀐 것(HANDOFF 명시 "ES 미설치 시 3개 skip"). 작업자 환경 972+7(신규)=979/48, 본 환경 975+7=982/45. 환경 차이일 뿐 결함 아님.
- **재검증 카운트(B1 보완 후)**: 파일 단독 **9 passed / 2 subtests**(+2). 4종 세트 **52 passed / 8 subtests**(+2/+2). full **984 passed / 45 skipped / 217 subtests**(+2 tests / +2 subtests). 증분이 신규 테스트 2건(`warmup_http_failure...` 1 + `http_and_audit_envelope...` 1, 후자 subtest 2)과 정확히 일치.
- `py_compile`·`git diff --check` 통과.

## Issues / Risks

### Blocking (contract obligations)

> **재검증(2026-07-14): B1 해소.** 작업자가 `test_warmup_http_failure_is_retained_and_measured_run_continues`를 추가했고, misleading했던 기존 이름을 `test_warmup_success_is_excluded`로 정리했다. 아래는 초판 blocking 기록이며, 말미에 해소 증거를 추가한다.

#### B1. warmup failure 보존 분기에 회귀 테스트가 없었다 (boundary matrix 빈 cell) — **해소됨**

- **정본**: 브리프 `05-writing-loop-benchmark-decisions.md:16`(Resolution) "warmup 1회 성공은 버리고 **failure는 보존한다**". B3-A(`:49`)도 "branch mismatch, provider/parse/HTTP failure는 p95에서 제외하고 **raw run·실패율로 남긴다**". → warmup failure 보존은 명시적 contract 요건.
- **구현**: `benchmark_writing_loop.py:180-186` warmup 루프에 `if not run.success: runs.append(run)` 전용 분기가 존재(동작은 맞음).
- **(초판) 테스트 부재**: `test_warmup_success_is_excluded_but_warmup_failure_is_retained`가 이름과 달리 성공 client만 써서 failure 보존 절반이 빠져 있었다.
- **선례 대조**: 기존 `tests/test_llm_benchmark_script.py:103-141`(`test_warmup_provider_error_is_recorded_without_aborting`)가 같은 동작을 전용 테스트로 잠그고 있었다.
- **(초판) under-strict guard 부재 입증**: 보존 분기를 제거한 사본에서 7 tests가 여전히 green이었음.

**해소 증거(재검증)**:
- 신규 `tests/test_writing_loop_benchmark_script.py:119-130` `test_warmup_http_failure_is_retained_and_measured_run_continues`가 cell을 채운다. `_Client(post_status=503)`로 warmup·measured 모두 HTTP 실패를 일으키고 `(a)` `[run.iteration ...] == [0, 1]`(warmup failure 보존 + measured 계속 실행), `(b)` `all(not run.success ...)`, `(c)` error_code `["http_503","http_503"]`를 검증. docstring이 under-strict(분기 삭제→it=0 누락)·over-strict(측정 it=1은 계속) 양방향을 명시. public surface(iteration·success·error_code)를 pin.
- **결정적 경험 증명**: `benchmark_writing_loop.py:185-186`의 보존 분기를 in-place로 제거하고 이 테스트만 실행 → **`AssertionError: [1] != [0, 1]`로 RED**. 즉 새 테스트는 green일 뿐 아니라 회귀를 실제로 잡는다(분기 복원 후 다시 9 passed/green으로 복귀 확인). under-strict guard 확보.
- over-strict 방향도 유효: warmup 실패 시 측정 run을 중단하도록 잘못 고치면 `[0,1]`→`[0]`로 red.
- `_Client`/`_Response`가 `post_status`(44-53행)를 지원하도록 같이 확장됨 — non-200 응답 시뮬레이션이 정상 동작.
- → boundary matrix의 빈 cell이 채워졌다. B1은 closed.

### Hardening recommendations (non-blocking)

#### H1. report metadata에 모델/quant/compose revision이 없다 (브리프 과다 약속)

- **정본**: 브리프 Follow-up `:69` "결과 report는 **모델/quant, compose revision**, endpoint, case fixture hash, warmup/repeat, raw per-run aggregate tokens/wall-clock, branch/stage trace, success/failure, case별 p95/max를 보존한다."
- **구현**: `build_report`(`benchmark_writing_loop.py:314-336`) metadata = `created_at`/`application_base_url`/`project_id`/`repeats`/`warmups`/`fixture_sha256`. 나머지(raw run·trace·p95·max·failure)는 모두 보존되나 **모델/quant/compose revision은 누락**.
- **구조적 사유**: harness는 배포 환경 사실(모델/quant/compose revision)을 모른다. 선례 `benchmark_llm_provider.py`는 `--model` 인자로 받아 metadata에 넣지만, 본 harness는 해당 인자가 없다.
- **권장 정합(오너 결정)**: (a) `--model`/`--quant`/`--compose-revision` 같은 optional CLI flag를 추가해 metadata에 찍거나, (b) 배포 app의 version/health endpoint를 조회해 채우거나, (c) 브리프를 보정해 이 값들은 live-run 절차에서 sidecar로 기록한다고 명시. live report가 이 필드 없이 확정되면 브리프 위반이 되므로 **live 실행 전에 정합 필요**. 측정 자체(토큰/wall-clock/trace)의 정확성에는 영향 없음 → non-blocking.

#### H2. 세 case의 candidate_text/finding이 동일하다 — branch 분기가 instruction 자연어에만 의존

- 세 fixture는 `candidate_text`·`finding`(`_FINDING`)이 문자 그대로 동일하고 `instruction`만 다르다. loop가 어느 branch(revise/retrieve_more/pass)로 갈지는 모델이 자연어 instruction을 따르는지에만 달려 있다. 브리프 B2-A가 이 위험을 이미 인지("모델 출력이 branch literal을 안정적으로 내도록 benchmark fixture/prompt control이 필요하다"). live 미실행이라 미검증.
- **권장**: live 실행 시 세 case 모두 success 3개가 나오는지, `unexpected_loop_trace` 비율이 0인지 우선 확인(브리프 `:99` 절차가 이미 이것을 요구). 모델이 instruction대로 분기하지 않으면 전체 case 붕괴 → 이때는 p95 default 근거로 승격 불가. documented limitation이므로 code defect는 아님.

#### H3. `_run_case`의 provider/parse/HTTP failure 경로가 end-to-end로 미테스트 — **부분 해소(재검증)**

- 브리프 B3-A가 "provider/parse/HTTP failure는 raw run·실패율로 남긴다"고 명시. (초판) `summarize_runs`만 synthetic failure run으로 검증되고, `_run_case`의 실제 non-200/`audit_missing` 경로가 end-to-end로는 미검증이었다.
- **재검증 부분 해소**: 신규 `test_http_and_audit_envelope_failures_become_raw_failure_runs`(132-147행)가 subTest 2건으로 `post_status=502 → http_502`와 `audit_id=None → audit_missing`을 `_run_case` → failure run end-to-end로 검증한다. 브리프가 명시한 HTTP failure mode 중 non-200·audit-missing이 커버됨.
- **잔존(여전 non-blocking)**: `http_transport_error`(httpx 예외), `invalid_loop_envelope`(parse), `audit_transport_error`, `invalid_audit_envelope`, `audit_http_{status}` 등 나머지 방어 분기는 여전히 미테스트. 이들은 브리프가 명시적으로 나열한 failure mode의 일부(subset)이므로, 남은 방어망 강화 후보로만 둔다(차단 사유 아님).

#### H4. POST latency 제외(audit GET 미포함) 검증이 암묵적이다

- F3처럼 clock 고갈로 우회 검증되지만, "audit GET 시간이 latency에 포함되지 않음"을 명시 assertion 하는 테스트는 없다. 누가 audit GET 경로에 `now()`를 끼워넣어도 clock 고갈로 에러가 나긴 하지만, 의도가 드러나는 explicit guard(예: audit GET 후에도 `http_latency_ms`가 POST-only 값과 동일)를 추가하면 의도가 명확해진다. non-blocking.

## Verdict

**합격(pass)** — 재검증(2026-07-14, B1 보완 후).

초판은 **조건부 합격**이었다(B1 blocking cell). 재검증에서 작업자가 cell을 채웠고, 검증자가 그 테스트가 회귀를 실제로 잡는지(in-place 분기 제거 → RED, 복원 → GREEN)까지 경험적으로 확인했다. 따라서 남은 blocking 항목이 없어 **합격**으로 상향한다.

harness의 측정 표면은 정본에 부합한다: POST latency·audit aggregate 분리 측정(F3), 세 fixture의 expected stage trace가 실제 loop 구현과 정확히 일치(F1, live 미실행 상태에서 코드 수준으로 확증 — 이 slice의 가장 큰 위험 제거), 응답/audit envelope contract 일치(F2), budget-off 전제 성립(F4), B4 위반 없이 production default 유지 off(F5), 선례 일치·테스트 green(F6, 재검증 카운트 9/52/984 모두 정합).

B1(warmup failure 보존)의 boundary cell이 신규 테스트로 채워졌고 양방향 guard가 경험적으로 입증됐다. H3(HTTP/audit failure end-to-end)도 부분 해소. H1·H2·H4는 여전 non-blocking이나, **H1(report metadata 모델/quant/compose revision 누락)은 live report 확정 전에 정본과 정합**해야 브리프 위반이 되지 않는다.

## Outstanding items

- **live benchmark 미실행(설계상)**: 본 sandbox는 `docker compose ps` service 0건, `http://127.0.0.1:8000` 연결 거부. 작업자가 임의로 full-stack/GPU를 올리지 않은 것은 정당. raw p95·실패율 report는 full-stack 전용 project에서 별도 실행. → 이 검증은 harness·fixture·report contract만 다루었고 실제 숫자는 다룰 수 없었다(측정 대상이 live 그 자체).
- **B4 최종 숫자 미확정(설계상)**: p95/여유 ceiling·off→on 승격은 live report 후 별도 owner decision. 본 slice가 아님.
- **uncommitted**: 본 작업분(+ B1 보완 테스트)은 working tree에 untracked/modified로 존재(commit 안 됨). 커밋 여부는 오너 결정.
- **B1 해결됨(재검증)**: boundary cell 채워짐, 양방향 guard 경험 입증. 본 slice는 contract 관점에서 closed 가능. 단 H1 정합·live 실행·B4 숫자 확정은 별개 후속.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# 1. trace 일치성(코드 수준): revise_gate.py:86-91 enum + run() 226-511을 직독해
#    세 fixture expected_stages와 end-to-end 대조(F1).
# 2. envelope 일치: main.py:2386-2436(payload builder)·2982-3019(endpoints)(F2).
# 3. budget off 전제: revise_gate.py:115-116 + main.py:433-438 + docker-compose.yml:45-46(F4).

# 4. 컴파일/whitespace
python3 -m py_compile scripts/benchmark_writing_loop.py tests/test_writing_loop_benchmark_script.py
git diff --check

# 5. focused(초판 50/6; 재검증 52/8)
python3 -m pytest -q -p no:cacheprovider \
  tests/test_writing_loop_benchmark_script.py tests/test_llm_benchmark_script.py \
  tests/test_writing_loop_budget.py tests/test_writing_loop_audit.py
# → 52 passed, 8 subtests passed

# 6. full(초판 982/45/215; 재검증 984/45/217)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider

# 7. B1 red 증명(재검증): 보존 분기를 제거하면 신규 테스트가 RED로 전환해야 cell이 채워진 것
#    benchmark_writing_loop.py:185-186 의 `if not run.success: runs.append(run)` 제거 후
python3 -m pytest -q tests/test_writing_loop_benchmark_script.py \
  ::WritingLoopBenchmarkScriptTests::test_warmup_http_failure_is_retained_and_measured_run_continues
# → 분기 제거 시 AssertionError [1] != [0, 1] (RED). 복원 시 9 passed/2 subtests (GREEN).

# 8. 2차 재검증(아래 섹션) 카운트
python3 -m pytest -q -p no:cacheprovider \
  tests/test_writing_loop_benchmark_script.py tests/test_writing_revise.py \
  tests/test_writing_report.py tests/test_writing_gate.py   # → 80 passed, 81 subtests
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider  # → 986 passed, 45 skipped, 217 subtests


## 재검증 2차 — live context-seed 보완 + provenance (2026-07-14)

작업자가 full-stack live를 돌리며 발견한 harness 누락을 보완했다(원본 1차 검증이 잡지 못한 latent defect).

### 무엇이 바뀌었는지
- **current_position seed**: `seed_benchmark_context()`가 계측 전 `POST /projects/{id}/drafts` → `POST /projects/{id}/drafts/{draft_id}/versions`(`raw_text`=`_CONTEXT_SEED_TEXT`, `idempotency_key`)로 실제 draft/version을 만들고 `{draft_id, version_id}`를 반환. 이 `current_position`을 warmup·measured 모든 `_run_case`에 전달. seed는 `_run_live`에서 `run_benchmark` 이전에 1회(측정 latency 밖).
- **provenance(H1 폐쇄)**: `--model`/`--quant`/`--compose-revision` required CLI 추가, `build_report` metadata에 기록.
- 회귀 +2: `test_current_position_is_forwarded_to_each_benchmark_request`(전달 값·under-strict), `test_seed_benchmark_context_creates_draft_and_version_before_measurement`(draft→version 순서·응답 shape).

### 검증 결과(1차 사료 재도출)
- **current_position shape 정확**: `CurrentPosition`(`context_search/models.py:97`)와 endpoint 사용(`main.py:3039`)이 `draft_id`/`version_id`. seed 반환 모양 일치.
- **seed 응답 파싱 정확**: `POST /drafts`→`_draft_payload`=`{"id":...}`(`main.py:1457,1176-1188`), `POST /drafts/{id}/versions`→`{"draft_version":{"id":...}}`(`main.py:1476-1481`). seed가 파싱하는 `json()["id"]`/`json()["draft_version"]["id"]`와 정확히 일치 → 런타임 파싱 break 없음.
- **B1~B4 준수 유지**: seed는 측정 latency 밖, 3 fixture·warmup/failure 처리·default off 불변. seed는 브리프 execution outline의 "deterministic seeded project/context fixture" 요구를 이제야 구현한 것(원본 harness가 빠뜨린 것).
- **문서 정합**: 브리프 Live execution(명령 블록 포함 `--model`/`--quant`/`--compose-revision`)·HANDOFF·work_log가 현재 CLI·동작과 일치.
- **카운트**: 4종 focused **80 passed / 81 subtests**(독립 재현 일치). full **986 passed / 45 skipped / 217 subtests**(+2 test / +0 subtest, production code 미변경으로 회귀 없음). `py_compile`·`git diff --check` 통과.

### 판정(2차)
**합격(pass) — harness 보완 코드/테스트/문서 관점.** seed·provenance·forwarding이 모두 정확하고 회귀로 잠겼으며, 브리프와 정합이다.

### 단, 남은 runtime blocker(코드 defect 아님) — 502 원인 미확정
- 보완 후 live `POST /writing/revise-and-gate`가 HTTP 502로 종료(성공 표본 0). 작업자는 p95/ceiling 승격을 보류했고(B4 준수, 숫자 날조 없음 — 올바름).
- **502 원인은 미검증**. 502는 `InvalidWritingRevision`/`ContextSearchFailed`/`ProviderError(non-timeout)`/report·gate failure 중 하나로 매핑되며(`main.py:2824-2837`), 현재 502 응답 body(error_type/detail)가 기록에 없다.
- **오너 힌트(권한문제) 검증 권장**: 작업자의 Mongo 추론은 사실에 부합한다 — `core_sot/mongo_repository.py:241-243`·`analysis/mongo_repository.py:241-243`가 `start_session`+`start_transaction`을 쓰고, Mongo transaction은 replica set이 필수이므로 standalone 불가. 단, (a) shared Mongo에서 실제로 관측한 게 topology 오류인지 permission 오류인지, (b) 502 자체가 권한/인증 문제인지는 502 body로 확인해야 한다. 구체적 가설:
  - remote LLM gateway(192.168.1.22:9080) 인증 — `/health`·`/v1/models`는 통과해도 generation endpoint가 API key/auth를 요구할 수 있음. app provider 설정의 auth 확인.
  - served model id(`google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`)와 app 설정 model명이 정확히 일치하는지(불일치 → provider 404 → 502).
  - 전용 replica set Mongo의 app 사용자 권한 — loop/audit/context 경로가 쓰는 컬렉션 쓰기 권한.
- 작업자의 다음 계획(502 body·stage 분리 진단)은 올바른 방향이나, 위 권한/인증 가설을 1순위로 확인할 것.
```
