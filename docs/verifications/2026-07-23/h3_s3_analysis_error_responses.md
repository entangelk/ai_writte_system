# 독립 검증 기록 — H3 에러 응답 계약 S3: analysis 트랙 21 endpoint 에러 선언

## Subject metadata

- **날짜**: 2026-07-23
- **요청자**: 오너 ("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?")
- **검증자**: 독립 검증자(Claude, 본 슬라이스 구현 미관여)
- **대상 슬라이스/산물**: H3 S3 — `services/application/app/main.py` analysis 구역 21 endpoint의 OpenAPI `responses=` 선언 + 신규 상수 `_CONFIG_503`/`_ERRORS_404_502_CONFIG`/`_ERRORS_400_404_409_502_CONFIG` + 회귀 9건(`AnalysisErrorContractDeclarationTest`·`AnalysisErrorBodyExactKeyTest`)
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.7.31 §HTTP 에러 응답 계약(L295–329). 계보 브리프 `docs/plans/api-error-response-contract-decisions.md`(D1=A/D2=A/D3=A/D4=A, Resolved 2026-07-22). 선행 검증 `docs/verifications/2026-07-23/h3_error_response_contract_s1_s2.md`(S1+S2).
- **작업 원천**: working tree, uncommitted(`git diff --stat HEAD` = main.py 61ins/21del · schema.d.ts +324 · test_application_api.py +203 · SoT/HANDOFF/work_log). 커밋 안 됨(작업자 명시).

## Scope (계약 스코프 — 본 슬라이스가 지배하는 표면)

CLAUDE.md "scope the contract read before opening it"에 따라 본 슬라이스의 정본 계약 범위를 먼저 세웠다. S3는 D3=A라 **endpoint×코드 표를 SoT가 유지하지 않는다**(`docs/system-contract-sot.md:302`) — 즉 "각 endpoint가 어떤 코드를 선언해야 하는가"의 authority는 OpenAPI가 아니라 **실제 endpoint 본문의 `except → HTTPException(status_code=…)` 매핑**이다(OpenAPI는 그 기계적 진실의 산출물). 따라서 감사 대상은:

1. **정본 계약**: SoT §HTTP 에러 응답 계약(L295–329) — 상태코드 의미론 표(L307–316)·**503의 두 얼굴**(L318–323: 구성 face vs 무결성 face)·422 제외(L301)·동적 `ProviderError` 9곳은 endpoint별 realistic 집합만 선언(L316, 브리프 L42 와 일치).
2. **브리프**: `docs/plans/api-error-response-contract-decisions.md` S3 행(L93 "analysis … 트랙")·D1~D4(L46–83)·스코프 밖 "동적 9곳 전체 열거 안 함"(L42).
3. **구현 코드**: `main.py` 상수 `_CONFIG_503`(L1043)/`_ERRORS_404_502_CONFIG`(L1050)/`_ERRORS_400_404_409_502_CONFIG`(L1053) + S2 상수(`_MIGRATION_503`/`_ERRORS_404`/`_ERRORS_404_409`/`_ERRORS_400_404_409`/`_ERRORS_400_404`) + analysis 21 endpoint 본문(L2336–3017).
4. **회귀 테스트**: `tests/test_application_api.py::AnalysisErrorContractDeclarationTest`(L2214)·`AnalysisErrorBodyExactKeyTest`(L2332).
5. **공개 envelope/스키마**: `frontend/src/api/schema.d.ts`(gen:api 산물)·OpenAPI dump.
6. **런타임 무변성**: backend 전체 suite + frontend suite.

경계 매트릭스를 본문 직독으로 먼저 세운 뒤(아래 Findings §1), 나머지 표면이 그것을 뒷받침하는지 대조했다.

## Methodology (재현 가능한 명령)

