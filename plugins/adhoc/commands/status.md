---
description: Show the current adhoc methodical-mode state
---

The user wants to see the current adhoc methodical-mode state.

Run exactly this Bash command:

```
state="on"; [ -f ~/.claude/.adhoc-state ] && state=$(cat ~/.claude/.adhoc-state | tr -d '[:space:]'); echo "adhoc methodical-mode state: ${state}"
```

After it succeeds, reply to the user in one short line with the state. If `off`, mention `/adhoc:on` re-enables. If `casual`, mention next turn skips and auto-reverts. If `on`, just confirm. Do not add anything else.
