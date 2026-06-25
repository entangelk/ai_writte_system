# 검증 기록 — AgentLoopRunner A3 (Completion 판정 + Retry/Budget 합성 + F1 Usage 방어)

## Subject metadata

- 일자: 2026-06-25
- 요청자: 사용자("작업 AI가 작업한 부분에 대해서 검증하고 의심해줘 … A3 구현을 완료했습니다")
- 검증자: 독립 검증 AI(Claude Code)
- 대상 slice/artifact: A3 sub-slice
  - `services/application/app/agent_loop/completion.py`(신규)
  - `services/application/app/agent_loop/resolution.py`(신규)
  - `services/application/app/agent_loop/budget.py`(`InvalidProviderUsage` + `_require_token_count` + `record_tokens` F1 방어 추가분; A1 본체는 제외)
  - `tests/test_agent_loop_completion.py`, `tests/test_agent_loop_resolution.py`, `tests/test_agent_loop_budget.py`(F1 +8)
- canonical spec reference:
  - `docs/plans/flat-loop-gate.md` 상태 `Draft`(completion/budget/retry slice 2026-06-24 소유자 확정)
  - §task별 completion criteria 계약(192–236): §공통 판정 하이브리드(196–203), §완결된 산출 vs loop 미해결(205–211), §completion boundary matrix(225–236)
  - §Budget 계약(75–102): token post-accounting + missing usage→`provider_error`(91)
  - §retry와 terminal decision 우선순위(104–111)
  - §budget boundary matrix(113–122)
  - §종료 decision literal(136–148), §boundary matrix completed/budget_exhausted 행(182–187)
  - `docs/plans/implementation-plan.md` A3 항
- source of the work being verified: working tree, uncommitted. `git status --porcelain`: `?? completion.py`, `?? resolution.py`, `?? tests/test_agent_loop_completion.py`, `?? tests/test_agent_loop_resolution.py`, `M budget.py`, `M tests/test_agent_loop_budget.py`. HEAD `c5202e8`.
- 구현 환경: Python 3 (WSL2 /mnt/d; 검증 전체를 `-B`로 수행해 stale `__pycache__` 회피).

## Scope

A3는 loop를 구동하거나 provider/tool을 호출하지 않는 **순수 결정 원시 함수**만 잠근다(각 모듈 docstring 명시). 점검 표면:

1. spec contract — `flat-loop-gate.md` §completion criteria, §retry 우선순위, §budget boundary matrix, §Budget 계약 token 행
2. completion 판정 — `judge_completion` 하이브리드(구조∧self-report), 출력 집합 {COMPLETED, AWAITING_REVIEW}
3. retry 합성 — `resolve_retry` 4분기(non-retryable / cap 소진 / budget 허용 retry / budget 차단→budget_exhausted+literal 보존)와 우선순위
4. budget→budget_exhausted 매핑 — `next_step_budget_decision` 5차원, post-accounting `==` 허용 / `>` 차단
5. F1 usage 방어 — `record_tokens`/`InvalidProviderUsage`(missing/negative/non-int/bool 거부, 명시적 0 수용)
6. 내부 일관성 — contract 자기 모순 점검 + boundary matrix 빈 칸 점검
7. 테스트 코드 감사 — boundary matrix cell 역추적, 양방향(under/over-strict) guard 존재
8. 비회귀 + pattern sweep(독자 재수행) — F1 정책 일관성(gateway ↔ loop)

범위 밖(원칙적 deferral, 본 검증에서 결함으로 보지 않음): runner 합성(budget-before-completion 순서 보장·retry 비-무료성·exception→decision 매핑), SelfReport wire 형식, task별 구조 조건의 구체 평가, retry cap 숫자 기본값(Gemma Q4 benchmark 후).

## Methodology

