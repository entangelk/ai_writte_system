# Decision brief — Phase 3B index sync/outbox

상태: `Approved; first archive outbox slice implemented`
정본 연결: [`../system-contract-sot.md`](../system-contract-sot.md), [`03-indexing.md`](03-indexing.md), [`03-indexing-kickoff-decisions.md`](03-indexing-kickoff-decisions.md)  
목적: Phase 3A explicit rebuild와 stale validation 이후, automatic sync/outbox 첫 구현이 inline adapter 호출이나 외부 queue 선택을 추측하지 않도록 범위를 좁힌다.

## Owner decisions — 2026-07-03

- 첫 automatic event source는 추천안 **B. archive events**를 채택한다. 다만 오너는 **D. `analysis_completed`**가 장기적으로 가장 맞는 흐름이라고 판단했으므로, 첫 slice는 archive events만 구현하되 event/source schema는 `analysis_completed`를 후속으로 추가할 수 있게 닫지 않는다.
- Delivery 방식은 추천안 **B. Mongo outbox/polling**을 채택한다. 외부 queue 운영 확장성은 현재 로컬 1인 프로젝트 단계에서는 고려하지 않는다.
- 저장 단위는 기존 추천안 A가 아니라 **B. `index_sync_outbox` + `index_sync_logs` 분리**를 채택한다. 이유는 상태 필드가 계속 늘어날 가능성이 높고, 개인 사용 환경에서도 request lifecycle과 completed history를 정확히 조인할 수 있어야 하기 때문이다.
- Archive 반영 방식은 **C first, B later**를 채택한다. 첫 구현은 outbox 기록 + stale validation guard로 사용 안전성을 확보하고, 후속 worker/adapter slice에서 정리 가능하도록 tombstone/status update를 우선 검토한다.
- Retry/backoff는 **B. bounded local retry metadata**를 채택한다. 서버/backend 계열 오류와 데이터 없음/not-found 계열 오류는 서로 다른 `error_type`을 사용해야 하며, 둘 다 기본 `max_attempts=3`으로 시작한다.
- Fake vector 단계는 **A. persistent log만 먼저**를 채택한다. 품질, embedding model, Chroma/Elasticsearch 실제 adapter는 핵심 코어가 끝난 뒤 최후속으로 다룬다.
- 첫 archive outbox code slice는 구현됐다. Worker loop, Chroma/Elasticsearch adapter execution, retry 실행, `analysis_completed` wiring은 별도 code slice로 진행한다.

## 현재 확정된 경계

- MongoDB가 정본이고 ChromaDB/Elasticsearch는 단방향 파생 index다.
- Phase 3A public rebuild 표면은 CLI script와 HTTP command endpoint이며, 둘 다 deterministic fake vector adapter를 사용한다.
- Phase 3A `IndexSyncRequest`/`IndexSyncResult`는 explicit rebuild용 in-process 축소 계약이다.
- `contracts.md` §7.2~7.3과 `mongo_collections.md` §39의 persistent sync envelope는 후속 sync log/outbox slice 범위다.
- `mongo_collections.md` §64는 stale hit 발견 시 context에서 제외하고 index sync job을 만든다고 적는다. 다만 §64는 `mongo_version` 기준 예시이고, Phase 3A source-block validator는 `content_hash`와 draft/block pointer 정합성 기준이므로, stale-hit 기반 sync job을 구현하기 전에 이 기준을 다시 맞춰야 한다.
- `validate_source_block_record(record)`는 stale hit 사용 전 Core SOT를 재조회하는 guard이며, automatic sync나 queue 처리를 대신하지 않는다.

## 구현을 막던 항목과 현재 처리

1. 첫 automatic event source: archive events를 먼저 채택하고, `analysis_completed`는 후속 확장 경로로 명시한다.
2. delivery 방식: Mongo outbox/polling을 채택하고, 외부 queue는 현재 단계에서 제외한다.
3. outbox/log 저장 단위: `index_sync_outbox` + `index_sync_logs` 분리로 채택한다.
4. archive 반영 방식: 첫 slice는 outbox 기록까지만 처리하고, hit 사용 안전성은 stale validation guard가 담당한다. 실제 derived index mutation은 후속 worker/adapter slice에서 tombstone/status update를 우선 검토한다.
5. retry/backoff와 terminal failure literal: schema는 bounded local retry metadata를 수용한다. `backend_error`와 `not_found`는 다른 error type이며 둘 다 `max_attempts=3`으로 시작한다. Retry 실행은 worker slice에서 확정한다.
6. fake vector adapter 단계: persistent outbox/log 계약만 먼저 잠그고, 실제 Chroma adapter는 후속으로 둔다.

