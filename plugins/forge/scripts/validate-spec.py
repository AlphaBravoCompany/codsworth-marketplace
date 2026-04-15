#!/usr/bin/env python3
"""
validate-spec.py — deterministic fidelity/traceability/coverage gate for
forge-generated specifications.

Enforces the v3.4.0 Verbatim-Fidelity contract:

  * Fidelity     — every Locked requirement quotes the user's literal words,
                   and the quote is a byte-identical substring of the cited
                   transcript answer.
  * Traceability — every bullet / table row in listed sections carries a
                   citation marker that resolves to a real transcript answer
                   (or a survey file / reality.md for permitted sections).
  * Coverage     — every A-NNN in the transcript is cited somewhere in the
                   spec body, so no interview content is silently dropped.
  * Structure    — the spec has a populated `## Global Invariants` section
                   and embeds the transcript verbatim as an appendix.

Exits 0 on pass, 1 on any failure, 2 on usage error.
Usage: validate-spec.py <spec.md> <transcript.md>

This script is the authoritative R4 gate. The model's self-check prose in
setup-forge.sh is advisory; this script is load-bearing. If the script fails,
finalization must not proceed.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_TRANSCRIPT_ANSWERS = 3

APPENDIX_HEADING_RE = re.compile(
    r"^##\s+Appendix:\s*Interview\s+Transcript\b",
    re.MULTILINE | re.IGNORECASE,
)

GLOBAL_INVARIANTS_HEADING_RE = re.compile(
    r"^##\s+Global\s+Invariants\b",
    re.MULTILINE | re.IGNORECASE,
)

ANSWER_BLOCK_RE = re.compile(
    r"^##\s+(A-\d+)(?:\s*\[([^\]]*)\])?\s*\n(.*?)(?=^##\s+[AQ]-\d+|^##\s+[A-Z]|\Z)",
    re.MULTILINE | re.DOTALL,
)

QUESTION_BLOCK_RE = re.compile(
    r"^##\s+Q-\d+\b",
    re.MULTILINE,
)

CITATION_RE = re.compile(
    r"\[(?:from|derived from)\s+[^\]]+\]",
    re.IGNORECASE,
)

ANSWER_REF_RE = re.compile(r"\bA-\d+\b")
QUESTION_CITE_RE = re.compile(r"\[\s*from\s+(Q-\d+)\s*\]", re.IGNORECASE)

QUOTED_STRING_RE = re.compile(r'"([^"\n]{3,})"')

LOCKED_ITEM_ID_RE = re.compile(
    r"^\s*[-*]\s+\*\*(FR-\d+|NFR-\d+|AC-\d+|GI-\d+|US-\d+|OT-\d+)\*\*",
    re.MULTILINE,
)

SECTION_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$", re.MULTILINE)

# Sections whose bullets / table rows MUST carry a citation marker.
# Matched case-insensitively on the heading text (trimmed).
# Implementation Phases is EXCLUDED — its bullets trace via "implements [FR-NNN]"
# requirement references, not direct transcript citations, and the requirements
# themselves already carry the fidelity burden.
REQUIRED_CITATION_SECTIONS = {
    "problem statement",
    "scope",
    "user stories",
    "functional requirements",
    "non-functional requirements",
    "global invariants",
    "technical design",
    "file change map",
    "observable truths",
    "codebase references",
}

# Sentinels and scaffolding that do NOT need citations.
SENTINEL_LINES = {
    "none — the user gave no explicit placement constraints.",
    "none - the user gave no explicit placement constraints.",
}

# Sub-field prefixes. Lines starting with any of these (after stripping the
# bullet marker) are treated as sub-fields of their parent bullet and inherit
# the parent's citation — no independent citation required.
SUBFIELD_PREFIXES = (
    "**verification:**",
    "**depends on:**",
    "**source answers",
    "**acceptance criteria:**",
    "**codebase integration",
    "**current state**",
    "**proposed changes:**",
    "**new endpoints:**",
    "**modified endpoints:**",
    "**pattern to follow**",
    "**component diagram:**",
    "**dependency flow:**",
    "**error cases for this feature:**",
    "**claude's gloss",
    "maps to:",
    "maps to ",
    "applies to:",
    "applies to ",
    "violation looks like:",
    "violation looks like ",
    "extends:",
    "extends ",
    "follows pattern:",
    "follows pattern ",
    "new files:",
    "new files ",
    "modifies:",
    "modifies ",
    "migration strategy:",
    "migration strategy ",
)

# A line that starts with `**As a**` is the User Story narrative line —
# its parent US heading already carries the citation.
US_NARRATIVE_PREFIX = "**as a**"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Answer:
    id: str
    body: str
    tags: list[str] = field(default_factory=list)


@dataclass
class Report:
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Track which item IDs have already been flagged NOT_VERBATIM so the
    # Locked check and the opportunistic check don't both fire on the
    # same bullet.
    verbatim_violated: set[str] = field(default_factory=set)

    def fail(self, msg: str) -> None:
        self.failures.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_transcript(text: str) -> dict[str, Answer]:
    """Return {A-NNN: Answer(id, body, tags)}."""
    answers: dict[str, Answer] = {}
    for match in ANSWER_BLOCK_RE.finditer(text):
        aid = match.group(1)
        tag_blob = match.group(2) or ""
        body = match.group(3).strip()
        tags = [t.strip() for t in tag_blob.split(",") if t.strip()]
        answers[aid] = Answer(id=aid, body=body, tags=tags)
    return answers


def split_spec_body_appendix(text: str) -> tuple[str, str | None]:
    """Return (body, appendix) — appendix is None if no appendix section."""
    match = APPENDIX_HEADING_RE.search(text)
    if not match:
        return text, None
    return text[: match.start()], text[match.start() :]


def iter_sections(text: str) -> Iterable[tuple[str, int, int]]:
    """Yield (heading_text, start_of_body, end_of_section) for every `## ` section.

    `## ` headings only (not `###` subsections). Body starts after the heading
    line and extends until the next `## ` or end-of-text.
    """
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", text, re.MULTILINE))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        yield m.group(1).strip(), start, end


def extract_section(text: str, heading_name: str) -> str | None:
    """Extract the body of a `## {heading_name}` section (case-insensitive)."""
    target = heading_name.strip().lower()
    for name, start, end in iter_sections(text):
        if name.lower().startswith(target):
            return text[start:end]
    return None


# ---------------------------------------------------------------------------
# Checks — each returns nothing and appends to Report
# ---------------------------------------------------------------------------


def check_transcript_sanity(
    answers: dict[str, Answer], report: Report
) -> None:
    if len(answers) < MIN_TRANSCRIPT_ANSWERS:
        report.fail(
            f"TRANSCRIPT_TOO_SHALLOW: transcript has {len(answers)} "
            f"A-NNN answers, need ≥{MIN_TRANSCRIPT_ANSWERS}"
        )


def check_structure(
    spec_text: str,
    body: str,
    appendix: str | None,
    transcript_answers: dict[str, Answer],
    report: Report,
) -> None:
    if not GLOBAL_INVARIANTS_HEADING_RE.search(spec_text):
        report.fail(
            "MISSING_SECTION: '## Global Invariants' not found in spec. "
            "Foundry decompose needs this to propagate architectural "
            "constraints into every casting."
        )

    if appendix is None:
        report.fail(
            "MISSING_APPENDIX: '## Appendix: Interview Transcript' not found "
            "in spec. Embed transcript.md verbatim at finalization."
        )
        return

    # Count A-NNN blocks inside the appendix (not body) and compare to
    # transcript.md. If the appendix is truncated, fail.
    appendix_answer_ids = set(
        m.group(1) for m in ANSWER_BLOCK_RE.finditer(appendix)
    )
    transcript_ids = set(transcript_answers.keys())
    missing_from_appendix = transcript_ids - appendix_answer_ids
    if missing_from_appendix:
        report.fail(
            f"APPENDIX_INCOMPLETE: transcript has "
            f"{len(transcript_ids)} answers but appendix contains "
            f"only {len(appendix_answer_ids)}. "
            f"Missing: {sorted(missing_from_appendix)[:10]}"
            + (" ..." if len(missing_from_appendix) > 10 else "")
        )


def check_locked_fidelity(
    body: str, transcript_answers: dict[str, Answer], report: Report
) -> None:
    """Locked items must have a quoted substring that is byte-identical to
    a range inside the cited transcript answer.
    """
    # A Locked item lives inside `### Locked (...)` or inside Global Invariants
    # (every GI is implicitly Locked). We scan the body for bullets whose ID
    # prefix is FR/NFR/AC/GI AND which sit under a Locked heading OR inside
    # the Global Invariants section. For simplicity we treat EVERY bullet with
    # `**FR-N**` / `**NFR-N**` / `**AC-N**` / `**GI-N**` under a "Locked"
    # subheading, AND every `**GI-N**` anywhere, as Locked.
    locked_bullets = _collect_locked_bullets(body)
    for bullet in locked_bullets:
        _check_single_locked(bullet, transcript_answers, report)


def _collect_locked_bullets(body: str) -> list[tuple[str, str, str]]:
    """Return list of (id, full_bullet_text, section_name) for Locked items."""
    bullets: list[tuple[str, str, str]] = []
    # Walk ## sections, then within each find ### Locked subsections,
    # then extract bullets. Also pull every GI-NNN bullet regardless of
    # Locked framing (GIs are always Locked).
    for section_name, start, end in iter_sections(body):
        section = body[start:end]

        # Direct GI bullets (Global Invariants = implicitly Locked)
        if section_name.lower().startswith("global invariants"):
            for b in _iter_bullets(section):
                if re.search(r"\*\*GI-\d+\*\*", b):
                    bullets.append(("GI", b, section_name))

        # ### Locked subsections
        sub_matches = list(
            re.finditer(r"^###\s+Locked\b.*?$", section, re.MULTILINE)
        )
        for i, sm in enumerate(sub_matches):
            sub_start = sm.end()
            # end of this subsection: next ### or end of parent
            next_sub = re.search(r"^###\s+", section[sub_start:], re.MULTILINE)
            sub_end = (
                sub_start + next_sub.start()
                if next_sub is not None
                else len(section)
            )
            sub_body = section[sub_start:sub_end]
            for b in _iter_bullets(sub_body):
                id_match = re.search(r"\*\*((?:FR|NFR|AC|GI)-\d+)\*\*", b)
                if id_match:
                    bullets.append((id_match.group(1), b, section_name))
    return bullets


def _iter_bullets(text: str) -> Iterable[str]:
    """Yield full bullet strings (including multi-line continuations)."""
    lines = text.splitlines()
    i = 0
    current: list[str] = []
    bullet_indent: int | None = None
    while i < len(lines):
        line = lines[i]
        # Start of a bullet
        m = re.match(r"^(\s*)([-*])\s+", line)
        if m:
            if current:
                yield "\n".join(current)
                current = []
            bullet_indent = len(m.group(1))
            current.append(line)
        elif current is not None and line.strip() == "":
            # Blank line — keep accumulating if the next non-blank is still
            # indented under this bullet; for simplicity we end bullets on
            # blank lines unless followed by an indented continuation.
            # Conservative: break here.
            yield "\n".join(current)
            current = []
            bullet_indent = None
        elif current:
            # Continuation if more indented than the bullet marker
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            if bullet_indent is not None and indent > bullet_indent:
                current.append(line)
            else:
                yield "\n".join(current)
                current = []
                bullet_indent = None
                # Re-process this line as potential new bullet
                continue
        i += 1
    if current:
        yield "\n".join(current)


def _check_single_locked(
    bullet: tuple[str, str, str],
    transcript_answers: dict[str, Answer],
    report: Report,
) -> None:
    item_id, text, section = bullet
    # L1: has quoted string
    quotes = QUOTED_STRING_RE.findall(text)
    if not quotes:
        report.fail(
            f"LOCKED_NO_QUOTE: {item_id} in '{section}' has no double-quoted "
            f"user-verbatim substring. Either add the user's literal words "
            f"inside quotes or re-classify as Flexible."
        )
        return
    # L2: has [from A-NNN] marker
    citation_match = re.search(
        r"\[from\s+((?:A-\d+)(?:\s*,\s*A-\d+)*)\s*\]", text, re.IGNORECASE
    )
    if not citation_match:
        report.fail(
            f"LOCKED_NO_CITATION: {item_id} in '{section}' has no "
            f"[from A-NNN] marker."
        )
        return
    cited_ids = re.findall(r"A-\d+", citation_match.group(1))
    # L3: citation resolves
    unresolved = [cid for cid in cited_ids if cid not in transcript_answers]
    if unresolved:
        report.fail(
            f"DANGLING_CITATION: {item_id} cites {unresolved} but "
            f"transcript has no such answer(s). This is hallucination."
        )
        return
    # L4: at least one quoted string is a byte-identical substring of some
    # cited answer's body. (Multiple quotes allowed; at least one must match.)
    matched_any = False
    for quote in quotes:
        for cid in cited_ids:
            if quote in transcript_answers[cid].body:
                matched_any = True
                break
        if matched_any:
            break
    if not matched_any:
        preview = quotes[0][:80].replace("\n", " ")
        report.fail(
            f"NOT_VERBATIM: {item_id} quotes '{preview}' but that text does "
            f"not appear verbatim in cited answer(s) {cited_ids}. Either fix "
            f"the quote to match the transcript, or re-classify as Flexible."
        )
        report.verbatim_violated.add(item_id)


def check_opportunistic_fidelity(
    body: str, transcript_answers: dict[str, Answer], report: Report
) -> None:
    """Any line in the spec body containing BOTH a double-quoted substring
    AND a `[from A-NNN]` marker is subject to verbatim check, even if the
    line isn't in a `### Locked` subsection. This catches AC-NNN bullets
    nested inside User Stories, ad-hoc quoted claims in Technical Design,
    etc. Lines with `[derived from A-NNN]` and a quote are flexible —
    the quote is illustrative, not verbatim — so this check only applies
    to `[from A-NNN]` lines.
    """
    from_cite_pattern = re.compile(
        r"\[from\s+((?:A-\d+)(?:\s*,\s*A-\d+)*)\s*\]", re.IGNORECASE
    )
    for line in body.splitlines():
        from_match = from_cite_pattern.search(line)
        if not from_match:
            continue
        quotes = QUOTED_STRING_RE.findall(line)
        if not quotes:
            continue
        cited_ids = re.findall(r"A-\d+", from_match.group(1))
        unresolved = [c for c in cited_ids if c not in transcript_answers]
        if unresolved:
            # Already reported by check_dangling_refs; skip here.
            continue
        matched = False
        for quote in quotes:
            for cid in cited_ids:
                if quote in transcript_answers[cid].body:
                    matched = True
                    break
            if matched:
                break
        if not matched:
            id_match = re.search(
                r"\*\*((?:FR|NFR|AC|GI|US|OT)-\d+)\*\*", line
            )
            label = id_match.group(1) if id_match else "line"
            # Skip if the Locked check already flagged this item
            if label in report.verbatim_violated:
                continue
            preview = quotes[0][:80].replace("\n", " ")
            report.fail(
                f"NOT_VERBATIM: {label} quotes '{preview}' but that text "
                f"does not appear verbatim in cited answer(s) {cited_ids}. "
                f"A `[from A-NNN]` marker next to a quoted string means the "
                f"quote must be byte-identical to the cited answer."
            )
            report.verbatim_violated.add(label)


def check_universal_citations(body: str, report: Report) -> None:
    """Every bullet / table row in REQUIRED_CITATION_SECTIONS must contain a
    traceable marker (or be an allowed sentinel / scaffolding line).
    """
    for section_name, start, end in iter_sections(body):
        name_norm = section_name.strip().lower()
        if name_norm not in REQUIRED_CITATION_SECTIONS:
            continue
        section = body[start:end]
        for line_num, line in enumerate(section.splitlines(), 1):
            if not _line_requires_citation(line):
                continue
            if not _line_has_traceable_marker(line):
                preview = line.strip()[:100]
                report.fail(
                    f"UNSOURCED_BULLET: section '{section_name}' line "
                    f"{line_num}: {preview}"
                )


def _line_requires_citation(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    # Headings
    if stripped.startswith("#"):
        return False
    # Blockquotes (guidance lines the template itself emits)
    if stripped.startswith(">"):
        return False
    # Horizontal rules
    if stripped.startswith("---"):
        return False
    # Sentinels
    if stripped.lower() in SENTINEL_LINES:
        return False
    # Table rows
    if stripped.startswith("|"):
        # Separator rows
        if set(stripped.replace("|", "").strip()) <= set("-: "):
            return False
        # Header row detection is heuristic: treat rows whose cells are all
        # short labels (≤3 words, no digits) as headers.
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if cells and all(
            len(c.split()) <= 3 and not any(ch.isdigit() for ch in c)
            for c in cells
        ):
            return False
        return True
    # Strip bullet marker before scaffolding/sub-field checks
    bullet_match = re.match(r"^[-*]\s+\[?\s*[ x]?\s*\]?\s*", stripped)
    content = stripped[bullet_match.end() :] if bullet_match else stripped
    content_low = content.lower()
    # Sub-field prefixes — these are elaborations of the parent bullet
    if any(content_low.startswith(p) for p in SUBFIELD_PREFIXES):
        return False
    # User Story narrative line
    if content_low.startswith(US_NARRATIVE_PREFIX):
        return False
    # List items (after sub-field exclusion) → citation required
    if bullet_match:
        return True
    # Plain paragraph lines inside a required section
    return True


def _line_has_traceable_marker(line: str) -> bool:
    """A line is traceable if it has EITHER a [from/derived from] citation
    OR a bare A-NNN reference OR a bracketed requirement ID reference
    ([FR-NNN], [GI-NNN], [US-NNN], [OT-NNN], [NFR-NNN], [AC-NNN]).
    """
    if CITATION_RE.search(line):
        return True
    if ANSWER_REF_RE.search(line):
        return True
    if re.search(r"\[(?:FR|NFR|AC|GI|US|OT)-\d+", line):
        return True
    return False


def check_dangling_refs(
    body: str, transcript_answers: dict[str, Answer], report: Report
) -> None:
    """Every A-NNN referenced inside a citation marker in the body must exist
    in the transcript.
    """
    seen_bad: set[tuple[str, str]] = set()
    for cite_match in CITATION_RE.finditer(body):
        cite_text = cite_match.group(0)
        for aid_match in ANSWER_REF_RE.finditer(cite_text):
            aid = aid_match.group(0)
            if aid not in transcript_answers:
                key = (aid, cite_text)
                if key in seen_bad:
                    continue
                seen_bad.add(key)
                report.fail(
                    f"DANGLING_CITATION: spec body cites {aid} in "
                    f"'{cite_text}' but transcript has no such answer."
                )


def check_no_question_citations(body: str, report: Report) -> None:
    for m in QUESTION_CITE_RE.finditer(body):
        report.fail(
            f"CITES_QUESTION: spec contains '[from {m.group(1)}]'. "
            f"Citations must point at answers (A-NNN), not questions."
        )


def check_arch_invariants_populated(
    body: str, transcript_answers: dict[str, Answer], report: Report
) -> None:
    arch_tagged = [
        aid
        for aid, ans in transcript_answers.items()
        if any("ARCH_INVARIANT" in t for t in ans.tags)
    ]
    if not arch_tagged:
        return
    gi_section = extract_section(body, "Global Invariants")
    if gi_section is None:
        # Already reported by check_structure; don't double-fail here.
        return
    gi_entries = re.findall(
        r"^\s*[-*]\s+\*\*GI-\d+\*\*", gi_section, re.MULTILINE
    )
    if not gi_entries:
        report.fail(
            f"MISSING_GI_ENTRIES: transcript has "
            f"{len(arch_tagged)} ARCH_INVARIANT-tagged answer(s) "
            f"({arch_tagged[:5]}) but Global Invariants section has no "
            f"GI-NNN entries. Extract the placement rules from those answers."
        )


def check_coverage(
    body: str, transcript_answers: dict[str, Answer], report: Report
) -> None:
    """Every A-NNN in the transcript must be cited somewhere in the spec
    body (not counting the embedded appendix). Uncited answers mean the
    model dropped interview content on the floor.
    """
    cited: set[str] = set()
    for cite_match in CITATION_RE.finditer(body):
        for aid_match in ANSWER_REF_RE.finditer(cite_match.group(0)):
            cited.add(aid_match.group(0))
    uncited = sorted(set(transcript_answers.keys()) - cited)
    if uncited:
        report.fail(
            f"UNCITED_ANSWERS: {len(uncited)} transcript answer(s) are never "
            f"cited in the spec body: {uncited[:10]}"
            + (" ..." if len(uncited) > 10 else "")
            + ". Either cite them in a relevant section, add to Informational "
            f"with a note, or remove them from the transcript if the user "
            f"retracted them."
        )


def check_survey_only_requirements(body: str, report: Report) -> None:
    """FR/NFR items under Locked/Flexible whose only citation is
    [from survey/...] — these imply a requirement inferred from the codebase,
    not from the user.
    """
    for section_name, start, end in iter_sections(body):
        name_low = section_name.strip().lower()
        if name_low not in (
            "functional requirements",
            "non-functional requirements",
        ):
            continue
        section = body[start:end]
        # Only inspect bullets under ### Locked / ### Flexible
        sub_matches = list(
            re.finditer(
                r"^###\s+(Locked|Flexible)\b", section, re.MULTILINE
            )
        )
        for i, sm in enumerate(sub_matches):
            sub_start = sm.end()
            next_sub = re.search(
                r"^###\s+", section[sub_start:], re.MULTILINE
            )
            sub_end = (
                sub_start + next_sub.start()
                if next_sub is not None
                else len(section)
            )
            sub_body = section[sub_start:sub_end]
            for bullet in _iter_bullets(sub_body):
                id_match = re.search(
                    r"\*\*((?:FR|NFR)-\d+)\*\*", bullet
                )
                if not id_match:
                    continue
                has_answer_cite = bool(ANSWER_REF_RE.search(bullet))
                has_survey_cite = "survey/" in bullet.lower()
                if has_survey_cite and not has_answer_cite:
                    report.fail(
                        f"SURVEY_ONLY_REQUIREMENT: {id_match.group(1)} in "
                        f"'{section_name}' cites only a survey file with no "
                        f"[from A-NNN] backing. This is a requirement "
                        f"inferred from the codebase, not from the user."
                    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(
            "usage: validate-spec.py <spec.md> <transcript.md>",
            file=sys.stderr,
        )
        return 2

    spec_path = Path(argv[1])
    transcript_path = Path(argv[2])

    if not spec_path.exists():
        print(f"FAIL: spec file not found: {spec_path}", file=sys.stderr)
        return 1
    if not transcript_path.exists():
        print(
            f"FAIL: transcript file not found: {transcript_path}",
            file=sys.stderr,
        )
        return 1

    spec_text = spec_path.read_text(encoding="utf-8")
    transcript_text = transcript_path.read_text(encoding="utf-8")

    transcript_answers = parse_transcript(transcript_text)
    body, appendix = split_spec_body_appendix(spec_text)

    report = Report()

    check_transcript_sanity(transcript_answers, report)
    check_structure(spec_text, body, appendix, transcript_answers, report)
    check_locked_fidelity(body, transcript_answers, report)
    check_opportunistic_fidelity(body, transcript_answers, report)
    check_universal_citations(body, report)
    check_dangling_refs(body, transcript_answers, report)
    check_no_question_citations(body, report)
    check_arch_invariants_populated(body, transcript_answers, report)
    check_survey_only_requirements(body, report)
    check_coverage(body, transcript_answers, report)

    # Dedupe failures (opportunistic + locked checks can fire on the same line)
    seen: set[str] = set()
    deduped: list[str] = []
    for f in report.failures:
        if f in seen:
            continue
        seen.add(f)
        deduped.append(f)
    report.failures = deduped

    # Print report
    print(f"=== Forge Spec Validation ===")
    print(f"spec:       {spec_path}")
    print(f"transcript: {transcript_path} ({len(transcript_answers)} answers)")
    print()

    if report.warnings:
        print(f"⚠ {len(report.warnings)} WARNING(S):")
        for w in report.warnings:
            print(f"  - {w}")
        print()

    if report.failures:
        print(f"✗ {len(report.failures)} FAILURE(S):")
        for i, f in enumerate(report.failures, 1):
            print(f"  {i}. {f}")
        print()
        print(
            "FAIL: spec does not satisfy the Verbatim-Fidelity Gate. "
            "Fix and re-run."
        )
        return 1

    print("✓ PASS: fidelity, traceability, and coverage checks all passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
