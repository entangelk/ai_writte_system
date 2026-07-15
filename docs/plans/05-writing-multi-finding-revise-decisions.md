# 착수 결정 브리프 — Phase 5.x Writing loop multi-finding revise

상태: `Resolved — 2026-07-15 (오너 D1=A·D2=A 확정, D3=A 기본; 구현·회귀 완료 SoT v1.6.88)`

## Resolution (오너 결정 2026-07-15)

- **D1=A continuity-only 유지**: 각 선택 finding은 continuity + revise + evidence 후보 내 정확히 1회. do_not_use/pov는 revise 추천이어도 자동 splice 제외(Gate 계약이 block/needs_review로 라우팅).
- **D2=A sequential**: `_eligible_revision_finding`을 "정확히 1개"에서 "N개 중 최우선 1개 선택"으로 완화. loop 기존 re-gate가 다음 라운드 finding을 선택, finding당 revision round 1 소비(구조 상한 bound). reviser/splice/report/gate/audit/budget 계약 무변.
- **D3=A** (기본 적용): error severity 먼저, 동급이면 Gate 반환 순서(안정 정렬).
- 구현: `revise_gate.py`에 per-finding 자격 `_is_eligible_continuity_revise` 추출 + `_eligible_revision_finding`이 자격 finding 중 severity desc→gate순서 최우선 1개 선택. 변경 표면 = 자격 함수 1개(loop·reviser·report·Gate 무변). 회귀 +7(`EligibleRevisionFindingTest` 5: 자격 0→None[empty·POV·DO_NOT_USE·retrieve_more·evidence 부재·multi-occurrence]·단일·2개 첫 선택·error 우선 order-independent·ineligible 혼재 시 eligible 선택 / `MultiFindingSequentialLoopTest` 2: 실 reviser 관통 sequential 2-finding→pass·기본 상한 budget_exhausted bound). 기존 `test_revise_eligibility_rejects_every_broader_boundary`의 "2 continuity findings→not_eligible" case를 새 계약(eligible)으로 정정. full 1062/45/240. **독립 검증 PASS(조건 없음)** `docs/verifications/2026-07-15/writing_multi_finding_revise.md`; 비차단 hardening 3건 반영(H1 브리프 정밀도[revise 분기 finding 추론]·H2 DO_NOT_USE 명시 케이스·H3 first-round finding 비대칭 문서화).

관련 정본: `docs/system-contract-sot.md` v1.6.87, `05-writing-loop-ceiling-composition-decisions.md`, `flat-loop-gate.md` §Budget, `revise_gate.py`(loop·`_eligible_revision_finding`), `gate.py`(`_PRIORITY`·finding 파싱), `gate_prompt.py`(finding 계약), Phase 5.6 부분 revise(v1.6.73) D4=C 후속.

## 배경 — 현재 단일-finding 제약

`revise_gate.py`의 bounded loop는 Gate decision이 `revise`일 때 `_eligible_revision_finding`(`revise_gate.py:523-538`)로 자동 revise 대상을 고른다. 이 함수는 **정확히 1개**만 허용한다:

```python
if len(findings) != 1:            # ← 2개+ 이면 즉시 not_eligible
    return None
finding = findings[0]
if finding.finding_type is not CONTINUITY: return None
if finding.recommended_decision is not REVISE: return None
if not finding.evidence.strip() or candidate.text.count(finding.evidence) != 1: return None
```

**Gate 계약상**(`gate.py:32-36,123-125`) loop가 revise 분기에 있으면 decision = findings의 `recommended_decision` 최대 우선순위 = `revise`이므로, **그 순간 어떤 finding도 `retrieve_more`/`needs_user_review`/`block`를 추천하지 않는다**(그들이 있으면 decision이 그쪽으로 올라가 revise 분기 자체에 안 온다). 남는 finding 추천은 `revise` 또는 `pass`인데(검증 H1: `pass` 추천 finding이 섞일 수 있음), **자격 함수가 `recommended_decision is REVISE`인 continuity finding만 선택**하므로 `pass` 추천이 섞여도 안전하다. 즉 revise 분기에서 revise-추천 continuity finding이 2개+면 정상적인 다수 지적인데, 현재는 **1개가 아니라는 이유만으로 자동 개선을 포기**(`not_eligible` 종료)한다.

B2b 재측정에서 `not_eligible`이 다수 관측된 한 원인이기도 하다(다만 그건 finding 자격 strict 조건 미달이 주였다 — work_log 2026-07-14 Task 2). 실 Gate가 다수 continuity 문제를 한 번에 지적하는 정상 상황을 loop가 처리 못 하는 게 이 slice의 gap이다.

## Decision needed

Gate가 revise 분기에서 **다수 finding**을 낼 때 loop가 이를 bounded budget 안에서 어떻게 소진하는가 — (1) 어떤 finding이 자동 revise 자격인가(범위), (2) 여러 개를 어떤 처리 모델로 도는가, (3) 여러 자격 finding 중 무엇을 먼저 고르는가.

