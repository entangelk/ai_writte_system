# 착수 결정 브리프 — Phase 5.10 Writing loop aggregate token/time budget (L5 "B2 increment")

상태: `Resolved — 2026-07-13 (M1~M6 승인·구현)`

관련 정본: SoT v1.6.77 L5(구조적 call cap first, aggregate token/time은 usage 계측 뒤 B2)·v1.6.78(token/latency 집계는 B2 usage plumbing 후속), `05-writing-bounded-loop-decisions.md` L4/L5/L6, `flat-loop-gate.md` §Budget 계약(5차원·계측·초과·기본값), `docs/benchmarks/2026-06-30/gemma_q4_llama_cpp_repeats3_warmup1.json`

## Resolution

- 오너 결정: **M1=A, M2=A, M3=A, M4=A, M5=A first→B, M6=A first**.
- 이번 slice는 loop collaborator의 provider usage를 내부 `*_metered` 반환으로 전달하고, aggregate `total_tokens`와 monotonic `wall_clock_ms`를 집계·선택적으로 강제한다. token은 각 논리 provider 단계 뒤 post-accounting하며 누적 `> limit`인 결과를 채택하지 않고, wall-clock deadline은 다음 provider/search 단계 전에 검사한다.
- `WritingLoopPolicy.max_total_tokens|max_wall_clock_ms`와 `WRITING_LOOP_MAX_TOTAL_TOKENS|WRITING_LOOP_MAX_WALL_CLOCK_MS`를 추가하되 기본은 `None`(off)이다. production 숫자는 B2b full-stack loop benchmark 뒤 별도 확정한다.
- aggregate는 opt-in persisted audit의 summary/detail에만 additive로 노출한다. ephemeral `loop`/`stages`와 public candidate/Gate payload는 유지하며, 첫 Gate 전에 budget이 소진된 정상 결과만 `gate=null`일 수 있다.

> 문서 전반에서 "B2 increment"로 참조되는 후속을 구현 가능한 결정 단위 **M1~M6**(M = metering/budget)로 분리한다. "B2"는 이 increment 자체의 이름이고, M1~M6은 그 내부 세부 결정이다.

## Decision needed

`/writing/revise-and-gate` bounded loop(v1.6.77)는 현재 **구조적 call cap**(총 revision 2·retrieval 1·Gate 3 — `WritingLoopPolicy`)만 강제한다. `flat-loop-gate.md`의 5차원 budget 중 **aggregate total-token**과 **aggregate wall-clock**은 L5에서 명시적으로 B2로 미뤄졌다. 이유는 두 가지였다: (1) 현재 Writing domain service 결과가 provider `usage`를 loop까지 전달하지 않아 token을 집계할 수 없고, (2) aggregate 기본 숫자는 live 계측 없이 추측할 수 없다.

이 increment를 착수하려면 **usage/latency plumbing 방식, 강제할 차원, 강제 시맨틱, 관측 표면, 기본값 도입 posture**를 owner-level 계약으로 먼저 확정해야 한다. 이들은 기존 계약에서 하나로 도출되지 않고, 특히 M3(전파 방식)은 public envelope를 바꿀지 여부를, M6(기본값)은 "근거 없는 숫자 금지" 원칙과 live 계측 의존을 건드리므로 임의 구현하면 오너를 원치 않은 경로에 묶는다.

## 현재 확정된/관측된 경계 (구현 전 사실)

