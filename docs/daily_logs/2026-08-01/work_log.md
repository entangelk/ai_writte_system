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

---

## Task — 인증 D8-6d: admin project purge endpoint (SoT v1.7.74, D8-6 종료)

### Goals

- D8-6 마지막 슬라이스이자 **operation 카운트/공개 API 변화를 주는 유일 슬라이스**. 6a/6b/6c 파기
  메서드를 endpoint 하나에서 조율해 D5(전체 그래프 파기) 완성. 오너 결정: 응답 204(파기=소멸),
  부분 실패 503+재시도(전역 handler, 멱등).

### Completed work — 구현 (코드 변경)

- **main.py**: `_ERRORS_ADMIN_404`({401,403,404,503} — 409 불필요, purge 멱등) + `POST /admin/projects/{id}/purge`
  (204, `response_model=None`, `_REQUIRE_ADMIN`). core_sot.purge(NotFound→404, 8컬렉션 트랜잭션) → derived 8 service
  purge(10컬렉션) → enqueue_project_purged(6c worker). archive_project 패턴 미러.
- **boundary matrix**: CombinedBoundaryMatrixTest ADMIN 4→5(`len(tiers)` 70→71). AdminErrorContractDeclarationTest
  EXPECTED 4→5 + `_declared` 200/204 제외(purge 204 success 가 error lock list 에 섞이지 않게; writing/generate 202 등은 종전 동작 유지).
- **ProjectAuthorizationTest**: purge(admin + {project_id})가 "{project_id} path ⇒ ownership" 가정의 의도적
  예외(관리자가 id 로 파기, 내용 안 읽음 — D5). purge path 로 한정(다른 admin+project_id route 는 가드 잡음).
- **회귀**: AdminProjectPurgeTest(204+소멸·enqueue entry·404). `_client` index_sync_outbox 주입 확장.

### Verification

- 양방향 뮤테이션: endpoint 에서 core_sot.purge + enqueue_project_purged 동시 누락 → AdminProjectPurgeTest
  **3 re-fail**(204·사라짐·404·entry). 복구 후 green.
- **전량(test-mongo ON, 116s)**: **1820 passed / 4 skipped / 1532 subtests** — 1817 대비 **+3 =
  AdminProjectPurgeTest, 회귀 0건**. subtests 1519→1532(+13).

### Decisions

- 오너 결정(본 세션): 응답 **204**(파기=소멸, archive payload 와 구분); 부분 실패 **503+재시도**(전역 handler, 멱등).
- admin+project_id 예외: D8-6d purge 가 경계 가정의 의도적 예외. purge path 로 한정.
- `_declared` 200/204 제외: 204(success)가 error lock list 에 섞이지 않게.
- enqueue 회귀 보강: endpoint 가 enqueue 를 빼먹으면 vector/index 고아(D5) — `_client` 확장으로 entry 단언.
- **부분 실패 재시도 edge case(명시)**: core_sot 파기 후 derived mongo 장애 → 503 → 재시도 시 core_sot 404(이미
  파기). 매우 드물고 잔류 derived 는 ghost(무해). 완전 멱등 재시구(core_sot purge 멱등화/reconciler)는 별도 슬라이스.

### D8-6 종료

- **6a(core_sot 8)·6b(derived 10)·6c(vector/index 백엔드 + worker drain)·6d(endpoint) 전부 완료**. 회귀 1820 passed.
- **남은**: 프론트 purge UI(D8-5 admin 화면 오너 결정 C-1~C-6 선행), 감사 로그(별도 슬라이스 추천),
  완전 멱등 재시구(부분 실패 edge case). frontend `schema.d.ts` 재생성(gen:api)은 백엔드 확정 후.

---

## D8-6d 검증 후속 — blocking #1 해소 + schema.d.ts 재생성 (기록 보강)

독립 검증(`docs/verifications/2026-08-01/d8_6d_purge_endpoint.md`, **조건부 합격**)의 조건 해소와
프론트 스키마 재생성을 커밋(`3e04884`·`527551e`)했으나 work_log 기록이 빠져 있어 여기 남긴다.

