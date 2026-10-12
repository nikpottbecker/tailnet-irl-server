#!/usr/bin/env bash
set -euo pipefail

MEDIAMTX_VERSION="${MEDIAMTX_VERSION:-1.21.2}"
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$HOME/Library/Application Support/IRL Server"
INSTALL_DIR="$BASE_DIR/app"
CONFIG_DIR="$BASE_DIR/config"
STATE_DIR="$BASE_DIR/state"
LOG_DIR="$BASE_DIR/logs"
BIN_DIR="$INSTALL_DIR/bin"
AGENT_DIR="$HOME/Library/LaunchAgents"
TAILSCALE_BIN=/Applications/Tailscale.app/Contents/MacOS/Tailscale

die() { echo "Fehler: $*" >&2; exit 1; }
is_tailscale_ipv4() {
  /usr/bin/python3 -c 'import ipaddress, sys; raise SystemExit(ipaddress.ip_address(sys.argv[1]) not in ipaddress.ip_network("100.64.0.0/10"))' "$1" 2>/dev/null
}
[[ "$(uname -s)" == Darwin ]] || die "Dieser Installer ist nur für macOS."
[[ -x "$TAILSCALE_BIN" ]] || die "Die Tailscale-App fehlt unter /Applications."
command -v openssl >/dev/null 2>&1 || die "openssl fehlt."
command -v curl >/dev/null 2>&1 || die "curl fehlt."
[[ -x /usr/bin/python3 ]] || die "Python 3 fehlt. Installiere zuerst die Apple Command Line Tools mit: xcode-select --install"

TAILSCALE_IP="$("$TAILSCALE_BIN" ip -4 2>/dev/null | head -n 1)"
is_tailscale_ipv4 "$TAILSCALE_IP" || die "Tailscale ist nicht verbunden."

case "$(uname -m)" in
  arm64) ARCH=arm64 ;;
  x86_64) ARCH=amd64 ;;
  *) die "Nicht unterstützte Mac-Architektur: $(uname -m)" ;;
esac
ARCHIVE="mediamtx_v${MEDIAMTX_VERSION}_darwin_${ARCH}.tar.gz"
BASE_URL="https://github.com/bluenviron/mediamtx/releases/download/v${MEDIAMTX_VERSION}"
TEMP_DIR="$(mktemp -d /tmp/irl-server-macos.XXXXXX)"
trap 'rm -rf -- "$TEMP_DIR"' EXIT

mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$STATE_DIR" "$LOG_DIR" "$BIN_DIR" "$AGENT_DIR"
curl -fsSL "$BASE_URL/$ARCHIVE" -o "$TEMP_DIR/$ARCHIVE"
curl -fsSL "$BASE_URL/checksums.sha256" -o "$TEMP_DIR/checksums.sha256"
EXPECTED="$(awk -v file="$ARCHIVE" '{ name=$2; sub(/^\*/, "", name); if (name == file) print $1 }' "$TEMP_DIR/checksums.sha256")"
ACTUAL="$(shasum -a 256 "$TEMP_DIR/$ARCHIVE" | awk '{print $1}')"
[[ "$EXPECTED" =~ ^[a-f0-9]{64}$ && "$EXPECTED" == "$ACTUAL" ]] || die "MediaMTX-Prüfsumme stimmt nicht."
tar -xzf "$TEMP_DIR/$ARCHIVE" -C "$TEMP_DIR" mediamtx

