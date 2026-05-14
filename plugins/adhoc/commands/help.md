---
description: Show the adhoc plugin commands and how the methodical-mode hook works
---

The user wants help with the adhoc plugin. Reply with exactly this message — verbatim, no additions, no embellishment:

```
adhoc — methodical-mode for ad-hoc Claude work (v0.2.0)

WHAT IT DOES
  Always-on UserPromptSubmit hook prepends a methodical pre-response checklist
  to every user turn: restate the task, mark assumptions VERIFIED/UNVERIFIED,
  Read Floor (read code before editing), Approach Deliberation (>=2 candidates),
  Blast Radius (grep callers), Stall Check (anti-spin), Competing Hypotheses
  (for bugs), Goal-Driven Execution (verifiable success criteria), Restraint
  Check (no over-engineering). Stops the race-to-an-answer pattern.

  Always-on Stop hook enforces four gates after the response is drafted:
    (a) Citations  — file:line citations must be backed by Read/Grep this turn
    (b) Uncertainty — blocks "not verified" / "haven't checked" / "I assumed"
    (c) Grounding  — codebase questions require a Read/Grep/Glob this turn
                     (no general-knowledge fallback)
    (d) Critic     — substantive responses (>500 chars) must pass the
                     adhoc:pre-stop-critic subagent's verdict before Stop

COMMANDS — methodical-mode (UserPromptSubmit hook)
  /adhoc:status            Show current methodical-mode state
  /adhoc:on                Re-enable methodical-mode for this session
  /adhoc:off               Disable methodical-mode for the rest of this session
  /adhoc:casual            Skip methodical-mode for the NEXT turn only — auto-reverts
  /adhoc:deep              Heavier methodical analysis pass (skill, read-only)
  /adhoc:help              This message

COMMANDS — Stop-hook gates
  /adhoc:citations-on      Enable file:line citation verifier (default)
  /adhoc:citations-off     Disable citation verifier
  /adhoc:uncertainty-on    Enable uncertainty-tell scanner (default)
  /adhoc:uncertainty-off   Disable uncertainty-tell scanner
  /adhoc:strict-on         Enable grounding audit + critic gate (default)
  /adhoc:strict-off        Disable grounding audit + critic gate
  /adhoc:trust-me          One-shot bypass of grounding + critic gates for the
                           NEXT turn only — auto-consumed. Uncertainty + citation
                           gates stay on.

SUBAGENTS
  adhoc:second-opinion     Independent fresh-context critique of a plan / approach.
                           User-invoked. Heavier review for major decisions.
  adhoc:pre-stop-critic    Hook-invoked critic that reviews each substantive
                           response before Stop is allowed. Lightweight. Emits
                           the sentinel [adhoc:pre-stop-critic-output] so the
                           Stop hook does not recurse on critic output.

STATE FILES (all under ~/.claude/)
  .adhoc-state              methodical-mode injector: absent/"on" / "off" / "casual"
  .adhoc-citations-mode     gate (a): absent/"default" / "off"
  .adhoc-uncertainty-mode   gate (b): absent/"default" / "off"
  .adhoc-strict-mode        gates (c) and (d): absent/"default" / "off"
  .adhoc-trust-me           one-shot bypass file for (c) and (d) — consumed on read
  .adhoc-citations-log.jsonl   per-turn gate decisions (audit log)

WHEN TO RELEASE-VALVE
  /adhoc:casual    For trivial chitchat where the methodical preamble is pure
                   noise. Skips the UserPromptSubmit injection for one turn.
  /adhoc:trust-me  For genuine general-knowledge questions ("what's a closure?")
                   that have nothing to do with this codebase. Skips strict
                   gates (c) + (d) for one turn — citation + uncertainty gates
                   still run.
  /adhoc:off       For long pairing sessions where you've calibrated and the
                   preamble repeats itself. Silences the UserPromptSubmit
                   injection for the rest of the session. Stop gates keep firing.
  /adhoc:strict-off + /adhoc:uncertainty-off + /adhoc:citations-off
                   Nuclear: disables ALL Stop gates for the session.

DESIGN NOTES
  - Default is always-on enforcement. If you remembered to invoke it, you
    wouldn't need it — the point is that it fires when you forget.
  - Citation, uncertainty, and grounding gates use deterministic regex.
    Critic gate spawns an opus/medium subagent on substantive responses.
  - Recursion guard: critic responses begin with the sentinel marker
    [adhoc:pre-stop-critic-output] so the Stop hook does not gate the critic.
  - All gate decisions are logged to .adhoc-citations-log.jsonl for
    post-hoc auditing of false positives / negatives.
```

Do not add anything before or after. Do not summarize. Do not paraphrase.
