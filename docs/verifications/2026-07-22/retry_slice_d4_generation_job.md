# 검증 기록 — 비동기 생성 job 재시도 endpoint + UI (async-pad D4=A, SoT v1.7.28)

## Subject metadata

- **날짜**: 2026-07-22
- **요청자**: 오너 ("다음작업 검증해줘. 재시도 UI 슬라이스를 완료했습니다." — 명시적 검증 트리거, CLAUDE.md §5)
- **검증자**: 독립 AI 감사자 (작업자와 다른 세션)
- **대상 슬라이스/아티펙트**: 비동기 생성 job 재시도 슬라이스(async-pad D4=A). 백엔드 `services/application/app/writing/generation_job.py`·`main.py` + 프론트 `frontend/src/api/client.ts`·`schema.d.ts`·`writing/useGenerationJobs.{ts,test.ts}`·`GenerationPad.{tsx,test.tsx}`·`drafts/DraftEditor.tsx`·`styles.css` + 테스트 `tests/test_writing_generation_job.py`·`test_writing_generation_job_mongo.py`·`test_writing.py` + `docs/system-contract-sot.md`(v1.7.27→v1.7.28)·`plans/async-generation-pad-decisions.md`·`CHANGELOG.md`·`HANDOFF.md`·`daily_logs/2026-07-22/work_log.md`
- **정본 계약 참조**: [`docs/system-contract-sot.md`](../../system-contract-sot.md) **v1.7.28**(헤더 bump + 버전 로그 + §272 전이 문구 갱신 + §274 신규 retry 절) · [`plans/async-generation-pad-decisions.md`](../../plans/async-generation-pad-decisions.md) **D4=A**("orphan/retry도 Analysis 계약 재사용") + Deferred 절
- **작업 출처**: working tree, **uncommitted**(`git status` — 18개 파일 modified, 커밋 미수행). HEAD = `d45ffc2` (accept dirty guard).

## Scope

정본 계약 읽기 **전**에 스코핑한 계약 표면(이 슬라이스를 govern하는 근원):

1. **retry endpoint 계약 리터럴(SoT §274, v1.7.28)** — `POST .../writing/generation-jobs/{job_id}/retry` → **200 + WritingGenerationJobPayload**; FAILED→PENDING(failure_reason/detail·claim lease clear); worker claim 루프가 자동 재claim(별도 run 호출 없음); **FAILED만 재시도 가능**, 그 외(pending/running/succeeded)는 `InvalidJobStateTransition`→**409**, 미발견·타 프로젝트는 **404**.
2. **전이 규칙(SoT §272 갱신)** — `PENDING→RUNNING`(claim), `RUNNING→{SUCCEEDED,FAILED}`, **`FAILED→PENDING`은 명시 재시도로 retry endpoint가 구동(v1.7.28)**.
3. **Analysis retry 선례 차이** — Analysis는 retry 후 프론트가 별도 `run` POST, 생성 worker는 PENDING 자동 claim(작업자 핵심 설계 주장).
4. **이름 충돌 함정(작업자 강조)** — `InvalidJobStateTransition`이 `analysis/service.py`·`writing/generation_job.py` 양쪽에 별개 클래스로 존재 → writing 것을 별칭으로 catch해야 함(아니면 writing RuntimeError가 500로 샘).
5. **lease clear 충분성** — `mark_pending_for_retry`가 clear하는 필드가 lease를 완전히 해제하는지(`claimed_at` vs `claimed_by`).
6. **gen:api additive** — schema.d.ts에 retry path 추가만 있고 삭제 없는지(non-breaking).
7. **구현 코드 + 회귀 테스트**(backend 10 + frontend 4) + **수치 주장**(backend 1322/73/328, frontend 192/13, tsc, build 398.69 kB, gen:api).

## Methodology

독립 재도출 — 작업자의 work_log/CHANGELOG/SoT 주장을 일차 소스에서 재검증.

