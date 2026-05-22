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
    assert status["counts"]["model_identity"] >= 30
    assert status["counts"]["model_fact"] == summary["fact_count"]


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
