# 검증 기록: AgentLoopRunner A1 (decision + budget 계약 회귀)

## Subject metadata

- **날짜**: 2026-06-24
- **요청자**: 소유자(entangelk) — "다음 작업 검증해줘. 복원 완료, 63개 전부 통과, whitespace clean입니다." (Slice A1 완료 보고)
- **검증자**: Claude(독립 검증 세션)
- **대상 slice/artifact**: AgentLoopRunner 첫 sub-slice **A1** — `LoopDecision`(종료 decision 7종) + `BudgetPolicy`/`BudgetTracker`(5차원 budget)의 fake/인프라 없는 결정적 회귀 구현. 사용자 입도 결정 "decision+budget 먼저, 더 작게".
- **canonical spec reference**: `docs/plans/flat-loop-gate.md`(HEAD = `aba3274`, working tree 미수정) — §종료 decision literal(138-176), §Budget 계약(75-122, 특히 89 하한 규칙·91 token post-accounting·113-122 budget boundary matrix).
- **source of work**: working tree, uncommitted. 신규 `services/application/app/agent_loop/{decision,budget}.py`(및 패키지 `__init__`), `tests/test_agent_loop_{decision,budget}.py`; 갱신 `implementation-plan.md`, `HANDOFF.md`, `CHANGELOG.md`, `work_log.md`. HEAD = `aba3274`.

## Scope

A1의 명시적 범위는 **metering primitives + policy validation**. budget→decision 매핑, retry, signature normalization, completion 판정, loop 합성은 A2/A3/후속 slice로 연기됨(module/test docstring 명시). 검증 surface:

1. **코드-계약 일치성** — `decision.py`/`budget.py` vs `flat-loop-gate.md` §종료 decision literal + §Budget 계약
2. **회귀 테스트 boundary matrix 매핑** — 19개 테스트가 should-fire/should-NOT-fire 분기를 1:1로 lock하는지, 양방향 guard 존재, 빈 셀 여부
3. **63/63 통과 재현** — 워커 "기존 44 + 신규 19" 주장 직접 실행
4. **변이 증명(mutation) 재현** — 워커 주장(token `>`→`>=` over-strict FAIL, iteration `<`→`<=` under-strict FAIL) 및 "직접 복원 완료" 검증
5. **whitespace clean** — trailing/CRLF
6. **인덱스/상태 문서 정합** — HANDOFF tree/CHANGELOG/work_log/implementation-plan
7. **부가**: flat-loop-gate.md R1/R2/R3 보강(이전 검증 conditional pass 조건)이 A1 인접 커밋에서 실제 반영됐는지

**범위 밖**: 실제 tool handler, Mongo/ES/Chroma 통합(Slice 1·3 이후), budget→`budget_exhausted` decision 매핑(A3), retry 우선순위(A3), signature normalization(A2), completion 판정(A3).

## Methodology

모든 claim은 primary source에서 재도출. 사용 명령:

- `git status --porcelain` / `git log --oneline` — 변경 범위·커밋 위치 확인
- `find services/application -type f` / `ls services/` — 패키지 구조 검증(llm_gateway와 동일 레이아웃)
- `Read decision.py` / `Read budget.py` — 코드 전체 판독, `flat-loop-gate.md` literal/규칙과 라인 단위 대조
- `Read test_agent_loop_decision.py` / `Read test_agent_loop_budget.py` — boundary matrix 분기 매핑·양방향 guard 점검
- `grep -rc "def test" tests/test_*.py`(신규 2개 제외) — 기존 테스트 개수(44) 재계수
- `python3 -m pytest tests/ -q` — 전체 회귀 직접 실행
- `grep -nP '[ \t]+$'` + `file` — trailing whitespace/CRLF 점검
- 변이 재현: `cp budget.py /tmp/budget.py.orig`(백업) → `sed -i` 변이 → `pytest tests/test_agent_loop_budget.py::<Class> -q` → `cp /tmp/budget.py.orig budget.py`(복원) → `diff -q` IDENTICAL 확인 → 전체 재실행
- `git diff --stat HEAD -- docs/plans/flat-loop-gate.md` + `sed -n '225,237p'` + `grep finalize|defer|횡일관` — flat-loop-gate.md R1/R2/R3 보강 실제 반영 여부