## 1. 첫 automatic event source

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. `draft_saved` | 새 snapshot 저장 직후 source block index sync 요청을 만든다 | 최신 snapshot 검색 준비에 직결 | save path와 index freshness 기대가 바로 결합됨 |
| B. archive events | `project_archived`/`draft_archived` 후 기존 derived hit를 stale 처리하도록 sync 요청을 만든다 | Phase 3A의 남은 stale exposure gap을 직접 줄임 | 새 content indexing 자동화는 여전히 후속 |
| C. stale-hit detection | query/Context Gate가 stale hit를 발견할 때 sync 요청을 만든다 | 실제 stale 발견 지점과 복구가 연결됨 | query/Context Gate wiring이 아직 없음 |
| D. `analysis_completed` | Phase 2A candidate 생성 후 index sync 요청을 만든다 | 오너가 장기적으로 가장 맞는 흐름으로 판단했고, `contracts.md` 예시와도 가까움 | candidate indexing/review 지위가 아직 미확정 |

채택: **B**. 이유는 Phase 3A가 이미 source block explicit rebuild와 stale validation을 잠갔고, HANDOFF의 남은 gap도 archive 후 기존 materialized record를 즉시 숨기는 automatic sync다. `draft_saved` 자동 색인은 사용자 기대가 크지만 save API latency/rollback semantics가 더 복잡하므로 별도 slice로 둔다.

후속 고려: **D**를 schema에서 닫지 않는다. `IndexSyncEvent`는 첫 code slice에서 `project_archived|draft_archived`만 허용하지만, `source` 구조와 dedup key는 후속 `analysis_completed`가 `analysis_jobs`/`analysis_candidates` 같은 source collection을 가리킬 수 있게 일반적인 `mongo_collection`/`mongo_id`/optional version 형태로 둔다. `analysis_completed`를 실제로 켜는 시점에는 candidate review status와 indexed representation을 먼저 확정한다.

## 2. Delivery 방식

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. inline best-effort | archive API가 index adapter를 직접 호출한다 | 구현이 가장 작음 | adapter 실패가 API 응답 의미를 흐리고 rollback 오해를 만든다 |
| B. Mongo outbox/polling | archive API는 outbox entry만 기록하고 worker가 처리한다 | 정본 write와 derived sync 실패를 분리한다 | queue/log 계약을 먼저 정해야 한다 |
| C. external queue | Redis/Kafka 등 외부 queue에 event를 발행한다 | 운영 확장성이 좋다 | 현재 repo/compose에 없는 dependency를 추측하게 된다 |

채택: **B**. Core SOT archive는 성공해야 하고 derived index sync 실패가 archive write를 되돌리면 안 된다. 첫 slice는 Mongo collection 기반 outbox entry 생성까지만 잠그고, worker loop와 adapter execution은 후속으로 둔다. 외부 queue는 현재 로컬 1인 프로젝트 단계에서 운영 복잡도만 늘리므로 고려하지 않는다.

## 3. 저장 단위

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. `index_sync_logs` 단일 collection | pending request와 completed result를 같은 document lifecycle로 관리한다 | 기존 `mongo_collections.md` §39 이름과 index를 재사용 | pending/running/retry 상태 필드가 §39 예시보다 넓어지고 history query와 queue claim query가 섞인다 |
| B. `index_sync_outbox` + `index_sync_logs` 분리 | queue와 history를 분리한다 | lifecycle이 명확하고, status/retry/claim 필드가 늘어도 completed history와 정확히 조인 가능 | 새 collection/schema와 조인 key를 추가해야 한다 |
| C. in-memory queue only | 테스트용 queue만 둔다 | 가장 작음 | restart/retry/운영 가시성 수용 기준을 못 잠근다 |

채택: **B**. `index_sync_outbox`는 pending/running/failure-retry lifecycle을 소유하고, `index_sync_logs`는 completed or terminal attempt history를 소유한다. 두 collection은 `sync_request_id`로 조인한다. 같은 archive endpoint를 반복 호출해도 `index_sync_outbox`에는 dedup key 기준으로 active request가 하나만 남아야 하고, worker execution이 생긴 뒤 attempt별 결과는 `index_sync_logs`에 append한다.

