# Verification — Phase 4 Slice 4.3 context search HTTP API + async wiring

## Subject metadata

- 검증일: 2026-07-04
- 요청자: owner ("다음작업 검증해줘 Slice 4.3 개발 착수·구현·검증 완료했습니다. ... HTTP API + async wiring ...")
- 검증자: 독립 검증 AI(Claude, 작업 AI와 다른 세션; 직전 Slice 4.2 검증(`docs/verifications/2026-07-04/context_search_slice_4_2.md`)도 동일 세션)
- 대상 slice/artifact: Phase 4 Slice 4.3 — `services/application/app/context_search/service.py`(async 전환 + `_build_plan` re-raise/wrap), `services/application/app/main.py`(endpoint `POST /projects/{id}/context-search` + `_default_context_search_service` wiring + `_build_context_search_request`), `tests/test_context_search_api.py`(신규 7개), `tests/test_context_search.py`(async 전환), `tests/test_application_api.py`(analysis 정정). 브랜치 `phase4-slice-4-2-planner` 6커밋(`d0a989c`→`38ae6ed`), main 미푸시.
- 정본 계약 참조:
  - `docs/plans/04-agentic-search-kickoff-decisions.md`(상태 `Approved`) — §9.3(Slice 4.3 범위 4항 + 오류 매핑), "구현 후속 — Slice 4.3 (2026-07-04)" 단락(208–220행).
  - `docs/system-contract-sot.md` v1.6.34(changelog 36행) + §Phase 4(375–381행).
  - `services/application/app/context_search/service.py`(v1.6.31/32 — `_validate_plan`, `ContextSearchFailed`, `ContextSearchBudgetExceeded`, error taxonomy), `models.py`(`ContextSearchErrorType`, `NEED_ALLOWED_TOOLS`).
  - 직전 검증 `docs/verifications/2026-07-04/context_search_slice_4_2.md` — 차단 조건이었던 빈 셸 3종(B1 step keys exact-match / B2 non-string query / B4 empty plan_id)의 폐쇄 추적.
- 검증 대상 작업 출처: branch `phase4-slice-4-2-planner` HEAD(`38ae6ed`), working tree clean.

## Scope

1. 계약 스코핑 — Slice 4.3을 govern하는 정본 체인(§9.3 4항 → SoT v1.6.34 → §Phase 4 → service/models → 직전 4.2 검증)만 종단 독해.
2. service async 전환 — `build_context_package`/`_build_plan` async, `inspect.isawaitable` seam(sync fake + async planner 양쪽), `_build_plan`의 `ContextSearchFailed` re-raise vs wrap.
3. endpoint 오류 매핑 boundary matrix — §9.3 item 4 의 5개 매핑(400/504/502/404/503) 각각을 regression에 매핑; 빈 셸 탐지.
4. async seam 양방향 — sync fake 경로(S2) + **async planner→service 경로(S1)** 각각의 under-strict guard 존재.
5. **직전 4.2 검증 차단 조건(빈 셸 3종) 폐쇄 추적** — mutation으로 re-fail 하는지 확인.
6. create_app env wiring + analysis 정정(`assert_called_with`)의 계약 유지 여부.
7. mutation testing — endpoint 매핑 5종 + async seam 2방향 + 보강 셸 3종.
8. suite 카운트 독립 재현 + envelope 주장 정확성.
9. live/deployed 검증 주장(실제 12B, HTTP 200) — 코드가 아닌 관찰 기록인지, 문서 반영 여부.

## Methodology

- 계약 스코프 먼저 좁힘: 브리프 §9.3 4항 + SoT v1.6.34 changelog + §Phase 4 376행 + service/models 고정 literal + 직전 4.2 검증 기록만 종단 독해. Phase 2/3/5/6, §2.1 tool-call, prior-memory는 스코프 밖.
- boundary matrix 구축 후 endpoint 분기와 API 회귀 7개를 수동 매핑. "테스트 초록" ≠ "계약 잠김" 구분.
- **경험적 mutation testing**(핵심): `main.py`/`service.py`/`planner.py`를 `/tmp` 백업 후 파이썬 문자열 치환으로 guard를 무력화하고 `python3 -m unittest` 재실행, re-fail 수 기록, 복원. (a) endpoint 매핑 E1–E5, (b) async seam S1/S2, (c) 직전 4.2 빈 셸 P1–P3의 폐쇄 재실증. **guard 무력화에도 전부 통과하면 = 빈 셸**.
- 테스트 실행: `python3 -m unittest discover tests`, `python3 -m pytest -q`, `git diff --check main...HEAD`.
- 문서 정합: `git show --stat`로 live/deployed 커밋이 코드가 아닌 문서 변경인지 확인; `git diff main...HEAD`로 전체 교차 검증.

