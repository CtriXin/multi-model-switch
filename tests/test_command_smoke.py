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
