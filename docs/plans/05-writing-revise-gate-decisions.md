# 착수 결정 브리프 — Phase 5.7 partial revise → Gate 1회 합성

상태: `Resolved — G1=A, G2=A, G3=B adopted(v1.6.75), G4=A, G5=A, G6=A, G7=A, G8=B adopted(v1.6.77)`

관련 정본: SoT v1.6.69 Writing Gate, v1.6.73 partial revise D5=A→B→C, `05-writing-partial-revise-decisions.md`

## Decision needed

부분 revise 성공 직후 Writing Gate를 정확히 한 번 자동 평가하는 D5=B를 어떤 public API/envelope로 제공할지 확정해야 한다. revised candidate는 비영속이므로 Gate 실패 때 candidate를 잃지 않아야 하며, 기존 `/writing/revise` 응답을 변경하면 이미 잠긴 독립 API 계약을 깨게 된다.

## Owner decisions — 2026-07-13

- G1=A: 별도 additive `/writing/revise-and-gate`.
- G2=A: 한 요청에서는 동일 ContextPackage를 revise와 Gate가 공유한다. 후속 loop에서 `retrieve_more`가 명시될 때만 재검색/메모리 재접근을 수행하며, DB 연결 해제 후 재접근 같은 lifecycle은 retrieve_more 브리프에서 다룬다.
- G3=A first→B: 첫 slice는 빈 report 상태로 Gate. 목표는 report 최신화 후 Gate이며 latency/partial 단계 계약을 추가해 확장한다.
- G4=A: Gate 실패는 partial-success에 revised candidate와 `gate_error`를 포함한다. Gate 입력/설정 검증 실패는 400, provider·invalid result·예기치 않은 평가 실패는 502, provider timeout은 504다. D8 unchanged(후보 자체 없음)와 달리 이 분기는 candidate artifact가 이미 존재한다.
- G5=A, G6=A, G7=A: non-pass 200, nested envelope, 의존성/오류 명시.
- G8=A first→B after: 첫 slice는 revise 1회+Gate 1회. 후속에는 정책·budget을 잠근 내부 반복을 추가한다.

후속 채택(v1.6.77): **G8=B**. 단일 continuity finding auto-revise와 targeted retrieval을 설정 가능한 구조적 budget 안에서 반복하고 최소 `loop`/`stages`를 공개한다. 상세 현재 계약은 `05-writing-bounded-loop-decisions.md`가 소유한다.

## 현재 확정된 경계

- partial revise는 continuity+revise 단일 finding, exact evidence 단일 anchor, replacement LLM 1회, Application splice다.
- Writing Gate는 별도 LLM 1회이며 decision=`pass|revise|retrieve_more|needs_user_review|block`, side-effect-free다.
- D5 로드맵은 A(별도 호출)→B(자동 Gate 1회)→C(bounded pass loop)다. 이 slice는 B까지만이며 두 번째 revise나 loop를 실행하지 않는다.
- revised candidate의 report는 stale 방지를 위해 비워진다. report 재평가 API는 별도로 존재한다.
- 모델은 호출/응답만, 합성 순서·검증·오류 envelope는 Application이 소유한다.

## Options table

### G1 — public API 경계

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 별도 `/writing/revise-and-gate` | 기존 revise 입력을 받고 `{candidate, gate}` 합성 응답 | 기존 `/writing/revise` 무변, A와 B를 client가 명시 선택 | endpoint 하나 추가 |
| B. `/writing/revise`가 항상 Gate까지 실행 | 기존 응답을 합성 envelope로 변경 | endpoint 수가 적음 | v1.6.73 응답/latency/dependency 계약을 깨는 변경 |
| C. `/writing/revise?evaluate=true` | query flag로 선택 | 경로 재사용 | 한 endpoint가 두 envelope를 가져 schema/client가 복잡 |

추천: **A**. 기존 독립 API를 보존하는 additive 합성이다.

### G2 — ContextPackage

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 한 번 재구성해 revise와 Gate가 공유 | 같은 근거로 수정/판정, planner 호출 1회 | package가 revise 뒤 최신 검색은 아님 |
| B. Gate 전에 다시 검색 | Gate가 별도 최신 package 사용 | planner 비용 2배, 두 package 차이로 재현성 저하 |
| C. client가 Gate package 제출 | 호출 절약 | 서버 권위 재구성 원칙 위반 |

추천: **A**. 한 합성 request 안에서는 동일 grounding을 사용한다.

### G3 — report 재추출 위치

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 빈 report 상태로 Gate | Gate가 candidate text+ContextPackage를 직접 평가 | LLM 2회(revise+Gate)로 bounded | report risk/claim 보조 없음 |
| B. report 재추출 후 Gate | revise→report→Gate | Gate 보조 정보 최신 | LLM 3회, report 실패 partial 단계 추가 |
| C. Gate 뒤 pass일 때만 report | 판정 우선, pass candidate만 enrich | 불필요 report 호출 절약 | 응답이 pass/non-pass별 report 상태가 달라짐 |

채택: **A first→B**. 첫 slice는 revise+Gate에 한정하고 목표는 report 최신화 후 Gate다.

