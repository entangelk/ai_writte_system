# Records & Handoff — writing guide

**How to record work in this repo.** Applies to every contributor — Claude Code (via `CLAUDE.md`) and Codex (via `AGENTS.md`). The standing rule is inline in those files (§5): *always update these files after completing tasks, no exceptions.* This doc is the reference for *how* to write each record. For independent verification of another worker's slice, see `verification.md` in this same folder.

## Work Log
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
- **Mutations go in as a table, not a tally.** `verification.md` §"Mutation
  testing" requires recording *which mutation hit which cell*; the work log is
  where that pairing lands. "5종 전부 재실패" is not reproducible — an
  independent verifier re-deriving the mutations will pick slightly different
  forms and get different cell counts, and then cannot tell whether the gap is
  the mutation's scope or a weak guard (measured: Slice 8.4, 2026-08-04, three
  of five counts diverged for exactly this reason). One row per mutation:
  **the diff applied · the file:line · the cells that failed, by name**.

## User Decisions and Rationale
- When a user's preference, decision, constraint, or rationale affects requirements, scope, architecture, design, behavior, or implementation direction, summarize that decision in `docs/daily_logs/YYYY-MM-DD/work_log.md`.
- Preserve the user's intent, the selected direction, and relevant tradeoffs so later workers can understand why the project took that direction. Do not transcribe the conversation.
- When a user decision directly drives a major design or feature change recorded in `CHANGELOG.md`, include a concise note about that decision and rationale in the changelog entry.
- Do not record conversational decision history in `HANDOFF.md`; keep it focused on current actionable development state.
- If a later request conflicts with a recorded user decision, rationale, or established design direction, identify the conflict and ask the user which direction is now canonical before implementing the conflicting change.

## HANDOFF.md

**HANDOFF.md is a snapshot, not a log. Editing it is mostly *deleting*.**

Purpose: what the next worker needs in order to start working *right now*. If a
line would not change what they do today, it does not belong here.

**There is no length cap — length is a symptom, not the rule.** A long HANDOFF
can be entirely correct, and some entries need detail to be usable. A hard cap
would either block content that earns its place or, worse, invite someone to
meet the number by collapsing paragraphs into one unreadable line. What actually
goes wrong is *duplication of finished work*, and that is what to check for.

**Self-audit trigger.** When the file passes **~200 lines** — and roughly every
100 lines after that — stop before adding more and audit it:

```bash
wc -l HANDOFF.md
```

Walk the file section by section and ask:

1. Would this change what the next worker does **today**? If not, delete it.
2. Is this a completion narrative? It is already in `work_log.md`, the SoT
   version log, and `CHANGELOG.md` — delete it here.
3. Is it still true? Dated observations expire; re-check or drop them.
4. Is a long section long because the content genuinely needs it? Then keep it.
   Passing the trigger is not a failure — failing to look is.

Then record the result in the header line of `HANDOFF.md`:

```markdown
> 마지막 자가 검수: YYYY-MM-DD · N줄
```

That line is how the next worker (and you, next time) can tell whether the
trigger is actually being honored instead of quietly scrolling past it.

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

## CHANGELOG.md
- Update on major design or feature changes (not every small edit)
- Top table links to daily_logs for detail