install -m 0755 "$TEMP_DIR/mediamtx" "$BIN_DIR/mediamtx"
install -m 0755 "$SOURCE_DIR/start-mediamtx.sh" "$INSTALL_DIR/start-mediamtx.sh"
install -m 0755 "$SOURCE_DIR/status_server.py" "$INSTALL_DIR/status_server.py"
install -m 0755 "$SOURCE_DIR/rotate-credentials.sh" "$INSTALL_DIR/rotate-credentials.sh"
install -m 0755 "$SOURCE_DIR/recording.sh" "$INSTALL_DIR/recording.sh"
install -m 0755 "$SOURCE_DIR/irl-serverctl" "$INSTALL_DIR/irl-serverctl"
install -m 0644 "$SOURCE_DIR/VERSION" "$INSTALL_DIR/VERSION"
install -m 0600 "$SOURCE_DIR/mediamtx.template.yml" "$CONFIG_DIR/mediamtx.template.yml"
if [[ ! -f "$CONFIG_DIR/profile.env" ]]; then
  install -m 0600 "$SOURCE_DIR/profile.env.example" "$CONFIG_DIR/profile.env"
fi
if [[ ! -f "$CONFIG_DIR/recording.env" ]]; then
  install -m 0600 "$SOURCE_DIR/recording.env.example" "$CONFIG_DIR/recording.env"
fi

if [[ ! -f "$CONFIG_DIR/credentials.env" ]]; then
  umask 0077
  {
    printf 'PUBLISH_PASSWORD=%s\n' "$(openssl rand -hex 24)"
    printf 'READ_PASSWORD=%s\n' "$(openssl rand -hex 24)"
  } > "$CONFIG_DIR/credentials.env"
fi
chmod 0600 "$CONFIG_DIR/credentials.env"

render_plist() {
  local source="$1" target="$2"
  sed \
    -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
    -e "s|__CONFIG_DIR__|$CONFIG_DIR|g" \
    -e "s|__STATE_DIR__|$STATE_DIR|g" \
    -e "s|__LOG_DIR__|$LOG_DIR|g" \
    -e "s|__TAILSCALE_IP__|$TAILSCALE_IP|g" \
    "$source" > "$target.tmp"
  plutil -lint "$target.tmp" >/dev/null
  mv "$target.tmp" "$target"
  chmod 0600 "$target"
}

MEDIA_PLIST="$AGENT_DIR/com.nik.irl-mediamtx.plist"
DASHBOARD_PLIST="$AGENT_DIR/com.nik.irl-dashboard.plist"
render_plist "$SOURCE_DIR/launchd/com.nik.irl-mediamtx.plist.template" "$MEDIA_PLIST"
render_plist "$SOURCE_DIR/launchd/com.nik.irl-dashboard.plist.template" "$DASHBOARD_PLIST"

DOMAIN="gui/$(id -u)"

reload_agent() {
  local label="$1" plist="$2"
  launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
  for _ in {1..20}; do
    launchctl print "$DOMAIN/$label" >/dev/null 2>&1 || break
    sleep 0.1
  done
  for _ in {1..5}; do
    if launchctl bootstrap "$DOMAIN" "$plist" 2>/dev/null; then
      return 0
    fi
    sleep 0.25
  done
  die "LaunchAgent konnte nicht geladen werden: $label"
}

reload_agent com.nik.irl-mediamtx "$MEDIA_PLIST"
reload_agent com.nik.irl-dashboard "$DASHBOARD_PLIST"
launchctl kickstart -k "$DOMAIN/com.nik.irl-mediamtx"
launchctl kickstart -k "$DOMAIN/com.nik.irl-dashboard"

for _ in {1..30}; do
  curl -fsS --max-time 1 "http://$TAILSCALE_IP:8090/healthz" >/dev/null 2>&1 && break
  sleep 0.25
done
curl -fsS --max-time 2 "http://$TAILSCALE_IP:8090/healthz" >/dev/null || {
  tail -n 30 "$LOG_DIR/mediamtx-error.log" "$LOG_DIR/dashboard-error.log" >&2 || true
  die "Dashboard ist nicht erreichbar."
}

echo "IRL Server läuft nativ auf diesem Mac."
echo "Dashboard: http://$TAILSCALE_IP:8090"
echo "Verwaltung: \"$INSTALL_DIR/irl-serverctl\" status"
echo "Logs: $LOG_DIR"
