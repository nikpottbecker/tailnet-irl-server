#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_DIR="$(mktemp -d /tmp/irl-credentials-test.XXXXXX)"
trap 'rm -rf -- "$TEST_DIR"' EXIT

printf 'PUBLISH_PASSWORD=old\nREAD_PASSWORD=old\n' > "$TEST_DIR/credentials.env"
IRL_CONFIG_DIR="$TEST_DIR" IRL_SKIP_RESTART=1 "$SOURCE_DIR/rotate-credentials.sh" --yes >/dev/null

PUBLISH_PASSWORD="$(awk -F= '$1 == "PUBLISH_PASSWORD" {print $2}' "$TEST_DIR/credentials.env")"
READ_PASSWORD="$(awk -F= '$1 == "READ_PASSWORD" {print $2}' "$TEST_DIR/credentials.env")"

[[ "$PUBLISH_PASSWORD" =~ ^[a-f0-9]{48}$ ]]
[[ "$READ_PASSWORD" =~ ^[a-f0-9]{48}$ ]]
[[ "$PUBLISH_PASSWORD" != "$READ_PASSWORD" ]]
[[ "$(wc -l < "$TEST_DIR/credentials.env" | tr -d ' ')" == 2 ]]

case "$(uname -s)" in
  Darwin) PERMISSIONS="$(stat -f '%Lp' "$TEST_DIR/credentials.env")" ;;
  Linux) PERMISSIONS="$(stat -c '%a' "$TEST_DIR/credentials.env")" ;;
esac
[[ "$PERMISSIONS" == 600 || "$PERMISSIONS" == 640 ]]

if IRL_CONFIG_DIR="$TEST_DIR" IRL_SKIP_RESTART=1 "$SOURCE_DIR/rotate-credentials.sh" >/dev/null 2>&1; then
  echo "Rotation ohne --yes wurde unerwartet ausgeführt." >&2
  exit 1
fi

echo "OK: Zugangsdaten atomar erneuert und Dateirechte geprüft"
