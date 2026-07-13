# 착수 결정 브리프 — Phase 5.9 Writing bounded revise/retrieve loop

상태: `Resolved — L1=A, L2=A, L3=A, L4=A configurable, L5=A, L6=A first→C, L7=A, L8=A typed distinction, L9=A first→B`

관련 정본: SoT v1.6.77, `05-writing-revise-gate-decisions.md` G8, `05-writing-partial-revise-decisions.md` D4/D5/D7/D8, `05-writing-revise-report-gate-decisions.md` R5, `05-writing-retrieve-more-decisions.md` T7/T8, `flat-loop-gate.md`

## Decision needed

`/writing/revise-and-gate`가 첫 Gate 뒤 `revise`와 `retrieve_more`를 어디까지 자동 실행할지, 사람 확인 경계·반복별 report/ContextPackage 정책·종료 envelope·전체 예산을 확정해야 한다. 현재 정본은 G8을 A first→B로 열어 두었지만, 안전한 finding 자격과 공개 loop 상태, 집계 token/time 예산은 기존 계약에서 하나로 도출되지 않는다.

## Owner decisions — 2026-07-13

- **L1/L2/L3=A**: 기존 `/writing/revise-and-gate`를 bounded loop로 승격한다. pass와 사람 decision은 종료하고, 단일 continuity revise finding과 잔여 budget이 있는 retrieve_more만 자동 실행한다. revise 뒤 report→Gate, retrieve 뒤 merge→Gate만 재계산한다.
- **L4=A configurable**: 첫 구현 기본값은 총 revision 2·retrieval 1·Gate 3이지만 코드 고정 literal이 아니라 설정으로 변경 가능한 `WritingLoopPolicy`다. 관측 가능한 loop가 완성된 뒤 실제 분포에 따라 운영값을 조정할 수 있어야 한다.
- **L5=A**: 구조적 call cap을 먼저 강제한다. aggregate token/time은 usage plumbing과 live 계측 뒤 B2로 연다.
- **L6=A first→C**: 최소 `loop`+`stages`를 먼저 공개하고, 중간 candidate/report/context 전체 artifact는 감사·재현 필요가 구체화될 때 additive로 확장 가능성을 보존한다.
- **L7=A**: 정상 종료는 200 business outcome으로 구분한다. stage transport/provider 실패의 loop 상태는 정상 종료 literal과 섞이지 않는 `failed`다.
- **L8=A typed distinction**: 자동 후속 revise의 unchanged만 200 `no_change`다. 최초 사용자 요청 revise와 standalone `/writing/revise`의 unchanged 502는 유지한다. 문자열 조건이 아니라 전용 `UnchangedWritingRevision` 타입으로 두 의미를 분리한다.
- **L9=A first→B**: 첫 구현은 호출 내 ephemeral stages이며 save/accept/Analysis는 없다. 후속 persisted loop audit가 stage/artifact identity를 수용할 수 있게 public schema를 additive로 유지한다.

## 현재 확정된 경계

- 현재 합성은 최초 revise→report→Gate 뒤 `retrieve_more`일 때 planner→targeted search→merge→Gate를 최대 한 번 수행한다.
- `pass|revise|retrieve_more|needs_user_review|block` 중 `needs_user_review|block`은 사람/정책 경계이며 자동 수정 대상이 아니다.
- 부분 revise는 single finding, exact evidence 1회 출현, anchor 검증을 전제로 한다. multi-finding 자동 수정은 아직 열리지 않았다.
- candidate text가 바뀌면 report를 다시 생성해야 한다. retrieval만 수행하면 report를 다시 만들지 않고 merged ContextPackage로 Gate를 재평가한다.
- 현재 domain service 결과에는 provider token `usage`가 전달되지 않는다. 따라서 aggregate token budget을 실제로 강제하려면 provider→domain 결과 계약을 먼저 확장해야 한다.
- candidate/report/GateRun/ContextPackage는 비영속이며 save/accept/Analysis는 이 endpoint의 side effect가 아니다.

## Options table

