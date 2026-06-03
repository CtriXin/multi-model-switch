"""Isolation tests for Claude account/project state handling."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import types
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.fixture
def scoped_store(tmp_path):
    config_root = tmp_path / "config"
    projects_root = config_root / "projects"
    with patch("mms_project_store.PRIMARY_CONFIG_DIR", config_root), patch(
        "mms_project_store.PROJECTS_DIR",
        projects_root,
    ), patch("mms_session_index.get_projects_dir", lambda: projects_root):
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
        resume_model="claude-sonnet-4-6",
    )
    record_claude_session_start(
        cwd=str(project_dir),
        account_id="claude-b",
        pid=202,
        runtime_kind="oauth",
        slot_home="/tmp/slot-b",
        resume_model="gpt-5.4",
    )

    rows = list_indexed_sessions("claude")
    accounts = {item["account_id"] for item in rows}
    pids = {item["pid"] for item in rows}
    resume_models = {item["resume_model"] for item in rows}

    assert {"claude-a", "claude-b"} <= accounts
    assert {101, 202} <= pids
    assert {"claude-sonnet-4-6", "gpt-5.4"} <= resume_models


def test_load_project_scoped_resume_uses_real_home_index_under_gateway_home(monkeypatch, tmp_path):
    import mms_launchers
    from mms_project_store import claude_raw_entry_path
    from mms_session_index import record_claude_session_start

    real_home = tmp_path / "real-home"
    gateway_home = real_home / ".config" / "mms" / "codex-gateway" / "s" / "16593"
    gateway_home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(gateway_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(real_home / ".config"))
    monkeypatch.setenv("MMS_REAL_HOME", str(real_home))
    monkeypatch.setenv("REAL_HOME", str(real_home))
    monkeypatch.setenv("ORIGINAL_HOME", str(real_home))

    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    payload = record_claude_session_start(
        cwd=str(project_dir),
        account_id="relay-a",
        pid=101,
        runtime_kind="api_key",
        slot_home=str(tmp_path / "slot"),
    )
    started_at_ms = int(datetime.fromisoformat(payload["started_at"]).timestamp() * 1000)
    raw_sessions = claude_raw_entry_path("sessions", str(project_dir), account_id="relay-a")
    (raw_sessions / "session-1.json").write_text(
        json.dumps(
            {
                "pid": 202,
                "sessionId": "session-match",
                "cwd": str(project_dir.resolve()),
                "startedAt": started_at_ms + 321,
                "kind": "interactive",
                "entrypoint": "cli",
            }
        ),
        encoding="utf-8",
    )

    result = mms_launchers._load_project_scoped_claude_resume_session_id(
        str(project_dir),
        account_id="relay-a",
        runtime_kind="api_key",
    )

    assert result == "session-match"


def test_backfill_project_store_resume_files_cross_account(tmp_path, scoped_store):
    import mms_launchers
    from mms_project_store import claude_raw_entry_path, ensure_claude_project_store

    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    ensure_claude_project_store(str(project_dir), account_id="relay-a")
    ensure_claude_project_store(str(project_dir), account_id="relay-b")
    source_projects = claude_raw_entry_path("projects", str(project_dir), account_id="relay-b")
    source_file = source_projects / "repo-key" / "session-cross.jsonl"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text('{"sessionId":"session-cross"}\n', encoding="utf-8")

    target_projects = claude_raw_entry_path("projects", str(project_dir), account_id="relay-a")
    mms_launchers._backfill_project_store_claude_resume_files(str(target_projects), str(project_dir))

    copied = target_projects / "repo-key" / "session-cross.jsonl"
    assert copied.read_text(encoding="utf-8") == '{"sessionId":"session-cross"}\n'


def test_mms_config_paths_resolve_real_home_under_gateway_shell(monkeypatch, tmp_path):
    import mms_core
    import mms_router

    real_home = tmp_path / "real-home"
    gateway_home = real_home / ".config" / "mms" / "codex-gateway" / "s" / "4174"
    gateway_home.mkdir(parents=True)

    monkeypatch.setenv("HOME", str(gateway_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(real_home / ".config"))
    monkeypatch.setenv("MMS_REAL_HOME", str(real_home))
    monkeypatch.setenv("REAL_HOME", str(real_home))
    monkeypatch.setenv("ORIGINAL_HOME", str(real_home))

    reloaded_core = importlib.reload(mms_core)
    reloaded_router = importlib.reload(mms_router)
    try:
        assert reloaded_core.CONFIG_PATH == str(real_home / ".config" / "mms" / "config.toml")
        assert reloaded_core.CREDENTIALS_PATH == str(real_home / ".config" / "mms" / "credentials.sh")
        assert reloaded_core._config_write_target_path() == str(real_home / ".config" / "mms" / "config.toml")
        assert reloaded_router.MODEL_ROUTES_PATH == str(real_home / ".config" / "mms" / "model-routes.json")
    finally:
        monkeypatch.delenv("HOME", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.delenv("MMS_REAL_HOME", raising=False)
        monkeypatch.delenv("REAL_HOME", raising=False)
        monkeypatch.delenv("ORIGINAL_HOME", raising=False)
        importlib.reload(mms_router)
        importlib.reload(mms_core)


def test_mms_config_root_overrides_gateway_real_home(monkeypatch, tmp_path):
    import mms_core
    import mms_registry
    import mms_router

    real_home = tmp_path / "real-home"
    gateway_home = real_home / ".config" / "mms" / "codex-gateway" / "s" / "4174"
    preview_root = tmp_path / "preview-root"
    gateway_home.mkdir(parents=True)

    monkeypatch.setenv("HOME", str(gateway_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(gateway_home / ".config"))
    monkeypatch.setenv("MMS_REAL_HOME", str(real_home))
    monkeypatch.setenv("REAL_HOME", str(real_home))
    monkeypatch.setenv("ORIGINAL_HOME", str(real_home))
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))
    monkeypatch.setenv("MMS_COMMAND_NAME", "mmf")
    monkeypatch.setenv("MMS_PREVIEW_MODE", "mmf")

    reloaded_core = importlib.reload(mms_core)
    reloaded_router = importlib.reload(mms_router)
    try:
        stable_root = real_home / ".config" / "mms"
        assert reloaded_core.CONFIG_PATH == str(preview_root / "config.toml")
        assert reloaded_core.CREDENTIALS_PATH == str(preview_root / "credentials.sh")
        assert reloaded_core._active_config_path() == str(preview_root / "config.toml")
        assert reloaded_core._active_credentials_path() == str(preview_root / "credentials.sh")
        assert reloaded_core._active_usage_path() == str(preview_root / "usage.json")
        assert reloaded_core._config_root_status()["mode"] == "preview"
        assert reloaded_core._config_root_status()["command"] == "mmf"
        assert reloaded_router.MODEL_ROUTES_PATH == str(preview_root / "model-routes.json")
        assert mms_registry.default_registry_db_path(env=os.environ) == preview_root / "registry" / "model-registry.sqlite"
        assert not str(reloaded_core.CONFIG_PATH).startswith(str(stable_root))
    finally:
        monkeypatch.delenv("HOME", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.delenv("MMS_REAL_HOME", raising=False)
        monkeypatch.delenv("REAL_HOME", raising=False)
        monkeypatch.delenv("ORIGINAL_HOME", raising=False)
        monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
        monkeypatch.delenv("MMS_COMMAND_NAME", raising=False)
        monkeypatch.delenv("MMS_PREVIEW_MODE", raising=False)
        importlib.reload(mms_router)
        importlib.reload(mms_core)


def test_preview_usage_write_skips_legacy_routes_export(monkeypatch, tmp_path):
    import mms_core

    real_home = tmp_path / "real-home"
    preview_root = tmp_path / "mms-next"
    preview_root.mkdir(parents=True)

    monkeypatch.setenv("MMS_REAL_HOME", str(real_home))
    monkeypatch.setenv("REAL_HOME", str(real_home))
    monkeypatch.setenv("ORIGINAL_HOME", str(real_home))
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))
    monkeypatch.setenv("MMS_COMMAND_NAME", "mmf")
    monkeypatch.setenv("MMS_PREVIEW_MODE", "mmf")

    reloaded = importlib.reload(mms_core)
    try:
        calls = []
        monkeypatch.setattr(reloaded, "_refresh_routes_export_for_hive", lambda *args, **kwargs: calls.append(kwargs))

        def fail_thread(*_args, **_kwargs):
            raise AssertionError("preview usage writes must not start legacy route export thread")

        monkeypatch.setattr(reloaded.threading, "Thread", fail_thread)
        reloaded._trigger_routes_export_after_usage_write()

        assert calls == []
    finally:
        monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
        monkeypatch.delenv("MMS_COMMAND_NAME", raising=False)
        monkeypatch.delenv("MMS_PREVIEW_MODE", raising=False)
        monkeypatch.delenv("MMS_REAL_HOME", raising=False)
        monkeypatch.delenv("REAL_HOME", raising=False)
        monkeypatch.delenv("ORIGINAL_HOME", raising=False)
        importlib.reload(mms_core)


def test_stable_usage_write_keeps_legacy_routes_export(monkeypatch, tmp_path):
    import mms_core

    real_home = tmp_path / "real-home"
    stable_root = real_home / ".config" / "mms"
    stable_root.mkdir(parents=True)

    monkeypatch.setenv("MMS_REAL_HOME", str(real_home))
    monkeypatch.setenv("REAL_HOME", str(real_home))
    monkeypatch.setenv("ORIGINAL_HOME", str(real_home))
    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    monkeypatch.delenv("MMS_COMMAND_NAME", raising=False)
    monkeypatch.delenv("MMS_PREVIEW_MODE", raising=False)

    reloaded = importlib.reload(mms_core)
    try:
        calls = []
        monkeypatch.setattr(reloaded, "_refresh_routes_export_for_hive", lambda *args, **kwargs: calls.append(kwargs))

        class ImmediateThread:
            def __init__(self, *, target, **_kwargs):
                self.target = target

            def start(self):
                self.target()

        monkeypatch.setattr(reloaded.threading, "Thread", ImmediateThread)
        reloaded._trigger_routes_export_after_usage_write()

        assert calls == [{"force": True, "quiet": True}]
    finally:
        monkeypatch.delenv("MMS_REAL_HOME", raising=False)
        monkeypatch.delenv("REAL_HOME", raising=False)
        monkeypatch.delenv("ORIGINAL_HOME", raising=False)
        importlib.reload(mms_core)


def test_project_store_uses_selected_config_root(monkeypatch, tmp_path):
    import mms_project_store

    real_home = tmp_path / "real-home"
    preview_root = tmp_path / "mms-next"
    monkeypatch.setenv("MMS_REAL_HOME", str(real_home))
    monkeypatch.setenv("REAL_HOME", str(real_home))
    monkeypatch.setenv("ORIGINAL_HOME", str(real_home))
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))

    assert mms_project_store.get_primary_config_dir() == preview_root
    assert mms_project_store.get_projects_dir() == preview_root / "projects"


def test_launcher_runtime_aux_paths_use_selected_config_root(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    preview_root = tmp_path / "mms-next"
    monkeypatch.setenv("MMS_REAL_HOME", str(real_home))
    monkeypatch.setenv("REAL_HOME", str(real_home))
    monkeypatch.setenv("ORIGINAL_HOME", str(real_home))
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))

    reloaded = importlib.reload(mms_launchers)
    try:
        assert reloaded.RUNTIME_DIR == str(preview_root / "runtime")
        assert reloaded.HEALTH_CHECK_PATH == str(preview_root / "health_check.json")
        assert reloaded.ANTHROPIC_URL_CACHE_PATH == str(preview_root / "cache" / "anthropic_base_urls.json")
        assert reloaded._selected_config_path("usage.json") == str(preview_root / "usage.json")
    finally:
        monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
        monkeypatch.delenv("MMS_REAL_HOME", raising=False)
        monkeypatch.delenv("REAL_HOME", raising=False)
        monkeypatch.delenv("ORIGINAL_HOME", raising=False)
        importlib.reload(mms_launchers)


def test_usage_local_stats_use_selected_config_root(monkeypatch, tmp_path):
    import mms_usage

    real_home = tmp_path / "real-home"
    stable_root = real_home / ".config" / "mms"
    preview_root = tmp_path / "mms-next"
    stable_root.mkdir(parents=True)
    preview_root.mkdir(parents=True)
    (stable_root / "usage.json").write_text('{"sources":{"stable":{}}}', encoding="utf-8")

    monkeypatch.setenv("MMS_REAL_HOME", str(real_home))
    monkeypatch.setenv("REAL_HOME", str(real_home))
    monkeypatch.setenv("ORIGINAL_HOME", str(real_home))
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))

    reloaded = importlib.reload(mms_usage)
    try:
        assert reloaded._active_usage_path() is None
        (preview_root / "usage.json").write_text('{"sources":{"preview":{}}}', encoding="utf-8")
        assert reloaded._active_usage_path() == str(preview_root / "usage.json")
    finally:
        monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
        monkeypatch.delenv("MMS_REAL_HOME", raising=False)
        monkeypatch.delenv("REAL_HOME", raising=False)
        monkeypatch.delenv("ORIGINAL_HOME", raising=False)
        importlib.reload(mms_usage)


def test_speed_stats_use_selected_config_root(monkeypatch, tmp_path):
    import mms_speed_stats

    real_home = tmp_path / "real-home"
    stable_root = real_home / ".config" / "mms"
    preview_root = tmp_path / "mms-next"
    stable_root.mkdir(parents=True)

    monkeypatch.setenv("MMS_REAL_HOME", str(real_home))
    monkeypatch.setenv("REAL_HOME", str(real_home))
    monkeypatch.setenv("ORIGINAL_HOME", str(real_home))
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))

    reloaded = importlib.reload(mms_speed_stats)
    try:
        reloaded.record_model_speed(
            "preview-model",
            ttfb_ms=123,
            provider={"id": "preview-provider", "base_url": "https://preview.example/v1"},
        )
        assert (preview_root / "speed-stats.json").exists()
        assert not (stable_root / "speed-stats.json").exists()
        assert reloaded._speed_stats_path() == preview_root / "speed-stats.json"
    finally:
        monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
        monkeypatch.delenv("MMS_REAL_HOME", raising=False)
        monkeypatch.delenv("REAL_HOME", raising=False)
        monkeypatch.delenv("ORIGINAL_HOME", raising=False)
        importlib.reload(mms_speed_stats)


def test_health_cache_uses_selected_config_root(monkeypatch, tmp_path):
    import mms_health_cache
    import mms_speed_stats

    real_home = tmp_path / "real-home"
    stable_root = real_home / ".config" / "mms"
    preview_root = tmp_path / "mms-next"
    stable_root.mkdir(parents=True)
    preview_root.mkdir(parents=True)
    (preview_root / "speed-stats.json").write_text(
        json.dumps(
            {
                "preview-model": {
                    "ttfb_avg_ms": 800,
                    "samples": 3,
                    "last_updated": datetime.now().astimezone().isoformat(),
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("MMS_REAL_HOME", str(real_home))
    monkeypatch.setenv("REAL_HOME", str(real_home))
    monkeypatch.setenv("ORIGINAL_HOME", str(real_home))
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))

    reloaded_speed = importlib.reload(mms_speed_stats)
    reloaded_health = importlib.reload(mms_health_cache)
    try:
        reloaded_health.refresh_health_cache()
        assert (preview_root / "health-cache.json").exists()
        assert not (stable_root / "health-cache.json").exists()
        assert reloaded_health._speed_stats_path() == preview_root / "speed-stats.json"
        assert reloaded_speed._speed_stats_path() == preview_root / "speed-stats.json"
    finally:
        monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
        monkeypatch.delenv("MMS_REAL_HOME", raising=False)
        monkeypatch.delenv("REAL_HOME", raising=False)
        monkeypatch.delenv("ORIGINAL_HOME", raising=False)
        importlib.reload(mms_speed_stats)
        importlib.reload(mms_health_cache)


def test_runtime_events_use_selected_config_root(monkeypatch, tmp_path):
    import mms_events

    real_home = tmp_path / "real-home"
    stable_root = real_home / ".config" / "mms"
    preview_root = tmp_path / "mms-next"
    stable_root.mkdir(parents=True)

    monkeypatch.setenv("MMS_REAL_HOME", str(real_home))
    monkeypatch.setenv("REAL_HOME", str(real_home))
    monkeypatch.setenv("ORIGINAL_HOME", str(real_home))
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))
    monkeypatch.setitem(
        sys.modules,
        "gbrain_memory_hook",
        SimpleNamespace(ingest_mms_event=lambda _event: None),
    )

    reloaded = importlib.reload(mms_events)
    try:
        reloaded.emit_event("started", "preview-model")
        assert (preview_root / "events" / "latest.json").exists()
        assert not (stable_root / "events" / "latest.json").exists()
        assert reloaded.get_latest_event()["model"] == "preview-model"
    finally:
        monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
        monkeypatch.delenv("MMS_REAL_HOME", raising=False)
        monkeypatch.delenv("REAL_HOME", raising=False)
        monkeypatch.delenv("ORIGINAL_HOME", raising=False)
        importlib.reload(mms_events)


def test_broker_credentials_and_cache_use_selected_config_root(monkeypatch, tmp_path):
    import mms_broker

    real_home = tmp_path / "real-home"
    stable_root = real_home / ".config" / "mms"
    preview_root = tmp_path / "mms-next"
    stable_root.mkdir(parents=True)
    preview_root.mkdir(parents=True)
    (stable_root / "credentials.sh").write_text(
        "export MMS_TEST_BROKER_DEVICE_KEY='stable-secret'\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("MMS_TEST_BROKER_DEVICE_KEY", raising=False)
    monkeypatch.setenv("MMS_REAL_HOME", str(real_home))
    monkeypatch.setenv("REAL_HOME", str(real_home))
    monkeypatch.setenv("ORIGINAL_HOME", str(real_home))
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))

    reloaded = importlib.reload(mms_broker)
    profile = {
        "id": "broker-a",
        "broker_base_url": "http://127.0.0.1:17777",
        "device_key_env": "MMS_TEST_BROKER_DEVICE_KEY",
    }
    try:
        env = reloaded._build_broker_env(profile, workspace_root=str(tmp_path))
        assert env["CC_BROKER_DEVICE_KEY"] == ""
        assert reloaded._broker_credentials_path() == str(preview_root / "credentials.sh")
        assert reloaded._broker_cache_dir() == str(preview_root / "cache" / "broker")

        (preview_root / "credentials.sh").write_text(
            "export MMS_TEST_BROKER_DEVICE_KEY='preview-secret'\n",
            encoding="utf-8",
        )
        reloaded._load_env_file.cache_clear()
        env = reloaded._build_broker_env(profile, workspace_root=str(tmp_path))
        assert env["CC_BROKER_DEVICE_KEY"] == "preview-secret"
    finally:
        monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
        monkeypatch.delenv("MMS_REAL_HOME", raising=False)
        monkeypatch.delenv("REAL_HOME", raising=False)
        monkeypatch.delenv("ORIGINAL_HOME", raising=False)
        reloaded._load_env_file.cache_clear()
        importlib.reload(mms_broker)


def test_statusline_reads_route_and_health_from_selected_config_root(tmp_path):
    script = Path(__file__).resolve().parents[1] / "statusline-command.sh"
    real_home = tmp_path / "real-home"
    stable_root = real_home / ".config" / "mms"
    preview_root = tmp_path / "mms-next"
    gateway_home = stable_root / "claude-gateway" / "s" / "12345"
    stable_root.mkdir(parents=True)
    preview_root.mkdir(parents=True)
    gateway_home.mkdir(parents=True)
    (stable_root / "route_status.json").write_text(
        json.dumps({"tier": "heavy", "model": "claude-stable-20260101"}),
        encoding="utf-8",
    )
    (gateway_home / ".config" / "mms").mkdir(parents=True)
    (gateway_home / ".config" / "mms" / "route_status.json").write_text(
        json.dumps({"tier": "heavy", "model": "claude-session-stable-20260101"}),
        encoding="utf-8",
    )
    (preview_root / "route_status.json").write_text(
        json.dumps({"tier": "light", "model": "claude-preview-20260101", "context_window_tokens": 1_000_000}),
        encoding="utf-8",
    )
    (preview_root / "health-cache.json").write_text(
        json.dumps(
            {
                "records": {
                    "claude-preview-20260101": {
                        "status": "ok",
                        "checked_at": datetime.now().astimezone().isoformat(),
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    payload = {
        "model": {"display_name": "Sonnet"},
        "workspace": {"current_dir": str(tmp_path)},
        "context_window": {
            "used_percentage": 1,
            "total_input_tokens": 1000,
            "total_output_tokens": 2000,
            "context_window_size": 200000,
        },
        "cost": {"total_cost_usd": 0, "total_duration_ms": 0},
    }
    env = {
        **os.environ,
        "HOME": str(gateway_home),
        "XDG_CONFIG_HOME": str(real_home / ".config"),
        "MMS_REAL_HOME": str(real_home),
        "REAL_HOME": str(real_home),
        "ORIGINAL_HOME": str(real_home),
        "MMS_CONFIG_ROOT": str(preview_root),
        "TMPDIR": str(tmp_path) + os.sep,
    }
    result = subprocess.run(
        ["bash", str(script)],
        input=json.dumps(payload),
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "preview" in result.stdout
    assert "stable" not in result.stdout
    assert "3k/1M" in result.stdout
    assert "●" in result.stdout


def test_statusline_strips_gateway_xdg_without_explicit_root(tmp_path):
    script = Path(__file__).resolve().parents[1] / "statusline-command.sh"
    real_home = tmp_path / "real-home"
    stable_root = real_home / ".config" / "mms"
    gateway_home = stable_root / "claude-gateway" / "s" / "12345"
    stable_root.mkdir(parents=True)
    gateway_home.mkdir(parents=True)
    (stable_root / "route_status.json").write_text(
        json.dumps({"tier": "heavy", "model": "claude-stable-20260101"}),
        encoding="utf-8",
    )
    (stable_root / "health-cache.json").write_text(
        json.dumps(
            {
                "records": {
                    "claude-stable-20260101": {
                        "status": "ok",
                        "checked_at": datetime.now().astimezone().isoformat(),
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    payload = {
        "model": {"display_name": "Sonnet"},
        "workspace": {"current_dir": str(tmp_path)},
        "context_window": {
            "used_percentage": 1,
            "total_input_tokens": 1000,
            "total_output_tokens": 2000,
            "context_window_size": 200000,
        },
        "cost": {"total_cost_usd": 0, "total_duration_ms": 0},
    }
    env = {
        **os.environ,
        "HOME": str(gateway_home),
        "XDG_CONFIG_HOME": str(gateway_home / ".config"),
        "MMS_REAL_HOME": str(real_home),
        "REAL_HOME": str(real_home),
        "ORIGINAL_HOME": str(real_home),
        "TMPDIR": str(tmp_path) + os.sep,
    }
    env.pop("MMS_CONFIG_ROOT", None)
    env.pop("MMS_CONFIG_DIR", None)
    result = subprocess.run(
        ["bash", str(script)],
        input=json.dumps(payload),
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "stable" in result.stdout
    assert "●" in result.stdout


def test_claude_route_status_path_uses_selected_root_when_explicit(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    preview_root = tmp_path / "mms-next"
    monkeypatch.setenv("MMS_REAL_HOME", str(real_home))
    monkeypatch.setenv("REAL_HOME", str(real_home))
    monkeypatch.setenv("ORIGINAL_HOME", str(real_home))
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))

    assert mms_launchers._claude_route_status_paths() == [str(preview_root / "route_status.json")]


def test_rescue_launch_env_uses_selected_config_root(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    preview_root = tmp_path / "mms-next"
    stable_root = real_home / ".config" / "mms"
    gateway_home = stable_root / "codex-gateway" / "s" / "4174"
    gateway_home.mkdir(parents=True)

    monkeypatch.setenv("HOME", str(gateway_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(gateway_home / ".config"))
    monkeypatch.setenv("MMS_REAL_HOME", str(real_home))
    monkeypatch.setenv("REAL_HOME", str(real_home))
    monkeypatch.setenv("ORIGINAL_HOME", str(real_home))
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))

    env: dict[str, str] = {}
    mms_launchers._inject_rescue_launch_env(env)

    assert env["MMS_RESCUE_CONFIG_ROOT"] == str(preview_root)
    assert env["MMS_RESCUE_CONFIG_ROOT"] != str(stable_root)


def test_rescue_launch_env_preserves_explicit_rescue_root(monkeypatch, tmp_path):
    import mms_launchers

    preview_root = tmp_path / "mms-next"
    explicit_rescue_root = tmp_path / "explicit-rescue-root"
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))

    env = {"MMS_RESCUE_CONFIG_ROOT": str(explicit_rescue_root)}
    mms_launchers._inject_rescue_launch_env(env)

    assert env["MMS_RESCUE_CONFIG_ROOT"] == str(explicit_rescue_root)


def test_home_context_reports_selected_config_root(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    stable_root = real_home / ".config" / "mms"
    preview_root = tmp_path / "outside-preview-root"
    gateway_home = stable_root / "codex-gateway" / "s" / "4174"
    gateway_home.mkdir(parents=True)
    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    monkeypatch.delenv("MMS_CONFIG_DIR", raising=False)

    env = {
        "HOME": str(gateway_home),
        "XDG_CONFIG_HOME": str(gateway_home / ".config"),
        "MMS_REAL_HOME": str(real_home),
        "REAL_HOME": str(real_home),
        "ORIGINAL_HOME": str(real_home),
        "MMS_CONFIG_ROOT": str(preview_root),
    }

    context = mms_launchers._build_home_context(env, {"auth_mode": "api_key"}, "codex")
    validated = mms_launchers._validate_home_context_or_exit(context)

    assert context["config_root"] == str(preview_root)
    assert context["config_root_explicit"] is True
    assert validated["config_root"] == str(preview_root)
    assert context["config_root"] != str(stable_root)


def test_home_context_defaults_to_stable_root_without_explicit_root(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    stable_root = real_home / ".config" / "mms"
    gateway_home = stable_root / "codex-gateway" / "s" / "4174"
    gateway_home.mkdir(parents=True)
    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    monkeypatch.delenv("MMS_CONFIG_DIR", raising=False)

    context = mms_launchers._build_home_context(
        {
            "HOME": str(gateway_home),
            "XDG_CONFIG_HOME": str(gateway_home / ".config"),
            "MMS_REAL_HOME": str(real_home),
            "REAL_HOME": str(real_home),
            "ORIGINAL_HOME": str(real_home),
        },
        {"auth_mode": "api_key"},
        "codex",
    )

    assert context["config_root"] == str(stable_root)
    assert context["config_root_explicit"] is False


def test_model_context_overrides_follow_selected_config_root(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    stable_root = real_home / ".config" / "mms"
    preview_root = real_home / ".config" / "mms-next"
    stable_root.mkdir(parents=True)
    preview_root.mkdir(parents=True)
    (stable_root / "model-context-overrides.json").write_text(
        json.dumps({"models": {"root-selected-model": 111_000}}),
        encoding="utf-8",
    )
    (preview_root / "model-context-overrides.json").write_text(
        json.dumps({"models": {"root-selected-model": 222_000}}),
        encoding="utf-8",
    )
    mms_launchers._MODEL_CONTEXT_OVERRIDES_CACHE.update({"path": None, "mtime": None, "data": {"models": {}, "provider_overrides": {}}})

    monkeypatch.setenv("MMS_REAL_HOME", str(real_home))
    monkeypatch.setenv("REAL_HOME", str(real_home))
    monkeypatch.setenv("ORIGINAL_HOME", str(real_home))
    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    monkeypatch.delenv("MMS_CONFIG_DIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    assert mms_launchers._lookup_context_window("root-selected-model") == 111_000

    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))

    assert mms_launchers._lookup_context_window("root-selected-model") == 222_000
    assert mms_launchers._MODEL_CONTEXT_OVERRIDES_CACHE["path"] == str(preview_root / "model-context-overrides.json")


def test_mmf_wrapper_selects_mms_next_without_stable_fallback(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    real_home = tmp_path / "real-home"
    gateway_home = real_home / ".config" / "mms" / "codex-gateway" / "s" / "4174"
    gateway_home.mkdir(parents=True)

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(gateway_home),
            "XDG_CONFIG_HOME": str(gateway_home / ".config"),
            "MMS_REAL_HOME": str(real_home),
            "REAL_HOME": str(real_home),
            "ORIGINAL_HOME": str(real_home),
        }
    )
    env.pop("MMS_CONFIG_ROOT", None)
    env.pop("MMS_CONFIG_DIR", None)
    env.pop("MMS_COMMAND_NAME", None)

    result = subprocess.run(
        [sys.executable, str(repo_root / "mmf"), "config", "root", "--json"],
        cwd=repo_root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    status = json.loads(result.stdout.strip())
    expected_preview_root = real_home / ".config" / "mms-next"
    assert status["command"] == "mmf"
    assert status["mode"] == "preview"
    assert status["root_source"] == "MMS_CONFIG_ROOT"
    assert status["config_root"] == str(expected_preview_root)
    assert status["config_path"] == str(expected_preview_root / "config.toml")
    stable_root = real_home / ".config" / "mms"
    assert not (stable_root / "config.toml").exists()
    assert not (stable_root / "credentials.sh").exists()
    assert not (stable_root / "cache").exists()


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
        json.dumps(
            {
                "theme": "dark",
                "hooks": {"preToolUse": [{"matcher": "*"}]},
                "statusLine": {"type": "command", "command": "/tmp/status.sh"},
                "permissions": {"allow": ["Read"]},
            }
        ),
        encoding="utf-8",
    )

    _sync_claude_session_state_to_account_home(str(session_home), str(account_home))

    assert json.loads((account_home / ".claude.json").read_text(encoding="utf-8"))["userID"] == "device-b"
    settings = json.loads((account_home / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert settings["theme"] == "dark"
    assert settings["hooks"]["preToolUse"][0]["matcher"] == "*"
    assert settings["statusLine"]["command"] == "/tmp/status.sh"
    assert settings["permissions"]["allow"] == ["Read"]


def test_copy_claude_state_json_strips_restore_state(tmp_path):
    from mms_launchers import _copy_claude_state_json

    src = tmp_path / "src.json"
    dst = tmp_path / "nested" / "dst.json"
    src.write_text(
        json.dumps(
            {
                "projects": {"/tmp/demo-project": {"lastSessionId": "abc", "lastCost": 99}},
                "lastSessionId": "global-session",
                "lastCost": 123,
                "bypassPermissionsModeAccepted": True,
                "alwaysThinkingEnabled": True,
            }
        ),
        encoding="utf-8",
    )

    _copy_claude_state_json(str(src), str(dst))

    result = json.loads(dst.read_text(encoding="utf-8"))
    assert "projects" not in result
    assert "lastSessionId" not in result
    assert "lastCost" not in result
    assert result["bypassPermissionsModeAccepted"] is True
    assert result["alwaysThinkingEnabled"] is True


def test_ensure_claude_project_trust_marks_current_project_accepted(tmp_path):
    from mms_launchers import _ensure_claude_project_trust

    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    result = _ensure_claude_project_trust({"numStartups": 1}, str(project_dir))
    entry = result["projects"][str(project_dir.resolve())]

    assert entry["hasTrustDialogAccepted"] is True
    assert entry["hasCompletedProjectOnboarding"] is True
    assert entry["allowedTools"] == []
    assert entry["enabledMcpjsonServers"] == []
    assert entry["hasClaudeMdExternalIncludesApproved"] is True
    assert entry["hasClaudeMdExternalIncludesWarningShown"] is True
    assert entry["projectOnboardingSeenCount"] == 1


def test_load_project_scoped_claude_resume_session_id_is_project_scoped(monkeypatch, tmp_path):
    import mms_launchers

    project_dir = tmp_path / "repo"
    other_project = tmp_path / "other"
    project_dir.mkdir()
    other_project.mkdir()

    monkeypatch.setattr(
        mms_launchers,
        "list_indexed_sessions",
        lambda _cli="claude": [
            {
                "project_path": str(other_project.resolve()),
                "account_id": "relay-a",
                "runtime_kind": "api_key",
                "session_id": "session-other-project",
                "last_active_at": "2026-04-16T11:00:00+00:00",
            },
            {
                "project_path": str(project_dir.resolve()),
                "account_id": "relay-b",
                "runtime_kind": "api_key",
                "session_id": "session-other-account",
                "last_active_at": "2026-04-16T16:00:00+00:00",
            },
            {
                "project_path": str(project_dir.resolve()),
                "account_id": "relay-a",
                "runtime_kind": "oauth",
                "session_id": "session-other-runtime",
                "last_active_at": "2026-04-16T13:00:00+00:00",
            },
            {
                "project_path": str(project_dir.resolve()),
                "account_id": "relay-a",
                "runtime_kind": "api_key",
                "resume_model": "qwen3-coder-plus",
                "session_id": "pid-9999",
                "last_active_at": "2026-04-16T14:00:00+00:00",
            },
            {
                "project_path": str(project_dir.resolve()),
                "account_id": "relay-a",
                "runtime_kind": "api_key",
                "resume_model": "claude-sonnet-4-6",
                "session_id": "session-match",
                "last_active_at": "2026-04-16T15:00:00+00:00",
            },
        ],
    )

    result = mms_launchers._load_project_scoped_claude_resume_session_id(
        str(project_dir),
        account_id="relay-a",
        runtime_kind="api_key",
        resume_model="claude-sonnet-4-6",
    )

    assert result == "session-other-account"


def test_load_project_scoped_claude_resume_session_id_does_not_require_matching_model(monkeypatch, tmp_path):
    import mms_launchers

    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    monkeypatch.setattr(
        mms_launchers,
        "list_indexed_sessions",
        lambda _cli="claude": [
            {
                "project_path": str(project_dir.resolve()),
                "account_id": "relay-a",
                "runtime_kind": "api_key",
                "resume_model": "qwen3-coder-plus",
                "session_id": "session-qwen",
                "last_active_at": "2026-04-16T12:00:00+00:00",
            },
            {
                "project_path": str(project_dir.resolve()),
                "account_id": "relay-a",
                "runtime_kind": "api_key",
                "resume_model": "gpt-5.4",
                "session_id": "session-gpt",
                "last_active_at": "2026-04-16T13:00:00+00:00",
            },
        ],
    )

    result = mms_launchers._load_project_scoped_claude_resume_session_id(
        str(project_dir),
        account_id="relay-a",
        runtime_kind="api_key",
        resume_model="claude-sonnet-4-6",
    )

    assert result == "session-gpt"


def test_sync_claude_session_state_back_to_account_strips_restore_state(tmp_path):
    from mms_launchers import _sync_claude_session_state_to_account_home

    session_home = tmp_path / "session"
    account_home = tmp_path / "account"
    (session_home / ".claude").mkdir(parents=True)

    (session_home / ".claude.json").write_text(
        json.dumps(
            {
                "userID": "device-b",
                "projects": {"/tmp/demo-project": {"lastSessionId": "abc", "lastCost": 99}},
                "lastSessionId": "global-session",
                "lastCost": 123,
                "numStartups": 3,
            }
        ),
        encoding="utf-8",
    )
    (session_home / ".claude" / "settings.json").write_text(
        json.dumps({"theme": "dark"}),
        encoding="utf-8",
    )

    _sync_claude_session_state_to_account_home(str(session_home), str(account_home))

    result = json.loads((account_home / ".claude.json").read_text(encoding="utf-8"))
    assert result["userID"] == "device-b"
    assert result["numStartups"] == 3
    assert "projects" not in result
    assert "lastSessionId" not in result
    assert "lastCost" not in result
    assert json.loads((account_home / ".claude" / "settings.json").read_text(encoding="utf-8")) == {"theme": "dark"}


def test_sync_claude_session_state_back_to_account_keeps_safe_project_state(tmp_path):
    from mms_launchers import _sync_claude_session_state_to_account_home

    session_home = tmp_path / "session"
    account_home = tmp_path / "account"
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    (session_home / ".claude").mkdir(parents=True)

    (session_home / ".claude.json").write_text(
        json.dumps(
            {
                "userID": "device-b",
                "projects": {
                    str(project_dir.resolve()): {
                        "hasCompletedProjectOnboarding": True,
                        "hasClaudeMdExternalIncludesApproved": True,
                        "hasClaudeMdExternalIncludesWarningShown": True,
                        "projectOnboardingSeenCount": 2,
                        "lastSessionId": "global-session",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (session_home / ".claude" / "settings.json").write_text(json.dumps({}), encoding="utf-8")

    _sync_claude_session_state_to_account_home(str(session_home), str(account_home))

    result = json.loads((account_home / ".claude.json").read_text(encoding="utf-8"))
    project_state = result["projects"][str(project_dir.resolve())]
    assert project_state["hasCompletedProjectOnboarding"] is True
    assert project_state["hasClaudeMdExternalIncludesApproved"] is True
    assert project_state["hasClaudeMdExternalIncludesWarningShown"] is True
    assert project_state["projectOnboardingSeenCount"] == 2
    assert "lastSessionId" not in project_state


def test_sync_claude_session_state_back_to_account_merges_tips_history(tmp_path):
    from mms_launchers import _sync_claude_session_state_to_account_home

    session_home = tmp_path / "session"
    account_home = tmp_path / "account"
    (session_home / ".claude").mkdir(parents=True)
    account_home.mkdir()

    (account_home / ".claude.json").write_text(
        json.dumps(
            {
                "tipsHistory": {
                    "theme-command": 4,
                    "terminal-setup": 1,
                }
            }
        ),
        encoding="utf-8",
    )
    (session_home / ".claude.json").write_text(
        json.dumps(
            {
                "tipsHistory": {
                    "theme-command": 2,
                    "terminal-setup": 3,
                    "memory-command": 1,
                }
            }
        ),
        encoding="utf-8",
    )
    (session_home / ".claude" / "settings.json").write_text(json.dumps({}), encoding="utf-8")

    _sync_claude_session_state_to_account_home(str(session_home), str(account_home))

    result = json.loads((account_home / ".claude.json").read_text(encoding="utf-8"))
    assert result["tipsHistory"]["theme-command"] == 4
    assert result["tipsHistory"]["terminal-setup"] == 3
    assert result["tipsHistory"]["memory-command"] == 1


def test_sync_claude_session_state_back_to_account_keeps_newer_oauth_token(tmp_path):
    from mms_launchers import _sync_claude_session_state_to_account_home

    session_home = tmp_path / "session"
    account_home = tmp_path / "account"
    (session_home / ".claude").mkdir(parents=True)
    (account_home / ".claude").mkdir(parents=True)

    (account_home / ".claude.json").write_text(
        json.dumps(
            {
                "userID": "device-a",
                "numStartups": 5,
                "claudeAiOauth": {
                    "accessToken": "tok-fresh",
                    "refreshToken": "refresh-fresh",
                    "expiresAt": "2026-04-20T10:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )
    (session_home / ".claude.json").write_text(
        json.dumps(
            {
                "userID": "device-b",
                "numStartups": 3,
                "claudeAiOauth": {
                    "accessToken": "tok-old",
                    "refreshToken": "refresh-old",
                    "expiresAt": "2026-04-16T10:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )
    (session_home / ".claude" / "settings.json").write_text(json.dumps({}), encoding="utf-8")

    _sync_claude_session_state_to_account_home(str(session_home), str(account_home))

    result = json.loads((account_home / ".claude.json").read_text(encoding="utf-8"))
    assert result["userID"] == "device-b"
    assert result["numStartups"] == 5
    assert result["claudeAiOauth"]["accessToken"] == "tok-fresh"
    assert result["claudeAiOauth"]["refreshToken"] == "refresh-fresh"


def test_apply_runtime_network_profile_injects_proxy_timezone_locale_and_ipv4():
    from mms_launchers import _apply_runtime_network_profile

    env = {"KEEP": "1"}
    runtime = {
        "id": "claude-b",
        "proxy": "http://127.0.0.1:7890",
        "no_proxy": "localhost,127.0.0.1",
        "timezone": "Asia/Singapore",
        "force_ipv4": True,
    }

    with patch("mms_launchers._check_proxy_connectivity_or_exit") as check_proxy:
        result = _apply_runtime_network_profile(env, runtime, validate_proxy=True)

    check_proxy.assert_called_once_with(
        "http://127.0.0.1:7890",
        "localhost,127.0.0.1",
        label="claude-b",
        force_ipv4=True,
    )
    assert result["KEEP"] == "1"
    assert result["HTTP_PROXY"] == "http://127.0.0.1:7890"
    assert result["HTTPS_PROXY"] == "http://127.0.0.1:7890"
    assert result["NO_PROXY"] == "localhost,127.0.0.1"
    assert result["TZ"] == "Asia/Singapore"
    assert result["LANG"] == "en_US.UTF-8"
    assert result["MMS_FORCE_IPV4"] == "1"
    assert "--dns-result-order=ipv4first" in result["NODE_OPTIONS"]


def test_apply_runtime_network_profile_clears_inherited_proxy_when_runtime_is_direct(monkeypatch):
    from mms_launchers import _apply_runtime_network_profile

    env = {
        "HTTP_PROXY": "http://127.0.0.1:7890",
        "HTTPS_PROXY": "http://127.0.0.1:7890",
        "NO_PROXY": "localhost",
        "MMS_FAKE_UPSTREAM_MODE": "upstream-proxy",
        "NODE_EXTRA_CA_CERTS": "/tmp/mms-ca.pem",
    }

    result = _apply_runtime_network_profile(env, {"id": "direct-runtime"}, validate_proxy=False)

    assert "HTTP_PROXY" not in result
    assert "HTTPS_PROXY" not in result
    assert "NO_PROXY" not in result
    assert "MMS_FAKE_UPSTREAM_MODE" not in result
    assert "NODE_EXTRA_CA_CERTS" not in result


def test_normalize_account_keeps_proxy_and_timezone():
    from mms_core import _normalize_account

    account = _normalize_account(
        {
            "id": "claude-b",
            "cli": "claude",
            "proxy": "http://127.0.0.1:7890",
            "no_proxy": "localhost",
            "timezone": "Asia/Singapore",
        }
    )

    assert account["proxy"] == "http://127.0.0.1:7890"
    assert account["no_proxy"] == "localhost"
    assert account["timezone"] == "Asia/Singapore"


def test_normalize_account_defaults_timezone_to_singapore():
    from mms_core import DEFAULT_ACCOUNT_TIMEZONE, _normalize_account

    account = _normalize_account(
        {
            "id": "claude-default",
            "cli": "claude",
        }
    )

    assert account["timezone"] == DEFAULT_ACCOUNT_TIMEZONE


def test_normalize_provider_keeps_proxy_and_timezone():
    from mms_core import _normalize_provider

    provider = _normalize_provider(
        {
            "id": "gateway-b",
            "proxy": "http://127.0.0.1:7890",
            "no_proxy": "localhost",
            "timezone": "America/Los_Angeles",
        }
    )

    assert provider["proxy"] == "http://127.0.0.1:7890"
    assert provider["no_proxy"] == "localhost"
    assert provider["timezone"] == "America/Los_Angeles"


def test_normalize_provider_defaults_timezone_to_singapore():
    from mms_core import DEFAULT_ACCOUNT_TIMEZONE, _normalize_provider

    provider = _normalize_provider({"id": "gateway-default"})

    assert provider["timezone"] == DEFAULT_ACCOUNT_TIMEZONE


def test_prompt_proxy_fields_skips_no_proxy_when_proxy_empty(monkeypatch):
    import mms_core

    prompts = []

    def fake_ask(label, **kwargs):
        prompts.append(str(label))
        return ""

    monkeypatch.setattr(mms_core, "Prompt", SimpleNamespace(ask=fake_ask))

    proxy, no_proxy = mms_core._prompt_validated_proxy_fields("", "", wizard=False)

    assert (proxy, no_proxy) == ("", "")
    assert len(prompts) == 1
    assert "NO_PROXY" not in prompts[0]


def test_resolve_interactive_launch_model_selects_fresh_model_for_broker():
    import mms_core

    runtime = {"runtime_kind": "broker", "auth_mode": "broker_profile"}
    seen = {}

    with patch.object(mms_core, "_ensure_models_cache_available", return_value=True), patch.object(
        mms_core,
        "display_models",
        side_effect=lambda models, _role, _recommend: seen.setdefault("models", list(models)) or list(models),
    ), patch.object(
        mms_core,
        "select_model_interactive",
        return_value="glm-5.1",
    ):
        ok, model = mms_core._resolve_interactive_launch_model(
            "claude",
            runtime,
            ["glm-5.1", "MiniMax-M2.7"],
            ["qwen3-coder-plus"],
            "all",
            ["glm-5.1"],
        )

    assert ok is True
    assert model == "glm-5.1"
    assert seen["models"] == ["glm-5.1", "MiniMax-M2.7"]


def test_resolve_interactive_launch_model_for_native_account_skips_selection():
    import mms_core

    runtime = {"auth_mode": "oauth"}

    with patch.object(mms_core, "select_model_interactive") as select_mock:
        ok, model = mms_core._resolve_interactive_launch_model(
            "claude",
            runtime,
            ["glm-5.1"],
            ["qwen3-coder-plus"],
            "all",
            ["glm-5.1"],
        )

    assert ok is True
    assert model is None
    select_mock.assert_not_called()


def test_snapshot_file_entry_ignores_claude_runtime_noise(tmp_path):
    import mms_core

    path = tmp_path / ".claude.json"
    path.write_text(
        json.dumps(
            {
                "userID": "user-1",
                "numStartups": 1,
                "projects": {"/tmp/repo": {"lastSessionId": "a", "lastCost": 1}},
                "oauthAccount": {
                    "accountUuid": "acct-1",
                    "emailAddress": "u@example.com",
                    "organizationUuid": "org-1",
                    "displayName": "User",
                },
            }
        ),
        encoding="utf-8",
    )
    first = mms_core._snapshot_file_entry(str(path))

    path.write_text(
        json.dumps(
            {
                "userID": "user-1",
                "numStartups": 99,
                "projects": {"/tmp/repo": {"lastSessionId": "b", "lastCost": 999}},
                "oauthAccount": {
                    "accountUuid": "acct-1",
                    "emailAddress": "u@example.com",
                    "organizationUuid": "org-1",
                    "displayName": "User",
                },
            }
        ),
        encoding="utf-8",
    )
    second = mms_core._snapshot_file_entry(str(path))

    assert first["sha256"] == second["sha256"]
    assert first["normalized_kind"] == "claude_state_identity"


def test_snapshot_file_entry_detects_claude_identity_change(tmp_path):
    import mms_core

    path = tmp_path / ".claude.json"
    path.write_text(
        json.dumps(
            {
                "userID": "user-1",
                "oauthAccount": {
                    "accountUuid": "acct-1",
                    "emailAddress": "u@example.com",
                    "organizationUuid": "org-1",
                },
            }
        ),
        encoding="utf-8",
    )
    first = mms_core._snapshot_file_entry(str(path))

    path.write_text(
        json.dumps(
            {
                "userID": "user-2",
                "oauthAccount": {
                    "accountUuid": "acct-2",
                    "emailAddress": "u@example.com",
                    "organizationUuid": "org-1",
                },
            }
        ),
        encoding="utf-8",
    )
    second = mms_core._snapshot_file_entry(str(path))

    assert first["sha256"] != second["sha256"]


def test_snapshot_file_entry_ignores_claude_settings_session_env_noise(tmp_path):
    import mms_core

    path = tmp_path / ".claude" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "env": {
                    "HTTP_PROXY": "http://127.0.0.1:7890",
                    "NODE_EXTRA_CA_CERTS": "/tmp/ca.pem",
                    "CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
                },
                "statusLine": {"type": "command", "command": "/tmp/status.sh"},
            }
        ),
        encoding="utf-8",
    )
    first = mms_core._snapshot_file_entry(str(path))

    path.write_text(
        json.dumps(
            {
                "env": {
                    "HTTP_PROXY": "http://127.0.0.1:9999",
                    "NODE_EXTRA_CA_CERTS": "/tmp/other-ca.pem",
                    "CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
                },
                "statusLine": {"type": "command", "command": "/tmp/status.sh"},
            }
        ),
        encoding="utf-8",
    )
    second = mms_core._snapshot_file_entry(str(path))

    assert first["sha256"] == second["sha256"]
    assert first["normalized_kind"] == "claude_settings_runtime_stripped"


def test_detect_working_base_url_uses_runtime_proxy(monkeypatch):
    import mms_core

    calls = {}

    class FakeResponse:
        status_code = 200

    def fake_request(method, url, **kwargs):
        calls["method"] = method
        calls["url"] = url
        calls["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr(mms_core, "_runtime_httpx_request", fake_request)

    candidate = mms_core.detect_working_base_url(
        "https://gateway.example.com",
        "/v1/messages",
        {"x-api-key": "sk-test"},
        body=b"{}",
        runtime={"proxy": "http://127.0.0.1:7890"},
    )

    assert candidate == "https://gateway.example.com"
    assert calls["method"] == "POST"
    assert calls["kwargs"]["runtime"]["proxy"] == "http://127.0.0.1:7890"


def test_probe_models_uses_provider_proxy(monkeypatch):
    import mms_core

    calls = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"data": [{"id": "claude-sonnet-4-6"}]}

    def fake_request(method, url, **kwargs):
        calls["method"] = method
        calls["url"] = url
        calls["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr(mms_core, "_runtime_httpx_request", fake_request)
    monkeypatch.setattr(mms_core, "_save_probe_file_cache", lambda *args, **kwargs: None)

    result = mms_core._probe_models(
        {
            "id": "gateway-proxy",
            "base_url": "https://gateway.example.com",
            "api_key": "sk-test",
            "protocols": ["openai_chat_completions"],
            "proxy": "http://127.0.0.1:7890",
        },
        emit_output=False,
        force_refresh=True,
        skip_cache=True,
    )

    assert result["models"] == ["claude-sonnet-4-6"]
    assert calls["method"] == "GET"
    assert calls["kwargs"]["runtime"]["proxy"] == "http://127.0.0.1:7890"


def test_gateway_ping_uses_runtime_proxy(monkeypatch):
    import mms_launchers

    calls = {}

    def fake_request(method, url, **kwargs):
        calls["method"] = method
        calls["url"] = url
        calls["kwargs"] = kwargs
        return types.SimpleNamespace(status_code=200)

    monkeypatch.setattr(mms_launchers, "_runtime_httpx_request", fake_request)
    monkeypatch.setattr(mms_launchers, "_build_gateway_url", lambda base_url, path: f"{base_url.rstrip('/')}{path}")

    ok = mms_launchers._gateway_ping(
        "https://gateway.example.com/v1",
        "sk-test",
        runtime={"proxy": "http://127.0.0.1:7890"},
    )

    assert ok is True
    assert calls["method"] == "GET"
    assert calls["kwargs"]["runtime"]["proxy"] == "http://127.0.0.1:7890"


def test_gateway_ping_rejects_401(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(
        mms_launchers,
        "_runtime_httpx_request",
        lambda *args, **kwargs: types.SimpleNamespace(status_code=401),
    )
    monkeypatch.setattr(mms_launchers, "_build_gateway_url", lambda base_url, path: f"{base_url.rstrip('/')}{path}")

    ok = mms_launchers._gateway_ping(
        "https://gateway.example.com/v1",
        "sk-test",
        runtime={"proxy": "http://127.0.0.1:7890"},
    )

    assert ok is False


def test_validate_proxy_url_accepts_mainstream_formats():
    from mms_core import _validate_proxy_url

    assert _validate_proxy_url("http://user:pass@198.51.100.24:6394") is None
    assert _validate_proxy_url("socks5h://127.0.0.1:7890") is None


def test_validate_proxy_url_rejects_invalid_scheme():
    from mms_core import _validate_proxy_url

    assert _validate_proxy_url("socket5://127.0.0.1:7890") == "代理协议仅支持 http / https / socks5 / socks5h"


def test_runtime_httpx_request_prefers_ipv4(monkeypatch):
    import mms_core

    calls = {}

    class FakeTransport:
        def __init__(self, **kwargs):
            calls["transport_kwargs"] = kwargs

    class FakeClient:
        def __init__(self, *, transport=None, follow_redirects=False):
            calls["follow_redirects"] = follow_redirects
            calls["transport"] = transport

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def request(self, method, url, **kwargs):
            calls["method"] = method
            calls["url"] = url
            calls["request_kwargs"] = kwargs
            return types.SimpleNamespace(status_code=200)

    monkeypatch.setattr(
        mms_core,
        "httpx",
        types.SimpleNamespace(HTTPTransport=FakeTransport, Client=FakeClient),
    )

    response = mms_core._runtime_httpx_request(
        "GET",
        "https://gateway.example.com/models",
        runtime={"force_ipv4": True, "proxy": "http://127.0.0.1:7890"},
        headers={"Authorization": "Bearer sk-test"},
        timeout=8,
    )

    assert response.status_code == 200
    assert calls["transport_kwargs"]["proxy"] == "http://127.0.0.1:7890"
    assert calls["transport_kwargs"]["trust_env"] is False
    assert calls["transport_kwargs"]["local_address"] == "0.0.0.0"
    assert calls["request_kwargs"]["headers"]["Authorization"] == "Bearer sk-test"
    assert calls["request_kwargs"]["headers"]["User-Agent"] == "MMS/1.0"


def test_runtime_httpx_request_disables_ambient_env_for_official_anthropic(monkeypatch):
    import mms_core

    calls = {}

    class FakeTransport:
        def __init__(self, **kwargs):
            calls["transport_kwargs"] = kwargs

    class FakeClient:
        def __init__(self, *, transport=None, follow_redirects=False):
            calls["transport"] = transport
            calls["follow_redirects"] = follow_redirects

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def request(self, method, url, **kwargs):
            calls["method"] = method
            calls["url"] = url
            calls["request_kwargs"] = kwargs
            return types.SimpleNamespace(status_code=200)

    monkeypatch.setattr(
        mms_core,
        "httpx",
        types.SimpleNamespace(HTTPTransport=FakeTransport, Client=FakeClient),
    )

    response = mms_core._runtime_httpx_request(
        "GET",
        "https://api.anthropic.com/api/oauth/usage",
        runtime={},
        timeout=8,
    )

    assert response.status_code == 200
    assert calls["transport_kwargs"]["trust_env"] is False
    assert "proxy" not in calls["transport_kwargs"]
    assert calls["request_kwargs"]["headers"]["User-Agent"] == "MMS/1.0"


def test_runtime_httpx_request_keeps_existing_env_behavior_for_non_anthropic_direct_runtime(monkeypatch):
    import mms_core

    calls = {}

    class FakeTransport:
        def __init__(self, **kwargs):
            calls["transport_kwargs"] = kwargs

    class FakeClient:
        def __init__(self, *, transport=None, follow_redirects=False):
            calls["transport"] = transport

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def request(self, method, url, **kwargs):
            return types.SimpleNamespace(status_code=200)

    monkeypatch.setattr(
        mms_core,
        "httpx",
        types.SimpleNamespace(HTTPTransport=FakeTransport, Client=FakeClient),
    )

    response = mms_core._runtime_httpx_request(
        "GET",
        "https://gateway.example.com/models",
        runtime={},
        timeout=8,
    )

    assert response.status_code == 200
    assert calls["transport_kwargs"] == {}


def test_apply_runtime_ip_stack_profile_sets_ipv4first():
    from mms_launchers import _apply_runtime_ip_stack_profile

    env = {"NODE_OPTIONS": "--max-old-space-size=4096"}
    runtime = {"id": "claude-b", "force_ipv4": True}

    result = _apply_runtime_ip_stack_profile(env, runtime)

    assert result["MMS_FORCE_IPV4"] == "1"
    assert "--dns-result-order=ipv4first" in result["NODE_OPTIONS"]


def test_test_proxy_connectivity_rejects_http_404(monkeypatch):
    import mms_core

    monkeypatch.setattr(
        mms_core.subprocess,
        "run",
        lambda *args, **kwargs: types.SimpleNamespace(returncode=0, stdout="404", stderr=""),
    )

    ok, detail = mms_core._test_proxy_connectivity("http://127.0.0.1:7890")

    assert ok is False
    assert "HTTP 404" in detail


def test_load_config_does_not_persist_normalization_by_default(monkeypatch, tmp_path):
    import mms_core

    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(mms_core, "_config_write_target_path", lambda: str(config_path))
    monkeypatch.setattr(mms_core, "_ensure_mms_config_guard_files", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_core, "_migrate_legacy_api_config", lambda cfg: cfg)
    monkeypatch.setattr(mms_core, "_merge_base_user_broker_profiles", lambda cfg, path: (cfg, False))
    monkeypatch.setattr(mms_core, "_ensure_provider_config", lambda cfg: ({**cfg, "providers": []}, True))
    monkeypatch.setattr(mms_core, "_ensure_account_config", lambda cfg: (cfg, False))
    monkeypatch.setattr(mms_core, "ensure_broker_config", lambda cfg: (cfg, False))
    monkeypatch.setattr(mms_core, "_normalize_presets_config", lambda cfg: (cfg, False))
    monkeypatch.setattr(mms_core, "_normalize_user_config", lambda cfg: (cfg, False))
    monkeypatch.setattr(mms_core, "_normalize_cache_config", lambda cfg: (cfg, False))
    monkeypatch.setattr(mms_core, "_normalize_load_balance_config", lambda cfg: (cfg, False))

    saved = []
    monkeypatch.setattr(mms_core, "save_config", lambda cfg, reason=None: saved.append((cfg, reason)))

    loaded = mms_core.load_config()

    assert loaded["providers"] == []
    assert saved == []


def test_load_config_persists_when_requested(monkeypatch, tmp_path):
    import mms_core

    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(mms_core, "_config_write_target_path", lambda: str(config_path))
    monkeypatch.setattr(mms_core, "_ensure_mms_config_guard_files", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_core, "_migrate_legacy_api_config", lambda cfg: cfg)
    monkeypatch.setattr(mms_core, "_merge_base_user_broker_profiles", lambda cfg, path: (cfg, False))
    monkeypatch.setattr(mms_core, "_ensure_provider_config", lambda cfg: ({**cfg, "providers": []}, True))
    monkeypatch.setattr(mms_core, "_ensure_account_config", lambda cfg: (cfg, False))
    monkeypatch.setattr(mms_core, "ensure_broker_config", lambda cfg: (cfg, False))
    monkeypatch.setattr(mms_core, "_normalize_presets_config", lambda cfg: (cfg, False))
    monkeypatch.setattr(mms_core, "_normalize_user_config", lambda cfg: (cfg, False))
    monkeypatch.setattr(mms_core, "_normalize_cache_config", lambda cfg: (cfg, False))
    monkeypatch.setattr(mms_core, "_normalize_load_balance_config", lambda cfg: (cfg, False))

    saved = []
    monkeypatch.setattr(mms_core, "save_config", lambda cfg, reason=None: saved.append((cfg, reason)))

    loaded = mms_core.load_config(persist=True)

    assert loaded["providers"] == []
    assert saved and saved[0][1] == "auto:load_config_normalize"


def test_runtime_network_summary_masks_proxy_secret():
    from mms_launchers import _runtime_network_summary

    summary = _runtime_network_summary(
        {
            "proxy": "http://demo-user:demo-pass@198.51.100.24:6394",
            "timezone": "America/Los_Angeles",
            "force_ipv4": True,
        }
    )

    assert "demo-pass" not in summary
    assert "198.51.100.24:6394" in summary
    assert "DNS proxy-likely" in summary
    assert "TZ America/Los_Angeles" in summary
    assert "LANG en_US.UTF-8" in summary
    assert "IPv4 on" in summary


def test_mask_proxy_url_accepts_proxy_fingerprint_value():
    from mms_launchers import _mask_proxy_url

    value = _mask_proxy_url("http://198.51.100.24:6394+auth")

    assert value == "http://198.51.100.24:6394+auth"


def test_validate_home_context_accepts_isolated_oauth_session(tmp_path):
    from mms_launchers import _build_home_context, _validate_home_context_or_exit

    real_home = tmp_path / "real-home"
    account_home = real_home / ".config" / "mms" / "accounts" / "claude-a"
    session_home = account_home / "s" / "12345"

    context = _build_home_context(
        {
            "HOME": str(session_home),
            "MMS_SESSION_HOME": str(session_home),
            "MMS_REAL_HOME": str(real_home),
            "REAL_HOME": str(real_home),
            "ORIGINAL_HOME": str(real_home),
        },
        {
            "id": "claude-a",
            "cli": "claude",
            "auth_mode": "oauth",
            "home_dir": str(account_home),
            "proxy": "http://127.0.0.1:7890",
        },
        "claude",
    )

    result = _validate_home_context_or_exit(context)

    assert result["real_home"] == str(real_home)
    assert result["session_home"] == str(session_home)
    assert result["config_root"] == str(real_home / ".config" / "mms")
    assert result["net_mode"] == "proxy"
    assert result["dns_mode"] == "proxy-likely"
    assert result["locale"] == "en_US.UTF-8"


def test_runtime_locale_env_defaults_to_en_us():
    from mms_launchers import _runtime_locale_env

    result = _runtime_locale_env({})

    assert result["LANG"] == "en_US.UTF-8"
    assert result["LC_ALL"] == "en_US.UTF-8"


def test_runtime_locale_env_supports_zh_language(monkeypatch):
    from mms_launchers import _runtime_locale_env

    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LANG", raising=False)
    result = _runtime_locale_env({"language": "zh"})

    assert result["LANG"] == "zh_CN.UTF-8"
    assert result["LC_MESSAGES"] == "zh_CN.UTF-8"


def test_validate_home_context_blocks_oauth_real_home_leak(tmp_path):
    from mms_launchers import _build_home_context, _validate_home_context_or_exit

    real_home = tmp_path / "real-home"
    account_home = real_home / ".config" / "mms" / "accounts" / "claude-a"

    context = _build_home_context(
        {
            "HOME": str(real_home),
            "MMS_SESSION_HOME": str(real_home),
            "MMS_REAL_HOME": str(real_home),
            "REAL_HOME": str(real_home),
            "ORIGINAL_HOME": str(real_home),
        },
        {
            "id": "claude-a",
            "cli": "claude",
            "auth_mode": "oauth",
            "home_dir": str(account_home),
        },
        "claude",
    )

    with pytest.raises(SystemExit):
        _validate_home_context_or_exit(context)


def test_validate_home_context_blocks_codex_xdg_drift(tmp_path):
    from mms_launchers import _build_home_context, _validate_home_context_or_exit

    real_home = tmp_path / "real-home"
    account_home = real_home / ".config" / "mms" / "accounts" / "codex-a"
    session_home = account_home / "s" / "23456"

    context = _build_home_context(
        {
            "HOME": str(session_home),
            "MMS_SESSION_HOME": str(session_home),
            "MMS_REAL_HOME": str(real_home),
            "REAL_HOME": str(real_home),
            "ORIGINAL_HOME": str(real_home),
            "XDG_CONFIG_HOME": str(real_home / ".config"),
        },
        {
            "id": "codex-a",
            "cli": "codex",
            "auth_mode": "oauth",
            "home_dir": str(account_home),
        },
        "codex",
    )

    with pytest.raises(SystemExit):
        _validate_home_context_or_exit(context)


def test_emit_dns_guard_hint_warns_for_local_dns_risk(capsys):
    from mms_launchers import _emit_dns_guard_hint

    _emit_dns_guard_hint(
        {"proxy": "socks5://127.0.0.1:7890", "auth_mode": "oauth"},
        cli_name="claude",
        auth_mode="oauth",
    )

    captured = capsys.readouterr()
    assert "DNS 风险" in captured.out


def test_emit_dns_guard_hint_silent_for_proxy_likely(capsys):
    from mms_launchers import _emit_dns_guard_hint

    _emit_dns_guard_hint(
        {"proxy": "http://127.0.0.1:7890", "auth_mode": "oauth"},
        cli_name="claude",
        auth_mode="oauth",
    )

    captured = capsys.readouterr()
    assert captured.out == ""


def test_session_required_env_from_runtime_env_keeps_fake_upstream_tls_env():
    from mms_launchers import _session_required_env_from_runtime_env

    result = _session_required_env_from_runtime_env(
        {
            "HTTP_PROXY": "http://127.0.0.1:7890",
            "HTTPS_PROXY": "http://127.0.0.1:7890",
            "NO_PROXY": "127.0.0.1,localhost",
            "TZ": "America/Los_Angeles",
            "LANG": "en_US.UTF-8",
            "LC_ALL": "en_US.UTF-8",
            "SSL_CERT_FILE": "/tmp/mms-ca.pem",
            "NODE_EXTRA_CA_CERTS": "/tmp/mms-ca.pem",
            "MMS_FAKE_UPSTREAM_MODE": "upstream-proxy",
            "MMS_FAKE_UPSTREAM_PROXY": "http://127.0.0.1:8899",
            "MMS_FAKE_UPSTREAM_ORIGINAL_PROXY": "http://198.51.100.24:6394+auth",
            "MMS_FAKE_UPSTREAM_ORIGINAL_NO_PROXY": "",
            "UNRELATED": "skip-me",
        }
    )

    assert result["HTTP_PROXY"] == "http://127.0.0.1:7890"
    assert result["LANG"] == "en_US.UTF-8"
    assert result["LC_ALL"] == "en_US.UTF-8"
    assert result["SSL_CERT_FILE"] == "/tmp/mms-ca.pem"
    assert result["NODE_EXTRA_CA_CERTS"] == "/tmp/mms-ca.pem"
    assert result["MMS_FAKE_UPSTREAM_MODE"] == "upstream-proxy"
    assert "UNRELATED" not in result


def test_sanitize_account_claude_settings_payload_strips_session_env():
    from mms_launchers import _sanitize_account_claude_settings_payload

    result = _sanitize_account_claude_settings_payload(
        {
            "theme": "dark",
            "env": {
                "HTTP_PROXY": "http://127.0.0.1:7890",
                "NODE_EXTRA_CA_CERTS": "/tmp/mms-ca.pem",
                "TZ": "America/Los_Angeles",
                "LANG": "en_US.UTF-8",
                "CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
            },
            "hooks": {"preToolUse": [{"matcher": "*"}]},
            "statusLine": {"type": "command", "command": "/tmp/status.sh"},
            "permissions": {"allow": ["Read"], "deny": ["Bash(rm -rf /)*"]},
        }
    )

    assert "env" not in result
    assert result["theme"] == "dark"
    assert result["hooks"]["preToolUse"][0]["matcher"] == "*"
    assert result["statusLine"]["command"] == "/tmp/status.sh"
    assert result["permissions"]["allow"] == ["Read"]


def test_strip_claude_restore_state_removes_project_resume_noise():
    from mms_launchers import _strip_claude_restore_state

    result = _strip_claude_restore_state(
        {
            "projects": {"/tmp/demo-project": {"lastSessionId": "abc", "lastCost": 99}},
            "lastSessionId": "global-session",
            "lastCost": 123,
            "bypassPermissionsModeAccepted": True,
            "alwaysThinkingEnabled": True,
        }
    )

    assert "projects" not in result
    assert "lastSessionId" not in result
    assert "lastCost" not in result
    assert result["bypassPermissionsModeAccepted"] is True
    assert result["alwaysThinkingEnabled"] is True


def test_strip_claude_restore_state_drops_gateway_sensitive_auth_state():
    from mms_launchers import _strip_claude_restore_state

    result = _strip_claude_restore_state(
        {
            "userID": "device-b",
            "oauthAccount": {"emailAddress": "demo@example.com"},
            "provider": "minimax",
            "api_key": "sk-demo",
            "cachedExtraUsageDisabledReason": "org_level_disabled",
            "passesEligibilityCache": {"org-a": {"eligible": False}},
            "s1mAccessCache": {"org-a": {"hasAccess": False}},
            "hasAvailableSubscription": False,
            "penguinModeOrgEnabled": False,
            "customApiKeyResponses": {"demo": "x"},
            "subscriptionNoticeCount": 3,
            "bypassPermissionsModeAccepted": True,
        },
        strip_sensitive_auth=True,
    )

    for key in (
        "userID",
        "oauthAccount",
        "provider",
        "api_key",
        "cachedExtraUsageDisabledReason",
        "passesEligibilityCache",
        "s1mAccessCache",
        "hasAvailableSubscription",
        "penguinModeOrgEnabled",
        "customApiKeyResponses",
        "subscriptionNoticeCount",
    ):
        assert key not in result
    assert result["bypassPermissionsModeAccepted"] is True


def test_claude_source_list_hides_cross_cli_oauth_bridge():
    from mms_core import _account_options_for_model

    cfg = {
        "accounts": [
            {
                "id": "gemini-a",
                "name": "gemini-a",
                "cli": "gemini",
                "enabled": True,
                "home_dir": "/tmp/gemini-a",
            }
        ],
        "account": {"defaults": {}},
    }

    options = _account_options_for_model(
        cfg,
        "claude",
        [],
        model_info={"model": "gemini-3.1-pro-preview"},
        allow_selected_model=True,
    )

    assert options == []


def test_claude_source_list_hides_broker_options():
    from mms_core import _broker_options_for_cli

    cfg = {
        "broker_profiles": [
            {
                "id": "broker-a",
                "name": "broker-a",
                "enabled": True,
                "broker_base_url": "https://broker.example.com",
            }
        ]
    }

    assert _broker_options_for_cli(cfg, "claude", {"model": "claude-sonnet-4-6"}) == []


def test_inspect_runtime_exposure_reports_claude_oauth_env(monkeypatch, tmp_path):
    import json as _json
    from mms_launchers import inspect_runtime_exposure

    monkeypatch.setenv("MMS_REAL_HOME", str(tmp_path))
    monkeypatch.setenv("MMS_FAKE_UPSTREAM", "0")

    account_home = tmp_path / ".config" / "mms" / "accounts" / "claude-a"
    claude_dir = account_home / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "settings.json").write_text(_json.dumps({}), encoding="utf-8")

    payload = inspect_runtime_exposure(
        "claude",
        {
            "id": "claude-a",
            "name": "claude-a",
            "cli": "claude",
            "auth_mode": "oauth",
            "home_dir": str(account_home),
            "proxy": "http://127.0.0.1:7890",
            "timezone": "America/Los_Angeles",
            "force_ipv4": True,
        },
    )

    env_map = {item["key"]: item["value"] for item in payload["process_env"]}
    assert payload["network"]["locale"] == "en_US.UTF-8"
    assert payload["home"]["account_home"] == str(account_home)
    assert env_map["HTTP_PROXY"] == "http://127.0.0.1:7890"
    assert env_map["LANG"] == "en_US.UTF-8"
    assert env_map["TZ"] == "America/Los_Angeles"
    assert payload["settings"]["statusline"] is False
    assert payload["settings"]["hook_events"] == []
    assert "HTTP_PROXY" in payload["settings"]["env_keys"]
    assert "TZ" in payload["settings"]["env_keys"]


def test_gateway_claude_bridge_context_drops_unknown_kwargs(monkeypatch, capsys):
    import mms_launchers

    calls = {}

    @contextmanager
    def fake_old_bridge(gateway_url, gateway_key, heavy_model=None):
        calls["gateway_url"] = gateway_url
        calls["gateway_key"] = gateway_key
        calls["heavy_model"] = heavy_model
        yield {"base_url": "http://127.0.0.1:1", "api_key": "bridge-token"}

    monkeypatch.setattr(mms_launchers, "gateway_claude_bridge", fake_old_bridge)

    with mms_launchers._gateway_claude_bridge_context(
        "https://gateway.example.com/v1",
        "sk-test",
        heavy_model="gpt-5.4",
        strip_upstream_user_agent=True,
    ) as bridge_cfg:
        assert bridge_cfg["api_key"] == "bridge-token"

    captured = capsys.readouterr()
    assert calls["gateway_url"] == "https://gateway.example.com/v1"
    assert calls["gateway_key"] == "sk-test"
    assert calls["heavy_model"] == "gpt-5.4"
    assert "旧版 bridge 签名" in captured.out


def test_account_guard_report_detects_profile_drift(monkeypatch, tmp_path):
    import mms_launchers

    state_path = tmp_path / "account-guard-state.json"
    state_path.write_text(
        json.dumps(
            {
                "accounts": {
                    "claude-a": {
                        "last_profile": {
                            "proxy_fingerprint": "http://1.1.1.1:80",
                            "timezone": "America/Los_Angeles",
                            "force_ipv4": True,
                            "no_proxy": "",
                        },
                        "consecutive_failures": 1,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mms_launchers, "_account_guard_state_path", lambda: str(state_path))
    monkeypatch.setattr(mms_launchers, "_count_live_session_dirs", lambda _path: 1)

    report = mms_launchers._build_account_guard_report(
        {
            "id": "claude-a",
            "home_dir": str(tmp_path / "account"),
            "proxy": "http://2.2.2.2:90",
            "timezone": "America/New_York",
            "force_ipv4": False,
            "no_proxy": "localhost",
        }
    )

    assert report["status"] == "risky"
    assert report["active_sessions_after"] == 2
    assert set(report["drift_fields"]) == {"proxy", "timezone", "ipv4", "no_proxy"}
    assert report["score"] < 85


def test_account_guard_report_blocks_excessive_parallel_sessions(monkeypatch, tmp_path):
    import mms_launchers

    monkeypatch.setattr(mms_launchers, "_account_guard_state_path", lambda: str(tmp_path / "guard.json"))
    monkeypatch.setattr(mms_launchers, "_count_live_session_dirs", lambda _path: 4)

    report = mms_launchers._build_account_guard_report(
        {
            "id": "claude-a",
            "home_dir": str(tmp_path / "account"),
            "timezone": "America/Los_Angeles",
        }
    )

    assert report["status"] == "blocked"
    assert "安全上限 4" in report["blocked_reason"]


def test_record_account_guard_finalize_tracks_failures(monkeypatch, tmp_path):
    import mms_launchers

    state_path = tmp_path / "account-guard-state.json"
    monkeypatch.setattr(mms_launchers, "_account_guard_state_path", lambda: str(state_path))

    mms_launchers._persist_account_guard_launch(
        "claude-a",
        {
            "profile": {
                "proxy_fingerprint": "direct",
                "timezone": "America/Los_Angeles",
                "force_ipv4": True,
                "no_proxy": "",
            },
            "score": 100,
            "status": "stable",
            "drift_fields": [],
            "active_sessions_after": 1,
        },
        session_home=str(tmp_path / "session"),
    )
    mms_launchers._record_account_guard_finalize("claude-a", exit_code=1)
    mms_launchers._record_account_guard_finalize("claude-a", exit_code=2)

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    account = payload["accounts"]["claude-a"]
    assert account["consecutive_failures"] == 2
    assert account["last_exit_code"] == 2

    mms_launchers._record_account_guard_finalize("claude-a", exit_code=0)
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["accounts"]["claude-a"]["consecutive_failures"] == 0


def test_claude_network_guard_blocks_claude_account_bypass_without_proxy():
    from mms_launchers import build_claude_network_guard

    guard = build_claude_network_guard(
        {
            "id": "claude-a",
            "auth_mode": "oauth",
            "cli": "claude",
            "timezone": "America/Los_Angeles",
            "force_ipv4": True,
        },
        require_proxy=True,
    )

    assert guard["status"] == "blocked"
    assert "必须配置 proxy" in guard["block_reason"]
    assert "官方账号" in guard["block_reason"]


def test_claude_network_guard_blocks_sensitive_provider_bypass_without_proxy():
    from mms_launchers import build_claude_network_guard

    guard = build_claude_network_guard(
        {
            "id": "relay-a",
            "auth_mode": "api_key",
            "skip_anthropic_probe": True,
            "timezone": "America/Los_Angeles",
            "force_ipv4": True,
        },
        require_proxy=True,
    )

    assert guard["status"] == "blocked"
    assert "配置 proxy" in guard["block_reason"]
    assert "敏感 Claude provider" in guard["block_reason"]


def test_claude_network_guard_blocks_no_proxy_conflict():
    from mms_launchers import build_claude_network_guard

    guard = build_claude_network_guard(
        {
            "id": "claude-a",
            "proxy": "http://127.0.0.1:7890",
            "no_proxy": "claude.ai,localhost",
            "timezone": "America/Los_Angeles",
            "force_ipv4": True,
        },
        require_proxy=True,
    )

    assert guard["status"] == "blocked"
    assert "直连泄漏风险" in guard["block_reason"]
    assert "claude.ai" in guard["no_proxy_conflicts"]


def test_claude_network_guard_collects_targets_and_egress(monkeypatch):
    import mms_launchers

    def fake_probe(proxy_url, target_url, *, no_proxy="", force_ipv4=True, resolve_ip=False):
        if resolve_ip:
            return {"ok": True, "body": "1.2.3.4", "detail": "", "http_code": ""}
        return {"ok": True, "detail": "", "http_code": "200", "body": "200"}

    monkeypatch.setattr(mms_launchers, "_run_proxy_probe", fake_probe)
    guard = mms_launchers.build_claude_network_guard(
        {
            "id": "claude-a",
            "proxy": "http://127.0.0.1:7890",
            "timezone": "America/Los_Angeles",
            "force_ipv4": True,
        },
        require_proxy=True,
    )

    assert guard["status"] == "ok"
    assert guard["dns_mode"] == "proxy-likely"
    assert guard["ipv4_egress"] == "1.2.3.4"
    assert all(item["ok"] for item in guard["targets"])
