"""The window that turns remote access on must not lock itself out.

Remote mode authenticates every connection, loopback included, because a
tunnel reaches this socket over loopback too (that property stays guarded by
tests/test_mms_web_remote_access.py). The switch therefore signs in the
session that flipped it, and only that one: another local tab with no cookie
still gets 401.
"""
import json
import socket
import threading
import urllib.error
import urllib.request

import pytest

from mms_web.remote_access import COOKIE, QUERY
from mms_web.server import WebApplication, create_server

# Every fixed header a response carries, in the order `_send` writes them.
# The optional `headers` list may only append; reordering or dropping any of
# these is a regression.
FIXED_HEADERS = [
    "server", "date",
    "content-type", "content-length", "cache-control",
    "x-mms-web-identity", "x-mms-web-version", "x-mms-web-state",
    "x-content-type-options", "referrer-policy", "x-frame-options",
    "content-security-policy",
]


@pytest.fixture
def serve(tmp_path, monkeypatch):
    # `HTTPServer.server_bind` resolves every address it binds with
    # socket.getfqdn(). On a machine whose reverse lookup is slow that stalls
    # the switch request for as long as DNS takes, which has nothing to do
    # with the cookie this file is about, so the lookup is pinned here.
    monkeypatch.setattr(socket, "getfqdn", lambda host="": host or "localhost")
    servers = []

    def start(listen="loopback"):
        app = WebApplication(state_root=tmp_path / f"state-{listen}-{len(servers)}",
                             config_root=tmp_path / "config", listen=listen)
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


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def call(port, path, *, method="GET", body=None, cookie=None, token=None,
         csrf=None, forwarded_proto=None):
    """One request against the real handler, headers kept in wire order."""
    url = f"http://127.0.0.1:{port}{path}" + (f"?{QUERY}={token}" if token else "")
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Host", f"127.0.0.1:{port}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
        request.add_header("Origin", f"http://127.0.0.1:{port}")
    if csrf:
        request.add_header("X-MMS-CSRF", csrf)
    if cookie:
        request.add_header("Cookie", f"{COOKIE}={cookie}")
    if forwarded_proto:
        request.add_header("X-Forwarded-Proto", forwarded_proto)
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=10) as response:
            return response.status, response.read(), list(response.headers.items())
    except urllib.error.HTTPError as error:
        return error.code, error.read(), list(error.headers.items())


def header(headers, name):
    return next((value for key, value in headers if key.lower() == name.lower()), "")


def set_cookie(headers):
    return header(headers, "Set-Cookie")


def switch(app, port, payload, **kwargs):
    """Flip the switch through real HTTP, the way the settings page does."""
    return call(port, "/api/v1/remote-access", method="POST", body=payload,
                csrf=app.csrf_token, **kwargs)


def test_turning_the_switch_on_signs_this_window_in(serve):
    """① The window that flipped it keeps working without the token in the URL."""
    app, port = serve()
    assert call(port, "/api/v1/sessions")[0] == 200

    status, _, headers = switch(app, port, {"enabled": True})
    assert status == 200
    assert app.access.required is True
    value = set_cookie(headers)
    assert value == (f"{COOKIE}={app.access.token}; Path=/; HttpOnly; "
                     "SameSite=Lax; Max-Age=31536000")
    assert "Secure" not in value

    # The same window continues: its next request carries the cookie.
    status, body, _ = call(port, "/api/v1/sessions", cookie=app.access.token)
    assert status == 200
    assert "sessions" in json.loads(body)


def test_another_local_tab_without_the_cookie_is_still_refused(serve):
    """② The regression gate: loopback must never become an exemption.

    A second tab on 127.0.0.1 has no cookie and no token, and a tunnel
    arrives looking exactly like it. Both must be told 401.
    """
    app, port = serve()
    switch(app, port, {"enabled": True})

    status, body, headers = call(port, "/api/v1/sessions")
    assert status == 401
    assert body == b"401"
    assert set_cookie(headers) == ""
    # The same request with the cookie is the one that is served.
    assert call(port, "/api/v1/sessions", cookie=app.access.token)[0] == 200


