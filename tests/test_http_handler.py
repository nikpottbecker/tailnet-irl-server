import json
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import status_server


class HTTPHandlerTests(unittest.TestCase):
    def setUp(self):
        self.state = status_server.offline_state()
        self.clock = [100.0]
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
        self.server.stream_health_monitor = status_server.StreamHealthMonitor(
            clock=lambda: self.clock[0], stall_seconds=6
        )
        self.server.event_tracker = status_server.EventTracker()
        self.server.storage_monitor = status_server.StorageMonitor(Path.cwd())
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
            payload = json.load(response)
            history = payload.pop("history")
            storage = payload.pop("storage")
            stream_health = payload.pop("stream_health")
            self.assertEqual(payload, self.state)
            self.assertEqual(history["disconnects_24h"], 0)
            self.assertTrue(storage["available"])
            self.assertEqual(stream_health["state"], "offline")

    def test_health_endpoint_reports_media_server_failure(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(f"{self.base_url}/healthz")
        self.assertEqual(raised.exception.code, 503)

    def test_status_api_reports_input_bitrate_stall_and_recovery(self):
        self.state.update(
            {
                "online": True,
                "ready": True,
                "bytes": 100,
                "ready_since": "2026-10-12T12:00:00Z",
            }
        )
        with urllib.request.urlopen(f"{self.base_url}/api/status") as response:
            self.assertEqual(json.load(response)["stream_health"]["state"], "starting")

        self.clock[0] += 2
        self.state["bytes"] = 1_000_100
        with urllib.request.urlopen(f"{self.base_url}/api/status") as response:
            health = json.load(response)["stream_health"]
        self.assertEqual(health["state"], "receiving")
        self.assertEqual(health["bitrate_bps"], 4_000_000)

        self.clock[0] += 7
        with urllib.request.urlopen(f"{self.base_url}/api/status") as response:
            stalled = json.load(response)["stream_health"]
        self.assertEqual(stalled["state"], "stalled")
        self.assertEqual(stalled["stalled_seconds"], 7)

        self.clock[0] += 1
        self.state["bytes"] += 250_000
        with urllib.request.urlopen(f"{self.base_url}/api/status") as response:
            recovered = json.load(response)["stream_health"]
        self.assertEqual(recovered["state"], "receiving")
        self.assertEqual(recovered["bitrate_bps"], 2_000_000)

    def test_dashboard_has_security_headers_and_custom_server_name(self):
        with urllib.request.urlopen(f"{self.base_url}/") as response:
            body = response.read().decode()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
            self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
            self.assertEqual(response.headers["Server"].strip(), "TailnetIRLServer")
            self.assertIn("SERVER NICHT ERREICHBAR", body)
            self.assertIn("WebRTC öffnen", body)
            self.assertIn("Speicher", body)
            self.assertIn("Signalqualität", body)

    def test_version_manifest_and_icon_endpoints(self):
        with urllib.request.urlopen(f"{self.base_url}/api/version") as response:
            payload = json.load(response)
            self.assertEqual(payload["name"], "Tailnet IRL Server")
            self.assertEqual(payload["version"], "1.8.0")
        with urllib.request.urlopen(f"{self.base_url}/manifest.webmanifest") as response:
            manifest = json.load(response)
            self.assertEqual(manifest["icons"][0]["src"], "/icon.svg")
        with urllib.request.urlopen(f"{self.base_url}/icon.svg") as response:
            self.assertEqual(response.headers["Content-Type"], "image/svg+xml")
            self.assertIn(b"<svg", response.read())


if __name__ == "__main__":
    unittest.main()