### blocking #1 — endpoint→derived purge wiring 회귀 부재 (`3e04884`)

- **검증자가 뮤테이션 A로 입증한 빈 칸**: endpoint 의 derived 8 service purge 호출(10컬렉션)을 **전부
  제거해도 1820 passed / 0 failed**. core_sot(정본)+enqueue(vector/index)는 잠겨 있었으나 중간
  derived 층만 어떤 회귀에도 안 잡혀, 리팩터링 누락 시 **조용한 고아**(D5 부분 삭제 금지 위반).
- **보강**: `_PurgeSpy`(purge_project 호출 기록, 그 외 `__getattr__` 로 inner 위임) + `_client` 에
  `memory_service`·`analysis_service` 주입 인자 추가. `AdminProjectPurgeTest` 가 두 spy 를 주입하고
  `test_admin_purge_fans_out_to_derived_services` 로 fan-out 을 단언.
- **양방향 뮤테이션**: endpoint 에서 memory·analysis purge 누락 → 해당 셀 re-fail(`spy.purged == []`).
  복구 후 green(4 passed).
- **대표 2개로 한정한 이유**: 8 derived 중 memory·analysis 가 실 데이터를 가장 많이 만드는 축이고,
  나머지 6(review·gate·writing 3·llm)은 endpoint 본문 + 6b 회귀가 각 service purge 자체를 덮는다.
  빈 칸이었던 것은 **endpoint 가 부르는지 여부**이며 대표 2 spy 가 그 칸을 닫는다.

### schema.d.ts 재생성 (`527551e`)

- `npm run gen:api`(dump_openapi.py → openapi-typescript). 6d 의 `POST /admin/projects/{project_id}/purge`
  (204)가 schema 에 추가(operations 3곳). `tsc --noEmit` green. **프론트 purge UI 자체는 D8-5 admin
  화면 오너 결정 C-1~C-6 선행**이라 이번 범위 아님.

### Verification (본 세션 재실측)

- **전량(test-mongo ON, 97.5s)**: **1821 passed / 4 skipped / 1532 subtests** — 6d 직후 1820 대비
  **+1 = `test_admin_purge_fans_out_to_derived_services`, 회귀 0건**. skip·subtests 동일.
- 검증 문서의 남은 non-blocking: #2 완전 멱등 재시구(별도 슬라이스) · #3 SoT "완성" 표현(이제
  wiring lock 이 붙어 근거 성립) · #4 `ProjectAuthorizationTest` 예외 `pass` 의 외과성(사소).

---

## Task — 스크립트 세션 로그인: D8-3a 401 부채 해소 (앱 HTTP 8종, SoT 무변)

### Goals

- D8-6 종료 후 다음 슬라이스. **오너 선택**: D8-5는 오너 결정 C-1~C-6에 막혀 있고 D8-7은 결정 브리프가
  선행이라, 결정 없이 갈 수 있고 **우선순위가 올라가 있던** 추적 부채(HANDOFF)를 연다.
- D8-3a 이후 앱의 모든 route 가 세션을 요구해 운영 smoke·진단 스크립트가 401 을 받는다. 특히
  `diagnose_writing_report`·`diagnose_writing_gate` 는 report·gate 실패 원인을 보는 **유일한 진단
  도구**인데 막혀 있어 2026-07-29 장애 조사에서 쓰지 못했다(앱 코드로 우회했고 그 리그는 repo 에 없다).
- 성공 기준: ① 자격증명을 주면 로그인해 세션을 유지하고 ② 안 주면 종전대로 익명 진행하며 ③ **plain
  http 에서 Secure 쿠키가 버려지는 함정**을 회귀가 양방향으로 잠근다.

### Completed work — 구현 (코드 변경)

