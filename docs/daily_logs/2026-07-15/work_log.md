# Work Log — 2026-07-15

## Goals

- HANDOFF와 2026-07-14 work_log이 지정한 다음 작업(B2b ceiling Option A의 **측정 메커니즘 M-i 확정 → per-stage 측정 도구 구현**)을 진행한다.
- 측정 메커니즘(M-i vs M-ii)은 감사 계약(P1=B bodyless)을 건드릴지 갈리는 오너 결정이므로(CLAUDE.md §1) 임의 선택하지 않고 확인한 뒤 착수한다.

## User Decisions and Rationale

- **측정 메커니즘 M-i 확정**: `docs/plans/05-writing-loop-ceiling-composition-decisions.md`의 sub-decision에서 오너가 **M-i(in-process per-stage 측정 script)**를 선택했다. 각하된 M-ii(persisted audit에 per-stage token/ms 노출)는 P1=B "bodyless" 감사 결정을 수정해야 하고 retrieve_plan/context_search stage가 terminal_pass run에 없어 Gate 독립성 문제를 재발생시킨다. M-i는 audit 계약을 건드리지 않고(정본 보존, 로컬 1인 프로젝트 단계) `diagnose_writing_gate/report` 선례 패턴을 재사용하며 Gate 독립성 문제를 합성 retrieve_more Gate로 원천 회피한다. full-stack HTTP 지연은 wall-clock 여유율(B4)로 흡수한다.
- **다음 slice로 multi-finding revise 선택 + D1=A/D2=A/D3=A 확정**: B2b ceiling live 수집이 풀스택 다운으로 막혀(오너/풀스택 과제), sandbox-내 병렬 후속 중 오너가 **Writing loop multi-finding revise**를 골랐다. 결정 브리프(`plans/05-writing-multi-finding-revise-decisions.md`)로 forks를 surface: **D1=A**(continuity-only 유지 — do_not_use/pov 자동 splice 제외, canon 보존)·**D2=A**(sequential, 라운드당 1 finding — 아키텍처가 이미 매 revise 뒤 re-gate하므로 자격 함수 완화만으로 순차 소진 성립; batch D2=B는 splice/계약 대규모 재작성이라 §2 위배)·D3=A(error severity 먼저). 근거: 로컬 1인 프로젝트지만 정본 보존 정책상 canon-민감 자동수정은 review 경로로 두고, 최소 변경으로 gap을 닫는다.

## Completed work

### Phase 5.10 Option A (M-i) per-stage 측정 도구 구현 (SoT v1.6.87)

- **배경**: v1.6.86에서 합성 코어(`worst_case_stage_counts`/`compose_worst_case_ceiling`)가 이미 구현·독립 검증 PASS. 이 코어는 per-stage 비용 dict를 입력받아 최악경로 ceiling을 산출하나, 그 입력(실 12B per-stage token·ms)을 얻는 측정 메커니즘이 미확정이었다. 본 slice가 오너 확정 M-i를 구현한다.

- **`services/application/app/writing/per_stage_measure.py`(신규, 측정 코어)**:
  - `run_per_stage_measurement(...)`가 loop 5개 stage(revise/report/gate/retrieve_plan/context_search)를 격리 측정한다. 각 stage는 collaborator의 `*_metered` 변형(revise/report/gate/retrieve_plan)으로 provider `TokenUsage`를 받고 `perf_counter`(주입 가능한 `clock`)로 wall-clock을 잰다.
  - **불변식 동형**: `context_search`는 loop `metered()` 밖 호출(`revise_gate.py:474`)이라 aggregate token 미포함 → 측정 코어도 `context_search.total_tokens=0`으로 고정, `stage_tokens` dict에서 제외(`_TOKEN_STAGES`=revise/report/gate/retrieve_plan). wall-clock은 전 stage 포함.
  - **retrieve_plan Gate 독립성 회피**: 실 Gate는 retrieve_more를 안 내므로(live 0/12), `_synthetic_retrieve_more_gate`가 planner가 받아들이는 retrieve_more `WritingGateResult`(코드 구성, 모델 미산출)를 만들어 `plan_metered`에 먹인다. planner는 retrieve_more decision + retrieve_more finding ≥1만 요구하고 evidence containment는 검사 안 하므로 generic finding으로 충분.
  - `repeats`간 stage별 **보수적 MAX**를 취한다(합성 공식의 "관측 최댓값"). stage fault(`MeteredCallError` 등)는 그때까지 완료한 stage samples를 보존하고 `error`/`error_stage`로 surface, 미완료 stage는 `incomplete_stages`에 담아 operator가 gap에서 ceiling을 합성하지 못하게 한다.
  - **쓰기 없음**: 읽기/판정 메서드만 호출(build_context_package·revise_metered·enrich_metered·evaluate_metered·plan_metered), Mongo/audit/file 0. 출력은 숫자만(token/ms/model)이라 gate/report 진단과 달리 raw prose가 없어 persist가 안전.
  - `measurement_to_dict`가 JSON-safe(숫자만) 데이터로 렌더.

