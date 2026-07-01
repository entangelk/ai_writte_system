# Work Log — 2026-07-01

## Goals

- HANDOFF를 읽고 다음 작업을 진행한다.
- Phase 2A 실제 provider/Gateway wiring을 막고 있는 prompt, JSON output, source_ref 생성 경계를 결정 브리프로 정리한다.
- 다음 구현자가 추측 없이 사용자 승인 후 runner factory wiring slice로 들어갈 수 있게 HANDOFF를 갱신한다.
- Phase 2A source_ref catalog를 내부 smoke setup이 아니라 Application HTTP API로 준비할 수 있게 한다.

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

### Phase 2A provider wiring live smoke

- 변경 파일: `scripts/phase2a_provider_live_smoke.py`, `HANDOFF.md`, `docs/daily_logs/2026-07-01/work_log.md`.
- HANDOFF의 1순위 Next Task였던 실제 Gateway/model 운영 경계 smoke를 실행했다.
- Public HTTP에는 아직 `source_ref` 생성 endpoint가 없으므로, smoke script가 in-memory Core SOT에 project/draft/version과 `source_ref` catalog(`민아`, `파란 편지`, `준호`)를 준비한다. 그 뒤 Application `/analysis/jobs/{job_id}/run`을 ASGI로 호출하고, Application provider adapter는 Gateway app의 `/v1/generate`를 통과해 실제 llama.cpp-compatible endpoint `http://192.168.1.29:9080`을 호출한다.
- 첫 sandbox 내부 실행은 Python/httpx 외부 TCP가 `[Errno 1] Operation not permitted`로 막혀 `provider_error` 보존 경로로 떨어졌다. 이는 sandbox 제한에 의한 것이므로, 같은 명령을 승인된 외부 네트워크 실행으로 재실행했다.
- 승인 실행 결과: `run_http_status=400`, final job `status=failed`, `failure_reason=schema_invalid`, `failure_detail="provider content must be JSON"`, candidates 0. 실제 모델 출력은 strict JSON이 아니었지만, run endpoint가 schema failure를 terminal job으로 안정 보존함을 확인했다.
- 효과: live smoke 수용 기준인 "terminal job을 만들거나 provider/schema failure를 안정적으로 보존"이 충족됐다. 동시에 현 prompt/Gateway text generation 조합은 strict JSON을 보장하지 않는다는 운영 신호가 생겼고, 이는 `/v1/generate-structured` 후속 검토 근거로 남겼다.

### Phase 2A JSON repair retry

- 변경 파일: `services/application/app/analysis/extractor.py`, `tests/test_analysis_extractor_schema.py`, `scripts/phase2a_provider_live_smoke.py`, `docs/system-contract-sot.md`, `docs/plans/02-analysis-provider-wiring-decisions.md`, `CHANGELOG.md`, `HANDOFF.md`, `docs/daily_logs/2026-07-01/work_log.md`.
- 사용자 제안에 따라 parser 실패 원인을 먼저 확인했다. live smoke 원문은 markdown-fenced JSON이었고, 내부 JSON도 adapter가 요구하는 candidate schema보다 얕았다(`source_ref_id`/`quote`만 있고 `candidate_type`/`provenance`/`confidence`/`source_anchors`/`payload`가 없음).
- llama.cpp/Gemma endpoint의 JSON mode 가능성도 확인했다. `chat_template_kwargs.enable_thinking=false`를 명시하면 simple JSON 요청은 `message.content`로 정상 반환됐다. `response_format={"type":"json_object"}`도 거절되지는 않았지만, 동일 단순 요청에서는 response_format 없이도 JSON이 반환됐다. 직접 curl에서 thinking을 끄지 않으면 `message.content`가 비고 `reasoning_content`에만 JSON 예시가 들어가는 현상도 확인했다.
- 사용자 결정: `/v1/generate-structured` public contract를 바로 열기보다, 1번 방향(Application-side repair)을 먼저 진행한다.
- 구현: `VersionedPromptAnalysisExtractionAdapter`가 첫 provider content를 기존 strict parser로 검증하고, 실패 시 원문 output/parser error/original prompt payload를 포함한 repair prompt를 같은 provider에 1회만 재호출한다. repair output도 기존 `parse_analysis_extraction()`과 source validation/candidate schema를 그대로 통과해야 한다. repair도 실패하면 성공으로 보정하지 않고 기존 runner failure mapping에 따라 `schema_invalid`로 보존한다.
- smoke script는 provider 원문/repair 결과를 `provider_results`에 남기도록 보강했고, 기본 `--max-tokens`를 Application runtime 기본값과 같은 2048로 맞췄다.
- 승인 live smoke 재실행 결과: 첫 provider result는 fenced `{"candidates":[]}`였고, repair result는 valid Phase 2A JSON candidate 3개였다. `/analysis/jobs/{job_id}/run`은 `200`, final job `succeeded`, candidates 3개로 닫혔다.

