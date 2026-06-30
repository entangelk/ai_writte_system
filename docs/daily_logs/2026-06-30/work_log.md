# Work Log — 2026-06-30

## Goals

- HANDOFF를 읽고 다음 작업을 진행한다.
- Phase 2A의 다음 막히지 않은 slice로 analysis job/candidate HTTP API를 추가한다.
- Phase 2A runner 실행 경계 추천안을 승인된 다음 작업으로 보고 run endpoint API contract를 구현한다.
- 검증자 산출물까지 포함해 커밋한 뒤, HANDOFF의 다음 막히지 않은 작업인 Gemma Q4 live benchmark로 AgentLoopRunner budget/retry production 기본값을 확정한다.

## Completed work

### Phase 2A analysis job/candidate HTTP API 추가

- 변경 파일: `services/application/app/main.py`, `services/application/app/analysis/service.py`, `tests/test_application_api.py`, `docs/system-contract-sot.md`, `docs/plans/02-analysis-pipeline.md`, `CHANGELOG.md`, `HANDOFF.md`, `docs/daily_logs/2026-06-30/work_log.md`.
- HANDOFF의 다음 후보 중 runner→gateway runtime wiring은 model tool-call wire format/payload 확정에 의존해 현재 구현하지 않는 것이 SoT와 일치한다. 따라서 Core SOT API 패턴에 맞춰 analysis job/candidate 상태 노출 API를 먼저 구현했다.
- `AnalysisService.get_job()`를 추가해 repository 내부 `_require_job()`을 public read surface로 열었다.
- `create_app()`가 `analysis_service`를 주입받을 수 있게 하고, 기본 runtime에서는 `CORE_SOT_MONGO_URI`가 있으면 `MongoAnalysisRepository`, 없으면 `InMemoryAnalysisRepository`를 사용하도록 했다.
- 새 API:
  - `POST /projects/{project_id}/analysis/jobs`: `project_id + snapshot_id + idempotency_key` 기준 job idempotent 생성/replay.
  - `GET /projects/{project_id}/analysis/jobs/{job_id}`: job 상태/failure field 조회.
  - `GET /projects/{project_id}/analysis/jobs/{job_id}/candidates`: 저장된 candidate 목록 조회.
- 이 surface는 runner나 Gateway 호출을 시작하지 않는다. 존재하지 않는 project와 cross-project job/candidate 접근은 404로 잠갔다.
- SoT를 v1.6.11로 올리고 `02-analysis-pipeline.md`에 API 경계를 명시했다.

### Phase 2A analysis HTTP API 독립 검증 조건 보강

- 변경 파일: `tests/test_application_api.py`, `HANDOFF.md`, `docs/daily_logs/2026-06-30/work_log.md`.
- 독립 검증 기록 `docs/verifications/2026-06-30/phase2a_analysis_http_api.md`가 조건부 합격으로 I1을 제기했다. 계약이 "존재하지 않는 project → 404"를 3개 endpoint에 적용하지만, 기존 회귀는 POST와 GET job만 건드리고 `GET /projects/{nope}/analysis/jobs/{any}/candidates`를 잠그지 않았다.
- `test_analysis_job_missing_project_returns_404`에 candidates endpoint 호출을 추가해 I1 빈 셀을 폐쇄했다.
- 비차단 권고 I2도 함께 보강했다. `test_analysis_missing_job_under_existing_project_returns_404`를 추가해 존재하는 project 아래 없는 job id에 대해 GET job과 GET candidates가 404를 반환함을 잠갔다.
- I3(빈 `idempotency_key`가 HTTP에서 500이 될 수 있음)는 계약이 명명하지 않은 malformed request 정책 변경이라 이번 조건 폐쇄 범위에서는 건드리지 않고 후속 참고로 남겼다.

### Phase 2A runner 실행 경계 결정 브리프 추가