- **`scripts/script_auth.py`(신규)**: `add_login_arguments(parser)`(`--username`, env `APPLICATION_USERNAME`)
  · `password_from_env()` · `login(client, …)` · `authenticate_client(client, username=…)`.
  - **비밀번호는 env 전용**(`APPLICATION_PASSWORD`) — `create_user.py` 선례 그대로다(argv 는 shell
    history·`ps` 에 남는다). `--password` 옵션은 **의도적으로 없고** 회귀가 그 부재를 단정한다.
  - **토큰은 명시 `Cookie` 헤더로 싣는다**. 세션 쿠키는 `Secure` 라 httpx 쿠키 저장소가 plain http
    대상에서 조용히 버리는데(HANDOFF 함정) 스크립트는 전부 `http://application:8000` 이다.
  - 로그인 실패는 `ScriptLoginError`(401 = 계정/비밀번호/비활성 구분 없음 — 앱의 단일 메시지 정책과
    동형) · **200 인데 Set-Cookie 가 없으면도 에러**(조용히 익명으로 남는 것을 막는다).
- **배선 8종**: `phase2a_deployed_e2e_smoke` · `phase3a_deployed_rebuild_smoke` ·
  `phase4_context_search_deployed_smoke` · `phase6_gate_finding_live_smoke` · `diagnose_writing_gate` ·
  `diagnose_writing_report` · **`measure_writing_stages`** · **`benchmark_writing_loop`**.
  각 스크립트는 parser 에 `add_login_arguments`, client 생성 직후 `await authenticate_client(...)`.
- **★ 패턴 스윕이 2종을 더 찾았다**(CLAUDE.md §4): HANDOFF 는 6종을 지목했지만 `scripts/` 를
  `application_base_url`·`application:8000` 로 훑으니 `benchmark_writing_loop`·`measure_writing_stages`
  도 `/projects` 를 친다. 부채 목록이 실측보다 작았던 것이며 8종 전부 배선했다.
- 진단 2종 docstring 에 로그인 사용법 추가(`-e APPLICATION_PASSWORD` + `--username`), **`--current-position`
  을 주면 시드를 건너뛰므로 로그인도 불필요**함을 명시.

### Verification

- **회귀 신규 `tests/test_script_login.py` 9 케이스 + 배선 전수 가드**(subtests 8 = 스크립트 8종):
  헤더 부착·로그인 body·자격증명 없음(익명)·username 만 있고 env 없음·401 에러·Set-Cookie 없음 에러 ·
  `--password` argv 부재 · env 읽기 · `ScriptLoginWiringCoverageTest`(8종이 flag + 로그인 호출을 모두 가짐).
- **양방향 뮤테이션**:
  - **A — Cookie 헤더 부착 제거(쿠키 저장소에 위임)**: `test_login_attaches_the_session_to_later_requests_over_http`
    re-fail(`cookie: None != 'session=tok-1'`). **Secure 함정이 실제로 잠겨 있음을 실측** — 저장소에
    맡기는 "그럴듯한" 구현이 여기서만 걸린다.
  - **B — 한 스크립트에서 `authenticate_client` 호출 삭제**(`diagnose_writing_report`): 배선 가드
    subtest re-fail. flag 만 남기고 로그인을 잃는 리팩터링을 잡는다(관측 슬라이스의 "조립 가드" 교훈).
  - 둘 다 **역방향 Edit 으로 원복**(HANDOFF 함정: `git checkout --` 은 미커밋 슬라이스를 날린다).
- **★ 라이브 관통(실 앱 in-process, 알파)**: 배포 스택은 내려가 있고 알파 `application` 이미지는 auth
  이전 빌드라, 실 `create_app` 을 in-memory user/session 으로 127.0.0.1:8531 에 띄워 스크립트를 그대로
  돌렸다(`AUTH_COOKIE_SECURE=true`, plain http — 함정 조건 그대로).
  - 자격증명 없음 → `POST /projects` **401**(종전 동작 그대로).
  - `--username probe` + `APPLICATION_PASSWORD` → `phase3a_deployed_rebuild_smoke` **exit 0**
    (project/draft/version/rebuild 전부 200), `phase2a_deployed_e2e_smoke` 인증 write 6건 200
    (project·draft·version·source_ref 3) 후 analysis run 만 **503**(LLM 게이트웨이 미구성 face —
    인증이 아니라 협력자 부재).
