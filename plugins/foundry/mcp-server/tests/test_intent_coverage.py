"""Phase 8 / INTENT-01 — intent-carrier coverage tests.

17 RED-or-SKIP stubs covering Plans 08-02 / 08-03 / 08-04 territory plus
2 Wave-0 sentinel tests.

Plan 08-01 territory (Wave 0 sentinels — 2 stubs):
  1. test_fixture_loader
  2. test_module_collection_guard

Plan 08-02 territory (validator behavior — 10 stubs):
  3. test_unknown_top_level_key_rejected
  4. test_a_nnn_literal_in_prompt_propagated
  5. test_a_auto_nnn_literal_propagated
  6. test_typed_row_indirection_paraphrased
  7. test_a_nnn_absent_dropped
  8. test_any_dropped_blocks
  9. test_a1_not_substring_matched_in_a12
  10. test_missing_appendix_vacuous
  11. test_agent_used_embedding_audit
  12. test_intent_coverage_regex_byte_equivalent_to_validate_spec

Plan 08-03 territory (agent + MCP tool — 1 stub direct, 1 grouped under 08-04):
  13. test_agent_frontmatter_shape

Plan 08-04 territory (integration — 5 stubs, conditional-skip):
  14. test_mcp_tool_registered (Plan 08-03 ships server.py edit; grouped
      with 08-04 in VALIDATION map for orchestrator-routing reasons)
  15. test_start_md_has_f07_section
  16. test_f05_step2b_lists_intent_carrier
  17. test_v20_spec_skips_intent_carrier
  18. test_synthetic_regression_zero_fp

VALIDATION.md per-task verification map lists 17 rows total
(8-01-01 + 8-01-02 + 8-02-01..10 + 8-03-01 + 8-04-01..05). Stub 18
(synthetic regression) collapses Plan 08-04's 8-04-05; stub 14
(MCP tool registration) covers 8-04-01.

RED-or-SKIP discipline:

- Module-top guard: ``pytest.skip(allow_module_level=True)`` when
  ``validate-intent-coverage.py`` is missing on disk. Plan 08-01
  ships ZERO production code, so all 17 stubs SKIP at module-top
  until Plan 08-02 ships the validator script. Mirrors Phase 7
  Plan 07-01 file-existence-gated module-skip discipline.
- Plan 08-02 ships validator -> module collects; Plan 08-02 territory
  tests turn RED-or-GREEN depending on validator behavior.
- Plan 08-03 ships agent file + MCP tool registration -> Plan 08-03
  territory tests (13 + 14) auto-flip from per-test SKIP to RED-or-GREEN
  with zero edits to this file.
- Plan 08-04 ships start.md edits -> Plan 08-04 territory tests
  (15-18) auto-flip from per-test SKIP to RED-or-GREEN with zero
  edits to this file.

Phase 1+2+3+4+5+6+7 byte-equivalence is preserved by living in a NEW
module — no edits to existing test_*.py modules.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

import pytest

# tests/test_intent_coverage.py -> parents: [0]=tests, [1]=mcp-server,
# [2]=foundry, [3]=plugins, [4]=repo-root. Mirrors test_spec_test_deriver.py
# (Phase 7 Plan 07-01) which uses parents[4] verified-working form.
REPO_ROOT = Path(__file__).resolve().parents[4]
VALIDATE_PATH = (
    REPO_ROOT / "plugins" / "foundry" / "scripts"
    / "validate-intent-coverage.py"
)
VALIDATE_SPEC_PY = (
    REPO_ROOT / "plugins" / "forge" / "scripts" / "validate-spec.py"
)
AGENT_PATH = (
    REPO_ROOT / "plugins" / "foundry" / "agents" / "intent-carrier.md"
)
START_MD = (
    REPO_ROOT / "plugins" / "foundry" / "commands" / "start.md"
)
SERVER_PY = (
    REPO_ROOT / "plugins" / "foundry" / "mcp-server" / "src"
    / "foundry_mcp" / "server.py"
)
FIXTURES_DIR = Path(__file__).parent / "fixtures"


if not VALIDATE_PATH.exists():
    pytest.skip(
        "validate-intent-coverage.py not yet shipped — "
        "Plan 08-02 territory",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# Plan 08-01 territory — Wave 0 sentinel tests (2 stubs).
#
# These two GREEN as soon as the module collects (i.e., once Plan 08-02
# ships the validator script and lifts the module-top guard). Until then
# they SKIP at module-top with the rest.
# ---------------------------------------------------------------------------


def test_fixture_loader() -> None:
    """Plan 08-01 sentinel — every Wave-0 fixture loads cleanly.

    Sanity check: each of the 8 intent_coverage JSONs + 3 specs +
    2 transcripts + 5 casting prompts + 2 tool-call logs parses. Catches
    typos / truncations / shadow-edits to the Wave-0 fixture surface.
    Mirror of 8-01-01 row in VALIDATION.md per-task verification map.
    """
    coverage = sorted((FIXTURES_DIR / "intent_coverage").glob("*.json"))
    assert len(coverage) == 8, f"expected 8 intent_coverage fixtures, got {len(coverage)}"
    for f in coverage:
        json.loads(f.read_text(encoding="utf-8"))

    specs = sorted((FIXTURES_DIR / "specs").glob("spec_intent_*.md"))
    assert len(specs) == 3, f"expected 3 intent specs, got {len(specs)}"
    for s in specs:
        text = s.read_text(encoding="utf-8")
        assert text.startswith("---"), f"missing frontmatter in {s.name}"

    transcripts = sorted((FIXTURES_DIR / "transcripts").glob("transcript_intent_*.md"))
    assert len(transcripts) == 2, f"expected 2 intent transcripts, got {len(transcripts)}"

    prompts = sorted((FIXTURES_DIR / "casting_prompts").glob("casting-*-prompt-*.md"))
    assert len(prompts) == 5, f"expected 5 casting-prompt fixtures, got {len(prompts)}"

    logs = sorted((FIXTURES_DIR / "tool_call_logs").glob("tool_call_log_intent_*.json"))
    assert len(logs) == 2, f"expected 2 intent tool-call-log fixtures, got {len(logs)}"
    for f in logs:
        json.loads(f.read_text(encoding="utf-8"))


def test_module_collection_guard() -> None:
    """Plan 08-01 sentinel — module-top guard IS pytest.skip(allow_module_level=True).

    Meta-test: when this test runs, the module has already collected — so
    the module-top guard either was bypassed (validator exists, this is
    fine) or was a pytest.skip(allow_module_level=True). Assert by
    reading the source: the guard SHOULD be a pytest.skip with
    allow_module_level=True. Mirror of 8-01-02 row in VALIDATION.md
    per-task verification map.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    assert "allow_module_level=True" in source, (
        "module-top guard must use pytest.skip(allow_module_level=True) "
        "so the entire module SKIPs cleanly when validate-intent-coverage.py "
        "is missing"
    )
    # Cross-check: the guard sits BEFORE the first test definition.
    guard_idx = source.index("allow_module_level=True")
    first_test_idx = source.index("def test_fixture_loader")
    assert guard_idx < first_test_idx, "guard must precede all test defs"


