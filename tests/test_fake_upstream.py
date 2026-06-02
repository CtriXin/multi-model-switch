from __future__ import annotations

import json
import shutil
import ssl
import stat


class _FakeTable:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.columns = []
        self.rows = []

    def add_column(self, *args, **kwargs):
        self.columns.append((args, kwargs))

    def add_row(self, *args, **kwargs):
        self.rows.append((args, kwargs))


class _CollectingConsole:
    def __init__(self):
        self.items = []

    def print(self, *args, **kwargs):
        self.items.append(args[0] if args else "")


def test_fake_upstream_runtime_httpx_request_and_log(monkeypatch, tmp_path):
    import mms_core

    monkeypatch.setenv("MMS_FAKE_UPSTREAM", "1")
    monkeypatch.setenv("MMS_REAL_HOME", str(tmp_path))

    response = mms_core._runtime_httpx_request("GET", "https://api.anthropic.com/v1/models")

    assert response.status_code == 200
    body = response.json()
    assert any(item["id"] == "claude-sonnet-4-6" for item in body["data"])

    log_path = tmp_path / ".config" / "mms" / "fake-upstream" / "requests.jsonl"
    assert log_path.exists()
    assert stat.S_IMODE(log_path.stat().st_mode) == 0o600
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(row["kind"] == "httpx" and row["host"] == "api.anthropic.com" for row in rows)


def test_fake_upstream_proxy_probe(monkeypatch, tmp_path):
    import mms_launchers
    from mms_runtime.fake_upstream import tail_log

    monkeypatch.setenv("MMS_FAKE_UPSTREAM", "1")
    monkeypatch.setenv("MMS_REAL_HOME", str(tmp_path))

    probe = mms_launchers._run_proxy_probe(
        "http://127.0.0.1:7890",
        "https://claude.ai",
        no_proxy="",
        force_ipv4=True,
        resolve_ip=True,
    )

    assert probe["ok"] is True
    assert probe["body"] == "198.51.100.24"
    rows = tail_log(5)
    assert rows[-1]["proxy"] == "http://127.0.0.1:7890"


def test_fake_upstream_local_proxy_intercepts_https(monkeypatch, tmp_path):
    import httpx
    from mms_runtime.fake_upstream import ensure_local_proxy, status_payload, tail_log

    monkeypatch.setenv("MMS_FAKE_UPSTREAM", "1")
    monkeypatch.setenv("MMS_REAL_HOME", str(tmp_path))

    proxy = ensure_local_proxy()
    ssl_ctx = ssl.create_default_context(cafile=proxy["ca_cert_path"])
    transport = httpx.HTTPTransport(proxy=proxy["proxy_url"], verify=ssl_ctx)
    with httpx.Client(transport=transport, timeout=5.0) as client:
        response = client.post(
            "https://api.anthropic.com/v1/messages",
            json={"model": "claude-sonnet-4-6", "stream": True, "messages": [{"role": "user", "content": "hi"}]},
            headers={"Accept": "text/event-stream"},
        )

    assert response.status_code == 200
    assert "message_start" in response.text
    status = status_payload()
    assert status["proxy_url"] == proxy["proxy_url"]
    assert status["proxy_pid"] > 0
    rows = tail_log(20)
    assert any(row["kind"] == "upstream" and row["host"] == "api.anthropic.com" and row["path"] == "/v1/messages" for row in rows)


