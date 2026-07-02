# Work Log — 2026-07-02

## Goals

- HANDOFF를 읽고 다음 작업을 진행한다.
- Phase 2A 전체 배포형 E2E를 Application/Gateway 실제 프로세스 네트워크 경로로 확인한다.
- 배포형 E2E smoke를 재현 가능한 스크립트와 회귀로 남긴다.

## Completed work

### Phase 3 indexing kickoff 결정 브리프 추가

- 변경 파일: `docs/plans/03-indexing-kickoff-decisions.md`, `docs/plans/README.md`, `HANDOFF.md`, `docs/daily_logs/2026-07-02/work_log.md`.
- HANDOFF의 남은 개발 후보 중 `/v1/generate-structured`는 조건부 후속이고, tool-call/artifact schema는 상류 계약이 없어 막혀 있었다.
- Phase 3 indexing이 다음 의존성 경로(Phase 4/2B)를 여는 축이지만, `03-indexing.md`와 SoT에는 embedding model, ES analyzer, sync delivery, archive/delete 반영 방식이 미확정으로 남아 있었다.
- 새 브리프는 Phase 3A 첫 구현을 source block only, Chroma-like vector contract with deterministic fake adapter, fake embedding only, explicit rebuild/index command, status/version filter 방식으로 추천한다.
- SoT 버전은 올리지 않았다. 이유: 사용자 승인 전 public contract가 아니라, 승인 요청용 결정 브리프다.

### Phase 3A source block indexing 첫 slice 구현

- 변경 파일: `services/application/app/indexing/__init__.py`, `services/application/app/indexing/models.py`, `services/application/app/indexing/service.py`, `tests/test_indexing_phase3a.py`, `docs/system-contract-sot.md`, `docs/plans/03-indexing-kickoff-decisions.md`, `docs/plans/03-indexing.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-02/work_log.md`.
- 사용자 요청에 따라 Phase 3 kickoff 추천안을 첫 코드 slice 범위로 승인한 것으로 보고, 가장 작은 구현부터 진행했다.
- `IndexRecordKind.SOURCE_BLOCK`, `IndexPointer(project_id, collection, document_id, version_id, content_hash)`, `SourceBlockIndexRecord`, `IndexSyncResult`를 추가했다.
- `DeterministicFakeEmbeddingProvider`와 `InMemoryVectorIndexAdapter`를 추가했다. 실제 ChromaDB/embedding model은 후속 결정으로 남겼다.
- `SourceBlockIndexingService.rebuild_snapshot_source_block_index(project_id, snapshot_id)`를 추가했다. Core SOT snapshot blocks를 source block index records로 materialize하고 vector index adapter에 upsert한다.
- Archive/delete 반영은 hard delete가 아니라 `project_archived`/`draft_archived` flag와 query filter로 시작했다.
- SoT를 v1.6.20으로 올려 첫 slice 범위를 명시했다.

### Phase 3A source block indexing 검증 후 보강

- 변경 파일: `services/application/app/indexing/models.py`, `services/application/app/indexing/service.py`, `tests/test_indexing_phase3a.py`, `docs/system-contract-sot.md`, `docs/plans/03-indexing-kickoff-decisions.md`, `docs/plans/03-indexing.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-02/work_log.md`.
- 독립 검증 `docs/verifications/2026-07-02/phase3a_source_block_index.md`가 조건부 합격으로 지적한 F1/F2를 보강했다.
- F1 대응으로 `IndexSyncTarget.VECTOR`, `IndexSyncRequest(project_id, snapshot_id, target)`를 추가하고 `IndexSyncResult`가 request를 싣도록 바꿨다.
- SoT를 v1.6.21로 올려 Phase 3A request/result가 explicit rebuild용 in-process 축소 계약이며, `contracts.md` §7.3의 persistent sync log/outbox envelope는 후속 sync log slice 범위라고 명시했다.
- F2 대응으로 draft-only archive 상태에서 query 결과가 제외되고 include_archived에서는 `draft_archived=True`, `project_archived=False`로 남는 회귀를 추가했다.
- R1 대응으로 archive/status filter는 rebuild가 materialize한 metadata 기준이고, archive 이후 기존 stale record를 즉시 숨기려면 재build 또는 후속 automatic sync가 필요하다고 SoT/plan/HANDOFF에 명확화했다.

