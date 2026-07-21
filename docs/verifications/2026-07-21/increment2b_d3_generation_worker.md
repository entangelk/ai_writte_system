# 검증 기록 — 비동기 생성 + 결과 패드 슬라이스 증분 2b (D3=B, 생성 worker 실행 루프) + 2a hardening

## Subject metadata

- **날짜**: 2026-07-21
- **요청자**: 오너 ("작업 AI가 작업한거 확인해서 검증해줄래? 2개인가 3개 커밋 앞일꺼야")
- **검증자**: 독립 검증 AI (Claude)
- **대상**: b2e8303(2a 기준) 이후 3커밋 — **9f012fe**(증분 2b 본체, D3=B worker 실행 루프, SoT v1.7.26)·**6c098ba**(2a 검증 H-1 hardening 반영)·**5b6ba87**(trivial 2줄). 핵심 검증 = 2b(worker 최초 LLM/gateway 호출).
- **정본 계약 참조**: 브리프 `plans/async-generation-pad-decisions.md` D3=B(worker+독립 job claim, 색인 outbox 무관). SoT v1.7.25→**v1.7.26**(§261 scratch 용도 확장 + 신규 worker/job 계약 조항). 선례 `index_sync_worker.py`(graceful shutdown·--loop)·`indexing/mongo_repository.claim_next_outbox_entry`(atomic claim, 2a 검증).
- **작업 출처**: commit 9f012fe(HEAD~1) + 6c098ba. `git show --stat 9f012fe` = 10 files(+808): 신규 `writing/generation_worker.py`(122)·`scripts/generation_job_worker.py`(174)·테스트 2(+337) + main.py(+73)·generation_job.py(+11)·docker-compose(+53)·SoT(+7)·HANDOFF/work_log.

## Scope

브리프 D3=B 적합·2a 검증 hardening(H-1 provenance·H-2 catch-all·H-3 reclaim) 반영 정확성·실행 파이프라인이 동기 generate와 동치인지·ProviderError TIMEOUT 분기·worker 루프/CLI/gateway 게이팅·main 팩토리(create_app 무변)·compose 서비스·SoT v1.7.26 내부 일관성·회귀 양방향·suite 재도출·**catch-all 커버리지 경계**(핵심 의심).

## Methodology

