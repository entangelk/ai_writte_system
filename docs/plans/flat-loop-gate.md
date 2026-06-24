# Flat Loop Gate 계약

상태: `Draft`(decision/tool registry/budget policy/completion criteria slice는 2026-06-24 소유자 확정. 숫자 기본 한도는 후속)
선행 조건: [`gemma4-reuse.md`](gemma4-reuse.md)의 bounded flat loop 재사용 방침, Slice 0 LLM Gateway provider error 계약
후속 소비자: Phase 2 Analysis Pipeline(2B 비교 loop), Phase 4 Agentic Search, Writing/Review

## 목표와 범위

Application/Worker의 평면형 agent loop(`AgentLoopRunner`)가 정상 종료했는지, 아니면 왜 멈췄는지를 안정된 decision literal로 보고하고, task별로 허용된 domain tool과 다차원 budget 안에서 안전하게 실행하며, task별로 언제 `completed`로 종료하는지를 정의하는 계약을 확정한다. 숫자 기본 한도는 후속 slice로 둔다.

flat loop는 [`gemma4-reuse.md`](gemma4-reuse.md) 원칙을 따른다. sub-agent spawn, delegate tool, 중첩 agent loop 호출은 지원하지 않는다.

## Domain Tool Registry 계약

Registry와 tool handler는 LLM Gateway가 아니라 Application/Worker가 소유한다. Registry는 run 시작 시 task profile에 맞는 allowlist를 고정하며, 모델이나 API 요청자가 run 도중 tool을 추가하거나 허용 범위를 넓힐 수 없다.

모든 v1 tool은 조회·대조·사전 검증만 수행한다. 원문, memory, candidate, canon, index를 생성·수정·삭제하거나 승인 상태를 바꾸는 side effect는 허용하지 않는다. 저장과 상태 전이는 loop 밖의 Application service와 domain Gate가 담당한다.

### 등록 조건과 argument validation

각 registry entry는 최소한 다음을 가진다.

- 안정된 public tool `name`
- task별 설명과 입력 `JSON Schema`
- Application/Worker handler
- 허용 task profile
- 성공 result schema와 안정된 runtime error 분류

입력 schema가 없거나 root가 JSON object가 아니면 tool을 등록할 수 없다. 구체 업무 필드는 각 Phase의 공개 request/candidate/package schema가 확정될 때 같은 계약으로 잠근다. Registry validator는 다음 순서와 규칙을 공통으로 강제한다.

1. raw arguments를 JSON으로 정확히 한 번 parse한다. parse 실패를 `{}`로 바꾸지 않는다.
2. root object와 등록된 schema를 검증한다.
3. schema의 `required`, type, enum, bounds를 그대로 적용하고 unknown field는 `additionalProperties: false`로 거절한다.
4. string↔number 변환, singleton↔array 변환, 기본값 삽입 같은 coercion/repair를 하지 않는다.
5. 검증이 끝난 뒤에만 handler를 호출한다. 실패한 arguments는 실행·재시도하지 않고 `invalid_tool_arguments`로 종료한다.

`project_id`, task/trace identity, deadline은 모델 arguments가 아니다. 신뢰된 `ToolExecutionContext`에서 handler에 주입하며 모델이 덮어쓸 수 없다. handler도 모든 조회에 이 context의 `project_id`를 강제한다.

### v1 domain tool과 task profile

public tool literal은 다음 6종으로 고정한다. 상세 업무 payload schema는 해당 Phase 계약보다 먼저 추측해 만들지 않는다.

