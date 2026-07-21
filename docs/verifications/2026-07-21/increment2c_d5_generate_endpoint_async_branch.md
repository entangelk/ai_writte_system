# Verification — 증분 2c: generate endpoint 동기/비동기 분기 (D5=A)

## Subject metadata

- **Date**: 2026-07-21
- **Requester**: 오너(entangelk) — "작업 ai가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?" (독립 adversarial 검증 요청)
- **Verifier**: Claude(본 세션, 작업자와 별개)
- **Target slice**: 비동기 생성 + 결과 패드 증분 2c — `POST .../writing/generate`의 `output_length` 동기/비동기 분기 + `GET .../generation-jobs/{job_id}` 상태 read (SoT v1.7.27, D5=A)
- **Canonical spec reference**:
  - `docs/system-contract-sot.md` §271(비동기 생성 job 저장소+worker), §272(endpoint 배선 D5), §508("status는 항상 candidate" 동기 한정), v1.7.27 changelog 행 — 모두 `Approved` v1.7.27
  - `docs/plans/async-generation-pad-decisions.md` §D5(프리셋 기준 분기: 1024=동기, 2048/4096=비동기), Owner decisions(D5=A, 2026-07-20 확정)
- **Source of work being verified**: working tree, uncommitted(`git diff --stat` = 11 files +723/-47, commit 안 함 — 작업자가 "지시 시만 커밋" 명시)

## Scope

정본 계약 범위(§271/§272/D5와 그 cross-reference만 — 외부 rule은 제외):

1. **정본 계약(SoT)**: §271, §272, §508, v1.7.27 changelog 행의 내부 일관성 + §270 라벨.
2. **캐노니컬 플랜**: `async-generation-pad-decisions.md` D5=A endpoint 분기 결정.
3. **구현 코드**: `services/application/app/main.py`(generate endpoint 분기, GET 상태 read, `_writing_generation_job_payload`, create_app wiring), `services/application/app/writing/http_models.py`(신규 3 모델 + `GENERATE_ASYNC_RESPONSES`), `services/application/app/writing/generation_job.py`(저장소 서비스 — 2a이나 2c가 생산자로서 호출).
4. **회귀 테스트**: `tests/test_writing.py::WritingGenerateAsyncBranchTest`(13), `WritingGenerationJobEnvelopeKeyTest`(2), `WritingOutputLengthPresetTest`(2건 재작성).
5. **프론트엔드**: `frontend/src/writing/WritingPanel.tsx`(runGenerate async 가드), `api/client.ts`(union 반환형), `WritingPanel.test.tsx`.
6. **공개 envelope/schema**: `frontend/src/api/schema.d.ts`(gen:api 산출물 — 신규 2 스키마 + generate 202 응답 + GET 응답).
7. **전체 suite**: backend pytest + frontend vitest + tsc.

## Methodology

boundary matrix를 정본 §272/§271/D5에서 먼저 구축한 뒤, 각 cell을 코드·테스트·mutation으로 채움. 작업자 주장을 hypothesis로 취급해 refute 시도.

정확한 명령:
- backend suite: `PYTHONPATH=services python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider`
- 개별 클래스: `PYTHONPATH=services python3 -m pytest tests/test_writing.py::WritingGenerateAsyncBranchTest ... -q -p no:cacheprovider`
- frontend: `cd frontend && npx vitest run` / `npx tsc --noEmit`
- mutation: `cp services/application/app/main.py /tmp/main.py.bak`(백업) → Edit로 mutation → 단일 테스트 실행 → `cp /tmp/main.py.bak services/application/app/main.py`(원복) → `diff -q`로 원복 확인. `generation_job.py`도 동일 패턴.
- OpenAPI 확인: `frontend/src/api/schema.d.ts` 직독(generate path line 730, responses block line 3514-3542).

## Findings

### 1. 정본 계약(§271/§272/§508) — 내부 일관성

