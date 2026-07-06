# Verification — Phase 2B.3 candidate↔canonical compare + D3 scope key (proposals only)

## Subject metadata

- 날짜: 2026-07-06
- 요청자: 오너 (“다음작업 검증해줘. 커밋 완료하고 다음 작업(Phase 2B.3)까지 진행했습니다.” + “여기서 2B.3을 독립 검증하시겠습니까?”)
- 검증자: Claude Code (독립 감사 — 구현 미관여 제3자, 작업자 주장을 일차 소스에서 재도출)
- 대상 slice/artifact: Phase 2B.3 code slice — candidate↔canonical 대조 + action proposal + D3 scope key(SoT v1.6.42). commit `1c8f9d5`(branch `phase2b-slice-2b-2-prior-memory-context`).
  - 신규: `services/application/app/memory/scope.py`, `services/application/app/analysis/compare.py`, `docs/plans/02b-3-analysis-compare-action-decisions.md`, `tests/test_memory_scope.py`, `tests/test_analysis_compare.py`, `tests/test_analysis_compare_api.py`.
  - 수정: `memory/{models,mongo_repository,service}.py`, `context_search/{models,prior_memory}.py`, `main.py`, `docs/system-contract-sot.md`, `HANDOFF.md`, work_log.
- 보조 검증(2B.2 커밋 `0b706f2`): 직전 검증(`docs/verifications/2026-07-06/phase_2b_2_prior_memory_context.md`)의 O2/O4/O6 보강 및 검증 기록 반영 여부.
- canonical spec reference:
  - `docs/plans/02b-3-analysis-compare-action-decisions.md`(Resolved — D1=A 터미널 JSON, D2=A character-only scope key, D3=A 하이브리드, D4=A proposal only, D5=A scope 저장+승격 산출, D6=self-exclusion 유지, D7=A HTTP)
  - `docs/system-contract-sot.md` v1.6.42 changelog + §8 ⑧ 추적(line 36/363/366/394/448)
  - `docs/plans/02b-analysis-compare-kickoff-decisions.md` §D3(결정적 key)·§D4(action literal 집합)
  - `docs/plans/04-context-package-completion-decisions.md` §8 ⑧(line 100: 확장 필드 “memory type/scope, status/version, 검색 이유”)
  - `services/application/app/memory/models.py`(2B.1 MemoryEntry), `analysis/schema.py`(payload shape), `analysis/models.py`(AnalysisCandidate)
  - 직전 검증 `docs/verifications/2026-07-06/phase_2b_2_prior_memory_context.md`(O1~O6)
- 검증 대상 work source: commit `1c8f9d5`(HEAD). 2B.2 보강은 commit `0b706f2`.

## Scope

1. **Spec contract**: 02b-3 브리프 D1~D7, SoT v1.6.42 changelog, §8 ⑧ 완전 완성 주장, 부모 브리프 D3/D4 위임 회수.
2. **Implementation code**: `scope.py`·`compare.py`(신규 전량), `memory`/`context_search`/`main.py` diff — literal 1:1 대조.
3. **Regression tests**: 신규 19개(`test_memory_scope.py` 5 + `test_analysis_compare.py` 8 + `test_analysis_compare_api.py` 6) — assertion이 계약을 pin하는지, under/over-strict 양방향 guard.
4. **Public envelope/schema**: `ActionProposal` 직렬화, scope 직렬화(`_scope_payload`), §8 ⑧ 5+1 필드.
5. **Full suite**: 보고 수치(526 passed/45 skipped) 독립 재계산.
6. **2B.2 보강 회수 검증**: `0b706f2`가 직전 검증 O2(dead-code)/O4(이름)/O6(다중-type 테스트)를 실제로 반영했는지, 검증 기록이 커밋됐는지.
7. **문서 정합**: changelog ↔ 미확정목록 ↔ brief ↔ 코드 간 literal 일치 + 브리프 내부 모순 탐지.

## Methodology

CLAUDE.md 검증 원칙 — contract scope 먼저 → boundary matrix 락리스트 → 코드/테스트 매핑 → 빈 cell 탐지 → green bar ≠ spec 준수 구분. 작업자 주장은 독립 재도출 결과와 교차할 때만 인용.

