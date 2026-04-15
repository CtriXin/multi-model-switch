from __future__ import annotations

from contextlib import contextmanager


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
    monkeypatch.setattr(mms_launchers, "_codex_gateway_env", lambda runtime, base_url: {"PATH": ""})

    def fake_select_reasoning_effort_tui(default="medium"):
        captured["default_effort"] = default
        return "xhigh"

    monkeypatch.setattr(mms_tui, "select_reasoning_effort_tui", fake_select_reasoning_effort_tui)

    @contextmanager
    def fake_bridge(gateway_url, api_key, **kwargs):
        captured["bridge_kwargs"] = kwargs
        yield {"base_url": "http://127.0.0.1:8765", "api_key": "bridge-key"}

    def fake_exec_or_run(cmd, env, once=False, force_subprocess=False):
        captured["cmd"] = cmd
        captured["env"] = env
        captured["once"] = once
        captured["force_subprocess"] = force_subprocess

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
    assert captured["default_effort"] == "high"
    assert '-c' in captured["cmd"]
    assert 'model_reasoning_effort="xhigh"' in captured["cmd"]
    assert captured["force_subprocess"] is True
