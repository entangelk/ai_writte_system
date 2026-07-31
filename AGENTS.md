# AGENTS.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Scope:** This file is intended for Codex-based contributors working in this repository.

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

- How to write the work log, user decisions, HANDOFF.md, and CHANGELOG.md: see [`docs/guides/records-and-handoff.md`](docs/guides/records-and-handoff.md).
- Independent verification of another worker's slice: see [`docs/guides/verification.md`](docs/guides/verification.md).

## 6. Commits / Git Workflow

**Checkpoint commits during work. Never push. Don't branch unless asked.**

Verification in this repo is adversarial: a regression-guard check requires temporarily reverting a fix (or mutating code) to confirm a test re-fails, then restoring it. A forgotten restore silently destroys or reverts the fix, and uncommitted working-tree state is not recoverable — a checkpoint commit is. Treat checkpoint commits as the safety mechanism against this, not as noise.

- **Commit checkpoints directly to the current branch (`main` by default)** during a slice, as needed. This is the expected default here — do not wait to be asked.
- **Keep the destructive mutation uncommitted.** The revert-to-test itself stays in the working tree, so a failed restore is one `git reset` / `git checkout` away and never lands as a broken commit.
- **Never `push`.** The owner pushes themselves.
- **Do not create a branch** unless explicitly asked. The default is solo work directly on `main`.
