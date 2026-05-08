---
active: false
engine: forge
version: "2.0.0"
phase: "SPEC FORGED"
iteration: 1
max_iterations: 0
started_at: "2026-05-08T17:39:05Z"
finalized_at: "2026-05-08T17:39:05Z"
spec_type: "GREENFIELD"
entrypoint_node_id: ""
entrypoint_anchor: ""
feature_name: "phase9-sloppy"
feature_slug: "phase9-sloppy"
output_dir: "forge-specs"
spec_path: "forge-specs/phase9-sloppy/spec.md"
spec_format_version: "v2.1"
json_path: "forge-specs/phase9-sloppy/spec.json"
progress_path: "forge-specs/phase9-sloppy/progress.txt"
draft_path: "forge-specs/phase9-sloppy/draft.md"
transcript_path: "forge-specs/phase9-sloppy/transcript.md"
state_path: "forge-specs/phase9-sloppy/state.md"
survey_dir: "forge-specs/phase9-sloppy/survey"
reality_path: "forge-specs/phase9-sloppy/survey/reality.md"
context_file: ""
no_survey: false
first_principles: false
focus_dirs: ""
user_prompt: "Synthetic adversarial corpus for Phase 9 ablation runs (CONTEXT.md §Implementation Decisions §Candidate spec triggers a-h)"
---

# Forge Specification Engine — phase9-sloppy

This is the R-phase state file for the Phase 9 synthetic adversarial corpus. The spec was hand-authored once at the SPEC FORGED milestone and is replayed verbatim across all 10 cohorts in the Phase 9 ablation matrix.

## Phase

`SPEC FORGED` — spec.md, transcript.md, and survey/reality.md are committed; the spec is ready for /foundry:start replay against each cohort's disable lever.

## Synthetic Adversarial Trigger Surfaces

Each surface enumerated here corresponds to a Phase 9 cohort's disable-lever target (see `.planning/phases/09-milestone-real-run-consolidation/09-CONTEXT.md` §Implementation Decisions §Candidate spec):

- **(a) INTV-01 trigger**: A-AUTO-001..A-AUTO-004 entries in transcript.md with `[IMPLICIT_FACT:DEPLOYMENT|RUNTIME|FRAMEWORK_VERSION|SCALE]` tags. The `no_INTV_01` cohort strips the tags but keeps the entries.
- **(b) TYPE-01 trigger**: `## Global Invariants` / `## State Transitions` / `## Contracts` typed-table sections in spec.md, each row citing `[from A-NNN]`. The `no_TYPE_01` cohort strips these sections.
- **(c) TYPE-02 trigger**: `spec_format_version: v2.1` frontmatter in spec.md. The `no_TYPE_02` cohort flips to `v2.0` (cascades stream_skips for EVID-01/PROBE-01/TEST-01/INTENT-01 by construction).
- **(d) EVID-01 trigger**: casting-side, emerges during F1 CAST when teammate-emitted evidence files are evaluated. Disabled by `casting_commit=None` for every Foundry-Accept-Casting call.
- **(e) EVID-02 trigger**: casting-side, requires `# evidence-for: US-N, FR-N` headers on committed evidence files. Disabled by stripping the headers.
- **(f) TEST-01 trigger**: CT-001 `mode` branch in spec.md `## Contracts` table — the response-shape divergence under `hypothesis-jsonschema` strategies.
- **(g) PROBE-01 trigger**: A-006's "The cap is 5000" Locked answer carries residual ambiguity (unit unstated; resolves to bytes-context only via A-002's "x is the payload size in bytes"). PROBE-01's R3.5 reviewer should surface this with an A-NNN-cited flag.
- **(h) INTENT-01 trigger**: A-007's branch-binding constraint that decompose would naturally drop without the F0.7 INTENT-CARRIER cross-check (the constraint does not name a specific surface element; it is a meta-process rule).
