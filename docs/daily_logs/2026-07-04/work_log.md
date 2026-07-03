# Work Log — 2026-07-04

## Goals

- HANDOFF와 최신 work log를 읽고 다음 작업을 진행한다.
- HANDOFF Next Tasks 1의 Phase 4 Slice 4.2(터미널 JSON LLM planner adapter)를 구현한다.
- 새 테스트 머신에는 외부 llama.cpp LLM 서버가 없으므로, 로컬 llama.cpp GPU 서버를 Docker로 띄워 환경을 맞춘다.

## Completed work

### Phase 4 Slice 4.2 터미널 JSON LLM planner adapter 구현 (SoT v1.6.33)

- 변경 파일: `services/application/app/context_search/planner.py`(신규), `tests/test_context_search_planner.py`(신규), `scripts/phase4_context_search_planner_live_smoke.py`(신규), `docs/plans/04-agentic-search-kickoff-decisions.md`, `docs/system-contract-sot.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-04/work_log.md`.
- 브리프 §9.2 승인 범위를 구현했다. Phase 2A `VersionedPromptAnalysisExtractionAdapter` 패턴을 그대로 따라간다.
- versioned prompt template: `CONTEXT_SEARCH_PLAN_TASK_TYPE = "context_search_plan"`, `CONTEXT_SEARCH_PLAN_PROMPT_VERSION = "context_search_plan_v1"`, `CONTEXT_SEARCH_PLAN_TEMPLATE` 상수와 `seed_context_search_plan_template()` 헬퍼를 추가했다. 기존 `analysis/prompt_templates.py`의 `PromptTemplateService.seed_template()` 저장소를 재사용하고, analysis 모듈은 건드리지 않았다(surgical).
- `build_context_search_plan_request()`: system=template, user=JSON payload(project_id/purpose/query/has_current_position/needs+need별 allowed_tools/tool_literals/output_contract). `project_id`는 모델이 아니라 request에서 주입한다.
- `parse_search_plan(content, project_id)`: strict JSON object → `steps` 배열 → 각 step(step_id 비어있지 않은 str, need∈`ContextNeed`, tools 비어있지 않은 배열 각 원소∈`SearchTool`, query str). enum literal 위반은 `SearchPlanParseError`. `plan_id`는 모델이 주면 쓰고 없으면 기본값.
- `TerminalJsonSearchPlanner.build_plan()`(async): template 조회 → Gateway `/v1/generate` 1-turn → strict parse. parse 실패 시 원문 output/parser error/원 user payload로 1회 repair 후 재parse. 그래도 실패하면 `ContextSearchFailed(llm_error)`. template 부재도 `llm_error`.
- live smoke `scripts/phase4_context_search_planner_live_smoke.py`: 실제 Gateway → llama.cpp endpoint로 planner를 실행하고 produced SearchPlan(또는 llm_error)을 JSON으로 출력한다. Phase 2A live smoke와 같은 in-process gateway app + `httpx.ASGITransport` 배선을 쓴다.
- SoT를 v1.6.33으로 올리고 Phase 4 섹션·브리프 §9.2 후속을 반영했다.

## Decisions

- **경계 분담 — adapter는 literal 멤버십만, plan 의미는 service가 소유**: 브리프 §9.2 item 3은 "§1 집합 밖 literal은 repair 후에도 남으면 llm_error"만 요구한다. 따라서 adapter는 need/tool의 enum 멤버십만 검증하고, plan 의미 검증(미요청 need, need별 불허 tool, project_id 일치)은 Slice 4.1 `ContextSearchService._validate_plan`이 계속 소유한다. 두 계층이 겹치지 않아 중복 검증이 없다.
- **async adapter + sync service seam 유지**: LLM provider(`generate`)가 async라 planner adapter도 async로 만들었다(Phase 2A와 동일). Slice 4.1의 sync `SearchPlanner` Protocol과 sync `build_context_package`는 fake 주입 seam으로 그대로 두었다. async planner를 sync service에 통합하려면 service를 async로 올려야 하는데, 이는 브리프가 "후속 slice"로 명시한 HTTP wiring 범위라 이번 slice에서 하지 않았다. 이 재조정 지점을 planner 모듈 docstring·브리프·SoT·HANDOFF에 명시했다.
- **error type = llm_error**: planner가 낸 malformed/out-of-set output은 브리프 error taxonomy의 `llm_error`(planner provider 계열)로 매핑한다. service `_build_plan`도 planner 예외를 llm_error로 감싸므로 wiring 이후에도 계열이 유지된다.

