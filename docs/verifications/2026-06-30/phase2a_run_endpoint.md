# Phase 2A analysis run endpoint 독립 검증

## Subject metadata

- 검증일: 2026-06-30
- 요청자: entangelk(사용자, "클로드 작업 AI가 작업한 분 확인해서 검증하고 의심하고 또 의심해줘")
- 검증자: Claude(독립 검증)
- 검증 대상 slice/artifact: Phase 2A analysis run endpoint — `POST /projects/{project_id}/analysis/jobs/{job_id}/run` + `AnalysisExtractionRunner.run_job()` + `create_app(analysis_runner=...)` 주입
- 정본 계약 참조:
  - `docs/system-contract-sot.md` v1.6.12(changelog `docs/system-contract-sot.md:36`, run endpoint 계약 단락 `docs/system-contract-sot.md:323`)
  - `docs/plans/02-analysis-runner-execution-decisions.md`(승인 결정 §1–§6, 특히 §5 envelope/HTTP mapping)
  - `docs/plans/02-analysis-pipeline.md`(Application API surface 4종)
- 검증 대상 작업 출처: **working tree, uncommitted**(HEAD `0727edb` 기준 미커밋 변경분). 커밋된 Phase 2A HTTP read API(`64ec099`)/decision brief(`54df31e`,`0727edb`)는 본 검증의 범위가 아니다.

## Scope

1. **정본 계약(run endpoint)**: SoT v1.6.12 run endpoint 단락 + decision brief §1–§6 + pipeline plan의 HTTP surface 확장.
2. **구현 코드**: `services/application/app/main.py`의 `AnalysisJobRunner` Protocol·`create_app(analysis_runner=...)`·`run_analysis_job` 엔드포인트·`_analysis_run_payload`; `services/application/app/analysis/runner.py`의 `run_job`·`_execute_pending_job`·`_failure_reason`.
3. **회귀 테스트**: `tests/test_application_api.py`(run endpoint 5종 + fake/failing runner double), `tests/test_analysis_runner.py`(`run_job` 1종).
4. **공개 envelope/schema**: run response `{job, candidates, idempotent_replay}` 및 job/candidate payload literal이 기존 read API와 동일한지.
5. **전체 suite**: `python3 -m unittest discover tests`.

## Methodology

1. `git diff HEAD -- services/.../main.py services/.../runner.py`로 구현 변경분을 읽고 `runner.py` 전체로 failure mapping 컨텍스트 확보.
2. `git diff HEAD -- docs/system-contract-sot.md docs/plans/02-analysis-*.md CHANGELOG.md HANDOFF.md`로 계약 변경분을 읽고 **경계 matrix**를 계약에서 추출.
3. 계약 self-consistency: SoT changelog/단락, decision brief §5/승인요약, HANDOFF, CHANGELOG가 동일 HTTP mapping literal을 쓰는지 교차 확인.
4. 구현 ↔ 계약 literal 일치: 5개 HTTP status(404/400/409/502/503)가 `main.py` except 절에 그대로 있는지.
5. boundary matrix → 회귀 테스트 trace: 각 "should fire"/"should NOT fire" 분기가 어느 테스트 함수에 대응하는지 `grep`으로 추적.
6. 테스트 코드 자체 감사: 각 run-endpoint 테스트가 (a) 계약을 실제로 pin 하는지, (b) under-strict/over-strict 양방향 guard가 있는지.
7. 재실행(검증자 직접):
   - `python3 -m py_compile services/application/app/main.py services/application/app/analysis/runner.py tests/test_application_api.py tests/test_analysis_runner.py`
   - `python3 -m unittest tests.test_application_api tests.test_analysis_runner`
   - `python3 -m unittest discover tests`

## Findings

### F0. 테스트/컴파일 재실행 — 작업 로그 주장과 일치

