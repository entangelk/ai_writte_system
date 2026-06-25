# 검증 기록 — AgentLoopRunner provider composition slice

## Subject metadata

- 날짜: 2026-06-25
- 요청자: 소유자("작업 AI가 작업한 분에 대해서 검증하고 의심해줄래? 커밋하고 다음 작업까지 진행했습니다.")
- 검증자: 독립 검증 세션(Claude Code)
- 검증 대상 slice/artifact:
  - `services/application/app/agent_loop/runner.py`(신규, commit `b118e15`)
  - `tests/test_agent_loop_runner.py`(신규, commit `b118e15`)
  - runner가 compose하는 원시 모듈(`budget.py`/`resolution.py`/`completion.py`/`parser.py`/`decision.py`)의 composition 사용처
  - (spot-check) `parser.py` + `tests/test_agent_loop_parser.py`(commit `02acd3b`)
- 정본 계약 참조(scope 한정):
  - `docs/plans/flat-loop-gate.md` §"retry와 terminal decision 우선순위"(line 104-111) — retry non-free + budget-blocks-retry 규칙
  - 같은 문서 §"Budget 계약"/"차원과 계측"(line 75-93) — token post-accounting, `== limit` 허용 / `> limit` `budget_exhausted`, missing usage → `provider_error`
  - 같은 문서 §"budget boundary matrix"(line 113-122)
  - 같은 문서 §"task별 completion criteria 계약"/"공통 판정(하이브리드)"(line 192-211)
  - 같은 문서 §"종료 decision literal"(line 136-148) — 7종 상호 배타
  - `docs/plans/implementation-plan.md` §AgentLoopRunner changelog 행(b118e15로 갱신)
  - `docs/system-contract-sot.md` §AgentLoopRunner provider composition 행(b118e15로 추가)
- 검증 대상 작업 출처: commits `02acd3b`(self-report parser slice) + `b118e15`(agent loop provider runner). HEAD = `b118e15`. 검증 시점 working tree clean(mutation 증명 후 원복 완료).

## Scope

본 검증의 1차 대상은 **runner slice(`b118e15`)** 다. 이 slice는 이전에 **독립 검증 기록이 없었다**(worker 자체 회귀만 존재). parser slice(`02acd3b`)는 이미 `docs/verifications/2026-06-25/self_report_parser.md`로 독립 검증(합격)됐으므로 본 검증에서는 spot-check로 교차 확인한다. 아래 표면을 하나의 묶음으로 검증한다.

1. **계약 본문(self-consistency)**: flat-loop-gate §retry/§Budget/§completion ↔ implementation-plan changelog ↔ system-contract-sot 행의 경계·리터럴 일치.
2. **composition 순서(계약의 핵심)**: runner가 주장하는 5단계 순서(budget 전 check → iteration 기록 → provider call/retry → usage 기록 + post-accounting budget check → parse self_report → judge completion)가 계약 순서와 일치하는가.
3. **I2 forward-lock(load-bearing)**: token overrun이 completion **전에** `budget_exhausted`로 끝나는 순서 — 양방향 변이 증명.
4. **retry non-free(load-bearing)**: provider retry가 iteration budget을 소비 — 양방향 변이 증명.
5. **spec ↔ implementation 리터럴 일치**: decision 7종, SelfReport 2종, preserved literal, 예외→decision uniform 매핑.
6. **회귀 테스트 감사**: `test_agent_loop_runner.py` 7개가 public envelope를 잠그는지, 양방향 guard 존재.
7. **보고 숫자 독립 재현**: worker/계획이 보고한 focused/전체 회귀 숫자 재계산(envelope claim 재검증).
8. **패턴 sweep**: 동일 composition/ordering pattern의 인접 중복 사이트.
9. **문서 갱신 반영**: b118e15가 건드린 계약/HANDOFF/SoT/changelog의 실제 반영.

## Methodology

계약을 먼저 스코프하고(flat-loop-gate §retry·§Budget·§completion 끝까지 읽기), boundary matrix를 구축한 뒤 코드·테스트를 매트릭스 셀에 매핑했다. load-bearing guard 2종은 **변이 증명**(코드를 의도적으로 망가뜬 뒤 관련 테스트가 FAIL 하는지, 원복 후 PASS 하는지)으로 양방향을 독립 입증했다. "코드가 돌아가는가"가 아니라 "코드가 계약을 고정하는가"를 감사한다.

