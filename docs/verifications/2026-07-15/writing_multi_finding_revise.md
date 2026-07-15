# Verification — Phase 5.x Writing loop multi-finding revise (SoT v1.6.88)

## Subject metadata

- **Date**: 2026-07-15
- **Requester**: owner ("다음작업 검증해줘 ... Writing loop multi-finding revise")
- **Verifier**: independent audit (this session)
- **Target slice/artifact**: Writing loop 다수 continuity finding 순차 revise
  - `services/application/app/writing/revise_gate.py` (`_is_eligible_continuity_revise` 신규 + `_eligible_revision_finding` 완화)
  - `tests/test_writing_revise.py` (`EligibleRevisionFindingTest` 5 + `MultiFindingSequentialLoopTest` 2, +7; boundary case 정정)
- **Canonical spec reference**: `docs/plans/05-writing-multi-finding-revise-decisions.md` (D1=A/D2=A/D3=A 결정 브리프) + `docs/system-contract-sot.md` v1.6.88 row. 종속: `revise_gate.py` bounded loop(`run`/`_run`), `gate.py:32-36,122-125`(decision priority).
- **Source of work being verified**: commit `d1187aa` (HEAD; working tree clean).

## Scope

계약 스코프(브리프 chain 따라 확장한 정본 집합):

1. **자격 완화 계약(D2=A)** — `_eligible_revision_finding` "정확히 1개" → "N개 중 최우선 1개". 빈/전부 자격밖 → None(`not_eligible` 유지).
2. **자격 범위(D1=A)** — continuity + REVISE + evidence 후보 내 정확히 1회만. do_not_use/pov는 splice 제외.
3. **선택 순서(D3=A)** — error severity 먼저, 동급 시 Gate 반환 순서(안정).
4. **순차 소진 전제** — loop가 매 revise 후 revised candidate로 re-gate해 남은 finding 재선택.
5. **변경 표면 격리** — 자격 함수만 변경; loop/reviser/splice/report/Gate/audit/budget·public literal·schema·서비스 경계 무변.
6. **bound 안전성** — `max_revision_rounds` + `UnchangedWritingRevision`(NO_CHANGE)가 총량/무한루프 bound.

Out of scope: batch reviser(D2=B), do_not_use/pov 자동 revise(D1=B), `max_revision_rounds` 기본값 상향(live 후) — 전부 브리프 Deferred.

## Methodology

계약 스코핑 → 경계 매트릭스 → 구현/테스트를 **반박 대상 가설**로 1차 소스 재도출. 모든 claim `file:line`.

실행 명령(재현 가능):
- `git show --stat d1187aa`; `git show d1187aa -- services/application/app/writing/revise_gate.py`; `git show d1187aa -- tests/test_writing_revise.py`
- `python3 -m py_compile services/application/app/writing/revise_gate.py tests/test_writing_revise.py`
- `PYTHONPATH=. python3 -m pytest tests/test_writing_revise.py::EligibleRevisionFindingTest tests/test_writing_revise.py::MultiFindingSequentialLoopTest -v`
- `PYTHONPATH=. python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` (프로젝트 정규 명령)
- `docker compose config --quiet`; `git diff --check`; `git status --short`
- 코드 정독: `revise_gate.py:355-444`(loop revise/re-gate), `:524-565`(자격 함수), `models.py:42-50`(finding type/severity), `gate.py:32-36,122-125`(decision priority), `main.py:2741-2828`(run 진입)
- 패턴 스윕(§4): `_eligible_revision_finding`·`_is_eligible_continuity_revise` 소비처 전수

## Findings

### F1. 자격 완화 + D1=A continuity-only — CONFIRMED

