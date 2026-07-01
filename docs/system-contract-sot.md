# 시스템 정본 계약 SoT

상태: `Approved`  
계약 버전: `v1.6.16`
승인일: `2026-06-26`  
최근 갱신일: `2026-07-01`
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

이 문서의 `Approved` 상태는 정본 계약 인덱스와 문서 우선순위의 승인을 뜻한다. 아래 "미확정" 항목은 이 승인으로 확정되지 않으며, 사용자 결정 또는 별도 승인된 Phase 계획 없이는 추측해 구현하지 않는다.

## 계약 버전 관리

- 이 문서의 계약 버전은 사용자 결정으로 정본 계약, 문서 우선순위, 서비스 경계, public literal, 미확정 항목의 상태가 바뀔 때 올린다.
- 호환 가능한 명확화, 링크 보정, 검증 근거 추가는 patch 수준으로 기록한다.
- 구현 계약이나 public literal 의미가 바뀌면 minor 이상으로 기록하고, 영향받는 계획 문서·테스트·검증 기록을 함께 갱신한다.
- 기존 승인 결정과 충돌하는 새 요청이 들어오면 구현 전에 충돌을 명시하고 어느 쪽이 canonical인지 사용자에게 확인한다.
- 상세 작업 이력은 `docs/daily_logs/`에 남기고, 이 문서에는 현재 정본에 영향을 주는 변경만 기록한다.

## 계약 변경 이력

