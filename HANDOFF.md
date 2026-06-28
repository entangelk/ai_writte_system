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
- 외부 서버 수정은 완료됐고 direct live endpoint `192.168.1.29:9080`을 사용할 수 있다.
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
- Core SOT minimal skeleton 독립 검증은 조건부 합격이었다(`docs/verifications/2026-06-26/core_sot_minimal_skeleton.md`). C1(`***`, `##`, `archive_project` 회귀), C2(known SHA-256 vector), C3(within-block source_ref 계약 명시)는 보강 완료됐다.
- Core SOT가 실제 MongoDB 저장소에 연결됐다(2026-06-28). method 기반 `CoreSotRepository` Protocol + pymongo(sync) `MongoCoreSotRepository`가 transaction 경로(기본)와 non-transaction fallback(retry guard·orphan cleanup·ordered write)을 구현하고, idempotency는 `draft_versions` unique index로 강제된다. skip-aware live 통합 테스트 17개가 단일 노드 replica set에서 통과했다.
- Application + MongoDB(replica set) Docker 런타임이 추가됐다(2026-06-28). `services/application/Dockerfile`(cache-friendly layer)·`docker-compose.yml`(mongo replica set healthcheck로 rs.initiate idempotent + application + application healthcheck)·`.dockerignore`. `docker compose up` 후 transaction 경로로 API save/replay end-to-end 검증 완료. gateway 서비스는 아직 compose에 미편입(외부 llama.cpp endpoint 의존).
- SourceRef persistence가 추가돼 Slice 1이 마무리됐다(2026-06-28, R3 폐쇄). `SourceRef`에 `id`/`project_id`를 더하고 `create_source_ref`가 `source_refs` collection에 persist, `get_source_ref`는 project_id 격리를 강제한다. archive 후 source_ref 보존을 in-memory+Mongo(양 경로) 회귀로 잠갔다(SoT §113 충족, 계약 변경 없음). source_ref ↔ candidate 연결은 Phase 2 범위.

## Next Tasks

1. gateway 서비스를 Dockerfile/compose에 편입(현재 application+Mongo만 compose에 있음; gateway는 외부 llama.cpp endpoint 의존이라 Slice 1 범위 밖이었음).
2. Slice 1 잔여 회귀 후보: index 부재/충돌 시 동작, archive 후 파생 인덱스 stale 이벤트. (fallback 동시성 race는 SoT v1.4 single-writer 제약으로 contract out 됨; 동시성 필요 시에만 (a) 보강 재검토.)
3. plan 01 최소 산출물 #7(후속 Phase 재사용 fixture)과 project/draft list/get API는 아직 미구현.
4. Slice 1 결정이 현재 SoT 정본 계약을 바꾸면 `docs/system-contract-sot.md` 계약 버전을 갱신하고 변경 이력에 사용자 결정 근거를 남긴다. (Mongo adapter는 persistence/retention v1.3을 구현으로 충족, 재검증 R2 결정으로 fallback single-writer 제약이 v1.4로 추가됨. SourceRef persistence는 v1.4 §113을 구현으로 충족.)
5. runner domain tool-call branch는 Gateway tool-call response parsing + model tool-call wire format + Phase payload/tool handler가 확정된 뒤 별도 slice로 구현한다.
6. task별 artifact schema 평가(`artifact_present`)는 Slice 2A/4/5 payload schema 확정 시 profile별로 교체한다.
7. Gemma Q4 benchmark 후 budget/retry production 숫자 기본 한도 확정(retry cap 구조는 `BudgetPolicy`에 폐쇄됐고 숫자 기본값만 남음).

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
- SourceRef persistence 자체 회귀(2026-06-28): Mongo 미연결 전체 175개(21 skip), 단일 노드 replica set 연결 시 175개 전부 통과(Mongo 통합 21개). 잠근 범위: source_ref persist+id 재조회, project_id 격리(NotFound), archive_project 후 §113 보존(in-memory + Mongo fallback/transaction 양 경로). pattern sweep: 생성-후-미persist 패턴은 source_ref가 마지막 gap이었고 나머지 엔티티는 이미 persist됨.
- Application + Mongo Docker 런타임 검증(2026-06-28): `docker compose build` 성공(deps→source 캐시 순서), `docker compose up` 후 mongo healthy·app `/health` ok·transaction 경로 API save/replay end-to-end(version 1, idempotent replay, `draft_versions`=1) 확인. `docker compose down -v`로 정리.
- Core SOT MongoDB adapter 독립 재검증(2026-06-28): **조건부 합격 → R1 보강으로 합격 조건 충족**. 기록 `docs/verifications/2026-06-28/mongo_adapter_recheck.md`. 168개·양 경로 17개 재현, 핵심 persistence/retention 계약 양방향 lock 확인. R1(pymongo 미설치 시 discovery 깨짐) 해결: import try/except + skip, pymongo 차단 후 `errors=1`→`errors=0, skipped=17` 복원. R2(fallback 동시성 bug) 사용자 결정 option (b)로 single-writer 제약을 SoT v1.4/plan/adapter에 명시. R3(`source_refs` 미persist)는 SourceRef persistence slice 추적.
- completion criteria 계약 독립 검증(2026-06-24): 조건부 합격. 워커 보고·내부 일관성·cross-reference 4종 독립 확인, blocking 없음. 비차단 risk R1/R2(matrix 비대칭)·R3(self-report 정의 갭)를 소유자 결정으로 본 slice에서 즉시 보강했다. 기록 `docs/verifications/2026-06-24/completion_criteria_contract.md`
- Slice 0.6 독립 검증(2026-06-24): 합격. httpx MockTransport/proxy/close 경계 6개 회귀 통과, `except` 순서 load-bearing 가정 4종 검증. 독립 검증 환경에서 `HttpxJsonTransport` 경유 actual adapter live smoke 완료(content `연결 확인 완료`, finish_reason=stop). 기록 `docs/verifications/2026-06-24/llm_gateway_slice_0_6_httpx.md`

