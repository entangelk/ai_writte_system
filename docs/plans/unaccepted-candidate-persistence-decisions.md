# Decision brief — 미채택 Writing candidate 영속

상태: `Draft — 오너 결정 대기 (구현 미착수)`
정본 연결: [`../system-contract-sot.md`](../system-contract-sot.md), [`07-conversational-authoring.md`](07-conversational-authoring.md), [`product-readiness-backlog.md`](product-readiness-backlog.md), [`writing-workspace-v2-w0-contract.md`](writing-workspace-v2-w0-contract.md)
작성: 2026-07-19 (다음 작업 때 오너가 결정 확정)

> 이 문서는 **제안 브리프**다. 아래 "Owner decisions" 섹션은 비어 있으며, 다음 작업 세션에서 오너가 각 결정을 채운 뒤에만 구현을 착수한다.

## Decision needed

지금 미채택 Writing candidate(생성했지만 accept하지 않은 초안)를 영속화할지, 한다면 어떤 shape로 할지를 확정한다 — 이 항목이 **Phase 7 P1의 영역이고 Phase 7은 GATE-1로 진입이 게이팅**되므로, "지금 해도 되는지"부터가 오너 결정이다.

## 왜 지금 추측 구현하면 안 되는가 (계약 충돌 선surface)

CLAUDE.md "기록된 설계 방향과 충돌하면 먼저 확인" 규칙에 따라 다음을 명시한다.

- **미채택 산출 영속 = Phase 7 P1**. `07-conversational-authoring.md` §4 P1이 "미채택 산출 별도 1급 여부(검토 D)"를 P1 착수 브리프 대상으로 명시하고, §3 D2가 "3계층 영속 = `draft_version` ⟂ **미채택 AI 산출(low-stakes)** ⟂ `conversation`/`conversation_turn`"으로 이미 계층 설계를 잠갔다.
- **Phase 7 진입은 GATE-1로 게이팅**. `product-readiness-backlog.md` GATE-1: "UX-1 완료 + QUAL-1 2주 검토 완료 → dogfood에서 반복 재현된 문제와 Phase 7 P1~P5를 대조해 가치가 입증된 첫 slice만 선택". HANDOFF Active Decisions: "**UX-1+QUAL-1 전 Phase 7 착수 금지**가 기본 진입 게이트다."
- **현재 상태**: dogfood 미착수(오너 "어느정도 완성되면 시작"), QUAL-1 미충족. 즉 GATE-1 미충족.

따라서 이 브리프의 **첫 결정(D0)은 게이트 질문**이다: 최소 복구 기능이 "Phase 7 진입"으로 GATE-1에 막히는가, 아니면 Phase 7과 무관한 pre-dogfood UX 안전망인가.

## 현재 동작 (grounding)

- generate → Gate → accept 흐름에서 candidate는 **accept 전까지 순수 in-memory**다(`WritingCandidate`, `writing/models.py`). accept 시에만 새 `draft_version`으로 영속된다.
- 유일한 기존 candidate 영속은 **opt-in loop audit**(`writing/loop_audit.py`, `persist_audit`/env 기본 off)로, revise-and-gate bounded loop의 final candidate text만 감사 목적으로 남긴다 — 일반 generate candidate의 복구 경로가 아니다.
- 결과: 사용자가 이어쓰기를 생성하고 accept하지 않은 채 새로고침/이탈하면 그 초안은 **소실**된다. 이것이 이 기능이 메우려는 gap이다.

## D0 — 게이트: 지금 하는가

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. Phase 7까지 미룬다 | 아무것도 안 하고 GATE-1(dogfood+QUAL-1) 뒤 Phase 7 P1로 통합 설계 | 계약·게이트 완전 준수, 계층/보존/대화주입을 P1에서 한 번에 일관 설계 | 그때까지 미채택 초안 소실 UX가 dogfood를 오염(초안 잃는 불편이 dogfood 피드백에 섞임) |
| B. 최소 복구만 pre-Phase-7로 | Phase 7 P1의 conversation/turn·directive는 열지 않고, "마지막 미채택 초안 복구"만 low-stakes 안전망으로 지금 구현 | dogfood 품질↑(초안 안 잃음), Phase 7 계층(D2 low-stakes tier)과 정합되게 좁게 시작 | Phase 7 P1의 일부를 먼저 건드림 — 오너가 "이건 Phase 7 진입"으로 볼 여지, 나중 P1과 중복/재설계 위험 |
| C. Phase 7 P1 착수 | 지금 conversation/turn 1급 엔티티부터 정식 착수 | 한 번에 정식 | **GATE-1 정면 위반**(dogfood 근거 없이 Phase 7 진입), 범위 과다 |

