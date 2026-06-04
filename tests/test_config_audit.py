from __future__ import annotations

import json
import sys
from pathlib import Path


def test_save_config_creates_backup_and_audit(monkeypatch, tmp_path):
    import mms_core

    target = tmp_path / "config.toml"
    target.write_text('reload = "--help"\n', encoding="utf-8")

    monkeypatch.setattr(mms_core, "_config_write_target_path", lambda: str(target))
    monkeypatch.setattr(mms_core, "_config_write_caller", lambda: {
        "path": "/tmp/caller.py",
        "line": 12,
        "function": "manual_restore",
    })
    monkeypatch.setattr(mms_core, "_iso_now", lambda: "2026-04-12T08:00:00Z")
    monkeypatch.setattr(mms_core, "_local_now_slug", lambda: "20260412-160000")

    mms_core.save_config({"reload": "--ok"}, reason="restore claude-tonnya")

    audit_path = tmp_path / "config-audit.jsonl"
    backup_path = tmp_path / "backups" / "config-write-20260412-160000" / "config.toml"

    assert backup_path.exists()
    assert 'reload = "--help"' in backup_path.read_text(encoding="utf-8")
    assert audit_path.exists()

    rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["reason"] == "restore claude-tonnya"
    assert rows[0]["backup_path"] == str(backup_path)
    assert rows[0]["target_path"] == str(target)
    assert rows[0]["caller_function"] == "manual_restore"


def test_save_config_uses_auto_reason_when_missing(monkeypatch, tmp_path):
    import mms_core

    target = tmp_path / "config.toml"
    monkeypatch.setattr(mms_core, "_config_write_target_path", lambda: str(target))
    monkeypatch.setattr(mms_core, "_config_write_caller", lambda: {
        "path": "/tmp/caller.py",
        "line": 34,
        "function": "account_edit",
    })
    monkeypatch.setattr(mms_core, "_iso_now", lambda: "2026-04-12T08:01:00Z")
    monkeypatch.setattr(mms_core, "_local_now_slug", lambda: "20260412-160100")

    mms_core.save_config({"reload": "--ok"})

    audit_path = Path(tmp_path / "config-audit.jsonl")
    rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[0]["reason"] == "auto:account_edit"


def test_save_config_bootstraps_guard_files(monkeypatch, tmp_path):
    import mms_core

    target = tmp_path / "config.toml"
    monkeypatch.setattr(mms_core, "_config_write_target_path", lambda: str(target))
    monkeypatch.setattr(mms_core, "_local_now_slug", lambda: "20260412-160200")

    mms_core.save_config({"reload": "--ok"}, reason="bootstrap guards")

    agents_path = tmp_path / "AGENTS.md"
    claude_path = tmp_path / "CLAUDE.md"

    assert agents_path.exists()
    assert claude_path.exists()
    assert "human confirmation before write" in agents_path.read_text(encoding="utf-8")
    assert "human-only config" in claude_path.read_text(encoding="utf-8")


def test_startup_snapshot_guard_bootstraps_snapshots(monkeypatch, tmp_path):
    import mms_core

    target = tmp_path / "config.toml"
    target.write_text('reload = "--ok"\n', encoding="utf-8")
    monkeypatch.setattr(mms_core, "_config_write_target_path", lambda: str(target))
    monkeypatch.setattr(mms_core, "_iso_now", lambda: "2026-04-12T08:02:00Z")
    monkeypatch.setattr(mms_core, "_snapshot_period_bucket", lambda _name: "bucket-1")

    cfg = {
        "provider": {"default": "default"},
        "account": {"defaults": {"claude": "claude-a"}},
        "providers": [],
        "accounts": [
            {
                "id": "claude-a",
                "cli": "claude",
                "home_dir": str(tmp_path / "accounts" / "claude-a"),
                "proxy": "http://127.0.0.1:7890",
                "timezone": "America/Los_Angeles",
                "force_ipv4": True,
            }
        ],
    }

    mms_core._ensure_startup_snapshot_guard(cfg)

    accepted = tmp_path / "snapshots" / "startup" / "accepted.json"
    latest = tmp_path / "snapshots" / "startup" / "latest.json"
    daily = tmp_path / "snapshots" / "daily" / "latest.json"
    weekly = tmp_path / "snapshots" / "weekly" / "latest.json"

    assert accepted.exists()
    assert latest.exists()
    assert daily.exists()
    assert weekly.exists()