- 변경 파일: `docs/plans/02-analysis-runner-execution-decisions.md`, `docs/plans/README.md`, `HANDOFF.md`, `docs/daily_logs/2026-06-30/work_log.md`.
- 커밋 `64ec099` 후 HANDOFF의 다음 작업을 이어 진행했다. 다음 구현 후보는 실제 runner 실행을 API/Worker에서 어떻게 시작할지 정해야 하지만, Gateway runtime wiring과 tool-call wire format은 아직 미확정이라 구현으로 들어가면 추측이 된다.
- 이에 당시 미승인 브리프로 선택지와 추천안을 분리했다. 추천안은 별도 `POST /projects/{project_id}/analysis/jobs/{job_id}/run`, 첫 slice는 HTTP 요청 안에서 runner를 실행하고 완료까지 기다리는 방식, 기존 job 상태 무관 replay, runner/factory dependency 주입, source_ref 자동 생성과 Gateway runtime wiring 제외다.
- 실패 HTTP status/error envelope는 이 시점에는 남은 결정이었다. 이후 run endpoint slice에서 missing/cross-project 및 snapshot_not_found 404, runner 미구성 503, schema/source invalid 400, duplicate conflict 409, provider/기타 실행 오류 502로 확정했다.
- `docs/plans/README.md` 읽는 순서에 job-state 브리프와 runner 실행 브리프를 추가했고, `HANDOFF.md` Next Tasks를 승인 대기 상태로 갱신했다.

### Phase 2A analysis run endpoint 추가

- 변경 파일: `services/application/app/main.py`, `services/application/app/analysis/runner.py`, `tests/test_application_api.py`, `tests/test_analysis_runner.py`, `docs/system-contract-sot.md`, `docs/plans/02-analysis-pipeline.md`, `docs/plans/02-analysis-runner-execution-decisions.md`, `CHANGELOG.md`, `HANDOFF.md`, `docs/daily_logs/2026-06-30/work_log.md`.
- 사용자의 "다음 작업 진행" 요청을 runner 실행 브리프 추천안 승인으로 해석해 SoT v1.6.12로 run endpoint 계약을 확장했다.
- `AnalysisExtractionRunner.run_job()`을 추가해 이미 생성된 pending job을 실행할 수 있게 했다. 기존 `run()`은 생성+실행 surface로 유지하고, 기존 job이 있으면 상태 무관 replay하는 기존 계약을 보존했다.
- `create_app(..., analysis_runner=...)` dependency를 추가하고 `POST /projects/{project_id}/analysis/jobs/{job_id}/run`을 구현했다.
- endpoint는 pending job만 runner로 실행하고 요청 안에서 await한다. `running`/`succeeded`/`failed` job은 재실행하지 않고 현재 job과 저장된 candidate를 `idempotent_replay=true`로 반환한다.
- 기본 runtime은 아직 실제 provider/Gateway runner를 구성하지 않으므로 pending job run 요청은 runner 미구성 시 503을 반환한다. Gateway runtime wiring, provider prompt/JSON output contract, source_ref 자동 생성은 후속으로 남겼다.
- 실패 HTTP mapping은 missing/cross-project 및 snapshot_not_found 404, runner 미구성 503, schema/source invalid 400, duplicate conflict 409, provider/기타 실행 오류 502로 잠갔다.

### Phase 2A run endpoint 독립 검증 조건 폐쇄

- 변경 파일: `tests/test_application_api.py`, `tests/test_analysis_runner.py`, `docs/system-contract-sot.md`, `docs/plans/02-analysis-pipeline.md`, `docs/plans/02-analysis-runner-execution-decisions.md`, `HANDOFF.md`, `docs/daily_logs/2026-06-30/work_log.md`.
- 독립 검증 기록 `docs/verifications/2026-06-30/phase2a_run_endpoint.md`가 조건부 합격으로 F4/F5를 제기했고, 비차단 F6도 확인했다.
- F4 폐쇄: `/run` HTTP 경로에서 `DuplicateAnalysisCandidateRequest`가 409로, 일반 provider/기타 exception이 502로 표면화되는 named regression을 추가했다. 각 runner double은 실제 runner처럼 job을 `failed`로 닫고 원본 예외를 다시 던지므로 HTTP status와 GET 가시성을 같이 잠근다.
- F5 폐쇄: 코드가 이미 `snapshot_not_found`를 404로 표면화하고 있었으므로 SoT v1.6.12 run endpoint 계약과 runner execution brief, pipeline plan에 `snapshot_not_found` 404를 명시했다. `/run` HTTP 회귀도 추가해 failed job의 `failure_reason=snapshot_not_found`를 확인한다.
- F6 보강: failed job HTTP replay를 직접 추가하고, `AnalysisExtractionRunner.run_job()`의 non-pending replay 분기를 직접 caller surface에서 잠갔다.

