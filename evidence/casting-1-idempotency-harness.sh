#!/usr/bin/env bash
# Faithful evidence harness for Casting C001.
# Extracts the two CHANGED heredoc blocks from the committed
# plugins/foundry/scripts/setup-prereqs.sh and runs each TWICE against a
# seeded temp project, proving idempotency + correct transformation.
# Output is path-free (temp dir never printed) so it re-executes byte-identically.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/plugins/foundry/scripts/setup-prereqs.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FIXED_SERVER_DIR="/opt/foundry/mcp-server"   # fixed so .mcp.json foundry entry is deterministic

# ── Seed an EXISTING project with the OLD broken state ────────────────────────
mkdir -p "$TMP/.serena"
cat > "$TMP/.mcp.json" <<'SEED'
{
  "mcpServers": {
    "foundry": {"command": "uvx", "args": ["old"]},
    "playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]},
    "serena": {"command": "uvx", "args": ["serena-mcp"]}
  }
}
SEED
cat > "$TMP/.serena/project.yml" <<'SEED'
# Serena LSP configuration for Foundry TRACE verification
languages:
  - name: go
  - name: typescript
  - name: python
  - name: javascript

ignored_paths:
  - node_modules
  - vendor
SEED

# ── Extract the committed Python block (between the PYEOF markers) ─────────────
PYBODY="$(sed -n '/^python3 << PYEOF$/,/^PYEOF$/p' "$SCRIPT" | sed '1d;$d')"
run_py() {
  printf '%s\n' "$PYBODY" \
    | sed "s#\$MCP_FILE#$TMP/.mcp.json#g; s#\$MCP_SERVER_DIR#$FIXED_SERVER_DIR#g" \
    | python3 >/dev/null
}

# ── Extract the committed Serena shell block ──────────────────────────────────
SERBODY="$(sed -n '/^SERENA_DIR="\$PROJECT_ROOT\/\.serena"$/,/^ok "Serena config written/p' "$SCRIPT")"
run_serena() {
  ( info() { :; }; ok() { :; }; PROJECT_ROOT="$TMP"; eval "$SERBODY" )
}

# ── Run each block TWICE ──────────────────────────────────────────────────────
run_py;     A_MCP="$(cat "$TMP/.mcp.json")"
run_py;     B_MCP="$(cat "$TMP/.mcp.json")"
run_serena; A_YML="$(cat "$TMP/.serena/project.yml")"
run_serena; B_YML="$(cat "$TMP/.serena/project.yml")"

echo "=== OT-008 idempotency (run1 == run2) ==="
[ "$A_MCP" = "$B_MCP" ] && echo ".mcp.json    : IDEMPOTENT" || { echo ".mcp.json    : NOT IDEMPOTENT"; exit 1; }
[ "$A_YML" = "$B_YML" ] && echo "project.yml  : IDEMPOTENT" || { echo "project.yml  : NOT IDEMPOTENT"; exit 1; }

echo
echo "=== OT-002 / AC-002 / FR-009: serena entry replaced with HTTP ==="
python3 - "$TMP/.mcp.json" <<'CHK'
import json, sys
s = json.load(open(sys.argv[1]))["mcpServers"]["serena"]
assert s == {"type": "http", "url": "http://localhost:9121/mcp"}, s
assert "command" not in s and "args" not in s, s
print("serena =", json.dumps(s))
print("no command/args keys under serena: PASS")
CHK

echo
echo "=== resulting .mcp.json ==="
cat "$TMP/.mcp.json"

echo
echo "=== OT-006 / FR-008: javascript removed; OT-007: forge-specs/foundry-archive/.serena added ==="
grep -q 'name: javascript' "$TMP/.serena/project.yml" && { echo "javascript present: FAIL"; exit 1; } || echo "javascript removed: PASS"
for p in forge-specs foundry-archive .serena; do
  grep -q "  - $p" "$TMP/.serena/project.yml" || { echo "$p missing: FAIL"; exit 1; }
done
echo "forge-specs/foundry-archive/.serena present: PASS"

echo
echo "=== resulting .serena/project.yml ==="
cat "$TMP/.serena/project.yml"