## 4. Archive 반영 방식

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. derived index hard delete | archive event 처리 시 Chroma/ES record를 삭제한다 | archive 후 노출 위험이 작음 | Mongo archive가 정본 삭제가 아니므로 재build/감사/복구 의미가 흐려질 수 있음 |
| B. tombstone/status update | derived index record에 archived/tombstone metadata를 반영한다 | 정본 보존 정책과 맞고 stale 원인 추적이 가능 | 실제 Chroma/ES adapter별 update/delete semantics를 나중에 정해야 함 |
| C. stale/status filter + validation | query filter와 `validate_source_block_record()`가 archived hit 사용을 막는다 | Phase 3A와 바로 연결되고 backend 선택을 추측하지 않음 | automatic sync 처리 전 materialized backend 상태는 남아 있을 수 있음 |

채택: **C first, B later**. 첫 code slice는 archive event를 outbox에 기록하는 데서 멈추고, 실제 derived index mutation은 하지 않는다. 현재 사용 안전성은 Phase 3A의 stale validation guard가 담당한다. Worker/adapter slice가 열리면 hard delete보다 tombstone/status update를 우선 검토한다. 이유는 project/draft archive가 Mongo 정본 삭제가 아니라 읽기 허용 보존 상태이기 때문이다.

## 5. Retry/backoff와 terminal failure literal

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. retry 없음 | 실패하면 바로 terminal failure로 둔다 | 구현이 가장 작음 | transient Chroma/ES 오류에 취약 |
| B. bounded local retry metadata | outbox entry가 attempt count, next_attempt_at, last_error를 가진다 | 외부 queue 없이도 재시도/운영 가시성을 열 수 있음 | worker claim/retry 구현 시 clock/claim 규칙을 정해야 함 |
| C. external queue retry policy | Redis/Kafka/Celery 등으로 위임한다 | 운영 기능이 풍부함 | 현재 로컬 1인 프로젝트 범위를 벗어난다 |

채택: **B contract, execution later**. 첫 code slice는 retry를 실행하지 않지만 `index_sync_outbox` schema는 `attempt_count`, `max_attempts`, `next_attempt_at`, `last_error`, `status`를 담을 수 있게 둔다. 상태 literal은 `pending|running|success|failed`를 기본으로 한다. 완료 성공 literal은 기존 §7.3/§39의 `success`를 재사용한다. Terminal failure literal은 `failed`로 둔다. 서버/backend 계열 오류는 `backend_error`, 데이터 없음/not-found 계열 오류는 `not_found`로 분리하며 둘 다 기본 `max_attempts=3`이다. Backoff 숫자와 claim timeout은 worker slice에서 확정한다.

## 6. Fake vector 단계와 실제 adapter 도입

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. persistent log만 먼저 | fake backend를 명시한 outbox/log 계약만 잠근다 | 외부 dependency 없이 archive to sync request 계약을 검증 | 실제 Chroma write 품질은 후속 |
| B. Chroma adapter까지 같이 구현 | outbox와 실제 vector mutation을 한 번에 연결한다 | end-to-end 효과가 바로 보임 | embedding model/dimension/backend 배포를 추측하게 됨 |
| C. Chroma+Elasticsearch 동시 구현 | 최종 구조에 가까움 | 현재 미확정 항목을 가장 많이 동시에 결정해야 함 |

채택: **A**. 첫 Phase 3B code slice는 persistent outbox/log schema와 archive event 생성만 다룬다. Target envelope는 canonical `targets` shape를 쓰되, 실제 backend는 `backend="in_memory_fake"`로 드러낸다. ChromaDB adapter, embedding model/dimension, Elasticsearch analyzer, 품질 평가는 핵심 코어 구현 뒤 최후속으로 다룬다.

## 7. Schema lock

첫 code slice 전에 아래 항목을 기준으로 삼는다.

1. status literal
   - `contracts.md` §7.3과 `mongo_collections.md` §39의 완료 literal은 `success`다.
   - 채택: terminal 성공은 기존 `success`를 재사용하고, lifecycle status는 `pending|running|success|failed`로 둔다.
   - `succeeded`를 쓰려면 §7.3/§39/SoT를 함께 갱신해야 한다.
