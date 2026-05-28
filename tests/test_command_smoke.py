from __future__ import annotations


class _FakeTable:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
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


def test_json_file_helpers_preserve_dict_only_load_and_secure_save(tmp_path):
    import json
    import stat

    import mms_command_tools

    default = {"fallback": True}
    missing_path = tmp_path / "missing.json"
    assert mms_command_tools.load_json_file(str(missing_path), default) is default

    list_path = tmp_path / "list.json"
    list_path.write_text("[1, 2, 3]", encoding="utf-8")
    assert mms_command_tools.load_json_file(str(list_path), default) is default

    broken_path = tmp_path / "broken.json"
    broken_path.write_text("{bad", encoding="utf-8")
    assert mms_command_tools.load_json_file(str(broken_path), default) is default

    saved_path = tmp_path / "nested" / "state.json"
    payload = {"message": "中文", "count": 2}
    mms_command_tools.save_json_file(str(saved_path), payload)
    assert json.loads(saved_path.read_text(encoding="utf-8")) == payload
    assert "中文" in saved_path.read_text(encoding="utf-8")
    assert stat.S_IMODE(saved_path.stat().st_mode) == 0o600


def test_ui_language_helpers_preserve_precedence_and_global_arg_cleaning(monkeypatch):
    import mms_command_tools
    import mms_core

    def normalize(raw):
        return {
            "zh": "zh",
            "en": "en",
            "zh_CN.UTF-8": "zh",
            "en_US.UTF-8": "en",
        }.get(str(raw or "").strip(), "")

    cfg, changed = mms_command_tools.normalize_ui_config(
        {"ui": {"language": "en"}},
        normalize_language=normalize,
    )
    assert cfg == {"ui": {"language": "en"}}
    assert changed is False

    cfg, changed = mms_command_tools.normalize_ui_config(
        {"ui": {"language": "fr", "theme": "ignored"}},
        normalize_language=normalize,
    )
    assert cfg == {"ui": {"language": "zh"}}
    assert changed is True

    environ = {"MMS_LANG": "zh", "LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"}
    assert mms_command_tools.resolve_ui_language(
        {"ui": {"language": "en"}},
        "en",
        normalize_language=normalize,
        load_version_meta=lambda: {"preferred_language": "zh"},
        environ=environ,
    ) == "en"
    assert mms_command_tools.resolve_ui_language(
        {"ui": {"language": "en"}},
        "",
        normalize_language=normalize,
        load_version_meta=lambda: {"preferred_language": "zh"},
        environ=environ,
    ) == "zh"
    assert mms_command_tools.resolve_ui_language(
        {"ui": {"language": "en"}},
        "",
        normalize_language=normalize,
        load_version_meta=lambda: {"preferred_language": "zh"},
        environ={"LC_ALL": "zh_CN.UTF-8"},
    ) == "en"
    assert mms_command_tools.resolve_ui_language(
        {},
        "",
        normalize_language=normalize,
        load_version_meta=lambda: {"preferred_language": "en"},
        environ={},
    ) == "en"

    assert mms_command_tools.extract_global_lang(
        ["config", "--lang", "en", "provider.default", "--lang"],
        normalize_language=normalize,
    ) == (["config", "provider.default", "--lang"], "en")

    monkeypatch.delenv("MMS_LANG", raising=False)
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setattr(mms_core, "_load_version_meta", lambda: {"preferred_language": "zh"})
    assert mms_core._normalize_ui_config({"ui": {"language": "en"}}) == ({"ui": {"language": "en"}}, False)
    assert mms_core._resolve_ui_language({}, None) == "en"
    assert mms_core._extract_global_lang(["--lang", "zh", "codex"]) == (["codex"], "zh")


def test_gateway_active_and_snapshot_path_helpers_preserve_resolution(tmp_path):
    import os

    import mms_command_tools
    import mms_core

    marker = os.path.join(".config", "mms", "codex-gateway", "s") + os.sep
    gateway_path = os.path.join(str(tmp_path), marker, "123", "config.toml")
    base_config = os.path.join(str(tmp_path), ".config", "mms", "config.toml")
    base_dir = os.path.join(str(tmp_path), ".config", "mms")

    assert mms_command_tools.base_user_config_path_from_gateway(
        gateway_path,
        gateway_session_markers=(marker,),
    ) == base_config
    assert mms_command_tools.base_user_primary_dir_from_gateway(
        gateway_path,
        gateway_session_markers=(marker,),
    ) == base_dir
    assert mms_core._base_user_primary_dir_from_gateway(gateway_path) == base_dir

    assert mms_command_tools.active_sibling_path_from_gateway(
        gateway_path,
        filename="config.toml",
        base_user_primary_dir_from_gateway=lambda _path: base_dir,
        path_exists=lambda path: path == base_config,
    ) == base_config
    assert mms_command_tools.active_sibling_path_from_gateway(
        gateway_path,
        filename="config.toml",
        base_user_primary_dir_from_gateway=lambda _path: base_dir,
        path_exists=lambda _path: False,
    ) == gateway_path

    assert mms_command_tools.config_guard_root_dir(
        config_path=gateway_path,
        config_write_target_path=lambda: "unused",
        base_user_primary_dir_from_gateway=lambda _path: base_dir,
    ) == base_dir
    normal_config_path = str(tmp_path / "plain" / "config.toml")
    assert mms_command_tools.config_guard_root_dir(
        config_path=normal_config_path,
        config_write_target_path=lambda: "unused",
        base_user_primary_dir_from_gateway=lambda _path: "",
    ) == str(tmp_path / "plain")
    assert mms_command_tools.config_snapshot_root(
        config_path=normal_config_path,
        config_guard_root_dir=lambda path: os.path.dirname(path),
        config_snapshot_dir="snapshots",
    ) == str(tmp_path / "plain" / "snapshots")
    assert mms_command_tools.config_snapshot_path(
        "startup",
        "accepted.json",
        config_path=normal_config_path,
        config_snapshot_root=lambda path: os.path.join(os.path.dirname(path), "snapshots"),
    ) == str(tmp_path / "plain" / "snapshots" / "startup" / "accepted.json")


def test_base_user_broker_profile_merge_helper_preserves_gateway_overlay(tmp_path):
    import mms_command_tools

    active_config = tmp_path / "gateway" / "config.toml"
    base_config = tmp_path / "base" / "config.toml"
    base_config.parent.mkdir()
    base_config.write_text(
        """
[[broker_profiles]]
id = "base"
name = "Base"

[[broker_profiles]]
id = "second"
""".strip(),
        encoding="utf-8",
    )

    cfg = {"provider": {"default": "relay"}, "broker_profiles": [{"id": "active"}]}
    ensure_calls = []

    def ensure_broker_config(merged):
        ensure_calls.append(merged)
        return merged, False

    merged, changed = mms_command_tools.merge_base_user_broker_profiles(
        cfg,
        str(active_config),
        base_user_config_path_from_gateway=lambda _path: str(base_config),
        ensure_broker_config=ensure_broker_config,
    )
    assert changed is True
    assert merged["provider"] == {"default": "relay"}
    assert merged["broker_profiles"] == [
        {"id": "active"},
        {"id": "base", "name": "Base"},
        {"id": "second"},
    ]
    assert ensure_calls == [merged]
    assert cfg["broker_profiles"] == [{"id": "active"}]

    unchanged, changed = mms_command_tools.merge_base_user_broker_profiles(
        cfg,
        str(active_config),
        base_user_config_path_from_gateway=lambda _path: "",
        ensure_broker_config=ensure_broker_config,
    )
    assert unchanged is cfg
    assert changed is False

    base_config.write_text("{broken", encoding="utf-8")
    unchanged, changed = mms_command_tools.merge_base_user_broker_profiles(
        cfg,
        str(active_config),
        base_user_config_path_from_gateway=lambda _path: str(base_config),
        ensure_broker_config=ensure_broker_config,
    )
    assert unchanged is cfg
    assert changed is False


def test_toml_and_existing_path_helpers_preserve_read_and_filtering(tmp_path):
    import tomllib

    import mms_command_tools
    import mms_core

    toml_path = tmp_path / "prefs.toml"
    toml_path.write_text('message = "中文"\n[launch.defaults]\nbypass = true\n', encoding="utf-8")
    assert mms_command_tools.load_toml_file(str(toml_path), toml_loads=tomllib.loads) == {
        "message": "中文",
        "launch": {"defaults": {"bypass": True}},
    }
    assert mms_core._load_toml_file(str(toml_path))["message"] == "中文"

    paths = [str(tmp_path / "missing.toml"), str(toml_path), str(tmp_path / "other.toml")]
    assert mms_command_tools.existing_paths(paths, path_exists=lambda path: path.endswith("prefs.toml")) == [str(toml_path)]


def test_preference_and_override_load_helpers_preserve_merge_warning_and_sanitize():
    from datetime import datetime, timezone

    import mms_command_tools

    class DecodeError(Exception):
        pass

    class Console:
        def __init__(self):
            self.items = []

        def print(self, value):
            self.items.append(value)

    console = Console()
    loaded = {
        "/prefs-a.toml": {"launch": {"defaults": {"bypass": "on"}}, "ignored": True},
        "/prefs-b.toml": {"launch": {"cli": {"codex": {"reasoning_effort": "high"}}}},
    }

    prefs = mms_command_tools.load_user_preferences_from_paths(
        existing_preferences_paths=lambda: ["/prefs-a.toml", "/broken.toml", "/prefs-b.toml"],
        load_toml_file=lambda path: (_ for _ in ()).throw(DecodeError("bad toml")) if path == "/broken.toml" else loaded[path],
        merge_dicts=mms_command_tools.merge_dicts,
        sanitize_user_preferences=lambda payload: mms_command_tools.sanitize_user_preferences(
            payload,
            cli_names=["codex"],
            asset_root_keys={},
        ),
        console=console,
        toml_error_types=(DecodeError,),
    )
    assert prefs["launch"]["defaults"]["bypass"] is True
    assert prefs["launch"]["cli"]["codex"]["reasoning_effort"] == "high"
    assert any("跳过无效 preferences 文件 /broken.toml" in item for item in console.items)

    console = Console()
    overrides = {
        "/override-a.toml": {"provider": {"default": "a"}},
        "/override-b.toml": {"provider": {"name": "B"}},
    }
    merged = mms_command_tools.apply_local_overrides(
        {"base": True, "provider": {"default": "old"}},
        existing_override_paths=lambda: ["/override-a.toml", "/broken.toml", "/override-b.toml"],
        load_toml_file=lambda path: (_ for _ in ()).throw(DecodeError("bad override")) if path == "/broken.toml" else overrides[path],
        merge_dicts=mms_command_tools.merge_dicts,
        load_user_preferences=lambda: {"launch": {"defaults": {"bypass": "enable"}}},
        console=console,
        toml_error_types=(DecodeError,),
    )
    assert merged == {
        "base": True,
        "provider": {"default": "a", "name": "B"},
        "_mms_preferences": {"launch": {"defaults": {"bypass": "enable"}}},
    }
    assert any("跳过无效 override 文件 /broken.toml" in item for item in console.items)

    prefs = {"assets": {"roots": {"toon": "/tmp/toon-root"}}}
    assert mms_command_tools.preference_asset_root(
        "toon",
        asset_root_keys={"toon": "toon"},
        load_user_preferences=lambda: prefs,
    ) == "/tmp/toon-root"
    assert mms_command_tools.preference_asset_root(
        "unknown",
        asset_root_keys={"toon": "toon"},
        load_user_preferences=lambda: prefs,
    ) == ""
    assert mms_command_tools.iso_now(now_func=lambda: datetime(2026, 5, 28, 15, 20, 32, tzinfo=timezone.utc)) == "2026-05-28T15:20:32Z"
    assert mms_command_tools.local_now_slug(now_func=lambda: datetime(2026, 5, 28, 23, 20, 32)) == "20260528-232032"


def test_usage_stats_file_helpers_preserve_defaults_secure_write_and_guard(tmp_path):
    import json
    import stat

    import mms_command_tools

    missing_path = tmp_path / "missing.json"
    assert mms_command_tools.load_usage_stats_from_path(str(missing_path)) == {"sources": {}}

    list_path = tmp_path / "list.json"
    list_path.write_text("[1, 2, 3]", encoding="utf-8")
    assert mms_command_tools.load_usage_stats_from_path(str(list_path)) == {"sources": {}}

    broken_path = tmp_path / "broken.json"
    broken_path.write_text("{bad", encoding="utf-8")
    assert mms_command_tools.load_usage_stats_from_path(str(broken_path)) == {"sources": {}}

    stats_path = tmp_path / "usage.json"
    stats_path.write_text('{"models": {"codex": 1}}', encoding="utf-8")
    loaded = mms_command_tools.load_usage_stats_from_path(str(stats_path))
    assert loaded == {"models": {"codex": 1}, "sources": {}}

    guard_calls = []
    target_path = tmp_path / "config.toml"
    mms_command_tools.write_usage_stats_locked(
        str(tmp_path / "state" / "usage.json"),
        {"message": "中文", "sources": {"codex": {}}},
        ensure_mms_config_guard_files=lambda path: guard_calls.append(path),
        config_write_target_path=lambda: str(target_path),
    )
    written_path = tmp_path / "state" / "usage.json"
    assert guard_calls == [str(target_path)]
    assert json.loads(written_path.read_text(encoding="utf-8")) == {"message": "中文", "sources": {"codex": {}}}
    assert "中文" in written_path.read_text(encoding="utf-8")
    assert not (tmp_path / "state" / "usage.json.tmp").exists()
    assert stat.S_IMODE(written_path.stat().st_mode) == 0o600


def test_usage_routes_export_trigger_preserves_throttle_running_and_async_reset():
    import mms_command_tools

    class Lock:
        def __init__(self):
            self.entries = 0

        def __enter__(self):
            self.entries += 1
            return self

        def __exit__(self, *_args):
            return False

    state = {"running": False, "last": 100.0}
    lock = Lock()
    threads = []
    refresh_calls = []

    class Thread:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            threads.append(self)

        def start(self):
            self.started = True

    def trigger(now):
        return mms_command_tools.trigger_routes_export_after_usage_write(
            lock=lock,
            is_running=lambda: state["running"],
            set_running=lambda value: state.__setitem__("running", value),
            get_last_started_at=lambda: state["last"],
            set_last_started_at=lambda value: state.__setitem__("last", value),
            min_interval_sec=15.0,
            refresh_routes_export_for_hive=lambda **kwargs: refresh_calls.append(kwargs),
            thread_cls=Thread,
            monotonic=lambda: now,
        )

    state["running"] = True
    trigger(200.0)
    assert threads == []
    assert state == {"running": True, "last": 100.0}

    state["running"] = False
    trigger(110.0)
    assert threads == []
    assert state == {"running": False, "last": 100.0}

    trigger(120.0)
    assert state == {"running": True, "last": 120.0}
    assert len(threads) == 1
    assert threads[0].kwargs["daemon"] is True
    assert threads[0].kwargs["name"] == "mms-usage-routes-export"
    assert getattr(threads[0], "started", False) is True
    threads[0].kwargs["target"]()
    assert refresh_calls == [{"force": True, "quiet": True}]
    assert state["running"] is False
    assert lock.entries >= 2

    def failing_refresh(**_kwargs):
        raise RuntimeError("export failed")

    threads.clear()
    state["last"] = 0.0
    mms_command_tools.trigger_routes_export_after_usage_write(
        lock=lock,
        is_running=lambda: state["running"],
        set_running=lambda value: state.__setitem__("running", value),
        get_last_started_at=lambda: state["last"],
        set_last_started_at=lambda value: state.__setitem__("last", value),
        min_interval_sec=15.0,
        refresh_routes_export_for_hive=failing_refresh,
        thread_cls=Thread,
        monotonic=lambda: 200.0,
    )
    assert state["running"] is True
    threads[0].kwargs["target"]()
    assert state["running"] is False


def test_backup_config_tree_preserves_real_home_backup_layout(tmp_path):
    import os

    import mms_command_tools

    real_home = tmp_path / "real-home"
    primary_config = tmp_path / "active-config"
    primary_config.mkdir()
    (primary_config / "config.toml").write_text("provider = {}\n", encoding="utf-8")

    backup_dir = mms_command_tools.backup_config_tree(
        "provider-rename",
        resolve_real_user_home=lambda: str(real_home),
        primary_config_dir=str(primary_config),
        local_now_slug=lambda: "20260529-010203",
    )

    expected_dir = real_home / ".config" / "mms-backups" / "provider-rename-20260529-010203"
    assert backup_dir == str(expected_dir)
    assert (expected_dir / "active-config" / "config.toml").read_text(encoding="utf-8") == "provider = {}\n"

    calls = []
    missing_dir = mms_command_tools.backup_config_tree(
        "config-migrate",
        resolve_real_user_home=lambda: str(real_home),
        primary_config_dir=str(tmp_path / "missing-config"),
        local_now_slug=lambda: "20260529-010204",
        copytree=lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    assert missing_dir == os.path.join(str(real_home), ".config", "mms-backups", "config-migrate-20260529-010204")
    assert calls == []


def test_refresh_routes_export_for_hive_helper_preserves_load_override_export_and_errors():
    import mms_command_tools

    calls = []
    messages = []

    class FakeConsole:
        def print(self, message):
            messages.append(message)

    assert mms_command_tools.refresh_routes_export_for_hive(
        None,
        force=True,
        quiet=False,
        startup_safe=True,
        load_config=lambda: {"provider": {"default": "demo"}, "providers": []},
        apply_local_overrides=lambda cfg: {**cfg, "local_override_applied": True},
        export_model_routes=lambda cfg, force=False, startup_safe=False: calls.append((cfg, force, startup_safe)),
        console=FakeConsole(),
    ) is True
    assert calls == [
        ({"provider": {"default": "demo"}, "providers": [], "local_override_applied": True}, True, True)
    ]

    assert mms_command_tools.refresh_routes_export_for_hive(
        {"direct": True},
        force=False,
        quiet=True,
        startup_safe=False,
        load_config=lambda: None,
        apply_local_overrides=lambda cfg: calls.append(("unexpected_apply", cfg)),
        export_model_routes=lambda cfg, force=False, startup_safe=False: calls.append((cfg, force, startup_safe)),
        console=FakeConsole(),
    ) is True
    assert calls[-1] == ({"direct": True}, False, False)

    assert mms_command_tools.refresh_routes_export_for_hive(
        None,
        load_config=lambda: None,
        apply_local_overrides=lambda cfg: calls.append(("unexpected_apply", cfg)),
        export_model_routes=lambda cfg, **kwargs: calls.append(("unexpected_export", cfg, kwargs)),
        console=FakeConsole(),
    ) is False
    assert calls[-1] == ({"direct": True}, False, False)

    def failing_export(*_args, **_kwargs):
        raise RuntimeError("boom")

    assert mms_command_tools.refresh_routes_export_for_hive(
        {"direct": True},
        quiet=False,
        load_config=lambda: None,
        apply_local_overrides=lambda cfg: cfg,
        export_model_routes=failing_export,
        console=FakeConsole(),
    ) is False
    assert messages == ["[yellow]⚠ Hive routes export 刷新失败: boom[/yellow]"]


def test_config_guard_file_helper_preserves_bootstrap_backup_and_mode(tmp_path):
    import stat

    import mms_command_tools

    (tmp_path / "AGENTS.md").write_text("old agents", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("old claude", encoding="utf-8")

    mms_command_tools.ensure_mms_config_guard_files(
        config_path=str(tmp_path / "config.toml"),
        config_guard_root_dir=lambda _path: str(tmp_path),
        render_agents_guard=lambda: "new agents",
        render_claude_guard=lambda: "new claude",
        config_backup_root=lambda _path: str(tmp_path / "backups"),
        local_now_slug=lambda: "20260528-225100",
    )

    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "new agents"
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == "new claude"
    assert stat.S_IMODE((tmp_path / "AGENTS.md").stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "CLAUDE.md").stat().st_mode) == 0o600
    backup_dir = tmp_path / "backups" / "guardrails-20260528-225100"
    assert (backup_dir / "AGENTS.md").read_text(encoding="utf-8") == "old agents"
    assert (backup_dir / "CLAUDE.md").read_text(encoding="utf-8") == "old claude"


def test_snapshot_drift_prompt_helpers_preserve_tty_gate_and_preview():
    import mms_command_tools

    class Tty:
        def __init__(self, value):
            self.value = value

        def isatty(self):
            return self.value

    class Panel:
        def __init__(self, text, **kwargs):
            self.text = text
            self.kwargs = kwargs

    class Console:
        def __init__(self):
            self.items = []

        def print(self, value):
            self.items.append(value)

    assert mms_command_tools.snapshot_prompt_allowed(stdin=Tty(True), stdout=Tty(True)) is True
    assert mms_command_tools.snapshot_prompt_allowed(stdin=Tty(True), stdout=Tty(False)) is False

    console = Console()
    confirm_calls = []
    confirmed = mms_command_tools.confirm_startup_snapshot_drift(
        [f"diff-{idx}" for idx in range(14)],
        accepted_path="/accepted.json",
        latest_path="/latest.json",
        ensure_rich=lambda: confirm_calls.append("rich"),
        panel_cls=Panel,
        confirm_ask=lambda label, default=False: confirm_calls.append((label, default)) or True,
        snapshot_prompt_allowed=lambda: True,
        console=console,
    )
    assert confirmed is True
    assert confirm_calls == ["rich", ("是否接受当前快照并继续启动？", False)]
    panel = console.items[0]
    assert panel.kwargs == {"title": "MMS Snapshot Guard", "border_style": "red"}
    assert "diff-11" in panel.text
    assert "diff-12" not in panel.text
    assert "... 还有 2 项" in panel.text
    assert "accepted: /accepted.json" in panel.text
    assert "latest:   /latest.json" in panel.text

    console = Console()
    assert mms_command_tools.confirm_startup_snapshot_drift(
        ["diff"],
        accepted_path="/accepted.json",
        latest_path="/latest.json",
        ensure_rich=lambda: None,
        panel_cls=Panel,
        confirm_ask=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not ask")),
        snapshot_prompt_allowed=lambda: False,
        console=console,
    ) is False


def test_startup_snapshot_guard_helper_preserves_bootstrap_pending_and_exit_flow():
    import mms_command_tools

    class Console:
        def __init__(self):
            self.items = []

        def print(self, value):
            self.items.append(value)

    current = {"generation": 1}
    writes = {}
    periodic = []
    console = Console()

    def path_for(kind, name, config_path=None):
        return f"{config_path}:{kind}:{name}"

    kwargs = {
        "config_write_target_path": lambda: "/config.toml",
        "build_config_guard_snapshot": lambda cfg, config_path=None: dict(current),
        "config_snapshot_path": path_for,
        "iso_now": lambda: "now",
        "snapshot_digest": lambda payload: f"digest-{payload['generation']}",
        "write_json_snapshot": lambda path, payload: writes.__setitem__(path, payload),
        "update_periodic_snapshot": lambda period, snapshot, config_path=None: periodic.append((period, dict(snapshot), config_path)),
        "load_json_snapshot": lambda path: writes.get(path),
        "snapshot_diff_lines": lambda accepted, now: [] if accepted == now else ["generation changed"],
        "confirm_startup_snapshot_drift": lambda *_args, **_kwargs: False,
        "command_name": lambda: "mmg",
        "config_guard_exit_code": 41,
        "console": console,
    }

    result = mms_command_tools.ensure_startup_snapshot_guard({}, **kwargs)
    assert result == {"generation": 1}
    assert writes["/config.toml:startup:accepted.json"]["digest"] == "digest-1"
    assert periodic == [
        ("daily", {"generation": 1}, "/config.toml"),
        ("weekly", {"generation": 1}, "/config.toml"),
    ]

    current["generation"] = 2
    result = mms_command_tools.ensure_startup_snapshot_guard({}, enforce=False, **kwargs)
    assert result == {"generation": 2}
    pending = writes["/config.toml:startup:pending.json"]
    assert pending["diffs"] == ["generation changed"]
    assert pending["accepted"] == {"generation": 1}
    assert pending["current"] == {"generation": 2}

    exits = []
    try:
        mms_command_tools.ensure_startup_snapshot_guard(
            {},
            exit_func=lambda code: exits.append(code) or (_ for _ in ()).throw(SystemExit(code)),
            **kwargs,
        )
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert exc.code == 41
    assert exits == [41]
    assert "mmg guard status" in console.items[-1]
    assert "mmg guard accept" in console.items[-1]


def test_guard_accept_tui_confirm_helper_preserves_no_drift_and_confirm_paths():
    import mms_command_tools

    class Console:
        def __init__(self):
            self.items = []

        def print(self, value):
            self.items.append(value)

    console = Console()
    paths = {
        "latest.json": "/latest.json",
        "accepted.json": "/accepted.json",
    }
    accepted = {"snapshot": {"generation": 1}}
    current = {"generation": 1}

    kwargs = {
        "config_write_target_path": lambda: "/config.toml",
        "build_config_guard_snapshot": lambda cfg, config_path=None: dict(current),
        "config_snapshot_path": lambda _kind, name, config_path=None: paths[name],
        "load_json_snapshot": lambda path: accepted if path == "/accepted.json" else None,
        "snapshot_diff_lines": lambda old, new: [] if old == new else ["generation changed"],
        "confirm_startup_snapshot_drift": lambda *_args, **_kwargs: True,
        "console": console,
    }

    assert mms_command_tools.confirm_guard_accept_from_tui({}, **kwargs) is False
    assert console.items == ["[green]当前快照没有 drift，不需要 accept。[/green]"]

    current["generation"] = 2
    confirm_calls = []
    kwargs["confirm_startup_snapshot_drift"] = lambda diffs, **kw: confirm_calls.append((diffs, kw)) or True
    assert mms_command_tools.confirm_guard_accept_from_tui({}, **kwargs) is True
    assert confirm_calls == [
        (
            ["generation changed"],
            {"accepted_path": "/accepted.json", "latest_path": "/latest.json"},
        )
    ]


def test_snapshot_payload_helpers_preserve_config_guard_normalization(tmp_path):
    import hashlib
    import json
    import stat
    from datetime import datetime

    import mms_command_tools
    import mms_core

    assert mms_command_tools.snapshot_proxy_fingerprint("") == "direct"
    assert (
        mms_command_tools.snapshot_proxy_fingerprint("http://user:pass@proxy.local:8080")
        == "http://proxy.local:8080+auth"
    )
    assert mms_command_tools.is_snapshot_ignored_file("/tmp/usage.json", ignored_files={"usage.json"}) is True
    assert mms_core._is_snapshot_ignored_file("/tmp/usage.json") is True
    assert mms_command_tools.sha256_text("中文") == mms_core._sha256_text("中文")

    home_dir = str(tmp_path / "home")
    assert mms_command_tools.snapshot_cli_state(home_dir, "codex") == [
        str(tmp_path / "home" / ".codex" / "auth.json"),
        str(tmp_path / "home" / ".codex" / "config.toml"),
    ]
    assert mms_core._snapshot_cli_state(home_dir, "claude") == [
        str(tmp_path / "home" / ".claude" / "settings.json"),
    ]

    state_payload = mms_command_tools.normalize_claude_state_snapshot_payload(
        {
            "userID": " user-1 ",
            "oauthAccount": {
                "accountUuid": " account-1 ",
                "emailAddress": "me@example.com",
                "token": "ignored",
            },
            "sessionToken": "ignored",
        }
    )
    assert state_payload["userID"] == "user-1"
    assert state_payload["oauthAccount"]["accountUuid"] == "account-1"
    assert state_payload["oauthAccount"]["emailAddress"] == "me@example.com"
    assert "token" not in state_payload["oauthAccount"]
    assert mms_core._normalize_claude_state_snapshot_payload(None)["userID"] == ""

    settings_payload = mms_command_tools.normalize_claude_settings_snapshot_payload(
        {"env": {"HTTP_PROXY": "http://proxy", "CUSTOM_FLAG": "1"}, "theme": "dark"},
        session_env_keys={"HTTP_PROXY"},
    )
    assert settings_payload == {"env": {"CUSTOM_FLAG": "1"}, "theme": "dark"}
    assert mms_core._normalize_claude_settings_snapshot_payload(
        {"env": {"HTTP_PROXY": "http://proxy", "NO_PROXY": "localhost"}}
    ) == {}

    identity_home = tmp_path / "identity-home"
    identity_home.mkdir()
    (identity_home / ".claude.json").write_text(
        json.dumps(
            {
                "userID": "user-abcdef",
                "oauthAccount": {
                    "accountUuid": "acct-123456",
                    "organizationUuid": "org-654321",
                    "emailAddress": "me@example.com",
                },
                "sessionToken": "ignored",
            }
        ),
        encoding="utf-8",
    )
    identity_entry = mms_command_tools.snapshot_claude_identity_entry(
        str(identity_home),
        normalize_claude_state_snapshot_payload=mms_command_tools.normalize_claude_state_snapshot_payload,
        mask_identity_value=lambda value, keep=4: f"id:{str(value)[-keep:]}",
        mask_email_value=lambda value: f"mail:{value}",
        sha256_text=mms_command_tools.sha256_text,
    )
    assert identity_entry["fingerprint"] == "id:cdef|id:3456|id:4321|mail:me@example.com"
    assert identity_entry["sha256"]

    account_entry = mms_command_tools.snapshot_account_entry(
        {"id": "claude-a", "cli": "claude", "home_dir": str(identity_home), "proxy": "http://proxy:8080"},
        default_priority=10,
        default_timezone="UTC",
        normalize_priority=lambda value: int(value),
        normalize_timezone_name=lambda value, default: value or default,
        runtime_force_ipv4=lambda runtime: runtime.get("force_ipv4", False),
        snapshot_proxy_fingerprint=mms_command_tools.snapshot_proxy_fingerprint,
        sha256_text=mms_command_tools.sha256_text,
        snapshot_claude_identity_entry=lambda _home: {"fingerprint": "fp", "sha256": "sha"},
    )
    assert account_entry["priority"] == 10
    assert account_entry["timezone"] == "UTC"
    assert account_entry["identity_fingerprint"] == "fp"
    assert account_entry["proxy_fingerprint"] == "http://proxy:8080"

    provider_entry = mms_command_tools.snapshot_provider_entry(
        {"id": "relay", "name": "Relay", "priority": 11, "models_endpoint": "/models", "force_ipv4": True},
        default_priority=10,
        default_timezone="UTC",
        normalize_priority=lambda value: int(value),
        normalize_timezone_name=lambda value, default: value or default,
        runtime_force_ipv4=lambda runtime: runtime.get("force_ipv4", False),
        snapshot_proxy_fingerprint=mms_command_tools.snapshot_proxy_fingerprint,
        sha256_text=mms_command_tools.sha256_text,
    )
    assert provider_entry["priority"] == 11
    assert provider_entry["force_ipv4"] is True
    assert mms_core._snapshot_provider_entry({"id": "relay", "name": "Relay"})["id"] == "relay"

    claude_state = tmp_path / ".claude.json"
    claude_state.write_text(
        json.dumps({"userID": "user-1", "oauthAccount": {"emailAddress": "me@example.com"}, "sessionToken": "secret"}),
        encoding="utf-8",
    )
    normalized_bytes, normalized_kind = mms_command_tools.snapshot_file_content_bytes(
        str(claude_state),
        session_env_keys={"HTTP_PROXY"},
    )
    normalized_state = json.loads(normalized_bytes.decode("utf-8"))
    assert normalized_kind == "claude_state_identity"
    assert normalized_state["userID"] == "user-1"
    assert "sessionToken" not in normalized_state

    claude_settings_dir = tmp_path / ".claude"
    claude_settings_dir.mkdir()
    claude_settings = claude_settings_dir / "settings.json"
    claude_settings.write_text(
        json.dumps({"env": {"HTTP_PROXY": "http://proxy", "CUSTOM_FLAG": "1"}, "theme": "dark"}),
        encoding="utf-8",
    )
    settings_bytes, settings_kind = mms_core._snapshot_file_content_bytes(str(claude_settings))
    normalized_settings = json.loads(settings_bytes.decode("utf-8"))
    assert settings_kind == "claude_settings_runtime_stripped"
    assert normalized_settings == {"env": {"CUSTOM_FLAG": "1"}, "theme": "dark"}

    plain_file = tmp_path / "plain.txt"
    plain_file.write_text("payload", encoding="utf-8")
    entry = mms_command_tools.snapshot_file_entry(
        str(plain_file),
        snapshot_file_content_bytes=lambda _path: (b"payload", ""),
    )
    assert entry["exists"] is True
    assert entry["sha256"] == hashlib.sha256(b"payload").hexdigest()
    assert "normalized_kind" not in entry
    assert mms_core._snapshot_file_entry(str(tmp_path / "missing.json"))["exists"] is False

    snapshot = {"b": 2, "a": "中文"}
    assert mms_command_tools.snapshot_digest(snapshot) == mms_core._snapshot_digest({"a": "中文", "b": 2})
    assert mms_command_tools.load_json_snapshot(str(tmp_path / "missing-snapshot.json")) is None
    broken_snapshot = tmp_path / "broken-snapshot.json"
    broken_snapshot.write_text("{bad", encoding="utf-8")
    assert mms_command_tools.load_json_snapshot(str(broken_snapshot)) is None
    written_snapshot = tmp_path / "snapshots" / "latest.json"
    mms_command_tools.write_json_snapshot(str(written_snapshot), {"message": "中文"})
    assert json.loads(written_snapshot.read_text(encoding="utf-8")) == {"message": "中文"}
    assert stat.S_IMODE(written_snapshot.stat().st_mode) == 0o600

    assert mms_command_tools.snapshot_period_bucket("daily", now_func=lambda: datetime(2026, 5, 28, 22, 0)) == "2026-05-28"
    assert mms_command_tools.snapshot_period_bucket("weekly", now_func=lambda: datetime(2026, 5, 28, 22, 0)) == "2026-W22"
    assert mms_command_tools.snapshot_period_bucket("startup", now_func=lambda: datetime(2026, 5, 28, 22, 5)) == "2026-05-28T22:05"

    periodic = {}
    mms_command_tools.update_periodic_snapshot(
        "daily",
        {"snapshot": True},
        config_path="/tmp/config.toml",
        config_snapshot_path=lambda period, filename, config_path=None: f"{config_path}:{period}:{filename}",
        snapshot_period_bucket=lambda period: f"bucket:{period}",
        iso_now=lambda: "now",
        snapshot_digest=lambda payload: f"digest:{payload['snapshot']}",
        write_json_snapshot=lambda path, payload: periodic.update({path: payload}),
    )
    assert periodic == {
        "/tmp/config.toml:daily:latest.json": {
            "period": "daily",
            "bucket": "bucket:daily",
            "captured_at": "now",
            "digest": "digest:True",
            "snapshot": {"snapshot": True},
        }
    }

    config_path = tmp_path / "cfg" / "config.toml"
    snapshot = mms_command_tools.build_config_guard_snapshot(
        {
            "provider": {"default": " relay "},
            "account": {"defaults": {"codex": "codex-a"}},
            "accounts": [
                {"id": "z-account", "home_dir": str(tmp_path / "z"), "cli": "codex"},
                "ignored",
                {"id": "a-account", "home_dir": str(tmp_path / "a"), "cli": "claude"},
            ],
            "providers": [
                {"id": "z-provider"},
                "ignored",
                {"id": "a-provider"},
            ],
        },
        config_path=str(config_path),
        default_config=lambda: {"provider": {}, "account": {}, "accounts": [], "providers": []},
        config_write_target_path=lambda: str(config_path),
        config_guard_root_dir=lambda path: str(tmp_path / "cfg"),
        config_snapshot_schema="schema.v1",
        iso_now=lambda: "now",
        snapshot_account_entry=lambda account: {
            "id": account["id"],
            "home_dir": account["home_dir"],
            "cli": account["cli"],
        },
        snapshot_cli_state=lambda home, cli: [
            str(tmp_path / "cfg" / "credentials.sh"),
            str(tmp_path / "cfg" / "usage.json"),
            str(tmp_path / f"{cli}.state"),
        ],
        snapshot_provider_entry=lambda provider: {"id": provider["id"]},
        is_snapshot_ignored_file=lambda path: str(path).endswith("usage.json"),
        snapshot_file_entry=lambda path: {"path": path},
        environ={"MMS_REAL_HOME": str(tmp_path / "real-home")},
    )
    assert snapshot["schema"] == "schema.v1"
    assert snapshot["captured_at"] == "now"
    assert snapshot["config_path"] == str(config_path)
    assert snapshot["real_home"] == str(tmp_path / "real-home")
    assert snapshot["defaults"] == {"provider_default": "relay", "account_defaults": {"codex": "codex-a"}}
    assert [item["id"] for item in snapshot["accounts"]] == ["a-account", "z-account"]
    assert [item["id"] for item in snapshot["providers"]] == ["a-provider", "z-provider"]
    file_paths = [item["path"] for item in snapshot["files"]]
    assert file_paths == sorted(set(file_paths))
    assert not any(path.endswith("usage.json") for path in file_paths)
    assert str(tmp_path / "cfg" / "credentials.sh") in file_paths


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


def test_tui_usage_recency_helpers_preserve_sorting_and_cold_family_rules():
    from datetime import datetime, timezone

    import mms_command_tools

    now = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)

    assert mms_command_tools.parse_usage_timestamp("2026-05-28T10:00:00Z") == datetime(
        2026,
        5,
        28,
        10,
        0,
        0,
        tzinfo=timezone.utc,
    )
    assert mms_command_tools.parse_usage_timestamp("not-a-date") is None
    assert mms_command_tools.usage_recency_score(
        "2026-05-20T12:00:00Z",
        now=now,
        half_life_days=0,
    ) == 1.0

    families = [
        {"family": "GPT", "last_used_at": "2026-05-01T00:00:00Z"},
        {"family": "Qwen", "last_used_at": "2026-05-28T11:30:00Z"},
        {"family": "Claude"},
    ]
    assert [
        item["family"]
        for item in mms_command_tools.sort_family_entries_for_tui(families, preferred_family="GPT", now=now)
    ] == ["Qwen", "GPT", "Claude"]
    assert [
        item["family"]
        for item in mms_command_tools.sort_family_entries_for_tui(
            [{"family": "Qwen"}, {"family": "GPT"}, {"family": "Claude"}],
            preferred_family="GPT",
            now=now,
        )
    ] == ["GPT", "Claude", "Qwen"]

    cold_kwargs = {
        "known_model_family_names": {"GPT", "Claude", "Qwen"},
        "cold_max_use_count": 3,
        "cold_idle_days": 21,
        "now": now,
    }
    assert mms_command_tools.family_is_cold_for_tui("Unknown", 0, "", **cold_kwargs) is True
    assert mms_command_tools.family_is_cold_for_tui(
        "Unknown",
        0,
        "2026-04-01T00:00:00Z",
        **cold_kwargs,
    ) is True
    assert mms_command_tools.family_is_cold_for_tui(
        "Unknown",
        0,
        "2026-05-27T00:00:00Z",
        **cold_kwargs,
    ) is False
    assert mms_command_tools.family_is_cold_for_tui("GPT", 0, "", **cold_kwargs) is False
    assert mms_command_tools.family_is_cold_for_tui(
        "Unknown",
        0,
        "",
        preferred_family="Unknown",
        **cold_kwargs,
    ) is False


