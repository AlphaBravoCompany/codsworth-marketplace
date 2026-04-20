# Foundry V3 — Flow Reversal Design

**Status:** Exploration / design doc. Not yet committed as a decision.
**Date:** 2026-04-20
**Author:** design conversation between Garrett and Claude

This document preserves the research and design work behind a proposed architectural reversal in the Forge → Foundry pipeline. It consolidates two conversation turns into one reference. See "The Plan" at the bottom for next steps.

---

## The Problem

In the current Forge → Foundry pipeline, agents exhibit **endpoint-anchored plumbing hallucination**:

- The spec describes a final feature (e.g., "a /workloads page showing cluster pods with status badges")
- Agents lock onto the terminal state (the UI, the output, the endpoint)
- They then fabricate plausible-sounding intermediate plumbing **backward** from that endpoint — inventing service layers, stores, adapters, operators that don't correspond to how the real system works
- The hallucinated middle *looks* correct because it bridges backward from a real endpoint, but it's garbage

Desired behavior: agents trace **forward** from the natural origin (where data/control enters the system — a CRD spec, a user action, a config file, an event source) and only arrive at the terminal state after every upstream dependency has been verified to exist in actual code.

The illustrative example from the conversation (NOT a rule, just illustration): "First a line in the deployment spec, then the operator parses it, then data flows to storage, then picked up by the controller, then surfaced via API, then rendered." Trace from the actual source, not back from the endpoint.

---

## Diagnosis from Research

### How this is described in the literature

Not named as a single phenomenon, but decomposes into four mechanisms:

1. **The Reversal Curse** (Berglund et al., ICLR 2024, [arXiv 2309.12288](https://arxiv.org/abs/2309.12288)) — LLMs are fundamentally worse at reasoning backward than forward. Forward associations dominate; reverse ones collapse.
2. **Attention dilution** (Selective Prompt Anchoring, Tian et al., 2024) — as generation proceeds, the nearest-visible anchor (the endpoint description) crowds out the original system root.
3. **Training-data priors** — coding models have seen millions of modal service→store→adapter→view stacks. Given only an endpoint, they confidently sample the *typical* upstream stack.
4. **Non-causal CoT** (Lanham et al., [arXiv 2402.16048](https://arxiv.org/html/2402.16048v1)) — chain-of-thought output is post-hoc rationalization, not faithful trace. So "explain your plan" does not reveal whether the middle was fabricated.

Closest named description: Haryanto's **"Spec Interpretation Failure"** — *"the agent reads code for structure (what does this function do?) but not for governance (what constraints bind this function?)"*.

### Counterintuitive findings from the literature

- **Self-consistency is actively harmful here.** Confabulation consensus ([arXiv 2602.09341](https://arxiv.org/html/2602.09341)) shows correlated errors across samples; voting *reinforces* the fabrication.
- **Stronger models are more anchoring-biased, not less** (Nguyen et al., 2024). You cannot model-upgrade out of this.
- **Backward chaining in LLMs is effective when anchored to a knowledge base** (LAMBADA, Kazemi et al., [arXiv 2212.13894](https://arxiv.org/abs/2212.13894)). The failure isn't "backward reasoning is bad" — it's "backward reasoning without grounding is fabrication." The fix is grounding, not direction.
- **Governance prose in prompts is consulted, not enforced** (Haryanto). System-prompt-level instructions ("follow the spec") are structurally weaker than tool-level enforcement ("the build hook rejects this"). Maximum impact: encode requirements as *tool-level preconditions*, not prose.

### Top three evidence-backed mitigations

1. **ReAct-style tool-grounded observation loops** (Yao et al., ICLR 2023) — force Thought/Action/Observation triples where each intermediate claim must be confirmed by a real tool call before being used downstream.
2. **De-Hallucinator iterative grounding** (Eghbali & Pradel, 2024, [arXiv 2401.01701](https://arxiv.org/abs/2401.01701)) — retrieve project-specific symbols/APIs and re-prompt with them explicitly injected. 42–68% reduction in API hallucination.
3. **Chain-of-Verification** (Dhuliawala et al., ACL Findings 2024, [arXiv 2309.11495](https://arxiv.org/abs/2309.11495)) — generate independent verification questions ("does file X exist? does symbol Y exist?"). ~23% hallucination reduction.

---

## Root Cause in the Codebase

End-state-first reasoning is baked into the spec format itself and amplified at three stages:

| Stage | File:line | Problem |
|---|---|---|
| Forge interview | `plugins/forge/commands/plan.md:200-217` | Spec template captures "user can see X" — observable outcomes, never origin/flow |
| Foundry decompose | `plugins/foundry/skills/decompose/SKILL.md:184-188` | `must_haves: { truths, artifacts, key_links }` — all end-state framing; no origin field |
| Teammate casting | `plugins/foundry/agents/teammate.md:20-95, 117-194` | Four deviation rules and five self-check steps — none verify upstream data sources exist |
| INSPECT verification | `plugins/foundry/agents/tracer.md:31-100` | Four-level check (EXISTS, SUBSTANTIVE, WIRED, PLACED) all verify **upstream callers**, never **downstream data sources**. An endpoint returning `[]` passes all four. |

The hole: TRACE answers "is this symbol called?" It never asks "does this symbol's input come from somewhere real?" That's the exact gap where backward-fabricated plumbing hides.

---

## Why Prompt-Level Patches Won't Reverse the Behavior

Reasoning from how Claude actually works:

1. **Forward predictor.** I generate left-to-right, sampling highest-probability continuation. My "plan" is not derived — it's sampled.
2. **Attention is dominated by whatever is most recent and most concrete in context.** If the spec says "/workloads page shows pods," that phrase is the attention anchor. Everything I generate is a continuation *toward* that anchor.
3. **The Reversal Curse is structural.** Asking me to reason backward from a terminal state is asking me to do the weakest thing I do. When I do it anyway, I substitute training-data modal plumbing for actual system reasoning. That is the garbage.
4. **Chain-of-thought is post-hoc.** Asking me to "explain my plan" produces a fluent explanation that matches the plan — it does not reveal whether the middle was derived or fabricated.
5. **Tool output is the one thing I can't fabricate.** LSP responses are ground truth I have to accept. Prose instructions are not.

**Implication:** no amount of prompt-level instruction to "reason origin-first" or "verify sources" will flip the behavior, because the *artifact being reasoned against* (the spec) is end-state-first. As long as the attention anchor describes a terminal state, the model will reason toward that terminal state.

**The fix must change the artifact, not the instructions around it.**

---

## The Reversal Principle

**Don't give the model an end-state to reason backward from. Give it a grounded prefix to reason forward from.**

Currently:
```
Spec (end-state) → Decompose by feature → Teammate builds forward-from-nothing toward end-state
                                          (backward-fabricates the middle)
```

Reversed:
```
System flow graph (grounded) → Requirement located as a delta on the graph → Teammate builds forward-from-grounded-prefix, one hop at a time
                                                                              (cannot fabricate — the prefix is LSP-verified)
```

The end state is no longer the attention anchor. **The actual system's flow graph is the anchor.** The spec is just a request to extend the graph at a specific position.

This leverages forward-prediction strength instead of fighting backward-reasoning weakness.

---

## The V3 Architecture (Five Phases)

### Phase 1 — FLOW MAP (replaces Forge R0 codebase survey)

Not a codebase map. A **flow graph** of the target system. Nodes = real files/symbols/config. Edges = real data/control handoffs. Every node LSP- or grep-verified before being added.

Output format is **structural** (JSON/YAML), not prose — prose invites interpretation, structure doesn't.

This is the grounded prefix. It exists before the user says anything about what they want to build.

### Phase 2 — FLOW INTERVIEW (replaces Forge R2 user interview)

The user still describes what they want in end-state terms — that is how humans think, and we should not force them to think in flows. But the **interview artifact is not their description**. It is a translation.

The interviewer (Claude, given the flow map as primary context) converts the user's end-state into a **flow delta**:

> "Your request translates to: extending the graph from existing-node X to new-node Y to new-node Z to a new terminal node at the UI. Confirm?"

The user confirms or corrects. The spec output is the flow delta, not a feature description. There is no "/workloads page shows pods" requirement floating in the spec. There is "extend flow at `pkg/informers/pod.go:PodInformer` → new handler at `app/api/workloads/route.ts` → new component at `app/workloads/page.tsx`."

### Phase 3 — DELTA DECOMPOSITION (replaces F0.5 DECOMPOSE)

Packets are derived *from the flow delta*, not from the spec. Each packet:

```yaml
packet:
  flow_position: N
  consumes: <symbol_in_existing_graph_or_earlier_packet>
  produces: <new_symbol_this_packet_creates>
  terminal_state_slice: <which_part_of_user_end_state_this_hop_contributes_to>
```

There is no "build the workloads page" packet. There is "packet 3: implement /api/workloads handler, consuming PodInformer (existing), producing WorkloadsResponse (new), used by packet 4."

The packet format structurally prevents free-floating end-states. If a packet doesn't declare a `consumes`, decomposition rejects it.

### Phase 4 — UPSTREAM-FIRST CASTING

Teammates execute in flow order. Not a policy — enforced by the fact that a downstream teammate's `consumes` field points to a symbol that doesn't exist yet. When they grep/LSP for it, they get "not found." They have no end-state to reason toward because their work packet starts at an existing symbol and ends at a new one.

Each teammate's prompt is a forward-completion task: "Here is symbol A (grounded, real, cited). Produce symbol B that consumes A and is consumed by downstream packet's B." No terminal UI in their attention anchor.

Prompt structure replaces `<spec_requirements>` with:
- `<upstream_anchor>` — grounded, real, cited
- `<this_hop>` — what you produce
- `<downstream_contract>` — what your output will be consumed by

### Phase 5 — FORWARD TRACE VERIFICATION

INSPECT runs the flow from the declared origin forward through each hop. Any break = defect. This replaces TRACE as the primary verification. TRACE (upstream from endpoint) becomes supplementary.

---

## Greenfield vs Brownfield Branching

Greenfield has no existing system to flow-map. End-state-first is actually appropriate for greenfield (the terminal shape is the design; you build forward from scratch in a reasonable order). Brownfield requires reversal.

Mechanism: a flag or auto-detection at `/forge:plan` entry.

- **`--greenfield`** (or empty-ish target dir auto-detected) → skip flow mapping. Use current V2-ish pipeline. Spec is end-state-first.
- **`--brownfield`** (or populated target dir auto-detected) → run flow mapping first. Spec is a flow delta. Teammates get upstream-first casting.
- **Mixed case** (new subsystem inside existing repo) → flag applies per-feature. If the feature touches existing code, brownfield. If purely new additive code with no existing upstream, greenfield slice within brownfield repo.

Auto-detection heuristic: if Forge's R0 codebase survey finds >N files in relevant paths, default to brownfield and prompt user to confirm. Flag overrides.

---

## Does the Interview Still Ask Detailed Questions?

**Yes — more detailed, and the detail is grounded instead of invented.**

In V2, the interview asks the user to enumerate requirements. Questions get deep fast ("what happens when the API returns 500?") but all questions live in the user's end-state frame.

In V3 brownfield mode, the interview has the flow graph in context. Questions become:

- "Your feature hooks into `pkg/informers/pod.go:PodInformer` — is that the right upstream, or should we be reading from the raw API instead?"
- "You want a /workloads page — does the data come via the existing `/api/v1` router or a new route?"
- "The existing controller at `pkg/controllers/pod.go` already emits status updates — do you want to consume those events, or poll?"

The interviewer offers candidate answers from the flow graph instead of asking the user to invent them. This is the opposite of less detailed — it is more detailed and grounded. The user doesn't need to know implementation; the interviewer translates user end-state into flow-positional questions.

In V3 greenfield mode, the interview looks like V2 (no graph to anchor to), but with a clear awareness that the output spec will drive end-state-first building (which is fine for greenfield).

---

## Honest Caveats

1. **Flow graphs are expensive to build.** For greenfield projects there's nothing to map — the greenfield branch handles this.
2. **The translation step (Phase 2) is itself an LLM step.** If translation is sloppy, end-state-first framing moves inside the interviewer. Mitigation: the interview produces a structured delta, the user validates it node-by-node against the graph, and the graph is immutable ground truth during the session.
3. **Not every brownfield requirement is flow-shaped.** Styling changes, copy edits, refactors don't have origins in the data-flow sense. V3 needs to distinguish flow-requirements (reversed pipeline) from non-flow-requirements (end-state pipeline is fine). Possibly a second auto-detection or a third flag (`--cosmetic` or similar).
4. **This is a V3, not a V2.5.** Partial adoption produces a worse system than either full version — two artifact shapes fighting each other.

---

## The Plan

### Phase 0 — Prototype (before any code changes)

Validate the architecture cheaply before committing to a rewrite.

- Pick one realistic abk8s feature (the `/workloads` page is a reasonable candidate since it was the V2 first-test target)
- Hand-build the flow graph for the relevant subsystem
- Hand-write a flow delta for the realistic user request
- Hand-author the packet schema for that delta
- Write what a teammate prompt would actually look like in V3
- Inspect: does the resulting teammate prompt structurally remove the end-state anchor? Does a Claude given only the `<upstream_anchor>` + `<this_hop>` + `<downstream_contract>` write clean forward code, or does end-state framing leak in anyway?

**Decision point after Phase 0:** if the prototype shows teammates building forward cleanly against grounded prefixes, commit to the V3 rewrite. If end-state framing still leaks somewhere, iterate on the packet format or abandon and pick a different lever.

### Phase 1 — V3 architecture spec

Only after prototype validates the approach.

- Write FOUNDRY-V3-DESIGN.md (supersedes V2)
- Define flow-graph schema formally
- Define flow-delta schema formally
- Define packet schema with consumes/produces fields
- Define greenfield/brownfield branching (flag + auto-detect heuristic)
- Define the flow-shaped / non-flow-shaped distinction for brownfield

### Phase 2 — Build flow-mapper (brownfield path only)

- New agent variant: `plugins/foundry/agents/flow-mapper.md`
- Produces `flow-graph.json`
- LSP/grep-grounded, every node verified before inclusion

### Phase 3 — Rebuild Forge R2 interview

- `plugins/forge/commands/plan.md` gains brownfield-mode branching
- Brownfield interview uses flow graph as primary context
- Translates user's end-state requests into flow deltas
- User validates deltas node-by-node before handoff to Foundry
- Greenfield interview stays as-is

### Phase 4 — Rebuild Foundry decompose

- `plugins/foundry/skills/decompose/SKILL.md` brownfield branch
- Replace `must_haves` schema with `flow_delta` schema
- Packets derived from delta with consumes/produces fields

### Phase 5 — Rebuild teammate prompts

- `plugins/foundry/agents/teammate.md` brownfield branch
- Replace `<spec_requirements>` with `<upstream_anchor>` + `<this_hop>` + `<downstream_contract>`

### Phase 6 — Add forward-trace INSPECT stream

- `plugins/foundry/agents/flow-tracer.md` — mirror of TRACE
- Runs flow from origin forward as primary verification
- TRACE (upstream) retained as supplementary

### Phase 7 — Version bump + migration guide

- v3.0.0 release
- Migration guide for users of V2
- Update `plugins/foundry/FOUNDRY-V2-DESIGN.md` → `FOUNDRY-V3-DESIGN.md`

---

## Research Sources

- [The Reversal Curse](https://arxiv.org/abs/2309.12288) — Berglund et al., ICLR 2024
- [De-Hallucinator](https://arxiv.org/abs/2401.01701) — Eghbali & Pradel, 2024
- [When the Agent Quoted My Spec, Then Destroyed My Architecture](https://medium.com/@cyharyanto/when-the-agent-quoted-my-spec-then-destroyed-my-architecture-30f770985a45) — Haryanto, 2026
- [Chain-of-Verification](https://arxiv.org/abs/2309.11495) — Dhuliawala et al., ACL Findings 2024
- [Least-to-Most Prompting](https://arxiv.org/abs/2205.10625) — Zhou et al., ICLR 2023
- [ReAct](https://react-lm.github.io/) — Yao et al., ICLR 2023
- [Selective Prompt Anchoring](https://arxiv.org/html/2408.09121) — Tian et al., 2024
- [LLMs with Chain-of-Thought Are Non-Causal Reasoners](https://arxiv.org/html/2402.16048v1) — Lanham et al.
- [Auditing Multi-Agent LLM Reasoning Trees](https://arxiv.org/html/2602.09341)
- [LAMBADA: Backward Chaining](https://arxiv.org/abs/2212.13894) — Kazemi et al., ACL 2023
- [Cognition: Don't Build Multi-Agents](https://cognition.ai/blog/dont-build-multi-agents)
- [Aider: Repository Map](https://aider.chat/docs/repomap.html)
- [Addy Osmani: How to Write a Good Spec for AI Agents](https://addyosmani.com/blog/good-spec/)
