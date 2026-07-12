# 독립 검증 — Phase 5.2 Writing Gate (SoT v1.6.69)

## Subject metadata

- **Date**: 2026-07-12
- **Requester**: 오너("작업 Ai 가 작업한 부분 확인하고 검증하고 의심하고 또 의심해줄래? Writing Gate slice를 v1.6.69로 구현했습니다.").
- **Verifier**: 독립 세션(검증자). 구현자의 클레임을 확인용이 아닌 반박용 가설로 취급.
- **Target slice**: Phase 5.2 Writing Gate — 신규 `writing/gate.py`·`writing/gate_prompt.py` + `writing/models.py` 확장(WritingGateDecision/FindingType/Severity/Finding/Result) + `main.py` `POST /projects/{id}/writing/gate` 엔드포인트.
- **Canonical spec reference**: `docs/plans/05-writing-gate-decisions.md`(Resolved, D1=A·D2=B·D3=A·D4=A first, "승인 후 첫 회귀 경계" 9행) + `docs/plans/05-writing-ai.md` §74-79 + `docs/system-contract-sot.md` v1.6.69(버전 로그 L36) + Gate 합성 계약(L319-339).
- **Source of work**: working tree, uncommitted. `git status` — modified `main.py`·`writing/models.py`·`05-writing-ai.md`·SoT·CHANGELOG·HANDOFF·work_log, untracked `writing/gate.py`·`writing/gate_prompt.py`·`05-writing-gate-decisions.md`·`tests/test_writing_gate.py`. HEAD = `388cf07`(v1.6.68).

## Scope

1. **Spec contract** — 브리프 D1~D4·"승인 후 첫 회귀 경계" 9행의 내부 일관성, SoT v1.6.69 엔트리·plan §78-79·Gate 합성 테이블(L328)과의 교차 일관성.
2. **Implementation code** — `writing/gate.py`(strict parser·priority 재계산·do_not_use/POV blocking·evidence grounding·project isolation), `writing/gate_prompt.py`(terminal JSON prompt·payload 조립), `writing/models.py`(계약 리터럴), `main.py`(엔드포인트·에러 매핑 400/502/504/503/404).
3. **계약 일관성 검증** — D3=A(side-effect-free, 부분 revise 느슨한 연결), "저장·검색·재생성 수행 안 함", priority 모델 주장에 맡기지 않고 재계산, malformed 502 vs invalid input 400 분리.
4. **Regression tests** — 회귀 14개(+6 subtests)가 매트릭스 9행을 양방향으로 채우는지 추적. 구현자 work_log L337 "양방향으로 검사한다" 클레임 검증.
5. **Boundary matrix** — 브리프 9행 각 분기가 named test로 매핑되는지, 빈 셀이 있는지.
6. **Full suite + mutation** — 838/48/107 재도출 + 변형으로 guard bite 증명.

라이브 실 Gemma 판정 품질·JSON 준수는 브리프 Follow-up(L68)가 "production 판정 품질 채택은 fake 회귀와 분리"로 명시적으로 scope 밖. 결정적 parser/service/HTTP 계약만 검증.

## Methodology

브리프 "승인 후 첫 회귀 경계" 9행을 lock list로 세우고 코드·테스트·스펙에 대입. 각 "should fire"와 "should NOT fire(over-strict)" 분기를 named test로 추적한 뒤, 변형(mutating guard)으로 기존 테스트가 변형을 bite하는지(real failure) 확인하여 guard가 잠겨 있는지 증명. under-strict뿐 아니라 over-strict 방향을 독립적으로 증명.

명령(재현은 §Reproduction):
- `cat services/application/app/writing/gate.py gate_prompt.py tests/test_writing_gate.py` — 신규 코드/테스트.
- `git diff HEAD -- services/application/app/main.py services/application/app/writing/models.py` — 확장 diff.
- `grep -n "1.6.69\|Writing Gate" docs/system-contract-sot.md CHANGELOG.md docs/plans/05-writing-ai.md` — 정본 반영.
- `python3 -m pytest tests/test_writing_gate.py -v -p no:cacheprovider` — focused(14/6).
- `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` — 전체(838/48/107).
- 변형: `cp gate.py /tmp/gate.py.bak` → 정확한 문자열 replace → focused pytest → 복구 → `diff -q`로 복구 확인(MW1·MW2).
- 400 도달성: httpx ASGI 인메모리 클라이언트로 빈 instruction/candidate_text·bad task_type 직접 POST.

