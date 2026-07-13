# 독립 검증 — Phase 5.8 Writing `retrieve_more` 1회 lifecycle (SoT v1.6.76)

## Subject metadata

- **Date**: 2026-07-13
- **Requester**: 오너("신규 구성요소는 Writing Gate가 아니라 … follow-up retrieval planner로 구현했습니다. … T5=B를 위해 독립 endpoint 대신 기존 /writing/revise-and-gate 내부 lifecycle으로 연결했습니다. … 변경 사항은 아직 커밋하지 않았습니다. 검증해줘.").
- **Verifier**: 독립 세션(검증자). 구현자 클레임을 반박 가설로 취급 — green bar와 무관하게 계약 경계를 깨보려 시도.
- **Target slice**: Phase 5.8 — `services/application/app/writing/retrieval.py`(신규: `TerminalJsonWritingRetrievalPlanner`·`parse_writing_retrieval_plan`·`merge_context_packages`·`WritingRetrievalPlan`), `services/application/app/writing/revise_gate.py`(`FollowupRetrievalPlanner`·`ContextPackageSearch` Protocol·`WritingRetrievalConfigurationError`·`WritingRetrievalFailure`·`run()` retrieve_more lifecycle), `services/application/app/main.py`(wiring `retrieval_planner`·`current_position`/`context_budget` 전달·`except WritingRetrievalFailure` envelope), `tests/test_writing_retrieval.py`(신규)·`tests/test_writing_revise.py`(retrieval 회귀 +B1 fix). 문서: SoT v1.6.76·`plans/05-writing-retrieve-more-decisions.md`·`plans/05-writing-ai.md`·CHANGELOG·HANDOFF.
- **Canonical spec reference**: `docs/plans/05-writing-retrieve-more-decisions.md`(Resolved, T1=B·T2=B·T3=E·T4=E·T5=B·T6=B·T7=A first→B·T8=A first→B) + `docs/system-contract-sot.md` v1.6.76(L36) + v1.6.75(교차 참조). 브리프 §"승인 후 첫 회귀 경계" 9행이 lock list.
- **Source of work**: working tree, uncommitted. HEAD=cc6913f(v1.6.74). 정본은 v1.6.76으로 갱신. 이전 검증(`writing_revise_report_gate.md`)의 B1(gate-failure report 보존 미잠금)이 본 slice에서 같이 폐쇄됐는지 함께 확인.

## Scope

1. **Spec contract** — 브리프 T1~T8·9행 매트릭스·SoT v1.6.76 changelog·v1.6.75 계약과의 내부 일관성·교차 모순. 기존 `/writing/revise`·`/writing/report`·`/writing/gate`·v1.6.75 합성 계약 무변경(T1=B 내부 lifecycle) 확인.
2. **Implementation code** — retrieve_more 분기 조건·planner 1회·targeted delta 1회·merge(dedup+budget)·reporter 재호출 0·second Gate 1회·종료 상한 1.
3. **retrieval planner/merge(R3=E·T4=E·T5=B)** — strict JSON `query+needs`, canonical 5종 허용·candidate_memory 거부·빈/중복/미지 literal 사전 실패, delta 우선 dedup+budget 재적용 merge.
4. **retrieval 실패 envelope(T7)** — planner/context 실패 → candidate+첫 Gate+`retrieval_error`(400/502/503/504 taxonomy); second Gate 실패 → 기존 `gate_error`(gate=null).
5. **Regression tests** — 9행 매트릭스가 named test로 채워지는지, guard 양방향 bite, 빈 셀 점검. **B1 fix**(gate-failure report 보존 assertion) 경험적 증명.
6. **Full/focused suite + 컴파일/whitespace + 패턴 sweep** — 917/45/194·105/93·py_compile·diff --check 재도출; report 우회/중복 합성 패턴 부재.

## Methodology

브리프 9행을 lock list로 세우고 각 셀을 named test로 추적. 핵심 적대 검증: (1) **이전 검증 B1**(gate-failure candidate 최신 report 보존)이 본 slice에서 실제로 잠혔는지 — `enriched`→`revised` mutation을 first-gate 실패 경로에 주입해 테스트가 실패하는지 경험적 증명; (2) retrieve_more lifecycle가 정확히 한 번만 수행되고 두 번째 retrieve_more가 추가 round를 만들지 않는지(T8=A first→B); (3) merge의 delta-우선·dedup·budget이 under-strict(targeted 누락 방지)·over-strict(중복/과잉 배제) 양방향으로 잠혔는지; (4) retrieval 실패 envelope가 첫 Gate를 보존하고 second Gate 실패는 gate_error로 떨어지는지.

