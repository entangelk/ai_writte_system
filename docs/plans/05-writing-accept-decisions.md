# 착수 결정 브리프 — Phase 5.3 Writing accept→save→analysis 재진입

상태: `Resolved` (D1=A·D3=A·D4=A·D6=A·D7=A, D2=A first→C, D5=A first→C)
관련: `system-contract-sot.md` v1.6.69, `plans/05-writing-ai.md` §흐름/수용 기준, `plans/05-writing-generation-decisions.md`(continue_scene=`draft_patch`), `plans/05-writing-gate-decisions.md`(Gate side-effect-free·비영속), Core SOT explicit version save, Phase 2A job/run 계약

## Decision needed

사용자가 통과한 WritingCandidate를 accept할 때 어느 draft version에 어떤 byte 규칙으로 반영하고, 비영속 Gate를 어떻게 신뢰하며, 저장 성공 뒤 Analysis를 어디까지 자동 진행할지 확정해야 한다. 이 선택은 새 draft snapshot과 public accept API의 성공/재시도 의미를 바꾸므로 기존 계획에서 추측할 수 없다.

## Owner decisions — 2026-07-12

- **D1=A, D3=A, D4=A**: 추천안 채택(별도 이견 없음). base version 필수/stale 409, accept 시 Gate 재평가/pass만 저장, accept idempotency key로 save/job key 파생.
- **D2=A first, C 확장 고려**: 첫 slice는 결정적 paragraph append. 서비스/API 모델은 후속 client 지정 separator/offset patch contract를 additive로 열 수 있게 둔다.
- **D5=A first, C 확장 고려**: 첫 slice는 pending Analysis job 생성. job identity/상태를 응답해 후속 background run이 같은 job을 소비할 수 있게 둔다.
- **D6=A, D7=A**: Gate non-pass는 `200 accepted=false`; save 후 job 생성 실패는 saved artifact를 포함한 `502 partial-success`로 반환하고 same-key retry로 수렴한다.

## Options table

### D1 — 적용 대상과 stale base 처리

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. `draft_id + base_version_id` 필수, latest가 아니면 409 | accept가 명시 base snapshot을 읽고 현재 latest와 같을 때만 적용한다 | 다른 편집을 덮어쓰지 않고 재현 가능하다 | stale UI는 다시 생성/재검토해야 한다 |
| B. `draft_id`만 받고 항상 latest에 append | 서버가 accept 시점 latest를 사용한다 | 클라이언트 입력이 작다 | 생성·Gate 때 본 원문과 다른 version에 조용히 붙을 수 있다 |
| C. 클라이언트가 완성 `raw_text` 제출 | 기존 save API를 그대로 호출한다 | 서버 merge 규칙이 없다 | candidate 외 임의 본문 변경을 accept로 위장할 수 있다 |

추천: **A**. Writing 생성과 Gate가 본 편집 기준을 accept까지 보존하고 concurrent/stale overwrite를 409로 명시한다.

### D2 — `draft_patch` 결합 literal

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 결정적 paragraph append | base가 비면 candidate 그대로, base가 newline으로 끝나면 그대로 concat, 아니면 `\n\n` 뒤 candidate를 붙인다 | 최소 규칙으로 자연스러운 scene continuation, byte 재현 가능 | 사용자가 한 줄 개행을 원한 경우와 다를 수 있다 |
| B. 무조건 exact concat | separator를 추가하지 않는다 | byte 규칙이 가장 단순하다 | 기존 마지막 문장과 candidate가 붙을 수 있다 |
| C. 클라이언트가 separator/offset 지정 | append 위치와 separator를 요청에 포함한다 | editor 유연성 | 첫 continue_scene slice에 patch 편집 계약이 과도하게 커진다 |

추천: **A**. continue_scene 전용 최소 append 규칙이며 revision patch/선택 영역 replace는 후속으로 분리한다.

첫 slice의 candidate patch는 저장 전 외곽 whitespace를 `strip()`하고, 그 결과를 위 separator 규칙으로 결합한다. 내부 whitespace는 보존한다. 후속 C가 offset/separator를 열 때 whitespace 처리도 명시 입력으로 확장할 수 있다.

### D3 — accept 시 Gate 신뢰 경계

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. accept endpoint가 Gate를 다시 평가하고 `pass`만 저장 | 비영속/클라이언트 위조 문제 없이 서버가 최종 안전성을 보장한다 | LLM·context-search 호출이 다시 필요하고 accept latency가 늘어난다 |
| B. 클라이언트가 GateResult를 제출 | 추가 호출이 없다 | 비영속 결과를 위조하거나 다른 candidate 결과를 재사용할 수 있다 |
| C. GateResult를 먼저 영속화하고 id 참조 | 단일 평가와 감사 추적 | Gate persistence라는 별도 큰 slice가 선행돼야 한다 |

추천: **A**. 오너가 내부 LLM 호출 수보다 정확도를 우선한다고 확정했고, 현재 GateResult는 의도적으로 비영속이다. `pass` 외 decision은 저장하지 않으며 결과를 그대로 응답한다.

### D4 — accept idempotency

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. `idempotency_key` 필수, save/job 파생 key로 재사용 | `(project,draft,key)` save replay와 `(project,snapshot,derived key)` job replay를 하나의 사용자 intent로 묶는다 | key 파생 literal을 계약해야 한다 |
| B. candidate text hash로 서버 파생 | 클라이언트 key가 없다 | 같은 prose를 다른 의도로 두 번 accept하기 어렵다 |
| C. idempotency 없음 | 구현이 작다 | retry가 draft version과 analysis job을 중복 생성한다 |

추천: **A**. Core SOT/Analysis의 기존 idempotency choke point를 재사용한다. save key=`writing-accept:{idempotency_key}`, analysis key=`writing-accept:{idempotency_key}`로 각 저장소의 project/draft 또는 project/snapshot scope가 충돌을 방지한다.

