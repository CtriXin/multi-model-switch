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
import os
import secrets
import socket
from pathlib import Path

COOKIE = "mms_pilot_key"
QUERY = "k"
# Long enough that guessing is not a strategy, short enough to fit a QR code
# alongside the address.
_TOKEN_BYTES = 32
_MODES = ("loopback", "lan", "all")


def _lan_address() -> str:
    """This machine's address on its own network, or empty if it has none."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Never actually sends: connect on UDP only selects the route, which
        # is how the kernel tells us which local address a peer would see.
        probe.connect(("192.0.2.1", 9))
        return probe.getsockname()[0]
    except OSError:
        return ""
    finally:
        probe.close()


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


class RemoteAccess:
    """Which addresses may reach Pilot, and the token they must carry."""

    def __init__(self, state_root: str | os.PathLike, mode: str = "loopback",
                 hostnames: tuple[str, ...] = ()):
        if mode not in _MODES:
            raise ValueError(f"unknown listen mode: {mode}")
        self.mode = mode
        self.hostnames = tuple(dict.fromkeys(h.strip().lower() for h in hostnames if h.strip()))
        self.lan_address = _lan_address() if mode == "lan" else ""
        # Loopback-only keeps today's behaviour exactly, token included: there
        # is nothing to gate, and requiring one would break every existing
        # bookmark for no gain.
        self.token = "" if mode == "loopback" else _load_or_create(
            Path(state_root) / "remote-access-token")

    @property
    def required(self) -> bool:
        return bool(self.token)

    def bind_address(self) -> str:
        """The address to listen on.

        "lan" resolves to this machine's own address rather than the wildcard,
        so choosing the LAN does not also expose every other interface. Only
        an explicit "all" binds the wildcard.
        """
        if self.mode == "loopback":
            return "127.0.0.1"
        if self.mode == "all":
            return "0.0.0.0"
        return self.lan_address or "127.0.0.1"

    def allowed_hosts(self, port: int) -> set[str]:
        """Host header values this server answers to."""
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.mode != "loopback":
            for name in self.hostnames:
                # A tunnel arrives on the standard port, so accept the bare
                # hostname as well as an explicit one.
                hosts.add(name)
                hosts.add(f"{name}:{port}")
            address = self.lan_address or (_lan_address() if self.mode == "all" else "")
            if address:
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

    def link(self, port: int) -> str:
        """The address to hand to a phone, token included."""
        host = self.hostnames[0] if self.hostnames else (self.bind_address() or "127.0.0.1")
        scheme = "https" if self.hostnames else "http"
        base = host if self.hostnames else f"{host}:{port}"
        return f"{scheme}://{base}/" + (f"?{QUERY}={self.token}" if self.required else "")
