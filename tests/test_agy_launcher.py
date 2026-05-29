import os
import subprocess
from pathlib import Path


def test_core_agy_is_managed_oauth_and_not_provider_supported():
    import mms_core

    provider = {
        "id": "default",
        "name": "Default",
        "enabled": True,
        "api_key": "sk-test",
        "base_url": "https://example.test/v1",
        "openai_base_url": "https://example.test/v1",
        "protocols": ["openai_chat_completions"],
        "supported_clis": ["claude", "codex", "opencode", "gemini", "agy"],
    }

    assert "agy" in mms_core.CLI_NAMES
    assert "gemini" not in mms_core.CLI_NAMES
    assert "agy" in mms_core.MMS_MANAGED_OAUTH_CLIS
    assert "gemini" not in mms_core.MMS_MANAGED_OAUTH_CLIS
    assert mms_core._native_clis_for_model("gemini-3.1-pro-preview") == []
    assert mms_core._provider_supports_cli_name(provider, "agy") is False


def test_legacy_gemini_account_is_preserved_but_not_visible():
    import mms_core

    cfg, changed = mms_core._ensure_account_config(
        {
            "accounts": [
                {
                    "id": "gemini-old",
                    "name": "Gemini Old",
                    "cli": "gemini",
                    "home_dir": "/tmp/gemini-old",
                }
            ],
            "account": {"defaults": {"gemini": "gemini-old"}},
        }
    )

    assert changed is True
    assert cfg["accounts"][0]["cli"] == "gemini"
    assert cfg["account"]["defaults"]["gemini"] == "gemini-old"
    assert "gemini" not in mms_core.CLI_NAMES


def test_agy_visible_when_binary_exists_or_account_exists(monkeypatch):
    import mms_core

    provider = {
        "id": "default",
        "name": "Default",
        "enabled": True,
        "api_key": "sk-test",
        "base_url": "https://example.test/v1",
        "openai_base_url": "https://example.test/v1",
        "protocols": ["openai_chat_completions"],
        "supported_clis": ["claude", "codex", "opencode", "gemini"],
    }

    monkeypatch.setattr(mms_core, "check_cli_installed", lambda cli_name: False)
    assert "agy" not in mms_core._resolve_visible_clis({"accounts": []}, provider, ["gpt-5"])

    monkeypatch.setattr(mms_core, "check_cli_installed", lambda cli_name: cli_name == "agy")
    assert "agy" in mms_core._resolve_visible_clis({"accounts": []}, provider, ["gpt-5"])

    cfg = {
        "accounts": [
            {
                "id": "agy-main",
                "name": "Antigravity Main",
                "cli": "agy",
                "auth_mode": "oauth",
                "enabled": True,
                "home_dir": "/tmp/agy-main",
            }
        ],
        "account": {"defaults": {"agy": "agy-main"}},
    }

    monkeypatch.setattr(mms_core, "check_cli_installed", lambda cli_name: False)
    assert "agy" in mms_core._resolve_visible_clis(cfg, provider, ["gpt-5"])


def test_agy_official_account_menu_lists_multiple_oauth_accounts():
    import mms_core

    cfg = {
        "accounts": [
            {"id": "agy-work", "name": "Work", "cli": "agy", "enabled": True, "priority": 100},
            {"id": "agy-home", "name": "Home", "cli": "agy", "enabled": True, "priority": 100},
            {"id": "agy-disabled", "name": "Disabled", "cli": "agy", "enabled": False},
            {"id": "gemini-old", "name": "Gemini Old", "cli": "gemini", "enabled": True},
        ],
        "account": {"defaults": {"agy": "agy-home"}},
    }

    options = mms_core._official_account_menu_options(cfg, "agy")

    assert [option["id"] for option in options] == ["agy-home", "agy-work"]
    assert options[0]["badge"] == "*"
    assert "默认" in options[0]["summary"]