### Gemma Q4 live benchmark 및 AgentLoopRunner budget 기본값 확정

- 변경 파일: `scripts/benchmark_llm_provider.py`, `tests/test_llm_benchmark_script.py`, `docs/benchmarks/2026-06-30/gemma_q4_llama_cpp_repeats3_warmup1.json`, `docs/plans/flat-loop-gate.md`, `docs/plans/README.md`, `docs/plans/implementation-plan.md`, `docs/system-contract-sot.md`, `CHANGELOG.md`, `HANDOFF.md`, `docs/daily_logs/2026-06-30/work_log.md`.
- 검증자 산출물 포함 run endpoint 작업은 먼저 커밋 `4f8182a`로 닫았다.
- HANDOFF의 다음 막히지 않은 작업인 실제 Gemma/llama.cpp endpoint benchmark를 진행했다. `http://192.168.1.29:9080/health`와 `/v1/models`를 확인했고, model은 `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`, context는 8192로 확인됐다.
- `python3 -m scripts.benchmark_llm_provider --base-url http://192.168.1.29:9080 --repeats 3 --warmups 1 --timeout 240`를 실행해 raw report를 `docs/benchmarks/2026-06-30/gemma_q4_llama_cpp_repeats3_warmup1.json`에 저장했다.
- 측정 결과는 전체 failure 0이었다. p95/max token은 `short_smoke` 1.56s/28 tokens, `json_extraction` 8.70s/125 tokens, `continue_scene` 57.16s/407 tokens다.
- `flat-loop-gate.md`에 초기 local MVP production 기본값을 확정했다: `analysis_compare` 2 iterations/45s/1024 tokens/5 tool calls/repeat 2/retry 1+1, `context_search` 3/60s/1536/8/repeat 2/retry 1+1, `writing_generate` 1/120s/1024/no tools/provider retry 1.
- SoT를 v1.6.13으로 올려 benchmark report와 `flat-loop-gate.md`가 production 기본값의 canonical 근거임을 기록하고, 미확정 목록에서 budget/retry production 숫자를 제거했다.
- `scripts/benchmark_llm_provider.py`는 문서와 사용 예시처럼 file path로 직접 실행해도 repo package import가 되도록 `sys.path` bootstrap을 추가했다. `tests/test_llm_benchmark_script.py`에 `python scripts/benchmark_llm_provider.py --help` 회귀를 추가해 CLI 사용 표면을 잠갔다.

### Slice 1 draft version export 추가

- 변경 파일: `services/application/app/core_sot/models.py`, `services/application/app/core_sot/service.py`, `services/application/app/main.py`, `tests/test_core_sot.py`, `tests/test_application_api.py`, `CHANGELOG.md`, `HANDOFF.md`, `docs/daily_logs/2026-06-30/work_log.md`.
- HANDOFF의 Next Tasks(2~6)가 모두 Gateway/model tool-call wire format 등 미확정 결정에 막혀 있어 사용자에게 진행 방향을 물었고, 막히지 않은 Slice 1 잔여 백엔드 작업인 export를 진행하기로 했다(사용자 선택). export 형식은 plain text + Markdown으로 결정했다.
- `DraftVersionExport` immutable model을 추가했다: `format`/`filename`/`content_type`/`body`와 추적 필드(`project_id`/`draft_id`/`version_id`/`version_number`/`snapshot_id`/`content_hash`).
- `CoreSotService.export_draft_version()`을 추가했다. 기존 `get_draft_version()` 위에 build하며, `body`는 두 형식 모두 선택 version snapshot의 `raw_text`를 그대로 내보낸다(변환·strip·AI metadata 주입 없음).
- 형식은 `txt`/`markdown`만 허용한다. `UnsupportedExportFormat`(CoreSotError) 거절, 형식은 content_type(`text/plain`/`text/markdown`)과 filename 확장자(`.txt`/`.md`)만 가른다.
- `GET /projects/{project_id}/drafts/{draft_id}/versions/{version_id}/export?format=txt|markdown` endpoint를 추가했다. unsupported format은 400, missing/cross-project version은 404(기존 `get_draft_version` 격리 경로 재사용).

