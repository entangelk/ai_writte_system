# Work Log — 2026-07-03

## Goals

- HANDOFF와 2026-07-02 work log를 읽고 다음 작업을 진행한다.
- Phase 3B automatic sync/outbox 브리프에 대한 사용자 결정을 반영한다.
- 브리프의 미구현/미분석 항목 4, 5, 6을 분석해 첫 code slice 전에 추측이 남지 않게 한다.

## Completed work

### Phase 3B sync/outbox 브리프 승인 결정 반영

- 변경 파일: `docs/plans/03-index-sync-outbox-decisions.md`, `docs/plans/03-indexing.md`, `docs/system-contract-sot.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-03/work_log.md`.
- 사용자 결정에 따라 브리프 상태를 owner-approved pre-implementation 상태로 바꿨다.
- 첫 automatic event source는 archive events(`project_archived`, `draft_archived`)로 채택했다.
- 다만 사용자는 `analysis_completed`가 장기적으로 가장 맞는 흐름이라고 보았으므로, 첫 slice는 archive events에 한정하되 event/source schema가 후속 `analysis_completed`를 닫지 않도록 문서화했다.
- Delivery는 Mongo outbox/polling으로 확정하고, 외부 queue는 현재 로컬 1인 프로젝트 단계에서 제외했다.
- 저장 단위는 기존 추천안 A(`index_sync_logs` 단일)가 아니라 B(`index_sync_outbox` + `index_sync_logs` 분리)로 확정했다. 두 collection은 `sync_request_id`로 조인한다.
- SoT를 v1.6.25로 올려 이 사용자 결정을 정본 계약 인덱스에 반영했다.

### 브리프 누락 항목 4/5/6 보강

- 변경 파일: `docs/plans/03-index-sync-outbox-decisions.md`, `docs/plans/03-indexing.md`, `docs/system-contract-sot.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-03/work_log.md`.
- 항목 4 archive 반영 방식은 hard delete/tombstone-or-status/stale-validation 선택지로 정리했다.
- 채택안은 첫 slice에서 outbox 기록까지만 처리하고, 실제 derived index mutation은 하지 않는 것이다. 현재 사용 안전성은 Phase 3A `validate_source_block_record()` guard가 담당한다. Worker/adapter slice가 열리면 hard delete보다 tombstone/status update를 우선 검토한다.
- 항목 5 retry/backoff는 retry 없음/bounded local retry metadata/external queue retry policy 선택지로 정리했다.
- 채택안은 outbox schema가 `attempt_count`, `max_attempts`, `next_attempt_at`, `last_error`, `status`를 담을 수 있게 하되, retry 실행과 backoff 숫자, claim timeout, retryable taxonomy는 worker slice에서 확정하는 것이다.
- 항목 6 fake vector 단계는 persistent log only/Chroma adapter 동시 구현/Chroma+Elasticsearch 동시 구현 선택지로 정리했다.
- 채택안은 persistent outbox/log 계약만 먼저 잠그고, actual ChromaDB adapter, embedding model/dimension, Elasticsearch analyzer는 후속 결정으로 남기는 것이다.

### Phase 3B archive outbox 첫 code slice 구현

- 변경 파일: `services/application/app/indexing/models.py`, `services/application/app/indexing/service.py`, `services/application/app/indexing/mongo_repository.py`, `services/application/app/main.py`, `tests/test_indexing_phase3a.py`, `tests/test_indexing_mongo_indexes.py`, `tests/test_application_api.py`, `docs/plans/03-index-sync-outbox-decisions.md`, `docs/plans/03-indexing.md`, `docs/system-contract-sot.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-03/work_log.md`.
- `IndexSyncEvent`, `IndexSyncStatus`, `IndexSyncBackend`, `IndexSyncErrorType`, `IndexSyncSource`, `IndexSyncTargetState`, `IndexSyncLastError`, `IndexSyncOutboxEntry`, `IndexSyncLog` 모델을 추가했다.
- `IndexSyncOutboxService`와 `InMemoryIndexSyncRepository`를 추가했다.
- `MongoIndexSyncRepository`를 추가해 `index_sync_outbox` dedup index와 future `index_sync_logs` join index를 설치하게 했다.
- Application archive endpoint가 Core SOT archive 성공 후 `index_sync_outbox` pending entry를 생성하도록 연결했다.
- `project_archived` source는 `projects/{project_id}`, `draft_archived` source는 `drafts/{draft_id}`다.
- Dedup key는 `(project_id, event, source.mongo_collection, source.mongo_id)`라 재archive가 중복 outbox entry를 만들지 않는다.
- Target envelope는 canonical `targets.chroma.status="pending"` + `targets.chroma.backend="in_memory_fake"`다. Phase 3A reduced `target="vector"`는 persistent outbox에 저장하지 않는다.
- Retry metadata는 `attempt_count=0`, `max_attempts=3`, `next_attempt_at=None`, `last_error=None`로 시작한다.
- 오류 타입은 서버/backend 계열 `backend_error`와 데이터 없음/not-found 계열 `not_found`를 분리했다.
- `analysis_completed`는 후속 후보로 문서에만 남기고 code enum에는 아직 열지 않았다.
- SoT를 v1.6.26으로 올려 archive outbox 첫 code slice를 정본 계약 인덱스에 반영했다.

### Phase 3B archive outbox 독립 검증 후속 보강

- 변경 파일: `docs/mongo_collections.md`, `services/application/app/indexing/mongo_repository.py`, `tests/test_indexing_mongo_indexes.py`, `tests/test_indexing_phase3a.py`, `docs/system-contract-sot.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-03/work_log.md`.
- 독립 검증 `docs/verifications/2026-07-03/phase3b_archive_outbox_slice.md`의 PASS 판정과 비블로킹 리스크를 확인했다.
- Risk 1 대응으로 live Mongo 없이도 Mongo outbox document 직렬화/역직렬화를 잠그는 fake collection round-trip 회귀를 추가했다. `put_outbox_entry()`로 저장한 `IndexSyncOutboxEntry`를 `get_outbox_entry_by_dedup_key()`로 다시 읽어 동일 객체로 복원되는지 확인한다.
- Risk 2 대응으로 `docs/mongo_collections.md`에 `39A. index_sync_outbox`를 추가했다. pending request collection, document shape, dedup key, indexes, `index_sync_logs`와의 `sync_request_id` 조인 관계를 명시했다.
- 저위험 권고 대응으로 `analysis_completed`가 아직 `IndexSyncEvent` enum에 열리지 않았음을 명시 회귀로 고정했다.
- work log의 v1.6.26 code slice 갱신 누락도 보완했다.
- SoT를 v1.6.27로 올려 검증 후속 보강을 정본 계약 인덱스에 반영했다.

