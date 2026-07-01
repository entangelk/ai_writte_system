# Phase 2A Provider/Gateway Runner Factory Wiring 첫 구현 slice 독립 검증

## Subject metadata

- 검증일: `2026-07-01`
- 요청자: 프로젝트 오너("검증하고 의심하고 또 의심해줄래?")
- 검증자: 독립 검증 AI (Claude)
- 검증 대상: Phase 2A provider/Gateway runner factory wiring 첫 구현 slice (SoT v1.6.16)
- 정합 스펙 기준:
  - `docs/plans/02-analysis-provider-wiring-decisions.md` (Approved for Phase 2A provider wiring pre-implementation)
  - `docs/system-contract-sot.md` v1.6.15 / v1.6.16 (변경 이력 + Phase 2A provider wiring 단락)
  - 교차 계약: `services/llm_gateway/app/main.py` (`/v1/generate` route), `services/llm_gateway/app/payload.py`
- 검증 대상 작업 출처: working tree, uncommitted (`git status`에 modified/untracked로 노출). HEAD = `e68015a`.

## Scope

정합 스펙 스코프는 결정 브리프의 §4 literal 계약 + "추천 최소 slice" 1~6 검증 기준 + carried-forward 경계(run endpoint 503, source_anchors 검증)로 좁혔다. 브리프가 chain하는 문서(system-contract-sot, 02-analysis-pipeline, 02-analysis-runner-execution-decisions, llm-gateway) 중 이 slice에 직접 해당하는 surface만 포함했다.

검증 surface:

1. 정합 계약(결정 브리프 + SoT v1.6.15/v1.6.16)의 내부 정합성
2. 구현 코드: `core_sot/{repository,service,mongo_repository}.py`, `analysis/{prompt_templates,prompt_template_mongo_repository,prompt_builder,gateway_provider,extractor}.py`, `main.py`
3. 회귀 테스트: `test_core_sot.py`, `test_core_sot_mongo.py`, `test_core_sot_mongo_indexes.py`, `test_prompt_templates.py`, `test_prompt_template_mongo_indexes.py`, `test_analysis_prompt_builder.py`, `test_analysis_gateway_provider.py`, `test_analysis_extractor_schema.py`, `test_analysis_runner.py`
4. 교차-프로젝트 계약: Application→Gateway `/v1/generate` 요청/응답 wire format
5. 전체 회귀 재실행 + diff hygiene

## Methodology

정합 스펙을 먼저 end-to-end 읽어 경계 매트릭스를 구성한 뒤, 각 분기를 코드와 테스트에 추적했다. 작업자의 work log 주장을 복사하지 않고 primary source에서 재도출했다.

실행한 명령:

- `git status`, `git diff --stat`, `git log --oneline`(변경 범위 파악)
- `git diff <file>`(수정 파일 전부), 신규 파일은 `Read`로 전문 열독
- `python3 -m unittest tests.test_core_sot.CoreSotSourceRefTest tests.test_core_sot_mongo_indexes tests.test_prompt_templates tests.test_prompt_template_mongo_indexes tests.test_analysis_prompt_builder tests.test_analysis_gateway_provider tests.test_analysis_extractor_schema tests.test_analysis_runner tests.test_application_api`(focused 재실행)
- `python3 -m unittest discover tests`(전체 재실행)
- `git diff --check`
- env-wiring 팩토리 수동 구성 실행(`python3 -c "..."`로 `_default_analysis_runner` 직접 호출, 아래 Reproduction)
- `grep -rn "LLM_GATEWAY_BASE_URL\|_default_analysis_runner\|analysis_runner" tests/`(wiring 경로 테스트 커버리지 확인)

## Findings

### Surface 1 — 정합 계약 내부 정합성

- 브리프 §4 literal이 코드에 그대로 존재한다:
  - `prompt_version = "analysis_extract_v1"`, `task_type = "analysis_extract"` — `services/application/app/analysis/prompt_templates.py:8-9`.
  - top-level key `candidates`, 빈 결과 `{"candidates": []}` — prompt builder `output_contract`(`prompt_builder.py:46-50`)와 extractor parse(`extractor.py`)가 일치.
  - "입력 catalog의 id만 사용 / 원문 외 사실 금지" — template literal(`prompt_templates.py:13-14`).
