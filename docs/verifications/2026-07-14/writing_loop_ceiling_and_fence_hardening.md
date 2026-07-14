# 검증 기록 — Writing loop ceiling 합성 코어(Option A) + fence-sweep 검증기록 hardening 보강

## Subject metadata

- **날짜**: 2026-07-14
- **요청자**: 오너 ("작업 AI가 작업한 부분 확인해서 검증하고 의심하고 또 의심해줄래" — 두 부분 독립 감사 요청)
- **검증자**: Claude (본 세션, glm-5.2)
- **대상 slice/artifact**: 작업 AI가 본 세션에 산출한 두 부분 —
  1. **Piece 1(fence-sweep 검증기록 hardening 보강)**: `docs/verifications/2026-07-14/residual_parser_fence_strip_sweep.md`의 non-blocking 3건(item 1 over-strict 4종 message-pin 통일·item 2 카운트 3→4 정정·item 3 역사 문서 stale 테스트명 미수정 근거) 적용 + F6/F10 오너 인지 2건 HANDOFF 명시.
  2. **Piece 2(Task 2 Option A — aggregate ceiling 합성 코어)**: `docs/plans/05-writing-loop-ceiling-composition-decisions.md` 브리프 + `scripts/benchmark_writing_loop.py`의 `worst_case_stage_counts`/`compose_worst_case_ceiling` 순수 함수 + `tests/test_writing_loop_benchmark_script.py::WorstCaseCeilingCompositionTests` 회귀 5개.
- **정규 계약 참조**: `docs/system-contract-sot.md` v1.6.86; Writing loop aggregate budget는 SoT v1.6.80(Phase 5.10 B2) + `flat-loop-gate.md` §Budget; 합성의 구조 상한은 `revise_gate.py::WritingLoopPolicy`(구조 cap)·`WritingReviseGateService.run`(loop·metering)에 정확히 대응.
- **작업 소스**: working tree, uncommitted(commit `db04df6` 위). `git diff HEAD`로 검증.

## Scope

정규 계약 scope를 먼저 구축한 뒤 각 표면을 검증(1차 소스에서 재도출, 작업 AI 주장을 신뢰하지 않음).

1. **Piece 2 핵심 불변식(하중 최대)**: `context_search`가 loop `metered()` **밖**이라 aggregate token에 미포함·wall-clock엔 포함된다는 주장을 `revise_gate.py` 실제 loop 코드로 직접 확인.
2. **Piece 2 합성 공식**: `n_gate = min(G, 1+(R-1)+T)` 와 revise/report/retrieve/context_search 카운트가 loop 구조 및 `max_structural_path` fixture와 일치하는지.
3. **Piece 2 회귀 5개**: boundary(should fire / should NOT fire)의 empty cell + mutation으로 guard bite 실증.
4. **Piece 1 over-strict message-pin 보강**: 4종 over-strict 테스트가 pin한 메시지가 실제 structural check(object/schema/enum)에서 오는지(우연한 substring가 아닌지) + mutation으로 bite 실증.
5. **Piece 1 카운트/근거 기록**: HANDOFF·CHANGELOG "4개" 정정 + work_log item 1/3 근거 + plans/README 신규 브리프 등재.
6. **Option A 전제(retrieve_more 0/12)**: benchmark trace에서 실제로 retrieve 경로가 0회인지 empirical 확인.
7. **카운트 독립 재현**: focused 16 · full 1040/45/235 · `git diff --check` clean.

## Methodology

모든 명령은 working tree(uncommitted) 상태에서 실행. 작업 AI가 주장한 숫자·불변식·메시지를 1차 소스에서 재도출.

