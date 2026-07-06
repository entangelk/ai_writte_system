# Decision brief — Phase 4 ContextPackage 완성 (§8 C / §5 B)

상태: `Resolved (2026-07-05) — D1=B, ⑤/⑧ 모두 Phase 2B 종속`
정본 연결: [`../system-contract-sot.md`](../system-contract-sot.md), [`04-agentic-search-kickoff-decisions.md`](04-agentic-search-kickoff-decisions.md) §5·§8, [`04-agentic-search.md`](04-agentic-search.md)
목적: Phase 4 착수 브리프가 추적 의무로 남긴 두 항목 — ⑧ ContextPackage를 Writing용/Analysis 비교용 모두 완성(§8 C), ⑤ `needs_review` candidate 포함(§5 B) — 을 착수 전에 확정한다. 두 항목은 각각 결정/선행 의존성이 있어 추측 구현 금지 대상이다.

## 배경 (결정이 아니라 사실)

- ContextPackage/ContextItem 계약은 이미 `status` 라벨 필드(`ContextItemStatus.CANDIDATE`/`CANONICAL`)를 열어 뒀다(`services/application/app/context_search/models.py`). 현재 모든 item은 source block/SOT 기반이라 `canonical`이다.
- `evaluate_context_gate()`는 현재 candidate 라벨 item을 **금지**한다(있으면 reject). 착수 브리프 §5 A("candidate를 canon으로 표현하지 않음")를 가장 작게 지키는 형태다.
- Phase 2A candidate는 전부 `needs_review`이며 승인/canonical 승격 경로(Phase 2B/6)가 아직 없다. canonical memory store는 존재하지 않는다(착수 브리프 §배경).
- candidate는 `analysis_candidates` Mongo collection에 있고, **vector index에는 없다**(candidate indexing은 명시적 후속, SoT 미확정 목록). 현재 검색 재료는 source block + Mongo SOT뿐이다.
- Writing용 뷰: 현재 package(macro=current/recent scene, micro=event/source quote, purpose=`writing_context`)는 Phase 5 MVP의 `continue_scene` prompt assembly 소비에 구조적으로 충분하다. `constraints`/`do_not_use`는 현재 항상 빈 tuple이다(채우는 출처 미정).
- Analysis 비교용 뷰: 착수 브리프 §8이 "analysis 비교용 확장 필드(기존 memory type/scope, status/version, 검색 이유)는 **Phase 2B 착수 브리프에서 결정**하고 그 slice가 끝나야 §8이 닫힌다"고 명시했다.

## 확정된 상위 방향 (착수 브리프)

- §5: candidate 기억은 **A 먼저 + B 후속 확장**. status 라벨 필드는 A에서 이미 열림(확장 비용 낮음).
- §8: package 경계는 **A(단일 schema + purpose literal)로 시작하되, 이후 slice에서 C(Writing용/Analysis 비교용 모두 완성)까지 도달**해야 한다.

## 결론 요약 (읽는 사람용)

- **⑧ Analysis 비교용 뷰는 이 slice에서 닫을 수 없다** — 착수 브리프가 필드 확정을 Phase 2B 착수 브리프로 위임했다. 따라서 §8 C의 Analysis 절반은 Phase 2B에 종속된 추적 항목으로 유지한다. Writing용 뷰는 이미 Phase 5 MVP에 충분하므로, "완성" 중 지금 닫을 수 있는 것은 없다(있다면 D5 constraints/do_not_use 출처 결정뿐인데 그것도 출처가 미정).
- **⑤ candidate 포함이 이 slice의 실질 작업 후보다.** 단 canonical store 부재 + Gate 금지 + 검색 경로 미정 + Writing-안전성 위험이 얽혀 있어, 아래 D1~D5 결정이 필요하다.

---

## D1. candidate 포함을 지금 할 것인가, 승인/canonical 경로가 생긴 뒤로 미룰 것인가

착수 브리프 §5는 "A→B"로 B(포함)를 계획했지만 "지금" 하는 것과 별개다. §5 옵션표는 B의 단점으로 "승인 전 후보가 Writing 근거로 흘러갈 위험, Phase 6 review 지위 미확정"을 명시했다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 지금 포함 | `needs_review` candidate를 `status="candidate"`로 ContextPackage에 넣고 Gate가 라벨 조건으로 허용 | prior-memory context를 조기 확보 | 승인/canonical 경로가 없어 미검증 추론이 Writing 근거로 흐를 위험, Gate 안전규칙을 완화해야 함 |
| B. Phase 2B/6까지 미룸 | candidate 승인/canonical 승격이 생긴 뒤 canonical만 포함(§5 C에 수렴) | Writing이 미검증 후보를 canon처럼 쓰지 않음, Gate 금지 규칙 유지 | prior-memory context가 그만큼 늦어짐 |

추천: **B(미룸).** 근거: (1) 현재 canonical store가 없어 §5 C("승인된 canonical만")와 §5 B가 사실상 "미검증 후보 vs 없음"의 선택이다. (2) `evaluate_context_gate`의 candidate 금지 규칙은 Writing AI 경계("candidate 정보는 확정 canon처럼 단정하지 않는다", `05-writing-ai.md`)를 지키는 방어선인데, canonical 경로 없이 이걸 완화하면 방어선이 사라진다. (3) Phase 2B가 candidate↔기존 기억 대조/승격을 도입하면 그때 canonical 라벨이 실제로 생겨 §5 B/C가 안전하게 닫힌다. 즉 **⑤의 안전한 완성은 Phase 2B에 자연 종속**된다.

