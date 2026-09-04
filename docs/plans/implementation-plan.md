# 구현 계획

상태: **이행됨 — 설계 근거로 보존**. 여기 적은 배포 경계·구현 순서는 Phase 1~9 로 이행됐다. 현재 상태는 [`../system-contract-sot.md`](../system-contract-sot.md) 변경이력과 [`../../HANDOFF.md`](../../HANDOFF.md) 를 본다.  
목표: 현재 계획을 실제 개발 가능한 vertical slice와 검증 gate로 변환한다.

## 승인된 아키텍처 결론

처음부터 여러 저장소와 독립 배포 조직을 전제로 한 MSA는 사용하지 않는다. 하나의 monorepo 안에서 다음 두 경계를 조합한다.

- Application: FastAPI 기반 Product Shell/API/domain service를 우선 modular monolith로 구성
- LLM Gateway: GPU/모델 lifecycle 때문에 별도 프로세스·컨테이너로 구성
- Background Worker: 분석·색인 job이 웹 요청을 막지 않도록 별도 실행 가능하게 구성하되 Application과 코드/계약을 공유하고 느슨한 연결을 유지
- Data services: MongoDB, ChromaDB, Elasticsearch는 개발 환경에서 Compose로 조합

2026-06-26 사용자 결정으로 monorepo + 독립 LLM Gateway 경계, FastAPI backend, 느슨하게 분리 가능한 Worker 경계를 승인했다. frontend framework 최종 선택은 보류하며, 단일 local service UI로 충분하지 않을 때 React 또는 Vue를 기본 후보로 검토한다. 초기 개인 로컬 runtime은 외부 queue 제품을 전제하지 않고 단순한 in-process/background boundary로 시작한다.

```text
Browser / Local UI
        │
        ▼
Application API ───── MongoDB
        │                 │
        ├── Background/Worker ── ChromaDB / Elasticsearch
        │          │
        │          └────────── LLM Gateway ── model volume
        │
        └───────────────────── LLM Gateway
```

이 구조는 프로세스 수준으로는 서비스가 나뉘지만, 운영 조직과 저장소까지 쪼개는 본격 MSA는 아니다. LLM 장비를 분리할 필요가 생기면 `LLM_GATEWAY_URL`만 원격 endpoint로 바꿀 수 있어야 한다.

## 배포 경계 원칙

- Gateway 구현과 계약은 같은 repo에서 version을 맞춘다.
- 모델 weight, tokenizer cache, 생성 결과 cache는 Git에 넣지 않는다.
- Application은 모델 파일 경로나 CUDA 설정을 알지 않는다.
- Gateway는 MongoDB나 프로젝트 memory에 접근하지 않는다.
- prompt 조립과 업무 규칙은 Application/Worker에 둔다.
- model loading, inference, JSON 제약, token/latency 측정은 Gateway에 둔다.
- 개발/테스트에서는 fake provider로 GPU 없이 계약 테스트가 가능해야 한다.

## 기존 `gemma4_12b` 재사용 기준

참조 기준은 `/mnt/d/devel/gemma4_12b`의 commit `485c4e2fe78323c408fcb64d08c2cdc9ec94f9e3`이다. 세부 판정과 파일별 이관 순서는 [`gemma4-reuse.md`](gemma4-reuse.md)를 따른다.

- Compose의 `llama-server`와 GGUF Q4_0 하이브리드 설정은 Slice 0의 시작점으로 사용한다.
- Gateway schema/client와 thinking control 회귀 테스트를 선택적으로 이관한다.
- 평면형 `AgentEngine` loop 골격은 Application/Worker orchestration으로 옮긴다.
- demo tool과 Gateway 내부 ToolRegistry는 프로젝트 도메인에 그대로 가져오지 않는다.
- sub-agent spawn/delegation은 도입하지 않는다.
- reference code의 loop 종료/오류를 업무 Gate decision과 혼동하지 않도록 보강한다.
- 참조 repo가 없는 머신에서도 build/test/run이 가능해야 하며 외부 경로 의존을 금지한다.