1. **loop 본문 정독**: `revise_gate.py:226-511`(`WritingReviseGateService.run`) — `metered()` 정의(`:247-267`)·revise(`:361,:406`)·report(`:318`)·gate(`:340`)·retrieve_plan(`:462`)·context_search(`:474`)·merge(`:490`) 호출 지점 전수 확인.
2. **policy 기본값/검증**: `WritingLoopPolicy` 본문(`revise_gate.py:99-127`) — 기본 R=2/T=1/G=3 + `__post_init__` 하한(R≥1, T≥0, G≥1).
3. **합성 공식·불변식 코드 정독**: `benchmark_writing_loop.py`의 `_TOKEN_STAGES`·`_WALL_CLOCK_STAGES`·`worst_case_stage_counts`·`compose_worst_case_ceiling` + `max_structural_path.expected_stages`(`:~120-135`).
4. **over-strict pin 메시지 소스 대조**: extractor `:286`·planner `:244`·compare_judge `:179`·retrieval `:238` 실제 raise 문구와 테스트 assertRaisesRegex 패턴 대조.
5. **mutation test — Piece 1**: `json_extract.py:38`을 `return content`(no-op strip)로 치환 후 4-file suite 실행 → fail 수 관측(Task 1의 15 대비 증가 = over-strict 보강분 bite) 후 revert.
6. **mutation test — Piece 2**: (a) `_TOKEN_STAGES`에 `context_search` 누출 → 불변식 테스트 fail (b) gate 공식 `1+(R-1)+T`→`1+R+T`(off-by-one) → uncapped 테스트 fail, 각각 관측 후 revert. 매번 `git diff --stat`로 residue 부재 확인.
7. **카운트 독립 재현**: focused `tests/test_writing_loop_benchmark_script.py`(16) · full `--ignore=tests/test_memory_mongo.py`(1040/45/235).
8. **정적 검증**: `py_compile`(변경 6 파일) · `git diff --check`.
9. **Option A 전제 empirical 확인**: `docs/benchmarks/2026-07-14/writing_loop_b2b_q4_post_fence_fix.json`에서 12 run 전체의 `retrieve_plan`/`context_search` stage 출현 수와 `summary` success 분포 직접 집계.
10. **pattern sweep**: loop 내 provider-calling stage가 `metered()`를 경유하는지 전수 — context_search 외에 metered 밖 stage가 더 있는지 확인(merge는 in-process 순수 함수).

## Findings

### F1. 핵심 불변식(context_search token 제외) — 1차 소스로 정확히 확인 (하중 최대, 의심 지점)

`WritingReviseGateService.run`에서 provider usage를 합산하는 채널은 `metered()`(`:247-267`) 단 하나이며, `add_usage(accumulated, usage)`(`:264`)로 `accumulated`(= `max_total_tokens` 원천)에 누적된다. loop 본문에서:

- revise `:361,:406` · report `:318` · gate `:340` · **retrieve_plan `:462`** — 모두 `metered(self._*, ...)` 경유 → aggregate token에 합산. ✓
- **context_search `:474`** — `delta = await self._context_search.build_context_package(...)`로 `metered()` **없이 직접 호출** → provider usage가 `accumulated`에 합산되지 않는다. context_search는 자체 `ContextBudget`(`:481`의 `context_budget` param)로 비용을 govern한다.

따라서 작업 AI의 불변식 — *"context_search는 loop metered() 밖이라 aggregate token에 미포함, wall-clock엔 포함"* — 은 코드로 정확히 확인. `compose_worst_case_ceiling`이 `_TOKEN_STAGES`(revise/report/gate/retrieve_plan)에서만 token을 합산하고 `_WALL_CLOCK_STAGES`(위 4종 + context_search)에서 ms를 합산하는 것은 loop의 실제 accounting 경계와 정확히 대응한다. **이 불변식은 ceiling이 safety bound이므로 하중이 가장 크며, 1차 소스로 성립함.**

pattern sweep: metered 밖 provider-calling stage는 context_search가 유일. merge(`:490` `merge_context_packages`)는 in-process 순수 함수(provider 미호출)라 token·wall-clock 모두 미포함이 타당(아래 H2).

### F2. 합성 공식·카운트 — loop 구조 및 fixture와 정확히 일치

`worst_case_stage_counts`(`benchmark_writing_loop.py:~425`): revise=R, report=R, gate=`min(G, 1+(R-1)+T)`, retrieve_plan=T, context_search=T.

