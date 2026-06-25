# 검증 기록 — AgentLoopRunner A2 (Tool Registry + Strict Arguments + Signature)

## Subject metadata

- 일자: 2026-06-25
- 요청자: 사용자("작업 AI가 작업한 분에 대해서 검증하고 의심해줄래? … AgentLoopRunner A2까지 진행")
- 검증자: 독립 검증 AI(Claude Code)
- 대상 slice/artifact: `services/application/app/agent_loop/registry.py` + `tests/test_agent_loop_registry.py`(A2 구현 sub-slice)
- canonical spec reference:
  - `docs/plans/flat-loop-gate.md` 상태 `Draft`(tool registry slice 2026-06-24 소유자 확정)
  - §Domain Tool Registry 계약(13–73): §등록 조건과 argument validation(19–37, 특히 validator 5단계 31–35), §v1 domain tool과 task profile(39–62), §tool registry boundary matrix(64–73)
  - §종료 decision literal: `blocked`(158–160), `invalid_tool_arguments`(166–168)
  - §boundary matrix(178–190)의 `blocked`/`invalid_tool_arguments`/`tool_error` should-NOT-fire 구분
  - `docs/plans/implementation-plan.md` §진행 중 Slice 4 A1/A2(131–140)
- source of the work being verified: working tree, uncommitted. `git status --porcelain`: `?? services/application/app/agent_loop/registry.py`, `?? tests/test_agent_loop_registry.py`, `M CHANGELOG.md/HANDOFF.md/docs/plans/implementation-plan.md`. HEAD `b5eb803`.
- 구현 환경: Python 3.12.3.

## Scope

A2는 handler 실행·retry·completion 합성이 아니라 **registry 구성·strict argument 검증·canonical signature 정규화**만 잠근다(구현 docstring 및 테스트 docstring 명시). 점검 표면:

1. spec contract — `flat-loop-gate.md` §Domain Tool Registry(등록 조건, validator 5단계, v1 tool 6종·task profile allowlist, context-only argument 금지, boundary matrix 6행 중 A2 범위 행)
2. 내부 일관성 — §33 validator 규칙 ↔ 구현 `_validate_value`/`_validate_arguments` ↔ decision 매핑
3. registration 조건 — schema-less·non-object root·unknown-field 허용 schema·context-only 필드 등록 거부
4. strict argument 검증 — parse-once, non-object root, unknown field, required 누락, type coercion, non-object JSON → `invalid_tool_arguments`
5. `blocked` vs `invalid_tool_arguments` 양방향 구분 경계
6. canonical signature 정규화(key sort·compact separator·value/type/tool 비접힘)
7. 테스트 코드 감사 — 18개 focused 회귀 각각을 contract clause로 역추적(boundary matrix lock list)
8. 비회귀 — focused 18개 + 전체 83개
9. 유사 패턴 sweep(독자 재수행)

## Methodology

1. **contract scope 먼저 구축**: `flat-loop-gate.md` 본문을 열기 전 A2를 govern하는 정확한 섹션(§등록조건 5단계, v1 tool/profile 표, boundary matrix 6행, blocked/invalid_tool_arguments literal)을 확정하고 그 안만 정독. 인접한 budget/completion/Gate 합성 섹션은 A2 범위 밖.
2. **boundary matrix 구축 후 코드 비교**: contract의 모든 should-fire/should-NOT-fire 분기와 literal(6 tool명, 3 allowlist, `blocked`/`invalid_tool_arguments`, context-only 5종)을 lock list로 추출한 뒤 구현·테스트에 대입.
3. **contract 자기 모순 점검**: §33이 "required, type, enum, bounds를 그대로 적용"이라 명시 → 구현이 enum/bounds를 다루는지 실증(ad-hoc 스크립트).
4. **테스트 코드를 감사 대상으로**: green bar와 별개로 각 테스트 assertion이 contract를 pin하는지, under-strict/over-strict 양방향 guard 존재 확인.
5. **작업자 주장을 믿지 않고 재도출**: 18/18·83/83·pattern sweep을 검증자가 직접 재실행.

정확한 명령은 Reproduction에 있다.

## Findings

### 1. Allowlist literal — v1 tool 6종 × task profile (빈 칸 없음, 정본과 일치)

`DOMAIN_TOOL_ALLOWLISTS`(registry.py:49–63)를 `flat-loop-gate.md` §v1 domain tool 표(43–50) 및 task profile 표(54–58)와 대치:

| profile | 계약 허용 tool | 구현 tuple | 일치 |
|---|---|---|---|
| `analysis_compare` | search_memory, load_memory, load_snapshot, compare_memory, validate_candidate | 동일 5종 | ✓ |
| `context_search` | search_memory, load_memory, validate_context | 동일 3종 | ✓ |
| `writing_generate` | 없음 | `()` | ✓ |

`DomainToolName` enum(registry.py:40–46) 6종이 계약 tool 표와 문자열 그대로 일치. `test_profile_allowlists_match_contract`(test:54)가 tuple을 exact match로 pin. ✓

### 2. Registration 조건 — schema-less / non-object / unknown-field 허용 / context-only (양방향)

`_validate_schema_contract`(registry.py:173–194)가 §29·§33을 등록 시점에 강제:

- schema 없음 → ToolBlocked(registry.py:174) ↔ §29 "입력 schema가 없거나". test:101 ✓
- root `type != object` → ToolBlocked(:176) ↔ §29 "root가 JSON object가 아니면". (직접 테스트는 없으나 동일 함수 분기)
- `additionalProperties is not False` → ToolBlocked(:181) ↔ §33 "unknown field는 additionalProperties: false로 거절". test:105 ✓
- properties 누락 / required 비sequence / required가 properties에 없는 이름 → ToolBlocked(:178–194)
- context-only 필드(`project_id`, `task_id`, `trace_id`, `deadline`, `deadline_ms`) → ToolBlocked(:184–187) ↔ §37 "project_id, task/trace identity, deadline은 모델 arguments가 아니다". test:109 ✓

`deadline_ms`는 계약에 문자 그대로 없으나 "deadline"의 변종으로 허용 범위를 넓히는 방향(더 엄격)이므로 안전. ✓

### 3. Strict argument 검증 — parse-once / non-object / unknown / required / coercion → invalid_tool_arguments (양방향)

`validate_call`(registry.py:148–170):

- raw args를 `json.loads` **정확히 한 번**(:161), 이후 검증·signature는 parsed dict 사용 ↔ §31 "정확히 한 번 parse".
- JSONDecodeError → InvalidToolArguments(":163, `{}`로 바꾸지 않음" ↔ §31·§168). test:143 ✓
- non-object root → InvalidToolArguments(:165) ↔ §32 "root object 검증". test:148 (`"[]"`) ✓
- unknown field → InvalidToolArguments(`_validate_arguments`:209–211) ↔ §33. test:152 ✓
- required 누락 → InvalidToolArguments(:205–207), 기본값 삽입 없음 ↔ §34. test:158 ✓
- type coercion(string→int 등) → InvalidToolArguments(`_validate_value`:218–246) ↔ §34 "string↔numbers, singleton↔array 변환 하지 않는다". test:162(`limit:"2"`) ✓

`integer`가 bool을 거부하고 float를 거부(:224), `number`가 bool을 거부(:227)하는 것도 JSON Schema 의미에 부합. ✓

### 4. `blocked` vs `invalid_tool_arguments` 양방향 구분 (핵심 경계)

- 미등록/타 profile tool 요청 → **ToolBlocked**(registry.py:150–158), decision=`BLOCKED` ↔ §60 + boundary matrix allowlist 행. test:168(`compare_memory` on context_search) ✓
- 등록 tool의 malformed args → **InvalidToolArguments**, decision=`INVALID_TOOL_ARGUMENTS` ↔ §35·§188. test:143 ✓

이 분기가 §188 "invalid_tool_arguments should-NOT-fire: 유효 args runtime 오류 아님(tool_error)" 및 §186 "blocked should-NOT-fire: tool runtime 오류 아님"과 정합. `validate_call`이 tool-name 해석·등록 확인을 **JSON parse보다 먼저** 수행(:150→:161)하므로, out-of-profile tool + malformed args 동시 발생 시 `blocked`가 우선. 계약이 우선순위를 명시하지 않으나 allowlist를 구조적 전제조건으로 보는 해석과 일치. ✓

### 5. Canonical signature 정규화 (양방향, non-over-collapse)

`_signature_for`(registry.py:249–251) = `f"{name}:{json.dumps(args, sort_keys=True, separators=(',',':'))}"`.

- key 순서 무관 동일 signature ↔ BudgetTracker repeated-call 정규화. test:185 (동일 sig + exact `'search_memory:{"limit":2,"query":"alpha"}'`) ✓
- 다른 value → distinct sig. test:197 ✓
- 다른 JSON type(문자열 `"1"` vs `"01"`) → distinct sig(숫자 정규화로 접히지 않음). test:206 ✓
- 다른 tool → distinct sig. test:211 ✓

`json.dumps(sort_keys=True)`는 중첩 dict key도 재귀 정렬하므로 canonical 형태 안정. ✓

