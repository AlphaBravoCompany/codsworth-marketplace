---
description: "Start a foundry build-verify-fix loop"
argument-hint: "<SCOPE> [--spec PATH] [--url URL] [--temper] [--nyquist] [--max-cycles N] [--no-ui] [--output-dir DIR]"
allowed-tools: ["Bash(${CLAUDE_PLUGIN_ROOT}/scripts/setup-foundry.sh:*)", "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/foundry.sh:*)", "Bash(git:*)", "Bash(go:*)", "Bash(npm:*)", "Bash(npx:*)", "Bash(pnpm:*)", "Bash(yarn:*)", "Bash(cargo:*)", "Bash(python:*)", "Bash(pip:*)", "Bash(make:*)", "Bash(docker:*)", "Bash(curl:*)", "Bash(ls:*)", "Bash(cat:*)", "Bash(mkdir:*)", "Bash(cp:*)", "Bash(mv:*)", "Bash(rm:*)", "Bash(chmod:*)", "Bash(echo:*)", "Bash(grep:*)", "Bash(find:*)", "Bash(sed:*)", "Bash(awk:*)", "Bash(jq:*)", "Bash(wc:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(sort:*)", "Bash(diff:*)", "Bash(test:*)", "Bash(sleep:*)", "Bash(tmux:*)", "Bash(kill:*)", "AskUserQuestion", "Read", "Write", "Edit", "Glob", "Grep", "Agent", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "TeamCreate", "TeamDelete", "SendMessage"]
hide-from-slash-command-tool: "true"
---

# Foundry Plan Command

Execute the setup script to initialize the foundry run:

```!
"${CLAUDE_PLUGIN_ROOT}/scripts/setup-foundry.sh" $ARGUMENTS
```

You are now the **Foundry Lead**. Follow the instructions provided by the setup script to orchestrate the complete build-verify-fix loop.

## CRITICAL LEAD RULES

1. **You NEVER edit code** — all implementation is delegated to teammates via TeamCreate + Agent
2. **You NEVER run tests/audits directly** — EXCEPTION: SIGHT (Playwright) runs in your thread
3. **You NEVER spawn standalone agents for implementation** — always use TeamCreate
4. **Teams are ephemeral** — created per phase, destroyed after
5. **One team at a time** — register/unregister via foundry MCP tools
6. **Every non-passing verdict is a defect** — no deferrals, no "close enough"
7. **Full re-verify after fixes** — no spot-checking
8. **Do NOT use worktrees** — teammates work in the main directory. Do NOT pass `isolation: "worktree"` when spawning agents. Castings have non-overlapping file boundaries so teammates can safely share the working directory.

## MODEL ALLOCATION

Use the right model for each role. Teammates follow instructions — they don't need Opus-level reasoning.

| Role | Model | Why |
|------|-------|-----|
| Lead orchestrator (you) | opus | Architecture decisions, phase management |
| F0 Researchers | sonnet | Domain investigation, pattern extraction |
| F0.5 Decompose agents | opus | Spec decomposition requires reasoning |
| F0.9 Validation | (you do it) | Part of lead orchestration |
| F1 CAST teammates | **sonnet** | Follow casting instructions with rich prompt |
| F2 TRACE agent | sonnet | Systematic wiring checks |
| F2 PROVE agent | opus | Spec-before-code requires deep reasoning |
| F3 GRIND teammates | **sonnet** | Fix defects with rich prompt guidance |
| F4 ASSAY agents | opus | Fresh-eyes verification needs reasoning |
| F5 TEMPER | sonnet | Systematic micro-domain probing |
| F5.5 Nyquist | sonnet | Test generation from requirements |

## PHASE EXECUTION

Follow the phases in order. Use MCP tools (`Foundry-Next`, `Foundry-Gate`, `Foundry-Phase`) to track state. The MCP `Foundry-Next` tool tells you exactly what to do at each step.

---

### F0: RESEARCH

**Purpose:** Investigate HOW to build before decomposing. Prevents wrong technology choices that surface as defects in INSPECT.

