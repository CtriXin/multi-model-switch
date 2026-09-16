import os
from pathlib import Path

import pytest
import tomllib


@pytest.fixture(autouse=True)
def isolate_pi_capability_bundle(monkeypatch):
    import mms_launchers

    real_resolve = mms_launchers._pi_support.resolve_model_capabilities

    def resolve_without_default_bundle(*args, **kwargs):
        kwargs.setdefault("approved_facts", {})
        kwargs.setdefault("model_policy", {})
        return real_resolve(*args, **kwargs)

    monkeypatch.setattr(mms_launchers._pi_support, "resolve_model_capabilities", resolve_without_default_bundle)


def _openai_runtime(**overrides):
    runtime = {
        "id": "relay-a",
        "name": "Relay A",
        "enabled": True,
        "auth_mode": "api_key",
        "api_key": "sk-openai",
        "openai_base_url": "https://relay.example.com/v1",
        "protocols": ["openai_chat_completions"],
        "supported_clis": ["codex"],
        "thinking_mode": "disable",
    }
    runtime.update(overrides)
    return runtime


def _anthropic_runtime(**overrides):
    runtime = {
        "id": "relay-b",
        "name": "Relay B",
        "enabled": True,
        "auth_mode": "api_key",
        "api_key": "sk-ant",
        "anthropic_base_url": "https://relay.example.com/anthropic",
        "protocols": ["anthropic_messages"],
        "supported_clis": ["claude"],
    }
    runtime.update(overrides)
    return runtime


def _patch_launch_env(monkeypatch, mms_launchers, tmp_path):
    real_home = tmp_path / "real-home"
    real_home.mkdir()
    (real_home / ".grok").mkdir()
    (real_home / ".grok" / "auth.json").write_text('{"access_token":"real-session"}\n', encoding="utf-8")
    preview_root = tmp_path / "mms-next"
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_selected_mms_config_root", lambda _env: str(preview_root))
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_launchers, "_scrub_inherited_runtime_env", lambda env, **_kwargs: env)
    monkeypatch.setattr(mms_launchers, "_inject_real_home_hints", lambda env, include_xdg=False: env)
    monkeypatch.setattr(mms_launchers, "_inject_host_capability_hints", lambda env: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=False: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_locale_profile", lambda env, runtime: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_ip_stack_profile", lambda env, runtime: env)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_launchers, "_install_session_packet_env", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(mms_launchers, "_resolve_web_access_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_weber_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_toon_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_token_saver_root", lambda: "")
    monkeypatch.setattr(mms_launchers.os, "getpid", lambda: 4242)
    monkeypatch.setattr(
        "mms_grok_support._install_grok_compat_proxy",
        lambda payload, grok_home: payload,
    )
    return real_home, preview_root


def test_grok_compat_fills_minimax_stream_usage_prompt_tokens():
    from mms_grok_compat import rewrite_sse_text

    raw = (
        'data: {"id":"x","choices":[{"index":0,"delta":{"role":"assistant"}}],'
        '"model":"MiniMax-M2.7","object":"chat.completion.chunk",'
        '"usage":{"total_tokens":0,"total_characters":0}}\n\n'
    )
    rewritten = rewrite_sse_text(raw)
    payload = rewritten.split("data:", 1)[1].strip()
    import json

    obj = json.loads(payload)
    assert obj["usage"]["prompt_tokens"] == 0
    assert obj["usage"]["completion_tokens"] == 0


def test_grok_compat_converts_minimax_final_message_chunk_to_delta():
    import json
    from mms_grok_compat import rewrite_sse_text

    raw = (
        'data: {"id":"x","choices":[{"finish_reason":"stop","index":0,'
        '"message":{"content":"hello","role":"assistant"}}],'
        '"model":"MiniMax-M2.7","object":"chat.completion.chunk",'
        '"usage":{"total_tokens":84,"prompt_tokens":42,"completion_tokens":42}}\n\n'
    )
    obj = json.loads(rewrite_sse_text(raw).split("data:", 1)[1].strip())
    assert "delta" in obj["choices"][0]
    assert obj["choices"][0]["delta"] == {}
    assert "message" not in obj["choices"][0]
    assert obj["choices"][0]["finish_reason"] == "stop"


