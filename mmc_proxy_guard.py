from __future__ import annotations

import base64
import selectors
import socket
import socketserver
import ssl
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlsplit


_HEADER_END = b"\r\n\r\n"
_MAX_HEADER_BYTES = 64 * 1024
_RELAY_BUFFER_SIZE = 64 * 1024


@dataclass(frozen=True)
class UpstreamProxyConfig:
    raw_url: str
    scheme: str
    host: str
    port: int
    auth_header_value: str


def parse_upstream_proxy(proxy_url: str) -> UpstreamProxyConfig:
    raw_url = str(proxy_url or "").strip()
    parsed = urlsplit(raw_url)
    scheme = (parsed.scheme or "").strip().lower()
    if scheme not in {"http", "https"}:
        raise ValueError(f"unsupported upstream proxy scheme: {scheme or 'missing'}")
    host = str(parsed.hostname or "").strip()
    if not host:
        raise ValueError("missing upstream proxy host")
    port = int(parsed.port or (443 if scheme == "https" else 80))
    username = unquote(str(parsed.username or ""))
    password = unquote(str(parsed.password or ""))
    auth_header_value = ""
    if username or password:
        raw = f"{username}:{password}".encode("utf-8")
        auth_header_value = "Basic " + base64.b64encode(raw).decode("ascii")
    return UpstreamProxyConfig(
        raw_url=raw_url,
        scheme=scheme,
        host=host,
        port=port,
        auth_header_value=auth_header_value,
    )


def inject_upstream_proxy_auth(request_head: bytes, auth_header_value: str) -> bytes:
    if not auth_header_value:
        return request_head
    try:
        decoded = request_head.decode("iso-8859-1")
    except UnicodeDecodeError:
        return request_head
    lines = decoded.split("\r\n")
    if not lines:
        return request_head
    request_line = lines[0]
    headers = []
    replaced = False
    for line in lines[1:]:
        if not line:
            continue
        if line.lower().startswith("proxy-authorization:"):
            if not replaced:
                headers.append(f"Proxy-Authorization: {auth_header_value}")
                replaced = True
            continue
        headers.append(line)
    if not replaced:
        headers.append(f"Proxy-Authorization: {auth_header_value}")
    payload = "\r\n".join([request_line, *headers, "", ""])
    return payload.encode("iso-8859-1")


def loopback_only_no_proxy() -> str:
    return "127.0.0.1,localhost"


def recv_proxy_request_head(sock: socket.socket) -> tuple[bytes, bytes]:
    sock.settimeout(15.0)
    buffer = bytearray()
    while len(buffer) < _MAX_HEADER_BYTES:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buffer.extend(chunk)
        marker = buffer.find(_HEADER_END)
        if marker >= 0:
            head_end = marker + len(_HEADER_END)
            head = bytes(buffer[:head_end])
            tail = bytes(buffer[head_end:])
            sock.settimeout(None)
            return head, tail
    sock.settimeout(None)
    raise ValueError("incomplete proxy request head")


def relay_bidirectional(left: socket.socket, right: socket.socket) -> None:
    selector = selectors.DefaultSelector()
    try:
        selector.register(left, selectors.EVENT_READ, right)
        selector.register(right, selectors.EVENT_READ, left)
        while True:
            events = selector.select(timeout=1.0)
            if not events:
                continue
            for key, _mask in events:
                src = key.fileobj
                dst = key.data
                data = src.recv(_RELAY_BUFFER_SIZE)
                if not data:
                    return
                dst.sendall(data)
    finally:
        selector.close()


class _ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _ProxyRelayHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        controller = self.server.controller
        controller.handle_client_socket(self.request)


