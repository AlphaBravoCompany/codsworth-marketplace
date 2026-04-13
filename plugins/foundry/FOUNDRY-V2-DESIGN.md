# Foundry v2: GSD Prevention + Foundry Detection, Fully Autonomous

## Vision

**Set it and forget it.** User provides a spec (via Forge or directly), runs `/foundry:start`, and walks away. Foundry v2 prevents problems before they happen AND detects the ones that slip through — so the INSPECT→GRIND loop runs 0-1 times instead of 3-5.

## Design Principles

1. **Prevention over detection** — invest upstream to save downstream cycles
2. **Zero human interaction after start** — no checkpoints, no approvals, no decisions
3. **Every agent gets a rich prompt** — 7-line teammate prompts are dead
4. **Context budget awareness** — agents know their limits and stay within them
5. **Smart model allocation** — Opus thinks, Sonnet builds, no waste
6. **Self-verification at every level** — agents check their own work before reporting done

## Architecture: The New Phase Flow

```
/forge:plan → Spec with locked/discretion/deferred classification
                                    │
                                    ▼
/foundry:start ─────────────────────┐
                                    │
    F0: RESEARCH ◄──── NEW ─────────┤  Auto-spawn researcher agents
         │                          │  Investigate HOW to build (not just what exists)
         │                          │  Output: research artifacts per casting domain
         ▼                          │
    F0.5: DECOMPOSE (enhanced) ─────┤  Decompose spec into castings
         │                          │  Each casting gets must_haves (truths, artifacts, key_links)
         │                          │  
         ▼                          │
    F0.9: VALIDATE ◄── NEW ─────────┤  Plan validation gate (8 dimensions)
         │  ↺ revision loop (max 3) │  Auto-revise castings if issues found
         │                          │  No human involvement — lead fixes autonomously
         ▼                          │
    F1: CAST (enhanced) ────────────┤  Rich teammate prompt (deviation rules, scope boundary,
         │                          │  analysis paralysis guard, self-check, atomic commits)
         │                          │  Model: Sonnet for teammates, Opus stays lead
         ▼                          │
    F2: INSPECT (enhanced) ─────────┤  TRACE + PROVE + SIGHT + TEST (keep all 4)
         │                          │  ADD: stub detection patterns, three-level verification
         │                          │  ADD: "don't trust build output" mindset
         ▼                          │
    F3: GRIND (enhanced) ───────────┤  Rich teammate prompt (same as CAST)
         │  ↺ back to F2            │  ADD: structured debugging protocol per defect
         │                          │  ADD: deviation rules, self-check
         ▼                          │
    F4: ASSAY (keep) ───────────────┤  Fresh-eyes spec-before-code (already great)
         │  ↺ back to F3 if fail    │
         ▼                          │
    F5: TEMPER (keep) ──────────────┤  Optional micro-domain stress test
         ▼                          │
    F5.5: NYQUIST ◄── NEW ─────────┤  Generate tests for uncovered requirements
         ▼                          │  Run and verify — never mark untested as passing
    F6: DONE ───────────────────────┘  Report + archive
```

## Detailed Changes

---

### Change 1: New F0 RESEARCH Phase

**What:** Before decomposing the spec, auto-spawn researcher agents to investigate the technical domain.

**Why:** Castings built without research make wrong technology choices that surface as defects in INSPECT. Researching first means casting teammates build with current best practices.

**Implementation:**

1. After `Foundry-Init`, before DECOMPOSE, lead reads the spec
2. Lead identifies 2-4 technical domains that need research (e.g., "WebSocket auth", "real-time sync", "file upload handling")
3. Spawns parallel Explore agents (model: sonnet) — one per domain
4. Each researcher:
   - Checks Context7 for current library docs
   - Investigates standard patterns and anti-patterns
   - Reports confidence levels (HIGH/MEDIUM/LOW)
   - Outputs research summary (written to `foundry-archive/{run}/research/`)
