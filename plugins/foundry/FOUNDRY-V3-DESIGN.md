# Foundry V3 — Design

**Status:** authoritative design spec for the V3 flow-reversal architecture, released as plugin version `4.0.0`. Supersedes `FOUNDRY-V2-DESIGN.md` (which documented the architecture released across plugin versions 2.x–3.6.x). The "V3" label refers to the third generational architecture, not to plugin semver — plugin semver jumped from 3.6.x to 4.0.0 because this is a breaking change.

Grounded in research (`FOUNDRY-V3-FLOW-REVERSAL-DESIGN.md`) and validated by a worked prototype + three tests (`FOUNDRY-V3-PROTOTYPE.md`).

V3's single architectural change: the primary artifact that drives builds is no longer an end-state spec. It is a **flow graph** of the target system plus a **flow delta** describing the additions to that graph. Teammates receive hop contracts, not spec slices. This structurally eliminates endpoint-anchored plumbing hallucination on brownfield builds.

---

## 1. Relationship to other docs

- `FOUNDRY-V3-FLOW-REVERSAL-DESIGN.md` — research, rationale, why V3 exists. Read first if you haven't.
- `FOUNDRY-V3-PROTOTYPE.md` — hand-built worked example on abk8s `/workloads`, plus three tests validating the architecture. Read before implementing.
- `FOUNDRY-V3-DESIGN.md` (this file) — formal schemas, agents, phase sequence, migration. Read to implement.
- `FOUNDRY-V2-DESIGN.md` — predecessor, retained for migration reference.

---

## 2. Operating modes

V3 has three modes. Every run picks exactly one.

