#!/usr/bin/env python3
"""adhoc Stop hook — methodical-mode enforcement gates.

Reads the Stop hook event JSON from stdin, walks the conversation transcript
to find the current turn's last assistant message and tool calls, then runs
four enforcement gates. Any gate firing blocks the Stop with a combined
reason message that Claude reads on the continued turn.

Gates:
  (a) Citations — file:line citations in the response must be backed by a
      Read/Grep call Claude made directly in this turn. Subagent calls do
      not count. Mode file: ~/.claude/.adhoc-citations-mode (default/off).

  (b) Uncertainty — response must NOT contain self-flagged uncertainty
      tells like "not verified", "haven't checked", "I assumed".
      Mode file: ~/.claude/.adhoc-uncertainty-mode (default/off).

  (c) Grounding — if the user's prompt looks like a codebase question
      (mentions file paths, code extensions, project terms), the response
      requires at least one Read/Grep/Glob call this turn. No general-
      knowledge fallback for codebase questions. Mode file:
      ~/.claude/.adhoc-strict-mode (default/off; shared with (d)).

  (d) Critic — substantive responses must be reviewed by spawning the
      adhoc:pre-stop-critic subagent at least once this turn before
      Claude is allowed to Stop. The critic's verdict (CONCUR / PUSH BACK /
      WRONG SHAPE) is logged but does not itself block (single critic
      cycle per turn). Mode file: shares ~/.claude/.adhoc-strict-mode.

One-shot bypass for (c) and (d): ~/.claude/.adhoc-trust-me (file is
consumed on read). Recursion guard: if the assistant response starts
with the sentinel marker [adhoc:pre-stop-critic-output], ALL gates skip
(this turn IS the critic, not a normal Claude turn).

Mode files all use the same convention as v0.1.5's citations-mode:
  absent / "default" — gate ON (block on violation)
  "off"              — gate short-circuits, no checks
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
CITATIONS_MODE_FILE = HOME / ".claude" / ".adhoc-citations-mode"
UNCERTAINTY_MODE_FILE = HOME / ".claude" / ".adhoc-uncertainty-mode"
STRICT_MODE_FILE = HOME / ".claude" / ".adhoc-strict-mode"
TRUST_ME_FILE = HOME / ".claude" / ".adhoc-trust-me"
LOG_FILE = HOME / ".claude" / ".adhoc-citations-log.jsonl"

# Sentinel — pre-stop-critic output starts with this on its first line.
# Used as the recursion guard: if the response begins with this marker, the
# Stop is for the critic itself, not the main Claude, and ALL gates skip.
CRITIC_SENTINEL = "[adhoc:pre-stop-critic-output]"

# What subagent_type the critic gate looks for in Task/Agent tool calls
CRITIC_AGENT_TYPE = "adhoc:pre-stop-critic"

# Length thresholds (chars)
GROUNDING_MIN_RESPONSE_CHARS = 200
CRITIC_MIN_RESPONSE_CHARS = 500
CLARIFYING_GATE_LENGTH = 1000  # asks shorter than this skip critic gate

# Code-file extensions (used by both citation regex and grounding heuristic)
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

FENCED_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
DIFF_LINE_RE = re.compile(r"^[+\-@]{1,3}\s")

VERIFICATION_TOOLS = {"Read", "Grep", "Glob"}
AGENT_TOOLS = {"Task", "Agent"}

# (b) Uncertainty-tell scanner — narrow regex, only the specific failure mode
UNCERTAINTY_TELLS_RE = re.compile(
    r"\b("
    r"not\s+yet\s+verified|"
    r"haven't\s+(?:verified|checked|confirmed|read)|"
    r"have\s+not\s+(?:verified|checked|confirmed|read)|"
    r"didn't\s+(?:verify|check|confirm|read)|"
    r"did\s+not\s+(?:verify|check|confirm|read)|"
    r"unverified|"
    r"still\s+need\s+to\s+(?:verify|check|confirm)|"
    r"i\s+assumed|"
    r"i'm\s+assuming|"
    r"todo:\s*verify"
    r")\b",
    re.IGNORECASE,
)

# (c) Grounding — three independent signals that a prompt is "codebase-shaped"
CODEBASE_PATH_RE = re.compile(r"\b[\w\-.]+/[\w\-./]+\b")
CODEBASE_EXT_RE = re.compile(rf"\.(?:{CODE_EXT})\b", re.IGNORECASE)
CODEBASE_ACTION_RE = re.compile(
    r"\b("
    r"function|file|files|code|fix|implement|modify|add|remove|delete|"
    r"refactor|rename|where\s+is|how\s+does|"
    r"this\s+(?:codebase|project|repo|repository|file|function|module)|"
    r"the\s+(?:codebase|project|repo|function|file|code|module|handler|endpoint|hook|script|plugin|agent|skill|command)|"
    r"our\s+(?:codebase|project|repo)|"
    r"my\s+(?:codebase|project|repo)|"
    r"in\s+(?:the\s+)?codebase|"
    r"adhoc|foundry|forge|crew|tidy|e2e"
    r")\b",
    re.IGNORECASE,
)

# (c) Grounding — markers that the assistant is asking, not answering
CLARIFYING_QUESTION_RE = re.compile(
    r"\b("
    r"want\s+me\s+to|"
    r"should\s+i|"
    r"which\s+(?:would|of\s+these|do\s+you)|"
    r"do\s+you\s+(?:want|prefer|need)|"
    r"would\s+you\s+(?:like|prefer)|"
    r"is\s+that\s+(?:right|what\s+you\s+meant)"
    r")\b",
    re.IGNORECASE,
)

# (d) Critic — verdict extraction from critic output (used for logging only;
# gate passes once any critic call exists this turn)
CRITIC_VERDICT_RE = re.compile(
    r"^###\s+Verdict\s*\n\s*(CONCUR(?:\s+WITH\s+CAVEATS)?|PUSH\s+BACK|WRONG\s+SHAPE)\b",
    re.IGNORECASE | re.MULTILINE,
)

# --- helpers --------------------------------------------------------------


def read_mode(path: Path) -> str:
    if not path.exists():
        return "default"
    try:
        return path.read_text().strip().lower() or "default"
    except OSError:
        return "default"


def consume_trust_me() -> bool:
    """Check and delete the one-shot trust-me flag. Returns True if it was present."""
    if not TRUST_ME_FILE.exists():
        return False
    try:
        TRUST_ME_FILE.unlink()
    except OSError:
        pass
    return True


def log_event(event: dict) -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a") as fh:
            fh.write(json.dumps(event) + "\n")
    except OSError:
        pass


def strip_non_citations(text: str) -> str:
    """Remove fenced code blocks and diff lines before regex-scanning prose."""
    no_fences = FENCED_BLOCK_RE.sub("", text)
    kept = []
    for line in no_fences.splitlines():
        if DIFF_LINE_RE.match(line):
            continue
        kept.append(line)
    return "\n".join(kept)


def find_citations(text: str) -> list[tuple[str, str]]:
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
    """Paths Claude directly Read/Grep'd in this turn. Subagent calls excluded."""
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
            if block.get("name", "") not in VERIFICATION_TOOLS:
                continue
            params = block.get("input", {}) or {}
            for key in ("file_path", "path"):
                val = params.get(key)
                if isinstance(val, str) and val:
                    verified.add(val)
    return verified


