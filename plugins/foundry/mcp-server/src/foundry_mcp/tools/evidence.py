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

import os
import re
import shutil
import signal
import subprocess
import threading
import time
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
# Volatile-redaction (Plan 04-03 — body landed).
#
# Pitfall 5 from RESEARCH.md: ordering matters. Each ``re.sub`` is applied to
# the OUTPUT of the previous substitution, so pattern N's substituted text
# can match (or de-match) pattern N+1. Tests lock the non-commutative
# contract via ``test_volatile_order_is_respected``.
# ---------------------------------------------------------------------------
def _apply_volatile_redaction(text: str, volatile_patterns: list[str]) -> str:
    """Apply each volatile pattern as ``re.sub`` in DECLARED ORDER.

    Args:
        text: source string to redact.
        volatile_patterns: ordered list of regex pattern strings. Each is
            applied via ``re.sub(pattern, VOLATILE_PLACEHOLDER, text)`` against
            the running output (NOT the original ``text``).

    Returns:
        The fully-redacted string. Empty list ⇒ ``text`` returned unchanged.

    Raises:
        ValueError prefixed with ``EVIDENCE_VOLATILE_MALFORMED`` when any
        pattern fails to compile (``re.error``). Caller translates to a
        provenance record with ``failure_token=EVIDENCE_VOLATILE_MALFORMED``.

    Pitfall 5 mitigation: iterative ``re.sub`` with declared order honored.
    Reverse-ordered patterns yield different output (test-locked).

    Placeholder-ladder discipline (test-locked in
    ``test_volatile_order_is_respected``): the substitution token used for
    each pattern is selected by inspecting the pattern itself —

      - If the pattern string CONTAINS ``<VOLATILE>`` (a "compound" rule
        that depends on a prior level-0 redaction), matches are substituted
        with ``<TIMING>`` (the next-level placeholder).
      - Otherwise (a "level-0" rule on raw text), matches are substituted
        with ``<VOLATILE>``.

    This lets authors stage redactions in two passes: first collapse raw
    timing fields into ``<VOLATILE>``, then collapse the resulting
    ``"<phrase> <VOLATILE>"`` shape into a higher-level
    ``<TIMING>`` token. Without the ladder, a compound pattern would
    re-substitute with the same ``<VOLATILE>`` and lose the level
    distinction. CONTEXT.md describes the level-0 case (``<VOLATILE>``);
    the ladder generalizes that to multi-level chains.
    """
    redacted = text
    for pat in volatile_patterns:
        # Placeholder ladder: pattern referencing <VOLATILE> is level-1+,
        # substitutes with <TIMING>; otherwise level-0 → <VOLATILE>.
        replacement = (
            "<TIMING>" if VOLATILE_PLACEHOLDER in pat else VOLATILE_PLACEHOLDER
        )
        try:
            redacted = re.sub(pat, replacement, redacted)
        except re.error as exc:
            raise ValueError(
                f"EVIDENCE_VOLATILE_MALFORMED: invalid regex {pat!r}: {exc}"
            ) from exc
    return redacted


# ---------------------------------------------------------------------------
# Subprocess re-execution with descendant cleanup (Plan 04-03).
#
# Pitfall 3 (RESEARCH.md): ``subprocess.run(timeout=N, start_new_session=True)``
# kills the IMMEDIATE child but leaves descendants running. The Popen +
# manual ``os.killpg`` path kills the entire process group on timeout.
#
# Pitfall 4 (RESEARCH.md): non-UTF-8 captured output crashes the comparator
# unless ``errors='replace'`` is paired with ``text=True`` + ``encoding``.
# U+FFFD substitutes invalid bytes deterministically.
#
# stderr is merged into stdout (CONTEXT.md "stdout+stderr-merged byte-match")
# so a single captured string compares against the committed log.
# ---------------------------------------------------------------------------
def _run_command_with_timeout(
    cmd: str,
    cwd: Path,
    timeout: int,
) -> tuple[int, str, float]:
    """Re-execute ``cmd`` in ``cwd`` with timeout enforcement.

    Args:
        cmd: shell command string (executed via ``shell=True``).
        cwd: working directory (typically the worktree path).
        timeout: wall-clock seconds before SIGTERM/SIGKILL escalation.

    Returns:
        ``(exit_code, merged_stdout_stderr, elapsed_seconds)``.
        On timeout, ``exit_code == -1`` and ``merged_stdout_stderr`` carries
        whatever the child managed to flush before being killed.

    Discipline (per CONTEXT.md + RESEARCH.md Pitfalls 3 & 4):
      - ``shell=True`` so users can write pipelines / multi-token cmds in
        the ``# evidence-cmd:`` header.
      - ``stderr=subprocess.STDOUT`` merges streams (single-string compare).
      - ``text=True, encoding='utf-8', errors='replace'`` makes binary or
        non-UTF-8 output survive comparator entry.
      - ``start_new_session=True`` puts the child in a fresh process group
        so ``os.killpg`` reaches descendants.
      - ``env=os.environ.copy()`` inherits the lead's env (CONTEXT.md).

    Timeout escalation: SIGTERM → 2s grace → SIGKILL. Wrapped in
    ``ProcessLookupError``/``OSError`` guards because the child may have
    already exited between the timeout and the killpg call (race).
    """
    started = time.monotonic()
    proc = subprocess.Popen(
        cmd,
        shell=True,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # merge stderr→stdout per CONTEXT.md
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=True,
        env=os.environ.copy(),  # inherit lead's env per CONTEXT.md
    )
    try:
        stdout, _ = proc.communicate(timeout=timeout)
        elapsed = time.monotonic() - started
        return proc.returncode, stdout or "", elapsed
    except subprocess.TimeoutExpired:
        # Pitfall 3: kill the entire process group, not just the immediate child.
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
        try:
            stdout, _ = proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
            try:
                stdout, _ = proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                stdout = ""
        elapsed = time.monotonic() - started
        return -1, stdout or "", elapsed


