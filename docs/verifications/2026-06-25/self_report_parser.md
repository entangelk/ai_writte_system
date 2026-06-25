# 검증 기록 — self-report 종료채널 parser slice

## Subject metadata

- 날짜: 2026-06-25
- 요청자: 소유자("클로드 작업 AI가 작업한 분에 대해서 검증하고 의심해줄래?")
- 검증자: 독립 검증 세션(Claude Code)
- 검증 대상 slice/artifact: `services/application/app/agent_loop/parser.py`(신규), `tests/test_agent_loop_parser.py`(신규), `services/application/app/agent_loop/completion.py`(docstring 갱신)
- 정본 계약 참조:
  - `docs/plans/flat-loop-gate.md` §"완결된 산출 vs loop 미해결의 구분(핵심)"(line 205-211) — 정본 규칙
  - `docs/plans/implementation-plan.md` §AgentLoopRunner line 149-150 — 계약 mirror + line 141 changelog 진행 行
  - `docs/system-contract-sot.md` §AgentLoopRunner line 149-150 — 계약 mirror
- 검증 대상 작업 출처: working tree, uncommitted(git status: `?? parser.py`, `?? test_agent_loop_parser.py`, `M completion.py` + 계약/HANDOFF/work_log 4건 modified). HEAD = `5572e95`.

## Scope

본 검증은 parser slice 1건만 대상으로 하며, 아래 표면을 하나의 묶음으로 검증한다.

1. **계약 본문(self-consistency)**: flat-loop-gate §211 ↔ implementation-plan §149-150/§141 ↔ system-contract-sot §149-150 의 리터럴·경계 일치.
2. **구현 코드**: `parser.py`(`parse_self_report_payload`, `_parse_json_object`, `InvalidSelfReport`, `_SELF_REPORT_FIELD`).
3. **의존 리터럴**: `completion.py`의 `SelfReport`(FINALIZE/DEFER), `decision.py`의 `LoopDecision.PROVIDER_ERROR`.
4. **회귀 테스트**: `test_agent_loop_parser.py`(양방향 guard, parametrized 경계값, public surface 주장).
5. **패턴 sweep**: `self_report` / `parse_self_report_payload` 전-repo 중복·default/fallback/nested-field 오인 경로.
6. **예외→decision uniform 매핑 일관성**: `InvalidSelfReport.decision` 와 타 agent_loop 예외들의 `.decision` 패턴.
7. **계약/HANDOFF/work_log 갱신**: worker가 "갱신했다"고 한 6개 문서의 실제 반영.
8. **테스트 직접 재실행**: worker 보고 14개/129개 통과 주장의 독립 재현.

## Methodology

계약을 먼저 스코프하고(본문 끝까지 읽기, 빈 칸 없이 boundary matrix 구축), 그 뒤 코드·테스트를 매트릭스 셀에 1:1 매핑했다. "코드가 돌아가는가"가 아니라 "코드가 계약을 고정하는가"를 감사한다.

사용한 명령(모두 repo root `/mnt/d/devel/에베베/ai_writte_system` 기준):

- focused 회귀: `python3 -m unittest tests.test_agent_loop_parser tests.test_agent_loop_completion -v`
- 전체 회귀: `python3 -m unittest discover -s tests -p 'test_*.py'`
- 패턴 sweep: `grep -rn "self_report" --include="*.py" services tests`
- 정의 단일성: `grep -rn "parse_self_report" --include="*.py"` (전 repo)
- 예외-decision 패턴: `grep -rn "decision = LoopDecision\|class Invalid" --include="*.py" services/application/app/agent_loop`
- 변경분 확인: `git diff -- services/application/app/agent_loop/completion.py`
- 리터럴은 직접 Read로 행 단위 교차(`parser.py`, `completion.py`, `decision.py`, 계약 3문서, `budget.py`, `registry.py`).

## Findings

### F1. 계약 자기일관성 — PASS

세 정본 위치의 종료채널 wire 계약이 문자열 그대로 일치한다(모두 `top-level self_report` / `정확히 finalize 또는 defer` / `누락·오타·대소문자 변형·non-string·산출물 내부 nested self_report → provider output 오류`).

