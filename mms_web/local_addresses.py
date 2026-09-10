"""Every address another device could reach this machine at.

Asking the kernel which local address it would use to reach the internet gives
one answer, the default route's, and on any machine running a VPN, Tailscale or
Docker that is not the address a phone on the same Wi-Fi can use. The link
Pilot printed was then unreachable and its own Host allowlist rejected the
address that would have worked.

So the whole set is enumerated instead, and the caller decides what to show.
Hostname lookup is not a way to get there: this machine answers to "bogon",
which resolves to nothing at all.
"""
from __future__ import annotations
import ipaddress
import re
import shutil
import socket
import subprocess

# `ip` on Linux, `ifconfig` on macOS and BSD. Both print one `inet <addr>` per
# address, which is all that is needed; the rest of the line differs and is
# not parsed.
_INET = re.compile(r"\binet\s+(\d+\.\d+\.\d+\.\d+)")
_TIMEOUT = 4


def _from_os() -> list[str]:
    for command in (["ip", "-4", "-o", "addr"], ["ifconfig", "-a"]):
        if not shutil.which(command[0]):
            continue
        try:
            output = subprocess.run(command, capture_output=True, text=True,
                                    timeout=_TIMEOUT).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        found = _INET.findall(output or "")
        if found:
            return found
    return []


def _default_route() -> list[str]:
    """The one address the kernel would use to reach the internet.

    Kept as a fallback for a machine with neither tool, and never sends: a UDP
    connect only selects the route.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        return [probe.getsockname()[0]]
    except OSError:
        return []
    finally:
        probe.close()


# The three ranges a home or office network actually hands out (RFC 1918).
# Not ipaddress.is_private, which also covers the benchmark range a proxy tool
# on this machine uses for its own tunnel endpoint: that is not a LAN, and
# offering it as one is how the wrong address got printed in the first place.
_LAN_RANGES = tuple(ipaddress.ip_network(cidr) for cidr in
                    ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
# Where Tailscale and similar overlays live.
_OVERLAY = ipaddress.ip_network("100.64.0.0/10")


def _rank(address: str) -> int:
    """Most likely to be the one someone wants, first.

    A LAN address is the same-Wi-Fi case and the common one. An overlay address
    reaches across networks and is worth offering next. Anything else is a
    tunnel endpoint that may or may not lead anywhere useful, so it goes last,
    but it is still offered: only the person at the keyboard knows what their
    other machine is on.
    """
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return 2
    if any(parsed in network for network in _LAN_RANGES):
        return 0
    return 1 if parsed in _OVERLAY else 2


def local_addresses() -> list[str]:
    """This machine's own IPv4 addresses, most useful first, no duplicates.

    Loopback and link-local are left out: one is not remote access and the
    other means the interface never got an address.
    """
    usable: list[str] = []
    for address in [*_from_os(), *_default_route()]:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            continue
        if parsed.is_loopback or parsed.is_link_local or parsed.is_unspecified:
            continue
        if address not in usable:
            usable.append(address)
    # Stable within a rank: interface order is the only other signal there is.
    return [address for _, address in
            sorted(enumerate(usable), key=lambda pair: (_rank(pair[1]), pair[0]))]


def describe(address: str) -> str:
    """What kind of network this address is on, for the person choosing one."""
    return {
        0: "同一个 Wi-Fi 或网线下的设备",
        1: "装了同一个虚拟网（如 Tailscale）的设备",
        2: "其他网卡，不一定通",
    }[_rank(address)]
