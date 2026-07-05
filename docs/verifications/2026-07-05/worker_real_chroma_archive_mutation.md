# Verification — worker→real Chroma archive mutation 배선

## Subject metadata

- 날짜: 2026-07-05
- 요청자: 오너 (작업 AI 산물의 독립 검증 요청 — “검증하고 의심하고 또 의심해줄래”)
- 검증자: Claude Code (독립 감사, 작업자와 무관)
- 대상 slice: Phase 3B index sync worker → real Chroma archive mutation 배선 (SoT v1.6.37)
- 정본 스펙 참조:
  - `docs/plans/03-index-worker-retry-decisions.md` §8 (닫힌 결정과 수용 기준), 특히 §8.2 (Archive worker-time `not_found`), §8.3 (Fake archive mutation operation), §8 “명시적 후속”
  - `docs/system-contract-sot.md` v1.6.37 changelog 및 §Phase 3B 갱신
- 검증 대상 work source: working tree, uncommitted (branch `phase4-slice-4-2-planner`). 변경 파일: `services/application/app/indexing/chroma.py`, `scripts/index_sync_worker.py`, `tests/test_chroma_adapter.py`, `tests/test_index_sync_worker_script.py`, `docs/system-contract-sot.md`, `docs/daily_logs/2026-07-05/work_log.md`, `HANDOFF.md`.

## Scope

아래 표면을 스펙-코드-테스트-문서 한 묶음으로 검증한다.

1. **스펙 계약**: 브리프 §8.2/§8.3/§8 “명시적 후속”이 archive mutation에 대해 규정하는 boundary.
2. **구현 코드**: `ChromaArchiveIndexMutationAdapter` / `_archive_where` / `ChromaCollection.delete` (`chroma.py`), `_build_archive_adapter` / summary `archive_backend` (`index_sync_worker.py`).
3. **회귀 테스트**: `tests/test_chroma_adapter.py`(`ChromaArchiveMutationTest`, `ChromaArchiveWorkerIntegrationTest`) 및 `tests/test_index_sync_worker_script.py`(`BuildArchiveAdapterTest`).
4. **문서 정합**: SoT v1.6.37 changelog, work_log, HANDOFF가 구현과 일치하는지, 그리고 스펙 인용이 정확한지.

## Methodology

스펙 우선(scoping-first) 검증. 코드를 먼저 보지 않고 브리프 §8에서 boundary matrix를 먼저 세운 뒤, 각 cell이 코드 리터럴 ↔ 테스트 ↔ 문서에 모두 매핑되는지 추적했다. 모든 클레임은 `file:line` 기반으로 재도출.

실행 명령(모두 저장소 루트에서):

```bash
# diff 파악
git diff --stat HEAD
git diff HEAD -- scripts/index_sync_worker.py services/application/app/indexing/chroma.py
git diff HEAD -- tests/test_chroma_adapter.py tests/test_index_sync_worker_script.py
git diff HEAD -- docs/system-contract-sot.md docs/daily_logs/2026-07-05/work_log.md HANDOFF.md

# 스펙 독해
# docs/plans/03-index-worker-retry-decisions.md §5, §6, §7, §8 (경계 조항까지 end-to-end)

# 코드-스펙 대조를 위한 심볼 위치 탐색
grep -n "DerivedIndexRecordNotFound\|class IndexSyncWorker\|mark_archived\|CHROMA_VECTOR_BACKEND\|FAKE_VECTOR_BACKEND" services/application/app/indexing/service.py
grep -n "PROJECT_ARCHIVED\|DRAFT_ARCHIVED\|mongo_id" services/application/app/indexing/models.py services/application/app/indexing/service.py
sed -n '52,140p' services/application/app/indexing/chroma.py   # record_to_chroma metadata 매핑
sed -n '274,440p' services/application/app/indexing/service.py # worker run_once 매핑

# import 방향/순환 점검
grep -n "import" services/application/app/indexing/service.py | grep -i chroma   # service→chroma import 없음 확인
grep -n "from services.application.app.indexing.service" services/application/app/indexing/chroma.py
grep -n "import chromadb" services/application/app/indexing/chroma.py            # lazy import 확인

# 테스트 재현 (작업자 클레임 검증)
python3 -m unittest discover tests
python3 -m pytest -q tests
python3 -m pytest -q tests/test_chroma_adapter.py tests/test_index_sync_worker_script.py
git diff --check
```

