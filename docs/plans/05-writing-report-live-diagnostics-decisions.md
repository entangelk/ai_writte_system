# 착수 결정 브리프 — Phase 5.10 Writing candidate report live diagnostics

상태: `Resolved — 2026-07-14 (오너 채택: D1=A, D2=A)`

> **배경**: v1.6.83 gate fence-strip remediation으로 B2b `invalid_gate_result` 502가 0건이 됐으나, 재측정(1/12 success)에서 `invalid_candidate_report` 502가 남았다("report field must be an array"). persisted audit은 P1 bodyless라 report raw output이 없고, report는 1-call repair가 있어 first/repair 어느 쪽이·어느 clause에서 실패했는지 알 수 없다.
>
> **결과**: 오너가 gate D1=A와 동일 패턴을 채택했다 — D1=A operator-only report 진단 CLI로 report raw output(first + repair)과 exact strict-parse error를 stdout에서 관측하고, D2=A에 따라 remediation(report fence strip / prompt / parser)은 별도 결정 브리프로 연기. D1=A 진단 표면은 v1.6.84로 구현됐다(`services/application/app/writing/report_live_diag.py`, `scripts/diagnose_writing_report.py`, `tests/test_writing_report_live_diag.py`).
>
> **D2=A remediation은 별도 결정 브리프(오너 결정)**: 관측한 exact clause로 (a) `report.py:parse_report`에 fence strip 추가(tracked debt `report.py:113`, gate `json_object` 선례) (b) report prompt에 fence 금지 (c) schema 위반에 대한 prompt 보강 중 어느 조합을 채택할지 결정. report는 이미 repair가 있으므로 gate보다 완충돼 있지만, first+repair 모두 같은 방식으로 실패하면 repair도 소용없다는 점이 관측으로 드러난다.

## Decision needed

B2b 재측정(v1.6.83 이후)의 `invalid_candidate_report` 502는 report parser가 모델 출력을 reject한 것이지만, raw report content가 저장되지 않아 정확한 위반 clause(fence? schema? 어느 필드?)와 first/repair 중 어느 시점인지 판별할 수 없다. **어느 범위의 raw report output을 어디에 노출·보존할지**는 기존 계약에서 도출할 수 없다.

## Options table

### D1 — raw report output 관측 경계

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. operator-only one-shot CLI (Resolved) | gate 진단과 동일. benchmark project/request를 입력받아 동일 report provider request의 first+repair raw response와 parse error만 stdout에 출력. DB/audit/API 저장 없음. | P1 bodyless·P2 opt-in 정책·public envelope 무변, 원인 재현 가능. report의 first+repair 두 raw를 모두 잡음. | 실행자 local runtime 접근 필요, 별도 CLI 회귀. |
| B. request opt-in debug response | `/writing/revise-and-gate` 요청 flag가 true일 때 partial envelope에 raw report output을 additive. | 실패 요청 한 번에 정보. | API caller에게 model text 노출, public contract·접근제어 재설계. |
| C. persisted audit에 raw report 저장 | audit detail에 raw report text 저장. | 재현 없이 과거 실패 분석. | P1 bodyless 결정과 충돌, retention·접근권한 재결정. |

### D2 — 진단 뒤 remediation 순서

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. raw evidence 확인 후 별도 브리프 (Resolved) | D1 결과로 exact 위반 clause를 고정한 뒤 fence strip / prompt / parser 완화 중 하나를 다음 브리프에서 결정. | 품질 문제를 추측 수정하지 않음, strict report 계약 보존. | 일부 malformed는 수렴이 한 단계 늦음. |
| B. 지금 JSON repair 추가 / parser 완화 | evidence 없이 repair 강화 또는 schema 완화. | 빠를 수 있음. | format·token·failure semantics를 evidence 없이 선점, contract 약화 위험. |

## Recommendation + reason (채택됨)

**D1=A, D2=A**. gate D1=A가 효과를 입증했으므로 report에도 동일 최소 범위를 적용한다. report는 1-call repair가 있어 first+repair 두 raw를 모두 잡는 점만 gate와 다르다. raw model text를 audit/public API에 넣으면 bodyless audit 경계를 되돌리지만, one-shot local CLI는 해당 실패를 관측하는 최소 범위다.

## Follow-up considerations

- CLI 출력은 operator terminal에만 존재하며 file/Mongo/audit write를 하지 않는다. 민감 candidate/context text가 포함될 수 있으므로 work log나 committed fixture에 복사하지 않는다.
- CLI가 production과 같은 model/prompt template/ContextPackage/thinking=false/max_tokens를 쓰는지 회귀로 잠근다(`_build_report_service(capture)`로 production config 재사용).
- D2 후 remediation 시 report fixture hash·model/quant/compose revision을 새 report에 기록하고 이전 failure audit은 역사 기록으로 보존한다.

## Deferred / out of scope

- persisted audit의 raw report body, retention/TTL, role-based audit access.
- public debug API flag, frontend diagnostics UI.
- report parser fence strip / JSON repair / prompt rewrite의 실제 구현 (D2=A 별도 브리프).
- `analysis/compare_judge.py`·`extractor.py`·`context_search/planner.py`·`writing/retrieval.py`의 동일 root-cause(tracked debt) — repair로 완충돼 있어 별도 후속.
