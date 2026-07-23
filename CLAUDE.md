# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.
- If you detect a contradiction within a spec doc, or across spec docs, surface the contradiction to the user and ask which side is canonical. Never silently pick a side.
- At the start of a project (or when entering an unfamiliar repo), check whether a spec-precedence tree for conflicting sources exists. If it's absent, recommend defining one before deeper work — without it, future spec conflicts collapse into ad-hoc judgment calls.

### Owner decision brief (kickoff)

When implementation cannot start without an owner-level decision (architecture, contract literal, scope cut, dependency choice, policy direction — anything where picking silently would commit the owner to a path they didn't choose), stop and produce a **decision brief** before coding. Do not improvise a choice and continue.

Required structure (mirror `docs/plans/03-index-sync-outbox-decisions.md`):
- **Decision needed** — one sentence: what choice is blocking implementation, and why it can't be derived from existing spec/precedent.
- **Options table** — every realistic option as a row, with columns `선택지 | 설명 | 장점 | 단점`. Don't pre-filter to your preferred option; the owner may see merit in a row you'd dismiss.
- **Recommendation + reason** — name the option you'd pick and why, tied to the project's current phase/constraints (e.g. "로컬 1인 프로젝트 단계", "정본 보존 정책"). A menu with no steer is not a brief.
- **Follow-up considerations** — doors this decision should leave open (e.g. a schema field kept general for a later event source).
- **Deferred / out of scope** — explicitly listed, so the owner knows what is *not* being decided in this slice.

After the owner decides:
- Record the decision and rationale in `docs/daily_logs/YYYY-MM-DD/work_log.md` per "User Decisions and Rationale" in §5.
- If the decision sets a contract literal or boundary, reflect it in the canonical plan / schema before or alongside implementation.

A brief is for genuine forks. Don't manufacture one for questions answerable from spec, precedent, or a 30-second grep — that's Think Before Coding, not a brief.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

### Pattern sweep before declaring fix complete

When fixing a defect, spend ~30 seconds grepping for the same root-cause pattern in adjacent functions / files before marking the fix done. Bugs are rarely solo — the same misunderstanding tends to repeat in places nobody reported yet.

- After fixing `f()`, grep for the symptom signature (function call, magic value, naive UTC, etc.) repo-wide.
- If the pattern is found elsewhere: either fix it inline (if scope-trivial) or document it as a tracked debt with file:line. Never silently skip.
- For each discovered location, run `git blame` on that line for one-line context — knowing *why* the pattern was placed there often changes the fix decision (intentional vs accidental).
- The 30-second budget is on purpose — this is a sanity sweep, not a refactor. Anything deeper goes to a separate task.

### Two-directional regression guards

A regression test should fail in *both* directions, not just one.

- **Under-strict guard**: if the pre-fix bug is reintroduced, the test must re-fail.
- **Over-strict guard**: if an over-correction breaks a normal case (e.g. someone applies `+1` where the original cancelation was intentional), the test must also fail.
- State both directions in the test docstring or assertion names so future readers (and future-you) can see what's being locked.

### Minimum Verification by Artifact Type

- **Documentation-only changes**: verify affected links, references, stated versions, and precedence claims where applicable; run repository-supported diff or formatting checks.
- **Code changes**: when behavior changes, add or update regression tests first; run focused tests for the changed behavior, then the relevant broader suite before completion.
- **Public interfaces or structured contracts**: when changing CLI output, APIs, configuration formats, schemas, generated metadata, or similar contracts, verify the behavioral tests and any affected examples, validation artifacts, introspection output, or contract files that exist in the project.
- If a named verification surface does not exist in the current project, state that clearly and use the closest available verification rather than adding unrequested infrastructure.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## 5. Work Logs & Handoff

**Always update these files after completing tasks. No exceptions.**

### Work Log
- Path: `docs/daily_logs/YYYY-MM-DD/work_log.md`
- Follow the style of existing logs in `docs/daily_logs/`

**Required sections:**
- Goals — specific objectives for the day
- Completed work — for each task: description, files changed, key changes, effect
- Issues found — problem / cause / resolution / outcome
- Decisions — what was decided / why / tradeoffs
- Next steps

**Writing principles:**
- Be specific: not "fixed it" but "what was changed and how"
- Include reasoning: why this approach was chosen
- State the outcome: what effect the change had
- Write immediately after completing work, while details are fresh

### User Decisions and Rationale
- When a user's preference, decision, constraint, or rationale affects requirements, scope, architecture, design, behavior, or implementation direction, summarize that decision in `docs/daily_logs/YYYY-MM-DD/work_log.md`.
- Preserve the user's intent, the selected direction, and relevant tradeoffs so later workers can understand why the project took that direction. Do not transcribe the conversation.
- When a user decision directly drives a major design or feature change recorded in `CHANGELOG.md`, include a concise note about that decision and rationale in the changelog entry.
- Do not record conversational decision history in `HANDOFF.md`; keep it focused on current actionable development state.
- If a later request conflicts with a recorded user decision, rationale, or established design direction, identify the conflict and ask the user which direction is now canonical before implementing the conflicting change.

### HANDOFF.md

**HANDOFF.md is a snapshot, not a log. Editing it is mostly *deleting*.**

Purpose: what the next worker needs in order to start working *right now*. If a
line would not change what they do today, it does not belong here.

**Hard limits — check these before you commit, they are not suggestions:**

```bash
wc -l HANDOFF.md                              # must be <= 150
awk '{print length}' HANDOFF.md | sort -rn | head -1   # must be <= ~400
```

Over the limit means **prune**, not reflow. The limits exist because an
unreadable snapshot is the same as no snapshot.

**The rule that keeps getting broken — read this one twice:**

- **Never append a "…완료" paragraph to Current Status.** Finishing a slice is not
  a status update. Status is what the system *is now*, not what you did.
- When you finish a slice, the HANDOFF edit is: **delete** what stopped being
  true, **rewrite** the affected section, and put the narrative in `work_log.md`.
- Completion narratives already live in three places — `work_log.md`, the SoT
  version log, and `CHANGELOG.md`. A fourth copy here is pure duplication, and it
  is what buries the parts that actually matter.
- Measured failure this rule exists for (2026-07-23): the file had reached **366
  lines, 81 completion markers, and a 4811-character single line**, because
  slice after slice appended its own summary and nobody deleted. Every one of
  those entries was already in the SoT log and CHANGELOG.

**Never record machine-local observations as project facts.** Ports, container
IPs, absolute host paths, and "the server is up on X" are true of *your* machine
at *this* moment; this project moves between dev machines. State what the repo
guarantees (`docker-compose.yml`, `.env.example`) — or, if you must record an
observation, mark it explicitly: "on this machine, as of <date>".
Measured failure (2026-07-23): HANDOFF recorded Chroma as running on 8001. 8001
was a *different project's* container; following that note would have pointed a
test that creates and deletes collections at another project's vector store.

Belongs here:
- Current system state, active drafts, and anything blocking right now
- Traps and operational gotchas the next person would otherwise walk into
- Open debts and pending owner decisions, with `file:line`
- "Next Tasks" — short, prioritized, immediately actionable
- Project structure map; MCP interface table when tools/resources change

Does not belong here:
- Completed work, past milestones, fixed bugs, superseded hypotheses
- Conversational decision history (that is `work_log.md`)
- Verification narratives (that is `docs/verifications/`)
- Numbers nobody re-measured today

If a newer note supersedes an older one, rewrite the section — never stack both.

### CHANGELOG.md
- Update on major design or feature changes (not every small edit)
- Top table links to daily_logs for detail

### Verification Records
- **Trigger**: when the user explicitly requests verification of work done by another worker (human or AI) — phrases like "검증해줘", "verify this", "의심하고 또 의심해봐줘", "check that the implementation matches the spec", or any equivalent ask to audit a finished/in-progress slice against its specification.
- **Do not** write a verification record for routine self-checks you perform while implementing your own change. Verification records exist to give the owner an independent, durable audit trail of work they didn't do themselves.
- **Path**: `docs/verifications/YYYY-MM-DD/<slug>.md` (date-based subdirectory, mirroring `docs/daily_logs/`). Use a short slug describing the subject under verification (e.g. `rule_2_implementation`, `gate_promotion_flow`).
- **Required sections**:
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
- **Verify the spec/implementation/test/fixture stack as one whole — not just "did it run"**:
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
- **Writing principles**:
  - Independent: do not copy the verified worker's claims unchecked. Re-derive each claim from primary sources (plan, code, tests, smoke output).
  - Skeptical: explicitly check both under-strict (the bug can reappear) and over-strict (a normal case is wrongly flagged) directions where applicable.
  - Adversarial: treat the verified worker's claims as hypotheses to *refute*, not confirm. Actively search for the input, edge case, or contract clause that breaks the claim before accepting it. Default stance is "wrong until I fail to break it", not "looks right".
  - Cite primary sources, not summaries. Prefer `file:line` over "the work log says X".
  - State the verdict directly. Conditional pass is allowed but must name the condition.
  - Never conflate "the test suite is green" with "the test suite verifies what the spec demands". Make the distinction visible in the record.
- **Relation to other documents**:
  - Verification records are independent audit artifacts. Do not move their content into `work_log.md`, `HANDOFF.md`, or `CHANGELOG.md`.
  - If verification surfaces a new user decision (e.g. owner authorizes publication after seeing the record), that decision still flows to `work_log.md` per the "User Decisions and Rationale" rule.
  - If verification fails, the verifier does not silently fix the defect. Surface the finding to the user and let them decide next steps.