## Boundary matrix (스펙에서 도출한 lock list)

| # | boundary (스펙 출처) | 코드 리터럴 | 테스트 매핑 |
|---|---|---|---|
| B1 | `mark_archived(entry)` seam (§8.3 “`mark_archived(source)` 또는 `delete_or_tombstone(source)` equivalent”) | `chroma.py` `ChromaArchiveIndexMutationAdapter.mark_archived` | `ChromaArchiveMutationTest.setUp` |
| B2 | project_archived = 해당 project 전체 derived record 삭제 (§8.2 “archived project가 derived index에서 노출되지 않게”) | `_archive_where`: `{"project_id": entry.project_id}` (`chroma.py:215`) | `test_project_archived_deletes_only_that_projects_records` |
| B3 | draft_archived = project-scoped 해당 draft만 삭제 | `_archive_where`: `{"$and":[{"project_id":...},{"draft_id":entry.source.mongo_id}]}` (`chroma.py:217-223`) | `test_draft_archived_deletes_only_that_draft_scoped_to_project` |
| B4 | 대상 부재 → `DerivedIndexRecordNotFound` (§8.2 채택 B “이미 없으면 success”) → delete 미호출 | `mark_archived` `get(include=[])` 후 `len(ids)==0` raise (`chroma.py:244-249`) | `test_project_archived_with_no_records_is_idempotent_not_found`, `test_draft_archived_with_no_records_is_idempotent_not_found` |
| B5 | worker가 `DerivedIndexRecordNotFound`를 idempotent success로 매핑 (§8.2 채택 B) | `IndexSyncWorker.run_once` except 절 → `record_outbox_success` (`service.py:391-396`) | `test_worker_treats_missing_records_as_idempotent_success` |
| B6 | worker 삭제 성공 → terminal success + outbox 제거 | `_process_entry` → `mark_archived` → else success (`service.py:431`, `:446-450`) | `test_worker_deletes_matching_records_and_records_success` |
| B7 | `CHROMA_HOST` 설정 시 real Chroma adapter (env 규약 = create_app B.4) | `_build_archive_adapter` (`index_sync_worker.py:25-42`) | `test_with_chroma_host_builds_chroma_archive_adapter` |
| B8 | `CHROMA_HOST` 미설정 시 종전 recording fake fallback | 동일 함수 폴백 분기 | `test_without_chroma_host_uses_recording_fake` |
| B9 | summary JSON `archive_backend` (`chroma`/`in_memory_fake`) | `run_worker` return (`index_sync_worker.py:79,82`) | `test_run_worker_outputs_summary_json`, `BuildArchiveAdapterTest` 반환값 |
| B10 | numpy-like truthiness 회피 (B.5 fix 패턴 — 작업자 명시적 주장) | `if len(ids) == 0:` (`chroma.py:246`) | **(없음 — 아래 F1)** |
| B11 | `_archive_where` unsupported event 거부 (defensive) | `raise ValueError(...)` (`chroma.py:224-225`) | **(없음 — 아래 F3)** |

## Findings

### 1. 스펙 계약 (§8.2 / §8.3 / §8 “명시적 후속”)

