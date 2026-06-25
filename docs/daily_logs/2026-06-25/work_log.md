# Work Log — 2026-06-25

## Goals

- HANDOFF 기준 다음 작업인 AgentLoopRunner A2를 진행한다.
- tool registry, strict argument validation, signature normalization을 실제 인프라 없이 결정적 회귀로 잠근다.
- A2 완료 후 다음 작업자가 A3(completion/retry/loop 합성)를 바로 이어갈 수 있게 상태 문서를 갱신한다.
- 흩어진 계획 문서의 서비스 경계와 확정 계약을 정리하는 SoT 초안을 만든다.

## Completed work

### AgentLoopRunner A2 구현(tool registry + strict arguments + signature)

- 변경 파일: `services/application/app/agent_loop/registry.py`, `tests/test_agent_loop_registry.py`, `docs/plans/implementation-plan.md`, `CHANGELOG.md`, `HANDOFF.md`, 이 작업 로그.
- `flat-loop-gate.md`의 tool registry 계약을 Application 소유 `agent_loop` 패키지에 추가했다.
- `TaskProfile` 3종(`analysis_compare`, `context_search`, `writing_generate`)과 v1 domain tool 6종을 literal로 고정했다.
- profile별 allowlist를 계약 그대로 고정했다: `analysis_compare` 5종, `context_search` 3종, `writing_generate` 0종.
- run 시작 시 등록 tool이 profile allowlist 밖에 있거나 profile 필수 tool이 빠지면 `ToolBlocked(decision=blocked)`로 차단한다.
- `ToolEntry` 등록 조건에서 schema-less tool, unknown field 허용 schema, 모델 argument의 context 전용 필드(`project_id`, task/trace/deadline 계열)를 거부한다.
- `validate_call`은 raw arguments를 JSON으로 한 번 parse하고 object가 아니면 거부한다. malformed JSON, unknown field, required 누락, type coercion 시도는 `InvalidToolArguments(decision=invalid_tool_arguments)`로 분류한다.
- valid call만 `tool name + canonical JSON arguments` signature를 만든다. canonical JSON은 key sort와 compact separator를 사용하며, 다른 argument 값/type/tool은 같은 signature로 접히지 않는다.
- 실제 Mongo/검색 handler 실행, runtime `tool_error`, budget→decision 매핑, retry, completion 판정은 A3 및 Slice 1·3 이후 범위로 남겼다.

### 시스템 정본 계약 SoT 초안 작성

- 변경 파일: `docs/system-contract-sot.md`, `docs/README.md`, `docs/plans/README.md`, `CHANGELOG.md`, `HANDOFF.md`, 이 작업 로그.
- 기존 계획 문서가 Phase별로 흩어져 있어 구현자가 어떤 계약을 먼저 봐야 하는지 모호했다. 새 문서를 "정본 계약 인덱스"로 추가해 문서 우선순위, 서비스 책임, 확정된 전역 계약, Gateway/AgentLoopRunner 계약, Gate 합성, Phase별 계약 인덱스, 미확정 결정 목록을 한 곳에 모았다.
- `docs/contracts.md`는 여전히 아이디에이션/reference로 두고, 새 구현 진입점은 `docs/system-contract-sot.md`로 분리했다.
- `docs/README.md`와 `docs/plans/README.md`에 SoT 문서를 먼저 보도록 링크와 우선순위 문구를 추가했다.
- 초안 상태이므로 세부 Phase schema를 추측하지 않았다. 확정된 구현·검증 계약과 미확정 항목을 분리했고, `enum`/bounds validator deferral 같은 triggered 조건도 유지했다.

## Issues found

### A2 시작 시 registry 모듈 부재

- 문제: 새 A2 테스트가 `services.application.app.agent_loop.registry`를 import할 수 없었다.
- 원인: A1은 decision/budget만 구현했고 registry는 후속 sub-slice로 명시되어 있었다.
- 해결: `registry.py`를 추가하고 focused 18개 회귀를 통과시켰다.
- 결과: 전체 `python3 -m unittest discover -s tests`가 83개 통과했다.

### 유사 패턴 sweep

