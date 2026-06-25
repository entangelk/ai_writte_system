# CHANGELOG

| Date | Change | Detail |
|---|---|---|
| 2026-06-25 | AgentLoopRunner A3 검증 후 보강(I1/I3) | [work log](docs/daily_logs/2026-06-25/work_log.md) |
| 2026-06-25 | AgentLoopRunner A3 decision 합성 회귀 구현 | [work log](docs/daily_logs/2026-06-25/work_log.md) |
| 2026-06-25 | AgentLoopRunner A2 registry 계약 회귀 구현 | [work log](docs/daily_logs/2026-06-25/work_log.md) |
| 2026-06-24 | 개발 계획 문서 구조 도입 | [work log](docs/daily_logs/2026-06-24/work_log.md) |

## 2026-06-25

### Added

- AgentLoopRunner A3 독립 검증(합격) 후 비차단 2건을 보강했다. I3로 `InvalidBudgetPolicy`에 `decision = blocked`를 추가해 budget/registry 예외→종료 decision uniform 매핑을 완성했고, I1(유일한 spec↔impl 갭)로 `BudgetPolicy`에 `provider_retry_cap`/`tool_retry_cap`(0 이상)을 추가해 계약 §retry "retry cap은 필수 policy 값"을 구현에 실현했다. I2(runner 합성 순서)는 spec이 A3를 순수 원시로 규정해 runner slice forward-lock으로 뒀다. 전체 회귀 117→121, retry cap 검증 변이 증명(`_RETRY_DIMENSIONS=()` FAIL/복원 PASS).
- AgentLoopRunner A3를 구현했다. `judge_completion`(종료채널 self-report `FINALIZE`/`DEFER` + 구조 조건 하이브리드 판정 → `completed`/`awaiting_review`), `resolve_retry`(retry 우선순위: non-retryable 즉시 종료 → cap 소진 → cap 남음+budget 허용 retry → cap 남음+budget 차단 `budget_exhausted`에 원래 error literal trace 보존), `next_step_budget_decision`(budget 5차원 → `budget_exhausted` 매핑)을 fake/인프라 없이 양방향 회귀로 잠갔다. terminal-decision 우선순위(error > blocked/invalid_tool_arguments > budget_exhausted > completion)는 순차 합성으로 뒀다.
- A3의 F1 방어로 `BudgetTracker.record_tokens`가 음수/None/bool/비-int token count를 0으로 보정하지 않고 `InvalidProviderUsage`(decision=`provider_error`)로 거부하도록 했다(명시적 0은 유효).
- AgentLoopRunner A2를 구현했다. `ToolRegistry`가 task profile별 v1 domain tool allowlist, strict JSON argument validation(`required`·type·`additionalProperties`·array `items`만; `enum`/bounds는 후속), context-only argument 차단, canonical tool-call signature를 fake/인프라 없이 양방향 회귀로 잠근다.
- A2 독립 검증의 비차단 권고를 반영해 중첩 object schema와 array `items`를 등록 시점에 재귀 검증하고, runtime schema guard의 `assert` 의존을 명시 검사로 교체했다.
- 서비스 경계와 확정 계약을 한 곳에서 추적하기 위한 `docs/system-contract-sot.md` 초안을 추가하고, `docs/README.md`와 `docs/plans/README.md`의 진입점을 갱신했다.
- SoT 독립 검증 R1을 보강해 `docs/plans/README.md`의 문서-precedence tree를 SoT(`docs/system-contract-sot.md` §문서 우선순위)의 5-level과 통일하고, SoT를 정본 precedence로 defer 했다. 정본 precedence tree를 SoT 한 곳으로 단일화.

사용자는 HANDOFF의 다음 작업을 이어 진행하도록 요청했다. 이에 A2 범위를 실제 domain handler 구현이 아니라 registry/argument/signature 계약 회귀로 좁혀 완료하고, handler 실행·retry·completion 합성은 A3 이후로 남겼다.

독립 검증(2026-06-25)이 `flat-loop-gate.md` §33 "enum, bounds 적용" 명시와 구현이 일치하지 않음을 실증 발견했다. 사용자 결정으로 v1/A2 validator 범위를 `{required, type, additionalProperties, array items}`로 계약에 명시 좁히고 `enum`/bounds는 keyword 사용 tool 등록 시점까지 deferred로 reconcile 했다(§33·본 로그·검증 기록에 반영). 상세 기록은 `docs/verifications/2026-06-25/agent_loop_a2_registry.md`.

사용자는 여러 계획 문서가 나뉘어 있어 계약 및 서비스에 대한 정본 문서를 SoT로 활용하고 싶다고 결정했다. 이에 새 SoT 문서는 세부 Phase 계획을 대체하지 않고, 문서 우선순위·서비스 책임·확정 계약·미확정 결정을 먼저 확인하는 정본 인덱스 역할로 작성했다.

사용자는 A3 범위를 fake provider/tool을 주입받아 루프를 실구동하는 러너 골격이 아니라 A1·A2와 동일한 인프라 없는 순수 decision 합성 원시로 진행하기로 결정했다(결과: `completion.py`·`resolution.py`·budget F1 방어). self-report의 구체 wire 형식은 provider-response parser slice로, retry cap policy 배치(`BudgetPolicy` cap 추가 여부)는 별도 slice로 남겼다.

사용자는 A3 독립 검증이 "retry cap 정책 근원 부재"를 유일한 spec↔impl 갭(I1)으로 지적한 뒤, retry cap 배치를 별도 `RetryPolicy`/`TaskProfile`이 아니라 `BudgetPolicy` 확장(Option A)으로 결정했다. 이유: `allows_tools`도 budget이 아닌데 이미 `BudgetPolicy`에 있어 "run policy" 역할과 일관되고 runner가 policy 객체 1개만 전달하면 된다. tradeoff: `BudgetPolicy`가 소비 budget과 retry 한도를 함께 가져 이름이 약간 불일치하지만, 단일 run-policy 객체의 단순함이 우선했다. `resolve_retry(retries_remaining)` 시그니처는 그대로이고 runner가 `policy.<cap> - used`로 남은 retry를 계산한다.

