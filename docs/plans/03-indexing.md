# Phase 3. Indexing

상태: `Draft`  
선행 조건: Phase 1 정본 pointer/version, Phase 2 검색 대상 후보 계약  
후속 소비자: Agentic Search

## 목표

MongoDB 정본을 바꾸지 않는 단방향 검색 인덱스를 구축하고, stale 결과를 검출·복구할 수 있게 한다.

## 역할 구분

- ChromaDB: 유사 장면, 분위기, 의미적 관련성 후보 검색
- Elasticsearch: 이름, 별칭, 고유명사, 대사, 상태와 metadata 필터
- MongoDB: 최종 본문, 상태, version, canon의 정본

## MVP 범위

- 단일 Chroma collection `project_memory_vectors` 후보
- 단일 Elasticsearch index `writing_memory_search` 후보
- source block과 Phase 2에서 합의된 구조화 기억의 index representation
- Mongo pointer, `project_id`, kind, version, status metadata
- `index_sync_outbox` + `index_sync_logs`
- upsert/delete/rebuild와 stale check
- adaptive chunking, semantic chunking, 길이 기반 episode/section chunking은 후속 파생 index 전략 후보로 둔다. 이들은 MongoDB raw snapshot/source_ref 정본을 대체하지 않으며, 도입 시 Mongo pointer/version/hash로 재조회 가능해야 한다.

collection/index 분리는 사용량과 mapping 요구가 확인된 뒤 검토한다.

2026-07-02 Phase 3A 첫 slice는 [`03-indexing-kickoff-decisions.md`](03-indexing-kickoff-decisions.md)에 따라 더 작게 시작한다. 첫 구현은 source block only, Chroma-like vector contract with deterministic fake adapter, fake embedding only, explicit snapshot rebuild, archive/status filter만 다룬다. `IndexSyncRequest(project_id, snapshot_id, target)`와 `IndexSyncResult(request, records_attempted, records_written)`는 explicit rebuild용 in-process 축소 계약이며, `contracts.md` §7.3의 persistent sync log/outbox envelope는 후속 sync log slice에서 다룬다. `scripts/phase3a_rebuild_source_block_index.py`는 `project_id + snapshot_id` explicit rebuild를 Core SOT MongoDB 기반 JSON summary와 exit code(0 full write, 1 partial write, 2 usage/config/domain error)로 노출한다. Application HTTP API `POST /projects/{project_id}/snapshots/{snapshot_id}/index/source-blocks/rebuild`도 같은 rebuild를 `backend="in_memory_fake"` summary로 노출한다. `scripts/phase3a_deployed_rebuild_smoke.py`는 이미 떠 있는 Application HTTP endpoint로 snapshot을 만든 뒤 HTTP rebuild를 실행하고, `--mongo-uri`가 있으면 같은 snapshot을 CLI rebuild 경로로도 읽어 두 public summary를 비교한다. `validate_source_block_record(record)`는 query/Context Gate 계층이 hit 사용 전에 Core SOT 정본을 재조회해 `project_archived`, `draft_archived`, `snapshot_missing`, `draft_mismatch`, `content_hash_mismatch`, `block_missing` stale reason을 확인하는 explicit guard다. `snapshot_missing`은 단독 reason으로 short-circuit하며, drift 판정은 `version_id`가 아니라 `content_hash`와 draft/block pointer 정합성 기준이다. 실제 ChromaDB, Elasticsearch, 자동 outbox/polling, analysis candidate indexing은 후속 결정이다.

2026-07-03 automatic sync/outbox의 첫 구현 범위는 [`03-index-sync-outbox-decisions.md`](03-index-sync-outbox-decisions.md)에 owner-approved 브리프로 정리했고, archive outbox 첫 code slice를 구현했다. 첫 automatic event source는 archive events(`project_archived`, `draft_archived`)이며, 오너가 장기적으로 더 맞는 흐름으로 본 `analysis_completed`는 후속 event candidate로 열어 둔다(아직 code enum에는 열지 않음). Delivery는 로컬 1인 runtime 기준 외부 queue 없이 Mongo outbox/polling으로 시작한다. 저장 단위는 단일 `index_sync_logs`가 아니라 `index_sync_outbox` + `index_sync_logs` 분리이며, 두 collection은 `sync_request_id`로 조인한다. Application archive endpoint는 Core SOT archive 성공 후 canonical `targets` shape(`targets.chroma.status="pending"`, `targets.chroma.backend="in_memory_fake"`)의 pending outbox entry를 idempotent하게 생성한다. Dedup key는 `(project_id, event, source.mongo_collection, source.mongo_id)`다. Retry metadata는 `attempt_count`, `max_attempts=3`, `next_attempt_at`, `last_error`를 둔다. 서버/backend 계열 오류와 데이터 없음/not-found 계열 오류는 각각 `backend_error`, `not_found`로 분리한다. Actual ChromaDB/Elasticsearch mutation, stale-hit sync job, `analysis_completed` wiring은 후속이다.

