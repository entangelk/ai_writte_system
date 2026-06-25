# 검증 기록 — System Contract SoT 초안 + A2 I2/I3 보강

## Subject metadata

- 일자: 2026-06-25
- 요청자: 사용자("다음작업 검증해줘. 계약 정본 SoT 만드는 작업이었어")
- 검증자: 독립 검증 AI(Claude Code)
- 대상 slice/artifact:
  - 1차: `docs/system-contract-sot.md` 초안(commit `c5202e8`) + `docs/README.md`·`docs/plans/README.md` 진입점 갱신
  - 2차: A2 registry I2/I3 비차단 권고 보강(commit `62bad96`, 직전 A2 검증의 후속)
- canonical spec reference(SoT가 인용·요약하는 정본들):
  - `docs/plans/flat-loop-gate.md`(§Budget 75–123, §Domain Tool Registry, §종료 decision literal, §세 Gate 직교 124–134)
  - `docs/plans/llm-gateway.md`(상태 `Proposed`), `docs/plans/02-analysis-pipeline.md`(Analysis Gate literal)
  - `docs/plans/00-foundations.md`(candidate literal), `docs/plans/implementation-plan.md`(배포 경계·slice 상태)
  - `services/llm_gateway/app/errors.py`(5 provider literal), `services/application/app/agent_loop/registry.py`·`budget.py`
- source of the work being verified: commit `c5202e8`(SoT) + `62bad96`(A2+I2/I3). `git status --short` clean. HEAD `c5202e8`.
- 구현 환경: Python 3.12.3.

## Scope

본 slice는 **문서(Draft SoT 인덱스)**가 주 대상이다. 문서 검증은 "green bar"가 아니라 (a) SoT가 인용·요약한 모든 literal·status·link가 정본과 일치하는지, (b) SoT가 정본을 overstate/축소하지 않는지, (c) SoT 자체 내부 일관성, (d) 새 canonical 층이 기존 precedence 문서와 충돌하지 않는지에 있다. 추가로 같은 커밋 묶음에 들어간 A2 I2/I3 보강(코드)도 확인한다. 점검 표면:

1. SoT contract — 문서 우선순위·문서 역할 표·시스템 경계·확정 전역 계약·서비스별 계약(Gateway/Loop)·Gate 합성·Phase 인덱스·구현 상태·미확정 목록
2. literal 교차 대조 — 5 provider literal, 5 Analysis Gate literal, 3 candidate literal, 7 Loop decision, 6 v1 tool, 3 allowlist, budget 차원/임계
3. status/링크 정합성 — 각 Phase 문서 status 주장(Proposed/Draft)과 파일 존재·상대링크 해소
4. 내부 일관성 — 미확정 목록 ↔ Phase 인덱스 미확정 노트, enum/bounds deferral 전파
5. precedence tree 자기 모순 — SoT precedence vs `plans/README.md` precedence
6. I2/I3 보강 — registry 재귀 등록 검증·`assert` 제거 + 2개 신규 회귀 lock
7. 비회귀 — 85/85

## Methodology

1. **SoT를 먼저 정독 후 claim 추출**: 모든 "확정된 계약"·literal·status·link를 lock list로 뽑고 정본에 대입.
2. **literal 문자열 단위 대조**: provider/Analysis/candidate/decision/tool literal을 코드·Phase 문서에서 grep해 SoT 인용과 정확히 일치하는지 확인.
3. **status 과장 점검**: SoT가 Draft/Proposed 문서를 Approved처럼 표현하거나 미구현을 확정처럼 표현하는지.
4. **링크 해소 + 파일 존재**: SoT가 링크하는 모든 Phase/verification 문서가 실제 존재하는지.
5. **precedence 자기 모순**: SoT precedence tree와 plans/README precedence tree를 항목 단위로 비교.
6. **I2/I3 보강 실증**: ad-hoc 스크립트로 중첩 object·array items 등록 차단·`assert` 0건·enum/bounds deferral 유지를 직접 확인.
7. **작업자 주장 재도출**: 85/85, 두 커밋, clean status를 검증자가 재실행.