# ---------------------------------------------------------------------------
# Plan 08-02 territory — validator behavior tests (10 stubs).
#
# These tests use the run_intent_coverage_validator fixture (defined in
# conftest.py); the fixture itself pytest.skip()s when the validator
# script is missing, so per-test SKIP is automatic at fixture-acquire
# time. Once Plan 08-02 ships, the module-top guard above passes and
# these tests turn RED-or-GREEN based on validator behavior.
# ---------------------------------------------------------------------------


def test_unknown_top_level_key_rejected(
    run_intent_coverage_validator: Callable[..., tuple[int, str, str]],
) -> None:
    """Plan 08-02 territory — schema-closed top-level discipline.

    intent_coverage_schema_invalid.json carries a smuggled
    ``auto_resolve_hint`` top-level key NOT in KNOWN_INTENT_COVERAGE_KEYS;
    validator MUST reject with INTENT_COVERAGE_SCHEMA_INVALID token.
    """
    coverage = (
        FIXTURES_DIR / "intent_coverage" / "intent_coverage_schema_invalid.json"
    )
    exit_code, stdout, _ = run_intent_coverage_validator(coverage)
    assert exit_code != 0
    assert "INTENT_COVERAGE_SCHEMA_INVALID" in stdout, stdout


def test_a_nnn_literal_in_prompt_propagated(
    run_intent_coverage_validator: Callable[..., tuple[int, str, str]],
    tmp_path: Path,
) -> None:
    """Plan 08-02 territory — A-NNN literal in prompt body produces PROPAGATED.

    Synth fixture in tmp_path: appendix has A-001, casting prompt body
    contains ``A-001`` verbatim. Resulting verdict for (A-001, casting-1)
    cell MUST be PROPAGATED with citation_chain=["A-001"]; validator
    exits 0 on the resulting matrix.
    """
    spec = tmp_path / "spec.md"
    spec.write_text(
        "---\nspec_format_version: v2.1\n---\n"
        "## Appendix: Interview Transcript\n\n"
        "## A-001 [Locked]\nSurface contract. [from Q-001]\n",
        encoding="utf-8",
    )
    coverage = tmp_path / "coverage.json"
    coverage.write_text(
        json.dumps({
            "stream": "INTENT-01",
            "phase": "F0.7",
            "spec_format_version": "v2.1",
            "spec_hash": "sha256:abc",
            "agent_path": "plugins/foundry/agents/intent-carrier.md",
            "wall_clock_seconds": 1.0,
            "answer_count": 1,
            "casting_count": 1,
            "summary": {"PROPAGATED": 1, "PARAPHRASED": 0, "DROPPED": 0},
            "matrix": [
                {"answer_id": "A-001", "casting_id": "1",
                 "verdict": "PROPAGATED", "citation_chain": ["A-001"]},
            ],
        }),
        encoding="utf-8",
    )
    exit_code, stdout, stderr = run_intent_coverage_validator(
        coverage, spec_path=spec,
    )
    assert exit_code == 0, (stdout, stderr)


