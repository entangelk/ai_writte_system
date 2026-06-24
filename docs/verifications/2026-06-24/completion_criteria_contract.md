# 검증 기록: flat loop task별 completion criteria 계약

## Subject metadata

- **날짜**: 2026-06-24
- **요청자**: 소유자(entangelk) — "클로드 작업 AI가 작업한 분에 대해서 검증하고 의심해줘"
- **검증자**: Claude(독립 검증 세션)
- **대상 slice/artifact**: HANDOFF Next Task 1 "task별 completion criteria 확정(Analysis/Context/Writing)" 완료 보고. 산출물 = `docs/plans/flat-loop-gate.md` 신규 `## task별 completion criteria 계약` 섹션 + boundary matrix, 상태/범위/제외범위/착수결정 갱신, 그리고 README/HANDOFF/CHANGELOG/work_log 인덱스·상태 갱신.
- **canonical spec reference**: `docs/plans/flat-loop-gate.md`(working tree) — 특히 §목표와 범위, §세 Gate는 다른 층위(직교), §종료 decision literal, §boundary matrix, §task별 completion criteria 계약(신규), §Loop Gate 보강점 반영, §제외 범위, §착수 전 결정사항.
- **source of work**: working tree, uncommitted(5개 파일 modified, commit 전). HEAD = `a75531a feat: finalize flat loop safety contracts`. 본 변경은 커밋되지 않은 working tree 상태.

## Scope

검증 대상 surface(각각 아래 Findings에서 file:line 인용):

1. **신규 completion criteria 계약 본문** — `flat-loop-gate.md` §192~221(공통 하이브리드 판정, 완결된 산출 vs loop 미해결 구분, task profile별 기준 표 + bullets)
2. **completion boundary matrix** — `flat-loop-gate.md` §223~230(구현 slice 회귀 lock list)
3. **문서 갱신** — 상태(3), 범위(9), 제외 범위(248), 착수 전 결정사항(255)
4. **내부 일관성** — completion 섹션 ↔ 기존 §종료 decision literal(150~190) ↔ §세 Gate 직교(124~134) ↔ §보강점 반영(232~244)
5. **cross-reference 정확성** — `02-analysis-pipeline.md`(candidate status/5종 literal), `04-agentic-search.md`(ContextPackage/Context Gate), `05-writing-ai.md`(WritingCandidate/Writing Gate), `gemma4-reuse.md`(7 보강점)
6. **인덱스/상태 문서** — README(13번 항목), HANDOFF(Current Status/Active Decisions/Next Tasks), CHANGELOG(신규 entry + 결정 rationale), work_log(Completed/Decisions/Next steps)
7. **링크 정합성** — 내부 anchor `#종료-decision-literal`(203)

**범위 밖**: 코드 구현(없음). `AgentLoopRunner` decision enum 및 양방향 회귀는 명시적으로 Phase 4 구현 slice에서 도입(`flat-loop-gate.md:264`). 따라서 본 검증은 **구현 slice 이전의 lock list 정의 단계**에 대한 것이며, "빈 셀 없는 양방향 회귀 테스트 매핑"이 아닌 "이 lock list가 빈 셀 없이, 모순 없이, 구현 slice에서 회귀로 변환 가능할 만큼 완결되었는가"를 기준으로 한다.

## Methodology

모든 claim은 primary source에서 재도출. 워커의 work_log/HANDOFF 주장을 전제하지 않음. 사용 명령:

- `git status && git diff --stat` — 변경 파일 범위 확인(5개 파일, 문서 한정)
- `git diff -- docs/plans/flat-loop-gate.md` — 신규 섹션 + 갱신 라인 정확 추출
- `Read docs/plans/flat-loop-gate.md` (전체 272행) — canonical contract 전체 맥락 확보, 기존 decision literal 섹션과 신규 completion 섹션의 교차 판독
- `git diff -- HANDOFF.md CHANGELOG.md docs/plans/README.md` — 인덱스/상태/결정 기록 정합성
- `git diff -- docs/daily_logs/2026-06-24/work_log.md` — 워커 보고 대 실제 변경 교차검증
- `grep -n "needs_review\|create\|...\|conflict" docs/plans/02-analysis-pipeline.md` — candidate status/literal 실제 정의 확인
- `grep -n "ContextPackage\|pointer\|budget\|SOT\|stale\|Context Gate" docs/plans/04-agentic-search.md` — ContextPackage 구조 및 preflight/Gate 비대체 원칙 확인
- `grep -n "WritingCandidate\|Writing Gate\|모호\|충돌" docs/plans/05-writing-ai.md` — WritingCandidate 정의 확인
- `sed -n '79,95p' docs/plans/gemma4-reuse.md` — "7개 보강점" 실제 행수 계수
- `sed -n '184p;194p;229p' docs/plans/flat-loop-gate.md` — context_search over-strict guard의 decision-level vs task-level matrix 커버리지 비교
- `ls` / config grep — repo markdown lint/format 도구 존재 여부(결과: 없음 → formatting 검증은 git diff 정합성으로 대체)

## Findings

### 1. 신규 completion criteria 계약 본문(§192~221)

- 하이브리드 판정이 두 조건의 AND로 정의됨(`flat-loop-gate.md:198-201`): (1) 구조 조건 = 목표 산출물이 정의된 형태로 존재, (2) 자율 조건 = 모델이 미해결 분기·추가 진행 필요를 self-report하지 않음. 산출물 있으나 조건 미달 = `awaiting_review`(203).
- "완결된 산출 vs loop 미해결" 핵심 구분 명문화(205-209): 개별 항목 불확실성을 산출물 안에 명시(candidate `needs_review` status, confidence, `conflict` 후보)하면 완결된 산출 → `completed`; 산출물 자체 도출 미해결 self-report → `awaiting_review`.
- task profile별 기준 표(213-217): `analysis_compare`(모든 대상 후보화 → completed, 개별 모호는 candidate status), `context_search`(의도 충족 package 후보 빌드 → completed), `writing_generate`(candidate 생성 → completed, 산출물 모호·충돌 self-report → awaiting_review). bullets(219-221)이 표를 보충.
- 워커 보고의 3가지 결정(A 하이브리드 / B analysis_compare 부분 모호 = run completed + candidate status / C writing_generate 모호 self-report = awaiting_review)이 각각 `flat-loop-gate.md:198-201`, `:219`, `:221`에 정확히 반영됨. **워커 보고는 사실**.

### 2. completion boundary matrix(§223~230)

- `analysis_compare`: completed should-fire(227) + awaiting_review should-fire(228, 별도 행) + 부분 모호 비승격 should-NOT-fire(227) + 개별 모호 승격 금지 should-NOT-fire(228). 4개 분기 모두 명시.
- `context_search`: completed should-fire(229). preflight 성공만으로 completed 아님(under-strict guard), 근거 부족 self-report = awaiting_review(229 should-NOT-fire 칸).
- `writing_generate`: completed should-fire(230). 모호·충돌 self-report = completed 아님(under-strict guard), Gate reject여도 completed(over-strict guard)(230).
- **비대칭 발견**: `analysis_compare`/`writing_generate` 행엔 over-strict guard("Gate reject여도 completed")가 있으나 **`context_search` 행(229)엔 없음**. 단, decision-level matrix `:184`(task 무관 "domain Gate 통과 불필요, over-strict guard")과 공통 prose `:194`("completed but Gate rejected 가능")로 잠겨 있어 hard gap은 아님. — Issues/Risks R1 참조.

### 3. 문서 갱신(상태/범위/제외/착수결정)

- 상태(3): "completion criteria slice는 2026-06-24 소유자 확정. 숫자 기본 한도는 후속" — 정확.
- 범위(9): "task별로 언제 completed로 종료하는지를 정의하는 계약을 확정한다. 숫자 기본 한도는 후속 slice" — 신규 범위 반영.
- 제외 범위(246-249): 기존 "completion criteria 계약" 항목이 **삭제됨** — scope 축소 정확. 숫자 기본 한도·저장 정책만 남음.
- 착수 전 결정사항(255): "task별 completion criteria 확정: 하이브리드 판정, 완결된 산출 vs loop 미해결 구분(2026-06-24 소유자 확정)" — `[x]` 전환 정확.
- 총 7개 결정사항(253-259) 중 completion 항목만 체크 전환, 다른 6개는 미변경. surgical.