### Phase 2A source_ref catalog HTTP API

- 변경 파일: `services/application/app/main.py`, `tests/test_application_api.py`, `scripts/phase2a_provider_live_smoke.py`, `docs/system-contract-sot.md`, `docs/plans/02-analysis-provider-wiring-decisions.md`, `CHANGELOG.md`, `HANDOFF.md`, `docs/daily_logs/2026-07-01/work_log.md`.
- `POST /projects/{project_id}/snapshots/{snapshot_id}/source-refs`를 추가했다. 요청은 `start_offset`, `end_offset`만 받고, Core SOT가 snapshot raw text에서 `quote`, `block_id`, `content_hash`를 계산한다.
- `GET /projects/{project_id}/snapshots/{snapshot_id}/source-refs`와 `GET /projects/{project_id}/source-refs/{source_ref_id}`를 추가했다. 두 조회 경로 모두 project/snapshot/ref 격리를 Core SOT 서비스에 위임한다.
- invalid span은 400, missing/cross-project snapshot/ref는 404로 매핑했다.
- archived project에서도 source_ref 생성·조회가 허용됨을 API 회귀로 잠갔다. 이는 immutable snapshot의 파생 주석이라는 기존 SoT carve-out과 일치한다.
- `scripts/phase2a_provider_live_smoke.py`가 더 이상 in-memory service로 source_ref를 직접 만들지 않고, 새 HTTP source-ref endpoint로 catalog를 준비하도록 바꿨다.
- 효과: Phase 2A live smoke 준비 경로가 public Application API에 가까워졌고, 다음 smoke는 snapshot save → source_ref HTTP materialization → analysis job run 흐름을 함께 검증한다.

### Phase 2A source_ref catalog anchor repair

- 변경 파일: `services/application/app/analysis/extractor.py`, `tests/test_analysis_extractor_schema.py`, `docs/system-contract-sot.md`, `CHANGELOG.md`, `HANDOFF.md`, `docs/daily_logs/2026-07-01/work_log.md`.
- source_ref HTTP 준비 경로를 탄 live smoke에서 repair output이 valid Phase 2A JSON이었지만, catalog id `source-ref-1`을 `source_ref-1`처럼 underscore 형태로 바꾸는 실패를 확인했다.
- `VersionedPromptAnalysisExtractionAdapter`가 parsed candidate의 `source_ref_id`, `start_offset`, `end_offset`, `quote`, `content_hash`를 입력 source_ref catalog와 대조하도록 보강했다. mismatch가 있으면 malformed JSON/schema repair와 같은 1회 repair prompt를 사용한다.
- repair 후에도 catalog mismatch가 남으면 성공으로 보정하지 않고 parsed draft를 그대로 반환해 기존 runner/source validation 경계가 `source_invalid`를 보존한다.
- 보강 뒤 live smoke 재실행 결과: 새 HTTP source_ref endpoint로 catalog를 준비했고, 첫 provider result는 fenced `{"candidates":[]}`, repair result는 `source-ref-*` id와 span/hash를 정확히 보존한 valid JSON이었다. `/analysis/jobs/{job_id}/run`은 `200`, final job `succeeded`, candidates 3개로 닫혔다.

### SourceRef catalog HTTP API verification follow-up

- 변경 파일: `tests/test_analysis_extractor_schema.py`, `docs/verifications/2026-07-01/source_ref_catalog_http_api.md`, `HANDOFF.md`, `docs/daily_logs/2026-07-01/work_log.md`.
- 독립 검증 `docs/verifications/2026-07-01/source_ref_catalog_http_api.md`가 조건부 합격을 기록했다. 차단 조건 I1은 catalog id는 유효하지만 span/quote/content_hash가 catalog와 다른 경우에도 repair가 1회 시도되는지 테스트가 없다는 점이었다.
- `test_versioned_prompt_adapter_repairs_catalog_anchor_drift_once`를 추가했다. provider 첫 응답은 `source_ref_id="source-ref-1"`을 유지하되 quote만 `"민호"`로 틀리게 만들고, adapter가 repair prompt를 1회 호출하며 `"source_anchors must preserve catalog span, quote, and content_hash"` 메시지를 포함하는지 단언한다.
- verification record에는 원 조건부 판정을 보존하고, 후속 폐쇄 섹션으로 I1이 닫혔음을 기록했다.

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