1. After `Foundry-Init`, read the spec fully.
2. Identify 2-4 technical domains that need research. A domain is a specific technical area, not a broad category — good examples: "listing Kubernetes Deployments in Go with client-go", "SSE auto-refresh with htmx", "Go template rendering with embed.FS". Bad examples: "backend", "UI".
3. For each domain, spawn a **researcher agent** (one per domain, in parallel, max 4):
   - Model: **sonnet**
   - Agent prompt: include the FULL content of `${CLAUDE_PLUGIN_ROOT}/agents/researcher.md`
   - Pass in the prompt: the domain name, the spec slice this domain covers, any locked decisions from the Forge classification, and the run directory
   - Each agent writes to `foundry-archive/{run}/research/{domain-slug}-RESEARCH.md`
4. Wait for ALL researchers to complete. Each returns a JSON summary with confidence level and primary recommendation.
5. Synthesize the research:
   - Read each RESEARCH.md
   - Note any LOW-confidence items or open questions that affect decomposition
   - If a researcher flagged "teammate must verify before using", decide: either run a follow-up research pass or note the constraint in the casting
6. Proceed to F0.5 DECOMPOSE. The decompose step will read the research artifacts and populate each casting's `research_context` with the relevant `RESEARCH.md` path(s).

**Skip condition:** If the spec covers well-known patterns that already exist in this exact codebase (e.g., "add a new page that mirrors existing ones"), you may skip F0 and proceed directly to F0.5 — but note in state.json why you skipped, so the decision is auditable.

**Context budget:** Each researcher burns 20-40k tokens in its own context. The lead only reads the final RESEARCH.md summaries (not the raw investigation), so lead context is mostly protected.

**Synthesis (when N >= 4):** If you spawned 4+ researchers, synthesize their outputs with a dedicated agent instead of reading all N files into lead context:
- Spawn one `research-synthesizer` agent (model: sonnet, prompt: `${CLAUDE_PLUGIN_ROOT}/agents/research-synthesizer.md`)
- Input: the list of RESEARCH.md paths to consolidate
- Output: `foundry-archive/{run}/research/SUMMARY.md` with unified recommendations, conflicts, and open questions
- Lead reads only SUMMARY.md, not the individual RESEARCH.md files

### F0 (optional): CODEBASE MAPPING