### Slice 1 export 독립 검증 비차단 note 보강 (N1/N4)

- 변경 파일: `tests/test_core_sot.py`, `tests/test_application_api.py`, `docs/daily_logs/2026-06-30/work_log.md`, `HANDOFF.md`.
- 독립 검증 기록 `docs/verifications/2026-06-30/slice1_draft_version_export.md`는 합격이며 비차단 note 4건을 남겼다.
- N1(허위 인용): export 작업이 새로 넣은 `§113/§115` 인용 2곳(`test_export_survives_archive` docstring, work_log "잠근 범위")을 실제 근거인 "SoT archive 읽기 전용 정책(v1.5, `system-contract-sot.md:136-141`)"로 교정했다. SoT는 번호 조항(§N)이 아니라 마크다운 섹션이라 `§113/§115`는 옛 줄번호를 가리키는 stale 인용이다. 레포 전반(CHANGELOG/HANDOFF/기존 테스트)의 동일 관행은 surgical 원칙상 이번 범위 밖으로 두고 미수정했다.
- N4(직접 회귀 부재): `test_export_survives_draft_and_project_archive`(draft archive + project archive 후 export 200·body 보존)와 `test_export_missing_project_returns_404`를 HTTP 회귀로 추가해 export endpoint를 직접 잠갔다. 기존엔 동일 `get_draft_version` 경로를 다른 endpoint 회귀가 간접 커버했다.
- N2(content_type charset suffix)·N3(filename prefix 미명시)는 계약 위반이 아니고 pin할 조항이 계약에 없어 그대로 둔다.

### benchmark defaults 독립 검증 비차단 권고 보강

- 변경 파일: `docs/verifications/2026-06-30/phase2a_run_endpoint_closure.md`, `docs/verifications/2026-06-30/gemma_benchmark_defaults.md`, `docs/plans/flat-loop-gate.md`, `services/application/app/agent_loop/resolution.py`, `HANDOFF.md`, `docs/daily_logs/2026-06-30/work_log.md`.
- 검증 AI의 폐쇄 검증 기록 2건을 확인했다. `phase2a_run_endpoint_closure.md`와 `gemma_benchmark_defaults.md` 모두 합격이며, 검증자가 보고한 수치와 재계산 근거를 원문 산출물로 보존했다.
- `gemma_benchmark_defaults.md`의 비차단 권고 2건을 보강했다. `flat-loop-gate.md`의 `context_search` 근거 문구가 1536 token ceiling과 모순되지 않도록 "measured extraction에 token 여유"를 둔다는 설명으로 정정했다.
- `resolution.py`의 benchmark 이전 시제 주석을 benchmark 이후 현재 상태에 맞게 "flat-loop-gate.md가 소유"하는 숫자 기본값으로 정정했다.

## Issues found

- 문제: HANDOFF의 다음 작업은 analysis HTTP API와 runner→gateway runtime wiring 중 선택이 필요하다고 되어 있었다.
- 원인: runtime wiring은 Gateway tool-call response parsing, model tool-call wire format, Phase payload/tool handler가 아직 미확정이라 구현하면 wire를 추측하게 된다.
- Resolution: 막힌 wiring은 그대로 Next Tasks에 남기고, 상태/결과 노출 HTTP API만 좁게 구현했다.
- Outcome: Phase 2A job/candidate를 UI나 후속 worker가 조회할 수 있는 최소 public surface가 생겼고, 미확정 LLM/tool-call 계약은 건드리지 않았다.

