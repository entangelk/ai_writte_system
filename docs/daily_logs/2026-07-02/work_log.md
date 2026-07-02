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

- 이번 턴에서 Phase 3A indexing code는 구현하지 않았다. 이유: SoT 미확정 항목(embedding model, ES analyzer, sync delivery, archive/delete 반영)을 임의로 채우면 프로젝트 규칙과 충돌하기 때문이다.
- Phase 3A 추천안은 fake embedding/fake vector adapter로 계약과 idempotency/stale semantics를 먼저 잠그는 방향이다. 실제 embedding model과 ES analyzer는 별도 quality/ops 결정 뒤 확정한다.
- 배포형 Phase 2A smoke는 ASGITransport가 아니라 실제 Application/Gateway 프로세스 네트워크 경로를 확인하는 별도 스크립트로 유지한다. 이유: 기존 live smoke는 같은 프로세스 내 ASGI 조립이라 container DNS, compose env, process boundary를 검증하지 못한다.
- 사용자 지적에 따라 실제 모델 smoke는 240초 같은 짧은 timeout으로 조급하게 실패 판정하지 않고, 모델 처리 속도를 고려해 충분한 timeout을 둔 뒤 리턴 시그널을 기다린다.
- 테스트용 compose 컨테이너는 사용자 요청에 따라 내리지 않았다.

## Verification

- Phase 3 kickoff doc links: `docs/plans/03-indexing-kickoff-decisions.md`가 참조하는 `../system-contract-sot.md`와 `03-indexing.md` 존재 확인.
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

- Phase 3 indexing kickoff 브리프 승인 후 Phase 3A source block indexing fake-adapter slice를 구현한다.
- `/v1/generate-structured`는 repair 후 malformed JSON 비율이나 latency가 운영상 문제로 확인될 때 별도 Gateway slice로 검토한다.
- Phase 3 indexing 계약이 확정되면 archive 후 파생 인덱스 stale 이벤트를 별도 회귀로 다룬다.
