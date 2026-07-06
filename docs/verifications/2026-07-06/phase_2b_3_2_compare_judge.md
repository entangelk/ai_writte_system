# Verification — Phase 2B.3.2 real Gateway terminal-JSON CompareJudge adapter

## Subject metadata

- 날짜: 2026-07-06
- 요청자: 오너 (“다음 작업 검증해줘. 깃 커밋까지 했고 diff로 확인하면 더 좋을꺼같아. … Phase 2B.3.2 — 실제 Gateway 터미널-JSON CompareJudge adapter … 이부분 진행했어”)
- 검증자: Claude Code (독립 감사, diff 기반 교차 검증)
- 대상 slice/artifact: Phase 2B.3.2 — 2B.3의 `CompareJudge` seam을 실 Gateway adapter로 충전(SoT v1.6.43). commit `aa8d3e9`(branch `phase2b-slice-2b-2-prior-memory-context`).
  - 신규: `services/application/app/analysis/compare_judge.py`(258줄), `scripts/phase2b3_compare_judge_live_smoke.py`(163줄), `tests/test_analysis_compare_judge.py`(177줄).
  - 수정: `main.py`(+30, env wiring), `tests/test_analysis_compare_api.py`(+67, env factory 2), `docs/system-contract-sot.md`, `HANDOFF.md`, work_log.
- 보조 검증(직전 2B.3 검증 후속 `51e9770`): G1/G2/G3 회수 및 검증 기록 커밋 반영 여부.
- canonical spec reference:
  - `docs/plans/02b-3-analysis-compare-action-decisions.md` D1=A(터미널 JSON 1-turn)·D3=A(하이브리드, judge 라벨) — 2B.3.2는 이 결정의 실 adapter 실현(별도 브리프 없이 4.1→4.2 리듬의 동일패턴 증분)
  - `docs/system-contract-sot.md` v1.6.43 changelog + v1.6.42(2B.3 seam 정의)
  - `services/application/app/context_search/planner.py`(4.2 `TerminalJsonSearchPlanner` — 패턴 원천)
  - `services/application/app/analysis/compare.py`(2B.3 `CompareJudge` Protocol, `JUDGE_ACTIONS`, `InvalidJudgeResult`)
  - `services/application/app/analysis/prompt_templates.py`(versioned prompt 저장소)
- 검증 대상 work source: commit `aa8d3e9`(HEAD). 후속 `51e9770`도 회수 확인.

## Scope

1. **Pattern fidelity**: `compare_judge.py`가 4.2 `TerminalJsonSearchPlanner`와 동일 구조(async provider, versioned prompt, strict parse, 1 repair, 동일 에러 매핑 패턴)인지 diff/grep으로 교차.
2. **Literal/contract**: `analysis_compare_v1`/task_type, matched-pair 4종만·`create` 거부, strict `{action,rationale}`, InvalidJudgeResult 매핑.
3. **env wiring**: `_default_compare_service`의 `LLM_GATEWAY_BASE_URL` 분기·`ANALYSIS_COMPARE_MAX_TOKENS=512`·template seeding.
4. **Regression tests**: `test_analysis_compare_judge.py` 11 + env factory 2 — parse/repair/create-거부 양방향.
5. **Full suite**: 541 passed/45 skipped 독립 재계산.
6. **2B.3 후속 회수**: `51e9770`가 직전 검증 G1/G2/G3 + 검증 기록을 정확히 반영했는지.

## Methodology

```bash
# (1) 패턴 원천(4.2 planner) 구조
grep -n "class TerminalJsonSearchPlanner\|async def\|get_template\|repair\|ContextSearchFailed\|seed_template" services/application/app/context_search/planner.py
# (2) 신규 adapter 전량
cat services/application/app/analysis/compare_judge.py
# (3) env wiring diff
git show aa8d3e9 -- services/application/app/main.py
# (4) 테스트 감사 + env factory + G1/G2 후속 diff
cat tests/test_analysis_compare_judge.py
git show aa8d3e9 -- tests/test_analysis_compare_api.py
git show 51e9770 -- tests/test_analysis_compare.py tests/test_analysis_compare_api.py
# (5) 독립 재실행
python3 -m pytest -q tests/test_analysis_compare_judge.py tests/test_analysis_compare.py tests/test_analysis_compare_api.py tests/test_memory_scope.py
python3 -m pytest -q --ignore=tests/test_memory_mongo.py
git diff --check
# (6) live smoke 구조(sandbox-external, 미실행)
sed -n '1,30p' scripts/phase2b3_compare_judge_live_smoke.py
```

