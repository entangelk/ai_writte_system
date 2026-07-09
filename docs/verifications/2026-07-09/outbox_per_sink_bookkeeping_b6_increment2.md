# 검증 기록 — (b-6) 증분2: outbox per-sink bookkeeping (SoT v1.6.57)

## Subject metadata

- **날짜**: 2026-07-09
- **요청자**: 오너(사용자) — "작업 AI의 작업 내용 확인하고 검증하고 의심하고 또 의심해줄래?"
- **검증자**: Claude(독립 감사, 구현 미관여)
- **대상 slice/artifact**: (b-6) 증분2 — index-sync outbox per-sink bookkeeping. SoT v1.6.57.
- **정본 계약 참조**:
  - 착수 결정 브리프 `docs/plans/04-worker-compose-outbox-bookkeeping-decisions.md`(상태 `Resolved`, 오너 결정 **G3=B / G4=B / G6=A**, 증분2 scope는 브리프 §G3/G4/G5/G6 및 "검증 계획" §증분2).
  - SoT `docs/system-contract-sot.md` v1.6.57 changelog entry(본문 line 36).
- **검증 대상 작업 출처**: working tree, **uncommitted**(git status `M` 16개 파일 — production 6 + test 6 + doc 4). commit hash 없음.

## Scope (canonical contract scope)

증분2에 관련된 계약 표면만. 증분1(worker compose 서비스, v1.6.56)·Phase 7 기획·b-2/b-5는 본 검증 범위 밖(브리프가 증분2로 chain하지 않음).

1. **계약(브리프)**: G3=B·G4=B·G6=A 결정 본문, "검증 계획" §증분2, "한계/수용 사항" #1(ES-lexical backfill 부재).
2. **구현 코드**:
   - `services/application/app/indexing/models.py`(`IndexSyncTargetState`·`SinkOutcome`·`IndexSyncLastError`).
   - `services/application/app/indexing/service.py`(`_PER_SINK_EVENTS`·`_enqueue_event`·`run_once` 분기·`_drain_sinks`/`_drain_archive`·`_merge_target_states`/`_classify_targets`/`_sink_terminal`·`record_outbox_*` Protocol/InMemory·`_sync_log`).
   - `services/application/app/indexing/memory_index.py`·`candidate_index.py`(composite `drain`).
   - `services/application/app/indexing/mongo_repository.py`(`_target_state_doc`/`_to_target_state` round-trip·`record_outbox_*`·requeue `$set`).
   - `scripts/index_sync_worker.py`(`_build_memory_adapter`/`_build_candidate_adapter` always-composite).
