from __future__ import annotations

from pathlib import Path

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
