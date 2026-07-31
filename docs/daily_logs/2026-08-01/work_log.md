# 2026-08-01 작업 로그

## Task — 인증 D8-6c-1: memory vector/lexical 파기 purge_project (drain 연결 없음, SoT 무변)

### Goals

- D8-6(영구 삭제)의 vector/index 백엔드 첫 반. 6a(core_sot 8)·6b(derived 10)는 mongo 컬렉션
  파기를 끝냈고, **6c는 Chroma·ES 같은 vector/index 백엔드에서 project 데이터를 hard delete**하는
  것이다. 어제(2026-07-31) 6c를 한 덩어리로 시도했다가 consistent 분할이 안 되는 부분을 버리고
  직전 커밋(337807b)로 되돌린 뒤, 권장 분할과 탐색 결과를 인수인계로 남겼다.
- **권장 분할(어제 결정)의 첫 반 = 6c-1(memory 도메인)**. 6c-1b(candidate) → 6c-2(worker drain
  연결) → 6d(endpoint) 후속. 6c-1은 **drain handler 연결 없이 purge_project 메서드만 추가**한다
  (6a `enqueue_project_purged` 패턴 — "메서드만, 미사용" — endpoint(6d)가 유일 production 호출자).
- 성공 기준: ① memory vector(Chroma/in-memory)·lexical(ES/in-memory) 백엔드가 project 단위로
  hard delete 되고 ② 멱등(이미 파기/미인덱스여도 에러 아님)하며 ③ 회귀가 project 스코프 삭제 +
  인접 project 유지(over-strict) 양쪽을 잠근다.

### Completed work — 구현 (코드 변경)

- **`memory_index.py`**: `MemoryVectorIndexAdapter` Protocol + `InMemoryMemoryVectorIndexAdapter` +
  `MemoryIndexSyncAdapter` + `CompositeMemoryIndexSyncAdapter` 에 `purge_project(*, project_id)`
  추가. InMemory는 records에서 project_id 매칭 제외(컴프리헨션). SyncAdapter/Composite는 각 sink
  adapter의 `purge_project` 로 위임.
- **`memory_lexical_index.py`**: `MemoryLexicalIndexAdapter` Protocol + `InMemoryMemoryLexicalIndexAdapter`
  + `ElasticsearchMemoryIndexAdapter` + `MemoryLexicalIndexSyncAdapter` 에 `purge_project` 추가. ES는
  `ElasticsearchClient` Protocol에 **`delete_by_query(*, index, query)`(8.x 시그니처)**를 추가하고
  adapter가 `{"term": {"project_id": project_id}}` 로 bulk delete.
- **`chroma.py`**: `ChromaMemoryVectorIndexAdapter.purge_project` —
  `collection.delete(where={"project_id": project_id})`. `ChromaCollection` Protocol은 이미 `delete(where=)`
  를 보유해 변경 불필요(탐색 결과 4번 정확).

### Verification

- **핵심 회귀 12 케이스**(test_memory_vector_index·test_chroma_memory_adapter·
  test_context_search_memory_lexical_retrieval): project 스코프 삭제(under-strict) + 인접 project
  유지(over-strict) + 멱등(빈 결과 OK) + SyncAdapter/Composite 위임 + composite 예외 전파.
  `_FakeES`(test_context_search_memory_lexical_retrieval)에 `delete_by_query` 추가. 단독 실행
  **53 passed / 3 skipped**(skip은 ES live/connect 패키지).
- **전량(test-mongo ON, 107s)**: **1803 passed / 4 skipped / 1519 subtests** — 6c 전 기준 1791 대비
  **+12 = 6c-1 회귀 12, 회귀 0건**. subtests·skip 동일.
- **양방향 가드 뮤테이션 검증**(checkpoint commit `d1fa777` 안전망):
  - **A — InMemory purge 방향 반전(`!=`→`==`)**: `test_inmemory_purge_drops_only_target_project` 외
    2개(위임·composite) re-fail. over-strict 가드(인접 project 유지)가 잡는다.
  - **B — composite purge 예외 삼킴(try/except)**:
    `test_composite_purge_propagates_sink_failure` re-fail(RuntimeError not raised). whole-event
    all-or-retry 가드가 잡는다(6c-2 _drain_purge 정책).
  - 둘 다 `git restore`로 원복 후 green 재확인, working tree clean.

### Decisions

- **6c-1은 drain 연결 없음**(6a `enqueue_project_purged` 패턴). worker `_drain_purge` 분기는 6c-2.
  endpoint(6d)가 유일 production 호출자이므로 6c-1 시점엔 purge_project를 부르는 경로가 없다 —
  단위 테스트가 직접 호출해 검증.
- **멱등 계약**(인수인계 "멱등 계약" 준수): `purge_project`는 빈 결과(이미 파기/미인덱스)여도
  `DerivedIndexRecordNotFound`를 raise **안 함**(`mark_archived`의 soft NotFound 와 의도적 차이 —
  불가역+멱등). Chroma delete / ES delete_by_query / in-memory 모두 빈 매칭이 에러 아님.
- **composite purge는 예외 전파**(per-sink 격리 안 함). drain은 per-sink `SinkOutcome` 격리지만,
  purge는 6c-2의 whole-event all-or-retry 정책에 맞춰 하나라도 실패하면 예외를 전파한다(탐색 결과
  "drain 방식 추천": per-sink target 키가 memory/candidate composite 에서 충돌).
- **source_block archive 파기(`ChromaArchiveIndexMutationAdapter`)는 6c-2에서**. 6c-1은 memory
  도메인만. archive adapter(`ArchiveIndexMutationAdapter` Protocol)의 purge_project 추가는 worker
  `_drain_purge` 연결과 한 덩어리가 자연스럽다.
- 18컬렉션 전수 가드(`test_purge_project_coverage.py`)는 **mongo repository 계약만** 검사 —
  indexing 백엔드(Protocol 기반)는 별도 가드가 필요. 6c-1b/6c-2 끝에서 indexing 백엔드 purge
  전수 가드 추가 후보.

### Next steps

- **6c-1b**: candidate 도메인 파기 — 같은 패턴(`candidate_index.py`·`candidate_lexical_index.py`:
  Protocol + InMemory + Chroma/ES adapter + `CandidateIndexSyncAdapter`·`CompositeCandidateIndexSyncAdapter`
  purge). ES `delete_by_query`는 6c-1에서 Protocol에 이미 추가했으므로 candidate lexical ES adapter가
  바로 씀.
- **6c-2**: worker `_drain_purge` + `run_once` 분기(`elif entry.event is PROJECT_PURGED`) 연결 +
  source_block archive(`ChromaArchiveIndexMutationAdapter`) purge + 회귀(worker drain, 어제 깨진
  guard `_archive_where` PURGED `ValueError` 교체).
- **6d**: `POST /admin/projects/{id}/purge` endpoint + `_REQUIRE_ADMIN` + boundary matrix(ADMIN +1·총 +1).
