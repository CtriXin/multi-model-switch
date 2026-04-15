from __future__ import annotations

import io
import json
import os
import types
from datetime import datetime
from pathlib import Path


def test_build_claude_session_settings_only_inherits_allowlisted_keys(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(mms_launchers, "_load_mms_claude_settings_template", lambda: {})
    monkeypatch.setattr(mms_launchers, "_load_global_claude_settings_template", lambda: {})

    result = mms_launchers._build_claude_session_settings(
        {
            "theme": "dark",
            "hooks": {"preToolUse": [{"matcher": "*"}]},
            "statusLine": {"type": "command", "command": "/tmp/status.sh"},
            "permissions": {"allow": ["Read"]},
            "env": {"HTTP_PROXY": "http://127.0.0.1:7890"},
        },
        required_env={"HTTP_PROXY": "http://127.0.0.1:7890"},
        default_env={"CLAUDE_CODE_ATTRIBUTION_HEADER": "0"},
    )

    assert "theme" not in result
    assert result["hooks"]["preToolUse"][0]["matcher"] == "*"
    assert result["statusLine"]["type"] == "command"
    assert "statusline-command.sh" in result["statusLine"]["command"]
    assert "Read" in result["permissions"]["allow"]
    assert result["env"]["HTTP_PROXY"] == "http://127.0.0.1:7890"
    assert result["env"]["CLAUDE_CODE_ATTRIBUTION_HEADER"] == "0"


def test_prepare_claude_session_tree_removes_legacy_source_symlink(monkeypatch, tmp_path):
    import mms_launchers

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    monkeypatch.chdir(repo_dir)

    raw_root = tmp_path / "project-store"
    raw_root.mkdir()
    for entry in mms_launchers.CLAUDE_PERSISTENT_ENTRIES:
        (raw_root / entry).mkdir(exist_ok=True)

    monkeypatch.setattr(
        mms_launchers,
        "ensure_claude_project_store",
        lambda cwd, account_id="": {"project_key": "project-key"},
    )
    monkeypatch.setattr(
        mms_launchers,
        "claude_raw_entry_path",
        lambda entry, cwd, account_id="": raw_root / entry,
    )
    monkeypatch.setattr(mms_launchers, "record_claude_session_start", lambda **kwargs: None)
    monkeypatch.setattr(mms_launchers, "write_slot_marker", lambda *args, **kwargs: None)

    source_claude_dir = tmp_path / "source-claude"
    source_claude_dir.mkdir()
    (source_claude_dir / "agents").mkdir()

    session_claude_dir = tmp_path / "session" / ".claude"
    session_claude_dir.mkdir(parents=True)
    os.symlink(source_claude_dir / "agents", session_claude_dir / "agents")

    mms_launchers._prepare_claude_session_tree(
        str(tmp_path / "session"),
        str(session_claude_dir),
        account_id="claude-a",
        source_claude_dir=str(source_claude_dir),
    )

    assert not (session_claude_dir / "agents").exists()
    assert not os.path.islink(session_claude_dir / "agents")
    for entry in mms_launchers.CLAUDE_PERSISTENT_ENTRIES:
        assert os.path.islink(session_claude_dir / entry)


def test_link_claude_library_entries_replaces_broad_library_symlink(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    keychains = real_home / "Library" / "Keychains"
    keychains.mkdir(parents=True)
    (real_home / "Library" / "Preferences").mkdir()

    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )

    session_home = tmp_path / "session"
    session_home.mkdir()
    os.symlink(real_home / "Library", session_home / "Library")

    mms_launchers._link_claude_library_entries(str(session_home))

    session_library = session_home / "Library"
    assert session_library.is_dir()
    assert not session_library.is_symlink()
    assert os.path.islink(session_library / "Keychains")
    assert not (session_library / "Preferences").exists()


def test_finalize_claude_slot_stale_cleanup_skips_sync(monkeypatch, tmp_path):
    import mms_launchers

    session_home = tmp_path / "slot" / "1234"
    session_home.mkdir(parents=True)

    sync_calls = []
    monkeypatch.setattr(
        mms_launchers,
        "read_slot_marker",
        lambda _path: {"cwd": str(tmp_path), "account_id": "claude-a", "account_home": str(tmp_path / "account")},
    )
    monkeypatch.setattr(
        mms_launchers,
        "_sync_claude_session_state_to_account_home",
        lambda *args, **kwargs: sync_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(mms_launchers, "finalize_claude_session", lambda **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_record_account_guard_finalize", lambda *args, **kwargs: None)

    mms_launchers._finalize_claude_slot(str(session_home), stale_cleanup=True)

    assert sync_calls == []


def test_claude_guard_runtime_uses_gateway_home_for_api_key(monkeypatch, tmp_path):
    import mms_launchers

    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )

    result = mms_launchers._claude_guard_runtime({"id": "relay-a", "auth_mode": "api_key"})

    assert result["home_dir"] == str(tmp_path / ".config" / "mms" / "claude-gateway")


def test_launch_cli_enforces_network_guard_for_sensitive_claude_api_key_bypass(monkeypatch):
    import mms_launchers

    guard_calls = []
    account_guard_calls = []

    monkeypatch.setattr(mms_launchers, "validate_provider_for_cli", lambda cli, runtime: None)
    monkeypatch.setattr(
        mms_launchers,
        "_build_account_guard_report",
        lambda runtime: account_guard_calls.append(runtime) or {"status": "stable", "profile": {}, "active_sessions_after": 1, "score": 100, "drift_fields": []},
    )
    monkeypatch.setattr(
        mms_launchers,
        "_enforce_claude_network_guard_or_exit",
        lambda runtime, require_proxy=False: guard_calls.append((runtime.get("id"), require_proxy)),
    )
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["claude-sonnet-4-6"], "base_source": "remote"},
    )
    monkeypatch.setitem(mms_launchers.LAUNCHERS, "claude", lambda model_info, runtime, once=False: None)

    mms_launchers.launch_cli(
        "claude",
        {"model": "claude-sonnet-4-6"},
        {
            "id": "relay-a",
            "name": "relay-a",
            "auth_mode": "api_key",
            "api_key": "sk-test",
            "base_url": "https://relay.example.com",
            "skip_anthropic_probe": True,
            "bypass": True,
        },
        once=True,
    )

    assert guard_calls == [("relay-a", True)]
    assert account_guard_calls == []


