import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from mms_web.server import WebApplication, create_server


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "public").mkdir()
        (self.root / "public/index.html").write_text("<h1>MMS</h1>")
        (self.root / "secret.txt").write_text("protected-test-secret")
        with patch("mms_web.server._adapter", return_value=None):
            self.app = WebApplication(state_root=self.root / "state")
        self.server = create_server(self.app, self.root / "public", 0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.app.close()
        self.temp.cleanup()

    def request(self, method="GET", path="/api/v1/bootstrap", body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_missing_adapters_are_live_empty_without_writes(self):
        status, _, body = self.request()
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(data["mode"], "live")
        self.assertEqual(data["sessions"], [])
        self.assertFalse(any(data["capabilities"].values()))
        self.assertFalse((self.root / "state").exists())

    def test_host_and_cross_origin_reads_are_denied(self):
        for headers in [
            {"Host": "attacker.test"}, {"Origin": "https://attacker.test"},
            {"Sec-Fetch-Site": "cross-site"}, {"Origin": "null"},
        ]:
            with self.subTest(headers=headers):
                self.assertEqual(self.request(headers=headers)[0], 403)

    def test_mutation_requires_csrf_and_never_fakes_success(self):
        headers = {"Content-Type": "application/json"}
        self.assertEqual(self.request("POST", "/api/v1/sessions", "{}", headers)[0], 403)
        headers["X-MMS-CSRF"] = self.app.csrf_token
        status, _, body = self.request("POST", "/api/v1/sessions", "{}", headers)
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(body)["error"]["code"], "CAPABILITY_UNAVAILABLE")

    def test_body_and_route_validation(self):
        headers = {"Content-Type": "application/json", "X-MMS-CSRF": self.app.csrf_token}
        for payload in ["[]", "{", "null"]:
            self.assertEqual(self.request("POST", "/api/v1/sessions", payload, headers)[0], 400)
        self.assertEqual(self.request(path="/api/v1/unknown")[0], 404)

    def test_static_path_escape_and_security_headers(self):
        for path in ["/../secret.txt", "/%2e%2e/secret.txt"]:
            status, _, body = self.request(path=path)
            self.assertEqual(status, 404)
            self.assertNotIn(b"protected-test-secret", body)
        status, headers, _ = self.request(path="/")
        self.assertEqual(status, 200)
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_internal_error_never_serializes_exception(self):
        with patch.object(self.app, "get", side_effect=RuntimeError("secret-private-key")):
            status, _, body = self.request()
        self.assertEqual(status, 500)
        self.assertNotIn(b"secret-private-key", body)


if __name__ == "__main__":
    unittest.main()
