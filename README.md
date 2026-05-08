<p align="center">
  <img src=".github/assets/banner.jpg" alt="Codsworth Marketplace — Forge & Foundry" width="900"/>
</p>

<p align="center">
  <b>Forge plans. Foundry builds.</b><br/>
  <i>A two-plugin marketplace for Claude Code — the spec engine and the build engine, working as one.</i>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/forge-v4.3.0-1E88E5?style=flat-square" alt="Forge v4.3.0"/>
  <img src="https://img.shields.io/badge/foundry-v4.3.0-F57C00?style=flat-square" alt="Foundry v4.3.0"/>
  <img src="https://img.shields.io/badge/Claude%20Code-plugin-8E44AD?style=flat-square" alt="Claude Code plugin"/>
  <img src="https://img.shields.io/badge/license-MIT-2E7D32?style=flat-square" alt="MIT license"/>
</p>

---

## Why Codsworth

Most AI coding tools either **ask and build in one breath** — producing code that drifts from what you actually wanted — or **plan in one context and execute in another**, producing plans that rot on the way to the executor.

Codsworth splits the work cleanly across two specialised plugins and makes them honest partners:

- **Forge** runs a codebase-aware, ecosystem-grounded **interview** and produces a locked, verifiable spec.
- **Foundry** takes the locked spec and runs an **autonomous build-verify-fix loop** with mechanical drift prevention at every handoff.

Both plugins share one discipline: **plans are prompts**. What Forge writes is what Foundry reads, byte for byte. No interpretation layer, no paraphrasing, no "I'll just adjust the scope a little." The spec survives the trip.

---

## The duo

```mermaid
flowchart LR
    idea([Your idea]) --> forge
    subgraph forge[Forge — the spec engine]
        direction TB
        Rpre[R-pre Mode detect] --> R0
        R0[R0 Survey: 4 Explore agents] --> R1
        R1[R1 Synthesize reality] --> R15[R1.5 Research]
        R15 --> R2[R2 Interview + implicit-fact extraction]
        R2 --> R3[R3 Spec + typed tables]
        R3 --> R35[R3.5 Adversarial review]
        R35 --> R4[R4 Validate + version frontmatter]
    end
    forge --> spec[(spec.md + flow-delta.json)]
    spec --> foundry
    subgraph foundry[Foundry — the build engine]
        direction TB
        F0[F0 Research + map] --> F06[F0.6 Pattern map]
        F06 --> F05[F0.5 Decompose]
        F05 --> F07[F0.7 Intent-Carrier]
        F07 --> F09[F0.9 11-dimension validate]
        F09 --> F1[F1 Cast: parallel build + evidence re-exec]
        F1 --> F2[F2 Inspect: 8 streams]
        F2 -->|defects| F3[F3 Grind]
        F3 --> F2
        F2 -->|clean| F4[F4 Assay]
        F4 --> F6[F6 Done]
    end
    foundry --> shipped([Shipped feature])
```

Each plugin has one job and does it well. Forge does not build. Foundry does not interview. They communicate through a single shared artifact — the spec — and every mechanism in the marketplace exists to keep that artifact intact across the handoff.

---

## Quick start

```bash
# In Claude Code: add the marketplace and install the duo
claude plugin marketplace add AlphaBravoCompany/codsworth-marketplace
claude plugin install forge@codsworth
claude plugin install foundry@codsworth

# Wire Foundry's MCP server into your target project
claude mcp add foundry -- uvx --from "git+https://github.com/AlphaBravoCompany/codsworth-marketplace#subdirectory=plugins/foundry/mcp-server" foundry-mcp --project-root .
```

Then, from inside your project:

```bash
# Step 1 — Forge interviews you and produces a spec
/forge:plan "add a workloads page that lists running pods with status and logs"

# ... Forge runs codebase research in parallel, then walks you through a
#     grounded interview, then writes spec.md (and flow-delta.json on
#     brownfield runs) ...

# Step 2 — Foundry takes the spec and builds it
/foundry:start pioneer --spec docs/specs/workloads-page.md
```

