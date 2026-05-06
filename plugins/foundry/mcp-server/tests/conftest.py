"""conftest for foundry-mcp-server tests (Phase 4 / EVID-01).

Mirrors plugins/forge/tests/conftest.py:90-114 helper-fixture shape verbatim.
PLUGIN_ROOT resolves to plugins/foundry/mcp-server/ (parent of this conftest).

Three fixtures:

- ``fixtures_dir``: session-scoped path to ``tests/fixtures/``
- ``load_fixture``: function returning the text content of a fixture file
- ``run_accept_casting_with_evidence``: SKIP-stub harness whose signature is
  locked in Plan 04-01; Plan 04-04 swaps in the real body via fixture-body
  replacement (no signature change). Mirrors Plan 03-01's
  ``run_f05_decompose_with_test_roster`` precedent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest


# ``conftest.py`` lives at ``plugins/foundry/mcp-server/tests/conftest.py`` so
# the MCP-server plugin root is the parent of the tests directory.
PLUGIN_ROOT = Path(__file__).resolve().parent.parent  # plugins/foundry/mcp-server/
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


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
                f"fixture missing: {target} — "
                f"Wave 0 plan (04-01) didn't create it. "
                f"Re-run plan 04-01 (Wave 0 scaffolding) to regenerate fixtures."
            )
        return target.read_text(encoding="utf-8")

    return _loader


@pytest.fixture
def run_accept_casting_with_evidence():
    """STUB — Plan 04-04 lands the real harness via fixture-body swap.

    Signature: caller passes a fixture-evidence-file name (str), an optional
    ``casting_commit`` (str | None — when None, harness synthesizes one),
    optional ``spec_format_version`` (str — defaults to 'v2.1'), optional
    kwargs forwarded to ``foundry_accept_casting``. Returns dict with shape::

        {
            "verdict": str,
            "failure_token": str | None,
            "provenance": dict | None,
            "manifest": dict,
            "stdout": str,
            "stderr": str,
        }

    Body raises ``pytest.skip`` in Plan 04-01 so Plan 04-02/03/04-territory
    tests SKIP rather than ERROR. Plan 04-04 replaces the body with a tiny
    git-repo synthesizer that:

      1. ``mkdtemp()`` a project_root with a ``.git/`` initialized
      2. writes ``spec.md`` with the requested ``spec_format_version`` frontmatter
      3. copies the fixture evidence file in as ``evidence/casting-N-<name>.log``
      4. commits everything (creates the casting_commit)
      5. invokes ``foundry_accept_casting`` via direct call (not subprocess)
      6. returns the verdict + manifest + provenance

    Mirrors Plan 03-01's ``run_f05_decompose_with_test_roster`` SKIP-stub
    precedent: signature locked here so downstream plans land the real body
    without touching test call sites.
    """

    def _run(
        evidence_fixture: str,
        *,
        casting_commit: str | None = None,
        spec_format_version: str = "v2.1",
        **kwargs,
    ):
        pytest.skip(
            "run_accept_casting_with_evidence body lands in Plan 04-04"
        )

    return _run