- SoT v1.6.15(결정 승인) → v1.6.16(`/v1/generate` 채택) 계보가 충돌 없이 연속한다. `system-contract-sot.md` 변경 이력 표의 v1.6.15/v1.6.16 행.
- **교차-단락 일치(contradiction 점검 통과)**: SoT v1.6.12는 "source_ref 자동 생성과 Gateway runtime wiring은 이 endpoint 범위가 아니다"라고 명시. v1.6.16은 wiring을 *Application runtime factory*(`create_app`/`_default_analysis_runner`)에 넣었고 run endpoint handler는 주입받은 runner만 사용(`main.py` run handler). 즉 endpoint는 여전히 thin handler이고 wiring 소유권이 factory로 이동한 것이라 v1.6.12와 모순 아님. 검증 합격.

### Surface 2 — 구현 코드 vs 스펙 literal/경계

- Slice 1(catalog read): `CoreSotService.list_source_refs`가 snapshot 존재 + `project_id` 일치를 먼저 검증하고 `NotFound`(`service.py:413-420`), in-memory/Mongo 모두 `project_id + snapshot_id` 필터로 source order 정렬(`service.py:149-167`, `mongo_repository.py:202-213`). Mongo required index `source_refs_by_project_snapshot` 설치(`mongo_repository.py:99-108`).
- Slice 2(versioned template): `PromptTemplateService.seed_analysis_extract_v1`/`get_template`, 같은 `task_type + version`의 다른 template은 `PromptTemplateConflict`(`prompt_templates.py:74-99`). Mongo `uniq_prompt_template_version` unique index(`prompt_template_mongo_repository.py:40-50`).
- Slice 3(prompt builder): snapshot metadata + raw_text + source_ref catalog를 `ChatCompletionRequest`로 조립, 빈 catalog와 cross-snapshot ref는 provider 호출 전 거절(`prompt_builder.py:25-33`). Gateway에 업무 의미를 넘기지 않음(system = template, user = 직렬화 payload). 검증 합격.
- Slice 4(/v1/generate): `GatewayGenerateProvider`가 `/v1/generate`에 POST(`gateway_provider.py:53`).
- Slice 5(provider error 보존): `ProviderError`를 그대로 raise(`gateway_provider.py:54-67, 69-70, 130-136`), content는 기존 `parse_analysis_extraction`으로 통과(`extractor.py` `VersionedPromptAnalysisExtractionAdapter.extract`).
- Slice 6(wiring): `LLM_GATEWAY_BASE_URL` 있으면 `_default_analysis_runner`가 runner 조립, 없으면 `None` → 503(`main.py:146-172, 206-208, 546-549`).
- `{"candidates":[]}` 유효 빈 결과 처리: parse 조건이 `not isinstance(raw_candidates, list)`로 좁아져 빈 배열이 `()`로 파싱(`extractor.py`).

### Surface 3 — 회귀 테스트가 계약을 고정하는지

- 빈 extraction: 양방향 lock 확인. under-strict `test_empty_candidates_array_is_valid_empty_extraction`(`{"candidates":[]}` → `()`), over-strict 교정(malformed 목록에서 빈 배열 케이스 제거), runner `test_runner_succeeds_with_empty_extraction_result`(빈 extraction → `SUCCEEDED` + candidate 0). 합격.
- catalog: `test_list_source_refs_returns_snapshot_catalog_in_source_order`(under-strict, source order), `test_list_source_refs_enforces_project_and_snapshot_boundary`(over-strict, cross-project `NotFound` + missing snapshot `NotFound` 양방향). Mongo round-trip `test_source_ref_catalog_round_trip_from_persisted_store`. index `test_core_sot_mongo_indexes`가 exact index tuple 단정. 합격.
- template: seed/fetch/idempotent/conflict/missing/non-empty 5종. Mongo index `test_prompt_template_mongo_indexes` under/over-strict docstring 포함. 합격.
- prompt builder: catalog 포함 + empty catalog 거절 + cross-snapshot 거절. 합격(단, 아래 Issues N2).
- gateway provider: **실제 gateway app + ASGITransport** 진짜 round-trip(`test_analysis_gateway_provider.py:19-47`), error envelope 보존(`:49-74`), malformed 응답 `INVALID_RESPONSE`(`:76-93`). 강한 테스트. 합격.
- versioned adapter: template + catalog 사용 + catalog 누락 시 provider 미호출(`provider.requests == []`). 합격.

### Surface 4 — 교차-프로젝트 `/v1/generate` wire format