> D1에서 A를 택하면 D2~D5를 진행한다. B를 택하면 이 brief는 "⑤/⑧ 모두 Phase 2B 종속"으로 결론나고, Phase 4는 현재가 합리적 정지점이며 다음 큰 슬라이스는 Phase 2B 착수가 된다.

## D2. (A일 때) candidate 검색 경로

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. Mongo-direct | `analysis_candidates`를 project scope로 직접 조회(need↔candidate_type 매핑), 임베딩/vector 없이 | candidate indexing 후속 결정을 안 건드림, 최소 | 유사도 랭킹 없음(recency/type 필터만) |
| B. vector index화 | candidate를 파생 vector index에 색인 후 vector 검색 | 유사도 검색 일관성 | candidate indexing(명시적 후속)을 지금 열어야 함, embedding·stale 계약 확장 |

추천: **A(Mongo-direct).** candidate indexing은 명시적 후속이고, 첫 포함은 랭킹보다 "라벨된 prior-memory를 안전하게 노출"이 목적이므로 Mongo-direct가 최소다.

## D3. (A일 때) candidate를 서빙하는 need literal

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 새 need `prior_memory` | candidate 전용 need 1종을 enum에 추가, tool은 mongo | 의미가 명확, 기존 source-block need와 분리 | 새 literal(착수 브리프 §1 "실제 서빙 가능한 literal만" 원칙엔 부합) |
| B. 기존 `event_context`에 매핑 | event candidate를 `event_context`로 흘림 | 새 literal 없음 | character/open_question candidate가 갈 곳 없음, 의미 혼선 |

추천: **A(`prior_memory` 신설).** 착수 브리프 §배경이 유보한 것은 "canonical memory 기반 need(`character_state` 등)"인데, `prior_memory`는 canonical이 아니라 명시적으로 `status="candidate"` 재료를 서빙하는 need라 의미가 다르다.

## D4. (A일 때) Context Gate 정책

현재 Gate는 candidate 라벨을 무조건 reject한다. 포함하려면 규칙을 바꿔야 한다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 라벨 강제 허용 | `status="candidate"` item을 허용하되 **반드시 라벨링·micro 전용**(macro 금지)으로 강제, canonical과 섞이지 않게 검사 | Writing이 candidate/canon을 구분해 소비 가능 | Gate 규칙·회귀 확장 |
| B. 무조건 허용 | candidate item을 canonical과 동일 취급 | 단순 | Writing-안전성 방어선 소실(채택 불가) |

추천: **A.** candidate는 micro_evidence로만, `status="candidate"` 라벨 필수, macro(scene 골격)에는 금지. Gate는 "candidate가 macro에 있으면 reject", "candidate가 라벨 없으면 reject"로 방향을 뒤집는다.

## D5. Writing용 뷰의 `constraints`/`do_not_use` 채우기 (⑧ Writing 절)

현재 두 필드는 항상 빈 tuple이다. 채우는 출처(POV/timeline constraint, do_not_use)가 SOT metadata인지, 별도 need인지, candidate 파생인지 미정이다.

| 선택지 | 설명 |
|---|---|
| A. 이 slice 범위 밖 | Phase 5 착수 브리프에서 출처와 함께 결정(빈 tuple은 MVP 소비에 문제 없음) |
| B. 지금 정의 | 출처를 지금 확정하고 populate |

추천: **A(범위 밖).** 출처가 Writing 요구에 종속되므로 Phase 5 착수 브리프에서 정한다. 현재 빈 tuple은 계약 위반이 아니다.

## ⑧ Analysis 비교용 뷰 (추적 유지)

- 착수 브리프 §8이 Phase 2B 착수 브리프로 필드 확정을 위임했다. 이 slice는 그 종속을 **명시적으로 재확인**하고 SoT 미확정 목록/HANDOFF 추적 항목을 유지한다. 여기서 필드를 추측 정의하지 않는다.

## 후속 (이 brief 범위 밖)

- ES lexical 경로(§8, 착수 전 별도 브리프).
- tool-call flat loop planner 전환(§2.1, 상류 wire 계약 해소 후).
- candidate indexing(D2 B를 나중에 택할 경우).

## Owner decisions — 2026-07-05

- **D1 = B (Phase 2B까지 미룸).** candidate 포함은 승인/canonical 경로가 생기는 Phase 2B로 미룬다. 근거: canonical store 부재 상태에서 지금 포함은 "미검증 후보 vs 없음"의 선택이고, `evaluate_context_gate`의 candidate 금지 규칙은 Writing-안전성 방어선이므로 canonical 경로 없이 완화하지 않는다. ⑤의 안전한 완성은 Phase 2B에 자연 종속된다.
- D1=B이므로 **D2/D3/D4는 열지 않는다**(candidate 검색 경로·`prior_memory` need·Gate 완화 모두 미착수). D5(constraints/do_not_use 출처)는 Phase 5 착수 브리프로.
- **결론: ⑤와 ⑧(Analysis 절) 모두 Phase 2B에 종속된다.** Phase 4는 현재 상태(Writing용 뷰가 Phase 5 MVP에 충분, candidate 미포함, Gate가 candidate 금지)가 합리적 정지점이다. §8 C 완성 의무는 Phase 2B 착수 브리프가 소유한다. 다음 큰 슬라이스는 Phase 2B 착수다.

## Phase 2B가 이어받는 항목 (추적 이관)

- ⑤ `needs_review` candidate 포함(§5 B): 검색 경로(D2), `prior_memory` need(D3), Gate 완화(D4)를 candidate 승인/canonical 승격 계약과 함께 결정한다.
- ⑧ Analysis 비교용 뷰(§8 C): 확장 필드(기존 memory type/scope, status/version, 검색 이유)를 Phase 2B 착수 브리프에서 확정한다.