### L1 — public 실행 경계

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 기존 `/writing/revise-and-gate`를 bounded loop로 승격 | 현재 내부 retrieval 흐름에 안전한 auto-revise를 더한다 | package와 중간 artifact를 같은 호출에서 유지, client 왕복 없음 | 기존 endpoint latency와 성공 응답이 additive 확장됨 |
| B. 새 `/writing/loop` endpoint | 기존 합성을 그대로 두고 명시적 loop API를 만든다 | opt-in과 관측성 명확 | 거의 같은 orchestration/API가 두 벌이 됨 |
| C. request flag로 opt-in | 기존 endpoint에 `auto_loop=true`를 추가한다 | rollout 선택 가능 | 한 endpoint가 두 실행 의미와 두 테스트 행렬을 가짐 |

추천: **A**. G8과 T8이 기존 합성의 후속 내부 loop를 가리키며, 비영속 ContextPackage를 유지해야 merge가 가능하다.

### L2 — decision별 자동 행동과 사람 확인

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 엄격한 safe subset | `pass` 종료, `needs_user_review|block` 즉시 종료, `retrieve_more`는 잔여 retrieval budget 안에서 실행, `revise`는 자격을 만족하는 단일 finding만 자동 수정 | 기존 single-finding 안전 경계 보존 | 여러 수정 finding은 자동 완결하지 못함 |
| B. 모든 `revise` finding 자동 처리 | findings를 순서대로 수정한다 | 자동화 범위 큼 | multi-finding 우선순위·anchor drift·상호 덮어쓰기 정책을 선점 |
| C. retrieval만 반복하고 revise는 항상 종료 | 현재 T8만 확장한다 | 수정 안전성 최고 | G8 B의 자동 revise 목적을 달성하지 못함 |

추천: **A**. auto-revise 자격은 `recommended_decision=revise`, finding 1개, `type=continuity`, exact evidence 1회 출현으로 제한한다. 자격 밖 `revise`는 실패가 아니라 사람 판단이 필요한 정상 종료다.

### L3 — 반복 상태 전이와 artifact 최신성

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. artifact별 최소 재계산 | revise 뒤 report→Gate, retrieve 뒤 merge→Gate만 수행한다. revise는 현재 merged package를 사용한다 | 현재 R5/T6 원칙과 일치, 불필요한 report 호출 없음 | report가 context-relative라는 T6 tradeoff 유지 |
| B. 모든 행동 뒤 report→Gate | retrieval 뒤에도 report를 새로 만든다 | 매 단계 report/context 일치 | candidate 불변 retrieval에도 provider 호출·실패 단계 증가 |
| C. 매 반복마다 context부터 전부 재구성 | revise/retrieve 뒤 전체 검색→report→Gate를 다시 수행한다 | 단순한 전체 재실행 모델 | 부분 pass에서 낭비가 크고 targeted retrieval 결정을 무력화 |

추천: **A**. 상태 전이는 `Gate(revise)→revise→report→Gate`, `Gate(retrieve_more)→planner→targeted search→merge→Gate`다. 새 Gate가 다른 자동 decision을 내리면 잔여 budget 안에서 한 번 이어갈 수 있다.

### L4 — 첫 increment의 구조적 상한

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 총 revision 2·retrieval 1·Gate 3 | 최초 revision 포함 최대 2회, targeted retrieval 최대 1회, Gate 최대 3회, report 최대 2회 | `revise→retrieve`와 `retrieve→revise`를 모두 한 번씩 처리하면서 결정적으로 종료 | 같은 action을 두 번 재시도하지 못함 |
| B. revision 3·retrieval 2·Gate 5 | decision을 action별 두 번까지 허용 | pass 도달 가능성 증가 | cycle·latency와 부분 실패 행렬이 급증 |
| C. 공통 `max_iterations` 하나 | 모든 action을 같은 횟수로 센다 | 설정 단순 | search/provider/report 비용이 다른 단계를 같은 단위로 뭉개 경계가 불명확 |

채택: **A configurable**. 최초 수정 뒤 auto-revise는 1회, targeted retrieval은 현행 1회를 유지한다. Gate 3회면 두 action의 순서 조합을 모두 닫을 수 있고 동일 action 반복은 사람에게 돌린다. 세 상한은 설정 가능한 `WritingLoopPolicy`와 환경 설정으로 배선하며 component 내부 JSON repair 1회는 loop round가 아니라 해당 호출의 고정 parser 정책으로 유지한다.