## Findings

### 1. 코드-계약 일치성

- **`LoopDecision` 7종**(`decision.py:15-22`) = `flat-loop-gate.md:138-146` 정확 일치: `completed`/`awaiting_review`/`blocked`/`budget_exhausted`/`invalid_tool_arguments`/`tool_error`/`provider_error`. StrEnum로 raw literal과 문자열 비교 가능(trace payload 소비 계약 충족).
- **`BudgetPolicy` 하한 규칙**(`budget.py:59-77`) = `flat-loop-gate.md:89` 일치: positive 3종(iteration/wall-clock/token)은 `>= 1`(`:61`), tool 2종(tool-call/repeated-call)은 `>= 0`(`:65`), `allows_tools=True` + tool budget `< 1` 거부(`:69-73`), `allows_tools=False` + tool budget `!= 0` 거부(`:74-77`). **양방향 모순 거부**.
- **bool 거부**(`budget.py:31-34`, `_is_int`): bool은 int subclass라 명시 거부 → `True` budget이 1로 오인되지 않음. 워커 보고 사실.
- **`BudgetTracker` 계측** = `flat-loop-gate.md:113-122` budget boundary matrix 일치:
  - iteration `can_start_iteration = _iterations < max`(`:121-122`) → N번째 허용/N+1 차단 ✓
  - tool-call `can_start_tool_call = _tool_calls < max`(`:135-136`) → N/N+1 ✓
  - repeated-call `can_start_repeated_call = sig_count < max`(`:139-140`), `record_tool_call`이 tool_calls + sig count 동시 증가(`:142-146`) → 같은 sig N/N+1 ✓
  - **token post-accounting** `is_token_budget_exceeded = _total_tokens > max`(`:131-132`) → `==limit` 허용/`>limit` 초과. `flat-loop-gate.md:91`("누적 == limit 완료 허용; > limit budget_exhausted") 정확 일치 ✓
  - wall-clock `deadline = now + max_wall_clock_ms`(`:113`), `is_deadline_reached = now >= deadline`(`:118`), `now_ms` 주입 가능(`:101`) → 결정적 테스트 가능 ✓

### 2. 회귀 테스트 boundary matrix 매핑(19개)

A1 scope(metering + policy) 내 모든 분기에 1:1 매핑, 빈 셀 없음:

| boundary matrix 행(`flat-loop-gate.md`) | test(should-fire / should-NOT-fire) | 양방향 |
|---|---|---|
| iteration N 허용/N+1 차단·과잉차단 금지 | `IterationBudgetTest.test_allows_up_to_n_then_blocks_n_plus_one`(94-98) | ✓ 한 test에 양방향 |
| token ==limit 허용·>limit 초과 | `test_accumulated_equal_to_limit_is_not_exceeded`(over-strict) + `test_accumulated_over_limit_is_exceeded`(under-strict) | ✓ 분리 |
| wall-clock deadline 도달·in-budget 비차단 | `test_deadline_reached_only_at_or_after_the_limit`(99/100/101) + `test_deadline_check_before_start_is_an_error` | ✓ |
| tool-call N/N+1 | `ToolCallBudgetTest.test_allows_up_to_n_then_blocks_n_plus_one` | ✓ 양방향 |
| repeated-call 같은 sig N/N+1·다른 sig 비반복 | `test_same_signature_allows_n_then_blocks_n_plus_one` + `test_different_signature_is_not_counted_as_a_repeat`(over-strict) | ✓ |
| policy positive 하한·음수·bool·양방향 모순 | `BudgetPolicyValidationTest` 7 test(positive 하한 0 거부, 음수 거부, bool 거부, allows_tools=True+0 거부, allows_tools=False+!=0 거부) | ✓ |
| decision 7종 개수·값·유일성·문자열비교 | `LoopDecisionLiteralTest` 4 test | ✓ |