## 구현 진행 상태

### 완료: Slice 0.1 — portable thinking payload contract

- 현재 repo 내부에 self-contained `ChatMessage`, `ChatCompletionRequest`, llama.cpp payload builder 추가
- `thinking=true/false/default/explicit override` 계약 고정
- legacy `<|think|>` message 주입 금지
- 미지원 `stream=true` 조기 거절
- 외부 repo, FastAPI, Docker, GPU 없이 실행되는 7개 unit contract test 추가
- request precondition(messages, role, non-streaming, positive max_tokens, non-empty default model)을 plan과 양방향 회귀로 고정
- thinking 생략 시 default false/true 양쪽을 회귀로 고정

아직 provider HTTP client, fake provider, FastAPI endpoint, Docker/실모델 구성은 구현하지 않았다.

### 완료: Slice 0.2 — provider protocol과 deterministic fake

- Application이 구체적인 llama.cpp client 대신 의존할 async `LLMProvider` protocol 추가
- model/content/finish reason/token usage의 최소 generation result 추가
- 결과와 오류를 FIFO로 재현하고 요청을 기록하는 fake provider 추가
- 준비된 outcome이 없으면 응답을 조작하지 않고 명시적으로 실패
- 정상 결과, provider timeout, fake exhaustion을 포함한 4개 unit contract test 추가

아직 실제 HTTP provider와 오류 literal/envelope는 구현하지 않았다.

### 완료: Slice 0.3 — provider error literal과 envelope

- `provider_unavailable`, `provider_timeout`, `provider_overloaded`, `provider_invalid_response` 고정
- public message, retryable, 선택 provider 이름을 가진 안정된 error envelope 추가
- retryable/non-retryable을 오류 종류로 추측하지 않고 provider adapter가 명시
- 내부 transport exception/cause가 envelope에 직렬화되지 않도록 분리
- fake provider에서도 같은 `ProviderError`를 그대로 재현
- literal, 양방향 retryable, 내부 정보 비노출을 포함한 5개 unit contract test 추가

아직 HTTP status/transport exception 매핑과 실제 HTTP provider는 구현하지 않았다.

### 완료: Slice 0.4 — transport/HTTP status error mapping

- transport timeout/connection/invalid-response를 stable `ProviderError`로 변환
- HTTP 408/504는 timeout, 429는 overloaded, 5xx는 unavailable로 변환
- 그 밖의 4xx를 의미에 맞게 표현하기 위해 `provider_request_rejected` literal 추가
- 2xx/3xx를 오류로 잘못 분류하지 않고 mapper 사용 오류로 거절
- upstream response body나 raw exception을 mapper 입력/공개 envelope에 포함하지 않음
- retryable/non-retryable 양방향과 상태 경계를 포함한 7개 unit contract test 추가

아직 특정 HTTP library와 실제 endpoint를 호출하는 provider client는 구현하지 않았다.

### 완료: Slice 0.5 — fake-transport 기반 llama.cpp provider client

- async `JsonTransport` protocol, JSON response, FIFO fake transport 추가
- fake transport outcome 소진 시 응답을 만들지 않고 명시적으로 실패
- `LlamaCppProvider`가 `/v1/chat/completions` payload를 전송하고 text completion을 parsing
- model/content/finish reason/prompt·completion token usage를 `GenerationResult`로 변환
- transport failure와 HTTP status mapper를 실제 provider 흐름에 연결
- malformed object, empty choices, `content=None`을 성공으로 위장하지 않고 invalid response 처리
- upstream error body를 public envelope에 포함하지 않음
- live server 없이 정상/timeout/429/redirect/malformed/optional usage를 포함한 7개 contract test 추가
- text response의 필수 문자열과 token count 타입/범위를 plan과 malformed cases로 고정

아직 실제 HTTP library adapter와 tool-call response parsing은 구현하지 않았다.

