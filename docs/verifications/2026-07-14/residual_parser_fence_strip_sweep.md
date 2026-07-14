# 검증 기록 — 잔존 4개 strict JSON parser fence-strip 스윕 (SoT v1.6.86)

## Subject metadata

- **날짜**: 2026-07-14
- **요청자**: 오너 ("작업 AI가 작업한 부분 확인해서 검증하고 의심하고 또 의심해줄래" — Task 1 완료 독립 감사 요청)
- **검증자**: Claude (본 세션, glm-5.2)
- **대상 slice/artifact**: SoT v1.6.86 — gate(v1.6.83)·report(v1.6.85)가 남긴 추적 부채 4곳(`analysis/compare_judge.py::_json_object`·`analysis/extractor.py::_json_object`·`context_search/planner.py::_json_object`·`writing/retrieval.py::parse_writing_retrieval_plan`)에 공유 `writing/json_extract.py::strip_code_fence` 적용 + Phase 2A extraction 계약 clause 정정 + 회귀 +8.
- **정규 계약 참조**: `docs/system-contract-sot.md` v1.6.86 — Phase 2A extraction clause(`docs/system-contract-sot.md:403`), version log v1.6.86 항목(`docs/system-contract-sot.md:36`), D2=A 추출 프레이밍 근거(v1.6.83·v1.6.85 changelog 항목 + `docs/plans/05-writing-gate-live-diagnostics-decisions.md`, `docs/plans/05-writing-report-live-diagnostics-decisions.md`).
- **작업 소스**: working tree, uncommitted (commit `db04df6` 위). `git diff HEAD`로 검증.

## Scope

정규 계약 scope를 먼저 구축한 뒤 각 표면을 검증:

1. **계약 표면**: SoT Phase 2A extraction clause(`:403`)의 정정 정당성 + v1.6.86 changelog(`:36`) 기재 사실 정확성 + 정정 후 정본 계약의 자기충돌 여부.
2. **구현 코드**: 4개 parser의 `strip_code_fence` 적용 + `writing/json_extract.py` 본문/docstring + `retrieval.TEMPLATE` fence 금지 추가 + 순환 import 부재.
3. **회귀 테스트**: 4개 테스트 파일의 신규 +8(under/over-strict) + 기존 fence→repair 테스트 정정 — boundary matrix(should fire / should NOT fire)의 empty cell 검사 + mutation으로 under-strict guard 실증.
4. **public envelope/schema**: extraction이 구조 완화가 아님(strict 검증 무변) 확인.
5. **전체 스위트**: focused 4-file + full 1035/45/235 카운트 독립 재실행.
6. **live 관통(실 12B)**: 머신 상태 확인 후 compare_judge·planner live smoke를 Task 1 코드와 no-op mutation 두 상태로 실행 — 실모델 출력 parse 성공 + strip의 defensive/parity 성격 확인.

## Methodology

모든 명령은 working tree(uncommitted) 상태에서 실행. 작업 AI가 주장한 숫자를 신뢰하지 않고 1차 소스에서 재도출.

