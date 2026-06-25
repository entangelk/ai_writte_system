# Work Log — 2026-06-25

## Goals

- HANDOFF 기준 다음 작업인 AgentLoopRunner A2를 진행한다.
- tool registry, strict argument validation, signature normalization을 실제 인프라 없이 결정적 회귀로 잠근다.
- A2 완료 후 다음 작업자가 A3(completion/retry/loop 합성)를 바로 이어갈 수 있게 상태 문서를 갱신한다.
- 흩어진 계획 문서의 서비스 경계와 확정 계약을 정리하는 SoT 초안을 만든다.
- AgentLoopRunner A3(completion 판정·retry 우선순위·loop decision 합성·budget→budget_exhausted 매핑·F1 usage 방어)를 인프라 없는 순수 원시로 잠근다.
- AgentLoopRunner self-report 종료채널 wire 형식을 확정하고 provider-response parser slice를 회귀로 잠근다.
- AgentLoopRunner provider composition slice를 구현해 parser 연결과 I2 forward-lock을 회귀로 잠근다.

## Completed work

### AgentLoopRunner A2 구현(tool registry + strict arguments + signature)

- 변경 파일: `services/application/app/agent_loop/registry.py`, `tests/test_agent_loop_registry.py`, `docs/plans/implementation-plan.md`, `CHANGELOG.md`, `HANDOFF.md`, 이 작업 로그.
- `flat-loop-gate.md`의 tool registry 계약을 Application 소유 `agent_loop` 패키지에 추가했다.
- `TaskProfile` 3종(`analysis_compare`, `context_search`, `writing_generate`)과 v1 domain tool 6종을 literal로 고정했다.
- profile별 allowlist를 계약 그대로 고정했다: `analysis_compare` 5종, `context_search` 3종, `writing_generate` 0종.
- run 시작 시 등록 tool이 profile allowlist 밖에 있거나 profile 필수 tool이 빠지면 `ToolBlocked(decision=blocked)`로 차단한다.
- `ToolEntry` 등록 조건에서 schema-less tool, unknown field 허용 schema, 모델 argument의 context 전용 필드(`project_id`, task/trace/deadline 계열)를 거부한다.
- `validate_call`은 raw arguments를 JSON으로 한 번 parse하고 object가 아니면 거부한다. malformed JSON, unknown field, required 누락, type coercion 시도는 `InvalidToolArguments(decision=invalid_tool_arguments)`로 분류한다.
- valid call만 `tool name + canonical JSON arguments` signature를 만든다. canonical JSON은 key sort와 compact separator를 사용하며, 다른 argument 값/type/tool은 같은 signature로 접히지 않는다.
- 실제 Mongo/검색 handler 실행, runtime `tool_error`, budget→decision 매핑, retry, completion 판정은 A3 및 Slice 1·3 이후 범위로 남겼다.

### 시스템 정본 계약 SoT 초안 작성

- 변경 파일: `docs/system-contract-sot.md`, `docs/README.md`, `docs/plans/README.md`, `CHANGELOG.md`, `HANDOFF.md`, 이 작업 로그.
- 기존 계획 문서가 Phase별로 흩어져 있어 구현자가 어떤 계약을 먼저 봐야 하는지 모호했다. 새 문서를 "정본 계약 인덱스"로 추가해 문서 우선순위, 서비스 책임, 확정된 전역 계약, Gateway/AgentLoopRunner 계약, Gate 합성, Phase별 계약 인덱스, 미확정 결정 목록을 한 곳에 모았다.
- `docs/contracts.md`는 여전히 아이디에이션/reference로 두고, 새 구현 진입점은 `docs/system-contract-sot.md`로 분리했다.
- `docs/README.md`와 `docs/plans/README.md`에 SoT 문서를 먼저 보도록 링크와 우선순위 문구를 추가했다.
- 초안 상태이므로 세부 Phase schema를 추측하지 않았다. 확정된 구현·검증 계약과 미확정 항목을 분리했고, `enum`/bounds validator deferral 같은 triggered 조건도 유지했다.