정확한 명령은 Reproduction에 있다.

## Findings

### 1. literal 교차 대조 — 정본과 문자열 그대로 일치 (빈 칸 없음)

| SoT 인용 | 정본 근거 | 일치 |
|---|---|---|
| 5 provider literal(`provider_unavailable/timeout/overloaded/invalid_response/request_rejected`) | `errors.py:11-15` | ✓ |
| 5 Analysis Gate literal(`create/update/add_evidence/no_change/conflict`) | `02-analysis-pipeline.md:26,107` | ✓ |
| 3 candidate literal(`draft_candidate/analysis_candidate/context_candidate`) | `00-foundations.md:43-45`, `contracts.md:162-166` | ✓ |
| 7 Loop decision | `flat-loop-gate.md` §종료 decision, `decision.py` | ✓ |
| 6 v1 tool + 3 allowlist(analysis_compare 5 / context_search 3 / writing_generate 0) | `flat-loop-gate.md` §v1 tool, `registry.py:49-63` | ✓ |
| budget 차원 5종·임계(iter/wall/token ≥1, tool-using tool/repeated ≥1, writing 0) | `flat-loop-gate.md:89` | ✓ |
| token post-accounting(`==limit` 완료/`>limit` 초과)·retry budget 소비 | `flat-loop-gate.md:91,106` | ✓ |

SoT가 literal을 의역하거나 누락 없이 정본 그대로 인용. ✓

### 2. status/링크 정합성 — 과장 없음, 전부 해소

- `llm-gateway.md` = `Proposed`(SoT:30) ↔ 실제 header `Proposed` ✓
- `flat-loop-gate.md` = "Draft, 일부 구현 검증됨"(SoT:30) ↔ header `Draft`(A1/A2 구현검증 주석) ✓ (과장 아님)
- Phase 1~6·`00-foundations`·`product-shell`·`implementation-plan` = `Draft`(SoT:27-37) ↔ header 전부 `Draft` ✓
- `contracts.md` = "Reference only"(SoT:38) ↔ 구 status line 없음, `docs/README.md`가 아이디에이션/참고로 분류 ✓
- SoT가 링크하는 `plans/01-core-sot.md`~`06-review-ui.md`·`00-foundations.md`·verification 4건 전부 파일 존재·상대경로 해소 ✓

SoT가 미구현(A3, Phase 1~6)을 확정으로 표현하지 않고 "현재 구현 상태" 표(SoT:273-279)에 정확히 미구현 표시. ✓

### 3. enum/bounds deferral — 새 canonical 층에 정확히 전파 (직전 A2 검증 reconcile 유지)

SoT:177-178이 v1/A2 validator 범위를 `{required, type, additionalProperties:false, array items}`로 명시하고 enum/bounds를 "첫 사용 tool 등록 시 검증+회귀 추가, 그전까지 명시적 deferral"로 기록. `flat-loop-gate.md` §33 reconcile과 일치. 미확정 목록(SoT:296)에도 "enum/bounds를 쓰는 첫 tool schema 등록 시 validator 확장 방식"으로 추적됨. **SoT가 reconcile을 역추적하지 않고 "strict JSON Schema validation"으로 overstate하지 않음.** ✓

### 4. Gate 합성·직교 — 정본과 일치

SoT:186-206의 4-Gate 비합성·합성 순서·"completed but Gate rejected 가능"/"candidate needs_review but loop completed 가능"이 `flat-loop-gate.md` §세 Gate 직교(124-134)·completion criteria 계약과 일치. ✓

### 5. I2/I3 보강 — 폐쇄 확인 (코드, 62bad96)

직전 A2 검증의 비차단 권고가 코드+회귀로 닫혔다:
- **I2(중첩 object 등록-검증 비대칭) 폐쇄**: `_validate_schema_contract`(registry.py:173-210)가 object property와 array `items`를 재귀 검증. 실증 — non-strict 중첩 object·items 없는 array 모두 등록 시 `ToolBlocked`. 신규 회귀 `test_nested_object_schema_must_be_strict_at_registration`(test:122)·`test_array_schema_requires_items_at_registration`(test:137)가 양방향을 lock.
- **I3(`assert`의 `-O` 제거) 폐쇄**: `_validate_arguments`(registry.py:216-221)의 `assert`가 명시 `raise InvalidToolArguments`로 교체. 실증 — 모듈 내 `assert` 0건.
- **I1 deferral 유지**: enum/bounds schema는 여전히 등록 통과(validator가 요구/검사 안 함). 실증 확인.