- provider 경계는 이미 usage를 반환한다: `GenerationResult.usage: TokenUsage(prompt_tokens, completion_tokens)` + `total_tokens` property (`services/llm_gateway/app/provider.py:12-27`). Gateway 계약(SoT §251-252)은 usage 누락/invalid를 0으로 보정하지 않고 `provider_invalid_response`로 본다.
- 구현 전에는 **Writing loop collaborator가 `result.usage`를 버렸다**: `revise`(부분 수정), `report.enrich`(초기 + repair 최대 2회), `gate.evaluate`(Gate), `retrieval.plan`(planner 초기 + repair 최대 2회). 이번 slice는 이 네 서비스에 내부 `*_metered` 변형을 추가했다. 합성 loop 밖 `service.generate`와 standalone endpoint usage 노출은 범위 밖이다.
- 한 loop 실행의 실제 provider 호출 수 = revise + report(+repair) + gate + [retrieve_plan(+repair) + context_search + Gate] 반복. 구조적 cap은 revise/gate/retrieval **round**를 세지, provider 호출/token/시간을 세지 않는다. repair 호출은 loop round가 아니라 component 내부 정책(L4)이므로 round count에 안 잡히지만 token/시간은 소비한다.
- generic `AgentLoopRunner`의 budget 5차원은 **tool 중심 loop**(`analysis_compare`/`context_search`/`writing_generate`)용이고, Writing 합성 loop는 여러 domain service를 orchestration하는 다른 층위다. `flat-loop-gate.md`의 정의는 재사용하되 generic runner를 그대로 끼우지는 않는다(L5=C 기각 근거).
- ContextPackage의 search-hit 수와 context token은 이미 **Context Gate의 `ContextBudget.max_tokens`**가 검증한다(loop 밖 계약). retrieval round는 L4가 1로 제한한다. 따라서 loop aggregate budget에서 진짜로 비어 있는 차원은 **total-token**과 **wall-clock** 둘이다.
- 감사 표면: ephemeral 응답 `stages`는 `{stage,ordinal,status}` 3키만(L6), persisted audit는 bodyless per-stage hash/fingerprint/pointer(P1=B). 둘 다 token/latency는 아직 없다(SoT v1.6.78 명시: "B2 후속").
- 계측 기본값의 근거는 `flat-loop-gate.md` §production 기본값의 절차(2026-06-30 Gemma Q4 live benchmark, `repeats=3`/`warmups=1`). 단일 turn 측정값: `continue_scene` p95 57.16s/max 407 tokens, `json_extraction` p95 8.70s/max 125 tokens. loop aggregate 값은 이 단일 turn 값의 **합**이므로 별도 loop-level 계측이 필요하다.

## Options table

### M1 — 이 increment의 범위 (plumbing / 강제 / 기본값의 분리)

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. plumbing + aggregation + configurable 강제, 기본값은 후속 | usage/latency를 domain 결과→loop로 전달하고, aggregate token/wall-clock을 집계·강제하는 기계를 넣되 **production 숫자는 live 계측(B2b) 후 확정**. 기본은 off/generous | 기계와 계약을 결정적으로 잠그고 fake provider로 회귀 검증 가능, 숫자는 근거 생긴 뒤 | 이 slice에서 tight한 운영 한도를 직접 강제하지 않음 |
| B. 이번에 production 기본 숫자까지 확정 | plumbing + 강제 + 실제 한도 값 | 완전한 운영 budget 한 번에 | live 계측 없이 숫자를 박아야 함 — "근거 없는 숫자 금지" 위반, L5 기각 논리 재현 |
| C. plumbing/관측만, 강제 없음 | usage를 audit에 기록만 하고 budget 강제는 전부 후속 | 변경 최소, 순수 관측 | budget "강제"라는 B2 목적을 이 slice가 달성 못 함; 기계 계약이 미확정으로 남아 다음 slice가 또 브리프 필요 |

추천: **A**. L5의 논리("L4는 강제 가능한 구조적 budget, aggregate는 계측 뒤")를 그대로 잇는다. 기계(전파·집계·강제 경로)는 fake provider로 결정적으로 잠글 수 있으므로 지금 확정하고, 유일하게 live에 의존하는 **숫자 기본값만 B2b로 분리**한다. 이는 v1.6.79 persisted audit이 취한 "기계는 지금, 운영 기본은 off/opt-in" posture와 일관된다.