### AgentLoopRunner A3 구현(completion 판정 + retry/budget decision 합성 + F1 usage 방어)

- 변경 파일: `services/application/app/agent_loop/completion.py`(신규), `services/application/app/agent_loop/resolution.py`(신규), `services/application/app/agent_loop/budget.py`(F1 방어), `tests/test_agent_loop_completion.py`·`tests/test_agent_loop_resolution.py`(신규), `tests/test_agent_loop_budget.py`(F1 회귀), `docs/plans/implementation-plan.md`, `docs/system-contract-sot.md`, `CHANGELOG.md`, `HANDOFF.md`, 이 작업 로그.
- 사용자 결정(아래 Decisions)으로 A3를 A1·A2와 동일한 인프라 없는 순수 decision 합성 원시로 진행했다. 러너 실구동(fake provider/tool 주입 루프)은 Slice 1·3 이후.
- `SelfReport`(`FINALIZE`/`DEFER`) 종료채널 신호 추상과 `judge_completion(artifact_present, self_report)`을 추가했다. 구조 조건(artifact 존재)과 self-report(`FINALIZE`)을 모두 충족할 때만 `completed`, 그 외 `awaiting_review`. 산출물 데이터 채널의 불확실성(needs_review·confidence·conflict)은 `artifact_present`를 유지하므로 종료채널 `FINALIZE`면 `completed`(승격 금지). 구체 wire 형식은 provider-response parser slice로 deferred.
- `resolve_retry(error_kind, retryable, retries_remaining, budget_permits_next)`로 retry 우선순위를 잠갔다: non-retryable 즉시 종료 → retryable cap 소건 시 해당 error decision → cap 남음+budget 허용 retry(비종단) → cap 남음+budget 차단 `budget_exhausted`(원래 error literal은 `preserved_literal`로 trace 보존). cap 소건이 budget 차단보다 우선.
- `next_step_budget_decision(tracker, needs_iteration, tool_signature)`로 budget 5차원(iteration·wall-clock·token·tool-call·repeated-call) → `budget_exhausted` 매핑을 잠갔다. wall-clock deadline과 token 초과는 전역 정지 신호, iteration/tool 차원은 다음 단위 작업 종류에 따라 검사. budget-blocked가 completion보다 선행(성공 위장 금지).
- `BudgetTracker.record_tokens`에 F1 방어를 추가했다: prompt/completion count가 음수/None/bool/비-int면 0으로 보정하지 않고 `InvalidProviderUsage`(decision=`provider_error`)로 거부. 명시적 0은 유효. 거부 시 누적 총합은 불변.
- terminal-decision 우선순위(error > blocked/invalid_tool_arguments > budget_exhausted > completion)는 순차 합성으로, 각 decision point에서 정확히 하나가 발화한다. 별도 compose 함수 없이 각 원시가 자기 decision point를 담당.
- agent_loop focused 73개(decision 4 + budget 25 + registry 20 + completion 6 + resolution 18), 전체 117개 회귀 통과. 4곳 핵심 분기를 변이해 양방향 lock을 증명했다.

### A3 독립 검증 후 보강(I1 / I3 폐쇄)

