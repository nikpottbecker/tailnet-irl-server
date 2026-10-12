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
        self.assertIn("developed by <a href=\"https://github.com/nikpottbecker\">Nik Pottbecker</a>", page)

    def test_stream_state_rejects_invalid_api_shape(self):
        response = BytesIO(b"[]")
        with patch("urllib.request.urlopen", return_value=response):
            self.assertEqual(
                status_server.stream_state(),
                {"online": False, "ready": False, "readers": 0, "bytes": 0},
            )

    def test_stream_state_tolerates_invalid_item_fields(self):
        response = BytesIO(
            b'{"items":[null,{"name":"live","ready":true,"readers":"bad","bytesReceived":"bad"}]}'
        )
        with patch("urllib.request.urlopen", return_value=response):
            self.assertEqual(
                status_server.stream_state(),
                {"online": True, "ready": True, "readers": 0, "bytes": 0},
            )


if __name__ == "__main__":
    unittest.main()
