#!/usr/bin/env bash
set -euo pipefail

die() {
  echo "Fehler: $*" >&2
  exit 1
}

usage() {
  echo "Verwendung: $0 {enable|disable|status|list}"
}

case "$(uname -s)" in
  Darwin)
    CONFIG_DIR="${IRL_CONFIG_DIR:-$HOME/Library/Application Support/IRL Server/config}"
    STATE_DIR="${IRL_STATE_DIR:-$HOME/Library/Application Support/IRL Server/state}"
    ;;
  Linux)
    CONFIG_DIR="${IRL_CONFIG_DIR:-/etc/irl-server}"
    STATE_DIR="${IRL_STATE_DIR:-/var/lib/irl-server}"
    ;;
  *) die "Nicht unterstütztes Betriebssystem: $(uname -s)" ;;
esac

CONFIG_FILE="$CONFIG_DIR/recording.env"
RECORDING_DIR="${IRL_RECORDING_DIR:-$STATE_DIR/recordings}"
[[ -f "$CONFIG_FILE" ]] || die "Recording-Konfiguration nicht gefunden: $CONFIG_FILE"

value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key {value=substr($0, index($0, "=") + 1)} END {print value}' "$CONFIG_FILE"
}

restart_services() {
  [[ "${IRL_SKIP_RESTART:-0}" == 1 ]] && return 0
  if [[ "$(uname -s)" == Darwin ]]; then
    local domain="gui/$(id -u)"
    launchctl kickstart -k "$domain/com.nik.irl-mediamtx"
    launchctl kickstart -k "$domain/com.nik.irl-dashboard"
  else
    [[ "${EUID:-$(id -u)}" -eq 0 ]] || die "Bitte mit sudo ausführen."
    systemctl restart irl-mediamtx.service irl-dashboard.service
  fi
}

set_enabled() {
  local enabled="$1" temp_file
  if [[ "$(uname -s)" == Linux && "${IRL_SKIP_RESTART:-0}" != 1 ]]; then
    [[ "${EUID:-$(id -u)}" -eq 0 ]] || die "Bitte mit sudo ausführen."
  fi
  temp_file="$(mktemp "$CONFIG_DIR/recording.env.tmp.XXXXXX")"
  trap 'rm -f -- "$temp_file"' EXIT
  awk -F= -v enabled="$enabled" '
    BEGIN {found=0}
    $1 == "RECORDING_ENABLED" {print "RECORDING_ENABLED=" enabled; found=1; next}
    {print}
    END {if (!found) print "RECORDING_ENABLED=" enabled}
  ' "$CONFIG_FILE" > "$temp_file"
  if [[ "$(uname -s)" == Darwin ]]; then
    chmod "$(stat -f '%Lp' "$CONFIG_FILE")" "$temp_file"
  else
    chmod "$(stat -c '%a' "$CONFIG_FILE")" "$temp_file"
  fi
  if [[ "$(uname -s)" == Linux && "${IRL_SKIP_RESTART:-0}" != 1 ]]; then
    chown root:irl-server "$temp_file"
  fi
  mv "$temp_file" "$CONFIG_FILE"
  trap - EXIT
  mkdir -p "$RECORDING_DIR"
  restart_services
}

case "${1:-}" in
  enable)
    set_enabled true
    echo "Recording aktiviert: $RECORDING_DIR"
    ;;
  disable)
    set_enabled false
    echo "Recording deaktiviert. Vorhandene Aufnahmen bleiben erhalten."
    ;;
  status)
    echo "Recording: $(value RECORDING_ENABLED)"
    echo "Format: $(value RECORDING_FORMAT)"
    echo "Segmentdauer: $(value RECORDING_SEGMENT_DURATION)"
    echo "Aufbewahrung: $(value RECORDING_DELETE_AFTER)"
    echo "Ordner: $RECORDING_DIR"
    ;;
  list)
    if [[ -d "$RECORDING_DIR" ]]; then
      find "$RECORDING_DIR" -type f \( -name '*.mp4' -o -name '*.ts' \) -print | sort
    fi
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
