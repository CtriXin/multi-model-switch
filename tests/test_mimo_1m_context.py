from __future__ import annotations

import json
import os

import mms_capability_resolver
import mms_context_window


def _empty_context_overrides():
    return {"models": {}, "provider_overrides": {}}


def _anthropic_mimo_runtime():
    """The channel MiMo documents for Claude Code: the Anthropic-compatible one."""
    return {
        "id": "mimo-direct-anthropic",
        "name": "MiMo Direct",
        "enabled": True,
        "auth_mode": "api_key",
        "api_key": "sk-test",
        "anthropic_base_url": "https://api.xiaomimimo.com/anthropic",
        "protocols": ["anthropic_messages"],
        "supported_clis": ["claude", "codex", "pi", "opencode"],
    }


def _conservative_capabilities(*_args, **_kwargs):
    return {
        "context_window_tokens": 8_192,
        "sources": {"context_window_tokens": "conservative_fallback"},
    }


def test_mimo_pro_1m_suffix_uses_one_m_context(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(mms_context_window, "load_model_context_overrides", _empty_context_overrides)

    assert (
        mms_launchers._lookup_context_window(
            "mimo-v2.5-pro[1m]",
            provider_id="mimo-direct-anthropic",
        )
        == 1_048_576
    )
    assert (
        mms_launchers._effective_context_window(
            "mimo-v2.5-pro[1m]",
            provider_id="mimo-direct-anthropic",
        )
        == 1_048_576
    )


def test_mimo_non_pro_1m_suffix_uses_one_m_context(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(mms_context_window, "load_model_context_overrides", _empty_context_overrides)

    assert (
        mms_launchers._lookup_context_window(
            "mimo-v2.5[1m]",
            provider_id="mimo-direct-anthropic",
        )
        == 1_048_576
    )


def test_mimo_pro_without_1m_suffix_keeps_safe_context(monkeypatch):
    """MiMo's Anthropic endpoint runs the plain id in 256K mode.

    The `[1m]` suffix is what asks for the extended context there, so telling
    Claude Code 1M for the plain name would push requests past what the server
    honours. The fact is provider-specific, so it is profile data
    (the `mimo` profile), reached here through the real matcher.
    """
    import mms_launchers

    monkeypatch.setattr(mms_context_window, "load_model_context_overrides", _empty_context_overrides)

    assert (
        mms_launchers._lookup_context_window(
            "mimo-v2.5-pro",
            provider_id="mimo-direct-anthropic",
        )
        == 262_144
    )
    assert (
        mms_context_window.resolve_context_window(
            "mimo-v2.5-pro",
            runtime=_anthropic_mimo_runtime(),
        )
        == 262_144
    )


def test_mimo_without_1m_suffix_keeps_safe_context_on_anthropic(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(mms_context_window, "load_model_context_overrides", _empty_context_overrides)

    assert (
        mms_launchers._lookup_context_window(
            "mimo-v2.5",
            provider_id="mimo-direct-anthropic",
        )
        == 262_144
    )
    assert (
        mms_context_window.resolve_context_window(
            "mimo-v2.5",
            runtime=_anthropic_mimo_runtime(),
        )
        == 262_144
    )


def test_the_anthropic_route_and_the_openai_routes_pick_different_profiles():
    """The 256K plain mode is provider data, so the matcher has to separate them.

    The `mimo` profile answers for the Anthropic endpoint and for any MiMo
    channel that does not say which endpoint it is; the OpenAI-style routes have
    their own profiles, where the plain name really is the 1M model.
    """
    import mms_provider_profiles

    for provider_id, base_url in (
        ("mimo-direct-anthropic", "https://api.xiaomimimo.com/anthropic"),
        ("mimo-direct-anthropic", ""),
        ("mimo-anthropic", "https://api.xiaomimimo.com/anthropic"),
    ):
        profile_id, _profile = mms_provider_profiles.resolve_provider_profile(
            provider_id=provider_id, base_url=base_url, model_name="mimo-v2.5"
        )
        assert profile_id == "mimo", (provider_id, base_url)

    for provider_id in ("mimo-openai", "mimo-direct-openai", "xiaomi-openai", "openai-mimo"):
        profile_id, _profile = mms_provider_profiles.resolve_provider_profile(
            provider_id=provider_id,
            base_url="https://api.xiaomimimo.com/v1",
            model_name="mimo-v2.5",
        )
        assert profile_id == "mimo-openai", provider_id
        assert (
            mms_context_window.resolve_context_window(
                "mimo-v2.5",
                provider_id=provider_id,
                runtime={"id": provider_id, "openai_base_url": "https://api.xiaomimimo.com/v1"},
            )
            == 1_048_576
        ), provider_id


def test_every_harness_gets_the_same_mimo_window_on_the_anthropic_route(monkeypatch):
    """Per (model, provider): 256K for the plain id, 1M for the selector."""
    import mms_launchers
    import mms_pi_support

    monkeypatch.setattr(mms_context_window, "load_model_context_overrides", _empty_context_overrides)
    # Answer from the repository's profiles alone: whether this machine has an
    # approved bundle must not decide what the assertion sees.
    monkeypatch.setattr(mms_capability_resolver, "_load_default_approved_facts_shared", lambda: {})
    monkeypatch.setattr(mms_capability_resolver, "load_default_model_policy", lambda: {})
    runtime = _anthropic_mimo_runtime()
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda _runtime, emit_output=False: {
            "models": ["mimo-v2.5", "mimo-v2.5[1m]", "mimo-v2.5-pro", "mimo-v2.5-pro[1m]"]
        },
    )

    for model, expected in (
        ("mimo-v2.5", 262_144),
        ("mimo-v2.5-pro", 262_144),
        ("mimo-v2.5[1m]", 1_048_576),
        ("mimo-v2.5-pro[1m]", 1_048_576),
    ):
        env = {}
        mms_launchers._apply_claude_context_env_overrides(
            env,
            context_window=mms_launchers._effective_context_window(model, provider_id=runtime["id"]),
            model_names=(model,),
        )
        assert int(env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"]) == expected, model
        assert mms_pi_support._pi_model_entry(runtime, model)["model"]["contextWindow"] == expected, model
        assert mms_launchers._opencode_model_config(runtime, model)["limit"]["context"] == expected, model
        codex = mms_launchers._codex_gateway_context_window(runtime, {"model": model})
        # Codex is told only about windows past its own floor; when it is told,
        # it is the same number.
        assert codex in (None, expected), model


def test_mimo_falls_back_to_the_shared_data_file_without_a_profile(monkeypatch):
    """A channel whose profile says nothing still gets the documented window."""
    import mms_launchers

    monkeypatch.setattr(mms_context_window, "load_model_context_overrides", _empty_context_overrides)
    monkeypatch.setattr(mms_capability_resolver, "resolve_model_capabilities", _conservative_capabilities)

    assert mms_launchers._lookup_context_window("mimo-v2-pro", provider_id="some-relay") == 262_144


def test_mimo_one_m_policy_shortcut_enables_plain_model_1m(monkeypatch, tmp_path):
    import mms_launchers

    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(mms_context_window, "load_model_context_overrides", _empty_context_overrides)
    (tmp_path / "model-policy.json").write_text(
        json.dumps(
            {
                "models": {
                    "mimo-v2.5": {
                        "capabilities": {
                            "one_m_context": True,
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


def test_mimo_context_policy_enables_plain_model_1m(monkeypatch, tmp_path):
    import mms_launchers

    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(mms_context_window, "load_model_context_overrides", _empty_context_overrides)
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


def test_mimo_approved_capability_enables_plain_model_1m_before_safe_cap(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(mms_context_window, "load_model_context_overrides", _empty_context_overrides)

    def fake_resolve_model_capabilities(model_name, *, provider_id="", **_kwargs):
        assert model_name == "mimo-v2.5"
        assert provider_id == "newapi-tencent"
        return {
            "context_window_tokens": 1_048_576,
            "sources": {"context_window_tokens": "approved_facts"},
        }

    monkeypatch.setattr(mms_capability_resolver, "resolve_model_capabilities", fake_resolve_model_capabilities)

    assert (
        mms_launchers._lookup_context_window(
            "mimo-v2.5",
            provider_id="newapi-tencent",
        )
        == 1_048_576
    )


def test_mimo_plain_model_uses_one_m_on_openrouter_and_openai_routes(monkeypatch, tmp_path):
    import mms_launchers
    import mms_provider_profiles

    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(mms_context_window, "load_model_context_overrides", _empty_context_overrides)
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
        mms_context_window,
        "load_model_context_overrides",
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


def test_bridge_thinking_support_reads_model_policy(monkeypatch, tmp_path):
    import mms_bridge

    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    (tmp_path / "model-policy.json").write_text(
        json.dumps({"models": {"mimo-v2.5": {"capabilities": {"thinking": True}}}}),
        encoding="utf-8",
    )

    assert mms_bridge._domestic_model_supports_thinking("mimo-v2.5") is True
