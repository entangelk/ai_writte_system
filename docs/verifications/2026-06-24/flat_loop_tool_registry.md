# 검증 기록 — Flat Loop Tool Registry 계약 slice

## Subject metadata

- 일자: 2026-06-24
- 요청자: 사용자("다음작업 검증해줘")
- 검증자: 독립 검증 AI(Claude Code)
- 대상 slice/artifact: flat loop tool registry 계약 slice — `docs/plans/flat-loop-gate.md` §Domain Tool Registry, 그리고 Phase 2/4/5·gemma4-reuse·README·CHANGELOG·HANDOFF·work_log 동기화
- canonical spec reference:
  - `docs/plans/flat-loop-gate.md` 상태 `Draft`(decision/tool registry slice 소유자 확정), §Domain Tool Registry 계약·§tool registry boundary matrix
  - `docs/plans/gemma4-reuse.md` §평면형 Agentic 구조·§종료 decision 논의안·§Loop Gate 보강점
  - `docs/plans/02-analysis-pipeline.md` §Phase 2B, `docs/plans/04-agentic-search.md` §Agentic 실행 경계·§착수 전 결정사항, `docs/plans/05-writing-ai.md` §Writing AI 경계
  - 직교 원칙의 정본: `docs/plans/flat-loop-gate.md` §세 Gate는 다른 층위(decision slice에서 확정)
- source of the work being verified: working tree, uncommitted(`git status --porcelain` 9개 파일 modified, HEAD `08567d8`). 코드 변경 없음 — 계약 문서 slice. 기존 contract 회귀 44개는 변경 없이 통과해야 한다.
- 구현 환경: Python 3.12.3.

## Scope

본 slice는 구현 코드가 아니라 **계약 문서**다. 따라서 검증은 "green bar"가 아니라 계약 감사·내부 일관성·교차참조 정확성·stale literal sweep·기존 회귀 비회귀에 있다. 점검한 표면:

1. spec contract — `flat-loop-gate.md` §Domain Tool Registry(등록 조건, argument validation 5단계, v1 tool 6종·task profile allowlist, preflight vs domain Gate 독립)
2. 내부 일관성 — per-tool `허용 profile` ↔ per-profile `허용 tool` 양방향 일치, read-only 제약, decision literal 매핑
3. boundary matrix — 6개 경계의 should-fire/should-NOT-fire 완결성
4. 교차참조 동기화 — Phase 2/4/5·gemma4-reuse·README가 allowlist/직교 원칙/preflight 독립을 정확히 인용
5. stale literal sweep — 이전 예시 도구명(`search_context`/`resolve_memory`) 잔존 여부
6. 동기화 문서 — CHANGELOG·HANDOFF·work_log의 tool registry 항목 정확성
7. 비회귀 — `git diff --check`, 기존 contract 회귀 44개 통과

## Methodology

1. **작업자 주장을 믿지 않고 재도출**: 44/44·`git diff --check`·stale literal grep을 검증자가 직접 재실행.
2. **양방향 일관성 삼각검증**: v1 tool 표의 `허용 profile` 열과 task profile 표의 `허용 tool` 열을 양방향으로 대조해 빈 칸·모순 점검.
3. **계약 자기 모순 점검**: tool registry preflight 독립 명제 ↔ decision slice의 직교 원칙 ↔ Phase 2/4/5 Gate 인용 교차 대조.
4. **교차참조 정합성**: git diff로 Phase/gemma4-reuse/README/CHANGELOG/HANDOFF/work_log의 변경이 flat-loop-gate 본문과 일치하는지 확인.
5. **boundary matrix 완결성**: 각 경계가 should-fire + should-NOT-fire를 가지며, should-NOT-fire가 명명된 decision으로 귀결되는지.

사용한 정확한 명령은 Reproduction에 있다.

## Findings

### 1. v1 tool ↔ task profile 양방향 일관성 (빈 칸 없음)

per-tool `허용 profile` ↔ per-profile `허용 tool` 양방향 대치:

| Tool | tool표 허용 profile | analysis_compare(5) | context_search(3) |
|---|---|---|---|
| `search_memory` | analysis_compare, context_search | ✓ | ✓ |
| `load_memory` | analysis_compare, context_search | ✓ | ✓ |
| `load_snapshot` | analysis_compare | ✓ | (제외 ✓) |
| `compare_memory` | analysis_compare | ✓ | (제외 ✓) |
| `validate_candidate` | analysis_compare | ✓ | (제외 ✓) |
| `validate_context` | context_search | (제외 ✓) | ✓ |

profile별 합계: analysis_compare = 5(search/load_memory/load_snapshot/compare/validate_candidate), context_search = 3(search/load_memory/validate_context), writing_generate = 0. 양쪽 표가 완전히 일치. 모순·빈 칸 없음. ✓

### 2. read-only 제약 일관

6종 tool 모두 조회·대조·preflight로 제한됨. 저장·승인·canon·index side effect 금지가 본문(§Domain Tool Registry 도입부)과 각 tool 제한 열·boundary matrix(Gate 합성·Writing 경계 행)에 일관. writing_generate = tool 없음이 §Writing AI 경계와 일치. ✓

