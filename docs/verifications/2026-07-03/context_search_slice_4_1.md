# Verification — Phase 4 Slice 4.1 context search

## Subject metadata

- 검증일: 2026-07-03
- 요청자: owner ("클로드 작업 AI가 작업한 분에 대해서 검증하고 의심하고 또 의심해줄래?")
- 검증자: 독립 검증 AI(Claude, 작업 AI와 다른 세션)
- 대상 slice/artifact: Phase 4 Slice 4.1 — `services/application/app/context_search/`(신규) + `services/application/app/indexing/service.py`(`query_similar` 추가) + `tests/test_context_search.py`(신규 24개) + 결정 8건 브리프/SoT 반영(v1.6.30/31)
- 정본 계약 참조:
  - `docs/plans/04-agentic-search-kickoff-decisions.md`(상태 `Approved for Phase 4 first slices (2026-07-03)`) — §1/§2/§2.1/§3/§4/§5/§6/§7/§8/§9(Slice 4.1 범위 + 회귀 목록)
  - `docs/system-contract-sot.md` v1.6.30, v1.6.31(§Phase 4, §미확정 결정 목록, changelog)
  - `docs/plans/04-agentic-search.md`(§착수 전 결정사항 8개 항목)
- 검증 대상 작업 출처: working tree, uncommitted(`git status` — context_search/ 신규 untracked, indexing/service.py·문서 7종 modified). 커밋 안 됨(작업자 명시 대로).

## Scope

1. 도메인 계약: `context_search/models.py` — purpose/need/tool/status/error enum literal, `ContextSearchRequest`/`SearchPlan`/`ContextItem`/`ContextPackage`/`GateDecision` 구조.
2. 오케스트레이션: `context_search/service.py` — stale guard → SOT 재조회 흐름, index text 미사용, SOT block kind 결정적 경계, retriever 실패 degraded+taxonomy, SOT 실패 전체 실패, planner 주입.
3. Context Gate: `evaluate_context_gate()` 독립 재검증(cross-project / SOT reload 증거 / candidate 라벨 / stale / budget).
4. `InMemoryVectorIndexAdapter.query_similar()` 표면 + 기존 Phase 3A/Core SOT 회귀 무손상.
5. 회귀 24개 — boundary matrix(should-fire / should-NOT-fire 양방향) 추적.
6. 전체 suite 실행 카운트 재현.
7. 결정 8건 반영 정합성(brief/plan/SoT/CHANGELOG/HANDOFF/work log) + 계약 자기 모순.
8. 작업자 meta-주장(stale 행 발견, "435 통과") 사실 확인.

## Methodology

- 계약 스코프를 먼저 좁혔다: 브리프 §9 Slice 4.1 범위 + 회귀 목록, §6 fallback/error taxonomy, §1/§5/§8 literal 집합, SoT v1.6.30/31 changelog와 §Phase 4 절만 종단 독해. 무관한 prior ideation(`agentic_search_flow.md` §7 전체)은 스코프 밖.
- boundary matrix를 계약에서 구축한 뒤 코드와 테스트에 매핑. "테스트가 초록" ≠ "계약이 잠겼다"를 구분.
- 경험적 probe(독립 Python 스크립트)로 의심 경로를 실제 구동: (a) `_BrokenSotRepository`가 `get_blocks`에서 `RuntimeError`를 던질 때 SOT_ERROR 매핑 여부, (b) toggle repo로 index build는 정상·reload는 고장 상태에서 vector 경로 동작.
- 테스트 실행: `python3 -m unittest tests.test_context_search -v`, `python3 -m pytest -q`(전체), `python3 -m unittest discover -s tests`.
- 코드 catch 표면 grep: `service.py`의 `except` 종류/위치, Mongo repository의 pymongo 예외 래핑 여부.
- 문서 정합은 `git diff HEAD`로 전체 diff를 읽어 교차 검증.

사용한 정확한 명령은 §Reproduction에 열거.

## Findings

### 1. 도메인 계약(models.py) — 계약 부합

