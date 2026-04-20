# Foundry V3 Prototype — abk8s `/workloads` worked example

**Status:** hand-built prototype, not production. Goal: see whether the V3 artifact chain actually removes end-state anchoring before committing to a rewrite. Grounded in real abk8s code as of 2026-04-20.

Contains: (1) flow graph schema, (2) existing abk8s subsystem flow graph, (3) flow delta for `/workloads`, (4) sample V3 teammate prompt for one hop, (5) analysis of whether the prototype works.

---

## 1. Flow Graph Schema

A flow graph is JSON. Two record kinds: nodes and edges.

### Node

```
{
  "id":          "collectNodes",                    // unique within graph
  "kind":        "func" | "type" | "route" | "template" | "ticker" | "goroutine" | "field",
  "status":      "existing" | "new",
  "anchor": {                                        // null when status=new
    "file":   "internal/status/collector.go",
    "symbol": "Collector.collectNodes",
    "line":   218
  },
  "consumes":    "*kubernetes.Clientset + context", // prose is fine
  "produces":    "[]NodeStatus",
  "description": "Lists nodes via typed client, computes NodeStatus per node, returns slice. Silent on error (returns nil)."
}
```

Rule: every `existing` node MUST have a grounded anchor (file, symbol, and optionally line). `grep` or LSP proved it. No node enters the graph on vibes.

### Edge

```
{
  "from":    "refreshLoop",
  "to":      "doCollect",
  "kind":    "call" | "read" | "write" | "trigger" | "render" | "http-request" | "schedule" | "emit",
  "payload": "tick"                                  // optional — what flows across
}
```

Rule: every edge's `from` and `to` must be node IDs that exist in the graph.

That's the whole schema. Deliberately flat. No hierarchy, no nesting — a graph is a graph.

---

## 2. Pre-workloads abk8s Flow Graph (real, grounded)

This is the state of abk8s *before* `/workloads` is added — what V3 would see on R0.

Only the subsystem touched by `/workloads` is mapped. A full abk8s flow graph would be larger.

### Nodes

| id | kind | status | anchor | produces / consumes |
|---|---|---|---|---|
| `web.Start` | func | existing | `internal/web/server.go:26` | starts http server; consumes addr/token/kubeconfig; produces running mux |
| `parsePages` | func | existing | `internal/web/server.go:108` | reads `templates/` dir; produces `map[string]*template.Template` |
| `dashboard` | type | existing | `internal/web/server.go:70` | holds collector, pages, latest *ClusterStatus |
| `dashboard.refreshLoop` | goroutine | existing | `internal/web/server.go:140` | 5s ticker; calls doCollect |
| `dashboard.doCollect` | func | existing | `internal/web/server.go:156` | calls Collector.Collect; writes d.latest |
| `dashboard.renderPage` | func | existing | `internal/web/server.go:182` | reads d.latest; executes template; writes html |
| `dashboard.handleOverview` | func | existing | `internal/web/server.go:203` | GET /; renderPage("overview.html") |
| `dashboard.handleNodes` | func | existing | `internal/web/server.go:211` | GET /nodes; renderPage("nodes.html") |
| `dashboard.handlePods` | func | existing | `internal/web/server.go:215` | GET /pods; renderPage("pods.html") |
| `dashboard.handleAPIStatus` | func | existing | `internal/web/server.go:240` | GET /api/v1/status; writes JSON of d.latest |
| `status.Collector` | type | existing | `internal/status/collector.go` (Collector type) | aggregates all collect* methods |
| `status.Collector.Collect` | func | existing | `internal/status/collector.go:Collect` | orchestrator; calls collectNodes/collectPods/etc; produces *ClusterStatus |
| `status.Collector.collectNodes` | func | existing | `internal/status/collector.go:~218` | clientset + ctx → []NodeStatus (pattern: 15s timeout, silent-nil-on-error, SliceStable) |
| `status.Collector.collectPods` | func | existing | `internal/status/collector.go` | clientset + ctx → PodSummary |
| `status.Collector.kubeClient` | func | existing | `internal/status/collector.go` | cached typed clientset |
| `status.ClusterStatus` | type | existing | `internal/status/collector.go:32` | aggregate struct {Nodes, Pods, Addons, Certs, Security, Components, ...} |
| `k8s.ClientFactory` | type | existing | `internal/k8s/client.go:14` | kubeconfig → typed + dynamic clients |
| `templates/layout.html` | template | existing | `internal/web/templates/layout.html` | nav + `<main>` slot; active-class for `.Page` |
| `templates/nodes.html` | template | existing | `internal/web/templates/nodes.html` | renders `.Nodes` table or empty state |
| `templates/overview.html` | template | existing | `internal/web/templates/overview.html` | renders `.dashboard-grid` of cards |
| `static/style.css` | asset | existing | `internal/web/static/style.css` | has `.status-healthy`, `.status-failed`, `.card`, `.dashboard-grid` |

