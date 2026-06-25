# 시스템 정본 계약 SoT

상태: `Draft`  
목적: 흩어진 계획 문서의 확정된 계약과 서비스 경계를 한 곳에서 추적한다.  
적용 범위: 제품 경계, 서비스 책임, 데이터 정본, Gateway, AgentLoopRunner, Gate 합성, 검증 기록.

이 문서는 세부 Phase 계획을 대체하지 않는다. 대신 구현자가 먼저 확인해야 할 **정본 계약 인덱스**다. 아래 계약과 세부 계획이 충돌하면 이 문서의 [문서 우선순위](#문서-우선순위)에 따라 조정한다.

## 문서 우선순위

1. 사용자가 명시 승인했고 이 문서 또는 해당 Phase 계획에 반영된 결정
2. `Approved` 상태의 본 SoT와 Phase 계획
3. `Draft` 상태이지만 구현·검증·커밋으로 잠긴 계약 문서
4. `docs/plans/`의 미구현 Phase 계획
5. `docs/` 루트의 아이디에이션 문서

동일 우선순위 문서끼리 충돌하면 구현하지 않는다. 충돌을 작업 로그와 해당 문서에 기록하고 사용자에게 어느 쪽이 canonical인지 확인한다.

현재 이 문서는 `Draft`다. 새 구현은 아래 "확정된 계약"만 구현 기준으로 삼고, "미확정" 항목은 추측해 채우지 않는다.

## 문서 역할

| 문서 | 역할 | 지위 |
|---|---|---|
| 이 문서 | 서비스/계약 SoT 인덱스와 우선순위 | Draft SoT |
| [`plans/README.md`](plans/README.md) | 계획 문서 진입점과 Phase/MVP 관계 | Draft |
| [`plans/00-foundations.md`](plans/00-foundations.md) | 전역 원칙과 제품 경계 | Draft |
| [`plans/implementation-plan.md`](plans/implementation-plan.md) | 구현 순서, slice 상태, 검증 gate | Draft |
| [`plans/llm-gateway.md`](plans/llm-gateway.md) | LLM Gateway 계약과 Gemma Q4 검증 | Proposed |
| [`plans/flat-loop-gate.md`](plans/flat-loop-gate.md) | AgentLoopRunner decision/tool/budget/completion 계약 | Draft, 일부 구현 검증됨 |
| [`plans/product-shell.md`](plans/product-shell.md) | 사용자 제품 표면 | Draft |
| [`plans/01-core-sot.md`](plans/01-core-sot.md) | MongoDB 정본 저장 계약 | Draft |
| [`plans/02-analysis-pipeline.md`](plans/02-analysis-pipeline.md) | 분석 후보와 Analysis Gate | Draft |
| [`plans/03-indexing.md`](plans/03-indexing.md) | Chroma/ES 파생 인덱스 | Draft |
| [`plans/04-agentic-search.md`](plans/04-agentic-search.md) | ContextPackage와 Context Gate | Draft |
| [`plans/05-writing-ai.md`](plans/05-writing-ai.md) | WritingCandidate와 Writing Gate | Draft |
| [`plans/06-review-ui.md`](plans/06-review-ui.md) | 후보 검토와 상태 전이 UI | Draft |
| [`contracts.md`](contracts.md) | 초기 계약 아이디에이션 | Reference only |

## 시스템 경계

처음에는 monorepo 안에서 서비스 경계를 나눈다. 본격 MSA는 전제하지 않는다.

| 구성요소 | 소유 책임 | 소유하지 않는 것 |
|---|---|---|
| Product Shell | 프로젝트/원고 작업 공간, 처리 상태, 내보내기 | 기억 정본, AI 판정 |
| Application API | 제품 API, domain service, Gate 합성, request context | 모델 lifecycle, 벡터/lexical 정본 판정 |
| Worker | 분석/색인/검색 job 실행, AgentLoopRunner 실행 | 사용자 UI, LLM Gateway 내부 transport |
| MongoDB | 원문, snapshot, source_ref, 상태, version, 구조화 기억의 정본 | 의미 검색 또는 lexical ranking |
| ChromaDB | semantic retrieval cache | canonical memory |
| Elasticsearch | lexical/metadata retrieval index | canonical memory |
| LLM Gateway | model load, inference, provider error, usage/timing | Mongo/Chroma/ES 접근, project memory lookup, domain tool 실행 |
| AgentLoopRunner | bounded flat loop, tool allowlist, budget, terminal decision | domain Gate 통과 여부, memory update |
| Gate | 후보 검증과 처분 | 사용자 의도 최종 확정, loop 종료 원인 |
| Review UI | 승인/거절/수정 UX | 자동 canon 승격 규칙의 독자 소유 |

## 확정된 전역 계약

### 제품과 프로젝트 경계

- MVP는 계정/인증이 없는 단일 사용자 시스템이다.
- 그래도 모든 저장·검색·Gate·tool handler는 `project_id`를 강제한다.
- 향후 다중 사용자를 위해 `user_id`를 지금 억지로 넣지 않는다.
- Product Shell은 프로젝트/원고 작업 표면이며 AI 기억의 정본을 별도로 소유하지 않는다.

### Source of Truth

- MongoDB가 원문과 구조화 기억의 SOT다.
- 원문 snapshot은 primary SOT다.
- 사용자가 승인한 설정은 canonical SOT다.
- 분석 결과는 저장되더라도 derived SOT이며 상태와 근거가 필요하다.
- ChromaDB와 Elasticsearch는 MongoDB로 재생성 가능한 파생 인덱스다.
- 검색 hit는 MongoDB pointer/version/hash로 재조회하기 전까지 정본 사실이 아니다.

### Candidate 원칙

- 모든 AI 출력은 candidate다.
- Writing AI 출력은 `draft_candidate`다.
- Analysis AI 출력은 `analysis_candidate`다.
- Agentic Search 출력은 `context_candidate`다.
- candidate는 Gate 또는 사용자 승인 없이 canonical 상태가 되지 않는다.
- 후보 상태와 loop 종료 decision은 다른 층위다. 예: Analysis candidate `needs_review`와 Loop decision `awaiting_review`는 같은 뜻이 아니다.

### 추적성

- 구조화 기억에는 `project_id`, 상태, version, `source_ref`가 필요하다.
- `source_ref`는 snapshot/block/span/quote/hash로 원문을 다시 찾을 수 있어야 한다.
- 검색 결과와 ContextPackage 항목은 MongoDB pointer로 SOT를 다시 읽고 version/hash를 확인해야 한다.
- trace에는 provider error detail, loop decision, tool call, Gate finding의 원인을 보존한다.

## 서비스별 계약 SoT

### LLM Gateway

정본 세부 문서: [`plans/llm-gateway.md`](plans/llm-gateway.md)

확정된 구현 계약:

- Gateway는 같은 repo에 두되 독립 프로세스/컨테이너로 실행한다.
- Application은 모델 파일 경로, CUDA 설정, inference engine 세부를 알지 않는다.
- Gateway는 MongoDB/ChromaDB/Elasticsearch에 접근하지 않는다.
- Gateway는 domain tool registry나 AgentLoopRunner terminal decision을 소유하지 않는다.
- 현재 provider error literal은 다음 5종이다.

```text
provider_unavailable
provider_timeout
provider_overloaded
provider_invalid_response
provider_request_rejected
```

- HTTP/text completion 성공 응답은 `model`, 첫 choice `message.content`, `finish_reason`, `usage.prompt_tokens`, `usage.completion_tokens`를 모두 유효값으로 가져야 한다.
- `usage` 또는 token count 누락/invalid는 0으로 보정하지 않고 `provider_invalid_response`다.
- 명시적 token count 0은 유효하다.
- `HttpxJsonTransport`는 `trust_env=false`가 기본이며, proxy는 필요할 때만 opt-in한다.
- 실제 tool-call parsing은 아직 미구현이다.

검증 근거:

- Slice 0.1~0.6 unit/contract 회귀
- [`verifications/2026-06-24/llm_gateway_f1_f2_closure.md`](verifications/2026-06-24/llm_gateway_f1_f2_closure.md)
- [`verifications/2026-06-24/llm_gateway_slice_0_6_httpx.md`](verifications/2026-06-24/llm_gateway_slice_0_6_httpx.md)

### AgentLoopRunner

정본 세부 문서: [`plans/flat-loop-gate.md`](plans/flat-loop-gate.md)

확정된 구현 계약:

- Loop는 Application/Worker 소유다.
- sub-agent spawn, delegate tool, nested AgentLoopRunner 호출, 임의 code/shell tool은 지원하지 않는다.
- 한 run은 정확히 하나의 terminal decision으로 종료한다.

```text
completed
awaiting_review
blocked
budget_exhausted
invalid_tool_arguments
tool_error
provider_error
```

- Gateway의 5 provider literal은 Loop decision으로 승격하지 않고 `provider_error` trace detail로 보존한다.
- domain Gate 결과와 Loop decision은 직교한다.
- `completed`는 loop 종료 상태일 뿐 domain Gate 통과가 아니다.
- `budget_exhausted`는 성공이 아니다.
- provider 응답 content는 JSON object이며 loop 종료 채널은 top-level `self_report` field다.
- `self_report` 허용값은 정확히 `finalize` 또는 `defer`다. 누락·오타·대소문자 변형·non-string·산출물 내부 nested `self_report`는 provider output 오류다.

Budget 계약:

- 필수 차원은 `max_iterations`, `max_wall_clock_ms`, `max_total_tokens`, `max_tool_calls`, `max_repeated_calls`다.
- `max_iterations`, `max_wall_clock_ms`, `max_total_tokens`는 1 이상이다.
- tool 사용 profile의 `max_tool_calls`, `max_repeated_calls`는 1 이상이다.
- tool 없는 `writing_generate`는 tool budget 2종을 0으로 둔다.
- token은 post-accounting 차원이다. 누적 `== limit`은 완료 가능, `> limit`은 `budget_exhausted`다.
- retry는 free path가 아니며 기존 budget을 소비한다.

Tool registry 계약:

- v1 public tool literal은 6종이다.

```text
search_memory
load_memory
load_snapshot
compare_memory
validate_candidate
validate_context
```

- `analysis_compare` allowlist: `search_memory`, `load_memory`, `load_snapshot`, `compare_memory`, `validate_candidate`
- `context_search` allowlist: `search_memory`, `load_memory`, `validate_context`
- `writing_generate` allowlist: 없음
- 모델 arguments는 `project_id`, task/trace identity, deadline을 소유할 수 없다.
- raw arguments는 JSON으로 정확히 한 번 parse한다. parse 실패를 `{}`로 바꾸지 않는다.
- A2 validator 범위는 `required`, type, `additionalProperties: false`, array `items`다.
- `enum`/bounds(`minimum`/`maximum`)는 이 keyword를 선언하는 tool schema가 처음 등록될 때 검증과 양방향 회귀를 추가한다. 그전까지 명시적 deferral이다.
- valid tool call signature는 `tool name + canonical JSON arguments`다. canonical JSON은 key sort와 JSON type/value 보존을 사용한다.

검증 근거:

- [`verifications/2026-06-24/agent_loop_a1_decision_budget.md`](verifications/2026-06-24/agent_loop_a1_decision_budget.md)
- [`verifications/2026-06-25/agent_loop_a2_registry.md`](verifications/2026-06-25/agent_loop_a2_registry.md)
- [`verifications/2026-06-25/agent_loop_a3_completion_resolution.md`](verifications/2026-06-25/agent_loop_a3_completion_resolution.md)
- [`verifications/2026-06-25/self_report_parser.md`](verifications/2026-06-25/self_report_parser.md)
- [`verifications/2026-06-25/agent_loop_provider_runner.md`](verifications/2026-06-25/agent_loop_provider_runner.md)

## Gate 합성 계약

Loop Gate, Analysis Gate, Context Gate, Writing Gate는 같은 decision으로 합치지 않는다.

| Gate | 질문 | 대표 결과 |
|---|---|---|
| Loop Gate | loop run이 왜 끝났나 | terminal decision 7종 |
| Analysis Gate | 분석 후보를 어떻게 처분할까 | `create/update/add_evidence/no_change/conflict` 및 job 상태 |
| Context Gate | package를 AI에 전달해도 되나 | project/SOT/pointer/version/stale/budget 검사 |
| Writing Gate | writing candidate를 editor에 제안해도 되나 | hard constraint/POV/continuity/finding |

합성 순서:

```text
AgentLoopRunner terminal decision
→ 산출물 존재 시 domain Gate 실행
→ Gate finding과 후보 상태 저장
→ 사용자 검토 또는 후속 service action
```

Loop decision이 `completed`여도 domain Gate가 reject할 수 있다. 반대로 domain candidate가 `needs_review` 상태여도 loop는 완결된 산출을 제출했다면 `completed`일 수 있다.

## Phase 계약 인덱스

### Product Shell

정본 세부 문서: [`plans/product-shell.md`](plans/product-shell.md)

- 단일 사용자 제품 표면이다.
- 프로젝트 CRUD, 원고 작업 공간, 처리 상태, 내보내기를 제공한다.
- 보관/삭제 정책, export 형식, draft/chapter/scene 계층은 미확정이다.

### Phase 1. Core SOT

정본 세부 문서: [`plans/01-core-sot.md`](plans/01-core-sot.md)

- `projects`, `drafts`, `draft_versions`, `source_snapshots`, `source_blocks`, `source_refs` 계약을 만든다.
- snapshot은 생성 후 수정하지 않는다.
- offset 기준, normalization/hash, transaction/idempotency, 삭제 보존 정책은 미확정이다.

### Phase 2. Analysis Pipeline

정본 세부 문서: [`plans/02-analysis-pipeline.md`](plans/02-analysis-pipeline.md)

- Phase 2A는 prior memory 없이 snapshot 근거 기반 후보를 만든다.
- Phase 2B는 Phase 3~4 이후 prior memory를 검색해 `create/update/add_evidence/no_change/conflict` 후보를 만든다.
- Analysis AI는 canon을 확정하지 않고 기존 기억을 직접 덮어쓰지 않는다.
- 분석 taxonomy, confidence threshold, `confirmed` 자동 승격 여부는 미확정이다.

### Phase 3. Indexing

정본 세부 문서: [`plans/03-indexing.md`](plans/03-indexing.md)

- ChromaDB와 Elasticsearch는 MongoDB pointer/version/status를 가진 파생 인덱스다.
- index hit는 SOT 재조회 전까지 정본이 아니다.
- embedding model, ES analyzer, sync 전달 방식, 삭제 반영 방식은 미확정이다.

### Phase 4. Agentic Search

정본 세부 문서: [`plans/04-agentic-search.md`](plans/04-agentic-search.md)

- 목적에 맞는 ContextPackage 후보를 만든 뒤 Context Gate를 통과시킨다.
- `context_search` profile은 flat-loop allowlist 3종만 쓴다.
- tool success와 `validate_context` success는 Context Gate 통과가 아니다.
- Writing용 package와 Analysis 비교용 package의 공통/분리 경계는 미확정이다.

### Phase 5. Writing AI

정본 세부 문서: [`plans/05-writing-ai.md`](plans/05-writing-ai.md)

- Writing AI는 DB/검색 tool에 직접 접근하지 않는다.
- MVP `writing_generate` profile은 tool 없음이다.
- 검증된 ContextPackage와 WritingBrief로 WritingCandidate를 만든다.
- 사용자가 accept하기 전에는 draft version이나 canon이 바뀌지 않는다.
- 출력 형식(full text/patch), Gate decision literal, 첫 task type은 미확정이다.

### Phase 6. Review UI

정본 세부 문서: [`plans/06-review-ui.md`](plans/06-review-ui.md)

- 사용자가 후보의 원문 근거, 기존 기억 diff, Gate finding을 보고 approve/reject/edit/defer 한다.
- 승인 전 candidate가 canonical UI나 검색 constraint로 위장되지 않는다.
- 승인 후 MongoDB가 먼저 갱신되고 인덱스는 그 결과를 따른다.
- 승인 결과가 `confirmed`인지 `canonical`인지, merge/split UI 범위는 미확정이다.

## 현재 구현 상태

| Slice | 상태 | 근거 |
|---|---|---|
| LLM Gateway 0.1~0.6 | 구현·검증 완료 | `services/llm_gateway/`, `tests/test_llm_*`, `test_httpx_transport.py` |
| AgentLoopRunner A1 | 구현·검증 완료 | `decision.py`, `budget.py`, A1 verification |
| AgentLoopRunner A2 | 구현·검증 완료 | `registry.py`, A2 verification |
| AgentLoopRunner A3 | 구현·독립 검증 합격(보강) | `completion.py`, `resolution.py`, budget F1 방어 + retry cap, `InvalidBudgetPolicy.decision` |
| AgentLoopRunner provider composition | 구현·독립 검증 합격(보강) | `parser.py`, `runner.py`, `test_agent_loop_runner.py`; I2 forward-lock(provider usage budget before completion, retry non-free), provider runner verification |
| Product Shell/Phase 1~6 | 미구현 | 계획 문서만 존재 |

## 미확정 결정 목록

다음 항목은 구현자가 임의로 채우지 않는다.

- 본 SoT를 `Approved`로 승격할지 여부
- `confirmed`와 `canonical`의 의미 및 승격 주체
- Core SOT의 offset 기준, normalization/hash, block split 규칙
- project/draft archive/soft delete/hard delete 정책
- Analysis MVP taxonomy와 confidence threshold
- Analysis `create/update/add_evidence/no_change/conflict`의 정확한 public envelope
- Chroma embedding model, ES analyzer, sync delivery 방식
- ContextPackage schema variant(Writing용/Analysis용 공통 또는 분리)
- WritingCandidate 출력 단위(full text/patch)
- Writing Gate decision literal과 editor 처리
- budget/retry production 기본 숫자
- enum/bounds를 쓰는 첫 tool schema 등록 시 validator 확장 방식

## 변경 규칙

1. 계약 literal을 바꿀 때는 해당 테스트와 검증 기록을 함께 갱신한다.
2. spec과 구현이 충돌하면 둘 중 하나를 조용히 선택하지 않는다.
3. 미확정 항목을 구현해야 하면 사용자 결정 또는 좁은 spike로 먼저 계약을 만든다.
4. 문서-only 변경도 링크, 우선순위, status, 관련 HANDOFF를 확인한다.
5. 상세 구현 이력은 daily work log에 기록하고, 현재 actionable 상태만 `HANDOFF.md`에 남긴다.