1. **계약 스코핑**: SoT v1.7.28 헤더·버전 로그·§272·§274 + brief D4=A를 읽어 boundary matrix 구축(should-fire[200] / should-NOT-fire[409×3, 404×2] + 리터럴).
2. **리터럴 일치(spec↔impl)**: SoT §274 문구 ↔ `generation_job.py`(`_ALLOWED_TRANSITIONS` + `mark_pending_for_retry`)·`main.py`(retry endpoint) ↔ `schema.d.ts` 대조. 전이 규칙 §272 ↔ `_ALLOWED_TRANSITIONS`.
3. **이름 충돁 함정 독립 검증**: `analysis/service.py`·`writing/generation_job.py` 양쪽에 `InvalidJobStateTransition`이 실존하는지, `main.py`가 이미 analysis 것을 import하는지, retry endpoint가 writing 것을 catch하는지.
4. **lease/transition 정확성**: `_transition`의 예외 타입·raise 조건 + claim lease 필드(`claimed_at`만 존재) 확인.
5. **테스트 코드 감사(audit subject)**: backend 10 + frontend 4건이 (a) 계약 실제 고정 (b) under-strict(재claim) (c) over-strict(거절 4종) 양방향 잠금인지. 특히 endpoint 409 parametrized가 이름 충돌 함정을 잠그는지.
6. **수치 재실행(정확한 명령)**: `PYTHONPATH=services/application python3 -m pytest tests/ -q`(전체) + 관련 파일 단독 · `cd frontend && npx vitest run` · `npx tsc --noEmit` · `npm run build` · `npm run gen:api` 후 byte-identical diff.
7. **머신 상태 직접 확인(memory note 준수)**: mongo 실패 발견 시 `docker ps`·포트 도달성·실패 traceback을 직접 보고 "사전 존재/환경" vs "이 슬라이스 회귀" 판별.

## Findings

### 1. Boundary matrix — 전 cell 매핑, 빈 cell 없음 (backend)

| 계약 분기 (SoT §274) | 상태코드 | 코드 구현 | 회귀 테스트 | 방향 |
|---|---|---|---|---|
| FAILED→retry | **200** (PENDING, failure/lease clear, 재claim) | `mark_pending_for_retry` + endpoint 200 | 서비스 `test_retry_resets...`·`test_retried_job_is_reclaimable...` + endpoint `test_retry_failed_resets...` | **under-strict** |
| pending→retry | **409** | `_transition` raise → `InvalidGenerationJobStateTransition` catch | 서비스 `test_retry_on_pending...` + endpoint `test_retry_non_failed_states_are_409`(subtest) | over-strict |
| running→retry | **409** | 동 | 서비스 + endpoint(subtest) | over-strict |
| succeeded→retry | **409** | 동 | 서비스 + endpoint(subtest) | over-strict |
| unknown job→retry | **404** | `job is None` | endpoint `test_retry_404_unknown_job` | over-strict |
| wrong project→retry | **404** | `job.project_id != project_id` | endpoint `test_retry_404_wrong_project` | over-strict |
| mongo failure-field null 보존 | — | `repo.update` round-trip | `test_update_clears_failure_fields_on_retry` | data layer |

- **under-strict 잠금**: 가드/메서드 제거·변경 시 `test_retried_job_is_reclaimable_by_the_worker`(FAILED는 claim 안 됨→retry 후 재claim RUNNING)·endpoint 200 재claim 단정이 re-fail. ✓
- **over-strict 잠금**: pending/running/succeeded 409 + unknown/wrong-project 404 전종 단정. ✓

### 2. 이름 충돌 함정 — 실재 + 해결 + 회귀 잠금 (작업자 핵심 주장 검증)

독립 확인:
- `analysis/service.py:68` `class InvalidJobStateTransition(AnalysisError)` ✓
- `writing/generation_job.py:147` `class InvalidJobStateTransition(RuntimeError)` ✓ — **별개 클래스, 다른 베이스**
- `main.py:37` analysis 것을 이미 import("imported above") → retry endpoint가 이것을 catch했다면 writing `RuntimeError`가 잡히지 않아 **500**으로 샐 것.
- `main.py:140-148` writing 것을 `InvalidJobStateTransition as InvalidGenerationJobStateTransition` 별칭으로 별도 import → `main.py:3339` `except InvalidGenerationJobStateTransition`로 catch해 **409** 매핑.