1. **코드/계약/테스트 diff**: `git diff HEAD -- <files>` 로 4 parser + json_extract + SoT + 4 test 파일의 변경을 직접 확인.
2. **`strip_code_fence` 본문 정독**: `services/application/app/writing/json_extract.py:22-38` — regex와 no-match 동작이 "extraction not relaxation"(whole-content fence만 strip, prose salvage 없음)인지 확인.
3. **focused 스위트**: `PYTHONPATH=. python3 -m pytest -q -p no:cacheprovider tests/test_analysis_compare_judge.py tests/test_analysis_extractor_schema.py tests/test_context_search_planner.py tests/test_writing_retrieval.py` → 60 passed / 39 subtests.
4. **mutation test(under-strict 실증)**: `json_extract.py:38` `return match.group(1).strip()` → `return content`(no-op)로 치환 후 동일 focused 스위트 실행 → under-strict guard가 bite하는지(=fix 제거 시 재실패) 관측 후 revert.
5. **전체 스위트**: `PYTHONPATH=. python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → 1035 passed / 45 skipped / 235 subtests.
6. **계약 자기충돌 sweep**: `grep -rnE 'markdown-fenced|fenced JSON|fence.*repair|fence.*실패|fenced.*valid'` 를 `docs/`·`plans/` 전역에 적용 — 정정 후 잔존 "fenced→repair" 언어의 위치(정본 vs 역사 기록) 분류.
7. **정적 검증**: `python3 -m py_compile`(5 파일), `git diff --check`, `docker compose config --quiet`, import 실행(`python3 -c`로 4 parser + json_extract 동시 import → 순환 import 부재 확인).
8. **boundary matrix 구축**: 정정된 clause(`:403`)의 각 분기를 테스트 함수에 매핑, empty cell 검사.
9. **머신 상태 직접 확인**(`docker ps` + `curl /health`): full-stack이 **실제로 기동 중**(application·mongo·gateway·worker·embedding·ES·chroma 전부 healthy, gateway `/health` ok, llama.cpp `192.168.1.22:9080` 도달 가능). smoke 스크립트의 "external TCP 불가" note는 stale.
10. **live smoke(working-tree 코드, 실 12B)**: smoke 스크립트는 deployed application(8000)을 치지 않고 working-tree adapter를 PYTHONPATH로 직접 instantiate → in-process gateway → 실 llama.cpp. 따라서 **rebuild 없이 Task 1 신규 코드로 live 관통 가능**. `scripts/phase2b3_compare_judge_live_smoke.py`·`scripts/phase4_context_search_planner_live_smoke.py`를 (a) Task 1 코드 (b) `json_extract.py` no-op mutation 두 상태로 각각 실행.

## Findings

### F1. 구현 코드 — 주장과 정확히 일치, 최소 변경

4 parser 모두 `json.loads(content)` → `json.loads(strip_code_fence(content))`로 동일 패턴 적용. 각 파일에 `from services.application.app.writing.json_extract import strip_code_fence` import 추가. `json_extract.py`는 본문 무변, docstring만 "gate·report가 쓰던 private helper" → "6개 parser 공유"로 갱신(`json_extract.py:10-14`).

- `services/application/app/analysis/compare_judge.py:203` — `payload = json.loads(strip_code_fence(content))` ✓
- `services/application/app/analysis/extractor.py:282` — 동일 ✓
- `services/application/app/context_search/planner.py:240` — 동일 ✓
- `services/application/app/writing/retrieval.py:213` — `root = json.loads(strip_code_fence(content))` ✓ + `retrieval.py:47` TEMPLATE에 "Do not wrap the JSON in markdown fences and do not add prose." 추가 ✓

`strip_code_fence`(`json_extract.py:27-38`)는 whole-content fence regex(`:22-24`)로 단일 fence만 매칭, no-match 시 원문 반환 — prose salvage / `{…}` regex 없음. **extraction이지 구조 완화가 아님**을 코드로 확인: fence 추출 후 동일 `_json_object`/schema 검증이 parsed dict에 그대로 적용됨.

### F2. 순환 import 부재 — 주장 확인

`json_extract.py`는 `re`와 `from __future__ import annotations`만 import(`json_extract.py:17,19`) → leaf 모듈. `python3 -c`로 4 parser + json_extract 동시 import 성공, 4 parser 모두 `strip_code_fence` 참조 확인. `analysis`/`context_search` → `writing.json_extract` 방향 import가 새로 생겼으나 역방향 의존이 없어 순환 불가. `py_compile` 5파일 OK, `git diff --check` OK, `docker compose config --quiet` OK.

### F3. 회귀 테스트 — 양방향 guard, mutation으로 under-strict 실증 (가장 중요)

신규 +8 메서드(under-strict + over-strict 각 2 × 4 parser), under-strict 4메서드의 tag 서브테스트 3개×4 = +12 subtest.

**Boundary matrix (정정된 clause `:403` 기준, empty cell 없음):**

| 계약 분기 | 유형 | lock 테스트 | 상태 |
|---|---|---|---|
| fenced valid → first-call 통과(compare) | should fire | `test_fenced_valid_output_is_extracted` + `test_markdown_fenced_valid_output_parses_without_repair` | mutation bite ✓ |
| fenced valid → first-call 통과(extractor) | should fire | `test_fenced_valid_extraction_is_extracted` | mutation bite ✓ |
| fenced valid → first-call 통과(planner) | should fire | `test_fenced_valid_plan_is_extracted` + `test_markdown_fenced_first_response_parses_without_repair` | mutation bite ✓ |
| fenced valid → first-call 통과(retrieval) | should fire | `test_fenced_valid_plan_is_extracted` | mutation bite ✓ |
| fenced schema/object-invalid → 여전히 reject(compare) | should NOT weaken | `test_fence_does_not_weaken_schema_check` | ✓ |
| fenced object-invalid → reject(extractor) | should NOT weaken | `test_fence_does_not_weaken_object_check` | ✓ (message-coupled, F6) |
| fenced object-invalid → reject(planner) | should NOT weaken | `test_fence_does_not_weaken_object_check` | ✓ |
| fenced schema-invalid → reject(retrieval) | should NOT weaken | `test_fence_does_not_weaken_schema_check` | ✓ |
| genuinely-malformed → repair 보존(extractor) | repair path 보존 | `test_versioned_prompt_adapter_repairs_invalid_provider_json_once` + `..._does_not_retry_more_than_once` | ✓ (genuinely-malformed JSON으로 교체, F4) |
| genuinely-invalid → repair(retrieval) | repair path | `test_planner_repairs_position_need_when_position_is_absent` | ✓ (기존, 무영향) |

**mutation test 결과(no-op strip, `json_extract.py:38` 치환)**: 15 failed / 57 passed. under-strict 전부 fail — compare/extractor/planner/retrieval의 `..._fenced_valid..._extracted` + 두 `_parses_without_repair`. 즉 fix 제거 시 버그 재현 → **under-strict guard가 진짜로 bite함**. over-strict 3종(compare/planner/retrieval, bare `assertRaises`)은 strip 유무 무관 reject → strip에 우연히 의존하지 않음. over-strict 1종(extractor)은 message-regex coupling으로 fail(F6). revert 후 `git diff`로 본문 복구·mutation comment 제거 확인.

### F4. repair-path intent 보존 — extractor 테스트 정정 정확

extractor의 두 repair 테스트는 옛 전제("fence = first-parse 실패")에 기반해 첫 response로 fenced-valid를 쓰고 있었다. fence 추출 도입 후엔 fenced-valid가 first-call 통과해 repair가 일어나지 않으므로, genuinely-malformed JSON으로 교체:

- `test_versioned_prompt_adapter_repairs_invalid_provider_json_once`(`tests/test_analysis_extractor_schema.py:~245`): 첫 content `'{"candidates": [ this is not valid json'`. assertion `len(provider.requests)==2` + repair message에 `"provider content must be JSON"`(`extractor.py:283`의 JSONDecodeError 메시지) 포함 → JSON-failure 경로 명시적 검증. 2nd response는 valid `_content([...])`. ✓ repair intent 보존.
- `test_versioned_prompt_adapter_does_not_retry_more_than_once`(`:~470`): 첫 content fenced `{"candidates":[]}`(이제 유효 empty extraction이 됨) → `"{not valid json"`. 2nd `"still not json"`. `len(provider.requests)==2` + `AnalysisExtractionError`. cap-at-once intent 보존. ✓

compare/planner의 fence→repair 테스트는 `_parses_without_repair`로 rename + assertion을 `len==1`(repair 없음)로 정정. retrieval은 fence→repair 테스트가 애초에 없어 무수정(기존 repair 테스트는 genuine-invalid 기반, 무영향).

### F5. 카운트 — 독립 재실행으로 주장 확인

- focused 4-file: **60 passed / 39 subtests** (주장 일치).
- full(`--ignore=tests/test_memory_mongo.py`): **1035 passed / 45 skipped / 235 subtests**, exit 0 (주장 일치). v1.6.85 baseline 1027/45/223 대비 +8 test / +12 subtest = 신규 fence 회귀 8메서드 + under-strict 4메서드×3 tag. 정합.

### F6. 계약 clause 정정 정당성 — 가장 의심 지점, 인가 체인으로 정당함

**의심**: 작업 AI가 SoT 정본 계약 텍스트(Phase 2A extraction clause)를 직접 수정. CLAUDE.md "Never silently pick a side" 위반 가능.

**조사**: 정정 전 clause는 "첫 content가 malformed JSON, **markdown-fenced JSON**, 또는 schema mismatch로 실패하면 repair" 였고, 이를 "fenced 유효 JSON은 first call 통과, malformed/schema mismatch만 repair"로 고침. 인가 체인:

1. **D2=A 추출 프레이밍(오너 결정, 기록됨)**: SoT v1.6.83 changelog가 오너 결정 D2=A (a)+(c) + 프레이밍 "fence 래핑은 정상 출력 포맷 변형, parser가 JSON 추출 — 버그가 아니라 추출 과정, strict schema/enum 검증은 parsed dict에 동일 적용(완화 아님)"을 확정. v1.6.85가 동일 프레이밍을 report에 적용. `docs/plans/05-writing-gate-live-diagnostics-decisions.md:123`가 (a)+(c)를 권장했고 오너가 채택.
2. **추적 부채 명시 스코프**: v1.6.83 changelog가 "동일 root-cause가 report·compare_judge·extractor·planner·retrieval에도 있으나 repair로 완충돼 Gate만 수정, 나머지 tracked debt"로 기록. v1.6.85가 "잔존 4: compare/extractor/planner/retrieval"로 잔존 명시. HANDOFF Next Tasks #1 = "잔존 tracked debt parser fence 추출 적용".
3. **오너의 Task 1 승인**: 오너가 Task 1(스윕)을 지시 → 위 프레이밍을 4 parser에 적용 승인.

**결론**: clause 정정은 silent pick이 아님. (a) D2=A가 fence=추출(실패 아님) 정책을 이미 확정했고, (b) 오너가 4 parser 스윕을 승인했으므로, (c) Phase 2A clause(분석 extractor의 **이전 동작** 기술)는 동작 변경에 따라 불가피하게 갱신돼야 함 — 그대로 두면 code↔contract 자기모순 발생. clause가 기술하던 "strict 실패→repair" 메커니즘 자체는 보존되고 "strict 실패"의 정의만 좁아짐(fenced-valid 제외). 정정은 다른 모든 조건(malformed/schema mismatch/source_ref mismatch/repair 1회/truncation 미보정/post-repair source_invalid)을 축실하게 보존(`:403` 비교). v1.6.86 changelog(`:36`)에 정정 사실·이유가 명시돼 있어 정본 자체에서 감사 가능(silent 아님).

**단, 이 slice가 SoT 정본 텍스트를 수정한 유일한 지점임** — 오너는 v1.6.86 changelog(`:36`)와 clause(`:403`)를 읽고 D2=A 프레이밍의 Phase 2A(분석 파이프라인) 확장에 동의하는지 1회 확인 권장. 인가 체인은 건전하나, 정본 수정이므로 가시적 확인이 적절함.

### F7. 정본 계약 자기충돌 — blocking 모순 없음

정정 후 `docs/`·`plans/`에서 잔존 "fenced→repair" 언어 위치 분류:

- **정본 live 계약**: clause `:403`(정정됨, fenced→추출) + 최신 changelog v1.6.86(fenced→추출). 자기일관적. ✓
- **역사 기록(수정 불필요, 허용됨)**: SoT v1.6.43 changelog("malformed/fenced/out-of-set이면 1회 repair", compare_judge 과거 동작); `plans/02-analysis-provider-wiring-decisions.md:122`(관찰+"strict 실패 시 repair" 메커니즘 — 메커니즘은 보존); `plans/04-agentic-search-kickoff-decisions.md:204`(rename된 테스트명 참조); 구 검증기록 `docs/verifications/2026-07-04/context_search_slice_4_2.md:80`, `docs/verifications/2026-07-06/phase_2b_3_2_compare_judge.md:60`(과거 slice 상태 기록).

SoT가 plans/검증기록보다 상위(정본 우선순위, SoT 목적문 "흩어진 계획 문서의 확정된 계약을 한 곳에서 추적"). 역사 기록의 과거 동작 기술은 불변 기록이므로 blocking 모순 아님. 정정된 clause가 "fenced→fail"을 명시 제거했으므로 정본 내 모순 없음.

### F8. SoT changelog 기재 사실 — fence 금지 문구 주장 확인

v1.6.86 changelog(`:36`)가 "retrieval.TEMPLATE에 fence 금지 추가(나머지 3개는 이미 존재)" 주장. grep으로 확인: compare_judge(`:48` TEMPLATE + `:219` repair prompt), extractor(`:198` repair prompt), planner(`:49` TEMPLATE + `:262` repair prompt) 모두 "Do not wrap the JSON in markdown fences" 보유. 주장 정확. ✓

### F9. public envelope/schema — 무변 확인

모든 parser가 fence 추출 후 동일 strict 검증을 parsed dict에 적용(`compare_judge.py:204` Mapping check, `extractor.py:283` Mapping check, `planner.py` object check, `retrieval.py` enum/schema check). over-strict 테스트 4종이 fenced-invalid reject로 검증. public literal·schema·서비스 경계 무변 — D2=A "완화 아님" 프레이밍 준수. ✓

### F10. live 관통(실 12B) — Task 1 코드로 실모델 출력 parse 성공, 단 strip은 defensive/parity

머신 상태 확인 결과 full-stack이 기동 중이어서(Task 1 신규 코드로) live smoke를 rebuild 없이 실행. 두 parser(compare_judge·planner — live smoke 스크립트가 있는 2종)를 (a) Task 1 코드 (b) `strip_code_fence` no-op mutation 두 상태로 각각 실 12B(`gemma-4-12B-it-qat-q4_0-gguf:Q4_0`)로 관통:

| parser | Task 1 코드(real strip) | no-op strip mutation |
|---|---|---|
| compare_judge (`phase2b3_compare_judge_live_smoke.py`) | 4쌍 전부 `succeeded` (action+rationale) | 4쌍 전부 **`succeeded`** |
| planner (`phase4_context_search_planner_live_smoke.py`) | `succeeded` (유효 2-step plan) | **`succeeded`** (유효 2-step plan) |

**해석**: no-op strip(추출 무효)에서도 두 parser 모두 최종 `succeeded` → **이 live 호출들에서 strip은 성공 여부를 바꾸지 않았다**. 실 12B가 first call에서 raw JSON을 반환했거나(가능성 높음 — 두 parser prompt에 이미 fence 금지 문구 `compare_judge.py:48`·`planner.py:49`가 있어 모델이 compliance), 최소한 first·repair 어느 한쪽에서 parse-가능한 JSON이 나와 repair가 살렸다. 어느 쪽이든 **strip이 live 결과를 바꾸지 않았다**는 게 핵심이다. (주: smoke가 raw content·request 수를 노출하지 않아 "first raw" vs "fenced-first→raw-repair"를 완전히 구분할 수는 없으나, 4쌍 전부 + planner까지 no-op에서 일관 `succeeded`라면 first-call raw JSON이 지배적이다.) 따라서 **이 4 parser에 대한 strip은 live-remedial(실제 502를 고치는)이 아니라 defensive/parity** — gate/report(모델이 실제로 fence를 뱉어 502의 root cause였고 strip이 502→성공으로 바꿔 remedial)와 대조적.

**의의**: (1) Task 1 코드가 실 12B 출력을 정상 parse함을 live로 확인(안전성). (2) 다만 작업 AI의 v1.6.86 SoT 프레이밍 "fence-wrapped 유효 출력이 first·repair 양쪽에서 반복되면 동일 502/invalid가 가능했던 잔여 위험을 제거"는 이 4 parser에 대해선 **이론적/예방적 위험 제거**로 이해해야 함(현재 모델이 fence를 안 뱉으므로 실현된 502가 아니었음). strip은 여전히 정확하고 gate/report와의 parity + 이론적 이중-fence-502 제거라는 가치가 있으나, "gate/report처럼 live 502를 고쳤다"는 오독은 금물. extractor·retrieval은 전용 live smoke 스크립트가 없어 관통 미실행(동일 strip·동일 모델이므로 유추 가능하나 직접 관찰은 아님).

## Issues / Risks

### Blocking (계약 의무)

**없음.** 정정된 clause의 모든 "should fire / should NOT fire" 분기가 named 테스트에 매핑되고, under-strict는 mutation으로 bite 실증, over-strict 4종 존재, repair path 보존, boundary matrix에 empty cell 없음. 정본 계약 자기모순 없음.

### Hardening recommendations (non-blocking, 현 spec 초과)

1. **extractor over-strict 테스트의 message-regex coupling** (`tests/test_analysis_extractor_schema.py:627` `test_fence_does_not_weaken_object_check`): `assertRaisesRegex(AnalysisExtractionError, "must be a JSON object")`로 메시지까지 pin. mutation(no-op strip)에서 fence 미벗김으로 `[]`가 JSONDecodeError → 메시지 `"provider content must be JSON"`가 돼 regex 불일치 fail. 다른 3 parser의 bare `assertRaises` 패턴과 불일치. 실제 strip 상태에선 정확히 동작(의도한 over-strict 방향 = object-check 완화 검출을 정상 수행)하므로 결함 아님. 일관성을 위해 bare `assertRaises(AnalysisExtractionError)`로 통일하거나, 정밀도를 위해 regex 유지 — 둘 다 합리적.
2. **HANDOFF "3개" 미소계수**: `HANDOFF.md` v1.6.86 Verification 항목이 "compare/extractor/planner의 기존 fence→repair 테스트 **3개** 정정"이라 했으나, 실제 정정/이름변경된 테스트는 4개(compare 1 + extractor 2 + planner 1). 표면 동작·테스트 자체는 정확하나 문서 카운트만 미세 부족.
3. **역사 문서의 rename 테스트명 잔재**: `test_markdown_fenced_first_response_repairs_once`→`..._parses_without_repair`(planner), `test_markdown_fenced_output_repairs_once`→`..._parses_without_repair`(compare) rename이 `plans/04:204`·`docs/verifications/2026-07-04/context_search_slice_4_2.md:80`·`docs/verifications/2026-07-06/phase_2b_3_2_compare_judge.md:60`에 stale 참조로 남음. 정본 우선순위 모델에서 허용되나, 향후 독자 혼동 가능. 선택적 정정.

## Verdict

**합격 (PASS).**

이유(하중 지점):
- 코드는 주장과 정확히 일치하는 최소 변경이며, `strip_code_fence`는 extraction(parser 정규화)이지 구조 완화가 아님(F1, F9).
- 회귀 +8의 under-strict guard를 **mutation test로 bite 실증**(fix 제거 시 15 fail 재현) — 단순 green bar가 아닌 실질 보증(F3).
- boundary matrix에 empty cell 없음; over-strict 4종 존재; repair-path intent 정확 보존(F3, F4).
- full 1035/45/235 · focused 60/39을 독립 재실행으로 확인(F5).
- **live 관통(실 12B)**: Task 1 코드로 compare_judge·planner 실모델 출력 parse 성공(F10). 단, live mutation으로 이 4 parser에 대해 strip이 defensive/parity(모델이 prompt fence 금지에 compliance해 raw JSON 반환)임을 확인 — 코드 정확성·안전성은 확보됐고, gate/report와의 parity + 이론적 위험 제거 가치는 유지.
- 정본 계약 clause 정정은 D2=A 프레이밍(기록된 오너 결정) + 오너 승인 스윕의 불가피한 귀결이며, 다른 조건을 축실하게 보존하고 changelog에 가시화 — silent pick 아님(F6). 정본 자기모순 없음(F7).
- 순환 import·py_compile·compose config·diff --check 전부 OK(F2).

조건부 합격이 아닌 이유: blocking 계약 의무 위반이나 empty boundary cell이 없음. 단, F6에서 명시한 대로 clause 정정이 **SoT 정본 텍스트를 수정한 유일한 지점**이므로 오너의 1회 가시적 확인을 권장(인가 체인은 건전).

## Outstanding items

- **미커밋**: Task 1 변경 전부 working tree(uncommitted, `db04df6` 위). 발행(publish/commit)은 오너 승인 대기.
- **live 관통은 compare_judge·planner 2종만**: 전용 live smoke 스크립트가 있는 2종은 실 12B로 관통 완료(F10, 둘 다 raw JSON → strip defensive). extractor·retrieval은 전용 live smoke 스크립트 부재로 관통 미실행(동일 `strip_code_fence`·동일 모델이라 유추 가능하나 직접 관찰은 아님).
- **F6 오너 확인**: D2=A 추출 프레이밍의 Phase 2A(분석 파이프라인) 확정 적용에 오너가 동의하는지 v1.6.86 changelog/clause 1회 확인.

## Reproduction

```bash
# 1. 코드/계약/테스트 diff (1차 소스)
git diff HEAD -- services/application/app/analysis/compare_judge.py \
  services/application/app/analysis/extractor.py \
  services/application/app/context_search/planner.py \
  services/application/app/writing/retrieval.py \
  services/application/app/writing/json_extract.py \
  docs/system-contract-sot.md tests/