```bash
# (1) 계약 독해 — D1~D7 + F4/D6 + 헤드라인 긴장
sed -n '1,140p' docs/plans/02b-3-analysis-compare-action-decisions.md
# (2) SoT v1.6.42 changelog + §8 ⑧ 추적
grep -n "1.6.42\|⑧\|scope" docs/system-contract-sot.md
# (3) 선행 계약 교차
sed -n '100p' docs/plans/04-context-package-completion-decisions.md          # ⑧ 확장 필드
# (4) 핵심 신규 코드 전량
cat services/application/app/memory/scope.py services/application/app/analysis/compare.py
# (5) diff — memory/context_search/main.py
git show 1c8f9d5 -- services/application/app/memory/ services/application/app/context_search/ services/application/app/main.py
# (6) 2B.2 보강 — O2/O4/O6 + 검증 기록 커밋
git show 0b706f2 -- services/application/app/main.py | grep -A30 analysis_context_endpoint
grep -n "def test_" tests/test_analysis_context.py tests/test_analysis_context_api.py
git show --stat 0b706f2 | grep verifications
# (7) 테스트 감사 대상 읽기 + 독립 재실행
cat tests/test_memory_scope.py tests/test_analysis_compare.py tests/test_analysis_compare_api.py
python3 -m pytest -q tests/test_memory_scope.py tests/test_analysis_compare.py tests/test_analysis_compare_api.py
python3 -m pytest -q --ignore=tests/test_memory_mongo.py
git diff --check
```

## Boundary matrix (계약 lock list → 코드 → 테스트)

| # | 계약 branch | 코드(file:line) | 회귀 테스트 | under-strict | over-strict |
|---|---|---|---|---|---|
| L1 | `CompareAction` 5 literal(create/update/add_evidence/no_change/conflict) | `compare.py:36-41` | 전 compare 테스트가 action 값 사용 | ✓ | — |
| L2 | `JUDGE_ACTIONS`이 create 제외(judge는 create 못 낸다) | `compare.py:46-53,152-156` | `test_judge_returning_create_is_rejected`(InvalidJudgeResult) | ✓ | ✓(`test_single_match…` ADD_EVIDENCE 수락이 over-strict pair) |
| L3 | character → `MemoryScope("character", 정규화 name)` | `scope.py:37-42` | `test_character_scope_over_normalized_name` | ✓ | — |
| L4 | event/open_question → `None`(identity 대조 제외, D2=A) | `scope.py:43` | `test_event_has_no_deterministic_scope` + `test_open_question_has_no_deterministic_scope` | ✓ | ✓(`test_event_is_always_create_even_with_prior_event_memory` = over-strict: prior 있어도 create) |
| L5 | 정규화 = 공백 collapse + casefold | `scope.py:29-31` | `test_name_normalization_is_case_and_whitespace_insensitive` + `test_normalize_name_direct` + compare `test_match_uses_normalized_name` | ✓ | ✓(양방향: "Ariel Song"↔"  ariel   song ") |
| L6 | 매칭 0개 → `create`(event/question 포함, 결정적) | `compare.py:120-129` | `test_character_with_no_prior_is_create` + `test_event_is_always_create…` + API `test_no_match_returns_create_proposal_without_judge` | ✓ | △(다른 character identity→no-match 미명시 → G1) |
| L7 | 복수 동일 identity → `conflict`(결정적, 2B.1 중복 표면화) | `compare.py:130-142` | `test_duplicate_canonical_identity_is_conflict_without_judge` | ✓ | ✓(`test_single_match…` 1개→judge가 conflict 아님) |
| L8 | 1매칭 + judge None → `CompareJudgeNotConfigured`(HTTP 503) | `compare.py:144-148`; `main.py` 503 | `test_match_needs_judge_else_503_signal` + API `test_match_without_judge_returns_503` | ✓ | — |
| L9 | 1매칭 + judge → 라벨; judge-create → `InvalidJudgeResult` | `compare.py:149-163` | `test_single_match_is_labeled_by_judge` + `test_judge_returning_create_is_rejected` + API `test_match_with_injected_judge…` | ✓ | ✓ |
| L10 | **D6 self-exclusion**(`analysis_job_id != job_id`) | `compare.py:179-181` | `test_self_exclusion_is_two_directional`(own job→CREATE+judge 0호출 / 다른 job→UPDATE) | ✓ | ✓(명시적 under/over-strict 주석) |
| L11 | scope 승격 시 산출(D5=A, MemoryEntry 저장) | `service.py:135` `scope=derive_scope(...)` | API `test_promoted_character_memory_serializes_scope` | ✓ | — |
| L12 | `PriorMemoryItem.scope` 추가 → §8 ⑧ 완전 완성 | `context_search/models.py`+`prior_memory.py:146` | L11 envelope 테스트가 scope 직렬화 검증 | ✓ | — |
| L13 | §8 ⑧ 전 필드(memory type/scope/status/version/검색이유) | PriorMemoryItem 7필드+scope | `test_promoted_character_memory_serializes_scope`(scope={scope_type,scope_id}) | ✓ | — |
| L14 | **proposal only**(memory 쓰기 없음, D4=A) | `compare.py`(put_memory 호출 없음) | 코드 검증 — 쓰기 call 부재 | ✓ | — |
| L15 | HTTP `POST /projects/{project_id}/analysis/jobs/{job_id}/compare` | `main.py` endpoint | 전체 API 테스트가 해당 경로 | ✓ | — |
| L16 | `CompareJudgeNotConfigured` → 503 | `main.py` | API `test_match_without_judge_returns_503` | ✓ | — |
| L17 | `InvalidJudgeResult` → 502 | `main.py` | **service-layer에서만 raise 검증; HTTP 502 status 미검증** → G2 | △ | — |
| L18 | missing project/job → 404 | `main.py` | API `test_missing_project_returns_404` + `test_missing_job_returns_404` | ✓ | — |
| L19 | scope HTTP 직렬화(None or {scope_type,scope_id}) | `main.py _scope_payload` | `test_promoted_character_memory_serializes_scope`(정규화 "ariel song") | ✓ | — |
| L20 | candidate scope 즉석 산출(2A candidate 스키마 미변경, D5 상세) | `compare.py:118`; `analysis/models.py` 미변경 | `git show --stat`로 analysis/models.py 부재 확인 | ✓ | — |

