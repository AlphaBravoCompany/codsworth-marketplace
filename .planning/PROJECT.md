# Codsworth Marketplace — Forge/Foundry Quality Redesign

## What This Is

A Claude Code plugin marketplace housing **Forge** (codebase-aware spec interview, V2 free-form + V3 flow-graph brownfield modes) and **Foundry** (build-verify-fix agent loop with CAST → INSPECT → GRIND → ASSAY phases). Used by Garrett (plugin author) and downstream AI-assisted developers to spec features and have agent teams implement them with structural defenses against AI-generated sloppy work.

The current milestone is a **quality redesign**: closing five structural gaps that allow sloppy AI output to slip past Foundry's verification streams.

## Core Value

Foundry runs ship **provably correct** code in one or two cycles, with verification grounded in upstream evidence (typed spec contracts, execution traces, adversarial spec-anchored checks) — not in a browser-based UI testing stream that may or may not run.

## Requirements

### Validated

<!-- Capabilities already shipped in v4.2.0 and observed working -->

- ✓ **Forge V3 brownfield mode** — flow-graph + flow-delta + node-by-node interview — existing
- ✓ **Forge V2 spec interview** — free-form Locked/Flexible/Informational classification with verbatim transcript — existing
- ✓ **Foundry F0-F6 build-verify-fix loop** — RESEARCH → DECOMPOSE → CAST → INSPECT → GRIND → ASSAY → DONE — existing
- ✓ **Adversarial assayer (PROVE)** — spec-before-code methodology, Squidward-mode tone, stub-pattern library — existing
- ✓ **7-stream INSPECT phase** — TRACE / FLOW_TRACE / PROVE / RESEARCH_AUDIT / COVERAGE_DIFF / SIGHT / TEST — existing
- ✓ **Architectural placement check** — `## Global Invariants` propagation with PLACED/MISPLACED verdict — existing
- ✓ **Deterministic spec validator** — `validate-spec.py` enforces verbatim transcript citations — existing
- ✓ **Teammate deliberation procedures** — Read Floor + Approach Deliberation + Blast Radius + Stall Check — existing
- ✓ **Casting acceptance gate** — `Foundry-Accept-Casting` mechanically verifies requirement-ID citations — existing

### Active

<!-- v1 of the quality redesign milestone. Hypotheses until shipped + validated. -->

- [ ] **TYPE-01**: V2 spec template gets typed sections (invariants table, state-transition table, contracts table) enforced by `validate-spec.py`
- [ ] **TYPE-02**: V2 free-form interview converges toward V3's structural shape where applicable (without breaking V2 spec consumers)
- [ ] **EVID-01**: `Foundry-Accept-Casting` rejects castings without committed execution evidence (test output, REPL log, curl session, or log lines demonstrating the behavior)
- [ ] **EVID-02**: Teammate's Step-11 completion report includes execution-evidence file paths alongside requirement citations
- [ ] **PROBE-01**: New adversarial spec-reviewer agent runs after R3 SPEC, before SPEC FORGED. Reads draft spec + transcript, flags ambiguities citing specific A-NNN entries, blocks finalization until resolved
- [ ] **INTENT-01**: New intent-carrier agent runs at F0.5 DECOMPOSE. Reads transcript + emitted casting prompts, flags transcript constraints not present in any casting prompt, blocks F0.9 VALIDATE until resolved
- [ ] **TEST-01**: New spec-derived failing-test stream in F2 INSPECT. Reads spec FIRST, builds verification checklist, generates minimal failing tests, runs them. Distinct attention from PROVE (which reads code). Pairs with TRACE/FLOW_TRACE for cross-direction coverage
- [ ] **RUN-01**: Real-run validation on a previously-sloppy build (e.g., a recent abk8s feature run) confirms defect rate drops measurably with all v1 interventions enabled

### Out of Scope

<!-- Explicit boundaries — reasons documented to prevent re-adding. -->

- Replacing SIGHT — SIGHT remains available; the milestone goal is that quality does not *depend* on SIGHT, not that SIGHT is removed
- Rewriting Forge V3 brownfield mode — V3's flow-graph + node-by-node is already structurally strong; touching it risks regression
- New plugin types — this milestone is Forge/Foundry quality, not new product surface
- Browser-based testing streams — explicit user constraint: do not lean on browser tooling as the safety net
- Migrating away from markdown-driven plugin commands — plugin format stays as-is
- Severity classification of defects — Foundry already forbids severity tiers; this milestone preserves "every non-VERIFIED is a defect"

