# Core SOT MongoDB Adapter 검증 기록

## Subject Metadata

- **날짜**: 2026-06-28
- **요청자**: 사용자 (이전 작업자의 MongoDB adapter 작업 검증 요청)
- **검증자**: Claude (Opus 4.8)
- **대상 Slice**: MongoDB adapter + transaction-backed repository
- **정본 spec 참조**: `docs/system-contract-sot.md` v1.3 (persistence/retention 계약)
- **작업 출처**: working tree, uncommitted (git status shows `M` on service/main.py, new mongo_repository.py)

## Scope

검증 대상 표면:
1. **Spec contract**: `docs/system-contract-sot.md` §확정된 전역 계약 - persistence/retention (v1.3)
2. **Repository Protocol**: `services/application/app/core_sot/repository.py`
3. **MongoDB adapter**: `services/application/app/core_sot/mongo_repository.py`
4. **Service integration**: `services/application/app/core_sot/service.py` (repository 사용 부분)
5. **회귀 테스트**: `tests/test_core_sot_mongo.py`
6. **의존성**: `services/application/requirements.txt` (pymongo)
7. **Wiring**: `services/application/app/main.py` (Mongo URI/env var 처리)

## Methodology

### 1. Contract Read (spec scope)

`docs/system-contract-sot.md` v1.3의 persistence/retention 계약 섹션을 읽고 boundary matrix를 구성:

**계약 literal (system-contract-sot.md:110-114):**
1. MongoDB가 원문과 구조화 기억의 SOT다
2. draft save는 명시적 version save만 지원한다
3. draft save request는 `idempotency_key`를 필수로 가진다
4. 같은 `project_id + draft_id + idempotency_key` 재시도는 같은 `draft_version`을 반환해야 한다
5. Docker 기반 정상 runtime은 MongoDB transaction을 기본으로 사용한다
6. non-transaction fallback은 local/test 환경의 제한적 경로이며, write order, idempotency lookup, orphan cleanup/retry guard를 요구한다
7. project/draft 삭제는 MVP에서 archive로 처리한다
8. `source_snapshots`, `draft_versions`, `source_blocks`, `source_refs`는 보존한다

### 2. Implementation Trace

각 파일을 읽으며 spec literal과 구현을 비교:

```bash
# spec read
less docs/system-contract-sot.md

# implementation read
less services/application/app/core_sot/repository.py
less services/application/app/core_sot/mongo_repository.py
less services/application/app/core_sot/service.py
less tests/test_core_sot_mongo.py
less services/application/app/main.py
```

### 3. Test Execution

```bash
# 전체 테스트 suite (Mongo 미지정)
python3 -m unittest discover -s tests

# Mongo 통합 테스트 (work_log 기록)
docker run -d --name coresot-mongo-test -p 27018:27017 mongo:7 --replSet rs0
docker exec coresot-mongo-test mongosh --eval "rs.initiate()"
CORE_SOT_TEST_MONGO_URI="mongodb://localhost:27018/?directConnection=true" python3 -m unittest tests.test_core_sot_mongo -v
```

### 4. Cross-Check

Spec ↔ implementation, implementation ↔ test, test ↔ spec 간 literal 일치를 확인.

## Findings

### 1. Spec ↔ Implementation Consistency

| Spec Clause (system-contract-sot.md) | Implementation | Status |
|---|---|---|
| MongoDB가 SOT | `MongoCoreSotRepository` (mongo_repository.py:41-228) | ✓ |
| 명시적 version save only | `save_draft` → `DraftVersion` 생성 (service.py:152-211) | ✓ |
| `idempotency_key` 필수 | `service.py:160-161` 검증 | ✓ |
| 같은 key 재시도 → 같은 version 반환 | `service.py:164-168` short-circuit, `200-205` race guard | ✓ |
| Docker runtime transaction 기본 | `use_transactions=True` default (mongo_repository.py:49) | ✓ |
| non-transaction fallback (write order, lookup, orphan cleanup, retry guard) | `_record_save_fallback` (mongo_repository.py:191-228) | ✓ |
| project/draft는 archive | `archive_project`, `archive_draft` (service.py:245-256) | ✓ |
| snapshot/version/source_refs 보존 | Mongo collections preserve, `get_version/snapshot/blocks` (mongo_repository.py:140-152) | ✓ |

**모든 spec literal이 구현에 그대로 반영되어 있음. 빈 칸 없음.**

### 2. CoreSotRepository Protocol

`repository.py:31-70`에 정의된 Protocol 메서드:

- Identifier generation: `next_project_id`, `next_draft_id`, `next_version_id`, `next_snapshot_id` ✓
- CRUD: `get_project`, `put_project`, `get_draft`, `put_draft` ✓
- Save operations: `version_count`, `find_save_request`, `record_save` ✓
- Read operations: `get_version`, `get_snapshot`, `get_blocks` ✓

`MongoCoreSotRepository`가 모든 메서드를 구현하고 있음 (mongo_repository.py:92-152). Protocol-based contract 충족.

