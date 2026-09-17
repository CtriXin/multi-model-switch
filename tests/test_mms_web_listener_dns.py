"""Binding Pilot listeners never waits for reverse DNS (T8e)."""
import random
import socket
import time
from http.server import BaseHTTPRequestHandler

from mms_web.server import RemoteListeners, WebApplication, create_server


def _port():
    ports = list(range(61000, 62001))
    random.shuffle(ports)
    for port in ports:
        with socket.socket() as probe:
            try:
                probe.bind(('127.0.0.1', port))
                return port
            except OSError:
                pass
    raise RuntimeError('no isolated test port available')


def _slow_dns(monkeypatch):
    calls = []
    def slow(host=''):
        calls.append(host)
        time.sleep(.3)
        return host
    monkeypatch.setattr(socket, 'getfqdn', slow)
    return calls


def test_main_listener_binds_without_reverse_dns(tmp_path, monkeypatch):
    import mms_web.server as server_module
    monkeypatch.setattr(server_module, '_adapter', lambda *a, **kw: None)
    app = WebApplication(state_root=tmp_path / 'state', config_root=tmp_path / 'config')
    calls = _slow_dns(monkeypatch)
    server = create_server(app, tmp_path, _port())
    try:
        assert calls == []
        assert server.server_name == '127.0.0.1'
        assert server.server_port == server.server_address[1]
    finally:
        server.server_close()
        app.close()


def test_remote_listener_sync_does_not_wait_for_reverse_dns(monkeypatch):
    calls = _slow_dns(monkeypatch)
    listeners = RemoteListeners(BaseHTTPRequestHandler, _port())
    started = time.monotonic()
    try:
        listeners.sync(['127.0.0.1', '127.0.0.1'])
        elapsed = time.monotonic() - started
        assert calls == [], 'the remote constructor must use the same no-DNS server'
        assert elapsed < .25
        assert listeners.active == ['127.0.0.1'] and listeners.failed == {}
    finally:
        listeners.close()


def test_removing_and_closing_listeners_releases_the_actual_socket():
    listeners = RemoteListeners(BaseHTTPRequestHandler, _port())
    for close in (lambda: listeners.sync([]), listeners.close):
        listeners.sync(['127.0.0.1'])
        opened = listeners._servers['127.0.0.1']  # retain it: GC cannot conceal a missing close
        close()
        assert opened.socket.fileno() == -1
        assert listeners.active == []
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', listeners._port))