명령(전체 재현은 §Reproduction):
- `git --no-pager diff cc6913f -- services/application/app/writing/revise_gate.py services/application/app/main.py` + 신규 `retrieval.py` 전수 독파.
- `python3 -m pytest -q ... tests/test_writing*.py`(6파일) → 105/93.
- `python3 -m pytest --ignore=tests/test_memory_mongo.py -q` → 917/45/194.
- mutation B1: `revise_gate.py` first-gate `WritingReviseGateFailure(enriched, exc)` → `(revised, exc)` 후 `test_gate_failure_returns_partial_candidate` → **5/6 subtest FAIL**(IndexError) 확인 후 원복.
- `python3 -m py_compile ...` + `git diff --check`.

## Findings

### 1. Spec contract — 일관성 PASS (단, 관찰 #1 spec-silent 항목 존재)

브리프 T1~T8·9행 매트릭스 ↔ SoT v1.6.76(L36) ↔ 코드 일치. T1~T8 결정 literal이 세 곳에서 동일. "모델=호출/응답, Application=검색·합성 순서·검증·오류 envelope·반복 한도" 원칙 유지 — retrieval planner는 query+needs 선택 1회 호출/응답, 기존 Phase 4 planner는 선택된 needs 안의 step/tool 계획, Application이 merge·budget·종료 상한 소유. T6=B(report 재사용, context-relative stale tradeoff 명시 수용)·T8=A first→B(상한 1, 두 번째 retrieve_more 종료) 양쪽에 정본·코드 일치. 정본 자기 모순 없음. **단, §Issues 관찰 #1**: planner가 `current_position` 부재 시 `MACRO_NEEDS`(current_scene·recent_scenes)를 허용 집합에서 제외하는 동작이 코드에 있으나 정본(T4=E·boundary 3 "허용 집합은 canonical 5종")에 명시 없음.

### 2. Implementation code — 계약 대조 PASS

- T1=B·T2=B: 기존 `POST /projects/{project_id}/writing/revise-and-gate`(`main.py:2580`) 내부에서 첫 GateResult 소비. 별도 endpoint/flag 미추가. 기존 `/writing/revise`·`/writing/report`·`/writing/gate` 무변경. ✓
- 분기 조건: `if (gate.decision is not WritingGateDecision.RETRIEVE_MORE or self._max_retrieval_rounds == 0): return …`(`revise_gate.py:88-90`) — retrieve_more가 아니거나 상한 0이면 v1.6.75 결과 그대로 반환. ✓
- retrieval 단계: planner 1회(`revise_gate.py:100-103`) → `build_context_package` 1회(선택 needs/query, `:104-113`) → `merge_context_packages(package, delta, max_tokens=context_budget.max_tokens)`(`:114-116`) 전체 try → `WritingRetrievalFailure(enriched, gate, exc)`(`:117-118`). second Gate는 `merged` package로 1회(`:119-124`). candidate는 줄곧 `enriched`(report 보존, reporter 재호출 0). ✓
- 종료 상한: 코드가 선형(루프 없음), ctor가 `max_retrieval_rounds not in (0,1)` 검증(`:81-82`), wiring `max_retrieval_rounds=1`(`main.py:1103`). 두 번째 retrieve_more여도 추가 round 없이 반환. ✓
- wiring: `WritingReviseGateService(retrieval_planner=retrieval_planner, context_search=context_search, max_retrieval_rounds=1)`(`main.py:1096-1107`), 의존 guard는 기존 revision/report/gate 3종 유지. endpoint가 `current_position`·`context_budget` 전달(`main.py:2680-2681`). ✓
- retrieval 실패 envelope(`main.py:2717-2746`): cause별 8분기 taxonomy(ProviderError 504/502·`InvalidWritingRetrievalPlan` 502/`invalid_retrieval_plan`·`WritingRetrievalConfigurationError` 503/`retrieval_not_configured`·`WritingRetrievalPlannerError` 503/`retrieval_planner_error`·`InvalidContextSearchRequest` 400/`invalid_context_request`·`ContextSearchBudgetExceeded` 504·`ContextSearchFailed` 502/`cause.error_type.value`·else 502/`retrieval_error`), `{candidate, gate:첫 Gate, retrieval_error}` 반환. ✓ T7 "400/502/503/504 + invalid_retrieval_plan|retrieval_planner_error|context_*" 일치.
- 예외 매핑 순서: `WritingRetrievalFailure`가 `WritingReviseReportFailure` 뒤·`WritingReviseGateFailure` 앞. second Gate 실패는 service가 `WritingReviseGateFailure(enriched, exc)`(`revise_gate.py:124`)로 → 기존 gate_error envelope(gate=null). ✓ boundary 8.