- 응답: gateway route가 `{model, text, finish_reason, usage:{prompt_tokens, completion_tokens, total_tokens}}` 반환(`llm_gateway/app/main.py:160-169`). adapter `_generation_result`가 동일 키(`body["model"]`, `body["text"]`, `body["finish_reason"]`, `usage["prompt_tokens"/"completion_tokens"]`) 읽기(`gateway_provider.py:114-129`). **정확 일치**.
- 요청: `GenerateRequest` 필드(messages/model/temperature/top_p/max_tokens/thinking/chat_template_kwargs, `main.py:29-36`)와 adapter payload(`gateway_provider.py:29-45`)가 동일. `ChatMessage.to_payload()` → `{role, content}`(`payload.py:23-27`)가 gateway `GenerateMessage`({role, content})와 일치. **정확 일치**.
- `SourceRefCatalog` Protocol(`extractor.py`)과 `CoreSotService.list_source_refs` 시그니처 일치. `AnalysisExtractionRunner` 생성자 요구 인자(analysis_service/snapshot_loader/extractor)와 `_default_analysis_runner` 전달 인자 일치.

### Surface 5 — 전체 회귀 재실행

- focused: 95 passed(재현, work log 주장과 일치).
- 전체 discover: 348 passed, 37 skipped(재현, 일치).
- `git diff --check`: clean(재현).

## Issues / Risks

- **[BLOCKING — conditional pass 조건] Slice 6 "env-set → runner 구성 → pending job 실행" 분기가 커밋된 회귀 테스트에 추적되지 않음.**
  - 증거: `grep -rn "LLM_GATEWAY_BASE_URL\|_default_analysis_runner" tests/` → 테스트에 0건. 테스트는 모두 `create_app(..., analysis_runner=runner)`로 runner를 **명시 주입**(`test_application_api.py:796,885,916`)하며, 이 경로는 `if runner is None: runner = _default_analysis_runner(...)`(`main.py:206-208`)에서 팩토리를 건너뛴다. env-unset → 503 분기는 기존 테스트로 잠겨 있으나, env-set → 자동 wiring → pending job 실행 분기는 어떤 테스트도 실행하지 않는다.
  - 브리프 Slice 6 검증 기준이 이를 명시적으로 요구한다("runner 미구성 503이 실제 구성 환경에서는 pending job 실행으로 바뀌고").
  - 현재 코드는 구조적으로 건전하다 — 본 검증에서 `_default_analysis_runner`를 env-set 상태로 직접 호출해 `AnalysisExtractionRunner` + `VersionedPromptAnalysisExtractionAdapter`가 오류 없이 조립되고 `source_validation_enabled == True`임을 실행으로 확인(Surface 5 Reproduction). 즉 결함이 아니라 **lock 부재**.
  - 그럼에도 CLAUDE.md("An untraced branch is a blocking finding regardless of the green bar")에 따라 이 분기는 untraced다. live gateway가 없어도 단위 수준 wiring 회귀(LLM_GATEWAY_BASE_URL 설정 + in-process/fake provider로 create_app이 pending job을 실행하는지)로 잠글 수 있으므로, 작업자가 "live smoke"로만 미룬 것은 단위 lock까지 미루는 것에 해당한다.
  - 권고: env-set 상태에서 create_app이 실제로 default runner를 조립해 pending job을 terminal 상태로 실행하는 회귀를 추가할 것(provider/transport는 주입 가능하도록 factory에 hook을 두거나 monkeypatch). 이 lock이 추가되기 전까지 본 slice는 조건부 합격.

- [NON-BLOCKING, 사전 존재] `parse_analysis_extraction`의 "candidates not-a-list / missing" 분기에 직접 회귀가 없다. malformed 목록에 `{"candidates": <non-list>}` 또는 candidates 누락 케이스가 없다. 이 slice가 도입한 것은 아니며 기존부터 동일. 기록만 남김.

- [NON-BLOCKING] prompt builder의 per-ref 검사(`prompt_builder.py:28-33`)는 `project_id`/`snapshot_id`/`content_hash` 세 조건을 OR로 묶었으나, 개별 조건이 mutation-lock되지 않았다. cross-snapshot(`snapshot_id`)만 단독 테스트. 다만 1차 격리는 catalog query(service layer)에서 이미 잠겨 있으므로 builder 검사는 defense-in-depth이며, 주 계약 경계(cross-project 제외)는 잠겨 있다.