def test_apply_runtime_network_profile_uses_fake_upstream_proxy_under_fake_upstream(monkeypatch, tmp_path):
    import mms_launchers

    monkeypatch.setenv("MMS_FAKE_UPSTREAM", "1")
    monkeypatch.setenv("MMS_REAL_HOME", str(tmp_path))
    monkeypatch.setattr(
        mms_launchers,
        "_fake_upstream_status_payload",
        lambda: {
            "proxy_url": "http://127.0.0.1:8899",
            "ca_cert_path": "/tmp/mms-ca.pem",
        },
    )

    env = {"KEEP": "1"}
    result = mms_launchers._apply_runtime_network_profile(
        env,
        {
            "id": "claude-tonnya",
            "proxy": "http://user:pass@198.51.100.24:6394",
            "no_proxy": "claude.ai",
            "timezone": "America/Los_Angeles",
        },
        validate_proxy=False,
    )

    assert result["KEEP"] == "1"
    assert result["HTTP_PROXY"] == "http://127.0.0.1:8899"
    assert result["HTTPS_PROXY"] == "http://127.0.0.1:8899"
    assert result["NO_PROXY"] == "127.0.0.1,localhost,::1"
    assert result["TZ"] == "America/Los_Angeles"
    assert result["MMS_FAKE_UPSTREAM_MODE"] == "upstream-proxy"
    assert result["MMS_FAKE_UPSTREAM_PROXY"] == "http://127.0.0.1:8899"
    assert result["MMS_FAKE_UPSTREAM_ORIGINAL_PROXY"] == "http://198.51.100.24:6394+auth"
    assert result["MMS_FAKE_UPSTREAM_ORIGINAL_NO_PROXY"] == "claude.ai"
    assert result["NODE_EXTRA_CA_CERTS"] == "/tmp/mms-ca.pem"
    assert result["SSL_CERT_FILE"] == "/tmp/mms-ca.pem"


def test_fake_upstream_patch_httpx_module(monkeypatch, tmp_path):
    import httpx
    from mms_runtime.fake_upstream import patch_httpx_module

    monkeypatch.setenv("MMS_FAKE_UPSTREAM", "1")
    monkeypatch.setenv("MMS_REAL_HOME", str(tmp_path))

    patch_httpx_module(httpx)
    response = httpx.post("https://api.anthropic.com/v1/messages", json={"model": "claude-sonnet-4-6"})

    assert response.status_code == 200
    assert response.json()["id"].startswith("msg_fake_")


def test_confirm_context_lines_show_fake_only_when_enabled(monkeypatch):
    import mms_core

    runtime = {
        "id": "claude-tonnya",
        "auth_mode": "oauth",
        "proxy": "http://127.0.0.1:7890",
    }

    monkeypatch.setenv("MMS_FAKE_UPSTREAM", "1")
    enabled_lines = mms_core._confirm_context_lines("claude", runtime)
    assert ("Fake", "ON") in enabled_lines

    monkeypatch.setenv("MMS_FAKE_UPSTREAM", "0")
    disabled_lines = mms_core._confirm_context_lines("claude", runtime)
    assert all(label != "Fake" for label, _ in disabled_lines)


def test_fake_upstream_command_handler_toggles_and_renders_log():
    import mms_commands.tools as mms_command_tools

    enabled_values = []
    tail_values = []
    console = _CollectingConsole()

    def status_payload():
        return {
            "enabled": True,
            "state_path": "/tmp/state.json",
            "log_path": "/tmp/requests.jsonl",
            "proxy_url": "http://127.0.0.1:7777",
            "ca_cert_path": "/tmp/ca.pem",
            "proxy_pid": 123,
            "proxy_started_at": "now",
            "updated_at": "later",
        }

    mms_command_tools.handle_fake_upstream_command(
        ["on"],
        command_name="mmg",
        set_enabled=enabled_values.append,
        status_payload=status_payload,
        tail_log=lambda _tail: [],
        table_cls=_FakeTable,
        console=console,
    )

    assert enabled_values == [True]
    assert any("已开启" in str(item) for item in console.items)

    mms_command_tools.handle_fake_upstream_command(
        ["log", "--tail", "3"],
        command_name="mmg",
        set_enabled=enabled_values.append,
        status_payload=status_payload,
        tail_log=lambda tail: tail_values.append(tail) or [
            {"ts": "t1", "kind": "upstream", "host": "api.example", "request_body_preview": "redacted"},
        ],
        table_cls=_FakeTable,
        console=console,
    )

    assert tail_values == [3]
    table = console.items[-1]
    assert table.kwargs == {"title": "Fake Upstream Log"}
    assert table.rows[-1][0] == ("t1", "upstream", "api.example", "redacted")