5. Lead synthesizes research into casting context

**New files:**
- `foundry/agents/researcher.md` — research agent prompt (~300 lines)

**Modified files:**
- `foundry/commands/start.md` — add F0 RESEARCH section
- `foundry_orchestrator.py` — add `research` gate check (research dir exists with ≥1 file)

**MCP tool changes:**
- `Foundry-Next` returns `action: "research"` after init when no research exists

---

### Change 2: Enhanced DECOMPOSE with must_haves

**What:** Each casting in manifest.json gets structured `must_haves` — not just Observable Truths.

**Why:** Observable Truths are good but they lack the structured contract that verification can check mechanically. `must_haves` gives INSPECT concrete criteria.

**Implementation:**

Enhanced casting structure in `manifest.json`:
```json
{
  "id": 1,
  "title": "Auth System",
  "spec_text": "...",
  "observable_truths": ["User can log in", "Invalid creds return 401"],
  "must_haves": {
    "truths": ["User can log in with email/password", "Invalid credentials return 401"],
    "artifacts": [
      {"path": "src/api/auth/login.ts", "provides": "Login endpoint", "min_lines": 30},
      {"path": "src/components/LoginForm.tsx", "provides": "Login UI", "min_lines": 50}
    ],
    "key_links": [
      {"from": "LoginForm.tsx", "to": "/api/auth/login", "via": "fetch in onSubmit"},
      {"from": "login.ts", "to": "User model", "via": "prisma query"}
    ]
  },
  "key_files": ["src/api/auth/login.ts", "src/components/LoginForm.tsx"],
  "research_context": "See research/auth.md for JWT best practices"
}
```

**Modified files:**
- `foundry/skills/decompose/SKILL.md` — add must_haves generation to casting template
- `foundry/commands/start.md` — F0 DECOMPOSE section references must_haves

---

### Change 3: New F0.9 VALIDATE Gate (Casting Validation)

**What:** After DECOMPOSE, before CAST, automatically validate that castings will deliver the spec. Revision loop if issues found.

**Why:** This is the single biggest quality gap. Currently nobody asks "will these castings actually deliver the spec?" before building starts. A 5-minute validation saves hours of GRIND cycles.

**Implementation:**

New MCP tool: `Foundry-Validate-Castings`
- Reads manifest.json + spec.md
- Checks 6 dimensions (adapted from GSD plan-checker):
  1. **Requirement Coverage** — every spec requirement (US-N, FR-N) appears in at least one casting's spec_text
  2. **Casting Completeness** — every casting has must_haves with truths + artifacts + key_links
  3. **Dependency Correctness** — no file overlap (already exists), casting order makes sense
  4. **Key Links Planned** — artifacts are wired together across castings (not isolated)
  5. **Scope Sanity** — no casting has >8 key_files (already exists), observable truths are user-facing
  6. **Research Integration** — castings reference research findings where applicable

Returns: `{ passed: bool, issues: [...], revision_hints: [...] }`

**Revision loop (autonomous):**
1. Lead calls `Foundry-Validate-Castings`
2. If issues found → lead auto-revises castings based on `revision_hints`
3. Re-validates (max 3 iterations)
4. After 3 iterations → proceed anyway (log warnings), don't block

**New files:**
- `foundry_mcp/tools/foundry_validate.py` — validation logic (~200 lines)

**Modified files:**
- `foundry_mcp/server.py` — register new tool
- `foundry_orchestrator.py` — add `validate` gate, revision tracking in state.json
- `foundry/commands/start.md` — add F0.9 VALIDATE section with revision loop

---

### Change 4: Rich Teammate Prompt (The Big One)

**What:** Replace the 7-line teammate prompt with a comprehensive 300+ line prompt that includes deviation rules, scope boundary, analysis paralysis guard, self-check, and atomic commit protocol.

**Why:** This is the #1 quality difference between GSD and Foundry at the execution level.

**Implementation:**

