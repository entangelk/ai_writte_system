# Analysis write-error and job-state commits verification

## Subject metadata

- Date: 2026-06-29
- Requester: user, asking to verify two committed AI-worker changes
- Verifier: Codex
- Target artifacts:
  - `23d6ef3` (`Re-verify and harden analysis candidate write-error mapping`)
  - `ebbbd14` (`Contract and implement Phase 2A job state transitions (slice 1)`)
- Source of work: `main` at `ebbbd14`, working tree clean at verification start
- Canonical spec scope:
  - `docs/system-contract-sot.md` v1.6.8 lines 37, 315 for candidate write-error mapping
  - `docs/system-contract-sot.md` v1.6.9 lines 36, 316-318 for job lifecycle/failure state
  - `docs/plans/02-analysis-pipeline.md` lines 31-34 for Phase 2A runner/persistence context
  - `docs/plans/02-analysis-job-state-decisions.md` lines 24-72 for approved job-state decisions and slice order

## Scope

1. Candidate write-error classification: duplicate-key code `11000` maps to `DuplicateAnalysisCandidateRequest`; non-duplicate `BulkWriteError`/`PyMongoError` preserves original type; fallback cleanup runs regardless.
2. Job-state contract self-consistency: job-level only, task status absent, allowed transitions, terminal immutability, failure fields.
3. Implementation consistency: service/repository/model literals match the scoped contract.
4. Regression coverage: in-memory/fake tests, live Mongo tests, and committed coverage gaps.
5. Documentation/handoff accuracy for what is done versus next work.

## Methodology

```bash
git status --short
git show --stat --oneline --decorate --no-renames 23d6ef3
git show --stat --oneline --decorate --no-renames ebbbd14
rg -n "v1\.6\.8|v1\.6\.9|duplicate|BulkWriteError|failure_reason|AnalysisJobStatus|pending|running|succeeded|failed|state transition|상태 전이" docs/plans docs/system-contract-sot.md HANDOFF.md CHANGELOG.md
rg -n "BulkWriteError|DuplicateKeyError|duplicate|writeErrors|AnalysisJobStatus|AnalysisJobFailureReason|failure_reason|mark_job|update_job|InvalidJobStateTransition|pending|running|succeeded|failed" services/application/app tests
python3 -m unittest tests.test_analysis_mongo_error_mapping tests.test_analysis_job_state -v
python3 -m unittest discover -s tests
docker run -d --rm --name codex_verify_mongo_27024 -p 27024:27017 mongo:7 --replSet rs0
docker exec codex_verify_mongo_27024 mongosh --quiet --eval "rs.initiate({_id:'rs0',members:[{_id:0,host:'localhost:27017'}]})"
docker exec codex_verify_mongo_27024 mongosh --quiet --eval "rs.status().members.map(m=>m.stateStr).join(',')"
CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27024/?directConnection=true' python3 -m unittest tests.test_analysis_mongo -v
python3 -c "... MongoAnalysisRepository/AnalysisService job-state smoke ..."
docker stop codex_verify_mongo_27024
```

The first host-side Mongo connection attempt inside the sandbox failed with `Operation not permitted`; the live Mongo connection/test commands were rerun with approved escalation. The container was stopped after verification.

## Findings

### F1. Contract scope and internal consistency

Pass. SoT v1.6.8 explicitly narrows write-error mapping to duplicate-key code `11000` and says non-duplicate bulk/driver errors preserve their original type (`docs/system-contract-sot.md:315`). SoT v1.6.9 and the job-state brief consistently define job-only status, no task status, `pending -> running -> succeeded|failed`, terminal immutability, existing-job replay, and the five `failure_reason` literals (`docs/system-contract-sot.md:316-318`, `docs/plans/02-analysis-job-state-decisions.md:24-63`). I did not find an internal spec contradiction in the scoped clauses.

### F2. Commit `23d6ef3` write-error mapping

Pass. The helper only returns true for `DuplicateKeyError` or `BulkWriteError` whose `writeErrors` are all code `11000` (`services/application/app/analysis/mongo_repository.py:31-50`). Transaction and fallback paths map only that helper-positive case to `DuplicateAnalysisCandidateRequest`; fallback cleanup happens before classification (`services/application/app/analysis/mongo_repository.py:227-255`).

The committed fake-based tests cover both directions: duplicate maps in transaction/fallback, non-duplicate `BulkWriteError` is reraised in transaction/fallback, and fallback cleanup is asserted (`tests/test_analysis_mongo_error_mapping.py:108-152`). Focused execution passed: `Ran 14 tests ... OK` when combined with job-state tests. Live Mongo candidate persistence also passed on a throwaway replica set: `tests.test_analysis_mongo` ran 6 tests OK.

### F3. Commit `ebbbd14` job-state implementation

Conditional pass. The core in-memory service behavior matches the approved slice 1 contract:

- Status/failure enums and `AnalysisJob` fields exist (`services/application/app/analysis/models.py:30-53`).
- Allowed transitions are exactly `pending->running`, `running->succeeded`, `running->failed` (`services/application/app/analysis/service.py:50-58`).
- Non-allowed transitions raise `InvalidJobStateTransition`, failed requires an enum reason, and non-failed transitions clear/reject failure fields (`services/application/app/analysis/service.py:198-265`).
- `AnalysisTask` still has no status field (`services/application/app/analysis/models.py:56-62`).

The committed in-memory tests cover creation defaults, legal success/failure paths, pending skip-to-terminal rejection, terminal immutability, running repeat rejection, missing failure reason, and project isolation (`tests/test_analysis_job_state.py:34-143`). Focused execution passed: `Ran 14 tests ... OK`, and full discovery passed: `Ran 285 tests ... OK (skipped=33)`.

### F4. Mongo job-state persistence

Behavior observed, but committed regression missing. The Mongo adapter stores and reconstructs status/failure fields (`services/application/app/analysis/mongo_repository.py:164-165`, `258-286`). A manual live smoke against the throwaway replica set verified `pending->running->failed`, persisted `provider_error` + detail, fresh-service idempotent replay returning the terminal failed job, and terminal re-run rejection: output `mongo job state smoke ok`.

However, the committed live Mongo test file still only checks default/pending job round-trip and job/task/candidate idempotency (`tests/test_analysis_mongo.py:86-219`). There is no committed skip-aware test that calls `mark_job_running`, `mark_job_succeeded`, or `mark_job_failed` through `MongoAnalysisRepository`. This matches HANDOFF Next Tasks saying slice 3 is still pending, but it means the commit-message/work-log claim "live Mongo state-transition persistence and terminal replay verified" is only a manual verification claim, not a durable regression artifact.

### F5. Regression matrix gaps

Blocking for a full pass on `ebbbd14` as a verified slice:

1. The five closed `failure_reason` literals are not all regression-locked. Tests exercise `provider_error`, `snapshot_not_found`, and `source_invalid`, but not `schema_invalid` or `duplicate_conflict` (`tests/test_analysis_job_state.py:56-127`). The model contains all five literals (`services/application/app/analysis/models.py:37-42`), but the boundary matrix has empty cells for two public enum values.
2. Mongo status/failure round-trip and terminal replay are manually smoke-tested, but not committed as a skip-aware regression even though the commit changes `_job_doc`/`_to_job` and `update_job` (`services/application/app/analysis/mongo_repository.py:164-165`, `258-286`).

These are test/verification-lock gaps rather than observed runtime failures. The underlying behavior worked in focused, full, and live smoke runs.

### F6. Runner integration boundary

Accurately recorded as not done. `AnalysisExtractionRunner.run()` creates/reuses a job and proceeds directly to snapshot load/extract/validate/record without any `mark_job_*` calls (`services/application/app/analysis/runner.py:59-103`). `rg` found no job-state transition calls in `runner.py`. HANDOFF correctly states runner integration is slice 2 and current runner-created jobs remain `pending` (`HANDOFF.md:82`, `HANDOFF.md:88`).

## Issues / risks

1. Blocking: `ebbbd14` does not commit regression coverage for every closed `failure_reason` literal. Add a parametrized/looped test that all five enum values can be recorded on a failed job, and that non-enum/string values are rejected if that boundary is intended to stay closed.
2. Blocking: Mongo job-state round-trip and terminal replay need a committed skip-aware live regression. The manual smoke passed, but future workers cannot rerun it through the test suite.
3. Non-blocking reporting risk: Work log/HANDOFF wording says live Mongo job-state persistence was checked, which is true manually, but should not be read as "committed regression exists." HANDOFF already mitigates this by listing slice 3 as next work.

## Verdict

- `23d6ef3`: pass.
- `ebbbd14`: conditional pass. The implemented behavior matches the core slice 1 contract and the manual Mongo smoke passed, but the verification matrix is not fully locked until the failure-reason enum coverage and skip-aware Mongo job-state regression are committed.

## Outstanding items

- No code fixes were made by this verifier.
- Working tree changes after this verification are limited to this verification record and documentation handoff/log updates.
- Recommended next fix before runner slice 2: add the two missing regression locks above so slice 1 does not rely on manual proof.

## Reproduction

```bash
python3 -m unittest tests.test_analysis_mongo_error_mapping tests.test_analysis_job_state -v
python3 -m unittest discover -s tests

docker run -d --rm --name codex_verify_mongo_27024 -p 27024:27017 mongo:7 --replSet rs0
sleep 3
docker exec codex_verify_mongo_27024 mongosh --quiet --eval "rs.initiate({_id:'rs0',members:[{_id:0,host:'localhost:27017'}]})"
sleep 3
CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27024/?directConnection=true' python3 -m unittest tests.test_analysis_mongo -v
# Then run the short MongoAnalysisRepository/AnalysisService job-state smoke from Methodology if checking the manual claim.
docker stop codex_verify_mongo_27024
```
