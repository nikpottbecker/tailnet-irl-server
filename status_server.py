#!/usr/bin/env python3
"""Small dependency-free Tailnet dashboard for the IRL relay."""

from __future__ import annotations

import html
import ipaddress
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


CONFIG_DIR = Path(os.environ.get("IRL_CONFIG_DIR", "/etc/irl-server"))
API_URL = os.environ.get("MEDIAMTX_API", "http://127.0.0.1:9997/v3/paths/list")
TAILSCALE_IPV4_NETWORK = ipaddress.ip_network("100.64.0.0/10")
DEFAULT_PROFILE: dict[str, object] = {
    "stream_name": "IRL Server (Tailscale)",
    "video_resolution": "1920x1080",
    "video_fps": 30,
    "video_bitrate": 6_000_000,
    "audio_bitrate": 128_000,
    "srt_latency": 2_000,
    "adaptive_bitrate": True,
}


def is_tailscale_ipv4(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.version == 4 and address in TAILSCALE_IPV4_NETWORK


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def read_credentials(path: Path | None = None) -> dict[str, str]:
    values = read_env_file(path or CONFIG_DIR / "credentials.env")
    required = {"PUBLISH_PASSWORD", "READ_PASSWORD"}
    if not required.issubset(values):
        raise RuntimeError("credentials.env is incomplete")
    return values


def read_profile(path: Path | None = None) -> dict[str, object]:
    profile = dict(DEFAULT_PROFILE)
    profile_path = path or CONFIG_DIR / "profile.env"
    if not profile_path.exists():
        return profile

    values = read_env_file(profile_path)
    stream_name = values.get("STREAM_NAME", str(profile["stream_name"]))
    resolution = values.get("VIDEO_RESOLUTION", str(profile["video_resolution"]))
    if not stream_name or len(stream_name) > 64:
        raise RuntimeError("STREAM_NAME must contain 1 to 64 characters")
    if not re.fullmatch(r"[1-9][0-9]{2,3}x[1-9][0-9]{2,3}", resolution):
        raise RuntimeError("VIDEO_RESOLUTION must use WIDTHxHEIGHT, for example 1920x1080")

    def integer(name: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(values.get(name, default))
        except ValueError as error:
            raise RuntimeError(f"{name} must be an integer") from error
        if not minimum <= value <= maximum:
            raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
        return value

    adaptive = values.get("ADAPTIVE_BITRATE", "true").lower()
    if adaptive not in {"true", "false"}:
        raise RuntimeError("ADAPTIVE_BITRATE must be true or false")

    profile.update(
        {
            "stream_name": stream_name,
            "video_resolution": resolution,
            "video_fps": integer("VIDEO_FPS", 30, 1, 120),
            "video_bitrate": integer("VIDEO_BITRATE", 6_000_000, 100_000, 50_000_000),
            "audio_bitrate": integer("AUDIO_BITRATE", 128_000, 32_000, 512_000),
            "srt_latency": integer("SRT_LATENCY", 2_000, 120, 20_000),
            "adaptive_bitrate": adaptive == "true",
        }
    )
    return profile


def offline_state() -> dict[str, object]:
    return {
        "online": False,
        "ready": False,
        "readers": 0,
        "bytes": 0,
        "bytes_sent": 0,
        "ready_since": None,
        "tracks": [],
    }


def tailscale_ip() -> str:
    value = os.environ.get("TAILSCALE_IP")
    if not value:
        binary = os.environ.get("TAILSCALE_BIN", "tailscale")
        result = subprocess.run(
            [binary, "ip", "-4"], check=True, capture_output=True, text=True
        )
        value = result.stdout.splitlines()[0].strip()
    if not is_tailscale_ipv4(value):
        raise RuntimeError("no active Tailscale IPv4 address")
    return value


def stream_state() -> dict[str, object]:
    try:
        with urllib.request.urlopen(API_URL, timeout=1.5) as response:
            payload = json.load(response)
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError("unexpected MediaMTX API response")
    except (OSError, urllib.error.URLError, TypeError, ValueError):
        return offline_state()

    for item in payload["items"]:
        if not isinstance(item, dict):
            continue
        if item.get("name") == "live":
            readers = item.get("readers")
            received = item.get("inboundBytes", item.get("bytesReceived", 0))
            sent = item.get("outboundBytes", item.get("bytesSent", 0))
            tracks = item.get("tracks")
            ready_since = item.get("readyTime")
            return {
                "online": True,
                "ready": bool(item.get("ready")),
                "readers": len(readers) if isinstance(readers, list) else 0,
                "bytes": int(received) if isinstance(received, (int, float)) else 0,
                "bytes_sent": int(sent) if isinstance(sent, (int, float)) else 0,
                "ready_since": ready_since if isinstance(ready_since, str) else None,
                "tracks": [str(track) for track in tracks]
                if isinstance(tracks, list)
                else [],
            }
    state = offline_state()
    state["online"] = True
    return state


def connection_data(
    ip: str,
    credentials: dict[str, str],
    profile: dict[str, object] | None = None,
) -> dict[str, str]:
    publish = credentials["PUBLISH_PASSWORD"]
    read = credentials["READ_PASSWORD"]
    stream_profile = profile or DEFAULT_PROFILE
    srt_publish = (
        f"srt://{ip}:8890?streamid=publish:live:mobile:{publish}&pkt_size=1316"
    )
    srt_read = f"srt://{ip}:8890?streamid=read:live:studio:{read}&pkt_size=1316"
    settings = {
        "streams": [
            {
                "name": stream_profile["stream_name"],
                "url": srt_publish,
                "selected": True,
                "video": {
                    "resolution": stream_profile["video_resolution"],
                    "fps": stream_profile["video_fps"],
                    "bitrate": stream_profile["video_bitrate"],
                    "codec": "H.264/AVC",
                    "bFrames": False,
                    "maxKeyFrameInterval": 2,
                },
                "audio": {"bitrate": stream_profile["audio_bitrate"]},
                "srt": {
                    "latency": stream_profile["srt_latency"],
                    "adaptiveBitrateEnabled": stream_profile["adaptive_bitrate"],
                },
            }
        ]
    }
    compact = json.dumps(settings, ensure_ascii=False, separators=(",", ":"))
    return {
        "srt_publish": srt_publish,
        "srt_read": srt_read,
        "rtsp_read": f"rtsp://studio:{read}@{ip}:8554/live",
        "rtmp_publish": f"rtmp://{ip}:1935/live?user=mobile&pass={publish}",
        "moblin": "moblin://?" + urllib.parse.quote(compact, safe=""),
        "preview": f"http://{ip}:8888/live",
    }


def status_presentation(state: dict[str, object]) -> tuple[str, str]:
    if not state["online"]:
        return "SERVER NICHT ERREICHBAR", "error"
    if state["ready"]:
        return "LIVE", "live"
    return "WARTET AUF HANDY", "idle"


def render_page(
    ip: str,
    credentials: dict[str, str],
    state: dict[str, object],
    profile: dict[str, object] | None = None,
) -> str:
    stream_profile = profile or DEFAULT_PROFILE
    links = connection_data(ip, credentials, stream_profile)
    status, status_class = status_presentation(state)

    def esc(value: object) -> str:
        return html.escape(str(value), quote=True)

    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#071019"><link rel="manifest" href="/manifest.webmanifest">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="IRL Server">
<title>IRL Server</title>
<style>
:root{{--bg:#071019;--panel:#101c27;--line:#263746;--text:#f6f8fa;--muted:#9db0bf;--accent:#ffb000;--ok:#39d98a;--error:#ff5c5c}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:16px system-ui,-apple-system,sans-serif}}
main{{max-width:900px;margin:auto;padding:28px 18px 60px}}header{{display:flex;gap:18px;justify-content:space-between;align-items:end;border-bottom:1px solid var(--line);padding-bottom:20px}}
h1{{font-size:clamp(28px,7vw,54px);margin:0;letter-spacing:-.05em}}p{{color:var(--muted)}}.badge{{padding:9px 12px;border-radius:4px;font-weight:800;font-size:13px;letter-spacing:.08em;text-align:center}}.idle{{background:var(--accent);color:#161000}}.live{{background:var(--ok);color:#03130c}}.error{{background:var(--error);color:#210000}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin-top:20px}}section{{background:var(--panel);border:1px solid var(--line);padding:18px;border-radius:9px}}h2{{font-size:17px;margin:0 0 8px}}code{{display:block;color:#d8e8f2;overflow-wrap:anywhere;font-size:12px;background:#071019;padding:10px;border-radius:5px}}a.button,button{{display:inline-block;margin-top:12px;padding:11px 14px;background:var(--accent);color:#171000;text-decoration:none;border:0;border-radius:5px;font-weight:800;cursor:pointer}}small{{color:var(--muted)}}
footer{{margin-top:24px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}}footer a{{color:var(--text)}}
</style></head><body><main>
<header><div><small>TAILNET · {esc(ip)}</small><h1>IRL SERVER</h1></div><span id="status-badge" class="badge {status_class}" aria-live="polite">{status}</span></header>
<div class="grid">
<section><h2>1 · iPhone / Moblin</h2><p>Tailscale verbinden, dann Moblin automatisch konfigurieren.</p><a class="button" href="{esc(links['moblin'])}">In Moblin öffnen</a><p><small>H.264 · {esc(stream_profile['video_resolution'])}p{esc(stream_profile['video_fps'])} · {float(stream_profile['video_bitrate']) / 1_000_000:g} Mbit/s · SRT {esc(stream_profile['srt_latency'])} ms · adaptive Bitrate {'an' if stream_profile['adaptive_bitrate'] else 'aus'}</small></p></section>
<section><h2>2 · OBS auf dem PC</h2><p>Medienquelle → Lokale Datei aus → Eingabeformat <b>mpegts</b>.</p><code id="obs">{esc(links['srt_read'])}</code><button data-copy-target="obs">OBS-Link kopieren</button></section>
<section><h2>Fallback für Moblin</h2><p>Falls SRT in einem Netz blockiert ist, RTMP testen.</p><code id="rtmp">{esc(links['rtmp_publish'])}</code><button data-copy-target="rtmp">RTMP-Link kopieren</button></section>
<section><h2>Vorschau</h2><p>Browser-Vorschau über LL-HLS; mit Benutzer <b>studio</b> und dem Lesepasswort anmelden.</p><a class="button" href="{esc(links['preview'])}">Vorschau öffnen</a></section>
<section><h2>Live-Telemetrie</h2><p>Media-Server: <b id="server-state">{'bereit' if state['online'] else 'nicht erreichbar'}</b><br>Feed: <b id="feed-state">{'aktiv' if state['ready'] else 'offline'}</b><br>Datenrate: <b id="bitrate">0.00 Mbit/s</b><br>Laufzeit: <b id="uptime">–</b><br>Leser: <b id="reader-count">{esc(state['readers'])}</b><br>Empfangen: <b id="received-bytes">{float(state['bytes']) / 1_000_000:.1f} MB</b><br>Gesendet: <b id="sent-bytes">{float(state.get('bytes_sent', 0)) / 1_000_000:.1f} MB</b><br>Spuren: <b id="tracks">{esc(', '.join(state.get('tracks', [])) or '–')}</b></p></section>
<section><h2>Alternative für VLC</h2><p>RTSP ist für VLC/FFmpeg meist die einfachste Leseverbindung.</p><code id="rtsp">{esc(links['rtsp_read'])}</code><button data-copy-target="rtsp">RTSP-Link kopieren</button></section>
</div>
<footer>This product includes Tailnet IRL Server software developed by <a href="https://github.com/nikpottbecker">Nik Pottbecker</a>. <a href="https://github.com/nikpottbecker/tailnet-irl-server">Source &amp; license</a></footer>
<script>
const badge = document.querySelector('#status-badge');
let previousBytes = null;
let previousSampleAt = null;
function formatDuration(value) {{
  const started = Date.parse(value || '');
  if (!Number.isFinite(started)) return '–';
  const seconds = Math.max(0, Math.floor((Date.now() - started) / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  return hours > 0
    ? `${{hours}}:${{String(minutes).padStart(2, '0')}}:${{String(remainder).padStart(2, '0')}}`
    : `${{minutes}}:${{String(remainder).padStart(2, '0')}}`;
}}
function showStatus(state) {{
  const online = Boolean(state.online);
  const ready = Boolean(state.ready);
  const bytes = Number(state.bytes || 0);
  const sampleAt = performance.now();
  let bitrate = 0;
  if (ready && previousBytes !== null && bytes >= previousBytes && previousSampleAt !== null) {{
    const seconds = (sampleAt - previousSampleAt) / 1000;
    if (seconds > 0) bitrate = ((bytes - previousBytes) * 8) / seconds / 1000000;
  }}
  badge.textContent = !online ? 'SERVER NICHT ERREICHBAR' : ready ? 'LIVE' : 'WARTET AUF HANDY';
  badge.className = `badge ${{!online ? 'error' : ready ? 'live' : 'idle'}}`;
  document.querySelector('#server-state').textContent = online ? 'bereit' : 'nicht erreichbar';
  document.querySelector('#feed-state').textContent = ready ? 'aktiv' : 'offline';
  document.querySelector('#bitrate').textContent = `${{bitrate.toFixed(2)}} Mbit/s`;
  document.querySelector('#uptime').textContent = ready ? formatDuration(state.ready_since) : '–';
  document.querySelector('#reader-count').textContent = Number(state.readers || 0).toLocaleString('de-DE');
  document.querySelector('#received-bytes').textContent = `${{(bytes / 1000000).toFixed(1)}} MB`;
  document.querySelector('#sent-bytes').textContent = `${{(Number(state.bytes_sent || 0) / 1000000).toFixed(1)}} MB`;
  const tracks = Array.isArray(state.tracks) ? state.tracks : [];
  document.querySelector('#tracks').textContent = tracks.length ? tracks.join(', ') : '–';
  previousBytes = ready ? bytes : null;
  previousSampleAt = ready ? sampleAt : null;
}}
async function refreshStatus() {{
  try {{
    const response = await fetch('/api/status', {{cache: 'no-store'}});
    showStatus(await response.json());
  }} catch (_) {{
    showStatus({{online: false, ready: false, readers: 0, bytes: 0, bytes_sent: 0, ready_since: null, tracks: []}});
  }}
}}
async function copyText(value) {{
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    await navigator.clipboard.writeText(value);
    return;
  }}
  const input = document.createElement('textarea');
  input.value = value;
  input.setAttribute('readonly', '');
  input.style.position = 'fixed';
  input.style.opacity = '0';
  document.body.appendChild(input);
  input.select();
  const copied = document.execCommand('copy');
  input.remove();
  if (!copied) throw new Error('copy failed');
}}
document.querySelectorAll('button[data-copy-target]').forEach((button) => {{
  button.addEventListener('click', async () => {{
    const original = button.textContent;
    const value = document.querySelector(`#${{button.dataset.copyTarget}}`).textContent;
    try {{
      await copyText(value);
      button.textContent = 'Kopiert';
    }} catch (_) {{
      button.textContent = 'Kopieren fehlgeschlagen';
    }}
    setTimeout(() => {{ button.textContent = original; }}, 1800);
  }});
}});
setInterval(refreshStatus, 2000);
</script>
</main></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "TailnetIRLServer"
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlsplit(self.path).path
        if path in {"/healthz", "/api/status"}:
            state = stream_state()
            body = json.dumps(state).encode()
            status = 200 if path == "/api/status" or state["online"] else 503
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
        elif path == "/manifest.webmanifest":
            body = json.dumps(
                {
                    "name": "IRL Server",
                    "short_name": "IRL Server",
                    "start_url": "/",
                    "display": "standalone",
                    "background_color": "#071019",
                    "theme_color": "#071019",
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json")
            self.send_header("Cache-Control", "public, max-age=86400")
        elif path == "/":
            body = render_page(
                self.server.server_address[0],
                self.server.credentials,  # type: ignore[attr-defined]
                stream_state(),
                self.server.profile,  # type: ignore[attr-defined]
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; connect-src 'self'; "
                "img-src 'self' data:; object-src 'none'; base-uri 'none'",
            )
        else:
            body = b"not found\n"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"dashboard: {self.address_string()} {fmt % args}")


def main() -> None:
    ip = tailscale_ip()
    server = ThreadingHTTPServer((ip, int(os.environ.get("PORT", "8090"))), Handler)
    server.credentials = read_credentials()  # type: ignore[attr-defined]
    server.profile = read_profile()  # type: ignore[attr-defined]
    print(f"IRL dashboard listening on http://{ip}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
