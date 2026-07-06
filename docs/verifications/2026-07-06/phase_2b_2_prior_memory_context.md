# Verification — Phase 2B.2 prior-memory 검색 + Analysis 비교용 ContextPackage 구현

## Subject metadata

- 날짜: 2026-07-06
- 요청자: 오너 (“클로드 작업 AI가 작업한 부분을 확인하고 검증하고 의심하고 또 의심해줄래? Phase 2B.2 구현을 완료했습니다.”)
- 검증자: Claude Code (독립 감사 — 구현을 하지 않은 제3자 시선, 작업자 주장을 그대로 믿지 않고 일차 소스에서 재도출)
- 대상 slice/artifact: Phase 2B.2 code slice — prior-memory 검색 + Analysis 비교용 ContextPackage(§8 ⑧, SoT v1.6.41). 변경: `services/application/app/context_search/prior_memory.py`(신규), `services/application/app/context_search/models.py`, `services/application/app/main.py`, `tests/test_analysis_context.py`(신규), `tests/test_analysis_context_api.py`(신규), `docs/system-contract-sot.md`, `docs/plans/02b-2-analysis-context-package-decisions.md`, `HANDOFF.md`.
- canonical spec reference(교차 검증용):
  - `docs/system-contract-sot.md` v1.6.41 changelog + §8 ⑧ 추적(line 36/362/364/392/446)
  - `docs/plans/02b-2-analysis-context-package-decisions.md`(Resolved — D1=A, D2=A(semantic seam), D3=A, D4=B(A 포함 hybrid), D5=A, D6=B; F3/F4/F5 착수 명시)
  - `docs/plans/02b-analysis-compare-kickoff-decisions.md` §D6(2B.2에 ⑧ 위임)
  - `docs/plans/04-context-package-completion-decisions.md` §8 ⑧(line 100: “기존 memory type/scope, status/version, 검색 이유”)
  - `docs/plans/analysis-memory-taxonomy.md` §비교용 ContextPackage(line 91: 5필수 — 기존 값·상태·source·version·비교 이유)
  - `services/application/app/memory/models.py`(2B.1 `MemoryEntry`/`MemoryStatus` — PriorMemoryItem 매핑 원천)
  - 선행 검증 `docs/verifications/2026-07-05/phase2b2_brief_spec_gate.md`(착수 전 스펙 게이트 — F1~F5)
- 검증 대상 work source: working tree, uncommitted(git status: 5 modified + 4 untracked). HEAD = 83a91ce.

## Scope

아래 표면을 “did it run”이 아니라 “spec이 요구하는 것을 실제로 잠갔는가” 수준에서 검증:

1. **Spec contract**: 02b-2 브리프 D1~D6 + F3/F4/F5, SoT v1.6.41 changelog/§8 ⑧ 추적, taxonomy 5필수, 2B.1 MemoryEntry 구조와의 정합.
2. **Implementation code**: `prior_memory.py`(신규 전량), `models.py`/`main.py` diff — literal 1:1 대조.
3. **Regression tests**: 신규 16개(`test_analysis_context.py` 10 + `test_analysis_context_api.py` 6) — assertion이 계약을 pin하는지, under-strict/over-strict 양방향 guard 존재.
4. **Public envelope/schema**: HTTP 응답 직렬화(`_analysis_context_payload`), PriorMemoryItem 7필드 직렬화, `/context-search` purpose 거절.
5. **Full test suite**: 보고된 수치(506 passed/45 skipped) 독립 재계산, mongo 3개 error의 환경 귀인 재실증.
6. **문서 정합**: SoT changelog ↔ 미확정목록 ↔ brief ↔ 코드 간 literal 일치.

## Methodology

CLAUDE.md 검증 원칙 — “코드를 먼저 보지 말고 canonical contract scope 먼저 구축 → boundary matrix 락리스트 → 코드/테스트 매핑 → 빈 cell 탐지 → green bar ≠ spec 준수 구분”. 작업자의 work_log/HANDOFF 주장은 독립 재도출 결과와 교차할 때만 인용.

