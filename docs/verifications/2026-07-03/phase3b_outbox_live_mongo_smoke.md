# Phase 3B index_sync_outbox Live Mongo Smoke 독립 검증

## Subject metadata

- 검증일: `2026-07-03`
- 요청자: 프로젝트 오너("다음 작업 검증해줘. 커밋 2개 완료했습니다. … index_sync_outbox live Mongo persistence smoke를 추가했습니다.")
- 검증자: 독립 검증 AI (Claude)
- 검증 대상 slice: `9c17038 Add live index sync outbox smoke` — `tests/test_indexing_mongo.py`(신규, skip-aware live smoke 2개) + HANDOFF/work_log 갱신.
- 정합 스펙 기준(canonical contract scope):
  - 직전 검증 `docs/verifications/2026-07-03/phase3b_archive_outbox_slice.md`가 "다음 slice"로 명시한 "Mongo live round-trip/outbox persistence smoke" + 그 검증의 risk #1(직렬화 무테스트)
  - `docs/system-contract-sot.md` v1.6.26 archive outbox 계약 + v1.6.27 후속 보강 항목
  - 구현 계약: `services/application/app/indexing/mongo_repository.py`(`MongoIndexSyncRepository`: `put_outbox_entry`/`get_outbox_entry_by_dedup_key`/`_outbox_doc`/`_to_outbox_entry`/`ensure_indexes`)
- 검증 대상 작업 출처: commit `9c17038`(HEAD), working tree clean. 보조 확인: `36063d0`에 bundle된 직전 검증 risk 해소(`mongo_collections.md` §39A, fake round-trip 회귀, `analysis_completed` pin).

## Scope

정합 스펙 스코프를 (1) 직전 검증의 risk #1 해소로서의 "live round-trip/outbox persistence smoke", (2) SoT v1.6.26/v1.6.27의 outbox 영속 계약으로 좁혔다. 본 slice는 test-only 추가(production code 변경 없음)이므로, 구현 계약 대상은 직전 slice에서 이미 commit된 `mongo_repository.py`의 직렬화/영속/idempotency 동작이다.

검증 surface:

1. `tests/test_indexing_mongo.py` — skip-aware probe(write 권한 검증), live round-trip 1개, cross-instance live dedup 1개
2. live 동작 독립 재현: throwaway `mongo:7`로 2개 live smoke 실제 실행
3. 작업자 주장 카운트(discover 398 / live 2 pass / `git diff --check`) 재현
4. 보조: 직전 검증 risk #1/#2/#4 해소가 `36063d0`에 정확히 반영됐는지 교차 확인(fake round-trip, §39A registry, `analysis_completed` pin)

## Methodology

스펙을 읽어 boundary matrix를 구성한 뒤 live Mongo를 **직접** throwaway container로 띄워 재현. 작업자 주장·work_log를 복사하지 않고, 별도 포트(27032)·별도 이미지 인스턴스(standalone mongo:7)로 독립 입증. shared resource(`shared-mongo:27017`)는 mutation하지 않았다.

실행한 명령:

