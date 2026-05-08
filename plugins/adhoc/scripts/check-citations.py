#!/usr/bin/env python3
"""adhoc Stop hook — citation verifier.

Reads the Stop hook event JSON from stdin, walks the conversation transcript
to find the current turn's last assistant message and tool calls, then checks
every file:line citation in the response against the set of paths that were
actually Read or Grep'd in this turn (subagent calls excluded).

If any cited file:line was NOT directly Read/Grep'd by Claude in this turn,
the hook blocks the response — forcing Claude to verify or remove the claim
before stopping.

Mode is controlled by ~/.claude/.adhoc-citations-mode:
  absent / "default" — block on unverified file:line citations (default)
  "off"              — short-circuit, no checks
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# --- configuration --------------------------------------------------------

HOME = Path(os.environ.get("HOME", os.path.expanduser("~")))
MODE_FILE = HOME / ".claude" / ".adhoc-citations-mode"
LOG_FILE = HOME / ".claude" / ".adhoc-citations-log.jsonl"

# Tier A regex: path/to/file.ext:NUMBER
# - path component must contain at least one '/' or be a recognizable filename
# - ext must be a known code/config extension to reduce noise on prose
CODE_EXT = (
    "go|ts|tsx|js|jsx|mjs|cjs|py|rb|rs|java|kt|swift|c|cc|cpp|cxx|h|hpp|"
    "cs|php|scala|clj|ex|exs|erl|hs|ml|fs|fsx|sh|bash|zsh|"
    "proto|sql|yaml|yml|toml|ini|json|jsonl|"
    "md|mdx|tf|hcl|dockerfile|"
    "html|css|scss|sass|less|vue|svelte"
)
CITATION_RE = re.compile(
    rf"(?P<path>(?:[\w\-./]+/)*[\w\-.]+\.(?:{CODE_EXT})):(?P<line>\d+)",
    re.IGNORECASE,
)

# Strip fenced code blocks before regex — Claude may write example code with
# fake paths. Citations inside ``` blocks are not load-bearing claims.
FENCED_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)

# Diff/patch markers — `+++ b/foo.go` is structural, not a citation.
DIFF_LINE_RE = re.compile(r"^[+\-@]{1,3}\s")

# Tools that count as "Claude directly verified this path"
VERIFICATION_TOOLS = {"Read", "Grep", "Glob"}

# --- helpers --------------------------------------------------------------

def read_mode() -> str:
    """Return current citation-check mode: 'default' or 'off'."""
    if not MODE_FILE.exists():
        return "default"
    try:
        return MODE_FILE.read_text().strip().lower() or "default"
    except OSError:
        return "default"


def log_event(event: dict) -> None:
    """Append one JSONL line to the citations log. Best-effort; never raises."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a") as fh:
            fh.write(json.dumps(event) + "\n")
    except OSError:
        pass


def strip_non_citations(text: str) -> str:
    """Remove fenced code blocks and diff lines before citation regex.

    Fenced blocks are illustrative; diff markers are structural — neither
    represents Claude making a load-bearing factual claim about the codebase.
    """
    no_fences = FENCED_BLOCK_RE.sub("", text)
    kept = []
    for line in no_fences.splitlines():
        if DIFF_LINE_RE.match(line):
            continue
        kept.append(line)
    return "\n".join(kept)


def find_citations(text: str) -> list[tuple[str, str]]:
    """Extract (path, line) tuples from prose claims, skipping code blocks."""
    cleaned = strip_non_citations(text)
    seen = set()
    out: list[tuple[str, str]] = []
    for m in CITATION_RE.finditer(cleaned):
        key = (m.group("path"), m.group("line"))
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def collect_verified_paths(turn_messages: list[dict]) -> set[str]:
    """Return the set of file paths Claude directly Read/Grep'd in this turn.

    Subagent (Task / Agent) tool calls are intentionally NOT included — their
    internal Reads happen in a separate context and don't constitute direct
    verification by the parent Claude.
    """
    verified: set[str] = set()
    for msg in turn_messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if isinstance(content, str):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use":
                continue
            tool = block.get("name", "")
            if tool not in VERIFICATION_TOOLS:
                continue
            params = block.get("input", {}) or {}
            # Read uses file_path; Grep uses path; Glob uses path
            for key in ("file_path", "path"):
                val = params.get(key)
                if isinstance(val, str) and val:
                    verified.add(val)
    return verified