New teammate prompt template (used for both CAST and GRIND):

```markdown
You are a Foundry teammate. Your job is to implement assigned tasks completely and correctly.

## DEVIATION RULES

While building, you WILL discover work not in the task. Apply these rules:

**RULE 1: Auto-fix bugs** — Code doesn't work (logic errors, null crashes, broken queries)
→ Fix inline, test, continue. No permission needed.

**RULE 2: Auto-add missing critical functionality** — Missing essentials (error handling,
input validation, auth checks, CSRF protection, rate limiting)
→ Add inline, test, continue. These aren't "features" — they're correctness requirements.

**RULE 3: Auto-fix blocking issues** — Something prevents completing the task
(missing dep, wrong imports, broken config, missing env var)
→ Fix inline, test, continue. No permission needed.

**RULE 4: Log architectural concerns** — Fix requires structural modification
(new DB table, major schema change, switching libraries)
→ DO NOT STOP. Log the concern to foundry-archive/{run}/concerns.md and continue
with the best available approach. Lead reviews concerns after CAST.

SCOPE: Only fix issues from YOUR task's changes. Pre-existing issues → log, don't fix.
LIMIT: Max 3 auto-fix attempts per task. After 3, log remaining issues and move on.

## ANALYSIS PARALYSIS GUARD

If you make 5+ consecutive Read/Grep/Glob calls without any Edit/Write/Bash:
STOP. State in one sentence why you haven't written anything. Then either:
1. Write code (you have enough context), or
2. Log "blocked: [reason]" and move to next task.

## SELF-CHECK

After completing each task:
1. Verify created files exist: [ -f path ] && echo FOUND || echo MISSING
2. Run build: [project build command]
3. Run tests: [project test command]
4. If self-check fails, fix (counts toward 3-attempt limit)

## COMMIT PROTOCOL

After each task passes self-check:
1. Stage task-related files individually (NEVER git add . or git add -A)
2. Commit: git commit -m "feat(foundry): [concise task description]"
3. Record hash for reporting

## TASK EXECUTION

1. Read the task description fully
2. Read the casting's must_haves — understand what success looks like
3. Read research context if referenced
4. Implement the task
5. Apply deviation rules as needed
6. Self-check
7. Commit
8. Mark task complete via TaskUpdate
9. Claim next task or go idle
```

**New files:**
- `foundry/prompts/teammate.md` — rich teammate prompt (~300 lines)

**Modified files:**
- `foundry/commands/start.md` — reference teammate.md instead of inline 7-line prompt

---

### Change 5: Model Profile Allocation

**What:** Use Sonnet for CAST/GRIND teammates (they follow instructions), Opus only for lead + ASSAY + planning.

**Why:** Teammates follow explicit casting instructions. They don't need Opus-level reasoning — they need Sonnet's instruction-following. This saves cost AND often produces better results (Sonnet sticks to the plan instead of going creative).

**Implementation:**

Model allocation table:
| Role | Model | Why |
|------|-------|-----|
| Lead orchestrator | opus | Architecture decisions, phase management |
| F0 Researchers | sonnet | Domain investigation, pattern extraction |
| F0.5 Decompose agents | opus | Spec decomposition requires reasoning |
| F0.9 Validation | (lead does it) | Part of lead's orchestration |
| F1 CAST teammates | **sonnet** | Follow casting instructions |
| F2 TRACE agent | sonnet | Systematic wiring checks |
| F2 PROVE agent | opus | Spec-before-code requires deep reasoning |
| F3 GRIND teammates | **sonnet** | Fix defects with rich prompt guidance |
| F4 ASSAY agents | opus | Fresh-eyes verification needs reasoning |
| F5 TEMPER | sonnet | Systematic micro-domain probing |

**Modified files:**
- `foundry/commands/start.md` — specify model per agent spawn

---

### Change 6: Enhanced INSPECT with Stub Detection