2026-07-03 worker/retry 실행 경계는 [`03-index-worker-retry-decisions.md`](03-index-worker-retry-decisions.md)에 정리했고, one-shot worker 첫 slice를 구현했다. 첫 worker는 one-shot command로 실행하고, 장기적으로 UI-triggered background/daemon이 같은 service를 재사용할 수 있게 둔다. Claim timeout은 10분이며, `claimed_at` lease timestamp로 stale running을 판정한다. Backoff는 `max_attempts=3` 기준 1분 → 5분 → terminal `failed`다. Terminal-location/index 전략은 terminal 이동을 채택해 `success|failed`가 되면 active outbox entry를 제거하고 terminal history는 `index_sync_logs`가 소유한다. Archive worker-time `not_found`는 idempotent success로 처리한다. Query-time `not_found`는 후속 LLM orchestration/query selector retry loop의 error type으로 남긴다. Dedup은 `pending|running` active entry에만 적용한다.

## 단방향 동기화

```text
MongoDB change → index_sync_outbox pending request
→ worker/adapter execution → index_sync_logs attempt/result history
```

ChromaDB나 Elasticsearch 검색 결과가 MongoDB 기억을 직접 갱신해서는 안 된다.

## 동기화 이벤트 후보

- `draft_saved`
- `analysis_completed`
- `entity_confirmed`, `entity_updated`
- `foreshadowing_resolved`
- `canon_changed`
- `voice_sample_added`
- `draft_deleted`, `project_archived`

첫 automatic event는 `project_archived`/`draft_archived`로 축소 확정됐다. `analysis_completed`는 오너가 장기적으로 가장 맞는 흐름으로 본 후속 event candidate지만, candidate indexing/review 지위가 확정될 때까지 wiring하지 않는다.

Project/draft archive 이후 MongoDB source snapshot과 version은 보존한다. 파생 index record는 stale 처리, version/status filter, rebuild 중 선택해 정본 상태를 따라가야 하며, index 삭제가 MongoDB 정본 삭제를 의미하지 않는다. Phase 3A의 archive/status filter는 explicit rebuild가 materialize한 record metadata 기준이므로, archive 이후 기존 stale record를 즉시 숨기려면 재build 또는 후속 automatic sync가 필요하다. 다만 query/Context Gate가 hit를 사용하기 전 `validate_source_block_record()`를 호출하면 archive 후 기존 materialized record도 stale로 검출할 수 있다.

## 산출물

1. 공통 IndexSyncRequest/Result 계약
2. ChromaDB adapter와 record mapping
3. Elasticsearch adapter, mapping, 한국어 analyzer 결정
4. sync log와 retry/rebuild 도구
5. version mismatch/stale 판정 규칙

## 수용 기준

- 각 index hit가 `project_id`, Mongo collection/ID, version으로 정본을 가리킨다.
- Mongo 문서 갱신·삭제 후 stale hit를 식별하고 사용하지 않는다.
- adapter 실패가 MongoDB 정본 저장을 되돌리거나 오염시키지 않는다.
- 같은 sync event를 재처리해도 중복 record가 생기지 않는다.
- MongoDB만으로 프로젝트 인덱스를 완전히 재생성할 수 있다.
- 한 프로젝트의 검색이 다른 프로젝트 record를 반환하지 않는다.

## 착수 전 결정사항

- [ ] 임베딩 모델, dimension, 한국어 품질 기준
- [ ] Elasticsearch nori analyzer 사용과 배포 방식
- [ ] MVP 단일 index/collection의 mapping 충돌 가능성
- [x] event queue, outbox, polling 중 sync 전달 방식 — [`03-index-sync-outbox-decisions.md`](03-index-sync-outbox-decisions.md)에 따라 Mongo outbox/polling 채택, 외부 queue 제외
- [x] 삭제/archive를 hard delete, tombstone, version filter 중 어떻게 반영할지 — 첫 slice는 outbox entry + stale validation guard, worker slice에서는 tombstone/status update 우선 검토
- [x] sync 실패 시 retry/backoff와 운영 가시성 — [`03-index-worker-retry-decisions.md`](03-index-worker-retry-decisions.md)에 따라 one-shot worker command, claim timeout 10분, backoff 1분 → 5분 → failed, terminal 이동, archive worker-time `not_found` idempotent success, active-only status-aware dedup을 구현했다.
- [ ] adaptive chunking 또는 길이 기반 episode/section chunking을 도입할지, 도입한다면 어떤 quality metric과 version metadata를 요구할지

## 원문 및 상세 참고

- [`../abstract.md`](../abstract.md) §2.2~2.3, §9~11, §16.2~16.3
- [`../mongo_collections.md`](../mongo_collections.md) §39, §49, §57, §64
- [`../contracts.md`](../contracts.md) §7
- [`03-index-worker-retry-decisions.md`](03-index-worker-retry-decisions.md)
