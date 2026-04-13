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
3. **R1.5: RESEARCH** — Targeted online research to kill assumptions before interviewing
4. **R2: INTERVIEW** — Multi-round adaptive interview grounded in codebase + ecosystem findings
5. **R3: SPEC** — Generate foundry-ready specification when user says "done"
6. **R4: VALIDATE** — Verify all file references, pattern references, coverage

## SURVEY RULES (R0)
- Spawn ALL 4 agents in a SINGLE message (parallel execution)
- Use `subagent_type: "Explore"` for each agent
- Each agent writes to the survey directory specified in SESSION INFORMATION
- Wait for all 4 to complete before proceeding to R1

## RESEARCH RULES (R1.5)

After writing `reality.md`, identify 2-4 **targeted** research domains grounded in what the survey actually found. Research is NOT generic — it verifies the current state of things the codebase already depends on, or things the feature request implies.

**Good research targets** (the survey found specific things):
- "Codebase uses htmx 1.9 + EventSource for SSE — is 1.9 still current? Any breaking changes in 2.x? Does the SSE extension pattern still work?"
- "Codebase uses client-go v0.29 for k8s API — what's the current stable version? Any deprecated APIs since?"
- "User mentioned 'embedded dashboard' and repo has html/template + embed.FS — is this still the idiomatic Go pattern or has it moved to something else?"

**Bad research targets** (too generic — skip these):
- "How do you build a web UI?"
- "What is Kubernetes?"

**Procedure:**
1. Read `reality.md` that R1 just produced
2. Identify specific technical claims that would be wrong if your training data is stale (library versions, API surface, deprecated patterns, ecosystem shifts)
3. Pick 2-4 narrow domains to verify. If nothing in reality.md has technical claims that need verifying (e.g., pure design spec with no libraries), **skip R1.5 entirely** and note in state.md that research was not applicable
4. Spawn one `researcher` agent per domain in parallel (single message). Use `subagent_type: "Agent"` with the full content of `${CLAUDE_PLUGIN_ROOT}/agents/researcher.md` as the prompt
5. Pass to each researcher: domain name, the specific claim from reality.md to verify, the output path `{survey_dir}/research-{domain-slug}.md`
6. Each researcher uses WebSearch + WebFetch (Context7 if available in this project's .mcp.json) to verify current state
7. Wait for all researchers to complete
8. Append a `## Research Findings` section to reality.md summarizing each domain's HIGH/MEDIUM/LOW confidence verdict and the top actionable insight

**Skip condition (also triggers from --no-survey):** If --no-survey was passed, skip R1.5 too. No codebase context = no targeted research possible.

**Context budget**: each researcher burns 20-40k tokens in its own context. The interviewer (R2) only reads the research findings summary in reality.md, not raw investigation.

## INTERVIEW RULES (R2)
1. EVERY question must use AskUserQuestion — plain text questions won't work
2. Ground every question in codebase findings (from R0/R1) AND research findings (from R1.5, if applicable)
3. Ask NON-OBVIOUS questions (not "what should it do?" but "I see X pattern in Y file — should we follow it or diverge?")
4. **Use research findings to kill stale-knowledge questions.** If R1.5 verified "htmx 2.x is out and SSE extension is now a separate package", don't ask the user "should we use the built-in htmx SSE?" — you already know. Instead, ask "R1.5 research found htmx 2.x moved SSE to a separate package — do you want to migrate to 2.x as part of this feature, or stay on 1.9?"
5. **Surface research conflicts.** If research found something that contradicts what the user seems to assume, tell them explicitly: "You mentioned X, but my research of current {library} docs shows Y. Which way do you want to go?"
6. Continue until user says "done" or "finalize"
7. Update the draft spec file regularly using the Write tool

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

## REQUIREMENT CLASSIFICATION

During finalization (R3: SPEC), classify every requirement into one of three categories:

### Locked (implement exactly as specified)
Requirements where the user gave specific, concrete instructions. The implementation must match exactly — no creative interpretation.

Examples:
- "Passwords must be hashed with bcrypt (cost factor 12)"
- "The API must return 429 after 100 requests per minute"
- Specific data formats, protocols, or algorithms named by the user

### Flexible (Claude's discretion on approach)
Requirements where the user described the WHAT but not the HOW. The implementing agent has discretion on approach.

Examples:
- "User sees a loading state while data fetches" (implementation approach flexible)
- "Error messages should be user-friendly" (exact wording flexible)
- UI layout and interaction patterns not explicitly constrained

### Informational (context, not requirements)
Background information the user shared that provides context but is NOT a requirement to implement. **Also: research findings from R1.5 that aren't strict requirements but downstream teammates should know about.**

Examples:
- "The team currently uses Tailwind CSS" (user-provided)
- "Previous auth system used JWT with 15-min expiry" (user-provided)
- "We have 10,000 daily active users" (user-provided)
- "htmx 2.x SSE extension is a separate package — this codebase is on 1.9, not migrating in this feature" (from R1.5 research)
- "client-go v0.30 is current stable; codebase uses v0.29 — no breaking changes relevant to Deployments API" (from R1.5 research)

Auto-populate Informational from `reality.md` `## Research Findings` section during R3 finalization. Every research finding that isn't locked or flexible becomes an Informational item so Foundry teammates downstream see the ecosystem context when they build.

### How to classify
During the interview, track which category each piece of information falls into:
- User says "must", "exactly", "require" → **Locked**
- User describes desired behavior without constraining approach → **Flexible**
- User provides background/context → **Informational**

### Spec output format
In the final spec, group requirements under these headings:

```
## Requirements

### Locked (implement exactly as specified)
- **US-1**: User can log in with email and password
- **FR-3**: Passwords must be hashed with bcrypt (cost factor 12)

### Flexible (Claude's discretion on approach)
- **US-5**: User sees a loading state while data fetches
- **FR-8**: Error messages should be user-friendly

### Informational (context, not requirements)
- The team currently uses Tailwind CSS
- Previous auth system used JWT with 15-min expiry
```

Foundry's CAST teammates use this classification: **Locked** = implement exactly, **Flexible** = best judgment, **Informational** = context only.

### CRITICAL: SPEC FORGED MEANS STOP
After outputting `<promise>SPEC FORGED</promise>`, you MUST stop. Do not:
- Offer to implement the feature
- Suggest next steps for implementation
- Make any code changes
- Run any commands

The spec is the deliverable. Foundry builds it.
