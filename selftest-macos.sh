#!/usr/bin/env bash
set -euo pipefail

TAILSCALE_BIN=/Applications/Tailscale.app/Contents/MacOS/Tailscale
DOMAIN="gui/$(id -u)"

fail() { echo "NICHT OK: $*" >&2; exit 1; }
pass() { echo "OK: $*"; }
is_tailscale_ipv4() {
  /usr/bin/python3 -c 'import ipaddress, sys; raise SystemExit(ipaddress.ip_address(sys.argv[1]) not in ipaddress.ip_network("100.64.0.0/10"))' "$1" 2>/dev/null
}

[[ -x "$TAILSCALE_BIN" ]] || fail "Tailscale-App fehlt"
IP="$("$TAILSCALE_BIN" ip -4 2>/dev/null | head -n 1)"
is_tailscale_ipv4 "$IP" || fail "Tailscale ist nicht verbunden"
pass "Tailscale aktiv ($IP)"

MEDIA_STATE="$(launchctl print "$DOMAIN/com.nik.irl-mediamtx" 2>/dev/null | awk '/state =/{print $3; exit}')"
DASHBOARD_STATE="$(launchctl print "$DOMAIN/com.nik.irl-dashboard" 2>/dev/null | awk '/state =/{print $3; exit}')"
[[ "$MEDIA_STATE" == running ]] || fail "MediaMTX-LaunchAgent läuft nicht"
[[ "$DASHBOARD_STATE" == running ]] || fail "Dashboard-LaunchAgent läuft nicht"
pass "beide LaunchAgents laufen"

JSON="$(curl -fsS --max-time 2 "http://$IP:8090/healthz")" || fail "Dashboard nicht erreichbar"
python3 -c 'import json,sys; assert json.load(sys.stdin)["online"] is True' <<<"$JSON" || fail "MediaMTX-API nicht bereit"
pass "Dashboard und MediaMTX-API bereit"

lsof -nP -a -c mediamtx -iUDP@"$IP":8890 | grep -q mediamtx || fail "SRT lauscht nicht auf der Tailscale-IP"
if lsof -nP -a -c mediamtx -iUDP:8890 | grep -Eq '(\*|0\.0\.0\.0):8890'; then
  fail "SRT lauscht unerwartet auf allen Interfaces"
fi
pass "SRT ausschließlich an Tailscale gebunden"

echo "Dashboard: http://$IP:8090"
