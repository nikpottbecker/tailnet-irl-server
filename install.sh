#!/usr/bin/env bash
set -euo pipefail

MEDIAMTX_VERSION="${MEDIAMTX_VERSION:-1.21.2}"
INSTALL_DIR="/opt/irl-server"
CONFIG_DIR="/etc/irl-server"
STATE_DIR="/var/lib/irl-server"
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

die() {
  echo "Fehler: $*" >&2
  exit 1
}

[[ "$(uname -s)" == "Linux" ]] || die "Der Server-Installer unterstützt Debian/Ubuntu Linux."
[[ "${EUID:-$(id -u)}" -eq 0 ]] || die "Bitte mit sudo ausführen: sudo ./install.sh"
command -v systemctl >/dev/null 2>&1 || die "systemd wurde nicht gefunden."
command -v openssl >/dev/null 2>&1 || die "openssl wurde nicht gefunden."
command -v python3 >/dev/null 2>&1 || die "python3 wurde nicht gefunden."

if ! command -v curl >/dev/null 2>&1; then
  apt-get update
  apt-get install -y curl ca-certificates
fi

if ! command -v tailscale >/dev/null 2>&1; then
  echo "Installiere Tailscale aus dem offiziellen Paket-Installer …"
  curl -fsSL https://tailscale.com/install.sh | sh
fi

systemctl enable --now tailscaled
if ! tailscale ip -4 >/dev/null 2>&1; then
  echo "Tailscale ist noch nicht verbunden. Öffne gleich den angezeigten Login-Link."
  tailscale up --hostname=irl-server
fi
TAILSCALE_IP="$(tailscale ip -4 | head -n 1)"
[[ "$TAILSCALE_IP" =~ ^100\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]] || die "Keine aktive Tailscale-IP gefunden."

case "$(uname -m)" in
  x86_64|amd64) ARCH="amd64" ;;
  aarch64|arm64) ARCH="arm64" ;;
  armv7l) ARCH="armv7" ;;
  *) die "Nicht unterstützte CPU-Architektur: $(uname -m)" ;;
esac

ARCHIVE="mediamtx_v${MEDIAMTX_VERSION}_linux_${ARCH}.tar.gz"
BASE_URL="https://github.com/bluenviron/mediamtx/releases/download/v${MEDIAMTX_VERSION}"
TEMP_DIR="$(mktemp -d /tmp/irl-server-install.XXXXXX)"
trap 'rm -rf -- "$TEMP_DIR"' EXIT

echo "Lade MediaMTX v${MEDIAMTX_VERSION} und prüfe die offizielle SHA-256-Summe …"
curl -fL "$BASE_URL/$ARCHIVE" -o "$TEMP_DIR/$ARCHIVE"
curl -fL "$BASE_URL/checksums.sha256" -o "$TEMP_DIR/checksums.sha256"
EXPECTED="$(awk -v file="$ARCHIVE" '{ name=$2; sub(/^\*/, "", name); if (name == file) print $1 }' "$TEMP_DIR/checksums.sha256")"
[[ "$EXPECTED" =~ ^[a-f0-9]{64}$ ]] || die "Keine offizielle Prüfsumme für $ARCHIVE gefunden."
ACTUAL="$(sha256sum "$TEMP_DIR/$ARCHIVE" | awk '{print $1}')"
[[ "$ACTUAL" == "$EXPECTED" ]] || die "MediaMTX-Prüfsumme stimmt nicht."
tar -xzf "$TEMP_DIR/$ARCHIVE" -C "$TEMP_DIR" mediamtx
install -m 0755 "$TEMP_DIR/mediamtx" /usr/local/bin/mediamtx

if ! id irl-server >/dev/null 2>&1; then
  useradd --system --home-dir "$STATE_DIR" --shell /usr/sbin/nologin irl-server
fi
install -d -o root -g irl-server -m 0750 "$CONFIG_DIR"
install -d -o irl-server -g irl-server -m 0750 "$STATE_DIR"
install -d -o root -g root -m 0755 "$INSTALL_DIR"

install -m 0755 "$SOURCE_DIR/start-mediamtx.sh" "$INSTALL_DIR/start-mediamtx.sh"
install -m 0755 "$SOURCE_DIR/status_server.py" "$INSTALL_DIR/status_server.py"
install -m 0640 -o root -g irl-server "$SOURCE_DIR/mediamtx.template.yml" "$CONFIG_DIR/mediamtx.template.yml"

if [[ ! -f "$CONFIG_DIR/credentials.env" ]]; then
  umask 0077
  PUBLISH_PASSWORD="$(openssl rand -hex 24)"
  READ_PASSWORD="$(openssl rand -hex 24)"
  {
    printf 'PUBLISH_PASSWORD=%s\n' "$PUBLISH_PASSWORD"
    printf 'READ_PASSWORD=%s\n' "$READ_PASSWORD"
  } > "$CONFIG_DIR/credentials.env"
fi
chown root:irl-server "$CONFIG_DIR/credentials.env"
chmod 0640 "$CONFIG_DIR/credentials.env"

install -m 0644 "$SOURCE_DIR/systemd/irl-mediamtx.service" /etc/systemd/system/irl-mediamtx.service
install -m 0644 "$SOURCE_DIR/systemd/irl-dashboard.service" /etc/systemd/system/irl-dashboard.service
systemctl daemon-reload
systemctl enable --now irl-mediamtx.service irl-dashboard.service

for _ in {1..20}; do
  if curl -fsS --max-time 1 "http://$TAILSCALE_IP:8090/healthz" >/dev/null; then
    break
  fi
  sleep 0.5
done

if ! systemctl is-active --quiet irl-mediamtx.service; then
  journalctl -u irl-mediamtx.service -n 30 --no-pager >&2
  die "Der Media-Dienst ist nicht gestartet."
fi
if ! systemctl is-active --quiet irl-dashboard.service; then
  journalctl -u irl-dashboard.service -n 30 --no-pager >&2
  die "Das Dashboard ist nicht gestartet."
fi

echo
echo "IRL Server ist fertig."
echo "Dashboard: http://$TAILSCALE_IP:8090"
echo "Öffne diese Adresse auf dem iPhone oder PC, während Tailscale verbunden ist."
echo "Passwörter: $CONFIG_DIR/credentials.env (werden bei Updates beibehalten)"
