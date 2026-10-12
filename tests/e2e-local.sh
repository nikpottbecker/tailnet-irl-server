#!/usr/bin/env bash
set -euo pipefail

VERSION="${MEDIAMTX_VERSION:-1.21.2}"
TEST_DIR="$(mktemp -d /tmp/irl-e2e.XXXXXX)"
MTX_PID=""
PUB_PID=""

cleanup() {
  [[ -z "$PUB_PID" ]] || kill "$PUB_PID" 2>/dev/null || true
  [[ -z "$MTX_PID" ]] || kill "$MTX_PID" 2>/dev/null || true
}
trap cleanup EXIT

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) PLATFORM="darwin_arm64"; HASH_CMD=(shasum -a 256) ;;
  Darwin-x86_64) PLATFORM="darwin_amd64"; HASH_CMD=(shasum -a 256) ;;
  Linux-x86_64) PLATFORM="linux_amd64"; HASH_CMD=(sha256sum) ;;
  Linux-aarch64) PLATFORM="linux_arm64"; HASH_CMD=(sha256sum) ;;
  *) echo "Unsupported test platform" >&2; exit 1 ;;
esac

ARCHIVE="mediamtx_v${VERSION}_${PLATFORM}.tar.gz"
BASE="https://github.com/bluenviron/mediamtx/releases/download/v${VERSION}"
curl -fsSL "$BASE/$ARCHIVE" -o "$TEST_DIR/$ARCHIVE"
curl -fsSL "$BASE/checksums.sha256" -o "$TEST_DIR/checksums.sha256"
EXPECTED="$(awk -v file="$ARCHIVE" '{ name=$2; sub(/^\*/, "", name); if (name == file) print $1 }' "$TEST_DIR/checksums.sha256")"
ACTUAL="$("${HASH_CMD[@]}" "$TEST_DIR/$ARCHIVE" | awk '{print $1}')"
[[ "$EXPECTED" == "$ACTUAL" ]] || { echo "Checksum mismatch" >&2; exit 1; }
tar -xzf "$TEST_DIR/$ARCHIVE" -C "$TEST_DIR" mediamtx

PUBLISH_PASSWORD="publishsecret123456789012345678"
READ_PASSWORD="readsecret12345678901234567890"
PUBLISH_HASH="$(printf '%s' "$PUBLISH_PASSWORD" | openssl dgst -binary -sha256 | openssl base64 -A)"
READ_HASH="$(printf '%s' "$READ_PASSWORD" | openssl dgst -binary -sha256 | openssl base64 -A)"
sed \
  -e 's/__TAILSCALE_IP__/127.0.0.1/g' \
  -e 's/127.0.0.1:9997/127.0.0.1:19997/g' \
  -e 's/127.0.0.1:9998/127.0.0.1:19998/g' \
  -e "s|__PUBLISH_SHA256__|$PUBLISH_HASH|g" \
  -e "s|__READ_SHA256__|$READ_HASH|g" \
  -e 's|__RECORDING_ENABLED__|true|g' \
  -e "s|__RECORDING_PATH__|$TEST_DIR/recordings|g" \
  -e 's|__RECORDING_FORMAT__|fmp4|g' \
  -e 's|__RECORDING_SEGMENT_DURATION__|2s|g' \
  -e 's|__RECORDING_DELETE_AFTER__|0s|g' \
  mediamtx.template.yml > "$TEST_DIR/mediamtx.yml"

"$TEST_DIR/mediamtx" "$TEST_DIR/mediamtx.yml" >"$TEST_DIR/mediamtx.log" 2>&1 &
MTX_PID="$!"
for _ in {1..30}; do
  curl -fsS http://127.0.0.1:19997/v3/info >/dev/null 2>&1 && break
  sleep 0.2
done
curl -fsS http://127.0.0.1:19997/v3/info >/dev/null

ffmpeg -hide_banner -loglevel error -re \
  -f lavfi -i testsrc2=size=640x360:rate=25 \
  -f lavfi -i sine=frequency=1000:sample_rate=48000 \
  -t 6 -c:v libx264 -preset ultrafast -tune zerolatency -g 50 \
  -c:a aac -f mpegts \
  "srt://127.0.0.1:8890?streamid=publish:live:mobile:${PUBLISH_PASSWORD}&pkt_size=1316" \
  >"$TEST_DIR/publisher.log" 2>&1 &
PUB_PID="$!"

for _ in {1..30}; do
  STATE="$(curl -fsS http://127.0.0.1:19997/v3/paths/get/live 2>/dev/null || true)"
  [[ "$STATE" == *'"ready":true'* ]] && break
  sleep 0.2
done
[[ "$STATE" == *'"ready":true'* ]] || { cat "$TEST_DIR/mediamtx.log" >&2; exit 1; }

ffprobe -v error -show_entries stream=codec_name,codec_type -of json \
  "srt://127.0.0.1:8890?streamid=read:live:studio:${READ_PASSWORD}&pkt_size=1316" \
  > "$TEST_DIR/probe.json"
grep -q '"codec_name": "h264"' "$TEST_DIR/probe.json"
grep -q '"codec_name": "aac"' "$TEST_DIR/probe.json"

wait "$PUB_PID"
PUB_PID=""
for _ in {1..20}; do
  RECORDING="$(find "$TEST_DIR/recordings" -type f -name '*.mp4' -size +0c -print -quit 2>/dev/null || true)"
  [[ -n "$RECORDING" ]] && break
  sleep 0.2
done
[[ -n "$RECORDING" ]] || { cat "$TEST_DIR/mediamtx.log" >&2; exit 1; }

echo "OK: authenticated SRT publish/read and fMP4 recording with H.264/AAC"
cat "$TEST_DIR/probe.json"
echo "Test artifacts: $TEST_DIR"
