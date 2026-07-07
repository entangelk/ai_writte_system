# Verification — Phase 2B.5 memory→vector 재색인 증분 2(라이브 배선)

## Subject metadata

- **Date**: 2026-07-07
- **Requester**: entangelk (오너) — “다음작업 검증해줘. Phase 2B.5가 완결됐습니다. 두 커밋 모두 main에 반영했습니다. … 증분 2 (a8b1d9b, 이번 턴): 라이브 배선.”
- **Verifier**: Claude (독립 검증, 구현 작업 미관여)
- **Target slice / artifact**: Phase 2B.5 **증분 2** — `services/application/app/memory/service.py`(choke-point 중앙화: `MemoryReindexOutbox` Protocol·`reindex_outbox`·`_enqueue_reindex`), `analysis/apply.py`(increment-1 apply-seam 흡수·제거), `indexing/chroma.py`(`ChromaMemoryVectorIndexAdapter` + `memory_record_to_chroma`/`memory_record_from_chroma`), `main.py`(create_app 배선), `scripts/index_sync_worker.py`(`_build_memory_adapter`), `scripts/phase2b5_reindex_memory.py`(backfill), `scripts/phase2b5_memory_reindex_live_smoke.py`(live smoke), 회귀 `test_memory_vector_index.py`(+4)·`test_chroma_memory_adapter.py`(11)·`test_analysis_apply_api.py`(+1)·`test_index_sync_worker_script.py`(+2)·`test_phase2b5_reindex_memory_script.py`(4).
- **Canonical spec reference**:
  - `docs/system-contract-sot.md` v1.6.46(version-table 신규 행 + §Phase 2B prose 행). v1.6.45 행은 증분 1 closure(dispatch 회귀 추가·본인 증분1 검증 인용)로 갱신됨.
  - `docs/plans/02b-5-memory-vector-reindex-decisions.md`(Resolved + Owner decision “promote 경로도 enqueue”).
  - 하위 계약: v1.6.44(2B.4 append-only), v1.6.40(2B.1 promote/auto-promote), v1.6.37(worker→real Chroma archive adapter 패턴).
- **Source of work being verified**: commit **a8b1d9b**(HEAD, `main`). 증분 1 closure는 **67b5362**.

## Scope

본 검증은 아래 표면을 2B.5 증분 2 계약(SoT v1.6.46 + 브리프 Owner decision) 대비로 점검한다.

1. **계약(contract)**: 오너 결정 “모든 canonical mint 경로(apply·수동 promote·auto-promote)가 enqueue” + choke-point 중앙화 경계(비-replay mint에서만 enqueue, replay/below-threshold/non-canonical-target는 무enqueue) + apply-seam 흡수 + 순환 회피.
2. **구현 코드**: `memory/service.py`(choke point), `analysis/apply.py`(seam 제거), `indexing/chroma.py`(memory adapter), `main.py`(wiring), `scripts/index_sync_worker.py`(drain), backfill/live smoke 스크립트.
3. **회귀 테스트**: 증분 1 closure(dispatch 1) + 증분 2 신규(promote-path 4·chroma adapter 11·apply HTTP wiring 1·worker memory 분기 2·backfill 4).
4. **공개 표면/envelope**: outbox entry(event/source), worker summary `memory_backend`, `MemoryIndexRecord`↔chroma round-trip, backfill summary.
5. **전체 스위트**(infra-free 단위 한정; 실 Chroma/Mongo 관통 live는 sandbox 밖 후속).

## Methodology

scoped reading(SoT v1.6.46 + 브리프 Owner decision + 하위 v1.6.44/2B.1)로 boundary matrix를 만들고, 각 분기를 회귀에 추적. 코드를 1차 원천으로 재유도하고, 독립 probe/변이(mutant)로 증명했다. choke-point “모든 mint 커버” 주장은 canonical-mint 지점을 grep으로 전수 확인.