## Findings

### 1. Spec contract — 내부 일관성

브리프 D1=A·D2=B·D3=A·D4=A first ↔ "승인 후 첫 회귀 경계" 9행 ↔ SoT v1.6.69 엔트리(L36) ↔ plan §78-79가 전부 일관. decision literal·우선순위·finding type/severity·public envelope가 정본 3곳에 동일 문자열로 반영.

정직성 포인트:
- **D3=A의 정당성**(브리프 L14, work_log L342): 브리프 옵션 B는 "자동 전체 재생성"인데 오너 의도는 위반 판정 단위 부분 재생성이므로, 부분 patch anchor 계약이 없는 현재에 B를 택하면 의도 역전. D3=A로 두고 finding별 `evidence`/`recommended_decision`을 후속 연결점으로 남긴 것은 정확한 범위 설정.
- **malformed 502 vs invalid input 400 분리**(work_log L343): 초기에 malformed LLM JSON이 400으로 합쳐질 수 있었던 것을 `WritingGateError`(입력→400)와 `InvalidWritingGateResult`(provider 결과→502)로 분리. 이 분리는 브리프 L89 매트릭스("malformed/provider fault 502")와 일치.

SoT L484("Writing Gate decision literal과 editor 처리 — 미확정 유지")는 literal이 v1.6.69로 잠긴 현재 부분 stale. → §Issues/Hardening.

### 2. Implementation code — 스펙 리터럴 대 일치

- `_PRIORITY`(`gate.py:31-35`): `{PASS:0, REVISE:1, RETRIEVE_MORE:2, NEEDS_USER_REVIEW:3, BLOCK:4}` → `max`가 `block > needs_user_review > retrieve_more > revise > pass`를 정확히 산출. 브리프 L47/L86과 동일.
- decision literal 5종·finding type 3종·severity 2종(`models.py:34-50`): 브리프 L37/L47 리터럴과 문자열 그대로 일치.
- finding schema exactness(`gate.py:117-119`): `set(value) != {type,severity,message,evidence,recommended_decision}` — 추가 필드 거부. 브리프 D2=B("exactly") 일치.
- root schema exactness(`gate.py:96`): `set(root) != {decision,findings,checked_constraints}` — 추가 필드 거부.
- do_not_use/POV blocking 강제(`gate.py:129-133`): `severity is not ERROR or recommendation is not BLOCK` → raise. 로직은 올바름.
- evidence grounding(`gate.py:69-70`): `any(item.evidence not in candidate.text ...)` → 후보 prose에 존재하는 발췌만 허용. 로직 올바름.
- project isolation(`gate.py:81-91`): instruction/candidate text 비어있음·request_id 불일치·project 불일치를 provider 호출 전(`evaluate` L56 `_validate`가 `generate` L63보다 선행) 검증. 로직 올바름.
- HTTP 에러 매핑(`main.py:2261-2274`): `WritingGateError`→400, `InvalidWritingGateResult`→502, `ContextSearchBudgetExceeded`→504, `ContextSearchFailed`→502, `ProviderError`→`(code is TIMEOUT)?504:502`. 브리프 L89 매트릭스와 일치.
- side-effect-free: 엔드포인트는 `context_search.build_context_package` + `writing_gate.evaluate`만 호출. save/search-재실행/regenerate 코드 경로 없음. D3=A 일치.

### 3. 계약 일관성 검증 — 핵심 클레임

- **"priority를 모델 주장에 맡기지 않고 findings로 재계산·검증"**(work_log L333): `parse_writing_gate_result`(`gate.py:109-112`)가 `max(findings recommended_decision)`로 expected를 재계산하고 `decision is not expected`면 reject. 참으로 확인. 단, 이 검증의 over-strict 방향이 테스트에 잠기지 않음(→ §5 finding).
- **generate→gate additive**: gate 서비스/엔드포인트가 generate 응답을 변경하지 않음. `_writing_candidate_payload` 미건드, gate 응답은 독립 envelope. D4=A "합성은 additive 확장 가능" 일치.
- **candidate 비영속 inline**: 엔드포인트가 body로 `WritingCandidate`를 즉석 생성(`main.py:2252-2256`), candidate_id 없음. 브리프 L89 "별도 candidate-not-found 분기는 없다" 일치.

