# Verification — Phase 4 Slice 4.2 터미널 JSON LLM planner adapter

## Subject metadata

- 검증일: 2026-07-04
- 요청자: owner ("클로드 검증 AI가 작업한 내용 확인하고 검증하고 의심하고 또 의심해줄래? ... Slice 4.2 ... 구현했습니다.")
- 검증자: 독립 검증 AI(Claude, 작업 AI와 다른 세션)
- 대상 slice/artifact: Phase 4 Slice 4.2 — `services/application/app/context_search/planner.py`(신규) + `tests/test_context_search_planner.py`(신규 13개) + `scripts/phase4_context_search_planner_live_smoke.py`(신규) + 브리프 §9.2 후속/SoT v1.6.33/HANDOFF/CHANGELOG/work_log 반영.
- 정본 계약 참조:
  - `docs/plans/04-agentic-search-kickoff-decisions.md`(상태 `Approved for Phase 4 first slices (2026-07-03)`) — §2 채택(terminal JSON + strict parse + 1회 repair, Phase 2A 패턴 재사용), §2.1(tool-call 전환 추적), §1(purpose/need/tool literal 최소 집합), §6(error taxonomy), §9.2(Slice 4.2 범위 4항), "구현 후속 — Slice 4.2 (2026-07-04)" 단락.
  - `docs/system-contract-sot.md` v1.6.33(changelog 36행) + §Phase 4(375–381행).
  - `services/application/app/context_search/models.py`(v1.6.31 고정 literal 집합 — `ContextNeed`/`SearchTool`/`NEED_ALLOWED_TOOLS`/`SearchPlan`/`SearchPlanStep`).
  - `services/application/app/context_search/service.py`(v1.6.31 — `_validate_plan` plan 의미 검증, `ContextSearchFailed`, `ContextSearchErrorType.LLM_ERROR`).
  - 인접 패턴 정본: `services/application/app/analysis/extractor.py` `VersionedPromptAnalysisExtractionAdapter`(재사용 주장의 비교 기준), `analysis/prompt_templates.py`(`PromptTemplateService.seed_template()`), `llm_gateway/app/payload.py`·`provider.py`(`ChatCompletionRequest`/`LLMProvider`/`FakeLLMProvider`).
- 검증 대상 작업 출처: working tree, uncommitted(`git status` — `planner.py`/`test_context_search_planner.py`/`phase4_context_search_planner_live_smoke.py` untracked, 문서 4종 modified). 커밋 안 됨(작업자 명시 대로).

## Scope

1. 계약 스코핑 — Slice 4.2를 govern하는 정본 체인(§9.2 → §2/§2.1/§1/§6 → SoT v1.6.33 → models/service → Phase 2A reference)만 종단 독해. 무관한 prior ideation은 스코프 밖.
2. boundary matrix 구축 — planner가 소유하는 "should fire / should NOT fire" 분기 전부와 literal(task_type, prompt_version, error_type, project_id 주입, DEFAULT_PLAN_ID)을 열거하고, 각 분기를 regression test에 매핑. **빈 셀 없음**이 합격 조건.
3. 계약 자기 일관성 — 브리프 §9.2 ↔ SoT v1.6.33 changelog ↔ §Phase 4 ↔ models ↔ service ↔ prompt template ↔ parse 코드 간 literal/분기 교차 검증. 내부 모순 탐지.
4. spec ↔ implementation literal 일치 — enum 멤버십 검증 범위, repair 1회, llm_error 매핑, retry cap.
5. Phase 2A 패턴 일관성 — 재사용 주장을 `extractor.py`와 대조; 차이점이 의도적·spec 일치인지.
6. **테스트 코드를 감사 대상으로** — assertion이 boundary를 실제로 pin하는지; under-strict(bug 재발 시 재실패) + over-strict(정상 case 잘못 거부 금지) 양방향.
7. mutation testing — guard를 풀었을 때 어떤 테스트가 re-fail하는지, 그리고 **guard를 풀어도 아무 테스트도 잡지 못하는 빈 셀**이 존재하는지 경험적 실증.
8. 전체 suite 카운트 독립 재현 + envelope count 주장 정확성.
9. live smoke 스크립트 정적 검증(미실행 사유 포함).