- §1 purpose `writing_context` 1종 ✓ (`ContextSearchPurpose`, models.py:22-23).
- §1 need 4종 `current_scene`/`recent_scenes`/`event_context`/`source_quote` ✓ (`ContextNeed`, models.py:26-30).
- §5 status 라벨 `candidate`/`canonical` ✓ (`ContextItemStatus`, models.py:38-40). candidate는 첫 slice에서 package에 들어가지 않지만 라벨 필드는 계약에 열려 있음.
- §6 error taxonomy `backend_error`/`system_error`/`llm_error`/`sot_error` 4종 ✓ (`ContextSearchErrorType` StrEnum, models.py:43-49).
- §9.1 `ContextSearchRequest(project_id, purpose, needs, query, current_position, context_budget)` ✓ (models.py:76-83). `current_position: CurrentPosition | None`이되 `_validate_request`가 MACRO_NEEDS 요청 시 필수화(service.py:165-170) — 계약 부합.
- §9.1 `ContextPackage(project_id, purpose, macro/micro/constraints/do_not_use, trace, degraded, status="candidate")` ✓ (models.py:143-154).
- §9.5 `GateDecision(pass/reject + findings)` ✓ (models.py:163-166).

**경미한 명명分歧(비차단, 관찰)**: 브리프 §9.1 스케치는 `ContextItem(status, text, pointers, source_refs)`라 적었으나, 구현은 `ContextItem(need, status, text, pointer[singular], snapshot_id, sot_reloaded, token_estimate, source_ref_ids)`다. 복수 `pointers` → 단수 `pointer: IndexPointer`, `source_refs` → `source_ref_ids`. gate 검사에 필요한 보조 필드(need/snapshot_id/sot_reloaded/token_estimate)가 추가됐고 본질(status/text/pointer/source refs/candidate-canonical 라벨)은 보존됐다. 스키치 대 정의 차이로, 계약 의미 위반은 아니다.

### 2. 오케스트레이션(service.py) — 대부분 부합, **SOT 백엔드 다운 경로에 계약 위반 존재**

부합하는 계약:
- §9.2 planner 주입형 Protocol ✓ (`SearchPlanner`, service.py:78-79). planner 예외 → `LLM_ERROR` (service.py:172-179).
- §9.3 vector hit → `validate_source_block_record()` stale guard → SOT 재조회 → ContextItem ✓ (service.py:254-286). **index hit text 미사용** ✓ — `_item_from_block`은 SOT block의 `block.text`만 쓴다(service.py:367-381).
- §9.3 Mongo direct 경로 `current_scene`/`recent_scenes`는 `current_position` 기준 version snapshot에서 조회 ✓ (service.py:317-357).
- §9 "SOT block kind 기반 deterministic 경계(AI split 없음)" ✓ — `_split_scene_blocks`는 `BlockKind.HEADING`/`SCENE_MARKER`를 경계로 삼고 AI 추론 없음(service.py:416-440).
- §9.4 deterministic ranking(need 우선순위, need 내 도착순=유사도순 보존 via stable sort) + 문자수 기반 token 추정 + budget 초과 항목 통째 제외 ✓ (`estimate_tokens` service.py:88-89, `_rank`/`_apply_budget` service.py:383-413).
- §6 vector retriever 실패 → `degraded=true` + `BACKEND_ERROR` trace ✓ (service.py:230-252, 132-134).