3. **회귀 테스트**: `tests/test_candidate_index.py`(`CompositeDrainTest`·`WorkerDispatchTest`·`PerSinkBookkeepingTest`)·`tests/test_indexing_phase3a.py`·`tests/test_indexing_mongo.py`·`tests/test_index_sync_worker_script.py`·`tests/test_context_search_memory_lexical_retrieval.py`·`tests/test_memory_vector_index.py`.
4. **전체 스위트**: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` 재현성.
5. **문서 정합**: SoT v1.6.57 entry·CHANGELOG top·HANDOFF·work_log.

## Methodology (재현 가능한 절차)

- **계약 범위 선행**: 본문을 열기 전 브리프에서 should-fire/should-NOT-fire 분기와 literal을 추출해 boundary matrix(lock list)를 먼저 구축.
- **구현 대조**: `git diff -- <file>`로 각 production 파일의 변경을 읽고, 브리프 계약·boundary matrix와 줄 단위 대조. 필요 시 `Read`로 주변 문맥(`run_once` 시그니처·clock threading·leaf adapter not-found 처리)을 추가 독해.
- **외과적 변경 sweep**: `grep -rn`으로 구식 속성(`_adapters`)·제거 상수(`CHROMA_TARGET`)·구식 enum(`IndexSyncBackend` in targets context)·구식 호출자(`.index_memory(`/`.index_candidate(`)·composite 생성자 형태를 repo 전수 검사.
- **경계 분기 회귀 추적**: 각 boundary cell을 named test에 매핑. 빈 셀(추적 안 된 분기)은 blocking finding.
- **스위트 실행**: `PYTHONPATH=. python3 -m pytest -q` 전체 → mongo 4개 실패 원인 독해 → `--ignore=tests/test_memory_mongo.py`로 702/45 재현. focused 회귀는 변경 test 7개 파일로 먼저 단축 신호.
- **smoke/envelope 재계산**: 본 slice는 발견 건수·심도 envelope을 emit하지 않으므로, 보고된 숫자는 pytest count(702/45)로 한정해 재계산.
- **문서 정합**: SoT version header·CHANGELOG top·HANDOFF diff·work_log diff를 읽어 구현·브리프와 교차 정합.

정확한 명령은 **Reproduction** 절 참조.

## Boundary matrix (lock list) — 브리프에서 추출

**Should-fire (G3=B/G4=B)**:
- F1 worker가 claim 시 실제 sink target을 materialize(enqueue는 sink-agnostic).
- F2 각 sink의 `attempt_count`가 독립 증가.
- F3 성공 sink는 SUCCESS로 동결(replay 시 skip).
- F4 실패 sink는 `SinkOutcome(ok=False, BACKEND_ERROR)`(swallow/전파 아님) — all-or-nothing raise 폐지.
- F5 all-SUCCESS → entry 삭제.
- F6 all-terminal(SUCCESS + per-sink-max FAILED) → entry 삭제.
- F7 부분 실패 → targets `$set` 영속 requeue.
- F8 transient 실패 복구 → all-SUCCESS → 삭제(DLQ 아님).
- F9 `_build_*_adapter` ES 무관 항상 composite + named `(target, backend)`.
- F11 per-sink max = `entry.max_attempts`(=3).

**Should-NOT-fire (over-strict)**:
- N1 한 sink 실패가 healthy sink를 DLQ poison 금지(본 slice가 고치는 버그).
- N2 SUCCESS sink replay 시 재색인 금지.
- N3 enqueue가 sink target을 hardcode 금지.
- N4 새 enum member 금지(`backend` str, `"elasticsearch"`) — G6=A.
- N5 archive 경로가 per-sink로 빠지지 않을 것(종전 whole-event max_attempts DLQ 보존).

## Findings

### 1. 계약(브리프) — 내부 정합

브리프 `docs/plans/04-...-decisions.md`의 증분2 결정(G3=B/G4=B/G6=A)은 본문·"검증 계획"·"한계/수용 사항" §1 간에 모순 없이 정합하다. 증분2 scope는 "필드 추가"가 아닌 "이미 존재·inert인 `targets` 표면을 worker가 갱신하도록 wire-up"으로 명시(브리프 §"핵심 발견" line 22-29)되며, 이는 SoT v1.6.57 entry의 "v1.6.52/54가 두 번 미룬 per-target bookkeeping 해소" 서술과 일치. **G6=A**(새 literal 없음)와 G3=B(per-sink 예산)는 상충하지 않는다 — per-sink max로 기존 `INDEX_SYNC_MAX_ATTEMPTS`(=3)를 재사용해 새 상수 도입 없이 per-sink 예산을 실현(이는 구현 §3에서 확인). 계약 내부 모순(blocking) 없음.

### 2. 구현 — `models.py`

`IndexSyncTargetState`에 `attempt_count: int = 0`·`last_error: IndexSyncLastError | None = None` 추가, `backend: IndexSyncBackend` → `backend: str` 완화(models.py:76-84). 신설 `SinkOutcome(target/backend/ok/error)`(models.py:88-95). `IndexSyncLastError`를 `IndexSyncTargetState` 위로 이동(참조 순서, 무해). 브리프 G3=B(per-sink 필드)·G6=A(str backend, enum member 미추가)와 정합. **F2·F4·N4 locked at model level**.

### 3. 구현 — `service.py` (핵심)

- `_PER_SINK_EVENTS = {MEMORY_UPSERTED, CANDIDATE_UPSERTED}`(service.py:48-51). archive event는 제외 → `_drain_archive`로 라우팅. **N5 dispatch 기반**.
- `_enqueue_event`: `targets={}`(service.py:394-398). **F1·F9·N3**.
- `run_once`(service.py:445-): `now` param → `clock`, event 종류로 `_drain_sinks`/`_drain_archive` 분기(service.py:469-472). `_Disposition` enum으로 summary counter 구동.
- `_drain_sinks`(service.py:518-571): `skip = frozenset(SUCCESS targets)`(service.py:547-551) → `adapter.drain(entry, skip=)` → `_merge_target_states` → `_classify_targets`. SUCCEEDED → `record_outbox_success(targets=)`; else → `record_outbox_failure(targets=, terminal=(FAILED))`. **F2·F3·F5·F6·F7**.
- `_merge_target_states`(service.py:838-859): `merged = dict(entry.targets)`(SUCCESS sink 동결 carry-forward) + 각 outcome sink `attempt_count = prior_attempts + 1`. 각 sink 독립 예산. **F2**.
- `_classify_targets`(service.py:862-883) + `_sink_terminal`(service.py:886-891): `not targets or all-SUCCESS → SUCCEEDED`; `all(_sink_terminal) → FAILED`; else `REQUEUED`. `_sink_terminal`: SUCCESS→True / FAILED and `attempt_count >= max_attempts`→True. **F5·F6·F11**. per-sink max가 `entry.max_attempts`(=3) 재사용 → G6=A 정합(새 literal 없음).
- `record_outbox_success`/`record_outbox_failure`(Protocol service.py:108-122 / InMemory service.py:190-247): `targets`/`terminal` optional 추가. InMemory `record_outbox_failure`는 `terminal is None`일 때만 per-event `attempt_count >= max_attempts` 폐백(archive 경로). per-sink 호출은 항상 명시적 `terminal=` 전달 → per-event max 폐백 미도달. **archive 후진호환(N5) 보존**.

### 4. 구현 — composite drain (`memory_index.py:218-243`·`candidate_index.py:204-229`)

양 composite 대칭. `drain(entry, *, skip)`: 각 `(target, backend, adapter)` sink에 대해 `target in skip → continue`, else `try adapter.index_memory/index_candidate → SinkOutcome(ok=True/False)`. all-or-nothing raise 폐지, per-sink `try/except` 격리. **F3·F4·N1·N2 locked here**.

### 5. 구현 — `mongo_repository.py` round-trip

`_target_state_doc`(mongo_repository.py:260-273): `status.value`·`backend`(str as-is)·`attempt_count`·`last_error`. `_to_target_state`(mongo_repository.py:315-325): `backend=doc["backend"]`(enum 강제 없음 → `"elasticsearch"` round-trip 안전)·`attempt_count=doc.get("attempt_count", 0)`(후진호환)·`last_error`. `record_outbox_failure` requeue 경로(mongo_repository.py:207-223)가 `$set targets`(per-sink `_target_state_doc`) 영속. **F7·N4**.

### 6. 구현 — `index_sync_worker.py` always-composite

`_build_memory_adapter`/`_build_candidate_adapter`(index_sync_worker.py:75-143·161-221): ES 무관 **항상** `Composite*Adapter(tuple(sinks))` 반환, `sinks = [(VECTOR_TARGET, backend, adapter)]`, ES 시 `(LEXICAL_TARGET, ELASTICSEARCH_BACKEND, lexical)` 추가. 단일 vector sink가 no-ES 배포 mirror. **F9**.

### 7. 회귀 테스트 — boundary cell 추적 (빈 셀 없음)

| Cell | Test (file:func) | 방향 |
|---|---|---|
| F1·F9·N3 (enqueue 빈 targets) | `test_indexing_mongo.py`·`test_indexing_phase3a.py::test_project_archive_creates_sink_agnostic_pending_outbox_entry` (`entry.targets == {}`) | under-strict |
| F2 (독립 attempt_count) | `test_candidate_index.py::PerSinkBookkeepingTest::test_failing_sink_requeues_only_itself_until_per_sink_max` (lexical 1→2→3) | under-strict |
| F3·N2 (SUCCESS skip) | `test_candidate_index.py::test_drain_skips_already_succeeded_targets` (vector.calls==0) + PerSinkBookkeeping (vector.calls==1 after 3 pass) | over-strict |
| F4 (격리, 양방향) | `test_candidate_index.py::test_sink_failure_is_isolated_not_swallowed_not_propagated` (healthy ok=True·failing ok=False+BACKEND_ERROR) | 양방향(구 `test_sink_failure_propagates_not_swallowed` 재lock) |
| F5 (all-SUCCESS 삭제) | `test_candidate_index.py::WorkerDispatchTest::test_candidate_upserted_dispatches_to_candidate_adapter` (`outbox_entries == {}`) | under-strict |
| F6·F11 (all-terminal·per-sink max=3) | PerSinkBookkeeping pass 3 (`outbox_entries == {}`, lexical.calls==3) | under+over |
| F7 (부분 실패 requeue) | PerSinkBookkeeping pass 1/2 (`entries_requeued==1`) + mongo `$set` 코드 독해 | under-strict |
| F8 (transient 복구 삭제) | `test_candidate_index.py::PerSinkBookkeepingTest::test_failed_sink_recovers_on_retry_then_entry_deleted` | under-strict |
| F9 (always-composite named) | `test_index_sync_worker_script.py` 6 case (sink `[:2]` identity, leaf via `_sinks[0][2]`) | 양방향 |
| N1 (healthy 미 poison) | PerSinkBookkeeping (vector SUCCESS 동결, lexical만 재시도) | over-strict |
| N4 (enum member 없음) | `models.py` 독해 + `test_index_sync_worker_script.py` (backend `"elasticsearch"` str) | — |
| N5 (archive whole-event 보존) | `test_indexing_phase3a.py::test_backend_error_uses_one_minute_then_five_minute_backoff_then_failed` (PROJECT_ARCHIVED, attempt_count [1,2,3], 60s/300s backoff, DLQ-at-3) | over-strict |

**모든 boundary cell이 named regression test에 추적됨. 빈 셀 없음.** 각 테스트는 assertion이 계약을 직접 pin(부산물 아님), under-strict(버그 재발 시 재실패)·over-strict(should-NOT-fire 분기) 양쪽 락 보유. `PerSinkBookkeepingTest`는 worker→repo→outbox entry 전 루프를 InMemory repo로 구동하는 end-to-end 락.

### 8. 전체 스위트 실행

`PYTHONPATH=. python3 -m pytest -q` → **4 failed, 702 passed, 45 skipped**. 4 failed는 전부 `tests/test_memory_mongo.py::MongoMemoryRepositoryTest`(live Mongo 필요). 실패 traceback은 pymongo 연결/인증 경로(`_check_response_to_command`/wire-version/server-selection)로 assertion 실패가 아님 → sandbox에 live Mongo가 없어서 발생, **b-6 증분2 코드 결함 아님**. `--ignore=tests/test_memory_mongo.py` → **702 passed, 45 skipped**(작업 AI 보고와 정확 일치, 재현됨). focused(변경 test 7 파일) → 104 passed/7 skip. `git diff --check` clean.

### 9. 외과적 변경 sweep — clean

`grep -rn` 전수: 구식 `_adapters`(composite 구 속성) 0건·`CHROMA_TARGET` 0건·composite 구 positional 생성자 0건. `.index_memory(`/`.index_candidate(` 호출자는 leaf adapter 내부(composite drain·`phase4_lexical_memory_live_smoke.py:117`은 leaf `MemoryLexicalIndexSyncAdapter` 직접 구동, composite 아님 → 파손 아님)·leaf 단위 테스트만. `IndexSyncBackend` enum은 정의·`FAKE_VECTOR_BACKEND`/`CHROMA_VECTOR_BACKEND` 상수·`test_indexing_mongo_indexes.py`(수정 미포함, StrEnum=str 호환)에 잔존하나 모두 정상. orphan 정리(`CHROMA_TARGET`/`IndexSyncBackend` import 제거)는 본 변경이 만든 것만. **외과적 변경 원칙 준수**.

### 10. 행동 회귀 부재 — `DerivedIndexRecordNotFound` 국소화

구 `_process_entry`의 외곽 `except DerivedIndexRecordNotFound → success`가 `_drain_archive`로 이동. 이 예외는 `chroma.py:249`(`ChromaArchiveAdapter.mark_archived`)에서만 raise. memory leaf(`MemoryIndexSyncAdapter.index_memory`, memory_index.py:178)는 `MemoryNotFound`를 내부 catch해 self-heal(delete+return), candidate leaf는 not-found/transitioned를 delete+return — **둘 다 raise하지 않음**. 따라서 per-sink drain 경로는 이 예외를 만나지 않고, archive 경로의 idempotent success 의미가 `_drain_archive`에서 정확히 보존. **행동 회귀 없음**.

### 11. 문서 정합

SoT version header `v1.6.57`(line 3)·v1.6.57 changelog entry(line 36)는 브리프 G3=B/G4=B/G6=A·구현·수용 한계를 정확 반영. CHANGELOG top entry 동일. HANDOFF는 v1.6.57로 bump·테스트 702/45 갱신·"outbox per-sink bookkeeping 완료"·(b-6) 증분2를 활성 작업에서 완료로 이동·ES-lexical backfill을 Next Tasks #1 첫 후보로 기록. work_log §"(b-6) 증분2"는 구현·회귀·수용 한계를 상세 기록. 내부 정합.

## Issues / Risks

- **차단 발견(불합격 사유)**: 없음. 모든 boundary cell 추적됨, 코드-계약 정합, 행동 회귀 부재, 스위트 재현.
- **비차단 관찰 #1 (`_classify_targets` 빈-targets SUCCEEDED 폐백)**: `not targets → SUCCEEDED`(service.py:866-869)는 empty composite 시 silent no-op 성공·삭제로 이론적 가능. 단 worker builder는 항상 ≥1 sink로 생성 → 도달 불가. 코드 주석이 "should not happen" 명시. 회귀로 pin되지 않았으나 도달 불가 경로라 blocking 아님.
- **비차단 관찰 #2 (양-sink 동시 실패 명시 pin 부재)**: "두 sink가 동시에 실패해 함께 requeue 후 함께 terminal DLQ" 시나리오가 명시 테스트로 pin되진 않음. 단 `_classify_targets`/`_merge_target_states` 로직이 단일-sink 실패 테스트와 동일 코드 경로라 논리적으로 커버. 별도 경계라기보단 동일 경로의 합성.
- **비차단 관찰 #3 (per-event `attempt_count`의 vestigial화)**: per-sink event에서 outbox entry의 per-event `attempt_count`는 backoff 산정에만 쓰이고 terminal 결정은 per-sink 상태가 주도. repo의 `terminal is None` 폐백은 per-sink 호출이 항상 명시적 `terminal=` 전달해 미도달. 무해하나, 향후 per-sink와 per-event 의미가 혼동될 여지 존재(현재 정합).
- **수용 한계(오너 인지, blocking 아님)**: ES-lexical backfill 부재(브리프 한계 #1·SoT entry·HANDOFF Next Tasks #1에 기록). per-sink-max로 terminal drop된 ES-only 실패는 수렴 수단 없음. 본 slice의 scope가 아니며 fix(ES-lexical backfill 스크립트)는 후보로 추적 중.
- **sandbox 밖 관통**: 실 배포에서 한 sink만 죽였을 때 Mongo outbox `targets`가 per-sink 상태를 반영하는지 end-to-end는 테스트가 InMemory repo로 전 루프를 구동해 간접 검증(실 Mongo 직접 관통은 sandbox 밖 후속).

## Verdict

**합격 (PASS)**.

이유(하중 인자):
1. **계약 정합**: 구현이 브리프 G3=B/G4=B/G6=A를 literal까지 정확히 실현. 계약 내부 모순 없음.
2. **경계 매트릭스 빈 셀 없음**: should-fire 10개·should-NOT-fire 5개 분기 전부 named regression test에 추적, 양방향(under-strict + over-strict) 락. 구 all-or-nothing pin 테스트가 per-sink 격리로 양방향 재lock됨. `PerSinkBookkeepingTest`가 worker→repo→outbox 전 루프를 end-to-end로 구동.
3. **행동 회귀 부재**: archive whole-event DLQ-at-max 경로 보존(`test_backend_error_uses_one_minute...`), `DerivedIndexRecordNotFound` idempotent success 의미 `_drain_archive`에 정확히 국소화.
4. **스위트 재현**: 702 passed/45 skipped(mongo env 제외) 정확 재현, 4개 mongo 실패는 연결 환경 artifact(코드 결함 아님), `git diff --check` clean.
5. **외과적 변경**: 구식 참조 0건, orphan 정리는 본 변경분만.
6. **수용 한계 투명**: ES-lexical backfill 부재가 오너 인지 사항으로 문서에 명시 추적됨.

차단 조건 없음. 비차단 관찰 3건은 future-hardening 영역이며 현재 정합성에 영향 없음.

## Outstanding items (오너 다음 단계에 영향)

- **uncommitted working tree**: 본 slice 16개 파일이 모두 working tree에 uncommitted 상태. 오너의 commit/push 결정 대기(검증자는 commit하지 않음 — CLAUDE.md "검증 실패 시 silently fix 금지"의 대칭: 합격이어도 검증자가 대신 commit하지 않음).
- **ES-lexical backfill 후보 대기**: b-6 브리프의 두 증분 소진. 다음 slice는 오너 선택 대기(후보: ES-lexical backfill / b-4 hybrid 튜닝 / (c)~(e) / Phase 6). 각 후보는 착수 전 결정 브리프 필요.
- **sandbox 밖 실 배포 관통**: per-sink bookkeeping의 실 Mongo end-to-end 검증은 후속(본 검증은 InMemory repo로 전 루프 검증).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# 1. 변경 범위·외과적 변경 sweep
git status --short
git diff --check                                              # clean
grep -rn "_adapters\b\|CHROMA_TARGET" services/ scripts/ tests/   # 0건

# 2. 핵심 회귀(변경 test 파일 focused)
PYTHONPATH=. python3 -m pytest -q \
  tests/test_candidate_index.py tests/test_indexing_phase3a.py \
  tests/test_indexing_mongo.py tests/test_index_sync_worker_script.py \
  tests/test_context_search_memory_lexical_retrieval.py \
  tests/test_memory_vector_index.py tests/test_indexing_mongo_indexes.py
# → 104 passed, 7 skipped

# 3. 전체 스위트(mongo 환경 제외 = 프로젝트 검증 관례)
PYTHONPATH=. python3 -m pytest -q --ignore=tests/test_memory_mongo.py
# → 702 passed, 45 skipped   (live Mongo 없으면 --ignore 없이는 4 failed = 연결 환경 artifact)

# 4. per-sink 핵심 경계 직접 구동
PYTHONPATH=. python3 -m pytest -q \
  "tests/test_candidate_index.py::PerSinkBookkeepingTest" \
  "tests/test_candidate_index.py::CompositeDrainTest" \
  "tests/test_indexing_phase3a.py::IndexSyncWorkerTest::test_backend_error_uses_one_minute_then_five_minute_backoff_then_failed"
# → 전부 passed
```
