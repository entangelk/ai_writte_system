# HANDOFF

## Current Status

- `docs/` 루트의 기존 설계 문서는 초기 아이디에이션 자료로 분류되어 있다.
- 실제 개발 준비용 진입점은 `docs/plans/README.md`다.
- 서비스 경계와 확정 계약을 모은 정본 SoT는 `docs/system-contract-sot.md`다.
- 계획은 공통 기반, Product Shell, 분석 memory taxonomy, Phase 1~6으로 나뉘어 있다.
- Product Shell과 Phase 계획은 `Draft`, 분석 taxonomy는 `Discussion` 상태다.
- 전체 구현 순서 문서는 `Draft`, LLM Gateway 경계는 `Proposed` 상태다.
- Slice 0.1~0.5가 구현됐다: payload, provider/fake, error envelope, transport mapping, fake-transport llama.cpp client.
- Slice 0.6 httpx adapter와 mock contract가 구현됐다. actual adapter live smoke는 독립 검증 환경에서 완료됐다.
- Git repository이며 Slice 0.6 httpx adapter가 구현·검증·커밋됐다.
- Slice 0.1~0.5의 F1/F2 조건이 delta 독립 재검증으로 폐쇄됐고 조건부 합격이 합격으로 승격됐다.
- flat loop 종료 decision, tool registry, budget policy, task별 completion criteria 계약이 `docs/plans/flat-loop-gate.md`에 확정됐다. 숫자 기본 한도만 후속(benchmark 이후)이다.
- Gateway optional `usage`→0과 token budget의 충돌은 usage/count 필수화로 해소됐다. 누락은 `provider_invalid_response`, 명시적 0은 유효하다.
- Gateway가 compose에 독립 `gateway` 서비스로 편입됐다. compose는 llama.cpp 서버를 띄우지 않고, gateway 컨테이너가 `LLAMA_BASE_URL`의 외부 llama.cpp-compatible endpoint를 호출한다.

## Active Decisions