1. **contract scope 먼저 구축**: `flat-loop-gate.md`를 열기 전 A3를 govern하는 섹션(§completion criteria, §retry, §budget boundary matrix, §Budget 계약 token 행)과 그 연쇄 참조만 확정하고 그 안만 정독. tool registry(A2)·Gate 합성·저장 정책은 A3 범위 밖.
2. **boundary matrix(lock list) 구축 후 코드 비교**: contract의 모든 should-fire/should-NOT-fire 분기와 literal(7 decision, `budget_exhausted`, preserved literal `"provider_error"`/`"tool_error"`, `SelfReport.FINALIZE/DEFER`, token `==`/`>` 경계)을 추출한 뒤 구현·테스트에 대입. 빈 칸 없음 점검.
3. **contract 자기 모순 점검**: §retry(106 "retry cap은 필수 policy 값") ↔ BudgetPolicy(A1) 구성 ↔ `resolve_retry(retries_remaining)` 시그니처 교차 점검. §boundary matrix ↔ §종료 decision literal 상호배타성 교차.
4. **spec-silent-but-code-enforced 점검**: 코드가 강제하는 모든 분기가 spec에 명시돼 있는지 역방향 점검.
5. **테스트 코드를 감사 대상으로**: green bar와 별개로 각 assertion이 contract를 pin하는지, under-strict(보고된 버그 재발 가능) + over-strict(정상 케이스 과잉 차단) 양방향 guard, 경계값(`==`/`>`/`0`/음수) parametrization 확인.
6. **작업자 주장을 믿지 않고 재도출**: 117/117, per-module 6/18/25, F1 pattern sweep(gateway 동일 정책), F1 음수/0 양방향을 검증자가 직접 재실행·재실증.
7. **잘못된 코드베이스 함정 교정**: 최초 pattern sweep에서 `/mnt/d/devel/gemma4_12b/.../llama_client.py:183`의 `.get("prompt_tokens", 0)`(missing→0 보정)를 발견했으나, 이는 별개 레포인 참조 구현이며 본 프로젝트 gateway는 `services/llm_gateway/app/client.py:114` `_token_count`임을 확인 후 정정(아래 F1 항).

정확한 명령은 Reproduction에 있다.

## Findings

### 1. Completion 판정 — 하이브리드 AND, 출력 집합 정확 (빈 칸 없음)

`judge_completion(completion.py:42–54)`:

```python
if artifact_present and self_report is SelfReport.FINALIZE:
    return LoopDecision.COMPLETED
return LoopDecision.AWAITING_REVIEW
```

`SelfReport`는 종료 채널 신호 2종만(`FINALIZE="finalize"`, `DEFER="defer"`, completion.py:38–39). 출력은 정확히 {COMPLETED, AWAITING_REVIEW}이며 §13–15 "이 judge는 후보 종료 상태에 도달했을 때 completion 질문에만 답한다"와 일치.

2×2 진리표 전 분기가 테스트로 lock(test_agent_loop_completion.py):

| (artifact_present, self_report) | 구현 결과 | 계약 | 테스트 | 방향 |
|---|---|---|---|---|
| (True, FINALIZE) | COMPLETED | §198 "두 조건 모두" | test_artifact_present_and_finalize_completes_for_every_profile(52–62) | should-fire |
| (True, DEFER) | AWAITING_REVIEW | §203 "자율 조건 미달" | test_defer_is_awaiting_review_for_every_profile(64–71) | should-fire |
| (False, FINALIZE) | AWAITING_REVIEW | §249 "answer 존재=완료" 보강점 | test_finalize_without_artifact_is_not_completed(73–79) | over-strict |
| (False, DEFER) | AWAITING_REVIEW | §203 | test_no_artifact_and_defer_is_awaiting_review(81–86) | under-strict |

진리표 4 cell 전부 커버. 빈 칸 없음. ✓

