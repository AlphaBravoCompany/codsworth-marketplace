"""Pytest fixtures for plugins/forge tests.

Install pytest in the development environment with:

    uvx pytest tests/

(Note: the project is PEP 668-managed; do NOT pip-install pytest globally.
``uvx pytest`` runs in an isolated, ephemeral virtualenv. See Plan 01-01
SUMMARY.md for the canonical invocation.)

This file exposes the following reusable fixtures:

- ``fixtures_dir``: session-scoped path to ``tests/fixtures/``
- ``load_fixture``: function returning the text content of a fixture file
- ``run_validator_subprocess``: function invoking ``validate-spec.py`` via subprocess.
  Takes a (spec_path, transcript_path) pair; the fixture builds a synthesized
  spec on-the-fly so the spec's appendix contains the transcript verbatim and
  every user A-NNN is cited in the body. The static ``spec-minimal.md`` is
  used as a header/title template only — its body is replaced. This was added
  in Plan 01-03 to satisfy the validator's structural checks (APPENDIX_INCOMPLETE,
  UNCITED_ANSWERS, UNSOURCED_BULLET, MISSING_GI_ENTRIES) which were impossible
  to satisfy with one static spec across multiple transcript fixtures.
- ``run_setup_forge``: function invoking ``setup-forge.sh`` via subprocess and
  returning the captured ``CompletedProcess`` along with the resolved prompt
  file path (which contains the assembled R0-R4 instructions setup-forge writes
  before the interactive interview begins).
- ``run_typed_validator_subprocess`` (Plan 02-01): function that synthesizes a
  spec body containing the THREE Phase 2 typed tables (invariants /
  state-transitions / contracts) — or omits them entirely when
  ``with_typed_tables=False`` — and invokes validate-spec.py against it. Used
  by Phase 2 RED stubs (test_typed_sections.py) to exercise check_typed_sections
  rules 1/2/3 plus the legacy-v4.2.0 backwards-compat path. The builder shape
  (Option A from 02-01-PLAN.md): ``_build_synthesized_spec`` is extended with a
  ``with_typed_tables`` keyword + auxiliary keyword flags
  (``inject_paraphrase``, ``inject_dangling_citation``,
  ``state_transitions_sentinel``, ``contracts_sentinel``) so a single builder
  serves both Phase 1 and Phase 2 fixtures. Phase 1's
  ``run_validator_subprocess`` fixture continues to use the default
  (``with_typed_tables=False``) and is unchanged in behavior.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest


# Regex to enumerate user-answered A-NNN IDs in a transcript (excluding
# auto-discovered A-AUTO-NNN). Mirrors validate-spec.py:84 ANSWER_REF_RE in
# spirit — anchored on the heading form '## A-NNN'. A-AUTO-NNN is intentionally
# NOT matched because Plan 03 exempts those from check_coverage.
_A_HEADING_RE = re.compile(r"^##\s+(A-\d+)\b", re.MULTILINE)
_A_AUTO_HEADING_RE = re.compile(r"^##\s+(A-AUTO-\d+)\b", re.MULTILINE)
_IMPLICIT_FACT_TAG_BRACKETED_RE = re.compile(
    r"\[IMPLICIT_FACT:[A-Z_]+\]"
)
_ARCH_INVARIANT_TAG_RE = re.compile(r"\[ARCH_INVARIANT")


# Repo paths are computed once at module import. ``conftest.py`` lives at
# ``plugins/forge/tests/conftest.py`` so the forge plugin root is its parent.
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
VALIDATE_SPEC = SCRIPTS_DIR / "validate-spec.py"
SETUP_FORGE = SCRIPTS_DIR / "setup-forge.sh"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@dataclass
class SetupForgeResult:
    """Captured artefacts from a ``setup-forge.sh`` invocation.

    ``process`` is the subprocess.CompletedProcess returned by ``subprocess.run``.
    ``prompt_path`` is the resolved path to the assembled prompt file (the file
    setup-forge.sh writes via the ``PROMPT_FILE`` mktemp before printing it).
    ``prompt_text`` is the contents of that prompt file (or empty string when
    setup-forge.sh exited non-zero before emitting the prompt).
    """

    process: subprocess.CompletedProcess
    prompt_path: Path | None
    prompt_text: str


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Path to the fixtures directory shared by all tests."""
    return FIXTURES_DIR


@pytest.fixture
def load_fixture(fixtures_dir: Path) -> Callable[[str], str]:
    """Return a callable that reads ``fixtures_dir / name`` and returns text.

    Raises ``FileNotFoundError`` with an explicit "Wave 0 plan didn't create it"
    diagnostic so a missing fixture in a downstream wave is easy to spot.
    """

    def _loader(name: str) -> str:
        target = fixtures_dir / name
        if not target.is_file():
            raise FileNotFoundError(
                f"fixture missing: {target} — Wave 0 plan didn't create it. "
                f"Re-run plan 01-01 (Wave 0 scaffolding) to regenerate fixtures."
            )
        return target.read_text()

    return _loader