### 3. argument validation 5단계 ↔ decision 매핑

5단계 검증(parse 1회·object-root schema·required/type/enum/bounds + additionalProperties:false·coercion 금지·검증 후 handler) 실패 → `invalid_tool_arguments`. 이는 decision slice의 `invalid_tool_arguments` 정의(malformed args + 실행 차단)와 gemma4-reuse "`{}` 강제 금지" 보강점과 일치. parse 실패를 `{}`로 바꾸지 않는다는 명시가 참조 구현의 결함 회피와 정합. ✓

### 4. project_id 주입 ↔ 단일 사용자 경계

`project_id`/task/trace/deadline은 모델 arguments가 아니라 신뢰된 `ToolExecutionContext`에서 주입, handler는 모든 조회에 context의 `project_id` 강제. MVP 단일 사용자 + `project_id` 경계 원칙(00-foundations)과 일치. 모델이 project scope를 args로 바꿀 수 없는 구조. ✓

### 5. preflight vs domain Gate 독립 (직교 원칙 일관)

`compare_memory`/`validate_candidate`/`validate_context`는 loop 중 preflight이며 "loop 후 Analysis/Context Gate는 항상 독립 실행, Loop decision과 domain Gate 결과는 계속 직교"로 명문화. boundary matrix "Gate 합성" 행(validate tool 성공을 Gate 통과로 간주하지 않음)이 이를 lock. decision slice의 직교 원칙과 모순 없음. Phase 2·04에 같은 명제가 인용됨. ✓

### 6. boundary matrix 완결성 (6 경계)

| 경계 | should-fire | should-NOT-fire | 귀결 decision |
|---|---|---|---|
| allowlist | 등록·허용 tool만 실행 | 미등록/타 profile/spawn/delegate/nested | `blocked` 명시 ✓ |
| arguments | schema-valid만 handler | invalid JSON/schema/unknown/coercion | `invalid_tool_arguments` 명시 ✓ |
| project scope | context project_id로만 조회 | 모델 arg scope 변경/cross-project 반환 | (decision 미명시 — O1) |
| runtime failure | valid args 후 non-retryable | argument 실패 | `tool_error` 명시 ✓ |
| Gate 합성 | loop 후 domain Gate 실행 | validate 성공≠Gate 통과 | (구조 명제, decision 아님) ✓ |
| Writing 경계 | 검증된 ContextPackage로 tool 없는 생성 | Writing DB/검색 tool 직접 접근 | `blocked` 계열 (04 경계와 일치) ✓ |

5/6 경계가 should-fire + should-NOT-fire + 명명된 decision을 갖춘다.

### 7. 교차참조 동기화 정확

- `02-analysis-pipeline.md`: "search/load/compare/validate tool" → "`flat-loop-gate.md`의 `analysis_compare` allowlist"로 정확 치환, compare/validate preflight 명제 추가. ✓
- `04-agentic-search.md`: "search/resolve/validate tool" → "`context_search` allowlist"로 치환, validate_context preflight 추가, 착수 전 결정 #9(flat loop 종료 decision과 Context Gate 관계)를 `[x] 직교·순차 합성`으로 해소 표기. ✓
- `05-writing-ai.md`: `writing_generate` tool 없음 명제 추가. ✓
- `gemma4-reuse.md`: 평면 구조 도면의 예시 도구명을 확정 6종으로 갱신, 종료 decision 논의안 `needs_review`→`awaiting_review`, "literal 확정 전" 문구를 "decision slice에서 확정"으로 갱신. ✓
- `README.md`: flat-loop-gate 설명을 "종료 decision과 tool registry 계약"으로 갱신. ✓

### 8. stale literal sweep

`grep -rn "search_context\|resolve_memory" docs/` → 잔존 0건. 이전 예시 도구명이 문서 어디에도 남지 않음. ✓

### 9. 동기화 문서·비회귀

- `CHANGELOG.md`: tool allowlist·strict validation·read-only 6종·Gate 비우회 원칙 Added 항목 + 사용자 결정 narrative 추가. 본문과 일치. ✓
- `HANDOFF.md`: Current Status·Active Decisions(2줄 추가)·Next Tasks·Project Structure 갱신. tool registry 6종·profile allowlist·project_id 주입·preflight 독립이 본문과 일치. ✓
- `work_log.md`: Completed work(tool slice) 항목 + Issues found(token budget/usage 충돌) 항목 + Decisions(2줄) + Next steps 갱신. ✓
- `git diff HEAD --check` → whitespace 오류 0. ✓
- `python3 -m unittest discover -s tests` → Ran 44 tests, OK(코드 변경 없음, 비회귀 확인). ✓

### 10. 작업자의 budget/usage 충돌 보고 (프로세스 적합)