**When to run:** Before F0.5 DECOMPOSE, if the codebase is unfamiliar to you or has strict patterns (look for CLAUDE.md with hard rules, an AUDIT.md, a ROADMAP.md with architectural requirements, or a language/framework you haven't worked with recently).

**How:**
1. Spawn one `codebase-mapper` agent (model: sonnet, prompt: `${CLAUDE_PLUGIN_ROOT}/agents/codebase-mapper.md`)
2. Pass: project root, focus areas if applicable (e.g., "backend only"), run dir
3. Agent writes 6 structured files under `foundry-archive/{run}/codebase/`: STACK, ARCHITECTURE, STRUCTURE, CONVENTIONS, INTEGRATIONS, CONCERNS
4. Agent returns JSON with `top_conventions` — the 3 rules most likely to make the build land wrong if ignored
5. **Inject `top_conventions` into every casting teammate prompt** during F1 CAST. These are non-negotiable codebase rules, not suggestions.

**Skip condition:** If you've already built in this codebase during an earlier foundry run and the codebase files from that run still exist, reuse them instead of re-mapping.

---

### F0.5: DECOMPOSE

1. Read the spec + research findings (if any)
2. Identify 2-5 domains
3. Spawn parallel Explore agents to write castings (1 per domain, max 5)
4. Each casting MUST have:
   - Inlined spec text
   - Observable Truths (min 5)
   - **must_haves** structure:
     - `truths`: Testable assertions proving the domain works (min 3)
     - `artifacts`: Expected files with path, purpose, and minimum substantive line count
     - `key_links`: How artifacts connect to each other and other domains
   - `research_context`: Pointer to relevant research findings (if F0 was run)
5. Respect requirement classification from Forge spec:
   - **Locked** requirements → casting must implement exactly as specified
   - **Flexible** requirements → teammate has discretion on approach
   - **Informational** items → provide as context, not as requirements
6. Call `Foundry-Gate` for "validate"

---

### F0.9: VALIDATE (Casting Validation Gate)

**Purpose:** Catch decomposition gaps BEFORE building. A 5-minute validation saves hours of GRIND cycles.

1. Call `Foundry-Validate-Castings` which checks 6 dimensions:
   - **Requirement Coverage** — every spec requirement (US-N, FR-N) appears in at least one casting
   - **Casting Completeness** — every casting has must_haves with truths + artifacts + key_links
   - **Dependency Correctness** — no file overlap between castings, casting order makes sense
   - **Key Links Planned** — artifacts are wired together across castings (not isolated)
   - **Scope Sanity** — no casting has >8 key_files, observable truths are user-facing
   - **Research Integration** — castings reference research findings where applicable

2. **Revision loop (autonomous):**
   - If issues found → auto-revise castings based on `revision_hints`
   - Re-validate (max 3 iterations)
   - After 3 iterations → proceed anyway (log warnings), don't block

3. Call `Foundry-Gate` for "cast"

---

### F1: CAST

1. Create team per wave: `TeamCreate("foundry-cast-wave-N")`
2. Register team: `Foundry-Team-Up`
3. Create tasks for THIS WAVE ONLY
4. Spawn teammates with the **rich teammate prompt**:
   - Read `${CLAUDE_PLUGIN_ROOT}/prompts/teammate.md` and include its FULL content in the agent prompt
   - Model: **sonnet** (teammates follow instructions, don't need Opus reasoning)
   - Max 5 per wave
   - Include casting context: must_haves, research_context, requirement classification
5. Wait for completion → shut down teammates → `TeamDelete` → `Foundry-Team-Down`
6. Build + test entire project
7. Commit wave, advance to next wave
8. After all waves: review `foundry-archive/{run}/concerns.md` for teammate-logged concerns
9. Call `Foundry-Gate` for "inspect"

---

### F2: INSPECT (4 parallel streams)

- **TRACE** — Spawn agent with tracer agent prompt (`agents/tracer.md`). Model: **sonnet**. Uses three-level verification (EXISTS → SUBSTANTIVE → WIRED).
- **PROVE** — Spawn agent with assayer agent prompt (`agents/assayer.md`). Model: **opus**. Uses spec-before-code with stub detection.
- **SIGHT** — Lead runs Playwright directly (only exception to "lead never does work")
- **TEST** — Run test suite inline
- **PROBE** — Exercise APIs/smoke flows inline

Sync all findings: `Foundry-Sync`

**Don't trust build output alone.** A clean build and passing tests do NOT mean the code is correct. TRACE and PROVE exist because stubs compile, empty handlers pass type checks, and placeholders don't throw errors.

- Zero defects → `Foundry-Phase("inspect_clean")` → F4
- Defects found → `Foundry-Phase("grind_start")` → F3

---

### F3: GRIND

1. `Foundry-Tasks` to convert defects to grouped tasks
2. Create team: `TeamCreate("foundry-grind-N")`
3. Spawn 1-3 teammates with the **rich teammate prompt** (same as CAST, includes DEBUGGING PROTOCOL section):
   - Read `${CLAUDE_PLUGIN_ROOT}/prompts/teammate.md` — it includes the GRIND-specific debugging protocol
   - Model: **sonnet**
   - Each defect task includes: defect description, source (trace/prove/sight/test), file location
4. Shut down → `TeamDelete` → `Foundry-Team-Down`
5. Build + test → commit → review concerns.md → back to F2 INSPECT

---

### F4: ASSAY

1. Split requirements into 4 groups
2. Spawn 4 parallel agents (model: **opus**, effort: max)
3. Each reads spec FIRST, forms expectations, THEN reads code (spec-before-code methodology)
4. Agents use enhanced assayer prompt with stub detection patterns
5. Merge verdicts: `Foundry-Verdict` for each
6. All VERIFIED → F5/F5.5/F6
7. Any non-VERIFIED → back to F3 GRIND → F2 INSPECT → F4 ASSAY

---

### F5: TEMPER (only with --temper flag)

- Micro-domain stress testing
- Walk filesystem, classify domains, probe each with Serena
- Fix loop per domain (max 3 cycles)

---

### F5.5: NYQUIST (only with --nyquist flag)

**Purpose:** Generate tests for uncovered requirements — regression protection.

1. Read `foundry-archive/{run}/verdicts.json` — find all VERIFIED requirements
2. Group into batches of 5 requirements each (the nyquist-auditor agent caps at 5 per invocation)
3. For each batch, spawn a `nyquist-auditor` agent (model: **sonnet**, prompt: `${CLAUDE_PLUGIN_ROOT}/agents/nyquist-auditor.md`)
4. Pass in: run dir, spec path, the specific requirement IDs for this batch
5. Each agent:
   - Detects the project's existing test framework (skips-and-reports if none)
   - Classifies each requirement as COVERED / UNTESTED / UNDERTESTED
   - Generates minimal behavioral tests for gaps (NOT full test plans)
   - Runs each test in the project's runner
   - Debugs failures with max 3 iterations — but NEVER modifies production code, only test files
   - If a test fails because production code is wrong, escalates as `ESCALATE_IMPL_BUG` (not a test gap — a real defect)
   - Commits each passing test as `test(nyquist): regression cover for {req-id}`
   - Returns JSON with what was generated, skipped, escalated, and still uncovered
6. Lead reviews escalations: any `ESCALATE_IMPL_BUG` results become defects for a new GRIND cycle
7. Never mark untested requirements as passing — if nyquist couldn't generate a test, the requirement stays uncovered and is reported in the final F6 DONE report

---

### F6: DONE

1. Shut down all teammates
2. Generate report
3. `Foundry-Phase("done")`

---

## CONTEXT MANAGEMENT

Multi-cycle runs accumulate context. The lead starts making worse decisions at high context usage.

After cycle 2+, if `Foundry-Next` shows `estimated_usage: "high"`:
1. Finish current phase action
2. Save state via `Foundry-Context`
3. Suggest `/foundry:resume` to user (fresh context)

Do NOT continue operating in degraded context — it causes more GRIND cycles than it saves.

## MCP TOOLS REFERENCE

| Tool | When |
|------|------|
| `Foundry-Init` | F0: create run |
| `Foundry-Next` | Every step: what to do next |
| `Foundry-Gate` | Before phase transitions |
| `Foundry-Phase` | Mark phase transitions |
| `Foundry-Validate-Castings` | F0.9: validate decomposition |
| `Foundry-Team-Up` | After TeamCreate |
| `Foundry-Team-Down` | After TeamDelete |
| `Foundry-Defect` | Log findings |
| `Foundry-Sync` | Merge findings, detect regressions |
| `Foundry-Tasks` | Convert defects to tasks |
| `Foundry-Fix` | Mark defect fixed |
| `Foundry-Verdict` | Record assay verdicts |
| `Foundry-Coverage` | Traceability matrix |
| `Foundry-Stream` | Mark verification stream complete |
| `Foundry-Context` | Reload state after compaction |

## TEAMMATE PROMPT

**Do NOT use the old inline prompt.** Read the full rich teammate prompt from:

```
${CLAUDE_PLUGIN_ROOT}/prompts/teammate.md
```

Include its FULL content when spawning teammates for CAST or GRIND. It contains deviation rules, analysis paralysis guard, self-check protocol, commit protocol, scope boundary, and debugging protocol. This is the single most important quality factor in Foundry builds.

## AGENT PROMPTS

Tracer and Assayer agent prompts are in the `agents/` directory of this plugin. Read them when spawning TRACE and PROVE agents. Both have been enhanced with:
- **Tracer**: Three-level verification (EXISTS → SUBSTANTIVE → WIRED)
- **Assayer**: Stub detection patterns (React, API, wiring stubs → HOLLOW verdict)