- 3커밋 `git show --stat`/`git show` 로 범위·코드 회수.
- `generation_worker.py`·`generation_job_worker.py` 전문 독해 + `index_sync_worker.py` run_loop 예외 처리 대조(선례 일치).
- taxonomy 현재 상태·9f012fe generation_job.py 증분으로 H-1/H-2 클로저 확인.
- catch-all 커버리지: execute_generation_job 의 try 블록 범위(70-107) vs scratch/mark 위치(109-122) + run_loop(130)·main(164) 예외 처리 부재 확인.
- SoT v1.7.26 diff 전문 독해 + §261/§265/신규 worker 조항 상호 일관성 검토.
- compose: `stop_grace_period`/`restart`/env/depends_on 확인.
- suite: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider`.

## Findings

### 1. 2a 검증 hardening 5개 전부 반영 — 확인

작업자가 **이전 두 검역(증분1·2a)에서 건넨 hardening을 전부 코드와 SoT에 반영**했다:
- **증분2a H-1(taxonomy provenance)**: docstring 재작성(generation_job.py:54-65) — "classify into a job reason, **not an HTTP status** (produces no HTTP response), so **no status codes are implied**" + "timeout split follows the writing endpoints' convention (generate 자체는 collapse하지만 worker는 구분해 pad가 구분)". "(504)" 모호성 제거. ✓
- **증분2a H-2(catch-all)**: `INTERNAL = "internal"` reason 추가(generation_job.py:88) + worker 최외곽 `except Exception → INTERNAL`(generation_worker.py:106-107). ✓
- **증분2a H-3(reclaim 멱등)**: scratch.save **전** `clear_accepted_item(request_id)`(generation_worker.py:111)로 2a per-request delete 재사용 — reclaim 시 선행 scratch를 지우고 새로 써 최대 1개. ✓
- **증분1 H-1(§262 용도 긴장)**: SoT §261(line 263) scratch 용도를 "(1) 복구 (2) 비동기 생성 결과 보관"으로 확장 → v1.7.25 당시 §262(복구 전용) vs §265(pad rationale) 표면적 긴장 해소. ✓
- **증분1 H-2(version_id None 정밀도)**: SoT §267(line 267) "HTTP generate 경로는 current_position이 있을 때만 저장하고 ContextPositionBody.version_id가 필수 문자열이므로 항상 실값; None은 legacy/직접호출자용 seam"으로 정밀화. ✓

### 2. 실행 파이프라인 = 동기 generate와 동치 — 확인

`execute_generation_job`(generation_worker.py:63-122):
- ContextSearchRequest(71-79): purpose=WRITING_CONTEXT·needs=c.needs·query=job.query or instruction·current_position=(draft_id,version_id)·max_tokens=job.max_tokens — generate endpoint의 search_request와 동형. ✓
- WritingRequest(82-88): job.request_id·project_id·task_type·instruction·draft_excerpt. **intent/next_unit 생략 = 정확**(WritingGenerateRequest에 intent 필드 자체가 없고 generate도 기본값 사용 — 증분2a 검증에서 확인한 대로). ✓
- scratch.save(112-121): version_id=job.version_id 포함(D7). mark_succeeded(result_scratch_id=entry.id). ✓

### 3. 실패 분류 taxonomy — 완전 + 양방향

generation_worker.py:92-107이 7 mapped 예외 + catch-all를 정확 매핑:
- WritingError/InvalidContextSearchRequest→INVALID_REQUEST·InvalidCandidateReport→INVALID_REPORT·ContextSearchBudgetExceeded→CONTEXT_BUDGET_EXCEEDED·ContextSearchFailed→CONTEXT_SEARCH_FAILED·ProviderError→(`exc.code is ProviderErrorCode.TIMEOUT`)?PROVIDER_TIMEOUT:PROVIDER_ERROR·Exception→INTERNAL.
- ProviderError TIMEOUT split **양방향 테스트**(test_writing_generation_worker.py:117-129: TIMEOUT→PROVIDER_TIMEOUT, OVERLOADED→PROVIDER_ERROR). ✓
- catch-all INTERNAL 테스트(:160-165: ValueError→INTERNAL). ✓

### 4. worker 루프/CLI/gateway 게이팅 — index_sync 선례 미러

- `_GracefulShutdown`(87-104)·`run_loop`(107-138)·JSON 이벤트·주입 seam — `index_sync_worker.py` 패턴 동형. ✓
- gateway 미설정→`build_async_generation_collaborators` None→rc=2 + "LLM_GATEWAY_BASE_URL" 안내(:127-132 테스트). ✓
- run_pass(71-84): claim→execute 1건, None 시 idle. ✓

### 5. main.py 팩토리 — create_app 무변

`build_async_generation_collaborators()`(main.py:1436-1471)가 create_app의 같은 env 팩토리 재사용(writing/context_search/scratch), gateway 부재 시 None. `_default_writing_generation_job_service()`(:437-461)는 scratch 선례 동형(in-memory 기본 + CORE_SOT_MONGO_URI 시 Mongo upgrade + `WRITING_GENERATION_CLAIM_TIMEOUT_SECONDS`). **create_app 본체 무변**(팩토리는 별도). ✓

### 6. compose generation_worker — 확인

- application과 같은 이미지/Dockerfile·같은 gateway+context env(Mongo/Chroma/ES/embedding)·같은 scratch cap(패드 저장소 공유). ✓
- `restart: unless-stopped`(crash 시 compose 재시작 = 사실상 resilience). ✓
- `stop_grace_period: 180s`(>91s long 생성, index worker 120s보다 김 — in-flight 생성이 SIGTERM에 완료). ✓
- depends_on: mongo/gateway/embedding/chroma/elasticsearch service_healthy. ✓

### 7. SoT v1.7.26 — 내부 일관

§261 scratch 용도 확장 + 신규 worker/job 계약 조항(line 268): atomic claim·lease(600s)·상태머신·taxonomy 6+internal·draft anchor 필수·enqueue 멱등·H-3 worker 결과 멱등·"worker 실행/claim 실패는 격리되어 다른 job이나 정본 경로를 막지 않는다"·endpoint 배선 2c 명시. §261/§265/신규 조항 상호 모순 없음. async 경로 현재 dormant(generate가 job enqueue 안 함) 명시. ✓

### 8. 회귀 + suite

- 신규 16(실행 executor 10: 성공·실패 매핑 8[7 mapped+INTERNAL]·H-3 reclaim 1 / CLI 6: run_pass·loop drain+sleep 양방향·gateway 게이팅). boundary matrix 빈틈 없음. ✓
- backend **1295 passed / 73 skipped / 326 subtests**(1279 + 16, 독립 재도출 일치). frontend·gen:api 무변. ✓

## Issues / Risks

### Blocking (계약 의무)

**없음.** 동작 결함·계약 모순·추적 안 된 분기 없다. 2a hardening 5개 전부 정확히 클로저. 실행 파이프라인은 동기 generate와 동치, taxonomy 양방향 잠금, H-3 멱등 검증.

### Hardening recommendations (비차단)

- **H-1(2b) — catch-all 커버리지 경계 (핵심 정제)**: H-2 catch-all(`except Exception → INTERNAL`, generation_worker.py:106-107)은 try 블록(70-107, context-build + generate)만 감싼다. **scratch.clear_accepted_item + scratch.save + mark_succeeded(109-122)는 try 밖**이다. 따라서 scratch/mark 단계의 fault는 catch-all에 안 잡혀 전파 → `run_pass`→`run_loop`(scripts/generation_job_worker.py:130)·`main`(:164)에 try/except 없어 **worker 루프가 통째로 crash**(종료 → compose 재시작). 그 job은 RUNNING으로 남아 lease(600s) 만료 후 재claim → **비싼 generate(LLM)를 재실행**.
  - H-2 docstring(generation_job.py:67-72)의 "never livelock RUNNING→reclaim→re-fail"은 **generate 단계에만** 성립한다. scratch-only 지속 실패(좁지만 가능) 시 job이 600s마다 generate를 재실행하며 종료 상태에 못 닿는다.
  - **완화 요인(비차단 근거)**: (1) scratch와 job 저장소가 같은 Mongo(`CORE_SOT_MONGO_URI`)라 보통 같이 죽고, 그럼 mark_failed도 실패해 catch-all 확장이 어차피 못 돕는다; (2) `restart: unless-stopped` + lease가 사실상의 resilience; (3) H-3가 결과 중복 방지; (4) 브리프가 reclaim 재실행을 수용(D3=B). 그래도 H-2 클로저 주장이 docstring보다 좁다.
  - 권고(오너 트레이드오프): (a) scratch/mark를 catch-all 안으로 넣어 scratch-only fault → mark_failed(INTERNAL)(종료; 단 scratch blip에 성공 생성을 잃음), 또는 (b) scratch/mark 단계 fault가 H-2 범위 밖임(crash-and-reclaim에 의존)을 docstring에 명시. 현행은 (b)에 해당하나 서술 누락.

- **(operational) 라이브 스모크 미실행 — worker 최초 LLM/gateway 호출이 단위 테스트만**: 테스트는 전부 `_FakeProvider`. 실 gateway 타임아웃·ProviderError 매핑·compose 기동→claim→gateway 호출→Mongo scratch write 경로가 **end-to-end로 미검증**. async 경로가 2c까지 dormant라 end-to-end는 불가하나, **seeded job으로 worker→gateway→scratch 통합 스모크**를 지금 돌리면 2b의 가장 위험한 표면을 2c 전에 검증 가능. 작업자가 "실 12B 라이브 스모크는 후속"으로 미뤄 둠(정직한 인지). 강력 권고: 2c 착수 전 seeded-job 라이브 스모크 1회.

## Verdict

**합격 (PASS, 조건 없음).**

근거:
1. **2a hardening 5개 전부 정확한 클로저** — H-1 provenance docstring 재작성·H-2 INTERNAL catch-all·H-3 clear-before-save 멱등, 그리고 증분1의 §261 용도 확장·§267 정밀도까지 SoT v1.7.26에 반영. 의심의 의심까지 건넨 것이 다 반영됐다.
2. **실행 파이프라인 동치** — context-build→generate→scratch(D7 version_id)→mark_succeeded가 동기 generate와 정확히 같고, taxonomy가 generate 예외를 빠짐없이 매핑하며 TIMEOUT split 양방향 잠금.
3. **D3=B 핵심 성취** — 별도 worker 서비스·atomic claim·lease·graceful shutdown으로 이중 실행 방지+crash 복구. index_sync 선례 충실 미러, 색인 outbox 무관(H3).
4. **green bar 독립 재도출** — 1295/73/326. create_app 무변, frontend/gen:api 무변.

H-1(2b)은 catch-all 커버리지의 정제(현행 crash-and-reclaim은 작동하고 브리프가 수용하나, docstring의 "never livelock"이 generate 단계에만 해당). 라이브 스모크 미실행은 정직하게 인계된 후속. 어느 것도 합격을 가리지 않는다.

## Outstanding items

- **2b 3커밋 커밋됨**(9f012fe 본체 + 6c098ba hardening + 5b6ba87). green bar·`diff --check` clean(작업 tree clean).

### Post-verification updates (검증 후 해소)

- **★ 라이브 스모크 — 해소(PASS)**: 작업 AI가 검증 직후(5b6ba87 핸드오프 작성 시점) 외부 12B(192.168.1.22:9080)로 seeded-job 스모크를 돌렸다. gateway-backed `execute_generation_job`이 실 한국어 산문 166자 생성 → job succeeded·scratch 1건·`version_id="v-live"` 보존. worker의 최초 gateway generate 호출 + 결과→scratch 배선 + mark_succeeded가 실 12B에서 관통 확인(context search는 stub — Phase 4에서 이미 라이브 검증). 완전 스택 e2e(실 context search + Mongo + compose 서비스)는 endpoint 배선 2c 후 오너 풀스택.
- **H-1(2b) — 해소(적용)**: 오너 지시로 (a) catch-all 확장을 적용했다. `execute_generation_job`의 result-persist 단계(`clear_accepted_item` + `scratch.save`)를 try 블록 안으로 옮겨 최외곽 `except Exception → INTERNAL`이 저장 단계까지 덮도록 했다. 회귀 `test_persist_failure_terminates_job_not_crash` 추가(under-strict). backend **1296 passed**(1295+1). 상세는 `work_log.md` "증분 2b 독립 검증 후 hardening" 태스크.
- **2c(D5)**: generate 2048/4096→enqueue·1024 동기·async+no current_position→400·`GET .../generation-jobs/{id}` 상태 read. 이 flip이 async 경로 개통(현재 dormant).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
git show --stat 9f012fe                                       # 2b 본체 범위
git show 9f012fe -- services/application/app/writing/generation_job.py  # INTERNAL 추가 분
# 실행 코어 + catch-all 커버리지 경계(try 70-107 vs scratch/mark 109-122)
sed -n '63,122p' services/application/app/writing/generation_worker.py
sed -n '107,138p;156,170p' scripts/generation_job_worker.py   # run_loop/main 예외처리 부재
# taxonomy 현재 상태(H-1 provenance + H-2 INTERNAL)
sed -n '53,88p' services/application/app/writing/generation_job.py
# SoT v1.7.26 + compose
git show 9f012fe -- docs/system-contract-sot.md docker-compose.yml
# suite
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider   # 1295 passed/73 skipped/326 subtests
python3 -m pytest tests/test_writing_generation_worker.py tests/test_generation_job_worker.py -q -p no:cacheprovider
```