def test_startup_snapshot_guard_blocks_on_proxy_drift(monkeypatch, tmp_path, capsys):
    import mms_core

    target = tmp_path / "config.toml"
    target.write_text('reload = "--ok"\n', encoding="utf-8")
    monkeypatch.setattr(mms_core, "_config_write_target_path", lambda: str(target))
    monkeypatch.setattr(mms_core, "_iso_now", lambda: "2026-04-12T08:03:00Z")
    monkeypatch.setattr(mms_core, "_snapshot_period_bucket", lambda _name: "bucket-2")
    monkeypatch.setattr(mms_core, "_confirm_startup_snapshot_drift", lambda *args, **kwargs: False)

    cfg = {
        "provider": {"default": "default"},
        "account": {"defaults": {"claude": "claude-a"}},
        "providers": [],
        "accounts": [
            {
                "id": "claude-a",
                "cli": "claude",
                "home_dir": str(tmp_path / "accounts" / "claude-a"),
                "proxy": "http://127.0.0.1:7890",
                "timezone": "America/Los_Angeles",
                "force_ipv4": True,
            }
        ],
    }

    mms_core._ensure_startup_snapshot_guard(cfg)

    drifted_cfg = {
        **cfg,
        "accounts": [
            {
                **cfg["accounts"][0],
                "proxy": "",
            }
        ],
    }

    try:
        mms_core._ensure_startup_snapshot_guard(drifted_cfg)
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert exc.code == mms_core.CONFIG_GUARD_EXIT_CODE

    pending = tmp_path / "snapshots" / "startup" / "pending.json"
    assert pending.exists()
    payload = json.loads(pending.read_text(encoding="utf-8"))
    assert any("account claude-a proxy" in item for item in payload["diffs"])

    out = capsys.readouterr().out
    assert "guard status" in out
    assert "guard accept" in out


def test_startup_snapshot_guard_skips_block_when_not_enforced(monkeypatch, tmp_path):
    import mms_core

    target = tmp_path / "config.toml"
    target.write_text('reload = "--ok"\n', encoding="utf-8")
    monkeypatch.setattr(mms_core, "_config_write_target_path", lambda: str(target))
    monkeypatch.setattr(mms_core, "_iso_now", lambda: "2026-04-12T08:03:30Z")
    monkeypatch.setattr(mms_core, "_snapshot_period_bucket", lambda _name: "bucket-2b")
    monkeypatch.setattr(mms_core, "_confirm_startup_snapshot_drift", lambda *args, **kwargs: False)

    cfg = {
        "provider": {"default": "default"},
        "account": {"defaults": {"claude": "claude-a"}},
        "providers": [],
        "accounts": [
            {
                "id": "claude-a",
                "cli": "claude",
                "home_dir": str(tmp_path / "accounts" / "claude-a"),
                "proxy": "http://127.0.0.1:7890",
                "timezone": "America/Los_Angeles",
                "force_ipv4": True,
            }
        ],
    }

    mms_core._ensure_startup_snapshot_guard(cfg)

    drifted_cfg = {
        **cfg,
        "accounts": [
            {
                **cfg["accounts"][0],
                "proxy": "",
            }
        ],
    }

    result = mms_core._ensure_startup_snapshot_guard(drifted_cfg, enforce=False)

    assert result["accounts"][0]["id"] == "claude-a"
    pending = tmp_path / "snapshots" / "startup" / "pending.json"
    assert pending.exists()


def test_tui_guard_accept_requires_drift_confirmation(monkeypatch, tmp_path):
    import mms_core

    target = tmp_path / "config.toml"
    target.write_text('reload = "--ok"\n', encoding="utf-8")
    monkeypatch.setattr(mms_core, "_config_write_target_path", lambda: str(target))
    monkeypatch.setattr(mms_core, "_iso_now", lambda: "2026-04-12T08:03:45Z")
    monkeypatch.setattr(mms_core, "_snapshot_period_bucket", lambda _name: "bucket-2c")

    cfg = {
        "provider": {"default": "default"},
        "account": {"defaults": {"claude": "claude-a"}},
        "providers": [],
        "accounts": [
            {
                "id": "claude-a",
                "cli": "claude",
                "home_dir": str(tmp_path / "accounts" / "claude-a"),
                "proxy": "http://127.0.0.1:7890",
                "timezone": "America/Los_Angeles",
                "force_ipv4": True,
            }
        ],
    }
    mms_core._ensure_startup_snapshot_guard(cfg)

    calls = []

    def fake_confirm(diff_lines, **kwargs):
        calls.append((diff_lines, kwargs))
        return True

    monkeypatch.setattr(mms_core, "_confirm_startup_snapshot_drift", fake_confirm)
    drifted_cfg = {
        **cfg,
        "accounts": [{**cfg["accounts"][0], "timezone": "Asia/Singapore"}],
    }

    assert mms_core._confirm_guard_accept_from_tui(drifted_cfg) is True
    assert calls
    assert any("account claude-a timezone" in item for item in calls[0][0])
    assert calls[0][1]["accepted_path"].endswith("accepted.json")