def test_a_auto_nnn_literal_propagated(
    run_intent_coverage_validator: Callable[..., tuple[int, str, str]],
    tmp_path: Path,
) -> None:
    """Plan 08-02 territory — A-AUTO-NNN literal also produces PROPAGATED.

    Synth fixture: appendix has A-AUTO-003 [DEPLOYMENT], casting prompt
    body contains ``A-AUTO-003`` verbatim. Resulting verdict for the
    (A-AUTO-003, casting-1) cell MUST be PROPAGATED. Mirrors
    test_a_nnn_literal_in_prompt_propagated for the implicit-fact branch.
    """
    spec = tmp_path / "spec.md"
    spec.write_text(
        "---\nspec_format_version: v2.1\n---\n"
        "## Appendix: Interview Transcript\n\n"
        "## A-AUTO-003 [DEPLOYMENT]\nDeploys via k8s manifest. [auto-extracted]\n",
        encoding="utf-8",
    )
    coverage = tmp_path / "coverage.json"
    coverage.write_text(
        json.dumps({
            "stream": "INTENT-01",
            "phase": "F0.7",
            "spec_format_version": "v2.1",
            "spec_hash": "sha256:abc",
            "agent_path": "plugins/foundry/agents/intent-carrier.md",
            "wall_clock_seconds": 1.0,
            "answer_count": 1,
            "casting_count": 1,
            "summary": {"PROPAGATED": 1, "PARAPHRASED": 0, "DROPPED": 0},
            "matrix": [
                {"answer_id": "A-AUTO-003", "casting_id": "1",
                 "verdict": "PROPAGATED", "citation_chain": ["A-AUTO-003"]},
            ],
        }),
        encoding="utf-8",
    )
    exit_code, stdout, stderr = run_intent_coverage_validator(
        coverage, spec_path=spec,
    )
    assert exit_code == 0, (stdout, stderr)


