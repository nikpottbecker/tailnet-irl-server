#!/usr/bin/env bash
set -euo pipefail

die() {
  echo "Fehler: $*" >&2
  exit 1
}

usage() {
  echo "Verwendung: $0 --yes"
  echo "Erzeugt neue Publisher- und Leser-Zugangsdaten und startet die Dienste neu."
}

[[ "${1:-}" == "--yes" && $# -eq 1 ]] || {
  usage >&2
  exit 2
}
command -v openssl >/dev/null 2>&1 || die "openssl wurde nicht gefunden."

case "$(uname -s)" in
  Darwin)
    CONFIG_DIR="${IRL_CONFIG_DIR:-$HOME/Library/Application Support/IRL Server/config}"
    MODE=0600
    ;;
  Linux)
    CONFIG_DIR="${IRL_CONFIG_DIR:-/etc/irl-server}"
    MODE=0640
    if [[ "${IRL_SKIP_RESTART:-0}" != 1 && "${EUID:-$(id -u)}" -ne 0 ]]; then
      die "Bitte mit sudo ausführen: sudo $0 --yes"
    fi
    ;;
  *)
    die "Nicht unterstütztes Betriebssystem: $(uname -s)"
    ;;
esac

[[ -d "$CONFIG_DIR" ]] || die "Konfigurationsordner nicht gefunden: $CONFIG_DIR"
CREDENTIALS="$CONFIG_DIR/credentials.env"
TEMP_FILE="$(mktemp "$CONFIG_DIR/credentials.env.tmp.XXXXXX")"
trap 'rm -f -- "$TEMP_FILE"' EXIT

umask 0077
{
  printf 'PUBLISH_PASSWORD=%s\n' "$(openssl rand -hex 24)"
  printf 'READ_PASSWORD=%s\n' "$(openssl rand -hex 24)"
} > "$TEMP_FILE"
chmod "$MODE" "$TEMP_FILE"

if [[ "$(uname -s)" == Linux && "${IRL_SKIP_RESTART:-0}" != 1 ]]; then
  chown root:irl-server "$TEMP_FILE"
fi
mv "$TEMP_FILE" "$CREDENTIALS"
trap - EXIT

if [[ "${IRL_SKIP_RESTART:-0}" != 1 ]]; then
  if [[ "$(uname -s)" == Darwin ]]; then
    DOMAIN="gui/$(id -u)"
    launchctl kickstart -k "$DOMAIN/com.nik.irl-mediamtx"
    launchctl kickstart -k "$DOMAIN/com.nik.irl-dashboard"
  else
    systemctl restart irl-mediamtx.service irl-dashboard.service
  fi
fi

echo "Zugangsdaten wurden erneuert."
echo "Moblin neu importieren und die OBS-/VLC-URLs aus dem Dashboard ersetzen."
