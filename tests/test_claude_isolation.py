"""Isolation tests for Claude account/project state handling."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def scoped_store(tmp_path):
    config_root = tmp_path / "config"
    projects_root = config_root / "projects"
    with patch("mms_project_store.PRIMARY_CONFIG_DIR", config_root), patch(
        "mms_project_store.PROJECTS_DIR",
        projects_root,
    ), patch("mms_session_index.PRIMARY_CONFIG_DIR", config_root):
        yield config_root, projects_root


def test_project_key_is_scoped_by_account(tmp_path):
    from mms_project_store import project_key

    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    shared_a = project_key(str(project_dir), account_id="claude-a")
    shared_b = project_key(str(project_dir), account_id="claude-b")
    shared_a_again = project_key(str(project_dir), account_id="claude-a")

    assert shared_a != shared_b
    assert shared_a == shared_a_again


def test_project_store_starts_empty_without_global_seed(tmp_path, scoped_store):
    _config_root, _projects_root = scoped_store
    from mms_project_store import claude_project_metadata_path, ensure_claude_project_store

    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    store = ensure_claude_project_store(str(project_dir), account_id="claude-a")

    history_path = Path(store["raw_root"]) / "history.jsonl"
    assert history_path.exists()
    assert history_path.read_text(encoding="utf-8") == ""

    metadata_path = claude_project_metadata_path(str(project_dir), account_id="claude-a")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["account_id"] == "claude-a"


def test_seed_claude_state_does_not_copy_global_user_identity(tmp_path):
    from mms_account_state import seed_claude_state

    account_home = tmp_path / "account-home"
    account_home.mkdir()

    seed_claude_state(str(account_home))

    state_path = account_home / ".claude.json"
    assert state_path.exists()
    assert json.loads(state_path.read_text(encoding="utf-8")) == {}


def test_session_index_isolated_by_account(tmp_path, scoped_store):
    _config_root, _projects_root = scoped_store
    from mms_session_index import list_indexed_sessions, record_claude_session_start

    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    record_claude_session_start(
        cwd=str(project_dir),
        account_id="claude-a",
        pid=101,
        runtime_kind="oauth",
        slot_home="/tmp/slot-a",
    )
    record_claude_session_start(
        cwd=str(project_dir),
        account_id="claude-b",
        pid=202,
        runtime_kind="oauth",
        slot_home="/tmp/slot-b",
    )

    rows = list_indexed_sessions("claude")
    accounts = {item["account_id"] for item in rows}
    pids = {item["pid"] for item in rows}

    assert {"claude-a", "claude-b"} <= accounts
    assert {101, 202} <= pids


def test_sync_claude_session_state_back_to_account(tmp_path):
    from mms_launchers import _sync_claude_session_state_to_account_home

    session_home = tmp_path / "session"
    account_home = tmp_path / "account"
    (session_home / ".claude").mkdir(parents=True)

    (session_home / ".claude.json").write_text(
        json.dumps({"userID": "device-b", "numStartups": 3}),
        encoding="utf-8",
    )
    (session_home / ".claude" / "settings.json").write_text(
        json.dumps({"theme": "dark"}),
        encoding="utf-8",
    )

    _sync_claude_session_state_to_account_home(str(session_home), str(account_home))

    assert json.loads((account_home / ".claude.json").read_text(encoding="utf-8"))["userID"] == "device-b"
    assert json.loads((account_home / ".claude" / "settings.json").read_text(encoding="utf-8"))["theme"] == "dark"