def test_rolling_the_token_signs_this_window_in_and_retires_the_old_one(serve):
    """③ 「换一个 token」 must not lock out the window that asked for it."""
    app, port = serve()
    switch(app, port, {"enabled": True})
    old = app.access.token

    status, _, headers = switch(app, port, {"regenerate": True}, cookie=old)
    assert status == 200
    fresh = app.access.token
    assert fresh and fresh != old
    assert set_cookie(headers) == (f"{COOKIE}={fresh}; Path=/; HttpOnly; "
                                   "SameSite=Lax; Max-Age=31536000")
    assert call(port, "/api/v1/sessions", cookie=fresh)[0] == 200
    assert call(port, "/api/v1/sessions", cookie=old)[0] == 401


def test_turning_it_off_restores_the_old_behaviour(serve):
    """④ Off means off: no token required, no cookie involved."""
    app, port = serve()
    switch(app, port, {"enabled": True})

    status, _, headers = switch(app, port, {"enabled": False}, cookie=app.access.token)
    assert status == 200
    assert app.access.required is False
    assert set_cookie(headers) == ""
    assert call(port, "/api/v1/sessions")[0] == 200


def test_the_token_link_hands_out_the_same_cookie_shape(serve):
    """One gate, one cookie: the link and the switch cannot drift apart."""
    app, port = serve()
    _, _, switched = switch(app, port, {"enabled": True})
    token = app.access.token

    status, _, headers = call(port, "/api/v1/sessions", token=token)
    assert status == 302
    assert set_cookie(headers) == set_cookie(switched)

    # An https tunnel ahead marks both Secure; without it neither is.
    status, _, headers = call(port, "/api/v1/sessions", token=token,
                              forwarded_proto="https")
    assert status == 302
    assert set_cookie(headers).endswith("; Secure")
    assert set_cookie(headers) == (f"{COOKIE}={token}; Path=/; HttpOnly; "
                                   "SameSite=Lax; Max-Age=31536000; Secure")


def test_the_switch_cookie_is_secure_only_behind_an_https_tunnel(serve):
    app, port = serve()
    _, _, plain = switch(app, port, {"enabled": True})
    assert "; Secure" not in set_cookie(plain)

    status, _, forwarded = switch(app, port, {"regenerate": True},
                                  cookie=app.access.token, forwarded_proto="https")
    assert status == 200
    assert set_cookie(forwarded).endswith("; Secure")


def test_only_the_switch_and_the_token_roll_sign_the_caller_in(serve):
    """Hostnames and turning it off do not touch the token, so no cookie."""
    app, port = serve()
    switch(app, port, {"enabled": True})
    assert call(port, "/api/v1/sessions", cookie=app.access.token)[0] == 200

    for payload in ({"hostname": "x-y-z.trycloudflare.com"},
                    {"removeHostname": "x-y-z.trycloudflare.com"},
                    {"enabled": False}):
        status, _, headers = switch(app, port, payload, cookie=app.access.token)
        assert status == 200, payload
        assert set_cookie(headers) == "", payload


def test_a_response_without_extra_headers_keeps_every_fixed_header(serve):
    """Plan A changes the one response writer, so prove nothing else moved."""
    app, port = serve()
    status, _, headers = call(port, "/api/v1/sessions")
    assert status == 200
    assert [name.lower() for name, _ in headers] == FIXED_HEADERS
    assert header(headers, "Content-Type") == "application/json; charset=utf-8"
    assert header(headers, "Cache-Control") == "no-store"
    assert header(headers, "X-Content-Type-Options") == "nosniff"
    assert header(headers, "Referrer-Policy") == "no-referrer"
    assert header(headers, "X-Frame-Options") == "DENY"
    assert header(headers, "Content-Security-Policy") == (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
    assert header(headers, "X-MMS-Web-Version")
    assert header(headers, "X-MMS-Web-Identity")
    assert header(headers, "X-MMS-Web-State")


def test_the_sign_in_cookie_is_appended_after_the_fixed_headers(serve):
    app, port = serve()
    _, _, headers = switch(app, port, {"enabled": True})
    assert [name.lower() for name, _ in headers] == FIXED_HEADERS + ["set-cookie"]


def test_all_mode_keeps_the_switch_a_no_op(serve):
    """`--listen all` is a command-line choice; the switch must not widen it."""
    app, port = serve("all")
    status, _, headers = switch(app, port, {"enabled": True}, cookie=app.access.token)
    assert status == 200
    assert app.access.mode == "all"
    assert set_cookie(headers) == ""