### L5 — token/time/provider/search budget 도입 순서

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 구조적 call cap 먼저, 계측 후 aggregate token/time | L4를 강제하고 각 component timeout은 유지한다. usage plumbing·live latency 측정 뒤 aggregate 값과 search hit/token cap을 후속 확정한다 | 근거 없는 숫자를 피하고 현재 계약 변경 최소 | 이번 increment에서 총 token/time 한도를 직접 강제하지 않음 |
| B. 이번에 5차원 aggregate budget까지 도입 | provider calls·wall-clock·tokens·search calls·repeated calls를 모두 집계한다 | 완전한 운영 budget | domain usage 계약 확장과 실측 기본값 결정이 함께 필요 |
| C. generic `AgentLoopRunner` budget을 그대로 재사용 | 기존 5차원 모델에 Writing을 맞춘다 | 새 budget 모델 최소 | tool/artifact 중심 generic loop와 Writing 단계/부분 artifact 의미가 다름 |

추천: **A**. 로컬 1인 프로젝트 단계이고 현재 usage가 domain 경계를 통과하지 않는다. L4는 실제 강제 가능한 구조적 budget이며, aggregate token/time 기본값은 live 계측 없이 추측하지 않는다. 이는 full budget 폐기가 아니라 **B2 increment**로 명시한다.

### L6 — 성공·종료 envelope와 `stages`

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. additive `loop`+최소 `stages` | 기존 `{candidate,gate}`에 `loop:{status,revision_rounds,retrieval_rounds,gate_evaluations}`와 `{stage,ordinal,status}` 배열을 추가한다 | budget 종료와 중간 artifact 순서를 client가 구분 | public schema 확대 |
| B. 기존 `{candidate,gate}`만 유지 | 최종 Gate만 반환한다 | 하위호환 최대 | 같은 non-pass라도 자격 부족/예산 소진/정상 terminal을 구분 불가 |
| C. 모든 단계의 전체 payload 공개 | 각 candidate/report/Gate/context trace를 stages에 넣는다 | 디버깅·감사 풍부 | 비영속 첫 slice에 response와 retention 계약이 과도함 |

채택: **A first→C**. R5/T7에서 미룬 additive stage 관측성을 G8에서 최소 범위로 연다. stage literal은 `revise|report|gate|retrieve_plan|context_search|merge`, status는 `completed|failed|no_change`만 둔다. provider model/usage, context 본문과 중간 candidate payload는 아직 공개하지 않되 후속 persisted 감사에서 additive로 확장한다.

### L7 — 정상 종료 literal과 예산 소진

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 200 business outcome | `pass|terminal_decision|not_eligible|budget_exhausted|no_change`로 종료 원인을 명시하고 마지막 candidate/Gate를 보존한다 | non-pass와 budget 소진을 transport 오류로 오인하지 않음 | caller가 `loop.status`를 확인해야 함 |
| B. budget/no-change를 409/422로 반환 | 자동 완결 실패를 HTTP 오류로 표시한다 | 실패가 눈에 띔 | Gate의 정상 non-pass 의미와 충돌 |
| C. 마지막 Gate decision만으로 추론 | 별도 종료 literal 없음 | schema 최소 | budget 소진과 의도된 terminal을 구분할 수 없음 |

추천: **A**. 다음 action을 시작하기 전에 상한을 검사하고 마지막 완전한 artifact에서 종료한다. `needs_user_review|block`은 `terminal_decision`, 자격 밖 revise는 `not_eligible`, 실행할 잔여 횟수가 없으면 `budget_exhausted`다.

### L8 — auto-revise `unchanged`와 partial error

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. loop의 unchanged는 200 `no_change` | 이전 candidate와 마지막 Gate를 보존하고 더 반복하지 않는다. 단계 실패는 기존 status taxonomy와 candidate/Gate/loop/stages partial envelope를 사용한다 | 불필요한 같은 수정 재시도 방지, artifact 보존 | standalone `/writing/revise`의 현행 unchanged 502와 의미가 다름 |
| B. 현행처럼 unchanged 502 | standalone과 동일 error literal 유지 | 계약 일관 | auto-loop에서는 정상 수렴 실패를 provider 오류처럼 취급 |
| C. unchanged면 retrieval로 전환 | 다른 해결책을 자동 시도 | 자동성 | Gate가 요구하지 않은 검색 side effect를 발명 |