def test_launch_cli_does_not_require_proxy_for_regular_api_key_bypass(monkeypatch):
    import mms_launchers

    guard_calls = []
    account_guard_calls = []

    monkeypatch.setattr(mms_launchers, "validate_provider_for_cli", lambda cli, runtime: None)
    monkeypatch.setattr(
        mms_launchers,
        "_build_account_guard_report",
        lambda runtime: account_guard_calls.append(runtime) or {"status": "stable", "profile": {}, "active_sessions_after": 1, "score": 100, "drift_fields": []},
    )
    monkeypatch.setattr(
        mms_launchers,
        "_enforce_claude_network_guard_or_exit",
        lambda runtime, require_proxy=False: guard_calls.append((runtime.get("id"), require_proxy)),
    )
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["claude-sonnet-4-6"], "base_source": "remote"},
    )
    monkeypatch.setitem(mms_launchers.LAUNCHERS, "claude", lambda model_info, runtime, once=False: None)

    mms_launchers.launch_cli(
        "claude",
        {"model": "claude-sonnet-4-6"},
        {
            "id": "newapi-personal-tokyo",
            "name": "newapi-personal-tokyo",
            "auth_mode": "api_key",
            "api_key": "sk-test",
            "base_url": "https://relay.example.com",
            "bypass": True,
        },
        once=True,
    )

    assert guard_calls == [("newapi-personal-tokyo", False)]
    assert account_guard_calls == []


