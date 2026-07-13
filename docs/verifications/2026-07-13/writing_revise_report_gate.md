# 독립 검증 — Phase 5.7 G3 B partial revise→report→Gate 합성 (SoT v1.6.75)

## Subject metadata

- **Date**: 2026-07-13
- **Requester**: 오너("G3 B 구현을 완료했습니다. R5는 확장 비용을 확인한 뒤 A first→C later로 확정했습니다. … /writing/revise-and-gate가 revise → report 최신화 → Gate 순서로 실행 … 검증하고 의심하고 또 의심해줄래?").
- **Verifier**: 독립 세션(검증자). 구현자 클레임을 반박 가설로 취급 — green bar와 무관하게 계약 경계를 깨보려 시도. 기본 태도 "맞아 보여도 깨뜨려 본 뒤 못 깨서 받아들인다".
- **Target slice**: Phase 5.7 G3 B — `services/application/app/writing/revise_gate.py`(`CandidateReporter` Protocol·`WritingReviseReportFailure`·`run()` 3단계화·gate/return 인자 `revised`→`enriched`), `services/application/app/main.py`(`WritingReviseReportFailure` import·wiring `reporter=writing_report`·`except WritingReviseReportFailure` JSONResponse), `tests/test_writing_revise.py`(`_Reporter` 더블·`WritingReviseGateApiTest` G3 B 회귀 +보강). 문서: SoT v1.6.75·`plans/05-writing-revise-report-gate-decisions.md`·`plans/05-writing-ai.md`·CHANGELOG·HANDOFF.
- **Canonical spec reference**: `docs/plans/05-writing-revise-report-gate-decisions.md`(Resolved, R1=A·R2=A·R3=A·R4=A·R5=A first→C·R6=A) + `docs/system-contract-sot.md` v1.6.75(L36) + v1.6.71/72/74(교차 참조). 브리프 §"승인 후 첫 회귀 경계" 9행이 lock list.
- **Source of work**: working tree, uncommitted. HEAD=cc6913f(v1.6.74 compose partial revision). 정본은 v1.6.75로 갱신됨.

## Scope

1. **Spec contract** — 브리프 R1~R6·9행 매트릭스·SoT v1.6.75 changelog·기존 v1.6.71/72/74 계약과의 내부 일관성·교차 모순. 기존 `/writing/revise`(2단계 아님, 독립)·`/writing/report`(독립 side-effect-free) 계약 무변경 확인.
2. **Implementation code** — 합성 순서(revise→report enrich→Gate)·동일 ContextPackage·report 실패 envelope·Gate 실패 envelope·예외 매핑 순서·의존성 guard(reporter 필수).
3. **report 실패 partial(R3=A·R4=A, 핵심)** — revise 성공 후 report 실패 시 revised candidate 보존 + `{candidate, gate:null, report_error}` 502/504, Gate 미호출; taxonomy(provider timeout 504, provider unavailable/invalid/unexpected 502).
4. **Gate 실패 partial의 report 보존(7b, 핵심)** — report 성공 후 Gate 실패 시 **최신 report가 든 enriched candidate**가 partial envelope에 보존되는지.
5. **Regression tests** — 9행 매트릭스가 named test로 채워지는지, guard 양방향 bite, 빈 셀 점검. mutation test로 under-strict guard 부재 경험적 증명.
6. **Full/focused suite + 컴파일/whitespace + 합성 패턴 sweep** — 906/45/185·94/84·py_compile·diff --check 재도출; 동일 report 우회/중복 합성 패턴 부재.

## Methodology

브리프 9행을 lock list(boundary matrix)로 세우고 각 셀을 named test로 추적. 핵심 적대 검증: (1) report 실패가 gate try 블록 **앞** 단계에서 wrap되어 gate 미호출이 보장되는지, revise ProviderError가 report/gate 실패로 오분류되지 않는지(예외 매핑 순서 + service wrapping 상호작용); (2) **Gate 실패 partial candidate의 "최신 report 보존" clause(7b)가 실제로 regression test에 의해 잠겨 있는지** — 코드 읽기만이 아니라 mutation(`enriched`→`revised`)을 주입해 기존 suite가 이를 잡아내는지 경험적 증명; (3) 합성 service가 report 단계에 추가 retry를 만들지 않는지(boundary 8), 동일 package 객체가 세 단계에 전달되는지(R2=A) — 테스트 더블의 `is` 검증과 `calls` counter로 이중 확인.