사용한 명령(repo root `/mnt/d/devel/에베베/ai_writte_system` 기준):

- focused 회귀: `python3 -m unittest tests.test_agent_loop_runner -v`
- 전체 회귀: `python3 -m unittest discover -s tests -p 'test_*.py'`
- per-module count: `grep -cE '^\s*def test_' tests/test_agent_loop_*.py`
- 변이 증명: `runner.py` 백업 → `Edit`로 의도적 변이 → focused 회귀 → `cp` 원복 (working tree clean 확인)
- 패턴 sweep: `grep -rn "next_step_budget_decision" services/`
- unused import: `grep -n "field(" services/application/app/agent_loop/runner.py`
- 리터럴은 직접 Read로 행 단위 교차(`runner.py`, `resolution.py`, `budget.py`, `completion.py`, `parser.py`, `decision.py`, 계약 문서).

## Findings

### F1. composition 순서 — 계약과 일치(PASS)

runner `run()`(`runner.py:100-181`)의 실행 순서가 flat-loop-gate의 계약 순서와 정확히 일치한다.

| 단계 | code | 계약 근거 |
|---|---|---|
| provider 호출 전 budget check | `runner.py:111-117`(`next_step_budget_decision(needs_iteration=True)`) | §budget matrix iteration 행: "다음 provider 호출이 한도를 넘기기 전 차단" |
| iteration 기록(시도 1회) | `runner.py:119`(`record_iteration()`) | §차원: "retry도 각각 1회" — retry는 `continue` 후 동일 line 재진입 |
| provider call + retry | `runner.py:122-145` | §retry 우선순위 |
| usage 기록(F1 방어) | `runner.py:147-154`(`record_tokens`, `InvalidProviderUsage`→`provider_error`) | §차원: missing/invalid usage 0 보정 금지 → `provider_error` |
| post-accounting budget check(completion **전**) | `runner.py:156-162`(`needs_iteration=False` → token/deadline) | §차원: "응답 반영 직후 검사; 초과 응답은 성공으로 채택하지 않음" |
| parse self_report | `runner.py:164-168` | §completion §211 wire 형식 |
| judge completion | `runner.py:170-175` | §공통 판정(하이브리드) |

핵심: post-accounting budget check(`:156`)가 parse/completion(`:164-175`) **앞에** 있다. 이 순서가 I2 forward-lock의 실현이다.

### F2. boundary matrix(spec → code → test 매핑) — runner-level 빈 칸 없음(4종은 원시 레벨 lock, I3 비고)

runner slice의 **고유 계약**(순서 + I2 + retry non-free) 분기는 모두 runner-level 회귀에 매핑된다.

| # | 계약 분기 | code 경로 | 회귀 테스트 | lock |
|---|---|---|---|---|
| 1 | token overrun → completion 전 `budget_exhausted`(under-strict) | `runner.py:156-162` | `test_token_overrun_is_budget_exhausted_before_completion` | ✓ 변이(F3) |
| 2 | `== limit` → `completed`(over-strict) | `runner.py:156` 허용 + `:170-175` | `test_equal_token_limit_can_complete` | ✓ |
| 3 | retry가 iteration budget 소진 시 `budget_exhausted` + 원래 literal 보존(under-strict) | `runner.py:126-145` | `test_provider_retry_consumes_iteration_budget` | ✓ 변이(F3) |
| 4 | cap·budget 남으면 retry → `completed`(over-strict) | `runner.py:137-140` `continue` | `test_provider_retry_can_complete_when_iteration_budget_remains` | ✓ |
| 5 | `finalize` + 산출물 → `completed` | `runner.py:170-175` | `test_finalize_response_completes_after_self_report_parse` | ✓ |
| 6 | `defer` → `awaiting_review` | `runner.py:170-175`(judge `or` fallthrough) | `test_defer_response_awaits_review` | ✓ |
| 7 | invalid self_report → `provider_error` | `runner.py:164-168`(`exc.decision`) | `test_invalid_self_report_maps_to_provider_error` | ✓ |

trace 주장도 고정: `test_finalize...`가 `[event.kind] == ["provider_call","self_report","completion"]`을 단언해 event 순서/종류를 잠근다.

### F3. load-bearing guard 양방향 변이 증명 — PASS(둘 다 입증)

