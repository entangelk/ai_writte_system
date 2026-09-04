# LLM Gateway와 Gemma 12B Q4 계획

상태: **이행됨 — 설계 근거로 보존**. LLM Gateway 는 구현·운영 중이며 키 폴백 taxonomy 까지 SoT v1.8.0 에 등재됐다.  
참조 구현: `/mnt/d/devel/gemma4_12b` commit `485c4e2fe78323c408fcb64d08c2cdc9ec94f9e3`

참조 구현의 기준 모델은 `google/gemma-4-12B-it-qat-q4_0-gguf`, quant tag `Q4_0`이다. RTX 3050 6GB에서 GPU/CPU 하이브리드 실행을 목표로 `llama.cpp` CUDA server, context 8192, parallel slot 1을 기본 설정으로 둔다. 이 값은 참조 설정이며 현재 프로젝트 환경의 실측 완료값은 아니다.

## 결정 제안

Gateway code는 같은 monorepo에 두고, 실행은 독립 서비스로 분리한다.

| 선택 | 판단 |
|---|---|
| Application process 안에 모델 직접 로드 | 비추천: GPU lifecycle, crash, dependency, scale이 업무 API와 결합됨 |
| 같은 repo의 독립 Gateway container | 추천: 계약/version 관리가 쉽고 로컬·원격 배치를 모두 수용 |
| 처음부터 별도 repo/본격 MSA | 보류: 단일 사용자 프로젝트에 배포·관측·호환성 비용이 큼 |

## Gateway 책임

- model/tokenizer load와 readiness
- text/chat generation
- JSON/structured output 제약 또는 grammar 적용
- generation parameter와 timeout/cancel 처리
- model/quant/context capability 보고
- token usage, finish reason, timing, request ID 반환
- 제한된 동시성, queue, overload 응답

Gateway가 하지 않는 일:

- MongoDB/ChromaDB/Elasticsearch 접근
- 프로젝트 memory 검색
- source_ref 생성 또는 검증
- prompt의 업무 의미 결정
- candidate 승인이나 memory update
- 프로젝트 도메인 tool 실행과 agent loop 상태 소유

참조 repo는 Gateway 안에서 generic tool loop까지 실행하지만, 현재 프로젝트에서는 역할을 분리한다. inference proxy/client는 Gateway에 두고, Agentic Search/Analysis의 loop와 domain tool registry는 Application/Worker가 소유한다.

## 개발 머신 독립성

- 외부 `gemma4_12b` repo는 필수 dependency가 아니다.
- 이관된 code/test는 현재 repo 안에서 독립 실행한다.
- model weight와 GPU smoke는 별도 실행 환경의 책임이다.
- 현재 작업 환경에서는 direct curl smoke가 가능하다. 실제 Python adapter smoke 가능 여부는 실행 환경별로 따로 검증한다.
- 로컬 LLM HTTP adapter는 host proxy 환경에 우발적으로 연결되지 않도록 `trust_env=false`를 기본으로 사용하며, proxy가 필요한 배포에서만 명시적으로 활성화한다.

## 내부 API 초안

가능하면 inference engine의 OpenAI-compatible API를 그대로 외부 계약으로 삼지 않고 얇은 내부 계약으로 감싼다. engine 교체 시 Application 변경을 줄이기 위해서다.

```text
GET  /health/live
GET  /health/ready
GET  /v1/capabilities
POST /v1/generate
POST /v1/generate-structured
```

요청에 필요한 최소 정보:

```text
request_id
task_type
prompt_version
messages 또는 prompt
temperature / top_p
max_output_tokens
response_schema 또는 grammar
stop
deadline_ms
```

### 현재 request preconditions

- `messages`는 하나 이상이어야 한다.
- 각 message의 `role`은 빈 문자열일 수 없다.
- `stream`은 현재 `false`만 허용한다.
- `max_tokens`는 생략하거나 bool이 아닌 1 이상의 정수여야 한다. `0`은 허용하지 않는다.
- Gateway의 `default_model` 설정은 빈 문자열일 수 없다.
- `thinking`을 생략하면 configured `default_thinking` 값을 그대로 사용하며 `true`와 `false` 모두 유효하다.
- 명시적 `chat_template_kwargs.enable_thinking`은 request/default thinking보다 우선한다.