### 4. 내부 일관성(계약 자체 교차검사)

- `completed` 정의(150-152) "loop 종료 상태만 의미, Gate 통과 무관" ↔ completion criteria(194) "domain Gate와 직교, completed but Gate rejected 가능" — **일관**.
- `awaiting_review` 정의(155-156) "자율 완료 기준 미달" ↔ completion 하이브리드(198-203) 자율 조건(self-report) — "자율 완료 기준"이 새 섹션에서 구체화됨. **일관**.
- blocked/budget_exhausted/error 3종을 completion task matrix가 아닌 decision-level matrix(186-190)에 위임. 이 구조는 `:203` "이 우선순위는 종료 decision literal의 상호 배타성을 따른다"로 정당화됨. **일관**(task 무반복 공통 decision은 task matrix에서 중복 정의하지 않는 설계).
- 보강점 표(243) "answer 존재 = 완료 → 완료 기준 미충족 시 completed가 아닌 awaiting_review" ↔ 신규 completion criteria — **일관**. 신규 섹션이 이 보강점의 구체화.
- 7개 보강점 count(`gemma4-reuse.md:85-91` 실제 7행, `flat-loop-gate.md:234` "7개") — **정확**. grep이 1행(`잘못된 tool arguments JSON`)을 놓쳤으나 `sed`로 7행 확인.
- **내부 모순 미발견**. 계약은 자기일관적임.

### 5. cross-reference 정확성

- `02-analysis-pipeline.md:20,41` candidate status `needs_review` 정의, `:26,97,98,107` 5종 literal(`create`/`update`/`add_evidence`/`no_change`/`conflict`) 정의 — completion 표(215) 인용과 **정확히 일치**.
- `04-agentic-search.md:9,50,54,58,63-71` ContextPackage 구조(pointer/budget/SOT/stale/Context Gate) 정의, `:34` "validate_context는 loop 중 preflight이며 종료 후 Context Gate 검사를 대체하지 않는다" — completion criteria `:220`(validate_context preflight는 신호일 뿐 Context Gate 대체 아님)과 **일관**.
- `05-writing-ai.md:16,33` WritingCandidate 정의, `:9,34` 충돌 검사 + Writing Gate decision("review" 포함) — completion criteria `:221`(candidate 메타로 모호·충돌 전달, loop 후 Writing Gate 판정)과 **양립**.
- `gemma4-reuse.md:79-91` 7 보강점 — `flat-loop-gate.md:234,268` "7개 보강점" **정확**.

### 6. 인덱스/상태 문서

- README 13번(`docs/plans/README.md`): "...tool registry, budget policy, **task별 completion criteria** 계약(숫자 기본 한도는 후속 slice)" — 인덱스 갱신 정확.
- HANDOFF Current Status(`HANDOFF.md:14`): "...tool registry, budget policy, task별 completion criteria 계약이 확정됐다. 숫자 기본 한도만 후속" — 정확.
- HANDOFF Active Decisions(`HANDOFF.md:37`): completion 하이브리드 + analysis_compare 부분 모호 + writing_generate self-report 요약 — 워커 결정 3종과 일치.
- HANDOFF Next Tasks: 기존 Task 1(completion criteria)이 완료되어 제거, Task 2/3이 1/2로 재번호화(benchmark 한도, Phase 4 구현 slice 회귀) — 정확, work_log Next steps와 **일치**.
- CHANGELOG: 신규 entry("flat loop task별 completion criteria 확정...") + 결정 rationale(하이브리드 판정, 직교 모델 선택) — 워커 결정을 반영. CLAUDE.md "User Decisions and Rationale" 규칙 준수.
- work_log: Completed section 신규 subsection, Decisions section (A)/(B)/(C) 결정 기록, Next steps 재번호화 — HANDOFF/flat-loop-gate와 **일치**.

