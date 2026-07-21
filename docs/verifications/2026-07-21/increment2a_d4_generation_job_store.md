# 검증 기록 — 비동기 생성 + 결과 패드 슬라이스 증분 2a (D4=A 데이터층, 생성 job 저장소)

## Subject metadata

- **날짜**: 2026-07-21
- **요청자**: 오너 ("다음작업 검증해주소. 증분 2a 완료·커밋했습니다")
- **검증자**: 독립 검증 AI (Claude)
- **대상 슬라이스/아티팩트**: 비동기 생성 + 결과 패드 **증분 2a** — 생성 job 저장소(D4=A 데이터층). 신규 `writing/generation_job.py`(상태머신·taxonomy·서비스·atomic claim) + `writing/generation_job_mongo.py`(어댑터). worker 실행 루프(2b)·endpoint 분기(2c)는 제외.
- **정본 계약 참조**: 브리프 `docs/plans/async-generation-pad-decisions.md` D3=B(worker+독립 job claim)·D4=A(job 레코드 분리, 상태 pending/running/succeeded/failed, orphan/retry Analysis 재사용). 선례 `analysis/models.py`·`analysis/service.py`(상태머신)·`indexing/mongo_repository.py::claim_next_outbox_entry`(atomic claim). **SoT 무변**(2a는 endpoint 미배선이라 §261 용도 확장은 2b로 이어짐 — v1.7.25 그대로).
- **작업 출처**: commit **b2e8303**(HEAD). `git show --stat` = 6 files(신규 4 + HANDOFF/work_log doc 2), +934/-1.

## Scope

정본/브리프 적합성(D3=B·D4=A)·선례 일치(Analysis 상태머신 + index-sync atomic claim)·상태머신 전이 강제·claim 원자성·lease 회수(crash RUNNING)·enqueue 멱등(2층)·job 모델 완전성(generate 재현 입력)·실패 taxonomy 완전성·Mongo 어댑터 round-trip·회귀 테스트 양방향·전체 suite green bar 재도출·"기존 코드 무변→회귀 위험 0" 검증.

## Methodology