def test_startup_snapshot_guard_ignores_config_file_and_audit_churn(monkeypatch, tmp_path):
    import mms_core

    target = tmp_path / "config.toml"
    target.write_text('reload = "--ok"\n', encoding="utf-8")
    audit_path = tmp_path / "config-audit.jsonl"
    audit_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(mms_core, "_config_write_target_path", lambda: str(target))
    monkeypatch.setattr(mms_core, "_iso_now", lambda: "2026-04-12T08:04:00Z")
    monkeypatch.setattr(mms_core, "_snapshot_period_bucket", lambda _name: "bucket-3")

    cfg = {
        "provider": {"default": "default"},
        "account": {"defaults": {"claude": "claude-a"}},
        "providers": [],
        "accounts": [
            {
                "id": "claude-a",
                "cli": "claude",
                "home_dir": str(tmp_path / "accounts" / "claude-a"),
                "proxy": "http://127.0.0.1:7890",
                "timezone": "America/Los_Angeles",
                "force_ipv4": True,
            }
        ],
    }

    mms_core._ensure_startup_snapshot_guard(cfg)
    target.write_text('reload = "--changed-but-semantic-same"\n', encoding="utf-8")
    audit_path.write_text('{"x":1}\n', encoding="utf-8")
    mms_core._ensure_startup_snapshot_guard(cfg)

    pending = tmp_path / "snapshots" / "startup" / "pending.json"
    assert not pending.exists()


def test_startup_snapshot_guard_ignores_usage_and_account_guard_churn(monkeypatch, tmp_path):
    import mms_core

    target = tmp_path / "config.toml"
    target.write_text('reload = "--ok"\n', encoding="utf-8")
    usage_path = tmp_path / "usage.json"
    usage_path.write_text('{"sources":{}}\n', encoding="utf-8")
    guard_state_path = tmp_path / "account-guard-state.json"
    guard_state_path.write_text('{"accounts":{}}\n', encoding="utf-8")
    monkeypatch.setattr(mms_core, "_config_write_target_path", lambda: str(target))
    monkeypatch.setattr(mms_core, "_iso_now", lambda: "2026-04-12T08:05:00Z")
    monkeypatch.setattr(mms_core, "_snapshot_period_bucket", lambda _name: "bucket-4")

    cfg = {
        "provider": {"default": "default"},
        "account": {"defaults": {"claude": "claude-a"}},
        "providers": [],
        "accounts": [
            {
                "id": "claude-a",
                "cli": "claude",
                "home_dir": str(tmp_path / "accounts" / "claude-a"),
                "proxy": "http://127.0.0.1:7890",
                "timezone": "America/Los_Angeles",
                "force_ipv4": True,
            }
        ],
    }

    mms_core._ensure_startup_snapshot_guard(cfg)
    usage_path.write_text('{"sources":{"x":1}}\n', encoding="utf-8")
    guard_state_path.write_text('{"accounts":{"claude-a":{"launch_count":3}}}\n', encoding="utf-8")
    mms_core._ensure_startup_snapshot_guard(cfg)

    pending = tmp_path / "snapshots" / "startup" / "pending.json"
    assert not pending.exists()