```bash
# (1) 컴파일 + 위생(tree clean, 두 커밋 main 반영)
python3 -m py_compile services/application/app/memory/service.py \
  services/application/app/indexing/chroma.py services/application/app/main.py \
  services/application/app/analysis/apply.py scripts/index_sync_worker.py \
  scripts/phase2b5_reindex_memory.py scripts/phase2b5_memory_reindex_live_smoke.py
git status --porcelain   # clean
git log --oneline -1     # a8b1d9b

# (2) 증분 1 closure + 전체 스위트(mongo env 제외)
grep -n "memory_adapter=None\|BACKEND_ERROR\|not configured" tests/test_memory_vector_index.py
python3 -m pytest -q --ignore=tests/test_memory_mongo.py   # 598 passed / 45 skipped

# (3) canonical-mint 지점 전수(우회 경로 탐지)
grep -rn "status=MemoryStatus.CANONICAL" services/application/app/memory/   # 정확히 2곳

# (4) choke-point non-vacuity 변이(_enqueue_reindex 를 no-op)
PYTHONPATH=. python3 - <<'PY'
import unittest
from services.application.app.memory.service import MemoryService
MemoryService._enqueue_reindex = lambda self, m: None   # NEUTER
s = unittest.TestSuite()
for mod in ["tests.test_memory_vector_index","tests.test_memory_apply","tests.test_analysis_apply_api"]:
    s.addTests(unittest.TestLoader().loadTestsFromName(mod))
r = unittest.TextTestRunner(verbosity=0).run(s)
print(r.testsRun, len(r.failures), len(r.errors))   # 42 9 1  → 10 re-fail
PY
```

## Findings

### 1. 증분 1 조건부 합격 조건 폐쇄 확인

본인 증분 1 검증(`docs/verifications/2026-07-07/phase_2b_5_memory_vector_reindex_increment_1.md`)의 유일한 차단 조건(worker `MEMORY_UPSERTED` + adapter 미구성 → RuntimeError/BACKEND_ERROR 분기 회귀 부재)이 **67b5362에서 폐쇄**됐다. `tests/test_memory_vector_index.py:389 test_memory_upserted_without_adapter_records_backend_error`가 `memory_adapter=None` → `IndexSyncErrorType.BACKEND_ERROR` + requeue + detail `"memory index adapter is not configured"`를 단정한다. SoT v1.6.45 행도 closure를 기록하고 본인 검증을 인용했다. **빈 셀 해소.**

### 2. choke-point 중앙화 경계 ↔ 회귀 추적 (boundary matrix)

오너 결정 “모든 canonical mint가 enqueue”의 핵심. canonical-mint 지점 grep 결과 **정확히 2곳**(`service.py:160` promote_candidate, `:281` `_versioned_upsert`)이며, 우회 mint 경로는 없다(`put_memory` 호출도 동일 2곳만).

| # | 계약 경계(SoT v1.6.46 / Owner decision) | 코드 | 회귀 | 상태 |
|---|---|---|---|---|
| 1 | 수동 promote 신규 mint → enqueue | `service.py:160-178` | `test_manual_promote_enqueues_reindex` | LOCKED |
| 2 | **replay mint → enqueue 없음**(over-strict) | `service.py:172-176`(early return) | `test_manual_promote_replay_does_not_double_enqueue` | LOCKED |
| 3 | auto-promote threshold fire → enqueue(promote 경유) | `service.py:196-205`(→ promote_candidate) | `test_auto_promote_enqueues_when_threshold_fires` | LOCKED |
| 4 | **auto-promote below-threshold → enqueue 없음**(over-strict) | `service.py:201-202`(return None) | `test_auto_promote_below_threshold_does_not_enqueue` | LOCKED |
| 5 | versioned upsert(update/add_evidence) 신규 mint → enqueue | `service.py:281-307` | `test_update_replaces_prior_version_vector`(choke point 경유, version==2) | LOCKED |
| 6 | apply create → enqueue(MemoryService 경유) | `apply.py`(seam 제거, `apply.py:67-71`) | `test_create_enqueues_reindex`·`test_apply_create_enqueues_memory_upserted`(HTTP E2E) | LOCKED |
| 7 | apply no_change/conflict → enqueue 없음(mint 미호출) | `apply.py:_apply_one`(_skip) | `test_no_change/conflict_does_not_enqueue`(증분1) | LOCKED |
| 8 | outbox 미주입 → noop | `service.py:_enqueue_reindex`(None 가드) | (주입 memory_service 테스트 경로) | LOCKED(전이) |

