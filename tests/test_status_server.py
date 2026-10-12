import json
import tempfile
import unittest
import urllib.parse
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import status_server


class StatusServerTests(unittest.TestCase):
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
