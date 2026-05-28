from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import mms_registry
import mms_registry_cli


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_JSON = ROOT / "docs/reference/model-capability-calibration/2026-05-21-mms-model-capability-calibration.json"


def test_refresh_sources_imports_reference_snapshot_to_db(tmp_path: Path) -> None:
    db_path = tmp_path / "model-registry.sqlite"

    summary = mms_registry_cli.refresh_source_snapshots(db_path=db_path, paths=[REFERENCE_JSON])
    status = mms_registry_cli.registry_status(db_path=db_path)

    assert summary["imported_count"] == 1
    assert summary["model_count"] >= 39
    assert summary["fact_count"] >= summary["model_count"]
    assert status["counts"]["source_snapshot"] == 1
    assert status["counts"]["source_check"] == 1
    assert status["source_freshness"]["due_count"] == 0
    assert status["counts"]["model_identity"] >= 30
    assert status["counts"]["model_fact"] == summary["fact_count"]


def test_preview_config_root_uses_registry_subdir_for_db(monkeypatch, tmp_path: Path) -> None:
    preview_root = tmp_path / "mms-next"

    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))

    assert mms_registry.default_registry_db_path() == preview_root / "registry" / "model-registry.sqlite"
    assert mms_registry.default_registry_db_path(config_dir=preview_root) == preview_root / "registry" / "model-registry.sqlite"


def test_legacy_config_dir_keeps_root_level_registry_db(monkeypatch, tmp_path: Path) -> None:
    legacy_root = tmp_path / "mms"

    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)

    assert mms_registry.default_registry_db_path(config_dir=legacy_root) == legacy_root / "model-registry.sqlite"


def test_source_freshness_and_if_due_refresh_use_check_timestamp(tmp_path: Path) -> None:
    db_path = tmp_path / "model-registry.sqlite"
    old_captured = "2026-05-01T00:00:00.000Z"

    db = mms_registry.open_registry(db_path)
    try:
        mms_registry.import_source_snapshot(db, REFERENCE_JSON, captured_at=old_captured)
    finally:
        db.close()

    stale = mms_registry_cli.source_freshness(
        db_path=db_path,
        paths=[REFERENCE_JSON],
        max_age_hours=1,
    )
    refreshed = mms_registry_cli.refresh_source_snapshots(
        db_path=db_path,
        paths=[REFERENCE_JSON],
        if_due=True,
        max_age_hours=1,
    )
    fresh = mms_registry_cli.source_freshness(
        db_path=db_path,
        paths=[REFERENCE_JSON],
        max_age_hours=1,
    )
    status = mms_registry_cli.registry_status(db_path=db_path)

    assert stale["due_count"] == 1
    assert stale["sources"][0]["reason"] == "max_age_exceeded"
    assert refreshed["imported_count"] == 1
    assert refreshed["skipped_count"] == 0
    assert fresh["due_count"] == 0
    assert status["counts"]["source_snapshot"] == 1
    assert status["counts"]["source_check"] == 1


def test_registry_command_check_staleness_and_if_due(capsys, tmp_path: Path) -> None:
    db_path = tmp_path / "model-registry.sqlite"

    check_rc = mms_registry_cli.handle_registry_command(
        [
            "--db",
            str(db_path),
            "check-staleness",
            "--path",
            str(REFERENCE_JSON),
        ],
        command_name="mms registry",
    )
    refresh_rc = mms_registry_cli.handle_registry_command(
        [
            "--db",
            str(db_path),
            "refresh-sources",
            "--if-due",
            "--path",
            str(REFERENCE_JSON),
        ],
        command_name="mms registry",
    )
    second_refresh_rc = mms_registry_cli.handle_registry_command(
        [
            "--db",
            str(db_path),
            "refresh-sources",
            "--if-due",
            "--path",
            str(REFERENCE_JSON),
        ],
        command_name="mms registry",
    )
    out = capsys.readouterr().out

    assert check_rc == 0
    assert refresh_rc == 0
    assert second_refresh_rc == 0
    assert "due_count=1" in out
    assert "imported_count=1" in out
    assert "skipped_count=1" in out


