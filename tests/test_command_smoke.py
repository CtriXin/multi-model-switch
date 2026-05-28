from __future__ import annotations


class _FakeTable:
    def __init__(self, *args, **kwargs):
        self.rows = []

    def add_column(self, *args, **kwargs):
        return None

    def add_row(self, *args, **kwargs):
        self.rows.append((args, kwargs))


class _FakeConsole:
    def print(self, *args, **kwargs):
        return None


class _CollectingConsole:
    def __init__(self):
        self.items = []

    def print(self, *args, **kwargs):
        self.items.append(args[0] if args else "")


def test_usage_main_initializes_rich_before_render(monkeypatch):
    import mms_account_state
    import mms_usage

    def _fake_ensure_rich():
        mms_usage.Table = _FakeTable
        mms_usage.Text = str

    async def _fake_section_claude(_accounts):
        mms_usage.Table(title="Claude")

    monkeypatch.setattr(mms_usage, "Table", None)
    monkeypatch.setattr(mms_usage, "Text", None)
    monkeypatch.setattr(mms_usage, "_ensure_rich", _fake_ensure_rich)
    monkeypatch.setattr(mms_usage, "console", _FakeConsole())
    monkeypatch.setattr(mms_usage, "_section_claude", _fake_section_claude)
    monkeypatch.setattr(mms_usage, "_section_codex", lambda _accounts: None)
    monkeypatch.setattr(mms_usage, "_section_providers", lambda _cache=None: None)
    monkeypatch.setattr(mms_usage, "_section_local_stats", lambda: None)
    monkeypatch.setattr(mms_usage, "_load_models_cache", lambda: {})
    monkeypatch.setattr(mms_account_state, "cache_current_claude_token", lambda: None)

    mms_usage.usage_main(
        {"accounts": [{"id": "claude-a", "cli": "claude", "auth_mode": "oauth", "enabled": True}]},
        [],
    )

    assert mms_usage.Table is _FakeTable


def test_handle_session_command_initializes_rich_before_listing(monkeypatch):
    import mms_core
    import mms_session_index

    def _fake_ensure_rich():
        mms_core.Table = _FakeTable
        mms_core.Text = str

    monkeypatch.setattr(mms_core, "Table", None)
    monkeypatch.setattr(mms_core, "Text", None)
    monkeypatch.setattr(mms_core, "_ensure_rich", _fake_ensure_rich)
    monkeypatch.setattr(mms_core, "console", _FakeConsole())
    monkeypatch.setattr(
        mms_session_index,
        "list_indexed_sessions",
        lambda cli_name="claude": [
            {
                "session_id": "session-1",
                "project_path": "/tmp/demo",
                "account_id": "claude-a",
                "last_active_at": "2026-04-16T12:00:00Z",
            }
        ],
    )

    mms_core.handle_session_command(["ls"])

    assert mms_core.Table is _FakeTable


def test_handle_session_prune_dry_run_lists_stale_gateway_sessions(monkeypatch, tmp_path):
    import mms_core

    real_home = tmp_path / "home"
    stale = real_home / ".config" / "mms" / "claude-gateway" / "s" / "999999"
    stale.mkdir(parents=True)
    (stale / "payload.txt").write_text("stale session\n", encoding="utf-8")
    console = _CollectingConsole()

    def _fake_ensure_rich():
        mms_core.Table = _FakeTable
        mms_core.Text = str

    monkeypatch.setattr(mms_core, "Table", None)
    monkeypatch.setattr(mms_core, "Text", None)
    monkeypatch.setattr(mms_core, "_ensure_rich", _fake_ensure_rich)
    monkeypatch.setattr(mms_core, "console", console)
    monkeypatch.setattr(mms_core, "resolve_real_user_home", lambda: str(real_home))

    mms_core.handle_session_command(["prune", "--cli", "claude"])

    tables = [item for item in console.items if isinstance(item, _FakeTable)]
    assert tables
    assert tables[0].rows[0][0][0] == "claude"
    assert tables[0].rows[0][0][1] == "999999"
    assert stale.exists()


def test_session_command_parser_dispatches_prune_args():
    import mms_command_tools

    calls = []

    mms_command_tools.handle_session_command(
        ["prune", "--cli", "opencode", "--apply", "--yes"],
        command_name="mmg",
        handle_session_ls=lambda cli: calls.append(("ls", cli)),
        handle_session_info=lambda session_id, cli: calls.append(("info", session_id, cli)),
        handle_session_prune=lambda cli, apply=False, yes=False: calls.append(("prune", cli, apply, yes)),
    )

    assert calls == [("prune", "opencode", True, True)]


def test_command_request_classifiers_preserve_help_and_safe_prune_semantics():
    import mms_command_tools
    import mms_core

    assert mms_command_tools.is_help_request(["config", "preferences.help"]) is True
    assert mms_command_tools.is_help_request(["config", "set", "cache.probe_async_min_interval_sec", "5"]) is False
    assert mms_command_tools.is_setup_web_request(["config", "setup-web"]) is True
    assert mms_command_tools.is_session_prune_dry_run(["session", "prune"]) is True
    assert mms_command_tools.is_session_prune_dry_run(["session", "prune", "--apply"]) is False

    assert mms_core._is_help_request(["config", "human-gate"]) is True
    assert mms_core._is_setup_web_request(["web-setup"]) is True
    assert mms_core._is_config_help_request(["preferences.example"]) is True
    assert mms_core._is_session_prune_dry_run(["session", "ls"]) is False


