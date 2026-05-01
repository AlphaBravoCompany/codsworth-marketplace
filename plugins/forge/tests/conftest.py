"""Pytest fixtures for plugins/forge tests.

Install pytest in the development environment with:

    pip install 'pytest>=7.0'

This file exposes three reusable fixtures:

- ``fixtures_dir``: session-scoped path to ``tests/fixtures/``
- ``load_fixture``: function returning the text content of a fixture file
- ``run_validator_subprocess``: function invoking ``validate-spec.py`` via subprocess
- ``run_setup_forge``: function invoking ``setup-forge.sh`` via subprocess and
  returning the captured ``CompletedProcess`` along with the resolved prompt
  file path (which contains the assembled R0-R4 instructions setup-forge writes
  before the interactive interview begins).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest


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


@pytest.fixture
def run_validator_subprocess() -> Callable[..., subprocess.CompletedProcess]:
    """Invoke validate-spec.py via subprocess and return CompletedProcess.

    Usage:
        result = run_validator_subprocess(spec_path, transcript_path)
        assert result.returncode == 0
    """

    def _runner(
        spec_path: str | Path,
        transcript_path: str | Path,
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                "python3",
                str(VALIDATE_SPEC),
                str(spec_path),
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