### D5 — Analysis 재진입 깊이

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. save 후 pending Analysis job 생성까지 | 저장 성공과 LLM 분석 실패를 한 응답에서 혼동하지 않고 기존 `/run`을 재사용한다 | 사용자가 별도 run 호출을 해야 후보가 생긴다 |
| B. save→job 생성→동기 run까지 | 한 요청으로 분석 후보까지 생성돼 핵심 루프가 완전히 닫힌다 | provider 실패 시 draft는 이미 저장됐는데 HTTP 실패처럼 보이는 partial-success 계약이 필요하다 |
| C. save 후 background run | accept latency가 작고 자동 분석된다 | 현재 background queue/lifecycle 계약이 없고 restart 복구를 새로 정해야 한다 |

추천: **A first**. 첫 slice는 정본 write와 analysis re-entry(job identity)까지 원자적으로 이해 가능한 envelope로 닫고, UI/호출자가 기존 run endpoint를 명시 실행한다. B는 후속 additive orchestration으로 열어 둔다.

### D6 — Gate non-pass의 HTTP 의미

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. HTTP 200 + `accepted=false` + GateResult | revise/retrieve/review/block을 정상 business outcome으로 반환하고 write는 0건이다 | editor가 decision을 그대로 처리하며 오류 retry와 구분된다 | HTTP 성공을 단순히 저장 성공으로 해석하면 안 된다 |
| B. HTTP 409 | 현재 candidate가 accept 불가 상태임을 conflict로 표현한다 | 저장되지 않았음이 강하게 보인다 | 정상 Gate 판정을 transport error처럼 다루게 된다 |
| C. HTTP 422 | accept 조건 미충족으로 표현한다 | validation 계열과 가깝다 | 모델 판정 결과와 malformed input을 혼동하기 쉽다 |

추천: **A**. Gate decision은 오류가 아니라 editor workflow의 정상 분기다. `accepted` boolean을 machine contract로 둔다.

### D7 — save 성공 후 Analysis job 생성 실패

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 502 partial-success envelope + 같은 key retry 수렴 | `accepted=true`, saved version/snapshot, `analysis_job=null`, `analysis_error`를 반환하고 재시도는 save replay 뒤 job 생성을 다시 시도한다 | 정본 commit을 숨기지 않고 운영 복구 가능하다 | 502 응답에 성공 artifact가 포함되는 복합 envelope다 |
| B. save만 성공한 200 + warning | 저장 성공을 우선한다 | 클라이언트가 warning을 놓치면 분석 재진입이 영구 누락될 수 있다 |
| C. cross-store transaction 도입 | save와 job을 원자 처리한다 | 가장 강한 일관성 | Core SOT/Analysis repository 경계를 깨고 in-memory/Mongo 양쪽 대규모 변경이 필요하다 |

추천: **A**. 두 저장소가 이미 독립 idempotency를 가지므로 같은 accept key replay가 자연스러운 수렴 수단이다. HTTP error detail만 던지지 말고 saved artifact를 구조화해 반환한다.

## Recommendation + reason

**D1=A, D2=A first→C, D3=A, D4=A, D5=A first→C, D6=A, D7=A**를 추천한다. 로컬 1인 프로젝트여도 원고 정본은 stale overwrite를 허용하면 안 되며, accept는 사용자가 명시한 단일 write intent로 idempotent해야 한다. Gate 재평가는 정확도 우선이라는 기존 결정과 맞고, 분석 run을 분리하면 이미 commit된 draft를 provider 장애 때문에 실패로 오해하지 않는다.

## Follow-up considerations

- generate→gate→accept 합성 API는 각 독립 service가 잠긴 뒤 additive로 제공할 수 있다.
- 동기 analysis run을 추가할 때는 `save_status`와 `analysis_status`를 분리한 partial-success envelope 및 HTTP status를 먼저 결정한다.
- candidate/Gate persistence가 생기면 inline candidate text 대신 immutable candidate id와 GateRun id를 참조할 수 있다.
- revision patch는 source offset/hash 또는 editor selection anchor 계약을 별도로 연다.

## Deferred / out of scope

- 자동 analysis run과 retry/background worker
- revision patch/선택 영역 replace/full draft merge
- WritingCandidate·GateResult 영속화 및 Review Inbox 통합
- accept 취소/rollback, version 삭제, canon 자동 승격
- 구조적 self-report와 memory hint 직접 적용

## 승인 후 첫 회귀 경계

1. pass Gate + latest base → 결정적 raw_text append + 새 immutable version/snapshot.
2. Gate가 pass가 아니면 draft version/job 모두 생성 금지; 정상 pass는 저장 가능.
3. stale base/cross-project draft-version은 provider 또는 write 전에 409/404.
4. 빈 candidate/instruction/key, unsupported task/output type은 400.
5. 같은 accept key replay → 같은 version/snapshot/job, Gate/save/job side effect 중복 없음.
6. 다른 accept key → 다음 version과 별도 analysis job.
7. save 성공 → 새 snapshot을 가리키는 pending Analysis job 생성; run은 호출하지 않음.
8. archived project/draft는 409, missing project/draft/version은 404.
9. Gate/context/provider 오류는 draft/job 성공으로 위장하지 않음(502/504); Gate 호출 전 결정적 validation 실패는 provider 미호출.
10. 기존 generate/gate/save/job/run API 계약은 변경하지 않는 additive endpoint.
11. Gate non-pass는 정상 `accepted=false` outcome이며 transport/provider 오류와 구분.
12. save 후 job write 실패는 saved artifact를 숨기지 않고 같은 accept key replay로 pending job 생성에 수렴.
