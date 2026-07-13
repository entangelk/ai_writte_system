# 착수 결정 브리프 — Phase 5.7 partial revise → report → Gate 합성

상태: `Resolved — R1=A, R2=A, R3=A, R4=A, R5=C adopted(v1.6.77), R6=A`

관련 정본: SoT v1.6.71 Writing self-report, v1.6.72 report 재평가 API, v1.6.74 partial revise→Gate G3=A first→B, `05-writing-revise-gate-decisions.md`

## Decision needed

승인된 G3 B의 `revise → report 최신화 → Gate` 3단계를 기존 합성 API에 어떻게 추가하고, revise 성공 뒤 report가 실패했을 때 비영속 revised candidate를 어떤 HTTP/envelope로 보존할지 확정해야 한다. 기존 정본은 목표 순서만 잠갔으며 report 실패의 public contract는 잠그지 않았다.

## Owner decisions — 2026-07-13

- R1=A, R2=A, R3=A, R4=A, R6=A.
- R5는 다회 합성 확장을 열어두기 위해 C를 검토했으나, 현재 `{candidate, gate}`에 `stages`를 additive field로 붙이는 확장 비용이 작고 지금 C를 열면 stage item/status/attempt/usage schema를 추가 결정해야 한다. 따라서 **A first→C later**로 확정한다.

후속 채택(v1.6.77): **R5=C**. `{candidate,gate}`에 최소 `loop`와 `stages[{stage,ordinal,status}]`를 additive로 열었다. 전체 중간 artifact/model/usage는 후속 persisted 감사까지 보류한다.
- 이번 slice는 성공 `{candidate, gate}`를 유지한다. 추후 다회 합성을 실제로 열 때 `stages` schema와 loop budget을 함께 결정한다.

## 현재 확정된 경계

- 기존 `POST /projects/{id}/writing/revise-and-gate`는 동일 ContextPackage로 revise 1회→Gate 1회를 실행한다.
- partial revise 직후 candidate의 report 네 필드는 stale 방지를 위해 비워진다.
- G3는 A first→B로 승인됐다. 따라서 목표 상태는 Gate가 빈 report가 아니라 revised text에서 다시 추출한 최신 report를 받는 것이다.
- 독립 `/writing/report`는 side-effect-free이며 report 추출은 strict JSON + repair 최대 1회다. provider timeout은 504, provider/invalid report는 502다.
- revised candidate는 비영속이다. Gate 실패 선례는 HTTP 400/502/504에 candidate를 포함한 partial envelope로 artifact를 보존한다.
- 이 slice는 save/accept/Analysis, 재검색, 두 번째 revise, bounded loop, persistence를 수행하지 않는다.

## Options table

### R1 — public API 전환 방식

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 기존 `/writing/revise-and-gate`를 3단계로 승격 | 같은 요청/응답 경로에서 revise→report→Gate를 항상 실행 | G3의 목표 상태가 기본 동작이 되고 endpoint 난립이 없음 | latency·필수 dependency·호출 수가 2단계 계약에서 바뀜 |
| B. 별도 `/writing/revise-report-and-gate` 추가 | 2단계 endpoint를 보존하고 3단계 opt-in 경로 신설 | 완전한 후진 호환, 비교 측정 쉬움 | 거의 같은 API가 둘로 갈라지고 목표 상태가 기본이 아님 |
| C. 기존 endpoint에 `refresh_report` flag 추가 | 한 경로에서 2/3단계를 선택 | 단계별 비용 선택 가능 | 한 endpoint가 두 dependency/latency 계약을 가져 client·회귀가 복잡 |

추천: **A**. G3가 이미 A first→B라는 순차 migration으로 승인됐으므로, 2단계는 임시 첫 slice이고 3단계가 목표 계약이다. 아직 persisted public consumer가 없는 로컬 1인 프로젝트 단계에서 별도 영구 API나 flag를 남길 이유가 작다.

### R2 — ContextPackage lifecycle

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 최초 package 객체를 세 단계가 공유 | revise/report/Gate가 같은 grounding snapshot을 사용 | 검색 1회, 재현성과 기존 G2 원칙 유지 | report 시점에 검색을 새로 고치지 않음 |
| B. report 전에 package를 다시 구성 | revised text 이후 최신 검색 수행 | 새 prose에 맞춘 context 가능 | 명시적 `retrieve_more` 없이 DB·메모리 재접근, package identity·budget 이중화 |
| C. report만 context 없이 실행 | candidate text만으로 report 추출 | 검색 의존 축소 | 기존 report 계약과 grounding을 약화 |

추천: **A**. 재검색은 승인된 G2에 따라 `retrieve_more` 후속 브리프가 소유한다. G3가 그 lifecycle을 선점하면 안 된다.

### R3 — revise 성공 후 report 실패 envelope

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 502/504 + revised candidate + `report_error`, `gate=null` | 성공 artifact를 보존하고 실패 단계를 명시, Gate 미실행도 드러남 | partial envelope가 한 단계 더 생김 |
| B. 200 + candidate + `report_status=failed`, `gate=null` | transport 성공과 단계 실패 분리 | report 실패를 정상 완료로 오인할 위험 |
| C. 오류만 반환 | 기존 `/writing/report` 오류 응답과 단순 일치 | 성공한 비영속 revised candidate 유실 |
| D. 빈 report로 Gate를 계속 실행 | Gate outcome까지 최대한 반환 | G3 B가 조용히 G3 A로 퇴행하고 실패 원인이 섞임 |

추천: **A**. Gate 실패에서 채택한 artifact-preserving partial-success 선례와 대칭이다. D는 report 최신화 후 Gate라는 순서 계약을 위반하므로 선택하지 않는다.

