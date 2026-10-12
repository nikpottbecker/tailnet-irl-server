import json
import tempfile
import unittest
import urllib.parse
from collections import namedtuple
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import status_server


class StatusServerTests(unittest.TestCase):
    def test_storage_monitor_aggregates_recordings_and_caches_results(self):
        disk_usage = namedtuple("usage", "total used free")
        clock = [100.0]
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            recordings = state_dir / "recordings" / "live"
            recordings.mkdir(parents=True)
            (recordings / "one.mp4").write_bytes(b"1234")
            (recordings / "two.ts").write_bytes(b"123456")
            (recordings / "ignored.txt").write_text("not media")
            monitor = status_server.StorageMonitor(
                state_dir, clock=lambda: clock[0], cache_seconds=30
            )
            with patch(
                "status_server.shutil.disk_usage",
                return_value=disk_usage(100 * 1024**3, 95 * 1024**3, 5 * 1024**3),
            ):
                snapshot = monitor.snapshot()
                self.assertEqual(snapshot["level"], "warning")
                self.assertEqual(snapshot["recording_files"], 2)
                self.assertEqual(snapshot["recording_bytes"], 10)

                (recordings / "three.mp4").write_bytes(b"12")
                self.assertEqual(monitor.snapshot()["recording_files"], 2)
                clock[0] += 31
                refreshed = monitor.snapshot()
                self.assertEqual(refreshed["recording_files"], 3)
                self.assertEqual(refreshed["recording_bytes"], 12)

    def test_storage_monitor_reports_critical_and_unavailable_states(self):
        disk_usage = namedtuple("usage", "total used free")
        with tempfile.TemporaryDirectory() as tmp:
            monitor = status_server.StorageMonitor(Path(tmp))
            with patch(
                "status_server.shutil.disk_usage",
                return_value=disk_usage(100 * 1024**3, 99 * 1024**3, 512 * 1024**2),
            ):
                self.assertEqual(monitor.snapshot()["level"], "critical")

        unavailable = status_server.StorageMonitor(Path("/path/that/does/not/exist"))
        self.assertFalse(unavailable.snapshot()["available"])

    def test_event_tracker_persists_stream_transitions_without_secrets(self):
        now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "connection-history.json"
            tracker = status_server.EventTracker(path, clock=lambda: now)
            initial = tracker.observe(status_server.offline_state())
            self.assertEqual(initial["events"], [])

            live = status_server.offline_state()
            live.update(
                {
                    "online": True,
                    "ready": True,
                    "ready_since": "2026-10-12T11:58:00Z",
                    "secret": "must-not-be-stored",
                }
            )
            history = tracker.observe(live)
            self.assertEqual(history["last_live_at"], "2026-10-12T11:58:00Z")
            self.assertEqual(
                [event["type"] for event in history["events"]],
                ["stream_started", "server_online"],
            )

            idle = dict(live, ready=False, ready_since=None)
            history = tracker.observe(idle)
            self.assertEqual(history["disconnects_24h"], 1)
            self.assertEqual(history["events"][0]["type"], "stream_stopped")
            self.assertEqual(history["events"][0]["duration_seconds"], 120)
            self.assertNotIn("must-not-be-stored", path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

            restored = status_server.EventTracker(path, clock=lambda: now)
            restored_history = restored.observe(idle)
            self.assertEqual(restored_history, history)

            payload = json.loads(path.read_text())
            payload["events"][0]["unexpected"] = "not exposed"
            path.write_text(json.dumps(payload))
            normalized = status_server.EventTracker(path, clock=lambda: now)
            normalized_history = normalized.observe(idle)
            self.assertNotIn("unexpected", normalized_history["events"][-1])

    def test_version_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "VERSION"
            path.write_text("1.2.3-beta.1\n")
            self.assertEqual(status_server.app_version(path), "1.2.3-beta.1")
            path.write_text("not-a-version\n")
            self.assertEqual(status_server.app_version(path), "development")

    def test_tailscale_ipv4_range(self):
        self.assertTrue(status_server.is_tailscale_ipv4("100.64.0.1"))
        self.assertTrue(status_server.is_tailscale_ipv4("100.127.255.254"))
        self.assertFalse(status_server.is_tailscale_ipv4("100.63.255.255"))
        self.assertFalse(status_server.is_tailscale_ipv4("100.128.0.1"))
        self.assertFalse(status_server.is_tailscale_ipv4("not-an-address"))

    def test_credentials_and_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "credentials.env"
            path.write_text("PUBLISH_PASSWORD=publishsecret1234567890\nREAD_PASSWORD=readsecret123456789012\n")
            credentials = status_server.read_credentials(path)
        links = status_server.connection_data("100.64.1.2", credentials)
        self.assertIn("streamid=publish:live:mobile:publishsecret", links["srt_publish"])
        self.assertIn("streamid=read:live:studio:readsecret", links["srt_read"])
        self.assertTrue(links["moblin"].startswith("moblin://?"))
        self.assertEqual(links["webrtc_preview"], "http://100.64.1.2:8889/live")

        settings = json.loads(urllib.parse.unquote(links["moblin"].split("?", 1)[1]))
        stream = settings["streams"][0]
        self.assertEqual(stream["video"]["resolution"], "1920x1080")
        self.assertEqual(stream["video"]["codec"], "H.264/AVC")
        self.assertEqual(stream["srt"]["latency"], 2000)
        self.assertTrue(stream["srt"]["adaptiveBitrateEnabled"])

    def test_custom_stream_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.env"
            path.write_text(
                "STREAM_NAME=Mobile 720p\n"
                "VIDEO_RESOLUTION=1280x720\n"
                "VIDEO_FPS=50\n"
                "VIDEO_BITRATE=3500000\n"
                "AUDIO_BITRATE=96000\n"
                "SRT_LATENCY=2500\n"
                "ADAPTIVE_BITRATE=false\n"
            )
            profile = status_server.read_profile(path)
        credentials = {
            "PUBLISH_PASSWORD": "publishsecret1234567890",
            "READ_PASSWORD": "readsecret123456789012",
        }
        links = status_server.connection_data("100.64.1.2", credentials, profile)
        settings = json.loads(urllib.parse.unquote(links["moblin"].split("?", 1)[1]))
        stream = settings["streams"][0]
        self.assertEqual(stream["name"], "Mobile 720p")
        self.assertEqual(stream["video"]["resolution"], "1280x720")
        self.assertEqual(stream["video"]["fps"], 50)
        self.assertEqual(stream["video"]["bitrate"], 3_500_000)
        self.assertEqual(stream["audio"]["bitrate"], 96_000)
        self.assertEqual(stream["srt"]["latency"], 2_500)
        self.assertFalse(stream["srt"]["adaptiveBitrateEnabled"])

    def test_invalid_stream_profile_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.env"
            path.write_text("VIDEO_RESOLUTION=full-hd\nVIDEO_FPS=fast\n")
            with self.assertRaisesRegex(RuntimeError, "VIDEO_RESOLUTION"):
                status_server.read_profile(path)

    def test_recording_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "recording.env"
            path.write_text(
                "RECORDING_ENABLED=true\n"
                "RECORDING_FORMAT=mpegts\n"
                "RECORDING_SEGMENT_DURATION=10m\n"
                "RECORDING_DELETE_AFTER=7d\n"
            )
            self.assertEqual(
                status_server.read_recording(path),
                {
                    "enabled": True,
                    "format": "mpegts",
                    "segment_duration": "10m",
                    "delete_after": "7d",
                },
            )

    def test_invalid_recording_configuration_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "recording.env"
            path.write_text("RECORDING_ENABLED=sometimes\n")
            with self.assertRaisesRegex(RuntimeError, "RECORDING_ENABLED"):
                status_server.read_recording(path)

    def test_dashboard_escapes_secrets(self):
        credentials = {
            "PUBLISH_PASSWORD": "secret&publisher123456789",
            "READ_PASSWORD": "secret<reader12345678901",
        }
        page = status_server.render_page(
            "100.64.1.2",
            credentials,
            {"online": True, "ready": False, "readers": 0, "bytes": 0},
        )
        self.assertNotIn("secret<reader", page)
        self.assertIn("secret&lt;reader", page)
        self.assertIn("WARTET AUF HANDY", page)
        self.assertIn('data-copy-target="obs"', page)
        self.assertIn("fetch('/api/status'", page)
        self.assertIn("document.execCommand('copy')", page)
        self.assertIn("developed by <a href=\"https://github.com/nikpottbecker\">Nik Pottbecker</a>", page)

    def test_status_presentation(self):
        self.assertEqual(
            status_server.status_presentation({"online": False, "ready": False}),
            ("SERVER NICHT ERREICHBAR", "error"),
        )
        self.assertEqual(
            status_server.status_presentation({"online": True, "ready": False}),
            ("WARTET AUF HANDY", "idle"),
        )
        self.assertEqual(
            status_server.status_presentation({"online": True, "ready": True}),
            ("LIVE", "live"),
        )

    def test_stream_state_rejects_invalid_api_shape(self):
        response = BytesIO(b"[]")
        with patch("urllib.request.urlopen", return_value=response):
            self.assertEqual(
                status_server.stream_state(),
                status_server.offline_state(),
            )

    def test_stream_state_tolerates_invalid_item_fields(self):
        response = BytesIO(
            b'{"items":[null,{"name":"live","ready":true,"readers":"bad","bytesReceived":"bad","bytesSent":"bad","readyTime":42,"tracks":"bad"}]}'
        )
        with patch("urllib.request.urlopen", return_value=response):
            self.assertEqual(
                status_server.stream_state(),
                {
                    "online": True,
                    "ready": True,
                    "readers": 0,
                    "bytes": 0,
                    "bytes_sent": 0,
                    "ready_since": None,
                    "tracks": [],
                },
            )

    def test_stream_state_exposes_live_telemetry(self):
        response = BytesIO(
            b'{"items":[{"name":"live","ready":true,"readers":[{},{}],'
            b'"inboundBytes":1250000,"outboundBytes":2500000,'
            b'"readyTime":"2026-10-12T05:00:00Z","tracks":["H264","MPEG-4 Audio"]}]}'
        )
        with patch("urllib.request.urlopen", return_value=response):
            self.assertEqual(
                status_server.stream_state(),
                {
                    "online": True,
                    "ready": True,
                    "readers": 2,
                    "bytes": 1_250_000,
                    "bytes_sent": 2_500_000,
                    "ready_since": "2026-10-12T05:00:00Z",
                    "tracks": ["H264", "MPEG-4 Audio"],
                },
            )


if __name__ == "__main__":
    unittest.main()
