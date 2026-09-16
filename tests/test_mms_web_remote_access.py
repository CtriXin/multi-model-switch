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


def fetch(port, path="/api/v1/sessions", host=None, token=None, cookie=None,
          redirect=True, remote=False):
    """Exercise both forwarding-header and plain TCP tunnel requests."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}" + (f"?{QUERY}={token}" if token else ""))
    request.add_header("Host", host or f"127.0.0.1:{port}")
    if remote:
        request.add_header("X-Forwarded-For", "203.0.113.9")
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

    assert fetch(port, remote=True)[0] == 401
    assert fetch(port, cookie="wrong-token", remote=True)[0] == 401
    assert fetch(port, cookie=app.access.token, remote=True)[0] == 200


def test_a_token_in_the_query_becomes_a_cookie_and_leaves_the_url(serve):
    """So the token does not sit in history, the address bar or a Referer."""
    app, port = serve("all")
    status, _, headers = fetch(port, "/api/v1/sessions", token=app.access.token,
                               redirect=False, remote=True)
    assert status == 302
    assert headers["Location"] == "/api/v1/sessions"
    cookie = headers["Set-Cookie"]
    assert cookie.startswith(f"{COOKIE}={app.access.token}")
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_a_rejected_request_says_nothing_about_the_service(serve):
    app, port = serve("all")
    status, body, _ = fetch(port, "/", cookie="nope", remote=True)
    assert status == 401
    assert body == b"401"


def test_lan_mode_keeps_loopback_and_opens_one_socket_per_address(tmp_path):
    """The local browser and any tunnel arrive on loopback and must not move.

    Each of this machine's own addresses gets its own socket instead, so
    switching off closes them and leaves nothing listening.
    """
    access = RemoteAccess(tmp_path, "lan")
    assert access.bind_address() == "127.0.0.1"
    assert access.extra_binds() == access.addresses
    assert access.accepts("127.0.0.1:8765", 8765)
    for address in access.addresses:
        assert access.accepts(f"{address}:8765", 8765)
    # Unlike "all", an arbitrary address on the serving port is not answered.
    assert not access.accepts("203.0.113.9:8765", 8765)
    everything = RemoteAccess(tmp_path, "all")
    assert everything.accepts("203.0.113.9:8765", 8765)
    # "all" cannot enumerate what it serves, so it keeps the wildcard socket
    # and needs no extras.
    assert everything.bind_address() == "0.0.0.0"
    assert everything.extra_binds() == []


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


def test_remote_mode_requires_a_token_even_without_forwarding_headers(serve):
    """A raw TCP tunnel is indistinguishable from a local browser."""
    app, port = serve("all")
    assert app.access.required is True
    assert fetch(port)[0] == 401
    assert fetch(port, cookie=app.access.token)[0] == 200
    assert fetch(port, token=app.access.token, redirect=False)[0] == 302


def test_a_tunnel_also_arrives_from_loopback_and_is_not_exempt(serve):
    """cloudflared connects from 127.0.0.1, so the peer address cannot decide it."""
    app, port = serve("all")
    for header in ("X-Forwarded-For", "X-Forwarded-Proto", "CF-Connecting-IP"):
        request = urllib.request.Request(f"http://127.0.0.1:{port}/api/v1/sessions")
        request.add_header("Host", f"127.0.0.1:{port}")
        request.add_header(header, "203.0.113.9" if header != "X-Forwarded-Proto" else "https")
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=10)
        assert caught.value.code == 401, header
        # The same request with the token is served.
        request.add_header("Cookie", f"{COOKIE}={app.access.token}")
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.status == 200


def _post(port, host, origin, token, csrf):
    request = urllib.request.Request(f"http://127.0.0.1:{port}/api/v1/does-not-exist",
                                     data=b"{}", method="POST")
    request.add_header("Host", host)
    request.add_header("Origin", origin)
    request.add_header("X-MMS-CSRF", csrf)
    request.add_header("Content-Type", "application/json")
    request.add_header("Cookie", f"{COOKIE}={token}")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def test_all_mode_accepts_a_mutation_from_any_interface_it_serves(serve):
    """Browsers send Origin on every POST; it must pass wherever Host passes."""
    app, port = serve("all")
    host = f"10.0.0.5:{port}"  # a second interface the server never detected
    status, body = _post(port, host, f"http://{host}", app.access.token, app.csrf_token)
    assert status != 403, body
    assert b"INVALID_ORIGIN" not in body
    # A page served from somewhere else is still refused.
    status, body = _post(port, host, "http://evil.example", app.access.token, app.csrf_token)
    assert status == 403 and b"INVALID_ORIGIN" in body


def test_lan_mode_still_narrows_the_origin_by_host(serve):
    app, port = serve("lan")
    status, body = _post(port, f"127.0.0.1:{port}", f"http://10.0.0.5:{port}", app.access.token, app.csrf_token)
    assert status == 403 and b"INVALID_ORIGIN" in body
