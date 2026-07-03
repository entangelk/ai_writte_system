# Decision brief — Phase 3B index sync worker/retry

상태: `Approved; first one-shot worker slice implemented`
정본 연결: [`../system-contract-sot.md`](../system-contract-sot.md), [`03-indexing.md`](03-indexing.md), [`03-index-sync-outbox-decisions.md`](03-index-sync-outbox-decisions.md)  
목적: `index_sync_outbox`에 쌓인 pending request를 worker가 처리하기 전에, claim, retry, backoff, terminal status, status-aware dedup 규칙을 추측 없이 확정한다.

## Owner decisions — 2026-07-03

- 구현 전에 이 브리프를 먼저 확정하고, 다음 작업자가 장단점과 결정 이유를 그대로 활용할 수 있게 한다.
- Worker 첫 구현은 **B. one-shot worker command**로 시작한다. 장기적으로는 서비스 UI 호출 시 백그라운드에서 도는 worker/daemon 형태가 될 수 있지만, 현재 로컬 1인 runtime에서는 수동·직렬 실행 가능한 command가 가장 작고 충분하다.
- Claim timeout은 **10분**으로 둔다. Docker/Compose가 프로세스를 재시작하더라도 MongoDB에 남은 `running` outbox entry가 자동으로 `pending`으로 돌아오지 않으므로, timeout은 DB 상태 회수를 위한 방어선이다.
- Backoff는 **1분 → 5분 → terminal `failed`**로 둔다. `max_attempts=3`은 기존 Phase 3B archive outbox slice에서 확정된 값을 유지한다.
- `backend_error`는 최대 3회 시도한다. Query-time `not_found`도 후속 LLM orchestration/query selector가 대체 조회 전략을 다시 고르는 loop의 error type으로 같은 3회 budget을 쓴다. 단, archive worker-time `not_found`는 idempotent success로 따로 처리한다(아래 문단 및 §8.2).
- Status-aware dedup은 **active 상태만 dedup**한다. `pending|running` entry가 있으면 기존 entry를 반환하고, `success|failed` terminal entry만 있으면 같은 dedup key라도 새 request 생성을 허용한다.
- Terminal-location/index 전략은 **B. terminal 이동**을 채택한다. `success|failed`가 되면 active outbox entry는 제거되고 terminal attempt/history는 `index_sync_logs`가 소유한다. 따라서 기존 active outbox unique index는 유지한다.
- Archive worker-time `not_found`는 **B. idempotent success**로 처리한다. Archive/tombstone/delete 대상 record가 이미 없으면 목표 상태가 달성된 것으로 본다. Query-time `not_found`는 별도의 query selector/LLM orchestration retry loop error type으로 남긴다.

## 이미 확정된 선행 계약

- Delivery는 외부 queue 없이 Mongo outbox/polling이다.
- 저장 단위는 `index_sync_outbox` + `index_sync_logs` 분리이며, 두 collection은 `sync_request_id`로 조인한다.
- Status literal은 `pending|running|success|failed`다.
- Error type은 `backend_error`와 `not_found`를 분리한다.
- `max_attempts=3`이다.
- 첫 automatic event는 `project_archived`와 `draft_archived`다.
- 실제 ChromaDB/Elasticsearch adapter와 품질/embedding model 선택은 핵심 코어 이후 최후속이다. 이번 worker slice는 fake/backend contract와 persistent lifecycle을 잠그는 데 집중한다.

## 1. 구현 순서

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 결정 브리프 먼저 확정 | 본 문서를 먼저 만들고 구현한다 | 숫자·상태·로그 계약이 검증 가능한 기준으로 남는다 | 구현까지 한 단계 더 걸린다 |
| B. 결정과 구현을 같은 slice에서 처리 | 사용자 답변을 바로 코드로 반영한다 | 빠르다 | 다음 작업자가 왜 그런 숫자인지 추적하기 어렵다 |