def test_resolve_visible_clis_preserves_oauth_and_family_hint_rules():
    import mms_command_tools

    resolver_calls = []

    def accounts_for_cli(_cfg, cli_name):
        return ["account"] if cli_name == "claude" else []

    def check_cli_installed(cli_name):
        return cli_name == "agy"

    def resolve_provider_for_cli(cfg, cli_name, default_provider, default_models):
        resolver_calls.append((cfg, cli_name, default_provider, default_models))
        if cli_name == "missing":
            return None, []
        if cli_name == "gemini":
            return {"id": "provider"}, []
        if cli_name == "codex":
            return {"id": "provider"}, ["gpt-5.5"]
        return {"id": "provider"}, []

    cfg = {"cfg": True}
    provider = {"id": "default"}
    models = ["gpt-5.5"]

    assert mms_command_tools.resolve_visible_clis(
        cfg,
        provider,
        models,
        cli_names=["claude", "agy", "missing", "gemini", "codex", "opencode"],
        managed_oauth_clis={"claude", "agy"},
        cli_model_family_hints={"gemini": ["Gemini"], "codex": ["GPT"]},
        accounts_for_cli=accounts_for_cli,
        check_cli_installed=check_cli_installed,
        resolve_provider_for_cli=resolve_provider_for_cli,
    ) == ["claude", "agy", "codex", "opencode"]
    assert [call[1] for call in resolver_calls] == ["missing", "gemini", "codex", "opencode"]


def test_use_tui_preserves_tty_width_and_oserror_rules():
    import mms_command_tools

    class Stdin:
        def __init__(self, is_tty):
            self._is_tty = is_tty

        def isatty(self):
            return self._is_tty

    class Size:
        def __init__(self, columns):
            self.columns = columns

    assert mms_command_tools.use_tui(Stdin(False), lambda: Size(120)) is False
    assert mms_command_tools.use_tui(Stdin(True), lambda: Size(39)) is False
    assert mms_command_tools.use_tui(Stdin(True), lambda: Size(40)) is True

    def raise_oserror():
        raise OSError("no tty")

    assert mms_command_tools.use_tui(Stdin(True), raise_oserror) is False


def test_launcher_entry_and_model_info_helpers_preserve_filtering_rules():
    import mms_command_tools

    assert mms_command_tools.clean_model_info({"model": "gpt-5.5", "provider": {"id": "relay"}}) == {
        "model": "gpt-5.5",
    }
    assert mms_command_tools.clean_model_info("gpt-5.5") == "gpt-5.5"

    oauth_clis = {"claude", "codex", "gemini", "agy"}
    assert mms_command_tools.uses_native_account_entry({"auth_mode": "oauth"}, "claude", oauth_capable_clis=oauth_clis)
    assert not mms_command_tools.uses_native_account_entry({"auth_mode": "api_key"}, "claude", oauth_capable_clis=oauth_clis)
    assert not mms_command_tools.uses_native_account_entry({"auth_mode": "oauth"}, "opencode", oauth_capable_clis=oauth_clis)
    assert mms_command_tools.uses_broker_entry({"runtime_kind": "broker"}, "claude")
    assert not mms_command_tools.uses_broker_entry({"runtime_kind": "broker"}, "codex")
    assert mms_command_tools.uses_managed_entry({"auth_mode": "oauth"}, "codex", oauth_capable_clis=oauth_clis)

    assert mms_command_tools.preset_model_info(
        {
            "cli": "claude",
            "provider": "relay",
            "account": "claude-a",
            "bridge": "http://bridge",
            "description": "demo",
            "model": "gpt-5.5",
            "thinking": True,
        }
    ) == {"model": "gpt-5.5", "thinking": True}
    assert mms_command_tools.preset_model_info(None) == {}


def test_broker_and_opencode_profile_helpers_preserve_disabled_default_and_config_precedence():
    import mms_command_tools

    assert mms_command_tools.available_broker_profiles_for_cli({}, "claude") == []
    assert mms_command_tools.broker_enabled_by_cli({}, ["claude", "codex"]) == {
        "claude": False,
        "codex": False,
    }
    assert mms_command_tools.broker_enabled_by_cli(
        {"broker": True},
        ["claude", "codex"],
        available_broker_profiles_for_cli=lambda _cfg, cli_name: [{"id": "remote"}] if cli_name == "claude" else [],
    ) == {"claude": True, "codex": False}
    profiles = [
        {"id": "a", "device_id": "dev-a", "workspace_id": "ws-a", "broker_base_url": "http://a"},
        {"id": "b", "device_id": "dev-b", "workspace_id": "ws-b", "remote_service_label": "remote-b"},
    ]
    prompts = iter(["bad", "2"])
    console = _CollectingConsole()
    assert mms_command_tools.select_broker_profile_interactive(
        {},
        "claude",
        available_broker_profiles_for_cli=lambda _cfg, _cli_name: profiles,
        ensure_rich=lambda: None,
        table_cls=_FakeTable,
        prompt_ask=lambda *args, **kwargs: next(prompts),
        console=console,
    ) == profiles[1]
    assert any("请输入有效编号" in str(item) for item in console.items)
    console.items.clear()
    launch_calls = []
    assert mms_command_tools.launch_broker_experiment_interactive(
        {"cfg": True},
        "claude",
        select_broker_profile_interactive=lambda cfg, cli_name: None,
        run_broker_profile_interactive=lambda cfg, profile_id: launch_calls.append((cfg, profile_id)) or 0,
        console=console,
    ) is False
    assert launch_calls == []
    assert mms_command_tools.launch_broker_experiment_interactive(
        {"cfg": True},
        "claude",
        select_broker_profile_interactive=lambda cfg, cli_name: {
            "id": "remote",
            "name": "Remote",
            "device_id": "dev",
            "workspace_id": "ws",
        },
        run_broker_profile_interactive=lambda cfg, profile_id: launch_calls.append((cfg, profile_id)) or 9,
        console=console,
    ) is True
    assert launch_calls == [({"cfg": True}, "remote")]
    assert any("退出码 9" in str(item) for item in console.items)

    seen = []

    def profile_selection(raw):
        seen.append(raw)
        return {"profile": raw or "default"}

    assert mms_command_tools.opencode_default_profile_from_config(
        {"opencode": {"profile": "lite", "default_profile": "agent"}},
        opencode_profile_selection=profile_selection,
    ) == {"profile": "agent"}
    assert mms_command_tools.opencode_default_profile_from_config(
        {},
        opencode_profile_selection=profile_selection,
    ) == {"profile": "default"}
    assert seen == ["agent", None]


def test_launch_trace_formatter_preserves_sources_and_override_chain():
    import mms_command_tools

    trace_overrides = [
        ("cli arg", {"cli": "codex", "model": "gpt-5.4"}),
        ("runtime resolve", {"provider": "relay", "runtime": "api_key", "bridge": "http://bridge"}),
        ("empty", {}),
    ]
    runtime = {"auth_mode": "api_key", "provider_id": "relay"}

    report = mms_command_tools.format_launch_trace(
        "codex",
        {"model": "gpt-5.4"},
        runtime,
        trace_overrides,
        runtime_provider_id=lambda runtime: runtime.get("provider_id", ""),
        runtime_account_id=lambda runtime: "",
        runtime_bridge=lambda runtime: "http://bridge",
    )

    assert "[MMS Trace]" in report
    assert "cli:      codex <- cli arg" in report
    assert "provider: relay <- runtime resolve" in report
    assert "account:  - <- (not set)" in report
    assert "model:    gpt-5.4 <- cli arg" in report
    assert "bridge:   http://bridge <- runtime resolve" in report
    assert "runtime:  api_key <- runtime resolve" in report
    assert "cli arg         -> cli=codex, model=gpt-5.4" in report
    assert "empty           -> (none)" in report


def test_trace_record_helper_preserves_enabled_filtering_and_none_skip():
    import mms_command_tools

    trace_overrides = []
    mms_command_tools.record_trace_override(
        False,
        trace_overrides,
        "disabled",
        cli="codex",
    )
    assert trace_overrides == []

    mms_command_tools.record_trace_override(
        True,
        trace_overrides,
        "cli arg",
        cli="codex",
        provider=None,
        model="gpt-5.4",
    )
    assert trace_overrides == [("cli arg", {"cli": "codex", "model": "gpt-5.4"})]


def test_settings_result_display_helpers_format_payload_and_fallback_report():
    import mms_command_tools

    payload = mms_command_tools.settings_result_tui_payload(
        "done",
        [("Key", "value"), ("Blank", "")],
        "note",
        localize=lambda zh, en: zh,
    )
    assert payload == (
        "✓ done",
        [("状态", "成功"), ("Key", "value"), ("Blank", "-"), ("说明", "note")],
        [("back", "返回")],
    )
    assert mms_command_tools.compact_tui_report_value("x" * 12, max_len=5) == "xxxx…"

    console = _CollectingConsole()
    mms_command_tools.display_settings_result_report(
        "failed",
        [("Reason", "line1\nline2")],
        "try again",
        ok=False,
        console=console,
    )
    assert console.items == [
        "[red]✗ failed[/red]",
        "[cyan]Reason[/cyan] line1 line2",
        "[dim]try again[/dim]",
    ]


def test_settings_result_tui_available_preserves_env_and_tty_checks():
    import mms_command_tools

    class FakeStream:
        def __init__(self, result=None, exc=None):
            self.result = result
            self.exc = exc

        def isatty(self):
            if self.exc is not None:
                raise self.exc
            return self.result

    assert mms_command_tools.settings_result_tui_available(
        env={},
        stdin=FakeStream(True),
        stdout=FakeStream(True),
    ) is True
    assert mms_command_tools.settings_result_tui_available(
        env={"MMS_DISABLE_SETTINGS_RESULT_TUI": "yes"},
        stdin=FakeStream(True),
        stdout=FakeStream(True),
    ) is False
    assert mms_command_tools.settings_result_tui_available(
        env={},
        stdin=FakeStream(True),
        stdout=FakeStream(False),
    ) is False
    assert mms_command_tools.settings_result_tui_available(
        env={},
        stdin=FakeStream(exc=RuntimeError("boom")),
        stdout=FakeStream(True),
    ) is False


def test_select_settings_result_tui_uses_payload_builder_and_selector():
    import mms_command_tools

    calls = []

    def payload_builder(title, rows, note="", *, ok=True):
        calls.append(("payload", title, list(rows), note, ok))
        return "✓ done", [("状态", "成功")], [("back", "返回")]

    def selector(title, info_lines, actions):
        calls.append(("selector", title, info_lines, actions))
        return "back"

    selected = mms_command_tools.select_settings_result_tui(
        "done",
        [("Key", "value")],
        "note",
        ok=True,
        settings_result_tui_payload=payload_builder,
        select_channel_action_tui=selector,
    )

    assert selected == "back"
    assert calls == [
        ("payload", "done", [("Key", "value")], "note", True),
        ("selector", "✓ done", [("状态", "成功")], [("back", "返回")]),
    ]


def test_print_settings_result_report_preserves_tui_and_fallback_flow():
    import mms_command_tools

    events = []

    def display(title, rows, note="", *, ok=True, console):
        events.append(("display", title, list(rows), note, ok, console))

    mms_command_tools.print_settings_result_report(
        "done",
        [("Key", "value")],
        "note",
        ok=True,
        settings_result_tui_available=lambda: True,
        select_settings_result_tui=lambda title, rows, note="", ok=True: events.append(("tui", title, list(rows), note, ok)),
        mark_tui_rendered=lambda: events.append(("mark",)),
        clear_tui_rendered=lambda: events.append(("clear",)),
        ensure_rich=lambda: events.append(("rich",)),
        display_settings_result_report=display,
        console="console",
    )
    assert events == [
        ("tui", "done", [("Key", "value")], "note", True),
        ("mark",),
    ]

    events.clear()
    mms_command_tools.print_settings_result_report(
        "done",
        [("Key", "value")],
        "note",
        ok=False,
        settings_result_tui_available=lambda: False,
        select_settings_result_tui=lambda *args, **kwargs: events.append(("tui",)),
        mark_tui_rendered=lambda: events.append(("mark",)),
        clear_tui_rendered=lambda: events.append(("clear",)),
        ensure_rich=lambda: events.append(("rich",)),
        display_settings_result_report=display,
        console="console",
    )
    assert events == [
        ("rich",),
        ("display", "done", [("Key", "value")], "note", False, "console"),
    ]

    events.clear()

    def broken_selector(*args, **kwargs):
        raise RuntimeError("boom")

    mms_command_tools.print_settings_result_report(
        "done",
        [],
        "",
        settings_result_tui_available=lambda: True,
        select_settings_result_tui=broken_selector,
        mark_tui_rendered=lambda: events.append(("mark",)),
        clear_tui_rendered=lambda: events.append(("clear",)),
        ensure_rich=lambda: events.append(("rich",)),
        display_settings_result_report=display,
        console="console",
    )
    assert events == [
        ("clear",),
        ("rich",),
        ("display", "done", [], "", True, "console"),
    ]


def test_print_settings_error_report_preserves_error_payload():
    import mms_command_tools

    calls = []
    exc = RuntimeError("boom")

    result = mms_command_tools.print_settings_error_report(
        "failed",
        exc,
        print_settings_result_report=lambda title, rows, note, *, ok=True: calls.append((title, rows, note, ok)) or "reported",
        localize=lambda zh, en: zh,
    )

    assert result == "reported"
    assert calls == [
        (
            "failed",
            [("错误", exc)],
            "操作未完成；没有改变 runtime defaults。",
            False,
        )
    ]


def test_pause_after_tui_report_preserves_skip_and_fallback_prompt():
    import mms_command_tools

    events = []

    mms_command_tools.pause_after_tui_report(
        "按 Enter 返回设置",
        tui_rendered=lambda: True,
        clear_tui_rendered=lambda: events.append(("clear",)),
        ensure_rich=lambda: events.append(("rich",)),
        input_func=lambda: events.append(("input",)),
        console=_CollectingConsole(),
    )
    assert events == [("clear",)]

    console = _CollectingConsole()
    events.clear()
    mms_command_tools.pause_after_tui_report(
        "按 Enter 返回设置",
        tui_rendered=lambda: False,
        clear_tui_rendered=lambda: events.append(("clear",)),
        ensure_rich=lambda: events.append(("rich",)),
        input_func=lambda: events.append(("input",)),
        console=console,
    )
    assert events == [("rich",), ("input",)]
    assert console.items == ["[dim]按 Enter 返回设置[/dim]"]

    events.clear()
    mms_command_tools.pause_after_tui_report(
        "按 Enter 返回设置",
        tui_rendered=lambda: False,
        clear_tui_rendered=lambda: events.append(("clear",)),
        ensure_rich=lambda: events.append(("rich",)),
        input_func=lambda: (_ for _ in ()).throw(EOFError()),
        console=_CollectingConsole(),
    )
    assert events == [("rich",)]


def test_model_probe_recovery_helpers_preserve_findings_actions_and_details():
    import mms_command_tools

    provider = {"id": "relay", "name": "Relay"}
    probe = {"error_kind": "protocol_unsupported", "details": ["provider: Relay", "error: unsupported"]}

    findings = mms_command_tools.model_validation_findings(
        provider,
        probe,
        provider_label=lambda item: item["name"],
    )
    assert findings[0]["severity"] == "high"
    assert findings[0]["title"] == "当前 provider 不支持模型探测"
    assert "Relay 没有声明" in findings[0]["summary"]
    assert findings[-1]["severity"] == "low"

    actions = mms_command_tools.build_model_recovery_actions(
        {"providers": [{"id": "relay"}, {"id": "backup"}]},
        provider,
        probe,
        provider_map=lambda cfg: {item["id"]: item for item in cfg["providers"]},
    )
    assert [item["id"] for item in actions] == [
        "edit_credentials",
        "switch_provider",
        "show_details",
        "continue_without_validation",
    ]
    assert actions[1]["recommended"] is True

    class FakePanel:
        def __init__(self, body, **kwargs):
            self.body = body
            self.kwargs = kwargs

    console = _CollectingConsole()
    mms_command_tools.display_model_probe_details(probe, panel_cls=FakePanel, console=console)
    panel = console.items[0]
    assert panel.body == "- provider: Relay\n- error: unsupported"
    assert panel.kwargs == {"title": "校验详情", "border_style": "yellow"}


def test_select_provider_interactive_preserves_prompt_flow():
    import mms_command_tools

    cfg = {
        "providers": [
            {"id": "relay", "name": "Relay", "protocols": ["openai"]},
            {"id": "disabled", "name": "Disabled", "enabled": False},
            {"id": "backup", "name": "Backup", "protocols": ["anthropic", "openai"]},
        ]
    }

    class FakePrompt:
        values = iter(["9", "1"])

        @classmethod
        def ask(cls, *args, **kwargs):
            return next(cls.values)

    console = _CollectingConsole()
    selected = mms_command_tools.select_provider_interactive(
        cfg,
        "relay",
        resolve_provider_context=lambda received_cfg, provider_id: {"resolved": provider_id, "cfg": received_cfg},
        table_cls=_FakeTable,
        prompt_cls=FakePrompt,
        console=console,
    )
    table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert table.kwargs == {"title": "可切换的 Providers"}
    assert table.rows == [(("1", "backup", "Backup", "anthropic, openai"), {})]
    assert selected == {"resolved": "backup", "cfg": cfg}
    assert any("请输入 1-1 的编号" in str(item) for item in console.items)

    empty_console = _CollectingConsole()
    assert mms_command_tools.select_provider_interactive(
        {"providers": [{"id": "relay"}]},
        "relay",
        resolve_provider_context=lambda received_cfg, provider_id: None,
        table_cls=_FakeTable,
        prompt_cls=FakePrompt,
        console=empty_console,
    ) is None
    assert empty_console.items == ["[yellow]没有可切换的其他 provider[/yellow]"]


def test_pick_recovery_actions_preserves_tui_and_prompt_fallback():
    import mms_command_tools

    findings = [{"title": "问题", "summary": "说明"}]
    actions = [
        {"id": "edit", "title": "编辑", "summary": "修复", "recommended": True},
        {"id": "details", "title": "详情", "summary": "查看"},
    ]

    selected = mms_command_tools.pick_recovery_actions(
        findings,
        actions,
        use_tui=True,
        select_actions_tui=lambda *args, **kwargs: ["details"],
        panel_cls=_FakeTable,
        prompt_cls=None,
        console=_CollectingConsole(),
    )
    assert selected == ["details"]

    class FakePanel:
        def __init__(self, body, **kwargs):
            self.body = body
            self.kwargs = kwargs

    class FakePrompt:
        values = iter(["3", "2,1,2"])

        @classmethod
        def ask(cls, *args, **kwargs):
            return next(cls.values)

    console = _CollectingConsole()
    selected = mms_command_tools.pick_recovery_actions(
        findings,
        actions,
        use_tui=True,
        select_actions_tui=lambda *args, **kwargs: "fallback",
        panel_cls=FakePanel,
        prompt_cls=FakePrompt,
        console=console,
    )
    assert selected == ["details", "edit"]
    assert isinstance(console.items[0], FakePanel)
    assert console.items[0].body == "- 问题: 说明"
    assert any("请输入 1-2" in str(item) for item in console.items)


def test_run_recovery_action_preserves_dispatch_and_callbacks():
    import mms_command_tools

    cfg = {"providers": [{"id": "relay"}, {"id": "backup"}]}
    provider = {"id": "relay", "base_url": "https://relay.example", "api_key": "sk-test"}
    probe = {"details": ["failure"]}
    calls = []

    def display_details(received_probe):
        calls.append(("details", received_probe))

    def edit_credentials(received_provider, base_url, api_key, *, allow_keep=False):
        calls.append(("edit", received_provider, base_url, api_key, allow_keep))
        return {"id": "relay", "base_url": "https://new.example"}

    def select_provider(received_cfg, current_provider_id):
        calls.append(("select", received_cfg, current_provider_id))
        return {"id": "backup"}

    console = _CollectingConsole()
    selected, skip = mms_command_tools.run_recovery_action(
        cfg,
        provider,
        probe,
        "show_details",
        display_model_probe_details=display_details,
        setup_provider_credentials=edit_credentials,
        select_provider_interactive=select_provider,
        console=console,
    )
    assert selected is provider
    assert skip is False
    assert calls[-1] == ("details", probe)

    selected, skip = mms_command_tools.run_recovery_action(
        cfg,
        provider,
        probe,
        "edit_credentials",
        display_model_probe_details=display_details,
        setup_provider_credentials=edit_credentials,
        select_provider_interactive=select_provider,
        console=console,
    )
    assert selected["base_url"] == "https://new.example"
    assert skip is False
    assert calls[-1] == ("edit", provider, "https://relay.example", "sk-test", True)

    selected, skip = mms_command_tools.run_recovery_action(
        cfg,
        provider,
        probe,
        "switch_provider",
        display_model_probe_details=display_details,
        setup_provider_credentials=edit_credentials,
        select_provider_interactive=select_provider,
        console=console,
    )
    assert selected == {"id": "backup"}
    assert skip is False
    assert calls[-1] == ("select", cfg, "relay")

    selected, skip = mms_command_tools.run_recovery_action(
        cfg,
        provider,
        probe,
        "continue_without_validation",
        display_model_probe_details=display_details,
        setup_provider_credentials=edit_credentials,
        select_provider_interactive=select_provider,
        console=console,
    )
    assert selected is provider
    assert skip is True
    assert "已跳过模型校验" in console.items[-1]


def test_rescue_report_payload_helpers_preserve_safe_local_outputs():
    import mms_command_tools

    localize = lambda zh, en: zh
    title, rows, note = mms_command_tools.rescue_default_fallback_report_payload(
        "deepseek-v4-flash",
        localize=localize,
    )
    hot_title, hot_rows, hot_note = mms_command_tools.rescue_default_fallback_report_payload(
        "deepseek-v4-flash",
        hot_fallback_enabled=True,
        localize=localize,
    )
    clear_title, clear_rows, clear_note = mms_command_tools.rescue_default_fallback_report_payload(
        "",
        cleared=True,
        localize=localize,
    )
    blocked_title, blocked_rows, _blocked_note = mms_command_tools.rescue_hot_fallback_toggle_report_payload(
        True,
        has_default=False,
        localize=localize,
    )
    demo_title, demo_rows, _demo_note = mms_command_tools.rescue_demo_packet_report_payload(
        {"artifacts": {"markdown": "/tmp/rescue.md", "json": "/tmp/rescue.json"}},
        localize=localize,
    )
    paths_title, paths_rows, _paths_note = mms_command_tools.rescue_paths_report_payload(
        {"artifact_markdown": "/tmp/current.md", "artifact_json": "/tmp/current.json"},
        localize=localize,
    )
    handover_title, handover_rows, handover_note = mms_command_tools.rescue_handover_report_payload(
        {"artifacts": {"markdown": "/tmp/handover.md", "latest_markdown": "/tmp/latest.md"}},
        "deepseek-v4-flash",
        localize=localize,
    )

    assert title == "全局 fallback 已设置"
    assert ("Model", "deepseek-v4-flash") in rows
    assert ("Hot fallback", "关闭") in rows
    assert "只记录 rescue / fallback handoff" in note
    assert hot_title == "全局 fallback 已设置"
    assert ("Hot fallback", "开启") in hot_rows
    assert "routed model" in hot_note
    assert clear_title == "全局 fallback 已清除"
    assert ("保存位置", "[rescue].fallback_model") in clear_rows
    assert clear_note == ""
    assert blocked_title == "无法开启 hot fallback"
    assert ("原因", "请先设置全局 fallback model") in blocked_rows
    assert demo_title == "测试 rescue packet 已生成"
    assert ("rescue.md", "/tmp/rescue.md") in demo_rows
    assert paths_title == "Rescue 文件路径"
    assert ("rescue.json", "/tmp/current.json") in paths_rows
    assert handover_title == "fallback handover 已生成"
    assert ("latest", "/tmp/latest.md") in handover_rows
    assert "不切换当前 session" in handover_note


def test_registry_report_payload_helpers_preserve_compact_outputs():
    import mms_command_tools

    localize = lambda zh, en: zh
    source_title, source_rows, _source_note = mms_command_tools.registry_source_staleness_report_payload(
        {
            "db_path": "/tmp/model-registry.sqlite",
            "due_count": 2,
            "source_count": 6,
            "sources": [
                {"due": True, "reason": "age", "checked_at": "2026-05-28", "source_path": f"/tmp/source-{idx}"}
                for idx in range(6)
            ],
        },
        localize=localize,
    )
    refresh_title, refresh_rows, refresh_note = mms_command_tools.registry_refresh_sources_report_payload(
        {"db_path": "/tmp/db.sqlite", "imported_count": 1, "model_count": 2, "fact_count": 3},
        localize=localize,
    )
    scheduled_title, scheduled_rows, scheduled_note = mms_command_tools.registry_scheduled_refresh_report_payload(
        {
            "db_path": "/tmp/db.sqlite",
            "dry_run": True,
            "source_due_count": 2,
            "source_refresh": {"imported_count": 0},
            "openrouter_due": False,
            "openrouter_fetch": {},
        },
        localize=localize,
    )
    fetch_title, fetch_rows, fetch_note = mms_command_tools.registry_openrouter_fetch_report_payload(
        {"db_path": "/tmp/db.sqlite", "snapshot_id": "snap-1", "model_count": 9},
        localize=localize,
    )
    diff_title, diff_rows, diff_note = mms_command_tools.registry_openrouter_diff_report_payload(
        {
            "change_count": 6,
            "stored_count": 6,
            "missing_reference_count": 1,
            "untracked_catalog_count": 3,
            "changes": [
                {"field_key": "context_window", "model_key": f"gpt-{idx}", "provider_model_id": f"openai/gpt-{idx}"}
                for idx in range(6)
            ],
        },
        localize=localize,
    )
    publish_title, publish_rows, publish_note = mms_command_tools.registry_publish_approved_report_payload(
        {"manifest_path": "/tmp/manifest.json", "bundle_revision": "rev-1"},
        localize=localize,
    )
    verify_title, verify_rows, verify_note = mms_command_tools.registry_verify_approved_report_payload(
        {
            "manifest_path": "/tmp/manifest.json",
            "manifest": {"bundle_revision": "rev-1"},
            "verified_files": {"a": "hash", "b": "hash"},
        },
        localize=localize,
    )
    doctor_title, doctor_rows, doctor_note = mms_command_tools.registry_doctor_report_payload(
        {"db_path": "/tmp/db.sqlite", "user_version": 1, "counts": {"models": 2, "facts": 3}},
        localize=localize,
    )

    assert source_title == "模型真源 Source Staleness"
    assert ("到期 Source", "2 / 6") in source_rows
    assert ("更多 Source", 1) in source_rows
    assert refresh_title == "刷新 Sources 完成"
    assert ("跳过", 0) in refresh_rows
    assert "不改变当前 runtime defaults" in refresh_note
    assert scheduled_title == "定时刷新结果"
    assert ("OpenRouter", "No Network 模式未拉取") in scheduled_rows
    assert "不接入 startup" in scheduled_note
    assert fetch_title == "OpenRouter Catalog 拉取完成"
    assert ("Snapshot", "snap-1") in fetch_rows
    assert "provider_catalog source snapshot" in fetch_note
    assert diff_title == "OpenRouter Candidate Diff"
    assert ("缺少 reference", 1) in diff_rows
    assert ("更多变化", 1) in diff_rows
    assert "candidate_change evidence" in diff_note
    assert publish_title == "发布 Approved Bundle 完成"
    assert ("Bundle", "rev-1") in publish_rows
    assert "不改 root aliases" in publish_note
    assert verify_title == "Latest-approved hash 验证完成"
    assert ("文件", 2) in verify_rows
    assert verify_note == ""
    assert doctor_title == "Registry Doctor / 状态"
    assert doctor_rows == [("DB", "/tmp/db.sqlite"), ("user_version", 1), ("facts", 3), ("models", 2)]
    assert doctor_note == ""


def test_about_and_snapshot_payload_helpers_preserve_version_actions():
    import mms_command_tools

    localize = lambda zh, en: zh
    title, info_lines, actions = mms_command_tools.about_tui_payload(
        {
            "version_info": {
                "release": "v9.9.9",
                "git_branch": "main",
                "git_commit": "abc123",
                "install_channel": "latest-tag",
                "source": "install.sh",
            },
            "mms": {
                "current": "v9.9.9",
                "latest": "v9.9.10",
                "status": "有新版 v9.9.10",
                "outdated": True,
                "last_error": "SSL handshake failed",
            },
            "clis": {
                "codex": {
                    "label": "codex-cli 0.132.0",
                    "latest": "0.133.0",
                    "status": "有新版 0.133.0",
                    "outdated": True,
                },
                "claude": {"label": "2.1.148 (Claude Code)", "latest": "", "status": "最新"},
            },
        },
        config_path="/tmp/mms/config.toml",
        localize=localize,
    )
    guard_title, guard_info, guard_actions = mms_command_tools.snapshot_guard_tui_payload(
        command_name="mmg",
        localize=localize,
    )
    console = _CollectingConsole()
    mms_command_tools.display_about_version_summary(
        {"mms": {"current": "dev", "status": "最新"}},
        payload_builder=lambda snapshot: ("关于 / About", [("MMS", snapshot["mms"]["current"])], [("back", "返回")]),
        console=console,
    )

    assert title == "关于 / About"
    assert ("MMS", "v9.9.9 · 有新版 v9.9.10") in info_lines
    assert ("Codex", "codex-cli 0.132.0 · 有新版") in info_lines
    assert ("Claude 最新", "未检查") in info_lines
    assert ("Config", "/tmp/mms/config.toml") in info_lines
    assert ("检查错误", "MMS latest 检查失败：SSL handshake，可稍后重试") in info_lines
    assert ("upgrade_mms", "升级 MMS") in actions
    assert ("upgrade_codex_cli", "升级 Codex CLI") in actions
    assert ("upgrade_claude_cli", "升级 Claude CLI") not in actions
    assert guard_title == "启动快照 / Snapshot Guard"
    assert ("CLI", "mmg guard status / accept") in guard_info
    assert guard_actions == [("status", "查看当前 Snapshot 状态"), ("accept", "接受当前 Snapshot"), ("back", "返回")]
    assert console.items == ["[cyan]关于 / About[/cyan]", "[cyan]MMS[/cyan] dev"]


def test_about_upgrade_command_helpers_preserve_shell_commands():
    import mms_command_tools

    assert mms_command_tools.mms_upgrade_shell_command(
        preferred_language="en",
        normalize_language=lambda value: value,
    ).endswith("install.sh | bash -s -- --latest-tag --lang en")
    assert mms_command_tools.mms_upgrade_shell_command(
        include_clis=True,
        preferred_language="",
        normalize_language=lambda value: "",
    ).endswith("install.sh | bash -s -- --latest-tag --lang zh --install-cli claude,codex")
    assert mms_command_tools.cli_upgrade_shell_command(
        "codex",
        cli_version_packages={"codex": "@openai/codex"},
    ) == "npm install -g @openai/codex@latest"
    assert mms_command_tools.cli_upgrade_shell_command(
        "missing",
        cli_version_packages={"codex": "@openai/codex"},
    ) == ""


def test_run_about_upgrade_preserves_confirm_gate_and_execution():
    import mms_command_tools

    class Result:
        stdout = "ok"
        returncode = 0

    console = _CollectingConsole()
    calls = []
    cancelled = mms_command_tools.run_about_upgrade(
        target="mms",
        ensure_rich=lambda: calls.append(("rich",)),
        cli_upgrade_shell_command=lambda target: "npm",
        mms_upgrade_shell_command=lambda include_clis=False: "install-mms --latest",
        confirm_ask=lambda label, default=False: calls.append(("confirm", label, default)) or False,
        subprocess_run=lambda *args, **kwargs: calls.append(("run", args, kwargs)) or Result(),
        console=console,
        localize=lambda zh, en: zh,
    )
    assert cancelled is False
    assert calls == [("rich",), ("confirm", "确认执行升级？", False)]
    assert console.items == [
        "[yellow]即将升级 MMS[/yellow]",
        "[dim]install-mms --latest[/dim]",
        "[yellow]已取消升级。[/yellow]",
    ]

    console = _CollectingConsole()
    calls.clear()
    succeeded = mms_command_tools.run_about_upgrade(
        target="codex",
        ensure_rich=lambda: calls.append(("rich",)),
        cli_upgrade_shell_command=lambda target: f"upgrade-{target}",
        mms_upgrade_shell_command=lambda include_clis=False: "install-mms",
        confirm_ask=lambda label, default=False: True,
        subprocess_run=lambda *args, **kwargs: calls.append(("run", args, kwargs)) or Result(),
        console=console,
        localize=lambda zh, en: zh,
    )
    assert succeeded is True
    assert calls[0] == ("rich",)
    assert calls[1][0] == "run"
    assert calls[1][1][0] == ["bash", "-lc", "upgrade-codex"]
    assert calls[1][2]["stdout"] == mms_command_tools.subprocess.PIPE
    assert console.items[-1].startswith("[green]✓ 升级命令完成")

    console = _CollectingConsole()
    assert mms_command_tools.run_about_upgrade(
        target="missing",
        ensure_rich=lambda: None,
        cli_upgrade_shell_command=lambda target: "",
        mms_upgrade_shell_command=lambda include_clis=False: "",
        confirm_ask=lambda label, default=False: True,
        subprocess_run=lambda *args, **kwargs: Result(),
        console=console,
        localize=lambda zh, en: zh,
    ) is False
    assert console.items == ["[red]没有可执行的升级命令。[/red]"]


def test_mms_config_guard_renderers_preserve_human_gate_text():
    import mms_command_tools

    agents_text = mms_command_tools.render_mms_config_agents_guard()
    claude_text = mms_command_tools.render_mms_config_claude_guard()

    assert agents_text.startswith("# AGENTS.md")
    assert "human confirmation before write" in agents_text
    assert "Never overwrite in place without a backup" in agents_text
    assert "`~/.config/mms`" in agents_text
    assert claude_text.startswith("# CLAUDE.md")
    assert "human-only config" in claude_text
    assert "Claude must never auto-write MMS user config" in claude_text
    assert "before/after values" in claude_text


