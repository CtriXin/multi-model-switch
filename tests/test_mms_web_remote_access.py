"""The gate that lets a phone reach Pilot, and keeps everyone else out."""
import json
from pathlib import Path
import socket
import threading
import urllib.error
import urllib.request

import pytest

from mms_web.remote_access import COOKIE, QUERY, RemoteAccess
from mms_web.server import WebApplication, create_server


@pytest.fixture
def serve(tmp_path):
    servers = []

    def start(listen="loopback", hostnames=()):
        app = WebApplication(state_root=tmp_path / f"state-{listen}-{len(servers)}",
                             config_root=tmp_path / "config",
                             listen=listen, hostnames=hostnames)
        server = create_server(app, tmp_path, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, app))
        return app, server.server_address[1]

    yield start
    for server, app in servers:
        server.shutdown()
        server.server_close()
        app.close()


def fetch(port, path="/api/v1/sessions", host=None, token=None, cookie=None, redirect=True):
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}" + (f"?{QUERY}={token}" if token else ""))
    request.add_header("Host", host or f"127.0.0.1:{port}")
    if cookie:
        request.add_header("Cookie", f"{COOKIE}={cookie}")
    opener = urllib.request.build_opener(
        *([] if redirect else [type("NoRedirect", (urllib.request.HTTPRedirectHandler,),
                                    {"redirect_request": lambda *a, **k: None})]))
    try:
        with opener.open(request, timeout=10) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read(), dict(error.headers)


def test_loopback_only_needs_no_token_and_binds_nowhere_else(serve):
    """The default must behave exactly as it did before this gate existed."""
    app, port = serve()
    assert app.access.required is False
    assert app.access.bind_address() == "127.0.0.1"
    status, body, _ = fetch(port)
    assert status == 200
    assert "sessions" in json.loads(body)
    # Nothing to leak, so nothing is written.
    assert not (app.state_root / "remote-access-token").exists()


def test_reaching_beyond_loopback_requires_the_token(serve):
    app, port = serve("all")
    assert app.access.required is True
    token_file = app.state_root / "remote-access-token"
    assert token_file.read_text().strip() == app.access.token
    # Readable only by its owner: it is the whole gate.
    assert token_file.stat().st_mode & 0o077 == 0

    assert fetch(port)[0] == 401
    assert fetch(port, cookie="wrong-token")[0] == 401
    assert fetch(port, cookie=app.access.token)[0] == 200


def test_a_token_in_the_query_becomes_a_cookie_and_leaves_the_url(serve):
    """So the token does not sit in history, the address bar or a Referer."""
    app, port = serve("all")
    status, _, headers = fetch(port, "/api/v1/sessions", token=app.access.token, redirect=False)
    assert status == 302
    assert headers["Location"] == "/api/v1/sessions"
    cookie = headers["Set-Cookie"]
    assert cookie.startswith(f"{COOKIE}={app.access.token}")
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_a_rejected_request_says_nothing_about_the_service(serve):
    app, port = serve("all")
    status, body, _ = fetch(port, "/", cookie="nope")
    assert status == 401
    assert body == b"401"


def test_the_lan_mode_binds_this_machine_only_not_the_wildcard(tmp_path):
    access = RemoteAccess(tmp_path, "lan")
    address = access.bind_address()
    assert address != "0.0.0.0"
    # Either a real address on this machine, or loopback when it has none.
    assert address == access.lan_address or address == "127.0.0.1"


def test_a_configured_hostname_is_accepted_with_or_without_the_port(tmp_path):
    access = RemoteAccess(tmp_path, "all", ("pilot.example.com",))
    assert access.accepts("pilot.example.com", 8765)
    assert access.accepts("pilot.example.com:8765", 8765)
    assert access.accepts("PILOT.EXAMPLE.COM", 8765)
    assert not access.accepts("evil.example.com", 8765)


def test_loopback_mode_refuses_every_other_host(serve):
    app, port = serve()
    assert fetch(port, host="pilot.example.com")[0] == 403
    assert fetch(port, host=f"localhost:{port}")[0] == 200


def test_the_token_is_stable_across_restarts(tmp_path):
    first = RemoteAccess(tmp_path, "lan")
    assert RemoteAccess(tmp_path, "all").token == first.token


def test_an_unknown_listen_mode_is_refused(tmp_path):
    with pytest.raises(ValueError):
        RemoteAccess(tmp_path, "everywhere")


def test_the_link_carries_the_token_and_prefers_the_public_hostname(tmp_path):
    assert RemoteAccess(tmp_path, "loopback").link(8765) == "http://127.0.0.1:8765/"
    access = RemoteAccess(tmp_path, "all", ("pilot.example.com",))
    assert access.link(8765) == f"https://pilot.example.com/?{QUERY}={access.token}"
