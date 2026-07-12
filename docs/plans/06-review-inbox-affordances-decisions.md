# 착수 결정 브리프 — Phase 6 Review Inbox 액션 어포던스

상태: `Resolved` (오너 결정 D1=자격 주석형 descriptor·D2=candidate+conflict+gate finding 전부·D3=list+detail 둘 다)
관련: Phase 6 `plans/06-review-ui.md` §39 화면 단위·§53 산출물·SoT §434 Phase 6·Review Inbox v1.6.64·review action(confirm/reject v1.6.61·merge/split v1.6.63·gate resolve/dismiss v1.6.65·edit v1.6.66)

## Decision needed

Review Inbox(v1.6.64)는 candidate payload·conflict·source pointer·diff를 노출하지만 **각 항목에 어떤 review action이 가능한지(어포던스)를 선언하지 않는다**. 이미 4개 write 계약(confirm/reject/edit·merge/split·resolve/dismiss)이 존재하고 각자 자격 규칙(merge=character+matched canonical, split=character, gate=open일 때만)이 있는데, 프론트가 이를 추론하려면 백엔드 도메인 규칙을 재구현해야 한다. 어포던스를 백엔드가 선언해 단일 계약으로 묶는다.

## Options table (검토)

| 결정 | 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|---|
| D1 서술자 형태 | **자격 주석형 `{action,eligible,reason}`**(채택) | 가용/불가 + 불가 이유 | 프론트가 disabled+툴팁 렌더, 자격 규칙(character/matched)이 계약에 실림 | 필드 3개, reason 문자열 관리 |
| D1 | 이름 배열만 | 가용 action 이름만 나열 | 최소 | 프론트가 "왜 불가"를 모름 → 자격 규칙 재구현 유발 |
| D2 포함 범위 | **candidate+conflict+gate finding 전부**(채택) | inbox 3섹션 모두 | 프론트 한 계약으로 3섹션 구동, 일관 | gate finding payload 확장(전용 API에도 반영) |
| D2 | candidate+conflict만 | gate 제외 | 범위 소 | gate 어포던스 후속, 3섹션 불일치 |
| D3 노출 위치 | **list+detail 둘 다**(채택) | list 행에도 요약 action set | 프론트 목록에서 바로 버튼 렌더 | list payload 증가(read-time 재계산, 비용 소) |
| D3 | detail만 | detail에서만 action | list lean | 목록 뷰가 action affordance 없음 |

## Recommendation + reason (채택 근거)

로컬 1인 프로젝트지만 Phase 6의 목적이 "프론트가 review 루프를 구동"이므로, **어포던스가 자격 규칙까지 실어야**(D1 주석형) 프론트가 백엔드 도메인 로직을 재구현하지 않는다. 이미 4개 write가 다 있으니 **3섹션 전부 일관**(D2)해야 프론트가 한 계약으로 구동한다. **list+detail 둘 다**(D3)는 read-time 재계산이라 비용이 작고 목록 뷰의 즉시 액션을 가능케 한다.

## 자격 규칙 (구현이 지켜야 할 authority — reconciliation.py:69-74, gate_findings v1.6.65)

- **candidate**(inbox는 needs_review·미승격만 노출): `confirm`/`reject`/`edit` **항상 eligible**.
- **conflict**(open review_queue entry):
  - `merge`: eligible ⟺ candidate_type=character **AND** matched canonical 존재. 불가 이유="merge/split is character-only"(비-character) 또는 "merge requires a matched canonical memory"(character·matched 없음).
  - `split`: eligible ⟺ candidate_type=character. 불가 이유="merge/split is character-only".
- **gate finding**(inbox는 open만 노출): `resolve`/`dismiss` eligible ⟺ status=open. 불가 이유="gate finding is already terminal".
- **권위는 read-time 재계산**(어포던스는 선언만, write 엔드포인트가 실제 authority — 어포던스가 eligible=true여도 write는 자기 검증을 그대로 수행).
- **machine contract = `action`(literal) + `eligible`(bool)**. `reason`은 **사람이 읽는 display text**로, 안정 계약 literal이 아니다 — 소비자는 `reason` 문자열을 pattern-match하지 말고 `eligible`/`action`으로 분기해야 한다. localization/문구 변경은 계약 bump 없이 가능(현재 문구는 코드 리터럴, 검증 review_inbox_affordances.md H2).

## Follow-up considerations (열어둘 문)

- action별 href/route(HATEOAS)는 넣지 않음 — 프론트가 이름→경로 매핑. 후속에 route 계약이 필요해지면 descriptor에 `href` 추가로 확장 가능(현재 additive 여지).
- merge 자격을 `conflict.matched_memory`(resolved 실체) 기준으로 판정 — matched_memory_id는 있으나 memory가 유실된 경우 merge가 실제 실패하므로 eligible=false가 더 정직(inbox detail이 이미 resolved matched_memory만 노출하는 것과 정합).

## Deferred / out of scope

부분 승인/부분 retry·merge/split를 event/open_question로 일반화·상태 변경 invalidate 범위·frontend(framework 미확정). 어포던스는 **선언만** 추가하며 write 계약·상태 모델·색인은 무변.

## 경계 매트릭스 (구현 시 회귀 잠금)

| # | 분기 | 방향 | 잠금 대상 |
|---|---|---|---|
| 1 | candidate actions = confirm/reject/edit 전부 eligible | under-strict | 누락 시 실패 |
| 2 | conflict merge: character+matched → eligible=true, reason=None | under-strict | 자격을 잘못 막으면 실패 |
| 3 | conflict merge: character·matched 없음 → eligible=false, reason="matched canonical" | over-strict | 잘못 eligible 시 실패 |
| 4 | conflict merge/split: 비-character → 둘 다 eligible=false, reason="character-only" | over-strict | 잘못 eligible 시 실패 |
| 5 | conflict split: character → eligible=true(matched 불요) | under/over | matched 요구로 잘못 막으면 실패 |
| 6 | gate finding: open → resolve/dismiss eligible=true | under-strict | 누락 시 실패 |
| 7 | gate finding: terminal(resolved/dismissed) → eligible=false, reason | over-strict | 잘못 eligible 시 실패 |
| 8 | list item에 candidate actions 포함(detail 전용 아님) | under-strict | list 누락 시 실패 |
| 9 | detail: item candidate actions + 각 conflict actions | under-strict | conflict actions 누락 시 실패 |
| 10 | gate finding actions가 review-inbox·/gate-findings 양쪽 payload에 포함 | under-strict | 공유 serializer 누락 시 실패 |
| 11 | 어포던스가 write 계약·상태 모델 무변(선언만) | over-strict | 상태 변경 side effect 발생 시 실패 |

## 성격

read-only 어포던스 계산 + 기존 payload에 `actions` 필드 additive. 신규 도메인 write 없음. 순수 함수 3종(`candidate_affordances`/`conflict_affordances`/`gate_finding_affordances`) + `ActionAffordance` descriptor + serializer. 공개 응답 envelope 확장(list item·detail item·conflict·gate finding에 `actions`) → **minor bump(v1.6.67)**. 부분 승인·merge/split 일반화·frontend는 계속 미확정.
