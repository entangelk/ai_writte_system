# Phase 2A Analysis Mongo persistence 독립 검증

## Subject Metadata

- **날짜**: 2026-06-29
- **요청자**: 사용자 ("작업 AI가 작업한 분 읽어 보고 검증하고 의심하고 또 의심해줄래?" — Phase 2A Analysis Mongo persistence slice)
- **검증자**: Claude (본 세션, 구현과 무관)
- **대상 slice**: Phase 2A Analysis Mongo repository/persistence — `MongoAnalysisRepository`, job/task/candidate idempotency unique index, candidate batch write의 transaction/fallback all-or-nothing 경계, service `record_candidates` batch API, runner batch write 전환.
- **정본 spec 참조(canonical contract scope)**:
  - `docs/system-contract-sot.md` **v1.6.6**(changelog line 34; §307–309 Phase 2A Mongo persistence 계약 3조) — 본 slice가 신설한 계약
  - `docs/plans/02-analysis-pipeline.md` line 31("candidate/needs_review 중심의 MongoDB 저장" 조)
  - `docs/plans/02-analysis-kickoff-decisions.md` line 94(step 5)
  - **교차 참조 추적**: SoT v1.6.6 §309가 "Core SOT fallback과 같이 single-writer local/test 전용"이라 단언 → `services/application/app/core_sot/mongo_repository.py`의 fallback 의미론이 계약 단언과 일치하는지 대조(계약 내부 일관성).
  - **out of scope**: Phase 2A runner 계약(v1.6.4/1.6.5) 자체의 재검증, source anchor identity(v1.6.3), payload schema — 본 slice가 건드린 persistence 표면만. 단 runner가 batch API로 전환된 접점은 검증.
- **검증 대상 커밋**: `bc4a1c0` Implement Phase 2A analysis Mongo persistence (단일 커밋, 13 파일).
- **작업 출처**: committed. working tree clean(`git status` clean 확인).
- **선행 검증**: `docs/verifications/2026-06-29/analysis_phase2a_slice4.md` (합격, non-blocking F2 = "Mongo all-or-nothing은 persistence slice에서 별도 검증" 으로 이월). **본 slice는 그 F2를 닫겠다고 선언한 slice** → F2 폐쇄가 실제로 일어났는지가 중심 검증 질문.
- **검증 입장**: (a) 계약 ↔ code literal 일치, (b) 계약 내부 자기모순 없음, (c) all-or-nothing 경계(transaction/fallback 양 경로)가 named 회귀 또는 실행으로 실제 보장되는지 — **skip된 green bar가 무엇을 검증하고 무엇을 검증하지 않는지 분리**, (d) boundary matrix 빈 칸(should-fire/should-not-fire 분기 중 test가 없는 것) 적발.

## Scope

1. **계약 ↔ code literal 일치** — collection 이름, required unique index 이름/키/unique flag, `analysis_candidates_by_job` query index, setup error mapping 타입.
2. **계약 내부 자기모순 / 교차참조 일관성** — SoT v1.6.6 ↔ plan ↔ kickoff ↔ CHANGELOG 간 literal 충돌, "Core SOT fallback과 같이" 단언의 진위.
3. **all-or-nothing 경계** — transaction 경로(한 트랜잭션 commit), fallback 경로(이번 시도 candidate `_id`만 삭제). **양 경로 모두 named 회귀 또는 직접 실행으로 증명**.
4. **batch API 회귀 감사** — `record_candidates`/`put_candidates`의 분기(new / cross-batch replay / intra-batch dup)가 named test에 매핑되는가.
5. **smoke/보고 숫자 교차검증** — 작업자 보고 "focused 8 / live Mongo 6 skip / 전체 discovery 270 통과·33 skip" 재현.
6. **회귀 test 감사** — `test_analysis_mongo_indexes.py`(실행), `test_analysis_mongo.py`(환경 skip)가 계약 분기를 양방향 pin 하는가. test code 자체가 감사 대상.