```bash
# (1) 계약 독해 — 브리프 결정 + F3/F4/F5
sed -n '1,132p' docs/plans/02b-2-analysis-context-package-decisions.md
# (2) SoT §8 ⑧ 추적 + v1.6.41 changelog
grep -n "1.6.41\|⑧\|analysis_context\|prior_memory\|scope" docs/system-contract-sot.md
# (3) 선행 계약 교차
sed -n '91p'  docs/plans/analysis-memory-taxonomy.md                  # 5필수
sed -n '100p' docs/plans/04-context-package-completion-decisions.md   # ⑧ 확장 필드
# (4) 2B.1 MemoryEntry 원천(PriorMemoryItem 매핑)
sed -n '22,46p' services/application/app/memory/models.py
# (5) 구현 전량 읽기 — prior_memory.py(신규) + models.py/main.py diff
cat services/application/app/context_search/prior_memory.py
git diff services/application/app/context_search/models.py services/application/app/main.py
# (6) 테스트 감사 대상 읽기
cat tests/test_analysis_context.py tests/test_analysis_context_api.py
# (7) 독립 재실행
python3 -m unittest tests.test_analysis_context tests.test_analysis_context_api -v
python3 -m pytest -q --ignore=tests/test_memory_mongo.py
python3 -m pytest -q tests/test_context_search.py tests/test_context_search_api.py tests/test_context_search_planner.py tests/test_context_search_shared_index.py tests/test_memory_phase2b.py tests/test_memory_api.py tests/test_application_api.py
python3 -m pytest tests/test_memory_mongo.py::MongoMemoryRepositoryTest::test_promoted_memory_round_trips_through_fresh_service   # 환경 귀인
git diff --check
```

## Boundary matrix (선행 계약에서 도출한 lock list → 코드 → 테스트)

