from __future__ import annotations

import json
from pathlib import Path


def _runtime(**overrides):
    runtime = {
        "id": "deepseek",
        "name": "DeepSeek",
        "api_key": "sk-runtime",
        "openai_base_url": "https://api.deepseek.com/v1",
        "protocols": ["openai_chat_completions"],
        "supported_clis": ["opencode"],
    }
    runtime.update(overrides)
    return runtime


def test_opencode_config_uses_openai_compatible_provider():
    import mms_launchers

    payload = json.loads(
        mms_launchers._build_opencode_config_content(
            _runtime(models=["deepseek-chat"]),
            "deepseek-reasoner",
        )
    )

    assert payload["model"] == "mms/deepseek-reasoner"
    assert payload["small_model"] == "mms/deepseek-reasoner"
    assert payload["autoupdate"] is False
    assert payload["share"] == "disabled"
    assert payload["permission"] == {"edit": "ask", "bash": "ask"}

    provider = payload["provider"]["mms"]
    assert provider["npm"] == "@ai-sdk/openai-compatible"
    assert provider["name"] == "DeepSeek"
    assert provider["options"] == {
        "baseURL": "https://api.deepseek.com/v1",
        "apiKey": "{env:MMS_OPENCODE_API_KEY}",
    }
    assert sorted(provider["models"]) == ["deepseek-chat", "deepseek-reasoner"]
    reasoner = provider["models"]["deepseek-reasoner"]
    if "limit" in reasoner:
        assert isinstance(reasoner["limit"]["context"], int)
        assert reasoner["limit"]["output"] == mms_launchers.OPENCODE_DEFAULT_OUTPUT_LIMIT


def test_opencode_model_limit_includes_required_output_value():
    import mms_launchers

    config = mms_launchers._opencode_model_config(
        _runtime(opencode_output_limit=16384),
        "gpt-5.5",
    )

    assert isinstance(config["limit"]["context"], int)
    assert config["limit"]["context"] > 0
    assert config["limit"]["output"] == 16384


def test_opencode_gateway_env_writes_session_local_config(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(mms_launchers, "_real_user_home", lambda: str(real_home))
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        mms_launchers,
        "_install_session_packet_env",
        lambda env, **_kwargs: env.update({"MMS_SESSION_PACKET": "packet.json"}),
    )
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, *_args, **_kwargs: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_locale_profile", lambda env, *_args, **_kwargs: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_ip_stack_profile", lambda env, *_args, **_kwargs: env)

    env = mms_launchers._opencode_gateway_env(
        _runtime(),
        model_info={"model": "deepseek-chat"},
    )

    session_home = Path(env["HOME"])
    config_path = Path(env["OPENCODE_CONFIG"])
    assert session_home.is_dir()
    assert config_path == session_home / ".config" / "opencode" / "opencode.json"
    assert json.loads(config_path.read_text(encoding="utf-8")) == json.loads(env["OPENCODE_CONFIG_CONTENT"])
    assert env["XDG_CONFIG_HOME"] == str(session_home / ".config")
    assert env["MMS_SESSION_HOME"] == str(session_home)
    assert env["MMS_OPENCODE_API_KEY"] == "sk-runtime"
    assert env["OPENAI_BASE_URL"] == "https://api.deepseek.com/v1"
    assert env["OPENCODE_CLIENT"] == "mms"


def test_launch_opencode_passes_model_ref_and_session_env(monkeypatch):
    import mms_launchers

    captured = {}
    monkeypatch.setattr(mms_launchers, "gateway_health_check", lambda _runtime: None)
    monkeypatch.setattr(
        mms_launchers,
        "_opencode_gateway_env",
        lambda runtime, model_info=None: {"PATH": "/tmp/bin", "HOME": "/tmp/opencode-session"},
    )

    def fake_exec(cmd, env, once, **_kwargs):
        captured["cmd"] = cmd
        captured["env"] = env
        captured["once"] = once

    monkeypatch.setattr(mms_launchers, "_exec_or_run", fake_exec)

    mms_launchers.launch_opencode(
        {"model": "deepseek-chat"},
        _runtime(),
        once=True,
    )

    assert captured["cmd"] == ["opencode", "-m", "mms/deepseek-chat"]
    assert captured["env"]["HOME"] == "/tmp/opencode-session"
    assert captured["once"] is True


def test_get_export_env_exposes_opencode_inline_config():
    import mms_launchers

    runtime = _runtime(model="deepseek-chat")

    exports = mms_launchers.get_export_env("opencode", runtime)
    payload = json.loads(exports["OPENCODE_CONFIG_CONTENT"])

    assert exports["MMS_OPENCODE_API_KEY"] == "sk-runtime"
    assert exports["OPENAI_API_KEY"] == "sk-runtime"
    assert exports["OPENAI_BASE_URL"] == "https://api.deepseek.com/v1"
    assert payload["model"] == "mms/deepseek-chat"
    assert payload["provider"]["mms"]["options"]["apiKey"] == "{env:MMS_OPENCODE_API_KEY}"


def test_core_provider_supports_opencode_cli():
    import mms_core

    provider = _runtime()

    assert "opencode" in mms_core.CLI_NAMES
    assert mms_core._provider_supports_cli_name(provider, "opencode") is True
    assert mms_core._provider_supports_model_for_cli(provider, "opencode", "deepseek-chat") is True


def test_existing_openai_provider_lists_show_opencode_without_config_migration(monkeypatch):
    import mms_core

    provider = _runtime(
        supported_clis=["claude", "codex"],
        models=["deepseek-chat"],
    )
    cfg = {
        "providers": [],
        "account": {"defaults": {}},
        "accounts": [],
    }

    monkeypatch.setattr(mms_core, "_provider_effective_models", lambda _provider, cached, _cfg=None: list(cached or []))

    assert mms_core._provider_supports_cli_name(provider, "opencode") is True
    assert mms_core._provider_supports_model_for_cli(provider, "opencode", "deepseek-chat") is True
    assert "opencode" in mms_core._resolve_visible_clis(cfg, provider, ["deepseek-chat"])


def test_launchers_validate_existing_openai_provider_for_opencode():
    import mms_launchers

    provider = _runtime(
        supported_clis=["claude", "codex"],
        models=["deepseek-chat"],
    )

    assert mms_launchers._provider_supports_cli(provider, "opencode") is True
    mms_launchers.validate_provider_for_cli("opencode", provider)
