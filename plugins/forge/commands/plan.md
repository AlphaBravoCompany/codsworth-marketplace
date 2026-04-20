---
description: "Start a codebase-aware specification interview for a feature"
argument-hint: "FEATURE_NAME [--context FILE] [--output-dir DIR] [--no-survey] [--focus DIRS] [--first-principles] [--brownfield] [--greenfield] [--cosmetic]"
allowed-tools: ["Bash(${CLAUDE_PLUGIN_ROOT}/scripts/setup-forge.sh:*)", "Bash(python3:*)", "Bash(find:*)", "Bash(wc:*)", "AskUserQuestion", "Read", "Write", "Edit", "Glob", "Grep", "Agent"]
hide-from-slash-command-tool: "true"
---

# Forge Plan Command

Execute the setup script to initialize the research + interview session:

```!
"${CLAUDE_PLUGIN_ROOT}/scripts/setup-forge.sh" $ARGUMENTS
```

You are now conducting a codebase-aware specification interview. Follow the instructions provided by the setup script exactly.

## MODE DETECTION (R-pre) — v3.0.0+

Before R0, detect which pipeline this run uses. Three modes:

| Mode | When | Pipeline |
|---|---|---|
| **`brownfield`** | existing codebase, flow-shaped request | V3: flow-mapper → flow-interviewer → flow-delta.json (plus spec.md for compatibility) |
| **`greenfield`** | empty or near-empty target, flow-shaped request | V2 pipeline unchanged (end-state-first is correct when there is no upstream to honor) |
| **`cosmetic`** | non-flow-shaped request (styling, copy, deps, docs, minor refactor) in any codebase | V2 pipeline, no flow mapping |

**Detection procedure:**

1. If `--brownfield`, `--greenfield`, or `--cosmetic` flag was passed → use that mode verbatim. Skip auto-detection.
2. Otherwise, auto-detect:
   - Count relevant-language source files under target paths (Go `*.go`, TS/JS `*.ts|*.tsx|*.js|*.jsx`, Python `*.py`, Rust `*.rs`, excluding tests, vendored code, `node_modules/`).
     ```bash
     find "${PROJECT_ROOT}" -type f \( -name "*.go" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" -o -name "*.py" -o -name "*.rs" \) \
       -not -path "*/vendor/*" -not -path "*/node_modules/*" -not -path "*/target/*" -not -path "*/__pycache__/*" \
       -not -name "*_test.go" -not -name "*.test.ts" -not -name "*.test.tsx" -not -name "*.spec.ts" \
       | wc -l
     ```
   - If count ≤ 20 → default `greenfield`.
   - Else → read the user's feature-name / initial prompt. If the request is flow-shaped (adds a new feature, new endpoint, new page, new data flow, new module) → default `brownfield`. If it is cosmetic (styling, copy edit, README update, dependency bump, minor refactor with no behavioral change) → default `cosmetic`.
3. **Confirm with the user via AskUserQuestion** — always. Show the detected mode, the file count, and a one-line rationale. Options: `confirm` | `force-greenfield` | `force-brownfield` | `force-cosmetic` | `abort`.
4. Record the chosen mode to `state.md` as `mode: brownfield|greenfield|cosmetic` before proceeding.

**If mode is `greenfield` or `cosmetic`:** follow the V2 pipeline documented below (R0 → R4) unchanged. Stop reading this section.

**If mode is `brownfield`:** follow the V3 overrides in §V3 BROWNFIELD OVERRIDES below. The V2 phase sections remain as reference for the parts V3 does not override (R1 SYNTHESIZE, R1.5 RESEARCH, R4 VALIDATE are all shared).

## PHASE EXECUTION ORDER

1. **R0: SURVEY + DOMAIN** (parallel, single message)
   - **R0.A SURVEY** — 4 Explore agents research the codebase (architecture, data, surface, infra) (unless --no-survey)
   - **R0.B DOMAIN** — 1 domain-scout agent runs ecosystem research on the feature category (prior art, common shapes, gotchas, questions the interviewer should ask). Uses `agents/domain-scout.md`. Runs even if no codebase exists, as long as `--no-survey` wasn't passed.