### M2 — 강제할 aggregate 차원

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. total-token + wall-clock | `flat-loop-gate.md` 5차원 중 구조적 cap(L4)이 이미 덮지 않는 두 차원만 추가한다 | 중복 없이 정확히 빈 차원을 채움; generic 계약과 literal 일치 | search-hit/context-token은 loop budget으로 강제 안 함(Context Gate 소관으로 둠) |
| B. total-token만 | wall-clock은 component별 provider timeout에 맡긴다 | 최소 | loop 전체가 오래 도는 상황(반복·retry 누적)을 aggregate로 못 막음 |
| C. token + wall-clock + search/context-token | ContextBudget와 별개로 loop 차원에도 search-hit·context-token cap 추가 | 완전 | Context Gate `ContextBudget.max_tokens`와 이중 강제·의미 중복; retrieval 1회 cap이 이미 검색 폭을 제한 |

추천: **A**. 구조적 round cap(L4)이 provider 호출 수·retrieval 검색 수를 이미 bound하므로, 5차원에서 실제로 비어 있는 것은 total-token(post-accounting)과 wall-clock 둘뿐이다. search-hit/context-token은 loop budget이 아니라 Context Gate 계약에 남겨 이중 강제를 피한다(관측은 M5에서 별도).

### M3 — usage/latency 전파 방식 (아키텍처 — public envelope 영향)

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 내부 채널 (도메인 서비스가 `(result, TokenUsage)` 반환 또는 얇은 internal wrapper) | loop만 usage를 읽고 집계한다. public `WritingCandidate`/`WritingGateResult`/stages envelope는 **무변** | L6가 미룬 "ephemeral usage 비노출"을 지키면서 집계 가능; 공개 계약 불변 | 각 domain service 시그니처가 usage를 함께 반환하도록 확장(내부만) |
| B. domain 결과 dataclass에 `usage` 필드 additive, 직렬화만 제외 | `WritingCandidate.usage` 등을 추가하고 HTTP payload builder에서 제외 | 결과 하나로 전달 | public dataclass에 필드가 생겨 실수 노출 위험; candidate가 여러 stage를 거치며 어느 turn usage인지 모호 |
| C. loop이 metering accumulator를 각 service에 주입 | service가 side-channel로 usage를 accumulator에 push | loop 결과 shape 완전 불변 | seam이 늘고 service가 loop 상태를 알아야 함(결합↑), 테스트 대역 복잡 |

추천: **A**. 공개 envelope는 L6/P1이 정한 대로 유지하고 usage는 내부 채널로만 흐른다. domain service는 "무엇을 만들지"에 집중하되 자기 호출의 usage를 함께 돌려주는 것이 자연스럽다(loop이 turn 경계를 정확히 앎). 집계 결과의 공개 여부는 M5에서 별도로 결정한다.

### M4 — 강제 시맨틱

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. `flat-loop-gate.md` 미러 | token = post-accounting(각 응답 뒤 누적, 누적 `> limit`이면 초과 content 채택 안 하고 종료); wall-clock = 다음 stage 시작 전 deadline 검사; usage 누락/invalid는 0 보정 없이 provider 오류; 종료 시 마지막 완전한 candidate/Gate 보존 | 기존 budget 계약과 literal·의미 완전 일치, 학습 비용 0 | Writing loop엔 partial candidate가 있어 "초과 content 미채택"의 의미를 "마지막 완전 artifact 보존"으로 매핑해야 함(자연스러움) |
| B. pre-flight 추정 | 다음 stage의 예상 token을 미리 추정해 넘으면 시작 안 함 | 초과를 아예 안 만듦 | 추정 부정확, generic 계약과 불일치 |
| C. 관측만(강제 없음) | 누적만 하고 종료 안 시킴 | 단순 | M1=C와 동일 문제(강제 목적 미달) |

추천: **A**. token은 post-accounting 차원(응답 뒤에야 정확)이라 누적 후 초과 시 `budget_exhausted`로 종료하고 마지막 완전한 candidate/최근 Gate를 보존한다(기존 partial envelope 재사용). wall-clock은 다음 stage(provider/search) 시작 전 monotonic deadline을 검사한다 — mid-provider cancellation은 component별 provider timeout에 맡긴다. usage 누락은 Gateway가 이미 `provider_invalid_response`로 처리하므로 loop은 그 provider 오류를 그대로 전파한다(0 보정 금지).

