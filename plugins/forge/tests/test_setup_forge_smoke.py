"""Smoke tests for plugins/forge/scripts/setup-forge.sh — R1.75 emission.

Wave 0 (Plan 01-01) baseline: both tests in this file MUST be RED initially.
The setup-forge.sh changes from Plan 02 turn them green.

Each test invokes setup-forge.sh via subprocess (real script, no mocks) and
asserts content of the assembled prompt file.
"""

from __future__ import annotations


# -----------------------------------------------------------------------------
# Test 1: R1.75 IMPLICIT-FACT phase is emitted in the prompt
# -----------------------------------------------------------------------------
def test_implicit_fact_phase_emitted(run_setup_forge):
    result = run_setup_forge("test-feature", "--no-survey")

    # The prompt file must exist and contain the new R1.75 phase content.
    assert result.prompt_path is not None, (
        "Expected setup-forge.sh to emit a prompt file path on stdout; "
        f"stdout:\n{result.process.stdout}\nstderr:\n{result.process.stderr}"
    )
    prompt = result.prompt_text

    assert "PHASE R1.75" in prompt, (
        f"Expected 'PHASE R1.75' in prompt; got prompt of length {len(prompt)}"
    )
    # Case-insensitive check for IMPLICIT-FACT (could be "IMPLICIT-FACT",
    # "IMPLICIT_FACT", or "Implicit Fact" depending on prose).
    lowered = prompt.lower()
    assert "implicit-fact" in lowered or "implicit_fact" in lowered, (
        "Expected an 'IMPLICIT-FACT' (or IMPLICIT_FACT) reference in prompt"
    )
    assert "gap-list" in lowered, (
        "Expected 'gap-list' reference in prompt (scout-then-ask procedure)"
    )


# -----------------------------------------------------------------------------
# Test 2: Closed vocabulary (six categories) appears in the prompt
# -----------------------------------------------------------------------------
def test_closed_vocab_in_prompt(run_setup_forge):
    result = run_setup_forge("test-feature", "--no-survey")

    assert result.prompt_path is not None, (
        "Expected setup-forge.sh to emit a prompt file; "
        f"stdout:\n{result.process.stdout}\nstderr:\n{result.process.stderr}"
    )
    prompt = result.prompt_text

    # All six closed-vocabulary categories must appear (OTHER is the escape
    # hatch and is NOT required by this assertion — only the core six).
    assert "DEPLOYMENT" in prompt, "Expected 'DEPLOYMENT' category in prompt"
    assert "SCALE" in prompt, "Expected 'SCALE' category in prompt"
    assert "RUNTIME" in prompt, "Expected 'RUNTIME' category in prompt"
    assert "FRAMEWORK_VERSION" in prompt, (
        "Expected 'FRAMEWORK_VERSION' category in prompt"
    )
    assert "SECURITY" in prompt, "Expected 'SECURITY' category in prompt"
    assert "NETWORK" in prompt, "Expected 'NETWORK' category in prompt"
