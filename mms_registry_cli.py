from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.request import Request, urlopen

import mms_registry
from mms_capability_resolver import resolve_model_capabilities


ROOT = Path(__file__).resolve().parent
DEFAULT_REFERENCE_DIR = ROOT / "docs" / "reference" / "model-capability-calibration"
DEFAULT_SOURCE_REFRESH_MAX_AGE_HOURS = 24 * 14
DEFAULT_OPENROUTER_REFRESH_MAX_AGE_HOURS = 24 * 7
OPENROUTER_MODELS_API_URL = "https://openrouter.ai/api/v1/models"


def _reference_snapshot_paths(paths: Iterable[str | Path] | None = None) -> list[Path]:
    if paths:
        candidates = [Path(path).expanduser() for path in paths]
    else:
        candidates = sorted(DEFAULT_REFERENCE_DIR.glob("*.json"))
    return [path for path in candidates if path.exists() and path.is_file()]


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def source_freshness(
    *,
    db_path: str | Path | None = None,
    paths: Iterable[str | Path] | None = None,
    max_age_hours: int = DEFAULT_SOURCE_REFRESH_MAX_AGE_HOURS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Report local source-reference staleness without importing new facts."""
    snapshot_paths = _reference_snapshot_paths(paths)
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    max_age_seconds = max(0, int(max_age_hours or 0)) * 3600
    db = mms_registry.open_registry(db_path)
    sources: list[dict[str, Any]] = []
    try:
        for path in snapshot_paths:
            raw = path.read_bytes()
            content_hash = mms_registry.sha256_hex(raw)
            row = db.execute(
                """
                SELECT checked_at, content_hash, snapshot_id, status
                FROM source_check
                WHERE source_kind = ? AND source_path = ?
                """,
                (mms_registry.CALIBRATION_SOURCE_KIND, str(path)),
            ).fetchone()
            checked_at = str(row["checked_at"]) if row is not None else ""
            checked_dt = _parse_utc(checked_at)
            age_seconds = int((current - checked_dt).total_seconds()) if checked_dt is not None else None
            missing = row is None
            changed = row is not None and str(row["content_hash"]) != content_hash
            stale = age_seconds is None or age_seconds >= max_age_seconds
            due = bool(missing or changed or stale)
            if missing:
                reason = "never_checked"
            elif changed:
                reason = "source_content_changed"
            elif stale:
                reason = "max_age_exceeded"
            else:
                reason = "fresh"
            sources.append(
                {
                    "source_kind": mms_registry.CALIBRATION_SOURCE_KIND,
                    "source_path": str(path),
                    "checked_at": checked_at,
                    "age_seconds": age_seconds,
                    "max_age_hours": int(max_age_hours or 0),
                    "content_hash": content_hash,
                    "last_checked_hash": str(row["content_hash"]) if row is not None else "",
                    "snapshot_id": int(row["snapshot_id"]) if row is not None and row["snapshot_id"] is not None else None,
                    "status": str(row["status"]) if row is not None else "missing",
                    "due": due,
                    "reason": reason,
                }
            )
    finally:
        db.close()
    due_sources = [source for source in sources if source.get("due")]
    return {
        "db_path": str(Path(db_path) if db_path else mms_registry.default_registry_db_path()),
        "max_age_hours": int(max_age_hours or 0),
        "source_count": len(sources),
        "due_count": len(due_sources),
        "fresh_count": len(sources) - len(due_sources),
        "sources": sources,
    }


def _openrouter_file_content_hash(path: str | Path) -> str:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return mms_registry.sha256_hex(canonical)


def _row_age_status(
    row,
    *,
    max_age_hours: int,
    now: datetime | None = None,
    expected_content_hash: str | None = None,
) -> dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    checked_at = str(row["checked_at"]) if row is not None else ""
    checked_dt = _parse_utc(checked_at)
    age_seconds = int((current - checked_dt).total_seconds()) if checked_dt is not None else None
    stale = age_seconds is None or age_seconds >= max(0, int(max_age_hours or 0)) * 3600
    changed = row is not None and bool(expected_content_hash) and str(row["content_hash"]) != expected_content_hash
    if row is None:
        reason = "never_checked"
    elif changed:
        reason = "source_content_changed"
    elif stale:
        reason = "max_age_exceeded"
    else:
        reason = "fresh"
    return {
        "checked_at": checked_at,
        "age_seconds": age_seconds,
        "max_age_hours": int(max_age_hours or 0),
        "due": bool(row is None or changed or stale),
        "reason": reason,
    }


def openrouter_catalog_freshness(
    *,
    db_path: str | Path | None = None,
    max_age_hours: int = DEFAULT_OPENROUTER_REFRESH_MAX_AGE_HOURS,
    now: datetime | None = None,
    source_path: str | Path | None = None,
    expected_content_hash: str | None = None,
) -> dict[str, Any]:
    catalog_source_path = str(Path(source_path).expanduser() if source_path else OPENROUTER_MODELS_API_URL)
    db = mms_registry.open_registry(db_path)
    try:
        row = db.execute(
            """
            SELECT checked_at, content_hash, snapshot_id, status
            FROM source_check
            WHERE source_kind = ? AND source_path = ?
            """,
            (mms_registry.OPENROUTER_MODELS_SOURCE_KIND, catalog_source_path),
        ).fetchone()
    finally:
        db.close()
    status = _row_age_status(
        row,
        max_age_hours=max_age_hours,
        now=now,
        expected_content_hash=expected_content_hash,
    )
    status.update(
        {
            "db_path": str(Path(db_path) if db_path else mms_registry.default_registry_db_path()),
            "source_kind": mms_registry.OPENROUTER_MODELS_SOURCE_KIND,
            "source_path": catalog_source_path,
            "content_hash": str(row["content_hash"]) if row is not None else "",
            "expected_content_hash": expected_content_hash or "",
            "snapshot_id": int(row["snapshot_id"]) if row is not None and row["snapshot_id"] is not None else None,
            "status": str(row["status"]) if row is not None else "missing",
        }
    )
    return status


def refresh_source_snapshots(
    *,
    db_path: str | Path | None = None,
    paths: Iterable[str | Path] | None = None,
    if_due: bool = False,
    max_age_hours: int = DEFAULT_SOURCE_REFRESH_MAX_AGE_HOURS,
) -> dict[str, Any]:
    """Import local source snapshots into the registry DB without promotion."""
    snapshot_paths = _reference_snapshot_paths(paths)
    freshness = None
    if if_due:
        freshness = source_freshness(db_path=db_path, paths=snapshot_paths, max_age_hours=max_age_hours)
        due_paths = {str(item.get("source_path")) for item in freshness.get("sources", []) if item.get("due")}
        snapshot_paths = [path for path in snapshot_paths if str(path) in due_paths]
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
        "skipped_count": len(_reference_snapshot_paths(paths)) - len(snapshot_paths) if if_due else 0,
        "model_count": sum(int(item.get("model_count", 0) or 0) for item in imported),
        "fact_count": sum(int(item.get("fact_count", 0) or 0) for item in imported),
        "freshness": freshness or source_freshness(db_path=db_path, paths=_reference_snapshot_paths(paths), max_age_hours=max_age_hours),
    }


def fetch_openrouter_catalog(
    *,
    db_path: str | Path | None = None,
    url: str = OPENROUTER_MODELS_API_URL,
    from_file: str | Path | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Fetch or import OpenRouter model catalog as provider_catalog evidence."""
    source_url = str(url or OPENROUTER_MODELS_API_URL)
    if from_file:
        file_path = Path(from_file).expanduser()
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        source_path = str(file_path)
        transport = "file"
    else:
        request = Request(
            source_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "MMS-Registry/1.0 (+https://github.com/CtriXin/multi-model-switch)",
            },
        )
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        source_path = source_url
        transport = "network"
    if not isinstance(payload, dict):
        raise mms_registry.RegistryValidationError("OpenRouter catalog payload must be a JSON object")
    db = mms_registry.open_registry(db_path)
    try:
        summary = mms_registry.import_raw_source_payload(
            db,
            payload,
            source_kind=mms_registry.OPENROUTER_MODELS_SOURCE_KIND,
            source_path=source_path,
        )
    finally:
        db.close()
    summary.update(
        {
            "db_path": str(Path(db_path) if db_path else mms_registry.default_registry_db_path()),
            "transport": transport,
            "url": source_url,
        }
    )
    return summary


