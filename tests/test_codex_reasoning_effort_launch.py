from __future__ import annotations

from contextlib import contextmanager


def test_runtime_reasoning_helpers_normalize_values():
    import mms_launchers

    assert mms_launchers._runtime_thinking_enabled({"thinking_mode": "disable"}) is False
    assert mms_launchers._runtime_thinking_enabled({"thinking_mode": "enable"}) is True
    assert mms_launchers._runtime_reasoning_effort({"reasoning_effort": "xhigh"}) == "xhigh"
    assert mms_launchers._runtime_reasoning_effort(
        {"reasoning_effort": "max"}, model_name="gpt-5.6-luna"
    ) == "max"
    assert mms_launchers._runtime_reasoning_effort(
        {"reasoning_effort": "max"}, model_name="gpt-5.5"
    ) == "xhigh"
    assert mms_launchers._runtime_reasoning_effort({"reasoning_effort": "weird"}) == "high"
    assert mms_launchers._claude_code_effort_env_value("glm-5.2", {"reasoning_effort": "xhigh"}) == "max"
    assert mms_launchers._claude_code_effort_env_value("k3[1m]", {}) == "max"
    assert mms_launchers._claude_code_effort_env_value("k3", {"reasoning_effort": "low"}) == "max"
    assert mms_launchers._claude_code_effort_env_value("kimi-k3", {"reasoning_effort": "low"}) == "max"
    assert mms_launchers._claude_code_effort_env_value("gpt-5.4", {"reasoning_effort": "xhigh"}) == ""


def test_claude_kimi_k3_context_env_follows_user_policy(monkeypatch):
    """K3 has no MMS-specific ``[1m]`` selector: user policy wins for every alias."""
    import mms_launchers

    import mms_capability_resolver
    import mms_context_window

    monkeypatch.setattr(
        mms_context_window,
        "load_model_context_overrides",
        lambda: {"models": {}, "provider_overrides": {}},
    )

    def fake_capabilities(model_name, *, provider_id="", **_kwargs):
        if str(model_name).lower() == "k3":
            return {
                "context_window_tokens": 1_000_000,
                "sources": {"context_window_tokens": "model_policy"},
            }
        return {"context_window_tokens": 0, "sources": {"context_window_tokens": "conservative_fallback"}}

    monkeypatch.setattr(mms_capability_resolver, "resolve_model_capabilities", fake_capabilities)

    assert mms_launchers._lookup_context_window("k3", provider_id="kimi") == 1_000_000
    assert mms_launchers._lookup_context_window("k3[1m]", provider_id="kimi") == 1_000_000


def test_claude_kimi_k3_without_policy_uses_profile_one_million_window(monkeypatch):
    """Without a policy the provider profile decides, and it records K3 as native 1M."""
    import mms_launchers

    import mms_capability_resolver
    import mms_context_window

    monkeypatch.setattr(
        mms_context_window,
        "load_model_context_overrides",
        lambda: {"models": {}, "provider_overrides": {}},
    )
    monkeypatch.setattr(mms_capability_resolver, "_load_default_approved_facts_shared", lambda: {})
    monkeypatch.setattr(mms_capability_resolver, "load_default_model_policy", lambda: {})

    assert mms_launchers._lookup_context_window("k3", provider_id="kimi") == 1_048_576
    assert mms_launchers._lookup_context_window("k3[1m]", provider_id="kimi") == 1_048_576


def test_get_export_env_for_claude_kimi_k3_sets_effort_and_context(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(mms_launchers, "validate_provider_for_cli", lambda *_args, **_kwargs: None)
    runtime = {
        "id": "kimi",
        "auth_mode": "api_key",
        "api_key": "sk-kimi",
        "anthropic_base_url": "https://api.kimi.com/coding/",
        "protocols": ["anthropic_messages"],
        "supported_clis": ["claude"],
    }

    exports = mms_launchers.get_export_env("claude", runtime, model_info={"model": "k3[1m]"})

    assert exports["CLAUDE_CODE_EFFORT_LEVEL"] == "max"
    assert exports["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] == "1048576"
    assert exports["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] == "1048576"
    assert exports["CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE"] == "1045576"


def test_claude_glm_1m_context_sets_client_cap_without_selector():
    import mms_launchers

    env = {}
    mms_launchers._apply_claude_context_env_overrides(
        env,
        context_window=1_000_000,
        model_names=("glm-5.2",),
    )

    assert env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] == "1000000"
    assert env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] == "1000000"
    assert env["CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE"] == "997000"
    assert all("[1m]" not in value for value in env.values())


def test_claude_glm_below_1m_still_states_its_own_window():
    """#230: a known window is stated whatever its size, not only at 1M.

    Claude Code's built-in cap describes Anthropic's models, so leaving it in
    place for a routed GLM meant compacting at the client's number rather than
    the model's.
    """
    import mms_launchers

    env = {}
    mms_launchers._apply_claude_context_env_overrides(
        env,
        context_window=200_000,
        model_names=("glm-5.2",),
    )

    assert env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] == "200000"