| # | 계약 branch | 코드(file:line) | 회귀 테스트 | under-strict | over-strict |
|---|---|---|---|---|---|
| L1 | `ContextSearchPurpose.ANALYSIS_CONTEXT="analysis_context"` literal | `models.py`(diff) enum | `test_returns_canonical…`(purpose==ANALYSIS_CONTEXT) + API `package["purpose"]=="analysis_context"` | ✓ | — |
| L2 | `ContextNeed.PRIOR_MEMORY="prior_memory"` literal | `models.py`(diff) enum | needs 검증 + API `needs=["prior_memory"]` | ✓ | — |
| L3 | PriorMemoryItem 7필드, **value=payload(Mapping)**(F3) | `models.py` PriorMemoryItem; `prior_memory.py:133` `value=entry.payload` | `test_prior_memory_item_carries_five_required_comparison_fields`(`dict(item.value)==payload`, status/version/source_ref_ids/memory_type/match_reason) | ✓ | ✓(exact field mapping) |
| L4 | memory_type 필터(해당 type canonical만) | `prior_memory.py:83` `entry.memory_type in wanted` | `test_memory_type_filter_is_two_directional`(char→m1 / event→m2) + API `test_only_job_candidate_types_are_searched`(event prior, char job→빈) | ✓ | ✓(양방향) |
| L5 | canonical-only 필터(“canonical MemoryEntry 조회”) | `prior_memory.py:82` `entry.status is MemoryStatus.CANONICAL` | should-fire(canonical 반환)은 `test_returns_canonical…`로 검증; **non-canonical 제외 방향은 현재 불가** → 아래 O1 | △ | △ |
| L6 | 빈 memory_types → 빈 package(절대 전체 아님) | `prior_memory.py:77-78` `if not wanted: return ()` | `test_empty_memory_types_returns_empty_package_not_all`(m1/m2 존재해도 빈 types→빈)+ API `test_job_with_no_prior_memories_returns_empty_package` | ✓ | ✓(“not all” 명시적) |
| L7 | **F4 self-exclusion**(`exclude_job_id`로 자기 job memory 제외) | `prior_memory.py:84-87` | `test_self_exclusion_is_two_directional`(exclude job-A→prior만 / None→둘 다) + API `test_returns_prior_memories…excluding_self`(현재 job own 제외, prior job만) | ✓ | ✓(None 케이스=over-strict guard, 주석 명시) |
| L8 | project-scoped 조회(cross-project 격리) | `prior_memory.py:81` `list_memories(project_id=…)` | `test_lookup_is_project_scoped`(project-1→mine만, project-2 memory 제외) | ✓ | ✓ |
| L9 | needs 빈 → 거부 | `prior_memory.py:120-121` | `test_empty_needs_rejected` | ✓ | — |
| L10 | non-prior_memory need → 거부 | `prior_memory.py:122-126` | `test_non_prior_memory_need_rejected`(CURRENT_SCENE) | ✓ | — |
| L11 | Gate pass(prior-only package) | `prior_memory.py:164-173` | `test_gate_passes_prior_memory_only_package`(GATE_PASS, findings=()) | ✓ | ✓(정상 package 거부 안 함=over-strict) |
| L12 | Gate reject — Writing item 누출(`writing_item_in_analysis_package`) | `prior_memory.py:164-170` | `test_gate_rejects_writing_item_leak_two_directional`(macro_items 누출→GATE_REJECT) | ✓ | ✓(L11과 쌍으로 양방향) |
| L13 | HTTP `POST /projects/{project_id}/analysis/jobs/{job_id}/context` 경로 | `main.py`(diff) endpoint | 전체 API 테스트가 해당 경로 사용 | ✓ | — |
| L14 | D4=B job-aware 유도(job candidate types → coarse memory_type 집합, 중복 제거) | `main.py:1030-1033` `dict.fromkeys(...)` | `test_returns_prior_memories_of_job_candidate_types…` + `test_only_job_candidate_types_are_searched` | ✓(단일 type)| △(다중 type 합집합 / 동일 type 중복제거 미검증 → O6) |
| L15 | missing project → 404 | `main.py`(diff) `(AnalysisNotFound, NotFound)→404` | `test_missing_project_returns_404` | ✓ | — |
| L16 | missing job → 404 | `main.py`(diff) | `test_missing_job_returns_404` | ✓ | — |
| L17 | `/context-search`가 analysis_context purpose → 400(Writing-only 분리) | `main.py:1172-1175` `if purpose is not WRITING_CONTEXT: raise` | `test_analysis_context_purpose_rejected_on_writing_endpoint`(400) | ✓ | — |
| L18 | trace optional(analysis_context는 None) | `models.py` `trace: ContextSearchTrace \| None = None` | `test_returns_canonical…`(`package.trace is None`)+ Writing 회귀 126개 green(trace 채우는 경로 유지) | ✓ | ✓(Writing 경로 회귀로 over-strict 방지) |

## Findings

### 1. Literal 1:1 대조 — 계약 ↔ 코드 (양호)

계약 lock list의 모든 literal이 코드에 **paraphrase 없이** 그대로 나타난다:

- 신설 enum: `ContextSearchPurpose.ANALYSIS_CONTEXT="analysis_context"`, `ContextNeed.PRIOR_MEMORY="prior_memory"`(`models.py` diff).
- `PriorMemoryItem` 7필드 = memory_id/memory_type/value/status/version/source_ref_ids/match_reason(`models.py`). taxonomy 5필수(값·상태·source·version·비교 이유)→ value/status/source_ref_ids/version/match_reason 1:1 매핑, memory_id+memory_type은 식별자.
- **F3 value=payload**: `prior_memory.py:133` `value=entry.payload`. `MemoryEntry`에 `value` 필드 없음(`memory/models.py:32-46` 확인)→ payload(Mapping) 매핑이 유일한 정합 해석. 정확.
- F4 self-exclusion: `prior_memory.py:84-87` `not (exclude_job_id is not None and entry.analysis_job_id == exclude_job_id)`. HTTP는 `exclude_job_id=job.id`(`main.py` diff) — “그 job 자신이 승격한 memory” 제외, 잠정값 표시 일관.
- Gate finding literal `writing_item_in_analysis_package`(`prior_memory.py:167`) — 코드↔테스트(`["writing_item_in_analysis_package"]`) 일치.
- HTTP 경로 `POST /projects/{project_id}/analysis/jobs/{job_id}/context`(`main.py` diff) — D6=B Owner decision 경로와 byte-단위 일치(선행 검증 F1 정정 결과 반영).