def _latest_source_payload(db, source_kind: str) -> tuple[dict[str, Any], dict[str, Any]]:
    row = db.execute(
        """
        SELECT snapshot_id, source_kind, source_path, captured_at, content_hash, model_count, payload_json
        FROM source_snapshot
        WHERE source_kind = ?
        ORDER BY snapshot_id DESC
        LIMIT 1
        """,
        (source_kind,),
    ).fetchone()
    if row is None:
        raise mms_registry.RegistryValidationError(f"missing source snapshot: {source_kind}")
    payload = json.loads(str(row["payload_json"] or "{}"))
    if not isinstance(payload, dict):
        raise mms_registry.RegistryValidationError(f"source snapshot payload must be object: {source_kind}")
    return dict(row), payload


def _openrouter_items(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    data = payload.get("data") if isinstance(payload.get("data"), list) else []
    items = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if model_id:
            items[model_id] = item
    return items


def _calibration_openrouter_refs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for model in payload.get("models") or []:
        if not isinstance(model, dict):
            continue
        alias = str(model.get("alias") or model.get("canonical_model_id") or "").strip()
        for ref in model.get("provider_catalog_references") or []:
            if not isinstance(ref, dict):
                continue
            if str(ref.get("source") or "").lower() != "openrouter":
                continue
            provider_model_id = str(ref.get("model_id") or model.get("openrouter_model_id") or "").strip()
            if not provider_model_id:
                continue
            top_provider = ref.get("top_provider") if isinstance(ref.get("top_provider"), dict) else {}
            refs.append(
                {
                    "model_key": alias,
                    "provider_model_id": provider_model_id,
                    "context_length": ref.get("context_length"),
                    "max_completion_tokens": top_provider.get("max_completion_tokens"),
                    "pricing": ref.get("pricing_raw_usd_per_unit") or model.get("provider_pricing_raw_usd_per_unit") or {},
                    "supported_parameters": sorted(ref.get("supported_parameters") or model.get("provider_supported_parameters") or []),
                }
            )
    return refs


def _candidate_value(item: dict[str, Any], field_key: str) -> Any:
    if field_key == "context_length":
        return item.get("context_length")
    if field_key == "max_completion_tokens":
        top_provider = item.get("top_provider") if isinstance(item.get("top_provider"), dict) else {}
        return top_provider.get("max_completion_tokens")
    if field_key == "pricing":
        return item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
    if field_key == "supported_parameters":
        return sorted(item.get("supported_parameters") or [])
    return None


def _canonical_equal(left: Any, right: Any) -> bool:
    return json.dumps(left, ensure_ascii=False, sort_keys=True, separators=(",", ":")) == json.dumps(
        right,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def diff_openrouter_catalog(
    *,
    db_path: str | Path | None = None,
    store: bool = True,
    limit: int = 50,
) -> dict[str, Any]:
    """Compare latest OpenRouter catalog source with calibration OpenRouter refs."""
    db = mms_registry.open_registry(db_path)
    try:
        openrouter_snapshot, openrouter_payload = _latest_source_payload(db, mms_registry.OPENROUTER_MODELS_SOURCE_KIND)
        baseline_snapshot, baseline_payload = _latest_source_payload(db, mms_registry.CALIBRATION_SOURCE_KIND)
        catalog = _openrouter_items(openrouter_payload)
        refs = _calibration_openrouter_refs(baseline_payload)
        changes: list[dict[str, Any]] = []
        missing = 0
        for ref in refs:
            item = catalog.get(ref["provider_model_id"])
            if item is None:
                missing += 1
                changes.append(
                    {
                        "change_kind": "provider_catalog_missing",
                        "model_key": ref["model_key"],
                        "provider_model_id": ref["provider_model_id"],
                        "field_key": "presence",
                        "old_value": "present_in_baseline",
                        "new_value": "missing_in_catalog",
                        "metadata": {},
                    }
                )
                continue
            for field_key in ("context_length", "max_completion_tokens", "pricing", "supported_parameters"):
                old_value = ref.get(field_key)
                new_value = _candidate_value(item, field_key)
                if _canonical_equal(old_value, new_value):
                    continue
                changes.append(
                    {
                        "change_kind": "provider_catalog_changed",
                        "model_key": ref["model_key"],
                        "provider_model_id": ref["provider_model_id"],
                        "field_key": field_key,
                        "old_value": old_value,
                        "new_value": new_value,
                        "metadata": {"source": "openrouter"},
                    }
                )
        referenced_ids = {ref["provider_model_id"] for ref in refs}
        untracked_count = len(set(catalog) - referenced_ids)
        record = {"recorded_count": 0}
        if store:
            record = mms_registry.record_candidate_changes(
                db,
                changes,
                source_snapshot_id=int(openrouter_snapshot["snapshot_id"]),
                baseline_snapshot_id=int(baseline_snapshot["snapshot_id"]),
            )
        stored_count = int(record.get("recorded_count", 0) or 0)
    finally:
        db.close()
    return {
        "db_path": str(Path(db_path) if db_path else mms_registry.default_registry_db_path()),
        "source_snapshot_id": int(openrouter_snapshot["snapshot_id"]),
        "baseline_snapshot_id": int(baseline_snapshot["snapshot_id"]),
        "matched_reference_count": len(refs),
        "missing_reference_count": missing,
        "untracked_catalog_count": untracked_count,
        "change_count": len(changes),
        "stored_count": stored_count,
        "changes": changes[: max(0, int(limit or 0))],
    }


def scheduled_refresh(
    *,
    db_path: str | Path | None = None,
    max_age_hours: int = DEFAULT_SOURCE_REFRESH_MAX_AGE_HOURS,
    openrouter_max_age_hours: int = DEFAULT_OPENROUTER_REFRESH_MAX_AGE_HOURS,
    include_openrouter: bool = True,
    no_network: bool = False,
    openrouter_from_file: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Safe entrypoint for cron/launchd/manual scheduled refresh runs."""
    source_status = source_freshness(db_path=db_path, max_age_hours=max_age_hours)
    openrouter_source_path = str(Path(openrouter_from_file).expanduser()) if openrouter_from_file else OPENROUTER_MODELS_API_URL
    openrouter_expected_hash = _openrouter_file_content_hash(openrouter_from_file) if openrouter_from_file else None
    openrouter_status = openrouter_catalog_freshness(
        db_path=db_path,
        max_age_hours=openrouter_max_age_hours,
        source_path=openrouter_source_path,
        expected_content_hash=openrouter_expected_hash,
    )
    result: dict[str, Any] = {
        "db_path": str(Path(db_path) if db_path else mms_registry.default_registry_db_path()),
        "dry_run": bool(dry_run),
        "source_due_count": source_status.get("due_count", 0),
        "source_status": source_status,
        "openrouter_due": bool(openrouter_status.get("due")),
        "openrouter_status": openrouter_status,
        "source_refresh": {"skipped": True},
        "openrouter_fetch": {"skipped": True},
        "openrouter_diff": {"skipped": True},
    }
    if dry_run:
        return result
    if int(source_status.get("due_count", 0) or 0) > 0:
        result["source_refresh"] = refresh_source_snapshots(
            db_path=db_path,
            if_due=True,
            max_age_hours=max_age_hours,
        )
    else:
        result["source_refresh"] = {"skipped": True, "reason": "not_due"}
    if not include_openrouter:
        result["openrouter_fetch"] = {"skipped": True, "reason": "no_openrouter"}
        result["openrouter_diff"] = {"skipped": True, "reason": "no_openrouter"}
        return result
    if include_openrouter and bool(openrouter_status.get("due")):
        if no_network and not openrouter_from_file:
            result["openrouter_fetch"] = {"skipped": True, "reason": "no_network"}
        else:
            try:
                result["openrouter_fetch"] = fetch_openrouter_catalog(
                    db_path=db_path,
                    from_file=openrouter_from_file,
                )
            except Exception as exc:  # Network scheduled jobs should record failure, not alter runtime truth.
                result["openrouter_fetch"] = {
                    "skipped": True,
                    "status": "error",
                    "reason": f"{type(exc).__name__}: {exc}",
                }
                return result
            try:
                result["openrouter_diff"] = diff_openrouter_catalog(db_path=db_path, limit=20)
            except mms_registry.RegistryValidationError as exc:
                result["openrouter_diff"] = {"skipped": True, "reason": str(exc)}
    else:
        result["openrouter_fetch"] = {"skipped": True, "reason": "not_due"}
        result["openrouter_diff"] = {"skipped": True, "reason": "not_due"}
    return result


def registry_status(*, db_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(db_path) if db_path else mms_registry.default_registry_db_path()
    exists_before = path.exists()
    db = mms_registry.open_registry(path)
    try:
        counts = {}
        for table in (
            "source_snapshot",
            "source_check",
            "candidate_change",
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
    freshness = source_freshness(db_path=path)
    return {
        "db_path": str(path),
        "existed_before": exists_before,
        "user_version": user_version,
        "journal_mode": journal_mode,
        "counts": counts,
        "latest_source_snapshot": latest_snapshot,
        "source_freshness": freshness,
    }


def publish_approved_bundle(
    *,
    config_dir: str | Path | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    return mms_registry.publish_latest_approved_bundle(config_dir=config_dir, db_path=db_path, actor="mms")


def verify_approved_bundle(
    *,
    config_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    return mms_registry.verify_latest_approved_bundle(config_dir=config_dir, manifest_path=manifest_path)


def resolve_approved_model(
    model_name: str,
    *,
    config_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    facts_path = mms_registry.latest_approved_capability_facts_path(
        config_dir=config_dir,
        manifest_path=manifest_path,
    )
    return resolve_model_capabilities(model_name, approved_facts_path=facts_path)


def backup_registry_db(
    *,
    config_dir: str | Path | None = None,
    db_path: str | Path | None = None,
    backup_dir: str | Path | None = None,
    reason: str = "manual",
) -> dict[str, Any]:
    return mms_registry.backup_registry_db(
        config_dir=config_dir,
        db_path=db_path,
        backup_dir=backup_dir,
        reason=reason,
    )


def restore_registry_db(
    backup_path: str | Path,
    *,
    config_dir: str | Path | None = None,
    db_path: str | Path | None = None,
    apply: bool = False,
    reason: str = "manual",
) -> dict[str, Any]:
    return mms_registry.restore_registry_db(
        backup_path,
        config_dir=config_dir,
        db_path=db_path,
        apply=apply,
        reason=reason,
    )


def _print_status(status: dict[str, Any]) -> None:
    counts = status.get("counts") if isinstance(status.get("counts"), dict) else {}
    latest = status.get("latest_source_snapshot") if isinstance(status.get("latest_source_snapshot"), dict) else {}
    freshness = status.get("source_freshness") if isinstance(status.get("source_freshness"), dict) else {}
    print("MMS Registry")
    print(f"db_path={status.get('db_path')}")
    print(f"user_version={status.get('user_version')}")
    print(f"journal_mode={status.get('journal_mode')}")
    for key in sorted(counts):
        print(f"{key}={counts[key]}")
    print(f"source_due_count={freshness.get('due_count', 0)}")
    print(f"source_fresh_count={freshness.get('fresh_count', 0)}")
    if latest:
        print(f"latest_source_kind={latest.get('source_kind')}")
        print(f"latest_source_path={latest.get('source_path')}")
        print(f"latest_model_count={latest.get('model_count')}")
        print(f"latest_captured_at={latest.get('captured_at')}")
    else:
        print("latest_source_snapshot=none")


def _print_freshness(summary: dict[str, Any]) -> None:
    print("MMS Registry Source Staleness")
    print(f"db_path={summary.get('db_path')}")
    print(f"max_age_hours={summary.get('max_age_hours')}")
    print(f"source_count={summary.get('source_count')}")
    print(f"due_count={summary.get('due_count')}")
    print(f"fresh_count={summary.get('fresh_count')}")
    for item in summary.get("sources") or []:
        print(
            "source="
            f"due={item.get('due')} "
            f"reason={item.get('reason')} "
            f"checked_at={item.get('checked_at') or '-'} "
            f"path={item.get('source_path')}"
        )


def _print_publish(summary: dict[str, Any]) -> None:
    print("MMS Registry Publish Approved Bundle")
    print(f"manifest_path={summary.get('manifest_path')}")
    print(f"bundle_revision={summary.get('bundle_revision')}")
    print(f"capability_revision={summary.get('capability_revision')}")
    print(f"route_revision={summary.get('route_revision')}")
    print(f"policy_revision={summary.get('policy_revision')}")
    print(f"profile_revision={summary.get('profile_revision')}")
    files = summary.get("files") if isinstance(summary.get("files"), dict) else {}
    for name in sorted(files):
        print(f"file_{name}={files[name]}")


def _print_verify(summary: dict[str, Any]) -> None:
    manifest = summary.get("manifest") if isinstance(summary.get("manifest"), dict) else {}
    files = summary.get("verified_files") if isinstance(summary.get("verified_files"), dict) else {}
    print("MMS Registry Verify Approved Bundle")
    print(f"verified={summary.get('verified')}")
    print(f"manifest_path={summary.get('manifest_path')}")
    print(f"bundle_revision={manifest.get('bundle_revision')}")
    for name in sorted(files):
        print(f"verified_file={name} path={files[name].get('path')} sha256={files[name].get('sha256')}")


def _print_resolve(model_name: str, caps: dict[str, Any]) -> None:
    print("MMS Registry Resolve")
    print(f"model={model_name}")
    for key in (
        "context_window_tokens",
        "max_output_tokens",
        "supports_thinking",
        "expected_protocol",
    ):
        print(f"{key}={caps.get(key)} source={caps.get('sources', {}).get(key)}")
    thinking = caps.get("thinking_control") if isinstance(caps.get("thinking_control"), dict) else {}
    print(f"thinking_control_type={thinking.get('control_type') or ''}")
    print(f"thinking_control_path={thinking.get('path') or ''}")


def _print_refresh(summary: dict[str, Any]) -> None:
    print("MMS Registry Refresh Sources")
    print(f"db_path={summary.get('db_path')}")
    print(f"imported_count={summary.get('imported_count')}")
    print(f"skipped_count={summary.get('skipped_count', 0)}")
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


def _print_fetch_catalog(summary: dict[str, Any]) -> None:
    print("MMS Registry Fetch OpenRouter Catalog")
    print(f"db_path={summary.get('db_path')}")
    print(f"transport={summary.get('transport')}")
    print(f"source_kind={summary.get('source_kind')}")
    print(f"source_path={summary.get('source_path')}")
    print(f"snapshot_id={summary.get('snapshot_id')}")
    print(f"model_count={summary.get('model_count')}")
    print(f"content_hash={summary.get('content_hash')}")


def _print_openrouter_diff(summary: dict[str, Any]) -> None:
    print("MMS Registry OpenRouter Candidate Diff")
    print(f"db_path={summary.get('db_path')}")
    print(f"source_snapshot_id={summary.get('source_snapshot_id')}")
    print(f"baseline_snapshot_id={summary.get('baseline_snapshot_id')}")
    print(f"matched_reference_count={summary.get('matched_reference_count')}")
    print(f"missing_reference_count={summary.get('missing_reference_count')}")
    print(f"untracked_catalog_count={summary.get('untracked_catalog_count')}")
    print(f"change_count={summary.get('change_count')}")
    print(f"stored_count={summary.get('stored_count')}")
    for item in summary.get("changes") or []:
        print(
            "candidate_change="
            f"{item.get('model_key')} "
            f"{item.get('provider_model_id')} "
            f"{item.get('field_key')} "
            f"{item.get('change_kind')}"
        )


def _print_scheduled_refresh(summary: dict[str, Any]) -> None:
    print("MMS Registry Scheduled Refresh")
    print(f"db_path={summary.get('db_path')}")
    print(f"dry_run={summary.get('dry_run')}")
    print(f"source_due_count={summary.get('source_due_count')}")
    print(f"openrouter_due={summary.get('openrouter_due')}")
    source_refresh = summary.get("source_refresh") if isinstance(summary.get("source_refresh"), dict) else {}
    openrouter_fetch = summary.get("openrouter_fetch") if isinstance(summary.get("openrouter_fetch"), dict) else {}
    openrouter_diff = summary.get("openrouter_diff") if isinstance(summary.get("openrouter_diff"), dict) else {}
    openrouter_status = summary.get("openrouter_status") if isinstance(summary.get("openrouter_status"), dict) else {}
    print(f"source_imported={source_refresh.get('imported_count', 0)}")
    print(f"source_skipped={source_refresh.get('skipped_count', 0) if 'skipped_count' in source_refresh else source_refresh.get('skipped')}")
    print(f"source_skip_reason={source_refresh.get('reason', '')}")
    print(f"openrouter_source_path={openrouter_status.get('source_path', '')}")
    print(f"openrouter_fetched={not bool(openrouter_fetch.get('skipped', False))}")
    print(f"openrouter_fetch_reason={openrouter_fetch.get('reason', '')}")
    print(f"openrouter_model_count={openrouter_fetch.get('model_count', 0)}")
    print(f"candidate_changes={openrouter_diff.get('stored_count', 0)}")
    print(f"candidate_skip_reason={openrouter_diff.get('reason', '')}")


def _print_backup(summary: dict[str, Any]) -> None:
    print("MMS Registry DB Backup")
    print(f"skipped={summary.get('skipped', False)}")
    print(f"reason={summary.get('reason', '')}")
    print(f"source_db_path={summary.get('source_db_path', '')}")
    print(f"backup_path={summary.get('backup_path', '')}")
    print(f"manifest_path={summary.get('manifest_path', '')}")
    print(f"sha256={summary.get('sha256', '')}")
    print(f"integrity_check={summary.get('integrity_check', '')}")


def _print_restore(summary: dict[str, Any]) -> None:
    print("MMS Registry DB Restore")
    print(f"apply={summary.get('apply', False)}")
    print(f"skipped={summary.get('skipped', False)}")
    print(f"skip_reason={summary.get('skip_reason', '')}")
    print(f"backup_path={summary.get('backup_path', '')}")
    print(f"target_db_path={summary.get('target_db_path', '')}")
    print(f"backup_sha256={summary.get('backup_sha256', '')}")
    print(f"integrity_check={summary.get('integrity_check', '')}")
    pre_restore = summary.get("pre_restore_backup") if isinstance(summary.get("pre_restore_backup"), dict) else {}
    print(f"pre_restore_backup_path={pre_restore.get('backup_path', '')}")
    print(f"restored_integrity_check={summary.get('restored_integrity_check', '')}")


def handle_registry_command(argv: list[str], *, command_name: str = "mms registry") -> int:
    parser = argparse.ArgumentParser(
        prog=command_name,
        description="Manage MMS local model registry source truth.",
    )
    parser.add_argument("--db", default="", help="Override registry sqlite path")
    subparsers = parser.add_subparsers(dest="subcommand")

    subparsers.add_parser("status", help="Show local registry DB status")
    subparsers.add_parser("doctor", help="Alias of status for now; does not change runtime truth")
    backup_parser = subparsers.add_parser("backup-db", help="Create a SQLite backup of the registry DB")
    backup_parser.add_argument("--config-dir", default="", help="Override MMS config dir")
    backup_parser.add_argument("--backup-dir", default="", help="Override backup output dir")
    backup_parser.add_argument("--reason", default="manual", help="Audit reason for this backup")
    restore_parser = subparsers.add_parser("restore-db", help="Restore registry DB from a backup; dry-run unless --apply")
    restore_parser.add_argument("backup_path", help="Backup sqlite path to restore")
    restore_parser.add_argument("--config-dir", default="", help="Override MMS config dir")
    restore_parser.add_argument("--apply", action="store_true", help="Actually replace the target DB after pre-restore backup")
    restore_parser.add_argument("--reason", default="manual", help="Audit reason for this restore")
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
    refresh_parser.add_argument("--if-due", action="store_true", help="Only import sources that are missing, changed, or stale")
    refresh_parser.add_argument("--max-age-hours", type=int, default=DEFAULT_SOURCE_REFRESH_MAX_AGE_HOURS, help="Staleness threshold for --if-due")
    fetch_openrouter_parser = subparsers.add_parser(
        "fetch-openrouter-catalog",
        help="Fetch OpenRouter /api/v1/models into source_snapshot evidence",
    )
    fetch_openrouter_parser.add_argument("--url", default=OPENROUTER_MODELS_API_URL, help="OpenRouter models API URL")
    fetch_openrouter_parser.add_argument("--from-file", default="", help="Import catalog JSON from a local file instead of network")
    fetch_openrouter_parser.add_argument("--timeout", type=float, default=20.0, help="Network timeout in seconds")
    openrouter_diff_parser = subparsers.add_parser(
        "diff-openrouter-catalog",
        help="Compare latest OpenRouter catalog snapshot with calibration references",
    )
    openrouter_diff_parser.add_argument("--no-store", action="store_true", help="Do not write candidate_change rows")
    openrouter_diff_parser.add_argument("--limit", type=int, default=50, help="Max candidate changes to print")
    scheduled_parser = subparsers.add_parser(
        "scheduled-refresh",
        help="Run safe if-due registry refresh for cron/launchd/manual scheduling",
    )
    scheduled_parser.add_argument("--max-age-hours", type=int, default=DEFAULT_SOURCE_REFRESH_MAX_AGE_HOURS)
    scheduled_parser.add_argument("--openrouter-max-age-hours", type=int, default=DEFAULT_OPENROUTER_REFRESH_MAX_AGE_HOURS)
    scheduled_parser.add_argument("--no-openrouter", action="store_true", help="Skip OpenRouter catalog refresh")
    scheduled_parser.add_argument("--no-network", action="store_true", help="Do not perform network fetches")
    scheduled_parser.add_argument("--openrouter-from-file", default="", help="Import OpenRouter catalog JSON from a file")
    scheduled_parser.add_argument("--dry-run", action="store_true", help="Only report due state")
    staleness_parser = subparsers.add_parser("check-staleness", help="Check source reference staleness without importing")
    staleness_parser.add_argument("--path", action="append", default=[], help="Reference JSON snapshot path; may be repeated")
    staleness_parser.add_argument("--max-age-hours", type=int, default=DEFAULT_SOURCE_REFRESH_MAX_AGE_HOURS, help="Staleness threshold")
    publish_parser = subparsers.add_parser(
        "publish-approved",
        help="Publish generated/latest-approved bundle from current local artifacts",
    )
    publish_parser.add_argument("--config-dir", default="", help="Override MMS config dir")
    publish_parser.add_argument("--refresh-sources", action="store_true", help="Refresh source snapshots before publishing")
    verify_parser = subparsers.add_parser("verify", help="Verify latest-approved manifest hashes")
    verify_parser.add_argument("--config-dir", default="", help="Override MMS config dir")
    verify_parser.add_argument("--manifest", default="", help="Override manifest path")
    resolve_parser = subparsers.add_parser("resolve", help="Resolve one model through latest-approved capability facts")
    resolve_parser.add_argument("model")
    resolve_parser.add_argument("--config-dir", default="", help="Override MMS config dir")
    resolve_parser.add_argument("--manifest", default="", help="Override manifest path")

    args = parser.parse_args(argv)
    db_path = args.db or None
    if args.subcommand in {None, "status", "doctor"}:
        _print_status(registry_status(db_path=db_path))
        return 0
    if args.subcommand == "backup-db":
        summary = backup_registry_db(
            config_dir=args.config_dir or None,
            db_path=db_path,
            backup_dir=args.backup_dir or None,
            reason=args.reason or "manual",
        )
        _print_backup(summary)
        return 0
    if args.subcommand == "restore-db":
        summary = restore_registry_db(
            args.backup_path,
            config_dir=args.config_dir or None,
            db_path=db_path,
            apply=bool(args.apply),
            reason=args.reason or "manual",
        )
        _print_restore(summary)
        return 0
    if args.subcommand == "refresh-sources":
        summary = refresh_source_snapshots(
            db_path=db_path,
            paths=args.path or None,
            if_due=bool(args.if_due),
            max_age_hours=int(args.max_age_hours or DEFAULT_SOURCE_REFRESH_MAX_AGE_HOURS),
        )
        _print_refresh(summary)
        return 0
    if args.subcommand == "check-staleness":
        summary = source_freshness(
            db_path=db_path,
            paths=args.path or None,
            max_age_hours=int(args.max_age_hours or DEFAULT_SOURCE_REFRESH_MAX_AGE_HOURS),
        )
        _print_freshness(summary)
        return 0
    if args.subcommand == "fetch-openrouter-catalog":
        summary = fetch_openrouter_catalog(
            db_path=db_path,
            url=args.url or OPENROUTER_MODELS_API_URL,
            from_file=args.from_file or None,
            timeout=float(args.timeout or 20.0),
        )
        _print_fetch_catalog(summary)
        return 0
    if args.subcommand == "diff-openrouter-catalog":
        summary = diff_openrouter_catalog(
            db_path=db_path,
            store=not bool(args.no_store),
            limit=int(args.limit or 50),
        )
        _print_openrouter_diff(summary)
        return 0
    if args.subcommand == "scheduled-refresh":
        summary = scheduled_refresh(
            db_path=db_path,
            max_age_hours=int(args.max_age_hours or DEFAULT_SOURCE_REFRESH_MAX_AGE_HOURS),
            openrouter_max_age_hours=int(args.openrouter_max_age_hours or DEFAULT_OPENROUTER_REFRESH_MAX_AGE_HOURS),
            include_openrouter=not bool(args.no_openrouter),
            no_network=bool(args.no_network),
            openrouter_from_file=args.openrouter_from_file or None,
            dry_run=bool(args.dry_run),
        )
        _print_scheduled_refresh(summary)
        return 0
    if args.subcommand == "publish-approved":
        config_dir = args.config_dir or None
        if args.refresh_sources:
            refresh_source_snapshots(db_path=db_path)
        summary = publish_approved_bundle(config_dir=config_dir, db_path=db_path)
        _print_publish(summary)
        return 0
    if args.subcommand == "verify":
        summary = verify_approved_bundle(config_dir=args.config_dir or None, manifest_path=args.manifest or None)
        _print_verify(summary)
        return 0
    if args.subcommand == "resolve":
        caps = resolve_approved_model(args.model, config_dir=args.config_dir or None, manifest_path=args.manifest or None)
        _print_resolve(args.model, caps)
        return 0
    return 2


__all__ = [
    "DEFAULT_REFERENCE_DIR",
    "handle_registry_command",
    "fetch_openrouter_catalog",
    "diff_openrouter_catalog",
    "scheduled_refresh",
    "backup_registry_db",
    "publish_approved_bundle",
    "refresh_source_snapshots",
    "registry_status",
    "restore_registry_db",
    "resolve_approved_model",
    "source_freshness",
    "verify_approved_bundle",
]