def test_agy_official_account_menu_explains_legacy_gemini_is_not_agy():
    import mms_core

    cfg = {
        "accounts": [
            {"id": "gemini-old", "name": "Gemini Old", "cli": "gemini", "enabled": True},
        ],
        "account": {"defaults": {"gemini": "gemini-old"}},
    }

    options = mms_core._official_account_menu_options(cfg, "agy")

    assert [option["id"] for option in options] == [mms_core._AGY_CONNECT_PROFILE_ID]
    assert "Gemini CLI" in options[0]["summary"]
    assert "Antigravity" in options[0]["summary"]


def test_launch_agy_uses_oauth_home_context_and_bypass(monkeypatch):
    import mms_launchers

    calls = {}

    def fake_account_env(runtime, *, validate_proxy=True, model_info=None):
        return {
            "HOME": "/tmp/agy-account/s/123",
            "MMS_SESSION_HOME": "/tmp/agy-account/s/123",
            "XDG_CONFIG_HOME": "/tmp/agy-account/s/123/.config",
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

    runtime = {"id": "agy-main", "cli": "agy", "auth_mode": "oauth", "home_dir": "/tmp/agy-account", "bypass": True}
    mms_launchers.launch_agy({}, runtime, once=True)

    assert calls["prepare"][2] == "agy"
    assert calls["exec"][0] == ["agy", "--dangerously-skip-permissions"]
    assert calls["exec"][2] is True


def test_agy_home_context_requires_isolated_session(tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    account_home = real_home / ".config" / "mms" / "accounts" / "agy-main"
    session_home = account_home / "s" / "12345"

    context = mms_launchers._build_home_context(
        {
            "HOME": str(session_home),
            "MMS_SESSION_HOME": str(session_home),
            "XDG_CONFIG_HOME": str(session_home / ".config"),
            "MMS_REAL_HOME": str(real_home),
            "REAL_HOME": str(real_home),
            "ORIGINAL_HOME": str(real_home),
        },
        {
            "id": "agy-main",
            "cli": "agy",
            "auth_mode": "oauth",
            "home_dir": str(account_home),
        },
        "agy",
    )

    result = mms_launchers._validate_home_context_or_exit(context)

    assert result["session_home"] == str(session_home)
    assert result["xdg_config_home"] == str(session_home / ".config")
    assert result["config_root"] == str(real_home / ".config" / "mms")


def test_account_env_prepares_agy_isolated_home(monkeypatch, tmp_path):
    import mms_launchers

    account_home = tmp_path / "account-home"
    real_home = tmp_path / "real-home"
    real_home.mkdir()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:15721/v1")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:15721")

    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mms_launchers,
        "_ensure_agy_account_keychain",
        lambda home, session_home=None: str(Path(home) / "Library" / "Keychains" / "login.keychain-db"),
    )
    monkeypatch.setattr(mms_launchers, "_install_agy_security_wrapper", lambda *args, **kwargs: "")
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_link_claude_library_entries", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_install_host_context_env", lambda *args, **kwargs: {})
    monkeypatch.setattr(mms_launchers, "_session_managed_mcp_servers", lambda *args, **kwargs: {})
    monkeypatch.setattr(mms_launchers, "_merge_mms_session_hooks", lambda *args, **kwargs: {})
    monkeypatch.setattr(mms_launchers, "_resolve_web_access_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_weber_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_agent_browser_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_toon_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_token_saver_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_auto_github_contributor_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))

    env = mms_launchers._account_env(
        {"id": "agy-main", "cli": "agy", "home_dir": str(account_home)},
        validate_proxy=False,
    )

    session_home = Path(env["MMS_SESSION_HOME"])
    assert env["HOME"] == str(session_home)
    assert env["XDG_CONFIG_HOME"] == str(session_home / ".config")
    assert str(session_home).startswith(str(account_home / "s"))
    assert "OPENAI_API_KEY" not in env
    assert "OPENAI_BASE_URL" not in env
    assert "HTTP_PROXY" not in env
    assert (account_home / "Library" / "Keychains").is_dir()
    assert os.path.islink(session_home / "Library")
    assert (session_home / "Library").resolve() == (account_home / "Library").resolve()
    assert (session_home / "Library" / "Keychains").resolve() == (account_home / "Library" / "Keychains").resolve()
    assert (account_home / ".gemini" / "antigravity-cli").is_dir()
    assert os.path.islink(session_home / ".gemini")
    assert (account_home / ".gemini" / "antigravity-cli" / "plugins" / "mms-session" / "plugin.json").is_file()


def test_account_env_prepares_distinct_agy_keychains_for_multiple_accounts(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_keychains = real_home / "Library" / "Keychains"
    real_keychains.mkdir(parents=True)

    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mms_launchers,
        "_ensure_agy_account_keychain",
        lambda home, session_home=None: str(Path(home) / "Library" / "Keychains" / "login.keychain-db"),
    )
    monkeypatch.setattr(mms_launchers, "_install_agy_security_wrapper", lambda *args, **kwargs: "")
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_install_host_context_env", lambda *args, **kwargs: {})
    monkeypatch.setattr(mms_launchers, "_session_managed_mcp_servers", lambda *args, **kwargs: {})
    monkeypatch.setattr(mms_launchers, "_merge_mms_session_hooks", lambda *args, **kwargs: {})
    monkeypatch.setattr(mms_launchers, "_resolve_web_access_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_weber_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_agent_browser_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_toon_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_token_saver_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_auto_github_contributor_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))

    env_a = mms_launchers._account_env(
        {"id": "agy-a", "cli": "agy", "home_dir": str(tmp_path / "agy-a")},
        validate_proxy=False,
    )
    env_b = mms_launchers._account_env(
        {"id": "agy-b", "cli": "agy", "home_dir": str(tmp_path / "agy-b")},
        validate_proxy=False,
    )

    keychains_a = Path(env_a["MMS_SESSION_HOME"]) / "Library" / "Keychains"
    keychains_b = Path(env_b["MMS_SESSION_HOME"]) / "Library" / "Keychains"
    assert keychains_a.resolve() == (tmp_path / "agy-a" / "Library" / "Keychains").resolve()
    assert keychains_b.resolve() == (tmp_path / "agy-b" / "Library" / "Keychains").resolve()
    assert keychains_a.resolve() != keychains_b.resolve()
    assert keychains_a.resolve() != real_keychains.resolve()
    assert keychains_b.resolve() != real_keychains.resolve()


def test_agy_keychain_initializer_sets_account_local_default(monkeypatch, tmp_path):
    import mms_launchers

    account_home = tmp_path / "account-home"
    session_home = account_home / "s" / "123"
    session_home.mkdir(parents=True)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs.get("env", {})))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(mms_launchers, "_macos_security_bin", lambda: "/usr/bin/security")
    monkeypatch.setattr(mms_launchers.subprocess, "run", fake_run)

    keychain_path = mms_launchers._ensure_agy_account_keychain(
        str(account_home),
        session_home=str(session_home),
    )

    expected_keychain = str(account_home / "Library" / "Keychains" / "login.keychain-db")
    assert keychain_path == expected_keychain
    assert (account_home / "Library" / "Preferences").is_dir()
    assert [call[0][1] for call in calls] == [
        "create-keychain",
        "set-keychain-settings",
        "unlock-keychain",
        "list-keychains",
        "default-keychain",
    ]
    assert all(call_env["HOME"] == str(session_home) for _cmd, call_env in calls)
    assert calls[-2][0][-1] == expected_keychain
    assert calls[-1][0][-1] == expected_keychain