§8.2 채택 B: “archive/tombstone/**delete** 대상 record가 이미 없으면 목표 상태 달성으로 보고 success 처리한다” + “Archive event의 목표는 archived project/draft가 derived index에서 노출되지 않게 하는 것이다”. §8.3: fake adapter는 “`mark_archived(source)` 또는 `delete_or_tombstone(source)` equivalent call을 recording-only로 제공”하되 “실제 vector record mutation은 하지 않는다”. §8 “명시적 후속”: “실제 ChromaDB/Elasticsearch adapter mutation”.

→ 이 slice는 §8 “명시적 후속”으로 미뤄둔 real adapter mutation을 회수한다. 허용 범위 내다. (단, 스펙 인용 정확성은 아래 F2 참조.)

스펙 내부 모순(§8.2 ↔ §8.3 ↔ changelog)은 발견되지 않았다.

### 2. 구현 코드

스펙-코드 리터럴 일치:

- `_archive_where` project/draft 분기(`chroma.py:213-225`): PROJECT_ARCHIVED → `{"project_id": entry.project_id}`; DRAFT_ARCHIVED → `$and` project+draft. §8.2 의도와 부합.
- `entry.source.mongo_id`가 draft id인 것 확인: `enqueue_draft_archived`가 `mongo_id=draft_id`로 entry 생성 (`service.py:290-298`). 작업자 주장 정확.
- metadata에 `project_id`/`draft_id`가 실제 저장됨: `record_to_chroma`가 둘 다 metadata에 flatten (`chroma.py:71,73`). → Chroma where 절이 실제 매칭 가능.
- 대상 부재 → `DerivedIndexRecordNotFound`, delete 미호출: `mark_archived`가 `get(where, include=[])` 후 `len(ids)==0`이면 raise 후 return (`chroma.py:244-249`). §8.2 채택 B와 정확히 일치.
- worker 매핑: `DerivedIndexRecordNotFound` except → `record_outbox_success` (`service.py:391-396`); 일반 Exception → `BACKEND_ERROR` failure (`service.py:397-407`). §8.2 idempotent success 정책 정확히 구현.
- backend literal: `FAKE_VECTOR_BACKEND="in_memory_fake"`, `CHROMA_VECTOR_BACKEND="chroma"` (`service.py:35-36`). summary `archive_backend` 매핑 일치.
- env 규약: `CHROMA_HOST`/`CHROMA_PORT`(기본 8000)/`CHROMA_COLLECTION`(기본 `DEFAULT_COLLECTION_NAME`=`project_memory_vectors`) (`index_sync_worker.py:30-40`). create_app B.4와 동일 규약.
- import 단방향: `service.py`는 `chroma`를 import하지 않는다 (grep 결과 없음). `chroma.py` → `service.DerivedIndexRecordNotFound` 단방향 (`chroma.py:25`). `chromadb`는 `connect_chroma_collection` 내부 lazy import (`chroma.py:260`). 순환 없음. 작업자 주장 정확.

### 3. 회귀 테스트

실행 재현:

- `python3 -m unittest discover tests` → **Ran 516 OK (skipped=45)**. 작업자 클레임과 정확히 일치.
- `python3 -m pytest -q tests` → **471 passed, 45 skipped**. 작업자 클레임과 정확히 일치.
- 신규 회귀 `tests/test_chroma_adapter.py tests/test_index_sync_worker_script.py` → 22 passed, 1 skipped.
- `git diff --check` → exit 0.

테스트가 잠근 범위(B2~B9): under-strict(버그 재현 시 재실패)와 over-strict(정상 case 무손상) 양방향이 모두 포함된 경우가 대부분이다. 특히:

- B2 over-strict: `test_project_archived_deletes_only_that_projects_records`가 타 project(`p2a`) 무손상을 `stored_ids()=={"p2a"}`로 명시 검증.
- B3 over-strict: `test_draft_archived_deletes_only_that_draft_scoped_to_project`가 **같은 draft id의 타 project record**(`p2d1`, project-2/draft-1) 무손상을 검증 — cross-project 충돌 방지 의도까지 lock.
- B4 under-strict: not_found 경로에서 `delete_calls == 0`을 명시 검증 → delete를 깜빡하고 호출하는 over-eager 구현도 잡음.

→ B2/B3/B4/B5/B6/B7/B8/B9는 단방향이 아닌 양방향으로 잠겨 있어 양호.

### 4. 문서 정합

- SoT v1.6.37 changelog/§Phase 3B 갱신, work_log “Completed work”, HANDOFF Next Tasks/Verification가 구현 리터럴(delete 방식, `_archive_where`, `DerivedIndexRecordNotFound`, `archive_backend`, env 규약)과 일치.
- 단, 스펙 인용 하나에 확대 해석이 있다 → 아래 F2.

## Issues / Risks

### F1. [BLOCKING — 조건부 합격 차단 조건] `mark_archived`의 numpy-like truthiness guard under-strict regression 누락

`chroma.py:246`의 `if len(ids) == 0:` 는 작업자가 “numpy-like truthiness 회피 위해 truthiness 대신 `len()` 사용(B.5 fix 패턴 준수)”라고 명시한 guard다. 그러나 **이 guard의 under-strict 방향 regression 테스트가 존재하지 않는다.**

근거:

- `FakeChromaCollection`은 이미 `ambiguous_ids` 플래그로 ids를 `AmbiguousTruthValueList`(`__bool__`이 ambiguous 에러를 raise하는 list subclass)로 감쌀 수 있게 구현돼 있다 (`tests/test_chroma_adapter.py:84`, get 메서드 `:122-125`).
- B.5 fix에서는 `_records_from_get`/`_records_from_query`에 대해 이 `ambiguous_ids`/`ambiguous_embeddings`/`ambiguous_metadatas`를 활성화한 회귀를 추가해, “real Chroma가 numpy-like container를 돌려줘도 `is None`/`len()` 검사로 회피한다”는 것을 unit으로 잡았다 (HANDOFF B.5 기록 및 `tests/test_chroma_adapter.py`의 numpy-like 회귀 참조).
- 그러나 `ChromaArchiveMutationTest`의 4개 테스트 모두 `ambiguous_ids`를 설정하지 않는다 (`setUp`이 `FakeChromaCollection()`을 default 그대로 사용). fake의 get이 빈 일반 list `[]`를 반환하므로, 현재 코드 `if len(ids) == 0:`와 regression 코드 `if not ids:`가 동일하게 동작한다.

실패 시나리오: 누군가 `if len(ids) == 0:`를 `if not ids:`로 되돌렸을 때, real Chroma client가 빈 결과를 numpy-like container로 반환하면 `__bool__`이 ambiguous `ValueError`를 raise → `mark_archived` 예외 전파 → worker `run_once`의 일반 Exception 분기 (`service.py:397`)가 이를 `BACKEND_ERROR`로 분류 → 3회 retry 후 `failed` terminal. 즉 **§8.2의 “대상 없음 = idempotent success” 정책이 real backend에서 조용히 깨지고, unit suite는 이를 잡지 못한다.**

CLAUDE.md 위반:

- “The boundary matrix has no empty cells — empty cells are blocking findings regardless of the green bar.”
- “Two-directional regression guards — under-strict guard: if the pre-fix bug is reintroduced, the test must re-fail.” (B10 cell이 빈 칸)
- “Never reframe a missing over-strict guard as ‘future enhancement’/‘보강 후보’/‘후속 보강 후보’.”

B.5가 동일한 패턴을 unit으로 잡을 수 있음을 이미 증명했으므로, “live smoke 후속”으로 미루는 정당화는 성립하지 않는다.

해결 권고: `ChromaArchiveMutationTest`에 케이스 1개 추가 — `collection.ambiguous_ids = True`로 설정한 뒤 빈 결과 상태에서 `mark_archived`가 (a) `DerivedIndexRecordNotFound`를 raise하고 (b) `delete_calls == 0`임을 검증. 이때 regression(`if not ids:`)은 `AmbiguousTruthValueList.__bool__`의 ValueError로 재실패해야 양방향 lock이 성립한다. 필요하면 매칭 record가 있는 상태에서도 `ambiguous_ids=True`로 `delete`가 정상 호출되는 over-strict 방향도 같이 잠글 것.

### F2. [NON-BLOCKING — 문서 정정 권고] delete vs tombstone “등가” 스펙 인용 확대

work_log “설계 결정” 및 요약이 “브리프 §8.3이 두 방식을 목적상 등가로 둔다”고 인용한다. 그러나 실제 스펙을 읽으면:

- §8.3은 fake adapter의 메서드명으로 `mark_archived(source)` / `delete_or_tombstone(source)`를 나열만 할 뿐, real adapter의 delete/tombstone 선택에 대한 “등가” 언급이 없다 (§8.3은 fake path 한정).
- §8.2 선택지 B 설명이 “archive/tombstone/delete 대상 record가 이미 없으면…”으로 세 방식을 하나의 허용 묶음으로 나열하는 것이 “등가” 근거에 가장 가깝다.

delete 선택 자체는 §8.2의 허용 묶음 + 합리적 근거(derived record의 SOT rebuild 가능성, archive 목표 = 검색 후보 제외, delete = 단일 원자 연산, query-time stale guard가 이미 정합성 보장)로 정당하다. 다만 인용을 “§8.2/§8.3이 delete와 tombstone을 둘 다 허용 목록에 나열”로 좁혀 정확히 기술할 것. 동작에는 무관 → non-blocking.

### F3. [NON-BLOCKING — boundary 빈 칸, 낮은 심각도] `_archive_where` unsupported event 분기 미검증

`_archive_where`가 PROJECT/DRAFT 외 event에 `ValueError`를 raise (`chroma.py:224-225`) 하지만, 이 분기를 검증하는 테스트가 없다 (B11 cell 빈 칸). 다만 worker `_process_entry`가 먼저 unsupported event를 `RuntimeError`로 차단 (`service.py:436-437`)하므로, 정상 경로에서 adapter까지 도달할 수 없다 — 즉 defensive dead-path다. 스펙은 PROJECT_ARCHIVED/DRAFT_ARCHIVED만 정의하므로 spec-silent defensive code이기도 하다. non-blocking이나 matrix 빈 칸으로 기록.

### F4. [NON-BLOCKING — outstanding] live smoke 미실행

실제 Chroma 서버 관통 live smoke(archive → outbox → worker command → 컨테이너 Chroma record 실삭제 확인)는 sandbox 밖 승인 네트워크가 필요해 미실행이다. 작업자가 후속으로 명시했고 HANDOFF Next Tasks에 반영돼 있다. 단, **F1의 under-strict guard가 없는 상태**이므로, live에서 real Chroma client의 ids 반환 타입(numpy-like 여부)이 `len()` guard로 실제 작동하는지는 현재 미검증이다. F1을 보강하면 unit에서 이 경로를 선제 lock할 수 있다.

## Verdict

**조건부 합격 (conditional pass).**

- 스펙-코드-테스트-문서의 핵심 정합성은 양호하다: §8.2 idempotent-success 정확 구현, `_archive_where` scope 정확(cross-project 무손상까지 over-strict lock), worker 매핑 양방향 검증, env 규약·backend literal·import 방향 모두 작업자 클레임과 일치. 전체 suite 516/471 재현됨.
- **차단 조건 (F1)**: `mark_archived`의 `len(ids) == 0` numpy-like truthiness guard에 대한 under-strict regression이 빠져 있다. 작업자가 “B.5 fix 패턴 준수”를 명시했으나, B.5가 `AmbiguousTruthValueList`로 잡았던 동일 패턴의 회귀를 여기서는 추가하지 않았고, `FakeChromaCollection.ambiguous_ids` 기능이 이미 존재함에도 활용하지 않는다. 이 빈 칸은 CLAUDE.md의 “boundary matrix has no empty cells” / “two-directional regression guards”에 의해 차단 조건이다. 보강 시 합격으로 전환.
- F2(스펙 인용 정정), F3(defensive dead-path 빈 칸)은 non-blocking.
- F4(live smoke)는 outstanding.

## Outstanding items

- F1 회귀 보강 대기 (오너/작업자 결정). 보강 전까지 real Chroma 빈 결과(numpy-like ids)에서 §8.2 idempotent-success가 실제로 관통할지 unit이 보증하지 못한다.
- live smoke 미실행 — sandbox 밖 승인 네트워크 필요 (HANDOFF Next Tasks 1에 반영됨).
- 커밋/푸시 미실행 — 오너 요청 시 진행 (작업자 명시).

## Reproduction

```bash
# 스펙-코드 대조
sed -n '204,250p' services/application/app/indexing/chroma.py        # ChromaArchiveIndexMutationAdapter / _archive_where
sed -n '274,440p' services/application/app/indexing/service.py       # worker 매핑 + enqueue_*
sed -n '52,82p'   services/application/app/indexing/chroma.py        # record_to_chroma metadata (project_id/draft_id 저장)
sed -n '70,140p'  docs/plans/03-index-worker-retry-decisions.md      # §8.2/§8.3

# 테스트 재현
python3 -m unittest discover tests                                    # Ran 516 OK (skipped=45)
python3 -m pytest -q tests                                            # 471 passed, 45 skipped
python3 -m pytest -q tests/test_chroma_adapter.py tests/test_index_sync_worker_script.py  # 22 passed, 1 skipped
git diff --check                                                      # exit 0

# F1 재현(회귀 주입): chroma.py:246 의 `if len(ids) == 0:` -> `if not ids:` 로 바꾼 뒤
# real Chroma 빈 결과를 모방하기 위해 fake에 ambiguous_ids=True 케이스가 **없으므로**
# 현재 unit suite는 재실패하지 않는다 — 이것이 F1의 빈 칸이다.
```