- `py_compile`: 4 파일 `PY_COMPILE_OK`.
- `tests.test_application_api tests.test_analysis_runner`: **50 passed**(0.985s). 작업 로그의 "50개 통과" 일치.
- `unittest discover tests`: **Ran 309 tests, OK (skipped=35)**(1.427s). "309개 통과, 35 skip" 일치.
- green bar 자체는 재현됐으나, green bar ≠ 계약 검증(아래 F1/F2 참조).

### F1. 구현 ↔ 계약 literal 일치 — HTTP mapping 5종 모두 정확히 부합

`main.py:run_analysis_job`(`services/application/app/main.py:412-452`)의 except 절은 계약(SoT `:323`, decision brief §5)과 정확히 일치한다:

| 계약(SoT v1.6.12 / brief §5) | 구현(`main.py`) | 일치 |
|---|---|---|
| missing/cross-project → 404 | `:438-439` `except (AnalysisNotFound, NotFound) → 404` | ✓ |
| pending + runner 미구성 → 503 | `:429-433` `raise HTTPException(503, ...)` + `:448-449` `except HTTPException: raise`(503이 502로 뭉개지지 않음) | ✓ |
| schema_invalid/source_invalid → 400 | `:442-447` `except (AnalysisExtractionError, InvalidCandidateSource, InvalidAnalysisCandidate) → 400` | ✓ |
| duplicate_conflict → 409 | `:440-441` `except DuplicateAnalysisCandidateRequest → 409` | ✓ |
| provider/기타 → 502 | `:450-451` `except Exception → 502` | ✓ |

runner failure_reason mapping(`runner.py:176-190`)과 main.py HTTP mapping은 **양측 일관적**이다(예: `InvalidAnalysisCandidate`→runner `schema_invalid`→HTTP 400; `DuplicateAnalysisCandidateRequest`→runner `duplicate_conflict`→HTTP 409). 계약 내부 불일치(blocking)는 없다. 단, snapshot_not_found는 F2 참조.

### F2. 응답 envelope — 기존 read API와 동일 literal 재사용

`_analysis_run_payload`(`main.py:180-190`)는 `_analysis_job_payload`/`_analysis_candidate_payload`(read API가 쓰는 동일 helper)를 재사용한다. decision brief §5 point 1("job/candidate payload가 기존 read API와 동일 literal") 충족. 테스트 `test_analysis_run_endpoint_executes_pending_job_with_injected_runner`(`tests/test_application_api.py:669`)가 `candidate_type=="character_observation"` + candidate id가 `GET .../candidates` 결과와 일치함을 lock.

### F3. 핵심 동작 분기 — pending 실행 / non-pending replay / runner 호출 양방향 guard 충실

- **should fire(pending 실행)**: `tests/test_application_api.py:669`가 pending job + injected runner → 200, `idempotent_replay=false`, `status=succeeded`, candidate 1건, 그리고 `runner.calls == [job_id]`로 runner 실제 호출을 lock.
- **should NOT fire(non-pending 비재실행, over-strict guard)**: `tests/test_application_api.py:712-715`는 runner를 **주입하지 않은 채** succeeded/running job을 run → 200 + `idempotent_replay=true`. runner를 잘못 호출했다면 `analysis_runner is None` 분기(`main.py:429`)에서 503이 됐을 것. 200이 나왔다는 것 자체가 non-pending 시 runner 미호출을 증명. 양방향 guard 충실.
- **failed job GET 가시성**: `tests/test_application_api.py:768`가 runner 실패 후 `GET`으로 `status=failed`, `failure_reason=schema_invalid`를 확인. SoT `:323` "실패 job은 이후 GET으로 조회 가능해야 한다" lock.
- **runner-level run_job**: `tests/test_analysis_runner.py:515-539`가 `run_job(pending)` → extractor 1회 호출, `idempotent_replay=false`, `succeeded`, candidate 1건 저장을 lock.

### F4. [Issue] HTTP failure mapping 409(duplicate_conflict)·502(provider/기타)의 run-endpoint 회귀 부재 — 미추적 branch