- 문제: 독립 검증이 GET candidates missing-project 404 회귀 누락을 발견했다.
- 원인: POST와 GET job missing-project는 같은 테스트에서 잠겼지만, candidates handler의 `_require_project_exists()` 호출은 endpoint-specific 회귀가 없었다.
- Resolution: candidates missing-project 404 회귀를 추가했고, 권고였던 existing-project missing job 404도 GET job/GET candidates 양쪽으로 보강했다.
- Outcome: 조건부 합격의 차단 조건 I1이 폐쇄됐고, 권고 I2도 회귀로 잠겼다.

- 문제: runner 실행 API를 바로 구현하려면 실행 트리거, 동기/비동기 경계, replay semantics, runner dependency 주입, 실패 HTTP mapping을 정해야 한다.
- 원인: 기존 SoT는 HTTP 상태/결과 노출 API만 승인했고, Gateway/model tool-call/runtime wiring은 미확정으로 남아 있다.
- Resolution: 구현 대신 결정 브리프를 작성해 선택지와 추천안을 분리했다.
- Outcome: 다음 구현자가 추측 없이 사용자 승인 후 run endpoint 또는 Worker 실행 slice로 들어갈 수 있다.

- 문제: 독립 검증이 runner 실행 브리프의 "동기 함수형 orchestration" 표현이 실제 코드와 모순된다고 지적했다.
- 원인: `AnalysisExtractionRunner.run`은 `async def` coroutine인데, 브리프가 Python sync/async 축과 HTTP 요청-블로킹/background enqueue 축을 섞어 표현했다.
- Resolution: 브리프의 확정 경계를 "async coroutine이며 호출자가 await/bridge 필요"로 고치고, Q2를 "요청 안에서 완료까지 기다리는가 background/worker에 넘기는가"로 재구성했다. `running` replay는 `idempotent_replay=true`로 명시했고, run API 구현 시 SoT minor update가 필요함도 남겼다.
- Outcome: 조건부 합격 I1의 사실 오류가 폐쇄됐고, 사용자 승인 전제가 코드와 일치한다.

- 문제: 기존 `AnalysisExtractionRunner.run()`은 job 생성과 실행을 함께 소유해서, 이미 생성된 job을 `job_id`로 실행하는 API와 맞지 않았다.
- 원인: `run()`이 같은 `project_id + snapshot_id + idempotency_key` 기존 job을 찾으면 상태 무관 replay로 반환하는 계약을 갖고 있었다.
- Resolution: 기존 `run()` 계약은 유지하고, `AnalysisExtractionRunner.run_job()`을 별도로 추가해 existing pending job 실행 surface를 만들었다.
- Outcome: `POST .../run`이 생성/조회 API와 분리된 job 실행 endpoint가 됐고, 기존 runner replay 회귀는 그대로 통과했다.

- 문제: 독립 검증이 `/run` endpoint HTTP mapping 중 409와 502가 테스트에서 비어 있고, `snapshot_not_found` HTTP status가 계약에 명시되지 않았다고 지적했다.
- 원인: 기존 회귀는 200/400/404/503만 직접 밟았고, SoT v1.6.12 문구가 `snapshot_not_found`를 failure_reason에는 열거했지만 run endpoint HTTP mapping에는 넣지 않았다.
- Resolution: duplicate conflict 409, provider/기타 502, snapshot_not_found 404를 `/run` HTTP 테스트로 추가하고, 계약 문서에 snapshot_not_found 404를 명시했다.
- Outcome: 조건부 합격의 F4/F5가 폐쇄됐고, 비차단 F6도 direct regression으로 보강됐다.

- 문제: `python3 scripts/benchmark_llm_provider.py --help`가 `ModuleNotFoundError: No module named 'services'`로 실패했다.
- 원인: script를 module mode가 아니라 file path로 실행하면 Python이 repo root를 import path에 넣지 않는다.
- Resolution: `__package__`가 비어 있는 직접 실행 경로에서 repo root를 `sys.path`에 추가하고, subprocess 회귀를 추가했다.
- Outcome: 문서와 직관적인 CLI 사용 방식이 동작하며, 기존 `python3 -m scripts.benchmark_llm_provider` 실행 방식도 유지된다.