### Phase 3B index sync outbox live Mongo smoke

- 변경 파일: `tests/test_indexing_mongo.py`, `HANDOFF.md`, `docs/daily_logs/2026-07-03/work_log.md`.
- `CORE_SOT_TEST_MONGO_URI`가 write 가능한 MongoDB를 가리킬 때 실행되는 skip-aware live smoke를 추가했다.
- Smoke는 `MongoIndexSyncRepository`와 `IndexSyncOutboxService`를 실제 Mongo collection에 붙여 `project_archived` outbox entry를 insert하고, fresh repository read-back으로 같은 `IndexSyncOutboxEntry`가 복원되는지 확인한다.
- Repeated enqueue는 live unique index 위에서도 같은 `sync_request_id`를 반환하고 `index_sync_outbox` document가 1개만 남는지 확인한다.
- 기본 환경에서는 Mongo가 없거나 인증/권한이 없으면 skip한다. 단순 ping이 아니라 throwaway DB에 index 생성까지 해 보는 probe로 권한 없는 Mongo를 오판하지 않게 했다.
- Throwaway `mongo:7` replica set(`localhost:27031`)에서 live smoke 2개가 실제 실행 통과했다.

### Phase 3B outbox live Mongo smoke 독립 검증 후속 보강

- 변경 파일: `tests/test_indexing_mongo.py`, `tests/test_indexing_mongo_indexes.py`, `HANDOFF.md`, `docs/daily_logs/2026-07-03/work_log.md`.
- 독립 검증 `docs/verifications/2026-07-03/phase3b_outbox_live_mongo_smoke.md`의 PASS 판정과 비블로킹 관찰을 확인했다.
- Observation 1 대응으로 live smoke에 `draft_archived` round-trip을 추가했다. 이제 실제 Mongo에서 `project_archived`와 `draft_archived` archive event source를 모두 읽고 쓴다.
- Observation 2 대응으로 fake collection이 duplicate `_id` insert에서 `DuplicateKeyError`를 발생시키게 하고, `MongoIndexSyncRepository.put_outbox_entry()`가 해당 branch를 idempotent no-op으로 처리하는 단위 회귀를 추가했다.
- Observation 3 대응으로 live smoke의 기본 URI를 없앴다. `CORE_SOT_TEST_MONGO_URI`가 명시되지 않으면 skip하므로, 기본 `unittest discover`가 우연히 `localhost:27017`의 writable Mongo에 side effect를 내지 않는다.
- Observation 4는 이미 `ensure_indexes()` 생성자 실패와 index setup 단위 회귀가 역할을 나눠 잠그고 있어 추가 live index 목록 단언은 하지 않았다.

### Phase 3B worker/retry 결정 브리프 작성

- 변경 파일: `docs/plans/03-index-worker-retry-decisions.md`, `docs/plans/03-indexing.md`, `docs/plans/README.md`, `docs/system-contract-sot.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-03/work_log.md`.
- 사용자 요청에 따라 worker/retry 구현 전에 결정 브리프를 먼저 만들었다.
- 브리프는 one-shot worker command, claim timeout 10분, backoff 1분 → 5분 → terminal `failed`, `backend_error`/`not_found` 모두 3회 시도, active-only status-aware dedup을 채택안으로 기록했다.
- Docker/Compose restart가 worker process를 재시작할 수는 있지만 MongoDB에 남은 `running` outbox 상태를 자동으로 `pending`으로 되돌리지는 않는다는 점을 claim timeout 필요성의 이유로 남겼다.
- `not_found`는 단순 같은 query 반복이 아니라 후속 query selector/LLM orchestration이 생기면 대체 조회 전략을 다시 고르는 loop로 해석한다고 문서화했다.
- SoT를 v1.6.28로 올려 worker/retry 실행 경계를 정본 계약 인덱스에 반영했다.

### Phase 3B worker/retry 브리프 독립 검증 후속 보강

- 변경 파일: `docs/plans/03-index-worker-retry-decisions.md`, `docs/plans/03-indexing.md`, `docs/system-contract-sot.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-03/work_log.md`.
- 독립 검증 `docs/verifications/2026-07-03/phase3b_worker_retry_brief.md`의 조건부 합격 판정과 구현 차단 빈칸을 확인했다.
- status-aware dedup과 기존 unique index 충돌을 브리프에 구현 차단 사항으로 명시했다. Terminal entry location / active-only unique index는 partial unique index(A)와 terminal 이동(B) 중 오너 결정이 필요하며, 브리프 추천은 B로 남겼다.
- Claim timeout 구현에 필요한 `claimed_at` lease timestamp, timestamp type, atomic claim, claim order, stale running reclaim 시 attempt accounting을 문서화했다.
- Archive worker-time `not_found`와 query-time `not_found`를 분리해 설명했다. Archive worker-time은 idempotent success로 볼지 3회 retry할지 오너 결정이 필요하며, 브리프 추천은 idempotent success다.
- Fake archive mutation은 recording-only `mark_archived`/`delete_or_tombstone` equivalent로 검증하고 실제 Chroma/Elasticsearch mutation은 후속으로 둔다고 명시했다.
- `index_sync_logs` 최소 attempt log field(`sync_log_id`, timestamps, status/error fields 등)를 브리프에 추가했다.
- SoT/HANDOFF/CHANGELOG의 표현을 "승인"에서 "조건부 승인, 구현 전 결정 필요"로 낮춰 overclaim을 제거했다.

### Phase 3B one-shot index sync worker 첫 slice 구현

