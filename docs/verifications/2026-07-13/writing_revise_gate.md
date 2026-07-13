# 독립 검증 — Phase 5.7 partial revise→Gate 1회 합성 (SoT v1.6.74)

## Subject metadata

- **Date**: 2026-07-13
- **Requester**: 오너("다음작업 검증해줘. Phase 5.7 revise→Gate 1회 합성을 구현했습니다. … 원격 실모델에서는 revise 성공 후 Gate가 invalid JSON을 반환했습니다. 합성 계층이 revised candidate를 보존해 partial_ok 경로가 실제로 작동하는 것을 확인 … 독립 검증 전이라 아직 커밋하지 않았습니다.").
- **Verifier**: 독립 세션(검증자). 구현자 클레임을 반박 가설로 취급 — green bar와 무관히 계약 경계를 깨보려 시도.
- **Target slice**: Phase 5.7 — 신규 `services/application/app/writing/revise_gate.py`(`WritingReviseGateService`·`WritingReviseGateFailure`·Protocol 주입), `main.py`(`WritingReviseGateService` wiring·`POST /projects/{id}/writing/revise-and-gate`·partial JSONResponse), `tests/test_writing_revise.py`(`WritingReviseGateApiTest` +7). 문서: SoT v1.6.74·`plans/05-writing-revise-gate-decisions.md`·`plans/05-writing-ai.md`·CHANGELOG·HANDOFF.
- **Canonical spec reference**: `docs/plans/05-writing-revise-gate-decisions.md`(Resolved, G1=A·G2=A·G3=A first→B·G4=A·G5=A·G6=A·G7=A·G8=A first→B) + `docs/system-contract-sot.md` v1.6.74(L36). 브리프 §"승인 후 첫 회귀 경계" 8행이 lock list.
- **Source of work**: working tree, uncommitted. HEAD=d8231cf(v1.6.73). 이전 검증(`writing_report_api.md`·`writing_partial_revise.md`)의 B1/H2/H3가 d8231cf에서 폐쇄됨을 먼저 확인.

## Scope

1. **Spec contract** — 브리프 G1~G8·8행 매트릭스·SoT v1.6.74 changelog·"모델=호출/응답, Application=합성 순서/검증/오류 envelope" 원칙의 내부 일관성·교차 모순. 기존 `/writing/revise` 계약 무변경(G1=A) 확인.
2. **Implementation code** — 합성 순서(revise→gate)·동일 ContextPackage·partial envelope 구조·예외 매핑·의존성 guard.
3. **partial_ok(G4=A, 핵심)** — revise 성공 후 Gate 실패 시 revised candidate 보존; 성공한 개정이 splice·report clear까지 적용된 상태로 전달되는지.
4. **Regression tests** — 8행 매트릭스가 named test로 채워지는지, guard 양방향 bite, 빈 셀 점검. 이전 B1(context 매핑)·H3(no-save spy) 반영 확인.
5. **Live LLM smoke(독립 재현)** — 실모델에서 revise 성공→Gate invalid JSON→합성층 partial_ok candidate 보존 재현.
6. **Full/focused suite + 컴파일/whitespace** — 903/45/179·91/78·py_compile·diff --check 재도출.

## Methodology

브리프 8행을 lock list로 세우고 각 셀을 named test로 추적. 핵심 적대 검증: (1) 합성 서비스가 revise를 gate try 블록 **밖**에서 호출하는지(revise 실패 시 gate 미호출 보장), gate 실패 시 `WritingReviseGateFailure(revised, exc)`로 candidate를 잃지 않는지 코드 확인; (2) 실 gemma 모델에서 revise-then-gate를 돌려 Gate invalid JSON 시 **보존된 candidate가 진짜 개정본**(splice 적용·report clear·evidence 제거)인지 1차 원천에서 재현 — fake-provider는 gate 실패를 주입해 envelope 구조만 검증하므로 실제 발화를 live로 증명.

명령(전체 재현은 §Reproduction):
- `git --no-pager diff d8231cf -- services/application/app/main.py` — 3개 additive hunk(imports·wiring·신규 endpoint)만, 기존 `/writing/revise` 무변경 확인.
- `python3 -m pytest -q ... tests/test_writing_revise.py tests/test_writing.py tests/test_writing_report.py tests/test_writing_gate.py tests/test_writing_accept.py` → 91/78.
- `python3 -m pytest --ignore=tests/test_memory_mongo.py -q` → 903/45/179.
- `/tmp/smoke_revise_gate.py` — 실 revise+gate 합성, partial_ok 재현.

## Findings

### 1. Spec contract — 일관성 PASS

브리프 G1~G8 ↔ SoT v1.6.74 changelog ↔ 코드 일치. "모델은 호출/응답, Application은 합성 순서·검증·오류 envelope·loop/budget 제어 소유" 원칙이 코드에 충실히 반영 — 모델 서비스(revise/gate)는 각각 1회 호출/응답, 합성 순서·partial envelope·의존성 guard는 Application(`revise_gate.py`·endpoint). G4 순차화(현재 A=502/504 partial, 후속은 별도) 일치. HANDOFF·CHANGELOG·plan v1.6.74 동기화. 정본 모순 없음.

