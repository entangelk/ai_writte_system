# 구현 계획

상태: `Draft`  
목표: 현재 계획을 실제 개발 가능한 vertical slice와 검증 gate로 변환한다.

## 권장 아키텍처 결론

처음부터 여러 저장소와 독립 배포 조직을 전제로 한 MSA는 사용하지 않는다. 하나의 monorepo 안에서 다음 두 경계를 조합한다.

- Application: Product Shell, API, domain service를 우선 modular monolith로 구성
- LLM Gateway: GPU/모델 lifecycle 때문에 별도 프로세스·컨테이너로 구성
- Background Worker: 분석·색인 job이 웹 요청을 막지 않도록 별도 실행 가능하게 구성하되 Application과 코드/계약을 공유
- Data services: MongoDB, ChromaDB, Elasticsearch는 개발 환경에서 Compose로 조합

```text
Browser / Local UI
        │
        ▼
Application API ───── MongoDB
        │                 │
        ├── Job Queue/Worker ── ChromaDB / Elasticsearch
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

완료 증거:

- GPU 없이 contract test 통과
- 실제 모델 health → generation smoke 통과
- model load time, peak VRAM/RAM, context length, TTFT, tokens/sec, 전체 latency 기록
- 동시성 1에서 OOM 없이 반복 호출
- 잘못된 JSON과 timeout을 Application이 정상적인 오류로 처리
- reference Gateway의 기존 8개 계약 테스트를 이관된 경계에서 재현

### Slice 1. Project Shell + Core SOT

목표: 계정 없이 프로젝트를 만들고 원고를 저장·다시 열고 내보내는 첫 vertical slice를 만든다.

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
- WritingBrief/prompt assembly
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

- [ ] monorepo + 독립 LLM Gateway 경계 승인
- [ ] backend/frontend framework
- [ ] job queue 방식과 worker process 경계
- [x] 첫 model artifact: `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`
- [ ] Gemma model terms/download 권한과 참조 source code provenance
- [ ] GPU 모델/VRAM, CPU RAM, 운영 OS
- [ ] 첫 inference engine과 fallback provider
- [ ] Slice 2A의 최소 분석 taxonomy
- [ ] 첫 export 형식

## 관련 계획

- [`gemma4-reuse.md`](gemma4-reuse.md)
- [`llm-gateway.md`](llm-gateway.md)
- [`product-shell.md`](product-shell.md)
- [`01-core-sot.md`](01-core-sot.md)
- [`analysis-memory-taxonomy.md`](analysis-memory-taxonomy.md)
- [`02-analysis-pipeline.md`](02-analysis-pipeline.md)