- 변경 파일: `services/application/app/indexing/models.py`, `services/application/app/indexing/service.py`, `services/application/app/indexing/mongo_repository.py`, `scripts/index_sync_worker.py`, `tests/test_indexing_phase3a.py`, `tests/test_indexing_mongo_indexes.py`, `tests/test_index_sync_worker_script.py`, `docs/plans/03-index-worker-retry-decisions.md`, `docs/plans/03-indexing.md`, `docs/mongo_collections.md`, `docs/system-contract-sot.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-03/work_log.md`.
- 사용자 결정으로 terminal-location/index 전략은 B를 채택했다. `index_sync_outbox`는 active queue로 유지하고, terminal `success|failed` history는 `index_sync_logs`가 소유한다. 따라서 기존 active outbox unique index는 유지한다.
- 사용자 결정으로 archive worker-time `not_found`는 B를 채택했다. Archive/tombstone/delete 대상 derived record가 이미 없으면 목표 상태 달성으로 보고 idempotent success 처리한다. Query-time `not_found`는 후속 query selector/LLM orchestration retry loop error type으로 남긴다.
- `IndexSyncOutboxEntry`에 `claimed_at`을 추가하고, `IndexSyncLog`에 `started_at`/`finished_at`을 추가했다. Timestamp는 UTC datetime/BSON Date 정책으로 문서화했다.
- `InMemoryIndexSyncRepository`와 `MongoIndexSyncRepository`에 pending/stale-running claim, success/failure record, terminal outbox removal, retry backoff update, log append를 추가했다.
- `IndexSyncWorker`는 one-shot `run_once(limit=N)`로 bounded 실행되며, recording-only fake archive adapter를 사용해 archive event 처리 의도와 status/log lifecycle을 검증한다.
- Backend failure는 attempt 실패로 기록하고 `attempt_count`를 증가시킨다. attempt 1 실패는 1분 뒤, attempt 2 실패는 5분 뒤 재시도하고, attempt 3 실패는 terminal `failed`로 outbox에서 제거한다.
- Stale running reclaim은 `attempt_count`를 증가시키지 않는다. 실제 adapter/backend 결과가 없는 crash를 실패 attempt로 오표기하지 않기 위해서다.
- Worker summary의 `entries_requeued`는 repository 내부 저장구조가 아니라 `attempt_count + 1 < max_attempts` 계약으로 계산한다. Mongo repository에도 같은 summary semantics가 적용되게 하기 위해서다.
- MongoDB read-back 경로는 BSON Date가 naive UTC로 반환돼도 Python domain model 계약에 맞게 timezone-aware UTC `datetime`으로 정규화한다.
- `scripts/index_sync_worker.py`를 추가해 `CORE_SOT_MONGO_URI`/`--mongo-uri` 기반 one-shot worker command를 제공한다.
- SoT를 v1.6.29로 올려 worker 첫 구현 slice를 정본 계약 인덱스에 반영했다.

### Phase 3B worker/retry slice 독립 검증 후속 보강

- 변경 파일: `tests/test_indexing_mongo.py`, `docs/plans/03-index-worker-retry-decisions.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-03/work_log.md`, `docs/verifications/2026-07-03/phase3b_worker_retry_slice.md`.
- 독립 검증(`docs/verifications/2026-07-03/phase3b_worker_retry_slice.md`, 합격)이 지적한 두 비블로킹 항목을 보강했다.
- 이슈 #2(Mongo worker lifecycle live 회귀 부재): `tests/test_indexing_mongo.py`에 `MongoIndexSyncWorkerSmokeTests` 4개를 추가했다. 기존 outbox live smoke와 같은 `CORE_SOT_TEST_MONGO_URI` env-only skip 게이트를 공유한다. 잠근 범위: success → active outbox 제거 + success log append, backend_error 1분→5분 backoff 후 3회 terminal `failed`(logs `[1,2,3]`), stale running(>10분) reclaim은 `attempt_count` 미소비 + non-stale는 reclaim 불가, terminal success 후 같은 dedup key 재enqueue는 새 `sync_request_id`.
- 이슈 #1(브리프 §5 내부 모순): 브리프 Owner 결정(line 13)과 §5 채택이 "`not_found` 3회"로 남아 §8.2/코드/테스트/SoT의 "archive worker-time `not_found` = idempotent success"와 충돌했다. line 13과 §5에 query-time(3회, 후속 selector)/archive worker-time(idempotent success) 분리 note를 추가해 모순을 제거했고, §8 회귀의 query-time `not_found` 항목에 "후속 query selector slice에서 회귀 추가"를 표시했다. 결정 자체는 변경 없이 문서 일관성만 정리했다.

### Phase 4 agentic search 착수 결정 브리프 작성

- 변경 파일: `docs/plans/04-agentic-search-kickoff-decisions.md`(신규), `docs/plans/04-agentic-search.md`, `docs/plans/README.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-03/work_log.md`.
- HANDOFF Next Tasks가 모두 후속/상류 차단 상태(real adapter 최후속, tool-call branch 차단, `artifact_present` 대기)라 계획 순서상 다음 착수 지점을 Phase 4 agentic search로 판단했다.
- Phase 2A/3A/3B와 같은 관례로 구현 전 착수 결정 브리프를 먼저 작성했다. 상태는 `Proposed for owner decision`이며 오너 결정 전 구현을 시작하지 않는다.
- `04-agentic-search.md`의 미확정 8개 항목 각각에 선택지 표와 추천안을 정리했다: ① purpose/need 최소 literal(추천 `writing_context` 1종 + `current_scene`/`recent_scenes`/`event_context`/`source_quote` 4종 — 현재 검색 재료인 source block + Mongo SOT로 실제 서빙 가능한 것만), ② 규칙 기반 deterministic planner 우선(LLM flat loop planner는 domain tool-call branch 상류 3중 의존 해소 후), ③ retrieval surface는 Phase 3A fake vector + Mongo direct 순차 실행(ES lexical 후속), ④ deterministic ranking(need 우선순위→similarity→tie-break)과 문자수 기반 token 추정 + 초과 항목 제외, ⑤ `needs_review` candidate는 첫 slice 제외하되 `candidate`/`canonical` status 라벨 필드는 계약에 오픈, ⑥ retriever step 실패는 degraded 표시 + trace 기록, Mongo SOT reload 실패는 전체 실패, ⑦ ContextPackage는 첫 slice에서 persist하지 않음, ⑧ Writing/Analysis package는 단일 schema + purpose literal로 시작하고 analysis 비교용 필드는 Phase 2B 착수 브리프에서 결정.
- 구현을 막는 상류 의존(사실)도 결정과 분리해 명시했다: tool-call branch 미구현, ES 부재, canonical memory store 부재.
- 첫 구현 slice 제안은 `services/application/app/context_search/` domain model + 규칙 기반 planner + `validate_source_block_record()` guard 경유 SOT reload orchestration + deterministic ranking/budget + Context Gate 최소 검사 + 양방향 회귀 목록으로 한정했다. HTTP API, LLM planner, ES, prior-memory purpose, package persist는 후속 slice로 남겼다.
- SoT는 올리지 않았다. 승인된 결정이 아직 없으므로 SoT 반영은 오너 결정 후로 미룬다(3B 브리프와 같은 관례). (후속: 같은 날 오너 결정으로 v1.6.30 승인됨 — 아래 참조.)

