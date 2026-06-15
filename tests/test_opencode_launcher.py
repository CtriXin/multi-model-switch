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


def _write_skill(root: Path, name: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
    return skill_dir


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
    assert payload["permission"] == "allow"
    assert sorted(payload["agent"]) == [
        "mobius-builder",
        "mobius-explore",
        "mobius-fixer",
        "mobius-reviewer",
    ]
    assert payload["agent"]["mobius-builder"]["mode"] == "primary"
    assert payload["agent"]["mobius-explore"]["permission"]["edit"] == "deny"
    assert payload["agent"]["mobius-reviewer"]["permission"]["edit"] == "deny"
    assert payload["agent"]["mobius-fixer"]["permission"]["edit"] == "allow"

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


def test_opencode_config_keeps_local_rtk_plugin_out_of_json(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(mms_launchers, "_opencode_rtk_plugin_path", lambda _runtime=None: "/tmp/opencode-rtk.ts")

    payload = json.loads(
        mms_launchers._build_opencode_config_content(
            _runtime(models=["deepseek-chat"]),
            "deepseek-chat",
        )
    )

    assert "plugin" not in payload


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


def test_opencode_config_can_disable_default_bypass():
    import mms_launchers

    payload = json.loads(
        mms_launchers._build_opencode_config_content(
            _runtime(models=["deepseek-chat"], bypass=False),
            "deepseek-chat",
        )
    )

    assert payload["permission"] == {"edit": "ask", "bash": "ask"}
    assert payload["agent"]["mobius-fixer"]["permission"]["edit"] == "ask"


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

    for model in ("mimo-v2.5", "K2.6", "kimi-k2.5", "qwen3.6-plus", "gpt-5.3-codex"):
        config = mms_launchers._opencode_model_config(_runtime(), model)
        assert config["attachment"] is True
        assert config["modalities"] == {"input": ["text", "image"], "output": ["text"]}
        if model == "mimo-v2.5":
            assert config["reasoning"] is False
            assert config["limit"] == {"context": 1048576, "output": 131072}

    for model in ("mimo-v2.5-pro", "qwen3-coder-plus", "glm-5.1", "deepseek-v4-pro", "MiniMax-M2.7"):
        config = mms_launchers._opencode_model_config(_runtime(), model)
        assert "attachment" not in config
        assert "modalities" not in config
        if model == "mimo-v2.5-pro":
            assert config["reasoning"] is False
            assert config["limit"] == {"context": 1048576, "output": 131072}


def test_core_opencode_prefers_mimo_openai_compatible_base_from_anthropic():
    import mms_core

    provider = _runtime(
        id="mimo-direct-anthropic",
        name="MiMo Direct",
        openai_base_url="",
        anthropic_base_url="https://token-plan-cn.xiaomimimo.com/anthropic",
        protocols=["anthropic_messages"],
        supported_clis=["opencode"],
    )

    candidates = mms_core._opencode_route_transport_candidates(provider, "mimo-v2.5-pro")

    assert candidates == [
        (
            "openai_chat_completions",
            "https://token-plan-cn.xiaomimimo.com/v1",
            "https://token-plan-cn.xiaomimimo.com/anthropic/v1",
        )
    ]


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

    session_home = Path(env["MMS_SESSION_HOME"])
    config_path = Path(env["OPENCODE_CONFIG"])
    assert session_home.is_dir()
    assert config_path == session_home / ".config" / "opencode" / "opencode.json"
    config_payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert config_payload["provider"]["mms"]["options"]["apiKey"] == "{env:MMS_OPENCODE_API_KEY}"
    assert env["HOME"] == str(real_home)
    assert env["XDG_CONFIG_HOME"] == str(session_home / ".config")
    assert env["XDG_CACHE_HOME"] == str(session_home / ".cache")
    assert env["XDG_DATA_HOME"] == str(session_home / ".local" / "share")
    assert env["XDG_STATE_HOME"] == str(session_home / ".local" / "state")
    assert env["MMS_SESSION_HOME"] == str(session_home)
    assert env["MMS_HOME_ISOLATION_MODE"] == "soft"
    assert env["MMS_OPENCODE_SOFT_HOME"] == "1"
    assert env["MMS_OPENCODE_API_KEY"] == "sk-runtime"
    assert env["OPENAI_BASE_URL"] == "https://api.deepseek.com/v1"
    assert env["OPENCODE_CLIENT"] == "mms"
    assert env["OPENCODE_PERMISSION"] == mms_launchers.OPENCODE_BYPASS_PERMISSION_ENV
    assert env["MMS_OPENCODE_BYPASS"] == "1"
    assert "OPENCODE_CONFIG_CONTENT" not in env


def test_opencode_gateway_env_materializes_session_assets(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    caveman_root = tmp_path / "caveman"
    (caveman_root / "skills").mkdir(parents=True)
    _write_skill(caveman_root / "skills", "caveman")
    web_access = _write_skill(tmp_path / "web-access-root", "web-access")
    weber = _write_skill(tmp_path / "weber-root", "weber")
    codegraph = _write_skill(tmp_path / "codegraph-root", "codegraph")
    toon = _write_skill(tmp_path / "toon-root", "toon")
    token_saver = _write_skill(tmp_path / "token-root", "token-saver")

    monkeypatch.setattr(mms_launchers, "_real_user_home", lambda: str(real_home))
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, *_args, **_kwargs: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_locale_profile", lambda env, *_args, **_kwargs: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_ip_stack_profile", lambda env, *_args, **_kwargs: env)
    monkeypatch.setattr(mms_launchers, "_resolve_caveman_root", lambda: str(caveman_root))
    monkeypatch.setattr(mms_launchers, "_resolve_web_access_root", lambda: str(web_access))
    monkeypatch.setattr(mms_launchers, "_resolve_weber_root", lambda: str(weber))
    monkeypatch.setattr(mms_launchers, "_resolve_codegraph_root", lambda: str(codegraph))
    monkeypatch.setattr(mms_launchers, "_resolve_toon_root", lambda: str(toon))
    monkeypatch.setattr(mms_launchers, "_resolve_token_saver_root", lambda: str(token_saver))
    rtk_plugin = tmp_path / "opencode-rtk.ts"
    rtk_plugin.write_text("export const RtkOpenCodePlugin = async () => ({})\n", encoding="utf-8")
    monkeypatch.setattr(mms_launchers, "_opencode_rtk_plugin_path", lambda _runtime=None: str(rtk_plugin))

    env = mms_launchers._opencode_gateway_env(
        _runtime(caveman_mode="enable"),
        model_info={"model": "deepseek-chat"},
    )

    config_dir = Path(env["OPENCODE_CONFIG_DIR"])
    payload = json.loads(Path(env["OPENCODE_CONFIG"]).read_text(encoding="utf-8"))
    assert "plugin" not in payload
    assert (config_dir / "plugins" / "mms-rtk.ts").is_symlink()
    assert (config_dir / "plugins" / "mms-rtk.ts").resolve() == rtk_plugin
    for name in ("caveman", "web-access", "weber", "codegraph", "toon", "token-saver"):
        assert (config_dir / "skills" / name).is_symlink()
        assert (config_dir / "skills" / name / "SKILL.md").exists()
    packet = json.loads(Path(env["MMS_SESSION_PACKET_JSON"]).read_text(encoding="utf-8"))
    features = {row["name"]: row["status"] for row in packet["features"]}
    assert features["caveman"] == "enabled"
    assert features["opencode_rtk"] == "enabled"
    assert features["web_access"] == "enabled"
    assert features["codegraph"] == "enabled"


def test_opencode_gateway_env_can_disable_bypass(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(mms_launchers, "_real_user_home", lambda: str(real_home))
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_launchers, "_install_session_packet_env", lambda env, **_kwargs: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, *_args, **_kwargs: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_locale_profile", lambda env, *_args, **_kwargs: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_ip_stack_profile", lambda env, *_args, **_kwargs: env)
    monkeypatch.setenv("OPENCODE_PERMISSION", mms_launchers.OPENCODE_BYPASS_PERMISSION_ENV)

    env = mms_launchers._opencode_gateway_env(
        _runtime(bypass=False),
        model_info={"model": "deepseek-chat"},
    )
    config_payload = json.loads(Path(env["OPENCODE_CONFIG"]).read_text(encoding="utf-8"))

    assert "OPENCODE_PERMISSION" not in env
    assert env["MMS_OPENCODE_BYPASS"] == "0"
    assert config_payload["permission"] == {"edit": "ask", "bash": "ask"}


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


def test_launch_opencode_backend_agent_uses_headless_server(monkeypatch):
    import mms_launchers

    captured = {}

    monkeypatch.setattr(mms_launchers, "gateway_health_check", lambda *_args, **_kwargs: None)
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
        _runtime(openai_base_url="http://129.146.32.12:3000/openai", opencode_entrypoint="serve"),
        once=True,
    )

    assert captured["cmd"] == ["opencode", "serve", "--pure"]
    assert captured["env"]["MMS_OPENCODE_ENTRYPOINT"] == "serve"
    assert captured["env"]["MMS_OPENCODE_LAUNCH_MODEL"] == "mms/deepseek-chat"
    assert captured["env"]["MMS_OPENCODE_LAUNCH_AGENT"] == "mobius-builder"
    assert captured["once"] is True


def test_launch_opencode_acp_uses_session_local_config_without_model_flag(monkeypatch):
    import mms_launchers

    captured = {}

    monkeypatch.setattr(mms_launchers, "gateway_health_check", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        mms_launchers,
        "_opencode_gateway_env",
        lambda runtime, model_info=None: {"PATH": "/tmp/bin", "HOME": "/tmp/opencode-session"},
    )

    def fake_exec(cmd, env, once, **_kwargs):
        captured["cmd"] = cmd
        captured["env"] = env

    monkeypatch.setattr(mms_launchers, "_exec_or_run", fake_exec)

    mms_launchers.launch_opencode(
        {"model": "deepseek-chat"},
        _runtime(openai_base_url="http://129.146.32.12:3000/openai", opencode_entrypoint="acp"),
        once=False,
    )

    assert captured["cmd"] == ["opencode", "acp", "--pure"]
    assert captured["env"]["MMS_OPENCODE_ENTRYPOINT"] == "acp"
    assert "-m" not in captured["cmd"]
    assert "--agent" not in captured["cmd"]


def test_launch_opencode_heavy_omo_uses_global_opencode_config(monkeypatch):
    import mms_launchers

    captured = {}
    real_home = Path("/tmp/mms-real-home")

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
    monkeypatch.setattr(mms_launchers, "_real_user_home", lambda: str(real_home))
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))
    monkeypatch.setenv("HOME", "/tmp/mms-isolated-home")
    monkeypatch.setenv("OPENCODE_CONFIG", "/tmp/isolated-opencode.json")

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
    assert captured["env"]["HOME"] == str(real_home)
    assert captured["env"]["XDG_CONFIG_HOME"] == str(real_home / ".config")
    assert "OPENCODE_CONFIG" not in captured["env"]
    assert captured["env"]["OPENCODE_CLIENT"] == "mms"
    assert captured["env"]["MMS_OPENCODE_PROFILE"] == "heavy_omo"
    assert captured["env"]["OPENCODE_PERMISSION"] == mms_launchers.OPENCODE_BYPASS_PERMISSION_ENV
    assert captured["env"]["MMS_OPENCODE_BYPASS"] == "1"
    assert captured["once"] is True