### M5 — 집계값 관측 표면

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. persisted audit에만 additive | `StoredWritingLoopRun`에 aggregate `total_tokens`/`wall_clock_ms`(+선택적 per-stage) 추가. ephemeral 응답은 무변 | L6("ephemeral usage 비노출")·P1(감사가 hash/pointer 흡수) 원칙과 일치; opt-in 감사에만 실림 | audit off면 caller가 실측 집계를 못 봄 |
| B. audit + ephemeral `loop` 요약 additive | `loop:{...}`에 `total_tokens`/`wall_clock_ms` additive | budget 종료 이유를 caller가 즉시 봄 | L6가 미룬 usage 공개를 지금 여는 것 — public schema 확대 |
| C. per-stage token/latency까지 stages/audit에 공개 | 각 stage row에 usage/latency | 디버깅 풍부 | L6=C(전체 artifact)를 선점, 비영속 응답에 과함 |

추천: **A first→B**. 집계값을 우선 persisted audit(P1/P4의 additive 자리)에만 실어 L6 원칙을 지키고, budget 종료를 caller가 실시간으로 구분할 필요가 구체화되면 ephemeral `loop` 요약에 additive로 공개한다. per-stage 세부(C)는 전체 artifact 감사(L6=C)와 함께 연다.

### M6 — 기본값 posture와 숫자 출처 (live 의존)

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. off/opt-in 기본, 숫자는 B2b live 계측 후 | aggregate cap 기본 = None(무제한). `WritingLoopPolicy` 필드 + env로 활성화. production 숫자는 loop-level Gemma Q4 benchmark(B2b)로 확정 | 근거 없는 숫자 안 박음; 구조적 cap(L4)이 이미 loop을 bound; v1.6.79 opt-in posture와 일관 | 활성화 전에는 aggregate 한도 미강제(구조적 cap만) |
| B. 단일 turn benchmark×round로 도출한 generous ceiling 기본 on | 2026-06-30 값(continue_scene 407 tok/57s 등)에 최대 round를 곱한 안전 상한을 기본 on | 첫날부터 폭주 방어선 존재 | 곱셈 추정은 loop 실측이 아님; tight budget 오해 위험 → 명시적 "ceiling(안전 상한)"으로만 문서화해야 함 |
| C. 이 slice 차단, live 계측 먼저 | 숫자 확정 전엔 구현 안 함 | 숫자 근거 확실 | 기계·계약이 계속 미확정, full-stack 머신 배치까지 Writing 트랙 정지 |

추천: **A first, ceiling(B)은 후속 옵션**. 기본은 off(무제한, 구조적 cap만 강제)로 두어 근거 없는 숫자를 피하고, 활성화 훅(`WritingLoopPolicy`의 `max_total_tokens`/`max_wall_clock_ms` optional 필드 + `WRITING_LOOP_MAX_TOTAL_TOKENS`/`WRITING_LOOP_MAX_WALL_CLOCK_MS` env)만 배선한다. production 숫자는 **B2b**(full-stack 머신, loop-level benchmark로 `revise→report→gate` 및 `retrieve→gate` 실측 누적)에서 `flat-loop-gate.md` 절차대로 확정한다. 필요하면 그때 (B)의 generous ceiling을 잠정 기본으로 승격할 수 있다.

## Recommendation + reason

추천 묶음: **M1=A, M2=A, M3=A, M4=A, M5=A first→B, M6=A first(ceiling B 후속)**.

로컬 1인 프로젝트 단계에서 이 increment의 가치는 "loop이 무한/폭주하지 않도록 aggregate 차원을 **강제 가능한 형태로 확정**"하는 것이지, 검증 안 된 숫자를 박는 게 아니다. 따라서:
- provider→domain→loop usage 전파와 wall-clock 계측을 **내부 채널**로 넣어 public envelope를 건드리지 않고(M3=A), `flat-loop-gate.md`와 동일한 post-accounting/deadline 시맨틱으로 강제하며(M4=A), 실제로 빈 두 차원(total-token·wall-clock)만 채운다(M2=A).
- 집계값은 opt-in persisted audit에 우선 싣고(M5=A), 기본은 off로 두어(M6=A) 구조적 cap(L4)만으로도 loop이 이미 유한함을 유지한다.
- 유일하게 live에 의존하는 production 숫자는 B2b로 명시 분리해, 이 slice는 fake provider로 결정적으로 회귀 검증 가능하다.