- 변경 파일: `services/application/app/agent_loop/budget.py`, `tests/test_agent_loop_budget.py`, `docs/plans/implementation-plan.md`, `docs/system-contract-sot.md`, `CHANGELOG.md`, `HANDOFF.md`, 이 작업 로그.
- 독립 검증(`docs/verifications/2026-06-25/agent_loop_a3_completion_resolution.md`) 판정 **합격**. 비차단 3건 중 I1(유일한 spec↔impl 갭)·I3(cosmetic)을 보강했고, I2(runner 합성 순서)는 spec이 A3를 순수 원시로 규정하므로 runner slice의 forward-lock 의무로 추적만 유지.
- **I3 보강**: `InvalidBudgetPolicy`에 `decision = LoopDecision.BLOCKED` 추가(계약 §Budget "모순 policy는 provider 호출 전 blocked"). `InvalidProviderUsage`(`provider_error`)와 짝이 돼 "future runner가 budget/registry 예외를 uniformly 매핑"이라는 docstring 주장이 실현됐다. 회귀 `test_invalid_budget_policy_classifies_as_blocked`.
- **I1 폐쇄(사용자 결정 Option A)**: `BudgetPolicy`에 `provider_retry_cap`/`tool_retry_cap`을 추가했다. 계약 §retry "retry cap은 task profile의 필수 policy 값, 0 이상"이 이제 구현에 실현됐다(`_RETRY_DIMENSIONS` 루프로 >= 0·bool 거부 검증). `resolve_retry(retries_remaining)` 시그니처는 그대로이고, runner가 `policy.<cap> - used`로 `retries_remaining`을 합법 계산할 수 있게 됐다. 회귀 3종(0 허용, 음수·bool 거부). 변이 증명(`_RETRY_DIMENSIONS=()` → FAIL(2) / 복원 PASS).
- 회귀: 전체 117 → **121**(I3 +1, I1 +3). 검증 기록은 보강 전 working-tree 상태(HEAD `c5202e8`)를 가리키므로, 해당 기록 Reproduction의 `BudgetPolicy(...)` 호출은 retry cap 필드가 없는 보강 전 시그니처이다(점-in-time 기록이라 그대로 둠).

### AgentLoopRunner self-report parser slice

- 변경 파일: `services/application/app/agent_loop/parser.py`, `tests/test_agent_loop_parser.py`, `services/application/app/agent_loop/completion.py`, `docs/plans/flat-loop-gate.md`, `docs/plans/implementation-plan.md`, `docs/system-contract-sot.md`, `HANDOFF.md`, 이 작업 로그.
- A3에서 deferred로 남겨둔 종료채널 wire 형식을 확정했다. provider 응답 `content`는 JSON object이고, loop 종료 채널은 top-level `self_report` field다.
- 허용값은 정확히 `finalize` 또는 `defer`뿐이다. `parse_self_report_payload`는 이를 `SelfReport.FINALIZE`/`SelfReport.DEFER`로 변환한다.
- 누락, malformed JSON, non-object JSON, non-string 값, 대소문자 변형, artifact 내부 nested `self_report`는 모두 `InvalidSelfReport(decision=provider_error)`로 거부한다. silent default나 산출물 데이터 채널 fallback은 없다.
- 산출물 payload schema 자체는 아직 Phase schema가 확정되지 않았으므로 검증하지 않았다. 이 slice는 종료채널 추출만 소유한다.
- `flat-loop-gate.md`, `implementation-plan.md`, `system-contract-sot.md`의 deferred 문구를 확정된 `self_report` wire 계약으로 갱신했다.
- 회귀: focused parser+completion 14개 통과, 전체 discovery 129개 통과.

### self-report parser 독립 검증 R1 보강

- 변경 파일: `tests/test_agent_loop_parser.py`, `HANDOFF.md`, 이 작업 로그.
- 독립 검증(`docs/verifications/2026-06-25/self_report_parser.md`)은 parser slice를 **합격**으로 판정했고, 비차단 R1로 계약의 "오타" 거부 카테고리에 전용 value sample이 없다는 권고를 남겼다. branch는 이미 `case variant` test가 동일 `ValueError` 분기를 잠그고 있어 비차단이었다.
- 권고를 수용해 잘 형성된 잘못된 리터럴 `{"self_report":"done"}`을 거부하는 `test_wrong_literal_typo_is_invalid`를 추가했다.
- 회귀: focused parser+completion 15개 통과, 전체 discovery 130개 통과.

### AgentLoopRunner provider composition slice

