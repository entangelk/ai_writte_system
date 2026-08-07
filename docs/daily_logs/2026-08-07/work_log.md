# 2026-08-07 작업 로그

## Goals

- 라우터 분해 **Slice 1 잔여 도메인** 착수 — 2026-08-06 에 선행(H-3-A 공유 prelude
  추출)이 닫히면서 "기계적"이 된 구간이다.
- 한 번에 다 옮기지 않는다. **작은 도메인 4종을 먼저 옮겨** 제품 route 의 이동
  패턴(공유 직렬화기 처리·유료 경로·소유권 tier)을 한 번 확정한다.

---

## Task 1 — health · memory · observability · context-search 이동 (`b6eec79`)

### User Decisions and Rationale

- 오너 지시는 *"핸드오프와 어제자 데일리로그 확인해서 다음작업 진행하자"* 뿐이었고,
  **다음 작업의 지목은 문서가 이미 하고 있었다** — HANDOFF `Next Tasks` 2번과
  2026-08-06 work_log Task 5·6·7 의 `Next steps` 가 셋 다 **라우터 분해 잔여 7 도메인**
  을 첫 항목으로 적는다. 새 결정 브리프가 필요한 fork 가 아니라고 판단해 브리프 없이
  착수했다(R1·A1 은 2026-08-05 에 이미 확정).
- **슬라이스 크기는 구현자 판단으로 작게 잡았다.** 잔여 64 operation 을 한 번에
  옮기는 것이 기술적으로 불가능하지는 않지만, 이 저장소의 관례가 "중간 독립 검증
  단위를 작게"이고(8.2 범위 결정과 같은 근거) 제품 route 는 auth·admin 과 달리
  **공유 직렬화기**를 끌고 있어 첫 이동에서 그 처리 방식이 정해진다.

### Completed work

**5 operation · 4 도메인**을 `main.py` 밖으로 옮겼다. in-routers **12 → 17**.

| 새 파일 | operation | 협력자 |
|---|---|---|
| [`routers/health.py`](../../../services/application/app/routers/health.py) | `GET /health` (1) | 없음 |
| [`routers/memory.py`](../../../services/application/app/routers/memory.py) | `GET …/memory` · `GET …/memory/{id}` (2) | `core_sot`·`memory` |
| [`routers/observability.py`](../../../services/application/app/routers/observability.py) | `GET …/observability/kpi` (1) | `core_sot`·`llm_call_audit`·`writing_loop_audit` |
| [`routers/context_search.py`](../../../services/application/app/routers/context_search.py) | `POST …/context-search` (1) | `core_sot`·`memory`·`analysis`·`context_search`·`gate_findings`·`llm_call_audit` |

그리고 **공유 직렬화기 3종**을 신설
[`api/payloads.py`](../../../services/application/app/api/payloads.py) 로 추출했다 —
`_project_brief_payload` · `_memory_payload` · `_scope_payload`.

