"""Coverage for the opt-in Pi request capture (issue #97).

The point of the capture surface is to be invisible unless explicitly asked for,
and to reliably flag raw control bytes when it is.
"""

import json
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mms_pi_capture


MODELS_PAYLOAD = {
    "providers": {
        "mms-relay-anthropic": {
            "name": "relay",
            "baseUrl": "http://relay.example.com",
            "api": "anthropic-messages",
            "apiKey": "secret",
            "models": [{"id": "glm-5.2"}],
        },
        "mms-relay-responses": {
            "name": "relay responses",
            "baseUrl": "http://relay.example.com:3000/openai/v1",
            "api": "openai-responses",
            "apiKey": "secret",
            "models": [{"id": "gpt-5.6-terra"}],
        },
    }
}


def _write_models(tmp_path):
    models_path = tmp_path / "models.json"
    models_path.write_text(json.dumps(MODELS_PAYLOAD, indent=2) + "\n", encoding="utf-8")
    return models_path


def test_capture_disabled_leaves_launch_untouched(tmp_path):
    models_path = _write_models(tmp_path)
    before = models_path.read_text(encoding="utf-8")
    env = {}

    assert mms_pi_capture.apply_capture_proxy(models_path, env, tmp_path) == ""
    assert models_path.read_text(encoding="utf-8") == before
    assert env == {}


@pytest.mark.parametrize("disabled", ["", "0", "false", "off", "no"])
def test_falsy_settings_stay_disabled(disabled):
    assert mms_pi_capture.capture_setting({mms_pi_capture.CAPTURE_ENV: disabled}) == ""


def test_origin_token_roundtrip():
    for origin in ("http://relay.example.com", "https://relay.example.com:3000"):
        token = mms_pi_capture.encode_origin(origin)
        assert "/" not in token
        assert mms_pi_capture.decode_origin(token) == origin


def test_capture_url_keeps_the_upstream_path_suffix():
    url = mms_pi_capture.capture_url("127.0.0.1:9000", "http://relay.example.com:3000/openai/v1")
    prefix = f"http://127.0.0.1:9000{mms_pi_capture.CAPTURE_PATH_PREFIX}/"
    assert url.startswith(prefix)
    token = url[len(prefix):].split("/", 1)[0]
    assert mms_pi_capture.decode_origin(token) == "http://relay.example.com:3000"
    assert url.endswith("/openai/v1")


def test_explicit_endpoint_rewrites_every_provider(tmp_path):
    models_path = _write_models(tmp_path)
    env = {}

    capture_dir = mms_pi_capture.apply_capture_proxy(
        models_path, env, tmp_path, setting="127.0.0.1:9000"
    )

    assert capture_dir == str(tmp_path / "pi-capture")
    assert env[mms_pi_capture.CAPTURE_ENDPOINT_ENV] == "127.0.0.1:9000"
    payload = json.loads(models_path.read_text(encoding="utf-8"))
    for provider in payload["providers"].values():
        assert provider["baseUrl"].startswith(
            f"http://127.0.0.1:9000{mms_pi_capture.CAPTURE_PATH_PREFIX}/"
        )
    # Everything except the baseUrl must survive the rewrite untouched.
    assert payload["providers"]["mms-relay-anthropic"]["apiKey"] == "secret"
    assert payload["providers"]["mms-relay-responses"]["api"] == "openai-responses"

    routes = json.loads((Path(capture_dir) / "routes.json").read_text(encoding="utf-8"))
    assert routes["mms-relay-anthropic"]["original"] == "http://relay.example.com"


def test_unparsable_base_url_is_left_alone():
    payload = {"providers": {"broken": {"baseUrl": "not-a-url"}}}
    _, routes = mms_pi_capture.rewrite_models_payload(payload, "127.0.0.1:9000")
    assert routes == {}
    assert payload["providers"]["broken"]["baseUrl"] == "not-a-url"


class _EchoUpstream(BaseHTTPRequestHandler):
    received = []

    def log_message(self, *args):
        return

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        type(self).received.append((self.path, body))
        payload = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_proxy_flags_raw_control_bytes_and_forwards_bytes_verbatim(tmp_path):
    upstream = HTTPServer(("127.0.0.1", 0), _EchoUpstream)
    _EchoUpstream.received = []
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    upstream_origin = f"http://127.0.0.1:{upstream.server_address[1]}"

    port = _free_port()
    script = Path(__file__).resolve().parents[1] / "scripts" / "pi_capture_proxy.py"
    proxy = subprocess.Popen(
        [sys.executable, str(script), "--port", str(port), "--log-dir", str(tmp_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("capture proxy never started listening")

        token = mms_pi_capture.encode_origin(upstream_origin)
        url = f"http://127.0.0.1:{port}{mms_pi_capture.CAPTURE_PATH_PREFIX}/{token}/v1/messages"
        # A body carrying the exact defect we are hunting: an unescaped control byte.
        body = b'{"model":"glm-5.2","messages":[{"role":"user","content":"a\x00b"}]}'

        import urllib.request

        request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            assert response.status == 200
            assert json.loads(response.read())["ok"] is True

        assert _EchoUpstream.received == [("/v1/messages", body)]

        entries = [
            json.loads(line)
            for line in (tmp_path / "capture.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["origin"] == upstream_origin
        assert entry["path"] == "/v1/messages"
        assert entry["status"] == 200
        assert [hit["byte"] for hit in entry["raw_control_bytes"]] == ["0x00"]
        # Suspicious requests keep their raw body for byte-level inspection.
        assert (tmp_path / f"req-{entry['index']:05d}.bin").read_bytes() == body
    finally:
        proxy.terminate()
        proxy.wait(timeout=10)
        upstream.shutdown()


def test_proxy_keeps_clean_requests_out_of_the_raw_body_dump(tmp_path):
    upstream = HTTPServer(("127.0.0.1", 0), _EchoUpstream)
    _EchoUpstream.received = []
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    upstream_origin = f"http://127.0.0.1:{upstream.server_address[1]}"

    port = _free_port()
    script = Path(__file__).resolve().parents[1] / "scripts" / "pi_capture_proxy.py"
    proxy = subprocess.Popen(
        [sys.executable, str(script), "--port", str(port), "--log-dir", str(tmp_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("capture proxy never started listening")

        token = mms_pi_capture.encode_origin(upstream_origin)
        url = f"http://127.0.0.1:{port}{mms_pi_capture.CAPTURE_PATH_PREFIX}/{token}/v1/messages"
        body = json.dumps({"content": "clean payload"}).encode("utf-8")

        import urllib.request

        request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            assert response.status == 200

        entry = json.loads((tmp_path / "capture.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert entry["raw_control_bytes"] == []
        assert not (tmp_path / f"req-{entry['index']:05d}.bin").exists()
    finally:
        proxy.terminate()
        proxy.wait(timeout=10)
        upstream.shutdown()