- 문제: sandbox 안의 Python/httpx benchmark가 endpoint에 연결하지 못했지만 `curl`은 성공했다.
- 원인: sandbox network 제약으로 보이는 `httpx.ConnectError('All connection attempts failed')`가 발생했다.
- Resolution: 사용자 승인된 escalated command로 benchmark를 재실행했다.
- Outcome: live benchmark가 완료되어 budget/retry production 기본값을 추측 없이 확정할 수 있었다.

- 문제: 독립 검증이 `context_search` budget 근거 문장과 실제 1536 token ceiling 사이의 수치 비일관, 그리고 benchmark 완료 후 stale해진 retry 주석을 발견했다.
- 원인: benchmark 기본값을 확정하면서 값은 업데이트됐지만 설명 문장 일부가 이전 표현을 유지했다.
- Resolution: 값은 유지하고 문구만 현재 계약과 수치에 맞게 정정했다.
- Outcome: 검증의 비차단 권고 2건이 문서/주석 수준에서 폐쇄됐다.

## Decisions

- Analysis HTTP API는 job 생성/replay와 조회만 담당하고 runner 실행 트리거를 포함하지 않는다. 이유: 실행 wiring은 별도 계약이 필요하며, 이 slice의 목적은 이미 구현된 analysis 상태를 public Application API로 노출하는 것이다.
- `POST /projects/{project_id}/analysis/jobs`는 project 존재만 검증하고 snapshot 존재는 앞당겨 검증하지 않는다. 이유: runner의 `snapshot_not_found` failure_reason 계약이 이미 snapshot load 실패를 소유한다.
- Runner 실행 경계는 승인 전까지 구현하지 않는다. 추천안은 브리프에 남겼지만, 실패 HTTP status/error envelope는 사용자 결정이 필요하다.
- Runner는 async coroutine이므로, "동기 실행"이라는 표현은 Python 함수 형태가 아니라 HTTP 요청이 완료까지 기다리는지 여부로만 사용한다.
- Runner 실행 경계 추천안은 이번 사용자 요청으로 승인된 다음 작업으로 처리했다. 별도 run endpoint, 요청 안 await, 상태 무관 replay, runner dependency 주입, source_ref 자동 생성/Gateway wiring 제외를 채택했다.
- 실패 HTTP mapping은 이번 API contract slice에서 최소 public 계약으로 고정했다: missing/cross-project 및 snapshot_not_found 404, runner 미구성 503, schema/source invalid 400, duplicate conflict 409, provider/기타 실행 오류 502.
- 독립 검증 F5에 따라 `snapshot_not_found`는 run endpoint에서 404로 표면화하는 것이 canonical이다. 이유: snapshot loader가 같은 project의 snapshot을 찾지 못한 상태는 missing resource이며, job은 실패 상태로 보존되어 이후 GET으로 조회된다.
- AgentLoopRunner production budget/retry 기본값은 2026-06-30 Gemma Q4_0 llama.cpp benchmark report를 canonical 근거로 삼는다. 이 값은 현재 local MVP endpoint 기준의 초기 상한이며, 모델·quant·prompt shape·tool handler latency가 바뀌면 같은 benchmark/report 절차로 재확정한다.

## Verification