def test_claude_bypass_requires_proxy_only_for_claude_account_or_sensitive_provider():
    import mms_launchers

    assert mms_launchers._claude_bypass_requires_proxy({"auth_mode": "oauth", "cli": "claude"}) is True
    assert mms_launchers._claude_bypass_requires_proxy({"auth_mode": "oauth", "cli": "gemini"}) is False
    assert mms_launchers._claude_bypass_requires_proxy({"auth_mode": "oauth", "cli": "codex"}) is False
    assert mms_launchers._claude_bypass_requires_proxy({"auth_mode": "api_key", "skip_anthropic_probe": True}) is True
    assert mms_launchers._claude_bypass_requires_proxy({"auth_mode": "api_key"}) is False


def test_resolve_anthropic_base_url_cache_is_scoped_by_configured_url(monkeypatch):
    import mms_launchers

    old_cache_key = mms_launchers._anthropic_cache_key("relay-a", "https://old.example.com")
    now_iso = datetime.now().isoformat()
    saved_cache = {}

    monkeypatch.setattr(
        mms_launchers,
        "_load_anthropic_url_file_cache",
        lambda: {old_cache_key: {"url": "https://old.example.com", "ts": now_iso}},
    )
    monkeypatch.setattr(mms_launchers, "_save_anthropic_url_file_cache", lambda payload: saved_cache.update(payload))
    mms_launchers._ANTHROPIC_URL_CACHE.clear()

    resolved, method = mms_launchers._resolve_anthropic_base_url(
        {
            "id": "relay-a",
            "api_key": "sk-test",
            "anthropic_base_url": "https://new.example.com",
            "skip_anthropic_probe": True,
        }
    )

    assert resolved == "https://new.example.com"
    assert method == "config_bypass"
    assert mms_launchers._anthropic_cache_key("relay-a", "https://new.example.com") in saved_cache


def test_load_probe_file_cache_marks_stale_and_preserves_error(monkeypatch, tmp_path):
    import mms_core

    monkeypatch.setattr(mms_core, "_PROBE_FILE_CACHE_DIR", str(tmp_path))
    cache_path = Path(mms_core._probe_file_cache_path("provider-a"))
    cache_path.write_text(
        json.dumps(
            {
                "raw_models": [],
                "working_url": "https://relay.example.com/v1",
                "base_source": "remote",
                "error": "probe failed",
                "error_kind": "http_error",
            }
        ),
        encoding="utf-8",
    )
    stale_ts = datetime.now().timestamp() - (mms_core._PROBE_FILE_CACHE_NEGATIVE_TTL + 10)
    os.utime(cache_path, (stale_ts, stale_ts))

    cached = mms_core._load_probe_file_cache("provider-a", allow_stale=True)
    base_result = mms_core._base_probe_result_from_cache("provider-a", cached)

    assert cached["is_stale"] is True
    assert base_result["error"] == "probe failed"
    assert base_result["error_kind"] == "http_error"
    assert base_result["is_stale"] is True


def test_provider_candidates_ignore_stale_probe_cache(monkeypatch):
    import mms_core

    monkeypatch.setattr(
        mms_core,
        "_load_probe_file_cache",
        lambda provider_id, allow_stale=False: (
            {"raw_models": ["fresh-model"], "is_stale": False}
            if provider_id == "fresh"
            else {"raw_models": ["stale-model"], "is_stale": True}
        ),
    )
    monkeypatch.setattr(mms_core, "resolve_provider_context", lambda cfg, provider_id: {"id": provider_id})

    candidates = mms_core._provider_candidates(
        {"providers": [{"id": "fresh"}, {"id": "stale"}]},
        {"id": "default"},
        ["default-model"],
    )

    assert candidates[1] == ({"id": "fresh"}, ["fresh-model"])
    assert candidates[2] == ({"id": "stale"}, None)


