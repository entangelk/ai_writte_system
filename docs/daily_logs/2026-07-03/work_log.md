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

## Next steps

- Actual ChromaDB/Elasticsearch mutation, stale-hit sync job, `analysis_completed` wiring은 후속이다.
