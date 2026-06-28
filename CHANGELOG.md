# CHANGELOG

| Date | Change | Detail |
|---|---|---|
| 2026-06-28 | Application + MongoDB(replica set) Docker 런타임 추가 | [work log](docs/daily_logs/2026-06-28/work_log.md) |
| 2026-06-28 | SoT v1.4: non-transaction fallback single-writer 제약 명시(R2) | [work log](docs/daily_logs/2026-06-28/work_log.md) |
| 2026-06-28 | Core SOT MongoDB adapter + transaction-backed repository 추가 | [work log](docs/daily_logs/2026-06-28/work_log.md) |
| 2026-06-26 | Core SOT 검증 보강(C1~C3) | [work log](docs/daily_logs/2026-06-26/work_log.md) |
| 2026-06-26 | Core SOT 최소 구현 골격 추가 | [work log](docs/daily_logs/2026-06-26/work_log.md) |
| 2026-06-26 | Core SOT persistence/retention 계약 승인 | [work log](docs/daily_logs/2026-06-26/work_log.md) |
| 2026-06-26 | Core SOT text/reference 계약 승인 | [work log](docs/daily_logs/2026-06-26/work_log.md) |
| 2026-06-26 | Slice 1 실행 경계 승인 | [work log](docs/daily_logs/2026-06-26/work_log.md) |
| 2026-06-26 | System Contract SoT v1.0 승인 | [work log](docs/daily_logs/2026-06-26/work_log.md) |
| 2026-06-25 | AgentLoopRunner provider composition slice 구현 | [work log](docs/daily_logs/2026-06-25/work_log.md) |
| 2026-06-25 | AgentLoopRunner A3 검증 후 보강(I1/I3) | [work log](docs/daily_logs/2026-06-25/work_log.md) |
| 2026-06-25 | AgentLoopRunner A3 decision 합성 회귀 구현 | [work log](docs/daily_logs/2026-06-25/work_log.md) |
| 2026-06-25 | AgentLoopRunner A2 registry 계약 회귀 구현 | [work log](docs/daily_logs/2026-06-25/work_log.md) |
| 2026-06-24 | 개발 계획 문서 구조 도입 | [work log](docs/daily_logs/2026-06-24/work_log.md) |

## 2026-06-28

### Added

- Application + MongoDB Docker 런타임을 추가했다. `services/application/Dockerfile`은 빌드 캐시 보존을 위해 `requirements.txt`를 먼저 설치하고 소스를 뒤에 복사한다(Active Decision 준수). `docker-compose.yml`은 Slice 1 runtime으로 MongoDB 단일 노드 replica set(transaction 기본 계약을 위해 필수)과 application을 정의하며, mongo healthcheck가 `rs.initiate`를 idempotent하게 수행하고 member host를 `mongo:27017`로 두어 compose 네트워크 내 replica-set discovery가 성공한다. `.dockerignore`로 build context를 최소화했다. `docker compose up` 후 transaction 경로로 API save/replay end-to-end를 검증했다(version 1, idempotent replay, `draft_versions`=1). application requirements에 `uvicorn[standard]`을 추가했다. gateway 서비스는 외부 llama.cpp endpoint 의존이라 아직 compose에 미편입.
- Core SOT를 실제 MongoDB 저장소에 연결했다. `services/application/app/core_sot/`에 method 기반 `CoreSotRepository` Protocol(`repository.py`)과 pymongo(sync) 기반 `MongoCoreSotRepository`(`mongo_repository.py`)를 추가했다. 승인된 persistence/retention 계약(v1.3)을 구현으로 충족한다: `draft_versions`의 unique index `(project_id, draft_id, idempotency_key)`로 idempotency 경계를 강제하고, transaction 경로(기본, Docker/replica-set)는 save write set을 원자적으로 commit하며, non-transaction fallback(local/test)은 retry guard·orphan cleanup·ordered write를 갖춘다. `CoreSotService`는 dict 직접접근 대신 Protocol method만 사용하도록 리팩터됐고 기존 in-memory 골격과 14개 단위 테스트는 그대로 유지된다. `tests/test_core_sot_mongo.py`에 skip-aware live 통합 테스트(fallback+transaction 17개)를 추가했고 단일 노드 replica set에서 전부 통과했다.

