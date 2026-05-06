"""Phase 4 / EVID-01 — server-side evidence re-execution.

Re-runs each cited evidence command in a ``git worktree``-isolated checkout at
the casting's commit hash, redacts declared volatile fields, and compares
byte-for-byte against the committed log. Mismatches, non-zero exits, timeouts,
missing commands, or stub-pattern hits all reject with closed-vocabulary
failure tokens.

Plan 04-02: skeleton (constants + header parser + verify_evidence stub).
Plan 04-03: worktree/subprocess/redaction/comparator/stub-library bodies.
Plan 04-04: foundry_accept_casting integration + v2.0 stream-skip routing.

CONTEXT.md decisions locked. RESEARCH.md patterns followed beat-for-beat.

Closed vocabulary: every public failure path emits exactly one member of
``KNOWN_EVIDENCE_FAILURE_TOKENS``. Mirrors Phase 1
``VALID_IMPLICIT_FACT_CATEGORIES``, Phase 2 ``TYPED_SECTION_HEADINGS``, Phase 3
``KNOWN_SPEC_FORMAT_VERSIONS``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Closed-vocabulary failure-token allowlist (Phase 1/2/3 discipline mirror).
#
# Any new token = code-edit forced; ``test_failure_tokens_are_in_allowlist``
# enforces tuple-membership at CI time. Order intentional and documented in
# CONTEXT.md.
# ---------------------------------------------------------------------------
KNOWN_EVIDENCE_FAILURE_TOKENS: tuple[str, ...] = (
    "EVIDENCE_COMMAND_MISSING",
    "EVIDENCE_TIMEOUT",
    "EVIDENCE_EXIT_NONZERO",
    "EVIDENCE_OUTPUT_MISMATCH",
    "EVIDENCE_STUB_DETECTED",
    "EVIDENCE_VOLATILE_MALFORMED",
    "EVIDENCE_COMMIT_MISSING",
    "EVIDENCE_NETWORK_VIOLATION",  # reserved in v1; never fires; activated by future per-evidence network-deny opt-in
)

# Sanity-bounded timeout discipline. Default fires when an evidence file omits
# ``# evidence-timeout:``; ceiling caps deliberately-long sleeps that would
# stall the gate. CONTEXT.md Claude's Discretion #7 → 1800s recommended.
EVIDENCE_TIMEOUT_DEFAULT_SECONDS: int = 120
EVIDENCE_TIMEOUT_CEILING_SECONDS: int = 1800

# Stub-pattern threshold (Plan 04-03 territory; constant declared here so
# Plan 04-02 stubs can reference it deterministically).
EVIDENCE_STUB_MIN_BYTES: int = 128

# v2.0 backwards-compat gate — Plan 04-04 reads spec_format_version from
# spec.md frontmatter and routes <(2,1) specs through manifest.stream_skips.
MIN_SPEC_FORMAT_VERSION_FOR_EVID_01: tuple[int, int] = (2, 1)

# Volatile-redaction placeholder. Public so test code + Plan 04-03 comparator
# share the same literal. NOT one of the failure tokens — substituted into
# captured/log text during the redaction pipeline.
VOLATILE_PLACEHOLDER: str = "<VOLATILE>"

# Phase 5 grep contract: Phase 4 owns these directives only. Phase 5's
# ``# evidence-for:`` joins this set without parser edits — the parser
# silently ignores unknown directives so Phase 5 can introduce its directive
# at activation time (mirrors Phase 1 ``[IMPLICIT_FACT:CATEGORY]`` precedent —
# introduced by the same phase that owns it).
_KNOWN_HEADER_DIRECTIVES: frozenset[str] = frozenset({"cmd", "volatile", "timeout"})


# ---------------------------------------------------------------------------
# Header parser (Plan 04-02 territory).
#
# Header block extends from file start through the last consecutive comment-
# or-blank line; first non-comment, non-blank line ends the block. Parser
# accepts ``# evidence-cmd:`` (single, mandatory at caller-translation level —
# parser returns None, caller emits EVIDENCE_COMMAND_MISSING),
# ``# evidence-volatile:`` (zero or more, list-valued in DECLARED ORDER per
# Pitfall 5 from RESEARCH.md), ``# evidence-timeout:`` (optional integer in
# (0, EVIDENCE_TIMEOUT_CEILING_SECONDS]).
#
# Unknown directives (e.g., Phase 5's ``# evidence-for:``) are silently
# ignored so Phase 5's introduction lands without parser edits — Phase 5
# grep contract from CONTEXT.md.
# ---------------------------------------------------------------------------
_EVIDENCE_HEADER_LINE_RE = re.compile(
    r"^\s*#\s*evidence-([a-z][a-z0-9-]*)\s*:\s*(.+?)\s*$",
    re.MULTILINE,
)
_EVIDENCE_HEADER_BLOCK_RE = re.compile(r"\A(?:#[^\n]*\n|[ \t]*\n)+")


def _parse_evidence_header(text: str) -> dict[str, Any]:
    """Parse evidence file header (leading comment block).

    Args:
        text: full evidence-file contents (header block + body).

    Returns:
        ``{'cmd': str | None, 'volatile': list[str], 'timeout': int | None}``.

    Raises:
        ValueError prefixed with EVIDENCE_VOLATILE_MALFORMED when:
          - ``# evidence-timeout:`` value is not an integer
          - ``# evidence-timeout:`` integer is <= 0 or
            > ``EVIDENCE_TIMEOUT_CEILING_SECONDS``

    Caller translates ``cmd is None`` → ``EVIDENCE_COMMAND_MISSING``. Volatile
    patterns are returned as raw strings (NOT pre-compiled);
    ``_apply_volatile_redaction`` (Plan 04-03) compiles them at application
    time and raises ``EVIDENCE_VOLATILE_MALFORMED`` on ``re.error``. Plan
    04-02 SUMMARY documents this application-time-validation choice.

    Multiple ``# evidence-cmd:`` lines: first wins; subsequent ignored. Plan
    04-04 may upgrade to a hard-fail if abuse surfaces.

    Phase 5 grep contract: unknown ``# evidence-*:`` directives are silently
    ignored at this parser level. Phase 5 owns the parsing of its own
    directives (e.g. ``# evidence-for:``) at the foundry_accept_casting layer.

    Timeout out-of-range collapses to EVIDENCE_VOLATILE_MALFORMED rather than
    introducing a 9th token: closed-vocabulary discipline preserves the
    8-token allowlist locked in CONTEXT.md (Plan 04-02 SUMMARY decision).
    """
    out: dict[str, Any] = {"cmd": None, "volatile": [], "timeout": None}
    block_match = _EVIDENCE_HEADER_BLOCK_RE.match(text)
    block = block_match.group(0) if block_match else ""
    for m in _EVIDENCE_HEADER_LINE_RE.finditer(block):
        directive, raw_val = m.group(1), m.group(2).strip()
        if directive not in _KNOWN_HEADER_DIRECTIVES:
            continue  # Phase 5 grep contract — ignore unknown
        if directive == "cmd":
            if out["cmd"] is not None:
                continue  # first wins; subsequent silently ignored
            out["cmd"] = raw_val
        elif directive == "volatile":
            out["volatile"].append(raw_val)
        elif directive == "timeout":
            try:
                parsed = int(raw_val)
            except ValueError as exc:
                raise ValueError(
                    f"EVIDENCE_VOLATILE_MALFORMED: timeout {raw_val!r} "
                    f"is not an integer"
                ) from exc
            if parsed <= 0 or parsed > EVIDENCE_TIMEOUT_CEILING_SECONDS:
                raise ValueError(
                    f"EVIDENCE_VOLATILE_MALFORMED: timeout {parsed} "
                    f"out of range (0, {EVIDENCE_TIMEOUT_CEILING_SECONDS}]"
                )
            out["timeout"] = parsed
    return out


# ---------------------------------------------------------------------------
# Volatile-redaction (Plan 04-03 territory — Plan 04-02 ships function STUB
# so Plan 04-01 stubs can import the symbol; body lands in Plan 04-03).
# ---------------------------------------------------------------------------
def _apply_volatile_redaction(text: str, volatile_patterns: list[str]) -> str:
    """Apply each volatile pattern as ``re.sub`` in DECLARED ORDER.

    Plan 04-02: NotImplementedError stub.
    Plan 04-03: real body using ``re.sub`` iteratively; raises ValueError
    prefixed with ``EVIDENCE_VOLATILE_MALFORMED`` on invalid regex
    (``re.error``).

    Pitfall 5 from RESEARCH.md: ordering matters — pattern N's substitution
    output may match (or de-match) pattern N+1.
    ``test_volatile_order_is_respected`` locks the contract.
    """
    raise NotImplementedError(
        "_apply_volatile_redaction body lands in Plan 04-03"
    )


# ---------------------------------------------------------------------------
# Top-level entry point (Plan 04-02 STUB; Plan 04-03 body; Plan 04-04 wired
# into foundry_accept_casting).
# ---------------------------------------------------------------------------
def verify_evidence(
    casting_id: int | str,
    project_root: Path,
    casting_commit: str,
    *,
    spec_path: Path | None = None,
) -> dict[str, Any]:
    """Top-level Phase 4 evidence verification entry point.

    Plan 04-02 (now): NotImplementedError stub. The signature is locked so
    ``foundry_accept_casting`` (Plan 04-04) can import and call without
    import errors during incremental wiring.

    Plan 04-03 (next wave): worktree + subprocess + redaction + comparator
    + stub-pattern library bodies. Returns the v2.1+ verdict + provenance.

    Plan 04-04 (final wave): wire into ``foundry_accept_casting`` AFTER
    req-ID-citation check, BEFORE scope-flag check. v2.0 spec routing
    through ``manifest.stream_skips`` (using
    ``MIN_SPEC_FORMAT_VERSION_FOR_EVID_01`` gate).

    Args:
        casting_id: casting identifier (int or str — manifest stores as str).
        project_root: repo root containing ``.git`` and
            ``castings/manifest.json``.
        casting_commit: full SHA of the casting's commit (for
            ``git worktree add``).
        spec_path: optional explicit spec.md path; defaults to
            ``project_root / 'specs' / 'spec.md'`` (per Foundry layout).

    Returns:
        ``{
            'verdict': 'accepted' | 'rejected' | 'skipped',
            'failure_token': str | None,  # member of KNOWN_EVIDENCE_FAILURE_TOKENS
            'failure_detail': str | None,
            'provenance_records': list[dict],  # one per evidence file
            'manifest_updates': dict,  # stream_skips additions, etc.
        }``
    """
    raise NotImplementedError(
        "verify_evidence body lands in Plan 04-03 (logic) "
        "+ Plan 04-04 (foundry_accept_casting integration)"
    )
