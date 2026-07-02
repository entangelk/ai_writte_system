# Decision brief — Phase 3B index sync/outbox

상태: `Proposed for owner approval`  
정본 연결: [`../system-contract-sot.md`](../system-contract-sot.md), [`03-indexing.md`](03-indexing.md), [`03-indexing-kickoff-decisions.md`](03-indexing-kickoff-decisions.md)  
목적: Phase 3A explicit rebuild와 stale validation 이후, automatic sync/outbox 첫 구현이 inline adapter 호출이나 외부 queue 선택을 추측하지 않도록 범위를 좁힌다.

## 현재 확정된 경계

- MongoDB가 정본이고 ChromaDB/Elasticsearch는 단방향 파생 index다.
- Phase 3A public rebuild 표면은 CLI script와 HTTP command endpoint이며, 둘 다 deterministic fake vector adapter를 사용한다.
- Phase 3A `IndexSyncRequest`/`IndexSyncResult`는 explicit rebuild용 in-process 축소 계약이다.
- `contracts.md` §7.2~7.3과 `mongo_collections.md` §39의 persistent sync envelope는 후속 sync log/outbox slice 범위다.
- `mongo_collections.md` §64는 stale hit 발견 시 context에서 제외하고 index sync job을 만든다고 적는다. 다만 §64는 `mongo_version` 기준 예시이고, Phase 3A source-block validator는 `content_hash`와 draft/block pointer 정합성 기준이므로, stale-hit 기반 sync job을 구현하기 전에 이 기준을 다시 맞춰야 한다.
- `validate_source_block_record(record)`는 stale hit 사용 전 Core SOT를 재조회하는 guard이며, automatic sync나 queue 처리를 대신하지 않는다.

## 구현을 막는 미확정 항목

1. 첫 automatic event source: `draft_saved`, archive events, stale-hit detection, analysis completion 중 무엇부터 처리할지
2. delivery 방식: inline best-effort, Mongo outbox/polling, 외부 queue 중 무엇을 정본 계약으로 삼을지
3. outbox/log 저장 단위: sync request와 sync result를 한 collection에 같이 둘지, queue와 result log를 분리할지
4. archive 반영 방식: derived index hard delete, tombstone, stale/status filter 중 무엇을 자동 처리할지
5. retry/backoff와 terminal failure literal
6. fake vector adapter 단계에서 persistent log만 먼저 잠글지, 실제 Chroma adapter까지 같이 붙일지

## 1. 첫 automatic event source

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. `draft_saved` | 새 snapshot 저장 직후 source block index sync 요청을 만든다 | 최신 snapshot 검색 준비에 직결 | save path와 index freshness 기대가 바로 결합됨 |
| B. archive events | `project_archived`/`draft_archived` 후 기존 derived hit를 stale 처리하도록 sync 요청을 만든다 | Phase 3A의 남은 stale exposure gap을 직접 줄임 | 새 content indexing 자동화는 여전히 후속 |
| C. stale-hit detection | query/Context Gate가 stale hit를 발견할 때 sync 요청을 만든다 | 실제 stale 발견 지점과 복구가 연결됨 | query/Context Gate wiring이 아직 없음 |
| D. `analysis_completed` | Phase 2A candidate 생성 후 index sync 요청을 만든다 | `contracts.md` 예시와 가까움 | candidate indexing/review 지위가 아직 미확정 |

추천: **B**. 이유는 Phase 3A가 이미 source block explicit rebuild와 stale validation을 잠갔고, HANDOFF의 남은 gap도 archive 후 기존 materialized record를 즉시 숨기는 automatic sync다. `draft_saved` 자동 색인은 사용자 기대가 크지만 save API latency/rollback semantics가 더 복잡하므로 별도 slice로 둔다.

## 2. Delivery 방식

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. inline best-effort | archive API가 index adapter를 직접 호출한다 | 구현이 가장 작음 | adapter 실패가 API 응답 의미를 흐리고 rollback 오해를 만든다 |
| B. Mongo outbox/polling | archive API는 outbox entry만 기록하고 worker가 처리한다 | 정본 write와 derived sync 실패를 분리한다 | queue/log 계약을 먼저 정해야 한다 |
| C. external queue | Redis/Kafka 등 외부 queue에 event를 발행한다 | 운영 확장성이 좋다 | 현재 repo/compose에 없는 dependency를 추측하게 된다 |

추천: **B**. Core SOT archive는 성공해야 하고 derived index sync 실패가 archive write를 되돌리면 안 된다. 첫 slice는 Mongo collection 기반 outbox entry 생성까지만 잠그고, worker loop와 adapter execution은 후속으로 둔다.

## 3. 저장 단위

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. `index_sync_logs` 단일 collection | pending request와 completed result를 같은 document lifecycle로 관리한다 | 기존 `mongo_collections.md` §39 이름과 index를 재사용 | pending 상태 필드가 §39 예시보다 넓어진다 |
| B. `index_sync_outbox` + `index_sync_logs` 분리 | queue와 history를 분리한다 | lifecycle이 명확함 | 새 collection/schema를 추가해야 한다 |
| C. in-memory queue only | 테스트용 queue만 둔다 | 가장 작음 | restart/retry/운영 가시성 수용 기준을 못 잠근다 |

