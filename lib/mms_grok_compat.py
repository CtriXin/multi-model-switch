"""Rewrite MiniMax/NewAPI OpenAI-stream responses so Grok's strict serde can read them."""

from __future__ import annotations

import argparse
import codecs
import http.client
import json
import os
import socket
import socketserver
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit, urlunsplit

OPENAI_COMPAT_BACKENDS = ("chat_completions",)
ANTHROPIC_COMPAT_BACKENDS = ("messages",)
PROXIED_BACKENDS = OPENAI_COMPAT_BACKENDS + ANTHROPIC_COMPAT_BACKENDS


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


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def fill_openai_usage(usage):
    if not isinstance(usage, dict):
        return usage
    if "prompt_tokens" not in usage:
        usage["prompt_tokens"] = _as_int(usage.get("input_tokens"))
    if "completion_tokens" not in usage:
        usage["completion_tokens"] = _as_int(usage.get("output_tokens"))
    if "total_tokens" not in usage:
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    return usage


def fill_stream_choice_delta(payload):
    """MiniMax's last SSE event is a full `message` object, not a chunk `delta`."""
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list):
        return payload
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        if "delta" in choice:
            continue
        choice.pop("message", None)
        choice["delta"] = {}
    return payload


_ANTHROPIC_EVENT_TYPES = {
    "message_start",
    "message_delta",
    "message_stop",
    "content_block_start",
    "content_block_delta",
    "content_block_stop",
    "ping",
}


def is_anthropic_event(payload):
    return isinstance(payload, dict) and payload.get("type") in _ANTHROPIC_EVENT_TYPES


def fill_missing_thinking_signature(node):
    """Grok's messages serde requires thinking.signature on content_block_start.

    Real Anthropic omits the key and later sends signature_delta. Grok fail-closes
    on the missing field, then overwrites "" with the delta. Do not clobber a
    signature that is already present.
    """
    if isinstance(node, dict):
        if node.get("type") == "thinking" and "signature" not in node:
            node["signature"] = ""
        for key in ("content", "delta", "message", "content_block"):
            if key in node:
                fill_missing_thinking_signature(node[key])
    elif isinstance(node, list):
        for item in node:
            fill_missing_thinking_signature(item)
    return node


def rewrite_inference_payload(payload):
    if not isinstance(payload, dict):
        return payload
    if is_anthropic_event(payload):
        fill_missing_thinking_signature(payload)
        return payload
    if isinstance(payload.get("usage"), dict):
        fill_openai_usage(payload["usage"])
    fill_stream_choice_delta(payload)
    return payload


def rewrite_sse_text(text):
    out = []
    for line in text.splitlines(keepends=True):
        newline = ""
        body = line
        if line.endswith("\r\n"):
            newline = "\r\n"
            body = line[:-2]
        elif line.endswith("\n"):
            newline = "\n"
            body = line[:-1]
        if body.startswith("data:"):
            data = body[5:].strip()
            if data and data != "[DONE]":
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    out.append(line)
                    continue
                rewrite_inference_payload(payload)
                out.append("data: " + json.dumps(payload, ensure_ascii=False) + newline)
                continue
        out.append(line)
    return "".join(out)


class SseUtf8Rewriter:
    """Decode SSE bytes incrementally so a UTF-8 character can span read1 chunks."""

    def __init__(self):
        self.decoder = codecs.getincrementaldecoder("utf-8")()
        self.leftover = ""

    def push(self, chunk, *, final=False):
        self.leftover += self.decoder.decode(chunk or b"", final=final)
        emitted = []
        if "\n" in self.leftover:
            *complete, self.leftover = self.leftover.split("\n")
            text = rewrite_sse_text("\n".join(complete) + "\n")
            if text:
                emitted.append(text.encode("utf-8"))
        if final and self.leftover:
            text = rewrite_sse_text(self.leftover)
            self.leftover = ""
            if text:
                emitted.append(text.encode("utf-8"))
        return b"".join(emitted)


def rewrite_sse_byte_stream(chunks):
    rewriter = SseUtf8Rewriter()
    pieces = []
    chunk_list = list(chunks)
    if not chunk_list:
        return b""
    for index, chunk in enumerate(chunk_list):
        pieces.append(rewriter.push(chunk, final=index == len(chunk_list) - 1))
    return b"".join(pieces)