scope 밖 분기(retry 무료 아님·budget→budget_exhausted 매핑·invalid-args counting·provider timeout vs deadline·missing-usage → provider_error)는 `budget.py` docstring(`:8-11`)과 `test_agent_loop_budget.py` docstring(`:9-12`)이 A2/A3로 명시 연기. **A1 scope 내 빈 셀 없음**.

### 3. 63/63 통과 재현

- 기존 테스트 재계수: `test_httpx_transport`(6) + `test_llama_provider_client`(8) + `test_llm_gateway_payload`(12) + `test_llm_provider`(4) + `test_llm_provider_errors`(6) + `test_llm_transport_mapping`(8) = **44**. 워커 "기존 44" 일치.
- `python3 -m pytest tests/ -q` → **`63 passed, 44 subtests passed`**. 신규 19 = 63. 워커 보고 사실.

### 4. 변이 증명(mutation) 재현 — 핵심 독립 확인

워커가 "untracked 파일이라 git checkout 복원 실패, 직접 복원 후 재검증 완료"라고 한 부분을 cp 백업 기반으로 재현:

- **변이 1(token `>` → `>=`)**: `budget.py:132` 변이 후 `TokenBudgetTest` → `test_accumulated_equal_to_limit_is_not_exceeded` **FAIL**(`AssertionError: True is not false`, `:106`). `==limit`을 초과로 만드는 over-correction을 over-strict guard가 잡음. 워커 보고 정확.
- **변이 2(iteration `<` → `<=`)**: `budget.py:122` 변이 후 `IterationBudgetTest` → `test_allows_up_to_n_then_blocks_n_plus_one` **FAIL**(`:98`, N+1 위치에서 차단되어야 하는데 허용). under-strict guard 잡음. 워커 보고 정확.
- **복원 정확성**: 각 변이 후 `cp /tmp/budget.py.orig` 복원 → `diff -q` **`IDENTICAL (복원 완벽)`** → 전체 63/63 재확인. 워커의 "직접 복원"이 바이너리 정확했음을 독립 입증(untracked여서 git이 추적 못 한 것과 무관).

### 5. whitespace clean

- `grep -nP '[ \t]+$'` → 4개 신규 파일 모두 trailing whitespace 없음.
- `file` → 4개 파일 모두 "UTF-8 text", CRLF 없음. 워커 보고 사실.

### 6. 인덱스/상태 문서 정합

- `HANDOFF.md` project tree에 `services/application/app/agent_loop/{decision,budget}.py` 추가, Active Decisions A1 행 추가, Next Tasks 재번호화(A2/A3/benchmark). `work_log.md` A1 Completed subsection + Decisions(사용자 입도 결정) + Next steps 일치. `implementation-plan.md` "진행 중: Slice 4 A1" subsection 추가. `CHANGELOG.md` A1 entry 추가. **모두 상호 일치, surgical**.

### 7. 부가: flat-loop-gate.md R1/R2/R3 보강 실제 반영 확인

이전 검증(`completion_criteria_contract.md`, conditional pass — R1/R2/R3)의 조건이 HEAD `aba3274`에서 해소됨을 확인(working tree = HEAD, 미수정):
- **R1 해결**: `:233` context_search completed 행에 "Gate reject여도 completed" over-strict guard 추가 + `:227` "모든 task의 completed 행은 over-strict guard 포함" 선언. 세 completed 행(`:231/:233/:235`) 모두 보유.
- **R2 해결**: completion matrix가 task × {completed, awaiting_review} 횡일관 2행(analysis_compare `:231-232`, context_search `:233-234`, writing_generate `:235-236`).
- **R3 해결**: `:211` self-report = loop 종료 채널의 `finalize` vs `defer`, candidate status = 산출물 데이터 채널, "두 채널은 직교".
- HANDOFF Active Decisions와 work_log의 "독립 검증 R1/R2/R3 보강 완료" 주장은 flat-loop-gate.md 실제 내용과 **일치(사실)**. 내 초기 의심("HANDOFF만 고치고 flat-loop-gate는 안 고쳤다")은 **기각**.