def test_env_command_renders_and_writes_export_file(tmp_path):
    import mms_command_tools

    console = _CollectingConsole()
    cfg = {"presets": {"demo": {"cli": "claude", "provider": "relay"}}}
    env_path = tmp_path / "demo.sh"

    def resolve_runtime(_cfg, preset, provider_override=None, stderr_only=False):
        assert preset["provider"] == "relay"
        assert provider_override == "override"
        assert stderr_only is False
        return "claude", {"ANTHROPIC_BASE_URL": "https://relay.example/v1", "API_KEY": "a b"}, {"id": "relay"}

    mms_command_tools.handle_env_command(
        cfg,
        ["demo", "--provider", "override", "--apply"],
        command_name="mmg",
        resolve_named_preset=lambda cfg_arg, name: cfg_arg["presets"][name],
        resolve_preset_export_runtime=resolve_runtime,
        env_dir=str(tmp_path),
        preset_env_file_path=lambda name: str(env_path),
        display_title=lambda: "MMS",
        console=console,
    )

    text = env_path.read_text(encoding="utf-8")
    assert "# Generated by MMS" in text
    assert "export ANTHROPIC_BASE_URL=https://relay.example/v1" in text
    assert "export API_KEY='a b'" in text
    assert any("已写入" in str(item) for item in console.items)


def test_activate_command_outputs_eval_exports(capsys):
    import mms_command_tools

    mms_command_tools.handle_activate_command(
        {"presets": {"demo": {"cli": "codex"}}},
        ["demo", "--provider", "relay"],
        command_name="mmg",
        resolve_named_preset=lambda cfg, name, stderr_only=False: cfg["presets"][name],
        resolve_preset_export_runtime=lambda cfg, preset, provider_override=None, stderr_only=False: (
            "codex",
            {"OPENAI_BASE_URL": "https://relay.example/v1", "OPENAI_API_KEY": "k v"},
            {"id": provider_override},
        ),
    )

    out = capsys.readouterr().out
    assert "export OPENAI_BASE_URL=https://relay.example/v1" in out
    assert "export OPENAI_API_KEY='k v'" in out


def test_models_command_dispatches_selected_provider():
    import mms_command_tools

    calls = []

    mms_command_tools.handle_models_command(
        {"providers": [{"id": "relay"}]},
        [],
        command_name="mmg",
        provider_map=lambda cfg: {"relay": cfg["providers"][0]},
        select_provider_for_models=lambda cfg: "relay",
        manage_provider_models=lambda cfg, provider_id: calls.append((cfg, provider_id)),
        text_cls=str,
        console=_CollectingConsole(),
    )

    assert calls == [({"providers": [{"id": "relay"}]}, "relay")]


def test_models_command_unknown_provider_exits_with_available_list():
    import pytest
    import mms_command_tools

    console = _CollectingConsole()

    with pytest.raises(SystemExit) as exc:
        mms_command_tools.handle_models_command(
            {"providers": [{"id": "relay"}]},
            ["missing"],
            command_name="mmg",
            provider_map=lambda cfg: {"relay": cfg["providers"][0]},
            select_provider_for_models=lambda cfg: "relay",
            manage_provider_models=lambda cfg, provider_id: None,
            text_cls=str,
            console=console,
        )

    assert exc.value.code == 1
    assert any("未找到模型源: missing" in str(item) for item in console.items)
    assert any("relay" in str(item) for item in console.items)


def test_choose_runtime_source_initializes_rich_before_interactive_source_table(monkeypatch):
    import mms_core

    class _TTY:
        def isatty(self):
            return True

    class _FakePrompt:
        @staticmethod
        def ask(*args, **kwargs):
            return "1"

    def _fake_ensure_rich():
        mms_core.Table = _FakeTable
        mms_core.Prompt = _FakePrompt

    options = [
        {
            "runtime": {"id": "provider-a", "name": "Provider A", "auth_mode": "api_key"},
            "models": ["gpt-5.4"],
            "launch_cli": "codex",
            "desc": "provider",
        },
        {
            "runtime": {"id": "account-a", "name": "Account A", "auth_mode": "oauth"},
            "models": ["gpt-5.4"],
            "launch_cli": "codex",
            "desc": "account",
        },
    ]

    monkeypatch.setattr(mms_core, "Table", None)
    monkeypatch.setattr(mms_core, "Prompt", None)
    monkeypatch.setattr(mms_core, "_ensure_rich", _fake_ensure_rich)
    monkeypatch.setattr(mms_core, "console", _FakeConsole())
    monkeypatch.setattr(mms_core.sys, "stdin", _TTY())
    monkeypatch.setattr(mms_core, "_list_runtime_sources", lambda *args, **kwargs: (options, 0))

    runtime, models, cli = mms_core._choose_runtime_source(
        {},
        "codex",
        {},
        ["gpt-5.4"],
    )

    assert mms_core.Table is _FakeTable
    assert runtime["id"] == "provider-a"
    assert models == ["gpt-5.4"]
    assert cli == "codex"
