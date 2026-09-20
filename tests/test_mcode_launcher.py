"""Tests for the mcode (MiniMax Code) launcher integration."""


def test_core_mcode_is_cli_but_not_provider_supported():
    import mms_core

    provider = {
        "id": "default",
        "name": "Default",
        "enabled": True,
        "api_key": "sk-test",
        "base_url": "https://example.test/v1",
        "openai_base_url": "https://example.test/v1",
        "protocols": ["openai_chat_completions"],
        "supported_clis": ["claude", "codex", "opencode", "mcode"],
    }

    assert "mcode" in mms_core.CLI_NAMES
    assert "mcode" in mms_core.OAUTH_CAPABLE_CLIS
    # mcode manages its own MiniMax OAuth; it never launches through a gateway provider.
    assert mms_core._provider_supports_cli_name(provider, "mcode") is False


def test_mcode_visible_when_binary_exists(monkeypatch):
    import mms_core

    provider = {
        "id": "default",
        "name": "Default",
        "enabled": True,
        "api_key": "sk-test",
        "base_url": "https://example.test/v1",
        "openai_base_url": "https://example.test/v1",
        "protocols": ["openai_chat_completions"],
        "supported_clis": ["claude", "codex", "opencode"],
    }

    monkeypatch.setattr(mms_core, "check_cli_installed", lambda cli_name: False)
    assert "mcode" not in mms_core._resolve_visible_clis({"accounts": []}, provider, ["gpt-5"])

    monkeypatch.setattr(mms_core, "check_cli_installed", lambda cli_name: cli_name == "mcode")
    assert "mcode" in mms_core._resolve_visible_clis({"accounts": []}, provider, ["gpt-5"])


def test_mcode_official_account_menu_lists_oauth_accounts():
    import mms_core

    cfg = {
        "accounts": [
            {"id": "mcode-work", "name": "Work", "cli": "mcode", "enabled": True, "priority": 100},
            {"id": "mcode-home", "name": "Home", "cli": "mcode", "enabled": True, "priority": 100},
            {"id": "mcode-disabled", "name": "Disabled", "cli": "mcode", "enabled": False},
            {"id": "agy-other", "name": "Other", "cli": "agy", "enabled": True},
        ],
        "account": {"defaults": {"mcode": "mcode-home"}},
    }

    options = mms_core._official_account_menu_options(cfg, "mcode")

    assert [option["id"] for option in options] == ["mcode-home", "mcode-work"]
    assert options[0]["badge"] == "*"


def test_launch_mcode_rejects_provider_runtime(monkeypatch):
    import mms_launchers
    import pytest

    with pytest.raises(SystemExit):
        mms_launchers.launch_mcode({}, {"auth_mode": "api_key", "id": "gw"}, once=True)


def test_launch_mcode_tui_mode_keeps_default_permission(monkeypatch):
    import mms_launchers

    calls = {}

    def fake_account_env(runtime, *, validate_proxy=True, model_info=None):
        return {
            "HOME": "/tmp/mcode-account/s/123",
            "MMS_SESSION_HOME": "/tmp/mcode-account/s/123",
            "XDG_CONFIG_HOME": "/tmp/mcode-account/s/123/.config",
            "MMS_REAL_HOME": "/tmp/real-home",
            "REAL_HOME": "/tmp/real-home",
            "ORIGINAL_HOME": "/tmp/real-home",
        }

    def fake_prepare(runtime, env, cli_name):
        calls["prepare"] = (runtime, env, cli_name)
        return {}

    def fake_exec(cmd, env, once):
        calls["exec"] = (cmd, env, once)

    monkeypatch.setattr(mms_launchers, "_account_env", fake_account_env)
    monkeypatch.setattr(mms_launchers, "_prepare_oauth_home_context", fake_prepare)
    monkeypatch.setattr(mms_launchers, "_exec_or_run", fake_exec)

    runtime = {
        "id": "mcode-main",
        "cli": "mcode",
        "auth_mode": "oauth",
        "home_dir": "/tmp/mcode-account",
        "bypass": True,
    }
    mms_launchers.launch_mcode({}, runtime, once=False)

    assert calls["prepare"][2] == "mcode"
    # mcode TUI has no permission flag; bypass must NOT inject one.
    assert calls["exec"][0] == ["mcode"]
    assert calls["exec"][2] is False


def test_launch_mcode_once_mode_maps_bypass_to_permission_full(monkeypatch):
    import mms_launchers

    calls = {}

    def fake_account_env(runtime, *, validate_proxy=True, model_info=None):
        return {
            "HOME": "/tmp/mcode-account/s/123",
            "MMS_SESSION_HOME": "/tmp/mcode-account/s/123",
            "XDG_CONFIG_HOME": "/tmp/mcode-account/s/123/.config",
            "MMS_REAL_HOME": "/tmp/real-home",
            "REAL_HOME": "/tmp/real-home",
            "ORIGINAL_HOME": "/tmp/real-home",
        }

    monkeypatch.setattr(mms_launchers, "_account_env", fake_account_env)
    monkeypatch.setattr(mms_launchers, "_prepare_oauth_home_context", lambda *a, **k: {})
    monkeypatch.setattr(mms_launchers, "_exec_or_run", lambda cmd, env, once: calls.update(cmd=cmd, once=once))

    runtime = {
        "id": "mcode-main",
        "cli": "mcode",
        "auth_mode": "oauth",
        "home_dir": "/tmp/mcode-account",
        "bypass": True,
    }
    mms_launchers.launch_mcode({}, runtime, once=True)
    assert calls["cmd"] == ["mcode", "exec", "--permission", "full"]
    assert calls["once"] is True

    # bypass off: exec without permission flag
    calls.clear()
    runtime["bypass"] = False
    mms_launchers.launch_mcode({}, runtime, once=True)
    assert calls["cmd"] == ["mcode", "exec"]


def test_confirm_tui_offers_bypass_for_mcode():
    import inspect

    import mms_tui

    src = inspect.getsource(mms_tui.confirm_tui)
    assert '"mcode"' in src