**변이 A — I2 forward-lock 순서**: post-accounting budget check(`:156-162`)를 completion 판정(`:170-175`) **뒤로** 이동.
- 결과: `test_token_overrun_is_budget_exhausted_before_completion` **FAIL** — trace에 `self_report`가 누출(`['provider_call','self_report','completion','budget']`). over-limit content가 completion까지 도달해 `assertNotIn("self_report")` 위반.
- over-strict 케이스(`test_equal_token_limit_can_complete`)는 영향 없음(PASS 유지).
- 의미: 순서가 load-bearing. budget check가 completion 앞에 있지 않으면 over-token 응답이 `completed`로 위장될 수 있다. under-strict 방향 입증 완료.

**변이 B — retry budget gating**: retry except block의 `budget_permits_retry`(`:126-128`)를 `True` 고정(budget gate 우회).
- 결과: `test_provider_retry_consumes_iteration_budget` **FAIL** — retry가 무료 경로가 되어 `completed`로 종료, `preserved_error_literal`이 `"provider_error"`가 아닌 `None`.
- over-strict 케이스(`test_provider_retry_can_complete_when_iteration_budget_remains`)는 영향 없음(PASS 유지).
- 의미: retry가 iteration budget을 소비함이 load-bearing. §retry "retry는 별도 무료 경로가 아니다" under-strict 방향 입증 완료.

두 변이 후 모두 `runner.py` 원복 → 137개 green 재확인 + `git diff --stat` 공백(working tree clean).

### F4. spec ↔ implementation 리터럴 일치 — PASS

- decision 7종(`decision.py:15-22`) = 계약 §종료 decision literal(`flat-loop-gate.md:138-146`) 문자열 그대로. 상호 배타는 한 run당 정확히 하나의 return path로 실현(runner의 모든 종료가 `AgentLoopRunResult(decision=...)` 단일 return). ✓
- `SelfReport.FINALIZE/DEFER`(`completion.py:38-39`) = 계약 허용값. ✓
- `preserved_error_literal = "provider_error"`(`resolution.py:92-95` `preserved_literal=error_decision.value`, `error_decision=LoopDecision.PROVIDER_ERROR`(`:52-53`)) = 계약 "원래 오류 literal을 trace에 보존". `test_provider_retry_consumes_iteration_budget`이 `"provider_error"` 단언으로 고정. ✓
- 예외→decision uniform 매핑: `InvalidProviderUsage.decision=PROVIDER_ERROR`(`budget.py:48`), `InvalidSelfReport.decision=PROVIDER_ERROR`(`parser.py:25`), `InvalidBudgetPolicy.decision=BLOCKED`(`budget.py:36`). runner는 이들을 `exc.decision`로 그대로 전달(`:154,:168`). ✓
- token `== limit` 허용 / `> limit` 거부: `budget.py:181-182` `is_token_budget_exceeded → self._total_tokens > max`(`>` 비교). `==`는 허용. 계약 "누적값이 한도와 같고 … completed가 가능하다. 초과하면 budget_exhausted" 일치. ✓

### F5. 회귀 직접 재실행 + 보고 숫자 재계산 — PASS(전체 137 일치) / **I1: focused 숫자 부정합 발견**

- `python3 -m unittest discover -s tests -p 'test_*.py'` → **Ran 137 tests ... OK**. worker/HANDOFF 보고 137과 일치.
- per-module 실측: decision 4 + budget 29 + registry 20 + completion 6 + parser 9 + resolution 18 + runner 7 = **93**.
- **I1(문서 결함)**: `implementation-plan.md`(b118e15 갱신분)은 "agent_loop focused **84**개 양방향 회귀 통과(decision 4 + budget 29 + registry 20 + completion 6 + parser 9 + resolution 18 + runner 7)"라고 기록. 괄호 안 breakdown 합은 **93**인데 본문 숫자는 **84**. `84 = 77(직전 slice 합) + 7(runner)`이며 **parser 9개를 더하지 않은 산술 오류**. 실측 93과 불일치.
  - HANDOFF `:79`의 "focused runner/parser/completion/resolution 40개"(=9+6+18+7 ✓)와 "전체 discovery 137개"(✓)는 정확. 부정합은 implementation-plan.md 본문 숫자 1곳만.
  - "보고 숫자 재계산 없음" 사례 — envelope claim을 독립 재검증한 결과 실제 값은 93.

### F6. 패턴 sweep — PASS

