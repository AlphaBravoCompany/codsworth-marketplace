#!/usr/bin/env bash
# serena-daemon.sh — Manage the shared Serena MCP HTTP daemon.
#
# All Claude Code sessions connect to one long-lived serena-mcp process over
# streamable-HTTP at localhost:9121 instead of each session forking its own
# stdio process. This script starts/stops/inspects that daemon and can install
# an OS service so it survives reboots.
#
# Usage: serena-daemon.sh <subcommand>
#
# Subcommands: start stop status restart install-service uninstall-service
#
# Streamable-HTTP transport only (SSE is broken for Claude Code, issue #196).

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

info()  { printf "${CYAN}[serena]${RESET} %s\n" "$*"; }
ok()    { printf "${GREEN}[serena]${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}[serena]${RESET} %s\n" "$*"; }
fail()  { printf "${RED}[serena]${RESET} %s\n" "$*" >&2; }

# ── Constants ─────────────────────────────────────────────────────────────────
PORT=9121
PID_FILE="$HOME/.serena-daemon.pid"
LOG_FILE="$HOME/.serena-daemon.log"
PLIST_FILE="$HOME/Library/LaunchAgents/com.codsworth.serena.plist"
SYSTEMD_FILE="$HOME/.config/systemd/user/serena-daemon.service"

# ── start ─────────────────────────────────────────────────────────────────────
# Idempotent. Never spawns a second process if one is already running.
cmd_start() {
  # 1. PID file liveness check.
  if [ -f "$PID_FILE" ]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      ok "Serena daemon already running (PID $pid)"
      exit 0
    fi
    # Stale PID file — remove and continue.
    rm -f "$PID_FILE"
  fi

  # 2. Port in-use check.
  local port_pids=""
  if command -v lsof >/dev/null 2>&1; then
    port_pids="$(lsof -i :"$PORT" -t 2>/dev/null || true)"
    if [ -n "$port_pids" ]; then
      local found_serena=""
      local p cmdline
      for p in $port_pids; do
        cmdline="$(ps -p "$p" -o command= 2>/dev/null || true)"
        if printf '%s' "$cmdline" | grep -q "serena-mcp"; then
          found_serena="$p"
        fi
      done
      if [ -n "$found_serena" ]; then
        # Serena already on the port but no valid PID file — adopt it.
        echo "$found_serena" > "$PID_FILE"
        ok "Serena daemon already running (PID $found_serena)"
        exit 0
      fi
      fail "port $PORT in use by another process"
      exit 1
    fi
  elif command -v ss >/dev/null 2>&1; then
    # Linux fallback: detect occupancy only (cannot identify the process).
    if ss -tlnp "sport = :$PORT" 2>/dev/null | grep -q "$PORT"; then
      fail "port $PORT in use by another process"
      exit 1
    fi
  fi

  # 3. uvx availability.
  if ! command -v uvx >/dev/null 2>&1; then
    fail "uvx not found. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
  fi

  # 4. Launch detached.
  nohup uvx serena-mcp start-mcp-server \
    --transport streamable-http \
    --port "$PORT" \
    >> "$LOG_FILE" 2>&1 &
  local daemon_pid=$!

  # 5. Record PID.
  echo "$daemon_pid" > "$PID_FILE"

  # 6. Verify startup.
  sleep 2
  if kill -0 "$daemon_pid" 2>/dev/null; then
    ok "Serena daemon started (PID $daemon_pid). Log: $LOG_FILE"
    exit 0
  else
    rm -f "$PID_FILE"
    fail "Serena daemon failed to start. Check log: $LOG_FILE"
    exit 1
  fi
}

# ── stop ──────────────────────────────────────────────────────────────────────
cmd_stop() {
  if [ ! -f "$PID_FILE" ]; then
    warn "Serena daemon is not running (no PID file)"
    exit 0
  fi

  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"

  if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    warn "PID ${pid:-?} is not running (stale PID file)"
    rm -f "$PID_FILE"
    exit 0
  fi

  # Graceful SIGTERM, wait up to 10s, then SIGKILL fallback.
  kill -TERM "$pid" 2>/dev/null || true
  local i
  for i in $(seq 1 10); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done

  if kill -0 "$pid" 2>/dev/null; then
    kill -KILL "$pid" 2>/dev/null || true
  fi

  rm -f "$PID_FILE"
  ok "Serena daemon stopped."
  exit 0
}