loop trace로 검증:
- 초기 revise 1 + report 1 + gate 1(gate_evaluations 0→1).
- REVISE 분기(`:394-443`): cap `revision_rounds>=R` 전에 증분 → 추가 revise는 최대 R-1회, 매번 report+gate.
- RETRIEVE_MORE 분기(`:445-510`): cap `retrieval_rounds>=T` 전에 증분 → 최대 T회, 매번 retrieve_plan+context_search+merge+gate.
- 총 gate = 1(초기) + (R-1) + T, 단 G cap(`:401,:447`)으로 상한.

기본 정책(2/1/3): gate=min(3, 1+1+1)=3, revise=2, report=2, retrieve_plan=1, context_search=1. 이는 `max_structural_path.expected_stages`(`:~127-131`: `revise, report, gate, revise, report, gate, retrieve_plan, context_search, merge, gate`)와 정확히 일치(merge 제외 카운트 동일). edge config(R=1/T=0/R=1,T=0)에서도 공식이 loop cap과 정합함을 수순 확인. `__post_init__`(R≥1,T≥0,G≥1)이 보장하는 모든 유효 config에서 under/over-bound 없음.

### F3. 회귀 5개 — boundary matrix empty cell 없음, mutation으로 guard bite 실증

| 계약 분기 | 유형 | lock 테스트 | mutation bite |
|---|---|---|---|
| 카운트 = max_structural fixture | should match | `test_default_policy_counts_match_max_structural_path` | 공식 변형 시 fail |
| gate cap 강제(G<R+T) | should NOT exceed | `test_gate_count_is_capped_by_max_gate_evaluations` | cap 제거 시 fail |
| gate 공식 정확(G≥R+T) | should NOT under-count | `test_gate_count_uncapped_when_evaluations_allow` | off-by-one(2b) 시 fail ✓ |
| context_search token 제외/ms 포함 | 불변식 | `test_context_search_adds_wall_clock_but_not_tokens` | token 누출(2a) 시 fail ✓ |
| 미측정 stage = 0 | robustness | `test_missing_stage_cost_treated_as_zero` | — |

**mutation 실증**:
- **2a**(`_TOKEN_STAGES`에 context_search 누출): `test_context_search_adds_wall_clock_but_not_tokens` **fail**(token 780 → 780+9999). 불변식이 진짜로 lock됨.
- **2b**(gate 공식 `1+R+T` off-by-one): `test_gate_count_uncapped_when_evaluations_allow` **fail**(gate 3→4). **주목**: G-cap 테스트(default·capped)는 G가 off-by-one을 mask해 이 mutation을 잡지 못한다 — uncapped 테스트(G=9)가 유일하게 공식 자체를 lock한다. suite 설계가 의도적이고 정확함(both-direction).

산술 검증: token 2·100+2·200+3·50+1·30=780(context_search 9999 제외) · ms 2·1000+2·2000+3·500+1·300+1·400=8200(context_search 포함). 코드 및 테스트 기대치와 정합.

### F4. Piece 1 over-strict message-pin 보강 — pin 메시지가 실제 structural check에서 옴, mutation으로 bite 강화 확인

4종 over-strict 테스트가 `assertRaisesRegex`로 pin한 문구가 모두 **실제 structural check의 raise 문구**(우연한 substring 아님):

| parser | pin 패턴 | 소스 raise(`file:line`) | check 종류 |
|---|---|---|---|
| compare_judge | `"result fields do not match schema"` | `compare_judge.py:179` | schema check |
| extractor | `"must be a JSON object"` | `extractor.py:286`(`"provider content must be a JSON object"`) | object check |
| planner | `"must be a JSON object"` | `planner.py:244`(`"planner content must be a JSON object"`) | object check |
| retrieval | `"not allowed for Writing retrieval"` | `retrieval.py:238`(`"need is not allowed for Writing retrieval: …"`) | enum/allowed-need check |

보강 방향의 정당성: Task 1 검증은 3종(compare/planner/retrieval)을 bare `assertRaises`로 두어 "strip 유무 무관 reject"라 했으나, 이는 **false confidence**다 — strip이 subtly broken돼 content를 망가뜨려도 JSONDecodeError로 reject되면 bare `assertRaises`는 통과해 버린다. 작업 AI의 pin 통일은 "reject가 우연한 JSON error가 아니라 실제 object/schema/enum check에서 나온다"를 명시적으로 assert하므로 더 정확한 over-strict guard다(strip이 깨져야만 structural check가 `[]`/schema-invalid를 검사할 기회를 얻으므로, 이 guard가 strip에 의존하는 것은 올바르다).