- `main.py` **4,808 → 4,534줄**(−274).
- `evaluate_context_gate` patch 대상 **3곳**을 새 모듈 경로로 갱신
  ([`test_context_search_api.py:247·278·297`](../../../tests/test_context_search_api.py#L247)).
- 이동으로 미사용이 된 `main.py` import **6개** 제거(`asdict`·`aggregate_kpi`·
  `GateFindingError`·`evaluate_context_gate`·`ContextSearchHttpRequest`·
  `ObservabilityKpiResponse`). **기존 미사용분 21개는 손대지 않았다**(아래 Issues).

### Decisions (구현자 판단)

- **★ 공유 직렬화기를 `api/payloads.py` 로 내리는 것은 취향이 아니라 강제다.**
  `routers/*` 는 `from ..main import` 를 되살릴 수 없고(2026-08-06 순환 폐쇄),
  이동한 handler 가 쓰는 이름은 전부 `main` 밖에 있어야 한다. 그런데
  `_memory_payload`·`_scope_payload`·`_project_brief_payload` 는 **이동분과 잔류분이
  둘 다** 쓴다(analysis apply · project brief 4곳). 어느 한쪽에 두면 방향이 뒤집힌다 —
  `env.py` 를 `api/` 밖에 둔 것과 **같은 형태의 문제, 같은 처방**이다.
- **반대로 한 도메인만 쓰는 것은 내리지 않았다.** `_context_item_payload` ·
  `_context_trace_payload` · `_context_package_payload` · `_build_context_search_request`
  는 context-search 만 쓰므로 그 라우터 모듈 안에 뒀다. 전부 `api/` 로 모으면
  **`payloads.py` 가 두 번째 `main.py`** 가 된다 — 이 슬라이스가 없애려는 것이 그것이다.
- **직렬화기 이름의 밑줄을 유지했다**(`_memory_payload`). 모듈 공개 심볼로 승격하면서
  이름을 다듬으면 handler 본문이 byte-동일이 아니게 되고, R1 이 지문 diff 로 무변을
  증명하는 근거가 약해진다. 선례(`_ERRORS_401`·`_REQUIRE_AUTH`)와도 일치한다.
- **`CHANGELOG.md` 는 갱신하지 않았다.** 가이드가 *"major design or feature changes
  (not every small edit)"* 로 한정하고, **직전 두 리팩터(2026-08-05 라우터 분해
  `e8b9908` · 2026-08-06 공유 prelude 추출 `2f20fbb`)도 항목이 없다**. 계약·제품
  표면이 한 자리도 안 바뀐 내부 이동이라 선례를 따랐다 — 검증자가 "기록 누락"으로
  읽지 않도록 여기 남긴다.
- **`main.py` 의 기존 미사용 import 21개는 손대지 않았다**(`datetime`·`Header`·
  `BaseModel`·`AdminAuditEvent` 등, 어제 prelude 추출의 잔재로 보인다). CLAUDE.md §3
  대로 **내 변경이 만든 6개만** 지웠다. 정리는 별도 슬라이스 사안이다.

### Verification

- **행위 무변** — [`repro_router_split.py`](../../verifications/2026-08-05/repro_router_split.py)
  지문 pre/post **diff 없음**. route **76** · order-sensitive pairs **0** ·
  `app.openapi()` sha256 무변 · 해석된 dependency 트리 무변.
  - **order-sensitive pairs 가 0 인 것이 이번엔 실제 검사였다.** HANDOFF 가
    *"`{project_id}` 를 쓰는 도메인이 옮겨가면 그 실행에서 다시 본다"* 고 예고한
    자리이며, `{project_id}` 를 쓰는 route 가 register 로 나간 것은 이번이 처음이다.
- **본문 byte-동일 전수** — 이동한 정의 **12/12**. 그중 모듈 수준으로 내려간 3종은
  **들여쓰기 한 단계를 제외하고** 동일하다(중첩→모듈 이동에서 불가피한 유일한 차이).
- 집중 스위트: `test_context_search_api` · `test_memory_api` · `test_app_import_paths`
  · `test_billable_actions` · `test_auth_api` · `test_docs_indexes` →
  **170 passed / 1,097 subtests**.

### 뮤테이션

**커밋 → 뮤테이션 → 원복 순서 준수** — `b6eec79` 커밋 후 `git status --short` 빈 것을
확인하고 시작했다(CLAUDE.md §6 게이트).

| # | 뮤테이션 (적용한 diff) | 위치 | 재실패한 셀 |
|---|---|---|---|
| M1 | `from ..api.payloads import _memory_payload` → `from ..main import _memory_payload` (순환 복귀) | [`routers/memory.py:21`](../../../services/application/app/routers/memory.py#L21) | `test_app_import_paths.py` **5 cells 전부** — `test_the_fully_qualified_name_loads` · `test_the_short_package_name_also_loads` · `test_the_module_runs_as_a_script` · `test_the_short_name_load_keeps_the_routers_in_one_tree` · `test_a_router_module_loads_before_main`(subtest `module=…routers.memory`) |
| M2 | `register_memory(app, …)` 호출 삭제 (operation 76 → 74) | [`main.py`](../../../services/application/app/main.py) `create_app` | `test_auth_api.py::CombinedBoundaryMatrixTest::test_every_operation_lands_in_exactly_one_named_tier` + `test_memory_api.py` **11 cells**(promotion·review·auto-promote 계열) |
| M3 | `dependencies` 를 `[enforce_quota, *소유권]` 순서로 뒤집기 | [`routers/context_search.py:156`](../../../services/application/app/routers/context_search.py#L156) | `test_quota_enforcement_api.py::BillableRouteWiringTest::test_enforcement_is_declared_after_ownership` **subtest 1개만**(`operation=('/projects/{project_id}/context-search','post')`) |
| M4 | `except _STORAGE_ERRORS: raise` 절 제거 (방어 제거 방향) | [`routers/context_search.py:191`](../../../services/application/app/routers/context_search.py#L191) | `test_context_search_api.py::ContextSearchApiTest::test_gate_finding_storage_failure_is_503` **1개만** |
| M5 | 공유 `_scope_payload` 에서 `scope_id` 키 누락 | [`api/payloads.py:61`](../../../services/application/app/api/payloads.py#L61) | `test_analysis_compare_api.py::AnalysisCompareApiTest::test_promoted_character_memory_serializes_scope` **1개만** |

- **M3·M4 는 "1개만"이 좋은 결과다** — 이동한 route 하나의 성질을 그 route 의 셀
  하나가 정확히 잠근다는 뜻이고, 넓은 셀이 여러 개를 흡수하고 있지 않다는 뜻이다.
- **M2 의 tier 전수 가드가 문 것이 register 누락의 방어선이다.** 잔여 4 도메인을
  옮길 때 register 호출을 빠뜨리면 도메인 셀보다 **이 셀이 먼저** 이유를 말해 준다.
  **[2026-08-07 독립 검증 정정]** 종전 이 줄은 *"`76 operation` 이 안 맞는다고"* 라
  적었으나, 실측으로 먼저 물리는 것은 **project-tier 카운트**
  ([`test_auth_api.py:1215`](../../../tests/test_auth_api.py#L1215)의
  `len(by_tier["project"]) == 61` → `59 != 61`)이고 `len(tiers) == 76` 은 그 다음
  줄이다. 셀이 문다는 사실은 같지만 **실패 메시지가 말해 주는 숫자가 다르다** —
  register 를 빠뜨린 사람이 실제로 보게 될 것은 61 쪽이다.
- **over-strict 방향**: M3 의 정상 순서(소유권 → 시행)는 통과하고, M1 의 정상
  상대 import(`..api.payloads`)도 통과한다. `payloads.py` 를 쓰지 않고 각 라우터가
  사본을 갖는 형태도 **테스트는 통과한다** — 그래서 공유는 테스트가 아니라
  M5 가 증거다(아래).

### 회귀 기준선

**backend test-mongo ON `2197 passed / 1 skipped / 2159 subtests`.**

- **★ HANDOFF 에 적혀 있던 기준선 `2196/1/1933` 은 이미 낡은 값이었다.** 어제
  `abcface` 가 `test_docs_indexes.py` 에 셀 1개 + subtest 222개를 더했는데
  (어제 work_log Task 6 이 `12 passed / 10 subtests` → `13 / 232` 로 기록한다)
  **기준선 줄이 갱신되지 않았다**. 2196+1 / 1933+222 = **2197 / 2155** 이며,
  이 슬라이스 착수 직후 실측이 정확히 그 값이었다(1015.72s).
- 거기서 **subtests +4 는 전부 M1 이 드러낸 가드 보강**이다 —
  `test_a_router_module_loads_before_main` 이 이제 라우터 모듈 **6개 전부**를
  도므로 subtest 2 → 6. **셀 수(2197)와 operation 수(76)는 한 자리도 안 변했다.**
- 종전 값 이력: 2197/1/2155(착수 직전 · `abcface` 반영) ·
  2196/1/1933(공유 prelude 추출 시점 실측 · 이후 `abcface` 미반영) ·
  2193/1/1931(H-3) · 2191/1/1931(8.2c hardening).
- **최종 실측 888.60s**(착수 직후 1015.72s — 같은 셸·같은 test-mongo, 부하 차이).
- **★ 숫자 주장 세 곳을 함께 고쳤다**: 이 로그 · [`HANDOFF.md`](../../../HANDOFF.md)
  회귀 기준선 줄 · 최상위 [`README.md:88`](../../../README.md#L88) 절차 표 ②.
  README 의 그 칸은 **어떤 가드도 안 덮는 유일한 숫자 주장**이며(2026-08-06 이
  추적 부채로 올린 항목), 실제로 `2,196/1,933` 에 얼어 있었다.

### Issues found — ★ 라우터 로드 가드가 `admin`·`auth` 두 개만 보고 있었다

M1 을 처음 돌렸을 때 **5 cells 중 4개만 재실패**했다. 통과한 하나가
`test_a_router_module_loads_before_main` — 이 셀의 **자기 주장이 바로 그것**
(*"라우터 모듈을 먼저 import 해도 뜬다"*)인데, 목록이
`("…routers.admin", "…routers.auth")` **하드코딩**이라 오늘 늘어난 4개 모듈은
검사 대상이 아니었다.

- **다른 4 셀이 물었으므로 이 뮤테이션이 샌 것은 아니다**(그 넷은 `main` 을 로드하고
  `main` 이 새 라우터를 import 하므로 순환이 그대로 드러난다). 문제는 **셀이 잠근다고
  적힌 성질과 실제로 잠그는 범위가 어긋났다는 것**이고, 이것은 2026-08-06 이
  *"가드는 통과하는데 이유가 낡은"* 형태로 기록한 것과 같은 병이다.
- 처방: 목록을 `routers/*.py` 글롭으로 바꿨다. **사람이 갱신해야 하는 가드는
  갱신을 잊는 쪽으로만 조용히 약해진다** — 잔여 4 도메인이 들어올 때 자동으로
  범위에 든다.
- 보강 후 M1 재실행: **5 cells 전부 재실패**, 그중 이 셀은
  `SUBFAILED(module='…routers.memory')` 로 **어느 모듈이 범인인지까지** 말한다.

### Issues found — `_require_project_exists` 사본이 4벌 생겼다

이동한 도메인마다 `core_sot.get_project(project_id=project_id)` 한 줄짜리 클로저가
필요하다. 그대로 두면 잔여 4 도메인까지 **8벌**이 되고, *"없는 project 는 404"* 라는
한 줄 계약이 갈라질 자리가 8개 생긴다.

- `api/dependencies.py::project_existence_check(core_sot)` **factory 하나**로 합쳤다.
  FastAPI dependency 가 아니라 handler 가 직접 부르는 평범한 클로저라 factory 형태다.
- **이 슬라이스에서 처리한 이유**: 다음 도메인 이동이 이 패턴을 4번 더 복제한다.
  한 번 복제되고 나면 되돌리는 비용이 8배가 된다.
- 지문은 그대로 **IDENTICAL** — 해석되는 dependency 트리도 응답도 안 바뀐다.

### Issues found — 공유가 진짜 공유인지는 M5 가 증명했고, 겸사겸사 공백도 드러났다

`api/payloads.py::_scope_payload` 에서 `scope_id` 를 빼자 재실패한 셀은
**`test_analysis_compare_api.py` 한 개**다. 두 가지를 동시에 말한다.

- **좋은 쪽**: 뮤테이션은 `api/payloads.py` 에 넣었는데 문 것은 **아직 `main.py` 에
  남아 있는 analysis 도메인의 셀**이다. 즉 이동분과 잔류분이 **같은 정의 하나**를
  본다는 것이 실측됐다 — 사본 두 벌이었다면 이 셀은 통과했을 것이다.
- **드러난 공백**: `test_memory_api.py` 는 M5 아래서 **전부 통과했다**(23 passed).
  즉 내가 옮긴 `GET …/memory`·`GET …/memory/{id}` 의 응답에 `scope.scope_id` 가
  실린다는 것을 단정하는 셀이 **없다** — 그 성질은 analysis 쪽 셀에 **전이적으로만**
  걸려 있다. **이 슬라이스가 만든 결함은 아니다**(이동 전에도 없었다). 다만 분해
  때문에 *"memory 응답을 위해 `payloads.py` 를 고쳤는데 analysis 셀이 깨진다"* 는
  형태로 **드러나게 됐다**. 추적 부채로 옮긴다.

### 아직 안 한 것 (의도)

- **잔여 3~4 도메인**(projects·drafts·analysis·writing) 은 안 옮겼다. 남은 것이
  **59 operation** 이고 `main.py` 의 부피 대부분이 그쪽이다.
- **Slice 2(`create_admin_app()`)** 도 안 건드렸다. 이 슬라이스와 직교다.

### Next steps

1. **잔여 도메인 이동** — `projects`·`drafts`·`analysis`·`writing` (**59 operation**).
   이제 패턴이 셋 다 정해졌다: ① 공유 직렬화기는 `api/payloads.py`, 도메인 전용은
   그 라우터 ② `_require_project_exists` 는 `project_existence_check(core_sot)`
   ③ 각 이동 후 `repro_router_split.py` 지문 diff. **`writing` 이 가장 크고**
   (`_writing_*_payload` 9종·유료 5경로) 거기서 `_draft_payload`·
   `_analysis_job_payload` 가 다시 공유 대상으로 올라온다.
2. **Slice 2(`create_admin_app()`)** — 이 슬라이스와 직교이며 선행은 H-2(shim
   drift 가드) 하나다.
3. **이 슬라이스는 독립 검증 대기** 상태다. 다음 세션이 검증자라면 여기부터 본다 —
   대상 커밋 2개(`b6eec79`·`925a321`), 재현은 `repro_router_split.py` 지문 diff 와
   위 뮤테이션 표 5종. **→ Task 3 에서 닫혔다(합격 `06e7440`).**

---

## Task 2 — 독립 검증 반영 (`06e7440` 대상) · 비차단 2건 폐쇄

독립 세션이 **합격 · Blocking 0** 으로 검증했다
([기록](../../verifications/2026-08-07/router_split_slice1_remainder_1st.md)).
6개 축을 전부 재실측했고, **repro 지문이 못 보는 빈칸을 AST 비교로 닫은 것**과
**패치 타깃 스윕**(이동 심볼을 `app.main.<…>` 로 patch 하는 테스트 0건 확인)은
구현자가 안 쟀던 축이다. 재현 스크립트 2종(`repro_byte_identical.py` ·
`repro_mutations.py`)을 커밋해 뒀다 — 메모리 규칙
`verification-repro-scripts-must-be-committed` 를 지킨 형태다.

### User Decisions and Rationale

- 오너 지시: *"검증기록 확인해서 보강할 부분 보강해줘."* 판정이 **합격**이므로
  슬라이스를 되돌리는 일은 없고, **비차단 지적 2건을 닫는 것**이 작업 범위다.

### Completed work

| 지적 | 처리 |
|---|---|
| ① `GET …/memory` 응답의 `scope` 를 단정하는 셀이 없다 | [`test_memory_api.py`](../../../tests/test_memory_api.py) 에 `MemoryReadScopeSerializationTest` **3 cells** 신설 |
| ② (화술적) M2 서술이 "76 operation 이 안 맞는다"고 적었는데 실제로는 project-tier 카운트가 먼저 물린다 | Task 1 뮤테이션 절을 정정 — 실패 메시지가 말하는 숫자는 **61** 이다 |

### ★ 검증자가 "별도 계약 확인 필요"로 남긴 것 — 확인했고, 계약이 있다

검증 기록은 *"현재 spec 이 이 필드를 강제하는지는 별도 계약 확인 필요"* 라며
셀 추가를 조건부로 권했다. **정본에 있다** —
`system-contract-sot.md` **v1.6.42**(Phase 2B.3 D2=A/D5=A)가 결정적 scope key 를
도입하며 *"`MemoryEntry` 에 `scope` 필드 추가, 2B.1 승격이 candidate→memory 시
산출(D5=A, Mongo round-trip · **`_memory_payload` 포함**)"* 이라고 **직렬화기를
이름으로 지목**한다. 따라서 이 셀은 없던 계약을 새로 만드는 것이 아니라
**이미 있는 계약을 잠그는 것**이다.

### 신설 셀이 잠그는 것 (두 방향)

- **under-strict** — `scope_type`/`scope_id` 중 하나라도 빠지면 앞의 두 셀이 재실패.
  `scope_id` 는 정규화된 identity key 이므로(`"  Ariel   Song "` → `"ariel song"`)
  표시용 이름으로 바뀌는 회귀도 여기서 잡힌다.
- **over-strict** — `event_observation`·`open_question_observation` 은
  `derive_scope` 가 **의도적으로 `None`** 을 준다(엔티티 id 가 없다). "scope 가
  비었으니 채우자" 는 과잉 교정을 세 번째 셀이 문다. 키가 **사라지는 것**과 값이
  **null 인 것**도 구분해 단정한다 — 프런트에게 전자는 "아직 안 왔다", 후자는
  "없다"이기 때문이다.

### 뮤테이션 (2종 · 신설 셀 검증)

**커밋 → 뮤테이션 → 원복 순서 준수.** 원복 후 `payloads.py` 가 HEAD 와 byte-동일함을
`diff` 로 확인했다(`git diff --stat` 일치는 증거가 아니다 — 가이드 §Mutation testing).

| # | 뮤테이션 | 위치 | 재실패한 셀 |
|---|---|---|---|
| H1 | `_scope_payload` 에서 `scope_id` 키 제거 (검증자 M5 재현) | [`api/payloads.py:61`](../../../services/application/app/api/payloads.py#L61) | `test_reading_one_memory_carries_the_deterministic_scope` · `test_listing_memory_carries_the_deterministic_scope` **2개** |
| H2 | `scope is None` 일 때 `{"scope_type":"unknown","scope_id":""}` 를 채우는 과잉 교정 | 같은 함수 | `test_a_taxonomy_without_identity_serializes_scope_as_null` **1개만** |

**H1 은 검증자가 M5 로 돌렸을 때 이 파일이 23 cells 전부 통과했던 바로 그
뮤테이션이다** — 이제 2 cells 가 문다. 그것이 이 hardening 의 전부다.

### Verification

- `tests/test_memory_api.py` **23 → 26 passed**(+3 cells).
- **전수 회귀 `2200 passed / 1 skipped / 2160 subtests`**(831초, test-mongo ON).
  Task 1 의 `2197/1/2159` 에서 **셀 +3 은 전부 신설 `MemoryReadScopeSerializationTest`**
  이고, **subtest +1 은 코드와 무관하다** — 검증자가 자기 기록을 등재하면서
  검증 기록이 **222 → 223건**이 됐고 `test_docs_indexes.py` 의 판정 열 전수 셀이
  한 행 더 돈 것이다(그 파일 단독 `13 passed / 233 subtests`, 종전 232).
  **이 subtest 수는 검증 기록을 쓸 때마다 1씩 오른다** — 회귀로 오독하지 않도록
  HANDOFF 기준선 줄에도 적었다.
- 숫자 주장 세 곳(이 로그 · HANDOFF 기준선 줄 · `README.md:88`)을 다시 정렬했다.

### 아직 안 한 것 (의도)

- **검증 기록 본문은 고치지 않았다.** 남의 세션 산출물이고, 판정·근거가 정확하다.
  ②의 정정은 **내 work_log 쪽**에 적었다(틀린 서술의 출처가 거기다).
- `main.py` 기존 미사용 import 21개 정리는 여전히 별도 슬라이스다(검증자도
  "기존 부채"로 확인했다).

### Next steps

- 잔여 4 도메인 이동(59 operation) — Task 1 의 Next steps 그대로.

---

## Task 3 — projects · drafts · source-refs 이동 (`131bc2a`, Slice 1 잔여 2차)

### User Decisions and Rationale

- **오너 질문: *"도메인 전부 이동한 다음에 미사용 정리하는 게 깔끔하지 않을까?"*
  → 그 판단이 맞고, 그대로 간다.** 근거 셋을 답으로 드렸다: ① 이동마다 새 orphan
  이 생긴다(1차 6개, **이번 2차 38개**) — 먼저 치워도 곧바로 다시 쌓인다
  ② import 블록은 이동이 매번 만지는 자리라 섞으면 *"이동 때문에 지운 것"* 과
  *"부채라 지운 것"* 이 한 diff 에 엉킨다(지금 이동 커밋이 지문 IDENTICAL 로
  깔끔히 증명되는 이유가 그 분리다) ③ 이동이 끝나면 `main.py` 는 조립 코드만
  남아 import 블록이 훨씬 작아진다 — 그때 한 번의 작은 diff 로 끝난다.
- 이어서 *"알아서 다음 작업 진행해줘"* 라 슬라이스 범위는 구현자 판단이다.

### Decisions (구현자 판단) — 왜 세 도메인을 한 슬라이스로 묶었나

1차(5 op)보다 큰 25 op 를 한 번에 옮겼다. 근거는 크기가 아니라 **결합도 실측**이다.

- **AST 로 잰 결과 잔여 59 route 중 도메인을 넘나드는 직렬화기는
  `_analysis_job_payload`(analysis↔writing) 하나뿐**이었다. projects·drafts·
  source_refs 는 서로 완전히 독립이고 각자 자기 직렬화기만 쓴다 — 즉 이 셋을
  나눠 옮겨도 얻는 것이 없다.
  - *주의*: 처음에 route 줄 범위로 헬퍼 사용을 셌더니 `_writing_*_payload` 가
    analysis 와 "공유"로 나왔다. **route 사이에 헬퍼 정의가 끼어 있어서 생긴
    허위**다(마지막 analysis route ~ 첫 writing route 구간에 writing 직렬화기
    정의가 산다). AST 로 handler 본문만 보면 공유는 위의 하나뿐이다.
    **줄 범위로 소속을 세면 안 된다** — 다음 도메인에서도 같은 함정이 있다.
- **projects 와 drafts 는 route 선언이 서로 끼워져 있다**(PATCH project → PATCH
  draft → DELETE project → DELETE draft → …). 도메인별로 나눠 옮기면 같은 구간을
  두 번 헤집게 되고, 그 사이 상태는 지문으로 검증하기 애매해진다. 셋을 합치면
  `main.py` 의 **연속 구간 하나**(1963~2593)를 통째로 들어내는 일이 된다.
- **모듈은 그래도 셋으로 나눴다** — 브리프가 `projects`·`drafts` 를 별도 모듈로
  적었고, 한 파일에 25 op 를 담으면 이 슬라이스가 없애려는 것을 다시 만든다.

### Completed work

| 새 파일 | operation | 협력자 |
|---|---|---|
| [`routers/projects.py`](../../../services/application/app/routers/projects.py) | 11 | `core_sot`·`access_grants`·`sync_outbox` |
| [`routers/drafts.py`](../../../services/application/app/routers/drafts.py) | 10 | `core_sot`·`sync_outbox` |
| [`routers/source_refs.py`](../../../services/application/app/routers/source_refs.py) | 4 | `core_sot`·`shared_vector_index`·`shared_embeddings`·`shared_backend` |

- in-routers **17 → 42**, 잔여 **34**(analysis 21 · writing 13).
- `main.py` **4,534 → 3,924줄**.
- 직렬화기 5종은 **전부 도메인 전용이라 `api/payloads.py` 로 내리지 않았다**.
  1차에서 정한 규칙("공유만 내린다")의 반대쪽 사례다.
- 이동으로 미사용이 된 import **38개** 제거. **기존 부채 21개는 손대지 않았다**(위 오너 판단).
  - **[독립 검증 정정 2026-08-07]** 종전 이 줄은 **22개**라 적었다. 내 AST 검출기가
    `from __future__ import annotations` 를 미사용으로 셌기 때문이며, 그것은 import 가
    아니라 **컴파일러 지시자**다. `pyflakes` F401 실측은 **21**이고 그것이 정리 슬라이스의
    정확한 출발값이다. 1차 로그가 적은 21 이 맞았고 2차에서 내가 틀렸다.
- **패치 타깃 갱신 0건** — 이동한 심볼을 `app.main.<…>` 로 patch 하는 테스트가
  없다(스윕 결과 남은 3종 `connect_chroma_collection`·`_build_embedding_provider`·
  `GatewayGenerateProvider` 는 전부 `main.py` 잔류 조립부다).

### Verification

- **행위 무변** — 지문 diff 없음. **이번 비교 기준은 오늘 세션 착수 시점(`9bc06e3`
  상태)의 지문**이라 하루치(1차 + hardening + 2차) 전체가 한 번에 증명된다.
  route **76** · order-sensitive pairs **0** · openapi sha256 무변 · dependency 트리 무변.
- **이동 정의 30/30 byte-동일**(들여쓰기 정규화).
- 집중 스위트 **279 passed / 1,501 subtests**.
- **전수 회귀 `2200 passed / 1 skipped / 2163 subtests`**(829초, test-mongo ON).
  Task 2 의 `2200/1/2160` 에서 **셀 증감 0** — **25 operation 이동이 셀을 한 개도
  더하거나 빼지 않았다**(operation 76 유지의 실측은 숫자가 아니라 지문 IDENTICAL
  이지만, 셀 무변은 "테스트를 고쳐서 통과시킨 것이 아니다"의 실측이다).
  **subtest +3 은 전부 N1 이 확인한 그 글롭**이다 — `routers/*.py` 가 6 → 9개가
  되며 `test_a_router_module_loads_before_main` 이 3 subtest 더 돈다.

### 뮤테이션 (5종)

**커밋 → 뮤테이션 → 원복 순서 준수.** 원복 후 4개 파일 전부 HEAD 와 byte-동일함을
`diff` 로 확인했다.

| # | 뮤테이션 | 위치 | 재실패한 셀 |
|---|---|---|---|
| N1 | `from ..api.payloads import` → `from ..main import` (순환 복귀) | `routers/projects.py` | `test_app_import_paths.py` **5 cells**, 그중 `test_a_router_module_loads_before_main` 이 `SUBFAILED(module='…routers.projects')` |
| N2 | `register_projects(...)` 호출 삭제 | `main.py` `create_app` | `test_auth_api.py` **19 cells**(tier 전수 2 + 소유권/인증 경계 다수) |
| N3 | `list_drafts` 의 `except DraftOrderIntegrityError → 503` 절 제거 (방어 제거) | `routers/drafts.py` | `LegacyOrderedDraftMigration503Test::test_list_drafts_on_legacy_data_returns_503` · `CrudErrorBodyExactKeyTest::test_503_body` **2개** |
| N4 | rebuild 의 `EmbeddingProviderError` 매핑 502 → 500 (분류 오염) | `routers/source_refs.py` | `SourceBlockRebuildEmbeddingFailureTest::test_embedding_failure_is_502_with_the_uniform_body` **1개만** |
| N5 | `POST /projects` 의 `dependencies=_REQUIRE_AUTH` 제거 | `routers/projects.py` | `AuthenticationBoundaryTest::test_every_operation_is_either_protected_or_a_named_exemption` `SUBFAILED(path='/projects')` · `CombinedBoundaryMatrixTest::test_every_operation_lands_in_exactly_one_named_tier` |

- **★ N1 이 이 슬라이스에서 가장 값진 결과다.** 1차에서 하드코딩을 글롭으로 바꾼
  가드가 **신규 모듈 3종을 자동으로 범위에 넣었다**(모듈 6 → 9, subtest 도 6 → 9).
  *"사람이 갱신해야 하는 가드는 갱신을 잊는 쪽으로 약해진다"* 는 1차의 처방이
  다음 슬라이스에서 실제로 값을 한 것이다 — 그때 안 고쳤다면 지금 projects 에
  순환을 되살려도 그 셀은 조용히 통과했다.
- N4 가 **1개만** 문 것은 좋은 결과다(넓은 셀이 흡수하지 않는다). 반대로 N2 가
  19개를 문 것은 register 누락이 **도메인 전체를 지우는** 변경이기 때문이다.

### Issues found — 전수 회귀를 test-mongo 없이 돌려 기준선을 한 번 버렸다

첫 실행이 **`2087 passed / 114 skipped`** 로 나왔다. hardening 뒤 test-mongo 를
내려 둔 채 돌린 것이다. **합계는 2201 로 직전과 같아 셀 증감이 0 임은 읽을 수
있었지만**, 기준선으로 인용할 수 있는 값은 아니다.

- HANDOFF 가 *"skip 수는 머신·인프라 기동 여부마다 달라 같은 환경에서 비교한다"*
  고 적어 둔 그 함정이며, 이번엔 **내가 직접 내려 놓고 잊은** 경우다.
- 재발 방지로 이 로그에 적어 둔다: **전수 회귀 직전에
  `docker inspect -f '{{.State.Health.Status}}' ai_writte_system-test-mongo-1`
  를 같은 명령줄에 붙인다**(이번 재실행이 그 형태다).

### Next steps

1. **잔여 2 도메인** — `analysis`(21) · `writing`(13). **`_analysis_job_payload`
   가 둘의 유일한 공유 직렬화기**이므로 그 하나만 `api/payloads.py` 로 내린다.
   `analysis` 는 `_transition_gate_finding`·`_review_source_pointer` 같은
   **직렬화기가 아닌 헬퍼**도 끌고 있어 1·2차보다 손이 더 간다.
2. **그 다음 = `main.py` 미사용 import 정리**(오너 판단으로 이 순서다).
3. **Slice 2(`create_admin_app()`)** — 여전히 직교.

---

## Task 4 — 2차 독립 검증 반영 (`d9ecdd1` 대상) · 비차단 3건 폐쇄

독립 세션이 **합격 · Blocking 0** 으로 검증했다
([기록](../../verifications/2026-08-07/router_split_slice1_remainder_2nd.md)).
부하 주장을 전부 반증 시도로 재실측했고, 특히 **orphan 안전을 `pyflakes` F821 로**
확인한 것은 구현자가 안 쟀던 축이다 — `main.py` 가 PEP 563(`from __future__ import
annotations`)을 쓰므로 *"import 가 된다"* 보다 **정적으로 미정의 이름이 0건**임을
보는 쪽이 강하다.

### User Decisions and Rationale

- 오너 지시: *"검증기록 확인해서 보강할 부분 보강해줘."* 이것이 검증자가 오너에게
  물은 *"repro 를 내가 올릴까, 다음 작업자가 올릴까"* 에 대한 답이기도 하다 —
  **내가 지금 올린다.**

### Completed work

| 지적 | 처리 |
|---|---|
| ① 2차의 byte-동일·뮤테이션 repro 가 커밋되지 않았다 | [`repro_byte_identical_2nd.py`](../../verifications/2026-08-07/repro_byte_identical_2nd.py)(30 def) · [`repro_mutations_2nd.py`](../../verifications/2026-08-07/repro_mutations_2nd.py)(N1~N5) 신설·커밋 |
| ② 미사용 import 카운트 22 vs 실측 21 | **21 이 맞다** — Task 3 본문 정정 |
| ③ (관찰) `docker inspect` 가 `no such object` 를 뱉었다 | **더 단순한 설명을 찾았다** — 아래 |

### Decisions (구현자 판단) — 왜 1차 스크립트를 확장하지 않고 파일을 나눴나

검증자 제안은 *"`repro_byte_identical.py` 의 TARGETS 를 30개로 확장"* 이었다.
나눠 쓰기로 했다. **두 슬라이스는 베이스 커밋이 다르다**(1차 `9bc06e3` ·
2차 `46ae980`). 한 파일에 합치면 어느 쪽 기대값인지가 인자로 갈리고, 각 검증
기록의 §Reproduction 이 *"이 명령 하나"* 를 가리키지 못한다. 슬라이스당 한
파일이면 **기대 출력이 고정된다** — 1차 `12/12`, 2차 `30/30`. 잔여 도메인
이동도 같은 형태로 하나씩 더 붙이면 된다.

### ★ 검증자 관찰 ③ 의 원인은 데몬 경합이 아니라 오타로 보인다

검증자는 `docker inspect … test-mongo-1` 이 *"찰나에"* `no such object` 를 뱉은 것을
**데몬 찰나 지연이 낸 허위 에코**로 해석했다. 그런데 같은 기록 §Reproduction (5) 의
컨테이너 이름이 **`ai_witte_system-…`**(`r` 누락)이다. 그 이름은 전이적이 아니라
**항상** `no such object` 다(실측). 그리고 그대로 두면 그 줄의 `until` 루프가
**영원히 돈다** — 재현 절차가 멈추지 않는다.

- 오타를 고쳤고, **남의 기록이라 흔적 없이 고치지 않고** 그 자리에 근거 두 줄을 남겼다.
- 내 회귀 명령의 에코는 출력 파일에 `healthy` 로 남아 있다 — 내 쪽에서 허위 에코는
  관측되지 않았다.
- **그래도 검증자의 결론(진짜 신호는 최종 skip 수)은 맞다.** 이번 슬라이스에서 내가
  기준선을 한 번 버린 것도 최종 skip 수로 드러났다(Task 3 Issues).

### Verification

- 커밋한 repro 를 **실제로 끝까지 돌렸다**(커밋만 하고 안 돌리면 같은 부채가 된다):
  - `repro_byte_identical_2nd.py` → **30/30 byte-동일**, exit 0.
  - `repro_mutations_2nd.py` → **N1~N5 전부 FAIL=True**, N1 은
    `SUBFAILED(module='…routers.projects')`, N5 는 `SUBFAILED(path='/projects')`.
    마지막 preflight 재확인까지 clean.
  - 1차 `repro_byte_identical.py` 도 여전히 **12/12**(2차 이동이 1차 산출물을 안 건드림).
- `pyflakes` F401 실측 **21**(정리 슬라이스 출발값) · F821 **0**.
- `test_docs_indexes.py` **13 passed / 234 subtests**(검증자 기록 등재로 233 → 234).

### 아직 안 한 것 (의도)

- **전수 회귀를 다시 돌리지 않았다.** 이 Task 는 `docs/` 와 repro 스크립트만
  건드렸고, 늘어난 subtest 1개는 **발원 셀에서 직접 확인**했다
  (`test_docs_indexes.py` 233 → 234). HANDOFF 기준선에는 **마지막으로 전수를 실측한
  값(2163)** 을 두고 *"지금 돌리면 2164"* 를 근거와 함께 적었다 — 추론한 수를
  실측처럼 적지 않는다.

### Next steps

1. **잔여 2 도메인** — `analysis`(21) · `writing`(13). 결합도 실측은 HANDOFF 에 있다.
2. 그 다음 **`main.py` 미사용 import 정리** — 출발값은 **21**(pyflakes F401).
3. **Slice 2(`create_admin_app()`)** — 직교.
