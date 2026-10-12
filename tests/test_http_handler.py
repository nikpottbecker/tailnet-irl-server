import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

import status_server


class HTTPHandlerTests(unittest.TestCase):
    def setUp(self):
        self.state = status_server.offline_state()
        self.state_patch = patch("status_server.stream_state", side_effect=lambda: self.state)
        self.state_patch.start()
        self.server = status_server.ThreadingHTTPServer(
            ("127.0.0.1", 0), status_server.Handler
        )
        self.server.credentials = {
            "PUBLISH_PASSWORD": "publishersecret1234567890",
            "READ_PASSWORD": "readersecret123456789012",
        }
        self.server.profile = dict(status_server.DEFAULT_PROFILE)
        self.server.recording = dict(status_server.DEFAULT_RECORDING)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.state_patch.stop()

    def test_status_api_remains_available_when_media_server_is_offline(self):
        with urllib.request.urlopen(f"{self.base_url}/api/status") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(json.load(response), self.state)

    def test_health_endpoint_reports_media_server_failure(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(f"{self.base_url}/healthz")
        self.assertEqual(raised.exception.code, 503)

    def test_dashboard_has_security_headers_and_custom_server_name(self):
        with urllib.request.urlopen(f"{self.base_url}/") as response:
            body = response.read().decode()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
            self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
            self.assertEqual(response.headers["Server"].strip(), "TailnetIRLServer")
            self.assertIn("SERVER NICHT ERREICHBAR", body)
            self.assertIn("WebRTC öffnen", body)

    def test_version_manifest_and_icon_endpoints(self):
        with urllib.request.urlopen(f"{self.base_url}/api/version") as response:
            payload = json.load(response)
            self.assertEqual(payload["name"], "Tailnet IRL Server")
            self.assertEqual(payload["version"], "1.3.0")
        with urllib.request.urlopen(f"{self.base_url}/manifest.webmanifest") as response:
            manifest = json.load(response)
            self.assertEqual(manifest["icons"][0]["src"], "/icon.svg")
        with urllib.request.urlopen(f"{self.base_url}/icon.svg") as response:
            self.assertEqual(response.headers["Content-Type"], "image/svg+xml")
            self.assertIn(b"<svg", response.read())


if __name__ == "__main__":
    unittest.main()
