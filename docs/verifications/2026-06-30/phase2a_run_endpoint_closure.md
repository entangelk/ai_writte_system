# Phase 2A run endpoint — F4/F5/F6 폐쇄 재검증

## Subject metadata

- 검증일: 2026-06-30
- 요청자: entangelk(사용자, "다음작업 검증해줘. 완료했습니다." — 2개 커밋 중 `4f8182a`)
- 검증자: Claude(독립 검증)
- 검증 대상 slice/artifact: commit `4f8182a` "Implement Phase 2A analysis run endpoint" — 선행 조건부합격 `docs/verifications/2026-06-30/phase2a_run_endpoint.md`의 F4/F5/F6 폐쇄분(신규 회귀 + 계약 보강)
- 정본 계약 참조:
  - `docs/system-contract-sot.md` v1.6.12(changelog `docs/system-contract-sot.md:37`, run endpoint 단락 `docs/system-contract-sot.md:324`; 줄번호는 HEAD=d4c2438 기준, v1.6.13 삽입으로 +1)
  - `docs/plans/02-analysis-runner-execution-decisions.md` §5(승인 결정)
  - `docs/plans/02-analysis-pipeline.md`(surface 4종 + snapshot_not_found 404)
- 검증 대상 작업 출처: commit `4f8182a`(HEAD). worktree clean.

## Scope

1. **F4 폐쇄**: run endpoint HTTP mapping `duplicate_conflict→409`·`provider/기타→502` 회귀 추가 여부 + 양방향 lock.
2. **F5 폐쇄**: `snapshot_not_found→404` 회귀 추가 + 계약(SoT/decision brief/pipeline) 명시 여부.
3. **F6 폐쇄**: `run_job` non-pending replay 회귀 + failed-job HTTP replay 회귀 추가 여부.
4. **boundary matrix 완결성**: run endpoint HTTP mapping 6 branch(404×2 / 400 / 409 / 502 / 503)가 모두 named regression에 대응하는지.
5. **재실행**: focused suite + discover.

## Methodology

1. `git show 4f8182a -- tests/ services/ docs/`로 클로저 변경분을 읽고, 원 conditional-pass 기록의 F4/F5/F6 각 조건과 대조.
2. 각 신규 회귀가 (a) 계약 literal을 실제 pin 하는지, (b) double가 아니라 `main.py` except 절을 실제로 exercise 하는지 확인.
3. boundary matrix를 새로 작성해 6 branch 전부 named test에 대응하는지 추적.
4. 계약 보강이 3 문서(SoT, decision brief, pipeline)에서 동일 literal로 일치하는지 교차 확인.
5. 재실행(검증자 직접): `py_compile`, `tests.test_application_api tests.test_analysis_runner`, `unittest discover tests`.

## Findings

### F0. 재실행 — 작업자 주장과 일치

- `tests.test_application_api tests.test_analysis_runner`: **54 passed**(50→+4). 
- `unittest discover tests`: **314 passed, skipped=35**(309→+4 run-endpoint 클로저 + d4c2438의 +1 벤치마크 = 314).
- 신규 매핑 테스트 3종 + `run_job` replay 1종 모두 `ok`.

### F1. [F4 해소] 409·502 HTTP mapping 회귀 추가 — main.py except 절을 실제 exercise

신규 double 2종이 `main.py`의 미추적 except 절을 직접 hit 한다:

| branch | double(`tests/test_application_api.py`) | assertion | except 절 |
|---|---|---|---|
| `duplicate_conflict→409` | `_ApiDuplicateConflictRunner`가 `DuplicateAnalysisCandidateRequest` raise | `failed.status_code==409`, `failure_reason==duplicate_conflict` | `main.py:440-441` |
| `provider/기타→502` | `_ApiProviderErrorRunner`가 `RuntimeError` raise | `failed.status_code==502`, `failure_reason==provider_error` | `main.py:450-451` |

HTTP status는 double이 아니라 `main.py` except 절에서 결정된다(double은 `mark_job_failed`+raise만). 따라서 `:440`의 `409→400`·`:451`의 `502→500` 변이 시 해당 테스트가 붉어진다. under-strict lock 확인. 원 F4의 "empty cell" 2개 모두 채워졌다.

### F2. [F5 해소] snapshot_not_found→404 회귀 + 3문서 계약 명시

- **회귀**: `_ApiSnapshotNotFoundRunner`가 `NotFound` raise → `test_analysis_run_endpoint_maps_snapshot_not_found_to_404`가 `failed.status_code==404`, `failure_reason==snapshot_not_found`를 lock. `main.py:438` `except (AnalysisNotFound, NotFound)→404` 경로 실제 exercise.
- **계약 보강(3문서 동일 literal)**:
  - SoT changelog `:37` 및 run endpoint 단락 `:324`: "missing/cross-project 및 `snapshot_not_found`는 404".
  - decision brief §5: "missing/cross-project와 `snapshot_not_found`는 404".
  - pipeline plan: "cross-project job/candidate/run 접근 및 `snapshot_not_found`는 404".