- [NON-BLOCKING, 문서 정밀도] SoT v1.6.16 "근거" 열이 `tests/test_application_api.py`(이 slice에서 미변경)를 포함하고, 정작 이 slice에서 변경되어 빈 extraction→succeeded 흐름을 잠근 `tests/test_analysis_runner.py`를 누락한다. 동작에는 무영향, 근거 목록 정밀도 이슈.

- [BOUNDARY RISK, 비차단] gateway provider의 HTTP 400 비-envelope fallback → `REQUEST_REJECTED` 분기(`gateway_provider.py:101-105`)가 직접 테스트되지 않는다. gateway가 항상 envelope detail을 반환하므로 실발 확률은 낮다.

## Verdict

**조건부 합격(Conditional Pass).**

하중 이유(load-bearing reasons):

- 정합 계약 내부 정합성 합격(SoT v1.6.12 ↔ v1.6.16 모순 없음).
- 교차-프로젝트 `/v1/generate` wire format(요청/응답)이 Application adapter와 정확 일치.
- 브리프 §4 literal과 "추천 최소 slice" 1~5 검증 기준이 코드와 회귀 테스트에 모두 추적됨.
- 빈 extraction 처리는 양방향 lock.
- focused 95 / 전체 348(37 skip) / `git diff --check` 재현.

차단 조건(BLOCKING condition — 합격으로 전환하려면):

- Slice 6 "env-set → 자동 wiring → pending job 실행" 분기를 고정하는 **커밋된 단위 회귀**를 추가할 것. 현재 이 분기는 어떤 테스트도 실행하지 않는다(작업자는 live smoke로만 미뤄뒀지만, 단위 lock은 live gateway 없이 가능).

위 조건이 채워지면 합격. 코드 자체는 현재 구조적으로 건전하므로(factory 조립을 실행으로 확인), 이것은 lock 추가 요구이지 코드 결함 정정 요구가 아니다.

## Outstanding items

- **Live Gateway smoke 미실행**: 실제 `LLM_GATEWAY_BASE_URL`/실서비스 환경이 없어 source_ref catalog가 준비된 snapshot에서 `/analysis/jobs/{job_id}/run` 실연결 smoke를 아직 안 돌림. 작업자가 HANDOFF/work log Next Task #1로 명시. 본 검증도 live 경로는 실행하지 않았다(교차 계약은 static + in-process round-trip으로 검증).
- 위 BLOCKING 조건(env-wiring 단위 회귀) 미해결 상태.
- 검증 과정에서 코드/테스트를 수정하지 않았다(규칙: verifier는 결함을 silently fix하지 않는다). 모든 발견은 오너 결정 후 진행.

## Reproduction

```bash
# focused (work log와 동일 명령)
python3 -m unittest tests.test_core_sot.CoreSotSourceRefTest \
  tests.test_core_sot_mongo_indexes tests.test_prompt_templates \
  tests.test_prompt_template_mongo_indexes tests.test_analysis_prompt_builder \
  tests.test_analysis_gateway_provider tests.test_analysis_extractor_schema \
  tests.test_analysis_runner tests.test_application_api
# 기대: Ran 95 tests ... OK

# 전체
python3 -m unittest discover tests
# 기대: Ran 348 tests ... OK (skipped=37)

# diff hygiene
git diff --check   # clean

# env-wiring factory 수동 구성 확인(코드가 현재 깨지지 않았음을 증명; 커밋된 lock은 아님)
python3 -c "
import os
os.environ['LLM_GATEWAY_BASE_URL']='http://gateway-fake:9999'
from services.application.app.main import _default_core_sot_service, _default_analysis_service, _default_analysis_runner
from services.application.app.analysis.runner import AnalysisExtractionRunner
cs=_default_core_sot_service(); an=_default_analysis_service(cs)
r=_default_analysis_runner(core_sot=cs, analysis=an)
assert isinstance(r, AnalysisExtractionRunner) and an.source_validation_enabled
del os.environ['LLM_GATEWAY_BASE_URL']
assert _default_analysis_runner(core_sot=cs, analysis=an) is None
print('wiring constructs OK; env-unset -> None OK')
"

# untraced 분기 확인(grep 결과 0건이어야 함 = wiring lock 부재 증거)
grep -rn 'LLM_GATEWAY_BASE_URL\|_default_analysis_runner' tests/
```