**함정 잠금**: endpoint `test_retry_non_failed_states_are_409`가 pending/running/succeeded 각각 **409**를 단정. 만약 analysis 것(`AnalysisError`)을 catch했다면 writing `RuntimeError`가 잡히지 않아 **500** → 이 409 단정이 re-fail. 즉 이 테스트가 함정을 잠급니다. 작업자 "회귀가 잠금" 주장 정확. ✓

### 3. 리터럴 일치(spec↔impl) + SoT 자기모순 없음

- SoT §272 "(FAILED,PENDING) 전이" ↔ `generation_job.py:142` `_ALLOWED_TRANSITIONS`에 `(FAILED, PENDING)` 추가 ✓
- SoT §274 "failure_reason/detail·claim lease clear" ↔ `mark_pending_for_retry` `failure_reason=None, failure_detail=None, claimed_at=None`(`:321-323`) ✓
- SoT §274 "200 + WritingGenerationJobPayload" ↔ endpoint `response_model=WritingGenerationJobPayload`·200 ✓
- SoT §274 "그 외 상태는 InvalidJobStateTransition→409" ↔ `_transition` raise(`:333` writing 것) → endpoint 409 ✓
- SoT §274 "미발견·타 프로젝트는 404" ↔ endpoint `job is None or job.project_id != project_id` → 404 ✓
- SoT §274 "별도 run 호출 없다; worker 자동 claim" ↔ retry endpoint에 run 호출 없음 + `claim_next`가 PENDING을 집음(Analysis retry 대비 `run_analysis_job` 별도 endpoint 없음) ✓
- **lease clear 충분성**: lease 필드는 `claimed_at` 하나뿐(`generation_job.py:114`, `claimed_by` 없음) → `claimed_at=None`으로 lease 완전 해제. claimed_by 누락 우려 불필요 ✓
- **SoT 자기모순 없음**: §272 전이 규칙·§274 retry 절·버전 로그 v1.7.28 세 곳이 200/409/404·FAILED-only·clear 항목에서 일관. §272 본문이 "Core SOT 외부"라 하면서 SoT bump한 것은 — 시스템 자체가 Core 외부여도 **retry라는 새 공개 계약(200/409/404)**이 추가됐으므로 SoT에 기록되는 것으로, 기존 GET generation-jobs(§273) 패턴과 동형. 모순 아님.

### 4. Frontend boundary matrix — 전 cell 매핑

| 분기 | 동작 | 테스트 | 방향 |
|---|---|---|---|
| retry failed → pending, 폴링 재개→succeeded | 훅 `retry`(서버 pending으로 교체→active) | 훅 "retry resets...resumes polling to completion"(onSettled 2회) | under-strict |
| retry non-failed → no-op | 훅 `status !== "failed"` 가드 | 훅 "retry is a no-op for a job that is not failed"(/retry 미발화) | over-strict |
| retry POST 실패 → failed 유지 | 훅 catch→return | 훅 "retry leaves the job failed when the retry request fails" | 실패 경로 |
| "다시 시도" 버튼 → onRetryFailed(job_id) | GenerationPad 버튼 | GenerationPad "retries a failed job by id" | UI |

- `client.retryGenerationJob` URL = 백엔드 라우트와 정확 일치(`encodeURIComponent(jobId)`) ✓
- DraftEditor 배선: 훅 `retry`를 `onRetryFailed={(jobId) => void retryGenerationJob(jobId)}`로 연결 ✓

### 5. gen:api additive — byte-identical 재생성

