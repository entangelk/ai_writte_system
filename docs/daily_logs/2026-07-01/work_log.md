# Work Log — 2026-07-01

## Goals

- HANDOFF를 읽고 다음 작업을 진행한다.
- Phase 2A 실제 provider/Gateway wiring을 막고 있는 prompt, JSON output, source_ref 생성 경계를 결정 브리프로 정리한다.
- 다음 구현자가 추측 없이 사용자 승인 후 runner factory wiring slice로 들어갈 수 있게 HANDOFF를 갱신한다.

## Completed work

### Phase 2A provider/Gateway wiring 결정 브리프 추가

- 변경 파일: `docs/plans/02-analysis-provider-wiring-decisions.md`, `docs/plans/README.md`, `HANDOFF.md`, `docs/daily_logs/2026-07-01/work_log.md`.
- HANDOFF의 다음 구현 후보는 실제 provider/Gateway runner factory wiring이었지만, Gateway JSON output/prompt 계약과 source_ref 생성 boundary가 미확정이라 바로 구현하면 추측 구현이 된다.
- 새 브리프를 `Decision brief — awaiting user approval` 상태로 추가했다. SoT 계약 버전은 올리지 않았다. 이유: 아직 사용자가 승인한 public 계약이 아니라, 승인 요청을 위한 선택지/추천안이다.
- 추천안은 첫 provider wiring slice를 tool-call 없는 terminal JSON extraction으로 좁힌다. 모델은 새 source_ref를 만들지 않고 입력 source_ref catalog의 id를 선택하며, prompt 조립과 prompt version은 Application/Worker runner factory가 소유한다. Gateway 호출은 현재 구현된 `/v1/generate`를 사용하고, structured endpoint와 domain tool-call branch는 후속으로 둔다.
- `docs/plans/README.md` 읽는 순서에 새 브리프를 추가했다.
- `HANDOFF.md` Current Status와 Next Tasks를 갱신해 다음 액션을 "브리프 승인 후 provider/Gateway runner factory wiring 구현"으로 정리했다.

### Phase 2A provider/Gateway wiring 사용자 결정 반영

- 변경 파일: `docs/plans/02-analysis-provider-wiring-decisions.md`, `docs/system-contract-sot.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-01/work_log.md`.
- 사용자가 브리프의 1번/2번은 A로 승인했다. Phase 2A 첫 provider wiring은 tool-call 없이 terminal JSON extraction으로 진행하고, source_ref 후보는 글쓰기 프로그램 특성상 정적/기계적으로 anchor catalog를 만들 수 있다는 전제를 둔다. 모델은 새 source_ref를 만들지 않고 입력 catalog의 id를 선택한다.
- 3번은 C로 결정했다. Prompt template은 DB에 저장하고 versioned 관리한다. 이유: prompt 변경/버전 추적이 필요하고, agentic loop context와 ContextPackage도 앞으로 체계화해 관리할 가능성이 높기 때문이다.
- 4번은 기존 추천대로 `analysis_extract_v1`/`analysis_extract` 최소 literal을 채택했다.
- 5번은 사용자의 판단을 반영해 확정 구현 대신 비용 확인 단계로 바꿨다. `/v1/generate`와 structured generation은 분리되는 편이 좋아 보이지만, 지금 임시 통합 후 분리가 가능한지와 structured endpoint를 지금 여는 비용을 먼저 확인한 뒤 더 나은 쪽으로 진행한다.
- 6번은 추천 runner factory 최소 구성을 채택했다.
- SoT를 v1.6.15로 올려 승인된 결정과 남은 Gateway surface 선택 비용 확인 항목을 반영했다.

### Phase 2A provider/Gateway runner factory wiring 첫 구현 slice

