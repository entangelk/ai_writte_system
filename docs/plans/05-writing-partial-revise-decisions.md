# 착수 결정 브리프 — Phase 5.6 finding evidence 기반 부분 revise

상태: `Resolved — D1=A→follow-up brief, D2=A first→C, D3=A, D4=A first→C, D5=A→B→C, D6=C, D7=A first→C, D8=A first→C`

관련 정본: SoT v1.6.69~72, `05-writing-gate-decisions.md` D3/Follow-up, `05-writing-accept-decisions.md` revision patch 후속, `writing_agent_prompt.md` §16.2

## Decision needed

Writing Gate finding의 exact `evidence`를 어떤 patch anchor와 public 결과로 변환해 후보 일부만 재생성할지 확정해야 한다. 기존 정본은 자동 전체 재생성을 금지하고 evidence 기반 부분 revise를 후속으로 열었지만, anchor 모호성·여러 finding·새 candidate identity·Gate 재평가·반복 budget은 아직 정하지 않았다.

## Owner decisions — 2026-07-13

- D1=A: revise-only first. retrieve_more는 후속 브리프로 계약한다.
- D2=A first→C: exact evidence 단일 발생만 허용하고 장기 offset/hash anchor로 확장한다.
- D3=A: 모델은 replacement 평문만 반환한다. **anchor 산술·검증·splice·loop 제어는 내부 Application 서버가 소유하고 모델 서버는 호출/응답에 집중한다.** 모델 교체 가능성을 위해 이 책임 경계를 Writing 전반의 원칙으로 둔다.
- D4=A first→C: 단일 finding을 기본으로 구현하고, 작은 글쓰기/작은 replacement 호출의 자원 비용을 측정한 뒤 여러 finding 단일-turn structured 응답(C)을 별도 확장한다.
- D5=A→B→C: 첫 slice는 Gate 별도 호출, 다음은 자동 Gate 1회, 궁극적으로 Gate pass까지 bounded loop. C의 사람 확인 대상과 자동 반복 허용 finding은 테스트/정책 브리프로 먼저 잠근다.
- D6=C: inline API를 먼저 열고 persisted candidate/GateRun/revision 감사 이력 기반 id API를 additive 후속으로 둔다.
- D7=A first→C: 첫 slice는 LLM 1회. 장기에는 Application 소유 AgentLoopRunner budget으로 확장하되 tool-call 상류 의존을 우회하지 않는다.
- D8=A first→C: unchanged는 첫 slice에서 invalid provider result 502. 장기에는 `200 + changed=false + revision_status` business outcome으로 승격해 transport 실패와 분리한다. 한 응답에 502와 200을 동시에 쓸 수 없으므로 순차 migration으로 해석한다.
- 파생 안전선: revised text는 기존 candidate report를 stale하게 만들므로 새 candidate의 report 네 필드는 비우고 `/writing/report` 재평가로 다시 채운다.

## 현재 확정된 경계

- Gate는 side-effect-free이며 finding `evidence`는 candidate text에 실제 포함되어야 한다.
- `do_not_use`와 POV finding은 blocking error라 현재 Gate 계약상 부분 revise 추천 대상이 아니다. 첫 자연 대상은 `continuity + recommended_decision=revise`다.
- 현재 WritingCandidate는 비영속 inline object이고 `output_type=draft_patch`다. accept는 continue_scene 전체 patch를 paragraph append하며 selection replace/revision patch는 별도 후속이다.
- 사용자가 accept하기 전 draft/canon은 바뀌지 않는다. report/Gate/accept/Analysis 자동 실행은 각각 독립 API다.

## Options table

### D1 — 첫 orchestration 범위

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. revise만 | `continuity + revise` finding의 evidence 범위만 수정한다 | anchor/patch 계약에 집중, 검색·반복 budget과 분리 | retrieve_more는 후속 |
| B. revise + retrieve_more | revise는 부분 수정, retrieve_more는 재검색 후 수정까지 한 API에서 처리 | 두 decision을 한 흐름으로 제공 | 검색 query/needs·재생성 범위·budget이 결합되어 slice가 커진다 |
| C. retrieve_more 먼저 | 검색 부족 경로부터 닫고 revise는 미룬다 | 기존 ContextSearch 재사용 | evidence 기반 부분 수정이 계속 비어 있다 |

