# Verification — Phase 2A analysis job/candidate HTTP read surface

## Subject metadata

- 날짜: 2026-06-30
- 요청자: 사용자 ("클로드 작업 AI가 작업한 분 읽고 검증하고 의심하고 또 의심해줄래")
- 검증자: Claude (독립 감사, 구현 미관여)
- 대상 slice: Phase 2A analysis job/candidate HTTP API (SoT v1.6.11)
- 정본 계약 참조:
  - `docs/system-contract-sot.md` v1.6.11 (계약 버전 라인, 변경 이력 v1.6.11 엔트리, §"Phase 2A Application API" bullet)
  - `docs/plans/02-analysis-pipeline.md` §Phase 2A "Application API는 …" bullet
- 검증 대상 소스: working tree, uncommitted (`git status` — 7개 파일 modified, `docs/daily_logs/2026-06-30/` untracked). commit hash 없음.

## Scope

정본 계약이 이 slice에 대해 명명한 표면만 감사한다. 계약이 명명하지 않은 영역(runner 내부, Mongo 저장, job-state 전이)은 직전 slice에서 별도 검증됐으므로 제외한다.

1. **계약 자체 일관성** — SoT v1.6.11 변경이력/본문 bullet, plan §2A bullet, CHANGELOG, HANDOFF가 같은 literal을 쓰는지.
2. **Spec↔implementation literal 일치** — 3개 엔드포인트 경로, idempotency 기준, "runner/Gateway 시작 안 함", 404 조건.
3. **구현 회로** — `main.py` 3개 핸들러 + helper, `service.py` `get_job` public surface, 프로젝트 격리/404 매핑.
4. **회귀 테스트** — `tests/test_application_api.py` 신규 3개 테스트가 계약 boundary를 실제로 고정하는지.
5. **전체 스위트 재현** — worker가 보고한 카운트(27 / 302+35skip)를 독립 재실행.
6. **경계 행렬** — 계약이 명명한 모든 "발생해야/발생하지 않아야" 분기 → 회귀 테스트 추적.

## Methodology

정본 계약 스코프를 먼저 빌드했다(SoT v1.6.11 엔트리 + §2A bullet + plan §2A bullet + HANDOFF Active/Verification 라인). 이 영역만 end-to로 읽고 경계 행렬을 만든 뒤, 코드/테스트/런을 그 행렬에 대입했다. worker의 work log 주장은 복사하지 않고 primary source에서 재도출했다.

실행한 명령(정확한 복제 시퀀스는 §Reproduction):
- `git --no-pager diff HEAD -- <file>` 로 7개 파일 전체 diff 검토
- `python3 -m py_compile services/application/app/main.py services/application/app/analysis/service.py tests/test_application_api.py`
- `python3 -m unittest tests.test_application_api -v`
- `python3 -m unittest discover tests`
- `git --no-pager diff --check`
- symbol/line 검증: `grep`/`Read` 로 `service.py`(get_job, _require_job, list_candidates, list_candidates_for_job, error class), `models.py`(StrEnum literal), `core_sot/service.py`(NotFound/get_project), `main.py`(import, helper, 핸들러) 확인

## Findings

### F1. 계약 자체 일관성 — PASS

5개 문서가 동일 literal을 사용한다:
- 엔드포인트 3종: `POST /projects/{project_id}/analysis/jobs`, `GET /projects/{project_id}/analysis/jobs/{job_id}`, `GET /projects/{project_id}/analysis/jobs/{job_id}/candidates`
- idempotency 기준: `project_id + snapshot_id + idempotency_key`
- "runner/Gateway 실행을 시작하지 않는다"
- "존재하지 않는 project 또는 cross-project job/candidate 접근은 404"

SoT v1.6.11 변경이력(`docs/system-contract-sot.md:36`)·SoT §2A bullet(`docs/system-contract-sot.md:321`)·plan §2A bullet(`docs/plans/02-analysis-pipeline.md:35`)·CHANGELOG(`CHANGELOG.md:5`, `CHANGELOG.md:49`)·HANDOFF(`HANDOFF.md:84`, `HANDOFF.md:100`)가 서로 모순 없이 일치한다. SoT 헤더의 `계약 버전: v1.6.11`(`docs/system-contract-sot.md:4`)과 문서 역할 표의 `Approved SoT v1.6.11`(`docs/system-contract-sot.md:60`)도 같이 올라갔다. 계약 내부 충돌 없음.

### F2. Spec↔implementation literal 일치 — PASS