모든 분기 추적 가능, over-strict(replay·below-threshold) 양방향 포함. **빈 셀 없음.**

### 3. auto-promote 경유 커버 — 핵심 주장 독립 확인

`auto_promote_candidate`(`service.py:196-205`)는 threshold gate 통과 시 `self.promote_candidate(..., mode=AUTO_THRESHOLD)`를 호출한다. 즉 auto-promote는 독립 mint가 아니라 choke point(promote_candidate)를 경유한다. 작업자의 “2 choke point가 3 경로를 커버” 주장이 1차 소스로 정확함. below-threshold는 `return None`(mint 없음)이라 enqueue도 없다(행4로 잠김).

### 4. apply-seam 흡수·제거 확인

`apply.py` diff: 증분 1의 `MemoryReindexOutbox` Protocol·`reindex_outbox` param·`_enqueue_reindex`·`apply_proposals`의 post-loop enqueue가 **전부 제거**됐다. `MemoryApplyService.__init__(self, *, memory_service)`로 환원, `apply_proposals`는 단순 `tuple(self._apply_one(...))` 반환. 주석도 “Reindex enqueue is owned by MemoryService (2B.5 D3=B choke point)”로 갱신. create→promote_candidate, update/add_evidence→record_*_version이 MemoryService에서 enqueue하므로 apply의 별도 hook이 불필요 — 주장대로. `grep enqueue_memory_upserted` 결과 참조 지점이 `memory/service.py`(choke), `indexing/service.py`(정의), main.py(wiring), 테스트에만 존재하고 apply.py엔 없음.

### 5. choke-point non-vacuity 변이(mutant) — 작업 주장보다 강하게 재실증

`MemoryService._enqueue_reindex`를 no-op로 무력화하고 3개 테스트 모듈(42 test)을 돌렸더니 **10개 재실패**(9 fail + 1 error). 재실패 목록: `test_manual_promote_enqueues_reindex`·`test_manual_promote_replay_does_not_double_enqueue`·`test_auto_promote_enqueues_when_threshold_fires`·`test_create_enqueues_reindex`·`test_create_indexes_canonical_record`·`test_enqueue_dedups_same_memory`·`test_events_accumulate_as_separate_records`·`test_reindex_is_idempotent`·`test_update_replaces_prior_version_vector`·`test_apply_create_enqueues_memory_upserted`. work log는 “4개 재실패”라고 했으나 **실제는 10개** — choke point가 work 주장보다 더 load-bearing임(non-vacuity 확정, 주장은 보수적).

### 6. 실 Chroma adapter + worker drain + backfill + create_app wiring

