#!/usr/bin/env bash
set -euo pipefail

fail() { echo "NICHT OK: $*" >&2; exit 1; }
pass() { echo "OK: $*"; }
is_tailscale_ipv4() {
  python3 -c 'import ipaddress, sys; raise SystemExit(ipaddress.ip_address(sys.argv[1]) not in ipaddress.ip_network("100.64.0.0/10"))' "$1" 2>/dev/null
}

command -v tailscale >/dev/null 2>&1 || fail "Tailscale fehlt"
IP="$(tailscale ip -4 2>/dev/null | head -n 1)"
is_tailscale_ipv4 "$IP" || fail "Tailscale ist nicht verbunden"
pass "Tailscale aktiv ($IP)"

systemctl is-active --quiet irl-mediamtx.service || fail "irl-mediamtx ist nicht aktiv"
systemctl is-active --quiet irl-dashboard.service || fail "irl-dashboard ist nicht aktiv"
pass "beide systemd-Dienste aktiv"

JSON="$(curl -fsS --max-time 2 "http://$IP:8090/healthz")" || fail "Dashboard nicht erreichbar"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["online"] is True' <<<"$JSON" || fail "MediaMTX-API nicht bereit"
pass "Dashboard und MediaMTX-API bereit"

ss -lun | grep -Fq "$IP:8890" || fail "SRT lauscht nicht auf der Tailscale-IP"
if ss -lun | grep -Eq '(^|[[:space:]])(0\.0\.0\.0|\*):8890([[:space:]]|$)'; then
  fail "SRT lauscht unerwartet auf allen Interfaces"
fi
pass "SRT nur an Tailscale gebunden"

echo "Bereit. Für den vollständigen Videotest Moblin starten und danach den Feed in OBS öffnen."