## Methodology

- 계약 스코프 먼저 좁힘: 브리프 §9.2 4항 + §2 채택문 + §1/§6 literal + SoT v1.6.33 changelog와 §Phase 4 375–381행, models/service의 고정 literal만 종단 독해. `agentic_search_flow.md`, Phase 2/3/5/6 섹션은 스코프 밖.
- boundary matrix를 계약에서 구축한 뒤 `parse_search_plan`/`build_plan`의 분기와 테스트 함수를 수동 매핑. "테스트가 초록" ≠ "계약이 잠겼다"를 구분.
- **경험적 mutation testing**(핵심): `planner.py`를 `cp` 백업 후 파이썬 문자열 치환으로 guard를 무력화하고 `python3 -m unittest tests.test_context_search_planner` 재실행, 어떤 테스트가 re-fail하는지 기록, `cp`로 복원. (a) 긍정 방향 5종: 잘 잠긴 boundary의 under-strict guard 존재 실증. (b) 부정 방향 3종: guard를 풀어도 13개 전부 통과하면 = 해당 boundary를 pin하는 regression이 없음(빈 셀).
- 테스트 실행: `python3 -m py_compile ...`, `python3 -m unittest tests.test_context_search_planner`, `python3 -m unittest discover tests`, `python3 -m pytest -q`(전체 정밀 카운트), `git diff --check`.
- Phase 2A 일관성: `extractor.py`의 `VersionedPromptAnalysisExtractionAdapter.extract` 흐름을 `planner.py` `build_plan`과 라인 대 라인 대조.
- 문서 정합: `git diff HEAD`로 전체 diff 읽어 교차 검증.

사용한 정확한 명령은 §Reproduction에 열거.

## Findings

### 1. 계약 자기 일관성 — 부합 (내부 모순 없음)

- §9.2 item 1 "versioned prompt template `context_search_plan_v1`(기존 `prompt_templates` 저장소 재사용)" ↔ SoT v1.6.33 changelog ↔ `planner.py:43-44`(`CONTEXT_SEARCH_PLAN_TASK_TYPE = "context_search_plan"`, `CONTEXT_SEARCH_PLAN_PROMPT_VERSION = "context_search_plan_v1"`) 일치. task_type/version literal 정확.
- §9.2 item 2 "Gateway `/v1/generate` 1-turn → SearchPlan JSON strict parse + 1회 repair(Phase 2A adapter 패턴)" ↔ `build_plan`(planner.py:95-130) 흐름 일치.
- §9.2 item 3 "유효 need/tool literal 검증: §1 집합 밖 literal이면 repair 1회, 그래도 남으면 `llm_error`" ↔ `parse_search_plan`(planner.py:182-234)의 `ContextNeed(value)`/`SearchTool(raw)` enum 멤버십 검사 + `build_plan`의 repair-then-`ContextSearchFailed(LLM_ERROR)` 매핑 일치.
- §1 literal 집합 ↔ `models.py`: `ContextNeed` 4종(`current_scene`/`recent_scenes`/`event_context`/`source_quote`, models.py:26-30), `SearchTool` 2종(`vector`/`mongo`, models.py:33-35). planner 테스트의 unknown literal(`villain_arc` need, `graph` tool)은 둘 다 enum 밖이므로 멤버십 검증 경로 탐 — 적절.
- **경계 분담 일관성**: §9.2는 adapter에게 "literal 멤버십"만, plan 의미(미요청 need / need별 불허 tool / project 일치)는 명시적으로 service `_validate_plan`(service.py:180-208) 소유로 기록(브리프 "구현 후속" 193행, SoT changelog, work_log Decisions). adapter가 `NEED_ALLOWED_TOOLS` need별 매핑을 검사하지 않는 것은 **의도적**이며 spec 일관됨. `current_scene` need에 `vector` tool이 오면 planner는 parse 성공, service가 `LLM_ERROR` reject — 이 경계는 planner 테스트에 없는 것이 **정상**(planner 책임 아님).