사용한 정확한 명령은 §Reproduction에 열거.

## Findings

### 1. 계약 자기 일관성 — 부합 (내부 모순 없음)

- §9.3 item 1 "build_context_package async + inspect.isawaitable + evaluate_context_gate sync 유지" ↔ `service.py:123`(`async def build_context_package`), `service.py:179-193`(`async def _build_plan`, `inspect.isawaitable`), `service.py`의 `evaluate_context_gate`(sync, planner 미호출) 일치.
- §9.3 item 2 "POST /projects/{id}/context-search, body→ContextSearchRequest, package+gate 직렬화" ↔ `main.py:852-882` endpoint + `_build_context_search_request`(main.py:887-915) + `_context_package_payload` 일치.
- §9.3 item 3 "create_app env(`LLM_GATEWAY_BASE_URL`) 기반 wiring, 미구성 503" ↔ `_default_context_search_service`(main.py:217-253, `if not base_url: return None`) + endpoint `context_search is None → 503`(main.py:863-867) 일치.
- §9.3 item 4 오류 매핑(invalid 400 / wall-clock 504 / ContextSearchFailed 502 / missing project 404 / 미구성 503) ↔ endpoint 매핑 블록(main.py:856-881) 일치. SoT v1.6.34 changelog가 동일 5매핑 명시.
- `_build_plan` re-raise/wrap 로직: planner가 이미 분류한 `ContextSearchFailed`(예: llm_error)는 re-raise, 나머지 예외만 `LLM_ERROR`로 wrap(service.py:185-193) — 브리프 "구현 후속" 212행 명시와 일치. 이는 Slice 4.2의 planner가 낸 `ContextSearchFailed(LLM_ERROR)` lineage가 service 통합 후에도 보존됨을 보장.

### 2. service async 전환 — 부합

- `build_context_package` async(service.py:123), 내부 `await self._build_plan`(service.py:128), `_execute_step_tool`/`_rank`/`_apply_budget`은 sync 유지 — planner만 async seam. evaluate_context_gate sync.
- `SearchPlanner` Protocol 반환 타입이 `SearchPlan | Awaitable[SearchPlan]`(service.py:82-84)로, sync/async 양쪽을 계약에 명시. 주석으로 seam 의도 설명.
- Slice 4.1 도메인 회귀 `ContextSearchPackageTest`/`ContextGateTest`가 `IsolatedAsyncioTestCase`로 전환되고 모든 `build_context_package` 호출에 `await`(test_context_search.py:169+). fake planner 클래스는 무수정 — `_StaticPlanner`/`_FailingPlanner`(test_context_search_api.py:62-75)가 sync `build_plan` 반환. **이것이 이 slice의 핵심 주장인 "fake planner 클래스 churn 0"을 뒷받침** — sync fake가 async service에 그대로 동작.

### 3. endpoint 오류 매핑 boundary matrix — 5매핑 중 4개 잠김, **wall-clock 504 빈 셸**

| 매핑 (§9.3 item 4) | status | regression test | mutation(E*) |
|---|---|---|---|
| invalid ValueError(미지원 need literal) | 400 | `test_unknown_need_literal_is_400` | E5-reverse ✓ |
| invalid `InvalidContextSearchRequest`(empty needs) | 400 | `test_empty_needs_is_400` | E5 re-fail ✓ |
| missing project(`NotFound`) | 404 | `test_missing_project_is_404` | E3 re-fail ✓ |
| planner 실패 `ContextSearchFailed`(llm_error) | 502 | `test_planner_failure_maps_to_502_llm_error` | E2 re-fail ✓ |
| planner 미구성 | 503 | `test_unconfigured_service_is_503` | E4 re-fail ✓ |
| **wall-clock `ContextSearchBudgetExceeded`** | **504** | **—** | **E1 빈 셸 (504→500 전부 통과)** |
| 정상 | 200 + gate | `test_returns_package_and_gate_decision`, `test_fresh_package_passes_the_gate` | over-strict ✓ |

