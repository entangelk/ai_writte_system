# Verification — Phase 5.10 Writing loop aggregate token/wall-clock budget (B2 increment)

## Subject metadata

- **Date**: 2026-07-13
- **Requester**: entangelk (owner) — "작업 AI 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?"
- **Verifier**: Claude (independent verification session)
- **Target slice/artifact**: Writing loop aggregate token/wall-clock budget — `metering.py` (`MeteredCallError`/`add_usage`/`EMPTY_USAGE`), four `*_metered` collaborator variants (revise/report/gate/retrieval), `WritingLoopPolicy.max_total_tokens|max_wall_clock_ms`, `WritingReviseGateService` post-accounting + deadline enforcement, persisted audit run-level `total_tokens`/`wall_clock_ms`, env/Compose `WRITING_LOOP_MAX_TOTAL_TOKENS|WRITING_LOOP_MAX_WALL_CLOCK_MS`.
- **Canonical spec reference**: `docs/system-contract-sot.md` **v1.6.80** (changelog row, line 36) + `docs/plans/05-writing-loop-budget-decisions.md` (M1–M6, "승인 후 첫 회귀 경계" 1–8). Cross-referenced: `docs/plans/flat-loop-gate.md` §Budget (lines 84–85, 89–93, 130–131), `docs/plans/05-writing-bounded-loop-decisions.md` L4–L6.
- **Source of work being verified**: commit `cca09e7` ("feat: add writing loop aggregate budgets"), branch `main`. Working tree clean at verification start; no uncommitted changes.

## Scope

1. **Contract read** — SoT v1.6.80 changelog row + `05-writing-loop-budget-decisions.md` (M1–M6 decision bundle + 8-point red-first lock list) + `flat-loop-gate.md` §Budget (the generic 5-dimension semantics the slice mirrors).
2. **Implementation** — `services/application/app/writing/metering.py`, `revise_gate.py` (loop state machine + `metered()` helper + token/deadline guards + `WritingLoopSummary.total_tokens/wall_clock_ms`), `revise.py`/`report.py`/`gate.py`/`retrieval.py` (`*_metered` variants), `loop_audit.py`/`loop_audit_mongo.py` (run-level aggregate fields), `main.py` (env wiring + `_writing_loop_payload`/`_writing_loop_audit_*_payload` + `_record_loop_audit`).
3. **Regression tests** — `tests/test_writing_loop_budget.py` (new, 480 lines), plus the new `*_metered` tests in `tests/test_writing_{revise,report,gate,retrieval}.py` and the `total_tokens`/`wall_clock_ms` row in `tests/test_writing_loop_audit_mongo.py`.
4. **Public envelope / config** — ephemeral `loop` (4 keys) / `stages` (3 keys) shape, audit summary/detail additive keys, `WritingCandidate`/`WritingGateResult` dataclasses (no `usage` field), `docker-compose.yml` env defaults.
5. **Re-run + mutation** — focused/full regression, `py_compile`, `docker compose config --quiet`, `git diff --check`; 7 targeted mutations to verify each guard bites.

## Methodology

