#!/usr/bin/env python3
"""Recording reverse proxy for Pi provider traffic (issue #97).

Sits between Pi and the relay, records the exact bytes Pi puts on the wire, and
forwards them unmodified. The upstream origin travels inside the request path as
``/__mms_capture__/<base64url-origin>/<rest>`` so one proxy can serve every
provider in a launch.

Keep-alive and chunked response streaming are preserved: the point is to observe
the transport, not to change it.

Raw request bodies are written only for suspicious or failing requests, so a long
session does not fill the disk.
"""

from __future__ import annotations

import argparse
import base64
import http.client
import json
import os
import socketserver
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler

CAPTURE_PATH_PREFIX = "/__mms_capture__"
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
_COUNTER_LOCK = threading.Lock()
_COUNTER = {"n": 0}


def decode_origin(token):
    padding = "=" * (-len(token) % 4)
    return base64.urlsafe_b64decode((token + padding).encode("ascii")).decode("utf-8")


def scan_raw_control_bytes(body):
    """Return every raw control byte with its offset.

    ``JSON.stringify`` escapes the whole C0 range, so a compact JSON body from Pi
    must contain none of these. Any hit is the smoking gun.
    """
    hits = []
    for offset, value in enumerate(body):
        if value < 0x20 or value == 0x7F:
            hits.append((offset, value))
            if len(hits) >= 20:
                break
    return hits


def describe_hits(body, hits):
    described = []
    for offset, value in hits:
        window = body[max(0, offset - 70):offset + 30]
        described.append({
            "offset": offset,
            "byte": f"0x{value:02x}",
            "context": repr(window),
        })
    return described


class CaptureHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    log_dir = "."

    def log_message(self, *args):  # noqa: D102 - stderr noise is not useful here
        return

    def _record(self, entry, body=None):
        line = json.dumps(entry, ensure_ascii=False)
        with _COUNTER_LOCK:
            # Plaintext request metadata; keep it owner-readable only.
            fd = os.open(
                os.path.join(self.log_dir, "capture.jsonl"),
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o600,
            )
            with os.fdopen(fd, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        if body is not None:
            path = os.path.join(self.log_dir, f"req-{entry['index']:05d}.bin")
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(body)

    def _read_request_body(self):
        if str(self.headers.get("Transfer-Encoding") or "").lower() == "chunked":
            chunks = []
            while True:
                size_line = self.rfile.readline().strip()
                size = int(size_line.split(b";")[0] or b"0", 16)
                if size == 0:
                    self.rfile.readline()
                    break
                chunks.append(self.rfile.read(size))
                self.rfile.readline()
            return b"".join(chunks)
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _split_target(self):
        if not self.path.startswith(CAPTURE_PATH_PREFIX + "/"):
            return "", ""
        remainder = self.path[len(CAPTURE_PATH_PREFIX) + 1:]
        token, _, rest = remainder.partition("/")
        try:
            origin = decode_origin(token)
        except Exception:
            return "", ""
        return origin, "/" + rest

    def _fail(self, status, message):
        payload = json.dumps({"error": {"message": message}}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle(self):
        origin, upstream_path = self._split_target()
        body = self._read_request_body()
        if not origin:
            self._fail(400, f"capture proxy could not decode an upstream origin from {self.path}")
            return

        with _COUNTER_LOCK:
            _COUNTER["n"] += 1
            index = _COUNTER["n"]

        hits = scan_raw_control_bytes(body)
        try:
            body.decode("utf-8")
            valid_utf8 = True
        except UnicodeDecodeError:
            valid_utf8 = False

        entry = {
            "index": index,
            "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "method": self.command,
            "origin": origin,
            "path": upstream_path,
            "request_bytes": len(body),
            "raw_control_bytes": describe_hits(body, hits),
            "valid_utf8": valid_utf8,
        }

        scheme, _, netloc = origin.partition("://")
        connection_class = (http.client.HTTPSConnection if scheme == "https"
                            else http.client.HTTPConnection)
        headers = {}
        for key, value in self.headers.items():
            if key.lower() in HOP_BY_HOP or key.lower() in ("host", "content-length"):
                continue
            headers[key] = value

        try:
            connection = connection_class(netloc, timeout=600)
            connection.request(self.command, upstream_path, body=body, headers=headers)
            response = connection.getresponse()
        except Exception as exc:
            entry["upstream_error"] = f"{type(exc).__name__}: {exc}"
            self._record(entry, body if (hits or not valid_utf8) else None)
            self._fail(502, entry["upstream_error"])
            return

        entry["status"] = response.status
        suspicious = bool(hits) or not valid_utf8 or response.status >= 400
        # Record before relaying the response: a hang mid-stream must still leave
        # the request evidence on disk.
        self._record(entry, body if suspicious else None)

        self.send_response(response.status)
        for key, value in response.getheaders():
            if key.lower() in HOP_BY_HOP or key.lower() == "content-length":
                continue
            self.send_header(key, value)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        collected = bytearray()
        relay_error = ""
        try:
            while True:
                # read1, not read: SSE must reach Pi as it arrives instead of
                # being buffered until the block size is filled.
                chunk = response.read1(65536)
                if not chunk:
                    break
                if response.status >= 400 and len(collected) < 65536:
                    collected.extend(chunk)
                self.wfile.write(f"{len(chunk):x}\r\n".encode("ascii") + chunk + b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except Exception as exc:
            relay_error = f"{type(exc).__name__}: {exc}"
        finally:
            connection.close()

        if collected or relay_error:
            self._record({
                "index": index,
                "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "phase": "response",
                "status": response.status,
                "relay_error": relay_error,
                "response_body": collected.decode("utf-8", "replace")[:2000],
            })

    do_POST = _handle
    do_GET = _handle
    do_PUT = _handle
    do_DELETE = _handle
    do_PATCH = _handle


class CaptureServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def watch_parent(parent_pid, server):
    """Exit with the launch that asked for the capture, so nothing is orphaned."""
    while True:
        time.sleep(5)
        try:
            os.kill(parent_pid, 0)
        except OSError:
            server.shutdown()
            return


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--log-dir", required=True)
    parser.add_argument("--parent-pid", type=int, default=0)
    args = parser.parse_args(argv)

    os.makedirs(args.log_dir, mode=0o700, exist_ok=True)
    os.chmod(args.log_dir, 0o700)
    CaptureHandler.log_dir = args.log_dir
    server = CaptureServer(("127.0.0.1", args.port), CaptureHandler)
    if args.parent_pid:
        threading.Thread(target=watch_parent, args=(args.parent_pid, server), daemon=True).start()
    print(f"pi capture proxy listening on 127.0.0.1:{args.port} -> {args.log_dir}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
