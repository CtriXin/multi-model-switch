from __future__ import annotations

import json
import ssl
import stat


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
    from mms_fake_upstream import tail_log

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
    from mms_fake_upstream import ensure_local_proxy, status_payload, tail_log

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


def test_apply_runtime_network_profile_routes_to_local_fake_proxy(monkeypatch, tmp_path):
    import mms_launchers

    monkeypatch.setenv("MMS_FAKE_UPSTREAM", "1")
    monkeypatch.setenv("MMS_REAL_HOME", str(tmp_path))

    env = {}
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

    assert result["HTTP_PROXY"].startswith("http://127.0.0.1:")
    assert result["HTTPS_PROXY"].startswith("http://127.0.0.1:")
    assert result["NODE_EXTRA_CA_CERTS"].endswith("fake-upstream-ca-cert.pem")
    assert result["SSL_CERT_FILE"].endswith("fake-upstream-ca-cert.pem")
    assert "NODE_TLS_REJECT_UNAUTHORIZED" not in result
    assert result["MMS_FAKE_UPSTREAM_ORIGINAL_PROXY"] == "http://198.51.100.24:6394+auth"
    assert result["NO_PROXY"] == "127.0.0.1,localhost,::1"


def test_fake_upstream_patch_httpx_module(monkeypatch, tmp_path):
    import httpx
    from mms_fake_upstream import patch_httpx_module

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


def test_fake_upstream_form_body_is_redacted(monkeypatch, tmp_path):
    import httpx
    from mms_fake_upstream import ensure_local_proxy, tail_log

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