- `python3 -m py_compile services/application/app/main.py services/application/app/analysis/service.py tests/test_application_api.py`
- `python3 -m unittest tests.test_application_api -v` — 28개 통과.
- `python3 -m unittest discover tests -v` — 303개 통과(35 skip).
- 잠근 범위: job create/replay/get, candidate list read-back, missing project 404(POST/GET job/GET candidates), existing-project missing job 404, cross-project job/candidate 404.
- 문서-only 추가 검증: `docs/plans/02-analysis-runner-execution-decisions.md`의 기준 문서 링크와 `docs/plans/README.md`/`HANDOFF.md` 참조 대상 존재 확인.
- runner 실행 브리프 보강 검증: `services/application/app/analysis/runner.py`의 `async def run` 및 `tests/test_analysis_runner.py`의 `await runner.run` 호출과 브리프의 async/await 표현 일치 확인.
- `python3 -m py_compile services/application/app/main.py services/application/app/analysis/runner.py tests/test_application_api.py tests/test_analysis_runner.py`
- `python3 -m unittest tests.test_application_api tests.test_analysis_runner -v` — 50개 통과.
- `python3 -m unittest discover tests -v` — 309개 통과(35 skip).
- 잠근 범위: injected runner로 pending job 실행, terminal/running replay 비재실행, missing/cross-project run 404, pending runner 미구성 503, runner 실패 시 job failed 상태 보존+HTTP 400, `AnalysisExtractionRunner.run_job()` existing pending job 실행.
- 보강 후 `python3 -m py_compile services/application/app/main.py services/application/app/analysis/runner.py tests/test_application_api.py tests/test_analysis_runner.py`
- 보강 후 `python3 -m unittest tests.test_application_api tests.test_analysis_runner -v` — 54개 통과.
- 보강 후 `python3 -m unittest discover tests -v` — 313개 통과(35 skip).
- 보강 후 잠근 범위: `/run` duplicate conflict 409, provider/기타 exception 502, snapshot_not_found 404, failed job replay, `AnalysisExtractionRunner.run_job()` non-pending replay.
- benchmark endpoint 확인: `curl -sS --max-time 5 http://192.168.1.29:9080/health` → `{"status":"ok"}`, `/v1/models` → `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`.
- live benchmark: `python3 -m scripts.benchmark_llm_provider --base-url http://192.168.1.29:9080 --repeats 3 --warmups 1 --timeout 240` — 3 case 모두 failure 0, report 저장 완료.
- `python3 -m py_compile scripts/benchmark_llm_provider.py tests/test_llm_benchmark_script.py`
- `python3 scripts/benchmark_llm_provider.py --help` — `--base-url` 옵션 표시 확인.
- `python3 -m unittest tests.test_llm_benchmark_script -v` — 8개 통과.
- `python3 -m unittest discover tests -v` — 314개 통과(35 skip).
- 검증 기록 확인: `docs/verifications/2026-06-30/phase2a_run_endpoint_closure.md`, `docs/verifications/2026-06-30/gemma_benchmark_defaults.md`.
- benchmark defaults 비차단 권고 보강 후 stale 문구 pattern sweep — 추가 발견 없음.
- `python3 -m py_compile services/application/app/agent_loop/resolution.py`
- `python3 -m unittest tests.test_agent_loop_resolution -v` — 18개 통과.

- export 자체 회귀: `python3 -m py_compile services/application/app/main.py services/application/app/core_sot/service.py services/application/app/core_sot/models.py tests/test_core_sot.py tests/test_application_api.py` 통과.
- `python3 -m unittest tests.test_core_sot.CoreSotExportTest tests.test_application_api -v` — 47개 통과.
- 독립 검증 N1/N4 보강 후 `python3 -m unittest discover tests` — 327개 통과(35 skip, export 회귀 +2).
- export 잠근 범위: body가 선택 version snapshot raw_text와 정확히 일치, 요청한 version 선택(latest 아님), txt/markdown은 content_type/확장자만 차이·body 동일, unsupported format 거절, missing version NotFound, archive 후 export 보존(SoT archive 읽기 전용 정책, v1.5); HTTP는 200 traceability payload, markdown query, unsupported 400, missing 404, cross-project 404, archived-draft export 200, missing-project export 404.

## Next steps

- 다음 Phase 2A 작업은 실제 provider/Gateway runner factory wiring이다. 단 Gateway JSON output/prompt 계약, source_ref 생성 boundary, model tool-call wire format이 확정되기 전까지 구현하지 않는다.
- Gateway `/v1/generate` runtime wiring과 domain tool-call branch는 model tool-call wire format/payload 확정 뒤 구현한다.