응답에 필요한 최소 정보:

```text
request_id
model_id / model_revision / quantization
text 또는 parsed_output
finish_reason
input_tokens / output_tokens
load/queue/prompt/generation timing
schema_valid
```

### 현재 text-completion response preconditions

- HTTP 2xx 응답만 generation 성공 후보로 parsing한다.
- body는 JSON object이고 `choices`는 비어 있지 않은 list여야 한다.
- `model`, 첫 choice의 `message.content`, `finish_reason`은 문자열이어야 한다.
- `usage`와 그 안의 `prompt_tokens`, `completion_tokens`는 필수다. 어느 하나라도 누락되면 `provider_invalid_response`로 거절한다.
- `prompt_tokens`와 `completion_tokens`는 bool이 아닌 0 이상의 정수여야 하며 명시적 0은 유효하다.
- public `ProviderError.message`는 빈 문자열일 수 없다.
- 위 조건을 어긴 성공 응답은 `provider_invalid_response`로 처리한다.

실제 wire schema와 오류 literal은 Slice 0에서 계약 테스트와 함께 확정한다.

현재 구현된 provider 오류 literal:

```text
provider_unavailable
provider_timeout
provider_overloaded
provider_invalid_response
provider_request_rejected
```

transport/HTTP status mapper와 `LlamaCppProvider`는 `JsonTransport` 경계로 연결됐고, 실제 library adapter인 `HttpxJsonTransport`도 구현됐다. Mock HTTP 경계는 검증됐다. service dependency는 `httpx>=0.28,<1`이며 local endpoint 기본 정책은 `trust_env=false`다. 2026-06-24 독립 검증 환경에서 `HttpxJsonTransport`를 경유한 actual adapter live smoke까지 검증됐다. Tool-call parsing은 여전히 미구현이다.

## Gemma Q4 적용 원칙

### Prompt 전략

- 한 호출에 한 분석 목적을 둔다.
- compact context와 짧은 source quote를 우선한다.
- 중첩이 얕은 strict JSON schema를 사용한다.
- `do_not_use`, candidate/canonical, 추정 금지를 명시한다.
- source_ref ID를 모델이 새로 만들게 하지 않고 입력 span key를 선택하게 한다.
- JSON repair는 최대 횟수를 제한하고 원본 output을 trace에 보존한다.

### Generation profile 분리

| workload | 성향 |
|---|---|
| extraction/classification | 낮은 temperature, structured output, 짧은 output |
| memory comparison | 낮은 temperature, 기존/신규 근거 병렬 입력 |
| search planning | 낮은 temperature, 작은 taxonomy와 schema |
| writing | 더 높은 창의성, 긴 output, Gate 필수 |

정확한 sampling 값은 모델 benchmark로 확정하며 문서에서 미리 고정하지 않는다.

## Quantization과 engine 결정

참조 repo를 기준으로 첫 runtime은 GGUF Q4_0 + `llama.cpp` server로 좁혀졌다.

- GGUF Q4 계열이면 `llama.cpp` 호환 server가 첫 후보다.
- AWQ/GPTQ 계열이면 해당 format을 안정적으로 지원하는 GPU server가 필요하다.
- bitsandbytes 4-bit이면 Python/Transformers runtime 의존성이 커진다.

우선 `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`을 재현한다. 다운로드 권한이나 모델 호환성 문제가 있을 때만 대체 GGUF/provider를 검토한다. model weight는 host의 read-only volume으로 mount하고 repo와 image에 포함하지 않는다.

## Slice 0 benchmark matrix

### 측정 환경

- GPU/VRAM과 driver/runtime version
- CPU/RAM과 OS
- model ID/revision/quant file hash
- engine/version와 offload 설정
- context size, batch, concurrency

### 측정 항목

- cold/warm load time
- idle/peak VRAM 및 system RAM
- prompt processing 속도와 TTFT
- output tokens/sec와 전체 latency
- 요청 queue time
- 최대 안정 context
- structured output 유효율과 repair율
- timeout/cancel 후 memory 회수
- 연속 실행 시 OOM/crash 여부