| Tool | 역할 | 허용 profile | 제한 |
|---|---|---|---|
| `search_memory` | lexical/semantic/direct 경로에서 memory 후보와 SOT pointer 검색 | `analysis_compare`, `context_search` | hit는 정본 사실이 아니며 후속 `load_memory` 필요 |
| `load_memory` | pointer를 같은 project의 MongoDB SOT로 재조회하고 status/version/source를 반환 | `analysis_compare`, `context_search` | cross-project, missing, stale 대상은 성공 result에 포함하지 않음 |
| `load_snapshot` | Analysis task에 고정된 snapshot/source text를 loader 계약으로 조회 | `analysis_compare` | run context의 snapshot 범위를 벗어날 수 없음 |
| `compare_memory` | 새 근거와 기존 memory의 값/version/status를 대조하는 deterministic preflight | `analysis_compare` | memory를 갱신하거나 Analysis decision을 확정하지 않음 |
| `validate_candidate` | candidate의 schema/source/version 조건을 사전 점검 | `analysis_compare` | loop 후 Analysis Gate를 대체하지 않음 |
| `validate_context` | ContextPackage 후보의 project/SOT/pointer/stale/budget 조건을 사전 점검 | `context_search` | loop 후 Context Gate를 대체하지 않음 |

task profile allowlist는 다음과 같다.

| Task profile | 허용 tool |
|---|---|
| `analysis_compare` | `search_memory`, `load_memory`, `load_snapshot`, `compare_memory`, `validate_candidate` |
| `context_search` | `search_memory`, `load_memory`, `validate_context` |
| `writing_generate` | 없음. MVP Writing AI는 검증된 ContextPackage만 입력받고 DB/검색 tool에 접근하지 않음 |

`spawn`, `delegate`, 다른 `AgentLoopRunner` 호출, 임의 code/shell 실행 tool은 등록 금지다. 등록됐지만 현재 profile에 허용되지 않은 tool 또는 미등록 tool을 모델이 요청하면 handler를 호출하지 않고 `blocked`로 종료한다. run 시작 전에 profile의 필수 tool이 빠진 경우도 provider 호출 전에 `blocked`로 종료한다.

`compare_memory`, `validate_candidate`, `validate_context`는 loop 중 피드백을 위한 preflight tool이다. 호출 성공이나 모델의 해석만으로 domain Gate를 통과한 것으로 보지 않는다. loop 종료 후 Analysis/Context Gate는 항상 독립 실행되며, Loop decision과 domain Gate 결과는 계속 직교한다.

### tool registry boundary matrix(구현 slice 회귀 lock list)

| 경계 | should-fire | should-NOT-fire |
|---|---|---|
| allowlist | 현재 profile에 등록·허용된 tool만 실행 | 미등록/다른 profile/spawn·delegate·nested loop는 실행하지 않고 `blocked` |
| arguments | schema-valid object만 handler에 전달 | invalid JSON/schema, unknown field, coercion/default repair는 실행하지 않고 `invalid_tool_arguments` |
| project scope | context의 `project_id`로만 조회 | 모델 argument로 project scope를 변경하거나 cross-project 결과 반환 금지 |
| runtime failure | valid args 이후 handler non-retryable 실패는 `tool_error` | argument 실패를 `tool_error`로 분류하지 않음 |
| Gate 합성 | preflight 결과와 별개로 loop 후 domain Gate 실행 | validate tool 성공을 Analysis/Context Gate 통과로 간주하지 않음 |
| Writing 경계 | 검증된 ContextPackage로 tool 없는 생성 허용 | Writing AI의 DB/검색 tool 직접 접근 금지 |

## Budget 계약

Budget은 run 시작 전에 서버의 task profile로 고정한다. 요청자는 profile 한도보다 작은 값을 요청할 수 있지만 늘리거나 차원을 끌 수 없다. 모든 차원은 필수이며 누락·음수·서로 모순된 policy는 provider 호출 전에 `blocked`로 종료한다. production 숫자 기본값은 Gemma Q4 benchmark 뒤에 확정하며, 그전 contract test는 각 한도를 명시적으로 주입한다.

### 차원과 계측