- `git log --oneline -6`, `git status`, `git show --stat 9c17038`, `git show --stat 36063d0`
- `Read`로 `tests/test_indexing_mongo.py` 전량, `tests/test_indexing_mongo_indexes.py`(1-68, 100-164), `tests/test_indexing_phase3a.py:249-266` 열독
- `git show 9c17038 -- HANDOFF.md docs/daily_logs/2026-07-03/work_log.md`, `git show 36063d0 -- docs/mongo_collections.md`(risk #2 해소 확인)
- `docker ps`(mongo container/포트 확인: `shared-mongo:27017`, `agent-memory-mongodb:27018`)
- `python3 -m py_compile tests/test_indexing_mongo.py tests/test_indexing_mongo_indexes.py` + `git diff --check`
- `docker run --rm -d --name iso-verify -p 27032:27017 mongo:7` → readiness poll(`mongosh ping`)
- `CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27032/?directConnection=true' python3 -m unittest tests.test_indexing_mongo -v`(live 2)
- `CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27032/?directConnection=true' python3 -m unittest discover tests`(398 / live 포함)
- `CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27099/?directConnection=true' python3 -m unittest discover tests`(398 / 39 skip, 작업자 sandbox 동등 재현)
- `docker stop iso-verify`(정리 + 잔존 확인)

## Findings

### 1. skip-aware probe — 권한 있는 Mongo만 live 실행

- `tests/test_indexing_mongo.py:39-59` `_probe_mongo()`: 단순 `ping`이 아니라 throwaway DB에 `create_index("key")`까지 수행해 write 권한을 검증한다. 연결만 되고 write 권한이 없는 Mongo를 live 가능으로 오판하지 않는다(직전 work_log에 명시된 해소). 5회 retry + `serverSelectionTimeoutMS=300`. ✅
- `_MONGO_AVAILABLE = _probe_mongo()`를 import 시 평가하고 `@unittest.skipUnless(_MONGO_AVAILABLE, ...)`로 class 단위 skip. Mongo 미가용/권한 없음 → skip(not fail). ✅

### 2. live round-trip boundary matrix

| boundary | 분기 | 테스트 | 가드 | 결과 |
|---|---|---|---|---|
| project_archived entry가 Mongo에 영속 후 fresh repo로 동일 복원 | should-fire | `test_project_archive_outbox_entry_persists_and_round_trips`(`:77-103`) | `assertEqual(recovered, entry)`(전 field 동치) + status/attempt_count/max_attempts/next_attempt_at/last_error/targets.chroma.{status,backend} 명시 pin | ✅ |
| cross-instance repeated enqueue가 live unique index 위에서 동일 sync_request_id, document 1개 | should-fire(idempotency) | `test_repeated_project_archive_replays_same_live_outbox_document`(`:105-115`) | 별도 repo instance 2개 사용, `assertEqual(replay.sync_request_id, first.sync_request_id)` + `count_documents({})==1` | ✅ |

- round-trip 테스트(`:80-93`)는 entry를 `self.service`로 넣은 뒤 **새 `MongoIndexSyncRepository` 인스턴스**(`reread_repo`)에서 `get_outbox_entry_by_dedup_key`로 읽어 `recovered == entry`를 단언한다. Python 메모리가 아니라 Mongo에 실제로 write됐음을 입증하는 핵심 가드. `_outbox_doc`/`_to_outbox_entry` 직렬화에서 field 하나라도 누락되면 동치 단언이 실패한다.
- idempotency 테스트(`:106-115`)는 두 번째 enqueue를 **별도 service+repo 인스턴스**로 수행한다. service의 get-then-put이 첫 repo가 write한 Mongo document를 새 repo에서 get으로 찾아 재사용함을 입증(인메모리 상태 공유 아님). `count_documents({})==1`로 중복 미발생을 pin.
- tearDown(`:73-75`)이 `drop_database` + `close`로 격리/정리. setUp마다 `uuid` 기반 고유 db명(`:69`)으로 병렬/재실행 충돌 회피. ✅

### 3. live 동작 독립 재현 (작업자 주장 B)

- throwaway `mongo:7` standalone(포트 27032, `--replSet` 없음)에서:
  ```
  CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27032/?directConnection=true' \
    python3 -m unittest tests.test_indexing_mongo -v
  → test_project_archive_outbox_entry_persists_and_round_trips ... ok
    test_repeated_project_archive_replays_same_live_outbox_document ... ok
    Ran 2 tests in 3.977s  OK
  ```
- 작업자는 replSet(`--replSet rs0` + `rs.initiate`) on 27031에서 통과했다고 했고, 검증자는 **standalone mongo:7**에서도 동일 통과를 입증했다. smoke가 replSet이 아닌 vanilla mongo:7에서도 동작함이 확인됐다.

### 4. 작업자 주장 카운트 재현 + hygiene

- `python3 -m py_compile tests/test_indexing_mongo.py tests/test_indexing_mongo_indexes.py` → OK.
- `git diff --check` → clean(working tree clean, HEAD=`9c17038`).
- discover(unreachable URI, 작업자 sandbox 동등) → `Ran 398 tests … OK (skipped=39)` — 작업자 주장 "398 통과, 39 skip" 정확 재현.
- discover(live URI → 검증자 mongo:27032) → `Ran 398 tests … OK (skipped=18)` — live 2개가 full suite 내에서도 통과.
- skip 카운트(18/39)는 환경 의존(mongo 가용성 등). 핵심 불변량 **398 total / 0 failures**는 양쪽 모두에서 성립. 컨테이너 정리 완료(`docker stop iso-verify`, 잔존 없음 확인).

### 5. 보조 — 직전 검증 risk 해소가 정확히 반영됐는지 교차 확인

- **risk #1(직렬화 무테스트) 해소 — 단위 + live 이중 pin.** `tests/test_indexing_mongo_indexes.py:123-160` `test_outbox_entry_round_trips_through_mongo_document_shape`가 `_FakeCollection`(`insert_one`/`find_one` + dotted-key `_lookup` 지원, `:43-64`)로 실저장/복원 round-trip을 검증한다. 단위 테스트는 `attempt_count=2`, `next_attempt_at="..."`, `last_error=IndexSyncLastError(NOT_FOUND, ...)` 등 **live entry(항상 pending/None)가 닿지 못하는 non-trivial/terminal 인접 필드**까지 `assertEqual(recovered, entry)`로 pin한다. 위 §2 live round-trip과 보완 관계. ✅
- **risk #2(collection registry 누락) 해소.** `docs/mongo_collections.md`에 `§39A index_sync_outbox`가 추가됐다(Purpose/Document Example/Idempotency/Indexes). Document Example이 `_outbox_doc`과 field-by-field 일치(`_id`/`sync_request_id`/`user_id:null`/`source{...,mongo_version:null}`/`targets.chroma{status,backend}`/retry metadata/`last_error:null`), error_type `backend_error`/`not_found` 분리 명시, dedup key + 2개 outbox index 일치. `§39 index_sync_logs`에도 code가 생성하는 2개 join index(`sync_request_id+attempt_count`, `project_id+sync_request_id`)가 보강됐다. ✅
- **risk #4(`analysis_completed` 미개방 미 pin) 해소.** `tests/test_indexing_phase3a.py:249-253` `test_analysis_completed_event_is_not_open_until_candidate_indexing_contract`가 `assertNotIn("analysis_completed", {event.value for event in IndexSyncEvent})`로 pin한다. enum에 조기 추가 시 실패하는 올바른 over-strict 가드. ✅
- **risk #3(status-aware dedup) — 명시적 후속 이월.** HANDOFF Next Task 2에 "검증자가 지적한 status-aware dedup은 worker가 terminal 상태를 만들기 시작할 때 함께 정제한다"로 기록됐다. 본 slice엔 worker가 없어 entry가 항상 pending이므로 현재 결함 아님. ✅(이월 명시)
- SoT v1.6.27 항목이 위 해소(§39A + round-trip + `analysis_completed` pin)를 정확히 기술. live smoke slice 자체는 test-only라 SoT bump 없음 → "major design/feature change" 기준에 부합하는 올바른 판단.

## Issues / Risks

> 본 slice(test-only) 대상 결함은 없다. 비블로킹 관찰만 기록.

1. **[Observation] live smoke는 `project_archived`만 실행한다.** `draft_archived` live round-trip은 없다. 두 event는 동일 `_enqueue_archive_event` → 동일 직렬화 경로이고, 단위 round-trip 테스트가 field 전체(terminal 인접 필드 포함)를 pin하므로 전이 커버는 성립. live에서 draft 한 케이스 추가는 marginal 보강.
2. **[Observation] `put_outbox_entry`의 `except DuplicateKeyError: return`(`mongo_repository.py:102-103`)이 어떤 테스트에도 닿지 않는다.** service가 get-then-put이라 단일 thread에선 dup insert가 발생하지 않고, fake `_FakeCollection.insert_one`은 uniqueness를 강제하지 않으며, live도 get-then-put으로 dup을 피한다. 해당 분기는 동시 worker 경쟁용 defensive code이고 correct-by-inspection이다. 그 분기를 trigger할 unique index 자체는 존재(index setup 회귀 + live 생성자 성공으로 입증). 동시성 하 기능적 강제는 worker slice에서 닿을 수 있다.
3. **[Operational awareness] 기본 `_MONGO_URI`가 `mongodb://localhost:27017`.** 27017에 write 가능 Mongo가 떠 있는 환경(검증자 환경의 `shared-mongo` 등)에서는 기본 `discover`가 live 2개를 **silently 실행**해 해당 Mongo에 uuid 기반 test db를 만들고 지운다(tearDown/probe가 정리하므로 잔류는 없음). skip-aware·격리·자기정리이지만, "기본 discover가 27017의 Mongo에 side-effect"는 인지 항목. 작업자 sandbox는 27017이 비어 39 skip으로 관측됐다. 결함 아님.
4. **[Observation] live smoke가 real Mongo의 index 목록을 명시 단언하지 않는다.** `MongoIndexSyncRepository.__init__`이 `ensure_indexes()`를 호출하므로, index 생성이 실패하면 setUp에서 생성자가 `MongoIndexSyncRepositorySetupError`를 raise해 test가 error(자동 실패)된다. index spec 자체는 단위 테스트(`test_ensure_indexes_creates_required_outbox_and_log_indexes`)가 명시 pin. live에서 별도 index 단언은 중복이므로 생략 타당.

## Verdict

**합격(PASS)** — `9c17038` live Mongo smoke slice.

load-bearing 사유:
- 본 slice의 목적(직전 검증/HANDOFF가 다음 slice로 지정한 "Mongo live round-trip/outbox persistence smoke")이 `tests/test_indexing_mongo.py` 2개 테스트로 정확히 달성됐고, round-trip 동치(`recovered == entry`) + cross-instance idempotency(`sync_request_id` 동일 + `count_documents==1`)의 핵심 boundary가 live Mongo 위에서 pin됐다.
- live 동작을 작업자 환경(replSet:27031)이 아닌 **독립 throwaway mongo:7 standalone(27032)**에서 재현해 2개 통과를 입증했다(vanilla mongo:7 호환성까지 확인).
- 작업자 주장 카운트(398 / live 2 pass / `git diff --check` clean)를 독립 재현. discover 398 total / 0 failures는 skip 카운트(환경 의존)와 무관하게 성립.
- 직전 검증 risk #1(직렬화)·#2(registry)·#4(`analysis_completed` pin)가 `36063d0`에 정확히 해소됐음을 교차 확인했고, risk #3(status-aware dedup)은 worker slice로 명시 이월됐다.

위 Issues/Risks는 전부 비블로킹 관찰(동일 경로 전이 커버, defensive 미닿는 분기, 기본 URI side-effect 인지, live index 중복 단언 생략 타당)로, 본 slice 결함이 아니다.

## Outstanding items

- 본 slice는 commit `9c17038`로 HEAD에 반영됐고 working tree clean. `git push` 여부는 `git status`가 "ahead of origin/main by 2 commits"이므로 owner 결정 대기.
- 다음 slice는 worker/retry. 오너가 명시한 대로 **claim timeout과 backoff 숫자가 미확정**이므로, worker 구현 착수 전 해당 값을 먼저 정해야 한다(결정 브리프 §5 "Backoff 숫자와 claim timeout은 worker slice에서 확정"). status-aware dedup 정제(risk #3)도 worker가 terminal 상태를 만들 때 함께 다룬다.

## Reproduction

```bash
# 상태/코드/테스트
git log --oneline -3                       # 9c17038 (HEAD), 36063d0, 86b82af
git show --stat 9c17038                    # test_indexing_mongo.py +119, HANDOFF/work_log
git show 36063d0 -- docs/mongo_collections.md   # §39A registry (risk #2 해소)
python3 -m py_compile tests/test_indexing_mongo.py tests/test_indexing_mongo_indexes.py
git diff --check

# discover — 작업자 sandbox 동등(unreachable URI → 39 skip)
CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27099/?directConnection=true' \
  python3 -m unittest discover tests        # Ran 398 … OK (skipped=39)

# live 독립 재현 (throwaway mongo:7)
docker run --rm -d --name iso-verify -p 27032:27017 mongo:7
# wait readiness
for i in $(seq 1 40); do docker exec iso-verify mongosh --quiet --eval 'db.adminCommand({ping:1}).ok' 2>/dev/null | grep -q 1 && break; sleep 0.5; done
CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27032/?directConnection=true' \
  python3 -m unittest tests.test_indexing_mongo -v   # Ran 2 … OK
CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27032/?directConnection=true' \
  python3 -m unittest discover tests                  # Ran 398 … OK (live 포함)
docker stop iso-verify
```