- spec-silent-but-code-enforced gap 폐쇄. 코드의 de-facto 404가 계약에 명시됐다.

### F3. [F6 해소] run_job non-pending replay + failed-job HTTP replay 회귀 추가

- **runner-level**: `test_runner_run_job_replays_existing_non_pending_job`(`tests/test_analysis_runner.py`)가 succeeded job으로 `run_job` 호출 → `extractor.calls==0`, `job_idempotent_replay==True`, candidate 0건을 lock. `runner.py:106-115` non-pending replay 분기를 직접 hit(원 F6의 "HTTP short-circuit로 도달 불가" 분기 직접 회귀화).
- **HTTP-level failed replay**: 기존 `test_analysis_run_endpoint_replays_terminal_and_running_without_runner`가 `failed` job 케이스로 확장돼 `failed_replay.status_code==200`, `idempotent_replay==True`, `status==failed`, `failure_reason==provider_error`를 lock. 원 F6의 "failed replay 미cover" 해소.

### F4(boundary). run endpoint HTTP mapping 6 branch 전부 named regression에 대응 — matrix 완결

| branch | contract | named regression |
|---|---|---|
| 404 missing/cross-project | ✓ | `test_analysis_run_endpoint_missing_and_cross_project_returns_404` |
| 404 snapshot_not_found | ✓ | `test_analysis_run_endpoint_maps_snapshot_not_found_to_404` |
| 400 schema/source invalid | ✓ | `test_analysis_run_endpoint_preserves_failed_job_on_runner_error` |
| 409 duplicate_conflict | ✓ | `test_analysis_run_endpoint_maps_duplicate_conflict_to_409` |
| 502 provider/기타 | ✓ | `test_analysis_run_endpoint_maps_provider_exception_to_502` |
| 503 runner 미구성 | ✓ | `test_analysis_run_endpoint_pending_without_runner_returns_503` |

빈 cell 없음. 원 conditional-pass의 load-bearing 조건(F4·F5)과 권고(F6) 전부 폐쇄.

### F5(프로세스). 원 검증 기록 verbatim 보존 — 자의적 pass 전환 없음

커밋된 `docs/verifications/2026-06-30/phase2a_run_endpoint.md`는 선행 검증자(본인)의 **conditional-pass 원문 그대로**(`조건부 합격` 판정 유지). 작업자가 이를 임의로 `합격`으로 고쳐쓰지 않았다. 폐쇄는 별도 검증(본 기록)으로 독립 확인한다. 감사 추적 적정.

## Issues / Risks

- 신규 double들이 `mark_job_failed`를 raise 전에 직접 호출한다. 이는 실제 runner(`_execute_pending_job`의 except→mark_job_failed→reraise) 흐름을 시뮬레이션한 것이며, failure_reason↔exception 매핑 자체는 runner slice 2(16종)에서 이미 lock돼 있으므로 중복/순환 우려 없음. HTTP status 매핑만이 본 클로저의 검증 대상이고 그것은 `main.py` 실제 코드로 결정된다.
- runtime wiring(provider/Gateway runner factory)은 여전 제외. 계약상 out-of-scope이므로 결함 아님.

## Verdict

**합격(pass)** — 원 conditional-pass `phase2a_run_endpoint.md`의 load-bearing 조건 F4(409·502 회귀)·F5(snapshot_not_found 회귀+3문서 계약 명시)와 권고 F6(run_job replay·failed HTTP replay)가 모두 폐쇄됐고, run endpoint HTTP mapping 6 branch에 빈 cell 없이 named regression이 대응하며, 재실행(54/314)이 일치한다. 원 검증 기록은 verbatim 보존돼 감사 추적이 적정하다.

## Outstanding items

- 없음(본 slice 한정). runtime wiring은 후속 slice로 남음(HANDOFF Next Tasks).
- 본 기록과 원 `phase2a_run_endpoint.md`는 함께 읽어야 한다(원문 = 조건부합격 근거, 본문 = 폐쇄 확인).

## Reproduction

```bash
git show 4f8182a -- tests/test_application_api.py tests/test_analysis_runner.py
python3 -m unittest tests.test_application_api tests.test_analysis_runner   # 54 passed
python3 -m unittest discover tests                                         # 314, skip 35
# boundary matrix 빈 cell 재확인
grep -nE "status_code, (409|502|404)" tests/test_application_api.py
```