| Limit literal | 계측 단위와 포함 범위 | 초과 검사 |
|---|---|---|
| `max_iterations` | 시작한 provider 호출 수. retry도 각각 1회 | 다음 provider 호출이 한도를 넘기기 전 차단 |
| `max_wall_clock_ms` | monotonic clock 기준 runner 시작부터 terminal decision 직전까지. provider/tool/retry 시간 포함 | deadline 도달 시 진행 중 작업을 취소하고 종료 |
| `max_total_tokens` | 성공 응답마다 필수 `usage.prompt_tokens + usage.completion_tokens` 누적. retry 응답도 포함 | 응답 반영 직후 검사; 초과 응답은 성공 완료로 채택하지 않음 |
| `max_tool_calls` | handler 실행을 시작한 횟수. retry도 각각 1회 | 다음 handler 실행이 한도를 넘기기 전 차단 |
| `max_repeated_calls` | 동일 normalized tool call signature가 실행된 횟수 | 같은 signature의 다음 실행이 한도를 넘기기 전 차단 |

count 한도 `N`은 1~N번째 작업을 허용하고 N+1번째 시작을 막는다. 허용된 N번째 작업에서 completion criteria를 충족하면 `completed`가 가능하지만, 다음 작업이 필요하면 `budget_exhausted`다. `max_iterations`, `max_wall_clock_ms`, `max_total_tokens`는 1 이상이어야 한다. tool을 쓰는 profile의 `max_tool_calls`와 `max_repeated_calls`도 1 이상이며, tool 없는 `writing_generate`만 두 값을 0으로 둔다.

token은 provider 응답 뒤에 정확한 usage를 알 수 있으므로 한 응답 크기만큼 한도를 넘을 수 있는 post-accounting 차원이다. 누적값이 한도와 같고 같은 응답이 completion criteria를 충족하면 `completed`가 가능하다. 누적값이 한도를 **초과**하면 해당 content를 성공 결과로 채택하지 않고 `budget_exhausted`로 종료한다. `usage` 또는 두 token count가 누락·invalid이면 0으로 보정하지 않고 Gateway `provider_invalid_response` → Loop `provider_error`로 종료한다.

wall-clock deadline은 provider 자체 timeout과 구분한다. runner deadline이 먼저 만료돼 취소하면 `budget_exhausted`; 아직 runner budget이 남았는데 provider timeout이 발생하면 `provider_error`이며 상세 `provider_timeout`을 trace에 남긴다.

### repeated-call normalization

signature는 strict schema validation을 통과한 뒤 `tool name + canonical JSON arguments`로 만든다. canonical JSON은 object key를 정렬하고 JSON type/value를 보존한다. coercion 전후 값, 실행 result, trace ID는 signature에 넣지 않는다.

- 같은 tool + 같은 canonical arguments는 같은 signature다.
- 같은 tool이라도 arguments가 다르면 다른 signature다.
- 다른 tool은 arguments가 같아도 다른 signature다.
- invalid arguments는 handler를 실행하지 않으므로 tool-call/repeated-call budget을 소비하지 않는다.

### retry와 terminal decision 우선순위

provider/tool retry cap은 task profile의 필수 policy 값이며 0 이상이다. production 기본값은 benchmark와 운영 smoke 뒤에 확정한다. retry는 별도 무료 경로가 아니며 provider retry는 iteration/wall-clock/token을, tool retry는 wall-clock/tool-call/repeated-call을 그대로 소비한다.

- non-retryable provider/tool 오류는 즉시 `provider_error`/`tool_error`로 종료한다.
- retryable 오류의 retry cap이 먼저 소진되면 해당 `provider_error`/`tool_error`로 종료한다.
- retry cap은 남았지만 다음 retry를 어느 budget 차원이 막으면 `budget_exhausted`로 종료하고 원래 오류 literal을 trace에 보존한다.
- runner deadline이 도달하면 새 retry를 시작하지 않는다. 사용자 cancel 입력은 본 v1 request 계약에서 지원하지 않으며, deadline에 의한 cancel만 `budget_exhausted`다.

### budget boundary matrix(구현 slice 회귀 lock list)

