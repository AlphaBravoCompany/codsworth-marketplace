---
name: decompose
description: Break a master spec into micro-domain buildable work packets
user_invocable: true
model: opus
effort: high
---

# /decompose — Micro-Domain Spec Decomposer

Break a Lisa-produced master spec into a directory of small, detailed, self-contained domain files ("buildable work packets") ready for Mill execution.

## Arguments

`/decompose <path-to-master-spec>`

Example: `/decompose docs/specs/auth.md`

## Task

### Step 0: Validate Input

Detect the feature name and check for existing decomposition:

```bash
R=$PWD; while [ -n "$R" ] && [ "$R" != / ] && [ ! -d "$R/.claude" ]; do R=${R%/*}; done
FEATURE=$("$R/.claude/scripts/decompose.sh" detect-feature "$ARGUMENTS")
"$R/.claude/scripts/decompose.sh" check-exists "docs/specs/${FEATURE}-decomposed"
```

Read the master spec file at the provided path. If no path given, check for the most recent spec in `docs/specs/`:

```bash
ls -t docs/specs/*.md | head -1
```

If no spec found, tell the user to run Lisa first.

If `check-exists` returns `EXISTS`, this is a **re-decompose** (see Re-Decompose Mode at the bottom).

**Auto-approve mode**: When running via `claude --print` (pipeline automation), skip the user approval prompt in Step 1 and auto-approve the proposed tree.

### Step 1: Analyze and Propose Domain Tree

Read the full master spec. Identify the major domains of work.

**Predefined domains** (use when content fits): foundation, backend, frontend, data, infra, testing, observability, security

**Custom domains**: Create additional domain-specific categories when content doesn't fit standard buckets (e.g., `billing/`, `compliance/`, `patient-records/`).

**Granularity rule**: Each file should map to ~1 focused coding session (1-3 user stories max). If a domain area is too large, split it into multiple files within the domain subdirectory.

**Pass-through detection**: If the spec covers only a single domain (one logical area of work), skip full decomposition. Instead, reformat the master spec into the universal template (see Step 2) and produce a single file.

Present the proposed domain tree to the user:

```
Proposed Domain Breakdown for: {feature}
═══════════════════════════════════════

docs/specs/{feature}-decomposed/
├── foundation/
│   ├── project-setup.md — Initialize project structure, dependencies, config
│   └── environments.md — Dev/staging/prod environment configuration
├── backend/
│   ├── api-contracts.md — REST API endpoints, request/response schemas
│   └── business-logic.md — Core business rules and service layer
├── data/
│   └── schema.md — Database tables, relationships, migrations
├── frontend/
│   ├── components.md — UI component library and design system
│   └── pages.md — Page-level layouts and routing
└── testing/
    └── strategy.md — Test plan, fixtures, CI integration

Total: {N} files across {M} domains
```

Ask the user to approve or request changes. In `--print` (automated) mode, auto-approve.

### Step 2: Generate Domain Files

For each file in the approved tree, generate a markdown file using the **strict universal template**. Every file MUST have all 12 sections. Missing/irrelevant sections are marked `N/A`.

**YAML Frontmatter:**
```yaml
---
domain: {domain-name}
file: {file-name}
depends_on:
  - {domain/file}
  - {domain/file}
estimated_complexity: low | medium | high
---
```

**12 Sections (all required):**

1. **## Purpose** — What this domain file covers and why it exists
2. **## Scope** — What's included and explicitly excluded
3. **## Requirements** — Numbered requirements (REQ-1, REQ-2, ...)
4. **## Explicit Behaviors** — Specific behaviors that MUST be implemented (not vague)
5. **## Dependencies** — What other domain files this depends on and what it needs from each
6. **## Interfaces** — Input/output formats, API contracts, events emitted/consumed
7. **## Constraints** — Limits, performance requirements, size bounds
8. **## Edge Cases** — Unusual scenarios that must be handled
9. **## Acceptance Criteria** — Specific, verifiable criteria (checkboxes)
10. **## Definition of Done** — What "complete" means for this domain
11. **## Related Files** — Cross-references to other decomposed files (not hard deps)
12. **## Testing Strategy** — How to test this domain, verification commands

