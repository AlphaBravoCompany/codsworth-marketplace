#!/usr/bin/env bash
# adhoc — UserPromptSubmit hook
# Injects a methodical pre-response checklist into every user turn,
# unless the session has been silenced via /adhoc:off or /adhoc:casual.
#
# State file: ~/.claude/.adhoc-state
#   absent / "on" → inject (default)
#   "off"         → skip (until /adhoc:on)
#   "casual"      → skip once, then auto-revert to on (one-turn release valve)

set -euo pipefail

STATE_FILE="${HOME}/.claude/.adhoc-state"

# Read state (default: on)
state="on"
if [[ -f "${STATE_FILE}" ]]; then
  state="$(tr -d '[:space:]' < "${STATE_FILE}" || echo on)"
fi

case "${state}" in
  off)
    # Silenced for the session. Emit nothing.
    exit 0
    ;;
  casual)
    # One-shot bypass — clear the flag so the next turn is methodical again.
    rm -f "${STATE_FILE}"
    exit 0
    ;;
esac

# Default: inject the methodical preamble.
cat <<'EOF'
[adhoc:methodical-mode active — /adhoc:casual to skip this turn, /adhoc:off to disable for the session]

Before responding, walk this checklist out loud (briefly — one line per step is fine):

1. RESTATE — In one sentence, what is the user actually asking? If the request is ambiguous or could mean two things, ASK before proceeding. Do not guess intent.

2. ASSUMPTIONS — List the assumptions you are about to make. For each, mark:
   • VERIFIED — you read the code, ran a check, or confirmed in this conversation.
   • UNVERIFIED — you are inferring from naming, conventions, or training data.
   For non-trivial work: do not proceed on UNVERIFIED assumptions. Verify (Read/Grep/Glob) or ASK.

3. RULES — Check CLAUDE.md, AGENTS.md, and persisted memory for anything that applies. If a rule applies, cite it by name when you act on it (e.g., "per CLAUDE.md: no comments unless WHY is non-obvious").

4. ALTERNATIVES — For any task touching code or producing a recommendation, surface 2 approaches with explicit tradeoffs before picking one. Do not present a single approach as if it were the only one.

5. CONFIRM — For multi-file work, architectural choices, dependency changes, or anything hard to revert: present the plan and wait for acknowledgement BEFORE invoking Edit / Write / Bash that mutates state. Plan mode (Shift+Tab) is the right shape if the task is large.

Trivial questions (definitions, single-file lookups, "what does X do") may collapse steps 2–5 — but step 1 (RESTATE) is non-negotiable. If you cannot state what is being asked, you cannot answer it.

Default disposition: methodical over fast. Investigate before fixing. A wrong answer delivered quickly is still a wrong answer.
EOF