```bash
# 0. 정본 스코프 읽기 (end-to-end, skim 아님)
#    docs/system-contract-sot.md:295-329, docs/plans/api-error-response-contract-decisions.md 전문

# 1. endpoint 본문 직독 → 경계 매트릭스 (선언 == 실제 매핑 raise 집합)
sed -n '2336,3017p' services/application/app/main.py   # 21 endpoint + except 절 전수

# 2. analysis endpoint 전수 추출 (멀티라인 decorator 포함) → 트랙 closure 확인
grep -nE '"/projects/\{project_id\}/analysis' services/application/app/main.py

# 3. 동적 status_code=status 9곳이 analysis 구역 밖인지 (브리프 스코프 주장)
grep -nE "status_code=status\b" services/application/app/main.py

# 4. OpenAPI self-discovery (코드가 emit할 의도가 아니라 실제 스펙을 읽는다)
python3 scripts/dump_openapi.py > /tmp/awt_openapi.json   # exit 0, 169410 bytes
#    → /tmpawt_openapi.json에서 /analysis/ path의 responses 코드 집합을 EXPECTED와 직접 대조

# 5. 회귀 9건 + subtest 카운트
python3 -m pytest tests/test_application_api.py::AnalysisErrorContractDeclarationTest \
                  tests/test_application_api.py::AnalysisErrorBodyExactKeyTest -v -p no:cacheprovider

# 6. mutation 4종 (각각 edit → 해당 회귀 run → revert; revert 후 git diff --stat 로 잔류 0 확인)
python3 -m pytest "tests/test_application_api.py::AnalysisErrorContractDeclarationTest::test_config_503_description_names_the_operator_action"   # mutation A
python3 -m pytest "tests/test_application_api.py::AnalysisErrorContractDeclarationTest::test_the_whole_analysis_track_is_declared"                  # mutation B
python3 -m pytest "tests/test_application_api.py::AnalysisErrorContractDeclarationTest::test_declared_error_statuses_match_the_lock_list"            # mutation C/D

# 7. backend 전체 (전용 test-mongo 27020 RS, ai_writte_system-test-mongo-1 기동 중)
python3 -m pytest -q -p no:cacheprovider

# 8. frontend 재생성 + 타입 + 빌드 + 테스트
cd frontend
git diff --stat HEAD -- src/api/schema.d.ts          # +324/-0
npm run gen:api && sha256sum src/api/schema.d.ts     # 멱등(재생성 전후 sha 동일)
npx tsc --noEmit                                       # exit 0
npm run build                                          # JS 399.03 kB
npm run test                                           # 13 files / 194 tests
```

## Findings

### 1. 경계 매트릭스 — 선언 집합 == 실제 매핑 raise 집합 (21/21, 빈 cell 없음)

CLAUDE.md 핵심: "test는 OpenAPI==EXPECTED만 pin하므로 EXPECTED 자체의 정확성은 **코드 직독**이 authority". 각 endpoint의 `except → HTTPException(status_code=N)` 절을 직독해 raise 집합을 도출하고 선언 상수와 대조했다.

| # | endpoint (method) | 선언 상수 → 집합 | 본문 직독 raise 집합 (file:line) | match |
|---|---|---|---|---|
| 1 | analysis/jobs (post) | `_ERRORS_404`→{404} | NotFound→404 (L2347) | ✓ |
| 2 | analysis/jobs/{job_id} (get) | {404} | (AnalysisNotFound,NotFound)→404 (L2360) | ✓ |
| 3 | …/candidates (get) | {404} | (AnalysisNotFound,NotFound)→404 (L2372) | ✓ |
| 4 | …/retry (post) | `_ERRORS_404_409`→{404,409} | 404 (L2386)·InvalidJobStateTransition→409 (L2388) | ✓ |
| 5 | …/run (post) | `_ERRORS_400_404_409_502_CONFIG`→{400,404,409,502,503} | 503 runner=None (L2410)·404 (L2419)·409 Duplicate (L2421)·400 (L2423)·502 ProviderError (L2429)·502 catch-all (L2440) | ✓ |
| 6 | candidates/…/promote (post) | {404} | (AnalysisNotFound,MemoryNotFound,NotFound)→404 (L2461) | ✓ |
| 7 | …/confirm (post) | {404,409} | 404 (L2498)·InvalidCandidateStateTransition→409 (L2500) | ✓ |
| 8 | …/reject (post) | {404,409} | 404 (L2517)·409 (L2519) | ✓ |
| 9 | …/edit (post) | `_ERRORS_400_404_409`→{400,404,409} | 404 (L2541)·409 (L2543)·InvalidAnalysisCandidate→400 (L2545) | ✓ |
| 10 | …/auto-promote (post) | {404} | (AnalysisNotFound,NotFound)→404 (L2559) | ✓(매핑)† |
| 11 | …/context (post) | {404} | (AnalysisNotFound,NotFound)→404 (L2649); 주석이 400 불가 명시 (L2655) | ✓ |
| 12 | …/compare (post) | `_ERRORS_404_502_CONFIG`→{404,502,503} | 404 (L2691)·503 CompareJudgeNotConfigured (L2697)·502 InvalidJudgeResult (L2699)·502 ProviderError (L2701) | ✓ |
| 13 | …/apply (post) | `_ERRORS_400_404`→{400,404} | 404 (L2752,2786)·400 루프내 (L2760,2766)·400 (L2788,2790) | ✓ |
| 14 | review-queue (get) | {404} | NotFound→404 (L2805) | ✓ |
| 15 | review-queue/…/reconcile (post) | {404,409} | 404 (L2826)·409 (L2828)·ValueError→409 (L2830) | ✓ |
| 16 | review-inbox (get) | {404} | NotFound→404 (L2916) | ✓ |
| 17 | review-inbox/{candidate_id} (get) | {404} | (NotFound,ReviewInboxNotFound)→404 (L2940) | ✓ |
| 18 | gate-findings (get) | {404} | NotFound→404 (L2971) | ✓ |
| 19 | gate-findings/{finding_id} (get) | {404} | (NotFound,GateFindingNotFound)→404 (L2986) | ✓ |
| 20 | …/resolve (post) | {404,409} | `_transition_gate_finding`: 404 (L2998)·InvalidGateFindingTransition→409 (L3000) | ✓ |
| 21 | …/dismiss (post) | {404,409} | 동일 (`_transition_gate_finding`) | ✓ |