- 변경 파일: `services/application/app/agent_loop/runner.py`, `tests/test_agent_loop_runner.py`, `docs/plans/implementation-plan.md`, `docs/system-contract-sot.md`, `CHANGELOG.md`, `HANDOFF.md`, 이 작업 로그.
- `AgentLoopRunner` 최소 provider composition을 추가했다. 실제 domain tool handler는 아직 없으므로 provider call/usage/self-report/completion 순서만 실행 가능한 코드로 연결했다.
- 실행 순서: provider 호출 전 `next_step_budget_decision(needs_iteration=True)` → `record_iteration()` → provider call → provider retry resolution → `record_tokens()` → `next_step_budget_decision(needs_iteration=False)` → `parse_self_report_payload()` → `judge_completion()`.
- I2 forward-lock을 회귀로 잠갔다. token overrun은 self-report를 파싱하거나 completion을 판단하기 전에 `budget_exhausted`로 종료한다. `== token limit`은 over-strict guard로 `completed` 가능하다.
- provider retry는 free path가 아니다. retryable provider error에서 retry cap이 남아도 다음 provider attempt가 iteration budget에 막히면 `budget_exhausted`가 되고 원래 `provider_error` literal은 `preserved_error_literal`로 보존된다. iteration budget이 남으면 retry 후 정상 completion 가능하다.
- trace는 provider call/error/retry, budget stop, self_report, completion event를 `RunnerTraceEvent`로 보존한다.
- 회귀: focused runner/parser/completion/resolution 40개 통과, 전체 discovery 137개 통과.

## Issues found

### A2 시작 시 registry 모듈 부재

- 문제: 새 A2 테스트가 `services.application.app.agent_loop.registry`를 import할 수 없었다.
- 원인: A1은 decision/budget만 구현했고 registry는 후속 sub-slice로 명시되어 있었다.
- 해결: `registry.py`를 추가하고 focused 18개 회귀를 통과시켰다.
- 결과: 전체 `python3 -m unittest discover -s tests`가 83개 통과했다.

### 유사 패턴 sweep

- 문제: invalid args `{}` 보정, signature 오접힘, context scope 모델 주입과 같은 근본 패턴이 다른 구현에 남아 있을 수 있었다.
- 확인: `json.loads`, `additionalProperties`, `project_id`, `invalid_tool_arguments`, `signature` 패턴을 `services`, `tests`, `flat-loop-gate.md`에서 검색했다.
- 결과: 위험한 중복 구현은 발견되지 않았다. 관련 코드는 새 A2 모듈/테스트와 기존 A1의 normalized signature 소비 지점뿐이었다.

### A2 독립 검증 후 비차단 권고 보강

- 문제: 독립 검증 I2가 중첩 object schema의 등록-검증 비대칭을 지적했다. 기존 구현은 runtime에서는 fail-closed였지만 등록 시점에는 중첩 object strictness를 잡지 못했다.
- 추가 확인: reconcile 후 A2 범위로 남긴 `array items`도 `items` 누락 시 등록을 통과할 수 있었다.
- 해결: `_validate_schema_contract`를 재귀화해 중첩 object의 `additionalProperties: false`, context-only field, required/properties 일치, array `items` schema를 등록 시점에 검증한다.
- 해결: 독립 검증 I3의 `assert` 의존을 제거하고 `_validate_arguments`에서 schema 구조를 명시 검사로 바꿨다.
- 회귀: `test_nested_object_schema_must_be_strict_at_registration`, `test_array_schema_requires_items_at_registration` 2개를 추가했다. focused registry 회귀는 18→20, 전체 회귀는 83→85가 됐다.
- 결과: `python3 -m unittest tests.test_agent_loop_registry -v` 20/20 통과, `python3 -m unittest discover -s tests` 85/85 통과.
- 확인: enum/bounds는 여전히 validator 범위에서 제외되어 수용된다. 이는 사용자 결정으로 갱신한 `flat-loop-gate.md` §33의 explicit deferral과 일치한다.

### SoT 독립 검증 R1 보강(precedence tree 통일)