**mutation 실증(no-op strip)**: 4-file suite **18 failed / 54 passed**(Task 1의 15 failed 대비 +3). 증분 +3은 정확히 보강된 3종 over-strict(compare/planner/retrieval `_does_not_weaken_*`)가 추가로 bite한 것(출력에 `test_fence_does_not_weaken_schema_check` fail 명시). 보강이 실제로 guard를 강화했음을 실증. over-correction(object check 제거 시 `[]` 수용) 방향도 `assertRaisesRegex`가 no-exception으로 fail catch — CLAUDE.md 양방향 guard 충족.

### F5. Option A 전제(retrieve_more 0/12) — benchmark trace로 empirical 확인

`writing_loop_b2b_q4_post_fence_fix.json`(12 run = case 3종×4): 전 run에서 `retrieve_plan`/`retrieve_more`/`context_search` stage 출현 **0회**. `summary`: `max_structural_path` 0/4 success, `retrieve_more_then_pass` 0/4 success, `terminal_pass` **1/4** success(error_codes http_502·unexpected_loop_trace).

→ 최악경로(10-stage max_structural)와 임의 retrieve 경로 모두 실 12B로 한 번도 walk되지 않았다(loop-level 직접 측정 불가). 작업 AI의 "1/12 success"(=terminal_pass 1건만 trace-match success)·"retrieve_more 0/12"·"Gate 독립성으로 prose steer 불가" 조사 결론이 1차 소스로 정확함. 이 empirical 사실이 Option A(해석적 합성) 도입의 근거. terminal_pass(유일 success)의 max_total_tokens=2310·loop_wall_clock_ms_p95=11036는 최소경로 비용이지 최악경로 ceiling이 아님 — 작업 AI 브리프가 이 구분을 정확히 명시.

### F6. 카운트·정적·문서 — 독립 재현으로 주장 확인

- focused benchmark: **16 passed / 2 subtests**(주장 일치). full: **1040 passed / 45 skipped / 235 subtests**(주장 일치; Task 1 v1.6.86의 1035 + Option A 5 = 1040 정합).
- `py_compile` 변경 6 파일 OK · `git diff --check` **DIFF_CHECK_CLEAN**.
- HANDOFF(`:34,:77`)·CHANGELOG(`:9`) "compare/extractor/planner 기존 fence→repair 테스트 **4개**[compare 1·extractor 2·planner 1]" 정정 확인(item 2). HANDOFF Verification(`:68`)에 F6(SoT 정본 수정 유일 지점)·F10(strip=defensive/parity) 오너 인지 2건 + item 1 hardening 반영 사실 명시. work_log(`:189` item 1 근거·`:191` item 3 역사 기록 불변 근거·`:120-135` Task 2 조사·Option A) 기록 확인. `docs/plans/README.md` item 27에 신규 브리프 등재.

## Issues / Risks

### Blocking (계약 의무)

**없음.** Piece 2의 핵심 불변식(context_search token 제외)과 합성 공식이 loop 1차 소스로 성립(F1, F2), 회귀 5개가 mutation으로 양방향 bite(F3), Option A 전제가 benchmark로 empirical 확인(F5). Piece 1 over-strict 보강이 pin 메시지 소스 대조 + mutation +3 fail로 유효(F4). boundary matrix 양쪽 모두 empty cell 없음.

### Hardening recommendations (non-blocking, 현 spec/slice 초과)