### 2. Implementation code — 계약 대조 PASS

- G1=A: 신규 `POST /projects/{project_id}/writing/revise-and-gate`(`main.py:2576`). v1.6.74 diff가 main.py에 **3개 additive hunk**(imports `89-90`·wiring `1029-1030`·신규 endpoint `2573+`)만 — 기존 `/writing/revise`(`2498`) 무변경. ✓
- G2=A: endpoint가 `build_context_package` 1회로 package를 만들고 `writing_revise_gate.run(..., package=package)`에 전달; revise·gate가 같은 package 사용(`revise_gate.py:57-66`). ✓
- 합성 순서(`revise_gate.py:57-69`): `revised = await self._reviser.revise(...)`(try 밖 → revise 실패 시 전파, gate 미호출), `try: gate = await self._gate.evaluate(...) except Exception: raise WritingReviseGateFailure(revised, exc)`(gate 실패 시 revised 보존). 설계가 계약을 정확히 반영. ✓
- partial envelope(`main.py:2657-2678`): cause별 status/type 산출(ProviderError→504/502·code, InvalidWritingGateResult→502·invalid_gate_result, WritingGateError→400·writing_gate_error, else→502·gate_error) 후 `JSONResponse(status, {candidate, gate:null, gate_error:{type,detail}})`. 성공은 `{candidate, gate}`(`2679-2682`). G6=A 일치. ✓
- G7=A: `writing_revise_gate = WritingReviseGateService(...) if writing_revision is not None and writing_gate is not None else None`(`main.py:1029-1030`) — 어느 하나 미구성 시 None→503, 조용한 degrade 없음. ✓
- side-effect: endpoint 본문은 validate_inputs·build_context_package·run·직렬화만 — save/report/accept/Analysis 호출 부재(구조적).

### 3. partial_ok (G4=A, 핵심) — PASS

- `test_gate_failure_returns_partial_candidate`(`test_writing_revise.py:360-380`): 3 subtest(ProviderError TIMEOUT→504/provider_timeout, UNAVAILABLE→502/provider_unavailable, InvalidWritingGateResult→502/invalid_gate_result). 각 status + `body["candidate"]["text"]=="앞 문장. 고친 문장. 뒤 문장."`(진짜 개정본) + `gate is None` + `gate_error.type`. under-strict 유효(candidate 미보존 시 text 불일치).
- **live 재현**: 실 gemma에서 revise 성공 후 Gate가 `InvalidWritingGateResult: ... content must be JSON`로 실패 → `OUTCOME=partial_ok`. 보존된 candidate = `'해리는 ... 그런데 해리는 방금 넣은 상자를 손에 꼭 쥐고 있었다.'` — `REVISE_ACTUALLY_APPLIED=True`(원본 아님, splice 적용)·`REPORT_CLEARED=True`·`EVIDENCE_GONE_FROM_TEXT=True`. 작업자 "합성 계층이 revised candidate를 보존해 partial_ok가 작동" 클레임 1차 원천 재현.

### 4. Regression tests — 8행 매트릭스(§Issues B1의 빈 셀 외) PASS

1. 동일 package revise 1→gate 1, 성공 `{candidate,gate}`: `test_composes_one_revise_and_one_gate`(gate.last_package IS context.last_package, candidate_claims==()) ✓
2. non-pass 5종 200, 두 번째 revise 없음: `test_all_gate_decisions_are_200_without_second_revise`(`WritingGateDecision` 전 순회, provider.calls==1·gate.calls==1) ✓
3. Gate 실패 partial: `test_gate_failure_returns_partial_candidate` ✓ (위 §3)
4. 의존성 미구성 503: `test_missing_gate_or_reviser_is_503`(gate 결측·reviser 결측 각 503) ✓
5. context 실패 매핑 + revise/gate 미호출: `test_context_failures_map_without_revise_or_gate_calls`(BudgetExceeded→504·Failed→502, provider.calls==0·gate.calls==0) ✓ — **이전 검증 B1(context 502/504)이 이 endpoint에서는 커버됨.**
6. revise 실패→Gate 미호출: `test_revise_failure_never_calls_gate`(unchanged→InvalidWritingRevision→502, gate.calls==0) ✓
7. no draft save: `test_composition_does_not_save_draft`(`_NoWriteCoreSotService` save spy, save_calls==0) ✓ — **이전 H3(no-save spy) 반영.**
- 이전 H2(validate before context_search)도 d8231cf에서 `validate_inputs` 추출로 해소 — `/writing/revise`(`2552`)·본 endpoint(`2635`) 모두 context_search 전 validate.

### 5. Suite / 컴파일 / whitespace — 재도출 PASS

- focused: **91 passed / 78 subtests**(클레임과 정확 일치).
- full: **903 passed / 45 skipped / 179 subtests**(정확 일치).
- `py_compile` 변경 3파일 OK; `git diff --check` clean.

## Issues / Risks

### Blocking (계약 의무)