- 문제: 독립 검증(`docs/verifications/2026-06-25/system_contract_sot.md`)이 SoT(`system-contract-sot.md` §문서 우선순위)와 `plans/README.md`(충돌 시 우선순위)의 문서-precedence tree가 항목 불일치함을 발견했다. SoT는 "Approved SoT+Phase 계획(2) / Draft-locked(3) / 미구현 Draft(4)", plans/README는 "SoT 확정 계약(2) / Approved Phase 계획(3) / Draft-locked(4)"로, Draft SoT 확정 계약 vs Approved Phase 문서 충돌 시 결론이 양쪽에서 달라질 수 있었다.
- 확인: repo sweep에서 문서-precedence tree는 SoT·plans/README 두 곳만(`docs/README.md`는 SoT로 defer). 제3의 분기 없음.
- 해결(사용자 요청 "비차단 부분 네가 보강해줘. 권고부분도 보강해주고"): `plans/README.md` tree를 SoT 5-level과 동일하게 통일하고 "상세와 최종 판정은 SoT에 있다"로 SoT를 정본 precedence로 defer. SoT tree가 의미론상 더 타당(Approved=사용자 서명 계획이 미서명 Draft-locked 구현보다 우선이어야 사용자 지시 변경이 기존 구현을 덮어씀)하고 SoT가 §7에서 자기 precedence를 권위로 선언했으므로 plans/README를 SoT에 맞췄다.
- 결과: 정본 precedence tree는 SoT 한 곳만 유지(DRY). 독립 검증 R1 폐쇄.

### A3 변이 검증 중 stale `__pycache__` 충돌

- 문제: 양방향 변이 spot-check에서 소스를 `cp`로 복원했는데도 복원 후 테스트가 계속 FAIL(28 errors)했다. 에러는 `BudgetPolicy` 생성 시 `max_tool_calls must be an integer >= 0`였다.
- 원인: 변이로 생성된 mutated `.pyc`가 WSL2 `/mnt/d`(Windows DrvFs) 마운트의 mtime 캐싱 때문에 소스 복원 후에도 재컴파일되지 않고 재사용됐다. `grep`으로 본 소스는 정상(`value < 0`)이지만 런타임은 mutated bytecode를 썼다.
- 해결: `find services tests -name __pycache__ -type d -prune -exec rm -rf {} +`로 캐시 정리 후 정상(117 통과). 이후 변이 검증은 `python3 -B`(pyc 미생성)로 실행해 stale 캐시를 원천 차단했다.
- 결과: 4곳 변이가 양방향으로 정확히 검증됐고, repo는 gitignored `__pycache__`만 영향이라 깨끗함.

### A3 변이 시 sed 다중 매칭

- 문제: F1 라인 변이에 `sed 's/value < 0/value > 0/'`를 썼더니 `_require_token_count`(line 55)뿐 아니라 A1 `BudgetPolicy`의 TOOL_DIMENSIONS 검사(line 88)까지 같이 바뀌어 `BudgetPolicy` 생성이 깨졌다.
- 해결: `raise InvalidProviderUsage`에 anchor한 Python 1회 치환으로 F1 라인만 정확히 타겟팅해 변이 증명을 다시 했다(line 88 미영향 확인).
- 교훈: 동일한 패턴이 인접한 다른 의미의 라인에도 있을 수 있으니 변이는 문맥 anchor를 쓸 것.

### 유사 패턴 sweep(provider 숫자 값 검증)

- 확인: "provider가 준 token count를 검증 없이 수용" 패턴을 `services`에서 검색. `services/llm_gateway/app/client.py:114`의 `_token_count`가 이미 bool·비-int·음수(`value < 0`)를 거부한다.
- 결과: loop 측 `_require_token_count`(budget.py)와 동일 정책. loop F1 방어는 gateway 1차 게이트 뒤의 defense-in-depth로 일관적이며, gap/중복 위험 없음. `record_tokens`는 loop가 gateway 응답을 소비하는 지점이므로 F1 방어 위치가 맞다.