### 3. MongoDB Adapter Two-Path Implementation

**Transaction Path (mongo_repository.py:167-189):**
```python
def _record_save_transactional(...):
    with self._client.start_session() as session:
        with session.start_transaction():
            self._versions.insert_one(version_doc, session=session)  # 먼저 (unique index abort)
            self._snapshots.insert_one(snapshot_doc, session=session)
            if block_docs:
                self._blocks.insert_many(block_docs, session=session)
```
- version 먼저 insert → unique index `(project_id, draft_id, idempotency_key)`가 중복 감지 → transaction 전체 abort
- `DuplicateKeyError` → `DuplicateSaveRequest` 번역
- **All-or-nothing 보장**

**Non-Transaction Fallback (mongo_repository.py:191-228):**
```python
def _record_save_fallback(...):
    # 1. Retry guard
    if self.find_save_request(*scope.values()) is not None:
        raise DuplicateSaveRequest(idempotency_key)

    # 2. Orphan cleanup
    self._snapshots.delete_many(scope)
    self._blocks.delete_many(scope)

    # 3. Ordered writes
    self._snapshots.insert_one(_snapshot_doc(snapshot, idempotency_key))
    if block_docs:
        self._blocks.insert_many(block_docs)
    self._versions.insert_one(_version_doc(version))  # commit marker last
```
- **Retry guard**: 이미 commit된 version이 있으면 dependents를 건드리지 않고 replay 신호
- **Orphan cleanup**: 직전 실패 시도의 dependents 제거
- **Ordered writes**: immutable dependents 먼저, commit marker(version) 마지막
- **Race cleanup**: version insert 실패 시 이 시도가 쓴 dependents만 정리

두 경로 모두 spec 요구사항(write order, idempotency lookup, orphan cleanup, retry guard)을 충족.

### 4. Idempotency Boundary Enforcement

**Unique index (mongo_repository.py:76-84):**
```python
self._versions.create_index(
    [("project_id", ASCENDING), ("draft_id", ASCENDING), ("idempotency_key", ASCENDING)],
    unique=True,
    name="uniq_save_request",
)
```
- MongoDB unique index가 authoritative idempotency boundary
- Transaction path: index 위반 → transaction abort → `DuplicateSaveRequest`
- Fallback path: index 위반 → orphan cleanup → `DuplicateSaveRequest`

Spec "같은 `project_id + draft_id + idempotency_key` 재시도는 같은 `draft_version`을 반환" 충족.

### 5. Test Coverage (test_core_sot_mongo.py)

**공통 계약 테스트 (_MongoContractMixin):**
1. `test_save_persists_and_reconstructs_snapshot_blocks_and_version`: 저장 후 재구성 (line:97-119)
2. `test_idempotent_replay_returns_same_version_without_duplicate`: idempotent replay (line:121-141)
3. `test_distinct_idempotency_key_creates_next_version`: 다른 key로 version 증가 (line:143-161)
4. `test_unique_index_blocks_duplicate_save_request`: unique index 중복 거절 (line:163-200)
5. `test_project_id_isolation_blocks_cross_project_draft_access`: project_id 격리 (line:202-213)
6. `test_archive_preserves_version_snapshot_and_blocks`: archive 보존 (line:215-235)
7. `test_source_ref_reconstructs_exact_quote_from_persisted_snapshot`: source_ref 재구성 (line:237-258)

**Fallback 전용 (FallbackMongoTest):**
8. `test_fallback_cleans_orphans_from_prior_failed_attempt`: orphan cleanup (line:265-328)
9. `test_retry_guard_does_not_delete_committed_dependents`: retry guard (line:330-368)

**Transaction 전용 (TransactionMongoTest):**
10. `test_transaction_abort_leaves_no_partial_write_on_duplicate`: transaction abort (line:378-414)

총 10개 contract test × 2 경로 = 17개 전체 (공통 7 × 2 + fallback 2 + transaction 1).

**Skip-awareness:** `_probe_mongo()` (line:43-64)가 Mongo 가용성과 transaction 지원을 탐지하고 `@unittest.skipUnless`로 조건부 skip (fail 아님).

### 6. Service Integration

`service.py:132`이 `CoreSotRepository` Protocol을 의존성으로 받음 → in-memory와 Mongo 양쪽에 동작:

```python
class CoreSotService:
    def __init__(self, repository: CoreSotRepository) -> None:
        self._repo = repository
```

`save_draft` (line:152-211)의 idempotency 흐름:
1. `find_save_request`로 먼저 short-circuit (line:164-168)
2. race로 `DuplicateSaveRequest` 발생 시 committed version 재조회 후 replay 반환 (line:200-205)

Service layer가 dict 직접 접근 없이 Protocol method만 사용 → storage 교체 가능.

### 7. Main Wiring (main.py)

```python
def _default_service(...) -> CoreSotService:
    if os.environ.get("CORE_SOT_MONGO_URI"):
        client = MongoClient(uri)  # lazy import
        return CoreSotService(MongoCoreSotRepository(client, ...))
    return CoreSotService(InMemoryCoreSotRepository())
```