### Edges (subset — flow-relevant)

```
web.Start        --call-->       parsePages         (loads templates at startup)
web.Start        --go-->         dashboard.refreshLoop
dashboard.refreshLoop --tick-->  dashboard.doCollect (every 5s)
dashboard.doCollect   --call-->  status.Collector.Collect
status.Collector.Collect --call--> status.Collector.collectNodes
status.Collector.Collect --call--> status.Collector.collectPods
status.Collector.collectNodes --call--> status.Collector.kubeClient
status.Collector.kubeClient   --read--> k8s.ClientFactory
status.Collector.Collect --write--> status.ClusterStatus   (payload: populated struct)
dashboard.doCollect      --write--> dashboard.latest        (payload: *ClusterStatus)
HTTP GET /nodes          --http-request--> dashboard.handleNodes
dashboard.handleNodes    --call-->  dashboard.renderPage    (payload: "nodes.html")
dashboard.renderPage     --read-->  dashboard.latest
dashboard.renderPage     --render-->templates/nodes.html
templates/nodes.html     --emit-->  HTML response
```

**Key observation from the graph:** every existing page (`/nodes`, `/pods`, `/overview`) is the *terminus* of a chain that begins with a tick → Collect → collect* → ClusterStatus field → template. The pattern is already there. `/workloads` isn't a novel shape; it's another instance of a well-established shape.

---

## 3. Flow Delta — `/workloads`

The user's request ("a Workloads page showing Deployments") translates to **extending the graph with eight new nodes in a specific order**. Each new node declares its upstream (existing or earlier-hop) and its downstream consumer.

### Hop list (ordered — upstream first)

| # | New node | Upstream (consumes from) | Downstream (consumed by) | File |
|---|---|---|---|---|
| 1 | `DeploymentStatus` (type) | apps/v1.Deployment shape (k8s API external) | hops 2, 3 | `internal/status/collector.go` |
| 2 | `Collector.collectDeployments` (func) | hop 1 + `Collector.kubeClient` (existing) + ctx | hop 4 | `internal/status/collector.go` |
| 3 | `ClusterStatus.Deployments` (field) | hop 1 | hops 4, 6, 9 (overview) | `internal/status/collector.go` |
| 4 | `Collect` wiring (line added) | hops 2 + 3 + existing `Collector.Collect` | hop 5 via `dashboard.latest` | `internal/status/collector.go` |
| 5 | `templates/workloads.html` (file) | hop 3 via `pageData.Deployments` | hop 6 | `internal/web/templates/workloads.html` |
| 6 | `dashboard.handleWorkloads` (func) | `dashboard.renderPage` (existing) + hop 5 | hop 7 | `internal/web/server.go` |
| 7 | `/workloads` mux route (line added) | hop 6 | HTTP GET /workloads | `internal/web/server.go:Start` |
| 8 | `layout.html` nav link (line added) | existing page nav pattern | browser | `internal/web/templates/layout.html` |

Secondary hops (can run in parallel once their upstream is ready):
- 9: overview card (consumes hop 3)
- 10: TUI `workloads.go` (consumes hop 3)
- 11: TUI `app.go` registration (consumes hop 10)

### The shape is all forward

No hop says "the user sees a /workloads page." The user-visible page emerges as the final node in the chain because each hop produces the thing its downstream consumes. The terminal state is a **consequence** of a grounded chain, not a **specification** that the chain is supposed to match.

---

## 4. Sample V3 Teammate Prompt (hop 2: `collectDeployments`)

This is what a V3 teammate would actually receive to build hop 2. Compare to what V2 would have sent: the entire 444-line spec.