**추천: B (조건부).** 단, 오너가 "B는 Phase 7 진입이 아니라 pre-dogfood UX 안전망"으로 **명시 승인**할 때만. 근거: (1) 초안 소실은 dogfood를 시작하기도 전에 신뢰를 깎는 기본 UX 결손이다. (2) Phase 7 D2가 이미 "미채택 AI 산출 = low-stakes 별도 tier"로 계층을 정해 두었으므로, 그 tier를 좁게(마지막 1건 복구) 먼저 채우는 것은 P1의 conversation/directive 설계를 선점하지 않는다. (3) 로컬 1인 프로젝트 단계라 계약 표면을 최소로 유지할 수 있다. 오너가 "게이트 우선"을 택하면 **A**가 정답이다 — 이 판단은 오너 몫이다.

## D1 — shape (D0=B일 때만)

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 마지막 미채택 candidate 1건/draft | `(project_id, draft_id)`당 최신 미채택 candidate만 upsert 저장(다음 생성이 덮어씀), accept/이탈 시 정리 | 최소 표면, "새로고침해도 방금 초안 남아있음"이라는 실제 니즈에 정확히 대응 | 여러 후보 비교/이력은 불가(그건 Phase 7) |
| B. draft별 미채택 candidate 이력 | 생성 턴마다 append, 목록/선택 | 후보 비교 가능 | conversation_turn과 사실상 겹침 → Phase 7 P1 영역 침범, 보존/만료 정책 필요 |
| C. conversation_turn 겸용 | Phase 7 스키마를 미리 채택 | 나중 재설계 0 | D0=C와 동일한 게이트 위반 |

**추천: A.** "잃지 않기"라는 핵심 가치를 최소로 충족하고 Phase 7 P1(후보 이력·대화)과 명확히 분리된다. B/C는 D0의 게이트 판단을 사실상 뒤집으므로 D0=B와 모순.

## D2 — 저장 위치·보존 (D1=A일 때)

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. Core SOT 밖 별도 collection `writing_drafts_scratch` | 정본(version/snapshot) 오염 없이 low-stakes 임시 저장, accept 시 삭제 | 정본 계약 무변, D2 "low-stakes tier" 정합 | 새 collection 1개 |
| B. 기존 loop_audit 재사용 | 이미 있는 감사 저장에 얹기 | 신규 collection 0 | 감사(append-only immutable)와 복구(mutable upsert/삭제)의 의미 충돌, 오염 |
| C. 프론트 localStorage만 | 서버 무변, 브라우저에 초안 보관 | 백엔드 0 | 기기/브라우저 간 이동 불가, 정본 경계 밖이라 신뢰성↓, 서버 계약 부재 |

**추천: A.** 정본(Core SOT)은 건드리지 않되 서버 신뢰성은 확보한다. 보존: accept 시 즉시 삭제, 그 외 자동 만료는 두지 않되(P5=A "자동 삭제 없음" 정신) 후속 retention 과제로 남긴다. **C(localStorage)는 서버 왕복 없이 가장 싸지만**, "잃지 않기"의 신뢰를 브라우저에 위임하는 것이라 D2 low-stakes tier의 서버 계약과 어긋난다 — 오너가 "정말 최소"를 원하면 C도 후보다.

## Follow-up considerations (열어둘 문)

- `writing_drafts_scratch` 스키마는 나중 Phase 7 `conversation_turn`으로 흡수/승격될 수 있게, candidate 식별(`request_id`/`intent`/`next_unit`)을 그대로 싣되 대화 필드(`content_channel` 등)는 지금 넣지 않는다(추측 금지).
- accept 경로(`writing/accept.py`)가 성공 시 scratch를 삭제하는 훅만 추가하고, accept의 원자성·idempotency 계약은 건드리지 않는다.
- 프론트는 draft editor 진입 시 scratch가 있으면 "이어쓰던 미채택 초안이 있습니다 — 복구/버리기"를 제안하는 표면만 얹는다.

## Deferred / out of scope (이 슬라이스에서 안 하는 것)

- Phase 7 P1 conversation/conversation_turn 1급 엔티티, revise/ideate task mode, directive 감독(P2~P5) — GATE-1 뒤.
- 미채택 후보 **이력/비교**(D1=B) 및 대화 로그.
- scratch 자동 만료/retention 정책(별도 운영 과제).
- saved publication manifest 정본(별도 Deferred 항목, 이 브리프와 무관).

## Owner decisions — (다음 세션에서 채움)

- **D0**: _대기_
- **D1** (D0=B일 때): _대기_
- **D2** (D1=A일 때): _대기_