**over-strict "needs_review status 승격 금지 / Gate reject여도 completed" (§231·§233·§235)**: 이 분기는 judge 시그니처 수준에서 lock된다 — `judge_completion`은 `needs_review`/Gate 결과를 입력으로 받지 않으므로 **위반 경로 자체가 없다**. `artifact_present`는 caller가 사전 평가한 bool이며, 산출물 데이터 채널 불확실성(needs_review/conflict)은 caller가 `artifact_present=True`로 접어넣는다(test:54–56 주석 명시). 따라서 judge-수준 empty cell이 아니라 **서명 수준의 구조적 lock**. per-profile 구조 평가의 구체 의미(`_STRUCTURAL_CONDITION` dict, test:33–37)는 Phase payload schema 확정 시 lock이라는 점은 §211 "구체 wire 형식은 Phase 4 slice에서 확정"으로 spec-sanctioned. ✓

### 2. resolve_retry — 4분기 + cap-소진 우선순위 (양방향 핵심)

`resolve_retry(resolution.py:57–93)` 우선순위:

1. `not retryable` → `error_decision`, literal 없음(81–82)
2. `retries_remaining <= 0`(cap 소진) → `error_decision`, literal 없음(84–85)
3. `budget_permits_next` → retry(decision=None)(87–88)
4. 그 외(cap 남음 + budget 차단) → `BUDGET_EXHAUSTED` + `preserved_literal=error_decision.value`(90–93)

`_error_decision`(51–54): PROVIDER→`PROVIDER_ERROR`, TOOL→`TOOL_ERROR`.

§retry(108–110) 3개 규칙과 정합:
- §108 "non-retryable 즉시 provider_error/tool_error" ↔ 분기 1 ✓
- §109 "retry cap 먼저 소진 시 해당 error decision" ↔ 분기 2 ✓
- §110 "cap 남았지만 budget 막으면 budget_exhausted + 원래 literal 보존" ↔ 분기 4 (`preserved_literal="provider_error"`/`"tool_error"`) ✓

**핵심 양방향 guard — cap 소진이 budget 차단보다 우선**: 분기 2가 분기 4보다 먼저 검사(84 → 90). `test_cap_exhausted_takes_precedence_over_budget_blocked`(test:90–100)가 `retries_remaining=0, budget_permits_next=False` → `PROVIDER_ERROR` + `preserved_literal=None`을 단언. 이는 under-strict(cap 무시하고 budget_exhausted로 빠지는 버그)와 over-strict(budget이 막혔다고 cap-소건 error를 budget_exhausted로 덮어쓰는 버그) **양쪽 모두** 재발 시 실패. ✓

분기 4의 `preserved_literal`은 §176(umbrella provider_error), §172(tool_error) "trace 보존"과 일치. non-retryable/cap-소진 분기에서 literal이 `None`인 것도 §110이 literal 보존을 budget-차단 case에만 명시하므로 정합. ✓

provider/tool 양쪽을 각 분기마다 별도 테스트(NonRetryableTest 2, CapExhaustedTest 3, RetryPathTest 2, BudgetBlockedTest 2 = 9). ✓

### 3. next_step_budget_decision — 5차원 매핑, post-accounting 경계 정확 (양방향)

`next_step_budget_decision(resolution.py:96–123)`:

- `needs_iteration and not can_start_iteration()` → BUDGET_EXHAUSTED(112–113)
- `is_deadline_reached()` → BUDGET_EXHAUSTED(114–115) [항상]
- `is_token_budget_exceeded()` → BUDGET_EXHAUSTED(116–117) [항상]
- `tool_signature` 있을 때 `not can_start_tool_call() or not can_start_repeated_call()` → BUDGET_EXHAUSTED(118–122)
- else `None`(123)

§budget boundary matrix(117–121) 5행과 정합. wall-clock/token은 step 유형 무관 global stop(항상 검사), iteration은 provider call(`needs_iteration`)일 때만, tool 차원은 tool call(`tool_signature`)일 때만 — §Budget 계약 "wall-clock과 token은 global, iteration은 provider call, tool은 tool call" 그대로. ✓