From `/foundry:start` onward, Foundry runs fully autonomous until it's done. No approval gates, no checkpoints, no "is this what you wanted?" It builds, verifies, grinds defects until they're gone, then assays the final result against the spec one more time.

---

## Forge — the spec engine

Forge conducts a **codebase-aware specification interview** and produces a foundry-ready spec with every requirement tagged, classified, and locked.

### What makes Forge different

- **Mode detection.** Every run is classified as `brownfield`, `greenfield`, or `cosmetic`. Brownfield runs produce a flow delta against the existing system. Greenfield runs produce an end-state spec. Cosmetic runs skip flow mapping entirely.
- **Parallel codebase research.** Before asking a single question, Forge spawns 4 Explore agents to survey your codebase (architecture, data, surface, infra) in parallel. The interviewer walks in already grounded.
- **R1.5 ecosystem research.** Targeted research into library versions, API shapes, and common gotchas for the feature category — so the interviewer never asks something it could have verified.
- **Brownfield flow grounding.** A `flow-mapper` agent produces a real, LSP-anchored graph of the existing system. The R2 interviewer walks the user through node-by-node hop confirmation, with the entrypoint user-confirmed before any hops are sketched. The output is a `flow-delta.json` of grounded hops, not a free-form end-state description.
- **Implicit-fact extraction (INTV-01).** During R2, the interviewer captures environmental facts the user states in passing — "we're on Postgres 14", "auth is JWT" — as `A-AUTO-NNN` entries with `[IMPLICIT_FACT:*]` tags. Foundry's intent-carrier then verifies every implicit fact survives the trip to a casting prompt.
- **Typed spec tables (TYPE-01).** R3 emits three structured tables — `## Global Invariants`, `## State Transitions`, `## Contracts` — instead of free-form prose. Each row carries a `[from A-NNN]` citation, and the entire table propagates byte-identical into every Foundry casting via `<invariants>` / `<state_transitions>` / `<contracts>` blocks. Phase 6 PROBE, Phase 7 TEST, and Phase 8 INTENT all key off these tables.
- **Versioned spec format (TYPE-02).** Every spec carries `spec_format_version: v2.1` in its frontmatter. Legacy `v2.0` specs continue to build unchanged; downstream agents (PROBE-01, TEST-01, INTENT-01) declare a minimum spec_format_version, and F0.5 DECOMPOSE emits `stream-skipped` records when the spec is older than an agent requires. No silent skews.
- **Spec type classification.** Every feature is tagged `GREENFIELD`, `MIGRATION`, `BUG_FIX`, or `REFACTOR`. Migration specs get enforced source-inventory enumeration: every symbol to port must be named explicitly, no wiggle-word "equivalent coverage" allowed.
- **Requirement classification.** Every item is tagged `Locked` (implement exactly), `Flexible` (teammate discretion), or `Informational` (context only). Foundry teammates honour the classification mechanically.
- **R3.5 adversarial spec review (PROBE-01).** Between R3 SPEC and R4 VALIDATE, an adversarial reviewer reads the draft as if a Foundry teammate would. Every ambiguity, missing citation, or contradictory `[from A-NNN]` chain becomes a `PROBE-NNN` finding. The author resolves them before SPEC FORGED — no half-finished spec reaches Foundry.
- **Verbatim-fidelity gate.** Locked requirements must quote the user verbatim with a transcript citation. The deterministic `validate-spec.py` gate refuses to finalize a spec until every Locked item is byte-identical to the source answer.
- **AskUserQuestion-driven interview.** Structured questions, structured answers — no free-form prompt parsing.

### Forge phases

