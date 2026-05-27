from __future__ import annotations

import json
from pathlib import Path


def test_contract_codex_bypass_mode_always_skips_hook_review_prompt():
    import mms_launchers

    cmd = ["codex"]

    mms_launchers._append_codex_bypass_flags(cmd, {"bypass": True})

    assert "--dangerously-bypass-approvals-and-sandbox" in cmd
    assert "--dangerously-bypass-hook-trust" in cmd


def test_contract_real_home_hook_trust_wins_over_stale_session(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_hooks_path = str(real_home / ".codex" / "hooks.json")
    stale_hooks_path = str(tmp_path / "gateway" / "s" / "old" / ".codex" / "hooks.json")
    target_hooks_path = str(tmp_path / "gateway" / ".codex" / "hooks.json")
    real_hooks = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "/tmp/nsr.sh"}]},
                {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "/tmp/scmp.py"}]},
            ]
        }
    }
    target_hooks = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "/tmp/scmp.py"}]},
                {"matcher": "*", "hooks": [{"type": "command", "command": "/tmp/nsr.sh"}]},
            ]
        }
    }
    stale_config = (
        f'[hooks.state."{stale_hooks_path}:pre_tool_use:1:0"]\n'
        'trusted_hash = "sha256:stale-session"\n'
    )
    real_config = (
        f'[hooks.state."{real_hooks_path}:pre_tool_use:1:0"]\n'
        'trusted_hash = "sha256:real-home"\n'
    )

    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))

    rendered = mms_launchers._append_codex_session_hook_trust_states(
        f'[hooks.state."{target_hooks_path}:pre_tool_use:0:0"]\ntrusted_hash = "sha256:old-target"\n',
        target_hooks_path=target_hooks_path,
        target_hooks=target_hooks,
        trust_config_texts=[stale_config, real_config],
        source_hook_payloads_by_path={
            stale_hooks_path: real_hooks,
            real_hooks_path: real_hooks,
        },
    )

    assert f'[hooks.state."{target_hooks_path}:pre_tool_use:0:0"]' in rendered
    assert 'trusted_hash = "sha256:real-home"' in rendered
    assert "sha256:stale-session" not in rendered
    assert "sha256:old-target" not in rendered


def test_contract_codex_gateway_keeps_stable_codex_home(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_codex = real_home / ".codex"
    real_codex.mkdir(parents=True)
    (real_codex / "config.toml").write_text('base_url = "https://api.example.com"\n', encoding="utf-8")
    (real_codex / "hooks.json").write_text('{"hooks":{}}\n', encoding="utf-8")
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    hooks_payload = {
        "hooks": {
            "SessionStart": [
                {"hooks": [{"type": "command", "command": "/tmp/notify.sh"}]},
            ]
        }
    }

    pid = {"value": 111}
    monkeypatch.chdir(repo_dir)
    monkeypatch.setattr(mms_launchers.os, "getpid", lambda: pid["value"])
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_sync_codex_session_claude_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=False: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_locale_profile", lambda env, runtime: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_ip_stack_profile", lambda env, runtime: env)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_install_host_context_env", lambda *args, **kwargs: {})
    monkeypatch.setattr(mms_launchers, "_install_session_packet_env", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_build_codex_session_hooks", lambda *args, **kwargs: hooks_payload)
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))

    env1 = mms_launchers._codex_gateway_env(
        {"id": "relay-a", "api_key": "sk-runtime", "nsr_mode": "disable"},
        "https://relay.example.com",
        model_info={"model": "gpt-5.5"},
    )
    pid["value"] = 222
    env2 = mms_launchers._codex_gateway_env(
        {"id": "relay-a", "api_key": "sk-runtime", "nsr_mode": "disable"},
        "https://relay.example.com",
        model_info={"model": "gpt-5.5"},
    )

    gateway_codex = real_home / ".config" / "mms" / "codex-gateway" / ".codex"
    assert Path(env1["CODEX_HOME"]) == gateway_codex
    assert Path(env2["CODEX_HOME"]) == gateway_codex
    assert Path(env1["MMS_SESSION_HOME"]) != Path(env2["MMS_SESSION_HOME"])
    assert (Path(env1["MMS_SESSION_HOME"]) / ".codex").resolve() == gateway_codex
    assert (Path(env2["MMS_SESSION_HOME"]) / ".codex").resolve() == gateway_codex
    assert json.loads((gateway_codex / "hooks.json").read_text(encoding="utf-8")) == hooks_payload