**경계값 양방향**:
- iteration `can_start_iteration` = `_iterations < max`(budget.py:144–145) → N번째 허용, N+1 차단. test_iteration_n_plus_one_blocks(res:156–162) ✓
- token `is_token_budget_exceeded` = `_total_tokens > max`(budget.py:156–157) → `==` 허용, `>` 차단. test_token_equal_to_limit_is_allowed(164–168) + test_token_over_limit_blocks(170–177) — `==`/`>` 양쪽 ✓ (§91 "누적 == limit 완료 허용; > limit은 budget_exhausted")
- wall-clock `is_deadline_reached` = `now >= deadline`(budget.py:138–141). test_wall_clock_deadline_blocks(179–185) + budget.py test_deadline_reached_only_at_or_after(118–129) ✓
- tool-call / repeated-call N/N+1 + "다른 valid arguments는 반복 아님" over-strict guard(res:202–217) ✓

**over-strict guard "tool-only step이 iteration에 막히지 않음"**: `test_tool_only_step_not_blocked_by_iteration`(res:219–228)이 `needs_iteration=False` + iteration 소진 상태에서 tool step이 `None` 반환을 단언. §budget boundary matrix iteration should-NOT-fire "N번째 정상 완료 과잉 차단 않음"의 교차 검증. ✓

모든 차원이 동일 `BUDGET_EXHAUSTED`로 OR되므로 검사 순서는 결과에 무관(순서 관련 미세 버그 없음). ✓

### 4. F1 usage 방어 — missing/negative/non-int/bool 거부, 명시적 0 수용 (양방향, defense-in-depth 확인)

`_require_token_count`(budget.py:52–57) + `record_tokens`(151–154):

```python
def _require_token_count(value, name):
    if not _is_int(value) or value < 0:           # _is_int rejects bool (46–49)
        raise InvalidProviderUsage(...)
    return value
```

`InvalidProviderUsage.decision = LoopDecision.PROVIDER_ERROR`(budget.py:39). §91 "usage 또는 두 token count가 누락·invalid이면 0으로 보정하지 않고 provider_error"와 정합.

양방향 guard(test_agent_loop_budget.py ProviderUsageDefenseTest 183–240):

| 입력 | 기대 | 테스트 | 방향 |
|---|---|---|---|
| `decision` literal | PROVIDER_ERROR | test_invalid_usage_classifies_as_provider_error(192–193) | literal pin |
| 음수(-1) | reject | test_negative_count_is_rejected(195–200) | under-strict(missing→0 보정 버그 재발 시 실패) |
| None | reject | test_none_count_is_rejected(202–205) | under-strict |
| bool(True) | reject | test_bool_count_is_rejected(207–211) | under-strict |
| float(1.5)/str("1") | reject | test_non_integer_count_is_rejected(213–218) | under-strict |
| **명시적 0** | **수용** | test_explicit_zero_is_valid_and_accumulates(220–224) | **over-strict(0까지 거부하는 과잉 버구 재발 시 실패)** |
| reject 시 누적 불변 | 직전 합만 유지 | test_rejection_leaves_accumulated_total_unchanged(232–240) | 부분 누적 방지 |

"음수 거부"와 "명시적 0 수용"의 **양방향**이 핵심 — `value < 0` 경계에서 `0`은 유효·음수는 거부. 이 둘을 분리 단언하지 않으면 `value <= 0` 같은 over-correction이 0까지 묶어 거부해도 테스트가 잡지 못한다. ✓

**Pattern sweep — 작업자 "gateway 동일 정책, gap 없음" 주장 독립 실증(정정 포함)**:

- 최초 grep에서 `/mnt/d/devel/gemma4_12b/gateway/app/llama_client.py:183`의 `usage_data.get("prompt_tokens", 0)`(missing→0 보정)을 발견. **그러나 이는 별개 레포(gemma4_12b)의 참조 구현**이며 본 프로젝트 gateway가 아님.
- 본 프로젝트 gateway `services/llm_gateway/app/client.py:114–117` `_token_count`:
  ```python
  def _token_count(value):
      if isinstance(value, bool) or not isinstance(value, int) or value < 0:
          raise ValueError("token count must be a non-negative integer")
      return value
  ```
  루프 `_require_token_count`(bool/non-int/음수 거부, 0 수용)와 **문자 그대로 동일 정책**. gateway는 `_mapping(body["usage"])`(client.py:81, usage 부재 시 TypeError) + `usage["prompt_tokens"]`(82, 부재 시 KeyError)로 missing을 잡고 line 84에서 `INVALID_RESPONSE` → provider_invalid_response로 승격(gateway 테스트 `test_missing_usage_is_rejected_as_invalid_response` test_llama_provider_client.py:234, `test_zero_token_counts_are_accepted_as_valid`:258 존재).
- repo-wide 보정 sweep: `services/`(llm_gateway 외)에 `.get("..._tokens", 0)`식 silent 보정 **없음**.

→ 루프 F1은 진짜 defense-in-depth: gateway가 이미 missing/invalid usage를 provider_invalid_response로 차단하므로 정상 경로에선 루프가 None/missing을 볼 일이 없으나, 다른 provider adapter·bypass·gateway 계약 변경 시에도 루프 원시 함수가 독자적으로 막는다. **작업자의 "gap 없음" 주장은 정확**(작업자가 인용한 `client.py:114` file:line도 정확). ✓

### 5. 테스트 감사 — boundary matrix cell 역추적 (빈 칸 점검)

| Test | lock 하는 contract 분기 | 방향 |
|---|---|---|
| `test_self_report_has_finalize_and_defer` / `..._string_comparable`(completion:41–48) | SelfReport 2 literal | literal pin |
| `test_artifact_present_and_finalize_completes_for_every_profile`(52–62) | 구조∧finalize → completed(§198) | should-fire |
| `test_defer_is_awaiting_review_for_every_profile`(64–71) | defer → awaiting_review(§203) | should-fire |
| `test_finalize_without_artifact_is_not_completed`(73–79) | finalize 무산출물 ≠ completed(§249) | over-strict |
| `test_no_artifact_and_defer_is_awaiting_review`(81–86) | 무산출물 ≠ completed | under-strict |
| `test_non_retryable_*_terminates_immediately`(res:45–66) | non-retryable 즉시 error(§108) | should-fire |
| `test_retryable_*_with_cap_exhausted_is_*_error`(70–88) | cap 소진 → error(§109) | should-fire |
| `test_cap_exhausted_takes_precedence_over_budget_blocked`(90–100) | cap 소진 > budget 차단(§122) | **양방향 핵심** |
| `test_cap_remaining_and_budget_permits_retries_*`(104–124) | cap+budget 허용 → retry | should-fire |
| `test_*_retry_blocked_by_budget_is_budget_exhausted_with_literal`(127–148) | budget 차단 → budget_exhausted + literal(§110) | should-fire |
| `test_iteration/token/wall/tool/repeated_*_blocks`(156–217) | 각 차원 N+1 차단(§117–121) | should-fire + 경계 |
| `test_token_equal_to_limit_is_allowed`(164–168) | 누적 == limit 허용(§91) | over-strict |
| `test_repeated_call_..._same_signature_only`(202–217) | 다른 args ≠ 반복(§121) | over-strict |
| `test_tool_only_step_not_blocked_by_iteration`(219–228) | tool step ≠ iteration 차단 | over-strict |
| `test_exhausted_budget_takes_precedence_over_completion`(232–248) | budget > completion(§187 under-strict) | 문서형(아래 I2) |
| F1 8종(budget:192–240) | missing/neg/bool/non-int→reject, 0→수용(§91) | 양방향 |

A3 원시 함수가 담당하는 boundary cell은 should-fire/should-NOT-fire 양쪽 모두 테스트로 mapping됨. runner 합성 단계 cell(budget-before-completion 순서·retry 비-무료)은 I2에서 별도 처리. **A3 원시 함수 수준에 empty cell 없음.** ✓