- 3개 경로가 코드에 그대로 존재: `main.py:340`(POST), `main.py:358`(GET job), `main.py:367`(GET candidates).
- idempotency 기준: `AnalysisService.create_job`(`service.py:179-200`)이 `find_job_request(project_id, snapshot_id, idempotency_key)`(`service.py:184-186`)로 replay를 판별 — 계약 literal과 동일.
- "runner/Gateway 시작 안 함": `main.py`에 runner/gateway/generate import 없음(`grep` 확인). 3개 핸들러는 `create_job`/`get_job`/`list_candidates`만 호출한다. 구조적으로 계약 부합.
- 404 매핑: missing project는 `_require_project_exists`(`main.py:162`) → `core_sot.get_project` → `NotFound`(`core_sot/service.py:199,382`) → `HTTPException(404)`. cross-project/missing job은 `AnalysisService._require_job`(`service.py:496-500`, `job is None or job.project_id != project_id`) → `AnalysisNotFound` → GET 핸들러들이 `(AnalysisNotFound, NotFound)`를 잡아 404(`main.py:363,374`). POST 핸들러는 `NotFound`만 잡는다(`main.py:352-354`) — POST 경로의 유일한 not-found 원천이 project 존재이므로 정확하다.

### F3. 구현 회로 — PASS

- `AnalysisService.get_job`(`service.py:202-203`)은 private `_require_job`을 위임만 한다. project_id 스코핑을 우회하지 않고 그대로 보존하므로 public read surface로서 캡슐화 위반이 없다.
- `list_candidates`(`service.py:422-426`)는 `_require_job(project_id, job_id)`로 job 소유권을 먼저 검증한 뒤 `list_candidates_for_job(project_id, job_id)`(`service.py:155-162`, `candidate.project_id == project_id and candidate.job_id == job_id`)로 필터링 — cross-project candidate 노출 경로 없음.
- `create_app` 시그니처 확장(`main.py:101`)은 `analysis_service`를 optional keyword로 받아 기존 `create_app(service)`/`create_app()` 호출에 후방 호환. `_default_service`→`_default_core_sot_service` 리네임에 대한 orphan 참조 없음(`grep` 확인). 게이트웨이 `services/llm_gateway/app/main.py`의 `create_app`은 별개 함수라 영향 없음.

### F4. 회귀 테스트 코드 감사 — PASS (단, 경계 누락은 F6 참조)

테스트 코드는 감사 대상(감사자 아님). 신규 3개 테스트를 읽어 assertion이 계약을 실제로 고정하는지 확인:
- `test_analysis_job_create_get_and_idempotent_replay`(`tests/test_application_api.py:530`): first/replay 의 `idempotent_replay` False/True, 동일 `job.id`, GET 의 `status=="pending"`·`failure_reason is None`를 단언. (a) contract 고정 ✓ (b) under-strict: replay가 새 job을 만들면 fail ✓ (c) over-strict: 정상 동일-projekt GET이 거부되면 fail ✓.
- `test_analysis_candidates_read_back_and_project_isolation`(`tests/test_application_api.py:567`): candidate 수/`id`/`candidate_type`/`status=="needs_review"`/`source_ref_ids`/`payload` 단언 + cross-project GET job·candidates 404 단언. 양방향 guard ✓.
- `test_analysis_job_missing_project_returns_404`(`tests/test_application_api.py:618`): POST·GET job missing-project 404. under-strict: 404 매핑이 사라지면 fail ✓.

### F5. 카운트/빌드 재현 — PASS

- `py_compile` 3파일: OK.
- `python3 -m unittest tests.test_application_api -v` → **Ran 27 tests** OK (worker 주장과 일치).
- `python3 -m unittest discover tests` → **Ran 302 tests** OK (**skipped=35**) (worker 주장과 일치).
- `git diff --check`: clean (exit 0).
- worker가 보고한 숫자를 그대로 믿지 않고 재실행해 동일하게 재도출했다.

### F6. 경계 행렬 — 한 셀 미고정 (conditional)

계약이 명명한 boundary ↔ 회귀 테스트 추적:

| # | 경계(계약) | 기대 | 고정 테스트 | 상태 |
|---|---|---|---|---|
| 1 | POST 신규 job (`idempotent_replay=False`) | 발생 | `...create_get_and_idempotent_replay` | LOCKED |
| 2 | POST replay 동일 job (`True`, 동일 id) | 발생 | 동일 | LOCKED |
| 3 | GET job 상태(`pending`)/`failure_reason` None | 발생 | 동일 | LOCKED |
| 4 | GET candidates 저장 candidate read-back | 발생 | `...read_back_and_project_isolation` | LOCKED |
| 5 | runner/Gateway 시작 안 함 | 미발생 | 구조(import 없음) | LOCKED(구조) |
| 6 | POST missing project → 404 | 발생 | `...missing_project_returns_404` | LOCKED |
| 7 | GET job missing project → 404 | 발생 | 동일 | LOCKED |
| 8 | **GET candidates missing project → 404** | 발생 | — | **미고정** |
| 9 | GET job cross-project → 404 | 발생 | HTTP(`...project_isolation`) + service(`test_transition_enforces_project_isolation`, `test_task_creation_enforces_project_isolation`) | LOCKED(양층) |
| 10 | GET candidates cross-project → 404 | 발생 | HTTP(동일) + service(`test_cross_project_candidate_access_is_not_listed`) | LOCKED(양층) |