**Content richness rule**: Each file must contain enough detail that AI can implement it WITHOUT referring back to the master spec. Pull specific details, data structures, API shapes, business rules, and constraints from the master spec into each file.

Write files to `docs/specs/{feature}-decomposed/{domain}/{file}.md`.

### Step 3: Generate Manifest

After all files are written, generate `docs/specs/{feature}-decomposed/manifest.json`.

**Schema:**
```json
{
  "feature": "{feature-name}",
  "master_spec": "{path-to-master-spec}",
  "output_dir": "docs/specs/{feature}-decomposed",
  "created_at": "{ISO-8601 timestamp}",
  "domains": [
    {
      "name": "{domain-name}",
      "path": "{domain}/",
      "files": [
        {
          "name": "{file-name}",
          "path": "{domain}/{file}.md",
          "depends_on": ["{domain/file}", ...],
          "domain_type": "predefined" | "custom",
          "complexity": "low" | "medium" | "high",
          "status": "pending",
          "must_haves": {
            "truths": [
              "User can log in with email/password",
              "Invalid credentials return 401"
            ],
            "artifacts": [
              {"path": "src/api/auth/login.ts", "provides": "Login endpoint", "min_lines": 30},
              {"path": "src/components/LoginForm.tsx", "provides": "Login UI", "min_lines": 50}
            ],
            "key_links": [
              {"from": "LoginForm.tsx", "to": "/api/auth/login", "via": "fetch in onSubmit"},
              {"from": "login.ts", "to": "User model", "via": "prisma query"}
            ]
          },
          "research_context": "See research/auth.md for JWT best practices",
          "scrutiny": {
            "status": "pending",
            "iterations": 0,
            "last_run": null,
            "failures": []
          }
        }
      ]
    }
  ],
  "waves": [
    ["{domain/file}", ...],
    ["{domain/file}", ...],
    ...
  ],
  "stats": {
    "total_files": N,
    "total_domains": N,
    "total_waves": N
  }
}
```

**must_haves structure** (required for each file):
- **truths**: Testable assertions that prove the domain works. Should be user-facing, observable behaviors (not implementation details). Minimum 3 per file.
- **artifacts**: Expected files with their purpose and minimum substantive line count. `min_lines` prevents stubs from passing — a 5-line "login endpoint" is a red flag.
- **key_links**: How artifacts connect to each other and to other domains. These form the wiring verification checklist for the TRACE phase.
- **research_context**: Optional pointer to research findings relevant to this domain (from F0 RESEARCH phase).

**Wave computation**: Group files into parallel execution batches. Wave 1 = files with no dependencies. Wave 2 = files whose dependencies are all in wave 1. Etc. Detect and report circular dependencies as errors.

After writing the manifest, validate it:

```bash
R=$PWD; while [ -n "$R" ] && [ "$R" != / ] && [ ! -d "$R/.claude" ]; do R=${R%/*}; done
"$R/.claude/scripts/decompose.sh" validate-manifest "docs/specs/${FEATURE}-decomposed"
```

### Step 4: Report

Print a summary:

```
Decomposition Complete
══════════════════════

Feature: {feature}
Master spec: {path}
Output: docs/specs/{feature}-decomposed/

Domains: {N}
Files: {N}
Waves: {N}

Wave 1 (parallel): foundation/project-setup, data/schema
Wave 2 (parallel): backend/api-contracts, frontend/components
Wave 3 (parallel): testing/strategy

Manifest: docs/specs/{feature}-decomposed/manifest.json

Next step: /scrutinize docs/specs/{feature}-decomposed/
```

## Re-Decompose Mode

If `docs/specs/{feature}-decomposed/` already exists when `/decompose` is run:

1. Read the existing manifest.json
2. Compare the current master spec against the existing decomposition
3. **New domains**: Add new subdirectories and files
4. **Removed domains**: Delete subdirectories no longer needed
5. **Changed domains**: Update existing files with new content (preserve structure, update details)
6. Regenerate manifest.json

Report what changed:
```
Re-Decompose: {feature}
════════════════════════
Added:   backend/webhooks.md, security/audit-log.md
Updated: backend/api-contracts.md, data/schema.md
Removed: frontend/legacy-compat.md
```
