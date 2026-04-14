"""Foundry casting validation — 6-dimension quality gate before CAST phase.

Validates that castings will deliver the spec before any building starts.
A 5-minute validation saves hours of GRIND cycles.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from foundry_mcp.tools.foundry_state import get_run_dir


def foundry_validate_castings(
    project_root: str = ".",
) -> dict:
    """Validate castings against the spec across 6 dimensions.

    Returns:
        {
            "passed": bool,
            "dimensions": {
                "requirement_coverage": {"ok": bool, "issues": [...]},
                "casting_completeness": {"ok": bool, "issues": [...]},
                "dependency_correctness": {"ok": bool, "issues": [...]},
                "key_links_planned": {"ok": bool, "issues": [...]},
                "scope_sanity": {"ok": bool, "issues": [...]},
                "research_integration": {"ok": bool, "issues": [...]},
            },
            "issues": [...],
            "revision_hints": [...],
        }
    """
    fdir = get_run_dir(project_root)
    if not fdir:
        return {"passed": False, "error": "No active foundry run"}

    manifest_path = fdir / "castings" / "manifest.json"
    if not manifest_path.exists():
        return {"passed": False, "error": "No manifest.json found"}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    castings = manifest.get("castings", [])

    if not castings:
        return {"passed": False, "error": "No castings in manifest"}

    # Load spec to extract requirements
    spec_path = fdir / "spec.md"
    state = json.loads((fdir / "state.json").read_text(encoding="utf-8")) if (fdir / "state.json").exists() else {}
    if not spec_path.exists():
        sp = state.get("spec_path", "")
        if sp:
            candidate = Path(project_root) / sp
            if candidate.exists():
                spec_path = candidate

    spec_text = spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""
    spec_req_ids = set(re.findall(r"\b(?:US|FR|NFR|AC|VC|IR|TR)-\d+(?:\.\d+)?\b", spec_text))

    # Check for research artifacts
    research_dir = fdir / "research"
    has_research = research_dir.exists() and any(research_dir.iterdir()) if research_dir.exists() else False

    issues: list[dict] = []
    revision_hints: list[str] = []
    dimensions: dict[str, dict] = {}

    # ── Dimension 1: Requirement Coverage ──
    covered_reqs: set[str] = set()
    for c in castings:
        spec_text_field = c.get("spec_text", "")
        casting_reqs = set(re.findall(r"\b(?:US|FR|NFR|AC|VC|IR|TR)-\d+(?:\.\d+)?\b", spec_text_field))
        covered_reqs.update(casting_reqs)
        # Also check observable truths text
        for truth in c.get("observable_truths", []):
            truth_reqs = set(re.findall(r"\b(?:US|FR|NFR|AC|VC|IR|TR)-\d+(?:\.\d+)?\b", truth))
            covered_reqs.update(truth_reqs)

    uncovered = spec_req_ids - covered_reqs
    dim1_ok = len(uncovered) == 0
    dim1_issues = []
    if uncovered:
        dim1_issues.append({"type": "uncovered_requirements", "ids": sorted(uncovered)})
        issues.append({"dimension": "requirement_coverage", "severity": "error",
                       "message": f"{len(uncovered)} requirements not in any casting: {', '.join(sorted(uncovered))}"})
        revision_hints.append(f"Add uncovered requirements to appropriate castings: {', '.join(sorted(uncovered))}")
    dimensions["requirement_coverage"] = {"ok": dim1_ok, "issues": dim1_issues,
                                          "covered": len(covered_reqs), "total": len(spec_req_ids)}

    # ── Dimension 2: Casting Completeness ──
    dim2_issues = []
    for c in castings:
        cid = c.get("id", "?")
        title = c.get("title", "Untitled")

        # Check observable truths
        truths = c.get("observable_truths", [])
        if len(truths) < 3:
            dim2_issues.append({"casting": cid, "issue": f"Only {len(truths)} observable truths (min 3)", "title": title})
            revision_hints.append(f"Casting #{cid} '{title}': add more observable truths (currently {len(truths)}, need 3+)")

        # Check must_haves if present
        must_haves = c.get("must_haves", {})
        if must_haves:
            mh_truths = must_haves.get("truths", [])
            mh_artifacts = must_haves.get("artifacts", [])
            mh_links = must_haves.get("key_links", [])
            if len(mh_truths) < 1:
                dim2_issues.append({"casting": cid, "issue": "must_haves.truths is empty", "title": title})
            if len(mh_artifacts) < 1:
                dim2_issues.append({"casting": cid, "issue": "must_haves.artifacts is empty", "title": title})
            if len(mh_links) < 1:
                dim2_issues.append({"casting": cid, "issue": "must_haves.key_links is empty", "title": title})

    dim2_ok = len(dim2_issues) == 0
    if dim2_issues:
        issues.append({"dimension": "casting_completeness", "severity": "warning",
                       "message": f"{len(dim2_issues)} completeness issues found"})
    dimensions["casting_completeness"] = {"ok": dim2_ok, "issues": dim2_issues}

    # ── Dimension 3: Dependency Correctness ──
    dim3_issues = []
    file_to_casting: dict[str, list] = {}
    for c in castings:
        cid = c.get("id", "?")
        for f in c.get("key_files", []):
            file_to_casting.setdefault(f, []).append(cid)

    overlaps = {f: cids for f, cids in file_to_casting.items() if len(cids) > 1}
    if overlaps:
        for f, cids in overlaps.items():
            dim3_issues.append({"file": f, "castings": cids, "issue": "File claimed by multiple castings"})
            revision_hints.append(f"File '{f}' is in castings {cids} — move to one casting or split")
        issues.append({"dimension": "dependency_correctness", "severity": "error",
                       "message": f"{len(overlaps)} file overlaps between castings"})

    dim3_ok = len(dim3_issues) == 0
    dimensions["dependency_correctness"] = {"ok": dim3_ok, "issues": dim3_issues}

    # ── Dimension 4: Key Links Planned ──
    dim4_issues = []
    all_artifacts: set[str] = set()
    all_link_targets: set[str] = set()
    for c in castings:
        must_haves = c.get("must_haves", {})
        for art in must_haves.get("artifacts", []):
            all_artifacts.add(art.get("path", ""))
        for link in must_haves.get("key_links", []):
            all_link_targets.add(link.get("from", ""))
            all_link_targets.add(link.get("to", ""))

    # Check if any casting has artifacts but no key_links (isolated)
    for c in castings:
        cid = c.get("id", "?")
        title = c.get("title", "Untitled")
        must_haves = c.get("must_haves", {})
        artifacts = must_haves.get("artifacts", [])
        links = must_haves.get("key_links", [])
        if len(artifacts) >= 2 and len(links) == 0:
            dim4_issues.append({"casting": cid, "title": title,
                               "issue": f"Has {len(artifacts)} artifacts but no key_links — isolated"})
            revision_hints.append(f"Casting #{cid} '{title}': add key_links showing how artifacts connect")

    dim4_ok = len(dim4_issues) == 0
    dimensions["key_links_planned"] = {"ok": dim4_ok, "issues": dim4_issues}

    # ── Dimension 5: Scope Sanity ──
    dim5_issues = []
    for c in castings:
        cid = c.get("id", "?")
        title = c.get("title", "Untitled")
        kf = len(c.get("key_files", []))
        if kf > 8:
            dim5_issues.append({"casting": cid, "title": title, "key_files": kf,
                               "issue": f"Too many key_files ({kf} > 8)"})
            revision_hints.append(f"Casting #{cid} '{title}': split into smaller castings (currently {kf} files)")

        # Check observable truths are user-facing
        truths = c.get("observable_truths", [])
        impl_detail_patterns = [
            r"import\b", r"export\b", r"function\b", r"class\b",
            r"instanceof", r"typeof", r"\.ts\b", r"\.js\b",
        ]
        non_user_facing = []
        for truth in truths:
            for pattern in impl_detail_patterns:
                if re.search(pattern, truth, re.IGNORECASE):
                    non_user_facing.append(truth)
                    break
        if non_user_facing:
            dim5_issues.append({"casting": cid, "title": title,
                               "issue": f"{len(non_user_facing)} truths look like implementation details, not user-facing behaviors",
                               "examples": non_user_facing[:3]})

    dim5_ok = len(dim5_issues) == 0
    dimensions["scope_sanity"] = {"ok": dim5_ok, "issues": dim5_issues}

    # ── Dimension 6: Research Integration ──
    dim6_issues = []
    if has_research:
        castings_with_research = sum(1 for c in castings if c.get("research_context"))
        if castings_with_research == 0:
            dim6_issues.append({"issue": "Research artifacts exist but no casting references them"})
            revision_hints.append("Research was conducted but no casting has research_context — link relevant findings")
            issues.append({"dimension": "research_integration", "severity": "warning",
                          "message": "Research exists but no casting references it"})

    dim6_ok = len(dim6_issues) == 0
    dimensions["research_integration"] = {"ok": dim6_ok, "issues": dim6_issues}

    # ── Dimension 7: Prompt Fidelity (v3.0.0) ──
    #
    # Every casting must have a pre-authored teammate prompt file at
    # `castings/casting-{id}-prompt.md`. The prompt MUST contain the spec
    # requirements for this casting as a literal substring of the master
    # spec.md — no paraphrasing allowed. This enforces the v3.0.0
    # architecture principle: plans are prompts, authored once from the
    # spec, and handed directly to teammates without lead re-translation.
    dim7_issues = []
    castings_dir = fdir / "castings"
    normalized_spec = _normalize(spec_text)

    for c in castings:
        cid = c.get("id", "?")
        title = c.get("title", "Untitled")
        prompt_path = castings_dir / f"casting-{cid}-prompt.md"

        # 7a: the prompt file must exist
        if not prompt_path.exists():
            dim7_issues.append({
                "casting": cid,
                "title": title,
                "issue": "missing_prompt_file",
                "detail": f"casting-{cid}-prompt.md does not exist",
            })
            revision_hints.append(
                f"Casting #{cid} '{title}': decompose must write castings/casting-{cid}-prompt.md. "
                f"Re-run F0.5 DECOMPOSE."
            )
            continue

        prompt_text = prompt_path.read_text(encoding="utf-8")

        if not prompt_text.strip():
            dim7_issues.append({
                "casting": cid,
                "title": title,
                "issue": "empty_prompt_file",
                "detail": f"casting-{cid}-prompt.md is empty",
            })
            continue

        # 7b: the prompt must contain a <spec_requirements> block
        spec_block = _extract_spec_block(prompt_text)
        if spec_block is None:
            dim7_issues.append({
                "casting": cid,
                "title": title,
                "issue": "missing_spec_block",
                "detail": (
                    f"casting-{cid}-prompt.md has no <spec_requirements>...</spec_requirements> "
                    f"section. The spec requirements must be included verbatim in that block."
                ),
            })
            revision_hints.append(
                f"Casting #{cid} '{title}': add a <spec_requirements> block containing "
                f"the verbatim spec text for this casting's ACs."
            )
            continue

        # 7c: every non-trivial line in the spec block must appear verbatim in spec.md
        if not normalized_spec:
            dim7_issues.append({
                "casting": cid,
                "title": title,
                "issue": "spec_unreadable",
                "detail": "spec.md could not be read; cannot verify substring integrity",
            })
            continue

        drift_lines = _find_drift(spec_block, normalized_spec)
        if drift_lines:
            dim7_issues.append({
                "casting": cid,
                "title": title,
                "issue": "spec_drift_detected",
                "detail": (
                    f"{len(drift_lines)} line(s) in the prompt's <spec_requirements> block do not "
                    f"appear verbatim in spec.md"
                ),
                "examples": drift_lines[:3],
            })
            revision_hints.append(
                f"Casting #{cid} '{title}': the <spec_requirements> block must be a literal copy-paste "
                f"from spec.md. Paraphrasing and summarizing are forbidden. Re-run F0.5 DECOMPOSE and "
                f"copy spec text character-for-character."
            )

        # 7d: forbidden scope-cutting phrases
        forbidden_found = _find_forbidden_phrases(prompt_text)
        if forbidden_found:
            dim7_issues.append({
                "casting": cid,
                "title": title,
                "issue": "forbidden_scope_phrase",
                "detail": f"prompt contains scope-cutting language",
                "phrases": forbidden_found,
            })
            revision_hints.append(
                f"Casting #{cid} '{title}': remove forbidden phrases from the prompt "
                f"({', '.join(repr(p) for p in forbidden_found[:3])}). These phrases silently "
                f"authorize scope cuts and are banned from teammate prompts."
            )

    dim7_ok = len(dim7_issues) == 0
    if not dim7_ok:
        issues.append({
            "dimension": "prompt_fidelity",
            "severity": "error",
            "message": f"{len(dim7_issues)} prompt fidelity issue(s) detected",
        })
    dimensions["prompt_fidelity"] = {"ok": dim7_ok, "issues": dim7_issues}

    # ── Overall result ──
    # Fail on errors, warn on warnings
    error_count = sum(1 for i in issues if i.get("severity") == "error")
    passed = error_count == 0

    return {
        "passed": passed,
        "dimensions": dimensions,
        "issues": issues,
        "revision_hints": revision_hints,
        "summary": {
            "castings": len(castings),
            "spec_requirements": len(spec_req_ids),
            "covered_requirements": len(covered_reqs),
            "error_count": error_count,
            "warning_count": len(issues) - error_count,
        },
    }


# ── Helpers for Dimension 7: Prompt Fidelity ──────────────────────────


_FORBIDDEN_PHRASES = [
    # Scope-cutting patterns
    "pick the core",
    "pick the most important",
    "don't port every",
    "do not port every",
    "skip the edge cases",
    "skip the edge case",
    "core coverage",
    "main cases",
    "the important ones",
    "follow-up pr",
    "follow up pr",
    "user will validate manually",
    "user will manually validate",
    "user will confirm later",
    "validate equivalence manually",
    "intentionally out-of-scope",
    "intentionally out of scope",
    "reduced scope",
    "target line count",
    "target ~",
    "aim for ~",
    "keep it under",
    # Hedge patterns
    "sufficient coverage",
    "equivalent to legacy for the main",
    "prove the framework is sufficient",
]


def _normalize(text: str) -> str:
    """Strip markdown formatting and collapse whitespace so substring
    matching compares meaningful content rather than formatting.

    Removes:
      - Leading list markers (`-`, `*`, `+`, `1.`, etc.)
      - Bold/italic wrappers (`**word**`, `*word*`, `__word__`, `_word_`)
      - Leading/trailing whitespace on each line
      - Consecutive blank lines (collapsed to single)

    This means the prompt's <spec_requirements> block can render the
    requirement without the spec's bullet formatting, but the meaningful
    content (e.g. "US-1: User can click ...") must match character-for-
    character after normalization.
    """
    if not text:
        return ""
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        # Strip leading list markers (-, *, +, 1., 1), a), etc.)
        line = re.sub(r"^\s*(?:[-*+]|\d+[\.\)]|[a-z]\))\s+", "", line)
        # Strip bold/italic wrappers: **X**, __X__, *X*, _X_
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"__([^_]+)__", r"\1", line)
        line = re.sub(r"\*([^*]+)\*", r"\1", line)
        line = re.sub(r"_([^_]+)_", r"\1", line)
        # Normalize internal whitespace
        line = re.sub(r"\s+", " ", line).strip()
        lines.append(line)
    # Collapse consecutive blank lines
    out = []
    prev_blank = False
    for ln in lines:
        if not ln:
            if not prev_blank:
                out.append("")
            prev_blank = True
        else:
            out.append(ln)
            prev_blank = False
    return "\n".join(out)


def _extract_spec_block(prompt_text: str) -> str | None:
    """Extract content between <spec_requirements>...</spec_requirements>.
    Returns the normalized block content, or None if the block is missing.
    """
    match = re.search(
        r"<spec_requirements>(.*?)</spec_requirements>",
        prompt_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return None
    return _normalize(match.group(1))


def _find_drift(spec_block: str, normalized_spec: str) -> list[str]:
    """Return lines from the prompt's spec block that don't appear in
    normalized spec.md. The spec_block is already normalized when passed
    in (via _extract_spec_block → _normalize). We split the normalized
    spec by lines AND also check substring containment for multi-line
    cases.

    Short lines (<8 chars) are skipped to avoid false positives on
    things like '---' or 'EOF'.
    """
    drift: list[str] = []
    spec_lines = set(ln for ln in normalized_spec.splitlines() if ln.strip())
    for line in spec_block.splitlines():
        stripped = line.strip()
        if len(stripped) < 8:
            continue
        if stripped in spec_lines:
            continue
        # Fallback: substring match against the full normalized spec
        # (handles cases where the prompt wraps a requirement across
        # fewer or more lines than the spec does)
        if stripped in normalized_spec:
            continue
        drift.append(stripped)
    return drift


def _find_forbidden_phrases(prompt_text: str) -> list[str]:
    """Return any forbidden scope-cutting phrases found in the prompt."""
    lower = prompt_text.lower()
    found: list[str] = []
    for phrase in _FORBIDDEN_PHRASES:
        if phrase in lower:
            found.append(phrase)
    return found
