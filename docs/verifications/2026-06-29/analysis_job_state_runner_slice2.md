# Phase 2A job-state runner integration verification

## Subject metadata

- Date: 2026-06-29
- Requester: user, asking to verify committed AI-worker work thoroughly, including non-blocking concerns
- Verifier: Codex
- Target slice/artifact: commit `bffd850` (`Integrate job state transitions into the runner (slice 2)`)
- Source of work: `main` at `bffd850`, working tree clean at verification start
- Canonical spec scope:
  - `docs/plans/02-analysis-job-state-decisions.md:24-72`
  - `docs/system-contract-sot.md:316-318`
  - `docs/plans/02-analysis-pipeline.md:31-34`
  - Prior verification conditions from `docs/verifications/2026-06-29/analysis_write_error_and_job_state_commits.md:88-97`

## Scope

1. Slice 1/3 closure claims: `failure_reason` enum coverage and Mongo job-state round-trip/terminal replay regression.
2. Slice 2 runner lifecycle: new job only executes, `pending -> running -> terminal`, replay does not re-run.
3. Failure mapping: each approved failure point maps to the closed `failure_reason` enum and does not write candidates.
4. Layering: runner depends on repository boundary for duplicate conflicts, not the Mongo adapter.
5. Verification execution: focused, full discovery, live Mongo repository tests, live runner smoke.

## Methodology

```bash
git status --short
git show --stat --oneline --decorate --no-renames bffd850
git diff --name-only bffd850^ bffd850
rg -n "job 상태|pending|running|succeeded|failed|failure_reason|snapshot_not_found|source_invalid|schema_invalid|provider_error|duplicate_conflict|InvalidCandidateSource|DuplicateAnalysisCandidateRequest|mark_job|runner" docs/plans docs/system-contract-sot.md HANDOFF.md CHANGELOG.md docs/daily_logs/2026-06-29/work_log.md services/application/app tests
python3 -m py_compile services/application/app/analysis/runner.py services/application/app/analysis/service.py services/application/app/analysis/repository.py services/application/app/analysis/mongo_repository.py tests/test_analysis_runner.py tests/test_analysis_job_state.py tests/test_analysis_mongo.py
python3 -m unittest tests.test_analysis_runner tests.test_analysis_job_state tests.test_analysis_mongo tests.test_analysis_mongo_error_mapping -v
python3 -m unittest discover -s tests
docker run -d --rm --name codex_verify_mongo_27026 -p 27026:27017 mongo:7 --replSet rs0
docker exec codex_verify_mongo_27026 mongosh --quiet --eval "rs.initiate({_id:'rs0',members:[{_id:0,host:'localhost:27017'}]})"
docker exec codex_verify_mongo_27026 mongosh --quiet --eval "rs.status().members.map(m=>m.stateStr).join(',')"
CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27026/?directConnection=true' python3 -m unittest tests.test_analysis_mongo -v
python3 -c "... live MongoAnalysisRepository + AnalysisExtractionRunner succeeded/snapshot_not_found smoke ..."
docker stop codex_verify_mongo_27026
```

Host Python access to the throwaway Mongo port required approved escalation because sandboxed localhost TCP access returned network restrictions in earlier live checks. The container was stopped after verification.

## Findings

### F1. Slice 1/3 closure claims are substantively closed

Pass. The prior verification required two durable locks before treating slice 1 as fully verified:

- Every closed `failure_reason` literal is now covered by `test_every_failure_reason_literal_round_trips`, including `schema_invalid` and `duplicate_conflict`; raw string reasons are rejected by `test_non_enum_failure_reason_is_rejected` (`tests/test_analysis_job_state.py:145-175`).
- Mongo job-state round-trip and terminal replay are now committed in `test_job_state_round_trips_and_terminal_replay` and run in fallback/transaction classes when live Mongo is available (`tests/test_analysis_mongo.py:176-217`).

Live Mongo execution against a throwaway replica set ran 8 tests OK, including both fallback and transaction versions of the job-state round-trip test.

### F2. Runner implements the new-job lifecycle

Pass. For a non-replay job, the runner creates the job, marks it running, loads the snapshot, extracts, preflights, records candidates, then marks the job succeeded and returns the succeeded job (`services/application/app/analysis/runner.py:78-146`). The success regression asserts returned and persisted `succeeded` status with no failure reason (`tests/test_analysis_runner.py:243-272`).

Focused execution passed: `tests.test_analysis_runner` contributes 13 passing runner tests. Full discovery passed: `Ran 296 tests ... OK (skipped=35)`.

### F3. Replay avoids re-extraction for succeeded jobs

Pass for the covered state. Existing jobs are detected via `create_job(...).idempotent_replay`; runner immediately returns `list_candidates` without loading/extracting again (`services/application/app/analysis/runner.py:83-94`). The regression uses a counting extractor and asserts one extractor call across initial run + replay (`tests/test_analysis_runner.py:274-309`).

### F4. Failure mapping implementation matches the declared mapping

Implementation pass. `_failure_reason()` maps `NotFound`, `AnalysisExtractionError`, `InvalidCandidateSource`, base `InvalidAnalysisCandidate`, `DuplicateAnalysisCandidateRequest`, and fallback `Exception` to the intended enum values, with ordering that keeps `InvalidCandidateSource` distinct from its base class (`services/application/app/analysis/runner.py:148-162`). The runner marks the job failed with `failure_detail=str(exc)` and re-raises (`services/application/app/analysis/runner.py:127-134`).

