from __future__ import annotations

from contextlib import contextmanager


def test_runtime_reasoning_helpers_normalize_values():
    import mms_launchers

    assert mms_launchers._runtime_thinking_enabled({"thinking_mode": "disable"}) is False
    assert mms_launchers._runtime_thinking_enabled({"thinking_mode": "enable"}) is True
    assert mms_launchers._runtime_reasoning_effort({"reasoning_effort": "xhigh"}) == "xhigh"
    assert mms_launchers._runtime_reasoning_effort({"reasoning_effort": "weird"}) == "high"
    assert mms_launchers._claude_code_effort_env_value("glm-5.2", {"reasoning_effort": "xhigh"}) == "max"
    assert mms_launchers._claude_code_effort_env_value("k3[1m]", {}) == "max"
    assert mms_launchers._claude_code_effort_env_value("k3", {"reasoning_effort": "low"}) == "max"
    assert mms_launchers._claude_code_effort_env_value("kimi-k3", {"reasoning_effort": "low"}) == "max"
    assert mms_launchers._claude_code_effort_env_value("gpt-5.4", {"reasoning_effort": "xhigh"}) == ""


def test_claude_kimi_k3_context_env_uses_selector_window(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(
        mms_launchers,
        "_load_model_context_overrides",
        lambda: {"models": {}, "provider_overrides": {}},
    )

    def fake_capability_context_window(model_name, *, provider_id=None, accepted_sources=None):
        if str(model_name).lower() == "k3" and accepted_sources == {"model_policy", "manual_override"}:
            return 1_000_000
        return None

    monkeypatch.setattr(mms_launchers, "_capability_context_window", fake_capability_context_window)

    assert mms_launchers._lookup_context_window("k3", provider_id="kimi") == 262_144
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

    def fake_select_reasoning_effort_tui(default="medium"):
        captured["default_effort"] = default
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
