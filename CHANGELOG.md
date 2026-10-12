# Changelog

All notable changes to Tailnet IRL Server are documented here.

## Unreleased

### Fixed

- Validate server addresses against Tailscale's complete `100.64.0.0/10` IPv4 range.
- Fail early on macOS when the Python 3 runtime required by the dashboard is missing.
- Handle malformed MediaMTX API responses without terminating dashboard requests.

### Added

- Update stream state live without reloading the dashboard page.
- Add copy controls for OBS/SRT, RTMP and RTSP connection URLs.
- Fall back to legacy clipboard copying on private HTTP addresses where the modern Clipboard API is unavailable.
- Distinguish a stopped media server from an idle stream in the status badge.
- Add a cache-free `/api/status` endpoint for the dashboard.

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