## Context

**The diagnosis** (gathered during /gsd:new-project questioning, 2026-05-01):

Sloppy Foundry output has five structural causes, each with partial existing machinery and a specific gap:

1. **Interviews enumerate, don't probe.** V3 has node-by-node anti-forced-decision discipline; V2's free-form interview lacks an adversarial pass. Gap: no agent reads the draft V2 spec for residual ambiguity before finalization.
2. **Spec-as-text is lossy.** V3's `flow-delta.json` + `flow-graph.json` is structurally checkable; V2 still uses Locked/Flexible/Informational markdown. Gap: V2 spec format has no typed contracts/invariants/state-transitions, so the spec validator can only check verbatim citations, not structural completeness.
3. **ASSAY is the same LLM doing a read.** Already 7 streams of different attention; assayers all read spec → code. Gap: no stream that reads spec, derives expected behavior, generates failing tests, runs them — a code-blind verification anchored only to spec.
4. **Nobody runs the thing (without SIGHT).** Teammate self-check runs build + tests, but tests can be authored by the same teammate who wrote the code. Gap: acceptance gate doesn't require *evidence* of execution producing observed behavior.
5. **Context handoffs lose intent.** Mandatory rules and global invariants propagate byte-identically; transcript is preserved verbatim in spec appendix. Gap: casting prompts derive from spec excerpt, never cross-checked against the full transcript — constraints stated in the interview but not synthesized into spec text are silently dropped.

**Why now:** Recent runs (notably on abk8s and similar brownfield builds) felt sloppy — false-VERIFIED verdicts triggered F4→F3→F2→F4 bounces, downstream teammates fabricated plausible-but-wrong middle plumbing, and ambivalence in V2 specs got rationalized into forced decisions. V3 brownfield mode addresses some of this for flow-shaped requests; V2 still produces the bulk of feature work and is the weakest path.

**Plugin structure** (for downstream agents):
- `plugins/forge/` — `commands/{plan,resume,cleanup,help}.md`, `agents/{flow-interviewer,researcher}.md`, scripts, validate-spec.py
- `plugins/foundry/` — `commands/{start,resume,setup,stop,status,help}.md`, `agents/{teammate,assayer,tracer,flow-tracer,coverage-diff,research-auditor,research-synthesizer,researcher,nyquist-auditor,codebase-mapper,flow-mapper}.md`, MCP server, scripts, skills (sight, prove, temper, trace), references (lead-discipline, verification-patterns)
- The MCP server (`plugins/foundry/mcp-server/`) is where casting acceptance, gate logic, and state machines live — most v1 changes will touch agent prompts + MCP tool definitions

## Constraints

- **Plugin format**: Stay on markdown-driven Claude Code plugin commands + bash scripts + Python helper for validate-spec — no new runtime dependencies
- **Backwards compatibility**: Existing v4.2.0 spec files (already shipped, tracked in dependent projects) must still build under the new path. V2 path stays runnable; typed sections are additive.
- **No browser dependency**: All v1 quality interventions must work without Playwright/SIGHT. SIGHT remains as one of seven INSPECT streams but is not load-bearing.
- **Verification preserves no-severity rule**: New streams cannot introduce severity tiers — every non-passing verdict is a defect.
- **Real-run validation gate**: Milestone is not "done" until a previously-sloppy build is re-run and the defect rate drops observably.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| All five interventions in v1, not iterated subset | User explicitly chose comprehensive scope over staged validation | — Pending |
| "Done" = real-run validation passes, not just unit-tests-of-tools | Diagnosis is about emergent quality, must be confirmed end-to-end | — Pending |
| SIGHT not the safety net | Explicit user constraint — upstream evidence is the lever | — Pending |
| V2 typed-section format is additive (not breaking) | Existing specs in dependent projects must still build | — Pending |
| New agents only where attention differs from primary (adversarial vs. constructive, spec-first vs. code-first) | Avoid handoff-multiplication that worsens cause #5 | — Pending |

---
*Last updated: 2026-05-01 after initialization*