## Issues found

- 문제: 없음. Slice 4.1 계약이 SearchPlan/SearchPlanStep 모델과 planner 주입 seam을 이미 정의해 두어 adapter는 그 계약을 채우기만 하면 됐다.

## Verification

- `python3 -m py_compile services/application/app/context_search/planner.py tests/test_context_search_planner.py scripts/phase4_context_search_planner_live_smoke.py` 통과.
- `python3 -m unittest tests.test_context_search tests.test_context_search_planner -v` 46개 통과(planner 18개 신규).
- 전체 `python3 -m unittest discover tests` 457 실행 중 413 passed / 44 skipped(pytest 413 passed / 44 skipped 재현). `git diff --check` 통과. (통과 수는 unittest "Ran N" 대신 passed/skipped를 분리 표기한다 — v1.6.32 검증이 지적한 "Ran N 오독" 반복 방지.)
- 잠근 범위(양방향): valid SearchPlan strict parse(literal + request project_id 주입, over-strict), plan_id 기본값, 알 수 없는 need/tool literal parse error(under-strict), non-JSON/bad shape 5종, prompt payload(template + needs/allowed_tools), markdown-fenced 1회 repair, invalid literal 1회 repair 후 성공, repair prompt에 parser_error/invalid_output 포함, repair 후에도 실패 시 `llm_error`, 1회 초과 재시도 금지(정확히 2회 provider 호출), template 부재 `llm_error`.

### Slice 4.2 독립 검증 조건부 합격의 빈 셸 3종 폐쇄

- 변경 파일: `tests/test_context_search_planner.py`, `docs/daily_logs/2026-07-04/work_log.md`, `HANDOFF.md`.
- 독립 검증(`docs/verifications/2026-07-04/context_search_slice_4_2.md`, 조건부 합격)은 본질 경계는 mutation으로 양방향 잠금됐음을 확인하면서도, contract가 요구하는 step-schema shape 분기 3종이 regression 없이 빈 셸로 남았음을 지적했다: B1 step key exact-match(`set(item.keys()) != {...}`), B2 non-string query(`_string`), B4 present 빈 문자열 `plan_id`(`_plan_id`). 세 경계 모두 코드에는 존재하나 pin하는 회귀가 없어 guard를 무력화해도 기존 13개가 전부 통과했다.
- 회귀 5개를 추가했다: B1 양방향(extra field should-fire + missing field should-fire) + non-object step(B1 sibling, 검증 line 147 권장), B2 non-string query should-fire, B4 present 빈 plan_id should-fire(부재→기본값 case는 기존 회귀가 이미 잠금). test docstring에 잠그는 방향을 명시했다.
- 각 guard를 개별 무력화하는 mutation으로 re-fail을 실증했다: B1(`if set(...)!=...` → `if False`) 2건 재실패, non-object(`if not isinstance(item, Mapping)` → `if False`) 1건 재실패, B2(`_string`의 isinstance 검사 제거) 1건 재실패, B4(`_plan_id`의 `or not value` 제거) 1건 재실패. 네 mutation 모두 복원 후 전체 통과.
- 비차단 정정: 직전 기록의 "Ran 452 OK(skipped=44)"는 "Ran N" 오독으로, 실제 passed = 452−44 = 408(회귀 5개 추가 후 457−44 = 413)이다. 이후 기록은 passed/skipped를 분리 표기한다.

### 로컬 llama.cpp GPU 서버 opt-in 구성 (환경 정합)