_ARCH_BLOCK_RE = re.compile(
    r"^##\s+(A-\d+)\s*\[([^\]]*ARCH_INVARIANT[^\]]*)\]"
    r"(?:\s*\([^)]*\))?\s*\n(.*?)"
    r"(?=^##\s+|\Z)",
    re.MULTILINE | re.DOTALL,
)


def _extract_arch_invariant_quote(transcript_text: str) -> tuple[str, str] | None:
    """Find the first ARCH_INVARIANT-tagged answer and extract a short
    verbatim phrase from its body for use in a GI-NNN bullet quote.

    Returns (aid, quote_text) or None if no ARCH_INVARIANT answer is found.

    The quote is a contiguous substring of the answer body, short enough to
    be readable in a GI bullet, with citation markers stripped. validate-spec.py
    normalizes whitespace and unicode punctuation before substring comparison
    so light prose differences are tolerated; we just need a real substring.
    """
    match = _ARCH_BLOCK_RE.search(transcript_text)
    if not match:
        return None
    aid = match.group(1)
    body = match.group(3).strip()
    # Strip [from ...] / [derived from ...] citation markers from the body
    # before picking a quote — the quote should be substantive content, not
    # citation metadata.
    body_no_cite = re.sub(
        r"\[(?:from|derived from)\s+[^\]]+\]", "", body, flags=re.IGNORECASE
    ).strip()
    # Take up to 60 characters of the first non-empty line as the quote.
    # 60 chars is short enough to fit comfortably in a bullet; long enough
    # to be a meaningful verbatim substring. validate-spec.py's
    # normalize_for_compare collapses whitespace runs so our trimming does
    # not need to be byte-exact — but we still want a substring of the
    # normalized body.
    first_line = next(
        (ln.strip() for ln in body_no_cite.splitlines() if ln.strip()), ""
    )
    if not first_line:
        return None
    quote = first_line[:60].rstrip(" ,.;:—-")
    return aid, quote


def _build_global_invariants_block(
    transcript_text: str, has_arch_invariant: bool, fallback_cite: str
) -> str:
    """Build a `## Global Invariants` body that satisfies both
    check_arch_invariants_populated (requires **GI-NNN**) and
    check_locked_fidelity (requires verbatim quote).
    """
    if not has_arch_invariant:
        return f"- The fixture spec exercises the validator gate. {fallback_cite}\n"
    extracted = _extract_arch_invariant_quote(transcript_text)
    if extracted is None:
        # Fall back to a non-Locked descriptive line — should not happen
        # because has_arch_invariant is True, but defensive.
        return f"- The fixture spec exercises the validator gate. {fallback_cite}\n"
    aid, quote = extracted
    # `**GI-001**` triggers Locked-fidelity check; the quoted substring must
    # appear in the cited answer's body. The citation [from A-NNN] resolves
    # the quote to a real transcript answer.
    return f'- **GI-001**: "{quote}" [from {aid}]\n'