# ── status ────────────────────────────────────────────────────────────────────
cmd_status() {
  if [ ! -f "$PID_FILE" ]; then
    info "Serena daemon: stopped"
    exit 1
  fi

  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"

  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    ok "Serena daemon: running (PID $pid)"
    exit 0
  else
    warn "Serena daemon: stopped (stale PID file removed)"
    rm -f "$PID_FILE"
    exit 1
  fi
}

# ── install-service ───────────────────────────────────────────────────────────
cmd_install_service() {
  local os
  os="$(uname)"

  local uvx_path
  uvx_path="$(command -v uvx || true)"
  if [ -z "$uvx_path" ]; then
    fail "uvx not found"
    exit 1
  fi

  case "$os" in
    Darwin)
      mkdir -p "$HOME/Library/LaunchAgents"
      cat > "$PLIST_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.codsworth.serena</string>
  <key>ProgramArguments</key>
  <array>
    <string>$uvx_path</string>
    <string>serena-mcp</string>
    <string>start-mcp-server</string>
    <string>--transport</string>
    <string>streamable-http</string>
    <string>--port</string>
    <string>$PORT</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$HOME/.serena-daemon.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/.serena-daemon.log</string>
</dict>
</plist>
EOF
      launchctl unload "$PLIST_FILE" 2>/dev/null || true
      launchctl load "$PLIST_FILE"
      ok "Serena service installed and loaded (macOS launchd). Daemon will start at login."
      exit 0
      ;;
    Linux)
      mkdir -p "$HOME/.config/systemd/user"
      cat > "$SYSTEMD_FILE" << EOF
[Unit]
Description=Serena MCP HTTP Daemon (codsworth-marketplace)
After=network.target

[Service]
Type=simple
ExecStart=$uvx_path serena-mcp start-mcp-server --transport streamable-http --port $PORT
Restart=on-failure
RestartSec=5
StandardOutput=append:%h/.serena-daemon.log
StandardError=append:%h/.serena-daemon.log

[Install]
WantedBy=default.target
EOF
      systemctl --user daemon-reload 2>/dev/null || true
      systemctl --user enable --now serena-daemon.service
      ok "Serena service installed and enabled (Linux systemd). Daemon will start at login."
      exit 0
      ;;
    *)
      fail "unsupported OS: $os"
      exit 1
      ;;
  esac
}

# ── uninstall-service ─────────────────────────────────────────────────────────
cmd_uninstall_service() {
  local os
  os="$(uname)"

  case "$os" in
    Darwin)
      launchctl unload "$PLIST_FILE" 2>/dev/null || true
      rm -f "$PLIST_FILE"
      ok "Serena service uninstalled (macOS launchd)."
      exit 0
      ;;
    Linux)
      systemctl --user disable --now serena-daemon.service 2>/dev/null || true
      rm -f "$SYSTEMD_FILE"
      ok "Serena service uninstalled (Linux systemd)."
      exit 0
      ;;
    *)
      fail "unsupported OS: $os"
      exit 1
      ;;
  esac
}

# ── usage ─────────────────────────────────────────────────────────────────────
usage() {
  cat << EOF
Usage: serena-daemon.sh <subcommand>

Subcommands:
  start              Start the Serena MCP HTTP daemon (idempotent)
  stop               Stop the Serena MCP HTTP daemon
  status             Report daemon status and PID
  restart            Stop then start
  install-service    Install OS service (launchd on macOS, systemd on Linux)
  uninstall-service  Remove OS service

Daemon command: uvx serena-mcp start-mcp-server --transport streamable-http --port 9121
PID file:       ~/.serena-daemon.pid
Log file:       ~/.serena-daemon.log
Port:           9121
EOF
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
case "${1:-}" in
  start)             cmd_start ;;
  stop)              cmd_stop ;;
  status)            cmd_status ;;
  restart)           "$0" stop; "$0" start ;;
  install-service)   cmd_install_service ;;
  uninstall-service) cmd_uninstall_service ;;
  *)                 usage; exit 1 ;;
esac