현재 repo에는 live endpoint 관측을 위한 lightweight runner
`scripts/benchmark_llm_provider.py`가 있다. 이 runner는 Gateway provider
계약을 통해 `short_smoke`, `json_extraction`, `continue_scene` case의
latency/token/error summary를 JSON으로 출력한다. 실제 budget/retry
production 기본값은 이 report를 live Gemma/llama.cpp endpoint에서 생성한
뒤 별도 결정한다.

Benchmark report는 다음 top-level shape를 가진다: `metadata`(`created_at`,
`base_url`, `model`, `repeats`, `warmups`), `summary`(case별 `runs`,
`successes`, `failures`, `latency_ms_p50`, `latency_ms_p95`,
`max_total_tokens`, `avg_output_tokens_per_second`, `error_codes`), `runs`
(raw run별 `case`, `iteration`, `success`, `latency_ms`, `prompt_tokens`,
`completion_tokens`, `total_tokens`, `tokens_per_second`, `finish_reason`,
`output_chars`, `error_code`, `error_retryable`, `error_message`). Warmup
provider failure는 전체 benchmark를 중단하지 않고 `iteration=0` 실패 run으로
기록한다.

### 품질 task

- entity/event 등 최초 추출
- mood/goal 같은 해석적 추출
- 기존 memory와 no_change/update/conflict 대조
- search plan 생성
- continue_scene 생성
- Gate용 claim extraction

한 모델/profile이 모든 task에서 최적이라고 가정하지 않는다. 동일 Gateway 계약 아래 task별 profile 또는 향후 다른 provider를 허용한다.

## 운영 기본값 제안

- 초기 concurrency는 1로 시작하고 benchmark 후 올린다.
- Application/Worker는 무제한 retry하지 않는다.
- timeout, overload, schema failure를 서로 다른 오류로 반환한다.
- Gateway restart가 AnalysisJob을 잃지 않도록 job 상태는 Application/MongoDB가 소유한다.
- readiness는 process 생존이 아니라 model이 실제 요청을 받을 수 있음을 의미한다.
- real-model health smoke와 단순 liveness를 분리한다.

## 테스트

### Gateway 자체

- health/readiness 전이
- schema-valid request/response
- invalid parameter와 oversized context
- timeout/cancel/overload
- structured output 성공/실패
- model metadata와 timing 반환

### Application 계약

- fake provider success, queued failure, exhaustion — 구현 완료
- provider error literal/envelope와 내부 cause 비노출 — 구현 완료
- transport failure/HTTP status의 stable error mapping — 구현 완료
- fake-transport 기반 llama.cpp text provider client — 구현 완료
- httpx JSON adapter와 mock HTTP contract — 구현 완료, live adapter smoke 검증 완료
- malformed JSON과 truncated output
- provider timeout/unavailable/overload
- request ID와 prompt/model revision trace
- retry가 중복 candidate/upsert를 만들지 않음

### 실모델 smoke

- 모델 로드 후 짧은 generation
- strict JSON fixture
- 한국어 원문 extraction fixture
- 한 번의 writing fixture
- 연속 N회 호출과 memory 안정성

N과 합격 기준은 실제 hardware baseline을 본 뒤 고정한다.

짧은 direct curl smoke와 기본 adapter smoke는 완료됐지만, 전체 model evaluation은 GPU/Python 실행 환경의 배포 전 gate다.

## 착수 전 필요한 정보

- [x] 참조 model repository: `google/gemma-4-12B-it-qat-q4_0-gguf`
- [x] 참조 quantization: GGUF `Q4_0`
- [ ] 실제 실행 장비가 참조 환경과 같은 RTX 3050 6GB인지 확인
- [ ] 원하는 최대 context와 동시 요청 수
- [ ] Linux native/WSL/Docker 중 실행 환경
- [x] 첫 server 후보: `ghcr.io/ggml-org/llama.cpp:server-cuda`

## 관련 자료

- [`gemma4-reuse.md`](gemma4-reuse.md)
- [`implementation-plan.md`](implementation-plan.md)
- [`00-foundations.md`](00-foundations.md)
- [`../contracts.md`](../contracts.md) — 현재 `Gemma / llama.cpp compatible provider` 아이디에이션
- [`../writing_agent_prompt.md`](../writing_agent_prompt.md) — local Gemma prompt 제약 아이디에이션
