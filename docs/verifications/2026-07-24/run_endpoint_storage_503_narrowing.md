# 검증 기록 — `POST …/analysis/jobs/{id}/run` 저장소 장애 502→503 좁히기 (SoT v1.7.40, (B))

## Subject metadata

- **날짜**: 2026-07-24
- **요청자**: 오너("작업 AI가 작업한 거 확인해서 검증하고 의심하고 또 의심해줄래?")
- **검증자**: 독립 검증 AI(Claude, 본 슬라이스 구현 미관여)
- **검증 대상 슬라이스/산출물**: (B) run endpoint 저장소 장애 502→503 좁히기 — `services/application/app/main.py::run_analysis_job` 신규 `except _STORAGE_ERRORS → 503`, SoT v1.7.39→v1.7.40 계약 갱신, 회귀 1건 신규.
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.7.40(Approved). 본문 §"정본 저장소 장애" run 예외 문장 + Phase 2A run 매핑 prose + 변경이력 v1.7.40 행. 선행 맥락: v1.7.35 D2=A("저장소는 502가 아닌 503"), v1.7.38(전역 handler + `_CONFIG_503`/`_with_storage_note` 선언), v1.7.39(run을 pre-existing 예외로 기록, (B)를 후속 오너 결정으로 이월).
- **검증 대상 작업 출처**: working tree, uncommitted(`git status`: main.py·test_application_api.py·system-contract-sot.md·HANDOFF.md·work_log.md 5개 파일 수정, 미커밋).

## Scope

1. **계약(정본 SoT)** — v1.7.40 변경이력 행 + §"정본 저장소 장애" run 예외 문장 + Phase 2A run 매핑 prose. 계약 내부 정합성(변경이력 ↔ 본문 ↔ Phase 2A) 점검.
2. **구현 코드** — `run_analysis_job`의 except 절 순서·적용 범위·본문 형태. 신규 절이 광의 catch보다 선���재하는지, 4개 저장소 호출을 모두 감싸는지.
3. **선언 무변 주장** — run endpoint의 `responses=_ERRORS_400_404_409_502_CONFIG`가 실제로 503을 포함하는지, `_CONFIG_503`이 `_with_storage_note`로 감싸져 있는지. 슬라이스가 선언을 건드렸는지.
4. **회귀 테스트** — 신규 `test_run_endpoint_narrows_storage_failure_to_503_despite_broad_except`. under-strict(신규 절 제거 시 502 재실패)·over-strict(provider→502 유지) 양방향 bite.
5. **공개 계약/생성 타입** — `gen:api` 재생성 시 `frontend/src/api/schema.d.ts` no-diff 실측.
6. **회귀 기준선** — `tests/test_application_api.py` 단독 + 전체 backend suite 카운트.

## Methodology

> 모든 명령은 `/mnt/d/devel/에베베/ai_writte_system` 에서 실행. 검증 시점 머신 상태: `ai_writte_system-test-mongo-1` 컨테이너 `Up (healthy)` on `:27020`(replica set, rs-test) — HANDOFF의 "스택 다운" 노트와 무관하게 **직접 `docker ps`로 확인**하여 "live 불가"로 단정하지 않음(memory `verify-machine-state-before-claiming-blocked` 적용).