### 완료: 검증 조건 F1/F2 보강과 direct live smoke

- F1: thinking 생략 + `default_thinking=true` 대칭 회귀 추가
- F2: 기존 code-enforced request/response precondition을 `llm-gateway.md` 계약으로 승격하고 회귀 추가
- direct llama.cpp `/health`, `/v1/models`, non-thinking chat completion 확인
- live smoke는 curl로 직접 server를 확인한 것이며 아직 실제 HTTP adapter 검증은 아님

### 구현 완료·live 검증 완료: Slice 0.6 — httpx JSON adapter

- LLM Gateway service dependency로 `httpx>=0.28,<1` 선언
- `HttpxJsonTransport`가 async POST, JSON decode, close/context manager 제공
- httpx timeout/connection을 기존 TransportFailure로 변환
- 2xx non-JSON은 invalid response, non-JSON 4xx/5xx는 body를 버리고 status 보존
- host proxy 환경을 우발적으로 사용하지 않도록 `trust_env=false` 기본값
- `httpx.MockTransport` 기반 success/timeout/connection/non-JSON과 proxy opt-in/out 5개 회귀 추가
- URL을 인자로 받는 실제 provider smoke module 추가

구현 환경에서는 Python socket이 응답 없이 대기해 live adapter smoke를 못 했으나, 2026-06-24 독립 검증 환경에서 `HttpxJsonTransport`를 경유한 actual adapter live smoke를 완료했다(응답 content `연결 확인 완료`, `finish_reason=stop`, usage 23/5/28). close-lifecycle 회귀까지 포함한 Mock contract 6개 회귀도 통과했다. 기록: `docs/verifications/2026-06-24/llm_gateway_slice_0_6_httpx.md`.

### 진행 중: Slice 4 계약 회귀 — AgentLoopRunner A1/A2/A3 + provider composition

[`flat-loop-gate.md`](flat-loop-gate.md)의 확정된 계약을 실제 검색 인프라 없이 결정적 회귀로 잠그는 구현 sub-slice다. Application 소유 컴포넌트이므로 `services/application/app/agent_loop/` 패키지에서 진행한다.