명령(전체 재현은 §Reproduction):
- `git --no-pager diff cc6913f -- services/application/app/writing/revise_gate.py services/application/app/main.py` — additive/수정 hunk만, 기존 `/writing/revise`·`/writing/report` 무변경 확인.
- `python3 -m pytest -q -p no:cacheprovider tests/test_writing.py tests/test_writing_accept.py tests/test_writing_gate.py tests/test_writing_report.py tests/test_writing_revise.py` → 94 passed/84 subtests.
- `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → 906 passed/45 skipped/185 subtests.
- `python3 -m py_compile ...` + `git diff --check`.
- mutation: `revise_gate.py`의 `WritingReviseGateFailure(enriched, exc)` → `(revised, exc)` 후 `tests/test_writing_revise.py` 실행 → 23 passed(=gap 증명) 후 즉시 원복.

## Findings

### 1. Spec contract — 일관성 PASS

브리프 R1~R6·9행 매트릭스 ↔ SoT v1.6.75 changelog(L36) ↔ 코드 일치. R1~R6 결정 literal이 세 곳에서 동일. "모델은 호출/응답, Application은 합성 순서·검증·오류 envelope 소유" 원칙(v1.6.73)이 유지 — report service는 `enrich` 1회 호출/응답 + 내부 strict JSON repair 1회, 합성 순서·partial envelope·의존성 guard는 Application. R5=A first→C(성공 `{candidate,gate}` 유지, `stages` additive 후속)가 SoT·브리프·CHANGELOG·plan 모두에서 일관. 정본 자기 모순 없음. 단, 용어 관찰(§Issues 비차단 #1) "non-pass 5종" 표현 존재.

### 2. Implementation code — 계약 대조 PASS

- R1=A: 기존 `POST /projects/{project_id}/writing/revise-and-gate`(`main.py:2580`)를 3단계로 승격. 별도 endpoint/flag 미추가. 기존 `/writing/revise`(`main.py:2502`)·`/writing/report`(`main.py:2433`) 무변경(diff 확인). ✓
- R2=A: endpoint가 `build_context_package` 1회(`main.py:2640`)로 package를 만들어 `writing_revise_gate.run(..., package=package)`(`main.py:2641`)에 전달; service `run()`이 같은 `package`를 revise·enrich·evaluate 세 단계에 전달(`revise_gate.py:72/79/83`). 재검색 없음. ✓
- R3=A: report 실패 → `except WritingReviseReportFailure`(`main.py:2661`)가 502/504 + `{candidate:_writing_candidate_payload(exc.candidate), gate:None, report_error:{type,detail}}` JSONResponse(`main.py:2670-2680`). `exc.candidate`는 service가 `WritingReviseReportFailure(revised, exc)`(`revise_gate.py:81`)로 건넨 **revised**(report 적용 전) — report 실패 시 report 없는 개정본 보존, 의미 일치. ✓
- R4=A: taxonomy — `cause`가 `ProviderError`면 504(TIMEOUT)/502(그 외) + `error_type=cause.code.value`, `InvalidCandidateReport`면 502/`invalid_candidate_report`, 그 외 502/`report_error`(`main.py:2662-2669`). report service(`report.py:67-85`)는 ProviderError를 전파(try 밖), invalid report는 repair 1회 후 `InvalidCandidateReport`. 매핑 원천과 일치. ✓
- R6=A: wiring이 `writing_revision is not None and writing_report is not None and writing_gate is not None`일 때만 service 구성(`main.py:1029-1035`). reporter 미구성 → service None → endpoint `writing_revise_gate is None` → 503(`main.py:2600-2604`), 어떤 context/revise/Gate 호출도 전. ✓
- 예외 순서: `except ProviderError`(`main.py:2658`)가 `WritingReviseReportFailure`/`WritingReviseGateFailure` **앞**. 그러나 service가 report/gate 예외를 `RuntimeError` subclass로 wrap하므로(`revise_gate.py:80-87`) ProviderError clause는 revise/context의 직접 ProviderError만 잡고, report/gate 실패는 각 전용 clause로 흐름. revise 실패가 gate 실패로 오분류되지 않음. ✓(이는 `test_revise_provider_timeout_is_504_without_calling_gate`가 잠금)
- diff: `main.py` additive(import + wiring 수정 + 신규 except clause), `revise_gate.py` additive(Protocol + 예외 class + run 3단계화). 사전 범위 밖 코드 미접촉. ✓

### 3. report 실패 partial(R3=A·R4=A) — PASS

`test_report_failure_returns_partial_candidate_without_calling_gate`(`test_writing_revise.py:527`)가 4종(TIMEOUT 504/`provider_timeout`, UNAVAILABLE 502/`provider_unavailable`, `InvalidCandidateReport` 502/`invalid_candidate_report`, `RuntimeError` 502/`report_error`)을 subtest로 열거. 각 case: status·`body["candidate"]["text"]`·**`body["candidate"]["candidate_claims"] == []`**(=report 적용 전 revised candidate 보존, report 필드인 candidate_claims로 revised vs enriched 구분)·`gate is None`·`report_error.type`·`reporter.calls == 1`·`gate.calls == 0`. report 4 필드 중 candidate_claims를 marker로 써서 "revised artifact 보존 + Gate 미호출"을 명시적 assertion으로 잠금. 양방향 guard 유효. ✓

### 4. Gate 실패 partial의 report 보존(7b) — **BLOCKING GAP (코드는 PASS, 테스트 미잠금)**

- **구현은 정확**: service가 gate 실패 시 `WritingReviseGateFailure(enriched, exc)`(`revise_gate.py:87`)로 **report 적용 후 enriched candidate**를 보존. endpoint는 `_writing_candidate_payload(exc.candidate)`(`main.py:2695`)로 4개 report 필드(self_reported_constraints·candidate_claims·new_memory_hints·risk_notes, `main.py:2259-2271`)를 직렬화하므로 응답 수준에서 관찰 가능. 코드·정본 일치.
- **그러나 regression assertion 부재**: `test_gate_failure_returns_partial_candidate`(`test_writing_revise.py:395`)는 5종 taxonomy는 잠그지만, partial candidate에 대해 `text`만 검사하고 **어떤 report 필드도 검사하지 않는다**(`test_writing_revise.py:416-420`). report 실패 테스트(§3)가 `candidate_claims == []`로 revised 보존을 잠근 것과 **비대칭**.
- **경험적 증명(mutation test)**: `revise_gate.py:87`을 `WritingReviseGateFailure(revised, exc)`(=최신 report 상실 회귀)로 바꾸고 `tests/test_writing_revise.py` 전체 실행 → **23 passed / 30 subtests passed**(회귀 탐지 실패). 즉 현재 suite는 "Gate 실패 partial candidate에 최신 report가 보존" contract 의무(SoT v1.6.75 "Gate 실패 partial candidate에는 최신 report가 보존된다" + 브리프 7행 "candidate에는 최신 report가 있다")를 잠그지 못한다. 즉시 원복(`grep VERIFY-MUTATION` → 잔여 없음 확인).
- **독립 회귀 가능성**: gate-failure candidate는 `exc.candidate`(예외 생성 시점)에서 오고, success candidate는 `result.candidate`(반환 시점)에서 옴. 둘 다 현재 `enriched`지만 **별개 코드 위치**이므로, success path의 `candidate_claims=="fresh"` assertion(`test_writing_revise.py:377`)이 gate-failure path를 대신 잠그지 못함. mutation으로 확인 완료.

### 5. Regression tests — boundary matrix 추적

| # | contract clause(브리프 9행) | named test | 상태 |
|---|---|---|---|
| 1 | revise→report→Gate 순서, 동일 package, 성공 `{candidate,gate}` | `test_composes_one_revise_and_one_gate_with_same_context` | 잠김 ✓ |
| 2 | Gate가 받는 candidate = reporter 최신 candidate(report 필드) | 같은 테스트, `gate.last_candidate.candidate_claims[0].text=="fresh"` + `reporter.last_candidate.candidate_claims==()` | 잠김 ✓ |
| 3 | report 실패 502/504 + `{candidate,gate:null,report_error}`, revised 보존 | `test_report_failure_returns_partial_candidate_without_calling_gate` | 잠김 ✓ |
| 4 | report 실패 시 Gate 0회; 정상 시 Gate 1회 | 위 테스트 `gate.calls==0` + (1) 테스트 `gate.calls==1` | 잠김 ✓ |
| 5 | reporter 미구성 503, 모든 호출 0 | `test_missing_gate_or_reviser_is_503`(3번째 subtest: report_service 누락 → 503, context/provider/gate calls 0) | 잠김 ✓ |
| 6 | revise/context 실패 → 기존 400/502/504 mapping, report/Gate 미호출 | `test_validation_failure_is_400_...`·`test_revise_provider_timeout_is_504_...`·`test_revise_failure_never_calls_gate`·`test_context_failures_map_...` | 잠김 ✓ |
| 7a | Gate non-pass 5종 모두 200 | `test_all_gate_decisions_are_200_without_second_revise`(`WritingGateDecision` 전수) | 잠김 ✓ |
| **7b** | **Gate 실패 partial candidate에 최신 report 보존** | `test_gate_failure_returns_partial_candidate`(taxonomy만, report 필드 미검사) | **빈 셀 ⚠️** |
| 8 | report repair 1회 재사용, 합성 service 추가 retry 없음 | `reporter.calls==1`(다수 테스트) + 코드 단일 await(루프 없음) | 간접 잠김 ✓ |
| 9 | save/accept/Analysis/재검색/2nd-revise side effect 0 | `test_composition_does_not_save_draft`(save) + `is` package 검증(재검색) | save 잠김 ✓, 나머지 구조적(ctor가 reviser/reporter/gate만) |

green bar(94/84, 906/45/185)는 재현됐으나, "green bar ≠ suite가 정본이 요구하는 것을 검증함" 구분이 필수 — 7b 셀이 비어 있으므로 본 검증은 green bar와 무관하게 conditional pass다.

### 6. Full/focused suite + 컴파일/whitespace + 패턴 sweep — PASS

- focused(`tests/test_writing*.py` 5파일): **94 passed / 84 subtests**(10.29s). 구현자 클레임과 정확 일치. ✓
- full(`--ignore=tests/test_memory_mongo.py`): **906 passed / 45 skipped / 185 subtests**(27.37s). 구현자 클레임과 정확 일치. ✓
- `python3 -m py_compile revise_gate.py main.py test_writing_revise.py` → OK. ✓
- `git diff --check` → clean. ✓
- 합성 패턴 sweep: `WritingReviseGateService` 인스턴스·`/writing/revise-and-gate` endpoint 각 1개뿐, 별도 우회/중복 합성 경로 없음. 독립 `/writing/revise`·`/writing/report`는 의도적 단일 API(2단계 합성 아님). 구현자 "동일 report 우회 합성 패턴 추가 발견 없음" 클레임 확인. ✓

## Issues / Risks

### Blocking (contract 의무)

- **B1 — Gate 실패 partial candidate의 "최신 report 보존"(7b) regression 미잠금**. SoT v1.6.75("Gate 실패 partial candidate에는 최신 report가 보존된다")와 브리프 7행("candidate에는 최신 report가 있다")이 명시한 contract 의무인데, `test_gate_failure_returns_partial_candidate`(`test_writing_revise.py:395-420`)가 taxonomy(5종 status/`gate_error.type`)는 잠그지만 partial candidate의 report 필드를 검사하지 않는다. mutation(`enriched`→`revised`, `revise_gate.py:87`) 주입 시 **suite 전체(23 test)가 green**으로 회귀를 탐지 못함(§4). 이것은 contract-required lock 누락이며 "후보 보강"/"후속"으로 재분류하지 않는다.
  - **권장 fix(오너 승인 후 구현자가 적용)**: 해당 테스트에 `self.assertEqual(body["candidate"]["candidate_claims"][0]["text"], "fresh")` 추가(report 실패 테스트의 `candidate_claims == []`와 대칭). 이 assertion은 mutation 하에서 `IndexError`(claims==[])로 실패하므로 under-strict guard로 작동하며, 정상(`enriched`) 하에서는 통과한다. 또는 service 단위 테스트에서 `WritingReviseGateFailure.candidate`가 enriched임을 직접 단언해도 동등.

### Hardening recommendations (비차단, 정본을 넘어서는 후보)

- **H1 — "non-pass 5종" 용어 정밀화**. `WritingGateDecision`은 pass|revise|retrieve_more|needs_user_review|block 5종(v1.6.69)이므로 "non-pass"는 문자 그대로 4종이다. SoT v1.6.74/v1.6.75·브리프 7행이 "non-pass 5종"이라 표기하나, 실제 의미는 "모든 decision outcome(5종)이 200"이다(`test_all_gate_decisions_are_200_without_second_revise`가 `WritingGateDecision` 전수로 200을 잠금). 동작은 정확·잠김. 정본 문구를 "5종(모든 decision outcome)" 또는 "non-pass 4종 + pass"로 정정하면 오독 방지. v1.6.74부터 이어진 표현이라 이 slice의 도입은 아님.
- **H2 — boundary 8(report repair 1회) composition-수준 직접 잠금**. 현재 `reporter.calls==1`로 호출 횟수는 잠기나, "report 일시 실패 시 합성 service가 retry하지 않는다"를 composition service 수준에서 직접 주입해 검증하는 테스트는 없다. 단, service 코드가 단일 `await`·루프 없음(`revise_gate.py:79`)이고 report service 자체의 repair 1회는 `tests/test_writing_report.py`가 소유하므로 현행으로 충분.
- **H3 — boundary 9 accept/Analysis/2nd-revise side-effect spy**. `WritingReviseGateService` ctor가 `reviser/reporter/gate`만 받으므로 accept/Analysis는 구조적 도달 불가. save는 `test_composition_does_not_save_draft`이 잠금. accept/Analysis/re-retrieve 명시 spy는 정본이 "side effect 0"을 더 강하게 잠그고 싶을 때 후보.

## Verdict

**조건부 합격(conditional pass)**.

- 이유(支点): 구현은 R1~R6·9행 매트릭스 전체에 대해 정확하고 정본과 일치하며, 906/45/185·94/84 재현, py_compile/diff --check clean, 합성 패턴 sweep·예외 매핑 순서·report taxonomy 모두 PASS다.
- 단, **B1 = contract-required regression lock 누락**(Gate 실패 partial candidate의 최신 report 보존). mutation test로 "현재 suite가 이 회귀를 잡지 못함"을 경험적 증명. CLAUDE.md §5 "boundary matrix에 빈 셀이 있으면 blocking" / "contract-required lock 누락을 후속으로 재분류하지 않는다"에 따라 합격이 아닌 조건부 합격.
- 폐쇄 조건: `test_gate_failure_returns_partial_candidate`에 gate-failure partial candidate의 report 필드 보존 assertion(예: `candidate_claims[0].text == "fresh"`) 추가. 이 단일 assertion으로 7b 셀이 채워지고 verdict → 합격.

## Outstanding items

- 본 slice는 working tree 미커밋 상태(HEAD=cc6913f). B1 폐쇄 전 커밋 권장하지 않음(오너 결정 영역).
- B1 fix는 구현자가 적용(검증자는 surface만, CLAUDE.md "검증 실패 시 silently fix하지 않는다").
- R5 C(다회 합성 `stages` additive)·retrieve_more lifecycle 브리프는 후속(오너가 "다음 우선 후보는 retrieve_more lifecycle 결정 브리프"로 명시).

## Reproduction

```bash
# focused
PYTHONPATH=. python3 -m pytest -q -p no:cacheprovider \
  tests/test_writing.py tests/test_writing_accept.py tests/test_writing_gate.py \
  tests/test_writing_report.py tests/test_writing_revise.py
# → 94 passed, 84 subtests passed

# full non-LLM
PYTHONPATH=. python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider
# → 906 passed, 45 skipped, 185 subtests passed

# compile / whitespace
python3 -m py_compile services/application/app/writing/revise_gate.py \
  services/application/app/main.py tests/test_writing_revise.py
git diff --check

# B1 gap 증명(mutation; 실행 후 반드시 원복)
# services/application/app/writing/revise_gate.py:87
#   WritingReviseGateFailure(enriched, exc)  →  WritingReviseGateFailure(revised, exc)
PYTHONPATH=. python3 -m pytest tests/test_writing_revise.py -q -p no:cacheprovider
# → 23 passed (회귀 탐지 실패 = B1 gap 증명). 원복 후 재실행 시 23 passed(정상).
# (원복 확인: grep -n VERIFY-MUTATION services/application/app/writing/revise_gate.py → 없음)
```