| Mode | When | Pipeline |
|---|---|---|
| **brownfield** | existing codebase, flow-shaped request | flow-mapper → flow-interview → delta-decompose → upstream-first cast → flow-trace INSPECT |
| **greenfield** | empty or near-empty target, flow-shaped request | V2 pipeline unchanged (end-state-first is appropriate when there's no upstream to honor) |
| **cosmetic** | non-flow-shaped request (styling, copy, deps, docs, minor refactor) in any codebase | V2-style direct casting — no flow mapping, no delta |

### 2.1 Mode detection

```
1. If --brownfield, --greenfield, or --cosmetic flag passed → use that mode.
2. Otherwise:
   a. Count relevant-language source files under the target paths.
      - Go: *.go (exclude _test.go, vendor/)
      - TS/JS: *.ts, *.tsx, *.js, *.jsx (exclude node_modules/)
      - Python: *.py (exclude venv/, __pycache__/)
      - Rust: *.rs (exclude target/)
      - (extend per language)
   b. If count <= 20 → default greenfield.
   c. Else → classify request via flow-interviewer's first pass:
      - If the request can be satisfied without touching data/control flow
        (styling change, copy edit, dependency bump, README update, minor
        refactor with no behavioral change) → cosmetic.
      - Otherwise → brownfield.
3. Always surface the detected mode to the user and confirm before proceeding.
```

### 2.2 Mode confirmation UX

Forge R0 (or V3 equivalent) emits a single confirmation after detection:

```
Target: /path/to/project (137 Go files)
Request: "Add a /workloads page showing Deployments"
Detected mode: brownfield (flow-shaped)
Proceed? [y/N/change]
  y = continue with brownfield pipeline
  N = abort
  change = force greenfield or cosmetic instead
```

No further questions about mode during the run.

---

## 3. Artifacts

V3 introduces three new artifact types. All are JSON. All are stored under `foundry-archive/{run}/` alongside V2 artifacts.

### 3.1 Flow graph — `flow-graph.json`

A flat graph of the target system. Produced by the flow-mapper agent. Immutable ground truth for the rest of the run. Every existing node MUST have a grounded anchor (file + symbol, line optional but preferred). Verification-enforced — see §6.1.

```json
{
  "schema_version": "v3.0",
  "generated_at": "2026-04-20T12:00:00Z",
  "target_root": "/Users/gsheppard/AB/abk8s",
  "scope_note": "Subsystem relevant to /workloads feature request.",
  "nodes": [
    {
      "id": "web.Start",
      "kind": "func",
      "status": "existing",
      "anchor": {
        "file": "internal/web/server.go",
        "symbol": "Start",
        "line": 26
      },
      "consumes": "addr, token, kubeconfig, auth settings",
      "produces": "running http.Server on addr",
      "description": "Dashboard HTTP server entry point; registers handlers and starts mux."
    },
    {
      "id": "status.Collector.collectNodes",
      "kind": "func",
      "status": "existing",
      "anchor": {
        "file": "internal/status/collector.go",
        "symbol": "Collector.collectNodes",
        "line": 279
      },
      "consumes": "ctx, cached Kubernetes clientset",
      "produces": "[]NodeStatus",
      "description": "Lists nodes, computes NodeStatus per node, silent-nil-on-error, sort.SliceStable by name."
    }
  ],
  "edges": [
    {
      "from": "web.Start",
      "to":   "status.Collector.Collect",
      "kind": "call",
      "payload": null
    },
    {
      "from": "status.Collector.Collect",
      "to":   "status.Collector.collectNodes",
      "kind": "call",
      "payload": "ctx"
    }
  ]
}
```

**Node fields:**

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | Unique within graph. Convention: `pkg.Type.Method` or `pkg.symbol`. |
| `kind` | enum | yes | `func` \| `type` \| `field` \| `route` \| `template` \| `ticker` \| `goroutine` \| `const` \| `config` \| `asset` \| `external` |
| `status` | enum | yes | `existing` \| `new`. Flow graph nodes are all `existing`. `new` appears only in deltas. |
| `anchor.file` | string | `existing` only | Path relative to `target_root`. MUST resolve. |
| `anchor.symbol` | string | `existing` only | LSP-resolvable symbol name in `anchor.file`. |
| `anchor.line` | int | optional | Approximate; hint only, not authoritative. |
| `consumes` | string | yes | Prose. What this node receives or reads. |
| `produces` | string | yes | Prose. What this node emits or writes. |
| `description` | string | yes | One to three sentences. Pattern, behavior, notable constraints (e.g., "silent-nil-on-error"). |

**Edge fields:**

| Field | Type | Required | Meaning |
|---|---|---|---|
| `from` | string | yes | Must be a node `id` in the graph. |
| `to` | string | yes | Must be a node `id` in the graph. |
| `kind` | enum | yes | `call` \| `read` \| `write` \| `trigger` \| `render` \| `http-request` \| `schedule` \| `emit` \| `depends-on` |
| `payload` | string | no | What flows across the edge. Optional prose. |

**Grounding rule (enforced):** every node with `status == "existing"` MUST have `anchor.file` and `anchor.symbol` that resolve via the LSP or grep. A flow graph containing unresolvable existing nodes is invalid.

### 3.2 Flow delta — `flow-delta.json`

Produced by the flow-interviewer agent. Describes the additions to the flow graph that satisfy the user's request. An ordered list of **packets**. Every NEW node MUST have an upstream that either (a) is a `status: existing` node in the flow graph, or (b) is a `produces` of an earlier packet in the same delta.

```json
{
  "schema_version": "v3.0",
  "generated_at": "2026-04-20T12:15:00Z",
  "flow_graph_ref": "flow-graph.json",
  "user_intent_summary": "Add a /workloads page to the abk8s dashboard showing Deployments.",
  "packets": [
    {
      "id": "P1",
      "title": "Add DeploymentStatus type",
      "flow_position": 1,
      "file": "internal/status/collector.go",
      "change_kind": "new-type",
      "consumes": [
        { "kind": "external", "ref": "apps/v1.Deployment shape from k8s.io/api/apps/v1" }
      ],
      "produces": [
        { "node_id": "status.DeploymentStatus", "kind": "type" }
      ],
      "depends_on": [],
      "terminal_slice": "data model underpinning the deployments display"
    },
    {
      "id": "P2",
      "title": "Add Collector.collectDeployments method",
      "flow_position": 2,
      "file": "internal/status/collector.go",
      "change_kind": "new-method",
      "consumes": [
        { "kind": "packet",   "ref": "P1" },
        { "kind": "existing", "ref": "status.Collector.kubeClient" }
      ],
      "produces": [
        { "node_id": "status.Collector.collectDeployments", "kind": "func" }
      ],
      "depends_on": ["P1"],
      "terminal_slice": "deployment list collection"
    }
  ]
}
```

**Packet fields:**

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | Unique within delta. Convention: `P1`, `P2`, ... |
| `title` | string | yes | One line, human-readable. |
| `flow_position` | int | yes | 1 = most upstream. Determines execution order. |
| `file` | string | yes | The one file the packet modifies or creates. A packet touches exactly one file. |
| `change_kind` | enum | yes | `new-file` \| `new-type` \| `new-method` \| `new-field` \| `new-route` \| `new-line` \| `modify-method` |
| `consumes` | array | yes | Refs to either existing flow-graph nodes OR earlier packets' produces. See below. |
| `produces` | array | yes | Declared new flow-graph nodes. Each gets a `node_id`. |
| `depends_on` | array | yes | IDs of packets that must complete before this one. Derived from `consumes` but explicit. |
| `terminal_slice` | string | yes | Which part of the user's end-state this packet contributes to. For traceability only — NOT given to teammates. |

**Consume-reference kinds:**

- `{ "kind": "existing", "ref": "<node_id>" }` — references a node in the flow graph.
- `{ "kind": "packet", "ref": "<packet_id>" }` — references an earlier packet's `produces[0]` in this delta.
- `{ "kind": "external", "ref": "<description>" }` — external to the codebase (k8s API, third-party lib). Unverifiable upstream; acceptable only for packets at `flow_position == 1` or for clearly-documented external contracts.

**Well-formedness rules (enforced — see §6.2):**

1. Every `consumes[*].ref` of kind `existing` must resolve to a node in the flow graph.
2. Every `consumes[*].ref` of kind `packet` must reference a packet with lower `flow_position`.
3. The DAG of `depends_on` edges must be acyclic and consistent with `flow_position` ordering.
4. Every packet must have at least one `consumes` entry.
5. No packet may `produce` a node that collides with an existing flow-graph node.
6. The `terminal_slice` field is required but never propagated to teammates (see §3.3 on why).

### 3.3 Packet → teammate prompt

A packet is not itself a teammate prompt. It is a structured record from which a prompt is generated deterministically. The prompt template has fixed blocks, populated from the packet and its dependencies:

```
<upstream_anchor>
  [file the packet will modify]
  [existing symbols in that file relevant to the packet — from flow-graph anchors]
  [sibling pattern — chosen automatically from a node in the flow graph with the same `kind` and closest file location]
  [what upstream produces, generated from consumes refs]
</upstream_anchor>

<prerequisite_hops>
  [one line per packet in depends_on, each with the specific grep/LSP command to verify that packet's produces]
  VERIFY before writing code:
    $ grep -n "<pattern>" <file>
  If the symbol is absent, STOP — your dependency chain is broken. Do not invent <symbol>.
</prerequisite_hops>

<this_hop>
  [derived from change_kind + packet title + produces]
  Behavior, step by step:
    [generated prose — filled in during decomposition, one concrete step per bullet]
  OUT OF SCOPE:
    [auto-generated from the rest of the delta — explicit list of other packets'
     produces, each phrased as "do NOT do X"]
</this_hop>

<downstream_contract>
  [generated from packets that have this packet in their consumes]
  [the method/file's name and signature are the contract; do not change them]
</downstream_contract>

<self_check>
  1. grep/LSP verification of each prerequisite (repeated from prerequisite_hops)
  2. language-specific build: `go build ./...`, `tsc --noEmit`, etc.
  3. language-specific lint: `go vet`, `eslint`, etc.
</self_check>
```

**What is deliberately NOT in the prompt:**

- `terminal_slice` from the packet (this is traceability metadata, not teammate context).
- The user's original request prose.
- The spec as a whole.
- Other packets' titles or descriptions (only their produces, and only in OUT OF SCOPE).
- Anything describing the final user-visible result beyond what the immediate downstream contract requires.

Validated by Test 2 of the prototype: the teammate stays scoped because the end-state is structurally absent from attention.

### 3.4 Artifact file layout

```
foundry-archive/{run}/
├── mode.json                      # detected mode + confirmation record
├── flow-graph.json                # brownfield only
├── flow-delta.json                # brownfield only (greenfield uses V2 manifests)
├── packets/
│   ├── P1.json                    # individual packet records
│   ├── P2.json
│   └── ...
├── prompts/
│   ├── P1.md                      # generated teammate prompt (for audit)
│   ├── P2.md
│   └── ...
├── concerns.md                    # unchanged from V2
├── defects.json                   # flow-tracer + other INSPECT streams
└── transcript/                    # casting transcripts
```

---

## 4. Phase sequence

### 4.1 Brownfield pipeline

```
R0   FLOW-MAP       flow-mapper builds flow-graph.json for the target paths
R1   RESEARCH       (unchanged from V2 where useful; may be skipped on cosmetic-adjacent asks)
R2   FLOW-INTERVIEW flow-interviewer converts user's end-state request into flow-delta.json;
                    every proposed NEW node validated user-side against the flow graph
R3   FINALIZE       flow-delta.json locked; packets sorted by flow_position
F0   RESEARCH       domain research for tricky packets (inherits V2)
F0.5 DECOMPOSE      generate teammate prompts from packets (deterministic; no LLM creativity)
F1   CAST           teammates execute packets in flow_position order, upstream first;
                    downstream packets blocked until their depends_on complete
F2   INSPECT        flow-tracer (new) + TRACE + PROVE + SIGHT run in parallel;
                    flow-tracer is the primary defect source
F3   GRIND          defects go back to teammates; same packet shape
F4   ASSAY          final adversarial verification (unchanged from V2)
F5   NYQUIST        optional test-coverage audit (unchanged from V2)
```

### 4.2 Greenfield pipeline

Identical to V2. No flow-mapper, no flow-interviewer, no delta-decomposer. End-state-first spec → V2 decomposition → V2 casting → V2 INSPECT. This is correct behavior when there is no upstream to honor.

### 4.3 Cosmetic pipeline

```
R2   INTERVIEW      single-pass classification confirms cosmetic
R3   FINALIZE       produces a minimal spec (V2 format) — usually one or two castings
F1   CAST           V2 teammates; skip flow-tracer since there is no flow
F4   ASSAY          V2 assayer
```

No flow-mapper, no flow-tracer. Fast path for "update the README," "bump lodash," "change the header color."

---

## 5. Agents

### 5.1 New agents

**`flow-mapper`** — produces `flow-graph.json`.
- **Input:** target paths, optional scope hints ("focus on the subsystem around X").
- **Tools:** LSP (primary), grep, glob, file read. No write access except to `flow-graph.json`.
- **Method:** iterative — start from declared entry points (main, handlers, command-line commands), walk callers and callees via LSP `find_references` and `goToDefinition`. Every node added must be anchored. Stops at language/framework boundaries (k8s API, database drivers, HTTP libraries — marked as `external`).
- **Validation:** every existing node's anchor is LSP-resolvable. Fails if not.
- **Output location:** `foundry-archive/{run}/flow-graph.json`.

**`flow-interviewer`** — produces `flow-delta.json`.
- **Input:** `flow-graph.json`, user request (prose), session history.
- **Tools:** read-only access to codebase, the flow graph, and an interactive conversation surface.
- **Method:**
  1. Classify request as brownfield-flow-shaped, cosmetic, or mixed.
  2. For flow-shaped: propose a hop list (NEW nodes + their upstream anchors) and walk the user through it node-by-node.
  3. For each proposed NEW node, the user confirms the upstream is correct or redirects.
  4. Emits the validated delta as `flow-delta.json`.
- **Validation:** the delta must pass all well-formedness rules in §3.2.
- **Critical behavior:** NEVER includes end-state description in the delta's per-packet fields beyond `terminal_slice` (which is not propagated to teammates).

**`flow-tracer`** — new INSPECT stream.
- **Input:** `flow-graph.json`, `flow-delta.json`, built code.
- **Tools:** LSP, grep, read.
- **Method:** for each packet in the delta, verify the packet's `produces` nodes exist in the code AND actually consume what their `consumes` declares. Walks forward from declared origin.
- **Output:** defects for any broken forward edge. Primary failure modes caught: (a) packet's produces missing; (b) produces exists but does not consume its declared upstream (e.g., an endpoint that hardcodes `[]` instead of calling the upstream method); (c) produces exists but shape differs from declared.

### 5.2 Existing agents with modified behavior

**`teammate`** (renamed from `foundry:teammate`) — receives packet-derived prompts in brownfield mode, V2 prompts in greenfield/cosmetic mode. Same execution engine.

**`tracer`** — retained. Runs after flow-tracer in INSPECT. Covers the same four levels (EXISTS, SUBSTANTIVE, WIRED, PLACED) for upstream wiring. Flow-tracer covers downstream.

**`assayer`** — retained, unchanged.

**`codebase-mapper`** — retained for V2 compatibility; no longer the primary mapper for brownfield (superseded by flow-mapper).

**`researcher`** — retained, domain-agnostic; may be invoked in either pipeline.

### 5.3 Removed agents

None. V3 additions are purely additive. V2 agents remain for greenfield and cosmetic modes.

---

## 6. Verification

Verification is layered. Earlier layers are cheaper and catch more.

### 6.1 Flow graph validation (schema + grounding)

Runs immediately after flow-mapper emits `flow-graph.json`. A dedicated validator:

1. Schema validation against JSON Schema (all required fields present, enums legal).
2. Every existing node's `anchor.file` path resolves under `target_root`.
3. Every existing node's `anchor.symbol` resolves via LSP in `anchor.file` (or grep-match if LSP unavailable for the language).
4. Every edge's `from` and `to` reference a node that exists in the graph.
5. Acyclicity check (the graph MAY have cycles legitimately — e.g., callbacks — so this is a warning, not a failure, but is logged).

Failure here aborts the run before any interview happens. Fixing requires re-running flow-mapper or hand-editing the graph (logged to `concerns.md`).

### 6.2 Flow delta validation (schema + well-formedness)

Runs immediately after flow-interviewer emits `flow-delta.json`. Validator checks:

1. JSON Schema.
2. Every `consumes[*].ref` of kind `existing` resolves to a flow-graph node.
3. Every `consumes[*].ref` of kind `packet` references a packet with lower `flow_position`.
4. `depends_on` edges form a DAG with no cycles.
5. No packet produces a node colliding with an existing flow-graph node's `id`.
6. Every packet has at least one `consumes`.
7. At least one packet has `flow_position == 1`.

Failure here returns to flow-interviewer for correction.

### 6.3 Teammate self-check (per-packet)

Teammates run the specific grep/LSP commands declared in their prompt's `<self_check>`. Binary results, no ambiguity. Validated by Test 3 of the prototype — when a prerequisite grep returns empty, the teammate STOPS.

### 6.4 Flow-tracer INSPECT (post-cast)

See §5.1. Primary forward-direction verifier. Pairs with `tracer` (upstream direction).

### 6.5 Assayer final gate

Unchanged from V2. Adversarial spec-before-code verification. In brownfield, the "spec" from the assayer's perspective is the flow delta — each packet's `produces` is an expectation to be verified against code.

---

## 7. Migration from V2

V2 runs in flight at the time of V3 release complete on V2. V3 takes effect on the next `foundry:start` invocation.

- No schema migration of historical `foundry-archive/` records.
- `FOUNDRY-V2-DESIGN.md` retained as historical reference.
- Version bump: Foundry v2.x → v3.0.0. Breaking change flagged in the changelog.
- Plugin users who prefer V2 can pin to the last v2 tag.

### 7.1 What users need to know

- New mode confirmation prompt at the start of every run.
- Brownfield runs may take longer on R0 because flow-mapper does real LSP traversal. A flow graph is cached per (target-path, commit-sha) tuple and reused across runs.
- Greenfield and cosmetic behavior is identical to V2.

---

## 8. Open questions

The prototype validated the core architecture but left these open:

1. **Flow-mapper scope control.** On a 500k-LOC monorepo, mapping everything is intractable. How does flow-mapper know what scope to map? Candidate: the user's request drives an initial scope ("paths that mention 'workloads' or related terms"); flow-mapper expands iteratively along edges until reaching declared boundaries or a size cap. Needs prototyping.

2. **Cross-flow requests.** Some features touch multiple subsystems with disjoint flows (e.g., "add audit logging to all API endpoints"). Modeling this: multiple partial flow graphs plus a delta that spans them. Needs design work.

3. **Flow-mapper quality audit.** How do we know the flow graph is *correct*? A pass that generates it can also miss edges. Candidate: a secondary audit pass that checks every edge in the graph against static analysis, and flags edges not explainable by static call-graph data. Not critical for v3.0.0 but needed for v3.1.

4. **Prompt-generation determinism.** Sibling-pattern selection (which existing node's description becomes the pattern block in the prompt) is auto-derived from the flow graph. Deterministic rule needs specification: "same kind, shortest path in graph, tied by file proximity." Testable. Write a spec.

5. **Delta-interviewer UX.** The node-by-node validation with the user could become tedious for large deltas. Candidate: batch confirmation with a visual graph diff. Deferred to v3.1.

6. **Pattern-description lying problem (from Test 1).** The upstream_anchor describes a sibling pattern. If this description is transcribed by an LLM rather than extracted from real code, it can be wrong. Mitigation: the prompt generator reads the sibling's anchored file region directly and includes a verbatim excerpt (not a paraphrase). No LLM between the code and the teammate.

7. **Language support cadence.** v3.0.0 targets Go, TS/JS, Python, Rust for LSP-backed flow-mapping. Other languages degrade to grep-based anchoring (weaker grounding; may produce lower-quality graphs). Document which languages get full support, which get degraded, and the quality tradeoff.

---

## 9. Phase-by-phase implementation order

Per `FOUNDRY-V3-FLOW-REVERSAL-DESIGN.md` "The Plan" and the test results:

1. **Phase 1 (this doc).** Design spec. ✓
2. **Phase 2.** Build `flow-mapper` agent. First pass: Go-only. Verify output against hand-built prototype graph for abk8s.
3. **Phase 3.** Rebuild Forge R2 interview for brownfield (`flow-interviewer`). Prototype node-by-node validation UX.
4. **Phase 4.** Build `delta-decomposer` — the deterministic packet → prompt generator. Validate on the abk8s delta from the prototype doc.
5. **Phase 5.** Update `teammate` to recognize the new prompt shape (additive; V2 prompts still work). Update `start.md` to branch on mode.
6. **Phase 6.** Build `flow-tracer` INSPECT agent.
7. **Phase 7.** Version bump to v3.0.0, migration notes, changelog.

Each phase has a validation hurdle against the abk8s `/workloads` prototype. If a phase's output diverges from the hand-built prototype's shape, stop and debug before proceeding.
