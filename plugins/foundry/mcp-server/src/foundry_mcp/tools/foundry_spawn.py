"""Foundry teammate spawn — reads the pre-authored casting prompt file.

Architecture principle (v3.0.0): **plans are prompts.** Teammate prompts are
authored ONCE by decompose at F0.5, written to disk as
`foundry-archive/{run}/castings/casting-{id}-prompt.md`, validated at F0.9,
and frozen. The lead never drafts or modifies teammate prompts — it calls
this tool with a casting_id and passes the returned text directly to the
Agent tool.

This eliminates the "lead drafts prompt from casting" step where spec
fidelity used to silently erode via paraphrasing, scope cuts, or hedge
language. The lead is a router, not an interpreter.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from foundry_mcp.tools.foundry_state import get_run_dir


def foundry_spawn_teammate(
    casting_id: int | str,
    phase: str = "cast",
    project_root: str = ".",
) -> dict:
    """Read and return the pre-authored prompt for a casting.

    Args:
        casting_id: The id of the casting whose teammate prompt to read.
        phase: "cast" (F1) or "grind" (F3). Affects which prompt variant to
            return if both exist; otherwise identical.
        project_root: Repo root.

    Returns:
        On success:
            {
                "ok": True,
                "casting_id": N,
                "phase": "cast" | "grind",
                "prompt_path": "foundry-archive/{run}/castings/casting-N-prompt.md",
                "prompt_hash": "sha256:...",
                "prompt": "<full text of the pre-authored prompt>",
                "instructions": "Pass the `prompt` field verbatim to the Agent tool. Do NOT modify it. Do NOT prepend, append, or substitute text. Only the `prompt` content is authorized teammate context."
            }
        On failure:
            {"ok": False, "error": "...", "hint": "..."}
    """
    fdir = get_run_dir(project_root)
    if not fdir:
        return {"ok": False, "error": "No active foundry run", "hint": "Call Foundry-Init first"}
    if not fdir.exists():
        return {"ok": False, "error": "Foundry run directory not found", "hint": f"Expected {fdir}"}

    manifest_path = fdir / "castings" / "manifest.json"
    if not manifest_path.exists():
        return {"ok": False, "error": "No manifest.json", "hint": "Run F0.5 DECOMPOSE first"}

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"manifest.json parse error: {e}"}

    castings = manifest.get("castings", [])
    casting = None
    for c in castings:
        if str(c.get("id")) == str(casting_id):
            casting = c
            break

    if not casting:
        available = [c.get("id") for c in castings]
        return {
            "ok": False,
            "error": f"casting_id {casting_id} not found in manifest",
            "hint": f"Available casting ids: {available}",
        }

    # Locate the pre-authored prompt file.
    prompt_path = fdir / "castings" / f"casting-{casting_id}-prompt.md"
    if not prompt_path.exists():
        return {
            "ok": False,
            "error": f"casting-{casting_id}-prompt.md does not exist",
            "hint": (
                "Decompose must write a pre-authored teammate prompt file for every casting. "
                "Re-run F0.5 DECOMPOSE or check that the decompose step wrote the prompt files."
            ),
        }

    prompt_text = prompt_path.read_text(encoding="utf-8")

    if not prompt_text.strip():
        return {
            "ok": False,
            "error": f"casting-{casting_id}-prompt.md is empty",
            "hint": "Re-run F0.5 DECOMPOSE to regenerate the prompt file.",
        }

    # Hash the prompt for audit tracking.
    prompt_hash = "sha256:" + hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:16]

    # Log the spawn for the audit trail.
    spawn_log = fdir / "spawns.log"
    try:
        from datetime import datetime, timezone
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "casting_id": casting_id,
            "phase": phase,
            "prompt_hash": prompt_hash,
            "prompt_path": str(prompt_path.relative_to(Path(project_root)) if prompt_path.is_absolute() else prompt_path),
        }
        with spawn_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        # Logging failures must not block the spawn.
        pass

    return {
        "ok": True,
        "casting_id": casting_id,
        "phase": phase,
        "prompt_path": str(prompt_path.relative_to(Path(project_root)) if prompt_path.is_absolute() else prompt_path),
        "prompt_hash": prompt_hash,
        "prompt": prompt_text,
        "instructions": (
            "Pass the `prompt` field VERBATIM to the Agent tool as the teammate's prompt. "
            "Do NOT modify, summarize, paraphrase, or augment the text. Do NOT add your own context, "
            "hedges, or scope notes. The prompt was authored at F0.5 DECOMPOSE with the master spec "
            "as source of truth and was validated at F0.9. Modifying it reintroduces the exact drift "
            "failure mode this architecture was built to prevent."
        ),
    }
