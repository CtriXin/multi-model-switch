from __future__ import annotations

import json
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
    monkeypatch.setenv("MMS_FAKE_UPSTREAM", "1")

    mms_core.handle_logs_command(["--tail", "7"])
    out = capsys.readouterr().out

    assert "fake-upstream log --tail 7" in out
    assert "guard status" in out
