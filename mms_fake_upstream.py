"""Development-only fake upstream mode.

When enabled, MMS can fake outbound upstream requests and write JSONL logs so
validation can run without hitting real external services.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import socketserver
import ssl
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlsplit

_FAKE_PROXY_HOST = "127.0.0.1"
_FAKE_PROXY_FINGERPRINT = "fake://127.0.0.1+local"
_LOG_BODY_LIMIT = 4000
_SERVER_LOCK = threading.Lock()
_CERT_LOCK = threading.Lock()
_SERVER_STATE: dict[str, object] = {}


class _ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _real_home():
    return os.path.expanduser(
        str(
            os.environ.get("MMS_REAL_HOME")
            or os.environ.get("ORIGINAL_HOME")
            or os.environ.get("REAL_HOME")
            or "~"
        )
    )


def _base_dir():
    return os.path.join(_real_home(), ".config", "mms", "fake-upstream")


def _state_path():
    return os.path.join(_base_dir(), "state.json")


def _log_path():
    return os.path.join(_base_dir(), "requests.jsonl")


def _cert_dir():
    return os.path.join(_base_dir(), "certs")


def _ca_cert_path():
    return os.path.join(_cert_dir(), "fake-upstream-ca-cert.pem")


def _ca_key_path():
    return os.path.join(_cert_dir(), "fake-upstream-ca-key.pem")


def _hosts_cert_dir():
    return os.path.join(_cert_dir(), "hosts")


def _iso_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_state():
    path = _state_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}



def _save_state(payload):
    path = _state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _merge_state(**updates):
    current = _load_state()
    current.update({key: value for key, value in updates.items() if value is not None})
    _save_state(current)
    return current


def _chmod_private(path):
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _unlink_if_exists(path):
    if not path or not os.path.exists(path):
        return
    try:
        os.remove(path)
    except OSError:
        pass


def _cert_key_pair_matches(cert_path, key_path):
    if not (os.path.exists(cert_path) and os.path.exists(key_path)):
        return False
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=cert_path, keyfile=key_path)
        return True
    except ssl.SSLError:
        return False



def set_enabled(enabled: bool):
    payload = {"enabled": bool(enabled), "updated_at": _iso_now()}
    if not enabled:
        payload.update(
            {
                "proxy_url": "",
                "ca_cert_path": "",
                "proxy_pid": 0,
                "proxy_started_at": "",
            }
        )
    _save_state(payload)



def is_enabled() -> bool:
    raw = str(os.environ.get("MMS_FAKE_UPSTREAM", "")).strip().lower()
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return True
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return bool(_load_state().get("enabled"))



def _proxy_fingerprint(proxy_url: str) -> str:
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return "direct"
    try:
        parsed = urlsplit(proxy_url)
    except Exception:
        return proxy_url
    scheme = parsed.scheme or "proxy"
    host = parsed.hostname or "unknown"
    port = f":{parsed.port}" if parsed.port else ""
    auth = "+auth" if parsed.username or parsed.password else ""
    return f"{scheme}://{host}{port}{auth}"



def status_payload() -> dict:
    state = _load_state()
    payload = {
        "enabled": bool(is_enabled()),
        "state_path": _state_path(),
        "log_path": _log_path(),
        "updated_at": state.get("updated_at", ""),
        "proxy_url": str(state.get("proxy_url") or ""),
        "ca_cert_path": str(state.get("ca_cert_path") or (_ca_cert_path() if os.path.exists(_ca_cert_path()) else "")),
        "proxy_pid": int(state.get("proxy_pid") or 0),
        "proxy_started_at": str(state.get("proxy_started_at") or ""),
    }
    with _SERVER_LOCK:
        if _SERVER_STATE.get("proxy_url"):
            payload["proxy_url"] = str(_SERVER_STATE.get("proxy_url") or "")
        if _SERVER_STATE.get("ca_cert_path"):
            payload["ca_cert_path"] = str(_SERVER_STATE.get("ca_cert_path") or "")
        if _SERVER_STATE.get("proxy_pid"):
            payload["proxy_pid"] = int(_SERVER_STATE.get("proxy_pid") or 0)
        if _SERVER_STATE.get("proxy_started_at"):
            payload["proxy_started_at"] = str(_SERVER_STATE.get("proxy_started_at") or "")
    return payload



def is_local_url(url: str) -> bool:
    try:
        host = (urlsplit(str(url or "")).hostname or "").lower()
    except Exception:
        return False
    return host in {"127.0.0.1", "localhost", "::1"}



def append_log(kind: str, payload: dict):
    path = _log_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    record = {"ts": _iso_now(), "kind": str(kind or "event")}
    record.update(payload if isinstance(payload, dict) else {})
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    _chmod_private(path)



def tail_log(limit: int = 20) -> list[dict]:
    path = _log_path()
    if not os.path.exists(path):
        return []
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if isinstance(row, dict) and row.get("proxy"):
                        row["proxy"] = _proxy_fingerprint(row.get("proxy"))
                    rows.append(row)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows[-max(1, int(limit or 20)) :]



def _redact_scalar(value):
    if value is None:
        return None
    text = str(value)
    if len(text) <= 8:
        return "****"
    return text[:4] + "****" + text[-4:]



def _is_secret_key(name: str) -> bool:
    lower = str(name or "").lower()
    return any(token in lower for token in ("authorization", "cookie", "token", "secret", "password", "api-key", "apikey", "auth"))



def _redact_json(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            out[key] = _redact_scalar(item) if _is_secret_key(key) else _redact_json(item)
        return out
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    return value



def _body_preview(body: bytes, *, content_type: str = "") -> str:
    if not body:
        return ""
    normalized_content_type = str(content_type or "").lower()
    raw = body[:_LOG_BODY_LIMIT]
    text = raw.decode("utf-8", errors="replace")
    if "json" in normalized_content_type:
        try:
            payload = json.loads(text)
            return json.dumps(_redact_json(payload), ensure_ascii=False)
        except Exception:
            pass
    if "application/x-www-form-urlencoded" in normalized_content_type:
        try:
            pairs = parse_qsl(text, keep_blank_values=True)
            return json.dumps(
                {
                    key: (_redact_scalar(value) if _is_secret_key(key) else value)
                    for key, value in pairs
                },
                ensure_ascii=False,
            )
        except Exception:
            pass
    try:
        pairs = parse_qsl(text, keep_blank_values=True)
        if pairs and any(key for key, _ in pairs):
            return json.dumps(
                {
                    key: (_redact_scalar(value) if _is_secret_key(key) else value)
                    for key, value in pairs
                },
                ensure_ascii=False,
            )
    except Exception:
        pass
    digest = uuid.uuid5(uuid.NAMESPACE_URL, text).hex[:12]
    return f"<opaque body {len(body)} bytes sha={digest}>"



def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    redacted = {}
    for key, value in headers.items():
        redacted[key] = _redact_scalar(value) if _is_secret_key(key) else str(value)
    return redacted



def _fake_models_payload():
    return {
        "object": "list",
        "data": [
            {"id": "claude-sonnet-4-6", "object": "model"},
            {"id": "claude-opus-4-6", "object": "model"},
            {"id": "gpt-5.4", "object": "model"},
            {"id": "kimi-k2.5", "object": "model"},
        ],
    }



def _anthropic_message_payload(request_json: dict | None = None):
    request_json = request_json if isinstance(request_json, dict) else {}
    return {
        "id": f"msg_fake_{uuid.uuid4().hex[:8]}",
        "type": "message",
        "role": "assistant",
        "model": str(request_json.get("model") or "claude-sonnet-4-6"),
        "content": [{"type": "text", "text": "OK (fake upstream)"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }



def _anthropic_sse_bytes(message_payload: dict) -> bytes:
    usage = message_payload.get("usage") or {}
    start = {
        **message_payload,
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {"input_tokens": usage.get("input_tokens", 0), "output_tokens": 0},
    }
    text = ""
    for item in message_payload.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            text = str(item.get("text") or "")
            break
    events = [
        f'event: message_start\ndata: {json.dumps({"type": "message_start", "message": start}, ensure_ascii=False)}\n\n',
        f'event: content_block_start\ndata: {json.dumps({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}, ensure_ascii=False)}\n\n',
        f'event: content_block_delta\ndata: {json.dumps({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}, ensure_ascii=False)}\n\n',
        f'event: content_block_stop\ndata: {json.dumps({"type": "content_block_stop", "index": 0}, ensure_ascii=False)}\n\n',
        f'event: message_delta\ndata: {json.dumps({"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": usage.get("output_tokens", 1)}}, ensure_ascii=False)}\n\n',
        f'event: message_stop\ndata: {json.dumps({"type": "message_stop"}, ensure_ascii=False)}\n\n',
    ]
    return "".join(events).encode("utf-8")



def _openai_chat_payload():
    return {
        "id": f"chatcmpl_fake_{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK (fake upstream)"}, "finish_reason": "stop"}],
    }



def _openai_chat_sse_bytes() -> bytes:
    chunks = [
        "data: " + json.dumps({
            "id": f"chatcmpl_fake_{uuid.uuid4().hex[:8]}",
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": "OK (fake upstream)"}, "finish_reason": "stop"}],
        }, ensure_ascii=False) + "\n\n",
        "data: [DONE]\n\n",
    ]
    return "".join(chunks).encode("utf-8")



def _responses_payload():
    return {
        "id": f"resp_fake_{uuid.uuid4().hex[:8]}",
        "object": "response",
        "status": "completed",
        "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "OK (fake upstream)"}]}],
    }



def _guess_html(url: str) -> bytes:
    split = urlsplit(str(url or ""))
    body = f"<html><body><h1>Fake Upstream</h1><p>{split.hostname or 'unknown'}</p></body></html>"
    return body.encode("utf-8")



def build_fake_response(method: str, url: str, *, headers: dict | None = None, body: bytes = b""):
    method = str(method or "GET").upper()
    headers = {str(k): str(v) for k, v in (headers or {}).items()}
    split = urlsplit(str(url or ""))
    host = (split.hostname or "").lower()
    path = split.path or "/"
    content_type = str(headers.get("content-type") or headers.get("Content-Type") or "")
    accept = str(headers.get("accept") or headers.get("Accept") or "")
    wants_stream = "text/event-stream" in accept.lower()
    request_json = {}
    if body:
        try:
            request_json = json.loads(body.decode("utf-8", errors="replace"))
        except Exception:
            request_json = {}
    if isinstance(request_json, dict) and request_json.get("stream") is True:
        wants_stream = True

    if host in {"api4.ipify.org", "api.ipify.org"}:
        return 200, {"Content-Type": "text/plain; charset=utf-8"}, b"198.51.100.24"
    if host in {"api6.ipify.org"}:
        return 200, {"Content-Type": "text/plain; charset=utf-8"}, b"2001:db8::24"
    if path.endswith("/models"):
        return 200, {"Content-Type": "application/json"}, json.dumps(_fake_models_payload(), ensure_ascii=False).encode("utf-8")
    if path.endswith("/v1/messages") or path.endswith("/messages"):
        payload = _anthropic_message_payload(request_json)
        if wants_stream:
            return 200, {"Content-Type": "text/event-stream; charset=utf-8"}, _anthropic_sse_bytes(payload)
        return 200, {"Content-Type": "application/json"}, json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if path.endswith("/chat/completions"):
        if wants_stream:
            return 200, {"Content-Type": "text/event-stream; charset=utf-8"}, _openai_chat_sse_bytes()
        return 200, {"Content-Type": "application/json"}, json.dumps(_openai_chat_payload(), ensure_ascii=False).encode("utf-8")
    if path.endswith("/responses"):
        return 200, {"Content-Type": "application/json"}, json.dumps(_responses_payload(), ensure_ascii=False).encode("utf-8")
    if "auth0" in host and ("token" in path or method == "POST"):
        payload = {"access_token": "fake-upstream-token", "token_type": "Bearer", "expires_in": 3600}
        return 200, {"Content-Type": "application/json"}, json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if method == "HEAD":
        return 200, {"Content-Type": "text/plain; charset=utf-8"}, b""
    if "text/html" in accept.lower() or host.endswith("claude.ai"):
        return 200, {"Content-Type": "text/html; charset=utf-8"}, _guess_html(url)
    payload = {"ok": True, "fake": True, "url": str(url or "")}
    return 200, {"Content-Type": "application/json"}, json.dumps(payload, ensure_ascii=False).encode("utf-8")



def fake_proxy_probe(target_url: str, *, proxy_url: str = "", no_proxy: str = "", force_ipv4: bool = True, resolve_ip: bool = False) -> dict:
    append_log(
        "proxy_probe",
        {
            "url": str(target_url or ""),
            "proxy": _proxy_fingerprint(proxy_url),
            "no_proxy": str(no_proxy or ""),
            "force_ipv4": bool(force_ipv4),
            "resolve_ip": bool(resolve_ip),
        },
    )
    if resolve_ip:
        body = "198.51.100.24" if force_ipv4 else "2001:db8::24"
        return {"ok": True, "detail": "", "http_code": "", "body": body}
    return {"ok": True, "detail": "", "http_code": "200", "body": "200"}



def fake_httpx_response(httpx_module, method: str, url: str, **kwargs):
    method = str(method or "GET").upper()
    split = urlsplit(str(url or ""))
    host = (split.hostname or "").lower()
    path = split.path or "/"
    body = b""
    if kwargs.get("json") is not None:
        body = json.dumps(kwargs["json"], ensure_ascii=False).encode("utf-8")
    elif kwargs.get("content") is not None:
        content = kwargs["content"]
        body = content if isinstance(content, (bytes, bytearray)) else str(content).encode("utf-8")
    headers = {str(k): str(v) for k, v in (kwargs.get("headers") or {}).items()}
    append_log(
        "httpx",
        {
            "method": method,
            "url": str(url or ""),
            "host": host,
            "path": path,
            "headers": sorted(list(headers.keys()))[:12],
            "request_body_preview": _body_preview(body, content_type=headers.get("content-type") or headers.get("Content-Type") or ""),
        },
    )
    request = httpx_module.Request(method, str(url))
    status_code, response_headers, response_body = build_fake_response(method, url, headers=headers, body=body)
    return httpx_module.Response(status_code, request=request, headers=response_headers, content=response_body)



def _safe_cert_name(hostname: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "."} else "_" for ch in str(hostname or "unknown"))


def _is_ip_hostname(hostname: str) -> bool:
    try:
        socket.inet_aton(str(hostname or ""))
        return True
    except OSError:
        return False


def _ensure_ca_cert():
    cert_path = _ca_cert_path()
    key_path = _ca_key_path()
    with _CERT_LOCK:
        if _cert_key_pair_matches(cert_path, key_path):
            return cert_path, key_path
        _unlink_if_exists(cert_path)
        _unlink_if_exists(key_path)
        openssl_bin = shutil.which("openssl")
        if not openssl_bin:
            raise RuntimeError("openssl missing")
        os.makedirs(_cert_dir(), exist_ok=True)
        cmd = [
            openssl_bin,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "7",
            "-keyout",
            key_path,
            "-out",
            cert_path,
            "-subj",
            "/CN=MMS Fake Upstream CA",
            "-addext",
            "basicConstraints=critical,CA:TRUE,pathlen:0",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "openssl failed").strip())
        _chmod_private(cert_path)
        _chmod_private(key_path)
        if not _cert_key_pair_matches(cert_path, key_path):
            _unlink_if_exists(cert_path)
            _unlink_if_exists(key_path)
            raise RuntimeError("generated fake upstream CA cert/key mismatch")
        return cert_path, key_path


def _ensure_host_tls_cert(hostname: str):
    hostname = str(hostname or "").strip() or "localhost"
    ca_cert_path, ca_key_path = _ensure_ca_cert()
    safe_name = _safe_cert_name(hostname)
    host_dir = os.path.join(_hosts_cert_dir(), safe_name)
    cert_path = os.path.join(host_dir, "cert.pem")
    key_path = os.path.join(host_dir, "key.pem")
    csr_path = os.path.join(host_dir, "req.csr")
    ext_path = os.path.join(host_dir, "ext.cnf")
    with _CERT_LOCK:
        if _cert_key_pair_matches(cert_path, key_path):
            return cert_path, key_path, ca_cert_path
        _unlink_if_exists(cert_path)
        _unlink_if_exists(key_path)
        _unlink_if_exists(csr_path)
        _unlink_if_exists(ext_path)
        openssl_bin = shutil.which("openssl")
        if not openssl_bin:
            raise RuntimeError("openssl missing")
        os.makedirs(host_dir, exist_ok=True)
        san_value = f"IP:{hostname}" if _is_ip_hostname(hostname) else f"DNS:{hostname}"
        with open(ext_path, "w", encoding="utf-8") as f:
            f.write("basicConstraints=CA:FALSE\n")
            f.write("keyUsage=digitalSignature,keyEncipherment\n")
            f.write("extendedKeyUsage=serverAuth\n")
            f.write(f"subjectAltName={san_value}\n")
        req_cmd = [
            openssl_bin,
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            key_path,
            "-out",
            csr_path,
            "-subj",
            f"/CN={hostname}",
        ]
        result = subprocess.run(req_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "openssl req failed").strip())
        sign_cmd = [
            openssl_bin,
            "x509",
            "-req",
            "-in",
            csr_path,
            "-CA",
            ca_cert_path,
            "-CAkey",
            ca_key_path,
            "-CAcreateserial",
            "-out",
            cert_path,
            "-days",
            "7",
            "-sha256",
            "-extfile",
            ext_path,
        ]
        result = subprocess.run(sign_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "openssl x509 failed").strip())
        _chmod_private(cert_path)
        _chmod_private(key_path)
        for path in (csr_path, ext_path):
            _unlink_if_exists(path)
        if not _cert_key_pair_matches(cert_path, key_path):
            _unlink_if_exists(cert_path)
            _unlink_if_exists(key_path)
            raise RuntimeError(f"generated fake upstream TLS cert/key mismatch for host: {hostname}")
        return cert_path, key_path, ca_cert_path



def _read_headers(reader):
    headers = {}
    while True:
        line = reader.readline()
        if not line or line in {b"\r\n", b"\n"}:
            break
        try:
            text = line.decode("iso-8859-1").rstrip("\r\n")
        except Exception:
            continue
        if ":" not in text:
            continue
        key, value = text.split(":", 1)
        headers[key.strip()] = value.strip()
    return headers



def _read_body(reader, headers):
    transfer_encoding = str(headers.get("Transfer-Encoding") or headers.get("transfer-encoding") or "").lower()
    if "chunked" in transfer_encoding:
        chunks = bytearray()
        while True:
            line = reader.readline()
            if not line:
                break
            size_text = line.split(b";", 1)[0].strip()
            try:
                size = int(size_text or b"0", 16)
            except ValueError:
                size = 0
            if size <= 0:
                while True:
                    trailer = reader.readline()
                    if not trailer or trailer in {b"\r\n", b"\n"}:
                        break
                break
            chunk = reader.read(size)
            chunks.extend(chunk)
            reader.read(2)
        return bytes(chunks)
    try:
        content_length = int(headers.get("Content-Length") or headers.get("content-length") or "0")
    except ValueError:
        content_length = 0
    if content_length <= 0:
        return b""
    return reader.read(content_length)



def _write_http_response(writer, status_code: int, headers: dict[str, str], body: bytes):
    reason = {200: "OK", 502: "Bad Gateway"}.get(int(status_code), "OK")
    writer.write(f"HTTP/1.1 {int(status_code)} {reason}\r\n".encode("ascii"))
    out_headers = {"Connection": "close", **{str(k): str(v) for k, v in headers.items()}}
    out_headers["Content-Length"] = str(len(body or b""))
    for key, value in out_headers.items():
        writer.write(f"{key}: {value}\r\n".encode("utf-8"))
    writer.write(b"\r\n")
    if body:
        writer.write(body)
    writer.flush()



def _log_upstream_request(*, method: str, url: str, headers: dict[str, str], body: bytes, source: str, connect_host: str = ""):
    split = urlsplit(str(url or ""))
    append_log(
        "upstream",
        {
            "source": source,
            "method": method,
            "url": str(url or ""),
            "host": split.hostname or connect_host or "",
            "path": split.path or "/",
            "query": split.query or "",
            "request_headers": _redact_headers(headers),
            "request_body_preview": _body_preview(body, content_type=headers.get("Content-Type") or headers.get("content-type") or ""),
        },
    )



def _handle_request(reader, writer, *, target_scheme: str, target_host: str = ""):
    request_line = reader.readline()
    if not request_line:
        return False
    try:
        line = request_line.decode("iso-8859-1").rstrip("\r\n")
        method, raw_target, _version = line.split(" ", 2)
    except ValueError:
        return False
    headers = _read_headers(reader)
    body = _read_body(reader, headers)
    if raw_target.startswith("http://") or raw_target.startswith("https://"):
        url = raw_target
    else:
        host = target_host or headers.get("Host") or headers.get("host") or "localhost"
        url = f"{target_scheme}://{host}{raw_target}"
    _log_upstream_request(method=method, url=url, headers=headers, body=body, source=target_scheme, connect_host=target_host)
    status_code, response_headers, response_body = build_fake_response(method, url, headers=headers, body=body)
    _write_http_response(writer, status_code, response_headers, response_body)
    return False



def _handle_connect(raw_socket, connect_host: str):
    cert_path, key_path, _ca_cert_path_unused = _ensure_host_tls_cert(connect_host)
    raw_socket.sendall(b"HTTP/1.1 200 Connection Established\r\nConnection: close\r\n\r\n")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=cert_path, keyfile=key_path)
    try:
        tls_socket = context.wrap_socket(raw_socket, server_side=True)
    except ssl.SSLError as exc:
        append_log(
            "tls_handshake_failed",
            {
                "host": connect_host,
                "detail": str(exc),
            },
        )
        try:
            raw_socket.close()
        except Exception:
            pass
        return
    tls_socket.settimeout(10)
    reader = tls_socket.makefile("rb")
    writer = tls_socket.makefile("wb")
    try:
        _handle_request(reader, writer, target_scheme="https", target_host=connect_host)
    finally:
        try:
            writer.close()
        except Exception:
            pass
        try:
            reader.close()
        except Exception:
            pass
        try:
            tls_socket.close()
        except Exception:
            pass



def _handler_factory():
    class FakeProxyHandler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(10)
            request_line = self.rfile.readline()
            if not request_line:
                return
            try:
                line = request_line.decode("iso-8859-1").rstrip("\r\n")
                method, raw_target, _version = line.split(" ", 2)
            except ValueError:
                return
            if method.upper() == "CONNECT":
                connect_host = raw_target.split(":", 1)[0].strip()
                _handle_connect(self.connection, connect_host)
                return
            headers = _read_headers(self.rfile)
            body = _read_body(self.rfile, headers)
            url = raw_target
            if not url.startswith(("http://", "https://")):
                host = headers.get("Host") or headers.get("host") or "localhost"
                url = f"http://{host}{raw_target}"
            _log_upstream_request(method=method, url=url, headers=headers, body=body, source="http")
            status_code, response_headers, response_body = build_fake_response(method, url, headers=headers, body=body)
            _write_http_response(self.wfile, status_code, response_headers, response_body)

    return FakeProxyHandler



def ensure_local_proxy() -> dict:
    if not is_enabled():
        return {}
    current_home = _real_home()
    with _SERVER_LOCK:
        thread = _SERVER_STATE.get("thread")
        server = _SERVER_STATE.get("server")
        if (
            thread
            and getattr(thread, "is_alive", lambda: False)()
            and server
            and str(_SERVER_STATE.get("real_home") or "") == current_home
        ):
            _merge_state(
                enabled=True,
                updated_at=_iso_now(),
                proxy_url=str(_SERVER_STATE.get("proxy_url") or ""),
                ca_cert_path=str(_SERVER_STATE.get("ca_cert_path") or ""),
                proxy_pid=int(_SERVER_STATE.get("proxy_pid") or os.getpid()),
                proxy_started_at=str(_SERVER_STATE.get("proxy_started_at") or _iso_now()),
            )
            return {
                "proxy_url": str(_SERVER_STATE.get("proxy_url") or ""),
                "ca_cert_path": str(_SERVER_STATE.get("ca_cert_path") or ""),
            }
        if server:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass
        ca_cert_path, _ca_key_path_unused = _ensure_ca_cert()
        server = _ThreadingTCPServer((_FAKE_PROXY_HOST, 0), _handler_factory())
        thread = threading.Thread(target=server.serve_forever, name="mms-fake-upstream", daemon=True)
        thread.start()
        proxy_url = f"http://{_FAKE_PROXY_HOST}:{server.server_address[1]}"
        _SERVER_STATE.clear()
        _SERVER_STATE.update({
            "server": server,
            "thread": thread,
            "proxy_url": proxy_url,
            "ca_cert_path": ca_cert_path,
            "proxy_pid": os.getpid(),
            "proxy_started_at": _iso_now(),
            "real_home": current_home,
        })
        _merge_state(
            enabled=True,
            updated_at=_iso_now(),
            proxy_url=proxy_url,
            ca_cert_path=ca_cert_path,
            proxy_pid=os.getpid(),
            proxy_started_at=str(_SERVER_STATE.get("proxy_started_at") or ""),
        )
        append_log("fake_proxy", {"proxy": _FAKE_PROXY_FINGERPRINT, "listen": proxy_url})
        return {"proxy_url": proxy_url, "ca_cert_path": ca_cert_path}



def patch_httpx_module(httpx_module):
    if not is_enabled():
        return
    if getattr(httpx_module, "_mms_fake_upstream_patched", False):
        return

    def _wrap_request(original_request):
        def _patched(method, url, *args, **kwargs):
            if is_enabled() and not is_local_url(url):
                return fake_httpx_response(httpx_module, method, url, **kwargs)
            return original_request(method, url, *args, **kwargs)
        return _patched

    original_request = httpx_module.request
    httpx_module.request = _wrap_request(original_request)
    httpx_module.get = lambda url, *args, **kwargs: httpx_module.request("GET", url, *args, **kwargs)
    httpx_module.post = lambda url, *args, **kwargs: httpx_module.request("POST", url, *args, **kwargs)
    httpx_module.head = lambda url, *args, **kwargs: httpx_module.request("HEAD", url, *args, **kwargs)
    httpx_module._mms_fake_upstream_patched = True
