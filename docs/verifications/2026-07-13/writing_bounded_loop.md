# Verification — Phase 5.9 G8 bounded revise/retrieve loop

## Subject metadata

- **Date**: 2026-07-13
- **Requester**: entangelk (owner) — "작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?"
- **Verifier**: Claude (independent verification session)
- **Target slice/artifact**: Writing bounded revise/retrieve loop — `WritingReviseGateService` bounded state machine, `WritingLoopPolicy`, additive `loop`/`stages` envelope, `WRITING_LOOP_MAX_*` env/Compose wiring, `UnchangedWritingRevision` typed distinction.
- **Canonical spec reference**: `docs/system-contract-sot.md` **v1.6.77** (changelog row) + `docs/plans/05-writing-bounded-loop-decisions.md` (L1–L9, "승인 후 첫 회귀 경계" 1–9). Cross-referenced: `05-writing-revise-gate-decisions.md` G8, `05-writing-partial-revise-decisions.md` D5/D7/D8, `05-writing-revise-report-gate-decisions.md` R5, `05-writing-retrieve-more-decisions.md` T7/T8.
- **Source of work being verified**: commit `565b9ec` ("feat: add bounded writing revision loop"), branch `main`, working tree clean.

## Scope

1. **Contract read** — SoT v1.6.77 + bounded-loop decision plan (L1–L9, 9 regression boundaries) + 4 cross-referenced plan "후속 채택(v1.6.77)" notes.
2. **Implementation** — `services/application/app/writing/revise_gate.py` (loop state machine, `WritingLoopPolicy`, `_eligible_revision_finding`, stage/loop/status enums, failure wrappers), `services/application/app/main.py` (`/writing/revise-and-gate` HTTP mapping, env/Compose wiring, payload serializers), `services/application/app/writing/revise.py` (`UnchangedWritingRevision` type).
3. **Regression tests** — `tests/test_writing_revise.py` (new loop tests + eligibility/partials), `tests/test_writing_retrieval.py` (constructor refactor).
4. **Public envelope / config** — `loop`/`stages` JSON shape, HTTP status taxonomy, `docker-compose.yml` env defaults.
5. **Re-run** — focused writing suite, full suite, `py_compile`, `docker compose config --quiet`, `git diff --check`.

## Methodology

- Built the **canonical contract scope** before opening code: SoT v1.6.77 changelog row → `05-writing-bounded-loop-decisions.md` (read end-to-end) → each cross-reference the plan names (G8/D4/D5/D7/D8/R5/T7/T8 + `flat-loop-gate.md`). Did not widen beyond that chain.
- Built the **boundary matrix** from the plan's "승인 후 첫 회귀 경계" 1–9 (the lock list) plus L1–L9 decision literals, then traced every should-fire and should-NOT-fire branch + literal to `file:line` in code and to a named test.
- **Cross-checked the contract against itself**: compared every literal (termination literals, stage names, stage status, loop fields, default caps, eligibility predicate, state transitions, unchanged semantics) across decision plan, SoT changelog, and code.
- Read each new/changed test and confirmed: assertion pins the contract (not a byproduct); under-strict guard exists (the bug can re-fail it); over-strict guards exist for should-NOT-fire branches; parametrized cases cover enumerated boundary values.
- Independently re-derived test counts; did not copy the work log's numbers.
- Exact commands:
  - `python3 -m pytest tests/test_writing_revise.py tests/test_writing_retrieval.py -q`
  - `python3 -m pytest tests/test_writing.py tests/test_writing_accept.py tests/test_writing_gate.py tests/test_writing_report.py tests/test_writing_retrieval.py tests/test_writing_revise.py -q`
  - `python3 -m pytest -q`
  - `python3 -m py_compile services/application/app/writing/revise_gate.py services/application/app/writing/revise.py services/application/app/main.py`
  - `docker compose config --quiet`
  - `git diff --check`; `git show 565b9ec --stat`; `git diff 51f2723 565b9ec -- tests/test_memory_mongo.py services/application/app/memory/mongo_repository.py`

## Findings

### 1. Contract ↔ implementation literal consistency

Every contract literal appears unchanged in code:

| Contract literal | Source | Code location | Match |
|---|---|---|---|
| Termination `pass\|terminal_decision\|not_eligible\|budget_exhausted\|no_change` + failure `failed` | Plan L7; SoT v1.6.77 | `revise_gate.py:64-70` `WritingLoopStatus` | ✓ |
| Stage `revise\|report\|gate\|retrieve_plan\|context_search\|merge` | Plan L6 | `revise_gate.py:73-79` `WritingLoopStageName` | ✓ |
| Stage status `completed\|failed\|no_change` | Plan L6 | `revise_gate.py:82-86` `WritingLoopStageStatus` | ✓ |
| Loop fields `{status,revision_rounds,retrieval_rounds,gate_evaluations}` | Plan L6 | `revise_gate.py:112-117`; `main.py:2346-2352` | ✓ |
| Default caps revision 2 / retrieval 1 / gate 3 | Plan L4; SoT v1.6.77 | `revise_gate.py:92-94`; `docker-compose.yml:38-40` | ✓ |
| Stage item `{stage,ordinal,status}` | Plan L6 | `revise_gate.py:105-109`; `main.py:2354-2359` | ✓ |
| `UnchangedWritingRevision` typed distinction | Plan L8; SoT v1.6.77 | `revise.py:41` `UnchangedWritingRevision(InvalidWritingRevision)` | ✓ |

No paraphrase, no contract-internal contradiction found.

### 2. Boundary matrix — every cell traced (no empty cells)

Built from "승인 후 첫 회귀 경계" 1–9 + L1–L9. Each should-fire and should-NOT-fire branch maps to code and a named test:

1. **`pass|needs_user_review|block` terminate** — `revise_gate.py:269-275` (pass→`PASS`; needs_user_review/block→`TERMINAL_DECISION`; immediate return, no further calls). Tests: `test_auto_revise_refreshes_report_and_reaches_pass` (pass); `test_ineligible_or_human_gate_decision_never_auto_revises` (needs_user_review, block → terminal_decision; asserts provider/reporter/gate calls == 1). ✓
2. **Single continuity revise finding eligible; broader → `not_eligible`, 0 fix calls** — `_eligible_revision_finding` `revise_gate.py:379-394` (len==1, CONTINUITY, REVISE, evidence non-empty & count==1). Positive: `test_auto_revise_refreshes_report_and_reaches_pass` (eligible → 2nd revise). Negative (5 cases): `test_revise_eligibility_rejects_every_broader_boundary` — empty, 2-finding, POV, evidence-0-occurrences ("존재하지 않는 문장."), evidence-multi-occurrences ("문장.") → all `not_eligible`, provider.calls==1. ✓
3. **revise→report→Gate (same package); retrieve→merge→Gate (no re-report)** — revise path `revise_gate.py:314-315` (`refresh_report`+`evaluate_gate`); retrieve path `revise_gate.py:358-373` (merge→`evaluate_gate`, no `refresh_report`). Tests: `test_retrieve_more_merges_and_regates_without_rereport` (reporter.calls==1 after retrieve); `test_retrieve_then_revise...` stage sequence has no `report` between `merge` and `gate`. ✓
4. **revise→retrieve and retrieve→revise within Gate 3, each action once** — `revise_gate.py:282-283` (revise budget), `319-320` (retrieve budget), both OR-combine gate-eval cap. Tests: `test_revise_then_retrieve_also_reaches_pass_with_same_caps` and `test_retrieve_then_revise_uses_each_action_once_and_three_gates` — both assert revision_rounds==2, retrieval_rounds==1, gate_evaluations==3. ✓
5. **Same auto decision again → `budget_exhausted` before next call** — cap checks precede the action call (`revise_gate.py:282-284`, `319-321`). Tests: `test_configurable_revision_cap_stops_before_auto_revise` (max_revision_rounds=1 → 2nd REVISE → budget_exhausted); `test_loop_caps_are_loaded_from_environment_settings` (env 1/0/1 → budget_exhausted, gate_evaluations==1). ✓
6. **auto-revise unchanged → 200 `no_change`, preserve candidate+last Gate, 0 extra calls** — `revise_gate.py:293-298` catches `UnchangedWritingRevision` → `NO_CHANGE`, returns `current_candidate` (pre-unchanged) + `last_gate`. Test: `test_auto_revise_unchanged_is_typed_no_change_not_standalone_error` (200, loop.status==no_change, revision_rounds==2, candidate preserved, gate.decision==revise, stages[-1]==revise/no_change). ✓
7. **Success: candidate+final Gate+loop+stages; stage failure: partial envelope (last candidate/Gate + pre-failure stages)** — success `revise_gate.py:212-216`; failure wrappers `_WritingLoopFailure` `revise_gate.py:128-143`. main.py success body `2843-2848`; failure bodies `2732-2842` each carry candidate/gate/loop/stages. Tests: pass-reaching tests assert loop+stages; `test_auto_revise_failure_preserves_previous_candidate_gate_and_stages`, `test_revise_provider_timeout_is_504_without_calling_gate`, `test_retrieval_failure_preserves_candidate_and_first_gate`, `test_second_gate_failure_keeps_latest_report_without_rereport`, `test_report_failure_returns_partial_candidate_without_calling_gate`. ✓
8. **request/project identity + `candidate_id=null` + save/accept/Analysis/persistence=0** — endpoint never calls save/accept/Analysis; `revise.py:128` sets `candidate_id=None`. Tests: `test_retrieve_more_merges...` (candidate_id is None, core.save_calls==0); `test_composition_does_not_save_draft` (save_calls==0). ✓
9. **JSON repair is component-internal, not a loop round** — report repair unchanged in report service; loop couples report 1:1 to revise (max 2). No new retry added. ✓ (pre-existing report contract, not modified by this slice)

