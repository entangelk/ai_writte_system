# Decision brief — 미채택 Writing candidate 영속

상태: `완료 (2026-07-20) — D0=B / D1=B / D2=A 구현·독립 검증 합격, 보존/만료 정책은 SoT v1.7.20으로 정본 승격`
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

## 보존/만료 정책 — **정본 승격 완료 (2026-07-20, SoT v1.7.20)**

D1=B(이력)가 요구하는 보존/만료 정책을 오너 위임에 따라 구현자가 잠정 결정했고, **오너 승인으로 정본 계약이 됐다**. 정본 위치는 [`../system-contract-sot.md`](../system-contract-sot.md) v1.7.20의 **Source of Truth** 절(`writing_drafts_scratch` 계약)이며, 아래는 그 계약의 유래와 근거를 남기는 기록이다. **충돌 시 SoT가 우선한다.**

> 승격 대상은 **"상한 20"이라는 숫자가 아니라 "기본 20 + 운영자 조정 가능"이라는 계약**이다. 오너 근거: "실제로 어떻게 될지는 사람에 따라 달라서" — 숫자를 코드 상수로 굳히면 dogfood에서 승격 근거를 만드는 관찰 자체가 코드 수정을 요구하게 된다. 따라서 dogfood에서 실사용 상한을 관찰하면 **기본값만** 조정하면 되고, 계약 자체는 다시 열지 않는다.

- **키**: scratch entry는 `(project_id, draft_id)`로 묶는다. `draft_id`는 generate 요청의 `current_position.draft_id`에서 온다. `current_position`이 없으면 scratch를 남기지 않는다(키 없음 = 안전망 대상 아님).
- **append(이력)**: generate 성공마다 candidate 1건을 append한다.
- **per-draft 상한 = 기본 20건**(최신 우선, 초과분은 오래된 것부터 삭제). D1=B의 무한 증가를 막는 잠정 상한.
  - **환경변수 `WRITING_SCRATCH_MAX_PER_DRAFT`로 조정 가능**(오너 결정 2026-07-20): "몇 건이 쓸모 있는지는 사람마다 다르다"는 이유로 이 숫자를 코드 상수로 굳히지 않는다. compose에 `${WRITING_SCRATCH_MAX_PER_DRAFT:-20}`로 노출한다(`WRITING_LOOP_MAX_*` 선례와 동형).
  - **1 미만은 거부한다**(구성 오류 시 기동 실패). 0/음수를 허용하면 save 직후 스스로를 trim해 **안전망이 지켜야 할 초안을 조용히 삭제**하게 되므로, 조용한 데이터 손실 대신 시끄러운 실패를 택했다.
- **accept 성공 시 즉시 삭제**: 해당 draft의 scratch 전체를 정리한다(사용자가 정본을 확정했으므로 미채택 이력은 무의미). **"성공"의 기준은 정본 version이 저장됐는가**이며, 따라서 다음 두 경로가 모두 정리 대상이다 — (1) 정상 200 accept, (2) **analysis job만 실패한 502 partial**(version은 저장됨, `accepted=true`+`saved` 존재). 반대로 **비-PASS Gate 결과(`accepted=false`, 저장된 것 없음)는 정리하지 않는다** — 사용자에게 아직 복구할 초안이 남아 있으므로 여기서 지우면 안전망이 오히려 초안을 죽인다. 세 분기 모두 회귀로 잠겨 있다(2026-07-20 검증 H-2).
- **명시적 버리기**: 복구 UI의 "버리기"는 draft scratch 전체를 삭제한다.
- **시간 기반 자동 만료 없음**(P5=A "자동 삭제 없음" 정신). per-draft 상한과 accept/명시 삭제만이 수렴 수단.
- **best-effort 격리**: generate/accept의 scratch 쓰기·삭제 실패는 본 흐름(생성/채택)을 실패시키지 않는다(안전망이 정본 경로를 막지 않는다).

## Follow-up considerations (열어둘 문)