### Phase 4 착수 브리프 오너 결정 반영 (SoT v1.6.30)

- 변경 파일: `docs/plans/04-agentic-search-kickoff-decisions.md`, `docs/plans/04-agentic-search.md`, `docs/system-contract-sot.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-03/work_log.md`.
- 오너가 8개 항목을 결정했다: §1 A(최소 literal, 후속 확장 가능 확인), §2 B(LLM planner 즉시), §3 A, §4 A(최소, 최종 튜닝 후속), §5 오너는 B 선호이나 확장 비용 낮음 확인 후 A 먼저 + B 후속, §6 A + 계열 구분 error taxonomy 확장 조건, §7 A, §8 A로 시작하되 이후 slice에서 C(Writing/Analysis 비교용 모두) 완성 의무.
- §2는 기존 승인 결정("tool-call branch는 wire 미계약이라 추측 구현 금지")과의 충돌을 명시하고 확인 질문을 했다. 오너 확인 결과 **터미널 JSON planner**(1-turn SearchPlan JSON 생성, tool-call 없음, Phase 2A extraction 패턴)로 확정했고, tool-call flat loop planner 전환 계획을 브리프 §2.1로 남겼다. live Gateway는 test/smoke 전용이고 구현은 provider 추상화 뒤에 둔다. IP 진입→내부 통신 전환은 env 설정 변경임을 확인했다.
- §6 오너 조건에 따라 step 실패 error taxonomy를 `backend_error`/`system_error`/`llm_error`/`sot_error` 4종(enum 확장 가능)으로 브리프에 확정했다. `sot_error`는 degraded가 아니라 전체 실패다.
- 브리프 상태를 `Approved for Phase 4 first slices (2026-07-03)`로 올리고 Owner decisions 섹션과 §9 Slice 4.1/4.2 승인 범위를 기록했다. SoT v1.6.30, `04-agentic-search.md` 착수 전 결정사항 전항 [x] 처리.

### Phase 4 Slice 4.1 구현 (SoT v1.6.31)

- 변경 파일: `services/application/app/context_search/__init__.py`(신규), `services/application/app/context_search/models.py`(신규), `services/application/app/context_search/service.py`(신규), `services/application/app/indexing/service.py`, `tests/test_context_search.py`(신규), `docs/plans/04-agentic-search-kickoff-decisions.md`, `docs/system-contract-sot.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-03/work_log.md`.
- domain model: purpose/need/tool/status/error enum, `ContextSearchRequest`/`ContextBudget`/`CurrentPosition`, `SearchPlan`/`SearchPlanStep(tools tuple)`, `ContextItem`(candidate/canonical status 라벨 + `source_ref_ids` 계약 필드 포함), `ContextPackage`(macro/micro/constraints/do_not_use/trace/degraded/status="candidate"), `GateFinding`/`GateDecision`, need→tool 허용 매핑.
- `ContextSearchService.build_context_package()`: planner(주입) → plan 검증(cross-project/미요청 need/불허 tool은 `llm_error`) → step 순차 실행 → deterministic ranking(need 우선순위, need 내 도착순=vector 유사도순) → budget 포함/제외(절단 없음) → package. wall-clock 한도 기본 60s(주입 clock), 초과는 error taxonomy와 분리된 `ContextSearchBudgetExceeded`.
- vector 경로: `query_similar` hit → Phase 3A `validate_source_block_record()` guard(stale 제외 + trace reason) → Mongo SOT 재조회 → SOT block text로 ContextItem 구성. index hit text는 사용하지 않는다. adapter 예외는 step `backend_error` + `degraded=true`로 계속 진행, SOT reload의 non-NotFound 오류는 `sot_error` 전체 실패.
- Mongo direct 경로: `current_position(draft_id, version_id)`로 version snapshot을 읽고 SOT block kind(heading/scene marker) 기반 deterministic 경계로 `current_scene`(마지막 경계 이후 paragraph run)/`recent_scenes`(경계 이전 paragraph 최대 5개)를 구성한다. AI 추론 split 없음.
- `evaluate_context_gate()`: orchestration flag를 신뢰하지 않고 SOT를 재조회하는 독립 검사. cross-project, SOT reload 증거 부재, candidate status 항목(첫 slice 금지 — B 확장 시 완화), stale(hash drift/block 소실/archive), budget 초과 → reject + findings.
- `InMemoryVectorIndexAdapter.query_similar(project_id, vector, limit)`을 indexing adapter에 추가했다(cosine, `(-similarity, record.id)` deterministic 순서, project-scoped). 유사도 계산은 context_search가 아니라 adapter 계층 소유로 두어 실제 Chroma 도입 시 같은 표면으로 교체한다.
- 회귀 24개: SOT reload/canonical 라벨/trace, scene 경계, project isolation, archive 후 stale 제외(should-fire)+fresh hit 미제외(should-NOT-fire), `sot_error` 전체 실패, budget 양방향, need 우선순위 ranking 양방향, backend 실패 degraded+taxonomy, 정상 실행 비degraded, 빈 결과 trace, planner 실패/plan 위반 3종 `llm_error`, wall-clock 초과, invalid request 3종, Gate pass 1 + reject 5분기, token 추정, query_similar 경계.

### Phase 4 Slice 4.1 독립 검증 차단 조건 폐쇄 (SoT v1.6.32)