registry 회귀 18→20, 전체 83→85. ✓

### 6. 비회귀 — 독자 재실행

- `python3 -m unittest discover -s tests` → **85/85 OK**(검증자 재실행)
- `git log --oneline -2` → `c5202e8`·`62bad96` ✓
- `git status --short` → clean(`.agents/.codex` 경고만, worker 주장과 일치) ✓

## Issues / Risks

### R1. [비차단, latent] SoT precedence tree vs `plans/README.md` precedence tree 항목 불일치

SoT(line 9-17)와 `plans/README.md`(충돌 시 우선순위)의 precedence tree가 항목 단위로 다르다:

- SoT: (2) Approved SoT + Approved Phase 계획 **동일 level**, (3) Draft-locked, (4) 미구현 Draft Phase 계획
- plans/README: (2) SoT에 반영된 확정 계약, (3) Approved Phase 계획, (4) Draft-locked — SoT-content와 Approved-phase-doc을 **분리 level**, 미구현 Draft plan에 대한 별도 level 없음

결정적 차이: Draft SoT의 확정 계약 vs Approved Phase 문서가 충돌할 때 결론이 양쪽에서 다를 수 있다(plans/README는 SoT-content 우세, SoT 해석은 Approved phase-doc 우세 가능). 현재 Approved 문서가 없어 **활성 모순은 아니**(latent).

- SoT가 line 7에서 자기 precedence를 권위로 선언하므로 엄격히는 SoT가 우세하지만, `plans/README.md`의 tree가 아직 reconcile 되지 않아 "단일 precedence 권위" 목표(사용자 결정, CHANGELOG:20)가 부분적으로 약화된다.
- 본 검증 방법론은 contract 자기 모순을 blocking으로 본다. 단, 본 SoT는 **명시적 `Draft`이자 소유자 승격 검토 대기**(HANDOFF Next Task 1) 상태이고 self-disclaim("현재 이 문서는 Draft다")하므로, R1은 Draft slice 자체를 block하지 않는다.
- **권고**: SoT를 `Approved`로 승격하는 검토 시점에 두 tree를 통일할 것. 승격 직후부터 Approved 문서가 생겨 분기가 활성화되므로, 그 전에 reconcile 해야 한다.

그 외 overstatement·누락·끊어진 링크·literal 불일치는 발견되지 않았다.

## Verdict

**합격(pass).**

적용 사유(load-bearing):
- SoT가 인용·요약한 모든 literal(5 provider·5 Analysis·3 candidate·7 decision·6 tool·3 allowlist·budget 임계)이 정본과 문자열 그대로 일치하고, status·링크·구현 상태 표가 과장 없이 정확하다(Findings 1-2).
- enum/bounds deferral(reconcile)이 새 canonical 층에 정확히 전파됐고, SoT가 이를 "strict JSON Schema"로 overstate하지 않는다(Findings 3).
- Gate 직교·합성 원칙이 정본과 일치한다(Findings 4).
- 직전 A2 검증의 비차단 권고 I2/I3가 코드+양방향 회귀로 완전 폐쇄됐고 I1 deferral은 유지됐다(Findings 5). 85/85 비회귀·clean status 재현.
- SoT는 세부 Phase 문서를 대체하지 않는 "정본 인덱스" 역할을 사용자 결정에 맞게 수행한다.

**비차단 risk R1**(precedence tree 불일치)은 소유자의 SoT 승격 검토 시점에 reconcile 해야 한다. Draft 상태에서는 self-disclaim과 "현재 Approved 문서 없음"으로 활성 모순이 아니므로 합격을 막지 않는다.

## Outstanding items