### 2. spec ↔ implementation literal 일치 — 부합

- `error_type = ContextSearchErrorType.LLM_ERROR`: repair 후에도 실패(planner.py:127-130), template 부재(planner.py:101-105) 모두 `LLM_ERROR` 매핑 — §6 "llm_error(planner provider 계열)" 일치.
- `project_id`는 request에서 주입, plan_id는 모델 출력: `parse_search_plan(content, project_id)`(planner.py:182, 189) — `SearchPlan.plan_id`는 root에서, `project_id`는 인자에서. §"project_id는 모델이 아니라 request에서 주입" 일치.
- `DEFAULT_PLAN_ID = "context_search_plan"`(planner.py:60): plan_id optional, 부재 시 기본값. `work_log`에 "plan_id 기본값" 명시, contract는 plan_id를 required로 명시하지 않으므로 합리적 기본.
- payload 구성: `build_context_search_plan_request`(planner.py:133-179)가 `project_id`/`purpose`/`query`/`has_current_position`/`needs`(+need별 `allowed_tools`)/`tool_literals`/`output_contract`를 JSON user payload로 — §9.2 item 2 + work_log 189행 일치.

### 3. Phase 2A 패턴 일관성 — 부합 (차이점은 모두 의도적)

`extractor.py:VersionedPromptAnalysisExtractionAdapter`와 `planner.py:TerminalJsonSearchPlanner` 대조:

- 동일: template 조회 → provider 1-turn generate → strict parse → parse 실패 시 `_repair_request`(원문 output + parser_error + 원 user payload)로 1회 repair → 재parse. repair request 빌더 구조(`_repair_request`)와 `_json_object`/`_non_empty_string` 헬퍼, `Mapping`/`Sequence` 검사 패턴이 사실상 동일.
- 차이 1(error model): Phase 2A는 `AnalysisExtractionError`(ValueError subclass)를 raise/전파 → runner failure_reason mapping으로 위임. Phase 4는 `ContextSearchFailed(ContextSearchErrorType.LLM_ERROR)`로 직접 매핑. **의도적** — §6 error taxonomy가 planner 계열 실패를 `llm_error`로 요구하므로 adapter가 계열을 확정. SoT/브리프가 명시적("template 부재도 llm_error").
- 차이 2(2차 catalog repair 없음): Phase 2A는 parse 통과 후 catalog mismatch를 한 번 더 repair(extractor.py:138-148). Phase 4는 그런 semantic 2차 검증이 없음. **의도적** — plan 의미 검증(미요청 need 등)은 service 소원이므로 adapter가 중복 검증하지 않음(설계 결정 1).
- 차이 3(repair content malformed 처리): Phase 2A `_repair_once`는 repair content가 malformed면 `AnalysisExtractionError`를 caller에 전파. Phase 4는 repair parse 실패를 잡아 `ContextSearchFailed(LLM_ERROR)`로 매핑(planner.py:124-130) — §9.2 "그래도 남으면 llm_error" 일치.

세 차이 모두 spec과 정확히 일치하며, "Phase 2A 패턴 재사용" 주장은 본질(template-based 1-turn + strict parse + 1회 repair)에서 성립.

### 4. 회귀 boundary matrix — 본질 경계는 양방향 잠김, **step-schema shape 3분기는 빈 셀**

planner가 소유하는 분기의 should-fire / should-NOT-fire 매핑:

| 분기 (planner 책임) | 방향 | regression test | 비고 |
|---|---|---|---|
| 유효 need/tool literal → parse 성공 | NOT-fire(over-strict) | `test_valid_plan_parses_literals_and_injects_project_id` | ✓ |
| 첫 응답 valid → repair 없이 1회 호출 | NOT-fire | `test_valid_first_response_parses_without_repair` | ✓ |
| prompt payload(template + needs/allowed_tools) | NOT-fire(계약 전달) | `test_prompt_carries_template_and_request_payload` | ✓ |
| unknown need literal → parse error → repair | fire(under-strict) | `test_unknown_need_literal_is_parse_error`, `test_invalid_literal_first_response_repairs_once`, `test_still_invalid_after_repair_maps_to_llm_error` | ✓ |
| unknown tool literal → parse error | fire | `test_unknown_tool_literal_is_parse_error` | ✓ |
| non-JSON / markdown fence / non-object / steps-non-array / step_id-empty / tools-empty | fire | `test_non_json_and_bad_shape_are_parse_errors`(5 subTest) | ✓ (일부 shape) |
| markdown-fenced → repair 1회 → 성공 | fire(NOT-fire 혼합) | `test_markdown_fenced_first_response_repairs_once` | ✓ |
| invalid literal → repair 1회 → 성공 | fire | `test_invalid_literal_first_response_repairs_once` | ✓ |
| repair prompt에 parser_error/invalid_output | fire(계약 전달) | `test_repair_prompt_includes_parser_error_and_invalid_output` | ✓ |
| repair 후에도 실패 → `LLM_ERROR` | fire | `test_still_invalid_after_repair_maps_to_llm_error` | ✓ |
| 정확히 1회 repair(≤2회 provider 호출) | fire | `test_does_not_retry_more_than_once` | ✓ |
| template 부재 → `LLM_ERROR` | fire | `test_missing_template_maps_to_llm_error` | ✓ |
| plan_id 부재 → 기본값 | NOT-fire | `test_plan_id_defaults_when_absent` | ✓ |
| **step keys exact-match 위반(extra/missing field) → parse error** | fire | — | **빈 셀 (B1)** |
| **query non-string → parse error** | fire | — | **빈 셀 (B2)** |
| **plan_id 빈 문자열/non-str(present) → parse error** | fire | — | **빈 셀 (B4)** |

### 5. Mutation testing 실증 결과

**긍정 방향(잘 잠긴 boundary의 under-strict guard 존재 확인)** — 각 guard 무력화 시 re-fail 수:

| mutation | re-fail | 실증 |
|---|---|---|
| need enum membership 무력화(`_need` → 항상 `CURRENT_SCENE`) | 3 failures | under-strict guard ✓ |
| tool enum membership 무력화(`SearchTool(raw)` → 항상 `MONGO`) | 2 failures | ✓ |
| repair 비활성화(첫 parse 실패 시 즉시 `LLM_ERROR`) | 1 failure + 3 errors | ✓ |
| retry cap 제거(2회차 초과 허용) | 2 errors(`FakeProviderExhausted`) | ✓ |
| template-missing → `LLM_ERROR` 매핑 제거(raw re-raise) | 1 error | ✓ |

5개 본질 boundary 모두 under-strict guard 실증 완료. 복원 후 13개 green.

**부정 방향(빈 셀 실증)** — guard 무력화에도 13개 **전부 통과**:

| mutation | 결과 | 의미 |
|---|---|---|
| step keys exact-match 제거(`set(item.keys()) != {...}` 블록 삭제) | OK(13/13) | 해당 boundary를 pin하는 regression 없음 |
| non-string query 허용(`_string(query)` → `item["query"]` 그대로) | OK(13/13) | 동일 |
| empty/non-str plan_id 허용(`_plan_id` 검사 완화) | OK(13/13) | 동일 |

세 mutation 모두 정상(valid steps)은 통과한 채로 위반 case만 잡지 못함 → contract가 요구하는 shape 경계 3종이 regression 없이 빈 셀로 남아 있음을 경험적으로 확정.

### 6. 전체 suite 카운트 독립 재현 — 부합 (정정 1건)

- `python3 -m unittest discover tests`: `Ran 452 tests ... OK (skipped=44)` — HANDOFF/work_log 주장("Ran 452 OK(skipped=44)")과 동일 재현.
- `python3 -m pytest -q`: **408 passed, 44 skipped** — "Ran 452, skipped=44"의 정확한 passed 해석은 452 − 44 = 408.
- `python3 -m py_compile`(planner/test/smoke 3종) 통과, `git diff --check` clean.