### 2. 계약 자기모순 교차검증 — 내부 정합 (양호)

- **F2(scope 처리) 정확히 폐쇄**: ⑧ 추적 항목의 “scope” 확장 필드(`04-context-package-completion-decisions.md:100`)는 D1=A가 2B.3에 위임. 따라서 §8 ⑧은 “5필수 완성”이지 “완전 완성”이 아니다. 이 문구가 SoT changelog(line 36/364: “scope는 MemoryEntry 부재로 담지 않음 → §8 ⑧ 추적은 2B.3까지 열림”), 미확정목록(line 362: “scope는 2B.3”), §8 절(line 392: “⑧은 ‘5필수 완성’”), brief(line 107)를 **모두 같은 방향으로** 서술 → 내부 모순 없음. 코드도 PriorMemoryItem에 scope 미포함으로 정합. 선행 검증(2026-07-05)의 F2 이슈가 해석 (a)+문구 정정으로 올바르게 닫혔다.
- **MemoryStatus 단일 ↔ 필터/Gate 정합**: `MemoryStatus`는 `CANONICAL` 단일(`memory/models.py:22-23`). (a) backend canonical 필터는 계약(“canonical MemoryEntry 조회”)이 요구하므로 존재, (b) Gate의 non-canonical 검사는 backend가 이미 보장하므로 미도입 — work_log “non-canonical guard 미도입(불가능 시나리오 방어 회피)”은 Gate에 한정된 서술로 코드와 모순 아님.
- **D5=A purpose 분기 실체화**: `evaluate_analysis_context_gate`가 analysis_context 전용. candidate 금지 무적용(대상이 canonical), 유일 실체 invariant=Writing item 누출 차단. F5(“최소로 정한다”)에 부합.
- changelog ↔ 미확정목록 ↔ brief ↔ 코드 간 literal(빈 memory_types=빈 package, exclude_job_id=job.id, trace=None, `/context-search` 400) 전부 일치.

### 3. 테스트 코드 감사 — green bar ≠ spec 준수 구분 (양호, 단 O1/O6)

테스트 16개를 “auditor”가 아닌 “audit subject”로 읽어 각 assertion이 계약을 실제로 pin하는지 확인:

- **F4 양방향 guard(모범)**: `test_self_exclusion_is_two_directional`는 exclude→prior만(under-strict: F4 제거 시 own 재등장으로 재실패) + None→둘 다(over-strict: 무관 job까지 drop 방지)를 모두 잠그고, 주석에 “Over-strict guard”로 명시. API `…excluding_self`는 실제 promote 경로로 같은 경계 재실증.
- **빈 memory_types over-strict guard**: `test_empty_memory_types_returns_empty_package_not_all`는 fixture에 m1/m2를 두고 빈 types→빈을 검증 → “전체 반환” 버그 도입 시 재실패. 의도적 over-strict 설계.
- **memory_type 양방향**: char/event 양쪽을 각각 조회해 교차 오염 없음을 잠금.
- **Gate 양방향**: pass(`test_gate_passes…`)+reject(`test_gate_rejects…`) 쌍으로 under/over-strict 모두 커버. (단 reject 테스트 이름의 “two_directional”은 쌍 전체를 가리키는 것이지 단일 테스트가 양방향은 아님 → O4 표기.)
- **project 격리 / needs 검증 2종 / 404 2종 / `/context-search` 400** — 전부 계약 branch에 대응, assertion이 공개 envelope(HTTP status, package 필드, gate decision)을 검사.

### 4. 공개 envelope/직렬화 (양호)

- `_analysis_context_payload`(`main.py` diff): package(purpose/status/degraded/token_estimate_total/prior_memories[]) + gate(decision/findings[]) 직렬화. API 테스트가 `package["purpose"]`, `body["gate"]["decision"]`, `item["memory_type"]/["status"]/["value"]/["match_reason"]`를 검사 → envelope/schema 변경 시 재실패.
- PriorMemoryItem 직렬화: `value`→`dict(item.value)`, `status`→`.value`, `source_ref_ids`→`list(...)`. Mapping/enum 직렬화 정확.

