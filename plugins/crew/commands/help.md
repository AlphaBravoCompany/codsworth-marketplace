---
description: "Explain the crew plugin and how to use it"
argument-hint: ""
allowed-tools: []
---

# Crew Help

Render this help text to the user verbatim.

---

# Crew — a dedicated dev agent

Throw an AI dev at a problem and have it own the outcome. Crew is a single command that gathers context, optionally proposes a plan, then executes against real systems (SSH, infra, code edits, deploys, features), and verifies the outcome by observation — not by inference.

## How to use it

```
/crew:do <whatever you want>
```

The intent is free-form. You don't pick a task type. Crew classifies it.

Examples:

```
/crew:do figure out why staging login is broken since yesterday

/crew:do make sure Shiro can run properly on Azure on RHEL — I want to deploy

/crew:do get the airgap bundle pulling all packages until it works

/crew:do rotate the prod database credentials and update all the services

/crew:do add a /workloads page to the embedded dashboard
```

## Flags

- `--paranoid` — doubles depth contract; spawns N=3 worker variants in parallel from the start; runs the critic twice with different framings.
- `--yolo` — skips the plan-approval checkpoint. **Forbidden against production** (crew enforces this regardless of flag).
- `--scope=light|deep` — override scope (default: router decides).

## What happens

1. **Router** classifies the intent — initial mode, scope, side-effect surface, whether a plan checkpoint is needed.
2. **Scout** gathers context — codebase, memory, recent git history, targeted web research, the verification surface ("what would prove this is real?"), and an honest assumption ledger. Bounded budget (25 tool calls / 5 min, doubled in paranoid).
3. **Worker** does the work, switching between modes as the task evolves:
   - `investigating` — forming hypotheses, reading systems
   - `planning` — proposing a path forward
   - `executing` — applying changes to real systems
   - `verifying` — proving the outcome with concrete commands
   - `stuck` — declaring it explicitly rather than thrashing
4. **One checkpoint** (only for side-effecting tasks) — the worker proposes a plan in chat, you approve / revise / cancel.
5. **Critic** runs after execution — adversarial check, must produce an evidence ledger of commands it actually ran.
6. **Fresh-eyes** runs in parallel with the critic — blind to everything except the original intent and current state. Catches drift the critic and worker can't see.
7. **Debrief** in chat — what was done, what changed along the way, what was verified, open follow-ups.

## On stuck

When the worker declares stuck (3 reflections without progress on a step), crew spawns **N=2-3 parallel worker variants** with deliberately different framings ("treat this as a config issue," "treat as an environment issue," "treat as a permissions issue"). A judge synthesizes their findings. This replaces the single-worker-reading-its-own-reflections loop that the research showed degenerates.

## Where state lives

Everything is in `.crew/runs/<run-id>/`:

- `state.json` — phase, status, configuration
- `brief.md` — scout's output
- `plan.md` — the worker's plan (if checkpoint phase ran)
- `journal.md` — append-only log of every significant action
- `reflections.md` — what failures taught the worker
- `verification.md` — the worker's own verification pass
- `critic-verdict.md` — adversarial verdict with evidence ledger
- `fresh-eyes-verdict.md` — blind drift check with evidence ledger
- `followups.md` — out-of-scope things noticed during the run
- `escalation.md` — only present if the worker got stuck

You don't have to read any of these. Plan and debrief render in chat. The files exist for resume and audit.

## Other commands

- `/crew:resume <run-id>` — pick up an interrupted run
- `/crew:list` — show recent runs
- `/crew:cancel [<run-id>]` — cancel an active run
- `/crew:help` — this text

## Host registry (optional)

If you have `.crew/hosts.yml` in the project, crew reads it and uses host tags. Example:

```yaml
hosts:
  staging:
    ssh: ubuntu@staging.example.com
    tags: [dev, azure, rhel]
  prod:
    ssh: deploy@prod.example.com
    tags: [production, azure, rhel]
```

Worker references host tags rather than re-learning hosts every run. Production-tagged hosts force plan approval.

## What crew is NOT

- Not a feature-builder pipeline (that's foundry/forge)
- Not a phase planner (that's gsd)
- Not a CrewAI workflow — same name, different thing

Crew is "I have a problem, go own it."