def test_opencode_run_preflight_uses_bypass_flag(monkeypatch):
    import mms_launchers

    captured = {"cmds": []}

    class Completed:
        returncode = 0
        stdout = "OK"
        stderr = ""

    def fake_run(cmd, **_kwargs):
        captured["cmds"].append(cmd)
        return Completed()

    monkeypatch.setattr(mms_launchers.subprocess, "run", fake_run)

    enabled = mms_launchers._opencode_run_preflight(
        {"HOME": "/tmp/opencode"},
        "mobius-builder",
        "mms/deepseek-chat",
        timeout=1,
    )
    disabled = mms_launchers._opencode_run_preflight(
        {"HOME": "/tmp/opencode"},
        "mobius-builder",
        "mms/deepseek-chat",
        timeout=1,
        bypass=False,
    )

    assert enabled["ok"] is True
    assert disabled["ok"] is True
    assert mms_launchers.OPENCODE_BYPASS_FLAG in captured["cmds"][0]
    assert mms_launchers.OPENCODE_BYPASS_FLAG not in captured["cmds"][1]


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
    assert exports["OPENCODE_PERMISSION"] == mms_launchers.OPENCODE_BYPASS_PERMISSION_ENV
    assert exports["MMS_OPENCODE_BYPASS"] == "1"
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
        "OPENCODE_PERMISSION": mms_launchers.OPENCODE_BYPASS_PERMISSION_ENV,
        "MMS_OPENCODE_BYPASS": "1",
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
        "OPENCODE_PERMISSION": mms_launchers.OPENCODE_BYPASS_PERMISSION_ENV,
        "MMS_OPENCODE_BYPASS": "1",
        "MMS_OPENCODE_PROFILE": "heavy_omo",
    }