- Built the **canonical contract scope** before opening code: SoT v1.6.80 changelog row → `05-writing-loop-budget-decisions.md` (read end-to-end, incl. Options table + Follow-up/Deferred) → `flat-loop-gate.md` §Budget (the cross-reference the brief names, lines 84–131) → bounded-loop plan L4–L6 (the structural cap this slice builds on). Did not widen beyond that chain.
- Built the **boundary matrix** from the brief's "승인 후 첫 회귀 경계" 1–8 (the lock list) plus M2/M3/M4/M5/M6 decision literals, then traced every should-fire and should-NOT-fire branch + literal to `file:line` in code and to a named test.
- **Cross-checked the contract against itself**: compared the post-accounting (`> limit`, `== limit` 허용) vs deadline (`>=`) asymmetry, the "aggregate는 audit에만" (M5=A) vs ephemeral shape (L6) claims, and the "부재 시 0" (SoT v1.6.80) forward-compat clause across SoT changelog, brief, and code.
- **Mutation testing (7 cases)**: for each load-bearing guard, mutated the source (cp backup → perl replace → run the one pinned test → cp restore → `git diff --quiet` confirm), and recorded whether the test bit. An empty cell = mutation passes the suite unchanged.
- Read each new/changed test and confirmed: assertion pins the contract (not a byproduct); under-strict guard exists (the bug can re-fail it); over-strict guards exist for `== limit` / within-deadline / opt-out branches.
- Independently re-derived test counts; did not copy the work log's numbers.
- Exact commands:
  - `python3 -m pytest tests/test_writing_loop_budget.py tests/test_writing_gate.py tests/test_writing_revise.py tests/test_writing_retrieval.py tests/test_writing_report.py tests/test_writing_loop_audit.py tests/test_writing_loop_audit_mongo.py -q`
  - `python3 -m pytest --ignore=tests/test_memory_mongo.py -q`
  - `python3 -m pytest tests/test_writing_revise.py tests/test_writing_report.py tests/test_writing_gate.py tests/test_writing_retrieval.py -q` (standalone taxonomy)
  - `python3 -m py_compile services/application/app/writing/{metering,revise_gate,revise,report,gate,retrieval,loop_audit,loop_audit_mongo}.py services/application/app/main.py`
  - `docker compose config --quiet`; `git diff --check`; `git show cca09e7 --stat`
  - 7 mutation runs (M1–M7) as described in Findings §6.

## Findings

### 1. Contract ↔ implementation literal consistency

Every contract literal appears unchanged in code:

| Contract literal | Source | Code location | Match |
|---|---|---|---|
| Two aggregate dimensions `total_tokens` + `wall_clock_ms` only (search/context-token stay in Context Gate) | Brief M2=A; SoT v1.6.80 | `revise_gate.py:115-116` policy fields; no search/context cap added | ✓ |
| Token = post-accounting, cumulative `> limit` result not adopted, `== limit` completes | Brief M4=A; `flat-loop-gate.md:85,91,131` | `revise_gate.py:276` `accumulated.total_tokens > policy.max_total_tokens` (strict `>`); checked inside `metered()` after each provider response (`:259,265`) | ✓ |
| Wall-clock = monotonic deadline checked before next provider/search stage | Brief M4=A; `flat-loop-gate.md:84` | `revise_gate.py:283` `elapsed_ms() >= policy.max_wall_clock_ms`; checked at `:313` (pre-report), `:334` (pre-Gate), `:355` (pre-initial), `:400,446` (loop branches), `:470` (pre-context-search) | ✓ |
| Component provider timeout stays a provider error, not budget | Brief M4=A; `flat-loop-gate.md:93` | `test_provider_timeout_is_provider_error_not_budget` → `WritingReviseGateFailure`, `loop.status=failed` | ✓ |
| Defaults `None` (off) | Brief M6=A; SoT v1.6.80 | `revise_gate.py:115-116` defaults `None`; `_env_opt_int` (`main.py:433-438`) maps unset/empty/whitespace → `None`; Compose `${VAR:-}` empty default | ✓ |
| Aggregate on persisted audit only; ephemeral `loop`/`stages` unchanged | Brief M5=A; SoT v1.6.80 | `_writing_loop_payload` 4 keys (`main.py:2386-2392`), `_writing_stages_payload` 3 keys (`:2394-2399`); `total_tokens`/`wall_clock_ms` only in `_writing_loop_audit_summary_payload` (`:2413-2414`) | ✓ |
| Internal usage channel; public `WritingCandidate`/`WritingGateResult` carry no usage | Brief M3=A; SoT v1.6.80 | `models.py` — no `usage`/`TokenUsage` field on any public dataclass; usage rides on `*_metered` return / `MeteredCallError.usage` only | ✓ |
| Standalone `revise`/`report`/`gate`/`plan` keep their HTTP taxonomy (502/504/400) | Brief M3=A; M4=A | Each bare method catches `MeteredCallError` and re-raises `exc.cause` (`revise.py:79-80`, `report.py:73-74`, `gate.py:60-61`, `retrieval.py:102-103`) — usage is discarded | ✓ |
| Mongo doc reads missing aggregate fields as 0 | SoT v1.6.80 | `loop_audit_mongo.py:92-93` `doc.get("total_tokens", 0)` / `doc.get("wall_clock_ms", 0)` | ✓ code; ✗ **test gap — see Issues B1** |
| Failed-loop termination may carry `gate=null` when budget exhausted before first Gate | SoT v1.6.80 | `WritingReviseGateResult.gate: WritingGateResult | None` (`revise_gate.py:159`); `result(BUDGET_EXHAUSTED)` uses `last_gate` which is `None` pre-first-Gate | ✓ |