### 6. 테스트 감사 — 18개 회귀 ↔ contract clause lock list (빈 칸 점검)

각 테스트를 boundary matrix cell에 역추적:

| Test | lock 하는 contract 분기 | 방향 |
|---|---|---|
| `test_profile_allowlists_match_contract` | 3 allowlist literal exact | literal pin |
| `test_writing_generate_accepts_no_tools` | writing_generate = tool 없음(§58) | should-NOT-fire |
| `test_missing_required_profile_tool_is_blocked_before_provider` | 필수 tool 누락 → blocked(§60) | should-fire |
| `test_tool_from_other_profile_is_not_registered` | 타 profile tool → blocked(boundary allowlist) | should-NOT-fire |
| `test_schema_less_tool_cannot_register` | schema 없음 등록 거부(§29) | should-fire |
| `test_schema_must_reject_unknown_fields` | additionalProperties:false 강제(§33) | should-fire |
| `test_model_cannot_own_project_or_trace_scope_fields` | context-only arg 등록 거부(§37) | should-NOT-fire |
| `test_valid_json_object_reaches_entry_with_parsed_arguments` | valid call 전달 + type 보존(coercion 아님) | should-fire(over-strict guard) |
| `test_invalid_json_is_invalid_tool_arguments_not_empty_object` | parse 실패 → `{}` 아닌 invalid_tool_arguments(§31·§168) | should-fire |
| `test_non_object_json_is_invalid` | non-object root → invalid_tool_arguments(§32) | should-NOT-fire |
| `test_unknown_field_is_rejected_without_repair` | unknown field → invalid_tool_arguments(§33·§245) | should-NOT-fire |
| `test_missing_required_field_is_rejected_without_default` | required 누락 + 기본값 삽입 금지(§34) | should-NOT-fire |
| `test_type_coercion_is_rejected` | coercion 금지(§34) | should-NOT-fire |
| `test_unregistered_or_out_of_profile_tool_is_blocked_not_invalid_args` | blocked vs invalid_tool_arguments 구분(§186·§188) | 양방향 핵심 |
| `test_same_tool_and_canonical_arguments_have_same_signature` | key 순서 무관 동일 sig | should-fire |
| `test_different_argument_value_keeps_distinct_signature` | 값 차이 보존 | over-strict guard |
| `test_different_json_type_keeps_distinct_signature` | 타입 차이 보존 | over-strict guard |
| `test_different_tool_keeps_distinct_signature` | tool 차이 보존 | over-strict guard |

A2 범위 내 6행 boundary matrix 중 allowlist·arguments·project-scope(등록 시점)·Writing 경계 행은 모두 테스트로 lock. runtime-fail(→tool_error)·Gate 합성 행은 handler/loop 합성이 A3에 있으므로 정당하게 범위 밖. ✓

### 7. 비회귀 및 pattern sweep (독자 재실행)

- `python3 -m unittest tests.test_agent_loop_registry -v` → **18/18 OK**(검증자 재실행, 0.003s)
- `python3 -m unittest discover -s tests` → **83/83 OK**(검증자 재실행, 0.133s)
- pattern sweep: `services/`·`packages/`에서 `additionalProperties`/`json.loads`/`ToolRegistry`/`invalid_tool_arguments` 검색 → registry.py 외 중복 구현 없음(`decision.py`의 literal 정의만). 작업자 sweep 주장과 일치. ✓

## Issues / Risks

### I1. [조건부 합격 조건] enum / bounds 검증 미구현 — §33과 직접 충돌, empty boundary cell

`flat-loop-gate.md` §33은 "schema의 **required, type, enum, bounds**를 그대로 적용하고 unknown field는 additionalProperties: false로 거절한다"라고 명시. 그러나 `_validate_value`(registry.py:218–246)는 `type`(string/integer/number/boolean/array/object)과 `required`, `additionalProperties`, array `items`만 다루며 **`enum`·`minimum`/`maximum`(bounds)을 전혀 검증하지 않는다.** 실증(ad-hoc, Reproduction 참조):

- `{"type":"string","enum":["alpha","beta"]}` schema에서 `query:"gamma"`(enum 밖) → **ACCEPTED**(열림)
- `{"type":"integer","minimum":1,"maximum":5}` schema에서 `limit:999`·`limit:0` → **둘 다 ACCEPTED**(열림)

관련 회귀 테스트 **없음**(enum/bounds의 should-fire·should-NOT-fire 둘 다 빈 칸).