def test_provider_options_for_model_accepts_openai_base_url_only(monkeypatch):
    import mms_core

    provider = {
        "id": "relay-openai-only",
        "enabled": True,
        "openai_base_url": "https://relay.example.com/v1",
        "api_key": "sk-test",
        "protocols": ["responses", "openai_chat_completions"],
        "supported_clis": ["codex"],
        "models_endpoint": "manual",
        "fallback_models": ["gpt-5.4"],
    }
    monkeypatch.setattr(
        mms_core,
        "_provider_candidates",
        lambda cfg, default_provider, default_models: [(provider, ["gpt-5.4"])],
    )

    options = mms_core._provider_options_for_model(
        {},
        "codex",
        {"id": "default"},
        ["gpt-5.4"],
        model_info={"model": "gpt-5.4"},
    )

    assert options
    assert options[0]["id"] == "relay-openai-only"


def test_bridge_fallback_cache_is_scoped_by_gateway_url(monkeypatch):
    import mms_bridge

    monkeypatch.setattr(
        mms_bridge,
        "_save_bridge_mode_cache",
        lambda cache: setattr(mms_bridge, "_bridge_mode_cache_memory", dict(cache)),
    )
    mms_bridge._bridge_mode_cache_memory = {}

    mms_bridge._record_bridge_fallback("relay-a", "gpt-5.4", "https://gw-a.example.com/v1")

    assert mms_bridge._needs_chatcompletions_bridge("relay-a", "gpt-5.4", "https://gw-a.example.com/v1") is True
    assert mms_bridge._needs_chatcompletions_bridge("relay-a", "gpt-5.4", "https://gw-b.example.com/v1") is False


def test_claude_passthrough_rules_use_minimal_headers_for_sensitive_provider():
    import mms_bridge

    header_names, header_prefixes = mms_bridge._claude_passthrough_rules(
        types.SimpleNamespace(
            minimal_claude_header_passthrough=True,
            strip_upstream_user_agent=False,
        )
    )

    assert header_names == mms_bridge._CLAUDE_SENSITIVE_HEADER_PASSTHROUGH
    assert header_prefixes == ()


def test_responses_proxy_empty_body_fallback_does_not_cache(monkeypatch):
    import mms_bridge

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @staticmethod
        def read():
            return b""

        @staticmethod
        def close():
            return None

    recorded = []
    fallback_calls = []

    mms_bridge.httpx = types.SimpleNamespace(stream=lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)
    monkeypatch.setattr(mms_bridge, "_needs_chatcompletions_bridge", lambda *args, **kwargs: False)
    monkeypatch.setattr(mms_bridge, "_record_bridge_fallback", lambda *args, **kwargs: recorded.append((args, kwargs)))

    raw_body = json.dumps({"model": "gpt-5.4"}).encode("utf-8")
    handler = mms_bridge._ResponsesProxyHandler.__new__(mms_bridge._ResponsesProxyHandler)
    handler.path = "/v1/responses"
    handler.headers = {
        "content-length": str(len(raw_body)),
        "authorization": "Bearer bridge-token",
    }
    handler.rfile = io.BytesIO(raw_body)
    handler.wfile = io.BytesIO()
    handler.server = types.SimpleNamespace(
        bridge_token="bridge-token",
        gateway_key="gateway-key",
        gateway_url="https://gw-a.example.com/v1",
        model_name="gpt-5.4",
        provider_id="relay-a",
    )
    handler.send_response = lambda *args, **kwargs: None
    handler.send_header = lambda *args, **kwargs: None
    handler.end_headers = lambda *args, **kwargs: None
    handler._do_chatcompletions_fallback = lambda *args, **kwargs: fallback_calls.append((args, kwargs))

    handler.do_POST()

    assert fallback_calls
    assert recorded == []