- §272(`docs/system-contract-sot.md:272`)가 endpoint 배선의 전체 계약을 서술: short=동기(200+WritingCandidatePayload), medium/long=enqueue+202+`{job, idempotent_replay}`, async+no current_position=400, GET 상태 read(200+WritingGenerationJobPayload; 404 미발견·타 프로젝트), async는 writing/context_search/scratch 미호출 + 동기 전용 503 우회, enqueue `(project_id, request_id)` 멱등. §271이 저장소/worker 계약(status pending/running/succeeded/failed, 멱등키, draft_id/version_id 필수)을 뒷받침. §508이 "status는 항상 candidate"를 **동기 후보 응답 한정**으로 정밀화(비동기는 job). 세 절이 상호 모순 없이 한 흐름을 서술. ✓
- v1.7.27 changelog 행의 행동 서술은 §272와 일치. 단, **수치 불일치 2건** (아래 Issues #1).

### 2. 캐노니컬 플랜 D5=A — 구현 일치

- 플랜 D5(`docs/plans/async-generation-pad-decisions.md:87-95`, 확정 D5=A line 120): "1024=동기, 2048/4096=비동기". 구현(`main.py:3194`)이 `if output_length in (OutputLength.MEDIUM, OutputLength.LONG)`로 정확히 분기. ✓
- 플랜 line 95 부연 "UI에서 프리셋 선택이 곧 동기/비동기 선택임을 사용자에게 드러낸다": async 시 "백그라운드 생성을 시작했습니다" notice로 간접 드러냄. preset selector 라벨에 sync/async 명시는 없으나, notice로 사용자가 백그라운드 전환을 인지하므로 계약 위반 아님(soft).

### 3. 구현 코드 — spec↔code literal 일치

- `main.py:3194-3220`: async 분기. `body.current_position is None` → 400(detail "current_position is required for async presets (output_length medium/long)"); `writing_generation_jobs.enqueue(...)` → `JSONResponse(202, {"job": _writing_generation_job_payload(result.job), "idempotent_replay": result.idempotent_replay})`. 상태코드/envelope shape가 §272 literal과 불일치 없음. ✓
- `main.py:3221-3228`: async 분기가 `if writing is None: 503` / `if context_search is None: 503` **앞**에 위치 → 동기 전용 503 검사를 async가 우회(§272 "동기 전용 503 검사도 우회"). ✓
- `main.py:3201-3213`: enqueue 호출이 `task_type.value`, `output_length.value`, `max_output_tokens=output_tokens`, `max_tokens=body.max_tokens`, `version_id`, `draft_id`, `request_id`를 전달. worker가 이들을 올바르 소비(아래 #7). endpoint는 async 분기에서 `writing.generate`/`context_search.build_context_package`/`writing_scratch.save`를 부르지 않음(전부 sync 분기 3245-3291에 한정). ✓
- `main.py:3293-3310`: GET 상태 read. `_require_project_exists`(404) → `writing_generation_jobs.get(job_id)` → `job is None or job.project_id != project_id` → 404. project-scoped 격리 계약 일치. ✓
- `main.py:3055-3076`: `_writing_generation_job_payload` — 12 필드(`job_id`/`request_id`/`project_id`/`draft_id`/`version_id`/`task_type`/`output_length`/`status`/`created_at`/`result_scratch_id`/`failure_reason`/`failure_detail`). `status`·`failure_reason`은 StrEnum의 `.value`(AnalysisJobPayload 선례 동형 평문 str). terminal 필드는 None until 종료. ✓
- `http_models.py:187-208`: `WritingGenerationJobPayload`(12 필드 exact-width) + `http_models.py:241-247`: `WritingGenerationJobAcceptedPayload`(`{job, idempotent_replay}`) + `http_models.py:277-289`: `GENERATE_ASYNC_RESPONSES={202: {...}}`. ✓
- `main.py:1570`: `writing_generation_job_service or _default_writing_generation_job_service()`. `main.py:439-462` 팩토리가 `CORE_SOT_MONGO_URI`로 in-memory/Mongo 분기. worker(`build_async_generation_collaborators`, `main.py:1472`)도 동일 팩토리 호출 → production에서 양측 같은 Mongo 저장소 공유(producer→worker handoff의 정확성 근거). ✓

### 4. boundary matrix — 빈 cell 없음

모든 §272/§271 계약 필수 분기가 명명된 회귀 테스트에 mapping:

| 분기 | 방향 | 테스트 | mutation 입증 |
|---|---|---|---|
| short→200 sync(후보 생성) | should fire | `test_short_preset_stays_synchronous` | — |
| medium→202+`{job,idempotent_replay=false}` pending | should fire | `test_medium_preset_enqueues_job_and_returns_202` | M2 |
| long→202 | should fire | `test_long_preset_also_enqueues` | — |
| async+no current_position→400 | should fire | `test_async_without_current_position_is_400` | M3 |
| short+no current_position→200(over-strict) | should NOT fire | `test_short_without_current_position_is_not_400` | — |
| 재POST (project_id,request_id)→같은 job, idempotent_replay=true | should fire | `test_async_is_idempotent_on_request_id` | M4(positive는 green 유지) |
| 멱등키=(project_id,request_id) not 단일축(over-strict) | should NOT collapse | `test_async_idempotency_key_is_project_plus_request` | M4 |
| async→writing.generate 미호출 | should NOT fire | `test_medium...`(provider.last_request is None) | M2 |
| async→context_search 미호출(3rd invariant) | should NOT fire | `test_medium...`(context.last_request is None) | — |
| async→scratch 미기록 | should NOT fire | `test_async_does_not_write_scratch_at_endpoint` | M2 |
| async→동기 전용 503 우회 | should NOT fire | `test_async_bypasses_sync_only_503_checks` | M1 |
| GET owner→200+full payload | should fire | `test_get_generation_job_returns_status` | — |
| GET terminal succeeded→result_scratch_id | should fire | `test_get_generation_job_surfaces_terminal_fields` | — |
| GET terminal failed→failure_reason/detail | should fire | `test_get_generation_job_surfaces_terminal_fields` | — |
| GET unknown job_id→404 | should NOT expose | `test_get_generation_job_404_unknown` | — |
| GET wrong project→404 | should NOT expose | `test_get_generation_job_404_wrong_project` | — |
| GET envelope keys exact(12) | literal | `test_get_status_envelope_keys_are_complete` | — |
| 202 envelope keys exact(`{job,idempotent_replay}`+12) | literal | `test_accepted_envelope_keys_are_complete` | — |

**빈 cell 없음.** 모든 계약 필수 분기가 trace됨.

### 5. 양방향 가드 — mutation으로 bite 입증(독립 재현)

작업자 주장 4종을 독립 mutation으로 검증. 각 case: 백업→mutation→단일 테스트 실패 확인→원복(`diff -q`로 identical 확인).

- **M1(503 우회, 작업자가 blocking 폐쇄라고 주장한 항목)**: async 분기 앞으로 `if writing is None: raise 503`를 끌어올림 → `test_async_bypasses_sync_only_503_checks`가 `AssertionError: 503 != 202`로 **re-fail**. under-strict 가드가 bite. ✓ (작업자 주장 독립 입증)
- **M2(async 분기 제거)**: `if output_length in (...)`로 빈 튜플 분기 → medium이 동기로 빠짐 → `test_medium_preset_enqueues_job_and_returns_202`(202≠200) **및** `test_async_does_not_write_scratch_at_endpoint`(동기 경로가 premature candidate "아린은 성문 앞에서 멈췄다."를 scratch에 써 items가 비지 않음) **동시 re-fail**. scratch-미기록 가드도 bite. ✓
- **M3(no-position 400 제거)**: `if False:`로 400 가드 무력화 → current_position=None인 async 요청이 `enqueue`의 `body.current_position.draft_id` 접근에서 `AttributeError: 'NoneType' object has no attribute 'draft_id'` → 500 → `test_async_without_current_position_is_400`가 re-fail. ✓
- **M4(멱등키 project-only 축소)**: `_request_index` 키를 `(project_id, project_id)`로 좁힘 → `test_async_idempotency_key_is_project_plus_request`가 다른 request_id "wr-b"를 replay로 붕괴시켜 `AssertionError: True is not false`로 re-fail. **반면 positive 테스트 `test_async_is_idempotent_on_request_id`는 green 유지**(같은 request_id 재POST는 여전히 replay여야 함). over-strict 가드가 정확히 bite. ✓

### 6. envelope/schema — 공개 표면 일치

- `frontend/src/api/schema.d.ts:3514-3542`: `POST .../writing/generate`의 responses가 200(WritingCandidatePayload)+**202(WritingGenerationJobAcceptedPayload)**+422로 문서화(`responses=GENERATE_ASYNC_RESPONSES`가 gen:api에 반영). ✓
- `schema.d.ts:3544-3564`: GET .../generation-jobs/{job_id}가 200(WritingGenerationJobPayload)+422. ✓
- `schema.d.ts:1552-1559`: 신규 2 스키마 정의 존재. ✓
- `WritingCandidatePayload`(schema.d.ts:1432-1455)에 `job` 필드 **없음** → 프론트 `"job" in produced` 가드가 런타임에 건전한 판별자. ✓

### 7. worker 호환(producer→worker handoff)

- `generation_worker.py:74-110`: worker가 endpoint가 enqueue한 필드를 올바르 소비 — `WritingTaskType(job.task_type)`(str round-trip), `ContextBudget(max_tokens=job.max_tokens)`, `max_output_tokens=job.max_output_tokens`, `CurrentPosition(draft_id=job.draft_id, version_id=job.version_id)`, scratch에 `version_id=job.version_id` stamp. `output_length`는 pad/debug용 status surface 전용(실행엔 미사용, 의도적). ✓
- endpoint(service.enqueue) ↔ worker(claim_next)가 동일 `WritingGenerationJobService` 사용 → shared store로 handoff 건전. 2b worker 테스트가 service-enqueued job 실행을, 2c endpoint 테스트가 enqueue를 각각 입증; seam은 자명(공유 service).

### 8. 전체 suite — 재실행 카운트

- backend: `1311 passed, 73 skipped, 325 subtests passed in 48.05s` (재실행). 작업자 주장(work_log/HANDOFF/요약 "1311")과 일치.
- frontend: `Test Files 11 passed (11) / Tests 163 passed (163)` (재실행). 작업자 주장 일치.
- `npx tsc --noEmit`: exit 0 (clean). union 반환형 narrowing 포함 type-safe.
- `git diff --check`: clean.

## Issues / Risks

### Blocking (contract obligations)

**없음.** boundary matrix의 모든 계약 필수 분기(should fire / should NOT fire / literal)가 명명된 회귀 테스트에 mapping되며, 4종 mutation으로 양방향 가드가 bite함을 입증했다. 정본 내부 모순(§271/§272/§508/changelog 행 간 행동 서술)은 없다. 빈 cell 없음.

### Hardening recommendations (비차단, spec을 넘는 보강)

1. **SoT v1.7.27 changelog 행의 수치 정정(문서 정확성)** — `docs/system-contract-sot.md:36` 행이 "backend **1309 passed**" 및 "신규 15: async 분기 **11** + envelope-key 2 + ..."로 쓰고 있으나, (a) 실제 카운트는 **1311 passed**(재실행 확정)이고 2b baseline 1296 + 신규 15 = 1311이며, (b) async 분기 신규 테스트는 **13**(envelope-key 2와 합쳐 15). work_log/HANDOFF/요약 메시지는 모두 1311·13로 정확. SoT만 "1309"/"11"로 어긋난다. SoT는 정본이므로 수치 정정 권장(행동·계약엔 무영향). → **소거**: "1309"→"1311", "11"→"13".

2. **producer→worker end-to-end 통합 테스트 부재** — endpoint가 enqueue한 job을 worker가 claim해 scratch에 결과를 내는 전체 경로(POST → claim_next → execute → scratch → GET terminal)를 단일 테스트로 잡는 회귀가 없음. 양 절반(2b worker 실행, 2c endpoint enqueue)은 독립 입증됐고 seam은 공유 service로 자명하므로 **비차단**. 증분 3(패드/폴링) 또는 별도 통합 테스트에서 추가 시 유효.

3. **GET "존재 불가 project" 404 미잠금** — GET endpoint가 `_require_project_exists`로 path project가 없으면 404를 내지만(`main.py:3301-3303`), 이 경로를 명시적으로 단정하는 테스트는 없음(unknown job_id·타 프로젝트 job만 cover). 코드는 계약대로 동작하므로 비차단; 인접 케이스로 보강 가능.

4. **payload 모델 `extra='forbid'` 미설정** — `WritingGenerationJobPayload`/`WritingGenerationJobAcceptedPayload`가 extras를 금지하지 않음. 단 `WritingGenerationJobEnvelopeKeyTest`가 `set(body) == _JOB_KEYS`로 **정확한 키 집합**을 pin하므로, extra key가 들어오면 set이 달라 테스트가 bite. 보강 미설정의 영향은 envelope-key 테스트가 상쇄. 비차단.

5. **상태코드 202 = 구현자 판단(오너 확인 대기)** — 작업자가 202를 선택하고 SoT §272/changelog에 반영했으며, "200+response_model 정직성 + responses={202} 문서화 + HTTP 의미론" 근거를 명시했음. 이는 **contract literal(공개 HTTP envelope)**에 대한 구현자 판단이나, 작업자가 침묵하지 않고 상세 근거를 남기고 **명시적으로 오너 확인을 요청**함("오너가 200을 선호하시면 status code + responses={}만 바꾸면 되는 국소 변경 — 검증 때 말씀해주시면 반영"). §508의 "status는 항상 candidate"를 동기 한정으로 정밀화한 것도 같은 맥락의 계약 모순 해소(job은 candidate가 아님). 결함이 아니라 **오너 결정 대기 항목**(아래 Outstanding items).

## Verdict

**PASS (조건 없음).**

이유(load-bearing):
- boundary matrix의 모든 계약 필수 분기가 명명된 회귀 테스트에 mapping(빈 cell 없음).
- 4종 mutation(M1 503 우회 / M2 async 분기 제거 / M3 no-position 400 제거 / M4 멱등키 축소)으로 under-strict·over-strict 양방향 가드가 bite함을 독립 입증. 작업자가 "blocking 1건(async 503-우회 회귀 부재) 폐쇄"라고 주장한 항목(M1)을 포함해 전부 재현.
- spec↔code literal 일치(202/400/404/envelope 키/status 평문 str), 정본 내부 모순 없음.
- backend 1311 passed/73 skipped/325 subtests, frontend 163/11, tsc clean — 전부 재실행으로 확정(작업자 주장과 일치; SoT 행의 "1309"는 오타).
- producer→worker handoff 건전(공유 service + worker의 필드 소비 정확).

오너가 결정해야 할 유일한 항목은 상태코드 202(구현자 판단, 오너 확인 대기 — 작업자가 이미 요청함)이며, 이는 검증 verdict가 아닌 오너 결정 사안이다. 202를 유지하든 200으로 바꾸든(국소 변경) 구현은 정본과 일치하는 상태다.

## Outstanding items

1. **오너 결정 대기 — 상태코드 202 vs 200**: 작업자가 202를 구현자 판단으로 선택·문서화하고 오너 확인을 요청한 상태. 오너가 202를 승인하면 그대로, 200을 선호하면 `main.py:3214` status_code + `GENERATE_ASYNC_RESPONSES` 키만 국소 변경(작업자가 명시한 대로). 이 결정은 async 결과를 "candidate가 아닌 job"으로 다루는 §508 정밀화와도 연관.
2. **커밋 미수행**: 11개 파일 working tree에 uncommitted. 오너 지시 시 커밋(작업자가 명시적으로 "지시 시만 커밋"으로 봉인).
3. **비차단 hardening #1(SoT 수치 정정)**: 오너가 SoT 정본의 수치 정확성을 원하면 "1309→1311", "11→13" 정정. 작업자가 반영 가능.
4. **다음 증분**: 증분 3(읽기 전용 패드 + 완료 배지 + 생성 중 5초 폴링). 2c가 깔아둔 GET 상태 read를 소비.

## Reproduction

```bash
# 전체 backend suite (카운트 재확정)
PYTHONPATH=services python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider
# → 1311 passed, 73 skipped, 325 subtests

# 2c 대상 클래스만
PYTHONPATH=services python3 -m pytest \
  tests/test_writing.py::WritingGenerateAsyncBranchTest \
  tests/test_writing.py::WritingGenerationJobEnvelopeKeyTest \
  tests/test_writing.py::WritingOutputLengthPresetTest -q -p no:cacheprovider
# → 24 passed, 6 subtests

# frontend
cd frontend && npx vitest run        # → 163 passed / 11 files
cd frontend && npx tsc --noEmit      # → exit 0

# mutation M1(503 우회) 예시 — 백업→mutation→re-fail→원복
cp services/application/app/main.py /tmp/main.py.bak
# (Edit: async 분기 앞에 `if writing is None: raise HTTPException(503, ...)` 삽입)
PYTHONPATH=services python3 -m pytest \
  tests/test_writing.py::WritingGenerateAsyncBranchTest::test_async_bypasses_sync_only_503_checks \
  -q -p no:cacheprovider   # → FAILED: 503 != 202
cp /tmp/main.py.bak services/application/app/main.py   # 원복
diff -q services/application/app/main.py /tmp/main.py.bak   # → identical
```

## Post-verification resolution (2026-07-21, 작업자)

오너가 "검증기록 확인해서 보강할 부분 보강하고 커밋까지 해줘"로 지시한 후 작업자가 반영한 사항(위 Findings/Verdict는 검증 시점 스냅샷으로 보존):

- **Outstanding #1 / record hardening #5 (상태코드 202)** — **오너 확정: 202 유지**. 검증 근거를 수용해 코드 무변. (200으로 바꾸려면 `main.py:3214` status_code + `GENERATE_ASYNC_RESPONSES` 키만 국소 변경.)
- **Outstanding #3 / Issues #1 (SoT 수치 정정)** — **반영**. 추가 보강(아래)으로 backend가 1311→**1312**, async 분기 13→**14**, 신규 15→**16**이 됐으므로, SoT v1.7.27 changelog 행·HANDOFF·work_log 모두 **1312/14/16**으로 일치시켰다(권장했던 "1309→1311, 11→13"는 본 보강의 +1 테스트로 "1309→1312, 11→14"로 확정).
- **record hardening #3 (GET 존재-불가 project 404)** — **반영**. `test_get_generation_job_404_nonexistent_project` 추가로 GET-404 매트릭스 3 arms(존재-불가 project·unknown job·타 프로젝트 job) 잠금.
- **record hardening #2 (producer→worker e2e 통합 테스트)** — **증분 3으로 지연**(비차단, 양 절반은 독립 입증·seam 자명).
- **record hardening #4 (`extra='forbid'`)** — **조치 불요**(비차단, envelope-key 테스트가 상쇄; 기존 partial envelope 패턴도 default ignore).
- **Outstanding #2 (커밋)** — 오너 지시로 커밋 진행.

재확인: backend `1312 passed/73 skipped/325 subtests`, frontend 163/11, tsc clean, `git diff --check` clean.
