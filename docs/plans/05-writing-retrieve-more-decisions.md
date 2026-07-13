# 착수 결정 브리프 — Phase 5.8 Writing `retrieve_more` 1회 lifecycle

상태: `Resolved — T1=B, T2=B, T3=E, T4=E, T5=B, T6=B, T7=A first→B, T8=A first→B`

관련 정본: SoT v1.6.69 Writing Gate, v1.6.75 revise→report→Gate 합성, `05-writing-gate-decisions.md`, `05-writing-revise-report-gate-decisions.md`, Phase 4 `ContextSearchRequest`

## Decision needed

Writing Gate의 `retrieve_more` 결과를 실제 재검색으로 연결할 때 query/need 생성, 새 ContextPackage 경계, report·Gate 재실행 순서와 public partial envelope를 확정해야 한다. 현재 정본은 “canonical 근거 부족”이라는 decision 의미와 재검색 후속만 잠갔으며, 이 선택들은 기존 계약에서 하나로 도출되지 않는다.

## Owner decisions — 2026-07-13

- **T1=B, T2=B**: 기존 `/writing/revise-and-gate` 내부에서 첫 GateResult의 `retrieve_more` findings를 소비한다. 비영속 이전 ContextPackage를 같은 호출 안에서 유지해야 T5 merge가 가능하므로 독립 endpoint는 만들지 않는다.
- **T3=E, T4=E**: Writing Gate schema를 키우지 않고 별도 follow-up retrieval planner LLM이 첫 GateResult와 candidate/instruction을 보고 `query + needs`를 함께 선택한다. 기존 Phase 4 planner는 선택된 needs 안에서 step/query/tool을 계획한다. `current_position`이 없으면 position-dependent `current_scene|recent_scenes`는 허용 집합에서 제외한다.
- **T5=B**: 이전 package와 targeted delta package를 Application이 merge하고 전체 context budget을 다시 적용한다. targeted delta를 먼저 배치해 새 근거가 기존 full package에 굶지 않게 하며, 두 package를 Gate에 병렬 정본으로 주지 않는다.
- **T6=B**: candidate text가 변하지 않으므로 v1.6.75의 최신 report를 보존하고 merged package로 Gate만 재평가한다. report는 context-relative로 달라질 수 있다는 tradeoff를 수용하되, 최종 Gate가 merged package를 직접 본다.
- **T7=A first→B**: 성공은 기존 `{candidate,gate}`를 유지하고 최종 Gate만 노출한다. 후속 다회 합성에서 `stages`를 additive로 연다. 첫 Gate 뒤 retrieval 실패는 `{candidate,gate:<첫 Gate>,retrieval_error}` partial envelope로 이미 생긴 artifact를 보존한다.
- **T8=A first→B**: Application의 `max_retrieval_rounds=1`로 첫 Gate 뒤 targeted retrieval+Gate 재평가를 최대 한 번 허용한다. 두 번째 Gate도 `retrieve_more`면 200 정상 outcome으로 종료하며, 1보다 큰 값은 G8 budget/policy 결정 뒤 연다.

## 현재 확정된 경계

- Writing Gate의 decision은 `pass|revise|retrieve_more|needs_user_review|block`이며, `retrieve_more`는 판정에 필요한 canonical 근거가 부족한 정상 outcome이다.
- Gate finding은 `type|severity|message|evidence|recommended_decision`을 가지며, `evidence`는 candidate text의 exact excerpt다. 별도 검색 query/need 필드는 아직 없다.
- 기존 continue-scene 검색은 `current_scene|recent_scenes|canonical_memory`와 `query`를 사용한다. Phase 4에는 추가 canonical 검색 need인 `event_context|source_quote`가 이미 존재한다.
- v1.6.75 합성은 같은 ContextPackage에서 revise→report→Gate를 실행한다. 명시적 `retrieve_more`만 새 package와 DB·메모리 재접근을 열 수 있다.
- candidate/report/GateRun/ContextPackage는 아직 비영속이다. 모델은 호출/응답에 집중하고 Application이 검색·합성 순서·검증·오류 envelope·반복 한도를 소유한다.
- 이 결정은 G8 B의 일반 내부 loop가 아니라, `retrieve_more` 한 건을 소비하는 bounded 1회 lifecycle만 대상으로 한다.