이 posture는 같은 날 확정한 v1.6.79(감사 opt-in, 기계는 지금·운영 기본은 off)와 정확히 대칭이라 계약 학습 비용이 낮다.

## Follow-up considerations (문을 열어둘 것)

- **B2b (live 계측·숫자 확정)**: full-stack Gemma Q4 머신에서 loop-level benchmark(`revise→report→gate`, `retrieve→gate`, 반복 조합)로 aggregate token/wall-clock p95를 측정해 production 기본값을 `flat-loop-gate.md` 절차로 확정하고, 필요 시 off→on 승격.
- per-stage token/latency 공개(M5=C)와 전체 중간 artifact(L6=C)를 함께 열 때 audit stage row schema를 확장한다.
- `WritingService.generate`(합성 loop 밖 단발 생성)와 standalone `/writing/revise`·`/writing/report`·`/writing/gate`에도 같은 usage 전파를 additive로 확장할지 — 이번엔 loop endpoint에 한정.
- generic `AgentLoopRunner`의 usage budget(I2 forward-lock)과 Writing loop budget이 언젠가 수렴할지 여부는 tool-call branch가 열릴 때 재검토.

## Deferred / out of scope (이번에 결정하지 않는 것)

- aggregate token/wall-clock의 **production 기본 숫자값**(= B2b, live 계측 의존).
- search-hit/context-token을 loop budget 차원으로 강제(Context Gate `ContextBudget`에 유지).
- per-stage usage/latency의 ephemeral·stages 공개, 전체 중간 artifact.
- standalone(비-loop) writing endpoint의 usage 노출.
- provider 응답의 latency를 Gateway가 반환하도록 하는 변경(loop은 자체 monotonic 계측; Gateway timing 필드 추가는 별도).
- save/accept/Analysis side effect, frontend.

## 승인 후 첫 회귀 경계 (red-first lock list)

1. loop이 revise/report/gate/retrieval planner의 각 provider 응답 usage를 **정확히 한 번씩** 누적한다. report/retrieval의 repair 2번째 호출 usage도 포함하고, 같은 turn을 이중 계산하지 않는다.
2. `max_total_tokens` 활성 시: 누적 `== limit`이면 완료 허용, 누적 `> limit`이면 초과 stage content를 채택하지 않고 `budget_exhausted`로 종료하며 **마지막 완전한 candidate와 최근 Gate**를 보존한다(under-strict: 초과를 성공 위장 금지 / over-strict: 한도 내 정상 완료를 조기 차단 금지).
3. `max_wall_clock_ms` 활성 시: 다음 stage(provider/search) 시작 전 monotonic deadline이 지났으면 `budget_exhausted`, 남았으면 진행. component provider timeout은 여전히 그 component의 provider 오류다(budget과 구분).
4. 기본(두 한도 None): aggregate 강제 없음 — 구조적 cap(L4)만으로 종료하며 v1.6.77 동작과 byte-동일(회귀 무변 증명).
5. provider 응답 usage 누락/invalid는 0으로 보정하지 않고 provider 오류를 전파한다(Gateway `provider_invalid_response` 미러).
6. public `WritingCandidate`/`WritingGateResult`/ephemeral `stages`(3키)/ephemeral `loop` 요약 shape는 M5=A 범위에서 **무변**이다(usage는 audit에만).
7. persisted audit 활성 시 `StoredWritingLoopRun`에 aggregate `total_tokens`/`wall_clock_ms`가 additive로 실리고, 비활성(opt-out)이면 종전과 동일(감사 0건).
8. `WritingLoopPolicy(max_total_tokens=..., max_wall_clock_ms=...)`와 env 배선이 실제 상태 전이를 바꾸고(양방향), 값 미설정은 무제한을 뜻한다.