def test_manage_target_helpers_build_sorted_targets_and_fallback_selection():
    import mms_command_tools

    cfg = {
        "provider": {"default": "relay"},
        "account": {"defaults": {"claude": "claude-main"}},
        "providers": [
            {"id": "backup", "name": "Backup"},
            {"id": "relay", "name": "Relay"},
        ],
        "accounts": [
            {"id": "codex-alt", "cli": "codex", "name": "Codex Alt"},
            {"id": "claude-main", "cli": "claude", "name": "Claude Main"},
        ],
    }
    usage = {
        ("provider", "relay"): (2, "2026-05-28"),
        ("provider", "backup"): (5, "2026-05-27"),
        ("account", "claude-main"): (3, "2026-05-28"),
        ("account", "codex-alt"): (1, "2026-05-26"),
    }
    targets = mms_command_tools.build_manage_targets(
        cfg,
        default_provider_id="relay",
        resolve_provider_context=lambda _cfg, provider_id: {"base_url": "https://relay", "api_key": "k"} if provider_id == "relay" else {},
        usage_summary_for_runtime=lambda kind, runtime_id: usage[(kind, runtime_id)],
        probe_account_status=lambda account: {"summary": f"{account['cli']}:ok"},
    )

    assert [item["id"] for item in targets] == ["claude-main", "relay", "codex-alt", "backup"]
    assert targets[0]["summary"] == "官方通道 · CLAUDE / 默认"
    assert targets[1]["summary"] == "默认网关通道"
    assert targets[1]["status"] == "已配置"
    assert targets[3]["status"] == "未配置"

    class FakePanel:
        def __init__(self, body, **kwargs):
            self.body = body
            self.kwargs = kwargs

    class FakePrompt:
        calls = ["9", "2"]

        @classmethod
        def ask(cls, *args, **kwargs):
            return cls.calls.pop(0)

    console = _CollectingConsole()
    selected = mms_command_tools.select_manage_target_fallback(
        targets,
        ensure_rich=lambda: None,
        panel_cls=FakePanel,
        table_cls=_FakeTable,
        prompt_cls=FakePrompt,
        console=console,
    )

    table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert table.rows[0][0] == ("1", "官方", "Claude Main", "CLAUDE", "claude:ok", "3")
    assert selected["id"] == "relay"
    assert any("请输入 1-4 的编号" in str(item) for item in console.items)


def test_rescue_and_registry_tui_payload_helpers_preserve_actions():
    import mms_command_tools

    info_lines, actions = mms_command_tools.rescue_landing_tui_payload(
        "deepseek-v4-flash",
        [{"created_at": "2026-05-23T09:10:11+08:00", "failed_model": "gpt-5.5", "status_code": 429}],
        latest_fallback_event={
            "at": "2026-05-24T01:02:03+08:00",
            "model": "deepseek-v4-flash",
            "note": "rescue_hot_fallback provider=relay",
        },
        hot_fallback_enabled=True,
    )
    info = dict(info_lines)
    action_ids = [action_id for action_id, _label in actions]

    assert info["全局默认"] == "deepseek-v4-flash"
    assert info["Hot fallback"] == "开启"
    assert "1 个 packet" in info["最近失败"]
    assert "2026-05-23 09:10:11" in info["最近失败"]
    assert "2026-05-24 01:02:03" in info["最近 fallback 尝试"]
    assert "rescue_hot_fallback provider=relay" in info["最近 fallback 尝试"]
    assert action_ids[:3] == ["choose_route_default", "manual_default", "clear_default"]
    assert "disable_hot_fallback" in action_ids
    assert "view_packets" in action_ids

    title, registry_info, registry_actions = mms_command_tools.registry_truth_tui_payload(
        {
            "db_path": "/tmp/model-registry.sqlite",
            "counts": {"source_snapshot": 2, "model_identity": 39, "model_fact": 338},
            "source_freshness": {"due_count": 1},
            "latest_source_snapshot": {"source_path": "https://openrouter.ai/api/v1/models"},
        },
        localize=lambda zh, en: zh,
    )
    assert title == "模型真源 / Registry Truth"
    assert [label for label, _value in registry_info] == ["DB", "来源快照", "模型身份", "模型事实", "待刷新来源", "最新来源"]
    assert [action_id for action_id, _label in registry_actions][:4] == [
        "check_staleness",
        "refresh_due_sources",
        "scheduled_dry_run",
        "scheduled_no_network",
    ]
    assert ("doctor", "Registry Doctor / 状态") in registry_actions


def test_latest_rescue_hot_fallback_event_filters_recent_events():
    import mms_command_tools

    old_event = {
        "type": "fallback",
        "model": "deepseek-v4-flash",
        "note": "rescue_hot_fallback status=503",
    }
    latest_event = {
        "type": "fallback",
        "model": "gpt-5.5",
        "note": "rescue_hot_fallback status=429",
    }
    events = [
        {"type": "fallback", "note": "manual fallback"},
        old_event,
        {"type": "failure", "note": "rescue_hot_fallback status=503"},
        "bad-event",
        latest_event,
    ]

    assert mms_command_tools.latest_rescue_hot_fallback_event(
        get_recent_events=lambda limit: events,
    ) is latest_event
    assert mms_command_tools.latest_rescue_hot_fallback_event(
        get_recent_events=lambda limit: (_ for _ in ()).throw(RuntimeError("boom")),
    ) is None


def test_model_source_and_speed_labels_preserve_thresholds():
    import mms_command_tools

    assert mms_command_tools.model_source_label("remote") == "远端列表"
    assert mms_command_tools.model_source_label("fallback") == "内置回退"
    assert mms_command_tools.model_source_label("manual") == "手工列表"
    assert mms_command_tools.model_source_label("extra") == "手工补充"
    assert mms_command_tools.model_source_label("derived_alias") == "本地别名"
    assert mms_command_tools.model_source_label("custom") == "custom"
    assert mms_command_tools.model_source_label("") == "-"
    assert mms_command_tools.ttfb_label(None) == "暂无数据"
    assert mms_command_tools.ttfb_label(1199) == "很快"
    assert mms_command_tools.ttfb_label(1200) == "正常"
    assert mms_command_tools.ttfb_label(2500) == "偏慢"
    assert mms_command_tools.ttfb_label(4500) == "很慢"
    assert mms_command_tools.tps_label(None) == "暂无数据"
    assert mms_command_tools.tps_label(80) == "很快"
    assert mms_command_tools.tps_label(40) == "正常"
    assert mms_command_tools.tps_label(20) == "偏慢"
    assert mms_command_tools.tps_label(19.9) == "很慢"


def test_runtime_map_helpers_filter_invalid_and_disabled_entries():
    import mms_command_tools

    cfg = {
        "providers": [
            {"id": "relay", "name": "Relay"},
            {"name": "Missing ID"},
            "bad",
        ],
        "accounts": [
            {"id": "claude-main", "cli": "claude", "enabled": True},
            {"id": "claude-off", "cli": "claude", "enabled": False},
            {"id": "codex-main", "cli": "codex"},
            {"cli": "claude"},
            "bad",
        ],
    }

    assert list(mms_command_tools.provider_map(cfg)) == ["relay"]
    assert list(mms_command_tools.account_map(cfg)) == ["claude-main", "claude-off", "codex-main"]
    assert [item["id"] for item in mms_command_tools.accounts_for_cli(cfg, "claude")] == ["claude-main"]
    assert [item["id"] for item in mms_command_tools.accounts_for_cli(cfg, "codex")] == ["codex-main"]


def test_provider_endpoint_helpers_preserve_config_resolution_semantics():
    import mms_command_tools

    assert mms_command_tools.provider_label({}, default_provider_id="default") == "default"
    assert mms_command_tools.provider_label({"id": "relay", "name": "Relay"}, default_provider_id="default") == "Relay"
    assert mms_command_tools.provider_openai_base_url({"base_url": "https://relay.example"}) == "https://relay.example/v1"
    assert mms_command_tools.provider_openai_base_url({"base_url": "https://relay.example/v1/"}) == "https://relay.example/v1"
    assert mms_command_tools.provider_openai_base_url({"openai_base_url": "https://openai.example/v1/"}) == "https://openai.example/v1"
    assert mms_command_tools.provider_anthropic_base_url({"base_url": "https://anthropic.example", "protocols": "anthropic_messages"}) == "https://anthropic.example"
    assert mms_command_tools.provider_anthropic_base_url({"base_url": "https://relay.example", "protocols": ["openai_chat_completions"]}) == ""
    assert mms_command_tools.provider_has_configured_base_url({"base_url": "https://relay.example"}) is True
    assert mms_command_tools.provider_has_configured_base_url({}) is False
    assert mms_command_tools.provider_id_variants("crs_oracle-gpt") == ["crs_oracle-gpt", "crs-oracle-gpt", "crs_oracle_gpt"]
    assert mms_command_tools.provider_id_variants("") == []
    assert (
        mms_command_tools.resolve_config_provider_id(
            {"crs-oracle-gpt": {}, "backup": {}},
            "crs_oracle_gpt",
        )
        == "crs-oracle-gpt"
    )


