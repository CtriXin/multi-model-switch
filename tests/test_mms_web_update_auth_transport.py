"""Guardian credentials must stay on the selected local service connection."""
import contextlib
import random
import socketserver
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from mms_web import update_handoff as handoff
from mms_web.errors import WebError


class LiteralServer(ThreadingHTTPServer):
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


@contextlib.contextmanager
def listener(status=200, headers=None):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            seen.append({"method": self.command, "path": self.path,
                         "cookie": self.headers.get("Cookie"),
                         "csrf": self.headers.get("X-MMS-CSRF")})
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(status)
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(b"{}")

        do_POST = do_GET

    for port in random.sample(range(61000, 62000), 100):
        try:
            server = LiteralServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    else:
        pytest.fail("no isolated test port available")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


@pytest.fixture
def state(tmp_path, monkeypatch):
    for key in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
                "all_proxy", "ALL_PROXY", "no_proxy", "NO_PROXY", "REQUEST_METHOD"):
        monkeypatch.delenv(key, raising=False)
    root = tmp_path / "state"
    root.mkdir()
    (root / "remote-access-token").write_text("fixture-only-guardian-secret")
    return root


@pytest.mark.parametrize("body", [None, {"token": "fixture-update-token"}], ids=["GET", "POST"])
def test_guardian_http_never_uses_inherited_proxy(state, monkeypatch, body):
    with listener() as (target, received), listener() as (proxy, proxy_seen):
        monkeypatch.setenv("http_proxy", f"http://127.0.0.1:{proxy}")
        monkeypatch.setenv("no_proxy", "unmatched.fixture.invalid")
        handoff.http(target, "update/identity", body, "fixture-csrf", state_root=state)
        assert proxy_seen == [], "guardian credentials reached the inherited proxy"
        assert received == [{"method": "GET" if body is None else "POST",
                             "path": "/api/v1/update/identity",
                             "cookie": "mms_pilot_key=fixture-only-guardian-secret",
                             "csrf": "fixture-csrf"}]


@pytest.mark.parametrize("body", [None, {"token": "fixture-update-token"}], ids=["GET", "POST"])
@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
def test_guardian_http_never_forwards_cookie_on_redirect(state, monkeypatch, body, code):
    monkeypatch.setenv("no_proxy", "*")
    with listener() as (sink, sink_seen):
        with listener(code, {"Location": f"http://127.0.0.1:{sink}/sink"}) as (source, source_seen):
            with pytest.raises((WebError, urllib.error.HTTPError)):
                handoff.http(source, "update/identity", body, "fixture-csrf", state_root=state)
            assert source_seen[0]["cookie"] == "mms_pilot_key=fixture-only-guardian-secret"
            assert sink_seen == []