- `git show --stat b2e8303` 로 변경 파일 한정(신규 only 주장).
- 신규 파일 2개 전문 독해 + 선례 직접 대조(Analysis `_ALLOW_JOB_TRANSITIONS`[service.py:108-111]·`InvalidJobStateTransition`[service.py:68]·`find_job_request`; index-sync `claim_next_outbox_entry`[mongo_repository.py:117-143]).
- generate endpoint except 블록(main.py:3107-3128)을 taxonomy 소스로 삼아 예외→reason 매핑 완전성·정확성 독립 도출.
- ProviderError TIMEOUT 분기의 진짜 출처 확인: `grep ProviderErrorCode.TIMEOUT`(main.py 9곳) → generate endpoint는 **flat 502**, 나머지 writing endpoint(gate/report/revise/accept)만 `504 if TIMEOUT`.
- intent/next_unit 갭 의심: WritingGenerateRequest(main.py:1313-1325) 필드 + generate의 WritingRequest 생성(main.py:3104-) 확인.
- 테스트 재실행: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider`.

## Findings

### 1. "순수 additive / 회귀 위험 0" — 확인

커밋 b2e8303은 **기존 코드 무변**. 변경 = 신규 `generation_job.py`(296)·`generation_job_mongo.py`(157)·`test_writing_generation_job.py`(221)·`test_writing_generation_job_mongo.py`(218) + HANDOFF.md(+3)/work_log.md(+40) doc. main.py·기존 테스트 미건드. → 회귀 위험 0 주장 성립. ✓

### 2. 상태머신 + 전이 강제 (D4=A)

- `WritingGenerationJobStatus`(generation_job.py:46-50): pending/running/succeeded/failed — Analysis `AnalysisJobStatus`(models.py:42-46)과 동일. ✓
- `_ALLOWED_TRANSITIONS`(generation_job.py:119-127): PENDING→RUNNING / RUNNING→{SUCCEEDED, FAILED} **3개**. Analysis는 4개(FAILED→PENDING 포함)이나, **FAILED→PENDING(재시도)은 caller가 없어 의도적 제외**(docstring:114-118, work_log Decisions). callerless dead 전이를 만들지 않겠다는 판단 — CLAUDE.md §2/§4 부합. 재시도 전이는 구동 public 메서드와 함께 재시도 UI 슬라이스에서 추가 예정. crash RUNNING 복구는 전이가 아니라 **claim lease**가 담당(아래 §3). ✓
- `_transition`(generation_job.py:289-296) + `InvalidJobStateTransition`(130)로 금지 전이 강제. mark_succeeded/mark_failed는 모두 `_transition` 경유. ✓

### 3. atomic claim + lease 회수 (D3=B 핵심)

- **Mongo** `claim_next`(generation_job_mongo.py:75-98): `find_one_and_update` + `$or[{status:PENDING}, {status:RUNNING, claimed_at:{$lte: stale_before}}]` + `sort(created_at,_id)` + `ReturnDocument.AFTER` — index-sync `claim_next_outbox_entry`(mongo_repository.py:117-143)과 **충실 동형**. ✓ 문서 수준 원자성으로 동시/replica worker 이중 실행 방지(D3=B).
- **lease 회수 구현 확인**: PENDING뿐 아니라 **lease 만료 RUNNING**도 회수(`claimed_at <= stale_before`). "crash된 RUNNING 복구는 claim lease가 담당" 주장이 코드에 있음. ✓ InMemory(generation_job.py:166-193)도 동일 `_claimable` 논리.
- `DEFAULT_CLAIM_TIMEOUT_SECONDS=600`(generation_job.py:43): long(≈91s)이 여유롭게 들어감. ✓

### 4. enqueue 멱등 (2층)

- 서비스 `find_request`(generation_job.py:227) 선행 체크 + Mongo unique `(project_id,request_id)` 인덱스(generation_job_mongo.py:34-38)가 `add`의 `DuplicateKeyError` 삼킴(53-59)으로 backstop. Analysis `find_job_request` 패턴 미러(키는 project+snapshot+idempotency_key → generation은 project+request_id로 적응; request_id 자체가 멱등키). ✓

### 5. job 모델 완전성 (generate 재현 입력)

- `WritingGenerationJob`(generation_job.py:74-105): task_type·instruction·draft_excerpt·query·output_length·**resolved max_output_tokens**·max_tokens·version_id 적재. "worker가 env를 다시 안 읽어도 자기완결" 주장 성립. ✓
- **draft_id/version_id required**(기본값 없는 frozen dataclass 필드) → 모델 수준에서 async draft anchor 강제. 2c의 endpoint 400(async+no current_position)과 정합. ✓
- **intent/next_unit 갭 없음 확인(의심 해소)**: WritingGenerateRequest(main.py:1313-1325) 자체에 intent 필드가 없고, generate의 WritingRequest 생성(3104-)도 intent/next_unit을 전달하지 않아 기본값(APPEND_CURRENT/None). 따라서 job이 이를 안 실어도 generate 재현에 정합. 2b 가이드의 `WritingRequest(...)` 생략도 올바름. ✓

### 6. 실패 taxonomy (6종) — 완전하나 provenance 정밀도 이슈

- `WritingGenerationJobFailureReason`(generation_job.py:53-71): invalid_request·invalid_report·context_budget_exceeded·context_search_failed·provider_error·provider_timeout.
- **완전성**: generate endpoint except 블록 6종(WritingError·InvalidCandidateReport·InvalidContextSearchRequest·ContextSearchBudgetExceeded·ContextSearchFailed·ProviderError) 전 매핑. ✓ 빈 곳 없음.
- **provenance 부정확(H-1)**: docstring은 taxonomy가 "generate endpoint의 except 블록에서 도출"이며 PROVIDER_TIMEOUT은 "(504)"라 함. 그러나 **generate endpoint는 ProviderError를 항상 502로 매핑**(main.py:3127, 타임아웃 분리 없음). `504 if exc.code is ProviderErrorCode.TIMEOUT` 분기는 gate/report/revise/accept 등 **나머지 writing endpoint의 관행**(main.py 9곳)이지 generate가 아님. 즉 taxonomy의 timeout 분리는 generate가 아니라 타 endpoint 관행에서 온 것이고, "(504)" 표기도 generate 기준이 아님. **매핑 규칙 자체는 정확·완전**(2b가 `exc.code is ProviderErrorCode.TIMEOUT`으로 분기하면 올바름), provenance 서술만 느슨 → 비차단.

### 7. Mongo 어댑터 + fake-collection 테스트

- `_doc`(108-130)/`_entry`(133-157): StrEnum(status·failure_reason) 직렬화·역직렬화 + nullable(claimed_at·failure_detail·result_scratch_id·query) `doc.get` 처리. round-trip 정확. ✓
- 인덱스 3: claim(status,created_at)·by_draft_created·request_unique. 전부 적절. ✓
- fake-collection(`_Collection.find_one_and_update` $or/$lte/sort 구현, test_writing_generation_job_mongo.py:87-95)으로 _doc↔_entry drift + claim 원자성 **로직** 핑(신규 `*_mongo.py` fake round-trip 필수 관행 준수 — memory `mongo-adapter-needs-fake-collection-test`). ✓

### 8. 회귀 테스트 — 양방향 boundary matrix

| 분기 | 테스트(in-memory / mongo) | 방향 |
|---|---|---|
| enqueue 멱등(같은 request) | `test_enqueue_is_idempotent_on_project_and_request` | under-strict(재생성 안 함) |
| 멱등 키에 project 포함 | `test_same_request_id_across_projects_is_not_deduped` | over-strict |
| distinct request → 신규 | `test_distinct_request_id_creates_a_new_job` | over-strict |
| claim oldest-first | `test_claim_moves_oldest_pending_to_running*` | — |
| fresh RUNNING skip(이중실행 방지) | `test_claim_skips_a_fresh_running_job` / `..._skips_fresh_running_but_reclaims_stale` | over-strict |
| stale RUNNING 재claim(crash 복구) | `test_claim_reclaims_a_lease_expired_running_job` / 같은 | under-strict |
| mark_succeeded/failed from RUNNING | `test_mark_*_from_running*` | — |
| PENDING→SUCCEEDED 금지 | `test_mark_succeeded_on_pending_is_rejected` | over-strict(raise) |
| SUCCEEDED→FAILED 금지 | `test_mark_failed_on_a_succeeded_job_is_rejected` | over-strict(raise) |
| unique index 중복 swallow | `test_duplicate_request_is_swallowed_not_raised` | — |
| round-trip(StrEnum+nullable) | `test_round_trip_preserves_all_fields_including_failure_enum` | drift 잠금 |

- claim lease는 under-strict(stale 회수)+over-strict(fresh 스킵) 양방향, 전이는 over-strict(금지 raise)로 잠김. ✓ 신규 22(인메모리 13 + mongo 9) — 주장 일치.

### 9. 전체 suite + 위생

- backend `pytest --ignore=tests/test_memory_mongo.py` → **1279 passed / 73 skipped / 326 subtests**(1257 + 신규 22, 독립 재도출 일치). ✓
- frontend·gen:api 무변(endpoint 미배선, SoT 무변). ✓
- `git diff --check` clean(커밋 메시지 명시). LLM 미사용(데이터층만, gateway 호출 0). ✓
- 2b 착수 가이드(work_log) 정확: `_WRITING_CONTINUE_SCENE_NEEDS`·`current_position=(draft_id,version_id)`·scratch.save(version_id)·§261 개정 시점 전부 generate 경로와 정합. ✓

## Issues / Risks

### Blocking (계약 의무)

**없음.** 동작 결함·추적 안 된 분기·누락된 가드·내부 계약 모순 어느 것도 없다. 상태머신 전이 강제·claim 원자성·lease 회수·enqueue 멱등 전부 구현+양방향 잠금. 기존 코드 무변(회귀 0).

### Hardening recommendations (비차단)

- **H-1(taxonomy provenance, doc-only)**: §6 — docstring이 "generate endpoint에서 도출"+PROVIDER_TIMEOUT "(504)"라 하나, generate는 ProviderError flat 502이고 timeout→504 분리는 타 writing endpoint 관행. 매핑 규칙은 정확하나 provenance가 느슨해 2b 작업자가 오독할 여지(예: "generate는 timeout을 502로 처리하니 job도 PROVIDER_ERROR로 합쳐야 하나?" 혼란). 권고: docstring을 "timeout 분리는 retry 분류를 위한 정제(generate는 flat 502지만 job은 TIMEOUT을 구분해 재시도 가능 transient로 분류)"로 수정. 코드/enum 불변.
- **H-2(2b 착수 플래그 — catch-all reason 부재)**: taxonomy 6종은 generate의 매핑된 예외만 커버. worker 루프가 infra 오류(pymongo·httpx)나 버그(KeyError 등)를 만나면 매핑될 reason이 없다. 2b는 (a) 예상치 못한 예외용 generic reason(예 UNKNOWN/PINFRA) 추가, 또는 (b) 최외곽 catch-all→PROVIDER_ERROR/FAILED 중 하나를 택해야 함. 아니면 예외가 반복 잡히지 않아 job이 lease 만료까지 RUNNING→재claim→재실패 루프(livelock) 위험. **2b 설계 시 결정 필요**(2a 결함 아님).
- **H-3(2b 착수 플래그 — reclaim 재실행)**: crash한 worker가 scratch에 부분 기록 후 죽으면, lease 만료 재claim 시 generate 재실행으로 scratch 항목이 2개 생길 수 있음. scratch per-draft 상한(20)이 수렴시키나, 2b는 인지 필요. 2a 데이터층 결함 아님.
- **(minor doc)** `DEFAULT_CLAIM_TIMEOUT_SECONDS` docstring "env-tunable" — 파라미터는 지금 tunable, env 바인딩은 서비스 조립 시(2b/2c) 추가. 현재 문장은 선취적.

## Verdict

**합격 (PASS, 조건 없음).**

근거:
1. **회귀 0 확인** — 기존 코드 무변, 신규 4파일(코드 2+테스트 2)만. green bar 독립 재도출(1279/73/326).
2. **선례 충실 미러** — 상태머신은 Analysis, atomic claim은 index-sync `claim_next_outbox_entry`와 동형. D3=B(이중 실행 방지)·D4=A(job/scratch 분리) 핵심 계약이 데이터층에 정확히 내장.
3. **양방향 잠금** — claim lease(under+over)·전이(over-strict raise)·멱등(under+over) 전 분기 회귀 커버. fake-collection round-trip으로 Mongo drift까지 핑.
4. **구현자 판단 3종 모두 건전** — async draft anchor required(패드 per-draft에서 강제)·FAILED→PENDING 지연(callerless 전이 회피)·resolved max_output_tokens 적재(worker 자기완결). 전부 work_log에 명시.
5. **지연은 투명** — §261 용도 확장(2b)·endpoint 분기(2c)·재시도 전이(재시도 UI 슬라이스) 전부 handoff에 추적.

H-1은 doc-only provenance 정리, H-2/H-3은 2b(가장 위험한 조각) 착수 시 고려할 플래그. 어느 것도 2a 합격을 가리지 않는다.

## Outstanding items

- **2a 커밋됨**(b2e8303, HEAD). green bar·`diff --check` clean.
- **2b(D3) 추적**: worker 실행 루프 + §261 SoT 용도 확장. work_log "2b 착수 가이드" 상세. **H-2(catch-all reason)·H-3(reclaim 재실행)을 2b 설계에 반영 권장** — 이게 worker 최초 LLM/gateway 호출이라 가장 위험.
- **2c(D5)**: endpoint 2048/4096→enqueue·1024 동기·async+no current_position→400·`GET .../generation-jobs/{id}` 상태 read.
- 권고: H-1(docstring provenance 1줄 정리)은 2a에 이미 커밋됐으나 2b 첫 커밋에 섞어 수정해도 됨(같은 슬라이스 맥락).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
git show --stat b2e8303                                      # 신규 4 + doc 2 만(기존 코드 무변)
# 상태머신·전이·claim·taxonomy 독해
sed -n '46,127p;166,193p;289,296p' services/application/app/writing/generation_job.py
sed -n '75,98p' services/application/app/writing/generation_job_mongo.py
# taxonomy 소스 대조: generate는 ProviderError flat 502
sed -n '3107,3128p' services/application/app/main.py
grep -n "ProviderErrorCode.TIMEOUT" services/application/app/main.py   # 504 분기는 generate 아닌 타 endpoint
# 선례 대조
sed -n '108,111p' services/application/app/analysis/service.py        # Analysis 4전이(FAILED→PENDING 포함)
sed -n '117,143p' services/application/app/indexing/mongo_repository.py  # claim_next_outbox_entry 동형
# suite
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider   # 1279 passed/73 skipped/326 subtests
python3 -m pytest tests/test_writing_generation_job.py tests/test_writing_generation_job_mongo.py -q -p no:cacheprovider
```