- 변경 파일: `services/application/app/context_search/service.py`, `tests/test_context_search.py`, `docs/plans/04-agentic-search-kickoff-decisions.md`, `docs/system-contract-sot.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-03/work_log.md`.
- 독립 검증(`docs/verifications/2026-07-03/context_search_slice_4_1.md`, 조건부 합격)이 차단급 결함을 실증했다: SOT reload catch가 `NotFound`/`CoreSotError`뿐이라 실가동 백엔드 장애(pymongo 등 non-CoreSotError 예외)가 `sot_error`로 매핑되지 않고 원형 탈출했고, vector 경로의 stale guard 호출은 try 블록 밖이었다. 기존 회귀 `test_sot_reload_failure_surfaces_sot_error_not_fake_success`는 `_BrokenSotRepository` fixture에도 불구하고 `version_id="missing-version"` 탓에 NotFound 경로만 탔다(`get_blocks`의 RuntimeError는 도달 불가 dead code).
- 코드 보강: SOT reload 호출 4곳(vector stale-guard 검증, vector hit 재조회, Mongo position reload, Gate 재검증 2곳)의 catch를 non-NotFound 예외까지 넓혀 `ContextSearchFailed(sot_error)`로 매핑했다. try 블록은 SOT 호출만 감싸 orchestration 버그의 `sot_error` 오분류를 막는다. Gate도 검증 불가를 pass/오귀속 reject로 바꾸지 않고 같은 lineage로 던진다. 매핑 계열은 별도 오너 결정 없이 `sot_error`로 정했다 — 근거: 승인 계약(§6/SoT v1.6.31)의 "Mongo SOT reload 실패 = sot_error 전체 실패"는 reload 시도 중의 실패 전부를 가리키는 평문 독해이고, `system_error`는 SOT 호출 밖 orchestration 계열용 예약으로 남긴다.
- 테스트 보강: `_ToggleBackendSotRepository`(정상↔`fail_reads=True`에서 raw RuntimeError)로 진짜 백엔드 예외를 주입하는 양방향 회귀 3개(Mongo position/vector hit/Gate — 정상 시 통과 over-strict + 다운 시 `sot_error` under-strict), vector snapshot NotFound soft 제외 회귀 1개(ghost record → `snapshot_missing` + 비degraded). 기존 테스트는 `test_missing_position_version_maps_to_sot_error`로 개명해 의도/동작을 일치시켰다. 변이 증명: 넓힌 catch를 `CoreSotError`로 되돌리면 5개 재실패.
- 계약 보강: 브리프 §6에 sot_error 범위(non-NotFound 예외 포함), NotFound 경로별 의도 분기(vector hit=`snapshot_missing` soft 제외 / Mongo position=`sot_error` 전체 실패), `system_error` 예약 literal을 명문화하고 SoT v1.6.32로 올렸다. 브리프 §9.1 `ContextItem` 필드명 스케치도 구현 확정 명(`pointer`/`source_ref_ids`)으로 정정했다.
- 비차단 정정: "435개 통과(44 skip)"는 unittest "Ran 435 ... OK (skipped=44)" 오독이었다(실제 391 passed/44 skipped). 이번 세션 기록(HANDOFF/work log/브리프)을 정정했다. 같은 "N개 통과(M skip)" 표현이 과거 날짜 기록 전반에도 있으므로(예: "394개 통과(37 skip)") 과거 이력은 고치지 않되, 이후 기록은 passed/skipped를 분리 표기한다.
- 검증 기록 원본은 조건부 판정 그대로 보존한다(관례). 폐쇄 증적은 본 로그와 HANDOFF/SoT가 소유한다.

## Issues found

- 문제: 브리프는 미확정 항목 목록에 4/5/6을 적었지만 실제 선택지와 채택안은 없었다.
- 원인: 초안이 event source, delivery, storage unit에 집중했고 archive mutation, retry/backoff, real adapter 도입 경계는 "승인 전 보류" 목록으로만 처리했다.
- Resolution: 4/5/6 각각에 선택지 표, 채택안, 후속 조건을 추가했다.
- Outcome: 다음 code slice가 archive outbox entry 생성으로 좁혀졌고, worker/retry/real adapter를 추측하지 않게 됐다.

- 문제: 저장 단위 추천안 A는 사용자 결정과 맞지 않았다.
- 원인: 기존 브리프는 이미 존재하는 `index_sync_logs` §39를 재사용하는 최소 변경을 선호했다.
- Resolution: 사용자 결정대로 `index_sync_outbox` + `index_sync_logs` 분리로 바꾸고, `sync_request_id` 조인을 첫 slice 수용 기준에 추가했다.
- Outcome: queue lifecycle과 result history가 섞이지 않는 방향으로 계약이 바뀌었다.

- 문제: `analysis_completed`를 지금 enum에 넣으면 실제 지원하지 않는 event literal이 열린 것처럼 보일 수 있었다.
- 원인: 사용자는 장기적으로 D가 가장 맞는 흐름이라고 판단했지만, 이번 구현은 archive events부터 시작하기로 했다.
- Resolution: `analysis_completed`는 브리프/SoT/HANDOFF의 후속 event candidate로 명시하고, code enum은 `project_archived`/`draft_archived`만 허용했다.
- Outcome: 첫 slice의 public/domain surface가 실제 구현 범위와 일치한다.

- 문제: Core SOT archive write와 outbox write를 같은 Mongo transaction unit에 넣으려면 Core SOT repository 경계에 indexing concern을 섞어야 했다.
- 원인: 현재 `CoreSotService`는 `CoreSotRepository` Protocol만 의존하고, indexing은 별도 domain module이다.
- Resolution: 첫 code slice는 Application archive endpoint orchestration으로 archive 성공 후 outbox enqueue를 호출했다. 같은 transaction/fallback unit hardening은 persistent worker/repository slice에서 재검토한다.
- Outcome: 현재 구조를 크게 흔들지 않고 archive outbox 계약과 idempotency를 먼저 잠갔다.

- 문제: `MongoIndexSyncRepository`의 `_outbox_doc()`/`_to_outbox_entry()` 직렬화 경로가 production-reachable인데 테스트가 없었다.
- 원인: 첫 회귀는 required index setup과 Application in-memory wiring에 집중했다.
- Resolution: fake collection 기반 round-trip 회귀를 추가해 live Mongo 없이 document shape를 잠갔다.
- Outcome: field 누락이나 enum 역직렬화 drift를 focused test가 잡을 수 있다.

- 문제: `index_sync_outbox` collection이 `mongo_collections.md` 운영 collection 레지스트리에 없었다.
- 원인: 첫 문서 업데이트는 SoT/Phase plan/brief에 집중했고, 루트 아이디에이션 collection registry를 갱신하지 않았다.
- Resolution: `39A. index_sync_outbox` 섹션과 목록/relationship/workflow cross-reference를 추가했다.
- Outcome: code-enforced collection이 문서 registry에도 드러난다.

- 문제: 테스트 환경에 인증이 필요한 Mongo가 떠 있으면 ping만으로 live test 가능 여부를 판단할 수 없었다.
- 원인: Mongo 연결 가능성과 throwaway DB/index 생성 권한은 별도 조건이다.
- Resolution: `tests/test_indexing_mongo.py`의 probe가 ping 후 throwaway collection index 생성까지 수행하도록 했다.
- Outcome: 권한 없는 Mongo는 failure가 아니라 skip으로 처리되고, write 가능한 Mongo에서만 live smoke가 실행된다.

