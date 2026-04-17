from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest


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
    assert env["HTTP_PROXY"] == "http://127.0.0.1:7890"
    assert env["NO_PROXY"] == "127.0.0.1,localhost"
    assert env["HOME"] == str(session_home)
    assert env["MMC_REAL_HOME"] == str((tmp_path / "real-home").resolve())
    assert env["TMPDIR"].startswith(str((tmp_path / "mmc-config" / "tmp").resolve()))
    assert path_parts[0] == str((session_home / ".mmc" / "bin").resolve())
    assert path_parts[1:3] == ["/opt/homebrew/bin", "/Users/demo/.cargo/bin"]
    assert env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"
    assert env["API_TIMEOUT_MS"] == "3000000"
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


def test_proxy_guard_blocks_missing_proxy(monkeypatch):
    import mmc_core

    args = argparse.Namespace(proxy="", no_proxy="")
    with pytest.raises(SystemExit, match="proxy guard"):
        mmc_core._enforce_proxy_guard_or_exit(args)


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
    assert guard["exit_ip"] == ""
    assert guard["exit_ip_detail"] == "checkip failed"


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
    monkeypatch.setattr(mmc_core, "_enforce_proxy_guard_or_exit", lambda _args: None)
    monkeypatch.setattr(mmc_core, "_bootstrap_account_state", lambda: None)
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

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    monkeypatch.setattr(mmc_core, "_enforce_proxy_guard_or_exit", lambda _args: None)
    monkeypatch.setattr(mmc_core, "_bootstrap_account_state", lambda: None)
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
    monkeypatch.setattr(mmc_core.subprocess, "Popen", lambda *_args, **_kwargs: child)

    args = argparse.Namespace(
        workspace=str(workspace),
        proxy="http://107.0.0.1:7890",
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
    assert finalized == [(session_home, exit_code, False)]
    assert stopped == [True]


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
