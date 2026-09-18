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


class _FakePrompt:
    @staticmethod
    def ask(*args, **kwargs):
        return ""


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

    # Gateway sessions live under the single config root, so prune scans that root.
    config_root = tmp_path / "home" / ".config" / "mms-next"
    stale = config_root / "claude-gateway" / "s" / "999999"
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
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(config_root))

    mms_core.handle_session_command(["prune", "--cli", "claude"])

    tables = [item for item in console.items if isinstance(item, _FakeTable)]
    assert tables
    assert tables[0].rows[0][0][0] == "claude"
    assert tables[0].rows[0][0][1] == "999999"
    assert stale.exists()


def test_session_gateway_roots_follow_explicit_config_root(monkeypatch, tmp_path):
    """Pilot 用 --config-root 起来时，prune/backfill 必须跟着同一个 root 走。"""
    import mms_core

    pilot_root = tmp_path / "pilot-root"
    real_home = tmp_path / "home"
    (real_home / ".config" / "mms-next" / "claude-gateway" / "s").mkdir(parents=True)
    (pilot_root / "claude-gateway" / "s").mkdir(parents=True)
    monkeypatch.setenv("MMS_REAL_HOME", str(real_home))
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(pilot_root))

    roots = dict(mms_core._session_gateway_roots("all"))
    resume_roots = mms_core._codex_resume_roots()

    assert roots["claude"] == str(pilot_root / "claude-gateway" / "s")
    assert roots["codex"] == str(pilot_root / "codex-gateway" / "s")
    assert str(pilot_root / "codex-gateway" / ".codex") in resume_roots
    assert all(str(real_home / ".config" / "mms-next") not in item for item in resume_roots)

    monkeypatch.delenv("MMS_CONFIG_ROOT")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    fallback_roots = dict(mms_core._session_gateway_roots("all"))

    assert fallback_roots["claude"] == str(real_home / ".config" / "mms-next" / "claude-gateway" / "s")


def test_select_provider_for_models_initializes_rich_before_render(monkeypatch):
    import mms_core

    console = _CollectingConsole()

    def _fake_ensure_rich():
        mms_core.Table = _FakeTable
        mms_core.Prompt = _FakePrompt

    monkeypatch.setattr(mms_core, "Table", None)
    monkeypatch.setattr(mms_core, "Prompt", None)
    monkeypatch.setattr(mms_core, "_ensure_rich", _fake_ensure_rich)
    monkeypatch.setattr(mms_core, "console", console)
    monkeypatch.setattr(
        mms_core,
        "_list_manage_targets",
        lambda _cfg: [
            {
                "kind": "provider",
                "title": "Demo",
                "id": "demo",
                "default_label": "是",
                "status": "ok",
            }
        ],
    )

    assert mms_core._select_provider_for_models({"providers": []}) is None
    assert mms_core.Table is _FakeTable
    assert any(isinstance(item, _FakeTable) for item in console.items)