def test_fake_upstream_form_body_is_redacted(monkeypatch, tmp_path):
    import httpx
    from mms_runtime.fake_upstream import ensure_local_proxy, tail_log

    monkeypatch.setenv("MMS_FAKE_UPSTREAM", "1")
    monkeypatch.setenv("MMS_REAL_HOME", str(tmp_path))

    proxy = ensure_local_proxy()
    ssl_ctx = ssl.create_default_context(cafile=proxy["ca_cert_path"])
    transport = httpx.HTTPTransport(proxy=proxy["proxy_url"], verify=ssl_ctx)
    with httpx.Client(transport=transport, timeout=5.0) as client:
        client.post(
            "https://anthropic.auth0.com/oauth/token",
            content="grant_type=password&username=test@example.com&password=secret-pass",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    rows = tail_log(20)
    upstream_rows = [row for row in rows if row.get("kind") == "upstream" and row.get("host") == "anthropic.auth0.com"]
    assert upstream_rows
    preview = upstream_rows[-1]["request_body_preview"]
    assert "secret-pass" not in preview
    assert "test@example.com" in preview


def test_fake_upstream_guard_still_requires_real_proxy(monkeypatch):
    import mms_launchers

    monkeypatch.setenv("MMS_FAKE_UPSTREAM", "1")

    guard = mms_launchers.build_claude_network_guard(
        {
            "id": "claude-tonnya",
            "auth_mode": "oauth",
            "proxy": "",
        },
        require_proxy=True,
    )

    assert guard["status"] == "blocked"
    assert "必须配置 proxy" in guard["block_reason"]


def test_handle_connect_swallows_tls_handshake_failure(monkeypatch):
    import mms_runtime.fake_upstream as mms_fake_upstream

    events = []

    class FakeContext:
        def load_cert_chain(self, certfile=None, keyfile=None):
            return None

        def wrap_socket(self, raw_socket, server_side=False):
            raise ssl.SSLError("bad certificate")

    class FakeSocket:
        def __init__(self):
            self.payloads = []
            self.closed = False

        def sendall(self, payload):
            self.payloads.append(payload)

        def close(self):
            self.closed = True

    monkeypatch.setattr(
        mms_fake_upstream,
        "_ensure_host_tls_cert",
        lambda _host: ("/tmp/cert.pem", "/tmp/key.pem", "/tmp/ca.pem"),
    )
    monkeypatch.setattr(mms_fake_upstream.ssl, "SSLContext", lambda _protocol: FakeContext())
    monkeypatch.setattr(mms_fake_upstream, "append_log", lambda kind, payload: events.append((kind, payload)))

    sock = FakeSocket()
    mms_fake_upstream._handle_connect(sock, "api.anthropic.com")

    assert sock.closed is True
    assert sock.payloads[0].startswith(b"HTTP/1.1 200 Connection Established")
    assert events[0][0] == "tls_handshake_failed"
    assert events[0][1]["host"] == "api.anthropic.com"


def test_ensure_host_tls_cert_rebuilds_stale_mismatched_pair(monkeypatch, tmp_path):
    import mms_runtime.fake_upstream as mms_fake_upstream

    if not shutil.which("openssl"):
        return

    monkeypatch.setenv("MMS_REAL_HOME", str(tmp_path))

    host_a_cert, host_a_key, _ = mms_fake_upstream._ensure_host_tls_cert("api.anthropic.com")
    host_b_cert, host_b_key, _ = mms_fake_upstream._ensure_host_tls_cert("api.github.com")

    with open(host_a_cert, "rb") as f:
        cert_bytes = f.read()
    with open(host_b_key, "rb") as f:
        key_bytes = f.read()
    with open(host_a_cert, "wb") as f:
        f.write(cert_bytes)
    with open(host_a_key, "wb") as f:
        f.write(key_bytes)

    assert mms_fake_upstream._cert_key_pair_matches(host_a_cert, host_a_key) is False

    repaired_cert, repaired_key, _ = mms_fake_upstream._ensure_host_tls_cert("api.anthropic.com")

    assert repaired_cert == host_a_cert
    assert repaired_key == host_a_key
    assert mms_fake_upstream._cert_key_pair_matches(repaired_cert, repaired_key) is True