채택: **A**. Worker/retry는 상태 전이와 retry 숫자가 public operational behavior가 되므로, 구현 전에 선택지와 tradeoff를 남긴다.

## 2. Worker 실행 형태

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. service function only | repository/service API만 구현한다 | 테스트가 가장 작고 빠르다 | 실제 운영자가 실행할 표면이 없다 |
| B. one-shot worker command | 한 번 실행하면 처리 가능한 entry를 제한 개수만큼 claim/process하고 종료한다 | 로컬 1인 runtime에 맞고, UI/daemon/cron으로 감싸기 쉽다 | 상시 background 처리 자체는 아직 아니다 |
| C. daemon/background worker | process가 계속 돌며 polling한다 | 서비스 UI와 가장 가까운 최종 형태다 | lifecycle, shutdown, compose health, 중복 worker 경쟁 등 결정이 늘어난다 |
| D. Application request 안의 직렬 함수 | UI/API 호출 중 직접 처리한다 | 구현이 작고 동작이 즉시 보인다 | 요청 latency와 derived sync 실패가 다시 결합될 수 있다 |

채택: **B first, C later**. 첫 구현은 one-shot worker command로 한다. 장기적으로 서비스 UI와 결합될 때는 UI/API가 command/service를 trigger하거나 daemon이 같은 service를 재사용한다. Application archive API가 worker를 inline 실행하지는 않는다.

## 3. Claim timeout

Claim timeout 의미: worker가 entry를 `running`으로 claim한 뒤 프로세스가 죽거나 멈췄을 때, 일정 시간이 지난 `running` entry를 다시 claim 가능하게 보는 시간이다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 없음 | `running`은 수동 개입 전까지 계속 running | 구현이 가장 작다 | worker crash 뒤 entry가 영구 고착될 수 있다 |
| B. 5분 | 5분 지난 running entry를 stale claim으로 본다 | 복구가 빠르다 | 느린 adapter가 생기면 중복 처리 위험이 조금 커진다 |
| C. 10분 | 10분 지난 running entry를 stale claim으로 본다 | 로컬 runtime에서 복구와 여유의 균형이 좋다 | crash 복구가 5분보다 느리다 |
| D. 30분 | 30분 지난 running entry만 재claim한다 | 긴 작업에 안전하다 | 실패 복구가 느리다 |

채택: **C. 10분**. Docker/Compose restart는 프로세스만 되살릴 뿐 MongoDB의 `running` 상태를 자동 복구하지 않는다. 따라서 claim timeout은 필요하다.

## 4. Backoff policy

기존 확정값: `max_attempts=3`.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 즉시 재시도 | 실패 후 바로 다음 attempt 가능 | 빠르다 | 같은 transient 오류를 연속으로 때릴 수 있다 |
| B. 고정 1분 | 실패마다 1분 뒤 재시도 | 단순하다 | 두 번째 실패 뒤에도 너무 짧을 수 있다 |
| C. 1분 → 5분 | attempt 1 실패 후 1분, attempt 2 실패 후 5분, attempt 3 실패 후 failed | 작고 현실적인 bounded retry다 | 장기 장애에는 빠르게 terminal이 된다 |
| D. 5분 → 30분 | 더 긴 지수형에 가깝다 | 외부 서비스 장애에 여유가 있다 | 로컬 개발 feedback이 느리다 |

채택: **C. 1분 → 5분 → failed**. 총 3회 시도에 맞춘 가장 작은 bounded backoff다.

## 5. `not_found` retry semantics

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. `backend_error`만 retry, `not_found`는 즉시 failed | 실제 없음은 빠르게 닫힌다 | 단순하다 | 대체 조회/selector가 필요한 case를 너무 빨리 포기한다 |
| B. `backend_error`와 `not_found` 모두 3회 | 두 오류 타입을 분리하되 같은 attempt budget을 쓴다 | 사용자 결정과 맞고 후속 selector loop를 열어 둔다 | 실제 permanent not found도 3회 뒤에야 terminal이다 |
| C. `backend_error` 3회, `not_found` 2회 | 약간 더 보수적이다 | 차이가 애매해진다 |