- `grep -rn "next_step_budget_decision" services/`: 정의(`resolution.py`) + runner 3 호출점(`:111,:127,:156`)만. **동일 composition/ordering pattern의 인접 중복 사이트 없음**. runner가 유일한 provider-call composition 층이므로 I2 ordering bug가 반복될 곳이 없다.
- `AgentLoopRunner` 정의는 `runner.py` 단일. `decision.py`/`registry.py`는 `grep` "Runner" comment 매치일 뿐 중복 composition layer 아님.

### F7. parser slice(02acd3b) spot-check — PASS(기존 독립 검증과 합치)

- `parser.py` + `test_agent_loop_parser.py` 9개 분기(top-level finalize/defer parse; missing/typo`"done"`/case`"Finalize"`/non-string`true,null`/non-json`"not-json"`/non-object`"[]"`/artifact nested 전부 거부)가 계약 §211 열거값과 1:1. 이미 `self_report_parser.md`(합격)에서 독립 검증됐고 본 spot-check로 재확인.
- `completion.py`의 02acd3b 변경은 docstring 3행만(`git show 02acd3b -- completion.py`). `judge_completion` 본문·`SelfReport` enum 무변경. 동작 영향 없음.

### F8. 문서 갱신 반영 — PASS(I1 제외)

- `system-contract-sot.md`(b118e15 +1행): "AgentLoopRunner provider composition | 구현·**자체 회귀** 완료 | parser.py, runner.py …; I2 forward-lock". 정직하게 "자체 회귀"로 표기(독립 검증 아님). ✓
- `implementation-plan.md`(b118e15): changelog 행에 5단계 순서 + I2 forward-lock 양방향 회귀 명시. ✓(단, 본문 숫자 84는 I1 결함)
- `HANDOFF.md:43`(Active Decisions), `:79`(Verification), `:124`/`:137`(Project Structure)에 runner slice 반영. ✓
- spec-silent-but-code-enforced gap: 없음. runner가 계약에 없는 종료/허용을 추가하지 않는다. domain tool-call branch와 task별 artifact schema는 명시적으로 Slice 1·3 이후로 scope-out(`runner.py:1-12` docstring, HANDOFF `:43,:49-50`).

## Issues / Risks

- **I1(비차단, 문서 결함 — 실제 값)**: `implementation-plan.md`의 "focused 84개"는 실측 93과 불일치(parser 9 누락 산술 오류). 코드/계약/테스트 동작에 영향 없으나 envelope claim 부정확. 권고: 본문 숫자를 `93`으로 수정(F5).
- **I2(비차단, dead import)**: `runner.py:16` `from dataclasses import dataclass, field`에서 `field`가 사용되지 않는다(모든 dataclass가 plain field). worker 자신의 변경이 도입한 미사용 import. 권고: `field` 제거.
- **I3(비차단, 계층화 coverage 비고 — 빈 칸 아님)**: 4개 종료 경로가 runner에서 **변환 없는 verbatim passthrough**로, 원시 레벨에서만 양방향 lock된다. (a) non-retryable → `provider_error`(`resolution.py:83-84`, `test_non_retryable_provider_terminates_immediately`), (b) cap 소진 → `provider_error`(`resolution.py:86-87`, `test_retryable_provider_with_cap_exhausted_is_provider_error`), (c) wall-clock deadline → `budget_exhausted`(`budget.py:163-166` + `resolution.py:116-117`, `test_wall_clock_deadline_blocks`/`test_deadline_reached_only_at_or_after_the_limit`), (d) 산출물 없는 finalize → `awaiting_review`(`completion.py:52-54`, completion 6개 회귀). runner는 이들을 `exc.decision`/`retry_outcome.decision`로 그대로 전달만 하므로 **runner 고유 계약의 빈 칸이 아니다**. 단, runner의 public envelope(`AgentLoopRunResult`)을 원시 테스트에 의존 없이 자체 잠그려면 (b) cap 소진→`provider_error`(`preserved_literal=None`), (d) 산출물 없는 finalize→`awaiting_review` 경로의 runner-level test 2종 보태면 "public surface를 겨냥" 원칙에 더 정렬됨. 선택적 강화.
- **I4(비차단, trace 대칭성 — 화면)**: retry가 budget에 막혀 종료할 때 terminal decision은 `budget_exhausted`이나 "budget" trace event가 발화되지 않는다(해당 decision이 `next_step_budget_decision`이 아닌 `resolve_retry`에서 옴). 정보는 `preserved_error_literal="provider_error"`로 전달되며 계약이 trace event 종류를 규정하지 않으므로 위반 아님.
- **I5(비차단, forward-lock 강화 후보)**: "retry가 iteration slot을 소비"는 정성적으로 입증됐다(max_iter=1 → retry 차단; max_iter=2 → retry 1회 허용). code 구조상 `record_iteration`이 retry를 포함한 매 loop iteration마다 무조건 호출되므로 정확하다. 단, retry_cap ≥ 2에서 "N iteration 안에 들어가는 retry 수"를 정량 입증하는 test(예: max_iter=2, retry_cap=2, 연속 retryable 2회 → 3번째 시도가 iteration budget에 막혀 `budget_exhausted`)는 없다. 선택적 강화.
- **spec-silent-but-code-enforced gap**: 없음(F8).
- **계약 자기모순**: 본 slice 범위의 flat-loop-gate §retry/§Budget/§completion 내 규칙 ↔ matrix ↔ changelog 간 모순 없음.