사용자는 transaction을 실제로 검증해야 한다는 이유로 mongomock 대신 real pymongo + live Mongo 통합 테스트(미가용 시 skip)를 선택했고, 로컬 단일 사용자 MVP 단순성을 위해 sync 드라이버(pymongo)를 선택했다. 이로써 통합 테스트 층은 인프라를 요구하지만, 기본 단위 스위트는 skip-aware로 여전히 인프라 없이 실행된다.

### Changed

- 독립 재검증(`docs/verifications/2026-06-28/mongo_adapter_recheck.md`, 조건부 합격) 대응으로 SoT를 v1.4로 갱신하고 R1~R3를 보강했다. R1(load-bearing): `tests/test_core_sot_mongo.py`의 pymongo/adapter import를 try/except로 감싸 pymongo 미설치 시에도 `unittest discover`가 깨지지 않고 skip되도록 복원했다. R2(사용자 결정 option b): non-transaction fallback을 single-writer 전용으로 SoT §112 / plan §01 / adapter docstring에 명시했다(동시성 안전은 transaction 기본 경로 담당). R3: `source_refs` 보존(§113) literal은 SourceRef persistence slice 추적 포인트로 남겼다.

R2는 사용자 결정이다. fallback 동시성 correctness bug에 대해, fallback이 spec상 "local/test 제한 경로"이고 production이 transaction path(동시성 안전)를 쓰므로, 제한된 경로에 동시성 방어 복잡도를 더하는 대신 single-writer 제약을 계약에 명시해 닫는 방향을 선택했다.

## 2026-06-26

### Changed

- Core SOT 최소 구현 골격을 추가했다. `services/application/app/core_sot/`에 immutable dataclass models, raw UTF-8 SHA-256 hash, deterministic source block splitter, source_ref 생성, in-memory repository/service를 추가했고, `services/application/app/main.py`에 FastAPI shell(health/project/draft/version save)을 추가했다. focused 11개와 전체 148개 회귀가 통과했다. MongoDB adapter/transaction-backed repository/export/editor shell은 후속이다.
- Core SOT minimal skeleton 독립 검증의 조건부 합격 항목 C1~C3를 보강했다. `***` scene marker, `##` heading, `archive_project` 경로 회귀를 추가하고, `content_hash`를 known SHA-256 UTF-8 vector로 독립 고정했다. within-block `source_ref` 제약은 SoT와 Phase 1 계약에 명시했다.
- Slice 1 실행 경계를 승인하고 SoT를 v1.1로 갱신했다. monorepo + 독립 LLM Gateway, FastAPI backend, 느슨하게 분리 가능한 Worker 경계를 확정했다. frontend framework 최종 선택은 보류하며, standalone frontend가 필요할 때 React 또는 Vue를 기본 후보로 검토한다. 초기 개인 로컬 runtime은 외부 queue 제품 없이 단순 in-process/background boundary로 시작한다.
- Core SOT text/reference 계약을 승인하고 SoT를 v1.2로 갱신했다. raw snapshot을 MongoDB SOT로 두고, offset은 raw Unicode code point, `content_hash`는 raw UTF-8 SHA-256으로 정했다. MVP `source_blocks`는 Markdown heading, 단독 `---`/`***` scene marker, 빈 줄 paragraph 기반 deterministic split만 사용한다. adaptive/semantic/length-based chunking은 Phase 3 이후 파생 index 전략 후보로 분리했다.
- Core SOT persistence/retention 계약을 승인하고 SoT를 v1.3으로 갱신했다. MongoDB transaction을 기본으로 하되 non-transaction fallback은 local/test 제한 경로로 두고, MVP는 명시적 version save만 지원한다. draft save는 `idempotency_key` 필수이며 project/draft는 archive, snapshot/version/source_ref는 보존한다.
- `docs/system-contract-sot.md`를 `Approved` v1.0 정본 계약 인덱스로 승격했다. 승인 범위는 문서 우선순위와 이미 확정·검증된 계약의 인덱스 역할이며, 미확정 결정 목록은 계속 추측 구현 금지로 남긴다.
- 향후 사용자 결정으로 정본 계약이 바뀔 수 있으므로 SoT 내부에 계약 버전 관리 규칙과 계약 변경 이력을 추가했다.