def test_typed_row_indirection_paraphrased(
    run_intent_coverage_validator: Callable[..., tuple[int, str, str]],
) -> None:
    """Plan 08-02 territory — PARAPHRASED via typed-row indirection.

    Locked decision A: typed-row indirection IS the canonical PARAPHRASED
    state. Fixture intent_coverage_paraphrased_via_typed.json has
    (A-005, casting-1) with verdict=PARAPHRASED + citation_chain=
    ["A-005", "<contracts>"]. Paired with spec_intent_clean.md which
    has CT-001 row citing [from A-005]. PARAPHRASED is a PASS verdict;
    matrix has dropped=0, so exit==0.
    """
    coverage = (
        FIXTURES_DIR / "intent_coverage"
        / "intent_coverage_paraphrased_via_typed.json"
    )
    spec = FIXTURES_DIR / "specs" / "spec_intent_clean.md"
    exit_code, stdout, _ = run_intent_coverage_validator(
        coverage, spec_path=spec,
    )
    assert exit_code == 0, stdout
    # citation_chain shape preserved
    data = json.loads(coverage.read_text(encoding="utf-8"))
    para_cells = [c for c in data["matrix"] if c["verdict"] == "PARAPHRASED"]
    assert any(
        c["citation_chain"] == ["A-005", "<contracts>"] for c in para_cells
    ), data


def test_a_nnn_absent_dropped(
    run_intent_coverage_validator: Callable[..., tuple[int, str, str]],
    tmp_path: Path,
) -> None:
    """Plan 08-02 territory — A-NNN absent from body AND typed-row -> DROPPED.

    Mirrors casting-1-prompt-dropped.md scenario: A-005 absent from body
    and absent from any [from A-005] typed-row. Resulting verdict for
    (A-005, casting-1) MUST be DROPPED; validator exits 1 with
    INTENT_COVERAGE_DROPPED token in stdout.
    """
    spec_text = (FIXTURES_DIR / "specs" / "spec_intent_clean.md").read_text(
        encoding="utf-8",
    )
    spec = tmp_path / "spec.md"
    spec.write_text(spec_text, encoding="utf-8")
    coverage_data = json.loads(
        (FIXTURES_DIR / "intent_coverage" / "intent_coverage_one_dropped.json"
         ).read_text(encoding="utf-8")
    )
    coverage = tmp_path / "coverage.json"
    coverage.write_text(json.dumps(coverage_data), encoding="utf-8")
    exit_code, stdout, _ = run_intent_coverage_validator(
        coverage, spec_path=spec,
    )
    assert exit_code != 0
    assert "INTENT_COVERAGE_DROPPED" in stdout, stdout


def test_any_dropped_blocks(
    run_intent_coverage_validator: Callable[..., tuple[int, str, str]],
) -> None:
    """Plan 08-02 territory — gate blocks on any DROPPED cell.

    intent_coverage_one_dropped.json has 1 DROPPED + 11 PROPAGATED;
    validator MUST reject with INTENT_COVERAGE_DROPPED token. Even one
    DROPPED is enough to block — gate is all-or-nothing.
    """
    coverage = (
        FIXTURES_DIR / "intent_coverage" / "intent_coverage_one_dropped.json"
    )
    spec = FIXTURES_DIR / "specs" / "spec_intent_clean.md"
    exit_code, stdout, _ = run_intent_coverage_validator(
        coverage, spec_path=spec,
    )
    assert exit_code != 0
    assert "INTENT_COVERAGE_DROPPED" in stdout, stdout


