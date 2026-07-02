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
- `index_sync_logs`
- upsert/delete/rebuild와 stale check
- adaptive chunking, semantic chunking, 길이 기반 episode/section chunking은 후속 파생 index 전략 후보로 둔다. 이들은 MongoDB raw snapshot/source_ref 정본을 대체하지 않으며, 도입 시 Mongo pointer/version/hash로 재조회 가능해야 한다.

collection/index 분리는 사용량과 mapping 요구가 확인된 뒤 검토한다.

2026-07-02 Phase 3A 첫 slice는 [`03-indexing-kickoff-decisions.md`](03-indexing-kickoff-decisions.md)에 따라 더 작게 시작한다. 첫 구현은 source block only, Chroma-like vector contract with deterministic fake adapter, fake embedding only, explicit snapshot rebuild, archive/status filter만 다룬다. `IndexSyncRequest(project_id, snapshot_id, target)`와 `IndexSyncResult(request, records_attempted, records_written)`는 explicit rebuild용 in-process 축소 계약이며, `contracts.md` §7.3의 persistent sync log/outbox envelope는 후속 sync log slice에서 다룬다. 실제 ChromaDB, Elasticsearch, 자동 outbox/polling, analysis candidate indexing은 후속 결정이다.

## 단방향 동기화

```text
MongoDB change → IndexSyncRequest → Chroma adapter / ES adapter
→ 결과 및 version 기록 → index_sync_logs
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

MVP에서 실제 지원할 이벤트는 착수 전에 축소 확정한다.

Project/draft archive 이후 MongoDB source snapshot과 version은 보존한다. 파생 index record는 stale 처리, version/status filter, rebuild 중 선택해 정본 상태를 따라가야 하며, index 삭제가 MongoDB 정본 삭제를 의미하지 않는다. Phase 3A의 archive/status filter는 explicit rebuild가 materialize한 record metadata 기준이므로, archive 이후 기존 stale record를 즉시 숨기려면 재build 또는 후속 automatic sync가 필요하다.

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
- [ ] event queue, outbox, polling 중 sync 전달 방식
- [ ] 삭제를 hard delete, tombstone, version filter 중 어떻게 반영할지
- [ ] sync 실패 시 retry/backoff와 운영 가시성
- [ ] adaptive chunking 또는 길이 기반 episode/section chunking을 도입할지, 도입한다면 어떤 quality metric과 version metadata를 요구할지

## 원문 및 상세 참고

- [`../abstract.md`](../abstract.md) §2.2~2.3, §9~11, §16.2~16.3
- [`../mongo_collections.md`](../mongo_collections.md) §39, §49, §57, §64
- [`../contracts.md`](../contracts.md) §7