사용자는 FastAPI 경험을 이유로 backend framework를 FastAPI로 승인했다. frontend framework는 단일 local service UI 가능성을 열어두기 위해 보류하고, 필요 시 React/Vue 중 선택하는 방향으로 남겼다. Worker/queue는 개인 로컬 시스템 특성상 과도한 외부 queue 제품을 피하고 느슨한 연결과 후속 분리 가능성을 우선했다.

사용자는 SOT는 MongoDB, 검색·인덱스는 vector/index DB라는 경계를 다시 확인했고, 업데이트/upsert와 version 확장성을 고려해 SOT에 version 추적성을 유지하기로 했다. 해시는 로컬이어도 두는 방향을 채택했다. adaptive chunking과 1화 단위 길이 기반 chunking은 MVP SOT block 규칙에 넣지 않고, 후속 파생 index 전략 후보로 남겼다.

사용자는 Docker 기반 사용을 전제로 MongoDB transaction 문제가 일반 runtime에서는 크지 않을 것이라고 판단했지만, fallback은 있으면 좋다고 승인했다. autosave는 AI 생성 결과가 항상 맞지 않는다는 이유로 초기 구현에서 제외하고, 실제 필요성이 확인될 때만 별도 기능으로 검토하기로 했다. 분석 후보의 부분 승인/부분 retry는 Slice 1 저장 계약이 아니라 Phase 2/6 review action idempotency에서 다룬다.

사용자는 SoT가 앞으로 사용자 결정에 의해 업데이트될 수 있음을 명시했고, 그 변경은 문서 내부에서 버전 관리되기를 원했다. 이에 v1.0 승인 이력과 future-change rule을 SoT에 직접 기록했다.

## 2026-06-25

### Added

- AgentLoopRunner provider composition slice를 구현했다. `runner.py`가 provider 호출 전 budget check, iteration 기록, provider retry, usage 기록, post-accounting budget check, `parse_self_report_payload`, `judge_completion` 순서를 연결한다. I2 forward-lock으로 token overrun이 `completed`로 위장되지 않음과 provider retry가 iteration budget을 소비함을 양방향 회귀로 잠갔다. 실제 domain tool handler와 task별 artifact schema 평가는 Slice 1·3 이후로 남겼다. 전체 discovery 137개 통과.
- AgentLoopRunner A3 독립 검증(합격) 후 비차단 2건을 보강했다. I3로 `InvalidBudgetPolicy`에 `decision = blocked`를 추가해 budget/registry 예외→종료 decision uniform 매핑을 완성했고, I1(유일한 spec↔impl 갭)로 `BudgetPolicy`에 `provider_retry_cap`/`tool_retry_cap`(0 이상)을 추가해 계약 §retry "retry cap은 필수 policy 값"을 구현에 실현했다. I2(runner 합성 순서)는 spec이 A3를 순수 원시로 규정해 runner slice forward-lock으로 뒀다. 전체 회귀 117→121, retry cap 검증 변이 증명(`_RETRY_DIMENSIONS=()` FAIL/복원 PASS).
- AgentLoopRunner A3를 구현했다. `judge_completion`(종료채널 self-report `FINALIZE`/`DEFER` + 구조 조건 하이브리드 판정 → `completed`/`awaiting_review`), `resolve_retry`(retry 우선순위: non-retryable 즉시 종료 → cap 소진 → cap 남음+budget 허용 retry → cap 남음+budget 차단 `budget_exhausted`에 원래 error literal trace 보존), `next_step_budget_decision`(budget 5차원 → `budget_exhausted` 매핑)을 fake/인프라 없이 양방향 회귀로 잠갔다. terminal-decision 우선순위(error > blocked/invalid_tool_arguments > budget_exhausted > completion)는 순차 합성으로 뒀다.
- A3의 F1 방어로 `BudgetTracker.record_tokens`가 음수/None/bool/비-int token count를 0으로 보정하지 않고 `InvalidProviderUsage`(decision=`provider_error`)로 거부하도록 했다(명시적 0은 유효).
- AgentLoopRunner A2를 구현했다. `ToolRegistry`가 task profile별 v1 domain tool allowlist, strict JSON argument validation(`required`·type·`additionalProperties`·array `items`만; `enum`/bounds는 후속), context-only argument 차단, canonical tool-call signature를 fake/인프라 없이 양방향 회귀로 잠근다.
- A2 독립 검증의 비차단 권고를 반영해 중첩 object schema와 array `items`를 등록 시점에 재귀 검증하고, runtime schema guard의 `assert` 의존을 명시 검사로 교체했다.
- 서비스 경계와 확정 계약을 한 곳에서 추적하기 위한 `docs/system-contract-sot.md` 초안을 추가하고, `docs/README.md`와 `docs/plans/README.md`의 진입점을 갱신했다.
- SoT 독립 검증 R1을 보강해 `docs/plans/README.md`의 문서-precedence tree를 SoT(`docs/system-contract-sot.md` §문서 우선순위)의 5-level과 통일하고, SoT를 정본 precedence로 defer 했다. 정본 precedence tree를 SoT 한 곳으로 단일화.