**비차단 정정**: HANDOFF line 114 / work_log line 35 / HANDOFF Verification line 134가 "Ran 452 OK(skipped=44)"를 "452개 통과(44 skip)"로 요약한 표현은 정확한 unittest 출력이나, passed count는 **408**이다. 이는 v1.6.32 검증에서 이미 지적된 "Ran N 오독" 패턴(HANDOFF line 115가 "395 passed/44 skipped"로 정정했던 것)의 동일 반복이다. 결과나 합격 여부에는 영향 없으나, 향후 기록은 passed/skipped 분리 표기를 권장.

### 7. live smoke 스크립트 정적 검증 — 부합 (미실행은 문서화됨)

- `scripts/phase4_context_search_planner_live_smoke.py`: py_compile 통과. `GatewayGenerateProvider` + in-process gateway app + `httpx.ASGITransport` 배선으로 Phase 2A live smoke와 동일 패턴. `ContextSearchFailed`를 잡아 `status=failed`/`error_type`/`detail`을, 성공 시 `plan_id`/`project_id`/`steps`를 JSON 출력 — 스크립트 자체는 contract 부합.
- 미실행 사유(sandbox 내부 Python/httpx 외부 TCP 차단 → 실제 Gateway `192.168.1.29:9080` 호출 불가)는 work_log/HANDOFF에 명시적으로 기록되어 있음. 이는 verification 차단 사유가 아니라 owner 결정 대기 outstanding item.

## Issues / Risks

**이슈 1 (차단, 빈 셀 3종) — contract 요구 shape 분기에 regression 없음**

경계 분담(adapter는 literal 멤버십만) 자체는 타당하나, adapter가 **소유하기로 한** parse 경계 중 3개에 양방향 regression이 없다. mutation으로 무력화해도 13개 테스트가 전부 통과함을 실증(§Findings 5).

- **B1 — step keys exact-match**: prompt template(planner.py:49-50 "Each step must contain exactly these fields")과 parse 코드(planner.py:203 `if set(item.keys()) != {"step_id", "need", "tools", "query"}`)는 정확 4-키 매칭을 요구. 그러나 extra field(`reasoning` 등)나 오타 키(`tool` 단수)를 reject하는 regression이 없다. LLM이 자주 extra field를 붙이는 패턴을 고려하면, 이 경계가 잠기지 않으면 추후 parser가 over-permissive하게 풀려도(또는 모델 출력 drift에도) 잡지 못한다. 영향 가장 큰 빈 셀.
- **B2 — non-string query**: contract는 "query: string" 요구, parse 코드 `_string(item["query"], "query")`(planner.py:208)가 검사하나 regression 없음.
- **B4 — empty/non-str plan_id when present**: parse 코드 `_plan_id`(planner.py:192-197)가 빈 문자열/비-str을 reject하나 regression 없음. (plan_id **부재** → 기본값 경로는 `test_plan_id_defaults_when_absent`로 잠김.)

세 분기 모두 `SearchPlanParseError`로 매핑되는 sibling이며, 일부는 enum 멤버십/다른 shape case와 helper를 부분 공유하지만, 정확 매칭(query str / keys exact / plan_id non-empty) 분기 자체는 별개 코드 경로이므로 CLAUDE.md 기준 별개 regression lock이 필요하다. "테스트가 초록"이지만 boundary matrix에 빈 셀이 존재하므로 **조건부 합격**.

**이슈 2 (비차단, 정정) — envelope count 표현**

위 §Findings 6. "Ran 452 OK(skipped=44)" 요약은 passed=408임. v1.6.32 정정의 동일 반복. 결과 영향 없음.

**관찰 (비차단, spec 일치)**