| 경계 | should-fire | should-NOT-fire |
|---|---|---|
| iteration | N번째 provider 호출까지 허용, N+1 필요 시 `budget_exhausted` | N번째 정상 완료를 과잉 차단하지 않음 |
| wall-clock | runner deadline 도달 시 `budget_exhausted` | budget 내 provider timeout은 `provider_error` |
| token | 누적 `== limit` 완료 허용; 누적 `> limit`은 `budget_exhausted` | missing usage를 0으로 계산하지 않고 `provider_error` |
| tool-call | N번째 handler 실행까지 허용, N+1 필요 시 `budget_exhausted` | invalid args는 handler 미실행이므로 count하지 않음 |
| repeated-call | 같은 signature N회 허용, N+1은 `budget_exhausted` | 같은 tool의 다른 valid arguments는 반복으로 오인하지 않음 |
| retry | retry cap 소진은 원래 error decision, 다른 budget이 retry를 막으면 `budget_exhausted` | retry를 budget 밖 무료 호출로 처리하지 않음 |

## 세 Gate는 다른 층위(직교)

Loop Gate decision은 domain Gate decision과 **병합하지 않는다**. 세 Gate는 서로 다른 질문에 답하며 순차적으로 합성된다.

| Gate | 소속 | 질문 | 결정 주체 |
|---|---|---|---|
| Loop Gate(본 문서) | `AgentLoopRunner` | 이 loop run이 **왜** 끝났나 | run 종료 상태 |
| Analysis Gate([`02-analysis-pipeline.md`](02-analysis-pipeline.md) §Analysis Gate) | memory candidate 검증 | 후보를 **어떻게 처분**할까 | `create/update/add_evidence/no_change/conflict` + AnalysisJob 상태 |
| Context Gate([`04-agentic-search.md`](04-agentic-search.md) §Context Gate) | context package 검증 | package를 **전달해도 되나** | project_id·SOT·pointer/version·stale·budget 검사 |

합성 흐름: loop run 종료(Loop decision) → 산출물이 해당 domain Gate 검사를 별도로 받음. Loop decision은 domain Gate 결과로 대체되지 않는다.

## 종료 decision literal

```text
completed
awaiting_review
blocked
budget_exhausted
invalid_tool_arguments
tool_error
provider_error
```

각 decision은 **상호 배타적**이며 한 run은 정확히 하나로 종료된다.

### completed

loop가 최종 answer를 도출하거나 계획된 작업을 정상 완료한 상태. **loop 종료 상태만** 의미하며, 산출물이 Analysis/Context Gate를 통과했는지와는 무관하다("completed but Gate rejected" 가능, Gate 결과는 trace).

### awaiting_review

산출물은 있으나 자율 완료 기준(예: confidence 부족, 모호함, 미해결 분기)을 만족하지 못해 사람 판단이 필요한 상태. Analysis 후보 저장 상태인 `needs_review`([`02-analysis-pipeline.md`](02-analysis-pipeline.md))와의 **단어 충돌을 피하려고** `needs_review`에서 rename했다. 같은 개념이 아니며 층위가 다르다(loop run decision vs candidate status).

### blocked

전제조건 결핍이나 해결 불가한 의존성(예: 필수 tool 미등록, 참조 memory 부재)으로 더 이상 진행할 수 없는 상태. 오류가 아니라 구조적 불가능.

### budget_exhausted

iteration·wall-clock·token·tool-call·repeated-call 예산이 완료 전 추가 진행을 막거나 token 한도를 초과해 멈춘 상태. **성공이 아니다**([`gemma4-reuse.md`](gemma4-reuse.md)의 "max iteration 시 마지막 content를 정상 완료로 오해" 보강점). budget 차원과 초과 정책은 본 문서에서 확정했고 숫자 기본 한도는 Gemma Q4 benchmark 이후 확정한다.

### invalid_tool_arguments

모델이 malformed tool arguments(잘못된 JSON 또는 schema 위반)를 출력해 **실행을 차단**한 상태. 이전 참조 구현처럼 `{}`로 강제 변환해 실행하지 않는다([`gemma4-reuse.md`](gemma4-reuse.md) 보강점). args는 유효했으나 tool이 runtime 오류를 낸 경우는 `tool_error`로 간다.