## 2026-06-24

### Added

- 초기 아이디에이션과 실제 개발 계획의 문서 지위를 분리했다.
- `abstract.md`를 공통 기반과 Phase 1~6 계획으로 재구성했다.
- 구현 Phase와 MVP 가치 묶음이 별도 축이라는 계획 기준을 명시했다.
- 단일 사용자 Product Shell과 프로젝트/원고 CRUD·내보내기 계획을 추가했다.
- 분석 memory taxonomy와 Agentic Search/RAG 기반 변경 후보 흐름을 추가했다.
- monorepo 기반 구현 순서와 독립 LLM Gateway/Gemma Q4 검증 계획을 추가했다.
- 기존 `gemma4_12b`의 선택 이관 계획과 flat Agentic Loop Gate 보강 기준을 추가했다.
- 외부 참조 repo 없이 동작하는 portable LLM payload, provider/fake, stable errors와 fake-transport llama.cpp client를 구현했다.
- 독립 검증 조건 F1/F2를 계약·회귀로 보강하고 direct live Gemma Q4 smoke를 확인했다.
- httpx 기반 실제 JSON transport와 재현 가능한 provider smoke command를 추가했다. Mock contract 6개 회귀와 독립 검증 환경의 actual adapter live smoke까지 통과했다.
- flat loop의 task별 tool allowlist, strict argument validation, read-only v1 domain tool 6종과 Gate 비우회 원칙을 확정했다.
- 누적 token budget 우회를 막기 위해 Gateway usage를 필수화하고, flat loop budget 5차원의 계측·초과·retry 우선순위를 확정했다.
- flat loop task별 completion criteria를 확정했다. `completed`/`awaiting_review`를 하이브리드(구조 조건 AND self-report)로 판정하고, "완결된 산출 vs loop 미해결" 구분으로 Analysis/Context/Writing의 종료 기준을 잠갔다.
- AgentLoopRunner 구현을 시작했다(A1). `services/application/` 패키지에 `LoopDecision` 종료 decision 7종과 `BudgetPolicy`/`BudgetTracker` 5차원 budget을 fake/인프라 없이 양방향 회귀로 잠갔다.

사용자는 기존 문서를 초기 아이디에이션으로 보존하면서 실제 개발 전 검토가 쉽도록 긴 초안을 세분화하기를 선택했다. 이에 원문은 유지하고 `docs/plans/`를 작업용 계획 진입점으로 추가했다.

또한 혼자 사용하는 제품이므로 계정 시스템은 MVP에서 제외하고, 프로젝트 관리와 원고 내보내기를 사용자 제품 표면에 포함하기로 했다. 분석 대상은 고정 5종으로 확정하지 않고 분위기·목표·줄거리 등을 논의한 뒤, 기존 기억과의 대조 및 versioned update까지 고려한다.

LLM 운영은 같은 monorepo에서 계약을 함께 관리하되 Gateway를 독립 프로세스/컨테이너로 분리하는 제안안을 채택 후보로 기록했다. 참조 repo에서 Gemma 12B QAT GGUF Q4_0과 llama.cpp CUDA 구성을 확인했으며, 실제 하드웨어 benchmark 전에는 성능 기준을 확정하지 않는다.

사용자는 기존 `gemma4_12b`의 loop/agentic 구현 재사용과 sub-agent spawn 제외를 요청했다. 검토 결과 inference 구성과 평면형 loop 골격은 선택 이관하되, domain tool 실행은 Application/Worker가 소유하고 반복·인자·시간·token budget Gate를 보강하도록 정리했다.

사용자는 tool registry를 Application/Worker가 소유하고 task별 서버 allowlist로 제한하는 방향을 승인했다. 모델 arguments는 strict JSON Schema로 검증하고 `project_id`는 신뢰된 실행 문맥에서 주입하며, compare/validate tool은 preflight로만 사용해 독립 domain Gate를 우회하지 않도록 했다.

사용자는 budget 안전성을 위해 이전의 optional usage 계약을 의도적으로 역전했다. `usage`와 두 token count는 필수이며 누락은 `provider_invalid_response`로 처리하되, 명시적 0 token은 정상값으로 계속 허용한다. 이 결정은 token usage를 `unknown`으로 전파하는 대안보다 단일 Gateway 경계에서 누락을 차단하는 단순성을 택한 것이다.

사용자는 task별 completion criteria를 하이브리드 판정으로 확정했다. `completed`는 구조 조건(목표 산출물 존재)과 자율 조건(모델이 미해결 분기를 self-report하지 않음)을 모두 충족해야 한다. `analysis_compare`의 부분 모호는 loop decision과 candidate status의 직교성을 활용해 run `completed`로 두고 개별 모호 후보는 candidate status로 표현하며, tool 없는 `writing_generate`는 모델이 산출물 자체의 모호·충돌을 self-report할 때만 `awaiting_review`로 종료한다. 이 방향은 개별 항목의 불확실성을 loop 미완료로 승격하지 않고 완결된 산출로 표현하는 직교 모델을 택한 것이다.

여러 개발 머신에서 참조 repo가 없을 수 있으므로 외부 경로는 runtime dependency로 사용하지 않는다. 첫 구현 slice로 llama.cpp thinking payload 경계를 현재 repo에 자립적으로 이관했으며, 작업용 머신의 real-model smoke는 보류한다.