- `LoopDecision` 종료 decision enum 7종을 계약 literal 그대로 고정(StrEnum, trace 비교 가능)
- `BudgetPolicy` 5차원 검증: iteration/wall-clock/token 하한 1, tool-call/repeated-call 비음수, bool 거부, tool 사용 여부와 tool 차원의 모순 거부
- `BudgetTracker` 계측: count 차원 N번째 허용·N+1 차단, wall-clock deadline(clock 주입으로 결정적), token post-accounting(`== limit` 허용·`> limit` 초과), repeated-call signature 분리(다른 valid arguments 비반복)
- `ToolRegistry` A2: task profile별 allowlist, schema-less/unknown 허용/context scope argument 등록 거부, strict JSON argument validation(`required`·type·`additionalProperties`·array `items`; `enum`/bounds는 keyword 사용 tool 등록 시점까지 deferred — flat-loop-gate §33 참조), canonical tool-call signature를 고정
- 독립 검증 후 보강: 중첩 object schema와 array `items`를 등록 시점에 재귀 검증하고, runtime schema guard의 `assert` 의존을 명시 검사로 교체
- `judge_completion` A3(completion.py): 종료채널 self-report(`FINALIZE`/`DEFER`)와 구조 조건(artifact 존재)의 하이브리드 판정으로 `completed`/`awaiting_review`를 가른다. 산출물 데이터 채널의 불확실성(needs_review·confidence·conflict)은 `artifact_present`를 유지하며 종료채널 `FINALIZE`면 `completed`(승격 금지).
- `parse_self_report_payload` parser slice(parser.py): provider 응답 content를 JSON object로 파싱하고 top-level `self_report` field의 정확한 `finalize`/`defer` literal만 종료 채널로 인정한다. 누락·malformed JSON·non-object·non-string·case variant·artifact nested `self_report`는 `provider_error`로 분류한다.
- `resolve_retry`/`next_step_budget_decision` A3(resolution.py): retry 우선순위(non-retryable 즉시 종료 → cap 소진 → cap 남음+budget 허용 retry → cap 남음+budget 차단 `budget_exhausted`+원래 literal trace 보존)와 budget 5차원→`budget_exhausted` 매핑. terminal-decision 우선순위(error > blocked/invalid_tool_arguments > budget_exhausted > completion)는 순차 합성
- `BudgetTracker.record_tokens` F1 방어(budget.py): 음수/None/bool/비-int token count를 0으로 보정하지 않고 `InvalidProviderUsage`(decision=`provider_error`)로 거부. 명시적 0은 유효
- A3 독립 검증(합격) 후 보강: `BudgetPolicy`에 `provider_retry_cap`/`tool_retry_cap`(0 이상, bool 거부)을 추가해 계약 §retry의 필수 policy 값을 실현(I1, 사용자 결정 Option A)하고, `InvalidBudgetPolicy.decision=blocked`로 budget/registry 예외→종료 decision uniform 매핑을 완성(I3). retry cap 검증 변이 증명. runner 합성 순서(I2)는 runner slice forward-lock
- `AgentLoopRunner` provider composition slice(runner.py): provider 호출 전 budget check → iteration 기록 → provider call/retry → usage 기록 → post-accounting budget check → `parse_self_report_payload` → `judge_completion` 순서를 실제 코드로 연결했다. I2 forward-lock으로 token overrun이 `completed`로 위장되지 않음과 provider retry가 iteration budget을 소비함을 양방향 회귀로 잠갔다. trace는 provider call/error/retry, budget stop, self_report, completion event를 보존한다.
- GPU/인프라 없이 agent_loop focused 93개 양방향 회귀 통과(decision 4 + budget 29 + registry 20 + completion 6 + parser 9 + resolution 18 + runner 7). 전체 discovery 137개 통과
- agent_loop 계약층은 여기서 멈춘다. runner의 domain tool-call branch는 Gateway tool-call response parsing, model tool-call wire format, Phase payload/tool handler가 모두 확정된 뒤 구현한다. task별 `artifact_present` 구조 평가는 Slice 2A/4/5 payload schema가 들어올 때 profile별로 교체한다. retry cap 구조는 `BudgetPolicy`에 폐쇄됐고 숫자 기본값은 2026-06-30 Gemma Q4 benchmark report(`docs/benchmarks/2026-06-30/gemma_q4_llama_cpp_repeats3_warmup1.json`)로 확정됐다.

## 제안 저장소 구조

실제 framework 선택 전의 논리 구조다. 디렉터리 이름은 stack 확정 시 조정할 수 있다.

```text
apps/
  web/                  # 프로젝트/원고/editor/review UI
services/
  application/          # API와 domain orchestration
  worker/               # analysis/index/background jobs
  llm-gateway/          # model serving adapter
packages/
  contracts/            # API, event, schema 계약
  evaluation/           # LLM fixtures와 scoring
infra/
  compose/              # local services와 실행 profiles
tests/
  contract/
  integration/
  e2e/
```

모듈이 작을 때 `application`과 `worker`는 같은 package를 공유하고 entrypoint만 나누는 편이 단순하다.

## 구현 순서

### Slice 0. Foundation Spike

목표: 기술 선택을 추측으로 굳히기 전에 실행 가능한 최소 골격과 성능 기준선을 만든다.

- Application/Gateway의 health check와 request ID 전파
- fake LLM provider 기반 generate/structured-generate 계약
- Gemma 12B Q4 모델 1회 실서빙
- 단일 prompt, JSON schema prompt, 긴 context prompt benchmark
- Compose local/real-model profile 구분
- 공통 configuration과 secret/volume 규칙
- `gemma4_12b` 선택 이관: Compose, schema/client, thinking contract tests
- reference commit과 이관 파일 provenance 기록
- 이 작업 머신에서는 real-model smoke를 실행하지 않고 GPU 실행 머신으로 검증을 이관

