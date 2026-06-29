# Phase 2A Analysis Mongo persistence 보강 독립 재검증

## Subject Metadata

- **날짜**: 2026-06-29
- **요청자**: 사용자 ("핸드오프 읽고 다음작업 진행해줘" → HANDOFF Next Tasks #2 "Phase 2A Analysis Mongo persistence 보강분을 독립 재검증한다")
- **검증자**: Claude (본 세션, 보강 구현과 무관)
- **대상 slice**: 선행 검증 `docs/verifications/2026-06-29/analysis_mongo_persistence.md`의 조건부 합격 조건 **C1/C2 폐쇄 보강**.
  - C1: transaction 경로 all-or-nothing을 replica set Mongo에서 실행 확인.
  - C2: `record_candidates` intra-batch dedupe(`batch_seen`)에 focused 회귀 추가 + 계약화.
- **검증 대상 커밋**: `daef3f2` "Harden analysis Mongo persistence after verification" (8 파일). working tree clean(`git status` 빈 출력 확인).
- **정본 spec 참조(canonical contract scope)**:
  - `docs/system-contract-sot.md` **v1.6.7**(changelog line 36; §309 Phase 2A service batch API 계약 조) — 보강이 신설한 계약.
  - `docs/plans/02-analysis-pipeline.md` line 32(service batch API intra-batch idempotency 조).
  - **교차 참조 추적**: `BulkWriteError` 매핑은 v1.6.7 changelog가 "Mongo bulk duplicate는 stable `DuplicateAnalysisCandidateRequest`로 표면화"로 단언 → 코드의 catch 절과 대조. fallback "single-writer local/test 전용" 단언은 v1.6.6 §309 + Core SOT fallback parity(선행 검증 F2에서 확정)이므로 본 재검증에서는 재확인만.
  - **out of scope**: index literal(선행 F1/F3에서 lock), source anchor identity, payload schema, runner 계약 — 보강이 건드린 `BulkWriteError` 매핑·intra-batch dedupe·live 실행 표면만.
- **선행 검증과의 관계**: 본 레코드는 선행 conditional pass의 C1/C2가 **실제로** 닫혔는지를 묻는다. "작업 로그가 닫혔다고 적었다"가 아니라 1차 출처(코드/회귀/live 실행)에서 재도출.

## Scope

1. **C1 — transaction/fallback all-or-nothing live 실행**: replica set Mongo에서 `tests.test_analysis_mongo`(Fallback + Transaction 양 클래스) 실제 통과.
2. **`BulkWriteError` 매핑이 load-bearing**: 보강 전 상태(`DuplicateKeyError`만 catch)로 변이 시 live 테스트가 실제로 실패하는지 — 누출 예외가 정말 `BulkWriteError`(code 11000)인지.
3. **C2 — intra-batch dedupe 회귀**: 신규 test가 `batch_seen` 분기를 양방향 pin 하는지(변이 증명 포함), 계약(SoT v1.6.7/plan) literal ↔ 코드 일치.
4. **Pattern sweep**: 동일 root-cause(`insert_many` + `DuplicateKeyError`-only catch)가 인접 코드(Core SOT mongo)에 잠재 버그로 존재하는지.
5. **보고 숫자 재현**: "전체 discovery 271 통과·33 skip", "live 6개 통과".

## Methodology

```bash
# 0. 커밋 diff
git show daef3f2 -- services/application/app/analysis/mongo_repository.py docs/ tests/

# 1. 인프라 없는 focused + 전체 discovery
python3 -m unittest tests.test_analysis_phase2a tests.test_analysis_mongo_indexes tests.test_analysis_runner -v
python3 -m unittest discover -s tests          # expect Ran 271, OK (skipped=33)

# 2. throwaway replica set 기동
docker run -d --rm --name verify_mongo_27021 -p 27021:27017 mongo:7 --replSet rs0
docker exec verify_mongo_27021 mongosh --quiet --eval "rs.initiate({_id:'rs0',members:[{_id:0,host:'localhost:27017'}]})"

# 3. live 통합 (fallback + transaction 양 경로)
CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27021/?directConnection=true' \
  python3 -m unittest tests.test_analysis_mongo -v

# 4. BulkWriteError 매핑 변이 증명: catch 절을 DuplicateKeyError-only로 되돌린 뒤 live 재실행 → FAIL 확인 → git checkout 복원
# 5. batch_seen 변이 증명: existing_candidate=None 으로 분기 무력화 → dedupe test FAIL 확인 → 복원
# 6. pattern sweep: grep insert_many / DuplicateKeyError / BulkWriteError 전 repo, core_sot 인덱스 unique 여부 확인
docker stop verify_mongo_27021
```

> **환경**: 본 환경의 `localhost:27017`은 도달 불가(ServerSelectionTimeoutError). 그러나 docker가 가용하여 선행 검증이 막혔던 C1을 **throwaway replica set으로 직접 실행**했다. pymongo 4.13.2. 컨테이너는 검증 후 stop/rm 정리됨.

## Findings

### F1. C1 — transaction/fallback all-or-nothing live 실행 — 합격 (실행 증명)

`mongodb://localhost:27021`(단일 노드 replica set rs0)에서:

```
tests.test_analysis_mongo  →  Ran 6 tests, OK
  FallbackMongoAnalysisTest.{round_trips, batch_duplicate_rolls_back, idempotent_replay}  ok
  TransactionMongoAnalysisTest.{round_trips, batch_duplicate_rolls_back, idempotent_replay}  ok
```

선행 검증 F5/Issue#1이 "transaction 경로 all-or-nothing은 code-trace에만 의존, 실행 미검증"이라 남겼던 절반이 **실제 transaction 경로 실행으로 닫혔다**. `TransactionMongoAnalysisTest.test_candidate_batch_duplicate_rolls_back_partial_write`(`tests/test_analysis_mongo.py:174-219`)는 미리 commit한 candidate와 충돌하는 batch를 `put_candidates`로 넣고, `DuplicateAnalysisCandidateRequest` 발생 + 충돌 전 doc(`should-rollback`) 미잔류 + 기존 doc 보존을 단정한다 — transaction abort의 all-or-nothing이 실 Mongo에서 보장됨. **C1 폐쇄 확인.**

### F2. `BulkWriteError` 매핑이 load-bearing — 합격 (변이 증명)

보강의 코드 변경은 `mongo_repository.py`의 transaction/fallback 양 catch 절을 `DuplicateKeyError`-only → `(BulkWriteError, DuplicateKeyError)`로 확장한 것이다(`mongo_repository.py:209, 221, 223`). 이 catch를 **보강 전 상태로 되돌려** live 테스트를 재실행한 결과:

```
FAILED (errors=2)
pymongo.errors.BulkWriteError: batch op errors occurred ...
  'writeErrors': [{'index': 1, 'code': 11000,
    'errmsg': 'E11000 duplicate key error ... index: uniq_analysis_candidate_request
               dup key: { project_id: "project-1", task_id: ..., logical_key: "event:committed" }'}]
  ... 'nInserted': 1   ← 충돌 전 1건이 삽입됨(부분 쓰기 위험)
```

증명된 사실:
- `insert_many`는 batch duplicate에서 `DuplicateKeyError`가 아니라 **`BulkWriteError`**를 던진다(transaction·fallback 양 경로). 보강 전 catch는 이를 놓쳐 누출 → `errors=2`. 이는 작업 로그의 "first 실행은 `BulkWriteError` 누출로 2 errors"와 정확히 일치.
- 누출 예외의 `writeErrors[0].code == 11000`(duplicate key) — 즉 매핑 대상이 진짜 중복임을 실증. realistic 경로에서 `BulkWriteError`는 unique index(`uniq_analysis_candidate_request`) 위반을 감싼다.
- `nInserted: 1`은 fallback에서 cleanup 없이는 부분 쓰기가 남음을 보여줌 → 보강 catch + `delete_many` cleanup이 all-or-nothing에 load-bearing.

변이 후 `git checkout`으로 복원, 재실행 6개 OK. **under-strict guard 성립**(중복 처리 미흡이 재도입되면 live 테스트가 다시 ERROR).

### F3. C2 — intra-batch dedupe 회귀 + 계약 — 합격 (변이 증명 + literal 일치)

신규 회귀 `test_record_candidates_dedupes_same_task_logical_key_within_batch`(`tests/test_analysis_phase2a.py:204-228`)는 `(duplicate_request, duplicate_request, distinct_request)`를 한 batch로 `record_candidates`에 넣고:

| 단정 | 방향 | 보호하는 분기 |
|---|---|---|
| `first.idempotent_replay is False` | should-fire(신규) | `service.py:272-292` 신규 생성 |
| `replay.idempotent_replay is True` 및 `replay.candidate.id == first.candidate.id` | should-fire(intra-batch dup) | `service.py:248-256` `batch_seen` hit |
| `distinct.idempotent_replay is False` 및 `distinct.candidate.id != first.candidate.id` | should-NOT-fire(over-collapse 방지) | logical_key 다르면 별도 candidate |
| `len(repo.candidates) == 2` | 종합 | 3 request → 2 candidate |

변이 증명: `existing_candidate = batch_seen.get(candidate_key)`를 `= None`으로 무력화하면 `AssertionError: False is not true`(`replay.idempotent_replay`)로 **FAIL**, 복원 시 OK. `batch_seen` 분기가 실제 lock됨 — 선행 검증 F6/Issue#2의 "제거해도 어떤 test도 fail 안 함" 갭이 닫혔다.

계약 literal 일치: 코드 `candidate_key = (project_id, request.task_id, request.logical_key)`(`service.py:247`)가 SoT v1.6.7 §309 / plan line 32의 "같은 batch 안의 동일 `project_id + task_id + logical_key` request" 및 "logical_key가 다르면 별도 candidate"와 문자 그대로 일치. spec-silent 갭이 계약화로 닫혔다.

> **비고(계약 배치)**: stable `DuplicateAnalysisCandidateRequest` 표면화는 SoT **changelog 행(line 36)**에는 명시됐으나 §309 본문 prose에는 error 타입 이름이 없다. 모순은 아니며 동작은 정확하나, §본문에 1줄로 끌어올리면 인덱스 독자가 changelog까지 내려가지 않아도 된다. 비차단.

### F4. Pattern sweep — 합격 (검증된 negative, 인접 버그 없음)

동일 root-cause(`insert_many` 결과를 `DuplicateKeyError`-only로 catch)를 repo 전체에서 sweep:

- Core SOT `mongo_repository.py`도 `insert_many(block_docs)`(`:225, :261`)를 `except DuplicateKeyError`(`:226, :264`)로만 감싼다 — 구조적으로 동일 패턴.
- **그러나 버그 아님**: `ensure_indexes`에서 `uniq_save_request`는 `_versions`에 `unique=True`(`:86-93`), `blocks_by_snapshot`은 `_blocks`에 **non-unique**(`:95-97`). blocks 컬렉션에 unique 제약이 없으므로 `insert_many(block_docs)`는 duplicate-key를 낼 수 없고, 중복은 항상 `_versions.insert_one`(단건)에서 `DuplicateKeyError`로 발생 → catch 정확.
- 반대로 analysis는 `insert_many`가 `analysis_candidates`(unique `uniq_analysis_candidate_request`)에 쓰므로 중복이 `BulkWriteError`로 표면화 — 보강이 필요했던 이유가 unique 제약 위치 차이로 정확히 설명됨.

다른 `insert_many` 사용처는 위 2개 파일뿐(`grep` 확인). **인접 latent 버그 없음.**

### F5. 보고 숫자 — 합격 (재현 일치)

- focused `tests.test_analysis_phase2a tests.test_analysis_mongo_indexes tests.test_analysis_runner` → **28개 OK**.
- 전체 `python3 -m unittest discover -s tests` → **Ran 271, OK (skipped=33)** — 작업 로그 "전체 discovery 271개 통과(33 skip)"와 정확히 일치.
- live `tests.test_analysis_mongo` → replica set에서 **6개 OK**(작업 로그 "6개 통과"와 일치). 인프라 없을 땐 6 skip.

## Issues / Risks

1. **[비차단, 정밀도] `BulkWriteError` catch가 계약 literal보다 넓다.** 계약은 "bulk **duplicate** → `DuplicateAnalysisCandidateRequest`"인데 코드는 *모든* `BulkWriteError`를 duplicate로 매핑한다(`mongo_repository.py:209, 223`). realistic 경로(code 11000)는 F2에서 실증되어 정확하나, 비-중복 `BulkWriteError`(예: write concern, document-too-large)가 발생하면 "duplicate request"로 오표기되어 인프라 오류를 숨길 수 있다. candidate doc은 고정 schema·소형이라 운영상 드물어 비차단. 정밀화하려면 `exc.details["writeErrors"]`의 code가 모두 11000인지 확인 후 매핑하고 그 외는 재던지기 권장(선택).
2. **[비차단, 계약 배치] `DuplicateAnalysisCandidateRequest` 표면화가 SoT §본문이 아닌 changelog 행에만 명시.** F3 비고 참조. 동작 정확, 문서 가독성만.
3. **[참고] in-memory ↔ Mongo 비대칭(선행 검증 Issue#5 승계).** `InMemoryAnalysisRepository.put_candidates`는 unique 제약 없이 later-wins. service layer(`batch_seen` + `find_candidate_request`)가 양쪽 모두에서 중복을 차단하므로 정상 흐름에선 관찰 안 됨. 보강 범위 밖, 상태 유지.

## Verdict

**합격 (pass).** 선행 conditional pass의 C1/C2가 1차 출처에서 실제로 닫혔음을 독립 재도출했다.

**load-bearing 근거**:
- C1: transaction + fallback all-or-nothing이 실 replica set에서 6개 통과로 **실행 증명**(F1). 선행 검증이 환경 제약으로 못 닫았던 transaction 절반이 닫힘.
- `BulkWriteError` 매핑이 변이 증명으로 load-bearing 확인 — 보강 전 상태는 live에서 `errors=2`(code 11000 누출), 보강 후 통과(F2).
- C2 intra-batch dedupe가 변이 증명으로 양방향 lock + 계약 literal 일치(F3). 선행 검증의 미추적 should-fire 분기 + spec-silent 갭이 닫힘.
- pattern sweep로 인접 sibling 버그 부재를 unique 제약 위치로 실증(F4).
- 보고 숫자(271/33, live 6) 재현 일치(F5).

비차단 Issue 3건은 모두 "코드가 틀렸다"가 아니라 정밀도/문서 배치이며 합격을 막지 않는다.

## Outstanding items

- 선택적 후속(비차단): Issue#1(`BulkWriteError` code 11000 한정 매핑), Issue#2(§본문에 error 타입 1줄). 검증자는 코드를 수정하지 않음(CLAUDE.md).
- working tree clean, 단일 보강 커밋 `daef3f2`. 모든 변이는 검증 후 `git checkout`으로 복원됨.
- HANDOFF Next Tasks #3(다음 구현 slice: Application/Worker wiring vs Job/task 상태 전이 계약화)은 본 재검증과 독립이며 owner 결정 대기.

## Reproduction

```bash
# 인프라 없는 회귀 + 숫자 재현
python3 -m unittest tests.test_analysis_phase2a tests.test_analysis_mongo_indexes tests.test_analysis_runner -v
python3 -m unittest discover -s tests          # Ran 271, OK (skipped=33)

# live transaction/fallback 양 경로 (C1)
docker run -d --rm --name verify_mongo_27021 -p 27021:27017 mongo:7 --replSet rs0
sleep 3
docker exec verify_mongo_27021 mongosh --quiet --eval \
  "rs.initiate({_id:'rs0',members:[{_id:0,host:'localhost:27017'}]})"
sleep 3
CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27021/?directConnection=true' \
  python3 -m unittest tests.test_analysis_mongo -v   # Ran 6, OK
docker stop verify_mongo_27021

# BulkWriteError 매핑 변이 증명 (F2): catch를 DuplicateKeyError-only로 되돌리면 위 live 6개 중 batch_duplicate 2개가 errors
# batch_seen 변이 증명 (F3): service.py의 existing_candidate=batch_seen.get(...) → =None 으로 바꾸면
#   tests.test_analysis_phase2a ...dedupes_same_task_logical_key_within_batch 가 FAIL
```