def test_env_file_helpers_preserve_shell_parsing_and_paths(tmp_path):
    import mms_command_tools

    env_path = tmp_path / "credentials.sh"
    env_path.write_text(
        "\n".join(
            [
                "# comment",
                "export MMS_PROVIDER_RELAY_API_KEY='sk test'",
                'MMS_PROVIDER_RELAY_BASE_URL=\"https://relay.example/v1\"',
                "NO_EQUALS",
                "BROKEN='unterminated",
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert mms_command_tools.env_file_path("claude", env_dir=str(tmp_path)) == str(tmp_path / "claude.sh")
    assert mms_command_tools.shell_quote("a'b") == "'a'\"'\"'b'"
    assert mms_command_tools.parse_shell_value("'sk test'") == "sk test"
    assert mms_command_tools.parse_shell_value('"quoted"') == "quoted"
    assert mms_command_tools.parse_shell_value("'unterminated") == "unterminated"
    assert mms_command_tools.load_env_file(str(tmp_path / "missing.sh")) == {}
    assert mms_command_tools.load_env_file(str(env_path)) == {
        "MMS_PROVIDER_RELAY_API_KEY": "sk test",
        "MMS_PROVIDER_RELAY_BASE_URL": "https://relay.example/v1",
        "BROKEN": "unterminated",
    }


def test_provider_credentials_load_helper_preserves_env_file_legacy_precedence(tmp_path):
    import mms_command_tools

    credentials_path = tmp_path / "credentials.sh"
    credentials_path.write_text(
        "\n".join(
            [
                "export MMS_PROVIDER_DEFAULT_BASE_URL='https://file.default/v1/'",
                "export MMS_PROVIDER_DEFAULT_API_KEY='file-default-key'",
                "export MMS_PROVIDER_DEFAULT_OPENAI_BASE_URL='https://file.openai/v1/'",
                "export MMS_PROVIDER_DEFAULT_ANTHROPIC_BASE_URL='https://file.anthropic/'",
                "export MMS_PROVIDER_DEFAULT_OPENAI_API_KEY='file-openai-key'",
                "export MMS_API_BASE_URL='https://legacy-file.default/v1'",
                "export MMS_API_KEY='legacy-file-key'",
                "export MMS_PROVIDER_RELAY_BASE_URL='https://file.relay/v1/'",
                "export MMS_PROVIDER_RELAY_API_KEY='file-relay-key'",
            ]
        ),
        encoding="utf-8",
    )
    legacy_config_path = tmp_path / "config.toml"
    legacy_config_path.write_text("[api]\nbase_url = 'https://legacy.config/v1/'\napi_key = 'legacy-config-key'\n", encoding="utf-8")

    provider_env_name = lambda provider_id, suffix: mms_command_tools.provider_env_name(
        provider_id,
        suffix,
        default_provider_id="default",
    )
    env_creds = mms_command_tools.load_provider_credentials(
        "default",
        default_provider_id="default",
        provider_env_name=provider_env_name,
        api_url_env_name="MMS_API_BASE_URL",
        api_key_env_name="MMS_API_KEY",
        credentials_paths=(str(credentials_path),),
        load_env_file=mms_command_tools.load_env_file,
        active_config_path=lambda: str(legacy_config_path),
        environ={
            "MMS_PROVIDER_DEFAULT_BASE_URL": "https://env.default/v1/ ",
            "MMS_PROVIDER_DEFAULT_API_KEY": " env-key ",
            "MMS_PROVIDER_DEFAULT_OPENAI_API_KEY": " env-openai-key ",
        },
    )
    assert env_creds == {
        "base_url": "https://env.default/v1",
        "openai_base_url": "https://file.openai/v1",
        "anthropic_base_url": "https://file.anthropic",
        "api_key": "env-key",
        "openai_api_key": "env-openai-key",
    }

    legacy_creds = mms_command_tools.load_provider_credentials(
        "default",
        default_provider_id="default",
        provider_env_name=provider_env_name,
        api_url_env_name="MMS_API_BASE_URL",
        api_key_env_name="MMS_API_KEY",
        credentials_paths=(str(tmp_path / "missing.sh"),),
        load_env_file=mms_command_tools.load_env_file,
        active_config_path=lambda: str(legacy_config_path),
        environ={},
    )
    assert legacy_creds["base_url"] == "https://legacy.config/v1"
    assert legacy_creds["api_key"] == "legacy-config-key"

    relay_creds = mms_command_tools.load_provider_credentials(
        "relay",
        default_provider_id="default",
        provider_env_name=provider_env_name,
        api_url_env_name="MMS_API_BASE_URL",
        api_key_env_name="MMS_API_KEY",
        credentials_paths=(str(credentials_path),),
        load_env_file=mms_command_tools.load_env_file,
        active_config_path=lambda: str(legacy_config_path),
        environ={},
    )
    assert relay_creds["base_url"] == "https://file.relay/v1"
    assert relay_creds["api_key"] == "file-relay-key"


def test_provider_credentials_save_helper_preserves_file_shape_and_refresh(tmp_path):
    import stat

    import mms_command_tools

    credentials_path = tmp_path / "credentials.sh"
    credentials_path.write_text(
        "\n".join(
            [
                "export KEEP='1'",
                "export MMS_PROVIDER_DEFAULT_OPENAI_BASE_URL='https://old.openai/v1'",
                "export MMS_PROVIDER_DEFAULT_ANTHROPIC_BASE_URL='https://old.anthropic'",
                "export MMS_PROVIDER_DEFAULT_OPENAI_API_KEY='old-openai-key'",
            ]
        ),
        encoding="utf-8",
    )
    refresh_calls = []
    provider_env_name = lambda provider_id, suffix: mms_command_tools.provider_env_name(
        provider_id,
        suffix,
        default_provider_id="default",
    )

    mms_command_tools.save_provider_credentials(
        "default",
        "https://new.default/v1/",
        "new-key",
        openai_base_url="",
        anthropic_base_url="https://new.anthropic/",
        openai_api_key=None,
        config_dir=str(tmp_path / "config"),
        credentials_path=str(credentials_path),
        provider_env_name=provider_env_name,
        default_provider_id="default",
        api_url_env_name="MMS_API_BASE_URL",
        api_key_env_name="MMS_API_KEY",
        load_env_file=mms_command_tools.load_env_file,
        shell_quote=mms_command_tools.shell_quote,
        trigger_routes_export_after_credentials_write=lambda: refresh_calls.append("refresh"),
    )

    text = credentials_path.read_text(encoding="utf-8")
    assert "export KEEP='1'" in text
    assert "export MMS_PROVIDER_DEFAULT_BASE_URL='https://new.default/v1'" in text
    assert "export MMS_PROVIDER_DEFAULT_API_KEY='new-key'" in text
    assert "export MMS_PROVIDER_DEFAULT_ANTHROPIC_BASE_URL='https://new.anthropic'" in text
    assert "MMS_PROVIDER_DEFAULT_OPENAI_BASE_URL" not in text
    assert "MMS_PROVIDER_DEFAULT_OPENAI_API_KEY" not in text
    assert "export MMS_API_BASE_URL='https://new.default/v1'" in text
    assert "export MMS_API_KEY='new-key'" in text
    assert refresh_calls == ["refresh"]
    assert stat.S_IMODE(credentials_path.stat().st_mode) == 0o600

    mms_command_tools.save_provider_credentials(
        "relay",
        "https://relay.example/v1",
        "relay-key",
        openai_base_url="https://relay-openai.example/v1",
        openai_api_key="relay-openai-key",
        config_dir=str(tmp_path / "config"),
        credentials_path=str(credentials_path),
        provider_env_name=provider_env_name,
        default_provider_id="default",
        api_url_env_name="MMS_API_BASE_URL",
        api_key_env_name="MMS_API_KEY",
        load_env_file=mms_command_tools.load_env_file,
        shell_quote=mms_command_tools.shell_quote,
        trigger_routes_export_after_credentials_write=lambda: refresh_calls.append("refresh"),
    )
    text = credentials_path.read_text(encoding="utf-8")
    assert "export MMS_PROVIDER_RELAY_OPENAI_BASE_URL='https://relay-openai.example/v1'" in text
    assert "export MMS_PROVIDER_RELAY_OPENAI_API_KEY='relay-openai-key'" in text
    assert text.count("export MMS_API_BASE_URL=") == 1
    assert refresh_calls == ["refresh", "refresh"]


def test_config_truthy_and_csv_helpers_preserve_cli_prompt_semantics():
    import pytest

    import mms_command_tools

    console = _CollectingConsole()

    assert mms_command_tools.config_truthy(None, default=True) is True
    assert mms_command_tools.config_truthy(None, default=False) is False
    assert mms_command_tools.config_truthy(True) is True
    assert mms_command_tools.config_truthy("disabled") is False
    assert mms_command_tools.config_truthy("yes") is True
    assert mms_command_tools.parse_csv_values(" codex, claude, codex, ,opencode ") == ["codex", "claude", "opencode"]
    assert mms_command_tools.parse_csv_values("codex,claude", allowed_values=["codex", "claude"]) == ["codex", "claude"]
    with pytest.raises(SystemExit) as exc_info:
        mms_command_tools.parse_csv_values("codex,bad", allowed_values=["codex", "claude"], console=console)
    assert exc_info.value.code == 1
    assert console.items == [
        "[red]不支持的值: bad[/red]",
        "[dim]可选值: codex, claude[/dim]",
    ]


def test_model_family_visibility_helpers_preserve_display_filter_semantics():
    import mms_command_tools

    model_families = [
        {"family": "Claude", "keywords": ("claude",), "category": "Claude 系 ⭐"},
        {"family": "GPT", "keywords": ("gpt-", "codex-"), "category": "GPT 系"},
        {"family": "Qwen", "keywords": ("qwen",), "category": "国产系"},
        {"family": "Kimi", "keywords": ("kimi", "k2.6"), "category": "国产系"},
    ]

    def infer_family(model_id):
        return mms_command_tools.infer_model_family(model_id, model_families=model_families)

    assert mms_command_tools.infer_model_family("anthropic/claude-opus-4.7", model_families=model_families) == (
        "Claude",
        "Claude 系 ⭐",
    )
    assert mms_command_tools.infer_model_family("deepseek-v4-pro", model_families=model_families) == ("其他", "其他")
    assert mms_command_tools.model_info_looks_domestic(
        {"model": "gpt-5.5", "backup": "qwen3.6-plus"},
        infer_model_family=infer_family,
        domestic_model_families={"Qwen", "Kimi"},
        domestic_model_keywords=("qwen", "kimi"),
    ) is True
    assert mms_command_tools.mms_model_visible(
        "hidden-model",
        infer_model_family=infer_family,
        hidden_models={"hidden-model"},
        hidden_model_families=set(),
    ) is False
    visible = mms_command_tools.filter_visible_models(
        [" claude-sonnet-4.5 ", "", "hidden-model", "qwen3.6-plus"],
        mms_model_visible=lambda model_id: model_id != "hidden-model",
    )
    assert visible == ["claude-sonnet-4.5", "qwen3.6-plus"]
    assert mms_command_tools.model_info_has_visible_models(
        {"opus": "hidden-model", "sonnet": "claude-sonnet-4.5"},
        mms_model_visible=lambda model_id: model_id != "hidden-model",
    ) is True
    assert mms_command_tools.model_info_has_visible_models(
        {"model": "hidden-model"},
        mms_model_visible=lambda model_id: model_id != "hidden-model",
    ) is False


def test_preference_primitive_helpers_preserve_allowlist_semantics():
    import mms_command_tools

    assert mms_command_tools.merge_dicts(
        {"launch": {"defaults": {"bypass": False}, "cli": {"codex": {"reasoning_effort": "low"}}}},
        {"launch": {"defaults": {"thinking_mode": "enable"}}},
    ) == {
        "launch": {
            "defaults": {"bypass": False, "thinking_mode": "enable"},
            "cli": {"codex": {"reasoning_effort": "low"}},
        }
    }
    assert mms_command_tools.pref_bool("enabled") is True
    assert mms_command_tools.pref_bool("off") is False
    assert mms_command_tools.pref_bool("maybe") is None
    assert mms_command_tools.pref_enable_disable(True) == "enable"
    assert mms_command_tools.pref_enable_disable("disabled") == "disable"
    assert mms_command_tools.pref_enable_disable("maybe") == ""
    assert mms_command_tools.pref_reasoning_effort("XHIGH") == "xhigh"
    assert mms_command_tools.pref_reasoning_effort("extreme") == ""
    assert mms_command_tools.pref_agent_pack("everything_claude_code") == "ecc"
    assert mms_command_tools.pref_agent_pack("oh-my-claude-code") == "omc"
    assert mms_command_tools.pref_agent_pack("off") == "none"
    assert mms_command_tools.sanitize_surface_list(["web-access", "web-access", "", None, "xmem"]) == ["web-access", "xmem"]
    assert mms_command_tools.sanitize_disabled_session_surfaces(
        {"skill": ["web-access"], "mcps": "pilot", "hook": ["/tmp/a", "/tmp/a"], "unknown": ["drop"]}
    ) == {
        "skills": ["web-access"],
        "mcp": ["pilot"],
        "hooks": ["/tmp/a"],
    }


def test_preference_allowlist_sanitizers_preserve_runtime_shape(tmp_path):
    import mms_command_tools

    skill_root = tmp_path / "web-access"
    asset_keys = {"web_access": "web_access", "web-access": "web_access", "xmem": "xmem"}
    raw = {
        "launch": {
            "defaults": {
                "thinking_mode": "enabled",
                "reasoning_effort": "xhigh",
                "caveman_mode": "off",
                "nsr_mode": True,
                "bypass": "no",
                "agent_pack": "oh-my-claude-code",
                "api_key": "ignored",
            },
            "cli": {
                "Codex": {"reasoning_effort": "low", "disabled_session_surfaces": {"skills": ["agent-browser"]}},
                "gemini": {"bypass": True},
                "unknown": {"bypass": True},
            },
        },
        "session_surfaces": {"disabled": {"mcps": ["pilot"], "hook": "/tmp/drop.sh"}},
        "assets": {"roots": {"web-access": str(skill_root), "credentials": "/tmp/ignored"}},
        "provider": {"base_url": "https://ignored.example"},
    }

    assert mms_command_tools.sanitize_launch_preferences(raw["launch"]["defaults"]) == {
        "thinking_mode": "enable",
        "reasoning_effort": "xhigh",
        "caveman_mode": "disable",
        "nsr_mode": "enable",
        "bypass": False,
        "agent_pack": "omc",
        "ecc_mode": "disable",
        "omc_mode": "enable",
    }
    assert mms_command_tools.sanitize_asset_roots(
        {"web-access": str(skill_root), "credentials": "/tmp/ignored"},
        asset_root_keys=asset_keys,
    ) == {"web_access": str(skill_root)}
    assert mms_command_tools.sanitize_user_preferences(raw, cli_names=["claude", "codex"], asset_root_keys=asset_keys) == {
        "launch": {
            "defaults": {
                "thinking_mode": "enable",
                "reasoning_effort": "xhigh",
                "caveman_mode": "disable",
                "nsr_mode": "enable",
                "bypass": False,
                "agent_pack": "omc",
                "ecc_mode": "disable",
                "omc_mode": "enable",
            },
            "cli": {
                "codex": {"reasoning_effort": "low", "disabled_session_surfaces": {"skills": ["agent-browser"]}},
                "gemini": {"bypass": True},
            },
        },
        "session_surfaces": {"disabled": {"mcp": ["pilot"], "hooks": ["/tmp/drop.sh"]}},
        "assets": {"roots": {"web_access": str(skill_root)}},
    }


def test_preference_runtime_overlay_helpers_preserve_merge_order():
    import mms_command_tools

    prefs = {
        "launch": {
            "defaults": {
                "thinking_mode": "enable",
                "reasoning_effort": "xhigh",
                "disabled_session_surfaces": {"skills": ["token-saver"]},
            },
            "cli": {
                "codex": {
                    "reasoning_effort": "low",
                    "disabled_session_surfaces": {"mcp": ["pilot"], "skills": ["token-saver"]},
                }
            },
        },
        "session_surfaces": {"disabled": {"skills": ["web-access"], "hooks": ["/tmp/drop.sh"]}},
    }
    runtime = {
        "id": "relay",
        "reasoning_effort": "medium",
        "disabled_session_surfaces": {"skills": ["existing", "web-access"]},
    }

    assert mms_command_tools.merge_disabled_session_surfaces(
        {"skills": ["existing", "web-access"]},
        {"skills": ["web-access", "token-saver"], "mcps": ["pilot"]},
    ) == {"mcp": ["pilot"], "skills": ["existing", "web-access", "token-saver"]}
    assert mms_command_tools.preference_runtime_overlay(prefs, "codex") == {
        "thinking_mode": "enable",
        "reasoning_effort": "low",
        "disabled_session_surfaces": {
            "skills": ["web-access", "token-saver"],
            "hooks": ["/tmp/drop.sh"],
            "mcp": ["pilot"],
        },
    }

    result = mms_command_tools.runtime_with_launch_preferences(
        {"_mms_preferences": prefs},
        runtime,
        "codex",
        load_user_preferences=lambda: (_ for _ in ()).throw(AssertionError("unused")),
    )
    assert result is not runtime
    assert runtime["reasoning_effort"] == "medium"
    assert result["thinking_mode"] == "enable"
    assert result["reasoning_effort"] == "low"
    assert result["disabled_session_surfaces"] == {
        "skills": ["existing", "web-access", "token-saver"],
        "hooks": ["/tmp/drop.sh"],
        "mcp": ["pilot"],
    }
    assert result["_mms_preferences_applied"] is True
    assert mms_command_tools.runtime_with_launch_preferences(
        {},
        {"_mms_preferences_applied": True},
        "codex",
        load_user_preferences=lambda: prefs,
    ) == {"_mms_preferences_applied": True}
    assert mms_command_tools.runtime_with_launch_preferences(
        {},
        "not-runtime",
        "codex",
        load_user_preferences=lambda: prefs,
    ) == "not-runtime"


def test_usage_runtime_helpers_filter_sort_and_summarize_sources():
    import mms_command_tools

    stats = {
        "last_by_cli": {
            "claude": {
                "cli": "claude",
                "model_info": {"model": "gpt-5.5"},
            }
        },
        "sources": {
            "old": {
                "runtime_kind": "provider",
                "id": "relay",
                "cli": "claude",
                "launches": 2,
                "last_used_at": "2026-05-27T10:00:00Z",
            },
            "new": {
                "runtime_kind": "provider",
                "id": "relay",
                "cli": "codex",
                "launches": 5,
                "last_used_at": "2026-05-28T10:00:00Z",
            },
            "other": {
                "runtime_kind": "account",
                "id": "relay",
                "cli": "codex",
                "launches": 7,
                "last_used_at": "2026-05-29T10:00:00Z",
            },
        }
    }
    rows = mms_command_tools.usage_rows_for_runtime(
        "provider",
        "relay",
        load_usage_stats=lambda: stats,
    )
    assert [item["cli"] for item in rows] == ["codex", "claude"]
    assert mms_command_tools.usage_summary_for_runtime(
        "provider",
        "relay",
        usage_rows_for_runtime=lambda kind, runtime_id: rows,
    ) == (7, "2026-05-28T10:00:00Z")


def test_vision_sidecar_candidate_helpers_preserve_order_and_overrides():
    import mms_command_tools

    assert mms_command_tools.vision_sidecar_model_candidates_for_provider("direct-mimo") == ["mimo-v2.5", "mimo-v2-omni"]
    assert mms_command_tools.vision_sidecar_model_candidates_for_provider("newapi-personal-kimi") == ["K2.6", "K2.6-code-preview", "kimi-k2.5"]
    assert mms_command_tools.vision_sidecar_model_candidates_for_provider("direct-qwen") == ["qwen3.6-plus", "qwen3.6-flash"]
    assert mms_command_tools.vision_sidecar_model_candidates_for_provider("other")[:3] == ["mimo-v2.5", "mimo-v2-omni", "K2.6"]

    configured = {
        "routes": [
            {"provider": "configured", "vision_model": "vision-a"},
            {"provider_id": "configured", "model": "vision-a"},
            {"provider_id": "second", "model": "vision-b"},
            "bad",
        ]
    }
    assert mms_command_tools.vision_sidecar_candidate_pairs(configured, ["direct-mimo"])[:3] == [
        ("configured", "vision-a"),
        ("second", "vision-b"),
        ("mimo-direct-anthropic", "mimo-v2.5"),
    ]
    assert mms_command_tools.vision_sidecar_candidate_pairs({}, ["a", "b"], explicit_model="chosen") == [
        ("a", "chosen"),
        ("b", "chosen"),
    ]
    assert mms_command_tools.vision_sidecar_candidate_pairs({}, ["ignored"], explicit_provider_id="direct-qwen") == [
        ("direct-qwen", "qwen3.6-plus"),
        ("direct-qwen", "qwen3.6-flash"),
    ]


def test_runtime_with_vision_sidecar_helper_preserves_selection_rules():
    import mms_command_tools

    cfg = {
        "providers": [
            {"id": "direct-mimo"},
            {"id": "direct-kimi"},
        ]
    }
    providers = {
        "direct-mimo": {
            "id": "direct-mimo",
            "enabled": True,
            "api_key": "sk-mimo",
            "anthropic_base_url": "https://mimo.example/anthropic/",
            "fallback_models": ["mimo-v2.5"],
        },
        "direct-kimi": {
            "id": "direct-kimi",
            "enabled": True,
            "api_key": "sk-kimi",
            "anthropic_base_url": "https://kimi.example/anthropic/",
            "fallback_models": ["K2.6"],
        },
    }
    runtime = mms_command_tools.runtime_with_vision_sidecar(
        cfg,
        {"id": "relay", "auth_mode": "api_key"},
        config_truthy=lambda value, default=True: bool(default if value is None else value),
        provider_map=lambda cfg_arg: {item["id"]: item for item in cfg_arg["providers"]},
        resolve_config_provider_id=lambda provider_defs, provider_id: provider_id if provider_id in provider_defs else "",
        resolve_provider_context=lambda _cfg, provider_id: providers[provider_id],
        provider_anthropic_base_url=lambda provider: str(provider.get("anthropic_base_url") or "").rstrip("/"),
        load_probe_file_cache=lambda *_args, **_kwargs: None,
        provider_effective_models=lambda provider, _cached_models, _cfg: provider.get("fallback_models", []),
        environ={},
    )

    assert runtime["vision_sidecar"] == {
        "enabled": True,
        "provider_id": "direct-mimo",
        "provider_profile": "",
        "model": "mimo-v2.5",
        "anthropic_base_url": "https://mimo.example/anthropic",
        "api_key": "sk-mimo",
        "proxy_url": "",
        "no_proxy": "",
    }
    assert mms_command_tools.runtime_with_vision_sidecar(
        {"vision_sidecar": {"enabled": False}, "providers": [{"id": "direct-mimo"}]},
        {"id": "relay", "auth_mode": "api_key"},
        config_truthy=lambda value, default=True: bool(default if value is None else value),
        provider_map=lambda _cfg: {"direct-mimo": {}},
        resolve_config_provider_id=lambda _defs, provider_id: provider_id,
        resolve_provider_context=lambda *_args: providers["direct-mimo"],
        provider_anthropic_base_url=lambda provider: provider.get("anthropic_base_url", ""),
        load_probe_file_cache=lambda *_args, **_kwargs: None,
        provider_effective_models=lambda *_args: [],
        environ={},
    ) == {"id": "relay", "auth_mode": "api_key"}


def test_model_capability_helpers_preserve_native_bridge_and_tags():
    import mms_command_tools

    def infer_family(model_name):
        normalized = str(model_name or "").lower()
        if normalized.startswith("claude-"):
            return "Claude", "Claude 系 ⭐"
        if normalized.startswith(("gpt-", "o1-", "o3-", "o4-", "codex-")):
            return "GPT", "GPT 系"
        if "qwen" in normalized:
            return "Qwen", "国产系"
        return "其他", "其他"

    assert mms_command_tools.native_clis_for_model("claude-sonnet-4.5") == ["claude"]
    assert mms_command_tools.native_clis_for_model("gpt-5.5") == ["codex"]
    assert mms_command_tools.native_clis_for_model("gemini-3.1-pro-preview") == []
    assert mms_command_tools.model_matches_account_cli("claude", "Claude-Sonnet-4.5") is True
    assert mms_command_tools.model_matches_account_cli("codex", "openai/gpt-5.5") is False
    assert mms_command_tools.model_matches_account_cli("gemini", "gemini-3.1-pro-preview") is True
    assert mms_command_tools.model_matches_account_cli("agy", "gpt-5.5") is False
    hints = {"codex": ("gpt-", "codex-"), "claude": ("claude-",)}
    models = ["gpt-5.5", "claude-sonnet-4.5", "qwen3.6-plus", "codex-mini"]
    assert mms_command_tools.model_matches_cli_family(
        "codex",
        "openai/gpt-5.5",
        cli_model_family_hints=hints,
    ) is True
    assert mms_command_tools.models_for_cli_family(
        "codex",
        models,
        cli_model_family_hints=hints,
    ) == ["gpt-5.5", "codex-mini"]
    assert mms_command_tools.provider_models_for_cli(
        "opencode",
        models,
        cli_model_family_hints=hints,
    ) == models
    assert mms_command_tools.provider_supports_cli_name(
        {"id": "kimi-relay", "supported_clis": ["codex", "claude"]},
        "codex",
    ) is False
    assert mms_command_tools.provider_supports_cli_name(
        {"id": "relay", "supported_clis": "codex"},
        "codex",
    ) is True
    assert mms_command_tools.provider_supports_cli_name(
        {"id": "relay", "supported_clis": ["claude"], "protocols": "anthropic_messages"},
        "opencode",
    ) is True
    assert mms_command_tools.provider_supports_cli_name(
        {"id": "relay", "supported_clis": ["codex"], "protocols": ["openai_chat_completions"]},
        "opencode",
    ) is True
    assert mms_command_tools.provider_supports_cli_name(
        {"id": "relay", "supported_clis": ["claude"]},
        "agy",
    ) is False
    assert mms_command_tools.provider_supports_model_for_cli(
        {"supported_clis": ["claude"]},
        "claude",
        "claude-sonnet-4.5",
        model_matches_account_cli=mms_command_tools.model_matches_account_cli,
        provider_supports_cli_name=mms_command_tools.provider_supports_cli_name,
        bridge_clis_for_model=lambda _model: ["claude"],
    ) is True
    assert mms_command_tools.provider_supports_model_for_cli(
        {"supported_clis": ["claude"]},
        "claude",
        "qwen3.6-plus",
        model_matches_account_cli=mms_command_tools.model_matches_account_cli,
        provider_supports_cli_name=mms_command_tools.provider_supports_cli_name,
        bridge_clis_for_model=lambda _model: ["claude"],
    ) is True
    assert mms_command_tools.provider_supports_model_for_cli(
        {"supported_clis": ["codex"]},
        "claude",
        "qwen3.6-plus",
        model_matches_account_cli=mms_command_tools.model_matches_account_cli,
        provider_supports_cli_name=mms_command_tools.provider_supports_cli_name,
        bridge_clis_for_model=lambda _model: [],
    ) is False
    assert mms_command_tools.is_installed_mms_layout(
        "/Users/xin/.mms/mms_core.py",
        real_user_home=lambda: "/Users/xin",
    ) is True
    assert mms_command_tools.is_installed_mms_layout(
        "/repo/multi-model-switch/mms_core.py",
        real_user_home=lambda: "/Users/xin",
    ) is False
    assert mms_command_tools.default_gpt_reasoning_effort(
        module_path="/repo/mms_core.py",
        is_installed_mms_layout=lambda _path: False,
    ) == "xhigh"
    assert mms_command_tools.default_gpt_reasoning_effort(
        module_path="/Users/xin/.mms/mms_core.py",
        is_installed_mms_layout=lambda _path: True,
    ) == "high"
    assert mms_command_tools.default_reasoning_effort_for_model_info(
        {"model": "openai/gpt-5.5", "subagent": "claude-sonnet-4.5"},
        model_matches_account_cli=mms_command_tools.model_matches_account_cli,
        default_gpt_reasoning_effort=lambda: "xhigh",
    ) == "xhigh"
    assert mms_command_tools.default_reasoning_effort_for_model_info(
        {"model": "claude-sonnet-4.5", "subagent": "gpt-5.5"},
        model_matches_account_cli=mms_command_tools.model_matches_account_cli,
        default_gpt_reasoning_effort=lambda: "xhigh",
    ) == "high"
    assert mms_command_tools.model_context_window(
        "runtime-approved-model[1m]",
        resolve_model_capabilities=lambda _model: {
            "context_window_tokens": 555_000,
            "sources": {"context_window_tokens": "approved_facts"},
        },
        model_context_windows=lambda: {"runtime-approved-model": 128_000},
    ) == 555_000
    assert mms_command_tools.model_context_window(
        "gpt-5.5",
        resolve_model_capabilities=lambda _model: (_ for _ in ()).throw(RuntimeError("resolver unavailable")),
        model_context_windows=lambda: {"gpt-5.5": 400_000},
    ) == 400_000
    assert mms_command_tools.model_context_window(
        "GPT-5.5",
        resolve_model_capabilities=lambda _model: {},
        model_context_windows=lambda: {"gpt-5.5": 400_000},
    ) == 400_000
    assert mms_command_tools.model_context_window(
        "",
        resolve_model_capabilities=lambda _model: {},
        model_context_windows=lambda: {"gpt-5.5": 400_000},
    ) is None
    assert mms_command_tools.model_context_window(
        "missing",
        resolve_model_capabilities=lambda _model: {},
        model_context_windows=lambda: (_ for _ in ()).throw(RuntimeError("windows unavailable")),
    ) is None
    assert mms_command_tools.bridge_clis_for_model("qwen3.6-plus", infer_model_family=infer_family) == ["claude", "codex"]
    assert mms_command_tools.model_cli_modes("gpt-5.5", infer_model_family=infer_family) == {
        "claude": "bridge",
        "codex": "native",
    }
    assert mms_command_tools.model_cli_summary("claude-sonnet-4.5", infer_model_family=infer_family) == "claude:native, codex:bridge"

    tags = mms_command_tools.model_capability_tags(
        "qwen3.6-plus",
        infer_model_family=infer_family,
        model_context_window=lambda _model: 1_000_000,
        reasoning_model_hints=("gpt-5",),
        tool_use_families={"Claude", "GPT", "Qwen"},
        vision_capable_model_names={"qwen3.6-plus"},
        vision_capable_model_hints=("gemini-",),
    )
    assert tags == ["vision", "tool_use", "long_context", "bridge_required"]
    assert (
        mms_command_tools.model_capability_summary(
            "qwen3.6-plus",
            model_capability_tags=lambda model_id: tags if model_id == "qwen3.6-plus" else [],
        )
        == "vision, tool_use, long_context, bridge_required"
    )


def test_probe_file_cache_helpers_preserve_ttl_normalization_and_cleanup(tmp_path):
    import json
    import os

    import mms_command_tools

    cache_dir = str(tmp_path / "cache")
    cache_path = lambda provider_id: mms_command_tools.probe_file_cache_path(
        provider_id,
        probe_file_cache_dir=cache_dir,
    )

    assert cache_path("relay") == str(tmp_path / "cache" / "models_relay.json")
    assert mms_command_tools.probe_cache_age(
        "missing",
        probe_file_cache_path=cache_path,
        path_exists=lambda _path: False,
    ) is None
    assert mms_command_tools.probe_cache_age(
        "relay",
        probe_file_cache_path=cache_path,
        path_exists=lambda _path: True,
        getmtime=lambda _path: 100.0,
        time_func=lambda: 130.0,
    ) == 30.0

    ignored = {"base_source": "live", "raw_models": ["gpt-5.5"]}
    mms_command_tools.save_probe_file_cache(
        "relay",
        ignored,
        probe_file_cache_dir=cache_dir,
        probe_file_cache_path=cache_path,
    )
    assert not os.path.exists(cache_path("relay"))

    mms_command_tools.save_probe_file_cache(
        "relay",
        {
            "base_source": "remote",
            "raw_models": [" gpt-5.5 ", "", 42],
            "working_url": "https://relay.example.com/v1",
        },
        probe_file_cache_dir=cache_dir,
        probe_file_cache_path=cache_path,
    )
    assert json.loads(open(cache_path("relay"), encoding="utf-8").read())["base_source"] == "remote"

    def normalize_models(raw):
        return [str(item).strip() for item in raw if str(item).strip()]

    fresh = mms_command_tools.load_probe_file_cache(
        "relay",
        probe_file_cache_path=cache_path,
        normalize_model_id_list=normalize_models,
        file_cache_ttl=60,
        negative_ttl=10,
        getmtime=lambda _path: 990.0,
        time_func=lambda: 1000.0,
    )
    assert fresh["raw_models"] == ["gpt-5.5", "42"]
    assert fresh["models"] == ["gpt-5.5", "42"]
    assert fresh["error"] is None
    assert fresh["error_kind"] is None
    assert fresh["details"] == []
    assert fresh["is_stale"] is False
    assert mms_command_tools.base_probe_result_from_cache("relay", fresh) == {
        "provider_id": "relay",
        "raw_models": ["gpt-5.5", "42"],
        "models": ["gpt-5.5", "42"],
        "error": None,
        "error_kind": None,
        "working_url": "https://relay.example.com/v1",
        "details": [],
        "base_source": "remote",
        "is_stale": False,
    }
    assert mms_command_tools.load_probe_file_cache(
        "relay",
        probe_file_cache_path=cache_path,
        normalize_model_id_list=normalize_models,
        file_cache_ttl=60,
        negative_ttl=10,
        getmtime=lambda _path: 900.0,
        time_func=lambda: 1000.0,
    ) is None
    stale = mms_command_tools.load_probe_file_cache(
        "relay",
        allow_stale=True,
        probe_file_cache_path=cache_path,
        normalize_model_id_list=normalize_models,
        file_cache_ttl=60,
        negative_ttl=10,
        getmtime=lambda _path: 900.0,
        time_func=lambda: 1000.0,
    )
    assert stale["is_stale"] is True

    probe_cache = {"relay": {"models": ["old"]}}
    mms_command_tools.invalidate_probe_cache(
        "relay",
        probe_cache=probe_cache,
        probe_file_cache_path=cache_path,
    )
    assert probe_cache == {}
    assert not os.path.exists(cache_path("relay"))


def test_runtime_normalization_helpers_preserve_provider_and_model_semantics():
    import mms_command_tools

    assert mms_command_tools.normalize_provider_id_input(" CRS Oracle! ", default_provider_id="default") == "crs-oracle"
    assert mms_command_tools.normalize_provider_id_input("!!!", default_provider_id="default") == "default"
    assert mms_command_tools.sanitize_provider_id("crs-oracle/gpt", default_provider_id="default") == "CRS_ORACLE_GPT"
    assert mms_command_tools.sanitize_provider_id("!!!", default_provider_id="default") == "DEFAULT"
    assert mms_command_tools.normalize_model_id_list("gpt-5.5, ,gpt-5.4,gpt-5.5") == ["gpt-5.5", "gpt-5.4"]
    assert mms_command_tools.normalize_model_id_list([" a ", None, "a", "b"]) == ["a", "b"]
    assert mms_command_tools.unique_runtime_id({"relay", "relay-2"}, "relay") == "relay-3"
    assert mms_command_tools.unique_runtime_id(set(), "") == "default"
    assert mms_command_tools.normalize_models_endpoint("") == "/models"
    assert mms_command_tools.normalize_models_endpoint("manual") == "manual"
    assert mms_command_tools.normalize_models_endpoint("api/models") == "/api/models"
    assert mms_command_tools.normalize_models_endpoint("/v1/models") == "/v1/models"
    assert (
        mms_command_tools.provider_env_name("crs-oracle/gpt", "API_KEY", default_provider_id="default")
        == "MMS_PROVIDER_CRS_ORACLE_GPT_API_KEY"
    )
    assert (
        mms_command_tools.provider_env_value(
            "crs-oracle/gpt",
            "API_KEY",
            default_provider_id="default",
            environ={"MMS_PROVIDER_CRS_ORACLE_GPT_API_KEY": " key "},
        )
        == "key"
    )


def test_runtime_priority_and_supported_cli_helpers_preserve_normalization():
    import mms_command_tools

    model_families = [{"family": "GPT"}, {"family": "Claude"}]
    cli_names = ["claude", "codex", "opencode"]
    legacy_aliases = {"provider", "gateway"}

    assert mms_command_tools.normalize_supported_clis(
        "provider",
        protocols=["anthropic_messages", "openai_chat_completions"],
        cli_names=cli_names,
        legacy_provider_cli_aliases=legacy_aliases,
    ) == ["claude", "codex"]
    assert mms_command_tools.normalize_supported_clis(
        ["codex", "unknown", "codex", "opencode"],
        protocols=[],
        cli_names=cli_names,
        legacy_provider_cli_aliases=legacy_aliases,
    ) == ["codex", "opencode"]
    assert mms_command_tools.normalize_priority("7", default_priority=50) == 7
    assert mms_command_tools.normalize_priority("0", default_priority=50) == 1
    assert mms_command_tools.normalize_priority("bad", default_priority=50) == 50
    assert mms_command_tools.canonical_model_family("gpt", model_families=model_families) == "GPT"
    assert mms_command_tools.canonical_model_family("unknown", model_families=model_families) == ""
    assert mms_command_tools.normalize_family_priority_overrides(
        {"gpt": "9", "Claude": 0, "unknown": 99},
        model_families=model_families,
        default_priority=50,
    ) == {"GPT": 9, "Claude": 1}
    assert mms_command_tools.normalize_family_priority_overrides([], model_families=model_families, default_priority=50) == {}
    priority_runtime = {"priority": "7", "family_priority_overrides": {"GPT": "11"}}
    priority_kwargs = {
        "canonical_model_family": lambda value: mms_command_tools.canonical_model_family(value, model_families=model_families),
        "normalize_priority": lambda value: mms_command_tools.normalize_priority(value, default_priority=50),
        "default_priority": 50,
    }
    assert mms_command_tools.runtime_priority_for_family(priority_runtime, "gpt", **priority_kwargs) == 11
    assert mms_command_tools.runtime_priority_for_family(priority_runtime, "Claude", **priority_kwargs) == 7
    assert mms_command_tools.runtime_priority_for_family("bad", "GPT", **priority_kwargs) == 50
    assert mms_command_tools.runtime_priority_for_model(
        priority_runtime,
        "gpt-5.5",
        infer_model_family=lambda model_name: ("GPT", "GPT 系") if model_name.startswith("gpt-") else ("", ""),
        runtime_priority_for_family=lambda runtime, family: mms_command_tools.runtime_priority_for_family(
            runtime,
            family,
            **priority_kwargs,
        ),
    ) == 11
    prioritized = mms_command_tools.runtime_with_priority(
        priority_runtime,
        model_name="gpt-5.5",
        canonical_model_family=priority_kwargs["canonical_model_family"],
        infer_model_family=lambda model_name: ("GPT", "GPT 系") if model_name.startswith("gpt-") else ("", ""),
        runtime_priority_for_family=lambda runtime, family: mms_command_tools.runtime_priority_for_family(
            runtime,
            family,
            **priority_kwargs,
        ),
        normalize_priority=priority_kwargs["normalize_priority"],
        default_priority=50,
    )
    assert prioritized == {"priority": 11, "family_priority_overrides": {"GPT": "11"}, "priority_family": "GPT"}
    assert priority_runtime == {"priority": "7", "family_priority_overrides": {"GPT": "11"}}
    assert mms_command_tools.runtime_with_priority(
        "bad",
        canonical_model_family=priority_kwargs["canonical_model_family"],
        infer_model_family=lambda _model_name: ("", ""),
        runtime_priority_for_family=lambda runtime, family: 99,
        normalize_priority=priority_kwargs["normalize_priority"],
        default_priority=50,
    ) == "bad"
    assert mms_command_tools.normalize_role("PRIMARY", valid_roles={"primary", "auto", "fallback"}) == "primary"
    assert mms_command_tools.normalize_role("bad", valid_roles={"primary", "auto", "fallback"}) == "auto"
    assert mms_command_tools.normalize_positive_seconds("0", 30, minimum=5) == 5
    assert mms_command_tools.normalize_positive_seconds("42", 30, minimum=5) == 42
    assert mms_command_tools.normalize_positive_seconds("bad", 30, minimum=5) == 30


def test_provider_normalization_helpers_preserve_default_and_cleanup_semantics():
    import mms_command_tools

    model_families = [{"family": "GPT"}, {"family": "Claude"}]
    defaults = {
        "default_provider_id": "default",
        "default_provider_protocols": ["openai_chat_completions", "anthropic_messages"],
        "provider_capable_clis": ["claude", "codex"],
        "default_priority": 50,
        "model_families": model_families,
        "default_account_timezone": "Asia/Singapore",
        "claude_1m_valid_modes": {"auto", "enable", "disable"},
        "cli_names": ["claude", "codex", "opencode"],
        "legacy_provider_cli_aliases": {"provider", "gateway"},
    }

    default_provider = mms_command_tools.default_provider(
        default_provider_id="default",
        default_provider_protocols=["openai_chat_completions"],
        provider_capable_clis=["codex"],
    )
    assert default_provider == {
        "id": "default",
        "name": "Default Gateway",
        "protocols": ["openai_chat_completions"],
        "supported_clis": ["codex"],
        "enabled": True,
        "role": "auto",
    }

    normalized = mms_command_tools.normalize_provider(
        {
            "id": " relay ",
            "name": "",
            "protocols": "anthropic_messages",
            "supported_clis": "provider",
            "priority": "0",
            "family_priority_overrides": {"gpt": "7", "unknown": "9"},
            "claude_1m_mode": "enabled",
            "timezone": "Bad/Timezone",
            "force_ipv4": "enabled",
            "fallback_models": "gpt-5.5, gpt-5.5, claude-sonnet",
            "extra_models": [" extra ", "", "extra"],
            "hidden_models": ["hidden", "hidden"],
            "models_endpoint": "v1/models",
            "default_openai_base_url": "https://relay.example/v1/",
            "default_anthropic_base_url": "https://relay.example/anthropic/",
            "cost_level": "legacy",
            "daily_budget": 1,
        },
        **defaults,
    )

    assert normalized["id"] == "relay"
    assert normalized["name"] == "relay"
    assert normalized["protocols"] == ["anthropic_messages"]
    assert normalized["supported_clis"] == ["claude"]
    assert normalized["priority"] == 1
    assert normalized["family_priority_overrides"] == {"GPT": 7}
    assert normalized["claude_1m_mode"] == "enable"
    assert normalized["timezone"] == "Asia/Singapore"
    assert normalized["force_ipv4"] is True
    assert normalized["fallback_models"] == ["gpt-5.5", "claude-sonnet"]
    assert normalized["extra_models"] == ["extra"]
    assert normalized["hidden_models"] == ["hidden"]
    assert normalized["models_endpoint"] == "/v1/models"
    assert normalized["default_openai_base_url"] == "https://relay.example/v1"
    assert normalized["default_anthropic_base_url"] == "https://relay.example/anthropic"
    assert "cost_level" not in normalized
    assert "daily_budget" not in normalized


def test_account_mode_timezone_and_ipv4_helpers_preserve_normalization():
    from types import SimpleNamespace

    import mms_command_tools

    valid_modes = {"auto", "enable", "disable"}
    assert mms_command_tools.normalize_claude_1m_mode("", default="auto", valid_modes=valid_modes) == "auto"
    assert mms_command_tools.normalize_claude_1m_mode("enabled", default="auto", valid_modes=valid_modes) == "enable"
    assert mms_command_tools.normalize_claude_1m_mode("off", default="auto", valid_modes=valid_modes) == "disable"
    assert mms_command_tools.normalize_claude_1m_mode("bad", default="enable", valid_modes=valid_modes) == "enable"
    assert mms_command_tools.normalize_claude_1m_mode("bad", default="unknown", valid_modes=valid_modes) == "auto"
    assert mms_command_tools.normalize_timezone_name("Asia/Singapore", default="UTC") == "Asia/Singapore"
    assert mms_command_tools.normalize_timezone_name("Bad/Timezone", default="UTC") == "UTC"
    assert mms_command_tools.normalize_timezone_name("", default="Asia/Shanghai") == "Asia/Shanghai"
    assert mms_command_tools.normalize_account_id(" Claude Main! ") == "claude-main"
    assert mms_command_tools.normalize_account_id("!!!") == "account"
    assert mms_command_tools.runtime_force_ipv4({"force_ipv4": True}) is True
    assert mms_command_tools.runtime_force_ipv4({"force_ipv4": "enabled"}) is True
    assert mms_command_tools.runtime_force_ipv4({"force_ipv4": "off"}) is False
    assert mms_command_tools.runtime_force_ipv4({"force_ipv4": "surprise"}) is False
    assert mms_command_tools.runtime_force_ipv4(None) is False
    official_hosts = ("api.anthropic.com", "claude.ai")
    assert mms_command_tools.url_matches_host_suffix("https://api.anthropic.com/v1/messages", official_hosts) is True
    assert mms_command_tools.url_matches_host_suffix("https://console.claude.ai", official_hosts) is True
    assert mms_command_tools.url_matches_host_suffix("https://evilclaude.ai.example", official_hosts) is False
    assert mms_command_tools.url_matches_host_suffix("not-a-url", official_hosts) is False
    assert mms_command_tools.runtime_should_disable_ambient_env(
        {},
        target_url="https://api.anthropic.com/v1/messages",
        official_hosts=official_hosts,
    ) is True
    assert mms_command_tools.runtime_should_disable_ambient_env(
        {"proxy": "http://proxy:8080"},
        target_url="https://relay.example/v1",
        official_hosts=official_hosts,
    ) is True
    assert mms_command_tools.runtime_should_disable_ambient_env(
        {},
        target_url="https://relay.example/v1",
        official_hosts=official_hosts,
    ) is False
    assert mms_command_tools.runtime_httpx_kwargs(
        {"proxy": " http://proxy:8080 ", "force_ipv4": "enabled"},
        target_url="https://relay.example/v1",
        official_hosts=official_hosts,
    ) == {"proxy": "http://proxy:8080", "trust_env": False, "local_address": "0.0.0.0"}
    assert mms_command_tools.runtime_httpx_kwargs(
        {"force_ipv4": False},
        target_url="https://api.anthropic.com",
        official_hosts=official_hosts,
    ) == {"trust_env": False}
    assert mms_command_tools.runtime_httpx_kwargs(
        {"force_ipv4": "off"},
        target_url="https://relay.example/v1",
        official_hosts=official_hosts,
    ) == {}
    proxy_schemes = {"http", "https", "socks5", "socks5h"}
    assert mms_command_tools.validate_proxy_url("", supported_proxy_schemes=proxy_schemes) is None
    assert mms_command_tools.validate_proxy_url(
        "http://user:pass@198.51.100.24:6394",
        supported_proxy_schemes=proxy_schemes,
    ) is None
    assert mms_command_tools.validate_proxy_url(
        "socks5h://127.0.0.1:7890",
        supported_proxy_schemes=proxy_schemes,
    ) is None
    assert mms_command_tools.validate_proxy_url(
        "socket5://127.0.0.1:7890",
        supported_proxy_schemes=proxy_schemes,
    ) == "代理协议仅支持 http / https / socks5 / socks5h"
    assert mms_command_tools.validate_proxy_url(
        "http://",
        supported_proxy_schemes=proxy_schemes,
    ) == "代理地址缺少 host"
    assert mms_command_tools.test_proxy_connectivity(
        "",
        fake_upstream_enabled=lambda: False,
        fake_proxy_probe=lambda *args, **kwargs: {},
        http_status_is_success=lambda value: value.startswith("2"),
    ) == (True, "未配置代理，跳过检测")
    assert mms_command_tools.test_proxy_connectivity(
        "http://127.0.0.1:7890",
        no_proxy="localhost",
        target_url="https://api.anthropic.com",
        force_ipv4=False,
        fake_upstream_enabled=lambda: True,
        fake_proxy_probe=lambda target_url, **kwargs: {"ok": True, "detail": f"{target_url}:{kwargs['no_proxy']}"},
        http_status_is_success=lambda value: value.startswith("2"),
    ) == (True, "https://api.anthropic.com:localhost")
    assert mms_command_tools.test_proxy_connectivity(
        "http://127.0.0.1:7890",
        fake_upstream_enabled=lambda: False,
        fake_proxy_probe=lambda *args, **kwargs: {},
        http_status_is_success=lambda value: value.startswith("2"),
        which=lambda _name: None,
    ) == (False, "当前系统没有 curl，无法测试代理连通性")

    run_calls = []
    ok, detail = mms_command_tools.test_proxy_connectivity(
        "http://127.0.0.1:7890",
        no_proxy="localhost",
        target_url="https://api.anthropic.com",
        force_ipv4=True,
        fake_upstream_enabled=lambda: False,
        fake_proxy_probe=lambda *args, **kwargs: {},
        http_status_is_success=lambda value: value.startswith("2"),
        which=lambda _name: "/usr/bin/curl",
        run_command=lambda cmd, **kwargs: run_calls.append((cmd, kwargs)) or SimpleNamespace(returncode=0, stdout="204", stderr=""),
    )
    assert ok is True
    assert detail == "代理连通性测试通过：https://api.anthropic.com (HTTP 204)"
    assert "-4" in run_calls[0][0]
    assert run_calls[0][0][-2:] == ["--noproxy", "localhost"]
    ok, detail = mms_command_tools.test_proxy_connectivity(
        "http://127.0.0.1:7890",
        fake_upstream_enabled=lambda: False,
        fake_proxy_probe=lambda *args, **kwargs: {},
        http_status_is_success=lambda value: value.startswith("2"),
        which=lambda _name: "/usr/bin/curl",
        run_command=lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="404", stderr=""),
    )
    assert ok is False
    assert detail == "HTTP 404"


def test_account_normalization_helpers_preserve_oauth_profile_shape(tmp_path):
    import mms_command_tools

    model_families = [{"family": "GPT"}, {"family": "Claude"}]
    normalized = mms_command_tools.normalize_account(
        {
            "id": " Claude Main! ",
            "name": "",
            "cli": "unknown",
            "home_dir": "~/mms-test-account",
            "enabled": 0,
            "priority": "0",
            "family_priority_overrides": {"Claude": "9", "unknown": "4"},
            "claude_1m_mode": "disabled",
            "proxy": " http://127.0.0.1:7890 ",
            "no_proxy": " localhost ",
            "timezone": "Bad/Timezone",
            "force_ipv4": "enabled",
            "note": " demo ",
        },
        oauth_capable_clis=("claude", "codex", "gemini", "agy"),
        accounts_dir=str(tmp_path),
        default_priority=50,
        model_families=model_families,
        default_account_timezone="Asia/Singapore",
        claude_1m_valid_modes={"auto", "enable", "disable"},
    )

    assert mms_command_tools.default_account_home("claude-main", accounts_dir=str(tmp_path)) == str(tmp_path / "claude-main")
    assert normalized["id"] == "claude-main"
    assert normalized["name"] == "claude-main"
    assert normalized["cli"] == "claude"
    assert normalized["auth_mode"] == "oauth"
    assert normalized["enabled"] is False
    assert normalized["home_dir"].endswith("mms-test-account")
    assert normalized["priority"] == 1
    assert normalized["family_priority_overrides"] == {"Claude": 9}
    assert normalized["claude_1m_mode"] == "disable"
    assert normalized["proxy"] == "http://127.0.0.1:7890"
    assert normalized["no_proxy"] == "localhost"
    assert normalized["timezone"] == "Asia/Singapore"
    assert normalized["force_ipv4"] is True
    assert normalized["note"] == "demo"


def test_semver_and_http_status_helpers_preserve_update_semantics():
    import mms_command_tools

    assert mms_command_tools.parse_semver_tag("v1.2.3") == (1, 2, 3)
    assert mms_command_tools.parse_semver_tag("1.2.3") is None
    assert mms_command_tools.normalize_semver_tags(["v1.2.0", "v1.10.0", "bad", "v1.2.0"]) == ["v1.10.0", "v1.2.0"]
    assert mms_command_tools.extract_semver_text("codex-cli 0.133.0-beta.1") == "0.133.0-beta.1"
    assert mms_command_tools.parse_semver_text("codex-cli 0.133.0-beta.1") == (0, 133, 0)
    assert mms_command_tools.compare_semver_text("0.132.0", "0.133.0") == -1
    assert mms_command_tools.compare_semver_text("0.134.0", "0.133.0") == 1
    assert mms_command_tools.compare_semver_text("0.133.0", "0.133.0") == 0
    assert mms_command_tools.compare_semver_text("dev", "0.133.0") is None
    assert mms_command_tools.semver_tag_gap("v1.16.3", ["v1.16.6", "v1.16.5", "v1.16.4", "v1.16.3"]) == 3
    assert mms_command_tools.semver_tag_gap("v1.16.6", ["v1.16.6", "v1.16.5"]) == 0
    assert mms_command_tools.semver_tag_gap("v1.16.6", [], "v2.0.0") is None
    assert mms_command_tools.http_status_is_success("200") is True
    assert mms_command_tools.http_status_is_success("299") is True
    assert mms_command_tools.http_status_is_success("300") is False
    assert mms_command_tools.http_status_is_success("bad") is False


def test_fetch_latest_semver_tags_preserves_request_and_normalization():
    import mms_command_tools

    requests = []

    class FakeRequest:
        def __init__(self, url, headers=None):
            self.url = url
            self.headers = headers
            requests.append((url, headers))

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(req, timeout=0):
        assert req.url.endswith("per_page=7")
        assert timeout == 3
        return FakeResponse()

    tags = mms_command_tools.fetch_latest_semver_tags(
        limit=7,
        request_cls=FakeRequest,
        urlopen_func=fake_urlopen,
        json_load=lambda resp: [{"name": "v1.2.0"}, {"name": "bad"}, "skip", {"name": "v1.3.0"}],
        normalize_semver_tags=mms_command_tools.normalize_semver_tags,
    )
    assert tags == ["v1.3.0", "v1.2.0"]
    assert requests == [
        (
            "https://api.github.com/repos/CtriXin/multi-model-switch/tags?per_page=7",
            {"Accept": "application/vnd.github+json", "User-Agent": "mms-update-check"},
        )
    ]

    assert mms_command_tools.fetch_latest_semver_tags(
        limit=7,
        request_cls=FakeRequest,
        urlopen_func=fake_urlopen,
        json_load=lambda resp: {"name": "v1.2.0"},
        normalize_semver_tags=mms_command_tools.normalize_semver_tags,
    ) == ""


def test_fetch_latest_semver_tag_returns_first_or_empty():
    import mms_command_tools

    assert mms_command_tools.fetch_latest_semver_tag(
        fetch_latest_semver_tags=lambda: ["v1.2.4", "v1.2.3"],
    ) == "v1.2.4"
    assert mms_command_tools.fetch_latest_semver_tag(
        fetch_latest_semver_tags=lambda: [],
    ) == ""


def test_detect_cli_version_preserves_missing_success_and_failure_paths():
    import mms_command_tools

    class Result:
        stdout = "codex-cli 0.132.0\nextra"
        returncode = 0

    calls = []
    missing = mms_command_tools.detect_cli_version(
        "",
        which=lambda command: (_ for _ in ()).throw(AssertionError("should not resolve")),
        subprocess_run=lambda *args, **kwargs: Result(),
        extract_semver_text=mms_command_tools.extract_semver_text,
        localize=lambda zh, en: zh,
    )
    assert missing == {"installed": False, "label": "未安装", "version": "", "path": ""}

    success = mms_command_tools.detect_cli_version(
        "codex",
        which=lambda command: "/usr/local/bin/codex",
        subprocess_run=lambda *args, **kwargs: calls.append((args, kwargs)) or Result(),
        extract_semver_text=mms_command_tools.extract_semver_text,
        localize=lambda zh, en: zh,
    )
    assert success == {
        "installed": True,
        "label": "codex-cli 0.132.0",
        "version": "0.132.0",
        "path": "/usr/local/bin/codex",
    }
    assert calls[0][0][0] == ["/usr/local/bin/codex", "--version"]
    assert calls[0][1]["stdout"] == mms_command_tools.subprocess.PIPE

    failed = mms_command_tools.detect_cli_version(
        "codex",
        which=lambda command: "/usr/local/bin/codex",
        subprocess_run=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        extract_semver_text=mms_command_tools.extract_semver_text,
        localize=lambda zh, en: zh,
    )
    assert failed == {
        "installed": True,
        "label": "读取失败: boom",
        "version": "",
        "path": "/usr/local/bin/codex",
    }


def test_fetch_npm_package_latest_version_preserves_command_and_failures():
    import mms_command_tools

    class Result:
        stdout = "0.133.0\n"
        returncode = 0

    calls = []
    assert mms_command_tools.fetch_npm_package_latest_version(
        "",
        which=lambda command: (_ for _ in ()).throw(AssertionError("should not resolve")),
        subprocess_run=lambda *args, **kwargs: Result(),
        extract_semver_text=mms_command_tools.extract_semver_text,
    ) == ""
    assert mms_command_tools.fetch_npm_package_latest_version(
        "@openai/codex",
        which=lambda command: "",
        subprocess_run=lambda *args, **kwargs: Result(),
        extract_semver_text=mms_command_tools.extract_semver_text,
    ) == ""

    latest = mms_command_tools.fetch_npm_package_latest_version(
        "@openai/codex",
        which=lambda command: "/usr/local/bin/npm",
        subprocess_run=lambda *args, **kwargs: calls.append((args, kwargs)) or Result(),
        extract_semver_text=mms_command_tools.extract_semver_text,
    )
    assert latest == "0.133.0"
    assert calls[0][0][0] == ["/usr/local/bin/npm", "view", "@openai/codex", "version", "--silent"]
    assert calls[0][1]["stderr"] == mms_command_tools.subprocess.DEVNULL

    class FailedResult:
        stdout = "0.133.0\n"
        returncode = 1

    assert mms_command_tools.fetch_npm_package_latest_version(
        "@openai/codex",
        which=lambda command: "/usr/local/bin/npm",
        subprocess_run=lambda *args, **kwargs: FailedResult(),
        extract_semver_text=mms_command_tools.extract_semver_text,
    ) == ""


def test_update_status_helpers_preserve_install_and_about_status_semantics():
    import mms_command_tools

    update_sources = {"install.sh", "homebrew"}
    localize = lambda zh, en: zh

    assert mms_command_tools.installed_update_semver(
        {"source": "install.sh", "installed_version": "v1.2.3"},
        update_notice_sources=update_sources,
    ) == ("v1.2.3", (1, 2, 3))
    assert mms_command_tools.installed_update_semver(
        {"install_channel": "latest-tag", "installed_version": "v1.2.3"},
        update_notice_sources=update_sources,
    ) == ("v1.2.3", (1, 2, 3))
    assert mms_command_tools.installed_update_semver(
        {"source": "manual", "installed_version": "v1.2.3"},
        update_notice_sources=update_sources,
    ) == (None, None)
    assert mms_command_tools.installed_update_semver(
        {"source": "install.sh", "installed_version": "dev"},
        update_notice_sources=update_sources,
    ) == (None, None)

    outdated = mms_command_tools.mms_update_status(
        {"installed_version": "v1.2.3"},
        {"latest_tag": "v1.2.4", "last_error": "net"},
        localize=localize,
    )
    assert outdated == {
        "current": "v1.2.3",
        "latest": "v1.2.4",
        "status": "有新版 v1.2.4",
        "outdated": True,
        "last_error": "net",
    }
    assert mms_command_tools.mms_update_status({"release": "dev"}, {"latest_tag": "v1.2.4"}, localize=localize)["status"] == "开发版/无法判断"
    assert mms_command_tools.mms_update_status({"installed_version": "v1.2.4"}, {}, localize=localize)["status"] == "未检查 latest"
    assert mms_command_tools.mms_update_status({"installed_version": "v1.2.4"}, {"latest_tag": "v1.2.4"}, localize=localize)["status"] == "最新"


def test_update_notice_preserves_prompt_payload_and_throttle():
    import mms_command_tools

    class TTY:
        def __init__(self, enabled=True):
            self.enabled = enabled

        def isatty(self):
            return self.enabled

    saved = []
    notice = mms_command_tools.update_notice(
        stdin=TTY(),
        stdout=TTY(),
        load_version_meta=lambda: {"source": "install.sh", "installed_version": "v1.16.3"},
        installed_update_semver=lambda meta: ("v1.16.3", (1, 16, 3)),
        load_update_check_cache=lambda: {"latest_tag": "v1.16.6", "semver_tags": ["v1.16.6", "v1.16.5", "v1.16.4", "v1.16.3"]},
        parse_semver_tag=mms_command_tools.parse_semver_tag,
        semver_tag_gap=mms_command_tools.semver_tag_gap,
        save_update_check_cache=saved.append,
        now=lambda: 1000.0,
        version_gap=3,
        prompt_interval_sec=600,
    )
    assert notice == {
        "installed_version": "v1.16.3",
        "latest_tag": "v1.16.6",
        "gap_count": 3,
        "upgrade_command": "curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash",
    }
    assert saved[-1]["last_prompted_for"] == "v1.16.6"
    assert saved[-1]["last_prompted_at"] == 1000.0

    assert mms_command_tools.update_notice(
        stdin=TTY(False),
        stdout=TTY(),
        load_version_meta=lambda: (_ for _ in ()).throw(AssertionError("should not load")),
        installed_update_semver=lambda meta: (None, None),
        load_update_check_cache=lambda: {},
        parse_semver_tag=mms_command_tools.parse_semver_tag,
        semver_tag_gap=mms_command_tools.semver_tag_gap,
        save_update_check_cache=saved.append,
        now=lambda: 1000.0,
        version_gap=3,
        prompt_interval_sec=600,
    ) is None
    assert mms_command_tools.update_notice(
        stdin=TTY(),
        stdout=TTY(),
        load_version_meta=lambda: {"source": "install.sh", "installed_version": "v1.16.3"},
        installed_update_semver=lambda meta: ("v1.16.3", (1, 16, 3)),
        load_update_check_cache=lambda: {"latest_tag": "v1.16.6", "last_prompted_for": "v1.16.6", "last_prompted_at": 950.0},
        parse_semver_tag=mms_command_tools.parse_semver_tag,
        semver_tag_gap=mms_command_tools.semver_tag_gap,
        save_update_check_cache=saved.append,
        now=lambda: 1000.0,
        version_gap=3,
        prompt_interval_sec=600,
    ) is None


def test_major_update_notice_delegates_to_update_notice():
    import mms_command_tools

    calls = []
    assert mms_command_tools.major_update_notice(
        update_notice=lambda: calls.append("called") or {"latest_tag": "v2.0.0"},
    ) == {"latest_tag": "v2.0.0"}
    assert calls == ["called"]


def test_start_async_update_check_preserves_interval_running_and_worker_flow():
    import mms_command_tools

    events = []
    saved = []
    running = {"value": False}

    class FakeLock:
        def __enter__(self):
            events.append(("lock", "enter"))

        def __exit__(self, exc_type, exc, tb):
            events.append(("lock", "exit"))
            return False

    class FakeThread:
        def __init__(self, *, target, daemon=False, name=""):
            events.append(("thread", daemon, name))
            self.target = target

        def start(self):
            events.append(("start",))
            self.target()

    mms_command_tools.start_async_update_check(
        load_version_meta=lambda: {"source": "install.sh", "installed_version": "v1.16.3"},
        installed_update_semver=lambda meta: ("v1.16.3", (1, 16, 3)),
        load_update_check_cache=lambda: {"checked_at": 0},
        fetch_latest_semver_tags=lambda: ["v1.16.6", "v1.16.5"],
        save_update_check_cache=saved.append,
        lock=FakeLock(),
        get_running=lambda: running["value"],
        set_running=lambda value: events.append(("running", value)) or running.__setitem__("value", value),
        thread_cls=FakeThread,
        now=lambda: 1000,
        interval_sec=60,
    )
    assert saved == [{"checked_at": 1000, "latest_tag": "v1.16.6", "semver_tags": ["v1.16.6", "v1.16.5"]}]
    assert ("thread", True, "mms-update-check") in events
    assert ("running", True) in events
    assert events[-2:] == [("running", False), ("lock", "exit")]

    events.clear()
    mms_command_tools.start_async_update_check(
        load_version_meta=lambda: {"source": "install.sh", "installed_version": "v1.16.3"},
        installed_update_semver=lambda meta: ("v1.16.3", (1, 16, 3)),
        load_update_check_cache=lambda: {"checked_at": 990},
        fetch_latest_semver_tags=lambda: (_ for _ in ()).throw(AssertionError("should not fetch")),
        save_update_check_cache=saved.append,
        lock=FakeLock(),
        get_running=lambda: False,
        set_running=lambda value: events.append(("running", value)),
        thread_cls=FakeThread,
        now=lambda: 1000,
        interval_sec=60,
    )
    assert events == []


def test_release_version_info_preserves_installed_and_git_fallbacks():
    import mms_command_tools

    calls = []
    info = mms_command_tools.release_version_info(
        load_version_meta=lambda: {
            "installed_version": "v9.9.9",
            "installed_ref": "release-ref",
            "install_channel": "latest-tag",
            "source": "install.sh",
        },
        git_output=lambda args: calls.append(tuple(args)) or "git-value",
    )
    assert info == {
        "release": "v9.9.9",
        "installed_version": "v9.9.9",
        "installed_ref": "release-ref",
        "git_describe": "git-value",
        "git_branch": "git-value",
        "git_commit": "git-value",
        "install_channel": "latest-tag",
        "source": "install.sh",
    }
    assert calls == [
        ("describe", "--tags", "--always", "--dirty"),
        ("branch", "--show-current"),
        ("rev-parse", "--short", "HEAD"),
    ]

    fallback = mms_command_tools.release_version_info(
        load_version_meta=lambda: {},
        git_output=lambda args: "abc123" if args[0] == "rev-parse" else "",
    )
    assert fallback["release"] == "abc123"
    assert fallback["installed_version"] == ""


def test_git_output_preserves_command_cwd_and_failure_paths():
    import mms_command_tools

    class Result:
        stdout = " main \n"
        returncode = 0

    calls = []
    value = mms_command_tools.git_output(
        ["branch", "--show-current"],
        subprocess_run=lambda *args, **kwargs: calls.append((args, kwargs)) or Result(),
        file_path="/tmp/project/mms_core.py",
    )
    assert value == "main"
    assert calls[0][0][0] == ["git", "-C", "/tmp/project", "branch", "--show-current"]
    assert calls[0][1]["timeout"] == 2

    class FailedResult:
        stdout = "main"
        returncode = 1

    assert mms_command_tools.git_output(
        ["branch"],
        subprocess_run=lambda *args, **kwargs: FailedResult(),
        file_path="/tmp/project/mms_core.py",
    ) == ""
    assert mms_command_tools.git_output(
        ["branch"],
        subprocess_run=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        file_path="/tmp/project/mms_core.py",
    ) == ""


def test_cli_version_status_preserves_cache_refresh_and_labels():
    import mms_command_tools

    packages = {"codex": "@openai/codex", "claude": "@anthropic-ai/claude-code"}
    detected = {
        "codex": {"installed": True, "version": "0.132.0", "label": "codex 0.132.0"},
        "claude": {"installed": False, "version": "", "label": "missing"},
    }
    saved = []
    fetched = []

    cached_status = mms_command_tools.cli_version_status(
        force_update=False,
        load_update_check_cache=lambda: {"cli_latest_versions": {"codex": "0.133.0"}},
        save_update_check_cache=saved.append,
        cli_version_packages=packages,
        detect_cli_version=lambda cli_name: detected[cli_name],
        fetch_npm_package_latest_version=lambda package: (_ for _ in ()).throw(AssertionError("should not fetch")),
        compare_semver_text=mms_command_tools.compare_semver_text,
        localize=lambda zh, en: zh,
        now=lambda: 123,
    )
    assert cached_status["codex"]["status"] == "有新版 0.133.0"
    assert cached_status["codex"]["outdated"] is True
    assert cached_status["codex"]["package"] == "@openai/codex"
    assert cached_status["claude"]["status"] == "未安装"
    assert saved == []

    forced_status = mms_command_tools.cli_version_status(
        force_update=True,
        load_update_check_cache=lambda: {},
        save_update_check_cache=saved.append,
        cli_version_packages=packages,
        detect_cli_version=lambda cli_name: {"installed": True, "version": "0.133.0", "label": cli_name},
        fetch_npm_package_latest_version=lambda package: fetched.append(package) or "0.133.0",
        compare_semver_text=mms_command_tools.compare_semver_text,
        localize=lambda zh, en: zh,
        now=lambda: 456,
    )
    assert forced_status["codex"]["status"] == "最新"
    assert forced_status["claude"]["status"] == "最新"
    assert fetched == ["@openai/codex", "@anthropic-ai/claude-code"]
    assert saved[-1]["cli_latest_versions"] == {"codex": "0.133.0", "claude": "0.133.0"}
    assert saved[-1]["cli_latest_checked_at"] == 456


def test_about_status_snapshot_preserves_callback_flow():
    import mms_command_tools

    calls = []
    snapshot = mms_command_tools.about_status_snapshot(
        force_update=True,
        release_version_info=lambda: calls.append(("version",)) or {"release": "v1.2.3"},
        refresh_update_cache_for_about=lambda force_update=False: calls.append(("cache", force_update)) or {"latest_tag": "v1.2.4", "checked_at": 123},
        cli_version_status=lambda force_update=False: calls.append(("cli", force_update)) or {"codex": {"version": "1.0.0"}},
        mms_update_status=lambda version_info, cache: calls.append(("mms", version_info, cache)) or {"status": "有新版 v1.2.4"},
    )

    assert snapshot == {
        "version_info": {"release": "v1.2.3"},
        "mms": {"status": "有新版 v1.2.4"},
        "clis": {"codex": {"version": "1.0.0"}},
        "checked_at": 123,
    }
    assert calls == [
        ("version",),
        ("cache", True),
        ("cli", True),
        ("mms", {"release": "v1.2.3"}, {"latest_tag": "v1.2.4", "checked_at": 123}),
    ]


def test_refresh_update_cache_for_about_preserves_force_and_error_paths():
    import mms_command_tools

    saved = []
    base_cache = {"latest_tag": "v1.0.0"}
    assert mms_command_tools.refresh_update_cache_for_about(
        force_update=False,
        load_update_check_cache=lambda: base_cache,
        fetch_latest_semver_tags=lambda: (_ for _ in ()).throw(AssertionError("should not fetch")),
        save_update_check_cache=saved.append,
        now=lambda: 99,
    ) is base_cache
    assert saved == []

    cache = mms_command_tools.refresh_update_cache_for_about(
        force_update=True,
        load_update_check_cache=lambda: {},
        fetch_latest_semver_tags=lambda: ["v1.2.4", "v1.2.3"],
        save_update_check_cache=saved.append,
        now=lambda: 123,
    )
    assert cache == {
        "checked_at": 123,
        "last_error": "",
        "latest_tag": "v1.2.4",
        "semver_tags": ["v1.2.4", "v1.2.3"],
    }
    assert saved[-1] is cache

    failed = mms_command_tools.refresh_update_cache_for_about(
        force_update=True,
        load_update_check_cache=lambda: {"latest_tag": "v1.0.0"},
        fetch_latest_semver_tags=lambda: (_ for _ in ()).throw(RuntimeError("net")),
        save_update_check_cache=saved.append,
        now=lambda: 456,
    )
    assert failed == {"latest_tag": "v1.0.0", "last_error": "net", "checked_at": 456}
    assert saved[-1] is failed


def test_runtime_usage_model_and_hint_helpers_preserve_tracking_shape():
    import mms_command_tools

    provider_runtime = {
        "runtime_kind": "provider",
        "auth_mode": "api_key",
        "id": "relay",
        "provider_id": "relay",
    }
    account_runtime = {
        "runtime_kind": "account",
        "auth_mode": "oauth",
        "id": "claude-main",
        "account_id": "claude-main",
    }

    assert mms_command_tools.runtime_usage_key(provider_runtime, "codex") == "provider:codex:relay"
    assert mms_command_tools.runtime_usage_key({}, "claude") == "provider:claude:default"
    assert mms_command_tools.resolve_model_name({"model": "gpt-5.5", "sonnet": "claude-sonnet"}) == "gpt-5.5"
    assert mms_command_tools.resolve_model_name({"sonnet": "claude-sonnet"}) == "claude-sonnet"
    assert mms_command_tools.resolve_model_name({}) == "official-default"
    assert mms_command_tools.resolve_model_name("") == "official-default"
    assert mms_command_tools.resolve_model_name("gpt-5.4") == "gpt-5.4"
    assert mms_command_tools.runtime_hint_from_runtime(
        provider_runtime,
        runtime_provider_id=lambda runtime: runtime.get("provider_id", ""),
        runtime_account_id=lambda runtime: runtime.get("account_id", ""),
    ) == {
        "runtime_kind": "provider",
        "auth_mode": "api_key",
        "provider_id": "relay",
        "runtime_id": "relay",
    }
    assert mms_command_tools.runtime_hint_from_runtime(
        account_runtime,
        runtime_provider_id=lambda runtime: runtime.get("provider_id", ""),
        runtime_account_id=lambda runtime: runtime.get("account_id", ""),
    ) == {
        "runtime_kind": "account",
        "auth_mode": "oauth",
        "account_id": "claude-main",
        "runtime_id": "claude-main",
    }
    assert mms_command_tools.runtime_hint_from_runtime(None, runtime_provider_id=lambda runtime: "", runtime_account_id=lambda runtime: "") == {}
    recorded = {}
    mms_command_tools.record_usage(
        provider_runtime,
        "codex",
        {"model": "gpt-5.5"},
        update_usage_stats=lambda mutator: mutator(recorded),
        iso_now=lambda: "2026-05-28T10:00:00Z",
        runtime_hint_from_runtime=lambda runtime: {"runtime_id": runtime["id"], "auth_mode": runtime["auth_mode"]},
    )
    assert recorded["sources"]["provider:codex:relay"]["launches"] == 1
    assert recorded["sources"]["provider:codex:relay"]["model_last_used_at"] == {
        "gpt-5.5": "2026-05-28T10:00:00Z"
    }
    assert recorded["last_by_cli"]["codex"]["runtime_hint"] == {"runtime_id": "relay", "auth_mode": "api_key"}
    scene_recorded = {}
    mms_command_tools.record_scene_usage(
        "legacy-scene",
        "claude",
        {"model": "claude-sonnet-4.5"},
        update_usage_stats=lambda mutator: mutator(scene_recorded),
        iso_now=lambda: "2026-05-28T11:00:00Z",
    )
    mms_command_tools.record_scene_usage(
        "__internal",
        "claude",
        {"model": "ignore"},
        update_usage_stats=lambda mutator: mutator(scene_recorded),
        iso_now=lambda: "2026-05-28T11:01:00Z",
    )
    assert scene_recorded["scenes"]["legacy-scene"] == {
        "launches": 1,
        "last_used_at": "2026-05-28T11:00:00Z",
        "last_cli": "claude",
        "last_model": "claude-sonnet-4.5",
    }
    stats = {
        "scenes": {"legacy-scene": scene_recorded["scenes"]["legacy-scene"]},
        "last_by_cli": {
            "claude": {
                "cli": "claude",
                "model_info": {"model": "gpt-5.5"},
            }
        },
        "sources": {
            "old": {
                "runtime_kind": "provider",
                "id": "relay-old",
                "cli": "claude",
                "last_model": "gpt-5.5",
                "last_used_at": "2026-05-27T10:00:00Z",
            },
            "new": {
                "runtime_kind": "account",
                "id": "claude-main",
                "cli": "claude",
                "last_model": "gpt-5.5",
                "last_used_at": "2026-05-28T10:00:00Z",
            },
            "other": {
                "runtime_kind": "provider",
                "id": "codex-relay",
                "cli": "codex",
                "last_model": "gpt-5.5",
                "last_used_at": "2026-05-29T10:00:00Z",
            },
        }
    }
    assert mms_command_tools.infer_runtime_hint_from_usage_stats(stats, "claude", "gpt-5.5") == {
        "runtime_kind": "account",
        "runtime_id": "claude-main",
        "auth_mode": "oauth",
        "account_id": "claude-main",
    }
    assert mms_command_tools.infer_runtime_hint_from_usage_stats(stats, "claude", "missing-model") == {}
    last_by_cli, scene_counts = mms_command_tools.get_scene_usage(load_usage_stats=lambda: stats)
    assert scene_counts == {"legacy-scene": 1}
    assert last_by_cli["claude"]["runtime_hint"]["account_id"] == "claude-main"


def test_usage_rename_and_target_home_helpers_preserve_keys_and_paths(tmp_path):
    import os

    import mms_command_tools
    import mms_core

    stats = {
        "sources": {
            "account:claude:old-account": {
                "runtime_kind": "account",
                "cli": "claude",
                "id": "old-account",
                "name": "Old Account",
            },
            "provider:codex:old-provider": {
                "runtime_kind": "provider",
                "cli": "codex",
                "id": "old-provider",
                "name": "Old Provider",
            },
            "provider:claude:other-provider": {
                "runtime_kind": "provider",
                "cli": "claude",
                "id": "other-provider",
                "name": "Other Provider",
            },
        }
    }

    def update_usage_stats(mutator):
        return mutator(stats)

    assert mms_command_tools.usage_key("provider", "codex", "relay") == "provider:codex:relay"
    assert mms_core._usage_key("provider", "codex", "relay") == "provider:codex:relay"
    assert mms_command_tools.rename_usage_account(
        "old-account",
        "new-account",
        "New Account",
        "claude",
        usage_path="/tmp/usage.json",
        path_exists=lambda _path: True,
        update_usage_stats=update_usage_stats,
    )
    assert "account:claude:old-account" not in stats["sources"]
    assert stats["sources"]["account:claude:new-account"]["name"] == "New Account"
    assert mms_command_tools.rename_usage_provider(
        "old-provider",
        "new-provider",
        "New Provider",
        usage_path="/tmp/usage.json",
        path_exists=lambda _path: True,
        update_usage_stats=update_usage_stats,
    )
    assert "provider:codex:old-provider" not in stats["sources"]
    assert stats["sources"]["provider:codex:new-provider"]["id"] == "new-provider"
    assert mms_command_tools.rename_usage_account(
        "missing",
        "new",
        "New",
        "claude",
        usage_path="/tmp/missing.json",
        path_exists=lambda _path: False,
        update_usage_stats=update_usage_stats,
    ) is False

    accounts_dir = tmp_path / "accounts"
    accounts_dir.mkdir()
    assert mms_command_tools.target_account_home(
        "",
        "new-account",
        accounts_dir=str(accounts_dir),
        default_account_home=lambda account_id: str(accounts_dir / account_id),
    ) == str(accounts_dir / "new-account")
    assert mms_command_tools.target_account_home(
        str(accounts_dir / "old-account"),
        "new-account",
        accounts_dir=str(accounts_dir),
        default_account_home=lambda account_id: str(accounts_dir / account_id),
    ) == os.path.join(str(accounts_dir), "new-account")
    custom_parent = tmp_path / "custom"
    assert mms_command_tools.target_account_home(
        str(custom_parent / "old-account"),
        "new-account",
        accounts_dir=str(accounts_dir),
        default_account_home=lambda account_id: str(accounts_dir / account_id),
    ) == os.path.join(str(custom_parent), "new-account")


def test_migrate_accounts_dirs_preserves_move_and_normalize_rules():
    import mms_command_tools

    made_dirs = []
    moves = []

    updated, changed = mms_command_tools.migrate_accounts_dirs(
        {
            "accounts": [
                "ignored",
                {"id": "same", "home_dir": "/accounts/same"},
                {"id": "old", "home_dir": "/legacy/old"},
                {"id": "occupied", "home_dir": "/legacy/occupied"},
            ]
        },
        target_account_home=lambda home_dir, account_id: f"/accounts/{account_id}",
        normalize_account=lambda account: {**account, "normalized": True},
        path_exists=lambda path: path in {"/legacy/old", "/legacy/occupied", "/accounts/occupied"},
        makedirs=lambda path, exist_ok=False: made_dirs.append((path, exist_ok)),
        move=lambda old, new: moves.append((old, new)),
    )

    assert changed is True
    assert updated == [
        {"id": "same", "home_dir": "/accounts/same", "normalized": True},
        {"id": "old", "home_dir": "/accounts/old", "normalized": True},
        {"id": "occupied", "home_dir": "/accounts/occupied", "normalized": True},
    ]
    assert made_dirs == [("/accounts", True)]
    assert moves == [("/legacy/old", "/accounts/old")]


def test_resolve_last_used_runtime_helper_preserves_provider_and_account_paths():
    import mms_command_tools

    provider = {"id": "relay", "runtime_kind": "provider", "models": ["gpt-5.5"]}
    account = {"id": "codex-main", "runtime_kind": "account"}

    runtime, models, choice = mms_command_tools.resolve_last_used_runtime(
        {},
        "codex",
        {
            "model_info": {"model": "gpt-5.5"},
            "runtime_hint": {"provider_id": "relay", "auth_mode": "api_key"},
        },
        ["gpt-5.5"],
        resolve_provider_context=lambda _cfg, provider_id: provider if provider_id == "relay" else None,
        provider_supports_model_for_cli=lambda provider_arg, cli_name, model_name: cli_name == "codex",
        probe_models=lambda provider_arg, emit_output=False: {"models": provider_arg["models"]},
        provider_effective_models=lambda _provider, cached_models, _cfg: list(cached_models or []),
        runtime_with_priority=lambda runtime_arg, model_name="": {**runtime_arg, "model_name": model_name},
        resolve_account_context=lambda *_args, **_kwargs: None,
        model_matches_account_cli=lambda *_args: False,
    )
    assert runtime == {"id": "relay", "runtime_kind": "provider", "models": ["gpt-5.5"], "model_name": "gpt-5.5"}
    assert models == ["gpt-5.5"]
    assert choice == "last used provider:relay"

    runtime, models, choice = mms_command_tools.resolve_last_used_runtime(
        {},
        "codex",
        {
            "model": "gpt-5.5",
            "runtime_hint": {"account_id": "codex-main", "auth_mode": "oauth"},
        },
        ["gpt-5.5", "gpt-5.4"],
        resolve_provider_context=lambda *_args, **_kwargs: None,
        provider_supports_model_for_cli=lambda *_args: False,
        probe_models=lambda *_args, **_kwargs: {"models": []},
        provider_effective_models=lambda *_args: [],
        runtime_with_priority=lambda runtime_arg, model_name="": {**runtime_arg, "model_name": model_name},
        resolve_account_context=lambda _cfg, account_id, cli_name: account if account_id == "codex-main" and cli_name == "codex" else None,
        model_matches_account_cli=lambda cli_name, model_name: cli_name == "codex" and model_name == "gpt-5.5",
    )
    assert runtime == {"id": "codex-main", "runtime_kind": "account", "model_name": "gpt-5.5"}
    assert models == ["gpt-5.5", "gpt-5.4"]
    assert choice == "last used account:codex-main"

    assert mms_command_tools.resolve_last_used_runtime(
        {},
        "codex",
        {"runtime_hint": {"account_id": "codex-main", "auth_mode": "oauth_bridge"}},
        ["gpt-5.5"],
        resolve_provider_context=lambda *_args, **_kwargs: None,
        provider_supports_model_for_cli=lambda *_args: False,
        probe_models=lambda *_args, **_kwargs: {"models": []},
        provider_effective_models=lambda *_args: [],
        runtime_with_priority=lambda runtime_arg, model_name="": runtime_arg,
        resolve_account_context=lambda *_args, **_kwargs: account,
        model_matches_account_cli=lambda *_args: True,
    ) == (None, None, None)


def test_provider_model_list_helpers_preserve_visibility_cli_and_source_shape():
    import mms_command_tools

    default_provider = {"id": "default", "name": "Default"}
    cfg = {
        "providers": [
            {"id": "relay-a"},
            {"id": "relay-b"},
            {"id": "relay-a"},
            {"id": ""},
            {"name": "missing-id"},
        ]
    }
    cache = {
        "relay-a": {"raw_models": ["gpt-5.5"], "models": ["display-only"]},
        "relay-b": {"raw_models": ["stale-model"], "is_stale": True},
    }
    resolved = {
        "relay-a": {"id": "relay-a", "resolved": True},
        "relay-b": {"id": "relay-b", "resolved": True},
    }
    cache_calls = []
    assert mms_command_tools.provider_candidates(
        cfg,
        default_provider,
        ("fallback",),
        load_probe_file_cache=lambda provider_id, allow_stale=False: cache_calls.append((provider_id, allow_stale)) or cache.get(provider_id),
        resolve_provider_context=lambda _cfg, provider_id: resolved[provider_id],
    ) == [
        (default_provider, ["fallback"]),
        (resolved["relay-a"], ["gpt-5.5"]),
        (resolved["relay-b"], None),
    ]
    assert cache_calls == [("relay-a", True), ("relay-b", True)]

    refresh_calls = []
    patch_calls = []

    def apply_patch(provider, payload):
        patch_calls.append((provider["id"], payload))
        return {**payload, "models": payload["models"] + provider.get("extra_models", [])}

    assert mms_command_tools.provider_effective_models(
        {"id": "manual", "models_endpoint": "manual", "fallback_models": ("manual-model",), "extra_models": ["extra"]},
        None,
        {"cfg": True},
        schedule_probe_refresh=lambda provider, cfg, reason: refresh_calls.append((provider["id"], cfg, reason)),
        apply_provider_model_patch=apply_patch,
    ) == ["manual-model", "extra"]
    assert refresh_calls == []
    assert patch_calls[-1] == (
        "manual",
        {"raw_models": ["manual-model"], "models": ["manual-model"], "base_source": "manual"},
    )
    assert mms_command_tools.provider_effective_models(
        {"id": "fallback", "fallback_models": ["fallback-model"]},
        None,
        {"cfg": True},
        schedule_probe_refresh=lambda provider, cfg, reason: refresh_calls.append((provider["id"], cfg, reason)),
        apply_provider_model_patch=apply_patch,
    ) == ["fallback-model"]
    assert refresh_calls == [("fallback", {"cfg": True}, "cache_miss")]
    assert patch_calls[-1] == (
        "fallback",
        {"raw_models": ["fallback-model"], "models": ["fallback-model"], "base_source": "fallback"},
    )
    assert mms_command_tools.provider_effective_models(
        {"id": "remote"},
        None,
        {},
        schedule_probe_refresh=lambda provider, cfg, reason: refresh_calls.append((provider["id"], cfg, reason)),
        apply_provider_model_patch=apply_patch,
    ) == []
    assert patch_calls[-1] == ("remote", {"raw_models": [], "models": [], "base_source": "remote"})
    assert mms_command_tools.provider_effective_models(
        {"id": "cached"},
        ("cached-model",),
        {},
        schedule_probe_refresh=lambda provider, cfg, reason: refresh_calls.append(("unexpected", provider["id"], reason)),
        apply_provider_model_patch=apply_patch,
    ) == ["cached-model"]
    assert patch_calls[-1] == (
        "cached",
        {"raw_models": ["cached-model"], "models": ["cached-model"], "base_source": "remote"},
    )

    assert mms_command_tools.provider_supports_mimo_anthropic_selectors(
        {"id": "mimo-direct", "anthropic_base_url": "https://relay.example/anthropic"}
    ) is True
    assert mms_command_tools.provider_supports_mimo_anthropic_selectors(
        {"id": "mimo-openrouter", "anthropic_base_url": "https://openrouter.ai/api/v1"}
    ) is False
    assert mms_command_tools.derived_model_aliases(
        ["claude-sonnet-4-5-20250929", "mimo-v2.5"],
        {"id": "mimo-direct", "anthropic_base_url": "https://relay.example/anthropic"},
    ) == ["claude-sonnet-4-6", "mimo-v2.5[1m]"]

    patched = mms_command_tools.apply_provider_model_patch(
        {
            "id": "relay",
            "extra_models": ["extra-model", "gpt-5.5"],
            "hidden_models": ["hidden-model", "claude-sonnet-4-6"],
        },
        {
            "raw_models": [
                "gpt-5.5",
                "gpt-5.5",
                "hidden-model",
                "claude-qwen-legacy",
                "claude-haiku-4-5-20251001",
            ],
            "used_fallback": True,
        },
        derived_model_aliases=lambda _models, _provider: ["claude-sonnet-4-6", "extra-model"],
    )
    assert patched["raw_models"] == [
        "gpt-5.5",
        "hidden-model",
        "claude-qwen-legacy",
        "claude-haiku-4-5-20251001",
    ]
    assert patched["models"] == ["gpt-5.5", "claude-haiku-4-5-20251001", "extra-model"]
    assert patched["model_sources"] == {
        "gpt-5.5": "fallback",
        "claude-haiku-4-5-20251001": "fallback",
        "extra-model": "extra",
    }
    assert patched["extra_models"] == ["extra-model", "gpt-5.5", "claude-sonnet-4-6"]
    assert patched["hidden_models"] == ["hidden-model", "claude-sonnet-4-6"]
    assert patched["base_source"] == "fallback"

    providers = [
        {
            "id": "relay-a",
            "name": "Relay A",
            "enabled": True,
            "api_key": "sk-a",
            "models": ["gpt-5.5", "hidden-model", "qwen3.6-plus"],
            "supported_clis": ["codex"],
        },
        {
            "id": "relay-b",
            "name": "Relay B",
            "enabled": True,
            "api_key": "sk-b",
            "models": ["gpt-5.5", "claude-sonnet-4.5"],
            "supported_clis": ["claude"],
        },
        {
            "id": "disabled",
            "name": "Disabled",
            "enabled": False,
            "api_key": "sk-disabled",
            "models": ["gpt-5.4"],
            "supported_clis": ["codex"],
        },
    ]

    kwargs = {
        "provider_candidates": lambda cfg, _default_provider, _default_models: [
            (provider, provider["models"]) for provider in cfg["providers"]
        ],
        "provider_has_configured_base_url": lambda _provider: True,
        "provider_effective_models": lambda _provider, cached_models, _cfg: list(cached_models or []),
        "mms_model_visible": lambda model_name: model_name != "hidden-model",
        "provider_supports_model_for_cli": lambda provider, cli_name, _model_name: cli_name in provider["supported_clis"],
    }

    assert mms_command_tools.all_provider_models_for_cli(
        {"providers": providers},
        "codex",
        {},
        [],
        **kwargs,
    ) == ["gpt-5.5", "qwen3.6-plus"]
    assert mms_command_tools.aggregate_provider_models(
        {"providers": providers},
        "claude",
        {},
        [],
        provider_label=lambda provider: provider["name"],
        default_provider_id="default",
        **kwargs,
    ) == [
        {"model": "gpt-5.5", "provider_id": "relay-b", "provider_name": "Relay B"},
        {"model": "claude-sonnet-4.5", "provider_id": "relay-b", "provider_name": "Relay B"},
    ]


def test_model_display_grouping_helpers_preserve_recommend_and_provider_dedupe():
    import mms_command_tools

    def infer_display(model_name):
        if "qwen" in model_name:
            return ("Qwen", "Qwen 系")
        return ("GPT", "GPT 系")

    assert mms_command_tools.categorize_models(
        ["gpt-5.5", "hidden-model", "qwen3.6-plus"],
        filter_visible_models=lambda models: [item for item in models if item != "hidden-model"],
        infer_model_family=infer_display,
    ) == {"GPT 系": ["gpt-5.5"], "Qwen 系": ["qwen3.6-plus"]}

    rich_calls = []
    console = _CollectingConsole()
    displayed = mms_command_tools.display_models(
        ["gpt-5.5", "hidden-model", "qwen3.6-plus"],
        "recommended",
        ["qwen3.6-plus"],
        ensure_rich=lambda: rich_calls.append("rich"),
        categorize_models=lambda models: mms_command_tools.categorize_models(
            models,
            filter_visible_models=lambda values: [item for item in values if item != "hidden-model"],
            infer_model_family=infer_display,
        ),
        normalize_user_role=lambda role: role,
        mode_recommended="recommended",
        model_capability_summary=lambda model: f"caps:{model}",
        model_cli_summary=lambda model: f"cli:{model}",
        table_cls=_FakeTable,
        console=console,
    )
    assert rich_calls == ["rich"]
    assert displayed == ["qwen3.6-plus"]
    table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert table.kwargs == {"title": "可用模型", "show_lines": True}
    assert table.rows == [
        (("1", "qwen3.6-plus ⭐", "Qwen 系", "caps:qwen3.6-plus", "cli:qwen3.6-plus"), {})
    ]

    def categorize(models):
        buckets = {"GPT 系": [], "Qwen 系": []}
        for model in models:
            buckets["Qwen 系" if "qwen" in model else "GPT 系"].append(model)
        return {key: value for key, value in buckets.items() if value}

    def normalize_role(role):
        return "recommended" if role == "recommended" else "all"

    def infer_family(model_name):
        return ("Qwen", "国产") if "qwen" in model_name else ("GPT", "GPT")

    filter_helper = lambda models, role, recommend: mms_command_tools.filter_models_for_display(
        models,
        role,
        recommend,
        categorize_models=categorize,
        normalize_user_role=normalize_role,
        mode_recommended="recommended",
    )

    assert filter_helper(["gpt-5.5", "qwen3.6-plus"], "recommended", ["qwen3.6-plus"]) == [
        ("qwen3.6-plus", "Qwen 系")
    ]
    assert mms_command_tools.group_models_for_custom(
        ["gpt-5.5", "qwen3.6-plus"],
        "all",
        [],
        filter_models_for_display=filter_helper,
        infer_model_family=infer_family,
    ) == [("GPT", ["gpt-5.5"]), ("Qwen", ["qwen3.6-plus"])]

    grouped = mms_command_tools.group_models_by_family_and_provider(
        [
            {"model": "gpt-5.5", "provider_id": "relay-a", "provider_name": "Relay A"},
            {"model": "gpt-5.5", "provider_id": "relay-a", "provider_name": "Relay A"},
            {"model": "qwen3.6-plus", "provider_id": "relay-b", "provider_name": "Relay B"},
        ],
        "recommended",
        ["gpt-5.5", "qwen3.6-plus"],
        filter_models_for_display=filter_helper,
        infer_model_family=infer_family,
    )
    assert grouped == [
        ("GPT", {"Relay A||relay-a": ["gpt-5.5"]}),
        ("Qwen", {"Relay B||relay-b": ["qwen3.6-plus"]}),
    ]


def test_provider_options_map_helper_preserves_provider_and_account_alternatives():
    import mms_command_tools

    providers = [
        {
            "id": "relay-a",
            "name": "Relay A",
            "enabled": True,
            "api_key": "sk-a",
            "models": ["gpt-5.5"],
            "supported_clis": ["codex"],
        },
        {
            "id": "relay-b",
            "name": "Relay B",
            "enabled": True,
            "api_key": "sk-b",
            "models": ["gpt-5.5", "gpt-5.4"],
            "supported_clis": ["codex"],
        },
    ]
    calls = []

    provider_map = mms_command_tools.build_provider_options_map(
        {"providers": providers},
        "codex",
        {},
        [],
        ["gpt-5.5", "gpt-5.4"],
        infer_model_family=lambda model_name: ("GPT", "GPT"),
        provider_candidates=lambda cfg, _default_provider, _default_models: [
            (provider, provider["models"]) for provider in cfg["providers"]
        ],
        provider_has_configured_base_url=lambda _provider: True,
        provider_effective_models=lambda _provider, cached_models, _cfg: list(cached_models or []),
        provider_supports_model_for_cli=lambda provider, cli_name, _model_name: cli_name in provider["supported_clis"],
        runtime_with_priority=lambda provider, model_name="", family_name="": {
            **provider,
            "runtime_model": model_name,
            "priority_family": family_name,
        },
        provider_label=lambda provider: provider["name"],
        account_options_for_model=lambda _cfg, _cli_name, _default_models, model_info=None, allow_selected_model=False: [
            {
                "title": "Codex Main",
                "runtime": {"id": "codex-main"},
                "priority_family": "GPT",
            }
        ] if model_info == {"model": "gpt-5.5"} and allow_selected_model else [],
        default_provider_id="default",
    )
    assert [item["provider_id"] for item in provider_map["gpt-5.5"]] == ["relay-a", "relay-b", "codex-main"]
    assert "gpt-5.4" not in provider_map

    loader = mms_command_tools.make_provider_options_loader(
        {},
        "codex",
        {},
        [],
        build_provider_options_map=lambda _cfg, _cli, _provider, _models, names: calls.append(tuple(names)) or {
            names[0]: [{"provider_id": "relay-a"}]
        },
    )
    assert loader("gpt-5.5") == [{"provider_id": "relay-a"}]
    assert loader("gpt-5.5") == [{"provider_id": "relay-a"}]
    assert loader("") == []
    assert calls == [("gpt-5.5",)]


def test_apply_runtime_priority_changes_preserves_runtime_and_family_overrides():
    import mms_command_tools

    cfg = {
        "providers": [
            {"id": "relay", "priority": 100, "family_priority_overrides": {"GPT": 200}},
        ],
        "accounts": [
            {"id": "codex-main", "priority": 150, "family_priority_overrides": {"Claude": 90}},
        ],
    }

    changed = mms_command_tools.apply_runtime_priority_changes(
        cfg,
        {
            "relay": "300",
            "relay||gpt": 400,
            "codex-main||claude": "500",
            "missing": 999,
        },
        canonical_model_family=lambda family: {"gpt": "GPT", "claude": "Claude"}.get(str(family).lower(), ""),
        normalize_family_priority_overrides=lambda value: dict(value or {}),
        normalize_priority=lambda value: int(value),
    )

    assert changed is True
    assert cfg["providers"][0]["priority"] == 300
    assert cfg["providers"][0]["family_priority_overrides"] == {"GPT": 400}
    assert cfg["accounts"][0]["priority"] == 150
    assert cfg["accounts"][0]["family_priority_overrides"] == {"Claude": 500}
    assert mms_command_tools.apply_runtime_priority_changes(
        cfg,
        {},
        canonical_model_family=lambda family: family,
        normalize_family_priority_overrides=lambda value: dict(value or {}),
        normalize_priority=lambda value: int(value),
    ) is False


def test_build_model_families_helper_preserves_best_provider_and_usage_shape():
    import mms_command_tools

    providers = [
        {
            "id": "auto-a",
            "name": "Auto A",
            "enabled": True,
            "api_key": "sk-a",
            "role": "auto",
            "priority": 500,
            "models": ["gpt-5.5", "hidden-model"],
            "supported_clis": ["codex"],
        },
        {
            "id": "primary-b",
            "name": "Primary B",
            "enabled": True,
            "api_key": "sk-b",
            "role": "primary",
            "priority": 1,
            "models": ["gpt-5.5", "qwen3.6-plus"],
            "supported_clis": ["codex"],
        },
    ]
    stats = {
        "sources": {
            "provider:codex:auto-a": {
                "cli": "codex",
                "models": {"gpt-5.5": 2},
                "model_last_used_at": {"gpt-5.5": "2026-05-27T10:00:00Z"},
            },
            "provider:codex:primary-b": {
                "cli": "codex",
                "models": {"gpt-5.5": 3, "qwen3.6-plus": 1},
                "last_model": "qwen3.6-plus",
                "last_used_at": "2026-05-28T10:00:00Z",
            },
        }
    }

    families = mms_command_tools.build_model_families_for_cli(
        {"providers": providers},
        "codex",
        {},
        [],
        provider_candidates=lambda cfg, _default_provider, _default_models: [
            (provider, provider["models"]) for provider in cfg["providers"]
        ],
        provider_has_configured_base_url=lambda provider: True,
        provider_effective_models=lambda _provider, cached_models, _cfg: list(cached_models or []),
        normalize_role=lambda role: role if role in {"primary", "auto", "fallback"} else "auto",
        runtime_priority_for_model=lambda provider, _model_name: provider.get("priority", 100),
        runtime_with_priority=lambda provider, model_name="": {**provider, "runtime_model": model_name},
        provider_label=lambda provider: provider["name"],
        mms_model_visible=lambda model_name: model_name != "hidden-model",
        infer_model_family=lambda model_name: ("GPT", "GPT") if model_name.startswith("gpt-") else ("Qwen", "Qwen"),
        load_usage_stats=lambda: stats,
        provider_supports_model_for_cli=lambda provider, cli_name, _model_name: cli_name in provider["supported_clis"],
        role_weights={"primary": 0, "auto": 1, "fallback": 2},
        default_provider_id="default",
    )

    gpt_model = families[0]["models"][0]
    assert families[0]["family"] == "GPT"
    assert gpt_model["provider_id"] == "primary-b"
    assert gpt_model["provider_name"] == "Primary B"
    assert gpt_model["provider_ctx"]["runtime_model"] == "gpt-5.5"
    assert gpt_model["use_count"] == 5
    assert gpt_model["last_used_at"] == "2026-05-27T10:00:00Z"
    assert families[1]["models"][0]["model"] == "qwen3.6-plus"
    assert families[1]["models"][0]["last_used_at"] == "2026-05-28T10:00:00Z"
    assert all(item["model"] != "hidden-model" for family in families for item in family["models"])


def test_resolve_best_provider_helper_preserves_role_priority_and_filters():
    import mms_command_tools

    providers = [
        {
            "id": "auto-high",
            "name": "Auto High",
            "enabled": True,
            "api_key": "sk-auto",
            "role": "auto",
            "priority": 999,
            "protocols": ["anthropic_messages"],
            "models": ["gpt-5.5"],
            "supported_clis": ["claude"],
        },
        {
            "id": "primary-low",
            "name": "Primary Low",
            "enabled": True,
            "api_key": "sk-primary",
            "role": "primary",
            "priority": 1,
            "protocols": ["anthropic_messages"],
            "models": ["gpt-5.5"],
            "supported_clis": ["claude"],
        },
        {
            "id": "wrong-protocol",
            "name": "Wrong Protocol",
            "enabled": True,
            "api_key": "sk-wrong",
            "role": "primary",
            "priority": 1000,
            "protocols": ["openai_chat_completions"],
            "models": ["gpt-5.5"],
            "supported_clis": ["claude"],
        },
    ]

    runtime, label = mms_command_tools.resolve_best_provider(
        {"providers": providers},
        "GPT-5.5",
        {},
        [],
        cli_name="claude",
        protocol="anthropic_messages",
        provider_candidates=lambda cfg, _default_provider, _default_models: [
            (provider, provider["models"]) for provider in cfg["providers"]
        ],
        provider_supports_model_for_cli=lambda provider, cli_name, _model_name: cli_name in provider["supported_clis"],
        provider_has_configured_base_url=lambda _provider: True,
        provider_effective_models=lambda _provider, cached_models, _cfg: list(cached_models or []),
        normalize_role=lambda role: role if role in {"primary", "auto", "fallback"} else "auto",
        runtime_priority_for_model=lambda provider, _model_name: provider.get("priority", 100),
        provider_label=lambda provider: provider["name"],
        runtime_with_priority=lambda provider, model_name="": {**provider, "runtime_model": model_name},
        role_weights={"primary": 0, "auto": 1, "fallback": 2},
    )

    assert runtime["id"] == "primary-low"
    assert runtime["runtime_model"] == "GPT-5.5"
    assert label == "Primary Low"

    missing, missing_label = mms_command_tools.resolve_best_provider(
        {"providers": providers},
        "missing-model",
        {},
        [],
        provider_candidates=lambda cfg, _default_provider, _default_models: [
            (provider, provider["models"]) for provider in cfg["providers"]
        ],
        provider_supports_model_for_cli=lambda *_args: True,
        provider_has_configured_base_url=lambda _provider: True,
        provider_effective_models=lambda _provider, cached_models, _cfg: list(cached_models or []),
        normalize_role=lambda role: role,
        runtime_priority_for_model=lambda provider, _model_name: provider.get("priority", 100),
        provider_label=lambda provider: provider["name"],
        runtime_with_priority=lambda provider, model_name="": provider,
        role_weights={"primary": 0, "auto": 1, "fallback": 2},
    )
    assert (missing, missing_label) == (None, None)


def test_provider_options_helper_preserves_selected_model_filtering():
    import mms_command_tools

    class Logger:
        def debug(self, *_args, **_kwargs):
            pass

        def info(self, *_args, **_kwargs):
            pass

    default_provider = {"id": "default"}
    providers = [
        {
            "id": "default",
            "name": "Default",
            "enabled": True,
            "api_key": "sk-default",
            "priority": 100,
            "models": ["gpt-5.5", "qwen3.6-plus"],
            "supported_clis": ["codex"],
        },
        {
            "id": "disabled",
            "name": "Disabled",
            "enabled": False,
            "api_key": "sk-disabled",
            "priority": 300,
            "models": ["gpt-5.5"],
            "supported_clis": ["codex"],
        },
    ]

    options = mms_command_tools.provider_options_for_model(
        {"providers": providers},
        "codex",
        default_provider,
        [],
        model_info={"model": "gpt-5.5"},
        infer_model_family=lambda model_name: ("GPT", "GPT") if model_name.startswith("gpt-") else ("Other", "Other"),
        probe_debug_logger=Logger(),
        provider_candidates=lambda cfg, _default_provider, _default_models: [
            (provider, provider["models"]) for provider in cfg["providers"]
        ],
        provider_has_configured_base_url=lambda provider: True,
        provider_effective_models=lambda _provider, cached_models, _cfg: list(cached_models or []),
        provider_models_for_cli=lambda _cli_name, models: list(models or []),
        provider_supports_model_for_cli=lambda provider, cli_name, model_name: (
            cli_name in provider["supported_clis"] and model_name in provider["models"]
        ),
        provider_supports_cli_name=lambda provider, cli_name: cli_name in provider["supported_clis"],
        runtime_with_priority=lambda provider, model_name="", family_name="": {
            **provider,
            "runtime_model": model_name,
            "priority_family": family_name,
        },
        runtime_choice_label=lambda provider: f"runtime:{provider['id']}",
        provider_label=lambda provider: provider["name"],
        runtime_priority_for_family=lambda provider, _family_name: provider.get("priority", 100),
        default_priority=100,
    )

    assert len(options) == 1
    option = options[0]
    assert option["id"] == "default"
    assert option["models"] == ["gpt-5.5"]
    assert option["runtime"]["runtime_model"] == "gpt-5.5"
    assert option["priority"] == 100
    assert option["priority_family"] == "GPT"
    assert option["is_default"] is True


def test_account_options_helper_preserves_oauth_filtering_and_default_marker():
    import mms_command_tools

    cfg = {
        "accounts": [
            {"id": "codex-main", "name": "Codex Main", "cli": "codex", "enabled": True},
            {"id": "claude-main", "name": "Claude Main", "cli": "claude", "enabled": True},
            {"id": "disabled", "name": "Disabled", "cli": "codex", "enabled": False},
            {"id": "bad", "name": "Bad", "cli": "badcli", "enabled": True},
        ],
        "account": {"defaults": {"codex": "codex-main"}},
    }
    accounts = {
        "codex-main": {"id": "codex-main", "name": "Codex Main", "cli": "codex", "priority": 250},
        "claude-main": {"id": "claude-main", "name": "Claude Main", "cli": "claude", "priority": 300},
    }

    assert mms_command_tools.account_options_for_model(
        cfg,
        "codex",
        ["gpt-5.5"],
        model_info={"model": "gpt-5.5"},
        allow_selected_model=False,
        infer_model_family=lambda model_name: ("GPT", "GPT") if model_name.startswith("gpt-") else ("Other", "Other"),
        oauth_capable_clis=("claude", "codex"),
        model_matches_account_cli=lambda cli_name, model_name: cli_name == "codex" and model_name.startswith("gpt-"),
        resolve_account_context=lambda _cfg, account_id, cli_name: accounts[account_id],
        runtime_with_priority=lambda runtime, model_name="", family_name="": {
            **runtime,
            "runtime_model": model_name,
            "priority_family": family_name,
        },
        runtime_choice_label=lambda runtime: f"runtime:{runtime['id']}",
        account_label=lambda account: account["name"],
        default_priority=100,
    ) == []

    options = mms_command_tools.account_options_for_model(
        cfg,
        "codex",
        ["gpt-5.5", "gpt-5.4"],
        model_info={"model": "gpt-5.5"},
        allow_selected_model=True,
        infer_model_family=lambda model_name: ("GPT", "GPT") if model_name.startswith("gpt-") else ("Other", "Other"),
        oauth_capable_clis=("claude", "codex"),
        model_matches_account_cli=lambda cli_name, model_name: cli_name == "codex" and model_name.startswith("gpt-"),
        resolve_account_context=lambda _cfg, account_id, cli_name: accounts[account_id],
        runtime_with_priority=lambda runtime, model_name="", family_name="": {
            **runtime,
            "runtime_model": model_name,
            "priority_family": family_name,
        },
        runtime_choice_label=lambda runtime: f"runtime:{runtime['id']}",
        account_label=lambda account: account["name"],
        default_priority=100,
    )

    assert len(options) == 1
    option = options[0]
    assert option["id"] == "codex-main"
    assert option["models"] == ["gpt-5.5"]
    assert option["priority"] == 250
    assert option["priority_family"] == "GPT"
    assert option["is_default"] is True
    assert option["launch_cli"] == "codex"


def test_runtime_source_selection_helpers_preserve_sort_defaults_and_trace_ids():
    import mms_command_tools

    provider_options = [
        {
            "kind": "provider",
            "id": "relay",
            "runtime": {"id": "relay", "runtime_kind": "provider", "auth_mode": "api_key"},
            "models": ["gpt-5.5"],
            "priority": 100,
            "launch_cli": "codex",
            "is_default": True,
            "title": "Relay",
        }
    ]
    account_options = [
        {
            "kind": "account",
            "id": "codex-main",
            "runtime": {"id": "codex-main", "auth_mode": "oauth"},
            "models": ["gpt-5.5"],
            "priority": 200,
            "launch_cli": "codex",
            "is_default": False,
            "title": "Codex Main",
        }
    ]
    broker_options = [
        {
            "kind": "broker",
            "id": "broker",
            "runtime": {"id": "broker", "auth_mode": "broker_profile", "name": "Broker"},
            "models": ["gpt-5.5"],
            "priority": 200,
            "launch_cli": "claude",
            "is_default": False,
            "title": "Broker",
        }
    ]

    runtime, models = mms_command_tools.resolve_provider_for_cli(
        {},
        "codex",
        {},
        [],
        provider_options_for_model=lambda *_args, **_kwargs: provider_options,
        cli_model_family_hints={"codex": "GPT"},
    )
    assert runtime["id"] == "relay"
    assert models == ["gpt-5.5"]
    assert mms_command_tools.resolve_source_default_index(account_options + provider_options, "codex") == 1

    options, default_choice = mms_command_tools.list_runtime_sources(
        {},
        "codex",
        {},
        [],
        provider_options_for_model=lambda *_args, **_kwargs: list(provider_options),
        account_options_for_model=lambda *_args, **_kwargs: list(account_options),
        broker_options_for_cli=lambda *_args, **_kwargs: list(broker_options),
        default_priority=100,
    )
    assert [item["id"] for item in options] == ["codex-main", "broker", "relay"]
    assert default_choice == 2

    assert mms_command_tools.runtime_choice_label(
        {"id": "relay", "auth_mode": "api_key"},
        account_label=lambda runtime: runtime["id"],
        provider_label=lambda runtime: runtime["id"],
    ) == "网关 / relay"
    assert mms_command_tools.runtime_choice_label(
        {"id": "codex-main", "auth_mode": "oauth"},
        account_label=lambda runtime: runtime["id"],
        provider_label=lambda runtime: runtime["id"],
    ) == "官方 / codex-main"
    assert mms_command_tools.trace_runtime_provider_id({"id": "relay", "auth_mode": "api_key"}) == "relay"
    assert mms_command_tools.trace_runtime_account_id({"id": "codex-main", "auth_mode": "oauth"}) == "codex-main"
    assert mms_command_tools.trace_runtime_account_id({"id": "bridge", "auth_mode": "oauth_bridge", "bridge_account_id": "acct"}) == "acct"
    assert mms_command_tools.trace_runtime_bridge({"auth_mode": "oauth_bridge", "bridge_url": "http://bridge"}) == "http://bridge"
    assert mms_command_tools.runtime_source_kind_label({"runtime_kind": "opencode_profile"}) == "OpenCode"
    assert mms_command_tools.runtime_source_kind_label({"runtime_kind": "broker"}) == "Broker"
    assert mms_command_tools.runtime_source_kind_label({"auth_mode": "oauth_bridge"}) == "官方桥接"
    assert mms_command_tools.runtime_source_kind_label({"auth_mode": "oauth"}) == "官方"
    trace_calls = []
    mms_command_tools.trace_runtime_choice(
        "runtime resolve",
        {"id": "bridge", "auth_mode": "oauth_bridge", "bridge_account_id": "acct", "bridge_url": "http://bridge"},
        launch_cli="claude",
        choice="Bridge",
        trace_record=lambda source, **payload: trace_calls.append((source, payload)),
    )
    assert trace_calls == [
        (
            "runtime resolve",
            {
                "cli": "claude",
                "provider": "",
                "account": "acct",
                "bridge": "http://bridge",
                "runtime": "oauth_bridge",
                "choice": "Bridge",
            },
        )
    ]


def test_runtime_resolver_helpers_preserve_provider_and_managed_oauth_paths():
    import mms_command_tools

    calls = []
    providers = {
        "override": {"id": "override", "runtime_kind": "provider", "models": ["gpt-5.5"]},
        "default": {"id": "default", "runtime_kind": "provider", "models": ["gpt-5.4"]},
    }
    accounts = {
        "codex-main": {"id": "codex-main", "auth_mode": "oauth", "enabled": True},
        "disabled": {"id": "disabled", "auth_mode": "oauth", "enabled": False},
    }

    def resolve_provider_for_cli(_cfg, cli_name, provider, models):
        calls.append(("provider_for_cli", cli_name, provider["id"], tuple(models or [])))
        return {**provider, "selected": cli_name}, list(models or [])

    runtime, models = mms_command_tools.resolve_launch_runtime(
        {},
        "codex",
        providers["default"],
        ["gpt-5.4"],
        provider_id="override",
        resolve_provider_context=lambda _cfg, provider_id: providers[provider_id],
        resolve_provider_for_cli=resolve_provider_for_cli,
        probe_models=lambda provider, emit_output=False: {"models": provider["models"]},
        managed_oauth_clis=("codex", "agy"),
        resolve_account_context=lambda *_args, **_kwargs: None,
    )
    assert runtime["id"] == "override"
    assert models == ["gpt-5.5"]
    assert calls[-1] == ("provider_for_cli", "codex", "override", ("gpt-5.5",))

    runtime, models = mms_command_tools.resolve_launch_runtime(
        {},
        "codex",
        providers["default"],
        ["gpt-5.4"],
        account_id="disabled",
        resolve_provider_context=lambda _cfg, provider_id: providers[provider_id],
        resolve_provider_for_cli=resolve_provider_for_cli,
        probe_models=lambda provider, emit_output=False: {"models": provider["models"]},
        managed_oauth_clis=("codex", "agy"),
        resolve_account_context=lambda _cfg, account_id=None, cli_name=None: accounts.get(account_id),
    )
    assert runtime["id"] == "disabled"
    assert models == ["gpt-5.4"]

    runtime, models = mms_command_tools.resolve_launch_runtime(
        {},
        "codex",
        providers["default"],
        ["gpt-5.4"],
        resolve_provider_context=lambda _cfg, provider_id: providers[provider_id],
        resolve_provider_for_cli=resolve_provider_for_cli,
        probe_models=lambda provider, emit_output=False: {"models": provider["models"]},
        managed_oauth_clis=("codex", "agy"),
        resolve_account_context=lambda _cfg, account_id=None, cli_name=None: accounts["codex-main"],
    )
    assert runtime["id"] == "codex-main"
    assert models == ["gpt-5.4"]

    runtime, models = mms_command_tools.resolve_provider_runtime(
        {},
        "claude",
        providers["default"],
        ["gpt-5.4"],
        provider_id="override",
        resolve_provider_context=lambda _cfg, provider_id: providers[provider_id],
        resolve_provider_for_cli=resolve_provider_for_cli,
        probe_models=lambda provider, emit_output=False: {"models": provider["models"]},
    )
    assert runtime["id"] == "override"
    assert models == ["gpt-5.5"]


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


def test_preset_helper_path_and_missing_preset_message(tmp_path):
    import mms_command_tools

    messages = []
    path = mms_command_tools.preset_env_file_path("Demo Preset!", env_dir=str(tmp_path))
    assert path == str(tmp_path / "demo-preset.sh")

    result = mms_command_tools.resolve_named_preset(
        {"presets": {"demo": {"cli": "claude"}}},
        "missing",
        normalize_preset_entry=lambda name, preset: {"name": name, **preset},
        emit_preset_error=lambda message, stderr_only=False: messages.append((message, stderr_only)),
    )

    assert result is None
    assert messages == [
        ("预设 'missing' 不存在", False),
        ("可用预设: demo", False),
    ]


def test_preset_export_runtime_uses_provider_override_and_exports():
    import mms_command_tools

    calls = []

    result = mms_command_tools.resolve_preset_export_runtime(
        {"providers": []},
        {"cli": "claude", "provider": "relay"},
        provider_override="override",
        infer_preset_auth_mode=mms_command_tools.infer_preset_auth_mode,
        emit_preset_error=lambda message, stderr_only=False: calls.append(("error", message, stderr_only)),
        ensure_provider_credentials=lambda cfg, provider_id: calls.append(("provider", provider_id)) or {"id": provider_id},
        validate_provider_for_cli=lambda cli, runtime: calls.append(("validate", cli, runtime["id"])),
        get_export_env=lambda cli, runtime: calls.append(("exports", cli, runtime["id"])) or {"A": "B"},
    )

    assert result == ("claude", {"A": "B"}, {"id": "override"})
    assert calls == [
        ("provider", "override"),
        ("validate", "claude", "override"),
        ("exports", "claude", "override"),
    ]


def test_preset_export_runtime_rejects_oauth_without_resolving_provider():
    import mms_command_tools

    messages = []

    result = mms_command_tools.resolve_preset_export_runtime(
        {"providers": []},
        {"cli": "claude", "account": "claude-a"},
        infer_preset_auth_mode=mms_command_tools.infer_preset_auth_mode,
        emit_preset_error=lambda message, stderr_only=False: messages.append((message, stderr_only)),
        ensure_provider_credentials=lambda cfg, provider_id: (_ for _ in ()).throw(AssertionError("must not resolve provider")),
        validate_provider_for_cli=lambda cli, runtime: None,
        get_export_env=lambda cli, runtime: {},
    )

    assert result is None
    assert messages == [("此预设使用 oauth 模式，不支持 env export", False)]


def test_presets_command_renders_only_visible_presets():
    import mms_command_tools

    console = _CollectingConsole()
    cfg = {
        "presets": {
            "visible": {
                "cli": "claude",
                "provider": "relay",
                "model": "sonnet",
                "description": "daily",
            },
            "hidden": {"cli": "claude", "account": "official"},
        }
    }

    mms_command_tools.handle_presets_command(
        cfg,
        preset_has_visible_model_options=lambda preset: "model" in preset,
        infer_preset_auth_mode=mms_command_tools.infer_preset_auth_mode,
        default_provider_id="default",
        table_cls=_FakeTable,
        console=console,
    )

    tables = [item for item in console.items if isinstance(item, _FakeTable)]
    assert len(tables) == 1
    assert tables[0].rows == [(("visible", "claude", "relay", "sonnet", "daily", "api_key"), {})]


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


def test_select_provider_for_models_filters_providers_and_reprompts_invalid():
    import mms_command_tools

    answers = ["bad", "2"]

    class Prompt:
        @staticmethod
        def ask(*_args, **_kwargs):
            return answers.pop(0)

    console = _CollectingConsole()
    selected = mms_command_tools.select_provider_for_models(
        {},
        list_manage_targets=lambda _cfg: [
            {"kind": "account", "id": "codex-main", "title": "Codex"},
            {"kind": "provider", "id": "relay-a", "title": "Relay A", "default_label": "是", "status": "启用"},
            {"kind": "provider", "id": "relay-b", "title": "Relay B", "default_label": "", "status": "启用"},
        ],
        table_cls=_FakeTable,
        prompt_cls=Prompt,
        console=console,
    )

    assert selected == "relay-b"
    table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert table.kwargs == {"title": "模型与测速 · 选择通道", "show_lines": True}
    assert table.rows == [
        (("1", "Relay A", "relay-a", "是", "启用"), {}),
        (("2", "Relay B", "relay-b", "", "启用"), {}),
    ]
    assert any("请输入 1-2 的编号" in str(item) for item in console.items)


def test_select_provider_for_models_returns_none_without_provider_targets():
    import mms_command_tools

    class Prompt:
        @staticmethod
        def ask(*_args, **_kwargs):
            raise AssertionError("empty provider list must not prompt")

    console = _CollectingConsole()
    assert mms_command_tools.select_provider_for_models(
        {},
        list_manage_targets=lambda _cfg: [{"kind": "account", "id": "codex-main"}],
        table_cls=_FakeTable,
        prompt_cls=Prompt,
        console=console,
    ) is None
    assert any("当前还没有可管理的网关通道" in str(item) for item in console.items)


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


def test_pick_manual_models_parses_unique_valid_indexes_only():
    import mms_command_tools

    class Prompt:
        @staticmethod
        def ask(*_args, **_kwargs):
            return "2, bad, 2, 4, 1"

    console = _CollectingConsole()
    selected = mms_command_tools.pick_manual_models(
        ["gpt-5.5", "gpt-5.4", "qwen3.6-plus"],
        table_cls=_FakeTable,
        prompt_cls=Prompt,
        console=console,
    )

    assert selected == ["gpt-5.4", "gpt-5.5"]
    table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert table.kwargs == {"title": "选择要预热的模型", "show_lines": True}
    assert table.rows == [
        (("1", "gpt-5.5"), {}),
        (("2", "gpt-5.4"), {}),
        (("3", "qwen3.6-plus"), {}),
    ]


def test_pick_manual_models_empty_and_blank_cancel_without_selection():
    import mms_command_tools

    class Prompt:
        @staticmethod
        def ask(*_args, **_kwargs):
            return "  "

    assert mms_command_tools.pick_manual_models(
        [],
        table_cls=_FakeTable,
        prompt_cls=Prompt,
        console=_CollectingConsole(),
    ) == []
    assert mms_command_tools.pick_manual_models(
        ["gpt-5.5"],
        table_cls=_FakeTable,
        prompt_cls=Prompt,
        console=_CollectingConsole(),
    ) == []


def test_warm_command_uses_recent_models_without_live_requests():
    import mms_command_tools

    rows = [
        {
            "last_model": "gpt-5.5",
            "models": {"gpt-5.4": 3, "gpt-5.5": 7, "": 99},
        },
        {
            "last_model": "gpt-5.4",
            "models": {"qwen3.6-plus": 10, "gpt-5.5": 2},
        },
    ]
    assert mms_command_tools.recent_models_for_provider(
        "relay",
        usage_rows_for_runtime=lambda runtime_kind, runtime_id: rows
        if (runtime_kind, runtime_id) == ("provider", "relay")
        else [],
    ) == ["gpt-5.5", "gpt-5.4", "qwen3.6-plus"]

    class Panel:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class Prompt:
        @staticmethod
        def ask(*_args, **_kwargs):
            return "1"

    class Confirm:
        @staticmethod
        def ask(*_args, **_kwargs):
            raise AssertionError("recent warm path should not ask confirm")

    calls = []
    console = _CollectingConsole()
    provider = {"id": "relay", "name": "Relay"}

    mms_command_tools.handle_warm_command(
        {"providers": [provider]},
        ["relay"],
        command_name="mmg",
        provider_map=lambda cfg: {"relay": provider},
        select_provider_for_warm=lambda cfg: "relay",
        resolve_provider_context=lambda cfg, provider_id: provider,
        probe_models=lambda provider_arg, emit_output=False: {"models": ["gpt-5.5", "gpt-5.4"]},
        recent_models_for_provider=lambda provider_id: ["gpt-5.4"],
        pick_manual_models=lambda models: (_ for _ in ()).throw(AssertionError("manual picker should not run")),
        warm_model_request=lambda provider_arg, model_name: calls.append((provider_arg["id"], model_name)) or (True, "ok"),
        text_cls=str,
        panel_cls=Panel,
        prompt_cls=Prompt,
        confirm_cls=Confirm,
        table_cls=_FakeTable,
        console=console,
    )

    assert calls == [("relay", "gpt-5.4")]
    tables = [item for item in console.items if isinstance(item, _FakeTable)]
    assert tables
    assert tables[0].rows[0][0] == ("gpt-5.4", "成功", "ok")


def test_warm_command_unknown_provider_exits_before_probe():
    import pytest
    import mms_command_tools

    console = _CollectingConsole()

    with pytest.raises(SystemExit) as exc:
        mms_command_tools.handle_warm_command(
            {"providers": [{"id": "relay"}]},
            ["missing"],
            command_name="mmg",
            provider_map=lambda cfg: {"relay": cfg["providers"][0]},
            select_provider_for_warm=lambda cfg: "relay",
            resolve_provider_context=lambda cfg, provider_id: (_ for _ in ()).throw(AssertionError("must not resolve")),
            probe_models=lambda provider, emit_output=False: (_ for _ in ()).throw(AssertionError("must not probe")),
            recent_models_for_provider=lambda provider_id: [],
            pick_manual_models=lambda models: [],
            warm_model_request=lambda provider, model: (True, "ok"),
            text_cls=str,
            panel_cls=object,
            prompt_cls=object,
            confirm_cls=object,
            table_cls=_FakeTable,
            console=console,
        )

    assert exc.value.code == 1
    assert any("未找到模型源: missing" in str(item) for item in console.items)


def test_export_command_writes_temp_env_file(tmp_path):
    import mms_command_tools

    console = _CollectingConsole()
    env_path = tmp_path / "claude.sh"

    mms_command_tools.handle_export(
        "claude",
        {"id": "relay"},
        apply=True,
        cli_names=["claude", "codex"],
        get_export_env=lambda cli, provider: {"ANTHROPIC_BASE_URL": "https://relay.example/v1", "API_KEY": "a b"},
        env_dir=str(tmp_path),
        env_file_path=lambda cli: str(env_path),
        display_title=lambda: "MMS",
        export_command_hint=lambda cli: f"mmg --export {cli} --apply",
        console=console,
    )

    text = env_path.read_text(encoding="utf-8")
    assert "# Generated by MMS" in text
    assert "export ANTHROPIC_BASE_URL=https://relay.example/v1" in text
    assert "export API_KEY='a b'" in text
    assert any("不会自动修改 ~/.zshrc" in str(item) for item in console.items)


def test_export_command_rejects_unsupported_cli_before_export_lookup():
    import mms_command_tools

    console = _CollectingConsole()

    mms_command_tools.handle_export(
        "unknown",
        {"id": "relay"},
        cli_names=["claude", "codex"],
        get_export_env=lambda cli, provider: (_ for _ in ()).throw(AssertionError("must not lookup exports")),
        env_dir="/tmp",
        env_file_path=lambda cli: "/tmp/out.sh",
        display_title=lambda: "MMS",
        export_command_hint=lambda cli: f"mmg --export {cli} --apply",
        console=console,
    )

    assert any("不支持的 CLI: unknown" in str(item) for item in console.items)
    assert any("claude, codex" in str(item) for item in console.items)


def test_config_help_display_helpers_render_expected_sections(tmp_path):
    import mms_command_tools

    active_path = tmp_path / "preferences.toml"
    active_path.write_text("# prefs\n", encoding="utf-8")
    missing_path = tmp_path / "missing.toml"
    console = _CollectingConsole()

    mms_command_tools.display_config_help(command_name="mmg", console=console)
    mms_command_tools.display_preferences_path(
        preference_paths=[str(active_path), str(missing_path)],
        preferences_doc_path="/docs/prefs.md",
        console=console,
    )
    mms_command_tools.display_preferences_help(
        command_name="mmg",
        preference_paths=[str(active_path)],
        preferences_doc_path="/docs/prefs.md",
        console=console,
    )
    mms_command_tools.display_human_gate_help(
        command_name="mmg",
        preferences_doc_path="/docs/prefs.md",
        console=console,
    )
    mms_command_tools.display_preferences_example(
        preferences_example_toml="[launch.defaults]\nreasoning_effort = \"high\"\n",
        console=console,
    )

    text = "\n".join(str(item) for item in console.items)
    assert "mmg config provider.list" in text
    assert "active" in text
    assert "create-if-needed" in text
    assert "preferences.toml" in text
    assert "human-only" in text
    assert "[launch.defaults]" in text


def test_usage_stats_display_sorts_recent_sources():
    import mms_command_tools

    console = _CollectingConsole()

    mms_command_tools.display_usage_stats(
        load_usage_stats=lambda: {
            "sources": {
                "old": {
                    "runtime_kind": "provider",
                    "name": "Old",
                    "cli": "claude",
                    "launches": 2,
                    "last_model": "sonnet",
                    "last_used_at": "2026-01-01T00:00:00Z",
                },
                "new": {
                    "runtime_kind": "account",
                    "name": "New",
                    "cli": "codex",
                    "launches": 1,
                    "last_model": "gpt-5.5",
                    "last_used_at": "2026-05-01T00:00:00Z",
                },
            }
        },
        usage_path="/tmp/usage.json",
        table_cls=_FakeTable,
        console=console,
    )

    table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert table.rows[0][0][0] == "account / New"
    assert table.rows[1][0][0] == "provider / Old"


def test_adapter_registry_display_renders_policy():
    import mms_command_tools

    console = _CollectingConsole()

    mms_command_tools.display_adapter_registry(
        top_source_companies=[
            {
                "company": "Example",
                "brand": "Relay",
                "families": ["GPT"],
                "default_adapter": "openai",
                "current_support": "supported",
                "oauth_native": False,
                "claude_bridge_default": True,
            }
        ],
        default_adapter_policy={"gpt": "use openai"},
        command_name="mmg",
        table_cls=_FakeTable,
        console=console,
    )

    table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert table.rows[0][0] == ("1", "Example / Relay", "GPT", "openai", "supported", "no", "yes")
    assert any("gpt" in str(item) and "use openai" in str(item) for item in console.items)
    assert any("mmg config adapter.registry" in str(item) for item in console.items)


def test_provider_account_display_helpers_render_rows():
    import mms_command_tools

    console = _CollectingConsole()
    cfg = {
        "provider": {"default": "relay"},
        "providers": [
            {
                "id": "relay",
                "name": "Relay",
                "protocols": ["openai"],
                "supported_clis": ["codex"],
                "enabled": True,
                "openai_base_url": "https://relay.example/v1",
            },
            {
                "id": "backup",
                "name": "Backup",
                "protocols": ["anthropic"],
                "supported_clis": ["claude"],
                "enabled": False,
                "anthropic_base_url": "https://anthropic.example/v1",
            },
        ],
    }

    mms_command_tools.display_providers(
        cfg,
        default_provider_id="default",
        default_priority=100,
        resolve_provider_context=lambda cfg_arg, provider_id: next(
            provider for provider in cfg_arg["providers"] if provider["id"] == provider_id
        ),
        provider_openai_base_url=lambda provider: provider.get("openai_base_url", ""),
        provider_anthropic_base_url=lambda provider: provider.get("anthropic_base_url", ""),
        command_name="mmg",
        table_cls=_FakeTable,
        console=console,
    )

    provider_table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert provider_table.rows[0][0] == (
        "relay",
        "Relay",
        "openai",
        "codex",
        "100",
        "默认 启用",
        "https://relay.example/v1",
    )
    assert provider_table.rows[1][0][5] == "禁用"

    console.items.clear()
    mms_command_tools.display_accounts(
        {
            "account": {"defaults": {"codex": "codex-a"}},
            "accounts": [
                {
                    "id": "codex-a",
                    "name": "Codex A",
                    "cli": "codex",
                    "priority": 200,
                    "enabled": True,
                    "home_dir": "/tmp/codex-a",
                }
            ],
        },
        default_priority=100,
        probe_account_status=lambda account: {"summary": "logged-in"},
        command_name="mmg",
        table_cls=_FakeTable,
        console=console,
    )

    account_table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert account_table.rows[0][0] == (
        "codex-a",
        "Codex A",
        "codex",
        "200",
        "默认 启用",
        "logged-in",
        "/tmp/codex-a",
    )


def test_runtime_usage_display_handles_tui_empty_and_rows():
    import mms_command_tools

    events = []
    console = _CollectingConsole()

    mms_command_tools.display_runtime_usage(
        "provider",
        "relay",
        "Relay",
        use_tui=lambda: True,
        clear_console=lambda: events.append("clear"),
        usage_rows_for_runtime=lambda kind, runtime_id: [],
        active_usage_path=lambda: "/tmp/usage.json",
        pause_after_tui_report=lambda message: events.append(("pause", message)),
        table_cls=_FakeTable,
        console=console,
    )

    assert events == ["clear", ("pause", "按 Enter 返回通道详情")]
    assert any("Relay 还没有本地启动统计" in str(item) for item in console.items)

    events.clear()
    console.items.clear()
    mms_command_tools.display_runtime_usage(
        "account",
        "codex-a",
        "Codex A",
        use_tui=lambda: False,
        clear_console=lambda: events.append("clear"),
        usage_rows_for_runtime=lambda kind, runtime_id: [
            {"cli": "codex", "launches": 3, "last_model": "gpt-5.5", "last_used_at": "2026-05-28"}
        ],
        active_usage_path=lambda: "/tmp/usage.json",
        pause_after_tui_report=lambda message: events.append(("pause", message)),
        table_cls=_FakeTable,
        console=console,
    )

    assert events == []
    table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert table.rows[0][0] == ("codex", "3", "gpt-5.5", "2026-05-28")


def test_config_display_renders_summary_and_masks_keys():
    import mms_command_tools

    console = _CollectingConsole()
    provider_calls = []
    account_calls = []
    cfg = {
        "provider": {"default": "relay"},
        "providers": [{"id": "relay"}],
        "account": {},
        "accounts": [],
        "cache": {"probe_async_refresh_after_sec": 10, "probe_async_min_interval_sec": 5},
        "nested": {"api_key": "abcd1234efgh", "plain": "value"},
    }

    mms_command_tools.display_config(
        cfg,
        resolve_provider_context=lambda cfg_arg: {"api_key": "sk-1234567890", "openai_base_url": "https://relay.example/v1"},
        provider_openai_base_url=lambda provider: provider.get("openai_base_url", ""),
        provider_anthropic_base_url=lambda provider: provider.get("anthropic_base_url", ""),
        mask_key=lambda value: "MASKED",
        active_credentials_path=lambda: "/tmp/credentials.sh",
        active_usage_path=lambda: "/tmp/usage.json",
        display_providers=lambda cfg_arg: provider_calls.append(cfg_arg),
        display_accounts=lambda cfg_arg: account_calls.append(cfg_arg),
        probe_async_refresh_after=1800,
        probe_async_min_interval=300,
        existing_override_paths=lambda: [],
        override_paths=["/tmp/override.toml"],
        existing_preferences_paths=lambda: ["/tmp/preferences.toml"],
        preference_paths=["/tmp/default-preferences.toml"],
        command_name="mmg",
        console=console,
    )

    text = "\n".join(str(item) for item in console.items)
    assert provider_calls == [cfg]
    assert account_calls == [cfg]
    assert "openai_base_url" in text
    assert "/tmp/credentials.sh" in text
    assert "probe_async_refresh_after_sec" in text
    assert "mmg config preferences.help" in text
    assert "MASKED" in text
    assert "plain" in text


def test_config_nested_helpers_and_coercion():
    import pytest
    import mms_command_tools
    import mms_core

    data = {}
    assert mms_command_tools.mask_key("abcd1234efgh") == "abcd****efgh"
    assert mms_command_tools.mask_key("short") == "****"

    mms_command_tools.set_nested(data, ["a", "b", "c"], "value")
    assert data == {"a": {"b": {"c": "value"}}}
    assert mms_command_tools.get_nested(data, ["a", "b", "c"]) == ("value", True)
    assert mms_command_tools.get_nested(data, ["a", "missing"]) == (None, False)
    assert mms_command_tools.unset_nested(data, ["a", "b", "c"]) is True
    assert mms_command_tools.unset_nested(data, ["a", "b", "c"]) is False

    coerce = lambda key, value: mms_command_tools.coerce_config_value(
        key,
        value,
        validate_user_role=lambda raw: f"role:{raw}",
        normalize_language=lambda raw: {"zh": "zh", "en": "en"}.get(str(raw).strip()),
        normalize_positive_seconds=lambda raw, minimum: max(int(raw), minimum),
    )
    assert coerce("user.role", "dev") == "role:dev"
    assert coerce("ui.language", "zh") == "zh"
    assert coerce("provider.default", " relay ") == "relay"
    assert coerce("cache.probe_async_min_interval_sec", "0") == 1
    assert coerce("provider.relay.enabled", "yes") is True
    with pytest.raises(ValueError):
        coerce("ui.language", "fr")

    wrapped = {}
    mms_core._set_nested(wrapped, ["x", "y"], "z")
    assert mms_core._get_nested(wrapped, ["x", "y"]) == ("z", True)
    assert mms_core._unset_nested(wrapped, ["x", "y"]) is True
    assert mms_core._mask_key("abcd1234efgh") == "abcd****efgh"


def test_config_ensure_helpers_dedupe_and_repair_defaults():
    import mms_command_tools

    providers_cfg, changed = mms_command_tools.ensure_provider_config(
        {
            "providers": [{"id": "relay-b"}, {"id": "relay-b"}, {"id": "relay-a"}],
            "provider": {"default": "missing"},
        },
        default_provider_id="default",
        default_provider=lambda: {"id": "default", "enabled": True},
        normalize_provider=lambda item: {"id": item["id"], "enabled": bool(item.get("enabled", True))},
    )
    assert changed is True
    assert [item["id"] for item in providers_cfg["providers"]] == ["relay-b", "relay-a"]
    assert providers_cfg["provider"] == {"default": "relay-b"}

    accounts_cfg, changed = mms_command_tools.ensure_account_config(
        {
            "accounts": [
                {"id": "codex-main", "cli": "codex"},
                {"id": "codex-main", "cli": "codex"},
                {"id": "gemini-old", "cli": "gemini"},
            ],
            "account": {"defaults": {"claude": "missing", "codex": "codex-main", "gemini": "gemini-old"}},
        },
        oauth_capable_clis=("claude", "codex", "gemini"),
        normalize_account=lambda item: dict(item),
    )
    assert changed is True
    assert [item["id"] for item in accounts_cfg["accounts"]] == ["codex-main", "gemini-old"]
    assert accounts_cfg["account"] == {"defaults": {"codex": "codex-main", "gemini": "gemini-old"}}


def test_handle_config_migrate_preserves_backup_save_and_report_flow():
    import mms_command_tools

    console = _CollectingConsole()
    saved = []

    mms_command_tools.handle_config_migrate(
        backup_config_tree=lambda reason: f"/backup/{reason}",
        load_config=lambda: None,
        migrate_accounts_dirs=lambda cfg: ([], False),
        save_config=lambda cfg: saved.append(cfg),
        config_path="/config.toml",
        active_credentials_path=lambda: "/credentials.sh",
        active_usage_path=lambda: "/usage.json",
        console=console,
    )
    assert saved == []
    assert any("未找到可迁移配置" in str(item) for item in console.items)

    console.items.clear()
    mms_command_tools.handle_config_migrate(
        backup_config_tree=lambda reason: f"/backup/{reason}",
        load_config=lambda: {"accounts": [{"id": "old"}], "provider": {"default": "relay"}},
        migrate_accounts_dirs=lambda cfg: ([{"id": "new"}], True),
        save_config=lambda cfg: saved.append(cfg),
        config_path="/config.toml",
        active_credentials_path=lambda: "/credentials.sh",
        active_usage_path=lambda: "/usage.json",
        console=console,
    )
    assert saved == [{"accounts": [{"id": "new"}], "provider": {"default": "relay"}}]
    assert console.items == [
        "[green]✓ 配置迁移完成[/green]",
        "[dim]config: /config.toml[/dim]",
        "[dim]credentials: /credentials.sh[/dim]",
        "[dim]usage: /usage.json[/dim]",
        "[dim]备份目录: /backup/config-migrate[/dim]",
    ]


def test_provider_default_handler_preserves_show_missing_and_save_refresh_flow():
    import mms_command_tools

    cfg = {"provider": {"default": "demo-a"}, "providers": [{"id": "demo-a"}, {"id": "demo-b"}]}
    console = _CollectingConsole()
    calls = []

    mms_command_tools.handle_provider_default_config(
        cfg,
        [],
        default_provider_id="default",
        provider_map=lambda current: {item["id"]: item for item in current["providers"]},
        save_config=lambda updated: calls.append(("save", updated["provider"]["default"])),
        refresh_routes_export_for_hive=lambda **kwargs: calls.append(("refresh", kwargs)),
        console=console,
    )
    assert "[cyan]provider.default[/cyan] = demo-a" in console.items
    assert calls == []

    console.items.clear()
    mms_command_tools.handle_provider_default_config(
        cfg,
        ["missing"],
        default_provider_id="default",
        provider_map=lambda current: {item["id"]: item for item in current["providers"]},
        save_config=lambda updated: calls.append(("save", updated["provider"]["default"])),
        refresh_routes_export_for_hive=lambda **kwargs: calls.append(("refresh", kwargs)),
        console=console,
    )
    assert any("未找到 provider: missing" in str(item) for item in console.items)
    assert calls == []

    console.items.clear()
    mms_command_tools.handle_provider_default_config(
        cfg,
        ["demo-b"],
        default_provider_id="default",
        provider_map=lambda current: {item["id"]: item for item in current["providers"]},
        save_config=lambda updated: calls.append(("save", updated["provider"]["default"])),
        refresh_routes_export_for_hive=lambda **kwargs: calls.append(("refresh", kwargs)),
        console=console,
    )
    assert cfg["provider"]["default"] == "demo-b"
    assert calls == [("save", "demo-b"), ("refresh", {"force": True, "quiet": False})]
    assert "[green]✓ provider.default = demo-b[/green]" in console.items


def test_provider_add_credentials_handlers_preserve_dispatch_and_validation():
    import mms_command_tools

    cfg = {
        "provider": {"default": "demo-a"},
        "providers": [
            {"id": "demo-a", "base_url": "https://a.example", "api_key": "key-a"},
            {"id": "demo-b", "base_url": "https://b.example", "api_key": "key-b"},
        ],
    }
    console = _CollectingConsole()
    connect_calls = []
    mms_command_tools.handle_provider_add_config(
        cfg,
        ["openrouter"],
        quick_connect_gateway=lambda current, preset_id=None: connect_calls.append((current, preset_id)),
    )
    assert connect_calls == [(cfg, "openrouter")]

    setup_calls = []
    provider_map = lambda current: {item["id"]: item for item in current.get("providers", [])}
    resolve_provider = lambda current, provider_id: provider_map(current)[provider_id]
    mms_command_tools.handle_provider_credentials_config(
        cfg,
        [],
        default_provider_id="fallback",
        provider_map=provider_map,
        resolve_provider_context=resolve_provider,
        setup_provider_credentials=lambda provider, base_url, api_key, allow_keep=False: setup_calls.append(
            (provider["id"], base_url, api_key, allow_keep)
        ),
        console=console,
    )
    assert setup_calls == [("demo-a", "https://a.example", "key-a", True)]

    console.items.clear()
    mms_command_tools.handle_provider_credentials_config(
        cfg,
        ["missing"],
        default_provider_id="fallback",
        provider_map=provider_map,
        resolve_provider_context=resolve_provider,
        setup_provider_credentials=lambda *_args, **_kwargs: setup_calls.append("unexpected"),
        console=console,
    )
    assert setup_calls == [("demo-a", "https://a.example", "key-a", True)]
    assert "[red]未找到模型源: missing[/red]" in console.items


def test_update_provider_model_overrides_preserves_patch_normalize_and_cache_invalidation():
    import mms_command_tools

    cfg = {
        "provider": {"default": "demo-a"},
        "providers": [
            {"id": "demo-a", "name": "Demo A", "extra_models": ["old-a"]},
            {"id": "demo-b", "name": "Demo B", "hidden_models": ["old-hidden"]},
        ],
    }
    saved = []
    invalidated = []
    normalized = []
    load_calls = []

    def normalize_provider(provider):
        normalized.append(dict(provider))
        return {**provider, "normalized": True}

    result = mms_command_tools.update_provider_model_overrides(
        cfg,
        "demo-b",
        extra_models="gpt-5.5, gpt-5.5, qwen3.6-plus",
        hidden_models=[" hidden ", "hidden", ""],
        models_endpoint="api/models",
        normalize_provider=normalize_provider,
        save_config=lambda updated: saved.append(updated),
        invalidate_probe_cache=lambda provider_id: invalidated.append(provider_id),
        load_config=lambda: load_calls.append("load") or {"loaded": True},
    )

    assert result == {"loaded": True}
    assert normalized == [
        {
            "id": "demo-b",
            "name": "Demo B",
            "hidden_models": ["hidden"],
            "extra_models": ["gpt-5.5", "qwen3.6-plus"],
            "models_endpoint": "/api/models",
        }
    ]
    assert saved == [
        {
            "provider": {"default": "demo-a"},
            "providers": [
                {"id": "demo-a", "name": "Demo A", "extra_models": ["old-a"]},
                {
                    "id": "demo-b",
                    "name": "Demo B",
                    "hidden_models": ["hidden"],
                    "extra_models": ["gpt-5.5", "qwen3.6-plus"],
                    "models_endpoint": "/api/models",
                    "normalized": True,
                },
            ],
        }
    ]
    assert invalidated == ["demo-b"]
    assert load_calls == ["load"]
    assert cfg["providers"][1] == {"id": "demo-b", "name": "Demo B", "hidden_models": ["old-hidden"]}

    saved.clear()
    invalidated.clear()
    normalized.clear()
    mms_command_tools.update_provider_model_overrides(
        cfg,
        "missing",
        extra_models=["new"],
        normalize_provider=normalize_provider,
        save_config=lambda updated: saved.append(updated),
        invalidate_probe_cache=lambda provider_id: invalidated.append(provider_id),
        load_config=lambda: {"loaded": "missing"},
    )
    assert saved == [{"provider": {"default": "demo-a"}, "providers": cfg["providers"]}]
    assert invalidated == ["missing"]
    assert normalized == []


def test_provider_edit_remove_handlers_preserve_validation_refresh_and_default_cleanup():
    import mms_command_tools

    cfg = {
        "provider": {"default": "demo-a"},
        "providers": [
            {"id": "demo-a", "name": "Demo A"},
            {"id": "demo-b", "name": "Demo B"},
        ],
    }
    console = _CollectingConsole()
    calls = []
    provider_map = lambda current: {item["id"]: item for item in current.get("providers", [])}

    edit_common = {
        "command_name": "mmg",
        "provider_map": provider_map,
        "prompt_provider_metadata": lambda existing=None, preset_id=None: {
            **existing,
            "name": f"Edited {preset_id}",
        },
        "upsert_provider": lambda current, provider: {
            **current,
            "providers": [
                provider if item.get("id") == provider.get("id") else item
                for item in current.get("providers", [])
            ],
        },
        "save_config": lambda updated: calls.append(("save", updated)),
        "invalidate_probe_cache": lambda provider_id: calls.append(("invalidate", provider_id)),
        "refresh_routes_export_for_hive": lambda **kwargs: calls.append(("refresh", kwargs)),
        "console": console,
    }

    mms_command_tools.handle_provider_edit_config(cfg, [], **edit_common)
    assert "[red]用法: mmg config provider.edit <id>[/red]" in console.items
    mms_command_tools.handle_provider_edit_config(cfg, ["missing"], **edit_common)
    assert any("未找到模型源: missing" in str(item) for item in console.items)
    assert calls == []

    console.items.clear()
    mms_command_tools.handle_provider_edit_config(cfg, ["demo-b"], **edit_common)
    assert calls[0][0] == "save"
    assert calls[0][1]["providers"][1]["name"] == "Edited demo-b"
    assert calls[1:] == [("invalidate", "demo-b"), ("refresh", {"force": True, "quiet": False})]
    assert "[green]✓ 已更新模型源: demo-b[/green]" in console.items

    console.items.clear()
    calls.clear()
    interactive_calls = []
    remove_common = {
        "command_name": "mmg",
        "default_provider_id": "default",
        "ensure_interactive_terminal": lambda reason: interactive_calls.append(reason),
        "provider_map": provider_map,
        "confirm_ask": lambda *args, **kwargs: True,
        "save_config": lambda updated: calls.append(("save", updated)),
        "delete_provider_credentials": lambda provider_id: calls.append(("delete-creds", provider_id)),
        "invalidate_probe_cache": lambda provider_id: calls.append(("invalidate", provider_id)),
        "refresh_routes_export_for_hive": lambda **kwargs: calls.append(("refresh", kwargs)),
        "console": console,
    }
    mms_command_tools.handle_provider_remove_config(cfg, ["demo-a"], **remove_common)
    assert interactive_calls == ["模型源删除确认"]
    assert calls[0] == ("save", {"provider": {"default": "demo-b"}, "providers": [{"id": "demo-b", "name": "Demo B"}]})
    assert calls[1:] == [
        ("delete-creds", "demo-a"),
        ("invalidate", "demo-a"),
        ("refresh", {"force": True, "quiet": False}),
    ]
    assert "[green]✓ 已删除模型源: demo-a[/green]" in console.items

    console.items.clear()
    calls.clear()
    mms_command_tools.handle_provider_remove_config(
        cfg,
        ["demo-b"],
        **{**remove_common, "confirm_ask": lambda *args, **kwargs: False},
    )
    assert calls == []
    assert "[yellow]已取消删除[/yellow]" in console.items

    console.items.clear()
    one_provider_cfg = {"providers": [{"id": "only"}]}
    mms_command_tools.handle_provider_remove_config(
        one_provider_cfg,
        ["only"],
        **remove_common,
    )
    assert any("无法删除最后一个" in str(item) for item in console.items)


def test_provider_upsert_and_credentials_cleanup_helpers_preserve_rewrite_rules(tmp_path):
    import mms_command_tools

    cfg = {"providers": [{"id": "demo-a", "name": "A"}], "provider": {"default": "demo-a"}}
    normalized_calls = []
    updated = mms_command_tools.upsert_provider(
        cfg,
        {"id": "demo-a", "name": "A2"},
        ensure_provider_config=lambda current: normalized_calls.append(current) or (current, True),
    )
    assert updated["providers"] == [{"id": "demo-a", "name": "A2"}]
    appended = mms_command_tools.upsert_provider(
        cfg,
        {"id": "demo-b", "name": "B"},
        ensure_provider_config=lambda current: (current, True),
    )
    assert appended["providers"] == [{"id": "demo-a", "name": "A"}, {"id": "demo-b", "name": "B"}]

    credentials = tmp_path / "credentials.sh"
    values = {
        "MMS_PROVIDER_DEMO_A_BASE_URL": "https://a.example",
        "MMS_PROVIDER_DEMO_A_API_KEY": "key-a",
        "MMS_PROVIDER_DEMO_B_API_KEY": "key-b",
        "MMS_API_BASE_URL": "https://default.example",
        "MMS_API_KEY": "default-key",
    }
    credentials.write_text("# old\n", encoding="utf-8")
    chmod_calls = []
    mms_command_tools.delete_provider_credentials(
        "demo-a",
        credentials_path=str(credentials),
        load_env_file=lambda path: dict(values),
        provider_env_name=lambda provider_id, suffix: f"MMS_PROVIDER_{provider_id.upper().replace('-', '_')}_{suffix}",
        default_provider_id="default",
        api_url_env_name="MMS_API_BASE_URL",
        api_key_env_name="MMS_API_KEY",
        shell_quote=lambda value: f"'{value}'",
        chmod=lambda path, mode: chmod_calls.append((path, mode)),
    )
    text = credentials.read_text(encoding="utf-8")
    assert "MMS_PROVIDER_DEMO_A_BASE_URL" not in text
    assert "MMS_PROVIDER_DEMO_A_API_KEY" not in text
    assert "MMS_PROVIDER_DEMO_B_API_KEY='key-b'" in text
    assert "MMS_API_KEY='default-key'" in text
    assert chmod_calls == [(str(credentials), 0o600)]

    chmod_calls.clear()
    mms_command_tools.delete_provider_credentials(
        "missing",
        credentials_path=str(credentials),
        load_env_file=lambda path: {"KEEP": "1"},
        provider_env_name=lambda provider_id, suffix: f"{provider_id}_{suffix}",
        default_provider_id="default",
        api_url_env_name="MMS_API_BASE_URL",
        api_key_env_name="MMS_API_KEY",
        shell_quote=lambda value: value,
        chmod=lambda path, mode: chmod_calls.append((path, mode)),
    )
    assert chmod_calls == []


def test_provider_rename_handler_preserves_backup_default_usage_and_cache_flow():
    import mms_command_tools

    cfg = {
        "provider": {"default": "demo-a"},
        "providers": [
            {"id": "demo-a", "name": "Demo A", "priority": 5},
            {"id": "demo-b", "name": "Demo B"},
        ],
    }
    console = _CollectingConsole()
    calls = []
    provider_map = lambda current: {item["id"]: item for item in current.get("providers", [])}
    common = {
        "command_name": "mmg",
        "normalize_provider_id_input": lambda value: value.lower().replace("_", "-"),
        "provider_map": provider_map,
        "normalize_provider": lambda provider: {**provider, "normalized": True},
        "backup_config_tree": lambda label: calls.append(("backup", label)) or "/tmp/backup",
        "save_config": lambda updated: calls.append(("save", updated)),
        "rename_usage_provider": lambda old_id, new_id, new_name: calls.append(("usage", old_id, new_id, new_name)),
        "invalidate_probe_cache": lambda provider_id: calls.append(("invalidate", provider_id)),
        "refresh_routes_export_for_hive": lambda **kwargs: calls.append(("refresh", kwargs)),
        "console": console,
    }

    mms_command_tools.handle_provider_rename_config(cfg, ["demo-a"], **common)
    assert "[red]用法: mmg config provider.rename <old_id> <new_id> [new_name][/red]" in console.items
    mms_command_tools.handle_provider_rename_config(cfg, ["missing", "new"], **common)
    assert any("未找到模型源: missing" in str(item) for item in console.items)
    mms_command_tools.handle_provider_rename_config(cfg, ["demo-a", "demo-a"], **common)
    assert "[yellow]名称和标识都未变化，无需重命名[/yellow]" in console.items
    mms_command_tools.handle_provider_rename_config(cfg, ["demo-a", "demo-b"], **common)
    assert "[red]目标模型源标识已存在: demo-b[/red]" in console.items
    assert calls == []

    console.items.clear()
    mms_command_tools.handle_provider_rename_config(cfg, ["demo-a", "Demo_New", "Demo New"], **common)
    assert calls[0] == ("backup", "provider-rename")
    assert calls[1][0] == "save"
    saved_cfg = calls[1][1]
    assert saved_cfg["provider"] == {"default": "demo-new"}
    assert saved_cfg["providers"][0] == {
        "id": "demo-new",
        "name": "Demo New",
        "priority": 5,
        "normalized": True,
    }
    assert calls[2:] == [
        ("usage", "demo-a", "demo-new", "Demo New"),
        ("invalidate", "demo-a"),
        ("invalidate", "demo-new"),
        ("refresh", {"force": True, "quiet": False}),
    ]
    assert "[green]✓ 已重命名模型源: demo-a -> demo-new[/green]" in console.items
    assert "[dim]显示名: Demo New[/dim]" in console.items
    assert "[dim]备份目录: /tmp/backup[/dim]" in console.items


def test_account_default_handler_preserves_show_reject_and_save_flow():
    import mms_command_tools

    cfg = {
        "account": {"defaults": {"codex": "codex-main"}},
        "accounts": [
            {"id": "codex-main", "cli": "codex"},
            {"id": "gemini-main", "cli": "gemini"},
        ],
    }
    console = _CollectingConsole()
    saves = []
    kwargs = {
        "managed_oauth_clis": ["claude", "codex", "gemini"],
        "delegated_oauth_clis": {"claude"},
        "account_map": lambda current: {item["id"]: item for item in current["accounts"]},
        "save_config": lambda updated: saves.append(dict(updated.get("account", {}).get("defaults", {}))),
        "command_name": "mmg",
        "console": console,
    }

    mms_command_tools.handle_account_default_config(cfg, [], **kwargs)
    assert "[cyan]account.default.codex[/cyan] = codex-main" in console.items
    assert any("Claude OAuth 独立入口已下线" in str(item) for item in console.items)

    console.items.clear()
    mms_command_tools.handle_account_default_config(cfg, ["codex"], **kwargs)
    assert "[red]用法: mmg config account.default <cli> <account_id>[/red]" in console.items
    mms_command_tools.handle_account_default_config(cfg, ["claude", "claude-main"], **kwargs)
    assert any("不再支持设置 account.default.claude" in str(item) for item in console.items)
    mms_command_tools.handle_account_default_config(cfg, ["opencode", "main"], **kwargs)
    assert any("不支持的 CLI: opencode" in str(item) for item in console.items)
    mms_command_tools.handle_account_default_config(cfg, ["codex", "missing"], **kwargs)
    assert any("未找到账号档案: missing" in str(item) for item in console.items)
    mms_command_tools.handle_account_default_config(cfg, ["codex", "gemini-main"], **kwargs)
    assert any("绑定的是 gemini" in str(item) for item in console.items)
    assert saves == []

    console.items.clear()
    mms_command_tools.handle_account_default_config(cfg, ["gemini", "gemini-main"], **kwargs)
    assert cfg["account"]["defaults"]["gemini"] == "gemini-main"
    assert saves == [{"codex": "codex-main", "gemini": "gemini-main"}]
    assert "[green]✓ account.default.gemini = gemini-main[/green]" in console.items


def test_account_add_status_login_handlers_preserve_guards_and_dispatch():
    import mms_command_tools

    console = _CollectingConsole()
    connect_calls = []
    mms_command_tools.handle_account_add_config(
        {"cfg": True},
        ["claude"],
        managed_oauth_clis={"claude", "codex", "agy"},
        delegated_oauth_clis={"claude"},
        quick_connect_official=lambda cfg, preset_cli=None: connect_calls.append((cfg, preset_cli)),
        console=console,
    )
    assert connect_calls == []
    assert any("不再管理 Claude 官方登录" in str(item) for item in console.items)
    mms_command_tools.handle_account_add_config(
        {"cfg": True},
        ["agy"],
        managed_oauth_clis={"claude", "codex", "agy"},
        delegated_oauth_clis={"claude"},
        quick_connect_official=lambda cfg, preset_cli=None: connect_calls.append((cfg, preset_cli)),
        console=console,
    )
    assert connect_calls == [({"cfg": True}, "agy")]

    display_calls = []
    console.items.clear()
    mms_command_tools.handle_account_status_config(
        {"cfg": True},
        [],
        resolve_account_context=lambda *_args, **_kwargs: None,
        probe_account_status=lambda _account: {},
        display_accounts=lambda cfg: display_calls.append(cfg),
        console=console,
    )
    assert display_calls == [{"cfg": True}]
    mms_command_tools.handle_account_status_config(
        {"cfg": True},
        ["codex-main"],
        resolve_account_context=lambda cfg, account_id: {"id": account_id, "cli": "codex"},
        probe_account_status=lambda account: {"state": "ok", "summary": f"{account['cli']}:ready"},
        display_accounts=lambda cfg: display_calls.append(cfg),
        console=console,
    )
    assert "[cyan]codex-main[/cyan] = ok" in console.items
    assert "[dim]codex:ready[/dim]" in console.items

    login_calls = []
    console.items.clear()
    mms_command_tools.handle_account_login_config(
        {},
        [],
        command_name="mmg",
        delegated_oauth_clis={"claude"},
        resolve_account_context=lambda *_args, **_kwargs: None,
        run_account_login=lambda account: login_calls.append(account),
        console=console,
    )
    assert "[red]用法: mmg config account.login <id>[/red]" in console.items
    mms_command_tools.handle_account_login_config(
        {},
        ["claude-main"],
        command_name="mmg",
        delegated_oauth_clis={"claude"},
        resolve_account_context=lambda *_args, **_kwargs: {"id": "claude-main", "cli": "claude"},
        run_account_login=lambda account: login_calls.append(account),
        console=console,
    )
    assert login_calls == []
    assert any("请使用 provider/API route 启动 Claude" in str(item) for item in console.items)
    mms_command_tools.handle_account_login_config(
        {},
        ["codex-main"],
        command_name="mmg",
        delegated_oauth_clis={"claude"},
        resolve_account_context=lambda *_args, **_kwargs: {"id": "codex-main", "cli": "codex"},
        run_account_login=lambda account: login_calls.append(account),
        console=console,
    )
    assert login_calls == [{"id": "codex-main", "cli": "codex"}]


def test_account_env_helpers_preserve_scrub_seed_proxy_and_home_behavior():
    import mms_command_tools

    base_env = {
        "KEEP": "1",
        "ANTHROPIC_AUTH_TOKEN": "secret",
        "CLAUDE_CODE_TOKEN": "secret",
        "OPENAI_API_KEY": "secret",
        "HTTP_PROXY": "ambient",
        "NO_PROXY": "ambient",
        "MMS_FAKE_UPSTREAM_MODE": "1",
        "SSL_CERT_FILE": "/tmp/ca.pem",
    }
    scrubbed = mms_command_tools.scrub_account_command_env(
        dict(base_env),
        prefix_blocklist=("ANTHROPIC_", "CLAUDE_CODE_", "OPENAI_"),
        proxy_env_keys=("HTTP_PROXY", "NO_PROXY"),
        fake_env_keys=("MMS_FAKE_UPSTREAM_MODE",),
        ca_env_keys=("SSL_CERT_FILE",),
    )
    assert scrubbed == {"KEEP": "1"}

    seeds = []
    env = mms_command_tools.account_env(
        {
            "id": "codex-main",
            "cli": "codex",
            "home_dir": "~/codex",
            "proxy": "http://proxy",
            "no_proxy": "localhost",
            "timezone": "Asia/Singapore",
        },
        environ=base_env,
        expanduser=lambda path: path.replace("~", "/home/xin"),
        scrub_account_command_env=lambda value: mms_command_tools.scrub_account_command_env(
            value,
            prefix_blocklist=("ANTHROPIC_", "CLAUDE_CODE_", "OPENAI_"),
            proxy_env_keys=("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"),
            fake_env_keys=("MMS_FAKE_UPSTREAM_MODE",),
            ca_env_keys=("SSL_CERT_FILE",),
        ),
        seed_claude_state=lambda home: seeds.append(("claude", home)),
        seed_agy_state=lambda home: seeds.append(("agy", home)),
        seed_gemini_state=lambda home: seeds.append(("gemini", home)),
    )
    assert seeds == []
    assert env["KEEP"] == "1"
    assert env["HOME"] == "/home/xin/codex"
    assert env["XDG_CONFIG_HOME"] == "/home/xin/codex/.config"
    assert env["HTTP_PROXY"] == "http://proxy"
    assert env["HTTPS_PROXY"] == "http://proxy"
    assert env["NO_PROXY"] == "localhost"
    assert env["TZ"] == "Asia/Singapore"
    assert env["MMS_ACCOUNT_ID"] == "codex-main"
    assert "OPENAI_API_KEY" not in env
    assert base_env["HTTP_PROXY"] == "ambient"

    gemini_env = mms_command_tools.account_env(
        {"id": "gemini-main", "cli": "gemini", "home_dir": "/tmp/gemini"},
        environ={},
        scrub_account_command_env=lambda value: value,
        seed_claude_state=lambda home: seeds.append(("claude", home)),
        seed_agy_state=lambda home: seeds.append(("agy", home)),
        seed_gemini_state=lambda home: seeds.append(("gemini", home)),
    )
    assert gemini_env["GEMINI_CLI_HOME"] == "/tmp/gemini"
    assert "HOME" not in gemini_env
    assert seeds[-1] == ("gemini", "/tmp/gemini")

    claude_env = mms_command_tools.account_env(
        {"id": "claude-main", "cli": "claude", "home_dir": "/tmp/claude"},
        environ={},
        scrub_account_command_env=lambda value: value,
        seed_claude_state=lambda home: seeds.append(("claude", home)),
        seed_agy_state=lambda home: seeds.append(("agy", home)),
        seed_gemini_state=lambda home: seeds.append(("gemini", home)),
    )
    assert claude_env["HOME"] == "/tmp/claude"
    assert seeds[-1] == ("claude", "/tmp/claude")
    assert mms_command_tools.account_label({"id": "codex-main", "name": "Codex Main"}) == "Codex Main"
    assert mms_command_tools.account_label({"id": "codex-main"}) == "codex-main"


def test_account_status_probe_helper_preserves_delegated_manual_and_cli_states():
    import subprocess
    from types import SimpleNamespace

    import mms_command_tools

    assert mms_command_tools.account_status_command("codex") == ["codex", "login", "status"]
    assert mms_command_tools.account_status_command("gemini") is None

    assert mms_command_tools.probe_account_status(
        {"cli": "claude"},
        account_env=lambda account: {},
    ) == {
        "state": "delegated",
        "summary": "Claude OAuth 独立入口已下线；MMS 不再探测或登录这个账号",
    }

    existing = {"/home/demo/.gemini/oauth_creds.json", "/home/agy/.gemini/antigravity-cli"}
    assert mms_command_tools.probe_account_status(
        {"cli": "gemini", "home_dir": "~/demo"},
        account_env=lambda account: {},
        expanduser=lambda path: path.replace("~", "/home"),
        path_exists=lambda path: path in existing,
    ) == {"state": "configured", "summary": "已配置 OAuth，建议直接启动 Gemini 验证"}
    assert mms_command_tools.probe_account_status(
        {"cli": "agy", "home_dir": "/home/agy"},
        account_env=lambda account: {},
        path_exists=lambda path: False,
        path_isdir=lambda path: path in existing,
    ) == {"state": "manual", "summary": "已初始化，登录状态需启动 agy 验证"}

    run_calls = []

    def run_ok(command, **kwargs):
        run_calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="logged in\nextra", stderr="")

    assert mms_command_tools.probe_account_status(
        {"cli": "codex", "home_dir": "/tmp/codex"},
        account_env=lambda account: {"HOME": account["home_dir"]},
        run_command=run_ok,
    ) == {"state": "logged_in", "summary": "logged in"}
    assert run_calls == [
        (
            ["codex", "login", "status"],
            {
                "env": {"HOME": "/tmp/codex"},
                "capture_output": True,
                "text": True,
                "timeout": 5,
            },
        )
    ]

    assert mms_command_tools.probe_account_status(
        {"cli": "unknown"},
        account_env=lambda account: {},
        account_status_command=lambda cli: None,
    ) == {"state": "unsupported", "summary": "不支持状态探测"}
    assert mms_command_tools.probe_account_status(
        {"cli": "codex"},
        account_env=lambda account: {},
        run_command=lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    ) == {"state": "cli_missing", "summary": "codex 未安装"}
    assert mms_command_tools.probe_account_status(
        {"cli": "codex"},
        account_env=lambda account: {},
        run_command=lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("codex", 5)),
    ) == {"state": "timeout", "summary": "状态探测超时"}