**What:** Add GSD's stub detection patterns and three-level verification to PROVE and TRACE agents.

**Why:** Current PROVE checks spec compliance. Current TRACE checks wiring. Neither explicitly looks for stubs — code that "exists" but is a placeholder.

**Implementation:**

Add to `foundry/agents/assayer.md` (PROVE/ASSAY):
```markdown
## STUB DETECTION (Check Level 2: Substantive)

After confirming code exists, check it's REAL implementation:

React stubs (RED FLAGS):
- return <div>Component</div> / return <div>Placeholder</div>
- onClick={() => {}} / onChange={() => console.log('clicked')}
- onSubmit={(e) => e.preventDefault()}  // Only prevents default

API stubs:
- return Response.json({ message: "Not implemented" })
- return Response.json([])  // Empty array with no DB query

Wiring stubs:
- fetch('/api/path') with no await/then/assignment
- await db.query() but return static response (not query result)
- useState but value never rendered in JSX

Verdict: If stub found, verdict is HOLLOW (not VERIFIED), even if spec requirement technically "exists."
```

Add to `foundry/agents/tracer.md` (TRACE):
```markdown
## THREE-LEVEL VERIFICATION

For each symbol/function traced:

| Level | Check | Fail = |
|-------|-------|--------|
| 1. EXISTS | Symbol/file present | MISSING |
| 2. SUBSTANTIVE | Real implementation, not stub | THIN (use stub detection patterns) |
| 3. WIRED | Called/imported by other code | UNWIRED |

All three must pass for verdict WIRED. Don't skip level 2.
```

**Modified files:**
- `foundry/agents/assayer.md` — add stub detection section
- `foundry/agents/tracer.md` — add three-level verification section

---

### Change 7: Enhanced GRIND with Debugging Protocol

**What:** Give GRIND teammates a structured debugging protocol instead of just a defect description.

**Why:** GSD's debugger uses scientific method with hypothesis testing. Foundry's GRIND teammates just get "fix this defect" and wing it.

**Implementation:**

Add to the rich teammate prompt (for GRIND mode):
```markdown
## DEBUGGING PROTOCOL (GRIND tasks only)

For each defect:
1. READ the defect description and source (trace/prove/sight/test)
2. REPRODUCE — find the exact code location. Read the full function.
3. HYPOTHESIZE — "I think the issue is X because Y"
4. VERIFY — check your hypothesis with a targeted read/grep
5. FIX — make the minimal change that fixes the defect
6. VALIDATE — run the same check that found the defect
7. SELF-CHECK — build + test pass

If fix doesn't work after 2 attempts:
- Log to concerns.md: "Defect D-{N}: attempted fix failed, may need architectural change"
- Move to next defect
```

**Modified files:**
- `foundry/prompts/teammate.md` — add GRIND debugging section

---

### Change 8: Forge Enhancement — Intent Classification

**What:** Make Forge output a richer spec that classifies requirements as locked/discretion/informational.

**Why:** When Foundry builds from a spec, it doesn't know which requirements are hard constraints vs. suggestions. This causes wrong guesses. If Forge marks them, Foundry respects them.

**Implementation:**

Add to Forge's spec output format:
```markdown
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

Foundry's CAST teammates then know: locked = implement exactly, flexible = best judgment, informational = context only.

**Modified files:**
- `forge/commands/plan.md` — add classification step to interview finalization

---

### Change 9: Context Budget in Foundry-Next

**What:** `Foundry-Next` tracks context usage and warns when approaching limits.

**Why:** Multi-cycle runs accumulate context. The lead starts making worse decisions at 70%+ context. Explicit tracking prevents degraded-context decisions.

**Implementation:**

Add to `Foundry-Next` response:
```json
{
  "context_budget": {
    "cycles_completed": 2,
    "estimated_usage": "high",
    "recommendation": "Consider /clear and /foundry:resume if quality is degrading"
  }
}
```

The lead prompt includes:
```markdown
## CONTEXT MANAGEMENT

