# Decision brief — Phase 3 indexing kickoff

상태: `Approved for Phase 3A first slice`
정본 연결: [`../system-contract-sot.md`](../system-contract-sot.md), [`03-indexing.md`](03-indexing.md)  
목적: Phase 3 첫 구현 slice가 Chroma/Elasticsearch/동기화 방식을 추측하지 않도록 MVP 범위를 좁힌다.

## 현재 확정된 경계

- MongoDB가 정본이다.
- ChromaDB와 Elasticsearch는 MongoDB pointer/version/status를 가진 파생 인덱스다.
- index hit는 SOT 재조회 전까지 정본이 아니다.
- MongoDB 정본 저장은 index adapter 실패 때문에 rollback되지 않는다.
- Phase 2B는 Phase 3~4 이후 prior memory를 검색해 후보를 만든다.

## 구현을 막는 미확정 항목

1. 첫 인덱스 대상: source block만, analysis candidate만, 둘 다
2. 첫 backend: Chroma만, Elasticsearch만, 둘 다
3. embedding model/dimension
4. sync delivery: inline best-effort, outbox/polling, external queue
5. archive/delete 반영: hard delete, tombstone, version/status filter
6. stale hit 판정 literal과 rebuild 단위

## 1. 첫 인덱스 대상

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. source block only | Core SOT snapshot/source_block을 색인한다 | Phase 1 산출물만으로 시작 가능 | Phase 2A candidate 검색은 후속 |
| B. analysis candidate only | Phase 2A candidate를 색인한다 | prior memory 검색에 가까움 | 승인 전 `needs_review` 후보의 검색 지위가 애매함 |
| C. source block + needs_review candidate | 둘 다 색인한다 | 검색 재료가 풍부함 | 첫 slice가 커지고 stale/status 규칙이 복잡함 |

추천: **A**. 이유는 Core SOT source block은 이미 immutable pointer/hash/version 계약이 있고, Phase 3의 "index hit는 정본이 아님" 규칙을 가장 작게 잠글 수 있기 때문이다. Candidate indexing은 review/canonical 지위가 정해진 뒤 확장한다.

## 2. 첫 backend

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. Chroma contract only | vector record mapping과 fake adapter부터 구현 | Phase 4 semantic search 준비에 직결 | lexical/name search는 후속 |
| B. Elasticsearch contract only | lexical/metadata record mapping부터 구현 | 이름/고유명사 검색이 빠름 | embedding 결정은 계속 남음 |
| C. 둘 다 | Chroma+ES 동시 구현 | 최종 그림과 가까움 | 첫 slice가 커짐 |

추천: **A**. 이유는 Phase 4 Agentic Search가 먼저 semantic 후보 검색을 필요로 하고, ES analyzer/nori 배포 결정은 운영 선택지가 더 많아 별도 결정 비용이 크다.

## 3. Embedding model/dimension

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. fake embedding only | deterministic fake vector로 contract/test를 먼저 잠근다 | 모델 선택 없이 schema/idempotency/stale 규칙 구현 가능 | 실제 검색 품질 미검증 |
| B. local embedding model 즉시 선택 | 예: sentence-transformers 계열 | 실제 vector dimension 고정 가능 | dependency/model 품질 결정을 지금 해야 함 |
| C. Gateway LLM embedding endpoint 대기 | 별도 Gateway embedding surface 후 진행 | 서빙 경계 통일 | Gateway contract가 아직 없음 |

추천: **A**. 첫 slice는 `EmbeddingProvider` Protocol과 deterministic fake dimension을 사용한다. 실제 embedding model/dimension은 live quality spike 후 SoT에 올린다.

## 4. Sync delivery

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. explicit rebuild/index command | API 저장 경로와 분리된 수동/테스트용 sync 호출 | 정본 write rollback 위험 없음, 단순 | 자동 최신화는 후속 |
| B. inline best-effort after save | save API가 index sync도 시도 | 사용자는 즉시 검색 가능 | adapter 실패와 API 응답 의미가 복잡함 |
| C. outbox/polling | Mongo outbox에 event 저장 후 worker가 처리 | 장기적으로 안전 | worker/outbox 계약을 지금 정해야 함 |

