# `gemma4_12b` 참조 구현 재사용 계획

상태: `Reviewed for planning`  
참조 경로: `/mnt/d/devel/gemma4_12b`  
참조 commit: `485c4e2fe78323c408fcb64d08c2cdc9ec94f9e3`  
검토 시점 working tree: clean

## 결론

참조 구현은 Slice 0의 좋은 기반이다. 전체 repo를 그대로 복제하거나 submodule로 연결하기보다, 검증된 작은 단위를 현재 monorepo의 책임 경계에 맞춰 선택 이관한다.

핵심 원칙:

- model server와 inference client/schema는 적극 재사용한다.
- agent loop 알고리즘은 재사용하되 실행 위치를 Application/Worker로 옮긴다.
- demo tool과 프로젝트 DB 접근을 Gateway에 넣지 않는다.
- 현재와 동일하게 평면형 단일 agent loop만 허용한다.
- sub-agent spawn, delegate tool, 중첩 agent request는 명시적으로 제외한다.

## 확인된 참조 구성

| 영역 | 현재 구현 |
|---|---|
| model | `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0` |
| inference | `ghcr.io/ggml-org/llama.cpp:server-cuda` |
| hardware target | RTX 3050 6GB + CPU/RAM hybrid offload |
| context/concurrency | total context 8192, default parallel slot 1 |
| Gateway | FastAPI + async `httpx` client |
| protocol | non-streaming OpenAI-compatible chat/tool calling subset |
| thinking | `chat_template_kwargs.enable_thinking`으로 per-request 제어 |
| agentic | model → allowlisted tool → result → model의 bounded flat loop |
| loop bound | `max_iterations`, request range 1~50, default 10 |
| sub-agent | 구현 없음 |

## 재사용 판정

### 거의 그대로 이관

| 참조 파일/영역 | 이관 대상 | 이유 |
|---|---|---|
| `docker-compose.yml`의 `llama-server` | Slice 0 model service | Q4_0, volume cache, CUDA hybrid, healthcheck가 준비됨 |
| `gateway/app/schemas.py`의 chat/tool types | provider contract 초안 | OpenAI-compatible subset과 stream 거절 경계가 명시됨 |
| `gateway/app/llama_client.py` | inference adapter | async client, response parse, thinking template 전달이 구현됨 |
| thinking 관련 tests | provider contract tests | 과거 실제 결함인 legacy think-token과 template flag 경계를 잠금 |
| model volume/cache 원칙 | infra configuration | weight를 repo/image와 분리함 |

“거의 그대로”도 package path, 설정 이름, 오류 envelope, request ID는 현재 프로젝트 계약에 맞춰 수정한다.

### 수정 후 이관

| 참조 파일/영역 | 수정 방향 |
|---|---|
| `gateway/app/agent.py` | Application/Worker의 flat loop runner로 이동 |
| `ToolRegistry` interface | domain tool의 allowlist/argument validator로 재작성 |
| `AgentRequest/Response/Step` | project/task/trace/budget/decision 필드 추가 |
| `/health` | liveness와 model readiness 분리, degraded 상태의 HTTP 계약 확정 |
| timeout | 전역 1200초뿐 아니라 요청 deadline/cancel과 job retry 연동 |
| error handling | raw exception string 대신 안정된 error literal/envelope |
| CORS | local UI origin만 허용하도록 제한 |

### 가져오지 않음

- `get_weather`, `calculator`, `get_current_time` demo tool
- Gateway가 프로젝트 MongoDB/검색 인덱스에 직접 접근하는 구조
- README의 오래된 `<|think|>` system prompt 주입 설명
- streaming이 구현된 것처럼 보이는 계약
- sub-agent/delegation 관련 확장
- 모델 weight와 local cache

## Loop Gate 보강점

현재 구현에는 tool allowlist와 `max_iterations`가 있지만, 프로젝트 workflow의 Gate로 쓰기에는 부족하다.