- **B1 — 본 endpoint의 revise-failure 매핑 sub-case가 미실행(빈 셀)**: 브리프 §3이 "revise validation/provider/context 실패는 Gate 미호출, 기존 400/502/504"를 명시하나, composition endpoint에서 실행된 revise-failure sub-case는 `InvalidWritingRevision→502`(`test_revise_failure_never_calls_gate`)뿐. 다음 두 분기가 어떤 composition test에도 exercise되지 않음:
  - (a) `except (WritingRevisionError, InvalidContextSearchRequest) → 400`(`main.py:2643`) — validate_inputs 실패(duplicate evidence·non-continuity·빈 입력·cross-project) 및 context 입력검증.
  - (b) bare `except ProviderError → 502/504`(`main.py:2654`) — revise provider timeout/unavailable. revise가 gate try **밖**(`revise_gate.py:57`)에서 호출되므로 revise ProviderError는 wrapping 없이 그대로 endpoint까지 전파되어 이 분기로 간다.
  - **boundary matrix 빈 셀 — green bar(903 passed)와 무관하게 blocking.** 단, (a)의 validate_inputs 로직과 400/502/504 매핑은 `/writing/revise`(동일 except 절, 회귀 있음)와 공통이므로, 이전 검증 B1들보다 회귀 위험은 낮다 — 위험은 "composition endpoint 전용 except-clause regression"으로 좁다. → 조건부 합격, B1 test 2건(예: duplicate-evidence finding→400+gate.calls==0; revise `_Provider(error=ProviderError(TIMEOUT))`→504+gate.calls==0) 추가 시 합격. (검증자는 §5에 따라 음서 수정하지 않음.)

### Hardening recommendations (비차단)

- **H1 — Gate cause fallback 분기 미실행**: `WritingGateError → 400 "writing_gate_error"`(`main.py:2664-2665`)와 `else → 502 "gate_error"` fallback(`2666-2667`)이 composition test에 없음. composition에서 gate 입력은 서버 구성·validate_inputs이 빈 instruction을 선제하므로 WritingGateError는 사실상 도달 불가; else는 방어 분기. 도달불가 사유를 문서화하거나 1건 케이스 권장.
- **H2 — partial envelope 400 허용 관찰**: brief G4/오너 발언은 "Gate 실패 502/504"이나, 코드는 `WritingGateError` cause일 때 partial envelope를 **400**으로도 반환. gate 검증실패가 400-class인 전체 error taxonomy와 일관되므로 합리적이나, "502/504" 진술을 400까지 확장한다는 SoT 한 줄 명시 권장.

## Verdict

**조건부 합격(conditional pass).** 조건: B1(composition endpoint revise-failure 400 / revise-provider 502·504 회귀 2건 추가).

근거: G1~G8 합성 계약(동일 package·revise 1+gate 1·non-pass 200·nested envelope·의존성 503 no-degrade·no-save) 전부 독립·적대 검증 통과, **partial_ok를 실모델에서 1차 원천 재현**(gate invalid JSON→진짜 개정 candidate 보존), suite 91/78·903/45/179·컴파일/whitespace 재도출 일치, SoT v1.6.74 원칙 충실 반영, 이전 검증 B1·H2·H3가 d8231cf+본 slice에서 모두 폐쇄됨. 유일한 계약 의무 위반은 B1 — composition endpoint 전용 revise-failure sub-case(단, 로직은 `/writing/revise`에서 이미 회귀로 잠금). B1만 채우면 합격. 본 slice는 세 검증 중 가장 충실한 커버리지.

## Outstanding items

- 변경사항 **미커밋**(working tree). B1 채운 뒤 커밋·HANDOFF 마무리가 정합적.
- B1 test 미추가(검증자 음서 수정 금지, §5).
- H1·H2는 오너 재량(H2 SoT 한 줄 명시 권장).
- Gate JSON 품질/repair는 본 slice 범위 외(별도 후속) — live에서 gate가 invalid JSON을 낸 것도 이 때문이며, partial_ok가 이를 안전하게 흡수함을 검증완료.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
# focused + full
python3 -m pytest -q -p no:cacheprovider tests/test_writing_revise.py tests/test_writing.py tests/test_writing_report.py tests/test_writing_gate.py tests/test_writing_accept.py   # 91 passed / 78 subtests
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider                                                                  # 903 passed / 45 skipped / 179 subtests
python3 -m py_compile services/application/app/main.py services/application/app/writing/revise_gate.py tests/test_writing_revise.py
git diff --check
# 기존 /writing/revise 무변경 확인: v1.6.74 diff가 additive hunk 3개만
git diff d8231cf -- services/application/app/main.py | grep "^@@"
# B1 빈 셀 수동 확인: composition test가 validate_inputs→400 / bare revise ProviderError→502/504 를 exercise 안 함
grep -n "duplicate\|ProviderError\|validate_inputs" tests/test_writing_revise.py   # WritingReviseGateApiTest(326~)에 해당 케이스 부재
# live partial_ok(원격 가동 시)
curl -s http://192.168.1.22:9080/health
PYTHONPATH=. python3 /tmp/smoke_revise_gate.py     # OUTCOME=partial_ok + REVISE_ACTUALLY_APPLIED=True
```