### 5. Full suite 독립 재실행 — 보고 수치 재계산 (양호)

- 신규 16개: `python3 -m unittest tests.test_analysis_context tests.test_analysis_context_api -v` → **Ran 16 tests … OK**(독립 재현).
- 전체: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **506 passed, 45 skipped**(작업자 주장과 정확 일치).
- 영향 번들(context_search/memory/application_api): **126 passed** — `ContextPackage.trace` optional 완화와 `/context-search` Writing-only purpose guard가 **기존 Writing 회귀를 깨지 않음**을 실증(작업자 “126개 통과” 주장 재현).
- `git diff --check` → clean(whitespace 이상 없음).

### 6. Mongo 3개 error — 환경 귀인 재실증 (양호, 작업자 무관)

`python3 -m pytest tests/test_memory_mongo.py` → 3 failed. 근본 원인 체인: `pymongo.errors.OperationFailure: Command createIndexes requires authentication, code: 13, codeName: Unauthorized` → `mongo_repository.py:64` `MongoMemoryRepositorySetupError`. 이 파일은 `services/application/app/memory/`(2B.1) 소관이며 **2B.2 변경이 전혀 손대지 않음**(git status로 확인: memory/ 디렉터리 미변경). 작업자의 “localhost:27017 인증 걸린 잔여 Mongo, 내 변경 무관, clean HEAD도 동일 재현” 주장이 그대로 성립. 인증 없는 Mongo로 교체/서 down 시 skip으로 정상화될 경계.

## Issues / Risks

> 아래는 모두 **non-blocking** 관찰이다. 핵심 계약 branch(L1~L4, L6~L18)는 양방향 guard로 잠겨 있고, literal/내부 정합/envelope/수치가 모두 재실증됐다. CLAUDE.md “빈 cell = blocking” 원칙을 L5에 최대 한 적용할 때의 판단은 Verdict에서 따로 다룬다.

### O1. [NON-BLOCKING — 현재 불가능, 2B.4 조건부] canonical-only 필터의 non-canonical 제외 방향이 오늘 테스트 불가

`prior_memory.py:82`의 `entry.status is MemoryStatus.CANONICAL` 필터는 계약(“canonical MemoryEntry 조회”)이 요구하는 lock이며 코드에 존재한다. 그러나 `MemoryStatus`가 `CANONICAL` 단일(`memory/models.py:22-23`)이므로 non-canonical `MemoryEntry`를 **생성할 수 없어** “non-canonical은 제외된다” 방향을 회귀로 잠글 수 없다 — 모든 fixture가 canonical이다. should-fire 방향(canonical이 반환된다)은 `test_returns_canonical…`로 검증됐다.

이것은 2B.1 단일-status 설계의 결과이지 2B.2의 누락이 아니다. `MemoryStatus`에 두 번째 literal(예: 2B.4 versioned upsert의 `superseded`/`obsolete`)이 도입되는 순간 이 필터는 실체를 가지며, 그때 non-canonical 제외 회귀를 추가해야 한다. **추천**: 2B.4 착수 시 `test_noncanonical_memories_excluded_from_prior_memory` 추가. CLAUDE.md “empty cell” 원칙을 엄격 적용하면 이것이 본 검증의 유일한 조건부 항목이다(Verdict 참조).

### O2. [NON-BLOCKING — dead-code, 무해] HTTP `InvalidAnalysisContextRequest → 400` 분기가 HTTP 경로에서 도달 불가

endpoint가 `needs=(ContextNeed.PRIOR_MEMORY,)`로 고정(`main.py` diff)하므로, 유일한 검증 실패(빈 needs / non-prior need)는 HTTP로 발생할 수 없다. `except InvalidAnalysisContextRequest → 400`(`main.py` diff)은 사실상 dead code. 검증 자체는 service layer에서 양방향으로 잠겨 있으므로(L9/L10) 계약 보호는 됐다. 동일 endpoint family의 기존 패턴(service exception → 400 매핑)과 일치해 무해하나, CLAUDE.md §2(불가능 시나리오 오류처리 회피) 관점에서는 미세한 과잉. 그대로 둬도 무방.