| Phase | What it does |
|---|---|
| R-pre MODE DETECT | Classifies the run as `brownfield` / `greenfield` / `cosmetic` and confirms with the user |
| R0 SURVEY | 4 Explore agents map architecture, data, surface, and infra in parallel |
| R1 SYNTHESIZE | Merges survey outputs into `reality.md` |
| R1.5 RESEARCH | Targeted online research grounded in survey findings (library versions, ecosystem shapes) |
| R2 INTERVIEW | Adaptive interview with implicit-fact extraction; brownfield mode adds flow-graph + node-by-node hop confirmation |
| R3 SPEC | Writes the final `spec.md` with typed `## Global Invariants` / `## State Transitions` / `## Contracts` tables (plus `flow-delta.json` on brownfield runs) |
| R3.5 PROBE | Adversarial spec reviewer flags ambiguities, missing citations, and contradictory chains before SPEC FORGED |
| R4 VALIDATE | `validate-spec.py` verifies file references, citations, coverage, verbatim fidelity, and `spec_format_version` frontmatter |

---

## Foundry — the build engine

Foundry takes a spec and **autonomously** delivers a working feature, with mechanical verification and drift prevention at every layer.

### What makes Foundry different

- **"Plans are prompts" architecture.** Decompose authors every teammate prompt once at F0.5, saves it to disk, validates it against the master spec, and freezes it. The lead at F1/F3 is a router, not an interpreter — it never re-drafts, paraphrases, or edits teammate prompts. One source of truth, verified mechanically, handed off verbatim.
- **Drift-prevention sextet.** Every casting prompt carries six frozen source-of-truth blocks, byte-identical across every teammate in the run:
  - `<mandatory_rules>` — full CLAUDE.md / AGENTS.md / .cursorrules imperatives, extracted by the codebase mapper
  - `<global_invariants>` — cross-cutting spec rules (auth, validation, security, architectural placement)
  - `<invariants>` — the spec's typed `## Global Invariants` table, propagated row-for-row
  - `<state_transitions>` — the spec's typed `## State Transitions` table, propagated row-for-row
  - `<contracts>` — the spec's typed `## Contracts` table, propagated row-for-row
  - `<spec_requirements>` — the casting's specific spec slice (V2 mode only)
- **F0.6 PATTERN MAPPING.** Before decompose, a `pattern-mapper` agent walks every file the spec will touch and finds the closest analog already in the codebase. Each casting prompt then carries `<analog_pattern>` excerpts (Imports, Setup, Core, Error blocks with `file:line` citations) and `<shared_patterns>` for cross-cutting concerns. Teammates mirror real code, not abstract conventions.
- **F0.7 INTENT-CARRIER (INTENT-01).** Between F0.5 DECOMPOSE and F0.9 VALIDATE, the intent-carrier checks that every transcript `A-NNN` answer the user gave (including `[IMPLICIT_FACT:*]`-tagged ones) survives into at least one casting prompt. Dropped facts surface as `INTENT_DROPPED` defects and block F0.9. Specs older than `v2.1` skip this check; redecomposition is the fix path when an answer is dropped.
- **Brownfield packet-mode prompts.** When the spec carries a flow delta, teammates receive `<upstream_anchor>`, `<prerequisite_hops>`, `<this_hop>`, `<downstream_contract>`, and `<self_check>` blocks instead of an end-state description. There is no end-state to anchor backward from — the failure mode V3 is engineered to prevent.
- **11-dimension F0.9 validation.** A mechanical quality gate that runs before any code is written: requirement coverage, casting completeness, dependency correctness (no file overlap), key links planned, scope sanity, research integration, prompt fidelity (with `<global_invariants>`, `<mandatory_rules>`, and per-typed-table propagation sub-checks 7e/7g/7h/7i/7j, plus 7m intent coverage), migration coverage, spec structure, File-Change-Map ↔ key_files cross-check, and pattern compliance.
- **Server-side evidence re-execution (EVID-01).** When a teammate cites `evidence: $ pytest tests/foo.py` in its completion report, `Foundry-Accept-Casting` re-runs the command server-side, captures stdout/stderr, and stamps a provenance record. Hand-fabricated evidence cannot pass; the spec's evidence chain is mechanically verified.
- **Evidence-to-requirement binding (EVID-02).** Each evidence artifact in the completion report binds to a specific requirement ID. Acceptance refuses any requirement whose evidence binding is missing or stale, so "evidence exists for the casting" can never substitute for "evidence covers this exact requirement."
- **F2 INSPECT — up to 8 verification streams.** After teammates build, Foundry runs in parallel:
  - **TRACE** — LSP-powered upstream wiring (EXISTS → SUBSTANTIVE → WIRED → PLACED)
  - **FLOW_TRACE** — brownfield only; downstream wiring (PRODUCED → CONSUMES_UPSTREAM → SUBSTANTIVE → CHAIN_INTACT)
  - **PROVE** — spec-to-code citation verification with stub detection
  - **RESEARCH_AUDIT** — checks code honours every research recommendation
  - **COVERAGE_DIFF** — 1:1 symbol check for MIGRATION specs
  - **SIGHT** — browser-based UI audit via Playwright
  - **TEST / PROBE** — full test suite + API smoke
  - **TEST_OBSERVATIONS (TEST-01)** — spec-only test derivation. Reads `## Contracts` table, generates Hypothesis property tests, runs them code-blind, emits a `test_observations` report. Catches contracts the implementation forgot to honour.