def test_grok_compat_proxy_rewrites_live_sse_chunk(tmp_path):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    import mms_grok_compat

    chunk = (
        b'data: {"id":"x","choices":[{"index":0,"delta":{"role":"assistant"}}],'
        b'"model":"MiniMax-M2.7","object":"chat.completion.chunk",'
        b'"usage":{"total_tokens":0,"total_characters":0}}\n\n'
    )

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            return

        def do_POST(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(chunk)

    upstream = HTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{upstream.server_address[1]}"
    listen = mms_grok_compat.start_compat_proxy(
        origin,
        parent_pid=os.getpid(),
        log_path=str(tmp_path / "compat.log"),
    )
    import urllib.request

    req = urllib.request.Request(
        listen + "/v1/chat/completions",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        body = resp.read().decode("utf-8")
    upstream.shutdown()
    obj = json.loads(body.split("data:", 1)[1].strip())
    assert obj["usage"]["prompt_tokens"] == 0
    assert obj["usage"]["completion_tokens"] == 0


def test_core_grok_cli_is_visible_and_provider_compat_is_implied():
    import mms_core

    provider = {
        "id": "relay-a",
        "name": "Relay A",
        "enabled": True,
        "api_key": "sk-test",
        "openai_base_url": "https://relay.example.com/v1",
        "protocols": ["openai_chat_completions"],
        "supported_clis": ["codex"],
    }
    assert "grok" in mms_core.CLI_NAMES
    assert mms_core._provider_supports_cli_name(provider, "grok") is True


def test_launch_grok_writes_isolated_openai_config_and_hides_builtin_models(monkeypatch, tmp_path):
    import mms_launchers

    captured = {}
    real_home, preview_root = _patch_launch_env(monkeypatch, mms_launchers, tmp_path)
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["gpt-5.4", "gpt-5.5"]},
    )

    def fake_exec(cmd, env, once, **_kwargs):
        captured["cmd"] = cmd
        captured["env"] = dict(env)
        captured["once"] = once

    monkeypatch.setattr(mms_launchers, "_exec_or_run", fake_exec)
    monkeypatch.setenv("XAI_API_KEY", "xai-should-not-leak")

    mms_launchers.launch_grok({"model": "gpt-5.4"}, _openai_runtime(), once=True)

    assert captured["cmd"][:3] == ["grok", "-m", "gpt-5.4"]
    assert "--effort" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--effort") + 1] == "none"
    assert captured["once"] is True
    grok_home = Path(captured["env"]["GROK_HOME"])
    assert grok_home == preview_root / "grok-gateway" / "s" / "4242" / "home"
    assert grok_home.is_dir()
    assert not (grok_home / "auth.json").exists()
    assert captured["env"]["MMS_GROK_API_KEY"] == "sk-openai"
    assert captured["env"]["MMS_GROK_AUTHORIZATION"] == "Bearer sk-openai"
    assert "XAI_API_KEY" not in captured["env"]
    assert captured["env"]["GROK_DISABLE_AUTOUPDATER"] == "1"
    real_auth = real_home / ".grok" / "auth.json"
    assert real_auth.read_text(encoding="utf-8") == '{"access_token":"real-session"}\n'

    payload = tomllib.loads((grok_home / "config.toml").read_text(encoding="utf-8"))
    assert payload["cli"]["use_leader"] is False
    assert payload["features"]["remote_fetch"] is False
    assert payload["models"]["default"] == "gpt-5.4"
    assert payload["models"]["allowed_models"] == ["gpt-5.4", "gpt-5.5"]
    assert "grok-4.6" not in payload["models"]["allowed_models"]
    assert payload["model"]["gpt-5.4"]["api_backend"] == "chat_completions"
    assert payload["model"]["gpt-5.4"]["base_url"] == "https://relay.example.com/v1"
    assert payload["model"]["gpt-5.4"]["env_key"] == "MMS_GROK_API_KEY"
    assert "api_key" not in payload["model"]["gpt-5.4"]