### 3. L8 three-way unchanged distinction (the highest-risk branch)

The contract requires three distinct unchanged semantics. All three are implemented and independently tested:

- **Initial revise unchanged (in loop) → 502**: initial revise catches `Exception` → `WritingLoopRevisionFailure` (`revise_gate.py:257-262`); main.py `2757-2765` maps `cause` `UnchangedWritingRevision` (is-a `InvalidWritingRevision`) → 502. Test: `test_revise_failure_never_calls_gate` (`_Provider("잘못된 문장.")` → 502, reporter/gate calls==0).
- **Standalone `/writing/revise` unchanged → 502**: `main.py:2635-2636` `except InvalidWritingRevision` → 502. Tests: `test_http_validation_and_unchanged_mapping`; standalone half of `test_auto_revise_unchanged...`.
- **Auto-followup revise unchanged → 200 `no_change`**: `revise_gate.py:293-298`. Test: `test_auto_revise_unchanged_is_typed_no_change_not_standalone_error`.

The auto path catches `UnchangedWritingRevision` *before* the generic `except Exception` (`revise_gate.py:293` precedes `299`), so the typed distinction is structural, not string-based. Two-directional guard confirmed: each direction has a test that would re-fail if the branch were inverted.

### 4. Constructor refactor (orphan check)

`WritingReviseGateService` constructor changed from `max_retrieval_rounds=` to `policy: WritingLoopPolicy`. All 3 call sites updated: `main.py:1106-1127` (builds policy from env), `test_writing_retrieval.py:272,323` (now `policy=WritingLoopPolicy(max_retrieval_rounds=1)`). Grep confirms no remaining bare `max_retrieval_rounds=` service argument. No orphaned old API. ✓

### 5. Compose / env / config surface

`docker-compose.yml:38-40` exposes `WRITING_LOOP_MAX_REVISION_ROUNDS=2`, `WRITING_LOOP_MAX_RETRIEVAL_ROUNDS=1`, `WRITING_LOOP_MAX_GATE_EVALUATIONS=3` (with host-var overrides). `main.py:1113-1123` reads the same env via `_env_int` with matching defaults. `WritingLoopPolicy.__post_init__` (`revise_gate.py:96-102`) rejects `max_revision_rounds<1`, `max_retrieval_rounds<0`, `max_gate_evaluations<1`. Test `test_loop_policy_accepts_tunable_caps_and_rejects_invalid_settings` locks tunability + the 3 invalid-value guards; `test_loop_caps_are_loaded_from_environment_settings` locks env loading. ✓

### 6. Re-run results (independently derived)

- **Writing focused** (`test_writing*.py`, 6 files): **115 passed, 108 subtests** — matches work log exactly.
- **Full suite**: **927 passed, 45 skipped, 209 subtests** — matches work log. **Plus 4 failed** in `tests/test_memory_mongo.py::MongoMemoryRepositoryTest` (see Outstanding items).
- `py_compile` on the 3 changed modules: OK.
- `docker compose config --quiet`: OK.
- `git diff --check`: clean.

## Issues / Risks

### Blocking (contract obligations)

**None.** Every contract-required branch — should-fire and should-NOT-fire — in the L1–L9 / regression-boundary-1–9 matrix maps to a named regression test with both under-strict and over-strict guards. No contract-internal contradiction. All literals appear unchanged in code. No untraced boundary.

