# Verification — Phase 2A analysis HTTP API I1/I2 closure (commit 64ec099)

## Subject metadata

- 날짜: 2026-06-30
- 요청자: 사용자 ("커밋하고 다음 작업까지 진행했습니다" — 64ec099 검증)
- 검증자: Claude (독립 감사, 구현 미관여)
- 대상: commit `64ec099` "Add Phase 2A analysis HTTP API" — 직전 조건부 합격의 I1 폐쇄(및 I2 추가 폐쇄)
- 정본 계약 참조: `docs/system-contract-sot.md` v1.6.11, 직전 검증 `docs/verifications/2026-06-30/phase2a_analysis_http_api.md`
- 검증 대상 소스: commit `64ec099` (working tree clean)

## Scope

직전 검증이 "조건부 합격"으로 남긴 I1(GET candidates missing-project → 404 회귀 부재)이 commit에서 폐쇄됐는지, 그리고 추가로 I2(권고)도 처리됐는지만 감사한다. 나머지 구현/계약 일관성은 직전 검증에서 이미 PASS이므로 재검 않는다.

1. I1 회귀가 실제로 추가됐고 계약 boundary를 고정하는지.
2. I2(nonexistent job_id → 404) 회귀 추가 여부와 guard 양방향성.
3. 카운트 재현(28 / 303).
4. 직전 검증 기록이 커밋 중 변조됐는지.

## Methodology

`git show 64ec099`로 신규 회귀 diff 추출 → 테스트 코드 직독 → `python3 -m unittest` 재실행 → `git show 64ec099 -- <verification record>` 로 기록 변조 여부 확인. worker 주장은 복사하지 않고 primary source에서 재도출.

## Findings

### F1. I1 폐쇄 — PASS

`tests/test_application_api.py:619-633` `test_analysis_job_missing_project_returns_404`가 GET candidates 케이스를 추가했다(`:627-629` `client.get("/projects/nope/analysis/jobs/analysis-job-1/candidates")` → `:633` `assertEqual(candidates.status_code, 404)`). 직전 검증의 미고정 셀 #8이 endpoint-specific 회귀로 잠겼다.
- under-strict: candidates 핸들러에서 `_require_project_exists` 호출을 제거하면 이 assert가 fail. ✓
- over-strict: 정상 동일-project candidates 조회는 `test_analysis_candidates_read_back_and_project_isolation`(`:567`)의 `listed.status_code == 200`이 고정. ✓

### F2. I2 추가 폐쇄 — PASS (조건이 아니었던 권고까지 처리)

`tests/test_application_api.py:635-647` `test_analysis_missing_job_under_existing_project_returns_404`가 신규 추가됐다. 존재 project + 존재 않는 job_id(`analysis-job-nope`)로 GET job·candidates → 404. 이것은 `_require_job`(`service.py:498`)의 `job is None` 분기를 최초로 잠근다.
- under-strict: None 검사가 깨지면 `AttributeError`(500) 또는 잘못된 응답 → fail. ✓
- cross-project 분기(`job.project_id != project_id`)는 기존 service/HTTP 테스트가 이미 잠금. ✓
- worker가 닫기 조건(I1)을 넘어 권고(I2)까지 자발적으로 추가했다.

### F3. 카운트 재현 — PASS

- `python3 -m unittest tests.test_application_api` → **Ran 28 tests** OK (27→28, I2 신규 1건).
- `python3 -m unittest discover tests` → **Ran 303 tests** OK (**skipped=35**) (302→303).
- worker 주장(28 / 303)과 정확히 일치.

### F4. 직전 검증 기록 무결성 — PASS

`git show 64ec099 -- docs/verifications/2026-06-30/phase2a_analysis_http_api.md`에 removed line 없음(verbatim 추가). 판정 라인도 "조건부 합격 (conditional pass)" 그대로(`:109`). worker가 직전 판정을 회고적으로 바꾸지 않았다 — 기록은 검증 시점(uncommitted tree) 상태를 정확히 보존한다.

## Issues / Risks

- 없음. I3(빈 idempotency_key → 500)은 직전 검증에서 informational로 기록됐고 이 commit의 범위가 아니며, 계약도 명명하지 않아 여전히 범위 밖이다.

## Verdict

**합격 (pass).** 직전 조건부 합격의 유일한 닫기 조건(I1)이 폐쇄됐고, 추가로 권고 I2까지 잠갔다. Phase 2A analysis HTTP API slice는 이제 무조건 합격.

## Outstanding items

- 없음. 다음 작업은 runner 실행 브리프 승인 → `docs/verifications/2026-06-30/phase2a_runner_execution_brief.md` 참조.

## Reproduction

```bash
cd "/mnt/d/devel/에베베/ai_writte_system"
git --no-pager show 64ec099 -- tests/test_application_api.py   # I1(:627-633) + I2(:635-647) 회귀 확인
python3 -m unittest tests.test_application_api                 # 기대: Ran 28 tests OK
python3 -m unittest discover tests                             # 기대: Ran 303 tests, skipped=35
git --no-pager show 64ec099 -- docs/verifications/2026-06-30/phase2a_analysis_http_api.md | grep '^-'  # 기대: 빈 출력(변조 없음)
```