- 변경 파일: `docker-compose.llama.yml`(신규), `docs/runbooks/local-llama-server.md`(신규), `HANDOFF.md`, `docs/daily_logs/2026-07-04/work_log.md`.
- 새 테스트 머신(RTX 3060 12GB, 16코어/15GB RAM, nvidia runtime + container-toolkit 1.18.2)에는 이전 작업 머신의 외부 llama.cpp endpoint(`192.168.1.29:9080`)가 없다. 사용자 결정으로 실제 llama.cpp GPU 서버를 Docker로 띄워 환경을 맞췄다(모델은 이전 벤치와 동일한 12B QAT 정합).
- 기존 `docker-compose.yml`은 의도적으로 llama.cpp 서버를 stack 밖으로 위임(주석 명시)하므로, 그 아키텍처를 훼손하지 않도록 **별도 opt-in override** `docker-compose.llama.yml`을 추가했다. base만 쓰면 종전대로 외부 `LLAMA_BASE_URL`이고, override를 함께 넘길 때만 in-stack `llama` 서비스가 뜬다: `docker compose -f docker-compose.yml -f docker-compose.llama.yml up -d`.
- `llama` 서비스: image `ghcr.io/ggml-org/llama.cpp:server-cuda`, `-hf ${LLAMA_HF_REPO:-google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0}` + `--jinja`(llama.cpp `chat_template_kwargs.enable_thinking` 지원 필요) + `--n-gpu-layers 99` + `--ctx-size 8192`, host port 9080. GGUF 다운로드는 `LLAMA_CACHE=/models` + `llama_models` 볼륨으로 캐시해 재기동 시 재다운로드하지 않는다. GPU는 `deploy.resources.reservations.devices`(nvidia)로 전달한다.
- override는 `gateway`의 `LLAMA_BASE_URL`을 `http://llama:9080`으로 덮고 `depends_on: llama: service_healthy`를 걸어, llama가 healthy(모델 로드 완료)된 뒤에만 gateway가 뜨고, 그 뒤 application이 뜨는 순서를 보장한다. `llama` healthcheck는 gateway `/health/ready`가 upstream으로 확인하는 것과 같은 `GET /health`를 curl로 친다(start_period 120s, retries 60 — 12B 로드 여유).
- gateway가 llama.cpp 서버에 요구하는 계약은 `GET /health`(readiness) + `POST /v1/chat/completions`(OpenAI 호환 응답 + `chat_template_kwargs`) 둘뿐임을 코드(`client.py`, `main.py`)에서 확인했고, `llama-server`가 이를 충족한다. runbook에 계약·prerequisite·env override 표·smoke·teardown을 정리했다.

## Next steps

- 로컬 llama.cpp 서버 기동 완료 후: `curl localhost:9080/health`와 gateway `/health/ready`로 upstream readiness를 확인하고, `LLAMA_BASE_URL=http://localhost:9080 python3 scripts/phase4_context_search_planner_live_smoke.py --timeout-seconds 1000`로 Slice 4.2 planner를 실제 모델로 검증한다(valid SearchPlan 또는 repair 후 `llm_error`). 12B는 느리므로(~5 t/s) timeout을 넉넉히 둔다.
- 이후 Phase 4 HTTP API surface + `TerminalJsonSearchPlanner`의 `ContextSearchService` wiring(service를 async로 올림)이 다음 slice다.

## 검증 상태 (env)

- `docker compose -f docker-compose.yml -f docker-compose.llama.yml config` 병합/검증 통과: gateway `LLAMA_BASE_URL=http://llama:9080` + `depends_on llama(service_healthy)`, llama GPU device 예약이 정상 반영됨.
- 이미지 tag `ghcr.io/ggml-org/llama.cpp:server-cuda` 존재 확인(`docker manifest inspect`). 호스트에 nvidia runtime + container-toolkit 1.18.2 존재 확인.
- `docker compose ... up -d llama`로 기동 착수 — CUDA 이미지 + 12B QAT GGUF(~7GB) 다운로드는 대용량이라 세션 내 완료 여부는 별도 확인 필요. `docker compose -f docker-compose.yml -f docker-compose.llama.yml logs -f llama`로 로드 진행을 보고 `ps`가 `healthy`가 되면 실제 모델 smoke를 실행한다.