- 긴 `abstract.md` 원본은 보존한다.
- 구현 Phase를 계획의 주 축으로 사용하고 공통 설계 원칙은 별도 문서로 관리한다.
- Phase와 MVP를 서로 다른 축으로 관리한다.
- 아이디에이션과 계획이 충돌하면 임의로 구현하지 않고 사용자 결정을 받는다.
- MVP는 계정/인증이 없는 단일 사용자 시스템이며 프로젝트 경계는 `project_id`로 유지한다.
- 기존 기억의 갱신은 AI가 직접 덮어쓰지 않고 검색·대조·Gate·검토·versioned upsert를 거친다.
- 아키텍처는 monorepo + modular Application + 독립 LLM Gateway/Worker로 승인됐다. Application API backend는 FastAPI다. Worker는 Application 코드/계약을 공유하되 느슨하게 연결하고, 나중에 별도 entrypoint/process로 분리 가능하게 둔다.
- frontend framework 최종 선택은 보류한다. 개인 로컬 시스템의 단일 서비스 UI로 충분할 수 있으므로, standalone frontend가 필요해질 때 React 또는 Vue를 기본 후보로 검토한다.
- 초기 local/personal runtime에서는 외부 queue 제품을 전제하지 않고 단순 in-process/background boundary로 시작한다.
- Dockerfile/Compose를 추가할 때는 빌드 캐시를 보존하는 레이어 순서를 우선한다. dependency manifest 복사·설치 레이어를 소스 복사보다 앞에 두고, 불필요한 전체 rebuild를 유발하는 `COPY .`/캐시 무효화 패턴을 피한다.
- Core SOT text/reference 계약은 raw snapshot 기준으로 승인됐다. offset은 raw Unicode code point, `content_hash`는 raw UTF-8 SHA-256, `normalized_text_hash`는 v1 필수 아님. MVP `source_blocks`는 Markdown heading/단독 `---`·`***` scene marker/빈 줄 paragraph 기반 deterministic split이며 AI 추론 split은 SOT에 넣지 않는다.
- adaptive chunking, semantic chunking, 길이 기반 episode/section chunking은 Phase 3 이후 파생 index 전략 후보로 둔다. MongoDB raw snapshot/source_ref 정본을 대체하지 않고 pointer/version/hash로 재조회 가능해야 한다.
- Core SOT persistence/retention 계약은 승인됐다. Docker 기반 정상 runtime은 MongoDB transaction 기본, non-transaction fallback은 local/test 제한 경로다. MVP는 명시적 version save only, autosave는 후속 결정이다. draft save는 `idempotency_key` 필수이며 같은 `project_id + draft_id + idempotency_key` 재시도는 같은 `draft_version`을 반환한다. project/draft는 archive하고 snapshot/version/source_ref는 보존한다.
- 분석 후보의 부분 승인, 부분 저장, 나머지 retry는 Phase 2/6 review action idempotency 계약에서 다루며 Slice 1 draft save idempotency와 섞지 않는다.
- MVP `source_ref` span은 하나의 `source_block` 안에 포함되어야 한다. 여러 block을 가로지르는 인용은 후속 후보/review 계약에서 별도로 다룬다.
- `/mnt/d/devel/gemma4_12b` commit `485c4e2`를 참조 구현으로 검토했으며 model/quant는 공식 QAT GGUF Q4_0으로 확인됐다. 실제 실행 hardware는 미확정이다.
- sub-agent spawn은 제외하고 bounded flat loop만 사용한다.
- 외부 `gemma4_12b`는 선택적 provenance이며 현재 repo runtime dependency가 아니다.
- 외부 서버 수정은 완료됐고 direct live endpoint `192.168.1.29:9080`에서 검증된 이력이 있다. 현재 repo compose 기본값은 머신 고정 IP가 아니라 Docker host 기준 `http://host.docker.internal:9080`이며, 다른 endpoint는 `LLAMA_BASE_URL`로 override한다.
- direct curl smoke는 성공했고, actual adapter live smoke는 독립 검증 환경에서 완료됐다.
- flat loop 종료 decision 7종(completed/awaiting_review/blocked/budget_exhausted/invalid_tool_arguments/tool_error/provider_error)을 확정했고, Loop/Analysis/Context Gate는 다른 층위(직교)로 병합하지 않는다.
- Loop의 `needs_review`를 `awaiting_review`로 rename(Analysis candidate status 충돌 해소), `provider_error`는 umbrella + Gateway 5 literal은 trace 보존, `completed`는 loop 종료 상태만(domain Gate 통과 별개)으로 정했다.
- flat loop registry는 Application/Worker 소유, task별 서버 allowlist, strict JSON Schema validation, read-only v1 tool 6종을 사용한다. `project_id`는 모델 인자가 아니라 신뢰된 실행 context에서 주입한다.
- `analysis_compare`는 5종, `context_search`는 3종 tool을 허용하고 `writing_generate`는 tool을 허용하지 않는다. compare/validate tool은 preflight이며 독립 domain Gate를 대체하지 않는다.
- budget은 iteration/wall-clock/total-token/tool-call/repeated-call 5차원을 사용한다. retry도 같은 budget을 소비하며, 초과는 성공으로 위장하지 않는다.
- budget/retry production 숫자 기본값은 Gemma Q4 benchmark 뒤에 확정한다. 그전 contract test는 명시값을 주입한다.
- completion 판정은 하이브리드(구조 조건 AND self-report)다. self-report는 loop 종료 채널의 `finalize` vs `defer` 결정이며 candidate status(산출물 데이터 채널)와 직교한다. `analysis_compare`의 부분 모호는 run `completed`+candidate status, tool 없는 `writing_generate`는 산출물 모호 `defer` 시 `awaiting_review`. completion matrix는 `task × {completed, awaiting_review}` 횡일관 2행으로 양방향 lock(독립 검증 R1/R2/R3 보강 완료).
- self-report wire 형식은 provider 응답 JSON object의 top-level `self_report` field다. 값은 정확히 `finalize` 또는 `defer`이고, 산출물 내부 nested `self_report`는 종료채널이 아니다.
- AgentLoopRunner A1/A2/A3가 구현됐다. `services/application/app/agent_loop/`에 `LoopDecision`(7종), `BudgetPolicy`(5차원 budget + retry cap + allows_tools)/`BudgetTracker`(F1 usage 방어), `ToolRegistry`(profile allowlist·strict arguments·canonical signature), `judge_completion`(completed/awaiting_review 하이브리드 판정), `resolve_retry`/`next_step_budget_decision`(retry 우선순위·budget→budget_exhausted 매핑)을 fake/인프라 없이 양방향 회귀로 잠갔다.
- flat loop 종료 decision 합성 원시가 A3로 잠겼고 독립 검증 합격 후 I1/I3를 보강했다. self-report는 `SelfReport`(FINALIZE/DEFER) enum 주입이고 wire 형식은 parser slice에서 확정. retry cap은 `BudgetPolicy.provider_retry_cap`/`tool_retry_cap`(0 이상)으로 실현됐다(검증 I1 폐쇄). I2(runner 합성 순서)는 provider composition runner slice에서 forward-lock 됐다.
- self-report 종료채널 parser slice가 구현됐다. provider 응답 `content`는 JSON object이고 top-level `self_report` field 값은 정확히 `finalize`/`defer`만 허용한다. 누락·malformed/non-object JSON·non-string·case variant·artifact nested `self_report`는 `InvalidSelfReport(decision=provider_error)`다.
- minimal `AgentLoopRunner` provider composition slice가 구현됐다. provider 호출 전 budget check → iteration 기록 → provider call/retry → usage 기록 → post-accounting budget check → `parse_self_report_payload` → `judge_completion` 순서를 연결한다. token overrun은 completion 전에 `budget_exhausted`, provider retry는 iteration budget을 소비한다. 실제 domain tool handler와 task별 artifact schema 평가는 Slice 1·3 이후 범위다.
- agent_loop 계약층(A1/A2/A3/parser/provider composition)은 현재 더 진행하지 않는다. tool-call branch는 Gateway tool-call parsing 미구현, model tool-call wire format 미계약, `ProviderTurnResult`가 terminal content만 받는 구조라는 3중 상류 의존이 있어 지금 구현하면 wire를 추측하게 된다. `artifact_present`도 Slice 2A/4/5 payload schema가 확정될 때 profile별로 교체한다.
- `docs/system-contract-sot.md`는 2026-06-26 사용자 결정으로 `Approved` v1.0이 됐다. 승인 범위는 정본 계약 인덱스와 문서 우선순위이며, 미확정 항목은 계속 추측 구현 금지다.
- 2026-06-26 Slice A 실행 경계 결정으로 `docs/system-contract-sot.md`가 v1.1이 됐다. monorepo+독립 Gateway, FastAPI backend, 느슨하게 분리 가능한 Worker 경계가 승인됐다.
- 2026-06-26 Slice B text/reference 결정으로 `docs/system-contract-sot.md`가 v1.2가 됐다. Slice 1 착수는 transaction/idempotency/save mode/delete policy 결정 뒤 진행한다.
- 2026-06-26 Slice C persistence/retention 결정으로 `docs/system-contract-sot.md`가 v1.3이 됐다. Slice 1 Core SOT 착수 전 결정은 해소됐다.
- 2026-06-26 Slice 1 최소 구현 맛보기 완료: `services/application/app/core_sot/`에 domain models, deterministic splitter/hash/source_ref, in-memory repository/service를 추가했고 `services/application/app/main.py`에 FastAPI shell(health/project/draft/save)을 추가했다. Docker compose/export/editor shell은 아직 미구현이다.
- 2026-06-28 Slice 1 MongoDB adapter 결정: Mongo adapter는 real pymongo + live Mongo 통합 테스트(미가용 시 skip), 드라이버는 pymongo(sync). 이유: transaction을 실제로 검증해야 하고(mongomock은 transaction 미지원), 로컬 단일 사용자 MVP에는 sync가 단순. 트레이드오프로 통합 테스트 층은 인프라를 요구하지만 기본 단위 스위트는 skip-aware로 인프라 없이 실행된다. service↔storage는 method 기반 `CoreSotRepository` Protocol로 분리했고 idempotency race는 `DuplicateSaveRequest`로 처리한다.
- 2026-06-28 Mongo adapter 재검증(R2) 사용자 결정: non-transaction fallback은 single-writer 전용으로 SoT v1.4에 명시(동시성 안전은 transaction 기본 경로 담당). 구현은 유지하고 계약만 명확화했다. 동시성이 필요해지면 후속에서 (a) concurrent-safe 보강을 재검토한다.
- 2026-06-28 archive 읽기전용 명문화 사용자 결정(SoT v1.5, rename_api.md R1): archive = 읽기 허용 + 본문 쓰기(draft 생성·version 저장)·메타데이터 수정(rename) 차단(409). SOT 본문은 archive 무관 항상 불변이라 "archived 본문 수정" 연산은 없음. write-level 다단계 프레임워크는 과설계로 채택하지 않고 연산 카테고리 prose로 정리. unarchive/상태전이는 범위 밖(차단 한정). source_ref 생성은 immutable snapshot 파생 주석이라 archived에서도 허용(사용자 #1 결정), idempotency·candidate archived 정책은 Phase 2/6.
- Core SOT minimal skeleton 독립 검증은 조건부 합격이었다(`docs/verifications/2026-06-26/core_sot_minimal_skeleton.md`). C1(`***`, `##`, `archive_project` 회귀), C2(known SHA-256 vector), C3(within-block source_ref 계약 명시)는 보강 완료됐다.
- Core SOT가 실제 MongoDB 저장소에 연결됐다(2026-06-28). method 기반 `CoreSotRepository` Protocol + pymongo(sync) `MongoCoreSotRepository`가 transaction 경로(기본)와 non-transaction fallback(retry guard·orphan cleanup·ordered write)을 구현하고, idempotency는 `draft_versions` unique index로 강제된다. skip-aware live 통합 테스트 17개가 단일 노드 replica set에서 통과했다.
- Application + MongoDB(replica set) Docker 런타임이 추가됐다(2026-06-28). `services/application/Dockerfile`(cache-friendly layer)·`docker-compose.yml`(mongo replica set healthcheck로 rs.initiate idempotent + application + application healthcheck)·`.dockerignore`. `docker compose up` 후 transaction 경로로 API save/replay end-to-end 검증 완료.
- LLM Gateway client Docker 런타임이 추가됐다(2026-06-28). `services/llm_gateway/Dockerfile`(cache-friendly layer)·`services/llm_gateway/app/main.py`(FastAPI shell: `/health/live`, `/health/ready`, `/v1/generate`)·compose `gateway` service. 모델 서버는 별도 운영이며 compose는 `LLAMA_BASE_URL`로 외부 llama.cpp-compatible endpoint만 가리킨다. gateway image build와 liveness/health smoke 통과. 검증 후 provider error 5종→HTTP status 매핑을 모두 gateway app test에서 lock했다.
- Core SOT 후속 Phase 재사용 fixture가 추가됐다(2026-06-28, plan 01 최소 산출물 #7 완료). `tests/fixtures/core_sot.py`가 deterministic raw text, expected hash/block/source_ref matrix, `build_core_sot_fixture()`를 제공한다. 검증 후 `ExpectedBlock.block_index` direct field와 한글 multibyte code point offset 회귀를 보강했다. Analysis candidate fixture는 Phase 2 schema 확정 전이라 의도적으로 제외했다.
- project/draft list/get API가 추가돼 Core SOT round-trip이 완성됐다(2026-06-28). `GET /projects`·`/projects/{id}`·`/projects/{id}/drafts`·`/projects/{id}/drafts/{draft_id}`. project_id 격리·404(없음/cross-project)·persisted round-trip을 API+Mongo(양 경로) 회귀로 잠갔다. rename은 후속.
- version read API가 추가됐다(2026-06-28). `GET /projects/{id}/drafts/{draft_id}/versions`(목록, version_number 순)·`GET .../versions/{version_id}`(단건 full read-back: snapshot raw_text + blocks text). version은 project_id·draft_id 일치 강제, 없음/cross-draft 404, payload에서 `idempotency_key` 의도적 제외. 분석/검색 Phase가 의존할 version/snapshot 재조회 표면이 열렸다.
- project/draft rename API가 추가됐다(2026-06-28). `PATCH /projects/{id}`·`PATCH /projects/{id}/drafts/{draft_id}`. 없음/cross-project 404, archived rename은 409(쓰기차단 계약).
- archive API endpoint가 추가돼 Core SOT CRUD가 API로 완성됐다(2026-06-28). `DELETE /projects/{id}`·`DELETE /projects/{id}/drafts/{draft_id}` → archive(soft delete, §115). archived 200 반환, 없음/cross-project 404, 재archive idempotent. 이로써 project/draft는 create·list·get·rename·archive 전부 API로 제공된다.
- SourceRef persistence가 추가돼 Slice 1이 마무리됐다(2026-06-28, R3 폐쇄). `SourceRef`에 `id`/`project_id`를 더하고 `create_source_ref`가 `source_refs` collection에 persist, `get_source_ref`는 project_id 격리를 강제한다. archive 후 source_ref 보존을 in-memory+Mongo(양 경로) 회귀로 잠갔다(SoT §113 충족, 계약 변경 없음). source_ref ↔ candidate 연결은 Phase 2 범위.
- Mongo index setup 잔여 회귀가 보강됐다(2026-06-28). `ensure_indexes()`는 현재 query path를 지탱하는 required index 2종(`uniq_save_request`, `blocks_by_snapshot`)을 생성하고, 기존 충돌 index 등 Mongo `OperationFailure`는 stable `MongoRepositorySetupError`로 표면화한다. 검증 후 현재 query path가 없는 `source_refs_by_snapshot` speculative index는 제거했고 SoT v1.5.1에 명확화했다.
- Gemma Q4 benchmark harness가 추가됐다(2026-06-28). `scripts/benchmark_llm_provider.py`가 외부 llama.cpp-compatible endpoint를 대상으로 short smoke, JSON extraction, scene continuation case를 반복 실행하고 latency/token/error summary JSON을 출력한다. 검증 후 CLI fake-runner wiring, warmup failure 기록(`iteration=0`), report field schema를 보강했다. 실제 endpoint benchmark와 budget/retry production 기본값 확정은 아직 남아 있다.
- Phase 2A 착수 최소 계약이 승인됐다(2026-06-29, SoT v1.6). `docs/plans/02-analysis-kickoff-decisions.md`는 최소 taxonomy 3종(`character_observation`, `event_observation`, `open_question_observation`), provenance `source_observed`/`ai_inferred`, Phase 2A `create` only, `needs_review` 고정, confidence range만 강제, `create_source_ref` primitive non-idempotent 유지 + candidate/job 저장층 idempotency 소유, 2A/2B milestone 분리를 확정한다. 후속 taxonomy 확장을 염두에 두되 첫 slice에서 넓은 taxonomy를 추측 구현하지 않는다.
- Phase 2A domain model + in-memory repository가 구현됐다(2026-06-29). `services/application/app/analysis/`에 `AnalysisJob`/`AnalysisTask`/`AnalysisCandidate`, repository Protocol, in-memory repository/service를 추가했다. job idempotency(`project_id + snapshot_id + idempotency_key`), candidate retry idempotency(`project_id + task_id + logical_key`), project isolation, `needs_review` 고정, confidence range, approved literal runtime validation, same source span의 다른 logical candidate 허용을 18개 회귀로 잠갔다. 독립 검증 조건 C1(NaN confidence reject), C2(action≠`create` 회귀), C3(`logical_key` 임시 identity 계약 명시)를 보강했고 전체 discovery 241개 통과(27 skip).
- Phase 2A Snapshot Loader + candidate source validation이 구현됐다(2026-06-29). `CoreSotSourceAdapter`가 같은 project의 snapshot raw text/hash/block ids를 로드하고, `AnalysisService`가 resolver 구성 시 `CandidateSourceAnchor(source_ref_id, start_offset, end_offset, quote, content_hash)`를 Core SOT `SourceRef`와 대조한다. source_ref 없음/cross-project/span mismatch/quote mismatch/hash mismatch/source_ref_ids-anchor mismatch/source_anchors 누락을 7개 회귀로 잠갔다. 전체 discovery 248개 통과(27 skip).
- Phase 2A 최소 taxonomy schema + fake-provider extraction adapter가 구현됐다(2026-06-29). `character_observation {name, observation}`, `event_observation {event}`, `open_question_observation {question}`만 허용하고 field는 모두 non-empty string이다. `AnalysisExtractionAdapter`는 provider content의 top-level `{candidates: [...]}` JSON object를 파싱해 approved literal/provenance/confidence/source_anchors/payload를 검증하고, `candidate_type + payload + source_anchors` canonical JSON SHA-256으로 `logical_key`를 만든다. 독립 검증 G1/D1 보강으로 `source_anchors`는 identity에서 unordered set으로 정규화한다(순서·동일 anchor 중복 무시, 다른 anchor 내용은 별도 identity). focused 32개 회귀와 전체 discovery 255개(27 skip)를 통과했다.
- Phase 2A extraction runner가 구현됐다(2026-06-29). `AnalysisExtractionRunner`는 source validation이 구성된 `AnalysisService`만 받으며, `AnalysisJob` idempotent 생성/재사용 → Snapshot Loader → provider extraction → `AnalysisTask` 생성/재사용 → 전체 draft 사전 검증 → candidate 저장 순서로 실행한다. Task는 `project_id + job_id + candidate_type`으로 재사용해 same job retry에서 candidate idempotency의 `task_id`가 흔들리지 않는다. invalid logical_key/source/schema draft가 있으면 candidate write를 시작하지 않고, 같은 run의 duplicate `(task_id, logical_key)` draft는 1개로 정규화한다. focused 39개와 전체 discovery 262개(27 skip)를 통과했다.
- Phase 2A Analysis Mongo repository/persistence가 구현됐다(2026-06-29). `MongoAnalysisRepository`는 `analysis_jobs`, `analysis_tasks`, `analysis_candidates`를 저장하고 required indexes `uniq_analysis_job_request`, `uniq_analysis_task_request`, `uniq_analysis_candidate_request`, `analysis_candidates_by_job`를 설치한다. Runner candidate write는 `record_candidates()` batch 경계를 통해 저장소에 전달되며, transaction 경로는 한 트랜잭션 commit, fallback은 single-writer local/test 전용 rollback(이번 시도 candidate `_id` 정리)으로 candidate 부분 저장을 막는다. Local live Mongo 미가용 환경에서는 새 통합 6개가 skip된다.
- Phase 2A Analysis Mongo persistence 독립 검증 조건부 합격의 C1/C2를 보강했다(2026-06-29). Live Mongo replica set 실행에서 드러난 `insert_many` duplicate `BulkWriteError` 누출을 `DuplicateAnalysisCandidateRequest` 매핑으로 수정했고, fallback/transaction 통합 6개가 실제 Mongo에서 통과했다. `record_candidates()` intra-batch 동일 `project_id + task_id + logical_key` request는 idempotent replay로 정규화한다고 SoT v1.6.7/plan에 명시하고 focused 회귀를 추가했다.
- `.gitignore`가 보강됐다(2026-06-29). Local agent state(`.agents/`, `.claude/`, `.codex/`, `.serena/`)와 Python cache/test cache, virtualenv, local env, build/editor/OS/log/tmp 산출물을 ignore한다.
- Phase 2A candidate write-error 분류가 정밀화됐다(2026-06-29, SoT v1.6.8). `_is_duplicate_key_error` helper로 duplicate-key(code `11000`) 충돌만 `DuplicateAnalysisCandidateRequest`로 매핑하고, duplicate가 아닌 `BulkWriteError`/`PyMongoError`는 원본 타입을 보존한다(인프라 오류 오표기 방지). fallback은 매핑 여부와 무관하게 이번 시도 candidate `_id`를 먼저 정리한다. 인프라 없는 fake 기반 회귀 4종(`tests/test_analysis_mongo_error_mapping.py`)이 transaction/fallback × duplicate/non-duplicate를 양방향 lock하고, live Mongo duplicate 경로 6개는 그대로 통과한다. 직전 독립 재검증의 비차단 Issue #1/#2를 닫았다.

## Next Tasks

1. Slice 1 잔여 회귀 후보: archive 후 파생 인덱스 stale 이벤트. Phase 3 indexing 계약이 Draft라 현재는 구현하지 않는다. (fallback 동시성 race는 SoT v1.4 single-writer 제약으로 contract out 됨; 동시성 필요 시에만 (a) 보강 재검토.)
2. Phase 2A 다음 구현 slice는 Application/Worker wiring 또는 Analysis job/task 상태 전이 중 먼저 진행할 쪽을 계약화한 뒤 시작한다. Job/task 실패 상태 저장은 아직 미확정이므로 구현 전 문서화가 필요하다.
3. Application/Worker가 gateway `/v1/generate`를 호출하는 runtime wiring은 Phase payload/tool handler와 model tool-call wire format이 확정된 뒤 별도 slice로 구현한다.
4. runner domain tool-call branch는 Gateway tool-call response parsing + model tool-call wire format + Phase payload/tool handler가 확정된 뒤 별도 slice로 구현한다.
5. task별 artifact schema 평가(`artifact_present`)는 Slice 2A/4/5 payload schema 확정 시 profile별로 교체한다.
6. 실제 Gemma/llama.cpp endpoint에서 `scripts/benchmark_llm_provider.py` 실행 후 budget/retry production 숫자 기본 한도 확정(retry cap 구조는 `BudgetPolicy`에 폐쇄됐고 숫자 기본값만 남음).

## Verification

- 계획 문서의 상대 링크와 원문 추적표 확인
- tool registry 계약과 Phase 2/4/5 연결 문구 및 양방향 boundary matrix 확인
- tool registry 계약 독립 검증 합격: `docs/verifications/2026-06-24/flat_loop_tool_registry.md`
- Gateway usage/count 누락 거절과 명시적 0 수용 focused regression 확인
- usage 필수화 후 actual adapter live smoke 재통과: content `연결 확인 완료`, finish `stop`, usage `23/5/28`
- 각 Phase 문서의 필수 planning section 확인
- 원본 `docs/abstract.md` 본문 보존 확인
- Product Shell과 analysis taxonomy의 계획 링크 및 Phase 연결 확인
- 구현 slice의 선후 관계와 LLM Gateway contract/model-test 분리 확인
- 현재 repo contract test 44개 통과. optional usage lock은 사용자 결정으로 missing-usage rejection으로 반전됐고 명시적 0 수용 guard는 유지됨
- 참조 repo unit contract test 8개 통과; 정책상 실모델 smoke는 보류
- Slice 0.1~0.5 독립 검증(2026-06-24): 조건부 합격. 기록 `docs/verifications/2026-06-24/llm_gateway_slice_0_1_to_0_5.md`. 당시 조건은 F1(기본값 True 미고정)·F2(spec-silent 거부의 계약 지위)였고 현재 구현 보강은 완료됐다.
- F1/F2 구현 보강 완료, delta 독립 재검증 합격(2026-06-24): F1 양방향 변이 증명(else False→true-test FAIL, else True→false-test FAIL), F2 request/response precondition이 `llm-gateway.md`에 명문화되고 13개 delta branch가 회귀에 1:1 매핑, live smoke 6항목 재실행 일치. 기록 `docs/verifications/2026-06-24/llm_gateway_f1_f2_closure.md`. 조건부 합격을 합격으로 승격.
- direct live smoke: health ok, model QAT GGUF Q4_0/context 8192, non-thinking 한국어 completion 성공
- Slice A1(decision+budget) 독립 검증(2026-06-24): 합격. 63/63 재현, 변이 증명 양방향·복원 정확·코드↔계약 line 단위 일치 입증, blocking 없음. F4(경계 테스트) 즉시 보강해 65개, F1(Gateway→budget usage 방어)은 A3로 이월. 기록 `docs/verifications/2026-06-24/agent_loop_a1_decision_budget.md`
- Slice A2(tool registry+strict arguments+signature) 자체 회귀(2026-06-25): focused 20개 통과, 전체 85개 통과. pattern sweep에서 위험한 중복 구현 없음.
- Slice A2 독립 검증(2026-06-25): **합격**(조건부 → 승격). allowlist/registration/strict args/blocked-vs-invalid/signature는 계약 literal 그대로 정확하고 양방향 lock 됨. 독립 검증이 §33 "enum, bounds 적용" 명시와 구현의 enum/bounds 미검증 불일치를 실증 발견 → 사용자 결정(option a)으로 v1/A2 validator 범위를 `{required, type, additionalProperties, array items}`로 §33·plan §138·CHANGELOG에 명시 좁히고 enum/bounds는 keyword 사용 tool 등록 시점까지 deferred로 reconcile. triggered 조건: enum/bounds 사용 tool 첫 등록 시 검증+회귀 추가. 기록 `docs/verifications/2026-06-25/agent_loop_a2_registry.md`
- A2 독립 검증의 비차단 I2/I3는 후속 보강 완료(2026-06-25): 중첩 object schema와 array `items`를 등록 시점에 재귀 검증하고 `_validate_arguments`의 `assert`를 명시 검사로 교체. enum/bounds deferral은 유지됨.
- Slice A3(completion 판정·retry/budget decision 합성·F1 usage 방어) 자체 회귀(2026-06-25): focused agent_loop 73개(decision 4 + budget 25 + registry 20 + completion 6 + resolution 18), 전체 117개 통과. 4곳 핵심 분기 변이로 양방향 lock 증명(completion `and/or`, retry cap 소진, token budget 매핑, F1 음수 수용).
- Slice A3 독립 검증(2026-06-25): **합격**. 117/117·per-module 6/18/25 재현, 4표면(completion/retry/budget 매핑/F1)이 정본 계약 literal 그대로 정확, 빈 칸 없음. 비차단 3건: I1(retry cap 정책 근원 부재=유일 spec↔impl 갭)·I3(exception uniformity 절반)은 보강으로 폐쇄, I2(runner 합성 순서)는 spec이 A3를 순수 원시로 규정해 runner slice forward-lock. 기록 `docs/verifications/2026-06-25/agent_loop_a3_completion_resolution.md`.
- A3 검증 후 보강(2026-06-25): I3(`InvalidBudgetPolicy.decision=BLOCKED`), I1(`BudgetPolicy`에 `provider_retry_cap`/`tool_retry_cap` 0 이상 추가, 사용자 결정 Option A). 전체 117→121, retry cap 검증 변이 증명(`_RETRY_DIMENSIONS=()` FAIL/복원 PASS).
- self-report parser slice 자체 회귀(2026-06-25): focused parser+completion 14개 통과, 전체 discovery 129개 통과. 패턴 sweep에서 기존 parser/default/nested-field 오인 경로 없음.
- self-report parser slice 독립 검증(2026-06-25): **합격**. 14/129 재현, boundary matrix 9분기 전 매핑(branch-level 빈 칸 없음), spec↔code 리터럴 행 단위 일치, 양방향 guard·패턴 sweep·예외→decision uniform 매핑 확인. 비차단 R1('오타' value-sample 비고 — 동일 분기가 이미 lock됨). 기록 `docs/verifications/2026-06-25/self_report_parser.md`
- self-report parser R1 보강 완료(2026-06-25): wrong well-formed literal `done` 거부 sample 추가. focused parser+completion 15개 통과, 전체 discovery 130개 통과.
- AgentLoopRunner provider composition 자체 회귀(2026-06-25): focused runner/parser/completion/resolution 40개 통과, 전체 discovery 137개 통과. I2 forward-lock(token overrun before completion, retry non-free) 양방향 회귀 포함.
- AgentLoopRunner provider composition 독립 검증(2026-06-25): **합격**. I2 forward-lock·retry non-free를 변이 증명으로 확인, 전체 137개 재현, spec↔code 리터럴·composition 순서 일치. 비차단 I1(focused 숫자 84→93)·I2(dead import)는 보강 완료. 기록 `docs/verifications/2026-06-25/agent_loop_provider_runner.md`
- System Contract SoT 최초 독립 검증(2026-06-25): **합격**. 당시 SoT가 인용한 literal(5 provider·5 Analysis·3 candidate·7 decision·6 tool·3 allowlist·budget 임계)·status·링크가 정본과 문자열 그대로 일치하고 enum/bounds deferral이 정확히 전파됨. 같은 묶음의 A2 I2/I3 비차단 권고도 코드+양방향 회귀로 폐쇄(registry 18→20, 전체 85/85). 비차단 risk R1(SoT↔plans/README precedence tree 불일치)도 검증자가 직접 reconcile로 폐쉄 — plans/README tree를 SoT 5-level과 통일하고 SoT를 정본 precedence로 defer. 기록 `docs/verifications/2026-06-25/system_contract_sot.md`
- Core SOT minimal skeleton 자체 회귀(2026-06-26): focused `python3 -m unittest tests.test_core_sot tests.test_application_api -v` 14개 통과, 전체 discovery 151개 통과. 잠근 범위: idempotent save, immutable snapshot/hash/block, known SHA-256 UTF-8 vector, `##` heading, `***` scene marker, source_ref quote/hash, within-block rejection, bool offset rejection, project_id isolation, project/draft archive preservation, FastAPI minimal flow.
- Core SOT MongoDB adapter 자체 회귀(2026-06-28): Mongo 미지정 시 전체 discovery 168개 중 17개 skip(OK), `CORE_SOT_TEST_MONGO_URI` 지정 시 168개 전부 통과. 단일 노드 replica set(`docker run ... mongo:7 --replSet rs0` + `rs.initiate`, `?directConnection=true`)에서 fallback/transaction 양 경로 17개 검증. 잠근 범위: save 후 snapshot/blocks/version 재구성, deterministic hash/blocks, idempotent replay 무중복, distinct key version 증가, unique index 중복 거절(`DuplicateSaveRequest`), project_id 격리, archive 보존, source_ref quote 재구성, fallback orphan cleanup, fallback retry guard(commit dependents 미삭제), transaction abort 후 partial write 잔류 없음. FastAPI app wiring smoke(env var Mongo)로 HTTP save/replay 확인.
- archive API endpoint 자체 회귀(2026-06-28): 전체 207개(Mongo 미연결 27 skip), replica set 연결 시 전부 통과. 잠근 범위: DELETE project archive(archived=true·읽기 유지·이후 쓰기 409), DELETE draft archive(409/읽기 200), project·draft 재archive idempotent 200, archived project 하위 draft archive 허용(over-strict guard·mutation 증명), 없음/missing draft/cross-project 404. 독립 재검증 조건부 합격→합격: Issue #1(archive_draft 상태전이 예외 미lock) over-strict guard + §115 :121 prose 명확화로 닫음, #2/#3 보강(`docs/verifications/2026-06-28/archive_api_endpoint.md`).
- project/draft rename API 자체 회귀(2026-06-28): 전체 201개(Mongo 미연결 27 skip), replica set 연결 시 전부 통과. 잠근 범위: rename round-trip(get 반영), 없음/cross-project draft→404, archived rename→409, project만 archive 시 rename_draft→409(분기 isolation·mutation 증명), draft만 archive 시 rename_project→200(should-fire), Mongo persisted rename(양 경로). 독립 재검증 조건부 합격→합격: Issue #1(rename_draft project.archived 분기 미lock) isolation test로 양방향 lock, #2/R2 보강(`docs/verifications/2026-06-28/rename_api.md`). R1(archived 쓰기차단의 SoT 명문화)은 사용자 결정 대기 권고.
- version read API 자체 회귀(2026-06-28): 전체 193개(Mongo 미연결 25 skip), replica set 연결 시 전부 통과. 잠근 범위: version list(version_number 순)+detail read-back(raw_text/block text 일치), idempotency_key 미노출(list+detail), 없는 version/draft→404, cross-draft/cross-project version→404, archived 후 version read 보존, Mongo persisted read-back(양 경로). 독립 재검증 조건부 합격→합격: Issue #1(project_id 격리 분기 미lock)을 inconsistent-state 주입 test로 양방향 lock(mutation 증명: 절 제거 시 FAIL), #2/#3/R2 보강(`docs/verifications/2026-06-28/version_read_api.md`).
- project/draft list/get API 자체 회귀(2026-06-28): 전체 185개(Mongo 미연결 23 skip), replica set 연결 시 전부 통과. 잠근 범위: project list+get round-trip, 없는 project→404, draft list+get+project 격리(B는 A draft 미노출, should-NOT-fire), cross-project/없는 project/없는 draft→404, 생성 순서 유지(in-memory+Mongo), archive된 project/draft도 list/get 가능(§113 read-allowed), Mongo persisted round-trip(양 경로). 독립 재검증 합격, 비차단 observation 3건은 모두 회귀로 폐쇄(`docs/verifications/2026-06-28/project_draft_list_get_api.md`).
- SourceRef persistence 자체 회귀(2026-06-28): Mongo 미연결 전체 176개(21 skip), 단일 노드 replica set 연결 시 Mongo 통합 21개 포함 전부 통과. 잠근 범위: source_ref persist+id 재조회, project_id 격리(NotFound), 존재하지 않는 id→NotFound, archive_project 후 §113 보존(in-memory + Mongo fallback/transaction 양 경로). pattern sweep: 생성-후-미persist 패턴은 source_ref가 마지막 gap이었고 나머지 엔티티는 이미 persist됨.
- SourceRef persistence 독립 재검증(2026-06-28): **합격**. 기록 `docs/verifications/2026-06-28/source_ref_persistence.md`. schema 변경 regression 없음·R3(§113 archive 보존) 폐쇄·spec-silent 판단 정당을 독립 재현으로 증명. 비차단 observation 3건 중 #1(missing-id→NotFound test 부재)은 회귀 추가로 폐쇄, #2/#3(archive 후 생성·idempotency 정책)은 Phase 2 추적(Next Tasks #5)으로 반영.
- Application + Mongo Docker 런타임 검증(2026-06-28): `docker compose build` 성공(deps→source 캐시 순서), `docker compose up` 후 mongo healthy·app `/health` ok·transaction 경로 API save/replay end-to-end(version 1, idempotent replay, `draft_versions`=1) 확인. `docker compose down -v`로 정리.
- LLM Gateway client Docker 런타임 검증(2026-06-28): focused gateway/provider/httpx 18개 통과(provider error 5종→HTTP status subTest 포함), `docker compose config` 통과, `COMPOSE_BAKE=false docker compose build gateway` 성공, `docker compose up -d gateway` 후 `/health/live` → `{"status":"ok"}` 및 container `healthy` 확인. 외부 llama.cpp readiness는 별도 운영 endpoint 의존이라 live smoke 범위에서 제외.
- Verification follow-up(2026-06-28): `docs/verifications/2026-06-28/gateway_compose.md` 합격 기록 반영. application API tests의 `fastapi.testclient.TestClient` hang을 test-only ASGITransport wrapper로 교체해 전체 discovery가 종료되게 했다.
- Core SOT reusable fixture 자체 회귀(2026-06-28): `python3 -m unittest tests.test_core_sot_fixture -v` 3개 통과, 전체 discovery 214개 통과(27 skip). 잠근 범위: deterministic raw snapshot hash, block index/kind/order/offset/text, source_ref quote/hash/project/block 연결, idempotent replay, multibyte Unicode code point offset.
- Mongo index setup 잔여 회귀(2026-06-28): `python3 -m unittest tests.test_core_sot_mongo_indexes -v` 2개 통과, `python3 -m py_compile services/application/app/core_sot/mongo_repository.py tests/test_core_sot_mongo_indexes.py` 통과, 전체 discovery 216개 통과(27 skip). 검증 후 O1/O2 보강으로 SoT v1.5.1에 required index/error mapping을 명시하고, query path 없는 `source_refs_by_snapshot` index를 제거했다. 잠근 범위: required index 2종 absent-index 생성 호출, conflicting pre-existing index의 `MongoRepositorySetupError` 매핑.
- Gemma Q4 benchmark harness 자체 회귀(2026-06-28): `python3 -m unittest tests.test_llm_benchmark_script -v` 7개 통과, `python3 -m py_compile scripts/benchmark_llm_provider.py tests/test_llm_benchmark_script.py` 통과, 전체 discovery 223개 통과(27 skip). 잠근 범위: success latency/token/tokens-per-second 기록, provider error literal/retryable 기록, warmup failure `iteration=0` 기록, invalid repeats/warmups 거절, CLI fake-runner wiring, per-case summary/report raw field shape.
- Core SOT MongoDB adapter 독립 재검증(2026-06-28): **조건부 합격 → R1 보강으로 합격 조건 충족**. 기록 `docs/verifications/2026-06-28/mongo_adapter_recheck.md`. 168개·양 경로 17개 재현, 핵심 persistence/retention 계약 양방향 lock 확인. R1(pymongo 미설치 시 discovery 깨짐) 해결: import try/except + skip, pymongo 차단 후 `errors=1`→`errors=0, skipped=17` 복원. R2(fallback 동시성 bug) 사용자 결정 option (b)로 single-writer 제약을 SoT v1.4/plan/adapter에 명시. R3(`source_refs` 미persist)는 SourceRef persistence slice 추적.
- completion criteria 계약 독립 검증(2026-06-24): 조건부 합격. 워커 보고·내부 일관성·cross-reference 4종 독립 확인, blocking 없음. 비차단 risk R1/R2(matrix 비대칭)·R3(self-report 정의 갭)를 소유자 결정으로 본 slice에서 즉시 보강했다. 기록 `docs/verifications/2026-06-24/completion_criteria_contract.md`
- Slice 0.6 독립 검증(2026-06-24): 합격. httpx MockTransport/proxy/close 경계 6개 회귀 통과, `except` 순서 load-bearing 가정 4종 검증. 독립 검증 환경에서 `HttpxJsonTransport` 경유 actual adapter live smoke 완료(content `연결 확인 완료`, finish_reason=stop). 기록 `docs/verifications/2026-06-24/llm_gateway_slice_0_6_httpx.md`
- Phase 2A source validation 자체 회귀(2026-06-29): `python3 -m unittest tests.test_analysis_source_validation tests.test_analysis_phase2a -v` 25개 통과, `python3 -m py_compile ...` 통과, 전체 discovery 248개 통과(27 skip).
- Phase 2A taxonomy schema/extractor 자체 회귀(2026-06-29): `python3 -m py_compile services/application/app/analysis/schema.py services/application/app/analysis/extractor.py services/application/app/analysis/service.py tests/test_analysis_extractor_schema.py tests/test_analysis_phase2a.py tests/test_analysis_source_validation.py` 통과, Slice3 보강 후 `python3 -m py_compile services/application/app/analysis/extractor.py tests/test_analysis_extractor_schema.py` 통과, `python3 -m unittest tests.test_analysis_extractor_schema tests.test_analysis_source_validation tests.test_analysis_phase2a -v` 32개 통과, 전체 discovery 255개 통과(27 skip). 잠근 범위: 3종 최소 payload schema 정상/거절, service 저장 경로 malformed payload 거절, fake-provider extraction adapter parsing, malformed provider content 거절, deterministic logical_key, over-collapse 방지, 같은 anchor set 순서 무관 identity, 동일 anchor 중복 정규화.
- Phase 2A extraction runner 자체 회귀(2026-06-29): `python3 -m py_compile services/application/app/analysis/runner.py services/application/app/analysis/service.py services/application/app/analysis/repository.py tests/test_analysis_runner.py tests/test_analysis_phase2a.py` 통과, Slice4 보강 후 `python3 -m py_compile services/application/app/analysis/runner.py services/application/app/analysis/service.py tests/test_analysis_runner.py` 통과, `python3 -m unittest tests.test_analysis_runner tests.test_analysis_extractor_schema tests.test_analysis_source_validation tests.test_analysis_phase2a -v` 39개 통과, 전체 discovery 262개 통과(27 skip). 잠근 범위: load→extract→validate→store 흐름, same job replay의 job/task/candidate idempotency, invalid logical_key/source/schema draft가 있을 때 candidate 부분 저장 금지, runner source validation 구성 강제, duplicate `(task_id, logical_key)` result dedupe.
- Phase 2A Analysis Mongo persistence 자체 회귀(2026-06-29): `python3 -m py_compile services/application/app/analysis/models.py services/application/app/analysis/repository.py services/application/app/analysis/service.py services/application/app/analysis/runner.py services/application/app/analysis/mongo_repository.py tests/test_analysis_mongo.py tests/test_analysis_mongo_indexes.py` 통과, `python3 -m unittest tests.test_analysis_runner tests.test_analysis_mongo_indexes -v` 8개 통과, `python3 -m unittest tests.test_analysis_mongo -v`는 live Mongo 미가용으로 6개 skip(OK). 잠근 범위: required analysis indexes, setup error mapping, runner batch write 경계, persisted round-trip/replay/batch rollback은 live Mongo 연결 시 fallback/transaction 양 경로에서 실행.
- Phase 2A candidate write-error 정밀화 자체 회귀(2026-06-29): `python3 -m unittest tests.test_analysis_mongo_error_mapping` 4개 통과, 전체 discovery 275개 통과(33 skip). over-broad 변이(helper 항상 True) 시 non-duplicate 재던지기 test 2개 FAIL → 양방향 lock 증명. throwaway replica set(port 27022)에서 live `tests.test_analysis_mongo` 6개 재통과로 duplicate(11000) 경로 무손상 확인.
- Phase 2A Analysis Mongo persistence 보강 독립 재검증(2026-06-29): **합격**. 기록 `docs/verifications/2026-06-29/analysis_mongo_persistence_hardening.md`. 선행 conditional pass의 C1(transaction/fallback all-or-nothing)을 throwaway replica set에서 live 6개 통과로 실행 증명, `BulkWriteError`(code 11000) 매핑을 변이 증명으로 load-bearing 확인(보강 전 `errors=2` 누출), C2 intra-batch dedupe(`batch_seen`) 회귀를 변이 증명으로 양방향 lock + SoT v1.6.7/plan literal 일치. pattern sweep: Core SOT `insert_many`는 `blocks_by_snapshot` non-unique라 동일 패턴이나 버그 아님. 전체 discovery 271 통과(33 skip) 재현. 비차단 Issue 2건(catch 정밀도/문서 배치)은 Next Tasks #7.
- Phase 2A Analysis Mongo persistence 검증 보강 자체 회귀(2026-06-29): 임시 `mongo:7 --replSet rs0` 컨테이너(port 27019)에서 `CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27019/?directConnection=true' python3 -m unittest tests.test_analysis_mongo -v` 첫 실행은 `BulkWriteError` 누출로 2 errors, 보강 후 6개 통과. `python3 -m unittest tests.test_analysis_phase2a tests.test_analysis_mongo_indexes tests.test_analysis_runner -v` 28개 통과, 전체 discovery 271개 통과(33 skip). 임시 컨테이너는 stop/rm 정리됨.

## Project Structure

```text
docker-compose.yml               # Slice 1 runtime: application + Mongo replica set + external-llama client gateway
.dockerignore                    # build context 최소화
.gitignore                       # local agent/tool state + Python/env/build/editor 산출물 제외
docs/
├── README.md                    # 문서 분류와 진입점
├── system-contract-sot.md       # 서비스 경계와 확정 계약 Approved SoT
├── abstract.md                  # 보존된 전체 아이디에이션 원본
├── *.md                         # 주제별 상세 아이디에이션
├── plans/
│   ├── README.md                # 계획 인덱스, 우선순위, Phase/MVP 관계
│   ├── 00-foundations.md
│   ├── product-shell.md         # 프로젝트/원고 관리와 내보내기
│   ├── analysis-memory-taxonomy.md # 분석 대상 및 갱신 논의안
│   ├── 02-analysis-kickoff-decisions.md # Phase 2A 착수 전 결정 브리프
│   ├── implementation-plan.md   # vertical slice와 검증 계획
│   ├── llm-gateway.md           # 모델 서빙 경계와 Gemma Q4 검증
│   ├── gemma4-reuse.md          # 기존 구현 선택 이관과 Loop Gate 보강
│   ├── flat-loop-gate.md        # flat loop decision/tool registry/budget policy 계약
│   └── 01-core-sot.md ~ 06-review-ui.md
└── daily_logs/
    ├── 2026-06-24/work_log.md
    ├── 2026-06-25/work_log.md
    ├── 2026-06-26/work_log.md
    ├── 2026-06-28/work_log.md
    └── 2026-06-29/work_log.md
services/
├── llm_gateway/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py             # FastAPI gateway shell: live/ready/generate
│       ├── payload.py          # portable llama.cpp payload contract
│       ├── provider.py         # provider protocol과 deterministic fake
│       ├── errors.py           # stable provider error envelope
│       ├── transport.py        # JSON transport/fake와 status error mapping
│       ├── client.py           # llama.cpp text completion provider
│       └── httpx_transport.py  # 실제 async HTTP JSON adapter
└── application/
    ├── requirements.txt        # FastAPI/pymongo/uvicorn dependency
    ├── Dockerfile              # cache-friendly application image (deps→source)
    └── app/
        ├── main.py             # FastAPI shell: health/project·draft create·list·get·rename·archive(DELETE)/version save·list·read (+Mongo wiring)
        ├── core_sot/
        │   ├── models.py       # Core SOT immutable dataclasses
        │   ├── splitter.py     # raw-text SHA-256 + deterministic source block split
        │   ├── repository.py   # CoreSotRepository Protocol + DuplicateSaveRequest
        │   ├── mongo_repository.py # pymongo(sync) adapter: transaction/fallback/idempotency
        │   └── service.py      # Core SOT service + in-memory repository skeleton
        ├── analysis/
        │   ├── models.py       # Phase 2A AnalysisJob/Task/Candidate + approved literals
        │   ├── repository.py   # AnalysisRepository Protocol
        │   ├── mongo_repository.py # pymongo(sync) adapter: analysis job/task/candidate persistence
        │   ├── schema.py       # 3종 taxonomy 최소 payload validator
        │   ├── extractor.py    # fake/provider extraction adapter + logical_key derivation
        │   ├── runner.py       # Snapshot Loader→provider extraction→candidate 저장 orchestration
        │   ├── source.py       # Core SOT snapshot/source_ref adapter
        │   └── service.py      # in-memory analysis repository/service + retry idempotency
        └── agent_loop/
            ├── budget.py       # BudgetPolicy(5차원 budget+retry cap)/BudgetTracker+F1 usage 방어(A1/A3)
            ├── completion.py   # SelfReport + judge_completion completed/awaiting_review(A3)
            ├── decision.py     # LoopDecision 종료 decision 7종(A1)
            ├── parser.py       # provider JSON content의 top-level self_report parser
            ├── registry.py     # ToolRegistry allowlist/strict args/signature(A2)
            ├── resolution.py   # resolve_retry + next_step_budget_decision(A3)
            └── runner.py       # minimal provider composition runner + trace
tests/
├── fixtures/
│   └── core_sot.py            # 후속 Phase 재사용 Core SOT fixture
├── test_llm_gateway_payload.py
├── test_llm_gateway_app.py
├── test_llm_provider.py
├── test_llm_provider_errors.py
├── test_llm_benchmark_script.py
├── test_llm_transport_mapping.py
├── test_llama_provider_client.py
├── test_httpx_transport.py
├── test_agent_loop_decision.py
├── test_agent_loop_budget.py
├── test_agent_loop_registry.py
├── test_agent_loop_completion.py
├── test_agent_loop_parser.py
├── test_agent_loop_runner.py
├── test_agent_loop_resolution.py
├── test_analysis_phase2a.py
├── test_analysis_extractor_schema.py
├── test_analysis_runner.py
├── test_analysis_source_validation.py
├── test_analysis_mongo_error_mapping.py
├── test_core_sot.py
├── test_core_sot_fixture.py
├── test_core_sot_mongo_indexes.py
├── test_core_sot_mongo.py
└── test_application_api.py
scripts/
├── smoke_llm_provider.py
└── benchmark_llm_provider.py
docs/verification_briefs/2026-06-24/
├── llm_gateway_slice_0_1_to_0_5.md
├── llm_gateway_f1_f2_live_smoke.md
└── llm_gateway_slice_0_6_httpx.md
docs/verifications/2026-06-24/
├── flat_loop_tool_registry.md
├── llm_gateway_slice_0_1_to_0_5.md
├── llm_gateway_slice_0_6_httpx.md
├── llm_gateway_f1_f2_closure.md
├── completion_criteria_contract.md
└── agent_loop_a1_decision_budget.md
```
