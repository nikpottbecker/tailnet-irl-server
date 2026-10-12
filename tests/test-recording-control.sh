#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_DIR="$(mktemp -d /tmp/irl-recording-test.XXXXXX)"
trap 'rm -rf -- "$TEST_DIR"' EXIT
mkdir -p "$TEST_DIR/config" "$TEST_DIR/state"
cp "$SOURCE_DIR/recording.env.example" "$TEST_DIR/config/recording.env"

run_control() {
  IRL_CONFIG_DIR="$TEST_DIR/config" IRL_STATE_DIR="$TEST_DIR/state" \
    IRL_SKIP_RESTART=1 "$SOURCE_DIR/recording.sh" "$1"
}

run_control enable >/dev/null
grep -Fxq 'RECORDING_ENABLED=true' "$TEST_DIR/config/recording.env"
STATUS_OUTPUT="$(run_control status)"
grep -Fq 'Recording: true' <<< "$STATUS_OUTPUT"

mkdir -p "$TEST_DIR/state/recordings/live"
touch "$TEST_DIR/state/recordings/live/test.mp4"
LIST_OUTPUT="$(run_control list)"
grep -Fq 'test.mp4' <<< "$LIST_OUTPUT"

run_control disable >/dev/null
grep -Fxq 'RECORDING_ENABLED=false' "$TEST_DIR/config/recording.env"
test -f "$TEST_DIR/state/recordings/live/test.mp4"

echo "OK: Recording sicher aktiviert, aufgelistet und deaktiviert"