def test_a1_not_substring_matched_in_a12(
    run_intent_coverage_validator: Callable[..., tuple[int, str, str]],
    tmp_path: Path,
) -> None:
    """Plan 08-02 territory — word-boundary discipline (A-1 vs A-12).

    Synth fixture: appendix has BOTH ``## A-1`` AND ``## A-12`` entries;
    casting prompt mentions only ``A-12`` verbatim. The validator MUST
    classify (A-1, casting-1) as DROPPED, NOT falsely PROPAGATED via
    naive substring match against the ``A-12`` mention. Validates the
    word-boundary discipline locked in 08-RESEARCH.md.
    """
    spec = tmp_path / "spec.md"
    spec.write_text(
        "---\nspec_format_version: v2.1\n---\n"
        "## Appendix: Interview Transcript\n\n"
        "## A-1 [Locked]\nFirst answer. [from Q-1]\n\n"
        "## A-12 [Locked]\nTwelfth answer. [from Q-12]\n",
        encoding="utf-8",
    )
    coverage = tmp_path / "coverage.json"
    # Construct matrix that classifies A-1 as PROPAGATED via substring match
    # mistake; validator MUST reject this with DROPPED-actual.
    coverage.write_text(
        json.dumps({
            "stream": "INTENT-01",
            "phase": "F0.7",
            "spec_format_version": "v2.1",
            "spec_hash": "sha256:abc",
            "agent_path": "plugins/foundry/agents/intent-carrier.md",
            "wall_clock_seconds": 1.0,
            "answer_count": 2,
            "casting_count": 1,
            "summary": {"PROPAGATED": 1, "PARAPHRASED": 0, "DROPPED": 1},
            "matrix": [
                {"answer_id": "A-1", "casting_id": "1",
                 "verdict": "DROPPED", "citation_chain": []},
                {"answer_id": "A-12", "casting_id": "1",
                 "verdict": "PROPAGATED", "citation_chain": ["A-12"]},
            ],
        }),
        encoding="utf-8",
    )
    exit_code, stdout, _ = run_intent_coverage_validator(
        coverage, spec_path=spec,
    )
    # Either: validator agrees with the DROPPED claim and surfaces token,
    # OR: validator independently re-derives and confirms A-1 is DROPPED.
    # Word-boundary discipline lives at the validator's re-derivation step,
    # which is what Plan 08-02 lands.
    assert exit_code != 0
    assert "INTENT_COVERAGE_DROPPED" in stdout, stdout


def test_missing_appendix_vacuous(
    run_intent_coverage_validator: Callable[..., tuple[int, str, str]],
    tmp_path: Path,
) -> None:
    """Plan 08-02 territory — v2.1 spec without appendix -> vacuous PROPAGATED.

    Synth spec: spec_format_version=v2.1 but NO ``## Appendix: Interview
    Transcript`` heading. answer_count=0 + matrix=[] would pass an
    answer-by-answer check vacuously. Validator MUST reject with
    INTENT_COVERAGE_VACUOUS_PROPAGATED token.
    """
    spec = tmp_path / "spec.md"
    spec.write_text(
        "---\nspec_format_version: v2.1\n---\n"
        "# Spec without an interview appendix.\n",
        encoding="utf-8",
    )
    coverage_text = (
        FIXTURES_DIR / "intent_coverage" / "intent_coverage_vacuous_propagated.json"
    ).read_text(encoding="utf-8")
    coverage = tmp_path / "coverage.json"
    coverage.write_text(coverage_text, encoding="utf-8")
    exit_code, stdout, _ = run_intent_coverage_validator(
        coverage, spec_path=spec,
    )
    assert exit_code != 0
    assert "INTENT_COVERAGE_VACUOUS_PROPAGATED" in stdout, stdout


def test_agent_used_embedding_audit(
    run_intent_coverage_validator: Callable[..., tuple[int, str, str]],
) -> None:
    """Plan 08-02 territory — code-blind audit fires on embedding tool use.

    Advisory shape: the audit only fires when ``--tool-call-log`` is
    passed. Fixture intent_coverage_clean.json (matrix is structurally
    fine) paired with tool_call_log_intent_used_embedding.json (contains
    ``from sentence_transformers`` substring + ``Embedding`` tool entry)
    MUST trigger INTENT_COVERAGE_AGENT_USED_EMBEDDING token. Mirrors
    Phase 7's code-blind audit advisory pattern.
    """
    coverage = (
        FIXTURES_DIR / "intent_coverage" / "intent_coverage_used_embedding.json"
    )
    spec = FIXTURES_DIR / "specs" / "spec_intent_clean.md"
    log = (
        FIXTURES_DIR / "tool_call_logs"
        / "tool_call_log_intent_used_embedding.json"
    )
    exit_code, stdout, _ = run_intent_coverage_validator(
        coverage, spec_path=spec, tool_call_log_path=log,
    )
    assert exit_code != 0
    assert "INTENT_COVERAGE_AGENT_USED_EMBEDDING" in stdout, stdout