채택: **A typed distinction**. loop orchestration의 **자동 후속 revise** unchanged는 모델 호출 실패가 아니라 “요청한 부분 수정으로 변화 없음”이라는 정상 종료다. 전용 `UnchangedWritingRevision` 타입을 도입해 최초/standalone 경로는 부모 `InvalidWritingRevision`의 기존 502를 유지하고 auto-loop만 `no_change`로 소비한다. 실제 stage 예외는 `revision_error|report_error|gate_error|retrieval_error`로 현재 taxonomy를 재사용한다.

### L9 — identity·persistence·side effect

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 호출 내 ephemeral loop | 같은 request/project, `candidate_id=null`, save/accept/Analysis 0, stages도 응답에만 존재 | 현재 Writing 계층과 일치, 변경 범위 작음 | 재접속 감사/replay 불가 |
| B. GateRun/revision/stages를 함께 영속 | loop 감사와 재현을 이번에 연다 | 운영 관측성 높음 | stable pointer/idempotency/retention 결정을 한꺼번에 요구 |

채택: **A first→B**. bounded 행동 정책을 먼저 잠그고 persisted loop 감사 API가 이후 stage/artifact identity를 additive로 수용하도록 한다.

## Recommendation + reason

채택 묶음은 **L1=A, L2=A, L3=A, L4=A configurable, L5=A, L6=A first→C, L7=A, L8=A typed distinction, L9=A first→B**다. 기존 endpoint 안에서 single-finding auto-revise 1회와 targeted retrieval 1회를 순서와 무관하게 이어가되, 사람 확인 decision과 multi-finding은 넘지 않는다. 기본 총 revision 2·retrieval 1·Gate 3은 설정 가능한 구조적 budget이며, 현재 수집되지 않는 aggregate token/time은 usage plumbing과 live 계측 뒤 B2로 연다. 최소 관측 schema는 후속 전체 artifact와 persisted loop 감사로 additive 확장한다.

## Follow-up considerations

- B2 budget increment에서 provider 응답 usage를 domain result까지 전달하고, 단계별 latency/search hit·context token을 함께 계측한 뒤 aggregate 기본값을 확정한다.
- 실 fixture에서 `revise→retrieve_more`, `retrieve_more→revise`, 동일 decision 반복의 빈도를 측정해 L4 상향 필요성을 판단한다.
- persisted GateRun이 열리면 stage ordinal, trigger finding fingerprint, input/output candidate hash, ContextPackage pointer를 immutable audit trail로 옮긴다.
- multi-finding은 finding 우선순위·anchor drift·부분 성공 envelope를 별도 결정한 뒤에만 자동화한다.

## Deferred / out of scope

- aggregate token/time 기본값과 provider usage contract 변경
- `max_retrieval_rounds>1`, auto-revision 2회 이상, pass까지 무제한 반복
- multi-finding 자동 수정과 non-continuity finding 수정
- Gate schema의 query/needs 확장
- 중간 candidate/report/context 본문 공개 또는 persistence
- save/accept/Analysis와 frontend

## 승인 후 첫 회귀 경계

1. `pass|needs_user_review|block`은 추가 revise/retrieve/provider 호출 없이 각각 `pass|terminal_decision`로 종료한다.
2. 자격을 만족하는 단일 continuity revise finding만 자동 수정한다. multi-finding, non-continuity, evidence 0회/2회 이상은 `not_eligible`이며 수정 호출 0이다.
3. revise 뒤 같은 merged ContextPackage로 report→Gate를 실행한다. retrieval 뒤 candidate/report는 유지하고 merge→Gate만 실행한다.
4. `revise→retrieve_more`와 `retrieve_more→revise` 모두 최대 Gate 3회 안에서 실행되고 각 action은 최대 한 번만 자동 수행한다.
5. 같은 auto decision이 다시 나오면 다음 action 호출 없이 `budget_exhausted`로 종료한다.
6. auto-revise unchanged는 200 `no_change`, 이전 candidate와 마지막 Gate를 보존하고 추가 호출 0이다.
7. 성공 응답은 candidate+최종 Gate와 loop counts/stages 순서를 정확히 노출한다. stage failure는 마지막 candidate/Gate와 실패 전 stages를 partial envelope로 보존한다.
8. request/project identity와 `candidate_id=null`을 유지하고 save/accept/Analysis/persistence 호출은 0이다.
9. component JSON repair는 기존 최대 1회이고 loop round count를 늘리지 않는다.