- **전량(test-mongo ON, 100s)**: **1830 passed / 4 skipped / 1540 subtests** — 1821 대비
  **+9 = 신규 회귀 9, 회귀 0건**. subtests 1532→1540(+8 = 배선 가드가 도는 스크립트 8종). skip 동일.
- 기존 스크립트 회귀 무변(`test_phase2a/3a/4_*_script.py` + gate·report live diag **43 passed**),
  8종 전부 `--help` 에 `--username` 노출.

### Decisions

- **자격증명은 선택**(안 주면 익명). 종전 동작 보존이고, 로그인이 필요 없는 호출(`/health`)이나
  `--current-position` 으로 시드를 건너뛰는 진단 실행에서 계정을 강요하지 않는다.
- **비밀번호 argv 금지** — `create_user.py` 선례. 회귀가 `--password` 부재를 단정하므로 나중에
  "편의상" 추가하려면 그 셀을 먼저 봐야 한다.
- **공용 모듈 1개**(`script_auth.py`) — 8곳에 같은 로그인 코드를 복제하면 Secure 함정 회피가 한 곳에서만
  썩는다. 배선 전수 가드가 새 스크립트의 누락을 잡는다.
- **워커는 범위 밖** — HTTP 를 안 쓰고 Mongo 에 직접 붙는다(D8-7 사안).
- SoT 무변: 공개 API·계약 변화 없음(스크립트는 계약 소비자다).

---

## Hardening — 검증(2026-08-01) 스크립트 로그인 슬라이스 지적 3건 반영

독립 검증이 **"8종 전부 배선했다"는 주장이 거짓**임을 잡았다(실제 9종). 지적 3건 전부 반영.

### #1 [중간, 실 결함] 배선 누락 — `phase2a_provider_live_smoke.py`

- **재현(독립)**: `create_application_app(core_sot, analysis, runner)` 로 앱을 in-process 로 띄우고
  `ASGITransport` + `http://application-smoke` 로 `/projects` 등 8개 route 를 친다. session_service 를
  안 넘겨 `_default_session_service()` 가 서고 → **`POST /projects` → 401 `not authenticated`**
  (스크래치 재현 실측). 배선 전 실제 증상은 401 본문에서 `KeyError: 'id'`.
- **왜 놓쳤나**: 내 스윕 기준이 `application_base_url`·`application:8000` 문자열이었는데 이 스크립트는
  ASGI 가상 호스트(`application-smoke`)를 쓴다. **"스크립트는 전부 application:8000" 전제가 틀렸다.**
- **수정**: 이 스크립트는 **자기 스택 전체를 소유**하고 저장소가 전부 in-memory 라, 운영자 계정을 빌릴
  곳도 실행 뒤 남는 것도 없다 → **일회용 계정을 직접 발급**한다(`secrets.token_urlsafe(24)` +
  `InMemoryUserRepository`/`InMemorySessionRepository` 를 `create_app` 에 주입) 후
  `authenticate_client(client, username=…, password=…)`. 이를 위해 `authenticate_client` 에
  **`password` 인자 추가**(기본은 종전대로 env) — 로그인 경로는 여전히 한 곳이다.
- **라이브 확인**: 죽은 llama(`127.0.0.1:9`)를 가리켜 실행 → project 생성·source_ref 3건·job 실행까지
  **인증 통과**, `final_job.status=failed`(llama 부재 — 인증 아님).

### #2 [낮음, 문서 정확성] "Secure 함정 때문에 헤더가 필수" 는 과장

- **직접 재현**: 헤더 부착을 `client.cookies.set(...)` 으로 바꿔도 **테스트 통과**. 손으로 넣은 쿠키는
  Secure 플래그가 없어 plain http 로도 나간다. 검증자 지적이 맞다.