## Project Structure

```text
docker-compose.yml               # Slice 1 runtime: application + Mongo replica set
.dockerignore                    # build context 최소화
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
│   ├── implementation-plan.md   # vertical slice와 검증 계획
│   ├── llm-gateway.md           # 모델 서빙 경계와 Gemma Q4 검증
│   ├── gemma4-reuse.md          # 기존 구현 선택 이관과 Loop Gate 보강
│   ├── flat-loop-gate.md        # flat loop decision/tool registry/budget policy 계약
│   └── 01-core-sot.md ~ 06-review-ui.md
└── daily_logs/
    ├── 2026-06-24/work_log.md
    ├── 2026-06-25/work_log.md
    ├── 2026-06-26/work_log.md
    └── 2026-06-28/work_log.md
services/
├── llm_gateway/
│   ├── requirements.txt
│   └── app/
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
        ├── main.py             # FastAPI shell: health/project/draft/version save (+Mongo wiring)
        ├── core_sot/
        │   ├── models.py       # Core SOT immutable dataclasses
        │   ├── splitter.py     # raw-text SHA-256 + deterministic source block split
        │   ├── repository.py   # CoreSotRepository Protocol + DuplicateSaveRequest
        │   ├── mongo_repository.py # pymongo(sync) adapter: transaction/fallback/idempotency
        │   └── service.py      # Core SOT service + in-memory repository skeleton
        └── agent_loop/
            ├── budget.py       # BudgetPolicy(5차원 budget+retry cap)/BudgetTracker+F1 usage 방어(A1/A3)
            ├── completion.py   # SelfReport + judge_completion completed/awaiting_review(A3)
            ├── decision.py     # LoopDecision 종료 decision 7종(A1)
            ├── parser.py       # provider JSON content의 top-level self_report parser
            ├── registry.py     # ToolRegistry allowlist/strict args/signature(A2)
            ├── resolution.py   # resolve_retry + next_step_budget_decision(A3)
            └── runner.py       # minimal provider composition runner + trace
tests/
├── test_llm_gateway_payload.py
├── test_llm_provider.py
├── test_llm_provider_errors.py
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
├── test_core_sot.py
├── test_core_sot_mongo.py
└── test_application_api.py
scripts/
└── smoke_llm_provider.py
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
