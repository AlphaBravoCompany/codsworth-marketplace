# adhoc — methodical-mode for Claude Code

> **Stops Claude from racing.** An always-on UserPromptSubmit hook injects a methodical pre-response checklist into every turn — restate the task, mark assumptions VERIFIED or UNVERIFIED, cite CLAUDE.md and memory rules in play, surface alternatives, confirm before editing.

Forge plans. Foundry builds. **adhoc thinks before it answers.**

---

## Why adhoc

Most ad-hoc work with Claude looks like this:

> *"Add rate limiting to /auth/login."*
>
> Claude reads three files, installs a package, edits four more, runs the tests, declares done. Ninety seconds later you notice it ignored the rate limiter you already had, applied middleware to the wrong scope, and silently broke a test you weren't watching.

The model isn't dumb. It's **trained to feel productive** — start, do, finish. The default disposition is racing. CLAUDE.md and memory don't fix it because they're passive: read once, agreed with, quietly ignored when the next prompt feels simple.

adhoc fixes it the only way that actually works: **at the runtime, not the prompt.** Every user turn fires a hook that prepends a checklist Claude must walk before responding. The model can't ignore it because it isn't being asked to remember — it's being handed structure on every prompt.

---

## What it does

A `UserPromptSubmit` hook fires before Claude sees your message. The hook emits a methodical preamble that becomes part of the prompt context. Claude must walk the checklist out loud (briefly) before answering.

```
[adhoc:methodical-mode active]

1. RESTATE       — One-sentence statement of what's being asked. Ask if ambiguous.
2. ASSUMPTIONS   — List them. Mark VERIFIED (you checked) or UNVERIFIED (inferring).
                   Don't proceed on UNVERIFIED for non-trivial work.
3. RULES         — Cite any CLAUDE.md / memory rule that applies, by name.
4. ALTERNATIVES  — Surface 2 approaches with tradeoffs before recommending.
5. CONFIRM       — Multi-file or hard-to-revert? Plan first, wait for ack.

Default disposition: methodical over fast.
A wrong answer delivered quickly is still a wrong answer.
```

That's the whole engine. Everything else is escape hatches and heavier modes.

---

## Install

```
/plugin marketplace add AlphaBravoCompany/codsworth-marketplace
/plugin install adhoc@codsworth
```

After install, every new conversation runs methodical-mode by default. No further setup.

---

## Commands

| Command | Effect |
|---|---|
| `/adhoc:status` | Show current state (`on` / `off` / `casual`) |
| `/adhoc:on` | Re-enable methodical-mode for this session |
| `/adhoc:off` | Silence methodical-mode for the rest of this session |
| `/adhoc:casual` | Skip methodical-mode for the **next single turn** — auto-reverts to on |
| `/adhoc:deep` | Run a heavier methodical analysis pass (read-only skill) |
| `/adhoc:help` | Inline reference |

---

## /adhoc:deep — when the preamble isn't enough

For tasks that are non-trivial, ambiguous, or architectural, the always-on preamble is a floor. `/adhoc:deep` is a heavier pass — a read-only skill that walks Claude through seven structured steps:

1. **Restate** — what's being asked, what was said, what was likely meant, what else it could mean
2. **Assumptions** — at least 5, each marked VERIFIED or UNVERIFIED, each verified or asked
3. **Prior art** — search the codebase, CLAUDE.md, memory, recent git history for related decisions
4. **Alternatives** — at least 3 distinct approaches with concrete tradeoffs
5. **Edge cases** — failure modes of the preferred approach
6. **Recommend** — one approach, with reasons and rejected alternatives cited
7. **Stop-points** — where Claude will pause for confirmation during execution

Output is a written analysis. **Zero code changes.** You decide what to do with it.

Use it before architectural decisions, refactors that touch >2 files, ambiguous bug reports, or any time you'd say "think hard about this."

---

## adhoc:second-opinion — independent critique

A subagent with **no prior conversation context**. Spawn it via the Agent tool when you want a take from a Claude that hasn't anchored on the framing you've been working with.

```
Agent({
  subagent_type: "adhoc:second-opinion",
  description: "Review the migration approach",
  prompt: "Problem: ... Proposed approach: ... Constraints: ... Files: ..."
})
```

Returns a written critique with these sections:

- **Agreements** — what the spawner got right (calibrates the rest)
- **Disagreements** — where the reviewer would have decided differently, with code citations
- **Missed considerations** — edge cases, hidden assumptions, prior art the spawner skipped
- **Alternative approach** — if the reviewer has a materially different one
- **Verdict** — `CONCUR` / `CONCUR WITH CAVEATS` / `PUSH BACK` / `WRONG SHAPE`

Use it before merging a non-trivial PR you authored with Claude, or any time the conversation has been long and you want fresh eyes.

---

## State management

State is stored in a single file: `~/.claude/.adhoc-state`

| File contents | Behavior |
|---|---|
| absent | methodical-mode **on** (default) |
| `off` | silenced for the session |
| `casual` | skipped on the next prompt, then auto-deleted (one-turn release valve) |

The toggle commands write/delete this file. The hook reads it before deciding whether to inject. No daemons, no background state.

---

## When to release-valve

The default is intentional. If you remembered to invoke it, you wouldn't need it. That said:

- **`/adhoc:casual`** — for trivial questions where the preamble is pure noise. Examples: *"what's the date,"* *"rename this variable,"* *"format this JSON."*
- **`/adhoc:off`** — for long pairing sessions where you've already calibrated and the preamble is repeating itself. Re-enable with `/adhoc:on` when you start a new task.

Don't disable it because the preamble feels chatty. **That's the working state.** Disable it when the preamble has stopped adding signal.

---

## Tuning

Three knobs you might want later:

1. **The preamble itself** — `scripts/inject.sh`. Wording is opinionated. Soften, sharpen, or shorten to taste.
2. **Always-on default** — to flip to off-by-default, change the script to require an opt-in state file instead of treating absence as on.
3. **Project-scoped state** — currently `~/.claude/.adhoc-state` is global across all projects. Swap to `${CLAUDE_PROJECT_DIR}/.adhoc-state` in the script for per-project state.

---

## Uninstall

```
/plugin uninstall adhoc@codsworth
rm -f ~/.claude/.adhoc-state
```

---

## What this isn't

- **Not a replacement for plan mode.** Plan mode (`Shift+Tab`) is a *constraint* — it blocks edits. adhoc is *guidance* — it shapes the response. They compose: methodical-mode + plan mode = think, plan, confirm, execute.
- **Not a replacement for Forge or Foundry.** Those are for spec'd, contracted work with verification phases. adhoc is for the gaps between — the small asks, the exploratory bugs, the *"can you take a look at this?"* turns where you don't want to spin up a full spec.
- **Not a memory system.** adhoc doesn't *learn* — it enforces. Pair it with your CLAUDE.md and persisted memory; adhoc is the runtime that makes Claude actually look at them.

---

## License

MIT. Same as the rest of the Codsworth marketplace.