# 2. strip_code_fence 본문 (extraction not relaxation)
sed -n '20,38p' services/application/app/writing/json_extract.py

# 3. focused 4-parser 스위트
PYTHONPATH=. python3 -m pytest -q -p no:cacheprovider \
  tests/test_analysis_compare_judge.py tests/test_analysis_extractor_schema.py \
  tests/test_context_search_planner.py tests/test_writing_retrieval.py
# 기대: 60 passed, 39 subtests passed

# 4. mutation test (under-strict bite 실증)
# json_extract.py:38 을 `return content` 로 임시 치환 후:
PYTHONPATH=. python3 -m pytest -p no:cacheprovider \
  tests/test_analysis_compare_judge.py tests/test_analysis_extractor_schema.py \
  tests/test_context_search_planner.py tests/test_writing_retrieval.py
# 기대: 15 failed (under-strict 전부 bite). 확인 후 반드시 revert.

# 5. 전체 스위트 (카운트 독립 재현)
PYTHONPATH=. python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider
# 기대: 1035 passed, 45 skipped, 235 subtests passed

# 6. 정적 검증
python3 -m py_compile services/application/app/analysis/compare_judge.py \
  services/application/app/analysis/extractor.py \
  services/application/app/context_search/planner.py \
  services/application/app/writing/retrieval.py \
  services/application/app/writing/json_extract.py
