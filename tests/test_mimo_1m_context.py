from __future__ import annotations

import json
import os


def _empty_context_overrides():
    return {"models": {}, "provider_overrides": {}}


def test_mimo_pro_1m_suffix_uses_one_m_context(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(mms_launchers, "_load_model_context_overrides", _empty_context_overrides)

    assert (
        mms_launchers._lookup_context_window(
            "mimo-v2.5-pro[1m]",
            provider_id="mimo-direct-anthropic",
        )
        == 1_000_000
    )
    assert (
        mms_launchers._effective_context_window(
            "mimo-v2.5-pro[1m]",
            provider_id="mimo-direct-anthropic",
        )
        == 1_000_000
    )


def test_mimo_non_pro_1m_suffix_uses_one_m_context(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(mms_launchers, "_load_model_context_overrides", _empty_context_overrides)

    assert (
        mms_launchers._lookup_context_window(
            "mimo-v2.5[1m]",
            provider_id="mimo-direct-anthropic",
        )
        == 1_000_000
    )


def test_mimo_pro_without_1m_suffix_keeps_safe_context(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(mms_launchers, "_load_model_context_overrides", _empty_context_overrides)

    assert (
        mms_launchers._lookup_context_window(
            "mimo-v2.5-pro",
            provider_id="mimo-direct-anthropic",
        )
        == 262_144
    )


def test_mimo_without_1m_suffix_keeps_safe_context_on_anthropic(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(mms_launchers, "_load_model_context_overrides", _empty_context_overrides)

    assert (
        mms_launchers._lookup_context_window(
            "mimo-v2.5",
            provider_id="mimo-direct-anthropic",
        )
        == 262_144
    )


def test_mimo_context_policy_enables_plain_model_1m(monkeypatch, tmp_path):
    import mms_launchers

    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(mms_launchers, "_load_model_context_overrides", _empty_context_overrides)
    (tmp_path / "model-policy.json").write_text(
        json.dumps(
            {
                "models": {
                    "mimo-v2.5": {
                        "capabilities": {
                            "context_window_tokens": 1_000_000,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    assert (
        mms_launchers._lookup_context_window(
            "mimo-v2.5",
            provider_id="mimo-direct-anthropic",
        )
        == 1_000_000
    )


def test_mimo_plain_model_uses_one_m_on_openrouter_and_openai_routes(monkeypatch, tmp_path):
    import mms_launchers
    import mms_provider_profiles

    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(mms_launchers, "_load_model_context_overrides", _empty_context_overrides)
    mms_provider_profiles.load_provider_profiles.cache_clear()

    assert mms_launchers._lookup_context_window("mimo-v2.5", provider_id="openrouter") == 1_048_576
    assert mms_launchers._lookup_context_window("mimo-v2.5-pro", provider_id="openrouter") == 1_048_576
    assert mms_launchers._lookup_context_window("mimo-v2.5", provider_id="mimo-direct-openai") == 1_048_576
    assert mms_launchers._lookup_context_window("mimo-v2.5-pro", provider_id="mimo-direct-openai") == 1_048_576


def test_direct_mimo_anthropic_model_patch_does_not_invent_1m_selector():
    import mms_core

    patched = mms_core._apply_provider_model_patch(
        {
            "id": "direct-mimo",
            "anthropic_base_url": "https://token-plan-cn.xiaomimimo.com/anthropic",
        },
        {
            "models": ["mimo-v2.5", "mimo-v2.5-pro"],
            "raw_models": ["mimo-v2.5", "mimo-v2.5-pro"],
            "base_source": "remote",
        },
    )

    assert "mimo-v2.5[1m]" not in patched["models"]
    assert "mimo-v2.5-pro[1m]" not in patched["models"]


def test_direct_mimo_base_url_anthropic_model_patch_does_not_invent_1m_selector():
    import mms_core

    patched = mms_core._apply_provider_model_patch(
        {
            "id": "direct-mimo",
            "base_url": "https://token-plan-cn.xiaomimimo.com/anthropic",
        },
        {
            "models": ["mimo-v2.5", "mimo-v2.5-pro"],
            "raw_models": ["mimo-v2.5", "mimo-v2.5-pro"],
            "base_source": "remote",
        },
    )

    assert "mimo-v2.5[1m]" not in patched["models"]
    assert "mimo-v2.5-pro[1m]" not in patched["models"]


def test_openrouter_mimo_model_patch_does_not_expose_selector_alias():
    import mms_core

    patched = mms_core._apply_provider_model_patch(
        {
            "id": "openrouter",
            "openai_base_url": "https://openrouter.ai/api/v1",
        },
        {
            "models": ["mimo-v2.5", "mimo-v2.5-pro"],
            "raw_models": ["mimo-v2.5", "mimo-v2.5-pro"],
            "base_source": "remote",
        },
    )

    assert "mimo-v2.5[1m]" not in patched["models"]
    assert "mimo-v2.5-pro[1m]" not in patched["models"]


def test_exact_1m_context_override_wins_before_suffix_stripping(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(
        mms_launchers,
        "_load_model_context_overrides",
        lambda: {
            "models": {"mimo-v2.5-pro[1m]": 900_000, "mimo-v2.5-pro": 262_144},
            "provider_overrides": {},
        },
    )

    assert (
        mms_launchers._lookup_context_window(
            "mimo-v2.5-pro[1m]",
            provider_id="mimo-direct-anthropic",
        )
        == 900_000
    )


def test_mimo_1m_selector_is_not_exported_as_claude_selected_model():
    import mms_launchers

    env = {}
    mms_launchers._apply_claude_model_overrides(
        env,
        "mimo-v2.5-pro[1m]",
        enable_1m=True,
    )

    assert env["ANTHROPIC_MODEL"] == "mimo-v2.5-pro"
    assert env["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "mimo-v2.5-pro"
    assert env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "mimo-v2.5-pro"
    assert env["ANTHROPIC_REASONING_MODEL"] == "mimo-v2.5-pro"
    assert env["CLAUDE_CODE_SUBAGENT_MODEL"] == "mimo-v2.5-pro"


def test_mimo_non_pro_1m_selector_is_not_exported_as_claude_selected_model():
    import mms_launchers

    env = {}
    mms_launchers._apply_claude_model_overrides(
        env,
        "mimo-v2.5[1m]",
        enable_1m=True,
    )

    assert env["ANTHROPIC_MODEL"] == "mimo-v2.5"
    assert env["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "mimo-v2.5"
    assert env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "mimo-v2.5"
    assert env["ANTHROPIC_REASONING_MODEL"] == "mimo-v2.5"
    assert env["CLAUDE_CODE_SUBAGENT_MODEL"] == "mimo-v2.5"


def test_non_mimo_1m_selector_is_not_stripped_by_mimo_guard():
    import mms_launchers

    env = {}
    mms_launchers._apply_claude_model_overrides(
        env,
        "deepseek-v4-pro[1m]",
        enable_1m=True,
    )

    assert env["ANTHROPIC_MODEL"] == "deepseek-v4-pro[1m]"
    assert env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "deepseek-v4-pro[1m]"


def test_mimo_1m_gateway_env_keeps_selector_in_status_and_claude_shell_slots(monkeypatch, tmp_path):
    import mms_launchers

    session_home = tmp_path / "gateway-session"
    session_home.mkdir()
    real_home = tmp_path / "real-home"
    (real_home / ".local").mkdir(parents=True)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    monkeypatch.chdir(repo_dir)
    monkeypatch.setattr(
        mms_launchers,
        "_reserve_session_home",
        lambda *args, **kwargs: (str(session_home), 0, 1),
    )
    monkeypatch.setattr(mms_launchers, "_link_claude_library_entries", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mms_launchers,
        "_prepare_claude_session_tree",
        lambda _home, claude_dir, **_kwargs: os.makedirs(claude_dir, exist_ok=True),
    )
    monkeypatch.setattr(
        mms_launchers,
        "_apply_runtime_network_profile",
        lambda env, runtime, validate_proxy=True: env,
    )
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))
    monkeypatch.setattr(
        mms_launchers,
        "_claude_route_status_paths",
        lambda: [str(tmp_path / "route-status.json")],
    )
    monkeypatch.setattr(mms_launchers, "list_indexed_sessions", lambda _cli="claude": [])

    env = mms_launchers._claude_gateway_env(
        {"id": "mimo-direct-anthropic", "api_key": "sk-runtime"},
        base_url="https://relay.example.com",
        auth_token="bridge-token",
        heavy_model="claude-sonnet-4-6",
        selected_model="claude-sonnet-4-6",
        display_model="mimo-v2.5-pro[1m]",
    )
    settings = json.loads(
        (session_home / ".claude" / "settings.json").read_text(encoding="utf-8")
    )

    assert env["MMS_MODEL_NAME"] == "mimo-v2.5-pro[1m]"
    assert settings["env"]["MMS_MODEL_NAME"] == "mimo-v2.5-pro[1m]"
    for key in (
        "ANTHROPIC_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "ANTHROPIC_REASONING_MODEL",
        "CLAUDE_CODE_SUBAGENT_MODEL",
    ):
        assert env[key] == "claude-sonnet-4-6[1m]"
        assert settings["env"][key] == "claude-sonnet-4-6[1m]"


def test_mimo_base_gateway_env_keeps_status_and_claude_shell_slots(monkeypatch, tmp_path):
    import mms_launchers

    session_home = tmp_path / "gateway-session"
    session_home.mkdir()
    real_home = tmp_path / "real-home"
    (real_home / ".local").mkdir(parents=True)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    monkeypatch.chdir(repo_dir)
    monkeypatch.setattr(
        mms_launchers,
        "_reserve_session_home",
        lambda *args, **kwargs: (str(session_home), 0, 1),
    )
    monkeypatch.setattr(mms_launchers, "_link_claude_library_entries", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mms_launchers,
        "_prepare_claude_session_tree",
        lambda _home, claude_dir, **_kwargs: os.makedirs(claude_dir, exist_ok=True),
    )
    monkeypatch.setattr(
        mms_launchers,
        "_apply_runtime_network_profile",
        lambda env, runtime, validate_proxy=True: env,
    )
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))
    monkeypatch.setattr(
        mms_launchers,
        "_claude_route_status_paths",
        lambda: [str(tmp_path / "route-status.json")],
    )
    monkeypatch.setattr(mms_launchers, "list_indexed_sessions", lambda _cli="claude": [])

    env = mms_launchers._claude_gateway_env(
        {"id": "mimo-direct-anthropic", "api_key": "sk-runtime"},
        base_url="https://relay.example.com",
        auth_token="bridge-token",
        heavy_model="claude-sonnet-4-6",
        selected_model="claude-sonnet-4-6",
        display_model="mimo-v2.5-pro",
    )
    settings = json.loads(
        (session_home / ".claude" / "settings.json").read_text(encoding="utf-8")
    )

    assert env["MMS_MODEL_NAME"] == "mimo-v2.5-pro"
    assert settings["env"]["MMS_MODEL_NAME"] == "mimo-v2.5-pro"
    for key in (
        "ANTHROPIC_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "ANTHROPIC_REASONING_MODEL",
        "CLAUDE_CODE_SUBAGENT_MODEL",
    ):
        assert env[key] == "claude-sonnet-4-6[1m]"
        assert settings["env"][key] == "claude-sonnet-4-6[1m]"