- **`ChromaMemoryVectorIndexAdapter`**(`indexing/chroma.py`): upsert(빈 short-circuit)/list(project scope, id 정렬)/delete `where={"$and":[{project_id},{memory_id}]}` — **delete가 project-scoped**라 교차-프로젝트 id 충돌 차단(행: `test_delete_is_project_scoped`·`test_delete_removes_only_target_in_project`). `memory_record_to_chroma`의 chroma id == `record.memory_id`(2B.4 append-only), metadata round-trip(`test_round_trip_preserves_fields`·`test_chroma_id_is_memory_id`). `_memory_records_from_get`는 None ids/embeddings/metadatas 처리(v1.6.35/37 numpy-like 패턴 일관). 11 회귀.
- **worker `_build_memory_adapter`**(`scripts/index_sync_worker.py`): Mongo-backed `MemoryService`(`MongoMemoryRepository.from_uri`) + embedding(`EMBEDDING_SERVICE_URL`/fake) + Chroma(`CHROMA_HOST`)/fake memory collection. summary에 `memory_backend`. env 분기 양방향 회귀(`test_without_chroma_host_uses_in_memory_fake`·`test_with_chroma_host_builds_chroma_memory_adapter`). **worker 측 MemoryService는 reindex_outbox 미주입**(drain 전용, 쓰기 아님) — write/drain 분리 정확.
- **backfill**(`scripts/phase2b5_reindex_memory.py`): `canonical = [m for m in memories if m.status is MemoryStatus.CANONICAL]`로 **superseded 제외**, outbox 우회 직접 embed+upsert(D7), summary(`canonical_count`/`records_written`/`memory_backend`), exit 0(성공)/2(ValueError·config). 4 회귀.
- **create_app wiring**(`main.py`): `sync_outbox = index_sync_outbox or _default_index_sync_outbox_service()` 후 `memory = memory_service or _default_memory_service(reindex_outbox=sync_outbox)` — in-memory/Mongo 양 경로 모두 outbox 주입. 주입 `memory_service`(테스트)는 자체 wiring 유지. HTTP E2E 회귀 `test_apply_create_enqueues_memory_upserted`가 `create_app(index_sync_outbox=...)` → apply → outbox entry `MEMORY_UPSERTED`를 단정(factory 경로 관통).
- **순환 회피**: `MemoryReindexOutbox`가 `memory/service.py`에 **로컬 Protocol**로 정의(구조적 타입, indexing 미import). indexing→memory 의존은 기존 방향 유지, memory→indexing 역방향 없음. `py_compile` + suite green으로 순환 없음 확인.

### 7. 문서 정합

- SoT v1.6.46(version-table + §Phase 2B prose)이 구현(choke point·실 Chroma·배선·backfill·회귀 수)과 정합.
- v1.6.45 행이 closure(dispatch 회귀·본인 증분1 검증 인용)로 갱신됨.
- HANDOFF·CHANGELOG·work log(2026-07-07)·브리프(Owner decision 반영) 갱신. CHANGELOG 최상단 행 링크 정확.

## Issues / Risks

- **[비차단, 설계 수용] mint 후 enqueue 실패 시 skew + replay 미재시도**: `promote_candidate`/`_versioned_upsert`가 `put_memory`(Mongo commit) **후** `_enqueue_reindex`(outbox put)를 호출한다. outbox put이 실패하면 canonical은 Mongo에 커밋됐지만 reindex entry 없음 → unindexed. 재시도 시 promote는 replay 분기로 빠져 **enqueue를 재시도하지 않는다**(`find_memory_by_candidate` 기존 → early return, `_enqueue_reindex` 미도달). 이는 D3=B(skew 무관용)의 본질적 skew 표면이며, **D7 backfill이 유일한 수렴 수단**. 증분 1 apply-seam과 동일 속성(회귀 없음도 동일). 확률은 낮지만(memory/outbox 동일 Mongo), backfill이 보증하지 않는 한 영구 orphan 가능 — 운영 시 정기 backfill 권고. 본 slice 결함이 아니라 채택된 async 설계의 수용 경계.
- **[비차단, 보고 정정] non-vacuity 변이 보고 과소**: work log/commit이 “disabling choke-point enqueue re-fails 4 tests”라고 했으나 독립 변이 시 **10개 재실패**. 방향은 맞(choke point load-bearing)지만 수치가 보수적. 비차단.
- **[비차단] backfill exit code 단순**: exit 0(성공)/2(ValueError)만 있고 source_block rebuild 스크립트(v1.6.22)의 partial-write exit 1이 없다. 단, backfill은 단일 `collection.upsert` 배치(원자)라 partial 개념이 약해 수용 가능. 색인 실패 시 미포착 예외 → traceback + 비-0 종료(운영자 가시). live 후속에서 exit 표면 다듬 권고.
- **[범위 밖, 정상] 실 Chroma/Mongo 관통 live**: backfill/live smoke 스크립트는 `--help`/usage-error 확인 단계이고 실 관통 실행은 sandbox 밖 후속. 본 slice 계약/단위 검증 범위 안.