### O3. [NON-BLOCKING — 설계 의도, owner 인지 권장] Gate가 HTTP 응답을 차단하지 않는다

endpoint는 gate decision을 package와 함께 직렬화해 **200으로 반환**(GATE_REJECT여도 200). 이는 Phase 4.3 Writing endpoint의 “package 와 독립 Gate 결정을 직렬화해 반환” 패턴과 동일하다. 따라서 L12의 “Writing item 누출 차단”은 이 slice에서 호출자(2B.3 compare)를 위한 **정보 신호/defense-in-depth**이지 HTTP hard-block이 아니다. 설계와 정합하나, owner는 “Gate가 현재 정보성”임을 인지할 것.

### O4. [NON-BLOCKING — 표기] Gate reject 테스트 이름이 단일 방향을 가리켜도 “two_directional”

`test_gate_rejects_writing_item_leak_two_directional`는 reject 한 방향만 단독 단언. 양방향 커버는 `test_gate_passes_prior_memory_only_package`와의 **쌍**으로 성립(둘 다 통과해야 under/over-strict 커버). 커버리지는 진짜 양방향이나, 이름이 단일 테스트를 과대 서술. 표기 정도.

### O5. [NON-BLOCKING — defense-in-depth, F5와 정합] Gate Writing-item-leak invariant가 현재 builder에서 구조적 거의 불가

`build_prior_memory_package`는 항상 `macro_items=()/micro_evidence=()`로 채우므로(`prior_memory.py:109-110`), Writing item은 버그나 직접 조립(테스트가 그렇게 함)으로만 들어온다. 즉 L12 invariant는 데이터 기반 경계라기보다 builder-bug 방어. 이것이 F5(“실체 invariant 하나로 최소화”)에서 작업자가 선택한 그 하나이며 문서화돼 있다 — 허용 범위. owner는 이것이 “canonical 단일 상태에서는 발화 불가능한 경계를 방어”에 가깝다는 점을 인지할 것(O1과 동일 뿌리: 단일-status 설계).

### O6. [NON-BLOCKING — coverage 권장] D4 job-aware 유도의 다중-type 합집합 / 동일-type 중복제거 미검증

`memory_types = tuple(dict.fromkeys(candidate.candidate_type for candidate in candidates))`(`main.py` diff). 현재 API 테스트는 단일 candidate-type job만 다룬다. 따라서 (a) 한 job이 character+event candidate를 둘 다 가질 때 두 type의 prior가 합집합 반환, (b) 같은 type candidate 2개 → `memory_types=(CHARACTER,)` 중복제거, 가 잠기지 않았다. 로직은 자명(`set` membership / `dict.fromkeys`)하나 CLAUDE.md “경계값마다 parametrized” 관점에서 별도 경계. **추천**: 다중 candidate-type job 1개 회귀 추가.

## Verdict

**합격 (PASS)** — 단, CLAUDE.md “boundary matrix 빈 cell = blocking” 원칙을 L5(canonical-only non-canonical 제외 방향)에 **최대 한 엄격 적용**하는 경우에 한해 **조건부 합격**으로 환원 가능(조건 = O1: 2B.4가 `MemoryStatus`에 두 번째 literal을 도입할 때 non-canonical 제외 회귀 추가).

load-bearing 근거:

1. **Literal 무결점**: 계약 lock list의 모든 literal(value=payload 포함)이 코드에 paraphrase 없이 정확히 나타나고, changelog/미확정목록/brief/코드가 모두 같은 방향으로 정합. 내부 모순 탐지 안 됨(F2 scope 처리가 올바르게 “5필수 완성”으로 폐쇄).
2. **핵심 경계 양방향 lock**: F4 self-exclusion, 빈 memory_types→빈 package, memory_type 필터, Gate pass/reject, project 격리, 404×2, `/context-search` 400이 각각 under-strict + over-strict(또는 그에 준하는 쌍)로 잠겼다.
3. **수치 독립 재현**: 16개 신규 OK, 전체 506 passed/45 skipped, 영향 번들 126 passed — 작업자 주장과 정확 일치. trace-optional 완화와 Writing purpose guard가 기존 회귀를 깨지 않음을 실증.
4. **환경 이슈 검증**: mongo 3개 error가 `code 13 Unauthorized`(createIndexes 인증 요구)이며 2B.1 코드(`mongo_repository.py`)에서 발생 — 2B.2 변경 무관이 작업자 주장대로 확인.