### G4 — revise 성공 후 Gate 실패 envelope

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 400/502/504 partial-success + revised candidate + `gate_error` | candidate를 잃지 않고 검증 실패와 provider 실패를 구분하며, 실패를 성공으로 위장하지 않음 | 복합 오류 envelope 필요, 비영속이라 retry가 같은 prose를 보장하지 않음 |
| B. 200 + candidate + `gate_status=failed` | candidate 보존, transport와 business outcome 분리 | Gate 실패를 HTTP 성공으로 볼 위험 |
| C. 오류만 반환 | 기존 error mapping 단순 | 성공한 revised candidate가 유실됨 |

추천: **A**. accept의 saved-artifact partial-success 선례를 따르되, Gate 입력/설정 검증은 400, provider·invalid result·예기치 않은 평가 실패는 502, timeout은 504로 기존 taxonomy를 유지한다. 재시도 수렴은 보장하지 않고 client가 candidate를 보관해 `/writing/gate`만 재호출할 수 있게 한다.

### G5 — Gate non-pass 의미

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 모두 200 정상 outcome | candidate+GateResult를 반환하고 decision이 다음 행동을 지시 | 기존 Gate/accept non-pass 의미와 일치 | client가 decision을 반드시 확인해야 함 |
| B. block만 409 | hard failure를 HTTP로 강조 | business decision과 transport 오류 혼합 |
| C. pass만 200, 나머지 422 | 성공 정의가 단순 | revise/retrieve/review가 정상 결과라는 기존 계약과 충돌 |

추천: **A**.

### G6 — 성공/실패 response shape

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 성공 `{candidate, gate}`, partial `{candidate, gate:null, gate_error}` | 단계 상태가 명확 | 기존 flat candidate serializer를 중첩 사용 |
| B. candidate fields와 gate fields를 한 flat object로 병합 | 읽기 짧음 | 필드 충돌·향후 확장 어려움 |
| C. 단계 배열 | loop 확장에 유리 | B 한 번에는 과도한 일반화 |

추천: **A**. C loop는 별도 계약에서 연다.

### G7 — dependency/error mapping

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. revise/gate/context 모두 필수, 기존 매핑 재사용 | 미구성 503, validation 400, context/revise/gate provider 502·timeout/budget 504 | sibling API와 일관 | 어느 단계 실패인지 envelope/detail에 명시 필요 |
| B. Gate 미구성이면 revise-only degrade | 일부 결과 제공 | B endpoint가 조용히 A로 퇴행 |

추천: **A**. endpoint 이름이 약속한 Gate를 생략하지 않는다.

### G8 — 반복과 side effect

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. revise 1회 + Gate 1회 후 항상 종료 | D5=B 정확히 구현, bounded | non-pass는 client 후속 필요 |
| B. Gate revise면 한 번 더 revise | 품질 향상 가능 | 이미 D5=C loop로 넘어가 budget/사람 확인 정책 필요 |

채택: **A first→B after**. 첫 slice는 각 1회이며, 내부 반복은 정책·budget을 잠근 후 추가한다. save/report/accept/Analysis는 첫 slice에서 자동 호출하지 않는다.

## Recommendation + reason

채택 묶음은 **G1=A, G2=A, G3=A first→B, G4=A, G5=A, G6=A, G7=A, G8=A first→B**다. 기존 독립 endpoint를 보존하면서 Application이 두 LLM 호출의 순서와 partial-success를 명시적으로 소유한다. 후속 loop의 budget·사람 확인·retrieve_more 재검색 정책은 지금 미리 일반화하지 않는다.

## Follow-up considerations

- D5=C 전에 자동 반복 가능한 finding/decision과 반드시 사람 확인할 조건을 fixture로 잠근다.
- persisted candidate/GateRun이 생기면 partial-success candidate와 Gate retry를 id로 수렴시킬 수 있다.
- report 재추출 합성은 latency/품질 측정 뒤 별도 옵션으로 연다.
- 단계별 model id/token usage를 envelope에 넣을지는 관측성 slice에서 결정한다.

## Deferred / out of scope

- Gate pass까지 반복, 두 번째 revise
- retrieve_more 자동 검색
- report 자동 재추출
- candidate/GateRun persistence와 idempotent replay
- save/accept/Analysis 자동 실행

## 승인 후 첫 회귀 경계

1. 동일 ContextPackage로 revise 1회→Gate 1회, 성공 `{candidate, gate}`.
2. Gate pass/revise/retrieve_more/needs_user_review/block 모두 200이며 두 번째 revise 없음.
3. revise validation/provider/context 실패는 Gate 미호출, 기존 400/502/504.
4. Gate 입력/설정 검증 실패는 400, provider/invalid result/예기치 않은 평가 실패는 502, timeout은 504이며 모두 revised candidate를 포함한 partial envelope.
5. Gate 미구성/revise 미구성/context 미구성은 503, 조용한 degrade 없음.
6. revised candidate report는 빈 상태로 Gate에 전달되고 report service는 미호출.
7. project/request identity와 evidence anchor 검증은 context/revise provider 전 수행.
8. draft save/report/accept/Analysis side effect 0.
