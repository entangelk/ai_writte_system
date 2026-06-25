# HANDOFF

## Current Status

- `docs/` 루트의 기존 설계 문서는 초기 아이디에이션 자료로 분류되어 있다.
- 실제 개발 준비용 진입점은 `docs/plans/README.md`다.
- 서비스 경계와 확정 계약을 모은 정본 SoT 초안은 `docs/system-contract-sot.md`다.
- 계획은 공통 기반, Product Shell, 분석 memory taxonomy, Phase 1~6으로 나뉘어 있다.
- Product Shell과 Phase 계획은 `Draft`, 분석 taxonomy는 `Discussion` 상태다.
- 전체 구현 순서 문서는 `Draft`, LLM Gateway 경계는 `Proposed` 상태다.
- Slice 0.1~0.5가 구현됐다: payload, provider/fake, error envelope, transport mapping, fake-transport llama.cpp client.
- Slice 0.6 httpx adapter와 mock contract가 구현됐다. actual adapter live smoke는 독립 검증 환경에서 완료됐다.
- Git repository이며 Slice 0.6 httpx adapter가 구현·검증·커밋됐다.
- Slice 0.1~0.5의 F1/F2 조건이 delta 독립 재검증으로 폐쇄됐고 조건부 합격이 합격으로 승격됐다.
- flat loop 종료 decision, tool registry, budget policy, task별 completion criteria 계약이 `docs/plans/flat-loop-gate.md`에 확정됐다. 숫자 기본 한도만 후속(benchmark 이후)이다.
- Gateway optional `usage`→0과 token budget의 충돌은 usage/count 필수화로 해소됐다. 누락은 `provider_invalid_response`, 명시적 0은 유효하다.

## Active Decisions

- 긴 `abstract.md` 원본은 보존한다.
- 구현 Phase를 계획의 주 축으로 사용하고 공통 설계 원칙은 별도 문서로 관리한다.
- Phase와 MVP를 서로 다른 축으로 관리한다.
- 아이디에이션과 계획이 충돌하면 임의로 구현하지 않고 사용자 결정을 받는다.
- MVP는 계정/인증이 없는 단일 사용자 시스템이며 프로젝트 경계는 `project_id`로 유지한다.
- 기존 기억의 갱신은 AI가 직접 덮어쓰지 않고 검색·대조·Gate·검토·versioned upsert를 거친다.
- 제안 아키텍처는 monorepo + modular Application + 독립 LLM Gateway/Worker다. 사용자 승인 전이다.
- `/mnt/d/devel/gemma4_12b` commit `485c4e2`를 참조 구현으로 검토했으며 model/quant는 공식 QAT GGUF Q4_0으로 확인됐다. 실제 실행 hardware는 미확정이다.
- sub-agent spawn은 제외하고 bounded flat loop만 사용한다.
- 외부 `gemma4_12b`는 선택적 provenance이며 현재 repo runtime dependency가 아니다.
- 외부 서버 수정은 완료됐고 direct live endpoint `192.168.1.29:9080`을 사용할 수 있다.
- direct curl smoke는 성공했고, actual adapter live smoke는 독립 검증 환경에서 완료됐다.
- flat loop 종료 decision 7종(completed/awaiting_review/blocked/budget_exhausted/invalid_tool_arguments/tool_error/provider_error)을 확정했고, Loop/Analysis/Context Gate는 다른 층위(직교)로 병합하지 않는다.
- Loop의 `needs_review`를 `awaiting_review`로 rename(Analysis candidate status 충돌 해소), `provider_error`는 umbrella + Gateway 5 literal은 trace 보존, `completed`는 loop 종료 상태만(domain Gate 통과 별개)으로 정했다.
- flat loop registry는 Application/Worker 소유, task별 서버 allowlist, strict JSON Schema validation, read-only v1 tool 6종을 사용한다. `project_id`는 모델 인자가 아니라 신뢰된 실행 context에서 주입한다.
- `analysis_compare`는 5종, `context_search`는 3종 tool을 허용하고 `writing_generate`는 tool을 허용하지 않는다. compare/validate tool은 preflight이며 독립 domain Gate를 대체하지 않는다.
- budget은 iteration/wall-clock/total-token/tool-call/repeated-call 5차원을 사용한다. retry도 같은 budget을 소비하며, 초과는 성공으로 위장하지 않는다.
- budget/retry production 숫자 기본값은 Gemma Q4 benchmark 뒤에 확정한다. 그전 contract test는 명시값을 주입한다.
- completion 판정은 하이브리드(구조 조건 AND self-report)다. self-report는 loop 종료 채널의 `finalize` vs `defer` 결정이며 candidate status(산출물 데이터 채널)와 직교한다. `analysis_compare`의 부분 모호는 run `completed`+candidate status, tool 없는 `writing_generate`는 산출물 모호 `defer` 시 `awaiting_review`. completion matrix는 `task × {completed, awaiting_review}` 횡일관 2행으로 양방향 lock(독립 검증 R1/R2/R3 보강 완료).
- self-report wire 형식은 provider 응답 JSON object의 top-level `self_report` field다. 값은 정확히 `finalize` 또는 `defer`이고, 산출물 내부 nested `self_report`는 종료채널이 아니다.
- AgentLoopRunner A1/A2/A3가 구현됐다. `services/application/app/agent_loop/`에 `LoopDecision`(7종), `BudgetPolicy`(5차원 budget + retry cap + allows_tools)/`BudgetTracker`(F1 usage 방어), `ToolRegistry`(profile allowlist·strict arguments·canonical signature), `judge_completion`(completed/awaiting_review 하이브리드 판정), `resolve_retry`/`next_step_budget_decision`(retry 우선순위·budget→budget_exhausted 매핑)을 fake/인프라 없이 양방향 회귀로 잠갔다. 러너 실구동(종료채널 wire parsing·provider/tool 호출 순서·trace 조립)·실제 tool handler(Slice 1·3 이후)는 미구현이다.
- flat loop 종료 decision 합성 원시가 A3로 잠겼고 독립 검증 합격 후 I1/I3를 보강했다. self-report는 `SelfReport`(FINALIZE/DEFER) enum 주입이고 wire 형식은 parser slice에서 확정. retry cap은 `BudgetPolicy.provider_retry_cap`/`tool_retry_cap`(0 이상)으로 실현됐다(검증 I1 폐쇄). I2(runner 합성 순서)는 runner slice의 forward-lock.
- self-report 종료채널 parser slice가 구현됐다. provider 응답 `content`는 JSON object이고 top-level `self_report` field 값은 정확히 `finalize`/`defer`만 허용한다. 누락·malformed/non-object JSON·non-string·case variant·artifact nested `self_report`는 `InvalidSelfReport(decision=provider_error)`다. runner 연결은 미구현이다.
- `docs/system-contract-sot.md`가 추가됐다. 현재는 `Draft` 초안이며 사용자 검토 후 정본으로 승격할지, 범위를 조정할지 결정해야 한다.