### self-report parser 패턴 sweep

- 확인: `self_report`, `SelfReport`, `finalize`, `defer` 패턴을 `services`, `tests`, `docs/plans`, `docs/system-contract-sot.md`에서 검색했다.
- 결과: 기존 코드에 종료채널을 default하거나 nested artifact field로 오인하는 중복 parser는 없었다. 관련 구현은 새 `parser.py`, 기존 `completion.py`, A3 resolution 테스트의 판정 예시뿐이었다.

### self-report parser 독립 검증 R1

- 문제: 검증 기록이 "오타" 카테고리의 전용 wrong-literal sample 부재를 비차단 권고로 기록했다.
- 원인: `"Finalize"` case-variant가 동일 `SelfReport(raw)` → `ValueError` 분기를 이미 잠갔으나, 계약 열거값 수준에서 `"done"` 같은 잘못된 정상 문자열 샘플은 없었다.
- 해결: `test_wrong_literal_typo_is_invalid` 추가.
- 결과: branch-level lock에 더해 value-level sample도 채워졌다.

### AgentLoopRunner provider composition 패턴 sweep

- 확인: `AgentLoopRunner`, `parse_self_report_payload`, `next_step_budget_decision`, `record_tokens`, `judge_completion` 사용 위치를 `services`, `tests`, `docs`에서 검색했다.
- 결과: 실제 composition 구현은 새 `runner.py` 한 곳뿐이다. 기존 A3 원시와 테스트 외에 completion-before-budget 또는 retry-free 우회 경로는 발견되지 않았다.

### 전체 테스트 명령 선택

- 문제: `python3 -m unittest`가 이 저장소에서는 테스트를 자동 발견하지 못하고 0개를 실행했다.
- 해결: repository test surface는 `python3 -m unittest discover -s tests -p 'test_*.py'`로 실행했다.
- 결과: 당시 129개 테스트 통과. provider composition slice 이후 현재 전체 회귀는 137개이며, 앞으로 전체 회귀 기록은 discovery 명령을 사용한다.

## Decisions

