# Verification — Writing persisted bounded-loop audit (Phase 5.9 L9 B, SoT v1.6.78)

## Subject metadata

- **Date**: 2026-07-13
- **Requester**: owner (독립 검증·의심 반복 요청)
- **Verifier**: Claude (session verifier, 작업자와 별개 컨텍스트)
- **Target slice**: Phase 5.9 L9 B persisted Writing bounded-loop audit — SoT v1.6.78
- **Canonical spec reference**:
  - `docs/system-contract-sot.md` v1.6.78 version-table row (line 36) + header v1.6.78 Approved
  - `docs/plans/05-writing-persisted-loop-audit-decisions.md` — owner decision brief (P1=B, P2=A, P3=A, P4=A, P5=A + retention directive), "승인 후 첫 회귀 경계" §98–106
  - Parent invariant: SoT v1.6.77 bounded-loop behavior (unchanged by this slice)
  - Adopted pattern: v1.6.65 Gate finding durable store (`06-gate-finding-persistence-decisions.md`)
- **Source of work being verified**: working tree, **uncommitted** (`git status`: modified `main.py`/`revise_gate.py`/`tests/test_writing_revise.py` + new `audit_hash.py`/`loop_audit.py`/`loop_audit_mongo.py`/`tests/test_writing_loop_audit.py`/brief). Worker stated no commit was made.

## Scope

The discrete surfaces checked against the canonical contract:

1. **Contract read** — SoT v1.6.78 row, brief P1–P5 + retention directive + "승인 후 첫 회귀 경계" 7 boundaries, cross-references (v1.6.77 parent, v1.6.65 precedent).
2. **Implementation code** — `writing/audit_hash.py`, `writing/loop_audit.py`, `writing/loop_audit_mongo.py`, `writing/revise_gate.py` (stage enrich + `record()` closure), `main.py` (default service, create_app wiring, `_record_loop_audit`, 5 termination audit sites, 2 read endpoints, 3 serialization surfaces).
3. **Regression tests** — `tests/test_writing_loop_audit.py` (+12) and the extended `tests/test_writing_revise.py`.
4. **Public envelope/schema** — summary list row, detail trail, ephemeral `{candidate,gate,loop,stages}`+`audit_id` response, `StoredWritingLoopRun`/`StoredLoopStage` dataclasses, Mongo doc round-trip.
5. **Test suite** — focused (loop audit, Writing 7-file) and full non-Mongo.
6. **Docs** — CHANGELOG, HANDOFF, work_log, SoT version header.

Out of scope (per brief): loop behavior policy (v1.6.77 invariant), full artifact body (P1=C), token/latency aggregation (B2), retention TTL, frontend.

## Methodology

- **Scope-first contract read**: built the boundary matrix from the brief's §98–106 lock list and the SoT v1.6.78 row *before* opening implementation, then traced each "should fire" / "should NOT fire" branch to a named test.
- **Primary-source re-derivation**: read each implementation symbol and test; did not copy worker claims.
- **Adversarial mutation (two-directional)**: injected a contract-violating field into each serialization surface and ran the suite to confirm whether a regression bites — the operational test of "empty cell vs. locked cell."
- **Literal cross-check**: compared every SoT/brief literal (field names, status set, status codes, ordering, immutability, additive rule) to code.
- **Commands** (exact):
  - `python3 -m py_compile services/application/app/writing/audit_hash.py services/application/app/writing/loop_audit.py services/application/app/writing/loop_audit_mongo.py services/application/app/writing/revise_gate.py services/application/app/main.py tests/test_writing_loop_audit.py`
  - `git diff --check`
  - `python3 -m pytest -q -p no:cacheprovider tests/test_writing_loop_audit.py`
  - `python3 -m pytest -q -p no:cacheprovider tests/test_writing_revise.py tests/test_writing_retrieval.py tests/test_writing_report.py tests/test_writing.py tests/test_writing_gate.py tests/test_writing_accept.py tests/test_writing_loop_audit.py`
  - `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider`
  - Mutation bites: edit `_writing_loop_audit_payload` / `_writing_loop_audit_summary_payload` in `main.py`, re-run `tests/test_writing_loop_audit.py`, revert (`git diff --stat` + grep to confirm clean).

## Findings

### 1. Contract read — boundary matrix

Canonical scope (SoT v1.6.78 row + brief §98–106). "filled" = maps to a named regression that fails if the branch is violated; **EMPTY** = contract-required branch with no tracing test.