### Phase 3A explicit rebuild script 추가

- 변경 파일: `scripts/phase3a_rebuild_source_block_index.py`, `tests/test_phase3a_rebuild_source_block_index_script.py`, `docs/system-contract-sot.md`, `docs/plans/03-indexing-kickoff-decisions.md`, `docs/plans/03-indexing.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-02/work_log.md`.
- `scripts/phase3a_rebuild_source_block_index.py`를 추가했다. `--project-id`, `--snapshot-id`, `CORE_SOT_MONGO_URI`/`--mongo-uri`를 받아 Core SOT MongoDB에서 snapshot blocks를 읽고 deterministic fake vector adapter로 explicit rebuild를 실행한다.
- 출력은 JSON summary로 제한했다: `project_id`, `snapshot_id`, `target`, `records_attempted`, `records_written`, `records_indexed`, `records_query_visible`, `records_archived`.
- Exit code는 full write 성공 0, partial write 1, usage/config/domain error 2다.
- Mongo URI 누락은 usage/config error(exit 2)로 표면화한다.
- SoT를 v1.6.22로 올려 CLI surface와 persistent vector backend/API endpoint가 후속임을 명시했다.
- 독립 검증 `docs/verifications/2026-07-02/phase3a_rebuild_script.md`의 합격 판정 후 비블로킹 권고 O1/O2를 반영해 exit code 계약을 SoT/plan/HANDOFF에 추가하고, `main()` partial write exit 1 회귀를 추가했다.

### Phase 3A explicit rebuild HTTP API 추가

- 변경 파일: `services/application/app/main.py`, `tests/test_application_api.py`, `docs/system-contract-sot.md`, `docs/plans/03-indexing-kickoff-decisions.md`, `docs/plans/03-indexing.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-02/work_log.md`.
- `POST /projects/{project_id}/snapshots/{snapshot_id}/index/source-blocks/rebuild`를 추가했다.
- Endpoint는 현재 deterministic fake vector adapter를 사용해 explicit rebuild를 실행하고 JSON summary를 반환한다: `project_id`, `snapshot_id`, `target`, `backend`, `records_attempted`, `records_written`, `records_indexed`, `records_query_visible`, `records_archived`.
- `backend`는 `in_memory_fake`로 고정해 persistent vector backend가 아직 없음을 public response에 드러냈다.
- missing/cross-project snapshot은 404로 반환한다.
- SoT를 v1.6.23으로 올려 HTTP surface를 명시했다.
- 독립 검증 `docs/verifications/2026-07-02/phase3a_rebuild_http_api.md`의 합격 판정 후 비블로킹 권고 O1을 반영해 CLI와 HTTP의 rebuild summary 계산을 `services/application/app/indexing/service.py`의 공통 helper로 추출했다.

### Phase 2A deployed E2E smoke 추가

