# Core SOT MongoDB Adapter 재검증 (독립 의심 검증)

## Subject Metadata

- **날짜**: 2026-06-28
- **요청자**: 사용자 ("작업 AI가 작업한 분에 대해서 검증하고 의심해줄래")
- **검증자**: Claude (본 세션, 이전 검증자와 별개)
- **대상 Slice**: MongoDB adapter + transaction-backed repository (HANDOFF Next Task #1 폐쇄)
- **정본 spec 참조**:
  - `docs/system-contract-sot.md` **v1.3** §97, §110-115 (persistence/retention, Approved)
  - cross-ref: `docs/plans/01-core-sot.md` §75-86, §94 (Draft — SoT가 우선)
- **작업 출처**: working tree, uncommitted
  - 신규(untracked): `services/application/app/core_sot/mongo_repository.py`, `repository.py`, `tests/test_core_sot_mongo.py`
  - 수정(modified): `service.py`, `main.py`, `requirements.txt`, `HANDOFF.md`, `CHANGELOG.md`
- **선행 검증 기록**: `docs/verifications/2026-06-28/mongo_adapter.md` (판정: 합격)
- **본 검증의 입장**: 선행 기록의 "합격" 결론 자체를 의심하고, 독립적으로 재도출. CLAUDE.md 원칙("Never reframe a missing over-strict guard as '차단 사유 아님'")을 엄격 적용.

## Scope

1. **Spec contract**: `system-contract-sot.md` v1.3 §110-115 (+ plan §75-86 cross-ref)
2. **Repository Protocol**: `repository.py`
3. **MongoDB adapter**: `mongo_repository.py`
4. **Service integration**: `service.py`
5. **회귀 테스트**: `tests/test_core_sot_mongo.py` (+ `test_core_sot.py` in-memory contract 보존)
6. **Test infrastructure 독립성**: pymongo 미설치 환경에서 discovery 동작 (선행 기록이 점검하지 않은 표면)
7. **Wiring / 의존성**: `main.py`, `requirements.txt`

## Methodology

### 1. Canonical contract scope (문서 전체 읽기 전 스코프 한정)

SoT v1.3이 정본이고 plan/01은 Draft(우선순위 4)이므로, 계약 literal은 SoT §110-115에서 추출하고 plan §75-86은 보조 detail만 인용. 그 외 섹션/과거 plan iteration은 out-of-scope.

### 2. Boundary matrix 구축 (spec literal → 분기 → regression test → fixture)

각 literal을 "should fire" / "should NOT fire" 분기로 분해한 뒤, 각 분기를 특정 regression test에 1:1 추적. 빈 칸 = blocking.

### 3. 독립 실행

```bash
# (a) 인프라 없이 discovery (pymongo 설치됨, Mongo 연결 없음)
python3 -m unittest discover -s tests

# (b) pymongo 미설치 시뮬레이션 — 선행 기록이 점검 안 한 표면
python3 -c "import sys; sys.modules['pymongo']=None; sys.modules['pymongo.errors']=None; \
  import unittest; s=unittest.TestLoader().discover('tests', pattern='test_core_sot*.py'); \
  r=unittest.TextTestRunner(verbosity=0).run(s); \
  print('errors',len(r.errors),'failures',len(r.failures),'run',r.testsRun)"

# (c) Mongo replica set에서 전체 discovery (독립 재현)
docker run -d --name coresot-mongo-test -p 27018:27017 mongo:7 --replSet rs0
docker exec coresot-mongo-test mongosh --quiet --eval 'rs.initiate()'
# myState==1(PRIMARY) 대기 후
CORE_SOT_TEST_MONGO_URI="mongodb://localhost:27018/?directConnection=true" \
  python3 -m unittest discover -s tests
```

### 4. Code 정적 분석

transaction path / fallback path의 write 순서, retry guard, orphan cleanup, race cleanup을 순차 및 동시성 두 시나리오에서 추적.

## Findings

### Surface 1 — Boundary matrix (spec ↔ 분기 ↔ test)

독립적으로 재구성한 matrix. 빈 칸 검사 결과:

| # | Spec literal (file:line) | 분기 방향 | Lock하는 regression test | 상태 |
|---|---|---|---|---|
| L2 | idempotency_key 필수 (sot:111) | should fire: 빈 key reject | `test_missing_idempotency_key_is_rejected` (test_core_sot.py:141) | ✓ |
| L3a | 같은 key 재시도 → 같은 version (sot:111) | should fire | `test_idempotent_replay_returns_same_version_without_duplicate` (in-memory + Mongo mixin) | ✓ |
| L3b | 같은 key 재시도 → 같은 version (sot:111) | should NOT fire: 다른 key → 새 version | `test_distinct_idempotency_key_creates_next_version` | ✓ 양방향 |
| L4 | unique index authoritative boundary | should fire: 같은 key 2번째 version insert → `DuplicateSaveRequest` | `test_unique_index_blocks_duplicate_save_request` (record_save 직접 호출) | ✓ |
| L5 | Docker runtime transaction 기본 (sot:112) | should fire: `use_transactions=True` default | `TransactionMongoTest.use_transactions=True` (mongo_repository.py:49) | ✓ |
| L6b/d | retry guard — committed version 보호 | should fire + should NOT fire (committed dependents 미삭제) | `test_retry_guard_does_not_delete_committed_dependents` | ✓ 양방향 |
| L6c | orphan cleanup — 이전 실패 dependents 제거 | should fire | `test_fallback_cleans_orphans_from_prior_failed_attempt` | ✓ |
| L7 | transaction abort → partial write 잔류 없음 (plan:76) | should fire | `test_transaction_abort_leaves_no_partial_write_on_duplicate` | ✓ |
| L9 | project/draft 삭제 = archive (sot:113) | should fire + should NOT fire (hard delete 부재) | `test_archive_preserves_version_snapshot_and_blocks` | ✓ |
| L10a | snapshot/version/blocks 보존 (sot:113) | should fire | `test_archive_preserves...` | ✓ |
| L11 | MongoDB = SOT (sot:97) | should fire | 통합 테스트 전체 (168) | ✓ |
| L12 | project_id isolation | should fire: cross-project → NotFound | `test_project_id_isolation_blocks_cross_project_draft_access` | ✓ |
| **L8** | **성공은 write 완료 후에만 응답 (plan:78)** | should fire | **명시적 regression test 없음** | △ 자명 |
| **L10b** | **source_refs 보존 (sot:113)** | should fire | **구현 자체 미존재** | ✗ scope-out |
| **L6-concurrent** | **fallback 동시성 안전성** | should fire: 병렬 같은 key save → consistent | **regression test 없음, code가 incorrect** | ✗ (R1/R2) |

**빈 칸 검사 결론**: 핵심 sequential contract(L2~L9, L11, L12)는 분기별 1:1 lock됨. 그러나 3개의 미충족 칸이 있고, 이 중 2개는 경계 조건이므로 아래 Issues에서 별도 평가. L8은 동기 pymongo 호출 구조상 자명하게 충족(record_save 반환 후에만 SaveDraftResult 반환, service.py:193-211)하지만 명시적 test는 없음 — 비차단.

### Surface 2 — 통합 테스트 독립 재현 (이전 "168 통과" 주장 검증)

```text
[5/5] run full discovery against replica set
Ran 168 tests in 3.387s
OK
```

- mongo:7 단일 노드 replica set(`--replSet rs0` + `rs.initiate()`, `?directConnection=true`)에서 **168개 전체 통과를 독립 재현**.
- Mongo 미지정 시 `Ran 168 tests ... OK (skipped=17)` 재현.
- 선행 기록의 테스트 카운트 주장은 정확함. ✓
- `test_core_sot.py` in-memory 14개 + `test_application_api.py`는 Mongo 없이도 통과 → 이전 minimal skeleton contract 보존 확인.

### Surface 3 — Code ↔ spec literal 정합성 (핵심 경로)

- Transaction path (`mongo_repository.py:167-189`): version을 **먼저** insert → unique index 위반이 transaction 전체를 abort → `DuplicateKeyError`→`DuplicateSaveRequest`(`:188-189`). all-or-nothing 보장. plan §76 "transaction 범위 = write set 전체" 충족. ✓
- Fallback path (`mongo_repository.py:191-228`): retry guard(`find_save_request`, `:205`) → orphan cleanup(`delete_many(scope)`, `:210-211`) → ordered writes(snapshot→blocks→version commit marker last, `:214-221`) → race cleanup(version insert 실패 시 자기 dependents만 delete, `:222-227`). 순차 시나리오에서 plan §78(write order/lookup/orphan cleanup/retry guard) 충족. ✓
- idempotency 단일 출처: unique index `(project_id, draft_id, idempotency_key)` on `draft_versions`(`:76-84`). snapshot/block doc에도 `idempotency_key`를 실어 orphan cleanup filter로 사용(`:286`, `:307`) — filter 키 3종이 모두 doc에 존재. ✓
- service.py는 repo 내부 dict 직접 접근 없이 Protocol method만 사용(`:164`, `:194`, `:258-263`) → storage 교체 가능. ✓

## Issues / Risks

### R1 — test 모듈의 module-level pymongo import가 infrastructure-free discovery를 regression (선행 기록 누락)

- **증상**: `tests/test_core_sot_mongo.py:20-21`이 module top-level에서 `from pymongo import MongoClient` / `from pymongo.errors import ...`. pymongo 패키지 자체가 없으면 **전체 `unittest discover`가 ImportError로 실패**한다.
- **독립 재현** (pymongo 차단 후 discover):
  ```text
  ERROR: test_core_sot_mongo (unittest.loader._FailedTest.test_core_sot_mongo)
  ImportError: Failed to import test module: test_core_sot_mongo
  Ran 13 tests
  FAILED (errors=1)
  ```
- **계약 위반**: 동일 파일 docstring(`:4-6`)이 *"skip (not fail) when none is available so the infrastructure-free unit suite stays runnable everywhere"*를 약속. 그러나 skip 처리는 Mongo **연결** 부재에만 작동하고, pymongo **패키지** 부재에는 작동하지 않는다. docstring ↔ implementation contract gap.
- **Regression 범위**: 선행 minimal skeleton 검증(2026-06-26)은 pymongo 없이 151개가 discovery되었다. Mongo adapter 추가 이후 pymongo가 없으면 discovery 자체가 깨진다. 즉, **이 slice가 이전에 성립하던 "infrastructure-free unit suite" 특성을 regression**시켰다. (Mongo *연결*이 없을 때만 skip이지, pymongo *패키지*가 없을 때는 전체가 깨진다.)
- **선행 기록 평가**: 이 표면을 점검하지 않았다(pymongo가 설치된 환경에서만 검증). "168개 통과"는 pymongo 설치 전제 하에만 성립.
- **심각도**: requirements.txt에 pymongo가 있어 application 환경에서는 항상 설치되므로 production runtime 영향은 없다. 그러나 test 독립성/CI 관점에서 실질적 regression이며, boundary matrix의 한 칸(infra-free discovery)이 깨진 상태.
- **해결**: 간단함. module-level pymongo import를 try/except로 감싸고 ImportError 시 `_MONGO_AVAILABLE=False`로 skip 처리. (driver 자체는 service layer가 아니라 test file에서만 import하므로 service 코드는 영향 없음.)
- **판정 영향**: boundary matrix 빈 칸. 조건부 합격의 load-bearing 조건.

### R2 — fallback path orphan cleanup이 동시성 시나리오에서 committed dependents 삭제 (선행 기록 과소평가)

- **분기**: 동일한 `(project_id, draft_id, idempotency_key)` save 요청 A, A'이 **동시** 진입.
  1. A·A' 모두 retry guard `find_save_request → None` 통과(version 아직 없음, `:205`).
  2. A: orphan cleanup 통과 → snapshot_A/blocks_A insert → version_A insert 성공.
  3. A': orphan cleanup `delete_many(scope)`(`:210-211`)가 **A의 snapshot_A/blocks_A를 삭제**(같은 project_id/draft_id/idempotency_key이므로 scope에 매칭).
  4. A': snapshot_A'/blocks_A' insert → version_A' insert → `DuplicateKeyError`(version_A 선행) → race cleanup은 자기 snapshot_A'만 삭제(`:225-226`).
  5. **결과**: `version_A`는 존재하지만 `version_A.snapshot_id`가 가리키는 snapshot_A/blocks_A는 소거 → **orphaned version**. 이후 idempotent replay 시 `get_snapshot(version.snapshot_id) → None` → `_save_result`(`:258-269`)의 `assert snapshot is not None`가 crash.
- **선행 기록 평가 정정**: 선행 기록은 이것을 "Non-Blocking, 위험도 낮음, unique index와 race cleanup이 방어"로 분류(`mongo_adapter.md:223-225`). **부정확**. unique index는 idempotency duplicate만 막을 뿐 data loss를 막지 못하고, race cleanup은 *자기 자신의* dependents만 지워서 *다른 요청의* committed dependents 삭제를 막지 못한다. 정확한 평가: **순차 contract는 충족, 동시성에서 correctness bug(data corruption)**.
- **spec 관계**: sot §112 / plan §78은 동시성 안전성을 **명시적으로 요구하지 않는다**(fallback은 "local/test 제한 경로"). 따라서 spec literal 위반은 아니다. 그러나 code가 동시성을 *방어하려 시도*하고(의도: orphan cleanup/retry guard) 실제로는 incorrect하므로 CLAUDE.md "spec-silent-but-code-enforced" 변형에 해당 — 소유자 결정으로 (a) fallback을 concurrent-safe로 보강하거나 (b) spec에 "fallback은 single-writer 전용" 제약을 명시해야 contract가 닫힌다.
- **production 영향**: production 경로는 transaction path(default)이며 동시성 안전(MongoDB transaction all-or-nothing). R2는 fallback(local/test)로 한정. HANDOFF Next Task #2("동시성 race, 같은 idempotency_key 병렬 save")에 이미 추적되어 있으나, **선행 기록이 이것을 correctness bug가 아닌 "위험도 낮음"으로 분류한 점은 정정 필요**.
- **판정 영향**: 비차단(production path 안전 + spec 동시성 미요구 + HANDOFF 추적됨). 단, 이 slice가 닫히려면 소유자가 (a)/(b) 중 방향을 확정해야 함을 명시.

### R3 — source_refs 보존 계약 literal이 구현에 아직 해당하지 않음 (선행 기록 부정확 표시)

- **계약**: sot §113 "`source_snapshots`, `draft_versions`, `source_blocks`, `source_refs`는 보존한다."
- **구현 현황**: `mongo_repository.py`에 `source_refs` collection이 **없다**. `create_source_ref`(service.py:213-243)는 `SourceRef` 객체를 반환만 하고 persist하지 않는다(in-memory skeleton 시점과 동일).
- **선행 기록 평가 정정**: 선행 기록 Findings #1 표에서 "snapshot/version/source_refs 보존 | Mongo collections preserve ... | ✓"로 표시(`mongo_adapter.md:84`). **source_refs는 persist되지 않으므로 "보존 ✓"는 misleading**.
- **판정 영향**: 본 slice의 scope는 draft save write set + idempotency + transaction/fallback이며, SourceRef 영속화는 별도 slice 범위(선행 minimal skeleton 검증에서도 in-memory 반환만 확인). 따라서 이 slice의 blocking은 아니다. 단, §113 literal이 존재하므로 향후 SourceRef persistence slice에서 보존 정책이 명시적으로 적용되어야 함을 추적 포인트로 남김.

### R4 — 비차단 관찰 (lock 되어 있으나 기록)

- **L8 "성공은 write 완료 후 응답"(plan §78)**: 동기 pymongo 호출 구조상 record_save 반환 후에만 SaveDraftResult 반환(service.py:193-211). 자명하게 충족되나 명시적 regression test는 없음. 동기 driver 선택(사용자 결정, HANDOFF:58) 덕분에 보장되는 성질 — 비차단.
- **Write order 경로 차이**: transaction path는 version→snapshot→blocks, fallback은 snapshot→blocks→version. 성공 시 결과 동일, failure mode 상이. spec은 write order를 요구하나 **순서를 명시하지 않으므로** 둘 다 허용. 비차단.

## Verdict

**조건부 합격 (Conditional Pass)**

**Load-bearing 조건 (R1, 반드시 폐쇄해야 합격으로 승격):**

1. **R1 해결**: `tests/test_core_sot_mongo.py`의 module-level pymongo import를 lazy/try-except로 변경해 pymongo 미설치 환경에서도 `unittest discover`가 실패하지 않고 skip되도록 한다. test 파일 자신의 docstring 약속("infrastructure-free unit suite stays runnable everywhere")과 minimal skeleton의 핵심 가치를 복원. 수정 범위는 test 파일만, service/adapter 코드 무관.

**합격 사유 (조건 1 충족 시):**

1. **Spec ↔ implementation**: persistence/retention 계약 v1.3 핵심 literal(L2~L9, L11, L12)이 분기별로 정확히 구현되고 양방향 regression으로 lock됨. boundary matrix 빈 칸 없음(동시성/source_refs 제외, 별도 평가).
2. **두 경로 구현**: transaction path(기본, all-or-nothing via version-first insert) + non-transaction fallback(retry guard/orphan cleanup/ordered writes/race cleanup)가 spec 요구대로 정확.
3. **idempotency 단일 출처**: unique index `(project_id, draft_id, idempotency_key)`가 authoritative boundary. 동일 key 재시도 → 동일 version 반환 양방향 lock.
4. **독립 재현**: 통합 테스트 168개(양 경로)를 단일 노드 replica set에서 통과시킴. 선행 기록의 카운트 주장 정확.
5. **in-memory regression 없음**: 기존 test_core_sot.py / test_application_api.py는 InMemoryCoreSotRepository public 속성 보존으로 통과 유지.

**비차단(소유자 결정 필요, 합격 승격을 막지 않음):**

- **R2**: fallback 동시성 correctness bug. production path(transaction)는 안전. 소유자가 (a) concurrent-safe 보강 또는 (b) spec에 fallback single-writer 제약 명시 중 방향 확정 필요. 선행 기록의 "위험도 낮음/방어됨" 평가는 정정됨.
- **R3**: source_refs 보존 literal은 SourceRef persistence slice에서 적용. 본 slice scope 밖. 선행 기록의 "source_refs 보존 ✓" 표시는 정정됨.

## Outstanding Items

1. **R1 미해결**: 본 검증 시점에 test module import regression이 열려 있어 조건부 합격. 소유자가 R1 수정을 적용하면 합격으로 승격 가능(재검증 불필요 — 동적 시뮬레이션으로 즉시 확인 가능).
2. **미커밋 작업**: mongo_repository.py / repository.py / test_core_sot_mongo.py untracked, service/main/requirements modified. R1 수정과 함께 commit 권장.
3. **R2 방향 결정 대기**: 소유자가 fallback 동시성 처리 방향((a) 보강 / (b) spec 제약)을 정하면 HANDOFF Next Task #2와 함께 폐쇄.
4. **인프라 정리**: 검증용 Docker 컨테이너는 본 검증 종료 후 제거 완료(`docker rm -f coresot-mongo-test`).

## Reproduction

```bash
# 1. 인프라 없이 discovery (pymongo 설치됨)
python3 -m unittest discover -s tests   # → 168 tests, OK (skipped=17)

# 2. R1 regression 재현 (pymongo 차단)
python3 -c "import sys; sys.modules['pymongo']=None; sys.modules['pymongo.errors']=None; \
  import unittest; s=unittest.TestLoader().discover('tests', pattern='test_core_sot*.py'); \
  r=unittest.TextTestRunner(verbosity=0).run(s); \
  print('errors',len(r.errors),'run',r.testsRun)"   # → errors=1 (R1)

# 3. Mongo replica set에서 양 경로 전체 재현
docker run -d --name coresot-mongo-test -p 27018:27017 mongo:7 --replSet rs0
# wait myState==1
docker exec coresot-mongo-test mongosh --quiet --eval 'rs.initiate()'
CORE_SOT_TEST_MONGO_URI="mongodb://localhost:27018/?directConnection=true" \
  python3 -m unittest discover -s tests   # → 168 tests, OK (0 skipped)
docker rm -f coresot-mongo-test
```