### 2. Usage plumbing (`*_metered` variants) — M3=A

All four collaborators expose a `*_metered` variant returning `(result, TokenUsage)`:

- **`WritingRevisionService.revise_metered`** (`revise.py:83-154`): success → `(revised, result.usage)`; parse/empty/unchanged failure → `MeteredCallError(cause, result.usage)`. Single provider call (no repair). ✓
- **`WritingCandidateReportService.enrich_metered`** (`report.py:77-102`): initial call → `usage = result.usage`; on parse failure, repair call → `usage = add_usage(usage, repair.usage)`; final parse failure → `MeteredCallError(cause, usage)` carrying **initial + repair** usage; repair-provider fault → `MeteredCallError(exc, usage)` (initial usage only, since repair produced no response). ✓
- **`WritingGateService.evaluate_metered`** (`gate.py:64-92`): success → `(WritingGateResult, result.usage)`; parse/validation failure → `MeteredCallError(InvalidWritingGateResult, result.usage)`. ✓
- **`TerminalJsonWritingRetrievalPlanner.plan_metered`** (`retrieval.py:106-170`): symmetric to report — initial + repair usage summed on success; `MeteredCallError(second, usage)` carrying both usages on final failure. ✓

`metering.py` (`add_usage` sums prompt+completion; `MeteredCallError` carries `cause + usage`; `EMPTY_USAGE = TokenUsage()`) is minimal and correct. No speculative abstraction.

### 3. Loop enforcement semantics (`revise_gate.py`) — M4=A

The `metered()` helper (`:247-267`) is the single chokepoint: it prefers `<method>_metered`, accumulates `usage` (success path) or `exc.usage` (`MeteredCallError` path), then calls `token_over_budget()`. On overrun it raises `_PostAccountingBudgetExceeded`, which each stage site catches to return `BUDGET_EXHAUSTED` while preserving `current_candidate` and `last_gate`. Provider/parse faults that stay under budget re-raise `exc.cause` so the stage's existing failure taxonomy (`WritingReviseReportFailure`/`WritingReviseGateFailure`/`WritingLoopRevisionFailure`/`WritingRetrievalFailure`) is unchanged.

- **`== limit` completes**: strict `>` in `token_over_budget` (`:276`) — pinned by `test_cumulative_equal_to_limit_can_complete` (10 == 10 → PASS).
- **Over-limit not adopted**: pinned by `test_gate_response_over_limit_is_not_adopted` (10 > 9 → BUDGET_EXHAUSTED, `revision_rounds=1`, `gate=None`, `provider.calls=1`, stages `[revise, report]` — the over-limit Gate response was counted but discarded).
- **Pre-first-Revise / pre-Report / pre-Gate / pre-context-search deadline**: each has a dedicated wall-clock test with an injected clock double; `test_deadline_after_retrieval_plan_blocks_context_search` confirms the planner ran (`planner.calls=1`) but context search did not (`context.calls=0`).
- **Failed-stage usage still counted**: `MeteredCallError` path accumulates `exc.usage` *before* deciding budget/cause, so a rejected report response's tokens reach the audit even when the original error propagates — pinned by `test_failed_stage_usage_is_counted_before_original_error_propagates` (revise 2 + rejected-report 3 = 5).
- **Token overrun wins over parse error**: `test_failed_response_token_overrun_wins_before_parse_error` — max=4, rejected report makes 5 > 4 → `BUDGET_EXHAUSTED` (not `WritingReviseReportFailure`), matching the generic-runner precedent (work log "parse 오류보다 budget_exhausted가 먼저").