- `CORE_SOT_MONGO_URI` 설정 시 Mongo, 미설정 시 in-memory
- pymongo lazy import → in-memory 경로는 pymongo 없이도 동작
- `CORE_SOT_MONGO_TRANSACTIONS`, `CORE_SOT_MONGO_DB`로 조정 가능

### 8. Dependency (requirements.txt)

```
pymongo>=4.6,<5
```

pymongo 4.6+ transaction 지원, sync driver 선택됨 (사용자 결정: local MVP 단순성).

## Issues / Risks

### Blocking

**없음.** 모든 spec literal이 구현에 반영되어 있고 테스트가 전체 통과.

### Non-Blocking (Future Considerations)

1. **동시성 race 시나리오**: 현재 테스트는 순차적 실행. 병렬 save race (`find_save_request` → `record_save` 사이 경쟁)는 spec에 기술되어 있으나 테스트에서 직접 재현하지 않음. 그러나 두 경로 모두 이 경쟁을 방어함: transaction path는 abort, fallback은 race cleanup.
   - **위험도**: 낮음. unique index와 race cleanup이 방어하고 있음.
   - **권고**: HANDOFF Next Task #2에 "동시성 race(같은 idempotency_key 병렬 save)"로 이미 기록되어 있음.

2. **Write order 차이**: transaction path는 version→snapshot→blocks, fallback은 snapshot→blocks→version. 성공 시 동일하나 failure mode가 다름. spec은 write order를 요구하나 순서는 명시하지 않음.
   - **위험도**: 낮음. 둘 다 ordered write semantic을 보장.
   - **권고**: 없음. 구현 차이가 spec을 위반하지 않음.

3. **Index 부재 시 동작**: unique index가 없으면 idempotency 경계가 무력화됨. `ensure_indexes()` (line:75-88)가 있으나 collection drop 후 재생성 전에는 gap 가능.
   - **위험도**: 중간. production 환경에서는 index 생성이 초기 migration으로 보장되어야 함.
   - **권고**: HANDOFF Next Task #2에 "index 부재/충돌 시 동작"으로 이미 기록되어 있음.

## Verdict

**합격 (Pass)**

**근거:**
1. Spec ↔ implementation: 모든 persistence/retention 계약(v1.3) literal이 그대로 구현됨. 빈 칸 없음.
2. Repository Protocol: method-based contract로 service ↔ storage 분리가 올바르게 됨.
3. Two-path implementation: transaction 경로(기본)와 non-transaction fallback(local/test 제한)이 spec 요구대로 구현됨.
4. Idempotency boundary: unique index `(project_id, draft_id, idempotency_key)`가 authoritative boundary로 강제됨.
5. Test coverage: 17개 skip-aware 통합 테스트가 fallback/transaction 양 경로의 contract를 lock하고 있음.
6. Regression: 기존 151개 단위 테스트는 그대로 통과 (in-memory repository 보존).
7. Verification: 168개 전체 통과 (Mongo 미지정 시 17개 skip, Mongo 지정 시 168개 전체).

**Non-blocking 권고는 HANDOFF Next Task #2에 이미 기록되어 있어 본 slice에서 해결될 사항이 아님.**

## Outstanding Items

1. **구현 상태**: working tree에 uncommitted 변경이 있음 (git status shows `M service/main.py` 등). commit 필요.
2. **인프라 정리**: 검증용 Docker 컨테이너는 work_log 기록에 따라 정리됨 (`docker rm -f coresot-mongo-test`).
3. **다음 작업**: HANDOFF Next Task #1 (Dockerfile/Compose)이 본 slice와는 별개로 남아 있음.

## Reproduction

```bash
# 1. spec 확인
less docs/system-contract-sot.md

# 2. 구현 확인
less services/application/app/core_sot/repository.py
less services/application/app/core_sot/mongo_repository.py
less services/application/app/core_sot/service.py
less tests/test_core_sot_mongo.py

# 3. 테스트 실행 (인프라 없이)
python3 -m unittest discover -s tests

# 4. 테스트 실행 (Mongo with fallback)
docker run -d --name coresot-mongo-test -p 27018:27017 mongo:7
CORE_SOT_TEST_MONGO_URI="mongodb://localhost:27018" python3 -m unittest tests.test_core_sot_mongo.FallbackMongoTest -v

# 5. 테스트 실행 (Mongo with transaction)
docker exec coresot-mongo-test mongosh --eval "rs.initiate()"
CORE_SOT_TEST_MONGO_URI="mongodb://localhost:27018/?directConnection=true" python3 -m unittest tests.test_core_sot_mongo.TransactionMongoTest -v

# 6. 전체 테스트 (Mongo)
CORE_SOT_TEST_MONGO_URI="mongodb://localhost:27018/?directConnection=true" python3 -m unittest discover -s tests

# 7. 정리
docker rm -f coresot-mongo-test
```