## Next Tasks

1. `docs/system-contract-sot.md` 검토: 문서 우선순위와 미확정 결정 목록이 원하는 정본 역할을 하는지 확인하고 `Draft` 유지/수정/Approved 승격 방향 결정. (precedence tree는 독립 검증 R1 보강으로 SoT↔plans/README 통일 완료)
2. 러너 실구동(Slice 1·3+): `parse_self_report_payload` 연결, provider/tool 호출 순서, trace 조립.
3. 러너 slice에서 검증 I2 forward-lock 회귀: `next_step_budget_decision`을 completion/retry 결정보다 먼저 호출(budget_exhausted가 completed로 위장 금지), retry 시 동일 차원 budget 소비(retry 비-무료성).
4. Gemma Q4 benchmark 후 budget/retry production 숫자 기본 한도 확정(retry cap 구조는 `BudgetPolicy`에 폐쇄됐고 숫자 기본값만 남음).

## Verification

- 계획 문서의 상대 링크와 원문 추적표 확인
- tool registry 계약과 Phase 2/4/5 연결 문구 및 양방향 boundary matrix 확인
- tool registry 계약 독립 검증 합격: `docs/verifications/2026-06-24/flat_loop_tool_registry.md`
- Gateway usage/count 누락 거절과 명시적 0 수용 focused regression 확인
- usage 필수화 후 actual adapter live smoke 재통과: content `연결 확인 완료`, finish `stop`, usage `23/5/28`
- 각 Phase 문서의 필수 planning section 확인
- 원본 `docs/abstract.md` 본문 보존 확인
- Product Shell과 analysis taxonomy의 계획 링크 및 Phase 연결 확인
- 구현 slice의 선후 관계와 LLM Gateway contract/model-test 분리 확인
- 현재 repo contract test 44개 통과. optional usage lock은 사용자 결정으로 missing-usage rejection으로 반전됐고 명시적 0 수용 guard는 유지됨
- 참조 repo unit contract test 8개 통과; 정책상 실모델 smoke는 보류
- Slice 0.1~0.5 독립 검증(2026-06-24): 조건부 합격. 기록 `docs/verifications/2026-06-24/llm_gateway_slice_0_1_to_0_5.md`. 당시 조건은 F1(기본값 True 미고정)·F2(spec-silent 거부의 계약 지위)였고 현재 구현 보강은 완료됐다.
- F1/F2 구현 보강 완료, delta 독립 재검증 합격(2026-06-24): F1 양방향 변이 증명(else False→true-test FAIL, else True→false-test FAIL), F2 request/response precondition이 `llm-gateway.md`에 명문화되고 13개 delta branch가 회귀에 1:1 매핑, live smoke 6항목 재실행 일치. 기록 `docs/verifications/2026-06-24/llm_gateway_f1_f2_closure.md`. 조건부 합격을 합격으로 승격.
- direct live smoke: health ok, model QAT GGUF Q4_0/context 8192, non-thinking 한국어 completion 성공
- Slice A1(decision+budget) 독립 검증(2026-06-24): 합격. 63/63 재현, 변이 증명 양방향·복원 정확·코드↔계약 line 단위 일치 입증, blocking 없음. F4(경계 테스트) 즉시 보강해 65개, F1(Gateway→budget usage 방어)은 A3로 이월. 기록 `docs/verifications/2026-06-24/agent_loop_a1_decision_budget.md`
- Slice A2(tool registry+strict arguments+signature) 자체 회귀(2026-06-25): focused 20개 통과, 전체 85개 통과. pattern sweep에서 위험한 중복 구현 없음.
- Slice A2 독립 검증(2026-06-25): **합격**(조건부 → 승격). allowlist/registration/strict args/blocked-vs-invalid/signature는 계약 literal 그대로 정확하고 양방향 lock 됨. 독립 검증이 §33 "enum, bounds 적용" 명시와 구현의 enum/bounds 미검증 불일치를 실증 발견 → 사용자 결정(option a)으로 v1/A2 validator 범위를 `{required, type, additionalProperties, array items}`로 §33·plan §138·CHANGELOG에 명시 좁히고 enum/bounds는 keyword 사용 tool 등록 시점까지 deferred로 reconcile. triggered 조건: enum/bounds 사용 tool 첫 등록 시 검증+회귀 추가. 기록 `docs/verifications/2026-06-25/agent_loop_a2_registry.md`
- A2 독립 검증의 비차단 I2/I3는 후속 보강 완료(2026-06-25): 중첩 object schema와 array `items`를 등록 시점에 재귀 검증하고 `_validate_arguments`의 `assert`를 명시 검사로 교체. enum/bounds deferral은 유지됨.
- Slice A3(completion 판정·retry/budget decision 합성·F1 usage 방어) 자체 회귀(2026-06-25): focused agent_loop 73개(decision 4 + budget 25 + registry 20 + completion 6 + resolution 18), 전체 117개 통과. 4곳 핵심 분기 변이로 양방향 lock 증명(completion `and/or`, retry cap 소진, token budget 매핑, F1 음수 수용).
- Slice A3 독립 검증(2026-06-25): **합격**. 117/117·per-module 6/18/25 재현, 4표면(completion/retry/budget 매핑/F1)이 정본 계약 literal 그대로 정확, 빈 칸 없음. 비차단 3건: I1(retry cap 정책 근원 부재=유일 spec↔impl 갭)·I3(exception uniformity 절반)은 보강으로 폐쇄, I2(runner 합성 순서)는 spec이 A3를 순수 원시로 규정해 runner slice forward-lock. 기록 `docs/verifications/2026-06-25/agent_loop_a3_completion_resolution.md`.
- A3 검증 후 보강(2026-06-25): I3(`InvalidBudgetPolicy.decision=BLOCKED`), I1(`BudgetPolicy`에 `provider_retry_cap`/`tool_retry_cap` 0 이상 추가, 사용자 결정 Option A). 전체 117→121, retry cap 검증 변이 증명(`_RETRY_DIMENSIONS=()` FAIL/복원 PASS).
- self-report parser slice 자체 회귀(2026-06-25): focused parser+completion 14개 통과, 전체 discovery 129개 통과. 패턴 sweep에서 기존 parser/default/nested-field 오인 경로 없음.
- self-report parser slice 독립 검증(2026-06-25): **합격**. 14/129 재현, boundary matrix 9분기 전 매핑(branch-level 빈 칸 없음), spec↔code 리터럴 행 단위 일치, 양방향 guard·패턴 sweep·예외→decision uniform 매핑 확인. 비차단 R1('오타' value-sample 비고 — 동일 분기가 이미 lock됨). 기록 `docs/verifications/2026-06-25/self_report_parser.md`
- self-report parser R1 보강 완료(2026-06-25): wrong well-formed literal `done` 거부 sample 추가. focused parser+completion 15개 통과, 전체 discovery 130개 통과.
- System Contract SoT 초안 독립 검증(2026-06-25): **합격**. SoT가 인용한 literal(5 provider·5 Analysis·3 candidate·7 decision·6 tool·3 allowlist·budget 임계)·status·링크가 정본과 문자열 그대로 일치하고 enum/bounds deferral이 정확히 전파됨. 같은 묶음의 A2 I2/I3 비차단 권고도 코드+양방향 회귀로 폐쇄(registry 18→20, 전체 85/85). 비차단 risk R1(SoT↔plans/README precedence tree 불일치)도 검증자가 직접 reconcile로 폐쉄 — plans/README tree를 SoT 5-level과 통일하고 SoT를 정본 precedence로 defer. 기록 `docs/verifications/2026-06-25/system_contract_sot.md`
- completion criteria 계약 독립 검증(2026-06-24): 조건부 합격. 워커 보고·내부 일관성·cross-reference 4종 독립 확인, blocking 없음. 비차단 risk R1/R2(matrix 비대칭)·R3(self-report 정의 갭)를 소유자 결정으로 본 slice에서 즉시 보강했다. 기록 `docs/verifications/2026-06-24/completion_criteria_contract.md`
- Slice 0.6 독립 검증(2026-06-24): 합격. httpx MockTransport/proxy/close 경계 6개 회귀 통과, `except` 순서 load-bearing 가정 4종 검증. 독립 검증 환경에서 `HttpxJsonTransport` 경유 actual adapter live smoke 완료(content `연결 확인 완료`, finish_reason=stop). 기록 `docs/verifications/2026-06-24/llm_gateway_slice_0_6_httpx.md`