def _build_synthesized_spec(
    transcript_text: str,
    *,
    with_typed_tables: bool = False,
    inject_paraphrase: bool = False,
    inject_dangling_citation: bool = False,
    state_transitions_sentinel: bool = False,
    contracts_sentinel: bool = False,
) -> str:
    """Build a minimal valid spec body that pairs cleanly with ``transcript_text``.

    The validator (validate-spec.py) enforces several structural checks that
    a static spec-minimal.md cannot satisfy across multiple transcript
    fixtures simultaneously:

      * ``APPENDIX_INCOMPLETE`` — the appendix MUST contain every transcript
        A-NNN (and A-AUTO-NNN) entry verbatim.
      * ``UNCITED_ANSWERS`` — every user A-NNN in the transcript MUST be
        cited somewhere in the spec body. (A-AUTO-NNN is exempt — Plan 03.)
      * ``UNSOURCED_BULLET`` — every bullet/paragraph in
        ``REQUIRED_CITATION_SECTIONS`` MUST carry a citation marker.
      * ``MISSING_GI_ENTRIES`` — when transcript has any ARCH_INVARIANT-tagged
        answer, ``## Global Invariants`` MUST contain at least one
        ``**GI-NNN**`` bullet.

    This builder synthesizes a body that satisfies all four for any given
    transcript. The body deliberately avoids ``### Locked`` subsections and
    ``**GI-NNN**`` bullets-with-quotes so check_locked_fidelity does not
    fire (no verbatim-substring matching needed). When the transcript carries
    any ARCH_INVARIANT-tagged answer, a single ``GI-001`` bullet is added to
    Global Invariants — it does not need a quoted substring because the
    Locked-fidelity check only enforces verbatim quoting on bullets that
    HAVE a quoted substring; absence of a quote is permitted in the relaxed
    fixture-test path. (Plan 03 / INTV-01 — see Plan 01-01 SUMMARY for
    background on why static fixtures don't work here.)

    Phase 2 extension (Plan 02-01):

    When ``with_typed_tables=True`` the builder additionally emits the THREE
    Phase 2 typed tables (invariants / state-transitions / contracts) using
    the column schemas locked in CONTEXT.md. Until Plan 02-03 ships
    ``check_typed_sections``, these tables are inert — the validator does
    not yet inspect them — so emitting them only matters once Plan 02-03
    lands. Plan 02-01 RED stubs verify the validator surface (warnings,
    failure tokens, exit codes) that 02-03 will produce; the typed-table
    spec body shape is the input contract.

    Auxiliary kwargs steer the Phase 2 negative tests:

      * ``inject_paraphrase=True`` — emit a prose paragraph adjacent to the
        invariants table whose tokens overlap a row's content cells at
        Jaccard ≥0.7 (negative test for rule 3).
      * ``inject_dangling_citation=True`` — append a row whose citation cell
        cites ``A-999`` (an A-NNN not in the transcript) — negative test for
        rule 2.
      * ``state_transitions_sentinel=True`` — emit the documented sentinel
        row in ``## State Transitions`` instead of a data row.
      * ``contracts_sentinel=True`` — same shape, in ``## Contracts``.

    When ``with_typed_tables=False`` (default — Phase 1 invocation path),
    the three typed-table headings are OMITTED entirely. The result mirrors
    Phase 1's builder behavior byte-identically so existing Phase 1 tests
    that depend on ``run_validator_subprocess`` are not perturbed by the
    Plan 02-01 extension.
    """
    user_ids = sorted(set(_A_HEADING_RE.findall(transcript_text)))
    auto_ids = sorted(set(_A_AUTO_HEADING_RE.findall(transcript_text)))
    has_arch_invariant = bool(_ARCH_INVARIANT_TAG_RE.search(transcript_text))

    if not user_ids:
        # Transcript has no user-answered A-NNN entries. Emit a placeholder
        # citation so check_universal_citations does not strip the bullet,
        # but the citation does not resolve to any answer (validate-spec.py
        # will raise DANGLING_CITATION for unresolved A-NNN refs). To avoid
        # that, emit a survey-file citation form instead — these are
        # accepted by _line_has_traceable_marker via CITATION_RE.
        primary_cite = "[from survey/architecture.md]"
        coverage_cites = ""
    else:
        primary_cite = f"[from {user_ids[0]}]"
        # Build a single citation block listing every user A-NNN so
        # check_coverage does not raise UNCITED_ANSWERS.
        coverage_cites = (
            "- All transcript answers are referenced here for coverage: "
            + ", ".join(f"[from {aid}]" for aid in user_ids)
            + "."
        )

    # When ARCH_INVARIANT-tagged answers exist, validate-spec.py's
    # check_arch_invariants_populated requires a **GI-NNN** bullet in
    # ## Global Invariants. The bullet itself is then treated as Locked by
    # _collect_locked_bullets, which means it needs a verbatim-quoted
    # substring matching the cited answer. Pull a short quote from the
    # ARCH_INVARIANT answer body to satisfy check_locked_fidelity.
    gi_block = _build_global_invariants_block(
        transcript_text, has_arch_invariant, primary_cite
    )

    # Phase 2 typed-tables block. When disabled, the synthesized spec contains
    # NO typed-table headings/sections at all (legacy v4.2.0 shape) — Plan
    # 02-03's check_typed_sections rule 1 will warn TYPE_TABLES_MISSING.
    if with_typed_tables:
        gi_block += _build_invariants_table_block(
            transcript_text,
            user_ids,
            primary_cite,
            inject_paraphrase=inject_paraphrase,
            inject_dangling_citation=inject_dangling_citation,
        )
        state_block = _build_state_transitions_section(
            user_ids, sentinel=state_transitions_sentinel
        )
        contracts_block = _build_contracts_section(
            user_ids, sentinel=contracts_sentinel
        )
    else:
        state_block = ""
        contracts_block = ""

    body = (
        "---\n"
        "spec_format_version: v2.0\n"
        "feature: fixture-synthesized\n"
        "created: 2026-05-01\n"
        "---\n"
        "\n"
        "# Spec: fixture-synthesized\n"
        "\n"
        "## Problem Statement\n"
        "\n"
        f"- Validator gate fixture problem statement {primary_cite}.\n"
        + (f"{coverage_cites}\n" if coverage_cites else "")
        + "\n"
        "## Scope\n"
        "\n"
        f"- In scope: exercising validate-spec.py {primary_cite}.\n"
        f"- Out of scope: real product work {primary_cite}.\n"
        "\n"
        "## Global Invariants\n"
        "\n"
        f"{gi_block}"
        "\n"
        f"{state_block}"
        f"{contracts_block}"
        "## Appendix: Interview Transcript\n"
        "\n"
        f"{transcript_text}\n"
    )
    return body


# ---------------------------------------------------------------------------
# Phase 2 typed-table builders (Plan 02-01)
# ---------------------------------------------------------------------------
#
# Schemas locked in 02-CONTEXT.md "Implementation Decisions / Table column
# schemas":
#
#   Invariants:        ID | statement | applies-to | violation | citation     (5 cols)
#   State-transitions: ID | from-state | to-state | trigger | guard | citation (6 cols)
#   Contracts:         ID | surface | input | output | errors | citation     (6 cols)
#
# Sentinel-row form (per CONTEXT.md "Empty-table / non-applicable policy"):
#   any non-ID content cell matches r"^\s*[Nn]one\s*[—\-]\s+.+"
#
# Citation-cell form (Locked-only):  [from A-NNN]
# (no derived from, no survey/, no A-AUTO — TYPED_ROW_CITATION_RE in
# validate-spec.py rejects those when Plan 02-03 ships.)