| 버전 | 날짜 | 변경 | 근거 |
|---|---|---|---|
| v1.6.16 | 2026-07-01 | Phase 2A provider/Gateway runner factory wiring의 첫 구현 slice를 추가했다. Core SOT는 snapshot별 source_ref catalog read surface를 제공하고 Mongo required index `source_refs_by_project_snapshot`을 설치한다. Prompt template은 `prompt_templates` 저장소에 `task_type + version` unique contract로 seed/fetch하며 `analysis_extract_v1`을 기본 seed한다. Prompt builder는 snapshot과 source_ref catalog를 Gateway `ChatCompletionRequest`로 조립한다. Application은 `LLM_GATEWAY_BASE_URL`이 설정된 경우 `/v1/generate` 기반 `GatewayGenerateProvider`와 `VersionedPromptAnalysisExtractionAdapter`로 기본 analysis runner를 구성하고, env가 없으면 기존처럼 503을 반환한다. `{"candidates":[]}`는 유효한 빈 extraction으로 처리한다. | `tests/test_core_sot.py`, `tests/test_prompt_templates.py`, `tests/test_analysis_prompt_builder.py`, `tests/test_analysis_gateway_provider.py`, `tests/test_analysis_extractor_schema.py`, `tests/test_analysis_runner.py`, `tests/test_application_api.py` |
| v1.6.15 | 2026-07-01 | Phase 2A provider/Gateway wiring pre-implementation 결정을 승인했다. 첫 실제 provider wiring은 tool-call 없는 terminal JSON extraction으로 진행하고, 모델은 새 source_ref를 생성하지 않고 입력 source_ref catalog의 id를 선택한다. Prompt template은 DB에 저장해 versioned 관리하며 첫 literal은 `analysis_extract_v1`, task_type은 `analysis_extract`다. Gateway 호출 surface는 구현 전 비용 확인으로 `/v1/generate` 임시 사용과 `/v1/generate-structured` 최소 구현 중 선택한다. | 사용자 결정, `plans/02-analysis-provider-wiring-decisions.md` |
| v1.6.14 | 2026-06-30 | 첫 export 형식을 plain text + Markdown으로 확정하고 Slice 1 draft version export 계약을 추가했다. `GET /projects/{project_id}/drafts/{draft_id}/versions/{version_id}/export?format=txt\|markdown`은 선택 version snapshot의 `raw_text`를 verbatim body로 내보내고(AI metadata 미주입, Markdown 합성/제거 없음, 두 형식 body 동일), `format`은 content_type/확장자만 가른다. payload에 version 추적 필드 포함. unsupported format 400, missing/cross-project version 404, archived도 export 허용. 사용자 결정: 막힌 Next Tasks 대신 export 진행, 형식은 plain text + Markdown. | 사용자 결정, `tests/test_core_sot.py`, `tests/test_application_api.py` |
| v1.6.13 | 2026-06-30 | Gemma Q4_0 llama.cpp live benchmark를 실행하고 AgentLoopRunner task profile의 초기 production budget/retry 숫자 기본값을 확정했다. Report는 `docs/benchmarks/2026-06-30/gemma_q4_llama_cpp_repeats3_warmup1.json`이며, `flat-loop-gate.md`가 `analysis_compare`, `context_search`, `writing_generate` 기본 policy를 소유한다. | 사용자 요청, `scripts/benchmark_llm_provider.py`, `docs/benchmarks/2026-06-30/gemma_q4_llama_cpp_repeats3_warmup1.json` |
| v1.6.12 | 2026-06-30 | Phase 2A analysis run endpoint 계약을 승인·구현했다. `POST /projects/{project_id}/analysis/jobs/{job_id}/run`은 pending job만 runner dependency로 실행하고 요청 안에서 await해 terminal job과 candidate 목록을 반환한다. `running`/`succeeded`/`failed` job은 재실행하지 않고 `idempotent_replay=true`로 현재 job과 저장된 candidate를 반환한다. pending job에서 runner가 구성되지 않았으면 503, missing/cross-project 및 `snapshot_not_found`는 404, `schema_invalid`/`source_invalid` 계열은 400, `duplicate_conflict`는 409, provider/기타 실행 오류는 502로 표면화한다. source_ref 자동 생성과 Gateway runtime wiring은 제외다. | 사용자 요청, `tests/test_application_api.py`, `tests/test_analysis_runner.py` |
| v1.6.11 | 2026-06-30 | Phase 2A analysis job/candidate HTTP read surface를 추가했다. Application API는 `POST /projects/{project_id}/analysis/jobs`로 job을 idempotent 생성/replay하고, `GET /projects/{project_id}/analysis/jobs/{job_id}`와 `GET /projects/{project_id}/analysis/jobs/{job_id}/candidates`로 job 상태와 candidate를 조회한다. 이 API는 runner/gateway 실행을 시작하지 않으며, 존재하지 않는 project 또는 cross-project job/candidate 접근은 404다. | `tests/test_application_api.py` |
| v1.6.10 | 2026-06-29 | Phase 2A job all-or-nothing 범위를 명확화했다. all-or-nothing은 candidate write에 한정되며, job/task 생성은 idempotent setup이라 실패 후에도 남을 수 있다(롤백 대상 아님). 동작 변경 없음, runner slice 2 검증의 비차단 오해 여지 해소. | `verifications/2026-06-29/analysis_job_state_runner_slice2.md` |
| v1.6.9 | 2026-06-29 | Phase 2A job 상태 전이와 실패 상태 저장 계약을 승인했다. 상태는 `AnalysisJob`에만 두고(Task 무상태), `pending→running→succeeded|failed` 전이만 허용하며 terminal은 불변이다. runner는 새 job(`pending`)만 실행하고 기존 job은 replay로 반환하며, `failed`는 terminal이라 재실행은 새 `idempotency_key`로 한다. `failed`는 닫힌 `failure_reason` enum(`snapshot_not_found`, `source_invalid`, `schema_invalid`, `provider_error`, `duplicate_conflict`) + free-text `failure_detail`로 저장한다. | 사용자 결정, `plans/02-analysis-job-state-decisions.md` |
| v1.6.8 | 2026-06-29 | Phase 2A candidate write의 write-error 분류를 정밀화했다. duplicate-key(code `11000`) 충돌만 `DuplicateAnalysisCandidateRequest`로 표면화하고, 그 외 `BulkWriteError`/`PyMongoError`는 원본 타입을 보존해 인프라 오류 오표기를 막는다. fallback은 매핑 여부와 무관하게 이번 시도 candidate `_id`를 먼저 정리한다. | `verifications/2026-06-29/analysis_mongo_persistence_hardening.md` |
| v1.6.7 | 2026-06-29 | Phase 2A service batch API의 intra-batch idempotency를 명시했다. 같은 batch 안의 동일 `project_id + task_id + logical_key` request는 첫 candidate를 만들고 이후 항목은 idempotent replay로 정규화하며, 다른 logical_key는 별도 candidate로 유지한다. Mongo bulk duplicate는 stable `DuplicateAnalysisCandidateRequest`로 표면화한다. | `verifications/2026-06-29/analysis_mongo_persistence.md` |
| v1.6.6 | 2026-06-29 | Phase 2A Analysis Mongo persistence 계약을 명시했다. `analysis_jobs`, `analysis_tasks`, `analysis_candidates`를 저장하고 job/task/candidate idempotency는 unique index로 강제한다. Candidate batch write는 transaction 경로에서 한 트랜잭션으로 commit하고, non-transaction fallback은 single-writer local/test 경로로 실패 시 이번 시도 candidate만 rollback한다. | `plans/02-analysis-pipeline.md` |
| v1.6.5 | 2026-06-29 | Phase 2A runner는 source validation이 구성된 `AnalysisService`만 받도록 명시하고, 같은 run의 duplicate `(task_id, logical_key)` draft는 result/write에서 1개로 정규화한다. Mongo persistence slice에서는 runner all-or-nothing의 transaction/fallback 보존을 별도 검증한다. | `verifications/2026-06-29/analysis_phase2a_slice4.md` |
| v1.6.4 | 2026-06-29 | Phase 2A extraction runner 계약을 명시했다. Runner는 job을 idempotent 생성/재사용하고, snapshot 로드→provider extraction→task 생성/재사용→전체 draft 사전 검증→candidate 저장 순서로 실행한다. Task는 `project_id + job_id + candidate_type`으로 재사용하며, candidate write는 모든 draft의 logical_key/source/schema 검증 뒤 시작한다. | `plans/02-analysis-pipeline.md` |
| v1.6.3 | 2026-06-29 | Phase 2A `source_anchors` identity를 unordered set으로 명확화했다. 같은 anchor 중복은 identity와 parsed draft에서 하나로 정규화하며, ordered evidence chain이 필요해지면 순서 의미를 별도 필드(`sequence`/`evidence_order` 등)로 계약화한다. | `verifications/2026-06-29/analysis_phase2a_slice3.md` |
| v1.6.2 | 2026-06-29 | Phase 2A logical_key derivation에서 같은 `source_anchors` set은 순서와 무관하게 같은 key를 만든다고 명시했다. Anchor 내용이 다르면 별도 candidate identity다. | `verifications/2026-06-29/analysis_phase2a_slice2.md` |
| v1.6.1 | 2026-06-29 | Phase 2A source validation 이후 최소 taxonomy schema와 fake-provider extraction adapter 계약을 명시했다. Payload는 `character_observation {name, observation}`, `event_observation {event}`, `open_question_observation {question}`이고 모든 field는 non-empty string이다. Provider extraction output은 top-level `{candidates: [...]}` JSON object이며, logical_key는 `candidate_type + payload + source_anchors` canonical JSON SHA-256으로 파생한다. | `plans/02-analysis-kickoff-decisions.md`, `plans/02-analysis-pipeline.md` |
| v1.6 | 2026-06-29 | Phase 2A 착수 최소 계약 승인: taxonomy 3종(`character_observation`, `event_observation`, `open_question_observation`), provenance `source_observed`/`ai_inferred`, candidate action `create` only, status `needs_review`, confidence range만 강제, `create_source_ref` primitive non-idempotent 유지 + candidate/job 저장층 retry idempotency 소유, 2A/2B milestone 분리. 같은 날 검증 보강으로 confidence NaN 거절, action≠`create` 회귀, `logical_key` 임시 identity 계약을 명시했다. | 사용자 결정, `plans/02-analysis-kickoff-decisions.md`, `verifications/2026-06-29/analysis_phase2a_slice1.md` |
| v1.5.1 | 2026-06-28 | Core SOT Mongo adapter setup 계약 명확화: query path를 지탱하는 required index는 `uniq_save_request`와 `blocks_by_snapshot`이며, MongoDB가 required index 생성을 거부하면 `MongoRepositorySetupError`로 표면화한다. 현재 query path가 없는 `source_refs_by_snapshot` 인덱스는 required contract에서 제외한다. | `docs/verifications/2026-06-28/mongo_index_setup.md` O1/O2 |
| v1.5 | 2026-06-28 | archive를 읽기 전용 상태로 명문화: 읽기 허용, 본문 쓰기(draft 생성·version 저장)+메타데이터 수정(rename) 차단(409), SOT 본문은 archive 무관 불변, 상태 전이(unarchive)와 source_ref/분석 후보 archived 정책은 범위 밖. 기존 구현·회귀와 정합하는 문서 명문화. (같은 날 비의미 명확화: archived project 하위 draft를 archive하는 것은 상태 전이이므로 하위 draft 쓰기 차단의 예외임을 명시 — `archive_api_endpoint.md` Issue #1.) | 사용자 결정, `docs/verifications/2026-06-28/rename_api.md` R1 |
| v1.4 | 2026-06-28 | non-transaction fallback을 single-writer 전용으로 명시. 동시성 안전은 transaction 기본 경로가 담당하고, fallback의 orphan cleanup/retry guard는 같은 writer의 순차 재시도에만 정의됨. | 사용자 결정(R2 option b), `docs/verifications/2026-06-28/mongo_adapter_recheck.md` |
| v1.3 | 2026-06-26 | Core SOT persistence/retention 계약 승인: Mongo transaction 기본, 제한적 non-transaction fallback, explicit version save only, save idempotency key 필수, project/draft archive와 snapshot/version/source_ref 보존. | 사용자 승인 |
| v1.2 | 2026-06-26 | Core SOT text/reference 계약 승인: raw snapshot 기준, Unicode code point offset, raw UTF-8 SHA-256 content hash, deterministic MVP source block split. Adaptive/length-based chunking은 파생 index layer 후속 후보로 분리. | 사용자 승인 |
| v1.1 | 2026-06-26 | Slice 1 실행 경계 승인: monorepo+독립 LLM Gateway, FastAPI Application API, 느슨하게 분리 가능한 Worker 경계. frontend framework 최종 선택은 보류. | 사용자 승인 |
| v1.0 | 2026-06-26 | SoT를 정본 계약 인덱스로 승인. 미확정 항목은 계속 추측 구현 금지. | 사용자 승인, `docs/verifications/2026-06-25/system_contract_sot.md` |

## 문서 역할

| 문서 | 역할 | 지위 |
|---|---|---|
| 이 문서 | 서비스/계약 SoT 인덱스와 우선순위 | Approved SoT v1.6.14 |
| [`plans/README.md`](plans/README.md) | 계획 문서 진입점과 Phase/MVP 관계 | Draft |
| [`plans/00-foundations.md`](plans/00-foundations.md) | 전역 원칙과 제품 경계 | Draft |
| [`plans/implementation-plan.md`](plans/implementation-plan.md) | 구현 순서, slice 상태, 검증 gate | Draft |
| [`plans/llm-gateway.md`](plans/llm-gateway.md) | LLM Gateway 계약과 Gemma Q4 검증 | Proposed |
| [`plans/flat-loop-gate.md`](plans/flat-loop-gate.md) | AgentLoopRunner decision/tool/budget/completion 계약 | Draft, 일부 구현 검증됨 |
| [`plans/product-shell.md`](plans/product-shell.md) | 사용자 제품 표면 | Draft |
| [`plans/01-core-sot.md`](plans/01-core-sot.md) | MongoDB 정본 저장 계약 | Draft |
| [`plans/02-analysis-kickoff-decisions.md`](plans/02-analysis-kickoff-decisions.md) | Phase 2A 착수 최소 결정 | Approved for Phase 2A kickoff |
| [`plans/02-analysis-job-state-decisions.md`](plans/02-analysis-job-state-decisions.md) | Phase 2A job 상태 전이 결정 | Approved for Phase 2A job-state slice |
| [`plans/02-analysis-provider-wiring-decisions.md`](plans/02-analysis-provider-wiring-decisions.md) | Phase 2A provider/Gateway wiring 결정 | Approved for Phase 2A provider wiring pre-implementation |
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

## 구현 기술 결정

- 저장소 구조는 monorepo를 유지한다.
- LLM Gateway는 같은 repo에서 계약을 맞추되 독립 프로세스/컨테이너 경계를 유지한다.
- Application API의 backend framework는 FastAPI를 사용한다.
- frontend framework 최종 선택은 보류한다. 개인 로컬 시스템의 단일 서비스 UI로 충분할 수 있으므로, standalone frontend가 필요해질 때 React 또는 Vue를 기본 후보로 검토한다.
- Worker는 Application과 코드·계약을 공유하되, 나중에 별도 entrypoint나 프로세스로 분리할 수 있게 느슨하게 연결한다.
- 초기 local/personal runtime에서는 외부 queue 제품을 전제하지 않고 단순한 in-process/background boundary로 시작한다. 더 강한 queue가 필요하다는 증거가 생기면 별도 결정으로 승격한다.

## 확정된 전역 계약

### 제품과 프로젝트 경계

- MVP는 계정/인증이 없는 단일 사용자 시스템이다.
- 그래도 모든 저장·검색·Gate·tool handler는 `project_id`를 강제한다.
- 향후 다중 사용자를 위해 `user_id`를 지금 억지로 넣지 않는다.
- Product Shell은 프로젝트/원고 작업 표면이며 AI 기억의 정본을 별도로 소유하지 않는다.

### Source of Truth

- MongoDB가 원문과 구조화 기억의 SOT다.
- 원문 snapshot은 primary SOT다.
- 원문 snapshot의 `raw_text`는 저장 후 변경하지 않는다.
- `source_ref` offset은 `raw_text` 기준 Unicode code point index로 계산한다.
- MVP `source_ref` span은 하나의 `source_block` 안에 포함되어야 한다. 여러 block을 가로지르는 인용은 후속 후보/review 계약에서 별도로 다룬다.
- `content_hash`는 `raw_text`의 UTF-8 bytes에 대한 SHA-256이다.
- `normalized_text_hash`는 v1 필수 계약이 아니다. 정규화 기반 dedupe/search가 필요해질 때 별도 계약으로 추가한다.
- MVP `source_blocks`는 deterministic source reference 단위다. Markdown heading, 명시 scene marker, paragraph boundary 기반으로 만들며 AI 추론으로 block을 나누지 않는다.
- 사용자가 승인한 설정은 canonical SOT다.
- 분석 결과는 저장되더라도 derived SOT이며 상태와 근거가 필요하다.
- ChromaDB와 Elasticsearch는 MongoDB로 재생성 가능한 파생 인덱스다.
- adaptive chunking, semantic chunking, 길이 기반 episode/section chunking은 검색 품질을 위한 파생 index 후보이며 MongoDB raw snapshot/source_ref 정본을 대체하지 않는다.
- 검색 hit는 MongoDB pointer/version/hash로 재조회하기 전까지 정본 사실이 아니다.
- draft save는 명시적 version save만 지원한다. autosave는 MVP 범위가 아니며, 필요성이 확인될 때 별도 사용자 결정으로만 추가한다.
- draft save request는 `idempotency_key`를 필수로 가진다. 같은 `project_id + draft_id + idempotency_key` 재시도는 같은 `draft_version`을 반환해야 한다.
- Mongo adapter는 required query indexes `uniq_save_request`(`project_id`, `draft_id`, `idempotency_key`, unique)와 `blocks_by_snapshot`(`snapshot_id`, `block_index`)를 설치해야 한다. MongoDB가 required index 생성을 거부하면 setup failure는 `MongoRepositorySetupError`로 표면화한다. 현재 `source_refs` 조회는 `_id` 기준이므로 by-snapshot source_ref index는 required contract가 아니다.
- Docker 기반 정상 runtime은 MongoDB transaction을 기본으로 사용한다. non-transaction fallback은 transaction을 사용할 수 없는 local/test 환경의 제한적 경로이며, write order, idempotency lookup, orphan cleanup/retry guard를 요구한다.
- non-transaction fallback은 **single-writer 전용**이다. 같은 `(project_id, draft_id, idempotency_key)`에 대한 동시 draft save는 fallback에서 보장하지 않으며(orphan cleanup이 동시 writer의 committed dependents를 지울 수 있음), 동시성 안전이 필요한 runtime은 transaction 기본 경로를 사용한다. fallback의 orphan cleanup/retry guard는 같은 writer의 순차 재시도에 대해서만 정의된다.
- project/draft 삭제는 MVP에서 archive로 처리한다. `source_snapshots`, `draft_versions`, `source_blocks`, `source_refs`는 보존한다.
- archive는 보존이자 **읽기 전용 상태**다. archived project/draft에 대해:
  - 읽기(project/draft get·list, version/snapshot/block 재조회)는 허용한다.
  - 본문 쓰기(draft 생성, version 저장)와 메타데이터 수정(project/draft rename)은 차단한다(409 Archived). project archive는 그 하위 draft 쓰기까지 차단한다.
  - SOT 본문(`source_snapshots`, `draft_versions`, `source_blocks`)은 archive 여부와 무관하게 생성 후 불변이다. 따라서 "archived 본문 수정"이라는 연산은 존재하지 않는다.
  - archive/unarchive 같은 상태 전이는 본 쓰기 차단의 대상이 아니다. 여기에는 archived project 하위 draft를 archive하는 것도 포함되므로(상태 전이), "하위 draft 쓰기 차단"의 예외로서 archived project에서도 허용한다. unarchive는 MVP 범위가 아니므로 본 계약은 "archived인 동안 차단"으로 한정하며 영구 불변을 규정하지 않는다.
  - `source_refs` 생성은 보존된 immutable snapshot에 대한 파생 주석이므로 archived 상태에서도 **허용한다**(사용자 결정). 이는 본문/메타데이터 쓰기 차단의 예외다.
- `create_source_ref` primitive는 non-idempotent다. 같은 span 재호출은 새 ref를 만들 수 있다. Phase 2A candidate/job 저장층이 같은 logical candidate retry 중복 방지 idempotency를 소유한다.
- Phase 2A candidate retry identity는 `project_id + task_id + logical_key`다. `logical_key`는 비어 있지 않은 문자열이어야 한다. schema/extraction slice의 기본 derivation은 `candidate_type + payload + source_anchors` canonical JSON의 SHA-256이며, 같은 provider retry payload는 같은 key가 되고 payload 또는 anchor set이 다른 관찰은 별도 candidate가 된다. `source_anchors`는 identity에서 unordered set으로 취급하므로 provider 출력 순서와 동일 anchor 중복은 같은 identity로 정규화한다. 순서 의미가 필요한 ordered evidence chain은 후속 schema에서 `sequence`/`evidence_order` 같은 명시 필드를 추가해 계약화한다.
- archive/delete 이후 파생 인덱스는 stale 처리, version filter, rebuild 대상으로 다루며 MongoDB 정본 보존을 되돌리지 않는다.
- 분석 후보의 부분 승인, 부분 저장, 나머지 retry는 Phase 2/6 review action idempotency 계약에서 다룬다. Slice 1 draft save idempotency와 섞지 않는다.

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
- 첫 export 형식은 plain text와 Markdown으로 확정했다(v1.6.14). DOCX/PDF/EPUB은 후속 검토다.
- 보관/삭제 정책, draft/chapter/scene 계층은 미확정이다.

### Phase 1. Core SOT

정본 세부 문서: [`plans/01-core-sot.md`](plans/01-core-sot.md)

- `projects`, `drafts`, `draft_versions`, `source_snapshots`, `source_blocks`, `source_refs` 계약을 만든다.
- snapshot은 생성 후 수정하지 않는다.
- text/reference와 persistence/retention 계약은 v1.2~v1.3에서 승인됐다.
- Application API는 `GET /projects/{project_id}/drafts/{draft_id}/versions/{version_id}/export?format=txt|markdown`으로 선택한 draft version을 내보낸다. export `body`는 그 version snapshot의 `raw_text`를 verbatim으로 내보내며 AI 분석 metadata를 본문에 주입하지 않고 Markdown을 합성·제거하지 않는다(두 형식 body 동일). `format`은 `content_type`(`text/plain`/`text/markdown`)과 filename 확장자(`.txt`/`.md`)만 가른다. payload는 `version_id`/`version_number`/`snapshot_id`/`content_hash` 추적 필드를 포함한다. 지원하지 않는 format은 400, missing/cross-project version은 404다. archive는 read를 막지 않으므로 export는 archived에서도 가능하다.

### Phase 2. Analysis Pipeline

정본 세부 문서: [`plans/02-analysis-pipeline.md`](plans/02-analysis-pipeline.md)

- Phase 2A는 prior memory 없이 snapshot 근거 기반 후보를 만든다.
- Phase 2A 최소 taxonomy는 `character_observation`, `event_observation`, `open_question_observation` 3종으로 시작하며 후속 확장을 막지 않는 구조로 구현한다.
- Phase 2A provenance literal은 `source_observed`와 `ai_inferred`만 허용한다. `user_declared`는 WritingBrief/Product Shell 입력 계약 이후로 미룬다.
- Phase 2A candidate action은 `create` only이고 status는 `needs_review`로 고정한다.
- Phase 2A confidence는 `0.0 <= confidence <= 1.0`만 강제하고 자동 reject threshold는 후속 품질 fixture 이후 결정한다. NaN은 이 범위 밖이므로 거절한다.
- Phase 2A source validation은 `CandidateSourceAnchor(source_ref_id, start_offset, end_offset, quote, content_hash)`를 같은 project의 Core SOT `SourceRef`와 대조한다. source_ref가 없거나 다른 project에 속하거나 span/quote/hash가 다르면 candidate 저장을 거절한다.
- Phase 2A Snapshot Loader는 같은 project의 Core SOT snapshot raw text, content hash, source block ids를 analysis 입력으로 로드한다. 다른 project의 snapshot은 찾을 수 없는 것으로 처리한다.
- Phase 2A 최소 payload schema는 `character_observation {name, observation}`, `event_observation {event}`, `open_question_observation {question}`이다. 모든 payload field는 non-empty string이며 추가 field와 누락 field는 malformed payload로 거절한다.
- Phase 2A fake-provider extraction adapter는 provider content를 top-level `{candidates: [...]}` JSON object로 파싱하고, 각 candidate의 approved type/provenance/confidence/source_anchors/payload를 검증한 뒤 candidate draft를 만든다.
- Phase 2A extraction runner는 source validation이 구성된 `AnalysisService`만 받는다. Runner는 `AnalysisJob`을 `project_id + snapshot_id + idempotency_key`로 idempotent 생성/재사용하고, Snapshot Loader → provider extraction → `AnalysisTask` 생성/재사용 → 전체 draft 사전 검증 → candidate 저장 순서로 실행한다. Task는 `project_id + job_id + candidate_type`으로 재사용한다. 한 run의 candidate write는 모든 draft가 logical_key/source/schema 검증을 통과한 뒤 시작한다. 같은 run의 duplicate `(task_id, logical_key)` draft는 1개로 정규화한다. Job 상태 전이와 실패 상태 저장 계약은 아래 job-state 조항(v1.6.9)에서 정의했으며 구현은 job-state slice다.
- Phase 2A service batch API는 같은 batch 안의 동일 `project_id + task_id + logical_key` candidate request를 idempotent replay로 정규화한다. 첫 request는 candidate를 만들고 이후 동일 request는 같은 candidate를 반환한다. 같은 batch 안에서도 logical_key가 다르면 별도 candidate로 유지한다.
- Phase 2A Mongo persistence는 `analysis_jobs`, `analysis_tasks`, `analysis_candidates`를 저장한다. Required idempotency indexes는 `uniq_analysis_job_request`(`project_id`, `snapshot_id`, `idempotency_key`, unique), `uniq_analysis_task_request`(`project_id`, `job_id`, `candidate_type`, unique), `uniq_analysis_candidate_request`(`project_id`, `task_id`, `logical_key`, unique)다. Candidate list query는 `analysis_candidates_by_job`(`project_id`, `job_id`) index를 사용한다. MongoDB가 required index 생성을 거부하면 setup failure는 `MongoAnalysisRepositorySetupError`로 표면화한다.
- Phase 2A candidate batch write는 transaction 경로에서 한 트랜잭션으로 commit한다. Non-transaction fallback은 Core SOT fallback과 같이 **single-writer local/test 전용**이며, 실패하면 이번 시도에서 새로 쓴 candidate `_id`만 삭제해 candidate 부분 저장을 남기지 않는다. 동시성 안전이 필요한 runtime은 transaction 경로를 사용한다.
- Phase 2A candidate write의 duplicate 충돌만 stable `DuplicateAnalysisCandidateRequest`로 표면화한다. `insert_many`가 unique index를 위반하면 pymongo는 duplicate-key code `11000`을 담은 `BulkWriteError`를 던지므로 양 경로(transaction/fallback)는 이를 `DuplicateAnalysisCandidateRequest`로 매핑한다. duplicate가 아닌 다른 `BulkWriteError`/`PyMongoError`(예: document validation, write concern)는 원본 예외 타입을 보존해 인프라 오류가 duplicate request로 오표기되지 않게 한다. fallback은 매핑 여부와 무관하게 이번 시도 candidate `_id`를 먼저 정리한다.
- Phase 2A job 상태는 `AnalysisJob`에만 둔다. `AnalysisTask`는 status가 없다(candidate_type 파티션이며 독립 lifecycle 없음). job 상태는 `pending`(생성, 미실행) → `running`(추출/검증/저장 진행) → `succeeded`(이번 run candidate 모두 저장) | `failed`(실패, candidate 미저장)다. 허용 전이는 `pending→running`, `running→succeeded`, `running→failed`뿐이고 그 외는 `InvalidJobStateTransition`이다. terminal 상태(`succeeded`/`failed`)는 불변이다.
- Phase 2A runner는 새로 생성한 job(`pending`)일 때만 추출을 실행한다. `find_job_request`가 기존 job(상태 무관)을 찾으면 idempotent replay로 그대로 반환하고 재실행하지 않는다. `failed`는 terminal이며 같은 snapshot 재분석은 새 `idempotency_key`(새 job)로 한다. crash 등으로 비terminal에 멈춘 stale job의 자동 복구/재개는 MVP 범위 밖이다.
- Phase 2A `failed` job은 닫힌 `failure_reason` enum과 free-text `failure_detail`을 저장한다. `failure_reason`은 `snapshot_not_found`(snapshot 로드 실패), `source_invalid`(source_ref/anchor 검증 실패), `schema_invalid`(payload/logical_key/provider content malformed), `provider_error`(provider extraction 호출 실패, Gateway `provider_error` umbrella와 정렬), `duplicate_conflict`(candidate 저장 `DuplicateAnalysisCandidateRequest`)다. `succeeded`/비terminal 상태에서는 `failure_reason`/`failure_detail`이 비어 있어야 한다. 실패는 성공으로 위장하지 않으며 candidate를 저장하지 않는다. all-or-nothing은 candidate write에 한정되고, job/task 생성은 idempotent setup이라 실패 후에도 남을 수 있다(롤백 대상 아님).
- Phase 2A Application API는 `POST /projects/{project_id}/analysis/jobs`로 job을 `project_id + snapshot_id + idempotency_key` 기준 idempotent 생성/replay하고, `GET /projects/{project_id}/analysis/jobs/{job_id}`로 job 상태를 읽고, `GET /projects/{project_id}/analysis/jobs/{job_id}/candidates`로 저장된 candidate를 읽는다. 존재하지 않는 project 또는 다른 project의 job/candidate 접근은 404로 처리한다.
- Phase 2A Application API는 `POST /projects/{project_id}/analysis/jobs/{job_id}/run`으로 기존 job 실행을 시작할 수 있다. 이 endpoint는 `pending` job만 실행하며, runner dependency를 주입받아 요청 안에서 async runner를 await한다. `running`/`succeeded`/`failed` job은 재실행하지 않고 현재 job과 저장된 candidate를 `idempotent_replay=true`로 반환한다. pending job에서 runner가 구성되지 않았으면 503이다. 실패 HTTP mapping은 `snapshot_not_found` 404, `schema_invalid`/`source_invalid` 계열 400, `duplicate_conflict` 409, provider/기타 실행 오류 502다. 실패 job은 이후 `GET`으로 조회 가능해야 한다. source_ref 자동 생성과 Gateway runtime wiring은 이 endpoint 범위가 아니다.
- Phase 2A 실제 provider wiring 첫 slice는 tool-call 없는 terminal JSON extraction으로 진행한다. source_ref 후보는 Application/Worker가 static/mechanical anchor catalog로 준비하고, 모델은 새 source_ref를 생성하지 않고 입력 catalog의 `source_ref_id`만 선택한다. Core SOT는 `project_id + snapshot_id`로 source_ref catalog를 source order로 읽는 surface를 제공하며, Mongo required index는 `source_refs_by_project_snapshot`이다. Prompt template은 DB에 저장해 versioned 관리하며, `prompt_templates` 저장소는 `task_type + version` unique contract를 가진다. 첫 prompt version literal은 `analysis_extract_v1`, task_type은 `analysis_extract`다. Prompt builder는 snapshot metadata/raw_text와 source_ref catalog를 Gateway `ChatCompletionRequest`로 조립한다. Application runtime은 `LLM_GATEWAY_BASE_URL`이 설정된 경우 `/v1/generate` 기반 provider adapter와 versioned prompt extractor로 기본 analysis runner를 구성한다. env가 없으면 기존처럼 pending `run`은 runner 미구성 503이다. `{"candidates":[]}`는 유효한 빈 extraction 결과다.
- Phase 2A와 2B는 별도 milestone이다.
- Phase 2B는 Phase 3~4 이후 prior memory를 검색해 `create/update/add_evidence/no_change/conflict` 후보를 만든다.
- Analysis AI는 canon을 확정하지 않고 기존 기억을 직접 덮어쓰지 않는다.
- Phase 2B taxonomy 확장, confidence threshold, `confirmed` 자동 승격 여부는 미확정이다.

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
| AgentLoopRunner production budget defaults | benchmark 기반 확정 | `docs/benchmarks/2026-06-30/gemma_q4_llama_cpp_repeats3_warmup1.json`, `plans/flat-loop-gate.md` |
| Core SOT minimal skeleton | 구현·조건부 검증 보강 완료 | `services/application/app/core_sot/`, `services/application/app/main.py`, `tests/test_core_sot.py`, `tests/test_application_api.py`; C1/C2/C3 보강 |
| Product Shell UI/Phase 2~6 | 미구현 | 계획 문서만 존재 |

## 다음 구현 경계

- agent_loop 계약층은 A1/A2/A3, self-report parser, provider composition까지 구현·독립 검증됐다.
- runner의 domain tool-call branch는 지금 구현하지 않는다. 선행 계약은 (1) Gateway tool-call response parsing, (2) model tool-call wire format, (3) Phase payload와 실제 tool handler다.
- `ProviderTurnResult`는 현재 terminal provider content와 usage만 표현한다. tool-call 수신 구조는 wire 계약이 생긴 뒤 확장한다.
- `artifact_present`는 현재 runner에 주입되는 결정 함수다. Slice 2A AnalysisCandidate, Slice 4 ContextPackage, Slice 5 WritingCandidate schema가 확정되면 profile별 구조 조건 평가로 교체한다.

## 미확정 결정 목록

다음 항목은 구현자가 임의로 채우지 않는다.

- frontend framework 최종 선택. standalone frontend가 필요해질 때 React 또는 Vue를 기본 후보로 검토한다.
- 외부 queue 제품 선택. 초기 local/personal runtime은 단순한 in-process/background boundary로 시작한다.
- Gateway/model tool-call response wire format
- `confirmed`와 `canonical`의 의미 및 승격 주체
- Phase 2/6 review action idempotency와 부분 승인/부분 retry 정책
- adaptive chunking 또는 길이 기반 episode/section chunking을 Phase 3 파생 index에 도입할지 여부
- Phase 2B taxonomy 확장과 confidence threshold
- Analysis `update/add_evidence/no_change/conflict`의 정확한 public envelope
- Chroma embedding model, ES analyzer, sync delivery 방식
- ContextPackage schema variant(Writing용/Analysis용 공통 또는 분리)
- WritingCandidate 출력 단위(full text/patch)
- Writing Gate decision literal과 editor 처리
- enum/bounds를 쓰는 첫 tool schema 등록 시 validator 확장 방식

## 변경 규칙

1. 계약 literal을 바꿀 때는 해당 테스트와 검증 기록을 함께 갱신한다.
2. spec과 구현이 충돌하면 둘 중 하나를 조용히 선택하지 않는다.
3. 미확정 항목을 구현해야 하면 사용자 결정 또는 좁은 spike로 먼저 계약을 만든다.
4. 문서-only 변경도 링크, 우선순위, status, 관련 HANDOFF를 확인한다.
5. 상세 구현 이력은 daily work log에 기록하고, 현재 actionable 상태만 `HANDOFF.md`에 남긴다.