## Boundary matrix (lock list → 코드 → 테스트)

| # | 계약 branch | 코드(file:line) | 회귀 테스트 | under-strict | over-strict |
|---|---|---|---|---|---|
| L1 | `TerminalJsonCompareJudge`가 `CompareJudge.judge`(async) 구현 | `compare_judge.py:73,91` | env factory 테스트가 compare_job 관통 | ✓ | — |
| L2 | versioned prompt `analysis_compare_v1` / task_type `analysis_compare` | `compare_judge.py:39-40` | `test_prompt_payload_carries…`(task_type/version 전달) | ✓ | — |
| L3 | prompt는 matched-pair 4종만, **“Never return create”** | `compare_judge.py:41-56` | `test_prompt_payload…no_create_action`(allowed_actions에 create 없음, sorted 4종) | ✓ | ✓ |
| L4 | Gateway 1-turn `provider.generate` | `compare_judge.py:111` | `test_valid_output_parses`(requests==1) | ✓ | — |
| L5 | strict parse `{action,rationale}` exact | `compare_judge.py:175-181` | `test_extra_field_rejected` + `test_empty_rationale_rejected` | ✓ | ✓(exact schema) |
| L6 | `create`/unknown action → parse 거부 → repair | `compare_judge.py:184-197` | `test_unknown_action_repairs_then_succeeds` + `test_create_is_never_a_valid_judge_output` | ✓ | ✓ |
| L7 | 1회 repair(markdown fence / bad shape / non-json) | `compare_judge.py:114-127` | `test_markdown_fenced_output_repairs_once` + `test_bad_shape_repairs_then_fails` + `test_non_json_repairs_then_fails` | ✓ | ✓(repair 후 성공/실패 양쪽) |
| L8 | 2회째 무효 → `InvalidJudgeResult`(→502) | `compare_judge.py:124-127` | `test_create_is_never…` + `test_bad_shape…` + `test_non_json…` (전부 InvalidJudgeResult) | ✓ | — |
| L9 | 누락 template → provider 호출 없이 `InvalidJudgeResult` | `compare_judge.py:99-102` | `test_missing_template_is_invalid_judge_result_without_provider_call`(requests==0) | ✓ | ✓(provider 미호출 명시) |
| L10 | matched-pair 4종 전부 파스 | `compare_judge.py:184-197` | `test_every_matched_pair_action_parses`(subTest 4종) | ✓ | ✓(모든 유효 action) |
| L11 | env `LLM_GATEWAY_BASE_URL` 있으면 실 judge wiring | `main.py _default_compare_service` | `test_env_configured_default_factory_wires_real_judge`(monkeypatch provider → UPDATE 라벨) | ✓ | — |
| L12 | env 없으면 judge=None(매칭 503) | `main.py` + `compare.py:144` | `test_default_factory_without_env_has_no_judge`(`_judge is None`) | ✓ | ✓ |
| L13 | `ANALYSIS_COMPARE_MAX_TOKENS` 기본 512 | `main.py`(`int(os.environ.get("ANALYSIS_COMPARE_MAX_TOKENS","512"))`) + `compare_judge.py:82` | 코드 검증 | ✓ | — |
| L14 | template seeding(`prompt_templates` 재사용) | `main.py seed_analysis_compare_template` + `compare_judge.py:63-70` | env factory 테스트가 seed 경로 관통 | ✓ | — |
| L15 | service `JUDGE_ACTIONS` 2차 방어(fake seam) 유지 | `compare.py:152-156` | 2B.3 `test_judge_returning_create_is_rejected`(service) + G2 `…maps_to_502`(HTTP) | ✓ | ✓ |

## Findings

### 1. 4.2 planner 패턴 정합 (양호)

