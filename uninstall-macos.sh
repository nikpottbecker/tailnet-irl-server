#!/usr/bin/env bash
set -euo pipefail

DOMAIN="gui/$(id -u)"
AGENT_DIR="$HOME/Library/LaunchAgents"
launchctl bootout "$DOMAIN/com.nik.irl-dashboard" 2>/dev/null || true
launchctl bootout "$DOMAIN/com.nik.irl-mediamtx" 2>/dev/null || true
rm -f "$AGENT_DIR/com.nik.irl-dashboard.plist" "$AGENT_DIR/com.nik.irl-mediamtx.plist"
echo "IRL-LaunchAgents entfernt. Daten bleiben unter ~/Library/Application Support/IRL Server erhalten."