def path_matches_verified(cited: str, verified: set[str]) -> bool:
    cited_norm = cited.lstrip("/")
    for v in verified:
        v_norm = v.lstrip("/")
        if v_norm == cited_norm or v_norm.endswith("/" + cited_norm):
            return True
        if cited_norm.endswith("/" + v_norm):
            return True
    return False


def collect_critic_calls(turn_messages: list[dict]) -> int:
    """Count Task/Agent tool calls with subagent_type == adhoc:pre-stop-critic."""
    count = 0
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
            if block.get("name") not in AGENT_TOOLS:
                continue
            params = block.get("input", {}) or {}
            if params.get("subagent_type") == CRITIC_AGENT_TYPE:
                count += 1
    return count


def find_critic_verdict(turn_messages: list[dict]) -> str | None:
    """Extract the verdict line from the most recent critic tool_result, if any."""
    for msg in reversed(turn_messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", [])
        if isinstance(content, str):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_result":
                continue
            text_content = block.get("content", "")
            if isinstance(text_content, list):
                text_content = "\n".join(
                    b.get("text", "") for b in text_content if isinstance(b, dict)
                )
            if not isinstance(text_content, str):
                continue
            if CRITIC_SENTINEL not in text_content:
                continue
            m = CRITIC_VERDICT_RE.search(text_content)
            if m:
                return re.sub(r"\s+", " ", m.group(1).upper())
    return None


def find_last_user_prompt(messages: list[dict]) -> str:
    """Return the text of the most recent user-role message with actual user text."""
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            has_text = False
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                    has_text = True
            if has_text:
                return "\n".join(text_parts)
    return ""


def is_codebase_shaped(prompt_text: str) -> bool:
    if CODEBASE_PATH_RE.search(prompt_text):
        return True
    if CODEBASE_EXT_RE.search(prompt_text):
        return True
    if CODEBASE_ACTION_RE.search(prompt_text):
        return True
    return False


def is_clarifying_response(response_text: str) -> bool:
    stripped = response_text.strip()
    if stripped.endswith("?"):
        return True
    if CLARIFYING_QUESTION_RE.search(stripped):
        return True
    return False


def load_transcript(path: str) -> list[dict]:
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
    if not messages:
        return [], None
    last_assistant = None
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            last_assistant = msg
            break
    if last_assistant is None:
        return [], None
    last_user_idx = -1
    for i, msg in enumerate(messages):
        if msg is last_assistant:
            break
        if msg.get("role") == "user":
            last_user_idx = i
    turn_start = last_user_idx if last_user_idx >= 0 else 0
    return messages[turn_start:], last_assistant


def assistant_text(msg: dict) -> str:
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


# --- check functions ------------------------------------------------------


def check_citations(
    response_text: str, verified_paths: set[str]
) -> tuple[bool, str, list]:
    if read_mode(CITATIONS_MODE_FILE) == "off":
        return False, "", []
    citations = find_citations(response_text)
    unverified = [
        (path, line)
        for (path, line) in citations
        if not path_matches_verified(path, verified_paths)
    ]
    if not unverified:
        return False, "", citations
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
    return True, reason, unverified


def check_uncertainty(response_text: str) -> tuple[bool, str, list]:
    if read_mode(UNCERTAINTY_MODE_FILE) == "off":
        return False, "", []
    cleaned = strip_non_citations(response_text)
    hits = [m.group(0) for m in UNCERTAINTY_TELLS_RE.finditer(cleaned)]
    if not hits:
        return False, "", []
    sample = "\n".join(f'  - "{t}"' for t in hits[:5])
    reason = (
        f"[adhoc:uncertainty] Response contains {len(hits)} self-flagged "
        "uncertainty marker(s) — you are reporting back work you know is "
        "incomplete:\n"
        f"{sample}\n"
        "Either verify the flagged items now (Read/Grep) and update the "
        "response, or stop and ASK the user before continuing. Don't ship "
        "with known gaps.\n"
        "(To disable this check: /adhoc:uncertainty-off)"
    )
    return True, reason, hits


def check_grounding(
    response_text: str,
    user_prompt: str,
    verified_paths: set[str],
    strict_off: bool,
    trust_me_consumed: bool,
) -> tuple[bool, str, dict]:
    details: dict = {}
    if strict_off:
        details["skipped"] = "strict-off"
        return False, "", details
    if trust_me_consumed:
        details["skipped"] = "trust-me"
        return False, "", details
    if len(response_text) < GROUNDING_MIN_RESPONSE_CHARS:
        details["skipped"] = f"response<{GROUNDING_MIN_RESPONSE_CHARS}"
        return False, "", details
    if is_clarifying_response(response_text):
        details["skipped"] = "response-is-clarifying"
        return False, "", details
    if not is_codebase_shaped(user_prompt):
        details["skipped"] = "prompt-not-codebase-shaped"
        return False, "", details
    if verified_paths:
        details["skipped"] = "tool-calls-made"
        return False, "", details
    reason = (
        "[adhoc:grounding] The user's prompt looks codebase-shaped (mentions "
        "code, files, project terms, or this marketplace's plugin names) but "
        "you made ZERO Read/Grep/Glob calls this turn. Methodical-mode "
        "requires grounding codebase claims in actual code, not training-data "
        "inference. Either:\n"
        "  1. Read or Grep the relevant files now and update the response, or\n"
        '  2. Reply with a clarifying question instead of an answer '
        '("want me to first check X?"). Don\'t answer from inference.\n'
        "One-shot bypass for this turn only: /adhoc:trust-me. Disable for "
        "the whole session: /adhoc:strict-off."
    )
    details["blocked"] = True
    return True, reason, details


def check_critic(
    response_text: str,
    turn_messages: list[dict],
    strict_off: bool,
    trust_me_consumed: bool,
) -> tuple[bool, str, dict]:
    details: dict = {}
    if strict_off:
        details["skipped"] = "strict-off"
        return False, "", details
    if trust_me_consumed:
        details["skipped"] = "trust-me"
        return False, "", details
    if len(response_text) < CRITIC_MIN_RESPONSE_CHARS:
        details["skipped"] = f"response<{CRITIC_MIN_RESPONSE_CHARS}"
        return False, "", details
    if (
        is_clarifying_response(response_text)
        and len(response_text) < CLARIFYING_GATE_LENGTH
    ):
        details["skipped"] = "short-clarifying-response"
        return False, "", details
    critic_count = collect_critic_calls(turn_messages)
    details["critic_calls"] = critic_count
    if critic_count == 0:
        reason = (
            "[adhoc:critic] Response is substantive "
            f"({len(response_text)} chars) but you have not spawned the "
            f"{CRITIC_AGENT_TYPE} subagent to review it. Spawn it now via the "
            "Agent tool:\n"
            "\n"
            "  Agent({\n"
            f"    subagent_type: '{CRITIC_AGENT_TYPE}',\n"
            "    description: 'Pre-Stop critic review',\n"
            "    prompt: <user prompt> + <your draft response> + <one-line "
            "summary of tool calls you made this turn> + <list of files you "
            "Read/Grep'd>\n"
            "  })\n"
            "\n"
            "Address the critic's verdict (CONCUR / PUSH BACK / WRONG SHAPE) "
            "and revise the response if needed before stopping again. The hook "
            "passes once a critic call appears in this turn's history.\n"
            "One-shot bypass for this turn only: /adhoc:trust-me. Disable "
            "for the whole session: /adhoc:strict-off."
        )
        details["blocked"] = True
        return True, reason, details
    # Critic was called; pass through. Record the verdict for the log.
    verdict = find_critic_verdict(turn_messages)
    details["verdict"] = verdict
    return False, "", details


# --- main -----------------------------------------------------------------


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    # Liveness: never block twice on the same stop attempt
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

    # Recursion guard: if this Stop is for the critic itself, skip all gates
    if response_text.lstrip().startswith(CRITIC_SENTINEL):
        log_event(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "session": event.get("session_id"),
                "decision": "pass",
                "reason": "critic-output-sentinel",
            }
        )
        return 0

    user_prompt = find_last_user_prompt(messages)
    verified_paths = collect_verified_paths(turn_messages)
    strict_off = read_mode(STRICT_MODE_FILE) == "off"
    trust_me_consumed = consume_trust_me() if not strict_off else False

    citations_blocked, citations_reason, citations_details = check_citations(
        response_text, verified_paths
    )
    uncertainty_blocked, uncertainty_reason, uncertainty_details = check_uncertainty(
        response_text
    )
    grounding_blocked, grounding_reason, grounding_details = check_grounding(
        response_text, user_prompt, verified_paths, strict_off, trust_me_consumed
    )
    critic_blocked, critic_reason, critic_details = check_critic(
        response_text, turn_messages, strict_off, trust_me_consumed
    )

    log_event(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session": event.get("session_id"),
            "response_chars": len(response_text),
            "user_prompt_chars": len(user_prompt),
            "verified_paths_count": len(verified_paths),
            "trust_me_consumed": trust_me_consumed,
            "strict_off": strict_off,
            "checks": {
                "citations": {
                    "blocked": citations_blocked,
                    "details": citations_details,
                },
                "uncertainty": {
                    "blocked": uncertainty_blocked,
                    "details": uncertainty_details,
                },
                "grounding": {
                    "blocked": grounding_blocked,
                    "details": grounding_details,
                },
                "critic": {
                    "blocked": critic_blocked,
                    "details": critic_details,
                },
            },
            "decision": "block"
            if any(
                [citations_blocked, uncertainty_blocked, grounding_blocked, critic_blocked]
            )
            else "pass",
        }
    )

    reasons = [
        r
        for r in (
            citations_reason if citations_blocked else "",
            uncertainty_reason if uncertainty_blocked else "",
            grounding_reason if grounding_blocked else "",
            critic_reason if critic_blocked else "",
        )
        if r
    ]
    if not reasons:
        return 0

    combined = "\n\n".join(reasons)
    print(json.dumps({"decision": "block", "reason": combined}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