## Issues / Risks

> 비차단. A1 scope(metering + policy)는 충족.

- **F1(경미·A3 추적)** — `record_tokens` 음수/None 방어 부재: `budget.py:128-129`는 단순 누적. 음수 prompt/completion이 들어오면 누적 왜곡, None이면 TypeError. 계약 `flat-loop-gate.md:91`("usage 누락·invalid → provider_error, 0 보정 금지")의 검증은 Gateway 계층 소관이고, A1은 valid 값을 받는다고 가정(module docstring 명시). 따라서 A1 defect 아님. 단, A3(loop 합성)에서 Gateway→budget 연결 시 음수/None/invalid usage 방어가 회귀로 lock되어야 함 — outstanding(A3 scope).

- **F2(경미)** — wall-clock `start()` 전 `is_deadline_reached` RuntimeError(`budget.py:116-117`, test `:129-132`)이 `flat-loop-gate.md`에 명시 없음. spec-silent code behavior. runner가 항상 `start()`를 선행하므로 실제 미발생 경로(defensive). 결함 아님, 계약 문서화 권장(선택).

- **F3(정보)** — **A1 완료 보고(사용자에게 전달된 요약)가 flat-loop-gate.md R1/R2/R3 보강(aba3274)을 언급하지 않음.** HANDOFF/work_log에는 기록됨. 기술적 결함은 아니나(A1 코드 작업과 R1/R2/R3 문서 보강은 별개), 보고 completeness 차원에서 인접 결정 변화가 누락됨. 영향 없음 — 이전 검증 conditional pass 조건이 aba3274에서 이미 해소됐음을 본 검증으로 확인.

- **F4(경미)** — `max_tool_calls=1` 경계값의 명시 허용 테스트 부재. `max_repeated_calls=1`은 `RepeatedCallBudgetTest`(`:158`)에서 암묵 검증되나, `max_tool_calls=1`은 명시 테스트 없음. `budget.py:70`(`max_tool_calls < 1` 거부)가 1 허용을 보장하므로 **빈 셀 아님**. 경계값 보강 후보.

- **F5(정보·A3 추적)** — boundary matrix의 "invalid args는 tool-call count 안 함", "retry 무료 호출 금지", "budget→budget_exhausted 매핑", "budget 내 provider timeout은 provider_error" 분기는 모두 A2/A3 scope로 docstring 명시 연기. consistent.

## Verdict

**합격(pass)**.

하중 이유(load-bearing reasons):
- **코드-계약 일치**(Findings 1): `LoopDecision` 7종, `BudgetPolicy` 5차원 하한·bool·양방향 모순 검증, `BudgetTracker` 5차원 계측(특히 token post-accounting `==limit`/`>limit`)이 `flat-loop-gate.md`와 라인 단위로 일치.
- **회귀 lock 완결**(Findings 2): A1 scope 내 boundary matrix의 모든 should-fire/should-NOT-fire 분기에 1:1 매핑, 양방향 guard, 빈 셀 없음. scope 밖 분기는 docstring이 A2/A3로 명시 연기.
- **63/63 재현**(Findings 3): 기존 44 + 신규 19 직접 실행 확인.
- **변이 증명 재현**(Findings 4): 두 변이 모두 예상 테스트를 FAIL시키고(over-strict/under-strict 양방향), 복원이 `diff IDENTICAL`로 완벽. 워커 "직접 복원 완료" 주장을 독립 입증.
- **whitespace clean**(Findings 5), 인덱스/상태 문서 정합(Findings 6).
- 이전 검증 R1/R2/R3 conditional pass 조건이 `aba3274`에서 해소됨 확인(Findings 7) — A1 인접 계약 상태 건전.