추천: **A**. retrieve_more는 검색 query/needs와 반복 종료를 별도 브리프로 잠근다.

### D2 — evidence anchor

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. exact substring 단일 발생만 | evidence가 candidate text에 정확히 한 번 있을 때만 anchor로 인정한다 | 현재 Gate 보장을 그대로 강화하며 결정적 splice 가능 | 중복 문구는 거부되어 사용자가 범위를 좁혀야 한다 |
| B. 첫 번째 일치 | 여러 번 있어도 첫 occurrence를 수정한다 | 구현이 작고 항상 진행 | 잘못된 문장을 고칠 수 있어 조용한 오수정 위험 |
| C. offset/hash anchor 신설 | start/end offset과 candidate hash를 Gate finding에 추가한다 | 명확하고 장기 editor patch와 정합 | Gate public schema 변경과 기존 finding 재생성이 선행돼 slice가 커진다 |

추천: **A first→C**. 모호한 anchor를 임의 선택하지 않고 persisted candidate/editor selection이 생길 때 offset/hash로 승격한다.

### D3 — 모델 출력과 splice 책임

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. replacement fragment 평문 + 서버 splice | 모델은 evidence를 대체할 문구만 반환하고 서버가 prefix+replacement+suffix를 결정적으로 합친다 | 평문 생성 강점 유지, 부분 범위가 기계적으로 보장됨 | replacement가 주변 문맥과 자연스럽게 이어지는지 Gate가 별도 확인해야 함 |
| B. 새 전체 candidate 평문 | 모델이 원 후보 전체 수정본을 반환한다 | 문맥 자연스러움 | evidence 밖 좋은 부분 보존을 기계적으로 보장할 수 없어 “부분 revise” 계약이 약해짐 |
| C. JSON patch | 모델이 offset/replacement JSON을 반환한다 | 구조화 patch | 로컬 모델 JSON fragility와 offset 산술을 모델에 맡김 |

추천: **A**. 모델에게 anchor 산술을 맡기지 않고 수정 범위를 서버가 보장한다.

### D4 — 한 요청의 finding 수

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 정확히 하나 | 한 evidence→한 replacement→한 splice | 겹침·순서·부분 실패 없음, 회귀 명확 | 여러 finding은 client가 순차 호출해야 함 |
| B. 여러 개, 역 offset 순 splice | 모든 finding replacement를 만들고 뒤에서부터 적용 | 한 번에 처리 | overlap·동일 evidence·한 항목 실패·LLM 호출 수 의미 필요 |
| C. 여러 finding을 한 LLM turn에 전달 | 모델이 여러 replacement를 반환 | 호출 수 절약 | structured output과 finding↔replacement identity 계약 필요 |

채택: **A first→C**. 여러 finding 단일-turn은 작은 단위 호출의 자원 비용을 측정한 뒤 별도 확장한다.

### D5 — 수정 뒤 검증

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. revise만 반환, Gate 별도 호출 | endpoint는 새 inline candidate만 반환하고 기존 `/writing/gate`로 재평가한다 | side-effect-free 컴포넌트 경계 유지, 실패 의미 단순 | client가 Gate 재호출을 빼먹을 수 있음 |
| B. 자동 Gate 1회 재평가 | revised candidate와 새 GateResult를 함께 반환한다 | 수정 성공 여부 즉시 확인 | revise 성공+Gate provider 실패 partial envelope, dependency/budget 결합 |
| C. Gate pass까지 반복 | 반복 revise/gate loop | 완결된 후보를 목표 | 종료/budget/identity 결정이 커지고 flat-loop 보류 경계와 충돌 가능 |

채택: **A→B→C**. 현재 독립 API 조합 원칙을 유지하고, 자동 Gate 1회와 bounded pass loop를 순차 확장한다. C 전에 사람 확인 대상과 자동 반복 허용 finding을 정책/테스트로 잠근다.

### D6 — public API와 identity

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. `POST /projects/{id}/writing/revise` inline | request, previous candidate text, 단일 finding을 받고 새 비영속 WritingCandidate를 반환한다 | 현재 generate/gate/report와 동형, persistence 불요 | 감사 이력은 client가 보관해야 함 |
| B. candidate id 기반 revision API | persisted candidate와 finding id를 서버에서 읽어 successor를 만든다 | append-only 감사 이력·권위 identity | v1.6.72 B persistence 선행 필요 |
| C. A 지금, B additive 후속 | inline API를 열고 persistence 뒤 id 기반 successor API 추가 | 현재 진행성과 장기 감사 이력 모두 보존 | public surface가 둘이 됨 |