## Project Structure

```text
docs/
├── README.md                    # 문서 분류와 진입점
├── system-contract-sot.md       # 서비스 경계와 확정 계약 SoT 초안
├── abstract.md                  # 보존된 전체 아이디에이션 원본
├── *.md                         # 주제별 상세 아이디에이션
├── plans/
│   ├── README.md                # 계획 인덱스, 우선순위, Phase/MVP 관계
│   ├── 00-foundations.md
│   ├── product-shell.md         # 프로젝트/원고 관리와 내보내기
│   ├── analysis-memory-taxonomy.md # 분석 대상 및 갱신 논의안
│   ├── implementation-plan.md   # vertical slice와 검증 계획
│   ├── llm-gateway.md           # 모델 서빙 경계와 Gemma Q4 검증
│   ├── gemma4-reuse.md          # 기존 구현 선택 이관과 Loop Gate 보강
│   ├── flat-loop-gate.md        # flat loop decision/tool registry/budget policy 계약
│   └── 01-core-sot.md ~ 06-review-ui.md
└── daily_logs/
    ├── 2026-06-24/work_log.md
    └── 2026-06-25/work_log.md
services/
├── llm_gateway/
│   ├── requirements.txt
│   └── app/
│       ├── payload.py          # portable llama.cpp payload contract
│       ├── provider.py         # provider protocol과 deterministic fake
│       ├── errors.py           # stable provider error envelope
│       ├── transport.py        # JSON transport/fake와 status error mapping
│       ├── client.py           # llama.cpp text completion provider
│       └── httpx_transport.py  # 실제 async HTTP JSON adapter
└── application/
    └── app/
        └── agent_loop/
            ├── budget.py       # BudgetPolicy(5차원 budget+retry cap)/BudgetTracker+F1 usage 방어(A1/A3)
            ├── completion.py   # SelfReport + judge_completion completed/awaiting_review(A3)
            ├── decision.py     # LoopDecision 종료 decision 7종(A1)
            ├── parser.py       # provider JSON content의 top-level self_report parser
            ├── registry.py     # ToolRegistry allowlist/strict args/signature(A2)
            └── resolution.py   # resolve_retry + next_step_budget_decision(A3)
tests/
├── test_llm_gateway_payload.py
├── test_llm_provider.py
├── test_llm_provider_errors.py
├── test_llm_transport_mapping.py
├── test_llama_provider_client.py
├── test_httpx_transport.py
├── test_agent_loop_decision.py
├── test_agent_loop_budget.py
├── test_agent_loop_registry.py
├── test_agent_loop_completion.py
├── test_agent_loop_parser.py
└── test_agent_loop_resolution.py
scripts/
└── smoke_llm_provider.py
docs/verification_briefs/2026-06-24/
├── llm_gateway_slice_0_1_to_0_5.md
├── llm_gateway_f1_f2_live_smoke.md
└── llm_gateway_slice_0_6_httpx.md
docs/verifications/2026-06-24/
├── flat_loop_tool_registry.md
├── llm_gateway_slice_0_1_to_0_5.md
├── llm_gateway_slice_0_6_httpx.md
├── llm_gateway_f1_f2_closure.md
├── completion_criteria_contract.md
└── agent_loop_a1_decision_budget.md
```