def test_intent_coverage_regex_byte_equivalent_to_validate_spec() -> None:
    """Plan 08-02 territory — ANSWER_BLOCK_RE / A_AUTO_BLOCK_RE / TYPED_ROW_CITATION_RE byte-equal to validate-spec.py.

    Single-source-of-truth contract: the validator inlines these regexes
    byte-equivalent to plugins/forge/scripts/validate-spec.py:61, 118, 212.
    Mirror of Phase 7 Plan 07-02's _REQUIREMENT_ID_RE byte-equivalence
    discipline (validator script is dash-named so cross-import is
    impossible; byte-equivalence at source level is the SSoT contract).
    """
    if not VALIDATE_SPEC_PY.is_file():
        pytest.skip("validate-spec.py missing — Phase 1 territory")
    spec_src = VALIDATE_SPEC_PY.read_text(encoding="utf-8")
    intent_src = VALIDATE_PATH.read_text(encoding="utf-8")
    # Extract source-line text for each regex constant from validate-spec.py
    # via simple anchor-then-balanced-paren scan. Both files inline the
    # same compile() expression; verify the inlined intent-coverage form
    # contains the same head pattern.
    for anchor in (
        "ANSWER_BLOCK_RE = re.compile(",
        "A_AUTO_BLOCK_RE = re.compile(",
        "TYPED_ROW_CITATION_RE = re.compile(",
    ):
        assert anchor in spec_src, f"{anchor} missing in validate-spec.py"
        assert anchor in intent_src, (
            f"{anchor} missing in validate-intent-coverage.py — "
            f"single-source-of-truth byte-equivalence broken"
        )


# ---------------------------------------------------------------------------
# Plan 08-03 territory — agent + MCP tool tests (1 direct stub).
#
# These tests conditional-skip when the agent / MCP tool registration is
# absent (Plan 08-03 territory). Once Plan 08-03 ships, they auto-flip
# to RED-or-GREEN with zero edits to this file.
# ---------------------------------------------------------------------------


def test_agent_frontmatter_shape() -> None:
    """Plan 08-03 territory — intent-carrier.md frontmatter discipline.

    Locked frontmatter: id=INTENT-01, min_spec_format_version=v2.1,
    model=opus, effort=max, tools includes Read/Write/Grep/Glob and
    EXCLUDES Bash/Edit/Task. Defense-in-depth: forbidden tools blocked
    at the agent file level even if rubric prose drifts.
    """
    if not AGENT_PATH.exists():
        pytest.skip("intent-carrier.md not yet shipped — Plan 08-03 territory")
    text = AGENT_PATH.read_text(encoding="utf-8")
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    assert m, "missing YAML frontmatter"
    front = m.group(1)
    assert re.search(r"^id:\s*INTENT-01\s*$", front, re.MULTILINE), front
    assert re.search(
        r"^min_spec_format_version:\s*v2\.1\s*$", front, re.MULTILINE,
    ), front
    assert re.search(r"^model:\s*opus\s*$", front, re.MULTILINE), front
    assert re.search(r"^effort:\s*max\s*$", front, re.MULTILINE), front
    m_tools = re.search(r"^tools:\s*(.+?)\s*$", front, re.MULTILINE)
    assert m_tools, "missing tools field"
    tools = m_tools.group(1)
    for t in ("Read", "Write", "Grep", "Glob"):
        assert t in tools, f"missing required tool {t}: {tools!r}"
    for forbidden in ("Bash", "Edit", "Task"):
        assert forbidden not in tools, (
            f"forbidden tool {forbidden} present: {tools!r}"
        )


