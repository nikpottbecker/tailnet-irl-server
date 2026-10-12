# Changelog

All notable changes to Tailnet IRL Server are documented here.

## Unreleased

## 1.6.0 — 2026-10-12

### Added

- Show cached disk capacity, free space, aggregate recording size and recording count in the dashboard and `irl-serverctl status`.
- Add warning and critical storage levels suitable for long-running recordings.

### Security

- Expose only aggregate storage values through the status API, never recording file names or paths.

## 1.5.0 — 2026-10-12

### Added

- Persist a bounded 30-day stream and media-server connection history in the private state directory.
- Show recent transitions, last-live time, completed stream durations and 24-hour stream-end counts in the dashboard.
- Include the 24-hour stream-end count and last-live timestamp in `irl-serverctl status`.

### Security

- Store no credentials, connection URLs or media details in the connection history.
- Normalize persisted event data before returning it through the status API.
- Grant the hardened Linux dashboard service write access only to `/var/lib/irl-server`.
- Restrict the macOS state directory to the installing user with mode `0700`.

## 1.4.0 — 2026-10-12

### Added

- Add `irl-serverctl` for consolidated status, version, release, restart and recording controls.
- Test the management command on both supported CI operating systems.

## 1.3.0 — 2026-10-12

### Added

- Add optional server-side fMP4/MPEG-TS recording with configurable segments and retention.
- Add `recording.sh` to enable, disable, inspect and list recordings without deleting existing media.
- Verify real fMP4 output in the authenticated SRT end-to-end test.

## 1.2.0 — 2026-10-12

### Added

- Show live input bitrate, stream uptime, media tracks and outbound traffic in the dashboard.
- Add a validated, update-safe `profile.env` for customizing Moblin resolution, frame rate, bitrates and SRT latency.
- Run cross-platform unit, shell and credential checks plus an authenticated SRT end-to-end test in GitHub Actions.
- Add direct WebRTC preview, a branded PWA icon and `/api/version` for installed-version checks.
- Pin CI to Ubuntu 24.04 and Node 24-based official GitHub Actions.

## 1.1.0 — 2026-10-12

### Fixed

- Validate server addresses against Tailscale's complete `100.64.0.0/10` IPv4 range.
- Fail early on macOS when the Python 3 runtime required by the dashboard is missing.
- Handle malformed MediaMTX API responses without terminating dashboard requests.
- Retry macOS LaunchAgent registration after an update when launchd is still releasing the previous job.
- Isolate end-to-end test API and metrics ports from an installed server running on the same host.

### Added

- Update stream state live without reloading the dashboard page.
- Add copy controls for OBS/SRT, RTMP and RTSP connection URLs.
- Fall back to legacy clipboard copying on private HTTP addresses where the modern Clipboard API is unavailable.
- Distinguish a stopped media server from an idle stream in the status badge.
- Add a cache-free `/api/status` endpoint for the dashboard.
- Add atomic publisher/reader credential rotation with automatic service restart.

### Documentation

- Add a complete GitHub Wiki for installation, client setup, security, operations and troubleshooting.

## 1.0.0 — 2026-10-11

First public release.

### Included

- Native launchd installation for macOS on Apple Silicon and Intel.
- Native systemd installation for Debian and Ubuntu on x86_64 and ARM64.
- MediaMTX relay bound directly to the active Tailscale IPv4 address.
- Authenticated SRT ingest from Moblin and authenticated SRT output for OBS.
- RTSP, RTMP, LL-HLS and WebRTC listeners inside the Tailnet.
- Mobile dashboard with one-tap Moblin configuration and copyable OBS URL.
- Separate locally generated publisher and viewer credentials.
- Official MediaMTX release checksum verification.
- Runtime self-tests and an H.264/AAC SRT end-to-end test.