def test_account_login_runner_preserves_command_messages_and_exit_handling():
    import pytest
    from types import SimpleNamespace

    import mms_command_tools

    console = _CollectingConsole()
    calls = []
    mms_command_tools.run_account_login(
        {"id": "claude-main", "cli": "claude", "home_dir": "/tmp/claude"},
        account_env=lambda account: calls.append(("unexpected-env", account)) or {},
        account_label=lambda account: account["id"],
        makedirs=lambda *args, **kwargs: calls.append(("unexpected-makedirs", args, kwargs)),
        run_command=lambda *args, **kwargs: calls.append(("unexpected-run", args, kwargs)),
        console=console,
    )
    assert calls == []
    assert any("Claude OAuth 独立入口已下线" in str(item) for item in console.items)

    console.items.clear()
    mms_command_tools.run_account_login(
        {"id": "codex-main", "name": "Codex Main", "cli": "codex", "home_dir": "/tmp/codex"},
        account_env=lambda account: {"HOME": account["home_dir"]},
        account_label=lambda account: account.get("name", account["id"]),
        makedirs=lambda path, exist_ok=False: calls.append(("makedirs", path, exist_ok)),
        run_command=lambda command, env=None: calls.append(("run", command, env)) or SimpleNamespace(returncode=0),
        console=console,
    )
    assert calls[-2:] == [
        ("makedirs", "/tmp/codex", True),
        ("run", ["codex", "login"], {"HOME": "/tmp/codex"}),
    ]
    assert any("Codex Main" in str(item) and "HOME=/tmp/codex" in str(item) for item in console.items)

    console.items.clear()
    mms_command_tools.run_account_login(
        {"id": "gemini-main", "cli": "gemini", "home_dir": "/tmp/gemini"},
        account_env=lambda account: {"GEMINI_CLI_HOME": account["home_dir"]},
        account_label=lambda account: account["id"],
        makedirs=lambda *args, **kwargs: None,
        run_command=lambda command, env=None: calls.append(("run-gemini", command, env)) or SimpleNamespace(returncode=0),
        console=console,
    )
    assert calls[-1] == ("run-gemini", ["gemini"], {"GEMINI_CLI_HOME": "/tmp/gemini"})
    assert any("GEMINI_CLI_HOME=/tmp/gemini" in str(item) for item in console.items)

    with pytest.raises(SystemExit) as exc:
        mms_command_tools.run_account_login(
            {"id": "bad", "cli": "unknown", "home_dir": "/tmp/bad"},
            account_env=lambda account: {},
            account_label=lambda account: account["id"],
            makedirs=lambda *args, **kwargs: None,
            run_command=lambda *args, **kwargs: SimpleNamespace(returncode=0),
            console=console,
        )
    assert exc.value.code == 1
    assert any("不支持的官方账号类型: unknown" in str(item) for item in console.items)

    with pytest.raises(SystemExit) as exc:
        mms_command_tools.run_account_login(
            {"id": "codex-main", "cli": "codex", "home_dir": "/tmp/codex"},
            account_env=lambda account: {},
            account_label=lambda account: account["id"],
            makedirs=lambda *args, **kwargs: None,
            run_command=lambda *args, **kwargs: SimpleNamespace(returncode=7),
            console=console,
        )
    assert exc.value.code == 7


