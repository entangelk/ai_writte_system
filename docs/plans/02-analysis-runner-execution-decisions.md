# Phase 2A Runner 실행 경계 결정 브리프

상태: `Decision Required`  
기준 문서: [`system-contract-sot.md`](../system-contract-sot.md), [`02-analysis-pipeline.md`](02-analysis-pipeline.md), [`02-analysis-job-state-decisions.md`](02-analysis-job-state-decisions.md)  
작성일: `2026-06-30`  
목적: Phase 2A analysis runner를 Application API/Worker에서 어떻게 시작할지 구현 전에 확정한다. 현재 HTTP API는 job 상태와 candidate 조회만 제공하며 runner 또는 Gateway 호출을 시작하지 않는다.

## 현재 확정된 경계

- Phase 2A runner는 이미 동기 함수형 orchestration으로 구현되어 있다.
- runner는 source validation이 구성된 `AnalysisService`만 받는다.
- runner는 새 job(`pending`)만 실행하고 기존 job은 상태와 무관하게 idempotent replay로 반환한다.
- 실패 job은 terminal이며 같은 snapshot 재분석은 새 `idempotency_key`로 새 job을 만들어야 한다.
- candidate write all-or-nothing은 candidate 저장에 한정된다. job/task setup은 실패 후에도 남을 수 있다.
- Application API의 현재 analysis surface는 다음 3개뿐이다.
  - `POST /projects/{project_id}/analysis/jobs`
  - `GET /projects/{project_id}/analysis/jobs/{job_id}`
  - `GET /projects/{project_id}/analysis/jobs/{job_id}/candidates`
- 위 API는 runner/Gateway 실행을 시작하지 않는 상태/결과 노출 surface다.
- Gateway/tool-call runtime wiring, model tool-call response wire format, domain tool handler는 아직 미확정이다.
- 초기 local/personal runtime은 외부 queue 제품을 전제하지 않고 단순 in-process/background boundary로 시작한다.

## 결정해야 할 질문

### 1. 실행 트리거는 어떤 API가 소유하는가?

선택지:

| 옵션 | 설명 | 장점 | 리스크 |
|---|---|---|---|
| A. 기존 `POST /analysis/jobs`가 생성과 실행을 모두 수행 | job 생성 직후 runner를 동기 실행 | endpoint가 하나라 단순 | 현재 계약의 "상태/결과 노출 API" 의미를 바꾸고, HTTP 요청 시간이 provider latency에 묶임 |
| B. 별도 `POST /analysis/jobs/{job_id}/run` 추가 | job 생성과 실행을 분리 | idempotency 단위가 명확하고 상태 조회 API와 충돌하지 않음 | endpoint가 하나 늘어남 |
| C. Worker-only 내부 entrypoint | HTTP는 job 생성/조회만 하고 worker가 pending job을 실행 | 장기 구조와 맞음 | MVP에서 worker discovery/polling 계약을 먼저 만들어야 함 |

추천: **B**. Phase 2A MVP에서는 `POST /projects/{project_id}/analysis/jobs/{job_id}/run`을 추가해 생성과 실행을 분리한다. HTTP 동기 실행으로 시작하되, 이 endpoint를 나중에 worker enqueue로 바꿀 수 있게 response shape를 job/candidate 결과 중심으로 둔다.

### 2. run endpoint는 동기 실행인가 비동기 enqueue인가?

선택지:

| 옵션 | 설명 | 장점 | 리스크 |
|---|---|---|---|
| A. 동기 실행 후 terminal job 반환 | 요청 안에서 runner 실행 완료 | 외부 queue 없이 구현·검증 가능 | 실모델 latency 동안 요청이 오래 걸림 |
| B. in-process background task로 `pending` 반환 | 요청은 빨리 끝나고 background에서 실행 | UI polling 구조에 가까움 | crash/restart/stale running 복구 계약이 필요해짐 |
| C. 별도 Worker polling/enqueue | production-like | 가장 확장 가능 | queue/claim/stale lease 계약이 필요해 Phase 2A보다 커짐 |

추천: **A**. 초기 local MVP와 현재 runner 계약에 맞춰 동기 실행으로 시작한다. 오래 걸리는 실모델 실행은 후속 Worker slice에서 분리한다.

### 3. run endpoint의 replay 동작은 무엇인가?

추천 계약:

- `POST /analysis/jobs/{job_id}/run`은 해당 job이 `pending`일 때만 runner를 실행한다.
- job이 이미 `succeeded` 또는 `failed`이면 재실행하지 않고 현재 job과 저장된 candidate 목록을 반환한다.
- job이 `running`이면 재실행하지 않고 현재 job과 저장된 candidate 목록을 반환한다. stale `running` 복구는 MVP 범위 밖이다.
- 다른 project의 job 또는 없는 job은 404다.

이유: `02-analysis-job-state-decisions.md`가 이미 "기존 job은 상태 무관 replay, failed 재실행은 새 idempotency_key"로 승인했다. run endpoint도 이 의미를 깨지 않아야 한다.

### 4. provider는 어떤 경계로 주입하는가?

선택지:

| 옵션 | 설명 | 장점 | 리스크 |
|---|---|---|---|
| A. fake/provider adapter를 application main에서 직접 구성 | 가장 빠름 | HTTP app이 provider lifecycle까지 알게 됨 |
| B. runner factory를 Application dependency로 주입 | 테스트에서 fake runner/provider 교체 쉬움 | factory surface를 새로 정의해야 함 |
| C. Worker entrypoint에서만 provider 구성 | API는 실행을 모름 | 이번 slice에서 실행 API를 만들 수 없음 |

추천: **B**. `create_app(..., analysis_runner=...)` 또는 작은 runner factory를 주입받는다. 기본 runtime factory는 아직 fake/no-op으로 두지 말고, 실제 provider wiring 계약이 생길 때 추가한다. 첫 implementation slice는 fake runner를 주입한 API contract test로 닫을 수 있다.

### 5. API response envelope는 무엇인가?

추천 계약:

```json
{
  "job": { "...": "AnalysisJob payload" },
  "candidates": [{ "...": "AnalysisCandidate payload" }],
  "idempotent_replay": false
}
```

- 새 pending job을 실행해 성공하면 `idempotent_replay=false`, job status는 `succeeded`.
- 기존 terminal/nonterminal job을 반환하면 `idempotent_replay=true`.
- runner가 실패하면 job은 `failed`로 저장되고 원본 예외는 HTTP error로 매핑한다. 단 실패 job 조회는 이후 `GET`으로 가능해야 한다.

미결정: runner 실패를 HTTP 몇 번대로 매핑할지. `snapshot_not_found`/`source_invalid`/`schema_invalid`는 400 또는 409 후보, `provider_error`는 502/503 후보, `duplicate_conflict`는 409 후보지만 아직 승인된 public API error envelope가 없다.

### 6. source_ref 생성은 run endpoint가 소유하는가?

추천: **아니오**. Phase 2A extractor output은 이미 `source_anchors`를 요구하며, anchor는 기존 `SourceRef`와 대조된다. run endpoint가 source_ref를 자동 생성하려면 provider quote/span을 source_ref primitive로 바꾸는 별도 계약이 필요하다. 이번 실행 API slice에서는 기존 source_ref가 준비된 fixture/fake runner를 기준으로 한다.

## 추천 최소 slice

사용자 승인 후 다음 순서로 구현한다.

1. `AnalysisRunResult` 또는 동등한 API response helper 추가  
   검증: job payload와 candidate payload가 기존 read API와 동일 literal을 사용한다.
2. `POST /projects/{project_id}/analysis/jobs/{job_id}/run` 추가  
   검증: pending job 실행, succeeded/failed/pending replay 비재실행, missing/cross-project 404.
3. fake runner 주입 기반 API contract test 추가  
   검증: runner 호출 횟수, candidate read-back, failure job 상태 보존, runner/Gateway real wiring 미사용.
4. 실제 provider/Gateway wiring은 별도 slice로 보류  
   선행 결정: provider prompt, Gateway JSON output contract, tool-call wire format 또는 "tool-call 없음" 명시.

## 승인 필요 요약

추천안:

- 실행 트리거는 별도 `POST /projects/{project_id}/analysis/jobs/{job_id}/run`.
- 첫 slice는 동기 실행으로 시작한다.
- 기존 job은 상태와 무관하게 replay하며 재실행하지 않는다.
- run response는 `job`, `candidates`, `idempotent_replay`를 반환한다.
- app은 runner/factory를 dependency로 주입받고, 첫 회귀는 fake runner로 닫는다.
- source_ref 자동 생성과 Gateway runtime wiring은 이번 slice에서 제외한다.
- 실패 HTTP status/error envelope는 별도 결정을 받아야 한다.
