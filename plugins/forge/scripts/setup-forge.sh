#!/bin/bash

# Forge Setup Script
# Creates state file and initializes the research + interview session
# Forge researches. Forge interviews. Foundry builds.

set -euo pipefail

# Parse arguments
FEATURE_NAME=""
CONTEXT_FILE=""
OUTPUT_DIR="docs/specs"
MAX_QUESTIONS=0  # Unlimited by default
NO_SURVEY=false
FIRST_PRINCIPLES=false
FOCUS_DIRS=""
USER_PROMPT=""

while [[ $# -gt 0 ]]; do
  case $1 in
    -h|--help)
      cat << 'HELP_EOF'
Forge - Codebase-Aware Specification Engine

Forge researches. Forge interviews. Foundry builds.

USAGE:
  /forge:plan <FEATURE_NAME> [OPTIONS]

ARGUMENTS:
  FEATURE_NAME    Name of the feature to spec out (required)

OPTIONS:
  --prompt <text>       Tell forge what you want (e.g., "refine this spec deeper", "add error handling")
  --context <file>      Initial context file (PRD, requirements, spec to refine, etc.)
  --output-dir <dir>    Output directory for specs (default: docs/specs)
  --max-questions <n>   Maximum question rounds (default: unlimited)
  --no-survey           Skip codebase survey (for greenfield/empty projects)
  --first-principles    Challenge assumptions before detailed spec gathering
  --focus <dirs>        Comma-separated directories to focus survey on (e.g., src/auth,src/api)
  -h, --help            Show this help

DESCRIPTION:
  Forge combines GSD-style parallel codebase research with Lisa-style adaptive
  interviews. It deeply studies your codebase FIRST, then asks smart questions
  grounded in what it found.

  Phase R0: SURVEY    - Parallel agents explore architecture, data, surface, infra
  Phase R1: SYNTHESIZE - Merge findings into codebase reality document
  Phase R2: INTERVIEW  - Multi-round adaptive interview (grounded in R0/R1)
  Phase R3: SPEC       - Generate foundry-ready spec (US/FR/NFR/AC/OT IDs)
  Phase R4: VALIDATE   - Self-check all file refs, patterns, coverage

  The interview continues until you say "done" or "finalize".

EXAMPLES:
  /forge:plan "user authentication"
  /forge:plan "payment processing" --context docs/PRD.md
  /forge:plan "search feature" --focus src/search,src/api
  /forge:plan airgap-e2e --context docs/specs/airgap.md --prompt "refine this spec deeper"
  /forge:plan auth-system --context docs/PRD.md --prompt "focus on error handling and edge cases"
  /forge:plan "new dashboard" --first-principles
  /forge:plan "greenfield api" --no-survey

OUTPUT:
  Final spec:     {output-dir}/{feature-slug}.md
  Structured JSON: {output-dir}/{feature-slug}.json
  Survey data:    docs/recon/{feature-slug}/
  Progress:       {output-dir}/{feature-slug}-progress.txt
  Draft:          .claude/forge-draft.md

WORKFLOW:
  1. Forge researches + interviews: /forge:plan "my feature"
  2. Foundry builds + verifies:     /foundry --spec docs/specs/my-feature.md

  Forge plans. Foundry builds. Ship with confidence.
HELP_EOF
      exit 0
      ;;
    --context)
      CONTEXT_FILE="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --max-questions)
      MAX_QUESTIONS="$2"
      shift 2
      ;;
    --no-survey)
      NO_SURVEY=true
      shift
      ;;
    --first-principles)
      FIRST_PRINCIPLES=true
      shift
      ;;
    --prompt)
      USER_PROMPT="$2"
      shift 2
      ;;
    --focus)
      FOCUS_DIRS="$2"
      shift 2
      ;;
    *)
      if [[ -z "$FEATURE_NAME" ]]; then
        FEATURE_NAME="$1"
      else
        FEATURE_NAME="$FEATURE_NAME $1"
      fi
      shift
      ;;
  esac
done

# Validate feature name
if [[ -z "$FEATURE_NAME" ]]; then
  echo "Error: Feature name is required" >&2
  echo "" >&2
  echo "   Example: /forge:plan \"user authentication\"" >&2
  exit 1
fi

# Create output directories
mkdir -p "$OUTPUT_DIR"
mkdir -p .claude

# Generate slug for filename (max 60 characters)
FEATURE_SLUG=$(echo "$FEATURE_NAME" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | tr -cd '[:alnum:]-' | cut -c1-60)
SPEC_PATH="$OUTPUT_DIR/$FEATURE_SLUG.md"
JSON_PATH="$OUTPUT_DIR/$FEATURE_SLUG.json"
PROGRESS_PATH="$OUTPUT_DIR/$FEATURE_SLUG-progress.txt"
DRAFT_PATH=".claude/forge-draft.md"
STATE_PATH=".claude/forge-${FEATURE_SLUG}.md"
SURVEY_DIR="docs/recon/$FEATURE_SLUG/survey"
REALITY_PATH="docs/recon/$FEATURE_SLUG/reality.md"
TIMESTAMP=$(date +%Y-%m-%d)

# Create survey directory
mkdir -p "$SURVEY_DIR"

# Read context file if provided
CONTEXT_CONTENT=""
if [[ -n "$CONTEXT_FILE" ]] && [[ -f "$CONTEXT_FILE" ]]; then
  CONTEXT_CONTENT=$(cat "$CONTEXT_FILE")