def _build_invariants_table_block(
    transcript_text: str,
    user_ids: list[str],
    primary_cite: str,
    *,
    inject_paraphrase: bool,
    inject_dangling_citation: bool,
) -> str:
    """Return the body of the typed `## Global Invariants` invariants table.

    Caller has already emitted the `## Global Invariants` heading + a
    Locked-fidelity GI-NNN bullet. This builder appends the typed table
    immediately after that bullet.

    When ``inject_paraphrase`` is True, also emits a prose paragraph
    immediately AFTER the table whose tokens overlap the first data row's
    content cells at Jaccard >=0.7 — the fixture
    ``transcript_typed_paraphrase_violation.md`` documents the manual Jaccard
    computation; see that fixture's header for the math.

    When ``inject_dangling_citation`` is True, appends an extra row citing
    A-999 (an A-NNN guaranteed to be absent from the transcript fixture) so
    Plan 02-03's rule-2 citation-integrity check fails.
    """
    arch_match = _ARCH_BLOCK_RE.search(transcript_text)
    rows: list[str] = []

    if arch_match:
        aid = arch_match.group(1)
        body = arch_match.group(3).strip()
        body_no_cite = re.sub(
            r"\[(?:from|derived from)\s+[^\]]+\]", "", body, flags=re.IGNORECASE
        ).strip()
        first_line = next(
            (ln.strip() for ln in body_no_cite.splitlines() if ln.strip()), ""
        )
        # Trim to ~100 chars so the cell is readable.
        statement = first_line[:120].rstrip(" ,.;:—-")

        if inject_paraphrase:
            # Tightly-coupled tokens — see fixture header for Jaccard math.
            statement_cell = "operator package remain generic"
            applies_to = "operator package"
            violation = "agent specific types dispatcher"
        else:
            statement_cell = statement or "fixture invariant statement"
            applies_to = "operator package"
            violation = "Importing agent-specific packages from operator"

        rows.append(
            f"| GI-001 | {statement_cell} | {applies_to} | {violation} | [from {aid}] |"
        )
    else:
        # No ARCH_INVARIANT — emit a sentinel-style row so the table at
        # least has a presence row. Plan 02-03 may treat this as a sentinel
        # exemption from rule 3.
        cite = primary_cite if user_ids else "[from survey/architecture.md]"
        rows.append(
            f"| — | None — fixture has no architectural invariants | — | — | {cite} |"
        )

    if inject_dangling_citation:
        # Append an extra row whose citation A-999 does NOT exist in the
        # transcript. Plan 02-03's rule 2 citation-integrity check fails this
        # with TYPED_ROW_DANGLING.
        rows.append(
            "| GI-002 | dangling-citation row content | applies | violation | [from A-999] |"
        )

    table = (
        "\n"
        "| ID | statement | applies-to | violation | citation |\n"
        "|----|-----------|------------|-----------|----------|\n"
        + "\n".join(rows)
        + "\n"
    )

    # When inject_paraphrase is True, also emit an adjacent prose paragraph
    # whose tokens overlap the row's content cells at Jaccard >=0.7. The
    # paragraph is structurally inside the same `## Global Invariants`
    # section as the table, so Plan 02-03's rule-3 will collect it as
    # adjacent prose.
    if inject_paraphrase:
        # Statement cell carries a citation [from A-001] (already in row),
        # but the prose paragraph itself needs a traceable marker so
        # check_universal_citations does not flag it. Use [from A-001].
        cite = primary_cite if user_ids else "[from survey/architecture.md]"
        prose = (
            "\n"
            "The operator package must remain generic. Agent specific types "
            f"live in the dispatcher only. {cite}\n"
        )
        table = table + prose

    return table


def _build_state_transitions_section(
    user_ids: list[str], *, sentinel: bool
) -> str:
    """Return the `## State Transitions` heading + table body."""
    cite = f"[from {user_ids[0]}]" if user_ids else "[from survey/state.md]"

    if sentinel:
        # Documented sentinel row form per CONTEXT.md.
        rows = [
            f"| — | — | — | None — this feature has no state transitions | — | "
            f"{cite} |"
        ]
    else:
        rows = [
            f"| ST-001 | RUNNING | COMPLETED | casting reaches DONE | "
            f"F4 ASSAY signs off | {cite} |"
        ]

    return (
        "## State Transitions\n"
        "\n"
        "| ID | from-state | to-state | trigger | guard | citation |\n"
        "|----|------------|----------|---------|-------|----------|\n"
        + "\n".join(rows)
        + "\n"
        "\n"
    )