**[차단급 발견 #1] SOT 백엔드 다운(non-NotFound repository 예외)이 `sot_error`로 매핑되지 않고 처리 없이 탈출한다.**

- 계약(§6 채택 + SoT v1.6.31): "Mongo SOT reload 실패는 성공 package로 위장하지 않고 전체 실패" + "`sot_error`(Mongo SOT reload 계열)". 즉 SOT reload 실패는 (a) 전체 실패이고 (b) `error_type=SOT_ERROR` lineage를 가져야 한다(이 lineage가 §6 enum 확장의 사유="이후 retry 로직이 error 계열에 따라 재시도 대상을 고를 수 있도록").
- 구현: SOT reload catch 표면은 `except NotFound`(→ None/제외)와 `except CoreSotError`(→ `SOT_ERROR`) 뿐이다(service.py:298-304 vector reload, service.py:328-332 mongo position reload). `validate_source_block_record`(service.py:257, vector 경로)는 `get_snapshot`→`get_blocks`를 호출하지만 **어떤 try 블록 밖**이며, indexing service의 `validate_source_block_record` 자체도 `NotFound`만 잡는다(indexing/service.py:544-).
- Mongo repository(`core_sot/mongo_repository.py`)는 `get_snapshot`/`get_blocks`/`get_version` 주변에서 pymongo 예외를 `CoreSotError`로 래핑하지 않는다(`ConnectionFailure`/`PyMongoError` import 0회; 잡는 건 `OperationFailure`:109, `DuplicateKeyError`:250/288 뿐이고 이들도 get_blocks/get_snapshot/get_version 경로가 아님). → 실가동 Mongo 장애 시 pymongo 예외가 원형 그대로 전파.
- 경험적 확인(probe): 유효 version_id + `get_blocks`가 `RuntimeError`를 던지는 repo에서
  - MONGO position reload 경로 → `UNCAUGHT RuntimeError`로 `build_context_package`를 빠져나감(`ContextSearchFailed(SOT_ERROR)` 아님).
  - VECTOR hit reload 경로(toggle repo로 build는 정상·reload는 고장) → 동일하게 `UNCAUGHT RuntimeError` 탈출(`validate_source_block_record` 단계).
- 영향 평가: "성공 위장 금지" 하위 조항은 탈출 예외라도 지켜진다(가짜 package 반환 아님). 그러나 **`sot_error` lineage 하위 조항이 위반**된다 — 호출자가 `error_type`으로 retry 대상을 고를 수 없고 원형 pymongo/`RuntimeError`를 받는다. 이것이 §6 enum 존재 사유 자체를 무력화.
- 오늘 폭발 반경: context_search는 아직 어떤 caller에도 연결되지 않음(HTTP surface 없음, Slice 4.2가 다음). 즉 잠재 결함이되, §6가 명시적으로 미래 retry-lineage targeting을 위해 설계됐고 Slice 4.2+에서 live caller가 붙으면 즉시 발현.
- **boundary matrix 빈 칸**: "SOT 백엔드 다운 → sot_error 전체 실패" 분기에 대응하는 회귀가 없다.

**[발견 #2, #1과 직결] 기존 테스트 `test_sot_reload_failure_surfaces_sot_error_not_fake_success`는 이름/fixture가 암시하는 분기를 검증하지 않는다.**

- 테스트는 `_BrokenSotRepository`(get_blocks `RuntimeError`)를 쓰지만 `version_id="missing-version"`을 줘서, `get_draft_version`이 `_repo.get_version()`에서 `None`을 반환 → `raise NotFound`(core_sot/service.py:263) 경로를 탄다. `NotFound`는 `CoreSotError` 하위(core_sot/service.py:40)라 `except CoreSotError`에 잡혀 `SOT_ERROR`로 매핑.
- 즉 **`_BrokenSotRepository.get_blocks`의 `RuntimeError`는 이 테스트에서 절대 도달하지 않는 dead code**다. 테스트가 잠근 것은 "NotFound → sot_error"이지, 이름과 fixture가 의도한 "SOT 백엔드 다운 → sot_error"가 아니다.
- 이것이 정확히 CLAUDE.md 검증 가이드가 경고하는 함정: "초록 테스트 = 계약 검증" 아님. 회귀 가드는 있되(NotFound 경로), boundary matrix의 의도된 칸(백엔드 다운 경로)은 비어 있다.
- 결과: #1의 코드 결함 + #2의 테스트 결함이 한 쌍. 둘 다 해소 전까지 해당 boundary는 잠기지 않는다.

**[발견 #3, 비차단 관찰] NotFound 처리가 vector 경로와 mongo 경로에서 상충한다.**

- vector reload: `except NotFound` → `return None` → hit를 `snapshot_missing`으로 **soft 제외**(degraded=false)(service.py:298-299, 269-273).
- mongo position reload: NotFound(누락 version) → 전파 → `except CoreSotError` → **`SOT_ERROR` 전체 실패**(service.py:328).
- 같은 "SOT에 없는 참조"를 두 경로가 다르게 처리한다. 계약(§6)은 NotFound를 명시적으로 다루지 않으므로 **spec-silent-but-code-enforced divergence**다. vector의 soft 제외(index drift로서의 합리적 해석)와 mongo의 hard 실패(요청 자체 malformed로서의 합리적 해석) 각각은 방어 가능하나, 분기가 문서화되지 않았고 양쪽 모두에 대해 "이것이 정한 동작이다"를 고정하는 회귀가 없다(vector NotFound 경로는 회귀로 직접 잠기지 않음). 계약 보강 후보.

**[발견 #4, 비차단 관찰] `system_error` literal이 정의됐으나 한 번도 생산되지 않는다 — 그리고 #1이 바로 그 자리다.**

- §6 enum 4종 중 `backend_error`/`llm_error`/`sot_error`는 코드에서 생산되지만 `system_error`("orchestration/코드 계열")는 service.py 어디에서도 발화하지 않는다(grep 0건 사용).
- §6가 "4종으로 시작"이라고 했으므로 첫 slice에서 전부 생산할 의무는 없다. 단, **#1에서 잡히지 않고 탈출하는 orchestration-lineage 실패가 바로 `system_error`가 분류하려던 것이며**, 분류되지 않은 채 탈출한다는 점에서 #1과 인과로 연결된다. 수정 시 #1을 `system_error`로 분류할지 `sot_error`로 넓혀 잡을지 owner 결정이 필요할 수 있다(계약 수준 결정).

### 3. Context Gate(`evaluate_context_gate`) — 계약 부합

- orchestration flag를 신뢰하지 않고 SOT 재조회로 재검증 ✓ — cross-project(service.py:457-465), SOT reload 증거 부재 `sot_reloaded=False`(service.py:466-473), candidate 라벨 금지(첫 slice)(service.py:474-481), stale 재검출(snapshot 누락/content_hash drift/block 소실/project archived/draft archived)(service.py:497-549), budget 초과(service.py:483-491).
- "loop preflight가 Gate를 대체하지 않는다" ✓ — `evaluate_context_gate`는 package/request/core_sot만 받고 orchestration 내부 상태를 참조하지 않는다.
- 경미: `_gate_stale_findings`가 item마다 `get_project`/`get_draft`를 중복 조회(service.py:531-548). 정합성 문제는 아니고 효율 관찰.

### 4. `query_similar()` + Phase 3A 무손상 — 부합

- `InMemoryVectorIndexAdapter.query_similar(project_id, vector, limit)` 추가 — cosine, `(-similarity, record.id)` deterministic 순서, project-scoped, `limit<1` → `ValueError`(indexing/service.py diff).
- 유사도 계산은 context_search가 아닌 adapter 계층 소유 → 실제 Chroma 도입 시 같은 표면 교체 가능(브리프 의도 부합).
- 기존 회귀 무손상: 전체 pytest `391 passed, 44 skipped`(초록). diff는 가산적(신규 method + `_cosine_similarity` helper + `import math`)이고 기존 method 변경 없음.
- 회귀 `test_query_similar_is_project_scoped_and_bounded`는 project-scoping + limit 상한 + `limit=0` ValueError를 잠근다.

### 5. 회귀 24개 boundary matrix 추적 — 양호, 단 §9.6 한 분기(#1/#2) 누락

테스트 수: ContextSearchPackageTest 16 + ContextGateTest 6 + TokenEstimateTest 1 + VectorQuerySimilarTest 1 = **24** ✓.

§9.6 회귀 목록 ↔ 테스트 매핑:
1. project isolation → `test_project_isolation_excludes_other_project_records`(under-strict ✓).
2. archive/drift 후 stale hit 제외(guard 경유) → `test_stale_hits_after_archive_are_excluded_with_reason_in_trace`(under-strict ✓) + `test_fresh_hits_are_not_wrongly_excluded_as_stale`(over-strict ✓).
3. SOT reload 실패 sot_error 전체 실패 → `test_sot_reload_failure_surfaces_sot_error_not_fake_success`. **[빈 칸]** — NotFound 경로만 잠금; 백엔드 다운 경로 미잠금(#1/#2).
4. budget 양방향 → `test_budget_includes_high_priority_and_excludes_overflow_bidirectional`(양방향 ✓).
5. retriever 실패 degraded + 계열 error → `test_vector_backend_failure_marks_degraded_with_error_taxonomy`(BACKEND_ERROR ✓) + `test_successful_run_is_not_marked_degraded`(over-strict ✓).
6. 빈 결과 trace → `test_empty_result_step_is_explainable_in_trace` ✓.
7. Gate reject 양방향 → `test_gate_passes_normal_package`(should-NOT-fire ✓) + reject 5종(cross-project/sot-reload/candidate/stale-archive/budget ✓).
8. 부가: planner 실패/plan literal 위반 3종 `llm_error`(`test_planner_failure_maps_to_llm_error`, `test_plan_with_disallowed_tool_for_need_is_llm_error`, `test_plan_for_other_project_or_unrequested_need_is_llm_error`), wall-clock 초과, invalid request 3종, token 추정 deterministic — 모두 계약 대로.

한 테스트 안에 양방향을 같이 넣은 회귀(budget, need-priority)는 under/over-strict가 한 fixture 안에서 같이 검증되어 인상적.

### 6. 전체 suite 카운트 — **"435 통과(44 skip)" 표현 부정활**

- `python3 -m pytest -q` → **391 passed, 44 skipped, 1 warning**(suite는 green).
- `python3 -m unittest discover -s tests` → "Ran 435 tests ... OK (skipped=44)".
- 작업자의 "전체 회귀 435개 통과(44 skip)"는 unittest 출력 "Ran 435 ... skipped=44"를 "435 통과"로 오독한 것이다. 실제 passed는 **391**(44는 skip). HANDOFF Verification 절과 work log에 같은 표현이 전파됐다.
- 실질 주장(suite green, 44 skip)은 참이지만, reported-number 정확성 검증 관점에서 passed 카운트가 44 과잉이다. 차단 사유는 아니고 기록 정정 권고.

### 7. 결정 8건 반영 + 계약 자기 모순 — 부합

- 브리프 상태 `Approved for Phase 4 first slices (2026-07-03)`, Owner decisions 섹션에 8건 근거 포함 ✓.
- §2 터미널 JSON planner 확정 + §2.1 tool-call 전환 계획 추적 ✓ — "LLM tool-call 미가용 시 우회" 패턴 문서화.
- §6 error taxonomy 4종 enum 계약화 ✓.
- §8 "이후 slice에서 C(Writing/Analysis 비교용 모두) 완성" 의무 → SoT §미확정 결정 목록("ContextPackage의 Analysis 비교용 확장 필드 … 완성은 추적 의무") + HANDOFF Next Tasks #2 + work log Decisions에 추적 항목으로 박힘 ✓.
- plan 04 §착수 전 결정사항 8개 항목 전부 [x] 처리 + 브리프 참조 ✓.
- SoT v1.6.30/31 changelog + §Phase 4 절 갱신 + 버전 bump(v1.6.29→v1.6.31) ✓.
- CHANGELOG 3건, HANDOFF(Owner Decisions 없음 복귀, Next Tasks 1순위=Slice 4.2, 구조표 context_search/ 추가) ✓.
- 계약 자기 모순: 브리프/SoT/plan 간 §6 error taxonomy literal, §1 need/purpose literal, §8 추적 의무가 일치. 내부 모순 발견 안 됨.
- 단, SoT v1.6.31 changelog/§6 문구("SOT reload 실패는 sot_error 전체 실패다")와 #1 코드 동작(백엔드 다운 시 sot_error 아닌 탈출)이 **불일치** — 이것이 계약 대 코드 불일치(자기 모순은 아니고 구현 결함).

### 8. 작업자 meta-주장 확인 — 정확

- "SoT 현재 구현 상태 표에 'Phase 2~6 미구현' stale 행 존재, 범위 밖이라 건드리지 않음" → **사실 확인**(system-contract-sot.md:410 "Product Shell UI/Phase 2~6 | 미구현 | 계획 문서만 존재"). Phase 2A/3A/3B/4.1이 구현됐음에도 요약 표는 갱신 안 됨(사전 문서 부채, 작업자가 정확히 관찰·보류). 솔직한 보고.

## Issues / Risks

- **[차단급] SOT 백엔드 다운 경로 → sot_error 미매핑(코드 + 회귀) [#1, #2]**: §6/SoT v1.6.31이 "SOT reload 실패 = sot_error 전체 실패"라 계약화했으나, `CoreSotError`가 아닌 repository 예외(pymongo 등)는 `except CoreSotError`에 잡히지 않고 원형으로 탈출한다. 오늘 caller가 없어 잠재적이나, §6 enum의 존재 사유(retry-lineage targeting)를 무력화하고 Slice 4.2+에서 발현. 기존 회귀는 의도(백엔드 다운)가 아닌 NotFound 경로만 잠근다.
  - 해소 옵션(소유자 결정 필요 영역): (a) SOT reload catch를 `CoreSotError`에서 더 넓히거나 non-NotFound 예외를 명시 잡아 `sot_error`(또는 `system_error`) 매핑, (b) Mongo repository가 pymongo 예외를 `CoreSotError`로 래핑하도록 변경(표면 넓음, 별도 slice 검토), (c) 최소 — 회귀를 NotFound가 아닌 진짜 백엔드 예외 주입으로 고쳐 boundary를 잠그되 매핑 방침은 owner 확정. 어느 쪽이든 boundary matrix 빈 칸을 채워야 slice 종료.
- **[비차단] NotFound 경로 상충 [#3]**: vector(soft 제외) vs mongo(전체 실패). 문서화 + 양쪽 회귀 또는 계약 보강 권고.
- **[비차단] `system_error` 미사용 [#4]**: 첫 slice 의무는 아니나 #1 수정 시 매핑 계열(sot vs system) 결정 필요.
- **[비차단] reported number 부정확 [#6]**: "435 통과" → "391 passed / 44 skipped"로 HANDOFF/work log 정정 권고.
- **[비차단, 사전 부채] SoT §현재 구현 상태 표 stale 행 [#8]**: Phase 2A/3A/3B/4.1 반영 안 됨. 별도 정리 권고(작업자 이미 인지).
- **[비차단, 명명] `ContextItem` 필드명 divergence [#1 find. 경미]**: 브리프 스케치 `pointers`/`source_refs` vs 구현 `pointer`/`source_ref_ids`. 본질 보존.

## Verdict

**조건부 합격(conditional pass).**

slice의 도메인 계약, orchestration 흐름(stale guard → SOT 재조회, index text 미사용, deterministic scene 경계, deterministic ranking/budget), Context Gate 독립 재검증, `query_similar` 표면, Phase 3A 무손상, 결정 8건 반영, 회귀 24개의 양방향 분기 커버리지는 모두 계약에 부합하고 우수하다. suite는 green.

그러나 **§6 "SOT reload 실패 = sot_error 전체 실패" boundary의 백엔드-다운 분기가 코드에서 구현되지 않았고(`CoreSotError` 외 예외 탈출), 회귀도 의도(백엔드 다운)가 아닌 NotFound 경로를 잠그고 있어 이 boundary는 사실상 잠기지 않았다 [#1, #2]**. CLAUDE.md 검증 원칙("초록 테스트 ≠ 계약 검증", "untraced branch는 blocking", boundary matrix 빈 칸 금지)에 따라, 합격 조건은 다음이다:

- (필수) SOT 백엔드 다운(non-NotFound repository 예외) → sot_error(또는 owner 결정된 계열) 전체 실패 boundary를 코드에서 구현하고, 진짜 백엔드 예외를 reload 시점에 주입하는 회귀(under-strict: 매핑 삭제 시 재실패 + over-strict: 정상 reload는 통과)를 추가할 것. 기존 `_BrokenSotRepository` 테스트의 의도/동작 일치도 같이 맞출 것.

비차단 항목(#3 NotFound 상충 문서화, #4 매핑 계열, #6 카운트 정정, #8 stale 행, 명명)은 본 slice 종료 조건은 아니나 후속/별도 정리 권고.

## Outstanding items

- 작업 미커밋(작업자 명시). owner가 게시 승인 시 커밋.
- #1/#2가 해소되기 전에 Slice 4.2(터미널 JSON planner adapter, live Gateway smoke)가 live caller를 붙이면 SOT 백엔드 다운 시 원형 예외가 상위로 새어 나갈 수 있음 — Slice 4.2 착수 전에 #1/#2 해소를 권장.
- #8 stale 행(Phase 2~6 미구현) 정리 여부는 owner 판단. 작업자가 "다음에 정리할지 알려달라"고 보류 중.

## Reproduction

전체 회귀 + 카운트:
```
python3 -m unittest tests.test_context_search -v        # 24개 (신규)
python3 -m pytest -q                                     # 391 passed, 44 skipped
python3 -m unittest discover -s tests                    # Ran 435 ... OK (skipped=44)
```

#1/#2 경험적 probe(MONGO 경로, 백엔드 다운이 sot_error로 잡히는지 — 잡히지 않음을 확인):
```python
# 유효 version_id + get_blocks RuntimeError repo로 build_context_package(CURRENT_SCENE) 호출
# → UNCAUGHT RuntimeError (ContextSearchFailed(SOT_ERROR) 아님)
# (본 기록 §Findings #1에 사용한 스크립트; 핵심은 version_id를 "missing"이 아닌 실재 값으로 줘야
#  get_version()이 None이 아니라 get_blocks()까지 도달한다는 점)
```
VECTOR 경로 probe는 toggle repo(build 시 정상, reload 시 get_blocks RuntimeError)로 동일 결론.

코드 catch 표면 / Mongo 래핑 확인:
```
grep -n "except NotFound\|except CoreSotError\|except Exception" \
  services/application/app/context_search/service.py
grep -c "ConnectionFailure\|PyMongoError" \
  services/application/app/core_sot/mongo_repository.py    # 0
```

위생: `git diff --check` — CLEAN.