- **`scripts/measure_writing_stages.py`(신규 CLI)**:
  - `build_services`가 `main.py`의 production factory(`_build_revise_service`/`_build_report_service`/`_default_writing_gate_service(provider=...)`/`_build_writing_retrieval_planner`/`_default_context_search_service`)로 모든 stage를 실 gateway provider와 조립 — prompt template·`LLM_GATEWAY_MODEL`·각 `WRITING_*_MAX_TOKENS`가 production 계약과 동형. gate/report 진단 script의 shared helper(`seed_context`·`build_search_request`·`_finding_from_dict`·`_PositionAction`·env helper)를 import해 중복 제거.
  - `_policy_from_env`가 `main.py`와 같은 `WRITING_LOOP_MAX_REVISION_ROUNDS|RETRIEVAL_ROUNDS|GATE_EVALUATIONS`로 `WritingLoopPolicy`를 구성 → 합성 ceiling이 production loop 구조 상한과 일치.
  - 측정 dict를 `compose_worst_case_ceiling`에 투입해 `{project_id, model, repeats, policy, measurement, ceiling}` JSON을 stdout 출력.
  - 실행: `docker compose run --rm --no-deps application python scripts/measure_writing_stages.py --project-id <id> --repeats 3`. `--current-position DRAFT_ID VERSION_ID`로 idempotent context seed 생략 가능.

- **회귀(`tests/test_writing_per_stage_measure.py`, +10)**: per-stage token/wall-clock 캡처·**context_search token 제외**(under/over-strict: ms 존재하나 stage_tokens에 부재)·synthetic retrieve_more Gate가 planner에 전달됨(실 Gate가 PASS여도)·repeats간 보수적 MAX(alternating usage에서 max 채택)·stage fault surface + incomplete_stages(fault 전 stage는 complete)·default 정책 ceiling round-trip(tokens=500·ms=9000)·no-write call sequence spy·`measurement_to_dict` JSON 키·repeats≥1 검증·CLI main/arg parser wiring.

### Writing loop multi-finding revise 구현 (SoT v1.6.88)

- **gap**: bounded loop의 `_eligible_revision_finding`(`revise_gate.py`)이 자동 revise 대상을 **정확히 1개**(`len(findings) != 1 → None`)로 제한했다. Gate 계약상(`gate.py:_PRIORITY`) loop가 revise 분기에 오면 decision=findings의 recommended_decision 최대 우선순위=revise이므로 **그 순간 모든 finding이 revise 추천**인데, 다수면 `len != 1` 이유만으로 `not_eligible` 종료 — 실 Gate가 다수 continuity 문제를 지적하는 정상 상황을 처리 못 했다.
- **구현(D2=A sequential)**: 아키텍처가 이미 매 revise 뒤 report→re-gate를 돌므로, 자격 함수만 "정확히 1개"→"N개 중 최우선 1개 선택"으로 완화하면 남은 finding이 다음 라운드 gate 결과에서 다시 선택돼 순차 소진된다. per-finding 자격을 `_is_eligible_continuity_revise`로 추출(continuity+revise+evidence 후보 내 1회 — 단일 규칙 그대로, **D1=A** do_not_use/pov 제외)하고, `_eligible_revision_finding`은 자격 finding 중 **severity desc→gate순서(D3=A)** 최우선 1개를 선택. 변경 표면 = 자격 함수 1개 + `WritingGateSeverity` import; loop·reviser·report·Gate·audit·budget 계약 무변.
- **동작 변화**: 유일한 변화 = 다수 continuity finding이 `not_eligible` 대신 순차 소진. loop status/stages/HTTP envelope/public literal 동일. finding당 revision round 1 소비라 `max_revision_rounds`가 총량을 그대로 bound(기본 2 → 2개까지, env 상향 가능).
- **회귀 +7**: `EligibleRevisionFindingTest` 5(자격 0→None under-strict[empty·POV·retrieve_more·evidence 부재·multi-occurrence]·단일 반환·2개 첫 선택·error 우선 order-independent[D3]·ineligible 혼재 시 eligible 선택[old len≠1 dead-end 제거 증명])·`MultiFindingSequentialLoopTest` 2(실 `WritingRevisionService` reviser 관통 2-finding 순차→pass·기본 상한 budget_exhausted over-strict bound). 기존 `test_revise_eligibility_rejects_every_broader_boundary`의 "2 continuity findings→not_eligible" case를 새 계약(eligible)으로 정정(주석으로 multi-finding 테스트 상호참조).
- **패턴 스윕(§4)**: `grep`으로 `len(findings)`/`findings[0]`/`_eligible_revision_finding` 소비처 확인 — writing source에서 `_eligible_revision_finding`이 유일 소비처(`revise_gate.py:396`), 다른 단일-finding 가정 없음.

