"""Isolation tests for Claude account/project state handling."""

from __future__ import annotations

import json
import types
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def scoped_store(tmp_path):
    config_root = tmp_path / "config"
    projects_root = config_root / "projects"
    with patch("mms_project_store.PRIMARY_CONFIG_DIR", config_root), patch(
        "mms_project_store.PROJECTS_DIR",
        projects_root,
    ), patch("mms_session_index.PRIMARY_CONFIG_DIR", config_root):
        yield config_root, projects_root


def test_project_key_is_scoped_by_account(tmp_path):
    from mms_project_store import project_key

    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    shared_a = project_key(str(project_dir), account_id="claude-a")
    shared_b = project_key(str(project_dir), account_id="claude-b")
    shared_a_again = project_key(str(project_dir), account_id="claude-a")

    assert shared_a != shared_b
    assert shared_a == shared_a_again


def test_project_store_starts_empty_without_global_seed(tmp_path, scoped_store):
    _config_root, _projects_root = scoped_store
    from mms_project_store import claude_project_metadata_path, ensure_claude_project_store

    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    store = ensure_claude_project_store(str(project_dir), account_id="claude-a")

    history_path = Path(store["raw_root"]) / "history.jsonl"
    assert history_path.exists()
    assert history_path.read_text(encoding="utf-8") == ""

    metadata_path = claude_project_metadata_path(str(project_dir), account_id="claude-a")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["account_id"] == "claude-a"


def test_seed_claude_state_does_not_copy_global_user_identity(tmp_path):
    from mms_account_state import seed_claude_state

    account_home = tmp_path / "account-home"
    account_home.mkdir()

    seed_claude_state(str(account_home))

    state_path = account_home / ".claude.json"
    assert state_path.exists()
    assert json.loads(state_path.read_text(encoding="utf-8")) == {}


def test_session_index_isolated_by_account(tmp_path, scoped_store):
    _config_root, _projects_root = scoped_store
    from mms_session_index import list_indexed_sessions, record_claude_session_start

    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    record_claude_session_start(
        cwd=str(project_dir),
        account_id="claude-a",
        pid=101,
        runtime_kind="oauth",
        slot_home="/tmp/slot-a",
    )
    record_claude_session_start(
        cwd=str(project_dir),
        account_id="claude-b",
        pid=202,
        runtime_kind="oauth",
        slot_home="/tmp/slot-b",
    )

    rows = list_indexed_sessions("claude")
    accounts = {item["account_id"] for item in rows}
    pids = {item["pid"] for item in rows}

    assert {"claude-a", "claude-b"} <= accounts
    assert {101, 202} <= pids


def test_sync_claude_session_state_back_to_account(tmp_path):
    from mms_launchers import _sync_claude_session_state_to_account_home

    session_home = tmp_path / "session"
    account_home = tmp_path / "account"
    (session_home / ".claude").mkdir(parents=True)

    (session_home / ".claude.json").write_text(
        json.dumps({"userID": "device-b", "numStartups": 3}),
        encoding="utf-8",
    )
    (session_home / ".claude" / "settings.json").write_text(
        json.dumps({"theme": "dark"}),
        encoding="utf-8",
    )

    _sync_claude_session_state_to_account_home(str(session_home), str(account_home))

    assert json.loads((account_home / ".claude.json").read_text(encoding="utf-8"))["userID"] == "device-b"
    assert json.loads((account_home / ".claude" / "settings.json").read_text(encoding="utf-8"))["theme"] == "dark"


def test_apply_runtime_network_profile_sets_proxy_and_timezone():
    from mms_launchers import _apply_runtime_network_profile

    env = {}
    runtime = {
        "id": "claude-b",
        "proxy": "http://127.0.0.1:7890",
        "no_proxy": "localhost,127.0.0.1",
        "timezone": "Asia/Singapore",
    }

    with patch("mms_launchers._check_proxy_connectivity_or_exit") as check_proxy:
        result = _apply_runtime_network_profile(env, runtime, validate_proxy=True)

    check_proxy.assert_called_once()
    assert result["HTTP_PROXY"] == "http://127.0.0.1:7890"
    assert result["HTTPS_PROXY"] == "http://127.0.0.1:7890"
    assert result["NO_PROXY"] == "localhost,127.0.0.1"
    assert result["TZ"] == "Asia/Singapore"


def test_normalize_account_keeps_proxy_and_timezone():
    from mms_core import _normalize_account

    account = _normalize_account(
        {
            "id": "claude-b",
            "cli": "claude",
            "proxy": "http://127.0.0.1:7890",
            "no_proxy": "localhost",
            "timezone": "Asia/Singapore",
        }
    )

    assert account["proxy"] == "http://127.0.0.1:7890"
    assert account["no_proxy"] == "localhost"
    assert account["timezone"] == "Asia/Singapore"


