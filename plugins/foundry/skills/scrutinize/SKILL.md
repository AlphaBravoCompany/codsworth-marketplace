---
name: scrutinize
description: Review decomposed spec files for ambiguity, missing details, and drift risk
user_invocable: true
model: opus
allowed-tools: Read, Grep, Glob, Bash, Edit, Write
---

# /scrutinize — Per-File Spec Scrutiny

Review each decomposed spec file against 7 quality checks. Can run on a single file or an entire decomposed directory. Supports auto-fix mode where failing files are automatically improved and re-checked.

## Arguments

`/scrutinize <path>` — path to a single `.md` file or a decomposed directory
`/scrutinize <path> --fix` — enable auto-fix loop (max 3 iterations per file)
`/scrutinize <path> --fix --master-spec <spec-path>` — auto-fix with master spec context

## Task

### Step 0: Determine Mode

Check if the provided path is a file or directory:

```bash
R=$PWD; while [ -n "$R" ] && [ "$R" != / ] && [ ! -d "$R/.claude" ]; do R=${R%/*}; done
"$R/.claude/scripts/scrutinize.sh" detect-mode "$ARGUMENTS"
```

- **Single file**: Run scrutiny on one file
- **Directory**: Batch-process all `.md` files (excluding manifest.json)

### Step 0.5: Structural Pre-Check

Before running the 7 content checks, verify the file has valid structure:

```bash
R=$PWD; while [ -n "$R" ] && [ "$R" != / ] && [ ! -d "$R/.claude" ]; do R=${R%/*}; done
"$R/.claude/scripts/scrutinize.sh" check-structure <file-path>
```

If structural check fails (missing sections, no frontmatter), report those as immediate failures before running content checks.

### Step 1: Run 7 Scrutiny Checks

For each file, evaluate ALL 7 checks independently. Each check is **binary pass/fail**.

#### Check 1: Is the file too large?
- **Pass**: File covers 1-3 user stories, implementable in one focused session
- **Fail**: File tries to cover too many concerns, multiple unrelated features, or would take multiple sessions
- **How to check**: Count requirements (REQ-N), acceptance criteria checkboxes, and distinct concerns in Scope

#### Check 2: Is the file too vague?
- **Pass**: Requirements are specific and actionable ("POST /users returns 201 with user JSON")
- **Fail**: Requirements are vague ("handle user creation properly", "make it work well")
- **How to check**: Look for words like "properly", "correctly", "well", "good", "appropriate" without specifics

#### Check 3: Does it assume unwritten knowledge?
- **Pass**: All referenced concepts, systems, or patterns are defined in this file or in listed dependencies
- **Fail**: References entities, APIs, configurations, or behaviors not documented anywhere in the decomposed set
- **How to check**: Cross-reference mentions against the file's own content, Dependencies section, and depends_on frontmatter

#### Check 4: Are dependencies explicit?
- **Pass**: YAML frontmatter `depends_on` matches Dependencies section; all upstream files are listed
- **Fail**: Dependencies section mentions files not in frontmatter, or frontmatter lists deps not explained in prose
- **How to check**: Compare frontmatter `depends_on` array with files mentioned in Dependencies section

#### Check 5: Are interfaces clear?
- **Pass**: Input/output formats, API shapes, data structures, and events are explicitly defined
- **Fail**: Interfaces section says "N/A" but the file clearly interacts with other components, or descriptions are incomplete
- **How to check**: If the file has dependencies or is depended upon, Interfaces must define the contract

#### Check 6: Are edge cases called out?
- **Pass**: Edge Cases section lists specific scenarios with expected behavior
- **Fail**: Edge Cases is "N/A" or only lists generic cases ("error handling", "invalid input")
- **How to check**: For each requirement, think "what could go wrong?" — if the answer isn't in Edge Cases, it fails

#### Check 7: Could AI misinterpret this?
- **Pass**: Instructions are unambiguous; there's only one reasonable interpretation
- **Fail**: Phrasing allows multiple valid implementations, or key details are left to interpretation
- **How to check**: For each requirement, ask "could two different developers implement this differently?" If yes, it fails

### Step 2: Report Results

**Single file output:**
```
Scrutiny Report: backend/api-contracts.md
══════════════════════════════════════════

[PASS] 1. File size — 3 user stories, session-scoped
[PASS] 2. Specificity — All requirements have concrete values
[FAIL] 3. Unwritten knowledge — References "UserRole enum" not defined here or in deps
[PASS] 4. Dependencies — Frontmatter matches prose
[FAIL] 5. Interfaces — Missing response schema for POST /users
[PASS] 6. Edge cases — 4 edge cases with expected behaviors
[PASS] 7. Ambiguity — Instructions are unambiguous

Result: FAIL (2 issues)
Issues:
  - Check 3: "UserRole enum" referenced but not defined in this file or data/schema.md
  - Check 5: POST /users response body shape not specified
```

**Directory output:**
```
Scrutiny Report: docs/specs/auth-decomposed/
═════════════════════════════════════════════

| File                        | Status | Issues |
|-----------------------------|--------|--------|
| foundation/project-setup.md | PASS   | —      |
| data/schema.md              | PASS   | —      |
| backend/api-contracts.md    | FAIL   | 2      |
| backend/business-logic.md   | PASS   | —      |
| frontend/components.md      | FAIL   | 1      |
| testing/strategy.md         | PASS   | —      |

Summary: 4/6 passed, 2 failed
```

### Step 3: Auto-Fix Loop (if --fix)

For each failing file:

1. **Read** the failing file and the master spec (if `--master-spec` provided)
2. **Identify** the specific failures from Step 2
3. **Fix** the file:
   - Check 1 (too large): Split into multiple files, update manifest
   - Check 2 (too vague): Add specific values, concrete behaviors, measurable criteria
   - Check 3 (unwritten knowledge): Add missing definitions or add to depends_on
   - Check 4 (dependencies): Sync frontmatter and prose
   - Check 5 (interfaces): Define input/output schemas, API shapes
   - Check 6 (edge cases): Add specific edge case scenarios with expected behavior
   - Check 7 (ambiguity): Rephrase to eliminate multiple interpretations
4. **Re-check** the fixed file (run all 7 checks again)
5. **Repeat** up to 3 times per file
6. If still failing after 3 iterations: mark as **stuck**

Update manifest.json scrutiny fields after each iteration:

```bash
R=$PWD; while [ -n "$R" ] && [ "$R" != / ] && [ ! -d "$R/.claude" ]; do R=${R%/*}; done
"$R/.claude/scripts/scrutinize.sh" update-manifest <output-dir> <domain/file> <status> <iteration> <failures-json>
```

### Step 4: Final Report (after auto-fix)

```
Auto-Fix Report: docs/specs/auth-decomposed/
══════════════════════════════════════════════

| File                        | Before | After | Iterations |
|-----------------------------|--------|-------|------------|
| backend/api-contracts.md    | FAIL   | PASS  | 2          |
| frontend/components.md      | FAIL   | STUCK | 3          |

Fixed: 1 file
Stuck: 1 file (frontend/components.md)

Stuck file issues:
  frontend/components.md:
    - Check 7: Ambiguous component naming convention — needs human decision
```