계약(SoT `:323`, decision brief §5, HANDOFF)은 run endpoint의 실패 HTTP mapping으로 **409와 502를 명시적으로 lock**한다. 그러나:

- `tests/test_application_api.py` 전체에 `502`라는 literal이 **한 건도 없다**(`grep "502"` → 없음).
- `main.py:440-441`의 `except DuplicateAnalysisCandidateRequest → 409` 절을 exercise하는 run-endpoint 테스트가 없다(duplicate는 project rename/archive 409 문맥에서만 등장하며 run endpoint와 무관).
- 테스트용 runner double `_ApiFakeAnalysisRunner`/`_ApiFailingAnalysisRunner` 중 어느 것도 `DuplicateAnalysisCandidateRequest`나 일반 `Exception`을 발생시키지 않는다(`_ApiFailingAnalysisRunner`는 `InvalidAnalysisCandidate`→400만).

즉 boundary matrix의 두 cell이 비어 있다: `duplicate_conflict→409`와 `provider/기타→502`. 이 두 except 절은 서로 다른 status code를 가진 별개 clause이므로, 인접 400 테스트 하나로는 커버되지 않는다. 누군가 `:440`의 `409`를 `400`으로, 또는 `:451`의 `502`를 `500`으로 바꿔도 어떤 테스트도 붉어지지 않는다. **계약에 명시된 failure mapping branch가 named regression에 대응하지 않으므로, green bar와 무관하게 untraced branch**다.

### F5. [Issue / contract gap] snapshot_not_found → HTTP 404가 code-enforced인데 계약이 침묵

5개 `failure_reason`(`snapshot_not_found`, `source_invalid`, `schema_invalid`, `provider_error`, `duplicate_conflict`) 중 계약은 source/schema→400, duplicate→409, provider/기타→502, missing/cross→404, runner 미구성→503를 명시하지만 **`snapshot_not_found`의 HTTP status는 어디에도 명시하지 않는다**(SoT `:36`/`:323`, decision brief §5 모두 침묵).

그런데 코드는: runner `_failure_reason`이 `NotFound → snapshot_not_found`(`runner.py:180-181`)로 매핑하고 `mark_job_failed` 후 원본 `NotFound`를 재throw; `main.py:438`의 `except (AnalysisNotFound, NotFound)`가 이 `NotFound`를 잡아 **404**로 표면화한다. 즉 de-facto `snapshot_not_found → 404`다.

이 경로는 도달 가능하다: `service.create_job`(`service.py:179-196`)은 snapshot 존재를 검증하지 않고 `snapshot_id`만 저장하므로, 존재하지 않는 snapshot을 가리키는 job을 run하면 `load_snapshot`이 `NotFound`를 던진다. "spec-silent-but-code-enforced"에 해당 — 계약이 404(또는 다른 code)를 명시하지 않은 채 코드가 매핑을 결정하고 있다. 404가 의미상 합리적이긴 하나, 계약이 run endpoint 실패 mapping을 failure_reason별로 명시적으로 열거하면서 이 한 값만 빠져 있으므로 contract gap이다.

### F6. [minor / non-blocking] run_job non-pending replay 분기와 failed-job HTTP replay가 직접 회귀에 없다

- `run_job`(`runner.py:106-115`)은 자체 non-pending replay 분기를 갖지만, HTTP layer(`main.py:417`)가 non-pending을 `run_job` 호출 전에 short-circuit하므로 HTTP 경로로는 도달 불가. runner-level에서 `run_job` non-pending replay를 직접 hit하는 테스트가 없다(`tests/test_analysis_runner.py:515`는 pending만). decision brief가 `run_job`의 non-pending replay를 계약 surface로 명시하므로, 직접 caller(예: 향후 worker) 관점에서는 lock이 비어 있다.
- HTTP replay 테스트(`:712-715`)는 succeeded/running만 cover하고 failed replay를 직접 cover하지 않는다(failed GET 가시성은 F3에서 별도 cover).

## Issues / Risks