`TerminalJsonCompareJudge`는 `TerminalJsonSearchPlanner`(`planner.py:77,95`)와 동일 골격: async provider, `get_template`(→`PromptTemplateError` 매핑), 1-turn `generate`, strict parse, `_repair_request` 1회, 2회째 무효→에러. 차이는 에러 타입 뿐 — planner는 `ContextSearchFailed(llm_error)`, judge는 `InvalidJudgeResult`(→502). 이는 compare 계약(D3=A “judge-create 거절”, D7 “InvalidJudgeResult 502”)에 정확히 대응. `seed_analysis_compare_template`은 4.2 `seed_context_search_plan_template`과 동일하게 기존 `prompt_templates` 저장소 재사용(D5/4.2 선례 정합). **“2A extraction / 4.2 planner와 동일 패턴”** 주장 참.

### 2. Literal/contract 정합 (양호)

- `ANALYSIS_COMPARE_TASK_TYPE="analysis_compare"`, `ANALYSIS_COMPARE_PROMPT_VERSION="analysis_compare_v1"`(changelog와 byte 정합).
- template이 4종(update/add_evidence/no_change/conflict)만 제시 + “Never return 'create' — the subject already exists”(line 55). 허용 집합 = `JUDGE_ACTIONS`와 일치.
- `parse_judge_result`: `set(root.keys()) != {"action","rationale"}` exact(`compare_judge.py:177`), `_action`이 `create`/비-JUDGE_ACTIONS를 `CompareJudgeParseError`로(line 191-196), `_string`이 빈 rationale 거부. strict parse 계약 정확.
- `_repair_request`가 parser_error/invalid_output/original payload를 담아 1회 재생성 → 2회째 `CompareJudgeParseError` 시 `InvalidJudgeResult`. 1-turn + 1 repair 계약 정합.

### 3. env wiring 정합 (양호)

`_default_compare_service(memory)`(`main.py` diff): `LLM_GATEWAY_BASE_URL` 부재 → `AnalysisCompareService(memory_service=memory)`(judge=None, 매칭 503 유지); 존재 → `seed_analysis_compare_template` → `GatewayGenerateProvider(timeout/trust_env)` → `TerminalJsonCompareJudge(model, max_tokens=ANALYSIS_COMPARE_MAX_TOKENS 기본 512)`. `create_app`이 `compare_service or _default_compare_service(memory)`(종전 하드코드드 `AnalysisCompareService(memory)`에서 교체). env 게이팅은 analysis runner / context search planner와 동일 패턴.

### 4. 테스트 감사 — 양방향 guard (양호)

`test_analysis_compare_judge.py` 11개가 adapter 계약을 탄탄히 잠근다:
- **L10 over-strict(모범)**: `test_every_matched_pair_action_parses`가 4종을 subTest로 전부 파스 → 어느 유효 action이든 수용.
- **L6 under-strict**: `test_create_is_never_a_valid_judge_output`가 create→repair→create→InvalidJudgeResult, requests==2로 “create는 judge 출력이 될 수 없다”를 양방향(거부 + repair 소진)으로 lock.
- **L7 repair 경험 전 커버**: markdown fence / unknown action(“merge”) / bad shape(missing rationale) / non-json 각각에 대해 repair-then-succeed/fail.
- **L9**: 누락 template이 provider 호출 없이 InvalidJudgeResult(requests==0 명시) — 잘못된 배포에서 LLM 비용 안 나가는 경계.
- **L3**: payload의 `allowed_actions`에 create 없음 + sorted 4종 일치.
- env factory 2: monkeypatch(`main_module.GatewayGenerateProvider`/`os.environ`, try/finally 복원 포함)로 env 있을 때 실 judge wiring→UPDATE 라벨, 없을 때 `_judge is None`. 위생적.

### 5. 2B.3 후속(51e9770) 회수 — G1/G2/G3 전부 (양호, 모범)