### tool_error

tool 실행 중 non-retryable 오류가 발생하거나 retryable 오류의 tool retry cap이 먼저 소진돼 종료한 상태. retry cap은 남았지만 다른 budget이 다음 retry를 막으면 `budget_exhausted`로 귀결된다.

### provider_error

LLM provider(Gateway) 실패로 종료한 상태. **coarse umbrella decision**이다. Gateway의 구체 5 literal(`provider_unavailable`/`provider_timeout`/`provider_overloaded`/`provider_invalid_response`/`provider_request_rejected`, Slice 0.3)은 Loop decision으로 전파하지 않고 **trace에 보존**한다. retryable 오류의 provider retry cap이 먼저 소진되면 `provider_error`, 다른 budget이 다음 retry를 막으면 `budget_exhausted`다.

## boundary matrix(구현 slice 회귀 lock list)

구현 slice는 아래 should-fire/should-NOT-fire 분기를 양방향 회귀로 고정한다. 빈 칸 없이 각 decision을 잠근다.

| Decision | should-fire | should-NOT-fire(인접 decision과의 구분) |
|---|---|---|
| completed | 최종 answer 도출 + 완료 기준 충족 + 정상 종료 | 예산 소진 아님(`budget_exhausted`); 오류 종료 아님; domain Gate 통과 불필요(over-strict guard: Gate reject여도 completed) |
| awaiting_review | 산출물 있으나 자율 완료 기준 미달 | 오류 종료 아님; 예산 전 공백 아님; candidate `needs_review`와 다른 층위 |
| blocked | 전제결핍/해결불가 의존성 | tool runtime 오류 아님(`tool_error`); 단순 예산 소진 아님 |
| budget_exhausted | 임의 예산 차원 한도 도달 | 예산 내 정상 완료 아님(`completed`); **성공 위장 금지**(under-strict guard) |
| invalid_tool_arguments | malformed args + 실행 차단 | 유효 args runtime 오류 아님(`tool_error`); 도구 미호출 정상 흐름 아님 |
| tool_error | tool non-retryable runtime 오류 | malformed args 아님(`invalid_tool_arguments`); provider 실패 아님(`provider_error`); retryable은 재시도 정책 |
| provider_error | Gateway 실패로 종료 | tool runtime 오류 아님(`tool_error`); 5 literal 자체가 아님(umbrella, 상세는 trace) |

## task별 completion criteria 계약

`completed`와 `awaiting_review`를 가르는 자율 완료 기준을 task profile별로 확정한다. 본 계약은 **Loop 층위**의 판정이며 domain Gate와 직교한다. 산출물이 Analysis/Context/Writing Gate를 통과하는지는 completion 판정에 들어가지 않는다("completed but Gate rejected" 가능).

### 공통 판정(하이브리드)

`completed`는 다음 두 조건을 **모두** 충족할 때만 가능하다.

1. **구조 조건(결정적)**: task의 목표 산출물이 정의된 형태로 존재한다.
2. **자율 조건(self-report)**: 모델이 미해결 분기·추가 진행 필요를 보고하지 않는다.