def test_agy_security_wrapper_keeps_security_on_account_home(monkeypatch, tmp_path):
    import mms_launchers

    account_home = tmp_path / "account-home"
    session_home = account_home / "s" / "123"
    session_home.mkdir(parents=True)
    monkeypatch.setattr(mms_launchers, "_macos_security_bin", lambda: "/usr/bin/security")

    wrapper_path = mms_launchers._install_agy_security_wrapper(
        str(session_home),
        str(account_home),
        {},
    )

    wrapper = Path(wrapper_path).read_text(encoding="utf-8")
    assert f'export HOME="{session_home}"' in wrapper
    assert f'export MMS_AGY_ACCOUNT_HOME="{account_home}"' in wrapper
    assert "REAL_HOME" not in wrapper
    assert 'exec "/usr/bin/security" "$@"' in wrapper


def test_agy_session_assets_overlay_common_skills_mcp_and_hooks(monkeypatch, tmp_path):
    import json
    import mms_launchers

    account_home = tmp_path / "account-home"
    session_home = tmp_path / "session-home"
    web_access = tmp_path / "web-access"
    toon = tmp_path / "toon"
    for root in (web_access, toon):
        root.mkdir(parents=True)
        (root / "SKILL.md").write_text("# skill\n", encoding="utf-8")

    monkeypatch.setattr(mms_launchers, "_resolve_web_access_root", lambda: str(web_access))
    monkeypatch.setattr(mms_launchers, "_resolve_weber_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_agent_browser_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_toon_root", lambda: str(toon))
    monkeypatch.setattr(mms_launchers, "_resolve_token_saver_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_auto_github_contributor_root", lambda: "")
    monkeypatch.setattr(
        mms_launchers,
        "_session_managed_mcp_servers",
        lambda *args, **kwargs: {"pilot": {"type": "stdio", "command": "python3", "args": ["pilot.py"]}},
    )
    monkeypatch.setattr(
        mms_launchers,
        "_merge_mms_session_hooks",
        lambda *args, **kwargs: {"SessionStart": [{"hooks": [{"type": "command", "command": "/tmp/start.sh"}]}]},
    )
    monkeypatch.setattr(mms_launchers, "_filter_missing_managed_hook_commands", lambda hooks: hooks)

    mms_launchers._overlay_agy_session_assets(str(account_home), str(session_home))

    plugin_dir = account_home / ".gemini" / "antigravity-cli" / "plugins" / "mms-session"
    assert (plugin_dir / "plugin.json").is_file()
    assert os.path.islink(plugin_dir / "skills")
    assert (plugin_dir / "skills" / "web-access" / "SKILL.md").read_text(encoding="utf-8") == "# skill\n"
    assert (plugin_dir / "skills" / "toon" / "SKILL.md").read_text(encoding="utf-8") == "# skill\n"
    assert json.loads((plugin_dir / "mcp_config.json").read_text(encoding="utf-8"))["mcpServers"]["pilot"]["command"] == "python3"
    hooks_path = plugin_dir / "hooks" / "hooks.json"
    assert json.loads(hooks_path.read_text(encoding="utf-8"))["hooks"]["SessionStart"][0]["hooks"][0]["command"] == "/tmp/start.sh"


def test_agy_session_assets_repairs_stale_plugins_symlink(monkeypatch, tmp_path):
    import mms_launchers

    account_home = tmp_path / "account-home"
    current_session = account_home / "s" / "222"
    stale_target = account_home / "s" / "111" / ".gemini" / "config" / "plugins"
    plugin_root = account_home / ".gemini" / "antigravity-cli" / "plugins"
    plugin_root.parent.mkdir(parents=True)
    current_session.mkdir(parents=True)
    plugin_root.symlink_to(stale_target)

    monkeypatch.setattr(mms_launchers, "_resolve_web_access_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_weber_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_agent_browser_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_toon_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_token_saver_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_auto_github_contributor_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_session_managed_mcp_servers", lambda *args, **kwargs: {})
    monkeypatch.setattr(mms_launchers, "_merge_mms_session_hooks", lambda *args, **kwargs: {})

    mms_launchers._overlay_agy_session_assets(str(account_home), str(current_session))

    stable_root = account_home / ".gemini" / "config" / "plugins"
    assert plugin_root.is_symlink()
    assert plugin_root.resolve() == stable_root.resolve()
    assert not stale_target.exists()
    assert (plugin_root / "mms-session" / "plugin.json").is_file()