git diff --check
docker compose config --quiet
PYTHONPATH=. python3 -c "import services.application.app.writing.json_extract, services.application.app.analysis.compare_judge, services.application.app.analysis.extractor, services.application.app.context_search.planner, services.application.app.writing.retrieval"

# 7. 계약 자기충돌 sweep (정정 후 잔존 fenced→repair 언어 위치)
grep -rnE 'markdown-fenced|fenced JSON|fence.*repair|fence.*실패' docs/ plans/

# 8. live 관통 (머신 상태 확인 → 실 12B, working-tree 코드, rebuild 불필요)
docker ps --format '{{.Names}}\t{{.Status}}'   # full-stack 기동 확인
curl -sS --max-time 4 http://192.168.1.22:9080/health   # llama.cpp 도달 확인
# (a) Task 1 코드 — 둘 다 succeeded
PYTHONPATH=. LLAMA_BASE_URL=http://192.168.1.22:9080 \
  LLAMA_DEFAULT_MODEL=google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0 \
  python3 scripts/phase2b3_compare_judge_live_smoke.py
PYTHONPATH=. LLAMA_BASE_URL=http://192.168.1.22:9080 \
  LLAMA_DEFAULT_MODEL=google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0 \
  python3 scripts/phase4_context_search_planner_live_smoke.py
# (b) live mutation — json_extract.py:38 을 `return content`로 치환 후 위 두 스크립트 재실행
#     → 둘 다 여전히 succeeded (모델이 raw JSON 반환 = strip defensive/parity). 확인 후 반드시 revert.
```