### 6. 비회귀 및 pattern sweep (독자 재실행)

- `python3 -B -m unittest discover -s tests` → **Ran 117 tests … OK**(검증자 재실행, 0.146s)
- per-module 독립 카운트: `test_agent_loop_completion` **6**, `test_agent_loop_resolution` **18**, `test_agent_loop_budget` **25**(F1 +8 = 직전 17 + 8). 작업자 주장 "85→117, completion 6 / resolution 18 / budget F1 +8"과 정합(6+18+25=49 focused; 117 전체). ✓
- F1 정책 일관성 sweep: gateway `client.py:114` ↔ loop `budget.py:52` 동일 정책 실증(위 §4). silent 보정 위치 repo에 없음.

## Issues / Risks

### I1. [비차단, 작업자 환기됨] retry cap 정책 근원이 어떤 policy 객체에도 실현되지 않음

`flat-loop-gate.md` §retry(106)은 "provider/tool retry cap은 **task profile의 필수 policy 값**이며 0 이상이다"라고 명시. 그러나:
- `BudgetPolicy`(budget.py:60–107, A1)은 `max_iterations/max_wall_clock_ms/max_total_tokens/max_tool_calls/max_repeated_calls/allows_tools`만 갖고 **retry cap이 없다**.
- `services/` 전체에 `retry_cap`/`RetryPolicy`/`provider_retry_cap`/`tool_retry_cap`/`max_retries` 정의가 **존재하지 않는다**(grep 실증). `retries_remaining`은 `resolve_retry`의 caller-supplied 파라미터로만 등장.

결과적으로 `resolve_retry`의 분기 2(`retries_remaining <= 0` = cap 소진)는 **현재 어떤 caller도 spec-준수 방식으로 채울 수 없다**(cap의 근원 policy가 어디에도 없으므로). A3 원시 함수 자체는 올바르고 테스트도 통과하지만, "retry cap은 필수 policy 값"이라는 계약이 아직 어떤 구성 객체에도 실현되지 않은 **spec↔impl 갭**이다.

- **작업자는 이를 silent하게 넘기지 않았다**: follow-up #1 "retry cap policy 배치 — BudgetPolicy에 추가할지 별도 slice에서 결정"으로 명시 환기. A3는 `resolve_retry(retries_remaining)` caller-supplied 설계로 동작.
- 본 검증 방법론은 silent gap을 차단하지만, **환기된(human-decision-pending) deferral은 empty cell이 아니다**. A3 범위(completion/retry 우선순위/budget 매핑/F1) 자체는 닫혀 있으므로 본 slice의 verdict에는 영향을 주지 않는다.
- 단, 본 갭은 **triggered 조건 없이 무기한 방치되면 안 된다**: runner(Phase 4)가 `resolve_retry`를 실제 호출하는 시점에는 반드시 retry cap의 policy 근원이 정해져야 한다(그 전에 runner는 `retries_remaining`을 합법적으로 계산할 수 없음). Outstanding items 참조.

### I2. [비차단, 범위 밖] runner 합성 단계 경계(budget-before-completion 순서·retry 비-무료성)는 A3 원시 함수에 없음

- §187 budget_exhausted should-NOT-fire "성공 위장 금지(under-strict)"와 §122 retry should-NOT-fire "retry를 budget 밖 무료 호출로 처리하지 않음"은 **runner가 `next_step_budget_decision`을 `judge_completion`보다 먼저, 그리고 retry 결정 전에 budget을 검사·소비할 때** 비로소 실현된다.
- A3는 순수 원시 함수이므로 이 순서를 강제하는 코드가 없다. `test_exhausted_budget_takes_precedence_over_completion`(res:232–248)은 두 원시 함수의 출력을 **별도로** 단언할 뿐, 합성 순서를 코드로 lock하지 않는다(주석으로만 "budget check fires first" 서술).
- 이는 spec이 A3를 "loop를 구동하지 않는 순수 결정 원시"(각 docstring)로 규정한 것과 정합하므로 **A3 결함이 아니다**. 단 runner slice에서 `next_step_budget_decision → resolve_retry/judge_completion` 호출 순서와 retry 시 `record_*` 소비를 양방향 회귀로 lock하는 것이 **forward-looking 의무사항**으로 남는다.