**21/21 정확히 일치. under-strict(누락 코드)·over-strict(불가 코드 선언) 양방향 빈 cell 없음.** run의 503은 "analysis runner is not configured"(L2413), compare의 503은 `CompareJudgeNotConfigured`(L2697) — 둘 다 SoT L320의 **구성 face**이므로 `_CONFIG_503`(`_MIGRATION_503` 아님) 선택이 정당하다. apply의 `CompareAction ValueError→400`(L2766)과 reconcile의 `ReconciliationAction ValueError→409`(L2830)는 서로 다른 매핑이지만 각 선언이 정확히 반영한다.

† (10 auto-promote) try 밖의 `memory.auto_promote_candidate` 루프(L2566–2573)는 매핑된 status가 없다 — 이 부분은 아래 Hardening §2에서 다룬다.

### 2. 트랙 전수 closure — lock 리스트 밖 `/analysis/` endpoint = 0

경로 문자열 자체로 analysis endpoint를 전수 추출(`grep '"/projects/\{project_id\}/analysis'`)하면 단일/멀티라인 decorator 합쳐 **정확히 21**개. `context-search`는 `/projects/{project_id}/context-search`(L3112)로 `/analysis/` 하위가 아니어서 정당히 제외. 동적 `status_code=status` 9곳(L3530/3599/3677/3793/3809/3843/3885/3916/4081)은 전부 analysis 구역(≤L3017) **밖**이므로 브리프의 "analysis는 동적 매핑 없음" 주장이 성립한다(경고가 발화하지 않은 것이지 스코프 축소가 아님).

### 3. OpenAPI self-discovery — 코드가 emit할 의도가 아니라 실제 스펙을 읽음

`dump_openapi.py`로 169KB JSON을 덤프하고 `/analysis/` path의 responses 코드 집합을 EXPECTED와 **독립 Python 스크립트**로 대조: `endpoints=21 mismatches=0 undeclared_analysis_ops=[]`. body-model subtest 총수 = `sum(|EXPECTED 집합|)` = **36**.

### 4. 503 두 얼굴 — 스키마에서 실제로 갈려 있음

- CRUD 무결성 face(drafts list/create·project export의 503): `migrate_ordered_units.py` 문안 **있음** (3곳 전부).
- analysis 구성 face(run·compare의 503): migrate 문안 **없음**, "deployment" **있음**.
- run의 502 body `$ref` = `#/components/schemas/ErrorDetailResponse`. (균일 단일 모델, D1=A.)

### 5. 회귀 테스트 코드 감사 (테스트는 감시자가 아니라 감사 대상)

`AnalysisErrorContractDeclarationTest`(L2214):
- `test_declared_error_statuses_match_the_lock_list`(L2281): `len(EXPECTED)==21` 고정 + (path,method)마다 `assertEqual(_declared, expected)` exact 집합 비교 → under/over 양방향. subTest 21.
- `test_the_whole_analysis_track_is_declared`(L2287): OpenAPI의 `/analysis/` operation 중 EXPECTED에 없는 것이 빈 집합. **S2에 없던 신규 축**(lock 리스트 자체의 over-strict 가드).
- `test_every_declared_error_body_is_the_uniform_detail_model`(L2300): (endpoint,code)마다 `$ref==ErrorDetailResponse`. **subTest 36**(⚠ work_log는 31로 기재 — 아래 Issues).
- `test_config_503_description_names_the_operator_action`(L2313): run·compare 503 description에 "not configured"+"deployment" 존재 **and** "migrate_ordered_units.py" 부재 → 두 얼굴 lock 양방향. subTest 2.