def test_account_edit_remove_handlers_preserve_validation_and_defaults_cleanup():
    import mms_command_tools

    cfg = {
        "accounts": [
            {"id": "codex-main", "cli": "codex", "name": "Codex"},
            {"id": "claude-main", "cli": "claude", "name": "Claude"},
        ],
        "account": {"defaults": {"codex": "codex-main", "claude": "claude-main"}},
    }
    console = _CollectingConsole()
    saved = []

    common = {
        "command_name": "mmg",
        "account_map": lambda current: {item["id"]: item for item in current.get("accounts", [])},
        "delegated_oauth_clis": {"claude"},
        "prompt_account_metadata": lambda existing=None, preset_id=None: {
            **existing,
            "name": f"Edited {preset_id}",
        },
        "ensure_account_config": lambda current: (current, True),
        "save_config": lambda updated: saved.append(updated),
        "console": console,
    }

    mms_command_tools.handle_account_edit_config(cfg, [], **common)
    assert "[red]用法: mmg config account.edit <id>[/red]" in console.items
    mms_command_tools.handle_account_edit_config(cfg, ["missing"], **common)
    assert any("未找到账号档案: missing" in str(item) for item in console.items)
    mms_command_tools.handle_account_edit_config(cfg, ["claude-main"], **common)
    assert any("不再编辑 Claude 官方账号" in str(item) for item in console.items)
    assert saved == []

    console.items.clear()
    mms_command_tools.handle_account_edit_config(cfg, ["codex-main"], **common)
    assert saved[-1]["accounts"][0]["name"] == "Edited codex-main"
    assert "[green]✓ 已更新账号档案: codex-main[/green]" in console.items

    console.items.clear()
    interactive_calls = []
    mms_command_tools.handle_account_remove_config(
        cfg,
        ["codex-main"],
        command_name="mmg",
        ensure_interactive_terminal=lambda reason: interactive_calls.append(reason),
        account_map=lambda current: {item["id"]: item for item in current.get("accounts", [])},
        confirm_ask=lambda *args, **kwargs: True,
        ensure_account_config=lambda current: (current, True),
        save_config=lambda updated: saved.append(updated),
        console=console,
    )
    assert interactive_calls == ["账号档案删除确认"]
    assert saved[-1]["accounts"] == [{"id": "claude-main", "cli": "claude", "name": "Claude"}]
    assert saved[-1]["account"] == {"defaults": {"claude": "claude-main"}}
    assert "[green]✓ 已删除账号档案: codex-main[/green]" in console.items

    console.items.clear()
    mms_command_tools.handle_account_remove_config(
        cfg,
        ["codex-main"],
        command_name="mmg",
        ensure_interactive_terminal=lambda reason: None,
        account_map=lambda current: {item["id"]: item for item in current.get("accounts", [])},
        confirm_ask=lambda *args, **kwargs: False,
        ensure_account_config=lambda current: (current, True),
        save_config=lambda updated: saved.append(updated),
        console=console,
    )
    assert "[yellow]已取消删除[/yellow]" in console.items