## Verdict

**합격(Pass).**

load-bearing 이유:
1. composition 순서가 계약과 정확히 일치하며(F1), 핵심 순서(post-accounting budget check가 completion 앞)가 I2 forward-lock을 실현한다.
2. I2 forward-lock과 retry non-free 두 load-bearing guard를 **양방향 변이 증명**으로 입증했다(F3). under-strict(망가뜨리면 FAIL)/over-strict(정상 케이스 유지) 양방향 모두 확인.
3. runner 고유 boundary matrix에 빈 칸 없이 7분기 전부 runner-level 회귀로 lock(F2). spec↔code 리터럴이 행 단위로 일치(F4).
4. 전체 137개 독립 재현(F5). parser slice spot-check로 기존 독립 검증과 합치 확인(F7).
5. 패턴 sweep에서 동일 ordering bug의 인접 중복 사이트 없음(F6).
6. spec-silent-but-code-enforced gap·계약 자기모순 0건(F8).

비차단 항목: I1(문서 숫자 84→93, 수정 권고)·I2(dead import `field`, 제거 권고)는 코드 동작에 영향 없는 정리 항목. I3/I4/I5는 lock이 비어있지 않은 상태에서의 선택적 강화 비고(빈 칸이 아니므로 verdict에 영향 없음).

## Outstanding items

- 본 검증은 코드/테스트 동작을 수정하지 않았다(변이 증명 후 전부 원복, working tree clean, 137 green). I1/I2의 실제 수정은 소유자 결정 사항.
- runner의 domain tool-call branch와 task별 `artifact_present` schema 평가는 명시적으로 Slice 1·3 이후 범위(`runner.py:1-12`, HANDOFF `:49-50`). 본 slice는 provider 응답 종료 한 terminal response에 한정하며, 실제 tool handler 연결 시 해당 Phase payload/handler와 함께 별도 slice·별도 검증이 필요하다.
- I3 권고(runner-level test 2종 보태) 또는 I5 권고(정량 retry-cap test)를 소유자가 수용할 경우, 본 기록 verdict는 합격을 유지하되 F2/I3 비고를 회신 갱신 가능.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# focused runner 회귀(worker 보고 7개)
python3 -m unittest tests.test_agent_loop_runner -v

# 전체 회귀(worker 보고 137개)
python3 -m unittest discover -s tests -p 'test_*.py'

# per-module count(I1 재계산: 합 = 93, 계획 본문 84와 불일치)
for f in decision budget registry completion parser resolution runner; do
  grep -cE '^\s*def test_' tests/test_agent_loop_${f}.py
done

# 패턴 sweep(next_step_budget_decision = runner 3 호출점만, 중복 composition 사이트 없음)
grep -rn "next_step_budget_decision" services/

# I2 dead import 확인(field( 사용처 없음)
grep -n "field(" services/application/app/agent_loop/runner.py

# 변이 증명 A(I2 순서): runner.py에서 post-accounting budget check(:156-162)를
#   completion 판정(:170-175) 뒤로 이동 → test_token_overrun_is_budget_exhausted_before_completion FAIL
# 변이 증명 B(retry non-free): retry block의 budget_permits_retry(:126-128)를 True 고정
#   → test_provider_retry_consumes_iteration_budget FAIL
# (각 변이 후 runner.py 원복 → 137 green 재확인)
```
