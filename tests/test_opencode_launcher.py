from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
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
    assert payload["default_agent"] == "mobius-builder"
    assert payload["autoupdate"] is False
    assert payload["share"] == "disabled"
    assert payload["permission"] == {"edit": "ask", "bash": "ask"}
    assert sorted(payload["agent"]) == [
        "mobius-builder",
        "mobius-explore",
        "mobius-fixer",
        "mobius-reviewer",
    ]
    assert payload["agent"]["mobius-builder"]["mode"] == "primary"
    assert payload["agent"]["mobius-explore"]["permission"]["edit"] == "deny"
    assert payload["agent"]["mobius-reviewer"]["permission"]["edit"] == "deny"
    assert payload["agent"]["mobius-fixer"]["permission"]["edit"] == "ask"

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


def test_opencode_config_can_disable_lite_agents_for_raw_profile():
    import mms_launchers

    payload = json.loads(
        mms_launchers._build_opencode_config_content(
            _runtime(models=["deepseek-chat"], opencode_lite_agents=False),
            "deepseek-chat",
        )
    )

    assert "agent" not in payload
    assert "default_agent" not in payload


def test_opencode_model_limit_includes_required_output_value():
    import mms_launchers

    config = mms_launchers._opencode_model_config(
        _runtime(opencode_output_limit=16384),
        "gpt-5.5",
    )

    assert isinstance(config["limit"]["context"], int)
    assert config["limit"]["context"] > 0
    assert config["limit"]["output"] == 16384


def test_opencode_model_config_marks_official_vision_models_only():
    import mms_launchers

    for model in ("mimo-v2.5", "K2.6", "kimi-k2.5", "qwen3.5-plus", "qwen3.6-plus", "gpt-5.3-codex"):
        config = mms_launchers._opencode_model_config(_runtime(), model)
        assert config["attachment"] is True
        assert config["modalities"] == {"input": ["text", "image"], "output": ["text"]}

    for model in ("mimo-v2.5-pro", "qwen3-coder-plus", "glm-5.1", "deepseek-v4-pro", "MiniMax-M2.7"):
        config = mms_launchers._opencode_model_config(_runtime(), model)
        assert "attachment" not in config
        assert "modalities" not in config


def test_opencode_provider_base_url_adds_v1_after_gateway_openai_prefix():
    import mms_launchers

    runtime = _runtime(openai_base_url="http://129.146.32.12:3000/openai")

    assert mms_launchers._opencode_provider_base_url(runtime) == "http://129.146.32.12:3000/openai/v1"


def test_opencode_provider_base_url_adds_v1_after_gateway_root():
    import mms_launchers

    runtime = _runtime(openai_base_url="http://161.33.197.51:4001")

    assert mms_launchers._opencode_provider_base_url(runtime) == "http://161.33.197.51:4001/v1"


def test_opencode_provider_base_url_preserves_existing_v1_and_explicit_override():
    import mms_launchers

    assert (
        mms_launchers._opencode_provider_base_url(
            _runtime(openai_base_url="http://129.146.32.12:3000/openai/v1/")
        )
        == "http://129.146.32.12:3000/openai/v1"
    )
    assert (
        mms_launchers._opencode_provider_base_url(
            _runtime(
                openai_base_url="http://129.146.32.12:3000/openai",
                opencode_base_url="https://custom.example/openai",
            )
        )
        == "https://custom.example/openai"
    )