채택: **B**. `not_found`는 "같은 query를 3번 반복"이 아니라, 후속 LLM orchestration/query selector가 생기면 다른 selector/query strategy를 다시 고르는 loop의 오류 타입으로 본다. 이번 worker slice가 selector를 구현하지 않더라도, error type과 attempt budget은 이 해석을 닫지 않게 둔다.

> 이 절의 retry 정책은 **query-time `not_found`** 에 해당한다. Archive **worker-time `not_found`** 는 §8.2에서 idempotent success로 따로 정한다(archive cleanup 시 대상이 이미 없으면 목표 달성으로 본다). 둘을 같은 "3회"로 읽지 않도록 주의.

## 6. Status-aware dedup

현재 archive outbox 첫 slice의 dedup key는 `(project_id, event, source.mongo_collection, source.mongo_id)`다. Worker가 terminal status를 만들기 전에는 모든 entry가 `pending`이므로 status-aware dedup이 필요 없었다. Worker slice부터는 필요하다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 상태 무관 dedup | 같은 dedup key면 항상 기존 entry 반환 | 가장 단순하다 | terminal 이후 재archive가 새 active request를 만들 수 없다 |
| B. active 상태만 dedup | `pending|running`이면 기존 entry 반환, `success|failed`만 있으면 새 request 허용 | terminal history를 보존하면서 새 active request를 만들 수 있다 | unique index 또는 lookup strategy를 조정해야 한다 |
| C. `failed`만 새 request 허용 | 실패 재처리만 새 request를 만든다 | 성공 중복을 막는다 | archive event 재처리와 status 변화 추적이 애매하다 |

채택: **B**. `index_sync_outbox`는 request lifecycle을 소유하고 `index_sync_logs`는 attempt/result history를 소유한다. Terminal entry가 생긴 뒤에도 같은 archive event를 다시 active request로 만들 수 있어야 한다.

Terminal 이동을 채택했으므로 `index_sync_outbox`의 기존 unique index `{project_id, event, source.mongo_collection, source.mongo_id}`는 유지한다. Terminal `success|failed` 상태가 되면 active outbox entry를 제거하고 `index_sync_logs`에 attempt/result history를 남긴다. 같은 dedup key의 새 archive event는 새 `sync_request_id`를 가진 active outbox entry를 만들 수 있다.

## 7. Claim lease, timestamps, and attempt accounting

Claim timeout 10분을 구현하려면 outbox entry에 claim lease field가 필요하다. 구현자는 아래 schema를 기준으로 삼는다.

### Claim lease fields

- `claimed_at`: nullable timestamp. Worker가 entry를 `running`으로 claim한 시각이다.
- `claim_timeout_seconds`: 첫 구현은 constant `600` seconds로 둔다. Per-entry field로 저장하지 않는다.
- `claimed_by`: nullable string. 첫 one-shot worker에서는 필수 수용 기준은 아니며, 후속 daemon/다중 worker 진단용 후보로 둔다.

### Timestamp type

- Python domain model은 timezone-aware UTC `datetime`을 사용한다.
- MongoDB 저장은 BSON Date로 한다.
- CLI/debug JSON으로 노출할 때만 ISO-8601 string으로 변환한다.
- `next_attempt_at`, `claimed_at`, `started_at`, `finished_at`은 같은 timestamp 정책을 따른다.

### Stale running reclaim accounting