## Options table

### T1 — public API 경계

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 별도 `/writing/retrieve-and-gate` | candidate와 `retrieve_more` finding을 받아 재검색→report→Gate를 한 번 실행한다 | 기존 endpoint 무변, retrieval slice를 독립 회귀 가능 | 비영속 이전 package가 없어 T5 merge 불가 |
| B. `/writing/revise-and-gate`가 Gate의 `retrieve_more`를 최대 1회 실행 | 기존 합성 요청 안에서 이전 package를 유지해 targeted delta와 merge한다 | client 왕복 없음, T5 merge 가능 | 호출 수·latency·partial 실패 계약 확장 |
| C. `/writing/gate?retrieve=true` | Gate endpoint에 opt-in flag를 둔다 | 경로 재사용 | 한 endpoint가 판정-only/재검색 합성 두 envelope와 dependency를 가짐 |

채택: **B**. T5=B가 비영속 이전 package를 요구하므로 같은 Application 호출 안에서 이어간다. 최대 1회로 G8 일반 loop와 경계를 둔다.

### T2 — 실행 가능한 입력

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. candidate + 단일 `retrieve_more` finding public 입력 | revise endpoint의 단일 finding 입력과 대칭이다 | trigger와 근거가 명시적 | 비영속 이전 GateResult와 package를 client가 재구성해야 함 |
| B. 같은 호출의 첫 GateResult 내부 소비 | decision이 `retrieve_more`일 때 그 결과의 모든 retrieve_more finding을 planner에 전달한다 | 서버가 방금 만든 결과라 identity 신뢰 가능, 다중 부족 근거 보존 | T1=B 내부 합성에 종속 |
| C. candidate + 자유 query만 | 검색 입력이 단순하다 | Gate 없이도 호출 가능 | `retrieve_more` lifecycle이라는 실행 자격이 사라짐 |

채택: **B**. public 재제출 없이 같은 호출에서 생성된 GateResult를 소비한다. planner에는 `recommended_decision=retrieve_more` findings만 전달한다.

### T3 — follow-up query 소유권

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. Application 결정적 조립 + client override | 명시 query가 있으면 사용하고, 없으면 instruction·finding message·exact evidence를 고정 포맷으로 결합한다 | 새 LLM 호출 없이 재현 가능, 기존 `query` 관례 유지 | 자연어 조립 품질을 fixture로 잠가야 함 |
| B. Gate schema에 `search_query` 추가 | Gate가 부족 판단과 검색어를 함께 낸다 | 의도 밀착 | 기존 Gate public schema/prompt/parser migration 필요 |
| C. 별도 query-writer LLM | finding에서 검색 query를 생성한다 | query 품질 확장 가능 | provider 호출·오류·budget이 늘고 첫 slice에 과도함 |
| D. client query 필수 | 서버는 query를 만들지 않는다 | 서버 계약 최소 | 자동 action 연결이 아니며 client가 Gate 문장을 해석해야 함 |
| E. follow-up retrieval planner가 query+needs 동시 선택 | candidate/instruction/첫 Gate findings와 허용 needs를 받아 strict JSON으로 둘을 함께 출력한다 | query와 검색 범위가 한 판단에서 정합, 로컬 호출 비용 허용 | 새 LLM 단계·parser·repair·오류 taxonomy 필요 |

채택: **E**. query와 needs는 서로 의존하므로 한 follow-up planner가 함께 결정한다. 이 planner는 판정 Gate가 아니라 검색 입력 선택기다.

### T4 — 재검색 need 집합

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. canonical 확장 고정 집합 | `current_scene|recent_scenes|event_context|source_quote|canonical_memory`를 새 요청에 사용한다 | 기존 검색보다 실제 범위를 넓히며 candidate 지식을 정본처럼 쓰지 않음 | finding별 선택 최적화는 없음 |
| B. 기존 continue-scene 3종 재실행 | `current_scene|recent_scenes|canonical_memory`만 다시 조회한다 | 변경 최소 | 같은 query/need 반복이면 새 근거가 늘지 않을 가능성이 큼 |
| C. client가 needs 제출 | Phase 4 literal을 그대로 선택한다 | 유연 | 권위/누락 검증을 client에 전가, public surface 확대 |
| D. Gate가 needs를 구조화 출력 | 부족 종류에 맞춰 동적 선택한다 | 장기적으로 정밀 | T3 B와 함께 Gate schema migration 필요 |
| E. 별도 follow-up retrieval planner가 허용 집합에서 선택 | 첫 Gate findings를 보고 필요한 canonical needs만 고른다 | 불필요한 3종/5종 전수 재실행 방지, Gate schema 무변 | planner 호출 1회 추가 |