def test_opencode_config_and_exports_use_normalized_gateway_openai_url(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(mms_launchers, "_real_user_home", lambda: str(real_home))
    runtime = _runtime(
        model="gpt-5.5",
        models=["gpt-5.5"],
        openai_base_url="http://129.146.32.12:3000/openai",
    )

    payload = json.loads(mms_launchers._build_opencode_config_content(runtime, "gpt-5.5"))
    exports = mms_launchers.get_export_env("opencode", runtime)

    assert payload["provider"]["mms"]["options"]["baseURL"] == "http://129.146.32.12:3000/openai/v1"
    assert exports["OPENAI_BASE_URL"] == "http://129.146.32.12:3000/openai/v1"
    assert json.loads(Path(exports["OPENCODE_CONFIG"]).read_text(encoding="utf-8"))["provider"]["mms"]["options"]["baseURL"] == "http://129.146.32.12:3000/openai/v1"


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
    config_payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert config_payload["provider"]["mms"]["options"]["apiKey"] == "{env:MMS_OPENCODE_API_KEY}"
    assert env["XDG_CONFIG_HOME"] == str(session_home / ".config")
    assert env["MMS_SESSION_HOME"] == str(session_home)
    assert env["MMS_OPENCODE_API_KEY"] == "sk-runtime"
    assert env["OPENAI_BASE_URL"] == "https://api.deepseek.com/v1"
    assert env["OPENCODE_CLIENT"] == "mms"
    assert "OPENCODE_CONFIG_CONTENT" not in env


def test_launch_opencode_passes_model_ref_and_session_env(monkeypatch):
    import mms_launchers

    captured = {}

    def fake_health_check(runtime):
        captured["health_base_url"] = runtime["openai_base_url"]

    monkeypatch.setattr(mms_launchers, "gateway_health_check", fake_health_check)
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
        _runtime(openai_base_url="http://129.146.32.12:3000/openai"),
        once=True,
    )

    assert captured["cmd"] == ["opencode", "--pure", "--agent", "mobius-builder", "-m", "mms/deepseek-chat"]
    assert captured["env"]["HOME"] == "/tmp/opencode-session"
    assert captured["once"] is True
    assert captured["health_base_url"] == "http://129.146.32.12:3000/openai/v1"


def test_launch_opencode_heavy_omo_uses_global_opencode_config(monkeypatch):
    import mms_launchers

    captured = {}

    monkeypatch.setattr(
        mms_launchers,
        "_opencode_gateway_health_check",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("session config should not be used")),
    )
    monkeypatch.setattr(
        mms_launchers,
        "_opencode_gateway_env",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("session env should not be used")),
    )
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, *_args, **_kwargs: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_locale_profile", lambda env, *_args, **_kwargs: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_ip_stack_profile", lambda env, *_args, **_kwargs: env)

    def fake_exec(cmd, env, once, **_kwargs):
        captured["cmd"] = cmd
        captured["env"] = env
        captured["once"] = once

    monkeypatch.setattr(mms_launchers, "_exec_or_run", fake_exec)

    mms_launchers.launch_opencode(
        {"model": "deepseek-chat"},
        _runtime(opencode_profile="heavy_omo", opencode_use_global_config=True),
        once=True,
    )

    assert captured["cmd"] == ["opencode"]
    assert captured["env"]["OPENCODE_CLIENT"] == "mms"
    assert captured["env"]["MMS_OPENCODE_PROFILE"] == "heavy_omo"
    assert captured["once"] is True