완료 증거:

- GPU 없이 contract test 통과
- 실제 모델 health → generation smoke 통과
- model load time, peak VRAM/RAM, context length, TTFT, tokens/sec, 전체 latency 기록
- 동시성 1에서 OOM 없이 반복 호출
- 잘못된 JSON과 timeout을 Application이 정상적인 오류로 처리
- reference Gateway의 기존 8개 계약 테스트를 이관된 경계에서 재현

### Slice 1. Project Shell + Core SOT

목표: 계정 없이 프로젝트를 만들고 원고를 저장·다시 열고 내보내는 첫 vertical slice를 만든다.

진행 상태:

- 최소 Application core skeleton 구현: `core_sot` domain models, deterministic splitter/hash/source_ref, infrastructure-free repository/service
- 최소 FastAPI shell 구현: health, project 생성, draft 생성, draft version save
- 자체 회귀 11개 추가: idempotent save, immutable snapshot/hash/block, source_ref quote/hash, bool offset rejection, project_id isolation, archive preservation, FastAPI minimal flow
- 아직 MongoDB adapter, transaction-backed repository, Docker compose, export, editor shell은 구현하지 않았다.

- 프로젝트/draft CRUD
- editor shell
- immutable draft version/snapshot/block/source_ref
- plain text 또는 Markdown export
- 저장 API와 idempotency

검증:

- CRUD와 프로젝트 격리 integration test
- snapshot/hash/block/ref deterministic test
- 저장 전후 version 불변성 test
- 선택한 version과 export 결과 일치 e2e test

### Slice 2A. Initial Analysis

목표: prior memory가 없는 원고에서 최소 분석 후보를 생성한다.

- 분석 taxonomy의 첫 대상 확정
- AnalysisJob/task/runner
- Gemma task별 compact prompt와 strict JSON
- source anchor/schema Gate
- candidate/review 저장

검증:

- 유형별 positive/negative fixture
- 근거 없는 추론, 잘못된 quote/span 차단
- 정상 근거 후보를 과도하게 차단하지 않는 반대 방향 사례
- retry/idempotency와 partial failure test
- 실모델 JSON 유효율과 repair 횟수 기록

### Slice 3. Derived Indexing

목표: MongoDB 기억을 ChromaDB/Elasticsearch에서 찾되 정본과 혼동하지 않게 한다.

- index contract/adapters
- sync log/retry/rebuild
- stale version 검출

검증:

- upsert/delete/rebuild integration test
- stale/cross-project hit 차단
- MongoDB만으로 완전 재생성

### Slice 4. Agentic Search

목표: 검색 후보를 정본으로 재조회해 추적 가능한 ContextPackage를 만든다.

- intent/plan/router
- hybrid retrieval와 candidate merge
- SOT resolver와 Context Gate
- Writing/Analysis 목적별 package
- bounded flat agent loop와 domain tool allowlist
- 반복 호출, 잘못된 인자, iteration/time/token budget Loop Gate

검증:

- exact/semantic/direct query routing
- ES/Chroma 단일 장애 degraded mode
- MongoDB 장애 시 성공 위장 금지
- 모든 context item의 source/version trace
- sub-agent 없이 단일 loop가 명시적 decision으로 종료

### Slice 2B. Update-aware Analysis

목표: 새 원고와 기존 기억을 RAG로 대조해 안전한 변경 작업 후보를 만든다.

- prior-memory comparison package
- create/update/add_evidence/no_change/conflict 판정
- versioned upsert와 review
- 영향받은 index invalidation

검증:

- 실제 신규 항목은 create
- 동일 항목은 중복 create가 아닌 no_change/add_evidence
- 변경은 과거 version을 보존한 update
- canon 충돌은 overwrite가 아닌 conflict/review
- 의미적으로 비슷하지만 다른 대상은 잘못 merge하지 않음