### 7. 링크 정합성

- 내부 anchor `[#종료-decision-literal](#종료-decision-literal)`(`flat-loop-gate.md:203`) → 대상 헤더 `## 종료 decision literal`(`:136`). GitHub anchor 규칙(소문자화, 공백→하이픈, 한국어 유지)으로 "종료 decision literal" → "종료-decision-literal". **정합**.
- README 인덱스 → `flat-loop-gate.md` 링크 유지. cross-reference 4종(`gemma4-reuse.md`, `02/04/05-*.md`, `implementation-plan.md`, `llm-gateway.md`) — 모두 존재 확인(`ls docs/plans/`).

## Issues / Risks

> 비차단(non-blocking)이지만 구현 slice(Task 2) 착수 전 명확화 권장. 본 slice는 "판정 기준 정의" 범위이므로 blocking defect는 아님.

- **R1 — completion matrix context_search over-strict guard 누락(비대칭)**: `flat-loop-gate.md:229` context_search 행의 should-NOT-fire 칸에 "Gate reject여도 completed" over-strict guard가 없음. `analysis_compare`(:227), `writing_generate`(:230)에는 있음. decision-level matrix `:184`와 공통 prose `:194`로 분기 자체는 잠겨 **hard gap은 아님**. 그러나 task별 matrix의 대칭성 위반으로, 구현자가 context_search의 over-strict 회귀("Context Gate reject여도 run은 completed") 케이스를 task-level 테스트로 빠뜨릴 위험. 권장: 구현 slice에서 context_search 행에 over-strict guard 행 추가, 또는 matrix를 task×decision 횡일관 구조로 재정렬.

- **R2 — completion matrix awaiting_review should-fire 행 비대칭**: `analysis_compare`는 completed should-fire 행(227)과 awaiting_review should-fire 행(228)을 분리했으나, `context_search`/`writing_generate`는 completed 행의 should-NOT-fire 칸에 awaiting_review 사례를 섞음(229, 230). 분기 자체는 prose(`:216-217, 221`)로 잠겨 빈 셀은 아니나, 행 구조 비대칭 → 구현자의 회귀 매핑 누락 위험(R1과 동일 계열). 권장: 구현 slice에서 세 profile을 동일 행 구조(completed 행 + awaiting_review 행 분리)로 통일.

- **R3 — "self-report" 기계적 정의 부재(contract gap candidate)**: 자율 조건의 "self-report"(`:201`)가 `analysis_compare`의 candidate `needs_review`(= self-report **아님**, `:207`)와 `writing_generate`의 candidate 메타 모호 + loop 보고(= self-report, `:221`)를 구분하는 판단 기준이, **모델 출력에서 구체적으로 무엇인지 명시되지 않음**. 계약은 의도를 서술했고 자기모순은 아님(analysis_compare는 다수 대상의 부분 불확실, writing_generate는 단일 산출물 전체 불확실이라는 차이를 prose가 암시). 그러나 "self-report 감지 신호"(loop decision 필드, 별도 status, 특정 토큰 등)가 정의되지 않으면 구현자가 두 케이스를 구분하는 기계적 규칙을 임의로 정하게 됨. 이 slice의 범위(판정 기준)는 충족하나, Phase 4 구현 slice에서 "self-report 감지 계약"이 completion criteria 또는 별도 섹션에 선행 정의되어야 함. **Spec-silent-on-mechanism** — CLAUDE.md "Spec-silent-but-code-enforced"의 역방향 변형(계약은 의도만, 구현이 기준을 정해야 하는 갭).

- **R4(정보)**: repo에 markdown lint/format 도구 없음(`.github/`, Makefile, markdownlint/prettier 설정 부재). 본 변경의 formatting 검증은 git diff 정합성 + anchor/링크 수동 확인으로 대체함. CI formatting gate가 없으므로 이는 검증 한계가 아닌 repo 현 상태 반영.

