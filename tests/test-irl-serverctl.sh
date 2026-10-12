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

echo "irl-serverctl-Test erfolgreich."