class LocalProxyGuard:
    def __init__(
        self,
        upstream_proxy_url: str,
        *,
        probe_targets: tuple[tuple[str, str], ...],
        probe_interval_sec: float,
        probe_fn: Callable[[str, str], dict],
        exit_ip_probe_fn: Callable[[str], dict] | None = None,
        exit_ip_check_interval_sec: float = 30.0,
        expected_exit_ip: str = "",
    ) -> None:
        self.upstream = parse_upstream_proxy(upstream_proxy_url)
        self._probe_targets = tuple(probe_targets)
        self._probe_interval_sec = max(float(probe_interval_sec), 0.5)
        self._probe_fn = probe_fn
        self._exit_ip_probe_fn = exit_ip_probe_fn
        self._exit_ip_check_interval_sec = max(float(exit_ip_check_interval_sec), self._probe_interval_sec)
        self._server = None
        self._server_thread = None
        self._heartbeat_thread = None
        self._stop_event = threading.Event()
        self.failed_event = threading.Event()
        self._failure_reason = ""
        self._pinned_exit_ip = str(expected_exit_ip or "").strip()
        self._next_exit_ip_check_at = 0.0
        self.local_proxy_url = ""

    @property
    def failure_reason(self) -> str:
        return str(self._failure_reason or "").strip()

    @property
    def pinned_exit_ip(self) -> str:
        return str(self._pinned_exit_ip or "").strip()

    def start(self) -> None:
        if self._exit_ip_probe_fn is not None:
            if self._pinned_exit_ip:
                self._next_exit_ip_check_at = time.monotonic() + self._exit_ip_check_interval_sec
            else:
                self._pin_initial_exit_ip()
        server = _ThreadingTCPServer(("127.0.0.1", 0), _ProxyRelayHandler)
        server.controller = self
        self._server = server
        self.local_proxy_url = f"http://127.0.0.1:{int(server.server_address[1])}"
        self._server_thread = threading.Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": 0.5},
            name="mmc-local-proxy-guard",
            daemon=True,
        )
        self._server_thread.start()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="mmc-local-proxy-heartbeat",
            daemon=True,
        )
        self._heartbeat_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        server = self._server
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass
        for thread in (self._heartbeat_thread, self._server_thread):
            if thread and thread.is_alive():
                thread.join(timeout=1.0)

    def fail(self, reason: str) -> None:
        if self.failed_event.is_set():
            return
        self._failure_reason = str(reason or "").strip()
        self.failed_event.set()
        self._stop_event.set()

    def _probe_exit_ip(self) -> dict:
        if self._exit_ip_probe_fn is None:
            return {"ok": True, "exit_ip": self._pinned_exit_ip, "detail": ""}
        result = self._exit_ip_probe_fn(self.upstream.raw_url)
        return result if isinstance(result, dict) else {"ok": False, "detail": "exit ip probe returned invalid payload"}

    def _pin_initial_exit_ip(self) -> None:
        result = self._probe_exit_ip()
        exit_ip = str(result.get("exit_ip") or "").strip()
        if not result.get("ok") or not exit_ip:
            detail = str(result.get("detail") or "missing exit IP").strip()
            raise RuntimeError(f"proxy exit IP pin failed: {detail}")
        self._pinned_exit_ip = exit_ip
        self._next_exit_ip_check_at = time.monotonic() + self._exit_ip_check_interval_sec

    def _check_pinned_exit_ip(self) -> bool:
        if self._exit_ip_probe_fn is None or not self._pinned_exit_ip:
            return True
        now = time.monotonic()
        if now < self._next_exit_ip_check_at:
            return True
        result = self._probe_exit_ip()
        self._next_exit_ip_check_at = now + self._exit_ip_check_interval_sec
        exit_ip = str(result.get("exit_ip") or "").strip()
        if not result.get("ok") or not exit_ip:
            detail = str(result.get("detail") or "missing exit IP").strip()
            self.fail(f"proxy exit IP check failed: {detail}")
            return False
        if exit_ip != self._pinned_exit_ip:
            self.fail(f"proxy exit IP changed: {self._pinned_exit_ip} -> {exit_ip}")
            return False
        return True

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.wait(self._probe_interval_sec):
            for label, target_url in self._probe_targets:
                result = self._probe_fn(self.upstream.raw_url, target_url)
                if result.get("ok"):
                    continue
                detail = str(result.get("detail") or "").strip()
                reason = f"proxy heartbeat failed for {label}"
                if detail:
                    reason = f"{reason}: {detail}"
                self.fail(reason)
                return
            if not self._check_pinned_exit_ip():
                return

    def _connect_upstream(self) -> socket.socket:
        sock = socket.create_connection((self.upstream.host, self.upstream.port), timeout=10.0)
        if self.upstream.scheme == "https":
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=self.upstream.host)
        return sock

    def handle_client_socket(self, client_sock: socket.socket) -> None:
        upstream_sock = None
        try:
            request_head, request_tail = recv_proxy_request_head(client_sock)
            upstream_sock = self._connect_upstream()
            upstream_sock.sendall(inject_upstream_proxy_auth(request_head, self.upstream.auth_header_value))
            if request_tail:
                upstream_sock.sendall(request_tail)
            relay_bidirectional(client_sock, upstream_sock)
        except Exception as exc:
            self.fail(f"local proxy relay failed: {exc}")
        finally:
            for sock in (upstream_sock, client_sock):
                if sock is None:
                    continue
                try:
                    sock.close()
                except OSError:
                    pass
