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


def test_the_setup_web_ui_also_binds_without_reverse_dns(monkeypatch):
    """The config WebUI is a second server in this repo. T8e converted the two
    Pilot listeners and left this one on the stock bind, which still blocks for
    30s when `mms config web --host <LAN address>` is used."""
    from mms_config_web import ConfigWebApp
    from mms_config_web_server import create_setup_server

    # Go through the real factory, not the class: a test that instantiates
    # SetupHTTPServer itself stays green when the call site is reverted to the
    # stock server, which is exactly the bug this guards.
    calls = _slow_dns(monkeypatch)
    started = time.monotonic()
    server = create_setup_server(ConfigWebApp({}, command_name='mms'), host='127.0.0.1', port=_port())
    try:
        assert calls == [], 'the setup WebUI must use the same no-DNS bind'
        assert time.monotonic() - started < .25
        assert server.server_name == '127.0.0.1'
        assert server.server_port == server.server_address[1]
    finally:
        server.server_close()
    assert server.socket.fileno() == -1


def test_actual_config_web_entry_uses_and_closes_the_no_dns_server(monkeypatch):
    import mms_config_web_server as module
    from mms_config_web import ConfigWebApp

    calls = _slow_dns(monkeypatch)
    bound = []
    factory = module.create_setup_server
    def bind(*args, **kwargs):
        server = factory(*args, **kwargs)
        bound.append(server)
        return server
    monkeypatch.setattr(module, "create_setup_server", bind)
    class NoLoopThread:
        def __init__(self, *args, **kwargs): pass
        def start(self): pass
        def join(self, *args, **kwargs): pass
    # Keep the real entry point and bind; omit its perpetual serving loop.
    monkeypatch.setattr(module.threading, "Thread", NoLoopThread)
    app = ConfigWebApp({}, command_name="mms")
    url = module.serve_config_web(app, host="127.0.0.1", port=_port(), open_browser=False)
    assert calls == []
    assert len(bound) == 1
    assert bound[0].RequestHandlerClass.app is app
    assert url == f"http://127.0.0.1:{bound[0].server_port}/"
    assert bound[0].socket.fileno() == -1