## D1 — 자동 revise 자격 범위 (finding type)

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **D1=A. continuity-only 유지(추천)** | 현행처럼 각 선택 finding은 `continuity` + `revise` + evidence 후보 내 정확히 1회만. do_not_use/pov는 revise 추천이어도 자동 splice 대상 제외(→ 그 gate decision이 애초에 block/needs_review로 라우팅되도록 Gate 계약이 유도). | 안전 — do_not_use/pov는 canon/POV 위반이라 evidence-splice 자동수정 위험. 현행 보수 자세 유지, 계약 최소 확장. | 다수 continuity만 소진, do_not_use/pov 다수는 여전히 loop 밖(설계상 block/needs_review). |
| D1=B. revise 추천 finding 전체 | continuity뿐 아니라 pov/do_not_use라도 `recommended_decision=revise` + evidence-once면 자동 revise. | Gate가 revise로 낸 모든 걸 소진. | do_not_use/pov를 evidence-splice로 자동수정하는 건 canon 오염 위험(2B.3 "자동 병합 없음" 정신과 상충). 범위 급확대. |

추천 **D1=A** — 로컬 1인 프로젝트지만 정본 보존 정책상 canon-민감(do_not_use/pov) 자동수정은 review 경로로 두는 게 맞다. 현행 단일-finding 자격 규칙을 그대로 유지하고 "정확히 1개" 조건만 완화.

## D2 — 처리 모델 (sequential vs batch)

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **D2=A. sequential — 라운드당 1 finding(추천)** | `_eligible_revision_finding`을 "정확히 1개"에서 "N개 중 최우선 1개 선택"으로 완화. loop가 이미 매 revise 뒤 report→re-gate를 돌므로, 남은 finding은 다음 라운드 gate 결과에서 다시 선택된다. finding당 revision round 1개 소비, `max_revision_rounds`로 총량 bound. | **reviser/splice 계약 무변**(단일 finding), 기존 re-gate loop 재사용, 결정적, budget 자동 bound. 변경 표면 최소(자격 함수 1개). | finding N개 = provider 호출 N·(revise+report+gate). 단 aggregate budget/구조 상한이 이미 이를 bound. 기본 `max_revision_rounds=2`면 2개까지만(env로 상향). |
| D2=B. batch — 1 reviser 호출에 N finding | reviser 계약을 다중 finding으로 확장, 한 호출에 N개 splice. | provider 호출 절감. | reviser+splice 재작성(비중첩 다중 splice·evidence-once 교차검증), 결정성/검증 복잡. 실패 원자성 모호. 큰 재작성. |

추천 **D2=A** — 아키텍처가 이미 매 revise 뒤 re-gate하므로 "정확히 1개→최우선 1개" 완화만으로 sequential 다중 소진이 성립한다. B는 splice/계약을 크게 재작성해 §2 Simplicity에 반한다. provider 호출 비용은 구조 상한·aggregate budget이 담당.

## D3 — 다수 자격 finding 중 선택 순서

자격 함수가 revise-추천 continuity finding만 남기므로, 그중 다수일 때 순서 기준이 필요하다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **D3=A. severity desc → gate 순서(추천)** | `error` finding 먼저, 동급이면 Gate 반환 순서(안정). | 심각한 continuity부터 bounded budget 소비. 결정적(안정 정렬). | 없음(경미). |
| D3=B. gate 반환 순서 그대로 | 첫 자격 finding부터. | 가장 단순. | 심각도 무시 — budget 소진 전 경미 건부터 처리될 수 있음. |

추천 **D3=A** — error continuity를 우선 소진. 안정 정렬로 결정성 유지.

## 이번 slice 범위 / Deferred

- **이번 slice(결정적, sandbox 내 검증)**: `_eligible_revision_finding`을 "최우선 1개 선택"으로 완화(D1 범위·D3 순서 반영). 나머지 loop·reviser·report·Gate·budget·audit 계약 무변. 양방향 회귀(다수 continuity→순차 소진·자격 밖 혼재 시 자격만 선택·severity 우선·기존 단일 finding 불변·자격 0→not_eligible 유지).
- **Deferred**: D2=B batch reviser(비용 측정 후 필요 시), do_not_use/pov 자동 revise(D1=B, canon 정책 재검토 필요), `max_revision_rounds` 기본값 상향(다중 finding 흔하면 env 튜닝, live 데이터 후).
- **별도 트랙**: 12B Gate 과민 revise/판별 튜닝(compare judge J1의 Gate 판)은 이 slice와 독립.

## Follow-up considerations

- 완화 후에도 `evidence 후보 내 정확히 1회` 조건은 finding별 유지(splice 모호성 방지). 선택된 finding revise 후 candidate 텍스트가 바뀌므로 다음 라운드 gate가 새 텍스트로 재평가 — 남은 finding evidence가 여전히 1회인지 자연히 재검증된다.
- `UnchangedWritingRevision`(no_change) + `max_revision_rounds`/`max_gate_evaluations`가 무한 루프를 이미 bound.
- 선택 함수만 바뀌므로 loop `stages`/audit/aggregate budget 계약 무변(각 revise round가 기존대로 기록).
- **first-round finding 비대칭(검증 H3, 설계상 의도)**: `/writing/revise-and-gate` 진입의 **첫 revise finding은 client 제공**(request body의 `finding`)이고 relaxed selector를 거치지 않는다. selector(`_eligible_revision_finding`)는 첫 Gate 이후 while-loop의 후속 라운드에서만 다수 finding을 선택한다. 진입 계약(첫 finding = 호출자 지정)상 의도된 비대칭이며, `test_multi_finding_revise_processes_sequentially`가 client 첫 finding + re-gate 2개 경로를 관통한다.