fi

# Detect project info for survey guidance
PROJECT_LANG=""
if [[ -f "go.mod" ]]; then PROJECT_LANG="go"
elif [[ -f "package.json" ]]; then PROJECT_LANG="javascript/typescript"
elif [[ -f "pyproject.toml" ]] || [[ -f "setup.py" ]]; then PROJECT_LANG="python"
elif [[ -f "Cargo.toml" ]]; then PROJECT_LANG="rust"
elif [[ -f "Package.swift" ]]; then PROJECT_LANG="swift"
fi

# Count source files for survey sizing
SRC_COUNT=$(find . -maxdepth 5 -type f \( -name "*.go" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" -o -name "*.py" -o -name "*.rs" -o -name "*.swift" \) ! -path "*/node_modules/*" ! -path "*/.git/*" ! -path "*/vendor/*" 2>/dev/null | wc -l | tr -d ' ')

# Build the interview prompt
PROMPT_FILE=$(mktemp)

# =========================================================================
# PHASE R0: SURVEY — Parallel codebase research
# =========================================================================

if [[ "$NO_SURVEY" == "false" ]]; then

# Build context-aware scope guidance for survey agents
SCOPE_GUIDANCE=""
if [[ -n "$CONTEXT_CONTENT" ]]; then
  # Extract a summary of the context for agents (first 200 lines max to avoid bloat)
  CONTEXT_SUMMARY=$(echo "$CONTEXT_CONTENT" | head -200)
  SCOPE_GUIDANCE="
SCOPE GUIDANCE — A context file was provided. Focus your exploration on the areas
of the codebase RELEVANT to this context. Do not map the entire repo — focus on
what matters for this feature/spec:

--- CONTEXT SUMMARY ---
$CONTEXT_SUMMARY
--- END CONTEXT SUMMARY ---

Explore code related to the above. Skip unrelated packages/modules."
fi

if [[ -n "$FOCUS_DIRS" ]]; then
  SCOPE_GUIDANCE="$SCOPE_GUIDANCE

FOCUS DIRECTORIES: $FOCUS_DIRS
Prioritize these directories. You may look outside them for dependencies and patterns,
but spend most of your time within these paths."
fi

cat > "$PROMPT_FILE" << SURVEY_PROMPT_EOF
# Forge Specification Engine

You are conducting a codebase-aware specification interview. Unlike a standard interview, you RESEARCH THE CODEBASE FIRST, then ask smart questions grounded in what you found.

## PHASE R0: SURVEY — Codebase Research

Before asking the user a single question, you must deeply explore the codebase. Spawn **4 parallel Explore agents** to investigate different dimensions of the codebase.

**IMPORTANT:** Use the Agent tool with \`subagent_type: "Explore"\` for each. All 4 agents should be spawned in a SINGLE message (parallel execution).
$SCOPE_GUIDANCE

### Agent 1: ARCHITECT
\`\`\`
Explore the architecture of this codebase$(if [[ -n "$SCOPE_GUIDANCE" ]]; then echo " relevant to the feature described in the SCOPE GUIDANCE below"; fi). Map:
- Package/module structure and layer boundaries
- Design patterns in use (MVC, hexagonal, microservices, etc.)
- How components communicate (imports, events, APIs, queues)
- Entry points (main files, handler registrations, route definitions)
- Configuration management (how config reaches code)
$SCOPE_GUIDANCE

Write your findings as structured markdown to: $SURVEY_DIR/architecture.md

Format: Use headers for each area. Include specific file paths. Note patterns with examples.
\`\`\`

### Agent 2: DATA
\`\`\`
Explore data models, storage, and data flow in this codebase$(if [[ -n "$SCOPE_GUIDANCE" ]]; then echo " relevant to the feature described in the SCOPE GUIDANCE below"; fi). Map:
- Database models/schemas (ORMs, migrations, raw SQL)
- Data structures and types (structs, interfaces, type definitions)
- Data access patterns (repositories, DAOs, direct queries)
- Data flow: input → validation → processing → storage → response
- External data sources (APIs, files, caches, queues)
$SCOPE_GUIDANCE

Write your findings as structured markdown to: $SURVEY_DIR/data.md

Format: Use headers for each area. Include specific file paths and type names.
\`\`\`

### Agent 3: SURFACE
\`\`\`
Explore the public surface area of this codebase$(if [[ -n "$SCOPE_GUIDANCE" ]]; then echo " relevant to the feature described in the SCOPE GUIDANCE below"; fi). Map:
- API endpoints/routes (HTTP methods, paths, handlers)
- UI components/pages (if frontend exists)
- CLI commands/flags (if CLI exists)
- Exported functions and public interfaces
- Extension points (where new features plug in)
- Authentication/authorization patterns
$SCOPE_GUIDANCE

Write your findings as structured markdown to: $SURVEY_DIR/surface.md

Format: Use headers for each area. Include specific file paths and function names.
\`\`\`

### Agent 4: INFRA
\`\`\`
Explore the infrastructure, testing, and tooling in this codebase$(if [[ -n "$SCOPE_GUIDANCE" ]]; then echo " relevant to the feature described in the SCOPE GUIDANCE below"; fi). Map:
- Test patterns (unit, integration, e2e — frameworks, fixtures, helpers)
- CI/CD configuration (pipelines, quality gates)
- Build system and dependencies (package manager, build tools)
- Environment configuration (env vars, config files, secrets management)
- Linting/formatting tools and conventions
- Deployment patterns (Docker, K8s, serverless, etc.)
$SCOPE_GUIDANCE

Write your findings as structured markdown to: $SURVEY_DIR/infra.md

Format: Use headers for each area. Include specific file paths and tool names.
\`\`\`

**After all 4 agents complete**, read all 4 survey files and proceed to PHASE R1.

SURVEY_PROMPT_EOF

else
  # No survey mode - skip directly to interview
cat > "$PROMPT_FILE" << 'NOSURVEY_PROMPT_EOF'
# Forge Specification Engine

You are conducting a specification interview. The --no-survey flag was set, so codebase research is skipped (greenfield or empty project).

Proceed directly to PHASE R2 (INTERVIEW) below.

NOSURVEY_PROMPT_EOF
fi

# =========================================================================
# PHASE R1: SYNTHESIZE — Merge research into reality document
# =========================================================================

if [[ "$NO_SURVEY" == "false" ]]; then

# Build context block for R1 synthesis
SYNTH_CONTEXT=""
if [[ -n "$CONTEXT_CONTENT" ]]; then
  SYNTH_CONTEXT="
### Feature Context

The user provided a context file describing what they want to build. Use this to PRIORITIZE
your synthesis — highlight the parts of the codebase most relevant to this feature and
deprioritize areas that don't apply.

--- FEATURE CONTEXT ---
$(echo "$CONTEXT_CONTENT" | head -300)
--- END FEATURE CONTEXT ---
"
fi

cat >> "$PROMPT_FILE" << SYNTH_PROMPT_EOF

## PHASE R1: SYNTHESIZE — Build Codebase Reality Document

Read all 4 survey files and synthesize them into a single **codebase reality document**. Write this to the reality path specified in SESSION INFORMATION below.
$SYNTH_CONTEXT
**Key instruction:** Do NOT just concatenate the survey files. Synthesize them — cross-reference findings, resolve contradictions, and prioritize information relevant to the feature being built ("$FEATURE_NAME").

Structure the reality document as:

\`\`\`markdown
# Codebase Reality: $FEATURE_NAME

## Architecture Summary
- How the app is organized (layers, packages, communication patterns)
- Key design patterns with specific examples

## Data Landscape
- Existing models and their relationships
- Data access patterns (with specific file/function references)
- Storage technologies in use

## Public Surface
- Existing endpoints/pages/commands relevant to this feature
- Extension points where new code plugs in
- Auth/authz model (if relevant)

## Conventions to Follow
- Naming patterns (with examples from codebase)
- Error handling style (with examples)
- Test patterns (with examples from test files)
- Logging approach

## Integration Points
- Where new feature code should live (specific packages/directories)
- What existing code to extend vs. create new
- Dependencies to be aware of

## Risks & Constraints
- Tight coupling areas
- Missing test coverage
- Tech debt that affects this feature area
- Performance considerations
\`\`\`

This document is the foundation for every interview question. Every question you ask in R2 should reference specific findings from this document.

**After writing the reality document, proceed to PHASE R2.**

SYNTH_PROMPT_EOF
fi

# =========================================================================
# PHASE R2: INTERVIEW — Codebase-grounded adaptive interview
# =========================================================================

cat >> "$PROMPT_FILE" << 'INTERVIEW_PROMPT_EOF'

## PHASE R2: INTERVIEW — Codebase-Grounded Adaptive Interview

You are now conducting a comprehensive specification interview. This works EXACTLY like a Lisa interview — multi-round, adaptive, progressive — but every question is grounded in your codebase research.

### CRITICAL RULES

#### 1. USE AskUserQuestion FOR ALL QUESTIONS
You MUST use the AskUserQuestion tool for every question you ask. Plain text questions will NOT work — the user cannot respond to them. Every question must go through AskUserQuestion with 2-4 concrete options.

#### 2. GROUND EVERY QUESTION IN CODEBASE REALITY
If you performed the survey, reference specific findings:
- BAD: "How should authentication work?"
- GOOD: "I see your auth middleware in `middleware/auth.go` uses JWT with RBAC. Should the new feature extend this existing RBAC model, or does it need a separate permission system?"
- BAD: "What's the data model?"
- GOOD: "Your User struct in `models/user.go` has 8 fields. The new feature needs permissions — should we add a `permissions []string` field to User, or create a separate Permission model with a foreign key?"
- BAD: "How should errors be handled?"
- GOOD: "I see you wrap errors with `fmt.Errorf('...: %w', err)` in `services/` and use sentinel errors in `pkg/errors/`. Should the new feature follow this same pattern?"

#### 3. ASK NON-OBVIOUS QUESTIONS
DO NOT ask basic questions the codebase already answers. Probe decisions, trade-offs, and intent:
- "I found 3 similar features using pattern X — should this one follow suit or is there a reason to diverge?"
- "Your test coverage for auth is integration-heavy but the API layer is mostly unit tests — which approach for the new feature?"
- "The existing API uses REST but I see a GraphQL schema file — is this feature REST or are you migrating?"

#### 4. BE DELIBERATE, NOT FAST
This is NOT a speed run. You are building a comprehensive specification that will drive weeks of
implementation. Take time to:
- Explore each domain thoroughly before moving to the next
- Ask follow-up questions when answers are vague ("what specifically happens when X?")
- Circle back to earlier topics when new information changes the picture
- Validate your understanding by restating what you heard before moving on

Do NOT try to cover everything in 3-5 questions. A good forge interview is 10-20+ questions across
multiple rounds. The spec quality directly correlates with interview depth.

#### 5. CONTINUE UNTIL USER SAYS STOP
The interview continues until the user explicitly says "done", "finalize", "finished", or similar. Do NOT stop after one round. After each answer, immediately ask the next question using AskUserQuestion.

#### 6. MAINTAIN RUNNING DRAFT
After every 2-3 questions, update the draft spec file with accumulated information using the Write tool. This ensures nothing is lost if the session is interrupted.

#### 7. BE ADAPTIVE
Base your next question on previous answers. If the user mentions something interesting, probe deeper. Do not follow a rigid script. Build on what you learn.

### DOMAIN DETECTION

Analyze the feature request and classify which domains apply. This determines your question focus:

| Domain | Signals | Question Focus |
|--------|---------|----------------|
| Auth | login, permission, role, token, session | Token strategy, RBAC model, session management |
| API | endpoint, route, handler, REST, GraphQL | HTTP methods, payloads, validation, versioning |
| Data | model, schema, database, query, migration | Schema design, access patterns, indexes, caching |
| Frontend | page, component, form, UI, UX | Component hierarchy, state management, responsive |
| Infra | deploy, CI, Docker, K8s, config | Deployment strategy, environment config, scaling |
| Security | encrypt, PII, compliance, audit | Threat model, data classification, audit logging |
| Testing | test, coverage, fixture, mock | Test strategy, coverage requirements, test data |
| Integration | webhook, event, queue, external API | Contract design, retry logic, circuit breakers |
| Performance | latency, throughput, cache, optimize | Budgets, caching strategy, profiling approach |

Apply 1-3 primary domains. Ask domain-specific questions for each.

### RED FLAG DETECTION

Watch for these red flags in the user's description and probe deeper:

| Red Flag | Risk | Mandatory Follow-up |
|----------|------|---------------------|
| "simple" or "just" | Scope underestimation | "What makes this simpler than [similar feature in codebase]?" |
| No error handling mentioned | Incomplete thinking | "What happens when [operation] fails?" |
| "like X but for Y" | Hidden complexity in delta | "What specifically differs from X?" |
| "secure" without specifics | Security theater | "What threat model? What data classification?" |
| "ASAP" or "quick" | Shortcut pressure | "What can we defer to Phase 2 vs. must-have in Phase 1?" |
| Vague acceptance criteria | Unverifiable requirements | "How would you TEST that this works?" |
| No mention of existing code | Greenfield assumption on brownfield | "How does this interact with [existing feature I found]?" |

### QUESTION PROGRESSION

**Round 1 — Universal (3-5 questions)**
Grounded versions of these core questions:
- What does "done" look like? (verifiable acceptance criteria)
- What is explicitly OUT of scope?
- What related code already exists? (Reference what you found in survey)
- What happens when things go wrong?
- Who/what depends on this?

**Round 2+ — Domain-Specific (adaptive)**
Based on detected domains, ask targeted questions. Examples:

**Auth domain:**
- "I see [current auth pattern]. Should new feature extend it or diverge?"
- "Token lifetime? Refresh strategy? What happens on expiry?"
- "Role hierarchy — flat list or nested permissions?"

**API domain:**
- "I see your handlers follow [pattern from surface.md]. Same pattern?"
- "Pagination strategy? Cursor-based like [existing endpoint] or offset?"
- "Rate limiting? Your current setup uses [X] — same for new endpoints?"

**Data domain:**
- "I found [existing models]. New feature adds [what] to the data model?"
- "Migration strategy — additive only or breaking changes?"
- "Caching layer? I see [cache pattern] in [file] — reuse it?"

**Frontend domain:**
- "Component library — I see [existing components]. Extend or new?"
- "State management — you use [X pattern]. Same for new feature?"
- "Responsive requirements? I see [current breakpoint strategy]."

**Round 3+ — Cross-Cutting Concerns (2-3 questions)**
Pick the most relevant:
- Blast radius: "What could break if this feature fails?"
- Rollback: "How do we undo this if it goes wrong?"
- Monitoring: "What metrics/alerts should we add?"
- Performance: "Latency/throughput budgets?"
- Documentation: "API docs, user docs, or internal docs needed?"

### INTERVIEW WORKFLOW

1. Read the reality document (if survey was performed)
2. Read any provided context
3. Detect domains and red flags from the feature name + context
4. Ask first grounded question using AskUserQuestion
5. After user responds, update draft if enough for a section
6. Ask next question immediately using AskUserQuestion
7. Repeat until user says "done" or "finalize"
8. When done, proceed to PHASE R3

INTERVIEW_PROMPT_EOF

# =========================================================================
# First Principles mode (optional, inserted before interview)
# =========================================================================

if [[ "$FIRST_PRINCIPLES" == "true" ]]; then
  cat >> "$PROMPT_FILE" << 'FP_EOF'

### FIRST PRINCIPLES MODE — ACTIVE

Before detailed spec gathering, challenge the user's assumptions (3-5 questions):

1. "What specific problem led to this idea?"
2. "What happens if we don't build this? Cost of inaction?"
3. "What's the simplest thing that might solve this?"
4. "What would make this the WRONG approach?"
5. "Is there an existing solution (internal, external, off-the-shelf)?"

If the approach seems valid, say: "The approach is sound. Let's move to detailed specification."
If flawed, help discover a better alternative before proceeding.

FP_EOF
fi

# =========================================================================
# Context injection (if provided)
# =========================================================================

if [[ -n "$CONTEXT_CONTENT" ]]; then
  cat >> "$PROMPT_FILE" << CONTEXT_EOF

## PROVIDED CONTEXT

\`\`\`
$CONTEXT_CONTENT
\`\`\`
CONTEXT_EOF
fi

# Detect GSD research in context
if [[ -n "$CONTEXT_CONTENT" ]] && echo "$CONTEXT_CONTENT" | grep -q "^## GSD Research Context"; then
  cat >> "$PROMPT_FILE" << 'GSD_EOF'

## GSD RESEARCH DETECTED — INTERVIEW ADAPTATION

The provided context contains GSD research output. Your survey agents may find overlapping information. Adapt:

### SKIP (GSD already covered):
- Generic tech stack questions — GSD Stack Research has this
- Generic architecture questions — GSD Architecture Research has this
- Generic feature discovery — GSD Feature Research catalogs these

### PROBE INSTEAD (GSD is broad but shallow):
- **Acceptance criteria**: "GSD identified [feature] — what proves it works?"
- **Edge cases**: "What happens when [feature] hits [failure mode]?"
- **Constraints**: "GSD recommends [tech] — version/deployment constraints?"
- **Pitfall handling**: "GSD flagged [pitfall] — user-facing behavior?"
- **Verification**: "What command proves [requirement] works?"

### MERGE with survey findings:
Cross-reference GSD research with what your survey agents found. Where they agree, skip.
Where they conflict, ask the user. Where GSD has gaps, your survey fills them.

GSD_EOF
fi

# =========================================================================
# PHASE R3: SPEC — Generate foundry-ready specification
# =========================================================================

cat >> "$PROMPT_FILE" << 'SPEC_PROMPT_EOF'

## PHASE R3: SPEC — Generate Foundry-Ready Specification

When the user says "done", "finalize", "finished", or similar, generate the specification.

### SPEC FORMAT (Foundry-Compatible)

The spec MUST use these ID schemes for foundry traceability:
- **US-NNN**: User Stories
- **FR-NNN**: Functional Requirements (lower-level than US)
- **NFR-NNN**: Non-Functional Requirements
- **AC-NNN**: Acceptance Criteria (nested under US/FR)
- **OT-NNN**: Observable Truths (per domain, min 5 each — foundry verification targets)

### SPEC PHILOSOPHY

You know this codebase. The spec should reflect that. Do NOT generate a generic spec that could
apply to any project. Every section should reference specific files, functions, patterns, and
conventions discovered during the survey. A developer reading this spec should be able to start
coding immediately without exploring the codebase themselves.

Take your time. A thorough spec prevents weeks of back-and-forth during implementation.

### SPEC TEMPLATE

```markdown
# Specification: {FEATURE_NAME}

> Generated by Forge v1.0.0 | Survey: {N} agents | Interview: {N} rounds
> Date: {TIMESTAMP}

## Problem Statement
[1-3 sentences from interview]

## Scope

### In Scope
- [Explicit list from interview]

### Out of Scope
- [Explicit list from interview — be specific about what is NOT included]

---

## User Stories

### US-001: [Story Title]
**As a** [user type], **I want** [action], **so that** [benefit].

**Acceptance Criteria:**
- AC-001: [Specific, testable criterion — e.g., "POST /api/users returns 201 with Location header"]
- AC-002: [Error case — e.g., "Duplicate email returns 409 with error body {code: 'EMAIL_EXISTS'}"]
- AC-003: [Edge case — e.g., "Password under 8 chars returns 400 with validation details"]

**Codebase Integration:**
- Extends: `services/auth.go:AuthService.CreateUser` (line ~45) — add permission check
- Follows pattern: `handlers/users.go:HandleCreateUser` — validate → service → respond
- New files: `services/permissions.go` (in `services/` alongside existing service files)
- Modifies: `models/user.go:User` struct — add `Permissions []string` field

### US-002: ...

---

## Functional Requirements

- FR-001: [Requirement with specific behavior] — Maps to US-001
- FR-002: [Requirement with specific behavior] — Maps to US-001, US-002

## Non-Functional Requirements

- NFR-001: [Requirement with measurable metric — e.g., "API response < 200ms p95"]
- NFR-002: ...

---

## Technical Design

### Data Model Changes

**Current state** (from survey):
[Show the EXISTING model/schema that will be modified, with file path]

**Proposed changes:**
[Show exactly what fields/tables/types are added/modified/removed]
[Include migration strategy if schema changes — additive only? breaking?]

### API Design

**New endpoints:**
| Method | Path | Handler | Request Body | Response | Auth |
|--------|------|---------|-------------|----------|------|
| POST   | /api/... | `handlers/...` | `{...}` | 201: `{...}` | Required |

**Modified endpoints:**
[Which existing endpoints change and how — reference current handler file paths]

**Pattern to follow:**
[Reference a specific existing endpoint as the template — e.g., "Follow handlers/users.go:HandleCreateUser"]

### Architecture

**Component diagram:**
[How new components fit into existing architecture — reference actual packages]

**Dependency flow:**
[What depends on new code, what new code depends on — reference specific imports]

### Error Handling

**Pattern to follow** (from survey):
[Reference the actual error handling pattern in the codebase — e.g., "Wrap with fmt.Errorf like services/users.go:L34"]

**Error cases for this feature:**
| Scenario | HTTP Status | Error Code | Message |
|----------|-------------|------------|---------|
| ... | 400 | VALIDATION_ERROR | "..." |
| ... | 409 | CONFLICT | "..." |

---

## File Change Map

Exactly which files are touched and what happens in each:

### Modified Files
| File | What Changes | Lines/Functions Affected |
|------|-------------|------------------------|
| `models/user.go` | Add Permissions field to User struct | `User` struct (~L15) |
| `services/auth.go` | Add permission check to CreateUser | `CreateUser()` (~L45) |
| ... | ... | ... |

### New Files
| File | Purpose | Pattern Source |
|------|---------|---------------|
| `services/permissions.go` | Permission CRUD service | Follows `services/users.go` pattern |
| `handlers/permissions.go` | Permission API handlers | Follows `handlers/users.go` pattern |
| ... | ... | ... |

---

## Observable Truths

These are verification targets for foundry's INSPECT/ASSAY phases.
Each must be independently verifiable by reading code or running a test.

### Domain: [domain-name]
- OT-001: [User-perspective verifiable statement — e.g., "A user with 'admin' role can access GET /api/admin"]
- OT-002: [Error case — e.g., "A user without 'admin' role receives 403 from GET /api/admin"]
- OT-003: [Edge case — e.g., "A user with empty permissions array can only access public endpoints"]
- OT-004: [Integration — e.g., "Creating a user with POST /api/users assigns default permissions"]
- OT-005: [Data — e.g., "Permissions are stored in the users table, not a separate join table"]

### Domain: [domain-name-2]
- OT-006: ...

---

## Implementation Phases

### Phase 1: Foundation
- [ ] [Specific task — e.g., "Add Permissions field to User struct in models/user.go"]
- [ ] [Specific task — e.g., "Create migration 003_add_permissions.sql"]
- [ ] [Specific task — e.g., "Create services/permissions.go with CRUD methods"]
- **Verification:** `go build ./...` and `go test ./models/... ./services/...`
- **Depends on:** nothing (foundation)

### Phase 2: Core
- [ ] [Specific task — e.g., "Create handlers/permissions.go following handlers/users.go pattern"]
- [ ] [Specific task — e.g., "Register routes in routes.go after existing /api/users routes"]
- [ ] [Specific task — e.g., "Add permission middleware to protected routes"]
- **Verification:** `go test ./handlers/... && curl -X POST localhost:8080/api/permissions`
- **Depends on:** Phase 1

### Phase 3: Integration & Polish
- [ ] [Specific task — e.g., "Update CreateUser to assign default permissions"]
- [ ] [Specific task — e.g., "Add permission checks to existing admin endpoints"]
- [ ] [Specific task — e.g., "Add integration tests for full permission flow"]
- **Verification:** `go test ./... -count=1` (full suite)
- **Depends on:** Phase 2

---

## Test Strategy

**Existing test patterns** (from survey):
- Unit tests: [e.g., "Table-driven tests in services/users_test.go — follow this pattern"]
- Integration tests: [e.g., "Uses testcontainers for Postgres in tests/integration/"]
- Fixtures: [e.g., "Test data in testdata/ directory, loaded via helpers.LoadFixture()"]

**Tests to write for this feature:**
| Test File | Tests | Type |
|-----------|-------|------|
| `services/permissions_test.go` | CRUD operations, validation, edge cases | Unit |
| `handlers/permissions_test.go` | HTTP status codes, auth, validation | Unit |
| `tests/integration/permissions_test.go` | Full flow with real DB | Integration |

**Coverage target:** [Based on existing project standards from survey]

---

## Codebase References

Key files, functions, and patterns from the survey that inform this spec:

| Reference | Why It Matters |
|-----------|---------------|
| `models/user.go:User` | Struct being extended with permissions |
| `handlers/users.go:HandleCreateUser` | Pattern template for new handlers |
| `services/users.go:UserService` | Pattern template for new service |
| `middleware/auth.go:RequireAuth` | Where permission checks plug in |
| `tests/integration/users_test.go` | Pattern template for integration tests |
```

### SPEC WRITING RULES

1. Every US MUST have 2+ testable ACs including at least one error/edge case
2. Every AC must be verifiable (not "works correctly" — specific HTTP status, specific behavior)
3. Every "Codebase Integration" section must reference REAL files with line numbers from the survey
4. The File Change Map must list EVERY file that will be modified or created
5. Observable Truths must be user-perspective, verifiable, and include error cases
6. Implementation phases must reference specific files/functions with verification commands
7. Test strategy must reference actual test patterns and name specific test files to create
8. Technical Design must show current state AND proposed changes (not just proposed)
9. Error handling must follow the project's existing pattern (reference specific examples)
10. Do NOT use placeholder text — every example in the spec should be real and specific

SPEC_PROMPT_EOF

# =========================================================================
# PHASE R4: VALIDATE — Self-check
# =========================================================================

cat >> "$PROMPT_FILE" << 'VALIDATE_PROMPT_EOF'

## PHASE R4: VALIDATE — Self-Check Before Declaring Done

After writing the spec, perform these validation checks:

### File Reference Check
For every file path mentioned in the spec:
- Use Glob or Read to verify it exists
- If it doesn't exist, mark it as "[NEW]" in the spec (proposed new file)
- If it's wrong, fix the reference

### Pattern Reference Check
For key function/type references:
- Use Grep to verify they exist in the codebase
- Fix any incorrect references

### Coverage Check
- Does every US have acceptance criteria?
- Does every domain have 5+ Observable Truths?
- Are there obvious feature gaps? (e.g., mentioned auth but no logout story)
- Are error cases covered for every happy path?

### Report Issues
If validation finds issues, fix them in the spec before finalizing.

VALIDATE_PROMPT_EOF

# =========================================================================
# FINALIZATION CONSTRAINTS
# =========================================================================

cat >> "$PROMPT_FILE" << 'FINAL_PROMPT_EOF'

## FINALIZATION CONSTRAINTS — CRITICAL

When the user says "done", "finalize", "finished", or similar:

### SEQUENCE:
1. Generate the full spec (PHASE R3 template above)
2. Validate the spec (PHASE R4 checks above)
3. Write final markdown spec to the spec path
4. Write JSON spec to the JSON path
5. Write progress file with all phases marked [PENDING]
6. Delete the state file using Write with empty content
7. Output `<promise>SPEC FORGED</promise>`
8. STOP IMMEDIATELY

### ALLOWED ACTIONS:
- Read any files needed for validation
- Write the final spec, JSON, and progress files
- Glob/Grep for validation checks
- Delete state file

### FORBIDDEN ACTIONS:
- NO implementation of any kind
- NO code changes
- NO Task/Agent tool calls during finalization
- NO offering to implement — the spec is the deliverable

### JSON SPEC FORMAT:
Write the JSON spec with this structure:
```json
{
  "feature": "FEATURE_NAME",
  "slug": "FEATURE_SLUG",
  "version": "1.0.0",
  "generated_by": "forge",
  "timestamp": "TIMESTAMP",
  "survey": { "performed": true/false, "agents": 4, "files": ["architecture.md", "data.md", "surface.md", "infra.md"] },
  "user_stories": [{ "id": "US-001", "title": "...", "acceptance_criteria": ["AC-001: ...", "AC-002: ..."] }],
  "functional_requirements": [{ "id": "FR-001", "description": "...", "maps_to": ["US-001"] }],
  "nonfunctional_requirements": [{ "id": "NFR-001", "description": "..." }],
  "observable_truths": [{ "id": "OT-001", "domain": "...", "statement": "..." }],
  "implementation_phases": [{ "phase": 1, "name": "...", "tasks": ["..."], "verification": "..." }],
  "codebase_references": ["file1.go", "file2.ts"]
}
```

### CRITICAL: SPEC FORGED MEANS STOP
After outputting `<promise>SPEC FORGED</promise>`, you MUST stop. Do not:
- Offer to implement the feature
- Suggest next steps beyond "use /foundry --spec"
- Make any code changes
- Run any commands

The spec is the deliverable. Foundry builds it.

FINAL_PROMPT_EOF

# =========================================================================
# Session information
# =========================================================================

cat >> "$PROMPT_FILE" << SESSION_EOF

## SESSION INFORMATION

- **Feature:** $FEATURE_NAME
- **Feature Slug:** $FEATURE_SLUG
- **Draft File:** $DRAFT_PATH (update this every 2-3 questions)
- **Final Spec:** $SPEC_PATH (write here when user says done)
- **JSON Spec:** $JSON_PATH (write here when user says done)
- **Progress:** $PROGRESS_PATH (write here when user says done)
- **Survey Directory:** $SURVEY_DIR (agents write here)
- **Reality Document:** $REALITY_PATH (synthesized survey)
- **State File:** $STATE_PATH (delete when done)
- **Started:** $TIMESTAMP
- **Project Language:** ${PROJECT_LANG:-"unknown (survey will detect)"}
- **Source File Count:** $SRC_COUNT
- **Survey Mode:** $(if [[ "$NO_SURVEY" == "true" ]]; then echo "SKIPPED"; else echo "ACTIVE"; fi)
- **Focus Directories:** ${FOCUS_DIRS:-"entire project"}
$(if [[ -n "$USER_PROMPT" ]]; then echo "- **User Intent:** $USER_PROMPT"; fi)

---

$(if [[ -n "$USER_PROMPT" ]]; then
cat << INTENT_EOF
## USER INTENT

The user told you what they want: **"$USER_PROMPT"**

This is your primary directive. Everything — the survey focus, the interview questions, the spec output —
should serve this intent. For example:
- "refine this spec deeper" → read the context file as an existing spec, probe its gaps, produce a more detailed version
- "focus on error handling" → survey for error patterns, ask about failure modes, spec every error case
- "add observability" → survey for logging/metrics, ask about SLOs, spec monitoring requirements
- "break this into smaller pieces" → analyze the context for decomposition boundaries

Adapt your approach to match what the user asked for.

INTENT_EOF
fi)

## BEGIN NOW

$(if [[ "$NO_SURVEY" == "false" ]]; then
  echo "Start by spawning the 4 survey agents in parallel (PHASE R0). All 4 in a SINGLE message."
  echo ""
  echo "Replace {SURVEY_DIR} in the agent prompts with: $SURVEY_DIR"
  if [[ -n "$FOCUS_DIRS" ]]; then
    echo ""
    echo "Focus survey agents on these directories: $FOCUS_DIRS"
  fi
else
  echo "Survey is skipped. Begin the interview immediately by asking your first grounded question about \"$FEATURE_NAME\" using AskUserQuestion."
fi)

SESSION_EOF

# Read the complete prompt
INTERVIEW_PROMPT=$(cat "$PROMPT_FILE")
rm "$PROMPT_FILE"

# Write state file
cat > "$STATE_PATH" << STATE_EOF
---
active: true
engine: forge
version: "1.0.0"
phase: "R0_SURVEY"
iteration: 1
max_iterations: $MAX_QUESTIONS
started_at: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
feature_name: "$FEATURE_NAME"
feature_slug: "$FEATURE_SLUG"
output_dir: "$OUTPUT_DIR"
spec_path: "$SPEC_PATH"
json_path: "$JSON_PATH"
progress_path: "$PROGRESS_PATH"
draft_path: "$DRAFT_PATH"
state_path: "$STATE_PATH"
survey_dir: "$SURVEY_DIR"
reality_path: "$REALITY_PATH"
context_file: "$CONTEXT_FILE"
no_survey: $NO_SURVEY
first_principles: $FIRST_PRINCIPLES
focus_dirs: "$FOCUS_DIRS"
user_prompt: "$USER_PROMPT"
---

$INTERVIEW_PROMPT
STATE_EOF

# Initialize draft spec
cat > "$DRAFT_PATH" << DRAFT_EOF
# Specification Draft: $FEATURE_NAME

*Forge interview in progress - Started: $TIMESTAMP*

## Survey Status
$(if [[ "$NO_SURVEY" == "true" ]]; then echo "Skipped (--no-survey)"; else echo "- [ ] Architecture agent"; echo "- [ ] Data agent"; echo "- [ ] Surface agent"; echo "- [ ] Infra agent"; echo "- [ ] Reality document synthesized"; fi)

## Overview
[To be filled during interview]

## Problem Statement
[To be filled during interview]

## Scope

### In Scope
- [To be filled during interview]

### Out of Scope
- [To be filled during interview]

## User Stories

<!--
Format each story with VERIFIABLE acceptance criteria and CODEBASE INTEGRATION:

### US-001: [Story Title]
**As a** [user], **I want** [action], **so that** [benefit].

**Acceptance Criteria:**
- AC-001: [Specific, testable — e.g., "API returns 200 for valid input"]
- AC-002: [Another — e.g., "Error message shown for invalid email"]

**Codebase Integration:**
- Extends: [file:function from survey]
- Pattern: [existing pattern to follow]
- New: [proposed file locations]
-->

[To be filled during interview]

## Functional Requirements
<!-- FR-001: [Description] — Maps to: US-NNN -->
[To be filled during interview]

## Non-Functional Requirements
<!-- NFR-001: [Description with specific metric] -->
[To be filled during interview]

## Technical Design

### Data Model
[To be filled — reference existing models from survey]

### API Design
[To be filled — follow existing endpoint patterns from survey]

### Architecture
[To be filled — align with existing architecture from survey]

## Observable Truths
<!--
Per domain, min 5 each. User-perspective, verifiable.
- OT-001: [Statement a user or test can verify]
-->
[To be filled during interview]

## Implementation Phases

### Phase 1: Foundation
- [ ] [Task with specific file references]
- **Verification:** \`[command]\`

### Phase 2: Core
- [ ] [Task with specific file references]
- **Verification:** \`[command]\`

### Phase 3: Integration
- [ ] [Task with specific file references]
- **Verification:** \`[command]\`

## Test Strategy
[Reference actual test patterns from survey]

## Codebase References
[Key files and patterns from survey]

## Definition of Done
- [ ] All acceptance criteria pass
- [ ] All Observable Truths verified
- [ ] Tests pass: \`[command]\`
- [ ] Lint/typecheck: \`[command]\`
- [ ] Build succeeds: \`[command]\`

## Next Steps

\`\`\`
/foundry --spec $SPEC_PATH
\`\`\`

Forge plans. Foundry builds.

## Open Questions
[To be filled during interview]

---
*Interview notes accumulated below*
---

DRAFT_EOF

# Output setup message
echo "Forge - Codebase-Aware Specification Engine"
echo ""
echo "Feature: $FEATURE_NAME"
echo "State: $STATE_PATH"
echo "Draft: $DRAFT_PATH"
echo "Output: $SPEC_PATH"
echo "JSON: $JSON_PATH"
echo "Survey: $SURVEY_DIR"
echo "Reality: $REALITY_PATH"
if [[ -n "$CONTEXT_FILE" ]]; then
  echo "Context: $CONTEXT_FILE"
fi
if [[ $MAX_QUESTIONS -gt 0 ]]; then
  echo "Max Questions: $MAX_QUESTIONS"
else
  echo "Max Questions: unlimited"
fi
if [[ "$NO_SURVEY" == "true" ]]; then
  echo "Survey: SKIPPED (--no-survey)"
else
  echo "Survey: ACTIVE (4 parallel agents)"
  if [[ -n "$FOCUS_DIRS" ]]; then
    echo "Focus: $FOCUS_DIRS"
  fi
fi
if [[ "$FIRST_PRINCIPLES" == "true" ]]; then
  echo "Mode: First Principles (challenges assumptions first)"
fi
if [[ -n "$USER_PROMPT" ]]; then
  echo "Intent: $USER_PROMPT"
fi
echo ""
echo "Forge researches first, then interviews. Say \"done\" when finished."
echo ""
echo "$INTERVIEW_PROMPT"