`_require_project_exists`(main.py:405-406)가 `core_sot.get_project` → `NotFound`를 발생시키고 endpoint가 404로 매핑 — missing project 분기의 근원 확인.

### 4. 직전 4.2 검증 차단 조건(빈 셸 3종) 폐쇄 — 부합 (양방향 lock)

직전 검증(`context_search_slice_4_2.md`)이 mutation으로 실증한 3개 빈 셸이 모두 보강됨. 작업자가 보강 테스트 docstring에 "B1 should-fire"/"B4 should-fire"로 검증 기록을 역참조:

| 셸 | 보강 회귀(test_context_search_planner.py) | mutation(P*) re-fail |
|---|---|---|
| B1 step keys exact-match(extra field) | `test_step_with_extra_field_is_parse_error` | P1 ✓ (1 fail + 1 error) |
| B1 반대 방향(missing key) | `test_step_missing_required_field_is_parse_error` | (P1 커버) |
| B1 sibling(non-object step) | `test_non_object_step_is_parse_error` | (P1 커버) |
| B2 non-string query | `test_non_string_query_is_parse_error` | P2 ✓ (1 fail) |
| B4 empty plan_id(present) | `test_present_empty_plan_id_is_parse_error` | P3 ✓ (1 fail) |

over-strict 방향(valid 4-key step 통과)은 기존 `test_valid_plan_parses_literals_and_injects_project_id` + `test_plan_id_defaults_when_absent`가 커버. **양방향 lock 완비**. docstring에 "Dropping the set-equality check re-passes this"로 mutation 의존성까지 명시 — 회귀 품질 우수. 직전 검증→피드백→폐쇄 루프가 제대로 작동한 사례.

### 5. async seam 양방향 — sync 방향 잠김, **async planner→service 방향 빈 셸**

`inspect.isawaitable` seam(service.py:182)의 양쪽 분기:

| 방향 | mutation | 결과 | 의미 |
|---|---|---|---|
| sync fake(`build_plan` → SearchPlan, awaitable 아님) | S2 isawaitable→True(SearchPlan을 await 시도) | **24 fail/error** | sync seam under-strict guard ✓ |
| **async planner → service**(`build_plan` → coroutine) | S1 isawaitable→False(coroutine 미 await) | **OK(전부 통과)** | **빈 셸: service에 async planner를 주입해 await하는 단위 회귀 없음** |

S1이 통과한 이유(경험적 실증): `TerminalJsonSearchPlannerTest`는 planner를 service 없이 직접 테스트하므로 service mutation에 영향 없음. service를 거치는 모든 회귀(`ContextSearchPackageTest`, API 7개)는 **sync fake planner**만 주입. 따라서 "async planner를 service에 꽂아 `build_context_package`가 그 coroutine을 await"하는 경로 — **이 slice의 핵심 deliverable** — 를 pin하는 automated regression이 없다. deployed E2E와 live smoke가 이 경로를 실제로 돌리나 automated regression이 아니다(§Findings 9).

### 6. create_app env wiring + analysis 정정 — 부합

- `_default_context_search_service`(main.py:217-253): `LLM_GATEWAY_BASE_URL` 부재 → `None`; 존재 시 `seed_context_search_plan_template` + `GatewayGenerateProvider` + `TerminalJsonSearchPlanner` + fake vector/embeddings wiring. `LLM_GATEWAY_TIMEOUT_SECONDS`(120s 기본), `LLM_GATEWAY_MODEL`, `CONTEXT_SEARCH_PLAN_MAX_TOKENS`(1024 기본) env 인자 일치.
- analysis 정정(`test_analysis_run_endpoint_uses_env_configured_default_runner`, test_application_api.py:1148-1157): `assert_called_once` → `assert_called_with(base_url="http://gateway.test", timeout_seconds=120.0, trust_env=False)`. 주석(1150-1152)이 정정 근거 명시 — create_app이 analysis+context search **두 provider**를 만들어 call count가 2가 되므로, call count 대신 "env 구성이 provider 생성을 구동하는지"를 검증. **계약 유지**: provider가 env로 구성됨을 pin. 다만 `assert_called_with`는 마지막 호출 인자만 검증하므로 두 provider가 같은 env 인자를 쓴다는 점은 확인하나, 각 consumer 매핑까지는 검증 안 함 — 비차단 관찰.