- Claim 시점에는 `attempt_count`를 증가시키지 않는다.
- Attempt가 실제로 실패 결과를 기록할 때 `attempt_count`를 1 증가시킨다.
- Worker crash로 `running` entry가 stale claim이 되면, reclaim 자체는 attempt를 소비하지 않는다.
- Stale reclaim은 `last_error`를 변경하지 않는다. Crash 원인 기록은 후속 observability가 필요해지면 별도 `claim_lost`/heartbeat 계열로 확장한다.
- 이 정책의 tradeoff: crash만 반복되는 경우 attempt budget을 소모하지 않으므로 terminal failure로 자동 수렴하지 않는다. 대신 실제 adapter/backend 결과가 없는 crash를 "실패 attempt"로 오표기하지 않는다.

### Atomic claim

- Claim은 MongoDB `findOneAndUpdate`/equivalent atomic operation으로 구현해야 한다.
- Claim filter는 active claim 조건을 한 번에 포함해야 한다.
- 동시 one-shot command가 겹쳐도 같은 entry가 두 worker에 동시에 claim되면 안 된다.

### Claim order and limit

- `--limit`은 한 번의 one-shot worker command가 claim/process할 최대 entry 수다.
- Claim order는 `next_attempt_at` ascending, then `sync_request_id` ascending이다.
- `next_attempt_at=null`은 즉시 실행 가능하므로 가장 이른 값으로 취급한다.

### `index_sync_logs` minimum fields

Worker slice에서 append할 attempt log는 최소한 아래 field를 가져야 한다.

- `sync_log_id`: repository-generated unique id.
- `sync_request_id`: outbox join key.
- `project_id`
- `event`
- `source`
- `attempt_count`: 이 log가 기록하는 attempt number.
- `status`: `success` or `failed`.
- `error`: 성공 시 null, 실패 시 `{error_type, detail}` object. `error_type`은 `backend_error` or query-time `not_found`를 보존한다.
- `started_at`, `finished_at`: timezone-aware UTC datetime/BSON Date.

## 8. 닫힌 결정과 다음 구현 slice 수용 기준

### 닫힌 결정

1. **Terminal entry location / active-only unique index**

   독립 검증에서 status-aware dedup과 기존 unique index의 충돌 가능성이 확인됐다. 선택지는 아래 둘이었고, 오너 결정으로 B를 채택했다.

   | 선택지 | 설명 | 장점 | 단점 |
   |---|---|---|---|
   | A. partial unique index | `index_sync_outbox`에 terminal entry를 남기고, unique index를 `status in ["pending","running"]` partial unique로 바꾼다 | outbox에서 terminal request 상태를 바로 볼 수 있고, active-only dedup 결정과 문구가 자연스럽다 | 기존 unique index migration이 필요하고, outbox가 active+terminal을 함께 보관한다 |
   | B. terminal 이동 | `success|failed`가 되면 outbox active entry를 제거하거나 terminal-only archive로 이동하고, terminal history는 `index_sync_logs`가 소유한다 | 선행 "outbox=active lifecycle, logs=history" 계약과 가장 잘 맞고 기존 unique index를 유지할 수 있다 | outbox에서 terminal 상태를 직접 조회할 수 없고, terminal summary 조회는 logs를 봐야 한다 |

   채택: **B. terminal 이동**. 선행 저장 단위 결정은 `index_sync_outbox`가 pending/running/failure-retry lifecycle을 소유하고 `index_sync_logs`가 completed or terminal attempt history를 소유한다고 정리했다. 따라서 outbox를 active queue로 유지하고 terminal history를 logs에 남기는 편이 collection 책임이 더 선명하다. 기존 outbox unique index는 유지한다.

