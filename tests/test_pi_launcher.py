import json
from pathlib import Path


def test_core_pi_cli_is_visible_and_provider_compat_is_implied():
    import mms_core

    provider = {
        "id": "relay-a",
        "name": "Relay A",
        "enabled": True,
        "api_key": "sk-test",
        "openai_base_url": "https://relay.example.com/v1",
        "anthropic_base_url": "https://relay.example.com/anthropic",
        "protocols": ["anthropic_messages", "openai_chat_completions"],
        "supported_clis": ["claude", "codex"],
    }

    assert "pi" in mms_core.CLI_NAMES
    assert mms_core._provider_supports_cli_name(provider, "pi") is True


def test_runtime_resolver_uses_repo_pi_wrapper(monkeypatch, tmp_path):
    import mms_runtime

    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    wrapper = scripts_dir / "pi-cli-wrapper.sh"
    wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    wrapper.chmod(0o755)
    monkeypatch.setattr(mms_runtime, "__file__", str(tmp_path / "mms_runtime.py"))

    resolved = mms_runtime.resolve_cli_binary("pi", env={"PATH": "/usr/bin"})

    assert resolved == str(wrapper)


def test_launch_pi_writes_openai_models_config_and_uses_wrapper(monkeypatch, tmp_path):
    import mms_launchers

    captured = {}
    real_home = tmp_path / "real-home"
    real_home.mkdir()

    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
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
    monkeypatch.setattr(mms_launchers, "_resolve_xmem_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(mms_launchers.os, "getpid", lambda: 4242)

    def fake_exec(cmd, env, once, **_kwargs):
        captured["cmd"] = cmd
        captured["env"] = dict(env)
        captured["once"] = once

    monkeypatch.setattr(mms_launchers, "_exec_or_run", fake_exec)

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

    mms_launchers.launch_pi({"model": "gpt-5.4"}, runtime, once=True)

    assert captured["cmd"] == ["pi", "--provider", "mms-relay-a", "--model", "gpt-5.4", "--thinking", "off"]
    assert captured["once"] is True
    assert captured["env"]["MMS_PI_BIN"] == "/tmp/pi-wrapper"

    models_path = real_home / ".config" / "mms" / "pi-gateway" / "s" / "4242" / ".pi" / "agent" / "models.json"
    payload = json.loads(models_path.read_text(encoding="utf-8"))
    provider = payload["providers"]["mms-relay-a"]
    assert provider["api"] == "openai-completions"
    assert provider["baseUrl"] == "https://relay.example.com/v1"
    assert provider["apiKey"] == "sk-openai"
    assert provider["models"][0]["id"] == "gpt-5.4"


def test_get_export_env_for_pi_writes_anthropic_models_config(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "relay-b",
            "name": "Relay B",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-anthropic",
            "anthropic_base_url": "https://relay.example.com/anthropic",
            "protocols": ["anthropic_messages"],
            "supported_clis": ["claude"],
            "model": "claude-sonnet-4-6",
        },
    )

    assert exports["MMS_PI_BIN"] == "/tmp/pi-wrapper"
    models_path = real_home / ".config" / "mms" / "pi-gateway" / "exports" / "relay-b-claude-sonnet-4-6" / "agent" / "models.json"
    payload = json.loads(models_path.read_text(encoding="utf-8"))
    provider = payload["providers"]["mms-relay-b"]
    assert provider["api"] == "anthropic-messages"
    assert provider["baseUrl"] == "https://relay.example.com/anthropic"
    assert provider["models"][0]["id"] == "claude-sonnet-4-6"


def test_get_export_env_for_pi_accepts_model_info_when_runtime_has_no_model(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "relay-c",
            "name": "Relay C",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-openai",
            "openai_base_url": "https://relay.example.com/v1",
            "protocols": ["openai_chat_completions"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "gpt-5.4"},
    )

    assert exports["MMS_PI_BIN"] == "/tmp/pi-wrapper"
    models_path = Path(exports["MMS_PI_MODELS_JSON"])
    payload = json.loads(models_path.read_text(encoding="utf-8"))
    provider = payload["providers"]["mms-relay-c"]
    assert provider["api"] == "openai-completions"
    assert provider["models"][0]["id"] == "gpt-5.4"


def test_preset_export_runtime_passes_pi_model_info(monkeypatch):
    import mms_core
    import mms_launchers

    runtime = {
        "id": "relay-c",
        "name": "Relay C",
        "enabled": True,
        "auth_mode": "api_key",
        "api_key": "sk-openai",
        "openai_base_url": "https://relay.example.com/v1",
        "protocols": ["openai_chat_completions"],
        "supported_clis": ["pi"],
    }
    captured = {}

    monkeypatch.setattr(mms_core, "ensure_provider_credentials", lambda cfg, provider_id=None: dict(runtime))
    monkeypatch.setattr(mms_launchers, "validate_provider_for_cli", lambda cli, runtime: None)

    def fake_get_export_env(cli, runtime, model_info=None):
        captured["cli"] = cli
        captured["runtime"] = dict(runtime)
        captured["model_info"] = dict(model_info or {})
        return {"PI_TELEMETRY": "0"}

    monkeypatch.setattr(mms_launchers, "get_export_env", fake_get_export_env)

    result = mms_core._resolve_preset_export_runtime(
        {"providers": [runtime]},
        {"cli": "pi", "model": "gpt-5.4", "provider": "relay-c"},
    )

    assert result is not None
    assert captured["cli"] == "pi"
    assert captured["runtime"]["id"] == "relay-c"
    assert captured["model_info"] == {"model": "gpt-5.4"}