def test_fetch_openrouter_catalog_from_file_records_provider_catalog_source(capsys, tmp_path: Path) -> None:
    db_path = tmp_path / "model-registry.sqlite"
    catalog_path = tmp_path / "openrouter-models.json"
    catalog_path.write_text(
        """
        {
          "data": [
            {
              "id": "openai/gpt-5.5",
              "context_length": 1050000,
              "pricing": {
                "prompt": "0.000005",
                "completion": "0.00003"
              },
              "supported_parameters": ["reasoning", "tools", "max_tokens"]
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    summary = mms_registry_cli.fetch_openrouter_catalog(
        db_path=db_path,
        from_file=catalog_path,
    )
    command_rc = mms_registry_cli.handle_registry_command(
        [
            "--db",
            str(db_path),
            "fetch-openrouter-catalog",
            "--from-file",
            str(catalog_path),
        ],
        command_name="mms registry",
    )
    status = mms_registry_cli.registry_status(db_path=db_path)
    out = capsys.readouterr().out

    assert summary["source_kind"] == mms_registry.OPENROUTER_MODELS_SOURCE_KIND
    assert summary["transport"] == "file"
    assert summary["model_count"] == 1
    assert command_rc == 0
    assert "source_kind=openrouter_models_api" in out
    assert "model_count=1" in out
    assert status["counts"]["source_snapshot"] == 1
    assert status["counts"]["source_check"] == 1
    assert status["counts"]["model_fact"] == 0


def test_diff_openrouter_catalog_records_candidate_changes(capsys, tmp_path: Path) -> None:
    db_path = tmp_path / "model-registry.sqlite"
    catalog_path = tmp_path / "openrouter-models.json"
    catalog_path.write_text(
        """
        {
          "data": [
            {
              "id": "deepseek/deepseek-v4-flash",
              "context_length": 999999,
              "top_provider": {
                "max_completion_tokens": 12345
              },
              "pricing": {
                "prompt": "0.000001",
                "completion": "0.000002"
              },
              "supported_parameters": ["max_tokens"]
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    mms_registry_cli.refresh_source_snapshots(db_path=db_path, paths=[REFERENCE_JSON])
    mms_registry_cli.fetch_openrouter_catalog(db_path=db_path, from_file=catalog_path)
    summary = mms_registry_cli.diff_openrouter_catalog(db_path=db_path, limit=5)
    command_rc = mms_registry_cli.handle_registry_command(
        [
            "--db",
            str(db_path),
            "diff-openrouter-catalog",
            "--limit",
            "3",
        ],
        command_name="mms registry",
    )
    status = mms_registry_cli.registry_status(db_path=db_path)
    out = capsys.readouterr().out

    assert summary["change_count"] >= 1
    assert summary["stored_count"] == summary["change_count"]
    assert any(item["provider_model_id"] == "deepseek/deepseek-v4-flash" for item in summary["changes"])
    assert command_rc == 0
    assert "MMS Registry OpenRouter Candidate Diff" in out
    assert "stored_count=" in out
    assert status["counts"]["candidate_change"] == summary["change_count"]


def test_scheduled_refresh_dry_run_writes_no_source_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "model-registry.sqlite"

    summary = mms_registry_cli.scheduled_refresh(
        db_path=db_path,
        dry_run=True,
        no_network=True,
    )
    status = mms_registry_cli.registry_status(db_path=db_path)

    assert summary["dry_run"] is True
    assert summary["source_due_count"] >= 1
    assert summary["openrouter_due"] is True
    assert summary["source_refresh"]["skipped"] is True
    assert summary["openrouter_fetch"]["skipped"] is True
    assert status["counts"]["source_snapshot"] == 0
    assert status["counts"]["source_check"] == 0
    assert status["counts"]["candidate_change"] == 0


def test_scheduled_refresh_no_network_imports_local_sources_only(capsys, tmp_path: Path) -> None:
    db_path = tmp_path / "model-registry.sqlite"

    summary = mms_registry_cli.scheduled_refresh(
        db_path=db_path,
        no_network=True,
    )
    command_rc = mms_registry_cli.handle_registry_command(
        [
            "--db",
            str(db_path),
            "scheduled-refresh",
            "--no-network",
        ],
        command_name="mms registry",
    )
    status = mms_registry_cli.registry_status(db_path=db_path)
    out = capsys.readouterr().out

    assert summary["source_refresh"]["imported_count"] >= 1
    assert summary["openrouter_fetch"]["skipped"] is True
    assert summary["openrouter_fetch"]["reason"] == "no_network"
    assert command_rc == 0
    assert "MMS Registry Scheduled Refresh" in out
    assert "openrouter_fetched=False" in out
    assert status["counts"]["source_snapshot"] >= 1
    assert status["counts"]["source_check"] >= 1
    assert status["counts"]["candidate_change"] == 0


def test_scheduled_refresh_from_file_imports_openrouter_and_candidates(tmp_path: Path) -> None:
    db_path = tmp_path / "model-registry.sqlite"
    catalog_path = tmp_path / "openrouter-models.json"
    catalog_path.write_text(
        """
        {
          "data": [
            {
              "id": "deepseek/deepseek-v4-flash",
              "context_length": 999999,
              "top_provider": {
                "max_completion_tokens": 12345
              },
              "pricing": {
                "prompt": "0.000001",
                "completion": "0.000002"
              },
              "supported_parameters": ["max_tokens"]
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    summary = mms_registry_cli.scheduled_refresh(
        db_path=db_path,
        no_network=True,
        openrouter_from_file=catalog_path,
    )
    second = mms_registry_cli.scheduled_refresh(
        db_path=db_path,
        no_network=True,
        openrouter_from_file=catalog_path,
    )
    status = mms_registry_cli.registry_status(db_path=db_path)

    assert summary["source_refresh"]["imported_count"] >= 1
    assert summary["openrouter_fetch"]["transport"] == "file"
    assert summary["openrouter_fetch"]["model_count"] == 1
    assert summary["openrouter_diff"]["stored_count"] >= 1
    assert second["source_refresh"]["reason"] == "not_due"
    assert second["openrouter_fetch"]["reason"] == "not_due"
    assert status["counts"]["source_snapshot"] >= 2
    assert status["counts"]["candidate_change"] >= 1


def test_registry_command_refresh_sources_and_status(capsys, tmp_path: Path) -> None:
    db_path = tmp_path / "model-registry.sqlite"

    rc = mms_registry_cli.handle_registry_command(
        [
            "--db",
            str(db_path),
            "refresh-sources",
            "--path",
            str(REFERENCE_JSON),
        ],
        command_name="mms registry",
    )
    status_rc = mms_registry_cli.handle_registry_command(
        ["--db", str(db_path), "status"],
        command_name="mms registry",
    )
    out = capsys.readouterr().out

    assert rc == 0
    assert status_rc == 0
    assert "imported_count=1" in out
    assert "model_identity=" in out


def test_registry_backup_and_restore_roundtrip(capsys, tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-config"
    db_path = config_dir / "model-registry.sqlite"

    mms_registry_cli.refresh_source_snapshots(db_path=db_path, paths=[REFERENCE_JSON])
    backup = mms_registry_cli.backup_registry_db(
        config_dir=config_dir,
        db_path=db_path,
        reason="test-roundtrip",
    )
    dry_run = mms_registry_cli.restore_registry_db(
        backup["backup_path"],
        config_dir=config_dir,
        db_path=db_path,
    )
    for path in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
        if path.exists():
            path.unlink()
    restored = mms_registry_cli.restore_registry_db(
        backup["backup_path"],
        config_dir=config_dir,
        db_path=db_path,
        apply=True,
        reason="test-restore",
    )
    status = mms_registry_cli.registry_status(db_path=db_path)
    backup_rc = mms_registry_cli.handle_registry_command(
        ["--db", str(db_path), "backup-db", "--config-dir", str(config_dir), "--reason", "cli-test"],
        command_name="mms registry",
    )
    restore_dry_run_rc = mms_registry_cli.handle_registry_command(
        ["--db", str(db_path), "restore-db", backup["backup_path"], "--config-dir", str(config_dir)],
        command_name="mms registry",
    )
    out = capsys.readouterr().out

    assert backup["skipped"] is False
    assert Path(backup["backup_path"]).exists()
    assert Path(backup["manifest_path"]).exists()
    assert backup["integrity_check"] == "ok"
    assert dry_run["skipped"] is True
    assert dry_run["skip_reason"] == "dry_run_apply_required"
    assert restored["skipped"] is False
    assert restored["restored_integrity_check"] == "ok"
    assert status["counts"]["source_snapshot"] == 1
    assert status["counts"]["source_check"] == 1
    assert backup_rc == 0
    assert restore_dry_run_rc == 0
    assert "MMS Registry DB Backup" in out
    assert "MMS Registry DB Restore" in out
    assert "skip_reason=dry_run_apply_required" in out


def test_legacy_import_report_detects_credential_conflicts_without_plaintext(capsys, tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        """
        [api]
        base_url = "https://config-default.example/v1"
        api_key = "sk-config-default-secret"

        [[providers]]
        id = "default"
        name = "Default"
        default_openai_base_url = "https://provider-default.example/v1"
        protocols = ["openai_chat_completions"]

        [[providers]]
        id = "kimi-direct"
        name = "Kimi Direct"
        default_openai_base_url = "https://config-kimi.example/v1"
        default_anthropic_base_url = "https://config-kimi.example/anthropic"
        protocols = ["anthropic_messages", "openai_chat_completions"]
        models_endpoint = "/models"
        priority = 10
        role = "primary"
        """,
        encoding="utf-8",
    )
    (config_dir / "credentials.sh").write_text(
        """
        export MMS_PROVIDER_KIMI_DIRECT_OPENAI_BASE_URL='https://creds-kimi.example/v1'
        export MMS_PROVIDER_KIMI_DIRECT_API_KEY='sk-creds-kimi-secret'
        export MMS_API_BASE_URL='https://creds-default.example/v1'
        export MMS_API_KEY='sk-creds-default-secret'
        """,
        encoding="utf-8",
    )

    summary = mms_registry_cli.legacy_import_report(config_dir=config_dir)
    rc = mms_registry_cli.handle_registry_command(
        ["legacy-report", "--config-dir", str(config_dir)],
        command_name="mms registry",
    )
    json_rc = mms_registry_cli.handle_registry_command(
        ["legacy-report", "--config-dir", str(config_dir), "--json"],
        command_name="mms registry",
    )
    out = capsys.readouterr().out
    encoded = json.dumps(summary, ensure_ascii=False, sort_keys=True)

    assert rc == 0
    assert json_rc == 0
    assert summary["read_only"] is True
    assert summary["plaintext_secret_in_db"] is False
    assert summary["provider_count"] == 2
    assert summary["conflict_count"] >= 2
    assert any(item["provider_id"] == "kimi-direct" and item["field"] == "openai_base_url" for item in summary["conflicts"])
    assert any(item["provider_id"] == "default" and item["field"] == "base_url" for item in summary["conflicts"])
    assert any(item["provider_id"] == "kimi-direct" and item["field"] == "api_key" for item in summary["secret_refs"])
    assert "MMS Legacy Import Report" in out
    assert "conflict=provider=kimi-direct field=openai_base_url" in out
    assert "secret_ref=provider=kimi-direct field=api_key" in out
    assert "sk-config-default-secret" not in encoded
    assert "sk-creds-default-secret" not in encoded
    assert "sk-creds-kimi-secret" not in encoded
    assert "sk-config-default-secret" not in out
    assert "sk-creds-default-secret" not in out
    assert "sk-creds-kimi-secret" not in out


def test_mmf_registry_legacy_report_does_not_bootstrap_config_migration(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        """
        [api]
        base_url = "https://config-default.example/v1"
        api_key = "sk-config-default-secret"
        """,
        encoding="utf-8",
    )
    (config_dir / "credentials.sh").write_text(
        """
        export MMS_API_BASE_URL='https://creds-default.example/v1'
        export MMS_API_KEY='sk-creds-default-secret'
        """,
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update({"MMS_CONFIG_ROOT": str(config_dir), "PYTHONPATH": str(ROOT)})
    result = subprocess.run(
        [sys.executable, str(ROOT / "mmf"), "registry", "legacy-report", "--config-dir", str(config_dir), "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(result.stdout)
    combined = result.stdout + result.stderr

    assert payload["schema"] == mms_registry_cli.LEGACY_IMPORT_REPORT_SCHEMA
    assert payload["read_only"] is True
    assert payload["conflict_count"] >= 1
    assert "sk-config-default-secret" not in combined
    assert "sk-creds-default-secret" not in combined
    assert not (config_dir / "backups").exists()
    assert not (config_dir / "config-audit.jsonl").exists()
    assert not (config_dir / "cache").exists()


def test_mmf_config_root_does_not_bootstrap_config_migration(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-config"
    config_dir.mkdir()
    original_config = """
    [api]
    base_url = "https://config-default.example/v1"
    api_key = "sk-config-default-secret"
    """
    (config_dir / "config.toml").write_text(original_config, encoding="utf-8")
    (config_dir / "credentials.sh").write_text(
        "export MMS_API_BASE_URL='https://creds-default.example/v1'\nexport MMS_API_KEY='sk-creds-default-secret'\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update({"MMS_CONFIG_ROOT": str(config_dir), "PYTHONPATH": str(ROOT)})
    result = subprocess.run(
        [sys.executable, str(ROOT / "mmf"), "config", "root", "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["command"] == "mmf"
    assert payload["mode"] == "preview"
    assert payload["config_root"] == str(config_dir)
    assert (config_dir / "config.toml").read_text(encoding="utf-8") == original_config
    assert not (config_dir / "backups").exists()
    assert not (config_dir / "config-audit.jsonl").exists()
    assert not (config_dir / "cache").exists()


def test_mmf_preview_help_is_short_and_read_only(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-next"
    config_dir.mkdir()
    original_config = """
    [api]
    base_url = "https://config-default.example/v1"
    api_key = "sk-config-default-secret"
    """
    (config_dir / "config.toml").write_text(original_config, encoding="utf-8")
    env = os.environ.copy()
    env.update({"MMS_CONFIG_ROOT": str(config_dir), "PYTHONPATH": str(ROOT)})

    result = subprocess.run(
        [sys.executable, str(ROOT / "mmf"), "preview", "--help"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    combined = result.stdout + result.stderr

    assert "MMF preview commands" in result.stdout
    assert "mmf preview doctor [--json]" in result.stdout
    assert "mmf config doctor [--json]" in result.stdout
    assert "mmf preview prepare --from ~/.config/mms --include-secrets --json" in result.stdout
    assert "AI Coding CLI" not in result.stdout
    assert "sk-config-default-secret" not in combined
    assert (config_dir / "config.toml").read_text(encoding="utf-8") == original_config
    assert not (config_dir / "registry").exists()
    assert not (config_dir / "cache").exists()


def test_mmf_config_source_status_is_read_only_and_reports_preview_state(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-config"
    config_dir.mkdir()
    original_config = """
    [api]
    base_url = "https://config-default.example/v1"
    api_key = "sk-config-default-secret"
    """
    (config_dir / "config.toml").write_text(original_config, encoding="utf-8")
    (config_dir / "credentials.sh").write_text(
        "export MMS_API_BASE_URL='https://creds-default.example/v1'\nexport MMS_API_KEY='sk-creds-default-secret'\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update({"MMS_CONFIG_ROOT": str(config_dir), "PYTHONPATH": str(ROOT)})
    result = subprocess.run(
        [sys.executable, str(ROOT / "mmf"), "config", "source", "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(result.stdout)
    combined = result.stdout + result.stderr

    assert payload["schema"] == "mms.model_source_status.v1"
    assert payload["read_only"] is True
    assert payload["root"]["command"] == "mmf"
    assert payload["root"]["mode"] == "preview"
    assert payload["legacy_import"]["conflict_count"] >= 1
    assert payload["registry_db"]["status"] == "missing"
    assert payload["registry_db"]["path"] == str(config_dir / "registry" / "model-registry.sqlite")
    assert payload["legacy_import"]["candidates"]["status"] == "not_imported"
    assert payload["legacy_import"]["candidates"]["provider_route_count"] == 0
    assert payload["generated_bundle"]["status"] == "missing"
    assert "sk-config-default-secret" not in combined
    assert "sk-creds-default-secret" not in combined
    assert (config_dir / "config.toml").read_text(encoding="utf-8") == original_config
    assert not (config_dir / "registry").exists()
    assert not (config_dir / "cache").exists()


def test_mmf_config_doctor_is_read_only_and_reports_next_action(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-config"
    config_dir.mkdir()
    original_config = """
    [api]
    base_url = "https://config-default.example/v1"
    api_key = "sk-config-default-secret"
    """
    (config_dir / "config.toml").write_text(original_config, encoding="utf-8")

    env = os.environ.copy()
    env.update({"MMS_CONFIG_ROOT": str(config_dir), "PYTHONPATH": str(ROOT)})
    result = subprocess.run(
        [sys.executable, str(ROOT / "mmf"), "config", "doctor", "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(result.stdout)
    combined = result.stdout + result.stderr

    assert payload["schema"] == "mms.preview_doctor.v1"
    assert payload["read_only"] is True
    assert payload["status"] == "needs_init"
    assert payload["ready"] is False
    assert payload["next_actions"][0]["command"] == "./mmf preview init --json"
    assert "sk-config-default-secret" not in combined
    assert (config_dir / "config.toml").read_text(encoding="utf-8") == original_config
    assert not (config_dir / "registry").exists()
    assert not (config_dir / "cache").exists()


def test_registry_v2_save_plan_reports_preview_backup_sequence_without_secrets(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-next"
    db_path = config_dir / "registry" / "model-registry.sqlite"
    db_path.parent.mkdir(parents=True)
    db_path.write_bytes(b"not-a-real-db")

    plan = mms_registry_cli.registry_v2_save_plan(
        config_dir=config_dir,
        command_name="mmf config save-plan",
        plan_summary={
            "will_write_config": True,
            "will_write_policy": True,
            "will_write_credentials": True,
        },
        credential_updates=[{"provider_id": "demo", "api_key": "sk-preview-secret"}],
    )
    encoded = json.dumps(plan, ensure_ascii=False, sort_keys=True)

    assert plan["schema"] == mms_registry_cli.REGISTRY_V2_SAVE_PLAN_SCHEMA
    assert plan["read_only"] is True
    assert plan["execution_state"] == "plan_only"
    assert plan["actual_save_enabled"] is False
    assert plan["root"]["command"] == "mmf"
    assert plan["root"]["mode"] == "preview"
    assert plan["db"]["path"] == str(db_path)
    assert plan["db"]["would_backup_existing_db"] is True
    assert plan["would_write"]["db_candidate_revision"] is True
    assert plan["would_write"]["secret_backend"] is True
    assert plan["would_write"]["generated_latest_approved_bundle"] is True
    assert plan["would_write"]["legacy_compat_files"]["credentials_sh"] is True
    assert plan["blocked_reasons"] == []
    assert "rollback" in " ".join(plan["ordered_steps"])
    assert "sk-preview-secret" not in encoded


def test_mmf_config_save_plan_is_read_only_and_reports_no_draft_changes(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-config"
    config_dir.mkdir()
    original_config = """
    [api]
    base_url = "https://config-default.example/v1"
    api_key = "sk-config-default-secret"
    """
    (config_dir / "config.toml").write_text(original_config, encoding="utf-8")

    env = os.environ.copy()
    env.update({"MMS_CONFIG_ROOT": str(config_dir), "PYTHONPATH": str(ROOT)})
    result = subprocess.run(
        [sys.executable, str(ROOT / "mmf"), "config", "save-plan", "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(result.stdout)
    combined = result.stdout + result.stderr

    assert payload["schema"] == mms_registry_cli.REGISTRY_V2_SAVE_PLAN_SCHEMA
    assert payload["read_only"] is True
    assert payload["root"]["command"] == "mmf"
    assert payload["root"]["mode"] == "preview"
    assert payload["actual_save_enabled"] is False
    assert payload["would_write"]["db_candidate_revision"] is False
    assert payload["would_write"]["secret_backend"] is False
    assert payload["would_write"]["generated_latest_approved_bundle"] is False
    assert "no_draft_changes" in payload["blocked_reasons"]
    assert "stable_root_human_only" not in payload["blocked_reasons"]
    assert payload["db"]["path"] == str(config_dir / "registry" / "model-registry.sqlite")
    assert "sk-config-default-secret" not in combined
    assert (config_dir / "config.toml").read_text(encoding="utf-8") == original_config
    assert not (config_dir / "registry").exists()
    assert not (config_dir / "cache").exists()


def test_mms_config_save_plan_blocks_stable_root_without_writing(tmp_path: Path) -> None:
    real_home = tmp_path / "home"
    stable_root = real_home / ".config" / "mms"
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(real_home),
            "MMS_REAL_HOME": str(real_home),
            "PYTHONPATH": str(ROOT),
        }
    )
    env.pop("MMS_CONFIG_ROOT", None)
    env.pop("MMS_CONFIG_DIR", None)
    env.pop("MMS_PREVIEW_MODE", None)
    env.pop("MMS_COMMAND_NAME", None)
    env.pop("XDG_CONFIG_HOME", None)
    result = subprocess.run(
        [sys.executable, str(ROOT / "mms"), "config", "save-plan", "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["schema"] == mms_registry_cli.REGISTRY_V2_SAVE_PLAN_SCHEMA
    assert payload["read_only"] is True
    assert payload["root"]["command"] == "mms"
    assert payload["root"]["mode"] == "stable"
    assert payload["root"]["config_root"] == str(stable_root)
    assert payload["actual_save_enabled"] is False
    assert payload["would_write"]["db_candidate_revision"] is False
    assert "stable_root_human_only" in payload["blocked_reasons"]
    assert "no_draft_changes" in payload["blocked_reasons"]
    assert not stable_root.exists()


def _registry_v2_candidate_config() -> dict:
    return {
        "provider": {"default": "primary-local"},
        "providers": [
            {
                "id": "primary-local",
                "name": "Primary Local",
                "enabled": True,
                "role": "primary",
                "priority": 100,
                "default_openai_base_url": "https://primary.example/v1",
                "api_key": "sk-primary-local-secret",
                "models_endpoint": "/models",
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["codex", "opencode"],
                "fallback_models": ["shared-model"],
                "extra_models": ["manual-model"],
            },
            {
                "id": "disabled-local",
                "enabled": False,
                "default_openai_base_url": "https://disabled.example/v1",
                "fallback_models": ["disabled-model"],
            },
        ],
    }


def test_registry_v2_save_candidate_writes_preview_db_without_secrets(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-next"
    cfg = _registry_v2_candidate_config()
    policy = {
        "version": 1,
        "models": {
            "shared-model": {"visible": True, "favorite": True},
            "manual-model": {"visible": False},
        },
    }

    dry_run = mms_registry_cli.apply_registry_v2_save_candidate(
        config_dir=config_dir,
        config_payload=cfg,
        policy_payload=policy,
        credential_updates=[{"provider_id": "primary-local", "api_key": "sk-redacted"}],
    )
    assert dry_run["skipped"] is True
    assert dry_run["candidate"]["route_entry_count"] == 2
    assert not (config_dir / "registry").exists()

    summary = mms_registry_cli.apply_registry_v2_save_candidate(
        config_dir=config_dir,
        config_payload=cfg,
        policy_payload=policy,
        credential_updates=[{"provider_id": "primary-local", "api_key": "sk-redacted"}],
        apply=True,
        command_name="mmf registry",
    )
    db_path = config_dir / "registry" / "model-registry.sqlite"
    db_text = db_path.read_bytes()

    assert summary["schema"] == mms_registry_cli.REGISTRY_V2_SAVE_CANDIDATE_SCHEMA
    assert summary["skipped"] is False
    assert summary["backup"]["reason"] == "new_db"
    assert summary["route_candidates"]["provider_route_count"] == 2
    assert summary["route_candidates"]["route_group_count"] == 2
    assert summary["policy_candidate"]["model_count"] == 2
    assert summary["profile_candidate"]["provider_count"] == 2
    assert summary["writes"]["generated_latest_approved_bundle"] is False
    assert summary["writes"]["secret_backend"] is False
    assert b"sk-primary-local-secret" not in db_text
    assert not (config_dir / "generated" / "model-registry.latest-approved.json").exists()

    db = sqlite3.connect(db_path)
    try:
        route_revision = summary["route_candidates"]["revision_id"]
        assert db.execute("SELECT count(*) FROM provider_route WHERE route_revision_id = ?", (route_revision,)).fetchone()[0] == 2
        refs = {row[0] for row in db.execute("SELECT secret_ref FROM provider_route WHERE route_revision_id = ?", (route_revision,))}
        assert refs == {"pending-webui:primary_local:api_key"}
        sources = {
            json.loads(row[0])["source"]
            for row in db.execute("SELECT metadata_json FROM registry_revision WHERE revision_id IN (?, ?, ?)", (
                summary["route_candidates"]["revision_id"],
                summary["policy_candidate"]["revision_id"],
                summary["profile_candidate"]["revision_id"],
            ))
        }
        assert sources == {"registry-v2-save-candidate"}
    finally:
        db.close()


def test_registry_v2_save_candidate_refuses_stable_root_without_allow_stable(tmp_path: Path) -> None:
    stable_root = tmp_path / "mms"

    try:
        mms_registry_cli.apply_registry_v2_save_candidate(
            config_dir=stable_root,
            config_payload=_registry_v2_candidate_config(),
            apply=True,
            command_name="mms registry",
        )
    except mms_registry.RegistryValidationError as exc:
        assert "refusing to write registry v2 save candidate into stable config root" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("stable config root candidate write should require --allow-stable")
    assert not stable_root.exists()


def test_registry_v2_save_candidate_rolls_back_preview_db_on_failure(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-next"
    cfg = _registry_v2_candidate_config()
    first = mms_registry_cli.apply_registry_v2_save_candidate(
        config_dir=config_dir,
        config_payload=cfg,
        apply=True,
        command_name="mmf registry",
    )
    db_path = config_dir / "registry" / "model-registry.sqlite"
    first_route_revision = first["route_candidates"]["revision_id"]

    original = mms_registry_cli._insert_registry_v2_candidate_revisions

    def write_then_fail(db, payload, *, actor):
        original(db, payload, actor=actor)
        raise RuntimeError("injected candidate failure")

    monkeypatch.setattr(mms_registry_cli, "_insert_registry_v2_candidate_revisions", write_then_fail)
    broken_cfg = _registry_v2_candidate_config()
    broken_cfg["providers"][0]["extra_models"] = ["manual-model", "should-rollback"]

    try:
        mms_registry_cli.apply_registry_v2_save_candidate(
            config_dir=config_dir,
            config_payload=broken_cfg,
            apply=True,
            command_name="mmf registry",
        )
    except RuntimeError as exc:
        assert "injected candidate failure" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("injected failure should be raised")

    backups = list((config_dir / "backups" / "db").glob("model-registry.*.sqlite"))
    assert backups
    db = sqlite3.connect(db_path)
    try:
        route_revisions = {
            row[0]
            for row in db.execute("SELECT revision_id, metadata_json FROM registry_revision WHERE revision_class = 'route'")
            if json.loads(row[1]).get("source") == "registry-v2-save-candidate"
        }
        assert route_revisions == {first_route_revision}
        assert db.execute("SELECT count(*) FROM provider_route").fetchone()[0] == first["route_candidates"]["provider_route_count"]
        assert not db.execute("SELECT 1 FROM route_group WHERE logical_model = 'should-rollback'").fetchone()
    finally:
        db.close()


def test_mmf_registry_v2_save_candidate_cli_accepts_webui_plan_json(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-next"
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema": "mms.setup_web.plan.v1",
                "config": _registry_v2_candidate_config(),
                "model_policy": {"version": 1, "models": {"shared-model": {"visible": True}}},
                "credential_updates": [{"provider_id": "primary-local", "api_key": "***"}],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update({"MMS_CONFIG_ROOT": str(config_dir), "PYTHONPATH": str(ROOT)})

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "mmf"),
            "registry",
            "v2-save-candidate",
            "--config-dir",
            str(config_dir),
            "--plan-json",
            str(plan_path),
            "--apply",
            "--json",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(result.stdout)
    combined = result.stdout + result.stderr

    assert payload["schema"] == mms_registry_cli.REGISTRY_V2_SAVE_CANDIDATE_SCHEMA
    assert payload["route_candidates"]["provider_route_count"] == 2
    assert payload["policy_candidate"]["model_count"] == 1
    assert "sk-primary-local-secret" not in combined
    assert (config_dir / "registry" / "model-registry.sqlite").exists()


def test_publish_preview_bundle_prefers_latest_registry_v2_save_candidate(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-next"
    cfg = _registry_v2_candidate_config()
    policy = {
        "version": 1,
        "models": {
            "shared-model": {"visible": True, "favorite": True},
            "manual-model": {"visible": False},
        },
    }
    candidate = mms_registry_cli.apply_registry_v2_save_candidate(
        config_dir=config_dir,
        config_payload=cfg,
        policy_payload=policy,
        credential_updates=[{"provider_id": "primary-local", "api_key": "***"}],
        apply=True,
        command_name="mmf registry",
    )
    publish_summary = mms_registry_cli.publish_preview_bundle(config_dir=config_dir)
    verify_summary = mms_registry_cli.verify_approved_bundle(config_dir=config_dir)
    status = mms_registry_cli.model_source_status(config_dir=config_dir, command_name="mmf config source")
    router = json.loads((config_dir / "generated" / "model-routes.json").read_text(encoding="utf-8"))
    policy_payload = json.loads((config_dir / "generated" / "model-policy.effective.json").read_text(encoding="utf-8"))
    profile_payload = json.loads((config_dir / "generated" / "provider-profiles.generated.json").read_text(encoding="utf-8"))
    generated_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            config_dir / "generated" / "model-routes.json",
            config_dir / "generated" / "model-policy.effective.json",
            config_dir / "generated" / "provider-profiles.generated.json",
            config_dir / "generated" / "model-registry.latest-approved.json",
        )
    )

    assert publish_summary["schema"] == "mms.preview_bundle_publish.v1"
    assert publish_summary["source"] == "registry-preview-v2-save-candidate"
    assert publish_summary["preview_source"] == "registry-v2-save-candidate"
    assert publish_summary["route_revision"] == candidate["route_candidates"]["revision_id"]
    assert publish_summary["policy_revision"] == candidate["policy_candidate"]["revision_id"]
    assert publish_summary["profile_revision"] == candidate["profile_candidate"]["revision_id"]
    assert publish_summary["provider_route_count"] == 2
    assert publish_summary["runtime_ready"] is False
    assert verify_summary["verified"] is True
    assert status["generated_bundle"]["verified"] is True
    assert router["source"] == "registry-preview-v2-save-candidate"
    assert router["routes"]["shared-model"]["primary"]["secret_ref"] == "pending-webui:primary_local:api_key"
    assert router["routes"]["shared-model"]["primary"]["api_key"] == ""
    assert policy_payload["source"] == "registry-preview-v2-save-candidate"
    assert policy_payload["models"]["manual-model"]["visible"] is False
    assert profile_payload["source"] == "registry-preview-v2-save-candidate"
    assert profile_payload["profiles"]["primary-local"]["models_endpoint"] == "/models"
    assert "sk-primary-local-secret" not in generated_text


def test_mmf_preview_init_creates_preview_layout_without_stable_fallback(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-next"
    real_home = tmp_path / "home"
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(real_home),
            "MMS_REAL_HOME": str(real_home),
            "MMS_CONFIG_ROOT": str(config_dir),
            "PYTHONPATH": str(ROOT),
        }
    )
    result = subprocess.run(
        [sys.executable, str(ROOT / "mmf"), "preview", "init", "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(result.stdout)
    combined = result.stdout + result.stderr

    assert payload["schema"] == mms_registry_cli.CONFIG_ROOT_INIT_SCHEMA
    assert payload["root"]["command"] == "mmf"
    assert payload["root"]["mode"] == "preview"
    assert payload["root"]["config_root"] == str(config_dir)
    assert payload["db_initialized"] is True
    assert payload["db_path"] == str(config_dir / "registry" / "model-registry.sqlite")
    assert (config_dir / "root-manifest.json").exists()
    assert (config_dir / "registry" / "model-registry.sqlite").exists()
    for rel in mms_registry_cli.CONFIG_ROOT_LAYOUT_DIRS:
        assert (config_dir / rel).is_dir()
    assert not (real_home / ".config" / "mms").exists()
    assert "api_key" not in combined.lower()
    assert "token" not in combined.lower()


def test_init_config_root_refuses_stable_root_without_allow_stable(capsys, tmp_path: Path) -> None:
    stable_root = tmp_path / "mms"

    try:
        mms_registry_cli.init_config_root(config_dir=stable_root, command_name="mms registry")
    except mms_registry.RegistryValidationError as exc:
        assert "refusing to initialize stable config root" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("stable config root init should require --allow-stable")

    assert not stable_root.exists()
    rc = mms_registry_cli.handle_registry_command(
        ["init-root", "--config-dir", str(stable_root), "--json"],
        command_name="mms registry",
    )
    out = capsys.readouterr().out
    payload = json.loads(out)

    assert rc == 2
    assert payload["ok"] is False
    assert "refusing to initialize stable config root" in payload["error"]
    assert not stable_root.exists()


def test_mmf_registry_legacy_import_dry_run_is_read_only(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-next"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        """
        [[providers]]
        id = "local"
        name = "Local"
        default_openai_base_url = "https://config-local.example/v1"
        api_key = "sk-config-local-secret"
        protocols = ["openai_chat_completions"]
        fallback_models = ["gpt-5.5"]
        extra_models = ["qwen3.7-max"]
        """,
        encoding="utf-8",
    )
    (config_dir / "credentials.sh").write_text(
        "export MMS_PROVIDER_LOCAL_API_KEY='sk-creds-local-secret'\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update({"MMS_CONFIG_ROOT": str(config_dir), "PYTHONPATH": str(ROOT)})
    result = subprocess.run(
        [sys.executable, str(ROOT / "mmf"), "registry", "legacy-import", "--config-dir", str(config_dir), "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(result.stdout)
    combined = result.stdout + result.stderr

    assert payload["schema"] == mms_registry_cli.LEGACY_IMPORT_SCHEMA
    assert payload["skipped"] is True
    assert payload["skip_reason"] == "dry_run_apply_required"
    assert payload["model_count"] == 2
    assert "sk-config-local-secret" not in combined
    assert "sk-creds-local-secret" not in combined
    assert not (config_dir / "registry").exists()
    assert not (config_dir / "imports").exists()


def test_mmf_registry_legacy_import_can_read_source_root_and_write_preview_target(tmp_path: Path) -> None:
    source_dir = tmp_path / "mms"
    target_dir = tmp_path / "mms-next"
    source_dir.mkdir()
    target_dir.mkdir()
    (source_dir / "config.toml").write_text(
        """
        [[providers]]
        id = "source-local"
        name = "Source Local"
        default_openai_base_url = "https://source-local.example/v1"
        api_key = "sk-source-local-secret"
        protocols = ["openai_chat_completions"]
        fallback_models = ["source-model"]
        """,
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update({"MMS_CONFIG_ROOT": str(target_dir), "PYTHONPATH": str(ROOT)})
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "mmf"),
            "registry",
            "legacy-import",
            "--config-dir",
            str(target_dir),
            "--source-config-dir",
            str(source_dir),
            "--apply",
            "--json",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(result.stdout)
    combined = result.stdout + result.stderr

    assert payload["config_root"] == str(target_dir)
    assert payload["source_config_root"] == str(source_dir)
    assert payload["read_only_report"]["config_root"] == str(source_dir)
    assert payload["model_count"] == 1
    assert payload["route_candidates"]["provider_route_count"] == 1
    assert (target_dir / "registry" / "model-registry.sqlite").exists()
    assert not (source_dir / "registry").exists()
    assert not (source_dir / "imports").exists()
    assert "sk-source-local-secret" not in combined


def test_mmf_preview_import_legacy_wrapper_targets_preview_root(tmp_path: Path) -> None:
    source_dir = tmp_path / "mms"
    target_dir = tmp_path / "mms-next"
    real_home = tmp_path / "home"
    source_dir.mkdir()
    target_dir.mkdir()
    (source_dir / "config.toml").write_text(
        """
        [[providers]]
        id = "wrapped-source"
        default_openai_base_url = "https://wrapped-source.example/v1"
        api_key = "sk-wrapped-source-secret"
        fallback_models = ["wrapped-model"]
        """,
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(real_home),
            "MMS_REAL_HOME": str(real_home),
            "MMS_CONFIG_ROOT": str(target_dir),
            "PYTHONPATH": str(ROOT),
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "mmf"),
            "preview",
            "import-legacy",
            "--from",
            str(source_dir),
            "--apply",
            "--json",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(result.stdout)
    combined = result.stdout + result.stderr

    assert payload["config_root"] == str(target_dir)
    assert payload["source_config_root"] == str(source_dir)
    assert payload["route_candidates"]["provider_route_count"] == 1
    assert (target_dir / "registry" / "model-registry.sqlite").exists()
    assert not (source_dir / "registry").exists()
    assert not (real_home / ".config" / "mms-next").exists()
    assert "sk-wrapped-source-secret" not in combined


def test_registry_legacy_import_refuses_stable_root_without_allow_stable(tmp_path: Path) -> None:
    stable_root = tmp_path / "mms"
    stable_root.mkdir()
    (stable_root / "config.toml").write_text("[api]\nbase_url = 'https://stable.example/v1'\n", encoding="utf-8")

    try:
        mms_registry_cli.import_legacy_config(config_dir=stable_root, apply=True, command_name="mms registry")
    except mms_registry.RegistryValidationError as exc:
        assert "refusing to import into stable config root" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("stable legacy import should require --allow-stable")

    assert not (stable_root / "registry").exists()
    assert not (stable_root / "imports").exists()


def test_mmf_registry_legacy_import_apply_writes_preview_db_without_plaintext(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-next"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        """
        [[providers]]
        id = "local"
        name = "Local"
        default_openai_base_url = "https://config-local.example/v1"
        default_anthropic_base_url = "https://config-local.example/anthropic"
        api_key = "sk-config-local-secret"
        protocols = ["anthropic_messages", "openai_chat_completions"]
        fallback_models = ["gpt-5.5"]
        extra_models = ["qwen3.7-max"]
        hidden_models = ["retired-model"]
        priority = 42
        role = "primary"
        """,
        encoding="utf-8",
    )
    (config_dir / "credentials.sh").write_text(
        """
        export MMS_PROVIDER_LOCAL_OPENAI_BASE_URL='https://creds-local.example/v1'
        export MMS_PROVIDER_LOCAL_API_KEY='sk-creds-local-secret'
        """,
        encoding="utf-8",
    )
    mms_registry.write_json_atomic(
        config_dir / "model-policy.json",
        {"version": 1, "models": {"gpt-5.5": {"favorite": True}}},
    )
    mms_registry.write_json_atomic(
        config_dir / "model-routes.lineup.json",
        {"version": 1, "routes": {"lineup-only-model": {"context_window": 123}}},
    )
    env = os.environ.copy()
    env.update({"MMS_CONFIG_ROOT": str(config_dir), "PYTHONPATH": str(ROOT)})
    result = subprocess.run(
        [sys.executable, str(ROOT / "mmf"), "registry", "legacy-import", "--config-dir", str(config_dir), "--apply", "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(result.stdout)
    combined = result.stdout + result.stderr
    db_path = config_dir / "registry" / "model-registry.sqlite"
    import_path = Path(payload["import_path"])

    assert payload["schema"] == mms_registry_cli.LEGACY_IMPORT_SCHEMA
    assert payload["skipped"] is False
    assert payload["model_count"] == 4
    assert payload["plaintext_secret_in_db"] is False
    assert payload["source_snapshot"]["model_count"] == 4
    assert payload["route_candidates"]["provider_route_count"] == 2
    assert db_path.exists()
    assert import_path.exists()
    import_text = import_path.read_text(encoding="utf-8")
    assert "sk-config-local-secret" not in combined
    assert "sk-creds-local-secret" not in combined
    assert "sk-config-local-secret" not in import_text
    assert "sk-creds-local-secret" not in import_text

    db = sqlite3.connect(db_path)
    try:
        assert db.execute("SELECT count(*) FROM source_snapshot WHERE source_kind = ?", (mms_registry_cli.LEGACY_IMPORT_SOURCE_KIND,)).fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM model_identity").fetchone()[0] == 4
        assert db.execute("SELECT count(*) FROM provider_route").fetchone()[0] == 2
        secret_ref = db.execute("SELECT secret_ref FROM provider_route LIMIT 1").fetchone()[0]
        assert secret_ref.startswith("legacy-")
        assert "sk-" not in secret_ref
    finally:
        db.close()

    status = mms_registry_cli.model_source_status(config_dir=config_dir, command_name="mmf config source")
    status_text = json.dumps(status, ensure_ascii=False, sort_keys=True)
    candidates = status["legacy_import"]["candidates"]

    assert status["registry_db"]["counts"]["provider_route"] == 2
    assert candidates["status"] == "imported"
    assert candidates["source_snapshot_count"] == 1
    assert candidates["route_revision_count"] == 1
    assert candidates["route_group_count"] == 2
    assert candidates["provider_route_count"] == 2
    assert candidates["latest_snapshot"]["model_count"] == 4
    assert "sk-config-local-secret" not in status_text
    assert "sk-creds-local-secret" not in status_text


def test_publish_preview_bundle_from_legacy_candidates_verifies_manifest(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-next"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        """
        [[providers]]
        id = "primary-local"
        default_openai_base_url = "https://primary.example/v1"
        api_key = "sk-primary-local-secret"
        fallback_models = ["shared-model"]
        priority = 100
        role = "primary"

        [[providers]]
        id = "fallback-local"
        default_openai_base_url = "https://fallback.example/v1"
        api_key = "sk-fallback-local-secret"
        fallback_models = ["shared-model"]
        priority = 10
        role = "fallback"
        """,
        encoding="utf-8",
    )
    import_summary = mms_registry_cli.import_legacy_config(
        config_dir=config_dir,
        apply=True,
        command_name="mmf registry",
    )
    publish_summary = mms_registry_cli.publish_preview_bundle(config_dir=config_dir)
    verified = mms_registry_cli.verify_approved_bundle(config_dir=config_dir)
    status = mms_registry_cli.model_source_status(config_dir=config_dir, command_name="mmf config source")
    manifest_path = config_dir / "generated" / "model-registry.latest-approved.json"
    router_path = config_dir / "generated" / "model-routes.json"
    lineup_path = config_dir / "generated" / "model-routes.lineup.json"
    router = json.loads(router_path.read_text(encoding="utf-8"))
    lineup = json.loads(lineup_path.read_text(encoding="utf-8"))
    generated_text = "\n".join(path.read_text(encoding="utf-8") for path in (manifest_path, router_path, lineup_path))

    assert publish_summary["schema"] == "mms.preview_bundle_publish.v1"
    assert publish_summary["route_revision"] == import_summary["route_candidates"]["route_revision_id"]
    assert publish_summary["route_count"] == 1
    assert publish_summary["provider_route_count"] == 2
    assert publish_summary["runtime_ready"] is False
    assert verified["verified"] is True
    assert status["generated_bundle"]["verified"] is True
    assert status["generated_bundle"]["runtime_ready"] is False
    assert status["generated_bundle"]["runtime_ready_status"] == "not_ready"
    assert status["generated_bundle"]["router_missing_api_key_count"] == 2
    assert status["generated_bundle"]["router_missing_base_url_count"] == 0
    assert status["generated_bundle"]["router_secret_ref_count"] == 2
    assert router["runtime_ready"] is False
    assert router["routes"]["shared-model"]["primary"]["provider_id"] == "primary-local"
    assert router["routes"]["shared-model"]["primary"]["api_key"] == ""
    assert router["routes"]["shared-model"]["primary"]["secret_ref"].startswith("legacy-config:")
    assert router["routes"]["shared-model"]["fallbacks"][0]["provider_id"] == "fallback-local"
    assert lineup["routes"]["shared-model"]["primary"] == {"provider_id": "primary-local", "model_id": "shared-model"}
    assert "api_key" not in json.dumps(lineup, ensure_ascii=False)
    assert "sk-primary-local-secret" not in generated_text
    assert "sk-fallback-local-secret" not in generated_text

    db = sqlite3.connect(config_dir / "registry" / "model-registry.sqlite")
    try:
        status = db.execute(
            "SELECT status FROM registry_revision WHERE revision_id = ?",
            (publish_summary["route_revision"],),
        ).fetchone()[0]
        assert status == "approved"
    finally:
        db.close()


def test_preview_include_secrets_enables_runtime_ready_publish_without_db_plaintext(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-next"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        """
        [[providers]]
        id = "secret-primary"
        default_openai_base_url = "https://secret-primary.example/v1"
        api_key = "sk-secret-primary-value"
        fallback_models = ["secret-model"]
        priority = 100
        role = "primary"

        [[providers]]
        id = "secret-fallback"
        default_openai_base_url = "https://secret-fallback.example/v1"
        api_key = "sk-secret-fallback-value"
        fallback_models = ["secret-model"]
        priority = 10
        role = "fallback"
        """,
        encoding="utf-8",
    )
    import_summary = mms_registry_cli.import_legacy_config(
        config_dir=config_dir,
        apply=True,
        include_secrets=True,
        command_name="mmf registry",
    )
    import_text = json.dumps(import_summary, ensure_ascii=False, sort_keys=True)
    secret_backend = import_summary["secret_backend"]
    secret_path = Path(secret_backend["path"])
    publish_summary = mms_registry_cli.publish_preview_bundle(config_dir=config_dir)
    router = json.loads((config_dir / "generated" / "model-routes.json").read_text(encoding="utf-8"))
    status = mms_registry_cli.model_source_status(config_dir=config_dir, command_name="mmf config source")

    assert secret_backend["secret_count"] == 2
    assert secret_path.exists()
    assert oct(secret_path.stat().st_mode & 0o777) == "0o600"
    assert "sk-secret-primary-value" not in import_text
    assert "sk-secret-fallback-value" not in import_text
    assert publish_summary["runtime_ready"] is True
    assert publish_summary["missing_api_key_count"] == 0
    assert publish_summary["missing_base_url_count"] == 0
    assert router["runtime_ready"] is True
    assert router["routes"]["secret-model"]["primary"]["api_key"] == "sk-secret-primary-value"
    assert router["routes"]["secret-model"]["fallbacks"][0]["api_key"] == "sk-secret-fallback-value"
    assert status["generated_bundle"]["runtime_ready"] is True
    assert status["generated_bundle"]["router_missing_api_key_count"] == 0
    assert status["generated_bundle"]["router_missing_base_url_count"] == 0
    assert status["generated_bundle"]["router_secret_ref_count"] == 2

    db = sqlite3.connect(config_dir / "registry" / "model-registry.sqlite")
    try:
        leaked = db.execute(
            "SELECT count(*) FROM provider_route WHERE secret_ref LIKE 'sk-%'"
        ).fetchone()[0]
        assert leaked == 0
    finally:
        db.close()


def test_preview_include_secrets_without_route_url_is_not_runtime_ready(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-next"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        """
        [[providers]]
        id = "missing-url"
        api_key = "sk-missing-url-value"
        fallback_models = ["secret-model"]
        priority = 100
        role = "primary"
        """,
        encoding="utf-8",
    )
    mms_registry_cli.import_legacy_config(
        config_dir=config_dir,
        apply=True,
        include_secrets=True,
        command_name="mmf registry",
    )

    publish_summary = mms_registry_cli.publish_preview_bundle(config_dir=config_dir)
    status = mms_registry_cli.model_source_status(config_dir=config_dir, command_name="mmf config source")
    router = json.loads((config_dir / "generated" / "model-routes.json").read_text(encoding="utf-8"))

    assert publish_summary["runtime_ready"] is False
    assert publish_summary["missing_api_key_count"] == 0
    assert publish_summary["missing_base_url_count"] == 1
    assert "missing route base URLs" in publish_summary["runtime_ready_reason"]
    assert router["runtime_ready"] is False
    assert status["generated_bundle"]["runtime_ready"] is False
    assert status["generated_bundle"]["runtime_ready_status"] == "not_ready"
    assert status["generated_bundle"]["router_missing_api_key_count"] == 0
    assert status["generated_bundle"]["router_missing_base_url_count"] == 1
    doctor = mms_registry_cli.preview_doctor(config_dir=config_dir, command_name="mmf config doctor")
    assert doctor["counts"]["missing_api_keys"] == 0
    assert doctor["counts"]["missing_base_urls"] == 1
    assert doctor["next_actions"][0]["command"] == "./mmf config source --json"


def test_model_source_status_downgrades_stale_runtime_ready_when_route_url_missing(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-next"
    generated = config_dir / "generated"
    generated.mkdir(parents=True)
    router = generated / "model-routes.json"
    lineup = generated / "model-routes.lineup.json"
    profile = generated / "provider-profiles.generated.json"
    policy = generated / "model-policy.effective.json"
    capabilities = generated / "model-capabilities.approved.json"
    mms_registry.write_json_atomic(
        router,
        {
            "version": 1,
            "runtime_ready": True,
            "routes": {
                "missing-url-model": {
                    "primary": {
                        "provider_id": "missing-url",
                        "model_id": "missing-url-model",
                        "api_key": "sk-present",
                    },
                    "fallbacks": [],
                }
            },
        },
    )
    mms_registry.write_json_atomic(
        lineup,
        {
            "version": 1,
            "routes": {
                "missing-url-model": {
                    "primary": {"provider_id": "missing-url", "model_id": "missing-url-model"},
                    "fallbacks": [],
                }
            },
        },
    )
    mms_registry.write_json_atomic(profile, {"schema_version": 1, "profiles": {}})
    mms_registry.write_json_atomic(policy, {"version": 1, "models": {}})
    mms_registry.write_json_atomic(capabilities, {"schema": "mms.model_capabilities.approved.v1", "models": []})
    mms_registry.export_latest_approved_bundle_manifest(
        generated / "model-registry.latest-approved.json",
        bundle_revision="bundle_missing_url_test",
        capability_revision="cap_missing_url_test",
        route_revision="route_missing_url_test",
        policy_revision="policy_missing_url_test",
        profile_revision="profile_missing_url_test",
        files={
            "router": {"path": router, "canonical_path": "generated/model-routes.json", "sensitivity": "secret"},
            "lineup": {"path": lineup, "canonical_path": "generated/model-routes.lineup.json", "sensitivity": "non-secret"},
            "profile": {"path": profile, "canonical_path": "generated/provider-profiles.generated.json", "sensitivity": "non-secret"},
            "policy": {"path": policy, "canonical_path": "generated/model-policy.effective.json", "sensitivity": "non-secret"},
            "capabilities": {"path": capabilities, "canonical_path": "generated/model-capabilities.approved.json", "sensitivity": "non-secret"},
        },
    )

    status = mms_registry_cli.model_source_status(config_dir=config_dir, command_name="mmf config source")

    assert status["generated_bundle"]["verified"] is True
    assert status["generated_bundle"]["runtime_ready"] is False
    assert status["generated_bundle"]["runtime_ready_status"] == "not_ready"
    assert status["generated_bundle"]["router_missing_base_url_count"] == 1


def test_mmf_preview_publish_wrapper_fails_closed_without_candidates(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-next"
    config_dir.mkdir()
    env = os.environ.copy()
    env.update({"MMS_CONFIG_ROOT": str(config_dir), "PYTHONPATH": str(ROOT)})
    result = subprocess.run(
        [sys.executable, str(ROOT / "mmf"), "preview", "publish", "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 2
    assert payload["ok"] is False
    assert "preview route candidate" in payload["error"]
    assert not (config_dir / "generated" / "model-registry.latest-approved.json").exists()


def test_mmf_preview_import_then_publish_wrapper_verifies_bundle(tmp_path: Path) -> None:
    source_dir = tmp_path / "mms"
    target_dir = tmp_path / "mms-next"
    source_dir.mkdir()
    target_dir.mkdir()
    (source_dir / "config.toml").write_text(
        """
        [[providers]]
        id = "wrapped-publish"
        default_openai_base_url = "https://wrapped-publish.example/v1"
        api_key = "sk-wrapped-publish-secret"
        fallback_models = ["wrapped-publish-model"]
        """,
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update({"MMS_CONFIG_ROOT": str(target_dir), "PYTHONPATH": str(ROOT)})
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "mmf"),
            "preview",
            "import-legacy",
            "--from",
            str(source_dir),
            "--apply",
            "--json",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    publish = subprocess.run(
        [sys.executable, str(ROOT / "mmf"), "preview", "publish", "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    verify = subprocess.run(
        [sys.executable, str(ROOT / "mmf"), "preview", "verify", "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    status_result = subprocess.run(
        [sys.executable, str(ROOT / "mmf"), "preview", "status", "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(publish.stdout)
    verify_payload = json.loads(verify.stdout)
    status_payload = json.loads(status_result.stdout)
    router = json.loads((target_dir / "generated" / "model-routes.json").read_text(encoding="utf-8"))
    verified = mms_registry_cli.verify_approved_bundle(config_dir=target_dir)
    combined = publish.stdout + publish.stderr + json.dumps(router, ensure_ascii=False)

    assert payload["schema"] == "mms.preview_bundle_publish.v1"
    assert payload["route_count"] == 1
    assert payload["runtime_ready"] is False
    assert verify_payload["verified"] is True
    assert status_payload["generated_bundle"]["verified"] is True
    assert status_payload["generated_bundle"]["runtime_ready"] is False
    assert verified["verified"] is True
    assert router["routes"]["wrapped-publish-model"]["primary"]["provider_id"] == "wrapped-publish"
    assert "sk-wrapped-publish-secret" not in combined


def _write_preview_doctor_provider(config_dir: Path, *, provider_id: str = "doctor-local", api_key: str = "sk-doctor-secret") -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(
        f"""
        [[providers]]
        id = "{provider_id}"
        default_openai_base_url = "https://{provider_id}.example/v1"
        api_key = "{api_key}"
        fallback_models = ["doctor-model"]
        priority = 100
        role = "primary"
        """,
        encoding="utf-8",
    )


def test_preview_doctor_reports_needs_init_without_writing(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-next"

    summary = mms_registry_cli.preview_doctor(config_dir=config_dir)

    assert summary["schema"] == "mms.preview_doctor.v1"
    assert summary["status"] == "needs_init"
    assert summary["read_only"] is True
    assert summary["next_actions"][0]["command"] == "./mmf preview init --json"
    assert not config_dir.exists()


def test_preview_doctor_reports_wrong_root_for_stable_config(monkeypatch, tmp_path: Path) -> None:
    stable_root = tmp_path / "mms"
    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    monkeypatch.delenv("MMS_PREVIEW_MODE", raising=False)
    monkeypatch.delenv("MMS_COMMAND_NAME", raising=False)

    summary = mms_registry_cli.preview_doctor(config_dir=stable_root, command_name="mms registry")

    assert summary["status"] == "wrong_root"
    assert summary["checks"][0] == {"id": "preview_root", "ok": False, "detail": "stable"}
    assert summary["next_actions"][0]["command"] == "./mmf config root --json"
    assert not stable_root.exists()


def test_preview_doctor_reports_needs_import_after_init(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-next"
    mms_registry_cli.init_config_root(config_dir=config_dir, command_name="mmf preview")

    summary = mms_registry_cli.preview_doctor(config_dir=config_dir)

    assert summary["status"] == "needs_import"
    assert summary["counts"]["candidate_provider_routes"] == 0
    assert summary["next_actions"][0]["command"].startswith("./mmf preview import-legacy")


def test_preview_doctor_reports_needs_publish_after_import(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-next"
    _write_preview_doctor_provider(config_dir)
    mms_registry_cli.import_legacy_config(config_dir=config_dir, apply=True, command_name="mmf preview")

    summary = mms_registry_cli.preview_doctor(config_dir=config_dir)

    assert summary["status"] == "needs_publish"
    assert summary["counts"]["candidate_provider_routes"] == 1
    assert summary["bundle"]["verified"] is False
    assert summary["next_actions"][0]["command"] == "./mmf preview publish --json && ./mmf preview verify --json"


def test_preview_doctor_reports_verified_not_runtime_ready_without_secret_backend(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-next"
    _write_preview_doctor_provider(config_dir)
    mms_registry_cli.import_legacy_config(config_dir=config_dir, apply=True, command_name="mmf preview")
    mms_registry_cli.publish_preview_bundle(config_dir=config_dir)

    summary = mms_registry_cli.preview_doctor(config_dir=config_dir)

    assert summary["status"] == "verified_not_runtime_ready"
    assert summary["bundle"]["verified"] is True
    assert summary["bundle"]["runtime_ready"] is False
    assert summary["counts"]["missing_api_keys"] == 1
    assert summary["counts"]["missing_base_urls"] == 0
    assert summary["secrets"]["status"] == "missing"
    assert summary["next_actions"][0]["command"].startswith("./mmf preview import-legacy")


def test_mmf_preview_doctor_wrapper_reports_ready_with_secret_backend(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-next"
    _write_preview_doctor_provider(config_dir, api_key="sk-doctor-ready-secret")
    mms_registry_cli.import_legacy_config(
        config_dir=config_dir,
        apply=True,
        include_secrets=True,
        command_name="mmf preview",
    )
    mms_registry_cli.publish_preview_bundle(config_dir=config_dir)
    env = os.environ.copy()
    env.update({"MMS_CONFIG_ROOT": str(config_dir), "PYTHONPATH": str(ROOT)})
    result = subprocess.run(
        [sys.executable, str(ROOT / "mmf"), "preview", "doctor", "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(result.stdout)
    combined = result.stdout + result.stderr

    assert payload["status"] == "ready"
    assert payload["ready"] is True
    assert payload["result"] == "READY"
    assert payload["bundle"]["verified"] is True
    assert payload["bundle"]["runtime_ready"] is True
    assert payload["secrets"]["secret_count"] == 1
    assert payload["next_actions"][0]["command"].startswith("scripts/mms_health_watchdog.py")
    assert "sk-doctor-ready-secret" not in combined


def test_mmf_preview_doctor_strict_exit_distinguishes_ready_state(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-next"
    _write_preview_doctor_provider(config_dir, api_key="sk-doctor-strict-secret")
    mms_registry_cli.import_legacy_config(config_dir=config_dir, apply=True, command_name="mmf preview")
    mms_registry_cli.publish_preview_bundle(config_dir=config_dir)
    env = os.environ.copy()
    env.update({"MMS_CONFIG_ROOT": str(config_dir), "PYTHONPATH": str(ROOT)})

    not_ready = subprocess.run(
        [sys.executable, str(ROOT / "mmf"), "preview", "doctor", "--strict-exit", "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    not_ready_payload = json.loads(not_ready.stdout)
    assert not_ready.returncode == 2
    assert not_ready_payload["result"] == "VERIFIED_NOT_RUNTIME_READY"
    assert not_ready_payload["ready"] is False

    mms_registry_cli.import_legacy_config(
        config_dir=config_dir,
        apply=True,
        include_secrets=True,
        command_name="mmf preview",
    )
    mms_registry_cli.publish_preview_bundle(config_dir=config_dir)
    ready = subprocess.run(
        [sys.executable, str(ROOT / "mmf"), "preview", "doctor", "--strict-exit"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert ready.returncode == 0
    assert "result=READY" in ready.stdout
    assert "ready=True" in ready.stdout
    assert "sk-doctor-strict-secret" not in (ready.stdout + ready.stderr)


def test_mmf_preview_prepare_wrapper_runs_full_preview_flow_without_secrets(tmp_path: Path) -> None:
    source_dir = tmp_path / "mms"
    target_dir = tmp_path / "mms-next"
    _write_preview_doctor_provider(source_dir, provider_id="prepare-local", api_key="sk-prepare-secret")
    target_dir.mkdir()
    env = os.environ.copy()
    env.update({"MMS_CONFIG_ROOT": str(target_dir), "PYTHONPATH": str(ROOT)})
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "mmf"),
            "preview",
            "prepare",
            "--from",
            str(source_dir),
            "--json",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(result.stdout)
    combined = result.stdout + result.stderr

    assert payload["schema"] == "mms.preview_prepare.v1"
    assert payload["ok"] is True
    assert payload["ready"] is False
    assert payload["result"] == "VERIFIED_NOT_RUNTIME_READY"
    assert payload["config_root"] == str(target_dir)
    assert payload["source_config_root"] == str(source_dir)
    assert payload["include_secrets"] is False
    assert payload["stages"]["import"]["provider_route_count"] == 1
    assert payload["stages"]["publish"]["runtime_ready"] is False
    assert payload["stages"]["verify"]["verified"] is True
    assert payload["doctor"]["status"] == "verified_not_runtime_ready"
    assert (target_dir / "generated" / "model-registry.latest-approved.json").exists()
    assert not (source_dir / "registry").exists()
    assert "sk-prepare-secret" not in combined


def test_mmf_preview_prepare_include_secrets_reports_ready_without_stdout_leak(tmp_path: Path) -> None:
    source_dir = tmp_path / "mms"
    target_dir = tmp_path / "mms-next"
    _write_preview_doctor_provider(source_dir, provider_id="prepare-secret", api_key="sk-prepare-ready-secret")
    target_dir.mkdir()
    env = os.environ.copy()
    env.update({"MMS_CONFIG_ROOT": str(target_dir), "PYTHONPATH": str(ROOT)})
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "mmf"),
            "preview",
            "prepare",
            "--from",
            str(source_dir),
            "--include-secrets",
            "--json",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    payload = json.loads(result.stdout)
    combined = result.stdout + result.stderr
    secret_path = target_dir / "secrets" / "legacy-secrets.json"

    assert payload["ok"] is True
    assert payload["ready"] is True
    assert payload["result"] == "READY"
    assert payload["include_secrets"] is True
    assert payload["stages"]["import"]["secret_backend_count"] == 1
    assert payload["stages"]["publish"]["runtime_ready"] is True
    assert payload["stages"]["publish"]["missing_api_key_count"] == 0
    assert payload["doctor"]["status"] == "ready"
    assert secret_path.exists()
    assert oct(secret_path.stat().st_mode & 0o777) == "0o600"
    assert "sk-prepare-ready-secret" not in combined


def test_mmf_preview_prepare_repeated_run_backs_up_existing_preview_db(tmp_path: Path) -> None:
    source_dir = tmp_path / "mms"
    target_dir = tmp_path / "mms-next"
    _write_preview_doctor_provider(source_dir, provider_id="prepare-backup", api_key="sk-prepare-backup-secret")
    target_dir.mkdir()
    env = os.environ.copy()
    env.update({"MMS_CONFIG_ROOT": str(target_dir), "PYTHONPATH": str(ROOT)})

    first = subprocess.run(
        [
            sys.executable,
            str(ROOT / "mmf"),
            "preview",
            "prepare",
            "--from",
            str(source_dir),
            "--json",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    second = subprocess.run(
        [
            sys.executable,
            str(ROOT / "mmf"),
            "preview",
            "prepare",
            "--from",
            str(source_dir),
            "--json",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    first_payload = json.loads(first.stdout)
    second_payload = json.loads(second.stdout)
    backup_path = Path(second_payload["stages"]["backup"]["backup_path"])

    assert first_payload["stages"]["backup"]["skipped"] is True
    assert first_payload["stages"]["backup"]["reason"] == "new_db"
    assert second_payload["stages"]["backup"]["skipped"] is False
    assert backup_path.exists()
    assert backup_path.parent == target_dir / "backups" / "db"
    assert not (source_dir / "backups").exists()
    assert "sk-prepare-backup-secret" not in (second.stdout + second.stderr)


def test_mmf_preview_prepare_strict_exit_requires_runtime_ready(tmp_path: Path) -> None:
    source_dir = tmp_path / "mms"
    target_dir = tmp_path / "mms-next"
    _write_preview_doctor_provider(source_dir, provider_id="prepare-strict", api_key="sk-prepare-strict-secret")
    target_dir.mkdir()
    env = os.environ.copy()
    env.update({"MMS_CONFIG_ROOT": str(target_dir), "PYTHONPATH": str(ROOT)})
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "mmf"),
            "preview",
            "prepare",
            "--from",
            str(source_dir),
            "--strict-exit",
            "--json",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 2
    assert payload["ok"] is True
    assert payload["ready"] is False
    assert payload["result"] == "VERIFIED_NOT_RUNTIME_READY"
    assert "sk-prepare-strict-secret" not in (result.stdout + result.stderr)


def _write_config_artifacts(config_dir: Path) -> None:
    generated_route = {
        "version": 1,
        "routes": {
            "gemini-3-flash-agent(high)": {
                "primary": {
                    "provider_id": "local-gemini",
                    "model_id": "gemini-3-flash-agent(high)",
                },
                "fallbacks": [],
            }
        },
    }
    artifacts = {
        "model-routes.json": generated_route,
        "model-routes.lineup.json": {
            "version": 1,
            "routes": {
                "gemini-3-flash-agent(high)": {
                    "primary": {
                        "provider_id": "local-gemini",
                        "model_id": "gemini-3-flash-agent(high)",
                        "max_context_tokens": 1048576,
                    },
                    "fallbacks": [],
                }
            },
        },
        "provider-profiles.json": {"version": 1, "profiles": {"local-gemini": {"protocol": "openai_chat_completions"}}},
        "model-policy.json": {"version": 1, "models": {"gemini-3-flash-agent(high)": {"visible": True}}},
    }
    for name, payload in artifacts.items():
        mms_registry.write_json_atomic(config_dir / name, payload)


def test_publish_approved_bundle_verifies_and_resolves_model(tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-config"
    db_path = tmp_path / "model-registry.sqlite"
    _write_config_artifacts(config_dir)
    mms_registry_cli.refresh_source_snapshots(db_path=db_path, paths=[REFERENCE_JSON])

    summary = mms_registry_cli.publish_approved_bundle(config_dir=config_dir, db_path=db_path)
    verified = mms_registry_cli.verify_approved_bundle(config_dir=config_dir)
    caps = mms_registry_cli.resolve_approved_model(
        "gemini-3-flash-agent(high)",
        config_dir=config_dir,
    )

    manifest_path = config_dir / "generated" / "model-registry.latest-approved.json"
    assert summary["manifest_path"] == str(manifest_path)
    assert verified["verified"] is True
    assert "capabilities" in verified["verified_files"]
    assert caps["context_window_tokens"] == 1048576
    assert caps["supports_thinking"] is True
    assert caps["thinking_control"]["control_type"] == "thinkingLevel"


def test_registry_command_publish_verify_and_resolve(capsys, tmp_path: Path) -> None:
    config_dir = tmp_path / "mms-config"
    db_path = tmp_path / "model-registry.sqlite"
    _write_config_artifacts(config_dir)
    mms_registry_cli.refresh_source_snapshots(db_path=db_path, paths=[REFERENCE_JSON])

    publish_rc = mms_registry_cli.handle_registry_command(
        ["--db", str(db_path), "publish-approved", "--config-dir", str(config_dir)],
        command_name="mms registry",
    )
    verify_rc = mms_registry_cli.handle_registry_command(
        ["--db", str(db_path), "verify", "--config-dir", str(config_dir)],
        command_name="mms registry",
    )
    resolve_rc = mms_registry_cli.handle_registry_command(
        ["--db", str(db_path), "resolve", "gemini-3-flash-agent(high)", "--config-dir", str(config_dir)],
        command_name="mms registry",
    )
    out = capsys.readouterr().out

    assert publish_rc == 0
    assert verify_rc == 0
    assert resolve_rc == 0
    assert "bundle_revision=bundle_" in out
    assert "verified=True" in out
    assert "thinking_control_type=thinkingLevel" in out