- 문제: `tests/test_indexing_mongo.py`의 기본 URI가 `localhost:27017`이면, 개발자 환경에 writable Mongo가 떠 있을 때 기본 discovery가 의도치 않게 live smoke를 실행할 수 있었다.
- 원인: 기존 Mongo 통합 테스트 관례를 따라 기본 localhost를 두었지만, 이 live smoke는 test-only 보강이라 명시 opt-in이 더 안전했다.
- Resolution: `CORE_SOT_TEST_MONGO_URI`가 명시되지 않으면 live smoke를 skip하도록 변경했다.
- Outcome: 기본 discovery는 외부 Mongo side effect 없이 skip되고, live smoke는 명시 URI에서만 실행된다.

- 문제: Docker/Compose restart만으로 worker crash 후 `running` outbox entry가 회수된다고 오해할 수 있었다.
- 원인: process lifecycle과 MongoDB에 저장된 outbox lifecycle이 별도인데, worker/retry 숫자 결정 전 이 차이가 문서화되지 않았다.
- Resolution: `docs/plans/03-index-worker-retry-decisions.md`에 claim timeout 10분의 목적을 stale `running` DB 상태 회수로 명시했다.
- Outcome: worker 구현자가 restart와 claim recovery를 혼동하지 않게 됐다.

- 문제: active-only status-aware dedup 결정이 기존 `index_sync_outbox` unique index와 충돌했다.
- 원인: 기존 unique index는 dedup key에 status를 포함하지 않아 terminal entry가 outbox에 남으면 같은 key의 새 active request insert를 막는다.
- Resolution: 브리프에 partial unique index와 terminal 이동 선택지를 추가하고, 오너 결정 전 worker 구현을 시작하지 않도록 상태를 조건부 승인으로 낮췄다.
- Outcome: 구현자가 unique index migration 또는 terminal 이동을 임의로 선택하지 않게 됐다.

- 문제: claim timeout을 판정할 lease timestamp field가 기존 model/schema에 없었다.
- 원인: 첫 outbox slice는 pending entry 생성까지만 다뤘고 worker claim schema를 열지 않았다.
- Resolution: 브리프에 `claimed_at`, UTC datetime/BSON Date 정책, atomic claim, stale running reclaim accounting을 추가했다.
- Outcome: claim timeout 구현에 필요한 field/type/attempt budget 원칙이 문서화됐다.

- 문제: worker terminal 처리 후 같은 dedup key의 새 active request를 허용하려면 outbox와 logs 책임을 code에서 분명히 나눠야 했다.
- 원인: 기존 outbox unique index는 active/terminal을 구분하지 않고 같은 key를 전역 unique로 묶었다.
- Resolution: terminal 이동을 채택하고 success/failed 시 active outbox entry를 제거하며 `index_sync_logs`에 attempt/result history를 append하게 했다.
- Outcome: 기존 unique index를 유지하면서 terminal 후 재enqueue가 새 `sync_request_id`를 만들 수 있다.

- 문제: MongoDB BSON Date read-back이 driver 설정에 따라 naive UTC `datetime`으로 들어올 수 있었다.
- 원인: 문서 계약은 timezone-aware UTC였지만 `_to_outbox_entry()`가 Mongo document timestamp를 그대로 domain model에 넣었다.
- Resolution: Mongo outbox 역직렬화에서 `next_attempt_at`/`claimed_at`을 UTC aware로 정규화하고, fake collection round-trip 회귀에 naive read-back sample을 추가했다.
- Outcome: repository read-back이 timestamp 계약을 안정적으로 지킨다.

- 문제: Worker summary의 `entries_requeued` 계산이 in-memory repository 내부 dict에 기대면 Mongo CLI 실행에서는 재시도 예정 실패를 requeued로 세지 못한다.
- 원인: summary 계산이 repository public contract가 아니라 테스트용 저장구조를 들여다봤다.
- Resolution: 실패 attempt 직전 `attempt_count + 1 < max_attempts`로 requeue 여부를 계산하게 바꿨다.
- Outcome: in-memory와 Mongo repository에서 같은 worker summary semantics가 유지된다.

- 문제: Slice 4.1의 SOT reload 실패 경로에서 실가동 백엔드 장애(non-CoreSotError 예외)가 `sot_error`로 매핑되지 않고 원형 탈출했고, 이를 잠갔다고 믿은 회귀는 실제로는 NotFound 경로만 탔다.
- 원인: catch 표면을 `except NotFound`/`except CoreSotError`로 좁게 잡았는데 Mongo repository는 pymongo 예외를 `CoreSotError`로 감싸지 않는다. 테스트는 `_BrokenSotRepository`(get_blocks RuntimeError)를 만들고도 `version_id="missing-version"`을 줘서 `get_version()` None → NotFound가 먼저 발화해 fixture의 RuntimeError가 dead code가 됐다 — "초록 테스트 = 계약 검증" 함정 그대로.
- Resolution: SOT reload 호출 4곳 catch를 non-NotFound 예외까지 넓혀 `sot_error` 매핑(try 블록은 SOT 호출만), toggle repo로 진짜 백엔드 예외를 주입하는 양방향 회귀 3개 + vector NotFound soft 제외 회귀 1개 추가, 기존 테스트 개명으로 의도/동작 일치, 변이 증명으로 잠금 확인.
- Outcome: "SOT 백엔드 다운 → sot_error 전체 실패" boundary가 코드·회귀·계약(§6 명문화, SoT v1.6.32) 세 층에서 닫혔고, Slice 4.2 live caller가 붙어도 원형 예외가 새지 않는다.

- 문제: 이번 세션 기록에 "전체 435개 통과(44 skip)"로 적었으나 실제 passed는 391이었다.
- 원인: unittest discover의 "Ran 435 tests ... OK (skipped=44)"에서 "Ran N"을 "N개 통과"로 오독했다. skip은 Ran에 포함된다.
- Resolution: 이번 세션 기록(HANDOFF/work log/브리프)을 passed/skipped 분리 표기로 정정했다(보강 후 439 실행 / 395 passed / 44 skipped).
- Outcome: reported number가 재계산 가능해졌다. 과거 날짜 기록의 같은 표현("394개 통과(37 skip)" 등)은 이력 보존을 위해 고치지 않되, 이후 기록은 분리 표기를 따른다(추적 부채로 명시).

## Decisions