추천: **A**. `index_sync_logs`는 이미 Mongo collection 목록에 있고 status index도 있다. 첫 slice는 pending request와 completed result를 같은 document lifecycle로 다룰 수 있게 하되, 아래 schema lock을 승인받은 뒤 구현한다.

## 4. 승인 전 schema lock

첫 code slice 전에 아래 항목은 조용히 추측하지 않는다.

1. status literal
   - `contracts.md` §7.3과 `mongo_collections.md` §39의 완료 literal은 `success`다.
   - 추천: terminal 성공은 기존 `success`를 재사용하고, lifecycle status는 `pending|running|success|failed`로 둔다.
   - `succeeded`를 쓰려면 §7.3/§39/SoT를 함께 갱신해야 한다.
2. target shape
   - `contracts.md` §7.2는 request를 `targets: ["chroma", "elasticsearch"]` list로, §7.3/§39는 result/log를 `targets: {chroma: {...}, elasticsearch: {...}}` object로 표현한다.
   - Phase 3A의 `target="vector"`는 explicit rebuild용 in-process 축소명이다.
   - 추천: persistent `index_sync_logs`에는 `target: "vector"` 단수 field를 저장하지 않는다. 첫 pending outbox entry는 canonical envelope에 맞춰 `targets`를 쓰고, 실제 backend가 fake인 동안에는 `targets.chroma.status="pending"`과 별도 `backend="in_memory_fake"` 또는 equivalent field로 runtime backend를 드러낸다.
   - 오너가 `vector`를 persistent target literal로 유지하려면 §7.2/§7.3/§39와 SoT에 reduced persistent target 예외를 명시해야 한다.
3. project/user scope
   - `project_id`는 필수다. §39 index와 project isolation 수용 기준, outbox dedup 모두 `project_id`에 의존한다.
   - `user_id`는 §39 예시에 있지만 현재 Core SOT/API 흐름에는 user model이 아직 없으므로 첫 slice에서는 `user_id`를 명시적으로 deferred/nullable로 둘지 결정해야 한다. 조용히 생략하지 않는다.
4. idempotency key
   - 추천 dedup key: `(project_id, event, source.mongo_collection, source.mongo_id)`.
   - `project_archived`의 source는 `projects/{project_id}`, `draft_archived`의 source는 `drafts/{draft_id}`다.
   - 같은 archive endpoint를 반복 호출해도 같은 key의 pending entry가 하나만 남아야 한다.
   - versioned content sync(`draft_saved`, stale-hit repair 등)를 추가할 때는 `mongo_version` 또는 `content_hash` 포함 여부를 별도 결정한다.
5. stale-hit sync job
   - `mongo_collections.md` §64의 stale-hit → sync job은 이 브리프의 option C에 해당한다.
   - 이번 추천은 archive events를 먼저 다루며, §64 경로는 query/Context Gate wiring 이후 별도 slice로 둔다.
   - 그때 §64의 `mongo_version` 기준과 Phase 3A source-block `content_hash` 기준을 SoT에서 reconcile한다.

## 5. 첫 구현 slice 제안

승인되면 다음 코드 slice는 아래로 제한한다.

1. `IndexSyncEvent`/`IndexSyncLog` domain model 추가
   - event literal: `project_archived`, `draft_archived`
   - `project_id`: required
   - `user_id`: deferred/nullable until user ownership is modeled
   - source: `mongo_collection`, `mongo_id`, optional `mongo_version`
   - targets: canonical `targets` shape; first recommended logical target is `chroma` with `backend="in_memory_fake"` while the fake vector adapter is still in use
   - status: `pending`
2. `CoreSotService.archive_project()`와 `archive_draft()` 성공 후 outbox entry 생성
   - outbox write 실패는 archive write rollback 여부를 명시한 뒤 구현한다.
   - 첫 추천은 same Mongo transaction/fallback unit에 포함하는 것이다. 이유는 event 생성이 "archive가 발생했다"는 SOT-side fact이기 때문이다.
3. Worker/adapter execution은 구현하지 않는다.
   - 즉, Chroma/Elasticsearch write, retry/backoff, hard delete/tombstone 처리는 후속이다.
4. 회귀
   - project archive creates one pending `project_archived` sync log
   - draft archive creates one pending `draft_archived` sync log
   - repeated archive is idempotent with respect to outbox event
   - dedup key is `(project_id, event, source.mongo_collection, source.mongo_id)`
   - archive read preservation remains unchanged
   - outbox uses canonical `targets` shape and does not silently persist Phase 3A's reduced `target="vector"` field

## 승인 전 보류

- 실제 ChromaDB adapter
- Elasticsearch adapter/analyzer
- polling worker loop
- retry/backoff policy
- stale-hit detection에서 sync 요청을 만드는 query/Context Gate wiring
- `draft_saved` 자동 색인