- **판단: 가드를 조이지 않는다.** 회귀는 *행동*(다음 요청에 세션이 실린다)을 잠그는 것이고 `cookies.set`
  은 실제로 동작하는 구현이므로, 헤더 전용 단정으로 바꾸면 **정상 구현을 깨는 과잉 교정**이 된다.
  대신 **주장 쪽을 고쳤다** — `script_auth` docstring·테스트 docstring·HANDOFF 를 "명시 헤더가 필수"에서
  **"로그인 응답 쿠키를 jar 자동 왕복에 맡기면 안 된다(헤더든 명시 set 이든 jar 밖으로 꺼내라)"** 로.
  테스트 docstring 에 "이 셀을 헤더 전용으로 조이지 말 것"을 근거와 함께 남겼다.

### #3 [낮음] 배선 가드가 목록 밖 스크립트를 못 본다 → 디스커버리 가드 추가

- 종전 `ScriptLoginWiringCoverageTest` 는 하드코딩된 목록만 검사해 **결함 #1 같은 미등록 스크립트를
  구조적으로 못 잡았다**. HANDOFF 의 "새 스크립트는 목록에 넣는다"는 강제가 아니었다.
- **추가**: `test_no_script_reaches_an_application_route_off_the_register` — `scripts/*.py` 를 읽어
  앱 route 마커(`"/projects`, `\bseed_context\b`)가 있는데 레지스터에 없으면 실패. **디렉터리를 읽지
  기억을 읽지 않는다.**
- **이 가드가 즉시 10번째 후보를 잡았고, 그것은 오탐이었다**: `phase4_context_search_planner_live_smoke`
  는 `seed_context_search_plan_template`(게이트웨이 전용) 때문에 걸렸다 → 마커를 **단어 경계 정규식**으로
  좁혀 해소. 우는 늑대가 되는 가드는 곧 삭제되므로 오탐 제거가 가드의 일부다.
- 레지스터를 **모드 dict** 로 바꿨다: `operator`(운영자 계정 — `--username` + env 필수) ·
  `self_hosted`(자기 스택 소유 — 자체 credential). 9종 = operator 8 + self_hosted 1.

### Verification