- `flat-loop-gate.md:211` — 정본 규칙. "허용값은 정확히 `finalize` 또는 `defer`뿐이다. 누락·오타·대소문자 변형·non-string·산출물 내부 nested `self_report`는 종료 채널로 인정하지 않고 provider output 오류로 처리한다."
- `implementation-plan.md:149-150` — mirror, 동일 문구.
- `implementation-plan.md:141` — changelog 진행 行: parser slice가 `finalize`/`defer` literal만 인정하고 누락·malformed JSON·non-object·non-string·case variant·artifact nested는 `provider_error`로 분류한다. 본문(§150)과 충돌 없이 `malformed JSON·non-object`를 명시적으로 보태는 합치적 확장.
- `system-contract-sot.md:149-150` — mirror, 동일 문구.

내부 모순(규칙 ↔ policy ↔ changelog ↔ matrix) 없음. **계약 자기일관성 blocking 위반 0건.**

### F2. boundary matrix(spec → code → test 매핑) — 빈 칸 없음(단, R1 value-level 비고 1건)

스코프된 계약에서 추출한 분기별 매핑. 모든 should-fire / should-NOT-fire 분기가 명명된 회귀에 대응한다.

| # | 계약 분기(§211 / §150) | code 경로 | 회귀 테스트 | lock |
|---|---|---|---|---|
| 1 | top-level `finalize` → FINALIZE | `parser.py:42` `SelfReport(raw)` | `test_top_level_finalize_parses` | ✓ |
| 2 | top-level `defer` → DEFER | `parser.py:42` | `test_top_level_defer_parses` | ✓ |
| 3 | 누락(missing) → 거부 | `parser.py:37-39`(`get`→None→`not isinstance(str)`) | `test_missing_self_report_is_not_defaulted_to_finalize` | ✓ |
| 4 | 오타(wrong well-formed value) → 거부 | `parser.py:43-46`(`except ValueError`) | (전용 sample 없음; #5와 동일 분기) | ⚠ R1 |
| 5 | 대소문자 변형 → 거부 | `parser.py:43-46` | `test_case_variants_are_not_coerced`(`"Finalize"`) | ✓ |
| 6 | non-string 값 → 거부 | `parser.py:38-39` | `test_non_string_self_report_is_invalid`(`true`,`null`) | ✓ |
| 7 | malformed JSON → 거부 | `parser.py:52-53`(`JSONDecodeError`) | `test_non_json_or_non_object_content`(`"not-json"`) | ✓ |
| 8 | non-object JSON → 거부 | `parser.py:55-56`(`not isinstance(payload, dict)`) | `test_non_json_or_non_object_content`(`"[]"`) | ✓ |
| 9 | artifact 내부 nested self_report → 거부 | `parser.py:37-39`(top-level `get`→None) | `test_artifact_nested_self_report_is_not_termination_channel` | ✓ |
| 분류 | 거부 = provider_error | `parser.py:25` `decision = LoopDecision.PROVIDER_ERROR` | `test_invalid_self_report_classifies_as_provider_error` | ✓ |

- should-fire over-strict guard 존재: `test_top_level_finalize_parses`(`parser.py:25-29` 참조) 입력이 `{"self_report":"finalize","artifact":{"status":"needs_review"}}`로, 종료채널과 **산출물 데이터 채널 필드가 공존**해도 파싱이 성공함을 고정. 이는 §211 직교 원칙(데이터 채널 필드가 종료채널을 깨지 않음)을 직접 잠근다. over-strict(추가 필드 존재 시 거부) 변이가 들어가면 이 test가 FAIL.
- should-NOT-fire under-strict guard 존재: 각 거부 test는 `assertRaises(InvalidSelfReport)`. 해당 분기의 거부 로직을 제거/default-화하면 예외가 나지 않아 FAIL.
- 모든 주장이 public surface(`parse_self_report_payload` 반환값, `InvalidSelfReport` 발화, `.decision` class attr)를 겨냥. 내부 helper(`_SELF_REPORT_FIELD`, `_parse_json_object`)에 결합되지 않음.

### F3. spec ↔ implementation 리터럴 일치 — PASS

- `_SELF_REPORT_FIELD = "self_report"`(`parser.py:19`) = 계약 `self_report`. ✓
- `SelfReport.FINALIZE = "finalize"`, `SelfReport.DEFER = "defer"`(`completion.py:38-39`) = 계약 허용값. ✓
- `InvalidSelfReport.decision = LoopDecision.PROVIDER_ERROR`(`parser.py:25`), `LoopDecision.PROVIDER_ERROR = "provider_error"`(`decision.py:22`) = 계약 "provider output 오류". ✓
- top-level-only: top-level `payload.get(_SELF_REPORT_FIELD)`(`parser.py:37`)만 조회. nested는 도달 불가 → 거부. 계약 "산출물 내부 nested self_report는 종료 채널이 아니다" 일치. ✓
- case-sensitive: `SelfReport(raw)`(`parser.py:42`)는 StrEnum value lookup으로 대소문자 구분. `"Finalize"`/`"FINALIZE"`/`"finalize "` 모두 no-match → `ValueError` → 거부. 계약 "대소문자 변형 … provider output 오류" 일치. ✓
- paraphrase 없음. 모든 리터럴이 계약 본문과 변경 없이 일치.

### F4. 회귀 테스트 직접 재실행 — PASS(worker 주장과 정확 일치)

- `python3 -m unittest tests.test_agent_loop_parser tests.test_agent_loop_completion -v` → **Ran 14 tests ... OK**. worker 보고 14개와 일치.
- `python3 -m unittest discover -s tests -p 'test_*.py'` → **Ran 129 tests ... OK**. worker 보고 129개와 일치.
- worker가 보고한 숫자가 미검증 상태였으나 독립 재현으로 확인됨.

### F5. 패턴 sweep — PASS(worker 주장 확인)

- `grep -rn "self_report" --include="*.py" services tests` 결과: `completion.py`, `parser.py`, `test_agent_loop_parser.py`, `test_agent_loop_completion.py` 4파일에만 존재. `runner`(미구현)/`resolution`/`registry`/`budget`/`decision`에 잔류 없음.
- `grep -rn "parse_self_report"` 전 repo: 정의는 `parser.py:28` 단일. 참조는 테스트 파일만. **중복 parser 없음, default/fallback/nested-field 오인 경로 없음.**
- worker의 "패턴 sweep 결과 기존 코드에 default/fallback/nested-field 오인 경로는 없었다" 주장이 독립 재확인됨.

### F6. 예외→decision uniform 매핑 일관성 — PASS

`InvalidSelfReport.decision = LoopDecision.PROVIDER_ERROR`(`parser.py:25`)가 agent_loop 패키지의 기존 패턴과 일치한다:

- `InvalidProviderUsage.decision = LoopDecision.PROVIDER_ERROR`(`budget.py:48`) — provider 출력(usage) 오류 → provider_error.
- `InvalidBudgetPolicy.decision = LoopDecision.BLOCKED`(`budget.py:36`).
- `ToolRegistryError.decision = LoopDecision.BLOCKED` / `InvalidToolArguments.decision = LoopDecision.INVALID_TOOL_ARGUMENTS`(`registry.py:75,81`).

parser가 "provider 출력 오류"를 `provider_error`로 매핑하는 것은 `InvalidProviderUsage`와 동일 분류이며 HANDOFF의 I3 uniform 매핑 방향과 충돌 없음. ✓

### F7. completion.py 변경분 — PASS(docstring-only, 동작 변경 없음)

`git diff` 결과 `completion.py`는 docstring 3행만 변경. 구 "The concrete wire format of the self-report signal (explicit token, structured field, ...) is fixed in the provider-response parser slice" → 신 "The wire format is fixed in parser.py as a provider JSON object with a top-level ``self_report`` field". `judge_completion` 본문·`SelfReport` enum 무변경. wire 형식이 구체 확정된 시점의 합당한 cross-reference 갱신이며, 변경 line이 모두 parser slice로 추적됨(surgical).

### F8. 문서 갱신 반영 — PASS

- `HANDOFF.md:42`(Active Decisions), `:75`(Verification), `:117`/`:131`(Project Structure)에 parser slice 반영. ✓
- `docs/daily_logs/2026-06-25/work_log.md:10`(Goals), `:53-60`(Completed work)에 parser slice 기록. ✓
- flat-loop-gate / implementation-plan / system-contract-sot 3계약문 모두 §위 참조 위치에 확정 wire 계약 반영(F1 확인). ✓

## Issues / Risks

- **R1(비차단, value-level fidelity)**: 계약 §211이 거부 카테고리로 "오타"를 "대소문자 변형"과 별개로 열거하지만, 잘 형성된 잘못된 리터럴(예 `"done"`, `"completed"`, `"finalise"`)의 전용 sample이 `test_agent_loop_parser.py`에 없다. 단, "오타"와 "대소문자 변형"은 **동일 code 분기**(`parser.py:43-46`의 `except ValueError`)를 공유하며, case-variant test가 이 분기를 이미 잠그고 있으므로 오타도 동일 기구로 거부된다. 즉 **branch-level 빈 칸이 아니라 value-sample 비고**다. blocking 아님. 권고: `test_case_variants_are_not_coerced`에 parametrized sample 1건(예 `"done"`)을 보태어 계약 열거값 수준에서 매트릭스를 완전히 채울 것.
- **R2(비차단, 인지용)**: 9개 거부 test는 모두 `assertRaises(InvalidSelfReport)`만 검사하고, 발화된 인스턴스의 `.decision == PROVIDER_ERROR`를 개별 검증하지 않는다. `.decision`이 class attr(`parser.py:25`)이므로 `test_invalid_self_report_classifies_as_provider_error`의 class-level 검증으로 충분하며 DRY하게 설계된 것. action 불필요, 인지 차원 기록.
- **spec-silent-but-code-enforced gap**: 없음. 코드가 계약에 없는 것을 추가로 거부/허용하지 않는다(추가 top-level 필드 존재를 허용하며, 이는 §211 직교 원칙과 일치). contract amendment 요청 사유 없음.

## Verdict

**합격(Pass).**

이유(pan-bearing):
1. 계약 자기일관성 blocking 위반 0건(F1).
2. boundary matrix의 모든 분기가 명명된 회귀에 매핑되며, branch-level 빈 칸 없음(F2). "오타"의 value-sample 부재(R1)는 동일 분기가 이미 lock된 비차단 비고.
3. spec ↔ code 리터럴이 행 단위로 일치(paraphrase 없음, F3).
4. 테스트 14/129 통과가 독립 재현됨(F4). 양방향 guard 존재.
5. 패턴 sweep에서 중복/default/fallback/nested 오인 경로 없음(F5).
6. 예외→decision uniform 매핑이 기존 패턴과 일치(F6).
7. completion.py 변경은 docstring-only(F7), 문서 갱신 6건 반영 확인(F8).

R1은 권고일 뿐 verdict에 영향을 주지 않는다 — lock이 비어있지 않기 때문.

## Outstanding items

- 본 slice는 parser만 소유하며 **runner 연결은 미구현**(HANDOFF.md:42, work_log.md:59 명시). worker가 "다음 작업"으로 언급한 `parse_self_report_payload`의 provider 응답 흐름 연결 + I2 forward-lock 회귀는 본 검증 범위 밖 forward 작업이다.
- 검증 대상은 working tree(uncommitted). parser.py / test 파일은 untracked이므로 커밋 전 까지 본 기록의 Reproduction이 가리키는 상태는 working tree이다.
- R1 권고(오타 sample 1건 추가)를 소유자가 수용할 경우, 본 기록 verdict는 합격을 유지하되 F2 매트릭스 #4 셀을 value-sample까지 채운 것으로 회신 갱신 가능.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# focused 회귀(worker 보고 14개)
python3 -m unittest tests.test_agent_loop_parser tests.test_agent_loop_completion -v

# 전체 회귀(worker 보고 129개)
python3 -m unittest discover -s tests -p 'test_*.py'

# 패턴 sweep(self_report 잔류 = completion/parser + 2 test 파일만)
grep -rn "self_report" --include="*.py" services tests

# 정의 단일성(parse_self_report_payload = parser.py:28 단일)
grep -rn "parse_self_report" --include="*.py" .

# 예외→decision uniform 매핑 일관성
grep -rn "decision = LoopDecision\|class Invalid" --include="*.py" services/application/app/agent_loop

# completion.py 변경분(docstring-only)
git diff -- services/application/app/agent_loop/completion.py
```