After cycle 2+, if Foundry-Next shows estimated_usage "high":
1. Finish current phase action
2. Save state via Foundry-Context
3. Suggest /foundry:resume to user (fresh context)

Do NOT continue operating in degraded context — it causes more GRIND cycles than it saves.
```

**Modified files:**
- `foundry_orchestrator.py` — add context_budget to next_action response
- `foundry/commands/start.md` — add context management section

---

### Change 10: New F5.5 NYQUIST Phase (Test Gap Filling)

**What:** After ASSAY passes, before DONE, auto-generate tests for uncovered requirements.

**Why:** ASSAY verifies the code works. Nyquist ensures it STAYS working — regression protection.

**Implementation:**

1. Lead reads verdicts.json — finds all VERIFIED requirements
2. For each, checks if automated test exists (grep for test files matching the domain)
3. For requirements without tests, spawns a test-generation agent (sonnet)
4. Agent generates minimal behavioral tests, runs them, debugs (max 3 iterations)
5. Commits passing tests

This is optional (like TEMPER) — enabled via `--nyquist` flag or always-on in config.

**New files:**
- `foundry/agents/nyquist.md` — test generation agent prompt (~150 lines)

**Modified files:**
- `foundry/commands/start.md` — add F5.5 NYQUIST section
- `foundry_orchestrator.py` — add nyquist gate and phase transition

---

## What Stays the Same

- **Foundry-Next guidance engine** — still the master orchestrator
- **MCP tools** (defect tracking, verdicts, streams, teams) — all kept
- **4 verification streams** (TRACE, PROVE, SIGHT, TEST) — enhanced, not replaced
- **ASSAY** — fresh-eyes spec-before-code methodology is already great
- **TEMPER** — micro-domain stress testing stays
- **Team lifecycle** — tmux scanning, register/unregister
- **Defect regression tracking** — keep this, GSD doesn't have it
- **Forge as separate plugin** — it's the interactive interview, Foundry is the autonomous builder

## What Changes About User Interaction

| Current Foundry | Foundry v2 |
|---|---|
| Lead never asks for approval | Same — but now SMARTER because prevention reduces need for intervention |
| No research before build | Auto-research (no user interaction) |
| No plan validation | Auto-validate + auto-revise (no user interaction) |
| 7-line teammate prompt | Rich prompt with deviation rules (no user interaction, just better output) |
| Opus for everything | Smart model allocation (no user interaction, just cheaper + better) |
| No debugging protocol | Structured debugging (no user interaction, just fewer GRIND cycles) |

**Net effect:** User still runs `/foundry:start` and walks away. But the system works harder before building, so it gets things right the first time.

## Implementation Priority

| # | Change | Impact | Effort | Files Changed |
|---|--------|--------|--------|---------------|
| 1 | Rich teammate prompt | **HIGHEST** | Low | 2 new, 1 modified |
| 2 | Casting validation gate | **HIGH** | Medium | 1 new, 3 modified |
| 3 | Enhanced must_haves in castings | **HIGH** | Low | 2 modified |
| 4 | Stub detection in INSPECT | **HIGH** | Low | 2 modified |
| 5 | Model profile allocation | **MEDIUM** | Low | 1 modified |
| 6 | Research phase | **MEDIUM** | Medium | 1 new, 2 modified |
| 7 | GRIND debugging protocol | **MEDIUM** | Low | 1 modified (teammate.md) |
| 8 | Forge intent classification | **MEDIUM** | Low | 1 modified |
| 9 | Context budget tracking | **LOW** | Low | 2 modified |
| 10 | Nyquist test generation | **LOW** | Medium | 1 new, 2 modified |

**Recommended execution order:** 1 → 3 → 2 → 4 → 5 → 6 → 7 → 8 → 9 → 10

## Version

This is the design for Foundry v2.0.0 — the "GSD Prevention + Foundry Detection" release.