`_is_eligible_continuity_revise`(`revise_gate.py:524-537`): `finding_type is CONTINUITY` ∧ `recommended_decision is REVISE` ∧ `evidence.strip()` ∧ `candidate.text.count(evidence)==1`. 구 단일-finding 규칙을 per-finding으로 추출(내용 동일). `_eligible_revision_finding`(`:541-565`): `eligible=[f for f in findings if _is_eligible_continuity_revise(...)]`, 빈 → None. do_not_use/pov는 `CONTINUITY` 아니므로 자동 splice 제외(D1=A) — 코드로 직접 확인. 회귀 `test_none_when_no_finding_eligible`(subTest 5: empty·POV·RETRIEVE_MORE decision·evidence 부재·3회 중복)가 전부 None 단언(under-strict). **boundary cell**: 자격 밖 전수 → None ✓.

### F2. D3=A 선택 순서 — CONFIRMED, 양방향

`:559-563` `max(enumerate(eligible), key=lambda i:(i[1].severity is WritingGateSeverity.ERROR, -i[0]))[1]`. ERROR(True=1) > WARNING(False=0) 1차; 동급 시 `-index`로 **가장 작은 index(=Gate 반환 순서 먼저)** 2차. 회귀 `test_error_severity_selected_before_warning_order_independent`(`test_writing_revise.py`)가 `(warn,err)→err`·`(err,warn)→err` **양 순서** 단언 — order-independence 양방향 lock. `test_two_eligible_selects_first_in_gate_order`(동급 2개→첫 번째)로 안정성 확인. **boundary cell**: error-priority·gate-order-tie ✓.

### F3. 자격밖 혼재가 eligible을 dead-end 안 함 — CONFIRMED [이 slice의 핵심]

`:556` list comprehension이 ineligible을 걸러내고 eligible만 남김. 구 `len(findings)!=1→None` 제거. 회귀 `test_ineligible_findings_do_not_dead_end_eligible_one` — `(pov, cont)→cont`(POV는 ineligible이나 cont 선택). under-strict: 구 규칙이면 None → 이제 cont. 기존 boundary case `test_revise_eligibility_rejects_every_broader_boundary`에서 `(_finding("고친 문장."),_finding("뒤 문장."))` 항목을 invalid tuple에서 **제거**(+ 주석 "TWO eligible continuity findings is no longer ineligible"). 대신 `test_two_eligible_selects_first_in_gate_order`·`test_multi_finding_revise_processes_sequentially`가 eligible 경로를 lock — **boundary case 정정이 양방향**(옛 not_eligible 단언 제거 + 새 eligible 단언 추가). **boundary cell**: ineligible 혼재 ✓.

### F4. 순차 소진 전제(re-gate) — CONFIRMED [load-bearing]

loop REVISE 분기(`revise_gate.py:395-444`): `eligible=_eligible_revision_finding(current_candidate,last_gate.findings)` → revise → `current_candidate=revised`(`:434`) → `refresh_report()` → `evaluate_gate()`(`:440-443`) → `continue`(`:444`). 즉 **revised candidate로 re-gate**. reviser가 선택 finding evidence를 제거하면 다음 gate는 그 finding 없이 재평가 → 남은 finding이 `_eligible_revision_finding`으로 재선택. follow-up(브리프:72) "revise 후 candidate 텍스트 변경 → 남은 finding evidence 1회 여부 자연 재검증"도 `count(evidence)==1`이 새 candidate에서 재평가됨으로 성립. 회귀 `test_multi_finding_revise_processes_sequentially`가 **실 `WritingReviseGateService.run` + 실 reviser provider**(`_service(_SequenceProvider(...))`)로 2-finding 순차→PASS 실측(`revision_rounds==3`·`provider.calls==3`·`gate.calls==3`·최종 text `앞 문장. 고친2. 뒤2.`) — 단순 unit가 아닌 end-to-end 관통. **boundary cell**: sequential 2-finding ✓.

### F5. bound 안전성 — CONFIRMED

- `max_revision_rounds`: `:401-404` `revision_rounds>=max_revision_rounds`→BUDGET_EXHAUSTED. 회귀 `test_second_eligible_bounded_by_revision_rounds`(기본 상한 R=2)가 2-finding에서 3라운드 진입 않고 `BUDGET_EXHAUSTED`·`revision_rounds==2`·`provider.calls==2` 단언(**over-strict**: 무한/초과 실행 시 재실패).
- `UnchangedWritingRevision`: `:416-422` reviser no-change → NO_CHANGE 종료 — 정체 finding 무한루프 차단.
- 이중 방어(R cap + NO_CHANGE)로 finding N개 소진이 구조 상한 초과 불가. **boundary cell**: budget bound(over-strict) ✓.

