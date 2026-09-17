"""Binding a listener must be a local operation: no reverse DNS, no stall.

The remote-access switch opens one socket per LAN address while the caller
holds the mutation lock. The stock ``HTTPServer.server_bind`` resolves
``socket.getfqdn(host)`` first — a reverse DNS query that blocks for the
resolver's full timeout (~30s) on networks whose router does not answer PTR
records. One such query froze every request in the Pilot behind the switch.
"""
import socket
import time
from http.server import BaseHTTPRequestHandler
from unittest import mock

from mms_web.server import RemoteListeners, WebApplication, create_server


class _QuietHandler(BaseHTTPRequestHandler):
    """Smallest handler: these tests never send it a real request."""

    def log_message(self, *_args):
        return

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")


def _unused_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _recording_fqdn(calls, delay):
    """A getfqdn stand-in that records calls and stalls, like a dead PTR."""

    def fake(host):
        calls.append(host)
        time.sleep(delay)
        return "stalled.invalid"

    return fake


def test_main_server_bind_does_no_reverse_dns(tmp_path):
    """The always-on socket (:690) must bind without resolving its name."""
    calls = []
    app = WebApplication(state_root=tmp_path / "state", config_root=tmp_path / "config")
    with mock.patch("socket.getfqdn", _recording_fqdn(calls, 0.2)):
        server = create_server(app, tmp_path, 0)
    try:
        assert calls == []
        assert server.server_name == "127.0.0.1"
    finally:
        server.server_close()
        app.close()


def test_remote_listener_bind_does_no_reverse_dns():
    """The per-address switch sockets (:728) must bind without getfqdn."""
    calls = []
    listeners = RemoteListeners(_QuietHandler, _unused_port())
    with mock.patch("socket.getfqdn", _recording_fqdn(calls, 0.2)):
        listeners.sync(["127.0.0.1"])
    try:
        assert calls == []
        assert listeners.active == ["127.0.0.1"]
    finally:
        listeners.close()


def test_sync_stays_fast_when_reverse_dns_would_stall():
    """With a dead-PTR resolver under the patch, sync still returns at once.

    Before the fix the query inside server_bind stalled the whole call for
    the resolver timeout while the switch held the mutation lock.
    """
    listeners = RemoteListeners(_QuietHandler, _unused_port())
    with mock.patch("socket.getfqdn", _recording_fqdn([], 1.5)):
        started = time.monotonic()
        listeners.sync(["127.0.0.1"])
        elapsed = time.monotonic() - started
    try:
        assert listeners.active == ["127.0.0.1"]
        assert elapsed < 1.0
    finally:
        listeners.close()


def test_close_actually_releases_the_port():
    """After close() nothing is listening: the subclass lost no cleanup."""
    port = _unused_port()
    listeners = RemoteListeners(_QuietHandler, port)
    listeners.sync(["127.0.0.1"])
    # Hold the reference: if _close() skips server_close(), garbage
    # collection would silently close the socket and mask the leak.
    server = listeners._servers["127.0.0.1"]
    with socket.create_connection(("127.0.0.1", port), timeout=2):
        pass
    real_close = server.server_close
    close_calls = []

    def _spied_close():
        close_calls.append(True)
        real_close()

    server.server_close = _spied_close
    listeners.close()
    assert close_calls, "close() must reach server_close(), not just shutdown()"
    probe = socket.socket()
    probe.settimeout(2)
    try:
        assert probe.connect_ex(("127.0.0.1", port)) != 0
    finally:
        probe.close()