## Findings

### 1. Literal 1:1 대조 — 계약 ↔ 코드 (양호)

- `CompareAction` 5 literal + `JUDGE_ACTIONS`(create 제외)가 코드와 정확 일치. judge-create→`InvalidJudgeResult` 분기(`compare.py:152-156`)는 계약(D3=A “judge는 create 못 낸다”)를 그대로 실체화.
- **D2=A scope**: `derive_scope`가 character만 `MemoryScope("character", normalize_name(name))`, event/open_question은 `None`. `normalize_name=" ".join(name.split()).casefold()` = changelog “공백 collapse + casefold”와 byte 정합. character payload에서 name이 빈 문자열/비문자/부재면 `None` 반환(→ create) — 방어적으로 정확.
- **D3=A 하이브리드 3분기**가 `_compare_candidate`에 정확히 순서 배치: 0매칭→create(120) / >1→conflict(130) / 1+judgeNone→503(144) / 1+judge→라벨(149). 판정 우선순위(conflict가 judge보다 먼저)가 2B.1 중복 canonical을 결정적으로 표면화하는 계약 의도와 정합.
- **D5=A scope 저장**: `MemoryService.promote_candidate`가 `scope=derive_scope(candidate.candidate_type, candidate.payload)`로 산출(`service.py:135`). Mongo round-trip(`_memory_doc`/`_to_memory`의 scope None-or-dict)·`_memory_payload`·`_prior_memory_item_payload`·`_scope_payload` 전부 일관.
- **D6 self-exclusion 확정**: `_find_matches`의 `entry.analysis_job_id != job_id`(`compare.py:181`). 2B.2의 F4 잠정값이 2B.3에서 compare no_change 상호작용 관찰 후 **유지**로 확정 — 브리프 D6·changelog·HANDOFF가 같은 방향.
- **D7=A HTTP**: 경로·503/502/404 매핑·`compare_service` 주입 param 전부 계약과 일치.