## Methodology

계약을 먼저 scope-read 한 뒤 code를 읽었고(순서 중요), boundary matrix를 세운 뒤 실행으로 채웠다. 재현 가능한 모든 명령은 아래와 동일.

```bash
# 0. 커밋 diff 확보
git show --stat bc4a1c0
git show bc4a1c0 -- services/application/app/analysis/  # 구현 diff
git show bc4a1c0 -- docs/                                # 계약 diff

# 1. compile
python3 -m py_compile services/application/app/analysis/models.py \
  services/application/app/analysis/repository.py \
  services/application/app/analysis/service.py \
  services/application/app/analysis/runner.py \
  services/application/app/analysis/mongo_repository.py \
  tests/test_analysis_mongo.py tests/test_analysis_mongo_indexes.py

# 2. focused (실행 가능한 index + runner)
python3 -m unittest tests.test_analysis_mongo_indexes tests.test_analysis_runner -v

# 3. live Mongo 통합 (환경 skip 여부)
python3 -m unittest tests.test_analysis_mongo -v

# 4. 전체 discovery (보고 숫자 재현)
python3 -m unittest discover -s tests

# 5. fallback all-or-nothing을 live Mongo 없이 직접 실행 검증(검증자 throwaway 스크립트)
#    -> _put_candidates_fallback 의 DuplicateKeyError→DuplicateAnalysisCandidateRequest +
#       이번 시도 _id cleanup을 fake collection으로 실행. (본 레코드 Reproduction 절 참조)

# 6. Mongo 가용성 / 인증 요구 여부 확인(왜 skip 되는가)
python3 -c "from pymongo import MongoClient; ..."   # localhost:27017 ping + insert auth probe

# 7. 교차참조 검증: Core SOT fallback 구조 대조
grep -n "use_transactions\|_fallback\|_transactional\|single.writer\|delete_many" \
  services/application/app/core_sot/mongo_repository.py
```

> **주의 — 환경 제약**: 본 검증 환경의 로컬 Mongo(`localhost:27017`)는 ping에는 응답하지만 **write에 인증을 요구**한다(`Command insert requires authentication`, code 13). 따라서 `test_analysis_mongo.py`의 probe가 `drop_database` cleanup에서 `Unauthorized(PyMongoError)`를 만나 (False, False)를 반환하고 6개 test가 전부 skip 된다. 이는 `CHANGELOG`에 기록된 Core SOT probe 수정과 **동일한 "auth-required = unavailable → skip" 패턴**이며 정상 동작이다. `CORE_SOT_TEST_MONGO_URI`는 미설정. **인증 정보는 검증 범위 밖에서 임의 수집하지 않았다.**

## Findings

### F1. 계약 ↔ code literal 일치 — 합격

SoT v1.6.6 §307–309와 plan line 31이 명시한 literal이 code에 변형 없이 존재한다.

| 계약 literal | code 위치 | 일치 |
|---|---|---|
| collection `analysis_jobs` / `analysis_tasks` / `analysis_candidates` | `mongo_repository.py:46-48` | ✓ |
| `uniq_analysis_job_request` = (project_id, snapshot_id, idempotency_key), unique | `mongo_repository.py:71-79` | ✓ |
| `uniq_analysis_task_request` = (project_id, job_id, candidate_type), unique | `mongo_repository.py:80-88` | ✓ |
| `uniq_analysis_candidate_request` = (project_id, task_id, logical_key), unique | `mongo_repository.py:89-97` | ✓ |
| `analysis_candidates_by_job` = (project_id, job_id), non-unique | `mongo_repository.py:98-101` | ✓ |
| index 거부 → `MongoAnalysisRepositorySetupError` | `mongo_repository.py:102-104` | ✓ |