`AnalysisErrorBodyExactKeyTest`(L2332): 404/409/400/502/503 실제 wire 본문이 정확히 `{detail}` 단일 키 + non-empty str. 502 테스트는 `_ApiProviderErrorRunner`(L1928, `RuntimeError` re-raise)로 generic `except Exception→502`(L2440)을 탄다 — 명시적 `except ProviderError→502`(L2429) 분기는 기존 `test_analysis_run_endpoint_maps_real_provider_error_to_502`가 별도 커버. S3 본문 테스트의 역할은 "502의 wire 본문 형태" 검증이므로 catch-all 경로 사용은 목적에 부합(503 본문 테스트는 runner=None으로 구성 face를 직접 탄다).

CLAUDE.md 테스트 감사 기준: (a) assertion이 계약을 pin — 예·(b) under-strict guard — 예(mutation D)·(c) over-strict guard — 예(mutation A/C)·(d) parametrized 전수 — body-model이 21 endpoint×전 코드 36쌍 커버·(e) 공개 envelope 대상 — 예(OpenAPI·HTTP body). **9 passed / 59 subtests** 독립 재실행으로 확인.

### 6. mutation 4종 — 전부 bite (독립 실증, 각각 revert 후 잔류 0 확인)

| mutation | 기대 회귀 bite | 실증 결과 |
|---|---|---|
| A. `_CONFIG_503` description에 `migrate_ordered_units.py` 누출 | config_503 | run·compare 양 subTest `assertNotIn` SUBFAIL ✓ |
| B. 선언 없는 `/analysis/brand-new-zzz` endpoint 추가 | track-wide | `('…/brand-new-zzz','get')` 포함 FAIL ✓ |
| C. `_ERRORS_404_502_CONFIG`에 504 추가(over-strict) | lock_list | compare만 SUBFAIL(나머지 20 무영향) ✓ |
| D. compare의 `responses=` 삭제(under-strict) | lock_list+body_model+config_503 | compare에서 3 메서드 5 subTest SUBFAIL ✓ |

### 7. 수치 전부 독립 재도출 (보고된 숫자를 그대로 믿지 않음)

| 항목 | work_log 주장 | 독립 재측정 | 일치 |
|---|---|---|---|
| backend suite | 1428 passed/1 skipped/443 subtests | **1428/1/443** (569.12s) | ✓ |
| 신규 회귀 | 9 tests/+59 subtests | **9 passed/59 subtests** | ✓ |
| gen:api | +324/-0 순수 additive | `git diff --stat`=324 ins/0 del; 재gen 후 sha 동일(멱등) | ✓ |
| tsc | clean | exit 0 | ✓ |
| build JS | 399.03 kB | **399.03 kB** | ✓ |
| frontend suite | 194/13 | **194 passed/13 files** | ✓ |
| baseline delta | 1419/1/384 → +9/+59 | 1419+9=1428, 384+59=443 | ✓ |

## Issues / Risks

### Blocking (계약 의무 위반)
**없음.** 경계 매트릭스에 빈 cell이 없고(§1), 트랙 closure가 성립하며(§2), 두 얼굴이 스키마에서 실제로 갈리고(§4), 회귀가 계약을 pin하며(§5), mutation 4종이 전부 bite한다(§6). 계약이 요구하는 lock(under-strict·over-strict·두 얼굴 분리·트랙 전수)에 누락이 없다.

### Hardening recommendations (비차단 — 현 계약이 요구하지 않는 보강)

- **H-1(문서 숫자 정밀도, 2건)**: 본문 직독과 독립 스크립트로 재측정한 결과 work_log/SoT changelog의 서술 숫자 2건이 어긋난다. 어느 쪽도 코드·상수·선언·테스트·스키마의 **정확성에는 무관**하고 aggregate(9 tests/59 subtests/+324/1428/443/194/13/399.03)는 전부 정확하다.
  - **"나머지 18 endpoint 재사용" → 실제 19**: 21 endpoint 중 신규 복합 상수를 쓰는 것은 run·compare **2**개뿐이므로 S2 상수 재사용은 **19**곳(work_log L206·SoT changelog L36 둘 다 "18"로 기재, 21−2=19). 합산 오기.
  - **"body-model subTest 31" → 실제 36**: `sum(|EXPECTED 집합|)`=36(독립 스크립트로 확인). aggregate 59(=21+36+2)가 맞으려면 이 축은 36이어야 한다(work_log L209 "subTest 31"로 기재, 31이면 총 54가 돼 59와 모순). SoT changelog는 aggregate "9(+59)"만 쓰므로 정확.
  - **제안**: 두 숫자 모두 work_log의 서술만 고치면 된다(코드/테스트/스키마 무변경).