### 2. §8 ⑧ 완전 완성 주장 — 검증 (양호, 모순 없음)

`04-context-package-completion-decisions.md:100`의 ⑧ 확장 필드 “기존 memory type/scope, status/version, 검색 이유” ↔ PriorMemoryItem 필드: memory_type ✓ / **scope ✓(신규)** / status ✓ / version ✓ / source_ref_ids(source) ✓ / match_reason(검색 이유) ✓ / value(기존 값) ✓. ⑧ 전 필드 충족 → “완전 완성” 주장은 참. SoT line 394/446도 같은 결론. 직전 검증의 F2/O1(scope 누락)이 2B.3에서 회수됐다. changelog·미확정목록(line 363 “⑧ scope는 v1.6.42로 닫힘”)·brief·코드 모두 정합.

### 3. 테스트 코드 감사 — 양방향 guard (양호, 단 G1/G2)

- **D6 self-exclusion 양방향(모범)**: own job→CREATE + judge 0호출(under-strict: 제거 시 own이 match해 judge 호출) / 다른 job→UPDATE(over-strict: 무관 job까지 제외 방지). 명시적 주석.
- **judge-create 거부**: under-strict(거부)+ `test_single_match…`(유효 라벨 수락) over-strict pair.
- **conflict**: 2 canonical 동일 identity→CONFLICT + 1 match→judge(conflict 아님) pair.
- **event/question always create**: `test_event_is_always_create_even_with_prior_event_memory`가 over-strict(prior event memory 있어도 create)를 잠가 D2=A 경계를 탄탄히 검증.
- **scope 직렬화 envelope**: API 테스트가 `listed[0]["scope"]=={"scope_type":"character","scope_id":"ariel song"}`(입력 "  Ariel Song " 정규화)로 §8 ⑧ completion을 공개 envelope에서 검증.
- **judge 주입 wiring**: `_build(judge=FakeJudge(...))` → `create_app(compare_service=...)` → 매칭 시 라벨 반환 흐름을 end-to-end 검증.

### 4. 2B.2 커밋(0b706f2) 보강 회수 — 직전 검증 O2/O4/O6 (양호)

직전 검증(`phase_2b_2_prior_memory_context.md`)의 non-blocking 관찰이 코드로 회수됐다:
- **O2(dead-code 제거)**: `/context` endpoint의 도달 불가 `except InvalidAnalysisContextRequest→400` 제거. 현재 코드는 `build_prior_memory_package(request)` 직접 호출 + “needs is fixed to (PRIOR_MEMORY,) … no InvalidAnalysisContextRequest→400 branch to add (request validation is a service-level contract)” 주석. 정확한 회수.
- **O4(이름 정정)**: `test_gate_rejects_writing_item_leak_two_directional` → `test_gate_rejects_writing_item_leak`로 misleading 접미사 제거. 양방향 커버는 `test_gate_passes_prior_memory_only_package`와의 쌍으로 유지.
- **O6(다중-type 테스트)**: `test_job_context_unions_multiple_types_and_dedups_same_type` 추가 → API 회귀 6→7(총 17). v1.6.41 changelog도 “17개 회귀 … O6 포함 / O2 dead-code 제거”로 갱신.
- 검증 기록 자신(`docs/verifications/2026-07-06/phase_2b_2_prior_memory_context.md`, 200줄)이 `0b706f2`에 커밋됨(`git show --stat` 확인).

### 5. Full suite 독립 재실행 — 수치 재계산 (양호)

- 신규 19개: `pytest tests/test_memory_scope.py tests/test_analysis_compare.py tests/test_analysis_compare_api.py` → **19 passed**.
- 전체: `pytest -q --ignore=tests/test_memory_mongo.py` → **526 passed, 45 skipped**(작업자 주장과 정확 일치; 506(2B.2 16개)+1(2B.2 O6)+19(2B.3)=526 산술 정합).
- mongo 3개 error은 직전 검증에서 이미 `code 13 Unauthorized`(createIndexes 인증)로 환경 귀인 확정 — 2B.3도 `mongo_repository.py`의 scope round-trip만 추가했고 인증 경로는 동일.