- 상세 domain tool payload 필드는 아직 Phase schema가 확정되지 않았으므로 추측하지 않았다. A2는 schema 구조와 strict 검증 메커니즘을 잠그고, 실제 handler payload schema는 해당 Phase 구현에서 구체화한다.
- 외부 `jsonschema` dependency를 추가하지 않았다. 현재 테스트 표면에 필요한 strict object/type/required/array 검증만 표준 `json` 기반 최소 구현으로 제공한다. 더 넓은 JSON Schema keyword가 필요해지면 그때 dependency 도입을 판단한다.
- **[독립 검증 후 사용자 결정, 2026-06-25]** 독립 검증(`docs/verifications/2026-06-25/agent_loop_a2_registry.md`)이 `flat-loop-gate.md` §33 "enum, bounds 적용" 명시와 구현의 enum/bounds 미검증 불일치를 실증 발견했다. 사용자 결정으로 v1/A2 validator 범위를 `{required, type, additionalProperties, array items}`로 계약에 **명시 좁힘**하고 `enum`/bounds는 keyword를 사용하는 tool schema가 등록되는 시점까지 deferred로 reconcile했다(§33·implementation-plan §138·CHANGELOG에 반영). 이유: 현재 v1 tool schema에 enum/bounds가 없어 활성 결함이 아니며, 의존성·구현 추가보다 계약 개정이 가볍다. tradeoff: enum/bounds를 쓰는 tool이 처음 등록되는 시점에 검증 + 양방향 회귀를 반드시 추가해야 한다(해당 시점까지 empty cell 아님, 명시적 deferral).
- 독립 검증의 비차단 I2/I3는 바로 보강했다. 중첩 object와 array `items`는 현재 A2 validator 범위에 속하므로 등록 시점 fail-fast가 단순하고, `assert` 제거는 동작 변화 없이 최적화 모드에서도 의도가 드러나는 쪽을 택했다.
- **[사용자 결정, 2026-06-25]** A3 범위를 fake provider/tool 주입 러너 골격이 아니라 A1·A2 동일 패턴의 인프라 없는 순수 decision 합성 원시로 좁혔다. 이유: 계약이 실제 tool handler·Mongo/ES 통합을 Slice 1·3 이후로 미뤘고, A1·A2 cadence를 유지하면 decision 합성 계약을 인프라 없이 빠르게 잠글 수 있었다. 당시 tradeoff로 러너 실구동(종료채널 wire parsing·provider/tool 호출 순서·trace 조립)은 후속 slice로 남겼고, 이후 provider composition runner slice에서 provider 응답 흐름과 I2 forward-lock만 별도 구현했다.
- self-report의 구체 wire 형식(명시 토큰·구조화 필드)은 provider-response parser slice에서 확정한다(flat-loop-gate §completion criteria가 "Phase 4 구현 slice에서 확정"으로 명시). A3는 `SelfReport` enum을 주입받아 판정만 잠갔다.
- **open contract point(→ 해소)**: flat-loop-gate §retry가 "provider/tool retry cap은 task profile의 필수 policy 값이며 0 이상"으로 명시하나 A1 `BudgetPolicy`는 5차원+allows_tools만 lock해 cap이 없었다. A3는 `resolve_retry(retries_remaining)`로 policy 저장 위치에 무관하게 동작시켰다. 독립 검증 I1이 이를 "유일한 spec↔impl 갭"으로 지적했고, **사용자 결정(Option A)**으로 `BudgetPolicy`에 `provider_retry_cap`/`tool_retry_cap`(0 이상)을 추가해 보강에서 폐쇄했다. 별도 `RetryPolicy`/`TaskProfile` 배치 대신 단일 run-policy 객체를 택했다(이유: `allows_tools`도 budget이 아닌데 이미 BudgetPolicy에 있어 "run policy" 역할과 일관, runner가 policy 1개만 전달). numeric 기본값은 benchmark 이후.
- terminal-decision 우선순위(error > blocked/invalid_tool_arguments > budget_exhausted > completion)를 별도 compose 함수가 아니라 각 원시의 decision point 순차 합성으로 표현했다. 루프에서는 한 시점에 정확히 하나만 발화하므로 "동시 후보 중 선택" 함수는 불필요하다 판단했다(Simplicity First).
- self-report 종료채널은 JSON object의 top-level `self_report` field로 확정했다. 이유: Phase payload들이 이후 JSON schema로 구체화될 가능성이 높고, top-level field가 산출물 데이터 채널과 가장 단순하게 분리된다. tradeoff: 자유 텍스트 응답이나 nested artifact field는 종료채널로 인정하지 않으므로 prompt/runner가 이 wrapper를 강제해야 한다.
- provider composition runner는 domain tool branch를 아직 구현하지 않았다. 이유: 실제 tool handler와 Phase payload schema가 아직 없고, 지금 검증 가능한 계약은 provider 응답 흐름과 I2 forward-lock이다. tradeoff: `analysis_compare`/`context_search`의 tool 실행 루프는 후속 Phase handler가 들어올 때 별도 slice로 잠가야 한다.

## Next steps

1. `docs/system-contract-sot.md`를 사용자가 검토하고 `Draft` 유지/수정/Approved 승격 방향을 결정한다.
2. runner의 domain tool-call branch와 실제 tool handler 연결은 Slice 1·3 이후 Phase payload/handler가 들어올 때 구현한다.
3. task별 artifact schema 평가(`artifact_present`)는 Phase payload schema 확정 시 profile별로 교체한다.
4. Gemma Q4 benchmark 후 budget/retry production 숫자 기본 한도를 확정한다. (retry cap 구조는 보강에서 `BudgetPolicy`에 폐쇄됐고 숫자 기본값만 남음.)