### 4. Boundary matrix — lock 추적 (9행)

브리프 "승인 후 첫 회귀 경계"(`05-writing-gate-decisions.md:79-90`) 9행을 lock list로 세우고 각 분기를 named test에 매핑.

| # | 브리프 분기 | 방향 | 매핑된 test | 상태 |
|---|---|---|---|---|
| 1 | pass: finding 없음 → editor 제안 | should-fire | `test_pass_requires_no_findings`(L85) | ✓ |
| 2a | do_not_use 위반 → block | under-strict | `test_each_non_pass_decision...`(block, L92)·`test_evaluate...`(L125) | ✓ |
| 2b | 명시 POV hard 위반 → block | under-strict | `test_priority...`(pov→block, L99-105) | ✓ |
| 2c | **정상 prose는 block 금지** | **over-strict** | — | **빈 셀** |
| 3 | continuity error → revise; warning만으로 block 금지 | fire+over-strict | revise: `test_each...`(revise, L92). warning→block 금지: priority over-strict와 동일 분기 | 부분 |
| 4 | 근거 부족 → retrieve_more; 정상 후보는 retrieve_more 금지 | fire+over-strict | retrieve_more: `test_each...`(L92). over-strict: priority over-strict와 동일 분기 | 부분 |
| 5 | 상충/모호 → needs_user_review; hard 위반을 review로 약화 금지 | fire+over-strict | nur: `test_each...`(L92). 약화 금지: do_not_use/pov validator → 부분(GAP-2) | 부분 |
| 6 | 우선순위 block>nur>retrieve_more>revise>pass | 양방향 | `test_priority...`(block>revise, L99) — **under-strict만** | 부분(GAP-1) |
| 7 | parser: bad JSON/unknown literal/누락 필드/빈 응답 | should-reject | `test_unknown_literal...`(L107)·`test_invalid_model_output...`(L193) | ✓ |
| 8 | cross-project → provider 호출 전 거부 | should-reject | `test_cross_project...`(provider.calls==0, L143) | ✓ |
| 9 | HTTP 200/503/404/400/502/504 | 매핑 | 200(L184)·503(L212)·404(L207)·502(L193,198)·504(L198). **400 미검증** | 부분(GAP-3) |

빈 셀 1 + 부분 셀 3(=over-strict 미잠금 1, validator parametrization 미완 1, HTTP 400 미검증 1). 이 행들이 아래 §Issues의 blocking finding이 됨.

### 5. Mutation testing — guard bite 실증

각 변형 후 focused 14개가 여전히 통과하면 해당 guard가 잠기지 않은 것(unlocked)으로 판정. 변형 적용→pytest→`cp /tmp/gate.py.bak` 복구→`diff -q`로 복구 확인.

- **MW1 (over-strict priority unlock)**: `gate.py:111` `if decision is not expected:` → `if _PRIORITY[decision] < _PRIORITY[expected]:`(under-strict만 reject, 과대 decision 허용). 결과: **14 passed** — over-strict 방향(block/needs_user_review/retrieve_more decision이 lower findings만 있을 때)이 잠기지 않음. 독립 실행(`out("block",[f("revise")])`, `out("retrieve_more",[f("revise")])`)로 실제 reject 동작은 올바름을 확인 — 즉 코드는 맞고 test만 없음.
- **MW2 (do_not_use/pov weakening unlock)**: `gate.py:132` `recommendation is not WritingGateDecision.BLOCK` → `recommendation is WritingGateDecision.REVISE`(revise만 reject, nur/retrieve_more 약화 허용). 결과: **14 passed** — do_not_use/pov를 needs_user_review/retrieve_more로 약화하는 방향이 잠기지 않음. 독립 실행(do_not_use/pov + nur/retrieve_more)로 실제 reject 동작은 올바름 — 코드는 맞고 test만 없음.

복구 확인: `diff -q /tmp/gate.py.bak gate.py` identical. focused 14/6 재통과.

### 6. Full suite