`_candidate_doc`(`mongo_repository.py:261-276`)가 쓰는 field 집합과 `_to_candidate`(`mongo_repository.py:278-289`)가 읽는 field 집합은 **대칭**(round-trip 누락 field 없음). `logical_key`는 candidate model field가 아니라 index key로만 저장/조회됨 — model 의미론과 일치.

### F2. 계약 내부 자기모순 / 교차참조 일관성 — 합격

- SoT v1.6.6 ↔ plan line 31 ↔ kickoff line 94 ↔ CHANGELOG ↔ HANDOFF 간 collection/index 이름·키·unique 여부·fallback 의미론이 **문자 그대로 일치**. 모순 적발 안 됨.
- **교차참조 단언 검증(중요)**: SoT v1.6.6 §309가 fallback을 "Core SOT fallback과 같이 single-writer local/test 전용"이라 단언. `core_sot/mongo_repository.py`를 대조한 결과, 동일 구조(`use_transactions` flag `:57/61`, `_record_save_transactional`/`_record_save_fallback` 이중 경로 `:205/:229`, fallback `delete_many` cleanup `:252-253/267-268`, module docstring "single-writer only" `:16`)를 가진다. **단언 진실**.
- v1.6.5 changelog가 "Mongo persistence slice에서 all-or-nothing transaction/fallback 보존을 별도 검증"이라 이월(F2)했고, v1.6.6 changelog line 34가 본 slice로 그 이월을 닫겠다고 명시 — 계약의 인과 chain이 일관됨.

### F3. index setup 회귀 — 합격(실행 검증)

`test_analysis_mongo_indexes.py`의 2개 test가 **인프라 없이 실행**되어 index literal을 양방향 pin 한다.

- `test_ensure_indexes_creates_required_absent_indexes`: under-strict guard. `_jobs`/`_tasks`/`_candidates`에 대한 `create_index` call을 (keys list, kwargs dict)까지 정확히 단정. index 하나라도 빠지면 fail. 실행 OK.
- `test_conflicting_index_failure_is_stable_setup_error`: over-strict guard. `OperationFailure`가 `MongoAnalysisRepositorySetupError`로 wrapping되고 `__cause__`가 `OperationFailure`임을 단정 — setup 실패가 write 실패로 오인되지 않음. 실행 OK.

> **한계(비차단)**: over-strict test는 `uniq_analysis_candidate_request`(3번째) 실패만 재현. 1/2/4번째 index 실패 경로는 parametrize 되지 않았다. 단 `except OperationFailure`(`:102`)가 4개 `create_index` 전체를 감싸므로 어느 것이 실패해도 같은 매핑으로 수렴 — 동작 정확성엔 영향 없고, test 경계 폭만 좁다.

### F4. fallback all-or-nothing 경계 — 합격(직접 실행 검증, live Mongo 불필요)

