from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any, Iterable

import mms_registry


ROOT = Path(__file__).resolve().parent
DEFAULT_REFERENCE_DIR = ROOT / "docs" / "reference" / "model-capability-calibration"


def _reference_snapshot_paths(paths: Iterable[str | Path] | None = None) -> list[Path]:
    if paths:
        candidates = [Path(path).expanduser() for path in paths]
    else:
        candidates = sorted(DEFAULT_REFERENCE_DIR.glob("*.json"))
    return [path for path in candidates if path.exists() and path.is_file()]


def refresh_source_snapshots(
    *,
    db_path: str | Path | None = None,
    paths: Iterable[str | Path] | None = None,
) -> dict[str, Any]:
    """Import local source snapshots into the registry DB without promotion."""
    snapshot_paths = _reference_snapshot_paths(paths)
    db = mms_registry.open_registry(db_path)
    imported: list[dict[str, Any]] = []
    try:
        for path in snapshot_paths:
            imported.append(mms_registry.import_source_snapshot(db, path))
    finally:
        db.close()
    return {
        "db_path": str(Path(db_path) if db_path else mms_registry.default_registry_db_path()),
        "source_paths": [str(path) for path in snapshot_paths],
        "imported": imported,
        "imported_count": len(imported),
        "model_count": sum(int(item.get("model_count", 0) or 0) for item in imported),
        "fact_count": sum(int(item.get("fact_count", 0) or 0) for item in imported),
    }


def registry_status(*, db_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(db_path) if db_path else mms_registry.default_registry_db_path()
    exists_before = path.exists()
    db = mms_registry.open_registry(path)
    try:
        counts = {}
        for table in (
            "source_snapshot",
            "model_identity",
            "model_fact",
            "registry_revision",
            "export_snapshot",
            "tombstone_event",
        ):
            counts[table] = int(db.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
        latest = db.execute(
            """
            SELECT source_kind, source_path, captured_at, model_count, content_hash
            FROM source_snapshot
            ORDER BY snapshot_id DESC
            LIMIT 1
            """
        ).fetchone()
        latest_snapshot = dict(latest) if latest is not None else {}
        user_version = int(db.execute("PRAGMA user_version").fetchone()[0])
        journal_mode = str(db.execute("PRAGMA journal_mode").fetchone()[0])
    finally:
        db.close()
    return {
        "db_path": str(path),
        "existed_before": exists_before,
        "user_version": user_version,
        "journal_mode": journal_mode,
        "counts": counts,
        "latest_source_snapshot": latest_snapshot,
    }


def _print_status(status: dict[str, Any]) -> None:
    counts = status.get("counts") if isinstance(status.get("counts"), dict) else {}
    latest = status.get("latest_source_snapshot") if isinstance(status.get("latest_source_snapshot"), dict) else {}
    print("MMS Registry")
    print(f"db_path={status.get('db_path')}")
    print(f"user_version={status.get('user_version')}")
    print(f"journal_mode={status.get('journal_mode')}")
    for key in sorted(counts):
        print(f"{key}={counts[key]}")
    if latest:
        print(f"latest_source_kind={latest.get('source_kind')}")
        print(f"latest_source_path={latest.get('source_path')}")
        print(f"latest_model_count={latest.get('model_count')}")
        print(f"latest_captured_at={latest.get('captured_at')}")
    else:
        print("latest_source_snapshot=none")


def _print_refresh(summary: dict[str, Any]) -> None:
    print("MMS Registry Refresh Sources")
    print(f"db_path={summary.get('db_path')}")
    print(f"imported_count={summary.get('imported_count')}")
    print(f"model_count={summary.get('model_count')}")
    print(f"fact_count={summary.get('fact_count')}")
    for item in summary.get("imported") or []:
        print(
            "source_snapshot="
            f"{item.get('snapshot_id')} "
            f"models={item.get('model_count')} "
            f"facts={item.get('fact_count')} "
            f"path={item.get('source_path')}"
        )


def handle_registry_command(argv: list[str], *, command_name: str = "mms registry") -> int:
    parser = argparse.ArgumentParser(
        prog=command_name,
        description="Manage MMS local model registry source truth.",
    )
    parser.add_argument("--db", default="", help="Override registry sqlite path")
    subparsers = parser.add_subparsers(dest="subcommand")

    subparsers.add_parser("status", help="Show local registry DB status")
    subparsers.add_parser("doctor", help="Alias of status for now; does not change runtime truth")
    refresh_parser = subparsers.add_parser(
        "refresh-sources",
        help="Import local reference snapshots as source_truth/candidate evidence",
    )
    refresh_parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="Reference JSON snapshot path; may be repeated. Defaults to docs/reference/model-capability-calibration/*.json",
    )

    args = parser.parse_args(argv)
    db_path = args.db or None
    if args.subcommand in {None, "status", "doctor"}:
        _print_status(registry_status(db_path=db_path))
        return 0
    if args.subcommand == "refresh-sources":
        summary = refresh_source_snapshots(db_path=db_path, paths=args.path or None)
        _print_refresh(summary)
        return 0
    return 2


__all__ = [
    "DEFAULT_REFERENCE_DIR",
    "handle_registry_command",
    "refresh_source_snapshots",
    "registry_status",
]
