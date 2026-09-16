"""The gate for reaching Pilot from anywhere but this machine.

Pilot's security model has been the loopback bind itself: it listens on
127.0.0.1 and refuses any Host header but localhost. That is enough while the
only client is a browser on the same machine, and it stays the default here.

The moment the address is reachable from a phone, whether over the LAN or
through a tunnel, that is no longer true. A public hostname is not a secret:
every certificate Cloudflare issues is published to Certificate Transparency
logs within minutes, and those logs are continuously scraped for subdomains.
So reaching beyond loopback requires a token, and the token is the whole gate:
one link carries it, the browser keeps it, and there is no account, no email
and no third party in the path.
"""
from __future__ import annotations
import ipaddress
import json
import os
import re
import secrets
from pathlib import Path

from .local_addresses import describe, local_addresses

COOKIE = "mms_pilot_key"
QUERY = "k"
# Long enough that guessing is not a strategy, short enough to fit a QR code
# alongside the address.
_TOKEN_BYTES = 32
_MODES = ("loopback", "lan", "all")
_PREFERENCE = "remote-access.json"
_TOKEN_FILE = "remote-access-token"
# A DNS name and nothing else: no scheme, no port, no path. A tunnel hands out
# a name like "wide-lions-run.trycloudflare.com", and that is all that goes in
# the allowlist.
_HOSTNAME = re.compile(r"^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?"
                       r"(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")


def clean_hostname(value: str) -> str:
    """A hostname the allowlist can hold, or "" when it is not one.

    People paste what the tunnel printed, which is a URL. The scheme, port and
    path are stripped rather than refused, because refusing a paste that
    contains the right answer is just an obstacle.
    """
    name = str(value or "").strip().lower()
    name = re.sub(r"^[a-z][a-z0-9+.-]*://", "", name)
    name = name.split("/")[0].split("?")[0]
    name = name.rsplit(":", 1)[0] if name.count(":") == 1 else name
    name = name.strip(".")
    if not _HOSTNAME.match(name):
        return ""
    try:
        # An address is not a hostname; those come from the machine itself.
        ipaddress.ip_address(name)
        return ""
    except ValueError:
        return name


def _load_or_create(path: Path) -> str:
    try:
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except OSError:
        pass
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    path.parent.mkdir(parents=True, exist_ok=True)
    # The token is the only thing standing between the internet and an agent
    # with write access to this machine, so it is never group or world
    # readable, and it is written before it is announced.
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as handle:
        handle.write(token + "\n")
    return token