### 7. suite 카운트 독립 재현 — 부합 (이번엔 주장 정확)

- `python3 -m unittest discover tests`: `Ran 464 tests ... OK (skipped=44)` — HANDOFF/work_log 주장("Ran 464 OK(skipped=44)")과 동일.
- `python3 -m pytest -q`: **420 passed, 44 skipped** — 464 − 44 = 420으로 주장("pytest 420 passed") 정확. 직전 slices에서 반복된 "Ran N 오독" 정정이 이번 기록에 반영됨(HANDOFF Verification 136행이 `Ran 464 OK(skipped=44)`와 `420 passed / 44 skipped`를 분리 명시).
- `git diff --check main...HEAD`: clean.

### 8. endpoint 직렬화 envelope — 부합

`test_returns_package_and_gate_decision`가 `{package, gate}` envelope을 검증: `package.{project_id, purpose, status, macro_items(non-empty), micro_evidence(non-empty), sot_reloaded=true, trace.plan.steps.{s1,s2}}` + `gate.decision ∈ {pass, reject}`. §9.3 item 2 직렬화 계약과 일치.

### 9. live/deployed 검증 주장 — 문서 기록(코드 변경 아님), 부합

- `git show --stat 38ae6ed`(4.3 live), `ab4060a`(deployed E2E): 둘 다 `HANDOFF.md` + `docs/daily_logs/2026-07-04/work_log.md`만 변경(2–3행). 실제 12B 배포 HTTP 200 / gate pass / plan `[(current_scene,[mongo]),(source_quote,[vector])]` / current_scene 2개 Mongo 서빙 / vector empty(non-persistent fake) 결과는 **관찰 기록**이지 코드/테스트 변경이 아님 — 적절.
- vector fake 한계(deployed vector need hit 없음, Mongo-direct need만 서빙)는 SoT v1.6.34 changelog와 브리프 §9.3 단락에 명시됨 — spec-silent가 아닌 문서화된 한계.
- 검증자는 sandbox TCP 제약으로 live smoke/deployed 재실행 불가. 주장은 work_log/HANDOFF 기록에 의존.

## Issues / Risks

**이슈 1 (차단, 빈 셸) — wall-clock 504 HTTP 매핑에 API 회귀 없음 (E1)**

contract §9.3 item 4와 SoT v1.6.34 changelog가 "wall-clock 504"를 명시. endpoint 매핑 코드(main.py:875-876 `except ContextSearchBudgetExceeded → 504`)는 존재하나, 이 매핑을 pin하는 API 회귀가 없다. mutation E1(504→500)으로 `tests.test_context_search_api` 7개가 전부 통과함을 실증. 도메인 회귀 `test_wall_clock_budget_exceeded_raises_budget_error`(test_context_search.py:592)는 service가 `ContextSearchBudgetExceeded`를 **raise**하는 것은 잡지만, endpoint가 그것을 **504로 매핑**하는 것은 잡지 않는다(다른 레이어). 매핑이 풀려도(예: 504→500/502) automated test가 탐지 못함.

**이슈 2 (차단, 빈 셸) — async planner→service 통합 경로에 단위 회귀 없음 (S1)**

이 slice의 핵심 deliverable("async 터미널 JSON planner를 `build_context_package`에서 await") 중 **async 방향**이 automated regression으로 잠기지 않았다. mutation S1(`isawaitable→False`)으로 service에 주입되는 async planner의 coroutine이 await되지 않아도 `tests.test_context_search` + `test_context_search_api` + `test_context_search_planner` 전부 통과함을 실증. 이유: service를 거치는 모든 회귀가 sync fake planner만 주입. async planner 자체(`TerminalJsonSearchPlannerTest` 13개)는 잠겨 있으나 service를 거치지 않고, deployed E2E/live smoke가 service+async planner를 돌리나 automated regression이 아니다. async wiring이 깨져도 deployed 실행 전까지 탐지 불가. sync 반대 방향(S2)은 잠겨 있어 양불균형.

**관찰 (비차단)**

- analysis 정정의 `assert_called_with`는 마지막 호출 인자만 검증 → 두 provider(analysis, context search)가 같은 env 인자로 생성됨은 확인하나 consumer별 매핑은 미검증. 계약 위반 아님.
- 미지원 **purpose** literal 400: need는 커버하나 purpose case는 별도 regression 없음. 다만 `_build_context_search_request`가 동일 `ValueError`→400 경로를 공유하므로 회귀 가치 낮음.