직전 검증(`phase_2b_3_compare_action.md`)의 non-blocking 3종이 코드로 정확히 회수됐다:
- **G1**: `test_character_with_different_identity_is_create` — prior "Bob" vs current "Ariel" → CREATE, `judge.calls==0`(scope 음 방향 lock).
- **G2**: `test_judge_returning_create_maps_to_502` — FakeJudge(CREATE) on matched pair → 502(HTTP 매핑 lock).
- **G3**: 브리프 D5 요약표 정정(candidate “저장” → 즉석 산출; 상세 결정·코드와 일치).
- 검증 기록 자신이 `51e9770`에 커밋됨(`git show --stat` 191줄 확인).
- v1.6.42 changelog도 “회귀 21개 … service+HTTP 502·다른 identity→create 양방향 / 528 passed”로 갱신.

### 6. Full suite 독립 재실행 — 수치 재계산 (양호)

- 2B.3 계열: `pytest tests/test_analysis_compare_judge.py tests/test_analysis_compare.py tests/test_analysis_compare_api.py tests/test_memory_scope.py` → **34 passed, 4 subtests**.
- 전체: `pytest -q --ignore=tests/test_memory_mongo.py` → **541 passed, 45 skipped**. 산술 정합: 526(2B.3) + 2(51e9770 G1/G2) = 528 → +13(aa8d3e9: judge 11 + env factory 2) = 541.
- `git diff --check` clean.

## Issues / Risks

> 본 slice는 non-blocking 관찰 1건(judgment-quality empirical 검증 연기)이 유일하고, 그것도 changelog/commit에 투명 명시된 scope 결정이다. adapter 계약 자체는 완전.

### J1. [NON-BLOCKING — scope 결정, 투명 명시] 실 LLM judgment 경계(update↔add_evidence↔no_change↔conflict)가 fixture/live로 아직 empirical 검증 안 됨

adapter의 parse/repair/create-거부/InvalidJudgeResult 계약은 fixture로 완전 잠겼다(L1~L15). 그러나 **실 12B LLM이 주어진 (candidate, memory) pair에 대해 어느 action을 내는가(judgment quality)** 는 아직 fixture/live smoke로 검증되지 않았다. changelog가 이를 명시적으로 scope-out: “판정 경계는 프롬프트 action 정의로 안내하고 **fixture는 adapter parse/repair를 잠근다**”. 즉 이 slice의 계약은 “adapter가 올바르게 parse/repair/거부한다”까지이고, “LLM이 의미적으로 올바른 라벨을 낸다”는 live smoke + judgment fixture의 영역이다. commit message도 “Judgment-boundary fixtures and the live smoke run (sandbox-external) are the follow-up”로 투명 연기. 이는 4.2 선례(planner live smoke가 별도 이벤트였음)와 정합. **추천**: live smoke(12B) 실행 + 의미 판정 경계 update vs add_evidence vs no_change vs conflict의 대표 fixture 쌍을 empirical로 한 번 검증.

### 기타 (정보)
- **create 2중 방어**: adapter parse(`_action`)와 service `JUDGE_ACTIONS`가 둘 다 create를 거부. docstring이 service guard를 “fake-injection seam 방어”로 명시 — defense-in-depth, 정합.
- live smoke는 `LLAMA_BASE_URL`(4.2 smoke와 동일 로컬 llama.cpp `192.168.1.29:9080`) 기반, sandbox-external 명시. 본 검증은 sandbox 제약으로 실실행 안 함(작업자도 follow-up으로 명시).

## Verdict

**합격 (PASS)**.

load-bearing 근거:

1. **Pattern fidelity**: 4.2 `TerminalJsonSearchPlanner`와 동일 골격(async/versioned prompt/strict parse/1 repair/에러 매핑) — “동일 패턴, 리스크 낮다” 주장이 코드로 확인.
2. **Literal/contract 무결점**: `analysis_compare_v1`/task_type/4종-only/“never create”/strict `{action,rationale}`/1 repair/InvalidJudgeResult가 전부 코드↔changelog↔테스트 정합.
3. **핵심 경계 양방향 lock**: create-거부(under-strict: repair 소환 후 InvalidJudgeResult) + 4종 전부 파스(over-strict) + repair 경험 4종 + 누락 template(provider 미호출) + payload-no-create + exact schema. boundary matrix 빈 cell 없음.
4. **env wiring**: `LLM_GATEWAY_BASE_URL` 분기·`ANALYSIS_COMPARE_MAX_TOKENS=512`·template seeding·judge=None 폴백이 factory 테스트로 end-to-end 검증.
5. **수치 독립 재현**: 34 passed(2B.3 계열), 541 passed/45 skipped(전체, 산술 정합).
6. **2B.3 후속 회수 모범**: 직전 검증 G1/G2/G3가 `51e9770`에서 정확히 회수됐고 검증 기록이 커밋됐다.

