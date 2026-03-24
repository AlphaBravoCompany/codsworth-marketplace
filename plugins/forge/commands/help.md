---
description: "Explain the Forge workflow and available commands"
---

# Forge Help

Please explain the following to the user:

## What is Forge?

**Forge plans. Foundry builds.**

Forge is a codebase-aware specification engine that deeply researches your code before conducting an adaptive interview. It combines GSD-style parallel research agents with Lisa-style progressive interviews to produce foundry-ready specifications.

Unlike traditional spec interviews that ask generic questions, Forge:
- **Surveys your codebase first** with 4 parallel research agents
- **Grounds every question** in actual code patterns, models, and architecture
- **Produces foundry-native specs** with US/FR/NFR/AC/OT IDs and real file references

## How It Works

```
R0: SURVEY     -> 4 parallel agents explore your codebase
R1: SYNTHESIZE -> Merge findings into a "codebase reality" document
R2: INTERVIEW  -> Multi-round adaptive interview grounded in findings
R3: SPEC       -> Generate foundry-ready specification
R4: VALIDATE   -> Self-check all file references and coverage
```

## Available Commands

### /forge:plan <FEATURE_NAME> [OPTIONS]

Start a new codebase-aware specification interview.

**Usage:**
```
/forge:plan "user authentication"
/forge:plan "payment processing" --context docs/PRD.md
/forge:plan "search feature" --focus src/search,src/api
/forge:plan "new dashboard" --first-principles
/forge:plan "greenfield api" --no-survey
```

**Options:**
- `--context <file>` — Initial context file (PRD, GSD research, requirements)
- `--output-dir <dir>` — Output directory for specs (default: docs/specs)
- `--max-questions <n>` — Maximum question rounds (default: unlimited)
- `--no-survey` — Skip codebase survey (for greenfield/empty projects)
- `--first-principles` — Challenge assumptions before detailed spec gathering
- `--focus <dirs>` — Comma-separated directories to focus survey on

### /forge:resume

Resume an interrupted specification interview.

**Usage:**
```
/forge:resume
```

If you have interrupted interviews (session ended mid-interview), this command will:
1. List all in-progress interviews with feature names, timestamps, and current phase
2. Let you select which interview to resume
3. Continue from the exact phase where it left off (even mid-survey)

### /forge:cleanup

Clean up all Forge interview state files.

**Usage:**
```
/forge:cleanup
```

Options to clean up state files only or state files + survey data.
Does NOT delete completed specs in `docs/specs/`.

### /forge:help

Show this help message.

## Survey Agents

Forge spawns 4 parallel Explore agents during the SURVEY phase:

| Agent | Explores | Discovers |
|-------|----------|-----------|
| **Architect** | Package structure, layers, patterns | How the app is organized |
| **Data** | Models, schemas, data flow | What data structures exist |
| **Surface** | APIs, routes, UI, exports | What's exposed and extensible |
| **Infra** | Tests, CI, deps, config | What tooling and patterns exist |

Survey data is saved to `docs/recon/{feature-slug}/` for reference.

## Interview Style

The interview works exactly like Lisa — multi-round, adaptive, progressive:
- Uses AskUserQuestion for every question (proper UI, not text prompts)
- Domain-adaptive question banks (auth, API, data, frontend, infra, etc.)
- Red flag detection ("just", "simple", "ASAP" trigger deeper probing)
- Continues until you say "done" or "finalize"

The key difference: every question references specific findings from the survey.

## Output

**During interview:**
- Draft spec: `.claude/forge-draft.md`
- Survey data: `docs/recon/{slug}/survey/`
- Reality doc: `docs/recon/{slug}/reality.md`

**After finalization:**
- Markdown spec: `docs/specs/{slug}.md`
- JSON spec: `docs/specs/{slug}.json`
- Progress file: `docs/specs/{slug}-progress.txt`

## Spec Format (Foundry-Compatible)

The generated spec uses foundry-native ID schemes:
- **US-NNN** — User Stories
- **FR-NNN** — Functional Requirements
- **NFR-NNN** — Non-Functional Requirements
- **AC-NNN** — Acceptance Criteria
- **OT-NNN** — Observable Truths (foundry verification targets)

Each user story includes a **Codebase Integration** section referencing real files and patterns.

## Complete Workflow

```
1. Forge plans:    /forge:plan "my feature"
2. Foundry builds: /foundry --spec docs/specs/my-feature.md
```

Forge plans. Foundry builds. Ship with confidence.

## Using with GSD Research

If you've already run GSD research (`/gsd:new-project`), pass it as context:

```
/forge:plan "my feature" --context .claude/lisa-context-my-feature.md
```

Forge will detect GSD research and adapt the interview to skip already-answered questions while probing gaps.

## Comparison

| | Lisa | Forge |
|---|------|-------|
| Codebase research | None | 4 parallel agents |
| Question grounding | Generic | References real files/patterns |
| Spec output | Markdown | Markdown + JSON + OTs |
| Foundry integration | Needs /decompose | Native (US/FR/NFR/AC/OT IDs) |
| Resume support | Yes | Yes (phase-aware) |
| GSD integration | Via bridge script | Native detection |