- **H-2(매핑되지 않은 예외 경로 — 사전 존재, S3 비관여)**: `auto_promote_job`은 `memory.auto_promote_candidate` 루프(L2566)가 try 밖이다. 유사하게 `analysis_review_queue_endpoint`(L2807)·`list_review_inbox`(L2922,2926)·`list_gate_findings`(L2975)도 list 호출이 try 밖이다. 이들 호출이 예외를 던지면 매핑된 status가 없어 **500**으로 샌다. 다만 (a) S3는 `responses=`만 추가했고 try/except 구조를 건드리지 않았으며(사전 존재), (b) SoT L329가 500 누수를 "정본이 승인한 동작이 아닌 알려진 결손"으로 분류하므로 **선언 계약 위반이 아니다**, (c) list/promote 호출이 realistic하게 예외를 던지는지는 service 층 의문이고 현재 매핑 raise 집합은 {404}가 정직하다. `start_next_unit`(S5 예정)과 동일 부류의 구조적 관찰이므로 S5 착수 시 `except DraftOrderIntegrityError→503`와 함께 이 list/promote 축도 점검할 만한 후보로 기록한다. 본 슬라이스 verdict에는 영향 없음.

## Verdict

**합격(조건 없음).** S1/S2 합격과 동일한 기준으로 통과한다. 근거:
1. 경계 매트릭스 21/21 빈 cell 없음 — 선언 집합 == 본문 직독 raise 집합(under/over 양방향).
2. 503 두 얼굴이 `_CONFIG_503`(구성) vs `_MIGRATION_503`(무결성)으로 선언 표면에서 처음 갈리며, run·compare의 503은 모두 구성 face로 `_CONFIG_503` 선택이 정당.
3. 회귀가 계약을 pin하고(OpenAPI exact 집합·단일 본문 모델·두 얼굴 문안·**트랙 전수 closure**) mutation 4종이 전부 bite.
4. 런타임 무변(1428/1/443, 동일 상수·분기·detail)·gen:api 순수 additive 멱등·tsc/build/vitest 전부 green·수치 전부 독립 재도출 일치.

H-1(문서 숫자 2건)·H-2(사전 존재 미매핑 경로)는 비차단이며 본 슬라이스가 닫아야 할 계약 의무가 아니다. H-1은 work_log 서술 정정만으로 즉시 닫힌다.

## Outstanding items (오너 다음 단계에 영향)

- **커밋 미수행**: 작업자가 명시적으로 커밋하지 않았다("원하시면 슬라이스 단위로 커밋하겠습니다"). 6개 파일(main.py·test_application_api.py·schema.d.ts·SoT·HANDOFF·work_log)이 working tree에 uncommitted로 남아 있고, 본 검증자의 mutation 실험은 모두 revert 완료(`git diff --stat HEAD -- services/application/app/main.py` = 61ins/21del, 잔류 probe 0, 9 테스트 green). **오너 커밋 승인 대기**.
- 검증 과정에서 main.py를 4회 mutation/revert했으나 최종 상태는 작업자 산물과 정확히 동일(diff·sha 기반 확인).
- **다음 슬라이스 = S4(memory/source)**. 본 검증의 H-2(list/promote 미매핑 경로)와 동적 `ProviderError` 9곳(전부 S5 writing 구역)은 S5 착수 시 점검 후보.

## Reproduction (end-to-end 최소 시퀀스)

```bash
# test-mongo RS 기동(이미 떠 있으면 생략)
docker compose -f docker-compose.test.yml up -d test-mongo

# 코드 직독 경계 매트릭스 + OpenAPI self-discovery
sed -n '2336,3017p' services/application/app/main.py
python3 scripts/dump_openapi.py > /tmp/openapi.json   # /analysis/ responses 코드 집합 직접 대조

# 회귀 + 전체 suite
python3 -m pytest tests/test_application_api.py::AnalysisErrorContractDeclarationTest \
                  tests/test_application_api.py::AnalysisErrorBodyExactKeyTest -v -p no:cacheprovider
python3 -m pytest -q -p no:cacheprovider              # 1428/1/443 예상

# frontend 재생성
cd frontend && git diff --stat HEAD -- src/api/schema.d.ts   # +324/-0
npm run gen:api && npx tsc --noEmit && npm run build && npm run test   # 399.03 kB / 194/13 예상

# mutation 4종(edit→run→revert)은 본문 §6 / Methodology step 6 참조
```