Committed tests cover `snapshot_not_found`, malformed-provider `schema_invalid`, source-anchor `source_invalid`, provider exception `provider_error`, and storage duplicate `duplicate_conflict`, asserting failed status/reason and zero candidates (`tests/test_analysis_runner.py:311-413`). The source/schema split is load-bearing because source validation now raises `InvalidCandidateSource` (`services/application/app/analysis/service.py:46-47`, `542-563`).

### F5. Layering change is correct

Pass. `DuplicateAnalysisCandidateRequest` now lives in the repository boundary (`services/application/app/analysis/repository.py:16-21`), runner imports it from there (`services/application/app/analysis/runner.py:20-22`), and Mongo imports/re-raises that same type (`services/application/app/analysis/mongo_repository.py:29-31`, `234-254`). Existing tests that import from `mongo_repository` still work because the imported class remains module-visible.

### F6. Live runner smoke reproduced

Pass. A throwaway Mongo replica set on port 27026 was used to run a live runner smoke with Mongo analysis persistence and in-memory Core SOT source loading:

- Successful runner invocation persisted a `succeeded` job and one candidate.
- Missing snapshot invocation re-raised `NotFound` and persisted a `failed` job with `failure_reason == snapshot_not_found`.

Smoke output: `live runner smoke ok`.

## Issues / risks

1. **[Blocking for full verification] Existing-job replay is only tested for a `succeeded` job.**  
   The contract says `find_job_request` returning an existing job, "state regardless", is replayed and never re-run (`docs/system-contract-sot.md:317`, `docs/plans/02-analysis-job-state-decisions.md:42-47`). The committed runner test covers succeeded replay (`tests/test_analysis_runner.py:274-309`) but not `failed`, `pending`, or `running` existing jobs. The implementation currently handles all states correctly via the early replay branch, but the boundary matrix has empty state cells.

2. **[Blocking for full verification] Base `InvalidAnalysisCandidate -> schema_invalid` is not directly reason-locked.**  
   `_failure_reason()` has a branch for base `InvalidAnalysisCandidate` (`services/application/app/analysis/runner.py:158-159`), and the work summary explicitly claims this mapping. Existing reason tests cover `AnalysisExtractionError -> schema_invalid` (`tests/test_analysis_runner.py:318-332`) and source subclass mapping, but they do not assert that a base validation failure such as empty `logical_key` produces a failed job with `schema_invalid`. Older preflight tests assert the exception and zero candidates (`tests/test_analysis_runner.py:212-241`) but not the stored reason. Removing or changing the base branch could escape the named failure-reason matrix.

3. **[Non-blocking] Failure detail from the runner is not asserted.**  
   The runner writes `failure_detail=str(exc)` (`services/application/app/analysis/runner.py:128-133`), and lower-level state tests prove details can persist (`tests/test_analysis_job_state.py:56-76`). No runner failure test asserts that detail is populated or useful. Because the spec says detail is free-text and does not require a format (`docs/plans/02-analysis-job-state-decisions.md:61`), this is a completeness risk rather than a contract failure.

4. **[Non-blocking] "Original exception re-thrown" is unevenly locked.**  
   Provider and duplicate paths assert exact exception classes (`tests/test_analysis_runner.py:345-382`), and older preflight tests assert `InvalidAnalysisCandidate` for validation failures. The shared `_assert_failed_reason` helper defaults to `expected_exc=Exception` (`tests/test_analysis_runner.py:384-408`), so snapshot-not-found and malformed-provider exact rethrow are not as tightly locked as the work summary claims. The implementation is correct; the regression is just looser than the prose.

5. **[Non-blocking] Failed validation can leave task setup behind.**  
   The contract and comments define candidate persistence as all-or-nothing, and task creation is idempotent setup (`docs/plans/02-analysis-job-state-decisions.md:10`, `services/application/app/analysis/runner.py:117-119`). A failure after `_prepare_draft()` may leave tasks while writing zero candidates. This appears contract-compatible, but future readers may misread "job 단위 all-or-nothing" as "no job/task side effects"; the current docs mostly clarify candidate all-or-nothing.

## Verdict

**Conditional pass.** The implementation behavior matches the approved design in the inspected paths, focused/full/live verification passed, and the prior slice 1/3 blockers are closed. I would not mark the slice fully verified until the two blocking regression gaps above are committed:

1. Runner replay tests for existing non-succeeded states, at minimum `failed` and preferably stale `pending`/`running` since the contract says state-agnostic replay.
2. A runner failure test where a base `InvalidAnalysisCandidate` validation failure stores `failure_reason == schema_invalid`.

## Outstanding items

- No code fixes were made by this verifier.
- Working tree changes after this verification are this verification record plus work log/HANDOFF updates.
- The throwaway Mongo container `codex_verify_mongo_27026` was stopped.

## Reproduction

```bash
python3 -m py_compile services/application/app/analysis/runner.py services/application/app/analysis/service.py services/application/app/analysis/repository.py services/application/app/analysis/mongo_repository.py tests/test_analysis_runner.py tests/test_analysis_job_state.py tests/test_analysis_mongo.py
python3 -m unittest tests.test_analysis_runner tests.test_analysis_job_state tests.test_analysis_mongo tests.test_analysis_mongo_error_mapping -v
python3 -m unittest discover -s tests

docker run -d --rm --name codex_verify_mongo_27026 -p 27026:27017 mongo:7 --replSet rs0
sleep 3
docker exec codex_verify_mongo_27026 mongosh --quiet --eval "rs.initiate({_id:'rs0',members:[{_id:0,host:'localhost:27017'}]})"
sleep 3
CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27026/?directConnection=true' python3 -m unittest tests.test_analysis_mongo -v
# Optional: rerun the live runner smoke described in Methodology.
docker stop codex_verify_mongo_27026
```
