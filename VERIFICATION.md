# VERIFICATION.md

**Independent verification policy.** Applies to every contributor in this repo — Claude Code (via `CLAUDE.md`) and Codex (via `AGENTS.md`). Verification here is always *independent*: it audits a slice the verifier did not produce themselves. This doc is the canonical home for that policy; `CLAUDE.md` §5 and `AGENTS.md` §5 link here instead of inlining.

## When to write a verification record

- **Trigger**: when the user explicitly requests verification of work done by another worker (human or AI) — phrases like "검증해줘", "verify this", "의심하고 또 의심해봐줘", "check that the implementation matches the spec", or any equivalent ask to audit a finished/in-progress slice against its specification.
- **Do not** write a verification record for routine self-checks you perform while implementing your own change. Verification records exist to give the owner an independent, durable audit trail of work they didn't do themselves.
- **Path**: `docs/verifications/YYYY-MM-DD/<slug>.md` (date-based subdirectory, mirroring `docs/daily_logs/`). Use a short slug describing the subject under verification (e.g. `rule_2_implementation`, `gate_promotion_flow`).

## Required sections

- Subject metadata — date, requester, verifier, target slice/artifact, canonical spec reference (file + version), source of the work being verified (commit hash, branch, or "working tree, uncommitted").
- Scope — the discrete surfaces being checked (e.g. spec contract, implementation code, regression tests, fixtures, public envelope/schema, full test suite, smoke runs).
- Methodology — how each surface is verified, with the exact commands used. Anything a future reader cannot reproduce from this section is not verified.
- Findings — one subsection per surface in Scope; cite file:line for every claim. State both what was checked and what was observed.
- Issues / Risks — split into two clearly labeled groups:
  - Blocking (contract obligations): spec violations, untraced boundary branches, missing over-strict guards, internal contract contradictions. These determine the verdict — see "boundary matrix has no empty cells" below.
  - Hardening recommendations (non-blocking): tests or contract clauses that are *not* required by the current spec but would make the boundary more robust if added (e.g. an under-tested edge the spec does not yet enumerate, a fixture that could cover a near-miss value). Surface these as named, actionable candidates — not as reasons to fail the slice.
- Verdict — pass / conditional pass / fail, with the load-bearing reasons listed.
- Outstanding items — operational state that affects the owner's next step (uncommitted work, awaiting publication authorization, blocked downstream tasks). Keep this distinct from "Issues" — these are not defects.
- Reproduction — the minimal command sequence that re-runs the verification end-to-end.

## Verify the spec/implementation/test/fixture stack as one whole — not just "did it run"