- 변경 파일: `scripts/phase2a_deployed_e2e_smoke.py`, `tests/test_phase2a_deployed_e2e_smoke_script.py`, `docker-compose.yml`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-02/work_log.md`.
- `scripts/phase2a_deployed_e2e_smoke.py`를 추가했다. 스크립트는 이미 떠 있는 Application HTTP endpoint만 사용해 project/draft/version 저장, source_ref catalog 3개 생성, analysis job 생성, `/analysis/jobs/{job_id}/run`, candidate read-back까지 수행한다.
- compose application 서비스에 `LLM_GATEWAY_BASE_URL=http://gateway:8001`, `LLM_GATEWAY_MODEL`, `LLM_GATEWAY_TIMEOUT_SECONDS`를 추가해 배포형 runtime에서 Application이 Gateway 컨테이너를 실제 네트워크로 호출하게 했다.
- 로컬 포트 충돌을 피할 수 있도록 `APPLICATION_PORT`, `GATEWAY_PORT`, `MONGO_PORT` env override를 추가했다. 기본값은 기존 `8000`/`8001`/`27017`이라 기본 사용법은 유지된다.
- 새 smoke 스크립트는 `httpx.MockTransport` 기반 테스트로 요청 순서, source_ref 준비, terminal status exit rule, file-path invocation import를 잠갔다.

## Issues found

- 문제: 다음 코드 슬라이스 후보 대부분이 계약 미확정에 막혀 있었다.
- 원인: Phase 3 indexing의 착수 전 결정사항이 아직 해소되지 않았고, tool-call/artifact schema도 상류 wire/schema 계약이 없다.
- Resolution: Phase 3 indexing kickoff 브리프를 추가해 승인할 선택지를 좁혔다.
- Outcome: 승인 후 바로 Phase 3A source block indexing fake-adapter slice로 들어갈 수 있다.

- 문제: Phase 3A를 실제 Chroma/embedding/automatic sync까지 구현하면 외부 backend와 모델 선택을 추측하게 된다.
- 원인: SoT의 미확정 목록에 Chroma embedding model, ES analyzer, sync delivery 방식이 남아 있다.
- Resolution: 첫 slice를 deterministic fake embedding + in-memory vector adapter + explicit rebuild service로 제한했다.
- Outcome: pointer/version/hash/idempotency/archive filter semantics를 외부 인프라 없이 먼저 잠갔다.

- 문제: 독립 검증에서 승인된 slice 항목의 `IndexSyncRequest` 누락과 `IndexSyncResult` shape의 `contracts.md` §7.3 미조정이 발견됐다.
- 원인: 첫 구현이 실제 동작에 필요한 result만 추가했고, Phase 3A 축소 shape와 후속 persistent sync log envelope의 관계를 SoT에 쓰지 않았다.
- Resolution: `IndexSyncRequest`를 모델에 추가하고 `IndexSyncResult`가 request를 포함하도록 바꿨으며, SoT v1.6.21과 계획 문서에 Phase 3A reduced shape의 범위를 명시했다.
- Outcome: F1 contract gap을 닫고 full sync log/outbox 구현은 후속 slice로 남겼다.

- 문제: 독립 검증 mutation test에서 `draft_archived` query exclusion 분기가 테스트에 잠기지 않았음이 확인됐다.
- 원인: 기존 archive 회귀가 project archive만 호출하면서 테스트 이름에는 project/draft를 모두 언급했다.
- Resolution: draft만 archive한 뒤 default query 0건, include_archived 2건, `draft_archived=True`, `project_archived=False`를 단언하는 회귀를 추가했다.
- Outcome: F2 미잠금 분기를 닫았다.

- 문제: Phase 3A indexing service가 domain service로만 있어 수동 rebuild entrypoint가 없었다.
- 원인: 첫 slice는 public Application API와 script 노출을 후속으로 남겼다.
- Resolution: HTTP endpoint보다 작은 CLI script를 먼저 추가해 explicit rebuild를 Mongo Core SOT + fake vector adapter JSON summary로 실행하게 했다.
- Outcome: 운영/디버그용 수동 rebuild 표면이 생겼고, HTTP endpoint 및 persistent vector backend는 후속 결정으로 남았다.

- 문제: CLI script만으로는 Application API 사용자나 smoke에서 explicit rebuild를 호출할 public HTTP 표면이 없었다.
- 원인: Phase 3A 첫 HTTP 노출을 persistent backend 확정 전까지 미뤘다.
- Resolution: `backend=in_memory_fake`를 응답에 포함하는 작은 HTTP command endpoint를 추가했다.
- Outcome: API에서도 source block rebuild 계약을 확인할 수 있고, persistent vector backend/automatic sync는 여전히 후속으로 명확히 남았다.