- **F3 GRIND loop.** Every defect becomes a task attached to the casting it belongs to. Teammates fix, Foundry re-verifies. No partial fixes, no deferred work.
- **F4 ASSAY.** After INSPECT is clean, four fresh-eyes agents re-read the spec, form expectations, *then* read the code. Catches stubs and hollow handlers that passed earlier checks.
- **Requirement-ID citation enforcement.** Before a casting is accepted, the teammate's completion report must cite a `file:line` proof for every requirement ID in its spec slice. Missing citations = rejected, re-dispatched.
- **Methodical teammate.** Teammates are tuned for correctness over wall-clock speed: read floor (depth before writing), approach deliberation (alternatives before committing), blast radius (consequences before editing), competing hypotheses (verification before fixing). CAST teammates deliberate; GRIND teammates stay surgical.
- **Stall watchdog.** The orchestrator tracks time between calls. If the lead sits silent for more than 3 minutes, the next call returns a visible `STALL DETECTED` warning that forces explicit re-engagement.

### Foundry phases

| Phase | What it does |
|---|---|
| F0 RESEARCH | Per-domain researcher agents + optional codebase mapping (extracts `MANDATORY_RULES.md`) |
| F0.6 PATTERN | `pattern-mapper` finds analog files for every spec target; emits `PATTERNS.md` for casting prompts |
| F0.5 DECOMPOSE | Authors castings + verbatim teammate prompts (V2 end-state mode or V3 packet mode) |
| F0.7 INTENT-CARRIER | Verifies every transcript `A-NNN` answer survives into a casting prompt (skipped on `< v2.1` specs) |
| F0.9 VALIDATE | 11-dimension mechanical gate before building |
| F1 CAST | Parallel wave-based building via teammates; `Foundry-Accept-Casting` re-runs cited evidence server-side |
| F2 INSPECT | Up to 8 parallel verification streams |
| F3 GRIND | Fix defects, re-inspect, repeat until clean |
| F4 ASSAY | Fresh-eyes final verification with stub detection |
| F5 TEMPER | Optional — micro-domain stress testing (`--temper`) |
| F5.5 NYQUIST | Optional — regression test generation (`--nyquist`) |
| F6 DONE | Shutdown, report, commit |

---

## What makes the duo different

| Most AI coding tools | Codsworth |
|---|---|
| Ask and build in one breath | Interview → spec → autonomous build, cleanly separated |
| Planner rewrites the prompt for the executor | Plans are prompts — decompose authors once, verbatim everywhere |
| Drift prevention is prose discipline | Drift prevention is mechanical (F0.9 + Accept-Casting + byte-identical propagation) |
| "Looks done" = tests pass | "Looks done" = 9 validation dimensions + up to 7 inspect streams + fresh-eyes assay |
| User approves every phase | Fully autonomous from `/foundry:start` to F6 DONE |
| CLAUDE.md is loaded per agent and hoped-for | CLAUDE.md rules are extracted verbatim and propagated byte-identical into every casting, verified mechanically |
| End-state descriptions everywhere | Brownfield runs use grounded flow deltas — no end-state framing for teammates extending existing systems |
| Bugs are logged for later | Every defect becomes a casting-scoped grind task; no deferrals |