- 문제: invalid args `{}` 보정, signature 오접힘, context scope 모델 주입과 같은 근본 패턴이 다른 구현에 남아 있을 수 있었다.
- 확인: `json.loads`, `additionalProperties`, `project_id`, `invalid_tool_arguments`, `signature` 패턴을 `services`, `tests`, `flat-loop-gate.md`에서 검색했다.
- 결과: 위험한 중복 구현은 발견되지 않았다. 관련 코드는 새 A2 모듈/테스트와 기존 A1의 normalized signature 소비 지점뿐이었다.

### A2 독립 검증 후 비차단 권고 보강

- 문제: 독립 검증 I2가 중첩 object schema의 등록-검증 비대칭을 지적했다. 기존 구현은 runtime에서는 fail-closed였지만 등록 시점에는 중첩 object strictness를 잡지 못했다.
- 추가 확인: reconcile 후 A2 범위로 남긴 `array items`도 `items` 누락 시 등록을 통과할 수 있었다.
- 해결: `_validate_schema_contract`를 재귀화해 중첩 object의 `additionalProperties: false`, context-only field, required/properties 일치, array `items` schema를 등록 시점에 검증한다.
- 해결: 독립 검증 I3의 `assert` 의존을 제거하고 `_validate_arguments`에서 schema 구조를 명시 검사로 바꿨다.
- 회귀: `test_nested_object_schema_must_be_strict_at_registration`, `test_array_schema_requires_items_at_registration` 2개를 추가했다. focused registry 회귀는 18→20, 전체 회귀는 83→85가 됐다.
- 결과: `python3 -m unittest tests.test_agent_loop_registry -v` 20/20 통과, `python3 -m unittest discover -s tests` 85/85 통과.
- 확인: enum/bounds는 여전히 validator 범위에서 제외되어 수용된다. 이는 사용자 결정으로 갱신한 `flat-loop-gate.md` §33의 explicit deferral과 일치한다.

## Decisions

- 상세 domain tool payload 필드는 아직 Phase schema가 확정되지 않았으므로 추측하지 않았다. A2는 schema 구조와 strict 검증 메커니즘을 잠그고, 실제 handler payload schema는 해당 Phase 구현에서 구체화한다.
- 외부 `jsonschema` dependency를 추가하지 않았다. 현재 테스트 표면에 필요한 strict object/type/required/array 검증만 표준 `json` 기반 최소 구현으로 제공한다. 더 넓은 JSON Schema keyword가 필요해지면 그때 dependency 도입을 판단한다.
- **[독립 검증 후 사용자 결정, 2026-06-25]** 독립 검증(`docs/verifications/2026-06-25/agent_loop_a2_registry.md`)이 `flat-loop-gate.md` §33 "enum, bounds 적용" 명시와 구현의 enum/bounds 미검증 불일치를 실증 발견했다. 사용자 결정으로 v1/A2 validator 범위를 `{required, type, additionalProperties, array items}`로 계약에 **명시 좁힘**하고 `enum`/bounds는 keyword를 사용하는 tool schema가 등록되는 시점까지 deferred로 reconcile했다(§33·implementation-plan §138·CHANGELOG에 반영). 이유: 현재 v1 tool schema에 enum/bounds가 없어 활성 결함이 아니며, 의존성·구현 추가보다 계약 개정이 가볍다. tradeoff: enum/bounds를 쓰는 tool이 처음 등록되는 시점에 검증 + 양방향 회귀를 반드시 추가해야 한다(해당 시점까지 empty cell 아님, 명시적 deferral).
- 독립 검증의 비차단 I2/I3는 바로 보강했다. 중첩 object와 array `items`는 현재 A2 validator 범위에 속하므로 등록 시점 fail-fast가 단순하고, `assert` 제거는 동작 변화 없이 최적화 모드에서도 의도가 드러나는 쪽을 택했다.

## Next steps

1. `docs/system-contract-sot.md`를 사용자가 검토하고 `Draft` 유지/수정/Approved 승격 방향을 결정한다.
2. AgentLoopRunner A3: completion 판정, retry 우선순위, loop 합성, budget→`budget_exhausted` decision 매핑 구현.
3. A3에서 Gateway→budget usage 연결 시 음수/None/invalid usage 방어를 회귀로 lock한다.
4. Gemma Q4 benchmark 후 budget/retry production 숫자 기본 한도를 확정한다.