`npm run gen:api` 재실행 후:
- `schema.d.ts`: working tree 추가 변경 **0**(`git diff --stat` 여전히 49 insertions, `/tmp` 백업과 `diff` → **BYTE-IDENTICAL ✓**)
- `openapi.json`: `git diff --stat` 빈 출력 = **무변** ✓
- 신규 path(operation `retry_writing_generation_job_..._post`) 추가만, **삭제 라인 0** → additive·non-breaking ✓
- **schema 409/404 부재는 gap 아님**: analysis retry operation(line 2442)도 responses가 **200+422만**(409/404 없음)이므로 정확히 동형. 프로젝트 관행 = HTTPException error codes는 SoT가 산해계약으로 명시 + 테스트가 잠금, schema는 success envelope + auto 422만. (이 슬라이스의 200 content는 `WritingGenerationJobPayload`로 analysis의 `[key:string]:unknown`보다 오히려 더 정확.)

### 6. 수치 주장 재실행

| 항목 | 작업자 주장 | 독립 재실행 | 일치 |
|---|---|---|---|
| backend | 1322 passed / 73 skipped / 328 subtests | 작업자는 `--ignore=tests/test_memory_mongo.py`로 1322 passed / 73 skipped / 328 subtests. `CORE_SOT_TEST_MONGO_URI=mongodb://localhost:27018`(메모리 전용)로 전체 suite를 돌리면 **1358 passed / 41 skipped / 0 failed / 328 subtests**(mongo 실연동 전부 green). | retry 표면 정확 일치; mongo는 환경 |
| frontend | 192 passed / 13 files | **192 passed / 13 files**(useGenerationJobs 11→14, GenerationPad 5→6) | ✓ |
| tsc | clean | exit 0, 출력 없음 | ✓ |
| build | 103 modules / 398.69 kB | `✓ 103 modules` · `index-*.js 398.69 kB` | ✓ |
| gen:api | additive 49줄 0삭제 | byte-identical 재생성, 49 insertions | ✓ |

retry boundary 자체는 독립 검증 **전부 green**: 서비스+mongo 단독 **28 passed** + endpoint `WritingGenerationJobRetryTest` **4 passed / 3 subtests** + frontend retry **4 passed**.

## Issues / Risks

### Blocking (계약 의무) — 없음

retry 슬라이스 boundary matrix(backend 7 분기 + frontend 4 분기) 전 cell 매핑, 양방향 잠금 확보. 이름 충돌 함정 실재+해결+회귀 잠금 검증. spec↔impl 리터럴 전항 일치, SoT v1.7.28 자기모순 없음. gen:api additive·byte-identical. retry 표면의 수치(프론트·tsc·build·gen:api) 전항 일치. 차단 사유 없음.

### Hardening recommendations (비차단)

1. ~~**DraftEditor 통합 retry-사슬 테스트 부재**~~ → **✅ 검증 후 보강 완료(별도 세션)**: 오너 독립 검증 후 fake-timer 통합 패턴으로 retry 사슬(생성→실패→"다시 시도"→retry POST→폴링 재개→succeeded 결과)을 관통하는 e2e 1건을 추가. frontend 192→193 passed / DraftEditor 38→40. 이로써 훅 단위(3)·GenerationPad 버튼(1)·DraftEditor 배선(1줄)에 더해 전체 사슬의 통합 단정까지 확보.

### 보고 충실성 메모 (정정)

작업자 보고 "backend 1322 passed / 73 skipped / 328 subtests" — work_log에는 `--ignore=tests/test_memory_mongo.py`로 mongo 4건을 **의도적 제외**한 suite임을 정확히 기록. 오너에게 보낸 메시지에만 ignore를 명시하지 않아 "전체 suite green"으로 읽힐 여지가 있었음(본 검증이 초기에 4 FAILED로 포착한 계기). 작업자가 FAILED를 숨긴 것은 아니며, mongo 실패가 본 슬라이스 무관 환경이라 제외한 선택은 합리적.

## Verdict

**합격 (PASS)** — retry 슬라이스 자체.

- retry endpoint 계약(200 FAILED / 409 non-failed / 404 missing·wrong-project) boundary matrix 전 cell 매핑, 양방향 잠금(under-strict=재claim, over-strict=거절 4종).
- 작업자가 강조한 **이름 충돌 함정**(`InvalidJobStateTransition` 양쪽 별개 클래스) 실재 확인 + 별칭 import 해결 정확 + endpoint 409 parametrized 테스트가 함정을 잠금.
- spec↔impl 리터럴 전항 일치, SoT v1.7.28(§272 전이·§274 retry 절·버전 로그) 자기모순 없음, Analysis retry와의 차이(별도 run 없음·worker 자동 claim) 코드로 확인.
- gen:api additive·byte-identical, 프론트 192/tsc/build 수치 일치.
- 비차단 hardening 1건(e2e 통합 테스트)만 보강 후보.

