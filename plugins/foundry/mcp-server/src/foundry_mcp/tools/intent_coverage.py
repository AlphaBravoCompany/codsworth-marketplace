"""Phase 8 / INTENT-01 — Foundry-Intent-Coverage MCP tool.

Thin subprocess wrapper around plugins/foundry/scripts/validate-intent-coverage.py.
Returns structured result with action='proceed_to_validate' on pass,
action='redecompose' on any DROPPED verdict, action='rerun_intent_carrier'
when intent-coverage.json is missing.

F0.7 gate semantics:
  - PASS (zero DROPPED): stamps .f07-intent-clean marker; orchestrator
    transitions to F0.9 VALIDATE.
  - FAIL (any DROPPED): returns redecompose action + dropped_answers list
    + redecompose_hints; orchestrator routes lead BACK to F0.5 DECOMPOSE
    with the missing A-NNN list as guidance. NEVER amends casting prompts
    in place (REQUIREMENTS.md Out of Scope).

Locked decisions (per 08-RESEARCH.md Open Questions 2 + 3):
  - On pass: stamp .f07-intent-clean marker file in run dir.
  - On fail: structured payload with action / dropped_answers /
    redecompose_hints / hint / validator_stdout / validator_exit.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from foundry_mcp.tools.foundry_state import get_run_dir

# Path resolution: from plugins/foundry/mcp-server/src/foundry_mcp/tools/intent_coverage.py
#   parents[0] = tools/
#   parents[1] = foundry_mcp/
#   parents[2] = src/
#   parents[3] = mcp-server/
#   parents[4] = foundry/
# So parents[4] / "scripts" / "validate-intent-coverage.py" resolves to
# plugins/foundry/scripts/validate-intent-coverage.py — verified manually
# against the test_intent_coverage.py REPO_ROOT discipline (tests/ is at
# parents[1]=mcp-server, so REPO_ROOT=parents[4]=repo-root in that file).
VALIDATOR_SCRIPT = (
    Path(__file__).resolve().parents[4]
    / "scripts"
    / "validate-intent-coverage.py"
)


def foundry_intent_coverage(project_root: str = ".") -> dict:
    """F0.7 INTENT-CARRIER gate — validate intent-coverage.json.

    Returns one of:
      {passed: True, action: 'proceed_to_validate', propagated_count: int,
       paraphrased_answers: [...], dropped_answers: [], matrix_path: str}
      OR
      {passed: False, action: 'redecompose', dropped_answers: [...],
       redecompose_hints: [{answer_id, suggested_casting, citation_chain}],
       hint: str, validator_stdout: str, validator_exit: int}
      OR
      {passed: False, action: 'rerun_intent_carrier', reason: str}
    """
    fdir = get_run_dir(project_root)
    if not fdir:
        return {"passed": False, "reason": "No active foundry run"}

    coverage_path = fdir / "intent-coverage.json"
    spec_path = fdir / "spec.md"
    if not coverage_path.exists():
        return {
            "passed": False,
            "action": "rerun_intent_carrier",
            "reason": (
                "intent-coverage.json missing — run intent-carrier agent first"
            ),
        }

    cmd = ["python", str(VALIDATOR_SCRIPT), str(coverage_path)]
    if spec_path.exists():
        cmd += ["--spec", str(spec_path)]
    # tool-call-log is advisory — passed only when the orchestrator has
    # captured an agent tool-call log for this run (08-RESEARCH.md Open
    # Question 5; advisory shape locked per Phase 7 precedent).

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    try:
        coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "passed": False,
            "action": "rerun_intent_carrier",
            "reason": "intent-coverage.json malformed — agent must re-emit",
            "validator_stdout": result.stdout,
            "validator_exit": result.returncode,
        }

    matrix = coverage.get("matrix", [])
    dropped = sorted(
        {c["answer_id"] for c in matrix if c.get("verdict") == "DROPPED"}
    )
    paraphrased = sorted(
        {c["answer_id"] for c in matrix if c.get("verdict") == "PARAPHRASED"}
    )
    propagated_count = sum(
        1 for c in matrix if c.get("verdict") == "PROPAGATED"
    )

    if result.returncode == 0 and not dropped:
        # Locked decision (Open Question 2): stamp marker file on pass.
        # Orchestrator's F0.9 sub-check 7m reads this marker to confirm
        # F0.7 actually ran (anti-skip discipline).
        (fdir / ".f07-intent-clean").write_text("ok\n", encoding="utf-8")
        return {
            "passed": True,
            "action": "proceed_to_validate",
            "propagated_count": propagated_count,
            "paraphrased_answers": paraphrased,
            "dropped_answers": [],
            "matrix_path": str(coverage_path),
        }

    # Build redecompose_hints: per dropped answer_id, name the first
    # casting_id with a DROPPED cell + the citation_chain from the matrix.
    # Heuristic only — author can refine; the structural guarantee is
    # that every dropped answer_id surfaces with at least one suggested
    # casting target.
    redecompose_hints = []
    for ans in dropped:
        first_drop_cell = next(
            (
                c
                for c in matrix
                if c.get("verdict") == "DROPPED"
                and c.get("answer_id") == ans
            ),
            None,
        )
        redecompose_hints.append(
            {
                "answer_id": ans,
                "suggested_casting": (
                    first_drop_cell.get("casting_id")
                    if first_drop_cell
                    else None
                ),
                "citation_chain": (
                    first_drop_cell.get("citation_chain", [ans])
                    if first_drop_cell
                    else [ans]
                ),
            }
        )

    return {
        "passed": False,
        "action": "redecompose",
        "dropped_answers": dropped,
        "redecompose_hints": redecompose_hints,
        "validator_stdout": result.stdout,
        "validator_exit": result.returncode,
        "hint": (
            "F0.5 DECOMPOSE must re-run with these A-NNN entries as "
            "additional citation anchors. Do NOT amend casting prompts "
            "in place — re-run F0.5 from spec.md."
        ),
    }