- 문제: sandbox 내부 Python/httpx는 live llama.cpp endpoint로 TCP 연결을 열 수 없었다.
- 원인: 현재 실행 환경의 network sandbox가 Python socket 연결을 차단했고, 직접 `httpx.get("http://192.168.1.29:9080/health")`도 `[Errno 1] Operation not permitted`로 실패했다. `curl` health/models 조회는 가능했지만, Application/Gateway provider path는 Python/httpx라 같은 제한을 받는다.
- Resolution: live smoke 명령을 승인된 외부 네트워크 실행으로 재실행했다.
- Outcome: 실제 endpoint까지 도달했고 schema-invalid failure preservation을 확인했다. 앞으로 이 smoke는 sandbox 밖 네트워크 권한이 필요하다.

- 문제: 실제 model output이 `AnalysisExtractionAdapter`가 요구하는 top-level JSON object가 아니었다.
- 원인: 현재 `/v1/generate` text generation surface와 `analysis_extract_v1` prompt는 strict JSON을 강제하지 않는다.
- Resolution: 이번 slice 범위에서는 정상적인 schema failure로 보존되는지를 확인했고, Gateway structured-output surface는 Next Task로 남겼다.
- Outcome: failure가 `schema_invalid` terminal job으로 보존되어 운영 경계는 통과했다. malformed JSON 비율을 낮추려면 `/v1/generate-structured` 또는 prompt/grammar 보강 slice가 필요하다.

- 문제: parser 실패가 단순히 markdown fence 때문인지, schema 불일치 때문인지 구분되지 않았다.
- 원인: 기존 live smoke summary는 provider raw content를 기록하지 않고 final job failure만 기록했다.
- Resolution: smoke script에 provider result recording을 추가하고 live run을 재실행했다.
- Outcome: 첫 실패는 fenced JSON이면서 동시에 schema가 얕은 출력임을 확인했다. repair retry 후에는 같은 endpoint가 valid Phase 2A schema를 만들 수 있음도 확인했다.

- 문제: direct curl에서는 Gemma가 JSON을 `message.content`가 아니라 `reasoning_content`에 쓰는 경우가 있었다.
- 원인: direct curl 요청에 `chat_template_kwargs.enable_thinking=false`를 넣지 않아 thinking path가 켜졌다. Gateway provider path는 이미 `thinking=False`를 통해 `enable_thinking=false`를 넣는다.
- Resolution: thinking off/on 조건을 나눠 direct curl을 비교했다.
- Outcome: `enable_thinking=false`에서는 simple JSON이 content로 반환된다. 현재 Gateway path의 thinking 설정은 맞고, structured endpoint 도입 여부와 별개로 repair retry가 실제 Phase 2A 출력 실패를 줄인다.

- 패턴 스윕: 같은 `parse_analysis_extraction(result.content)` 경로가 legacy `AnalysisExtractionAdapter`에도 남아 있음을 확인했다(`services/application/app/analysis/extractor.py`). `git blame` 결과 2026-06-29 fake-provider extraction adapter slice에서 추가된 초기 adapter이며, 현재 runtime provider wiring은 `VersionedPromptAnalysisExtractionAdapter`를 사용한다. legacy adapter는 source_ref catalog/original prompt payload가 없어 같은 repair prompt를 정확히 구성하기 어렵고 live path가 아니므로 이번 수정 범위에서는 건드리지 않았다.

- 문제: Phase 2A live smoke가 public HTTP가 아니라 in-memory Core SOT service로 source_ref catalog를 준비했다.
- 원인: SourceRef persistence와 domain service는 있었지만 Application API에 source_ref 생성/list/get surface가 없었다.
- Resolution: source_ref catalog HTTP API를 추가하고 live smoke script가 그 endpoint를 사용하게 바꿨다.
- Outcome: HTTP-only에 가까운 Phase 2A 준비 경로가 열렸다. 단, 전체 배포 환경에서 Application process와 Gateway process를 실제 네트워크로 띄우는 smoke는 아직 별도 운영 검증이다.