`python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **838 passed / 48 skipped / 107 subtests**. 구현자 보고(838/48/107)와 일치. focused `test_writing_gate.py`는 14 passed/6 subtests(구현자의 "33 passed"는 `test_writing_gate.py`(14)+`test_writing.py`(19) 합산 — 일치). `py_compile` gate/gate_prompt/models/main/테스트 통과.

### 7. 기타 관찰

- 엔드포인트가 context_search로 ContextPackage를 재구성(`main.py:2258`)하므로, gate HTTP 호출은 실제로 provider 호출 2회(context planner + gate evaluate)를 동반. 다만 gate service 자체는 1-turn이고 `test_evaluate...`가 service 수준 `provider.calls==1`을 단언하므로 D1=A "별도 1-turn" 위반 아님. 다만 gate 엔드포인트의 context-search-failure→504/502 매핑은 gate 표면에서 재단언되지 않고 generate 엔드포인트(test_writing.py)의 동일 패턴에 의존 — 비차단.

## Issues / Risks

### Blocking (contract obligations)

이슈 1~3은 모두 **코드 동작은 올바르고 test만 부재**인 경우(MW1·MW2 변형과 독립 실행으로 확인). fix는 test 추가만으로 완결(production 코드 변경 불요). 그럼에도 매트릭스 빈/부분 셀이므로 조건부 합격.

- **B1 — over-strict decision-priority guard 미잠금(매트릭스 2c/3/4/6 over-strict, GAP-1)**: `parse_writing_gate_result`(`gate.py:109-112`)의 priority 검증은 양방향을 검사하지만, `test_priority_rejects_weaker_top_level_decision`(L99-105)은 under-strict(block findings + revise decision) 방향만 단언. over-strict(lower findings + 과대 decision, 예: `_output("block",[_finding("revise")])` 또는 `_output("retrieve_more",[_finding("revise")])`)는 reject되어야 하지만 이를 잠그는 test 없음. MW1로 unlocked 입증. 브리프 L82-84 "정상 prose는 block 금지(over-strict)·단순 warning만으로 block 금지·근거 충분한 정상 후보는 retrieve_more 금지"가 contract-required over-strict 분기. 이 분기를 단언하는 named test 추가 필요.
- **B2 — do_not_use/POV blocking-error 요구의 불완전 parametrization(매트릭스 5 over-strict, GAP-2)**: validator(`gate.py:129-133`)는 do_not_use/POV가 `(severity=error AND recommendation=block)`일 것을 요구. 그러나 `test_hard_do_not_use_and_pov_findings_cannot_be_weakened`(L119-123)은 `(error, revise)` 한 셀만 단언. `(error, needs_user_review)`·`(error, retrieve_more)` 약화와 `(warning, *)` severity 약화는 단언 없음. MW2(revise만 reject)로 unlocked 입증. 브리프 L85 "명백한 hard 위반을 review로 약화 금지"가 contract-required. finding_type×recommendation×severity 경계값을 parametrize하는 test 보강 필요.
- **B3 — HTTP 400(invalid input) 분기 미검증(매트릭스 9, GAP-3)**: 엔드포인트의 `WritingGateError`→400 매핑(`main.py:2261-2262`)과 task_type `ValueError`→400(L2222-2225)이 도달 가능하나(빈 instruction→400·빈 candidate_text→400·bad task_type→400을 httpx로 실증), 어느 test도 400을 단언하지 않음(`grep 400 tests/test_writing_gate.py` 없음). 브리프 L89 "invalid input 400"이 contract-required HTTP 분기. invalid input→400 named test 추가 필요.

### Hardening recommendations (non-blocking)

- **H1 — `writing_agent_prompt.md §16.2` finding shape drift**: §16.2가 revision-loop 소비자 입력으로 `type=pov_violation`·`violating_text`를 기술하나, v1.6.69가 잠근 schema는 `type=pov`·`evidence`(+`severity`/`recommended_decision`). 이 slice가 §16.2를 직접 소비하지는 않으므로(revise 자동화는 브리프 Deferred) 동작 영향 없으나, cross-doc 불일치. revise loop slice 착수 시 §16.2를 잠긴 schema로 갱신하거나 매핑을 명시할 것. 브리프 Follow-up에 한 줄 메모 권장.
- **H2 — SoT L484 stale**: "Writing Gate decision literal과 editor 처리(미확정 유지)"가 literal 잠금(v1.6.69)과 충돌. literal은 확정·editor 처리만 deferred로 문구 갱신 권장. plan §78은 이미 올바르게 [x] 표시.
- **H3 — prompt "when available" 헤지 vs 강제 grounding**: prompt(`gate_prompt.py:26`) "Evidence must be a short exact excerpt from the candidate **when available**"이 헤지하나, parser는 evidence 비empty 강제(`gate.py:140-143`)·service는 `evidence in candidate.text` 강제(L69-70). "when available"은 사문(dead letter) — 모델이 이를 따라 evidence를 생략하면 parser가 reject. 특히 retrieve_more(컨텍스트 부재) finding은 후보 발췌가 의미적으로 어색. prompt에서 "when available" 제거하고 "모든 finding은 후보의 해당 span을 인용"으로 명시 권장. 동작 영향 없(prompt가 모델 품질에만).
- **H4 — 우선순위 중간 사슬(nur>retrieve_more>revise) 미단언**: `test_priority...`가 block>revise 한 쌍만. `_PRIORITY` dict로 산출되므로 로직 오류 가능성 낮으나, 다중 finding으로 전 사슬을 한 번에 단언하는 test 추가 시 매트릭스 6 신뢰도 상승.
- **H5 — package.project_id 불일치 분기 미직접단언**: `_validate`(`gate.py:88`)의 `package.project_id != request.project_id`가 OR로 candidate 분기와 같은 줄이라 개별 test 없음. 의미 중복이나 도달 가능 경로 명시 권장.

## Verdict

**조건부 합격(conditional pass)**. 정본 계약(브리프 D1~D4 + 매트릭스 9행, SoT v1.6.69, plan §78-79)은 내부 일관, 구현 리터럴은 스펙과 일치, side-effect-free·priority 재계산·project isolation·에러 매핑의 핵심 클레임이 모두 참. full suite 838/48/107 green.

그러나 매트릭스의 contract-required over-strict 분기 3곳이 named test로 잠기지 않음 — (B1) decision-priority over-strict 방향, (B2) do_not_use/POV blocking-error parametrization, (B3) HTTP 400. 세 경우 모두 변형·독립 실행으로 "코드는 올바르게 동작하지만 test만 부재"임을 입증했으므로, fix는 **test 추가만**으로 완결(production 코드 무변경). B1·B2·B3 회귀가 추가되면 합격.

## Outstanding items

- 변경 미커밋(구현자 명시). `git status` — 4 untracked(gate.py·gate_prompt.py·브리프·테스트) + 3 modified(main.py·models.py·문서 3). B1~B3 test 보강 후 커밋 권장.
- SoT·CHANGELOG·HANDOFF·plan·브리프는 v1.6.69 기준으로 갱신됨(확인 완료).
- B1~B3 test 추가 후 focused·전체 suite 재실행 필요.

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system

# focused (14 passed / 6 subtests)
python3 -m pytest tests/test_writing_gate.py -v -p no:cacheprovider

# full suite (838 passed / 48 skipped / 107 subtests)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider

# B1 입증: over-strict priority unlocked (변형 후 14 passed = guard 없음)
cp services/application/app/writing/gate.py /tmp/gate.py.bak
python3 - <<'PY'
import pathlib
p = pathlib.Path("services/application/app/writing/gate.py")
s = p.read_text()
p.write_text(s.replace(
  '    if decision is not expected:\n        raise ValueError("decision does not match finding priority")',
  '    if _PRIORITY[decision] < _PRIORITY[expected]:\n        raise ValueError("decision does not match finding priority")'))
PY
python3 -m pytest tests/test_writing_gate.py -q -p no:cacheprovider   # 여전히 14 passed = B1
cp /tmp/gate.py.bak services/application/app/writing/gate.py

# B2 입증: do_not_use/pov weakening to nur/retrieve_more unlocked
python3 - <<'PY'
import pathlib
p = pathlib.Path("services/application/app/writing/gate.py")
s = p.read_text()
p.write_text(s.replace(
  '           recommendation is not WritingGateDecision.BLOCK):\n        raise ValueError("do_not_use and POV findings must be blocking errors")',
  '           recommendation is WritingGateDecision.REVISE):\n        raise ValueError("do_not_use and POV findings must be blocking errors")'))
PY
python3 -m pytest tests/test_writing_gate.py -q -p no:cacheprovider   # 여전히 14 passed = B2
cp /tmp/gate.py.bak services/application/app/writing/gate.py

# B3 입증: 400 도달 가능 (현재 test에 400 단언 없음)
grep -c "400" tests/test_writing_gate.py   # 0
```