2. target shape
   - `contracts.md` §7.2는 request를 `targets: ["chroma", "elasticsearch"]` list로, §7.3/§39는 result/log를 `targets: {chroma: {...}, elasticsearch: {...}}` object로 표현한다.
   - Phase 3A의 `target="vector"`는 explicit rebuild용 in-process 축소명이다.
   - 기본값: persistent `index_sync_outbox`/`index_sync_logs`에는 `target: "vector"` 단수 field를 저장하지 않는다. 첫 pending outbox entry는 canonical envelope에 맞춰 `targets`를 쓰고, 실제 backend가 fake인 동안에는 `targets.chroma.status="pending"`과 별도 `backend="in_memory_fake"` 또는 equivalent field로 runtime backend를 드러낸다.
   - 오너가 `vector`를 persistent target literal로 유지하려면 §7.2/§7.3/§39와 SoT에 reduced persistent target 예외를 명시해야 한다.
3. project/user scope
   - `project_id`는 필수다. §39 index와 project isolation 수용 기준, outbox dedup 모두 `project_id`에 의존한다.
   - `user_id`는 §39 예시에 있지만 현재 Core SOT/API 흐름에는 user model이 아직 없으므로 첫 slice에서는 deferred/nullable로 둔다. 필드는 생략하지 않고 `null`을 허용해 후속 user ownership 계약이 생길 때 migration 지점을 남긴다.
4. idempotency key
   - Dedup key: `(project_id, event, source.mongo_collection, source.mongo_id)`.
   - `project_archived`의 source는 `projects/{project_id}`, `draft_archived`의 source는 `drafts/{draft_id}`다.
   - 같은 archive endpoint를 반복 호출해도 같은 key의 pending/active outbox entry가 하나만 남아야 한다.
   - versioned content sync(`draft_saved`, stale-hit repair 등)를 추가할 때는 `mongo_version` 또는 `content_hash` 포함 여부를 별도 결정한다.
5. stale-hit sync job
   - `mongo_collections.md` §64의 stale-hit to sync job은 이 브리프의 option C에 해당한다.
   - 이번 채택안은 archive events를 먼저 다루며, §64 경로는 query/Context Gate wiring 이후 별도 slice로 둔다.
   - 그때 §64의 `mongo_version` 기준과 Phase 3A source-block `content_hash` 기준을 SoT에서 reconcile한다.

## 8. 첫 구현 slice 제안

첫 archive outbox code slice는 아래 범위로 구현됐다.

1. `IndexSyncEvent`/`IndexSyncOutboxEntry`/`IndexSyncLog` domain model 추가
   - event literal: `project_archived`, `draft_archived`
   - 후속 event candidate: `analysis_completed`(아직 code enum에는 열지 않음)
   - `project_id`: required
   - `user_id`: nullable until user ownership is modeled
   - source: `mongo_collection`, `mongo_id`, optional `mongo_version`
   - targets: canonical `targets` shape; first logical target is `chroma` with `backend="in_memory_fake"` while the fake vector adapter is still in use
   - outbox status: `pending`
   - error type: `backend_error`, `not_found`
   - max attempts: `3`
2. Application archive endpoint가 `CoreSotService.archive_project()`와 `archive_draft()` 성공 후 outbox entry를 생성한다.
   - 첫 구현은 Application orchestration으로 붙였다. Core SOT transaction unit에 합치는 작업은 persistent worker/repository hardening slice에서 재검토한다.
3. Worker/adapter execution은 구현하지 않는다.
   - 즉, Chroma/Elasticsearch write, retry/backoff execution, hard delete/tombstone 처리는 후속이다.
4. 회귀
   - project archive creates one pending `project_archived` outbox entry
   - draft archive creates one pending `draft_archived` outbox entry
   - repeated archive is idempotent with respect to outbox event
   - dedup key is `(project_id, event, source.mongo_collection, source.mongo_id)`
   - archive read preservation remains unchanged
   - outbox uses canonical `targets` shape and does not silently persist Phase 3A's reduced `target="vector"` field
   - outbox/log split preserves joinability by `sync_request_id`

## 승인 전 보류

- 실제 ChromaDB adapter
- Elasticsearch adapter/analyzer
- polling worker loop
- retry/backoff execution and numeric policy
- stale-hit detection에서 sync 요청을 만드는 query/Context Gate wiring
- `analysis_completed` sync event wiring
- `draft_saved` 자동 색인