2. **R1: SYNTHESIZE** — Read all survey files + domain-orientation.md, write the reality document
3. **R1.5: RESEARCH** — Targeted online research to kill library-version assumptions (narrower than R0.B — this is stale-knowledge invalidation grounded in specific claims from reality.md)
4. **R2: INTERVIEW** — Multi-round adaptive interview grounded in codebase + domain + ecosystem findings, with **spec_type detection and migration source enumeration**
5. **R3: SPEC** — Generate foundry-ready specification when user says "done"
6. **R4: VALIDATE** — Verify all file references, pattern references, coverage

**R0.A vs R0.B vs R1.5:**
- **R0.A SURVEY** answers "what does THIS codebase look like?" (inside-in)
- **R0.B DOMAIN** answers "what does this FEATURE CATEGORY look like in the ecosystem, and what are the common gotchas?" (outside-in, before we know what decisions the user will make)
- **R1.5 RESEARCH** answers "are the specific library versions and APIs we plan to use still current?" (inside-out, after we know what the codebase uses)

All three feed the R2 interviewer. Different jobs, different timing, different depth.

## SPEC TYPE DETECTION (R2) — MANDATORY

During R2 INTERVIEW, you MUST classify this feature as one of four types and record the type in `state.md` and in the final `spec.md` frontmatter:

| Type | When | Examples |
|---|---|---|
| `GREENFIELD` | Building something new that doesn't exist yet | "add a workloads page", "new auth endpoint", "new dashboard widget" |
| `MIGRATION` | Converting/porting/replacing an existing artifact into a new form | "convert legacy tests to ginkgo v2", "migrate from REST to gRPC", "port the go bindings to python", "rewrite the parser in Rust" |
| `BUG_FIX` | Fixing specific broken behavior | "certificate rotation loses old cert on failure", "race in the cache invalidation" |
| `REFACTOR` | Restructuring code without changing external behavior | "extract auth middleware into its own package", "split the god-struct into services" |

**Detection trigger phrases** in the user's initial prompt or interview answers:
- MIGRATION: "convert", "migrate", "port", "replace existing X with", "rewrite Z into Y format", "move from A to B"
- BUG_FIX: "fix", "broken", "doesn't work", "race", "regression", "leak", audit finding references (C-N, H-N, M-N)
- REFACTOR: "extract", "split", "consolidate", "restructure", "reorganize", "clean up"
- GREENFIELD: default if none of the above apply

Ask an explicit classification question using AskUserQuestion if the type isn't obvious from the initial prompt.

## MIGRATION MODE ENFORCEMENT (R2) — IF spec_type is MIGRATION

If you classified the feature as MIGRATION, you have additional mandatory duties in R2:

1. **Enumerate the source inventory.** The user MUST provide (or you MUST generate via grep and ask the user to confirm) a complete list of every source artifact that must be ported. For a test migration: every Test* function in every legacy test file. For a library port: every public symbol. For a protocol migration: every endpoint.

2. **Use grep to generate the candidate inventory.** Example:
   ```bash
   grep -rn "^func Test" legacy/tests/ > /tmp/source-inventory.txt
   ```
   Then present the list to the user via AskUserQuestion and ask them to confirm/prune.

3. **Write the inventory to state.md.** Format:
   ```
   ## source_inventory
   - legacy/tests/auth_test.go:TestLogin
   - legacy/tests/auth_test.go:TestLogout
   - legacy/tests/cache_test.go:TestInvalidate
   ...
   ```

4. **Declare the destination naming rule.** How does source map to destination? Suffix `_v2`? New directory? New file with renamed symbols? The rule must be deterministic so the coverage-diff stream in F2 INSPECT can check it mechanically. Ask the user explicitly.

5. **NEVER accept wiggle-word language as a complete spec.** If the user says "equivalent coverage," "same semantics," "similar to legacy" without an enumerated source list, the spec is NOT finalizable. Refuse to proceed to R3 SPEC until the enumeration is done. This is the hard fix for the D4 failure mode.