### F6. 변경 표면 격리 — CONFIRMED

`git show d1187aa -- revise_gate.py`의 유일 hunk `@@ -520,19 +521,43 @@`(자격 함수 영역). loop 본체(`:355-444`)·reviser/splice/report/Gate/audit/budget 무변. 패턴 스윕: `_eligible_revision_finding` 소비처 = `revise_gate.py:396` 1곳 only; `_is_eligible_continuity_revise` 소비처 = `revise_gate.py:556` 1곳 only. import `WritingGateSeverity` 1개 추가. public literal·schema·서비스 경계 무변 — worker "변경 표면=자격 함수 1개" 주장 정확. **boundary cell**: 표면 격리 ✓.

### F7. Gate 계약 전제 — 부분 정정(비차단, 아래 Issues)

브리프(`05:27`) "revise 분기의 모든 finding이 revise 추천"은 **부정확**. `gate.py:122-123` `decision=max(findings' recommended_decision, key=_PRIORITY)`; REVISE 분기(decision=REVISE)면 각 finding의 recommended_decision ∈ {PASS(0), REVISE(1)}(더 높은 RETRIEVE_MORE/NEEDS_REVIEW/BLOCK 불가). 즉 PASS-recommended finding이 섞일 수 있음. 단 코드는 `recommended_decision is REVISE`로 **명시 필터**하므로 정확도 무영향(오히려 브리프보다 robust). See H1.

### F8. 재현 — worker claim 전부 독립 확인

| claim | 결과 |
|---|---|
| 회귀 +7(Eligible 5·MultiFinding 2) | `7 passed, 5 subtests passed` ✓ |
| 기존 boundary case 정정 | tuple 항목 제거 + 주석 + 새 eligible lock 확인 ✓ |
| full 1062/45/239 | 정규 명령 → `1062 passed, 45 skipped, 239 subtests` ✓ (정확 일치) |
| py_compile | OK ✓ |
| `docker compose config` | `--quiet` exit 0 ✓ |
| `git diff --check` | clean(working tree clean post-commit) ✓ |

**count 정합**: d1187aa가 test_writing_revise.py에 **정확히 7 메서드** 추가(40→47). 베이스라인은 1051이 아닌 **1055** — 커밋된 v1.6.87(24d14fd)이 per-stage test를 10→14로 늘였기 때문(아래 Observations). 1055+7=1062 ✓. subtests 235→239(+5 신규 subTest −1 정정항목 = +4) ✓.

## Issues / Risks

### Blocking (계약 의무 위반)

**없음.** 경계 매트릭스 11 cell 전부 회귀 lock; 순차 소진 전제(re-gate)와 bound 안전성 이중 방어가 loop 본체에서 확인; 변경 표면이 자격 함수로 격리; worker claim 정규 명령으로 재현.

### Hardening recommendations (비차단, 계약 초과)

- **H1 (브리프 정밀도)**: 브리프 `05:27` "revise 분기의 모든 finding이 revise 추천"이 부정확(PASS-recommended finding 혼재 가능, F7). 코드는 `recommended_decision is REVISE` 필터로 정확 처리하므로 동작 영향 0이나, 브리프 추론이 느슨 — "revise 추천 finding 중"으로 정정 권장(구 `len!=1` 근거 설명이 목적이므로 결론은 유효).
- **H2 (DO_NOT_USE 명시 미측정)**: 비-continuity 분야 테스트가 POV만 사용. `WritingGateFindingType`에 DO_NOT_USE가 별도(`models.py:43`)이나 동일 필터링(`CONTINUITY` 아니면 제외)이라 POV가 대표. DO_NOT_USE explicit case 추가 시 회귀 보강 가치 경미.
- **H3 (first-round finding 비대칭 — 설계상 인지)**: `/writing/revise-and-gate` 진입(`main.py:2741,2827`)의 첫 finding은 **client 제공**(`body.finding`), 자격 선택 아님. while-loop 후속 finding만 relaxed selector 사용. 진입 설계상 의도(test 6이 client 첫 finding + re-gate 2개로 정확히 관통)라 결함 아님 — 문서화만.