## Issues found

- 초기 테스트에서 두 가지가 드러났다:
  1. **부분 samples 유실**: `_measure_once`가 fault 시 `_StageMeasurementError`를 raise할 때 그때까지 모은 samples를 caller가 못 받아 모든 stage가 `incomplete`로 잘못 표시됐다. → `_measure_once`가 caller-provided `samples` 리스트에 append하도록 바꿔, fault 시에도 완료 stage를 보존(retain)하게 수정.
  2. **테스트 clock float 오차**: step=0.1 누적이 `int((clock()-start)*1000)` 절삭에서 99ms로 떨어졌다. → 테스트 clock을 binary-exact step=1.0(=1000ms/stage)로 바꿔 결정성 확보. 실 코드(`perf_counter`+`int` 절삭)는 무변.

## Decisions

- 오너: 측정 메커니즘 **M-i** 확정(위 User Decisions).
- 구현: 측정 코어는 감사/API/파일 어디에도 쓰지 않는 read-only orchestration이며, gate/report live diagnostics와 동형 seam(production factory 재사용)을 쓴다. 출력이 숫자만이라 진단(raw prose, terminal-only)과 달리 JSON을 persist해도 안전 — 그래서 CLI는 machine-usable JSON을 낸다.
- 구현: `context_search` token 제외·`retrieve_plan` 합성 Gate는 합성 코어 불변식(`_TOKEN_STAGES`)과 조사 결론(Gate 독립성)을 그대로 반영한 것이며, 새 계약 결정이 아니다.

### 독립 검증 PASS(조건 없음) + 비차단 hardening 반영

- 오너 요청으로 독립 검증 실행됨(`docs/verifications/2026-07-15/writing_per_stage_measure_mi.md`). **평결 PASS(조건 없음)** — 경계 매트릭스 빈 cell 없음, load-bearing 동형성 3건(context_search token 제외·retrieve_plan 합성 gate·합성 공식) 1차 소스 CONFIRMED, loop-level tripwire bite 실증, 작업 AI claim 전부 정규 명령 재현. 비차단 hardening 6건 중 실효성 높은 3건을 반영했다:
  - **H6(가장 실효적) — CLI가 incomplete 상태에서 ceiling 무조건 합성**: `compose_worst_case_ceiling`이 누락 stage를 `stage_tokens.get(stage,0)`로 0 기여시켜, fault로 빠진 stage가 있으면 `ceiling.max_total_tokens`/`max_wall_clock_ms`를 **과소 산출**한다. 이 산출물이 production default 근거라 `ceiling` 숫자만 읽는 operator에게 footgun. **fails-closed 방어**: CLI에 `compose_ceiling(measurement, policy)` 래퍼를 두어, 어느 stage든 incomplete(fault/미측정)면 `ceiling.complete=false`+`incomplete_stages`를 노출하고 `max_total_tokens`/`max_wall_clock_ms`를 `null`로 비운다(`stage_counts`는 디버깅용 보존). under-bound 숫자가 실 최악경로로 오독될 여지를 제거. 공유 합성 함수(`benchmark_writing_loop.py`)는 무변 — 가드는 CLI 경계에만 둠.
  - **H2 — CLI env→policy wiring 미측정**: `_policy_from_env`가 `WRITING_LOOP_MAX_{REVISION_ROUNDS,RETRIEVAL_ROUNDS,GATE_EVALUATIONS}` env→`WritingLoopPolicy`로 읽는 경로를 CLI 테스트(`fake_run`)가 관통 안 했다. `test_policy_from_env_reads_structural_caps`(env override 4/2/9)·`test_policy_from_env_defaults`(2/1/3)로 잠금.
  - **H1 — SoT v1.6.86 row 합성 코어 누락**: v1.6.87 row가 "v1.6.86 합성 코어"를 역참조하나, v1.6.86 row는 fence-strip만 기술하고 같은 commit(`18f0786`)의 B2b ceiling 합성 코어 slice를 누락했다. v1.6.86 row에 합성 코어 slice + 독립 검증 참조를 보강(역사 기록 정정이 아니라 같은 버전 두 slice 중 누락분 보완).
  - 보류: H3(first-stage fault edge — 일반 fault 메커니즘 F5로 커버)·H4(cosmetic `model` 필드)·H5(live real-gateway 미관통, acknowledged scope-외).