**단, 아래 Outstanding의 백엔드 4 FAILED는 이 슬라이스와 무관한 환경 문제로 판명(이 슬라이스 회귀 아님)하므로 verdict에 영향 없음.**

## Outstanding items

1. **백엔드 `test_memory_mongo` 4건 실패 — 환경(본 슬라이스 무관), 원인 정정**:
   - **정확한 원인**: `test_memory_mongo`가 `CORE_SOT_TEST_MONGO_URI`(기본 `mongodb://localhost:27017`)에 연결하는데, **27017(`shared-mongo`)은 인증 필수**라 `Unauthorized, code=13, "Command insert requires authentication"`로 write(`create_index`)가 거부 → `ensure_indexes()` `OperationFailure` → `MongoMemoryRepositorySetupError`. (초기 추정 "컨테이너 인덱스 충돌"은 오답 — write 자체가 인증으로 막힘.)
   - ping probe는 read라 `skipUnless`를 통과해 skip 대신 FAILED.
   - **27018(`agent-memory-mongodb`, mongo 7.0.30)에서는 green**(4 passed) — 오너 판단 "몽고는 별도 컨테이너라 스킵/실패가 없어야 맞다"가 정확. 27018이 메모리 전용 컨테이너.
   - **이 슬라이스 무관**: `test_memory_mongo.py`·`memory/mongo_repository.py`는 retry diff에 없음; 단독 실행에서도 동일 실패.
   - 작업자는 work_log에 `--ignore=tests/test_memory_mongo.py`로 제외 후 1322 passed를 기록(합리적 — 본 슬라이스 무관 환경). 다만 오너 보고 메시지에는 ignore를 명시하지 않아 "전체 suite green"으로 오해될 여지가 있었음. `CORE_SOT_TEST_MONGO_URI=mongodb://localhost:27018`로 전체 suite를 돌리면 **1358 passed / 41 skipped / 0 failed**(mongo 실연동 전부 green).
2. **커밋 미수행**: 18개 파일 modified(스테이징 안 됨). 작업자 "커밋 대기 중". 오너 승인 대기 — 결함 아님.
3. 본 슬라이스(재시도 UI, D4=A)는 폐쇄. async-pad 잔여 후속(per-draft 상한 dogfood 관찰·실 12B 풀스택 e2e)은 본 검증 범위 밖.

## Reproduction

```bash
# retry boundary 단독 green (서비스 + mongo + endpoint)
PYTHONPATH=services/application python3 -m pytest \
  tests/test_writing_generation_job.py \
  tests/test_writing_generation_job_mongo.py \
  "tests/test_writing.py::WritingGenerationJobRetryTest" -v
# → 28 + 4 passed / 3 subtests

# 백엔드 전체 (27018 메모리 전용 컨테이너로 mongo 실연동 green)
CORE_SOT_TEST_MONGO_URI=mongodb://localhost:27018 PYTHONPATH=services/application python3 -m pytest tests/ -q
# → 1358 passed / 41 skipped / 0 failed / 328 subtests

# 프론트 (192 passed / 13 files) + tsc + build
cd frontend && npx vitest run && npx tsc --noEmit && npm run build

# gen:api byte-identical
cd frontend && cp src/api/schema.d.ts /tmp/before && npm run gen:api && diff /tmp/before src/api/schema.d.ts && echo IDENTICAL
```

이름 충돌 함정 추적(읽기 전용): `analysis/service.py:68` · `writing/generation_job.py:147` · `main.py:37`(analysis import)·`:140-148`(writing 별칭)·`:3339`(catch) · `_transition` `generation_job.py:333` · `mark_pending_for_retry` `:306-325`.