| 현재 동작 | 위험 | 필요한 보강 |
|---|---|---|
| max iteration 시 마지막 assistant content 반환 | 정상 완료로 오해 가능 | `budget_exhausted` decision과 비성공 상태 |
| 잘못된 tool arguments JSON을 `{}`로 변경 | 모델 오류 은폐·잘못된 기본 실행 | `invalid_tool_arguments` finding 후 실행 금지 |
| tool exception을 JSON 문자열로 반환하고 계속 진행 | 실패 종류가 trace에서 약함 | retryable/non-retryable 분리와 decision 반영 |
| 같은 tool call 반복 허용 | 무의미한 loop와 자원 소모 | normalized call signature 반복 감지 |
| iteration만 제한 | 긴 단일 호출/다수 tool call 제어 부족 | wall-clock, token, tool-call count budget |
| 최종 answer 존재만으로 완료 | 필수 evidence/tool 미사용 가능 | task별 completion criteria와 output Gate |
| thinking text를 steps에 저장 | 민감/대용량 trace 가능 | 저장 정책, 길이 제한, 기본 비보존 검토 |

## 현재 프로젝트의 평면형 Agentic 구조

```text
Application/Worker AgentLoopRunner
  ├─ LLM Gateway: chat/tool_calls만 반환
  ├─ Domain Tool Registry: 허용 도구와 argument schema
  │    ├─ search_context
  │    ├─ load_snapshot
  │    ├─ resolve_memory
  │    └─ validate_candidate
  ├─ Loop Gate: iteration/time/token/repeat/error budget
  └─ Trace + decision
```

도구 이름은 예시이며 Phase 계약 확정 전 public literal이 아니다. Loop runner는 다른 AgentLoopRunner를 tool로 호출할 수 없고, agent spawn/delegate 도구를 등록하지 않는다.

## 종료 decision 논의안

```text
completed
needs_review
blocked
budget_exhausted
invalid_tool_arguments
tool_error
provider_error
```

literal은 아직 확정 전이다. Agentic Search와 Analysis의 기존 Gate decision과 중복되지 않도록 공통 오류/decision 계약에서 조정한다.

## 테스트 이관과 추가

### 참조에서 재현할 테스트

- `stream=true` 명시적 거절
- 요청 tool 중 등록된 tool만 모델에 노출
- 실행 가능한 tool이 하나도 없으면 모델 호출 전 거절
- `thinking=false/true`가 `enable_thinking`으로 전달
- caller의 명시적 template flag 우선순위
- legacy `<|think|>`가 message에 주입되지 않음

### 추가할 양방향 회귀

- 등록 tool은 실행되지만 미등록 tool은 실행되지 않음
- 올바른 arguments는 실행되지만 invalid JSON은 `{}`로 실행되지 않음
- 정상 종료는 `completed`, iteration 소진은 성공이 아닌 `budget_exhausted`
- 같은 tool의 다른 정당한 argument는 허용하되 완전히 같은 call 반복은 차단
- retryable tool error는 정책만큼 재시도하되 non-retryable error는 즉시 종료
- 필수 evidence를 모은 answer는 통과하되 evidence 없는 단정은 완료 처리하지 않음
- flat loop는 동작하되 spawn/delegate/nested agent request는 schema/registry에서 거절

## 검토 결과와 제한

- 참조 repo의 unit contract test 8개는 2026-06-24에 통과했다.
- 검토 시 `gemma4_12b`의 llama/gateway container는 실행 중이 아니어서 실모델 smoke는 재실행하지 않았다.
- 참조 repo의 최근 work log에는 thinking off의 실모델 결과가 기록돼 있지만, 이번 검토에서 독립 재현한 것은 아니다.
- 현재 repo에는 코드 자체의 LICENSE 파일이 없고 README에는 Gemma model terms만 있다. 동일 소유자의 내부 재사용은 사용자가 허용했지만, 외부 공개·배포 전에는 source code license/provenance를 명시해야 한다.
- 일부 README/설계 문서는 legacy `<|think|>` 주입을 설명하지만 현재 code/test/work log는 `chat_template_kwargs.enable_thinking`을 canonical mechanism으로 사용한다. 이관 시 code/test를 기준으로 한다.

## 이관 순서

1. 참조 commit과 이관 파일 목록을 기록한다.
2. 참조의 8개 contract test를 현재 package 경계에 맞게 먼저 이식한다.
3. Compose model service와 schema/client를 이관해 tests와 smoke를 통과시킨다.
4. AgentEngine의 loop 골격을 Application/Worker로 옮긴다.
5. demo registry 대신 domain tool interface와 Loop Gate를 구현한다.
6. 추가 양방향 회귀와 실제 Gemma Q4 smoke를 통과시킨다.

## 관련 계획

- [`implementation-plan.md`](implementation-plan.md)
- [`llm-gateway.md`](llm-gateway.md)
- [`04-agentic-search.md`](04-agentic-search.md)
- [`02-analysis-pipeline.md`](02-analysis-pipeline.md)