`_put_candidates_fallback`(`mongo_repository.py:209-227`)의 핵심은 "batch `insert_many` 실패 시 이번 시도 `_id`만 `delete_many`로 정리". 이를 **fake collection으로 직접 실행**하여 code 읽기가 아닌 실행으로 증명했다(Methodology #5 / Reproduction).

시나리오: `event:committed` candidate를 미리 commit → `put_candidates([(should_rollback, "event:new"), (dup, "event:committed")])` 호출(use_transactions=False).

결과:
- `DuplicateAnalysisCandidateRequest` 발생 ✓ (under-strict: 중복 미검출 bug 재도입 시 이 단정 fail)
- cleanup 후 `should_rollback`(충돌 **전에** 삽입된 doc) 제거됨 ✓ (over-strict: cleanup 제거 시 `assertIsNone(get_candidate("should-rollback"))` fail)
- 기존 `committed` 보존 ✓
- `delete_many` 호출 인자 = `['dup','should-rollback']`(이번 시도 _id 전체) ✓

`insert_many` ordered 여부와 무관하게 cleanup이 "이번 시도 _id 전체"를 지우므로 경계가 견고함을 확인. code + 실행 모두 합격.

### F5. transaction all-or-nothing 경계 — **실행 미검증**(환경 제약), code-trace 합격

`_put_candidates_transactional`(`mongo_repository.py:196-208`)은 `start_session` + `start_transaction` 안에서 `insert_many` 후 `DuplicateKeyError`만 잡아 `DuplicateAnalysisCandidateRequest`로 전환. transaction context manager가 예외 시 자동 abort하므로 부분 쓰기 불가 — **code-trace 상 정확**.

**그러나 실행 검증 불가**: 본 환경 Mongo는 (a) 인증 필수, (b) standalone(replica set 아님) → transaction 경로를 재현할 수 없다. `test_analysis_mongo.py`의 `TransactionMongoAnalysisTest`(`use_transactions=True`)는 `_TXN_SUPPORTED` gate로 skip. **transaction 경로의 all-or-nothing은 code-trace에만 의존하며, 이 slice가 닫겠다고 한 F2의 절반(transaction 쪽)은 실행으로 증명되지 않았다.**

### F6. batch API 회귀 감사 — **1개 분기 미검증(GAP)**

`record_candidates`(`service.py:232-297`)는 입력 request에 대해 3 분기를 가진다:

| 분기 | code | named 회귀 | 비고 |
|---|---|---|---|
| 신규 candidate → `idempotent_replay=False` | `:269-284` | ✓ (기존 phase2a/runner test, in-memory 실행) | |
| cross-batch replay(`find_candidate_request` hit) → `idempotent_replay=True` | `:257-265` | ✓ (live `test_idempotent_replay_*`, 환경 skip / in-memory 회귀는 존재) | |
| **intra-batch dup(`batch_seen` hit) → `idempotent_replay=True`** | `:248-256` | **✗ test 없음** | **GAP** |

`batch_seen`(`:243, 248, 286`)은 같은 batch 내 동일 `(task_id, logical_key)` request를 idempotent replay로 정규화한다. 이게 없으면 동일 request 2개가 모두 `find_candidate_request`를 통과(아직 commit 안 됨)해 각기 새 candidate를 만들고, `put_candidates`에서 unique index 충돌 → `DuplicateAnalysisCandidateRequest`로 batch 전체 실패한다. 즉 **`batch_seen`은 batch API 정확성에 load-bearing인 방어 코드**다.

**그러나 유일 호출자인 runner가 `_dedupe_prepared`(`runner.py:150-156`)로 호출 **전**에 이미 중복을 제거**하므로, runner 경로는 `batch_seen`을 절대 거치지 않는다. 그리고 `record_candidates`/`put_candidates`를 batch로 직접 부르는 test는 **0개**(`grep` 확인: test에서 `record_candidates`/`put_candidates`를 직접 호출하는 곳은 `test_analysis_mongo.py:207`의 repo-layer `put_candidates` 단 1곳뿐, service batch dedupe 아님).

→ **`batch_seen` 분기를 제거해도 어떤 test도 fail 하지 않는다.** CLAUDE.md boundary-matrix 규칙상 "should-fire 분기에 named 회귀가 없으면 green bar와 무관하게 blocking". 또한 이 동작(intra-batch dup → idempotent replay)은 **SoT/plan에 명시되지 않은 spec-silent-but-code-enforced** → 계약 갭(contract gap).

### F7. smoke/보고 숫자 — 합격(재현 일치)

- focused(index+runner) `python3 -m unittest tests.test_analysis_mongo_indexes tests.test_analysis_runner -v` → **8개 통과**(보고 8과 일치).
- live Mongo `python3 -m unittest tests.test_analysis_mongo -v` → **6개 skip**, skip 사유 메시지 정상(skip-aware). 보고와 일치.
- 전체 `python3 -m unittest discover -s tests` → **Ran 270 tests, OK (skipped=33)**. 작업자 보고 "270 통과·33 skip"과 **정확히 일치**(재계산 안 된 보고 숫자 없음 확인).

## Issues / Risks

1. **[비차단, 환경 제약] transaction 경로 all-or-nothing이 실행 미검증.** 본 slice의 존재 이유(F2 폐쇄)의 절반(transaction 쪽)이 code-trace에만 의존. replica set + 인증 Mongo에서 `tests.test_analysis_mongo`(특히 `TransactionMongoAnalysisTest`)를 실행하기 전까지 "transaction 경로도 실행으로 확인했다"고 주장할 수 없다. fallback 쪽은 본 검증에서 fake collection 실행으로 닫았다(F4).
2. **[계약 갭 + 미검증 분기] `record_candidates` intra-batch dedupe(`batch_seen`).** SoT/plan이 명시하지 않은 동작을 code가 강제하며, named 회귀가 없어 제거해도 suite가 green. (a) focused in-memory 회귀 추가 + (b) SoT/plan에 "service batch API는 intra-batch 동일 (task_id, logical_key) request를 idempotent replay로 정규화" 1줄 계약화 — 또는 (c) 의도적으로 scope-out 문서화 — 중 하나로 갭을 닫아야 함. CLAUDE.md에 따르면 미추적 should-fire 분기는 blocking 취급.
3. **[비차단, 한계] index over-strict test 경계 폭.** F3 참조. 4개 index 중 1개(uniq_analysis_candidate_request) 실패만 parametrize. 동작엔 영향 없으나 경계 lock 폭이 좁음.
4. **[비차단, 운영 메모] 기본 `use_transactions=True`가 standalone Mongo에서 hard-fail.** replica set이 아닌 Mongo에 기본 repo를 그대로 물리면 `start_transaction()`이 `OperationFailure`를 던지며 candidate write가 clean error가 아닌 채로 실패. 계약은 "정상 Docker/runtime은 transaction 기본"이라 가정하므로 위반이 아니나, 운영자가 standalone에 기본값으로 물릴 경우의 안내가 계약에 없음.
5. **[참고] in-memory ↔ Mongo 행동 비대칭(잠재).** `InMemoryAnalysisRepository.put_candidates`(`service.py:117-127`)는 unique 제약을 강제하지 않고 later-wins로 덮어쓴다. Mongo는 unique index로 `DuplicateAnalysisCandidateRequest`. 단 service layer(`batch_seen` + `find_candidate_request`)이 양쪽 모두에서 중복을 차단하므로 정상 흐름에선 관찰되지 않음. 본 slice의 계약 범위 밖이나 기록.

## Verdict

**조건부 합격(conditional pass).**

**합격 사유(load-bearing, 실행/계약으로 증명됨)**:
- 계약 ↔ code literal 일치 + 계약 내부 자기모순 없음(F1, F2). 교차참조(Core SOT fallback parity) 단언 진실.
- index setup literal + setup-error 매핑이 인프라 없이 실행되는 named 회귀로 양방향 pin(F3).
- fallback all-or-nothing이 fake collection **실행**으로 증명됨(F4). 이 slice가 닫겠다 한 F2의 fallback 절반은 실행 검증 완료.
- 보고 숫자(270/33) 재현 일치(F7).

**조건(합격 전환 조건)**:
1. **C1**: transaction 경로 all-or-nothing을 replica set + 인증 Mongo에서 `tests.test_analysis_mongo`(`TransactionMongoAnalysisTest` 포함)로 실행 확인. 그 전엔 transaction 쪽 F2 폐쇄가 "code-trace만" 임을 명시.
2. **C2**: `record_candidates` intra-batch dedupe(`batch_seen`)에 focused in-memory 회귀 추가 + SoT/plan에 1줄 계약화(또는 명시적 scope-out). 현재 미추적 should-fire 분기 + spec-silent 갭.

C1은 환경 제약(인증 정보/replica set 확보)에 달린 운영 항목이고, C2는 owner가 즉시 닫을 수 있는 code/계약 작업이다. 둘 중 하나라도 "합격" 전환 조건이며, 어느 쪽도 "code가 틀렸다"가 아니라 "실행/계약 lock이 아직 덜 닫혔다"임.

## Outstanding items

- **owner 결정 대기(C2)**: `batch_seen` 분기 회귀 추가 + 계약화 vs scope-out. 검증자는 code를 수정하지 않음(CLAUDE.md: 검증 실패/갭을 silently fix하지 않는다).
- **운영(C1)**: 인증 replica-set Mongo 확보 후 `CORE_SOT_TEST_MONGO_URI`로 `tests.test_analysis_mongo` full 실행 권장. 본 환경에선 불가.
- working tree clean, commit 단일(`bc4a1c0`). publication 권한은 본 검증 범위 밖.
- HANDOFF "Next Tasks #2"가 이미 "본 slice 독립 검증"을 다음 작업으로 적시 → 본 레코드가 그 작업의 산물.

## Reproduction

```bash
# F3 (index 회귀, 실행)
python3 -m unittest tests.test_analysis_mongo_indexes -v

# F7 (전체 discovery 숫자 재현)
python3 -m unittest discover -s tests   # expect: Ran 270, OK (skipped=33)

# F4 (fallback all-or-nothing, live Mongo 없이 직접 실행) — 검증자 throwaway 스크립트:
python3 - <<'PY'
from pymongo.errors import DuplicateKeyError
from services.application.app.analysis.models import (
    AnalysisCandidate, AnalysisCandidateAction, AnalysisCandidateStatus,
    AnalysisCandidateType, AnalysisProvenance)
from services.application.app.analysis.mongo_repository import (
    MongoAnalysisRepository, DuplicateAnalysisCandidateRequest)

class FakeCandidates:
    def __init__(self): self._by_id={}; self._uniq={}; self.delete_calls=[]
    def insert_many(self, docs):
        for d in docs:
            k=(d["project_id"],d["task_id"],d["logical_key"])
            if k in self._uniq: raise DuplicateKeyError("dup")
            self._by_id[d["_id"]]=d; self._uniq[k]=d["_id"]
    def delete_many(self, f):
        ids=set(f["_id"]["$in"]); self.delete_calls.append(sorted(ids))
        for i in ids:
            d=self._by_id.pop(i,None)
            if d: self._uniq.pop((d["project_id"],d["task_id"],d["logical_key"]),None)
    def find_one(self, f):
        if "_id" in f: return self._by_id.get(f["_id"])
        for d in self._by_id.values():
            if all(d.get(k)==v for k,v in f.items()): return {"_id":d["_id"]}
        return None

def cand(cid,lk):
    return AnalysisCandidate(id=cid,project_id="p1",job_id="j1",task_id="t1",
        candidate_type=AnalysisCandidateType.EVENT_OBSERVATION,
        action=AnalysisCandidateAction.CREATE,status=AnalysisCandidateStatus.NEEDS_REVIEW,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,confidence=0.8,
        source_ref_ids=("s1",),payload={"event":cid})

repo=object.__new__(MongoAnalysisRepository); repo._use_transactions=False
repo._candidates=FakeCandidates()
repo.put_candidate(cand("committed","event:committed"),logical_key="event:committed")
try:
    repo.put_candidates([(cand("rb","event:new"),"event:new"),
                         (cand("dup","event:committed"),"event:committed")])
    raise SystemExit("FAIL: no exception")
except DuplicateAnalysisCandidateRequest: print("PASS dup->DuplicateAnalysisCandidateRequest")
assert repo.get_candidate("rb") is None, "OVER-STRICT FAIL: rb not cleaned"
assert repo.get_candidate("committed") is not None, "FAIL: committed lost"
print("PASS fallback all-or-nothing (attempt-only cleanup)")
PY
```