- 문제: 독립 검증에서 CLI와 HTTP가 같은 rebuild summary 계산을 중복 구현해 drift 위험이 있다고 지적했다.
- 원인: CLI script와 HTTP endpoint가 각각 fresh fake adapter 생성, rebuild, count 계산을 따로 수행했다.
- Resolution: `SourceBlockIndexRebuildSummary`와 `rebuild_source_block_index_summary()`를 indexing service module에 추가하고, CLI/HTTP는 각자 표면 고유 필드만 더하도록 바꿨다.
- Outcome: CLI 8-field와 HTTP 9-field 계약은 유지하면서 공통 count semantics drift 위험을 줄였다.

- 문제: 첫 compose up에서 `8001` host port가 이미 `agent-memory-chroma`에 점유돼 Gateway 컨테이너가 시작하지 못했다.
- 원인: compose가 `8001:8001`을 고정 publish하고 있었다.
- Resolution: host port를 env override 가능하게 바꿨고, 실제 smoke는 `APPLICATION_PORT=8010`, `GATEWAY_PORT=8011`, `MONGO_PORT=27029`로 실행했다.
- Outcome: 기존 기본 포트는 유지하면서 로컬 충돌 환경에서도 배포형 smoke를 실행할 수 있다.

- 문제: sandbox 내부 Python/httpx는 `127.0.0.1:8010`에도 연결하지 못했다.
- 원인: 이전 live smoke와 같은 네트워크 sandbox 제한이다. 같은 endpoint를 `curl`로 확인하면 `/health`는 `{"status":"ok"}`였다.
- Resolution: smoke 스크립트 실행은 승인된 네트워크 권한으로 수행했다.
- Outcome: Application HTTP endpoint까지 연결됐고, 배포형 경로를 실제로 검증했다.

- 문제: 기본 `LLAMA_BASE_URL=http://host.docker.internal:9080`에서는 Gateway upstream 연결이 실패했고, 120초 timeout에서는 실제 모델 호출이 완료되기 전에 `gateway request timed out`으로 실패했다.
- 원인: 현재 모델 endpoint는 `http://192.168.1.29:9080`이고, 모델 처리 속도가 약 5 t/s라 120초가 부족할 수 있다.
- Resolution: `LLAMA_BASE_URL=http://192.168.1.29:9080`, `LLAMA_DEFAULT_MODEL=google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`, `LLAMA_TIMEOUT_SECONDS=900`, smoke client `--timeout-seconds 1000`로 재실행했다.
- Outcome: 배포형 E2E가 `run_http_status=200`, final job `succeeded`, candidates 3개로 통과했다.

## Decisions

