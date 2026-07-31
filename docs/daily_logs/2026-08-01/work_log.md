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

---

## Task — 인증 D8-6c-1b: candidate vector/lexical 파기 purge_project (drain 연결 없음, SoT 무변)

### Goals

- 6c 분할의 둘째 반. **6c-1(memory)의 정확한 미러**를 candidate 도메인에 적용. candidate
  vector(Chroma/in-memory)·lexical(ES/in-memory) 백엔드에 project 단위 hard delete 추가.
  drain handler 연결은 6c-2. 어제 인수인계의 "6c-1b: candidate, 같은 패턴" 슬라이스.

### Completed work — 구현 (코드 변경)

- **`candidate_index.py`**: `CandidateVectorIndexAdapter` Protocol + `InMemoryCandidateVectorIndexAdapter` +
  `CandidateIndexSyncAdapter` + `CompositeCandidateIndexSyncAdapter` 에 `purge_project(*, project_id)` 추가.
- **`candidate_lexical_index.py`**: `CandidateLexicalIndexAdapter` Protocol + `InMemoryCandidateLexicalIndexAdapter`
  + `ElasticsearchCandidateIndexAdapter` + `CandidateLexicalIndexSyncAdapter` 에 `purge_project` 추가.
  **★ ES `ElasticsearchClient` Protocol의 `delete_by_query`는 6c-1에서 memory_lexical_index 에 추가했고
  candidate_lexical_index 가 그것을 import 재사용**하므로, candidate ES adapter가 추가 Protocol 변경 없이
  바로 delete_by_query 를 씀(탐색 결과의 수월함 실측).
- **`chroma.py`**: `ChromaCandidateVectorIndexAdapter.purge_project` — `collection.delete(where={"project_id": ...})`.

### Verification

- **핵심 회귀 7 케이스**(test_candidate_index.py): InMemory vector·chroma·in-memory lexical·ES purge
  (스코프 + 인접 project 유지 + 멱등) + composite 위임·예외 전파. **★ `_FakeChromaCollection.delete`를
  `$and`와 단일키 project_id(purge) 모두 지원하게 확장** — 종전엔 `$and` 하드코딩이라 purge 의
  `where={"project_id":...}` 가 KeyError 였다(실제 ChromaCollection.delete 는 두 형태 모두 허용). 기존
  `$and` 케이스(delete_candidate_record) 무변. test_candidate_index.py 단독 **33 passed**.
- **전량(test-mongo ON, 94s)**: **1810 passed / 4 skipped / 1519 subtests** — 6c-1 후 1803 대비
  **+7 = 6c-1b 회귀 7, 회귀 0건**. subtests·skip 동일.
- **양방향 가드 뮤테이션**(checkpoint `5b73a86` 안전망): candidate InMemory purge 방향 반전(`!=`→`==`) →
  `test_purge_drops_only_target_project_and_is_idempotent` re-fail(over-strict 가드). composite 예외 전파
  가드는 6c-1 memory 의 것과 동일 코드(`CompositeXxxIndexSyncAdapter.purge_project`)라 candidate 에서
  별도 뮤테이션은 생략(memory 6c-1 B 검증으로 충분). 복구 후 green, working tree clean.

### Decisions

- candidate = memory 의 정확한 미러(동일 멱등 계약·composite 예외 전파·drain 연결 없음).
- `_FakeChromaCollection.delete` 확장은 내 purge 회귀가 필요로 하는 테스트 인프라 보강(실제 Chroma
  동작에 맞춤). 기존 테스트 무변 — `$and` 형태가 단일키 형태로 바뀌어도 여전히 매칭.
- 18컬렉션 전수 가드는 여전히 mongo repository 만 검사 — indexing 백엔드(Protocol 기반) purge 전수
  가드는 6c-2 끝에서 추가 후보(memory 6c-1 + candidate 6c-1b 백엔드 purge 가 이제 둘 다 있음).

### Next steps

- **6c-2**: worker `_drain_purge` + `run_once` 분기(`elif entry.event is PROJECT_PURGED`) 연결 +
  source_block archive(`ChromaArchiveIndexMutationAdapter`) purge + memory/candidate composite purge 호출
  + 회귀(worker drain, 어제 깨진 guard `_archive_where` PURGED `ValueError` 교체). 이 슬라이스가 끝나면
  6c의 5 백엔드(source_block + memory vec/lex + candidate vec/lex) drain 이 consistent 하게 연결됨.