### 4. Persisted audit aggregate + opt-in — M5=A / P2=B (v1.6.79)

- `StoredWritingLoopRun.total_tokens/wall_clock_ms` default to 0 (`loop_audit.py:65-66`), so older direct constructions stay valid.
- `WritingLoopAuditService.record` copies `summary.total_tokens`/`wall_clock_ms` into the run (`:145-146`).
- `_doc()` always writes both fields (`loop_audit_mongo.py:60-61`); `_run()` reads them with `doc.get(..., 0)` default (`:92-93`).
- Ephemeral `_writing_loop_payload` keeps exactly `{status, revision_rounds, retrieval_rounds, gate_evaluations}` — pinned by `test_ephemeral_loop_payload_excludes_token_fields` (asserts exact 4-key set even with a budget configured).
- Audit detail carries `total_tokens` — pinned by `test_persisted_audit_carries_aggregate_tokens` (revise 2 + report 3 + gate 5 = 10 on a single-pass loop).
- Opt-in default off / env-on / request-flag-override and persist-failure isolation are the v1.6.79 contract; this slice only adds the two fields, which the existing `test_opt_in_default_off_persists_nothing` and `test_persist_failure_is_isolated_from_the_loop_result` continue to cover.

### 5. Config wiring — M6=A

`WritingLoopPolicy.__post_init__` rejects non-positive caps (`revise_gate.py:125-128`); `WritingLoopPolicyBudgetTest` pins both directions. `main.py:1149-1163` wires `_env_opt_int("WRITING_LOOP_MAX_TOTAL_TOKENS")`/`("WRITING_LOOP_MAX_WALL_CLOCK_MS")`; `test_env_token_limit_changes_state_and_empty_value_is_unbounded` pins both directions (`"1"` → `budget_exhausted`, `""` → `pass`). Compose (`docker-compose.yml:45-46`) exposes both with `${VAR:-}` empty defaults. `docker compose config --quiet` passes.

### 6. Mutation results (each guard bites → no empty cell at that surface)

| # | Mutation (source) | Pinned test | Outcome |
|---|---|---|---|
| M1 | token `>` → `>=` (over-strict) | `test_cumulative_equal_to_limit_can_complete` | **1 failed** ✓ |
| M2 | token limit ×1000 (under-strict) | `test_gate_response_over_limit_is_not_adopted` | **1 failed** ✓ |
| M3 | `report.py` repair-usage sum removed | `test_enrich_metered_sums_initial_and_repair_usage` | **1 failed** ✓ |
| M3b | `retrieval.py` repair-usage sum removed | `test_plan_metered_sums_initial_and_repair_usage` | **1 failed** ✓ |
| M4 | wall-clock limit ×1000 (under-strict) | `test_deadline_reached_before_initial_stage_starts_nothing` | **1 failed** ✓ |
| M5 | `metered()` skips `exc.usage` accumulation | `test_failed_stage_usage_is_counted_before_original_error_propagates` | **1 failed** ✓ |
| M6 | audit summary omits `total_tokens` key | `test_persisted_audit_carries_aggregate_tokens` | **1 failed** ✓ |
| **M7** | **`loop_audit_mongo.py` `doc.get(k,0)` → `doc[k]`** | (SoT v1.6.80 "부재 시 0") | **0 failed — suite still green → EMPTY CELL** ✗ |

All mutations restored; `git diff --quiet` clean after each.

### 7. Re-run reproduction

- Focused (7 files): **116 passed / 90 subtests** — matches work log exactly.
- Full non-Mongo: **971 passed / 48 skipped / 215 subtests** (3 pre-existing `TestClient` collection warnings) — matches work log exactly.
- Standalone endpoint suite (revise/report/gate/retrieval): **78 passed / 84 subtests** — taxonomy unchanged after usage plumbing.
- `py_compile` (all changed modules) ✓; `docker compose config --quiet` ✓; `git diff --check` ✓.

## Issues / Risks

### Blocking (contract obligations)