- 문제: source_ref HTTP API로 만든 catalog id는 `source-ref-*`인데 model repair output이 `source_ref-*`로 바꿔 source validation이 실패했다.
- 원인: prompt가 "source_ref_id" 필드명을 쓰다 보니 모델이 catalog id literal의 hyphen까지 보존하지 못하고 field naming convention처럼 underscore로 변형했다.
- Resolution: Versioned adapter가 parser 통과 뒤에도 입력 catalog와 anchor literal을 대조하고, mismatch를 1회 repair 대상으로 삼도록 했다.
- Outcome: live smoke가 `run_http_status=200`, final job `succeeded`, candidates 3개로 통과했다. repair 후에도 mismatch가 남으면 기존 source validation 실패가 보존된다.

- 문제: 독립 검증이 `_catalog_anchor_error`의 span/quote/content_hash mismatch branch가 회귀에 추적되지 않는다고 지적했다.
- 원인: 기존 보강 테스트는 catalog id drift(`source_ref-1`)만 다뤘고, id는 유효하지만 quote/span/hash만 다른 branch를 직접 밟지 않았다.
- Resolution: id는 유효하고 quote만 다른 anchor를 사용해 두 번째 catalog mismatch 메시지를 repair prompt에 포함하는지 단언하는 회귀를 추가했다.
- Outcome: I1 빈 cell이 닫혔다.

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
- Live smoke는 public source_ref 생성 API가 아직 없으므로 repo script가 in-memory setup으로 catalog를 준비하는 방식으로 진행했다. Application→Gateway→model 운영 경계 검증에는 충분하지만, full deployed HTTP-only E2E는 source_ref materialization/API가 생긴 뒤 별도 확인한다.
- 사용자 결정: parser 실패 원인 확인 후에도 `/v1/generate-structured`를 바로 열지 않고 Application-side repair retry를 먼저 적용한다. 이유는 현재 JSON/schema 검증 소유자가 Application adapter이고, 새 Gateway public contract 없이 실제 실패(fence/schema mismatch)를 줄일 수 있기 때문이다.
- SourceRef catalog HTTP path는 `/projects/{project_id}/snapshots/{snapshot_id}/source-refs`와 `/projects/{project_id}/source-refs/{source_ref_id}`로 정했다. 이유: source_ref 생성/list는 snapshot catalog 준비 행위이고, 단건 ref read는 snapshot id 없이 ref identity로 읽는 사용처가 생길 수 있기 때문이다. 두 경로 모두 project_id 격리를 유지한다.
- SourceRef create는 기존 Core SOT primitive처럼 non-idempotent로 유지한다. idempotency는 Phase 2A candidate/job 저장층이 소유한다.
- Catalog anchor mismatch repair는 normalization이 아니라 retry다. `source_ref-1`을 코드가 `source-ref-1`로 자동 보정하지 않고, 모델에게 catalog literal을 다시 출력하게 한다. 이유: id literal 자동 보정은 잘못된 ref를 조용히 연결할 위험이 있고, 실패 시에는 기존 `source_invalid`가 더 안전한 결과다.

## Verification

