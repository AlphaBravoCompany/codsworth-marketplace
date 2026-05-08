---
date: 2026-05-08
project: phase9-sloppy
status: SPEC FORGED
---

# Interview Transcript: phase9-sloppy

*Verbatim Q/A record. This synthetic transcript is the canonical adversarial corpus for Phase 9 ablation runs — replayed verbatim across all 10 cohorts (per CONTEXT.md replay-based decision). See 09-CONTEXT.md §Implementation Decisions §Candidate spec for the seven failure-mode triggers (a-h).*

*Started: 2026-05-08*

---

## Q-001: What does this feature do at a high level?

**A-001 [Locked] [ARCH_INVARIANT]**

The phase9-sloppy job processor consumes inbound message envelopes from a queue and produces durable acknowledgement records. All acknowledgement writes must live in `src/services/ack/` — the persistence layer is not allowed to leak into `src/handlers/` or any HTTP-facing module. This is a hard placement rule because the acknowledgement records are audit-traceable and any second writer would split the source of truth.

---

## Q-002: What is the canonical surface for processing one envelope?

**A-002 [Locked]**

The single entry point is the function `process_envelope(envelope, mode)` exported from `src/services/ack/processor.py`. Input is a structured envelope object with two named fields: a numeric `x` field carrying the payload size in bytes, and a `mode` field that takes one of two string values, `"fast"` or `"thorough"`. Output is a structured acknowledgement record. Errors raised: `EnvelopeRejected` for malformed input; `AckPersistenceFailed` when the durable write fails after retries.

---

## Q-003: What state does an envelope move through during processing?

**A-003 [Locked]**

When `process_envelope` is invoked, the envelope transitions from `RECEIVED` to `VALIDATED` after schema check passes. After the durable acknowledgement write commits, it transitions from `VALIDATED` to `ACKNOWLEDGED`. The acknowledgement-write step has a precondition guard: the envelope's payload size must be at most the configured ceiling. Transitions are recorded in the acknowledgement record itself; no separate state log.

---

## Q-004: What output shape does the `"fast"` versus `"thorough"` mode produce?

**A-004 [Locked]**

In `"fast"` mode, the output is a record with two fields: `ack_id` (a string) and `received_at` (an ISO-8601 timestamp). In `"thorough"` mode, the output extends the same shape with an additional `verification_chain` field carrying an array of integrity hash strings. The `mode` field on the input drives this branching at the contract level — calls with `mode="fast"` MUST NOT carry a `verification_chain` in the response, and calls with `mode="thorough"` MUST carry a non-empty `verification_chain` in the response.

---

## Q-005: How should the system handle envelopes whose payload exceeds the ceiling?

**A-005 [Locked]**

When the payload exceeds the bound, the processor must reject the envelope before the durable write step. The rejection should surface as a clean `EnvelopeRejected` error with a reason field naming the bound that was violated. This is the audit-traceable rejection path — silent drops are not acceptable.

---

## Q-006: What is the cap?

**A-006 [Locked]**

The cap is 5000.

*(Author note: Locked answer carries residual ambiguity that PROBE-01's R3.5 reviewer should surface — the unit of "5000" is unstated. The transcript leaves it ambiguous between bytes (which A-002 names as the unit of `x`) and message count or some other dimension. PROBE-01 should flag this with a citation to A-006 and a reference to A-002 for the bytes-unit context. This is the (g) reviewer-surface trigger.)*

---

## Q-AUTO-001 (auto-extracted from R0 SURVEY)

**A-AUTO-001 [IMPLICIT_FACT:DEPLOYMENT]**

Deploys via Kubernetes manifest applied through a CI pipeline; production cluster is `phase9-prod` in region `us-east-1`. [auto-extracted from survey/reality.md]

---

## Q-AUTO-002 (auto-extracted from R0 SURVEY)

**A-AUTO-002 [IMPLICIT_FACT:RUNTIME]**

Runtime is Python 3.11.7; processes spawn under a single uvicorn worker per pod. [auto-extracted from survey/reality.md]

---

## Q-AUTO-003 (auto-extracted from R0 SURVEY)

**A-AUTO-003 [IMPLICIT_FACT:FRAMEWORK_VERSION]**

The HTTP framework is FastAPI 0.111; the queue client is aio-pika 9.4. [auto-extracted from survey/reality.md]

---

## Q-AUTO-004 (auto-extracted from R0 SURVEY)

**A-AUTO-004 [IMPLICIT_FACT:SCALE]**

Steady-state ingest is approximately 12 envelopes/second per pod with peak bursts to 120/second; 4 pods at the deployment baseline. [auto-extracted from survey/reality.md]

---

## Q-007: Where do evidence files for this feature live during integration testing?

**A-007 [Locked]**

All evidence files committed during integration testing must be checked into the same branch as the casting commit. We do not allow cross-branch evidence references — the audit trail must resolve within a single branch's git log. This is a constraint that decompose would naturally drop without an intent-coverage cross-check, because it does not name a specific surface element (no FR-N, no US-N, no class name); it is a meta-process constraint about WHERE evidence lives. The INTENT-01 stream catches it; without INTENT-01, decompose silently elides it.

*(Author note: This is the (h) INTENT-01 droppable transcript constraint trigger. A-007 is NOT cited verbatim in any typed-table row, so removing INTENT-01 from the F0.7 phase causes this constraint to vanish from any casting prompt, which is the no_INTENT_01 cohort's expected detection.)*

---

## Q-008: Are there any rate-limiting or backpressure rules?

**A-008 [Locked]**

When sustained ingest exceeds 80 envelopes/second per pod for more than 30 seconds, the processor must shed load by returning early-rejection responses. Rejected envelopes during shedding must include a `retry_after_seconds` hint. This applies before the schema-validation step.