| # | Clause (fire / NOT fire) | Tracing test | Cell |
|---|---|---|---|
| 1a | Success-path termination → 1 audit record | `test_success_loop_persists_full_trail_and_returns_audit_id` (pass); other 4 result statuses via one uniform site `main.py:2939` | filled (pass); 4 statuses = H2 |
| 1b | Partial-failure termination (4 exception types) → 1 audit record | `test_every_termination_is_audited_including_failure` (gate_error); report/revision/retrieval via uniform `_record_loop_audit` sites `main.py:2813/2846/2887/2917` | filled (gate_error); 3 types = H2 |
| 1c | Stage order preserved in record | `test_success_loop...` (6-stage sequence assertion) | filled |
| 2 | Retry = new run id; existing never mutated (append-only, both directions) | `test_retry_appends_a_new_run_and_never_mutates`; `test_retry_appends_distinct_runs_summary_is_bodyless_newest_first` | filled |
| 3a | Per-stage hash/fingerprint/pointer; final text is the one body | `test_record_captures_bodyless_trail_and_final_text` | filled |
| 3b | `final_candidate_hash == stages[-1].candidate_hash` | `test_success_loop...` (explicit) | filled (success); failure paths hold by construction |
| 3c | Intermediate stages carry hash ONLY — no candidate body in stage rows | none on detail stage rows | **EMPTY — B1** |
| 4a | list: project isolation | `test_project_isolation_on_list_and_detail`; `test_list_is_project_scoped_and_newest_first` | filled |
| 4b | list: created_at desc | `test_list_is_project_scoped_and_newest_first`; `test_retry_appends_distinct...` | filled |
| 4c | list: summary bodyless only | `test_retry_appends_distinct...` (exact 8-key set, `test_writing_loop_audit.py:294-298`) | filled |
| 4d | detail: cross-project / missing → 404 | `test_project_isolation...`; `test_get_rejects_cross_project_and_missing` | filled |
| 4e | detail: full trail returned | `test_success_loop...` | filled |
| 5 | Audit write: Core SOT/Analysis/memory side effect 0 | `test_audit_write_does_not_save_to_core_sot` (`_NoWriteCoreSotService` spy) | filled |
| 6 | Response `{candidate,gate,loop,stages}` + `audit_id` additive; ephemeral stages shape invariant | `audit_id` present on success+failure; ephemeral stages locked to 3 keys at `tests/test_writing_revise.py:528-529` (and exact-dict at `:678`,`:1006`) | filled |
| 7 | token/latency fields ABSENT — brief: "존재하면 회귀 실패" | summary: filled (8-key set); **detail top-level + detail stage rows: none** | **EMPTY — B1** |

Two empty cells (3c, 7) collapse into one blocking finding (B1): the **detail surface** (top-level payload + per-stage rows) has no over-strict guard for the contract-required absence invariants. The other three serialization surfaces (summary list row, ephemeral response stages, run/stage dataclass fields) are locked.

### 2. Implementation code

- `audit_hash.py`: `hash_text` (sha256 hex, `:19-20`), `finding_fingerprint` (deterministic JSON-sorted sha256 over type/severity/message/evidence/recommended_decision, `:23-30`), `package_pointer_ids` (sorted union of source_ref_ids + snapshot_id + document_id + version_id, `:33-41`). Shared by loop + audit so the `final_candidate_hash == last stage candidate_hash` invariant holds. Clean.
- `loop_audit.py`: `StoredLoopStage`/`StoredWritingLoopRun` are `frozen=True, slots=True` (`:35`,`:45`) → P5=A immutability is structural, not convention. `InMemoryWritingLoopAuditRepository.add` (`:77`) stores by id, never replaces. `WritingLoopAuditService.record` (`:112-143`) computes `final_candidate_hash=hash_text(final_candidate.text)` and `stages` via `_stored_stage`; `get` (`:148-154`) raises `WritingLoopAuditNotFound` on missing OR cross-project. Append-only + project isolation correct.
- `loop_audit_mongo.py`: `add` uses `insert_one` only — no replace/upsert (`:26-28`, comment "Append-only: insert, never replace"). Index `(project_id, created_at DESCENDING)` (`:17-20`) matches the list sort. `_doc`/`_run`/`_stage`/`_stage_doc` are field-for-field symmetric. **No round-trip regression exists** (see H1).
- `revise_gate.py`: `WritingLoopStage` (`:109-119`) gained `candidate_hash`/`finding_fingerprint`/`pointer_ids` as additive defaults. The `record()` closure (`:213-225`) reads `current_candidate` from the closure and stamps `hash_text(current_candidate.text)` at each stage boundary; revise stages pass `finding=` → fingerprint, retrieval stages pass `pointer_ids=package_pointer_ids(...)` (`:381`,`:391`). Traced all 5 termination paths (pass `:292`, terminal/not_eligible/budget/no_change `:297-346`, exception-carried `failed` `:246-249`/`262-265`/`280-283`/`328-332`/`395-399`): in every path `exc.candidate`/`result.candidate` is the same `current_candidate` whose text was hashed into `stages[-1]`, so `final_candidate_hash == stages[-1].candidate_hash` holds by construction for all paths, not just success.
- `main.py`: `_default_writing_loop_audit_service` (`:368-378`) is always available (in-memory default; Mongo on `CORE_SOT_MONGO_URI`) → P2=A "no run unaudited". create_app wiring `:1067-1069`. `_record_loop_audit` (`:2765-2777`) is invoked at exactly 5 sites (success `:2939`; 4 failures `:2813/2846/2887/2917`); pre-loop rejections (`validate_inputs`, pre-loop `build_context_package`) at `:2790-2803` raise `HTTPException` without auditing → over-strict guard valid. Verified that exceptions raised *inside* `run()` are wrapped by the loop into typed failures, so the bare `except` clauses at `:2790-2803` only fire pre-loop. Read endpoints `:2952-2977` honor `_require_project_exists` (404) + `WritingLoopAuditNotFound` (404).
  - **Pre-loop over-strict guard validated**: duplicate anchor → `WritingRevisionService.validate_inputs` raises `WritingRevisionError` (`revise.py:149`) → endpoint `:2790` → 400, no audit. `test_pre_loop_rejection_is_not_audited` pins this.