def test_account_rename_handler_preserves_backup_move_defaults_and_usage_flow():
    import mms_command_tools

    cfg = {
        "accounts": [
            {"id": "codex-main", "cli": "codex", "name": "Codex", "home_dir": "/old/codex-main"},
            {"id": "gemini-main", "cli": "gemini", "name": "Gemini", "home_dir": "/old/gemini-main"},
        ],
        "account": {"defaults": {"codex": "codex-main", "gemini": "gemini-main"}},
    }
    console = _CollectingConsole()
    calls = []
    accounts = lambda current: {item["id"]: item for item in current.get("accounts", [])}
    common = {
        "command_name": "mmg",
        "normalize_account_id": lambda value: value.lower().replace("_", "-"),
        "account_map": accounts,
        "backup_config_tree": lambda label: calls.append(("backup", label)) or "/tmp/backup",
        "target_account_home": lambda old_home, new_id: f"/new/{new_id}",
        "path_exists": lambda path: path == "/old/codex-main",
        "makedirs": lambda path, exist_ok=False: calls.append(("makedirs", path, exist_ok)),
        "move": lambda old, new: calls.append(("move", old, new)),
        "normalize_account": lambda account: {**account, "normalized": True},
        "ensure_account_config": lambda current: (current, True),
        "save_config": lambda updated: calls.append(("save", updated)),
        "rename_usage_account": lambda old_id, new_id, new_name, cli_name: calls.append(
            ("usage", old_id, new_id, new_name, cli_name)
        ),
        "console": console,
    }

    mms_command_tools.handle_account_rename_config(cfg, ["codex-main"], **common)
    assert "[red]用法: mmg config account.rename <old_id> <new_id>[/red]" in console.items
    mms_command_tools.handle_account_rename_config(cfg, ["missing", "new"], **common)
    assert any("未找到账号档案: missing" in str(item) for item in console.items)
    mms_command_tools.handle_account_rename_config(cfg, ["codex-main", "codex-main"], **common)
    assert "[yellow]新旧文件夹名相同，无需重命名[/yellow]" in console.items
    mms_command_tools.handle_account_rename_config(cfg, ["codex-main", "gemini-main"], **common)
    assert "[red]目标文件夹名已存在: gemini-main[/red]" in console.items
    assert calls == []

    console.items.clear()
    mms_command_tools.handle_account_rename_config(cfg, ["codex-main", "Codex_New"], **common)
    assert calls[0] == ("backup", "account-rename")
    assert calls[1] == ("makedirs", "/new", True)
    assert calls[2] == ("move", "/old/codex-main", "/new/codex-new")
    assert calls[3][0] == "save"
    saved_cfg = calls[3][1]
    assert saved_cfg["account"] == {"defaults": {"codex": "codex-new", "gemini": "gemini-main"}}
    assert saved_cfg["accounts"][0] == {
        "id": "codex-new",
        "cli": "codex",
        "name": "codex-new",
        "home_dir": "/new/codex-new",
        "normalized": True,
    }
    assert calls[4] == ("usage", "codex-main", "codex-new", "codex-new", "codex")
    assert "[green]✓ 已重命名账号档案: codex-main -> codex-new[/green]" in console.items
    assert "[dim]新目录: /new/codex-new[/dim]" in console.items
    assert "[dim]备份目录: /tmp/backup[/dim]" in console.items

    console.items.clear()
    calls.clear()
    mms_command_tools.handle_account_rename_config(
        cfg,
        ["codex-main", "codex-new"],
        **{**common, "path_exists": lambda path: path == "/new/codex-new"},
    )
    assert calls == [("backup", "account-rename")]
    assert "[red]目标目录已存在: /new/codex-new[/red]" in console.items