def test_launch_cli_opencode_omo_skips_provider_validation(monkeypatch):
    import mms_launchers

    captured = {}
    runtime = {
        "id": "global-opencode-omo",
        "name": "Global OpenCode / OMO",
        "runtime_kind": "opencode_profile",
        "auth_mode": "global_config",
        "opencode_profile": "heavy_omo",
        "opencode_use_global_config": True,
    }

    monkeypatch.setattr(
        mms_launchers,
        "validate_provider_for_cli",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("OMO is not a provider runtime")),
    )

    def fake_launcher(model_info, launch_runtime, once=False, **_kwargs):
        captured["model_info"] = model_info
        captured["runtime"] = launch_runtime
        captured["once"] = once

    monkeypatch.setitem(mms_launchers.LAUNCHERS, "opencode", fake_launcher)

    mms_launchers.launch_cli("opencode", {"model": "global-omo"}, runtime, once=True)

    assert captured["model_info"] == {"model": "global-omo"}
    assert captured["runtime"]["id"] == "global-opencode-omo"
    assert captured["runtime"]["auth_mode"] == "global_config"
    assert captured["once"] is True


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

    assert mms_core._normalize_opencode_profile_id("lite-pro") == "lite_pro_orchestrated"
    assert mms_core._normalize_opencode_profile_id("agent") == "lite_pro_orchestrated"
    assert mms_core._normalize_opencode_profile_id("orchestrated") == "lite_pro_orchestrated"
    assert mms_core._normalize_opencode_profile_id("openspec-multi") == "lite_pro_orchestrated"
    assert mms_core._normalize_opencode_profile_id("review") == "review_toolful"
    assert mms_core._normalize_opencode_profile_id("omo") == "heavy_omo"
    assert mms_core._opencode_profile_selection("lite_pro_orchestrated_backend") == ("lite_pro_orchestrated", "serve")
    assert mms_core._opencode_profile_selection("lite_pro_orchestrated_acp") == ("lite_pro_orchestrated", "acp")

    lite = mms_core._apply_opencode_profile(_runtime(), "lite")
    agent = mms_core._apply_opencode_profile(_runtime(), "agent")
    backend_multi = mms_core._apply_opencode_profile(_runtime(), "lite_pro_orchestrated_backend")
    review = mms_core._apply_opencode_profile(_runtime(), "review")
    heavy = mms_core._apply_opencode_profile(_runtime(), "omo")
    raw = mms_core._apply_opencode_profile(_runtime(), "raw")

    assert lite["opencode_pure"] is True
    assert lite["opencode_agent"] == "mobius-builder"
    assert lite["opencode_lite_agents"] is True
    assert agent["opencode_agent"] == "mobius-builder-pro"
    assert agent["opencode_launch_preflight"] is False
    assert agent["opencode_launch_fallback_route_keys"] == ["builder_primary", "builder_fallback"]
    orchestrated = mms_core._apply_opencode_profile(_runtime(), "lite_pro_orchestrated")
    assert orchestrated["opencode_agent"] == "mobius-builder-pro"
    assert orchestrated["opencode_roster"] == "lite_pro_orchestrated"
    assert orchestrated["opencode_profile_label"] == "Agent"
    assert backend_multi["opencode_profile"] == "lite_pro_orchestrated"
    assert backend_multi["opencode_entrypoint"] == "serve"
    assert review["opencode_profile"] == "review_toolful"
    assert review["opencode_profile_label"] == "Review"
    assert review["opencode_agent"] == "review-hub-host"
    assert review["opencode_roster"] == "review_toolful"
    assert review["opencode_launch_fallback_route_keys"] == ["builder_primary", "review_host_fallback"]
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