- **6d**: `POST /admin/projects/{id}/purge` endpoint + `_REQUIRE_ADMIN` + boundary matrix(ADMIN +1·총 +1).

---

## Hardening 보강 — 검증(2026-08-01) non-blocking #1·#2 반영

검증자 독립 검증(`docs/verifications/2026-08-01/d8_6c_purge_vector_lexical.md`, 합격)의 non-blocking
hardening #1·#2를 보강. #3(SoT)은 오너 결정 대기, #4(composite 관측성)는 설계적(6c-2 선택)이라 보강 아님.

### #1 indexing 백엔드 purge 전수 가드
- `test_purge_project_coverage.py`에 `IndexingBackendPurgeCoverageTest` 추가: memory/candidate
  vector·lexical Protocol 4종(`MemoryVectorIndexAdapter`·`CandidateVectorIndexAdapter`·
  `MemoryLexicalIndexAdapter`·`CandidateLexicalIndexAdapter`) + worker 가 drain 에서 부르는 composite 2종
  (`CompositeMemoryIndexSyncAdapter`·`CompositeCandidateIndexSyncAdapter`)이 `purge_project` 노출을 `dir()`
  단정. **D5 부분 삭제 금지의 indexing 층** — 고아 보증을 repository(18컬렉션)에서 indexing 백엔드로 확장.
- over-strict 가드: 6 백엔드 수 고정. **source_block archive(`ArchiveIndexMutationAdapter`)는 6c-2 에서
  purge_project 추가 시 합류**(카운트 6→7, 주석 명시).

### #2 candidate 멱등 테스트 대칭
- candidate Chroma(`ChromaCandidateAdapterTest`)·in-memory-lexical(`InMemoryLexicalAdapterTest`)에
  `test_purge_is_idempotent_on_empty` 추가. memory(4 백엔드 모두 idempotent 단언)와 대칭 — 빈 결과 no-raise.

### Verification
- `test_purge_project_coverage.py`: **4 passed**(`PurgeProjectCoverageTest` 2 + `IndexingBackendPurgeCoverageTest` 2).
- candidate purge: **9 passed**(+2 idempotent).
- **전량(test-mongo ON, 98s)**: **1814 passed / 4 skipped / 1519 subtests** — 1810 대비 **+4 = #1 2·#2 2,
  회귀 0건**. subtests·skip 동일.

### Decisions
- #1 가드는 memory(6c-1)+candidate(6c-1b) 백엔드가 모두 준비됐으므로 6c-2 전에 추가(검증자는 6c-2 종료 권장이었으나
  두 반 끝에 추가해도 정합). source_block archive 누락은 6c-2 합류로 닫힘(주석으로 인수인계).
- #3 SoT 버전 갱신 — **오너 결정 (b)**: SoT 변경이력에 **v1.7.72 entry** 추가(6c-1·6c-1b indexing 백엔드
  purge_project + 검증 hardening). 본문 규칙 확장 없이 변경이력 entry만(6a/6b 코드만 슬라이스도 변경이력 entry
  선례와 일관). HANDOFF 정본 버전 v1.7.71 → v1.7.72. operation 카운트 무변은 무관 타당.

---

## Task — 인증 D8-6c-2: worker PROJECT_PURGED drain 연결 (SoT v1.7.73)

### Goals

- 6c 마지막 코드 슬라이스. 6c-1·6c-1b 가 추가한 memory/candidate 백엔드 `purge_project`(12 커밋)를
  worker 가 PROJECT_PURGED entry 에서 실제로 부르도록 연결. 인수인계 설계(`_drain_purge` whole-event
  all-or-retry + `run_once` 분기 + source_block archive purge + 깨진 guard `_archive_where` 교체).
  endpoint(6d)만 남음.

### Completed work — 구현 (코드 변경)

- **`service.py`**: `IndexSyncWorker._drain_purge` 추가 — archive(source_block) + memory composite +
  candidate composite purge 순차 호출. **whole-event all-or-retry**(하나라도 실패 시 BACKEND_ERROR + requeue;
  per-sink SinkOutcome 격리는 MEMORY/CANDIDATE_UPSERTED drain 전용 — PROJECT_PURGED 한 entry 가
  memory/candidate 두 composite 로 흘러 per-sink target 키 충돌). memory/candidate adapter 가 None 이면
  archive-only(no-Chroma/no-ES bootstrap).