### Hardening recommendations (non-blocking, beyond current spec)

- **H1 — default-cap literal not unit-locked.** `WritingLoopPolicy()` defaults (2,1,3) are a contract literal (Plan L4; SoT v1.6.77) and appear unchanged in code (`revise_gate.py:92-94`) and Compose, and are implicitly bounded *below* by the pass-reaching loop tests (which require caps ≥ 2 revises / 3 gates). But no test asserts `WritingLoopPolicy() == (2,1,3)` exactly, so an upward drift (e.g. to 3/2/5) would pass the green bar. A one-line `assert WritingLoopPolicy().max_revision_rounds == 2` (etc.) would lock the exact default. The env-loading and tunability paths are already tested.
- **H2 — default-cap `budget_exhausted` termination not explicitly sampled.** Boundary #5 is traced via a *configurable* cap (max_revision_rounds=1). The same value-agnostic branch at the *default* cap (a 3rd consecutive REVISE after 2 revises → budget_exhausted) is not separately sampled. Adding it would lock the default-cap termination explicitly; absence is non-blocking because the branch logic is identical and the configurable test proves it fires.
- **H3 — defensive dead-ish catch.** `main.py:2720-2721` `except InvalidWritingRevision → 502` in the `/writing/revise-and-gate` handler is unreachable from the loop path (the loop wraps every revise exception in `WritingLoopRevisionFailure` at `revise_gate.py:257`/`299-308`, and `validate_inputs` raises `WritingRevisionError` not `InvalidWritingRevision`). It is harmless defensive code (likely carried from the partial-revise slice), not a defect — flagged only for awareness.

## Verdict

**합격 (PASS).**

The slice faithfully realizes SoT v1.6.77 / Plan L1–L9: the bounded state machine enforces structural caps (revision 2 / retrieval 1 / gate 3, configurable) before each action, terminates with the correct business-outcome literal, preserves the L8 three-way `UnchangedWritingRevision` distinction (initial/standalone → 502, auto → 200 `no_change`), exposes the additive minimal `loop`/`stages` envelope, and preserves candidate/Gate/stages in every partial-failure path. The boundary matrix has no empty cells; every contract-required branch has two-directional regression coverage. Reported test counts (115/108 writing; 927/45/209 full) reproduce exactly. The three hardening items are beyond-spec niceties and do not affect the verdict.

## Outstanding items

- **4 `test_memory_mongo.py` failures are environmental, not a slice regression.** They fail with `MongoMemoryRepositorySetupError: failed to create required memory MongoDB indexes` during setup (Mongo index creation on the running `agent-memory-mongodb`/`shared-mongo` containers). This slice touched **no** memory/Mongo file (`git show 565b9ec --stat` lists only writing files); `git diff 51f2723 565b9ec -- tests/test_memory_mongo.py services/application/app/memory/mongo_repository.py` is empty (byte-identical parent↔child). The worker's environment rendered these 4 as pass/skip; this environment reaches a partially-available Mongo and fails index creation. They should be investigated as a separate Mongo-infra item, not against the writing bounded-loop slice.
- All other full-suite outcomes (927 passed / 45 skipped / 209 subtests) match the work log; the slice's own regression surface is green.

## Reproduction

```bash
# Contract scope (read end-to-end before code):
#   docs/system-contract-sot.md  (v1.6.77 changelog row)
#   docs/plans/05-writing-bounded-loop-decisions.md  (L1-L9 + 회귀 경계 1-9)

# Focused (matches work log "Writing focused"):
python3 -m pytest tests/test_writing.py tests/test_writing_accept.py \
  tests/test_writing_gate.py tests/test_writing_report.py \
  tests/test_writing_retrieval.py tests/test_writing_revise.py -q
# -> 115 passed, 108 subtests passed

# Full suite (expect 4 unrelated Mongo-infra failures in this environment):
python3 -m pytest -q
# -> 4 failed (test_memory_mongo), 927 passed, 45 skipped, 209 subtests passed

# Static / config:
python3 -m py_compile services/application/app/writing/revise_gate.py \
  services/application/app/writing/revise.py services/application/app/main.py
docker compose config --quiet
git diff --check

# Prove the 4 Mongo failures are not from this slice:
git show 565b9ec --stat | grep -iE 'memory|mongo'   # (no output)
git diff 51f2723 565b9ec -- tests/test_memory_mongo.py \
  services/application/app/memory/mongo_repository.py  # (empty)
```