- **양방향 뮤테이션 3종**(전부 역방향 Edit 원복):
  - **C — provider_live 에서 `authenticate_client` 호출 삭제**: 레지스터 가드 subtest re-fail +
    스크립트 실행이 `KeyError: 'id'`(401 본문)로 재현.
  - **D — provider_live 를 레지스터에서 제거**: 디스커버리 가드 subtest re-fail
    ("calls application routes but is not registered"). **#3 가드가 실제로 문다는 증거.**
  - **A′ — 헤더를 `cookies.set` 으로 교체**: 통과(위 #2 판단의 근거 실측).
- `tests/test_script_login.py` **10 passed / 17 subtests**(9 레지스터 + 8 디스커버리).
- **전량(test-mongo ON)**: **1831 passed / 4 skipped / 1549 subtests** — 1830 대비 **+1 = 디스커버리
  가드, subtests +9**. 회귀 0건.

---

## Task — 6d 검증 #4: purge 경계 예외의 blanket `pass` 제거 (코드 무변)

### Goals

- 6d 독립 검증의 non-blocking #4. `ProjectAuthorizationTest` 의 purge 예외가 `pass` 라 **아무것도
  단정하지 않는다** — 오너 지시("구멍내지 말라")에 정확히 걸리는 자리.

### Completed work

- **검증자 권고는 실측상 틀렸다**(그대로 따르지 않았다): 권고는 "`ownership_guarded == expected` 는
  자명 통과라 유지 가능"이었는데, purge 는 `_REQUIRE_ADMIN`(auth + admin)뿐이라
  `ownership_guarded=False`·`expected=True` → **그 단정은 통과가 아니라 실패**한다.
- 대신 **예외의 형태를 단정**한다: `assertFalse(ownership_guarded)`(D5 상 의도적 부재 — ownership 을
  붙이면 관리자가 파기하지 못한다) + `assertTrue(admin_guarded)`. 종전 `pass` 는 **인가가 아예 없는
  purge 도 통과**시켰다(그 뒤의 403 선언 단정은 `expected or admin_guarded` 라 여전히 참).
- **패턴 스윕**: `tests/test_auth_api.py`·`test_application_api.py` 의 `pass`/`continue` 전수 확인 —
  나머지는 전부 정당한 필터(APIRoute 아님·PUBLIC 목록·202 success arm). blanket skip 은 이 한 곳뿐이었다.

### Verification

- **양방향 뮤테이션(인메모리)**: 프로덕션 인증 코드를 약화시키는 디스크 뮤테이션은 **분류기가 차단**했고
  타당한 차단이라 우회하지 않았다. 대신 스크래치에서 앱을 만들고 **route 객체의 dependencies 를
  런타임에 변형**해 같은 셀을 돌렸다 — **E**(admin dep 제거) → `assertTrue` re-fail ·
  **F**(ownership dep 추가) → `assertFalse` re-fail · **control**(무변형) pass.
- `ProjectAuthorizationTest` 6 passed / 134 subtests. **전량 1831 passed / 4 skipped / 1549 subtests**
  (셀 내부 강화라 카운트 무변), 회귀 0건. `git diff` 로 main.py 무변 확인.

---

## Task — D8-7 인프라 인증 착수 결정 브리프 (코드 없음)

### Goals

- D8-6 종료·스크립트 부채 해소 후 남은 유일한 페이즈 트랙. **오너 결정 없이는 코드를 쓸 수 없다**
  (CLAUDE.md "Owner decision brief" — 아키텍처·정책·의존성 선택). 산출물 =
  [`plans/auth-d8-7-infra-auth-decisions.md`](../../plans/auth-d8-7-infra-auth-decisions.md).

### 착수 전 실측 (브리프의 근거 — 전부 이번 세션에 직접 잼)

- **노출면**: compose 가 **7개 서비스 전부를 호스트에 게시**하고 바인드 주소 지정이 없다(0.0.0.0).
  즉 mongo(27520)·ES(9520)·chroma(8523)가 **지금 LAN에서 무인증으로 열려 있다** — 이것이
  "외부 노출 금지"의 실체다.
- **Mongo 배선 비용 = 코드 0줄**: `MongoClient(...)` 13곳이 **AST 전수 확인 결과 전부 `from_uri()` 안**
  이고 URI 는 `CORE_SOT_MONGO_URI` 한 곳에서 온다. 자격증명은 URI 에 실린다.
- **★ 그러나 keyfile 이 강제된다**: `docker run mongo:7 mongod --auth --replSet rs0` →
  `BadValue: security.keyFile is required when authorization is enabled with replica sets`.
  **커밋 불가 시크릿 파일 + 퍼미션이 머신마다** 필요해지고, repo 의 정의적 성질("어느 머신에서든
  compose up 만으로 뜬다")이 깨진다.
- **ES 배선 3곳**(`memory_lexical_index.py:342`·`candidate_lexical_index.py:287`·
  `phase4_lexical_memory_live_smoke.py:95`) · **Chroma 1곳**(`chroma.py:577`).

### 브리프의 결정 항목

- **G1(선행)** 위험을 자격증명으로 막을지(B) **노출면 축소로 없앨지**(A) — 추천 **C**(A를 지금,
  B는 원격 배포 시점). G1=A/C면 G3~G6은 불필요해진다.
- **G2** 대상 범위(Chroma 포함 여부 — D8-6이 이미 파기 대상으로 셌으므로 포함 추천) ·
  **G3** 기존 볼륨 마이그레이션 · **G4** 3대 머신 시크릿 배포(진짜 난점) · **G5** test compose 확장 여부 ·
  **G6** ES TLS.

### Decisions (구현자 판단, 오너 확정 대기)

- 추천 C 의 근거는 **위험의 형태**(LAN 노출은 노출면 축소로 완전히 사라진다)·**단계**(로컬 1인,
  머신 3대)·**되돌릴 수 있음**(A는 B를 막지 않는다).
- **G1=C를 고르면 SoT 문구 개정이 따라온다** — 지금 정본은 해제 조건을 *인증*으로 적고 있다.
  브리프에 명시했고 HANDOFF Owner Decisions 에도 올렸다.
- **미검증을 사실로 쓰지 않았다**: ES 8.x 가 **이미 만들어진 볼륨**에 보안을 켤 때 `ELASTIC_PASSWORD`
  가 먹는지는 실측 안 했고, 브리프에 "착수 시 실측 선행"으로 명시했다.

---

## 2026-08-01 마감 — 검증 통과 + 정밀도 보탬 + 다음 작업자 메모

### 독립 검증 (결함 0건)

- 두 작업(purge 가드 `pass` 제거 `7bf80ca` · D8-7 브리프 `f823046`) 모두 **검증자가 독립 재현**했고
  결함이 없었다. 검증자 권고를 실측으로 뒤집은 것(#4 의 `ownership_guarded==expected`)도
  **반박이 옳다**고 확인됐다(purge dependencies = auth + admin, ownership 없음).
- 브리프 §1 실측 표는 한 줄씩 독립 검증됐다 — 포트 7개 0.0.0.0 게시 · ES `xpack.security.enabled: false` ·
  MongoClient 13곳 전부 `from_uri` · ES 3곳 · Chroma `chroma.py:577` · keyfile 강제(공식 문서 교차).

### 정밀도 보탬 2건 반영 (결함 아님)

- **MongoClient "13곳" 은 `services/` 한정**이었다 — `scripts/` 에 **4곳 더** 있다
  (`migrate_ordered_units` · `phase2b5_memory_reindex_live_smoke` · `phase2b_candidate_index_live_smoke` ·
  `phase2b7_character_alias_live_smoke`, 전부 env 에서 온 uri 를 그대로 넘긴다). 직접 세어 확인 후
  브리프 표와 HANDOFF 문구를 정정했다. **"자격증명 코드 0줄" 결론은 그대로**(스크립트도 URI 만 바뀐다).
- **Chroma 경로 단축 표기**(`chroma.py:577`)를 ES 처럼 **풀 경로**로 맞췄다.

### 오늘 남긴 것 (다음 작업자용)

- **회귀 기준선 = 1831 passed / 4 skipped / 1549 subtests**(test-mongo ON). 이 숫자로 시작하라.
- **막고 있는 것은 오너 결정 둘뿐**이다: **D8-7 G1**(브리프 `plans/auth-d8-7-infra-auth-decisions.md`,
  나머지 G2~G6은 G1=B 일 때만 필요) · **D8-5 C-1~C-6**(관리자 화면). 그 밖의 페이즈 트랙은 없다.
- **결정 없이 지금 열 수 있는 것**: purge 감사 로그 · 완전 멱등 재시구(reconciler). 둘 다 D8-6 잔여이고
  작다. 다만 **감사 로그는 저장 위치·필드·조회 표면이 사실상 결정 사항**이라 작은 브리프가 먼저 붙는
  편이 낫다(감사 저장소 `llm_call_audits` 와 같은 축에 둘지가 첫 질문).
- **이번 슬라이스에서 배운 것(다음 스윕에 그대로 적용할 것)**: 문자열 하나로 스윕하면 **같은 일을 다른
  철자로 하는 호출부를 놓친다**(`application:8000` vs ASGI `application-smoke`). 부채 목록의 개수를
  그대로 믿지 말고 **디렉터리를 읽는 가드**로 바꿔라 — 이번에 그렇게 바꾸자마자 오탐 1건까지 같이
  드러났다(단어 경계로 좁혀 해소).
- **CHANGELOG 갱신됨**: D8-6 종료(마일스톤) + 스크립트 로그인 2행. 오늘 이전 마지막 항목은 07-31 이었다.
- **test-mongo 는 내려 두었다**(`docker-compose.test.yml down`). 회귀를 돌리려면 다시 올리고
  **healthy 를 기다린 뒤** 시작한다(HANDOFF 함정 — 곧바로 돌리면 초반 모듈만 skip 되어 잘못된 기준선이 난다).