### 3. Public envelope / schema

Three serialization surfaces in `main.py`:

- **Summary list row** `_writing_loop_audit_summary_payload` (`:2386-2396`): exactly 8 keys. Locked by `test_writing_loop_audit.py:294-298` exact-set assertion. ✓
- **Detail trail** `_writing_loop_audit_payload` (`:2398-2416`): summary + run-level hashes/fingerprints + `final_candidate_text` + stage rows. **No key-set / absence lock.** ✗ (B1)
- **Ephemeral response stages** `_writing_stages_payload` (`:2379-2384`): exactly `{stage, ordinal, status}` — the new audit fields do NOT leak into the ephemeral response. Locked by `tests/test_writing_revise.py:528-529`. ✓

Response additive rule (boundary #6): success (`:2944-2950`) and all 4 failure envelopes carry `candidate/gate/loop/stages/audit_id` (+ their pre-existing error block). `audit_id` is purely additive. ✓

### 4. Adversarial mutation results (the load-bearing evidence for B1)

| Mutation | Surface | Suite result | Lock exists? |
|---|---|---|---|
| Add `"token_usage": {prompt,completion}` to detail top-level + `"candidate_text":"LEAKED_BODY"` to each detail stage row | detail (`_writing_loop_audit_payload`) | **12 passed (no bite)** | ✗ EMPTY |
| Add `"token_usage": 999` to summary row | summary (`_writing_loop_audit_summary_payload`) | **1 failed** (`test_retry_appends...` 8-key set) | ✓ locked |

Asymmetry demonstrated: the worker locked summary (8-key) and ephemeral stages (3-key) but not the detail surface. Brief §106 explicitly requires "존재하면 회귀 실패" for token/latency, and §102 requires stages to carry "hash 만" (no body) — both are contract-required "should NOT fire" branches with no tracing test on precisely the surface where B2 stage-level usage will land (follow-up §84).

### 5. Test suite (independently re-run)

- `tests/test_writing_loop_audit.py` → **12 passed** (matches worker claim).
- Writing focused (7 files) → **128 passed / 108 subtests** (matches).
- Full non-Mongo → **940 passed / 45 skipped / 209 subtests** (matches work_log/HANDOFF exactly).
- `py_compile` (all 6 changed files) OK; `git diff --check` clean. Post-mutation revert verified clean (`grep MUTATION` empty, `git diff --stat` back to 129 insertions on `main.py`).

### 6. Docs

- SoT header `v1.6.78` Approved; version-table row `:36` consistent with brief (P1–P5, retention directive, additive `audit_id`, side-effect-1, B2 deferred). No internal contradiction between SoT row and brief.
- CHANGELOG top entry (2026-07-13 v1.6.78) matches; HANDOFF Current Status / Owner Decisions / Verification / Project Structure updated (mentions `loop_audit(+mongo)`, `audit_hash`). work_log has the slice entry with reasoning.

## Issues / Risks

### Blocking (contract obligation)

**B1 — Detail trail surface lacks the contract-required forward-defense lock (boundary #7 + half of #3).**

- **Clause**: brief §106 "token/latency 필드는 이 슬라이스에 없다(B2 forward-defense — 존재하면 회귀 실패)"; brief §102 "candidate 본문 문자열은 detail의 최종 candidate에만 있고 중간 stage에는 hash만 있다." Both are explicit "should NOT fire" branches in the adopted regression boundary list.
- **Gap**: `_writing_loop_audit_payload` (`main.py:2398-2416`) — neither the top-level dict nor the per-stage row has a key-set / absence assertion. Summary (`:294-298`, 8-key) and ephemeral stages (`test_writing_revise.py:528`, 3-key) ARE locked, so the detail omission is an oversight, not a design choice.
- **Demonstrated**: injecting `token_usage` (top-level) + `candidate_text` (stage row) into the detail payload left all 12 tests green (no bite). Injecting the same field into the summary bit immediately.
- **Fix (trivial, ~3 lines)**: in `test_success_loop_persists_full_trail_and_returns_audit_id` (or a dedicated test), assert the detail top-level key set and each stage row key set, e.g.:
  ```python
  self.assertEqual(set(payload), {<expected detail keys>})
  for s in payload["stages"]:
      self.assertEqual(set(s), {"stage","ordinal","status","candidate_hash","finding_fingerprint","pointer_ids"})
  ```
- This is the only blocking finding. It does not affect production behavior (the code is correct today); it leaves the boundary unlocked against a future B2/over-zealous edit.

### Hardening recommendations (non-blocking, beyond the explicit 7 boundaries)

- **H1 — Mongo adapter has no round-trip regression.** Precedent v1.6.65 Gate finding ships `tests/test_gate_findings_mongo.py` (fake `_Collection`/`_Client` round-trip, runs in the standard suite — *not* live-Mongo). The brief cites the gate-finding store as the "채택된 기본값" (`:22`), so adopting its Mongo test is the natural completion. `MongoWritingLoopAuditRepository` (`loop_audit_mongo.py`) is structurally symmetric (`_doc`↔`_run`) but a field drift (e.g., a dropped key in round-trip) would not be caught. Recommend a fake-collection round-trip test mirroring `test_gate_findings_mongo.py`. (Work_log's "in-memory/Mongo 결정적 경로" claim addresses *live* testing, which is fairly unnecessary; it does not address this deterministic-fake gap.)
- **H2 — Only `pass` and `failed` loop_status terminations are explicitly asserted to leave an audit record.** The other 4 result statuses (terminal_decision/not_eligible/budget_exhausted/no_change) flow through one uniform audit site (`main.py:2939`) so are audited by construction; a per-status `loop_status` assertion on the audit record would pin them against a future conditional-skip regression.
- **H3 — Audit-write exceptions propagate uncaught.** `_record_loop_audit` (`main.py:2770`) calls `writing_loop_audit.record(...)` with no try/except. InMemory never raises; a Mongo `insert_one` failure (reachable only with `CORE_SOT_MONGO_URI`) would surface as a raw 500 and lose an otherwise-successful loop result. Spec-silent (brief does not address audit-write failure semantics); consistent with the repo-wide "Mongo repo doesn't wrap pymongo errors" pattern, but worth an owner decision on fail-loud vs. degrade-gracefully now that audit is a side-effect of every loop call.
- **Observation (no action)** — brief option-prose (`:32`) says "input/output candidate hash" per stage, but the canonical SoT row + regression boundary §102 + code use one `candidate_hash` per stage, with run-level `initial_candidate_hash`/`final_candidate_hash` providing the input/output envelope. Internally consistent and matches the `final==last-stage` invariant; the prose is looser than the locked contract. No contradiction.

## Verdict

**조건부 합격 (Conditional Pass)** — load-bearing reason: **B1**. The brief explicitly lists token/latency absence and bodyless stage rows as regression boundaries ("존재하면 회귀 실패" / "hash 만"), and the detail surface — the exact place B2 stage-level usage will be added — has no over-strict guard (demonstrated by mutation: contract-violating fields added to detail → suite stays green). Per the "boundary matrix has no empty cells" rule, this contract-required lock must be added before the slice closes.

Everything else passes: code matches contract literals; append-only/immutability/project-isolation/additive-`audit_id`/side-effect-0 are locked both directions; the summary and ephemeral surfaces are correctly forward-defended; suite re-runs match reported counts (12 / 128·108 / 940·45·209); docs consistent; compile + diff clean.

Closure condition: add the detail + stage-row key-set (or field-absence) assertion described in B1, then this record can be re-promoted to 합격.

## Outstanding items

- Worker did **not** commit (working tree uncommitted). Owner to authorize commit (likely bundled with B1 closure).
- B1 closure is a test-only change (no production-code change required — code is already correct).
- H1–H3 are discretionary; H1 (Mongo fake round-trip) is the most precedent-aligned.

## B1 closure + H1/H2 hardening (2026-07-13, worker follow-up)

Worker addressed the blocking finding and two hardening recommendations after this audit. Test-only; no production-code change (the code was already correct).

- **B1 closed** — `test_success_loop_persists_full_trail_and_returns_audit_id` now asserts the detail top-level exact 15-key set and each stage row exact 6-key set (`{stage,ordinal,status,candidate_hash,finding_fingerprint,pointer_ids}`). Re-ran the audit's own mutation: injecting `token_usage` (top-level) + `candidate_text` (stage row) into `_writing_loop_audit_payload` now **fails** (`1 failed, 12 passed`) where it previously stayed green; reverted clean (no `LEAKED`/`token_usage` residue). Boundary-matrix cells 3c and 7 (detail surface) are now filled.
- **H1 closed** — new `tests/test_writing_loop_audit_mongo.py` mirrors `test_gate_findings_mongo.py`: deterministic fake collection round-trip (`_doc`↔`_run` field-for-field), append-only insert (duplicate `_id` raises), newest-first (`created_at` desc) list, project isolation, stable index name `writing_loop_audits_by_project_created`.
- **H2 closed** — new `test_each_non_pass_200_status_leaves_a_record_with_that_status` parametrizes the remaining 4 success-site statuses (terminal_decision / not_eligible / budget_exhausted / no_change), asserting each leaves an audit record with the matching `loop_status` and `error_type=None`.
- **H3 (audit-write failure semantics)** — surfaced to owner; owner responded with a deeper redesign that **supersedes P2=A → P2=B (opt-in), SoT v1.6.79** (brief "P2 재개정"). Audit is now decoupled from the loop critical path: `persist_audit` request flag (default off, env-overridable), and the persist is try/except-isolated so a write failure returns the loop result with `audit_id=null` + `audit_error` — H3 is structurally dissolved (a persist failure can no longer break the loop outcome). New regressions: `test_opt_in_default_off_persists_nothing`, `test_env_default_enables_audit_without_request_flag`, `test_persist_failure_is_isolated_from_the_loop_result`. Note: P2=A-specific locks in *this* record (boundary 1a/1b "every termination audited", `test_every_termination`) are re-scoped to "audited **when persist is on**"; the H2 per-status test now posts with the flag set.

Re-run after B1 closure (v1.6.78): `tests/test_writing_loop_audit*.py` → 16 passed / 4 subtests; full non-Mongo → **944 passed / 45 skipped / 213 subtests**. After P2=B opt-in (v1.6.79): loop-audit focused → 19 passed / 6 subtests; full non-Mongo → **947 passed / 45 skipped / 215 subtests**; `git diff --check` clean.

**Verdict update**: B1 closure condition met → **합격 (Pass)** for the v1.6.78 contract obligation. H1/H2 hardening adopted; H3 resolved by the v1.6.79 opt-in redesign (independent re-verification of the v1.6.79 delta is a follow-up verifier target).

## Reproduction

```bash
# focused
python3 -m pytest -q -p no:cacheprovider tests/test_writing_loop_audit.py
# Writing focused
python3 -m pytest -q -p no:cacheprovider \
  tests/test_writing_revise.py tests/test_writing_retrieval.py tests/test_writing_report.py \
  tests/test_writing.py tests/test_writing_gate.py tests/test_writing_accept.py \
  tests/test_writing_loop_audit.py
# full non-Mongo (project convention)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider
# compile + whitespace
python3 -m py_compile services/application/app/writing/{audit_hash,loop_audit,loop_audit_mongo,revise_gate}.py services/application/app/main.py tests/test_writing_loop_audit.py
git diff --check

# B1 reproduction (expect: suite STAYS GREEN = lock missing)
#   edit main.py _writing_loop_audit_payload: add "token_usage": {...} and
#   "candidate_text": "X" to each stage row, then:
python3 -m pytest -q -p no:cacheprovider tests/test_writing_loop_audit.py   # 12 passed
# contrast (expect: 1 FAILED = summary IS locked):
#   add "token_usage": 999 to _writing_loop_audit_summary_payload, then:
python3 -m pytest -q -p no:cacheprovider tests/test_writing_loop_audit.py   # 1 failed
# revert both edits (grep MUTATION empty, git diff --stat main.py == 129 insertions)
```
