# Decision brief — Phase 3B index sync/outbox

상태: `Proposed for owner approval`  
정본 연결: [`../system-contract-sot.md`](../system-contract-sot.md), [`03-indexing.md`](03-indexing.md), [`03-indexing-kickoff-decisions.md`](03-indexing-kickoff-decisions.md)  
목적: Phase 3A explicit rebuild와 stale validation 이후, automatic sync/outbox 첫 구현이 inline adapter 호출이나 외부 queue 선택을 추측하지 않도록 범위를 좁힌다.

## 현재 확정된 경계

- MongoDB가 정본이고 ChromaDB/Elasticsearch는 단방향 파생 index다.
- Phase 3A public rebuild 표면은 CLI script와 HTTP command endpoint이며, 둘 다 deterministic fake vector adapter를 사용한다.
- Phase 3A `IndexSyncRequest`/`IndexSyncResult`는 explicit rebuild용 in-process 축소 계약이다.
- `contracts.md` §7.2~7.3과 `mongo_collections.md` §39의 persistent sync envelope는 후속 sync log/outbox slice 범위다.
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

추천: **A**. `index_sync_logs`는 이미 Mongo collection 목록에 있고 status index도 있다. 첫 slice는 status를 `pending|running|succeeded|failed`로 확장하는 계약 브리프/SoT 보강 뒤 구현한다.

## 4. 첫 구현 slice 제안

승인되면 다음 코드 slice는 아래로 제한한다.

1. `IndexSyncEvent`/`IndexSyncLog` domain model 추가
   - event literal: `project_archived`, `draft_archived`
   - source: `mongo_collection`, `mongo_id`, optional `mongo_version`
   - target: `vector`
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
   - archive read preservation remains unchanged
   - outbox target is `vector`, not real Chroma/ES

## 승인 전 보류

- 실제 ChromaDB adapter
- Elasticsearch adapter/analyzer
- polling worker loop
- retry/backoff policy
- stale-hit detection에서 sync 요청을 만드는 query/Context Gate wiring
- `draft_saved` 자동 색인