## Verdict

**합격(pass).**

이유:
- 증분 1 조건부 합격 조건(dispatch 미추적 분기)이 67b5362에서 폐쇄됨(빈 셀 해소).
- choke-point 중앙화: canonical-mint 지점 정확히 2곳(grep 전수 확인), 우회 없음, auto-promote는 promote 경유 커버, 모든 “should fire/should NOT fire” 분기가 회귀로 잠김(빈 셀 없음).
- apply-seam 흡수·제거가 1차 소스로 확인, 순환 회피(로컬 Protocol) 정상.
- choke-point non-vacuity: 변이 무력화 시 10개 재실패(work 주장 4보다 강하게)로 load-bearing 확정.
- 실 Chroma adapter delete project-scoped `$and`·round-trip·worker drain·backfill superseded 제외·create_app E2E wiring 전부 회귀로 잠김.
- 전체 스위트 **598 passed / 45 skipped** 독립 재실행 재현. `py_compile` OK, working tree clean, 두 커밋 main 반영(HEAD `a8b1d9b`).

차단 조건 없음. 잔여는 전부 비차단(설계 수용 skew·보고 과소·backfill exit 단순·sandbox 밖 live).

## Outstanding items

- **[비차단 권고] 정기 backfill 운영화**: mint 후 enqueue 실패 skew의 유일 수렴 수단이 D7 backfill이므로, 운영 배포 시 정기 backfill(또는 backfill HTTP 트리거 후속) 권고.
- **[sandbox 밖, 후속]** 실 Chroma/Mongo 관통 live smoke 실행(promote→outbox→worker→실제 `memory_vectors` record 확인) — 스크립트는 완료.
- **[다음 slice, 별도 브리프]** 2B.5 읽기 경로 — `PriorMemoryBackend`를 vector semantic 검색으로 교체해 event/open_question 의미 대조 켜기(2B.5가 채운 index 소비). 착수 브리프 필요.
- **[오너 확인 대상 누적]** event/open_question identity 대조 제외(항상 create→벡터 누적)가 브리프 의도와 맞는지(증분 1에서 이월, 동일).

## Reproduction

```bash
cd "/mnt/d/devel/에베베/ai_writte_system"

# (1) 위생 + 컴파일
git status --porcelain && git log --oneline -1   # clean / a8b1d9b
python3 -m py_compile services/application/app/memory/service.py \
  services/application/app/indexing/chroma.py services/application/app/main.py \
  services/application/app/analysis/apply.py scripts/index_sync_worker.py \
  scripts/phase2b5_reindex_memory.py scripts/phase2b5_memory_reindex_live_smoke.py

# (2) 증분1 closure 회귀 + 전체 스위트(mongo env 제외)
python3 -m unittest tests.test_memory_vector_index tests.test_chroma_memory_adapter \
  tests.test_phase2b5_reindex_memory_script -v
python3 -m pytest -q --ignore=tests/test_memory_mongo.py   # 기대: 598 passed / 45 skipped

# (3) choke-point non-vacuity 변이(10 재실패 기대)
PYTHONPATH=. python3 - <<'PY'
import unittest
from services.application.app.memory.service import MemoryService
MemoryService._enqueue_reindex = lambda self, m: None
s = unittest.TestSuite()
for mod in ["tests.test_memory_vector_index","tests.test_memory_apply","tests.test_analysis_apply_api"]:
    s.addTests(unittest.TestLoader().loadTestsFromName(mod))
r = unittest.TextTestRunner(verbosity=0).run(s)
print(r.testsRun, len(r.failures), len(r.errors))   # 42 9 1
PY
```