def test_core_opencode_review_profile_uses_gpt54_host_and_review_agent():
    import mms_core
    import mms_launchers

    cfg = {"providers": [], "account": {"defaults": {}}, "accounts": []}
    provider = _runtime(
        id="crs-gpt",
        name="CRS GPT",
        supported_clis=["opencode"],
        protocols=["openai_chat_completions"],
    )

    model_info, runtime = mms_core._resolve_opencode_profile_runtime(
        cfg,
        provider,
        ["gpt-5.5", "gpt-5.4", "gpt-5.3-codex"],
        "review",
    )
    payload = mms_launchers._build_opencode_config_payload(runtime, model_info["model"])

    assert model_info == {"model": "gpt-5.4", "profile": "review_toolful"}
    assert runtime["id"] == "crs-gpt"
    assert runtime["opencode_profile"] == "review_toolful"
    assert runtime["opencode_agent"] == "review-hub-host"
    assert runtime["opencode_default_agent"] == "review-hub-host"
    assert runtime["opencode_default_route_key"] == "builder_primary"
    assert runtime["opencode_launch_fallback_agents"]["review_host_fallback"] == "review-hub-host-fallback"
    assert payload["model"].endswith("/gpt-5.4")
    assert payload["default_agent"] == "review-hub-host"
    assert payload["agent"]["review-hub-host"]["mode"] == "primary"
    assert payload["agent"]["review-hub-host"]["model"].endswith("/gpt-5.4")
    assert payload["agent"]["review-hub-host"]["permission"]["edit"] == "deny"
    assert payload["agent"]["review-hub-host"]["permission"]["bash"]["review-hub *"] == "allow"
    assert "review-hub worker-plan" in payload["agent"]["review-hub-host"]["prompt"]


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
        lambda *_args: [(provider, models), (mimo_direct, ["mimo-v2.5-pro", "mimo-v2.5"])],
    )

    model_info, runtime = mms_core._resolve_opencode_profile_runtime(
        cfg,
        provider,
        models,
        "lite_pro",
    )
    payload = mms_launchers._build_opencode_config_payload(runtime, model_info["model"])

    assert model_info == {"model": "gpt-5.5", "profile": "lite_pro_orchestrated"}
    assert runtime["opencode_agent"] == "mobius-builder-pro"
    assert runtime["opencode_launch_preflight"] is False
    assert runtime["opencode_launch_fallback_agents"]["builder_fallback"] == "mobius-builder-stable"
    assert payload["model"].endswith("/gpt-5.5")
    assert payload["default_agent"] == "mobius-builder-pro"
    assert payload["agent"]["mobius-builder-pro"]["model"].endswith("/gpt-5.5")
    assert payload["agent"]["mobius-builder-stable"]["mode"] == "primary"
    assert payload["agent"]["mobius-builder-stable"]["model"].endswith("/gpt-5.4")
    assert payload["agent"]["mobius-spec-writer"]["model"].endswith("/gpt-5.5")
    assert payload["agent"]["mobius-spec-compliance-reviewer"]["model"].endswith("/gpt-5.5")
    assert payload["agent"]["mobius-builder-pro"]["permission"]["task"]["mobius-spec-writer"] == "allow"
    assert payload["agent"]["mobius-builder-pro"]["permission"]["task"]["mobius-spec-compliance-reviewer"] == "allow"
    spec_route = next(route for route in runtime["opencode_routes"] if route["id"] == "spec_writer")
    assert spec_route["protocol"] == "openai_responses"
    assert payload["agent"]["mobius-explore-glm"]["model"].endswith("/glm-5-turbo")
    assert payload["agent"]["mobius-explore-kimi"]["model"].endswith("/kimi-for-coding")
    assert payload["agent"]["mobius-vision-mimo"]["model"].endswith("/mimo-v2.5")
    vision_route = next(route for route in runtime["opencode_routes"] if route["id"] == "vision_primary")
    assert vision_route["provider_id"] == "mimo-direct-anthropic"
    assert payload["provider"]["mms-vision_primary"]["models"]["mimo-v2.5"]["attachment"] is True
    assert payload["agent"]["mobius-reviewer-gpt55"]["model"].endswith("/gpt-5.5")
    reviewer_route = next(route for route in runtime["opencode_routes"] if route["id"] == "reviewer_primary")
    assert reviewer_route["provider_id"] == "mixed"
    assert reviewer_route["protocol"] == "openai_responses"
    assert payload["agent"]["mobius-reviewer-gpt54"]["model"].endswith("/gpt-5.4")
    assert payload["agent"]["mobius-reviewer-mimo"]["model"].endswith("/mimo-v2.5-pro")
    assert payload["provider"]["mms-reviewer_mimo"]["models"]["mimo-v2.5-pro"]["reasoning"] is False
    assert payload["agent"]["mobius-bughunt-deepseek"]["model"].endswith("/deepseek-v4-pro")
    assert payload["agent"]["mobius-bughunt-deepseek"]["permission"]["edit"] == "deny"
    assert payload["agent"]["mobius-bughunt-glm"]["model"].endswith("/glm-5.1")
    assert payload["agent"]["mobius-bughunt-glm"]["permission"]["edit"] == "deny"
    assert payload["agent"]["mobius-fixer-gpt54"]["model"].endswith("/gpt-5.4")
    assert payload["agent"]["mobius-fixer-gpt54"]["description"] == "Lite Pro GPT focused fixer"
    assert "steps" not in payload["agent"]["mobius-fixer-gpt54"]
    assert len(payload["provider"]) >= 7
    assert payload["provider"]["mms-explore_primary"]["npm"] == "@ai-sdk/anthropic"
    assert payload["provider"]["mms-reviewer_fallback"]["npm"] == "@ai-sdk/openai"
    assert payload["provider"]["mms-builder_primary"]["npm"] == "@ai-sdk/openai"
    builder_route = next(route for route in runtime["opencode_routes"] if route["id"] == "builder_primary")
    assert builder_route["protocol"] == "openai_responses"