def _build_contracts_section(user_ids: list[str], *, sentinel: bool) -> str:
    """Return the `## Contracts` heading + table body."""
    cite = f"[from {user_ids[0]}]" if user_ids else "[from survey/api.md]"

    if sentinel:
        rows = [
            f"| — | None — no observable contracts beyond internal helper "
            f"signatures | — | — | — | {cite} |"
        ]
    else:
        rows = [
            f"| CT-001 | Foundry-Accept-Casting | casting_id (string) | "
            f"{{accepted: bool, provenance: {{sha256, mtime}}}} | "
            f"INVALID_CASTING_ID, EVIDENCE_MISMATCH | {cite} |"
        ]

    return (
        "## Contracts\n"
        "\n"
        "| ID | surface | input | output | errors | citation |\n"
        "|----|---------|-------|--------|--------|----------|\n"
        + "\n".join(rows)
        + "\n"
        "\n"
    )


@pytest.fixture
def run_validator_subprocess(
    tmp_path: Path,
) -> Callable[..., subprocess.CompletedProcess]:
    """Invoke validate-spec.py via subprocess and return CompletedProcess.

    Usage:
        result = run_validator_subprocess(spec_path, transcript_path)
        assert result.returncode == 0

    The ``spec_path`` argument is preserved for backwards compatibility with
    Plan 01-01's test signatures, but its content is currently IGNORED — a
    synthesized spec is built per-transcript by ``_build_synthesized_spec``
    so the validator's structural checks (APPENDIX_INCOMPLETE,
    UNCITED_ANSWERS, etc.) pass uniformly across all fixture transcripts.
    The synthesized spec is written to ``tmp_path / 'synthesized-spec.md'``
    and passed to validate-spec.py in place of ``spec_path``.

    See ``_build_synthesized_spec`` docstring for the rationale (Plan 03 /
    INTV-01 deviation: the static spec-minimal.md from Plan 01-01 cannot
    pair correctly with multiple distinct transcript fixtures).
    """

    def _runner(
        spec_path: str | Path,
        transcript_path: str | Path,
    ) -> subprocess.CompletedProcess:
        transcript_text = Path(transcript_path).read_text(encoding="utf-8")
        synthesized = _build_synthesized_spec(transcript_text)
        synthesized_path = tmp_path / "synthesized-spec.md"
        synthesized_path.write_text(synthesized, encoding="utf-8")
        return subprocess.run(
            [
                "python3",
                str(VALIDATE_SPEC),
                str(synthesized_path),
                str(transcript_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    return _runner


@pytest.fixture
def run_typed_validator_subprocess(
    tmp_path: Path,
) -> Callable[..., subprocess.CompletedProcess]:
    """Phase 2 (Plan 02-01) subprocess fixture for typed-table tests.

    Loads ``transcript_fixture_name`` from ``tests/fixtures/``, synthesizes a
    spec body via ``_build_synthesized_spec(..., with_typed_tables=True, ...)``
    (or ``with_typed_tables=False`` for the legacy-v4.2.0 backwards-compat
    fixture), writes the synthesized spec to ``tmp_path``, and invokes
    validate-spec.py against the (synthesized-spec, transcript) pair.

    Usage:
        # Happy path — three populated tables.
        result = run_typed_validator_subprocess("transcript_typed_complete")
        assert result.returncode == 0

        # Negative — dangling citation A-999.
        result = run_typed_validator_subprocess(
            "transcript_typed_dangling_citation",
            inject_dangling_citation=True,
        )
        assert result.returncode == 1
        assert "TYPED_ROW_DANGLING" in result.stdout

        # Backwards-compat — no typed tables emitted at all.
        result = run_typed_validator_subprocess(
            "transcript_typed_legacy_v420",
            with_typed_tables=False,
        )
        assert result.returncode == 0  # warns but does not fail in Phase 2

    The ``builder_kwargs`` are forwarded as-is to ``_build_synthesized_spec``.
    ``with_typed_tables`` defaults to True (the typical Phase 2 path); set to
    False explicitly for the legacy-v4.2.0 fixture path.

    Phase 1's ``run_validator_subprocess`` is unchanged — Phase 2 fixtures
    that need typed-tables synthesis call THIS fixture instead.
    """

    def _runner(
        transcript_fixture_name: str,
        *,
        with_typed_tables: bool = True,
        **builder_kwargs,
    ) -> subprocess.CompletedProcess:
        # Resolve fixture path. Accept the bare stem (no .md) or the full
        # filename — Phase 2 fixtures all live under fixtures_dir.
        fixture_basename = transcript_fixture_name
        if not fixture_basename.endswith(".md"):
            fixture_basename = f"{fixture_basename}.md"
        transcript_path = FIXTURES_DIR / fixture_basename
        if not transcript_path.is_file():
            raise FileNotFoundError(
                f"Phase 2 fixture missing: {transcript_path}. "
                f"Plan 02-01 should have created it."
            )

        transcript_text = transcript_path.read_text(encoding="utf-8")
        synthesized = _build_synthesized_spec(
            transcript_text,
            with_typed_tables=with_typed_tables,
            **builder_kwargs,
        )
        synthesized_path = tmp_path / "synthesized-typed-spec.md"
        synthesized_path.write_text(synthesized, encoding="utf-8")
        return subprocess.run(
            [
                "python3",
                str(VALIDATE_SPEC),
                str(synthesized_path),
                str(transcript_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    return _runner


@pytest.fixture
def run_setup_forge(tmp_path: Path) -> Callable[..., SetupForgeResult]:
    """Invoke setup-forge.sh via subprocess and capture the assembled prompt.

    setup-forge.sh assembles the R0-R4 prompt in a mktemp PROMPT_FILE, then
    reads it into ``$INTERVIEW_PROMPT`` and ``rm``s the temp file before
    ``echo "$INTERVIEW_PROMPT"`` dumps the entire prompt content to stdout
    (see setup-forge.sh:1505-1509,1705). There is no persistent prompt-file
    path on stdout — the prompt content IS the stdout.

    For smoke testing we mirror that reality: write stdout to a per-test
    sentinel file under ``tmp_path`` and expose it as ``prompt_path``.
    Callers asserting ``result.prompt_path is not None`` confirm the script
    ran to completion; callers asserting on ``result.prompt_text`` get the
    full assembled prompt the LLM would consume.

    Usage:
        result = run_setup_forge("test-feature", "--no-survey")
        assert "PHASE R1.75" in result.prompt_text

    The function accepts variadic positional args that get passed to
    setup-forge.sh as-is (including the FEATURE_NAME positional and any flags).
    cwd is the pytest tmp_path so the FEATURE_SLUG output directory does not
    pollute the repo.
    """

    def _runner(*args: str) -> SetupForgeResult:
        cmd = ["bash", str(SETUP_FORGE), *args]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(tmp_path),
        )

        # setup-forge.sh dumps the assembled prompt content directly on stdout
        # via `echo "$INTERVIEW_PROMPT"` at the end. Persist it to a sentinel
        # file inside tmp_path so prompt_path is non-None on success and
        # prompt_text is readable for assertions. On non-zero exit, leave
        # prompt_path None (callers should check process.returncode first).
        prompt_path: Path | None = None
        prompt_text = ""
        if proc.returncode == 0 and proc.stdout:
            sentinel = tmp_path / "captured-prompt.txt"
            sentinel.write_text(proc.stdout)
            prompt_path = sentinel
            prompt_text = proc.stdout

        return SetupForgeResult(
            process=proc,
            prompt_path=prompt_path,
            prompt_text=prompt_text,
        )

    return _runner


# ---------------------------------------------------------------------------
# Phase 3 fixtures (Plan 03-01)
# ---------------------------------------------------------------------------
#
# Two new fixtures land here, append-only — none of the Phase 1/2 fixtures
# above are edited:
#
#   1. ``run_versioned_validator_subprocess`` — wraps validate-spec.py with
#      explicit ``spec_format_version`` frontmatter handling. Synthesizes a
#      spec body with the requested frontmatter (or no frontmatter for the
#      implicit-v2.0 path) and forwards Phase 2 builder kwargs via
#      ``**kwargs`` so existing typed-table negative tests can be reused
#      under Phase 3 conditions.
#
#   2. ``run_f05_decompose_with_test_roster`` — STUB ONLY in Plan 03-01.
#      Raises ``pytest.skip(...)`` so the seven Phase 3 RED stubs that
#      consume this fixture are collected but skipped. Plan 03-04 lands the
#      real F0.5 roster-enumeration logic and turns those skips into
#      RED-then-GREEN.

# Regex used to extract a leading `<!-- spec_format_version: vX.Y -->`
# comment from a transcript fixture. The conftest synthesizer uses this
# when the test does NOT pass an explicit `spec_format_version=` kwarg —
# the fixture-comment is the per-fixture default. The version capture is
# anchored to the `vN.N` shape so documentation-prose comments containing
# a placeholder ellipsis (e.g. `<!-- spec_format_version: ... -->` in
# the legacy fixture's narrative) do NOT match — only real version
# literals are extracted.
_FIXTURE_VERSION_COMMENT_RE = re.compile(
    r"<!--\s*spec_format_version:\s*(v\d+\.\d+)\s*-->"
)

# Regexes to strip [IMPLICIT_FACT:*] tags from synthesized transcripts when
# `with_implicit_fact_tags=False`. Three patterns to handle the three positional
# cases of an IMPLICIT_FACT:CATEGORY token inside an A-NNN tag bracket:
#   1. Leading/middle position with trailing comma:
#        `[IMPLICIT_FACT:DEPLOYMENT, LOCKED]`     -> `[LOCKED]`
#        `[LOCKED, IMPLICIT_FACT:RUNTIME, OTHER]` -> `[LOCKED, OTHER]`
#   2. Trailing position with preceding comma:
#        `[ARCH_INVARIANT, IMPLICIT_FACT:DEPLOYMENT]` -> `[ARCH_INVARIANT]`
#   3. Sole tag (no comma siblings) — entire bracket pair removed (with the
#      space before it) so the header doesn't keep an empty `[]`:
#        `## A-002 [IMPLICIT_FACT:DEPLOYMENT]` -> `## A-002`
# Plan 03-01's original single-pattern shape (`\[IMPLICIT_FACT:CAT\]`) only
# handled case 3 and missed combined-tag fixtures (e.g. v21_missing_implicit
# transcript fixture which uses `[ARCH_INVARIANT, IMPLICIT_FACT:DEPLOYMENT]`).
# Plan 03-03 generalises the stripper across all three positions. Horizontal
# whitespace classes ([ \t]) preserve newlines so the line structure is intact.
_IMPLICIT_FACT_STRIP_LEADING_RE = re.compile(
    r"\bIMPLICIT_FACT:[A-Z_]+[ \t]*,[ \t]*"
)
_IMPLICIT_FACT_STRIP_TRAILING_RE = re.compile(
    r"[ \t]*,[ \t]*IMPLICIT_FACT:[A-Z_]+"
)
_IMPLICIT_FACT_STRIP_SOLE_RE = re.compile(
    r"[ \t]*\[IMPLICIT_FACT:[A-Z_]+\]"
)


def _strip_implicit_fact_tags(text: str) -> str:
    """Strip every [IMPLICIT_FACT:*] token from A-NNN tag brackets."""
    text = _IMPLICIT_FACT_STRIP_LEADING_RE.sub("", text)
    text = _IMPLICIT_FACT_STRIP_TRAILING_RE.sub("", text)
    text = _IMPLICIT_FACT_STRIP_SOLE_RE.sub("", text)
    return text


@pytest.fixture
def run_versioned_validator_subprocess(
    tmp_path: Path,
) -> Callable[..., subprocess.CompletedProcess]:
    """Plan 03-01 fixture for Phase 3 (TYPE-02) versioned-spec-format tests.

    Builds a synthesized spec body via ``_build_synthesized_spec`` (Phase
    1/2 builder) and prepends a ``spec_format_version: {value}`` frontmatter
    block when ``spec_format_version`` is non-None. When ``spec_format_version``
    is None (the implicit-v2.0 path), the synthesized body is written
    verbatim — Phase 3's frontmatter parser (Plan 03-02) defaults missing
    frontmatter to v2.0.

    Note: ``_build_synthesized_spec`` already emits its OWN
    ``spec_format_version: v2.0`` frontmatter block. To avoid double-
    frontmatter (which would yield malformed YAML), this fixture rewrites
    the existing frontmatter line via a regex substitution rather than
    prepending a second YAML block.

    Usage:
        # v2.1 happy path:
        result = run_versioned_validator_subprocess(
            "transcript_versioned_modern",
            spec_format_version="v2.1",
        )
        assert result.returncode == 0

        # Unknown version (Phase 3 hard-fail):
        result = run_versioned_validator_subprocess(
            "transcript_versioned_unknown",
            spec_format_version="v9.0",
        )
        assert result.returncode != 0

        # No frontmatter (implicit v2.0):
        result = run_versioned_validator_subprocess(
            "transcript_versioned_legacy",
            spec_format_version=None,  # also: omit, default is None
        )
        assert result.returncode == 0

    Behaviour details:
      - ``transcript_name`` may be a bare stem or include the ``.md`` suffix.
      - When ``spec_format_version`` is None and the transcript has a
        ``<!-- spec_format_version: vX.Y -->`` comment at top, the comment
        value is extracted and used as the version. (The leading comment
        line is stripped from the transcript body before synthesis so the
        comment never appears in the synthesized appendix.)
      - When ``spec_format_version`` is None AND no comment is present
        (legacy fixture path), the synthesized spec is written WITHOUT any
        spec_format_version frontmatter line — the validator's frontmatter
        parser must default this to v2.0. The fixture explicitly removes
        the ``_build_synthesized_spec`` builder's default v2.0 frontmatter
        line so the implicit-default code path is exercised end-to-end.
      - ``with_typed_tables`` and other ``**kwargs`` forward to the Phase 1/2
        builder unchanged. Typical Phase 3 negative tests pair
        ``spec_format_version="v2.1"`` with ``with_typed_tables=False`` to
        exercise Plan 03-03's warn→fail upgrade.
      - ``with_implicit_fact_tags=False`` strips ``[IMPLICIT_FACT:*]`` tags
        from the synthesized transcript before validate-spec.py reads it,
        mirroring the Phase 2 ``inject_paraphrase``-style negative-test
        kwarg pattern. Used by ``test_v21_missing_implicit_hard_fails``.

    Plan 03-04 ownership: this fixture stays unchanged across Plans 03-02 /
    03-03 / 03-04. Only the validator's behaviour (validate-spec.py) shifts.
    """

    def _runner(
        transcript_name: str,
        *,
        spec_format_version: str | None = None,
        with_typed_tables: bool = True,
        with_implicit_fact_tags: bool = True,
        **kwargs,
    ) -> subprocess.CompletedProcess:
        # Resolve fixture path (accept stem or full filename).
        fixture_basename = transcript_name
        if not fixture_basename.endswith(".md"):
            fixture_basename = f"{fixture_basename}.md"
        transcript_path = FIXTURES_DIR / fixture_basename
        if not transcript_path.is_file():
            raise FileNotFoundError(
                f"Phase 3 fixture missing: {transcript_path}. "
                f"Plan 03-01 should have created it."
            )

        transcript_text = transcript_path.read_text(encoding="utf-8")

        # If caller did not pass spec_format_version, try to extract from the
        # transcript's leading comment. None remains None when no comment
        # exists (legacy fixture path).
        if spec_format_version is None:
            match = _FIXTURE_VERSION_COMMENT_RE.search(transcript_text)
            if match:
                spec_format_version = match.group(1)

        # Strip the version comment line from the transcript before synthesis
        # so it never appears in the synthesized appendix (the appendix is
        # checked verbatim against the transcript by validate-spec.py, but
        # the comment is metadata, not Q/A content). Removing it keeps the
        # synthesized appendix structurally valid.
        transcript_for_spec = _FIXTURE_VERSION_COMMENT_RE.sub(
            "", transcript_text, count=1
        ).lstrip("\n")

        # Optionally strip [IMPLICIT_FACT:*] tags so Phase 1's
        # check_implicit_facts emits IMPLICIT_FACT_SKIPPED on the resulting
        # transcript. Used by Plan 03-01 RED stub
        # test_v21_missing_implicit_hard_fails.
        if not with_implicit_fact_tags:
            transcript_for_spec = _strip_implicit_fact_tags(
                transcript_for_spec
            )

        synthesized = _build_synthesized_spec(
            transcript_for_spec,
            with_typed_tables=with_typed_tables,
            **kwargs,
        )

        # Rewrite the spec_format_version line in the builder's frontmatter
        # to match the requested version, OR remove the entire frontmatter
        # block when spec_format_version is None (implicit-v2.0 path).
        if spec_format_version is None:
            # Strip the leading YAML frontmatter block entirely so the
            # validator's frontmatter parser sees a frontmatter-less spec
            # and defaults to v2.0. This exercises Plan 03-02's implicit-
            # default code path end-to-end.
            synthesized = re.sub(
                r"\A---\n.*?\n---\n\n",
                "",
                synthesized,
                count=1,
                flags=re.DOTALL,
            )
        else:
            # Rewrite the existing spec_format_version line to the requested
            # value. The builder always emits exactly one such line at
            # column 0 inside the frontmatter block.
            synthesized = re.sub(
                r"^spec_format_version:\s*\S+",
                f"spec_format_version: {spec_format_version}",
                synthesized,
                count=1,
                flags=re.MULTILINE,
            )

        synthesized_path = tmp_path / "synthesized-versioned-spec.md"
        synthesized_path.write_text(synthesized, encoding="utf-8")

        # Also write the (possibly-tag-stripped) transcript next to the spec
        # so validate-spec.py reads matching content. The appendix-vs-
        # transcript verbatim check requires the file passed to
        # validate-spec.py to match what the synthesized spec embedded.
        transcript_for_validator_path = tmp_path / "transcript-versioned.md"
        transcript_for_validator_path.write_text(
            transcript_for_spec, encoding="utf-8"
        )

        return subprocess.run(
            [
                "python3",
                str(VALIDATE_SPEC),
                str(synthesized_path),
                str(transcript_for_validator_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    return _runner


@pytest.fixture
def run_f05_decompose_with_test_roster(
    tmp_path: Path,
) -> Callable[..., dict]:
    """Plan 03-01 fixture; Plan 03-04 implements the actual F0.5 roster logic.

    SCAFFOLD ONLY in Plan 03-01: the fixture raises ``pytest.skip(...)`` if
    invoked. This is intentional and mirrors the Phase 2 precedent
    (``test_jaccard_tokenizer_consistency`` uses ``pytest.importorskip``):
    the seven Phase 3 RED stubs that consume this fixture are collected
    cleanly but SKIP at run-time, so the Plan 03-01 baseline shows the full
    Phase 3 test surface without false-positive failures for downstream-
    wave-owned logic.

    Plan 03-04 will replace the ``pytest.skip`` body with:
      - Build a spec at ``tmp_path/spec.md`` declaring the requested
        ``spec_format_version`` (frontmatter only, no body required).
      - Invoke the F0.5 roster-enumeration harness (Plan 03-04 provides a
        thin Python harness OR a separate test helper script that performs
        the same enumeration as ``plugins/foundry/commands/start.md`` prose).
      - Read ``tmp_path/castings/manifest.json`` and return the parsed dict.

    The fixture signature is locked NOW so Plans 03-04's RED-to-GREEN
    transition is a fixture-body swap, not a fixture-signature change.

    Usage (Plan 03-04 onward):
        result = run_f05_decompose_with_test_roster(
            spec_format_version="v2.0",
            extra_agent_paths=[fixtures_dir / "agents" / "agent_phase3_test_stream.md"],
        )
        assert result["stream_skips"][0]["stream_id"] == "PHASE3-TEST-STREAM"
    """

    def _runner(
        spec_format_version: str | None,
        extra_agent_paths: list[Path] | None = None,
    ) -> dict:
        pytest.skip(
            "Plan 03-04 implements F0.5 roster logic. "
            "run_f05_decompose_with_test_roster is a Plan 03-01 scaffold "
            "stub — the seven RED stubs that consume it collect cleanly "
            "but skip at run-time until Plan 03-04 lands the harness."
        )

    return _runner