- 변경 파일: `services/application/app/core_sot/repository.py`, `services/application/app/core_sot/service.py`, `services/application/app/core_sot/mongo_repository.py`, `services/application/app/analysis/prompt_templates.py`, `services/application/app/analysis/prompt_template_mongo_repository.py`, `services/application/app/analysis/prompt_builder.py`, `services/application/app/analysis/gateway_provider.py`, `services/application/app/analysis/extractor.py`, `services/application/app/main.py`, `services/application/requirements.txt`, 관련 테스트, `docs/system-contract-sot.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-01/work_log.md`.
- 작은 슬라이스로 나눠 진행했다.
- Slice A: Core SOT에 `list_source_refs(project_id, snapshot_id)`를 추가했다. project/snapshot 격리를 강제하고 source order로 catalog를 반환한다. Mongo adapter에는 `source_refs_by_project_snapshot` required index를 추가했다.
- Slice B: versioned prompt template 저장소를 추가했다. `PromptTemplateService`는 `analysis_extract_v1`을 seed/fetch하고 같은 `task_type + version`의 다른 template을 conflict로 거절한다. Mongo adapter는 `prompt_templates` collection과 `uniq_prompt_template_version` index를 사용한다.
- Slice C: `analysis_extract_v1` prompt builder를 추가했다. snapshot metadata/raw_text와 source_ref catalog를 Gateway `ChatCompletionRequest`로 조립하며, 빈 catalog나 cross-snapshot ref는 provider 호출 전에 거절한다.
- Slice D: 비용 확인 결과 `/v1/generate-structured`는 이번 slice에서 보류했다. 제대로 열려면 Gateway public schema failure envelope를 새로 정해야 하는데, 현재 Application adapter가 JSON/schema 검증을 이미 소유한다. 대신 `/v1/generate` 기반 Application→Gateway adapter(`GatewayGenerateProvider`)를 추가해 나중에 structured endpoint로 바꿔도 교체 지점이 분리되게 했다.
- Slice E: `VersionedPromptAnalysisExtractionAdapter`를 추가하고 `create_app()` 기본 runtime wiring을 열었다. `LLM_GATEWAY_BASE_URL`이 설정되면 prompt template seed, Gateway provider, source_ref catalog, snapshot loader를 조합해 default analysis runner를 구성한다. env가 없으면 기존처럼 pending `run`은 503이다.
- 새 prompt contract에 맞춰 `{"candidates":[]}`를 유효한 빈 extraction으로 처리하도록 parser/runner 회귀를 보강했다.

### Phase 2A provider/Gateway wiring 독립 검증 보강

- 변경 파일: `tests/test_application_api.py`, `docs/system-contract-sot.md`, `HANDOFF.md`, `docs/daily_logs/2026-07-01/work_log.md`.
- 독립 검증 기록 `docs/verifications/2026-07-01/phase2a_provider_wiring.md`는 첫 구현 slice를 조건부 합격으로 판정했다. 차단 조건은 Slice 6의 `LLM_GATEWAY_BASE_URL` env-set default runner branch가 committed regression에 추적되지 않는다는 점이었다.
- `test_analysis_run_endpoint_uses_env_configured_default_runner`를 추가했다. 테스트는 env-set 상태에서 `create_app()`에 runner를 주입하지 않고, `GatewayGenerateProvider` 생성자만 fake provider로 patch해 `_default_analysis_runner` 경로를 실제로 타게 한다. 준비된 snapshot/source_ref catalog와 provider JSON 결과가 `/analysis/jobs/{job_id}/run`을 통해 `succeeded` job과 저장된 candidate로 이어지는지 확인한다.
- SoT v1.6.16 근거 열에 `tests/test_analysis_runner.py`를 포함하도록 보정했다.

## Issues found

- 문제: HANDOFF의 다음 작업 대부분이 Gateway/model tool-call wire format, prompt/output 계약, source_ref 생성 boundary에 막혀 있었다.
- 원인: Phase 2A run endpoint API contract는 완료됐지만 실제 provider wiring은 모델이 source_ref를 어떻게 참조할지, tool-call 없이 가능한지, prompt 조립을 누가 소유할지 결정되지 않았다.
- Resolution: 구현 대신 좁은 결정 브리프를 추가했다. terminal JSON extraction과 source_ref catalog 선택 방식을 추천안으로 제시하되 승인 대기 상태로 남겼다.
- Outcome: 다음 작업자는 사용자 승인 없이는 runtime wiring을 구현하지 않고, 승인되면 최소 slice 순서에 따라 바로 진행할 수 있다.

- 문제: Gateway 호출 surface는 `/v1/generate` 임시 사용과 `/v1/generate-structured` 분리 사이에서 바로 확정하기 어렵다.
- 원인: structured endpoint는 장기적으로 좋아 보이지만 현재 구현 비용, schema failure envelope, 기존 provider client와의 중복 범위를 확인해야 한다.
- Resolution: provider wiring 구현 전에 짧은 비용 확인 spike를 Next Task에 넣고, 결과가 명확하면 더 나은 쪽으로 진행하도록 했다.
- Outcome: 장기 분리 가능성을 닫지 않으면서도 최소 기능 구현 흐름을 유지했다.

