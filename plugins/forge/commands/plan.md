---
description: "Start a codebase-aware specification interview for a feature"
argument-hint: "FEATURE_NAME [--context FILE] [--output-dir DIR] [--no-survey] [--focus DIRS] [--first-principles]"
allowed-tools: ["Bash(${CLAUDE_PLUGIN_ROOT}/scripts/setup-forge.sh:*)", "AskUserQuestion", "Read", "Write", "Glob", "Grep", "Agent"]
hide-from-slash-command-tool: "true"
---

# Forge Plan Command

Execute the setup script to initialize the research + interview session:

```!
"${CLAUDE_PLUGIN_ROOT}/scripts/setup-forge.sh" $ARGUMENTS
```

You are now conducting a codebase-aware specification interview. Follow the instructions provided by the setup script exactly.

## PHASE EXECUTION ORDER

1. **R0: SURVEY** — Spawn 4 parallel Explore agents to research the codebase (unless --no-survey)
2. **R1: SYNTHESIZE** — Read all survey files, write the reality document
3. **R2: INTERVIEW** — Multi-round adaptive interview grounded in survey findings
4. **R3: SPEC** — Generate foundry-ready specification when user says "done"
5. **R4: VALIDATE** — Verify all file references, pattern references, coverage

## SURVEY RULES (R0)
- Spawn ALL 4 agents in a SINGLE message (parallel execution)
- Use `subagent_type: "Explore"` for each agent
- Each agent writes to the survey directory specified in SESSION INFORMATION
- Wait for all 4 to complete before proceeding to R1

## INTERVIEW RULES (R2)
1. EVERY question must use AskUserQuestion — plain text questions won't work
2. Ground every question in codebase findings from the survey
3. Ask NON-OBVIOUS questions (not "what should it do?" but "I see X pattern in Y file — should we follow it or diverge?")
4. Continue until user says "done" or "finalize"
5. Update the draft spec file regularly using the Write tool

## FINALIZATION CONSTRAINTS — CRITICAL

When the user says "done", "finalize", "finished", or similar:

### ALLOWED ACTIONS:
- Read any files needed to compile and validate the final spec
- Write the final spec, JSON spec, and progress file
- Use Glob/Grep to validate file references in the spec
- Delete the state file

### FORBIDDEN ACTIONS:
- NO Bash tool calls — do not run any commands
- NO Edit tool calls — do not modify existing code
- NO implementation of any kind — you are ONLY writing spec documents

### FINALIZATION SEQUENCE:
1. Write the final markdown spec (PHASE R3 template)
2. Validate the spec (PHASE R4 checks)
3. Write the JSON spec
4. Write the progress file with all phases marked [PENDING]
5. Delete the state file
6. Output `<promise>SPEC FORGED</promise>`
7. STOP IMMEDIATELY — do not continue with any other actions

### CRITICAL: SPEC FORGED MEANS STOP
After outputting `<promise>SPEC FORGED</promise>`, you MUST stop. Do not:
- Offer to implement the feature
- Suggest next steps for implementation
- Make any code changes
- Run any commands

The spec is the deliverable. Foundry builds it.