J1(judgment-quality empirical 검증 연기)은 adapter 계약 밖의 scope 결정으로, 투명 명시됐고 4.2 선례와 정합. 본 slice(2B.3.2 = seam을 실 adapter로 충전)의 계약은 완전히 충족.

## Outstanding items

- **J1(추천, follow-up)**: live smoke(12B llama.cpp, `scripts/phase2b3_compare_judge_live_smoke.py`, sandbox 밖) 실행 + 의미 판정 경계(update↔add_evidence↔no_change↔conflict) 대표 fixture 쌍 empirical 검증. changelog/commit에 이미 연기 명시.
- **커밋 대기**: 본 검증은 commit `aa8d3e9` 기준. owner 승인 시 브랜치 PR/merge. (참고: 작업자가 직전 2B.3 검증 기록을 `51e9770`으로 커밋한 선례가 있으므로, 본 기록도 동일하게 커밋될 수 있음 — owner 판단.)
- **2B.4(이후)**: proposal→versioned upsert/재색인(Chroma) + `MemoryStatus` 두 번째 literal 도입 시 prior_memory canonical-only 필터 non-canonical 제외 회귀(2B.2 O1, HANDOFF #1 추적 중).

## Post-verification follow-up (applied 2026-07-06, 검증자 직접)

본 검증 PASS 후, 검증이 파생한 2건을 검증자가 직접 보강했다(상세는 `docs/daily_logs/2026-07-06/work_log.md` 해당 섹션):

- **ProviderError 누출 수정(본 검증 중 패턴 스윕으로 발견, 본문 J1과는 별개)**: `GatewayGenerateProvider.generate`가 Gateway 장애 시 raise하는 `ProviderError`가 compare endpoint에서 uncaught → HTTP 500 누출(재현으로 확인). v1.6.34 taxonomy(LLM error→502) 적용 결함이라 `analysis_compare_endpoint`에 `except ProviderError → 502` + 회귀 `test_provider_error_during_judge_maps_to_502` 추가. **sibling 부채**(`/context-search` planner·2A extraction에 동일 누출)는 HANDOFF Next Tasks #8로 추적(수정 X, 범위 밖).
- **J1 live smoke 4 경계 강화**: smoke가 단일 pair → matched-pair 4 경계(update/add_evidence/no_change/conflict) 대표 pair로 확장 + `ProviderError` clean 처리. 실 12B 실행·관찰은 sandbox 밖이라 여전히 열림(HANDOFF #1 곁가지).

## Reproduction

```bash
# (1) 패턴 원천 대조
grep -n "class TerminalJsonSearchPlanner\|async def\|get_template\|repair\|ContextSearchFailed\|seed_template" services/application/app/context_search/planner.py
# (2) adapter + wiring
cat services/application/app/analysis/compare_judge.py
git show aa8d3e9 -- services/application/app/main.py
# (3) 테스트 감사 + 후속 회수
cat tests/test_analysis_compare_judge.py
git show aa8d3e9 -- tests/test_analysis_compare_api.py                  # env factory 2
git show 51e9770 -- tests/test_analysis_compare.py tests/test_analysis_compare_api.py   # G1/G2
# (4) 독립 재실행
python3 -m pytest -q tests/test_analysis_compare_judge.py tests/test_analysis_compare.py tests/test_analysis_compare_api.py tests/test_memory_scope.py   # 34 passed
python3 -m pytest -q --ignore=tests/test_memory_mongo.py                                                                                              # 541 passed / 45 skipped
git diff --check                                                                                                                                      # clean
# (5) live smoke(sandbox 밖에서만)
sed -n '1,30p' scripts/phase2b3_compare_judge_live_smoke.py
```