**불합격/조건부 사유 아님인 이유**: F1/F5는 A3 scope로 명시 연기된 항목(A1 범위 밖), F2는 defensive 비발생 경로, F3은 보고 completeness(기술 영향 없음), F4는 코드가 보장하는 경계값의 테스트 보강 후보(빈 셀 아님). blocking defect(코드-계약 불일치, trace 불가능 분기, 변이 미감지) 없음.

## Outstanding items

- **미커밋 변경**: `services/application/`(untracked dir), `tests/test_agent_loop_{decision,budget}.py`(untracked), `implementation-plan.md`/`HANDOFF.md`/`CHANGELOG.md`/`work_log.md`(modified). 소유자 커밋 승인 대기. 본 검증은 커밋 전 working tree 기준.
- **A3 선행 lock 권장**(F1): A3 구현 시 Gateway→budget usage 전달에서 음수/None/invalid 방어를 회귀로 lock. 계약 `flat-loop-gate.md:91`이 이를 요구하나 A1 metering은 가정에 의존.
- **downstream unblock**: A1 완료로 A2(tool registry·argument validation·signature normalization) 착수 가능.
- **Gemma Q4 benchmark**(Next Task 3): hardware 미확정, 여전히 blocking. 본 검증과 무관.

## Reproduction

```bash
# 1. 변경 범위·커밋 위치
git status --porcelain
git log --oneline -3 -- docs/plans/flat-loop-gate.md

# 2. 전체 회귀 (63/63 재현)
python3 -m pytest tests/ -q
# 기존 테스트 개수 재계수
grep -rc "def test" tests/test_httpx_transport.py tests/test_llama_provider_client.py \
  tests/test_llm_gateway_payload.py tests/test_llm_provider.py tests/test_llm_provider_errors.py \
  tests/test_llm_transport_mapping.py

# 3. 코드-계약 일치 (Read 후 라인 대조)
# Read services/application/app/agent_loop/decision.py  (flat-loop-gate.md:138-146)
# Read services/application/app/agent_loop/budget.py    (flat-loop-gate.md:89, 91, 113-122)

# 4. whitespace
grep -nP '[ \t]+$' services/application/app/agent_loop/decision.py \
  services/application/app/agent_loop/budget.py \
  tests/test_agent_loop_decision.py tests/test_agent_loop_budget.py   # (no output = clean)
file services/application/app/agent_loop/*.py tests/test_agent_loop_*.py

# 5. 변이 증명 (백업 → 변이 → FAIL → 복원 → IDENTICAL)
cp services/application/app/agent_loop/budget.py /tmp/budget.py.orig
# 변이 1: token over-strict guard
sed -i 's/> self\._policy\.max_total_tokens/>= self._policy.max_total_tokens/' services/application/app/agent_loop/budget.py
python3 -m pytest tests/test_agent_loop_budget.py::TokenBudgetTest -q   # expect 1 FAIL
cp /tmp/budget.py.orig services/application/app/agent_loop/budget.py
# 변이 2: iteration under-strict guard
sed -i 's/< self\._policy\.max_iterations/<= self._policy.max_iterations/' services/application/app/agent_loop/budget.py
python3 -m pytest tests/test_agent_loop_budget.py::IterationBudgetTest -q   # expect 1 FAIL
cp /tmp/budget.py.orig services/application/app/agent_loop/budget.py
diff -q /tmp/budget.py.orig services/application/app/agent_loop/budget.py   # expect IDENTICAL
python3 -m pytest tests/ -q   # expect 63 passed

# 6. flat-loop-gate.md R1/R2/R3 보강 반영 (이전 검증 조건 해소)
git diff --stat HEAD -- docs/plans/flat-loop-gate.md   # (empty = working tree = HEAD)
sed -n '211p;225,237p' docs/plans/flat-loop-gate.md
```