1. **합성 모델 ↔ loop metered() 경계 coupling(가장 가치 있는 보강 후보)**: `compose_worst_case_ceiling`의 정확성(context_search token 제외)은 `revise_gate.py:474`에서 context_search가 metered 밖에 있는 현 구조에 의존한다. **향후 refactor가 context_search를 metered()로 경유시키면 합성 함수는 ceiling을 조용히 under-bound하고, 현재 어떤 테스트도 이를 잡지 못한다**(F3의 mutation들은 합성 함수 내부 logic만 검사할 뿐 loop의 실제 metered 경계는 검사 안 함). ceiling이 safety bound임을 감안하면 silent under-bound = unsafe. 본 slice는 의도적으로 순수 함수로 scope됐으므로 blocking 아니다. 보강: (a) `revise_gate.py:474`에 "metered 밖 = ceiling 합성의 token 제외 근거" 주석 교차참조, 또는 (b) 통합 테스트로 실 loop run에서 context_search usage가 `accumulated.total_tokens`에 합산되지 않음을 단정. M-i 측정 script 도입 시 자연스럽게 (b)가 확보될 수 있음.
2. **merge wall-clock 미포함**: `_WALL_CLOCK_STAGES`가 merge를 제외(브리프 "in-process(0)"). merge는 순수 함수·sub-ms라 wall-clock under-estimate가 미미하며 B4 여유율로 흡수. 브리프에 명시된 합의적 단순화. (ceiling에 보수적이려면 merge 1회분을 포함하는 것이 더 안전하나, 무시 가능 수준.)
3. **Task 1 검증기록 본문의 stale 기술**: `residual_parser_fence_strip_sweep.md` F3("over-strict 3종은 bare assertRaises")·hardening rec#1이 보강 전 스냅샷을 기술. 보강 적용 사실은 HANDOFF(`:68`)·work_log(`:189`)에 내구 기록돼 audit trail은 온전하나, 검증기록 본문에도 "item 1 hardening subsequently applied" 1줄 메모를 남기면 독자 혼동 최소화(검증기록은 시점 스냅샷이므로 결함 아님; 우선순위 낮음).

## Verdict

**합격 (PASS).**

하중 지점:
- Piece 2의 **핵심 불변식**(context_search가 `metered()` 밖 → aggregate token 제외·wall-clock 포함)을 `revise_gate.py:474` 1차 소스로 확인(F1). 이 불변식이 ceiling의 safety를 결정하며, 코드가 주장과 정확히 일치.
- 합성 공식 `min(G, 1+(R-1)+T)` 와 카운트가 loop 구조(`:226-511`) 및 `max_structural_path` fixture와 정확히 일치(F2).
- 회귀 5개를 mutation(2a token 누출·2b off-by-one)으로 **양방향 bite 실증**(F3). 특히 uncapped 테스트만이 G-cap이 mask하는 공식 오류를 잡는 점에서 suite 설계가 정확.
- Option A 전제(retrieve_more 0/12, 최악경로 미walk)를 benchmark trace로 empirical 확인(F5) — 해석적 합성 도입 근거 성립.
- Piece 1 over-strict 보강의 pin 메시지가 실제 structural check 문구(object/schema/enum)임을 소스 대조로 확인(F4), no-op strip mutation에서 15→18 fail로 보강분 bite 실증. 양방향 guard 충족.
- 카운트 16/1040/45/235·`git diff --check` clean·py_compile OK·HANDOFF/CHANGELOG/work_log/plans-README 기록 전수 확인(F6).

조건부 합격이 아닌 이유: blocking 계약 의무 위반이나 empty boundary cell이 없음. hardening#1(합성↔metered coupling)은 본 slice가 의도적으로 순수 함수로 scope됐으므로 현 계약 위반이 아니며, M-i 측정 도입 시 자연 확보 가능한 후속 보강 후보.

## Outstanding items

- **미커밋**: Piece 1·Piece 2 전부 working tree(uncommitted, `db04df6` 위). 발행(commit/publish)은 오너 승인 대기.
- **측정 메커니즘 M-i + live per-stage 비용 수집은 오너 확정·sandbox 밖**: 합성 코어는 per-stage 비용 dict를 입력받는 순수 함수로 완성됐으나, 실 12B per-stage 비용(revise/report/gate/retrieve_plan/context_search token·ms) 수집 → 합성 → B4 여유율/default-on 승인은 후속. hardening#1(통합 guard)도 이 시점 확보 권장.
- **별도 트랙**: 12B Gate 과민 revise/not_eligible(not_eligible=4/budget_exhausted=2 in benchmark) = Gate 프롬프트 판별 튜닝 — 본 ceiling slice와 독립(브리프 명시).