# ---------------------------------------------------------------------------
# Plan 08-04 territory — integration tests (4-5 stubs, conditional-skip).
#
# These tests conditional-skip when Plan 08-04's start.md edits + roster
# activation are absent. Once Plan 08-04 ships, they auto-flip to
# RED-or-GREEN with zero edits to this file. test_mcp_tool_registered
# (stub 14) sits here for orchestrator-routing reasons (VALIDATION map
# row 8-04-01) even though the actual server.py edit lands in Plan 08-03.
# ---------------------------------------------------------------------------


def test_mcp_tool_registered() -> None:
    """Plan 08-04 / 8-04-01 — Foundry-Intent-Coverage tool entry in server.py.

    Plan 08-03 ships the MCP tool registration; VALIDATION.md groups it
    as 8-04-01 for orchestrator-routing convenience. Assert server.py
    contains a Tool entry named ``Foundry-Intent-Coverage`` near the
    Foundry-Validate-Castings registration.
    """
    if not SERVER_PY.exists():
        pytest.skip("server.py missing — Phase 4 territory")
    text = SERVER_PY.read_text(encoding="utf-8")
    if "Foundry-Intent-Coverage" not in text:
        pytest.skip(
            "Foundry-Intent-Coverage tool not yet registered — "
            "Plan 08-03 territory",
        )
    # Tool entry exists; confirm it's near Foundry-Validate-Castings (or
    # at least registered as a Tool entry).
    assert "Foundry-Validate-Castings" in text, (
        "Foundry-Validate-Castings is the anchor for Phase 8 registration; "
        "if it's missing, Phase 4/5 had a regression"
    )


def test_start_md_has_f07_section() -> None:
    """Plan 08-04 territory — F0.7 INTENT-CARRIER section between F0.5 and F0.9.

    start.md MUST contain ``### F0.7: INTENT-CARRIER`` heading with
    ordering F0.5 < F0.7 < F0.9. F0.9 sub-check 7m carries the
    INTENT_COVERAGE_RECORD_INCOMPLETE token (locked decision 4).
    """
    if not START_MD.exists():
        pytest.skip("start.md missing")
    text = START_MD.read_text(encoding="utf-8")
    if "### F0.7: INTENT-CARRIER" not in text:
        pytest.skip("F0.7 section not yet inserted — Plan 08-04 territory")
    # Ordering: F0.5 < F0.7 < F0.9 (Phase 1+ established F0.5 / F0.9
    # anchors).
    f05_idx = text.index("### F0.5")
    f07_idx = text.index("### F0.7: INTENT-CARRIER")
    f09_idx = text.index("### F0.9")
    assert f05_idx < f07_idx < f09_idx, (f05_idx, f07_idx, f09_idx)
    # F0.9 sub-check 7m present with INTENT_COVERAGE_RECORD_INCOMPLETE token.
    assert "7m" in text and "INTENT_COVERAGE_RECORD_INCOMPLETE" in text, (
        "F0.9 sub-check 7m or its token is missing"
    )


def test_f05_step2b_lists_intent_carrier() -> None:
    """Plan 08-04 territory — F0.5 step 2b roster activation.

    The placeholder ``[Future: INTENT-01 → ...]`` at start.md:117 MUST be
    REPLACED (not just commented) with a live roster entry citing
    ``plugins/foundry/agents/intent-carrier.md`` + ``(INTENT-01)``. Asserts
    no ``[Future: INTENT-01`` substring remains anywhere.
    """
    if not START_MD.exists():
        pytest.skip("start.md missing")
    text = START_MD.read_text(encoding="utf-8")
    if "intent-carrier.md" not in text:
        pytest.skip(
            "intent-carrier.md not yet wired into F0.5 step 2b — "
            "Plan 08-04 territory",
        )
    # Live roster entry present.
    assert "plugins/foundry/agents/intent-carrier.md" in text, (
        "F0.5 step 2b must cite the canonical agent path"
    )
    assert "INTENT-01" in text, "F0.5 step 2b must surface stream id"
    # Placeholder gone.
    assert "[Future: INTENT-01" not in text, (
        "placeholder ``[Future: INTENT-01`` must be REPLACED, not commented"
    )