작업자가 tool registry slice 도중 token budget과 Gateway optional `usage`→0 계약의 충돌을 발견하고, 이를 **해당 slice에서 임의 해결하지 않고** work_log Issues + HANDOFF Next Task #1로 올려 사용자 결정을 요청했다. CLAUDE.md("verifier does not silently fix", " recorded decision과 충돌 시 사용자에게 기준 확인")에 부합. 이 충돌 자체는 tool registry slice 범위 밖(budget slice)이므로 본 verdict에 영향을 주지 않는다.

## Issues / Risks

> blocking 결함 없음. 아래는 비차단 informational.

### O1 (정보, non-blocking — boundary matrix project scope 행의 decision 미명시)

boundary matrix "project scope" 행의 should-NOT-fire("모델 argument로 project scope 변경/cross-project 결과 반환 금지")가 어느 terminal decision으로 귀결하는지 명시돼 있지 않다. 다만 `project_id`는 모델 args가 아니라 신뢰된 context에서 주입되므로 모델이 scope를 바꿀 수 있는 경로 자체가 없고, cross-project 반환은 handler 자체의 정확성 영역이지 loop terminal decision이 아니다. 따라서 본 행은 handler-contract 경계로 해석되며, loop decision으로 명시할 필요는 없다. 보강 원하면 handler가 cross-project 시도를 `tool_error`로 분류한다는 한 줄을 추가할 수 있으나 우선순위 낮음.

### O2 (정보, non-blocking — 구현 회귀 미존재)

본 slice는 계약 문서만 변경하고 구현 코드/회귀를 추가하지 않았다. boundary matrix는 향후 Phase 4 구현 slice의 lock list다. 이는 slice 범위(tool registry **계약**)로서 타당하며, 구현 시점에 양방향 회귀가 추가돼야 한다(별명: allowlist/argument/project-scope/Gate 합성/Writing 경계). 본 검증은 계약 감사로 통과 판단하되, green bar(44/44)는 비회귀 증거일 뿐 주 판단이 아님을 명시.

## Verdict

**합격(pass).**

load-bearing 이유:

1. **내부 일관성**: v1 tool 6종 ↔ task profile 양방향 대치가 빈 칸·모순 없이 일치(analysis_compare 5종, context_search 3종, writing_generate 0종). read-only 제약이 본문·tool 제한 열·boundary matrix에 일관.
2. **계약 자기 모순 없음**: argument validation 5단계→`invalid_tool_arguments`, preflight 독립↔직교 원칙, project_id 주입↔단일 사용자 경계가 decision slice 및 gemma4-reuse 보강점과 정합.
3. **boundary matrix**: 6 경계 중 5개가 should-fire + should-NOT-fire + 명명된 decision을 갖춘다. 남은 1개(project scope)는 handler-contract 경계로 해석되어 decision 미명시가 blocking 아님(O1).
4. **교차참조 정확**: Phase 2/4/5·gemma4-reuse·README가 flat-loop-gate 본문과 정확히 동기화됐고, 04의 결정 #9가 올바르게 해소 표기됐다.
5. **stale literal 잔존 없음**(O8). 동기화 문서(CHANGELOG/HANDOFF/work_log) 정확.
6. **비회귀**: `git diff --check` clean, 44/44 통과(코드 미변경, 보조 증거).
7. **프로세스 적합**: 작업자가 발견한 budget/usage 충돌을 임의 해결 없이 사용자 결정으로 이관(O10).

CLAUDE.md가 금지하는 "미추적 over-strict guard를 future risk로 재분류" 패턴에 해당하지 않는다 — 본 slice의 모든 boundary는 구현 slice 회귀 lock list로 명시돼 있고, O1/O2는 회귀 존재(구현 시점)를 전제로 한 informational이다.

## Outstanding items

- working tree: 9개 파일 modified, 미커밋(HEAD `08567d8`). 소유자 커밋 대기.
- budget slice는 **token budget 계측 정본 결정**(Gateway `usage` 필수화 vs 보수적 대체 계측)이 선행해야 진행 가능. 본 검증과 별개 과제. HANDOFF Next Task #1.
- O1(project scope 행 decision 명시)은 비차단 보강 후보.
- 구현 slice(Phase 4)에서 boundary matrix 6 경계의 양방향 회귀 추가 필요.

## Reproduction

저장소 루트에서:

```bash
git status --porcelain                                     # 9개 파일 modified(미커밋)
git log --oneline -1                                       # HEAD 08567d8
git diff HEAD --check                                      # whitespace 오류 0
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v   # Ran 44 tests, OK

# stale 예시 도구명 잔존 sweep(0건이 정상):
grep -rn "search_context\|resolve_memory" docs/ || echo "(잔존 없음)"

# tool registry slice diff 범위 확인:
git diff -- docs/plans/flat-loop-gate.md docs/plans/02-analysis-pipeline.md \
  docs/plans/04-agentic-search.md docs/plans/05-writing-ai.md docs/plans/gemma4-reuse.md \
  docs/plans/README.md CHANGELOG.md HANDOFF.md docs/daily_logs/2026-06-24/work_log.md
```

tool↔profile 양방향 일관성은 `flat-loop-gate.md` §v1 domain tool 표와 §task profile allowlist 표를 수동 대치로 검증한다(빈 칸 없음).