- **B1 — Mongo aggregate "부재 시 0으로 읽는다" forward-compat guard is an empty cell.** SoT v1.6.80 explicitly states "감사 Mongo 구문서는 신규 필드 부재 시 0으로 읽는다". The code honours this (`loop_audit_mongo.py:92-93` `doc.get("total_tokens", 0)` / `doc.get("wall_clock_ms", 0)`), but no test pins it. The existing `test_add_get_and_list_round_trip_newest_first` only round-trips a doc that *has* both fields (`_run(..., total_tokens=123, wall_clock_ms=456)`), so it cannot detect a regression to `doc["total_tokens"]` (which would `KeyError` on a legacy doc lacking the fields). **Mutation M7 proves the cell is empty**: replacing `doc.get(k, 0)` with `doc[k]` leaves the full audit suite green (19 passed / 6 subtests). This is a contract-required lock that is untraced — per the "boundary matrix has no empty cells" rule the verdict cannot be a clean pass until a dedicated test constructs a field-less doc (or strips the two keys from a written doc) and asserts both fields read back as `0`. Trivial test-only closure; production code is unchanged and correct.

### Hardening recommendations (non-blocking — go beyond the current spec)

- **H1 — `metered()` bare-method fallback to `EMPTY_USAGE` is unguarded.** If a collaborator without a `*_metered` variant is injected while `max_total_tokens` is set, its usage is silently counted as zero, understating the aggregate. The four production collaborators all expose `*_metered`, and the default (`None`) policy makes the fallback harmless, so this is not reachable in production today. Candidate: either assert `*_metered` exists when a budget is active, or document the fallback as "usage unavailable → 0" explicitly in the brief. No spec clause currently requires either.
- **H2 — The post-accounting (`>`, `==` allowed) vs deadline (`>=`) operator asymmetry is correct but worth a one-line code comment.** It mirrors `flat-loop-gate.md` (token is post-accounting; wall-clock is a pre-check "N번째 허용, N+1번째 차단" per line 89), and M1/M2/M4 mutations confirm both directions are pinned, but the two operators sitting 7 lines apart (`revise_gate.py:276` vs `:283`) read as a possible typo without the generic-spec cross-reference. A comment citing `flat-loop-gate.md:89-91` would prevent a future "fix" that harmonizes them.
- **H3 — Retrieval-planner token overrun does not record a `retrieve_plan` stage.** When the planner response itself pushes cumulative tokens over `max_total_tokens`, `metered()` raises `_PostAccountingBudgetExceeded` before `record(RETRIEVE_PLAN, COMPLETED)` (`revise_gate.py:460-465`), so the audit trail omits the stage that triggered the overrun. This is consistent with how Gate-over-limit omits the `gate` stage (M2), so it is an observational symmetry, not a contract violation. Candidate: record a `retrieve_plan`/`failed` stage on the budget-exceeded path for richer audit, if per-stage observability becomes a goal (M5=C territory).

## Verdict

**조건부 합격 (conditional pass).**

The slice faithfully implements the owner-approved M1=A / M2=A / M3=A / M4=A / M5=A first→B / M6=A bundle: the four `*_metered` variants, the post-accounting token guard, the monotonic deadline guard, the off-by-default opt-in config, the audit-only aggregate exposure, and the unchanged public envelope are all correct and pinned in both directions (M1–M6 mutations all bite). Focused/full regression reproduces the work log's counts exactly. The metering plumbing is minimal and introduces no speculative abstraction.

The single condition is **B1**: SoT v1.6.80's "부재 시 0으로 읽는다" forward-compat clause is a contract-required lock, and mutation M7 proves no test guards it. Production code is correct; the gap is a missing regression. Closing it is a one-test, production-unchanged fix (construct a doc without the two keys, assert both read back as `0`). Until that test exists the boundary matrix has one empty cell, so the verdict is conditional rather than a clean pass.

## Outstanding items