산출물은 존재하나 두 조건 중 하나가 미달이면 `awaiting_review`. 산출물 자체를 만들 수 없는 전제 결핍/해결 불가 의존성이면 `blocked`. 예산이 추가 진행을 막으면 `budget_exhausted`. 이 우선순위는 [종료 decision literal](#종료-decision-literal)의 상호 배타성을 따른다.

### 완결된 산출 vs loop 미해결의 구분(핵심)

모델이 개별 항목의 불확실성을 **산출물 안에 명시적으로 표현**하면(candidate `needs_review` status, confidence 표기, `conflict` 후보 등) 그것은 **완결된 산출**이며 loop는 `completed`다. 불확실성의 처분은 candidate status와 loop 후 domain Gate의 소관이지 loop 종료 상태가 아니다.

반면 모델이 **산출물 자체를 어떻게 도출할지 미해결**이라고 self-report하면 loop 미해결이며 `awaiting_review`다. 이 구분이 본 계약의 중심이다.

두 경우를 기계적으로 가르는 것은 **신호가 나오는 채널**이다. self-report는 모델이 run을 종료할 때 산출물을 확정 제출(`finalize`)하는 대신 사람 판단을 요청(`defer`)하는 **loop 종료 채널**의 명시적 결정이다. candidate `needs_review` status·confidence 표기·`conflict` 후보는 **산출물 데이터 채널**의 필드 값이며, 모델이 이를 담아 산출물을 `finalize`하면 종료 채널은 여전히 `completed`다. 두 채널은 직교한다. 따라서 `analysis_compare`가 모호 대상을 `needs_review` 후보로 담아 제출하는 것(데이터 채널)과 `writing_generate`가 산출물을 확정하지 못해 `defer`하는 것(종료 채널)의 차이는 채널 차이이지 모순이 아니다. 종료 채널 신호의 구체 wire 형식(명시 토큰·구조화 필드 등)은 Phase 4 `AgentLoopRunner` 구현 slice에서 확정한다.

### task profile별 기준

| Task profile | 목표 산출물 | `completed` 구조 조건 | `awaiting_review` 분기 |
|---|---|---|---|
| `analysis_compare` | 입력 분석 대상별 변경 작업 후보(`create`/`update`/`add_evidence`/`no_change`/`conflict` 중 하나) | 입력된 모든 대상이 후보로 처리됨. 개별 모호 대상은 candidate `needs_review` status로 표현 | 모델이 어떤 대상을 어떻게 후보화할지 자체를 미해결로 self-report |
| `context_search` | 검증 가능한 ContextPackage 후보 1건 | 요청 의도를 충족하는 package 후보가 pointer/budget을 갖춰 빌드됨 | 모델이 충분한 근거 미수집·검색 계획 미해결을 self-report |
| `writing_generate` | WritingCandidate 1건 | candidate가 생성됨(tool 없음, budget상 tool 0회) | 모델이 산출물 자체의 모호·충돌을 self-report |

- **`analysis_compare`**: 다수 대상을 다루므로, 일부 대상만 확신 후보가 나오고 일부는 모호해도 run은 `completed`로 종료한다. 모호 대상은 candidate `needs_review` status로 표현되며 이는 완결된 산출이다(소유자 결정 2026-06-24). loop가 `awaiting_review`인 경우는 모델이 후보화 자체를 미해결로 보고할 때다. `compare_memory`/`validate_candidate` preflight 성공은 `completed` 신호가 아니며, 후보 처분은 loop 후 Analysis Gate가 독립 판정한다.
- **`context_search`**: package 후보가 빌드되고 모델이 추가 검색이 불필요하다고 보고하면 `completed`. `validate_context` preflight 성공은 신호일 뿐 Context Gate를 대체하지 않는다. 필수 tool 미등록·SOT 참조 부재 같은 구조적 불가는 `blocked`.
- **`writing_generate`**: tool이 없어 1~소수 provider 호출로 candidate를 생성한다. 모델이 모호·충돌을 self-report하지 않으면 `completed`, self-report하면 `awaiting_review`다(소유자 결정 2026-06-24). 모호·충돌의 구체 판정은 candidate 메타로도 전달돼 loop 후 Writing Gate가 본다.

### completion boundary matrix(구현 slice 회귀 lock list)

각 task를 `completed` 분기와 `awaiting_review` 분기 2행으로 횡일관하게 잠근다. 모든 task의 `completed` 행은 over-strict guard(Gate reject여도 `completed`)를 포함한다.

| Task profile | 분기 | should-fire | should-NOT-fire(over-strict / 인접 decision 구분) |
|---|---|---|---|
| `analysis_compare` | `completed` | 모든 대상 후보화 + 후보화 미해결 `defer` 없음 | 일부 후보가 `needs_review` status여도 `completed` 유지(`awaiting_review`로 승격 금지); Gate reject여도 `completed` |
| `analysis_compare` | `awaiting_review` | 모델이 후보화 자체를 미해결로 `defer` | 개별 후보 모호를 `awaiting_review`로 승격하지 않음 |
| `context_search` | `completed` | package 후보 빌드 + 추가 검색 불필요 보고 | preflight 성공만으로 `completed` 처리 금지; Gate reject여도 `completed` |
| `context_search` | `awaiting_review` | 모델이 근거 부족·검색 계획 미해결을 `defer` | 정상 빌드된 package를 근거 부족으로 오인하지 않음 |
| `writing_generate` | `completed` | candidate 생성 + 모호·충돌 `defer` 없음 | Gate reject여도 `completed`(over-strict guard) |
| `writing_generate` | `awaiting_review` | 모델이 산출물의 모호·충돌을 `defer` | candidate 생성 실패 아닌 모호를 `blocked`/`tool_error`로 분류하지 않음 |

## Loop Gate 보강점 반영

[`gemma4-reuse.md`](gemma4-reuse.md)의 7개 보강점이 decision에 어떻게 반영되는지:

| 참조 보강점 | 본 계약 반영 |
|---|---|
| max iteration → 정상 완료 오인 | `budget_exhausted`는 비성공 |
| invalid args → `{}` 강제 | `invalid_tool_arguments`로 실행 차단 |
| tool exception → JSON 문자열 계속 | `tool_error`(retryable/non-retryable 분리) |
| 같은 tool call 반복 허용 | repeated-call budget → `budget_exhausted` |
| iteration만 제한 | 다차원 budget → `budget_exhausted` |
| answer 존재 = 완료 | 완료 기준 미충족 시 `completed`가 아닌 `awaiting_review` |
| thinking trace 저장 | (본 decision slice 범위 밖, 저장 정책은 별도) |

## 제외 범위(후속 slice)

- **숫자 기본 한도**: 각 budget 및 retry cap의 production 값. hardware benchmark([`llm-gateway.md`](llm-gateway.md) §Slice 0 benchmark) 이후 확정한다.
- **저장 정책**: trace의 thinking text 보존 여부·길이 제한·기본 비보존.

## 착수 전 결정사항(남음)

- [x] tool registry 계약 확정: strict validator, task별 allowlist, v1 domain tool 6종(2026-06-24 소유자 확정)
- [x] budget 5차원·계측·초과·retry 우선순위 확정(2026-06-24 소유자 확정). 숫자 기본 한도는 benchmark 이후
- [x] task별 completion criteria 확정(Analysis/Context/Writing): 하이브리드 판정, 완결된 산출 vs loop 미해결 구분(2026-06-24 소유자 확정)
- [x] decision literal 7종 및 세 Gate 직교 원칙(2026-06-24 소유자 확정)
- [x] `needs_review` → `awaiting_review` rename(Analysis candidate status 충돌 해소)
- [x] `provider_error` umbrella + Gateway 5 literal trace 보존
- [x] `completed` = loop 종료 상태만(domain Gate 통과 별개)

## 산출물(본 slice)

1. 본 decision 계약 문서
2. (구현 시) `AgentLoopRunner` 종료 decision enum과 양방향 회귀 — Phase 4 구현 slice에서 도입

## 원문 및 상세 참고

- [`gemma4-reuse.md`](gemma4-reuse.md) §Loop Gate 보강점, §종료 decision 논의안, §평면형 Agentic 구조
- [`04-agentic-search.md`](04-agentic-search.md) §Agentic 실행 경계, §Context Gate 최소 검사, §착수 전 결정사항(9번)
- [`02-analysis-pipeline.md`](02-analysis-pipeline.md) §Analysis Gate 최소 검사, §착수 전 결정사항
- [`implementation-plan.md`](implementation-plan.md)