- prompt template이 모델에게 "tools: ... drawn from that need's allowed_tools"를 지시하면서, parser는 need별 매핑을 강제하지 않는다(prompt > parser 완화 방향). 이는 설계 결정 1에 따라 service `_validate_plan`이 강제하므로 안전(parser가 더 느슨하면 service가 잡음). contract 위반 아님.
- `step not a Mapping`(planner.py:201 `if not isinstance(item, Mapping)`) 분기도 명시적 regression case가 없으나, sibling shape 검증의 일부이며 B1과 동일 라인 군 — B1 보강 시 함께 cover 권장.

## Verdict

**조건부 합격 (conditional pass)**

이유(합격 요소):
- 계약 자기 일관성: 브리프 §9.2 ↔ SoT v1.6.33 ↔ models/service ↔ prompt template ↔ parse 코드 간 literal/분기 모순 없음(§Findings 1).
- 본질 planner boundary 5종(repair 정확히 1회, repair-then-`llm_error`, need/tool enum 멤버십, template 부재 `llm_error`, retry cap ≤2)을 mutation testing으로 양방향 잠금 실증(§Findings 5 긍정 방향).
- spec ↔ implementation literal 일치 + Phase 2A 패턴 일관성(차이 3종 모두 의도적·spec 일치).
- 전체 suite green 독립 재현(unittest Ran 452/OK/skipped=44, pytest 408 passed/44 skipped).

조건(차단, 해소 시 합격):
- **이슈 1 빈 셀 3종(B1 step keys exact-match / B2 non-string query / B4 empty plan_id)에 대한 양방향 regression 추가 필요.** 특히 B1은 LLM extra-field 패턴에서 실질적 회귀 가치가 높다. 추가 후 mutation 재실증으로 under-strict(bug 재발 시 re-fail) + over-strict(정상 4-키 step은 통과) 양방향 잠금 확인.

## Outstanding items

- **live smoke 미실행**(sandbox 외부 TCP 제한): owner가 승인된 네트워크에서 `scripts/phase4_context_search_planner_live_smoke.py` 실행 필요(HANDOFF Next Tasks 1). 검증자는 실행하지 않음(네트워크 제약).
- **커밋 미수행**: 작업자가 main 브랜치에서 커밋을 보류 중. 검증 결과(조건부 합격 + 빈 셀 3종)를 owner가 회수한 뒤 커밋/브랜치 결정 권고. main이므로 브랜치 분리 후 커밋 권장(작업자 제안에 동의).
- **Phase 4 후속**: HTTP API surface + `TerminalJsonSearchPlanner`의 `ContextSearchService` async wiring(service를 async로 올려 planner 주입)이 다음 slice — 본 slice 범위 밖.
- 본 검증은 결함을 silently fix하지 않음(이슈 1·2를 owner에게 회신).

## Reproduction

```bash
# 1. suite green + 정밀 카운트
python3 -m py_compile services/application/app/context_search/planner.py \
  tests/test_context_search_planner.py scripts/phase4_context_search_planner_live_smoke.py
python3 -m unittest tests.test_context_search_planner              # 13개
python3 -m unittest discover tests                                  # Ran 452 OK skipped=44
python3 -m pytest -q                                                # 408 passed, 44 skipped
git diff --check

# 2. mutation testing — 긍정 방향(under-strict guard). 각각 re-fail해야 정상.
#    (cp 백업 → python 문자열 치환으로 guard 무력화 → unittest → cp 복원)
#    need-membership / tool-membership / repair-disabled / retry-cap-removed / template-missing-not-llm-error
#    상세 치환 스크립트는 본 검증 세션의 bash 기록에 있음.

# 3. mutation testing — 부정 방향(빈 셀 실증). 각각 13개 전부 OK이면 빈 셀.
#    step-keys-mismatch-accepted / non-string-query-accepted / empty-plan-id-accepted

# 4. live smoke (sandbox 밖, 승인된 네트워크에서만)
python3 scripts/phase4_context_search_planner_live_smoke.py \
  --llama-base-url http://192.168.1.29:9080 \
  --model google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0
```