### I3. [비차단, cosmetic/일관성] exception→decision uniform 매핑이 절반만 실현

- `InvalidProviderUsage`는 클래스 속성 `decision = LoopDecision.PROVIDER_ERROR`(budget.py:39)를 갖는다. docstring(35–36)은 "이 `decision` 속성이 future runner가 budget/registry 예외를 **uniformly** terminal decision으로 매핑하게 한다"고 서술.
- 그러나 같은 파일의 `InvalidBudgetPolicy`(26–27, A1)는 `.decision` 속성이 **없다**(→blocked 매핑). 따라서 "uniformly" 주장이 절반만 실현됐다. runner는 `InvalidBudgetPolicy`를 타입별로 별도 처리해야 한다.
- 영향 없음: runner가 아직 존재하지 않아(grep에서 catch 지점 0건) 활성 결함 아님. 일관성을 원하면 `InvalidBudgetPolicy`에도 `decision = LoopDecision.BLOCKED`를 추가하거나 docstring의 "uniformly"를 좁히는 것으로 충분.

## Verdict

**합격(pass).**

적용 사유(load-bearing):

1. **계약 literal 그대로 정확**: 4개 A3 표면(completion/retry/budget 매핑/F1)이 모두 `flat-loop-gate.md` 해당 섹션의 literal을 paraphrase 없이 구현. 출력 집합 {COMPLETED, AWAITING_REVIEW}, `BUDGET_EXHAUSTED` + preserved literal `"provider_error"`/`"tool_error"`, token `==` 허용/`>` 차단, F1 missing→0 보정 금지·명시적 0 수용 — 전부 계약과 일치.
2. **boundary matrix 빈 칸 없음(원시 함수 수준)**: completion 2×2 진리표 4 cell, resolve_retry 4분기(특히 cap-소진 > budget-차단 양방향 핵심 guard), next_step 5차원 경계값 양방향, F1 음수-거부/0-수용 양방향이 전부 named regression으로 lock.
3. **양방향 변이 증명 실재**: 작업자가 주장한 4개 핵심 분기 양방향(completion AND/OR 진리표, retry cap 소진 우선, token `==`/`>` 매핑, F1 음수/0)을 검증자가 테스트 코드에서 직접 확인 — under-strict와 over-strict 양쪽 재발을 잡는 구조.
4. **독립 재현**: 117/117, per-module 6/18/25를 검증자가 재실행(-B). F1 pattern sweep을 독자 재실증해 작업자 "gateway 동일 정책, gap 없음" 주장이 정확함을 확인(잘못된 코드베이스 함정 정정 포함).
5. **silent gap 없음**: 발견된 유일한 spec↔impl 갭(I1, retry cap 근원)은 작업자가 follow-up으로 명시 환기했고, 나머지 deferral(runner 합성·SelfReport wire·per-profile 구조 평가)은 전부 spec-sanctioned. contract 자기 모순(A3 범위 내)·spec-silent-but-code-enforced 분기 없음.

I1(retry cap 근원, 작업자 환기)·I2(runner 합성 순서, 범위 밖)·I3(exception uniformity 절반, cosmetic)은 모두 비차단이며 Outstanding items에서 추적한다.

## Outstanding items