- hardening 회귀 +4(H6 2: ceiling complete/incomplete fails-closed·H2 2: env→policy).

## Verification

- focused: `python3 -m pytest -q -p no:cacheprovider tests/test_writing_per_stage_measure.py` → **14 passed**(초기 10 + hardening 4).
- full: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **1055 passed / 45 skipped / 235 subtests**(v1.6.86 1041 대비 +14 신규 테스트). fail 없음.
- `python3 -m py_compile services/application/app/writing/per_stage_measure.py scripts/measure_writing_stages.py tests/test_writing_per_stage_measure.py`, `docker compose config --quiet`, `git diff --check` 통과.
- **live per-stage 수집 실행은 sandbox 밖 풀스택 후속**: 착수 시점 스택은 다운(worker만 up, 8011/8000 연결 거부)이었다. 측정 도구 자체는 sandbox 내 결정적 회귀로 검증했고, 실 12B per-stage 수치 수집→합성→B4 여유율/default-on 승인은 오너의 풀스택 실행 과제다.

### multi-finding revise 검증 (SoT v1.6.88)

- focused: `python3 -m pytest -q -p no:cacheprovider tests/test_writing_revise.py` → **47 passed / 54 subtests**(신규 `EligibleRevisionFindingTest` 5 + `MultiFindingSequentialLoopTest` 2 포함, 정정된 boundary 테스트 포함).
- full: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **1062 passed / 45 skipped / 240 subtests**(v1.6.87 1055 대비 +7). fail 없음.
- `python3 -m py_compile services/application/app/writing/revise_gate.py tests/test_writing_revise.py`, `docker compose config --quiet`, `git diff --check` 통과.
- 동작 실측: `MultiFindingSequentialLoopTest`가 실 `WritingReviseGateService.run` + 실 `WritingRevisionService` reviser를 관통해 2-finding 순차 revise→pass를 검증(단위 아닌 end-to-end 경로 관측).

- **오너 독립 검증 PASS(조건 없음)**(`docs/verifications/2026-07-15/writing_multi_finding_revise.md`) — 경계 매트릭스 11 cell 전부 회귀 lock, 변경 표면 격리(자격 함수 유일 hunk), 순차 소진 전제 loop 본체 확인, worker claim 정규 명령 재현. 비차단 hardening 3건 반영:
  - **H1(브리프 정밀도)**: 브리프 `05:27`의 "revise 분기의 모든 finding이 revise 추천"이 부정확(Gate decision priority상 `pass` 추천 finding이 섞일 수 있음). 코드는 `recommended_decision is REVISE` 필터로 정확 처리(브리프보다 robust)하나, 브리프/SoT 산문을 "revise 분기엔 retrieve_more/needs_review/block 추천 finding이 없고, 자격 함수가 recommended_decision=revise인 continuity finding만 선택하므로 pass 혼재도 안전"으로 정밀화.
  - **H2(DO_NOT_USE 명시)**: 비-continuity ineligible 테스트가 POV만 썼다. `test_none_when_no_finding_eligible`에 `DO_NOT_USE` 케이스 추가(동일 필터링이나 별도 finding type 명시 커버). subtests 239→240.
  - **H3(first-round 비대칭 문서화)**: `/writing/revise-and-gate` 진입의 첫 revise finding은 client 제공이고 selector는 후속 라운드만 다수 finding을 선택한다(진입 계약상 의도된 비대칭, `test_multi_finding_revise_processes_sequentially`가 관통). 브리프 Follow-up에 명시.
  - hardening 후 focused 47/54, full 1062/45/240 유지.

## Next steps

- **(오너, sandbox 밖)** 풀스택 기동 후 `docker compose run --rm --no-deps application python scripts/measure_writing_stages.py --project-id <benchmark-project> --repeats 3`으로 실 12B per-stage token·ms를 수집한다. 출력 `ceiling.max_total_tokens`/`max_wall_clock_ms`가 raw 최악경로다.
- **(오너)** raw ceiling에 **B4 여유율**을 얹어 `WRITING_LOOP_MAX_TOTAL_TOKENS`/`WRITING_LOOP_MAX_WALL_CLOCK_MS` production 기본값(default-on)을 확정한다.
- **(별도 트랙)** 12B Gate 과민 revise/not_eligible finding = Gate 프롬프트 판별 튜닝(compare judge J1의 Gate 판) — 이 ceiling slice와 독립, 신호만 기록.
- (선택) 측정 도구가 새 CLI/JSON 계약이므로 오너가 원하면 독립 검증 대상. 본 slice는 자체 회귀로 결정적 표면을 잠갔다.