사용자는 HANDOFF의 다음 작업을 이어 진행하도록 요청했다. 이에 A2 범위를 실제 domain handler 구현이 아니라 registry/argument/signature 계약 회귀로 좁혀 완료하고, handler 실행·retry·completion 합성은 A3 이후로 남겼다.

독립 검증(2026-06-25)이 `flat-loop-gate.md` §33 "enum, bounds 적용" 명시와 구현이 일치하지 않음을 실증 발견했다. 사용자 결정으로 v1/A2 validator 범위를 `{required, type, additionalProperties, array items}`로 계약에 명시 좁히고 `enum`/bounds는 keyword 사용 tool 등록 시점까지 deferred로 reconcile 했다(§33·본 로그·검증 기록에 반영). 상세 기록은 `docs/verifications/2026-06-25/agent_loop_a2_registry.md`.

사용자는 여러 계획 문서가 나뉘어 있어 계약 및 서비스에 대한 정본 문서를 SoT로 활용하고 싶다고 결정했다. 이에 새 SoT 문서는 세부 Phase 계획을 대체하지 않고, 문서 우선순위·서비스 책임·확정 계약·미확정 결정을 먼저 확인하는 정본 인덱스 역할로 작성했다.

사용자는 A3 범위를 fake provider/tool을 주입받아 루프를 실구동하는 러너 골격이 아니라 A1·A2와 동일한 인프라 없는 순수 decision 합성 원시로 진행하기로 결정했다(결과: `completion.py`·`resolution.py`·budget F1 방어). self-report의 구체 wire 형식은 provider-response parser slice로, retry cap policy 배치(`BudgetPolicy` cap 추가 여부)는 별도 slice로 남겼다.

사용자는 A3 독립 검증이 "retry cap 정책 근원 부재"를 유일한 spec↔impl 갭(I1)으로 지적한 뒤, retry cap 배치를 별도 `RetryPolicy`/`TaskProfile`이 아니라 `BudgetPolicy` 확장(Option A)으로 결정했다. 이유: `allows_tools`도 budget이 아닌데 이미 `BudgetPolicy`에 있어 "run policy" 역할과 일관되고 runner가 policy 객체 1개만 전달하면 된다. tradeoff: `BudgetPolicy`가 소비 budget과 retry 한도를 함께 가져 이름이 약간 불일치하지만, 단일 run-policy 객체의 단순함이 우선했다. `resolve_retry(retries_remaining)` 시그니처는 그대로이고 runner가 `policy.<cap> - used`로 남은 retry를 계산한다.

## 2026-06-24

### Added