추천: **A**. MVP 첫 slice는 `rebuild_snapshot_index(project_id, snapshot_id)` 같은 explicit service method와 script/API 후보로 제한한다. 자동 outbox는 Phase 3B로 둔다.

## 5. Archive/delete 반영

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. status/version filter | record에 `project_archived`, `draft_archived`, `snapshot_version` 등을 두고 query에서 제외 | Mongo 정본 보존과 일치, hard delete 불필요 | query filter를 반드시 강제해야 함 |
| B. tombstone record | stale/tombstone marker를 별도 기록 | stale reason 추적 용이 | record shape 증가 |
| C. hard delete from index | archive 시 index record 삭제 | 검색 노출 방지 단순 | rebuild/debug provenance가 약해짐 |

추천: **A**. Phase 1 archive는 read-allowed이고 정본은 보존되므로, 첫 slice는 index record metadata와 query filter로 archived/stale record를 사용하지 않는 것을 잠근다.

## 6. 첫 구현 slice 제안

승인되면 다음 코드 slice는 아래로 제한한다.

1. `services/application/app/indexing/`에 pure domain model 추가
   - `IndexRecordKind.SOURCE_BLOCK`
   - `IndexPointer(project_id, collection, document_id, version_id, content_hash)`
   - `IndexSyncRequest(project_id, snapshot_id, target)`, `IndexSyncResult(request, records_attempted, records_written)`
2. deterministic fake embedding provider와 in-memory vector index adapter
3. Core SOT snapshot/source block → index record mapping
4. explicit `rebuild_snapshot_source_block_index(project_id, snapshot_id)` service
5. 회귀
   - same snapshot rebuild idempotency
   - project isolation
   - pointer/version/hash 보존
   - archived project/draft record가 query 결과에서 제외
   - adapter failure가 Core SOT 저장 결과를 rollback하지 않음

## 승인 결과

2026-07-02 사용자 요청("다음 슬라이스 진행, 작은것부터 구현")으로 추천안을 첫 코드 slice 범위로 승인했다. Phase 3A 첫 구현은 다음 계약으로 시작한다.

- target: source block only
- backend: Chroma-like vector contract with deterministic fake adapter
- embedding: fake provider only, real model deferred
- delivery: explicit rebuild/index command only
- archive/delete: status/version filter, no hard delete in first slice

`IndexSyncRequest`/`IndexSyncResult`는 Phase 3A explicit rebuild용 in-process 축소 계약이다. `contracts.md` §7.3의 persistent sync log/outbox envelope(`sync_result_id`, `sync_request_id`, target별 결과, timestamps)는 후속 sync log slice에서 다룬다. Archive/delete status filter는 rebuild가 materialize한 `project_archived`/`draft_archived` metadata 기준으로 적용되며, archive 이후 기존 stale record를 즉시 숨기려면 재build 또는 후속 automatic sync가 필요하다.

실제 embedding model, Elasticsearch analyzer, automatic sync/outbox, analysis candidate indexing은 후속 결정으로 남긴다.

## 구현 후속 — explicit rebuild script

2026-07-02 Phase 3A 후속 작은 slice로 `scripts/phase3a_rebuild_source_block_index.py`를 추가했다. 이 script는 `--project-id`, `--snapshot-id`, `CORE_SOT_MONGO_URI`/`--mongo-uri`를 받아 Core SOT MongoDB에서 snapshot blocks를 읽고 deterministic fake vector adapter로 explicit rebuild를 실행한다. 출력은 JSON summary(`project_id`, `snapshot_id`, `target`, `records_attempted`, `records_written`, `records_indexed`, `records_query_visible`, `records_archived`)다. Exit code는 full write 성공 0, partial write 1, usage/config/domain error 2다. Application HTTP API endpoint와 persistent vector backend는 후속이다.
