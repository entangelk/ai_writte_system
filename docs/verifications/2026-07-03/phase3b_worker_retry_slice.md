# Phase 3B index sync worker/retry 구현 slice 독립 검증

## Subject metadata

- 검증일: `2026-07-03`
- 요청자: 프로젝트 오너("작업한거 검증해줘. 진행 완료했고 커밋까지 만들었습니다. 커밋: 2fcce00 Add index sync worker retry slice")
- 검증자: 독립 검증 AI (Claude)
- 검증 대상 slice: commit `2fcce00 Add index sync worker retry slice` — one-shot worker CLI(`scripts/index_sync_worker.py`), `IndexSyncWorker`/lifecycle service, Mongo `claim_next_outbox_entry`/`record_outbox_success`/`record_outbox_failure`, `claimed_at` lease field, terminal-move(option B), archive worker-time `not_found` idempotent success.
- 정합 스펙 기준(canonical contract scope):
  - `docs/plans/03-index-worker-retry-decisions.md` §7(claim lease/timestamps/accounting), §8(닫힌 결정 + 수용 기준 6항 + 회귀 10항) — 본 slice의 직접 계약
  - `docs/system-contract-sot.md` v1.6.28(브리프 조건부 승인) + v1.6.29(worker 구현)
  - `docs/mongo_collections.md` §39A(outbox active queue + terminal 이동 + claimed_at) / §39(logs)
  - 선행: `03-index-sync-outbox-decisions.md` §3(split), §5(error type), 직전 검증 `docs/verifications/2026-07-03/phase3b_worker_retry_brief.md`(Issues #1~#4)
- 검증 대상 작업 출처: commit `2fcce00`(HEAD), working tree clean.

## Scope

정합 스펙 스코프를 (1) 브리프 §7/§8(수용 기준 + 회귀), (2) SoT v1.6.29 worker 단락, (3) mongo_collections §39A terminal-move/claimed_at로 좁혼다. 본 slice는 직전 검증(phase3b_worker_retry_brief.md)의 Issues #1(terminal-location)·#2(claim lease field)·#3(not_found idempotent success)·#4(fake adapter op)에 대한 오너 결정+구현이므로, 각 해소가 코드·테스트·계약 문서에 일관되게 반영됐는지를 주축으로 삼았다.

검증 surface:

1. 구현 코드: `models.py`(claimed_at/started_at/finished_at field + datetime type), `service.py`(`IndexSyncWorker`/`run_once`/`_process_entry`, `_claimable`/`_claim_sort_key`/`_backoff_seconds`, in-memory claim/success/failure), `mongo_repository.py`(atomic `find_one_and_update` claim, `delete_one`/`update_one` terminal-move, `_to_utc_datetime` 정규화), `scripts/index_sync_worker.py`(CLI)
2. 회귀 테스트: `tests/test_indexing_phase3a.py::IndexSyncWorkerTest`(5개) + `tests/test_index_sync_worker_script.py`(2개) — §8 회귀 10항 ↔ 테스트 추적 + 양방향 가드
3. 작업자 주장 카운트(focused 27 / full 407·40skip / `git diff --check`) 재현
4. **live Mongo worker lifecycle 독립 재현**: throwaway `mongo:7`에서 success / backoff-terminal / stale-reclaim / terminal-reenqueue 4경로(suite엔 live worker test가 없어 검증자가 직접 수행)
5. 계약 문서 일관성: 브리프 §5 vs §8.2(not_found), SoT v1.6.29, mongo_collections §39A

## Methodology

브리프 §8 회귀를 boundary matrix로 세운 뒤 코드·테스트에 역추적. 작업자 주장·work_log를 복사하지 않고 명령 재실행·재도출. live Mongo worker 경로는 suite에 테스트가 없으므로 throwaway `mongo:7`(포트 27033, standalone)에서 4경로를 직접 실행해 입증(shared resource 미변경, uuid db 격리 후 drop).

실행한 명령:

- `git log --oneline`, `git status`(clean), `git show --stat 2fcce00`, `git diff 9ac59c3..2fcce00 -- docs/system-contract-sot.md docs/mongo_collections.md`
- `Read`/symbol overview로 `models.py` diff, `service.py`(`IndexSyncWorker`/helper/in-memory repo claim·success·failure), `mongo_repository.py`(claim/success/failure/`_to_utc_datetime`), `scripts/index_sync_worker.py`, `tests/test_index_sync_worker_script.py`, `tests/test_indexing_phase3a.py::IndexSyncWorkerTest` 전량 열독
- `python3 -m py_compile`(7 파일) + `git diff --check`
- `python3 -m unittest tests.test_indexing_phase3a tests.test_index_sync_worker_script tests.test_indexing_mongo_indexes`(focused 27)
- `python3 -m unittest discover tests`(full 407 / skipped=40)
- live worker check: `docker run --rm -d --name iso-worker-verify -p 27033:27017 mongo:7` → `PYTHONPATH=<repo> python3 /tmp/worker_live_check.py`(success/backoff-terminal/stale-reclaim/terminal-reenqueue 4경로) → `docker stop`

## Findings

### 1. 직전 검증 Issues #1~#4 해소가 코드·문서에 일관되게 반영됐다

- **#1 terminal-location → option B(terminal 이동) 채택·구현.** `record_outbox_success`(`service.py:173`, `mongo_repository.py:172`)와 terminal `record_outbox_failure`(`service.py:198`, `mongo_repository.py:195`)가 모두 outbox entry를 제거(`_remove_outbox_entry` / `delete_one`). dedup key가 해제되므로 같은 key의 재enqueue가 새 `sync_request_id`로 가능. 기존 unique index(`{project_id,event,source.mongo_collection,source.mongo_id}`)는 변경 없이 active-only로 동작(mongo_collections §39A에 "active queue; terminal 시 outbox doc 제거, history는 logs; 기존 unique index는 active에 scope"로 명시). ✅
- **#2 claim lease field 추가.** `IndexSyncOutboxEntry.claimed_at: datetime | None`(`models.py`) 추가. claim 시 `claimed_at=now` 세팅(in-memory `:152`, Mongo `$set claimed_at` `:144`). `INDEX_SYNC_CLAIM_TIMEOUT_SECONDS`(10분)로 stale running 판정. mongo_collections §39A document example + index(`status,next_attempt_at,claimed_at,sync_request_id`)에 반영. ✅
- **#3 archive worker-time `not_found` → idempotent success.** `_process_entry`→`mark_archived`가 `DerivedIndexRecordNotFound`를 raise하면 `run_once`가 `record_outbox_success`로 처리(`service.py:378-384`, success로 terminal move). 테스트 `test_archive_worker_time_not_found_is_idempotent_success`(`test_indexing_phase3a.py:421`)가 `_NotFoundArchiveAdapter`로 이 경로를 pin(succeeded=1, failed=0, log status=success/error=null). ✅
- **#4 fake archive mutation operation.** `ArchiveIndexMutationAdapter.mark_archived(entry)` Protocol + `RecordingArchiveIndexMutationAdapter`(call recording only) 추가. 브리프 §8.3가 "recording-only"를 추천안으로 명시. ✅

### 2. §8 회귀 boundary matrix ↔ 테스트 + 양방향 가드

| §8 회귀 항목 | 테스트 | 가드 방향 | 결과 |
|---|---|---|---|
| claim pending → running | `test_worker_success...`/`test_active...` | 정상 | ✅ |
| stale running(>10min) → reclaimable | `test_stale_running_reclaim...` | under-strict | ✅ |
| non-stale running → not reclaimable | 동상(`non_stale is None`) | over-strict | ✅ |
| stale reclaim가 attempt_count 미소비 | 동상(`stale.attempt_count==0`) | 정합 | ✅ |
| backend_error 1min→5min→failed | `test_backend_error...`(`requeued 1/1/0`, `next_attempt_at` 60s/300s, logs `[1,2,3]`) | schedule + terminal | ✅ |
| archive worker-time not_found → idempotent success | `test_archive_worker_time_not_found...` | 정상(주입 adapter) | ✅ |
| success → terminal success | `test_worker_success...` | 정상 | ✅ |
| terminal → reenqueue new `sync_request_id` | 동상(`index-sync-request-2`) + live check 4 | option B 핵심 | ✅ |
| active(pending/running) → reenqueue same | `test_active_pending_or_running...` | over-strict(dedup) | ✅ |
| index_sync_logs append by `sync_request_id` | 전 worker 테스트 + live check 1/2 | join | ✅ |

- backoff 상수 `INDEX_SYNC_BACKOFF_SECONDS=(60,300)`(`service.py:37`)와 `_backoff_seconds`(attempt_count 1→60, 2→300)가 §4 schedule과 일치. ✅
- claim 순서 `_claim_sort_key=(next_attempt_at or datetime.min UTC, sync_request_id)`가 §7("next_attempt_at asc, null=최소, 동점 sync_request_id")와 일치. ✅
- `entries_requeued`가 `entry.attempt_count + 1 < max_attempts`로 claimed entry 데이터에서 직접 도출(`run_once:386`), repository 내부 구조 비의존(오너가 명시한 항목). ✅

### 3. Mongo 구현 — atomic claim / terminal-move / timestamp 정규화

- `claim_next_outbox_entry`(`mongo_repository.py:118-153`)가 `find_one_and_update` atomic 연산, `$or`(pending-with-due-next_attempt OR running-stale-claimed) filter, `(next_attempt_at, sync_request_id)` sort, `ReturnDocument.AFTER`. 동시 one-shot overlap 시 같은 entry 중복 claim 방지 구조. ✅ §7 atomic claim 요건 충족.
- `record_outbox_success`/terminal `record_outbox_failure`가 `delete_one`로 active outbox 제거(option B); non-terminal failure는 `update_one`(pending, attempt_count, next_attempt_at=backoff, claimed_at=None, last_error). ✅
- `_to_utc_datetime`(`:308-313`)가 Mongo read-back datetime을 timezone-aware UTC로 정규화(naive면 UTC 부여, aware면 astimezone UTC). 오너가 명시한 "Mongo read-back timestamp를 timezone-aware UTC로 정규화" 확인. ✅
- claim용 index가 `claimed_at` 포함로 갱신돼 claim query를 지원. ✅

### 4. 작업자 주장 카운트 재현 + hygiene

- `py_compile`(7 파일) → OK. `git diff --check` → clean.
- focused(`test_indexing_phase3a test_index_sync_worker_script test_indexing_mongo_indexes`) → 27 OK.
- full `discover` → `Ran 407 tests … OK (skipped=40)` — 작업자 주장 "407 OK, skipped=40" 정확 재현.

### 5. live Mongo worker lifecycle 독립 재현 (suite엔 live worker test가 없어 검증자가 직접 수행)

throwaway `mongo:7`(27033, standalone)에서 4경로 실행:
```
PASS 1 success: outbox emptied, 1 success log
PASS 2 backoff/terminal: 60s->300s->failed, logs [1,2,3]
PASS 3 stale reclaim: non-stale None, stale reclaimed with attempt_count 0
PASS 4 terminal->reenqueue: new sync_request_id
ALL LIVE WORKER CHECKS PASSED
```
- success 경로: claim→mark_archived(recording)→`record_outbox_success` → outbox doc 제거, logs 1건 success. ✅
- backoff/terminal: failing adapter로 3회 `run_once`(`now` 60s/300s 진전) → attempt마다 `next_attempt_at` 60s/300s, requeued 1/1/0, 3회째 terminal(outbox 제거), logs attempt `[1,2,3]` 모두 failed. ✅
- stale reclaim: claim(running) → `now+timeout-1` 재claim=None(non-stale) → `now+timeout+1` 재claim=회수(attempt_count 0 유지). ✅
- terminal→reenqueue: success(terminal move) 후 같은 key 재enqueue → 새 `sync_request_id`. ✅ (option B end-to-end 입증)

## Issues / Risks

> 본 slice의 §8 계약 대상으로는 결함이 없다. 아래는 문서 일관성·커버리지·DRY 관찰.

1. **[문서 불일치, 코드 정합] 브리프 §5 + Owner 결정 line 13이 stale.** §5 표 option B(line 79)·채택(line 82)·Owner line 13은 "`not_found`도 3회"라고 한다. 그러나 §8.2(line 171-173)·Owner line 16·§8 회귀(line 212)·코드(`_process_entry`→`DerivedIndexRecordNotFound`→`record_outbox_success`)·테스트·SoT v1.6.29·mongo_collections은 모두 "archive worker-time `not_found` = idempotent success"다. **코드/테스트/§8/SoT가 올바르고, 브리프 §5·line 13만 미갱신.** §5 단독 독자는 worker not_found를 3회 retry로 오독한다. CLAUDE.md(내부 계약 모순 surface)에 따라 명시. 권고: §5·line 13을 "query-time not_found = 3회(후속 selector), archive worker-time not_found = idempotent success(본 slice)"로 정정. 비블로킹(코드 정합).
2. **[커버리지, 검증자가 독립 보완] suite에 live Mongo worker test가 없다.** `IndexSyncWorker`/`claim_next_outbox_entry`/`record_outbox_*`는 `test_indexing_mongo.py`(live)가 아닌 `test_indexing_phase3a.py`(in-memory)·`test_index_sync_worker_script.py`(CLI faked)에만 등장. Mongo worker lifecycle(`find_one_and_update` nested `$or`+sort, `delete_one`/`update_one`, BSON Date round-trip)의 live 경로가 회귀로 잠기지 않는다. 검증자가 throwaway mongo로 4경로를 직접 통과시켰으나(one-off), CI 지속 보장을 위해 `test_indexing_mongo.py`의 skip-aware pattern을 따라 live worker smoke 추가 권장.
3. **[DRY, minor] `(60, 300)` backoff literal 중복.** `service.py:37`은 `INDEX_SYNC_BACKOFF_SECONDS=(60,300)` 상수를 쓰나, `mongo_repository.py:364`는 별도 `backoff_seconds = (60, 300)` literal을 둔다. 한쪽만 바뀌면 diverge. minor(circular import 회피 의도일 수 있으나 유지 보수 위험).
4. **[future/관찰] not_found idempotent-success 분기는 주입 adapter로만 닿는다.** 기본 `RecordingArchiveIndexMutationAdapter`는 `DerivedIndexRecordNotFound`를 raise하지 않으므로 production CLI worker는 이 분기에 닿지 않고 항상 mark_archived success로 종료된다(fake 단계에선 적절). real Chroma adapter 도입 시 대상 부재에 `DerivedIndexRecordNotFound`를 raise해야 idempotent success가 작동한다(§8.2에 계약은 있음). real adapter 책임으로 인지 항목.
5. **[문서 정밀도, minor] §8 회귀 line 211(query-time `not_found` retry, 같은 budget)은 본 slice에 검증 불가.** query selector가 없어 회귀를 둘 수 없다. "query selector slice에서 회귀 추가"로 한정 표기 권장.

## Verdict

**합격(PASS)** — commit `2fcce00` Phase 3B worker/retry 구현 slice.

load-bearing 사유:
- §8 수용 기준 6항 + 회귀 10항이 전부 구현됐고, 각 항이 명명된 회귀 테스트에 추적되며, claim timeout(backoff·stale reclaim)·dedup(active vs terminal)·backoff schedule의 양방향 가드가 갖춰졌다.
- 직전 검증 Issues #1(terminal 이동 B)·#2(claimed_at lease)·#3(not_found idempotent success)·#4(fake adapter op)가 코드·테스트·SoT v1.6.29·mongo_collections §39A에 일관되게 해소됐다.
- 작업자 주장 카운트(full 407·40skip) 독립 재현; `py_compile`·`git diff --check` clean.
- **live Mongo worker lifecycle 4경로를 throwaway mongo:7에서 독립 통과시켰다**(success / backoff-terminal / stale-reclaim / terminal-reenqueue). 이 경로는 suite에 live test가 없어 검증자가 직접 입증.

위 Issues/Risks는 (1) 브리프 §5/line 13 stale(코드는 정합), (2) live worker test 부재(검증자가 one-off로 보완, CI용 smoke 추가 권장), (3) backoff literal DRY, (4) real adapter not_found 책임(future), (5) §8 회귀 정밀도로, 본 slice 코드 결함이 아니다. 가장 실질적인 두 항목은 #1(브리프 §5 정정)과 #2(live worker smoke 추가)이다.

## Outstanding items

- 본 slice는 commit `2fcce00`로 HEAD 반영, working tree clean. `git push` 여부는 owner 결정(`git status` "ahead of origin/main by N commits").
- 권장 후속(비블로킹): (a) 브리프 §5·line 13을 worker-time/query-time not_found 분리로 정정(Issues #1); (b) `test_indexing_mongo.py`에 skip-aware live worker smoke 추가(Issues #2); (c) backoff literal 상수 공유(Issues #3).
- **Follow-up(보강 완료, 2026-07-03)**: 위 권장 후속 (a)·(b)는 검증 직후 보강 slice로 폐쇄했다 — 브리프 §5·Owner line 13·§8 회귀의 `not_found` 문구를 query-time(3회)/archive worker-time(idempotent success)으로 정정(Issues #1 해소), `tests/test_indexing_mongo.py::MongoIndexSyncWorkerSmokeTests` 4개(success terminal-move / backend_error 1분→5분→terminal / stale running reclaim `attempt_count` 미소비 / terminal→reenqueue)를 추가해 Mongo worker lifecycle live 회귀를 잠갔다(Issues #2 해소, throwaway mongo:7에서 live 7개 통과). (c) backoff literal 공유는 여전 미처리(비블로킹).
- 브리프 §명시적 후속 + HANDOFF Next Task: actual ChromaDB/Elasticsearch mutation(tombstone/status update, real adapter의 `DerivedIndexRecordNotFound` 책임 포함), `index_sync_logs` attempt append/read surface 확장, UI-triggered background/daemon lifecycle, stale-hit sync job, `analysis_completed` wiring, `draft_saved` 자동 색인.

## Reproduction

```bash
# 상태/코드/계약
git log --oneline -3                         # 2fcce00 (HEAD)
git show --stat 2fcce00
git diff 9ac59c3..2fcce00 -- docs/system-contract-sot.md docs/mongo_collections.md
git status                                   # clean

# compile + 회귀
python3 -m py_compile services/application/app/indexing/models.py \
  services/application/app/indexing/service.py services/application/app/indexing/mongo_repository.py \
  scripts/index_sync_worker.py tests/test_indexing_phase3a.py \
  tests/test_index_sync_worker_script.py tests/test_indexing_mongo_indexes.py
python3 -m unittest tests.test_indexing_phase3a tests.test_index_sync_worker_script tests.test_indexing_mongo_indexes  # 27
python3 -m unittest discover tests                                                            # 407 / skipped=40
git diff --check

# live Mongo worker lifecycle (검증자 재현 — throwaway mongo:7)
docker run --rm -d --name iso-worker-verify -p 27033:27017 mongo:7
# (wait ping) then:
PYTHONPATH="<repo root>" python3 - <<'PY'  # success/backoff/stale-reclaim/terminal-reenqueue 4경로
... (본 검증의 /tmp/worker_live_check.py 내용 — repo.get_outbox_entry_by_dedup_key read-back로 tz-aware 비교)
PY
docker stop iso-worker-verify

# 브리프 §5 stale 확인 (Issues #1)
grep -n "3회 시도한다\|모두 3회\|idempotent success" docs/plans/03-index-worker-retry-decisions.md
```
