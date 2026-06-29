# Phase 2A Job/Task 상태 전이 결정 브리프

상태: `Approved for Phase 2A job-state slice`  
기준 문서: [`system-contract-sot.md`](../system-contract-sot.md), [`02-analysis-pipeline.md`](02-analysis-pipeline.md), [`02-analysis-kickoff-decisions.md`](02-analysis-kickoff-decisions.md)  
승인일: `2026-06-29`  
목적: Phase 2A job/task 상태 전이와 실패 상태 저장을 구현 전에 추측 없이 확정한다. [`02-analysis-kickoff-decisions.md`](02-analysis-kickoff-decisions.md)가 candidate 계약을 닫았고, 본 브리프는 그 위에 job lifecycle을 얹는다.

## 현재 확정된 경계 (변경 없음)

- Phase 2A runner는 동기 실행이며 candidate write는 **job 단위 all-or-nothing**이다(모든 draft가 logical_key/source/schema 검증을 통과한 뒤에만 저장 시작).
- candidate는 `needs_review`로 고정 저장되고 Gate/사용자 승인 없이 canonical이 되지 않는다.
- job 생성 idempotency는 `project_id + snapshot_id + idempotency_key`다.
- candidate retry identity는 `project_id + task_id + logical_key`이고, task 재사용 key는 `project_id + job_id + candidate_type`다.
- `AnalysisTask`는 candidate_type 파티션이며 독립 스케줄 단위가 아니다.

## 승인된 결정

### 1. 상태 입도 — Job-level lifecycle, Task 무상태

결정: 상태는 `AnalysisJob`에만 둔다. `AnalysisTask`는 status 필드를 갖지 않는다.

이유: runner가 job 단위 all-or-nothing이라 한 job 안에서 일부 task만 성공하고 나머지는 실패하는 부분 성공이 존재하지 않는다. task는 candidate_type 파티션일 뿐이므로 독립 lifecycle이 없다. task별 부분 성공/재시도가 필요해지면(예: 유형별 독립 추출) 그때 task 상태를 후속 계약으로 추가한다.

### 2. Job 상태 집합과 전이

결정: job 상태는 4종이다.

| 상태 | 의미 | 종류 |
|---|---|---|
| `pending` | job이 생성됐고 아직 실행되지 않음 | 비terminal |
| `running` | 추출/검증/저장이 진행 중 | 비terminal |
| `succeeded` | 이번 run의 candidate가 모두 저장됨(all-or-nothing 성공) | terminal |
| `failed` | run이 실패했고 candidate가 저장되지 않음(all-or-nothing) | terminal |

허용 전이: `pending → running`, `running → succeeded`, `running → failed`. 그 외 전이는 모두 불법(`InvalidJobStateTransition`).

- `pending`은 향후 in-process/background boundary(외부 queue 미전제)를 위해 둔다. 동기 runner는 생성 즉시 `pending`으로 만들고 실행 진입 시 `running`으로 옮긴 뒤 terminal로 닫는다.
- terminal 상태(`succeeded`/`failed`)는 불변이다. `running`에서만 terminal로 전이한다.

### 3. 실패 job 재시도 — failed는 terminal, 재실행은 새 key

결정: 실패한 job은 terminal로 남는다. 같은 `project_id + snapshot_id + idempotency_key` 재시도는 기존 job(상태 무관)을 **idempotent replay로 그대로 반환**하며 runner는 재실행하지 않는다. 같은 snapshot을 다시 분석하려면 **새 `idempotency_key`로 새 job**을 만든다.

이유: job을 immutable한 idempotency 단위로 유지한다. `failed → running` 재실행을 허용하면 job이 mutable해지고 "같은 key가 같은 결과"라는 idempotency 의미가 흔들린다. 단일 사용자 local MVP에서 재실행은 새 run으로 보는 편이 단순하고, candidate identity가 `task_id`(=job별)로 분리되므로 새 job의 candidate가 기존 것과 충돌하지 않는다.

- runner는 **새로 생성한 job(=`pending`)일 때만** 추출을 실행한다. `find_job_request`가 기존 job을 찾으면(어떤 상태든) replay로 보고 재실행하지 않는다.
- crash 등으로 `pending`/`running`에 멈춘 stale job의 복구는 MVP 범위 밖이다. 본 계약은 replay 시 "기존 job을 그대로 반환"으로 한정하고 자동 복구/재개를 규정하지 않는다.

### 4. 실패 상태 저장 — 닫힌 enum + detail

결정: `failed` job은 닫힌 `failure_reason` enum과 free-text `failure_detail`을 저장한다. runner의 실제 실패 지점에 매핑한다.

| `failure_reason` | 매핑되는 실패 지점 |
|---|---|
| `snapshot_not_found` | Snapshot Loader가 같은 project의 snapshot을 찾지 못함 |
| `source_invalid` | source_ref/anchor 검증 실패(cross-project, span/quote/hash mismatch, anchor 누락 등) |
| `schema_invalid` | candidate payload schema·logical_key·provider content malformed |
| `provider_error` | provider extraction 호출 실패(Gateway `provider_error` umbrella와 정렬) |
| `duplicate_conflict` | candidate 저장이 `DuplicateAnalysisCandidateRequest`로 거절(방어적; 정상 흐름에선 task_id 분리로 도달하기 어려움) |

- `failure_detail`은 사람이 읽는 진단 문자열이며 계약상 형식을 강제하지 않는다.
- `succeeded`/비terminal 상태에서는 `failure_reason`/`failure_detail`이 비어 있어야 한다(설정 시 불법).
- 실패는 성공으로 위장하지 않는다: 실패 시 candidate는 저장되지 않고 job은 `failed`로만 닫힌다.

## 구현 슬라이스 (승인된 순서)

1. `AnalysisJob`에 `status`/`failure_reason`/`failure_detail` 추가 + `AnalysisJobStatus`/`AnalysisJobFailureReason` enum + service 상태 전이(`pending` 생성, `running` 진입, terminal 닫기, 불법 전이 거절).  
   검증: 합법 전이 통과, 불법 전이(`InvalidJobStateTransition`)·terminal 변경·비terminal에서 failure 필드 설정 거절, 양방향 lock.
2. runner 통합: 새 job만 실행(`pending→running→terminal`), 기존 job replay는 재실행 안 함, 실패 지점→`failure_reason` 매핑, all-or-nothing 유지.  
   검증: 정상 run `succeeded`+candidate 저장, 각 실패 지점이 해당 reason으로 `failed`+candidate 미저장, replay가 재실행 안 함.
3. Mongo persistence: job document에 status/failure 필드 round-trip, terminal job replay 재조회.  
   검증: persisted 상태 재구성, transaction/fallback 양 경로(인프라 가용 시), 인프라 없을 때 skip-aware.

## 승인된 결정 요약

- 상태는 job-level만, task는 무상태.
- job 상태는 `pending → running → succeeded|failed`이고 terminal은 불변.
- runner는 새 job(`pending`)만 실행하고 기존 job은 replay로 반환(재실행 없음).
- failed는 terminal이며 재실행은 새 `idempotency_key`(새 job)로 한다.
- 실패는 닫힌 `failure_reason` enum(`snapshot_not_found`, `source_invalid`, `schema_invalid`, `provider_error`, `duplicate_conflict`) + free-text `failure_detail`로 저장한다.
- stale 비terminal job의 자동 복구/재개는 MVP 범위 밖이다.