def test_copy_claude_state_json_oauth_mode_allowlists_auth_state(tmp_path):
    import mms_launchers

    src = tmp_path / "src.json"
    dst = tmp_path / "nested" / "dst.json"
    src.write_text(
        json.dumps(
            {
                "userID": "user-1",
                "firstStartTime": "2026-04-15T10:00:00Z",
                "numStartups": 7,
                "bypassPermissionsModeAccepted": True,
                "alwaysThinkingEnabled": True,
                "hasCompletedOnboarding": True,
                "lastOnboardingVersion": "1.2.3",
                "installMethod": "native",
                "oauthAccount": {
                    "accountUuid": "acct-1",
                    "emailAddress": "u@example.com",
                    "organizationUuid": "org-1",
                    "displayName": "User",
                    "workspaceRole": "owner",
                    "unexpected": "drop-me",
                },
                "claudeAiOauth": {
                    "accessToken": "tok-1",
                    "refreshToken": "refresh-1",
                    "expiresAt": "2026-04-16T10:00:00Z",
                    "emailAddress": "u@example.com",
                    "extra": "drop-me",
                },
                "provider": "gateway",
                "api_key": "sk-test",
                "projects": {"/tmp/repo": {"lastSessionId": "abc"}},
                "customApiKeyResponses": {"demo": "x"},
                "anonymousId": "anon-1",
            }
        ),
        encoding="utf-8",
    )

    mms_launchers._copy_claude_state_json(str(src), str(dst), mode="oauth")

    result = json.loads(dst.read_text(encoding="utf-8"))
    assert result == {
        "userID": "user-1",
        "firstStartTime": "2026-04-15T10:00:00Z",
        "numStartups": 7,
        "bypassPermissionsModeAccepted": True,
        "alwaysThinkingEnabled": True,
        "hasCompletedOnboarding": True,
        "lastOnboardingVersion": "1.2.3",
        "installMethod": "native",
        "oauthAccount": {
            "accountUuid": "acct-1",
            "emailAddress": "u@example.com",
            "organizationUuid": "org-1",
            "displayName": "User",
            "workspaceRole": "owner",
        },
        "claudeAiOauth": {
            "accessToken": "tok-1",
            "refreshToken": "refresh-1",
            "expiresAt": "2026-04-16T10:00:00Z",
            "emailAddress": "u@example.com",
        },
    }


def test_account_env_scrubs_claude_oauth_parent_env(monkeypatch, tmp_path):
    import mms_launchers

    account_home = tmp_path / "account-home"
    real_home = tmp_path / "real-home"
    real_home.mkdir()

    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-parent")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://relay.example.com")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("CLAUDE_CODE_SUBAGENT_MODEL", "claude-haiku-4-5")
    monkeypatch.setenv("CLAUDE_CODE_ATTRIBUTION_HEADER", "1")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:7890")

    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_claude_library_entries", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_prepare_claude_session_tree", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_persist_account_guard_launch", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))

    env = mms_launchers._account_env(
        {"id": "claude-a", "cli": "claude", "home_dir": str(account_home)},
        validate_proxy=False,
    )

    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert "ANTHROPIC_BASE_URL" not in env
    assert "ANTHROPIC_MODEL" not in env
    assert "CLAUDE_CODE_SUBAGENT_MODEL" not in env
    assert "CLAUDE_CODE_ATTRIBUTION_HEADER" not in env
    assert env["HTTP_PROXY"] == "http://127.0.0.1:7890"
    assert env["HOME"].startswith(str(account_home / "s"))


def test_install_session_command_wrappers_covers_global_mutating_commands(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    isolated_home = tmp_path / "isolated-home"
    real_home.mkdir()
    isolated_home.mkdir()

    monkeypatch.setenv(
        "PATH",
        os.pathsep.join(
            [
                str(isolated_home / ".mms" / "bin"),
                str(isolated_home / ".local" / "bin"),
                "/usr/local/bin",
                "/usr/bin",
            ]
        ),
    )
    monkeypatch.setenv("HOME", str(isolated_home))
    monkeypatch.setattr(mms_launchers, "_real_user_home", lambda: str(real_home))
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))

    env = {"PATH": "/usr/local/bin:/usr/bin"}
    session_home = tmp_path / "session-home"
    mms_launchers._install_session_command_wrappers(str(session_home), env)

    wrapper_dir = session_home / ".mms" / "bin"
    for command_name in ("pm2", "claude", "npm", "pnpm", "npx", "yarn", "corepack"):
        wrapper_path = wrapper_dir / command_name
        assert wrapper_path.exists()
        script = wrapper_path.read_text(encoding="utf-8")
        assert f'command -v "{command_name}"' in script
        assert str(isolated_home / ".mms" / "bin") not in script
        assert str(isolated_home / ".local" / "bin") not in script
        assert f'export HOME="{real_home}"' in script
        assert f'export XDG_CONFIG_HOME="{real_home / ".config"}"' in script
    assert f'export PM2_HOME="{real_home / ".pm2"}"' in (wrapper_dir / "pm2").read_text(encoding="utf-8")
    assert env["PATH"].startswith(str(wrapper_dir) + os.pathsep)