- **`service.py`**: `run_once` 분기 `elif entry.event is PROJECT_PURGED → _drain_purge` — PROJECT_PURGED 가
  깨진 guard `_archive_where` ValueError 경로(else→`_drain_archive`→`mark_archived`)로 가는 것 차단.
- **`service.py` Protocol**: `ArchiveIndexMutationAdapter`·`MemoryIndexMutationAdapter`·
  `CandidateIndexMutationAdapter` 에 `purge_project` 선언; `RecordingArchiveIndexMutationAdapter` 에
  recording purge(`purged_projects`) 추가.
- **`chroma.py`**: `ChromaArchiveIndexMutationAdapter.purge_project` (source_block collection.delete where project_id).
- **전수 가드**: `test_purge_project_coverage.py::IndexingBackendPurgeCoverageTest` 에 source_block archive
  합류(카운트 6→7) — D5 고아 보증 indexing 층이 5 백엔드 전부(source_block + memory vec/lex + candidate vec/lex) 커버.

### Verification

- 회귀: `test_indexing_phase3a.py::IndexSyncWorkerTest` 에 PROJECT_PURGED drain 3 케이스(전 백엔드 호출·
  whole-event requeue·archive-only).
- **★ 회귀 위치 버그 + 수정(정직 기록)**: `f81d145` 에서 회귀 3을 IndexSyncWorkerTest 끝이라 착각하고
  top-level `_fixture` 헬퍼(497-) **뒤에** 삽입 → `_fixture` 의 nested def 가 되어 **pytest 수집에서 제외**.
  결과 전체 suite 1814(회귀 3 미포함) + 뮤테이션(_drain_purge purge 무력화)에도 re-fail 안 하는 **무효 가드**였음.
  `python -c` 로 `archive.purged_projects==[]` 임에도 passed 인 것으로 발견(AST 로 IndexSyncWorkerTest 가
  331-494 종료 확인). `f8a6ad3` 에서 IndexSyncWorkerTest 본문(`test_run_once_stop_check` 직후, `_fixture` 전)으로
  이동 → 수집/실행. **교훈: 회귀 추가 후 단독 -q뿐 아니라 전체 suite 카운트 +1 과 뮤테이션 re-fail을 함께 본다.**
- 양방향 뮤테이션(checkpoint 안전망): `_drain_purge` purge 무력화(`try: pass`) → 회귀 3 re-fail
  (archive.purged_projects·memory·candidate 단언, **3 failed**). 복구 후 green(26 passed).
- **전량(test-mongo ON, 111s)**: **1817 passed / 4 skipped / 1519 subtests** — 1814(6c-1·6c-1b+hardening) 대비
  **+3 = 6c-2 회귀 3, 회귀 0건**. subtests·skip 동일.

### Decisions

- whole-event all-or-retry: PROJECT_PURGED 한 entry 가 memory/candidate 두 composite 로 흘러 per-sink
  target 키("vector"/"lexical") 충돌 → all-or-retry 가 유일 일관 선택. purge 멱등(재파기 무해).
- 깨진 guard `_archive_where` 는 run_once 분기로 PROJECT_PURGED 를 차단해 발화 안 함(`_archive_where`
  자체는 PROJECT/DRAFT_ARCHIVED 만 처리, 변경 없음).
- endpoint 없음 → operation 카운트 무변(6d 에서 ADMIN tier +1·총 +1).
- **terminal partial-purge(all-or-retry 내재, 검증 non-blocking #2)**: 한 sink 영구 장애로 FAILED
  terminal 시 그 전 파기 sink는 파기된 채 잔류 — 잔류 vector 는 core_sot 파기 후 query 가 도달 못 하는
  ghost(무해) + FAILED 가시. local 안정 환경에서 가능성 낮음(멱등 재파기로 eventual consistency).

### Next steps

- **6d**: `POST /admin/projects/{id}/purge` endpoint + `_REQUIRE_ADMIN` + boundary matrix(ADMIN +1·총 +1).
  이것으로 D8-6 영구 삭제 트랙 종료(core_sot·derived·vector/drain·endpoint 전부).
- **독립 검증**: 6c-2 worker drain 연결 + 깨진 guard 교체 + 회귀 위치 버그/수정에 대한 검증 권장.