def test_config_normalization_helpers_preserve_legacy_shapes():
    import mms_command_tools
    import mms_core

    preset = mms_command_tools.normalize_preset_entry(
        "demo",
        {
            "cli": " Codex ",
            "account": " Main Account! ",
            "sonnet": "claude-sonnet-4.5",
            "temperature": 0.2,
        },
    )
    assert preset == {
        "cli": "codex",
        "account": "main-account",
        "model": "claude-sonnet-4.5",
        "temperature": 0.2,
    }
    assert mms_command_tools.normalize_preset_entry("legacy", "gpt-5.5") == {"cli": "claude", "model": "gpt-5.5"}

    cfg, changed = mms_command_tools.normalize_presets_config(
        {"presets": {" demo ": "gpt-5.5", "": {"cli": "claude"}}}
    )
    assert changed is True
    assert cfg["presets"] == {"demo": {"cli": "claude", "model": "gpt-5.5"}}

    user_cfg, changed = mms_command_tools.normalize_user_config(
        {"user": {"role": "dev", "note": "keep"}},
        mode_all="all",
        normalize_user_role=lambda value: "recommended" if value == "recommended" else "all",
    )
    assert changed is True
    assert user_cfg["user"] == {"role": "all", "note": "keep"}

    cache_cfg, changed = mms_command_tools.normalize_cache_config(
        {"cache": {"probe_async_refresh_after_sec": "0", "probe_async_min_interval_sec": "bad", "extra": "drop"}},
        probe_async_refresh_after=1800,
        probe_async_min_interval=300,
    )
    assert changed is True
    assert cache_cfg["cache"] == {
        "probe_async_refresh_after_sec": 1,
        "probe_async_min_interval_sec": 300,
    }

    wrapped_cache_cfg, changed = mms_core._normalize_cache_config({"cache": {}})
    assert changed is True
    assert wrapped_cache_cfg["cache"]["probe_async_refresh_after_sec"] > 0


def test_snapshot_diff_lines_reports_guard_drift_without_ignored_files():
    import mms_command_tools

    previous = {
        "defaults": {"provider_default": "relay-a"},
        "accounts": [
            {
                "id": "claude-main",
                "proxy_sha256": "old-proxy",
                "proxy_fingerprint": "old proxy",
                "identity_sha256": "old-identity",
                "identity_fingerprint": "old identity",
            }
        ],
        "providers": [{"id": "relay", "priority": 100}],
        "files": [
            {"path": "/tmp/config.toml", "exists": True, "sha256": "old"},
            {"path": "/tmp/.claude.json", "exists": True, "sha256": "old-runtime"},
            {"path": "/tmp/ignored", "exists": True, "sha256": "old"},
        ],
    }
    current = {
        "defaults": {"provider_default": "relay-b"},
        "accounts": [
            {
                "id": "claude-main",
                "proxy_sha256": "new-proxy",
                "proxy_fingerprint": "new proxy",
                "identity_sha256": "new-identity",
                "identity_fingerprint": "new identity",
            }
        ],
        "providers": [{"id": "relay", "priority": 200}],
        "files": [
            {"path": "/tmp/config.toml", "exists": True, "sha256": "new"},
            {"path": "/tmp/.claude.json", "exists": True, "sha256": "new-runtime"},
            {"path": "/tmp/ignored", "exists": True, "sha256": "new"},
        ],
    }

    diffs = mms_command_tools.snapshot_diff_lines(
        previous,
        current,
        is_snapshot_ignored_file=lambda path: str(path).endswith("/ignored"),
    )

    assert "default route/account changed" in diffs
    assert "account claude-main proxy: old proxy -> new proxy" in diffs
    assert "account claude-main identity: old identity -> new identity" in diffs
    assert "provider relay priority: 100 -> 200" in diffs
    assert "file changed: /tmp/config.toml" in diffs
    assert not any(".claude.json" in item or "ignored" in item for item in diffs)


def test_config_validator_reports_provider_account_errors():
    import mms_command_tools
    import mms_core

    kwargs = {
        "default_provider_protocols": {"openai", "anthropic"},
        "cli_names": ["claude", "codex"],
        "legacy_provider_cli_aliases": {"legacy"},
        "default_priority": 100,
        "oauth_capable_clis": {"codex", "agy"},
        "mode_all": "all",
        "mode_recommended": "recommended",
        "canonical_model_family": lambda name: {"GPT": "GPT"}.get(name),
        "normalize_priority": lambda value: value if isinstance(value, int) and value > 0 else 100,
        "normalize_claude_1m_mode": lambda value: value if value in {"auto", "enable", "disable"} else "auto",
        "normalize_user_role": lambda value: value if value in {"all", "recommended"} else "all",
    }
    cfg = {
        "cache": {"probe_async_refresh_after_sec": 0},
        "provider": {"default": "missing"},
        "providers": [
            {
                "id": "relay",
                "protocols": ["bad"],
                "supported_clis": ["badcli"],
                "priority": -1,
                "family_priority_overrides": {"Bad": 1},
                "claude_1m_mode": "bad",
            },
            {"id": "relay"},
        ],
        "accounts": [
            {
                "id": "acct",
                "cli": "claude",
                "auth_mode": "api_key",
                "priority": 0,
                "claude_1m_mode": "bad",
            },
            {"id": "acct", "cli": "codex", "home_dir": "/tmp/a"},
        ],
        "account": {"defaults": {"badcli": "acct", "codex": "missing"}},
    }

    errors = mms_command_tools.validate_config(cfg, **kwargs)
    assert "probe_async_refresh_after_sec 必须是正整数" in errors
    assert "模型源 ID 重复: relay" in errors
    assert "模型源 relay 存在不支持的协议: bad" in errors
    assert "模型源 relay 存在不支持的 CLI: badcli" in errors
    assert "默认模型源不存在: missing" in errors
    assert "账号档案 acct 绑定了不支持的 CLI: claude" in errors
    assert "账号档案 acct 目前只支持 oauth 模式" in errors
    assert "账号档案 acct 缺少 home_dir" in errors
    assert "存在不支持的默认账号 CLI: badcli" in errors
    assert "codex 的默认账号不存在: missing" in errors

    valid_cfg = {
        "provider": {"default": "relay"},
        "providers": [{"id": "relay", "protocols": ["openai"], "supported_clis": ["codex"], "priority": 100}],
        "accounts": [{"id": "codex-a", "cli": "codex", "auth_mode": "oauth", "home_dir": "/tmp/codex-a"}],
        "account": {"defaults": {"codex": "codex-a"}},
        "user": {"role": "all"},
    }
    assert mms_command_tools.validate_config(valid_cfg, **kwargs) == []
    assert mms_core._validate_config({"provider": {"default": "relay"}, "providers": [{"id": "relay"}]}) == []


def test_config_get_set_unset_handlers_use_injected_save():
    import mms_command_tools

    console = _CollectingConsole()
    saved = []
    cfg = {"provider": {"default": "relay"}, "secret": {"api_key": "abcd1234efgh"}}

    mms_command_tools.handle_config_get(cfg, ["secret.api_key"], command_name="mmg", console=console)
    assert any("abcd****efgh" in str(item) for item in console.items)

    mms_command_tools.handle_config_set(
        cfg,
        ["cache.probe_async_min_interval_sec", "0"],
        command_name="mmg",
        coerce_config_value=lambda key, value: 1 if key == "cache.probe_async_min_interval_sec" else value,
        normalize_config_sections=lambda current: current,
        save_config=lambda current: saved.append(("set", current)),
        console=console,
    )
    assert saved[-1][0] == "set"
    assert saved[-1][1]["cache"]["probe_async_min_interval_sec"] == 1
    assert any("cache.probe_async_min_interval_sec = 1" in str(item) for item in console.items)

    mms_command_tools.handle_config_unset(
        saved[-1][1],
        ["cache.probe_async_min_interval_sec"],
        command_name="mmg",
        normalize_config_sections=lambda current: current,
        save_config=lambda current: saved.append(("unset", current)),
        console=console,
    )
    assert saved[-1][0] == "unset"
    assert "probe_async_min_interval_sec" not in saved[-1][1]["cache"]
    assert any("已移除 cache.probe_async_min_interval_sec" in str(item) for item in console.items)

    console.items.clear()
    mms_command_tools.handle_config_unset(
        cfg,
        ["missing.path"],
        command_name="mmg",
        normalize_config_sections=lambda current: current,
        save_config=lambda current: saved.append(("unexpected", current)),
        console=console,
    )
    assert saved[-1][0] == "unset"
    assert any("配置项 'missing.path' 不存在" in str(item) for item in console.items)


def test_config_validate_handler_prints_success_and_failure():
    import pytest
    import mms_command_tools

    console = _CollectingConsole()

    mms_command_tools.handle_config_validate({}, validate_config=lambda cfg: [], console=console)
    assert any("配置校验通过" in str(item) for item in console.items)

    console.items.clear()
    with pytest.raises(SystemExit) as exc:
        mms_command_tools.handle_config_validate({}, validate_config=lambda cfg: ["bad provider"], console=console)
    assert exc.value.code == 1
    assert any("配置校验失败" in str(item) for item in console.items)
    assert any("bad provider" in str(item) for item in console.items)


def test_api_and_config_file_handlers_preserve_masking_and_save_flow():
    import mms_command_tools

    console = _CollectingConsole()
    saved = []
    load_credentials = lambda: ("https://api.example/v1", "abcd1234efgh", "extra")

    mms_command_tools.handle_config_file(config_path="/tmp/config.toml", console=console)
    assert "/tmp/config.toml" in console.items

    console.items.clear()
    mms_command_tools.handle_api_config(
        "api.base_url",
        [],
        load_api_credentials=load_credentials,
        save_api_credentials=lambda base_url, api_key: saved.append((base_url, api_key)),
        credentials_path="/tmp/credentials.sh",
        mask_key=mms_command_tools.mask_key,
        console=console,
    )
    assert "[cyan]api.base_url[/cyan] = https://api.example/v1" in console.items
    assert saved == []

    console.items.clear()
    mms_command_tools.handle_api_config(
        "api.base_url",
        ["https://new.example/v1/"],
        load_api_credentials=load_credentials,
        save_api_credentials=lambda base_url, api_key: saved.append((base_url, api_key)),
        credentials_path="/tmp/credentials.sh",
        mask_key=mms_command_tools.mask_key,
        console=console,
    )
    assert saved == [("https://new.example/v1", "abcd1234efgh")]
    assert "[green]✓ api.base_url = https://new.example/v1[/green]" in console.items

    console.items.clear()
    mms_command_tools.handle_api_config(
        "api.api_key",
        [],
        load_api_credentials=load_credentials,
        save_api_credentials=lambda base_url, api_key: saved.append((base_url, api_key)),
        credentials_path="/tmp/credentials.sh",
        mask_key=mms_command_tools.mask_key,
        console=console,
    )
    assert "[cyan]api.api_key[/cyan] = abcd****efgh" in console.items
    assert any("/tmp/credentials.sh" in str(item) for item in console.items)

    console.items.clear()
    mms_command_tools.handle_api_config(
        "api.api_key",
        ["new-secret-key"],
        load_api_credentials=load_credentials,
        save_api_credentials=lambda base_url, api_key: saved.append((base_url, api_key)),
        credentials_path="/tmp/credentials.sh",
        mask_key=mms_command_tools.mask_key,
        console=console,
    )
    assert saved[-1] == ("https://api.example/v1", "new-secret-key")
    assert "[green]✓ api.api_key = new-****-key[/green]" in console.items

    console.items.clear()
    mms_command_tools.handle_api_config(
        "api.missing",
        [],
        load_api_credentials=load_credentials,
        save_api_credentials=lambda base_url, api_key: saved.append(("unexpected", base_url, api_key)),
        credentials_path="/tmp/credentials.sh",
        mask_key=mms_command_tools.mask_key,
        console=console,
    )
    assert "[red]配置项 'api.missing' 不存在[/red]" in console.items


def test_handle_config_dispatch_preserves_command_routing_and_api_setup():
    import pytest
    import mms_command_tools

    cfg = {"cfg": True}
    console = _CollectingConsole()
    calls = []

    def mark(name):
        def _inner(*args, **kwargs):
            calls.append((name, args, kwargs))
        return _inner

    kwargs = {
        "preferences_doc_path": "/tmp/preferences.md",
        "preference_paths": ["/tmp/preferences.toml"],
        "display_config": mark("display-config"),
        "display_config_help": mark("display-help"),
        "handle_config_migrate": mark("migrate"),
        "handle_config_file": mark("file"),
        "handle_config_validate": mark("validate"),
        "display_preferences_help": mark("preferences-help"),
        "display_preferences_path": mark("preferences-path"),
        "display_preferences_example": mark("preferences-example"),
        "run_config_web": lambda *args, **kwargs: calls.append(("web", args, kwargs)) or 23,
        "command_name": "mmg",
        "config_write_target_path": lambda: "/tmp/config.toml",
        "display_human_gate_help": mark("human-gate"),
        "handle_config_get": mark("get"),
        "handle_config_set": mark("set"),
        "handle_config_unset": mark("unset"),
        "run_connect_wizard": mark("connect"),
        "handle_openrouter_extension_config": mark("openrouter"),
        "display_adapter_registry": mark("adapter-registry"),
        "display_providers": mark("provider-list"),
        "handle_provider_default_config": mark("provider-default"),
        "handle_provider_add_config": mark("provider-add"),
        "handle_provider_edit_config": mark("provider-edit"),
        "handle_provider_rename_config": mark("provider-rename"),
        "handle_provider_remove_config": mark("provider-remove"),
        "handle_provider_credentials_config": mark("provider-credentials"),
        "display_accounts": mark("account-list"),
        "handle_account_default_config": mark("account-default"),
        "handle_account_add_config": mark("account-add"),
        "handle_account_edit_config": mark("account-edit"),
        "handle_account_remove_config": mark("account-remove"),
        "handle_account_rename_config": mark("account-rename"),
        "handle_account_status_config": mark("account-status"),
        "handle_account_login_config": mark("account-login"),
        "display_usage_stats": mark("usage"),
        "resolve_provider_context": lambda current: {"id": "relay", "base_url": "https://api.example", "api_key": "key"},
        "setup_provider_credentials": mark("setup-provider-credentials"),
        "handle_api_config": mark("api-config"),
        "console": console,
    }

    routes = [
        ([], "display-config", (cfg,)),
        (["help"], "display-help", ()),
        (["migrate"], "migrate", ()),
        (["file"], "file", ()),
        (["validate"], "validate", (cfg,)),
        (["preferences.help"], "preferences-help", ()),
        (["preferences.path"], "preferences-path", ()),
        (["preferences.example"], "preferences-example", ()),
        (["human-gate"], "human-gate", ()),
        (["get", "provider.default"], "get", (cfg, ["provider.default"])),
        (["set", "provider.default", "relay"], "set", (cfg, ["provider.default", "relay"])),
        (["unset", "provider.default"], "unset", (cfg, ["provider.default"])),
        (["connect"], "connect", (cfg,)),
        (["extension.openrouter", "models"], "openrouter", (cfg, ["models"])),
        (["adapter.registry"], "adapter-registry", ()),
        (["provider.list"], "provider-list", (cfg,)),
        (["provider.default", "relay"], "provider-default", (cfg, ["relay"])),
        (["provider.add", "openrouter"], "provider-add", (cfg, ["openrouter"])),
        (["provider.edit", "relay"], "provider-edit", (cfg, ["relay"])),
        (["provider.rename", "old", "new"], "provider-rename", (cfg, ["old", "new"])),
        (["provider.remove", "relay"], "provider-remove", (cfg, ["relay"])),
        (["provider.credentials", "relay"], "provider-credentials", (cfg, ["relay"])),
        (["account.list"], "account-list", (cfg,)),
        (["account.default"], "account-default", (cfg, [])),
        (["account.add", "codex"], "account-add", (cfg, ["codex"])),
        (["account.edit", "codex"], "account-edit", (cfg, ["codex"])),
        (["account.remove", "codex"], "account-remove", (cfg, ["codex"])),
        (["account.rename", "old", "new"], "account-rename", (cfg, ["old", "new"])),
        (["account.status", "codex"], "account-status", (cfg, ["codex"])),
        (["account.login", "codex"], "account-login", (cfg, ["codex"])),
        (["usage"], "usage", ()),
        (["api.base_url"], "api-config", ("api.base_url", [])),
        (["ui.language"], "get", (cfg, ["ui.language"])),
        (["ui.language", "zh"], "set", (cfg, ["ui.language", "zh"])),
    ]

    for argv, name, expected_args in routes:
        calls.clear()
        mms_command_tools.handle_config(cfg, argv, **kwargs)
        assert calls[-1][0] == name
        assert calls[-1][1] == expected_args

    console.items.clear()
    mms_command_tools.handle_config(cfg, ["preferences.doc"], **kwargs)
    assert "/tmp/preferences.md" in console.items

    calls.clear()
    with pytest.raises(SystemExit) as exc:
        mms_command_tools.handle_config(cfg, ["web", "--port", "0"], **kwargs)
    assert exc.value.code == 23
    assert calls == [
        (
            "web",
            (cfg, ["--port", "0"]),
            {
                "command_name": "mmg",
                "config_path": "/tmp/config.toml",
                "preferences_path": "/tmp/preferences.toml",
            },
        )
    ]

    calls.clear()
    mms_command_tools.handle_config(cfg, ["api.setup"], **kwargs)
    assert calls == [
        (
            "setup-provider-credentials",
            ({"id": "relay", "base_url": "https://api.example", "api_key": "key"}, "https://api.example", "key"),
            {"allow_keep": True},
        )
    ]


def test_session_list_info_display_helpers():
    import pytest
    import mms_command_tools

    console = _CollectingConsole()
    rows = [
        {
            "session_id": "session-1",
            "project_path": "/tmp/demo",
            "account_id": "claude-a",
            "last_active_at": "2026-05-28",
        },
        {
            "pid": 123,
            "project_path": "",
            "runtime_kind": "provider",
            "started_at": "2026-05-27",
            "exit_code": 7,
        },
    ]

    mms_command_tools.handle_session_ls(
        "claude",
        list_indexed_sessions=lambda cli_name: rows,
        table_cls=_FakeTable,
        console=console,
    )
    table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert table.rows[0][0] == ("session-1", "demo", "claude-a", "active", "2026-05-28")
    assert table.rows[1][0] == ("pid-123", "-", "provider", "active", "2026-05-27")

    console.items.clear()
    mms_command_tools.handle_session_info(
        "session-1",
        "claude",
        get_indexed_session=lambda session_id, cli_name: {"session_id": session_id, "extra": "value"},
        table_cls=_FakeTable,
        console=console,
    )
    info_table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert ("session_id", "session-1") in [row for row, _kwargs in info_table.rows]
    assert ("extra", "value") in [row for row, _kwargs in info_table.rows]

    console.items.clear()
    with pytest.raises(SystemExit) as exc:
        mms_command_tools.handle_session_info(
            "missing",
            "claude",
            get_indexed_session=lambda session_id, cli_name: None,
            table_cls=_FakeTable,
            console=console,
        )
    assert exc.value.code == 1
    assert any("找不到 session: missing" in str(item) for item in console.items)


def test_session_gateway_stale_helpers_preserve_roots_size_and_sorting(tmp_path):
    import os

    import mms_command_tools
    import mms_core

    real_home = tmp_path / "home"
    roots = dict(mms_command_tools.session_gateway_roots("all", real_home=str(real_home)))
    assert set(roots) == {"claude", "codex", "opencode"}
    assert roots["claude"].endswith(os.path.join(".config", "mms", "claude-gateway", "s"))

    active = os.path.join(roots["claude"], "active")
    small = os.path.join(roots["claude"], "small")
    large = os.path.join(roots["codex"], "large")
    os.makedirs(active)
    os.makedirs(small)
    os.makedirs(large)
    (tmp_path / "linked-target").write_text("ignored", encoding="utf-8")
    with open(os.path.join(small, "a.txt"), "w", encoding="utf-8") as handle:
        handle.write("1234")
    with open(os.path.join(large, "b.txt"), "w", encoding="utf-8") as handle:
        handle.write("12345678")
    try:
        os.symlink(str(tmp_path / "linked-target"), os.path.join(large, "linked"))
    except OSError:
        pass

    rows = mms_command_tools.list_stale_gateway_sessions(
        "all",
        session_gateway_roots=lambda _cli: [("claude", roots["claude"]), ("codex", roots["codex"])],
        session_home_is_active=lambda path: path == active,
        session_dir_size_bytes=mms_command_tools.session_dir_size_bytes,
    )

    assert [(row["cli"], row["name"], row["size"]) for row in rows] == [
        ("codex", "large", 8),
        ("claude", "small", 4),
    ]
    assert mms_command_tools.format_bytes(1536) == "1.5K"
    assert mms_core._format_bytes(0) == "0B"


def test_session_prune_handler_dry_run_and_apply_with_injected_remove():
    import mms_command_tools

    rows = [
        {"cli": "claude", "name": "123", "size": 1024, "mtime": "2026-05-28", "path": "/tmp/mms/claude-gateway/s/123"},
        {"cli": "codex", "name": "456", "size": 2048, "mtime": "2026-05-27", "path": "/tmp/mms/codex-gateway/s/456"},
    ]
    console = _CollectingConsole()
    finalized = []
    removed = []

    mms_command_tools.handle_session_prune(
        "all",
        apply=False,
        yes=False,
        list_stale_gateway_sessions=lambda cli_name: rows,
        finalize_claude_slot=lambda *args, **kwargs: finalized.append((args, kwargs)),
        remove_tree=lambda *args, **kwargs: removed.append((args, kwargs)),
        format_bytes=lambda size: f"{size}B",
        table_cls=_FakeTable,
        console=console,
    )
    table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert table.rows[0][0] == ("claude", "123", "1024B", "2026-05-28", "/tmp/mms/claude-gateway/s/123")
    assert removed == []
    assert any("dry-run only" in str(item) for item in console.items)

    console.items.clear()
    mms_command_tools.handle_session_prune(
        "all",
        apply=True,
        yes=True,
        list_stale_gateway_sessions=lambda cli_name: rows,
        finalize_claude_slot=lambda *args, **kwargs: finalized.append((args, kwargs)),
        remove_tree=lambda *args, **kwargs: removed.append((args, kwargs)),
        format_bytes=lambda size: f"{size}B",
        table_cls=_FakeTable,
        console=console,
    )
    assert finalized == [(("/tmp/mms/claude-gateway/s/123",), {"stale_cleanup": True})]
    assert removed == [
        (("/tmp/mms/claude-gateway/s/123",), {"ignore_errors": True}),
        (("/tmp/mms/codex-gateway/s/456",), {"ignore_errors": True}),
    ]
    assert any("已删除 2 个 stale MMS session" in str(item) for item in console.items)


def test_provider_model_table_display_renders_speed_and_sources():
    import mms_command_tools

    console = _CollectingConsole()
    provider = {"id": "relay", "name": "Relay"}
    probe = {
        "models": ["gpt-5.5", "custom-model"],
        "raw_models": ["gpt-5.5", "custom-model", "hidden-model"],
        "extra_models": ["custom-model"],
        "hidden_models": ["hidden-model"],
        "model_sources": {"custom-model": "manual"},
        "base_source": "remote",
    }

    mms_command_tools.display_provider_model_table(
        provider,
        probe,
        get_speed_entry=lambda model_id, provider=None: {
            "ttfb_avg_ms": 123.4,
            "tps_avg": 45.67,
            "samples": 2,
            "last_updated": "2026-05-28",
            "warming_up": model_id == "custom-model",
            "is_stale": model_id == "custom-model",
        },
        infer_model_family=lambda model_id: ("GPT", None),
        model_capability_summary=lambda model_id: "tools",
        model_cli_summary=lambda model_id: "codex",
        model_source_label=lambda source: f"src:{source}",
        ttfb_label=lambda value: "fast",
        tps_label=lambda value: "quick",
        table_cls=_FakeTable,
        console=console,
    )

    table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert table.rows[0][0] == (
        "gpt-5.5",
        "GPT",
        "tools",
        "codex",
        "src:remote",
        "123ms / fast",
        "45.7 / quick",
        "2",
        "2026-05-28",
    )
    assert table.rows[1][0][4] == "src:manual"
    assert table.rows[1][0][7] == "2（预热中）"
    assert table.rows[1][0][8] == "2026-05-28 (stale)"
    text = "\n".join(str(item) for item in console.items)
    assert "手工补充模型: custom-model" in text
    assert "已隐藏模型: hidden-model" in text
    assert "原始模型数: 3" in text


def test_openrouter_extension_arg_and_provider_helpers_preserve_detection_rules():
    import mms_command_tools

    assert mms_command_tools.provider_looks_openrouter({"id": "relay", "base_url": "https://openrouter.ai/api/v1"})
    assert mms_command_tools.provider_looks_openrouter({"provider_profile": "openrouter"})
    assert not mms_command_tools.provider_looks_openrouter({"id": "relay", "base_url": "https://example.com/v1"})
    assert not mms_command_tools.provider_looks_openrouter(None)

    cfg = {
        "providers": [
            {"id": "or", "name": "OpenRouter"},
            {"id": "plain", "name": "Plain"},
            {"id": "fallback", "base_url": "https://openrouter.example/v1"},
        ]
    }
    calls = []

    def resolve_provider_context(_cfg, provider_id):
        calls.append(provider_id)
        if provider_id == "fallback":
            raise RuntimeError("missing credentials")
        return {"id": provider_id, "resolved": True}

    assert mms_command_tools.openrouter_provider_candidates(
        cfg,
        resolve_provider_context=resolve_provider_context,
    ) == [
        {"id": "or", "resolved": True},
        {"id": "fallback", "base_url": "https://openrouter.example/v1"},
    ]
    assert calls == ["or", "fallback"]
    assert mms_command_tools.openrouter_extension_provider(
        cfg,
        "",
        provider_map=lambda current_cfg: {item["id"]: item for item in current_cfg["providers"]},
        resolve_provider_context=resolve_provider_context,
        openrouter_provider_candidates=lambda _cfg: [{"id": "or", "resolved": True}],
    ) == ({"id": "or", "resolved": True}, "")
    provider, warning = mms_command_tools.openrouter_extension_provider(
        cfg,
        "plain",
        provider_map=lambda current_cfg: {item["id"]: item for item in current_cfg["providers"]},
        resolve_provider_context=lambda _cfg, provider_id: {"id": provider_id, "base_url": "https://example.com/v1"},
        openrouter_provider_candidates=lambda _cfg: [],
    )
    assert provider == {"id": "plain", "base_url": "https://example.com/v1"}
    assert "不是 OpenRouter 模板" in warning
    assert mms_command_tools.openrouter_extension_provider(
        cfg,
        "missing",
        provider_map=lambda current_cfg: {item["id"]: item for item in current_cfg["providers"]},
        resolve_provider_context=resolve_provider_context,
        openrouter_provider_candidates=lambda _cfg: [],
    ) == (None, "未找到 provider: missing")

    assert mms_command_tools.parse_openrouter_extension_args(
        ["list", "or", "--limit", "0", "--assume-paid", "--json"]
    ) == {
        "action": "models",
        "provider_id": "or",
        "limit": 1,
        "assume_paid": True,
        "json": True,
    }
    assert mms_command_tools.parse_openrouter_extension_args(["help"])["action"] == "help"
    assert mms_command_tools.parse_openrouter_extension_args(["models", "--limit", "bad"])["limit"] == 12


def test_openrouter_extension_handler_preserves_help_add_probe_json_and_env_fallback():
    import json

    import mms_command_tools

    console = _CollectingConsole()
    calls = []
    summaries = []

    def parse_args(args_rest):
        return mms_command_tools.parse_openrouter_extension_args(args_rest)

    mms_command_tools.handle_openrouter_extension_config(
        {"cfg": True},
        ["help"],
        parse_openrouter_extension_args=parse_args,
        display_openrouter_extension_help=lambda: calls.append(("help",)),
        quick_connect_gateway=lambda cfg, preset_id=None: calls.append(("connect", cfg, preset_id)),
        openrouter_extension_provider=lambda cfg, provider_id="": (None, ""),
        openrouter_api_key_from_env=lambda: "",
        probe_openrouter_extension=lambda api_key, assume_paid=False: {"unexpected": True},
        display_openrouter_extension_summary=lambda *args, **kwargs: summaries.append((args, kwargs)),
        console=console,
    )
    assert calls == [("help",)]

    mms_command_tools.handle_openrouter_extension_config(
        {"cfg": True},
        ["add"],
        parse_openrouter_extension_args=parse_args,
        display_openrouter_extension_help=lambda: calls.append(("unexpected-help",)),
        quick_connect_gateway=lambda cfg, preset_id=None: calls.append(("connect", cfg, preset_id)),
        openrouter_extension_provider=lambda cfg, provider_id="": (None, ""),
        openrouter_api_key_from_env=lambda: "",
        probe_openrouter_extension=lambda api_key, assume_paid=False: {"unexpected": True},
        display_openrouter_extension_summary=lambda *args, **kwargs: summaries.append((args, kwargs)),
        console=console,
    )
    assert calls[-1] == ("connect", {"cfg": True}, "openrouter")
    assert summaries == []

    console.items.clear()
    calls.clear()
    mms_command_tools.handle_openrouter_extension_config(
        {},
        ["models", "or", "--limit", "3", "--assume-paid"],
        parse_openrouter_extension_args=parse_args,
        display_openrouter_extension_help=lambda: calls.append(("unexpected-help",)),
        quick_connect_gateway=lambda cfg, preset_id=None: calls.append(("unexpected-connect", cfg, preset_id)),
        openrouter_extension_provider=lambda cfg, provider_id="": (
            {"id": provider_id, "name": "OpenRouter", "api_key": "provider-key"},
            "non-fatal warning",
        ),
        openrouter_api_key_from_env=lambda: "env-key",
        probe_openrouter_extension=lambda api_key, assume_paid=False: calls.append(
            ("probe", api_key, assume_paid)
        ) or {"counts": {"visible_text": 1}},
        display_openrouter_extension_summary=lambda summary, **kwargs: summaries.append((summary, kwargs)),
        console=console,
    )
    assert "[yellow]non-fatal warning[/yellow]" in console.items
    assert calls == [("probe", "provider-key", True)]
    assert summaries[-1] == (
        {"counts": {"visible_text": 1}},
        {"provider_label": "OpenRouter (or)", "limit": 3, "show_models": True},
    )

    console.items.clear()
    calls.clear()
    summaries.clear()
    mms_command_tools.handle_openrouter_extension_config(
        {},
        ["status", "--json"],
        parse_openrouter_extension_args=parse_args,
        display_openrouter_extension_help=lambda: calls.append(("unexpected-help",)),
        quick_connect_gateway=lambda cfg, preset_id=None: calls.append(("unexpected-connect", cfg, preset_id)),
        openrouter_extension_provider=lambda cfg, provider_id="": (None, ""),
        openrouter_api_key_from_env=lambda: "env-key",
        probe_openrouter_extension=lambda api_key, assume_paid=False: {
            "api_key": api_key,
            "assume_paid": assume_paid,
        },
        display_openrouter_extension_summary=lambda *args, **kwargs: summaries.append((args, kwargs)),
        console=console,
    )
    assert json.loads(console.items[-1]) == {"api_key": "env-key", "assume_paid": False}
    assert summaries == []


def test_openrouter_extension_display_helpers_render_summary_and_limits():
    import mms_command_tools

    console = _CollectingConsole()
    rows = [
        {
            "id": "free/model",
            "origin": "openrouter",
            "is_free": True,
            "input_modalities": ["text"],
            "output_modalities": ["text"],
            "context_length": 128000,
        },
        {
            "id": "paid/model",
            "origin": "openrouter",
            "is_free": False,
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
            "context_length": 200000,
        },
    ]

    mms_command_tools.display_openrouter_extension_help("mmg", console=console)
    assert "mmg config extension.openrouter add" in "\n".join(str(item) for item in console.items)

    console.items.clear()
    mms_command_tools.display_openrouter_model_rows(
        "OpenRouter Text 模型",
        rows,
        limit=1,
        table_cls=_FakeTable,
        console=console,
    )
    text_table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert text_table.kwargs["title"] == "OpenRouter Text 模型"
    assert text_table.rows[0][0] == ("free/model", "openrouter", "yes", "text", "text", "128000")
    assert any("仅展示前 1 / 2 个" in str(item) for item in console.items)

    console.items.clear()
    summary = {
        "account": {"tier": "paid", "reason": "key"},
        "counts": {"visible_text": 2},
        "requests": {"models": {"status": "ok"}},
        "model_source": "api",
        "image_enabled": True,
        "video_enabled": True,
        "free_only": True,
        "text_models": rows,
        "image_models": [{"id": "img/model", "origin": "openrouter", "is_free": False}],
        "video_models": [
            {
                "id": "video/model",
                "origin": "openrouter",
                "supported_resolutions": ["720p"],
                "supported_durations": [5, 10],
            }
        ],
    }
    mms_command_tools.display_openrouter_extension_summary(
        summary,
        provider_label="provider/openrouter",
        limit=1,
        show_models=True,
        table_cls=_FakeTable,
        console=console,
    )
    tables = [item for item in console.items if isinstance(item, _FakeTable)]
    assert tables[0].rows[0][0] == ("provider/key", "provider/openrouter")
    assert tables[0].rows[4][0] == ("image/video", "on / on")
    assert tables[0].rows[5][0] == ("requests", "models:ok")
    assert tables[-1].rows[0][0] == ("video/model", "openrouter", "720p", "5,10")
    assert any("free-only" in str(item) for item in console.items)


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