채택: **E**. 기본 허용 집합은 `current_scene|recent_scenes|event_context|source_quote|canonical_memory`이며 하나 이상을 골라야 한다. 단, `current_position`이 없으면 Phase 4 position 계약에 따라 `current_scene|recent_scenes`를 제외한 3종만 허용한다. `candidate_memory`는 canonical 근거 부족 해소 수단에서 제외한다.

### T5 — ContextPackage lifecycle

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. fresh package로 전체 교체 | 확장 needs/query로 package를 한 번 새로 빌드하고 이후 단계가 같은 새 객체를 공유한다 | 중복 merge 규칙 없이 하나의 재현 가능한 grounding | 이전 package의 선택 결과는 보존하지 않음 |
| B. 이전 package와 새 결과 merge | 기존 근거를 유지하며 추가 hit만 합친다 | 정보 손실 최소 | 이전 package 입력/pointer와 dedup·budget·trace merge 계약 필요 |
| C. 추가 검색 결과만 Gate에 별도 첨부 | package는 유지하고 delta를 병렬 전달한다 | provenance 분리 | Gate/report prompt에 두 context 정본이 생김 |

채택: **B**. T1=B로 이전 package가 같은 호출 안에 존재한다. Application이 item identity dedup과 전체 budget 재적용을 소유하고 merged package 하나만 downstream에 전달한다.

### T6 — 재검색 뒤 실행 순서

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. search→report refresh→Gate | candidate text는 유지하고 새 package로 advisory report와 Gate를 모두 다시 계산한다 | v1.6.75의 “최신 report를 Gate에 전달” 원칙 유지 | report LLM 비용/실패 단계 존재 |
| B. search→Gate, 기존/빈 report 유지 | 근거 부족만 재판정한다 | 호출 1회 절약 | package가 바뀌었는데 report는 stale하거나 비어 있음 |
| C. search→revise→report→Gate | 새 근거로 바로 prose도 변경한다 | 한 번에 수정 가능 | `retrieve_more`와 `revise`를 합쳐 evidence/수정 정책과 G8 loop를 선점 |
| D. search-only | 새 package만 반환하고 Gate는 client가 별도 호출한다 | 가장 작은 orchestration | ContextPackage public serializer/identity를 새로 열어야 함 |

채택: **B**. candidate text는 그대로이고 v1.6.75 report가 이미 존재하므로 report provider를 다시 호출하지 않는다. report가 package 입력에도 영향받는다는 한계는 수용하며 최종 Gate가 merged package를 직접 평가한다.

### T7 — 결과·오류 envelope

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. v1.6.75 shape 우선 유지 | 성공 `{candidate,gate}`에 최종 Gate만 둔다. 첫 Gate 뒤 retrieval 실패는 `{candidate,gate:<첫 Gate>,retrieval_error}` 400/502/503/504로 보존한다 | 기존 성공 client 처리 유지, 이미 생긴 artifact 유실 없음 | 중간 단계는 성공 응답에 보이지 않음 |
| B. 모든 단계에 `retrieval`/`stages` 추가 | query/needs/trace/status를 응답에 노출한다 | 관측성 우수 | R5에서 미룬 stage schema·trace 공개·retention을 선행 결정해야 함 |
| C. 모든 실패를 200 stage status로 반환 | candidate 보존과 단계 표시 단순 | transport/provider 실패를 성공으로 오인 가능 |

채택: **A first→B**. 현재 성공 shape를 유지하고, 다회 loop/persistence를 열 때 `stages`를 additive로 추가한다. retrieval partial error type은 `invalid_retrieval_plan|retrieval_planner_error|context_*` 계열을 구분한다.