- 초기 아이디에이션과 실제 개발 계획의 문서 지위를 분리했다.
- `abstract.md`를 공통 기반과 Phase 1~6 계획으로 재구성했다.
- 구현 Phase와 MVP 가치 묶음이 별도 축이라는 계획 기준을 명시했다.
- 단일 사용자 Product Shell과 프로젝트/원고 CRUD·내보내기 계획을 추가했다.
- 분석 memory taxonomy와 Agentic Search/RAG 기반 변경 후보 흐름을 추가했다.
- monorepo 기반 구현 순서와 독립 LLM Gateway/Gemma Q4 검증 계획을 추가했다.
- 기존 `gemma4_12b`의 선택 이관 계획과 flat Agentic Loop Gate 보강 기준을 추가했다.
- 외부 참조 repo 없이 동작하는 portable LLM payload, provider/fake, stable errors와 fake-transport llama.cpp client를 구현했다.
- 독립 검증 조건 F1/F2를 계약·회귀로 보강하고 direct live Gemma Q4 smoke를 확인했다.
- httpx 기반 실제 JSON transport와 재현 가능한 provider smoke command를 추가했다. Mock contract 6개 회귀와 독립 검증 환경의 actual adapter live smoke까지 통과했다.
- flat loop의 task별 tool allowlist, strict argument validation, read-only v1 domain tool 6종과 Gate 비우회 원칙을 확정했다.
- 누적 token budget 우회를 막기 위해 Gateway usage를 필수화하고, flat loop budget 5차원의 계측·초과·retry 우선순위를 확정했다.
- flat loop task별 completion criteria를 확정했다. `completed`/`awaiting_review`를 하이브리드(구조 조건 AND self-report)로 판정하고, "완결된 산출 vs loop 미해결" 구분으로 Analysis/Context/Writing의 종료 기준을 잠갔다.
- AgentLoopRunner 구현을 시작했다(A1). `services/application/` 패키지에 `LoopDecision` 종료 decision 7종과 `BudgetPolicy`/`BudgetTracker` 5차원 budget을 fake/인프라 없이 양방향 회귀로 잠갔다.

사용자는 기존 문서를 초기 아이디에이션으로 보존하면서 실제 개발 전 검토가 쉽도록 긴 초안을 세분화하기를 선택했다. 이에 원문은 유지하고 `docs/plans/`를 작업용 계획 진입점으로 추가했다.

또한 혼자 사용하는 제품이므로 계정 시스템은 MVP에서 제외하고, 프로젝트 관리와 원고 내보내기를 사용자 제품 표면에 포함하기로 했다. 분석 대상은 고정 5종으로 확정하지 않고 분위기·목표·줄거리 등을 논의한 뒤, 기존 기억과의 대조 및 versioned update까지 고려한다.

LLM 운영은 같은 monorepo에서 계약을 함께 관리하되 Gateway를 독립 프로세스/컨테이너로 분리하는 제안안을 채택 후보로 기록했다. 참조 repo에서 Gemma 12B QAT GGUF Q4_0과 llama.cpp CUDA 구성을 확인했으며, 실제 하드웨어 benchmark 전에는 성능 기준을 확정하지 않는다.

사용자는 기존 `gemma4_12b`의 loop/agentic 구현 재사용과 sub-agent spawn 제외를 요청했다. 검토 결과 inference 구성과 평면형 loop 골격은 선택 이관하되, domain tool 실행은 Application/Worker가 소유하고 반복·인자·시간·token budget Gate를 보강하도록 정리했다.

사용자는 tool registry를 Application/Worker가 소유하고 task별 서버 allowlist로 제한하는 방향을 승인했다. 모델 arguments는 strict JSON Schema로 검증하고 `project_id`는 신뢰된 실행 문맥에서 주입하며, compare/validate tool은 preflight로만 사용해 독립 domain Gate를 우회하지 않도록 했다.

사용자는 budget 안전성을 위해 이전의 optional usage 계약을 의도적으로 역전했다. `usage`와 두 token count는 필수이며 누락은 `provider_invalid_response`로 처리하되, 명시적 0 token은 정상값으로 계속 허용한다. 이 결정은 token usage를 `unknown`으로 전파하는 대안보다 단일 Gateway 경계에서 누락을 차단하는 단순성을 택한 것이다.

사용자는 task별 completion criteria를 하이브리드 판정으로 확정했다. `completed`는 구조 조건(목표 산출물 존재)과 자율 조건(모델이 미해결 분기를 self-report하지 않음)을 모두 충족해야 한다. `analysis_compare`의 부분 모호는 loop decision과 candidate status의 직교성을 활용해 run `completed`로 두고 개별 모호 후보는 candidate status로 표현하며, tool 없는 `writing_generate`는 모델이 산출물 자체의 모호·충돌을 self-report할 때만 `awaiting_review`로 종료한다. 이 방향은 개별 항목의 불확실성을 loop 미완료로 승격하지 않고 완결된 산출로 표현하는 직교 모델을 택한 것이다.

여러 개발 머신에서 참조 repo가 없을 수 있으므로 외부 경로는 runtime dependency로 사용하지 않는다. 첫 구현 slice로 llama.cpp thinking payload 경계를 현재 repo에 자립적으로 이관했으며, 작업용 머신의 real-model smoke는 보류한다.