---

## What's new since v4.2.0

Eight orthogonal additions land on the v4.2.0 base — every one is "shipped, tests green, untested in a live cross-cohort matrix." The empirical milestone-level proof of combined defect-rate drop is tracked as Phase 9 / RUN-01 and is deferred until a real-run consolidation lands. Until then, treat each item as "verified by synthetic-fixture suite, not by ablation cohort."

| ID | What it adds | Where it lives |
|---|---|---|
| **INTV-01** | Interview elicits implicit environmental facts as `A-AUTO-NNN` entries with `[IMPLICIT_FACT:*]` tags before SPEC FORGED | Forge R2 |
| **TYPE-01** | V2 spec template gains typed `## Global Invariants` / `## State Transitions` / `## Contracts` markdown tables; rows propagate byte-identical into every casting | Forge R3 → Foundry F0.5 → casting prompt blocks |
| **TYPE-02** | `spec_format_version` frontmatter; legacy `v2.0` specs build unchanged; F0.5 emits `stream-skipped` records when downstream agents declare a higher minimum | Forge R4 → Foundry F0.5 |
| **EVID-01** | `Foundry-Accept-Casting` re-runs cited evidence commands server-side and stamps provenance | Foundry F1 acceptance |
| **EVID-02** | Step-11 completion report binds each evidence artifact to a specific requirement ID; missing binding = acceptance refused | Foundry F1 acceptance |
| **PROBE-01** | Adversarial spec reviewer at R3.5 flags ambiguities, missing citations, and contradictory `[from A-NNN]` chains before SPEC FORGED | Forge R3.5 |
| **TEST-01** | 8th F2 INSPECT stream reads spec only, derives Hypothesis property tests from `## Contracts`, runs them code-blind, emits `test_observations` | Foundry F2 |
| **INTENT-01** | F0.7 intent-carrier checks transcript `A-NNN` coverage in every casting prompt; `INTENT_DROPPED` blocks F0.9 and routes to redecomposition | Foundry F0.7 |

The eight additions touch six F0.9 sub-checks (7e/7g/7h/7i/7j/7m) and bring the validate gate from 9 dimensions to 11.

---

## Under the hood

Foundry's orchestration state lives in an MCP server written in Python, which the `foundry` Lead inside Claude Code calls at every phase transition via tools like `Foundry-Next`, `Foundry-Validate-Castings`, `Foundry-Spawn-Teammate`, `Foundry-Accept-Casting`, and `Foundry-Handoff`. Every casting prompt, every acceptance check, every handoff event is recorded in `foundry-archive/{run}/` under the target project — a full audit trail for every build.

Forge writes specs under `docs/specs/{feature-slug}/spec.md` using a structured template with frontmatter, tagged requirement IDs (`US-N`, `FR-N`, `NFR-N`, `AC-N`), requirement classification, and an embedded verbatim transcript appendix. Brownfield runs additionally write `flow-delta.json` alongside the spec. Foundry's F0.5 DECOMPOSE reads the spec (and flow delta, if present) as its sole source of truth.

---

## Update

```bash
claude plugin marketplace update codsworth
claude plugin update forge@codsworth
claude plugin update foundry@codsworth
```

## Versioning

See [GitHub releases](https://github.com/AlphaBravoCompany/codsworth-marketplace/releases) for the full changelog.

## Contributing

Issues and pull requests welcome at [github.com/AlphaBravoCompany/codsworth-marketplace](https://github.com/AlphaBravoCompany/codsworth-marketplace). If you're adding a new validation dimension, drift-prevention mechanism, or inspect stream, open a discussion first — the "plans are prompts" architecture is load-bearing and worth preserving.

## License

MIT — see [LICENSE](./LICENSE).

---

<p align="center"><i>Forge plans. Foundry builds. You ship.</i></p>
