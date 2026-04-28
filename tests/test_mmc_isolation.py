from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest


def _write_proxy_routes(path: Path, routes: list[dict]) -> Path:
    path.write_text(
        json.dumps({"schema_version": 1, "routes": routes}),
        encoding="utf-8",
    )
    return path


def test_bootstrap_account_state_starts_clean_without_legacy_import(monkeypatch, tmp_path):
    import mmc_core

    config_root = tmp_path / "mmc-config"
    monkeypatch.setenv("MMC_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))

    mmc_core._bootstrap_account_state()

    state = json.loads(mmc_core._account_state_path().read_text(encoding="utf-8"))
    settings = json.loads(mmc_core._account_settings_path().read_text(encoding="utf-8"))

    assert "userID" not in state
    assert "claudeAiOauth" not in state
    assert "oauthAccount" not in state
    assert "mcpServers" not in state
    assert settings == {}


def test_import_legacy_auth_state_only_keeps_auth_and_theme(monkeypatch, tmp_path):
    import mmc_core

    config_root = tmp_path / "mmc-config"
    source_home = tmp_path / "source-home"
    (source_home / ".claude").mkdir(parents=True)

    monkeypatch.setenv("MMC_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))

    (source_home / ".claude.json").write_text(
        json.dumps(
            {
                "userID": "device-1",
                "claudeAiOauth": {
                    "accessToken": "token-1",
                    "refreshToken": "refresh-1",
                    "expiresAt": "2026-04-17T00:00:00+00:00",
                },
                "oauthAccount": {
                    "displayName": "demo",
                    "emailAddress": "demo@example.com",
                },
                "mcpServers": {
                    "mindkeeper": {"command": "mk", "args": ["bad"]},
                    "hive": {"command": "hive"},
                },
                "projects": {
                    "/tmp/project-a": {
                        "hasTrustDialogAccepted": True,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (source_home / ".claude" / "settings.json").write_text(
        json.dumps({"theme": "dark", "hooks": {"preToolUse": [{"matcher": "*"}]}}),
        encoding="utf-8",
    )

    mmc_core._import_legacy_auth_state(str(source_home))

    state = json.loads(mmc_core._account_state_path().read_text(encoding="utf-8"))
    settings = json.loads(mmc_core._account_settings_path().read_text(encoding="utf-8"))

    assert state["userID"] == "device-1"
    assert state["claudeAiOauth"]["accessToken"] == "token-1"
    assert state["oauthAccount"]["emailAddress"] == "demo@example.com"
    assert "mcpServers" not in state
    assert "projects" not in state
    assert settings == {"theme": "dark"}


def test_build_session_settings_only_uses_repo_allowlisted_hooks(monkeypatch, tmp_path):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))

    settings = mmc_core._build_session_settings()
    hooks = settings["hooks"]
    commands = [
        hook["command"]
        for groups in hooks.values()
        for group in groups
        for hook in group["hooks"]
    ]

    assert set(hooks.keys()) == {"PreToolUse", "PostCompact"}
    assert any(group["matcher"] == "Bash" for group in hooks["PreToolUse"])
    assert any(group["matcher"] == "Read" for group in hooks["PreToolUse"])
    assert hooks["PostCompact"][0]["matcher"] == ""
    assert any("rtk-rewrite.sh" in command for command in commands)
    assert any("READ_ONCE_DIFF=1" in command and "read-once-hook.sh" in command for command in commands)
    assert any("read-once-compact.sh" in command for command in commands)
    assert all("agentim" not in command for command in commands)
    assert all("hive-compact-hook.sh" not in command for command in commands)
    assert all("claude-map-auto-index.sh" not in command for command in commands)
    assert all("claude-feishu" not in command for command in commands)


def test_prepare_session_tree_uses_explicit_workspace(monkeypatch, tmp_path):
    import mmc_core
    from mmc_project_store import claude_raw_entry_path, read_slot_marker

    config_root = tmp_path / "mmc-config"
    workspace = tmp_path / "workspace"
    other_cwd = tmp_path / "other-cwd"
    session_home = tmp_path / "session-home"
    workspace.mkdir()
    other_cwd.mkdir()

    monkeypatch.setenv("MMC_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    monkeypatch.chdir(other_cwd)

    mmc_core._prepare_session_tree(session_home, str(workspace))

    marker = read_slot_marker(session_home)
    history_link = session_home / ".claude" / "history.jsonl"

    assert marker["cwd"] == str(workspace.resolve())
    assert os.path.islink(history_link)
    assert os.path.realpath(history_link) == str(claude_raw_entry_path("history.jsonl", str(workspace)).resolve())


def test_build_process_env_uses_private_path_and_tmpdir(monkeypatch, tmp_path):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/ssh.sock")
    monkeypatch.setenv("TMPDIR", "/tmp/parent")
    monkeypatch.setenv("PYTHONPATH", "/tmp/python")

    claude_bin = tmp_path / "bin" / "claude"
    node_bin = tmp_path / "bin" / "node"
    claude_bin.parent.mkdir(parents=True)
    claude_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    node_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    claude_bin.chmod(0o755)
    node_bin.chmod(0o755)

    session_home = tmp_path / "session-home"
    args = argparse.Namespace(
        proxy="http://127.0.0.1:7890",
        no_proxy="127.0.0.1,localhost",
        lang="zh_CN.UTF-8",
        lc_all="zh_CN.UTF-8",
        lc_ctype="zh_CN.UTF-8",
        lc_messages="zh_CN.UTF-8",
        tz="America/Los_Angeles",
        force_ipv4=False,
        allow_dir=[],
        bypass=False,
        set_env=[
            "ANTHROPIC_MODEL=claude-sonnet-4-6",
            "MMS_MODEL_NAME=claude-sonnet-4-6",
            "OPENAI_API_KEY=sk-should-drop",
            "BAD=value",
        ],
        claude_bin=str(claude_bin),
        node_bin=str(node_bin),
    )

    monkeypatch.setattr(
        mmc_core,
        "_collect_safe_tool_path_dirs",
        lambda _names: ["/opt/homebrew/bin", "/Users/demo/.cargo/bin"],
    )

    env = mmc_core._build_process_env(args, session_home)
    path_parts = env["PATH"].split(os.pathsep)

    assert env["ANTHROPIC_MODEL"] == "claude-sonnet-4-6"
    assert env["MMS_MODEL_NAME"] == "claude-sonnet-4-6"
    assert env["HTTP_PROXY"] == "http://127.0.0.1:7890"
    assert env["NO_PROXY"] == "127.0.0.1,localhost"
    assert env["HOME"] == str(session_home)
    assert env["MMC_REAL_HOME"] == str((tmp_path / "real-home").resolve())
    assert env["TMPDIR"].startswith(str((tmp_path / "mmc-config" / "tmp").resolve()))
    assert env["XDG_RUNTIME_DIR"] == str((session_home / ".runtime").resolve())
    assert env["NPM_CONFIG_CACHE"] == str((session_home / ".cache" / "npm").resolve())
    assert env["NODE_GYP_DIR"] == str((session_home / ".cache" / "node-gyp").resolve())
    assert path_parts[0] == str((session_home / ".mmc" / "bin").resolve())
    assert path_parts[1:3] == ["/opt/homebrew/bin", "/Users/demo/.cargo/bin"]
    assert env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"
    assert env["API_TIMEOUT_MS"] == "3000000"
    assert Path(env["XDG_RUNTIME_DIR"]).is_dir()
    assert Path(env["NPM_CONFIG_CACHE"]).is_dir()
    assert Path(env["NODE_GYP_DIR"]).is_dir()
    assert "CLAUDE_CODE_ATTRIBUTION_HEADER" not in env
    assert "OPENAI_API_KEY" not in env
    assert "BAD" not in env
    assert "SSH_AUTH_SOCK" not in env
    assert "PYTHONPATH" not in env


def test_build_process_env_applies_proxy_override(monkeypatch, tmp_path):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))

    claude_bin = tmp_path / "bin" / "claude"
    node_bin = tmp_path / "bin" / "node"
    claude_bin.parent.mkdir(parents=True)
    claude_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    node_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    claude_bin.chmod(0o755)
    node_bin.chmod(0o755)

    args = argparse.Namespace(
        proxy="http://107.0.0.1:7890",
        no_proxy="api.anthropic.com",
        lang="",
        lc_all="",
        lc_ctype="",
        lc_messages="",
        tz="",
        force_ipv4=False,
        allow_dir=[],
        bypass=False,
        set_env=[],
        claude_bin=str(claude_bin),
        node_bin=str(node_bin),
    )

    env = mmc_core._build_process_env(
        args,
        tmp_path / "session-home",
        proxy_url_override="http://127.0.0.1:18080",
        no_proxy_override="127.0.0.1,localhost",
    )

    assert env["HTTP_PROXY"] == "http://127.0.0.1:18080"
    assert env["HTTPS_PROXY"] == "http://127.0.0.1:18080"
    assert env["NO_PROXY"] == "127.0.0.1,localhost"


def test_build_process_env_blocks_force_ipv4_injection(monkeypatch, tmp_path):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))

    claude_bin = tmp_path / "bin" / "claude"
    node_bin = tmp_path / "bin" / "node"
    claude_bin.parent.mkdir(parents=True)
    claude_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    node_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    claude_bin.chmod(0o755)
    node_bin.chmod(0o755)

    args = argparse.Namespace(
        proxy="http://127.0.0.1:7890",
        no_proxy="",
        lang="",
        lc_all="",
        lc_ctype="",
        lc_messages="",
        tz="",
        force_ipv4=True,
        allow_dir=[],
        bypass=False,
        set_env=[],
        claude_bin=str(claude_bin),
        node_bin=str(node_bin),
    )

    with pytest.raises(SystemExit, match="force_ipv4"):
        mmc_core._build_process_env(args, tmp_path / "session-home")


def test_ensure_not_nested_session_blocks_launch_inside_existing_session(monkeypatch, tmp_path):
    import mmc_core

    nested_home = tmp_path / "nested-session"
    monkeypatch.setenv("MMC_SESSION_HOME", str(nested_home))

    with pytest.raises(SystemExit, match="当前已在隔离 session 内"):
        mmc_core._ensure_not_nested_session("mmc run")


def test_proxy_guard_blocks_missing_proxy(monkeypatch):
    import mmc_core

    args = argparse.Namespace(proxy="", route_id="", routes_file="")
    with pytest.raises(SystemExit, match="loopback proxy route"):
        mmc_core._enforce_proxy_guard_or_exit(args)


def test_resolve_proxy_launch_target_rejects_non_loopback_proxy(monkeypatch):
    import mmc_core

    args = argparse.Namespace(proxy="http://10.0.0.8:8080", route_id="", routes_file="")
    with pytest.raises(SystemExit, match="loopback"):
        mmc_core._resolve_proxy_launch_target(args)


def test_resolve_proxy_launch_target_uses_route_file_and_binding(monkeypatch, tmp_path):
    import mmc_core

    routes_file = _write_proxy_routes(
        tmp_path / "proxy-routes.json",
        [
            {
                "id": "route-a",
                "purpose": "oauth_claude",
                "local_proxy_url": "http://127.0.0.1:31001",
                "sticky_account_binding": {"account_uuid": "acc-1", "email": "demo@example.com"},
                "expected_exit_ip": "1.2.3.4",
            }
        ],
    )
    monkeypatch.setattr(
        mmc_core,
        "_current_account_owner_metadata",
        lambda: {
            "account_home": "/tmp/mmc",
            "owner_user_id": "",
            "owner_account_uuid": "acc-1",
            "owner_email": "demo@example.com",
        },
    )

    resolved = mmc_core._resolve_proxy_launch_target(
        argparse.Namespace(proxy="", route_id="route-a", routes_file=str(routes_file))
    )

    assert resolved["id"] == "route-a"
    assert resolved["proxy_url"] == "http://127.0.0.1:31001"
    assert resolved["expected_exit_ip"] == "1.2.3.4"
    assert resolved["effective_no_proxy"] == "127.0.0.1,localhost"


def test_resolve_proxy_launch_target_blocks_route_drift_for_bound_account(monkeypatch, tmp_path):
    import mmc_core

    routes_file = _write_proxy_routes(
        tmp_path / "proxy-routes.json",
        [
            {
                "id": "route-a",
                "purpose": "oauth_claude",
                "local_proxy_url": "http://127.0.0.1:31001",
                "sticky_account_binding": {"email": "demo@example.com"},
                "expected_exit_ip": "1.2.3.4",
            },
            {
                "id": "route-b",
                "purpose": "oauth_claude",
                "local_proxy_url": "http://127.0.0.1:31002",
                "sticky_account_binding": {"email": "other@example.com"},
                "expected_exit_ip": "2.2.2.2",
            },
        ],
    )
    monkeypatch.setattr(
        mmc_core,
        "_current_account_owner_metadata",
        lambda: {
            "account_home": "/tmp/mmc",
            "owner_user_id": "",
            "owner_account_uuid": "",
            "owner_email": "demo@example.com",
        },
    )

    with pytest.raises(SystemExit, match="已固定到 route `route-a`"):
        mmc_core._resolve_proxy_launch_target(
            argparse.Namespace(proxy="http://127.0.0.1:31002", route_id="", routes_file=str(routes_file))
        )


def test_local_proxy_guard_blocks_no_proxy_conflict():
    import mmc_core

    guard = mmc_core._build_local_proxy_guard("http://127.0.0.1:7890", "api.anthropic.com,localhost")

    assert guard["status"] == "blocked"
    assert "NO_PROXY" in guard["block_reason"]


def test_local_proxy_guard_blocks_socks5_local_dns():
    import mmc_core

    guard = mmc_core._build_local_proxy_guard("socks5://127.0.0.1:7890", "")

    assert guard["status"] == "blocked"
    assert "DNS" in guard["block_reason"]


def test_local_proxy_guard_blocks_no_proxy_wildcard():
    import mmc_core

    guard = mmc_core._build_local_proxy_guard("http://127.0.0.1:7890", "*")

    assert guard["status"] == "blocked"
    assert "*" in guard["no_proxy_conflicts"]


def test_local_proxy_guard_blocks_when_exit_ip_cannot_be_pinned(monkeypatch):
    import mmc_core

    monkeypatch.setattr(mmc_core, "_run_proxy_probe", lambda *_args, **_kwargs: {"ok": True, "detail": ""})
    monkeypatch.setattr(
        mmc_core,
        "_run_exit_ip_probe",
        lambda *_args, **_kwargs: {"ok": False, "detail": "checkip failed", "exit_ip": ""},
    )

    guard = mmc_core._build_local_proxy_guard("http://127.0.0.1:7890", "")

    assert guard["status"] == "blocked"
    assert guard["block_reason"] == "无法固定 proxy 出口 IP"


def test_run_proxy_probe_returns_structured_error_when_subprocess_blows_up(monkeypatch):
    import mmc_core

    monkeypatch.setattr(mmc_core.shutil, "which", lambda _name: "/usr/bin/curl")
    monkeypatch.setattr(
        mmc_core.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("curl exploded")),
    )

    result = mmc_core._run_proxy_probe("http://127.0.0.1:7890", "https://claude.ai")

    assert result["ok"] is False
    assert "OSError" in result["detail"]


def test_run_exit_ip_probe_returns_structured_error_when_subprocess_blows_up(monkeypatch):
    import mmc_core

    monkeypatch.setattr(mmc_core.shutil, "which", lambda _name: "/usr/bin/curl")
    monkeypatch.setattr(
        mmc_core.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = mmc_core._run_exit_ip_probe("http://127.0.0.1:7890")

    assert result["ok"] is False
    assert "RuntimeError" in result["detail"]
    assert result["exit_ip"] == ""


def test_local_proxy_guard_blocks_when_exit_ip_mismatches_expected(monkeypatch):
    import mmc_core

    monkeypatch.setattr(mmc_core, "_run_proxy_probe", lambda *_args, **_kwargs: {"ok": True, "detail": ""})
    monkeypatch.setattr(
        mmc_core,
        "_run_exit_ip_probe",
        lambda *_args, **_kwargs: {"ok": True, "detail": "", "exit_ip": "2.2.2.2"},
    )

    guard = mmc_core._build_local_proxy_guard(
        "http://127.0.0.1:7890",
        "127.0.0.1,localhost",
        expected_exit_ip="1.1.1.1",
    )

    assert guard["status"] == "blocked"
    assert "expected 1.1.1.1, got 2.2.2.2" in guard["block_reason"]


def test_proxy_guard_rejects_pid_reuse_when_start_fingerprint_changes(monkeypatch, tmp_path):
    import mmc_core

    session_home = tmp_path / "session-home"
    session_home.mkdir()
    mmc_core._write_json(
        mmc_core._session_pid_stamp_path(session_home),
        {
            "pid": 4321,
            "lstart": "Thu Apr 16 12:00:00 2026",
            "command": "python mmc_core.py run",
        },
    )

    monkeypatch.setattr(mmc_core, "_pid_alive", lambda _pid: True)
    monkeypatch.setattr(
        mmc_core,
        "_read_pid_ps_value",
        lambda _pid, field: {
            "lstart": "Thu Apr 16 12:05:00 2026",
            "command": "/usr/bin/python3 unrelated.py",
        }[field],
    )

    assert mmc_core._slot_pid_is_active(session_home, 4321) is False


def test_overlay_project_scoped_resume_state_only_uses_owned_sessions(monkeypatch, tmp_path):
    import mmc_core

    config_root = tmp_path / "mmc-config"
    workspace = tmp_path / "repo"
    workspace.mkdir()

    monkeypatch.setenv("MMC_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    mmc_core._bootstrap_account_state()
    mmc_core._write_json(
        mmc_core._account_state_path(),
        {
            "userID": "device-1",
            "oauthAccount": {
                "accountUuid": "acct-1",
                "emailAddress": "demo@example.com",
            },
        },
    )

    account_home = str(mmc_core._account_home())
    monkeypatch.setattr(
        mmc_core,
        "list_indexed_sessions",
        lambda: [
            {
                "session_id": "session-foreign",
                "project_path": str(workspace.resolve()),
                "last_active_at": "2026-04-16T10:00:00+00:00",
                "account_home": account_home,
                "owner_account_uuid": "acct-2",
            },
            {
                "session_id": "session-owned",
                "project_path": str(workspace.resolve()),
                "last_active_at": "2026-04-16T09:00:00+00:00",
                "account_home": account_home,
                "owner_account_uuid": "acct-1",
            },
        ],
    )

    payload = mmc_core._overlay_project_scoped_resume_state({}, str(workspace))

    assert payload["projects"][str(workspace.resolve())]["lastSessionId"] == "session-owned"


def test_run_resume_rejects_foreign_owner_session(monkeypatch, tmp_path):
    import mmc_core

    config_root = tmp_path / "mmc-config"
    workspace = tmp_path / "repo"
    workspace.mkdir()

    monkeypatch.setenv("MMC_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    mmc_core._bootstrap_account_state()
    mmc_core._write_json(
        mmc_core._account_state_path(),
        {
            "userID": "device-1",
            "oauthAccount": {
                "accountUuid": "acct-1",
                "emailAddress": "demo@example.com",
            },
        },
    )

    monkeypatch.setattr(
        mmc_core,
        "list_indexed_sessions",
        lambda: [
            {
                "session_id": "session-foreign",
                "project_path": str(workspace.resolve()),
                "last_active_at": "2026-04-16T10:00:00+00:00",
                "account_home": str(mmc_core._account_home()),
                "owner_account_uuid": "acct-2",
            }
        ],
    )

    called = []
    monkeypatch.setattr(
        mmc_core,
        "_run_claude",
        lambda *_args, **_kwargs: called.append(True) or 0,
    )

    args = argparse.Namespace(session_ref="1", workspace="")
    exit_code = mmc_core._run_resume(args)

    assert exit_code == 1
    assert called == []


def test_session_index_reconciles_by_child_pid(monkeypatch, tmp_path):
    import mmc_session_index
    from mmc_project_store import claude_raw_entry_path

    config_root = tmp_path / "mmc-config"
    monkeypatch.setenv("MMC_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))

    workspace = tmp_path / "repo"
    workspace.mkdir()

    payload = mmc_session_index.record_claude_session_start(
        cwd=str(workspace),
        pid=101,
        slot_home=str(tmp_path / "slot"),
    )
    mmc_session_index.bind_claude_session_process(
        cwd=str(workspace),
        pid=101,
        child_pid=9876,
        launch_nonce="slot-1",
    )

    started_at_ms = int(mmc_session_index._payload_started_at_ms(payload) or 0)
    raw_sessions = claude_raw_entry_path("sessions", str(workspace))
    (raw_sessions / "session-a.json").write_text(
        json.dumps(
            {
                "pid": 1111,
                "sessionId": "session-wrong",
                "cwd": str(workspace.resolve()),
                "startedAt": started_at_ms + 1,
            }
        ),
        encoding="utf-8",
    )
    (raw_sessions / "session-b.json").write_text(
        json.dumps(
            {
                "pid": 9876,
                "sessionId": "session-match",
                "cwd": str(workspace.resolve()),
                "startedAt": started_at_ms + 2,
            }
        ),
        encoding="utf-8",
    )

    result = mmc_session_index.finalize_claude_session(
        cwd=str(workspace),
        pid=101,
        exit_code=0,
    )

    assert result["session_id"] == "session-match"


def test_finalize_session_index_keeps_pid_placeholder_when_raw_session_missing(monkeypatch, tmp_path):
    import mmc_session_index

    config_root = tmp_path / "mmc-config"
    monkeypatch.setenv("MMC_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))

    workspace = tmp_path / "repo"
    workspace.mkdir()

    mmc_session_index.record_claude_session_start(
        cwd=str(workspace),
        pid=404,
        slot_home=str(tmp_path / "slot"),
    )

    result = mmc_session_index.finalize_claude_session(
        cwd=str(workspace),
        pid=404,
        exit_code=0,
    )

    target = mmc_session_index._session_state_path(str(workspace), "pid-404")
    assert result["session_id"] == "pid-404"
    assert target.exists() is True
    stored = json.loads(target.read_text(encoding="utf-8"))
    assert stored["session_id"] == "pid-404"
    assert stored["exit_code"] == 0
    assert stored["last_active_at"]


def test_finalize_session_index_recovers_session_id_from_history_when_raw_session_missing(monkeypatch, tmp_path):
    import mmc_session_index
    from mmc_project_store import claude_raw_entry_path

    config_root = tmp_path / "mmc-config"
    monkeypatch.setenv("MMC_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))

    workspace = tmp_path / "repo"
    workspace.mkdir()

    payload = mmc_session_index.record_claude_session_start(
        cwd=str(workspace),
        pid=505,
        slot_home=str(tmp_path / "slot"),
    )
    mmc_session_index.bind_claude_session_process(
        cwd=str(workspace),
        pid=505,
        child_pid=9505,
        launch_nonce="slot-505",
    )
    started_at_ms = int(mmc_session_index._payload_started_at_ms(payload) or 0)
    history_path = claude_raw_entry_path("history.jsonl", str(workspace))
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "display": "/login",
                        "timestamp": started_at_ms + 10,
                        "project": str(workspace.resolve()),
                        "sessionId": "session-from-history",
                    }
                ),
                json.dumps(
                    {
                        "display": "hi",
                        "timestamp": started_at_ms + 20,
                        "project": str(workspace.resolve()),
                        "sessionId": "session-from-history",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = mmc_session_index.finalize_claude_session(
        cwd=str(workspace),
        pid=505,
        exit_code=0,
    )

    target = mmc_session_index._session_state_path(str(workspace), "session-from-history")
    assert result["session_id"] == "session-from-history"
    assert target.exists() is True
    stored = json.loads(target.read_text(encoding="utf-8"))
    assert stored["session_id"] == "session-from-history"
    assert stored["exit_code"] == 0


def test_session_index_write_json_uses_locked_atomic_write(monkeypatch, tmp_path):
    import mmc_session_index

    seen = []

    @contextmanager
    def _fake_lock(path):
        seen.append(("lock", Path(path)))
        yield

    monkeypatch.setattr(mmc_session_index, "locked_state_file", _fake_lock)
    monkeypatch.setattr(
        mmc_session_index,
        "atomic_write_json",
        lambda path, payload, mode=None, indent=2: seen.append(
            ("write", Path(path), payload["session_id"], mode, indent)
        ),
    )

    target = tmp_path / "index" / "session.json"
    mmc_session_index._write_json(target, {"session_id": "session-1"})

    assert seen == [
        ("lock", target),
        ("write", target, "session-1", 0o600, 2),
    ]


def test_cleanup_stale_session_slots_removes_matching_tmpdir(monkeypatch, tmp_path):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    monkeypatch.setattr(mmc_core, "_pid_alive", lambda _pid: False)

    sessions_dir = mmc_core._session_slots_dir()
    stale_session_home = sessions_dir / "4321-stale"
    stale_session_home.mkdir(parents=True)
    (stale_session_home / "marker").write_text("x", encoding="utf-8")

    stale_tmp = mmc_core._session_tmp_path(stale_session_home)
    stale_tmp.mkdir(parents=True)
    (stale_tmp / "socket").write_text("x", encoding="utf-8")

    active = mmc_core._cleanup_stale_session_slots(sessions_dir)

    assert active == []
    assert not stale_session_home.exists()
    assert not stale_tmp.exists()


def test_project_store_metadata_and_slot_marker_use_locked_atomic_write(monkeypatch, tmp_path):
    import mmc_project_store

    seen = []

    @contextmanager
    def _fake_lock(path):
        seen.append(("lock", Path(path)))
        yield

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    monkeypatch.setattr(mmc_project_store, "locked_state_file", _fake_lock)
    monkeypatch.setattr(
        mmc_project_store,
        "atomic_write_json",
        lambda path, payload, mode=None, indent=2: seen.append(
            ("write", Path(path), sorted(payload.keys()), mode, indent)
        ),
    )

    session_home = tmp_path / "session-home"
    workspace = tmp_path / "repo"
    session_home.mkdir()
    workspace.mkdir()

    mmc_project_store.write_slot_marker(
        session_home,
        cwd=str(workspace),
        project_key_value="demo",
        account_home=str(tmp_path / "account"),
    )
    mmc_project_store.ensure_claude_project_store(str(workspace))

    slot_marker_path = mmc_project_store.slot_marker_path(session_home)
    meta_path = mmc_project_store.claude_project_metadata_path(str(workspace))

    assert ("lock", slot_marker_path) in seen
    assert ("write", slot_marker_path, ["account_home", "cwd", "project_key", "runtime_kind", "written_at"], 0o600, 2) in seen
    assert ("lock", meta_path) in seen
    assert ("write", meta_path, ["canonical_path", "created_at", "display_name", "project_key"], 0o600, 2) in seen


def test_sync_session_state_persists_project_scoped_state_without_top_level_mcp_servers(monkeypatch, tmp_path):
    import mmc_core

    config_root = tmp_path / "mmc-config"
    monkeypatch.setenv("MMC_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))

    workspace = tmp_path / "repo"
    workspace.mkdir()
    session_home = tmp_path / "session-home"
    (session_home / ".claude").mkdir(parents=True)

    mmc_core._bootstrap_account_state()
    (session_home / ".claude.json").write_text(
        json.dumps(
            {
                "userID": "device-1",
                "oauthAccount": {"emailAddress": "demo@example.com"},
                "claudeAiOauth": {"accessToken": "tok-1"},
                "mcpServers": {"demo": {"command": "demo"}},
                "projects": {
                    str(workspace.resolve()): {
                        "allowedTools": ["Bash(ls:*)", "Read"],
                        "mcpContextUris": ["mcp://mindkeeper/context"],
                        "enabledMcpjsonServers": ["mindkeeper"],
                        "disabledMcpjsonServers": ["hive"],
                        "hasTrustDialogAccepted": True,
                        "projectOnboardingSeenCount": 2,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (session_home / ".claude" / "settings.json").write_text(
        json.dumps({"theme": "dark"}),
        encoding="utf-8",
    )

    mmc_core._sync_session_state_to_account_home(session_home)

    state = json.loads(mmc_core._account_state_path().read_text(encoding="utf-8"))
    project_state = state["projects"][str(workspace.resolve())]

    assert state["userID"] == "device-1"
    assert state["oauthAccount"]["emailAddress"] == "demo@example.com"
    assert state["claudeAiOauth"]["accessToken"] == "tok-1"
    assert "mcpServers" not in state
    assert project_state["allowedTools"] == ["Bash(ls:*)", "Read"]
    assert project_state["mcpContextUris"] == ["mcp://mindkeeper/context"]
    assert project_state["enabledMcpjsonServers"] == ["mindkeeper"]
    assert project_state["disabledMcpjsonServers"] == ["hive"]
    assert project_state["projectOnboardingSeenCount"] == 2


def test_finalize_session_cleans_session_home_and_tmpdir(monkeypatch, tmp_path):
    import mmc_core
    from mmc_project_store import write_slot_marker

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))

    session_home = tmp_path / "session-home"
    (session_home / ".claude").mkdir(parents=True)
    session_tmp = mmc_core._session_tmp_path(session_home)
    session_tmp.mkdir(parents=True)
    (session_home / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
    (session_tmp / "artifact.sock").write_text("x", encoding="utf-8")
    write_slot_marker(session_home, cwd=str(tmp_path / "repo"), project_key_value="demo", account_home=str(tmp_path))

    seen = {"sync": 0, "finalize": 0}
    monkeypatch.setattr(
        mmc_core,
        "_sync_session_state_to_account_home",
        lambda _path: seen.__setitem__("sync", seen["sync"] + 1),
    )
    monkeypatch.setattr(
        mmc_core,
        "finalize_claude_session",
        lambda **_kwargs: seen.__setitem__("finalize", seen["finalize"] + 1),
    )

    mmc_core._finalize_session(session_home, exit_code=0)

    assert seen == {"sync": 1, "finalize": 1}
    assert not session_home.exists()
    assert not session_tmp.exists()


def test_run_claude_finalizes_session_on_keyboard_interrupt(monkeypatch, tmp_path):
    import mmc_core

    workspace = tmp_path / "repo"
    workspace.mkdir()
    session_home = tmp_path / "session-home"
    finalized = []
    stopped = []

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    monkeypatch.setattr(mmc_core, "_bootstrap_account_state", lambda: None)
    monkeypatch.setattr(
        mmc_core,
        "_resolve_proxy_launch_target",
        lambda _args: {
            "proxy_url": "http://127.0.0.1:31001",
            "expected_exit_ip": "",
            "effective_no_proxy": "127.0.0.1,localhost",
        },
    )
    monkeypatch.setattr(mmc_core, "_enforce_proxy_guard_or_exit", lambda _plan: None)
    monkeypatch.setattr(mmc_core, "_reserve_session_home", lambda: (session_home, 0, 1))
    monkeypatch.setattr(mmc_core, "_prepare_session_tree", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mmc_core, "_link_keychains_only", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mmc_core, "_build_session_state", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(mmc_core, "_build_session_settings", lambda: {})
    monkeypatch.setattr(mmc_core, "_write_json", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mmc_core, "_start_session_proxy_guard", lambda _proxy, **_kwargs: _FakeGuard(stopped))
    monkeypatch.setattr(mmc_core, "_build_process_env", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(mmc_core, "_build_claude_cmd", lambda *_args, **_kwargs: ["claude"])
    monkeypatch.setattr(
        mmc_core,
        "_finalize_session",
        lambda session_path, *, exit_code, stale_cleanup=False: finalized.append(
            (session_path, exit_code, stale_cleanup)
        ),
    )
    monkeypatch.setattr(mmc_core, "bind_claude_session_process", lambda **_kwargs: None)
    monkeypatch.setattr(mmc_core.signal, "getsignal", lambda _signum: None)
    monkeypatch.setattr(mmc_core.signal, "signal", lambda _signum, _handler: None)

    class _FakeChild:
        pid = 4321

        def poll(self):
            return None

        def send_signal(self, _signum):
            return None

        def wait(self, timeout=None):
            raise KeyboardInterrupt

    monkeypatch.setattr(mmc_core.subprocess, "Popen", lambda *_args, **_kwargs: _FakeChild())

    args = argparse.Namespace(
        workspace=str(workspace),
        proxy="http://127.0.0.1:7890",
        no_proxy="",
        lang="",
        lc_all="",
        lc_ctype="",
        lc_messages="",
        tz="",
        force_ipv4=False,
        allow_dir=[],
        bypass=False,
        set_env=[],
        claude_bin="",
        node_bin="",
    )

    exit_code = mmc_core._run_claude(args)

    assert exit_code == 130
    assert finalized == [(session_home, 130, False)]
    assert stopped == [True]


def test_run_claude_kills_child_when_local_proxy_guard_fails(monkeypatch, tmp_path):
    import mmc_core

    workspace = tmp_path / "repo"
    workspace.mkdir()
    session_home = tmp_path / "session-home"
    finalized = []
    stopped = []
    env_call = {}
    popen_kwargs = {}

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    monkeypatch.setattr(mmc_core, "_bootstrap_account_state", lambda: None)
    monkeypatch.setattr(
        mmc_core,
        "_resolve_proxy_launch_target",
        lambda _args: {
            "proxy_url": "http://127.0.0.1:31001",
            "expected_exit_ip": "",
            "effective_no_proxy": "127.0.0.1,localhost",
        },
    )
    monkeypatch.setattr(mmc_core, "_enforce_proxy_guard_or_exit", lambda _plan: None)
    monkeypatch.setattr(mmc_core, "_reserve_session_home", lambda: (session_home, 0, 1))
    monkeypatch.setattr(mmc_core, "_prepare_session_tree", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mmc_core, "_link_keychains_only", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mmc_core, "_build_session_state", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(mmc_core, "_build_session_settings", lambda: {})
    monkeypatch.setattr(mmc_core, "_write_json", lambda *_args, **_kwargs: None)
    fake_guard = _FakeGuard(stopped, failure_reason="proxy heartbeat failed for claude: HTTP 000")
    monkeypatch.setattr(mmc_core, "_start_session_proxy_guard", lambda _proxy, **_kwargs: fake_guard)
    monkeypatch.setattr(
        mmc_core,
        "_build_process_env",
        lambda *_args, **kwargs: env_call.update(kwargs) or {},
    )
    monkeypatch.setattr(mmc_core, "_build_claude_cmd", lambda *_args, **_kwargs: ["claude"])
    monkeypatch.setattr(
        mmc_core,
        "_finalize_session",
        lambda session_path, *, exit_code, stale_cleanup=False: finalized.append(
            (session_path, exit_code, stale_cleanup)
        ),
    )
    monkeypatch.setattr(mmc_core, "bind_claude_session_process", lambda **_kwargs: None)
    monkeypatch.setattr(mmc_core.signal, "getsignal", lambda _signum: None)
    monkeypatch.setattr(mmc_core.signal, "signal", lambda _signum, _handler: None)

    class _FakeChild:
        pid = 9876

        def __init__(self):
            self.returncode = None
            self.signals = []
            self.wait_calls = 0

        def poll(self):
            return self.returncode

        def send_signal(self, signum):
            self.signals.append(signum)
            self.returncode = 143 if signum == signal.SIGTERM else 137

        def wait(self, timeout=None):
            if self.returncode is not None:
                return self.returncode
            self.wait_calls += 1
            fake_guard.failed_event.set()
            raise subprocess.TimeoutExpired(cmd="claude", timeout=timeout)

    child = _FakeChild()
    monkeypatch.setattr(
        mmc_core.subprocess,
        "Popen",
        lambda *_args, **kwargs: popen_kwargs.update(kwargs) or child,
    )

    args = argparse.Namespace(
        workspace=str(workspace),
        proxy="http://127.0.0.1:31001",
        no_proxy="",
        lang="",
        lc_all="",
        lc_ctype="",
        lc_messages="",
        tz="",
        force_ipv4=False,
        allow_dir=[],
        bypass=False,
        set_env=[],
        claude_bin="",
        node_bin="",
    )

    exit_code = mmc_core._run_claude(args)

    assert exit_code != 0
    assert signal.SIGTERM in child.signals
    assert env_call["proxy_url_override"] == fake_guard.local_proxy_url
    assert env_call["no_proxy_override"] == "127.0.0.1,localhost"
    assert popen_kwargs["start_new_session"] is (os.name == "posix")
    assert finalized == [(session_home, exit_code, False)]
    assert stopped == [True]


def test_terminate_child_process_restores_tty_after_force_kill(monkeypatch):
    import mmc_core

    restored = []
    signaled = []

    monkeypatch.setattr(mmc_core, "_restore_tty_state", lambda: restored.append(True))

    class _FakeChild:
        def __init__(self):
            self.returncode = None

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            if self.returncode is not None:
                return self.returncode
            raise subprocess.TimeoutExpired(cmd="claude", timeout=timeout)

    child = _FakeChild()

    def _fake_signal(target, signum):
        signaled.append(signum)
        if signum == signal.SIGKILL:
            target.returncode = 137

    monkeypatch.setattr(mmc_core, "_signal_child_process", _fake_signal)

    mmc_core._terminate_child_process(child, grace_timeout_sec=0.2)

    assert signaled[0] == signal.SIGTERM
    assert signaled[-1] == signal.SIGKILL
    assert restored == [True]


@pytest.mark.skipif(os.name != "posix", reason="process group signaling is POSIX-only")
def test_terminate_child_process_kills_spawned_process_group(tmp_path):
    import mmc_core

    grandchild_pid_file = tmp_path / "grandchild.pid"
    launcher_script = tmp_path / "spawn_group.py"
    launcher_script.write_text(
        "\n".join(
            [
                "import pathlib",
                "import subprocess",
                "import sys",
                "import time",
                "",
                "pid_file = pathlib.Path(sys.argv[1])",
                "grandchild = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])",
                "pid_file.write_text(str(grandchild.pid), encoding='utf-8')",
                "time.sleep(120)",
            ]
        ),
        encoding="utf-8",
    )

    child = subprocess.Popen(
        [sys.executable, str(launcher_script), str(grandchild_pid_file)],
        start_new_session=True,
    )
    grandchild_pid = None
    try:
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if grandchild_pid_file.exists():
                grandchild_pid = int(grandchild_pid_file.read_text(encoding="utf-8").strip())
                break
            time.sleep(0.05)
        assert grandchild_pid is not None
        setattr(child, "_mmc_process_group_id", os.getpgid(child.pid))

        mmc_core._terminate_child_process(child, grace_timeout_sec=0.2)

        assert child.poll() is not None
        deadline = time.time() + 5.0
        while time.time() < deadline:
            stat = mmc_core._read_pid_ps_value(grandchild_pid, "stat")
            if not stat or stat.startswith("Z"):
                break
            time.sleep(0.05)
        stat = mmc_core._read_pid_ps_value(grandchild_pid, "stat")
        assert not stat or stat.startswith("Z")
    finally:
        if child.poll() is None:
            try:
                os.killpg(os.getpgid(child.pid), signal.SIGKILL)
            except OSError:
                pass
            try:
                child.wait(timeout=1.0)
            except Exception:
                pass
        if grandchild_pid:
            try:
                os.kill(grandchild_pid, signal.SIGKILL)
            except OSError:
                pass


def test_handle_session_prune_removes_stale_slots_and_orphan_tmp(monkeypatch, tmp_path, capsys):
    import mmc_core

    config_root = tmp_path / "mmc-config"
    monkeypatch.setenv("MMC_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))

    sessions_dir = mmc_core._session_slots_dir()
    tmp_root = mmc_core._tmp_root()
    active_slot = sessions_dir / "123-1"
    stale_slot = sessions_dir / "456-2"
    active_slot.mkdir(parents=True)
    stale_slot.mkdir(parents=True)
    (tmp_root / active_slot.name).mkdir(parents=True)
    (tmp_root / stale_slot.name).mkdir(parents=True)
    (tmp_root / "orphan-only").mkdir(parents=True)

    monkeypatch.setattr(mmc_core, "_slot_pid_is_active", lambda _entry, pid: pid == 123)

    exit_code = mmc_core._handle_session_prune()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert active_slot.exists()
    assert not stale_slot.exists()
    assert (tmp_root / active_slot.name).exists()
    assert not (tmp_root / stale_slot.name).exists()
    assert not (tmp_root / "orphan-only").exists()
    assert "移除 1 个 stale slot" in output
    assert "清理 1 个 orphan tmp" in output


def test_reserve_session_home_uses_reservation_lock(monkeypatch, tmp_path):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    monkeypatch.setattr(mmc_core, "_cleanup_stale_session_slots", lambda _path: [])

    seen = []

    @contextmanager
    def _fake_lock(path):
        seen.append(Path(path))
        yield

    monkeypatch.setattr(mmc_core, "locked_state_file", _fake_lock)

    session_home, active_before, active_after = mmc_core._reserve_session_home()

    assert active_before == 0
    assert active_after == 1
    assert session_home is not None and session_home.exists()
    assert seen[0] == mmc_core._session_slots_lock_path()
    assert seen[1] == mmc_core._session_pid_stamp_path(session_home)


def test_reserve_session_home_blocks_after_max_live_sessions(monkeypatch, tmp_path):
    import mmc_core

    config_root = tmp_path / "mmc-config"
    monkeypatch.setenv("MMC_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))

    fake_active = [Path(f"/tmp/session-{index}") for index in range(1, 5)]
    monkeypatch.setattr(mmc_core, "_cleanup_stale_session_slots", lambda _path: fake_active)

    session_home, active_before, active_after = mmc_core._reserve_session_home()

    assert session_home is None
    assert active_before == 4
    assert active_after == 5


class _FakeGuard:
    def __init__(self, stopped, *, failure_reason=""):
        self.local_proxy_url = "http://127.0.0.1:18080"
        self.failure_reason = failure_reason
        self.failed_event = threading.Event()
        self._stopped = stopped

    def stop(self):
        self._stopped.append(True)


def test_local_proxy_guard_detects_exit_ip_drift():
    from mmc_proxy_guard import LocalProxyGuard

    observed = iter(
        [
            {"ok": True, "detail": "", "exit_ip": "1.1.1.1"},
            {"ok": True, "detail": "", "exit_ip": "2.2.2.2"},
        ]
    )

    guard = LocalProxyGuard(
        "http://127.0.0.1:7890",
        probe_targets=(),
        probe_interval_sec=0.5,
        probe_fn=lambda *_args, **_kwargs: {"ok": True, "detail": ""},
        exit_ip_probe_fn=lambda _proxy: next(observed),
        exit_ip_check_interval_sec=0.5,
    )

    guard._pin_initial_exit_ip()
    guard._next_exit_ip_check_at = 0.0

    assert guard.pinned_exit_ip == "1.1.1.1"
    assert guard._check_pinned_exit_ip() is False
    assert guard.failed_event.is_set() is True
    assert "1.1.1.1 -> 2.2.2.2" in guard.failure_reason


def test_local_proxy_guard_tolerates_single_transient_probe_failure():
    from mmc_proxy_guard import LocalProxyGuard

    guard = LocalProxyGuard(
        "http://127.0.0.1:7890",
        probe_targets=(("anthropic", "https://api.anthropic.com"),),
        probe_interval_sec=0.5,
        probe_fn=lambda *_args, **_kwargs: {"ok": True, "detail": ""},
        heartbeat_failures_before_kill=2,
    )

    assert guard._record_heartbeat_failure("proxy heartbeat failed for anthropic: curl: (28) timeout") is False
    assert guard.failed_event.is_set() is False

    guard._clear_heartbeat_failures()

    assert guard._record_heartbeat_failure("proxy heartbeat failed for anthropic: curl: (28) timeout") is False
    assert guard.failed_event.is_set() is False


def test_local_proxy_guard_ignores_failures_during_startup_grace(monkeypatch):
    import mmc_proxy_guard
    from mmc_proxy_guard import LocalProxyGuard

    monkeypatch.setattr(mmc_proxy_guard.time, "monotonic", lambda: 100.0)
    guard = LocalProxyGuard(
        "http://127.0.0.1:7890",
        probe_targets=(("anthropic", "https://api.anthropic.com"),),
        probe_interval_sec=0.5,
        probe_fn=lambda *_args, **_kwargs: {"ok": True, "detail": ""},
        heartbeat_failures_before_kill=2,
        startup_grace_sec=30,
    )
    guard._startup_grace_deadline = 120.0

    assert guard._record_heartbeat_failure("proxy heartbeat failed for anthropic: curl: (28) timeout") is False
    assert guard.failed_event.is_set() is False
    assert guard._heartbeat_failure_streak == 0


def test_local_proxy_guard_requires_consecutive_probe_failures_before_fail():
    from mmc_proxy_guard import LocalProxyGuard

    guard = LocalProxyGuard(
        "http://127.0.0.1:7890",
        probe_targets=(("anthropic", "https://api.anthropic.com"),),
        probe_interval_sec=0.5,
        probe_fn=lambda *_args, **_kwargs: {"ok": True, "detail": ""},
        heartbeat_failures_before_kill=2,
    )

    assert guard._record_heartbeat_failure("proxy heartbeat failed for anthropic: curl: (28) timeout") is False
    assert guard.failed_event.is_set() is False

    assert guard._record_heartbeat_failure("proxy heartbeat failed for anthropic: curl: (28) timeout") is True
    assert guard.failed_event.is_set() is True
    assert "consecutive 2/2" in guard.failure_reason


def test_start_session_proxy_guard_uses_runtime_grace_and_failure_threshold(monkeypatch):
    import mmc_core

    captured = {}

    class _FakeGuard:
        def __init__(self, proxy_url, **kwargs):
            captured["proxy_url"] = proxy_url
            captured.update(kwargs)
            self.local_proxy_url = proxy_url

        def start(self):
            captured["started"] = True

    monkeypatch.setattr(mmc_core, "LocalProxyGuard", _FakeGuard)

    guard = mmc_core._start_session_proxy_guard("http://127.0.0.1:7890", pinned_exit_ip="1.2.3.4")

    assert guard.local_proxy_url == "http://127.0.0.1:7890"
    assert captured["started"] is True
    assert captured["probe_targets"] == (("loopback", "http://127.0.0.1:7890"),)
    assert captured["heartbeat_failures_before_kill"] == mmc_core._LOCAL_PROXY_GUARD_HEARTBEAT_FAILURES_BEFORE_KILL
    assert captured["startup_grace_sec"] == mmc_core._LOCAL_PROXY_GUARD_STARTUP_GRACE_SEC
    assert captured["expected_exit_ip"] == ""
    assert captured["exit_ip_probe_fn"] is None


def test_runtime_proxy_probe_only_checks_local_loopback(monkeypatch):
    import mmc_core

    monkeypatch.setattr(
        mmc_core,
        "validate_loopback_proxy_url",
        lambda _url: {"ok": True, "host": "127.0.0.1", "port": 31001},
    )
    monkeypatch.setattr(
        mmc_core,
        "_doctor_probe_tcp_endpoint",
        lambda host, port, timeout_sec=4.0: (True, f"{host}:{port}"),
    )

    probe = mmc_core._build_runtime_proxy_probe()
    result = probe("http://127.0.0.1:31001", "https://api.anthropic.com")

    assert result == {"ok": True, "detail": ""}


def test_apply_launcher_defaults_fills_missing_launch_args(monkeypatch, tmp_path):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    defaults = mmc_core._save_launcher_defaults(
        {
            "proxy": "http://127.0.0.1:7890",
            "no_proxy": "127.0.0.1,localhost",
            "lang": "zh_CN.UTF-8",
            "tz": "America/Los_Angeles",
            "bypass": True,
        }
    )
    args = mmc_core._build_launch_namespace(workspace="/tmp/workspace")

    mmc_core._apply_launcher_defaults(args, defaults)

    assert args.proxy == "http://127.0.0.1:7890"
    assert args.no_proxy == "127.0.0.1,localhost"
    assert args.lang == "zh_CN.UTF-8"
    assert args.tz == "America/Los_Angeles"
    assert args.bypass is True


def test_build_claude_cmd_appends_resume_id_before_dirs(monkeypatch, tmp_path):
    import mmc_core

    env = {"PATH": str(tmp_path)}
    monkeypatch.setattr(mmc_core, "_resolve_claude_binary", lambda _env: "/tmp/claude")

    args = mmc_core._build_launch_namespace()
    args.allow_dir = ["/tmp/workspace"]

    cmd = mmc_core._build_claude_cmd(
        args,
        env,
        explicit_session_id="02c0ed3d-bd33-4c64-93e3-fa58a60d9d6c",
    )

    assert cmd[:3] == ["/tmp/claude", "--resume", "02c0ed3d-bd33-4c64-93e3-fa58a60d9d6c"]
    assert cmd[3:] == ["--add-dir", os.path.realpath("/tmp/workspace")]


def test_normalize_launcher_defaults_fills_loopback_no_proxy_when_missing(monkeypatch, tmp_path):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))

    normalized = mmc_core._normalize_launcher_defaults(
        {
            "proxy": "http://127.0.0.1:7890",
            "no_proxy": "",
        }
    )
    args = mmc_core._build_launch_namespace()

    assert normalized["no_proxy"] == "127.0.0.1,localhost"
    assert args.no_proxy == "127.0.0.1,localhost"


def test_run_default_entry_uses_saved_launcher_defaults(monkeypatch, tmp_path):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    monkeypatch.setattr(mmc_core.os, "getcwd", lambda: str(tmp_path / "repo"))
    mmc_core._save_launcher_defaults(
        {
            "proxy": "http://127.0.0.1:7890",
            "lang": "zh_CN.UTF-8",
            "tz": "America/Los_Angeles",
        }
    )

    captured = {}
    monkeypatch.setattr(
        mmc_core,
        "_run_claude",
        lambda args, explicit_session_id="": captured.update(
            {
                "workspace": args.workspace,
                "proxy": args.proxy,
                "lang": args.lang,
                "tz": args.tz,
                "explicit_session_id": explicit_session_id,
            }
        )
        or 0,
    )

    exit_code = mmc_core._run_default_entry()

    assert exit_code == 0
    assert captured["workspace"] == str(tmp_path / "repo")
    assert captured["proxy"] == "http://127.0.0.1:7890"
    assert captured["lang"] == "zh_CN.UTF-8"
    assert captured["tz"] == "America/Los_Angeles"
    assert captured["explicit_session_id"] == ""


def test_run_default_entry_prompts_and_saves_defaults_when_missing(monkeypatch, tmp_path):
    import mmc_core

    config_root = tmp_path / "mmc-config"
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    monkeypatch.setenv("MMC_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    monkeypatch.setattr(mmc_core.os, "getcwd", lambda: str(repo_dir))
    monkeypatch.setattr(mmc_core, "_interactive_stdio_available", lambda: True)
    answers = iter(["http://127.0.0.1:7890", "", "America/Los_Angeles", "zh_CN.UTF-8", "n"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    captured = {}
    monkeypatch.setattr(
        mmc_core,
        "_run_claude",
        lambda args, explicit_session_id="": captured.update({"proxy": args.proxy, "workspace": args.workspace}) or 0,
    )

    exit_code = mmc_core._run_default_entry()
    saved = json.loads((config_root / "launcher.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert captured == {"proxy": "http://127.0.0.1:7890", "workspace": str(repo_dir)}
    assert saved["proxy"] == "http://127.0.0.1:7890"
    assert saved["tz"] == "America/Los_Angeles"
    assert saved["lang"] == "zh_CN.UTF-8"
    assert saved["bypass"] is False


def test_run_setup_interactive_uses_default_lang_and_tz_on_empty_input(monkeypatch, tmp_path):
    import mmc_core

    config_root = tmp_path / "mmc-config"
    monkeypatch.setenv("MMC_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    monkeypatch.delenv("LANG", raising=False)
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_CTYPE", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    monkeypatch.delenv("TZ", raising=False)
    answers = iter(["http://127.0.0.1:7890", "", "", "", "n"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    payload = mmc_core._run_setup_interactive(save=False)

    assert payload["proxy"] == "http://127.0.0.1:7890"
    assert payload["no_proxy"] == "127.0.0.1,localhost"
    assert payload["tz"] == "America/Los_Angeles"
    assert payload["lang"] == "en_US.UTF-8"
    assert payload["bypass"] is False


def test_human_guard_blocks_live_command_without_manual_allow(monkeypatch, tmp_path):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))

    mmc_core._save_human_guard_state(
        {
            "enabled": True,
            "allow_until": "",
            "remaining_uses": 0,
        }
    )

    with pytest.raises(SystemExit, match="human-only guard 拒绝执行"):
        mmc_core._guarded_human_only_command("mmc run")


def test_human_guard_allow_consumes_single_live_command(monkeypatch, tmp_path):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    mmc_core._save_human_guard_state({"enabled": True})
    monkeypatch.setattr(mmc_core, "_interactive_stdio_available", lambda: True)
    monkeypatch.setattr(mmc_core, "_prompt_text", lambda *_args, **_kwargs: "")

    exit_code = mmc_core._handle_guard_allow(ttl_sec=120, uses=1, reason="manual smoke")

    assert exit_code == 0
    active_state = mmc_core._load_human_guard_state()
    assert active_state["enabled"] is True
    assert active_state["remaining_uses"] == 1
    assert active_state["last_allow_reason"] == "manual smoke"
    assert active_state["allow_until"]

    mmc_core._guarded_human_only_command("mmc run")

    consumed_state = mmc_core._load_human_guard_state()
    assert consumed_state["remaining_uses"] == 0
    assert consumed_state["allow_until"] == ""
    assert consumed_state["last_consumed_command"] == "mmc run"

    with pytest.raises(SystemExit, match="human-only guard 拒绝执行"):
        mmc_core._guarded_human_only_command("mmc run")


def test_human_guard_enable_and_disable_persist_state(monkeypatch, tmp_path):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setattr(mmc_core, "_interactive_stdio_available", lambda: True)
    monkeypatch.setattr(mmc_core, "_prompt_text", lambda *_args, **_kwargs: "ALLOW MMC")

    assert mmc_core._handle_guard_enable() == 0
    enabled_state = mmc_core._load_human_guard_state()
    assert enabled_state["enabled"] is True
    assert enabled_state["last_enable_at"]

    assert mmc_core._handle_guard_disable() == 0
    disabled_state = mmc_core._load_human_guard_state()
    assert disabled_state["enabled"] is False
    assert disabled_state["remaining_uses"] == 0
    assert disabled_state["allow_until"] == ""
    assert disabled_state["last_disable_at"]


def test_run_resume_latest_uses_saved_defaults(monkeypatch, tmp_path):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    mmc_core._save_launcher_defaults({"proxy": "http://127.0.0.1:7890"})
    monkeypatch.setattr(
        mmc_core,
        "_list_owned_indexed_sessions",
        lambda: [
            {"session_id": "session-latest", "last_active_at": "2026-04-16T01:00:00+00:00"},
        ],
    )
    monkeypatch.setattr(mmc_core.os, "getcwd", lambda: str(tmp_path / "repo"))

    captured = {}
    monkeypatch.setattr(
        mmc_core,
        "_run_resume",
        lambda args: captured.update(
            {
                "session_ref": args.session_ref,
                "proxy": args.proxy,
                "workspace": args.workspace,
            }
        )
        or 0,
    )

    exit_code = mmc_core._run_resume_latest()

    assert exit_code == 0
    assert captured["session_ref"] == "session-latest"
    assert captured["proxy"] == "http://127.0.0.1:7890"
    assert captured["workspace"] == str(tmp_path / "repo")


def test_run_resume_accepts_explicit_uuid_when_index_missing(monkeypatch, tmp_path, capsys):
    import mmc_core

    workspace = tmp_path / "repo"
    workspace.mkdir()
    session_id = "02c0ed3d-bd33-4c64-93e3-fa58a60d9d6c"
    args = mmc_core._build_launch_namespace(workspace=str(workspace))
    args.session_ref = session_id

    monkeypatch.setattr(mmc_core, "_resolve_owned_session_ref", lambda _ref: (None, "not found"))
    monkeypatch.setattr(mmc_core, "_list_owned_indexed_sessions", lambda: [])

    captured = {}
    monkeypatch.setattr(
        mmc_core,
        "_run_claude",
        lambda launch_args, explicit_session_id="": captured.update(
            {
                "workspace": launch_args.workspace,
                "explicit_session_id": explicit_session_id,
            }
        )
        or 0,
    )

    exit_code = mmc_core._run_resume(args)
    stderr = capsys.readouterr().err

    assert exit_code == 0
    assert captured["workspace"] == str(workspace)
    assert captured["explicit_session_id"] == session_id
    assert "显式 Claude session id" in stderr


def test_run_resume_latest_skips_non_resumable_placeholder_sessions(monkeypatch, tmp_path):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    mmc_core._save_launcher_defaults({"proxy": "http://127.0.0.1:7890"})
    monkeypatch.setattr(
        mmc_core,
        "_list_owned_indexed_sessions",
        lambda: [
            {"session_id": "", "last_active_at": "2026-04-16T03:00:00+00:00"},
            {"session_id": "pid-999", "last_active_at": "2026-04-16T02:00:00+00:00"},
            {"session_id": "session-good", "last_active_at": "2026-04-16T01:00:00+00:00"},
        ],
    )
    monkeypatch.setattr(mmc_core.os, "getcwd", lambda: str(tmp_path / "repo"))

    captured = {}
    monkeypatch.setattr(
        mmc_core,
        "_run_resume",
        lambda args: captured.update(
            {
                "session_ref": args.session_ref,
                "proxy": args.proxy,
                "workspace": args.workspace,
            }
        )
        or 0,
    )

    exit_code = mmc_core._run_resume_latest()

    assert exit_code == 0
    assert captured["session_ref"] == "session-good"


def test_resolve_owned_session_ref_ignores_non_resumable_placeholders(monkeypatch):
    import mmc_core

    monkeypatch.setattr(
        mmc_core,
        "_list_owned_indexed_sessions",
        lambda: [
            {"session_id": "", "last_active_at": "2026-04-16T03:00:00+00:00"},
            {"session_id": "pid-999", "last_active_at": "2026-04-16T02:00:00+00:00"},
            {"session_id": "session-good", "last_active_at": "2026-04-16T01:00:00+00:00"},
        ],
    )

    resolved, error = mmc_core._resolve_owned_session_ref("1")

    assert resolved == "session-good"
    assert error is None


def test_main_shortcuts_route_to_expected_handlers(monkeypatch):
    import mmc_core

    seen = []
    monkeypatch.setattr(mmc_core, "_run_default_entry", lambda: seen.append("run") or 0)
    monkeypatch.setattr(mmc_core, "_run_resume_latest", lambda: seen.append("resume-latest") or 0)
    monkeypatch.setattr(mmc_core, "_handle_session_ls", lambda: seen.append("session-ls") or 0)
    monkeypatch.setattr(mmc_core, "_guarded_human_only_command", lambda _label: None)

    with pytest.raises(SystemExit) as exc:
        mmc_core.main(["1"])
    assert exc.value.code == 0

    with pytest.raises(SystemExit) as exc:
        mmc_core.main(["2"])
    assert exc.value.code == 0

    with pytest.raises(SystemExit) as exc:
        mmc_core.main(["3"])
    assert exc.value.code == 0

    with pytest.raises(SystemExit) as exc:
        mmc_core.main([])
    assert exc.value.code == 0
    assert seen == ["run", "resume-latest", "session-ls", "run"]


def test_main_allow_shortcut_routes_to_guard_allow(monkeypatch):
    import mmc_core

    captured = {}
    monkeypatch.setattr(
        mmc_core,
        "_handle_guard_allow",
        lambda ttl_sec, uses, reason="": captured.update({"ttl_sec": ttl_sec, "uses": uses, "reason": reason}) or 0,
    )

    with pytest.raises(SystemExit) as exc:
        mmc_core.main(["allow", "--ttl-sec", "120", "--uses", "2", "--reason", "manual"])

    assert exc.value.code == 0
    assert captured == {"ttl_sec": 120, "uses": 2, "reason": "manual"}


def test_inject_upstream_proxy_auth_adds_and_replaces_header():
    from mmc_proxy_guard import inject_upstream_proxy_auth

    request = b"CONNECT claude.ai:443 HTTP/1.1\r\nHost: claude.ai:443\r\n\r\n"
    injected = inject_upstream_proxy_auth(request, "Basic abc")
    replaced = inject_upstream_proxy_auth(
        b"CONNECT claude.ai:443 HTTP/1.1\r\nHost: claude.ai:443\r\nProxy-Authorization: Basic old\r\n\r\n",
        "Basic new",
    )

    assert b"Proxy-Authorization: Basic abc\r\n" in injected
    assert b"Proxy-Authorization: Basic new\r\n" in replaced
    assert b"Basic old" not in replaced