- 문서 링크 확인: `docs/plans/02-analysis-provider-wiring-decisions.md`가 참조하는 `system-contract-sot.md`, `02-analysis-pipeline.md`, `02-analysis-runner-execution-decisions.md`, `llm-gateway.md` 존재 확인.
- 계약 충돌 확인: SoT 미확정 목록의 `Gateway/model tool-call response wire format`은 계속 미확정으로 유지했고, 새 브리프는 tool-call 없는 첫 slice 추천안만 제시한다.
- 문서-only 변경이라 code test는 실행하지 않았다.
- 사용자 결정 반영 후 문서-only 검증: SoT v1.6.15 변경 이력, Phase 2A 계약 문단, 미확정 목록의 Gateway surface 비용 확인 항목, HANDOFF Next Tasks가 같은 방향을 가리키는지 확인했다.
- 구현 focused 검증: `python3 -m unittest tests.test_core_sot.CoreSotSourceRefTest tests.test_core_sot_mongo_indexes tests.test_prompt_templates tests.test_prompt_template_mongo_indexes tests.test_analysis_prompt_builder tests.test_analysis_gateway_provider tests.test_analysis_extractor_schema tests.test_analysis_runner tests.test_application_api -v` — 96개 통과.
- 전체 회귀: `python3 -m unittest discover tests -v` — 349개 통과(37 skip).
- Diff hygiene: `git diff --check` 통과.
- 독립 검증 보강 단일 회귀: `python3 -m unittest tests.test_application_api.ApplicationApiTest.test_analysis_run_endpoint_uses_env_configured_default_runner -v` — 1개 통과.
- Live smoke script syntax: `python3 -m py_compile scripts/phase2a_provider_live_smoke.py` — 통과.
- Sandbox 제한 확인: `python3 scripts/phase2a_provider_live_smoke.py` — sandbox 내부에서는 Python/httpx 외부 TCP 차단으로 `run_http_status=502`, final job `failed/provider_error`, `failure_detail="provider is unavailable"` 보존.
- Live smoke 승인 실행: `python3 scripts/phase2a_provider_live_smoke.py` — 외부 네트워크 권한으로 endpoint `http://192.168.1.29:9080`, model `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0` 호출. 결과 `run_http_status=400`, final job `failed/schema_invalid`, `failure_detail="provider content must be JSON"`, candidates 0.
- JSON mode/provenance check: direct curl에서 `chat_template_kwargs.enable_thinking=false` + simple JSON instruction은 `message.content`에 valid JSON을 반환했다. thinking off 없이 같은 요청을 보내면 `message.content`가 비고 `reasoning_content`에 JSON 예시가 들어갔다. `response_format={"type":"json_object"}`는 endpoint에서 거절되지 않았지만, simple case에서는 response_format 없이도 valid JSON이 반환됐다.
- Repair focused regression: `python3 -m unittest tests.test_analysis_extractor_schema -v` — 12개 통과.
- Repair compile check: `python3 -m py_compile services/application/app/analysis/extractor.py tests/test_analysis_extractor_schema.py scripts/phase2a_provider_live_smoke.py` — 통과.
- Repair live smoke: `python3 scripts/phase2a_provider_live_smoke.py` — 첫 provider result fenced `{"candidates":[]}`, repair provider result valid Phase 2A JSON, `run_http_status=200`, final job `succeeded`, candidates 3개.
- Pattern sweep: `rg -n "parse_analysis_extraction\\(|provider content must be JSON|repair|generate\\(request\\)" services/application/app/analysis tests` 및 `git blame -L 70,82 -- services/application/app/analysis/extractor.py`.
- Focused broader regression: `python3 -m unittest tests.test_analysis_extractor_schema tests.test_analysis_runner tests.test_application_api -v` — 75개 통과.
- Full regression: `python3 -m unittest discover tests -v` — 351개 통과(37 skip).
- SourceRef API compile check: `python3 -m py_compile services/application/app/main.py tests/test_application_api.py scripts/phase2a_provider_live_smoke.py` — 통과.
- SourceRef API focused regression: `python3 -m unittest tests.test_application_api -v` — 47개 통과.
- SourceRef HTTP live smoke first run: `python3 scripts/phase2a_provider_live_smoke.py` — HTTP source_ref catalog 준비는 성공했지만 repair output이 `source_ref-*` id를 반환해 `run_http_status=400`, final job `failed/source_invalid`, `failure_detail="source_ref not found"`로 닫힘.
- Catalog anchor repair focused regression: `python3 -m py_compile services/application/app/analysis/extractor.py tests/test_analysis_extractor_schema.py` — 통과. `python3 -m unittest tests.test_analysis_extractor_schema -v` — 13개 통과.
- Catalog anchor repair live smoke: `python3 scripts/phase2a_provider_live_smoke.py` — HTTP source_ref catalog 준비, provider_results 2개(첫 fenced empty JSON, repair valid catalog anchors), `run_http_status=200`, final job `succeeded`, candidates 3개.
- Final focused regression: `python3 -m unittest tests.test_analysis_extractor_schema tests.test_analysis_runner tests.test_application_api -v` — 79개 통과.
- Final full regression: `python3 -m unittest discover tests -v` — 355개 통과(37 skip).
- Final diff hygiene: `git diff --check` — 통과.
- Verification follow-up compile check: `python3 -m py_compile tests/test_analysis_extractor_schema.py` — 통과.
- Verification follow-up focused extractor regression: `python3 -m unittest tests.test_analysis_extractor_schema -v` — 14개 통과.
- Verification follow-up focused 3-module regression: `python3 -m unittest tests.test_analysis_extractor_schema tests.test_analysis_runner tests.test_application_api -v` — 80개 통과.
- Verification follow-up full regression: `python3 -m unittest discover tests -v` — 356개 통과(37 skip).
- Verification follow-up diff hygiene: `git diff --check` — 통과.

## Next steps

- repair 후에도 malformed JSON/schema failure 또는 latency가 운영상 문제로 남으면 `/v1/generate-structured` 최소 contract를 별도 Gateway slice로 검토한다.
- Phase 3 indexing 계약이 확정되면 archive 후 파생 인덱스 stale 이벤트를 별도 회귀로 다룬다.