### Observations (cross-slice, 본 slice 영향 없)

- **커밋된 v1.6.87(24d14fd)이 본 verifier 직전 검증(`writing_per_stage_measure_mi.md`)의 비차단 hardening을 반영**: commit msg가 해당 검증 기록을 명시 인용 — "비차단 hardening 반영 — H6(incomplete ceiling fails-closed)·H2(env→policy wiring 회귀)·H1(SoT v1.6.86 합성 코어 역참조)". per-stage test 10→14(초기 10 + hardening 4). 본 검증이 확인한 H6 fail-closed 가드는 `measure_writing_stages.py:191,207-225`에 **정상 구현**(`compose_ceiling`이 `complete=not incomplete_stages and error is None`, 미완료 시 numeric ceiling null + `complete=false`) — stub 아님. 직전 v1.6.87 검증 기록은 **10-test pre-hardening 버전**을 검증했으므로, 적용된 hardening(14-test)은 본 session에서 심층 감사 안 함(suite green, low risk). owner가 원하면 별도 quick re-confirmation 권장.

## Verdict

**PASS (조건 없음).**

이유:
1. 경계 매트릭스 11 cell(자격 밖 5·단일·2개 순서·error 우선 양방향·ineligible 혼재·sequential 2-finding integration·budget over-strict) 전부 회귀 lock, 빈 cell 없음.
2. load-bearing 순차 소진 전제(re-gate)가 loop 본체(`revise_gate.py:395-444`)에서 확인, 실 service+reviser end-to-end 관통(test 6).
3. bound 안전성 이중 방어(`max_revision_rounds` + `UnchangedWritingRevision`)로 총량/무한루프 차단, over-strict 회귀로 lock.
4. 변경 표면이 자격 함수 1개로 격리(패턴 스윕 단일 소비처 확인), public literal·schema·서비스 경계 무변.
5. worker claim(7 회귀·boundary 정정·1062/45/239·lint)이 정규 명령으로 독립 재현, count 정합(1055+7=1062).
6. 비차단 hardening 3건 + cross-slice observation 1건은 모두 계약 초과/별도 slice.

## Outstanding items

- **B2b ceiling live 수집 (오너, sandbox 밖 풀스택)**: 여전히 풀스택 다운으로 막힘. 본 slice와 독립.
- **Deferred (브리프 명시)**: batch reviser(D2=B), do_not_use/pov 자동 revise(D1=B), `max_revision_rounds` 기본값 상향(live 데이터 후).
- **v1.6.87 hardening re-confirmation (선택)**: 적용된 H6/H2/H1 hardening의 심층 재감사 — 본 session에서는 구현 정상 + suite green만 확인.

## Reproduction

```bash
# 1. 컴파일
python3 -m py_compile services/application/app/writing/revise_gate.py tests/test_writing_revise.py

# 2. focused +7
PYTHONPATH=. python3 -m pytest \
  tests/test_writing_revise.py::EligibleRevisionFindingTest \
  tests/test_writing_revise.py::MultiFindingSequentialLoopTest -v
#   → 7 passed, 5 subtests passed

# 3. 정규 full suite (worker claim 재현)
PYTHONPATH=. python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider
#   → 1062 passed, 45 skipped, 239 subtests passed

# 4. 계약 정합 정독
#    revise_gate.py:395-444 (loop revise/re-gate), :524-565 (자격 함수),
#    gate.py:32-36,122-125 (decision priority), models.py:42-50 (type/severity)

# 5. 설정/정합
docker compose config --quiet && git diff --check && git status --short
```
