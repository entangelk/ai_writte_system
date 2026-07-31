# 독립 검증 — D8-6c-2 worker PROJECT_PURGED drain 연결 (commit f81d145 + f8a6ad3 + b2d6cbd + 3bbcd71 + 8f8ecd7)

## Subject metadata

- **날짜**: 2026-08-01
- **요청자**: 오너("다음작업 검증해줘. D8-6c-2 완료 — worker PROJECT_PURGED drain 연결 … 6c-2는 worker 동작 변경이므로 독립 검증을 권장합니다.")
- **검증자**: Claude (독립 세션, max 노력)
- **대상 슬라이스**: D8-6c-2 — `IndexSyncWorker._drain_purge`(PROJECT_PURGED entry → archive + memory + candidate composite purge, whole-event all-or-retry) + `run_once` 분기 + Protocol 3종·`ChromaArchiveIndexMutationAdapter`·`RecordingArchive` purge + 전수 가드 source_block 합류(6→7). **D8-6 코드 슬라이스 전부 종료**(6a·6b·6c). endpoint(6d)만 남음.
- **정규 스펙**: `docs/system-contract-sot.md` v1.7.69(D8-6a — PROJECT_PURGED 이벤트·drain 미연결 명시)/v1.7.72(6c-1·1b 회고적)/v1.7.73(6c-2) · `docs/plans/auth-d8-5-admin-decisions.md` §5(D5=A) · `docs/verifications/2026-07-31/d8_6b_purge_derived.md`(6c 검증 포인트 H2 위임) · `docs/verifications/2026-08-01/d8_6c_purge_vector_lexical.md`(6c-1·1b 선행 검증 — 본 슬라이스 hardening #1·#2·#3를 권고).
- **검증 대상 출처**: `b2d6cbd`(6c-1·1b 검증 hardening 보강 #1·#2 — 본 세션 범위에 포함, HEAD 에 있음) · `3bbcd71`(SoT v1.7.72) · `f81d145`(6c-2 코드) · `f8a6ad3`(회귀 위치 버그 수정) · `8f8ecd7`(SoT v1.7.73·문서). HEAD = `8f8ecd7`. push 안 됨.

## Scope

1. **★ 회귀 수집 실제성(무효 가드 재발 차단)** — 작업자 자가 보고 "회귀 3이 `_fixture` 뒤 nested def → pytest 수집 제외 → 무효 가드" 버그. f8a6ad3 수정이 진짜인지, 현재 3개가 수집·실행되는지 이름 실행으로 독립 확인.
2. **`_drain_purge` 구현 + `run_once` 분기** — 순차 호출·whole-event all-or-retry·None 핸들링·`_archive_where` ValueError 경로 차단.
3. **양방향 뮤테이션** — purge 무력화 / 실패 삼킴이 가드를 re-fail 시키는지(독립 재현). 작업자가 무효 가드를 한 번 만들었으므로 특히 중요.
4. **Protocol 3종 + archive 구현 + 전수 가드 6→7** — `dir()` introspect 가 실제로 purge_project 를 검사하는지(단순 카운트 아님).
5. **Hardening 보강(b2d6cbd·3bbcd71)** — 선행 6c-1·1b 검증 권고 #1(indexing 가드)·#2(candidate idempotent 대칭)·#3(SoT)의 구현 확인.
6. **전체 suite green + SoT 합치** — 1817 재현; SoT v1.7.72/v1.7.73 entry·헤더 버전 합치.

## Methodology

- 코드 diff: `git show f81d145 -- service.py chroma.py tests/...` 로 추가 라인 전수 독해; 회귀 위치 버그는 `git show f8a6ad3` 로 before/after 대조.
- 회귀 수집 확인: `python3 -m pytest tests/test_indexing_phase3a.py -v -k purge_drain` (collected/selected/deselected 수로 수집 판정) + `grep -n` 들여쓰기/클래스 경계.
- 양방향 뮤테이션(작업 트리 일시 변이 → re-fail → `git checkout` 원복, CLAUDE.md §6):
  - A: `_drain_purge` purge 3호출 no-op → 3 re-fail.
  - B: `_drain_purge` except절 삼킴(→success) → Test 2(requeue 가드) re-fail.
- 전체 suite: `python3 -m pytest -q`(test-mongo healthy).
- coverage 가드 메커니즘: `dir(cls)` introspect 단정 직독 + 실행.
- boundary matrix: [should fire] archive+memory+candidate 순차 purge · [should fire] 실패 시 requeue+BACKEND_ERROR · [should NOT fire] adapter None 시 archive-only · [should NOT fire] PROJECT_PURGED 가 `_archive_where` ValueError 경로로 가지 않음.

## Findings

### 1. ★ 회귀 수집 실제성 — 무효 가드 버그 수정 독립 확인 ✅

- **현재 위치**: 3개 회귀는 `IndexSyncWorkerTest`(line 331–) 본문内 — `test_purge_drain_calls_archive_memory_and_candidate`(:496)·`test_purge_drain_requeues_on_any_backend_failure`(:520)·`test_purge_drain_runs_without_memory_or_candidate_adapter`(:539), 모두 4-space 클래스 메서드. `_fixture` 헬퍼는 클래스 **뒤** top-level(:552). f8a6ad3 diff 가 "3개를 `_fixture` 뒤(nested)에서 `test_run_once_stop_check` 직후(클래스 본문)로 이동, `_fixture`를 클래스 뒤로" 이동시킨 것과 정합.
- **이름 실행**: `pytest -k purge_drain` → `3 passed, 23 deselected` = IndexSyncWorkerTest 총 26 메서드(= f81d145 buggy 상태 23 + 수정된 3). **실제 수집·실행됨**. ✅
- **버그 내연 일치**: f81d145 시점 suite = 1814(3 미수집), f8a6ad3 후 1817(+3). f81d145 커밋 메시지 "23 passed" = IndexSyncWorkerTest buggy 수집 수(26−3)와 정합 — 작업자가 "23 passed"를 쓴 것 자체가 3개가 안 돌고 있다는 신호였으나 그땐 인지 못함(스스로 work_log 2026-08-01 6c-2 섹션에 정직 기록).
- **교훈 절차 가드**: 회귀 추가 후 전체 suite 카운트 +N **미증가** 가 수집 제외의 자동 신호(작업자가 1814로 발견). pytest 는 nested-def 미수집에 경고 없음 → 카운트 + 뮤테이션 re-fail만이 유일한 가드. work_log 에 교훈 기록됨.

### 2. `_drain_purge` 구현 + `run_once` 분기 ✅

- **`_drain_purge`**(service.py:569–598): `archive_adapter.purge_project`(무조건 — `archive_adapter`는 required 파라미터) → `memory_adapter.purge_project`(None 체크) → `candidate_adapter.purge_project`(None 체크) 순차. 예외 시 `record_outbox_failure` + `REQUEUED`(attempt 잔량) 또는 `FAILED`. `_drain_archive`(:535–543)와 동일 failure 패턴 — whole-event all-or-retry. ✅
- **None 핸들링**: memory/candidate adapter 가 None 이면 archive-only(no-Chroma/no-ES 부트스트랩 미러). Test 3가 잠금. ✅
- **`run_once` 분기**(service.py:521–527): `if event in _PER_SINK_EVENTS → _drain_sinks` / `elif event is PROJECT_PURGED → _drain_purge` / `else → _drain_archive`. PROJECT_PURGED 가 `_drain_archive`→`mark_archived`→`_archive_where`(PROJECT_PURGED 를 ValueError 로 거부, work_log 2026-07-31:829) 경로로 가는 것 차단. 남은 archive 이벤트(PROJECT/DRAFT_ARCHIVED)만 `_archive_where` 도달 — 이들은 where-clause 매핑이 있어 안전. ✅
- **`_drain_purge`는 `DerivedIndexRecordNotFound` 특수처리 안 함**: purge_project 는 멱등(빈 매칭 = no-raise)이므로 `_drain_archive`의 soft-NotFound 분기(:530) 불필요 — generic Exception 처리로 충분. 의도적 차이. ✅
- **컬렉션 분리**: source_block 은 별도 컬렉션(`SOURCE_BLOCK_COLLECTION = "source_blocks"`, service.py:35). `ChromaArchiveIndexMutationAdapter.purge_project`(chroma.py:255–261, `delete(where={"project_id":...})`)는 source_blocks 만 타격 — memory_vectors/candidate_vectors 와 무관. 6c-1/1b 검증의 컬렉션 분리 확인과 동일 결론. ✅

### 3. 양방향 뮤테이션(독립 재현) ✅

| 변이 | 코드 | 결과 |
|---|---|---|
| A. under-strict(purge 3호출 no-op) | service.py:583-587 → `pass` | `test_purge_drain_*` **3 re-fail**(`archive.purged_projects: [] != ['project-1']` 등). 수집된 가드가 실제로 계약 잠금. ✅ |
| B. over-strict(실패 삼킴→success) | `_drain_purge` except절 → `pass`(fall to success) | `test_purge_drain_requeues_on_any_backend_failure` **1 re-fail**(`entries_succeeded: 1 != 0`), Test 1/3 은 purge 호출 유지로 pass — all-or-retry requeue 가드 정밀 격리. ✅ |

복구 후 green 재확인(working tree clean). **이 실증이 핵심** — f81d145 무효 가드(수집 제외)와 달리 현재 3개는 수집되고 양방향으로 계약을 잠금.

### 4. Protocol 3종 + archive 구현 + 전수 가드 6→7 ✅

- **Protocol 선언**: `ArchiveIndexMutationAdapter`(service.py:74-77)·`MemoryIndexMutationAdapter`(:88-90)·`CandidateIndexMutationAdapter`(:98-99) 에 `purge_project` 선언. `RecordingArchiveIndexMutationAdapter` 구현(:464-468, `purged_projects` 기록). `ChromaArchiveIndexMutationAdapter` 구현(chroma.py:255-261). ✅
- **전수 가드 메커니즘**(test_purge_project_coverage.py:96-123): `IndexingBackendPurgeCoverageTest` 는 (a) `test_all_indexing_backends_expose_purge_project` — 7개 계약 각각 `"purge_project" not in dir(cls)` introspect(단순 카운트 아닌 실제 메서드 존재 단정), (b) `test_indexing_purge_roster_is_complete` — `len == 7` over-strict. source_block archive 가 f81d145 에서 합류(6→7). 실행 **4 passed**(repo 18컬렉션 가드 2 + indexing 7백엔드 가드 2). ✅

### 5. Hardening 보강(b2d6cbd·3bbcd71) — 선행 검증 권고 반영 ✅

- **#1 indexing 백엔드 전수 가드**: `IndexingBackendPurgeCoverageTest` 추가(본 세션 실행으로 7백엔드 cover 확인) — 6c-1·1b 검증 hardening #1 해소.
- **#2 candidate idempotent 대칭**: `ChromaCandidateAdapterTest::test_purge_is_idempotent_on_empty`(test_candidate_index.py:465)·`InMemoryLexicalAdapterTest::test_purge_is_idempotent_on_empty`(:579) 추가. memory(4백엔드)와 대칭. 실행 **2 passed**. — hardening #2 해소.
- **#3 SoT**: 오너 결정(b) — v1.7.72 entry 로 6c-1·1b 소급 커버. — hardening #3 해소(단, 헤더 버전 미갱신 — Issues #1).

### 6. 전체 suite green + SoT 합치 ✅ (헤더 버전 불일치 — Issues #1)

- **전체 suite**: `python3 -m pytest -q` → **1817 passed / 4 skipped / 1519 subtests / 111.73s**. work_log 주장과 수치 완전 일치(1814→1817, 회귀 +3).
- **SoT v1.7.72·v1.7.73 entry**: 둘 다 존재·정확. v1.7.72는 6c-1·1b(indexing 백엔드 purge + 검증 hardening) 소급, v1.7.73은 6c-2(worker drain + 회귀 위치 버그 정직 기록). ✅
- **⚠️ SoT 헤더 버전 stale**: line 4 `계약 버전: v1.7.71` 인데 changelog 테이블 최신은 v1.7.73. 8f8ecd7 메시지 "정본 v1.7.72→v1.7.73" 의도대로라면 헤더도 v1.7.73 이어야 함. (승인일 line 5 `2026-06-26` 은 최초 승인일로 의도적일 수 있으나 버전 필드는 확실히 2버전 뒤처짐.)

## Issues / Risks

### Blocking (계약 의무) — 없음

boundary matrix 전 분기(순차 purge·실패 requeue·None 시 archive-only·`_archive_where` 경로 차단)가 명명 회귀로 매핑되고 양방향 뮤테이션으로 실증. 빈 칸 없음.

### Hardening recommendations (non-blocking)

1. **SoT 헤더 버전 미갱신** — `docs/system-contract-sot.md:4` `계약 버전: v1.7.71` → v1.7.73 로 갱신 권장(changelog 는 이미 v1.7.73). 문서 자기모순(헤더 vs changelog). 승인일 필드는 별도 검토.
2. **terminal partial-purge(all-or-retry 의 내재 성질)** — sink 가 max_attempts 초과 영구 장애 시 entry 가 FAILED(terminal) 되며, 그 전에 purge 된 sink 는 파기된 채 남음(순차 all-or-retry + per-sink bookkeeping 부재). 단 (a)각 sink 멱등, (b)project 는 core_sot 에서 이미 파기된 뒤라 잔류 vector 는 query 경로에 도달 못 하는 ghost(무해), (c)FAILED entry 가 log/모니터링에 가시. local 1인 안정 Chroma/ES 환경에서 terminal 장애 가능성 낮음. 6c-1/1b 검증 hardening #4(composite 관측성)와 동일 설계 트레이드오프. per-sink 재개가 필요하면 6d 이후 별도 설계.
3. **전수 가드 hardcoded roster** — `IndexingBackendPurgeCoverageTest` 는 "나열된 백엔드가 purge_project 를 잃으면" 잡지만 "새 project-scoped indexing 백엔드가 roster 에 빠지면" 못 잡음(6b-2 repo 가드와 동일 패턴·동일 한계). 새 백엔드 추가 시 `_INDEXING_PURGE_CONTRACTS` 수동 합류 필요(주석에 명시).
4. (경미) `_PurgeRecordingSink`(test:602)가 `drain` 미보유 — purge 경로에선 미호출이라 적합하나, `MemoryIndexMutationAdapter` 완전 구현은 아님. drain 테스트 재사용 시 주의.

## Verdict

**합격(PASS).** blocking 없음.

- `_drain_purge`·`run_once` 분기·Protocol/archive 구현·전수 가드 6→7 모두 정규 계약(D5·SoT·선행 검증)과 합치.
- **★ 회귀 위치 버그 수정 독립 확인**: 3개 회귀가 현재 실제 수집(3 passed, IndexSyncWorkerTest 26)되며, 양방향 뮤테이션(A:no-op→3 re-fail / B:삼킴→Test 2 re-fail)으로 진짜 계약 잠금 실증 — f81d145 의 무효 가드(수집 제외)가 아님. 작업자 자가 보고·정직 기록과 일치.
- 전체 suite 1817 독립 재현(수치 완전 일치). 회귀 +3(위치 수정에서 온 실제 증가).
- hardening 4건 non-blocking(헤더 버전 갱신 1건은 1줄 수정 권장). 선행 검증 hardening #1·#2·#3 은 b2d6cbd·3bbcd71 로 해소.

## Outstanding items

- **6d(next, D8-6 마지막)**: `POST /admin/projects/{id}/purge` endpoint + `_REQUIRE_ADMIN` + boundary matrix(ADMIN +1·총 +1). **유일한 operation 카운트/공개 API 변화 슬라이스** — 이 슬라이스에서 endpoint·boundary·operation 카운트·SoT operation 면이 함께 잡혀야 함.
- **Hardening #1(SoT 헤더 v1.7.73 갱신)**: 1줄 수정, 6d 또는 즉시 권장.
- **test-mongo**: healthy(이 세션 가동). 6d 회귀용 재사용 가능.
- 작업 트리 clean. push 는 오너.

## Reproduction

```bash
# 전체 green bar
python3 -m pytest -q
# → 1817 passed, 4 skipped, 1519 subtests (test-mongo ON)

# 회귀 3 수집 확인(이름 실행 — collected/selected 로 수집 판정)
python3 -m pytest tests/test_indexing_phase3a.py -v -k purge_drain
# → 3 passed, 23 deselected (IndexSyncWorkerTest 26)

# 양방향 뮤테이션(각: 변이 → re-fail → git checkout -- service.py 원복)
# A(under-strict): service.py _drain_purge purge 3호출을 `pass` 로   → 3 re-fail
# B(over-strict):  _drain_purge except절을 `pass`(→success) 로        → Test 2 re-fail

# 전수 가드
python3 -m pytest tests/test_purge_project_coverage.py -v
# → 4 passed (PurgeProjectCoverageTest 2 + IndexingBackendPurgeCoverageTest 2)
```