def origin_of(url):
    parsed = urlsplit(str(url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def retarget_base_url(url, listen_origin):
    parsed = urlsplit(str(url or "").strip())
    listen = urlsplit(str(listen_origin or "").strip())
    if not parsed.scheme or not parsed.netloc or not listen.netloc:
        return url
    return urlunsplit((listen.scheme or "http", listen.netloc, parsed.path, parsed.query, parsed.fragment))


class _CompatHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    upstream_origin = ""

    def log_message(self, *_args):
        return

    def _read_request_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _fail(self, status, message):
        payload = json.dumps({"error": {"message": message}}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle(self):
        origin = urlsplit(self.upstream_origin)
        if not origin.netloc:
            self._fail(500, "grok compat proxy has no upstream origin")
            return
        body = self._read_request_body()
        headers = {}
        for key, value in self.headers.items():
            if key.lower() in HOP_BY_HOP or key.lower() in {"host", "content-length"}:
                continue
            headers[key] = value
        connection_class = http.client.HTTPSConnection if origin.scheme == "https" else http.client.HTTPConnection
        try:
            connection = connection_class(origin.netloc, timeout=600)
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
        except Exception as exc:
            self._fail(502, f"{type(exc).__name__}: {exc}")
            return

        content_type = str(response.getheader("Content-Type") or "").lower()
        self.send_response(response.status)
        for key, value in response.getheaders():
            if key.lower() in HOP_BY_HOP or key.lower() == "content-length":
                continue
            self.send_header(key, value)
        if "text/event-stream" in content_type:
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            rewriter = SseUtf8Rewriter()
            while True:
                chunk = response.read1(65536)
                if not chunk:
                    data = rewriter.push(b"", final=True)
                    if data:
                        self.wfile.write(f"{len(data):x}\r\n".encode("ascii") + data + b"\r\n")
                    break
                data = rewriter.push(chunk)
                if data:
                    self.wfile.write(f"{len(data):x}\r\n".encode("ascii") + data + b"\r\n")
                    self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        else:
            raw = response.read()
            rewritten = raw
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict):
                rewrite_inference_payload(payload)
                rewritten = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_header("Content-Length", str(len(rewritten)))
            self.end_headers()
            self.wfile.write(rewritten)
        connection.close()

    do_POST = _handle
    do_GET = _handle
    do_PUT = _handle
    do_DELETE = _handle
    do_PATCH = _handle


class _CompatServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _watch_parent(parent_pid, server):
    while True:
        time.sleep(2)
        try:
            os.kill(parent_pid, 0)
        except OSError:
            server.shutdown()
            return


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_listening(port, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def start_compat_proxy(upstream_origin, *, parent_pid, log_path=""):
    origin = origin_of(upstream_origin) or str(upstream_origin or "").strip().rstrip("/")
    if not origin:
        raise RuntimeError("Grok compat proxy requires an upstream origin")
    port = _free_port()
    repo_root = os.path.dirname(os.path.abspath(__file__))
    child_env = os.environ.copy()
    child_env["PYTHONPATH"] = repo_root + os.pathsep + str(child_env.get("PYTHONPATH") or "")
    command = [
        sys.executable,
        "-m",
        "mms_grok_compat",
        "--port",
        str(port),
        "--upstream-origin",
        origin,
        "--parent-pid",
        str(parent_pid),
    ]
    stdout = subprocess.DEVNULL
    handle = None
    if log_path:
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        handle = open(log_path, "ab", buffering=0)
        stdout = handle
    try:
        subprocess.Popen(
            command,
            stdout=stdout,
            stderr=stdout,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
            cwd=repo_root,
            env=child_env,
        )
    finally:
        if handle is not None:
            handle.close()
    if not _wait_until_listening(port):
        raise RuntimeError(f"Grok compat proxy did not listen on 127.0.0.1:{port}")
    return f"http://127.0.0.1:{port}"


def rewrite_config_base_urls(
    payload,
    listen_origin,
    upstream_origin,
    *,
    backends=PROXIED_BACKENDS,
):
    models = payload.get("model") if isinstance(payload, dict) else None
    if not isinstance(models, dict):
        return payload
    wanted = origin_of(upstream_origin)
    allowed = {str(item) for item in (backends or ())}
    for table in models.values():
        if not isinstance(table, dict):
            continue
        if str(table.get("api_backend") or "").strip() not in allowed:
            continue
        base_url = str(table.get("base_url") or "").strip()
        if origin_of(base_url) != wanted:
            continue
        table["base_url"] = retarget_base_url(base_url, listen_origin)
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--upstream-origin", required=True)
    parser.add_argument("--parent-pid", type=int, default=0)
    args = parser.parse_args(argv)
    _CompatHandler.upstream_origin = origin_of(args.upstream_origin) or args.upstream_origin
    server = _CompatServer(("127.0.0.1", args.port), _CompatHandler)
    if args.parent_pid:
        threading.Thread(target=_watch_parent, args=(args.parent_pid, server), daemon=True).start()
    print(f"grok compat proxy 127.0.0.1:{args.port} -> {_CompatHandler.upstream_origin}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