- **diff 전수**: `git diff services/application/app/main.py tests/test_application_api.py docs/system-contract-sot.md HANDOFF.md` — 변경 전모 파악.
- **계약 읽기(범위 좁혀)**: SoT 본문 §"정본 저장소 장애"(run 예외 문장) + Phase 2A run bullet + 변경이력 v1.7.35/38/39/40 행만 종단간 독파. boundary matrix 구축: (should fire) 저장소 예외→503 / (should NOT fire) ProviderError→502, NotFound→404, Duplicate→409, Extraction 계열→400, runner 미구성 HTTPException→503(구성 face), generic Exception→502.
- **코드 구조**: `run_analysis_job` 본문(main.py:2536–2598)과 except 절 순서 직독. `_STORAGE_ERRORS`(1052, `_resolve_storage_error_types` → `(PyMongoError,)`)·`_CONFIG_503`(1140)·`_with_storage_note`(1107)·`_ERRORS_400_404_409_502_CONFIG`(1150) 정의 직독. 전역 handler 본문 형태(main.py:1696–1708) 직독.
- **under-strict mutation(핵심)**: 신규 `except _STORAGE_ERRORS → 503` 절을 Edit로 **제거** → 신규 테스트 단독 실행 → 502로 실패하는지 확인 → 절 복원(복원 중 도입한 주석 오타 `__storage_note`→`_with_storage_note` 정정 후 `git diff`로 무결성 재확인).
- **over-strict**: 기존 `test_analysis_run_endpoint_maps_provider_exception_to_502`·`_maps_real_provider_error_to_502` 단독 실행(provider→502 유지 확인).
- **schema no-diff**: `python3 scripts/dump_openapi.py > openapi.json && npx openapi-typescript openapi.json -o schema.d.ts`(gen:api 공식 명령, `frontend/package.json:11`) 재생성 → tracked `frontend/src/api/schema.d.ts`와 `diff`.
- **테스트 실행**:
  - `python3 -m pytest tests/test_application_api.py::CanonicalStoreFailureHandlerTest::test_run_endpoint_narrows_storage_failure_to_503_despite_broad_except -x -q`
  - `python3 -m pytest tests/test_application_api.py -k "test_analysis_run_endpoint_maps_provider_exception_to_502 or test_analysis_run_endpoint_maps_real_provider_error_to_502" -q`
  - `python3 -m pytest tests/test_application_api.py -q`
  - `python3 -m pytest tests/ -q`(전체 backend, test-mongo 기동 상태)
- **패턴 스윕(CLAUDE.md §4)**: `grep -n "except Exception" main.py`로 run 외 동일 패턴(광의 catch가 저장소 예외를 비-503으로 재분류) 탐색 → context-search `persist_rejection` 경로(main.py:3336–3342) 발견 → `test_context_search_api.py` 기존 테스트로 설계 의도 교차 확인.

## Findings

### 1. 계약(정본 SoT) — 내부 정합, 외부 정합
- 변경이력 v1.7.40 행(system-contract-sot.md:36)이 코드 변경을 정확히 기술: "광의 `except Exception → 502` 앞에 명시적 `except _STORAGE_ERRORS → HTTPException(503)`… 선언 무변… provider 실패는 명시 `except ProviderError → 502`가 계속 잡는다(over-strict 방향 불변)."
- 본문 §"정본 저장소 장애" run 예외 문장(system-contract-sot.md:338)이 v1.7.39의 "run은 502를 낸다(pre-existing)"에서 "run도 503을 낸다(v1.7.40 D2=A)"로 개정됨. 문장 내 "선언(`_CONFIG_503`)이 `_with_storage_note`로 두 얼굴을 이미 기술하므로 선언은 무변" 서술이 코드와 일치(아래 §3).
- Phase 2A run 매핑(system-contract-sot.md:517)에 "정본 저장소 장애 503(v1.7.40 D2=A)" 추가 — provider 실패 502와 나란히 명시.
- **계약 내부 정합성**: 변경이력 ↔ 본문 bullet ↔ Phase 2A prose 3곳 모두 "run 저장소 장애 = 503, provider 실패 = 502"로 일치. 모순 없음.

### 2. 구현 코드 — 계약 부합
- `run_analysis_job`(main.py:2536–2598) try 본문: `_require_project_exists`(2540, gate)·`analysis.get_job`(2541)·`analysis.list_candidates`(2543)·`runner.run_job`(2559) — 저장소 호출 4곳 모두 **동일 try** 내.
- except 절 순서: NotFound→404(2563) · Duplicate→409(2565) · Extraction 계열→400(2567) · **ProviderError→502(2573)** · **`_STORAGE_ERRORS`→503(2582, 신규, pos 5)** · HTTPException→raise(2594) · **Exception→502(2596, pos 7)**.
- 신규 절(2582)이 광의 `except Exception`(2596)보다 **선행** → 저장소 예외가 502로 빨려 들어가지 않음. ✓
- `ProviderError`(pos 4)와 `_STORAGE_ERRORS`(pos 5)는 타입이 disjoint(LLM/gateway 에러 vs pymongo) → 순서 무관하게 provider 실패는 502, 저장소 실패는 503. ✓
- runner 미구성 `HTTPException(503)`(2554)은 pos 6 `except HTTPException: raise`에서 그대로 재raise → 신규 절과 간섭 없이 구성 face 503 유지. ✓
- 본문 형태: 신규 절 `raise HTTPException(503, detail=str(exc))` → FastAPI `{"detail": ...}`. 전역 handler(main.py:1699)도 `JSONResponse(503, {"detail": str(exc)})`. **두 경로 동일 균일 본문** — 계약 "결과 status는 전역 handler와 동일한 503 균일 본문" 부합. ✓