- **R1 reconcile(완료, 2026-06-25)**: `plans/README.md` precedence tree를 SoT와 통일함. 사후 보강 추적 섹션 참조.
- SoT `Draft`→`Approved` 승격 여부·범위 조정은 사용자 결정 대기(HANDOFF:40, Next Task 1).
- A3(completion/retry/loop 합성)·Phase 1~6 구현·enum/bounds 첫 사용 tool 등록 시 검증 확장은 후속.
- 본 검증 기록은 SoT 초안의 최초 독립 검증(HANDOFF:68 "아직 독립 검증 기록은 없음"을 대체).

## 사후 보강 추적 (post-verification)

2026-06-25 사용자 요청("비차단 부분 네가 보강해줘. 권고부분도 보강해주고")으로 검증자가 R1을 직접 reconcile 했다. 본 섹션은 원 독립 검증의 판정(합격)을 덮어쓰지 않고, 검증 이후 working tree 변경을 추적한다.

- **R1 폐쇄**: `docs/plans/README.md`의 "충돌 시 우선순위" tree를 SoT(`docs/system-contract-sot.md` §문서 우선순위)와 동일한 5-level로 통일하고, SoT를 정본 precedence로 defer 하는 문구를 추가. 분기하던 유일한 tree(구 level 2 "SoT 확정 계약" / level 3 "Approved Phase 계획" / level 4 "Draft-locked")를 SoT 기준(level 2 "Approved SoT+Phase 계획" / level 3 "Draft-locked" / level 4 "미구현 Draft")으로 정렬.
- **의미론 근거**: SoT tree가 더 타당하다 — 사용자가 서명한 `Approved` Phase 계획이 미서명 `Draft`-locked 구현 계약보다 우선이어야, 사용자가 지시한 변경이 기존 구현을 정상적으로 덮어쓴다. plans/README의 구 tree(impl-lock > approved-plan)는 이를 역전시켜 사용자 지시 변경을 막을 수 있었다.
- **DRY**: plans/README는 이제 SoT에 "상세와 최종 판정은 SoT에 있다"로 defer 하므로, 정본 tree는 SoT 한 곳만 유지된다.
- 비교 검증(`sed -n`): 양 tree level 2-5 동일, level 1은 외부 참조 적응("이 문서"→"SoT")만. repo sweep에서 문서-precedence tree는 SoT·plans/README 두 곳만(분기 후보 제거 완료).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# 1. 비회귀 + 커밋/상태 재확인
python3 -m unittest discover -s tests          # 85/85 기대
git log --oneline -2                           # c5202e8, 62bad96 기대
git status --short                             # clean 기대(.agents/.codex 경고만)

# 2. SoT literal 교차 대조 (정본과 일치 확인)
grep -n "provider_unavailable\|provider_request_rejected" services/llm_gateway/app/errors.py
grep -n "create\|add_evidence\|no_change\|conflict" docs/plans/02-analysis-pipeline.md | head -3
grep -n "draft_candidate\|analysis_candidate\|context_candidate" docs/plans/00-foundations.md
sed -n '9,17p' docs/system-contract-sot.md     # SoT precedence
sed -n '/충돌 시 우선순위/,/^## /p' docs/plans/README.md  # plans/README precedence (R1 비교)

# 3. I2/I3 보강 실증 (62bad96)
python3 - <<'PY'
from services.application.app.agent_loop.registry import (
    ToolEntry, TaskProfile, DomainToolName, ToolBlocked)
def mk(s): return ToolEntry(name=DomainToolName.SEARCH_MEMORY,
    description_by_profile={TaskProfile.CONTEXT_SEARCH:"x"}, argument_schema=s)
for label,s in [("non-strict nested object",{"type":"object","properties":{"f":{"type":"object"}},"required":["f"],"additionalProperties":False}),
                ("array w/o items",{"type":"object","properties":{"t":{"type":"array"}},"required":["t"],"additionalProperties":False})]:
    try: mk(s); print(label,"-> STILL ACCEPTED")
    except ToolBlocked: print(label,"-> blocked (ok)")
import inspect, services.application.app.agent_loop.registry as r
print("assert count:", inspect.getsource(r).count("assert "))   # 0 기대
PY
```