### 3. retrieval planner/merge(T3=E·T4=E·T5=B) — PASS

- `ALLOWED_WRITING_RETRIEVAL_NEEDS` = CURRENT_SCENE·RECENT_SCENES·EVENT_CONTEXT·SOURCE_QUOTE·CANONICAL_MEMORY 5종(`retrieval.py:47-53`); `candidate_memory` 제외. parser가 `ContextNeed(raw)` 후 `need not in allowed_needs` 검사(`:210-213`) → candidate_memory는 유효 ContextNeed이나 허용 집합 밖이라 `InvalidWritingRetrievalPlan`. ✓
- `parse_writing_retrieval_plan`(`:181-219`): JSON decode·schema `{query,needs}` exact·query 비공백·needs 비빈 배열·미지 literal·허용 밖·중복 각각 `InvalidWritingRetrievalPlan`. repair 1회(`:130-145`, repair parse 실패 시 전파, 루프 없음). ✓
- `merge_context_packages`(`:222-284`): scope check(project_id·purpose)·`max_tokens>0`·ordered = `delta.macro+delta.micro+base.macro+base.micro`(delta 우선)·pointer identity 4-tuple dedup·budget 초과 시 `BUDGET_EXCLUDED_REASON` exclude·macro/micro 분할·constraints/do_not_use 순서 보존 dedup·trace=delta 우선·status=base. ✓ T5=B "이전 package+delta dedup·전체 budget 재적용 단일 package".

### 4. retrieval 실패 envelope(T7) — PASS

- `test_retrieval_failure_preserves_candidate_and_first_gate`(`test_writing_revise.py:472`): planner RuntimeError → 502/`retrieval_error`, candidate claims="fresh"(report 보존), **`gate.decision=="retrieve_more"`(첫 Gate 보존)**, gate.calls=1, reporter.calls=1. ✓
- `test_retrieval_dependency_and_context_failures_are_partial`(`:491`): 4종 — (planner+context None → 503/`retrieval_not_configured`),(planner TIMEOUT → 504/`provider_timeout`),(ContextSearchFailed call2 → 502/`backend_error`),(ContextSearchBudgetExceeded call2 → 504/`context_budget_exceeded`). 각 첫 Gate 보존·candidate report 보존·gate.calls=1. ✓
- `test_second_gate_failure_keeps_latest_report_without_rereport`(`:525`): second Gate `InvalidWritingGateResult` → 502, **`gate=null`**(retrieval_error 아닌 gate_error envelope), `gate_error.type=="invalid_gate_result"`, candidate claims="fresh", reporter.calls=1. ✓ boundary 8 뒷부분.

### 5. Regression tests — boundary matrix 추적 + B1 fix 경험적 증명