6. **In R3 SPEC output**, include the full `source_inventory` and `destination_naming_rule` as top-level fields in both the markdown spec and the JSON spec. Foundry's decompose will read these to populate each casting's `coverage_list`.

## SURVEY + DOMAIN RULES (R0)
- Spawn ALL 5 agents in a SINGLE message (parallel execution): 4 Explore agents for codebase survey + 1 domain-scout agent for ecosystem research
- Use `subagent_type: "Explore"` for the 4 codebase agents
- Use `subagent_type: "Agent"` for the domain-scout, passing the full content of `${CLAUDE_PLUGIN_ROOT}/agents/domain-scout.md` as its prompt
- Each agent writes to the survey directory specified in SESSION INFORMATION
- Wait for ALL 5 to complete before proceeding to R1
- The domain-scout writes `domain-orientation.md`; R1 SYNTHESIZE reads it and merges it into reality.md

**If `--no-survey` was passed:** skip BOTH R0.A and R0.B (no codebase + no domain research). Proceed directly to R2.

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
8. **VERBATIM TRANSCRIPT (v3.4.0):** Append every question AND user answer verbatim to `transcript.md` immediately after each AskUserQuestion returns. Use stable IDs (Q-001, A-001, Q-002, A-002, ...). Never paraphrase; never batch. The transcript is the source of truth — the structured spec.md is an index over it. See R2 rule #8 in setup-forge.sh for the full procedure.
9. **ARCHITECTURAL PLACEMENT DETECTION (v3.4.0):** When the user describes *where code lives* ("operator stays generic", "X must not know about Y", "agent handles Z, not the operator", "reuse existing RPC", "treat X as a library"), tag that A-NNN in the transcript with `[ARCH_INVARIANT]`. These answers become the `## Global Invariants` section of the final spec and are propagated verbatim into every foundry casting's `<global_invariants>` block. Missing these at interview time means downstream teammates will put code in the wrong architectural layer.

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
1. **Read `transcript.md` in full** — its bytes for the Appendix, its A-NNN index for citation validation.
2. Generate the spec body (PHASE R3 template) — every Locked item quoted + cited; every other bullet cited via `[from A-NNN]` / `[derived from A-NNN]` / `[from survey/...]`.
3. **Append `## Appendix: Interview Transcript`** with the full byte content of transcript.md pasted verbatim. No truncation.
4. Write the draft spec (body + appendix) to the canonical spec path in one Write call.
5. **Run the deterministic gate:** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate-spec.py <spec.md> <transcript.md>`
   - **Exit 0:** proceed to step 6.
   - **Exit 1:** read the numbered failures, fix the spec via Edit/Write on the canonical spec path, re-run the script. Loop until exit 0. This is a HARD STOP — the script is authoritative, your self-check is not.
6. Write the JSON spec.
7. Write the progress file with all phases marked [PENDING].
8. Delete the state file.
9. Do NOT delete transcript.md — it remains as the working artifact.
10. Output `<promise>SPEC FORGED</promise>`.
11. STOP IMMEDIATELY — do not continue with any other actions.

## REQUIREMENT CLASSIFICATION (v3.4.0 — verbatim-fidelity enforced)

During finalization (R3: SPEC), classify every requirement into one of three categories. **Locked requirements MUST quote the user verbatim with a transcript citation — see R3/R4 in setup-forge.sh for the hard rules. This section is the conceptual overview; the hard rules override if they conflict.**

### Locked (implement exactly as specified — direct quote from transcript)
Requirements where the user gave specific, concrete instructions. The spec contains the user's literal words in quotes with a `[from A-NNN]` citation pointing at the transcript.md answer it came from. No paraphrase, no interpretation, no "in other words."

Examples (note the quote+cite format):
- **FR-001** [from A-012]: "passwords must be hashed with bcrypt, cost factor 12"
- **FR-002** [from A-015]: "the API must return 429 after 100 requests per minute per user"
- **GI-001** [from A-020]: "operator stays generic — per-node rendering happens in the agent, not the operator" (architectural placement → Global Invariants section)

**If you can't find a verbatim quote in the transcript to support a Locked item, the item is not Locked — it's Flexible, or it needs another interview round. Never invent a quote.**

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

---

## V3 BROWNFIELD OVERRIDES (v3.0.0+)

Applies only when R-pre MODE DETECTION set `mode: brownfield`. These overrides replace specific V2 phases with V3 equivalents. Phases not listed here (R1 SYNTHESIZE, R1.5 RESEARCH, R4 VALIDATE) run as documented above.

**Why V3 exists, in one line:** end-state-first specs cause downstream teammates to fabricate plausible-sounding middle plumbing backward from the final feature. V3 replaces the end-state spec with a grounded flow graph plus a node-by-node confirmed delta — the attention anchor is the real system, not the imagined endpoint. Full rationale: see `${CLAUDE_PLUGIN_ROOT}/../foundry/FOUNDRY-V3-FLOW-REVERSAL-DESIGN.md`. Authoritative schema: `${CLAUDE_PLUGIN_ROOT}/../foundry/FOUNDRY-V3-DESIGN.md`.

### R0 — V3 override: FLOW-MAP (replaces R0.A SURVEY)

In brownfield mode, R0 produces a grounded flow graph instead of the four-agent codebase survey. R0.B DOMAIN (ecosystem research) still runs in parallel.

**Procedure:**

1. Spawn ONE `flow-mapper` agent (full content of `${CLAUDE_PLUGIN_ROOT}/../foundry/agents/flow-mapper.md` as prompt, or `subagent_type: "foundry:flow-mapper"` if registered).
2. Input to flow-mapper:
   - `project_root`: the target codebase.
   - `scope_hint`: natural-language description of the subsystem the user's feature will touch. Derive from the feature name + any `--focus` dirs. If you cannot derive a tight scope, ask the user via AskUserQuestion before spawning.
   - `run_dir`: the Forge session's survey directory.
   - `depth_cap: 6`, `size_cap: 120` unless user-overridden.
3. In parallel: spawn the `domain-scout` agent as in V2 R0.B.
4. Wait for both to complete.
5. Flow-mapper writes `flow-graph.json` to the survey directory. Validate it opens and the `validation: "passed"` summary was returned. If `scope_exceeded: true`, ask the user to narrow the scope and re-run — do not proceed with an incomplete graph.

**Important:** the four V2 Explore agents (architecture, data, surface, infra) do NOT run in V3 brownfield. Their output (codebase reality) is captured structurally by the flow graph. Preserve only domain-scout's `domain-orientation.md` for R1 SYNTHESIZE.

### R1 — shared with V2

R1 SYNTHESIZE runs unchanged. It reads `domain-orientation.md` + `flow-graph.json` (instead of the four survey files) and writes `reality.md`. The reality doc summarizes the flow graph's observations (node count, entry points, concerns logged by flow-mapper) plus the domain-scout findings.

### R1.5 — shared with V2

R1.5 RESEARCH runs unchanged. Same targeted stale-knowledge invalidation.

### R2 — V3 override: FLOW-INTERVIEW (replaces V2 free-form interview)

In brownfield mode, R2 is conducted by the `flow-interviewer` agent. It does node-by-node confirmation against the flow graph.

**Procedure:**

1. Spawn ONE `flow-interviewer` agent (full content of `${CLAUDE_PLUGIN_ROOT}/agents/flow-interviewer.md` as prompt, or `subagent_type: "forge:flow-interviewer"` if registered).
2. Input to flow-interviewer:
   - `project_root`, `flow_graph_path` (from R0), `user_request` (the feature description + any prior context), `run_dir`, `scope_hint`, `session_state_path` (for transcript continuity).
3. The flow-interviewer runs an interactive AskUserQuestion loop:
   - Proposes each new hop one at a time.
   - Pins hops on user `y`, adjusts on `adjust`, drops on `reject`.
   - Records every Q/A verbatim to `transcript.md` using the existing A-NNN / Q-NNN convention.
4. On completion, flow-interviewer emits `flow-delta.json` to `run_dir`.

**V2-specific R2 rules that still apply in brownfield:**
- VERBATIM TRANSCRIPT: every question and answer goes to `transcript.md`. Format continues A-NNN / Q-NNN.
- ARCHITECTURAL PLACEMENT DETECTION: when the user's answer describes where code lives (not just what it does), tag the A-NNN with `[ARCH_INVARIANT]`. These become `## Global Invariants` entries in the compatibility spec.md emitted in R3. (Flow-delta's grounding makes placement rules LESS critical than in V2 — since every new node has a declared file — but they still help.)
- spec_type classification: still record as GREENFIELD | MIGRATION | BUG_FIX | REFACTOR in `state.md`. Brownfield-mode is orthogonal to spec_type — a brownfield run can still be a MIGRATION.
- MIGRATION MODE ENFORCEMENT: source inventory and destination naming rule still required for MIGRATION spec_type. Flow-delta carries coverage_list on each packet for the same purpose.