def test_default_gpt_reasoning_effort_uses_xhigh_for_source_checkout(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(mms_launchers, "_real_user_home", lambda: "/tmp/real-home")

    assert mms_launchers._default_gpt_reasoning_effort(module_path="/worktrees/mms/mms_launchers.py") == "xhigh"


def test_default_gpt_reasoning_effort_keeps_high_for_installed_layout(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(mms_launchers, "_real_user_home", lambda: "/tmp/real-home")

    assert mms_launchers._default_gpt_reasoning_effort(module_path="/tmp/real-home/.mms/mms_launchers.py") == "high"


def test_mms_core_prefers_xhigh_for_gpt_in_source_checkout(monkeypatch):
    import mms_capability_resolver
    import mms_core

    monkeypatch.setattr(mms_core, "resolve_real_user_home", lambda env=None: "/tmp/real-home")
    monkeypatch.setattr(mms_capability_resolver, "load_default_model_policy", lambda: {})

    assert mms_core._default_reasoning_effort_for_model_info({"model": "gpt-5.4"}) == "xhigh"


def test_mms_core_uses_model_policy_reasoning_effort(monkeypatch):
    import mms_capability_resolver
    import mms_core

    monkeypatch.setattr(
        mms_capability_resolver,
        "load_default_model_policy",
        lambda: {"models": {"glm-5.2": {"capabilities": {"reasoning_effort": "max"}}}},
    )

    assert mms_core._default_reasoning_effort_for_model_info({"model": "glm-5.2"}) == "xhigh"


def test_mms_core_keeps_high_for_installed_layout(monkeypatch):
    import mms_core

    monkeypatch.setattr(mms_core, "resolve_real_user_home", lambda env=None: "/tmp/real-home")

    assert mms_core._default_gpt_reasoning_effort(module_path="/tmp/real-home/.mms/mms_core.py") == "high"


def test_launch_codex_passes_reasoning_effort_to_codex_config(monkeypatch):
    import mms_launchers
    import mms_tui

    captured = {}

    monkeypatch.setattr(mms_launchers, "_ensure_bridge_helpers", lambda: None)
    monkeypatch.setattr(mms_launchers, "_ensure_speed_stats", lambda: None)
    monkeypatch.setattr(mms_launchers, "gateway_health_check", lambda runtime: None)
    monkeypatch.setattr(mms_launchers, "_resolve_model", lambda model_info: "gpt-5.4")
    monkeypatch.setattr(mms_launchers, "_openai_base_url", lambda runtime: "https://example.test/v1")
    monkeypatch.setattr(mms_launchers, "build_provider_speed_scope", lambda runtime: None)
    monkeypatch.setattr(mms_launchers, "_probe_models", lambda runtime, emit_output=False: {"models": ["gpt-5.4"]})
    monkeypatch.setattr(mms_launchers, "_codex_gateway_env", lambda runtime, base_url, model_info=None: {"PATH": ""})
    monkeypatch.setattr(mms_launchers, "_resolve_codex_responses_fallback_routes", lambda runtime, model: [])
    monkeypatch.setattr(
        mms_launchers,
        "_resolve_codex_responses_fallback_routes",
        lambda runtime, model: [{"provider_id": "codex-fallback", "gateway_url": "https://fallback.test/v1"}],
    )

    def fake_select_reasoning_effort_tui(default="medium", **kwargs):
        captured["default_effort"] = default
        captured["options"] = kwargs.get("options")
        return "xhigh"

    monkeypatch.setattr(mms_tui, "select_reasoning_effort_tui", fake_select_reasoning_effort_tui)

    @contextmanager
    def fake_bridge(gateway_url, api_key, **kwargs):
        captured["bridge_kwargs"] = kwargs
        yield {"base_url": "http://127.0.0.1:8765", "api_key": "bridge-key"}

    def fake_exec_or_run(cmd, env, once=False, force_subprocess=False, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = env
        captured["once"] = once
        captured["force_subprocess"] = force_subprocess
        captured["exit_callback"] = kwargs.get("exit_callback")

    monkeypatch.setattr(mms_launchers, "codex_responses_bridge", fake_bridge)
    monkeypatch.setattr(mms_launchers, "_exec_or_run", fake_exec_or_run)

    runtime = {
        "id": "openai-main",
        "auth_mode": "api_key",
        "api_key": "sk-test",
    }
    model_info = {"model": "gpt-5.4"}

    mms_launchers.launch_codex(model_info, runtime, once=True)

    assert captured["bridge_kwargs"]["reasoning_effort"] == "xhigh"
    assert captured["bridge_kwargs"]["native_fallback_routes"] == [
        {"provider_id": "codex-fallback", "gateway_url": "https://fallback.test/v1"}
    ]
    assert captured["default_effort"] == "xhigh"
    assert [value for value, _label in captured["options"]] == ["low", "medium", "high", "xhigh"]
    assert '-c' in captured["cmd"]
    assert 'model_reasoning_effort="xhigh"' in captured["cmd"]
    assert captured["force_subprocess"] is True


def test_launch_codex_uses_runtime_thinking_and_effort_without_prompt(monkeypatch):
    import mms_launchers
    import mms_tui

    captured = {}

    monkeypatch.setattr(mms_launchers, "_ensure_bridge_helpers", lambda: None)
    monkeypatch.setattr(mms_launchers, "_ensure_speed_stats", lambda: None)
    monkeypatch.setattr(mms_launchers, "gateway_health_check", lambda runtime: None)
    monkeypatch.setattr(mms_launchers, "_resolve_model", lambda model_info: "gpt-5.4")
    monkeypatch.setattr(mms_launchers, "_openai_base_url", lambda runtime: "https://example.test/v1")
    monkeypatch.setattr(mms_launchers, "build_provider_speed_scope", lambda runtime: None)
    monkeypatch.setattr(mms_launchers, "_probe_models", lambda runtime, emit_output=False: {"models": ["gpt-5.4"]})
    monkeypatch.setattr(mms_launchers, "_codex_gateway_env", lambda runtime, base_url, model_info=None: {"PATH": ""})
    monkeypatch.setattr(mms_launchers, "_resolve_codex_responses_fallback_routes", lambda runtime, model: [])
    monkeypatch.setattr(
        mms_tui,
        "select_reasoning_effort_tui",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected prompt")),
    )

    @contextmanager
    def fake_bridge(gateway_url, api_key, **kwargs):
        captured["bridge_kwargs"] = kwargs
        yield {"base_url": "http://127.0.0.1:8765", "api_key": "bridge-key"}

    def fake_exec_or_run(cmd, env, once=False, force_subprocess=False, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = env
        captured["once"] = once
        captured["force_subprocess"] = force_subprocess
        captured["exit_callback"] = kwargs.get("exit_callback")

    monkeypatch.setattr(mms_launchers, "codex_responses_bridge", fake_bridge)
    monkeypatch.setattr(mms_launchers, "_exec_or_run", fake_exec_or_run)

    runtime = {
        "id": "openai-main",
        "auth_mode": "api_key",
        "api_key": "sk-test",
        "thinking_mode": "disable",
        "reasoning_effort": "medium",
    }

    mms_launchers.launch_codex({"model": "gpt-5.4"}, runtime, once=True)

    assert captured["bridge_kwargs"]["reasoning_enabled"] is False
    assert captured["bridge_kwargs"]["reasoning_effort"] == "medium"
    assert all("model_reasoning_effort" not in item for item in captured["cmd"])


def test_launch_codex_bypass_mode_skips_hook_review_prompt(monkeypatch):
    import mms_launchers
    import mms_tui

    captured = {}

    monkeypatch.setattr(mms_launchers, "_ensure_bridge_helpers", lambda: None)
    monkeypatch.setattr(mms_launchers, "_ensure_speed_stats", lambda: None)
    monkeypatch.setattr(mms_launchers, "gateway_health_check", lambda runtime: None)
    monkeypatch.setattr(mms_launchers, "_resolve_model", lambda model_info: "gpt-5.4")
    monkeypatch.setattr(mms_launchers, "_openai_base_url", lambda runtime: "https://example.test/v1")
    monkeypatch.setattr(mms_launchers, "build_provider_speed_scope", lambda runtime: None)
    monkeypatch.setattr(mms_launchers, "_probe_models", lambda runtime, emit_output=False: {"models": ["gpt-5.4"]})
    monkeypatch.setattr(mms_launchers, "_codex_gateway_env", lambda runtime, base_url, model_info=None: {"PATH": ""})
    monkeypatch.setattr(mms_launchers, "_resolve_codex_responses_fallback_routes", lambda runtime, model: [])
    monkeypatch.setattr(
        mms_tui,
        "select_reasoning_effort_tui",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected prompt")),
    )

    @contextmanager
    def fake_bridge(gateway_url, api_key, **kwargs):
        yield {"base_url": "http://127.0.0.1:8765", "api_key": "bridge-key"}

    def fake_exec_or_run(cmd, env, once=False, force_subprocess=False, **kwargs):
        captured["cmd"] = cmd

    monkeypatch.setattr(mms_launchers, "codex_responses_bridge", fake_bridge)
    monkeypatch.setattr(mms_launchers, "_exec_or_run", fake_exec_or_run)

    runtime = {
        "id": "openai-main",
        "auth_mode": "api_key",
        "api_key": "sk-test",
        "bypass": True,
        "thinking_mode": "disable",
        "reasoning_effort": "medium",
    }

    mms_launchers.launch_codex({"model": "gpt-5.4"}, runtime, once=True)

    assert "--dangerously-bypass-approvals-and-sandbox" in captured["cmd"]
    assert "--dangerously-bypass-hook-trust" in captured["cmd"]


def test_gpt_explicit_model_effort_precedes_checkout_default(monkeypatch):
    import mms_capability_resolver
    import mms_core
    monkeypatch.setattr(mms_capability_resolver, "load_default_model_policy", lambda: {"models": {"gpt-5": {"capabilities": {"reasoning_effort": "low"}}}})
    assert mms_core._default_reasoning_effort_for_model_info({"model": "gpt-5"}) == "low"
    assert mms_core._default_reasoning_effort_for_model_info({"model": "gpt-unconfigured"}) == mms_core._default_gpt_reasoning_effort()


def _isolated_codex_gateway(monkeypatch, tmp_path):
    """Run the Codex gateway writer against a throwaway config root."""
    import mms_launchers

    real_home = tmp_path / "real-home"
    config_root = real_home / ".config" / "mms-next"
    config_root.mkdir(parents=True)
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(config_root))
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))
    for name in (
        "_cleanup_stale_sessions",
        "_link_shared_dotfiles",
        "_sync_codex_session_claude_json",
        "_install_session_command_wrappers",
        "_install_session_packet_env",
    ):
        monkeypatch.setattr(mms_launchers, name, lambda *a, **k: None)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=False: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_locale_profile", lambda env, runtime: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_ip_stack_profile", lambda env, runtime: env)
    monkeypatch.setattr(mms_launchers, "_install_host_context_env", lambda *a, **k: {})
    monkeypatch.setattr(mms_launchers, "_build_codex_session_hooks", lambda *a, **k: {"hooks": {}})
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    return mms_launchers