## Verdict

**조건부 합격 (conditional pass)**

이유(합격 요소):
- 계약 자기 일관성: §9.3 ↔ SoT v1.6.34 ↔ service/models/endpoint 간 모순 없음.
- service async 전환 정확 + `_build_plan` re-raise/wrap lineage 보존 로직 spec 일치.
- endpoint 매핑 5종 중 4종(502/404/503/400) under-strict guard 실증.
- **직전 4.2 검증 차단 조건(빈 셸 3종 B1/B2/B4) 양방향 폐쇄 실증**(P1/P2/P3 re-fail + docstring 역참조).
- async seam sync 방향(S2) under-strict guard(24 re-fail).
- analysis 정정 계약 유지; suite green 독립 재현(unittest Ran 464/skipped=44, pytest 420 passed — 주장 정확, count 표기 정정 반영).
- live/deployed 검증이 코드가 아닌 관찰 기록으로 문서화; vector fake 한계 spec 명시.

조건(차단, 해소 시 합격):
- **이슈 1**: wall-clock 504 매핑에 대한 API 회귀 1개 추가(예: `wall_clock_seconds`를 아주 작게 주입한 service로 `ContextSearchBudgetExceeded` → 504를 trigger하는 endpoint 테스트). mutation E1로 re-fail 확인.
- **이슈 2**: async planner를 service에 주입하는 단위 회귀 1개 추가(예: `async def build_plan`을 가진 fake planner를 `ContextSearchService`에 주입해 `build_context_package`가 200/정상 package를 반환하는지; 또는 도메인 회귀에 async fake 케이스 1개). mutation S1로 re-fail 확인.

두 회귀 모두 작은 단위 추가로 폐쇄 가능. 빈 셸 2종은 contract가 명시하는 경계(§9.3 item 4, item 1)이므로 regression 부재 시 조건부 합격.

## Outstanding items

- **빈 셸 2종(E1, S1) 회귀 추가 여부**: owner 결정 대기. 검증자는 silently fix하지 않음.
- **PR / 후속 방향**: owner가 (a) ES lexical 또는 real Chroma, (b) prior-memory purpose §8 C, (c) tool-call flat loop planner §2.1 중 선택 또는 현 시점에서 PR 생성을 결정. 검증 결과(조건부 합격 + 빈 셸 2종) 회신 후 판단 권장 — 빈 셸 2종은 PR 전 보강 권장(회귀 2개 추가).
- **브랜치/커밋**: `phase4-slice-4-2-planner` 6커밋, main 미푸시. PR 시 빈 셸 보강을 같은 브랜치에 추가 가능.
- 본 검증은 결함을 silently fix하지 않음(이슈 1·2를 owner에게 회신).

## Reproduction

```bash
# 1. suite green + 정밀 카운트
python3 -m py_compile services/application/app/context_search/service.py \
  services/application/app/main.py
python3 -m unittest discover tests        # Ran 464 OK skipped=44
python3 -m pytest -q                       # 420 passed, 44 skipped
git diff --check main...HEAD

# 2. mutation testing — endpoint 매핑(E1-E5). 백업→치환→unittest tests.test_context_search_api→복원.
#    E1 504->500 (wall-clock): expect OK => EMPTY CELL
#    E2 502->500 : expect re-fail   E3 404->400 : re-fail
#    E4 503->500 : re-fail           E5 400->500 : re-fail

# 3. mutation testing — async seam(S1/S2). target: tests.test_context_search + _api + _planner
#    S1 isawaitable->False : expect OK => EMPTY CELL (async planner path unpinned)
#    S2 isawaitable->True  : expect 24 fail/error (sync fake path pinned)

# 4. mutation testing — reinforced 4.2 cells(P1-P3). target: tests.test_context_search_planner
#    P1 keys-exact 제거 : re-fail   P2 non-str query 허용 : re-fail   P3 empty plan_id 허용 : re-fail
#    (상세 치환 스크립트는 본 검증 세션 bash 기록에 있음)

# 5. live/deployed (sandbox 밖, owner 실행). 코드가 아닌 관찰 기록(HANDOFF/work_log에 이미 반영).
```
