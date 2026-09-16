"""The switch that makes Pilot reachable from a phone, and what it opens.

Off is the shipped default and off means no socket: a port that accepts a
connection is visible on the network whatever it answers back.
"""
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler

import pytest

from mms_web.errors import WebError
from mms_web.local_addresses import _rank, describe, local_addresses
from mms_web.remote_access import RemoteAccess, stored_mode
from mms_web.server import RemoteListeners


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def reachable(address: str, port: int) -> bool:
    probe = socket.socket()
    probe.settimeout(2)
    try:
        probe.connect((address, port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


# ── which addresses are offered ───────────────────────────────────────────

@pytest.mark.parametrize("address, rank", [
    ("192.168.23.73", 0),
    ("10.1.2.3", 0),
    ("172.20.0.9", 0),
    ("100.120.8.98", 1),      # Tailscale and similar overlays
    # The benchmark range a proxy tool uses for its own tunnel endpoint. It is
    # private by ipaddress's reckoning but it is not a LAN, and treating it as
    # one is what printed an address no phone could reach.
    ("198.18.0.1", 2),
    ("203.0.113.9", 2),
])
def test_addresses_are_ordered_by_how_likely_they_are_to_work(address, rank):
    assert _rank(address) == rank
    assert describe(address)


def test_this_machine_offers_its_own_addresses_and_no_others():
    found = local_addresses()
    assert found == list(dict.fromkeys(found)), "no duplicates"
    for address in found:
        assert not address.startswith("127."), "loopback is not remote access"
        assert not address.startswith("169.254."), "link-local means no address"
    # Sorted by rank, so the same-network address is the one offered first.
    assert [_rank(a) for a in found] == sorted(_rank(a) for a in found)


# ── the switch ────────────────────────────────────────────────────────────

def test_off_is_the_default_and_nothing_is_written(tmp_path):
    assert stored_mode(tmp_path) == "loopback"
    access = RemoteAccess(tmp_path)
    assert access.mode == "loopback"
    assert access.required is False
    assert access.addresses == [] and access.extra_binds() == []
    assert not (tmp_path / "remote-access-token").exists()


def test_the_switch_survives_a_restart(tmp_path):
    RemoteAccess(tmp_path).set_mode("lan")
    assert stored_mode(tmp_path) == "lan"
    # A fresh process reads it back and comes up open.
    assert RemoteAccess(tmp_path, stored_mode(tmp_path)).required is True
    RemoteAccess(tmp_path, "lan").set_mode("loopback")
    assert stored_mode(tmp_path) == "loopback"


def test_turning_it_off_and_on_keeps_the_same_link_working(tmp_path):
    access = RemoteAccess(tmp_path, "lan")
    first = access.token
    access.set_mode("loopback")
    assert access.token == "" and access.addresses == []
    access.set_mode("lan")
    # A link already sent to a phone should not die because someone toggled.
    assert access.token == first
    assert access.regenerate() != first


def test_a_regenerated_token_rejects_the_old_one(tmp_path):
    access = RemoteAccess(tmp_path, "lan")
    old = access.token
    access.regenerate()
    assert access.valid(old) is False
    assert access.valid(access.token) is True


# ── the sockets ───────────────────────────────────────────────────────────

class Quiet(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.end_headers()


def test_sockets_appear_and_disappear_with_the_switch():
    port = free_port()
    listeners = RemoteListeners(Quiet, port)
    try:
        assert reachable("127.0.0.1", port) is False
        listeners.sync(["127.0.0.1"])
        assert listeners.active == ["127.0.0.1"]
        assert reachable("127.0.0.1", port) is True
        listeners.sync([])
        assert listeners.active == []
        # Off is off: not a socket that answers 403.
        assert reachable("127.0.0.1", port) is False
    finally:
        listeners.close()


def test_an_address_that_cannot_be_bound_is_reported_not_raised():
    listeners = RemoteListeners(Quiet, free_port())
    try:
        listeners.sync(["203.0.113.9"])
        assert listeners.active == []
        assert "203.0.113.9" in listeners.failed
    finally:
        listeners.close()


def test_syncing_twice_does_not_rebind_what_is_already_open():
    port = free_port()
    listeners = RemoteListeners(Quiet, port)
    try:
        listeners.sync(["127.0.0.1"])
        listeners.sync(["127.0.0.1"])
        assert listeners.active == ["127.0.0.1"]
        assert listeners.failed == {}
        assert reachable("127.0.0.1", port) is True
    finally:
        listeners.close()


# ── the API the settings page uses ────────────────────────────────────────

@pytest.fixture()
def app(tmp_path):
    from mms_web.server import WebApplication

    application = WebApplication(state_root=tmp_path / "state",
                                 config_root=tmp_path / "config")
    application.listeners = RemoteListeners(Quiet, free_port())
    yield application
    application.close()


def test_the_page_sees_it_off_with_nothing_to_show(app):
    state = app.get(["remote-access"])
    assert state["enabled"] is False
    assert state["links"] == [] and state["listening"] == []
    assert state["token"] == ""


def test_turning_it_on_returns_a_link_per_reachable_address(app):
    state = app.post(["remote-access"], {"enabled": True})
    assert state["enabled"] is True and state["mode"] == "lan"
    assert state["token"]
    # Every offered link is one that actually has a socket behind it.
    for entry in state["links"]:
        if entry["kind"] == "address":
            assert entry["host"] in state["listening"]
        assert state["token"] in entry["url"]
        assert entry["detail"]
    assert state["listening"] == sorted(state["listening"])

    off = app.post(["remote-access"], {"enabled": False})
    assert off["enabled"] is False and off["listening"] == []


def test_the_token_can_only_be_replaced_while_it_is_on(app):
    with pytest.raises(WebError) as refused:
        app.post(["remote-access"], {"regenerate": True})
    assert refused.value.code == "REMOTE_ACCESS_OFF"
    app.post(["remote-access"], {"enabled": True})
    first = app.get(["remote-access"])["token"]
    assert app.post(["remote-access"], {"regenerate": True})["token"] != first


@pytest.mark.parametrize("payload", [{}, {"enabled": "yes"}, {"enabled": 1}])
def test_a_malformed_switch_is_refused(app, payload):
    with pytest.raises(WebError):
        app.post(["remote-access"], payload)


def test_the_command_line_still_wins_over_the_switch(tmp_path):
    """`--listen all` is a deliberate choice; the switch must not narrow it."""
    from mms_web.server import WebApplication

    application = WebApplication(state_root=tmp_path / "state",
                                 config_root=tmp_path / "config", listen="all")
    application.listeners = RemoteListeners(Quiet, free_port())
    try:
        state = application.post(["remote-access"], {"enabled": True})
        assert state["mode"] == "all"
        # "all" cannot enumerate what it serves, so it keeps its wildcard
        # socket and opens no extras.
        assert state["listening"] == []
        assert application.access.bind_address() == "0.0.0.0"
        # Turning the switch off must not narrow "all" either: the wildcard
        # socket cannot be recalled, so the token gate has to stay in place.
        state = application.post(["remote-access"], {"enabled": False})
        assert state["mode"] == "all"
        assert application.access.mode == "all"
        assert application.access.required is True
        assert application.access.token
    finally:
        application.close()


def test_the_stored_switch_is_written_readable_only_by_this_user(tmp_path):
    RemoteAccess(tmp_path, "lan").set_mode("lan")
    for name in ("remote-access.json", "remote-access-token"):
        assert (tmp_path / name).stat().st_mode & 0o077 == 0, name
    saved = json.loads((tmp_path / "remote-access.json").read_text(encoding="utf-8"))
    assert saved == {"mode": "lan", "hostnames": []}


def test_threads_do_not_leak_when_the_switch_is_flipped():
    port = free_port()
    before = threading.active_count()
    listeners = RemoteListeners(Quiet, port)
    for _ in range(3):
        listeners.sync(["127.0.0.1"])
        listeners.sync([])
    listeners.close()
    # Each closed listener's serve_forever returns, so the count comes back.
    for _ in range(50):
        if threading.active_count() <= before:
            break
        threading.Event().wait(0.05)
    assert threading.active_count() <= before

# ── the name a tunnel only reveals once it is running ─────────────────────

@pytest.mark.parametrize("pasted, kept", [
    # What the tunnel actually prints, pasted whole.
    ("https://wide-lions-run.trycloudflare.com", "wide-lions-run.trycloudflare.com"),
    ("https://wide-lions-run.trycloudflare.com/?k=abc", "wide-lions-run.trycloudflare.com"),
    ("PILOT.Example.COM:8443", "pilot.example.com"),
    ("  pilot.evilsngx.ccwu.cc  ", "pilot.evilsngx.ccwu.cc"),
    # Not names: an address comes from the machine itself, and the rest is junk.
    ("192.168.1.5", ""),
    ("localhost", ""),
    ("not a host", ""),
    ("", ""),
])
def test_a_pasted_tunnel_url_is_reduced_to_the_name(pasted, kept):
    from mms_web.remote_access import clean_hostname

    assert clean_hostname(pasted) == kept


def test_a_tunnel_name_takes_effect_at_once_and_survives_a_restart(tmp_path):
    """A quick tunnel's name is random per start, so requiring a restart to
    accept it would make the no-domain path unusable."""
    access = RemoteAccess(tmp_path, "lan")
    assert access.accepts("wide-lions-run.trycloudflare.com", 8765) is False
    assert access.add_hostname("https://wide-lions-run.trycloudflare.com/?k=x")
    assert access.accepts("wide-lions-run.trycloudflare.com", 8765) is True
    # And it is the first way offered: the only one that works off this network.
    first = access.links(8765)[0]
    assert first["kind"] == "hostname"
    assert first["url"].startswith("https://wide-lions-run.trycloudflare.com/")

    # A new process keeps it.
    again = RemoteAccess(tmp_path, "lan")
    assert again.accepts("wide-lions-run.trycloudflare.com", 8765) is True
    again.remove_hostname("wide-lions-run.trycloudflare.com")
    assert RemoteAccess(tmp_path, "lan").accepts(
        "wide-lions-run.trycloudflare.com", 8765) is False


def test_a_name_from_the_command_line_lasts_only_for_that_run(tmp_path):
    access = RemoteAccess(tmp_path, "lan", ("pilot.example.com",))
    assert access.accepts("pilot.example.com", 8765) is True
    assert access.saved_hostnames == ()
    # Nothing was persisted, so the next start without the flag does not answer to it.
    assert RemoteAccess(tmp_path, "lan").accepts("pilot.example.com", 8765) is False


def test_only_saved_names_can_be_taken_back_from_the_page(tmp_path):
    access = RemoteAccess(tmp_path, "lan", ("fixed.example.com",))
    access.add_hostname("added.example.com")
    kinds = {entry["host"]: entry.get("removable") for entry in access.links(8765)
             if entry["kind"] == "hostname"}
    assert kinds == {"fixed.example.com": False, "added.example.com": True}


def test_names_cannot_be_added_while_remote_access_is_off(app):
    with pytest.raises(WebError) as refused:
        app.post(["remote-access"], {"hostname": "x.example.com"})
    assert refused.value.code == "REMOTE_ACCESS_OFF"


def test_something_that_is_not_a_name_is_refused_with_a_reason(app):
    app.post(["remote-access"], {"enabled": True})
    with pytest.raises(WebError) as refused:
        app.post(["remote-access"], {"hostname": "not a host"})
    assert refused.value.code == "INVALID_HOSTNAME"


def test_the_page_can_add_and_drop_a_tunnel_name(app):
    app.post(["remote-access"], {"enabled": True})
    state = app.post(["remote-access"], {"hostname": "https://x-y-z.trycloudflare.com"})
    assert state["savedHostnames"] == ["x-y-z.trycloudflare.com"]
    assert state["links"][0]["host"] == "x-y-z.trycloudflare.com"
    dropped = app.post(["remote-access"], {"removeHostname": "x-y-z.trycloudflare.com"})
    assert dropped["savedHostnames"] == []
