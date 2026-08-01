# 독립 검증 — D8-6d admin project purge endpoint (commit 650629a + 583eab5 + 25d88bc + af2436f)

## Subject metadata

- **날짜**: 2026-08-01
- **요청자**: 오너("다음작업 검증해줘. D8-6d 완료 — D8-6 영구 삭제 트랙 종료 … 6d는 경계 가정을 확장하고 operation 카운트/공개 API 변화를 줬습니다.")
- **검증자**: Claude (독립 세션, max 노력)
- **대상 슬라이스**: D8-6d — `POST /admin/projects/{project_id}/purge`(204, `_REQUIRE_ADMIN`, `{401,403,404,503}`) endpoint 가 6a/6b/6c 파기 메서드를 조율. **D8-6 영구 삭제 트랙 종료**. operation 카운트 70→71, 공개 API 변화.
- **정규 스펙**: `docs/system-contract-sot.md` v1.7.74(D8-6d) · `docs/plans/auth-d8-5-admin-decisions.md` §5(D5=A 전체 그래프 영구 파기, admin-only, 부분 삭제 금지) · `docs/verifications/2026-08-01/d8_6c2_worker_drain.md`(6c-2 선행 — 본 슬라이스 hardening #1 SoT 헤더를 반영해 af2436f·25d88bc 가 해소).
- **검증 대상 출처**: `af2436f`(6c-2 검증 hardening #1 SoT 헤더 v1.7.73 — 본 세션 범위, HEAD) · `650629a`(endpoint + boundary matrix) · `583eab5`(enqueue 회귀 + 경계 가드 예외 + `_declared` 204) · `25d88bc`(SoT v1.7.74 + 문서). HEAD = `25d88bc`. push 안 됨.

## Scope

1. **endpoint 구현 + 오케스트레이션 + 상태코드** — 204·`_REQUIRE_ADMIN`·`{401,403,404,503}` 선언·core_sot→derived→enqueue 순서·NotFound→404·storage→503(전역 handler). D5 부분삭제금지 실패 semantics.
2. **★ endpoint→derived purge wiring 회귀 커버리지** — AdminProjectPurgeTest 가 8개 derived service purge(10컬렉션) 호출을 잡는가. 뮤테이션(8개 전부 제거)으로 empirically 입증.
3. **경계 가드 예외 + boundary matrix + operation 카운트** — ProjectAuthorizationTest purge 예외(보안 약화 아닌지), CombinedBoundaryMatrixTest ADMIN 5/tier 71, AdminErrorContract EXPECTED 5, operation 카운트 70→71.
4. **양방향 뮤테이션** — core_sot+enqueue 누락(작업자 주장) 독립 재현 + derived 누락(본 검증자 발견).
5. **전체 suite green + SoT 합치** — 1820 재현; v1.7.74 entry·헤더 버전·operation 카운트.

## Methodology

- 코드 diff: `git show 650629a -- main.py tests/...` 로 endpoint·boundary 전수 독해.
- boundary matrix: `CombinedBoundaryMatrixTest`(test_auth_api.py:685)·`AdminErrorContractDeclarationTest`(test_application_api.py) 직독 + 실행.
- 503 매핑: create_app 전역 exception handler(main.py:2196-2199, v1.7.38 `_STORAGE_ERRORS`→503) 확인.
- 양방향 뮤테이션(작업 트리 일시 변이 → re-fail/통과 확인 → `git checkout` 원복):
  - **A(결정적)**: endpoint 의 8개 derived purge 호출 전부 제거(core_sot+enqueue 유지) → AdminProjectPurgeTest + 전체 suite 에서 잡는지.
  - B: core_sot purge + enqueue 제거(derived 유지) → 작업자 "3 re-fail" 주장 독립 재현.
- boundary matrix: [should fire] 204 성공·core_sot 소멸·enqueue entry · [should fire] 404 미존재 · [should fire] 401/403(admin) · [should fire] 503(storage) · ★[should fire] derived 10컬렉션 파기.

## Findings

### 1. endpoint 구현 + 상태코드 ✅

- **선언**(main.py:2798-2800): `status_code=204, response_model=None, responses=_ERRORS_ADMIN_404, dependencies=_REQUIRE_ADMIN`. `_ERRORS_ADMIN_404`={404,503} + `_protected`의 401/403 = `{401,403,404,503}`. 409 불필요(purge 멱등 — 재파기=404). ✅
- **오케스트레이션**(main.py:2807-2819): `core_sot.purge_project`(try/except NotFound→404, 선행) → derived 8 service purge(memory·analysis·review_queue·gate_findings·writing_generation_jobs·writing_scratch·writing_loop_audit·llm_call_audit = 10컬렉션) → `enqueue_project_purged`(6c worker). 순서 정확(core_sot 선행 = source-of-truth 먼저). ✅
- **503 매핑 진짜**: endpoint 가 derived purge 실패(storage error)를 catch 않고 전파 → create_app 전역 handler(main.py:2196-2199, `_STORAGE_ERRORS`→`JSONResponse(503)`, v1.7.38 "신규 endpoint 가 mapping 상속") → 503. 선언 envelope 의 503 은 도달 가능. ✅

### 2. ★ endpoint→derived purge wiring 회귀 커버리지 — BLOCKING 갭 ❌

- **AdminProjectPurgeTest**(test_auth_api.py:636) 3케이스가 검증하는 것: ①204+core_sot project 소멸(`list_projects()==[]`) ②`enqueue_project_purged` PROJECT_PURGED entry ③미존재 404. **어느 것도 8개 derived service purge 가 실제로 불렸는지 단언 않음**.
- **Empirical 입증(뮤테이션 A)**: endpoint 의 derived 8 purge 호출을 **전부 제거**(core_sot+enqueue 유지) →
  - `AdminProjectPurgeTest`: **3 passed**(잡지 못함)
  - **전체 suite**: **1820 passed, 0 failed**( suite 어디서도 잡지 못함)
- 즉 D5 전체 그래프 파기(18컬렉션)의 **중간 10컬렉션(memory·analysis 3·review_queue·gate_findings·writing 3·llm_call_audit) endpoint wiring 이 회귀에 잠기지 않음**. 향후 리팩토링이 derived purge 호출을 떨어뜨려도 **조용한 고아 데이터(부분 삭제, D5 위반)** 가 발생하고 green bar 로 감지 불가.
- **비대칭**(뮤테이션 B로 확정): core_sot purge + enqueue 누락은 **3 re-fail**(작업자 주장 정확 — `test_admin_purge_returns_204_and_removes_project`·`test_admin_purge_enqueues_project_purged`·`test_admin_purge_missing_project_is_404`). 즉 회귀는 core_sot(정본)+enqueue(vector/index)는 잡지만 **derived 10컬렉션 만 잡지 못한다**.
- **왜 잡지 못하나**: 테스트가 core_sot 에 project 만 만들고 derived 데이터(메모리·분석 job 등)를 만들지 않으므로, derived purge 가 돌아도 지울 것이 없어 단언 불가. 검증 가이드 금지 실패 모드("계약 필수 분기가 회귀에 잠기지 않으면 green bar 와 무관하게 blocking")의 정확한 사례.

### 3. 경계 가드 예외 + boundary matrix + operation 카운트 ✅

- **ProjectAuthorizationTest 예외**(test_auth_api.py:374-383): `if route.path == "/admin/projects/{project_id}/purge"` **정확 경로 매치**로 purge 만 `pass`. 다른 admin+project_id route 는 여전히 가드 적용. `pass` 가 ownership 2단언을 건너뛰지만 **`"403" in responses` 단언은 if/else 밖이라 purge 에도 실행** → 403 선언 강제. purge 는 "admin 이 id 로 파기하고 내용은 안 읽음"(D5) — "{project_id} path ⇒ ownership" 불변의 의도적·문서화된 예외. **보안 약화 아님**(가드가 위반을 잡아 명시적 예외를 강제했다 = 가드 유효). ✅
- **boundary matrix**(test_auth_api.py:685 `CombinedBoundaryMatrixTest`): `ADMIN` 집합 5(purge 포함), `len(tiers)==71`(70→71), project tier 60(무변). tier 는 **route dependencies** 로 파생 — purge 는 `_REQUIRE_ADMIN`→admin tier(project_id 경로지만 project tier 아님). ✅ (참고: 커밋 메시지는 CombinedBoundaryMatrixTest 를 test_application_api 라 했으나 실제는 test_auth_api — 사소한 메시지 불일치.)
- **AdminErrorContract**(test_application_api.py:2297): purge EXPECTED `{"401","403","404","503"}`, `len(EXPECTED)==5`(4→5). `_declared` 가 2xx(200/204) 제외 — purge 204 success 가 error lock list 에 섞이지 않게(5개 contract 클래스에 적용됐으나 EXPECTED 카운트는 Admin 만 변경, 안전). ✅
- **operation 카운트 70→71**: SoT v1.7.74 entry 에 명시. boundary matrix `len(tiers)==71` 과 일치. ✅

### 4. 양방향 뮤테이션(독립 재현)

| 변이 | 코드 | 결과 |
|---|---|---|
| A. derived 8 purge 전부 제거 | main.py:2811-2818 삭제(core_sot+enqueue 유지) | AdminProjectPurgeTest **3 passed**, 전체 suite **1820 passed/0 failed** — **잡지 못함(갭)** ❌ |
| B. core_sot purge + enqueue 제거 | main.py:2807-2810 + 2819 삭제(derived 유지) | AdminProjectPurgeTest **3 re-fail** — 작업자 주장 정확 ✅ |

### 5. 전체 suite green + SoT 합치 ✅ (헤더 이슈 해소)

- **clean 전체 suite**: `python3 -m pytest -q` → **1820 passed / 4 skipped / 1532 subtests / 97.09s**. 수치 일치. subtest 1519→1532(+13)는 boundary matrix 가 purge route 를 순회하며 발생(정상).
- **SoT 헤더 버전 정상**: line 4 `v1.7.74`(6c-2 검증 hardening #1 의 v1.7.71 stale 가 af2436f→v1.7.73, 25d88bc→v1.7.74 로 해소). ✅
- **v1.7.74 entry 정확**: endpoint·204·`_REQUIRE_ADMIN`·`{401,403,404,503}`·오케스트레이션·operation 70→71·boundary 예외·503 부분실패 서술. 단 "D5 전체 그래프 파기(18컬렉션 + vector/index) **완성**" 주장은 derived 10컬렉션 wiring 이 회귀로 뒷받침되지 않아(Findings #2) **과대**.

## Issues / Risks

### Blocking (계약 의무) — 1건

1. **endpoint→derived purge wiring 회귀 부재(조건부 합격 사유)**. D5 전체 그래프 파기를 endpoint 가 조율하는 8개 derived service purge(10컬렉션) 호출이 어떤 회귀에도 잠기지 않음(뮤테이션 A 로 8개 전부 제거 시 0 fail 입증). core_sot(정본)+enqueue(vector/index)는 잠겨 있으나(Findings #4-B) derived 중간 10컬렉션만 빈 칸. 향후 리팩토링 누락 시 조용한 고아(D5 위반). **lock 추가까지 본 슬라이스는 합격 아님**.
   - 권장 regression: AdminProjectPurgeTest 가 derived 서비스(또는 mock)를 주입해 purge 후 derived 데이터(메모리·분석 job 등) 소멸을 단언, 또는 8 service 의 `purge_project` 호출을 spy 로 확인. minimum 으로는 8 service 중 대표 1~2개(예: memory·analysis)의 소멸 단언이라도 wiring 빈 칸을 닫는다.

### Hardening recommendations (non-blocking)

2. **partial-failure 503→재시도→404 모호성**(작업자 인지·"완전 멱등 재시구"로 남김): core_sot 파기(트랜잭션 커밋) 후 derived 도중 mongo 장애 → 503. 클라이언트 재시도 → core_sot `_require_project` NotFound → **404**(파기가 일어났는지 클라이언트가 불확정). derived 일부 컬렉션이 고아로 잔류 가능(좁은 창: core_sot 커밋 후 derived 완료 전 mongo 다운). 작업자가 reconciler/멱거 재시구 로 별도 슬라이스 명시. core_sot 가 선행 파기되므로 잔류 derived 는 대부분 query-도달 불가 ghost.
3. **SoT "완성" 과대 표현**: v1.7.74 entry 의 "D5 전체 그래프 파기 완성" 은 derived wiring 회귀 부재(Findings #1)와 충돌. lock 추가 후 "완성" 으로 확정 권장.
4. **ProjectAuthorizationTest 예외 `pass`**: ownership 2단언 모두 건너뜀 — purge 에서 `ownership_guarded==expected` 는 자명(통과)이라 무해하나, 더 외과적이라면 `assertFalse(admin_guarded and expected)`(purge 가 정당히 위반하는 것)만 skip 하고 `ownership_guarded==expected` 는 유지 가능(사소).

## Verdict

**조건부 합격(conditional pass).** blocking 1건.

- endpoint 구현·상태코드·오케스트레이션 순서·503 매핑·boundary matrix(ADMIN 5/tier 71)·AdminErrorContract(EXPECTED 5)·ProjectAuthorizationTest 예외(보안 약화 아님)·SoT v1.7.74(헤더 정상) — 모두 정규 계약과 합치.
- core_sot+enqueue 뮤테이션 3 re-fail 독립 재현(작업자 주장 정확).
- 전체 suite 1820 독립 재현(수치 일치).
- **단, endpoint→derived 8 service purge(10컬렉션) wiring 이 회귀에 잠기지 않음을 뮤테이션 A 로 입증(8개 제거→0 fail)**. D5 부분삭제금지 의 계약 필수 분기가 빈 칸 → 검증 가이드에 따라 lock 추가까지 **합격 아닌 조건부 합격**. 조건: derived purge orchestration regression 추가(Findings #1 권장안).

## Outstanding items

- **Blocking #1 처리(오너 결정)**: derived purge wiring regression 추가(별도 작은 슬라이스) 후 본 검증 조건 해소. 검증자는 fix 않고 오너에게 회신(검증 가이드).
- **schema.d.ts 재생성**(오너 질문): 6d 공개 API 변화(204 endpoint +1)로 `npm run gen:api` 필요. 프론트 purge UI 자체는 D8-5 admin 화면 C-1~C-6 선행. — 본 검증과 별개.
- **완전 멱등 재시구/reconciler**(hardening #2): partial-failure 503→404 모호성 + derived 고아 잔류 창. 별도 슬라이스(작업자 명시).
- **test-mongo**: healthy. 작업 트리 clean. push 는 오너.

## Reproduction

```bash
# 전체 green bar
python3 -m pytest -q
# → 1820 passed, 4 skipped, 1532 subtests (test-mongo ON)

# 회귀 + boundary + error-contract
python3 -m pytest "tests/test_auth_api.py::AdminProjectPurgeTest" \
  "tests/test_auth_api.py::CombinedBoundaryMatrixTest" \
  "tests/test_application_api.py::AdminErrorContractDeclarationTest" -v

# ★ 결정적 뮤테이션 A (derived wiring 갭 입증):
#   main.py:2811-2818 (8 derived purge 호출) 전부 삭제 후
python3 -m pytest "tests/test_auth_api.py::AdminProjectPurgeTest" -q   # 3 passed (잡지 못함)
python3 -m pytest -q                                                   # 1820 passed, 0 failed
# 뮤테이션 B (작업자 주장): main.py:2807-2810 + 2819 (core_sot purge+enqueue) 삭제 → 3 re-fail
git checkout -- services/application/app/main.py                       # 원복
```
