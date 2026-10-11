#!/usr/bin/env bash
set -euo pipefail

[[ "${EUID:-$(id -u)}" -eq 0 ]] || { echo "Bitte mit sudo ausführen." >&2; exit 1; }

systemctl disable --now irl-dashboard.service irl-mediamtx.service 2>/dev/null || true
rm -f /etc/systemd/system/irl-dashboard.service /etc/systemd/system/irl-mediamtx.service
systemctl daemon-reload

# Konfiguration und Passwörter bleiben absichtlich erhalten, damit eine
# Neuinstallation dieselben Moblin-/OBS-Links weiterverwenden kann.
rm -rf /opt/irl-server
rm -f /usr/local/bin/mediamtx

echo "Dienste und Programmdateien wurden entfernt."
echo "Erhalten: /etc/irl-server und /var/lib/irl-server"
echo "Tailscale wurde nicht deinstalliert."