def test_resolve_anthropic_base_url_probe_metadata_is_neutral(monkeypatch):
    import mms_launchers

    captured = {}

    def fake_detect(url, endpoint, headers, body=None, timeout=0, runtime=None):
        captured["url"] = url
        captured["endpoint"] = endpoint
        captured["body"] = body
        return url

    monkeypatch.setattr(mms_launchers, "detect_working_base_url", fake_detect)
    monkeypatch.setattr(mms_launchers, "_remember_anthropic_url", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_load_anthropic_url_file_cache", lambda: {})
    monkeypatch.setattr(mms_launchers, "_save_anthropic_url_file_cache", lambda payload: None)
    mms_launchers._ANTHROPIC_URL_CACHE.clear()

    resolved, method = mms_launchers._resolve_anthropic_base_url(
        {
            "id": "relay-a",
            "api_key": "sk-test",
            "anthropic_base_url": "https://relay.example.com",
        }
    )

    body = json.loads(captured["body"].decode("utf-8"))
    metadata_user_id = json.loads(body["metadata"]["user_id"])

    assert resolved == "https://relay.example.com"
    assert method == "probed"
    assert metadata_user_id["device_id"].startswith("device-")
    assert metadata_user_id["session_id"].startswith("session-")
    assert "account_uuid" not in metadata_user_id
    assert "mms-probe-" not in metadata_user_id["device_id"]
    assert "mms-probe-" not in metadata_user_id["session_id"]


def test_gateway_health_check_cache_is_scoped_per_provider(monkeypatch, tmp_path):
    import mms_launchers

    health_path = tmp_path / "health_check.json"
    monkeypatch.setattr(mms_launchers, "HEALTH_CHECK_PATH", str(health_path))
    monkeypatch.setattr(mms_launchers, "_gateway_ping", lambda *args, **kwargs: True)
    monkeypatch.setattr(mms_launchers, "_openai_base_url", lambda provider: provider.get("base_url"))
    monkeypatch.setattr(mms_launchers, "_anthropic_base_url", lambda provider: "")

    provider_a = {"id": "relay-a", "base_url": "https://relay-a.example.com", "api_key": "sk-a"}
    provider_b = {"id": "relay-b", "base_url": "https://relay-b.example.com", "api_key": "sk-b"}

    mms_launchers.gateway_health_check(provider_a)
    mms_launchers.gateway_health_check(provider_b)

    assert mms_launchers._health_check_due("relay-a") is False
    assert mms_launchers._health_check_due("relay-b") is False

    saved = json.loads(health_path.read_text(encoding="utf-8"))
    assert set(saved["providers"].keys()) == {"relay-a", "relay-b"}


def test_gateway_claude_bridge_binds_ephemeral_port_and_waits_ready(monkeypatch):
    import mms_bridge

    calls = {"wait": [], "closed": 0}

    class FakeServer:
        def __init__(self, addr, handler):
            calls["addr"] = addr
            calls["handler"] = handler
            self.server_address = ("127.0.0.1", 54321)

        def serve_forever(self):
            return None

        def server_close(self):
            calls["closed"] += 1

    class FakeThread:
        def __init__(self, target=None, daemon=None):
            self.target = target
            self.daemon = daemon

        def start(self):
            calls["started"] = True

        def join(self, timeout=None):
            calls["joined"] = timeout

    monkeypatch.setattr(mms_bridge, "_SilentHTTPServer", FakeServer)
    monkeypatch.setattr(mms_bridge.threading, "Thread", FakeThread)
    monkeypatch.setattr(
        mms_bridge,
        "_wait_local_server_ready",
        lambda port, attempts=50, delay=0.1: calls["wait"].append((port, attempts, delay)) or True,
    )

    with mms_bridge.gateway_claude_bridge("https://relay.example.com/v1", "sk-test") as bridge_cfg:
        assert bridge_cfg["base_url"] == "http://127.0.0.1:54321"
        assert bridge_cfg["api_key"].startswith("mms-bridge-")

    assert calls["addr"] == ("127.0.0.1", 0)
    assert calls["wait"] == [(54321, 50, 0.1)]
    assert calls["closed"] == 1


def test_chatcompletions_fallback_429_respects_retry_after_without_fanout(monkeypatch):
    import mms_bridge

    class FakeResponse:
        def __init__(self, status_code, body, headers=None):
            self.status_code = status_code
            self._body = body.encode("utf-8")
            self.headers = headers or {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return self._body

        @staticmethod
        def iter_lines():
            return iter(())

    calls = []
    sleep_calls = []
    response = FakeResponse(429, "rate limited", {"Retry-After": "3"})

    def fake_stream(method, url, **kwargs):
        calls.append(url)
        return response

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(stream=fake_stream))
    monkeypatch.setattr(
        mms_bridge,
        "_build_gateway_candidate_urls",
        lambda *args, **kwargs: [
            "https://gw-a.example.com/chat/completions",
            "https://gw-b.example.com/chat/completions",
        ],
    )
    monkeypatch.setattr(mms_bridge.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    handler = mms_bridge._ResponsesProxyHandler.__new__(mms_bridge._ResponsesProxyHandler)
    handler.headers = {}
    handler.wfile = io.BytesIO()
    handler.server = types.SimpleNamespace(speed_scope=None)
    status = {}
    sent_headers = {}
    handler.send_response = lambda code: status.setdefault("code", code)
    handler.send_header = lambda name, value: sent_headers.setdefault(name, value)
    handler.end_headers = lambda: None

    handler._do_chatcompletions_fallback(
        {"input": [], "instructions": ""},
        "gpt-5.4",
        "https://gw-root.example.com",
        "gateway-key",
        0,
    )

    assert calls == [
        "https://gw-a.example.com/chat/completions",
        "https://gw-a.example.com/chat/completions",
    ]
    assert sleep_calls == [2.0]
    assert status["code"] == 429
    assert sent_headers["Retry-After"] == "3"
    assert b"rate limited" in handler.wfile.getvalue()


def test_llm_classify_retries_retry_after_on_429(monkeypatch):
    import mms_router

    class FakeResponse:
        def __init__(self, status_code, payload=None, text="", headers=None, url="https://relay.example.com/v1/messages"):
            self.status_code = status_code
            self._payload = payload or {}
            self.text = text
            self.headers = headers or {}
            self.url = url

        def json(self):
            return self._payload

    calls = []
    sleep_calls = []
    responses = iter(
        [
            FakeResponse(429, text="rate limited", headers={"Retry-After": "1"}),
            FakeResponse(
                200,
                payload={
                    "content": [{"type": "text", "text": "LIGHT HIGH"}],
                    "usage": {"input_tokens": 8, "output_tokens": 2},
                },
            ),
        ]
    )

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(url)
        return next(responses)

    monkeypatch.setattr(mms_router, "_httpx", types.SimpleNamespace(post=fake_post))
    monkeypatch.setattr(mms_router.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    result = mms_router._llm_classify(
        "fix typo in docs",
        "https://relay.example.com",
        "sk-test",
        "claude-sonnet-4-6",
    )

    assert result == ("light", "high")
    assert calls == [
        "https://relay.example.com/v1/messages",
        "https://relay.example.com/v1/messages",
    ]
    assert sleep_calls == [1.0]