### T8 — 반복 종료·identity·side effect

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. `max_retrieval_rounds=1` | 첫 Gate 뒤 planner+targeted search+Gate를 최대 한 번 수행하고 항상 종료한다 | bounded, G8 정책/budget과 분리 | client가 후속 행동 결정 |
| B. `retrieve_more`가 사라질 때까지 재검색 | 자동 완결성 | 중복 query, 최대 반복·token/time budget·사람 확인 정책 필요 |
| C. 재검색 뒤 `revise`만 한 번 자동 처리 | 일부 non-pass 자동 해소 | decision별 비대칭 loop와 새 partial 단계 발생 |

채택: **A first→B**. 같은 `request_id`와 비영속 candidate(`candidate_id=null`)를 유지한다. 현재 상한은 1이고 1보다 큰 반복은 G8 정책·전체 budget 뒤 연다.

## Recommendation + reason

채택 묶음은 **T1=B, T2=B, T3=E, T4=E, T5=B, T6=B, T7=A first→B, T8=A first→B**다. 별도 follow-up retrieval planner가 첫 Gate의 부족 근거에서 필요한 query와 canonical needs만 선택하므로 무조건 3종/5종 재실행을 피한다. 같은 Application 호출이 이전 package와 targeted delta를 merge하고, candidate/report는 유지한 채 merged package로 Gate만 한 번 재평가한다. 현재 성공 envelope와 bounded 상한 1을 보존하면서 stage 관측성과 다회 반복 가능성은 열어둔다.

## Follow-up considerations

- 실 retrieval fixture에서 follow-up planner의 query/needs 선택과 `event_context|source_quote` hit 기여도를 측정해 Gate schema에 같은 필드를 중복 추가할 필요가 있는지 판단한다.
- persisted ContextPackage/GateRun이 생기면 이전 package id, 새 package id, trigger finding id와 query/needs를 감사 trail로 연결한다.
- G8 B는 새 Gate decision이 `revise`/`retrieve_more`일 때 어떤 분기만 자동 반복할지, report 재추출 횟수와 전체 provider/search/token/time budget을 함께 잠근다.
- 여러 retrieve finding은 현재 한 planner 입력으로 함께 전달한다. 후속에서는 finding 수가 커질 때의 grouping·priority·prompt budget만 별도 튜닝한다.

## Deferred / out of scope

- Gate schema에 `search_query`/`needs` 추가
- 여러 retrieval round에서 finding grouping·priority를 누적하는 정책
- 두 번째 재검색, 자동 revise, pass까지 내부 loop
- ContextPackage/GateRun/candidate/revision persistence와 idempotent replay
- `stages`/usage/latency/검색 trace public envelope
- save/accept/Analysis 및 frontend

## 승인 후 첫 회귀 경계

1. 첫 Gate가 `retrieve_more`가 아니면 planner/search/두 번째 Gate 호출은 모두 0이고 v1.6.75 결과를 그대로 반환한다.
2. 첫 Gate가 `retrieve_more`면 follow-up planner가 정확히 1회 호출되고, strict JSON `query + needs`를 반환한다. 허용 needs 밖 literal·빈 needs·빈 query는 검색 전에 실패한다.
3. planner는 모든 retrieve_more findings를 보며 기본 허용 집합은 canonical 5종뿐이다. `current_position`이 없으면 position-dependent `current_scene|recent_scenes`를 제외하며, `candidate_memory` 선택은 항상 거부한다.
4. 선택한 needs만 targeted ContextSearchRequest로 정확히 한 번 실행한다. 기존 Phase 4 planner는 그 needs 밖 step을 만들 수 없다.
5. 이전 package+delta package는 item identity로 dedup되고 전체 max_tokens budget을 다시 적용한 단일 merged package가 된다. 이전 package 객체를 별도 두 번째 정본으로 Gate에 전달하지 않는다.
6. candidate text와 report 네 필드는 유지되고 reporter 두 번째 호출은 0이다. 두 번째 Gate만 merged package로 정확히 1회 평가한다.
7. 두 번째 Gate decision 5종은 모두 200이고 다시 `retrieve_more`여도 추가 planner/search/Gate는 0이다.
8. follow-up planner/context 실패는 candidate+첫 Gate+`retrieval_error` partial envelope로 보존하고, 두 번째 Gate 실패는 merged context 단계의 기존 `gate_error` envelope를 사용한다.
9. `max_retrieval_rounds=1`, 같은 request/project identity, candidate_id null을 유지하며 save/revise/generate/accept/Analysis/persistence side effect는 0이다.
