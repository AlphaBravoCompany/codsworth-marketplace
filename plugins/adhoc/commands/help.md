---
description: Show the adhoc plugin commands and how the methodical-mode hook works
---

The user wants help with the adhoc plugin. Reply with exactly this message — verbatim, no additions, no embellishment:

```
adhoc — methodical-mode for ad-hoc Claude work

WHAT IT DOES
  An always-on UserPromptSubmit hook that prepends a methodical pre-response
  checklist to every user turn: restate the task, mark assumptions
  VERIFIED/UNVERIFIED, cite CLAUDE.md and memory rules in play, surface
  alternatives, confirm before editing. Stops the race-to-an-answer pattern.

COMMANDS
  /adhoc:status      Show current methodical-mode state (on / off / casual)
  /adhoc:on          Re-enable methodical-mode for this session
  /adhoc:off         Disable methodical-mode for the rest of this session
  /adhoc:casual      Skip methodical-mode for the NEXT turn only — auto-reverts
  /adhoc:deep        Heavier methodical analysis pass (skill, no code changes)
  /adhoc:help        This message

SUBAGENT
  adhoc:second-opinion   Independent fresh-context critique of a plan or approach.
                         Invoked via the Agent tool with subagent_type=adhoc:second-opinion.

STATE FILE
  ~/.claude/.adhoc-state
    absent / "on"   methodical-mode active (default)
    "off"           silenced for the session
    "casual"        skipped once, then auto-reverts to on

WHEN TO RELEASE-VALVE
  /adhoc:casual — for trivial questions ("what's the date", "rename this var")
                  where the methodical preamble is pure noise.
  /adhoc:off    — for long pairing sessions where you've already calibrated and
                  the preamble is repeating itself.

The default (always-on) is intentional. If you remembered to invoke it, you
wouldn't need it — the whole point is that it fires when you forget.
```

Do not add anything before or after. Do not summarize. Do not paraphrase.
