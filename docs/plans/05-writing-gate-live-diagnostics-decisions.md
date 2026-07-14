# 착수 결정 브리프 — Phase 5.10 Writing Gate live diagnostics

상태: `Proposed — 2026-07-14`

관련 정본: `docs/system-contract-sot.md` v1.6.81, `05-writing-loop-benchmark-decisions.md` B1~B4, `05-writing-bounded-loop-decisions.md` L6/L9, `05-writing-persisted-loop-audit-decisions.md` P1/P2/P5

## Decision needed

Remote Gemma Q4 B2b live run의 주된 502은 `Gate` stage의 `invalid_gate_result`이지만, 현재 persisted audit은 P1 bodyless 정책이라 raw provider content를 남기지 않아 정확한 JSON/enum/priority/evidence 위반 clause를 판별할 수 없다. **어떤 범위의 raw Gate output을 어디에 노출·보존할지**는 audit 본문 보존·public API·운영 접근 경계를 정하므로 기존 계약에서 도출할 수 없으며, 오너 선택 없이 구현할 수 없다.

## Current evidence

- benchmark 전용 project의 persisted audit은 revise·report 완료 뒤 Gate stage failed와 `error_type="invalid_gate_result"`를 반복 기록했다. provider token도 실제 누적됐다.
- gateway upstream readiness, configured model id와 served model id, 전용 replica-set Mongo transaction write가 모두 확인됐다. 이번 502은 remote auth, model-id mismatch, Mongo write permission이 아니다.
- `WritingGateService`는 raw model text를 `parse_writing_gate_result()`에 전달하며, exact key set, decision literal, findings/checked_constraints array, finding literal·priority·evidence containment을 strict 검증한다. audit은 stage/hash만 기록하므로 어느 clause가 실패했는지는 알 수 없다.

## Options table

### D1 — raw Gate output 관측 경계

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. operator-only one-shot CLI (Recommended) | benchmark 전용 project/request를 입력으로 받아 동일 Gate provider request의 raw response와 parse error만 stdout에 출력한다. DB/audit/API response에는 저장하지 않는다. | P1 bodyless·P2 opt-in policy와 public envelope를 바꾸지 않고 원인을 재현 가능하다. | 실행자에게 local runtime 접근이 필요하고, 별도 CLI 회귀가 필요하다. |
| B. request opt-in debug response | `/writing/revise-and-gate` 요청 flag가 true일 때 502 partial envelope에 raw Gate output을 additive로 넣는다. | 실제 실패 요청 한 번으로 정보가 나온다. | API caller에게 model text가 노출되고 public contract·access control을 새로 정해야 한다. |
| C. persisted audit에 raw Gate output 저장 | audit detail에 raw provider text를 저장해 나중에 조회한다. | 재현 없이 과거 실패를 분석할 수 있다. | P1 bodyless 결정과 충돌하며 retention·민감 본문·접근 권한을 함께 재결정해야 한다. |

### D2 — 진단 뒤 remediation 순서

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. raw evidence 확인 후 별도 prompt/repair brief (Recommended) | D1 결과로 실제 위반 clause를 고정한 뒤 prompt literal, repair, parser 완화 중 하나를 다음 브리프에서 결정한다. | quality 문제를 추측 수정하지 않고 strict Gate 계약을 보존한다. | B2b 재실행이 한 단계 늦어진다. |
| B. 지금 JSON repair를 추가 | Gate parse 실패 때 곧바로 provider repair 1회를 호출한다. | 일부 malformed JSON은 빨리 수렴할 수 있다. | repair format·token budget·failure semantics를 evidence 없이 선점한다. |
| C. parser를 완화 | extra key/priority/evidence 오류를 허용한다. | failure count가 줄 수 있다. | Gate public contract와 안전 경계를 약화시킬 수 있다. |

## Recommendation + reason

**D1=A, D2=A**를 권장한다. 현재는 로컬 1인 운영이지만 B2b는 production aggregate ceiling의 근거다. raw model text를 audit이나 public API에 넣으면 이미 확정된 bodyless audit 경계를 되돌리는 반면, one-shot local CLI는 해당 실패를 관측하는 데 필요한 최소 범위다. exact failure clause를 본 뒤에만 prompt/repair/parser 변경을 결정하면 strict Gate 안전 계약과 B4의 “실측 전 default-off” 원칙을 유지할 수 있다.

## Follow-up considerations

- CLI 출력은 operator terminal에만 존재하며 file write·Mongo write·audit append를 하지 않는다. 민감 candidate/context text가 포함될 수 있으므로 command output을 work log나 committed fixture에 복사하지 않는다.
- CLI가 production request와 같은 model, prompt template, ContextPackage, `thinking=false`, max token 설정을 썼는지 regression으로 잠근다.
- D2 후 prompt/repair 변경 시 B2b의 fixture hash·model/quant/compose revision을 새 report에 함께 기록하고, 이전 failure audit은 역사 기록으로 보존한다.

## Deferred / out of scope

- persisted audit의 raw provider body, retention/TTL, encryption, role-based audit access.
- public debug API flag, frontend diagnostics UI, production telemetry pipeline.
- Gate parser 완화, JSON repair, prompt rewrite, model/quant 변경의 실제 구현.
- B2b aggregate token/time default-on 또는 ceiling 숫자 변경.
