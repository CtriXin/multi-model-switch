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
    monkeypatch.setattr(mms_launchers, "_probe_models", lambda runtime, emit_output=False: {"models": ["gpt-5.4", "gpt-5.5"]})
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
    assert provider["api"] == "openai-responses"
    assert provider["baseUrl"] == "https://relay.example.com/v1"
    assert provider["apiKey"] == "sk-openai"
    assert provider["models"][0]["id"] == "gpt-5.4"
    assert provider["models"][1]["id"] == "gpt-5.5"


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
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["claude-sonnet-4-6", "claude-opus-4-7"]},
    )

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
    assert provider["models"][1]["id"] == "claude-opus-4-7"
    assert provider["models"][0]["input"] == ["text", "image"]
    assert provider["models"][0]["reasoning"] is True
    assert provider["models"][0]["contextWindow"] == 1_000_000
    assert provider["models"][0]["maxTokens"] == 64_000
    assert provider["models"][0]["compat"] == {"forceAdaptiveThinking": True}
    assert provider["models"][1]["compat"] == {"forceAdaptiveThinking": True}


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
    monkeypatch.setattr(mms_launchers, "_probe_models", lambda runtime, emit_output=False: {"models": ["gpt-5.4", "gpt-5.5"]})

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
    assert provider["api"] == "openai-responses"
    assert provider["models"][0]["id"] == "gpt-5.4"
    assert provider["models"][1]["id"] == "gpt-5.5"


def test_pi_dual_protocol_payload_splits_models_by_preferred_protocol(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["qwen3.6-plus", "gpt-5.4"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "newapi-personal-tokyo",
            "name": "NewAPI Tokyo",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-relay",
            "openai_base_url": "https://relay.example.com/v1",
            "anthropic_base_url": "https://relay.example.com/anthropic",
            "protocols": ["anthropic_messages", "openai_chat_completions"],
            "supported_clis": ["claude", "codex", "pi"],
        },
        model_info={"model": "qwen3.6-plus"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    assert set(payload["providers"]) == {
        "mms-newapi-personal-tokyo-anthropic",
        "mms-newapi-personal-tokyo-responses",
    }
    assert exports["MMS_PI_PROVIDER"] == "mms-newapi-personal-tokyo-anthropic"
    anthropic_models = payload["providers"]["mms-newapi-personal-tokyo-anthropic"]["models"]
    openai_models = payload["providers"]["mms-newapi-personal-tokyo-responses"]["models"]
    assert [item["id"] for item in anthropic_models] == ["qwen3.6-plus"]
    assert [item["id"] for item in openai_models] == ["gpt-5.4"]
    assert anthropic_models[0]["reasoning"] is True
    assert anthropic_models[0]["contextWindow"] == 1_000_000
    assert anthropic_models[0]["maxTokens"] == 65_536
    assert openai_models[0]["input"] == ["text", "image"]
    assert openai_models[0]["maxTokens"] == 128_000


def test_pi_openai_provider_compat_uses_profile_specific_flags(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["deepseek-v4-pro"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "deepseek-direct",
            "name": "DeepSeek Direct",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-deepseek",
            "openai_base_url": "https://api.deepseek.com",
            "protocols": ["openai_chat_completions"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "deepseek-v4-pro"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    provider = payload["providers"]["mms-deepseek-direct"]
    assert provider["compat"] == {
        "requiresReasoningContentOnAssistantMessages": True,
        "thinkingFormat": "deepseek",
    }
    assert provider["models"][0]["maxTokens"] == 384_000
    assert provider["models"][0]["thinkingLevelMap"] == {
        "minimal": None,
        "low": None,
        "medium": None,
        "high": "high",
        "xhigh": "max",
    }


def test_pi_kimi_family_uses_builtin_max_token_hint(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["kimi-for-coding"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "kimi-direct",
            "name": "Kimi Direct",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-kimi",
            "openai_base_url": "https://api.kimi.com/coding/v1",
            "anthropic_base_url": "https://api.kimi.com/coding",
            "protocols": ["anthropic_messages", "openai_chat_completions"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "kimi-for-coding"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    provider = payload["providers"][exports["MMS_PI_PROVIDER"]]
    assert provider["models"][0]["id"] == "kimi-for-coding"
    assert provider["models"][0]["input"] == ["text", "image"]
    assert provider["models"][0]["contextWindow"] == 262_144
    assert provider["models"][0]["maxTokens"] == 32_768


def test_pi_normalizes_anthropic_base_url_before_export(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["claude-sonnet-4-6"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "relay-anthropic-v1",
            "name": "Relay Anthropic V1",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-anthropic",
            "anthropic_base_url": "https://relay.example.com/v1",
            "protocols": ["anthropic_messages"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "claude-sonnet-4-6"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    provider = payload["providers"][exports["MMS_PI_PROVIDER"]]
    assert provider["api"] == "anthropic-messages"
    assert provider["baseUrl"] == "https://relay.example.com"


def test_pi_skips_image_generation_only_models(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["gpt-image-2", "gpt-5.4"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "codex-relay",
            "name": "Codex Relay",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-openai",
            "openai_base_url": "https://relay.example.com/v1",
            "protocols": ["openai_chat_completions"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "gpt-5.4"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    provider = payload["providers"][exports["MMS_PI_PROVIDER"]]
    assert [item["id"] for item in provider["models"]] == ["gpt-5.4"]


def test_pi_rejects_selected_image_generation_only_model(monkeypatch):
    import mms_launchers
    import pytest

    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["gpt-image-2"]},
    )

    with pytest.raises(RuntimeError, match="image-generation-only model"):
        mms_launchers._pi_build_models_payload(
            {
                "id": "codex-relay",
                "name": "Codex Relay",
                "enabled": True,
                "auth_mode": "api_key",
                "api_key": "sk-openai",
                "openai_base_url": "https://relay.example.com/v1",
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["pi"],
            },
            "gpt-image-2",
        )


def test_pi_builtin_hints_cover_new_qwen_flash_and_max_models(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["qwen3.6-flash", "qwen3.7-max"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "qwen-relay",
            "name": "Qwen Relay",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-qwen",
            "openai_base_url": "https://relay.example.com/v1",
            "anthropic_base_url": "https://relay.example.com/anthropic",
            "protocols": ["anthropic_messages", "openai_chat_completions"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "qwen3.6-flash"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    models = []
    for provider in payload["providers"].values():
        models.extend(provider["models"])
    model_by_id = {item["id"]: item for item in models}

    assert model_by_id["qwen3.6-flash"]["contextWindow"] == 1_000_000
    assert model_by_id["qwen3.6-flash"]["maxTokens"] == 65_536
    assert model_by_id["qwen3.6-flash"]["input"] == ["text", "image"]
    assert model_by_id["qwen3.7-max"]["contextWindow"] == 1_000_000
    assert model_by_id["qwen3.7-max"]["maxTokens"] == 65_536
    assert model_by_id["qwen3.7-max"]["input"] == ["text"]


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