| # | contract clause(브리프 9행) | named test | 상태 |
|---|---|---|---|
| 1 | 첫 Gate non-retrieve → planner/search/2nd Gate 0, v1.6.75 결과 | `test_all_gate_decisions_are_200_with_at_most_one_retrieval_round`(`retrieval.calls==0` for non-retrieve) | 잠김 ✓ |
| 2 | retrieve_more 시 planner 1회·strict JSON·빈/중복/미지 사전 실패 | `test_strict_plan_*`·`test_empty_duplicate_candidate_or_unknown_needs_are_rejected`·`test_planner_sees_all_retrieve_findings_*` | 잠김 ✓ |
| 3 | 허용 집합 canonical 5종·candidate_memory 거부 | `test_empty_duplicate_candidate_or_unknown_needs_are_rejected`(candidate_memory case) + allowed_needs prompt 검증 | 잠김 ✓ |
| 4 | 선택 needs만 targeted 1회 실행 | `test_retrieve_more_merges_and_regates_without_rereport`(`context.request.needs==(EVENT_CONTEXT,)`, `context.calls==1`) | 잠김 ✓ |
| 5 | merge dedup+budget 단일 package | `test_delta_is_prioritized_deduplicated_and_rebudgeted`(양방향 docstring) | 잠김 ✓ |
| 6 | candidate text+report 유지·reporter 0 재호출·2nd Gate 1회 | `test_retrieve_more_merges_and_regates_without_rereport`(`reporter.calls==1`, `gate.calls==2`, `gate.last_candidate.claims=="fresh"`) | 잠김 ✓ |
| 7 | 2nd Gate 5종 200·retrieve_more 반복 시 추가 round 0 | `test_all_gate_decisions_are_200_with_at_most_one_retrieval_round`(retrieve_more: `gate.calls==2`,`retrieval.calls==1`) + `test_non_retrieve_and_second_retrieve_both_stop` | 잠김 ✓ |
| 8 | retrieval 실패 → candidate+첫 Gate+retrieval_error; 2nd Gate 실패 → gate_error | `test_retrieval_failure_*`·`test_retrieval_dependency_*`·`test_second_gate_failure_*` | 잠김 ✓ |
| 9 | max_retrieval_rounds=1·identity·candidate_id null·side effect 0 | wiring hardcode + ctor 검증 + 종료 상한(#7); save spy는 PASS-gate 기존 테스트 | 상한/종료 잠김 ✓, save spy는 간접(관찰 #3) |

**B1 fix(이전 검증 조건부 합격 조건) 경험적 증명**: `revise_gate.py:87` first-gate `WritingReviseGateFailure(enriched, exc)` → `(revised, exc)` mutation 주입 시 `test_gate_failure_returns_partial_candidate`가 **5/6 subtest FAIL**(line 576 `candidate_claims[0].text=="fresh"` IndexError — revised는 claims가 비어). 즉 B1 assertion(`test_writing_revise.py:575-577`)이 유효한 under-strict guard로 작동. 원복 후 34 passed/39 subtests 정상 복귀, 잔여 없음. **이전 검증의 conditional pass 조건 폐쇄 확인.**

### 6. Full/focused suite + 컴파일/whitespace + 패턴 sweep — PASS

- focused(6파일): **105 passed / 93 subtests**(9.47s). 구현자 클레임 정확 일치. ✓
- full(`--ignore=tests/test_memory_mongo.py`): **917 passed / 45 skipped / 194 subtests**(27.28s). 구현자 클레임 정확 일치. ✓
- `py_compile`(retrieval/revise_gate/main/2 test) → OK. `git diff --check` → clean. ✓
- 합성 패턴 sweep: `/writing/revise-and-gate` 단일 endpoint, retrieval은 내부 lifecycle(T1=B). 신규 `WritingRetrievalPlanner`/`merge_context_packages`는 service 내부에서만 호출, 별도 우회/중복 경로 없음. ✓

## Issues / Risks

### Blocking (contract 의무)

- **B1(이전 검증) — 폐쇄됨**. gate-failure candidate 최신 report 보존 assertion이 추가됐고 mutation으로 bite 확인. 본 slice에서 해결. ✓

- **B2 — `MACRO_NEEDS` position-의존 제외가 spec-silent-but-code-enforced**. planner `plan()`이 `current_position is None`일 때 `ALLOWED_WRITING_RETRIEVAL_NEEDS`에서 `MACRO_NEEDS`(=CURRENT_SCENE·RECENT_SCENES, `context_search/models.py:88`)를 제외한 3종만 `allowed_needs`로 사용(`retrieval.py:114-117`). 그러나 정본(T4=E "허용 집합은 canonical 5종", boundary 3 "허용 집합은 canonical 5종뿐")은 position 조건 없이 5종을 허용 집합으로 서술. 코드가 정본보다 더 좁게 거부(reject)하므로 CLAUDE.md §5 "Spec-silent-but-code-enforced is a contract gap … resolving the ambiguity is part of the slice"에 해당. 동작 자체는 합리적(position 없이 current_scene/recent_scenes是无의미)·테스트됨(`test_planner_repairs_position_need_when_position_is_absent`)이나, 정본에 명시되지 않아 다음 검증자가 의도인지 우발인지 판단할 수 없다.
  - **권장 폐쇄(오너 결정)**: (a) 정본 보충 — T4=E·boundary 3·SoT v1.6.76에 "current_position 부재 시 current_scene/recent_scenes 제외" 1행 추가(회귀 이미 존재), 또는 (b) 코드 완화 — position 무관 5종 허용. (a)가 동작·테스트와 부합해 자연스럽다. 이것은 contract-required lock 누락이 아니라 **정본 서술 불완전**이므로, 폐쇄는 정본 1행 추가로 끝난다.

### Hardening recommendations (비차단, 정본을 넘어서는 후보)

- **H1 — endpoint 수준 retrieval taxonomy 부분 커버**. `except WritingRetrievalFailure` 8분기 중 endpoint 테스트가 잠근 것은 `retrieval_not_configured`·`provider_timeout`·`backend_error`(ContextSearchFailed)·`context_budget_exceeded`·`retrieval_error`(fallback) 5종. `invalid_retrieval_plan`·`retrieval_planner_error`·`invalid_context_request`·`provider_unavailable` 4종은 endpoint 매핑 literal이 미검증(`invalid_retrieval_plan` raising은 parser 단위 테스트가 잠금). 영향 낮음(전부 502, 단 503/400/504 변종)·envelope 구조는 잠김이므로 비차단.
- **H2 — boundary 9 retrieval 경로 side-effect spy 부재**. `test_composition_does_not_save_draft`가 PASS-gate라 retrieval 경로의 no-save/accept/Analysis를 명시 spy하지 않음. 단 service ctor가 `reviser/reporter/gate/planner/context_search`만 받으므로 구조적 도달 불가. 정본이 "side effect 0"을 더 강하게 잠그고 싶을 때 후보.
- **H3 — boundary 9 identity/candidate_id 명시 assertion 부재**. retrieval lifecycle 테스트가 `result.gate.decision`만 단언하고 `candidate_id is None`/동일 `request_id`를 명시 검사하지 않음. revise 비영속 출력에서 구조적 보장.

## Verdict

**조건부 합격(conditional pass)**.

- 이유(支点): 구현은 T1~T8·9행 매트릭스 전체에 대해 정확하고 정본과 일치하며, 917/45/194·105/93 재현, py_compile/diff --check clean, 합성 패턴 sweep PASS. **9개 boundary 모두 named test로 잠겼고**, 이전 검증 B1(gate-failure report 보존)은 본 slice에서 폐쇄됐고 mutation으로 bite를 경험적 증명.
- 단, **B2 = spec-silent-but-code-enforced contract gap**(MACRO_NEEDS position-의존 제외가 정본에 명시 없음). CLAUDE.md §5가 이 범주를 "slice 닫기 전 해결"로 규정하므로 합격이 아닌 조건부 합격. 다만 이것은 코드/lock 결함이 아니라 **정본 서술 1행 보충**으로 폐쇄되는 가벼운 조건이다(회귀 테스트 이미 존재).
- 폐쇄 조건: T4=E·boundary 3·SoT v1.6.76에 "current_position 부재 시 current_scene/recent_scenes 제외" 명시(오너가 (a)를 선택하는 경우). 또는 오너가 (b) 코드 완화를 선택하면 `test_planner_repairs_position_need_when_position_is_absent`를 그에 맞게 갱신. 어느 쪽이든 1행 수준.

## Outstanding items

- 본 slice working tree 미커밋(HEAD=cc6913f). B2 폐쇄(정본 1행) 후 커밋 권장.
- B2 폐쇄는 오너 결정 영역(정본 보충 vs 코드 완화); 검증자는 surface만.
- R5 C(다회 합성 `stages` additive)·T8 1 초과 round·persisted ContextPackage/GateRun 감사 trail은 후속.

## Reproduction

```bash
# focused (6파일)
PYTHONPATH=. python3 -m pytest -q -p no:cacheprovider \
  tests/test_writing.py tests/test_writing_accept.py tests/test_writing_gate.py \
  tests/test_writing_report.py tests/test_writing_revise.py tests/test_writing_retrieval.py
# → 105 passed, 93 subtests passed

# full non-LLM
PYTHONPATH=. python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider
# → 917 passed, 45 skipped, 194 subtests passed

# compile / whitespace
python3 -m py_compile services/application/app/writing/retrieval.py \
  services/application/app/writing/revise_gate.py services/application/app/main.py \
  tests/test_writing_retrieval.py tests/test_writing_revise.py
git diff --check

# B1 fix bite 증명(mutation; 실행 후 반드시 원복)
# services/application/app/writing/revise_gate.py first-gate(≈:87)
#   WritingReviseGateFailure(enriched, exc) → WritingReviseGateFailure(revised, exc)
PYTHONPATH=. python3 -m pytest \
  tests/test_writing_revise.py::WritingReviseGateApiTest::test_gate_failure_returns_partial_candidate \
  -q -p no:cacheprovider
# → 5 failed / 1 passed (IndexError at candidate_claims[0]) = B1 fix 유효 증명. 원복 후 6 passed.
# 원복 확인: grep -n VERIFY-MUTATION services/application/app/writing/revise_gate.py → 없음
```