def test_normalize_account_defaults_timezone_to_us():
    from mms_core import DEFAULT_ACCOUNT_TIMEZONE, _normalize_account

    account = _normalize_account(
        {
            "id": "claude-default",
            "cli": "claude",
        }
    )

    assert account["timezone"] == DEFAULT_ACCOUNT_TIMEZONE


def test_normalize_provider_keeps_proxy_and_timezone():
    from mms_core import _normalize_provider

    provider = _normalize_provider(
        {
            "id": "gateway-b",
            "proxy": "http://127.0.0.1:7890",
            "no_proxy": "localhost",
            "timezone": "America/Los_Angeles",
        }
    )

    assert provider["proxy"] == "http://127.0.0.1:7890"
    assert provider["no_proxy"] == "localhost"
    assert provider["timezone"] == "America/Los_Angeles"


def test_normalize_provider_defaults_timezone_to_us():
    from mms_core import DEFAULT_ACCOUNT_TIMEZONE, _normalize_provider

    provider = _normalize_provider({"id": "gateway-default"})

    assert provider["timezone"] == DEFAULT_ACCOUNT_TIMEZONE


def test_detect_working_base_url_uses_runtime_proxy(monkeypatch):
    import mms_core

    calls = {}

    class FakeResponse:
        status_code = 200

    def fake_request(method, url, **kwargs):
        calls["method"] = method
        calls["url"] = url
        calls["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr(mms_core, "_runtime_httpx_request", fake_request)

    candidate = mms_core.detect_working_base_url(
        "https://gateway.example.com",
        "/v1/messages",
        {"x-api-key": "sk-test"},
        body=b"{}",
        runtime={"proxy": "http://127.0.0.1:7890"},
    )

    assert candidate == "https://gateway.example.com"
    assert calls["method"] == "POST"
    assert calls["kwargs"]["runtime"]["proxy"] == "http://127.0.0.1:7890"


def test_probe_models_uses_provider_proxy(monkeypatch):
    import mms_core

    calls = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"data": [{"id": "claude-sonnet-4-6"}]}

    def fake_request(method, url, **kwargs):
        calls["method"] = method
        calls["url"] = url
        calls["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr(mms_core, "_runtime_httpx_request", fake_request)
    monkeypatch.setattr(mms_core, "_save_probe_file_cache", lambda *args, **kwargs: None)

    result = mms_core._probe_models(
        {
            "id": "gateway-proxy",
            "base_url": "https://gateway.example.com",
            "api_key": "sk-test",
            "protocols": ["openai_chat_completions"],
            "proxy": "http://127.0.0.1:7890",
        },
        emit_output=False,
        force_refresh=True,
        skip_cache=True,
    )

    assert result["models"] == ["claude-sonnet-4-6"]
    assert calls["method"] == "GET"
    assert calls["kwargs"]["runtime"]["proxy"] == "http://127.0.0.1:7890"


def test_gateway_ping_uses_runtime_proxy(monkeypatch):
    import mms_launchers

    calls = {}

    def fake_request(method, url, **kwargs):
        calls["method"] = method
        calls["url"] = url
        calls["kwargs"] = kwargs
        return types.SimpleNamespace(status_code=200)

    monkeypatch.setattr(mms_launchers, "_runtime_httpx_request", fake_request)
    monkeypatch.setattr(mms_launchers, "_build_gateway_url", lambda base_url, path: f"{base_url.rstrip('/')}{path}")

    ok = mms_launchers._gateway_ping(
        "https://gateway.example.com/v1",
        "sk-test",
        runtime={"proxy": "http://127.0.0.1:7890"},
    )

    assert ok is True
    assert calls["method"] == "GET"
    assert calls["kwargs"]["runtime"]["proxy"] == "http://127.0.0.1:7890"


def test_validate_proxy_url_accepts_mainstream_formats():
    from mms_core import _validate_proxy_url

    assert _validate_proxy_url("http://user:pass@168.158.185.127:6394") is None
    assert _validate_proxy_url("socks5h://127.0.0.1:7890") is None


def test_validate_proxy_url_rejects_invalid_scheme():
    from mms_core import _validate_proxy_url

    assert _validate_proxy_url("socket5://127.0.0.1:7890") == "代理协议仅支持 http / https / socks5 / socks5h"


def test_runtime_httpx_request_prefers_ipv4(monkeypatch):
    import mms_core

    calls = {}

    class FakeTransport:
        def __init__(self, **kwargs):
            calls["transport_kwargs"] = kwargs

    class FakeClient:
        def __init__(self, *, transport=None, follow_redirects=False):
            calls["follow_redirects"] = follow_redirects
            calls["transport"] = transport

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def request(self, method, url, **kwargs):
            calls["method"] = method
            calls["url"] = url
            calls["request_kwargs"] = kwargs
            return types.SimpleNamespace(status_code=200)

    monkeypatch.setattr(
        mms_core,
        "httpx",
        types.SimpleNamespace(HTTPTransport=FakeTransport, Client=FakeClient),
    )

    response = mms_core._runtime_httpx_request(
        "GET",
        "https://gateway.example.com/models",
        runtime={"force_ipv4": True, "proxy": "http://127.0.0.1:7890"},
        headers={"Authorization": "Bearer sk-test"},
        timeout=8,
    )

    assert response.status_code == 200
    assert calls["transport_kwargs"]["proxy"] == "http://127.0.0.1:7890"
    assert calls["transport_kwargs"]["trust_env"] is False
    assert calls["transport_kwargs"]["local_address"] == "0.0.0.0"


def test_apply_runtime_ip_stack_profile_sets_ipv4first():
    from mms_launchers import _apply_runtime_ip_stack_profile

    env = {"NODE_OPTIONS": "--max-old-space-size=4096"}
    runtime = {"id": "claude-b", "force_ipv4": True}

    result = _apply_runtime_ip_stack_profile(env, runtime)

    assert result["MMS_FORCE_IPV4"] == "1"
    assert "--dns-result-order=ipv4first" in result["NODE_OPTIONS"]


def test_test_proxy_connectivity_accepts_http_404(monkeypatch):
    import mms_core

    monkeypatch.setattr(
        mms_core.subprocess,
        "run",
        lambda *args, **kwargs: types.SimpleNamespace(returncode=0, stdout="404", stderr=""),
    )

    ok, detail = mms_core._test_proxy_connectivity("http://127.0.0.1:7890")

    assert ok is True
    assert "HTTP 404" in detail


def test_runtime_network_summary_masks_proxy_secret():
    from mms_launchers import _runtime_network_summary

    summary = _runtime_network_summary(
        {
            "proxy": "http://uqdefwnm:mxewpcc42roq@168.158.185.127:6394",
            "timezone": "America/Los_Angeles",
            "force_ipv4": True,
        }
    )

    assert "mxewpcc42roq" not in summary
    assert "168.158.185.127:6394" in summary
    assert "TZ America/Los_Angeles" in summary
    assert "IPv4 on" in summary


def test_account_guard_report_detects_profile_drift(monkeypatch, tmp_path):
    import mms_launchers

    state_path = tmp_path / "account-guard-state.json"
    state_path.write_text(
        json.dumps(
            {
                "accounts": {
                    "claude-a": {
                        "last_profile": {
                            "proxy_fingerprint": "http://1.1.1.1:80",
                            "timezone": "America/Los_Angeles",
                            "force_ipv4": True,
                            "no_proxy": "",
                        },
                        "consecutive_failures": 1,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mms_launchers, "_account_guard_state_path", lambda: str(state_path))
    monkeypatch.setattr(mms_launchers, "_count_live_session_dirs", lambda _path: 1)

    report = mms_launchers._build_account_guard_report(
        {
            "id": "claude-a",
            "home_dir": str(tmp_path / "account"),
            "proxy": "http://2.2.2.2:90",
            "timezone": "America/New_York",
            "force_ipv4": False,
            "no_proxy": "localhost",
        }
    )

    assert report["status"] == "risky"
    assert report["active_sessions_after"] == 2
    assert set(report["drift_fields"]) == {"proxy", "timezone", "ipv4", "no_proxy"}
    assert report["score"] < 85


def test_account_guard_report_blocks_excessive_parallel_sessions(monkeypatch, tmp_path):
    import mms_launchers

    monkeypatch.setattr(mms_launchers, "_account_guard_state_path", lambda: str(tmp_path / "guard.json"))
    monkeypatch.setattr(mms_launchers, "_count_live_session_dirs", lambda _path: 4)

    report = mms_launchers._build_account_guard_report(
        {
            "id": "claude-a",
            "home_dir": str(tmp_path / "account"),
            "timezone": "America/Los_Angeles",
        }
    )

    assert report["status"] == "blocked"
    assert "安全上限 4" in report["blocked_reason"]


def test_record_account_guard_finalize_tracks_failures(monkeypatch, tmp_path):
    import mms_launchers

    state_path = tmp_path / "account-guard-state.json"
    monkeypatch.setattr(mms_launchers, "_account_guard_state_path", lambda: str(state_path))

    mms_launchers._persist_account_guard_launch(
        "claude-a",
        {
            "profile": {
                "proxy_fingerprint": "direct",
                "timezone": "America/Los_Angeles",
                "force_ipv4": True,
                "no_proxy": "",
            },
            "score": 100,
            "status": "stable",
            "drift_fields": [],
            "active_sessions_after": 1,
        },
        session_home=str(tmp_path / "session"),
    )
    mms_launchers._record_account_guard_finalize("claude-a", exit_code=1)
    mms_launchers._record_account_guard_finalize("claude-a", exit_code=2)

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    account = payload["accounts"]["claude-a"]
    assert account["consecutive_failures"] == 2
    assert account["last_exit_code"] == 2

    mms_launchers._record_account_guard_finalize("claude-a", exit_code=0)
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["accounts"]["claude-a"]["consecutive_failures"] == 0
