# Flat Loop Gate 계약

상태: `Draft`(decision slice는 2026-06-24 소유자 확정. tool/budget slice는 후속)
선행 조건: [`gemma4-reuse.md`](gemma4-reuse.md)의 bounded flat loop 재사용 방침, Slice 0 LLM Gateway provider error 계약
후속 소비자: Phase 2 Analysis Pipeline(2B 비교 loop), Phase 4 Agentic Search, Writing/Review

## 목표와 범위

Application/Worker의 평면형 agent loop(`AgentLoopRunner`)가 정상 종료했는지, 아니면 왜 멈췄는지를 안정된 decision literal로 보고하는 계약을 확정한다. 이 문서는 decision slice만 다룬다. tool registry 계약과 budget 차원·한도 계약은 후속 slice로 둔다.

flat loop는 [`gemma4-reuse.md`](gemma4-reuse.md) 원칙을 따른다. sub-agent spawn, delegate tool, 중첩 agent loop 호출은 지원하지 않는다.

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

iteration·wall-clock·token·tool-call·repeated-call 예산 중 하나가 한도에 도달해 완료 전에 멈춘 상태. **성공이 아니다**([`gemma4-reuse.md`](gemma4-reuse.md)의 "max iteration 시 마지막 content를 정상 완료로 오해" 보강점). 정확한 budget 차원·한도는 budget slice에서 확정한다.

### invalid_tool_arguments

모델이 malformed tool arguments(잘못된 JSON 또는 schema 위반)를 출력해 **실행을 차단**한 상태. 이전 참조 구현처럼 `{}`로 강제 변환해 실행하지 않는다([`gemma4-reuse.md`](gemma4-reuse.md) 보강점). args는 유효했으나 tool이 runtime 오류를 낸 경우는 `tool_error`로 간다.

### tool_error

tool 실행 중 non-retryable 오류가 발생해 종료한 상태. retryable tool 오류는 재시도 정책(budget slice)이 처리하며, 재시도 예산 소진 시에만 `tool_error`(또는 `budget_exhausted`)로 귀결된다.

### provider_error

LLM provider(Gateway) 실패로 종료한 상태. **coarse umbrella decision**이다. Gateway의 구체 5 literal(`provider_unavailable`/`provider_timeout`/`provider_overloaded`/`provider_invalid_response`/`provider_request_rejected`, Slice 0.3)은 Loop decision으로 전파하지 않고 **trace에 보존**한다. retryable provider 오류의 재시도 정책은 budget slice가 담당한다.

## boundary matrix(구현 slice 회귀 lock list)

구현 slice는 아래 should-fire/should-NOT-fire 분기를 양방향 회귀로 고정한다. 빈 칸 없이 각 decision을 잠근다.

| Decision | should-fire | should-NOT-fire(인접 decision과의 구분) |
|---|---|---|
| completed | 최종 answer 도출 + 완료 기준 충족 + 정상 종료 | 예산 소감 아님(`budget_exhausted`); 오류 종료 아님; domain Gate 통과 불필요(over-strict guard: Gate reject여도 completed) |
| awaiting_review | 산출물 있으나 자율 완료 기준 미달 | 오류 종료 아님; 예산 전 공백 아님; candidate `needs_review`와 다른 층위 |
| blocked | 전제결핍/해결불가 의존성 | tool runtime 오류 아님(`tool_error`); 단순 예산 소진 아님 |
| budget_exhausted | 임의 예산 차원 한도 도달 | 예산 내 정상 완료 아님(`completed`); **성공 위장 금지**(under-strict guard) |
| invalid_tool_arguments | malformed args + 실행 차단 | 유효 args runtime 오류 아님(`tool_error`); 도구 미호출 정상 흐름 아님 |
| tool_error | tool non-retryable runtime 오류 | malformed args 아님(`invalid_tool_arguments`); provider 실패 아님(`provider_error`); retryable은 재시도 정책 |
| provider_error | Gateway 실패로 종료 | tool runtime 오류 아님(`tool_error`); 5 literal 자체가 아님(umbrella, 상세는 trace) |

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

- **tool registry 계약**: 허용 tool allowlist, argument schema/validator, domain tool 목록. 예시 이름(search_context/load_snapshot/resolve_memory/validate_candidate)은 확정 전이다.
- **budget 계약**: 각 예산 차원의 literal·기본 한도·초과 시 정책. 기본 한도는 hardware benchmark([`llm-gateway.md`](llm-gateway.md) §Slice 0 benchmark) 이후 확정한다.
- **completion criteria 계약**: task별 `completed` 판정 기준(필수 evidence/tool 사용). Analysis/Context/Writing task별로 별도 확정.
- **저장 정책**: trace의 thinking text 보존 여부·길이 제한·기본 비보존.

## 착수 전 결정사항(남음)

- [ ] tool registry 계약 확정(후속 slice)
- [ ] budget 차원·한도·초과 정책 확정(후속 slice)
- [ ] task별 completion criteria 확정(Analysis/Context/Writing)
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