def test_opencode_lite_pro_preflight_is_opt_in(monkeypatch):
    import mms_core
    import mms_launchers

    runtime = mms_core._apply_opencode_profile(_runtime(), "lite_pro")

    monkeypatch.delenv("MMS_OPENCODE_LAUNCH_PREFLIGHT", raising=False)
    assert mms_launchers._opencode_launch_preflight_enabled(runtime) is False

    monkeypatch.setenv("MMS_OPENCODE_LAUNCH_PREFLIGHT", "1")
    assert mms_launchers._opencode_launch_preflight_enabled(runtime) is True


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
        "qwen3.7-max",
        "qwen3.6-plus",
    ]
    monkeypatch.setattr(
        mms_core,
        "_provider_candidates",
        lambda *_args: [(provider, models), (mimo_direct, ["mimo-v2.5-pro", "mimo-v2.5"])],
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
    assert builder["permission"]["task"]["mobius-spec-writer"] == "allow"
    assert builder["permission"]["task"]["mobius-spec-compliance-reviewer"] == "allow"
    assert builder["permission"]["task"]["mobius-explore-qwen"] == "allow"
    assert builder["permission"]["task"]["mobius-executor-gpt54"] == "allow"
    assert builder["permission"]["task"]["mobius-bughunt-qwen"] == "allow"
    assert "Do not edit files directly" in builder["prompt"]
    assert "OpenSpec/SpecBridge-style contract" in builder["prompt"]
    assert payload["agent"]["mobius-builder-stable"]["permission"]["edit"] == "deny"
    assert payload["agent"]["mobius-spec-writer"]["model"].endswith("/gpt-5.5")
    assert payload["agent"]["mobius-spec-compliance-reviewer"]["model"].endswith("/gpt-5.5")
    assert payload["agent"]["mobius-executor-gpt54"]["model"].endswith("/gpt-5.4")
    assert "steps" not in payload["agent"]["mobius-executor-gpt54"]
    assert "do not reinterpret the architecture" in payload["agent"]["mobius-executor-gpt54"]["prompt"]
    assert payload["agent"]["mobius-bughunt-deepseek"]["model"].endswith("/deepseek-v4-pro")
    assert payload["agent"]["mobius-bughunt-deepseek"]["permission"]["edit"] == "deny"
    assert payload["agent"]["mobius-bughunt-glm"]["model"].endswith("/glm-5.1")
    assert payload["agent"]["mobius-bughunt-glm"]["permission"]["edit"] == "deny"
    assert payload["agent"]["mobius-bughunt-qwen"]["model"].endswith("/qwen3.7-max")
    assert payload["agent"]["mobius-bughunt-qwen"]["permission"]["edit"] == "deny"
    assert payload["agent"]["mobius-reviewer-gpt55"]["model"].endswith("/gpt-5.5")
    assert payload["agent"]["mobius-reviewer-gpt54"]["model"].endswith("/gpt-5.4")
    assert payload["agent"]["mobius-reviewer-mimo"]["model"].endswith("/mimo-v2.5-pro")
    assert payload["agent"]["mobius-vision-mimo"]["model"].endswith("/mimo-v2.5")
    assert payload["agent"]["mobius-vision-qwen"]["model"].endswith("/qwen3.6-plus")
    assert payload["agent"]["mobius-explore-qwen"]["model"].endswith("/qwen3.7-max")
    executor_models = {
        payload["agent"][name]["model"].rsplit("/", 1)[-1]
        for name in payload["agent"]
        if name.startswith("mobius-executor-")
    }
    assert executor_models == {"gpt-5.4"}
    assert payload["agent"]["mobius-reviewer-gpt55"]["model"].rsplit("/", 1)[-1] not in executor_models
    qwen_route = next(route for route in runtime["opencode_routes"] if route["id"] == "bughunt_qwen")
    assert qwen_route["protocol"] == "anthropic_messages"
    vision_qwen_route = next(route for route in runtime["opencode_routes"] if route["id"] == "vision_qwen")
    assert vision_qwen_route["protocol"] == "anthropic_messages"


def test_core_opencode_lite_pro_uses_agent_model_overrides(monkeypatch):
    import mms_core
    import mms_launchers

    cfg = {
        "providers": [],
        "account": {"defaults": {}},
        "accounts": [],
        "opencode": {
            "agent_models": {
                "mobius-explore-glm": {"provider_id": "domestic", "model": "kimi-for-coding"},
            }
        },
    }
    gpt = _runtime(
        id="gpt",
        name="GPT",
        protocols=["openai_chat_completions"],
        openai_base_url="https://gpt.example/v1",
    )
    domestic = _runtime(
        id="domestic",
        name="Domestic",
        protocols=["anthropic_messages"],
        anthropic_base_url="https://domestic.example/v1",
    )
    monkeypatch.setattr(
        mms_core,
        "_provider_candidates",
        lambda *_args: [(gpt, ["gpt-5.5", "gpt-5.4"]), (domestic, ["glm-5-turbo", "kimi-for-coding"])],
    )

    model_info, runtime = mms_core._resolve_opencode_profile_runtime(
        cfg,
        gpt,
        ["gpt-5.5", "gpt-5.4"],
        "lite_pro_orchestrated",
    )
    payload = mms_launchers._build_opencode_config_payload(runtime, model_info["model"])
    explore_route = next(route for route in runtime["opencode_routes"] if route["id"] == "explore_primary")

    assert explore_route["provider_id"] == "domestic"
    assert explore_route["model"] == "kimi-for-coding"
    assert runtime["opencode_agent_model_overrides"]["mobius-explore-glm"]["model"] == "kimi-for-coding"
    assert payload["agent"]["mobius-explore-glm"]["model"].endswith("/kimi-for-coding")


def test_core_opencode_lite_pro_uses_agent_roster_custom_and_disabled(monkeypatch):
    import mms_core
    import mms_launchers

    cfg = {
        "providers": [],
        "account": {"defaults": {}},
        "accounts": [],
        "opencode": {
            "agent_roster": {
                "mobius-vision-mimo": {"enabled": False, "preset": "vision"},
                "mobius-vision-custom-1": {
                    "enabled": True,
                    "custom": True,
                    "preset": "vision",
                    "provider_id": "domestic",
                    "model": "qwen3.6-plus",
                    "description": "Custom Qwen vision helper",
                },
            }
        },
    }
    gpt = _runtime(
        id="gpt",
        name="GPT",
        protocols=["openai_chat_completions"],
        openai_base_url="https://gpt.example/v1",
    )
    domestic = _runtime(
        id="domestic",
        name="Domestic",
        protocols=["anthropic_messages"],
        anthropic_base_url="https://domestic.example/v1",
    )
    monkeypatch.setattr(
        mms_core,
        "_provider_candidates",
        lambda *_args: [
            (gpt, ["gpt-5.5", "gpt-5.4"]),
            (domestic, ["qwen3.6-plus", "mimo-v2.5"]),
        ],
    )

    model_info, runtime = mms_core._resolve_opencode_profile_runtime(
        cfg,
        gpt,
        ["gpt-5.5", "gpt-5.4"],
        "lite_pro_orchestrated",
    )
    payload = mms_launchers._build_opencode_config_payload(runtime, model_info["model"])

    assert "mobius-vision-mimo" not in runtime["opencode_agent_model_keys"]
    assert "mobius-vision-mimo" not in payload["agent"]
    assert runtime["opencode_agent_model_keys"]["mobius-vision-custom-1"].startswith("custom_")
    assert payload["agent"]["mobius-vision-custom-1"]["model"].endswith("/qwen3.6-plus")
    assert payload["agent"]["mobius-vision-custom-1"]["permission"]["edit"] == "deny"
    assert payload["agent"]["mobius-vision-custom-1"]["description"] == "Custom Qwen vision helper"
    assert payload["agent"]["mobius-builder-pro"]["permission"]["task"]["mobius-vision-custom-1"] == "allow"
    assert "mobius-vision-mimo" not in payload["agent"]["mobius-builder-pro"]["permission"]["task"]


def test_core_opencode_lite_pro_keeps_required_builder_when_roster_disables_it(monkeypatch):
    import mms_core
    import mms_launchers

    cfg = {
        "providers": [],
        "account": {"defaults": {}},
        "accounts": [],
        "opencode": {
            "agent_roster": {
                "mobius-builder-pro": {"enabled": False, "preset": "builder"},
            }
        },
    }
    gpt = _runtime(
        id="gpt",
        name="GPT",
        protocols=["openai_chat_completions"],
        openai_base_url="https://gpt.example/v1",
    )
    monkeypatch.setattr(
        mms_core,
        "_provider_candidates",
        lambda *_args: [(gpt, ["gpt-5.5", "gpt-5.4"])],
    )

    model_info, runtime = mms_core._resolve_opencode_profile_runtime(
        cfg,
        gpt,
        ["gpt-5.5", "gpt-5.4"],
        "lite_pro_orchestrated",
    )
    payload = mms_launchers._build_opencode_config_payload(runtime, model_info["model"])

    assert model_info == {"model": "gpt-5.5", "profile": "lite_pro_orchestrated"}
    assert runtime["opencode_agent_model_keys"]["mobius-builder-pro"] == "builder_primary"
    assert payload["default_agent"] == "mobius-builder-pro"
    assert "mobius-builder-pro" in payload["agent"]


def test_core_opencode_profile_menu_backend_and_acp_apply_entrypoints(monkeypatch):
    import mms_core

    cfg = {"providers": [], "account": {"defaults": {}}, "accounts": []}
    provider = _runtime(
        id="mixed",
        name="Mixed",
        supported_clis=["codex"],
        protocols=["anthropic_messages", "openai_chat_completions"],
    )
    models = [
        "gpt-5.5",
        "gpt-5.4",
        "glm-5-turbo",
        "glm-5.1",
        "kimi-for-coding",
        "deepseek-v4-pro",
        "qwen3.7-max",
        "qwen3.6-plus",
    ]
    monkeypatch.setattr(mms_core, "_provider_candidates", lambda *_args: [(provider, models)])

    backend_model_info, backend_runtime = mms_core._resolve_opencode_profile_runtime(
        cfg,
        provider,
        models,
        "lite_pro_orchestrated_backend",
    )
    acp_model_info, acp_runtime = mms_core._resolve_opencode_profile_runtime(
        cfg,
        provider,
        models,
        "lite_pro_orchestrated_acp",
    )

    assert backend_model_info == {"model": "gpt-5.5", "profile": "lite_pro_orchestrated"}
    assert backend_runtime["opencode_profile"] == "lite_pro_orchestrated"
    assert backend_runtime["opencode_entrypoint"] == "serve"
    assert acp_model_info == {"model": "gpt-5.5", "profile": "lite_pro_orchestrated"}
    assert acp_runtime["opencode_profile"] == "lite_pro_orchestrated"
    assert acp_runtime["opencode_entrypoint"] == "acp"


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
    assert payload["agent"]["mobius-reviewer-gpt55"]["model"].endswith("/gpt-5.5")
    assert payload["agent"]["mobius-reviewer-gpt54"]["model"].endswith("/gpt-5.4")
    assert payload["agent"]["mobius-spec-writer"]["model"].endswith("/gpt-5.5")
    assert payload["agent"]["mobius-spec-compliance-reviewer"]["model"].endswith("/gpt-5.5")
    assert payload["agent"]["mobius-bughunt-deepseek"]["model"].endswith("/gpt-5.4")
    assert payload["agent"]["mobius-bughunt-glm"]["model"].endswith("/gpt-5.4")
    assert all(
        route["protocol"] == "openai_responses"
        for route in runtime["opencode_routes"]
        if route["model"].startswith("gpt-")
    )
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
    assert route["protocol"] == "openai_responses"


def test_core_opencode_lite_pro_prefers_responses_over_healthy_gpt_chat(monkeypatch):
    import mms_core

    provider = _runtime(
        id="gpt-openai",
        name="GPT OpenAI",
        supported_clis=["opencode"],
        protocols=["openai_chat_completions"],
        openai_base_url="https://openai-gpt.example/v1",
        models=["gpt-5.5"],
    )
    monkeypatch.setattr(mms_core, "_provider_candidates", lambda *_args: [(provider, ["gpt-5.5"])])
    monkeypatch.setattr(
        mms_core,
        "_load_opencode_route_health_latest",
        lambda *_args, **_kwargs: {
            "lite_pro|builder_primary|gpt-5.5|gpt-openai|openai_chat_completions": {
                "status": "live_healthy",
                "health_score": 80,
                "finished_at": "2026-05-16T10:00:00Z",
            }
        },
    )

    route = mms_core._find_opencode_model_route(
        {"providers": []},
        provider,
        ["gpt-5.5"],
        ("gpt-5.5",),
        route_key="builder_primary",
    )

    assert route["protocol"] == "openai_responses"


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

    def fake_preflight(_env, agent, model_ref, timeout=None, **_kwargs):
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
        return ("profile", "opencode", "agent")

    def fake_confirm_tui(cli, model_info, **kwargs):
        captured["cli"] = cli
        captured["model_info"] = model_info
        captured["runtime"] = kwargs.get("runtime")
        return "q"

    monkeypatch.setattr(mms_tui, "select_family_tui", fake_select_family_tui)
    monkeypatch.setattr(mms_tui, "confirm_tui", fake_confirm_tui)

    assert mms_core._handle_tui_launcher_selection(cfg, provider, False, ["opencode"]) is True
    assert [item["id"] for item in captured["profile_options"]["opencode"]] == ["agent", "review", "omo", "raw"]
    assert [item["label"] for item in captured["profile_options"]["opencode"]] == ["Agent", "Review", "OMO", "Raw"]
    assert captured["cli"] == "opencode"
    assert captured["model_info"] == {"model": "gpt-5.4", "profile": "lite_pro_orchestrated"}
    assert captured["runtime"]["id"] == "dual-protocol"
    assert captured["runtime"]["opencode_profile"] == "lite_pro_orchestrated"


def test_main_accepts_direct_opencode_profile_flag(monkeypatch):
    import mms_core

    cfg = {"providers": [], "account": {"defaults": {}}, "accounts": []}
    provider = _runtime(id="default-provider", name="Default Provider")
    captured = {}

    monkeypatch.setattr(mms_core.sys, "argv", ["mms", "opencode", "--profile", "agent"])
    monkeypatch.setattr(mms_core, "_extract_global_lang", lambda argv: (argv, None))
    monkeypatch.setattr(mms_core, "load_config", lambda: cfg)
    monkeypatch.setattr(mms_core, "_load_command_config", lambda: cfg)
    monkeypatch.setattr(mms_core, "set_language", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "_resolve_ui_language", lambda *_args, **_kwargs: "zh")
    monkeypatch.setattr(mms_core, "_ensure_startup_snapshot_guard", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "_refresh_routes_export_for_hive", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(mms_core, "_update_notice", lambda: None)
    monkeypatch.setattr(mms_core, "_start_async_update_check", lambda: None)
    monkeypatch.setattr(mms_core, "apply_local_overrides", lambda current_cfg: current_cfg)
    monkeypatch.setattr(mms_core, "ensure_provider_credentials", lambda _cfg, provider_id=None: provider)
    monkeypatch.setattr(mms_core, "ensure_models_ready", lambda _cfg, _provider: (provider, ["gpt-5.5"]))
    monkeypatch.setattr(mms_core, "_warm_probe_cache_async", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "_resolve_visible_clis", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(mms_core, "check_cli_installed", lambda _cli: True)
    monkeypatch.setattr(
        mms_core,
        "_resolve_interactive_launch_model",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("profile launch must not ask for a model")),
    )

    def fake_profile_runtime(_cfg, profile_provider, profile_models, profile_id):
        captured["profile_provider"] = profile_provider["id"]
        captured["profile_models"] = profile_models
        captured["profile_id"] = profile_id
        runtime = mms_core._apply_opencode_profile(_runtime(id="profile-runtime", model="gpt-5.5"), profile_id)
        return {"model": "gpt-5.5", "profile": profile_id}, runtime

    monkeypatch.setattr(mms_core, "_resolve_opencode_profile_runtime", fake_profile_runtime)
    monkeypatch.setattr(mms_core, "confirm_launch", lambda cli, model_info, once, runtime=None: "")
    monkeypatch.setattr(
        mms_core,
        "_launch_with_tracking",
        lambda cli, model_info, runtime, once=False: captured.update(
            {"cli": cli, "model_info": model_info, "runtime": runtime, "once": once}
        ),
    )

    mms_core.main()

    assert captured["profile_id"] == "lite_pro_orchestrated"
    assert captured["profile_provider"] == "default-provider"
    assert captured["profile_models"] == ["gpt-5.5"]
    assert captured["cli"] == "opencode"
    assert captured["model_info"] == {"model": "gpt-5.5", "profile": "lite_pro_orchestrated"}
    assert captured["runtime"]["opencode_profile"] == "lite_pro_orchestrated"


def test_main_uses_configured_opencode_default_profile_for_direct_target(monkeypatch):
    import mms_core

    cfg = {
        "providers": [],
        "account": {"defaults": {}},
        "accounts": [],
        "opencode": {"default_profile": "agent"},
    }
    provider = _runtime(id="default-provider", name="Default Provider")
    captured = {}

    monkeypatch.setattr(mms_core.sys, "argv", ["mms", "opencode"])
    monkeypatch.setattr(mms_core, "_extract_global_lang", lambda argv: (argv, None))
    monkeypatch.setattr(mms_core, "load_config", lambda: cfg)
    monkeypatch.setattr(mms_core, "_load_command_config", lambda: cfg)
    monkeypatch.setattr(mms_core, "set_language", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "_resolve_ui_language", lambda *_args, **_kwargs: "zh")
    monkeypatch.setattr(mms_core, "_ensure_startup_snapshot_guard", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "_refresh_routes_export_for_hive", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(mms_core, "_update_notice", lambda: None)
    monkeypatch.setattr(mms_core, "_start_async_update_check", lambda: None)
    monkeypatch.setattr(mms_core, "apply_local_overrides", lambda current_cfg: current_cfg)
    monkeypatch.setattr(mms_core, "ensure_provider_credentials", lambda _cfg, provider_id=None: provider)
    monkeypatch.setattr(mms_core, "ensure_models_ready", lambda _cfg, _provider: (provider, ["gpt-5.5"]))
    monkeypatch.setattr(mms_core, "_warm_probe_cache_async", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "_resolve_visible_clis", lambda *_args, **_kwargs: ["opencode"])
    monkeypatch.setattr(mms_core, "check_cli_installed", lambda _cli: True)
    monkeypatch.setattr(
        mms_core,
        "_resolve_interactive_launch_model",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("configured profile launch must not ask for a model")),
    )

    def fake_profile_runtime(_cfg, profile_provider, profile_models, profile_id):
        captured["profile_provider"] = profile_provider["id"]
        captured["profile_models"] = profile_models
        captured["profile_id"] = profile_id
        runtime = mms_core._apply_opencode_profile(_runtime(id="profile-runtime", model="gpt-5.5"), profile_id)
        return {"model": "gpt-5.5", "profile": profile_id}, runtime

    monkeypatch.setattr(mms_core, "_resolve_opencode_profile_runtime", fake_profile_runtime)
    monkeypatch.setattr(mms_core, "confirm_launch", lambda cli, model_info, once, runtime=None: "")
    monkeypatch.setattr(
        mms_core,
        "_launch_with_tracking",
        lambda cli, model_info, runtime, once=False: captured.update(
            {"cli": cli, "model_info": model_info, "runtime": runtime, "once": once}
        ),
    )

    mms_core.main()

    assert captured["profile_id"] == "lite_pro_orchestrated"
    assert captured["profile_provider"] == "default-provider"
    assert captured["profile_models"] == ["gpt-5.5"]
    assert captured["cli"] == "opencode"
    assert captured["runtime"]["opencode_profile"] == "lite_pro_orchestrated"


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
            "lite_pro_orchestrated|explore_primary|glm-5-turbo|channel-a|anthropic_messages": {
                "status": "blocked",
                "health_score": -100,
                "finished_at": "2026-05-16T10:00:00Z",
            },
            "lite_pro_orchestrated|explore_primary|glm-5-turbo|channel-b|anthropic_messages": {
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
            "lite_pro_orchestrated|explore_primary|glm-5-turbo|domestic|anthropic_messages": {
                "status": "unhealthy",
                "health_score": -25,
                "finished_at": "2026-05-16T10:00:00Z",
            },
            "lite_pro_orchestrated|explore_primary|kimi-for-coding|domestic|anthropic_messages": {
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


def test_opencode_smoke_classifies_reasoning_content_roundtrip_as_blocked():
    from scripts import smoke_opencode_profile

    route = {
        "id": "reviewer_primary",
        "model": "mimo-v2.5-pro",
        "provider_id": "mimo-direct-anthropic",
        "protocol": "anthropic_messages",
    }
    check = {
        "ok": False,
        "returncode": 1,
        "stderr": "Param Incorrect: The reasoning_content in the thinking mode must be passed back to the API.",
        "cache_transport_evidence": {
            "schema": "cache_transport_evidence.v1",
            "model": "mimo-v2.5-pro",
            "provider_id": "mimo-direct-anthropic",
            "protocol": "anthropic_messages",
            "request_url": "https://token-plan-cn.xiaomimimo.com/anthropic/v1/messages",
        },
    }

    error_class = smoke_opencode_profile._classify_error(check, route)

    assert error_class == "reasoning_content_roundtrip_required"
    assert smoke_opencode_profile._health_status(error_class, 0.5) == "blocked"


def test_opencode_smoke_classifies_thinking_block_roundtrip_as_blocked():
    from scripts import smoke_opencode_profile

    route = {
        "id": "reviewer_primary",
        "model": "deepseek-v4-pro",
        "provider_id": "deepseek-direct",
        "protocol": "anthropic_messages",
    }
    check = {
        "ok": False,
        "returncode": 1,
        "stderr": "API Error: 400 The `content[].thinking` in the thinking mode must be passed back to the API.",
        "cache_transport_evidence": {
            "schema": "cache_transport_evidence.v1",
            "model": "deepseek-v4-pro",
            "provider_id": "deepseek-direct",
            "protocol": "anthropic_messages",
            "request_url": "https://deepseek.example/v1/messages",
        },
    }

    error_class = smoke_opencode_profile._classify_error(check, route)

    assert error_class == "reasoning_content_roundtrip_required"
    assert smoke_opencode_profile._health_status(error_class, 0.5) == "blocked"


def test_core_opencode_profile_menu_includes_lite_pro_health_summary(monkeypatch):
    import mms_core

    monkeypatch.setattr(
        mms_core,
        "_load_opencode_route_health_latest",
        lambda *_args, **_kwargs: {
            "lite_pro|builder_primary|gpt-5.5|gpt|openai_responses": {
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
            "lite_pro_orchestrated|executor_gpt54|gpt-5.4|gpt|openai_responses": {
                "profile": "lite_pro_orchestrated",
                "role": "executor_gpt54",
                "status": "live_healthy",
            },
            "lite_pro_orchestrated|bughunt_qwen|qwen3.7-max|newapi|anthropic_messages": {
                "profile": "lite_pro_orchestrated",
                "role": "bughunt_qwen",
                "status": "degraded",
                "finished_at": "2026-05-16T10:00:00Z",
            },
            "lite_pro_orchestrated|bughunt_qwen|qwen3.7-max|newapi|openai_chat_completions": {
                "profile": "lite_pro_orchestrated",
                "role": "bughunt_qwen",
                "status": "live_healthy",
                "finished_at": "2026-05-15T10:00:00Z",
            },
        },
    )

    options = mms_core._opencode_profile_menu_options()
    agent = next(option for option in options if option["id"] == "agent")

    assert [option["id"] for option in options] == ["agent", "review", "omo", "raw"]
    assert agent["label"] == "Agent"
    assert agent["badge"] == "默认"
    assert "health: 1/18 healthy" in agent["summary"]
    assert "1 degraded" in agent["summary"]
    assert "16 untested" in agent["summary"]