2. **Archive worker-time `not_found` 처리**

   Query-time `not_found`는 후속 query selector/LLM orchestration loop에서 대체 조회 전략을 다시 고르는 error type이다. Archive worker-time `not_found`는 다르게 볼 수 있다.

   | 선택지 | 설명 | 장점 | 단점 |
   |---|---|---|---|
   | A. worker-time도 retry | archive 대상 derived record가 없다는 결과도 `not_found`로 3회 retry한다 | 모든 not_found가 같은 retry budget을 쓴다 | 이미 목표 상태가 달성된 archive cleanup을 불필요하게 실패 처리할 수 있다 |
   | B. archive worker-time not_found는 idempotent success | archive/tombstone/delete 대상 record가 이미 없으면 목표 상태 달성으로 보고 success 처리한다 | archive cleanup semantics와 맞고 불필요한 retry를 줄인다 | query-time not_found와 worker-time not_found 의미가 달라진다 |

   채택: **B**. Archive event의 목표는 archived project/draft가 derived index에서 노출되지 않게 하는 것이다. Adapter가 "이미 없음"을 말한다면 archive cleanup 관점에서는 성공에 가깝다. 단, stale-hit/query selector 계층의 `not_found`는 기존 결정대로 retryable selector loop error type으로 남긴다.

3. **Fake archive mutation operation**

   첫 worker는 실제 Chroma/Elasticsearch adapter를 구현하지 않는다. 그래도 fake path가 lifecycle을 검증하려면 archive mutation intent를 기록해야 한다.

   추천: fake adapter는 `mark_archived(source)` 또는 `delete_or_tombstone(source)` equivalent call을 recording-only로 제공한다. 실제 vector record mutation은 하지 않고, worker가 "archive event를 처리했다"는 call과 log/status lifecycle만 검증한다.

다음 code slice는 아래를 최소 수용 기준으로 삼는다.

1. `index_sync_outbox` claim API
   - claim 대상: `pending` with `next_attempt_at is null or <= now`
   - stale claim 대상: `running` with `claimed_at` older than 10 minutes
   - claim 결과는 `running`이고 attempt를 시작할 수 있어야 한다.
2. Retry update API
   - attempt 실패 시 `attempt_count`를 증가시킨다.
   - `attempt_count < max_attempts`면 `status="pending"` + `next_attempt_at`을 1분 또는 5분 뒤로 설정한다.
   - `attempt_count >= max_attempts`면 `status="failed"`로 terminal 처리한다.
   - `last_error.error_type`은 `backend_error` 또는 query-time `not_found`를 보존한다.
3. Success update API
   - 성공 시 `status="success"` attempt log를 남기고 active outbox entry를 제거한다.
4. `index_sync_logs` append
   - 각 attempt 결과를 `sync_request_id`로 append한다.
   - outbox/log는 `sync_request_id`로 조인 가능해야 한다.
5. Status-aware dedup
   - `pending|running` active entry만 dedup 대상으로 본다.
   - 같은 dedup key의 terminal `success|failed`만 있으면 새 `sync_request_id`를 가진 active request를 만들 수 있다.
   - Terminal entry는 outbox에 남기지 않고 `index_sync_logs`가 history를 소유한다.
6. One-shot worker command
   - `--limit` 같은 bounded option을 둔다.
   - 첫 worker는 fake adapter path로 status/log lifecycle을 검증한다.
   - Application archive endpoint 안에서 worker를 inline 실행하지 않는다.
7. 회귀
   - claim pending → running
   - stale running older than 10 minutes → reclaimable
   - non-stale running → not reclaimable
   - stale running reclaim 자체는 attempt_count를 증가시키지 않음
   - `backend_error` retry: attempt 1 failure → 1 minute, attempt 2 failure → 5 minutes, attempt 3 failure → failed
   - query-time `not_found` retry도 같은 attempt budget을 쓰되 error type literal은 `not_found` (후속 query selector slice에서 회귀 추가)
   - archive worker-time `not_found` → idempotent success
   - success → terminal success
   - terminal entry 뒤 재enqueue → new active request
   - active entry 중 재enqueue → same request

## 명시적 후속

- 실제 ChromaDB/Elasticsearch adapter mutation
- UI-triggered background execution 또는 daemon lifecycle
- LLM orchestration/query selector retry strategy
- stale-hit detection에서 sync 요청을 만드는 query/Context Gate wiring
- `analysis_completed` sync event wiring
- `draft_saved` 자동 색인