- Phase 3B 첫 automatic event source는 archive events로 시작한다. `analysis_completed`는 장기적으로 더 맞는 흐름으로 보지만 candidate indexing/review 지위가 확정될 때까지 후속이다.
- 외부 queue는 현재 로컬 1인 프로젝트 단계에서 고려하지 않는다. Mongo outbox/polling을 채택한다.
- Pending/running/retry lifecycle은 `index_sync_outbox`, completed or terminal attempt history는 `index_sync_logs`가 소유한다.
- 첫 code slice는 archive API 성공 후 canonical `targets.chroma` + `backend="in_memory_fake"` pending outbox entry를 idempotent하게 생성하는 데 한정한다.
- `user_id`는 현재 user model이 없으므로 nullable로 둔다. 필드는 생략하지 않아 후속 user ownership 계약의 migration 지점을 남긴다.
- `backend_error`와 `not_found`는 다른 error type이다. 둘 다 기본 3회 시도(`max_attempts=3`)로 시작한다.
- `analysis_completed`는 아직 code enum에 열지 않는다. 실제 candidate indexing/review 지위가 확정될 때 event literal과 source collection을 추가한다.
- `index_sync_outbox`는 `mongo_collections.md` 운영 collection 레지스트리에 등록한다.
- Worker/retry 구현 전 브리프를 먼저 확정한다. 첫 worker는 one-shot command로 시작하고 장기적으로 UI-triggered background/daemon이 같은 service를 재사용할 수 있게 둔다.
- Claim timeout은 10분, backoff는 1분 → 5분 → terminal `failed`다.
- `backend_error`와 `not_found`는 둘 다 `max_attempts=3`을 사용한다. `not_found`는 후속 query selector/LLM orchestration retry loop의 error type으로 해석한다.
- Status-aware dedup은 `pending|running` active entry에만 적용하고 terminal `success|failed`만 있으면 새 active request 생성을 허용한다.
- Terminal-location/index 전략은 terminal 이동을 채택한다. Outbox는 active queue이고 terminal history는 `index_sync_logs`가 소유한다.
- Archive worker-time `not_found`는 idempotent success다.
- (Phase 4) 착수 브리프 8개 항목을 오너가 결정했다(§1 A, §2 터미널 JSON LLM planner, §3 A, §4 A, §5 A→B 후속, §6 A+error taxonomy 조건, §7 A, §8 A→C 완성 의무). 상세와 근거는 브리프 Owner decisions 섹션과 위 "Phase 4 착수 브리프 오너 결정 반영" 참조.
- (Phase 4) planner를 LLM 기반으로 즉시 시작하는 이유: 뼈대가 되는 에이전트 LLM Gateway가 이미 live로 연결되어 있고, 규칙 기반 planner를 거치는 한 단계가 불필요하다고 판단했다. 단 tool-call wire 미계약 충돌을 피하기 위해 범위는 터미널 JSON 1-turn으로 좁혔다(오너 확인 완료).
- (Phase 4) "LLM tool-call 미가용 시 터미널 JSON으로 우회" 패턴은 반복될 결정이므로 전환 계획을 브리프 §2.1로 문서화해 두기로 했다(오너 요청).

## Verification