def test_launch_grok_uses_openai_for_minimax_instead_of_unsigned_messages(monkeypatch, tmp_path):
    import mms_launchers

    captured = {}
    _patch_launch_env(monkeypatch, mms_launchers, tmp_path)
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["MiniMax-M2.7"]},
    )

    def fake_exec(cmd, env, once, **_kwargs):
        captured["cmd"] = cmd
        captured["env"] = dict(env)

    monkeypatch.setattr(mms_launchers, "_exec_or_run", fake_exec)
    runtime = {
        "id": "relay-a",
        "name": "Relay A",
        "enabled": True,
        "auth_mode": "api_key",
        "api_key": "sk-test",
        "openai_base_url": "http://127.0.0.1:4003/v1",
        "anthropic_base_url": "http://127.0.0.1:4003/v1",
        "protocols": ["anthropic_messages", "openai_chat_completions"],
        "supported_clis": ["claude", "codex"],
    }
    mms_launchers.launch_grok({"model": "MiniMax-M2.7"}, runtime, once=True)

    grok_home = Path(captured["env"]["GROK_HOME"])
    payload = tomllib.loads((grok_home / "config.toml").read_text(encoding="utf-8"))
    model = payload["model"]["MiniMax-M2.7"]
    assert model["api_backend"] == "chat_completions"
    assert model["base_url"] == "http://127.0.0.1:4003/v1"
    assert "extra_headers" not in model
    assert captured["cmd"][:3] == ["grok", "-m", "MiniMax-M2.7"]


def test_launch_grok_uses_anthropic_messages_backend(monkeypatch, tmp_path):
    import mms_launchers

    captured = {}
    _patch_launch_env(monkeypatch, mms_launchers, tmp_path)
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["claude-sonnet-4-6"]},
    )

    def fake_exec(cmd, env, once, **_kwargs):
        captured["cmd"] = cmd
        captured["env"] = dict(env)

    monkeypatch.setattr(mms_launchers, "_exec_or_run", fake_exec)
    mms_launchers.launch_grok({"model": "claude-sonnet-4-6"}, _anthropic_runtime(), once=True)

    grok_home = Path(captured["env"]["GROK_HOME"])
    payload = tomllib.loads((grok_home / "config.toml").read_text(encoding="utf-8"))
    model = payload["model"]["claude-sonnet-4-6"]
    assert model["api_backend"] == "messages"
    assert model["base_url"] == "https://relay.example.com/anthropic/v1"
    assert model["env_http_headers"]["x-api-key"] == "MMS_GROK_API_KEY"
    assert model["extra_headers"]["anthropic-version"] == "2023-06-01"
    assert captured["cmd"][:3] == ["grok", "-m", "claude-sonnet-4-6"]


def test_launch_grok_rejects_oauth_runtime(monkeypatch, tmp_path):
    import mms_launchers

    _patch_launch_env(monkeypatch, mms_launchers, tmp_path)
    with pytest.raises(SystemExit):
        mms_launchers.launch_grok(
            {"model": "gpt-5.4"},
            _openai_runtime(auth_mode="oauth"),
            once=True,
        )


def test_get_export_env_for_grok_writes_isolated_home(monkeypatch, tmp_path):
    import mms_launchers

    real_home, preview_root = _patch_launch_env(monkeypatch, mms_launchers, tmp_path)
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["gpt-5.4"]},
    )
    exports = mms_launchers.get_export_env(
        "grok",
        _openai_runtime(model="gpt-5.4"),
        model_info={"model": "gpt-5.4"},
    )
    grok_home = Path(exports["GROK_HOME"])
    assert grok_home.is_relative_to(preview_root / "grok-gateway" / "exports")
    assert exports["MMS_MODEL_NAME"] == "gpt-5.4"
    assert exports["MMS_GROK_SELECTED_MODEL"] == "gpt-5.4"
    assert not (real_home / ".grok" / "home").exists()
    payload = tomllib.loads((grok_home / "config.toml").read_text(encoding="utf-8"))
    assert payload["models"]["allowed_models"] == ["gpt-5.4"]


def test_installer_offers_grok():
    import mms_installer

    assert "grok" in mms_installer.INSTALL_COMMANDS
    assert "grok" in mms_installer.CLI_DESCRIPTIONS


def test_runtime_resolver_finds_grok_bin_under_user_home(monkeypatch, tmp_path):
    import mms_runtime

    grok_bin = tmp_path / ".grok" / "bin"
    grok_bin.mkdir(parents=True)
    binary = grok_bin / "grok"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    found = mms_runtime.resolve_cli_binary("grok", env={"PATH": "/usr/bin"}, real_home=str(tmp_path))
    assert found == str(binary)