- `writing_drafts_scratch` 스키마는 나중 Phase 7 `conversation_turn`으로 흡수/승격될 수 있게, candidate 식별(`request_id`/`intent`/`next_unit`)을 그대로 싣되 대화 필드(`content_channel` 등)는 지금 넣지 않는다(추측 금지).
  - **구현 시 확정(2026-07-20, 검증 H-3)**: `intent`·`next_unit`은 **accept 경계에서만 결정되고 generate 시점에는 존재하지 않는다**(`/writing/generate` 요청 body에 두 필드가 없다). 따라서 실제 스키마는 `request_id`만 실값으로 싣고, **`intent`는 nullable seam으로 예약**(Phase 7 흡수 시 스키마 변경 없이 채울 수 있게), **`next_unit`은 제외**했다 — 항상 `None`인 구조체 필드를 미리 만드는 것은 Simplicity First에 어긋나고, 필요해지는 시점(intent가 실제로 기록되는 Phase 7)에 `intent`와 함께 추가하는 편이 응집도가 높기 때문이다. 즉 seam은 `intent` 한 축으로 대표시키고 `next_unit`은 그때 동반 추가한다.
- accept 경로(`writing/accept.py`)가 성공 시 scratch를 삭제하는 훅만 추가하고, accept의 원자성·idempotency 계약은 건드리지 않는다.
- 프론트는 draft editor 진입 시 scratch가 있으면 "이어쓰던 미채택 초안이 있습니다 — 복구/버리기"를 제안하는 표면만 얹는다.

## Deferred / out of scope (이 슬라이스에서 안 하는 것)

- Phase 7 P1 conversation/conversation_turn 1급 엔티티, revise/ideate task mode, directive 감독(P2~P5) — GATE-1 뒤.
- 미채택 후보 **이력/비교**(D1=B) 및 대화 로그.
- scratch 자동 만료/retention 정책(별도 운영 과제).
- saved publication manifest 정본(별도 Deferred 항목, 이 브리프와 무관).

## Owner decisions — 확정 (2026-07-20)

- **D0 = B** (최소 복구를 pre-Phase-7로). **단, 프레이밍 전환을 동반한다**: 오너는 이 결정을 "게이트 우선 개발"의 종료로 규정했다 — 지금부터는 **게이트(Writing Gate) ↔ UI/UX를 동반 정합**하는 단계이고, 그래서 **SoT 변경 작업이 잦아지는 구간**으로 들어간다. D0=C(Phase 7 P1 정식 착수)를 **각하한 것이 아니라 이 슬라이스가 향해 가는 방향으로 명시적으로 염두에 둔다**("B로 하되 C도 염두"). 따라서 B는 "Phase 7과 무관한 일회성 안전망"이 아니라 **Phase 7 계층으로 승격될 것을 전제로 한 좁은 첫 걸음**이다.

- **D1 = B** (draft별 미채택 candidate 이력). 브리프의 추천(A)과 다르게 오너는 B를 택했다 — **개발하면서 후속 정책(이력·보존)까지 함께 만드는 것**이 이 구간의 성격이기 때문이다(D0의 "C도 염두"와 정합: 이력은 Phase 7 `conversation_turn`으로 자연 흡수된다). B가 요구하는 "보존/만료 정책 필요"는 회피 대상이 아니라 이 슬라이스가 떠안는 작업이다(D2 참조).

- **D2 = A** (별도 collection `writing_drafts_scratch`, 정본 무변). 오너가 A/B/C 저장 위치를 직접 지정하지는 않았으나, **D1=B(이력)는 서버측 영속이 필수라 B(loop_audit 재사용, 의미 충돌)·C(localStorage, 이력·기기간 이동 불가)와 양립하지 않는다 → A만 정합적**이므로 A로 확정한다.
  - **보존/만료 정책**: 오너가 **구현자(Claude) 재량으로 잠정 정책을 정하고 테스트**하도록 위임했고, 그 결과를 **2026-07-20 오너 승인으로 SoT v1.7.20에 정본 승격**했다. 정본은 SoT의 Source of Truth 절이며 아래 절은 유래 기록이다.