- **B1 closure awaiting owner decision**: verifier does not silently add the test. Owner may authorize the trivial test-only closure (mirror the M7 mutation as a red-then-green regression), or accept the asymmetry (round-trip covers the new-code path; legacy docs are only reachable from a pre-v1.6.80 store on the same day's work). The fix is mechanical either way.
- **B2b (live calibration) unchanged**: production `max_total_tokens`/`max_wall_clock_ms` numbers remain `None`/off by design until the full-stack Gemma Q4 loop-level benchmark; this verification did not (and per the brief must not) introduce numbers.
- No uncommitted work; working tree clean; commit `cca09e7` is the verified artifact.

## Reproduction

```bash
# Focused + full regression (re-derives 116 / 971)
python3 -m pytest tests/test_writing_loop_budget.py tests/test_writing_gate.py \
  tests/test_writing_revise.py tests/test_writing_retrieval.py tests/test_writing_report.py \
  tests/test_writing_loop_audit.py tests/test_writing_loop_audit_mongo.py -q
python3 -m pytest --ignore=tests/test_memory_mongo.py -q

# B1 empty-cell proof (the suite stays green — the gap):
cp services/application/app/writing/loop_audit_mongo.py /tmp/lam.bak
perl -pi -e 's/doc\.get\("total_tokens", 0\)/doc["total_tokens"]/g; s/doc\.get\("wall_clock_ms", 0\)/doc["wall_clock_ms"]/g' \
  services/application/app/writing/loop_audit_mongo.py
python3 -m pytest tests/test_writing_loop_audit_mongo.py tests/test_writing_loop_audit.py -q   # → 19 passed, 6 subtests (no failure)
cp /tmp/lam.bak services/application/app/writing/loop_audit_mongo.py

# M1–M6 guard-bite spot check (each should print "1 failed"):
#   token >→>=:        test_cumulative_equal_to_limit_can_complete
#   token x1000:       test_gate_response_over_limit_is_not_adopted
#   report no-sum:     test_enrich_metered_sums_initial_and_repair_usage
#   retrieval no-sum:  test_plan_metered_sums_initial_and_repair_usage
#   wall-clock x1000:  test_deadline_reached_before_initial_stage_starts_nothing
#   no exc.usage:      test_failed_stage_usage_is_counted_before_original_error_propagates
#   audit no-token:    test_persisted_audit_carries_aggregate_tokens

# Static checks
python3 -m py_compile services/application/app/writing/{metering,revise_gate,revise,report,gate,retrieval,loop_audit,loop_audit_mongo}.py services/application/app/main.py
docker compose config --quiet
git diff --check
```

## Owner-authorized closure addendum (Codex)

- **Authorization**: owner requested that the verification record be reviewed and its actionable hardening applied.
- **B1 closed (test-only)**: `tests/test_writing_loop_audit_mongo.py::MongoWritingLoopAuditRepositoryTest::test_legacy_doc_without_aggregate_fields_reads_zero` now removes `total_tokens`/`wall_clock_ms` from a stored document and asserts both read back as `0`. The existing field-for-field round-trip test remains the over-strict guard for present values (`123`/`456`). Production Mongo code is unchanged.
- **M7 re-bite**: temporarily changing both `doc.get(key, 0)` reads to `doc[key]` made the new test fail with `KeyError: 'total_tokens'` (`1 failed`); restoring the implementation made it pass (`1 passed`). The previously empty contract cell now bites in both directions.
- **H2 applied**: `revise_gate.py` now explains that token uses post-accounting strict `>` while deadline uses pre-stage `>=`, explicitly referencing `flat-loop-gate` §Budget. Behavior is unchanged.
- **H1 deferred**: forbidding the bare-method fallback under an active token cap would create a new collaborator-injection/configuration failure contract and HTTP taxonomy. All four production collaborators already expose `*_metered`; a fail-fast rule requires a separate contract decision if non-production injection becomes an operational surface.
- **H3 deferred**: the planner response that exceeds token budget is deliberately not adopted, matching Gate-overrun behavior. Recording it as `completed` would be false; adding a new per-stage `budget_exhausted` status belongs with the deferred M5=C per-stage observability schema.
- **Reproduction after closure**: audit/B2 focused subset `39 passed / 6 subtests`; full non-Mongo `972 passed / 48 skipped / 215 subtests`; `py_compile` and `git diff --check` passed. The original conditional verdict above is preserved as the independent verifier's historical verdict; its sole blocking condition is closed in the working tree, but an independent re-verdict was not performed in this addendum.