- 문제: 브리프의 prompt contract는 후보가 없을 때 `{"candidates":[]}`를 허용했지만 기존 parser는 빈 candidates 배열을 malformed로 거절했다.
- 원인: fake-provider extraction adapter의 이전 회귀가 "non-empty array"를 전제로 하고 있었다.
- Resolution: 빈 candidates 배열은 빈 draft tuple로 파싱하도록 바꾸고, runner가 빈 extraction을 `succeeded` job + candidate 0개로 닫는 회귀를 추가했다.
- Outcome: prompt contract와 implementation이 일치한다.

- 문제: 독립 검증에서 env-set default runner wiring branch가 테스트에 직접 추적되지 않아 조건부 합격 차단 조건으로 남았다.
- 원인: 기존 `/run` HTTP 테스트는 runner를 명시 주입했고, env-unset 503만 잠겨 있었다.
- Resolution: env-set 상태에서 `create_app()`의 default runner factory를 타고 pending job이 terminal 상태까지 실행되는 회귀를 추가했다.
- Outcome: live Gateway smoke와 별개로, Slice 6의 단위 branch lock이 committed test artifact로 닫혔다.

## Decisions

- 이번 턴에서는 provider/Gateway runtime wiring을 구현하지 않았다. 이유: SoT의 미확정 항목을 임의로 채우지 않는다는 프로젝트 규칙과 충돌하기 때문이다.
- `02-analysis-provider-wiring-decisions.md`는 승인 대기 브리프이므로 SoT 버전과 CHANGELOG는 갱신하지 않았다.
- 브리프의 추천 방향은 tool-call 없는 terminal JSON extraction이다. 이유: 현재 구현된 `ProviderTurnResult`와 `AnalysisExtractionAdapter`가 terminal content를 이미 처리하고, tool-call branch는 Gateway parsing/model wire/handler payload가 모두 미확정이기 때문이다.
- 사용자 결정으로 Phase 2A provider wiring 첫 slice는 tool-call 없는 terminal JSON extraction으로 승인됐다.
- source_ref 후보는 정적/기계적 anchor catalog로 준비하고, 모델은 입력 catalog의 `source_ref_id`를 선택한다.
- Prompt template은 DB에 저장하고 versioned 관리한다. 첫 prompt version은 `analysis_extract_v1`, task_type은 `analysis_extract`다.
- Gateway 호출 surface는 구현 전 비용 확인 뒤 `/v1/generate` 임시 사용 또는 `/v1/generate-structured` 최소 구현 중 선택한다.
- 비용 확인 결과 이번 slice에서는 `/v1/generate` 임시 사용을 채택했다. structured endpoint는 schema failure envelope까지 정해야 하므로 별도 Gateway slice로 미룬다.
- `LLM_GATEWAY_BASE_URL` env가 default analysis runner activation switch다. env가 없으면 existing 503 behavior를 유지한다.

## Verification

- 문서 링크 확인: `docs/plans/02-analysis-provider-wiring-decisions.md`가 참조하는 `system-contract-sot.md`, `02-analysis-pipeline.md`, `02-analysis-runner-execution-decisions.md`, `llm-gateway.md` 존재 확인.
- 계약 충돌 확인: SoT 미확정 목록의 `Gateway/model tool-call response wire format`은 계속 미확정으로 유지했고, 새 브리프는 tool-call 없는 첫 slice 추천안만 제시한다.
- 문서-only 변경이라 code test는 실행하지 않았다.
- 사용자 결정 반영 후 문서-only 검증: SoT v1.6.15 변경 이력, Phase 2A 계약 문단, 미확정 목록의 Gateway surface 비용 확인 항목, HANDOFF Next Tasks가 같은 방향을 가리키는지 확인했다.
- 구현 focused 검증: `python3 -m unittest tests.test_core_sot.CoreSotSourceRefTest tests.test_core_sot_mongo_indexes tests.test_prompt_templates tests.test_prompt_template_mongo_indexes tests.test_analysis_prompt_builder tests.test_analysis_gateway_provider tests.test_analysis_extractor_schema tests.test_analysis_runner tests.test_application_api -v` — 96개 통과.
- 전체 회귀: `python3 -m unittest discover tests -v` — 349개 통과(37 skip).
- Diff hygiene: `git diff --check` 통과.
- 독립 검증 보강 단일 회귀: `python3 -m unittest tests.test_application_api.ApplicationApiTest.test_analysis_run_endpoint_uses_env_configured_default_runner -v` — 1개 통과.

## Next steps

- 실제 gateway endpoint를 대상으로 Phase 2A provider wiring live smoke를 실행한다.
- malformed JSON/schema failure가 실제로 자주 발생하면 `/v1/generate-structured` 최소 contract를 별도 Gateway slice로 검토한다.