## Issues / Risks

> 모두 **non-blocking**. 핵심 계약 분기(L1~L16, L18~L20)는 양방향 guard로 잠겨 있고, literal/§8 ⑧ completion/수치/2B.2 보강 회수가 재실증됐다.

### G1. [NON-BLOCKING — coverage 권장] “다른 character identity → no-match → create” 미명시

L6의 should-fire(no prior → create)와 L3의 should-fire(같은 identity match)는 잠겼으나, **should-NOT-fire “다른 이름의 character끼리는 match하지 않는다”** 가 명시적 회귀로 없다. mechanism은 자명한 dataclass 구조 동치(`entry.scope == scope`)이나, D2=A가 “identity = 정규화 name, 다른 이름 = 다른 대상”을 계약으로 정의하므로 이 음 방향이 하나의 boundary. 추천: character 'Ariel' 후보 vs character 'Bob' prior → create 1개 회귀.

### G2. [NON-BLOCKING — coverage 권장] `InvalidJudgeResult → 502` HTTP status가 API 미검증

L17. service-layer에서 `InvalidJudgeResult` raise는 잠겼으나(`test_judge_returning_create_is_rejected`), HTTP 502 status assertion을 하는 API 테스트가 없다. 502 catch는 2-line이며 테스트된 503 catch와 동일 패턴이라 위험은 낮다. 추천: `FakeJudge(CREATE)` 주입 후 `/compare` → 502 API 회귀 1개.

### G3. [NON-BLOCKING — 브리프 내부 모순, 문서 정정] D5 요약표 vs 상세 결정 (candidate scope 저장 여부)

- 브리프 **요약표(line 137)**: “scope를 **MemoryEntry/candidate/PriorMemoryItem**에 저장”
- 브리프 **상세 D5(line 125, Owner decision)** + changelog + 코드: “candidate 측 scope는 compare 시 payload에서 **즉석 산출**(2A candidate 저장 스키마 미변경)”

`git show --stat 1c8f9d5`에 `analysis/models.py` 부재 → `AnalysisCandidate`에 scope 필드 없음 → `compare.py:118`에서 즉석 산출. 즉 코드는 **상세 결정**을 따른다(요약표가 “candidate에 저장”이라고 잘못 기술). CLAUDE.md “내부 모순은 원칙적으로 blocking”이나, 상세 결정·changelog·코드가 모두 같은 방향(즉석 산출)이라 해석 단일 → 결정 자체의 모호함은 없고 요약표 1곳의 정정 대상. 추천: 요약표에서 “candidate” 제거 또는 “MemoryEntry/PriorMemoryItem에 저장, candidate는 즉석 산출”로 정정.

### G4. [NON-BLOCKING — 설계 의도, owner 인지] 운영 `/compare`는 judge 미주입이라 매칭 시 503

기본 `create_app`이 `AnalysisCompareService(memory_service=memory)`로 judge 없이 wiring. 따라서 매칭 pair는 503, no-match(create)·duplicate(conflict)만 결정적 served. 이는 4.1→4.2 리듬(계약+seam 먼저, 실 adapter는 다음 증분)과 정합하며 changelog·commit message·HANDOFF에 투명 명시. owner 인지 사항.

## Verdict

**합격 (PASS)**.

load-bearing 근거:

1. **Literal 무결점 + 추측 구현 부재**: D1~D7가 코드에 paraphrase 없이 정확히 실체화. 특히 D3=A 하이브리드 3분기(create/conflict/judge)의 우선순위·judge-create 거부·self-exclusion이 계약 그대로. scope 정규화(공백 collapse+casefold)도 byte 정합.
2. **§8 ⑧ 완전 완성 검증**: PriorMemoryItem.scope 추가로 ⑧ 확장 필드(memory type/scope/status/version/검색이유)가 전 충족. 직전 검증 F2/O1(scope 누락)이 회수됐고 changelog/미확정목록/brief/코드가 정합.
3. **핵심 경계 양방향 lock**: D6 self-exclusion, judge-create 거부, conflict(중복 canonical), event/question always-create, scope 정규화 match, 503, 404×2, scope 직렬화가 under/over-strict(또는 쌍)로 잠겼다.
4. **수치 독립 재현**: 19 신규 OK, 전체 526 passed/45 skipped(산술 정합), mongo 3개 error은 환경(직전 검증 확정).
5. **2B.2 보강 회수 확인**: 직전 검증 O2/O4/O6가 코드로 정확히 반영됐고 검증 기록 자신이 커밋됐다.