### R4 — report 실패 taxonomy

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 기존 report 매핑 재사용 | provider timeout=504, provider unavailable/invalid report/예상 밖 report 평가 실패=502 | sibling API 및 Gate partial taxonomy와 일관 | 예상 밖 오류도 명시적으로 감싸야 함 |
| B. report 실패 전부 502 | envelope 단순 | timeout retry 의미를 잃음 |
| C. invalid report만 422 | 모델 출력 오류를 구분 | 현재 report/Gate API taxonomy와 불일치 |

추천: **A**. `report_error.type`은 최소 `provider code`, `invalid_candidate_report`, `report_error`를 구분하고 `detail`을 둔다.

### R5 — 성공 response shape

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 기존 `{candidate, gate}` 유지 | candidate 내부 report가 최신화되므로 client schema 무변 | report 단계 수행 여부를 별도 top-level field로 보이지 않음 |
| B. `{candidate, report, gate}` | 단계가 명시적 | report가 candidate 필드와 중복되고 두 정본이 생김 |
| C. `{candidate, gate, stages}` | 향후 loop 관측성에 유리 | 현재 1회 합성에는 speculative 구조 |

채택: **A first→C later**. report는 독립 artifact가 아니라 enriched candidate의 구조 필드다. 일반 JSON object에 `stages`를 additive field로 붙일 수 있어 확장 비용이 작다. stage item/status/attempt/usage literal은 다회 합성이 실제로 필요할 때 persisted audit/observability 및 loop budget과 함께 결정한다.

### R6 — dependency와 실행 횟수

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. context/reviser/reporter/Gate 모두 필수, 각 단계 1회 | endpoint 이름과 목표 순서를 항상 지키며 전체 호출이 bounded | report parser repair가 발생하면 provider 요청은 내부적으로 2회일 수 있음 |
| B. reporter 미구성이면 기존 2단계로 degrade | 가용성 우선 | 조용히 stale/empty report Gate로 퇴행 |

추천: **A**. 합성 단계는 revise 1회, report enrich 1회, Gate 1회다. 단, report service의 기존 strict-JSON repair 1회는 report 단계 내부 계약으로 그대로 허용한다. reporter 미구성은 503이고 revise/context/provider를 호출하지 않는다.

## Recommendation + reason

채택은 **R1=A, R2=A, R3=A, R4=A, R5=A first→C, R6=A**다. 기존 합성 endpoint를 목표인 3단계 계약으로 승격하고, 같은 ContextPackage에서 revised candidate를 report로 enrich한 뒤에만 Gate를 실행한다. report 실패는 Gate 실패와 대칭인 502/504 partial envelope로 revised candidate를 보존한다. 성공 envelope는 지금 `{candidate, gate}`를 유지하되, 다회 합성 시 `stages`를 additive로 열 수 있다. 이 방식이 현재 로컬 1인 프로젝트 단계에서 가장 작은 코드·API 변화이며, retrieve_more lifecycle과 G8 loop 정책을 섞지 않는다.

## Follow-up considerations

- persisted candidate/revision/report/GateRun이 생기면 각 단계 identity와 retry를 id 기반으로 수렴시킨다.
- 단계별 provider 호출 수·token usage·latency는 persisted 감사 이력 또는 별도 observability 계약에서 추가할 수 있다.
- G8 내부 loop는 enriched candidate와 GateResult를 입력으로 받되, report를 매 반복마다 다시 추출할지는 loop budget 브리프가 별도로 결정해야 한다.
- `retrieve_more`가 package를 교체하면 새 package identity 아래 report와 Gate를 모두 다시 실행할지 해당 lifecycle 브리프에서 잠근다.

## Deferred / out of scope

- `retrieve_more` query/needs, ContextPackage 교체, DB·메모리 재접근 lifecycle
- Gate non-pass 뒤 자동 revise/re-report/re-Gate 반복
- 자동 반복 가능한 finding, 사람 확인 조건, 전체 호출/token/time budget
- persisted candidate/revision/report/GateRun identity·retention·idempotency 및 id 기반 API
- multi-finding revise, evidence offset/hash anchor, accept patch 확장
- save/accept/Analysis 및 frontend

## 승인 후 첫 회귀 경계

1. 동일 ContextPackage 객체로 revise 1회→report enrich 1회→Gate 1회가 순서대로 실행되고 성공 응답은 기존 `{candidate, gate}`다.
2. Gate가 받는 candidate의 text와 report 네 필드는 reporter가 반환한 최신 candidate와 동일하다.
3. report provider timeout은 504, provider unavailable/invalid report/예상 밖 report 실패는 502이며 `{candidate, gate:null, report_error}`에 revised candidate가 보존된다.
4. report 실패 때 Gate 호출은 0이다. 정상 report일 때만 Gate가 정확히 1회 호출된다.
5. reporter 미구성은 503이며 context/revise/Gate 호출은 모두 0이다. 조용한 2단계 degrade가 없다.
6. revise/context 실패는 report/Gate 모두 미호출이고 기존 400/502/504 mapping을 유지한다.
7. Gate decision 5종(pass + non-pass 4종)은 최신 report가 든 candidate와 함께 모두 200이다. Gate 실패는 기존 `{candidate, gate:null, gate_error}` 계약을 유지하되 candidate에는 최신 report가 있다.
8. report service의 invalid JSON→repair 1회 경계는 재사용하며, 합성 service가 추가 retry를 만들지 않는다.
9. draft save/report persistence/accept/Analysis/재검색/두 번째 revise side effect는 0이다.