- 작업자는 work_log(40–41)에서 의식적으로 "object/type/required/array 검증만 표준 json 기반 최소 구현으로 제공, broader JSON Schema keyword는 후속"이라 서술했으므로 **silent는 아님**.
- 그러나 **canonical contract(§33)은 이 예외를 부여하지 않는다.** §29 "구체 업무 필드는 Phase schema 확정 시 같은 계약으로 잠근다"는 *어떤 field*가 존재하는지에 대한 것이지 *어떤 검증 keyword*가 적용되는지에 대한 것이 아니며, §31–35는 "공통으로 강제한다"(보편)라고 명시. 결과적으로 현재 **contract와 구현이 모순**이며 어느 쪽도 reconcile 되지 않았다(work_log는 작업 서술일 뿐 계약 개정이 아님).
- 잠재 영향: 향후 v1 tool schema가 `enum`/`minimum`/`maximum`을 선언하면 validator가 이를 **조용히 무시** → "strict JSON argument validation"(plan §138·CHANGELOG) 주장이 거짓이 되는 unlocked boundary. 현재 v1 schema에 enum/bounds가 없어 **활성 결함은 아님**(latent).

→ 본 검증 방법론("empty cell은 blocking", "spec-explicit-but-code-deferred도 계약 갭")에 따라 이 slice가 완전히 닫히려면 둘 중 하나 필요:
  - (a) `flat-loop-gate.md` §33(및 plan §138)을 명시적으로 좁혀 v1/A2 validator 범위를 `{object, type, required, additionalProperties, array items}`로 고정하고 enum/bounds를 "해당 keyword를 사용하는 tool schema가 등록될 때까지 deferred"로 계약에 기록, 또는
  - (b) enum/bounds 검증을 구현하고 양방향 회귀 추가.

### I2. [비차단, latent] 중첩 object schema의 등록-검증 비대칭

`_validate_schema_contract`는 최상위 schema만 검사하므로, 중첩 object property가 strict하지 않은 경우(예: `{"type":"object","properties":{"filter":{"type":"object"}}}`) **등록은 통과**한다. 단 runtime `_validate_value`의 object 분기(:239–244)가 `additionalProperties is not False`를 검사해 해당 필드 호출 시 **fail-closed**(`"object schema must be strict"`). 실증 확인. 등록 시 재귀 검증이 없어 tool이 사실상 그 필드에 쓸 수 없는 latent 상태가 될 수 있으나, 보안 방향은 안전(fail-closed)이며 현재 v1 schema에 중첩 object가 없음. 비차단 권고: 등록 validator를 재귀화하거나 본 한계를 문서화.

### I3. [비차단, cosmetic] `_validate_arguments` 내 `assert`(registry.py:201, 203)

`assert isinstance(properties, Mapping)` / `assert isinstance(required, Sequence)`는 `python -O`에서 제거된다. 단 실제 강제는 `_validate_schema_contract`(등록 시, assert 아님)에서 이미 이뤄지므로 제거돼도 구멍이 생기지 않는다(중복 안전망). 비차단.

## Verdict

**합격(pass) — 조건부 합격에서 승격(2026-06-25, 사용자 결정 option (a)로 I1 조건 해소).**

초기 평가는 **조건부 합격**이었다. 적용 사유(load-bearing):
- A2 범위(allowlist 고정·registration 조건·strict argument 검증·blocked/invalid 구분·canonical signature)는 구현이 계약 literal 그대로 정확하고, 18개 focused 회귀가 boundary matrix의 in-scope cell을 양방향(should-fire + should-NOT-fire, under-strict + over-strict)으로 lock하며, 83/83 비회귀·pattern sweep도 독립 재현했다. 이 범위에서는 green bar ≠ verified 함정에 빠지지 않았다.
- **그러나** §33이 명시한 `enum`/`bounds` 검증이 구현에 없고(실증 I1), 이에 대한 회귀도 없어 **boundary matrix에 empty cell**이 존재했다. 본 검증 방법론은 empty cell을 "후속 보강"으로 환산하지 않으므로 조건부 합격이었다.

**조건 해소**: 사용자가 option (a)(계약 명시 좁힘)을 선택해, `flat-loop-gate.md` §33·`implementation-plan.md` §138·CHANGELOG A2 entry를 v1/A2 validator 범위 `{required, type, additionalProperties, array items}`로 명시 좁히고 `enum`/bounds를 "keyword 사용 tool 등록 시점까지 deferred"로 계약에 기록했다. 이로써 contract↔implementation 모순이 해소되고, empty cell은 명시적 deferral(첫 사용 tool 등록 시점에 검증+회귀 추가라는 triggered 조건)로 채워졌다. 따라서 **합격으로 승격**.