추천: **C(A first, B later)**. 현재는 `candidate_id=null`; 향후 persisted candidate/report/GateRun 감사 이력과 함께 successor relation을 추가한다.

### D7 — 첫 slice budget/실패 의미

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. LLM 1회, repair 없음 | 평문 replacement 한 turn만 허용; provider timeout 504/기타 502, validation 400 | writing_generate와 동형, bounded | 빈 replacement의 provider-result 오류 분류를 명시해야 함 |
| B. 1회 + 빈 출력 repair 1회 | 빈/부적합 replacement만 재요청 | 사소한 모델 흔들림 회복 | 평문인데 repair contract가 새로 필요 |
| C. AgentLoopRunner budget | 5차원 budget/retry를 사용 | 장기 loop와 통일 | writing task artifact schema/tool-call 상류가 아직 보류 |

채택: **A first→C**. replacement가 빈 문자열이면 첫 slice에서 invalid provider result 502로 분리한다. 장기 loop budget은 Application이 소유한다.

### D8 — unchanged replacement

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. invalid provider result 502 | replacement가 evidence와 같으면 수정 실패로 본다 | 고치지 않은 결과를 성공으로 위장하지 않음 | 문구 유지가 실제 최선인 드문 경우도 실패 |
| B. 200 no-op candidate | 동일 replacement도 유효 결과로 반환한다 | 단순하고 idempotent | revise finding을 해소하지 않았는데 성공처럼 보임 |
| C. 200 + `changed=false` | no-op를 business outcome으로 명시한다 | transport 실패와 구분 | 새 envelope literal과 client 분기 필요 |

채택: **A first→C**. 첫 slice 성공은 anchor 문구가 바뀌었다는 기계적 조건을 만족해야 한다. 후속에는 `200 + changed=false + revision_status`로 transport 실패와 분리한다.

## Recommendation + reason

채택 묶음은 **D1=A, D2=A first→C, D3=A, D4=A first→C, D5=A→B→C, D6=C(A first/B later), D7=A first→C, D8=A first→C**다. 현재 비영속·독립 API 단계에서 한 continuity finding의 exact evidence만 결정적으로 교체하면 “좋은 부분 보존”을 코드가 보장한다. 검색·반복·감사 persistence를 한꺼번에 열지 않아 실패와 budget 의미도 작게 유지된다.

## Follow-up considerations

- v1.6.72 B의 persisted candidate/report 감사 이력 도입 시 revision successor id, source candidate id, Gate finding/GateRun id를 함께 설계한다.
- offset/hash anchor(C)는 editor selection과 candidate content hash가 canonical해질 때 연다.
- 자동 Gate 합성(B)은 revised candidate 생성 성공 후 Gate 실패의 partial-success envelope를 먼저 결정한다.
- retrieve_more는 follow-up query/needs, 새 ContextPackage identity, 최대 반복 수를 별도 브리프로 결정한다.

## Deferred / out of scope

- retrieve_more 자동 검색·재생성
- 여러 finding batch/overlap resolution
- Gate pass까지 자동 반복
- draft selection replace와 accept-time revision patch 적용
- candidate/GateRun/revision 감사 persistence
- agent-loop tool-call branch

## 승인 후 첫 회귀 경계

1. continuity+revise 단일 finding, evidence 단일 발생 → replacement fragment만 생성하고 evidence 밖 prefix/suffix는 byte-for-byte 보존.
2. evidence 없음 또는 복수 발생, non-continuity, recommendation이 revise 아님, 빈 request/instruction/candidate/evidence → provider 전 400.
3. replacement 빈/whitespace → 502, 원 후보와 저장소 side effect 없음.
4. request/candidate/package project·request identity 불일치 → provider 전 400.
5. provider timeout 504, 기타 provider 502; context budget 504/backend 502; dependency 미구성 503; missing project 404.
6. 응답은 새 비영속 WritingCandidate(`candidate_id=null`, 기존 task/output/status 유지).
7. report/Gate/accept/Analysis/draft save 자동 호출 없음.
8. replacement가 evidence와 같으면 invalid provider result 502이며 성공으로 위장하지 않는다(D8=A 선택 시).