def path_matches_verified(cited: str, verified: set[str]) -> bool:
    """A citation is verified if its path matches any path Claude touched.

    Match is suffix-based: cited 'internal/api/handler.go' is verified by a
    Read of '/Users/x/proj/internal/api/handler.go'. Direction matters —
    cited path must be a suffix of (or equal to) a verified path.
    """
    cited_norm = cited.lstrip("/")
    for v in verified:
        v_norm = v.lstrip("/")
        if v_norm == cited_norm or v_norm.endswith("/" + cited_norm):
            return True
        # also allow the reverse: verified path is a suffix of cited path
        # (e.g. cited "src/foo/bar.go" and Read("foo/bar.go"))
        if cited_norm.endswith("/" + v_norm):
            return True
    return False


def load_transcript(path: str) -> list[dict]:
    """Read the JSONL transcript file. Returns [] on any failure."""
    try:
        msgs = []
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    msgs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return msgs
    except OSError:
        return []


def slice_current_turn(messages: list[dict]) -> tuple[list[dict], dict | None]:
    """Return (turn_messages, last_assistant_message) for the current turn.

    Walks backwards from the end:
      - find the last assistant message with text content (the response)
      - collect everything from the most recent user message forward
    """
    if not messages:
        return [], None

    # Find last assistant text message (the response we're checking)
    last_assistant = None
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            last_assistant = msg
            break

    if last_assistant is None:
        return [], None

    # Find most recent user message before the last assistant message
    last_user_idx = -1
    for i, msg in enumerate(messages):
        if msg is last_assistant:
            break
        if msg.get("role") == "user":
            last_user_idx = i

    turn_start = last_user_idx if last_user_idx >= 0 else 0
    return messages[turn_start:], last_assistant


def assistant_text(msg: dict) -> str:
    """Concatenate all text blocks in an assistant message."""
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts)


# --- main -----------------------------------------------------------------

def main() -> int:
    mode = read_mode()
    if mode == "off":
        # Short-circuit: hook is disabled. Allow stop normally.
        return 0

    # Read Stop hook event from stdin
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        # Malformed input — don't block, just exit cleanly
        return 0

    # Avoid infinite loops: if we already blocked this stop attempt, allow now
    if event.get("stop_hook_active"):
        return 0

    transcript_path = event.get("transcript_path")
    if not transcript_path or not os.path.exists(transcript_path):
        return 0

    messages = load_transcript(transcript_path)
    turn_messages, last_assistant = slice_current_turn(messages)
    if last_assistant is None:
        return 0

    response_text = assistant_text(last_assistant)
    citations = find_citations(response_text)
    verified_paths = collect_verified_paths(turn_messages)

    unverified = [
        (path, line)
        for (path, line) in citations
        if not path_matches_verified(path, verified_paths)
    ]

    log_event(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session": event.get("session_id"),
            "citations_found": [{"path": p, "line": l} for p, l in citations],
            "verified_paths_in_turn": sorted(verified_paths),
            "unverified": [{"path": p, "line": l} for p, l in unverified],
            "decision": "block" if unverified else "pass",
        }
    )

    if not unverified:
        return 0

    # Block: Claude must continue and address the unverified citations.
    cited_lines = "\n".join(f"  - {p}:{l}" for p, l in unverified)
    reason = (
        "[adhoc:citations] Response contains "
        f"{len(unverified)} file:line citation(s) that were NOT Read or Grep'd "
        "by you in this turn:\n"
        f"{cited_lines}\n"
        "Subagent (Task/Agent) calls do NOT count as direct verification — their "
        "internal Reads are not visible here. For each unverified citation, "
        "either:\n"
        "  1. Read the file yourself now and confirm the line is correct, or\n"
        "  2. Remove the citation from your response.\n"
        "Then continue. Do not stop until every file:line citation is backed "
        "by a Read/Grep tool call you made directly in this turn.\n"
        "(To disable this check: /adhoc:citations-off)"
    )

    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