I2(중첩 object 등록-검증 비대칭, fail-closed)·I3(`assert` cosmetic)은 비차단 권고사항으로 남는다.

## Outstanding items

- **I1 해소(2026-06-25)**: 사용자 결정 option (a)로 enum/bounds를 계약 명시 좁힘(deferred until first-use) 처리. triggered 조건: enum/bounds를 선언하는 tool schema가 처음 등록되는 시점에 검증 + 양방향 회귀를 추가해야 한다. 그 전까지는 empty cell 아님(명시적 deferral).
- A2 코드는 전부 uncommitted(working tree). HEAD `b5eb803` 이후 commit 대기. 본 검증의 doc reconcile(`flat-loop-gate.md`·`implementation-plan.md`·`CHANGELOG.md`·`HANDOFF.md`·`work_log.md`)도 같이 미커밋.
- A3(completion 판정·retry·loop 합성·decision 매핑)과 실제 tool handler(Mongo/ES/Chroma)는 후속 sub-slice/Slice 1·3 이후로 그대로 남아 있음(HANDOFF:38과 일치).
- 본 검증 기록은 최초의 2026-06-25 A2 독립 검증(HANDOFF A2 행의 "독립 검증 기록은 아직 없음"을 대체).

## Post-verification follow-up

2026-06-25 사용자 요청으로 Codex가 비차단 I2/I3를 후속 보강했다. 이 섹션은 원 독립 검증의 판정을 덮어쓰지 않고, 검증 이후 working tree 변경을 추적한다.

- I2 보강: `_validate_schema_contract`를 재귀화해 중첩 object schema도 등록 시점에 `additionalProperties: false`, required/properties 일치, context-only field 금지를 검증한다.
- 추가 보강: A2 reconcile 후 validator 범위에 남아 있는 array `items`도 등록 시점에 필수화했다. `items` 없는 array schema는 `ToolBlocked`로 거부한다.
- I3 보강: `_validate_arguments`의 `assert` 의존을 명시 검사로 교체해 `python -O`에서도 schema guard 의도가 유지된다.
- 추가 회귀: `test_nested_object_schema_must_be_strict_at_registration`, `test_array_schema_requires_items_at_registration`.
- 재검증: `python3 -m unittest tests.test_agent_loop_registry -v` → 20/20 OK, `python3 -m unittest discover -s tests` → 85/85 OK.
- I1의 enum/bounds deferral은 유지되며, ad-hoc 확인에서 enum/bounds 밖 값은 계속 수용된다. 이는 갱신된 `flat-loop-gate.md` §33의 explicit deferral과 일치한다.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# 1. focused + 전체 회귀 재실행
python3 -m unittest tests.test_agent_loop_registry -v   # 최초 검증 18/18, follow-up 이후 20/20 기대
python3 -m unittest discover -s tests                   # 최초 검증 83/83, follow-up 이후 85/85 기대

# 2. pattern sweep(중복 구현 부재 확인)
grep -rn "additionalProperties\|json.loads\|ToolRegistry\|invalid_tool_arguments" \
  --include="*.py" services/ packages/ | grep -v "agent_loop/registry.py"

# 3. I1 enum/bounds 미강제 실증
python3 - <<'PY'
from services.application.app.agent_loop.registry import (
    ToolRegistry, ToolEntry, TaskProfile, DomainToolName)
sch = {"type":"object","properties":{
    "query":{"type":"string","enum":["alpha","beta"]},
    "limit":{"type":"integer","minimum":1,"maximum":5}},
    "required":["query"],"additionalProperties":False}
def mk(n,s): return ToolEntry(name=n,
    description_by_profile={TaskProfile.CONTEXT_SEARCH:"x"}, argument_schema=s)
reg = ToolRegistry(TaskProfile.CONTEXT_SEARCH, entries=[
    mk(DomainToolName.SEARCH_MEMORY, sch),
    mk(DomainToolName.LOAD_MEMORY, {"type":"object","properties":{"q":{"type":"string"}},"required":["q"],"additionalProperties":False}),
    mk(DomainToolName.VALIDATE_CONTEXT, {"type":"object","properties":{"q":{"type":"string"}},"required":["q"],"additionalProperties":False})])
for raw in ['{"query":"gamma"}', '{"query":"alpha","limit":999}', '{"query":"alpha","limit":0}']:
    try:
        print(raw, "-> ACCEPTED:", reg.validate_call("search_memory", raw).arguments)
    except Exception as e:
        print(raw, "-> rejected:", type(e).__name__)
PY
# 기대: 세 경우 모두 ACCEPTED(= enum/bounds 미강제). I1 참조.
```