**V2-specific R2 rules that DO NOT apply:**
- Multi-round adaptive interview: the flow-interviewer's node-by-node loop replaces this.
- Spec drafting via incremental Write calls: flow-interviewer writes a delta, not a spec body.
- REQUIREMENT CLASSIFICATION (Locked/Flexible/Informational): in brownfield, the packet's file + consumes + produces + pattern-to-mirror carry the locked constraints structurally. R3 below still emits a compatibility spec.md with classification for Foundry V2 compatibility, but it is derived from the delta, not driven by it.

### R3 — V3 override: DELTA + COMPATIBILITY SPEC

When the user says "done" / "finalize" in brownfield:

1. Confirm `flow-delta.json` exists and passes validation (schema + well-formedness per FOUNDRY-V3-DESIGN.md §6.2).
2. **Emit compatibility `spec.md`** — generated deterministically from the flow-delta:
   - `Problem Statement`: the user_intent_summary from the delta.
   - `Scope → In Scope`: one bullet per packet's terminal_slice.
   - `Requirements → Locked`: one LR-NNN per packet, quoting the packet's title, with `[from P<id>]` citation.
   - `File Change Map`: one row per packet (file + change_kind + consumes/produces summary).
   - `Observable Truths`: derived from the delta's terminal_slices (for Foundry's assayer, which still reads spec.md).
   - `## Flow Delta Reference`: path to flow-delta.json. This is the signal to Foundry's decompose that V3 mode applies.
   - `## Global Invariants`: any `[ARCH_INVARIANT]`-tagged transcript answers (same as V2).
   - `## Appendix: Interview Transcript`: verbatim transcript.md (same as V2).