- **I1 — retry cap policy 근원 결정(사용자 결정 대기, 작업자 follow-up #1)**: `BudgetPolicy`에 `provider_retry_cap`/`tool_retry_cap`을 추가할지, 별도 `RetryPolicy`를 둘지, 아니면 task profile에 둘지 결정 필요. **triggered 조건**: runner(Phase 4)가 `resolve_retry`를 실제 호출하는 시점엔 반드시 결정돼야 함(그 전에 `retries_remaining`을 합법적으로 계산 불가). 숫자 기본값은 Gemma Q4 benchmark 후.
- **I2 — runner 합성 회귀(forward-looking)**: Phase 4 runner slice에서 (a) `next_step_budget_decision`을 completion/retry 결정보다 먼저 호출해 budget_exhausted가 completed로 위장되지 않음, (b) retry 시 동일 차원 budget 소비로 "retry 비-무료성" 보장 — 이 두 경계를 양방향 회귀로 lock.
- **SelfReport wire 형식(작업자 follow-up #2, spec §211)**: 종료 채널 신호의 구체 wire(명시 토큰/구조화 필드)는 provider-response parser slice에서 확정. 현재 `SelfReport` enum 주입으로 infrastructure-free.
- **A3 코드·본 검증 기록 모두 uncommitted**: HEAD `c5202e8` 이후 working tree. 커밋은 사용자 요청 시.
- **사용자 대기 Task 1(SoT Draft 검토)·Task 3(Gemma Q4 benchmark 후 숫자 기본값)**: 본 검증과 별개로 세션 시작부터 대기 중.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# 1. 전체 + per-module 비회귀(검증자 재실행값: 117 / 6 / 18 / 25). WSL2 stale pyc 회피용 -B.
python3 -B -m unittest discover -s tests
python3 -B -m unittest tests.test_agent_loop_completion tests.test_agent_loop_resolution tests.test_agent_loop_budget -v

# 2. F1 양방향(음수 거부 vs 명시적 0 수용) + cap-소진 우선순위 실증
python3 -B - <<'PY'
from services.application.app.agent_loop.budget import BudgetTracker, BudgetPolicy, InvalidProviderUsage
from services.application.app.agent_loop.resolution import resolve_retry, ErrorKind
from services.application.app.agent_loop.decision import LoopDecision
p = BudgetPolicy(max_iterations=2,max_wall_clock_ms=1000,max_total_tokens=10,
                 max_tool_calls=2,max_repeated_calls=2,allows_tools=True)
t = BudgetTracker(p)
# under-strict: negative rejected (not coerced to 0)
try: t.record_tokens(-1,0); print("BUG: negative accepted")
except InvalidProviderUsage: print("ok: negative rejected")
# over-strict: explicit 0 accepted (would fail if <=0 over-correction)
t.record_tokens(0,0); print("ok: explicit 0 accepted")
# cap-exhausted precedence over budget-blocked
o = resolve_retry(error_kind=ErrorKind.PROVIDER, retryable=True,
                  retries_remaining=0, budget_permits_next=False)
assert o.decision==LoopDecision.PROVIDER_ERROR and o.preserved_literal is None
print("ok: cap exhausted -> provider_error, no literal (precedence holds)")
# budget-blocked preserves literal
o = resolve_retry(error_kind=ErrorKind.TOOL, retryable=True,
                  retries_remaining=1, budget_permits_next=False)
assert o.decision==LoopDecision.BUDGET_EXHAUSTED and o.preserved_literal=="tool_error"
print("ok: budget blocked -> budget_exhausted + 'tool_error' literal")
PY

# 3. F1 pattern sweep — gateway 동일 정책 실증(client.py:114 _token_count)
python3 -B - <<'PY'
from services.llm_gateway.app.client import _token_count
for v,exp in [(0,"accept"),(5,"accept"),(-1,"raise"),(True,"raise"),(1.5,"raise"),("1","raise")]:
    try: _token_count(v); got="accept"
    except ValueError: got="raise"
    print(v, "->", got, "OK" if got==exp else "MISMATCH")
PY

# 4. retry cap 근원 부재 실증(I1)
grep -rnE "retry_cap|RetryPolicy|provider_retry_cap|tool_retry_cap|max_retries" services/ --include="*.py" || echo "(no retry cap policy source — I1 confirmed)"
```