### 3. 선언 무변 주장 — **검증됨(작업자 핵심 주장 확인)**
- `run_analysis_job` decorator(main.py:2537): `responses=_ERRORS_400_404_409_502_CONFIG`.
- `_ERRORS_400_404_409_502_CONFIG`(main.py:1150–1152)는 **이름과 달리 `503: _CONFIG_503`를 포함**: `{400, 404, 409, 502: _ERROR, 503: _CONFIG_503}`. 상수명의 "502"가 503 부재를 뜻하지 않음.
- `_CONFIG_503`(main.py:1140) = `_with_storage_note({...})` → description에 `_STORAGE_503_NOTE`("The canonical store may also be unreachable or failing…")가 **이미 붙어 있음**. 즉 run endpoint의 OpenAPI 선언은 v1.7.38(전역 handler 도입 시)부터 이미 저장소→503 face를 약속.
- `git diff main.py` = **+12/−0**(신규 except 절만). `_CONFIG_503`·`_with_storage_note`·`_STORAGE_503_NOTE`·`_ERRORS_400_404_409_502_CONFIG` 모두 미수정. → **선언은 슬라이스가 건드리지 않았음이 확정**. 작업자 주장 "코드가 선언을 따라잡은 것(선언 무변)" 정확.

### 4. 회귀 테스트 — 양방향 bite 확인
- 신규 `test_run_endpoint_narrows_storage_failure_to_503_despite_broad_except`(test_application_api.py:2752): `_ProjectGateFailingRepository.get_project`가 `_STORAGE_FAILURE`(`pymongo.errors.AutoReconnect`, `PyMongoError` 서브클래스 → `_STORAGE_ERRORS` 정당 구성원)를 던지는 repo로 `POST /projects/p1/analysis/jobs/j1/run` → **503**, `set(body)=={"detail"}`, detail 비어있지 않음. gate 경로(`_require_project_exists`→`core_sot.get_project`, main.py:2000–2001)가 failing repo를 관통함을 구조로 확인.
- **under-strict(실증)**: 신규 절 제거 시 `AssertionError: 502 != 503` — 저장소 예외가 광의 `except Exception → 502`로 떨어져 **pre-fix 버그 정확히 재현**. 절이 503 발화의 load-bearing임 증명. (작업자는 503→599 mutation으로 bite를 실증했다 기술했으나, 본 검증은 절 제거→502로 더 충실한 under-strict를 직접 실증.)
- **over-strict(실증)**: `test_analysis_run_endpoint_maps_provider_exception_to_502`·`_maps_real_provider_error_to_502`(test_application_api.py:1368·1392, `ApplicationApiTest` 클래스) — run endpoint 관통, provider 실패 502 단정 — 신규 절 존재 하에 **2 passed**. 신규 storage catch가 ProviderError를 503으로 삼키지 않음 확인.
- 테스트 docstring에 under/over-strict 양방향이 명시됨(test_application_api.py:2762–2766). parametrized가 아닌 단일 케이스(+0 subtest) — 이것이 "1470 passed / 579 subtests(직전 1469/579 대비 +1 passed, +0 subtest)"를 정확히 설명.

### 5. 공개 계약/생성 타입 — schema.d.ts no-diff 실증
- `gen:api`(`frontend/package.json:11`: `dump_openapi.py > openapi.json && openapi-typescript openapi.json -o src/api/schema.d.ts`)로 working-tree(신규 절 포함)에서 OpenAPI 재생성 → `frontend/src/api/schema.d.ts` tracked 버전과 `diff`: **NO DIFF(byte-identical)**.
- `git status`로 `frontend/openapi.json`(미추적/gitignored)·`frontend/src/api/schema.d.ts`(추적) 모두 **무변경** 확인. → 신규 절은 runtime 동작만 바꾸고 OpenAPI 메타데이터에 영향 없음(선언 무변과 일치).

### 6. 회귀 기준선 — 보고 카운트와 정확 일치
- `tests/test_application_api.py -q`: **120 passed, 261 subtests**(작업자 보고 120/261과 정확 일치).
- 전체 `tests/ -q`(test-mongo 기동): **1470 passed, 1 skipped, 579 subtests, 610.77s**(작업자 보고 1470/1/579와 정확 일치). delta = +1 passed(1469→1470), subtest 무변(579), skipped 무변(1) = 신규 회귀 1건이 전량 설명, 타 영역 회귀 **0**.

## Issues / Risks

