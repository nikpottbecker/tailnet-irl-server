#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR="${IRL_CONFIG_DIR:-/etc/irl-server}"
STATE_DIR="${IRL_STATE_DIR:-/var/lib/irl-server}"
TEMPLATE="${IRL_TEMPLATE:-$CONFIG_DIR/mediamtx.template.yml}"
CREDENTIALS="${IRL_CREDENTIALS:-$CONFIG_DIR/credentials.env}"
OUTPUT="$STATE_DIR/mediamtx.yml"

die() {
  echo "irl-server: $*" >&2
  exit 1
}

is_tailscale_ipv4() {
  python3 -c 'import ipaddress, sys; raise SystemExit(ipaddress.ip_address(sys.argv[1]) not in ipaddress.ip_network("100.64.0.0/10"))' "$1" 2>/dev/null
}

if [[ -n "${TAILSCALE_BIN:-}" ]]; then
  :
elif command -v tailscale >/dev/null 2>&1; then
  TAILSCALE_BIN="$(command -v tailscale)"
elif [[ -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ]]; then
  TAILSCALE_BIN=/Applications/Tailscale.app/Contents/MacOS/Tailscale
else
  die "tailscale command not found"
fi
MEDIAMTX_BIN="${MEDIAMTX_BIN:-/usr/local/bin/mediamtx}"
[[ -x "$MEDIAMTX_BIN" ]] || die "MediaMTX binary is not executable: $MEDIAMTX_BIN"
[[ -r "$TEMPLATE" ]] || die "configuration template is not readable: $TEMPLATE"
[[ -r "$CREDENTIALS" ]] || die "credentials file is not readable: $CREDENTIALS"

# credentials.env is generated locally by install.sh and contains only shell-safe
# alphanumeric secrets. It is never printed by this launcher.
# shellcheck disable=SC1090
source "$CREDENTIALS"
[[ "${PUBLISH_PASSWORD:-}" =~ ^[A-Za-z0-9_-]{20,}$ ]] || die "invalid publisher credential"
[[ "${READ_PASSWORD:-}" =~ ^[A-Za-z0-9_-]{20,}$ ]] || die "invalid reader credential"

TAILSCALE_IP="${TAILSCALE_IP:-$("$TAILSCALE_BIN" ip -4 2>/dev/null | head -n 1)}"
is_tailscale_ipv4 "$TAILSCALE_IP" || die "no active Tailscale IPv4 address"

PUBLISH_SHA256="$(printf '%s' "$PUBLISH_PASSWORD" | openssl dgst -binary -sha256 | openssl base64 -A)"
READ_SHA256="$(printf '%s' "$READ_PASSWORD" | openssl dgst -binary -sha256 | openssl base64 -A)"

mkdir -p "$STATE_DIR"
sed \
  -e "s/__TAILSCALE_IP__/$TAILSCALE_IP/g" \
  -e "s|__PUBLISH_SHA256__|$PUBLISH_SHA256|g" \
  -e "s|__READ_SHA256__|$READ_SHA256|g" \
  "$TEMPLATE" > "$OUTPUT.tmp"
chmod 0600 "$OUTPUT.tmp"
mv "$OUTPUT.tmp" "$OUTPUT"

exec "$MEDIAMTX_BIN" "$OUTPUT"