3. Write both `spec.md` and `flow-delta.json` to the session output directory.
4. Write the JSON spec with a new top-level field `flow_delta_path` pointing to `flow-delta.json`. Foundry will use this to detect V3 mode.
5. Run the deterministic gate: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate-spec.py <spec.md> <transcript.md>` — if the script reports failures specific to V3 idioms it doesn't understand yet, log them to `concerns.md` and proceed (V3-aware validator is future work).
6. Delete `state.md`.
7. Preserve `transcript.md` and `flow-delta.json` — both are authoritative.
8. Output `<promise>SPEC FORGED</promise>`.

### R4 — shared with V2

R4 VALIDATE runs unchanged. In brownfield it additionally checks:
- `flow-delta.json` exists and passes schema.
- Every file referenced in the delta's packets exists in `project_root` (for `modify-*` change_kinds) OR is a valid new path in the same directory tree as existing files (for `new-*` change_kinds).
- Every packet's `consumes.ref` of kind `existing` resolves to a node in `flow-graph.json`.

### Brownfield failure modes and fallbacks

- **Flow-mapper fails to produce a graph** (returns error or empty): fall back to V2 R0.A (four Explore agents). Log the fallback in `concerns.md`. The user's mode is effectively downgraded to greenfield for this run.
- **Flow-interviewer cannot translate the request** (user's request requires subsystems not in the flow graph): pause R2, re-spawn flow-mapper with a wider scope_hint, then resume R2.
- **User wants to override node-by-node confirmation** (prefers big-bang approval): offer to batch-confirm remaining hops via a single AskUserQuestion showing the full proposed delta — but log a concern noting the override.