def test_codex_gateway_context_window_only_widens_unknown_models():
    import mms_launchers

    kimi = {"id": "kimi"}
    for alias in ("k3", "k3[1m]", "kimi-k3"):
        assert mms_launchers._codex_gateway_context_window(kimi, {"model": alias}) == 1_048_576, alias

    # Codex knows its own catalog, including an effective window below the
    # model's maximum. Overriding those would push past a deliberate limit.
    for openai_model in ("gpt-5.5", "gpt-5.3-codex", "GPT-5.4"):
        assert mms_launchers._codex_gateway_context_window(kimi, {"model": openai_model}) is None, openai_model

    # Below 1M Codex's own default stands; we only ever widen.
    assert mms_launchers._codex_gateway_context_window(kimi, {"model": "kimi-for-coding"}) is None
    assert mms_launchers._codex_gateway_context_window(kimi, {"model": ""}) is None
    assert mms_launchers._codex_gateway_context_window(kimi, None) is None


def test_codex_gateway_config_carries_the_one_million_window(monkeypatch, tmp_path):
    """K3 is a 1M model, and Codex has no way to know that on its own.

    Every other harness is told: Claude Code through its context env, Pi
    through models.json. Codex was the one that received nothing, so it fell
    back to its default for an unknown routed model and compacted early.
    """
    from pathlib import Path

    mms_launchers = _isolated_codex_gateway(monkeypatch, tmp_path)
    runtime = {"id": "kimi", "api_key": "sk-test", "nsr_mode": "disable"}

    env = mms_launchers._codex_gateway_env(runtime, "https://relay.example.com", model_info={"model": "k3"})
    config = Path(env["CODEX_HOME"], "config.toml").read_text(encoding="utf-8")
    assert "model_context_window = 1048576" in config

    # The gateway config is reused across sessions, so switching models must
    # take the window back out rather than leave K3's 1M on a GPT session.
    env = mms_launchers._codex_gateway_env(runtime, "https://relay.example.com", model_info={"model": "gpt-5.4"})
    config = Path(env["CODEX_HOME"], "config.toml").read_text(encoding="utf-8")
    assert "model_context_window" not in config
    assert 'base_url = "https://relay.example.com"' in config