### Blocking (계약 의무) — **없음**
boundary matrix의 모든 "should fire / should NOT fire" 분기가 코드·회귀에 매핑됨:
- 저장소 예외→503(should fire): 신규 절 + 신규 회귀(under-strict 실증). ✓
- ProviderError→502(should NOT fire for storage): 기존 회귀 2건(over-strict). ✓
- runner 미구성→503(구성 face, should NOT be swallowed): pos 6 재raise + 기존 `test_context_search_503_uses_the_configuration_face` 계열 선례(run은 `runner is None` 경로). ✓
- NotFound/Duplicate/Extraction/generic Exception 매핑: 기존 회귀 유지(전체 suite green). ✓
계약 필수 lock 누락 0건. 변경 카운트/선언/생성 타입 무변이 실측으로 확인됨.

### Hardening recommendations (비차단)
- **H1 — 작업자 rationale의 사실 오류(정확성)**. 작업자 보고: "이 repo에 CHANGELOG.md는 실제로 존재하지 않아(HANDOFF가 참조만 함)". **실제로 `CHANGELOG.md`는 190KB로 존재**(마지막 갱신 commit `759a835`, head 항목 v1.7.35). 다만 CHANGELOG.md가 v1.7.38·v1.7.39·v1.7.40을 **모두 누락**한 채 SoT 변경이력만 갱신되어 온 것은 v1.7.38부터의 기존 관행(선행 커밋 `946150d`·`a18ed16`도 CHANGELOG.md 미갱신)이므로, 행동(CHANGELOG 미갱신) 자체는 선행례와 일치하고 슬라이스 계약 위반이 아님. 다만 "존재하지 않는다"는 근거 진술이 틀렸으므로, 향후 오너가 CHANGELOG.md를 계약 로그로 계속 유지할지 SoT 변경이력으로 일원화할지 방향 결정이 유의. (본 검증은 사실만 정정하고 자의적 보강은 하지 않음.)
- **H2 — 패턴 스윕 잔여: context-search `persist_rejection` 경로(동일 구조 패턴)**. `main.py:3336–3342`(context-search endpoint)의 inner broad `except Exception → GateFindingError → (외부 `except GateFindingError → 502`, main.py:3352)는 run과 **구조적으로 동일한 근본 패턴**이다: `gate_findings.persist_rejection`(저장소 write) 중 pymongo 에러가 광의 catch에 흡수되어 GateFindingError로 wrapping→502로 재분류되며, 전역 503 handler에 도달하지 못한다. 기존 `test_gate_finding_persistence_failure_is_502`(test_context_search_api.py:219)가 502를 단정하지만, 그 fixture `_FailingGateFindingService.persist_rejection`은 **`RuntimeError`를 던지므로 pymongo(저장소) 서브케이스는 미검증**이다. 즉 canonical store failure가 context-search persist_rejection 경로에서 502로 빠질 수 있는 잔여 갭이 존재한다.
  - **왜 비차단인가**: (a) 본 슬라이스(B)는 run endpoint에 한정되며 context-search(Phase 4)는 범위 밖, (b) 기존 테스트가 persist_rejection 실패→502를 **의도적으로 pin**하여 gate-finding 영속 실패를 502 semantic으로 설계한 것으로 보임, (c) SoT 본문 자체는 "runtime 저장소 실패가 전 경로 503"을 주장하지 않고 "60개 operation이 503을 **선언**"(main.py 선언 영역) + "run→503"만을 단정하므로 계약 위반이 아님. 단, HANDOFF "지금 상태"·work_log(work_log.md:355)의 "**저장소 503 face가 이제 예외 없이 전 endpoint 균일**하다" 서술은 context-search persist_rejection을 고려하면 **약간 과한 표현**이다. 권고: (i) persist_rejection에 pymongo 에러를 주입하는 케이스를 추가해 502 vs 503 중 계약 의도를 확정하거나, (ii) SoT 본문에 gate-finding 영속 실패의 502 예외를 명시해 "균일" 서술과 정합시키거나, (iii) 최소한 HANDOFF의 "예외 없이 균일"을 "run의 502 예외는 소멸(선언은 60개 균일)"로 좁혀 정확히 기술. 오너 결정 사항.
- **H3 — 관찰(결함 아님)**: 선행 work_log 노트(work_log.md:325)가 "(B) 시 트랙별 runtime 가드에 run 케이스 추가"를 제안했으나, 작업자는 parametrized 가드(`test_storage_failure_is_503_from_routes_across_every_track`, 6 트랙)에 run을 넣지 않고 **전용 독립 테스트**를 추가했다. run은 다른 6개와 메커니즘이 달라(local clause vs 전역 handler) 전용 테스트가 under/over-strict를 더 명시적으로 문서화하므로 정당한 선택. 단, parametrized 가드는 여전히 gate 경로만 sweep하므로 "새 endpoint가 광의 except로 저장소를 삼키는" drift를 잡지 못한다 — 이는 v1.7.39의 기존 한계(본 슬라이스 미도입).

## Verdict — **합격(Pass)**

슬라이스 자체 계약을 전부 충족한다:
- 코드 구조가 boundary matrix의 should/should-NOT-fire 전 분기와 정합(except 순서·적용 범위·본문 형태).
- 작업자의 핵심 주장 "선언 무변(코드가 선언을 따라잡은 것)"을 실측으로 확인(`_ERRORS_400_404_409_502_CONFIG`가 `503: _CONFIG_503` 포함, diff +12/−0).
- `gen:api` 재생성 schema.d.ts **no-diff(byte-identical)**, openapi/schema.d.ts 무변경.
- 회귀 신규 1건 under-strict(절 제거→502 재실패)+over-strict(provider→502 유지) 양방향 bite 실증.
- 보고 카운트 정확 일치(test_application_api.py 120/261, 전체 1470/1/579; delta +1 = 신규 회귀, 타 회귀 0).
- SoT 변경이력·본문·Phase 2A 3곳 내부 정합, 모순 0.

조건 없는 합격. H1(rationale 사실 오류)·H2(context-search 잔여 패턴 + "균일" 과잉 서술)·H3(parametrized 가드 미확장)는 모두 비차단 hardening/관찰이며, H2는 오너 인지 후 별도 슬라이스/계약 명확화 대상이다. 본 슬라이스의 계약 의무는 blocking finding 없이 충족됐다.

## Outstanding items

- **미커밋 작업**: 슬라이스 5개 파일(main.py·test_application_api.py·system-contract-sot.md·HANDOFF.md·work_log.md)이 working tree에 uncommitted. 작업자는 "커밋 지시 있으면 커밋" 상태로 보류 중 — 본 검증은 파일을 건드리지 않았음(`git diff --numstat main.py` = +12/−0, mutation cycle 흔적 없음으로 최종 확인).
- **오너 후속 결정 후보(H2)**: context-search persist_rejection의 저장소(pymongo) 서브케이스 502/503 의도 확정 — 별도 슬라이스.
- **검증 중 도입·즉시 정정한 사항**: under-strict mutation 후 절 복원 시 주석에 `__storage_note` 오타를 도입했으나 즉시 `_with_storage_note`로 정정하고 `git diff`로 무결성 재확인(최종 diff clean). 작업자 산출물에 영향 없음.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
# 전제: test-mongo 기동 확인 (없으면 docker compose -f docker-compose.test.yml up -d)
docker ps --format '{{.Names}}\t{{.Status}}' | grep test-mongo   # Up (healthy) 이어야 함

# 1. 신규 회귀 단독 (503)
python3 -m pytest tests/test_application_api.py::CanonicalStoreFailureHandlerTest::test_run_endpoint_narrows_storage_failure_to_503_despite_broad_except -x -q

# 2. over-strict (provider -> 502 유지)
python3 -m pytest tests/test_application_api.py -k "test_analysis_run_endpoint_maps_provider_exception_to_502 or test_analysis_run_endpoint_maps_real_provider_error_to_502" -q

# 3. under-strict mutation (절 제거 -> 502 재실패): main.py:2582~2593 except _STORAGE_ERRORS 절 삭제 후
python3 -m pytest tests/test_application_api.py::CanonicalStoreFailureHandlerTest::test_run_endpoint_narrows_storage_failure_to_503_despite_broad_except -x -q   # 기대: FAILED 502 != 503

# 4. application API 전수
python3 -m pytest tests/test_application_api.py -q   # 기대: 120 passed, 261 subtests

# 5. 전체 backend 기준선
python3 -m pytest tests/ -q   # 기대: 1470 passed, 1 skipped, 579 subtests

# 6. schema.d.ts no-diff
cd frontend && python3 ../scripts/dump_openapi.py > openapi.json \
  && npx openapi-typescript openapi.json -o /tmp/schema.d.ts.regen \
  && diff src/api/schema.d.ts /tmp/schema.d.ts.regen && echo "NO DIFF"
```
