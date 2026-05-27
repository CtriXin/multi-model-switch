from __future__ import annotations

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