**CLAUDE.md 엄격 적용 시 유일한 조건부 항목은 O1 뿐**이다. 이것은 “코드가 경계를 안 지킨다”가 아니라 “2B.1 단일-status 설계 때문에 오늘 그 경계의 부정 방향을 물리적으로 테스트할 수 없다”는 상황이다. 필터(lock)는 존재하며, 부정 방향은 오늘 vacuously true다. 본 검증자의 판단: **2B.2 slice 자체의 계약은 완전히 충족됐으므로 합격**이며, O1 회귀 추가 시점은 non-canonical status를 도입하는 2B.4로 추적한다. owner가 빈 cell 원칙을 문자 그대로 적용해 “2B.2 닫기 전에 non-canonical 회귀를 강제”하고 싶다면, 그것은 `MemoryStatus` 확장을 2B.2로 당기라는 뜻이 되므로 slice 범위(D1=A, 2B.1 위임 존중)와 충돌 — 권하지 않는다.

나머지 O2~O6은 dead-code/표기/coverage 권장/defense-in-depth 인지 사항이며, 어느 것도 2B.2 계약 위반이 아니다.

## Outstanding items

- **O1(추적)**: 2B.4 versioned upsert가 `MemoryStatus`에 `superseded`/`obsolete` 등을 도입할 때 `test_noncanonical_memories_excluded_from_prior_memory` 추가. 그 전까지는 단일-status로 인해 불가.
- **O6(추천)**: 다중 candidate-type job(character+event)의 prior 합집합 반환 + 동일 type 중복제거 회귀 1개 추가(2B.3 통합 시 자연).
- **커밋 미수행**: 작업자는 “커밋은 요청 주시면” 상태. 본 검증은 working tree(uncommitted) 기준. owner 승인 시 커밋.
- **Mongo 환경**: localhost:27017 인증 Mongo(잔여 smoke)를 down 하거나 인증 없는 인스턴스로 교체하면 `tests/test_memory_mongo.py` 3개가 error→skip으로 정상화. 2B.2 무관.
- **F4 잠정값**: `exclude_job_id` self-exclusion은 오너 승인 잠정값. 2B.3 compare(no_change/conflict)와의 상호작용 관찰 후 self-exclusion 유지 vs no_change 흡수 확정 — HANDOFF Next Tasks #1에 이미 추적됨.

## Reproduction

```bash
# (1) 계약 독해 + 선행 계약 교차
sed -n '1,132p' docs/plans/02b-2-analysis-context-package-decisions.md
grep -n "1.6.41\|⑧\|analysis_context\|scope" docs/system-contract-sot.md
sed -n '91p'  docs/plans/analysis-memory-taxonomy.md
sed -n '100p' docs/plans/04-context-package-completion-decisions.md
sed -n '22,46p' services/application/app/memory/models.py   # MemoryStatus 단일 + MemoryEntry(payload, no value)

# (2) 구현 + 테스트 감사
cat services/application/app/context_search/prior_memory.py
git diff services/application/app/context_search/models.py services/application/app/main.py
cat tests/test_analysis_context.py tests/test_analysis_context_api.py

# (3) 독립 재실행
python3 -m unittest tests.test_analysis_context tests.test_analysis_context_api -v          # 16 OK
python3 -m pytest -q --ignore=tests/test_memory_mongo.py                                    # 506 passed / 45 skipped
python3 -m pytest -q tests/test_context_search.py tests/test_context_search_api.py tests/test_context_search_planner.py tests/test_context_search_shared_index.py tests/test_memory_phase2b.py tests/test_memory_api.py tests/test_application_api.py   # 126 passed
python3 -m pytest tests/test_memory_mongo.py::MongoMemoryRepositoryTest::test_promoted_memory_round_trips_through_fresh_service 2>&1 | grep -iE "Unauthorized|code: 13"   # 환경 귀인
git diff --check                                                                              # clean
```
