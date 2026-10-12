# Tailnet IRL Server

[![Release](https://img.shields.io/github/v/release/nikpottbecker/tailnet-irl-server?display_name=tag&sort=semver)](https://github.com/nikpottbecker/tailnet-irl-server/releases)
[![License](https://img.shields.io/badge/license-BSD%20Advertising-blue)](LICENSE)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Wiki-2563EB)](https://github.com/nikpottbecker/tailnet-irl-server/wiki)
[![macOS](https://img.shields.io/badge/macOS-native-111827?logo=apple)](#macos)
[![Linux](https://img.shields.io/badge/Linux-native-FCC624?logo=linux&logoColor=111)](#linux--proxmox-lxc)

**A private, self-hosted IRL streaming relay for Moblin and OBS — carried entirely over Tailscale.**

Stream from an iPhone without exposing an ingest port to the public internet. Tailnet IRL Server runs MediaMTX as a native background service, creates separate publisher and viewer credentials, and gives you a mobile dashboard with a one-tap Moblin setup link and a ready-to-copy OBS URL.

```text
iPhone + Moblin ── authenticated SRT over Tailscale ──> Tailnet IRL Server
                                                               │
                   OBS / VLC / FFmpeg on PC <── SRT / RTSP ────┤
                   Browser preview         <── LL-HLS / WebRTC ┘
```

No Docker. No router port forwarding. No Cloudflare Tunnel. No public ingest endpoint.

**Documentation:** use the [GitHub Wiki](https://github.com/nikpottbecker/tailnet-irl-server/wiki) for complete installation, Moblin, OBS, security, operations and troubleshooting guides.

## Why use it?

- **Private by design:** media listeners bind directly to the server's Tailscale IP instead of `0.0.0.0`.
- **Built for Moblin:** import H.264, 1080p30, 6 Mbit/s, adaptive bitrate and a 2-second SRT latency with one tap.
- **OBS-ready:** copy the authenticated SRT reader URL straight from the dashboard.
- **Native services:** launchd on macOS and systemd on Debian or Ubuntu.
- **Multiple outputs:** SRT, RTSP, RTMP, LL-HLS and WebRTC through MediaMTX.
- **Automatic credentials:** publisher and viewer secrets are generated locally and kept out of logs.
- **Reproducible install:** the MediaMTX download is checked against its official SHA-256 manifest.
- **Self-test included:** verify Tailnet binding, services and the MediaMTX API at any time.

## Quick start

### macOS

Requirements: the official Tailscale app, an active Tailnet connection, Python 3 (included with the Apple Command Line Tools) and macOS on Apple Silicon or Intel.

```bash
git clone https://github.com/nikpottbecker/tailnet-irl-server.git
cd tailnet-irl-server
./install-macos.sh
./selftest-macos.sh
```

The two LaunchAgents start automatically after login. Application data and logs live under:

```text
~/Library/Application Support/IRL Server/
```

### Linux / Proxmox LXC

Supported targets: Debian 12/13 and Ubuntu 22.04/24.04 on x86_64 or ARM64. Proxmox containers must have `/dev/net/tun` enabled.

```bash
git clone https://github.com/nikpottbecker/tailnet-irl-server.git
cd tailnet-irl-server
sudo ./install.sh
sudo ./selftest.sh
```

If the machine is not yet connected to a Tailnet, the installer displays the official Tailscale login URL. When setup finishes, it prints the private dashboard address:

```text
http://100.x.y.z:8090
```

## Connect Moblin on iPhone

1. Connect the iPhone to the same Tailnet as the server.
2. Open the dashboard URL in Safari.
3. Tap **Open in Moblin** and approve the imported stream configuration.
4. Select **IRL Server (Tailscale)** in Moblin and go live.

The generated profile starts with settings suited to mobile networks:

| Setting | Default |
|---|---:|
| Video | H.264/AVC |
| Resolution | 1920×1080 |
| Frame rate | 30 fps |
| Video bitrate | 6 Mbit/s |
| Audio bitrate | 128 kbit/s |
| SRT latency | 2000 ms |
| Adaptive bitrate | Enabled |

You can add the dashboard to the iPhone Home Screen from Safari's Share menu.

## Receive the stream in OBS on PC

1. Connect the PC to the same Tailnet.
2. Open the dashboard and select **Copy OBS URL**.
3. In OBS, add a **Media Source**.
4. Disable **Local File** and paste the SRT URL into **Input**.
5. Enter `mpegts` as the **Input Format**.
6. Enable **Restart playback when source becomes active**.

The dashboard also provides an RTSP URL for VLC or FFmpeg and an authenticated browser preview.

## Security model

| Surface | Binding | Authentication |
|---|---|---|
| SRT ingest/read | Tailscale IP, UDP 8890 | Separate publisher/viewer credentials |
| RTSP | Tailscale IP, TCP 8554 | Viewer credentials |
| RTMP | Tailscale IP, TCP 1935 | Publisher credentials |
| LL-HLS | Tailscale IP, TCP 8888 | Viewer credentials |
| WebRTC | Tailscale IP, TCP 8889 + UDP 8189 | Viewer credentials |
| Control API | `127.0.0.1:9997` | Localhost only |
| Metrics | `127.0.0.1:9998` | Localhost only |

The dashboard contains working connection URLs and should only be reachable by trusted Tailnet devices. Restrict access further with Tailscale grants or ACLs when multiple people share the Tailnet.

## Operations

Linux:

```bash
sudo systemctl status irl-mediamtx irl-dashboard
sudo journalctl -u irl-mediamtx -f
sudo ./selftest.sh
```

macOS:

```bash
./selftest-macos.sh
tail -f "$HOME/Library/Application Support/IRL Server/logs/mediamtx.log"
```

Run the local end-to-end test to publish and read an authenticated H.264/AAC stream:

```bash
./tests/e2e-local.sh
```

Running the appropriate installer again updates the program while retaining the generated credentials.

## Current scope

Tailnet IRL Server provides one reliable SRT contribution path through Tailscale. It does not combine multiple network interfaces. Moblin SRTLA bonding requires a separate SRTLA receiver and is not included.

The installers currently use MediaMTX `v1.21.2` and verify the official release checksum before installation.

## Uninstall

```bash
# macOS
./uninstall-macos.sh

# Linux
sudo ./uninstall.sh
```

Credentials and state are retained intentionally so a later reinstall can keep the same Moblin and OBS URLs.

## Attribution and license

Tailnet IRL Server is available under the [BSD Advertising Acknowledgement License](LICENSE). You may use, modify and redistribute it, but **redistributions and promotional material mentioning the software must prominently include this acknowledgement:**

> This product includes Tailnet IRL Server software developed by Nik Pottbecker (https://github.com/nikpottbecker/tailnet-irl-server).

See [ATTRIBUTION.md](ATTRIBUTION.md) for placement examples and the exact required wording.

---

Developed by **Nik Pottbecker** · [GitHub](https://github.com/nikpottbecker)