- **[차단 후보] F4**: 계약이 lock한 run-endpoint HTTP mapping 중 `409`·`502` 두 branch에 named regression이 없다. boundary matrix "empty cell = blocking" 규칙에 비추어, green bar와 무관하게 untraced branch다.
- **[차단 후보] F5**: `snapshot_not_found` HTTP mapping이 계약에 명시되지 않은 채 코드가 404로 결정한다(spec-silent-but-code-enforced). 슬라이스 폐쇄 전 계약 보강(404 명시, 또는 의도한 다른 code로 정정 + 회귀)이 필요하다.
- **[비차단] F6**: `run_job` non-pending replay·failed-job HTTP replay의 직접 회귀 부재. 동작은 올바르고 다른 경로로 간접 cover되나, 공개 surface로서 직접 lock이 비어 있다.
- **[정보] runtime wiring 의도적 제외**: 실제 provider/Gateway runner factory가 아직 wiring되지 않아 기본 runtime에서 `analysis_runner=None` → pending run은 503. 이는 계약(SoT `:323`, decision brief §4/§6)이 명시한 out-of-scope이므로 결함이 아니다. 다음 작업자가 Gateway JSON output/prompt 계약과 source_ref 생성 boundary 확정 후 별도 slice로 구현한다(HANDOFF Next Tasks #2).

## Verdict

**조건부 합격(conditional pass)** — 구현 자체는 계약 literal과 정확히 부합하고(F1), envelope/동작 양방향 guard/failed GET 가시성/테스트 카운트가 모두 확인됐다(F2/F3/F0). 그러나 load-bearing 조건 2건이 미충족:

1. **F4 해소**: run endpoint에서 `duplicate_conflict → 409`와 `provider/기타 → 502`를 각각 exercise하는 회귀 테스트 추가(각각 `DuplicateAnalysisCandidateRequest`, 일반 `Exception`을 발생시키는 runner double 필요). 두 except 절은 별개 status code이므로 개별 lock이 필요.
2. **F5 해소**: `snapshot_not_found` HTTP mapping을 계약(SoT v1.6.12 run endpoint 단락 + decision brief §5)에 명시(현재 코드의 404를 계약에 반영하거나, 의도가 다르면 code를 정정하고 회귀 추가). 

위 두 조건이 닫히기 전까지는 합격으로 닫을 수 없다. F6은 권고(비차단).

## Outstanding items

- 작업 출처는 **미커밋**(working tree). HEAD `0727edb`. 커밋/게시는 소유자 결정.
- 본 검증은 verifier가 결함을 **조용히 고치지 않았음**(F4/F5 회귀·계약 보강은 소유자에게 회부). 
- F4/F5가 동일 작업자에 의해 같은 슬라이스에서 폐쇄되는 것이 자연스럽다(run endpoint slice의 범위 안).
- 게시 전 SoT v1.6.12 minor 번전에 F5 보강분이 반영되면 changelog/SoT version log 재정렬 고려.

## Reproduction

```bash
# 1. 계약/구현 변경분 확인
git diff HEAD -- services/application/app/main.py services/application/app/analysis/runner.py
git diff HEAD -- docs/system-contract-sot.md docs/plans/02-analysis-runner-execution-decisions.md docs/plans/02-analysis-pipeline.md

# 2. 컴파일 + focused suite + 전체 suite
python3 -m py_compile services/application/app/main.py services/application/app/analysis/runner.py tests/test_application_api.py tests/test_analysis_runner.py
python3 -m unittest tests.test_application_api tests.test_analysis_runner
python3 -m unittest discover tests

# 3. F4 빈 cell 확인(404/400/503은 hit, 409/502는 run endpoint에서 미hit)
grep -nE "502" tests/test_application_api.py                       # → 없음
grep -nE "status_code, 409|DuplicateAnalysis" tests/test_application_api.py  # → run endpoint 문맥 아님
grep -nE "status_code, (200|400|404|503)" tests/test_application_api.py      # → 400/503/404/200 만
```