def test_get_export_env_exposes_opencode_file_config(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(mms_launchers, "_real_user_home", lambda: str(real_home))
    runtime = _runtime(model="deepseek-chat")

    exports = mms_launchers.get_export_env("opencode", runtime)
    payload = json.loads(Path(exports["OPENCODE_CONFIG"]).read_text(encoding="utf-8"))

    assert exports["MMS_OPENCODE_API_KEY"] == "sk-runtime"
    assert exports["OPENAI_API_KEY"] == "sk-runtime"
    assert exports["OPENAI_BASE_URL"] == "https://api.deepseek.com/v1"
    assert exports["OPENCODE_CONFIG_DIR"] == str(Path(exports["OPENCODE_CONFIG"]).parent)
    assert "OPENCODE_CONFIG_CONTENT" not in exports
    assert payload["model"] == "mms/deepseek-chat"
    assert payload["provider"]["mms"]["options"]["apiKey"] == "{env:MMS_OPENCODE_API_KEY}"


def test_get_export_env_for_heavy_omo_does_not_write_session_config(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(mms_launchers, "_real_user_home", lambda: str(real_home))
    runtime = _runtime(model="deepseek-chat", opencode_profile="heavy_omo", opencode_use_global_config=True)

    exports = mms_launchers.get_export_env("opencode", runtime)

    assert exports == {
        "OPENCODE_CLIENT": "mms",
        "MMS_OPENCODE_PROFILE": "heavy_omo",
    }
    assert not (real_home / ".config" / "mms" / "opencode-gateway").exists()


def test_get_export_env_for_heavy_omo_does_not_require_provider_credentials():
    import mms_launchers

    exports = mms_launchers.get_export_env(
        "opencode",
        {"opencode_profile": "heavy_omo", "opencode_use_global_config": True},
    )

    assert exports == {
        "OPENCODE_CLIENT": "mms",
        "MMS_OPENCODE_PROFILE": "heavy_omo",
    }


def test_core_provider_supports_opencode_cli():
    import mms_core

    provider = _runtime()
    anthropic_provider = _runtime(
        supported_clis=["claude"],
        protocols=["anthropic_messages"],
        openai_base_url="",
        base_url="https://anthropic.example/v1",
    )

    assert "opencode" in mms_core.CLI_NAMES
    assert mms_core._provider_supports_cli_name(provider, "opencode") is True
    assert mms_core._provider_supports_model_for_cli(provider, "opencode", "deepseek-chat") is True
    assert mms_core._provider_supports_cli_name(anthropic_provider, "opencode") is True


def test_core_opencode_profiles_are_fixed_launch_shapes():
    import mms_core

    lite = mms_core._apply_opencode_profile(_runtime(), "lite")
    lite_pro = mms_core._apply_opencode_profile(_runtime(), "lite_pro")
    heavy = mms_core._apply_opencode_profile(_runtime(), "heavy_omo")
    raw = mms_core._apply_opencode_profile(_runtime(), "raw")

    assert lite["opencode_pure"] is True
    assert lite["opencode_agent"] == "mobius-builder"
    assert lite["opencode_lite_agents"] is True
    assert lite_pro["opencode_agent"] == "mobius-builder-pro"
    assert lite_pro["opencode_launch_preflight"] is True
    assert lite_pro["opencode_launch_fallback_route_keys"] == ["builder_primary", "builder_fallback"]
    orchestrated = mms_core._apply_opencode_profile(_runtime(), "lite_pro_orchestrated")
    assert orchestrated["opencode_agent"] == "mobius-builder-pro"
    assert orchestrated["opencode_roster"] == "lite_pro_orchestrated"
    assert heavy["opencode_use_global_config"] is True
    assert heavy["opencode_lite_agents"] is False
    assert raw["opencode_pure"] is True
    assert raw["opencode_agent"] == ""
    assert raw["opencode_lite_agents"] is False


def test_core_opencode_profile_runtime_uses_fixed_safe_gpt_not_kimi():
    import mms_core

    cfg = {"providers": [], "account": {"defaults": {}}, "accounts": []}
    provider = _runtime(
        id="dual-protocol",
        name="Dual Protocol",
        supported_clis=["codex"],
        protocols=["anthropic_messages", "openai_chat_completions"],
    )

    model_info, runtime = mms_core._resolve_opencode_profile_runtime(
        cfg,
        provider,
        ["K2.6", "gpt-5.4"],
        "lite",
    )

    assert model_info == {"model": "gpt-5.4"}
    assert runtime["id"] == "dual-protocol"
    assert runtime["model"] == "gpt-5.4"
    assert runtime["opencode_profile"] == "lite"
    assert runtime["opencode_agent"] == "mobius-builder"


def test_core_opencode_heavy_profile_uses_global_runtime_without_model_provider():
    import mms_core

    model_info, runtime = mms_core._resolve_opencode_profile_runtime(
        {"providers": []},
        {},
        [],
        "heavy_omo",
    )

    assert model_info == {"model": "global-omo"}
    assert runtime["runtime_kind"] == "opencode_profile"
    assert runtime["opencode_use_global_config"] is True


def test_core_opencode_lite_pro_builds_multi_model_roster(monkeypatch):
    import mms_core
    import mms_launchers

    cfg = {"providers": [], "account": {"defaults": {}}, "accounts": []}
    provider = _runtime(
        id="mixed",
        name="Mixed",
        supported_clis=["codex"],
        protocols=["anthropic_messages", "openai_chat_completions"],
    )
    mimo_direct = _runtime(
        id="mimo-direct-anthropic",
        name="MiMo Direct",
        supported_clis=["opencode"],
        protocols=["anthropic_messages"],
        openai_base_url="",
        anthropic_base_url="https://token-plan-cn.xiaomimimo.com/anthropic",
    )
    models = [
        "gpt-5.5",
        "gpt-5.4",
        "glm-5-turbo",
        "kimi-for-coding",
        "mimo-v2.5-pro",
        "deepseek-v4-pro",
        "glm-5.1",
    ]
    monkeypatch.setattr(
        mms_core,
        "_provider_candidates",
        lambda *_args: [(provider, models), (mimo_direct, ["mimo-v2.5-pro"])],
    )

    model_info, runtime = mms_core._resolve_opencode_profile_runtime(
        cfg,
        provider,
        models,
        "lite_pro",
    )
    payload = mms_launchers._build_opencode_config_payload(runtime, model_info["model"])

    assert model_info == {"model": "gpt-5.5", "profile": "lite_pro"}
    assert runtime["opencode_agent"] == "mobius-builder-pro"
    assert runtime["opencode_launch_preflight"] is True
    assert runtime["opencode_launch_fallback_agents"]["builder_fallback"] == "mobius-builder-stable"
    assert payload["model"].endswith("/gpt-5.5")
    assert payload["default_agent"] == "mobius-builder-pro"
    assert payload["agent"]["mobius-builder-pro"]["model"].endswith("/gpt-5.5")
    assert payload["agent"]["mobius-builder-stable"]["mode"] == "primary"
    assert payload["agent"]["mobius-builder-stable"]["model"].endswith("/gpt-5.4")
    assert payload["agent"]["mobius-explore-glm"]["model"].endswith("/glm-5-turbo")
    assert payload["agent"]["mobius-explore-kimi"]["model"].endswith("/kimi-for-coding")
    assert payload["agent"]["mobius-reviewer-mimo"]["model"].endswith("/mimo-v2.5-pro")
    reviewer_route = next(route for route in runtime["opencode_routes"] if route["id"] == "reviewer_primary")
    assert reviewer_route["provider_id"] == "mimo-direct-anthropic"
    assert reviewer_route["anthropic_base_url"] == "https://token-plan-cn.xiaomimimo.com/anthropic/v1"
    assert payload["agent"]["mobius-reviewer-deepseek"]["model"].endswith("/deepseek-v4-pro")
    assert payload["agent"]["mobius-fixer-deepseek"]["model"].endswith("/deepseek-v4-pro")
    assert payload["agent"]["mobius-fixer-glm"]["model"].endswith("/glm-5.1")
    assert payload["agent"]["mobius-fixer-gpt54"]["model"].endswith("/gpt-5.4")
    assert len(payload["provider"]) >= 7
    assert payload["provider"]["mms-explore_primary"]["npm"] == "@ai-sdk/anthropic"
    assert payload["provider"]["mms-reviewer_fallback"]["npm"] == "@ai-sdk/anthropic"
    assert payload["provider"]["mms-builder_primary"]["npm"] == "@ai-sdk/openai-compatible"


def test_core_opencode_lite_pro_orchestrated_delegates_to_executor_chain(monkeypatch):
    import mms_core
    import mms_launchers

    cfg = {"providers": [], "account": {"defaults": {}}, "accounts": []}
    provider = _runtime(
        id="mixed",
        name="Mixed",
        supported_clis=["codex"],
        protocols=["anthropic_messages", "openai_chat_completions"],
    )
    mimo_direct = _runtime(
        id="mimo-direct-anthropic",
        name="MiMo Direct",
        supported_clis=["opencode"],
        protocols=["anthropic_messages"],
        openai_base_url="",
        anthropic_base_url="https://token-plan-cn.xiaomimimo.com/anthropic",
    )
    models = [
        "gpt-5.5",
        "gpt-5.4",
        "glm-5-turbo",
        "glm-5.1",
        "kimi-for-coding",
        "deepseek-v4-pro",
        "qwen3.6-plus",
    ]
    monkeypatch.setattr(
        mms_core,
        "_provider_candidates",
        lambda *_args: [(provider, models), (mimo_direct, ["mimo-v2.5-pro"])],
    )

    model_info, runtime = mms_core._resolve_opencode_profile_runtime(
        cfg,
        provider,
        models,
        "lite_pro_orchestrated",
    )
    payload = mms_launchers._build_opencode_config_payload(runtime, model_info["model"])

    assert model_info == {"model": "gpt-5.5", "profile": "lite_pro_orchestrated"}
    assert runtime["opencode_roster"] == "lite_pro_orchestrated"
    builder = payload["agent"]["mobius-builder-pro"]
    assert builder["permission"]["edit"] == "deny"
    assert builder["permission"]["task"]["mobius-executor-deepseek"] == "allow"
    assert "Do not edit files directly" in builder["prompt"]
    assert payload["agent"]["mobius-builder-stable"]["permission"]["edit"] == "deny"
    assert payload["agent"]["mobius-executor-deepseek"]["model"].endswith("/deepseek-v4-pro")
    assert payload["agent"]["mobius-executor-glm"]["model"].endswith("/glm-5.1")
    assert payload["agent"]["mobius-executor-qwen"]["model"].endswith("/qwen3.6-plus")
    assert payload["agent"]["mobius-executor-gpt54"]["model"].endswith("/gpt-5.4")
    assert payload["agent"]["mobius-explore-qwen"]["model"].endswith("/qwen3.6-plus")
    qwen_route = next(route for route in runtime["opencode_routes"] if route["id"] == "executor_qwen")
    assert qwen_route["protocol"] == "anthropic_messages"


def test_core_opencode_lite_pro_falls_back_to_gpt_when_non_gpt_anthropic_unavailable(monkeypatch):
    import mms_core
    import mms_launchers

    cfg = {"providers": [], "account": {"defaults": {}}, "accounts": []}
    safe_provider = _runtime(
        id="safe-openai",
        name="Safe OpenAI",
        supported_clis=["codex"],
        protocols=["openai_chat_completions"],
    )

    model_info, runtime = mms_core._resolve_opencode_profile_runtime(
        cfg,
        safe_provider,
        [
            "gpt-5.5",
            "gpt-5.4",
            "mimo-v2.5-pro",
            "glm-5-turbo",
            "kimi-for-coding",
            "deepseek-v4-pro",
            "glm-5.1",
        ],
        "lite_pro",
    )
    payload = mms_launchers._build_opencode_config_payload(runtime, model_info["model"])

    assert payload["agent"]["mobius-builder-pro"]["model"].endswith("/gpt-5.5")
    assert payload["agent"]["mobius-explore-glm"]["model"].endswith("/gpt-5.4")
    assert payload["agent"]["mobius-explore-kimi"]["model"].endswith("/gpt-5.4")
    assert payload["agent"]["mobius-reviewer-deepseek"]["model"].endswith("/gpt-5.4")
    assert payload["agent"]["mobius-fixer-deepseek"]["model"].endswith("/gpt-5.4")
    assert payload["agent"]["mobius-fixer-glm"]["model"].endswith("/gpt-5.4")
    non_gpt_chat_routes = [
        route for route in runtime["opencode_routes"]
        if route["protocol"] == "openai_chat_completions" and not route["model"].startswith("gpt-")
    ]
    assert non_gpt_chat_routes == []


def test_core_opencode_lite_pro_rejects_gpt_anthropic_routes(monkeypatch):
    import mms_core

    cfg = {"providers": [], "account": {"defaults": {}}, "accounts": []}
    anthropic_only = _runtime(
        id="gpt-anthropic",
        name="GPT Anthropic",
        supported_clis=["opencode"],
        protocols=["anthropic_messages"],
        openai_base_url="",
        anthropic_base_url="https://anthropic-gpt.example/v1",
        models=["gpt-5.5"],
    )
    openai_provider = _runtime(
        id="gpt-openai",
        name="GPT OpenAI",
        supported_clis=["opencode"],
        protocols=["openai_chat_completions"],
        openai_base_url="https://openai-gpt.example/v1",
        models=["gpt-5.4"],
    )
    monkeypatch.setattr(
        mms_core,
        "_provider_candidates",
        lambda *_args: [(anthropic_only, ["gpt-5.5"]), (openai_provider, ["gpt-5.4"])],
    )

    route = mms_core._find_opencode_model_route(
        cfg,
        anthropic_only,
        ["gpt-5.5", "gpt-5.4"],
        ("gpt-5.5", "gpt-5.4"),
        route_key="builder_primary",
    )

    assert route["model"] == "gpt-5.4"
    assert route["provider_id"] == "gpt-openai"
    assert route["protocol"] == "openai_chat_completions"


def test_launch_opencode_lite_pro_uses_profile_default_model_ref(monkeypatch):
    import mms_launchers

    runtime = _runtime(
        opencode_profile="lite_pro",
        opencode_agent="mobius-builder-pro",
        opencode_roster="lite_pro",
        opencode_default_route_key="builder_primary",
        opencode_routes=[
            {
                "id": "builder_primary",
                "model": "gpt-5.5",
                "provider_id": "gpt",
                "provider_name": "GPT",
                "openai_base_url": "https://gpt.example/v1",
                "api_key": "sk-gpt",
            },
            {
                "id": "builder_fallback",
                "model": "gpt-5.4",
                "provider_id": "gpt",
                "provider_name": "GPT",
                "openai_base_url": "https://gpt.example/v1",
                "api_key": "sk-gpt",
            },
        ],
    )
    captured = {}
    monkeypatch.setattr(mms_launchers, "_opencode_gateway_health_check", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_launchers, "_opencode_gateway_env", lambda *_args, **_kwargs: {"HOME": "/tmp/opencode"})
    monkeypatch.setattr(
        mms_launchers,
        "_exec_or_run",
        lambda cmd, env, once, **_kwargs: captured.update({"cmd": cmd, "env": env, "once": once}),
    )

    mms_launchers.launch_opencode({"model": "gpt-5.5"}, runtime, once=True)

    assert captured["cmd"] == [
        "opencode",
        "--pure",
        "--agent",
        "mobius-builder-pro",
        "-m",
        "mms-builder_primary/gpt-5.5",
    ]


def test_launch_opencode_lite_pro_prefers_fallback_when_primary_preflight_fails(monkeypatch):
    import mms_launchers

    runtime = _runtime(
        opencode_profile="lite_pro",
        opencode_agent="mobius-builder-pro",
        opencode_roster="lite_pro",
        opencode_launch_preflight=True,
        opencode_default_route_key="builder_primary",
        opencode_launch_fallback_route_keys=["builder_primary", "builder_fallback"],
        opencode_launch_fallback_agents={
            "builder_primary": "mobius-builder-pro",
            "builder_fallback": "mobius-builder-stable",
        },
        opencode_routes=[
            {
                "id": "builder_primary",
                "model": "gpt-5.5",
                "provider_id": "gpt55",
                "provider_name": "GPT 5.5",
                "openai_base_url": "https://gpt55.example/v1",
                "api_key": "sk-gpt55",
            },
            {
                "id": "builder_fallback",
                "model": "gpt-5.4",
                "provider_id": "gpt54",
                "provider_name": "GPT 5.4",
                "openai_base_url": "https://gpt54.example/v1",
                "api_key": "sk-gpt54",
            },
        ],
    )
    captured = {"preflight": []}

    monkeypatch.setattr(mms_launchers, "_opencode_gateway_health_check", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        mms_launchers,
        "_opencode_gateway_env",
        lambda *_args, **_kwargs: {"HOME": "/tmp/opencode", "MMS_SESSION_HOME": ""},
    )

    def fake_preflight(_env, agent, model_ref, timeout=None):
        captured["preflight"].append((agent, model_ref))
        return {"ok": model_ref.endswith("/gpt-5.4"), "returncode": 0 if model_ref.endswith("/gpt-5.4") else 1}

    monkeypatch.setattr(mms_launchers, "_opencode_run_preflight", fake_preflight)
    monkeypatch.setattr(
        mms_launchers,
        "_exec_or_run",
        lambda cmd, env, once, **_kwargs: captured.update({"cmd": cmd, "env": env, "once": once}),
    )

    mms_launchers.launch_opencode({"model": "gpt-5.5"}, runtime, once=True)

    assert captured["preflight"] == [
        ("mobius-builder-pro", "mms-builder_primary/gpt-5.5"),
        ("mobius-builder-stable", "mms-builder_fallback/gpt-5.4"),
    ]
    assert captured["cmd"] == [
        "opencode",
        "--pure",
        "--agent",
        "mobius-builder-stable",
        "-m",
        "mms-builder_fallback/gpt-5.4",
    ]
    assert captured["env"]["MMS_MODEL_NAME"] == "gpt-5.4"
    assert captured["env"]["MMS_OPENCODE_LAUNCH_MODEL"] == "mms-builder_fallback/gpt-5.4"


def test_core_tui_opencode_profile_action_resolves_before_model_channel(monkeypatch):
    import mms_core
    import mms_launchers
    import mms_tui

    captured = {}
    cfg = {"providers": [], "account": {"defaults": {}}, "accounts": []}
    provider = _runtime(
        id="dual-protocol",
        name="Dual Protocol",
        supported_clis=["codex"],
        protocols=["anthropic_messages", "openai_chat_completions"],
    )

    monkeypatch.setattr(
        mms_core,
        "_probe_models",
        lambda *_args, **_kwargs: {"models": ["K2.6", "gpt-5.4"]},
    )
    monkeypatch.setattr(mms_core, "_build_model_families_for_cli", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(mms_core, "_make_provider_options_loader", lambda *_args, **_kwargs: (lambda _model: []))
    monkeypatch.setattr(mms_core, "_get_scene_usage", lambda: ({}, {}))
    monkeypatch.setattr(mms_core, "check_cli_installed", lambda _cli: True)
    monkeypatch.setattr(mms_core, "_build_confirm_preview_catalog", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(mms_launchers, "get_export_env", lambda _cli, _runtime: {})
    monkeypatch.setattr(mms_launchers, "_caveman_available_for_cli", lambda _cli: False)
    monkeypatch.setattr(mms_launchers, "_ecc_available_for_claude", lambda: False)
    monkeypatch.setattr(mms_launchers, "_omc_available_for_claude", lambda: False)

    def fake_select_family_tui(*_args, **kwargs):
        captured["profile_options"] = kwargs.get("profile_options_by_cli")
        return ("profile", "opencode", "lite")

    def fake_confirm_tui(cli, model_info, **kwargs):
        captured["cli"] = cli
        captured["model_info"] = model_info
        captured["runtime"] = kwargs.get("runtime")
        return "q"

    monkeypatch.setattr(mms_tui, "select_family_tui", fake_select_family_tui)
    monkeypatch.setattr(mms_tui, "confirm_tui", fake_confirm_tui)

    assert mms_core._handle_tui_scene_selection(cfg, [], provider, False, ["opencode"]) is True
    assert [item["id"] for item in captured["profile_options"]["opencode"]] == [
        "lite_pro",
        "lite_pro_orchestrated",
        "lite",
        "heavy_omo",
        "raw",
    ]
    assert captured["cli"] == "opencode"
    assert captured["model_info"] == {"model": "gpt-5.4"}
    assert captured["runtime"]["id"] == "dual-protocol"
    assert captured["runtime"]["opencode_profile"] == "lite"


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


def test_core_opencode_loads_repo_local_route_health_latest(tmp_path):
    import mms_core

    health_dir = tmp_path / ".ai" / "opencode-health"
    health_dir.mkdir(parents=True)
    key = "lite_pro|explore_primary|glm-5-turbo|newapi|anthropic_messages"
    (health_dir / "latest.json").write_text(
        json.dumps(
            {
                "schema": "mms.opencode_route_health_latest.v1",
                "routes": {
                    key: {
                        "status": "live_healthy",
                        "health_score": 85,
                        "finished_at": "2026-05-16T10:00:00Z",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    latest = mms_core._load_opencode_route_health_latest(tmp_path)
    row = mms_core._opencode_route_health_for_route(
        latest,
        "lite_pro",
        "explore_primary",
        {
            "id": "explore_primary",
            "model": "glm-5-turbo",
            "provider_id": "newapi",
            "protocol": "anthropic_messages",
        },
    )

    assert row["status"] == "live_healthy"
    assert row["health_score"] == 85


def test_core_opencode_route_health_filters_blocked_and_fresh_unhealthy():
    import mms_core

    now = datetime(2026, 5, 16, 10, 10, tzinfo=timezone.utc)
    fresh_unhealthy = {
        "status": "unhealthy",
        "finished_at": (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
    }
    stale_unhealthy = {
        "status": "unhealthy",
        "finished_at": (now - timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
    }

    assert mms_core._opencode_route_health_allows_route({"status": "blocked"}, now=now) is False
    assert mms_core._opencode_route_health_allows_route(fresh_unhealthy, now=now) is False
    assert mms_core._opencode_route_health_allows_route(stale_unhealthy, now=now) is True
    assert mms_core._opencode_route_health_allows_route({"status": "degraded"}, now=now) is True


def test_core_opencode_route_health_sort_order_is_deterministic():
    import mms_core

    rows = [
        {"status": "unhealthy", "health_score": -25, "finished_at": "2026-05-16T10:00:00Z"},
        {"status": "degraded", "health_score": 65, "finished_at": "2026-05-16T10:00:00Z"},
        {"status": "live_healthy", "health_score": 85, "finished_at": "2026-05-16T10:00:00Z"},
        {"status": "untested", "health_score": 0, "finished_at": ""},
        {"status": "blocked", "health_score": -100, "finished_at": "2026-05-16T10:00:00Z"},
    ]

    ordered = sorted(rows, key=mms_core._opencode_route_health_sort_key)

    assert [row["status"] for row in ordered] == [
        "live_healthy",
        "degraded",
        "untested",
        "unhealthy",
        "blocked",
    ]


def test_core_opencode_model_route_skips_blocked_same_model_channel(monkeypatch):
    import mms_core

    provider_a = _runtime(
        id="channel-a",
        protocols=["anthropic_messages", "openai_chat_completions"],
        supported_clis=["opencode"],
        openai_base_url="https://a.example/v1",
        models=["glm-5-turbo"],
    )
    provider_b = _runtime(
        id="channel-b",
        protocols=["anthropic_messages", "openai_chat_completions"],
        supported_clis=["opencode"],
        openai_base_url="https://b.example/v1",
        models=["glm-5-turbo"],
    )
    monkeypatch.setattr(
        mms_core,
        "_provider_candidates",
        lambda *_args: [(provider_a, ["glm-5-turbo"]), (provider_b, ["glm-5-turbo"])],
    )
    monkeypatch.setattr(
        mms_core,
        "_load_opencode_route_health_latest",
        lambda *_args, **_kwargs: {
            "lite_pro|explore_primary|glm-5-turbo|channel-a|anthropic_messages": {
                "status": "blocked",
                "health_score": -100,
                "finished_at": "2026-05-16T10:00:00Z",
            },
            "lite_pro|explore_primary|glm-5-turbo|channel-b|anthropic_messages": {
                "status": "live_healthy",
                "health_score": 85,
                "finished_at": "2026-05-16T10:00:00Z",
            },
        },
    )

    route = mms_core._find_opencode_model_route(
        {"providers": []},
        provider_a,
        ["glm-5-turbo"],
        ("glm-5-turbo",),
        route_key="explore_primary",
    )

    assert route["provider_id"] == "channel-b"
    assert route["health_status"] == "live_healthy"


def test_core_opencode_model_route_uses_peer_model_when_primary_model_is_fresh_unhealthy(monkeypatch):
    import mms_core

    provider = _runtime(
        id="domestic",
        protocols=["anthropic_messages", "openai_chat_completions"],
        supported_clis=["opencode"],
        openai_base_url="https://domestic.example/v1",
        models=["glm-5-turbo", "kimi-for-coding"],
    )
    monkeypatch.setattr(mms_core, "_provider_candidates", lambda *_args: [(provider, ["glm-5-turbo", "kimi-for-coding"])])
    monkeypatch.setattr(
        mms_core,
        "_load_opencode_route_health_latest",
        lambda *_args, **_kwargs: {
            "lite_pro|explore_primary|glm-5-turbo|domestic|anthropic_messages": {
                "status": "unhealthy",
                "health_score": -25,
                "finished_at": "2026-05-16T10:00:00Z",
            },
            "lite_pro|explore_primary|kimi-for-coding|domestic|anthropic_messages": {
                "status": "untested",
                "health_score": 0,
                "finished_at": "",
            },
        },
    )
    monkeypatch.setattr(
        mms_core,
        "_opencode_route_health_is_fresh",
        lambda row, **_kwargs: row.get("status") == "unhealthy",
    )

    route = mms_core._find_opencode_model_route(
        {"providers": []},
        provider,
        ["glm-5-turbo", "kimi-for-coding"],
        ("glm-5-turbo", "kimi-for-coding"),
        route_key="explore_primary",
    )

    assert route["model"] == "kimi-for-coding"
    assert route["protocol"] == "anthropic_messages"


def test_core_opencode_profile_menu_includes_lite_pro_health_summary(monkeypatch):
    import mms_core

    monkeypatch.setattr(
        mms_core,
        "_load_opencode_route_health_latest",
        lambda *_args, **_kwargs: {
            "lite_pro|builder_primary|gpt-5.5|gpt|openai_chat_completions": {
                "profile": "lite_pro",
                "role": "builder_primary",
                "status": "live_healthy",
            },
            "lite_pro|explore_primary|glm-5-turbo|newapi|anthropic_messages": {
                "profile": "lite_pro",
                "role": "explore_primary",
                "status": "degraded",
            },
            "lite_pro|reviewer_primary|mimo-v2.5-pro|newapi|anthropic_messages": {
                "profile": "lite_pro",
                "role": "reviewer_primary",
                "status": "blocked",
            },
            "lite_pro_orchestrated|executor_primary|deepseek-v4-pro|newapi|anthropic_messages": {
                "profile": "lite_pro_orchestrated",
                "role": "executor_primary",
                "status": "live_healthy",
            },
            "lite_pro_orchestrated|executor_qwen|qwen3.6-plus|newapi|anthropic_messages": {
                "profile": "lite_pro_orchestrated",
                "role": "executor_qwen",
                "status": "degraded",
            },
        },
    )

    lite_pro = next(option for option in mms_core._opencode_profile_menu_options() if option["id"] == "lite_pro")
    orchestrated = next(option for option in mms_core._opencode_profile_menu_options() if option["id"] == "lite_pro_orchestrated")

    assert "health: 1/9 healthy" in lite_pro["summary"]
    assert "1 degraded" in lite_pro["summary"]
    assert "1 blocked" in lite_pro["summary"]
    assert "6 untested" in lite_pro["summary"]
    assert "health: 1/14 healthy" in orchestrated["summary"]
    assert "1 degraded" in orchestrated["summary"]
    assert "12 untested" in orchestrated["summary"]
