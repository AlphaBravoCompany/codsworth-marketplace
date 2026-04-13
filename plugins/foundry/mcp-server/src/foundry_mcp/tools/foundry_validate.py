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