### Slice 5. Writing Loop

목표: ContextPackage 기반 이어쓰기 후보를 만들고 사용자가 채택하면 저장 루프로 되돌린다.

- continue_scene
- ProjectBrief style/prompt assembly
- Writing Gate
- editor candidate/accept

검증:

- context 밖 사실과 do_not_use/POV 위반 차단
- 정상적인 창작적 추가를 과도하게 차단하지 않음
- accept 전 SOT 불변, accept 후 새 version 생성

### Slice 6. Review and Operations

목표: 후보·충돌·상태를 사용자가 운영할 수 있게 한다.

- review inbox와 source/diff
- approve/reject/edit/defer
- analysis/index job 상태와 retry
- project memory cards와 export 보강

검증:

- 상태 전이와 과거 version 보존
- review action idempotency
- project scope e2e
- 장애 후 재시작/복구 smoke

## 테스트 계층

| 계층 | LLM | 목적 |
|---|---|---|
| Unit | 없음 | domain rule, splitter, state transition |
| Contract | fake provider | Application↔Gateway schema/error/timeout |
| Integration | fake 기본, real 선택 | Mongo/Chroma/ES/job orchestration |
| Model evaluation | 실제 Gemma Q4 | JSON 준수, extraction/comparison/writing 품질 |
| E2E | fake 기본, real smoke | 사용자 vertical slice와 배포 profile |

실모델 테스트는 매 unit test에 섞지 않는다. 빠르고 결정적인 fake suite를 기본 gate로 두고, GPU가 있는 환경에서 별도 model evaluation/smoke를 실행한다.

## LLM 품질 fixture 최소 집합

- 원문에 명시된 인물/사건을 정확히 추출
- 암시만 있는 내용을 확정 사실로 만들지 않음
- source span/ref를 모델이 임의 생성하지 않음
- 같은 기억 재등장에서 `no_change`/`add_evidence`
- 실제 상태 변화에서 `update`
- canon 모순에서 `conflict`
- 비슷한 이름의 다른 인물을 merge하지 않음
- Writing에서 candidate/canonical과 `do_not_use` 구분
- 정상 JSON, 깨진 JSON, truncated output, timeout

각 회귀는 under-strict와 over-strict 사례를 함께 둔다.

## 착수 전 결정사항

- [x] monorepo + 독립 LLM Gateway 경계 승인
- [x] backend framework: FastAPI
- [x] frontend framework policy: 최종 선택 보류, standalone frontend 필요 시 React/Vue 기본 후보
- [x] worker process 경계: Application 코드/계약 공유, 느슨한 연결, 분리 가능한 entrypoint
- [x] 초기 job queue 방식: 개인 local runtime에서는 외부 queue 제품 없이 단순 in-process/background boundary
- [ ] Gateway/model tool-call response wire format
- [x] 첫 model artifact: `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`
- [ ] Gemma model terms/download 권한과 참조 source code provenance
- [ ] GPU 모델/VRAM, CPU RAM, 운영 OS
- [ ] 첫 inference engine과 fallback provider
- [ ] Slice 2A의 최소 분석 taxonomy
- [x] 첫 export 형식: plain text + Markdown(SoT v1.6.14)

Slice 1 Core SOT 착수 전 결정은 `01-core-sot.md`에서 text/reference와 persistence/retention 계약까지 승인 완료됐다. Gateway/model tool-call wire, model terms/hardware/provider, Slice 2A taxonomy, export 형식은 후속 slice 결정이다.

## 관련 계획

- [`gemma4-reuse.md`](gemma4-reuse.md)
- [`llm-gateway.md`](llm-gateway.md)
- [`product-shell.md`](product-shell.md)
- [`01-core-sot.md`](01-core-sot.md)
- [`analysis-memory-taxonomy.md`](analysis-memory-taxonomy.md)
- [`02-analysis-pipeline.md`](02-analysis-pipeline.md)