추가 — 계약이 명명하지 않았지만 코드가 강제하는 분기:

| # | 분기 | 코드 동작 | 고정 테스트 | 상태 |
|---|---|---|---|---|
| 11 | `_require_job`의 `job is None`(존재 project + 존재 않는 job_id) | `AnalysisNotFound`→404 | — | 미고정(spec-silent) |

## Issues / Risks

- **I1 (conditional, blocking-close 조건)** — #8: "존재하지 않는 project → 404"는 계약이 명명한 boundary이며 3개 엔드포인트 모두에 적용된다. 그러나 GET candidates 엔드포인트에 대한 missing-project 회귀가 없다. shared helper `_require_project_exists`(`main.py:162`)가 GET job(#7)에서 고정돼 있어 helper 자체는 검증됐지만, candidates 핸들러에서 해당 호출 라인을 누군가 제거해도 302개 전체 스위트가 green으로 통과한다(고정이 없으므로). 이것이 빈 셀이며, endpoint별 guard 고정이 없으면 contract-named boundary가 잠기지 않은 것이다. → 합격 조건: `GET /projects/{nope}/analysis/jobs/{any}/candidates` → 404 회귀 1건 추가.
- **I2 (spec-silent, 권고)** — #11: `_require_job`(`service.py:498`)의 `job is None` 분기(존재 project + 존재 않는 job_id → 404)가 어느 층에서도 고정되지 않았다. cross-project 테스트들은 모두 실제 job_id를 쓰므로 `job.project_id != project_id` 분기만 건드린다. 동작은 올바르고 직관적이지만(404), 이 분기를 리팩터링으로 깨도 검출할 테스트가 없다. 계약이 명명하진 않았으므로 차단까진 아니나, 2-direction guard 취지상 보강 권고. → 권고: 존재 project + 존재 않는 job_id GET → 404 회귀 1건.
- **I3 (spec-silent, informational)** — POST `idempotency_key=""`(빈 문자열)는 Pydantic을 통과한 뒤 `create_job`(`service.py:182-183`)이 `AnalysisError`를 던지는데, 이것은 HTTP 핸들러가 잡지 않아 500이 된다. 계약은 빈 idempotency_key의 HTTP 동작을 명명하지 않아 범위 밖이지만, 알아둘 만한 잠재 500. (Pydantic이 field 누락은 422로 막지만 빈 문자열은 허용.)
- **I4 (informational)** — 작업 트리에 변경이 미커밋 상태다. 검증은 working tree 기준이며 commit hash가 없다. 게시 전 커밋 필요.

## Verdict

**조건부 합격 (conditional pass).**

사유(load-bearing):
- 구현은 정확하다 — 3개 엔드포인트, idempotency 기준, "runner 미시작", missing-project/cross-project 404 매핑이 모두 계약과 일치(F1-F3).
- 테스트/빌드/카운트가 독립 재현됐다(F4-F5).
- **그러나** 계약이 명명한 boundary "존재하지 않는 project → 404"의 GET candidates 셀(#8)이 endpoint-specific 회귀로 고정되지 않았다. CLAUDE.md 경계 행렬 규칙에 따라 빈 셀은 합격 조건이며, "future risk/보강 후보"로 재분류하지 않는다.

합격으로 승격 조건: I1 한 건(GET candidates missing-project → 404 회귀)을 추가하면 합격. I2/I3는 권고/informational이라 닫기 조건이 아니다.

## Outstanding items

- 작업 트리 변경 미커밋(I4). 소유자가 커밋/게시 승인해야 verifier가 commit hash 기준으로 재확인 가능.
- I1 회귀 추가 후 본 검증의 conditional 조건 폐쇄 가능. I2/I3는 별도 후순위.
- HANDOFF Next Tasks #2는 이 slice 완료를 반영해 "runner 실행을 API/Worker에서 시작하는 브리프"로 이미 갱신돼 있다 — blocker 없음.

## Reproduction

```bash
cd "/mnt/d/devel/에베베/ai_writte_system"
# 1. diff 검토
git --no-pager diff HEAD -- services/application/app/main.py \
  services/application/app/analysis/service.py tests/test_application_api.py \
  docs/system-contract-sot.md docs/plans/02-analysis-pipeline.md CHANGELOG.md HANDOFF.md
# 2. 컴파일
python3 -m py_compile services/application/app/main.py \
  services/application/app/analysis/service.py tests/test_application_api.py
# 3. 타깃 스위트
python3 -m unittest tests.test_application_api -v   # 기대: Ran 27 tests OK
# 4. 전체 스위트
python3 -m unittest discover tests                  # 기대: Ran 302 tests, skipped=35
# 5. whitespace
git --no-pager diff --check                          # 기대: clean, exit 0
# 6. 미고정 셀(I1) 재확인 — 현재 통과하는 회귀가 없음을 확인
grep -nE "nope|missing" tests/test_application_api.py | grep -i candidate   # 빈 출력 = #8 미고정 확인
```