- Phase 3A 추천안은 fake embedding/fake vector adapter로 계약과 idempotency/stale semantics를 먼저 잠그는 방향이다.
- 사용자 요청으로 Phase 3A 추천안의 첫 코드 slice를 진행했다. 실제 embedding model, ChromaDB adapter, Elasticsearch adapter, automatic sync/outbox는 계속 후속 결정으로 남긴다.
- 독립 검증 F1은 생략 문서화가 아니라 작은 `IndexSyncRequest` 모델 추가와 SoT v1.6.21 명확화로 닫았다. 이유: 승인된 slice 산출물과 맞고, full sync log/outbox 구현을 추측하지 않으면서도 다음 worker가 §7.3과 혼동하지 않게 한다.
- Archive/status filter는 live query guarantee가 아니라 explicit rebuild가 capture한 metadata 기준으로 명시했다. 즉 archive 이후 즉시 검색 노출을 막는 자동 sync는 후속 결정이다.
- Phase 3A 노출 표면은 Application HTTP API보다 CLI script를 먼저 선택했다. 이유: 현재 backend가 in-memory fake adapter라 HTTP endpoint를 열면 persistent index처럼 오해될 수 있고, script는 explicit rebuild 계약과 summary shape만 작게 잠글 수 있다.
- Phase 3A HTTP rebuild endpoint는 persistent index처럼 보이지 않도록 `backend="in_memory_fake"`를 public response에 포함한다.
- CLI/HTTP rebuild summary 공통화는 `scripts/`가 아니라 `indexing` domain module에 둔다. 이유: HTTP app이 script를 import하면 layering이 뒤집히고, domain helper는 CLI와 HTTP가 함께 재사용할 수 있다.
- Phase 3A rebuild script 검증 권고 중 DEFAULT Mongo DB literal 중복은 그대로 두었다. 이유: `mongo_repository.DEFAULT_DB_NAME`을 top-level import하면 script `--help`와 unit path가 pymongo import에 더 빨리 결합될 수 있어, 현재의 lazy Mongo import 경계를 유지하는 편이 더 작고 안전하다.
- 배포형 Phase 2A smoke는 ASGITransport가 아니라 실제 Application/Gateway 프로세스 네트워크 경로를 확인하는 별도 스크립트로 유지한다. 이유: 기존 live smoke는 같은 프로세스 내 ASGI 조립이라 container DNS, compose env, process boundary를 검증하지 못한다.
- 사용자 지적에 따라 실제 모델 smoke는 240초 같은 짧은 timeout으로 조급하게 실패 판정하지 않고, 모델 처리 속도를 고려해 충분한 timeout을 둔 뒤 리턴 시그널을 기다린다.
- 테스트용 compose 컨테이너는 사용자 요청에 따라 내리지 않았다.

## Verification