```
<upstream_anchor>
You are extending a verified flow in abk8s. The upstream of your work is real code that exists today.

FILE YOU WILL MODIFY: internal/status/collector.go
EXISTING SYMBOLS (verified via grep, do not modify):
  - type Collector struct         (~line 136 region)
  - func (c *Collector) Collect(ctx) *ClusterStatus   (~line 147)
  - func (c *Collector) collectNodes(ctx) []NodeStatus (~line 218)  ← pattern you will mirror
  - func (c *Collector) collectPods(ctx) PodSummary
  - func (c *Collector) kubeClient() (*kubernetes.Clientset, error)

PATTERN: collectNodes is your template. It:
  - Takes context.Context, returns a slice (or nil on error).
  - Calls c.kubeClient() → typed clientset; returns nil if that errors.
  - Wraps ctx in context.WithTimeout(ctx, 15*time.Second).
  - Calls the List API; returns nil if List errors. Does NOT log. Does NOT mutate lastRefreshErr.
  - Computes derived fields in Go (not in the template).
  - sort.SliceStable at the end for deterministic order.

YOUR UPSTREAM PRODUCES: a typed Kubernetes clientset capable of listing Deployments via
  cs.AppsV1().Deployments("").List(ctx, metav1.ListOptions{})
</upstream_anchor>

<prerequisite_hop>
Hop 1 (must be complete before yours):
  - `type DeploymentStatus struct { Name, Namespace string; Replicas, Ready, Updated int32; Status, ReadyLabel string }` added to internal/status/collector.go.

VERIFY before writing code:
  $ grep -n "type DeploymentStatus struct" internal/status/collector.go
If the symbol is absent, STOP — your dependency chain is broken. Do not invent DeploymentStatus.
</prerequisite_hop>

<this_hop>
Add exactly one method to *Collector:

  func (c *Collector) collectDeployments(ctx context.Context) []DeploymentStatus

Behavior, step by step:
  1. cs, err := c.kubeClient(); if err != nil { return nil }
  2. listCtx, cancel := context.WithTimeout(ctx, 15*time.Second); defer cancel()
  3. list, err := cs.AppsV1().Deployments("").List(listCtx, metav1.ListOptions{}); if err != nil { return nil }
  4. For each item in list.Items, build a DeploymentStatus:
       desired := int32(1)
       if item.Spec.Replicas != nil { desired = *item.Spec.Replicas }
       ready := item.Status.ReadyReplicas
       updated := item.Status.UpdatedReplicas
       status := "healthy"; if ready != desired || updated != desired { status = "degraded" }
       readyLabel := fmt.Sprintf("%d/%d", ready, desired)
  5. sort.SliceStable by: degraded first, then Namespace ASC, then Name ASC.
  6. Return the slice.

OUT OF SCOPE — do NOT do any of the following (they are other hops):
  - Do NOT define the DeploymentStatus type (hop 1 — prerequisite).
  - Do NOT add the Deployments field to ClusterStatus (hop 3 — separate hop).
  - Do NOT wire collectDeployments into Collect (hop 4 — later hop).
  - Do NOT create or modify any template (hops 5, 8).
  - Do NOT add HTTP handlers or routes (hops 6, 7).
  - Do NOT touch any file except internal/status/collector.go.
</this_hop>

<downstream_contract>
Hop 4 (later) will add this line inside Collector.Collect:
  status.Deployments = c.collectDeployments(ctx)

Your method's name, signature, and return type are the contract that hop 4 depends on. They are fixed. Do not rename, do not change parameters, do not change the return type.
</downstream_contract>

<self_check>
Before declaring done:
  1. `grep -n "type DeploymentStatus struct" internal/status/collector.go` — must show a match (prerequisite hop 1 confirmed).
  2. `go build ./internal/status/...` — must succeed (your method compiles).
  3. `go vet ./internal/status/...` — must pass.
  4. Your method must NOT yet be called from anywhere — that is hop 4's job. If the compiler complains about an unused function, that is expected; do NOT wire it in to silence the warning.
</self_check>
```

---

## 5. Does this remove the end-state anchor?

### What is NOT in the teammate's attention

- No mention of `/workloads` (the HTTP path).
- No mention of "page," "UI," "browser," "render," "table," "row," "column," or "badge."
- No mention of `handleWorkloads`, `workloads.html`, or any template.
- No mention of the user, the operator, or anyone looking at the output.
- No mention of "Workloads" as a feature name (only "deployment list").

### What IS in the teammate's attention