**CLAUDE.md “빈 cell = blocking” 관점**: 본 slice의 boundary matrix에서 채우지 못한 cell은 G1(다른 identity 음 방향)·G2(502 HTTP status) 두 coverage cell 뿐이며, 둘 다 “코드가 경계를 안 지킨다”가 아니라 “양방향 중 한 방향의 명시적 회귀가 빠졌다”이다. 둘 다 mechanism이 자명하고 under-strict(혹은 service-layer)는 잠겨 있으므로, 2B.3 계약 위반이 아닌 coverage 강화 후보로 분류한다(차단 아님). owner가 엄격 적용을 원하면 G1/G2 회귀 추가 후 2B.3.2로 진행.

G3(브리프 요약표 모순)은 문서 정정 대상이지 코드/결정 모순이 아니다(상세 결정+코드가 단일 해석). G4는 설계 의도(투명 명시).

## Outstanding items

- **G1(추천)**: 다른 character identity → no-match → create 회귀 1개.
- **G2(추천)**: `InvalidJudgeResult → 502` API 회귀 1개(create 반환 FakeJudge 주입).
- **G3(문서 정정)**: 브리프 D5 요약표 line 137에서 “candidate에 저장” 정정(상세 결정=즉석 산출에 맞춤).
- **2B.3.2(다음 증분, HANDOFF #1)**: 실제 Gateway 터미널-JSON `CompareJudge` adapter(versioned prompt `analysis_compare_v1` + `/v1/generate` 1-turn + strict parse/repair + `LLM_GATEWAY_BASE_URL` wiring + live smoke). 이 시점에 판정 경계(update↔add_evidence↔no_change↔conflict)를 fixture로 양방향 잠글 것.
- **2B.2 O1 forward(HANDOFF #1에 추적됨)**: 2B.4가 `MemoryStatus` 두 번째 literal 도입 시 prior_memory canonical-only 필터의 non-canonical 제외 회귀 추가(직전 검증 O1).
- **커밋 대기**: 본 검증은 commit `1c8f9d5` 기준. owner 승인 시 브랜치 PR/merge.

## Reproduction

```bash
# (1) 계약 + 선행 계약 교차
sed -n '1,140p' docs/plans/02b-3-analysis-compare-action-decisions.md
grep -n "1.6.42\|⑧\|scope" docs/system-contract-sot.md
sed -n '100p' docs/plans/04-context-package-completion-decisions.md

# (2) 핵심 신규 코드 + diff
cat services/application/app/memory/scope.py services/application/app/analysis/compare.py
git show 1c8f9d5 -- services/application/app/memory/ services/application/app/context_search/ services/application/app/main.py

# (3) 2B.2 보강 회수 확인
git show 0b706f2 -- services/application/app/main.py | grep -A25 analysis_context_endpoint   # O2 dead-code 제거
grep -n "def test_" tests/test_analysis_context_api.py                                       # O6 = 7번째
git show --stat 0b706f2 | grep verifications                                                 # 검증 기록 커밋
git show --stat 1c8f9d5 | grep "analysis/models" || echo "candidate schema unchanged (D5 상세 준수, G3)"

# (4) 테스트 감사 + 독립 재실행
cat tests/test_memory_scope.py tests/test_analysis_compare.py tests/test_analysis_compare_api.py
python3 -m pytest -q tests/test_memory_scope.py tests/test_analysis_compare.py tests/test_analysis_compare_api.py   # 19 passed
python3 -m pytest -q --ignore=tests/test_memory_mongo.py                                                          # 526 passed / 45 skipped
git diff --check                                                                                                  # clean
```