def _stored(state_root: str | os.PathLike) -> dict:
    try:
        saved = json.loads((Path(state_root) / _PREFERENCE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return saved if isinstance(saved, dict) else {}


def stored_mode(state_root: str | os.PathLike) -> str:
    """The mode the switch was last left in, or loopback.

    Off by default and off after a fresh install: opening this machine to its
    network is a decision, not something that happens because Pilot was
    installed.
    """
    mode = str(_stored(state_root).get("mode") or "loopback")
    return mode if mode in _MODES else "loopback"


class RemoteAccess:
    """Which addresses may reach Pilot, and the token they must carry."""

    def __init__(self, state_root: str | os.PathLike, mode: str = "loopback",
                 hostnames: tuple[str, ...] = ()):
        if mode not in _MODES:
            raise ValueError(f"unknown listen mode: {mode}")
        self.state_root = Path(state_root)
        self.mode = mode
        # Names given on the command line hold for this run only. Names added
        # from the page are kept, because a tunnel's hostname is only known
        # after it starts and restarting Pilot to accept it is a silly step.
        self.fixed_hostnames = tuple(dict.fromkeys(
            clean_hostname(h) for h in hostnames if clean_hostname(h)))
        self.saved_hostnames = tuple(dict.fromkeys(
            clean_hostname(h) for h in _stored(state_root).get("hostnames") or []
            if clean_hostname(h)))
        self.addresses: list[str] = []
        self.token = ""
        self._apply()

    def _apply(self) -> None:
        """Bring addresses and token in line with the current mode."""
        # Every address, not the default route's one: a machine with a VPN or
        # Tailscale reaches the internet through an address a phone on the same
        # Wi-Fi cannot use, and someone continuing on a second computer may
        # want the overlay address instead. Only they know which.
        self.addresses = local_addresses() if self.mode != "loopback" else []
        # Loopback-only keeps today's behaviour exactly, token included: there
        # is nothing to gate, and requiring one would break every existing
        # bookmark for no gain.
        self.token = "" if self.mode == "loopback" else _load_or_create(
            self.state_root / _TOKEN_FILE)

    @property
    def hostnames(self) -> tuple[str, ...]:
        """Every name this server answers to, whatever put it there."""
        return tuple(dict.fromkeys(self.fixed_hostnames + self.saved_hostnames))

    def remember(self) -> None:
        """Persist the choices so a restart comes back the way it was left."""
        path = self.state_root / _PREFERENCE
        path.parent.mkdir(parents=True, exist_ok=True)
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as handle:
            json.dump({"mode": self.mode, "hostnames": list(self.saved_hostnames)}, handle)

    def add_hostname(self, value: str) -> str:
        """Answer to one more name from now on, or "" if it is not a name.

        A tunnel is pointless if its hostname is refused, and the name is only
        knowable after the tunnel is up, so this takes effect immediately
        rather than at the next start.
        """
        name = clean_hostname(value)
        if not name:
            return ""
        if name not in self.saved_hostnames:
            self.saved_hostnames = self.saved_hostnames + (name,)
            self.remember()
        return name

    def remove_hostname(self, value: str) -> None:
        name = clean_hostname(value)
        if name in self.saved_hostnames:
            self.saved_hostnames = tuple(h for h in self.saved_hostnames if h != name)
            self.remember()

    def set_mode(self, mode: str) -> None:
        if mode not in _MODES:
            raise ValueError(f"unknown listen mode: {mode}")
        self.mode = mode
        self._apply()
        self.remember()

    def refresh(self) -> None:
        """Re-read this machine's addresses, which change with the network."""
        self._apply()

    def regenerate(self) -> str:
        """Replace the token, which makes every link handed out so far dead."""
        path = self.state_root / _TOKEN_FILE
        try:
            path.unlink()
        except OSError:
            pass
        self._apply()
        return self.token

    @property
    def required(self) -> bool:
        return bool(self.token)

    def bind_address(self) -> str:
        """The address the always-on socket listens on.

        Loopback, except in "all" mode. The local browser and any tunnel both
        arrive here, and they must keep working whatever the switch says.

        "lan" does not widen this socket. It opens one more socket per address
        instead, so switching off closes them and leaves nothing listening: a
        port that accepts a connection is visible on the network whatever it
        answers, and "off" should mean off. "all" keeps the wildcard, because
        its whole point is addresses that cannot be enumerated ahead of time.
        """
        return "0.0.0.0" if self.mode == "all" else "127.0.0.1"

    def extra_binds(self) -> list[str]:
        """Addresses that need their own socket for this mode."""
        return list(self.addresses) if self.mode == "lan" else []

    def allowed_hosts(self, port: int) -> set[str]:
        """Host header values this server answers to."""
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.mode != "loopback":
            for name in self.hostnames:
                # A tunnel arrives on the standard port, so accept the bare
                # hostname as well as an explicit one.
                hosts.add(name)
                hosts.add(f"{name}:{port}")
            for address in self.addresses:
                hosts.add(f"{address}:{port}")
        return hosts

    def accepts(self, host: str | None, port: int) -> bool:
        host = (host or "").strip().lower()
        if host in self.allowed_hosts(port):
            return True
        if self.mode != "all":
            return False
        # Binding every interface means the machine's addresses are not known
        # ahead of time, so accept any literal IP on the serving port. The
        # token, not the Host header, is the gate in that mode.
        name, _, given = host.rpartition(":")
        try:
            ipaddress.ip_address(name.strip("[]"))
        except ValueError:
            return False
        return given == str(port)

    def valid(self, presented: str | None) -> bool:
        if not self.required:
            return True
        return bool(presented) and secrets.compare_digest(presented, self.token)

    def link(self, port: int, host: str = "") -> str:
        """One address to open, token included.

        Without a host it picks the best guess: a configured hostname reaches
        this machine from anywhere, and otherwise the first address, which is
        the LAN one when there is one.
        """
        chosen = host or (self.hostnames[0] if self.hostnames
                          else (self.addresses[0] if self.addresses else "127.0.0.1"))
        named = chosen in self.hostnames
        base = chosen if named else f"{chosen}:{port}"
        scheme = "https" if named else "http"
        return f"{scheme}://{base}/" + (f"?{QUERY}={self.token}" if self.required else "")

    def state(self, port: int) -> dict:
        """What the settings page shows: the switch, the ways in, the token."""
        return {
            "mode": self.mode,
            "enabled": self.mode != "loopback",
            "token": self.token,
            "hostnames": list(self.hostnames),
            "savedHostnames": list(self.saved_hostnames),
            "links": self.links(port),
            "port": port,
        }

    def links(self, port: int) -> list[dict]:
        """Every way in, for a page that lets someone pick.

        A hostname comes first when one is configured: it is the only entry
        that works away from this network.
        """
        entries = [{"host": name, "url": self.link(port, name), "kind": "hostname",
                    "detail": "任何网络下都能打开",
                    "removable": name in self.saved_hostnames}
                   for name in self.hostnames]
        entries += [{"host": address, "url": self.link(port, address), "kind": "address",
                     "detail": describe(address)} for address in self.addresses]
        return entries