- A method signature.
- A sibling method (`collectNodes`) as a pattern to mirror.
- A concrete input (clientset + ctx).
- A concrete output (`[]DeploymentStatus`, sorted).
- An explicit list of things that are out of scope.
- A downstream contract (what hop 4 will do with the output).
- Self-check tool calls (grep, go build, go vet).

### Reasoning about what Claude would do with this prompt

Given only this prompt, Claude cannot reason backward from `/workloads` because `/workloads` is not in the prompt. Claude cannot fabricate a plausible UI because no UI is described. The forward task is: take Deployment objects from an API, produce sorted DeploymentStatus. That is a pure transformation — one function, one file, one signature. There is effectively no room for the model to introduce a fabricated middle because there is no middle to fabricate. The hop IS a middle, and its inputs and outputs are both pinned.

Compare to V2's prompt shape for the same work: the teammate gets the 444-line spec. In that spec, the teammate reads "user can see all Deployments on a /workloads page" first (the attention anchor). Then they scroll down to the technical design. By the time they reach `collectDeployments`, their attention is already oriented toward "producing what the page needs," and they will make small decisions (what to include in DeploymentStatus, how to format ReadyLabel, whether to sort in the collector or the template) based on what a page would want, not based on what a collector pattern establishes.

### Where the prototype is still vulnerable

1. **The template hop (hop 5).** The template is inherently about presentation — what the user sees. The teammate for hop 5 WILL see "a `<table>` with Name, Namespace, Ready, Status." That is genuinely end-state. The mitigation is: hop 5's upstream is `pageData.Deployments` (hop 3), which is already pinned in shape. The teammate for hop 5 cannot change the data model; they can only render what they are given. End-state reasoning is scoped to presentation, where it belongs.

2. **The overview card (hop 9).** Combines multiple data sources. A teammate building this might reason end-state-first about "the overview page layout" and then backfill. Mitigation: the hop's upstream is explicitly `ClusterStatus.Deployments` (hop 3), so the data model is pinned. The hop is constrained to "read this field, render this card." Not a full design task.

3. **Hop 1 (the type definition).** The DeploymentStatus struct has fields that include `ReadyLabel` (a pre-formatted "X/Y" string) and `Status` (a string "healthy"/"degraded"). These fields exist because the *template* will want them pre-computed. That's an end-state-driven design decision. In V3 proper, we'd want to surface this: hop 1's prompt should say "the template downstream wants these fields pre-computed so rendering stays dumb — that is why this type has these fields." The *decision* is end-state-informed, but the *work* (define a struct) is forward. Acceptable seam.

4. **Hop 8 (the nav link).** Purely presentational. Teammate needs to know "a nav link for /workloads between Pods and Certs." That IS end-state. Mitigation: the hop is tiny, and its upstream is "the existing nav pattern in layout.html." Pattern-mirroring is a forward task.

### Verdict

The prototype reversal works for the non-presentational hops (1, 2, 3, 4, 6, 7). It reduces but does not eliminate end-state anchoring in the presentational hops (5, 8, 9). Since presentational hops MUST reason about presentation, this is probably correct — we want end-state reasoning in the template and nav, not in the collector.

**The key property V3 preserves:** the *data-shape decisions* happen in the collector hops, where end-state anchoring would cause the damage (fabricated intermediate data types, invented API calls). The presentational hops are scoped to "render this already-pinned data shape," which is a contained forward task even though it's visually end-state-y.

---

## 6. What this proves

- The flow graph schema survives contact with a real, non-trivial Go codebase.
- The delta format (ordered hops, consumes/produces) can express a real feature request.
- A V3 teammate prompt for a collector-layer hop genuinely has no end-state anchor.
- The presentational hops need no special treatment — their upstream is pinned, so they can't damage the data flow.

## 7. What this does NOT prove

- Whether Claude actually BEHAVES differently with this prompt vs. the V2 spec. That requires running a teammate against this prompt and comparing the output to V2's actual output for the same hop. Next empirical step.
- Whether the flow-mapper agent (which would build the existing flow graph automatically) is tractable. This prototype's graph was hand-built from reading 5 files. A real flow-mapper would need to build much bigger graphs.
- Whether the translation step (user's end-state description → hop list) produces correct deltas reliably. That needs separate prototyping — run a Forge-R2-analog conversation against the flow graph and see if the delta it produces is sane.
