#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TEMP_DIR="$(mktemp -d /tmp/irl-serverctl-test.XXXXXX)"
trap 'rm -rf -- "$TEMP_DIR"' EXIT

printf '1.3.0\n' > "$TEMP_DIR/VERSION"
printf '{"tag_name":"v1.4.0"}\n' > "$TEMP_DIR/latest.json"

OUTPUT="$(
  IRL_VERSION_FILE="$TEMP_DIR/VERSION" \
  IRL_RELEASE_API="file://$TEMP_DIR/latest.json" \
  "$SOURCE_DIR/irl-serverctl" check-update
)"
grep -Fq 'Update verfügbar: 1.3.0 -> 1.4.0' <<<"$OUTPUT"

printf '{"tag_name":"v1.3.0"}\n' > "$TEMP_DIR/latest.json"
OUTPUT="$(
  IRL_VERSION_FILE="$TEMP_DIR/VERSION" \
  IRL_RELEASE_API="file://$TEMP_DIR/latest.json" \
  "$SOURCE_DIR/irl-serverctl" check-update
)"
[[ "$OUTPUT" == 'Aktuell: 1.3.0' ]]

IRL_VERSION_FILE="$TEMP_DIR/VERSION" "$SOURCE_DIR/irl-serverctl" version | grep -Fq 'Tailnet IRL Server 1.3.0'
"$SOURCE_DIR/irl-serverctl" help | grep -Fq 'check-update'

mkdir -p "$TEMP_DIR/config" "$TEMP_DIR/state" "$TEMP_DIR/bin"
cp "$SOURCE_DIR/VERSION" "$TEMP_DIR/VERSION"
cat > "$TEMP_DIR/config/credentials.env" <<'EOF'
PUBLISH_PASSWORD=publisher_secret_1234567890
READ_PASSWORD=reader_secret_12345678901234
EOF
if [[ "$(uname -s)" == Darwin ]]; then
  chmod 600 "$TEMP_DIR/config/credentials.env"
else
  chmod 640 "$TEMP_DIR/config/credentials.env"
fi
cat > "$TEMP_DIR/state/mediamtx.yml" <<'EOF'
rtspAddress: 100.64.1.2:8554
rtmpAddress: 100.64.1.2:1935
hlsAddress: 100.64.1.2:8888
webrtcAddress: 100.64.1.2:8889
webrtcLocalUDPAddress: 100.64.1.2:8189
srtAddress: 100.64.1.2:8890
EOF
cat > "$TEMP_DIR/bin/tailscale" <<'EOF'
#!/usr/bin/env bash
[[ "${1:-}" == ip && "${2:-}" == -4 ]] || exit 2
echo 100.64.1.2
EOF
cat > "$TEMP_DIR/bin/curl" <<'EOF'
#!/usr/bin/env bash
printf '{"online":true,"ready":false,"storage":{"available":true,"level":"%s"}}\n' "${DOCTOR_STORAGE_LEVEL:-ok}"
EOF
cat > "$TEMP_DIR/bin/services" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$TEMP_DIR/bin/tailscale" "$TEMP_DIR/bin/curl" "$TEMP_DIR/bin/services"

DOCTOR_ENV=(
  IRL_VERSION_FILE="$TEMP_DIR/VERSION"
  IRL_BASE_DIR="$TEMP_DIR"
  IRL_CONFIG_DIR="$TEMP_DIR/config"
  IRL_STATE_DIR="$TEMP_DIR/state"
  IRL_TAILSCALE_BIN="$TEMP_DIR/bin/tailscale"
  IRL_CURL_BIN="$TEMP_DIR/bin/curl"
  IRL_SYSTEMCTL_BIN="$TEMP_DIR/bin/services"
  IRL_LAUNCHCTL_BIN="$TEMP_DIR/bin/services"
)
DOCTOR_OUTPUT="$(env "${DOCTOR_ENV[@]}" "$SOURCE_DIR/irl-serverctl" doctor)"
grep -Fq 'Medienports ausschließlich an die aktuelle Tailscale-IP gebunden' <<< "$DOCTOR_OUTPUT"
grep -Fq 'Ergebnis: 9 OK · 0 Warnungen · 0 Fehler' <<< "$DOCTOR_OUTPUT"
grep -Fxq 'BEREIT' <<< "$DOCTOR_OUTPUT"

WARNING_OUTPUT="$(env "${DOCTOR_ENV[@]}" DOCTOR_STORAGE_LEVEL=warning "$SOURCE_DIR/irl-serverctl" doctor)"
grep -Fq 'Speicherplatz knapp' <<< "$WARNING_OUTPUT"
grep -Fq 'Ergebnis: 8 OK · 1 Warnungen · 0 Fehler' <<< "$WARNING_OUTPUT"
grep -Fxq 'BEREIT MIT WARNUNG' <<< "$WARNING_OUTPUT"

if env "${DOCTOR_ENV[@]}" DOCTOR_STORAGE_LEVEL=critical "$SOURCE_DIR/irl-serverctl" doctor > "$TEMP_DIR/doctor-critical.out" 2>&1; then
  echo "Doctor akzeptierte kritischen Speicherplatz unerwartet." >&2
  exit 1
fi
grep -Fq 'Speicherplatz kritisch' "$TEMP_DIR/doctor-critical.out"
grep -Fxq 'NICHT BEREIT' "$TEMP_DIR/doctor-critical.out"

sed -i.bak 's/srtAddress: 100.64.1.2:8890/srtAddress: 0.0.0.0:8890/' "$TEMP_DIR/state/mediamtx.yml"
rm -f "$TEMP_DIR/state/mediamtx.yml.bak"
if env "${DOCTOR_ENV[@]}" "$SOURCE_DIR/irl-serverctl" doctor > "$TEMP_DIR/doctor-failure.out" 2>&1; then
  echo "Doctor akzeptierte eine öffentliche SRT-Bindung unerwartet." >&2
  exit 1
fi
grep -Fq 'NICHT BEREIT' "$TEMP_DIR/doctor-failure.out"
grep -Fq 'MediaMTX-Konfiguration passt nicht vollständig' "$TEMP_DIR/doctor-failure.out"

echo "irl-serverctl-Test erfolgreich."