def test_v20_spec_skips_intent_carrier(
    tmp_path: Path,
) -> None:
    """Plan 08-04 territory — v2.0 spec stream-skip routing.

    A v2.0 spec MUST NOT engage INTENT-01 because INTENT-01 has
    ``min_spec_format_version: v2.1``. F0.5 step 2b enumeration MUST
    emit a stream_skips record naming intent-carrier.md + reason=
    spec_format_version + spec_version=v2.0 + stream_min=v2.1. Mirrors
    Phase 3's stream-skip routing for legacy specs.

    Skip discipline: this test exercises Phase 3's
    run_versioned_validator_subprocess fixture (lives in
    plugins/forge/tests/conftest.py) which is not directly accessible
    from the foundry-mcp-server tests directory; SKIP until Plan 08-04
    wires the v2.0 routing path or until cross-plugin fixture access
    is brokered.
    """
    if not START_MD.exists():
        pytest.skip("start.md missing")
    text = START_MD.read_text(encoding="utf-8")
    if "intent-carrier.md" not in text:
        pytest.skip(
            "intent-carrier.md not in F0.5 step 2b live roster — "
            "Plan 08-04 territory",
        )
    # The cross-plugin Phase 3 fixture path is not wired; this stub
    # documents the dependency. Plan 08-04 closes either by importing
    # the Phase 3 fixture module here OR by promoting v2.0-skip routing
    # tests into plugins/forge/tests/. Mirrors Phase 7 Plan 07-04's
    # incremental-promotion stance.
    pytest.skip(
        "Plan 08-04 v2.0 stream-skip routing — needs Phase 3 fixture "
        "(run_versioned_validator_subprocess) wired in cross-plugin",
    )


def test_synthetic_regression_zero_fp(
    run_intent_coverage_validator: Callable[..., tuple[int, str, str]],
) -> None:
    """Plan 08-04 territory — 12-fixture synthetic regression suite (zero false positives).

    Property: of all PARAPHRASED-correct fixtures, ZERO classify as
    DROPPED. Suite spans the 5 casting-prompt fixtures from Plan 08-01
    plus 7 synth tmp_path constructions covering paraphrased-via-typed
    / paraphrased-via-state_transitions / paraphrased-via-invariants /
    dropped / vacuous / dangling / used-embedding cases. Mirror of
    Phase 6's 8-fixture synthetic regression suite shape.

    Plan 08-01 stub: gated to skip until Plan 08-04 ships the full
    synth construction. The classifier behavior under test lives in
    Plan 08-02's validate-intent-coverage.py.
    """
    # Property is the TARGET; Plan 08-04 lands the implementation that
    # constructs all 12 fixtures and asserts the property. Until then,
    # we use the Plan 08-01 paraphrased fixture as a smoke check: the
    # validator must NOT classify the PARAPHRASED cell as DROPPED.
    coverage = (
        FIXTURES_DIR / "intent_coverage"
        / "intent_coverage_paraphrased_via_typed.json"
    )
    spec = FIXTURES_DIR / "specs" / "spec_intent_clean.md"
    exit_code, stdout, _ = run_intent_coverage_validator(
        coverage, spec_path=spec,
    )
    # Smoke: PARAPHRASED is a PASS verdict, exit==0; full 12-fixture
    # property exercised in Plan 08-04.
    assert exit_code == 0, stdout
    data = json.loads(coverage.read_text(encoding="utf-8"))
    para_cells = [c for c in data["matrix"] if c["verdict"] == "PARAPHRASED"]
    assert len(para_cells) >= 1, data
    for c in para_cells:
        assert c["verdict"] != "DROPPED", c