# ---------------------------------------------------------------------------
# Worktree management with concurrent-safety serialization (Plan 04-03).
#
# Pitfall 1 (RESEARCH.md): ``git worktree`` accumulates orphaned dirs from
# crashed prior runs. ``_prune_orphaned_worktrees`` runs once per session
# per project_root.
#
# Pitfall 2 (RESEARCH.md): concurrent ``git worktree add`` invocations on
# the same repo race on ``.git/config.lock``. ``_WORKTREE_LOCK`` serializes
# them at module level (within-process); cross-process serialization
# delegates to git's own locking.
# ---------------------------------------------------------------------------
_WORKTREE_LOCK = threading.Lock()
_PRUNE_DONE_FOR: set[str] = set()  # project_root strings already pruned this session


def _setup_worktree(
    project_root: Path,
    casting_id: int | str,
    commit_hash: str,
    run_dir: Path,
) -> Path:
    """Create a detached worktree at ``commit_hash`` under ``run_dir``.

    Args:
        project_root: repo containing ``.git/``.
        casting_id: int or str; embedded in the worktree dir name.
        commit_hash: full SHA (or any rev-parseable ref) to check out.
        run_dir: parent directory; worktree lives at
            ``run_dir / 'worktrees' / f'casting-{id}'``.

    Returns:
        Absolute path to the new worktree.

    Raises:
        RuntimeError when ``git worktree add`` fails (translated by
        ``verify_evidence`` to ``EVIDENCE_COMMIT_MISSING``).

    Idempotency: a stale worktree dir from a prior crash is torn down before
    re-creation. The ``_WORKTREE_LOCK`` serializes within-process so two
    threads don't race on ``.git/config.lock`` (Pitfall 2).
    """
    worktree_path = run_dir / "worktrees" / f"casting-{casting_id}"
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    if worktree_path.exists():
        _teardown_worktree(project_root, worktree_path)
    with _WORKTREE_LOCK:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(project_root),
                "worktree",
                "add",
                "--detach",
                str(worktree_path),
                commit_hash,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    if result.returncode != 0:
        raise RuntimeError(
            f"git worktree add failed (commit {commit_hash[:12]}): "
            f"{result.stderr.strip()}"
        )
    return worktree_path


def _teardown_worktree(project_root: Path, worktree_path: Path) -> None:
    """Idempotent teardown: ``git worktree remove --force`` → ``shutil.rmtree``
    fallback → ``git worktree prune``.

    Safe to call on a non-existent worktree (Pitfall 1: prior-crash teardowns
    must not crash the current run). ``capture_output=True`` swallows the
    inevitable "not a working tree" stderr on the prune path.
    """
    subprocess.run(
        [
            "git",
            "-C",
            str(project_root),
            "worktree",
            "remove",
            "--force",
            str(worktree_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if worktree_path.exists():
        shutil.rmtree(worktree_path, ignore_errors=True)
    subprocess.run(
        ["git", "-C", str(project_root), "worktree", "prune"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )


def _prune_orphaned_worktrees(project_root: Path) -> None:
    """Run ``git worktree prune`` once per session per ``project_root``.

    Pitfall 1: orphan worktrees from prior crashes stay registered in
    ``.git/worktrees/`` until pruned. The module-level ``_PRUNE_DONE_FOR``
    guard avoids re-pruning on every ``verify_evidence`` call.
    """
    key = str(project_root.resolve()) if project_root.exists() else str(project_root)
    if key in _PRUNE_DONE_FOR:
        return
    subprocess.run(
        ["git", "-C", str(project_root), "worktree", "prune"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    _PRUNE_DONE_FOR.add(key)


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