- Phase 3B brief links: `docs/plans/03-index-sync-outbox-decisions.md`가 참조하는 `../system-contract-sot.md`, `03-indexing.md`, `03-indexing-kickoff-decisions.md` 존재 확인.
- Stale wording sweep: `rg -n 'Proposed for owner|owner approval|SoT/public contract가 아니며|승인 필요|index_sync_logs pending|Mongo index_sync_logs 기반 pending' docs/plans/03-index-sync-outbox-decisions.md docs/plans/03-indexing.md HANDOFF.md docs/system-contract-sot.md CHANGELOG.md` — 현재 문맥에 남은 stale 문구 없음.
- Documentation diff hygiene: `git diff --check` — 통과.
- Phase 3B archive outbox compile: `python3 -m py_compile services/application/app/indexing/models.py services/application/app/indexing/service.py services/application/app/indexing/mongo_repository.py services/application/app/main.py tests/test_indexing_phase3a.py tests/test_indexing_mongo_indexes.py tests/test_application_api.py` — 통과.
- Phase 3B archive outbox focused regression: `python3 -m unittest tests.test_indexing_phase3a tests.test_indexing_mongo_indexes -v` — 17개 통과.
- Application archive wiring regression: `python3 -m unittest tests.test_application_api -v` — 50개 통과.
- Phase 3B related broader regression: `python3 -m unittest tests.test_indexing_phase3a tests.test_indexing_mongo_indexes tests.test_application_api -v` — 67개 통과.
- Phase 3A/3B broader regression: `python3 -m unittest tests.test_phase3a_rebuild_source_block_index_script tests.test_phase3a_deployed_rebuild_smoke_script tests.test_indexing_phase3a tests.test_application_api -v` — 79개 통과.
- Full regression: `python3 -m unittest discover tests -v` — 394개 통과(37 skip).
- Pattern sweep: `rg -n "archive_project\\(|archive_draft\\(|enqueue_project_archived|enqueue_draft_archived|IndexSyncErrorType|backend_error|not_found|INDEX_SYNC_MAX_ATTEMPTS|max_attempts" services tests docs/plans/03-index-sync-outbox-decisions.md docs/plans/03-indexing.md docs/system-contract-sot.md HANDOFF.md CHANGELOG.md docs/daily_logs/2026-07-03/work_log.md` — Core SOT service 단위 테스트의 직접 archive 호출은 남아 있으나, 이번 slice의 outbox 책임은 Application archive endpoint에 둔 것으로 문서화했다. API endpoint와 outbox enqueue 경로, error type, max attempts는 회귀로 잠겼다.
- Final diff hygiene: `git diff --check` — 통과.
- Verification follow-up compile: `python3 -m py_compile services/application/app/indexing/mongo_repository.py tests/test_indexing_mongo_indexes.py tests/test_indexing_phase3a.py` — 통과.
- Verification follow-up focused regression: `python3 -m unittest tests.test_indexing_phase3a tests.test_indexing_mongo_indexes -v` — 19개 통과.
- Verification follow-up full regression: `python3 -m unittest discover tests` — 396개 통과(37 skip).
- Index sync outbox live smoke compile: `python3 -m py_compile tests/test_indexing_mongo.py` — 통과.
- Index sync outbox default focused regression: `python3 -m unittest tests.test_indexing_mongo tests.test_indexing_mongo_indexes -v` — 권한 있는 Mongo 미가용으로 live 2개 skip, fake/index setup 3개 통과.
- Index sync outbox live Mongo regression: throwaway `mongo:7` replica set on `localhost:27031`에서 `CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27031/?directConnection=true' python3 -m unittest tests.test_indexing_mongo -v` — live 2개 통과. 컨테이너는 `docker stop index-sync-mongo-smoke`로 정리.
- Final full regression after live smoke: `python3 -m unittest discover tests` — 398개 통과(39 skip).
- Outbox live smoke follow-up compile: `python3 -m py_compile tests/test_indexing_mongo.py tests/test_indexing_mongo_indexes.py` — 통과.
- Outbox live smoke follow-up focused regression: `python3 -m unittest tests.test_indexing_mongo tests.test_indexing_mongo_indexes -v` — env 미지정으로 live 3개 skip, fake/index setup 4개 통과.
- Outbox live smoke follow-up live regression: throwaway `mongo:7` on `localhost:27032`에서 `CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27032/?directConnection=true' python3 -m unittest tests.test_indexing_mongo -v` — live 3개 통과. 컨테이너는 `docker stop phase3b-outbox-followup`로 정리.
- Final full regression after outbox live follow-up: `python3 -m unittest discover tests` — 400개 통과(40 skip).
- Worker/retry brief link check: `docs/plans/03-index-worker-retry-decisions.md`가 참조하는 `../system-contract-sot.md`, `03-indexing.md`, `03-index-sync-outbox-decisions.md` 존재 확인.
- Worker/retry brief verification follow-up: `docs/verifications/2026-07-03/phase3b_worker_retry_brief.md` 확인 후 구현 차단 빈칸 #1/#2와 비차단 항목 #3~#6을 브리프/HANDOFF/SoT에 반영했다.
- One-shot worker compile: `python3 -m py_compile services/application/app/indexing/models.py services/application/app/indexing/service.py services/application/app/indexing/mongo_repository.py scripts/index_sync_worker.py tests/test_indexing_phase3a.py tests/test_indexing_mongo_indexes.py tests/test_index_sync_worker_script.py` — 통과.
- One-shot worker focused regression: `python3 -m unittest tests.test_indexing_phase3a tests.test_indexing_mongo_indexes tests.test_index_sync_worker_script -v` — 27개 통과.
- One-shot worker broader regression: `python3 -m unittest tests.test_indexing_phase3a tests.test_indexing_mongo_indexes tests.test_indexing_mongo tests.test_index_sync_worker_script tests.test_application_api` — 80개 통과(3 skip).
- One-shot worker final full regression: `python3 -m unittest discover tests` — 407개 통과(40 skip).
- One-shot worker final diff hygiene: `git diff --check` — 통과.
- Worker slice 독립 검증: `docs/verifications/2026-07-03/phase3b_worker_retry_slice.md` — 합격. 직전 브리프 검증 리스크 #1~#4 해소, §8 회귀 전항 ↔ 테스트 추적, throwaway `mongo:7`로 live Mongo worker lifecycle 4경로(success / backoff-terminal / stale reclaim / terminal-reenqueue) 독립 통과를 입증.
- Worker slice 보강 compile: `python3 -m py_compile tests/test_indexing_mongo.py` — 통과.
- Worker slice 보강 live smoke: throwaway `mongo:7`(27034)에서 `CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27034/?directConnection=true' python3 -m unittest tests.test_indexing_mongo -v` — live 7개(기존 outbox 3 + 신규 worker 4) 통과. 컨테이너는 `docker stop`으로 정리.
- Worker slice 보강 final full regression: `python3 -m unittest discover tests` — 411개 통과(44 skip).
- Worker slice 보강 final diff hygiene: `git diff --check` — 통과.
- Phase 4 착수 브리프 link check: 브리프가 참조하는 `../system-contract-sot.md`, `04-agentic-search.md`, `flat-loop-gate.md`, `../abstract.md`, `../agentic_search_flow.md`, `../contracts.md` 존재 확인.
- Phase 4 착수 브리프 literal 정합: need 4종(`current_scene`, `recent_scenes`, `event_context`, `source_quote`)이 `agentic_search_flow.md` §7.2 목록과 일치, `context_search` tool 3종(`search_memory`, `load_memory`, `validate_context`)과 wall-clock 60000ms가 `flat-loop-gate.md` §tool/§budget 표와 일치함을 rg로 확인.
- Phase 4 착수 브리프 diff hygiene: `git diff --check` — 통과. 문서 전용 변경이라 테스트 대상 코드 변경 없음.
- Phase 4 Slice 4.1 compile: `python3 -m py_compile services/application/app/context_search/models.py services/application/app/context_search/service.py services/application/app/indexing/service.py tests/test_context_search.py` — 통과.
- Phase 4 Slice 4.1 focused regression: `python3 -m unittest tests.test_context_search -v` — 24개 통과.
- Phase 4 Slice 4.1 broader regression: `python3 -m unittest tests.test_context_search tests.test_indexing_phase3a tests.test_core_sot` — 72개 통과 (indexing adapter `query_similar` 추가에 따른 기존 Phase 3A/Core SOT 회귀 무손상 확인).
- Phase 4 Slice 4.1 full regression: `python3 -m unittest discover tests` — Ran 435, OK(skipped=44). (당초 "435개 통과(44 skip)"로 기록했으나 이는 "Ran N" 오독 — 실제 391 passed/44 skipped. 독립 검증 지적으로 정정.)
- Slice 4.1 검증 보강 compile: `python3 -m py_compile services/application/app/context_search/service.py tests/test_context_search.py` — 통과.
- Slice 4.1 검증 보강 focused regression: `python3 -m unittest tests.test_context_search -v` — 28개 통과(보강 전 24개).
- Slice 4.1 검증 보강 변이 증명: SOT reload catch 3계열을 `CoreSotError`로 좁히는 변이에서 5개 재실패(백엔드 다운 주입 회귀 포함), 복원 후 전체 통과 — 양방향 잠금 확인.
- Slice 4.1 검증 보강 full regression: `python3 -m unittest discover tests` — Ran 439, OK(skipped=44). `python3 -m pytest -q` — 395 passed, 44 skipped.
- Slice 4.1 검증 보강 diff hygiene: `git diff --check` — 통과.
- Phase 4 Slice 4.1 diff hygiene: `git diff --check` — 통과.

## Next steps

- Phase 4 Slice 4.2: 터미널 JSON LLM planner adapter(`context_search_plan_v1` prompt template, strict parse + 1회 repair, unit fake provider + live smoke).
- Phase 4 후속 추적 의무: ContextPackage Writing용/Analysis 비교용 모두 완성(§8 C), `needs_review` candidate 포함 확장(§5 B), tool-call planner 전환(§2.1).
- Actual ChromaDB/Elasticsearch mutation, stale-hit sync job, `analysis_completed` wiring은 후속이다.