- Phase 3 kickoff doc links: `docs/plans/03-indexing-kickoff-decisions.md`가 참조하는 `../system-contract-sot.md`와 `03-indexing.md` 존재 확인.
- Phase 3A compile: `python3 -m py_compile services/application/app/indexing/models.py services/application/app/indexing/service.py tests/test_indexing_phase3a.py` — 통과.
- Phase 3A focused regression: `python3 -m unittest tests.test_indexing_phase3a -v` — 5개 통과.
- Phase 3A broader regression: `python3 -m unittest tests.test_indexing_phase3a tests.test_core_sot -v` — 32개 통과.
- Final full regression after Phase 3A: `python3 -m unittest discover tests -v` — 365개 통과(37 skip).
- Final diff hygiene after Phase 3A: `git diff --check` — 통과.
- Phase 3A verification follow-up compile: `python3 -m py_compile services/application/app/indexing/models.py services/application/app/indexing/service.py tests/test_indexing_phase3a.py` — 통과.
- Phase 3A verification follow-up focused regression: `python3 -m unittest tests.test_indexing_phase3a -v` — 6개 통과.
- Phase 3A verification follow-up broader regression: `python3 -m unittest tests.test_indexing_phase3a tests.test_core_sot -v` — 33개 통과.
- Final full regression after Phase 3A verification follow-up: `python3 -m unittest discover tests -v` — 366개 통과(37 skip).
- Final diff hygiene after Phase 3A verification follow-up: `git diff --check` — 통과.
- Phase 3A rebuild script compile: `python3 -m py_compile scripts/phase3a_rebuild_source_block_index.py tests/test_phase3a_rebuild_source_block_index_script.py` — 통과.
- Phase 3A rebuild script focused regression: `python3 -m unittest tests.test_phase3a_rebuild_source_block_index_script -v` — 6개 통과.
- Phase 3A rebuild script broader regression: `python3 -m unittest tests.test_phase3a_rebuild_source_block_index_script tests.test_indexing_phase3a tests.test_core_sot -v` — 39개 통과.
- Final full regression after Phase 3A rebuild script: `python3 -m unittest discover tests -v` — 372개 통과(37 skip).
- Final diff hygiene after Phase 3A rebuild script: `git diff --check` — 통과.
- Phase 3A rebuild HTTP API compile: `python3 -m py_compile services/application/app/main.py tests/test_application_api.py` — 통과.
- Phase 3A rebuild HTTP API focused regression: `python3 -m unittest tests.test_application_api -v` — 50개 통과.
- Phase 3A rebuild HTTP API broader regression: `python3 -m unittest tests.test_application_api tests.test_phase3a_rebuild_source_block_index_script tests.test_indexing_phase3a tests.test_core_sot -v` — 89개 통과.
- Final full regression after Phase 3A rebuild HTTP API: `python3 -m unittest discover tests -v` — 375개 통과(37 skip).
- Final diff hygiene after Phase 3A rebuild HTTP API: `git diff --check` — 통과.
- Phase 3A rebuild HTTP API verification follow-up compile: `python3 -m py_compile services/application/app/indexing/service.py scripts/phase3a_rebuild_source_block_index.py services/application/app/main.py tests/test_phase3a_rebuild_source_block_index_script.py tests/test_application_api.py` — 통과.
- Phase 3A rebuild HTTP API verification follow-up focused regression: `python3 -m unittest tests.test_phase3a_rebuild_source_block_index_script tests.test_application_api -v` — 56개 통과.
- Phase 3A rebuild HTTP API verification follow-up broader regression: `python3 -m unittest tests.test_application_api tests.test_phase3a_rebuild_source_block_index_script tests.test_indexing_phase3a tests.test_core_sot -v` — 89개 통과.
- Final full regression after Phase 3A rebuild HTTP API verification follow-up: `python3 -m unittest discover tests -v` — 375개 통과(37 skip).
- Final diff hygiene after Phase 3A rebuild HTTP API verification follow-up: `git diff --check` — 통과.
- Compile: `python3 -m py_compile scripts/phase2a_deployed_e2e_smoke.py tests/test_phase2a_deployed_e2e_smoke_script.py` — 통과.
- Focused smoke script regression: `python3 -m unittest tests.test_phase2a_deployed_e2e_smoke_script -v` — 4개 통과.
- Focused broader regression: `python3 -m unittest tests.test_phase2a_deployed_e2e_smoke_script tests.test_application_api tests.test_analysis_gateway_provider -v` — 54개 통과.
- Full regression: `python3 -m unittest discover tests -v` — 360개 통과(37 skip).
- Compose config: `docker compose config` — 통과.
- Diff hygiene: `git diff --check` — 통과.
- Deployed smoke failure preservation: 기본 `host.docker.internal:9080` compose env에서 `run_http_status=502`, final job `failed/provider_error`, `failure_detail="provider is unavailable"` 확인.
- Deployed smoke timeout preservation: 실제 model endpoint + 120초 timeout에서 `run_http_status=502`, final job `failed/provider_error`, `failure_detail="gateway request timed out"` 확인.
- Deployed smoke success: `LLAMA_BASE_URL=http://192.168.1.29:9080 LLAMA_DEFAULT_MODEL=google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0 LLAMA_TIMEOUT_SECONDS=900 APPLICATION_PORT=8010 GATEWAY_PORT=8011 MONGO_PORT=27029 docker compose up -d --build` 후 `python3 scripts/phase2a_deployed_e2e_smoke.py --application-base-url http://127.0.0.1:8010 --timeout-seconds 1000` — `run_http_status=200`, final job `succeeded`, candidates 3개.

## Next steps

- Phase 3A source block indexing service를 public Application API 또는 script로 노출할지 결정한다.
- `/v1/generate-structured`는 repair 후 malformed JSON 비율이나 latency가 운영상 문제로 확인될 때 별도 Gateway slice로 검토한다.
- Phase 3 indexing 계약이 확정되면 archive 후 파생 인덱스 stale 이벤트를 별도 회귀로 다룬다.