## Verdict

**조건부 합격(conditional pass)**.

하중 이유(load-bearing reasons):
- **합격 요소**: 워커 보고(3가지 결정, 변경 파일 범위)가 사실이고 정확히 반영됨(Findings 1, 6). 계약은 자기일관적이고 내부 모순 없음(Findings 4). cross-reference 4종이 모두 실제 정의와 일치(Findings 5). 인덱스/상태/결정 기록이 surgical하게 갱신되고 상호 일치(Findings 3, 6). anchor 링크 정합(Findings 7).
- **조건(구현 slice 착수 전 명확화 필요)**: completion boundary matrix의 task별 행 비대칭(R1: context_search over-strict guard 누락, R2: awaiting_review should-fire 행 비대칭)과 "self-report" 기계적 정의 부재(R3). 이 계약이 Phase 4 구현 slice에서 CLAUDE.md "boundary matrix has no empty cells" 기준을 만족하는 양방향 회귀 lock list로 변환되려면, 구현 slice 착수 전에 (a) completion matrix를 task×decision 횡일관 구조로 재정렬하거나 context_search over-strict guard 행을 추가, (b) "self-report 감지 신호" 정의를 completion criteria 또는 구현 slice 계약에 추가해야 함.
- **불합격 사유 아님인 이유**: R1/R2는 분기 자체가 decision-level matrix + 공통 prose로 잠겨 있어 "빈 셀"(trace 불가능한 분기)이 아님. R3는 모순이 아닌 정의 미세화 갭이며, 본 slice의 명시적 범위("판정 기준 정의")는 충족함. 따라서 blocking defect(계약 자체의 내부 불일치, trace 불가능한 분기)는 없음.

## Outstanding items

- **미커밋 변경**: 5개 파일이 working tree에 modified 상태(`git status`). 소유자의 커밋 승인 대기. 본 검증은 커밋 전 working tree 기준.
- **게시 승인**: 해당 없음(문서 한정 변경, 외부 게시 아님).
- **downstream unblock**: 본 criteria 완료로 HANDOFF Next Task 2(Phase 4 구현 slice 회귀 구현)의 선행 조건 충족. 단, 구현 slice 착수 시 R1/R2/R3 명확화가 선행 권장됨 — 이는 구현 slice의 scope이므로 본 completion slice를 되돌릴 필요 없음.
- **Gemma Q4 benchmark**(구 Next Task 2 → 现 Next Task 1): hardware 미확정으로 여전히 blocking. 본 검증과 무관.

## Reproduction

```bash
# 1. 변경 범위 확인
git status && git diff --stat

# 2. canonical contract 신규 섹션 + 갱신 추출
git diff -- docs/plans/flat-loop-gate.md

# 3. 전체 계약 맥락(기존 decision literal 섹션과 교차 판독)
# Read docs/plans/flat-loop-gate.md (full)

# 4. 인덱스/상태 문서 정합성
git diff -- HANDOFF.md CHANGELOG.md docs/plans/README.md
git diff -- docs/daily_logs/2026-06-24/work_log.md

# 5. cross-reference 실제 정의 확인
grep -n "needs_review\|create\|update\|add_evidence\|no_change\|conflict" docs/plans/02-analysis-pipeline.md
grep -n "ContextPackage\|pointer\|budget\|SOT\|stale\|Context Gate" docs/plans/04-agentic-search.md
grep -n "WritingCandidate\|Writing Gate\|모호\|충돌" docs/plans/05-writing-ai.md
sed -n '79,95p' docs/plans/gemma4-reuse.md   # 7 보강점 행수 계수

# 6. over-strict guard 비대칭 확인(R1)
sed -n '184p;194p;227p;229p;230p' docs/plans/flat-loop-gate.md

# 7. repo lint/format 도구 부재 확인(R4)
ls .github/ Makefile pyproject.toml package.json 2>/dev/null
grep -rl "markdownlint\|prettier\|mdformat" . --include="*.json" --include="*.yaml" --include="*.toml" 2>/dev/null
```