- **Scope the contract read before opening it**: large spec documents grow over time, and reading every page each verification is both noisy and expensive — and worse, buries boundary clauses among unrelated rules. Before opening anything, build the *canonical contract scope* for the slice: which sections of which documents and which schema files actually govern the surface under verification. Typical anchors: the rule/feature section in the canonical plan (e.g. plan §6 Rule X), any sub-section it cross-references (policy structure, schema definition, decision boundary clauses), the matching changelog entry in the plan's version log, the relevant schema file(s) under `schemas/`, and any HANDOFF Active Decisions that name this rule. Follow each cross-reference the in-scope spec makes, but don't widen beyond that chain — unrelated rules, prior plan iterations, and ideation drafts are out of scope unless the in-scope spec explicitly chains back to them. Inside each anchored location read end-to-end (don't skim); boundary clauses are often single sentences buried mid-paragraph, and the cost saving comes from scoping, not from skimming.
- **Build the boundary matrix from the scoped reading**: every "should fire" branch, every "should NOT fire" branch, every literal (finding type, severity, decision_status, next_action name, policy path, threshold name, exit code). That matrix becomes the lock list the rest of the verification must fill in. A verification that starts with "let me check the code" instead of "let me scope the contract" cannot detect contract gaps — it can only check the code against itself.
- **Cross-check the contract against itself**: a canonical spec can disagree across its own sections — e.g. rule prose names one policy path while the policy structure section defines another; a changelog entry locks a boundary the rule body forgot to mention; a success/failure table contradicts the rule condition. Internal contract inconsistency is a **blocking** finding, not a stylistic nit — the contract itself is defective and must be reconciled (by owner decision if needed) before the slice can close.
- **The boundary matrix has no empty cells — empty cells are blocking findings**: every branch the *contract requires* — both "should fire" and "should NOT fire" — must map to a named regression test, and where applicable to a fixture entry. Trace each test function back to the clause it protects. **An untraced contract-required branch is a blocking finding regardless of the green bar.** Never reframe a missing contract-required lock (over-strict guard etc.) as "future risk", "future enhancement", "보강 후보", "후속 보강 후보", or "차단 사유 아님" — those phrases are the exact failure mode this guideline exists to prevent. If a contract-required lock is missing, the verdict is "조건부 합격" or "불합격" until the lock is added, not "합격 with risks". This blocking rule covers only contract obligations; genuine hardening candidates that go *beyond* the spec belong in "Hardening recommendations" above and do not fail the slice.
- **Spec-silent-but-code-enforced is a contract gap, not an implementation detail**: if the code rejects (or accepts) something the contract never explicitly addresses (e.g. the code excludes `informational`-mixed traces while the contract prose only excludes `must`-mixed), surface it as a contract amendment request before the slice can close. Either the code is over-restrictive (relax it) or the contract is incomplete (amend it and add the matching regression) — picking silently leaves the boundary unlocked and turns the next verifier into a guesser. Resolving the ambiguity is part of the slice, not after it.
- Spec ↔ implementation consistency: every literal in the spec must appear unchanged in the code. Don't accept paraphrase.
- **Test code is part of the audit subject, not the auditor**: a passing test suite is necessary but not sufficient. Read each new test and confirm: (a) the assertion actually pins the contract — not an unrelated byproduct, (b) under-strict guard exists (the reported bug can re-fail this test), (c) over-strict guards exist for every "should NOT fire" branch in the spec, (d) parametrized cases cover every enumerated boundary value, not just one sample, (e) assertions target the public surface a caller agent depends on (envelope, schema, finding payload) rather than internal helpers.
- Fixture grounding: when a fixture carries a `source_manifest`, recompute `sha256sum` against the manifest. Do not trust the manifest's claim.
- Schema / contract self-discovery: when the project exposes a `schema` / introspection command, verify the new literal appears there, not only in the code that emits it.
- Smoke run vs. envelope claim: when the work log or HANDOFF reports envelope counts (e.g. `high=N, medium=M`), re-run the smoke and compare numbers directly. Reported numbers that nobody recomputed are unverified.

## Writing principles

- Independent: do not copy the verified worker's claims unchecked. Re-derive each claim from primary sources (plan, code, tests, smoke output).
- Skeptical: explicitly check both under-strict (the bug can reappear) and over-strict (a normal case is wrongly flagged) directions where applicable.
- Adversarial: treat the verified worker's claims as hypotheses to *refute*, not confirm. Actively search for the input, edge case, or contract clause that breaks the claim before accepting it. Default stance is "wrong until I fail to break it", not "looks right".
- Cite primary sources, not summaries. Prefer `file:line` over "the work log says X".
- State the verdict directly. Conditional pass is allowed but must name the condition.
- Never conflate "the test suite is green" with "the test suite verifies what the spec demands". Make the distinction visible in the record.

## Relation to other documents

- Verification records are independent audit artifacts. Do not move their content into `work_log.md`, `HANDOFF.md`, or `CHANGELOG.md`.
- If verification surfaces a new user decision (e.g. owner authorizes publication after seeing the record), that decision still flows to `work_log.md` per the "User Decisions and Rationale" rule.
- If verification fails, the verifier does not silently fix the defect. Surface the finding to the user and let them decide next steps.