## Reproduction

```bash
# 0. 코드/계약/테스트 diff (1차 소스)
git diff HEAD -- scripts/benchmark_writing_loop.py tests/test_writing_loop_benchmark_script.py \
  services/application/app/analysis/ services/application/app/context_search/planner.py \
  services/application/app/writing/ HANDOFF.md CHANGELOG.md docs/system-contract-sot.md \
  docs/plans/README.md docs/daily_logs/2026-07-14/work_log.md

# 1. 핵심 불변식 — context_search 가 metered() 밖인지 (revise_gate.py:462 vs :474)
sed -n '462,484p' services/application/app/writing/revise_gate.py   # retrieve_plan=metered, context_search=직접
sed -n '247,267p' services/application/app/writing/revise_gate.py   # metered() = 유일한 usage 합산 채널

# 2. 합성 코어 + max_structural fixture
sed -n '405,470p' scripts/benchmark_writing_loop.py
sed -n '120,135p' scripts/benchmark_writing_loop.py   # expected_stages 와 카운트 비교

# 3. focused + full 카운트
PYTHONPATH=. python3 -m pytest -q -p no:cacheprovider tests/test_writing_loop_benchmark_script.py   # 16 passed
PYTHONPATH=. python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider            # 1040/45/235

# 4. mutation — Piece 2 불변식/공식 guard bite
cp scripts/benchmark_writing_loop.py /tmp/b.bak
# 4a. _TOKEN_STAGES 에 context_search 추가 → test_context_search_adds_wall_clock_but_not_tokens fail
sed -i 's/_TOKEN_STAGES = ("revise", "report", "gate", "retrieve_plan")$/_TOKEN_STAGES = ("revise", "report", "gate", "retrieve_plan", "context_search")/' scripts/benchmark_writing_loop.py
PYTHONPATH=. python3 -m pytest -q -p no:cacheprovider tests/test_writing_loop_benchmark_script.py::WorstCaseCeilingCompositionTests
cp /tmp/b.bak scripts/benchmark_writing_loop.py
# 4b. gate 공식 off-by-one → test_gate_count_uncapped_when_evaluations_allow fail
sed -i 's/gates = min(policy.max_gate_evaluations, 1 + (revises - 1) + retrievals)/gates = min(policy.max_gate_evaluations, 1 + revises + retrievals)/' scripts/benchmark_writing_loop.py
PYTHONPATH=. python3 -m pytest -q -p no:cacheprovider tests/test_writing_loop_benchmark_script.py::WorstCaseCeilingCompositionTests
cp /tmp/b.bak scripts/benchmark_writing_loop.py
git diff --stat scripts/benchmark_writing_loop.py   # residue 부재 확인

# 5. mutation — Piece 1 over-strict 보강 bite (15→18 fail)
cp services/application/app/writing/json_extract.py /tmp/j.bak
sed -i '38c\    return content' services/application/app/writing/json_extract.py
PYTHONPATH=. python3 -m pytest -q -p no:cacheprovider tests/test_analysis_compare_judge.py tests/test_analysis_extractor_schema.py tests/test_context_search_planner.py tests/test_writing_retrieval.py   # 18 failed
cp /tmp/j.bak services/application/app/writing/json_extract.py

# 6. Option A 전제 — retrieve_more 0/12 empirical
python3 -c "import json,collections; d=json.load(open('docs/benchmarks/2026-07-14/writing_loop_b2b_q4_post_fence_fix.json')); rm=sum(((s.get('stage') if isinstance(s,dict) else s) in ('retrieve_plan','retrieve_more') for r in d['runs'] for s in (r.get('stage_trace') or []))); print('retrieve occurrences:', rm, '| summary:', json.dumps(d['summary'],ensure_ascii=False))"

# 7. 정적 검증
python3 -m py_compile scripts/benchmark_writing_loop.py services/application/app/analysis/compare_judge.py services/application/app/analysis/extractor.py services/application/app/context_search/planner.py services/application/app/writing/json_extract.py services/application/app/writing/retrieval.py
git diff --check   # CLEAN
```