def test_startup_snapshot_guard_ignores_claude_state_runtime_churn(monkeypatch, tmp_path):
    import mms_core

    target = tmp_path / "config.toml"
    target.write_text('reload = "--ok"\n', encoding="utf-8")
    home_dir = tmp_path / "accounts" / "claude-a"
    home_dir.mkdir(parents=True, exist_ok=True)
    claude_json = home_dir / ".claude.json"
    claude_json.write_text(
        json.dumps(
            {
                "userID": "user-1",
                "numStartups": 1,
                "projects": {"/tmp/repo": {"lastSessionId": "a", "lastCost": 1}},
                "oauthAccount": {
                    "accountUuid": "acct-1",
                    "emailAddress": "u@example.com",
                    "organizationUuid": "org-1",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mms_core, "_config_write_target_path", lambda: str(target))
    monkeypatch.setattr(mms_core, "_iso_now", lambda: "2026-04-12T08:06:00Z")
    monkeypatch.setattr(mms_core, "_snapshot_period_bucket", lambda _name: "bucket-5")

    cfg = {
        "provider": {"default": "default"},
        "account": {"defaults": {"claude": "claude-a"}},
        "providers": [],
        "accounts": [
            {
                "id": "claude-a",
                "cli": "claude",
                "home_dir": str(home_dir),
                "proxy": "http://127.0.0.1:7890",
                "timezone": "America/Los_Angeles",
                "force_ipv4": True,
            }
        ],
    }

    mms_core._ensure_startup_snapshot_guard(cfg)
    claude_json.write_text(
        json.dumps(
            {
                "userID": "user-1",
                "numStartups": 99,
                "projects": {"/tmp/repo": {"lastSessionId": "b", "lastCost": 999}},
                "oauthAccount": {
                    "accountUuid": "acct-1",
                    "emailAddress": "u@example.com",
                    "organizationUuid": "org-1",
                },
            }
        ),
        encoding="utf-8",
    )
    mms_core._ensure_startup_snapshot_guard(cfg)

    pending = tmp_path / "snapshots" / "startup" / "pending.json"
    assert not pending.exists()


def test_logs_command_shows_copyable_commands(monkeypatch, capsys, tmp_path):
    import mms_core

    monkeypatch.setenv("MMS_REAL_HOME", str(tmp_path))

    mms_core.handle_logs_command(["--tail", "7"])
    out = capsys.readouterr().out

    assert "config_root" in out
    assert "fake-upstream" not in out
    assert "guard status" in out


def test_script_subcommand_sets_display_prog(monkeypatch, tmp_path):
    import mms_commands.tools as mms_command_tools

    script_dir = tmp_path / "scripts"
    script_dir.mkdir()
    script_path = script_dir / "smoke_cli_channels.py"
    script_path.write_text("print('ok')\n", encoding="utf-8")
    captured = {}

    class Console:
        def print(self, *_args, **_kwargs):
            raise AssertionError("console should not be used when script exists")

    class Completed:
        returncode = 7

    def fake_run(cmd, env):
        captured["cmd"] = cmd
        captured["env"] = env
        return Completed()

    monkeypatch.setattr(mms_command_tools.subprocess, "run", fake_run)

    code = mms_command_tools.handle_test_command(
        ["--dry-run"],
        subcommand_name="smoke",
        script_dir=str(script_dir),
        command_name="mmg",
        console=Console(),
    )

    assert code == 7
    assert captured["cmd"] == [sys.executable, str(script_path), "--dry-run"]
    assert captured["env"]["MMS_SUBCOMMAND_PROG"] == "mmg smoke"


def test_cache_command_show_renders_defaults():
    import mms_commands.tools as mms_command_tools

    class Table:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.rows = []

        def add_column(self, *_args, **_kwargs):
            pass

        def add_row(self, *args, **kwargs):
            self.rows.append((args, kwargs))

    class Console:
        def __init__(self):
            self.items = []

        def print(self, *args, **_kwargs):
            self.items.append(args[0] if args else "")

    console = Console()

    mms_command_tools.handle_cache_command(
        ["show"],
        command_name="mmg",
        load_command_config=lambda: {},
        normalize_positive_seconds=lambda value, minimum: max(int(value), minimum),
        ensure_provider_config=lambda cfg: (cfg, False),
        ensure_account_config=lambda cfg: (cfg, False),
        normalize_user_config=lambda cfg: (cfg, False),
        normalize_cache_config=lambda cfg: (cfg, False),
        save_config=lambda _cfg: (_ for _ in ()).throw(AssertionError("show must not save config")),
        probe_async_refresh_after=1800,
        probe_async_min_interval=300,
        table_cls=Table,
        console=console,
    )

    table = console.items[0]
    assert table.kwargs["title"] == "MMS Cache Settings"
    rows = [row for row, _kwargs in table.rows]
    assert ("probe_async_refresh_after_sec", "1800", "cache 超过多久后，启动时后台刷新") in rows
    assert ("probe_async_min_interval_sec", "300", "同一 provider 两次异步刷新最小间隔") in rows
    assert any("mmg cache reset" in str(item) for item in console.items)


def test_cache_command_refresh_after_saves_normalized_config():
    import mms_commands.tools as mms_command_tools

    class Console:
        def __init__(self):
            self.items = []

        def print(self, *args, **_kwargs):
            self.items.append(args[0] if args else "")

    saved = {}
    calls = []

    def passthrough(name):
        def _inner(cfg):
            calls.append(name)
            return cfg, False

        return _inner

    mms_command_tools.handle_cache_command(
        ["refresh-after", "0"],
        command_name="mmg",
        load_command_config=lambda: {"cache": {"probe_async_min_interval_sec": 42}},
        normalize_positive_seconds=lambda value, minimum: max(int(value), minimum),
        ensure_provider_config=passthrough("provider"),
        ensure_account_config=passthrough("account"),
        normalize_user_config=passthrough("user"),
        normalize_cache_config=passthrough("cache"),
        save_config=lambda cfg: saved.update(cfg),
        probe_async_refresh_after=1800,
        probe_async_min_interval=300,
        table_cls=object,
        console=Console(),
    )

    assert calls == ["provider", "account", "user", "cache"]
    assert saved["cache"]["probe_async_refresh_after_sec"] == 1
    assert saved["cache"]["probe_async_min_interval_sec"] == 42


def test_guard_command_status_renders_drift(tmp_path):
    import mms_commands.tools as mms_command_tools

    class Table:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.rows = []

        def add_column(self, *_args, **_kwargs):
            pass

        def add_row(self, *args, **kwargs):
            self.rows.append((args, kwargs))

    class Console:
        def __init__(self):
            self.items = []

        def print(self, *args, **_kwargs):
            self.items.append(args[0] if args else "")

    pending_path = tmp_path / "pending.json"
    pending_path.write_text("{}", encoding="utf-8")
    current_snapshot = {
        "real_home": "/home/real",
        "config_path": str(tmp_path / "config.toml"),
        "accounts": [{"id": "claude-a"}],
        "providers": [{"id": "relay"}],
    }
    paths = {
        "latest.json": str(tmp_path / "latest.json"),
        "accepted.json": str(tmp_path / "accepted.json"),
        "pending.json": str(pending_path),
    }
    console = Console()

    mms_command_tools.handle_guard_command(
        ["status"],
        command_name="mmg",
        bootstrap_cfg={"providers": []},
        load_config=lambda: {"should": "not-load"},
        default_config=lambda: {"should": "not-default"},
        config_write_target_path=lambda: str(tmp_path / "config.toml"),
        build_config_guard_snapshot=lambda cfg, config_path: current_snapshot,
        config_snapshot_path=lambda _kind, name, config_path: paths[name],
        load_json_snapshot=lambda path: {"snapshot": {"old": True}} if path == paths["accepted.json"] else None,
        snapshot_diff_lines=lambda accepted, current: ["account claude-a proxy changed"],
        iso_now=lambda: "2026-05-28T00:00:00Z",
        snapshot_digest=lambda snapshot: "digest",
        write_json_snapshot=lambda _path, _payload: (_ for _ in ()).throw(AssertionError("status must not write")),
        table_cls=Table,
        console=console,
    )

    table = console.items[0]
    rows = [row for row, _kwargs in table.rows]
    assert table.kwargs["title"] == "MMS Snapshot Guard"
    assert ("status", "drift") in rows
    assert ("pending", str(pending_path)) in rows
    assert any("account claude-a proxy changed" in str(item) for item in console.items)


def test_guard_command_accept_writes_snapshot_and_clears_pending(tmp_path):
    import mms_commands.tools as mms_command_tools

    class Console:
        def __init__(self):
            self.items = []

        def print(self, *args, **_kwargs):
            self.items.append(args[0] if args else "")

    pending_path = tmp_path / "pending.json"
    pending_path.write_text("{}", encoding="utf-8")
    current_snapshot = {"real_home": "/home/real", "accounts": [], "providers": []}
    paths = {
        "latest.json": str(tmp_path / "latest.json"),
        "accepted.json": str(tmp_path / "accepted.json"),
        "pending.json": str(pending_path),
    }
    written = {}
    console = Console()

    mms_command_tools.handle_guard_command(
        ["accept"],
        command_name="mmg",
        bootstrap_cfg=None,
        load_config=lambda: None,
        default_config=lambda: {"default": True},
        config_write_target_path=lambda: str(tmp_path / "config.toml"),
        build_config_guard_snapshot=lambda cfg, config_path: current_snapshot,
        config_snapshot_path=lambda _kind, name, config_path: paths[name],
        load_json_snapshot=lambda _path: None,
        snapshot_diff_lines=lambda accepted, current: [],
        iso_now=lambda: "2026-05-28T00:00:00Z",
        snapshot_digest=lambda snapshot: "digest-1",
        write_json_snapshot=lambda path, payload: written.update({path: payload}),
        table_cls=object,
        console=console,
    )

    assert set(written) == {paths["latest.json"], paths["accepted.json"]}
    assert written[paths["accepted.json"]]["digest"] == "digest-1"
    assert written[paths["accepted.json"]]["snapshot"] == current_snapshot
    assert not pending_path.exists()
    assert any("已接受当前快照" in str(item) for item in console.items)


def test_exposure_command_renders_runtime_sections():
    import mms_commands.tools as mms_command_tools

    class Table:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.columns = []
            self.rows = []

        def add_column(self, *args, **kwargs):
            self.columns.append((args, kwargs))

        def add_row(self, *args, **kwargs):
            self.rows.append((args, kwargs))

    class Console:
        def __init__(self):
            self.items = []

        def print(self, *args, **_kwargs):
            self.items.append(args[0] if args else "")

    captured = {}
    console = Console()
    cfg = {"providers": []}
    provider = {"id": "relay"}
    models = {"models": ["gpt-5.5"]}
    runtime = {"id": "relay-runtime"}

    def choose_runtime_source(cfg_arg, cli, default_provider, models_cache, account_id=None, provider_id=None):
        captured["choose"] = {
            "cfg": cfg_arg,
            "cli": cli,
            "provider": default_provider,
            "models": models_cache,
            "account_id": account_id,
            "provider_id": provider_id,
        }
        return runtime, ["gpt-5.5"], "codex"

    def inspect_runtime_exposure(cli, runtime_arg):
        captured["inspect"] = (cli, runtime_arg)
        return {
            "cli": cli,
            "runtime_id": runtime_arg["id"],
            "auth_mode": "api_key",
            "network": {
                "proxy_mode": "direct",
                "dns_mode": "direct",
                "proxy_fingerprint": "direct",
                "timezone": "Asia/Singapore",
                "locale": "zh_CN.UTF-8",
                "force_ipv4": True,
            },
            "home": {
                "real_home": "/home/real",
                "account_home": "/home/account",
                "session_home": "/home/session",
                "settings_path": "/home/session/settings.json",
            },
            "process_env": [{"key": "MMS_MODEL_NAME", "value": "gpt-5.5"}],
            "settings": {"statusline": True, "hook_events": ["SessionStart"], "env_keys": ["ANTHROPIC_BASE_URL"]},
            "notes": ["safe"],
        }

    mms_command_tools.handle_exposure_command(
        ["codex", "--provider", "relay"],
        command_name="mmg",
        cli_names=["claude", "codex"],
        load_command_config=lambda: cfg,
        ensure_provider_credentials=lambda cfg_arg: provider,
        ensure_models_ready=lambda cfg_arg, provider_arg: (provider_arg, models),
        choose_runtime_source=choose_runtime_source,
        inspect_runtime_exposure=inspect_runtime_exposure,
        table_cls=Table,
        console=console,
    )

    assert captured["choose"]["cli"] == "codex"
    assert captured["choose"]["provider_id"] == "relay"
    assert captured["inspect"] == ("codex", runtime)
    titles = [item.kwargs.get("title") for item in console.items if isinstance(item, Table)]
    assert titles == [
        "MMS Exposure Audit",
        "Session Home / Settings",
        "Process Env Exposed To CLI",
        "Session Settings Exposure",
    ]
    summary = console.items[0]
    assert ("cli", "codex") in [row for row, _kwargs in summary.rows]
    assert not any(row[0] == "fake_upstream" for row, _kwargs in summary.rows)
    assert any("safe" in str(item) for item in console.items)
